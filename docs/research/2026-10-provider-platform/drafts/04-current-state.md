# 04 - Current-state inventory: provider, auth, runtime and media platform

Task: task-4, teammate repo-inventory. Read-only repository archaeology for the lead's
00-SCOPE.md through 07-ROLLOUT-AND-MIGRATION.md docs.
Read from the isolated worktree `/home/kevina/CodingProjects/hutch/.worktrees/provider-platform` at
HEAD 7ef8ba211787 (2026-10-30), which is one docs-only commit after 1c454c32 named in the handoff
(7ef8ba2 "docs(providers): establish research scope, plan and validation ledger"). At first read the
worktree had no source edits; by completion (22:56) other teammates had begun editing
src/hutch/connections.py and src/hutch/data/connections.json and added src/hutch/providers/accounts.py
(section 17). Read at 2026-10-30 22:51-22:56 America/Vancouver. No tests were run, no
live provider call was made, no vendor page was fetched, no code edited. All line numbers are for that
worktree HEAD, not for the separate main checkout (section 17).

## 1. Summary table (one row per provider/integration)

| Integration | Repo representation and declared state | Credential path | Code path | Live verified? | Main risk or gap |
|---|---|---|---|---|---|
| OpenAI API (Chat Completions) | compat route `openai-chat-completions`, supported, verified_on 2026-10-08 (data/compat.json:6-31) | OPENAI_API_KEY only to exact https://api.openai.com; custom endpoints need their own connection key (providers/registry.py:26,39-61) | OpenAICompatProvider (providers/openai_compat.py:47) | No live request; recorded HTTP fixtures only (C/F) | Matrix vision text stale versus 2026-10-23 image-input code; API-key route has no Responses adapter |
| Anthropic API (Messages) | compat route `anthropic-messages`, supported, verified_on 2026-10-08 (data/compat.json:33-58) | ANTHROPIC_API_KEY / connection key; ambient key restricted to official host | ClaudeProvider (providers/claude.py:109) | No live request; recorded SDK/HTTP fixtures only (C/F) | compat.json says no model-list operation, but claude.py implements and probes the paginated Models API |
| OpenRouter | No own route id; covered by `openai-compatible-connection`, supported, verified_on 2026-10-11 (data/compat.json:89-119); template `openrouter` | OPENROUTER_API_KEY or named-connection key file | OpenAICompatProvider(openrouter=True) via providers/connection.py:34; policy/pricing in providers/openrouter_policy.py, openrouter_pricing.py | Public unauthenticated catalog GETs checked 2026-10-11; no live account or generation (C/V) | Catalog price is informational; upstream routing can change the answering model |
| OpenCode Go plan | compat route `opencode-go-connection`, experimental, verified_on 2026-10-08 (data/compat.json:121-146); template `opencode-go` | Provider-issued API key pasted into a Hutch connection; explicitly not OAuth session reuse | OpenAI-compatible named connection; required User-Agent and session header (connections.py:71-99, providers/connection.py:24) | Offline fixtures only, no credentials (C/F) | Terms describe coding-agent traffic; unattended/scheduled eligibility not established |
| Sign in with ChatGPT (SIWC) | compat route `sign-in-with-chatgpt`, experimental, verified_on 2026-10-09 (data/compat.json:148-175); `chatgpt-plan` template hidden from generic add form (connections.py:247-252) | Local PKCE/OIDC account in state/chatgpt/accounts.json 0600; disabled unless HUTCH_ENABLE_CHATGPT_PLAN=1 (chatgpt_auth.py:44-46,105-144) | OpenAIResponsesProvider (providers/openai_responses.py:18) via providers/connection.py:25-30 | Local OAuth/signature/stream fixtures only; no OpenAI account (C) | Eligibility unconfirmed; no provider-enforced output cap; background runs need per-Bot consent |
| Xiaomi MiMo token plans (SGP/CN/AMS) and PAYG | Four templates only (data/connections.json); no compat route; source is docs.openclaw.ai (aggregator) | XIAOMI_TOKEN_PLAN_API_KEY / XIAOMI_API_KEY or stored key | openai-chat shape; some models also declare an anthropic base URL | Not exercised; data readme says no keys on the dev machine (C) | Weakest-evidence connection family; credits not tokens; terms page not machine-readable |
| Custom OpenAI-compatible endpoint | compat route `openai-compatible-connection`, supported, verified_on 2026-10-11 (data/compat.json:89-119); template `custom-openai` | HUTCH_API_KEY, or connection key; never OPENAI_API_KEY (registry.py:263-273) | OpenAICompatProvider | Scripted fixtures only (C/F) | Dialect-specific fields omitted; no context/capability evidence for custom servers |
| Custom Anthropic-compatible endpoint | template `custom-anthropic`, models_endpoint false; no compat route id | connection key | ClaudeProvider | Fixture only (C) | Key-presence check only; no catalog, no live |
| Ollama native | compat route `ollama-native`, supported, verified_on 2026-10-08 (data/compat.json:61-87) | none (local); cloud-tagged names treated as hosted (providers/pricing.py:21-29) | OllamaProvider (providers/ollama.py:90); port-11434 compatible URL rerouted native (registry.py:252-254) | Fixtures/scripted fake server; no local model on dev machine (C/A) | num_ctx must be sent explicitly; fit is estimated |
| LM Studio, llama.cpp, vLLM | No compat rows; PRESET_URLS providers/openai_compat.py:25-31; LOCAL_PROVIDERS providers/pricing.py:21 | HUTCH_API_KEY optional for a custom base URL | OpenAICompatProvider | Fixtures only (F) | Three runtimes collapse into one generic wire route; matrix does not represent them |
| OpenCode assistant runtime | Runtime runtime/opencode.py:211 plus owned server runtime/opencode_server.py:97; host capability external_runtimes experimental on Linux (server/app.py:3047-3054); compat route `opencode-harness` still says unavailable (data/compat.json:177-201) | Private OpenCode profile; optional transfer of an existing local API key (runtime/opencode_login.py:79-97); needs installed CLI major version 2 (opencode_server.py:152-160) | OpenCodeRuntime; loopback `opencode serve` with per-start password (opencode_server.py:140-190) | 61 fixture-level tests in 6 files; no live model request (F/U) | Docs and data contradict each other (section 14); OpenCode tools run with user OS authority after approval |
| OpenCode CLI coding handoff | Documented experimental Linux feature (docs/realignment/provider-compatibility.md:28); code_handoff.py; API server/app.py:4090-4147; CLI cli.py:97-127 | Owner signs in to OpenCode CLI in a private Hutch profile; Hutch does not import those credentials | Interactive `opencode` child process in a detached worktree (code_handoff.py:37-105,492-521) | Launch and cleanup not live-tested (C) | Hutch does not meter its provider requests or broker its prompts |
| Pi executor | compat route `pi-harness`, unavailable, verified_on 2026-10-09 (data/compat.json:203-227); runtime/pi.py:20-38 raises before any process | none accepted | PiRuntime abort | Protocol fixtures only (C/F) | Fail-closed by design: no per-action approval hook, no usage reservation |
| Consumer-plan OAuth/session reuse | compat route `consumer-plan-oauth`, blocked, verified_on 2026-10-08 (data/compat.json:229-253) | none | none | Static policy (C) | Blocked by design; no cookie/session proxy |
| Google Calendar, Gmail, Outlook Calendar/Mail | Experimental account integrations, separate from model providers (docs/realignment/provider-compatibility.md:32-41) | Publisher/operator OAuth client IDs (oauth_apps.py, google_oauth_config.py) plus per-feature PKCE and Linux Secret Service | google_calendar.py:92, google_mail*.py, outlook_calendar.py:60, outlook_mail*.py | Fixture-level only; no live consent (C) | Not model routing; secret-store portability gap outside Linux |
| Media: OpenAI Images | No compat row; media/providers/openai_images.py self-tagged protocol-verified, live-unverified (media/providers/base.py:26) | OPENAI_API_KEY read by OpenAIImagesBackend.from_env (openai_images.py:174-179) | OpenAIImagesBackend behind MediaJobService | In-process fake transport only (F) | Not connected to Connections or the usage/reservation ledger; cost unknown to Hutch |
| Media: ComfyUI | No compat row; media/providers/comfyui.py, same tag | HUTCH_COMFYUI_URL (comfyui.py:157-161) | ComfyUIBackend behind MediaJobService | httpx.MockTransport only (F) | Caller supplies workflow graph; no live server check |
| Grounding adapters | GDELT, RSS/Atom, Hacker News, SearXNG, Bluesky, Jetstream and Wikimedia streams (grounding/acquire.py, grounding/streams.py); no compat/Connections entry | no user credential; state/grounding.json config (acquire.py:81-103) | tools `live_search` and `inspect_media` (tools/__init__.py:103) | Code docstring says GDELT/feeds/HN verified live, Bluesky blocked from current network (acquire.py:21-22); not re-tested here (C/U) | Separate configuration plane; no UI, no per-adapter connection object |

