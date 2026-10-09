# Requirements (v0.2) and implementation status

Source: *Hutch requirements v0.2 draft*, 7 Oct 2026 (UI = dashboard, LM = local models,
CO = collaboration, SR = safety and reliability, PF = performance). IDs are stable so issues and
commits can cite them. Evidence for the *why* is in
[research/offerings-and-failures.md](research/offerings-and-failures.md) and the
[Grok Bot product review](research/grok-bot-product-review-2026-10-09.md).

**Status key:** `done` — implemented and covered by a test or a recorded measurement ·
`partial` — implemented with a stated gap · `later` — scheduled after v0.1 per the draft ·
`planned` — not yet built.

> Performance numbers in the draft are *proposed targets*. Measured values live in
> [performance.md](performance.md) and the committed `benchmarks/baseline.json`.

*Status column last updated: 2026-10-09. Studio New Bot carries the latest user message into an editable, provenance-linked draft; each visible user message also offers **Make a bot**, which seeds setup from that exact request rather than requiring it to be restated. The owner may select up to eight earlier user messages from the same chat as reviewed saved background; later messages, assistant replies and other chats stay excluded. Setup suggests an editable professional Bot name and stable address locally and uses four review screens. A configured chat/workspace model route is prefilled; managed workspace, no tools, ask-first actions and no schedule are defaults. The owner still reviews the full draft; Hutch does not infer extra intent or permissions, and natural-language refinement remains open. A named workspace coordinator now offers one user-reviewed handoff to a selected specialist with a separate chat and durable parent status/result card; users can attach one exact specialist response to a coordinator follow-up. Schema v31 records content-free committed-event checkpoint markers and schema v32 adds optional task-only snapshots of reviewed coordinator facts. Schema v34 supports one narrowly gated, owner-confirmed fresh run from a failed/stopped built-in task checkpoint with no recorded action or child work and unchanged permissions; it does not resume processes, carry prior tools/receipts/facts or continue `outcome_unknown`. Schema v35 adds isolated Outlook Mail credentials and Bot grants. Specialist allowlists, generalized result delivery and broader team planning remain open. Built-in conversational runs support durable typed choices; external runtime coverage and final release validation remain open. Google Calendar and Outlook Calendar reads, plus separately permissioned Outlook Mail search previews, are implemented behind operator OAuth and Linux Secret Service setup; live account and consent verification remains outstanding. Gmail now has an experimental private-preview, read-only search path requiring the owner's restricted Google OAuth client, Linux Secret Service, and loopback-only Local Bot routes; no live account was tested, and public release remains unavailable pending Google scope verification and any applicable security assessment. Gmail sending is not implemented. Protected browser credential entry and human checkpoints are partial and still need headed/live verification. Coordinator/specialist model controls, general cross-Bot memory sharing and broad restart recovery remain incomplete.*

