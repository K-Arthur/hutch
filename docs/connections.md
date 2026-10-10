# Connections: subscription plans and custom endpoints

## Google Calendar lookup and event creation (experimental, local setup required)

Hutch implements read-only Google Calendar lookup for the built-in runtime. Owners may separately
opt into creating guest-free events after reviewing each exact action in chat. In Connections, enter
the public client ID for an OAuth client of type **Desktop app**, then enable the Calendar API in
the Google Cloud project. The ID is shared with the separate Gmail preview; do not enter a client
secret or token. Hutch stores this non-secret setting in its local SQLite configuration. Operators
can instead set `HUTCH_GOOGLE_OAUTH_CLIENT_ID` before starting Hutch; that value takes precedence
and the Connections field becomes read-only. A real Google account was not used in local
verification; Google consent-screen verification and public eligibility are not claimed. See IG-5
in [requirements](requirements.md#connections-and-integrations-added-at-the-product-owners-request-2026-10-07).

Sign in from the Hutch host at
`http://127.0.0.1:<port>` on the Connections page; Hutch opens Google in a separate browser tab.
Finish consent in that tab, then return to the original Hutch tab and reload Connections. The
installed-app flow uses authorization code with PKCE and the read-only
`calendar.calendarlist.readonly` and `calendar.events.readonly` scopes by default. Event creation is
a separate account sign-in because Google's installed-app flow does not support incremental
authorization. That separate sign-in also requests `calendar.events.owned`.
Hutch stores the refresh token in the Linux Secret Service through `secret-tool`; access tokens are
held in process memory. SQLite stores the named account reference and each Bot's selected calendar
grant, never provider tokens. The browser does not receive tokens. Callbacks are local loopback only,
one-use, expire after ten minutes, and have their authorization query removed before request logs.

Google grants access at the account level. Hutch's typed Bot tool further restricts each Bot to the
one calendar the owner selected in Connections; this Hutch boundary is not a provider-enforced
per-calendar OAuth grant. The default read-only grant returns bounded title, start, end and location
fields. Event creation requires a separate sign-in choice and a separate per-Bot grant, and is only
offered for calendars Google identifies as owned by the account. Google's `calendar.events.owned`
scope also permits Google-side changes and deletion on all calendars the account owns; Hutch only
implements guest-free event creation on the selected calendar. Hutch shows the exact title, time,
description, location, account and calendar in a fresh outward approval—even when that Bot uses auto
approval—and checks the grant again after the decision. It sends no guest list or invitations and
offers no edit or delete action. Required event times include an explicit UTC offset and the approval
displays those exact values. After insertion, Hutch reads the returned event ID back and checks the
title, time instants, description and location before reporting success; a silently omitted field or
shifted time remains unverified. If the write or verification result is uncertain, Hutch does not retry
automatically; the owner must inspect the selected calendar first. Event details sent to the model are
retained in run history. Read results contain only titles, times and locations;
descriptions and attendee details are not passed to the model. Calendar text is untrusted data and
cannot authorize actions. Strict Offline mode exposes neither online Calendar tool.

Live Google consent, public OAuth verification and provider requests remain unverified. The event
creation path is an experimental owner-configured preview, not a public support claim. See Google's
[Calendar scope table](https://developers.google.com/workspace/calendar/api/auth),
[installed-app OAuth limits](https://developers.google.com/identity/protocols/oauth2/native-app),
[event insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), and
[event readback](https://developers.google.com/workspace/calendar/api/v3/reference/events/get).

Disconnect first removes Hutch's Bot grants and local refresh credential, then requests Google
revocation. If Google does not confirm revocation, Hutch reports that explicitly and directs the
owner to review connected apps in their Google Account. Never import consumer-app browser cookies,
CLI auth files, or another product's private sign-in state.

## Gmail message search (experimental private preview; local setup required)

Hutch has an owner-configured, read-only Gmail search path for private preview. This does not make
Gmail available in a public release: `gmail.readonly` is a restricted, account-wide OAuth scope.
In Google Cloud, enable the Gmail API and add the owner's account as a test user while the OAuth
consent screen is in Testing. Enter the public Desktop OAuth client ID in the shared Google setup
section in Connections, or let the operator set `HUTCH_GOOGLE_OAUTH_CLIENT_ID` before startup.
Run Hutch in a Linux desktop session with an unlocked Secret Service. Start sign-in from the Hutch
host at `http://127.0.0.1:<port>` on Connections. The local installed-app flow uses authorization
code with PKCE; Linux Secret Service stores refresh tokens,
access tokens stay in process memory, and SQLite/browser storage never receive the tokens. The
callback is one-use, expires after ten minutes, and has authorization query fields removed before
access logging.

Google's grant authorizes access across the signed-in account, even though Hutch can grant one
connected account to one Bot. Hutch's tool only searches up to ten matches and returns sender,
subject, received date, and a 1,200-character-capped provider snippet. The `gmail.readonly` scope is
broader than those returned fields; Hutch does not fetch message bodies, attachments, labels, or
settings, and it cannot send, edit, forward, or delete messages. Search terms and returned previews
are stored with the local run history as untrusted data.

Only a Bot using Hutch's built-in runtime and Local inference can receive a grant. Every configured
primary, fallback, and escalation route must be a loopback model endpoint; hosted fallback and
remote custom endpoints are rejected. This prevents Hutch from intentionally sending Gmail previews
to hosted model routes. The operator-selected service listening on loopback remains outside Hutch's
verification boundary, so operators must trust that local model service. Hybrid, hosted, and Strict
Offline Bots do not receive this Gmail tool.

Google permits development/testing use under specific exceptions, but an OAuth project in Testing
is limited to 100 listed test users and authorizations/refresh tokens expire after seven days. This
is a Google project restriction, not a Hutch setting. Public distribution requires the applicable
restricted-scope verification. Google also requires an annual third-party security assessment for
apps that can access restricted user data from or through a third-party server. Hutch has not
completed Google verification or a security assessment and must not be described as publicly
approved for Gmail. [Google's Gmail scope table](https://developers.google.com/workspace/gmail/api/auth/scopes),
[restricted-scope verification rules](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification),
and [Testing-user limits](https://support.google.com/cloud/answer/15549945?hl=en) are the current
source for those constraints.

Disconnect clears Hutch's local token and Bot grants, then requests token revocation. If Google does
not confirm revocation, Connections says so and points the owner to Google's connected-app settings.
Calendar consent is separate. Gmail sending and all mailbox changes remain unavailable. Outlook
Calendar and Outlook Mail use separate permissions and accounts; see the Outlook sections below.
See the current provider
references: [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[Google installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference), and
[Microsoft authorization-code/PKCE guidance](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

## Outlook Calendar event lookup (experimental, local setup required)

The Connections page can connect a Microsoft work, school, or personal account through the local
public-client authorization-code flow when the app registration supports that account type. This is
an experimental read-only capability, separate from the Outlook Mail connection below. It remains unavailable until the operator configures `HUTCH_OUTLOOK_OAUTH_CLIENT_ID`
for a Microsoft Entra public-client application and runs Hutch on Linux with an unlocked Secret
Service. No Microsoft account, tenant, consent screen, or live Graph request was used in verification.

Under **Mobile and desktop applications**, register
`http://localhost/api/v1/connections/outlook-calendar/callback` as the redirect. Microsoft ignores the
port for localhost redirects, and Hutch binds its actual listener port into the callback. Choose the
registration's supported account types deliberately: select organizational accounts only, personal
accounts only, or both as appropriate; `/common` does not override that registration choice. It uses
the `common` authority, authorization code with S256 PKCE, and delegated `Calendars.ReadBasic`
plus `offline_access`; it requests no mail scope, write scope, or tenant-wide app-only permission.
Linux Secret Service stores only the refresh token. Short-lived access tokens stay in process memory;
SQLite records the account label and each Bot's selected-calendar grant. The browser receives neither
token. Callback state is one-use, expires after ten minutes, and is stripped from access logs.

Microsoft consent is account-wide. Hutch adds a local boundary by granting a Bot only one calendar
chosen from that account's verified calendar list. The Bot tool reads at most 25 events in a requested
range no longer than 366 days, and asks Graph only for subject, start, end, and location. These fields
are sent to the Bot's selected model and retained in its run history. Event text is untrusted input;
the tool cannot create, change, invite, or delete events. Strict Offline mode removes this online tool.

Disconnect clears Hutch's refresh token and all Hutch Bot grants. Microsoft Graph does not offer a
revocation endpoint suitable for this local public-client flow, so the UI directs the account owner to
revoke consent separately in their Microsoft account or organisation settings. This does not claim
that provider-side consent was revoked. See [Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference),
[List calendars](https://learn.microsoft.com/en-us/graph/api/user-list-calendars?view=graph-rest-1.0),
[List calendarView](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0),
[authorization code with PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow),
and [redirect URI guidance](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url).

## Outlook Mail search (experimental, local setup required)

Outlook Mail uses its own Microsoft public-client registration, callback, token namespace, and
per-Bot grant. It does not reuse an Outlook Calendar token or calendar consent. Configure
`HUTCH_OUTLOOK_OAUTH_CLIENT_ID` and Linux Secret Service as above, then register
`http://localhost/api/v1/connections/outlook-mail/callback` under **Mobile and desktop applications**.
The Mail flow requests delegated `Mail.Read` and `offline_access`; this broader read scope is needed
for the short body preview, because Hutch does not use only the less-privileged header-only
`Mail.ReadBasic` scope. No application permission, send permission, or mailbox-write scope is
requested. No real Microsoft account, consent screen, or Graph request has been verified.

The Connections page grants one connected mailbox to each Bot. Search uses the fixed Graph v1.0
`/me/messages` endpoint, which includes Deleted Items and Clutter, and returns no more than ten
matches with sender, subject, received time, and
a 1,200-character-capped preview. The read grant does not provide send, edit, delete,
forward, or mailbox-settings operations. Message content is untrusted, is sent to the Bot's selected
model, and is retained in its run history. Strict Offline mode does not expose the search tool.
Microsoft consent is account-wide: removing the Hutch grant or disconnecting removes Hutch's local
access, but provider consent must be revoked separately by the owner. Live account and provider
verification remain release gaps. See [List messages](https://learn.microsoft.com/graph/api/user-list-messages),
[`$search` for message collections](https://learn.microsoft.com/en-us/graph/search-query-parameter),
and [Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference).

### Outlook Mail sending (experimental Connections setup)

Sending uses a separate Outlook sign-in and credential namespace from `Mail.Read`. Set the same
`HUTCH_OUTLOOK_OAUTH_CLIENT_ID`, register
`http://localhost/api/v1/connections/outlook-mail-send/callback`, and explicitly sign in for
delegated `Mail.Send` plus `offline_access`. Hutch will not upgrade a read-only sign-in or infer
send permission from a broad account grant. Refresh credentials are stored in Linux Secret Service;
SQLite stores only the account label and each Bot's explicit grant. The optional setup is inside
**Apps & AI → More account settings → Outlook Mail → Set up optional email sending**. It has its own
sign-in, account record and Bot grant; it does not upgrade or reuse the Mail.Read connection. It has
not been exercised with a real Microsoft account.

The owner grants one sending account to one Bot from that section or with the versioned
`/api/v1/connections/outlook-mail-send` API. The screen states the approval and retry limits before
the grant is saved. Each action is one new plain-text message to at most
five addresses. Before sending, Hutch asks for a fresh decision on the exact account, recipients,
subject and body—even when the Bot uses automatic approval. Replies, forwards, attachments, CC and
BCC are not available. The request goes only to the fixed Microsoft Graph v1.0 `/me/sendMail`
endpoint, with redirects disabled. Hutch sends once: a timeout, server error, or unexpected response
is `outcome_unknown`, not a retry instruction. A Graph `202 Accepted` response means Microsoft
accepted the request; it does not prove delivery. Check Outlook Sent Items before considering any
retry. The action receipt remains available for reconciliation. Strict Offline mode does not expose
this tool.

The added delegated `Mail.Send` scope is account-wide. Removing the Hutch grant or disconnecting
removes local access, but the owner must revoke provider consent in Microsoft account or organisation
settings. No live OAuth consent, email send, delivery, or tenant-policy behavior has been verified.
This capability is experimental and must not be represented as generally supported or delivery
verified. Microsoft's [sendMail API](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0)
documents the `202 Accepted` response; its [send processing overview](https://learn.microsoft.com/en-us/graph/outlook-things-to-know-about-send-mail)
explains that Graph's direct interaction ends before the downstream delivery steps complete.

A **connection** is a named hosted endpoint with its own provider-scoped credentials, protocol, headers, billing mode,
usage allowance and terms notice. API-key routes use `<connection>/<model>`; the experimental ChatGPT plan route is
created only after its separate authorization succeeds:

```bash
hutch connections templates                          # what Hutch knows how to talk to
hutch connections add opencode-go --allowance-tokens 2000000 --allowance-window month
hutch connections set-account-cap opencode-go 25 --account-id team-provider
hutch connections set-key opencode-go                # hidden prompt; stored 0600, never printed
hutch connections ack opencode-go                    # read the plan's terms notice, then accept it
hutch connections test opencode-go                   # authenticates; spends no tokens
hutch usage reservations                             # inspect held or uncertain usage
hutch bot update my-bot --model opencode-go/zhipuai/glm-5.3
```

For OpenCode Go, sign in and manage the plan on OpenCode, then copy its provider API key into Hutch. This is the
provider's documented third-party connection method, not an OAuth session shared with Hutch. Hutch does not reuse
OpenCode's private `auth.json`, browser profile or CLI sign-in. For the eligibility-gated ChatGPT preview, the
Connections page starts OpenAI's official local sign-in flow; do not enable it unless Hutch is eligible for the flow:

```bash
HUTCH_ENABLE_CHATGPT_PLAN=1 hutch serve --host 127.0.0.1
```

This local opt-in switch is not proof of eligibility. ChatGPT plan access is not available through the generic API-key
form or CLI `set-key` command. It uses the Responses API only and does not expose ChatGPT conversations.

The same flow is on the dashboard's **Connections** page. Model ids may contain `/`
(`opencode-go/zhipuai/glm-5.3`): the connection name is everything before the first slash.

## Why this exists

Before connections, a hosted endpoint other than OpenAI or Anthropic meant `openai-compatible/<model>` plus
`HUTCH_BASE_URL`, with **one** global `OPENAI_API_KEY` for every such URL, no notion of a flat-rate plan, no
per-model protocol, no required headers and no warning about a vendor's terms. That is not usable for the
subscription plans people actually own. The loudest complaint about the products Hutch is measured against
(Grok Bot, OpenAI Dots) is an allowance that vanishes with no warning and no cap, so a connection can declare
its allowance and Hutch enforces it *before* the vendor does.

## Plans with templates

Everything below was read from the vendor's docs or a docs aggregator on **2026-10-07**. **None of it was
exercised against a live account** (there are no keys on the development machine); the fakes in
`tests/fakes.py` reproduce the documented wire formats.

| Template | Endpoint | Key | Billing | Source |
|---|---|---|---|---|
| `opencode-go` | `https://opencode.ai/zen/go/v1` (OpenAI chat) | `OPENCODE_API_KEY` or a key pasted into Hutch, after the user signs into Go and copies its provider key | flat subscription, dollar-denominated caps: 5-hour 20%, weekly 50%, monthly 100% | [OpenCode Go docs](https://opencode.ai/docs/go/) |
| `chatgpt-plan` | `https://api.openai.com/v1` (Responses only) | Official Sign in with ChatGPT local token-sharing flow; never an API key | subscription account; OpenAI controls actual allowance | [SIWC preview](https://developers.openai.com/siwc/token-sharing-open-source/) |
| `xiaomi-token-plan-{sgp,cn,ams}` | `https://token-plan-<region>.xiaomimimo.com/v1` (OpenAI chat) and `/anthropic` (Anthropic messages) | `XIAOMI_TOKEN_PLAN_API_KEY` (`tp-...`) | subscription **Credits**, not tokens | [OpenClaw provider docs](https://docs.openclaw.ai/providers/xiaomi), [MiMo docs](https://mimo.mi.com/docs/en-US/tokenplan/subscription) |
| `xiaomi` | `https://api.xiaomimimo.com/v1` | `XIAOMI_API_KEY` (`sk-...`) | per token (needs a price row) | same |
| `custom-openai` | any `/v1/chat/completions` server: OpenRouter, Together, Groq, a company gateway, vLLM | your env var | per token or subscription | - |
| `custom-anthropic` | any `/v1/messages` server (URL **without** `/v1/messages`) | your env var | per token or subscription | - |

OpenAI, Anthropic, Ollama, LM Studio and llama.cpp keep their built-in provider names and need no connection.

## What a connection controls

- **Key** (`CN-2`). Read from the environment variable first, then from `<state dir>/keys/<name>.key` (created
  `0600` in a `0700` directory). The key is never written to the database, `connections.json`, a transcript,
  a page or the API; tests grep every page and the database for a planted secret. The file option exists
  because a user-level systemd service does not inherit your shell's environment.
- **Headers** (`CN-3`). Hutch sends its own `User-Agent` (`hutch/<version>`) and, where a plan requires it, a
  stable per-conversation session id (`x-opencode-session: <conversation id>` for OpenCode Go). Standalone
  scheduled runs without a conversation use their run id.
- **Protocol per model** (`CN-7`). Some plans split models across wire formats. Hutch speaks `openai-chat` and
  `anthropic`; set a model's protocol with `hutch connections set-protocol <name> <model> anthropic`. The OpenAI
  *Responses* protocol is reserved for the fixed ChatGPT plan route; arbitrary connections cannot select it. A template
  or override that asks for it is rejected with a clear message rather than failing at run time. The OpenCode docs list Claude Haiku, MiniMax and Qwen families on
  the Anthropic endpoint and Grok / Muse Spark on Responses, while models.dev lists every model as
  OpenAI-compatible; the two sources conflict, so Hutch ships no per-model overrides and tells you how to set one.
- **Billing** (`CN-4`). `per_token` is priced from `prices.json`; with no price row a hosted model **cannot run
  while a Hutch currency limit is set** (Hutch refuses rather than guess). `subscription` and `free` cost nothing per call, but every
  call still lands in the usage ledger.
- **Allowance** (`CN-5`). Declare tokens per rolling window (`5h`, `day`, `week`, `month`). Hutch refuses a call
  that *could* pass it (used + prompt + the reply reserve), warns once at 80%, and shows the meter on the
  Connections page. Requests reserve estimated prompt + reply tokens before they start, and the SQLite transaction
  checks actual usage plus outstanding reservations across Hutch processes. The window is a rolling approximation:
  vendors may use fixed windows. Credits (Xiaomi) and dollars (OpenCode Go) are not tokens; the allowance is a proxy
  you calibrate against the vendor's console.
- **Shared account and currency limits** (`ADR-0011`). Connections default to separate account IDs. Give connections
  the same `--account-id` to share an account quota and currency admission limit. Example: `hutch connections set-account-cap
  opencode-go 25 --account-id team-provider` sets the strictest declared daily cap for that group. Price-based currency
  reservations use Hutch's prompt-size estimate and requested output-token limit; they are not an exact provider billing
  guarantee. If a currency cap is set, a model without a known price is refused.
- **Uncertain requests.** If Hutch cannot verify whether a provider accepted a request, its reservation stays held,
  including across restarts. Check the provider's usage record after the run is terminal, then reconcile either exact
  usage or a verified no-charge outcome:

  ```bash
  hutch usage reservations
  hutch usage reconcile rsv_... --not-charged --reason "provider usage page confirms no charge"
  # or: hutch usage reconcile rsv_... --prompt-tokens 900 --completion-tokens 120 \
  #   --actual-cost-usd 0.0042 --reason "provider usage page checked"
  ```

  Reconciliation inserts usage once or releases a verified no-charge hold. Active runs cannot be reconciled. Never
  release a reservation based only on a client timeout.
- **Terms** (`CN-6`). Each template carries a notice. A bot cannot use the connection until it is acknowledged,
  and a changed notice requires acknowledging again. A run that hits an unacknowledged connection fails fast
  and tells you the command, or falls back to the next model if the bot has one.
- **Test** (`CN-8`). `hutch connections test` authenticates against the model list (one `GET`, no model request).
  Anthropic-protocol endpoints have no standard list, so the test says "not verified" rather than pretending.
  A standalone `--chat <model>` probe is refused because it bypasses shared usage reservations and uncertain-charge
  reconciliation. Run a normal bot request to test model behavior through Hutch's budget and approval controls.

## Terms: read this before scheduling bots on a plan

- **OpenCode Go** asks third-party clients to send "typical coding agent traffic", to identify themselves with
  their own User-Agent and a stable session id, and says traffic is monitored for abuse. Hutch does the
  identification. Whether *unattended, scheduled* runs count as typical coding-agent traffic is OpenCode's
  decision. Check before you schedule.
- **Xiaomi Token Plan** documents support for coding tools (OpenCode, Claude Code, OpenClaw...) and says keys
  must not be shared. Its page is not machine-readable, so Hutch could not read the full terms. Confirm that
  automated use is allowed on your tier.
- In general, provider terms do not necessarily allow routing a per-seat subscription key through a third-party
  tool, and some plans apply risk controls to unusual traffic.

## Sign in with ChatGPT preview

This separate local-app flow uses PKCE, one-use state and nonce, OpenAI dynamic client registration, a stable Hutch
host ID, a loopback-only callback, and signature/issuer/audience/expiry verification. ChatGPT bearer credentials are
stored in the Hutch state directory with owner-only permissions and are returned by neither the API nor the page.
Hutch refreshes them for the official OpenAI API host only. Returning sign-in reuses the selected registration and stable
host identifier; Hutch sends a retained ID token only as the official `id_token_hint`, and sends `login_hint` only for a
verified email. Unverified email claims are neither displayed nor used as a sign-in hint. Authorization URLs containing
an ID-token hint must not be logged. Disconnect clears local tokens and requests revocation. No browser cookie, ChatGPT
conversation, or credential from another app is used.

The operator must set `HUTCH_ENABLE_CHATGPT_PLAN=1` and bind Hutch to local `127.0.0.1`. OpenAI's preview eligibility
is not confirmed for Hutch, so the route is experimental and disabled by default. Read the current
[eligibility and preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) first.
The Responses route always streams and sends `store:false`; it sends Hutch's local function definitions using the
preview-supported `additional_tools` input item, and omits unsupported preview fields, including `max_output_tokens`.
OpenAI therefore does not enforce Hutch's per-response output ceiling. Hutch usage reservations
and any operator allowance are estimates, can be exceeded by one response, and are not a hard spend cap. No live
ChatGPT account was used to verify this integration.

OpenAI's current terms require express consent before a plan is used by an automation or background process. Hutch
therefore requires a separate permission for each Bot and connected ChatGPT account before scheduled or coordinator-assigned
work can use that route. The permission is stored locally with that Bot, bound to its current model/fallback/escalation
configuration, and invalidated when that configuration changes. Hutch checks the current grant before each provider request;
revoking it blocks the next request after any in-flight request finishes. Disconnecting the account removes its grants.
User-started conversations keep their existing request-level authorization flow. Bot API responses and recovery snapshots
omit local account identifiers and raw consent records. [OpenAI's SIWC terms](https://openai.com/policies/sign-in-with-chatgpt-terms/)
require user-controlled runtimes and expressly authorized background use; [preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
still apply.

If the sign-in control is disabled, leave it disabled unless Hutch has confirmed eligibility; setting the local flag is
not an eligibility grant. If the callback expires or Hutch was opened through a hostname, HTTPS proxy, or remote device,
restart the flow from `http://127.0.0.1:<port>` on the Hutch host. If sign-in completes without the ChatGPT plan-use
scope, the account cannot select ChatGPT models until it is reauthorized with that scope. Once connected, user-started
messages use the existing request-level authorization flow; scheduled and specialist work still needs the separate
per-Bot permission above. When Hutch is not eligible or
you need a provider-enforced output limit, use an OpenAI API connection with an API key; ChatGPT Plus/Pro membership
does not itself create API billing credentials.

## Deliberately unsupported

**Reusing a consumer app's login session** (Claude Pro/Max, ChatGPT Plus/Pro, Copilot...). Anthropic's
documentation says OAuth tokens from consumer plans are for use inside its own applications and that using them
in other products or tools is not permitted; its consumer terms prohibit automated access except through an API
key. Hutch never reads or proxies browser cookies, CLI auth files or copied session tokens (`LM-15`). This is separate
from the official, eligibility-gated ChatGPT local-app preview above. Plans that issue an **API key**
(OpenCode Go, MiMo Token Plan, and the API products themselves) are supported through Hutch's built-in provider clients. Vendor
CLI harnesses (`pi`, `opencode`) are currently disabled; Hutch does not launch them or use their independent authentication.

## Limits worth knowing

- **Compatibility is route-level.** `GET /api/v1/compatibility` lists the HTTP shape, fields Hutch sends or omits,
  implementation state, dated sources, and the fixture/live verification boundary. A `supported` route means Hutch has
  tested its common wire contract; it does not guarantee that every endpoint or selected model supports tools, context
  limits, usage details, or retention behavior. `hutch connections test` checks a model list without spending tokens;
  per-model tool capability probing and persisted verification records are not implemented yet.
- Provider field-validation errors stop without replaying the same invalid body. Hutch retries without streaming only
  when a rejection identifies a stream/SSE incompatibility. If auth or quota failure leads to a different hosted
  account or destination, Hutch pauses for outward approval before constructing that provider; unresolved usage stays
  reserved until reconciliation.
- Not tested against live accounts. If a plan's real behaviour differs from its docs, use a normal bot run with that
  connection so the request goes through Hutch's shared usage reservations, approval path and durable receipt handling.
- Model discovery is the vendor's `GET /models`; context windows are not read from it (the list does not carry
  them), so no window is assumed for hosted models.
- A connection is **hosted**. A fallback from a local or hosted primary to another account,
  destination, protocol or connection revision requires outward approval, even in auto mode.
  The review names the account and endpoint and grants only that route within the current run.
  Generic hosted sticky grants cannot bypass it. Selecting the primary model explicitly does
  not authorize a different service.
- Rotation/removal of a connection key is effective before the next builtin call; the in-flight
  request may already have reached the provider. Connection URLs cannot contain HTTP basic
  credentials. `HUTCH_LEGACY_KEY_ROUTING` no longer bypasses provider scoping.
- A broken stream keeps its uncertain usage reservation. A retry needs its own reservation;
  reconcile the first from a provider record after the run is terminal. Currency remains a
  price-based estimate, not a guaranteed provider bill.