## 2. Evidence grades and the verification boundary

| Grade | Meaning |
|---|---|
| R | Read from the local source at the cited path:line in the worktree on 2026-10-30. Behaviour inferred from code; not executed. |
| C | Claim in repository docs presented as fact; the doc's own review date is given where known. Not reproduced here. |
| F | Repository docstring or test-file name claims fixture coverage. The suite was not run, so this is name-level only. |
| V | Vendor-documented per a URL embedded in repository data/docs with an observed_on date. Not fetched in this session. |
| A | Anecdotal/report-based research inside the repo (reviews, issue reports, single-user comments). |
| U | UNVERIFIED in this session; needs a later check. |

Two distinctions for the lead's docs:

1. "Endpoint listed in docs or data" is not "Hutch verified live". The strongest published state,
   `supported` in data/compat.json, means "recorded fixtures exist"; every route text also says no live request
   was made. Media adapters self-describe as "protocol-verified, live-unverified".
2. No vendor page was fetched here. Vendor URLs and their observation dates below are reproduced from the
   repository artifacts that cite them, so those dates are the repo's recorded dates, not my fetch date.

## 3. Provider-by-provider notes

### 3.1 OpenAI API key
- openai-chat adapter sends `max_completion_tokens` only for the exact official OpenAI authority or OpenRouter;
  other compatible endpoints get max_tokens (providers/openai_compat.py:59-64,307-309).
- Official-host check rejects lookalike hosts, userinfo, HTTP and nonstandard ports (registry.py:39-49);
  tests/test_compat.py:86 names a parametrized rejection test (F).
- Matrix "omitted" list (reasoning_effort, response_format, num_ctx) matches the default adapter path
  (data/compat.json:5-31; C/F). A constrained tool protocol can attach response_format elsewhere.