## Dashboard and app

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| UI-1 | Home shows Needs you / Running now / Stale | MVP | done | `views.home_state` served at `/`: Needs you / Running now / Stale, each with cause and fix; `tests/test_views.py`, `tests/test_dashboard.py` |
| UI-2 | Stop all in every header; per-run Stop kills child processes | MVP | done | Stop all in every header (plain POST + confirm); engine kills process groups; tested incl. forked helper |
| UI-3 | Run event streams resume from durable cursors and resources publish ordered updates | MVP | done | Per-run `seq`, cross-run SQLite event IDs and transactional resource invalidations replay from `Last-Event-ID`; pages are bounded, the retained boundary remains replayable, and older cursors require a reconciliation snapshot. See `tests/test_sse_resume.py`, `tests/test_durable_changes.py`, and the retention checkpoint in `realignment/ledger.md` |
| UI-4 | Run detail: steps, elapsed, spend, context vs caps | MVP | done | `views.run_meters`: steps, elapsed, spend, tokens, context vs caps, plus absolute model/tool/Hutch timing |
| UI-5 | Approvals inbox: parsed segments, rule, once/always/deny, countdown | MVP | done | approval card: parsed segments, rule, once/always/plan/deny, live countdown; outward never offers always |
| UI-6 | Every waiting state names its cause and a fix | MVP | done | `views.explain_run`, `explain_outcome` and the stale cause: every wait names a cause and a fix |
| UI-7 | New bot: template gallery → purpose, model preset, permissions+budget; YAML view | MVP | partial | Guided chat configures purpose, template, model route, tools, limits, approval policy and optional schedule. YAML import/export remains unbuilt. |
| UI-8 | First run clearly requests a configured real local or hosted model; no seeded bots or simulated runs | MVP | partial | CLI/app empty setup and fail-closed bot creation implemented; full visual/release validation pending |
| UI-9 | Schedules page: next runs in each bot's zone, coalesced misses, pause all | MVP | planned | |
| UI-10 | Memory page with provenance, edit, delete, export | Later | partial | bot page lists memory with the run that wrote it, delete; edit/export + dedicated page pending |
| UI-11 | Usage page: spend by bot/provider/day; escalation log | Later | done | `/usage`: spend and tokens by day (local day), model and bot, today against each bot's caps, plan allowances, cache share, and the fallback/escalation/allowance-stop log |
| UI-12 | Server-rendered templates + HTMX, no build step; stop/approve are plain POSTs | MVP | done | Jinja2 + htmx 2.0.4 vendored, no build step; every action is a plain POST; CSRF + Host/Origin checks |
| UI-13 | Approvals inbox usable at phone width | Later | done | approvals inbox verified at 390px in Chromium (full-width, thumb-sized actions) |
| UI-14 | Localhost app run by a user-level systemd service; Tauri shell after v0.1 | MVP, then later | planned | |
| UI-15 | Create or refine a bot through chat using the current conversation, ask only for missing details, then review and confirm the complete draft | MVP follow-up | partial | The four-screen Studio flow seeds from the latest request or the exact user message selected through **Make a bot**, and records its original text/source. Only earlier user messages may be selected as context; following requests, assistant replies, other chats and authority are excluded. Purpose-based display name/address suggestions and configured chat/workspace model defaults are editable. Local naming rules cover common reminder, filing, and Bot-team coordinator requests, normalize actions/time cues, and keep the address derived from the suggested name until edited. Managed workspace, no tools, ask-first actions, no schedule and bounded execution defaults fill the draft. Tools, starter, limits, schedule and human browser handoff remain optional choices. The user still reviews the full draft and model route. Natural-language request refinement and resolving additional details through chat are not implemented. Creation is idempotent and starts no run. Evidence: `tests/test_api.py::test_bot_creation_records_only_an_explicit_user_message_source`, `tests/e2e/test_browser.py::test_user_can_start_bot_setup_from_the_exact_chat_request`, `tests/e2e/test_browser.py::test_bot_creation_reuses_only_the_selected_chat_messages_and_keeps_provenance`, `tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone`, and `realignment/artifacts/bot-from-message/`. |
| UI-16 | Bots can ask typed single- or multi-select questions in chat and resume after a reply | MVP follow-up | partial | Schema v26 stores immutable questions/options and one-use answers; the built-in conversation tool stops its run at the question and a normal idempotent chat turn resumes with the selected labels. Answers grant no permission and never resolve approval or browser-human waits. OpenCode/Pi remain unavailable; desktop/tablet/phone visual validation and release evidence remain outstanding. See `tests/test_conversations.py`, `tests/test_runtime_builtin.py`, and `realignment/ledger.md`. |
| UI-17 | Users can enter passwords and complete web forms without exposing secrets to the model | MVP follow-up | partial | Opt-in local Linux browser handoff lets the person enter secrets in the visible owned profile. Agent typing is blocked on conventional password, OTP, payment-credential and secret-labelled fields; if a click, text entry or wait reveals a sensitive field, Hutch pauses on the same live page for the person before continuing, and warns against blindly retrying actions that already happened. All browser `type` event/receipt values are redacted, approvals bind a process-keyed fingerprint, and screenshots fail closed while a visible sensitive field exists. Native form submissions show their destination, method and visible field labels; isolated-world digests bind the form state to one-time approval, while values and fingerprints stay out of Hutch records. Hutch refuses selected file uploads and pages that cannot compute a secure form digest. Detection is not exhaustive for custom widgets; never paste credentials into chat. Evidence: `tests/test_browser_profiles.py::test_sensitive_browser_entry_is_redacted_and_pauses_for_the_person`, `tests/e2e/test_browser.py::test_browser_hands_off_when_a_click_reveals_a_sensitive_field`, `tests/e2e/test_browser.py::test_browser_hands_off_when_a_wait_reveals_a_sensitive_field`, `tests/e2e/test_browser.py::test_browser_hands_off_when_text_entry_reveals_a_sensitive_field`, `tests/e2e/test_browser.py::test_browser_form_submit_rechecks_the_reviewed_payload_in_chromium`, and responsive approval-card screenshots. Live headed/provider challenges are not tested. |
| UI-18 | Browser work can pause for CAPTCHA and other human-only checkpoints | MVP follow-up | partial | Local Linux handoff pauses the same profile for detected CAPTCHA/2FA/security markers or a visible sensitive field, states the origin/reason, and checks for a challenge before each browser action and after waits, clicks, text entry, navigation, and explicit Resume without reloading the page. When an action already occurred before a challenge became visible, its result says so and warns against blind retry. Hutch never solves or bypasses CAPTCHA. Consent and payment actions still use the normal exact-action approval flow. Evidence: `tests/test_browser_profiles.py::test_login_challenge_only_waits_when_same_live_browser_is_visible`, `tests/e2e/test_browser.py::test_studio_resumes_only_the_active_human_wait_with_v1_command`, and `tests/e2e/test_browser.py::test_browser_pauses_when_a_human_challenge_appears_during_wait`; live third-party challenges and physical-device behavior remain unverified. |
| UI-19 | Users can reply to a specific Bot message with a visible, removable, same-conversation message reference | MVP follow-up | done | Schema v25/API enforce assistant-message and same-conversation scope; the composer reference and unsent draft survive reload, exact retries retain the anchor, and referenced text is bounded and labelled untrusted. Keyboard, phone-touch, migration and restart paths pass; see T-MESSAGE-REPLY and `realignment/artifacts/message-replies/`. |

