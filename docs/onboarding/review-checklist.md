# Onboarding review checklist

Status: planning gate artifact - used at CP0 and at every implementation checkpoint in [task-plan.md](task-plan.md).
Owner: Lead/planning agent. Reviewers: a named code reviewer for each slice plus a final reviewer at CP7; the person who wrote a slice may not be its only reviewer.
Rule: a checklist item without linked evidence is FAIL, not partial. Do not ask an agent to "review the codebase"; every row names the files, routes, or artifacts to inspect.

## 1. Planning gate (CP0) - block implementation until every box is checked

- [ ] All six artifacts exist and are linked from the task plan: task-plan.md, edge-case-matrix.md, marketing-changes.md, slices/slice-01.md, slices/slice-02.md, plus this checklist; the independent review record and its finding-to-resolution table are in task-plan.md section 9.
- [ ] Slice-01 and slice-02 briefs each name exact @file/function anchors (not directories), a form/API contract, edge cases in scope, front-end states, visual evidence, docs, marketing dependency, and a rollback plan.
- [ ] The edge-case matrix contains every required category: partial save/resume after refresh; session expiry mid-step; provider timeout; webhook retry (marked OUT with re-open condition); duplicate submission; permission denied; offline/flaky network; stale resume when requirements change; optional step skipped and later resumed; locale/timezone/currency/units; non-Latin name/transliteration; low-quality document capture/EXIF (OUT with re-open condition); unsupported/spoofed file type (OUT); large-file upload interruption (OUT); camera permission denial (OUT); virtual keyboard; screen-reader announcements on step change; keyboard-only; reduced motion; dark mode; empty/loading/saving/error/blocked states.
- [ ] The matrix does not collapse provider-unavailable, permission-denied, offline/server-unreachable, and stale-resume into a generic error; saved vs verified and session-expiry vs credential failure are distinct.
- [ ] marketing-changes.md reconciles all six requested categories (signup form fields, CTA copy, trust microcopy, pricing/plan wording, welcome/confirmation banner, free-forever/no-card claims) with the real static site, including NO-OP/OUT verdicts, owners, acceptance criteria, and rollback.
- [ ] Research open questions 1-22 are answered with evidence or explicitly assigned to a slice; none silently ignored.
- [ ] No production code, generated CSS, marketing source, or test changed in the planning phase; the only new files are planning docs plus docs/onboarding/artifacts/planning-baseline.txt and planning-review-2026-10-29.md.
- [ ] Frozen-file baseline recorded: python3 scripts/audit_context_hygiene.py reports seven pre-existing violations on the current tree; the plan explains these are baseline and forbids growing models.py, pages.py, store.py, cli.py, or tests/e2e/test_design_system.py.
- [ ] The other session's uncommitted brand/dashboard work is documented as a coordination hazard; no plan step relies on reverting it.

## 2. Architecture and function rules

- [ ] No god functions: every changed/added function has one concern. Inspect src/hutch/onboarding.py (pure decisions only, no FastAPI/templates/store/filesystem/network), src/hutch/server/onboarding_api.py (orchestration only: parse form -> call pure decision -> call persistence -> render/redirect), src/hutch/onboarding_store.py (persistence only), and the templates.
- [ ] No function both validates, persists, renders, and navigates. If a handler exceeds roughly 40 logical lines or mixes orchestration with domain rules, it is split.
- [ ] Pure decision logic is separate from I/O and UI: step order, transitions, stale/requirements checks, replay/conflict decisions, chooser rules live in src/hutch/onboarding.py with unit tests.
- [ ] Every state transition has an explicit representation: checking, saved-unverified, verified, invalid-credential, no-credit, rate-limited, unreachable, permission-denied, timed-out, offline/server-unreachable, stale-resume, conflict, damaged, blocked, saving, success. Grep the templates for a generic error/no-service fallback that swallows these.
- [ ] Optional work is skippable and resumable and is distinguishable in words from required work; required steps cannot be skipped while claiming success.
- [ ] Completion shows the resulting assistant/workspace and the next product action; it is not a generic celebration screen (src/hutch/server/static/app.js assistant/chat completion path, slice 08).
- [ ] No duplicate implementation seams: onboarding reuses POST /api/v1/bots, POST /api/v1/conversations/{id}/messages, the new shared src/hutch/connections_service.py (key validation/probe/terms), ConnectionBook, ProviderError, the setup-record adapter, and the existing idempotency helpers; no second create path, provider registry, or schema dialect. Explicit exemption: src/hutch/server/onboarding_api.py owns a bounded render/flash/CSRF helper (~25 lines) because pages.py is frozen over its cap; it must not contain business logic, and the later pagekit extraction is a separate reviewed task.
- [ ] Size budget respected: new .py/.js/hand-written .css files <=400 lines (aim: onboarding.py <=250, onboarding_store.py <=80, onboarding_api.py split near 300, route_readiness.py <=200, connections_service.py <=200, each test file small); app.py grows only by the two registration lines plus net-zero-or-shrink connection-handler delegation and stays under its 7,461 baseline; models.py, pages.py, store.py, connections.py, security.py and the pinned e2e file do not grow; npm run check:agent and the context-hygiene audit add no new violation.

