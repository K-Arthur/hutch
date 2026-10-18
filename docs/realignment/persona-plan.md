# Persona, depth and sensitivity plan (2026-10-11)

Task checkpoint for the adaptive-persona slice: voice, proportional response depth, fast banter and calibrated
sensitive-topic boundaries delivered through configuration → runtime → visible response. Worktree
`.worktrees/persona-adaptive`, branch `persona/adaptive`. It now includes local `main` `6221cc2` through merge
`8a63585`; the initial persona base and earlier integration commits below are retained as historical checkpoints.
The user has authorized a tested fast-forward into local `main` when the work is ready. No push or deployment is
authorized. Companion evidence: `persona-research-ledger.md`.

## Approved decisions

- **Combined local work (user-approved):** the branch integrates committed local `main` so the document
  pipeline, ZIP bundles, skills, routines durability and WCAG work sit under one verified tree. Before landing,
  reread local `main`, integrate intervening commits, review the combined diff and fast-forward only when clean.
  Sibling worktrees and the original checkout keep their current state untouched.
- **Compact form UI (user-approved 2026-10-11 after inspected routes):** a response-style form beside the
  standing-directions field in assistant settings, plus scoped conversation/next-reply controls in chat
  options. Hutch's existing identity, tokens and components are fixed; no rebrand.
- **Scope:** preference precedence current turn → conversation override → user override (per agent) → agent
  preset → application default, with explicit off/false/zero/reset round-tripping and no automatic durable
  preference inference.

## Fixed constraints

- Voice, depth, grounding, safety boundaries and tool authority stay independent. No "safety off" mode, no
  harmful-compliance retries, no concealed model switches, no broad silent rewrites.
- Versioned typed profiles/preferences/plans. Each turn snapshots behavior at run start; material facts,
  evidence and output contracts are retained; reevaluation happens per turn, never as stale consent.
- Clear banter resolves locally where possible; no extra model pass solely for style; target p95 ≤20 ms
  excluding inference and necessary checks.
- Preserve existing data, concurrent edits/staging, adaptive context, tools/MCP, routines, artifacts,
  grounding and modest-device usability; no replacement framework or new dependencies without need.

## Slices

| Slice | Scope | Evidence gate |
|---|---|---|
| A. Integration | merge `ab1929e`; combined tree | focused suites pass; full suite/browser classified separately |
| B. Contracts + persistence | typed versioned persona/preferences/plan records (typed JSON on Bot/Run unless a migration proves necessary); transactional revision-aware writes; explicit scope/reset; write-once plan snapshot at common engine start | contract, migration and conflict tests |
| C. Runtime | subordinate bounded guidance into the existing builtin prompt before estimation; local banter resolution; completion validation so truncated/empty answers cannot present as final success; tool governance, output contracts and provider parameters unchanged | regressions incl. source-traced newest-context loss and incomplete-final-success |
| D. UI | approved compact form; temporary vs durable changes; unsaved/conflict states; accessible validation | actual-app browser workflows at 360/768/1440 |
| E. Verification | targeted then broader combined checks; independent read-only review; measured routing overhead; honest boundary labels | review result and measurements recorded |

Progress (2026-10-11):

- `ab1929e` integration merge; `b9dc523` plan, research ledger and UI-route records.
- `86fb19a` conversation context now spends its budget from the newest turn backwards, so recent
  corrections survive a bounded window (regression: `test_conversation_context_budget_keeps_the_newest_turns`).
- `83b3f89` empty and cap-truncated final answers can no longer report success; partial text stays visible
  (regressions: `test_empty_final_answer_is_not_a_success`, `test_length_truncated_final_answer_is_preserved_but_not_a_success`).
- Combined focused check on this tree: **246 passed** in 138.71 s (skills, routines durability, documents,
  runtime, builtin runtime, conversations, migration, delegation); log at
  `/<local-path-redacted> Full suite, browser suite and live checks remain unrun.
- `20958e3` slice B: versioned sparse response-style contracts (`src/hutch/persona.py`) with precedence
  resolution and per-field provenance; typed Bot/Run fields; a conversation `persona` column (schema v51);
  revision-guarded, idempotent saves with explicit reset; `GET/PATCH /api/v1/.../persona` resources; a one-turn
  `persona` on message submit; and a write-once resolved plan captured at run start (reused on retries,
  fail-closed on unreadable or newer state). Evidence: 17 persona tests, updated delegation/migration fixtures,
  and the **full offline suite: 1879 passed, 1 skipped** (log at
  `/<local-path-redacted> browser suite and live checks remain unrun.
