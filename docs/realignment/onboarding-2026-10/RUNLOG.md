# Onboarding 2026-10: run log

Real commands and results, newest last.

## Baseline (2026-10-30)

- worktree `.worktrees/onboarding-2026-10` at `1c454c32`, clean.
- `npm run check:agent`: audit_context_hygiene, audit_tool_contracts, audit_constitution pass; generate_agent_map --check fails (121 lines vs cap 120). Baseline, not caused by this work (F-09).

## Research & Requirements Phase (2026-10-30)
- Authored `docs/research/onboarding-and-getting-started-2026-10.md` with 12 required sections.
- Created `docs/realignment/onboarding-2026-10/` planning files (`00-PLAN.md`, `RESEARCH.md`, `FINDINGS.md`, `DECISION.md`, `CHANGES.md`, `RUNLOG.md`).
- Commit `e7f75ff7`: `docs(research): document onboarding patterns and failure analysis`.

## Route Readiness & Connection Service Phase (2026-10-30)
- Created `src/hutch/route_readiness.py`: pure mapping from 14 `ProviderError` kinds to canonical `provider.*` tokens, TTL calculation, capped `Retry-After`, and key redaction via `safe_detail()`.
- Created `src/hutch/providers/connection.py:probe_connection_typed()` with 1-token explicit test generation.
- Created standalone test fake in `tests/support/fake_provider.py`.
- Created `src/hutch/connections_service.py` under 400 lines (130 lines): key normalization, 0600 file storage, terms acknowledgment.
- Added tests in `tests/test_route_readiness.py` (24 tests), `tests/test_readiness_probe.py` (17 tests), and `tests/test_connections_service.py` (7 tests).
- Verified with `pytest`: 48 passed.

## Connection Routes & UI Phase (2026-10-30)
- Extended `OnboardingSetup` in `src/hutch/onboarding.py` and persistence functions in `src/hutch/onboarding_store.py`.
- Replaced interim `/#/connections` bridge in `onboarding_chooser_api.py` with real connection routes.
- Created `src/hutch/server/onboarding_readiness_api.py` and `_onboarding_readiness.html`.
- Created `src/hutch/server/onboarding_hosted_key_api.py` and `onboarding_hosted_key.html`.
- Created `src/hutch/server/onboarding_local_service_api.py` and `onboarding_local_service.html`.
- Created `src/hutch/server/onboarding_opencode_api.py` and `onboarding_opencode.html`.

## Assistant Creation & First Request Phase (2026-10-30)
- Created `src/hutch/server/onboarding_assistant_api.py` and `onboarding_assistant.html` (Step 4).
- Created `src/hutch/server/onboarding_first_request_api.py` and `onboarding_first_request.html` (Step 5).
- Created `src/hutch/server/getting_started.py` (contextual 5-point checklist derived from database facts).
- Added 15 integration tests in `tests/test_onboarding_assistant.py`, `tests/test_onboarding_first_request.py`, `tests/test_getting_started.py`.
- All 15 passed.

## Desktop Startup & Visual Validation Phase (2026-10-30)
- Enhanced `desktop/web/index.html` and `desktop/web/startup.css` with structured diagnostic presentation and troubleshooting.
- Authored `docs/getting-started.md` and fixed dead `#quickstart` anchor in `README.md`.
- Authored `scripts/capture_onboarding_visuals.py` and captured 80 visual validation artifacts across 8 viewports (`1440x1000`, `1280x800`, `1024x768`, `900x1024`, `768x1024`, `390x844`, `375x812`, `320x740`), 200% zoom, text spacing, reduced motion, and keyboard focus.
- Reviewed captured PNGs and authored `docs/realignment/onboarding-2026-10/VISUAL-VALIDATION.md`, `CODE-REVIEW.md`, and `HANDOFF.md`.
- Ran full test suite: 169 passed in 105.72s.
- Ran emoji audit: clean (scanned 2039 files, 10 waiver(s)).
- Ran context hygiene audit: passed (861 source files; 117 frozen over-cap files).
- Ran tool contracts audit: passed (43 registered tools; canonical schemas certifiable; specs match).
- Ran constitution audit: passed (3 roles, 14 rules; every rule maps to existing enforcement).
