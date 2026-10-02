"""The package must be installable and importable on a machine that is not
this one: no hard-coded /home/kyuwon paths, and the wheel must actually
contain its static assets and templates (not just the top-level files).

These tests build a real wheel and import the server in a clean subprocess
rather than asserting against source-tree structure, because the bug this
guards against is specifically a packaging-metadata mismatch that unit tests
against the source tree can't see.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _build_wheel(tmp_path: Path) -> Path:
    """Build the wheel into tmp_path, skipping the test if no builder exists."""
    builder = shutil.which("uv")
    if builder:
        cmd = ["uv", "build", "--wheel", "--out-dir", str(tmp_path)]
    elif shutil.which("python") or shutil.which("python3"):
        python = shutil.which("python3") or shutil.which("python")
        # `build` may not be installed; skip cleanly rather than fail if so.
        check = subprocess.run(
            [python, "-c", "import build"], cwd=PACKAGE_ROOT, capture_output=True
        )
        if check.returncode != 0:
            pytest.skip("neither uv nor the `build` package is available")
        cmd = [python, "-m", "build", "--wheel", "--outdir", str(tmp_path)]
    else:
        pytest.skip("no wheel builder (uv or python -m build) available")

    result = subprocess.run(cmd, cwd=PACKAGE_ROOT, capture_output=True, text=True)
    # A builder that exists and fails is the bug this test is for -- a broken
    # pyproject -- so it fails rather than skips (a skip turns CI green).
    assert result.returncode == 0, f"wheel build failed: {result.stderr[-2000:]}"

    wheels = sorted(tmp_path.glob("*.whl"))
    assert wheels, f"build reported success but produced no wheel: {result.stdout}"
    return wheels[-1]


def test_wheel_contains_static_and_template_assets(tmp_path):
    wheel_path = _build_wheel(tmp_path)
    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()

    assert "ctb_dashboard/static/js/session-control.js" in names
    # Any existing template -- just needs to prove templates/ shipped at all.
    assert any(n.startswith("ctb_dashboard/templates/") and n.endswith((".html", ".j2")) for n in names), names
    assert any(n.startswith("ctb_dashboard/static/vendor/") for n in names), names

    # Runtime .omc/ state (oh-my-claudecode session scratch dirs) must never
    # ship -- it's gitignored, machine-local, and irrelevant to the package.
    assert not any(".omc/" in n for n in names), [n for n in names if ".omc/" in n]


def test_server_imports_without_project_status(tmp_path):
    """server.py must not crash on import when the optional sibling
    project-status package isn't present -- it should degrade, not ImportError.
    """
    import os

    env = dict(os.environ)
    env["CTB_PSTATUS_DIR"] = str(tmp_path / "does-not-exist")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import ctb_dashboard.server as s; assert s.app is not None; print('OK')",
        ],
        cwd=PACKAGE_ROOT / "src",
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
