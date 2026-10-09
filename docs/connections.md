# Connections: subscription plans and custom endpoints

## Google Calendar event lookup (experimental, local setup required)

Hutch implements read-only Google Calendar lookup for the built-in runtime. It remains unavailable
by default: the Hutch operator must configure a Google Desktop OAuth client, enable the Calendar
API, and run a Linux desktop session with an unlocked Secret Service. A real Google account was
not used in local verification; Google consent-screen verification and public eligibility are not
claimed. See IG-5 in [requirements](requirements.md#connections-and-integrations-added-at-the-product-owners-request-2026-10-07).

Set `HUTCH_GOOGLE_OAUTH_CLIENT_ID` before starting Hutch. Sign in from the Hutch host at
`http://127.0.0.1:<port>` on the Connections page; Hutch opens Google in a separate browser tab.
Finish consent in that tab, then return to the original Hutch tab and reload Connections. The
installed-app flow uses authorization code
with PKCE and the read-only `calendar.calendarlist.readonly` and `calendar.events.readonly` scopes.
Hutch stores the refresh token in the Linux Secret Service through `secret-tool`; access tokens are
held in process memory. SQLite stores the named account reference and each Bot's selected calendar
grant, never provider tokens. The browser does not receive tokens. Callbacks are local loopback only,
one-use, expire after ten minutes, and have their authorization query removed before request logs.

Google authorizes read-only access at the account level. Hutch's typed Bot tool further restricts
each Bot to the one calendar the owner selected in Connections; that Hutch restriction is not a
provider-enforced per-calendar OAuth grant. The tool can list calendars and return event title, start,
end and location for a bounded time range. It cannot create, edit, delete, invite or send events.
Those returned fields are sent to the Bot's selected model and retained in that Bot's run history.
Descriptions and attendee details are not passed to the model or saved in run history. Calendar text
is untrusted data and cannot approve actions. Strict Offline mode does not expose the online Calendar
tool.

Disconnect first removes Hutch's Bot grants and local refresh credential, then requests Google
revocation. If Google does not confirm revocation, Hutch reports that explicitly and directs the
owner to review connected apps in their Google Account. Never import consumer-app browser cookies,
CLI auth files, or another product's private sign-in state.

Gmail and Outlook remain planned, not connected. Gmail message-body access has separate Google
consent and verification requirements; do not present the working Calendar flow as Gmail support.
Microsoft Graph will use delegated permissions only if implemented. Calendar writes, mail reads or
sends, arbitrary API URLs, deletion and mailbox settings are unavailable. See the current provider
references: [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[Google installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference), and
[Microsoft authorization-code/PKCE guidance](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

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
- **Test** (`CN-8`). `hutch connections test` authenticates against the model list (one `GET`, no tokens).
  Anthropic-protocol endpoints have no standard list, so the test says "not verified" rather than pretending;
  `--chat <model>` opts into one real 8-token call.

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

If the sign-in control is disabled, leave it disabled unless Hutch has confirmed eligibility; setting the local flag is
not an eligibility grant. If the callback expires or Hutch was opened through a hostname, HTTPS proxy, or remote device,
restart the flow from `http://127.0.0.1:<port>` on the Hutch host. If sign-in succeeds without plan-use permission,
the account cannot select ChatGPT models until it is reauthorized with that permission. When Hutch is not eligible or
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
- Not tested against live accounts. If a plan's real behaviour differs from its docs, `hutch connections test
  --chat <model>` is the first diagnostic.
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
