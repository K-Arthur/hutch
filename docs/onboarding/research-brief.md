# Onboarding and Setup - research brief for the planning agent

Date: 2026-10-29. One page. Full evidence: docs/onboarding/research.md and docs/onboarding/notes/ (six notes). Nothing here changes production code.

## 1. Job to be done

A user who already installed Hutch from source on their Linux machine opens the local dashboard for the first time and needs one real request answered with an AI service they trust, without configuring more than the next action requires. Activation means first useful output, not a saved assistant or a saved route. No hosted signup, account, pricing, KYC, or remote analytics exists on this surface.

## 2. Top five failure modes to resolve

| # | Failure mode (all P1) | Evidence | Fix direction | Done when |
|---|---|---|---|---|
| 1 | Configure-before-value detour: the no-provider first-run action lands on the general Apps and AI page, and AI providers are the third group after apps and devices | app.js:3314-3316, 3356-3374; group order 9803, 9807, 9811; comparable-products evidence in notes/best-practices.md | In-context AI-service chooser from first run: hosted key, local service, existing OpenCode login; defer apps/devices; return to setup with the chosen route | A user with no route reaches a chosen/verified route and the carried request without visiting the general catalog |
| 2 | Readiness is ambiguous and unverified: saved is read as working, and a failed check is reported as no service | app.js:3135-3214; OpenCode #38257 (models 200, generation 401); Jan #7658 | Per-route state model: checking, saved-unverified, verified, invalid-credential, no-credit, rate-limited, unreachable, permission-denied, timed-out; real probe policy; per-check reasons and retry | Each failure class has distinct, actionable copy and a retry/switch path; saved never claims verified |
| 3 | Provider/secret connection has no durable recovery state across the external browser | app.js:11390-11560; app.py:7100-7125; OpenCode #7992, #9922; RFC 8252 / RFC 8628 | Provider connection state machine with expiry countdown, waiting, cancel, retry, open-browser-again, restart; validate with a provider call; never echo a secret; keep paste working | External wait survives reload; expired/replayed/blocked cases each recover without a dead end |
| 4 | Refresh/provider return/another tab/device change loses the setup position | app.js:135-189, 1904-1918; no server-side onboarding state found; Hashnode state-machine guidance | Local server-owned setup record (status, step, per-step flags, timestamps, route) plus revalidation on resume; browser draft remains a cache | Reload at any step restores the same step and values; provider return lands at the right step |
| 5 | Phone-width and accessibility honesty gaps: primary action near the fold, keyboard unemulated, error/blocked states not consistently announced | docs/realignment/visual-validation.md:13-25 (375x812 action ends y=701; 320x740 y=729); MDN Visual Viewport; WCAG 4.1.3 | Keyboard-aware layout, sticky/scroll-safe primary action, explicit live regions for saving/error/blocked/success, focus management, binary visual gate | 320/375/768/1440 captures pass and the action remains reachable with the composer focused |

Secondary (P2, not in the top five but in the plan): assistant setup fast path (FM-06), terms-consent placement (FM-07), duplicate-submit idempotency (FM-08), secret-field autofill (FM-21), local-service CORS/offline probing (FM-22), pairing countdown/regenerate (FM-10), marketing availability/manifest truth (M-01 to M-04).

## 3. Modalities in scope

In scope: free text (request, purpose, names); secret text (provider key, bot token); plain endpoint URLs for local services; external-browser OAuth/PKCE and device-code login (system browser only, never embedded); manual one-time code plus passkey for phone pairing (no QR camera capture in this front-end); terms acknowledgement; first request with streamed output.

Out of scope, with rationale: identity-document upload, liveness/selfie video, signature, voice, in-dashboard camera capture, payment card, OCR, generic file upload. No hosted account/pricing/identity/doc requirement exists here; no comparable self-hosted first-run uses them. Re-open only if a hosted Hutch cloud, payments, or a regulatory identity gate is added.

## 4. Front-end decision

PARTIALLY REQUIRED. Build dedicated onboarding routes and a step flow inside the existing server-rendered dashboard (isolated route, server-held setup draft, bounded polling/SSE for external waits, reusable secret/status/error components). Do NOT build a separate SPA, hosted funnel, native first-run window, or mandatory tour. Precedents: Home Assistant, Jellyfin, Nextcloud all onboard inside the installed web UI. Full state matrix and 14-row acceptance checklist (R1-R14) are in notes/frontend-quality.md and research.md section 5.

## 5. Visual-validation acceptance criteria

- Breakpoints: required 320, 375, 768, 1440; extras 390, 900, 1024, 1366x768, 844x390 landscape.
- Required states: empty/no route; choosing AI; provider form filled; checking; saved-unverified; saving; invalid credential; provider unavailable; rate-limited; permission denied; blocked; offline/local server down; stale resume; assistant fast path; advanced disclosures; creating; duplicate-submit guard; success/first output; first approval; long provider error; non-Latin long name; expired pairing; dark theme; forced colours; reduced motion; 200 percent zoom; keyboard focus; popup-blocked OAuth.
- Method: baseline-first live screenshots of the real app with deterministic fixtures, then opened images with a binary APPROVED/NEEDS WORK verdict per state and viewport. Only after approval may Playwright toHaveScreenshot be added (Chromium/Linux, fixed clock, animations disabled, limited masks). Automated diff is additive, never the gate.
- Evidence: docs/onboarding/artifacts/<label>/ with PNGs plus validation.json rows (state, viewport, artifact, verdict, finding, source commit, reviewer); missing evidence is FAIL. Record limitations honestly (Chromium only unless another engine is captured; no real phone/notch/native keyboard).
- 13-item claim: provenance unverified; use the sourced 13-row gate in notes/visual-validation.md section 7 (overflow, 200 percent zoom, contrast, control boundaries, focus not obscured, focus appearance, target size, theme, forced colours, reduced motion, feedback timing, error visibility, evidence chain).
- Marketing boundary acceptance (10 binary checks in research.md section 7.4): entry names the real source-install path and prerequisites; availability is dated and never renders a dead Download; trust row adjacent to entry; no pricing/card/account capture; no fabricated social proof; no Welcome back on first run; success banners only after action; support matrix scoped and dated.

## 6. Out of scope for this surface (explicit)

KYC/identity modalities; light theme (fixed dark theme is a documented product decision; test dark and forced colours); remote analytics/drop-off dashboards (no-telemetry product policy; use local opt-in diagnostics); public webhook retry as an onboarding concern (channels use outbound polling/outbox); a separate onboarding funnel; a permanent mandatory checklist; the unsourced 13-item authority claim.

## 7. Open questions to route to code inspection before planning commits

The 22 open questions are listed in research.md section 8. The planning-critical ones: real readiness probes and timeouts; server model-route error taxonomy; whether any server-side setup state/idempotency exists; secret storage and operator-managed key behaviour; OAuth popup/callback state handling; OpenCode polling lifetime; phone reachability and passkey secure-context assumptions; locale support (English-only); desktop-host origin/webview differences; existing fixtures for failure states; whether site.js consumes downloads.json.

## 8. Gate status

PASS. docs/onboarding/research.md and docs/onboarding/research-brief.md exist. Every top-five failure mode is mapped to a realistic fix; every borrowed-but-inapplicable pattern is marked OUT with rationale. The plan may proceed; do not skip the open-questions section, and do not build KYC/identity or a separate funnel.
