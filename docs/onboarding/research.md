# Onboarding and Setup surface - research and discovery

Status: complete (2026-10-29). Research artifact for the planning agent. No production code was changed; this file and research-brief.md are the only deliverables, plus the six source notes under docs/onboarding/notes/.
Worktree note: line numbers describe the working tree as observed on 2026-10-29. The tree also carries another session's uncommitted brand/dashboard work; line numbers may drift when that work lands.

---

## 0. Scope, method, and evidence boundaries

### 0.1 What "onboarding" means for this product

Hutch is a local-first, MIT-licensed, open-source platform for personal AI assistants. It is installed from source on a Linux host, started as a local server, and used through the locally served dashboard (plus an optional Tauri desktop host). There is no hosted sign-up, no account creation, no email verification, no pricing tier, no payment card, no cloud tenancy, and no identity verification.

The onboarding surface starts when the local dashboard opens with an empty state and ends when the owner has completed a first useful task and has seen the approval model work. Concretely:

1. First-run screen with a request composer and an AI-service readiness panel (app.js:3273-3337).
2. Choose or connect an AI route: hosted provider API key, local model service (Ollama or OpenAI-compatible), or a provider login through OpenCode; accept provider terms where they apply (docs/runtime-setup.md:6-30; src/hutch/server/templates/connections.html:105-110).
3. Carry the request into assistant setup, review a suggested name and model route, and create the assistant (app.js:11584+; route #/assistant/new).
4. Send the first request and get a first useful output, including at least one approval decision when the task needs an action.
5. Optional and deferrable: connect apps (calendar, mail, Drive, Notion), connect a channel (Telegram), pair a phone (manual one-time code plus passkey), tune limits and budgets.

### 0.2 Method

- Static inspection of the current dashboard, server routes, templates, tests, and prior research records. Paths and line numbers are cited throughout.
- Live web research on comparable products, standards, and failure reports, captured in six notes under docs/onboarding/notes/ with a sources table each (all sources opened 2026-10-29).
- Prior in-repo research was read as context, not as current truth: docs/research/first-run-setup-2026-10-23.md, docs/research/bot-setup-patterns-2026-10-09.md, docs/research/connections-setup-ux-2026-10-10.md, docs/research/complaints.md, docs/responsive/research-2026-10-29.md, docs/realignment/visual-validation.md.
- No live provider call was made; no account, credential, or external service was touched.

### 0.3 The task prompt's borrowed claims, checked

The prompt supplied placeholders rather than URLs, so each claim was traced independently. Verdicts:

| Borrowed claim | Closest real source | What the source actually measures | Verdict for Hutch |
|---|---|---|---|
| "Only about 2 in 10 users complete onboarding checklists" | Secondary blog compiling a Userpilot 2025 benchmark of 188 companies: average checklist completion 19.2%, median 10.1% ([Tour Kit post](https://raw.githubusercontent.com/domidex01/tour-kit/4db0fe72ce36181c9ce67809832db8f07c09b98f/apps/docs/content/blog/onboarding-checklist-psychology.mdx)); the cited primary Userpilot page exposed navigation only when fetched | A vendor survey/benchmark average, not a law and not Hutch users; the primary figure could not be opened in-session | UNVERIFIED AS STATED. Defensible translation: most users who see a checklist do not finish it, so a checklist must not be the only path to value. Hutch currently has no checklist; keep it that way unless it reflects real state. |
| "Fintech/regulated onboarding commonly loses 68%+ of applicants before completion" | Signicat, The Battle to Onboard 2022: 68% of 7,600 consumers in 14 European markets self-reported abandoning a financial application, up from 63% in 2020; 38% lacked the required ID document; average patience was 18m53s ([Signicat six-year retrospective](https://www.signicat.com/blog/btob-six-year-retrospective), [2022 press release](https://www.signicat.com/se/pressmeddelande/the-battle-to-onboard-2022)) | Self-reported abandonment of financial applications because identity/onboarding friction was too slow or document-heavy, not a KYC-applicant conversion rate. Fenergo data reported alongside puts institutions' average onboarding abandonment around 10% ([OneID summary](https://oneid.uk/news-and-events/identity-verification-abandonment-cost)) | REAL SURVEY, WRONG CONTEXT FOR HUTCH. Hutch has no identity layer; do not use it as an expected drop-off figure. Its transferable lesson is that multi-minute, document-heavy steps and dishonest progress states cause abandonment. |
| "Do -> configure -> invite re-sequencing nearly doubled activation" | No primary source found. Closest material: a vendor case study claiming 11% -> 29% seven-day activation for a project-management SaaS after a first-run redesign ([Simplileap case study](https://www.simplileap.com/resources/case-studies/saas-onboarding-activation-redesign)), and practitioner posts arguing configuration/invite must follow first value ([FlowAudit](https://flowaudit.site/blog/the-invite-your-team-screen-is-an-activation-trap-a-p0p1p2-onboarding-playbook)) | The case study is a vendor's own client story, not a controlled measurement of this sequence; the "nearly doubled" claim was not found with a method | UNVERIFIED. Treat "value before configuration" as a testable design hypothesis, not a validated rule. |
| "Multimodal verification should use risk-based step-ups and fallbacks; manual review on conflicts" | Correct pattern for identity verification (document plus liveness plus risk score), e.g. [Sumsub material](https://sumsub.com/files/Sumsub_LeadershipCompass-IdentityVerification2026.pdf) | Applies to KYC/identity, which Hutch does not perform. None of the eight closest comparable products puts document upload, liveness, e-signature, or government-ID checks in first-run setup (failure-catalog.md, "Modality reality check") | OUT OF SCOPE for this product. Do not build a verification pipeline. In-scope modalities are secret text, endpoint URLs, external OAuth/device login, a manual pairing code plus passkey, terms acknowledgement, and free text. |
| "Onboarding specs need one primary task per step, saved state and resume, explicit skip, a state model, and server-side authorization" | Partly validated: state-machine treatment of onboarding (status plus step plus per-step flags, backend-owned order, idempotent steps, park external handoffs) in [Onboarding Is a State Machine, Not a Boolean](https://oladele.hashnode.dev/onboarding-is-a-state-machine-not-a-boolean); self-hosted products run first-run inside the existing web UI (Home Assistant, Jellyfin, Nextcloud); Hutch's own design system states setup recovery boundaries (docs/design-system.md:162-197, 328-334) | Operational guidance and practitioner experience, not a controlled study | ADOPT, localised below. The security/authorization part is local-owner permissions and approvals, not org/role provisioning. |
| "Visual validation must not rely only on automated tools; baseline live screenshots and a binary verdict come first" | Validated by primary docs: Playwright waits for two stable frames and disables animations, so it cannot show layout-shift timelines ([Playwright](https://playwright.dev/docs/api/class-pageassertions)); CLS is a temporal metric ([web.dev](https://web.dev/articles/cls)); jsdom has no layout engine ([jsdom](https://github.com/jsdom/jsdom#unimplemented-parts-of-the-web-platform)); WebAIM Million 2026 finds 95.9% of home pages with detected WCAG failures ([WebAIM](https://webaim.org/projects/million/)) | Primary standards/tool docs | ADOPT. Baseline live capture and an opened-image verdict precede regression tooling. |
| "13-item pre-PR visual checklist" | Provenance unverified. The only traceable artifact is a community AI skill page advertising a "13-item mandatory verification checklist" ([LobeHub ui-visual-validator listing](https://lobehub.com/skills/kumaran-is-claude-code-onboarding-ui-visual-validator)); no W3C/Playwright/NN/g standard defines 13 items | Community convention, not a standard | REPLACE with the sourced 13-row gate in section 6 and notes/visual-validation.md. Do not cite "13 items" as industry authority. |

### 0.4 Evidence strength labels

- [repo] current source/tests in this checkout.
- [primary] standard, official docs, merged code/PR, or provider documentation.
- [secondary] credible UX research, vendor case study, or blog; useful but not prevalence evidence.
- [anecdote] a single issue report or comment; used as a failure-scenario class, never as a rate.

---

## 1. Product-specific onboarding job-to-be-done

### 1.1 The job

When I have installed Hutch on my own machine and open it for the first time, I want to get one real piece of work started with an AI service I trust, without being asked to make decisions I cannot evaluate yet, so that I can tell within minutes whether this product is worth the setup I already did.

Corollaries that localize generic onboarding advice:

- The user has already paid a large setup cost before onboarding begins (install from source, run a server, obtain an API key or a local model). In-app first run must not spend that goodwill on configuration ceremony.
- The product promise is control, not speed (local state, explicit approvals, keys stay on the machine). Onboarding must demonstrate control and honesty; it must not imitate a cloud trial.
- There is no growth team, no remote analytics, and no hosted funnel. Drop-off feedback must be local, opt-in, and privacy-preserving.
- Failure is normal in a bring-your-own-provider product: missing runtime, invalid key, no credit, no network, provider outage. Onboarding must make failure recoverable rather than exceptional.

### 1.2 Activation definition

The smallest honest activation event is: the owner's own first request produced a useful assistant response and, where the request required an action, at least one approval was shown and decided. Saving an assistant alone is not activation; a saved route alone is not activation. Comparable products show that configuration without a verified first output is cosmetic (failure-catalog.md rows 1, 10, 19).

Because Hutch sends no telemetry, activation cannot be measured with a remote product-analytics SDK. The plan should define local, inspectable milestones instead: first_run_started, ai_route_saved, ai_route_verified, assistant_created, first_request_sent, first_request_succeeded, first_approval_decided, plus a local setup-state record that the doctor command can read or export with consent. The marketing site stores no browser preference and sends no analytics request (docs/marketing-site.md:1-8), so none of this may become remote tracking by default.

### 1.3 Current surface map

| Stage | Current UI | Routes / files | Observed state handling | Evidence |
|---|---|---|---|---|
| First run, empty workspace | Request composer beside AI-service readiness panel, three example requests, "How Hutch works", draft note | SPA renderChatStudio when bots list is empty, app.js:3273-3337; readiness app.js:3135-3245 | checking / ready / saved / setup / error; polite status region; submit disabled while checking; no-route action sends to #/connections | [repo] |
| AI-service chooser | General "Apps & AI" page; AI providers are the third group after "Your apps" and "Your devices" | app.js:9466; groups at 9803, 9807, 9811 | Provider cards, key store, test button, terms, allowances; ChatGPT sign-in; OpenCode dialog | [repo] |
| OpenCode connection | "Connect OpenCode" modal from first run; provider filter, API key, OAuth, existing local login | app.js:11390-11560 | install/status errors, local-login discovery, poll after connect, "saved but no usable model" state | [repo] |
| Provider secrets | Key field in each connection card, write-only, 0600 file or environment variable; test spends no tokens | templates/connections.html:9-11, 68-76; app.py:7100-7125 | Server caps key at 4 KiB; store returns success; test call separate; terms acknowledgement required server-side (422 if not confirmed) | [repo] |
| Assistant setup | Task page #/assistant/new with request carried forward, suggested name, model route, optional tools/memory/schedule/limits, review, YAML import | app.js:11584+; route at 1914-1922; docs/design-system.md:162-173 | Same-tab draft, Save draft and leave, Discard, conflict confirmations; create disables button; purpose-draft idempotency keys exist | [repo] |
| First request / run | Chat composer, run status, approval cards | SPA chat; tests/e2e/test_design_system.py:547, 748, 915 | Existing first-run tests cover empty, carried request, readiness states, phone/desktop widths | [repo] |
| Phone pairing | Desktop shows pair URL plus one-time code; phone page enters code, then creates a passkey | app.js:10084-10096; templates/pair.html; static/pair.js | 14-character code, 60-second expiry and single use; pairing/passkey failure messages; no QR image, no camera capture | [repo] |
| Marketing boundary | Static dev-preview site; CTAs "See the app" and "Check availability"; availability says no installers and no hosted sign-up | website/index.html:293-327, 788-844; docs/marketing-site.md:1-8 | Truthful availability, no analytics, GitHub quickstart link, releases manifest with empty artifacts | [repo] |

### 1.4 Who arrives, and what each group needs

| Arrival state | What they need first | What the current flow assumes |
|---|---|---|
| Already has a hosted API key | A minimal paste-and-verify path that returns to the first request | A general Apps and AI catalog plus a key card |
| Runs Ollama or another local service | Detection with the local URL and model list, no credential terminology | A general model route form; local discovery exists on the Models page, not in first run |
| Has OpenCode installed and logged in | One-click reuse, or a clear install instruction if absent | OpenCode modal exists, but only from a secondary button |
| No provider yet, wants to see the product | An honest explanation of what is required before value, plus a deferrable path | The first request action diverts to the connections catalog |
| Returning owner after reinstall or state restore | Detect existing state and do not re-ask | Partly: saved model defaults and stale checks are distinguished, but no server-side setup state exists |

---

## 2. Validated best practices (with sources)

Full mechanics and copy examples are in notes/best-practices.md. "Localised decision" is what this plan should adopt.

| # | Practice | Evidence | Localised decision for Hutch |
|---|---|---|---|
| 1 | Onboarding's job is first value, not teaching the product; keep it brief and contextual | NN/g qualitative study of first-time generative-AI users recommends avoiding long tutorials and skipping onboarding when possible ([NN/g](https://www.nngroup.com/articles/new-AI-users-onboarding/)); "grand tour" is an anti-pattern ([community onboarding skill](https://raw.githubusercontent.com/heymegabyte/claude-skills/refs/heads/master/06-build-and-slice-loop/onboarding-and-first-run.md)) | One request and one next action on the first screen. "How Hutch works" is already three promises; do not add a tour. Teach approvals at the first approval. |
| 2 | Prefer a working default route over asking the user to choose a model first | Jan downloads a default local model at launch and says "no setup required" ([Jan quickstart](https://docs.jan.ai/desktop/quickstart)); HuggingChat's Omni router does the same ([HuggingChat](https://huggingface.co/chat/)); counter-example: Jan's "Select a model" first screen ([Jan #7658](https://github.com/janhq/jan/issues/7658)) | Show a detected local route or a saved route first; when none exists, offer one recommended route with a short explanation, not a model catalog. Never silently substitute a hosted provider. |
| 3 | Probe readiness; do not infer it from configuration | n8n's self-hosted AI onboarding does live verification before completing ([n8n PR #35579](https://github.com/n8n-io/n8n/pull/35579)); Jan's wizard load-probes the backend ([Jan PR #8594](https://github.com/janhq/jan/pull/8594)); a models endpoint can return 200 while generation returns 401 ([OpenCode #38257](https://github.com/anomalyco/opencode/issues/38257)) | Distinguish saved from verified. If a real generation at setup is too expensive or surprising, state that the route is saved but unverified and verify at first send with an explicit state. |
| 4 | Separate saved, verified, unavailable, invalid, and permission-denied in words, not just colour | WCAG 2.2 SC 4.1.3 requires status messages to be programmatically determinable without moving focus ([W3C](https://www.w3.org/WAI/WCAG22/Understanding/status-messages)); comparable products return one generic failure and mislead users (failure-catalog.md rows 2, 3, 10) | Replace the single global failure count with per-route states and a specific next action. Keep the polite live region; never take focus for a status update. |
| 5 | Make every step resumable; model onboarding as state, not a boolean | Onboarding state needs status, step pointer, and per-step flags so refresh, drop-off, and out-of-order edits survive; backend owns order; steps that hand off externally park until confirmed ([state-machine article](https://oladele.hashnode.dev/onboarding-is-a-state-machine-not-a-boolean)); Hutch's design system already requires same-tab draft recovery and explicit draft replacement (docs/design-system.md:328-334) | Add a local server-side setup record keyed to this installation: step, per-step flags, timestamps, selected route, provider status. Keep the browser draft as a cache, not the source of truth. |
| 6 | Put a heavy or uncertain step's cost before the step | Ollama states the ~7.2 GB download and memory guidance ([Ollama quickstart](https://docs.ollama.com/quickstart.md)); Home Assistant says preparation may take 20 minutes or more ([Home Assistant onboarding](https://www.home-assistant.io/getting-started/onboarding/)); LM Studio lists hardware gates first ([LM Studio requirements](https://lmstudio.ai/docs/app/system-requirements)) | If a local model pull or install is required, say the size/time and prerequisites before the action. For provider checks, show a bounded checking state with a deadline and cancel/retry. |
| 7 | Keep failure non-terminal; make failed stages skippable and retryable | Jan PR #8594 makes a failed stage skippable rather than terminal ([Jan PR #8594](https://github.com/janhq/jan/pull/8594)); Home Assistant puts restore-from-backup on the same screen as the forward path | A failed provider check must not trap the user. Offer use another route, retry, and quit and resume later. Never lose the written request. |
| 8 | Empty states are first-run surfaces; use one consistent empty-state component and action labels | n8n unified divergent onboarding empty states and tied CTA labels to the real header actions ([n8n PR #33670](https://github.com/n8n-io/n8n/pull/33670)); NN/g empty-state guidance ([NN/g](https://www.nngroup.com/articles/empty-state-interface-design/)) | Reuse one empty-state pattern across first run, bots, chats, connections. The CTA must match the action actually performed. |
| 9 | Do not let a checklist become the product; if present, keep it short, optional, tied to real state | A secondary benchmark reports average checklist completion 19.2% and median 10.1% across 188 companies (unverified primary, section 0.3); n8n later disabled its sidebar checklist ([n8n PR #35734](https://github.com/n8n-io/n8n/pull/35734)) | No permanent onboarding checklist. A dismissible progress summary is acceptable only if every item maps to server-known state and it never gates chat. |
| 10 | External OAuth belongs in the system browser with state binding, expiry, and a polling story | RFC 8252 requires native apps to use an external user-agent, bind request/response with state, and allow any loopback port ([RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252)); device flow defines user_code, verification URI, expires_in, interval, slow_down ([RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628)); OpenRouter's localhost callback code is single-use and expires in 10 minutes ([OpenRouter OAuth](https://openrouter.ai/docs/guides/overview/auth/oauth.md)) | Open the system browser; keep a persistent waiting state with countdown, cancel, retry, and clear errors for expired/replayed codes. Do not use an embedded webview. |
| 11 | Verify secrets with a provider call; never echo them; distinguish invalid credentials from busy/transient failures | Telegram bot tokens grant full control and must be stored securely ([Telegram](https://core.telegram.org/bots)); OpenRouter documents 401/402/408/429/502/503 and Retry-After ([OpenRouter errors](https://openrouter.ai/docs/api-reference/errors.md)); GOV.UK requires paste to work ([GOV.UK password input](https://design-system.service.gov.uk/components/password-input/)) | Keep key entry write-only and server-side. Validate with the provider's cheapest authenticated call before saying connected. Map 401/403 to account/key wording, 402 to credit, 429/5xx to retry. |
| 12 | Prevent duplicate submission and make retries idempotent | Idempotency-Key returns the stored response on retry ([Stripe](https://docs.stripe.com/api/idempotent_requests)); GOV.UK buttons disable while pending and show progress ([GOV.UK button](https://design-system.service.gov.uk/components/button/)) | Disable and announce pending create/send actions; send a stable idempotency key on first-request and assistant creation; treat timeouts as unknown, not as a licence to blind-resend. |
| 13 | Use one thing per page, ask each question once, and review before commit | GOV.UK question pages, check-answers pattern ([GOV.UK question pages](https://design-system.service.gov.uk/patterns/question-pages/), [GOV.UK check answers](https://design-system.service.gov.uk/patterns/check-answers/)); NN/g progressive disclosure ([NN/g](https://www.nngroup.com/articles/progressive-disclosure/)) | The first-run setup should ask only what the next action needs; advanced assistant configuration stays after creation; assistant review shows name, route, and what will be saved. |
| 14 | Self-hosted products run first-run as a wizard inside the existing browser UI | Home Assistant, Jellyfin, Nextcloud all do first-run in the installed web UI ([HA](https://www.home-assistant.io/getting-started/onboarding/), [Jellyfin](https://jellyfin.org/docs/general/post-install/setup-wizard/), [Nextcloud](https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html)) | Build dedicated onboarding routes inside the existing dashboard, not a separate funnel. Jellyfin's skippable library step is the model for optional steps; Nextcloud's short default path with advanced settings behind one expandable section is the model for progressive disclosure. |
| 15 | Support the phone viewport and on-screen keyboard deliberately | The visual viewport shrinks when the on-screen keyboard opens while the layout viewport does not ([MDN Visual Viewport](https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API)); WCAG 1.4.10 requires reflow at a 320 CSS px-equivalent width ([W3C](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)) | The first action must remain reachable when the composer is focused; do not rely on fixed footers; exercise a scripted viewport resize because Chromium does not emulate a real keyboard. |
| 16 | Treat accessibility as part of the visual gate, not a separate audit | Status without focus (WCAG 4.1.3); focus not obscured (2.4.11); target size (2.5.8); error summary focus (GOV.UK); reduced motion and forced colours (MDN) | Hutch ships a fixed dark theme by explicit product decision and keeps forced-colours overrides (docs/design-system.md:300-306). Test dark and forced colours; do not promise a light theme that does not exist. |

Two prompt-suggested practices are deliberately not adopted as stated: a mandatory multi-step checklist and a separate onboarding funnel. The evidence supports neither for a local-first, single-owner product; both would add ceremony before value (sections 5 and 9).

---

## 3. Failure/complaint catalog (complaint -> mechanism -> realistic fix -> priority)

Rows FM-01 to FM-10 and FM-19 to FM-22 are current-surface or repo-verified mechanisms; FM-11 to FM-18 are comparable-product reports mapped onto the same mechanisms. Priority: P1 blocks or misroutes first value; P2 wastes work or support load; P3 polish; OUT not applicable. Full 27-row comparable catalog: notes/failure-catalog.md.

| ID | Complaint / failure | Mechanism | Evidence | Realistic fix in Hutch | Priority |
|---|---|---|---|---|---|
| FM-01 | A ready user cannot get from first request to a connected AI service in one place | First-run action for a missing route sends the owner to the general Apps and AI page; AI providers are the third service group after apps and devices; no in-context chooser | [repo] app.js:3314-3316, 3356-3374; group order 9803, 9807, 9811 | In-context Choose AI service step launched from first run with three routes (hosted key, local service, OpenCode), deep-link the model group, return to setup with the chosen route | P1 |
| FM-02 | "Saved" is read as "working"; a generic "No ready AI service" hides different causes | Readiness runs three checks, counts failures, and collapses them into setup/error; no real generation proves readiness; 401 vs unreachable vs no credit are not distinguished | [repo] app.js:3135-3214; [OpenCode #38257](https://github.com/anomalyco/opencode/issues/38257); [Jan #7658](https://github.com/janhq/jan/issues/7658) | Per-route state model: checking, saved-unverified, verified, invalid-credential, no-credit, rate-limited, unreachable, permission-denied, timed-out. Probe with the cheapest real generation once, or label saved and verify at first send | P1 |
| FM-03 | Provider/secret connection has no durable recovery state across the external browser | OAuth/device login waits on an external browser; OpenCode may be absent or unauthenticated; key save and key test are separate; no persistent waiting state with expiry, cancel, retry | [repo] app.js:11390-11560; app.py:7100-7125; [OpenCode #7992](https://github.com/anomalyco/opencode/issues/7992); [OpenCode #9922](https://github.com/anomalyco/opencode/issues/9922); [RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628) | Provider connection state machine with expires-at, waiting, cancel, retry, open browser again, restart from scratch; keep across reload; translate transport errors into the next diagnostic action | P1 |
| FM-04 | Refresh, provider return, another tab, or device change loses the setup position | First request and assistant setup draft are stored in sessionStorage (tab-scoped); no server-side onboarding step or chosen route for this installation | [repo] app.js:135-189, 1904-1918, 12068-12072; docs/design-system.md:328-334 | Local server-owned setup record (SQLite) with step, per-step flags, saved route, timestamps, resume token; revalidate provider state on resume; browser storage remains a cache | P1 |
| FM-05 | On a phone the primary action and readiness status compete with the keyboard and the fold; error states are only partly announced | At 375x812 first-run action ends at y=701 and readiness heading begins at y=726; at 320x740 the action ends at y=729; Chromium cannot emulate a real keyboard; only one polite live region exists and error/blocked states are not consistently announced | [repo] docs/realignment/visual-validation.md:13-25; app.js:3312; [MDN Visual Viewport](https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API); [W3C 4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages) | Keyboard-aware layout (scroll focused field into view, action reachable above keyboard), sticky primary action with safe-area padding, explicit live regions for saving/error/blocked/success, and a scripted viewport-resize state in the visual gate | P1 |
| FM-06 | Assistant setup asks for more configuration than the first task needs | Same page carries purpose, clarification/draft, runtime, model, tools, memory, schedule, time limits, workspace, YAML import, review; optional controls are disclosures but the page is long and model route is required | [repo] app.js:12360+, 12441; docs/design-system.md:162-173 | Default path: name, instructions, route, Create. Move tools, memory, schedule, limits, YAML, and workspace to post-create settings; do not call the model-refinement coordinator unless asked | P1 |
| FM-07 | Terms/consent state can be missed or loop | Terms acknowledgement is required server-side for connections (422 when unconfirmed) and can become stale after a notice change; first run does not surface provider terms before the connection detour | [repo] app.py:7123-7125; templates/connections.html:105-110; [chat-ui #252](https://github.com/huggingface/chat-ui/issues/252) | Show the terms summary and acknowledgement where the route is selected; persist version and timestamp; re-ask only on real change | P2 |
| FM-08 | Duplicate submits create duplicate assistants, messages, or spend | Some buttons disable while pending, but comparable reports show missing dedupe and retry duplicate effects; purpose-draft idempotency keys exist; first-request and assistant-create coverage must be verified | [repo] app.js:3361-3363, 12177-12180; [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests) | Stable idempotency keys for assistant creation and first send, server-side dedupe window, disabled plus aria-busy, same key on retry | P2 |
| FM-09 | A failed provider check is reported as "no service" because checks are collapsed | failures.length === 3 -> could not check; any failure -> setup with a joined list; the user cannot tell what failed or what to do differently | [repo] app.js:3146-3214 | One row per check (saved choice, OpenCode, other routes) with a specific state and action; never claim no service exists when a check failed | P1 |
| FM-10 | The phone pairing code expires while moving to the phone, and the desktop offers no countdown or regenerate | Desktop shows a 14-character code valid 60 seconds; expiry is server-side; copy states the duration but there is no visible timer or regenerate action | [repo] app.js:10084-10096; templates/pair.html:9-16; static/pair.js:27-67 | Live countdown, regenerate, keep URL plus code as the primary path, describe the passkey secure-context requirement before the phone attempt | P2 |
| FM-11 | OAuth says success but the client keeps waiting | Local poll never matches the callback, or the code is replayed/expired | [OpenCode #7992](https://github.com/anomalyco/opencode/issues/7992), [#18362](https://github.com/anomalyco/opencode/issues/18362) | Bind state to the local session, expire and clear the verifier, poll with interval and slow_down, expose cancel/retry | P1 |
| FM-12 | A model list works while generation returns 401 | Readiness inferred from listing, not from a real generation | [OpenCode #38257](https://github.com/anomalyco/opencode/issues/38257) | Verify with a minimal generation, or label saved-unverified and verify at first send | P1 |
| FM-13 | First-run buttons unusable on some mobile browsers | Onboarding layout overflows the viewport | [Open WebUI #16287](https://github.com/open-webui/open-webui/issues/16287) | Same fix as FM-05; add 320 and 375 to the mandatory gate | P1 |
| FM-14 | API key cannot be pasted; a saved key disappears after an update | Secret field blocks paste; persistence tied to a volume/env and not migrated | [OpenCode #9922](https://github.com/anomalyco/opencode/issues/9922); [Open WebUI #1135](https://github.com/open-webui/open-webui/issues/1135) | Never block paste; store keys in documented local state with 0600 and explicit migration; show where this is stored | P2 |
| FM-15 | A Start Chatting consent modal loops | Consent flag not persisted or validated | [chat-ui #252](https://github.com/huggingface/chat-ui/issues/252) | Persist versioned consent server-side and test reload/changed-notice paths | P2 |
| FM-16 | Onboarding re-asks for values already known | Onboarding ignores existing configuration | [Home Assistant #35696](https://github.com/home-assistant/core/issues/35696) | Prefill detected route/provider state and label it as detected; ask only for missing steps | P2 |
| FM-17 | First-run empty states disagree in voice, CTA, and layout | One-off empty states per resource | [n8n #33670](https://github.com/n8n-io/n8n/pull/33670) | One shared empty-state component and a small copy rule; CTA labels tied to the real action | P2 |
| FM-18 | A checklist competes with the real task and is disabled later | Mandatory checklist not tied to value and not dismissible | [n8n #35734](https://github.com/n8n-io/n8n/pull/35734) | No permanent checklist; at most a dismissible, real-state progress summary | P3 |
| FM-19 | A download affordance implies installers that do not exist | website/downloads.json lists Windows, macOS, and Ubuntu platform entries with empty artifact arrays and is linked as the Hutch desktop release manifest; site text says no installers; the hero CTA is "See the app", not "Download" | [repo] website/index.html:8, 293-327, 788-844; website/downloads.json | Keep availability explicit; retitle the manifest as a preview contract with no build implication, or remove the link; never add a dead download CTA | P2 |
| FM-20 | A welcome/confirmation banner pattern does not exist and should not be invented to look mature | Site has no banner, no signup, no cookie consent; app has no welcome-back copy; the first-run page is the welcome | [repo] website/site.js (159 lines, no banner logic); grep for "Welcome back" returns none in the app | Do not add a fake welcome-back or confirmation banner. If a post-install confirmation is added, name the actual state (first run on this machine) and offer the real next action | OUT (pattern not applicable) |
| FM-21 | Browser autofill or a password manager overwrites a provider key/token field, then the wrong secret is saved | Secret fields are ordinary inputs; Chrome ignores autocomplete=off on password inputs; autosave amplifies the corruption | [repo] templates/connections.html:68-76; [GOV.UK password input](https://design-system.service.gov.uk/components/password-input/); [sim PR #4973](https://github.com/simstudioai/sim/pull/4973) | Dedicated secret input, no autosave, explicit save plus provider verification, keep paste allowed, test with saved browser credentials | P1 |
| FM-22 | Local model service looks "invalid" when it is only down or CORS-blocked | Browser-side probe fails opaquely; localhost and 127.0.0.1 differ; CORS failure looks like server down | [Ollama /api/tags](https://docs.ollama.com/api/tags.md); [Ollama FAQ](https://docs.ollama.com/faq.md) | Prefer a server-side probe through the Python backend; short timeout; distinguish server-down, CORS-blocked, and no-model states; show the start/pull commands | P1 |

Cluster synthesis from the comparable catalog: blank or wrong first state; secret entry and persistence; async work without progress or deadline; misleading readiness; empty-state/checklist quality; existing state ignored; hardware/install prerequisites.

---

## 4. Modality inventory and per-modality edge-case matrix

### 4.1 Inventory (what this onboarding actually needs)

| # | Modality | In onboarding? | Where it appears today | Needed in the plan |
|---|---|---|---|---|
| 1 | Free text (first request, assistant purpose/instructions, names, labels, filters) | Yes | First-run composer; assistant setup; connection labels; bot form | Yes |
| 2 | Secret text (hosted provider API key, Telegram bot token, OpenCode provider key) | Yes | connections.html:68-76; OpenCode modal; channel setup | Yes |
| 3 | Plain text endpoints (local service base URL, OpenAI-compatible endpoint) | Yes, for local routes | Models page and setup hints; docs/runtime-setup.md:25-30 | Yes |
| 4 | External-browser OAuth/PKCE and device-code login | Yes for providers that offer it | OpenCode dialog (app.js:11524+); Google/Outlook tiles open a PKCE popup; ChatGPT local sign-in | Yes |
| 5 | Manual one-time code plus passkey (phone pairing) | Optional, after first run | Desktop code app.js:10084-10096; phone page pair.html and pair.js | Yes, optional |
| 6 | Terms/consent acknowledgement | Yes when a provider declares terms | connections.html:105-110; app.py:7123-7125 | Yes |
| 7 | Local file import (YAML assistant configuration) | Optional advanced step, not required for first value | app.js:727-728; server parsing app.py:291-350 | Defer; keep server validation |
| 8 | Image/document upload, camera capture, QR scan, liveness, video, voice, signature, payment card | No | Chat image attachment is a post-activation composer feature (uploads.py:24, 52: PNG/JPEG/WebP up to 25 MB, 200 per conversation); it is not an onboarding step | No |

Explicitly out of scope, with rationale: identity-document upload, liveness/selfie video, signature, voice, in-dashboard camera capture, payment card, OCR, and generic file upload. None of the eight closest products uses them in first-run setup (notes/failure-catalog.md, "Modality reality check"), and Hutch has no hosted account, pricing, identity, or document requirement in this surface. Only a future hosted Hutch cloud, payments, or a regulatory identity gate would put them back in scope.

### 4.2 Edge-case matrix (applicable modalities)

Priority P0/P1/P2 is relative to the onboarding surface. [ext] = external evidence, [repo] = current source, [open] = needs code verification before commitment.

| Edge case | Applies to | Failure mode | Realistic fix | Pri | Evidence |
|---|---|---|---|---|---|
| Secret pasted with whitespace/newline or a Bearer prefix | API keys, bot tokens | Provider returns 401; user believes the key is wrong | Trim, preserve the value for edit, pass the provider message through, validate with a real call | P0 | [OpenRouter errors](https://openrouter.ai/docs/api-reference/errors.md) |
| Format check presented as verification | Bot token/key fields | Connected shown for a dead key | Only a provider response can mark connected; format is a hint, not proof | P0 | [Telegram Bot API](https://core.telegram.org/bots/api) |
| Browser autofill or password manager fills a token field | Secret fields | Wrong secret silently saved | Dedicated secret input pattern, no autosave, explicit save and verify; keep paste allowed; do not treat autocomplete=off as a security control | P1 | [GOV.UK password input](https://design-system.service.gov.uk/components/password-input/) |
| Secret echoed in UI, URL, logs, or transcript | Secret fields | Credential leak | Write-only field, never echo, never put in a query string; redact logs; explain that a token grants control | P0 | [Telegram](https://core.telegram.org/bots) |
| Non-Latin, emoji, or very long assistant/display name | Free text | Truncation, mojibake, rejected name | Accept Unicode generally; normalise only for the local address/slug if required; intentional ellipsis elsewhere; test with real names | P1 | [W3C personal names](https://www.w3.org/International/questions/qa-personal-names) |
| External login never returns | OAuth/device | Step waits forever | Expiry countdown, cancel, retry, open browser again; do not trust a stale wait | P0 | [RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628), [OpenRouter OAuth](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| Callback accepted without session binding | OAuth | Wrong account linked or a forged callback accepted | Per-session state bound to the local server; PKCE S256; single-use code | P0 | [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252) |
| Login opened inside an embedded webview | Desktop host | Provider login breaks or bypasses browser policy | Always use the system external browser | P0 | [RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252) |
| Provider busy/rate-limited during a test | Provider checks | Busy reported as invalid | Distinguish 401/403 from 408/429/5xx; honour Retry-After with a cap | P0 | [OpenRouter errors](https://openrouter.ai/docs/api-reference/errors.md), [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.txt) |
| Local service not running / CORS failure | Local route | Looks like an invalid URL or a credential error | Probe server-side through the Python backend; show start Ollama plus the exact command; keep the URL in the field | P0 | [Ollama /api/tags](https://docs.ollama.com/api/tags.md), [Ollama FAQ](https://docs.ollama.com/faq.md) |
| Local service up, no model pulled | Local route | Empty model list, no next step | Empty state with the exact pull command and refresh; do not present a model name that is not installed | P1 | [Ollama /api/tags](https://docs.ollama.com/api/tags.md) |
| Pairing code expires or is reused | Phone pairing | Correct code rejected; two pairings | Server expiry with countdown and regenerate; single use; invalidate prior codes | P0 | [repo] app.js:10084-10096; [RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628) |
| Pair URL unreachable from the phone / passkey over plain HTTP | Phone pairing | Phone network error; WebAuthn prompt never appears | Use a phone-reachable HTTPS origin (relay/tunnel/host setup), or fall back to local-owner confirmation; state the requirement before the attempt | P0 | [MDN WebAuthn](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) |
| Pairing countdown uses local wall clock | Phone pairing | Copy says a time that is wrong across devices/time zones | Server UTC expiry, relative localised duration (expires in 5 minutes); no absolute wall-clock claim | P1 | [W3C time zones](https://www.w3.org/International/wiki/WorkingWithTimeZones) |
| Duplicate submit or retry-after-timeout | Any create/send | Duplicate assistant, duplicate message, double spend | Idempotency keys and server dedupe; disabled plus aria-busy; retry the same key | P0 | [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests) |
| Provider times out mid-generation | First request | Partial output then silence; user re-sends | Abort with timeout, show partial plus retry, cap retries, distinguish provider vs local-server failure | P0 | [OpenRouter errors](https://openrouter.ai/docs/api-reference/errors.md), [MDN AbortSignal.timeout](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static) |
| Stale resume after refresh/provider return/device change | Whole flow | Wrong step, duplicate prompts, secrets asked again | Server-owned setup record plus revalidation on resume; treat reconnect like first-time setup | P0 | [NN/g smart-device onboarding](https://www.nngroup.com/articles/smart-device-onboarding/), [repo] app.js:135-189 |
| Offline or local server stopped | Whole flow | Infinite skeleton or shell dead end | Explicit connection-loss state; local route remains usable offline; retry probe | P1 | [repo] local-first premise; [open] |
| Mobile keyboard covers the primary action | First-run composer | Cannot continue on a phone | Visual-viewport handling, scroll into view, action above keyboard; scripted resize test | P1 | [MDN Visual Viewport](https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API), [W3C VirtualKeyboard](https://w3c.github.io/editing/docs/virtualkeyboard/index.html) |
| Terms version changes after acknowledgement | Consent | Loop or unacknowledged spend | Persist version plus timestamp; re-ask only when the version changes; show what changed | P1 | [chat-ui #252](https://github.com/huggingface/chat-ui/issues/252), [repo] app.py:7123-7125 |
| Inbound channel webhooks never arrive to a local install | Channel setup (optional) | Connection never confirms | Prefer outbound polling design; document a tunnel if webhooks are required; verify secret signatures | P1 (out of onboarding scope; channel surface already documents polling/outbox) | [Telegram Bot API](https://core.telegram.org/bots/api); docs/channels.md:63-78 |
| File-type spoofing, EXIF orientation, OCR failure, liveness false reject, camera permission denial, large uploads | Not in onboarding | Not applicable to this surface | Do not build; revisit only if an upload/camera step is added to onboarding | OUT | [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) |

Detailed matrices: notes/modality-edge-cases.md (text entry, OAuth/device flow, pairing, local-service discovery, first-request timeouts/idempotency, channel callbacks, cross-cutting state).

---

## 5. Front-end scope decision

### 5.1 Decision: PARTIALLY REQUIRED

Required: dedicated first-run routes and a step flow inside the existing server-rendered dashboard (for example an isolated onboarding route with dashboard chrome removed, a server-held setup draft, SSE or bounded polling for external waits, and reusable secret/status/error components). This is "dedicated flow, not a dedicated front-end stack".

Not required: a separate SPA, a hosted funnel, a native first-run window, or a mandatory product tour.

Justification:

- There is no separate account lifecycle to host: the owner is already the local operator, authenticated by local execution or the existing passkey/pairing session. A separate funnel would duplicate the shell, navigation, auth, CSRF, and session rules for no product benefit.
- Every self-hosted precedent studied runs first-run in the existing browser UI: Home Assistant, Jellyfin, and Nextcloud ([HA](https://www.home-assistant.io/getting-started/onboarding/), [Jellyfin](https://jellyfin.org/docs/general/post-install/setup-wizard/), [Nextcloud](https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html)). Jellyfin even has a skippable optional step and a next-steps list.
- The current failures are flow-state failures, not page-design failures: a missing route chooser, ambiguous readiness, no durable resume, an overlong setup page, and no explicit unavailable/offline states.
- The prompt's dedicated-funnel patterns come from hosted SaaS with account creation, pricing, and growth instrumentation. Hutch has none of those and a privacy promise; the funnel would contradict the product.

### 5.2 What the front-end must add

| Component | Required? | Notes |
|---|---|---|
| Isolated onboarding routes plus step flow | Yes | /onboarding routes inside the existing Jinja/vanilla dashboard; browser back/forward must not corrupt state; no dashboard chrome competing with setup |
| AI-service chooser | Yes | Three clear routes: hosted API key, local service, existing OpenCode login; one recommended default; defer apps/channels |
| Provider connection state machine | Yes | waiting/expired/cancelled/retry; bounded polling; persistent across reload; terms acknowledgement |
| Local setup record | Yes | Server-side SQLite record keyed to this installation; browser draft remains a cache |
| Assistant setup fast path | Yes | Name, instructions, route, Create; advanced controls moved behind optional customization |
| Reusable secret, status, error-summary, and focus components | Yes | One secret input pattern; one status region pattern; error summary with focus and links per GOV.UK pattern |
| Accessibility and mobile behaviour | Yes | Live regions, focus management, keyboard-aware layout, forced colours, reduced motion, 200 percent zoom |
| Remote analytics or drop-off dashboard | No | Not permitted by the product's no-telemetry posture; use local diagnostics |
| New SPA framework or separate build | No | Adds duplicate state and another origin for secrets |

### 5.3 Interaction state model the plan must cover

| State | Current coverage | Required behaviour |
|---|---|---|
| not-started / empty | First-run view renders; empty-state tests exist | One primary action; honest explanation of what is required; no fake model list |
| loading / checking | Checking status, aria-busy, polite region | Bounded deadline; visible feedback within 1 second; no focus theft; retry after timeout |
| saving | Some buttons disable; setup page disables create | Disabled plus aria-busy plus progress before ignoring clicks; preserve form state; idempotent request |
| error | Global setup error and per-field errors in places | Specific, adjacent, actionable; announce without focus; keep user input |
| blocked | Not explicit; no ready AI service implies it | Name what blocks progress and the single next action; allow deferral where the product can still act |
| provider-unavailable | Collapsed into setup/error | Per-provider state with retry/switch route; distinguish outage from bad credentials |
| permission-denied | Not explicit for provider/OS keyring; passkey errors exist | Human-readable cause plus recovery; never a raw exception string |
| offline | Not explicit in first run | Local-server-unreachable distinct from provider-unreachable; keep completed steps |
| stale-resume | Session draft restores; no server state | Revalidate provider state; resume at the right step; never show a false success |
| success / complete | First output and assistant creation exist | Unambiguous success, first useful output, next optional action; do not call saving a success |
| abandoned / returned later | No state | Local setup record plus a welcome-back-to-setup path that does not re-ask known values |

Acceptance checklist for the setup surface (from notes/frontend-quality.md, sections 4):

| # | Check | Pass criteria |
|---|---|---|
| R1 | Isolated route | Onboarding usable with dashboard nav removed; browser back/forward does not corrupt state |
| R2 | Draft resume | Refresh at every step restores the same step and values; expired external waits restart cleanly |
| R3 | Verified connected | Connected only after a real provider call; no client-only success |
| R4 | Idempotent submit | Double-click and refresh-resubmit create exactly one bot or first request |
| R5 | Provider failure classes | 401/402/408/429/503 each show distinct, actionable copy; Retry-After respected |
| R6 | External wait lifecycle | Countdown, cancel, restart, expiry; no dead-end spinner |
| R7 | Pairing | Manual code path keyboard-complete; expiry/regeneration; single-use enforcement; passkey only over the intended secure origin |
| R8 | Local model | Unreachable vs CORS-blocked vs no-model states distinguishable; probe is short-timeout |
| R9 | Screen reader | Each async transition announced once via a status region; error summary focused |
| R10 | Keyboard | Full flow completed without a mouse; focus never obscured by sticky UI |
| R11 | Zoom/reflow | 200 percent zoom and 320 CSS px pass without horizontal scroll for text content |
| R12 | Motion/theme | Reduced motion honoured; the fixed dark theme and forced colours pass visual review |
| R13 | Secret handling | Token never echoed/logged/put in URL; show/hide and paste work; autofill overwrite tested |
| R14 | Mobile | Phone browser: keyboard does not cover Continue; no in-page camera permission requested |

Keyboard, screen reader, reduced motion, dark mode: the repo already has a fixed dark theme and forced-colours overrides (docs/design-system.md:300-306); tests use reduced motion; one polite status region exists on first run. Gaps to plan: focus management across SPA route changes, an announced error/blocked state, keyboard-only escape from the provider chooser, visible focus not obscured by sticky chrome (WCAG 2.4.11), the 44 px coarse-pointer floor versus the 32 px icon-button base, and the OAuth popup fallback when the browser blocks it.

---

## 6. Visual-validation plan

The repo already has the right conventions: deterministic browser tests, captured artifacts with summary and assertions, opened-image statements, and honesty about what was not run (docs/realignment/visual-validation.md; docs/responsive/STATE.md:56-78). This plan extends that convention to onboarding. Full method: notes/visual-validation.md.

### 6.1 Principles (order matters)

1. Capture the real local app from source and its real states with deterministic fixtures; do not unit-mock the HTML.
2. Baseline first. Open the captured images and record a binary verdict (APPROVED or NEEDS WORK) per state and viewport. Generated is not reviewed.
3. Only after the baseline is judged, add automated regression comparison for APPROVED states: Playwright toHaveScreenshot, Chromium/Linux, fixed clock, animations disabled, committed baselines, masks only for genuinely dynamic regions. Playwright's docs warn that screenshots differ by browser/platform and that tolerances (threshold, maxDiffPixels) intentionally hide small differences ([Playwright visual comparisons](https://playwright.dev/docs/test-snapshots)).
4. Never substitute automation for the gate: CLS is temporal, Playwright waits for two stable frames and disables animations, jsdom has no layout engine, and WebAIM reports widespread WCAG failures that automated tools cannot all detect.
5. Record limitations honestly: Chromium on Linux only unless another engine is actually captured; no real phone, no notch, no native keyboard unless emulated by scripted resize.

### 6.2 Required breakpoints

| Width (CSS px) | Role | Notes |
|---|---|---|
| 320 | Reflow floor (WCAG 1.4.10 equivalent) | Repo first-run evidence exists at 320x740 |
| 375 | Required phone baseline | Primary acceptance width |
| 390 | Extra phone baseline used by the repo responsive work | |
| 768 | Required tablet baseline | |
| 900 / 1024 | Repo transition probes | 1366x768 laptop is a cheap extra |
| 1440 | Required desktop baseline | Existing first-run tests use 1280 and 1440 measured workbench widths |

Landscape phone 844x390 should be included because the onboarding composer is a fixed-height shell concern and the repo responsive work already tracks it.

### 6.3 Interaction states to capture (each is one evidence row)

Empty/no route; saved-unverified route; checking/loading; choosing AI (chooser open); provider form filled but unsaved; saving; invalid credential; provider unavailable; rate-limited/retry; permission denied (passkey or keyring); blocked (no route); offline/local server down; stale resume; assistant setup fast path; assistant setup advanced disclosures; creating; duplicate-submit guard; success/first output; first approval; error with long provider text; non-Latin/long assistant name; expired pairing code; dark theme; forced colours; reduced motion; 200 percent zoom; keyboard focus order; popup-blocked OAuth.

Key binary criteria per state: one primary next action visible; status text present without relying on colour; no horizontal overflow; focused control not obscured; no duplicate submission path; the written request survives.

### 6.4 Real-data scenarios

- No provider configured at all (fresh state directory).
- One hosted provider with a syntactically valid but dead key (test-only fixture, no live call).
- Ollama-like local endpoint: running with one model, running with zero models, not running.
- Saved route that is unverified (the Saved state).
- OpenCode installed/ready, installed/unauthenticated, not installed.
- ChatGPT plan sign-in disabled (the app's own disabled state).
- Provider returns 401 on generation and 200 on model list (the misleading readiness case).
- Provider never answers (timeout) and provider returns a long multi-line error.
- Terms acknowledgement required, then the terms notice version changes.
- Pairing: code generated, expired, reused, phone unreachable, passkey unsupported/denied.
- Assistant name with CJK/accented/60-character text; long provider error; duplicate submit.
- Reload mid-flow; reload after provider return; second tab; server restart; offline after load.
- Marketing boundary: the same claims as the app at 375/768/1440 (hero, availability, quickstart handoff).

### 6.5 The 13-item gate

Use the sourced 13-row gate in notes/visual-validation.md section 7 rather than the community "13-item" claim (provenance unverified, section 0.3). The rows cover: no horizontal overflow; 200 percent text zoom; text contrast; control boundaries/state contrast; focus not obscured; focus appearance; target size; theme evaluation (for Hutch: fixed dark theme plus forced colours, not a light theme); forced colours; reduced motion; feedback timing; error visibility; evidence chain. Missing evidence is a FAIL, not a partial pass.

What this gate catches that unit/DOM tests cannot: paint/layout/overflow/clipping, contrast and colour-only state, focus-ring quality and obscuring, touch-target spacing, viewport/reflow, font fallback and layout shift, dark/forced colours, transient loading/error states, and cross-platform glyph rendering (notes/visual-validation.md section 8).

### 6.6 Evidence protocol and lanes

- Evidence root: docs/onboarding/artifacts/<label>/ with one PNG per state/viewport, a validation.json row per capture (state, viewport, artifact, verdict, finding, source commit, reviewer), and assertions/summary files. Existing repo precedent: docs/realignment/artifacts/ and docs/responsive/screenshots/.
- Fast lane (pre-PR): deterministic DOM assertions, no screenshots (repo convention: npm run check:agent and focused pytest; browser lane is separate).
- Visual lane: the capture run above, plus opened-image review and a binary verdict. Required before claiming the onboarding UI complete; not replaced by CI screenshot diffs.
- Nightly/CI (optional, additive): Playwright toHaveScreenshot for APPROVED states only, Chromium/Linux, fixed clock and baselines, with a note that other engines remain unverified.

---

## 7. Marketing-site change inventory

The site is a static development-preview page, not a signup funnel: no hosted sign-up, no pricing, no card gate, no analytics, and CTAs explain availability or point to the public source ([repo] docs/marketing-site.md:1-8; website/index.html:293-327, 788-844). The prompt's pricing/free-forever/card-gate/welcome-back patterns mostly do not apply; the transferable boundary risks are expectation mismatch, false affordances, and missing trust context near the real entry point. Full analysis: notes/marketing-boundary.md.

### 7.1 Boundary failure classes that do apply

| # | Class | Mechanism | Hutch-specific evidence | Translation |
|---|---|---|---|---|
| B-1 | CTA promise vs actual first screen | A software CTA implies a packaged app; the real path is source install, local server start, model route | Tauri's distribution guide only provides installer tooling, not a Hutch installer ([Tauri distribute](https://v2.tauri.app/distribute/)); repo says no packaged installers (website/index.html:800) | The entry must name the real path and prerequisites before the click |
| B-2 | Download/availability mismatch | Every Download button can lead to a release with no binary | [nazar#42](https://github.com/moollaza/nazar/issues/42); [watchman#1299](https://github.com/meta/watchman/issues/1299) | Do not render a Download/Install action when the manifest has no artifact; show an explicit availability state and date |
| B-3 | Trust signal missing at the entry | Users weigh design quality, up-front disclosure, comprehensive/current content, connection to the rest of the web | NN/g four credibility factors ([NN/g trust](https://www.nngroup.com/articles/trustworthy-design/)) | Put MIT license, repo, issue tracker, requirements, data-flow note, and preview status next to the entry action |
| B-4 | Welcome/confirmation copy at the wrong time | A static first-run or banner greets a new user as welcome back | [closer-app#35](https://github.com/Jdrew001/closer-app/issues/35); [proof#121](https://github.com/rsdouglas/proof/issues/121); [sox#315](https://github.com/soscripted/sox/issues/315) | Greeting must be state-driven: first-run copy on fresh state, returning copy only after a completed prior session; success banner only after the action |
| B-5 | Banner used decoratively | Banners are for important, not-directly-page content; success banners confirm an expected event | [GOV.UK notification banner](https://design-system.service.gov.uk/components/notification-banner/) | No welcome-back banner on first run; dismissible; never re-show stale success after a later failure |
| B-6 | Service-unavailable state resembles onboarding | Provider/local health fails and the page renders an empty skeleton | [GOV.UK problem pages](https://design-system.service.gov.uk/patterns/problem-with-the-service-pages/) | Explicit problem copy with retry and what was saved, not a blank panel |
| B-7 | Pricing/plan CTA the product cannot honour | A pricing table or free-forever badge implies a hosted or entitled service | Repo FAQ already states no hosted inference/subscription (website/index.html:75-78, 94) | Keep the FAQ wording; scope model-usage costs near the CTA; do not add pricing tiers |
| B-8 | Locale/units/platform claims | Works anywhere/minutes implies localized, multi-platform support | W3C i18n defines localization as more than translation ([W3C](https://www.w3.org/International/questions/qa-i18n)) | State Linux-first, English UI, supported versions; avoid unqualified time-to-value claims |
| B-9 | Fake or borrowed social proof | Testimonials, stars, or badges the project cannot substantiate | Google review-snippet guidance ([Google](https://developers.google.com/search/docs/appearance/structured-data/review-snippet.md.txt)) | No invented testimonials, star counts, trusted-by, or benchmark rankings; link the actual repo/issues |
| B-10 | Release mechanics assumed automatic | A release is text plus optional uploaded assets; binaries are not generated by tagging | [GitHub releases docs](https://raw.githubusercontent.com/github/docs/main/content/repositories/releasing-projects-on-github/about-releases.md) | Add a release-completeness check; a release without the expected artifact must not be linked as installable |

### 7.2 Change inventory

| # | Element | Current state | Required change | Priority |
|---|---|---|---|---|
| M-01 | Primary hero CTA | "See the app" (in-page proof) and "Check availability" | Keep the in-page CTA; add one short expectation line: Linux, source install, development preview, model route required; link quickstart/requirements | P2 |
| M-02 | Trust microcopy near the entry | Hero promises local data, model/app choice, approvals; MIT/open source/Linux caption; license/repo links elsewhere | Add a compact trust row adjacent to the entry: MIT license, source repo, issue tracker, data-flow one-liner (local by default; hosted routes send content to the chosen provider), preview/no-warranty note | P2 |
| M-03 | Availability section (#get) | Truthful: no installers, no hosted sign-up, source setup needs Linux and a model route | Add a short "what happens after install" sequence: start local server, open dashboard, write first request, choose/verify a model route; state that first-run setup is required and which parts are optional | P2 |
| M-04 | Hutch desktop release manifest link | website/index.html:8 links downloads.json as the release manifest; downloads.json lists Windows/macOS/Ubuntu entries with empty artifact arrays | Remove the link until builds exist, or retitle as a preview contract and say all artifact lists are empty; never add a Download CTA | P2 |
| M-05 | Pricing/plan language | No pricing page, no tiers, no card gate; MIT and source are stated | Keep pricing absent while there is no paid offer; if a paid or hosted tier is ever added, the onboarding promise and the site must change together | OUT while no pricing exists |
| M-06 | Welcome/confirmation banner | No banner, no cookie consent, no analytics; the first-run page is the only welcome; app has no welcome-back copy | Do not add a marketing banner to the app. If a post-install confirmation is added, it must name the actual state (first run on this machine) and offer the real next action; dismissible, never re-shown after failure | OUT (pattern not applicable) |
| M-07 | Quickstart handoff | Availability links to the GitHub quickstart; docs/runtime-setup.md says no runtime or model weights are bundled | Keep the quickstart link live; add the same prerequisites to availability; test the link in the browser lane | P2 |
| M-08 | FAQ and structured data claims | FAQ and JSON-LD state local-first, MIT, development preview, model routes, approvals | Update only statements that change; keep development-preview and no-hosted-signup/no-installer statements accurate | P2 |
| M-09 | Entry measurement | Site sends no analytics; server logs may exist locally | Do not add third-party analytics. If measurement is required, use local, opt-in diagnostics and say so | OUT (conflicts with product policy) |
| M-10 | Support matrix / locale claims | Linux is stated; English-only and Python/OS version support are unstated | Publish a short support matrix (OS/arch, Python version, UI language) and date-stamp availability claims | P2 |

### 7.3 Welcome/confirmation banner state machine (if a banner is ever added)

| Event | Allowed copy | Forbidden |
|---|---|---|
| First launch, empty state | Welcome to Hutch. Start the local server, choose a model route, make a first request. | Welcome back; fake progress; invented profile/name |
| Returning after completed onboarding | Welcome back, only if a completed-session marker exists | Greeting a first-run user; showing it twice |
| Action succeeded (first request, bot created) | Success banner confirming exactly that action, dismissible | Success before completion; success surviving a later failure |
| Action failed / provider unavailable | Problem copy with retry/switch route; assertive only if blocking | Hiding the failure; rendering an empty success shell |
| Pairing code expired | Code expired; generate a new one | Infinite spinner; silently reusing the code |
| Server/manifest unavailable | There is a problem; try again later; what was saved | Blaming the user; showing steps that cannot run |

### 7.4 Entry-surface acceptance checklist (binary)

| # | Check | Evidence |
|---|---|---|
| 1 | The primary entry action names the real path (source install), not "download the app" | CTA label plus destination screenshot; quickstart link status |
| 2 | Prerequisites are listed before the click (Linux, Python 3.11+, local server start, model route) | Rendered text at 375/768/1440 |
| 3 | Availability is explicit and dated; an empty/no-artifact release renders honestly, never as Download | Manifest/release screenshots; last-checked date visible |
| 4 | Trust row adjacent to entry: MIT license, repo, issue tracker, preview status, data-flow note | One screenshot of the entry block; links resolve |
| 5 | No pricing tiers, card gate, account/waitlist capture, urgency, or countdown UI | Link/CTA inventory from website/index.html and site.js |
| 6 | No fabricated social proof or unverified numeric claims | Search of page text/schema; each remaining number has a source |
| 7 | First-run vs returning copy is state-driven; Welcome back cannot appear on a first run | Banner state-machine evidence |
| 8 | Success banners only after the action; failures carry retry/switch route; expired pairing says expired and offers regenerate | State screenshots plus validation.json rows |
| 9 | Locale/units/platform claims scoped to what is tested; English UI and Linux-first stated | Support-matrix screenshot; no any-device/worldwide phrasing |
| 10 | Every claim that could change (availability, versions, pricing) carries a date or links to a single dated source | Page copy audit |

What must not change: no fake social proof, no invented security certifications, no free-forever or hosted-plan implication, no analytics, no dead download CTA, no fabricated welcome/personalisation. The site's dev-preview honesty is a product asset; the boundary fix is to make the real path (source install, local host, model route) visible before the user leaves the site.

---

## 8. Open questions that cannot be answered without code inspection

These are deliberately unresolved; do not guess them in the plan.

1. What is the complete current step order and route structure of first-run (empty chat, provider chooser, OpenCode dialog, assistant setup, first send)? Which paths are server-rendered versus SPA-rendered?
2. Does provider readiness ever perform a real generation, or only list models/check status? What are the exact timeouts and retry budgets for each readiness check?
3. What is the exact server contract for model routes (states, error codes, state values) and what can a client distinguish (401 vs 403 vs 429 vs unreachable vs no credit)?
4. Does any server-side onboarding/setup state exist today, or is the browser sessionStorage draft the only persistence? What survives a full app restart, a new tab, a second device, and a desktop-host restart?
5. Is assistant creation idempotent server-side? Does the first chat send have an idempotency key and a dedupe window? What happens on double-click or retry-after-timeout?
6. How are API keys and bot tokens stored (OS keyring, 0600 file, env var), and what is the exact failure mode when the store is unavailable or the key is operator-managed? Is there an existing managed-by-operator state in the connections UI?
7. How do the Google/Outlook OAuth popup flows handle a blocked popup, callback mismatch, expired code, and reload during the wait? Is there a persistent pending/waiting state anywhere in the UI?
8. What exactly does the OpenCode modal poll, for how long, and what state does it leave if the user closes the modal or reloads during provider sign-in?
9. Does phone pairing support QR rendering anywhere (it currently shows URL plus code), and is the phone expected to reach an HTTPS origin? What does the product do when the phone cannot reach the host?
10. Is there an existing auth requirement for the local dashboard, and how do passkey/pairing sessions affect first-run on a second device?
11. Is the product intentionally English-only? There is no locale negotiation (lang="en" only), and schedule time zones accept free text with a UTC default. Confirm expectations for localised dates, relative expiry copy, and non-English names.
12. What are the exact YAML import limits and validations (max bytes, duplicate keys, aliases, command rules), and is the client-side file check merely cosmetic?
13. Is there an existing empty-state component or copy rule shared by bots/chats/connections, or is each state one-off?
14. Which visual states already have deterministic fixtures (tests/e2e/test_design_system.py first-run tests; docs/realignment/capture_first_run.py), and which require new fixtures (provider 401, timeout, offline, expired pairing, popup blocked)?
15. Does the Tauri desktop host change localhost/origin assumptions for OAuth loopback callbacks, passkeys, and pairing? Which browser engine renders the served dashboard in each host?
16. What are the browser/support boundaries (Chromium only? Firefox/WebKit?) for the locally served dashboard and the phone browser path, and therefore which visual baselines are authoritative?
17. Does any local telemetry or event log exist that could support activation counting without remote analytics, and what is the consent/export path?
18. Are the legacy server pages still reachable, and could a first-run user land on a legacy setup page with a different navigation model?
19. What is the current behavior when the local server stops or the network drops during first run, and is there an offline banner/state anywhere?
20. What is the exact relationship between docs/runtime-setup.md prerequisites and the first-run copy: does first run ever link to the runtime setup docs, or assume the user has read them?
21. Does website/site.js consume downloads.json, and does any CTA render when the manifest is empty or the platform unsupported? Is the deployed site identical to the repository source?
22. Are there any first-run or returning-user banners in the dashboard, and what state decides them?

---

## 9. Gate: top failure modes mapped to a realistic fix or an explicit out-of-scope rationale

| # | Top failure mode (P1) | Realistic fix | Owner surface | Mapped? |
|---|---|---|---|---|
| 1 | No-provider first-run detours into the general Apps and AI catalog; configuration precedes value | In-context AI-service chooser in first run; three routes; defer apps/devices; return to setup with the chosen route | First-run SPA view, provider chooser, connections deep link | YES |
| 2 | Readiness is ambiguous and not verified; a failed check is reported as no service | Per-route state model and a real probe policy; saved-unverified wording; per-check reasons and retry | First-run readiness, server model-route status endpoint | YES |
| 3 | Provider/secret connection loses context across the external browser and has no recovery state | Provider state machine with expiry, waiting, cancel, retry, restart; validate with a provider call; never block paste or echo secrets | First-run chooser, OpenCode dialog, connection cards, server routes | YES |
| 4 | Refresh/provider return/device change loses the setup position | Local server-owned setup record (status, step, per-step flags, timestamps, selected route) plus revalidation on resume; browser draft is a cache | Server store, first-run state module, assistant setup | YES |
| 5 | First action/status compete on phones and a11y states are incomplete | Keyboard-aware layout, sticky/scroll-safe primary action, explicit live regions for saving/error/blocked/success, focus management, visual gate at 320/375/768/1440 | First-run view, assistant setup, visual gate | YES |

Out-of-scope items, with rationale:

| Item | Verdict | Rationale |
|---|---|---|
| Identity-document upload, liveness/selfie, signature, payment card, generic file upload, OCR | OUT | No hosted account, pricing, identity, or document requirement in this surface; no comparable self-hosted first-run uses them; only a hosted Hutch cloud/payments/regulatory gate would add them |
| Voice/video capture, in-dashboard camera, QR scanning by the dashboard | OUT | Pairing is a manual code plus phone passkey; the product is text-first; no camera API in this surface |
| Light mode / theme switch | OUT | The product intentionally ships a fixed dark theme (docs/design-system.md:300-306); test dark and forced colours, not a light theme |
| Remote analytics, third-party funnel tracking, drop-off dashboards | OUT | Conflicts with the no-telemetry local-first posture (docs/marketing-site.md:1-8); use local, opt-in diagnostics |
| Public webhook retry/duplicate handling as an onboarding concern | OUT | Channel connections use outbound polling/outbox with documented delivery semantics (docs/channels.md:63-78); not a first-run modality |
| A separate onboarding front-end application/funnel | OUT | Partially required decision above: extend the existing dashboard instead; a separate funnel duplicates auth/state and contradicts the product model |
| The exact 13-item industry checklist claim | OUT as authority | Provenance unverified; replace with the sourced 13-row gate |
| A permanent onboarding checklist | OUT as default | Evidence supports optional, real-state progress only; no gating checklist |

---

## 10. Suggested reading order for the planning agent

1. docs/onboarding/research-brief.md (one page).
2. This document, sections 1, 3, 5, and 9 (the product-specific decisions).
3. docs/onboarding/notes/best-practices.md and failure-catalog.md (mechanics and source rows).
4. docs/onboarding/notes/modality-edge-cases.md and frontend-quality.md (per-modality tests and the front-end acceptance checklist).
5. docs/onboarding/notes/visual-validation.md and marketing-boundary.md (evidence protocol and the marketing change inventory).
6. docs/design-system.md sections on first run and setup recovery; docs/runtime-setup.md; docs/marketing-site.md.
