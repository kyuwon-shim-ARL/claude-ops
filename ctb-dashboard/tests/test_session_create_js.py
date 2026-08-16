"""Behavioural tests for the new-session dialog's logic -- the real shipped JS.

Asserting that a string appears in the file proves nothing: the request body is
what reaches an endpoint that creates directories and git branches, so these
drive buildRequest() through node and check the payload it produces.

Skipped (not silently passed) when node is unavailable.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CREATE_JS = (
    Path(__file__).resolve().parents[1]
    / "src" / "ctb_dashboard" / "static" / "js" / "session-create.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available to run the real JS"
)

_HARNESS = """
global.window = {{ matchMedia: () => ({{matches:false}}) }};
global.document = {{
  addEventListener(){{}}, readyState:'complete', getElementById: () => null,
  createElement: () => ({{style:{{}}, setAttribute(){{}}, addEventListener(){{}},
                        appendChild(){{}}}}),
  body: {{appendChild(){{}}}},
}};
global.fetch = () => Promise.resolve();
require({path});
const api = window.ctbNewSession;
const call = JSON.parse({payload});
process.stdout.write(JSON.stringify(api[call.fn].apply(null, call.args)));
"""


def _call(fn, *args):
    script = _HARNESS.format(
        path=json.dumps(str(CREATE_JS)),
        payload=json.dumps(json.dumps({"fn": fn, "args": list(args)})),
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def build(**state):
    base = {"mode": "existing", "wtMode": "none", "gitInit": True}
    base.update(state)
    return _call("buildRequest", base)


# --- payload shape ----------------------------------------------------------


def test_existing_project_payload():
    r = build(project="alpha")
    assert r["payload"] == {"project": "alpha"}
    assert r["session"] == "claude_alpha"


def test_new_project_payload_carries_git_flag():
    r = build(mode="new", newProject="gamma", gitInit=False)
    assert r["payload"] == {"new_project": "gamma", "git_init": False}
    assert r["session"] == "claude_gamma"


def test_existing_worktree_payload():
    r = build(project="alpha", wtMode="existing", wtExisting="feat")
    assert r["payload"] == {"project": "alpha", "worktree": "feat"}
    assert r["session"] == "claude_alpha_wt_feat"


def test_new_worktree_payload():
    r = build(project="alpha", wtMode="new", wtNew="refactor")
    assert r["payload"] == {"project": "alpha", "worktree": "refactor"}
    assert r["session"] == "claude_alpha_wt_refactor"


def test_worktree_is_omitted_when_mode_is_none():
    r = build(project="alpha", wtMode="none", wtNew="ignored", wtExisting="ignored")
    assert "worktree" not in r["payload"]


def test_names_are_trimmed():
    r = build(mode="new", newProject="  gamma  ", wtMode="new", wtNew=" feat ")
    assert r["payload"]["new_project"] == "gamma"
    assert r["payload"]["worktree"] == "feat"


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "../escape", "a/b", "a b", ".hidden", "x" * 65])
def test_bad_project_names_produce_an_error_not_a_payload(name):
    r = build(project=name)
    assert "error" in r and "payload" not in r


@pytest.mark.parametrize("name", ["", "../x", "a/b", "a b", "-lead", "x" * 65])
def test_bad_worktree_names_produce_an_error_not_a_payload(name):
    r = build(project="alpha", wtMode="new", wtNew=name)
    assert "error" in r and "payload" not in r


def test_worktree_without_selection_is_refused():
    r = build(project="alpha", wtMode="existing", wtExisting="")
    assert "error" in r


def test_worktree_on_a_non_git_project_is_refused():
    r = build(project="beta", projectIsGit=False, wtMode="new", wtNew="feat")
    assert "error" in r and "git" in r["error"]


def test_worktree_on_a_new_project_without_git_is_refused():
    r = build(mode="new", newProject="gamma", gitInit=False, wtMode="new", wtNew="feat")
    assert "error" in r


def test_worktree_on_a_new_git_project_is_allowed():
    r = build(mode="new", newProject="gamma", gitInit=True, wtMode="new", wtNew="feat")
    assert r["payload"] == {"new_project": "gamma", "git_init": True, "worktree": "feat"}


def test_mode_selects_which_name_field_is_used():
    """A stale field from the other tab must not leak into the request."""
    r = build(mode="new", newProject="gamma", project="alpha")
    assert r["payload"] == {"new_project": "gamma", "git_init": True}
    r = build(mode="existing", project="alpha", newProject="gamma")
    assert r["payload"] == {"project": "alpha"}


# --- naming and paths mirror the server -------------------------------------


def test_session_name_convention():
    assert _call("sessionNameFor", "alpha", None) == "claude_alpha"
    assert _call("sessionNameFor", "alpha", "feat") == "claude_alpha_wt_feat"


def test_preview_path_convention():
    assert _call("previewPath", "/home/k/projects", "alpha", None) == "/home/k/projects/alpha"
    assert (_call("previewPath", "/home/k/projects/", "alpha", "feat")
            == "/home/k/projects/alpha/.claude/worktrees/feat")


def test_filter_is_case_insensitive_substring():
    projects = [{"name": "Alpha"}, {"name": "beta-alpha"}, {"name": "gamma"}]
    assert [p["name"] for p in _call("filterProjects", projects, "ALPH")] == ["Alpha", "beta-alpha"]
    assert len(_call("filterProjects", projects, "  ")) == 3


# --- the naming rules must not drift from the server ------------------------


def test_client_and_server_name_rules_agree():
    from ctb_dashboard import session_create

    js = CREATE_JS.read_text()
    assert session_create.PROJECT_NAME_RE.pattern.strip("^$") in js
    assert session_create.WORKTREE_NAME_RE.pattern.strip("^$") in js


# --- wiring: the dialog has to be reachable from the page -------------------


def test_dashboard_page_loads_the_dialog_and_shows_its_button():
    """Without both of these the feature exists only in the repo."""
    from fastapi.testclient import TestClient
    from ctb_dashboard import server

    html = TestClient(server.app).get("/").text
    assert '/static/js/session-create.js' in html
    assert 'id="btn-new-session"' in html
    # The dialog wires itself to that id; a rename on either side breaks it.
    assert "getElementById('btn-new-session')" in CREATE_JS.read_text()