## Local models and presets

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| LM-1 | Ollama provider uses native chat API, always sets context size | MVP | done | `providers/ollama.py`: native `/api/chat`, `num_ctx` always sent; the `/v1` path is never used for Ollama |
| LM-2 | Startup self-check: fact at top of a long prompt must be recalled | MVP | done | `context.run_selfcheck` (cached per model/window/template); `hutch doctor --deep` |
| LM-3 | Warn before a run when prompt + tools exceed effective context | MVP | done | `context.py` pre-run prompt + tools check; the run fails with the fix instead of truncating |
| LM-4 | Hardware probe: RAM, GPU memory, Apple Silicon, installed runtimes | MVP | done | `hardware.probe`: RAM, GPU memory, Apple Silicon, installed runtimes |
| LM-5 | Models page: fits / tight / won't fit + actual context | MVP | done | `/models` page and `hutch models list`; [models.md](models.md) |
| LM-6 | Models are scheduled resources; batching; cold load is a visible state | MVP | done | `slots.py` (batching, slot gate, fairness, visible wait reason); cold load is the `loading_model` state. Swap latency measurable with `hutch models swap-test`; not yet measured on real models |
| LM-7 | Task presets: router, research, extraction, coding, planner, vision | MVP | partial | six presets resolve per machine, shown on `/models` and `hutch models presets`; picking one in bot creation arrives with the wizard (UI-7) |
| LM-8 | Different presets for planner/executor/summarizer roles | Later | later | |
| LM-9 | One-step escalation on malformed calls / loop / overflow, within spend cap | MVP | partial | `runtime/ladder.py`: one-rung escalation uses the price-based estimate admission guard. Provider billing can differ; exact external dollar ceiling is unavailable |
| LM-10 | Review new hosted billing/destination authority | MVP | done with fixtures | Local or hosted primaries ask before a configured fallback/escalation changes account, destination, protocol or revision. Generic sticky grants cannot bypass this. The primary model selected in chat is explicit for that message; it does not authorize another service. |
| LM-11 | Reliability harness per model/quant/runtime/template | MVP | done | `reliability.py` + `hutch models bench`: five tool probes + long-prompt recall, keyed by model/quant/runtime/template/digest/window, shown on `/models`, used by doctor. Verified against scripted models only; not yet run on real local models |
| LM-12 | Re-measure when runtime or model file changes | Later | later | |
| LM-13 | Tool-call repair; ≤ 8 tools by default | MVP | partial | `runtime/toolrepair.py` coerce/validate/one retry; `hutch doctor` warns above 8 tools; the 8-tool default is not enforced at bot creation |
| LM-14 | Editable hosted price file with verified-on date in UI | MVP | done | price table with source and verified date on `/models`; edit, reset; 90-day stale flag |
| LM-15 | API key access; subscription use behind a terms warning; no token extraction | MVP | partial | Hutch provider API routes and connection terms notices exist. Vendor CLI harnesses `pi` and `opencode` are disabled until permissions, process isolation and budget enforcement are governed. |
| LM-16 | Show each model's license; flag non-Apache/MIT | Later | later | |