- `0d91ed8` slice C: the write-once plan is rendered locally and appended to the builtin system prompt as
  subordinate guidance (wording only; sensitive topics stay plain and steady; playfulness only in clearly
  playful turns, re-decided every turn). No style-only model pass; measured local resolution + render p95
  **0.006 ms** (500 samples) against the ≤20 ms target. Evidence: guidance/render tests, prompt-wiring tests
  with and without a plan, and 146 adjacent runtime/offline/delegation/conversation tests.
- `38974d5` slice D: the approved compact form in assistant settings (beside the standing directions) and
  scoped this-conversation / next-reply controls in chat options, with per-field origins, explicit reset,
  unsaved state, and revision-aware saves that keep the person's edits on conflict. Real-app verification:
  **15/15 browser checks** (Chromium 153.0.8010.12, no model route, no model calls, no page errors) with
  screenshots at 360/768/1440 and a trace in `docs/realignment/artifacts/persona-ui-2026-10-11/`
  (reproducible via `docs/realignment/capture_persona_ui.py`); static-asset guards and persona suites pass
  (59 tests). The full browser e2e suite and live-model checks remain unrun.
- `f35d8fa` review hardening after an independent read-only review of all persona commits: the origins
  surface now describes the value actually shown (unsaved edits, next-reply scope, post-conflict reloads),
  a stored plan written by a newer Hutch fails clearly (`persona_unavailable`) instead of surfacing as a
  user stop, and a stale whole-document bot save can no longer roll back the revision-guarded style.
  Regression tests: stale-document guard, unreadable conversation state, newer stored plan. Browser
  evidence regenerated with **20/20 checks**; focused regression batch **338 passed**.
- Browser-suite classification (2026-10-11): the full `tests/e2e` suite on this tree reports **26 failed,
  172 passed, 8 teardown errors**; a clean run of the same suite at the pre-persona merge `ab1929e` (scratch
  worktree, isolated basetemp) reports **27 failed, 171 passed, 8 errors**. The 8 teardown errors are the
  **same set**; the base-only failures are the two order-sensitive tests already documented as pre-existing
  (`test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` and
  `test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences`, both passing here); one test
  failed only in this tree's full run (`test_large_idle_roster_stays_compact_and_remains_searchable_and_keyboard_accessible`,
  an untouched roster surface) and **passes in isolation on both trees** — a suite-order flake, not a
  persona regression. The suite regenerated 479 tracked evidence files; all were restored to their committed
  bytes and no regenerated captures were kept.

Review follow-ups (status after the profile-compatibility slice):

- Bot persona storage now carries `persona_profile_version`; old unversioned documents remain v1-compatible.
  `Bot.from_store_json` isolates invalid/future profiles per assistant, keeps the original payload across
  unrelated saves, and prevents applying it. New runs fail with an agent-specific `persona_unavailable` error.
- `persona_preset` has no production writer yet (nothing ships an agent preset); the "Assistant preset"
  origin appears only if a template or future flow sets it.
- The persona flow has no committed test inside `tests/e2e/`; the reproducible capture script is the current
  browser regression vehicle (the full suite itself has now been classified against the pre-persona base).
- Live-model evaluation of humor, adherence and boundary calibration remains unrun (no authorized route).

## Acceptance budgets

| Check | Budget |
|---|---|
| Banter fast path | no extra model pass solely for style; local resolution target p95 ≤20 ms excluding inference/necessary checks |
| Precedence and reset | deterministic tests for each level and for off/false/zero/reset semantics |
| Snapshotting | mid-run changes never alter the in-flight turn; no stale consent reuse |
| Context preservation | newest user corrections and material facts survive context budgeting |
| Completion honesty | truncated/no-tool/empty answers cannot present as final success |
| UI | validated controls with scope/origin/inheritance/reset; 320/360/720-effective/768/1440 verification; unsaved and conflict states visible |
| Evidence honesty | unrun live-model checks are labeled; deterministic tests are never presented as live evidence |

## Integration notes

- Merge `ab1929e` integrates local `main` `4ac6041` (556 files, +8,245/−599). Additive conflicts kept both
  lineages: `Bot` keeps its tool allowlist plus `skills`; the tool registry imports skill and document tools;
  both changelog entry sets are retained.
