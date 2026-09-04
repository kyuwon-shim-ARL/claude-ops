"""What the user has actually said to sessions, turned into a glossary and an
evaluation set for speech to text, and the scoring that feeds back into it.

Three sources, all already on disk: the Claude Code transcripts under
``~/.claude/projects`` (every user prompt ever typed), the repositories under
``~/projects`` (names and branches), and the results of the lab itself (terms
the model missed). Nothing here is hand-written by the user except the
``# manual`` section of the glossary, which is kept as is.
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from . import stt

TRANSCRIPTS_ROOT = Path(os.path.expanduser("~/.claude/projects"))
PROJECTS_ROOT = Path(os.path.expanduser("~/projects"))
EVAL_DIR = Path(os.path.expanduser("~/.claude-ops/stt-eval"))
EVAL_SET_PATH = EVAL_DIR / "set.json"
RESULTS_PATH = EVAL_DIR / "results.jsonl"
GLOSSARY_MAX_AGE_S = 24 * 3600
GLOSSARY_AUTO_MAX = 300
PROMPT_MAX_CHARS = 400

_TAG_RE = re.compile(r"<(command-|bash-|local-command|system-reminder|task-notification)")
# Lines the harness writes in the user's voice, not the user.
_HARNESS_RE = re.compile(r"^(Background agent|\[Request interrupted|This session is being continued|Caveat:)")
_URL_RE = re.compile(r"https?://|www\.")
_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class Prompt:
    text: str
    project: str


def _text_of(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
            return None
        return " ".join(x.get("text", "") for x in content
                        if isinstance(x, dict) and x.get("type") == "text")
    return None


def iter_user_prompts(root: Path = TRANSCRIPTS_ROOT) -> Iterator[Prompt]:
    """Every prompt the user typed, across all projects. Tool results, slash
    commands, shell echoes and pasted walls are left out."""
    for proj_dir in sorted(Path(root).glob("*/")):
        project = re.sub(r"^-home-[^-]+-projects-", "", proj_dir.name)
        for f in sorted(proj_dir.glob("*.jsonl")):
            try:
                fh = open(f, encoding="utf-8", errors="ignore")
            except OSError:
                continue
            with fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("type") != "user":
                        continue
                    text = _text_of((row.get("message") or {}).get("content"))
                    if not text:
                        continue
                    text = text.strip()
                    if not text or _TAG_RE.search(text) or text.startswith("<") or _HARNESS_RE.match(text):
                        continue
                    if len(text) > PROMPT_MAX_CHARS:
                        continue
                    yield Prompt(text, project)


# --- glossary ----------------------------------------------------------------

def repo_names(root: Path = PROJECTS_ROOT) -> list[str]:
    try:
        return sorted(p.name for p in Path(root).iterdir() if (p / ".git").exists())
    except OSError:
        return []


def branch_names(root: Path = PROJECTS_ROOT, limit_repos: int = 60) -> list[str]:
    out: Counter[str] = Counter()
    for name in repo_names(root)[:limit_repos]:
        try:
            r = subprocess.run(
                ["git", "-C", str(Path(root) / name), "for-each-ref", "--format=%(refname:short)",
                 "refs/heads/"], capture_output=True, text=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        for b in r.stdout.split():
            if b not in ("main", "master", "HEAD"):
                out[b.rsplit("/", 1)[-1]] += 1
    return [b for b, _ in out.most_common()]


def glossary_terms(prompts: Iterable[Prompt], repo_names: list[str], branch_names: list[str],
                   min_count: int = 2, limit: int = GLOSSARY_AUTO_MAX) -> list[str]:
    """Repository and branch names first -- they are certain -- then the
    identifiers the user has typed at least ``min_count`` times, by frequency.
    Case is folded for counting; the most common spelling is kept."""
    counts: Counter[str] = Counter()
    spelling: dict[str, Counter] = {}
    for p in prompts:
        for t in stt.screen_terms([p.text]):
            k = t.lower()
            counts[k] += 1
            spelling.setdefault(k, Counter())[t] += 1
    seen: set[str] = set()
    out: list[str] = []
    for t in [*repo_names, *branch_names]:
        if t.lower() not in seen and len(t) >= 2:
            seen.add(t.lower())
            out.append(t)
    for k, n in counts.most_common():
        if n < min_count:
            break
        if k in seen:
            continue
        seen.add(k)
        out.append(spelling[k].most_common(1)[0][0])
        if len(out) >= limit:
            break
    return out


def read_glossary_sections(path: Path | str = stt.GLOSSARY_PATH) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"manual": [], "learned": [], "auto": []}
    current = "manual"
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return sections
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            name = s.lstrip("#").strip().split()[0].lower() if s.lstrip("#").strip() else ""
            if name in sections:
                current = name
            continue
        sections[current].append(s)
    return sections


def write_glossary(path: Path | str, auto_terms: list[str], learned: list[str]) -> int:
    """Rewrite the glossary: the manual section untouched, learned terms
    (misses from the lab) next, the automatic list last. Returns the size."""
    sections = read_glossary_sections(path)
    manual = sections["manual"]
    seen = {t.lower() for t in manual}
    learned_out = [t for t in dict.fromkeys(learned) if t.lower() not in seen and not seen.add(t.lower())]
    auto_out = [t for t in auto_terms if t.lower() not in seen and not seen.add(t.lower())]
    body = ["# manual  (yours; kept as is)", *manual, "",
            "# learned  (terms the lab heard wrong; promoted automatically)", *learned_out, "",
            "# auto  (repos, branches, identifiers you type often; regenerated)", *auto_out, ""]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("\n".join(body), encoding="utf-8")
    os.replace(tmp, p)
    return len(manual) + len(learned_out) + len(auto_out)


def glossary_is_stale(path: Path | str = stt.GLOSSARY_PATH, max_age_s: int = GLOSSARY_MAX_AGE_S) -> bool:
    try:
        return time.time() - Path(path).stat().st_mtime > max_age_s
    except OSError:
        return True


def rebuild_glossary(path: Path | str = stt.GLOSSARY_PATH, prompts: list[Prompt] | None = None) -> int:
    prompts = list(iter_user_prompts()) if prompts is None else prompts
    auto = glossary_terms(prompts, repo_names(), branch_names())
    learned = read_glossary_sections(path)["learned"]
    return write_glossary(path, auto, learned)


def promote_learned(missed: Iterable[str], path: Path | str = stt.GLOSSARY_PATH) -> int:
    """A term the model got wrong goes into the learned section at once."""
    sections = read_glossary_sections(path)
    learned = [*sections["learned"], *missed]
    return write_glossary(path, sections["auto"], learned)


# --- evaluation set -------------------------------------------------------------

def _speakable(text: str) -> bool:
    if "\n" in text or _URL_RE.search(text) or "`" in text or "/" in text or "@" in text:
        return False
    if not 12 <= len(text) <= 140:
        return False
    return not re.search(r"[{}<>\[\]|\\]", text)


def categorize(text: str, session_names: Iterable[str]) -> str:
    low = text.lower()
    for s in session_names:
        bare = re.sub(r"^claude[_-]", "", s).lower()
        if bare and (bare in low or s.lower() in low):
            return "session"
    ko = bool(_HANGUL_RE.search(text))
    latin = len(_LATIN_WORD_RE.findall(text))
    if ko and latin:
        return "mixed"
    if ko:
        return "ko"
    return "en" if latin else "ko"


_QUOTA = {"mixed": 0.45, "session": 0.2, "ko": 0.2, "en": 0.15}


def build_eval_set(prompts: Iterable[Prompt], session_names: list[str], n: int = 30,
                   seed: int = 0) -> list[dict]:
    """``n`` real prompts, short enough to read aloud, spread over the four
    categories, deterministic for a seed so the set is stable between runs."""
    buckets: dict[str, list[Prompt]] = {k: [] for k in _QUOTA}
    seen: set[str] = set()
    for p in prompts:
        if not _speakable(p.text):
            continue
        key = re.sub(r"\s+", " ", p.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        buckets[categorize(p.text, session_names)].append(p)
    rng = random.Random(seed)
    for b in buckets.values():
        rng.shuffle(b)
    picked: list[tuple[str, Prompt]] = []
    want = {k: round(n * q) for k, q in _QUOTA.items()}
    for k, b in buckets.items():
        picked.extend((k, p) for p in b[:want[k]])
        del b[:want[k]]
    # short categories give their slots to whoever has more
    for k in sorted(buckets, key=lambda k: -len(buckets[k])):
        while len(picked) < n and buckets[k]:
            picked.append((k, buckets[k].pop()))
    rng.shuffle(picked)
    items = []
    for i, (cat, p) in enumerate(picked[:n], 1):
        item = {"id": f"e{i:02d}", "text": p.text, "category": cat, "project": p.project}
        for s in session_names:
            if cat == "session" and re.sub(r"^claude[_-]", "", s).lower() in p.text.lower():
                item["session"] = s
                break
        items.append(item)
    return items


def load_or_build_eval_set(path: Path = EVAL_SET_PATH, session_names: list[str] | None = None,
                           rebuild: bool = False) -> dict:
    if not rebuild:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    prompts = list(iter_user_prompts())
    items = build_eval_set(prompts, session_names or [], n=30)
    data = {"items": items, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_prompts": len(prompts)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


# --- scoring ---------------------------------------------------------------------

def normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^\w\s가-힣]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    """Character error rate on normalized text -- the unit that is fair to
    Korean and English at once. 1.0 for an empty reference with any output."""
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0 if not h else 1.0
    return min(1.0, _levenshtein(r, h) / len(r))


def missed_terms(ref: str, hyp: str) -> list[str]:
    low = hyp.lower()
    return [t for t in dict.fromkeys(stt.screen_terms([ref])) if t.lower() not in low]


def append_result(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {**row, "ts": row.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def aggregate(path: Path, glossary_size: int) -> dict:
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass

    def bucket(key):
        out: dict[str, dict] = {}
        for r in rows:
            k = r.get(key) or "?"
            b = out.setdefault(k, {"n": 0, "_sum": 0.0})
            b["n"] += 1
            b["_sum"] += float(r.get("cer") or 0)
        return {k: {"n": b["n"], "cer": round(b["_sum"] / b["n"], 4)} for k, b in out.items()}

    missed: Counter[str] = Counter()
    for r in rows:
        missed.update(r.get("missed") or [])
    return {
        "n": len(rows),
        "by_engine": bucket("engine"),
        "by_category": bucket("category"),
        "top_missed": [[t, c] for t, c in missed.most_common(15)],
        "glossary_size": glossary_size,
        "recent": [{"id": r.get("id"), "engine": r.get("engine"), "cer": r.get("cer"), "ts": r.get("ts")}
                   for r in rows[-20:]][::-1],
    }
