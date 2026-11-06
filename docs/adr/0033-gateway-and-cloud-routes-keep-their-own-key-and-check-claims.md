# ADR-0033: Gateway and cloud routes keep their own key placement, and a check never claims more than it did

Status: accepted, 2026-11-06.

## Context

Phase 4 of the provider expansion added hosted providers, gateways and cloud routes. Reading vendor
documentation and probing hosts without a credential (research record
`docs/research/2026-11-provider-expansion/05-HOSTED-AND-GATEWAYS.md`) exposed four recurring failures in
other clients that Hutch would otherwise repeat:

- A host reads its key from a vendor header. Azure OpenAI's v1 API takes `api-key`; a Bearer value is treated
  as a Microsoft Entra ID token, which produces 401 or 404 responses that look like a wrong URL.
- A "connected" or "authenticated" check passes because the model list is public. Measured on 2026-11-06,
  eight hosts return HTTP 200 on `/models` for a placeholder key. Hutch reported "authenticated; N models" for
  seven of them.
- A subscription or plan endpoint is used by mistake and bills a different balance (Volcengine `/api/v3`
  against `/api/coding/v3`), or its terms forbid unattended use (Tencent Token Plan).
- A gateway pays for a failed request on its own credentials (Vercel BYOK fallback), so the key the person
  chose is not the payer.

Hutch's local-first, explicit-approval model and its honest-status vocabulary apply: a template is not a
support claim.

## Decision

1. A template may carry its key in a named header by declaring a header whose whole value is `{api_key}`. The
   key is substituted only when a provider is built, so no template, stored connection, catalogue row or API
   response holds it; the Bearer header is then omitted so the key travels in exactly one place; the form is
   refused on every protocol except OpenAI chat; a placeholder embedded in a longer value is refused.
2. A template whose host answers its model list for any key declares `models_list_ignores_key`, based on a
   dated measurement with a placeholder value. The connection check lists the models and reports the key as
   not verified; no consumer prints "verified" for an unverified check. Verification stays with a normal,
   governed bot request. OpenRouter keeps its dedicated key check.
3. A route whose terms forbid Hutch's use stays a `blocked` auth method with a cited source and no template
   (extending ADR-0032 to the Tencent Token Plan). A plan whose terms neither permit nor forbid unlisted tools
   (Volcengine and BytePlus Coding Plan) is `documented` and not offered. A pay-as-you-go template for the
   same vendor says it does not draw from the plan.
4. A gateway is its own identity and its billing exceptions are in an acknowledged notice, not hidden in a
   hint (Vercel BYOK fallback).
5. A template may list tool-schema keywords its host rejects. The wire copy is trimmed; `Tool.parameters` and
   `validate_call` remain the execution contract, so trimming never loosens what runs.
6. Cloud authentication that needs a request signer or a token mint (AWS IAM and SigV4 with the Converse event
   stream, Google service accounts, Microsoft Entra ID) is not shipped until it can be verified. Both approved
   dependency families stay unused: the shipped routes use plain header credentials (a Bedrock API key, an
   Azure resource key), and no dependency was added.

## Consequences

- Eight templates (Vercel AI Gateway, LiteLLM, ClawRouter, Bedrock runtime, Bedrock Mantle, Microsoft Foundry,
  Qianfan, StepFun global) are `implemented-unverified`.
- The three template-only settings are data. Provider code gained a 34-line key-header module, a 73-line
  schema-trim module (pure functions plus a thin provider wrapper), and a short branch in `provider_for_connection`; the frozen `openai_compat.py` and
  `connections.py` did not grow.
- `models_list_ignores_key` can lag a vendor change. If a vendor starts validating the key, the check
  under-claims (reports not verified) rather than over-claims. Re-measure when a template is reviewed.
- The flag and the trimming list apply to the template's own host. A user who points the template at another
  server keeps the same conservative reporting.
- Bedrock IAM, Vertex, Entra ID and Cloudflare AI Gateway remain `documented`. Revisit when an account for
  each can verify the route; the dependency approvals recorded in the progress file still stand.