## Bot collaboration

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| CO-1 | One user-named workspace coordinator and an owner-approved roster of allowed specialists | v0.1 | planned | A named coordinator is a directly conversable Bot; it does not inherit specialist tools or private history. |
| CO-2 | Structured, correlated task/result/question events with durable delivery status | v0.1 | partial | Schema v29 persists one reviewed parent-to-specialist task, its linked child run/chat, status and latest reply; schema v30 adds a user-selected result reference on a coordinator follow-up, bound to its task and successful source message. Typed task questions and generalized delivery/retry handling remain open. Same-Bot `delegate_task` remains separately bounded (`docs/realignment/delegation.md`). |
| CO-3 | The coordinator dispatches to specialists and receives their replies; user can also chat directly with each Bot; specialists cannot message peers | v0.1 | partial | One user-confirmed handoff routes to a selected Bot's own conversation, and the user can open that chat directly. The user can explicitly attach a bounded specialist response to a coordinator follow-up; no specialist roster allowlist or autonomous peer messaging exists. |
| CO-4 | Own workspace per specialist; explicit, logged file copy; per-bot memory | v0.1 | partial | Child runs get private workspaces and no runtime memory; explicit artifact transfer is unavailable |
| CO-5 | Planner sees results and artifact refs, not transcripts | v0.1 | partial | Parent model receives final child text; artifact references are not returned to model context |
| CO-6 | Engine enforces max hops, tasks, parallel specialists, wall-clock | v0.1 | partial | Depth/fan-out, child step/time limits and lineage cancellation are enforced; exposed child calls are serial and no plans exist |
| CO-7 | Plan budget split into per-task slices | v0.1 | partial | Child usage reserves against the inherited lineage ceiling; per-task slices and token allotments are absent |
| CO-8 | Same task posted twice pauses the plan | v0.1 | partial | Exact retries of the same tool step replay its child; semantic duplicate detection across later steps is absent |
| CO-9 | Stop plan kills every child run | v0.1 | partial | Run Stop cascades to persisted descendants; there is no plan resource or plan Stop command |
| CO-10 | Child approvals in the one inbox tagged with plan; bounded plan-level approval | v0.1 | partial | Child approvals appear in the shared conversation/Needs you flow and always ask; no plan grouping or plan-level grant exists |
| CO-11 | Coordinator conversation shows a durable handoff timeline, ownership, status, and cost; Fleet stays secondary until the roster is large | v0.1 | partial | The coordinator chat displays specialist owner, current status, reviewed brief, settings snapshot, and latest response. Per-task cost presentation and generalized plan history are not included. A dedicated Fleet surface remains secondary; about ten Bots is the owner-set heuristic, not a measured threshold. |
| CO-12 | One named, directly conversable workspace coordinator routes bounded work to selected Bots and receives durable results; the user can still chat directly with each task Bot | v0.1 follow-up | partial | Schema v28 selects a named coordinator; schema v29 implements one reviewed task handoff to an existing Bot, with a separate child chat/run and durable parent status/result. Schema v30 lets the user attach one exact successful specialist message to a coordinator follow-up as untrusted context. There is no reusable specialist allowlist, automatic multi-step planning, or live provider execution verification; see [Grok Bot product review](research/grok-bot-product-review-2026-10-09.md). |
| CO-13 | Coordinator improves a task request from current conversation context without changing intent or authority | v0.1 follow-up | partial | The completed source request and coordinator answer are preserved; the user chooses a Bot and edits the proposed brief and assumptions before dispatch. Only those reviewed fields cross chats; specialist authority remains its saved policy. Asking only unresolved questions and richer selected-context references remain open. |
| CO-14 | Workspace default and per-Bot model routes are visible and editable for the coordinator and specialists; per-run overrides remain distinct from saved defaults | v0.1 follow-up | partial | Preferences saves a validated workspace default for new Bot drafts, and per-Bot routes and one-message overrides remain distinct. The dispatch review shows the specialist's saved route and captures its capability snapshot; it does not add a task-specific override or guarantee a live provider route. |
| CO-15 | Coordinator and specialist work has durable progress checkpoints, separately correlated to the parent task and recoverable after restart | v0.1 follow-up | partial | Schema v31 journals ordered, content-free markers for committed child-run status, messages, approvals/questions/human waits and artifact references; the typed API returns the latest 16 plus the total count, and the task card exposes the timeline. The journal is atomically derived from the child's immutable event stream and linked run capability snapshot; it stores no reasoning, prompts, action arguments, tool output or secrets. Schema v34 adds one owner-confirmed fresh run from an eligible failed/stopped built-in task with no recorded tool action or child run, no later specialist-chat work or pending question, an active parent conversation, and an exact unchanged capability snapshot. Only reviewed brief/constraints and the bounded committed assistant response as untrusted progress enter the new run; actions, receipts, selected facts, credentials, prior tool results and old conversation history do not. This is not process resume; `outcome_unknown` stays reconciliation-only. External runtime recovery, general execution-state restore and broader collaboration remain open. |
| CO-16 | Bot memory is separately controlled from conversation history, task context and artifacts; cross-Bot memory is shared only by an explicit, inspectable user action | v0.1 follow-up | partial | Schema v32 lets the owner select up to eight current, reviewed facts from the coordinator Bot or exact coordinator chat while reviewing one handoff. Immutable snapshots, provenance and revisions stay attached to that task, bounded to 6,000 serialized characters, labelled untrusted in the specialist's run context, and never promoted to specialist Bot memory. Nothing is selected by default; once sent, provider retention follows that provider's terms and the payload cannot be recalled. General reusable cross-Bot grants and broader memory-policy journeys remain open. |

