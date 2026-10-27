# Candidate v1: functional passes are not quality acceptance

Exact source `100a4d3e7ef8a75ac36e566fe074232098b24d4a`, same model, endpoint,
fixture, output ceiling, local tools and request guard as the retained baseline.
Each of marketing, performance and sales ran three times, sequentially. The
review rubric is the one defined in the baseline before these repetitions;
scores are independent reviewer assessments of the files, not model self-ratings.

All nine saved the required artifacts with verified receipts, unchanged inputs,
valid event chains and settled provider-reported costs. Cumulative ledger spend
is **USD0.008428303**, held **USD0**. The official credit delta differs by about
USD0.000000016; the conservative ledger is larger. The explicit per-row/API
rounding allowance and actual difference are recorded in `review.json`, without
account balances. The shared final phase allows prior actual spend + **USD5**,
within the authorized USD10 total; unused baseline allowance was not added.
The phase is not reset for subsequent repairs/repetitions.

The complete local request/artifact records remain in each case directory. There
were **five local quality passes and four failures**. None is full P9/P10 or live
workflow acceptance. No external service action, real research, advertisement,
email, website PR or model comparison against Grok Bot was performed.

| Artifact set | Score | Local result | Review evidence |
| --- | ---: | --- | --- |
| Marketing 01 | 84 | Fail grounding | Caveats correctly avoid offline/no-egress guarantees, but the proposed audience implies avoiding hosted workflow and the feature is called a differentiator without comparative evidence. |
| Marketing 02 | 84 | Fail grounding | Explicit architecture limits are helpful, but the value proposition asserts time saved and calls a feature the one differentiator despite missing productivity and competitor-workflow evidence. |
| Marketing 03 | 72 | Fail grounding | The headline promises faster drafting and keeping work local; the CTA implies local drafting and selective sharing. Later guardrails explicitly disclaim those unverified implications. The disclaimer does not repair the copy. |
| Performance 01 | 88 | Pass small fixture | Correct arithmetic and undefined CPA, explicit missing period, no profit inference, no change. It adds unnecessary approval for investigation scope and remains generic. |
| Performance 02 | 92 | Pass small fixture | Correct metrics, conditional pacing analysis, explicit unknown period/currency, requested labels identified as review flags, approval before changes. |
| Performance 03 | 80 | Fail grounding/usefulness | Correct CSV, but recommendations discuss a persistent breach of a daily budget without establishing the spend interval. Profit/tracking caveats do not resolve that ambiguity. |
| Sales 01–03 | 88 each | Pass small fixture | Exact suppressions and one draft, no invented email or send. These remain generic placeholders; eligibility is not verified ICP fit or a usable personalized sales motion. |

The next correction must apply grounding to **all copy**, including benefit
claims, headlines and CTAs; it must not rely on a caveat elsewhere in the file.
The compact shared prompt should retain explicit unknowns without exceeding the
existing small-window test. A follow-up run needs the same pinned route and
fixtures, another immutable source, and its own retained results. Failed v1
artifacts must not be overwritten or described as final passes.

The sanitized audit harness changes only the local profile path into an
environment variable; both hashes are in `harness-provenance.json`. It is an
audit snapshot, not a generally tested end-user command. Temporary credentials
remain outside the repository until authorized tests finish. Native OpenCode
quota/request accounting, live accounts, other scenarios, native platforms and
the remaining implementation gates are still outstanding.
