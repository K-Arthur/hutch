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
routes; no key was present, so every account truthfully renders needs-authentication. Authenticated live
provider states were exercised in separate runs (see the live section) and were not captured as
screenshots; the temporary credential was removed afterwards. The website was served over HTTP from
the worktree, not opened as file://, to avoid font CORS noise.

| Surface | Viewports | Result |
|---|---|---|
| /providers, /models, /legacy/connections | 1440x960, 1280x720, 900x1024, 390x844, 320x740 | pass; HTTP 200; zero console errors/warnings; zero horizontal overflow; full-page and review captures saved |
| website index #providers (collapsed and expanded) | same five | pass; zero console errors; zero horizontal overflow |
| 200 percent text reflow (/providers and website #providers) | 1280x720 | pass; no horizontal overflow after font-size 200 percent |

The capture run was repeated after rebasing onto current main and again after the live-verification data/website changes; each run had the same result: zero console errors, zero horizontal overflow, all five viewports. The captures use unauthenticated accounts, so the page banner correctly states the two live-verified routes while every account still renders needs-authentication. Artifacts: artifacts/visual/ (full-page and review PNGs, capture-results.json, server logs). Inspected at
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
  routes live-verified; the page banner and website state that only those two text routes are live-verified.
- Failure-path evidence: the stored OpenCode Go API key is expired; Hutch surfaced the provider error in a
  failed run with cost 0.0 and performed no retry or silent account switch.

## Native Gemini route (2026-10-31)

Environment: no `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the process environment, no Google account
authorized for this work, and no local Gemini-compatible server. Network reads of the public discovery
document and docs pages were available, so the adapter was written from the published schema rather than
from an SDK's behaviour.

| Check | Command | Result |
|---|---|---|
| Contract tests for the native adapter | `uv run --frozen --no-sync pytest -q tests/test_provider_gemini.py` | 30 passed |
| Provider, connection, catalogue and tool-profile batch | `uv run --frozen --no-sync pytest -q tests/test_provider_gemini.py tests/test_connections.py tests/test_provider_catalog.py tests/test_provider_accounts.py tests/test_provider_capabilities.py tests/test_provider_readiness.py tests/test_compat.py tests/test_providers.py tests/test_toolcalling_compiler.py tests/test_integration_contract_regressions.py tests/test_models_layer.py tests/test_provider_surfaces.py` | 242 passed, 3 xfailed (includes the readiness correction and the health regression test) |
| Model switcher and provider surfaces | `uv run --frozen --no-sync pytest -q tests/test_provider_surfaces.py tests/test_model_switcher.py` | 39 passed |
| Website asset hashes and metadata | `uv run --frozen --no-sync pytest -q tests/e2e/test_website.py -k "hash or metadata or faq"` | 2 passed |

What those tests establish, stated narrowly:

- Request conversion: `contents` / `systemInstruction` / `functionDeclarations` (with `$schema` stripped,
  non-local `$ref` refused) / `generationConfig` caps, and `x-goog-api-key` in a header rather than the URL.
- Streaming: `:streamGenerateContent?alt=sse` framing, usage counters accumulated across chunks, and a
  stream that ends without a completion marker raising a typed `stream` error that the base class retries
  once without streaming (matching the existing SR-9 contract).
- Tool calls: `functionCall` parts become Hutch `ToolCall`s; the `thoughtSignature` is remembered and
  replayed on the assistant turn; `functionResponse` carries the tool result back.
- Typed outcomes for auth, missing model, quota versus rate limit, context overflow, safety refusals,
  blocked prompts, truncation and `MISSING_THOUGHT_SIGNATURE`.
- Model discovery paginates and refuses embedding-only rows.
- Wiring: the `google-gemini` template builds a `gemini`-protocol connection, and an ambient
  `GEMINI_API_KEY` is sent only to `generativelanguage.googleapis.com`.

Not established by the contract tests: that a real Gemini key works, that any model accepts an image, that tools behave
reliably, or that quotas and usage match the provider billing console. The route stays
`implemented-unverified` and the matrix says `not live-verified`.

### Live endpoint round-trip (2026-10-31, no credential)

The workflow environment has outbound network access and no Gemini credential. The adapter was pointed at
the real, live Generative Language endpoint with a deliberately invalid key, which is harmless, spends
nothing and proves more than a fixture does:

| Observation | Result |
|---|---|
| DNS/TLS/HTTP to `https://generativelanguage.googleapis.com/v1beta/models` | reached; Google answered |
| Provider response for the invalid key | HTTP 400 `INVALID_ARGUMENT` with "API key not valid. Please pass a valid API key." |
| Hutch `probe_models()` | `(False, "google rejected the credentials (API key not valid. Please pass a valid API key.). Check the API key.", [])` |
| Hutch `health()` after the fix | `reachable, but the API key was rejected` |

Two facts this produced that a fixture could not:

1. Google signals an invalid API key with **400 INVALID_ARGUMENT**, not 401/403. The error mapper already
   classified it correctly from the response body, but the health probe used `raise_for_status()` and
   surfaced a raw `HTTPStatusError` string. Health now maps through the same typed path, and
   `tests/test_provider_gemini.py` pins the 400-as-auth case.
2. The transport, URL shape, header placement and JSON error envelope are exercised against the real
   service, so an endpoint or header mistake would have failed here rather than in a user's first run.

Still not established, and not claimed: authenticated model discovery, inference, streaming, tool calls,
vision, usage reporting and quota behaviour. Those need a real key, and the matrix stays
`not live-verified`.
### Visual re-check of the marketing provider section (2026-10-31)

Served `website/` over HTTP and captured the expanded `#providers` panel at 1440x960, 1280x720, 900x1024,
390x844 and 320x740, plus one 1280x720 capture at 200 percent text size.

| Viewport | Horizontal overflow | Console errors | Gemini in the shipped list, Google gone from the research list |
|---|---|---|---|
| 1440x960 | 0 px | none | yes |
| 1280x720 | 0 px | none | yes |
| 900x1024 | 0 px | none | yes |
| 390x844 | 0 px | none | yes |
| 320x740 | 0 px after the fix (10 px before it) | none | yes |

Defect found by inspection and fixed: at 320 px the dated `deepseek api (live-verified 2026-10-30)` badge was
wider than the column and pushed the page 10 px sideways. `.routes-list .badge` now wraps inside the badge
(`white-space: normal`, `overflow-wrap: anywhere`, `height: auto`, `max-width: 100%`) in
`website/styles.css`; the CSS was rebuilt from its source and the asset hashes restamped.

Pre-existing and not fixed here: at 200 percent text size the site's horizontal navigation overflows by
316 px. The committed page measures the same 316 px, so this is a standing site-wide reflow gap rather than a
regression from this slice.

Remaining gaps for this route:

- No live catalogue or inference call (no credential available in this environment).
- Thought signatures survive only for the life of the Hutch process; a restart mid-conversation produces
  the provider's own `MISSING_THOUGHT_SIGNATURE` error, which is reported as a typed failure rather than
  hidden. Persisting them needs an additive field on the stored assistant message, a larger change than
  this slice.
- Speech, video, music, image generation and provider-native search remain documented only; the media job
  architecture was not extended in this slice.

## Hosted OpenAI-compatible routes (2026-10-31)

The catalogue carried 62 provider identities but only a handful had a real route. This slice wires the
hosted vendors whose endpoints the research register reached from vendor documentation, and records what
a credential-free call to the live service actually shows. No key was sent, no model was called and
nothing was spent.

Method: accept: application/json, `GET <base>/models`, 20 s timeout, one attempt, TLS verified. The URL
probed is exactly `template.base_url + "/models"`, so the template cannot drift from the observation.
Artifact: `artifacts/live-verification/endpoint-reachability-2026-10-31.json`.
`tests/test_provider_routes.py` fails if the artifact and the templates disagree.

| Provider | Probed URL | HTTP | What it shows |
|---|---|---:|---|
| arcee | `https://api.arcee.ai/api/v1/models` | 401 | host and route exist; credential demanded |
| byteplus | `https://ark.ap-southeast.bytepluses.com/api/v3/models` | 401 | host and route exist; credential demanded |
| cerebras | `https://api.cerebras.ai/v1/models` | 403 | host and route exist; credential demanded |
| chutes | `https://llm.chutes.ai/v1/models` | 200 | public model list returned; no credential used |
| cohere | `https://api.cohere.ai/compatibility/v1/models` | 401 | host and route exist; credential demanded |
| deepinfra | `https://api.deepinfra.com/v1/openai/models` | 200 | public model list returned; no credential used |
| fireworks | `https://api.fireworks.ai/inference/v1/models` | 401 | host and route exist; credential demanded |
| gmi-cloud | `https://api.gmi-serving.com/v1/models` | 401 | host and route exist; credential demanded |
| groq | `https://api.groq.com/openai/v1/models` | 401 | host and route exist; credential demanded |
| huggingface | `https://router.huggingface.co/v1/models` | 200 | public model list returned; no credential used |
| kilocode | `https://api.kilo.ai/api/gateway/v1/models` | 200 | public model list returned; no credential used |
| minimax | `https://api.minimax.io/v1/models` | 401 | host and route exist; credential demanded |
| mistral | `https://api.mistral.ai/v1/models` | 401 | host and route exist; credential demanded |
| moonshot | `https://api.moonshot.ai/v1/models` | 401 | host and route exist; credential demanded |
| novita | `https://api.novita.ai/openai/v1/models` | 200 | public model list returned; no credential used |
| nvidia | `https://integrate.api.nvidia.com/v1/models` | 200 | public model list returned; no credential used |
| ollama-cloud | `https://ollama.com/v1/models` | 200 | public model list returned; no credential used |
| stepfun | `https://api.stepfun.com/v1/models` | 401 | host and route exist; credential demanded |
| synthetic | `https://api.synthetic.new/v1/models` | 200 | public model list returned; no credential used |
| tencent-cloud | `https://tokenhub.tencentmaas.com/v1/models` | 401 | host and route exist; credential demanded |
| together | `https://api.together.xyz/v1/models` | 401 | host and route exist; credential demanded |
| venice | `https://api.venice.ai/api/v1/models` | 200 | public model list returned; no credential used |
| volcengine | `https://ark.cn-beijing.volces.com/api/v3/models` | 401 | host and route exist; credential demanded |
| xai | `https://api.x.ai/v1/models` | 401 | host and route exist; credential demanded |
| zai | `https://api.z.ai/api/paas/v4/models` | 401 | host and route exist; credential demanded |

What this establishes: each host resolves, presents a valid certificate, serves the path Hutch's adapter
will call, and answers with either a model catalogue or an explicit authentication challenge. That is
enough to say the route is real and correctly addressed; it is not enough to say a given account can use
it.

What it does not establish: that any specific model exists for a buyer, that inference, streaming, tool
calling, vision, audio, video, music or search works, or how the provider bills. All 25 routes stay
`implemented-unverified`, the matrix says `not live-verified`, and no marketing claim was upgraded.

Two endpoint corrections came from the probe rather than from documentation: BytePlus ModelArk answers on
`ark.ap-southeast.bytepluses.com` (the research register had listed it as unverified), and Kilo Gateway
serves both `/v1/models` and chat under `https://api.kilo.ai/api/gateway/v1` rather than at the bare
gateway root. Both are now recorded with the observed URL.

Focused checks for this slice:

| Check | Command | Result |
|---|---|---|
| Route wiring and evidence agreement | `uv run --frozen --no-sync pytest -q tests/test_provider_routes.py` | 5 passed |
| Catalogue, connections, accounts, surfaces, readiness | `uv run --frozen --no-sync pytest -q tests/test_provider_catalog.py tests/test_connections.py tests/test_provider_accounts.py tests/test_provider_surfaces.py tests/test_provider_readiness.py tests/test_compat.py` | 108 passed |
| Research-package honesty audit | `python3 scripts/audit_provider_research.py` | PASS |

### Visual re-check of the provider surfaces (2026-10-31)

The app was started from this tree against an isolated state directory and captured with Playwright
Chromium; the marketing site was served over HTTP from `website/`. Four real, unauthenticated connection
rows (groq, cerebras, xai, minimax) were created through the normal connection store so the pages had
accounts to render. No key existed, so every account truthfully renders `needs authentication`.

| Surface | Viewports | Result |
|---|---|---|
| `/providers` | 1440x960, 1280x720, 900x1024, 390x844, 320x740 | HTTP 200, 0 px horizontal overflow, 0 console errors/warnings |
| `/legacy/connections` | same five | HTTP 200, 0 px overflow, 0 console errors |
| website `#providers` (expanded) | same five | HTTP 200, 0 px overflow, 0 console errors; the new `shipped routes, inference unverified` group and all 25 badges present |
| `/providers` at 200 percent text | 1280x720 | 0 px overflow |

Artifacts: `artifacts/visual/routes-2026-10-31/` (`capture-results.json`, full-page PNGs, and
`review/` viewport-sized copies). Inspected at each viewport: the account cards with their
`needs authentication` state and the exact variable to set, the provider catalogue cards showing
`implemented-unverified` and per-provider account counts, and the website provider panel in its collapsed
and expanded forms.

Defect found by inspection and fixed before the accepted run: the first attempt named all 25 new routes
inside the "Shipped model routes" paragraph. At 1440 px that paragraph grew about twice as tall as its two
neighbouring cards and left visible dead space under them. The names now live only in their own badge
group, and the paragraph carries one sentence pointing at it.

Standing gap, measured rather than assumed: at 200 percent text the site's horizontal navigation overflows
by 316 px. The committed page measures the same 316 px (verified by stashing this slice's website edit and
re-measuring), and the widest element is a header `btn btn-primary btn-sm`, not anything in the provider
section. It is a site-wide reflow gap, not a regression from this slice, and it is left unfixed here
because changing the site's global header is outside this slice's ownership.

## OpenCode Go discovery path (2026-10-31)

The installed OpenCode credential store (`~/.local/share/opencode/auth.json`, read in memory only,
never copied into the repository) holds an `opencode-go` key and a `xiaomi-token-plan-sgp` key. Both
were probed against their live `/models` endpoints.

| Route | Observation | Meaning |
|---|---|---|
| OpenCode Go, `/go/openai/v1/models` | HTTP 404 | the chat base is not where the catalogue lives |
| OpenCode Go, `/go/v1/models` | HTTP 401 `authentication_error / api_key_expired` | the documented path is right; this key is expired |
| OpenCode Go, `POST /go/openai/v1/chat/completions` | HTTP 400 `MissingSessionID` | the chat path and the `x-opencode-session` requirement are both real |
| Xiaomi Token Plan SGP, `/v1/models` | HTTP 200, 6 models (`mimo-v2.5-asr`, `-tts`, `-tts-voiceclone`, `-tts-voicedesign`, ...) | the stored key authenticates and the regional endpoint answers |

The 404 matters. Hutch built its OpenCode Go connection from the chat base URL, so model discovery asked
`.../go/openai/v1/models`, which does not exist, and reported `opencode-go returned HTTP 404`. The vendor
documents the catalogue at `https://opencode.ai/inference/go/v1/models`. A user with a perfectly valid Go
key would have seen a 404 and concluded the connection was broken.

Fixed by letting a connection declare where its catalogue lives, separately from where chat lives:

- `Connection.models_base_url` (optional, validated as an absolute HTTP(S) URL with no embedded
  credentials) carries it; the adapter builds `GET <models_base_url>/models` when it is set.
- It is a template default that only applies to the template's own host. If `base_url` is overridden to a
  different origin the catalogue URL is dropped, so chat and discovery can never point at two different
  services. The existing fake-server test caught exactly this hazard on the first run.
- `tests/test_provider_routes.py` pins the path, the origin rule and the credential-embedding refusal.

Live check through Hutch's own code path afterwards: `probe_models()` returns
`reachable, but the API key was rejected` instead of the 404, and `health()` agrees. That is the truthful
message for an expired key, and it is the provider's own wording, not a guess.

Not established: no inference was run on OpenCode Go (the key is expired, and `probe_models` spends no
tokens by design), no model list was retrieved for this account, and the Xiaomi models were listed but not
called. Both routes keep their existing status; neither is live-verified for inference.

Housekeeping: the Xiaomi key authenticating is a new, dated fact about an endpoint Hutch already shipped.
It does not upgrade any capability claim - a model list is not a working chat request, and the six models
listed are speech and transcription models rather than chat models.

## Xiaomi Token Plan live inference (2026-10-31)

A second credential in the installed OpenCode store turned out to be valid: `xiaomi-token-plan-sgp`.
Its `/models` endpoint returned six ids - two chat models and four speech/transcription models. The
chat models were exercised through Hutch's own connection and adapter, with the key read in memory and
never written to the repository or an artifact.

| Model | Request | Result | Tokens (prompt / completion) |
|---|---|---|---|
| `mimo-v2.6-flash` | non-streaming, "Say: HUTCH_LIVE_OK", cap 64, temperature 0 | reply `HUTCH_LIVE_OK`, finish `stop` | 15 / 23 |
| `mimo-v2.6-pro` | same | succeeded | 22 / 12 |
| `mimo-v2.6-flash` | same, cap 12 | no visible answer, finish `length` | 15 / 12 |

Artifacts: `artifacts/live-verification/xiaomi-chat-live-2026-10-31.json` and
`xiaomi-reasoning-live-2026-10-31.json`.

### A real defect the live call exposed

The raw reply carries the model's thinking in a `reasoning_content` field next to `content`:

    {"message": {"content": "HUTCH_LIVE_OK",
                 "reasoning_content": "The user wants me to say ...",
                 "role": "assistant", "tool_calls": []},
     "usage": {"completion_tokens": 23, "prompt_tokens": 15,
               "completion_tokens_details": {"reasoning_tokens": 15}}}

Hutch's OpenAI-compatible adapter read only `message.content`. Two consequences, both bad:

1. **Billed work disappeared.** 15 of 23 completion tokens were reasoning and Hutch showed none of it,
   so the usage line charged for tokens with no visible output anywhere.
2. **An empty answer looked like a model fault.** With a cap of 12 the model spent 11 tokens thinking,
   hit the limit, and returned `content: ""`. Hutch reported an empty string and stopped. A person would
   reasonably conclude the model was broken; the model had answered the only way it could.

Fixed in `providers/openai_result.py`, which now owns result construction and keeps `thinking` (also
accepting a `reasoning` field, which other servers use), plus notes when the provider bills reasoning
tokens and when an answer was entirely reasoning. `tests/test_provider_reasoning.py` uses the real
response shape above as its fixture. Live confirmation afterwards: cap 12 returns no content and says
"the model returned no visible answer; raise the output limit or ask for a shorter answer"; cap 64
returns `HUTCH_LIVE_OK` with "the provider billed 15 of 23 completion tokens as reasoning".

The adapter file had to shrink rather than grow (it is a frozen over-cap file), so result construction
moved into its own module - a separation worth having anyway, because the honesty rules now live beside
each other and can be tested without a transport.

### What this does and does not establish

- Established: authenticated model discovery for this account, text generation on two chat models,
  usage reporting, and the two reporting behaviours above, all through Hutch's own code path.
- Not established: streaming, tool calling, vision, the speech/transcription models, other regions, or
  any price. The Token Plan bills in credits and Hutch does not convert credits to currency, so the
  route stays `subscription` billing with no currency estimate.
- Streaming was not exercised: `Provider.chat` takes no per-call delta callback, and driving the
  streaming path live would need a harness whose result would not tell us anything about a user's run.
  Recorded as a gap rather than implied.

## Speech-to-text: transcribe_audio (2026-10-31)

Hutch had no audio path at all: the media store and the block renderer anticipated `kind: "audio"`,
but nothing produced or consumed speech. This slice adds the first one - speech-to-text - as a
governed tool rather than a chat feature, so the same capability is available to bots and workflows
without changing which model answers a conversation.

### What was built

| Piece | File | What it owns |
|---|---|---|
| Route declaration | `src/hutch/data/connections.json` (4 xiaomi templates) | `transcription.protocol/model/languages/max_audio_base64_bytes/source`; a connection only offers the route when its bundled template declares it |
| Adapter | `src/hutch/providers/transcription.py` | wav/mp3 sniffing, data-URL request, response parsing, usage extraction, typed `ProviderError`s, redirect refusal |
| Tool | `src/hutch/tools/transcribe.py` | workspace path jail, account selection, approval detail, `begin_effect`, usage ledger row, no retry |
| Registry | `src/hutch/tools/__init__.py`, `src/hutch/integrations/catalog.py` | `transcribe_audio` in the catalogue, the new `audio` group, and Strict Offline withholding |

### The wire contract, observed rather than assumed

`POST https://token-plan-sgp.xiaomimimo.com/v1/chat/completions` with
`model: mimo-v2.5-asr` and one `input_audio` content part (`data:audio/wav;base64,...`). The reply is
an ordinary chat completion: `choices[0].message.content` is the transcript,
`usage.prompt_tokens_details.audio_tokens` counts audio input, and `usage.seconds` reports duration.
The vendor documents wav/mp3 only and a 10 MB base64 ceiling
(https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/Speech-Recognition, fetched 2026-10-31).

### Live run (owner-authorized, bounded)

One `mimo-v2.5-tts` request produced a 169,004-byte wav ("Hutch transcription check, October thirty
first."), then `TranscribeAudioTool` transcribed it through the real adapter. No secret was written
anywhere; the state directory was temporary and the artifact carries no audio bytes.

| Observation | Value |
|---|---|
| Transcript | `1. Hutch transcription check, October thirty-first.` |
| Model reported by the provider | `mimo-v2.5-asr` (the requested model) |
| Usage | 48 prompt / 11 completion tokens; 23 audio input tokens |
| Audio duration reported | 4 s |
| Ledger row | `xiaomi / mimo-v2.5-asr / 48 / 11 / transcription / mimo-live` |
| Approval detail | connection, provider, endpoint, model, language, bytes, format, billing |
| Wall time | 4.03 s |

The transcript matches the sentence; the model prefixed an ordinal marker that was not in the audio.
That is recorded rather than trimmed, because the tool reports what the provider returned.

### What this establishes and what it does not

Established: authenticated speech-to-text through Hutch's own tool and adapter; exact usage capture;
run-ledger accounting under `kind=transcription`; an approval prompt that names the receiving service
and account before the audio leaves the machine; redirects refused so the bearer key cannot travel to
another host.

Not established: mp3 input (the byte-sniffing and payload path are shared, but only wav was sent),
Chinese or automatic language detection, the cn/ams regional hosts, behaviour near the 10 MB ceiling,
streaming transcription, and any currency price (the Token Plan bills in credits and Hutch has no
reviewed price row for these models).

### Focused checks for this slice

| Check | Command | Result |
|---|---|---|
| Adapter and tool behaviour | `uv run --frozen --no-sync pytest -q tests/test_provider_transcription.py tests/test_transcribe_tool.py` | 30 passed |
| Tool contract + registry | `uv run --frozen --no-sync python scripts/audit_tool_contracts.py` | passed (45 tools) |
| Context hygiene | `uv run --frozen --no-sync python scripts/audit_context_hygiene.py` | passed |
| Research package honesty | `python3 scripts/audit_provider_research.py` | PASS |

Marketing claim check: the provider section was captured with Playwright Chromium at 1440x960,
1280x720, 900x1024, 390x844 and 320x740, plus 1280x720 at 200 percent text. Every viewport reported
0 px horizontal overflow and zero console errors; the 200 percent run keeps the site-wide 316 px header
gap already recorded above. Measured against the copy and badge added here: 0 px overflow, and the new
sentence and badge render at every width. Evidence: `artifacts/visual/asr-2026-10-31/`.

Artifact: `artifacts/live-verification/xiaomi-transcription-live-2026-10-31.json`.

## Tool calling and streaming (2026-10-31)

The two capabilities every provider row had been deferring were exercised on the one route with a
working credential. Both went through Hutch's own code: the CLI `hutch run` path for the end-to-end
case, and `provider_for_connection` for the adapter cases. Nothing was mocked and no response was
replayed.

### End-to-end: two tool calls from one streamed turn

An isolated state directory, one named connection (`mimo-live`, Token Plan sgp), and a bot with only
`list_files` and `read_file`, working in a temporary folder containing one `notes.txt`.

| Observation | Value |
|---|---|
| Prompt | list the workspace, read `notes.txt`, quote its first line |
| Run status | succeeded, 2 steps, exit code 0 |
| Step 1 | `streamed=True`, finish `tool_calls`, 768 prompt / 40 completion tokens |
| Calls emitted | `list_files {}` and `read_file {"path": "notes.txt"}` in the same assistant turn |
| Tool results | `notes.txt`; the file's full text |
| Step 2 | `streamed=True`, finish `stop`, 840 prompt / 39 completion tokens |
| Answer | quoted `Project codename: lantern.` |
| Stream retries | none: no step fell back to non-streaming |
| Ledger | one usage row per step, same account |

A second identical run reproduced it (2 steps, both streamed, the same two calls, the same quoted
answer), so the result is not a one-off. Parallel calls inside a single streamed response are the
interesting case for the assembler, and it handled them.

### Adapter level: both parsers agree

One `list_files` schema sent twice through `OpenAICompatProvider.chat`, once batched and once streamed:

| Request | `result_streamed` | finish | Parsed call | argument state |
|---|---|---|---|---|
| `stream=False` | False | `tool_calls` | `list_files {}` | `json_object`, no parse error |
| `stream=True` | True | `tool_calls` | `list_files {}` | `json_object`, no parse error |

### A real defect the live run exposed: streamed reasoning was discarded

The batch path keeps a model's thinking (`providers/openai_result.py`, fixed 2026-10-31). The streamed
path did not, and streaming is the default, so the same request reported different output depending on
transport.

A raw wire probe settled where the fault lay - not in the provider:

| Probe | Observation |
|---|---|
| `POST /chat/completions`, `stream: true`, one-word answer | 8 SSE chunks; `delta` fields seen: `role` (7), `content` (7), `tool_calls` (7, empty arrays), `reasoning_content` (7) |
| Reasoning text | 51 characters, starting "The user wants me" |
| Usage chunk | `prompt_tokens` 14, `completion_tokens` 19, `reasoning_tokens` 15 |

So MiMo does stream its thinking; Hutch dropped it. `toolcalling/streamassembly.py` now collects
`reasoning_content` (and `reasoning`) deltas and the adapter passes them into the result, matching the
batch parser. A drift test pins the two field-name lists together.

Measured effect, with the caveat that these are separate requests and the model thinks differently
each time: the streamed adapter probe reported 0 thinking characters before the change and 100 after;
the batch probe reported 53 and 53. Character counts are not expected to match across requests - the
point is that the streamed path no longer reports none.

After the fix the end-to-end run still passed with both steps streamed and no retry, so the change did
not disturb tool-call assembly.

### What this establishes and what it does not

Established: native tool calling on `mimo-v2.6-flash` through the built-in runtime (two calls in one
turn, validated, dispatched, results fed back, answer derived from them); batch and streamed tool-call
parsing agreeing on the same schema; the SSE transport path used for every live model call with usage
reported from the stream; reasoning deltas assembled on the streamed path.

Not established:

- **Progressive rendering.** Hutch consumes the stream server-side (watchdog, partial recovery, tool-call
  assembly). The dashboard does not paint tokens as they arrive. Calling this "streaming" without that
  qualifier would overclaim what a user sees.
- **Cancellation mid-stream.** The stop path exists and is covered by tests; it was not exercised live.
- **Vision, audio input, structured output and other tool families** on this route.
- **Other models and regions.** Only `mimo-v2.6-flash` was exercised for tools and streaming;
  `mimo-v2.6-pro` was exercised for text only, and the cn/ams hosts were not contacted.

### Focused checks for this slice

| Check | Command | Result |
|---|---|---|
| Stream reasoning and assembler | `uv run --frozen --no-sync pytest -q tests/test_provider_stream_reasoning.py` | 5 passed |
| Streaming and provider regression | `uv run --frozen --no-sync pytest -q tests/test_toolcalling_streaming.py tests/test_toolcalling_properties.py tests/test_provider_reasoning.py tests/test_providers.py` | 84 passed |
| Capability evidence and surfaces | `uv run --frozen --no-sync pytest -q tests/test_provider_capabilities.py tests/test_provider_surfaces.py` | 18 passed |

Artifacts: `artifacts/live-verification/xiaomi-tool-calling-streaming-live-2026-10-31.json` (CLI run),
`xiaomi-adapter-tool-calls-2026-10-31.json` (adapter batch/streamed), `xiaomi-stream-shape-2026-10-31.json`
(raw wire probe).