## Safety and reliability

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| SR-1 | One runtime/model crash affects only its own runs; health per runtime | MVP | done | orphan recovery, shutdown, per-run isolation and per-runtime health (`health.py`, Models page, doctor) |
| SR-2 | Exact per-step token/cost accounting, visible before a run | MVP | partial | Actual response usage is recorded per call; atomic pre-call reservations cover measured history plus prompt/reply estimates across Hutch runs and configured accounts. Currency reservations require known prices and are estimates, not provider billing guarantees; uncertain outcomes remain held for reconciliation. See ADR-0011 and `tests/test_reservations.py` |
| SR-3 | Per-bot compact-now and fresh-session controls | Later | later | |
| SR-4 | Outward-sending tools always ask, regardless of sticky allows | MVP | done | Shell pushes/transfers and all browser clicks/typing require one-time outward approval; sticky grants and `trusted` cannot suppress it. Native HTML submit controls are identified, reviewed with destination/method/visible field labels, and bound to an isolated-world digest of the current form state. A detected change after approval refuses the click; selected file submissions are refused, and sensitive input values stay in the browser. Network uploads remain denied. Custom JavaScript controls still receive generic click review; fixture coverage does not certify every website. |
| SR-5 | Small models: thinking off, per-turn token cap, loop detector | MVP | done | `think:false` only for thinking-capable models, per-turn token cap, loop detector that refuses a third identical call (`tests/test_providers.py`, `tests/test_runtime_builtin.py`) |
| SR-6 | In-app help generated from or tested against real routes | Later | later | |
| SR-7 | Every run shows its parent bot or plan | MVP | done | every run shows who started it: schedule, you (cli, dashboard or api), or a plan |
| SR-8 | Provider fallback chain | MVP | done | ordered fallback chain on unreachable model, missing model and mid-run outage, announced in the run (`tests/test_runtime_builtin.py`) |
| SR-9 | Failed streaming request retried once without streaming | MVP | done | a stream that fails mid-flight is retried once without streaming, never after Stop (`tests/test_providers.py`) |
| SR-10 | Bubblewrap-wrapped shell on Linux | Later | later | |
| SR-11 | Hash-chained event log | Later | done | hash chain in `store.py`, `Store.verify_chain`; tamper/delete tests; `hutch runs verify <run-id>` and run detail report verified, legacy/partial and failed status. Legacy events remain explicitly unverified because no historic hash exists. |
| SR-12 | Risk tier per bot (medium asks, high blocked) + per-command rules | MVP | done | `safety.PolicyEngine(tier, rules)`: readonly, supervised or trusted, plus per-command `allow`, `ask` or `deny` globs, seen through wrappers and substitutions; hard denies and outward sends cannot be overridden; bot page, API, CLI (`--risk-tier`, `--rule`); [safety.md](safety.md) |
| SR-13 | Command parser fuzz-tested | MVP | done | `shellparse.py` reads the line like a shell (substitutions, `bash -c`, wrappers, heredocs, `&`, newlines, redirects) and denies what it cannot read; hypothesis-fuzzed in `tests/test_shellparse.py` |
| SR-14 | `doctor` command | MVP | done | `hutch doctor` (`doctor.py`): every problem prints its fix; `--deep`, `--online`, `--json` |

## Performance

