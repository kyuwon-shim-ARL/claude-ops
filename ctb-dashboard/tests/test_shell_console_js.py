"""isShellSession() -- the console's one source of truth for whether a send
should go through the shell path (no Claude readiness gate, no draft
persistence) or the ordinary prompt path.

Driven through node against the real shipped JS, with window.ctbSessionAll
standing in for what the board publishes from the server's snapshot. A
string-presence check here would prove nothing -- the function has to
actually discriminate for a session that is and is not marked.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CONSOLE_JS = (
    Path(__file__).resolve().parents[1]
    / "src" / "ctb_dashboard" / "static" / "js" / "session-control.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
global.window = {{
  ctbSessionAll: {catalog},
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete',
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
process.stdout.write(JSON.stringify(window.ctbConsole._isShellSession({name})));
"""


def is_shell(catalog, name):
    script = _HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        catalog=json.dumps(catalog),
        name=json.dumps(name),
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


CATALOG = [
    {"name": "claude_alpha", "shell": False},
    {"name": "claude_alpha_sh", "shell": True},
]


def test_marked_session_is_shell():
    assert is_shell(CATALOG, "claude_alpha_sh") is True


def test_unmarked_session_is_not_shell():
    assert is_shell(CATALOG, "claude_alpha") is False


def test_unknown_session_is_not_shell():
    """Absence is not evidence either way -- default to the ordinary (gated)
    path rather than silently skipping the readiness check for a session
    nobody has published anything about."""
    assert is_shell(CATALOG, "claude_missing") is False


def test_no_catalogue_published_yet_defaults_to_not_shell():
    assert is_shell(None, "claude_alpha_sh") is False


# --- driving submit() end to end -------------------------------------------
#
# The module never builds its DOM through this harness's bare-bones
# `document.createElement` stub (it lacks classList, scrollIntoView,
# querySelectorAll, ...), so build()/show() cannot run here. Instead `el`
# (returned live by `_els()`) and `_state` are populated directly -- the
# same object submit() closes over -- which exercises submit()'s real async
# logic (post(), saveDrafts(), rememberTail/pollTail's draft math) without
# needing the DOM construction at all.
#
# A minimal localStorage and window.ctbControl.send are the only stand-ins
# needed beyond that.

_SUBMIT_HARNESS = """
const stores = {{}};
global.localStorage = {{
  getItem(k) {{ return Object.prototype.hasOwnProperty.call(stores, k) ? stores[k] : null; }},
  setItem(k, v) {{ stores[k] = String(v); }},
  removeItem(k) {{ delete stores[k]; }},
}};
const sent = [];
global.window = {{
  ctbSessionAll: {catalog},
  ctbControl: {{
    send(path, opts) {{
      sent.push({{ path, body: opts && opts.body ? JSON.parse(opts.body) : null }});
      return Promise.resolve({{
        ok: true, status: 200,
        json: () => Promise.resolve({{ status: 'sent', confirmed: true, submitted: true }}),
      }});
    }},
  }},
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
  confirm: () => {{ global.__confirmCalled = true; return false; }},
  matchMedia: () => ({{ matches: false }}),
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete', getElementById: () => null,
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => new Promise(() => {{}});  // pollTail's own fetch never needs to resolve for this test
global.AbortController = undefined;
require({path});
const api = window.ctbConsole;
const el = api._els();
el.input = {{ value: {text} }};
el.send = {{}};
el.status = null;
api._state.session = {session};
api._state.busy = false;
api._loadDrafts();
Object.assign(api._state.drafts, {drafts});

api._submit({via});

setTimeout(() => {{
  process.stdout.write(JSON.stringify({{
    sent,
    drafts_after: JSON.parse(localStorage.getItem('ctb_console_drafts') || '{{}}'),
    tails_after: JSON.parse(localStorage.getItem('ctb_console_tails') || '{{}}'),
    confirm_called: !!global.__confirmCalled,
  }}));
}}, 50);
"""


def _drive_submit(catalog, session, text, drafts=None, via="null", pre_drafts_raw=None):
    """Runs the real session-control.js submit() against the harness above
    and returns {sent, drafts_after, tails_after, confirm_called}."""
    script = _SUBMIT_HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        catalog=json.dumps(catalog),
        text=json.dumps(text),
        session=json.dumps(session),
        drafts=json.dumps(drafts or {}),
        via="null" if via is None else json.dumps(via),
    )
    if pre_drafts_raw is not None:
        # Seed localStorage before require() runs, so a pre-existing stored
        # entry for a now-shell session is what the test exercises.
        seed = f"stores['ctb_console_drafts'] = {json.dumps(json.dumps(pre_drafts_raw))};\n"
        script = script.replace("require(", seed + "require(", 1)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