- Vision text is stale: image input landed 2026-10-23 (commit dcc85e85 "Add capability-gated chat image input to
  admission and runtimes"), wired at runtime/builtin.py:365-410,1213-1222, server/app.py:3652-3717 and
  providers/attachments.py; OpenAI vision model table at providers/openai_compat.py:37-64. UI exposure is U.
- No Responses API adapter for a plain OpenAI API key; Responses exists only for SIWC.

### 3.2 Anthropic API key
- ClaudeProvider (providers/claude.py:109) disables SDK internal retries, maps typed errors, and implements
  list_models/probe_models against the Models API: limit 1000, after_id cursor, ten pages (claude.py:158-195).
- Contradiction C1: data/compat.json:39 says "The Anthropic API has no common model-list operation in Hutch's
  connection contract", while the adapter lists models and connections.json marks anthropic-api models_endpoint
  true. The matrix is stale relative to code.
- Request mapping: max_tokens, messages, tools, streaming, output_config.effort only for allowlisted models;
  temperature/thinking omitted so model defaults apply (data/compat.json; C/F).

### 3.3 OpenRouter
- Not a separate adapter: the `openrouter` template sets openai-chat plus an openrouter flag
  (providers/connection.py:31-34). OpenRouter-specific code is providers/openrouter_policy.py (42 lines) and
  providers/openrouter_pricing.py (482 lines).
- Catalog discovery only on explicit model-menu open: popular limit 40, search limit 80, query max 80
  (modelchoices.py:36-38,216-239); advertised context windows cached in-process with 60 s TTL, never fetched on
  the run path (modelchoices.py:41-64,94-107).
- Published catalog price is informational; receipts must use returned model identity and recorded usage
  (docs/realignment/provider-compatibility.md:21; data/compat.json; C).

### 3.4 OpenCode Go plan
- Named-connection template only; paste an issued API key. Template declares `x-opencode-session` header, own
  User-Agent, terms acknowledgement, and a per-model protocol hint (OpenAI chat for most, Anthropic for some,
  Responses not implemented) (data/connections.json).
- Code enforces generic connection invariants only; per-model protocol is manual via
  `hutch connections set-protocol` (cli.py:1437-1447). Nothing validates the hint against responses.
- Matrix date 2026-10-08; no live plan call. General/unattended eligibility explicitly unestablished
  (data/compat.json:121-146; C).

### 3.5 Sign in with ChatGPT (SIWC)
- Opt-in local OAuth: PKCE callback, ID-token/JWKS verification, account registration, refresh, disconnect
  (chatgpt_auth.py:105-519; routes server/app.py:7011-7071). Accounts stored atomically 0600 in
  state/chatgpt/accounts.json (chatgpt_auth.py:80-144); pending logins in the state/chatgpt subtree; accounts()
  returns safe rows only (chatgpt_auth.py:394-404).
- Route fixed to OpenAI Responses at https://api.openai.com/v1; ConnectionBook refuses any other template or
  base URL for that protocol (connections.py:178-193). Access token refreshed on demand (chatgpt_auth.py:414-456).
- Scheduled/background use needs a separate per-Bot, per-account express grant: BackgroundProviderConsent
  (models.py:265-274); PUT/DELETE consent routes server/app.py:3204-3237; disconnect revokes and removes
  (server/app.py:7024-7040; pages.py:583-598). Each provider request rechecks grant (docs; C/F).
- Preview limit: no provider-enforced output token cap (data/connections.json template;
  output_token_limit_enforced false). Local allowances are estimates.

### 3.6 Xiaomi plans, custom endpoints, local runtimes
- Xiaomi: four templates (three regional Token Plans plus PAYG), credits billed by Xiaomi, one env var per family;
  readme says the terms page was not machine-readable and the source is a docs aggregator
  (data/connections.json). No route fixture.
- custom-openai: openai-chat, models_endpoint true. custom-anthropic: anthropic, models_endpoint false.
  Endpoint validation rejects embedded credentials and non-loopback plain HTTP (connections.py:150-173).
- Local runtimes: Ollama native is the only dedicated local wire adapter; LM Studio/llama.cpp/vLLM use
  PRESET_URLS (openai_compat.py:25-31) and OpenAICompatProvider. is_local covers
  {ollama, lmstudio, llamacpp, llama.cpp, vllm} (pricing.py:21-29); Ollama cloud tags are hosted. A compatible
  URL on port 11434 is rerouted to the native provider so num_ctx can be set (registry.py:6-7,252-254).

### 3.7 OpenCode assistant runtime and credentials
- runtime/opencode.py:1-15: owns a private `opencode serve` process, uses the durable message endpoint instead
  of the volatile event stream, brokers every permission as once/reject, records provider token/cost totals
  against a usage reservation, fails closed.
- Server: loopback port, random OPENCODE_SERVER_PASSWORD env, requires CLI major version 2, disables share,
  background warming and automatic compaction, verifies maintenance controls before a paid prompt
  (opencode_server.py:97-260).
- Server lifecycle owned by server/app.py:1994-2029; status/setup endpoints server/app.py:7182-7243.
- Local login reuse: runtime/opencode_login.py reads XDG_DATA_HOME/opencode/auth.json with O_NOFOLLOW, ownership
  and 0600 checks, exposes only provider id + reusability, transfers only `type == "api"` keys through the owned
  server; OAuth sessions must re-sign-in (opencode_login.py:1-5,23-76,79-97). Strongest "CLI credential
  legitimacy" story in the repo.

### 3.8 Coding handoff, Pi, consumer OAuth
- Coding handoff creates a durable reviewed record and detached worktree pinned to the saved commit, refreshes a
  private profile config, refuses project-local plugins, and gives the task agent a 20-step ceiling
  (code_handoff.py:1-7,149-205,391-521; C). It is explicitly not the runtime: Hutch does not meter OpenCode's
  requests, broker its prompts, or sandbox approved commands (provider-compatibility.md:28; C).
- Pi fails closed (runtime/pi.py:20-38); get_runtime builds it for a persisted legacy bot but execute raises
  (runtime/__init__.py:18-19).
- Consumer OAuth/session reuse is blocked by design (connections.py:21-24; data/compat.json:229-253).

### 3.9 Account integrations and media/grounding providers
- Google Calendar/Gmail/Outlook are account integrations, not model providers; all experimental and
  fixture-only per provider-compatibility.md:32-41.
- Publisher client IDs are public-only release inputs: only `version` and `apps.<provider>.client_id` are
  accepted; no client secret/token fields (oauth_apps.py:19-46). Google resolution order is env
  HUTCH_GOOGLE_OAUTH_CLIENT_ID, then store kv connections:google_oauth_client_id, then distribution file
  (google_oauth_config.py:12-32). Outlook: env HUTCH_OUTLOOK_OAUTH_CLIENT_ID then publisher file
  (oauth_apps.py:61-62).
- Linux secret storage is two separate SecretToolStore classes (google_calendar.py:92, outlook_calendar.py:60);
  platforms/credentials.py covers native Windows/macOS keyring only and its docstring says Linux keeps the
  existing secret-tool transport (platforms/credentials.py:1-5,19-59).
- Media and grounding providers are separate planes (sections 12 and 13), not Connections entries.

## 4. Route syntax, model specs and provider construction

There is no single provider registry; a route is a string with a slash and construction is spread across modules.

- Tolerant parser: providers/registry.py:64-68 `parse_spec` partitions on the first "/" and defaults a
  slashless spec to ("openai-compatible", spec). Used by runtime/ladder.py:66-69 and call sites.
- Strict validator: registry.py:75-80 `validate_spec` requires a lowercase provider slug and a bounded model id
  allowing further slashes (OpenRouter ids). Error: "expected an explicit 'provider/model' spec".
- Bot model fields: models.py:378-435. `model` default "" (models.py:384), `base_url` (:385), `runtime`
  (:386), `inference_mode` (:387), `fallbacks` (:427), `escalation` (:428), `task_routes` (:429),
  `num_ctx` (:435). Run records `model_used` (may differ after fallback/escalation, models.py:627) and
  `model_override` (per-message picker choice, bot unchanged, models.py:639).
- Unusable-route shape rules live separately: route_problem.py:23-48 (no route, missing parts, mock, OpenCode
  three-part route, OpenCode route on builtin runtime). `route_problem(bot)` is the read-only roster/composer
  answer; legacy markers are route_problem.py:20 and run_is_legacy :51-62.
- Send-time validation: modelchoices.validate_override (modelchoices.py:357-427) raises ModelNotUsable with a fix
  string: slash form, mock refusal, OpenCode `opencode/provider/model` only, local/offline policy,
  strict-offline endpoint, runtime/model agreement (only the builtin runtime may pick its own route here),
  connection key/terms, KNOWN_PROVIDERS membership, ambient key presence.
- Runtime selection: runtime/__init__.py:16-26 returns PiRuntime for RuntimeKind.pi, OpenCodeRuntime for
  RuntimeKind.opencode, refuses mock, refuses empty route, else BuiltinRuntime. Engine calls get_runtime in the
  run path and converts RuntimeUnavailable into a failed run (engine.py:937-948; more builtin-only restrictions
  at engine.py:164-165,283-284,304-305,631-632,697-698,718-719).
- Provider construction has two paths:
  - ambient/built-in: runtime/ladder.py:34-46 `get_provider` caches by (provider, base_url, digest of relevant
    ambient env) so rotated keys do not reuse a client; registry.make_provider builds Ollama/Anthropic/
    OpenAI-compatible/preset adapters (registry.py:249-279), ambient OPENAI/ANTHROPIC keys allowed only on exact
    official hosts (registry.py:26,39-61).
  - connection: providers/connection.py:11-39 `provider_for_connection` resolves per-model endpoint
    (Connection.endpoint_for, connections.py:100-105), key via book.key, headers (User-Agent + template headers),
    then OpenAIResponsesProvider / OpenAICompatProvider / ClaudeProvider. Unknown protocol and non-Responses SIWC
    are refused.
- Provider contract: providers/base.py:26-64 typed ProviderError with kinds and retry/streaming classification;
  ChatRequest fields include num_ctx, max_tokens, temperature, think, effort, structured_output, session_id,
  cancel hooks (base.py:67-166); ChatResult/ToolCall/ModelMeta/Health (base.py:166-234); Provider ABC with
  chat/data_stays_local/supports_vision/health/list_models/show (base.py:324-371). Four chat adapters:
  openai_compat.py:47, claude.py:109, ollama.py:90, openai_responses.py:18; helper modules providers/images.py
  (observation/vision payloads) and providers/attachments.py (user image attachments).

## 5. Compatibility matrix and connection-template data

### 5.1 Matrix schema (data/compat.json + src/hutch/compat.py)
- Bundled JSON version 1, reviewed_on 2026-10-10, nine routes (data/compat.json:1-253). Required route fields are
  enforced: id, title, state, harness, api_shape, auth_flow, models, streaming, tool_calls, structured_output,
  vision, context_limits, cancellation, usage_reporting, quota_reporting, retention,
  hutch_request_mapping{sent,omitted}, verification, verified_on, policy_evidence (compat.py:13-18).
- States allowed: supported | experimental | unavailable | blocked (compat.py:13). Validation also requires
  unique ids, ISO dates, non-empty HTTPS evidence with no userinfo (compat.py:32-78).
- Exposed as GET /api/v1/compatibility with typed pydantic resources (server/app.py:1189-1230,3057-3061).
- Validation never checks that route ids/claims correspond to adapters, templates or code. A stale matrix passes
  as long as shape/dates are well formed. No evidence-tier enum exists (vendor-documented vs fixture vs live).
- Current inventory:

| id | state | verified_on | harness |
|---|---|---|---|
| openai-chat-completions | supported | 2026-10-08 | Hutch builtin runtime |
| anthropic-messages | supported | 2026-10-08 | Hutch builtin runtime |
| ollama-native | supported | 2026-10-08 | Hutch builtin runtime |
| openai-compatible-connection | supported | 2026-10-11 | Hutch builtin runtime |
| opencode-go-connection | experimental | 2026-10-08 | builtin via named connection |
| sign-in-with-chatgpt | experimental | 2026-10-09 | builtin, opt-in local sign-in |
| opencode-harness | unavailable | 2026-10-09 | "OpenCode is never launched by Hutch" |
| pi-harness | unavailable | 2026-10-09 | "Pi is never launched by Hutch" |
| consumer-plan-oauth | blocked | 2026-10-08 | not accepted |

### 5.2 Connection templates (data/connections.json + connections.py)
- 11 templates: opencode-go, openai-api, anthropic-api, chatgpt-plan, xiaomi-token-plan-sgp,
  xiaomi-token-plan-cn, xiaomi-token-plan-ams, xiaomi, openrouter, custom-openai, custom-anthropic.
- Template fields consumed by code: title, protocol, base_url, anthropic_base_url, api_key_env, billing,
  session_header, get_key_url, signin_guidance, source, models_endpoint, terms{url,requires_ack,notice},
  quota_hint, model_protocol_hint, quick_setup, provider_mark, setup_description, auth_type, auth_account_id,
  output_token_limit_enforced, prefer_stored_key, model_protocols, headers, account_id, caps
  (connections.py:71-235).
- Evidence line in the file: "Everything here was read from the vendor's own docs or a docs aggregator on
  2026-10-07 ... nothing was exercised against a live account" (data/connections.json:2). No per-row fetched_at;
  `source` is a bare URL. Xiaomi rows cite docs.openclaw.ai (aggregator, not vendor).
- Validation is per-connection construction (ConnectionBook._build, connections.py:150-235): endpoint scheme/URL,
  protocol allowlist, SIWC-only Responses, billing enum, account slug, cost/quota bounds, per-model protocol
  allowlist, OpenRouter policy only for OpenRouter. Invalid rows are collected in book.errors and skipped
  (connections.py:136-148); they do not fail the app.

## 6. Credential resolution (five distinct mechanisms)

| Mechanism | Where | Notes |
|---|---|---|
| Ambient env key, host-scoped | providers/registry.py:23-61 | OPENAI_API_KEY / ANTHROPIC_API_KEY only for exact official HTTPS host/port; lookalikes, userinfo, HTTP rejected. A wrong endpoint yields withheld-key hint and sends no key. |
| Named-connection key | connections.py:273-327 | Environment variable first unless prefer_stored_key, then 0600 file state/keys/<name>.key written by set_key (connections.py:345-358, chmod 0600, never returned by API). key_source reports which source. |
| SIWC OAuth account | chatgpt_auth.py; connections.py:283-288,319-321 | ChatGPTAuthBook.access_token refreshes the protected account token; has_key checks plan-use permission without network. Flag default off. |
| Local OpenCode API login | runtime/opencode_login.py:63-97 | Reads XDG opencode auth.json under strict file checks; only API-type keys reusable, only via owned server connect_key; OAuth requires fresh sign-in. |
| Account-OAuth books (Google/Microsoft) | oauth_apps.py, google_oauth_config.py, google_calendar.py:92, outlook_calendar.py:60, platforms/credentials.py | Public client IDs only in repo; refresh tokens in OS secret stores (Linux secret-tool for calendar/mail; native keyring helper for Windows/macOS only). Per-feature layouts, not unified. |

- API key ingestion: POST /api/connections/{name}/{action} set-key validates empty and 4 KiB max, stores with
  prefer_stored=True, never echoes (server/app.py:7117-7181). Legacy form path pages.py:611-667 does the same with
  CSRF tokens in templates/connections.html.
- Redaction: handlers replace the stored key in provider error text with [redacted] (server/app.py:7110-7114);
  tests/test_connection_secrets.py:12 asserts it (F).
- No unified credential service: model connections, SIWC accounts, Google books, Outlook books and OpenCode local
  logins each have a distinct file or secret-store namespace. Calendar/mail secret storage is effectively
  Linux-only; platforms/credentials.py:19-20 covers only win32/darwin.

## 7. Connections store and mutation

- Location: <state dir>/connections.json plus <state dir>/keys/<name>.key (connections.py:122-132). No SQLite
  table; the database stores usage/reservations, grants, consent and ack kvs (for example connection_ack:<name>,
  connections.py:432-448).
- Load/validate: ConnectionBook.__init__ reads JSON, merges template defaults per row, validates; errors kept in
  book.errors (connections.py:122-148). Writes are atomic tmp + os.replace (connections.py:237-243).
- No schema version on connections.json; unknown row keys are merged into the Connection build and may be
  silently ignored. State-drift risk for a future platform.
- Mutations: add/update/set_model_protocol/set_quota/remove/set_key/clear_key/acknowledge
  (connections.py:345-448). Built-in provider names are reserved (connections.py:44-45,377-378).
- CLI: `hutch connections` list/templates/add/set-key/ack/test/set-protocol/set-allowance/set-account-cap/remove
  around cli.py:1294-1490 (templates :1300, list :1316, add :1349, set-key :1382, ack :1401, test :1419,
  set-protocol :1437, set-allowance :1449, set-account-cap :1461, remove :1477).
- API: GET /api/v1/connections typed rows with usage/cost/terms/key source (server/app.py:3126-3152);
  GET /api/connections SPA JSON adds templates, SIWC accounts, Google/Microsoft books and errors
  (server/app.py:6029-6108); POST /api/connections/{name}/{action} (server/app.py:7117-7181).
- Terms: notice digest is sha256[:12]; ack stored in kv; stale when notice changes
  (connections.py:49-57,432-448). Unacknowledged terms show as setup in the picker (modelchoices.py:262-263) and
  are refused by validate_override (modelchoices.py:416-418).

## 8. Capability representations (four layers plus one evidence table)

1. Static route matrix: data/compat.json (section 5). Free text per axis; no evidence-tier enum.
2. Provider/tool capability profiles: toolcalling/profiles.py:36 evidence states documented, advertised, probed,
   observed, stale, unsupported, unknown; ModelCapabilityProfile fields include native_tools, tool_choice,
   parallel_calls, streaming_calls, constrained_schema, strict_tool_schema, multimodal, revision, backend
   (profiles.py:59-100). resolve_profile (:325) resolves from provider, endpoint class, protocol, model and
   optional revision; strategy_eligibility (:423) gates native/constrained/prompt strategies.
3. Host capability snapshot: GET /api/v1/capabilities returns host features (cross-process wake, process executor,
   strict shell, strict offline, remote pairing, trusted proxy, phone control, browser handoff, external runtimes)
   with status/reason/verification (server/app.py:2999-3056). Not a provider matrix.
4. Model capability observations: SQLite table model_capability_observations created by migration 37
   (store.py:1079-1105), one immutable positive function-tool-call observation per provider/account/model/route
   revision, exposed at GET /api/v1/model-capabilities (server/app.py:3062-3072; resources :1229-1245). Passive:
   it makes no extra model request; no negative observations and no expiry.
5. Bot-level tool profile: builtin._resolve_tool_profile (runtime/builtin.py:698-726) and
   GET /api/v1/tool-compatibility?ref= (server/app.py:3073-3125), which builds a profile from the bot's primary
   rung, endpoint, model and up to 20 stored observations, then reports strategy eligibility.

Gap: the three vocabularies (compat states, profile evidence states, observation rows) do not join. A provider
platform needs one capability vocabulary with an explicit evidence source.

## 9. Runtime architecture and boundaries

- Interface: AgentRuntime protocol execute(run, ctx, tools, stop) (runtime/base.py:21-34); RunAborted carries
  reason/detail/continuation (runtime/base.py:11-19).
- builtin: BuiltinRuntime (runtime/builtin.py:158), loop entry execute (builtin.py:1130-1903). Owns provider
  attempt, fallback/escalation via runtime/ladder.py (SpendGuard), usage reservations, approval-gated tool
  dispatch, transcript/event mirroring, image staging (builtin.py:365-410,1213-1222), context fit loop
  (runtime/fitloop.py), tool repair (runtime/toolrepair.py), step accounting (runtime/steps.py). Only runtime that
  reserves provider usage before a call.
- opencode: OpenCodeRuntime (runtime/opencode.py:211; execute :452-719) starts the owned server, resolves the
  explicit opencode/provider/model route (:46-57), maps OpenCode tools to Hutch tools, brokers every permission
  through approvals (never `always`, :327-376), reserves/records usage, fails closed on uncertainty
  (:1-15). Boundary: OpenCode's own tools run with the user's OS authority after approval; they are not inside
  Hutch's built-in shell sandbox (provider-compatibility.md:24; C).
- coding handoff: code_handoff.py as in 3.8; the API only records an immutable review, launching happens from
  `hutch code run` in an interactive terminal (docs/architecture.md:100-103; cli.py:117-127).
- pi: fail-closed (runtime/pi.py:20-38).
- Engine dispatch: get_runtime at engine.py:946 with RuntimeUnavailable handling engine.py:937-948; several engine
  features are builtin-only (live response preview engine.py:164-165, dynamic workflows :283-284, tool-free
  purposes :304-305,:937-938, persona preview :631-632, delegated execution :718-719).
- Runtime boundary is enforced by string checks on bot.runtime in engine/modelchoices/routes; there is no runtime
  capability registry, so a new runtime needs edits in several modules.

## 10. Model picker data and API

- Builder: modelchoices.model_choices(config, store, bot, hw, provider, *, discover_hosted_models,
  model_query) -> list[Choice] (modelchoices.py:302-354). Choice fields: spec, label, group, state
  (ready|setup|wont_fit), note, fix, default, hosted, worst_case_usd, detail, catalog_search
  (modelchoices.py:67-79).
- Entry sources:
  - bot's own model first unless route is unusable (modelchoices.py:319-327; route_problem import :28);
  - installed Ollama models with fit estimate (modelchoices.py:119-142), requires Ollama reachable;
  - hosted env-key price rows for anthropic/openai from PriceBook prices.json (modelchoices.py:145-160);
  - OpenCode models by starting the owned server, only when bot.runtime is opencode and discovery is allowed
    (modelchoices.py:163-194,328-330);
  - configured connections: SIWC account catalog, OpenRouter catalog/search, or generic list_models; key/terms
    state and per-row notes (modelchoices.py:197-292);
  - known specs harvested from bots and usage history (modelchoices.py:311-315);
  - local/offline inference_mode filters non-local routes (modelchoices.py:328,335-336).
- Advertised context windows are cached in-process only, keyed by connection/endpoint/key hash/model, 60 s catalog
  TTL, and never fetched on the run path (modelchoices.py:41-64,94-107,216-235); the code comment cites
  tests/test_model_switcher.py:184 for that discipline.
- Validation: validate_override (modelchoices.py:357-427) as in section 4.
- API:
  - GET /api/v1/model-routes (inference_mode, runtime literal builtin|opencode) returns choices for setup without
    creating a bot or run (server/app.py:4016-4028);
  - GET /api/bots/{ref}/models?discover=&q= returns {"default", "models"}; catalogs are queried only when
    discover is true (server/app.py:4951-4961);
  - GET/PUT /api/v1/preferences/model-defaults for the default that seeds new bots (server/app.py:4029-4059;
    routes.workspace_default is the single parser, server/pages_models.py:19-21);
  - /models page (server/pages_models.py:26-27) plus static/model-switcher.js for the composer picker (data
    comes from GET /api/bots/<name>/models, model-switcher.js:6; calls :243,:460).
- /api/bots/{ref}/models does not pass any "any runtime" flag; OpenCode entries appear only for an OpenCode bot.
  /api/v1/model-routes accepts runtime as a created draft bot's runtime.
- The picker deliberately makes no capability claim: tool support is only stored evidence (section 8), and the
  compatibility matrix is not surfaced there.

## 11. Connections UI surfaces

- SPA shell static/index.html plus static/app.js: hash route #/connections renders Apps & AI (app.js:1904
  route, renderConnections app.js:9347), fetches GET /api/connections (app.js:9353), then model-capabilities
  (limit 5) and /bots (app.js:9357-9361). Account-provider state (Google/Microsoft/SIWC, grants, errors) comes in
  that one JSON payload. Palette entry "Apps & AI" (static/palette.js:95).
