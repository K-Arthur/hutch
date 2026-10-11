# Changelog

## Unreleased
- Keep “Jump to latest” in its own reserved row below the transcript so a scrolled chat control cannot cover workflow-card text or collide with the fixed composer. The real local Studio route-card journey now checks WCAG text-spacing overrides, forced-colors rendering, keyboard focus, 44px action geometry and jump-to-latest behavior at 320px; opened screenshots and traces are retained. Actual browser-chrome zoom remains unverified.
- Re-run the complete non-browser test suite in an isolated worktree after fixing configured temporary-root handling: 2,137 passed in 603.70s, including the previously storage-blocked offline worker and delegated-offline paths. Retain the command, source hashes and output log in the dynamic workflow evidence ledger; broad E2E and soak checks remain.
- Place Strict Offline broker sockets under the configured private temporary root instead of forcing `/tmp`. This keeps isolated local workers available when the shared `/tmp` filesystem is full; the complete offline-mode test file passes with `TMPDIR=/var/tmp`.
- Publish a pending workflow question and the workflow's waiting status atomically; missing legacy conversation rows now use the Bot's workflow-mode default. Fix the amendment preview comparison copy and its recommendation text color token, and verify the cancellation label clears the pinned footer at 320px. Focused workflow/event checks pass; broad-suite outcomes and remaining temporary-storage limits are recorded in the dynamic workflow evidence ledger.
- Add paired-phone workflow supervision through the existing remote permission split: `monitor` can inspect redacted summaries, planned structure and discovered instance states; `review` can answer durable question IDs and request revision-checked Stop. The projection omits workflow inputs, results, artifacts, usage ledgers and expansion keys; monitor-only clients avoid review requests. Real SQLite/supervisor/API/browser coverage verifies CSRF and idempotency, local-owner-only planning/probe/policy/amend routes, 390/320px reflow, 44px targets and no page errors. Visual evidence is in `docs/realignment/artifacts/workflow-studio/phone/`.
- Make dynamic workflow joins and results honest: `all_settled` can aggregate explicitly named failed and skipped nodes, returns successful items separately with `complete` and `accepted` facts, and does not hide unrelated failures. `first_success` now fails validation until the scheduler can race and drain discarded work. Terminal workflow results keep node counts separate from declared output groups (`verified`, `partial`, `skipped`, `failed`, `uncertain`); exact independent checks can verify an output, nested-field checks do not certify its whole value, and incomplete aggregates stay partial.
- Complete the bounded verification-repair loop: `on_fail.adopt` names the prior node value to replace (a single check target is inferred for compatible plans), repair workers return a closed-schema `{"replacement": ...}` value, each recheck has a durable round identity, and unchanged output fails as no progress. Completed child results and adopted values are reconstructed after continuation. Also read advisory review fields from the validated structured output, so a valid pass stays advisory instead of becoming a false failure. The real engine/Store path is covered with scripted local responses; live repair-model quality remains unverified.
- Make workflow execution wait for canonical event commits before advancing. Event-write failures abort the owned attempt for recovery; completed effect receipts are replayed only when the immutable bot, tool, arguments and workflow identity still match, and changed operations remain conflicts. The buffered writer now keeps failed batches pending without acknowledging or dropping them, and refuses new events at its queue bound. Regressions cover enqueue rejection, commit acknowledgement failure, a real `write_file` effect across recovery, changed arguments, and a non-lock database error.
- Add read-only amendment previews and a constrained adoption API. Previews require the expected immutable revision and attempt generation, refresh authority, preserve root budget ceilings, report quiescence and pending question IDs, and offer reuse only for settled pure transforms whose full dependency chain is safe. Adoption is separately idempotent, requires a parked workflow with no live child/process, and cancels pending questions only by explicit request. Schema v58 archives the old graph, questions and result snapshot before invalidated nodes are cleared; revision fencing rejects stale callbacks and the existing supervisor continues under the new revision. The owner-local Studio includes a declarative plan/input editor, inspectable preview, explicit question-cancellation choice and adopt action. Draining active work, terminal-run adoption and reuse beyond pure transforms remain open. API regression coverage is in `tests/test_workflow_api.py`; browser interaction and responsive captures are in `tests/e2e/test_browser.py::test_workflow_amendment_preview_adoption_is_explicit_and_responsive.
- Add a private-preview workflow explanation after the existing “How it helps” journey, plus a matching availability row and FAQs for Suggest/Auto, exact-profile qualification, stopping/recovery, and workflows versus routines. Copy explains that chat route cards and saved-workflow Auto require selector qualification for the exact profile; both tested local profiles failed. It states that new-plan Auto and routine links are unavailable. Browser claims and refreshed 1440/768/360/320 captures are recorded in `docs/realignment/artifacts/dynamic-workflows/marketing/`.
- Add revisioned, server-persisted workflow-mode overrides per conversation (schema v57). New assistants default to Suggest, while upgrades preserve Off for older saved assistants. Bot Auto scope requires activated saved definitions and explicit limits for nodes, model requests, tokens, wall time and fan-out; conversation overrides cannot expand that scope. Policy mutations are idempotent, compare revisions, and start no work. Studio offers the mode control, saved-workflow card, planned/discovered steps, durable question IDs with keyboard answers, and revision-checked Stop. An exact-profile-qualified chat selector now returns a review-only Suggest card or starts a matching activated saved workflow in Auto after rechecking policy/scope. The routing/runtime set passed 74 tests; the expanded workflow API, conversation, routing and runtime set passed 113. Neither local Qwen3 profile qualified for selector, so they receive no routing tool. Auto for newly generated plans and scheduled workflow links remain unavailable.
- Reconcile the dynamic-workflow schema history at v53 so both the main v51 delegation-question guards and either earlier workflow v51/v52 layout upgrade idempotently, with backup and rollback coverage. Correct automatic recovery's timestamp/status binding, refuse stale orchestration-attempt takeover, and preserve scalar, array, null and falsy node results through run-detail API serialization.
- Add the first dynamic workflow interpreter: saved plans execute as typed, bounded data with durable node and question records, role-specific route checks, a CLI, and typed workflow API. The operator starts saved runs explicitly; saving or importing a method does not schedule it. See `docs/workflows.md`. Chat-turn recommendations, amendments, and scheduled workflow connections remain in progress.
- Extend exact workflow-model qualification (schema v56): complete backend/checkpoint/template/tokenizer/protocol/context/decoding/modality fingerprints now bind role records. Local-owner held-out author and selector campaigns use durable idempotent request/token/deadline reservations; only four passing dimensions qualify the exact profile, failures record negative evidence, and uncertain or incomplete probes never grant authority. Fixture probes verify strict JSON/compiled plans, abstention, separate authority review, exact-profile matching, replay prevention and campaign caps. A bounded Ollama 0.40.3 CPU campaign tested Qwen3 1.7B and 4B Q4_K_M; both failed author and selector requirements. Exact metadata, hashes, per-case results, memory, and latency are in `docs/realignment/artifacts/dynamic-workflows/qualification-campaign-2026-10-11.json`. No local author or selector model is qualified.
- Surface a specialist's clarifying question instead of a produced result (schema v51). A question-asking run ends normally, so coordinator tasks used to report `succeeded` and the question text was attachable as the specialist's finished result. `GET /api/v1/workspace/tasks` now derives `needs_input`, the `current_run_id` and a bounded `pending_question` object (stable id, question, selection mode, options, source run/message) from the task's dedicated specialist conversation; statuses, the stop target and the latest response follow that conversation's newest run, so a task continues truthfully after the owner answers. The coordinator task card shows **Needs your answer** with the specialist identity and inline, keyboard-accessible **Send answer**, keeps the result-attach control and **Stop specialist** target honest across the answer run, and announces a waiting question once through the shared polite status region. Attaching the pending question as a specialist result is refused by the message endpoint (409) and by a schema-v51 database guard. Same-bot `delegate_task` children can no longer ask the owner directly, and a child that somehow ends with a pending question returns an explicit needs-input result to its parent. Delegated invocations now carry an application-owned identity — the model step plus the call's position in that response — so an exact retry of a step reuses its original child while two deliberately repeated identical tasks in one response stay distinct instead of silently sharing one child. Local Chromium fixtures (desktop 1440, tablet 900, phone 390) cover the waiting card, keyboard answer, the resolved audit state and the answered question in the specialist chat; no provider or external request was used.

- Make document and file creation a first-class capability (schema v50): a `create_document` tool turns reviewed, typed content specifications into PDF, DOCX, XLSX, PPTX, CSV, JSON, Markdown, YAML or ZIP through deterministic renderers, validates every result with an independent reader before it can be promoted, and commits immutable SHA-256-recorded versions into a durable local store with journalled crash recovery. Downloads are served from the committed version through authenticated loopback routes that re-verify size and hash, carry RFC 5987 Unicode filenames, ETags and single-range support; a `revise_document` tool creates compare-and-swap versions while older versions stay downloadable, and `inspect_document` grounds revisions in the stored source specification. The Studio chat and Files view show document cards with format, version, validation state and preview/versions/download actions; previews are labelled as extracted content or approximate rendered pages (PDF pages render locally via PDFium; office layout renders additionally require an installed LibreOffice and degrade honestly when it is absent). Known failure classes from other products — expiring session downloads, unreachable generated files, preview-versus-bytes drift, formula cells that display zero, and corrupt Office packages — are defended explicitly, with evidence rows E1–E15 in `docs/realignment/evidence-ledger.md`, failure-class research in `docs/research/document-pipeline-failures-2026-10-10.md`, and the verified capability matrix in `docs/file-formats.md`.
- Replace an undefined `--r-control` stylesheet token with the shared `--r-ctl` radius left by the routines-editor merge; the token guard test now covers it.
- Streamline model-provider setup: connect OpenAI API, Anthropic API, or OpenRouter with one provider-specific API key, then discover current model IDs without an inference call. Keep plan sign-in separate, use a collapsed advanced endpoint section, and bundle sourced provider marks locally. Model catalogs and prices remain live/provider-reported, and catalog visibility does not claim tool compatibility.
- Unify tool calling behind one compiled contract per run. Model arguments are now decoded strictly (duplicate keys, `NaN`/`Infinity`, trailing text, absent bodies), validated against each tool's full registered schema, and dispatched once per correlated call; provider call ids are assigned deterministically when missing and reused ids are rejected as a unit. A per-run compilation snapshot records the exact route profile, strategy, schema diagnostics, and catalog/plan hashes in the transcript. A new per-Bot **tool protocol** setting (default `auto`, today's provider-native protocol) adds an opt-in constrained mode over backend-native JSON-schema controls (Ollama `format`, OpenAI-compatible `response_format`) and an explicitly chosen prompt-contract fallback; every mode shares the same validation, approval, and execution path. `GET /api/v1/tool-compatibility` reports route evidence and prerequisites without spending tokens, streaming assembly is strict (repeat/cumulative names, interleaved calls, conflicting ids, bounded growth), and untested routes remain labeled as unverified rather than claimed. Bot settings put the choice beside the model with an on-demand compatibility check (route, per-mode prerequisites, validator, last governed observation); known-unavailable modes are disabled and blocked before saving, and `hutch bot update --tool-protocol` mirrors the setting on the CLI.
- Align settings disclosures on one shared row skeleton: peer rows on the Apps & AI screen and in assistant settings now share left edges, copy sizes, and a Show/Hide action axis, Outlook event creation and Outlook Mail sending sit beside the access they relate to instead of nested inside it (no disclosure inside a disclosure), and layout-bearing inline styles and one-off paddings move onto the spacing scale. A rendered geometry test fails when the axes drift again.
- Resolve undefined Studio CSS tokens: radius, surface, and well references that computed to nothing (square corners on provider choices, task cards, and setup choices; cleared card backgrounds) now use the documented scale tokens, and a stylesheet guard fails when any fallback-less `var()` reference stops resolving.
- Recapture the marketing proof screenshot so the public "Real application" section shows the current welcome screen (OpenAI mark and current roster copy) instead of the retired sparkle glyph.
- Add the Agent Skills lifecycle: discover/import, validate, review/trust by content hash, install, assign to Bots, per-message activation, inspect, update/rollback, disable/uninstall — with a Skills library surface, a Bot assignment + readiness panel, a composer activation picker, `hutch skills …` CLI commands, `skills` API resources and three bundled sample skills. Only trusted, enabled, hash-verified skills reach a run; revocation between submit and start fails closed; `allowed-tools` never grants authority. External runtimes report skills as unsupported. See `docs/skills.md`.
- Add `GET /api/v1/bots/{ref}/readiness`, a shared resolver reporting runtime, model, tools, skills and connection readiness separately, and surface it in each Bot's settings.
- Fix template creation reusing the template singleton's Bot ID, which made the second Bot created from one template in a process collide; template copies now receive a fresh identity. The CLI `bot create` also keeps the template's tools when `--tools` is omitted, and an explicit empty list selects no tools.
- Make advanced assistant usage controls quieter: show work steps and time per task in a short summary, keep token and cost estimates behind an explicit disclosure, and accept minutes in the UI while preserving the seconds-based configuration.
- Tighten chat reply references: discard template indentation instead of rendering it as empty quoted space, and rely on the visible message for ordinary send confirmation so phone toasts no longer cover the composer. Keep notices for rehearsals and queued work.
- Streamline assistant settings headers: keep the assistant name on one line and group chat navigation and the destructive delete action under one accessible options menu.
- Restore shared primary/ghost button contrast after the generated utility cascade, and improve the empty schedule chooser with a clear primary action, real one-line ellipses, and a bounded scrollable assistant list on phones.
- Refine marketing illustrations and phone readability: align feature icons with headings, enlarge small labels, and remove decorative mascot glow rings while keeping the detailed 3D Hutch character.
- Add a separate experimental Outlook Calendar event-creation sign-in and per-Bot calendar grant. Each guest-free event shows its full details for exact approval and is read back before success; uncertain writes are held for reconciliation. The Microsoft scope is account-wide and can change or delete events, while Hutch exposes create-only on the selected calendar. Live Microsoft consent and provider writes remain unverified.
- Add `hutch code login` for the experimental OpenCode coding handoff. It uses OpenCode's supported interactive provider flow in a persistent private profile under Hutch state; coding tasks now check that profile before claiming a handoff and no longer start with an empty per-task auth database. Hutch does not import the regular OpenCode profile, and provider usage remains outside Hutch budgets.
- Keep message entry primary in an empty Studio chat. Put reusable-helper examples
  behind a collapsed setup disclosure, use compact 2D assistant rows, and state
  that opening an example does not start work.
- Compact the Apps & AI connection tiles on phones while preserving full service names, connection states, descriptions, and 44px actions. Refresh source-aligned screenshots after finding older captures did not match current labels or artwork.
- Replace the raw run-number label beside chat replies with an accessible **View work details** control. Keep internal identifiers on the optional details page and give the touch target 44px on phones.
- Refine the app's 2D mascots after review: remove the visor and pale slits, replacing them with two balanced ink eyes placed directly on each of the eight shape-specific silhouettes. The picker previews the final avatar geometry; the detailed 3D mascot remains exclusive to marketing.
- Keep quick assistant setup in everyday language: it confirms the saved AI
  choice, missing app access and recurring work, and approval checks without
  displaying internal model IDs. Model and routing details remain in **Fine-tune
  the details**.
- Add a separate experimental Gmail send-only connection using Google's sensitive `gmail.send` scope. It has its own OAuth account, Secret Service entry, schema-v47 per-assistant grants, and Connections setup; it cannot read mailbox content. Each action shows the exact sender, recipients, subject and body for fresh approval, sends one plain-text request, and holds ambiguous results without retry. Fixture coverage includes OAuth scope, MIME payload, revocation races, migrations, and desktop/tablet/phone/compact-phone browser states. No Google account or provider request was used; public OAuth verification remains outstanding.
- Give the chat title its available toolbar width and move assistant settings
  into the existing chat options menu. Keep approval details tappable above the
  floating jump-to-latest control on phones, and preserve nested review
  disclosures during transcript refresh.
- Keep ordinary assistant names whole on one sidebar line; use an ellipsis only
  when a custom name exceeds the available row width.
- Suggest a short, professional assistant name from the request and keep its
  inferred task role in an editable note. Show name and role separately in chat,
  settings, the sidebar, and larger assistant rosters; routine Idle text yields
  to the task role, while urgent status stays first. Changing the display name
  no longer changes the task-based local address. Existing combined names remain
  readable, and creating from a chat request still avoids asking for it again.
- Put pending approvals and uncertain outcomes ahead of optional browser-alert
  settings in **Needs you**. Keep notification controls in one collapsed
  disclosure, with a visible On/Off/Blocked/Unavailable state.
- Bring Archivo display headings into the app and supporting pages, so headings now share the
  locally bundled type voice used by marketing while 16px interface copy stays system sans.
  Activity also shows a short recent-work list when history exists.
- Simplify Scheduled work: pause/resume uses plain language, the empty state fits its content, and
  cron syntax plus missed-time behavior sit under **Timing details**.
- Keep the app's simple 2D assistant faces consistent across all head shapes,
  with two balanced, shape-fitted ink eyes; keep the detailed 3D mascot on the
  marketing site.
- Simplify larger assistant rosters by removing repeated schedule and access
  chips, keeping names on one line, and placing service, schedule, action-access,
  and usage details behind one disclosure. Correct narrow-phone card overflow.
- Keep ChatGPT's exact OpenAI Blossom beside its named service. Microsoft Outlook,
  Gmail, and Google Calendar use original category artwork until provider terms
  or required permission for product-icon use are confirmed. Outlook's inbox
  cue is distinct from Gmail's envelope cue.
- Repair the reviewed OpenCode handoff launch path: verify the host's pidfd support,
  return the atomically claimed task record, and preserve the intended exit code for
  cancellation. A Linux pseudo-terminal test now drives a fake OpenCode CLI through
  reviewed launch, isolated edit, Ctrl+C, verified cleanup, and retained status.
- Exercise `hutch code reconcile` with an exact live process identity and after that
  process exits; it refuses to signal a live group and only marks the task interrupted
  after verified disappearance, without making the task launchable again.

## Separate Outlook Mail send setup and provider artwork

- Exposed the existing experimental `Mail.Send` connection flow inside Outlook Mail's optional account settings. Read and send now have visibly separate sign-ins and Bot grants; exact per-message approval and the no-retry/uncertain-delivery limits appear before a send grant can be saved.
- Reused Microsoft's official sign-in artwork unchanged on its authorization buttons. Added OpenAI's unmodified white Blossom beside the named ChatGPT service; the Outlook product icon remains a neutral mail glyph because Hutch has no license to reproduce it.
- Desktop, tablet, phone, and compact-phone fixture captures cover the send sign-in, grant, revoke, and disconnect flow. No Microsoft account or provider request was used.

## Assistant identity and app-card refinement

- Refined the app mascot faces into fitted dark face panels with two soft pale slits. Their placement adapts to all eight head shapes; the separate marketing mascot is unchanged.
- Apps & AI now pairs the unaltered OpenAI Blossom with the named ChatGPT service. Outlook keeps a neutral mail glyph; Microsoft's unmodified sign-in lockup appears only on account-authorization buttons. Gmail remains a category glyph.
- Empty assistant welcomes no longer show “No description yet,” and the composer uses a short “Message…” prompt so a long assistant name cannot wrap it on phones. Background refreshes preserve the async template gallery instead of replacing its cards. Service glyphs have clearer size and color contrast while remaining distinct from provider logos.
- Short desktop windows use a compact first-run welcome so the main setup action can remain in the first screen. Assistant names remain single-line in the roster, and the active selection continues through its one options button.
- The responsive browser checks now cover the short desktop welcome, colored app tiles, shape-fitted oval eyes, selected-row coverage, and single-line names. New screenshots are individually reviewed before this UI slice is committed.

## Everyday activity and task review

- Activity leads with assistant and task counts; reported model tokens and recorded provider cost stay inside an optional **Usage details** disclosure.
- Empty Activity buckets no longer create three competing panels. A single clear-state links to a new chat and past work; populated views show only sections that contain something to review.
- Past work uses the same readable task cards on desktop and phone, with assistant, request, status, time, and a clear way to review the conversation.
- Task details keep the status and conversation in front. Run references, model usage, timing, and transcript verification stay available under **More details**.
- Outlook Mail's optional send setup remains separate from read access and uses Microsoft's official sign-in button. Every new send still requires exact approval; fixtures cover grant, revoke, and disconnect without a live account.

# Outlook email send preview (experimental, schema v46)

- Added a separate Microsoft delegated `Mail.Send` sign-in, token namespace and per-Bot grant. Every new plain-text message requires
  owner approval showing the exact account, recipients, subject and body, including in automatic mode; strict Offline does not expose
  the tool.
- Hutch makes one Graph send request. Ambiguous transport/server responses stay `outcome_unknown` and are not retried; Graph's
  `202 Accepted` is not described as delivery confirmation. Replies, forwards, attachments, CC and BCC remain unavailable.
- Optional setup is also available inside Apps & AI under Outlook Mail account settings; the versioned API remains available.
  Live consent and send behavior are unverified, so the feature is experimental and not a public marketing claim.

## Marketing approval illustration

- Replaced a text checkmark with a local SVG icon so the illustration renders consistently across fonts and satisfies the repository's
  icon/emoji audit. Refreshed the static asset hash and checked the card at desktop, tablet and phone sizes.

## Linux user service

- Added `hutch service install`, `status`, and `uninstall` for the loopback-only dashboard under `systemd --user`. The installer
  uses the active Python environment and Hutch state directory, refuses to overwrite an unrelated or modified unit, and does not
  enable remote access. Uninstall preserves all application data.
- Added operations and quickstart guidance for service logs, user-session behavior, and the fact that systemd status is not an HTTP
  readiness check. Automated tests use a controlled systemd runner; installation was not performed on this machine.

## App typography, icon language, and roster selection

- Added named, rem-based app type roles for body, reading, labels, metadata, and headings while keeping Hutch's marketing display font separate.
- Standardized local outline icon sizing and stroke treatment. Apps & AI and marketing use original Hutch-colored category glyphs beside exact provider names until brand artwork permissions are documented. Assistant names stay on one sidebar line; long names truncate with an ellipsis while the full name remains available in the row title.
- The active assistant's selection background now covers its full roster row, including the single options target; keyboard semantics remain on the assistant button.
- Tightened the phone first-run layout so its main setup action stays visible in the initial 390px screen.
- Browser regression checks cover type scaling, service icons, setup visibility, and selection at desktop, tablet, and phone widths. Individual captures are recorded in `docs/realignment/artifacts/`.

## Personal-assistant first run and app choices

- The empty chat now starts with a real request composer and carries that exact request into assistant setup. Its title and helper text make clear that the person is reviewing the request they just gave Hutch, not being asked to repeat it.
- The request composer offers three one-tap, icon-led starting ideas. Choosing one fills the request for editing; it does not create an assistant or start work.
- Quick setup suggests an editable assistant name and describes its safe starting behavior in everyday language. Model and permissions remain configurable in later steps.
- Assistant settings now open on the editable name and short role only. Standing directions and technical controls share one optional disclosure, and it stays open while settings are saved.
- The Connections view is now presented as **Apps & AI**. Calendar, mail, and reply-service choices use local visual marks with clear names and states; detailed account scopes and setup fields are tucked into an optional disclosure.
- The public website's desktop and phone product captures now match the current app welcome screen, including the example-request icons and current 2D face design. Fleet cards show readiness, schedule cadence, and approval expectations first; model IDs and usage/memory metrics live together under **More details**.
- The large chat's template gallery now leads with common personal-assistant tasks and human names such as **File organizer** and **Meeting follow-up**; stable template IDs remain internal.
- App mascots keep simple, shape-aware 2D silhouettes with a gently uneven pair of dark oval eyes and no separate pupils or highlights. The marketing site keeps its separate, more detailed 3D mascot.
- Browser fixtures verified first-run, request handoff, model selection, app setup and mascot geometry without provider calls.

## Google Calendar event creation (experimental, schema v45)

- Read-only calendar sign-in remains the default. A separate explicit installed-app OAuth sign-in can request Google's `calendar.events.owned` scope; existing read-only accounts remain unchanged because Google's desktop flow cannot add scopes incrementally.
- Owners can grant one Bot access to create guest-free events on one calendar Google identifies as owned by the signed-in account. Every event shows its normalized title, time, description, location, account and calendar for one-time outward approval, even when Bot approval mode is automatic.
- The request has no attendees and Hutch exposes no event edit/delete actions. Hutch reads the returned event ID back and compares title, time instants, description, location and confirmed status before saying the event was created. Transport/server uncertainty or a readback mismatch remains unreplayed and asks the owner to verify the calendar.
- Google warns the selected OAuth scope itself also permits changes and deletion on all calendars the user owns. Consent, public OAuth verification and provider/live-account behavior remain unverified; keep this experimental and do not market it as public support.
- HTTP/API/migration fixtures and a responsive Chromium journey cover the consent split, owned-vs-shared calendar boundary, exact review, grant revocation and uncertain-write handling. No Google credentials or provider calls were used.

## Intent-preserving chat-led Bot setup

- Simple Bot setup can optionally ask the workspace coordinator to clarify only a missing work detail. It asks one bounded question at a time, offers choice cards plus free text, and asks at most five questions before producing an editable proposal.
- The coordinator receives the exact selected user request, only earlier user context chosen by the owner, and the prior question/answer turns. The run stays tool-free; the proposal cannot create the Bot or change its tools, integrations, model, or permissions. The user still reviews and confirms creation.
- Unsent answers and proposals can resume in the same browser for up to seven days; they are not synced across devices, and setup warns owners not to enter credentials. Fixture-backed review and responsive captures are recorded in `docs/realignment/visual-validation.md`.

## Shape-aware 2D Bot faces

- Replaced the small diagonal eye marks with softer upright ink ovals. Eye placement, scale, spacing and subtle tilt now follow each mascot silhouette, and the identity picker previews the exact avatar face. Detailed 3D characters remain a marketing-site treatment.
- Verified every shape against its vector boundary and contrast in Chromium; individually inspected the eight enlarged silhouettes and responsive picker screenshots. See `docs/realignment/visual-validation.md`.

## Per-Bot task focus profiles

- Bot setup and Bot model settings can select or clear a task focus: router, research, extraction, coding, planner, or vision. The choice is persisted and used by the built-in local runtime for its context target and residency policy.
- Choosing a focus never selects or installs a model, changes a provider route, or triggers a run. The review step names the selected focus; an invalid or no-longer-configured profile is rejected instead of silently falling back.
- API and desktop/tablet/phone Chromium tests covered preset listing, persistence, update, clearing, invalid IDs, and the full no-provider-call setup journey.

## Independent responsive UI review

- Reduced Fleet card actions to **Open** plus one 44px options menu for pause/resume and settings. Empty Schedules now offers one explicit Bot chooser instead of presenting every Bot link at once.
- Run history uses readable Bot display names and switches from a dense table to compact run cards through tablet widths. The app's eight simple 2D Bot shapes keep their own face geometry; the marketing site retains its separate detailed 3D mascot.
- Captured Studio, Activity, Schedules, Fleet, Runs, approvals, Connections, Bot settings, run detail, Preferences and marketing independently at desktop, tablet and phone sizes. Fixture results and individual screenshots are recorded in `docs/realignment/visual-validation.md`.

## Conversation organization and local task templates

- Chat options now keep frequent actions visible and group template, export and archive actions under **More**. Keyboard Escape closes the nested disclosure first and restores focus at each level.
- Owners can review and save the first user request to a searchable local library, then edit, reuse or delete it from any chat. Using a saved request only fills the draft; Send remains a separate action. The library lives in SQLite and is included in local database backups.
- Owners can also download a reviewed task-template JSON file and import it into a chat draft. Templates omit replies, tools, files, credentials and conversation identifiers; import never sends or starts work.
- The token source now names shared section-title and wordmark sizes so Studio panels and server-rendered pages use the same roles. The design sidecar and generated CSS were refreshed from the main-branch `DESIGN.md` and shared token file.
- Responsive Chromium fixtures verified the menu, local template review/import, unchanged run count, focus recovery, and desktop/tablet/phone layout. No screen-reader or physical-device validation was performed.

## Quick Bot setup and a calmer large roster

- New Bot now has a one-screen purpose-first path when the workspace or source-chat model route is configured. It reuses that route, suggests a professional name locally, and creates a managed Bot with no tools or schedule, ask-first actions and no initial run. If no route is configured, the user must select one; Hutch never chooses a paid fallback silently.
- The explicit **Customize** path retains model, workspace, tools, memory, schedule, limits, browser handoff, YAML import and full review. A selected chat request remains the only included source unless the user chooses earlier context.
- At ten or more Bots, idle unpinned Bots collapse behind an accessible **All bots** disclosure. The workspace coordinator, attention states, pinned Bots, active work and the current chat stay available. Search and keyboard opening reach the full roster; row actions are visually quieter on desktop and remain visible to touch users.
- App mascot eyes now share a coherent tapered 2D shape and angle; the marketing site's more detailed 3D artwork remains separate. Product research and anecdotal failure cases are recorded in `docs/research/bot-setup-patterns-2026-10-09.md`.
- Responsive Chromium evidence and validation traces are stored under `docs/realignment/artifacts/simple-bot-setup/` and `docs/realignment/artifacts/compact-roster/` after those checks pass.

## Reviewed Bot setup YAML import

- The guided setup accepts bounded `hutch.ai/v1` YAML and fills an unsaved draft after strict safe parsing and Bot configuration validation. It rejects unsafe tags, aliases, duplicate keys, unknown fields and unsupported authority such as endpoint URLs, local folders, command rules, trusted risk or automatic approval. Missing local model credentials do not prevent review; final creation still checks route readiness.
- Every imported value remains editable in the existing setup steps, including tools, memory, schedule, model route and limits. Only the separate final **Create bot** action saves; importing does not create a Bot, start a run, or grant a connection.
- API adversarial cases and desktop/tablet/phone Chromium flow were verified with local fixtures. Screenshots, trace and validation metadata are in `docs/realignment/artifacts/bot-setup-import/`.

## Bounded Bot memory export

- Bot settings can download a consistent JSON snapshot of all fact scopes and revisions, human review/archive decisions, and incoming/outgoing Bot-share records. The endpoint applies explicit count and byte limits, refuses oversize exports instead of truncating, and sends `Cache-Control: no-store`.
- The confirmation describes plaintext handling and excluded data. The export does not contain conversation transcripts, credentials, run events, action receipts, workspace files or artifact bytes. Permanent deletion remains unavailable; archive retains history.
- API, snapshot-boundary and desktop/tablet/phone Chromium download tests passed with synthetic local data and no model/provider call. Screenshots and traces are in `docs/realignment/artifacts/bot-memory-export/`.

## Reviewed OpenCode coding handoff (experimental, schema v39)

- Studio can prepare a durable OpenCode coding task from a completed Bot answer after the owner reviews and edits the exact brief. The Bot must point to an existing Git project; each task is pinned to its reviewed commit in a separate worktree.
- `hutch code run <task-id>` launches the installed OpenCode mini CLI only from an interactive Linux terminal. Its own sign-in, selected model and usage pool remain separate from Hutch. The task profile does not auto-approve and caps steps at 20; shell commands approved in OpenCode retain the Linux user's authority and are outside Hutch's sandbox and permission broker.
- The CLI keeps OpenCode in its own verified process group in the current terminal session, hands over foreground terminal input, then restores it after verified cleanup. Reconciliation now includes the terminal session identity, so a reused numeric process-group ID is not treated as the original task.
- Task state stays visible while process cleanup is incomplete. Process identity includes boot ID and start time; reconciliation never signals stale PIDs. The worktree is retained for human review and is not applied, committed, pushed or published by Hutch.
- Updated product, architecture, safety, configuration, migration/operations and marketing claims. OpenCode's installed configuration loading, permission UX, model execution and live provider usage remain unverified; Pi/OpenCode Bot runtimes remain unavailable.

## Explicit Bot-to-Bot reference grants (schema v38)

- A person can share one exact, current, reviewed memory fact with one named Bot. The grant is a durable, provenance-labelled reference snapshot available across that recipient Bot's chats; it does not transfer tools, accounts, credentials, files or other history.
- Either Bot can revoke the grant. Source revision/archive or disabled memory blocks later retrieval, while the snapshot and its audit trail remain in local database backups.
- Studio chat and Bot settings show incoming/outgoing references and provide reviewed create/revoke dialogs. Typed `/api/v1` endpoints are idempotent and the global change feed contains only participant IDs, not fact content.
- Marketing workflow cards keep paragraph flow natural at desktop, tablet and phone widths; the public copy now describes explicit named-Bot memory grants accurately.
- Offline store/API, restore and responsive Chromium fixtures passed. No live provider calls, screen reader or physical phone was used.

## Dashboard accent polish (2026-10-09)

- Replaced one-sided accents on specialist checkpoint rows and quoted chat replies with subtle full outlines. Legacy Bot cards no longer use colored rails for running or paused state; the visible Fleet keeps its explicit text labels. Reply tests use the professional Bot display name exposed by the interface and assert the quote's balanced border.

## Provider diagnostic budget safety (2026-10-09)

- Standalone `hutch connections test --chat` requests are refused because they bypass shared usage reservations and uncertain-charge reconciliation. Credentials/model-list checks remain token-free; use a normal Bot run for model behavior checks.

## Scoped fact memory continuation (schema v15, local)

- Replace automatic per-bot fact/system injection with explicitly retrieved, human-reviewed chat facts and bounded FTS5.
- Fence proposals against expired/lost ownership, cancellation and terminal state. Preserve immutable revisions and reviews; cross-Bot sharing requires a separate explicit grant.
- Show review/revision/archive in chat and paginated management while memory is disabled. Archive retains history and backups; permanent scoped deletion remains pending.
- Import legacy facts as unreviewed and unscoped, preserve pre-upgrade backups, and verify fact hashes during held restoration.
- Correct the typed resource-change contract to accept restore-state invalidations introduced in schema v14.

All notable changes to hutch (formerly "openbot"). Format follows Keep a Changelog; versioning is semantic.

## [Unreleased]

- Connections can now save a public Google Desktop OAuth client ID locally for both Calendar and the Gmail private preview. The operator environment setting remains authoritative and read-only in the UI; credentials and OAuth tokens are never accepted by this setting. API persistence, environment precedence, fixture sign-in, and responsive setup screens are covered without a live Google account.
- Schema v41 adds an owner-managed, empty-by-default specialist roster for coordinator tasks. Settings save the roster, the dispatch review lists only approved Bots, and storage rechecks membership atomically. Promoting a specialist removes it from the list without automatically approving the former coordinator; removing approval leaves existing tasks and history intact. API, migration, direct-dispatch and responsive browser coverage were added.
- Guided Bot setup now validates and previews a versioned YAML configuration and can download the unsaved draft for review. The
  preview uses the Bot-creation validator, creates no Bot or run, and excludes provider endpoint URLs, local folder paths, and
  conversation-source identifiers; its private text response is not cached. Desktop, tablet and phone browser checks cover the
  preview and download.
- The current compatibility guide now consolidates the experimental Google Calendar, Gmail, Outlook Calendar, and Outlook Mail scopes, per-Bot grant boundaries, local credential storage, model-data movement, and live-verification limits. The typed API contract now lists model capability and workspace-default endpoints and distinguishes them from still-unavailable general workspace filesystem management.
- Connections now shows up to five newest, route-specific tool-call observations from normal Bot runs, with explicit unknown and history-unavailable states; this evidence is not a capability guarantee. Model-capability pagination supports newest-first keyset reads.
- Bot setup labels the generated name as a suggested Bot identity, explains its professional work-role pairing, and keeps the AI Bot identity explicit in chat and lists.
- Schema v37 records one immutable, positive tool-call observation per exact provider connection/account/model/route revision when a normal, owned Bot run with settled or uncertain usage reservation receives a declared call with valid arguments. Added bounded, typed `GET /api/v1/model-capabilities`; no extra paid probe is made, invalid calls do not count, and absent evidence remains unknown.

- Added an experimental private-preview Gmail search connection using an owner-configured Google Desktop OAuth client and Linux Secret Service. It requests restricted account-wide `gmail.readonly`, returns bounded headers/snippets only, and grants access only to built-in Bots whose complete model route set is loopback Local. Hybrid, hosted, remote model endpoints and hosted fallbacks are rejected. No Gmail send or mailbox-write operation exists; public release is unavailable pending Google scope verification and any applicable security assessment. Live account consent is unverified.
- ChatGPT plan routes now require explicit per-Bot, per-account consent before scheduled or coordinator-assigned work. The grant is tied to the current provider routes, rechecked before each model request, removed on disconnect, and excluded from public Bot/snapshot resources. Revoke stops later requests after any in-flight request completes.

### Added

- Run detail and `hutch runs verify <run-id>` now expose a read-only event-chain audit with verified, legacy/partial, and tampered states. Legacy events are clearly unverified; a detected mismatch makes the CLI exit nonzero.
- Schema v34 adds one owner-confirmed fresh attempt from a tightly gated checkpoint for failed/stopped built-in coordinator tasks. The new run gets only the reviewed task brief/constraints and the latest committed assistant text as untrusted progress; prior actions, receipts, selected facts, credentials and tool results do not transfer. Unknown effects, any recorded action, newer specialist work, pending questions, changed permissions, external runtimes and archived chats stay blocked. Exact retries are idempotent. This is not process resume and may use additional model quota.
- Purpose-based Bot names now preserve common hyphenated phrases, ignore trailing request clauses, and use an organizer label for organization requests; suggestions remain local, editable, and stable-address-aware.
- Each optional coordinator refinement request produces one review-only Bot-purpose draft from the exact originating user request, the current purpose draft and explicitly selected earlier user messages. It runs through normal admission and budget controls with no tools, action authority or Bot creation; the user must apply the editable suggestion. The owner can edit the purpose and request another draft. Material unknowns are called out rather than guessed. Interactive clarification and live model-quality checks remain open.
- The workspace coordinator now has scoped task-drafting guidance and a clearer specialist review: the operator can edit the goal, add an expected deliverable and constraints, inspect the specialist's saved settings, and confirm dispatch while the source request remains linked. Task wording cannot grant access; live model drafting quality remains unverified.

- Experimental Outlook Calendar read access uses a local public-client PKCE sign-in, Linux Secret Service refresh-token storage, and one selected-calendar grant per Bot. Outlook Mail has a separate local PKCE flow and per-Bot mailbox selection, returning bounded sender, subject, time, and preview fields. Microsoft consent remains account-wide and must be revoked in Microsoft settings; no live account or consent has been verified. Calendar writes and all mail changes are unavailable.
- Studio Bot creation now takes four reviewable screens. It reuses the selected latest chat request, suggests an editable purpose-based name and address, carries a configured chat/workspace model route forward, and starts with a managed workspace, no tools and no schedule. Optional capabilities and limits remain available before a complete review; saving still starts no run.
- Schema v32 lets the owner optionally select up to eight current reviewed facts from the coordinator Bot or exact coordinator chat during specialist task review. The exact values and provenance are stored with that task and passed as untrusted run context, never specialist saved memory; the UI previews the serialized 6,000-character bound and warns that provider-retained copies cannot be recalled.
- Schema v31 adds a bounded, append-only, content-free progress timeline for reviewed coordinator-to-specialist tasks. Existing task markers are backfilled from committed events; new markers are written transactionally from the child run's event stream and linked to the task/run. Checkpoint rows reject in-place edits, while deleting the owning task removes its timeline. API responses include the materialized total and latest 16 markers, and the chat task card presents them. This is an audit timeline, not restart continuation: there is no resume action, and unknown effects still require reconciliation. Hidden reasoning, prompts, action arguments, tool output and secrets are not copied into checkpoints.
- Schema v29 adds an experimental coordinator-to-specialist task handoff. The user reviews the selected specialist, its saved model/tools/action policy/workspace, an editable task brief, and optional assumptions before dispatch. The durable parent timeline keeps the source request, coordinator draft, reviewed brief, target settings snapshot, task status and latest specialist reply; opening the specialist chat remains a direct route. Only the reviewed brief and assumptions enter the child conversation, while that Bot's own enabled memory and workspace still apply. Exact retries replay safely, changed payloads conflict, and changed specialist settings fail before execution. Schema v30 lets the user attach one exact successful specialist response to a coordinator follow-up. The immutable transcript/export link records the task and source message, and only a bounded JSON-escaped response enters that run as untrusted context; files, credentials, permissions and memory are not shared. Live external-provider execution, specialist allowlists, resumable checkpoints and plan-level cancellation remain pending.
- Bots now have a human-facing display name separate from their stable local address. Guided setup proposes both from the stated purpose using a deterministic local rule; names remain editable and reviewed, and no model request or run is made for naming. The CLI accepts `--display-name`, and legacy slugs get readable labels. Schema v28 persists workspace coordinator selection; Bot settings can assign that role, the selected Bot opens as the default Studio chat, and the roster marks it.
- Guided setup now pairs a unique friendly teammate name with the purpose-derived Bot role, while the local address stays based on the role. Studio labels the chat as an AI bot so a human-readable name does not imply a person; owners can edit either name independently.
- Legacy success/error notices use a neutral full outline with a semantic icon instead of a colored side rail. The public workflow copy is shorter, and its keyboard skip link animates with a transform while preserving focus and target behavior.
- Experimental Google Calendar lookup uses an owner-configured Desktop OAuth client and Linux Secret Service. The local PKCE flow stores refresh credentials outside SQLite; each Bot is restricted by Hutch to one selected calendar and can read only bounded event titles, times and locations. Google grants account-level read-only scope, and no live account/consent-screen check or event write is claimed. Gmail search is a separate private preview using restricted account-wide `gmail.readonly`, limited to built-in Bots on loopback Local routes; public release awaits Google scope verification and any required security assessment, and no live account consent has been tested.
- Built-in conversation runs can ask durable single- or multi-select questions in Studio. Schema v26 stores the immutable prompt/options and answer link; a selection submits a normal, idempotent user turn and cannot approve or authorize an action. The public workflow page qualifies this as built-in chat behavior. Mixed provider tool-call batches are rejected before execution. OpenCode/Pi and final release validation remain unavailable or pending.
- Studio's composer model picker marks alternate routes as one-message, conversation-scoped overrides and clears them after an accepted send. A separate **Save as Bot default** action validates and updates the Bot route used by later chats and scheduled runs.
- Preferences can set a validated workspace model route and inference mode for new Bots. Chat-sourced and workspace-default choices remain editable in the setup draft; an explicit choice wins. Changing this preference leaves existing Bots, conversations and runs unchanged.
- Studio's New Bot flow can seed an editable draft from the exact user message selected with **Make a bot**, or from the latest user message via the top-bar action. The owner may optionally include up to eight earlier user messages from that conversation; later messages, assistant replies and other chats stay excluded. The selected request and context are shown in the final review and saved as Bot background. A configured non-mock model route from the source Bot is an editable suggestion for the new Bot's saved default. Saving creates no run and does not infer permissions or account access.
- Studio conversations can reply to a specific Bot message. The composer shows a removable, bounded reference; same-chat scope, untrusted quote labelling, stable idempotent retries and transcript/export provenance are enforced by schema v25.
- Experimental local Linux browser handoff now blocks agent typing into detected credential, OTP, payment-secret and token fields before input or durable action creation, redacts browser type values from events/receipts, and prevents screenshots while a conventional sensitive field is visible. People can enter credentials and complete CAPTCHA/2FA directly in the same live browser profile, then resume the current wait without a page reload; Hutch never types secrets or solves challenges. The field detector and live third-party path are not exhaustive or verified.
- Document the Grok Bot message-first named-Bot and coordinator workflow as a product reference. Record Hutch's context-aware task-brief requirements, explicit authority boundaries, durable cross-Bot result delivery, user-reported organization complaints, and the decision to retain per-Bot workspace/browser isolation. No Grok Bot account or live integration was tested.
- Experimental reverse-proxy HTTPS support now requires an explicit trusted proxy address/CIDR, exact public-host allowlist and HTTPS
  forwarding. Untrusted forwarding metadata is stripped, malformed public hosts are rejected, and the capability API exposes the
  configured-but-fixture-tested status. HTTP and WebSocket Origin schemes must match normalized HTTPS. Hutch still does not provision
  a tunnel or claim live remote validation.
- Studio can download a bounded conversation JSON export after showing its scope. It contains whitelisted metadata and ordered message text/provenance; the manifest explicitly excludes credentials, receipts, workspace content, artifact bytes and memory, and warns that message text is copied verbatim.
- Bots can own up to 100 independently timed recurring tasks, each with its own name, timezone,
  catch-up policy and prompt. Settings, per-task v1 CRUD and `hutch bot schedules` manage them;
  older schedule fields remain aliases for the first task. Schema v20 separates occurrence claims
  by task, and schema v21 keeps removed task IDs reserved so occurrence history cannot be reused.
- The marketing workflow now describes named recurring tasks, and the settings journey has
  inspected desktop, tablet and phone captures for add, edit, remove and primary promotion.
- Versioned standalone run submission at `POST /api/v1/tasks/runs` now requires an idempotency key and stores the run, task and replay result atomically. Exact retries return the original run, changed requests conflict, and the legacy run route remains available as a compatibility alias.
- Versioned human resume now requires the current `human_needed` event sequence, a live owner lease and an idempotency key. Each wait episode can be resumed once; stale requests and a second device cannot replay an old click to resume a later challenge.
- Studio chat now places Resume beside the current human-needed event and submits its sequence through the versioned API. Earlier challenges stay visible without an active Resume action; accepted requests show a clear pending state and retries reuse the same per-wait key.
- OpenCode Go Connections now explain the provider-issued API-key handoff without reading OpenCode's private auth files or reusing its login session. Connections also include an opt-in, eligibility-unconfirmed Sign in with ChatGPT preview using PKCE/OIDC, account-specific reauthorization hints, a protected local account store and a fixed streaming Responses API route; local functions use the preview's `additional_tools` input format. Provider-enforced output limits are unavailable, so usage allowances remain estimates.
- Transcript file-delivery intents are now recorded once per committed event batch in the same SQLite transaction. Schema v16 removes the per-event trigger without changing crash recovery, visible delivery errors or FULL-sync behavior.
- Bots can use a fresh workspace per run, a private Hutch-managed workspace shared across that bot's runs and chats, or a validated existing folder. The default remains fresh; managed files survive bot deletion and are excluded from database-only backups.
- Executor health uses a steady status mark with text and connection-state changes instead of a decorative pulse between health checks.
- Studio's working dots now stay steady while the visible label carries the state; server-rendered page headings use a roomier 1.4 line-height.
- Server-rendered live/reconnecting status now uses a steady dot; the text reports connection changes without a continuous pulse.
- Successful `write_file` actions now expose immutable, SHA-256-verified downloads directly in Studio chat without expanding tool details, up to 4 MB per file and 16 MB per run.
- Experimental phone/browser pairing now has a real `/pair` exchange page, a compact paired-device manager in Connections, current-device status, and one-click revocation with a safe self-revoke return. Device session and pairing responses have explicit v1 schemas; the marketing site now describes this path as experimental.
- Optional, user-enabled browser notifications now bring a generic Needs you alert to a background tab. They disclose no chat, bot or action details, and work only while the Hutch tab remains open.
- Full tool outputs clipped from model context are now immutable, run-scoped artifacts with recorded size and SHA-256. The chat provides a direct download; a bounded typed API lists versions, and downloads refuse missing, symlinked, oversized or hash-changed content.
- Per-tool output caps are configurable through the bot API. When output is clipped for model context, Studio shows a source card for the complete verified artifact; opening it serves inert plain text through a hash-checked compatibility route. Artifact limits are 4 MB each and 16 MB per run.
- Owners can explicitly share a verified artifact reference to a selected other chat. Both the source and receiving chat show the active grant and can revoke it; the target gets a provenance-labelled Files entry and a target-bound download. Bytes stay in the source run and never enter the target workspace or model context.
- Experimental `delegate_task` is an explicit per-bot opt-in for the supervised built-in Strict Offline Linux executor. Each child request always pauses for human approval, receives only its task text, gets a private per-run workspace, and inherits the immutable root capability and budget limits. Depth, lifetime child count, steps and duration are bounded; Stop cascades through the lineage. The default global limit supports one child at a time. External runtimes, parallel public child calls and automatic artifact/file transfer remain unavailable.
- Schemas v22–v24 add immutable same-bot run lineage, inherited tree-budget reservations, cancellation intent and a credential-free capability snapshot. The experimental child tool uses these controls only through the supervised Strict Offline Linux executor; historical rows without a snapshot remain ineligible.
- Experimental per-bot `offline` inference mode. Linux workers run in fresh bubblewrap namespaces, including verified network and PID isolation, and send model HTTP through private per-run Unix-socket brokers fixed to configured numeric loopback endpoints. The local IPv4/IPv6/PID probe and fixture Ollama request pass here. Browser/web-fetch tools are removed, provider/proxy environment is scrubbed, and saved connection/key files are masked inside workers; live model-server behavior and provenance remain unverified.
- Per-bot local model-route and Hybrid controls in Settings, the API, and CLI. Local-route mode
  filters hosted models and blocks hosted message overrides/fallbacks, including recognized
  Ollama cloud-tagged names. This setting does not promise strict offline behavior; local services
  and network-capable tools can still use the network.
- Legacy bots on the unavailable Pi or OpenCode executor can be moved to Hutch's built-in runtime
  from Settings after a valid Hutch model route is saved. The API accepts only `builtin`, refuses
  the switch while any run is active, and does not import credentials or sessions from either CLI.
- Marketing headings now describe model choice, approvals and stop cleanup directly; refreshed
  desktop, tablet and phone captures record hashes for the final website source. Fixed a stale
  stylesheet cache tag and added a regression check for local asset hashes.
- A versioned provider compatibility matrix is available at `/api/v1/compatibility`; it separates
  route-level fixture support from unverified endpoint/model capabilities and lists dated sources.
- OpenAI's `max_completion_tokens` is selected only for the exact official HTTPS API host; other
  OpenAI-compatible endpoints use `max_tokens` even when their URL contains a lookalike string.
- Generic provider field errors no longer trigger a duplicate non-streaming request; that recovery
  is reserved for errors that identify streaming/SSE incompatibility. Uncertain charges remain
  reserved, and a different paid route still waits for outward approval.
- Bots may opt into a same-session visible browser handoff on a Linux desktop. Login challenges
  pause only when the person can use that owned browser; Resume reloads and rechecks the challenge.
  Cross-process leases protect each bot's profile and the single local handoff slot. Settings show
  the current host capability reason and headless runs fail clearly. HTTP(S) and WebSocket traffic
  now goes through an owned loopback proxy that re-resolves and pins each connection to a checked
  public address; local Chromium tests cover rebinding across a redirect. Live public destinations,
  non-HTTP browser traffic, headed challenges, and phone handoff remain unverified or unavailable.

### Fixed

- Coordinator task-review request and quoted-answer blocks use quiet full outlines instead of side-tab accent stripes, with responsive evidence at desktop/tablet/phone widths.
- Stopping a delegated run now atomically marks its persisted descendants for cancellation before cleanup begins. The supervisor signals every owned descendant process; queued descendants stop immediately, while owned work remains visibly Cancelling until cleanup is verified. A racing child submission is either included in the cancellation tree or refused by the parent's stored cancel intent.
- Delegated children run only after a fresh outward approval, in a private 0700 per-run workspace with the immutable root capability and budget snapshot. They receive task text only; no parent transcript, browser, host folder or automatic artifact transfer is inherited. Dispatch and parent cancellation remain supervised, and historical children without a capability snapshot fail closed.
- Schema v14 restores database snapshots into a new private directory with old work quarantined,
  original process identities detached from cleanup authority, device sessions revoked and
  schedules paused. Submission, worker and supervisor claims refuse execution until a local
  operator review is recorded. Restoring never signals or modifies source processes. Snapshot
  hashes, migration, transcript/intent validation and installed executor/UI fingerprint checks
  precede activation; credentials, browser profiles and user files remain separately backed up.
- Schema v13 snapshots arguments and reviewed authority before an effect, requires an unexpired
  fence for owned receipt writes, and atomically seals missing receipts with Needs review.
  Receipt storage failure stops further tools. Immutable operator reconciliation records checked
  outcomes separately; it preserves the original status and event chain. Chat and the paginated
  Needs you drawer retain uncertain actions, including historical Done runs with receipt gaps.
- Matching uncertain effects in the same conversation require reconciliation before a new attempt
  can repeat them. The builtin runtime reads bounded current receipt guidance at execution;
  unrelated private conversations retain separate contexts. Legacy arguments remain explicitly unknown.
- Schema v12 enqueues JSONL delivery with committed events, verifies file prefixes and retries
  after restart without duplicate rows. Damaged mirrors are preserved before reconstruction;
  pending errors stay visible without changing a Done run. Delivery is bounded and joined before
  database closure. FULL WAL synchronization makes action prerequisites durable before admission,
  subject to storage honoring synchronization; live power-cut certification remains unavailable.
- Provider settlement/release requires unexpired worker ownership and cannot change the reserved
  run, bot, model, provider or account. Changed duplicate settlement conflicts; uncertain usage
  requires explicit reconciliation. Unresolved holds stay counted across midnight/quota rollover.
- Admit a worker approval and its waiting state atomically. Refuse full-request overwrites and
  expire decisions for lost/stopped execution before they can grant standing permission.

- Queued messages cannot replace an executing or waiting conversation attempt as the main Stop
  target. Older active approvals stay visible beyond the chat window; failed refresh retains
  review details with Retry instead of hiding the control or reporting completion.
  Header Review brings an older request into view; phone attempt labels wrap without clipping.

- Expired leases cannot renew or authorize owner actions, approvals, reservations, progress or
  status changes before recovery. Buffered worker replies validate ownership at commit, and late
  receipts cannot overwrite uncertain outcomes. Worker startup refuses an expired claim.

- Join worker signal listeners on completion and execution errors, and join cancellation cleanup
  before terminal status. Serialize cleanup verification so a stale survivor report cannot win.
- Refuse database closure while the event writer remains alive; preserve its connection and allow
  closure to be retried after it exits. Closing state refuses new buffered events.
- Stop expires pending approvals in its cancellation transaction; later requests expire immediately
  and stale workers cannot admit a new request.
- Remove the production mock runtime and `hutch demo seed`; `hutch init` now creates only state,
  and bot creation requires an actual configured route. Existing mock-route records remain readable
  for audit but fail before worker/action start with an actionable `model_unavailable` result. The
  deterministic scenario runtime is test-only and excluded from built wheels. The website now
  shows an inspected empty first-run capture instead of seeded mock runs or scripted approvals.
- Check restore execution hold before route validation in CLI/API run requests, so held restored
  state reports the required review step even when its historical bot has no usable model route.

### Added
- **Transactional resource replay:** schema v11 adds content-free invalidations with typed pages/SSE,
  history cursors, gap detection and consistent snapshot reconciliation. Silent process commits
  remain replayable; chat/attention updates preserve drafts and focus. Approval admission includes
  its inline review event, and canonical decisions survive a missing worker response. The separate
  JSONL mirror uses schema v12's separate recoverable delivery; no remote-support claim is added.
- **Bounded local inference:** one caller and eight FIFO waiters across Hutch processes. The slot
  releases before tools/human waits, Stop removes queued callers before reservation, and kernel
  ownership expires on process death. Native Ollama rechecks measured memory headroom; fit remains
  estimated and other local protocols lack validated memory admission. Recorded queue time is
  separate from Hutch overhead; chat shows the wait reason. Strict offline modes remain pending.
- **Provider authority and retry accounting:** hosted account/destination changes require a
  per-run outward decision, including from a hosted primary. Reviewed routes cannot change
  during approval or provider creation. Cached credentials refresh before calls; the unsafe
  legacy routing override is removed and basic credentials in endpoint URLs are refused.
  A failed stream retains uncertain usage and each retry reserves another attempt.
- **Exact-action and history repairs:** file approvals bind contents, destination and revision;
  descriptor-based writes refuse symlink or changed-revision destinations. Browser mutations
  bind text, URL and profile and always ask. Strict extra mounts retain their read-only grants
  and reject credential-containing ancestors. Final assistant messages and terminal status commit
  together; sealed runs reject stale reply mutations. See the realignment continuation ledger.
- **Conversation-first navigation:** one bot roster and settings destination; inline action decisions
  and a cross-bot Needs you drawer. Monitor contains Activity/history, with filtered Fleet at ten bots.
  Human and approval waits remain visible during queue-discovery failures; phone reminders occupy
  their own layout row, and an older queued turn cannot hide already executing work.
  Legacy navigation aliases preserve browser Back. Drafts belong to their conversation, stopping bots
  show “Stopping,” and queue failures retain requests. Approval commands carry immutable hashes and
  idempotency keys; expiry waits for server confirmation. See `docs/realignment/navigation.md`.
- **Shared provider usage reservations (partial S5):** schema v10 atomically reserves per-bot tokens, per-run/per-bot currency estimates,
  and configured shared-account quota/cost limits before builtin hosted calls. Successful replies settle actual usage once; uncertain
  outcomes stay held until a terminal run is reconciled from the provider record. Connections page and `/api/v1` expose held values.
  Currency checks are estimates and do not guarantee the provider's final bill. Pi/OpenCode remain disabled; live billing is unverified.
- **Repeatable performance evidence:** the benchmark runner now retains raw repetitions and host/revision/harness metadata; the
  pre-realignment archive and current branch have same-harness captures with a data-quality notebook and explicit sampling limits.
- **Marketing evidence:** remove seeded mock-run imagery and scripted approval controls; replace the product preview with an
  inspected capture of the real empty first-run UI and verify it at desktop, tablet and phone widths.
- **Global transcript replay:** `/api/v1/events` provides bounded cross-run pages and `/api/v1/events/stream` resumes with
  `Last-Event-ID`. A missing or future cursor directs the client to a bounded consistent snapshot and a replay watermark.
- **Canonical conversation persistence and v1 API (partial):** schema v8 imports each old run into a separate legacy conversation;
  new conversation/message/archive commands use atomic `Idempotency-Key` records and reject key reuse with changed arguments. Run
  admission snapshots up to 12 prior messages and 16,000 characters for the builtin runtime. FTS5 searches messages explicitly;
  search results are not injected into prompts. Studio supports durable thread switching and archive. Versioned stop and approval
  resolution also use idempotency keys. `/api/v1` now includes sanitized connection metadata, schedules, explicit capability records,
  and cross-run transcript replay with bounded snapshot reconciliation.
- **Experimental remote pairing:** schema v9 adds single-use 60-second pairing codes and hash-only, revocable device sessions with
  sliding 30-day expiry. Direct off-loopback binding requires `--allow-remote` plus TLS certificate/key. Pairing attempts are
  rate-limited; the phone UI, live control routes, tunnel support and device validation remain unavailable.
- **Fail-closed external runtimes:** legacy Pi/OpenCode selections now stop before spawning a subprocess because their permissions,
  process containment and provider-budget paths are not governed. OpenCode `--auto` and the broken Pi RPC adapter are removed from
  the execution path. Browser profiles and contexts are instance-owned per bot; fixture tests verify separate profile directories.
- **Phone menu keyboard control:** the Studio navigation now keeps Tab inside its full-screen mobile menu, moves focus to the first
  link on open and restores focus to the toggle on Escape. Added a browser regression test and saved desktop/tablet/phone captures.
- **Owned run cleanup and recovery:** production CLI, web, and daemon attempts use worker processes; recovery atomically fences expired
  owners before signalling; process records carry boot/start identity and pidfd cleanup never signals a reused PID/PGID. Incomplete
  cleanup remains visible and retries instead of claiming the run stopped. A leased supervisor coordinates schedule/recovery work.
- **Bounded shell execution:** captured stdout/stderr is drained into a fixed buffer; Linux strict mode uses bubblewrap plus a
  delegated systemd cgroup and fails closed. SQLite migrations serialize across processes, use the online backup API, and have a
  tested restore path. Store shutdown joins registered engine workers before closing the database.
- Composer options collect suggestions, rehearsal and Enter behavior beside the model selector;
  rehearsal labels disclose model calls and reads. Canonical messages, approvals and idempotent
  Stop survive the shared-checkout merge. Options restore focus on Escape; phone primary controls
  have 44px targets, cancelled notices use the actual status and recorded queue time remains visible
  without completed model steps.
- **UI-complaint research** ([docs/research/complaints.md](docs/research/complaints.md#7-ui--interface-complaints-design-signals)):
  documented interface failures across shipped agent UIs — Claude Code's saturated-on-black
  regression, ChatGPT accent churn, Codex role ambiguity, colour-only status dots — with a
  traceability table for the dashboard.
- **Design system** ([docs/design-system.md](docs/design-system.md)): one set of WCAG-AA-verified
  tokens (surfaces, text roles, semantic status colors, radius/type/spacing/motion scales) shared by
  the dashboard, marketing site, and legacy SPA; documented component anatomy for tool lines,
  approval gates, status chips, budget meters, empty states, dialogs, and toasts.
- **Emoji audit gate**: `scripts/audit_emoji.py` (improved Python port of varve's audit-emoji.mjs —
  HTML-entity, escape-sequence, and surrogate-pair detection; greppable waivers) wired into `pytest`
  via `tests/test_emoji_audit.py`. Pictographic emoji and icon-like text characters are banned;
  UI iconography is inline SVG only.
- Runs view: wired status filters and search (previously rendered with no listeners), shareable
  `#/runs?status=…&q=…` state, "show more" pagination, keyboard-operable rows, distinct empty states.
