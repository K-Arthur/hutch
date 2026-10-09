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
  tests. Product runtime selection, model validation, and model-picker state never inspect
  `HUTCH_TESTING`; the test harness injects its scenario directly into the in-process Engine and
  supervised test workers.
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

The packaged-runtime boundary has regressions with `HUTCH_TESTING=1` set: mock routes remain
unavailable, the model picker marks legacy mock records for repair, and runtime selection never
imports `tests.support`. A test-only `sitecustomize` injects the scenario into real supervised worker
processes; one worker-recovery test that starts an isolated supervisor opts in explicitly. The
focused runtime, Engine, and worker suites passed **29 tests** with unhandled pytest-thread warnings
and `SyntaxWarning`s treated as failures. These are local fixture checks, not live-provider tests.

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

After the website redesign was merged, the actual app proof images were regenerated from the live local UI on 2026-10-08
using the existing temporary empty state directory. `artifacts/no-mock-setup/results.json` records the exact application
source hashes, Chromium/Playwright versions, empty API checks and image hashes. The desktop (1440×1000), tablet (768×1024)
and phone (390×844) captures were opened and visually inspected; each had zero page errors and no horizontal overflow. The
desktop and phone captures replace `website/assets/captures/setup-desktop.webp` and `setup-phone.webp`. The refreshed marketing
viewport/full-page captures, including those embedded app images, are under `artifacts/marketing-top/`.

Historical mock-based benchmark and lifecycle artifacts remain in the realignment evidence tree
as records of earlier test methods. They are not product features and are no longer copied to the
marketing site. Live Ollama, hosted providers, Pi/OpenCode execution, remote phone control, and
physical-device checks remain separate unverified gates.

## Source-tree test-flag and legacy picker check (2026-10-09)

Product runtime selection, model-choice state and override validation no longer read
`HUTCH_TESTING`. Pytest injects its deterministic scenario through a test-only fixture, including
the isolated cancellation and supervised-worker scripts; the flag cannot activate a product
runtime, make `mock/demo` selectable or route work into the scenario. Legacy rows remain visible
for repair and are labeled as setup-required without claiming that a mock route sends data to a
hosted service.

The regression was first reproduced in a rendered Chromium model picker: the legacy route was
disabled but incorrectly carried the “leaves this machine” label. After the correction, the
focused runtime, model-choice, cancellation-process and browser regression group passed **37
tests** with thread and syntax warnings treated as errors. The inspected 1280×800 Chromium capture
is `artifacts/no-mock-setup/legacy-mock-picker.png`; the disabled row says “needs setup,” gives the
real-route repair, and does not claim hosted routing. Chromium **153.0.8010.12** / Playwright
**1.63.0**. This browser uses the deterministic test harness only to keep the rest of the local UI
available; no model was called.

The final complete offline run, after the hosted-label correction and the explicit browser navigation
used by the existing schedule-settings test, passed **1,449 tests, 2 skipped in 518.16 seconds**.
The wheel was rebuilt and imported in an isolated Python process with `HUTCH_TESTING=1`; it contains
no `tests/` package and returns the expected actionable `RuntimeUnavailable` for `mock/demo`. These
checks do not claim live provider or model verification.
