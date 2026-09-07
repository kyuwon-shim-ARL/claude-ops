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
    body = r.json()
    assert body["text"] == "pytest 돌려줘"
    assert body["seconds"] == 4
    # The response also carries the day's meter, so the console can warn as
    # the budget runs down.
    assert body["spent_today"] == 4.0
    assert body["daily_limit"] == _srv._STT_DAILY_SECONDS
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


# --- the lab -----------------------------------------------------------------

@pytest.fixture
def lab(client, monkeypatch, tmp_path):
    from ctb_dashboard import stt_corpus as sc
    monkeypatch.setattr(sc, "RESULTS_PATH", tmp_path / "results.jsonl")
    monkeypatch.setattr(sc, "EVAL_SET_PATH", tmp_path / "set.json")
    monkeypatch.setattr(stt, "GLOSSARY_PATH", str(tmp_path / "g.txt"))
    monkeypatch.setattr(sc.stt, "GLOSSARY_PATH", str(tmp_path / "g.txt"))
    monkeypatch.setattr(sc, "promote_learned", lambda missed, path=None: (tmp_path / "g.txt").write_text("\n".join(missed)))
    monkeypatch.setattr(_srv, "get_all_claude_sessions", lambda: {"claude_ops"})
    monkeypatch.setattr(sc, "iter_user_prompts", lambda *a, **k: iter([
        sc.Prompt("pytest 돌려줘 지금 바로", "a"), sc.Prompt("ops 세션 열어줘 빨리", "a"),
        sc.Prompt("이 문장은 한국어만 있습니다", "a"), sc.Prompt("run all the tests now", "a")]))
    monkeypatch.setattr(sc, "rebuild_glossary", lambda **k: 5)
    return client


def test_eval_set_is_built_from_real_prompts(lab):
    r = lab.get("/api/stt/eval/set")
    assert r.status_code == 200
    items = r.json()["items"]
    assert {it["text"] for it in items} == {"pytest 돌려줘 지금 바로", "ops 세션 열어줘 빨리",
                                            "이 문장은 한국어만 있습니다", "run all the tests now"}
    sess = next(it for it in items if it["category"] == "session")
    assert sess["session"] == "claude_ops"


def test_eval_scores_persists_and_promotes_misses(lab, tmp_path):
    body = {"id": "e01", "ref": "uni-mol-QSAR 에서 pytest 돌려줘", "hyp": "유니몰 에서 pytest 돌려줘",
            "engine": "gpt", "hints": True, "seconds": 3, "category": "mixed"}
    r = lab.post("/api/stt/eval", json=body, headers={"X-CTB-Secret": _SECRET})
    assert r.status_code == 200
    out = r.json()
    assert out["missed"] == ["uni-mol-QSAR"] and 0 < out["cer"] < 1
    assert out["stats"]["n"] == 1 and out["stats"]["by_engine"]["gpt"]["n"] == 1
    assert (tmp_path / "g.txt").read_text() == "uni-mol-QSAR"
    assert lab.get("/api/stt/eval/results").json()["top_missed"] == [["uni-mol-QSAR", 1]]


def test_eval_ios_baseline_does_not_touch_the_glossary(lab, tmp_path):
    body = {"id": "e01", "ref": "pytest 돌려줘", "hyp": "파이테스트 돌려줘", "engine": "ios", "hints": False}
    r = lab.post("/api/stt/eval", json=body, headers={"X-CTB-Secret": _SECRET})
    assert r.status_code == 200 and r.json()["missed"] == ["pytest"]
    assert not (tmp_path / "g.txt").exists()


def test_eval_requires_the_token(lab):
    assert lab.post("/api/stt/eval", json={"id": "e", "ref": "a", "hyp": "a"}).status_code == 403
    assert lab.post("/api/stt/eval/rebuild", json={}).status_code == 403


def test_rebuild_reports_sizes(lab):
    r = lab.post("/api/stt/eval/rebuild", json={}, headers={"X-CTB-Secret": _SECRET})
    assert r.status_code == 200
    assert r.json() == {"glossary_size": 5, "set_size": 4, "source_prompts": 4}