| ID | Requirement | Proposed target | Phase | Status | Where |
|---|---|---|---|---|---|
| PF-1 | Byte-identical system prompt + tool list across a run | cached-token share per run | MVP | done | frozen prompt prefix hash recorded on every step (`tests/test_runtime_builtin.py`) |
| PF-2 | Per-tool output limit and downloadable generated files | configurable per tool | MVP | done | clipped tool output and successful `write_file` contents are immutable run-scoped artifacts with a typed API listing and SHA-256-verified download; each is capped at 4 MB and aggregate snapshots at 16 MB per run, excluding arbitrary shell-created files (`runtime/steps.py`, `/api/v1/tasks/runs/{id}/artifacts`) |
| PF-3 | Prompt includes only the bot's allowed tools | — | MVP | done | only the bot's allowed tools reach the prompt (`tests/test_runtime_builtin.py`) |
| PF-4 | Compaction before the context limit | ~75% of context | Later | later | |
| PF-5 | Scheduler sleeps until next due run or event; no polling | near-zero idle CPU | MVP | done | `engine.run_loop`/`next_wakeup`, `wake.py`; `tests/test_engine_loop.py`; 0.0 s/h idle CPU |
| PF-6 | Playwright and provider SDKs imported lazily | CLI status < 300 ms | MVP | done | lazy `httpx`/provider imports; `hutch status` 275 ms (was 820 ms for `version`) |
| PF-7 | SQLite WAL, one writer, batched event inserts, run+seq index | 1,000 events/s | MVP | done | `store.py` writer thread + WAL; ~52k events/s; `tests/test_store_events.py` |
| PF-8 | Browser launches on first use, closes when idle | idle close 5 min | MVP | planned | |
| PF-9 | Coalesced live updates, paginated transcripts | usable at 10,000 events | MVP | done | the run page renders the last 200 events and paginates; a 10,000-event run is tested (`tests/test_dashboard.py`) |
| PF-10 | Small router model stays loaded | — | Later | later | |
| PF-11 | Per-step timing: model wait, tool time, Hutch overhead | overhead < 50 ms/step | MVP | done | `runtime/steps.py`; source-only test scenario measurement; not production inference latency |
| PF-12 | Benchmark suite in CI; fails on 20% regression | — | MVP | done | `benchmarks/run.py`, `baselines/local.json`, `.github/workflows/ci.yml` (CI not yet run remotely) |
| PF-13 | Idle daemon small | < 150 MB resident | MVP | done | 39 MB daemon / 56 MB serve idle |

## Build order and gates

| # | Phase | IDs | Gate | Gate status |
|---|---|---|---|---|
| 1 | Engine baseline | PF-5, PF-6, PF-7, PF-11, PF-12, PF-13 | tests pass offline; benchmarks record a baseline | **passed** — 101 tests offline; baseline in `benchmarks/baselines/local.json` |
| 2 | Run view and control | UI-1…6, UI-12, SR-7 | ten concurrent runs stream, connection cut, transcript resumes with no missing events | **passed** - `tests/test_sse_resume.py` (10 runs x 2 real cuts, real sockets) and `tests/e2e` (Chromium, TCP cut, DOM verified) |
| 3 | Local model layer | LM-1…6, SR-1, SR-14 | self-check passes; swap latency measured for two model pairs | **built and tested; gate not met** - self-check and swap measurement pass against scripted servers (`tests/test_slots.py`, `tests/test_models_layer.py`); no real local models on the dev machine, so swap latency for two real pairs is **not measured** |
| 4 | Reliability harness | LM-11, LM-13, SR-5 | ≥ 3 models profiled on the dev machine | **harness built and tested; gate not met** - three scripted models (good / needs repair / never calls tools) are ranked correctly in `tests/test_reliability.py`; **no real models were profiled** because the dev machine has ~3 GiB free and no Ollama. Run `hutch models bench <model>` on a real machine to meet it |
| 5 | Presets, escalation, budgets | LM-7, 9, 10, 14, 15, SR-2, 8, 9, 12, PF-1…3 | escalation respects caps in tests | planned |
| 6 | Collaboration | CO-1…11 | bounded delegation plan finishes on real local/hosted routes; a misbehaving child is stopped by its parent | planned |
| 7 | v0.1 release | UI-7…9, UI-14, SR-4, SR-13, docs, site | README quickstart runs verbatim on a clean Linux machine | planned |

## Additions beyond the draft (driven by the Dots / Grok Bot research)

