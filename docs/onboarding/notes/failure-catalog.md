# Failure and complaint catalog for Hutch onboarding (2026-10-29)

Companion to best-practices.md. Each row is a reported failure from a comparable product, the mechanism that produced it, whether Hutch can realistically fix the same class, and a priority. GitHub issue/PR text and excerpts were read via the GitHub API on 2026-10-29; where only the issue metadata and body excerpt were read it is noted in Sources. These are individual reports, not prevalence measurements.

## How to read this

- P1: blocks or misroutes the first useful output, or loses a secret/state silently.
- P2: recoverable but wastes the user's work, adds support load, or teaches the wrong model.
- P3: polish; fix after the first-output path is solid.
- "Fixable in Hutch" answers whether the same class can occur in a local-first dashboard that calls the user's own providers; "no" means the mechanism depends on a hosted account/tier Hutch will not have.

## Catalog

| # | Reported complaint | Mechanism | Source | Fixable in Hutch | Priority | Why |
|---|---|---|---|---|---|---|
| 1 | "no model selected by default on first launch... 'Select a model' placeholder" | Onboarding wrote no model into chat state; regression in 0.7.8 | [Jan #7658](https://github.com/janhq/jan/issues/7658) | yes | P1 | The first request cannot succeed without a route; the chosen route must become the chat default or a clear "Choose AI" action |
| 2 | Fresh install "dropped users straight into the chat with no engine, no embedding model, and no indication either was missing... broken without the user noticing" | Nothing probed readiness or surfaced missing dependencies | [Jan PR #8594](https://github.com/janhq/jan/pull/8594) | yes | P1 | Same shape as a dashboard that renders chat before any provider exists |
| 3 | Issue asks to prompt a model download when none exists; body says "we default a cloud model and show API key error, which is not cool" | Optimistic cloud default plus an error meant for a different problem | [Jan #3537](https://github.com/janhq/jan/issues/3537) | yes | P1 | "Not configured" must not be reported as "invalid key" |
| 4 | Onboarding buttons not visible on some Android browsers | Layout/overflow on the first-run page overflows the mobile viewport | [Open WebUI #16287](https://github.com/open-webui/open-webui/issues/16287) | yes | P1 | The first action must be inside 375x812 and reachable by touch |
| 5 | "impossible to paste API key after /connect (Ctrl-V / Ctrl-Shift-V / right-click all fail, no hints)" | Terminal input swallows paste; no instruction and no visible field affordance | [OpenCode #9922](https://github.com/anomalyco/opencode/issues/9922) | partly | P1 | A browser field is easier, but same user expectation: paste must work and masked entry must be explained |
| 6 | Browser says "authorization successful", CLI stays "Waiting for authorization" | OAuth redirect succeeded but the local poll never received/matched the callback | [OpenCode #7992](https://github.com/anomalyco/opencode/issues/7992), [invalid-code OAuth callback #18362](https://github.com/anomalyco/opencode/issues/18362) | partly | P1 | External provider login is in Hutch's scope; needs timeout, cancel, retry and a "sign in again" path |
| 7 | Users "can't get passed 'Start Chatting' modal" and are redirected back, acceptance flag never set | Consent acknowledgement state not persisted or validated server-side | [chat-ui #252](https://github.com/huggingface/chat-ui/issues/252) | yes | P1 | Hutch's terms acknowledgement must persist and must not loop |
| 8 | First model download stays at "Initializing Download" with "no message in the console" | Long async download with no progress, error channel or retry | [Jan #7728](https://github.com/janhq/jan/issues/7728), [Jan #7801](https://github.com/janhq/jan/issues/7801), [Jan #1556](https://github.com/janhq/jan/issues/1556) | partly | P1 | If Hutch triggers model pulls, progress and failure must be visible; if not, probes still need deadlines |
| 9 | "Can't connect to Ollama from Open WebUI"; "Model list takes forever to load / 500 on /api/models" | No timeout/retry budget and no mapping from error text to cause | [Open WebUI Troubleshooting](https://docs.openwebui.com/troubleshooting/) | yes | P1 | Provider checks are the onboarding gate; they need bounded time and translated errors |
| 10 | A /models endpoint works while chat/completions returns 401 | Readiness inferred from listing models rather than a real generation | [OpenCode #38257](https://github.com/anomalyco/opencode/issues/38257) | yes | P1 | The "verified" state must be proven by a minimal real request |
| 11 | "opencode connect OpenAI fails" style flows plus raw network errors ("socket connection closed unexpectedly", "Unable to connect. Is the computer able to access the URL?") | Transport errors shown verbatim; no diagnostic next step | [OpenCode #21643](https://github.com/anomalyco/opencode/issues/21643), [#12083](https://github.com/anomalyco/opencode/issues/12083), [self-signed cert #54095](https://github.com/anomalyco/opencode/issues/54095) | yes | P2 | Hutch will see the same socket/TLS/DNS failures with user-run local servers; translate to "check service/URL/cert" |
| 12 | API key lost after updating the container; API-key auth broke after an upgrade | Persistence tied to volume/env and not migrated across versions | [Open WebUI #1135](https://github.com/open-webui/open-webui/issues/1135), [auth broken after upgrade #8100](https://github.com/open-webui/open-webui/issues/8100) | partly | P2 | Local state survives installs only if stored in the documented data dir and migrations cover it |
| 13 | First-run empty states inconsistent in title voice, CTA label, layout, icon; list chrome flashes before the empty state | One-off empty states per resource, no shared state machine | [n8n PR #33670](https://github.com/n8n-io/n8n/pull/33670) | yes | P2 | Several empty states in Hutch (bots, chats, connections) should share one component and copy rules |
| 14 | Sidebar onboarding checklist disabled because it was not helping | Checklist competes with real work and is not dismissible/short enough | [n8n PR #35734](https://github.com/n8n-io/n8n/pull/35734) | yes | P2 | Keep readiness information, but do not gate value on checklist completion |
| 15 | Onboarding re-asks for location/units already present in configuration | Onboarding ignores existing state and does not prefill from config | [Home Assistant #35696](https://github.com/home-assistant/core/issues/35696) | yes | P2 | Detected provider/route/config must prefill and be labelled as detected |
| 16 | Hardware requirements discovered only after install/download (16 GB+ RAM recommended, AVX2 required, Intel Macs unsupported) | Requirement is documented but not gated in the flow | [LM Studio System Requirements](https://lmstudio.ai/docs/app/system-requirements) | partly | P2 | Put the machine-fit information before the heavy download or the local-route promise |
| 17 | Install docs unclear that CUDA libraries are needed even with non-NVIDIA setups | Install prerequisites not stated at the decision point | [Ollama #2503](https://github.com/ollama/ollama/issues/2503) | partly | P2 | Hutch docs can state per-OS prerequisites for Ollama/local routes |
| 18 | Ollama server "stops serving requests after 10-15 minutes" | Long-running provider stalls; requests hang instead of failing fast | [Ollama #4545](https://github.com/ollama/ollama/issues/4545) | partly | P2 | Onboarding and chat need request timeouts and a "provider stopped responding" state with retry |
| 19 | First-time model download does not auto-select the model in new chat | Download completion not wired into chat selection state | [Jan #7566](https://github.com/janhq/jan/issues/7566) | yes | P1 | Same as #1: a verified route must propagate everywhere the composer reads state |
| 20 | Self-hosted AI setup with environment-managed values: wizard must only ask for missing steps and must not reveal server values | Setup flow assumes it owns all configuration | [n8n PR #35579](https://github.com/n8n-io/n8n/pull/35579) | yes | P2 | Hutch may get keys from env/operator config; the wizard should show "managed by operator" as read-only |
| 21 | Pairing/device flow stuck at "Starting Interview" with no recovery | Async device-interview state has no timeout, cancel or retry | [Home Assistant #99497](https://github.com/home-assistant/core/issues/99497) | partly | P2 | Analog for phone QR pairing: pairing must expire, cancel and retry cleanly (analog inferred, not the same protocol) |
| 22 | Guided tour library failed to locate elements on Linux; backdrop had to be disabled | Tour libraries have platform-specific positioning failures | [Jan PR #5529](https://github.com/janhq/jan/pull/5529) | yes | P3 | Hutch is Linux-first; if any coach-mark/tour is used, test WebKitGTK/Chromium on Linux |
| 23 | AppImage certificate issue caused model download failure | Packaging/signing affects downloads, not just install | [Jan #4582](https://github.com/janhq/jan/issues/4582) | partly | P3 | Relevant to Tauri packaging later; not an onboarding blocker today |
| 24 | Self-hosting quick start friction: database, inference server, docker or git+npm | Many independent setup decisions before first value | [chat-ui #1774](https://github.com/huggingface/chat-ui/issues/1774) | partly | P2 | Hutch install-from-source docs are the real "onboarding" for self-hosters; reduce decisions in the path |
| 25 | Provider tier error: "free tier can only be used from within OpenCode" | Hosted entitlement leak into a local client | [OpenCode #49433](https://github.com/anomalyco/opencode/issues/49433) | no | out-of-scope | Hutch has no hosted tier and should not add one |
| 26 | Provider 401 "Request blocked by upstream provider" while listing works | Upstream policy/entitlement failure masked as auth error | [OpenCode #38257](https://github.com/anomalyco/opencode/issues/38257) | partly | P2 | Hutch can distinguish HTTP 401/403/429 in copy and suggest "provider account issue" |
| 27 | Default tiered context length can exhaust VRAM | Hardware-dependent default chosen without a safety margin | [Ollama #14116](https://github.com/ollama/ollama/issues/14116) | no | out-of-scope | Hutch does not set local model context defaults; if it ever does, gate on measured VRAM |

## Cluster synthesis

| Cluster | Rows | What it means for Hutch |
|---|---|---|
| Blank or wrong first state | 1, 2, 3, 13, 19 | The dashboard must never render chat as if a route exists; state must be probed and the chosen route propagated |
| Secret/credential entry and persistence | 5, 6, 7, 12, 20 | Paste, mask, callback handling, server-side storage and operator-managed mode are the real edge cases |
| Async work without progress or deadline | 8, 9, 11, 18, 21 | Every provider probe, download or pair needs progress, timeout, retry, cancel |
| Misleading readiness | 10, 26 | "Verified" must mean a real generation succeeded, not that a model list was reachable |
| Empty-state and checklist quality | 13, 14 | Optional, consistent, action-labelled; do not make the checklist the product |
| Existing state ignored | 15, 19, 20 | Detected/configured state should prefill and be marked, not re-asked |
| Hardware/install prerequisites | 16, 17, 24 | State fit and prerequisites before the heavy step and in install docs |

## Modality reality check (testing the borrowed fintech/KYC framing)

Checked the first-run/setup documentation of all eight products above plus the issues in this catalog: none of them makes document upload, proof-of-address, liveness/selfie, e-signature, or government-ID verification part of first-run setup. The Signicat figures below come from regulated financial onboarding, which is not Hutch's onboarding. Treating KYC drop-off as Hutch's baseline would mis-prioritise the work.

| Modality actually in Hutch's onboarding scope | Where it appears | Failure classes that matter |
|---|---|---|
| Hosted provider API key (secret text field) | AI service step | Paste failure, masking, storage/echo, lost after restart, wrong-key error wording |
| Local service endpoint URL (plain text) | Ollama/OpenAI-compatible route | Reachability, timeout, TLS/DNS errors, model list vs real generation |
| External provider login/OAuth | External provider route | Redirect/callback mismatch, poll timeout, cancel, cookie/state mismatch |
| QR pairing scanned by phone camera | Optional channel connection | Expiry, stale QR after retry, cancel, duplicate pairing, progress copy |
| Bot token (e.g. Telegram) (secret text field) | Optional channel connection | Paste, validation, revocation, "where the token is stored" |
| First request / sample prompt (free text) | Chat first run | Empty-state guidance, draft loss, request not sent, no first output |
| Terms/connection acknowledgement | Before first provider call or connection | Persistence, loop prevention, versioned consent, no re-ask after reload |
| Install/start commands (copy-paste docs) | Before the dashboard exists | Wrong Python/Node version, port conflict, unread error, update confusion |

## Borrowed-statistics ledger

| Claim in the task prompt | Closest real source found | What the source actually measures | Verdict |
|---|---|---|---|
| "~2 in 10 users complete onboarding checklists" | Secondary compilation quoting a Userpilot 2025 benchmark of 188 companies: average checklist completion 19.2%, median 10.1% ([Tour Kit checklist-psychology post](https://raw.githubusercontent.com/domidex01/tour-kit/4db0fe72ce36181c9ce67809832db8f07c09b98f/apps/docs/content/blog/onboarding-checklist-psychology.mdx)) | A vendor survey-derived average across its own customers/benchmark participants, not a general law and not Hutch's users. The cited primary page ([Userpilot benchmark URL](https://userpilot.com/blog/onboarding-checklist-completion-rate-benchmarks/)) when opened returned navigation text only; the 19.2%/10.1%/188 figures were not present in the fetched content | UNVERIFIED as stated; do not reuse the number. The defensible statement is "most users who see a checklist do not finish it (vendor survey), so checklists cannot be the only path to value". A later marketing post puts completion at "20% to 40%" with no method ([PageGains](https://pagegains.com/blog/how-to-write-a-saas-onboarding-checklist-that-users-actually-complete)) |
| "Fintech/regulated onboarding loses 68%+ of applicants" | Signicat "The Battle to Onboard" 2022: 68% of 7,600 consumers across 14 European markets said they had abandoned a financial application in the last year, up from 63% in 2020 ([Signicat six-year retrospective](https://www.signicat.com/blog/btob-six-year-retrospective), [2022 press release](https://www.signicat.com/se/pressmeddelande/the-battle-to-onboard-2022)); 38% lacked the right ID document, average patience before abandoning was 18m53s | Self-reported abandonment of financial-service applications (current accounts, loans, insurance), not KYC applicants only and not a conversion funnel. Fenergo data reported alongside says institutions' average onboarding abandonment is about 10% ([OneID summary](https://oneid.uk/news-and-events/identity-verification-abandonment-cost), secondary) | REAL SURVEY FIGURE, WRONG CONTEXT FOR HUTCH. Do not cite it as Hutch's expected drop-off; use it only to argue that multi-minute identity/KYC steps cause abandonment |
| "do -> configure -> invite re-sequencing nearly doubled activation" | No primary source found after multiple searches. The closest material is secondary: PageGains argues value actions should precede configuration and "invite" steps, and calls "invite your team" the most common blocker ([PageGains](https://pagegains.com/blog/how-to-write-a-saas-onboarding-checklist-that-users-actually-complete)); a compiled experiment list treats step ordering as an untested hypothesis ([Marketingskills experiments](https://github.com/coreyhaines31/marketingskills/blob/main/skills/onboarding/references/experiments.md)); a practitioner post says universal checklists are ignored by "65% to 80%" without methodology ([ProductLedGrowth.AI](https://productledgrowth.ai/articles/saas-onboarding-2026)) | Nothing measures "do -> configure -> invite" or a "nearly doubled" activation result. The percentages cited around this claim are marketing content without visible methodology | UNVERIFIED AND PROBABLY LAUNDERED. Treat the order as a testable hypothesis for Hutch, not a validated rule |

Note on provenance: a public "onboarding and first-run" skill file targets "20-40% activation rate" and repeats the same psychology claims without primary data ([heymegabyte skill](https://raw.githubusercontent.com/heymegabyte/claude-skills/refs/heads/master/06-build-and-slice-loop/onboarding-and-first-run.md)); this is the kind of secondary compilation that turns a vendor number into "2 in 10". Do not reuse.

## Test cases this catalog implies for Hutch

1. No provider configured: chat surface shows "Choose AI", never "invalid key".
2. Saved route is not verified: status says Saved, and first send either verifies first or reports the exact failure.
3. Provider returns 401 on generation but 200 on /models: status is Failed, with provider-account wording.
4. Provider never answers: bounded timeout, cancel, retry and "use another route".
5. API key paste via keyboard and context menu; value never re-displayed after save.
6. External login: redirect success, callback success, callback mismatch, user closes browser, retry.
7. QR pairing: expired QR, rescan, cancel, duplicate phone, connection drop mid-pair.
8. Terms acknowledgement: reload after accept; changing provider does not re-ask; versioned acceptance.
9. Reload during setup: draft request and chosen route survive; secrets remain masked.
10. Empty bot/channel lists: one consistent empty-state component and copy voice.
11. Mobile 375x812: primary action and status visible without scroll.
12. Operator-managed key: wizard shows read-only "managed by operator" and asks only for missing steps.

## Sources (accessed 2026-10-29)

| URL | Title | Type | Supports |
|---|---|---|---|
| https://github.com/janhq/jan/issues/7658 | onboarding: no model selected by default on first launch | primary issue report | row 1 |
| https://github.com/janhq/jan/pull/8594 | feat(onboarding): guided first-run setup wizard | primary PR description | row 2, readiness probe |
| https://github.com/janhq/jan/issues/3537 | Prompt user to download model if none available | primary issue report | row 3 |
| https://github.com/janhq/jan/issues/7728 | Jan does not download models in v0.7.8 | primary issue report | row 8 |
| https://github.com/janhq/jan/issues/7566 | First-time model download does not auto-select the model in new chat | primary issue report | row 19 |
| https://github.com/janhq/jan/pull/5529 | disabled backdrop onboarding on linux | primary PR description | row 22 |
| https://github.com/open-webui/open-webui/issues/16287 | Onboarding page buttons not visible on some mobile browsers | primary issue report | row 4 |
| https://github.com/open-webui/open-webui/issues/1135 | OpenAI API Key disappeared after updating | primary issue report | row 12 |
| https://docs.openwebui.com/troubleshooting/ | Open WebUI Troubleshooting | primary docs | row 9, symptom-indexed surface |
| https://github.com/anomalyco/opencode/issues/9922 | impossible to paste API key after /connect | primary issue report (metadata + body excerpt) | row 5 |
| https://github.com/anomalyco/opencode/issues/7992 | opencode connect OpenAI fails, stuck waiting for authorization | primary issue report (metadata + body excerpt) | row 6 |
| https://github.com/anomalyco/opencode/issues/18362 | Anthropic OAuth callback invalid authorization code | primary issue report (metadata + body excerpt) | row 6 |
| https://github.com/anomalyco/opencode/issues/38257 | OpenCode Go 401 while /v1/models works | primary issue report (metadata + body excerpt) | rows 10, 26 |
| https://github.com/anomalyco/opencode/issues/21643 | socket connection closed unexpectedly | primary issue report (metadata + body excerpt) | row 11 |
| https://github.com/anomalyco/opencode/issues/12083 | Unable to connect. Is the computer able to access the URL? | primary issue report (metadata + body excerpt) | row 11 |
| https://github.com/huggingface/chat-ui/issues/252 | Users can't get passed "Start Chatting" modal | primary issue report (metadata + body excerpt) | row 7 |
| https://github.com/huggingface/chat-ui/issues/1774 | Improve quickstart setup experience | primary issue report (metadata + body excerpt) | row 24 |
| https://github.com/n8n-io/n8n/pull/35579 | Add self-hosted AI Assistant onboarding | primary PR description | row 20, live verification |
| https://github.com/n8n-io/n8n/pull/33670 | Unify onboarding empty states | primary PR description | row 13 |
| https://github.com/n8n-io/n8n/pull/35734 | Tidy Storybook for Figma import | primary PR description | row 14 |
| https://github.com/home-assistant/core/issues/35696 | Location not taken over from configuration file during onboarding | primary issue report | row 15 |
| https://github.com/home-assistant/core/issues/99497 | ZHA onboarding stuck at "Starting Interview" | primary issue report (metadata + body excerpt) | row 21 |
| https://lmstudio.ai/docs/app/system-requirements | System Requirements | primary docs | row 16 |
| https://github.com/ollama/ollama/issues/2503 | Support Radeon RX 5700 XT, install guide ambiguity | primary issue report (metadata + body excerpt) | row 17 |
| https://github.com/ollama/ollama/issues/4545 | Ollama stops serving requests after 10-15 minutes | primary issue report (metadata + body excerpt) | row 18 |
| https://github.com/ollama/ollama/issues/14116 | Tiered context length can exhaust VRAM | primary issue report (metadata + body excerpt) | row 27 |
| https://www.signicat.com/blog/btob-six-year-retrospective | Financial service onboarding: a six-year retrospective | primary report summary | 68% stat |
| https://www.signicat.com/se/pressmeddelande/the-battle-to-onboard-2022 | Battle to Onboard 2022 press release (Swedish) | primary | 68%, 38%, 18m53s details |
| https://www.signicat.com/battle-to-onboard | Battle to Onboard 2020 | primary | 63% 2020 baseline, methodology 4,000 consumers |
| https://oneid.uk/news-and-events/identity-verification-abandonment-cost | Why 68% of Users Abandon Identity Checks | secondary vendor blog | Signicat/Fenergo aggregation |
| https://userpilot.com/blog/onboarding-checklist-completion-rate-benchmarks/ | User Onboarding Checklist (cited benchmark page) | primary claim page; figures not exposed on fetch | 19.2% claim provenance |
| https://raw.githubusercontent.com/domidex01/tour-kit/4db0fe72ce36181c9ce67809832db8f07c09b98f/apps/docs/content/blog/onboarding-checklist-psychology.mdx | Onboarding checklist psychology | secondary blog quoting Userpilot | "2 in 10" claim provenance |
| https://pagegains.com/blog/how-to-write-a-saas-onboarding-checklist-that-users-actually-complete | Why 80% of Users Abandon Your Onboarding Checklist | secondary marketing | checklist ordering claims, 20-40% |
| https://productledgrowth.ai/articles/saas-onboarding-2026 | SaaS Onboarding in 2026: Kill the Checklist | secondary practitioner | 65-80% ignored claim |
| https://github.com/coreyhaines31/marketingskills/blob/main/skills/onboarding/references/experiments.md | Onboarding Experiment Ideas | secondary compilation | step-ordering hypothesis |
| https://raw.githubusercontent.com/heymegabyte/claude-skills/refs/heads/master/06-build-and-slice-loop/onboarding-and-first-run.md | Onboarding and First-Run skill | secondary compilation | provenance warning |
| https://news.ycombinator.com/item?id=36851650 | HN comment on product tours | anecdote | tour fatigue |
