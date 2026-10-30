# Hutch onboarding: modality inventory and edge-case matrix

Research note, 2026-10-29. Scope: the first-run experience inside the locally served
Hutch dashboard after install-from-source and local server start (AI model route,
provider/connection terms, first request, optional named bot, optional channel,
approval model). Hutch's exact current flow is NOT asserted here; it is being
verified separately against code. External sources were opened live on 2026-10-29.

Confidence labels: [ext] external doc directly shows this; [inf] inference for Hutch
from that doc; [open] needs code inspection before the plan commits.

## 1. Modality inventory (what the plan must build)

| # | Modality | In onboarding? | Plan status | Front-end surface | Evidence |
|---|---|---|---|---|---|
| 1 | Hosted provider API key paste | yes | required | single-line secret field, paste, reveal toggle, test-connect | OpenRouter shows keys once and never again [ext](https://openrouter.ai/docs/guides/overview/auth/management-api-keys.md) |
| 2 | Token/secret lifecycle (clear, replace, revoke hint) | yes | required | masked value, "replace" flow, link to provider dashboard | Token grants full control and must be stored securely [ext](https://core.telegram.org/bots) |
| 3 | External-browser OAuth/PKCE with loopback callback | if provider offers login | required only for providers that support it | "Open browser" action, waiting state, cancel/retry | OpenRouter supports localhost callbacks on any port; code is single-use and expires in 10 min [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| 4 | Device-code manual entry fallback | if provider supports it | partial, only if that provider documents it | "Enter code" field + polling wait state | RFC 8628 defines user_code, verification_uri, expires_in, interval, authorization_pending/slow_down [ext](https://datatracker.ietf.org/doc/html/rfc8628) |
| 5 | Phone pairing by one-time manual code | optional channel step | required (per program lead: no in-page camera capture) | desktop shows code + URL; phone enters code; desktop polls state | RFC 8628 is the closest standard shape: short code, expiry, poll [ext](https://datatracker.ietf.org/doc/html/rfc8628) |
| 6 | Passkey/handoff confirmation for pairing | optional, if passkeys used | partial; must not assume it works over plain LAN HTTP | phone browser WebAuthn prompt; desktop waits | WebAuthn requires a secure context and signatures are origin-bound [ext](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) |
| 7 | QR rendered on desktop (convenience only) | optional | optional; no in-page scanner | static QR/URL that a native phone app opens | Telegram QR login is scanned by an already-logged-in native app, not a web page [ext](https://core.telegram.org/api/qr-login) |
| 8 | Local model service discovery/health | yes (Ollama-like local route) | required | base URL field + "Detect" action + model list | Ollama exposes GET /api/tags on http://localhost:11434 [ext](https://docs.ollama.com/api/tags.md) |
| 9 | Assistant ("bot") name, response style | optional step | required only for the optional bot wizard | Unicode text field, style select | W3C: do not limit name fields by charset or size; romanization loses information [ext](https://www.w3.org/International/questions/qa-personal-names) |
| 10 | First request prompt + first output (streamed/SSE) | yes | required | textarea, send, token streaming, error and retry | Streaming partially succeeded/failed is a documented provider error class [ext](https://openrouter.ai/docs/api-reference/errors.md) |
| 11 | Channel bot token paste (Telegram-style) | optional | required for the optional channel step | secret field + getMe-style validation call | Bot token format 123456:ABC-...; unique per bot [ext](https://core.telegram.org/bots/api) |
| 12 | Provider/connection terms acknowledgement | yes | required | checkbox + short plain-language summary, persisted with version | Provider key spends the user's own account credit [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| 13 | Approval-model teaching step (read-only) | yes | required, static | short explainer or inline help; no input | Local-first explicit approval is the product premise (program brief) |

### 1.1 Explicitly out of scope (do not over-build)

| Modality | Verdict | Why, with evidence | What would put it back in scope |
|---|---|---|---|
| Identity-document upload | out | No account, hosted sign-up, pricing, payment or KYC surface is in the product brief; self-hosted onboarding precedents are account-on-your-own-server only [ext](https://www.home-assistant.io/getting-started/onboarding/), [ext](https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html) | A hosted Hutch cloud, payments, or regulatory age/identity gating |
| Liveness/video selfie | out | Same as above; no camera modality described in the brief | Identity verification or age assurance requirement |
| Signature capture | out | No contract/e-sign surface in onboarding; approval model is an in-app permission gate, not a legal signature | Terms that must be legally signed |
| Voice input | out | Not described; channels are text bots. Telegram bot token is text config [ext](https://core.telegram.org/bots/api) | Voice-first channel or accessibility requirement |
| Camera capture in the dashboard (getUserMedia) | out | Pairing is manual code + passkey per program lead; QR is scanned by a native phone app [ext](https://core.telegram.org/api/qr-login) | An in-page QR scanner or avatar/photo capture step |
| Payment card | out | No pricing tiers/payment card in brief; local model route costs nothing at the vendor | Hosted inference resale inside onboarding |
| OCR | out | No document/image input in onboarding | Reading a receipt/document during setup |
| File upload (any) | out | No upload step in the described flow | Importing config, avatar, or document |
| EXIF/orientation handling | out | No image path in onboarding; only relevant to a future chat-attachment surface (Chromium handles EXIF by default in createImageBitmap) [ext](https://developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap) | Image attachments on the chat surface |
| File-type spoofing / large-file limits | out | Only applies once an upload exists; OWASP treats it as upload-path hardening [ext](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Any upload endpoint |

## 2. Edge-case matrix (applicable modalities only)

Priority: P0 blocks completion or leaks a secret; P1 causes wrong state or support load;
P2 polish.

### 2.1 Text entry: API keys, bot tokens, assistant name

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| Token pasted with whitespace/newline from a terminal | 401 invalid key; user believes key is wrong | provider error code on test call | trim, strip "Bearer ", keep value in the field for edit, pass provider message through | P0 | 401 = missing/invalid/revoked key [ext](https://openrouter.ai/docs/api-reference/errors.md) |
| Client-only format check treated as success | "Connected" shown for a dead key | only a real provider call proves it | validate via provider endpoint (e.g. getMe) before marking connected | P0 | bot token format is documented, but format alone does not prove validity [ext](https://core.telegram.org/bots/api) |
| Browser autofill injects saved credentials into a token field | wrong secret saved silently; later calls fail | value differs from paste; Chrome ignores autocomplete="off" on type=password | dedicated SecretInput component, no autosave, explicit save+verify; do not rely on autocomplete=off alone | P1 | two independent product fixes for this class [anecdote](https://github.com/simstudioai/sim/pull/4973), [anecdote](https://github.com/langflow-ai/langflow/pull/13748) |
| Password-manager "save password?" prompt on a token field | user stores the token twice or refuses the flow | UX report only | label/copy it as a setup token, keep autocomplete hints conservative, allow paste | P2 | GOV.UK password guidance: managers may fill even when autocomplete is off; always allow paste [ext](https://design-system.service.gov.uk/components/password-input/) |
| Paste blocked by the field | users cannot move token from terminal/password manager | manual report | never block paste or right-click; no onPaste prevention | P1 | "Always allow users to copy and paste" in password fields [ext](https://design-system.service.gov.uk/components/password-input/) |
| Secret echoed after save, in URL, or in logs | credential leak | code review | write-only field, never echo, never put in query string; warn token grants full bot control | P0 | tokens grant full control and must be stored securely [ext](https://core.telegram.org/bots) |
| Non-Latin assistant name truncated or rejected | user cannot name their bot in their script | validation error or mojibake | accept any Unicode, no charset whitelist, generous length, no transliteration | P1 | W3C: do not limit name field size; romanization loses distinctions [ext](https://www.w3.org/International/questions/qa-personal-names) |
| Very long / emoji / zero-width names | layout break, duplicate-looking bots | visual test | render with wrapping + ellipsis; length limit with clear error; do not forbid user content (repo no-emoji rule is for source/docs/UI, not user data) [open] | P2 | W3C personal names guidance [ext](https://www.w3.org/International/questions/qa-personal-names) |

### 2.2 External-browser OAuth / device login

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| User never returns from provider browser tab | step stuck on "waiting" forever | local state has no callback within expiry | show expiry countdown, "open browser again", cancel; provider code expires in 10 min | P0 | single-use code, 10 min expiry [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| Callback accepted without session binding (CSRF) | wrong account or attacker-supplied code linked | state mismatch on callback | generate per-session state, verify on return; PKCE alone is not session binding | P0 | RFC 8252 recommends the state parameter to bind request/response [ext](https://datatracker.ietf.org/doc/html/rfc8252) |
| Authorization code replayed | noisy 4xx and confusing retry loop | exchange fails | code is single-use; clear verifier after exchange; offer restart | P1 | [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| Login opened inside embedded webview (Tauri/webview window) | provider login may break; violates native-app BCP | request user-agent / known failure | always open the system external browser, not an in-app webview | P0 | OAuth for native apps should use an external user-agent [ext](https://datatracker.ietf.org/doc/html/rfc8252) |
| Loopback callback port unavailable/conflicting | redirect never lands | callback server bind error | bind an ephemeral free port; provider must accept any port; show manual fallback | P1 | providers MUST allow any port for loopback redirects [ext](https://datatracker.ietf.org/doc/html/rfc8252); OpenRouter supports any port [ext](https://openrouter.ai/docs/guides/overview/auth/oauth.md) |
| Provider account has no credit / key revoked mid-flow | login "succeeds" but first request 402/401 | test request against provider | test call before marking ready; surface provider-specific message | P0 | 402 insufficient credits; 401 invalid/revoked key [ext](https://openrouter.ai/docs/api-reference/errors.md) |
| Rate limit or provider timeout during test | validation says "invalid" when it is just busy | HTTP 429/503/408 vs 401 | distinguish auth errors from transient errors; retry with Retry-After and cap | P0 | 408/429/502/503 and Retry-After header [ext](https://openrouter.ai/docs/api-reference/errors.md); 429 + Retry-After semantics [ext](https://www.rfc-editor.org/rfc/rfc6585.txt) |
| Refresh during wait | state resets; duplicate auth attempt | reload loses state | persist step to server-side draft keyed by install/session; resume or restart explicitly | P1 | see 2.7 |
| Device-flow polling too fast | provider returns slow_down; UI shows error | error code | honor interval, add 5s on slow_down, abort on expiry | P1 | [ext](https://datatracker.ietf.org/doc/html/rfc8628) |

### 2.3 Phone pairing: one-time manual code + passkey

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| Code expires while the user moves to the phone | "invalid code" on a correct code | expiry timestamp passed | server-side expiry, visible countdown, one-click regenerate | P0 | RFC 8628 requires expires_in for device/user codes [ext](https://datatracker.ietf.org/doc/html/rfc8628); Telegram rejects AUTH_TOKEN_EXPIRED and requires re-scan [ext](https://core.telegram.org/api/qr-login) |
| Code reused / approved twice | two pairings or confusing duplicate session | code already consumed | single-use code; invalidate on success and on new code | P0 | AUTH_TOKEN_ALREADY_ACCEPTED [ext](https://core.telegram.org/api/qr-login) |
| Pair URL unreachable from the phone | phone shows network error | phone-side report; desktop poll never completes | pairing URL must be phone-reachable: provider relay/public URL, or LAN IP with firewall check; loopback URLs are same-device only | P0 | loopback redirects are for the same device [ext](https://datatracker.ietf.org/doc/html/rfc8252) [inf] |
| Passkey attempted over plain HTTP LAN address | WebAuthn prompt never appears | JS throws / no credential | WebAuthn requires a secure context; if passkeys are required the phone must use HTTPS (relay or tunnel) or localhost-class origin | P0 | [ext](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) |
| Passkey origin mismatch between phone and desktop | credential cannot be used across the two origins | RP ID/origin error | one shared relying-party origin for both surfaces, or fall back to code confirmation | P1 | signatures are origin-bound [ext](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API) [inf] |
| Screenshot/screen-share leaks the code | attacker completes pairing | unexplained pairing | short TTL, show device name on confirmation step, revoke from desktop after pair | P1 | QR/token flows in message apps treat the token as a login token [ext](https://core.telegram.org/api/qr-login) [inf] |
| Clock skew/timezone between desktop and phone | countdown or "expires at" copy is wrong | inconsistent timers | compute expiry from server UTC, show localized relative duration not wall-clock | P1 | W3C time-zone data pitfalls [ext](https://www.w3.org/International/wiki/WorkingWithTimeZones); Intl.RelativeTimeFormat [ext](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat) |
| Code displayed but no QR fallback | unusable in accessibility/low-vision contexts | manual report | always offer the typed code and URL as the primary path; QR is progressive enhancement | P2 | [inf] |

### 2.4 Local model service discovery and health

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| Local service not running | fetch throws; looks like "invalid URL" | network error vs HTTP status | probe GET /api/tags with a short timeout; show "start Ollama" instructions; do not treat as credential error | P0 | /api/tags on http://localhost:11434 [ext](https://docs.ollama.com/api/tags.md) |
| Browser blocked by CORS | TypeError indistinguishable from server down | DevTools only; opaque fetch failure | prefer a server-side probe through the local Python backend; if client-side, document OLLAMA_ORIGINS and test both localhost and 127.0.0.1 origins | P0 | Ollama allows cross-origin from 127.0.0.1 and 0.0.0.0 by default; others need OLLAMA_ORIGINS [ext](https://docs.ollama.com/faq.md) |
| Service up, no model pulled | empty model list | HTTP 200 with empty models array | show empty state + "pull a model" command, allow refresh | P1 | [ext](https://docs.ollama.com/api/tags.md) |
| Cold model load / slow first token | perceived hang, user re-clicks | no response within 1s/10s bands | immediate feedback, progress/eta, disable resubmit; keep the request abortable | P1 | NN/g 0.1/1/10 s feedback limits [ext](https://www.nngroup.com/articles/response-times-3-important-limits/) |
| Version/API drift | response shape changes | schema check | validate expected fields, fall back to generic "could not read model list" error | P2 | published OpenAPI for /api/tags [ext](https://docs.ollama.com/api/tags.md) |

### 2.5 First request, provider timeout/retry, duplicate submission

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| User double-clicks "send" or "create bot" | duplicate bot/first message; extra spend | two server rows/requests | disable button + aria-disabled while pending; server-side idempotency key and dedupe | P0 | idempotency key pattern returns stored response on retry [ext](https://docs.stripe.com/api/idempotent_requests); show progress before ignore-second-click [ext](https://design-system.service.gov.uk/components/button/) |
| Retry after timeout duplicates the operation | repeated bot/first request | same as above | retry with the same idempotency key, never a fresh one | P0 | [ext](https://docs.stripe.com/api/idempotent_requests) |
| Provider times out/stalls mid-generation | partial output then silence | stream abort/timeout error | abort via AbortSignal.timeout; show partial + retry; cap retries | P0 | [ext](https://openrouter.ai/docs/api-reference/errors.md); [ext](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static) |
| 429 loop | repeated retries burn time | 429 + Retry-After | sleep Retry-After, exponential backoff with cap, tell the user what is happening | P1 | [ext](https://openrouter.ai/docs/api-reference/errors.md), [ext](https://www.rfc-editor.org/rfc/rfc6585.txt) |
| User loses network / local server stops | page or fetch fails halfway | fetch error, SSE close | distinguish "local server unreachable" from "provider unreachable"; keep completed steps; retry probe | P1 | [inf] local-first architecture (program brief) |
| Terms checkbox not persisted/versioned | re-prompt loops or unacknowledged terms | step not durable | store acknowledgement with version and timestamp; show what was accepted | P1 | check-answers pattern: review before submit [ext](https://design-system.service.gov.uk/patterns/check-answers/) |

### 2.6 Channel connection callbacks (Telegram-style)

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| Invalid/revoked bot token | channel never connects | getMe-equivalent call returns 401 | validate with a provider API call before "connected"; keep token in edit mode on failure | P0 | [ext](https://core.telegram.org/bots/api) |
| Inbound webhook cannot reach a local-first install | connection never confirms | no callback arrives | outbound polling/offset design instead of webhook; or documented tunnel. Webhook retry/duplicate semantics only matter if a public URL exists | P1 | webhook deliveries retried up to 3 days and can duplicate [ext](https://docs.stripe.com/webhooks); Telegram polling requires offset recalculation to avoid duplicates [ext](https://core.telegram.org/bots/api) [open] |
| Unsigned/forged webhook | spoofed updates accepted | signature/secret check | verify provider signature or configured secret token on every request | P1 | secret_token header option for setWebhook [ext](https://core.telegram.org/bots/api) |
| Secret tokens in logs | credential leak | code review | redact tool args/URLs; store encrypted or in local state only | P0 | [ext](https://core.telegram.org/bots) |

### 2.7 Cross-cutting setup states

| Edge case | Failure mode | How detected | Realistic fix | Pri | Source |
|---|---|---|---|---|---|
| Stale resume after refresh/provider return/device change | wrong step shown, duplicate secret prompt | step id/version mismatch | server-side draft per install with step + timestamps; on resume revalidate provider state instead of trusting UI; treat reconnect like first-time setup | P0 | NN/g smart-device guidance: treat reconnection like first-time setup [ext](https://www.nngroup.com/articles/smart-device-onboarding/) |
| Locale/timezone mismatch in expiry/timestamp copy | user waits for a time that already passed | inconsistent copy/timers | relative localized durations ("expires in 5 minutes"), UTC on the wire, explicit timezone if absolute time shown | P1 | [ext](https://www.w3.org/International/wiki/WorkingWithTimeZones), [ext](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat) |
| Mobile virtual keyboard covers the primary action | cannot continue on a phone browser | manual device test | scroll focused field into view, keep primary action reachable above keyboard, do not rely on fixed footers | P1 | visual vs layout viewport split [ext](https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API); VirtualKeyboard API geometry/overlaysContent [ext](https://w3c.github.io/editing/docs/virtualkeyboard/index.html) |
| Offline/air-gapped first run | provider checks all fail with network errors | network probe | onboarding must offer a working local-only route; do not block completion on internet | P1 | local-first premise (program brief) [open] |

## 3. Open questions for code inspection

1. Is provider validation done client-side or via the Python backend? This decides whether the
   Ollama CORS and provider-key CORS risks apply at all.
2. Does the dashboard already persist any setup draft, or is first-run state purely in the browser?
3. Is the pairing surface manual-code only, or does a host/relay provide the HTTPS origin passkeys need?
4. Do channel connections use inbound webhooks or outbound polling? Local-first installs usually
   cannot receive public webhooks, which makes the webhook-retry class mostly irrelevant at setup.
5. Is there an existing idempotency/dedupe layer for POST handlers, or must onboarding add one?
6. Which providers are actually in the first-run route list, and do any expose OAuth (OpenRouter)
   versus API key only?

## Sources

All opened 2026-10-29. Type: P = primary (standard/vendor/official docs), S = secondary
(credible UX research/agency), A = anecdote (project issue/PR used only as a bug-class signal).

| URL | Title | Type | Supports |
|---|---|---|---|
| https://datatracker.ietf.org/doc/html/rfc8252 | RFC 8252 OAuth 2.0 for Native Apps | P | external browser, loopback redirect, any port, state/CSRF |
| https://datatracker.ietf.org/doc/html/rfc8628 | RFC 8628 OAuth 2.0 Device Authorization Grant | P | manual code, expiry, polling errors |
| https://www.rfc-editor.org/rfc/rfc6585.txt | RFC 6585 Additional HTTP Status Codes (429) | P | rate limit + Retry-After |
| https://openrouter.ai/docs/guides/overview/auth/oauth.md | OpenRouter OAuth PKCE | P | localhost callback, 10 min single-use code, user pays |
| https://openrouter.ai/docs/api-reference/errors.md | OpenRouter error codes | P | 401/402/408/429/502/503, Retry-After |
| https://openrouter.ai/docs/guides/overview/auth/management-api-keys.md | OpenRouter management keys | P | keys shown once, expiry, rotation |
| https://docs.ollama.com/api/tags.md | Ollama list models (/api/tags) | P | local service discovery, model list |
| https://docs.ollama.com/faq.md | Ollama FAQ | P | OLLAMA_ORIGINS/CORS defaults |
| https://core.telegram.org/bots/api | Telegram Bot API | P | token format, getMe, setWebhook secret_token, offset |
| https://core.telegram.org/bots | Telegram bots intro | P | token grants full control, store securely |
| https://core.telegram.org/api/qr-login | Telegram login via QR code | P | token expiry/refresh/already-accepted semantics |
| https://core.telegram.org/bots/faq | Telegram bots FAQ | P | webhook/secret-path guidance |
| https://docs.stripe.com/api/idempotent_requests | Stripe idempotent requests | P | retry safely, stored response, key reuse |
| https://docs.stripe.com/webhooks | Stripe webhooks | P | retry with backoff up to 3 days, duplicate events |
| https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html | OWASP File Upload Cheat Sheet | P | why upload hardening is N/A until an upload exists |
| https://developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap | MDN createImageBitmap | P | EXIF orientation is a browser concern, chat-image only |
| https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API | MDN Web Authentication API | P | passkeys: secure context, origin binding |
| https://www.w3.org/International/questions/qa-personal-names | W3C Personal names around the world | P | non-Latin names, no transliteration, field size |
| https://www.w3.org/International/wiki/WorkingWithTimeZones | W3C Working with time zones | P | UTC/local pitfalls for expiry copy |
| https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat | MDN Intl.RelativeTimeFormat | P | localized relative durations |
| https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static | MDN AbortSignal.timeout() | P | client-side request timeout |
| https://w3c.github.io/editing/docs/virtualkeyboard/index.html | W3C VirtualKeyboard API | P | keyboard geometry/overlaysContent |
| https://developer.mozilla.org/en-US/docs/Web/API/Visual_Viewport_API | MDN Visual Viewport API | P | keyboard shrink vs layout viewport |
| https://design-system.service.gov.uk/components/password-input/ | GOV.UK password input | P | allow paste, spellcheck/autocapitalize, show/hide |
| https://design-system.service.gov.uk/components/button/ | GOV.UK button | P | prevent double click, progress before ignoring clicks |
| https://design-system.service.gov.uk/patterns/check-answers/ | GOV.UK check answers | P | review-before-submit |
| https://www.nngroup.com/articles/smart-device-onboarding/ | NN/g smart-device onboarding | S | pairing wizard, honest progress, reconnect = first setup |
| https://www.nngroup.com/articles/response-times-3-important-limits/ | NN/g response time limits | S | 0.1/1/10 s feedback thresholds |
| https://github.com/simstudioai/sim/pull/4973 | Sim: stop autofill on API token field | A | autofill corrupts token fields (bug class) |
| https://github.com/langflow-ai/langflow/pull/13748 | Langflow: autofill corrupting config fields | A | autosave amplifies autofill corruption |
| https://www.home-assistant.io/getting-started/onboarding/ | Home Assistant onboarding | P | self-hosted onboarding happens in the existing web UI |
| https://docs.nextcloud.com/server/latest/admin_manual/installation/installation_wizard.html | Nextcloud installation wizard | P | 3-step browser wizard, no hosted KYC |