- Conflicting browser capture artifacts resolve to local main's canonical set (`canonical_capture_set: main`
  in the integration manifest); both complete sets are archived under
  `/<local-path-redacted> (local scratch, with `manifest.json` and SHA-256 checksums),
  outside the repository.
- Focused combined-tree check: **167 passed** in 25.44 s — `tests/test_skills.py`, `test_skill_runtime.py`,
  `test_skills_api.py`, `test_schedule_durability.py`, `test_document_store.py`, `test_documents_pipeline.py`,
  `test_documents_revisions.py`, `test_runtime.py`, `test_conversations.py`, `test_migration.py`; log at
  `/<local-path-redacted>
- Inherited whitespace flags from the incoming side (CSV fixtures, one `app.js` line, one `documents.py` EOF
  blank line) are pre-existing content and were left untouched.
- Baseline of the actual app before persona work: `/<local-path-redacted> (isolated state,
  Chromium **153.0.8010.12**, 360/768/1440 screenshots, DOM, trace; no model calls). Standing directions
  already use a textarea; dedicated persona/depth controls do not exist yet.
- Local `main` is 473 commits ahead of `origin/main` (`8d71f8a`); all work stays local.

## Resume checkpoint (2026-10-11, current execution)

- The clean `persona/adaptive` worktree continued from `666edcd`. Local `main` had advanced to `6221cc2`,
  which adds the mainline schema-v51 pending-question guards, unified tool protocol, and updated provider and
  runtime contracts. Merge `8a63585` integrates that mainline commit; the root checkout still has its unrelated
  visual artifact changes and untracked notes, which were not modified.
- Integration keeps mainline `_migrate_51` intact and adds an idempotent v52 repair that ensures its v51
  guards and adds `conversations.persona` only when absent. Mainline captures remain canonical for filenames
  changed on both sides; the persona capture set remains present under its own names.
- Combined focused migration/persona/runtime/tool-calling check passed: **188 passed in 67.95 s** using the
  existing documents worktree environment, with pytest temporary files directed to
  `/<local-path-redacted> An earlier run using `/tmp` hit the full 12 GB tmpfs;
  its own pytest directory was empty afterward. Existing `/tmp` caches were left untouched.
- Commit `04b5722` makes provider refusals terminal in provider retryability, startup fallback and runtime
  recovery while preserving availability recovery. OpenCode Go (`opencode-go/mimo-v2.6-flash`) made the small
  provider-contract edit and ran `tests/test_providers.py` (**39 passed**); the independently reviewed startup
  and runtime guards then passed with provider tests (**106 passed**). The change also has regressions proving
  refusal does not invoke fallback from startup or recovery. No expensive Go model or paid API credential was
  used.
- The profile-compatibility slice adds `persona_profile_version` to Bot storage and a tolerant per-Bot reader.
  Invalid and future profiles stay out of runtime composition, produce an assistant-specific settings/run
  error, and are preserved verbatim if an unrelated Bot field is saved. The roster still returns valid sibling
  assistants. The integrated persona/runtime, Bot/workdir, general store and API batch passes (**115 tests**).
  An earlier run had one test-message expectation mismatch, corrected and followed by a clean combined rerun.
- The v2 profile contract now supports the three named presets, independent Auto/Brief/Standard/Detailed depth,
  Off/Subtle/Playful humor, and bounded customization while preserving v1 `tone`/`banter` and `thorough` values.
  Preset selection clears only same-scope legacy tone/joking values when no explicit v2 override accompanies it.
  Focused checks passed: persona contract/API/runtime **33 passed**, runtime and general API **124 passed**, and
  Bot workdir/store **42 passed**.
- UI slice: assistant settings now present the v2 preset/depth/humor controls plus bounded optional wording
  preferences. Conversation controls save with revision-conflict recovery; next-reply controls remain
  browser-local and affect only the next send. The real-app Chromium regression exercises save/reset, dirty
  state, keyboard save, concurrent assistant and conversation edits, next-reply isolation, and zero
  model/network calls on control changes. Screenshots and Playwright trace are retained under
  `artifacts/persona-ui-v2-2026-10-11/`; detailed manual inspection is in `persona-ui-visual-review.md`.
  It covers 320/360/768/1440 CSS pixels and a 720 × 480 effective layout viewport representing 200% reflow
  at 1440 × 960; the browser runner could not apply native browser zoom. Focused persona/builtin-runtime checks
  passed (**100 tests**) and the browser regression passed (**1 test**). Live examples and the inspector are
  not part of this UI slice.
