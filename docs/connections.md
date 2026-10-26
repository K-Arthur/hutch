# Connections: subscription plans and custom endpoints

## Google Calendar lookup and event creation (experimental, publisher registration required)

Hutch implements read-only Calendar lookup and separately approved, guest-free event creation.
The normal flow is **Apps & AI → Google Calendar → Connect Google → choose your account →
approve → select a calendar and assistant**. An account nickname is optional. The tile starts
read-only authorization even if an earlier advanced form requested event creation.

Hutch's publisher supplies its public Google Desktop OAuth registration with the application.
A checkout with no registration shows **Not enabled in this build**; that is unfinished publisher
setup, not a requirement for every user to create a Cloud project. Being signed into the browser
can reuse Google's account session, but cannot grant Hutch calendar access by itself.
The current development manifest has no registered IDs, so live sign-in remains blocked.
Google consent-screen verification and public eligibility have not been established.

Developers can open **Apps & AI → Google Calendar → Developer settings for Google** to save their own
public Desktop client ID locally. Never enter a client secret or token. Operator environment
`HUTCH_GOOGLE_OAUTH_CLIENT_ID` takes precedence, followed by the saved override, then the build's
public registration. Clearing an override returns to the build default. Calendar, Workspace and
the separate Gmail preview share this app identity, but retain separate consent and credentials.
See IG-5 in [requirements](requirements.md#connections-and-integrations-added-at-the-product-owners-request-2026-10-07).

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
Calendar consent is separate. Gmail mailbox search remains read-only. Outlook
Calendar and Outlook Mail use separate permissions and accounts; see the Outlook sections below.
See the current provider
references: [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[Google installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference), and
[Microsoft authorization-code/PKCE guidance](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

## Gmail send-only (experimental private preview; local setup required)

Gmail sending uses a separate local PKCE account and Secret Service entry with only
`https://www.googleapis.com/auth/gmail.send`. It cannot read, search, modify, or delete mailbox
messages. Enable the Gmail API and use the same owner-configured Google Desktop OAuth client ID as
the read-only search connection. In Connections, optionally name the account and enter the sender address you
intend to use. Google must permit that address for the account; Hutch does not request mailbox
settings access to discover or validate aliases. An OAuth project in Testing has Google's 100-user
limit and seven-day refresh-token expiration.

An owner can grant one send account to one assistant. The built-in tool prepares one plain-text
email to one through five addresses; it has no attachments, CC, BCC, replies, or forwards. Every
send shows the sender, account, full recipient list, subject, and body for a fresh owner decision,
including when the assistant is in automatic mode. Hutch submits one request. Google acceptance is
not proof of delivery. A timeout, server error, redirect, or malformed success receipt is held as
`outcome_unknown`; check Gmail Sent before deciding what to do, because Hutch will never retry it.

Google classifies `gmail.send` as a sensitive scope requiring additional OAuth app verification
for public distribution. It is separate from restricted `gmail.readonly`; the restricted-data
security-assessment rule applies to the read scope, not this send-only capability. Hutch has no
Google verification or live-account evidence, so send-only Gmail remains a private preview and
must not be described as generally available. Sending and search consent are disconnected and
revoked independently. See [Google's scope table](https://developers.google.com/workspace/gmail/api/auth/scopes),
[message send method](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send),
and [message-format guide](https://developers.google.com/workspace/gmail/api/guides/sending).

## Outlook Calendar event lookup (experimental, publisher registration required)

The Connections page can connect a Microsoft work, school, or personal account through the local
public-client authorization-code flow when the app registration supports that account type. This is
an experimental read-only capability, separate from the Outlook Mail connection below. It remains unavailable until the publisher supplies a Microsoft public-client registration (or an operator sets `HUTCH_OUTLOOK_OAUTH_CLIENT_ID`)
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

### Outlook Calendar event creation (separate experimental opt-in)

Event creation uses a second sign-in and credential namespace; it never upgrades or reuses the
read-only `Calendars.ReadBasic` account. Configure the same Microsoft public-client ID and register
`http://localhost/api/v1/connections/outlook-calendar-write/callback` under **Mobile and desktop
applications**. In Connections, open Outlook Calendar's optional event-creation section, sign in
again, and grant one Bot one calendar returned by Microsoft. The write credential is stored in a
separate Linux Secret Service entry; SQLite stores only the account label and selected-calendar
grant. Disconnect removes Hutch's token and grants, but the owner must revoke Microsoft consent in
their account or organisation settings.

Microsoft's delegated `Calendars.ReadWrite` scope is account-wide and permits creating, reading,
changing and deleting calendar events. Hutch discloses this before opt-in, then exposes only guest-free
event creation on the one calendar selected for that Bot. Each event requires a fresh exact approval,
including in automatic mode; the review shows title, time, description, location, account and calendar.
After one Graph create request, Hutch reads the event back and verifies those fields and the absence
of attendees before reporting success. A timeout, server error, redirect, missing receipt or mismatch
is `outcome_unknown`; check the calendar before trying again. Hutch does not automatically retry, and
does not expose event editing, deletion, invitations or Strict Offline access. No Microsoft account,
tenant policy, live consent screen, or live Graph write has been verified.

## Outlook Mail search (experimental, publisher registration required)

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
**Apps & AI → Microsoft Outlook → Set up optional email sending**. It has its own
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

OpenRouter has a first-party **OpenRouter** template at
`https://openrouter.ai/api/v1`. Add it from Connections or run
`hutch connections add openrouter`, then store the key from
[OpenRouter's key settings](https://openrouter.ai/settings/keys) with
`hutch connections set-key openrouter`. Hutch sends that key only to the
configured OpenRouter endpoint. When you open the model picker, Hutch loads the
40 most-popular text models; typing a search asks OpenRouter's model catalog
for matching results. The catalog request does not generate a response or
spend model tokens. OpenRouter's own model ids, names, reported prices and
context values can change. Hutch shows those values as catalog information,
not as a guarantee of upstream availability. Paid-call admission separately
reads public per-model endpoint metadata with a five-minute freshness window. The response is capped at 1 MB, 512
endpoints and 64 pricing overrides per endpoint; compressed responses are rejected. Under a strict USD ceiling, stale or missing metadata, an unknown price
dimension, or no endpoint that fits the request blocks admission; other paths
may use clearly labeled stale metadata or a reviewed Settings > Prices row.
Reservations cover the highest eligible endpoint estimate, including published
long-context tiers and possible cache-write prices. They are estimates, not an
external billing cap. Hutch requests OpenRouter's `usage.include=true` and
retains `usage.cost` when reported. An alias or preset without a defensible
strict quote is refused. Tool support varies by model and upstream provider,
so a catalog entry does not prove a model will work for every task. Public
model and endpoint metadata GETs were checked on 2026-10-11. A live account
check on 2026-10-23 verified authenticated key discovery, a text reply and one
tool round trip with `openai/gpt-4o-mini`; the temporary test key was capped at
$1 and the calls cost about $0.00009. OpenRouter **management/provisioning
keys** can list models and administer the account, but OpenRouter rejects them
on completion endpoints. Hutch now detects that key type during the connection
check and tells the person to create a normal inference key instead of
reporting a false success.

OpenRouter connections may carry an operator-configured `openrouter_policy` in
`connections.json` or `POST /api/connections`. Supported controls are `order`,
`allow_fallbacks`, `require_parameters`, `data_collection`, `zdr`, and `max_price`.
For example, `{"data_collection":"deny","require_parameters":true,"max_price":{"prompt":1,"completion":2}}`
restricts endpoint data handling and sets input/output price ceilings in USD per
million tokens. An optional `request` price ceiling is USD per request; zero is
a real ceiling for free-only routes. These filters do not replace Hutch's usage
reservations or guarantee the final bill. A renamed OpenRouter connection keeps
the same authenticated checks, catalog support, and provider-reported usage
settlement. An exhausted credit balance or explicitly exhausted quota is not
retried as a transient throttle; switching to a different paid route still uses
the normal authorization and budget checks.

## Connect a model provider in one step

On a device that has never installed OpenCode or Ollama, use a hosted API-key route first; Hutch does not bundle either runtime. OpenCode requires the **V2** CLI on `PATH`, and Ollama requires a running local server plus downloaded models. See [runtime prerequisites](runtime-setup.md). From **Apps & AI → AI model providers → Connect a provider**, choose OpenAI API,
Anthropic API, or OpenRouter, paste the key, and select **Connect and find
models**. Hutch makes one authenticated catalog request; it does not spend
inference tokens. The response reports whether the catalog was verified and how
many model IDs it returned. Use the model picker to choose one. The list is live
and may change; it does not prove tool support, model quality, price stability,
or successful inference. Advanced providers and custom endpoints stay behind
**More providers and endpoint settings**.

Custom provider endpoints must use HTTPS. Plain HTTP is accepted only for an
explicit loopback service (`localhost`, `127.0.0.1`, or `::1`); Hutch will not
send a connection key over cleartext to a remote host. Put credentials in the
connection's key field or private key file, never in the endpoint URL.

OpenAI API keys use OpenAI API billing and are separate from ChatGPT sign-in or
a ChatGPT subscription. Anthropic's account catalog is paginated. OpenRouter
catalog details and prices are provider-reported and can change; OpenRouter may
route to a different upstream model under its own fallback rules. Hutch records
the model returned by the provider and does not silently select a different
Hutch connection. Review each provider's billing and routing controls. Catalog
prices are not billing guarantees. For a strict USD ceiling, Hutch requires a
fresh endpoint-aware estimate and refuses when it cannot bound the route. The
reservation remains an estimate; provider-side controls are still needed for a
provider-enforced limit.

Pasted keys are written to a private file on this Hutch with owner-only
permissions; they are never returned to the browser or stored in browser
storage. A key pasted through this dialog takes precedence over that connection's
environment variable, so Hutch uses the key the owner just chose. **Remove key**
clears the local key and restores the environment variable if configured. A
provider catalog error does not discard the connection: the UI says it could
not verify the list, and the connection appears under **AI model providers** for
testing or key replacement. No provider account or inference request was used
for visual validation. See the [multi-provider UX review](research/multi-provider-platform-review-2026-10-10.md)
and [brand asset provenance](brand-assets.md).

For OpenCode Go, sign in and manage the plan in the OpenCode Console, then copy its provider API key into Hutch. This is the
provider's documented third-party connection method, not an OAuth session shared with Hutch. Hutch's Go connection does not
reuse OpenCode's private auth database, browser profile or CLI sign-in. Separately, the experimental interactive coding handoff
supports `hutch code login`, which starts OpenCode's documented provider picker in a dedicated profile under Hutch state; it
does not import the user's regular OpenCode profile. See [coding handoff operations](operations.md#reviewing-an-opencode-coding-task).
For the eligibility-gated ChatGPT preview, the
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
| `openrouter` | `https://openrouter.ai/api/v1` (Chat Completions) | `OPENROUTER_API_KEY` or a key pasted into Hutch | per token; add a reviewed price row before currency-limited use | [OpenRouter model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models), [chat completions](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request) |
| `opencode-go` | `https://opencode.ai/inference/go/openai/v1` (OpenAI chat); `https://opencode.ai/inference/go/anthropic` (Anthropic Messages) | `OPENCODE_API_KEY` or a key pasted into Hutch, after the user signs into the OpenCode Console and copies its provider key | flat subscription, dollar-denominated caps: 5-hour 20%, weekly 50%, monthly 100% | [OpenCode Go docs](https://opencode.ai/v2/docs/console/go) |
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
key. Hutch never reads or proxies browser cookies, another tool's CLI auth files or copied session tokens (`LM-15`). The
experimental local OpenCode coding handoff uses a new provider login saved by OpenCode in a profile managed under Hutch state;
it is separate from using an OpenCode CLI session as a Hutch Bot runtime. This is separate from the official, eligibility-gated
ChatGPT local-app preview above. Plans that issue an **API key**
(OpenCode Go, MiMo Token Plan, and the API products themselves) are supported through Hutch's built-in provider clients.
The OpenCode assistant runtime is available through a Hutch-owned private profile, with once/reject permission brokering
and shared usage reservations; approved OpenCode tools run with the user's OS authority rather than inside the built-in
shell sandbox. Pi remains disabled. The separate reviewed OpenCode coding handoff is an
owner-launched terminal workflow and is not a runtime adapter.

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

## Google Drive, Docs and Sheets (experimental)

Open **Apps & AI → Google Drive**, **Google Docs**, or **Google Sheets** for that
service's capabilities, account controls and permissions. They are separate product
connections using one shared file-account transport. New sign-ins request only
`drive.file`: files created by Hutch or explicitly opened/shared with the app. Google's
[Docs API](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/create)
and [Sheets API](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/create)
both accept that narrow scope. A native Picker and full-Drive search are not implemented.

New file-service sign-ins identify the selected Google account using the Drive API's
[`about.get`](https://developers.google.com/workspace/drive/api/reference/rest/v3/about/get)
with only `user(emailAddress)` fields. This accepts the existing `drive.file` scope; no
OpenID/profile scope or browser credential import is added. Hutch stores that returned
email as local account metadata and displays it beside an optional nickname. A missing
or malformed identity prevents installing the new connection. Legacy combined accounts
are not silently queried or relabeled.

An existing file connection can be explicitly enabled for another service without
another Google sign-in or broader provider consent. Enable/disable operations use a
versioned contract and account revision check; disabling Docs leaves Drive and Sheets
unchanged. Assistants still need their existing tools and exact action-plan approval.
Disconnecting the shared Google account removes local file-service access for all three
and attempts Google revocation. Google may revoke other grants to the same app identity;
review the account's connected-app settings if other Google connections stop working.
Calendar and Gmail remain separate consent/credential flows. Nicknames are optional.

Existing combined connections keep their enabled capabilities and original OAuth scopes;
the UI identifies their broader consent. Disconnect and reconnect for narrow per-file
consent. No credentials are silently reauthorized or migrated. The legacy sign-in API
without a service selection retains its original combined-scope contract for compatibility;
the product UI always selects one service and requests only `drive.file`.

Assistants need `workspace_actions` tools. They prepare a plan with the connected account
reference, exact destination and changes, then request fresh approval to execute it.
Successful effects are read back and journaled; uncertain effects are not retried blindly.
Sharing or notifying people requires separate authority. Disconnecting clears local
credentials and attempts Google revocation; existing cloud files remain. The callback
reports success/cancellation and removes its status query from browser history. Live
Google account validation remains blocked by the missing publisher registration.

Docs and Sheets creation uses server-assigned IDs. Google explicitly
[does not support pre-generated IDs for these file types](https://developers.google.com/workspace/drive/api/guides/create-file#generate_ids_to_use_with_your_files).
Hutch sets a random creation identity in the initial file metadata and reconciles a lost
response with a bounded exact-property search and metadata readback. Missing, multiple,
truncated or mismatched results stay uncertain; the create is never automatically replayed.
Media uploads retain their supported pre-generated-ID path. Upload conversion to native
Workspace MIME types is rejected; use the corresponding Docs or Sheets action instead.

## Hutch on your phone (experimental)

The **Your devices** section in Apps & AI exposes phone supervision directly. It connects a
phone browser to the Hutch host for monitoring, exact approval decisions, stop/resume and
optionally starting work. It does not grant access to the phone's apps, messages, contacts
or files.

First configure private HTTPS access and the passkey hostname as described in
[ADR 0010](adr/0010-api-transport-and-remote-supervision.md). Then choose **Pair a phone →
Create pairing code** on the local host. Open the displayed private `/pair` address on the
phone, enter the single-use code within 60 seconds and enroll a passkey. The code is shown
only in that dialog; Hutch does not place it in a URL, browser storage or clipboard.
Starting work is unchecked by default and also requires the local per-assistant setting.
Paired phones cannot create pairing codes or administer integrations. Existing device
revocation is available under **Hutch on your phone → Manage devices**.

The UI refuses code creation when remote access, the canonical HTTPS/passkey origin or
the hostname allowlist is missing. It never enables a listener or installs certificates
automatically. Configuration readiness does not prove network reachability. Physical
phones, live private networks and production certificate management remain unverified.

## Notion search and page reads (experimental)

Open **Apps & AI → Notion → Connect Notion**. Hutch registers
a public client with Notion's official hosted MCP service and opens browser OAuth with
PKCE; no personal token or publisher client ID is needed for this flow. Finish sign-in,
reload Apps & AI and choose **Choose assistant access**. Select an assistant and the
search/page-read tools to grant. Strict Offline assistants are excluded.

Notion's `default` OAuth grant can authorize broader workspace access than Hutch's read
tools expose. Hutch only offers discovered `notion-search` and `notion-fetch`; it does not
expose writes, comments, deletion, connected-source search, sampling, roots or interactive
MCP apps. Results can go to the selected assistant's configured model providers and remain
in history. Explicit read grants cover normal reads, with policy authorization recorded
for the canonical action receipt; there is no repeated approval form for each search.

The official SDK is pinned to `mcp==2.3.0`. It negotiates modern `2026-07-28` and legacy
Streamable HTTP servers. Requests stay at `https://mcp.notion.com/mcp`; redirects, arbitrary
server endpoints and compressed responses are refused. Response/event bytes, schema size,
list pagination and request time are bounded. Server instructions, annotation claims and
external asset URLs never become execution authority. Canonical names are account-bound
`mcp__notion_<account>__<tool>` and per-assistant grants use the existing integration tables.

New grants apply to new work; a running task cannot gain integrations absent from its immutable admission snapshot. The built-in runtime and the governed Linux OpenCode bridge use the same bound tools and receipts. OpenCode bridge fixture coverage is not a live model evaluation.

Every call refreshes discovery and compares the reviewed schema before its read; a changed
manifest invalidates grants when discovered from setup. Removing access takes effect for
already constructed tools before the next read. Cancellation closes an in-flight read; it
does not claim a remote action was undone. Revoke one assistant or disconnect the account
from this panel. Disconnect disables all local grants and clears local tokens before
requesting provider revocation; an unconfirmed remote revocation is reported explicitly.
Tokens and refresh rotation stay in Linux Secret Service, not SQLite, URLs or browser
storage. Windows/macOS credential stores and live Notion account validation remain open.

Controlled tests exercise OAuth, JSON/SSE wire transport, modern/legacy negotiation, grant
revocation, schema changes, cancellation and the real browser/API path. These are not a
claim that a live Notion account has been connected or that public distribution is ready.

## KDE Connect device status (experimental, Linux)

Open **Apps & AI → Your devices → KDE Connect → Choose device access**. Pair your phone
using KDE Connect itself first. Choose **Find paired devices**, select a device and an
assistant, then **Allow status reads**. Opening Apps & AI or the setup dialog does not
enumerate devices. A retry is available if KDE Connect is not running.

The assistant can read only that device's pairing/reachability and last reported battery.
Battery data is not guaranteed fresh; offline devices and missing/disabled battery plugins
return an unavailable value rather than a fabricated zero. Device names are untrusted data.
Status can reach the assistant's selected model provider and be retained in run history.
Only built-in and governed OpenCode assistants outside Strict Offline mode are eligible.
Existing runs cannot acquire a new device grant midway through execution.

Reopen **Choose device access** to remove an assistant's grant. This takes effect on its
next protected call, including a held tool; a read whose grant or pairing is revoked before
completion withholds its result. Removing access leaves KDE Connect pairing intact.
This adapter never pairs/unpairs devices, activates the daemon, changes plugins, rings a
phone, sends messages, reads notifications/clipboard/files, or invokes remote commands.
It uses bounded, cancellable `/usr/bin/busctl` calls on the local user's D-Bus session.
Paired Hutch supervision browsers cannot administer these grants or enumerate devices.

Controlled subprocess, API, canonical receipt/bridge and responsive UI checks cover this
slice. A harmless local D-Bus protocol probe confirms the machine-readable response shape;
physical Android/iOS behavior and other Linux distributions have not been validated.
See the [integration coverage audit](realignment/integration-coverage-2026-10-26.md).

## Finding and managing connections

**Apps & AI** is a searchable directory of apps, devices and model services. Filter by
connected or not connected, or search by name/capability. Empty results have a clear
reset action. Selecting an app's settings opens a focused page with its accounts,
assistant permissions and disconnect controls; unrelated provider forms stay out of view.
Focused URLs such as `#/connections?app=notion` survive reload and browser Back/Forward.
**All connections** returns to the directory. Configured Google/Microsoft quick sign-in
still opens the actual provider consent flow directly and never requires an account nickname.

Connected Notion workspaces emphasize **Choose assistant access**; adding another workspace
is a separate secondary action. OAuth connection and assistant authority remain separate.
Connection references and provider diagnostics are available on purpose. Gmail's developer
registration link opens the shared Google settings page; released apps should carry their
own publisher registrations rather than require users to register apps themselves.

**Hutch on your phone → Manage devices** keeps revocation accessible and offers pairing
another phone. KDE Connect's status grants remain a separate, explicitly chosen device
capability. Opening the directory reads saved grant metadata; it does not enumerate
phones or change remote-access configuration. A late directory response cannot replace
another page after navigation.