- **Studio shell truthfulness + a11y**: the whole `<main>` is no longer a live region (it announced
  the entire page on every poll); announcements go through a bounded `#live-status` region that
  reports lifecycle changes only — run started/waited/finished, approval required, connection lost.
  The daemon badge no longer claims a hardcoded "live": health is established from `/api/health` with
  a heartbeat and degrades to `reconnecting`/`offline`. A 3-dot working indicator shows while a bot is
  actually computing (never for a waiting-for-human run). Contract tests in `tests/test_studio_shell.py`.
- **Run status labels**: the Studio and server-rendered run lists show lifecycle labels such as
  “Stopping” while owned cleanup is underway. Queued, resource-waiting, recovery and cancellation
  states remain active in the UI; an unknown future status stays visible until the server provides
  its label and terminal bit.
- **Approval review + app-wide attention**: the chat feed and the approvals queue share one
  approval card — the action in plain language first, a "Review details" disclosure (tool, why you
  are asked, reversibility, parsed segments, raw request), the exact scope of an "always allow"
  grant with a pointer to revoke it, and no always-allow for outward actions. Decisions are
  server-authoritative: a stale click that loses a cross-device race reconciles against
  `GET /api/approvals/{id}` and shows who actually decided. Client expiry disables controls while
  checking the persisted outcome. The Needs you drawer carries the count throughout the app,
  and a new arrival is announced once through the bounded live region. Queue + "Recently decided" (`?status=resolved`) refresh across
  devices every 5s. Browser coverage: `tests/e2e/test_browser.py::test_a_stale_approval_click_shows_the_other_devices_decision`.