SHELL_CATALOG = [{"name": "claude_demo_sh", "shell": True}]
PLAIN_CATALOG = [{"name": "claude_demo", "shell": False}]


def test_typing_in_a_shell_session_never_reaches_drafts_localStorage():
    out = _drive_submit(SHELL_CATALOG, "claude_demo_sh", "export SECRET=topsecret123")
    assert out["drafts_after"] == {}


def test_a_preexisting_stored_draft_for_a_shell_session_is_purged_through_submit():
    """End-to-end: a draft already in localStorage for the very session
    about to be sent through survives in memory only long enough for the
    send's own cleanup; the OTHER coverage below isolates saveDrafts()'s
    filter on its own (a shell entry injected straight into state.drafts,
    never through loadDrafts, so the only thing that can remove it is
    saveDrafts() itself)."""
    out = _drive_submit(SHELL_CATALOG, "claude_demo_sh", "echo hi",
                        pre_drafts_raw={"claude_demo_sh": "old secret draft",
                                        "claude_demo": "keep me"})
    assert "claude_demo_sh" not in out["drafts_after"]
    assert out["drafts_after"].get("claude_demo") == "keep me"


def test_saveDrafts_alone_purges_a_shell_entry_injected_directly_into_state():
    """Isolates saveDrafts()'s own filter from loadDrafts()'s: the shell
    entry is put into state.drafts directly, never through loadDrafts, so
    only saveDrafts() can be what removes it before the write."""
    out = _drafts_after_save(
        SHELL_CATALOG + [{"name": "claude_keep", "shell": False}],
        {"claude_demo_sh": "typed directly into state, never loaded",
         "claude_keep": "keep me"})
    assert "claude_demo_sh" not in out
    assert out.get("claude_keep") == "keep me"


_TAILS_HARNESS = """
const stores = {{}};
global.localStorage = {{
  getItem(k) {{ return Object.prototype.hasOwnProperty.call(stores, k) ? stores[k] : null; }},
  setItem(k, v) {{ stores[k] = String(v); }},
  removeItem(k) {{ delete stores[k]; }},
}};
stores['ctb_console_tails'] = JSON.stringify({seed});
global.window = {{
  ctbSessionAll: {catalog},
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete', getElementById: () => null,
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const api = window.ctbConsole;
api._rememberTail({name}, {{ log: {log}, cols: 80 }});
process.stdout.write(JSON.stringify(JSON.parse(localStorage.getItem('ctb_console_tails') || '{{}}')));
"""


def _tails_after_remember(catalog, name, log, seed):
    script = _TAILS_HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)), catalog=json.dumps(catalog),
        name=json.dumps(name), log=json.dumps(log), seed=json.dumps(seed),
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_remembering_a_shell_sessions_tail_never_writes_it_to_localStorage():
    out = _tails_after_remember(SHELL_CATALOG, "claude_demo_sh", "secret screen content", seed={})
    assert "claude_demo_sh" not in out


def test_remembering_any_tail_purges_a_preexisting_shell_entry():
    """Same guard as drafts: a name stored before it was marked shell is
    purged on the very next write, not just skipped going forward."""
    out = _tails_after_remember(
        PLAIN_CATALOG + [{"name": "claude_demo_sh", "shell": True}],
        "claude_demo", "ordinary screen",
        seed={"claude_demo_sh": {"log": "old secret screen", "at": 1, "cols": 80}})
    assert "claude_demo_sh" not in out
    assert "claude_demo" in out


def test_post_body_carries_shell_true_for_a_shell_session():
    out = _drive_submit(SHELL_CATALOG, "claude_demo_sh", "echo hi")
    assert out["sent"] == [{"path": "/api/sessions/claude_demo_sh/prompt",
                             "body": {"text": "echo hi", "shell": True}}]


def test_post_body_has_no_shell_flag_for_an_ordinary_session():
    out = _drive_submit(PLAIN_CATALOG, "claude_demo", "echo hi")
    assert out["sent"] == [{"path": "/api/sessions/claude_demo/prompt",
                             "body": {"text": "echo hi"}}]
    assert out["drafts_after"] == {}  # sent text is cleared from the draft on 200