def test_hints_off_sends_no_prompt(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(stt, "transcribe", lambda a, m, p, **k: seen.update(prompt=p) or {"text": "x", "seconds": 1})
    monkeypatch.setattr(_srv, "_refresh_glossary_if_stale", lambda: pytest.fail("refreshed with hints off"))
    r = client.post("/api/stt?session=claude_ops&hints=0", content=b"x", headers=_AUDIO)
    assert r.status_code == 200 and seen["prompt"] == ""


def test_lab_page_is_served(client):
    r = client.get("/stt-lab")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


# --- the spend cap ----------------------------------------------------------
#
# The transcriber bills by the minute of audio. Nothing else in the request
# path bounds money: the size limit bounds one upload and the rate limiter
# bounds requests per minute, and neither knows what a clip costs. These are
# the tests for the one guard that does -- including the failure that would
# retire it silently.

@pytest.fixture
def billed(client, monkeypatch):
    """A transcriber that reports a duration, and a record of what it was
    asked to do."""
    calls = []

    def _fake(audio, mime, prompt, **kw):
        calls.append(len(audio))
        return {"text": "네", "seconds": 600.0}

    monkeypatch.setattr(stt, "transcribe", _fake)
    monkeypatch.setattr(_srv, "_clip_seconds", lambda audio, mime: 5.0)
    return calls


def test_a_clip_adds_its_billed_seconds_to_the_day(client, billed):
    r = client.post("/api/stt?session=claude_ops&hints=0", content=b"x" * 999, headers=_AUDIO)
    assert r.status_code == 200
    assert r.json()["spent_today"] == 600.0
    r = client.post("/api/stt?session=claude_ops&hints=0", content=b"x" * 999, headers=_AUDIO)
    assert r.json()["spent_today"] == 1200.0


def test_the_day_closes_once_the_budget_is_spent(client, billed, monkeypatch):
    monkeypatch.setattr(_srv, "_STT_DAILY_SECONDS", 600.0)   # one clip spends it
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 200
    r = client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO)
    assert r.status_code == 429
    assert "budget" in r.json()["detail"].lower()
    assert len(billed) == 1, "the second clip must not reach the biller"


def test_the_cap_survives_a_state_file_it_cannot_write(client, billed, monkeypatch):
    """An unwritable state dir must not quietly turn the budget off."""
    monkeypatch.setattr(_srv, "_STT_DAILY_SECONDS", 600.0)
    monkeypatch.setattr(_srv, "_STT_USAGE_PATH", "/proc/nonexistent/stt-usage.json")
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 200
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 429
    assert len(billed) == 1


def test_a_clip_longer_than_the_budget_leaves_is_refused(client, billed, monkeypatch):
    """The gate on what is spent bounds the NEXT clip at zero, not this one:
    with ten seconds of budget left, a twenty-second clip is still a clip that
    would overrun it."""
    monkeypatch.setattr(_srv, "_STT_DAILY_SECONDS", 610.0)
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 200
    monkeypatch.setattr(_srv, "_clip_seconds", lambda audio, mime: 20.0)
    r = client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO)
    assert r.status_code == 429
    assert len(billed) == 1, "a clip that would overrun the day must not be sent"


def test_a_clip_longer_than_the_console_can_record_is_refused(client, billed, monkeypatch):
    monkeypatch.setattr(_srv, "_clip_seconds", lambda audio, mime: 400.0)
    r = client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO)
    assert r.status_code == 413
    assert not billed


def test_an_unreadable_clip_still_goes_through_on_the_size_limit_alone(client, billed, monkeypatch):
    """ffprobe missing, or a container it cannot parse: fall back, do not fail."""
    monkeypatch.setattr(_srv, "_clip_seconds", lambda audio, mime: None)
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 200


def test_a_transcriber_that_reports_no_duration_does_not_crash_the_meter(client, monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda *a, **k: {"text": "네", "seconds": None})
    monkeypatch.setattr(_srv, "_clip_seconds", lambda audio, mime: 5.0)
    r = client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO)
    assert r.status_code == 200
    assert r.json()["spent_today"] == 0.0


def test_a_junk_usage_file_reads_as_an_unspent_day(client, billed, tmp_path, monkeypatch):
    bad = tmp_path / "stt-usage.json"
    bad.write_text('{"day": "2026-01-01", "seconds": ["not", "a", "number"]}')
    monkeypatch.setattr(_srv, "_STT_USAGE_PATH", str(bad))
    assert client.post("/api/stt?hints=0", content=b"x" * 99, headers=_AUDIO).status_code == 200


def test_a_commented_env_value_does_not_take_the_service_down(monkeypatch):
    """systemd keeps inline comments in EnvironmentFile values (see CLAUDE.md)."""
    monkeypatch.setenv("CTB_STT_DAILY_SECONDS", "1800  # 30분")
    assert _srv._stt_daily_seconds() == 1800.0
    monkeypatch.setenv("CTB_STT_DAILY_SECONDS", "not a number")
    assert _srv._stt_daily_seconds() == 1800.0
    monkeypatch.setenv("CTB_STT_DAILY_SECONDS", "600")
    assert _srv._stt_daily_seconds() == 600.0