- **Reference map** ([docs/research/reference-map.md](docs/research/reference-map.md)): verified
  this session against the Grok Bot changelog (v0.68.1) and the two Open WebUI issues (#31656
  closed, #30055 open) — observed patterns, evidence, Hutch equivalents, and the deliberate
  decisions, with the unverified gaps stated. This pass' typing label follows the reference
  (the bot's name is dropped from the working status).
- **Marketing site signature system**: an intro stage, a poster wordmark the hutch character passes
  through (two exactly-registered layers with the subject between them), an aurora-light character with
  a geometric line face, neural connection lines, a live status pill, a scroll-linked receding hero
  heading, spotlight cursor tracking and morphing glows on the bento cards, and a hover-revealed action
  on each project card. All motion is removed under `prefers-reduced-motion` (intro deleted, reveals
  forced visible, zoom/parallax off). Browser tests in `tests/e2e/test_website.py`.

### Changed
- **Dashboard (server-rendered): monochrome-first pass.** Retired the tinted status fills and the
  violet token; state now reads as glyph + word + a 6px dot or a 2px rail, and the one softened
  emerald accent is reserved for the primary action and the active nav. Restrained serif page title,
  12px panels, calmer density; `aria-current` on the active nav, `aria-live` on the live pill, and a
  labelled approval badge. Direction in [docs/design-system.md](docs/design-system.md).
- **Legacy SPA studio + marketing site: monochrome-first alignment.** The studio's `-bg` tint tokens
  are neutral and violet is retired (tool names, memory keys, the third bot-avatar hue), with the
  decorative dot-grid gone and 12px panels; the site drops `--violet` and moves labels to sentence
  case. All three surfaces now share the retired-violet / neutral-tint rule.
- **Studio feed** (legacy SPA): tool call/result pairs merge into compact expandable one-line entries;
  4+ steps collapse under a "tool steps" group; expansion persists per run; run errors are alert rows.
- **Approvals**: live fail-closed TTL countdowns everywhere (previously static text), flipping to
  "expired — denied"; consistent amber gate card across studio feed and approvals queue.
- **Composer**: per-bot daily token budget meter (amber >= 70%, red >= 100%), icon send button,
  Up-arrow recall of the last prompt.
- **Dialogs/toasts**: `role=dialog` modals with focus trap, Escape/backdrop close, and focus
  restoration; `window.confirm` replaced by styled destructive confirms; toasts gained dismiss
  buttons and errors persist until dismissed.
- **Marketing site**: tokens aligned with the dashboard (AA text roles), comparison-matrix negatives
  calmed from a wall of red pills to quiet metadata, one primary action per viewport, 14px code
  windows, lowercase brand casing throughout, skip link/`<main>`/focus rings/reduced-motion, and an
  accessible mobile drawer (`aria-expanded`, Escape, focus return).
- **Server-rendered dashboard**: token values aligned onto the shared system (obsidian surfaces,
  12/8px radii, emerald focus rings) without structural changes.
- **Hero gradient-text bug fixed**: `filter` + `background-clip: text` on the same element painted the
  whole text box as a solid block in Chromium (visible in the pre-change baseline). The heading now
  falls back to a solid accent and only applies the clipped gradient inside `@supports`.
- **Stale browser tests re-pointed at the single UI** (the server transcript/overview pages redirect
  into the SPA since 27a73ed): the phone approval journey now targets `#/approvals`, and a live SPA
  transcript journey replaces the retired server SSE DOM test.

## [0.1.0] — 2026-10-07

First MVP.

### Changed
- **Renamed the project openbot → hutch** before any public push: "openbot" is taken on PyPI and
  collides with unrelated GitHub projects. Candidate research (PyPI, GitHub, web/marketing) in
  [docs/research/naming.md](docs/research/naming.md); `botshed` documented as fallback.

### Added
- Bot management: CRUD, starter templates (research-briefing, repo-sweeper, tidy-downloads),
  pause/resume, per-bot memory and sticky tool allows — via CLI, dashboard, and REST API.
- Runtimes: built-in agent loop (OpenAI-compatible: OpenAI, Ollama, llama.cpp, LM Studio, custom
  base URLs), deterministic mock runtime (offline demos/tests), Pi adapter (RPC stdio), OpenCode
  adapter (headless run).
- Tools: workspace-jailed shell (scrubbed env, HOME redirect), path-jailed file read/list/write,
  SQLite-backed memory, SSRF-guarded web fetch, optional Playwright browser with persistent
  per-bot profiles and pause-to-human on login/CAPTCHA walls.
- Safety: compound-command policy engine (deny/ask/allow) with secret-path, escalation,
  pipe-to-interpreter and exfiltration denylists; fail-closed approvals with sticky always-allows.
- Scheduling: IANA-timezone cron with DST-gap/ambiguity handling, catch-up coalescing or visible
  skip, per-bot single-instance locks.
- Engine: run dispatch with global concurrency, per-run hard caps (steps, wall clock, daily
  tokens), stop/stop-all, append-only transcripts (SQLite + JSONL).
- Interfaces: Typer CLI (`hutch`), FastAPI dashboard with live transcripts/approval queue/spend
  meters, headless daemon, `demo seed` for offline exploration.
- Docs: architecture (decision log), safety model, bot-config reference, roadmap, and incident
  research with requirement traceability.
- Tests: 70 tests covering the safety parser, DST math, engine lifecycle, API, and CLI.
- **Design system → brutalist-modern (Oct 2026):** neutral `#0a0a0a` cards with a 1px glass
  ring; accent blue `#52a8ff` for active states and success green `#62c073` for positive
  indicators; square (0px) buttons, 100px pill chips, monospace data rows; a subtle radial
  accent glow; and a full-screen mobile menu for the header nav on the app, server dashboard
  and marketing site. The site also gains scroll-reveal animations, floating parallax cards and
  a stacked text echo. See [docs/design-system.md](docs/design-system.md).
- **Studio → whole app + data viz:** the chat SPA is now self-contained with an **Overview** triage
  view (`GET /api/overview`), a **bento** Bots grid, and a **Timeline** column on the Runs table
  (per-run duration bars, blue/amber/red). See [docs/design-system.md](docs/design-system.md).
- **One UI:** the duplicate server pages redirect into the studio SPA; run detail gains a KPI bento
  and a model/tools/hutch timing timeline. See [docs/design-system.md](docs/design-system.md).