| Item | Why | Status |
|---|---|---|
| Dashboard CSRF / DNS-rebinding defence and device pairing | Local approval endpoints are drivable from any web page ([research §3](research/offerings-and-failures.md)) | local protections, single-use pairing UX, revocable device management, and experimental local Linux desktop browser handoff are implemented; direct remote bind requires `--allow-remote` and TLS. Authenticated PTY/physical desktop controls, phone browser handoff, tunnel validation, and live network/device tests remain open |
| **Rehearse** (dry-run) mode: mutating actions simulated and logged | Grok Bot: "no dry-run mode; testing performs real work" | done - enforced by the tools (`tools/base.rehearsed`, `safety.is_read_only`), not just the prompt; `tests/test_rehearsal.py` checks the disk, memory and approvals. (An earlier version only added a sentence to the prompt: no tool honoured it.) |
| **Working folder** per bot: the run's workspace is a folder of yours, validated hard, persistent across runs | Grok and Dots bots work on your real data; a fresh empty workspace per run made file-based bots a demo | done - `workdir.py`, [bot-config.md](bot-config.md); `tests/test_workdir.py` |
| Workspace continuity choice: fresh per run by default, private Hutch-managed folder per bot, or validated existing folder | Preserve explicit per-run isolation while allowing safe file continuity without forcing every bot to share a path | done - `Bot.workspace_mode`, API/CLI/settings; private immutable-ID directory under state; `tests/test_workdir.py`, browser captures in `realignment/artifacts/managed-workspaces/` |
| Role templates (sales, PM, marketing, analytics) in the gallery | Team Bots ships role templates | planned |
| **Model switcher** in the chat composer + all-models dialog, one-message override with explicit save-as-default action | A chat product switches models from the composer; ChatGPT shows deprecation notes there, Hutch shows fit, cost and what is missing | done - `modelchoices.py`, `static/model-switcher.js`, [models.md](models.md); browser-tested, desktop/tablet/phone |
| Approval webhook notification | Dots / Grok are reachable when you are away | planned |
| Pulled forward from *Later*: UI-10, UI-11, UI-13, SR-11 | Memory opacity, spend opacity, mobile, and audit are the loudest complaints about the two reference products | planned |

## Connections and integrations (added at the product owner's request, 2026-10-07)

Subscription plans such as OpenCode Go and the Xiaomi MiMo Token Plan, and the integration breadth that Dots
(4,000+ plugins) and Grok Bot (Slack, routines) advertise. Details: [connections.md](connections.md).

