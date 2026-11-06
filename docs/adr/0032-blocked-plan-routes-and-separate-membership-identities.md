# ADR-0032: Plan keys whose terms forbid Hutch's use are blocked identities, not templates

Status: accepted, 2026-11-06.

## Context

Several vendors sell a coding subscription alongside a general pay-as-you-go API and issue a key for each.
The two keys look alike, often work against the same family of models, and sit on hosts that differ by one
path segment (`/api/paas/v4` against `/api/coding/paas/v4`) or one subdomain (`dashscope-intl` against
`coding-intl.dashscope`). Other applications routinely conflate them: a plan key pasted into a general route
bills the wrong balance, and a general key pasted into a plan route is refused with a misleading error.

The plan terms also differ in what they permit:

- Alibaba Cloud Coding Plan: "interactive use in programming tools"; scripts, application backends and other
  non-interactive use are a violation that can suspend the subscription (vendor page read 2026-11-06).
- Z.AI GLM Coding Plan: "may only be used within officially supported tools and products" (usage policy
  read 2026-11-06). Hutch is not on that list.
- Kimi Code: members may use their key in third-party tools if they keep the real client identifier
  (vendor docs read 2026-11-06).

Hutch bots run unattended and are not a listed tool of any vendor. The previous catalogue modelled Kimi Code
as an auth method of `moonshot`, which hid its separate endpoint, key and bill.

## Decision

1. A route whose vendor terms forbid Hutch's use is recorded as an auth method with status `blocked` and a
   cited source in the catalogue. It has no connection template, no endpoint in any template, and no way to
   be reached by pasting its key into another template.
2. `tests/test_flagship_routes.py` fails if any template's `base_url`, `anthropic_base_url` or
   `models_base_url` points at a recorded plan endpoint.
3. A plan or membership that the vendor allows in third-party tools is its own catalogue identity with its own
   template and environment variable (`kimi-coding`, `opencode-go`, `opencode-zen`), subscription billing where
   it is one, and an acknowledged notice stating what the vendor requires of the client.
4. Regional hosts are separate templates with distinct environment variable names, so a region cannot be
   selected by accident and one variable cannot carry two regions' keys.
5. A template with no verified vendor model list sets `models_endpoint` false. Hutch does not ship a
   hardcoded model list as if it were discovery.

## Consequences

- A user who owns an Alibaba or Z.AI plan sees the route as blocked with the reason, instead of a working
  connection that may bill the wrong balance or put the subscription at risk.
- If a vendor later lists Hutch or permits unattended use, the change is one catalogue edit plus a template and
  a test update, and a dated source.
- Kimi Code and OpenCode Zen enter as `implemented-unverified`; they are not live-verified, and no UI or
  documentation may call them supported until a dated live record exists.
- Hutch gives up convenience (no Coding Plan quota for these vendors) for a policy boundary it can state.

