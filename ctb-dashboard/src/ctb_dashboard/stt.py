"""Speech to text for the console's push-to-talk button.

The audio is sent to OpenAI's ``gpt-transcribe`` with a prompt that names
what the session is about -- its project and branch, the identifiers on its
screen, and the user's own glossary -- because that is what turns a mixed
Korean/English instruction from "Clono sessione" into "Claude Ops 세션에서
pytest". The result comes back as text only; putting it into a session is
the user's Enter, never this module's.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

import httpx

MODEL = "gpt-transcribe"
LANGUAGE = "ko"
ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
PROMPT_MAX_CHARS = 900
TIMEOUT_S = 30.0
GLOSSARY_PATH = os.path.expanduser("~/.claude-ops/stt-glossary.txt")

# Words that look like code: a path, a file with an extension, a command with
# a dash or underscore, CamelCase. Plain words in either language are left
# out -- the model knows those; it is the names it cannot guess.
_IDENT_RE = re.compile(
    r"(?<![\w./-])("
    r"[\w./-]*\.[A-Za-z]{1,5}"      # file.ext, a/b/c.py
    r"|[A-Za-z][\w-]*[_-][\w-]+"     # snake_case, kebab-case
    r"|[a-z]+[A-Z][A-Za-z]+"          # camelCase
    r"|[A-Z][a-z]+[A-Z][A-Za-z]+"     # CamelCase
    r")(?![\w./-])"
)
# Commands worth hearing right even without an odd character in them.
_COMMANDS = {
    "pytest", "ruff", "git", "commit", "rebase", "merge", "push", "pull", "stash",
    "checkout", "branch", "diff", "grep", "tmux", "systemctl", "uv", "npm", "docker",
    "python", "node", "curl", "ssh",
}
_CMD_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(_COMMANDS)) + r")(?![\w-])")


def api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")


def enabled() -> bool:
    return bool(api_key())


def session_terms(session: str) -> list[str]:
    name = re.sub(r"^claude[_-]", "", session or "")
    if not name:
        return []
    wt = name.find("_wt_")
    if wt == -1:
        return [name]
    return [name[:wt], name[wt + 4:]]


def screen_terms(lines: Iterable[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        for m in _IDENT_RE.finditer(line):
            found.append(m.group(1).strip("./-"))
        for m in _CMD_RE.finditer(line):
            found.append(m.group(1))
    return [t for t in found if len(t) >= 2]


def read_glossary(path: str = GLOSSARY_PATH) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []


def build_prompt(session: str, screen_lines: Iterable[str], glossary: Iterable[str]) -> str:
    """One line of context, then the terms: the session first, then what is
    on its screen, then the glossary until the budget runs out. The glossary
    can hold hundreds of terms; the ones about this session must not be the
    ones that get cut."""
    seen: set[str] = set()
    terms: list[str] = []
    for t in [*session_terms(session), *screen_terms(screen_lines), *glossary]:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(t)
    head = "한국어와 영어가 섞인 개발 지시문. 용어: "
    out = head
    for t in terms:
        piece = (", " if out != head else "") + t
        if len(out) + len(piece) > PROMPT_MAX_CHARS:
            break
        out += piece
    return out


def extension_for(mime: str) -> str:
    m = (mime or "").split(";")[0].strip().lower()
    return {
        "audio/webm": "webm", "video/webm": "webm",
        "audio/mp4": "mp4", "video/mp4": "mp4", "audio/x-m4a": "m4a", "audio/m4a": "m4a",
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
        "audio/flac": "flac",
    }.get(m, "webm")


class TranscribeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def transcribe(audio: bytes, mime: str, prompt: str, *, api_key: str | None = None,
               transport: httpx.BaseTransport | None = None) -> dict:
    """Send one clip; return {"text", "seconds"}. Raises TranscribeError."""
    key = api_key if api_key is not None else globals()["api_key"]()
    if not key:
        raise TranscribeError(503, "OPENAI_API_KEY is not set")
    ext = extension_for(mime)
    files = {"file": (f"audio.{ext}", audio, mime.split(";")[0] or f"audio/{ext}")}
    data = {"model": MODEL, "language": LANGUAGE, "prompt": prompt}
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT_S) as client:
            r = client.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"},
                            data=data, files=files)
    except httpx.HTTPError as e:
        raise TranscribeError(502, f"upstream unreachable: {e}") from e
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message") or r.text
        except ValueError:
            msg = r.text
        raise TranscribeError(r.status_code, msg[:300])
    body = r.json()
    usage = body.get("usage") or {}
    return {"text": (body.get("text") or "").strip(), "seconds": usage.get("seconds")}
