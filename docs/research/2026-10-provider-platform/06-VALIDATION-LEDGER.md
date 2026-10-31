# 06 - Validation ledger

Exact commands and observed results. Status: in progress. Every hosted route in this package is not live-verified. Hosted live verification is `BLOCKED` for
this delivery because no provider credentials exist in the execution environment; nothing below should
be read as proof that a hosted provider works live.

## Environment probes

| Probe | Command | Observed | Verdict |
|---|---|---|---|
| Provider credential variables | names-only scan of the process environment | 0 provider-like variables | BLOCKED for hosted live calls |
| Local inference services | HTTP probe of 127.0.0.1:11434, 1234, 8000, 30000, 8080 | all unreachable (000) | no local model to exercise |
| Installed coding CLIs | `command -v` / `--version` | claude 2.1.314; codex and opencode installed (opencode version probe blocked by read-only log path); gemini/qwen/pi absent | CLI runtimes not live-exercised |
| Artifact | `artifacts/env-probe.txt` | recorded | evidence |

## Baseline automated tests (HEAD 1c454c32, clean worktree)

| Suite selection | Command | Result |
|---|---|---|
| per-file named suites in clean worktree | pytest -q per file with PYTHONPATH=<worktree>/src, 120 s timeout | 230 passed, 1 skipped; slowest test_model_switcher 75.9 s |
| provider catalogue | pytest -q tests/test_provider_catalog.py | 26 passed |
| accounts + catalogue + connections | pytest -q tests/test_provider_accounts.py tests/test_provider_catalog.py tests/test_connections.py | 80 passed in 32.77 s |
| capability evidence | pytest -q tests/test_provider_capabilities.py | 6 passed |
| readiness | pytest -q tests/test_provider_readiness.py | 6 passed |
| runtime registry | pytest -q tests/test_runtime_registry.py | 4 passed |
| local discovery | pytest -q tests/test_provider_discovery.py | 6 passed |
| server surfaces | pytest -q tests/test_provider_surfaces.py | 8 passed |

An earlier run on the shared main checkout (which included another session's in-progress edits) passed
230 tests with 1 skipped in 165 s; it is not a clean baseline and is recorded only as context. The full
focused batch command and its final count are in the delivery report and the completion-round evidence.

## Live provider validation

| Provider | Auth | Catalogue | Inference | Streaming | Tools | Capability | Verdict |
|---|---|---|---|---|---|---|---|
| all hosted providers | not available | not available | not available | not available | not available | not available | BLOCKED |

## Visual validation (real app, real browser, 2026-10-30)

The app was started from the branch worktree against an isolated state directory and captured with
Playwright Chromium. The only seeded state was real, unauthenticated accounts created through the normal
connection store (two OpenAI accounts, one Anthropic account, one OpenRouter account) and two saved model
routes; no key was present, so every account truthfully renders needs-authentication. The website was
served over HTTP from the worktree, not opened as file://, to avoid font CORS noise.

| Surface | Viewports | Result |
|---|---|---|
| /providers, /models, /legacy/connections | 1440x960, 1280x720, 900x1024, 390x844, 320x740 | pass; HTTP 200; zero console errors/warnings; zero horizontal overflow; full-page and review captures saved |
| website index #providers (collapsed and expanded) | same five | pass; zero console errors; zero horizontal overflow |
| 200 percent text reflow (/providers and website #providers) | 1280x720 | pass; no horizontal overflow after font-size 200 percent |

The capture run was repeated after rebasing onto current main (final branch tree) with the same result: zero console errors, zero horizontal overflow, all five viewports. Artifacts: artifacts/visual/ (full-page and review PNGs, capture-results.json, server logs). Inspected at
each viewport: provider accounts and readiness, provider catalogue and filters, local-inference probe
results, execution-runtime boundaries, model-route readiness panel, connections page with the catalogue
link, and the marketing provider section collapsed and expanded.

Issues found by inspection and fixed before the accepted run:
1. Website status cards initially used grid/card classes that did not behave at 390 px when expanded;
   replaced with the site's own choice-grid/choice-card pattern.
2. The execution-runtime table clipped its boundary column at phone widths; replaced with a wrapping
   plain list carrying the same information.
3. An installed-CLI version probe printed an error path as the version and caused horizontal overflow;
   CLI version output is now sanitized to a short token or blank.
4. The Providers page now highlights Apps & AI in the sidebar instead of Models.

Remaining gaps: no physical device, screen-reader session or native browser zoom gesture; contrast was
checked by eye on rendered surfaces plus the existing token audit, not a full automated audit; a real
authenticated provider state cannot be shown because no credential exists.

## Verified during delivery

- Clean-worktree baseline recorded above; focused tests for every new module and the named existing
  suites recorded in the completion round.
- Real app states captured at five viewports and inspected: empty catalogue/account states,
  needs-authentication accounts, capability-unverified route readiness, local-service absence, runtime
  boundaries, and the marketing provider section collapsed and expanded.
- Security-relevant behaviour exercised by tests: ambient-key scoping, no credential value on provider
  APIs or pages, CSRF on account actions, loopback-only discovery with redirects refused, and
  documentation claims reviewed.

## Gaps that remain

- No hosted provider was live-verified; every hosted route remains implemented-unverified.
- No local inference server was available, so discovery is exercised with injected transports and real
  failed probes, not a running model.
- Deferred: Gemini/Responses protocol generalisation, media/speech adapters with a verified job contract,
  provider-native search attribution, and CLI runtime executors. These are documented, not stubbed.
- Screen-reader, physical-device and native-zoom checks remain manual gaps.
- The main checkout's concurrent work prevented a same-tree merge check until completion; the final merge
  and main verification are recorded in the delivery report.