_DRAFTS_HARNESS = """
const stores = {{}};
global.localStorage = {{
  getItem(k) {{ return Object.prototype.hasOwnProperty.call(stores, k) ? stores[k] : null; }},
  setItem(k, v) {{ stores[k] = String(v); }},
  removeItem(k) {{ delete stores[k]; }},
}};
if ({seed}) stores['ctb_console_drafts'] = JSON.stringify({seed});
global.window = {{
  ctbSessionAll: {catalog},
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete', getElementById: () => null,
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => Promise.resolve();
require({path});
const api = window.ctbConsole;
api._loadDrafts();
Object.assign(api._state.drafts, {state_drafts});
api._saveDrafts();
process.stdout.write(JSON.stringify(JSON.parse(localStorage.getItem('ctb_console_drafts') || '{{}}')));
"""


def _drafts_after_save(catalog, state_drafts, seed=None):
    script = _DRAFTS_HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)), catalog=json.dumps(catalog),
        state_drafts=json.dumps(state_drafts), seed=json.dumps(seed),
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_an_ordinary_sessions_draft_still_reaches_localStorage():
    """The centralised guard (saveDrafts filtering isShellSession) must not
    have turned into a guard that drops everything."""
    out = _drafts_after_save(PLAIN_CATALOG, {"claude_demo": "half-typed instruction"})
    assert out == {"claude_demo": "half-typed instruction"}


def test_loadDrafts_purges_a_shell_entry_on_load_not_only_on_next_save():
    out = _drafts_after_save(
        SHELL_CATALOG, {},  # nothing newly typed this run
        seed={"claude_demo_sh": "old secret", "claude_demo": "keep"})
    assert out == {"claude_demo": "keep"}


# --- confirm-resend only when still on the same session -------------------

_CONFIRM_HARNESS = """
const stores = {{}};
global.localStorage = {{
  getItem(k) {{ return Object.prototype.hasOwnProperty.call(stores, k) ? stores[k] : null; }},
  setItem(k, v) {{ stores[k] = String(v); }},
  removeItem(k) {{ delete stores[k]; }},
}};
let switchAfterFirstSend = {switch_away};
const sent = [];
global.window = {{
  ctbSessionAll: {catalog},
  ctbControl: {{
    send(path, opts) {{
      const call = {{ path, body: opts && opts.body ? JSON.parse(opts.body) : null }};
      sent.push(call);
      // The FIRST send is the one the test refuses with reason 'shell'; the
      // console may switch sessions before that response lands.
      if (sent.length === 1 && switchAfterFirstSend) {{
        api_state_session_switch();
      }}
      return Promise.resolve({{
        ok: false, status: 409,
        json: () => Promise.resolve({{ status: 'refused', reason: 'shell', message: 'x' }}),
      }});
    }},
  }},
  location: {{search:'', pathname:'/'}}, addEventListener(){{}}, history:{{}},
  confirm: () => {{ global.__confirmCalled = true; return false; }},
  matchMedia: () => ({{ matches: false }}),
}};
global.document = {{
  addEventListener(){{}}, readyState:'complete', getElementById: () => null,
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}}, appendChild(){{}}}}),
  body: {{appendChild(){{}}, removeChild(){{}}}},
}};
global.navigator = {{}};
global.fetch = () => new Promise(() => {{}});
require({path});
const api = window.ctbConsole;
function api_state_session_switch() {{ api._state.session = 'claude_other'; }}
const el = api._els();
el.input = {{ value: 'echo hi' }};
el.send = {{}};
el.status = null;
api._state.session = 'claude_real';
api._state.busy = false;
api._state.drafts = {{}};

api._submit(null);

setTimeout(() => {{
  process.stdout.write(JSON.stringify({{ confirm_called: !!global.__confirmCalled }}));
}}, 50);
"""


def _confirm_offered(switch_away):
    script = _CONFIRM_HARNESS.format(
        path=json.dumps(str(CONSOLE_JS)),
        catalog=json.dumps(PLAIN_CATALOG + [{"name": "claude_real", "shell": False},
                                             {"name": "claude_other", "shell": False}]),
        switch_away="true" if switch_away else "false",
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["confirm_called"]


def test_confirm_resend_is_offered_when_still_on_the_refused_session():
    assert _confirm_offered(switch_away=False) is True


def test_confirm_resend_is_not_offered_after_switching_sessions():
    """The request can land after the console has moved on -- resending (or
    even asking) into whatever is open now is worse than just reporting the
    refusal."""
    assert _confirm_offered(switch_away=True) is False