- Server-rendered legacy page: GET /connections redirects 302 to /#/connections (pages.py:553-557);
  GET /legacy/connections renders templates/connections.html (pages.py:559-567; template 158 lines) with
  conn_views computed at pages.py:532-552 (key source, ack, measured+reserved usage, daily/cost cap, allowance
  meter). Legacy POST /connections/add and /connections/{name}/{action} handlers at pages.py:599-667.
- /models page remains for local fit, prices, test and delete; add is a redirect to Apps & AI
  (server/pages_models.py:76-108; decorators :26,:34,:61,:70,:76,:104,:110). Default model moves to Settings
  (pages_models.py:70-74).
- The SPA files are large and hand-written (static/app.js 14,273 lines, baseline 14,532); any provider UI work
  lands inside that bundle, not a component tree.

## 12. Media subsystem

- Package exports jobs/render/storage/validate (media/__init__.py:1-38).
- Job state machine: MediaJobService (media/jobs.py:109-592) over store media_jobs rows. Caller vocabulary
  submitting/running/succeeded/failed/cancelled/cancel_unconfirmed maps to the five store statuses;
  cancel_unconfirmed stays honest (media/jobs.py:1-45,81-89). submit is the only billable call and runs once per
  idempotency key; upstream id recorded immediately; finalize consumes expiring URLs and stores only validated
  bytes; reconcile marks orphans; no generic retry (jobs.py:46-58,183-238,240-265,267-318,320-418,430-501,503-582).
