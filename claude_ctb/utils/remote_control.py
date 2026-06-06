"""Auto-register Claude Code's built-in /remote-control on freshly launched sessions.

Every tmux session that (re)starts a Claude Code TUI routes through here so the
session becomes remotely controllable (claude.ai) without anyone typing
``/remote-control`` by hand. Disable globally with ``CTB_AUTO_REMOTE_CONTROL=0``.

Design (ticket EXP-20260604001639, tcrit v2):
- python owns the idle-detection LOGIC (single source of truth). The bash
  helpers delegate to :func:`pane_ready_from_text` via the module CLI; busy
  markers live in ``busy_markers.txt`` next to this file.
- "fresh" launches (cf / new-project / /fresh) fire as soon as the empty input
  box renders — they cannot be busy, so no idle settling is needed (low latency).
- "restart"/active launches use idle-aware waiting with a stable-2 debounce and a
  bounded timeout; on timeout we notify instead of blind-firing (no silent fail).
- An already-registered guard prevents re-firing /remote-control (which would
  toggle remote control OFF on a session that already has it).
"""

import hashlib
import logging
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)

# Anything in this set (case-insensitive) turns the feature off. An empty/unset
# value keeps the default (on), matching the bash helpers' ${VAR:-1} semantics.
_DISABLED_VALUES = {"0", "false", "no", "off"}

_MARKERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "busy_markers.txt")

# Conservative embedded default used only when busy_markers.txt is missing,
# empty, or unreadable (D6 fallback).
_EMBEDDED_MARKERS = ("esc to interrupt", "esc to cancel", " tokens)")

# Telemetry outcomes (T8).
_TELEMETRY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".omc", "state", "remote-control-telemetry.json",
)

# Per-session rate limit for the manual-registration fallback notification.
# Background self-healing (terminal_health) can retry a permanently-unready
# session every recovery cycle; without this guard each retry would send a
# Telegram alert and flood the user. Hard cap: one alert per session per window.
_FALLBACK_NOTIFY_COOLDOWN = 1800  # seconds (30 min)
_last_fallback_notify = {}  # session_name -> monotonic timestamp


def is_enabled() -> bool:
    """Whether auto /remote-control registration is active (default: on)."""
    return os.environ.get("CTB_AUTO_REMOTE_CONTROL", "1").strip().lower() not in _DISABLED_VALUES


def load_busy_markers():
    """Load busy markers from busy_markers.txt, falling back conservatively.

    Returns (markers, used_fallback). Fallback (embedded defaults) is used when
    the file is absent, unreadable, or contains no usable patterns; the caller is
    expected to warn so the fallback is never silent (D6).
    """
    try:
        if os.path.getsize(_MARKERS_FILE) == 0:
            return list(_EMBEDDED_MARKERS), True
        with open(_MARKERS_FILE, "r", encoding="utf-8") as fh:
            markers = [
                line.rstrip("\n")
                for line in fh
                if line.strip() and not line.lstrip().startswith("#")
            ]
        if not markers:
            return list(_EMBEDDED_MARKERS), True
        return markers, False
    except OSError:
        return list(_EMBEDDED_MARKERS), True


def _bottom_prompt_line(lines):
    """Return the bottom-most line that looks like the live input prompt (❯).

    We scan from the bottom so scrollback copies of an old prompt are ignored
    (tcrit M3 / anchor). Returns the raw line, or None if not found.
    """
    for line in reversed(lines):
        if "❯" in line:
            return line
    return None


def pane_ready_from_text(text, markers=None):
    """Pure idle/ready classifier for a captured tmux pane (T1).

    Returns a dict: {ready, idle, empty_input, prompt_found, anchor, reason}.
    - idle: no busy marker present (conservative — unknown == busy via markers).
    - prompt_found: a live ❯ prompt line exists.
    - empty_input: the prompt has no user-typed text after ❯ (nbsp/space ok).
    - anchor: the prompt line text (for stable-2 hashing by the caller).
    - ready: idle AND prompt_found AND empty_input.
    """
    if markers is None:
        markers, _ = load_busy_markers()

    idle = not any(m and m in text for m in markers)

    lines = text.rstrip("\n").split("\n") if text else []
    prompt = _bottom_prompt_line(lines)
    prompt_found = prompt is not None

    empty_input = False
    anchor = ""
    if prompt_found:
        anchor = prompt.rstrip()
        after = prompt.split("❯", 1)[1] if "❯" in prompt else ""
        # nbsp (\xa0)/whitespace are "empty". Some TUI versions box the prompt as
        # "│ ❯ ... │" — strip a trailing box border before judging emptiness.
        cleaned = after.replace("\xa0", " ").strip().strip("│").strip()
        empty_input = cleaned == ""

    ready = idle and prompt_found and empty_input
    if ready:
        reason = "ready"
    elif not prompt_found:
        reason = "no_prompt"
    elif not idle:
        reason = "busy"
    else:
        reason = "input_not_empty"

    return {
        "ready": ready,
        "idle": idle,
        "empty_input": empty_input,
        "prompt_found": prompt_found,
        "anchor": anchor,
        "reason": reason,
    }