- Contextual run-plan slice: new run snapshots now resolve intent, contextual depth, audience, grounding needs,
  humor eligibility, output contract and up to four label-only diagnostic reasons before the run starts. The
  classifier examines a maximum of 8,000 request characters, uses current-turn wording plus the presence of a
  prior assistant response, and adds no model call. Version-1/2 plans keep their prior depth and retry wording.
  Tests cover low-risk humor, sensitive/current requests, recipient and structured outputs, bounded diagnostics,
  context-gated correction signals, and the engine's persisted snapshot. `tests/test_persona.py` and
  `tests/test_runtime_builtin.py`: **116 passed** in the final combined run; the persona-only recheck also passed
  (**49 tests**). A separate 500-sample local
  resolution-and-guidance run measured **0.0416 ms p50 / 0.0520 ms p95 / 0.4883 ms max**, below the 20 ms local
  target. These are not provider latency or response-quality results. Tool routing, answer-scoped rewrite
  execution, live preview and inspector remain
  future work.
- Execution-purpose foundation: `Run` now distinguishes `task`, `bot_draft`, and `conversation` from the
  `tool_access` ceiling. Legacy stored drafts infer their prior `bot_draft` purpose; the review-only wording
  and one-response limit remain exclusive to that purpose. The separate conversation prompt exposes no tool
  schemas and refuses provider tool calls without executing them. Focused runtime checks passed (**4 passed**),
  and the Bot-purpose-draft API test passed (**1 passed**). The combined persona/runtime/engine and Bot-draft
  API check passed (**131 tests**). A local OpenCode packet pinned to `opencode-go/mimo-v2.6-flash` inspected
  the requested files but made no edits after about two minutes; it was stopped without retry.
- Banter routing: only a new interactive chat run with explicit humor intent, safe humor eligibility, no grounding
  needs, freeform output, operator audience, no selected skill, no rehearsal, and no delegation is downgraded to
  the `conversation` execution purpose. Its persisted capability snapshot records `tool_access=none`; the runtime
  sends no tool schemas and skips pending-action context lookup. Current facts, sensitive cues, analytical work,
  personal/workspace references, and structured/recipient output stay on the normal task route. The engine/runtime
  final combined persona/runtime/engine and Bot-purpose-draft API check passed (**138 tests**) after adding the
  personal/workspace-reference guards, explicit purpose/tool-access consistency checks, and the no-action-context
  regression. Provider recovery may still retry for availability failures;
  one inference is the ordinary successful path, not a network-attempt guarantee.
- The combined offline suite at `04b5722` completed with **1,989 passed, 2 failed** in 525.57 s. The Unix
  socket test failed only because the long test temp path exceeded `AF_UNIX` path length; rerunning with a short
  cache root made it pass. The other failure, `test_the_shell_cannot_see_the_real_home_or_any_folder_outside_the_workspace`, also failed on clean
  integration commit `8a63585` with the same observed `/home` visibility and is therefore an inherited sandbox
  environment failure, not a persona change. No assertions were weakened. The existing `/tmp` contents were not
  removed or altered.
- Static examples: added fixed, labeled Direct/Warm/Dry Wit samples plus a separate Brief/Detailed pair. The
  actual-app Chromium regression verifies keyboard disclosure, unchanged authored text after unsaved control edits,
  expected grid layout and zero inference requests at 320/360/720×480/768/1440; screenshots and trace are inspected
  under `artifacts/persona-static-examples-2026-10-11/`. Impeccable reported only three unchanged shared-style advisories.
  A low-cost OpenCode review was attempted with `opencode-go/mimo-v2.6-flash`, but stopped while discovering unrelated
  MCP tools before returning code findings; independent review remains outstanding.
- Remaining acceptance: update marketing claims/screenshots; finish combined offline/browser checks and bounded model
  evaluation. The adapter-receipt implementation and image-input availability audit are now recorded below. No separate
  supported
  Hutch Go connection is configured, so Hutch product-path response quality and model latency are unverified.
  The device OpenCode CLI did authenticate and run the low-cost MiMo Flash development task; a later bounded contract
  edit did not finish before its cost-limited stop, so implementation continued locally. A separate, pinned adapter
  receipt packet read the relevant source but did not return a diff after about two minutes and was stopped; no code
  or test result was taken from either stopped session. Its credential store has not been imported into Hutch. Keep
  future packets narrower and do not repeat either unchanged attempt.

- Answer-rewrite API/runtime slice: the versioned conversation endpoint accepts typed Shorter, Go deeper, and Less
  banter requests anchored to a succeeded answer in the same conversation. It snapshots the source request and answer
  as bounded untrusted context; rejects stale, failed, oversized, unanswered-question, missing and cross-chat targets;
  resolves source safety/output cues; and executes with no tool schemas, workspace path or action context. The tool-free
  runtime refuses provider tool calls. Final focused persona/runtime/conversation verification passed (**155 tests**).
