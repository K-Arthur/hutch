# Multi-provider UX and compatibility review — 2026-10-10

## Decision

Make provider setup a short, one-page connection: choose a named provider, paste
its own API key, and ask that provider for its current model catalog. Keep custom
endpoints, connection labels, and plan-specific routes in a collapsed advanced
section. Keep ChatGPT plan sign-in separate from OpenAI API billing. A catalog
entry is a current provider claim, not proof that a model supports Hutch's tools
or every task. Hutch must not silently swap the user's chosen provider or model.

## Findings and sources

- OpenAI's `GET /v1/models` lists model IDs available to the authenticated API
  key. It does not test an inference request or establish model-specific tool
  behavior. Hutch discovers names from the user's live account instead of
  publishing a model list in the app. [OpenAI API: List models](https://developers.openai.com/api/reference/resources/models/methods/list)
- Anthropic's Models API returns pages and continuation metadata; the catalog
  can evolve independently of application releases. Hutch follows cursors,
  bounds discovery at 10,000 IDs, and rejects repeated/missing cursors.
  [Anthropic API: List models](https://platform.claude.com/docs/en/api/models/list)
- OpenRouter's catalog reports current model metadata and prices. Its routing
  can use a configured fallback and the model that actually answers can differ
  from the requested catalog ID; therefore displayed catalog price is
  informational, and recorded response identity must be used for receipts.
  [OpenRouter model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties),
  [fallback routing](https://openrouter.ai/docs/guides/routing/model-fallbacks)
- T3 Chat's help and feature-feedback pages illustrate two issues to guard
  against: BYOK responsibility and a user's surprise when key priority changes
  which account pays. This is one report, not a prevalence estimate. Hutch
  makes a newly pasted key take priority for that one named connection, says
  where the key is kept, never echoes it, and returns to the environment key
  when the local key is cleared.
  [T3 Chat FAQ](https://t3.chat/faq),
  [BYOK priority feedback](https://feedback.t3.chat/p/enable-byo-api-key-for-gpt-5-and-gpt-5)
- OpenRouter's fallback behavior is not the same as Hutch's cross-provider
  fallback chain. Hutch keeps the selected Hutch route explicit and records the
  model returned by the provider. OpenRouter may still route within its own
  service according to provider options and availability; users should review
  provider-side routing and prices.
- Provider marks are current local vendor assets rather than icon-font
  approximations. Mobbin lookup was unavailable on the connected plan and the
  Figma MCP limit was reached during this session; no Mobbin or Figma screen
  review is claimed. The shipped layout follows Hutch's main design system and
  the official vendor assets documented in [brand-assets.md](../brand-assets.md).

## Implemented safeguards

- Quick setup uses provider templates delivered by Hutch; no model IDs or price
  values are embedded in the UI. OpenAI-compatible providers list live model
  IDs, Anthropic uses its paginated model endpoint, and OpenRouter keeps its
  searchable live catalog. Catalog reads do not make inference calls.
- The API key is sent only over the local app connection to Hutch and is saved
  to a private per-connection key file. It is not placed in browser storage or
  returned by the API. Credentials remain provider-scoped; no key is sent to
  another service.
- OpenAI API, Anthropic API, OpenRouter, OpenCode subscription keys, and
  Sign in with ChatGPT are shown as distinct access/billing routes. A connected
  plan is not described as free API access.
- Catalog failures preserve the saved connection but are visibly reported as
  unverified. A successful catalog read does not claim inference, tool-call,
  pricing, or live account compatibility.

## Verification boundary

Automated fixtures cover provider catalog pagination, account-specific model
discovery, credential routing, key-size/empty-key rejection, and the one-step
connection response. Browser captures cover the setup dialog at desktop, tablet,
and phone widths and a simulated catalog success. No live paid provider account
was used. Provider-specific live inference, billing, fallback routing, and tool
behavior remain unverified and must stay described as such.