def is_remote_control_active(text):
    """Best-effort check whether /remote-control is already registered (T6 guard).

    The exact active indicator is a Claude Code TUI string to be confirmed by the
    T4 spike; until confirmed it can be overridden via CTB_REMOTE_CONTROL_INDICATOR.
    Returns True only when we can positively detect it — when unknown we return
    False (cannot confirm) so a first registration still proceeds.
    """
    indicator = os.environ.get("CTB_REMOTE_CONTROL_INDICATOR", "").strip()
    candidates = [indicator] if indicator else ["Remote control active", "remote control:"]
    return any(c and c.lower() in text.lower() for c in candidates)


def _capture(session_name):
    """Capture a tmux pane as text, or '' on failure."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session_name, "-p"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return ""
    return result.stdout if result.returncode == 0 else ""


def _anchor_hash(anchor):
    return hashlib.sha256(anchor.encode("utf-8", "replace")).hexdigest()


def record_telemetry(outcome, session_name=""):
    """Append a /remote-control auto-registration outcome counter (T8).

    Outcomes: success | already_registered | fallback_timeout | no_command |
    disabled | unverified. Best-effort; never raises.
    """
    import json
    try:
        os.makedirs(os.path.dirname(_TELEMETRY_FILE), exist_ok=True)
        data = {"counts": {}, "last": {}}
        if os.path.exists(_TELEMETRY_FILE):
            try:
                with open(_TELEMETRY_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                pass
        data.setdefault("counts", {})
        data["counts"][outcome] = data["counts"].get(outcome, 0) + 1
        data.setdefault("last", {})
        data["last"] = {"outcome": outcome, "session": session_name, "ts": time.time()}
        tmp = _TELEMETRY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _TELEMETRY_FILE)
    except Exception as e:  # never let telemetry break registration
        logger.debug("telemetry write failed: %s", e)


def _notify_fallback(session_name, reason):
    """Send a Telegram notification asking for manual /remote-control (T3).

    Rate-limited per session (``_FALLBACK_NOTIFY_COOLDOWN``) so a looping caller
    cannot flood the user. Best-effort: requires bot config; silently degrades to
    a log warning.
    """
    now = time.monotonic()
    last = _last_fallback_notify.get(session_name)
    if last is not None and (now - last) < _FALLBACK_NOTIFY_COOLDOWN:
        logger.info("[%s] fallback notify suppressed (within %ss cooldown)",
                    session_name, _FALLBACK_NOTIFY_COOLDOWN)
        return False
    _last_fallback_notify[session_name] = now
    try:
        from ..telegram.notifier import SmartNotifier
        SmartNotifier().send_manual_notification(
            title="⚠️ /remote-control 자동등록 실패",
            content=f"세션 {session_name}: {reason}. 수동으로 /remote-control 입력이 필요합니다.",
            urgency="normal",
        )
        return True
    except Exception as e:
        logger.warning("[%s] fallback notify failed (%s): manual /remote-control needed (%s)",
                       session_name, e, reason)
        return False


def wait_until_ready(session_name, mode="fresh", timeout=None,
                     initial_delay=None, poll_interval=None):
    """Poll the pane until Claude is ready for /remote-control.

    mode="fresh": new launch — cannot be busy. Fire as soon as an empty prompt
        renders (low latency). Defaults: no initial delay, 0.4s poll, ~10s cap.
    mode="restart": session may be active. Require a stable-2 ready (same anchor
        hash on two reads ≥1s apart) and a bounded timeout. Defaults: 60s cap.

    Returns (ready: bool, reason: str).
    """
    if mode == "restart":
        timeout = 60 if timeout is None else timeout
        initial_delay = 3.0 if initial_delay is None else initial_delay
        poll_interval = 1.0 if poll_interval is None else poll_interval
    else:  # fresh
        timeout = 10 if timeout is None else timeout
        initial_delay = 0.0 if initial_delay is None else initial_delay
        poll_interval = 0.4 if poll_interval is None else poll_interval

    if initial_delay:
        time.sleep(initial_delay)

    deadline = time.monotonic() + timeout
    prev_hash = None
    last_reason = "timeout"
    while time.monotonic() < deadline:
        status = pane_ready_from_text(_capture(session_name))
        last_reason = status["reason"]
        if status["ready"]:
            if mode != "restart":
                return True, "ready"
            # stable-2 debounce (T2): same anchor on two consecutive ready reads.
            cur_hash = _anchor_hash(status["anchor"])
            if prev_hash == cur_hash:
                return True, "ready"
            prev_hash = cur_hash
        else:
            prev_hash = None  # busy/typing reappeared → reset (D5)
        time.sleep(poll_interval)
    return False, last_reason


def _send_keys(session_name):
    """Send the /remote-control slash command (text → Escape → Enter).

    A slash command's autocomplete swallows a same-keystroke Enter, so send the
    parts separately, mirroring the /exit delivery used elsewhere.
    """
    subprocess.run(["tmux", "send-keys", "-t", session_name, "/remote-control"], timeout=5)
    time.sleep(0.5)
    subprocess.run(["tmux", "send-keys", "-t", session_name, "Escape"], timeout=5)
    time.sleep(0.3)
    subprocess.run(["tmux", "send-keys", "-t", session_name, "Enter"], timeout=5)
    time.sleep(1.0)  # let Remote Control connect before any following prompt


def send_remote_control(session_name, wait=True, initial_delay=None, timeout=None,
                        mode="fresh", notify=True):
    """Register /remote-control on a tmux session running Claude Code.

    ``wait=True`` waits (mode-dependent) for an idle, empty prompt before sending;
    on timeout it does NOT blind-fire — it notifies for manual registration (T3).
    ``wait=False`` sends immediately (caller guarantees an empty prompt).
    ``notify=False`` suppresses the manual-registration fallback alert — use it
    for background self-healing (e.g. terminal recovery) that retries on its own.

    Returns True if the command was dispatched. Honors CTB_AUTO_REMOTE_CONTROL.
    """
    if not is_enabled():
        return False

    if wait:
        ready, reason = wait_until_ready(session_name, mode=mode,
                                         timeout=timeout, initial_delay=initial_delay)
        if not ready:
            if notify:
                _notify_fallback(session_name, f"idle 윈도우 미확보 ({reason})")
            record_telemetry("fallback_timeout", session_name)
            logger.warning("[%s] not ready (%s); skipped blind-fire", session_name, reason)
            return False

    # Already-registered guard (T6): don't re-fire (would toggle OFF).
    if is_remote_control_active(_capture(session_name)):
        record_telemetry("already_registered", session_name)
        logger.info("[%s] /remote-control already active; skip", session_name)
        return False

    try:
        _send_keys(session_name)
    except Exception as e:
        logger.error("[%s] failed to register /remote-control: %s", session_name, e)
        record_telemetry("fallback_timeout", session_name)
        return False

    # Best-effort success verification (T4). Indicator may be unconfirmed → warn,
    # never silently assume success.
    if is_remote_control_active(_capture(session_name)):
        record_telemetry("success", session_name)
    else:
        record_telemetry("unverified", session_name)
        logger.info("[%s] /remote-control sent; registration unverified", session_name)
    logger.info("[%s] /remote-control registered", session_name)
    return True


def send_remote_control_bg(session_name, **kwargs):
    """Fire-and-forget :func:`send_remote_control` in a daemon thread.

    Non-blocking: safe to call from synchronous launch paths and the asyncio bot
    loop alike. Use for plain (re)launches with no follow-up prompt.
    """
    if not is_enabled():
        return
    threading.Thread(
        target=send_remote_control, args=(session_name,), kwargs=kwargs, daemon=True
    ).start()


def _cli(argv):
    """Module CLI so bash helpers can reuse the SoT logic (D1).

    ``--check-ready`` reads a captured pane from stdin and exits 0 if ready,
    1 otherwise (prints the reason). ``--markers`` prints the active markers.
    """
    if "--markers" in argv:
        markers, fb = load_busy_markers()
        if fb:
            sys.stderr.write("[remote_control] busy_markers.txt missing/empty — using embedded defaults\n")
        sys.stdout.write("\n".join(markers) + "\n")
        return 0
    if "--check-ready" in argv:
        text = sys.stdin.read()
        status = pane_ready_from_text(text)
        sys.stdout.write(status["reason"] + "\n")
        return 0 if status["ready"] else 1
    sys.stderr.write("usage: python -m claude_ctb.utils.remote_control [--check-ready|--markers]\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
