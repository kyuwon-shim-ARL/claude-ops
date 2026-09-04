"""/api/stt: token-gated, audit-logged, bounded, and it never touches tmux
input -- it hands text back to the console, which drafts it."""

import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
from ctb_dashboard import stt
from ctb_dashboard.server import app

_SECRET = "control-secret-under-test"
_AUDIO = {"Content-Type": "audio/webm;codecs=opus", "X-CTB-Secret": _SECRET}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "send_prompt", lambda *a, **k: pytest.fail("stt typed into a session"))
    monkeypatch.setattr(_srv, "send_key", lambda *a, **k: pytest.fail("stt pressed a key"))
    monkeypatch.setattr(_srv, "_screen_lines_for_stt", lambda name: ["pytest tests/test_stt.py"])
    monkeypatch.setattr(stt, "read_glossary", lambda *a, **k: ["Uni-Mol"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return TestClient(app)


def test_config_says_whether_the_mic_can_show(client, monkeypatch):
    assert client.get("/api/stt/config").json() == {"enabled": True, "model": stt.MODEL}
    monkeypatch.delenv("OPENAI_API_KEY")
    assert client.get("/api/stt/config").json()["enabled"] is False


def test_stt_without_token_is_rejected(client):
    r = client.post("/api/stt?session=claude_ops", content=b"x", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 403


def test_stt_without_a_key_is_503(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    r = client.post("/api/stt?session=claude_ops", content=b"x", headers=_AUDIO)
    assert r.status_code == 503


def test_stt_rejects_an_oversized_clip(client, monkeypatch):
    monkeypatch.setattr(_srv, "_STT_MAX_BYTES", 10)
    r = client.post("/api/stt?session=claude_ops", content=b"x" * 11, headers=_AUDIO)
    assert r.status_code == 413


def test_stt_rejects_an_empty_clip(client):
    r = client.post("/api/stt?session=claude_ops", content=b"", headers=_AUDIO)
    assert r.status_code == 400


def test_stt_rejects_a_bad_session_name(client):
    r = client.post("/api/stt?session=../x", content=b"x", headers=_AUDIO)
    assert r.status_code == 422


def test_stt_transcribes_with_a_prompt_built_from_the_session(client, monkeypatch):
    seen = {}

    def fake(audio, mime, prompt, **kw):
        seen.update(audio=audio, mime=mime, prompt=prompt)
        return {"text": "pytest 돌려줘", "seconds": 4}

    monkeypatch.setattr(stt, "transcribe", fake)
    r = client.post("/api/stt?session=claude_uni-mol-QSAR", content=b"opus-bytes", headers=_AUDIO)
    assert r.status_code == 200
    assert r.json() == {"text": "pytest 돌려줘", "seconds": 4}
    assert seen["audio"] == b"opus-bytes"
    assert seen["mime"].startswith("audio/webm")
    for term in ("Uni-Mol", "uni-mol-QSAR", "test_stt.py"):
        assert term in seen["prompt"], term


def test_upstream_errors_pass_through_with_their_status(client, monkeypatch):
    def fake(*a, **k):
        raise stt.TranscribeError(429, "quota")
    monkeypatch.setattr(stt, "transcribe", fake)
    r = client.post("/api/stt?session=claude_ops", content=b"x", headers=_AUDIO)
    assert r.status_code == 502
    assert "quota" in r.json()["detail"] and "429" in r.json()["detail"]