- Answer-rewrite chat UI slice: completed built-in answers now expose **Shorter**, **Go deeper**, and **Less banter**.
  The actions use the typed answer-scoped endpoint, leave composer text/selection and one-turn style state intact, and
  preserve reader scroll and keyboard focus across feed refresh. They are absent on failed, pending-choice, oversized
  and non-built-in answers; the completed OpenCode fixture retains its normal answer UI without advertising rewrites.
  The real-app browser regression passed in Chromium 153.0.8010.12 with no provider/model call: **0** page errors,
  console errors, failed local responses or external requests; one explicit correction POST with the selected answer
  id; **44px** action targets and **9.92:1** measured text contrast; no horizontal overflow at 320, 360, 768, 1440,
  or 720×480 effective CSS pixels. The settings and rewrite browser regressions pass together (**2 tests**).
  Screenshots, trace and detector output are inspected and retained under
  `artifacts/persona-rewrite-ui-2026-10-11/`; details are in `persona-ui-visual-review.md`. Live response quality,
  human review and native browser zoom remain unverified.

- Local answer-feedback slice: completed built-in answers now expose **Helpful** and **Needs work** ratings, one
  optional fixed reason, and **Clear**. A new additive v53 table keeps only the latest bounded rating per answer,
  with revision tombstones for compare-and-swap conflict handling. Feedback stays in Hutch's local database, is
  omitted from exports, does not alter saved style or trigger a run, and is not exposed through the paired-phone
  capability allowlist. Errors remain actionable; successful saves announce an inline local status rather than
  stacking notifications. Docs now cover settings, privacy, exports, safety and the disabled external runtimes.
  The feedback API, migration/restart and existing-settings/rewrite/feedback browser regressions passed together:
  **6 passed**. Chromium 153.0.8010.12 recorded four expected feedback PUTs at revisions 0–3, no message requests,
  no provider calls, no page/console/response errors and no external requests. Screenshots and trace are inspected
  under `artifacts/persona-feedback-2026-10-11/`; layout, keyboard behavior, 44px targets and contrast are recorded
  in `persona-ui-visual-review.md`. A read-only review was started with pinned `opencode-go/mimo-v2.6-flash`; it
  read the diff but produced no findings before the bounded session was stopped, so independent review remains
  outstanding. This verifies the tested built-in/local workflow; response usefulness and model-quality effects
  remain unverified.

- Explicit live-preview slice: assistant settings now show a local budget quote before the preview button becomes
  available. The owner may preview the visible unsaved draft with a fixed fictional request; only the built-in runtime
  accepts it. Hutch records a standalone `persona_preview` run with the candidate style and saved-profile revision,
  but attaches no conversation, skills, tools or Bot/workspace instructions. Revision is checked again inside atomic
  run admission. The path uses one non-streaming request, the configured model only, a 1,024-token input estimate and
  the lower of 128 output tokens or the Bot's configured limit; it does not retry, escalate or fall back. Unknown
  hosted prices and the ChatGPT plan route without an enforceable response cap are blocked. The API tests cover free
  local budget lookup, durable idempotent replay, stale-profile rejection and a simulated concurrent-save race.
  `test_runtime_builtin.py` inspects the fake Ollama request: fixed prompt, no tools, no standing instructions or
  workspace path, non-streaming, 32-token configured cap, one response; a simulated provider failure stays terminal
  with no fallback attempt. Focused API/runtime/contract tests passed (**5 passed**). The actual-app Chromium browser
  test uses a fixture runtime (no live provider) and passed (**1 passed**): changing controls issues no preview POST,
  the explicit action uses only the draft and revision, saved settings stay unchanged, cancellation ends `stopped`,
  keyboard focus returns to the preview control, and no page, console, response or network errors were observed.
  Screenshots/trace at 320, 360, 720×480, 768 and 1440 CSS pixels are in
  `artifacts/persona-live-preview-2026-10-11/`; I inspected desktop, phone and effective-200%-width captures. All five
  widths had zero horizontal overflow. The combined persona/runtime suite passed (**136 passed in 61.69s**); the
  browser test was rerun after adding a duplicate-activation guard that preserves keyboard focus (**1 passed**). The
  first guard used native disabling and the browser check caught that it dropped focus; the accessible event guard
  preserves focus and ignores duplicate activation. The live Hutch model result, provider adherence, latency and human
  scoring remain unverified because no Hutch Go connection is configured.