| ID | Requirement | Status | Where |
|---|---|---|---|
| CN-1 | Named connections, each with its own key, usable as `<connection>/<model>` | done | `connections.py`, `providers/connection.py` |
| CN-2 | Keys from an env var or a 0600 file; never in the database, transcript, page or API | done | `ConnectionBook.key`; test greps pages + DB for a planted secret |
| CN-3 | Required headers: own User-Agent and a stable session id per conversation; standalone runs fall back to their run id | done | `ChatRequest.session_id`, both HTTP providers |
| CN-4 | Billing modes: per-token (priced), subscription / free (flat, still ledgered) | done | `PriceBook.flat_providers`, `usage` table |
| CN-5 | Declared allowance enforced before the call; warning at 80% | done | `SpendGuard.quota_refusal`, `quota` log |
| CN-6 | Terms notice acknowledged before first use; re-ack when it changes | done | `ConnectionBook.ack_status`, runtime fails fast with the fix |
| CN-7 | Protocol per model (openai-chat / anthropic); Responses API restricted to the fixed Sign in with ChatGPT route | partial | `openai-responses` is implemented only for the opt-in SIWC route; other connections reject it. Per-model capability verification remains pending. |
| CN-8 | Test a connection without spending tokens | done | `check_connection`, `hutch connections test` |
| CN-9 | Consumer-app cookie/session reuse explicitly unsupported; official ChatGPT local-app token-sharing is a separate eligibility-gated preview | done | policy and route boundary documented in connections.md; SIWC is opt-in and does not reuse another app's credentials |
| IG-1 | MCP client (stdio): bots can use MCP tools, all behind the approval gate | planned | |
| IG-2 | Inbound webhook trigger for a bot | planned | |
| IG-3 | Outbound notifications (approval needed, failure, result) to a webhook | planned | |
| IG-4 | "Save this run as a bot" (routine capture without a recorder) | planned | |
| IG-5 | Connect a named Google Calendar account for availability and event lookup; event creation is a separate exact-action approval | partial | Local read-only installed-app OAuth/PKCE, Secret Service refresh-token storage, typed API and per-Bot selected-calendar broker are implemented. Google authorization itself is read-only account-level, not provider-scoped per Bot. Titles/times/locations go to the model and run history; descriptions/attendees do not. Live account, consent-screen verification and event-write approval remain unverified/unbuilt. |
| IG-6 | Connect Gmail with separately selectable read and send abilities | partial | A private-preview read-only search uses the owner's Google Desktop OAuth client and restricted, account-wide `gmail.readonly` scope; it returns bounded sender, subject, date and snippet fields to a Bot only when its built-in runtime uses loopback Local inference routes without hosted fallbacks. Refresh tokens are kept in Linux Secret Service; local previews and query terms remain in run history. No Gmail send/write path exists. No live Google account was tested; public release remains unavailable until applicable Google scope verification and any required security assessment are complete. Calendar consent remains separate. |
| IG-7 | Connect a Microsoft Outlook account for calendar and mail tasks | partial | Outlook Calendar has an experimental local public-client PKCE flow using delegated `Calendars.ReadBasic`; one verified calendar can be granted to each Bot and read-only event fields are bounded. Separate Outlook Mail OAuth requests delegated `Mail.Read`, and each Bot can search one mailbox for up to ten messages across folders, including Deleted Items and Clutter, returning only sender, subject, received time and a bounded preview. Both features lack live account/consent verification; calendar writes and mail changes remain unavailable. |
| IG-8 | OAuth accounts and per-Bot grants are named, revocable and least-privilege; refresh credentials stay outside the application database | partial | Google and Outlook Calendar/Mail refresh credentials use Linux Secret Service; credential-free account/grant metadata is in SQLite so Hutch enforces each Bot's selected-calendar or mailbox boundary. Outlook Mail has a separate token namespace and Mail.Read grant. Gmail has a separate `gmail.readonly` token namespace and a narrower Hutch tool response, but Google's OAuth scope is still account-wide and broader than the fields Hutch returns. Disconnect removes local credentials/grants; Google revocation is requested and reported, while Outlook provider consent must be revoked separately by the owner. Live provider accounts and consent remain unverified. No browser-cookie or CLI-token import. |
| TP-1 | Role templates (sales, PM, marketing, analytics, support, ops) | planned | |
| TP-2 | Bot customization: persona/tone, reusable skills, delivery target | planned | |

### Owner-requested conversation and personal-account features (2026-10-09)

These requirements were added after the original realignment plan. They are product scope, not claims
about current behavior. The first delivery order is typed chat choices, a staged chat-led bot draft,
then account integrations. The order keeps user experience work testable before adding long-lived
third-party authority.

For integrations, Hutch must show which account and operation a bot can use, keep credentials out
of prompts/transcripts and the SQLite database, scope access per bot, and revoke it from Connections.
Every external write is a fresh immutable approval containing the account, destination, exact
payload, and expiry; a conversation choice never grants that authority. OAuth must use an explicit
user-delegated flow suitable for a local app. The provider's current scope and review requirements
must be checked before implementation: [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference), and
[Microsoft authorization-code/PKCE guidance](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
Gmail message-body access is a material release dependency because Google's current documentation
classifies the relevant read scopes as restricted and describes verification/security-assessment
requirements.

## Out of scope (unchanged)

A Rust rewrite, messaging channels (Discord, Telegram, Slack, Teams), hardware peripherals, peer-to-peer bot
chat, shared memory between bots, a vector database, multi-user accounts, and a mobile app.

## Open questions from the draft

- [ ] Does the current code match the finalized plan's layout? — *Reviewed 2026-10-07: yes, the v0.1 tree matches the plan; differences are listed in [architecture.md](architecture.md).*
- [x] Main development machine — AMD Ryzen 3 5300U (4C/8T), 22 GiB RAM, integrated Radeon (no ROCm/CUDA), Linux. Sets the CPU-only preset tier.
- [ ] Embedding model, if any — not needed; no vector memory in scope.
- [ ] Vision model for the browser tool vs DOM control — DOM control kept; vision preset exists but is optional.
- [ ] Performance targets realistic? — answered by the recorded baseline in [performance.md](performance.md).
- [x] Is "Hutch" free on PyPI? — checked during the rename (see [research/naming.md](research/naming.md)).
- [ ] **Hosted SaaS vs self-hosted** — the product *shape* mirrors Dots / Grok Bot, but this release is self-hosted and single-user per the draft's out-of-scope list. A hosted multi-tenant offering needs accounts, billing, isolation and a different threat model; it is not started.
