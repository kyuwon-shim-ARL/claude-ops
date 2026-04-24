
## [DONE 2026-04-23] state_detector.py ↔ session_state.py 상태 열거 통일

Resolved by P1 S0 of CTB Dashboard UX Overhaul plan
(`.omc/plans/20260423-ctb-dashboard-ux-overhaul.md`).

- `claude_ctb/utils/session_state.py` now canonical. Added `STUCK_AFTER_AGENT`
  to the enum + STATE_PRIORITY map.
- `ctb-dashboard/src/ctb_dashboard/state_detector.py` imports `SessionState`
  from canonical with graceful sys.path discovery + local fallback (for
  isolated pip-install scenarios).
- Added `ctb-dashboard/tests/test_session_state_parity.py` — asserts
  `state_detector.SessionState IS claude_ctb.utils.session_state.SessionState`
  whenever both are importable, blocking silent divergence regression.

---

## [TODO] P2 — 5-level hierarchy drilldown (L1-L5 navigation)

Tracked in plan §5.

## [TODO] P2 — Living Milestone UX

Builds on `{project}/.omc/milestones.yaml` created in P1.
Tracked in plan §5.

## [TODO] P2 — Foundation derived view

Tracked in plan §5.

## [TODO] P2 — Migrate index.html session grid to Alpine templates

Complete the strangler migration started in P1.

## [TODO] P3 — Unified rpt viewer + inline feedback loop

Reuse existing `projects_router._structure_feedback` Haiku pipeline.
Tracked in plan §6.