- Redacted-inspector and adapter-receipt slice: local tests inspect captured HTTP request bodies for Ollama,
  OpenAI-compatible chat and OpenAI Responses, plus Anthropic SDK message arguments at its adapter boundary; each carries
  the sample's system style guidance with provider-specific field mapping, and compatibility tests keep Pi/OpenCode
  harness routes disabled. Preview calls
  capture only allow-listed adapter/model, request-shape, saved revision and plan-version metadata before provider
  send;
  prompt/response text, credentials, account IDs, endpoints and hidden reasoning are excluded. The existing per-step
  `model_ms`/`queue_ms` are read from run events. Settings now display a collapsed, accessible summary of scope/revision,
  adapter/model, request shape and measured timing. The actual-app browser test checks redaction, keyboard disclosure,
  focus, phone reflow, 320px reflow and no horizontal overflow; screenshots and trace are retained in the live-preview
  artifact directory. The focused adapter/runtime suite passed (197 tests), and the actual-app inspector browser
  regression passed (1 test); source hashes match the retained evidence. The serialized receipt proves Hutch's request shape, not
  provider acceptance or model adherence. Local model/provider quality and human scoring remain pending without a separate
  Hutch provider connection.

- Image-input availability slice: source/API inspection found that conversation messages accept a text `prompt`, the
  built-in runtime creates text-only user messages, and there is no image attachment, upload, or image-content mapping
  in the chat path. Provider capability rows already reported images as unavailable through Hutch; the local Vision
  focus description was the conflicting claim and now says it changes context/residency only. The composer options menu
  names the unsupported state. Pasted image files are prevented from entering the textarea, leave its existing draft
  untouched, and produce a visible status without a messages POST. The task-focus contract and actual-app browser
  regression passed together (**5 passed**), with zero page/console/network errors and no provider request. Screenshots,
  source hashes, viewport measurements and traces for 1440, 768, 360 and 320 CSS pixels are retained under
  `artifacts/persona-image-input-unsupported/`; I inspected all four captures and found no clipping or horizontal
  overflow. A separate, unchanged composer-options browser case still fails its existing phone-width queue-time
  assertion on the current branch and clean local-main commit `63b2712` at the same `1.3s` assertion; its fixture also
  times out during server teardown after the assertion. No assertion was weakened. The independently scoped image-input
  regression passes on desktop, tablet, phone and compact phone.
- Marketing-site slice: extend the existing workflow section with independent voice/depth/humor choices, a real local
  settings capture, authored fixed examples and a separate depth comparison. The FAQ and availability table make the
  authority and text-only image boundaries explicit without changing the site's identity or section structure. The new
  static-site regression and token suite passed (**9 passed**); homepage content and full-site responsive screenshot checks
  passed (**1 + 3 passed**). Inspected Chromium captures at 1440, 768, 720×480 effective-width, 360 and 320 CSS pixels
  have zero horizontal overflow, and the page sent only same-origin GETs. Evidence and source hashes are in
  `artifacts/persona-marketing-2026-10-11/`; full-page captures are in `artifacts/no-mock-setup/site/`. The one detector
  pass reported two existing shared-style radius advisories (17px and 26px), not in the new response-style rules. Live
  provider adherence and human review remain unverified.

- Pre-latest-main integration checkpoint (2026-10-11): the complete offline suite passed (**2,048 passed in
  479.22 s**) with its basetemp under `/var/tmp`; its captured output is retained in
  `artifacts/persona-final-verification-2026-10-11/offline-suite.log`. The complete browser suite before importing
  the latest local main (`63b2712`) reported **29 failed, 181 passed, 8 teardown errors** in 1213.84 s. Compared
  with the earlier `ab1929e` base run, 25 failed cases overlap; the coordinator-specialist and schedule-overview
  failures from that older base now pass, and the previously flaky large-roster case also passed. The run exposed a
  stale persona-inspector assertion that expected the former arrow separator; the rendered labels now use commas to
  meet the repository emoji audit, and the assertion is updated. Focused live-preview and answer-rewrite browser tests
  then passed (**2 passed in 11.06 s**). The rewrite test's detached-locator failure occurred only in the full suite.
  A separate specialist-question UI locator failure did reproduce alone on this branch but passed alone on clean main
  `63b2712`; importing that main change and rechecking this flow is still required. The workflow-pill case also passed
  alone on both trees. The pre-integration browser log is retained at
  `artifacts/persona-final-verification-2026-10-11/browser-suite-pre-main.log`; it includes the now-fixed stale
  assertion and is historical evidence, not the final integrated browser result. The latest main is 10 commits ahead
  of the branch's integration base; it is now included through merge commit `15e1649`. The device OpenCode implementation
  work used the pinned low-cost `opencode-go/mimo-v2.6-flash`; two bounded final review attempts ended with a closed
  socket before returning findings, and no fallback model or paid API was used. Independent review is unverified.
  Hutch's separate Go connection is still unavailable, so product-model adherence, live latency and human scoring
  remain unverified.

