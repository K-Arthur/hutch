# Hutch onboarding: front-end decision, states, and accessibility quality

Research note, 2026-10-29 (tracks B and C). Question: does Hutch's first-run setup need a
dedicated front-end, and what interaction states and accessibility quality must that surface
carry? External sources were opened live on 2026-10-29. Stack assumptions (Jinja server-rendered
dashboard, vanilla JS/SSE, FastAPI backend, no hosted accounts) come from the program brief;
exact current routes are being verified against code separately.

Labels: [ext] external doc directly shows this; [inf] inference for Hutch; [brief] program brief.

## 1. Decision: PARTIALLY REQUIRED - dedicated first-run routes inside the existing dashboard

Recommendation: build an isolated first-run route and step flow (e.g. /onboarding/*) inside the
existing server-rendered dashboard: no dashboard chrome, server-held setup draft, SSE progress,
a small set of reusable form/status components. Do not build a separate SPA, a hosted funnel, or
a mandatory product tour. This is "dedicated flow, not dedicated front-end stack".

| Option | Verdict | Why | Cost / risk |
|---|---|---|---|
| Embed setup as ordinary dashboard pages | not sufficient | no isolated route means navigation and existing data compete with setup; multi-step questions need one-thing-per-page and durable state | low cost, high confusion; no clean resume |
| Dedicated /onboarding routes + wizard in the existing Jinja/vanilla app | required | every self-hosted precedent studied puts first-run setup in the existing browser UI, as a multi-step wizard [ext](https://www.home-assistant.io/getting-started/onboarding/), [ext](https://jellyfin.org/docs/general/post-install/setup-wizard/), [ext](https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html) | moderate: step registry, draft persistence, SSE, a11y components |
| Separate SPA or hosted onboarding funnel | not required | no hosted account/payment/analytics surface [brief]; heavy tutorials do not improve success [ext](https://www.nngroup.com/articles/mobile-tutorials/); a second build/runtime increases attack and maintenance surface for a local-first app | high build cost, duplicate state, another origin for secrets |
| Native Tauri first-run window | not required | no packaged installers published [brief]; browser onboarding is the established self-hosted pattern [ext](https://www.home-assistant.io/getting-started/onboarding/) | high: two UI surfaces to keep in sync |

### 1.1 Self-hosted first-run precedents (dedicated flow, shared shell)

| Product | Where first-run setup lives | Shape shown by docs | Pattern worth copying |
|---|---|---|---|
| Home Assistant | existing web UI after install | welcome -> create account or restore backup -> location/sharing -> finish; location derives time zone/unit/currency | derive locale/timezone where possible instead of asking; explicit "finish" step [ext](https://www.home-assistant.io/getting-started/onboarding/) |
| Jellyfin | existing web UI | wizard: language -> admin account -> media libraries (skippable) -> remote access -> next-steps list | optional steps are skippable; ends with a "next steps" checklist [ext](https://jellyfin.org/docs/general/post-install/setup-wizard/) |
| Nextcloud | existing web UI | three browser steps: admin account -> install -> done; advanced storage/database settings behind an expandable section | default path short, advanced settings progressively disclosed [ext](https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html) |

Also consistent with UX evidence: progressive disclosure defers advanced options
[ext](https://www.nngroup.com/articles/progressive-disclosure/); one-thing-per-page and asking
each question once reduce errors [ext](https://design-system.service.gov.uk/patterns/question-pages/).
Smart-device onboarding guidance is the closest analogue to model/channel setup: present a visual
wizard, give honest meaningful progress, handle errors transparently, and treat reconnection like
first-time setup [ext](https://www.nngroup.com/articles/smart-device-onboarding/).

### 1.2 Scope boundaries for the dedicated flow

| In scope | Out of scope |
|---|---|
| Isolated /onboarding route(s), step order, back/forward, exit-and-resume | new SPA framework, client-side router, new design system |
| Server-side setup draft keyed to this install/session | hosted account, analytics, payment, KYC/identity, uploads |
| Provider/model validators that make real calls before "connected" | optional product tour, gamification, streak/confetti onboarding |
| SSE progress for long external waits (OAuth, pairing, model load) | camera capture, in-page QR scanning, file/image pipeline |
| Reusable secret field, status region, error summary, focus management | notifications/email/phone verification (no such surface today) |

## 2. Interaction state model

Model each step as an explicit state machine, not a set of booleans. One SetupStep state per
step plus one global connection state; transitions are server-confirmed where money or secrets
are involved.

| State | Meaning | UI treatment | Screen-reader announcement | Durability |
|---|---|---|---|---|
| empty / not configured | fresh install, step untouched | short explainer, one primary action, no fake defaults | none needed | server draft created |
| validating / loading | provider probe, model list fetch | inline spinner on the control, label change, cancel where possible | role=status polite "Checking provider..." once [ext](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html) | transient |
| awaiting external | user in provider browser, pairing poll, slow model load | persistent wait panel with countdown, "open again", cancel | assertive only if time-critical; otherwise polite [ext](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Live_Regions) | step stays resumable |
| saving | POST in flight | button progress before any double-click guard; do not merely disable silently [ext](https://design-system.service.gov.uk/components/button/) | polite "Saving..." | server idempotency key |
| success confirmed | server/provider verified | explicit what happened + next optional step; never a dead end | polite "Connected" (not repeated per poll) | draft marks step done |
| validation error | bad field value | error summary listing links, focus moved to summary, inline messages tied via aria-describedby [ext](https://design-system.service.gov.uk/components/error-summary/), [ext](https://design-system.service.gov.uk/components/error-message/) | focus + summary text announces | draft keeps input |
| provider error | 401/402/403/408/429/502/503 | distinguish bad credential vs no credit vs busy vs down; show provider message and retry only when retryable [ext](https://openrouter.ai/docs/api-reference/errors.md) | polite, once per attempt | draft keeps input |
| blocked / needs action outside app | user must create key, start Ollama, approve in browser | block with exact next action and return path | polite | resumable |
| permission denied | only if a browser permission modal exists (e.g. passkey prompt canceled) | explain, offer typed-code fallback; no camera permission in this flow [brief] | polite | resumable |
| offline / local server down | network unreachable or local process stopped | separate "local Hutch server not reachable" from "provider not reachable"; retry probe [inf] | polite | last confirmed state shown |
| stale resume | draft older than current code/step/secret | never silently trust UI; revalidate provider state on resume; offer restart [ext](https://www.nngroup.com/articles/smart-device-onboarding/) | polite summary of resumed step | server draft + version |
| duplicate submit | second click/refresh resubmit | same idempotency key; server returns stored result instead of creating twice [ext](https://docs.stripe.com/api/idempotent_requests) | polite "Already saved" if visible | shared key |

Design rules that follow:

| Rule | Detail | Source |
|---|---|---|
| Never show "connected" without a real provider call | format checks are hints only | [ext](https://openrouter.ai/docs/api-reference/errors.md) |
| Feedback timing | immediate ack <1 s; progress/ETA beyond 10 s; open-ended waits get honest state | [ext](https://www.nngroup.com/articles/response-times-3-important-limits/) |
| Retry policy | honor Retry-After on 429/503, exponential backoff with cap, abort via AbortSignal.timeout | [ext](https://www.rfc-editor.org/rfc/rfc6585.txt), [ext](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static) |
| Durable draft | save step, values, timestamps, provider ids server-side; resume revalidates | [ext](https://www.nngroup.com/articles/smart-device-onboarding/), [ext](https://design-system.service.gov.uk/patterns/question-pages/) |
| Review before commit | summary of model route + bot + channel before creating anything | [ext](https://design-system.service.gov.uk/patterns/check-answers/) |
| Expiring waits | OAuth codes ~10 min single-use; pairing codes expire and must regenerate | [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md), [ext](https://datatracker.ietf.org/doc/html/rfc8628) |
| Cancellation | every external wait has cancel + restart; no dead-end spinner | [ext](https://datatracker.ietf.org/doc/html/rfc8628) |
| Success state | show what is configured and the next optional step | [ext](https://jellyfin.org/docs/general/post-install/setup-wizard/) |

## 3. Accessibility and input-quality requirements

| Area | Must do | Common pitfall | Verification | Source |
|---|---|---|---|---|
| Keyboard only | every step, reveal, retry, cancel, and back is keyboard-operable in logical order | custom toggle divs without keyboard activation | tab through with mouse unplugged | [ext](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html) |
| Focus visible | visible focus indicator on every control | CSS removes outline; low-contrast ring | visual check at 200% zoom | [ext](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html) |
| Focus not obscured | sticky footer/help panel/mobile keyboard must not hide the focused control | sticky "Continue" bar over focused input | tab to last field with panel open | [ext](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html) |
| Async status | role=status (implicit polite) for "Checking...", "Saved", "Waiting for browser"; aria-busy until multi-part update completes | updating the whole step region so announcements get lost or doubled | Playwright asserts status text; screen-reader spot check | [ext](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html), [ext](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html), [ext](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Attributes/aria-busy) |
| Error handling | error summary at top, focus moved to it, each link goes to its field; inline error programmatically associated | inline red text only, no focus move, no association | keyboard + screenreader walkthrough | [ext](https://design-system.service.gov.uk/components/error-summary/), [ext](https://design-system.service.gov.uk/components/error-message/) |
| Reduced motion | honor prefers-reduced-motion for spinners, transitions, progress animation | infinite bounce/spin as the only progress cue | OS setting test | [ext](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) |
| Dark/light | follow prefers-color-scheme, test both for contrast on disabled/error/status colors | dark theme with invisible borders/error text | screenshot both themes | [ext](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme) |
| 200% zoom / reflow | usable at 200% zoom and 320 CSS px width without 2D scrolling | fixed-width token field, wide tables, sticky side panel | browser zoom + 320 px viewport | [ext](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html), [ext](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) |
| API-key/token fields | one-line secret input with show/hide, spellcheck=false, autocapitalize=none; paste always allowed; never autosave silently | browser autofill overwrites token; Chrome ignores autocomplete=off on type=password; autosave then persists the wrong secret | device test with saved Chrome credentials | [ext](https://design-system.service.gov.uk/components/password-input/), [ext](https://web.dev/learn/forms/identity), [anecdote](https://github.com/simstudioai/sim/pull/4973), [anecdote](https://github.com/langflow-ai/langflow/pull/13748) |
| Autocomplete semantics | use documented autocomplete tokens where a real credential field exists; document that "off" is a hint only | treating autocomplete=off as a security control | inspect attribute + real autofill test | [ext](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/autocomplete), [ext](https://design-system.service.gov.uk/components/password-input/) |
| Passkeys | rely on the browser's WebAuthn UI; requires a secure context and origin-bound credentials | custom passkey modal; assuming passkey works from a plain-HTTP LAN IP | test on phone over the intended URL | [ext](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) |
| Mobile keyboard | focused field scrolls into view; primary action stays reachable; use visual-viewport/keyboard geometry when composing the sticky area | footer CTA covered by OS keyboard; fixed footer over fields | phone device test, portrait, both keyboards | [ext](https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API), [ext](https://w3c.github.io/editing/docs/virtualkeyboard/index.html) |
| Test determinism | rely on Playwright actionability (visible/stable/enabled/receives events) rather than fixed sleeps; assert on role/status text | sleep-based tests flake on streamed/SSE states | e2e run with provider mocked at the boundary | [ext](https://playwright.dev/docs/actionability) |
| Service-unavailable communication | a distinct, calm page when the local server or provider is down, with retry and no data loss | generic exception page mid-flow | fault-injection test | [ext](https://design-system.service.gov.uk/patterns/service-unavailable-pages/) |

## 4. Acceptance checklist for the setup surface

| # | Check | Pass criteria |
|---|---|---|
| R1 | Isolated route | /onboarding usable with dashboard nav removed; browser back/forward does not corrupt state |
| R2 | Draft resume | refresh at every step restores same step and values; expired external waits restart cleanly |
| R3 | Verified connected | "Connected" only after a real provider call; no client-only success |
| R4 | Idempotent submit | double-click and refresh-resubmit create exactly one bot/first request |
| R5 | Provider failure classes | 401/402/408/429/503 each show distinct, actionable copy; Retry-After respected |
| R6 | External wait lifecycle | countdown, cancel, restart, expiry; no dead-end spinner |
| R7 | Pairing | manual code path keyboard-complete; expiry/regeneration; single-use enforcement; passkey only over intended secure origin |
| R8 | Local model | unreachable vs CORS-blocked vs no-model states distinguishable; probe is short-timeout |
| R9 | Screen reader | each async transition announced once via status region; error summary focused |
| R10 | Keyboard | full flow completed without mouse; focus never obscured by sticky UI |
| R11 | Zoom/reflow | 200% zoom and 320 CSS px pass without horizontal scroll for text content |
| R12 | Motion/theme | reduced motion honored; light and dark both pass visual review |
| R13 | Secret handling | token never echoed/logged/put in URL; show/hide + paste work; autofill overwrite tested |
| R14 | Mobile | phone browser: keyboard does not cover Continue; no in-page camera permission requested |

## 5. Open questions for code inspection

1. Does the dashboard have a route/state pattern that can host an isolated first-run flow without a
   second app shell, and does it already have server-side draft storage?
2. Is there an existing component for secrets/errors/status, or is a small shared set needed?
3. Is the local server bound to 127.0.0.1 only? That decides whether pairing/passkeys can use a LAN
   URL at all or must go through an HTTPS relay.
4. Does setup already use SSE for model output? Reuse it for step progress or keep REST polling?
5. What is the idempotency story for POST /bots and "first request"? None may exist today.
6. Which optional steps (bot, channel, approval teaching) are truly optional in code, and can they be
   skipped without blocking first useful output? Jellyfin's skippable-library step is the model
   [ext](https://jellyfin.org/docs/general/post-install/setup-wizard/).

## Sources

All opened 2026-10-29. Type: P = primary (standard/vendor/official docs), S = secondary
(credible UX research/agency), A = anecdote (project issue/PR, used only as a bug-class signal).

| URL | Title | Type | Supports |
|---|---|---|---|
| https://www.home-assistant.io/getting-started/onboarding/ | Onboarding Home Assistant | P | self-hosted first-run in existing browser UI |
| https://jellyfin.org/docs/general/post-install/setup-wizard/ | Jellyfin setup wizard | P | wizard steps, skippable optional step, next steps |
| https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html | Nextcloud installation wizard | P | short 3-step browser setup, progressive disclosure |
| https://www.nngroup.com/articles/mobile-tutorials/ | NN/g mobile tutorials research | S | tutorials do not improve success |
| https://www.nngroup.com/articles/progressive-disclosure/ | NN/g progressive disclosure | S | defer advanced options |
| https://www.nngroup.com/articles/smart-device-onboarding/ | NN/g smart-device onboarding | S | visual wizard, honest progress, transparent errors, reconnect = first setup |
| https://www.nngroup.com/articles/response-times-3-important-limits/ | NN/g response time limits | S | 0.1/1/10 s feedback thresholds |
| https://design-system.service.gov.uk/patterns/question-pages/ | GOV.UK question pages | P | one thing per page, ask each question once |
| https://design-system.service.gov.uk/patterns/check-answers/ | GOV.UK check answers | P | review before submit |
| https://design-system.service.gov.uk/components/error-summary/ | GOV.UK error summary | P | focus move + error links |
| https://design-system.service.gov.uk/components/error-message/ | GOV.UK error message | P | inline error association |
| https://design-system.service.gov.uk/components/password-input/ | GOV.UK password input | P | show/hide, allow paste, spellcheck/autocapitalize |
| https://design-system.service.gov.uk/components/button/ | GOV.UK button | P | prevent double click, show progress first |
| https://design-system.service.gov.uk/patterns/service-unavailable-pages/ | GOV.UK service unavailable pages | P | distinct unavailable state |
| https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html | WCAG 2.2 SC 4.1.3 Status Messages | P | programmatic status without focus |
| https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html | WAI technique ARIA22 | P | role=status, polite, aria-atomic |
| https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Live_Regions | MDN ARIA live regions | P | polite vs assertive |
| https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Attributes/aria-busy | MDN aria-busy | P | delay announcements until updates complete |
| https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html | WCAG 2.2 SC 2.1.1 Keyboard | P | keyboard operability |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html | WCAG 2.2 SC 2.4.7 Focus Visible | P | visible focus indicator |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html | WCAG 2.2 SC 2.4.11 Focus Not Obscured | P | sticky UI must not hide focus |
| https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html | WCAG 2.2 SC 1.4.4 Resize Text | P | 200% text scaling |
| https://www.w3.org/WAI/WCAG22/Understanding/reflow.html | WCAG 2.2 SC 1.4.10 Reflow | P | 320 CSS px / 400% zoom |
| https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion | MDN prefers-reduced-motion | P | reduced motion |
| https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme | MDN prefers-color-scheme | P | light/dark preference |
| https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/autocomplete | MDN autocomplete attribute | P | autofill semantics are hints |
| https://web.dev/learn/forms/identity | web.dev Learn Forms: Identity | P | autocomplete tokens, allow paste |
| https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API | MDN Web Authentication API | P | passkey secure-context/origin constraints |
| https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API | MDN Visual Viewport API | P | keyboard shrinks visual viewport |
| https://w3c.github.io/editing/docs/virtualkeyboard/index.html | W3C VirtualKeyboard API | P | keyboard geometry, overlaysContent |
| https://playwright.dev/docs/actionability | Playwright auto-waiting | P | actionability-based test checks |
| https://docs.stripe.com/api/idempotent_requests | Stripe idempotent requests | P | duplicate-submit safety |
| https://openrouter.ai/docs/api-reference/errors.md | OpenRouter error codes | P | provider failure classes, Retry-After |
| https://openrouter.ai/docs/guides/overview/auth/oauth.md | OpenRouter OAuth PKCE | P | expiring single-use OAuth code |
| https://datatracker.ietf.org/doc/html/rfc8252 | RFC 8252 OAuth 2.0 for Native Apps | P | external browser, loopback redirect |
| https://datatracker.ietf.org/doc/html/rfc8628 | RFC 8628 Device Authorization Grant | P | expiry/interval/cancel for external waits |
| https://www.rfc-editor.org/rfc/rfc6585.txt | RFC 6585 (429 + Retry-After) | P | retry pacing |
| https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static | MDN AbortSignal.timeout() | P | abortable timeouts |
| https://github.com/simstudioai/sim/pull/4973 | Sim: autofill on API token field | A | autofill overwrite bug class |
| https://github.com/langflow-ai/langflow/pull/13748 | Langflow: autofill corrupting config fields | A | autosave amplifies autofill corruption |
