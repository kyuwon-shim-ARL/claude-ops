"""The glossary and the evaluation set are built from what the user actually
said to sessions, and the scoring feeds misses back into the glossary."""

import json

from ctb_dashboard import stt_corpus as sc


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def test_iter_prompts_keeps_only_real_user_text(tmp_path):
    proj = tmp_path / "-home-kyuwon-projects-foo"
    proj.mkdir()
    _jsonl(proj / "s.jsonl", [
        _user("uni-mol-QSAR 에서 pytest 돌려줘"),
        {"type": "assistant", "message": {"content": "ok"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        _user("<command-name>/model</command-name>"),
        _user("<bash-input>ls</bash-input>"),
        _user("x" * 500),
        _user('Background agent "Research task" was stopped by the user.'),
        {"type": "user", "message": {"content": [{"type": "text", "text": "리스트 형태 메시지"}]}},
    ])
    got = list(sc.iter_user_prompts(tmp_path))
    assert [p.text for p in got] == ["uni-mol-QSAR 에서 pytest 돌려줘", "리스트 형태 메시지"]
    assert got[0].project == "foo"


def test_glossary_ranks_repeated_identifiers_and_includes_repo_names():
    prompts = [sc.Prompt("pytest 돌려줘", "a"), sc.Prompt("pytest 랑 ruff", "a"),
               sc.Prompt("scaffold_split 확인", "b")]
    terms = sc.glossary_terms(prompts, repo_names=["claude-ops", "uni-mol-QSAR"],
                              branch_names=["scan-scope"], min_count=2)
    assert terms[:2] == ["claude-ops", "uni-mol-QSAR"] or set(terms[:2]) == {"claude-ops", "uni-mol-QSAR"}
    assert "scan-scope" in terms and "pytest" in terms
    assert "scaffold_split" not in terms  # seen once, below min_count


def test_glossary_file_keeps_the_manual_section(tmp_path):
    path = tmp_path / "g.txt"
    path.write_text("# manual\nUni-Mol\n\n# learned\nold-term\n\n# auto\nstale\n")
    sc.write_glossary(path, auto_terms=["pytest"], learned=["old-term", "pytest"])
    text = path.read_text()
    assert "Uni-Mol" in text and "old-term" in text and "pytest" in text
    assert "stale" not in text
    assert sc.read_glossary_sections(path)["manual"] == ["Uni-Mol"]
    # what stt.read_glossary sees is the flat list, comments dropped, no dups
    from ctb_dashboard import stt
    flat = stt.read_glossary(str(path))
    assert flat.count("pytest") == 1 and "# auto" not in flat


def test_eval_set_is_stratified_and_deduplicated():
    prompts = []
    for i in range(40):
        prompts.append(sc.Prompt(f"pytest 돌리고 {i}번 파일 커밋해줘", "a"))
        prompts.append(sc.Prompt(f"이 문장은 한국어만 있습니다 {i}", "a"))
        prompts.append(sc.Prompt(f"run the tests and then push branch {i}", "a"))
        prompts.append(sc.Prompt(f"claude_ops 세션 {i}번 열어줘", "a"))
    prompts.append(sc.Prompt("pytest 돌리고 1번 파일 커밋해줘", "a"))  # duplicate
    items = sc.build_eval_set(prompts, session_names=["claude_ops"], n=30, seed=1)
    assert len(items) == 30
    cats = {c: sum(1 for it in items if it["category"] == c) for c in ("mixed", "ko", "en", "session")}
    assert all(v >= 3 for v in cats.values()), cats
    assert len({it["text"] for it in items}) == 30
    assert all(it["id"].startswith("e") for it in items)


def test_eval_set_skips_prompts_that_cannot_be_read_aloud():
    prompts = [sc.Prompt("https://example.com/x 열어봐", "a"),
               sc.Prompt("```python\nprint(1)\n```", "a"),
               sc.Prompt("짧", "a"),
               sc.Prompt("kyuwon.shim@ip-korea.org 로 보내줘", "a"),
               sc.Prompt("pytest 돌려줘 지금", "a")]
    items = sc.build_eval_set(prompts, session_names=[], n=10, seed=0)
    assert [it["text"] for it in items] == ["pytest 돌려줘 지금"]


def test_cer_is_zero_for_a_match_and_ignores_case_and_punctuation():
    assert sc.cer("Claude Ops 세션에서 pytest!", "claude ops 세션에서 pytest") == 0.0


def test_cer_counts_edits_over_reference_length():
    assert abs(sc.cer("abcd", "abxd") - 0.25) < 1e-9
    assert sc.cer("", "x") == 1.0


def test_missed_terms_are_identifiers_absent_from_the_hypothesis():
    assert sc.missed_terms("uni-mol-QSAR 에서 pytest 돌려줘", "유니몰 에서 pytest 돌려줘") == ["uni-mol-QSAR"]
    assert sc.missed_terms("pytest 돌려줘", "PyTest 돌려줘") == []


def test_results_aggregate_by_engine_and_category(tmp_path):
    path = tmp_path / "results.jsonl"
    for eng, cer, cat in (("gpt", 0.1, "mixed"), ("gpt", 0.3, "ko"), ("ios", 0.5, "mixed")):
        sc.append_result(path, {"id": "e01", "engine": eng, "cer": cer, "category": cat,
                                "missed": ["pytest"] if eng == "ios" else [], "hints": True})
    stats = sc.aggregate(path, glossary_size=7)
    assert stats["n"] == 3
    assert abs(stats["by_engine"]["gpt"]["cer"] - 0.2) < 1e-9
    assert stats["by_engine"]["ios"]["n"] == 1
    assert stats["by_category"]["mixed"]["n"] == 2
    assert stats["top_missed"] == [["pytest", 1]]
    assert stats["glossary_size"] == 7 and len(stats["recent"]) == 3