- Latest-main integration and final combined verification (2026-10-11): local main `63b2712` is included by merge
  commit `15e1649`. Its event-source v52 and jobs/document-index v53 migrations collided with persona's then-v52
  repair and v53 feedback table; duplicate Python migration names had silently replaced the mainline DDL. The merged
  registry now keeps main's DDL, combines v52 source creation with the v51-shape/persona-column repair, applies
  idempotent job/document and feedback DDL at v53, and adds v54 to repair either legacy main-v53 or persona-v53 shape.
  The migration suite passed (**32 passed**), including a v50 upgrade, both v51 variants through Store startup,
  main-v52 upgrade, both v53 shapes, retained chat/source/job/document/feedback rows, and repeated initialization.
  The focused source, jobs, monitoring, document-store, persona and builtin-runtime batch passed (**227 passed**).
  The full integrated offline suite passed (**2,116 passed in 495.04 s**); its retained log is
  `artifacts/persona-final-verification-2026-10-11/offline-suite-integrated.log`.

  The full integrated `tests/e2e` run did not complete: it stayed at 33% in the responsive workspace-settings test for
  over seven minutes and was interrupted after 20 minutes. The partial log and interruption are retained as
  `artifacts/persona-final-verification-2026-10-11/browser-suite-integrated-stalled.log`. `/tmp` was at 100% during a
  subsequent focused attempt, causing Chromium/trace `ENOSPC`; no user data was removed. Repeating the task-specific
  suite with Chromium temporary files redirected to `/var/tmp` passed (**6 passed**): live preview, answer rewrite,
  specialist clarification, workflow-pill sizing and Runtime-page browser checks. The result is recorded in
  `artifacts/persona-final-verification-2026-10-11/browser-focused-integrated.log`; the two environment-contaminated
  failed attempts are retained separately. The full combined browser suite remains **blocked** by the stalled/full-temp
  environment and is not reported as passing.

  The updated preview and rewrite captures are in their persona artifact directories. I inspected the preview desktop,
  tablet and phone inspector captures; measured overflow remained 0px at 320, 360, 768 and 1440 CSS pixels and at the
  effective-200%-width viewport. The marketing-site responsive checks, token audit and same-origin/no-inference checks
  remain **verified** from the marketing slice. Provider adherence and human review remain **implemented but unverified**:
  Hutch's separate Go connection is absent, and no paid model/API route or OpenAI OAuth evaluation was used.

  After local `main` fast-forwarded to `a111ffb`, the post-merge clean-worktree smoke check passed (**38 passed in
  22.21 s**: 32 migration tests and 6 focused browser tests). Its output is retained at
  `artifacts/persona-final-verification-2026-10-11/post-merge-smoke.log`. Generated browser artifacts were restored to
  their committed state, and the main worktree was clean after verification.

  Browser failure comparison: with `TMPDIR=/var/tmp`, the integrated workspace-mode settings case failed at all four
  viewport sizes after 30 seconds waiting for the “Workspace Helper settings” heading (**4 failed in 128.38 s**). On
  integration-base commit `63b2712`, its desktop variant failed at the same locator (**1 failed, 3 deselected in
  35.11 s**). The desktop failure is inherited. This comparison ran in the existing runtime worktree, which had
  unrelated documentation changes; those changes were preserved. The full integrated browser suite remains unverified.

## Runtime evaluation checkpoint (2026-10-11)