- Storage: MediaStorage (media/storage.py:151-547), content-addressed version dirs, staging/commit, reads
  re-verify size + SHA-256 (storage.py:180-229,421-486); formats png/jpeg/webp/svg+xml/webm/mp4/wav (:44);
  MAX_MEDIA_BYTES 96,000,000 (:69); MAX_MEDIA_PER_JOB 8 (:72); reconcile_media_store (:499).
- Validation: magic-byte sniff, dimensions, SVG sanitization (reject script/handlers/external refs/foreignObject/
  DOCTYPE; 8 MB text cap :35; 20,000 element cap :38), JPEG EXIF scrub allowlist (media/validate.py:1-52,
  :235-331,:391-469); validate_media :469.
- Providers: protocol MediaBackend with capabilities/submit/poll/fetch/cancel (media/providers/base.py:26-63),
  each tagged "protocol-verified, live-unverified" (:26). Adapters: OpenAIImagesBackend (synchronous Images API;
  the charge happens inside submit; from_env OPENAI_API_KEY, openai_images.py:1-20,174-179) and ComfyUIBackend
  (prompt/history/view/interrupt; from_env HUTCH_COMFYUI_URL, comfyui.py:1-20,157-161).
- Render: deterministic flowchart SVG and animation, ffmpeg WebM assembly (media/render.py:303,431,500,531,536).
- Serving: build_media_router mounted at server/app.py:5569; GET /api/v1/media/{id}/versions/{version}/content
  re-verifies hash at serve time with ETag/immutable cache/Range support; poster route likewise
  (media/routes.py:34-103). 410 for corrupted stored bytes. media_jobs table created by migration 54
  (store.py:1850-1896; table :1868).
- Tools: render_diagram (deterministic, effect ""), create_media (outward, billable, ask-by-default with
  outward=True, cost unknown; refuses instead of substituting stock assets), animation deterministic
  (tools/media.py:1-22,39-48,371,393). Backends discovered from env only (_default_backends tools/media.py:49-66;
  service :67). Media has no Connections/credential UI and no usage-reservation integration.

## 13. Grounding subsystem

- Package: clock, temporal, dedup, acquire, streams, media, report (grounding/__init__.py:1-16).
- Acquisition: bounded adapters GDELT DOC 2.0, RSS/Atom feeds, Hacker News Algolia, SearXNG JSON (configured
  instance), Bluesky public search (grounding/acquire.py:1-21). Distinct outcomes
  ok/zero_results/partial/disabled/unavailable/blocked/rate_limited/timeout/error; local date validation;
  bounded concurrency, per-adapter timeout, per-host spacing, one retry with jitter and an investigation deadline
  (acquire.py:24-117). Config from <state dir>/grounding.json (acquire.py:81-103). Code docstring claims
  GDELT/feeds/HN verified live and Bluesky blocked from the current network; not re-tested here (C/U).
- Streams: versioned cursors with explicit kinds (seq / timestamp_micros / structured_json / opaque), Jetstream
  seq-vs-timestamp namespace split, Wikimedia SSE id parsing, honest liveness separating connected, last event,
  last canary and coverage gap (grounding/streams.py:1-17,43-93,146-330).
- Media inspection: bounded acquisition, frame sampling, C2PA presence and EXIF/ffprobe clues, no verdicts
  (grounding/media.py:1-52,58; inspect_media :295; reverse_image_search_status :482).
- Tables: investigations, sources/revisions, claims, evidence links, media artifacts/observations, answers and
  stream cursors created by _create_grounding_schema (store.py:1602-1794; investigations :1618, claims :1693,
  evidence :1707, inv_media :1723), called from _migrate_51 at store.py:1806. Package docstring says "store tables
  (schema v53)" (grounding/__init__.py:13); current SCHEMA_VERSION is 84 (store.py:2461 = 1 + 83 migration
  entries, including module migrators). Treat the v53 prose as possibly stale (U).
- Tools: group "grounding" = live_search, inspect_media (tools/__init__.py:103); tools/live.py imports acquire,
  media, dedup, report and writes through the canonical tables; tools/webfetch.py records evidence rows.
- API: investigations bundle/refresh/frames at server/app.py:5439-5510 (GET investigation :5439, POST refresh
  :5448, frame serving :5473).
- Grounding has no Connections object, no provider registry, no per-adapter credential; configuration is a file
  plus tool approval. It is a separate integration plane from model providers.

## 14. Contradictions between docs/data and code

