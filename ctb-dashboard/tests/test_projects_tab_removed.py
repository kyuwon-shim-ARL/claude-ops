"""The Projects tab is gone.

It was never used, and it pulled a whole second application into this one:
a router, a static mount, and a background scan loop, all imported from
/home/kyuwon/projects/project-status at startup.

What stays is the PI review gate, which happens to read from the same package
-- scanner.PROJECTS_ROOT and scanner.find_rpt_artifact. Removing the tab must
not take the review link with it, so that is pinned here too.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from ctb_dashboard import server
from ctb_dashboard.server import app

INDEX = (Path(__file__).resolve().parents[1]
         / "src" / "ctb_dashboard" / "templates" / "index.html")


def test_the_projects_route_is_gone():
    assert TestClient(app).get("/projects").status_code == 404


def test_the_projects_static_mount_is_gone():
    assert TestClient(app).get("/pstatus-static/app.js").status_code == 404


def test_no_route_is_left_under_projects():
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if p.startswith("/projects")], paths


def test_the_nav_link_is_gone():
    assert 'href="/projects"' not in INDEX.read_text()


def test_the_scan_loop_is_no_longer_started():
    """A background task for a feature nobody opens is pure cost."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "ctb_dashboard" / "server.py").read_text()
    assert "_pstatus_scan_loop" not in src
    assert "projects_router" not in src


# --- what must survive -------------------------------------------------------

def test_the_review_gate_still_has_its_route():
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/review" in paths


def test_the_review_gate_still_knows_where_projects_live():
    """It reads plans and reports from disk; losing this root breaks it."""
    assert server._CTB_PROJECTS_ROOT
    assert callable(server._find_rpt_artifact)
