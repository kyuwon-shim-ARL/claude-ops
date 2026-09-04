"""Speech to text for the console: the audio goes to OpenAI's gpt-transcribe
with a prompt built from what the session is about, and the words come back
as a draft. Nothing here sends anything to a session."""


import httpx
import pytest

from ctb_dashboard import stt


# --- prompt building ---------------------------------------------------------

def test_prompt_names_the_session_and_its_branch():
    p = stt.build_prompt("claude_uni-mol-QSAR_wt_scan-scope", [], [])
    assert "uni-mol-QSAR" in p and "scan-scope" in p


def test_prompt_picks_identifiers_off_the_screen_not_prose():
    lines = [
        "  Read src/ctb_dashboard/server.py and run pytest tests/test_stt.py -q",
        "그 다음에 커밋해 주세요 이것은 그냥 문장입니다",
        "$ git rebase -i HEAD~3",
    ]
    p = stt.build_prompt("claude_ops", lines, [])
    assert "server.py" in p and "test_stt.py" in p and "pytest" in p
    assert "rebase" in p
    assert "그냥" not in p  # plain words are not glossary


def test_prompt_carries_the_users_glossary_first():
    p = stt.build_prompt("claude_ops", ["pytest"], ["Uni-Mol", "scaffold split"])
    assert p.index("Uni-Mol") < p.index("pytest")


def test_prompt_is_bounded():
    lines = [f"very_long_identifier_number_{i}.py" for i in range(400)]
    p = stt.build_prompt("claude_ops", lines, [])
    assert len(p) <= stt.PROMPT_MAX_CHARS


def test_prompt_dedups_terms():
    p = stt.build_prompt("claude_ops", ["pytest pytest pytest", "pytest"], ["pytest"])
    assert p.count("pytest") == 1


# --- the API call ------------------------------------------------------------

def _transport(capture, status=200, body=None):
    def handler(request: httpx.Request):
        capture["request"] = request
        capture["content"] = request.read()
        return httpx.Response(status, json=body if body is not None else {"text": "hi", "usage": {"seconds": 3}})
    return httpx.MockTransport(handler)


def test_transcribe_posts_multipart_with_model_and_prompt():
    cap = {}
    r = stt.transcribe(b"RIFF....", "audio/wav", "claude-ops, pytest", api_key="sk-test",
                       transport=_transport(cap))
    assert r == {"text": "hi", "seconds": 3}
    req = cap["request"]
    assert req.url.path == "/v1/audio/transcriptions"
    assert req.headers["authorization"] == "Bearer sk-test"
    body = cap["content"]
    assert b"gpt-transcribe" in body and b"claude-ops, pytest" in body
    assert b'filename="audio.wav"' in body
    assert b"RIFF...." in body


@pytest.mark.parametrize("mime,ext", [
    ("audio/webm;codecs=opus", "webm"), ("audio/mp4", "mp4"), ("audio/mpeg", "mp3"),
    ("audio/ogg", "ogg"), ("audio/wav", "wav"), ("video/mp4", "mp4"), ("", "webm"),
])
def test_extension_follows_the_mime_type(mime, ext):
    assert stt.extension_for(mime) == ext


def test_upstream_failure_is_reported_not_swallowed():
    cap = {}
    with pytest.raises(stt.TranscribeError) as e:
        stt.transcribe(b"x", "audio/wav", "", api_key="sk-test",
                       transport=_transport(cap, 401, {"error": {"message": "bad key"}}))
    assert e.value.status == 401 and "bad key" in str(e.value)


def test_transcribe_requires_a_key():
    with pytest.raises(stt.TranscribeError) as e:
        stt.transcribe(b"x", "audio/wav", "", api_key="")
    assert e.value.status == 503