| # | Artifact says | Code says | Evidence | Severity |
|---|---|---|---|---|
| C1 | "The Anthropic API has no common model-list operation in Hutch's connection contract" (data/compat.json:39; file last commit 2026-10-11) | ClaudeProvider.list_models paginates the Models API limit 1000 with after_id for up to 10 pages and probe_models authenticates against it (providers/claude.py:158-195); anthropic-api template models_endpoint true; docs/research/multi-provider-platform-review-2026-10-10.md:18-21 describes exactly this pagination | R | High for docs honesty; matrix stale |
| C2 | compat route `opencode-harness` state "unavailable", harness "OpenCode is never launched by Hutch", verified_on 2026-10-09 (data/compat.json:177-201) | OpenCodeRuntime exists, starts `opencode serve`, reachable from bot.runtime (runtime/opencode.py:1-15,211; runtime/__init__.py:20-21); host capability external_runtimes is experimental on Linux (server/app.py:3047-3054); provider-compatibility.md:24 says "Available"; docs/architecture.md:103 says enabled through an owned private server | R/C | High: public artifacts disagree; commit 96e2c52f (2026-10-22, "Enable the governed OpenCode assistant runtime") changed data/connections.json but not data/compat.json |
| C3 | architecture.md D1: "Legacy pi and opencode enum values fail closed before process creation... remain unavailable" (docs/architecture.md:178-181) | Same document says OpenCode runtime is enabled (docs/architecture.md:103); Pi is fail-closed, OpenCode is not | R/C | High within one doc |
| C4 | "Hutch chat currently accepts text only: no route in this matrix exposes an image attachment or image content mapping" (docs/realignment/provider-compatibility.md:10-11; compat.json vision fields all "not exposed" for supported routes) | Capability-gated chat image input landed 2026-10-23 (commit dcc85e85), wired at runtime/builtin.py:365-410,1213-1222, server/app.py:3652-3717, providers/attachments.py, providers/images.py; OpenAI vision table openai_compat.py:37-64 | R (git log + code) | High: matrix verified_on 2026-10-08/11 predates the feature |
| C5 | compat.json opencode-go-connection auth_flow: "Hutch does not read OpenCode auth.json or browser sessions" (data/compat.json:121-146); provider-compatibility.md:22: "OpenCode CLI credentials in auth.json are not imported or reused" | runtime/opencode_login.py reads XDG opencode auth.json and transfers API-type keys into the owned OpenCode server for the assistant runtime (opencode_login.py:1-5,63-97); OAuth entries are refused. The absolute sentence is wrong for the assistant path; it is right that the OpenCode Go named connection does not reuse them | R/C | Medium: docs need scoping |
| C6 | architecture.md diagram lists builtin model providers as "openai / ollama / llama.cpp / lmstudio" (docs/architecture.md:89) | Adapters also cover anthropic, openai-compatible/OpenRouter via connection, OpenAI Responses/SIWC, OpenCode runtime | R/C | Low/medium: stale diagram |
| C7 | Data readme: all entries read "from the vendor's own docs or a docs aggregator on 2026-10-07" (data/connections.json:2) | Per-row source includes docs.openclaw.ai for all Xiaomi rows (aggregator), no per-row fetched date, and one notice says the terms page was not machine-readable | R | Medium for the evidence table |
| C8 | Grounding package docstring says store tables "schema v53" (grounding/__init__.py:13) | Tables are created by _create_grounding_schema called from _migrate_51 (store.py:1597-1600,1602-1794,1806); current SCHEMA_VERSION 84 | R | Low; verify before citing version numbers |
| C9 | provider-compatibility.md:61-67 cites tests/test_compat.py, tests/test_providers.py, test_provider_authority.py as regression coverage | Files exist with 5/42/11 test functions (F); coverage boundaries are fixture-only, not live | C/F | Low; wording is accurate |

Non-contradiction that looks like one: data/connections.json chatgpt-plan declares protocol openai-responses, while
ConnectionBook rejects Responses for every other template (connections.py:178-193). The "Responses unsupported"
rule and the one SIWC exception are consistent.

## 15. Oversize and god-function risks (worktree HEAD, measured 2026-10-30)

| File | Size (baseline) | Longest enclosing region | Why it matters |
|---|---|---|---|
| src/hutch/server/app.py | 7,291 (7,461) | create_app 1985-7291 = 5,307 lines; every route is nested inside the factory | New connection/provider APIs all land in one function; route inventory is already hard to audit |
| src/hutch/runtime/builtin.py | 1,955 (1,955) | BuiltinRuntime 158-1903 = 1,746; execute 1130-1903 = 774; _summarize_units 985-1128 = 144; _prepare_session 419-528 = 110 | Provider routing, admission, images, fallbacks and tool loop live in one class |
| src/hutch/store.py | 12,588 (12,593) | Store class 2599-12588 = 9,990; submit_conversation_message 5542-5844 = 303; admit_and_reserve 10088-10292 = 205; _create_grounding_schema 1602-1794 = 193 | Usage/reservation and capability-observation schema inside a 10k-line class |
| src/hutch/runtime/opencode.py | 719 (719) | OpenCodeRuntime 211-719 = 509; execute 452-719 = 268; _broker_permissions 327-376 = 50 | Governed external runtime is one long execute; provider work must not add branches here |
| src/hutch/server/pages.py | 697 (731) | register_pages 62-690 = 629 | Legacy connection pages and SPA-era APIs coexist |
| src/hutch/modelchoices.py | 431 (435) | _connection_choices 197-292; model_choices 302-354; validate_override 357-427 | Catalog discovery, SIWC, OpenRouter and generic list_models are special-cased in one file; frozen size means new providers must be factored out |
| src/hutch/server/static/app.js | 14,273 (14,532) | single hand-written bundle; renderConnections 9347 onward; route table 1904 | Provider UI additions land in a 953 KB bundle |
| src/hutch/media/jobs.py | 592 (592) | MediaJobService 109-592 = 484; finalize 320-418; reconcile 503-582 | Adding a media provider should not grow this class |
| src/hutch/grounding/acquire.py | 865 (865) | search_searxng 486-594; search_jetstream_stream 665-765; run_search 767-865 | Fan-out pattern the model platform may want to reuse |

Policy: .file-size-baseline.json is the frozen over-cap list; repository rule is "shrink only, never extend; split
instead" (AGENTS.md hard rules). Current sizes are below their frozen baselines (7291<7461 for app.py, 431<435 for
modelchoices.py, 14273<14532 for app.js), so new provider work cannot grow these files.

## 16. What the tests genuinely establish (name/docstring level; not executed)

- Provider/connection/model group: 169 test functions in 10 files.
  - tests/test_providers.py (42): explicit num_ctx, streaming retry, typed errors, exact usage, scripted HTTP
    fixtures; no live model.
  - tests/test_compat.py (5): versioned matrix has state and dated HTTPS evidence per route; endpoint returns
    typed records; OpenAI request mapping strips unimplemented fields and uses the exact host; OpenRouter uses its
    completion-limit field; lookalike/insecure hosts rejected (parametrized, :86).
  - tests/test_connections.py (40): connection semantics, own keys, headers, billing, allowances, terms, endpoint
    validation; no live provider.
  - tests/test_connection_secrets.py (1): provider error text redacts the stored key.
  - tests/test_provider_authority.py (11): route/account changes need outward review; rotation invalidates
    clients; auth/quota failures cannot silently construct a paid fallback; stream retry reserves again;
    embedded endpoint credentials refused.
  - tests/test_model_switcher.py (26): picker list, per-message override, validation; the code comment at
    modelchoices.py:46 says the discipline (catalog fetch only from the picker) is pinned at line 184.
  - tests/test_models_page.py (15), test_models_layer.py (23), test_models_detected_route.py (4),
    test_unusable_route_picker.py (2): page/view/route-shape coverage.
- ChatGPT/OAuth group: 28 functions in 4 files (auth 10, integration 3, background consent 10, oauth_apps 5):
  local PKCE, ID-token/JWKS verification, account storage, consent/revocation, publisher OAuth client validation;
  no OpenAI authorization server or account used.
- OpenCode/runtime group: 61 functions in 6 files (api 6, runtime_opencode 23, tool_bridge 7, login 6,
  runtime_controls 6, memory_bridge 13): server protocols, permission brokering, tool bridge, local login reading,
  runtime controls; no live `opencode` model request. Plus test_code_handoff.py (11) for profile/task configs.
- Media group: 81 functions in 5 files (jobs 25, providers 10, render 15, storage 13, validate 18). Protocol-only
  adapters through fakes; job state machine and no double billing; storage hash/integrity; validation/render.
  No live media provider.
- Grounding group: 97 functions in 10 files. Acquisition outcomes/date validation, dedup, temporal, streams
  (Jetstream/Wikimedia cursor semantics), media inspection, API/tool scenarios. The acquire "verified live"
  claim is a code comment, not proven by these tests.
- test_live_model_qualification.py (3) is an opt-in qualification harness with a fake OpenCode-shaped row; it
  makes no live request by default.
