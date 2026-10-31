# Onboarding 2026-10: changes

Chronological record. Each entry: commit, what changed, tests run.

## 2026-10-30 - Initial Research and Planning
- Authored `docs/research/onboarding-and-getting-started-2026-10.md` with 12 required sections.
- Created `docs/realignment/onboarding-2026-10/` planning files (`00-PLAN.md`, `RESEARCH.md`, `FINDINGS.md`, `DECISION.md`, `RUNLOG.md`).
- Commit `e7f75ff7`: `docs(research): document onboarding patterns and failure analysis`.

## 2026-10-30 - Core Readiness, Typed Probing, and Connection Service
- Created pure module `src/hutch/route_readiness.py` mapping all 14 `ProviderError` kinds to canonical `provider.*` tokens.
- Extended `src/hutch/providers/connection.py` with `probe_connection_typed()` and 1-token bounded test generation.
- Created standalone scripted test fake in `tests/support/fake_provider.py`.
- Created `src/hutch/connections_service.py` under 400 lines: key normalization, 0600 file persistence, terms tracking.
- Added 41 tests across `tests/test_route_readiness.py`, `tests/test_readiness_probe.py`, and `tests/test_connections_service.py`.

## 2026-10-30 - Real Connection Steps & Shared Readiness Poller
- Replaced interim `/#/connections` bridge in `src/hutch/server/onboarding_chooser_api.py` with real connection routes.
- Created `src/hutch/server/onboarding_readiness_api.py` and `_onboarding_readiness.html`.
- Created `src/hutch/server/onboarding_hosted_key_api.py` and `onboarding_hosted_key.html`.
- Created `src/hutch/server/onboarding_local_service_api.py` and `onboarding_local_service.html`.
- Created `src/hutch/server/onboarding_opencode_api.py` and `onboarding_opencode.html`.

## 2026-10-30 - Assistant Creation & First Request Execution
- Created `src/hutch/server/onboarding_assistant_api.py` and `onboarding_assistant.html` (Step 4).
- Created `src/hutch/server/onboarding_first_request_api.py` and `onboarding_first_request.html` (Step 5).
- Created `src/hutch/server/getting_started.py` (facts-based checklist).
- Added 15 integration tests in `tests/test_onboarding_assistant.py`, `tests/test_onboarding_first_request.py`, `tests/test_getting_started.py`.

## 2026-10-30 - Desktop Startup Diagnostics, Documentation & Visual Validation
- Enhanced `desktop/web/index.html` and `desktop/web/startup.css` with structured diagnostic presentation and troubleshooting.
- Authored `docs/getting-started.md` and fixed dead `#quickstart` anchor in `README.md`.
- Captured 80 visual validation artifacts across 8 viewports, 200% zoom, text spacing, reduced motion, and keyboard navigation.
- Authored `docs/realignment/onboarding-2026-10/VISUAL-VALIDATION.md`, `CODE-REVIEW.md`, and `HANDOFF.md`.
