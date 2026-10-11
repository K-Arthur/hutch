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
  `/tmp/opencode/hutch-persona-integration/focused-slices.log`. Full suite, browser suite and live checks remain unrun.
- `20958e3` slice B: versioned sparse response-style contracts (`src/hutch/persona.py`) with precedence
  resolution and per-field provenance; typed Bot/Run fields; a conversation `persona` column (schema v51);
  revision-guarded, idempotent saves with explicit reset; `GET/PATCH /api/v1/.../persona` resources; a one-turn
  `persona` on message submit; and a write-once resolved plan captured at run start (reused on retries,
  fail-closed on unreadable or newer state). Evidence: 17 persona tests, updated delegation/migration fixtures,
  and the **full offline suite: 1879 passed, 1 skipped** (log at
  `/tmp/opencode/hutch-persona-integration/offline-suite-sliceB-final.log`); browser suite and live checks remain unrun.
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
  `/tmp/opencode/hutch-persona-integration/` (local scratch, with `manifest.json` and SHA-256 checksums),
  outside the repository.
- Focused combined-tree check: **167 passed** in 25.44 s — `tests/test_skills.py`, `test_skill_runtime.py`,
  `test_skills_api.py`, `test_schedule_durability.py`, `test_document_store.py`, `test_documents_pipeline.py`,
  `test_documents_revisions.py`, `test_runtime.py`, `test_conversations.py`, `test_migration.py`; log at
  `/tmp/opencode/hutch-persona-integration/focused-mergecommit.log`.
- Inherited whitespace flags from the incoming side (CSV fixtures, one `app.js` line, one `documents.py` EOF
  blank line) are pre-existing content and were left untouched.
- Baseline of the actual app before persona work: `/tmp/opencode/hutch-persona-baseline/` (isolated state,
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
  `/home/kevina/.cache/hutch-persona-merge-20261011`. An earlier run using `/tmp` hit the full 12 GB tmpfs;
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
- Remaining acceptance: add feedback, static examples and explicitly requested live preview on isolated state, and
  redacted request/adapter inspector; update marketing claims/screenshots and remaining user-facing docs; verify
  supported-runtime serialized request receipts and image delivery; and run combined offline/browser checks plus
  bounded model evaluation. No separate supported
  Hutch Go connection is configured, so Hutch product-path response quality and model latency are unverified.
  The device OpenCode CLI did authenticate and run the low-cost MiMo Flash development task; its credential store
  has not been imported into Hutch. Keep subsequent CLI packets narrow and review every diff.

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

## Rollback

- Nothing is pushed or deployed. The user authorized a final fast-forward into local `main`; until acceptance
  checks and the clean-tree review pass, work stays on this branch. The original checkout and sibling worktrees
  are never rewritten.
- Each slice is its own additive commit; reverting that commit restores prior behavior. Contract or schema
  changes require tested downgrades before landing.
- Mid-run snapshotting prevents a bad preference change from corrupting an in-flight turn; verification uses
  isolated state directories under `/tmp/opencode/`.

## Initial evidence boundary

- Run: 167 focused tests on the combined tree; isolated actual-app baseline capture; online source and issue
  inspection (all fetched 2026-10-11).
- At the initial checkpoint, combined offline/browser suites, independent review, model responses, and
  multimodal/long-session checks were unrun. A product-path Hutch model connection is still unconfigured;
  device OpenCode runs use a separate developer credential and do not count as Hutch product evidence.
