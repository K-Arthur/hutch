# Real routes and truthful first-run state

Date: 2026-10-08. This slice removes the user-facing simulated model path; it does not certify
live model/provider behavior or complete the remaining S5–S9 product work.

## Product behavior

- `hutch init` creates the database and state directory without creating bots or activity.
- A bot requires a configured local or hosted model route. Templates carry task instructions and
  permissions, but no model, run, transcript, or result.
- New CLI/API/server-rendered creation paths reject a missing route. Legacy `mock/*` records stay
  readable for audit and migration, but the supervisor marks them `model_unavailable` before a
  worker or action starts. `hutch doctor` names the affected bot and repair.
- The public `hutch demo seed` command and production `MockRuntime` are removed. The deterministic
  `TestScenarioRuntime` lives under `tests/support/`; it is included only in the source test suite,
  not in built wheels. Its synthetic usage/output exists solely to exercise policy and persistence
  tests. The explicit `HUTCH_TESTING` test harness flag is not enabled by normal app commands.
- The website no longer ships mock-run screenshots or a scripted approval button. Its product
  image is a capture of the actual empty first-run UI; copy says when a model route and provider
  have not been verified live.

## Verification

On 2026-10-08 the full offline suite passed **1,243 tests in 258.74 seconds** with unhandled
pytest background-thread exceptions and Python `SyntaxWarning`s treated as failures. The final
anonymous marketing run passed **11 browser checks in 11.26 seconds** after the hero badge was
changed to describe local control rather than imply a resident bot. `uv build --wheel` succeeded;
inspection confirmed that the built wheel contains neither `tests/` nor the removed production
mock runtime/demo seeder. These are local fixture and packaging checks, not live-provider tests.

The focused test run covers CLI, API, model switching, offline routing, templates, engine/runtime,
and the anonymous website. It checks that empty/mocked production route creation fails, legacy
runs fail before a tool call, route changes from Local to Hybrid work in one update, the removed
`hutch demo seed` command is unavailable, and site copy/assets contain no simulated product flow.

The capture utility is `capture_first_run.py`. It refuses to take a screenshot unless the real
application reports empty bot, run, approval, conversation, and configured-connection lists. The
2026-10-08 capture used an isolated temporary state directory and an environment with no inherited
variables other than `PATH`, `LANG`, and `HUTCH_STATE_DIR`; no provider calls or external effects
were possible. Playwright 1.63.0 with Chromium 153.0.8010.12 captured desktop 1440×1000, tablet
768×1024, and phone 390×844. There was no horizontal overflow or page error. Original PNGs and
hashes are under `artifacts/no-mock-setup/`; compressed desktop/phone copies are the only app
screenshots left in the website assets.

The anonymous website was visually inspected and exercised at desktop, tablet, and phone widths.
Its 11 Playwright checks verify internal destinations, loadable local assets, reduced-motion
behavior, mobile menu focus restoration, no horizontal overflow, and the absence of mock copy or
simulated approval controls. The marketing capture test output is in
`artifacts/no-mock-setup/site/`.

Historical mock-based benchmark and lifecycle artifacts remain in the realignment evidence tree
as records of earlier test methods. They are not product features and are no longer copied to the
marketing site. Live Ollama, hosted providers, Pi/OpenCode execution, remote phone control, and
physical-device checks remain separate unverified gates.