- Not established by fixtures: live inference, live billing/usage reconciliation, SIWC eligibility, live
  Google/Microsoft consent, live media generation, live grounding adapters in this environment, Windows/macOS
  payload parity.

## 17. Isolation status and dirty working trees

Handoff named clean HEAD 1c454c32. Actual worktree state when read (2026-10-30 22:51):
- HEAD is 7ef8ba211787 ("docs(providers): establish research scope, plan and validation ledger"), one docs-only
  commit after 1c454c32, so the worktree also contains 00-SCOPE.md, 05-IMPLEMENTATION-PLAN.md,
  06-VALIDATION-LEDGER.md, 07-ROLLOUT-AND-MIGRATION.md and drafts/01-core-providers.md, 03-media-speech-search.md.
- At first read (22:51) the only modified file was docs/research/2026-10-provider-platform/drafts/
  03-media-speech-search.md (another teammate's draft). By 22:56 the shared worktree had moved: connections.py and
  data/connections.json are modified, src/hutch/providers/accounts.py and tests/test_provider_accounts.py are new
  (another teammate's in-progress provider-account work), and drafts 01/02/03 changed or appeared. This fragment's
  facts for connections.py and data/connections.json are the HEAD snapshot read at 22:51; re-check those two
  files before relying on their line numbers. All other cited files were unmodified at both samples. The worktree
  HEAD named in the handoff was 1c454c32 but its actual HEAD is 7ef8ba2 (one docs commit later).

Separate main checkout /home/kevina/CodingProjects/hutch (not the reference checkout per the lead) was sampled at
22:47 and had 42 entries; listed here only so implementation can avoid collisions, not as current Hutch behaviour:
- Modified tracked (21): src/hutch/cli.py, installation.py, main_assistant.py, modelchoices.py, personal_schema.py,
  route_problem.py, server/app.py, server/nav.py, server/security.py, server/static/app.js, index.html,
  installation.js, model-switcher.js, palette.js, studio.css; tests/e2e/test_model_picker.py,
  tests/e2e/test_starter_route.py, tests/test_cli.py, test_main_assistant.py, test_no_demo_content.py,
  test_unusable_route_picker.py.
- Untracked (21): .pipeline/personal-operations/2026-10/{00-BRIEF,COMPETITIVE-ANALYSIS,CURRENT-STATE,
  EDGE-CASES,FAILURE-ANALYSIS,GAP-REGISTER,RESEARCH}.md plus .pipeline/.../evidence/ (another session's research,
  not read and not evidence here); docs/research/2026-10-provider-platform/ (team workspace); src/hutch/
  demo_leftovers.py; src/hutch/server/static/{assistant-removal,model-repair,personal-tools,personal-ui,shared,
  today}.js and personal.css; tests/e2e/test_assistant_removal.py, tests/e2e/test_model_repair.py,
  tests/test_demo_leftovers.py, tests/test_static_cache_policy.py.
The overlap matters because the picker, connection API, host capabilities and SPA Apps & AI view all sit in files
that were dirty in the main checkout; if those edits land, this fragment's line numbers for the worktree HEAD stay
valid for the worktree but must not be compared with the main checkout working tree.

## 18. Blocked, retired and unsupported routes

| Route/flow | Status | Where stated | What the block protects |
|---|---|---|---|
| Consumer OAuth/session reuse (cookies, other app session tokens, consumer OAuth as API key) | Blocked | data/compat.json:229-253; connections.py:21-24 | Prevents credential laundering and account bans; SIWC is a separate documented preview |
| Pi executor | Unavailable, fails before process creation | data/compat.json:203-227; runtime/pi.py:20-38 | No approval broker and no way to reserve/reconcile provider spend |
| OpenCode executor as published in compat.json | Published "unavailable", code has a governed runtime | data/compat.json:177-201 vs runtime/opencode.py, provider-compatibility.md:24 | Publication stale, not a policy block; resolve before publishing provider docs |
| Retired mock/demo runtime and demo routes | Removed; persisted bots fail closed with a fix path | runtime/__init__.py:22-23; modelchoices.py:375-377; route_problem.py:20,26-38 | Stops fake inference being presented as real work |
| OpenCode Go models served only over OpenAI Responses | Unsupported on the direct connection | data/connections.json template hint; connections.py:41-42,178-193 | Only the SIWC template may use the Responses protocol |
| Custom Anthropic-compatible endpoint model catalog | Unsupported (models_endpoint false) | data/connections.json custom-anthropic | Test only proves key presence; no catalog request |
| OpenCode CLI coding handoff on non-Linux | Unavailable | server/app.py:4116 (Linux gate in create_code_handoff); provider-compatibility.md:28 | No sandbox/terminal ownership outside Linux |
| Project-local OpenCode plugin files in a coding handoff | Refused | code_handoff.py:472-491 | Installed V2 plugin-loading behaviour unverified |
| Gmail read/send public release | Experimental private preview, not for public release | provider-compatibility.md:39 | Sensitive/restricted-scope OAuth verification and security assessment incomplete |
| Google Calendar writes, Outlook writes/sends | Experimental, local setup, exact approval each time | provider-compatibility.md:36-39 | Scope reach exceeds exposed actions; live consent unverified |
| Vision/image chat per compat matrix | Published "not exposed" | data/compat.json vision fields; provider-compatibility.md:10-11 | Stale (C4); per-route availability still U |
| Anthropic constrained structured output | Not sent by current adapter | data/compat.json:33-58 | Matrix says constrained protocol unavailable on that route |
| Unattended/scheduled OpenCode Go use | Not established | data/connections.json opencode-go terms notice | Vendor describes coding-agent traffic; operator acknowledges terms |
| Any live model qualification | No probe; passive observations only | store.py:1079-1105; server/app.py:3073-3125 | Hutch cannot silently claim a model capability without evidence |

## 19. Gaps versus the requested multi-provider platform

1. No provider registry object. Provider identity is spread across OFFICIAL_HOSTS (registry.py:26), ambient_key
   (:52), _OFFLINE_DEFAULTS (:107), PRESET_URLS (openai_compat.py:25), LOCAL_PROVIDERS (pricing.py:21),
   HOSTED_KEYS (modelchoices.py:31), KNOWN_PROVIDERS (:33), RESERVED (connections.py:44). Adding one provider
   touches several of these plus data/docs.
2. No schema versioning or migration for user provider state: compat.json has version 1; connections.json has no
   version; state/connections.json rows are merged by key and invalid rows are warnings only.
3. Two incompatible validators: validate_spec (registry.py:75) accepts any lowercase slug; validate_override
   (modelchoices.py:420-422) rejects anything outside KNOWN_PROVIDERS. An imported config can pass one and fail
   the other.
4. API-key routes are Chat Completions only; Responses is reserved for SIWC (connections.py:178-193). There is no
   protocol-negotiation layer, only three hard-coded branches (providers/connection.py:25-39).
5. The compatibility matrix is hand-maintained and demonstrably stale (C1, C2, C4). Its validation checks shape
   and dates, not correspondence to code; it has no evidence-tier enum and cannot represent connection-specific
   plans (Xiaomi, OpenRouter routing, OpenCode Go model protocols).
6. Catalog discovery is three special cases inside modelchoices.py:197-292 (SIWC account list, OpenRouter search,
   generic list_models), each with its own cache, error policy and notes. No provider-level "list models"
   abstraction with a common result shape.
7. Credentials are bespoke stores: ConnectionBook key files, ChatGPT accounts.json, Google/Outlook account books
   plus secret-tool, OpenCode auth.json reader. No unified credential interface; the only cross-cutting rule
   ("never return the secret") is implemented per call site.
8. Account OAuth flows are duplicated per feature (Google Calendar, Gmail search, Gmail send, Outlook Calendar
   read, Outlook Calendar write, Outlook Mail read/send, plus SIWC). oauth_apps.py only handles publisher client
   IDs for Google/Microsoft; there is no one OAuth registration model.
9. No live verification pipeline: every adapter boundary says no live request; matrix dates describe docs plus
   fixtures. There is no dated live smoke test, no recorded response identity for most routes, and no UI
   distinction between "listed in docs" and "verified live on this account".
10. Per-model protocol is manual for connection plans: Connection.endpoint_for reads model_protocols
    (connections.py:100-105), set by CLI/legacy form. Nothing derives or verifies it from provider catalogs.
11. No model capability probe by design; the only positive evidence is a passive function-tool-call observation
    (store.py:1079-1105). A platform needs a richer yet honest capability record (streaming, structured output,
    vision, context) with provenance.
12. Media providers are env-configured and outside Connections and usage accounting (tools/media.py:39-67); a
    multi-provider platform likely wants media as first-class providers with the same credential/billing story.
13. Grounding adapters are a separate config plane (state/grounding.json, no UI, no connection object) that already
    implements the bounded fan-out and per-adapter outcome vocabulary a provider platform will need; reuse rather
    than build a second design (grounding/acquire.py:1-117).
14. Runtime boundaries hard-code builtin/opencode/pi as string checks in engine, modelchoices, routes and server
    (engine.py:164-165,283-284,304-305,631-632,697-698,718-719; runtime/__init__.py:16-26). A third runtime has
    no seam.
15. Frozen-shrink-only files (server/app.py, modelchoices.py, builtin.py, store.py, static/app.js) constrain where
    new provider abstractions may live: new modules, not growth of these.

## 20. Sources and verification dates

Repository evidence read in this session (all 2026-10-30, America/Vancouver, from the isolated worktree):

| Source | Kind | Date/as-of | Notes |
|---|---|---|---|
| src/hutch/data/compat.json | R/V container | reviewed_on 2026-10-10; last commit 2026-10-11 (git log) | 9 routes, per-route verified_on 2026-10-08 to 2026-10-11 |
| src/hutch/data/connections.json | R/V container | _readme says vendor docs read 2026-10-07; last commit 2026-10-22 | 11 templates; per-row source only |
| src/hutch/compat.py | R | read 2026-10-30 | matrix validation semantics |
| src/hutch/connections.py, providers/*.py, runtime/*.py, modelchoices.py, route_problem.py, code_handoff.py | R | read 2026-10-30 | 4 chat adapters, 2 runtimes + 1 fail-closed, picker, handoff |
| src/hutch/server/app.py, pages.py, pages_models.py, static/app.js, static/model-switcher.js, templates/connections.html | R | read 2026-10-30 | API and UI surfaces |
| src/hutch/media/**, grounding/** | R | read 2026-10-30 | media and grounding planes |
| src/hutch/store.py, models.py, toolcalling/profiles.py | R | read 2026-10-30 | schema 84; capability observations; bot/run fields |
| docs/realignment/provider-compatibility.md | C | reviewed 2026-10-10; last commit 2026-10-22 | states cited in sections 3 and 14 |
| docs/research/multi-provider-platform-review-2026-10-10.md | C/V | 2026-10-10 | sources recorded: OpenAI models list, Anthropic models list, OpenRouter catalog and fallbacks, T3 Chat FAQ/feedback |
| docs/research/offerings-and-failures.md | C/A | sources read 2026-10-07 | Dots/Grok research; pricing facts carried into prices.json |
| docs/research/complaints.md | C/A | revalidated 2026-10-07 | failure classes; quarantined claims excluded here |
| docs/architecture.md | C | read 2026-10-30 (undated file) | runtime/provider claims cited in C3/C6 and section 9 |
| git status, git log -1 per file | R | 2026-10-30 22:47 and 22:51 | staleness evidence for C1-C4; no history rewrite |
| tests/*.py (names, docstrings, counts) | F | read 2026-10-30 | not executed; counts are static test-function counts |
| draft 00-SCOPE.md, 05-IMPLEMENTATION-PLAN.md, 06-VALIDATION-LEDGER.md, 07-ROLLOUT-AND-MIGRATION.md | C | present in worktree | not read in detail for this fragment; another teammate's drafts 01 and 03 not read |

Vendor documentation embedded in repo data (URL + observation date as recorded by the repo; not re-fetched):

| Topic | URL recorded in repo | Recorded observation date | Evidence class |
|---|---|---|---|
| OpenAI Chat Completions | https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create | 2026-10-08 | V (as recorded) |
| OpenAI Models list | https://developers.openai.com/api/reference/resources/models/methods/list | 2026-10-08/10-10 | V (as recorded) |
| Anthropic Messages | https://platform.claude.com/docs/en/api/messages/create | 2026-10-08 | V (as recorded) |
| Anthropic Models list | https://platform.claude.com/docs/en/api/models/list | 2026-10-10 | V (as recorded) |
| Ollama chat API / context length / tool calling | https://docs.ollama.com/api/chat; https://docs.ollama.com/context-length; https://docs.ollama.com/capabilities/tool-calling | 2026-10-08 and 2026-10-07 | V (as recorded) |
| LM Studio tool use | https://lmstudio.ai/docs/developer/openai-compat/tools | 2026-10-08 | V (as recorded) |
| llama.cpp server | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md | 2026-10-08 | V (as recorded) |
| vLLM OpenAI-compatible server | https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/ | 2026-10-08 | V (as recorded; exact path per repo) |
| OpenRouter catalog / endpoints / billed usage | https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties; .../endpoints/list-all-endpoints-for-a-model; https://openrouter.ai/support/ | 2026-10-11 | V (as recorded) |
| OpenCode Go terms | https://opencode.ai/docs/go/; https://opencode.ai/v2/docs/console/go | 2026-10-08 and 2026-10-07 | V (as recorded) |
| OpenCode permissions / server / providers | https://opencode.ai/v2/docs/permissions; https://opencode.ai/docs/server/; https://opencode.ai/docs/providers/ | 2026-10-09 | V (as recorded) |
| Sign in with ChatGPT | https://developers.openai.com/siwc/token-sharing-open-source/ (+ /preview-limitations); https://openai.com/policies/sign-in-with-chatgpt-terms/ | 2026-10-09 | V (as recorded) |
| Pi RPC / CLI / security | https://pi.dev/docs/latest/rpc; https://pi.dev/docs/latest/cli; https://pi.dev/docs/latest/security | 2026-10-09 | V (as recorded) |
| Anthropic consumer/API boundary | https://www.anthropic.com/news/updates-to-our-consumer-terms?subjects=claude | 2026-10-08 | V (as recorded) |
| Xiaomi MiMo plans | https://docs.openclaw.ai/providers/xiaomi (aggregator); https://mimo.mi.com/docs/en-US/tokenplan/subscription | 2026-10-07 | V/A (aggregator) |
| Google Calendar/Gmail scopes, Microsoft Graph, installed-app OAuth | links in docs/realignment/provider-compatibility.md:36-39 | 2026-10-10 | V (as recorded) |
| OpenCode coding handoff research | docs/research/opencode-coding-handoff-2026-10-09.md | 2026-10-09 | C |

No vendor page was fetched in this session; a later vendor-verification task should re-fetch and record HTTP status
plus the fetch date before anything is published as vendor-current.

## 21. UNVERIFIED / open questions for the lead

1. U: Is chat image input exposed in the current SPA composer? Server admission accepts image_attachments
   (server/app.py:3652-3717), runtime attaches them (builtin.py:365-410,1213-1222), but the composer/upload path in
   the large static bundle was not traced end to end.
2. U: Is the OpenCode runtime used in a default install? It needs an installed OpenCode CLI major version 2
   (opencode_server.py:152-160) and an explicitly selected login; no live check.
3. U: Does compat matrix verified_on mean "fixtures recorded" or "docs reviewed"? Some route text says fixtures,
   some says docs; no field distinguishes them. Important for the lead's evidence table.
4. U: Do tests still pass in this worktree? Not run; counts are static.
5. U: Xiaomi endpoints/terms: source is an aggregator and the terms page was reported not machine-readable.
6. U: Grounding "verified live" (GDELT/feeds/HN) is a code comment, not re-run here; Bluesky may be blocked by
   network.
7. U: Google/Microsoft live OAuth flows and Windows/macOS parity for calendar/mail secret storage.
8. U: Media providers live behaviour (OpenAI Images, ComfyUI); only fake transports are tested.
9. U: What "provider" means for the requested platform: wire protocol, account/billing entity, or vendor product?
   The repo mixes all three (route id vs connection template vs adapter); section 19 assumes all three are wanted.
10. U: The handoff named HEAD 1c454c32 but the worktree is at 7ef8ba2 (one docs commit later, with provider docs).
    Confirm that is the intended base before implementation branches from it.