## 3. Server-side authorization for every privileged onboarding step

Inspect the route registration and tests; for each row confirm the route is not in REMOTE_ROUTE_CAPABILITIES (paired phones refused), CSRF is enforced on every POST, and no user-controlled redirect target exists.

| Privileged step | Route / handler | Required check | Evidence (test) |
|---|---|---|---|
| Read/write setup record | GET/POST /onboarding, /onboarding/request, /onboarding/reset (src/hutch/server/onboarding_api.py) | local owner only; CSRF on POST; no next param | capability None + 403 tests in tests/test_onboarding_page.py |
| Read/write route choice | GET/POST /onboarding/ai-service* | local owner only; CSRF; route_kind allowlist | tests/test_onboarding_chooser.py capability/422/409 tests |
| Readiness probe | slice 03 routes/fragments | owner only; probe runs server-side; no browser-to-provider request | policy tests + e2e network assertion |
| Save provider key | POST /api/connections, POST /api/connections/{name}/set-key (src/hutch/server/app.py:7055-7143) and onboarding form wrapper, both through src/hutch/connections_service.py | owner only; key write-only; trim then 4 KiB cap; never returned/logged/echoed; identical validation on both surfaces | existing API tests + new shared-service parity tests + redaction grep |
| Terms acknowledgement | POST /api/connections/{name}/ack | owner only; server-side 422 when not checked; digest version | tests/test_api.py connections coverage + new terms-version test |
| Local-service probe | slice 05 route | owner only; loopback/HTTPS rule in src/hutch/connections.py:150-180; server-side probe | probe policy tests |
| External login start/status/complete/cancel | src/hutch/server/app.py:7157-7226 proxies | owner only; CSRF on POST; no embedded webview; no secret echo | slice 06 tests |
| Assistant create | POST /api/v1/bots (app.py:4291-4375) | owner only; Idempotency-Key required (428); paired phones denied | tests/test_api.py:946-1014 + e2e double-submit |
| First request send | POST /api/v1/conversations/{id}/messages (app.py:3587-3717) | owner only / require_remote_start for paired; Idempotency-Key; approvals server-side | idempotency tests + slice 08 tests |
| Pairing code exchange | /api/v1/pairing/*, passkeys | public exact paths by design; code 60 s single-use; passkey secure context; remote requires HTTPS | tests/test_pairing_setup.py:18-70 |

- [ ] Secrets never enter the setup record, SQLite, transcripts, URLs, logs, or HTML; keys stay 0600 files (src/hutch/connections.py:345-366).
- [ ] CSP/security headers still apply to the new routes; no new external origin, script, or analytics.

## 4. Idempotency and duplicate-safe saves

- [ ] Setup saves are revision-guarded: identical resubmit replays as success-once; same revision/different content is an explicit conflict, never silent overwrite; tests cover double submit, refresh-resubmit, and two tabs.
- [ ] Assistant creation uses Idempotency-Key and a persisted replay; a refresh-resubmit creates exactly one assistant (assert entity count, not only response).
- [ ] First request uses Idempotency-Key; retry-after-timeout reuses the same key; no blind resend that can double-spend.
- [ ] Provider webhooks: onboarding has no inbound webhook (channel delivery is outbound polling/outbox). The matrix keeps the webhook row OUT with a re-open condition; if any inbound webhook is added, verify signature, replay/dedupe idempotency, and a visible retry/expiry state before shipping.
- [ ] Duplicate-safe UI: buttons disable with aria-busy and progress; form state is preserved; "Already saved" is not framed as an error.

## 5. Edge-case tests use real-world data, not only simple fixtures

- [ ] Every matrix row mapped to an implemented slice has at least one automated or captured check; OUT rows have a documented re-open condition.
- [ ] Required hostile data is exercised: CJK/accented/RTL/60-character names and requests; key with trailing newline or Bearer prefix; fake provider with 200 on model list and 401 on generation; 401/402/403/429/5xx and a long multi-line error; local service up with one model, up with zero models, down, and timed out; expired/replayed OAuth attempt; expired/reused pairing code; expired setup record under a fixed clock; newer-contract setup record; 320x740 and 375x812; 200 percent zoom; reduced motion; forced colours; second tab; server restart; offline after load (net.offline/server.unreachable, owned by slice 03/09).
- [ ] Stale/requirements-change cases use an old persisted record fixture, not a hand-edited UI state.
- [ ] Tests assert the explicit state (data attribute, state token, or exact copy), not merely "an error appeared"; no test asserts a generic failure for provider-unavailable/permission-denied/offline/stale cases.
- [ ] No live provider/account/credential is used; fake providers follow tests/fakes.py patterns; tests are deterministic (fixed clock where timestamps are asserted).

## 6. Accessibility checks (part of the gate, not a separate audit)

- [ ] Keyboard-only completion of every implemented step: Tab/Shift-Tab/Enter/Space/Escape/arrows; no trap; focus restored after dialogs/back; popup-blocked fallback visible for external login.
- [ ] Screen-reader announcements: each state transition announced once via a status region; polling ticks silent; error summary focused; step heading focused on step change; resumed step announced as resumed, not fresh.
- [ ] Focus not obscured by sticky chrome/action; visible focus indicator (2 px / 3:1 change); target sizes 24x24 minimum with spacing, 44 px coarse-pointer floor for primary phone actions.
- [ ] 200 percent text zoom and 320 CSS px reflow: no horizontal scrolling for text content; action reachable with a scripted visual-viewport resize (keyboard-open state) and documented as emulated, not a real phone keyboard.
- [ ] Reduced motion honoured; dark theme and forced colours pass; no light-theme promise or toggle added.
- [ ] Errors are specific, adjacent, not colour-only, and keep user input; status text is present without colour.
- [ ] Evidence recorded for these checks in the slice capture bundle; audit limitations stated (Chromium/Linux only unless another engine captured).

## 7. Visual-regression evidence

- [ ] Baseline-first method: real app from source with deterministic fixtures; opened-image binary verdict per state/viewport BEFORE any screenshot-diff tooling; generated is not reviewed.
- [ ] Evidence lives under docs/onboarding/artifacts/<slice>/ with PNGs and validation.json rows containing state, viewport, artifact, verdict (APPROVED/NEEDS WORK), finding (max 3), source_commit, reviewer.
- [ ] Required states/viewports for the slice exist; missing evidence is FAIL. At minimum across the feature: 320x740, 375x812, 768x1024, 1440x1000; empty/no route; checking; saved-unverified; saving; invalid credential; provider unavailable; rate-limited; permission denied; blocked; offline/server down; stale resume; expired resume; newer-version record; chooser; key form; local service; external wait; duplicate-submit guard; assistant fast path; completion/first output; first approval; long/non-Latin names; expired pairing; dark; forced colours; reduced motion; 200 percent zoom; keyboard focus order; popup-blocked OAuth.
- [ ] If toHaveScreenshot is added, only for APPROVED states, Chromium/Linux, fixed clock, animations disabled, committed baselines, limited masks; automated diff is additive, never the gate.
- [ ] Screenshot-affecting source lists updated where the repo requires them (tests/e2e/test_design_system.py VISUAL_SOURCE_FILES) without growing frozen files; website proof captures regenerated after the last first-run UI change (marketing MKT-16).

## 8. Docs updated

- [ ] docs/design-system.md: setup recovery boundaries (server-owned record, resume/stale/conflict/damaged semantics), chooser rules, completion/next-action rule.
- [ ] docs/runtime-setup.md: prerequisites are linked from the onboarding local-service and OpenCode steps; no bundled-runtime claim.
- [ ] docs/marketing-site.md: any changed public claim, manifest description, availability date, support matrix.
- [ ] Slice briefs updated with implemented anchors and acceptance records; task-plan checkpoint notes and edge/marketing/review statuses current.
- [ ] README.md and website/llms.txt updated with the same prerequisites/quickstart target the site and runtime docs use (marketing MKT-05/MKT-11); the site's quickstart fragment resolves to an existing heading; the proof capture (MKT-16) is regenerated after the last first-run UI change.
- [ ] No doc claims "13-item industry checklist" as authority; the sourced gate is cited instead.

## 9. Marketing site updated (final checkpoint)

- [ ] Every CHANGE row in marketing-changes.md is implemented or explicitly deferred with owner and reason; NO-OP/OUT rows remain absent (no signup/account/email capture, no pricing tiers, no card gate, no free-forever/no-card claim, no fabricated social proof, no analytics, no banner injected into the app).
- [ ] Research 7.4 ten binary checks pass: real source-install path named; prerequisites before the click; dated availability, no dead Download; adjacent trust row (MIT, repo, issues, preview, data-flow); no pricing/card/account; no fabricated social proof; state-driven first-run copy with no Welcome back on first run; success/expiry/failure copy truthful; Linux-first/English/dated support matrix; volatile claims dated with a single source.
- [ ] Link and text audits: .hero entry block, #get, FAQ/JSON-LD parity (20/20), downloads.json still has empty artifacts and honest title/date, no a[download]/releases/download, quickstart fragment resolves, no external requests, no storage, no emoji in source/docs/UI.
- [ ] Screenshots at 375/768/1440 of the changed entry block, availability, trust row; validation.json with owner/reviewer; generated CSS rebuilt only via npm run build:css if source CSS changed.

## 10. No regressions in adjacent flows

- [ ] Pinned first-run e2e tests updated deliberately (not deleted) and green: tests/e2e/test_design_system.py:547, :748, :915; docs/realignment/capture_first_run.py still runs or is updated with its copy checks.
- [ ] Existing adjacent flows tested: connections list/save/test/terms, assistant setup/create, chat send/stream/approval decision, phone pairing, models page, / SPA boot, /legacy/connections redirects; focused tests named per slice.
- [ ] Fast lane green: npm run test:agent with the focused files; python3 scripts/audit_context_hygiene.py and the rest of npm run check:agent (seven pre-existing violations are recorded baseline; this feature adds none); python3 scripts/audit_emoji.py if touched docs/source.
- [ ] Diff scope review: only files listed in the slice brief plus tests/docs/evidence; no unrelated formatting, no generated CSS edited by hand, no other session's work staged or reverted; the CP0 git baseline (docs/onboarding/artifacts/planning-baseline.txt) is compared against the final diff for app.py, app.js, base.html, connections.html, pair.html, the pinned e2e test, website/index.html and docs/design-system.md.

## 11. Rollback readiness

- [ ] Each implemented slice has a reviewed rollback plan: code revert, additive template block default-true, kv record left inert (never delete user setup data), no migration/SCHEMA_VERSION change, no marketing data migration.
- [ ] Rollback was rehearsed or reviewed against the exact commit for at least the setup-record slice and the marketing-copy slice; pinned e2e and audit re-checked after.
- [ ] If a rollback leaves a record with newer fields, older readers ignore unknown fields (forward-compatible read test exists).

## 12. Final sign-off table

| Gate | Reviewer (name) | Date | Evidence bundle | Verdict (PASS/FAIL) | Findings (max 3) |
|---|---|---|---|---|---|
| CP0 planning | independent review agent (session 12936c57) | 2026-10-29 | task-plan section 9 + artifacts/planning-review-2026-10-29.md + artifacts/planning-baseline.txt | PASS (findings resolved; see record) | none open from review |
| CP1 slice 01 | | | docs/onboarding/evidence/slice-01/ (canonical) + artifacts/slice-01/ (pointer) | | |
| CP2 slice 02 | | | docs/onboarding/evidence/slice-02/ | | |
| CP3-6 per checkpoint | | | per-slice artifacts | | |
| CP7 final (marketing + docs + visual + code review) | | | docs/onboarding/artifacts/final/ | | |

A failed row reopens the checkpoint; the next checkpoint may not start. Two reviewers are required for CP7: one code/architecture reviewer and one visual/accessibility reviewer. Record the exact commands run and their results; do not claim a browser check that was not run.

## 13. Command reference

```bash
# focused tests (fast lane)
npm run test:agent -- tests/test_onboarding_state.py tests/test_onboarding_page.py tests/test_onboarding_chooser.py
# static audits
python3 scripts/audit_context_hygiene.py   # uv cache may be read-only; python3 fallback is equivalent; 7 pre-existing violations are baseline
npm run check:agent                       # rest of the static audits; no new failure may be added
python3 scripts/audit_emoji.py            # when docs/source/UI text changed
# visual lane (Playwright Chromium, not the fast lane)
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_onboarding_page.py tests/e2e/test_onboarding_chooser.py
# generated CSS only when its sources changed
npm run build:css --silent
```

Missing evidence, a generic error state, a client-only success claim, or a privileged route without an authorization test is an automatic FAIL regardless of the rest of the row.