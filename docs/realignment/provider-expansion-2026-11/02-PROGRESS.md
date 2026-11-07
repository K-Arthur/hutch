# Progress: provider expansion (2026-11)

Update at every checkpoint. Keep entries short and factual.

## Phase status

| Phase | Status | Last commit | Live-verified | Blocked on |
|---|---|---|---|---|
| 0 Diagnose | done 2026-11-06 | Phase 0 commit | none this phase; re-read 2026-10-31 Xiaomi evidence | - |
| 1 Route resolution | done 2026-11-06 | 9f0fa4ed | none this phase; no provider call | - |
| 2 Credential lifecycle | done 2026-11-06 | Phase 2 commit | fixture lifecycle; no provider call | - |
| 3 Flagship providers | done 2026-11-06 | 88edb95d | unauthenticated GET opencode.ai/inference/v1/models (200); no paid call | shell env lacks OPENAI/ANTHROPIC/GEMINI keys |
| 4 Hosted and gateways | done 2026-11-06 | 47067fc6 | unauthenticated probes of 49 hosts; real server + CLI on isolated state; no keyed call | no credential for any Phase 4 provider |
| 5 Local and custom | done 2026-11-06 | 43c472cf | real LM Studio 0.0.27-1 (cold load, streaming through the pinned transport, five layered outcomes); real Ollama 0.40.13 identified behind /v1 (GET only); no paid call | vLLM, SGLang, inferrs, ds4 not installable here; private-LAN path has no peer |
| 6 Media, speech, search | done 2026-11-06 | 7525db43 | none against a vendor; real `hutch serve` + SIGKILL recovery against a loopback stand-in provider (Hutch's own recovery and ledger only); no paid call | no credential for any of the 11 media providers; no real ComfyUI; Runway, MiniMax video, Google Omni wire not read |
| 7 Frontend | done 2026-11-06 | 02dd0c57 | none against a vendor; real `hutch serve` + Playwright Chromium: 49 checks, 40 pages, 4 widths, axe 4.13.0 clean, keyboard, reduced motion, Strict Offline verdict; wizard and jobs driven against loopback stand-ins (Hutch's UI, API and ledger only); no paid call | no credential for any paid route; no light theme (dark-only decision); no desktop or non-Chromium run |
| 8 Website and docs | not started | | | |
| 9 Final review and merge | not started | | | |

## Phase 0 outputs (2026-11-06)

- Baseline: `npm run check:agent` passed; 26 focused provider/media test files ran (433 passed, 1
  failed). The failure was `test_catalog.py::test_the_presets_came_out_of_code_unchanged`: `Bot`
  gained `archived`, which the digest hashed. Recomputing with the pre-change field set reproduced
  every recorded digest, so preset content is unchanged. Fixed by excluding `archived` from the
  digest (test-only).
- `docs/research/2026-11-provider-expansion/00-GAP-AUDIT.md`: baseline, G1-G18 cross-cutting
  findings, missing identities, all 62 catalogue rows, ordered backlog.
- `docs/research/2026-11-provider-expansion/01-FAILURE-MINING.md`: auth, routing, retry, tool,
  local-engine and media failures classified fixable/mitigable/vendor-side, with test ideas.
- Visual capture: `docs/realignment/capture_provider_pages.py` captured Providers, Models and
  first-run at 360/768/1280/1920 in light and dark; 24/24 with 0 console errors, 0 failed requests,
  0 px overflow. Artifacts under
  `docs/realignment/artifacts/provider-expansion-2026-11/phase0/` (`results.json`).
- Real stack: isolated `HUTCH_STATE_DIR` + `hutch init` + `hutch serve --port 18890`; no provider
  call was made.

## Phase 1 outputs (2026-11-06)

- `9fffa9ab` Providers banner is derived from `LIVE_VERIFIED_EVIDENCE` grouped by route/date plus
  catalogue status counts. The old hardcoded sentence (which omitted Xiaomi and mislabeled
  documented/blocked entries) is gone.
- `d7f53448` `providers/routing.py` resolves `(provider, account, account_source, billing, model,
  runtime, protocol, endpoint, status)` from local facts, labels ambient keys, withholds them from
  non-official hosts, and refuses to pick between accounts. Exposed at
  `/api/v1/provider-resolution`. `resolve_chain` flags a subscription-to-metered hop.
- `36673256` schema version 91 writes the implicit `openai-compatible/` prefix into saved `model`,
  `fallbacks`, `escalation.to` and `task_routes`. Behavior, billing and order are unchanged;
  already explicit routes are untouched. Migration module keeps frozen `store.py` at its cap.
- `9f0fa4ed` `SpendGuard` refuses a fallback or escalation from a subscription primary to
  per-token/credits before the call.
- `docs/research/2026-11-provider-expansion/02-ROUTE-RESOLUTION.md` records the research, design,
  real-stack output and limits.
- Design docs updated in the same series: `docs/provider-platform.md` (resolver and billing
  boundary), `docs/models.md` (resolution API and refusal rules),
  `docs/realignment/provider-compatibility.md` (resolution subsection), and ADR-0028.
  `docs/runtime-setup.md` is unchanged because this phase did not change runtime behavior.

## Phase 2 outputs (2026-11-06)

- `chatgpt_status.py` projects a saved account into `active`, `expired`, `revoked` or `missing`
  with `can_refresh` and the expiry; `chatgpt_auth.accounts()` shrank to use it.
- `AccountProfile` carries `credential_state` and `credential_expires_at`. Readiness maps `expired`
  to `authentication_expired` and `revoked` to `needs_authentication`; `/providers` and
  `/legacy/connections` show the state instead of a green "missing" chip.
- `ConnectionBook.has_key` for a ChatGPT account requires an active credential; expired/revoked
  accounts no longer trigger model discovery.
- Single-flight is proven with two real processes contending for one rotating token; a failed
  refresh leaves the stored access and refresh tokens unchanged.
- A remote dashboard states that the ChatGPT loopback callback cannot complete there and points to
  an API key or the official CLI; no undocumented device-code client was added. OpenCode keeps its
  own official OAuth/device flow.
- `docs/research/2026-11-provider-expansion/03-CREDENTIAL-LIFECYCLE.md`, ADR-0029, and updates to
  `provider-platform.md`, `models.md`, `runtime-setup.md`, `connections.md`.
- Real UI observation: three synthetic ChatGPT accounts (active, expired, revoked) on an isolated
  server; API states matched; 32/32 captures clean at four widths in light and dark.

## UI correction pass (2026-11-06, after Phase 2)

- Root cause: the server templates used `.list-row`, `.plain-list` and `.card-actions`,
  but those classes were only defined in `style.css`, which these pages do not load. Rows
  had no alignment primitive, so content and actions stacked wherever the browser put them.
- Inline form buttons were 32px beside 44px fields: `.hutch-actions .btn` already used the
  routine height, but `.hutch-inline` did not. Inline actions are now 40px (44px at phone
  width), and the page header actions are 40px rather than 32px.
- The Connections "Add a connection" gallery was 37 cards each with an always-visible
  primary Add button. It is now one form with a template select, optional custom endpoint
  fields, and a collapsed template reference. The page is 4,219px tall at 1280 (was 7,658).
- Provider account actions now share a trailing edge: label input, Rename and Remove local
  key in one row on desktop; on phones the input and Rename share a row and Remove aligns
  to the same right edge.
- The disabled ChatGPT sign-in action is a ghost button, not a green primary; mobile page
  actions are equal-width full-row buttons.
- Validation: 32/32 captures at 360/768/1280/1920 in light and dark, 0 console errors, 0
  failed requests, 0 px overflow; keyboard order for the add form is template, name, base
  URL, key variable, Add, template reference, each with a 2px focus outline; 54 focused
  tests passed. Baseline browser failures (assistant settings tabs, first-run readiness,
  phone pairing confirm) reproduce at HEAD without these changes and are not caused here.

## Phase 3 outputs (2026-11-06)

- `88edb95d` splits `kimi-coding` (Anthropic Messages at `https://api.kimi.com/coding`, `KIMI_API_KEY`,
  subscription, acknowledged User-Agent notice) and `opencode-zen` (prepaid gateway at
  `https://opencode.ai/inference/v1`, `OPENCODE_API_KEY`) into their own catalogue identities (64 total)
  and connection templates (43 total). Removes `kimi-coding-key` from `moonshot`.
- Adds regional pay-as-you-go templates with distinct env vars: `moonshot-cn` (`MOONSHOT_CN_API_KEY`),
  `zai-cn` (`BIGMODEL_API_KEY`), `qwen-standard-intl` (`DASHSCOPE_API_KEY`), `qwen-standard-cn`
  (`DASHSCOPE_CN_API_KEY`). Marks Alibaba Cloud Coding Plan (`qwen/coding-plan`) and Z.AI GLM Coding
  Plan (`zai/coding-plan`) as `blocked` with cited vendor terms; `test_flagship_routes.py` fails if any
  template points at a blocked plan host.
- Removes `coding_cli` from `google` (Gemini CLI replaced by Antigravity CLI on 2026-06-18; third-party
  OAuth token use is a terms violation).
- Owner approved up to 5 cents of live generation checks across OpenAI, Anthropic and Google Gemini,
  reading keys from shell env vars, but `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` and
  `GOOGLE_API_KEY` are all unset in this shell environment; recorded as `blocked: no credential in
  shell environment` with zero paid calls. Unauthenticated `GET https://opencode.ai/inference/v1/models`
  and `/zen/v1/models` returned HTTP 200 (96,452 bytes).
- Real stack + visual validation: isolated `HUTCH_STATE_DIR` on port 18891 with `kimi`, `zen` and `qwen`
  connections added; 32/32 Playwright captures at 360/768/1280/1920 in light and dark with 0 console
  errors, 0 failed requests and 0 px horizontal overflow (`artifacts/provider-expansion-2026-11/phase3/`).
- `docs/research/2026-11-provider-expansion/04-FLAGSHIP-ROUTES.md`, ADR-0032, and updates to
  `docs/connections.md`, `docs/provider-platform.md` and `docs/realignment/provider-compatibility.md`.

## Phase 4 outputs (2026-11-06)

- `95d67ea1` eight `implemented-unverified` templates and identities (`vercel-ai-gateway`, `litellm`,
  `clawrouter`, `bedrock-runtime`, `bedrock-mantle`, `microsoft-foundry`, `qianfan`, `stepfun-global`);
  Synthetic moved to its documented `/openai/v1` path with its Anthropic base recorded; Tencent Token Plan
  `blocked` with a cited source; Volcengine and BytePlus Coding Plan `documented` and not offered; pay-as-you-go
  notices on Volcengine, BytePlus and StepFun. New seam `providers/auth_headers.py`: a header value of
  `{api_key}` carries the key and suppresses the Bearer (Foundry `api-key`).
- `b7dc5774` `providers/schema_trim.py` and `tool_schema_unsupported_keywords` (Volcengine only): the wire copy
  of each tool schema loses bound keywords; `Tool.parameters` and `validate_call` are unchanged.
- `27363e55` a host-less template added without a host now names `--base-url`.
- `6dfdb24a` found by the live run, not planned: seven public-list hosts made `connections test` claim a key
  was authenticated. `models_list_ignores_key` (measured 2026-11-06) makes the check list the models and say
  the key was not verified; the Models page no longer prints "connection verified" for an unverified check.
- `47067fc6` the OpenAI chat provider construction moved to a helper (`provider_for_connection` 43 to 35 lines).
- Docs in the same series: `docs/research/2026-11-provider-expansion/05-HOSTED-AND-GATEWAYS.md` (sources,
  probes, failure classes, decisions, results), ADR-0033, `provider-platform.md`, `connections.md`, `models.md`,
  `provider-compatibility.md`. `runtime-setup.md` is unchanged: no runtime behavior changed.
- Validation: 633 focused tests passed (provider, catalogue, compat, media, route, connection, doctor,
  builtin runtime, plus `test_hosted_routes.py`, `test_schema_trim.py`, `test_connection_check_honesty.py`);
  `npm run check:agent` and `npm run audit:context` passed; 32/32 captures at 360/768/1280/1920 clean
  (`artifacts/provider-expansion-2026-11/phase4/`), cropped views inspected.
- Real stack: `hutch init`, ten `hutch connections add`, `hutch serve --port 18892` on a temporary state dir.
  Every new connection failed fast naming its key variable; `/api/v1/provider-resolution` mapped each spec to
  provider, connection, billing, endpoint, `needs_authentication`, `substituted: false`. Against real hosts with
  a made-up placeholder value: Vercel rejected it, Synthetic listed 13 models and was reported as not verified.
- Not run: any keyed or paid call (no credential), a real LiteLLM proxy, a real local engine, keyboard
  traversal (no markup changed), light theme (G16).

## Phase 5 outputs (2026-11-06)

- Diagnosis first (real LM Studio, loopback): `https://169.254.169.254/v1` saved as a connection; bot `base_url`
  routes accepted any URL; a name was never judged by its address; HTTPS-on-a-plain-port said "is the server running?";
  a missing `/v1` said "invalid model catalog"; vLLM/SGLang `max_model_len` was parsed and then ignored (the prior
  note that the field is not in `/v1/models` was wrong: vLLM and SGLang `ModelCard` both carry it).
- `c1003d35` `providers/endpoint_policy.py`: address kinds (loopback, private, fake-IP 198.18/15, public, blocked),
  exact-name allowlist `HUTCH_PRIVATE_HOSTS`, local-style names, vendor exemption.
- `02cc1416` `providers/pinned_transport.py`, installed at `offline.httpx_offline_options` (the one seam every httpx
  adapter uses, so no adapter call site changed): resolve once, judge every answer, connect to the validated address
  with the original Host and TLS name, plain HTTP only to loopback/private, a credential header never over plain HTTP
  off loopback. Real-socket tests, including dual-stack `localhost` fallback.
- `d5f027de` blocked literals refused at save in every scheme and spelling; pasted API paths reduced to the root
  (`connections.py` unchanged in length: same-line edits).
- `15894273`, `a92e16ac`, `8f5361b8` `providers/endpoint_probe.py` and `check_connection`: layers address, dns,
  connect, tls, key, models; `/v1` suggestion; real self-signed TLS test; Ollama named from its own `/api/version`;
  a user-run endpoint is reported as not key-verified; an HTTP error the server explained keeps its words.
- `46666e1d` vLLM/SGLang window from `max_model_len` when `owned_by` names the server (implemented-unverified).
- `c62043f9` custom Anthropic endpoints are checked before each call (the SDK uses a vendored `httpx2`, so it is not
  pinned).
- Docs in the same series: `docs/research/2026-11-provider-expansion/06-LOCAL-AND-CUSTOM.md` (sources, diagnosis,
  decisions, results, not-run list), ADR-0034, `connections.md`, `models.md`, `provider-platform.md`, `runtime-setup.md`,
  `provider-compatibility.md`. `compat.json` is unchanged (no route contract changed).
- Validation: focused provider/local/media/connection/offline/runtime suites (see the run recorded in the research
  doc); `npm run check:agent` (context hygiene, tool contracts, constitution passed; agent map regenerated after the
  commits) and `npm run audit:context` passed; 20/20 Models page captures at 360/768/1280/1920 with 0 console errors,
  0 failed requests, 0 px overflow.
- Real stack: isolated state, `hutch init`, `hutch serve --port 18893`; a real `hutch run` cold-loaded
  `lmstudio/qwen3-0.6b` (16384) and a named custom connection streamed an answer through the pinned transport; a bot
  at `http://169.254.169.254/v1` failed with the blocked-address sentence and `steps=0`.
- Not run: vLLM, SGLang, inferrs, ds4 (no engine); private-LAN address over real sockets (no peer; forwarding LM Studio
  to the LAN address was declined by the permission guard and not worked around); DNS rebinding against a real
  resolver; an environment proxy; keyboard traversal and light theme (no markup changed; dark-only, G16).

## Phase 6 outputs (2026-11-06)

- `82fd0813` paid synchronous results are held in an owner-only atomic spool inside `submit` (`media/spool.py`);
  reconcile leaves a recoverable job running; OpenAI Images picks `response_format` and sizes by model family (GPT
  Image rejects both DALL-E parameters, four tracker issues) and the SDK no longer retries a billable call;
  `moderation_blocked` is a refusal; result URLs go through one bounded downloader on the pinned transport.
  `media/status.py` holds the service statuses (`refused` is new) and `jobs.py` shrank from 592 to 577 lines.
- `dc172e1c`, `02b20c69` `data/media-routes.json` (19 rows: 14 implemented-unverified, 3 documented, 2 retired) driven by
  a `sync` and a `task` backend; an HTTP 200 is not success (in-body envelopes, refusal markers, no media);
  requests are checked against documented limits before the approval; `backend_for` refuses to choose between
  accounts; the approval names who receives the prompt, the credential, the billing and a dated estimate or
  "cost unknown" (`media/cost.py`, `data/media-prices.json`: only Google image and speech are priced).
  `run_provider_media` (170 lines) became small functions.
- `a21affc3` `media/ledger.py`, `media/resume.py`, `media/jobs_routes.py`: list, advance and cancel jobs outside the
  tool call (`/api/v1/media/jobs`), local-owner only. Fixed pre-existing `finalize()` returning a bare row on failure.
- `9f0a61dd` ComfyUI: queue-aware cancel (reads `GET /queue`, interrupts only our running prompt with its id, confirms
  by re-reading), outputs from images/gifs/videos/audio, bounded and pinned downloads.
- `406d09ba`, `a493257c` `docs/realignment/run_media_resume_check.py` and its record
  (`artifacts/provider-expansion-2026-11/phase6/media-resume-run.json`): SIGKILLed victim, real server finishes
  the job with one provider request, SHA-256 equal, spool released, video pending to done, unconfirmable cancel
  stays `cancel_unconfirmed`, MiniMax 1026 inside a 200 is `refused`. Provider is a stand-in.
- `87ac6e33` catalogue: fal, PixVerse, Deepgram, ElevenLabs from documented/deferred to implemented-unverified, services
  limited to what a route backs; a test fails if a status exceeds the route table.
- `ea57ead5`, `7525db43`, ADR-0036, `provider-platform.md`, `connections.md`, `provider-compatibility.md`,
  `docs/research/2026-11-provider-expansion/07-MEDIA-SPEECH-SEARCH.md` (sources, failure classes, design, results,
  defects found by running, not run). `runtime-setup.md` and `models.md` are unchanged: no runtime or model-choice
  behavior changed.
- Validation: 253 media tests, 590 provider/catalogue/compat/media/route/connection tests, 127 app and tool tests, 82
  tool-contract and offline tests; `npm run check:agent` and `npm run audit:context` pass; mutation checks on the
  envelope check, the no-retry header, the content-type check and the old ComfyUI cancel and fetch. The emoji audit
  reports 8 violations, all in another tool's untracked `.codewhale/state/subagents.v1.json`.
- No UI changed, so no screenshot gate applies; the Providers page media section is Phase 7.

## Phase 7 outputs (2026-11-06)

- `bf762114` Providers page is a route index: one row per provider, route chips that say built or not built (never green),
  search plus category, status, sign-in route and service filters in the query string (form hidden until script runs).
  Account readiness no longer repeats its detail as the next action. `providers/catalog_view.py`, `providers.js`,
  `providers.css`, `_providers_catalogue.html`. Height at 1280: 13,279 to 8,011 px with everything below added.
- `f46fd9d4` `/providers/{id}`: per-route setup wizard derived from state (`providers/wizard.py`), four actions in
  `server/pages_provider_detail.py` (add, key, terms, test), capability table that lists unknown capabilities as
  unverified. Unbuilt or blocked routes get one step and no form. Key never rendered; vendor host cannot be overridden.
- `bd03e97f` Route picker with the resolved tuple (plain GET form; script swaps the result), also shown under each saved
  route on Models. Fixed a shared `Query` object that bound all picker parameters to the first name.
- `c86b2c82` Media, speech and search section (`media/view.py`, `media-jobs.js`): routes with status, credential source
  and a dated cost or "cost unknown"; jobs from the ledger with check and a two-click cancel; provider search apart from
  `live_search`.
- `166675b6` One sentence for what was found and what is saved, shared by first run and Models (`starter-route.js`);
  `app.js` shrank by four lines.
- `003e1750` Inference-mode check in the picker through `validate_inference_mode` (Strict Offline refuses a hosted route
  in the policy's words; a loopback route is allowed and not called working).
- `02dd0c57` Review fixes (below). ADR-0037, `docs/research/2026-11-provider-expansion/08-FRONTEND.md`, and updates to
  `provider-platform.md`, `models.md` and `design-system.md` are in the docs commit that follows.
- Validation: 73 tests added; 753 adjacent tests passed (provider, media, models, connections, static); 23 focused browser
  tests for first run and Models passed; `npm run check:agent` and `npm run audit:context` pass at the last code commit.
  Real-browser gate `docs/realignment/capture_provider_ui.py` (4 files, each under 400 lines): 49 checks, 40 pages, zero
  console errors, failed requests, overflow or credential in a page; evidence in
  `docs/realignment/artifacts/provider-expansion-2026-11/phase7/` (results plus 13 screenshots).
- Mutation checks (each made its test fail): ownership check, vendor base URL override, any-template, no-dedupe,
  unverified-as-green, filters visible, key done without a key, unbuilt route with forms, terms always, shared `Query`,
  trusted account, no Models tuple, actions on finished jobs, fabricated price, buttons always, mode always allowed,
  unguarded sign-in template, probe always.
- No generated CSS was edited or rebuilt; the new styles are the hand-written `static/providers.css`.

## Owner inputs (batch, answered 2026-11-06)

- Provisioned credentials: OpenAI, Anthropic, Google Gemini. Every other paid route is
  "blocked: no credential" for live purposes.
- Spend cap: discuss per phase; ask before the first paid call with route, model and token cap.
- Dependency approvals: both granted for Phase 4 (AWS SigV4 for Bedrock, Azure/Foundry auth). No
  dependency was added in Phase 0.

## Decisions log

- 2026-11-06: Phase 0 preset-digest fix excludes `archived`; content equality was proven against
  the pre-change `Bot` field set, so this is not a status change.
- 2026-11-06: Anthropic subscription OAuth stays out of Hutch. Only the official unmodified Claude
  Code CLI may be delegated to, with the user's own sign-in; no token import or proxy.
- 2026-11-06: Gemini CLI OAuth stays blocked (Google calls third-party use a terms violation).
  Google replaced Gemini CLI with Antigravity CLI on 2026-06-18; treat the `coding_cli` service
  claim as stale and decide in Phase 3c.
- 2026-11-06: The workspace is dark-only by product decision. The "light and dark" visual gate is
  scoped to the marketing site until a light theme is approved in Phase 7.
- 2026-11-06: Providers page live-evidence sentence is generated from evidence and statuses in
  Phase 1, not hand-maintained (G1).
- 2026-11-06: Route resolution never chooses an account when two or more could pay. An ambient key
  is labeled and never breaks the tie (D2, D3).
- 2026-11-06: A fallback or escalation from a subscription primary to per-token/credits is refused
  until the metered route is made primary. That configuration is the explicit consent (D4).
- 2026-11-06: Saved route specs are normalized to the provider prefix the runtime already used.
  The migration is additive in meaning: no spec, billing relationship or fallback order changes
  (D5, schema 91).
- 2026-11-06: A saved OAuth account has an explicit state (active, expired, revoked, missing). A
  refresh token is enough for active; expired/revoked accounts are not keys. A failed refresh keeps
  the stored credential (ADR-0029).
- 2026-11-06: ChatGPT sign-in stays loopback-only. Remote/headless hosts get an honest boundary and
  the API-key/official-CLI alternative; no undocumented device-code client is added. OpenCode owns
  its official OAuth/device flow.
- 2026-11-06: Revocation is reported as confirmed or unconfirmed; clearing local tokens is not the
  same act as provider-side revocation.
- 2026-11-06: Plan keys whose terms forbid unattended or unlisted third-party tools (Alibaba Cloud
  Coding Plan, Z.AI GLM Coding Plan) are `blocked` auth methods with cited vendor sources and no
  template (ADR-0032). Permitted third-party memberships (`kimi-coding`, `opencode-go`, `opencode-zen`)
  are separate catalogue identities with their own templates and env vars.
- 2026-11-06: Regional hosts use distinct templates and distinct environment variables so a region is
  never selected implicitly by a shared variable name.
- 2026-11-06: Claude Code CLI delegate and Codex native app-server runtime stay `documented`: each
  requires a governed executor contract (approvals, spend, cancellation, session isolation) larger
  than a 3-file task plus an interactive local CLI sign-in.

- 2026-11-06: Phase 4 ships no cloud request signer. Bedrock API keys (bearer) and Azure resource keys are plain
  header credentials, so both approved dependency families stay unused and no dependency was added. AWS IAM and
  SigV4 with the Converse event stream, Google service accounts (Gemini and Claude on Vertex) and Entra ID need a
  signer or token mint and an account to verify; they stay `documented` with the design in `05-HOSTED-AND-GATEWAYS.md`.
- 2026-11-06: A public model list is reachability evidence, never key evidence. Seven templates carry
  `models_list_ignores_key`; the check under-claims if a vendor later starts validating keys (ADR-0033).
- 2026-11-06: Cloudflare AI Gateway stays `documented`: account and gateway ids live in the URL, authentication
  needs a second header, and the vendor deprecated `/compat` for single-model chat (page updated 2026-11-04).
- 2026-11-06: Tencent Token Plan is blocked (forbids automated and non-interactive use). Volcengine and BytePlus
  Coding Plan are not offered: the vendor lists supported tools, Hutch is not listed, and no sentence permits
  unlisted tools.
- 2026-11-06: Gateways are their own identities; Vercel's BYOK fallback to Vercel credentials is an
  acknowledged notice, not a hint, because the payer can differ from the key's owner.
- 2026-11-06: Volcengine tool-schema trimming rests on one aggregator report and is not reproduced against an
  account; it is applied to the wire copy only and not extended to BytePlus.
- 2026-11-06: Endpoint policy decides on addresses, not spellings; `blocked` (link-local, metadata, unspecified,
  multicast, reserved) is refused for every scheme. A public-looking name that resolves privately is refused unless it
  is local-style or listed in `HUTCH_PRIVATE_HOSTS`; vendor hosts are exempt from the name rule (ADR-0034).
- 2026-11-06: Plain HTTP only to loopback/private; a key is never sent in clear text off loopback; redirects are not
  followed. Self-signed TLS stays refused (no skip switch); `SSL_CERT_FILE` is honored.
- 2026-11-06: Keyless named connections were not added: the keyless route already exists (`vllm/<model>` or
  `openai-compatible/<model>` with the bot's base URL) and is now guarded; a new auth mode would grow frozen
  `connections.py`, the CLI and the dashboard API without a safety gain.
- 2026-11-06: A custom endpoint's connection test is reported as not key-verified, because user-run servers answer
  their model list with any key or none (Ollama, LM Studio without a token).
- 2026-11-06: inferrs and ds4 get no template: no engine to verify and ds4 is Metal-only. They stay `documented` and
  reachable through the generic OpenAI-compatible route.

- 2026-11-06: Media routes are rows in a validated table driven by a `sync` and a `task` backend; a vendor whose wire is
  not read stays `documented` rather than being built on a guess (ADR-0036).
- 2026-11-06: OpenAI Sora 2 / Videos API (shut down 2026-09-24, no replacement) and the Google Veo preview models
  (2026-10-22) are `retired`; Gemini Omni Flash is `documented`, not built.
- 2026-11-06: A paid synchronous result is spooled before `submit` returns and released after the media store commits;
  recovery never pays twice. A task job needs only the ledger id.
- 2026-11-06: A refusal is a service status (`refused:` prefix over the store's five states) with the provider's
  reason, never retried and never a generic failure.
- 2026-11-06: With several capable backends `backend_for` refuses and names them. An ambient env key and a configured
  connection are two backends. Environment credentials are used only for vendors with no chat connection and are
  labeled ambient in the approval.
- 2026-11-06: Cost is a dated estimate with its basis or "cost unknown"; an unreadable price is never turned into a
  number. Estimates are recorded as `estimated`, unknown as `unpriced`.
- 2026-11-06: No automatic retry for any billable media call, including the SDK's defaults and Gemini TTS's empty 200.
- 2026-11-06: Job routes are absent from `REMOTE_ROUTE_CAPABILITIES`; paired phones are denied by default.
- 2026-11-06: Provider-native search for OpenAI, Google and xAI is documented, not built; the Xiaomi route and the
  `live_search` distinction are unchanged.
- 2026-11-06: ADR-0035 was already taken by the offline-models initiative running in the same repository, so this phase
  uses ADR-0036.

- 2026-11-06: The workspace stays dark-only (G16). A light theme is a product decision larger than Phase 7; the workspace
  visual gate is dark at four widths and the light/dark gate stays with the marketing site (ADR-0037).
- 2026-11-06: A route chip is never green. Green is a provider's own status for a dated live run; a route chip says built or
  not built, and a policy verdict ("allowed") is neutral.
- 2026-11-06: Filtering has one implementation (script) with the query string as state; the form is hidden without script and
  the full list is shown. Picker and jobs list fetch the server's own HTML and swap one element, so labels live in one place.
- 2026-11-06: The wizard acts through ConnectionBook in its own module because `pages.py` is frozen; only custom endpoints may
  set a base URL there, and sign-in templates are refused with a pointer to Apps & AI.
- 2026-11-06: First run and Models say "OpenCode is available with N model options ... None is saved as the default for new
  assistants yet." The earlier "ready" read as saved.
- 2026-11-06: axe-core 4.13.0 was read from another checkout on this machine for validation only; it is not a Hutch dependency
  and no dependency was added.


## Review findings log

- 2026-11-06, Phase 0, baseline test hashed lifecycle state (`archived`) as preset content; fixed
  by excluding it after proving content equality.
- 2026-11-06, Phase 0, `server/templates/providers.html:18` hardcodes obsolete live evidence and
  mislabels documented/blocked routes as implemented-unverified; queued for Phase 1.
- 2026-11-06, Phase 0, light and dark captures are identical because the theme is fixed; recorded
  as G16, not a capture failure.
- 2026-11-06, Phase 1, the first resolver draft imported the runtime registry at module load,
  creating a routing -> runtime -> builtin -> ladder -> routing cycle; the import is now lazy.
- 2026-11-06, Phase 1, `store.py` is frozen at its line cap, so the migration lives in
  `route_spec_schema.py` and is appended without growing the file.
- 2026-11-06, Phase 1, the surface test asserted the obsolete hardcoded banner; it now asserts the
  derived routes and status counts.
- 2026-11-06, Phase 1, the main design docs and ADR were not updated with the code in the first
  pass; corrected in the same series with ADR-0028 and the three design-doc updates.
- 2026-11-06, Phase 2, the real populated-state capture exposed a 500: a partial ChatGPT account
  record raised `KeyError` during model discovery. Fixed by requiring an active credential in
  `has_key` and reporting an incomplete record as a model-list error.
- 2026-11-06, Phase 2, `has_key` treated an expired ChatGPT access token as usable because it only
  checked plan scope; corrected to require an active credential.
- 2026-11-06, Phase 2, design docs initially lagged the code again; corrected in this series with
  ADR-0029 and four doc updates.
- 2026-11-06, Phase 3, `test_provider_routes.py` assumed every `ROUTES` entry owned a 1-tuple
  `connection_templates == (provider,)`; relaxed to `provider in row.connection_templates` when
  `moonshot-cn` and `zai-cn` were added.
- 2026-11-06, Phase 3, verified in `providers/connection.py` and `providers/claude.py` that
  `ClaudeProvider` forwards `conn.user_agent` (`hutch/<version>`) via `extra_headers` before claiming
  in the `kimi-coding` terms notice that Hutch sends its own `User-Agent`, and pinned that wire
  behavior in `test_flagship_routes.py`.

- 2026-11-06, Phase 4, the live run showed `connections test` reporting "authenticated" for seven hosts that
  ignore the key; fixed with a measured flag and tests that fail without it.
- 2026-11-06, Phase 4, the Models page printed "connection verified" for any `ok` check, including ones that
  verified nothing; fixed and covered by a real form-post test shown to fail without the fix.
- 2026-11-06, Phase 4, the first Models page test grepped source text; replaced by a real route test.
- 2026-11-06, Phase 4, long template titles wrapped and truncated in the rename field; shortened.
- 2026-11-06, Phase 4, `provider_for_connection` grew to 43 lines; the OpenAI chat construction moved to a helper.
- 2026-11-06, Phase 4, the seam and trimming tests were written in the same step as their code and not run red
  on their own; the honesty and Models page tests were run red first.
- 2026-11-06, Phase 5, the first Anthropic attempt injected an httpx transport; the SDK here is built on a vendored
  `httpx2`, so nine existing Claude tests failed with a type error. Replaced by a precheck, and the limit is recorded.
- 2026-11-06, Phase 5, the layered text replaced the server's own explanation of an HTTP 400 on the model list;
  `test_connection_secrets` caught it. The server's words are kept for explained HTTP errors, with a test that fails
  without the change.
- 2026-11-06, Phase 5, an existing test pinned "the key goes out exactly once"; the keyless `/api/version` request kept
  that property and the assertion now filters to key-bearing requests (intent unchanged, stated in the commit).
- 2026-11-06, Phase 5, a custom endpoint test said "authenticated" for servers that ignore keys; now under-claims.
- 2026-11-06, Phase 5, wording defects found by reading the live output: "set the endpoint to that" pointed at
  `/v1/models`; a literal blocked address read "resolves to" itself. Both fixed. A dead `LAYERS` constant was removed.
- 2026-11-06, Phase 5, the policy and transport tests were written in the same step as their code, not run red first;
  the one mutation tried (dropping the link-local check) was equivalent because `is_global` already blocks it, so it
  proves nothing; the honesty and word-keeping tests were each shown to fail without their change.
- 2026-11-06, Phase 5, another session's uncommitted edits to `ollama.py`, `openai_compat.py`, `runtime/outcomes.py`
  and two tests were present in the tree; none were staged or touched.

- 2026-11-06, Phase 6, the real-stack run showed `finalize()` returning a bare row on failure paths while callers unpack a
  tuple (pre-existing; a failed fetch raised ValueError in the tool). Fixed at the source with regression tests.
- 2026-11-06, Phase 6, the first downloader let `EndpointRefused` escape; the metadata-address test failed and it is now a
  `FetchError`.
- 2026-11-06, Phase 6, the first reconcile tests used the live service, which rightly skips jobs it drives; they now
  restart the service.
- 2026-11-06, Phase 6, own-diff review found: held results were never released or swept; a local "route cannot be
  filled" error claimed a billing risk; a lost race on `advance` reported a failure. All fixed with tests.
- 2026-11-06, Phase 6, releasing the held copy lost Xiaomi's measured tokens (read after release); the existing speech
  test caught it; usage is read before finalize and a resume-path test was added.
- 2026-11-06, Phase 6, a new catalogue note used the word "bearer" and tripped the secret-text scan; the note was reworded,
  not the test.
- 2026-11-06, Phase 6, one test I wrote asserted nothing (templates have no `models` key); removed.
- 2026-11-06, Phase 6, the route tests passed first time, so five mutations were run to prove they fail without the
  behavior; all five were caught.
- 2026-11-06, Phase 6, a concurrent session (offline-models Phase 7) committed to the same branch and regenerated the agent
  map; its uncommitted `modelview.py`, `models.html` and webhook files were never staged.

- 2026-11-06, Phase 7, the wizard forms rendered with fields about 200px apart: the base `.hutch-form` is a column, so my
  `flex: 1 1 220px` became a height. axe was green; the screenshot showed it.
- 2026-11-06, Phase 7, every provider page led with "No summary is recorded"; the green "built" chip read as "works"; the
  evidence table broke one word one letter per line; narrow-width CSS sat above the base rules it overrides. All fixed
  after looking at the screenshots, not from the checks.
- 2026-11-06, Phase 7, one shared `Query()` object bound the three picker parameters to the first name, so a typed model never
  arrived; a unit test written for it fails under the bug.
- 2026-11-06, Phase 7, own-diff review found a crafted POST for the sign-in template raised `KeyError` (HTTP 500), the test
  action did a network read on the event loop, and every detail page probed five loopback ports. All fixed with tests.
- 2026-11-06, Phase 7, my first assumption that the job routes need a CSRF token was wrong: they are guarded by the
  same-origin check. The script stopped sending an unused header and a test pins the real guard.
- 2026-11-06, Phase 7, a stated test count (125) in my own record was wrong (73); corrected after counting.
- 2026-11-06, Phase 7, `/tmp` was a full 12 GB tmpfs (10 GB in `/tmp/pytest-of-kevina`); nothing was deleted and all scratch went
  to `~/.hutch-tmp/provider-phase7`. Another session's uncommitted edits (Google image default and `resume.py`, route
  sharing, webhook files, `model-switcher.js`) were present and none was staged.


## Open items and deferred

- Claude CLI delegate and Codex native runtime remain `documented` (G4, G5); Grok OAuth and MiniMax
  Coding Plan OAuth remain `documented` pending vendor third-party terms and a Hutch-registered OAuth
  client (G7, G8).
- OpenAI, Anthropic and Google Gemini live checks are blocked only on exporting `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` into the shell environment.
- OpenCode Go unattended use needs vendor confirmation before leaving `experimental`.
- Out-of-scope providers are listed at the end of `00-GAP-AUDIT.md`.
- Phase 1 API only: the dashboard picker does not yet show the resolved tuple before the first send
  (Phase 7). The resolver is read-only and not persisted per run. (Closed in Phase 7: the route picker and the Models page show it.)
- Billing-crossing refusal covers subscription-to-metered only; a local/free primary falling back to
  a hosted route keeps the existing first-hosted approval path.
- Account identity is still the spec prefix; a separate Bot account field would change how saved
  routes are interpreted and is deferred.
- Phase 2 used synthetic account records: no live OpenAI SIWC sign-in, refresh or revocation was
  exercised. The route is eligibility-gated.
- Remote/WSL loopback sign-in is documented as unavailable, not implemented. OpenCode's official
  device/OAuth flow was not exercised interactively in this environment.
- Phase 4: AWS IAM/SigV4 and Converse, Vertex (Gemini and Claude), Entra ID, Cloudflare AI Gateway, Alibaba
  workspace endpoints, Step Plan, Volcengine/BytePlus Coding Plan, Qwen Token Plan remain `documented` or
  blocked. No Phase 4 route has a keyed call; OpenAI, Anthropic and Google Gemini remain the only providers with an
  owner credential, and none of them is a Phase 4 route.
- Phase 4: the Providers page repeats each account's "no local credential" detail and a near-identical next
  action (pre-existing duplicate copy); the page is 17,523 px tall at 1280 (G17). Both are Phase 7. (Partly closed in Phase 7: the next action is dropped when it restates the detail, and the page is 8,011 px at 1280 px, was 13,279.)
- Phase 4: whether Mistral's reasoning `high` with `temperature: 0` returns HTTP 400 was not tested; it is a
  recorded vendor quirk, not a Hutch rule.
- Phase 4: the two Tencent host spellings (`tencentmaas.com`, `tencentcloudmaas.com`) both answer HTTP 401;
  Hutch keeps the one in its recorded vendor source. Re-check when a Tencent account exists.
- Phase 5: vLLM and SGLang window reading, inferrs and ds4 are unverified or unbuilt for want of an engine; installing
  vLLM or SGLang needs the owner's approval and a GPU-class host. The `max_model_len` reading rests on vendor protocol
  docs and source, not a live server.
- Phase 5: private-address and `HUTCH_PRIVATE_HOSTS` paths are covered by real loopback sockets plus an injected
  resolver, not a LAN peer. An environment proxy defeats pinning (literals are still checked). The Anthropic SDK path
  is checked, not pinned, and the SDK follows redirects by default (pre-existing).
- Phase 5: `bot.base_url` is judged at the first call, not at save; no UI for `HUTCH_PRIVATE_HOSTS`; the
  layered test is not yet a dashboard surface of its own (Phase 7). A long flash notice renders as a heavy bold
  paragraph at 360 px (Phase 7).
- Phase 5: the generation ("test with one token") layer of the connectivity test remains the existing explicit probe;
  `connections test` makes no inference request.
- Phase 6: no route is live-verified. The owner said OpenAI, Anthropic and Google keys are provisioned, but the
  variables are unset in this shell (and so are xAI, MiniMax, fal, ElevenLabs, Deepgram, Runway, PixVerse). Next
  step per provider: export the key, agree the per-call cap (an image or a few hundred characters), run one request.
- Phase 6: Runway, MiniMax Hailuo and Google Gemini Omni Flash need their request and result pages read before a
  route is built. xAI image field names beyond model and prompt come from OpenClaw. Google's Interactions API has no
  documented way to stop Google keeping an interaction; none is sent.
- Phase 6: music, image editing through routes, streaming synthesis, mp3 output, voice cloning, image-to-video and
  provider-native search for OpenAI, Google and xAI are not built. The media store accepts wav audio only.
- Phase 6: the model of a route is data with no per-user override; a stale id is a data fix. The OpenAI guide and pricing
  page name different current image ids, so the default (`gpt-image-1-mini`) is a choice, not a verified fact.
- Phase 6: no page lists media jobs and a finished resumed job does not re-enter the conversation as a media block; the
  API exists for the Phase 7 frontend. (Closed in Phase 7: the Providers page lists open and finished jobs with check and cancel. Re-entry into the conversation is still open.)
- Phase 6: media-only vendors (fal, PixVerse, ElevenLabs, Deepgram) read one environment variable and are labeled
  ambient; there is no connection template or stored-key UI for them (frozen `connections.py`).
- Phase 6: no real ComfyUI server was available, and Comfy Cloud is not built.
- Phase 7: no light theme exists; the workspace gate is dark only (ADR-0037). Building one is a product choice for the owner.
- Phase 7: the wizard's connection test ran against a loopback stand-in only, never a vendor; a keyed test per provider is
  blocked on a credential and a per-call cap.
- Phase 7: Chromium only (no Firefox or WebKit), no Tauri desktop run, no screen-reader session; axe covers a subset of WCAG and
  the keyboard checks cover the filter, wizard, picker and job controls, not every control on every page.
- Phase 7: first run was covered by its existing browser tests and not re-captured at four widths; the process-level offline
  sandbox was not re-run (the picker shows the policy verdict).
- Phase 7: media-only vendors (fal, PixVerse, ElevenLabs, Deepgram) still have no stored-key form (no connection template; frozen
  `connections.py`); their page names the environment variable and calls it ambient.
- Phase 7: the layered endpoint test (Phase 5) is still not a dashboard surface of its own, and a long flash notice still renders
  as a heavy bold paragraph at 360 px; both are small follow-ups, not blockers for Phase 8.
- Phase 7: the Providers and Models pages now share `static/providers.css`; another session committed `models.html` changes
  earlier today and has uncommitted `hutch-pages.css` edits, so reconcile before Phase 8 touches either.