- `scripts/measure_persona_resolution.py` now reproduces the local routing benchmark. Run `09850b2` used 500 samples after 100 warmups over eight synthetic scenario classes on Python 3.13.15 / Linux x86_64 / AMD Ryzen 3 5300U (8 logical CPUs, 22.78 GiB reported RAM). `resolve_persona` + `contextualize_persona` + `guidance` measured **0.060859 ms p50 / 0.070031 ms nearest-rank p95 / 0.099014 ms max**, below the 20 ms local target. The source and result are `scripts/measure_persona_resolution.py` and `artifacts/persona-runtime-evaluation-2026-10-11/local-routing-latency.json`. This excludes provider, retrieval, network, streaming and end-to-end response latency.
- Live model evaluations remain pending. A dedicated Hutch instance uses a private temporary state directory and the supported local Sign in with ChatGPT flow; the visible browser is waiting at OpenAI sign-in for the user to complete authentication and approve the requested plan-use permission. No model response has been sent. If connected, the evaluation is capped at 12 responses and uses only synthetic prompts; no API key or OpenCode credential is used.
- Final local merge checkpoint: the clean `main` at `eca93aa` fast-forwarded through `5011bab`. The post-merge migration and focused-browser smoke passed **38 tests in 22.15 s** (32 migration tests and 6 browser tests); the captured result is `artifacts/persona-final-verification-2026-10-11/post-merge-final-smoke.log`. The new benchmark script passed compilation and a 16-sample post-merge smoke; the committed 500-sample result passed its schema/target check. `/tmp` was full during the temporary-output attempt, so the rerun wrote no temporary file and did not clear shared temp data. The full integrated browser suite and live provider quality remain unverified as described above.
- Local rollback gate (2026-10-11): `HUTCH_ENABLE_ADAPTIVE_PERSONA` defaults to enabled and accepts explicit common true/false spellings. Disabled mode keeps Bot and conversation profile rows readable and intact, blocks new style-only writes/previews/rewrites/feedback, skips plan creation and low-risk banter routing for new runs, and makes controls read-only. New one-turn values are ignored; previously captured write-once plans survive recovery. Tests cover flag parsing, disabled routing, old-plan recovery, API refusal and disable/re-enable persistence (**74 persona tests passed**); the relevant settings, examples, preview, rollback, rewrite and feedback browser journeys passed together (**6 passed in 22.75 s**). The rollback browser check itself covered 320/360/720×480/768/1440 CSS widths with zero overflow, failed same-origin responses, or inference/provider requests. Inspected screenshots, trace, source hashes and network evidence are in `artifacts/persona-rollback-ui-2026-10-11/`. No database migration or data rewrite was added. A pinned, low-cost OpenCode Go review browsed the diff and runtime paths but timed out at 90 seconds before returning findings; independent review remains unverified, with no model fallback or paid API use. Live model quality and human review remain pending.
- Full offline rerun after `ec50a5b`: **2,122 passed, 6 failed in 456.76 s** (`artifacts/persona-final-verification-2026-10-11/offline-suite-rollback-2026-10-11.log`). Four isolated-worker failures explicitly hit the full `/tmp` tmpfs (`ENOSPC`); no shared temporary files were removed. The OpenCode Go catalogue check also failed alone because its model list was unavailable. The DOCX identical-bytes assertion failed only in the full run and passed alone. None of these failures touched rollback-gate paths; no assertions were relaxed. The full integrated browser suite remains unverified; the six focused persona browser journeys above pass.
- Local-main fast-forward and focused smoke (2026-10-11): `persona/adaptive` fast-forwarded cleanly from `1326fc6` to `a0975d8`. After merge, 32 migration, 74 persona/API, and 74 built-in-runtime tests passed; five of six persona browser tests passed in the combined run, including the rollback UI regression. The remaining answer-rewrite locator detached while scrolling between viewports, then passed alone (**1 passed in 5.60 s**); this order-sensitive browser issue had passed in the six-journey pre-merge run. Combined output is `artifacts/persona-final-verification-2026-10-11/post-merge-rollback-smoke.log`. Test-generated unrelated captures were restored; no code assertions changed.

## Rollback

- Nothing is pushed or deployed. The feature branch was fast-forwarded into local `main` after the clean integration
  checkpoint; the final migration/browser smoke is recorded above. The original checkout and sibling worktrees were
  not rewritten.
- Each slice is its own additive commit; reverting that commit restores prior behavior. Contract or schema
  changes require tested downgrades before landing.
- Mid-run snapshotting prevents a bad preference change from corrupting an in-flight turn; verification uses
  isolated state directories under `/<local-path-redacted>

## Initial evidence boundary

- Run: 167 focused tests on the combined tree; isolated actual-app baseline capture; online source and issue
  inspection (all fetched 2026-10-11).
- At the initial checkpoint, combined offline/browser suites, independent review, model responses, and
  multimodal/long-session checks were unrun. A product-path Hutch model connection is still unconfigured;
  device OpenCode runs use a separate developer credential and do not count as Hutch product evidence.
