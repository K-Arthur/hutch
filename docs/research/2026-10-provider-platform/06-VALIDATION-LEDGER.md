# 06 - Validation ledger

Exact commands and observed results. Status: complete for this delivery plus live verification. On 2026-10-30 the
owner authorized live testing through the installed OpenCode CLI account (including its DeepSeek key). Two
owner-authorized routes were exercised for real: the direct DeepSeek connection through Hutch's built-in
runtime, and the managed OpenCode runtime with a DeepSeek model. Both succeeded for text generation. Tool
calling, streaming, image input, other modalities and every other provider were not live-exercised.
OpenCode Go's stored key reported expired and the run failed explicitly with no spend.

## Environment probes

| Probe | Command | Observed | Verdict |
|---|---|---|---|
| Provider credential variables | names-only scan of the process environment | 0 provider-like variables in the process environment | Owner-authorized live testing used the installed OpenCode account in memory (see live section); no direct provider variable was required |
| Local inference services | HTTP probe of 127.0.0.1:11434, 1234, 8000, 30000, 8080 | all unreachable (000) | no local model to exercise |
| Installed coding CLIs | command -v / --version | claude 2.1.314; codex installed; OpenCode 2.2.0 installed and used live; gemini/qwen/pi absent | OpenCode CLI and the Hutch-managed OpenCode runtime were live-exercised; Claude Code/Codex/Gemini CLIs were not |
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

## Live provider validation (2026-10-30)

Owner authorization: the installed OpenCode CLI account may be used for testing, including its DeepSeek key.
Credentials were read only in memory for the duration of a test; no secret was written to the repository or
to a committed artifact, and the isolated test state directories were deleted after each run.

| Route | Auth source | Catalogue | Inference | Streaming | Tools | Result | Artifact |
|---|---|---|---|---|---|---|---|
| DeepSeek direct connection, built-in runtime, deepseek-flash | owner OpenCode account, in-memory transfer to an isolated Hutch connection | authenticated; 2 models (deepseek-flash, deepseek-v4-pro) | one-step run succeeded; reply HUTCH_BUILTIN_OK; 612 prompt / 9 completion tokens | not tested live | not tested live (tools disabled for the run) | PASS (text only) | artifacts/live-verification/deepseek-builtin-runtime-live.json |
| Managed OpenCode 2.2.0 runtime, opencode/deepseek/deepseek-flash | owner DeepSeek key connected to Hutch's private OpenCode profile | private profile exposed DeepSeek models | one-step managed run succeeded; reply HUTCH_HUTCH_OK; 4452 prompt / 8 completion tokens; provider-reported cost $0.0006726 | not tested live | not tested live (empty tool list) | PASS (text only) | artifacts/live-verification/opencode-managed-runtime-deepseek-live.json |
| OpenCode CLI 2.2.0, deepseek/deepseek-flash | installed OpenCode account | model id accepted | real response HUTCH_LIVE_OK_2026 | n/a | n/a | PASS (external tool reference) | artifacts/live-verification/opencode-cli-deepseek.json |
| OpenCode Go stored API key, managed runtime | local OpenCode auth.json API login | 30 models exposed after transfer | provider rejected the key as expired; run failed explicitly | not reached | not reached | FAIL (honest provider error, no spend) | artifacts/live-verification/opencode-managed-runtime-live.json |

Cost note: the direct DeepSeek run recorded cost_usd 0.0 because no reviewed local price row existed for the
live model. That is unpriced, not a free-service claim; the managed OpenCode run reported $0.0006726 from the
provider. Tool calling, streaming, vision, audio, video, music and search remain not live-verified anywhere.
Blocked or unavailable: every other provider has no usable credential in this environment; the OpenCode Go
stored key is expired; no local inference server is running.

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

- Only the DeepSeek text routes above were live-verified. Every other hosted route and every other capability
  (tools, streaming, images, audio, video, music, provider-native search) remains implemented-unverified or
  documented. No local inference server was available.
- No local inference server was available, so discovery is exercised with injected transports and real
  failed probes, not a running model.
- Deferred: Gemini/Responses protocol generalisation, media/speech adapters with a verified job contract,
  provider-native search attribution, and CLI runtime executors. These are documented, not stubbed.
- Screen-reader, physical-device and native-zoom checks remain manual gaps.
- The main checkout's concurrent work prevented a same-tree merge check until completion; the final merge
  and main verification are recorded in the delivery report.

## Final integration (2026-10-30)

- Branch provider-platform was rebased twice onto main as other agents committed work, then fast-forwarded into main. Final branch HEAD and main HEAD are both 9167d653 at the time of this record.
- Provider suites on the merged tree: test_provider_catalog 26, test_provider_accounts 11, test_provider_capabilities 5, test_provider_readiness 7, test_runtime_registry 4, test_provider_discovery 6, test_provider_surfaces 8, test_providers 45, test_connections 43, test_compat 8 - all passed.
- Branch audits: context hygiene passed, agent map check passed (118 lines), tool contracts passed, constitution passed, provider research audit PASS, emoji audit clean on branch files.
- Main checkout verification after fast-forward: provider research audit PASS, agent map check passed, context hygiene passed. The main working tree still contains another session's uncommitted files; they were not modified, staged or reverted. Audits that scan those files (for example a working-tree emoji scan over .codewhale state and another session's research file) are not attributable to this slice and are reported in the delivery report.
- Security review: artifacts/security-review.md (no blocking finding; one documented SSRF-adjacent hardening gap carried over from before this slice).

## Live verification addendum (2026-10-30)

- Live tests performed after the initial delivery with the owner's explicit authorization: direct DeepSeek
  text generation through the built-in runtime, managed OpenCode runtime text generation with a DeepSeek
  model, and an external OpenCode CLI reference request. All three produced the expected text.
- The provider catalogue now records DeepSeek as an implemented direct route and OpenCode as implemented;
  capability evidence contains two dated live-verified text entries; the capability matrix marks only those
  routes live-verified and the page/website still state that everything else is unverified.
- Failure-path evidence: the stored OpenCode Go API key is expired; Hutch surfaced the provider error in a
  failed run with cost 0.0 and performed no retry or silent account switch.
