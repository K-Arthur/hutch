# Onboarding 2026-10: implementation findings

Observed in this checkout (commit 1c454c32) before any change. Line numbers are
from that commit.

| ID | Finding | Evidence | Severity | Requirement |
|---|---|---|---|---|
| F-01 | The shipped journey ends at a temporary bridge to `/#/connections`; no connection, assistant or first-run step exists | `onboarding_chooser_api.py:46-47`, `onboarding_ai_service.html:31-32` | P0 | R-04 |
| F-02 | `check_connection` reports `verified=ok` on a model-list success; a model list can succeed while generation fails | `providers/connection.py:50-69` | P0 | R-01 |
| F-03 | No typed per-route readiness exists; `route_readiness.py` and the typed probe are planned only | `docs/onboarding/slices/slice-03.md` | P0 | R-01, R-02 |
| F-04 | Setup record holds request and route only; no connection, assistant or first-request milestone | `onboarding.py` model | P0 | R-07, R-08, R-10 |
| F-05 | Desktop startup page is one static message; failures are written into one status line by `eval` | `desktop/web/index.html`, `main.rs:361` | P1 | R-11 |
| F-06 | Website `#get` links `github.com/K-Arthur/hutch#quickstart`; README has no Quickstart heading | `website/index.html:796,845`; README headings | P1 | R-12 |
| F-07 | Website copy says "Desktop apps are next" / "still in progress" with no date | `website/index.html:792-793` | P2 | R-12 |
| F-08 | No Getting Started guide exists in `docs/` | `ls docs` | P1 | R-12, R-13 |
| F-09 | `npm run check:agent` fails at baseline: agent map renders 121 lines against a 120 cap (new `src/hutch/personal/` row on main plus a stale map). Not caused by this program | `generate_agent_map.py --check` | Info | none; recorded in RUNLOG |
| F-10 | Request-step copy says the next choice "uses the existing Apps & AI setup", which becomes untrue once real steps exist | `onboarding.html:66` | P2 | R-04 |
