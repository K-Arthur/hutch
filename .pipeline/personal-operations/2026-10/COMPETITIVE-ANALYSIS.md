# COMPETITIVE-ANALYSIS: October 2026 landscape and where Hutch differentiates

Dated: 2026-10-31. Access date for all sources: 2026-10-31. Pricing is volatile; every price below
is tagged and dated, and cells marked "not verified" were inaccessible (403, JS-only page or
redirect stub) rather than guessed. This is a pattern analysis, not a feature-parity matrix.

## 1. Market map (late October 2026)

| Cluster | Players | What buyers use it for | Dominant model |
|---|---|---|---|
| Self-hosted personal agent | OpenClaw, Hermes (and hosted OpenClaw wrappers) | Always-on assistant across chat apps, files, browser, coding CLIs | Bring your own server, model and API keys; broad tool surface; community skills |
| Workflow automation SaaS | n8n, Zapier, Make | Connect apps, run deterministic automations, add AI steps | Visual graph, connector catalogue, execution/credit metering |
| AI teammate / inbox ops | Lindy | Inbox triage, meeting prep, scheduling, CRM updates in Slack/email | Per-seat subscription with pooled credits and guardrails |
| Calendar and task scheduling | Reclaim AI, Motion | Defend focus time, auto-schedule tasks, replan around meetings | Background scheduling agents, calendar-centric, subscription per seat |
| Workspace AI | Notion AI, Google Workspace AI, Microsoft Copilot/Power Automate | Summarize, draft, act inside docs/mail/chat; automations in the suite | Per-seat AI add-on credits; enterprise admin and compliance model |
| Coding agents | Claude Code, OpenAI Codex, OpenCode, Pi | Execute repo work from a CLI/IDE/cloud with subagents and tools | Agentic coding runtime with usage caps or token billing |
| Multi-agent coding orchestration | Claude Code subagents/worktrees, Codex harnesses, OpenClaw/Pi delegation, "plan-then-delegate" workflows | Parallelize repo work, isolate branches, keep a human reviewer | Supervisor + delegates; the orchestration layer is where failures concentrate |

Two market facts frame the whole table. First, the self-hosted-agent category is real but
cost-sensitive and power-user shaped: HN coverage of OpenClaw put it at ~350,000 stars while the
top replies described personal automation and a "just handy" verdict, and one user reported
~$3.50/day as not worth it (S1, OBSERVED). Second, the complaint data says the pain has moved from
wrong code to the bill and to security: token-consumption complaints rose from 9.1% to 13.7% of AI
coding complaint posts between the two measured windows, while incorrect code fell from 13.1% to
9.6% (S2, OBSERVED study by a competitor).

## 2. Comparison table A - execution model, trust model, sharing, pricing

| Player | Execution and persistence model | Approval / trust model | Sharing model | Pricing evidence (tagged) |
|---|---|---|---|---|
| OpenClaw | Gateway process on your machine; chat channels (Discord, Telegram, iMessage, Slack, WhatsApp and more); Automations/cron/test runs with run history; memory as Markdown files | Exec approvals, sandboxing opt-in, channel allowlists, bot loop guard; docs concede one trust boundary per gateway and "not a hostile multi-tenant security boundary" (S4) | Multi-user mode with session ownership/presence but explicitly "usability features, not security boundaries" (S4) | Free, open-source, self-hosted; VPS cost external, 4 GB class server per S5 |
| Hermes | Agent-first runtime; learns from experience and builds its own skills; free/open-source, self-hosted | Safer defaults than OpenClaw per comparison coverage; self-written skills widen the trust surface (HYPOTHESIS) | Single-operator self-host in reviewed coverage | Free, open-source; same VPS class as OpenClaw (S5) |
| n8n | Self-hosted or cloud; visual nodes plus JS/Python; AI Agent/MCP nodes; execution-based billing | Credentials held in the automation tool; human-approval steps are workflow constructs | Shared projects/roles; unlimited users on all cloud plans | Community Edition free self-host; Cloud Starter EUR 20/mo annual (2,500 execs), Pro EUR 50 (10,000), Business EUR 667 self-hosted-only (S6 verified pricing page; S7 review) |
| Zapier | Cloud only; 9,000+ app connections; Zaps, agents, MCP, SDK; task-based billing | OAuth-scoped connections per Zap; enterprise security controls on higher tiers | Team accounts and shared folders | Pricing page is JS-rendered; billing for Next-Gen Zaps/SDK confirmed by help center but exact numbers not verified this pass (S8, S9) |
| Make | Cloud; visual scenarios; modules billed per execution and run frequency limited by tier | Connection-level scopes; no local execution | Team/org roles | Free 1,000 credits/mo; Core $9 for 10,000 credits; per-module billing and tier-capped run frequency (S10, third-party dated 2026-10-15) |
| Lindy | Cloud; Slack/iMessage/SMS/email/web; skills as playbooks; routines on schedule/trigger; Watch-and-Learn turns a recorded process into a skill | Per-integration guardrails choose which writes run automatically and which wait for approval in Slack | Shared Lindy in channels plus private Lindys per person; pooled workspace credits | From $29.99/user/mo; $50 free credits lasting 7 days; credits $0.01 base, pooled, do not roll over; actions pause when credits run out (S11 verified pricing doc; S12 review) |
| Reclaim AI | Cloud; background agents schedule focus time, habits, buffers and tasks onto Google Calendar/Outlook; reschedules as meetings move | Rules the user sets; 2.0 "Preview Mode" stages proposed changes in a sandbox calendar until applied; MCP server | Per-user calendar; teams analytics on higher tiers | Free Lite plan with 5 AI Agents; Starter $10/seat/mo annual (S13, third-party review dated 2026-09-29) |
| Motion | Cloud; auto-schedules tasks/projects/meetings and replans; docs, notetaker, AI chat | Rule-based auto-scheduling; permissions on Business tier | Team workspaces with capacity planning | No free plan (7-day trial); Teams Pro AI $19/seat/mo annual ($25 monthly), Business AI $29 annual ($41 monthly); Individuals Pro AI $37 annual; 7,500 AI credits on Pro AI (S14, review dated 2026-10-14) |
| Notion AI | Cloud workspace; AI writing/search, agents and custom agents; triggers inside Notion and connected apps | Workspace permissions + AI credits; agent actions scoped to connected tools | Workspace/team sharing, guest access | Free $0; Plus $10/member/mo; Business $20/member/mo; agent credits per seat (S15, observed pricing page) |
| Google Workspace AI | Cloud suite; Gemini in Docs/Gmail/Meet/Sheets plus Workspace automation features | Google Workspace admin, DLP, consent model | Domain/org sharing and admin controls | Not verified this pass (pricing page JS-rendered); capability surface observed on the Workspace pricing page (S16) |
| Microsoft Copilot / Power Automate | Cloud suite plus automation; Copilot across Word/Excel/Outlook/Teams; agents and Copilot Studio; Power Automate flows | Microsoft 365 admin, compliance, connector policies | Tenant/org sharing, external sharing controls | Not verified this pass (pricing and plan pages JS-rendered); capability surface observed (S17) |
| Claude Code | CLI/IDE agent; subagents, worktrees, hooks/skills; usage-metered against subscription windows | Per-tool permissions and approval prompts; worktree isolation for parallel agents | Repo/branch sharing; no product-level shared spaces | Exact prices not verified this pass (docs redirect stub); 5-hour session quota and weekly cap behaviour documented in S18 issue |
| OpenAI Codex | Cloud/CLI coding agent; delegation harness; run from another machine via app-server routing | Sandboxed execution, approval modes; cloud review flows | Repo/PR sharing | Not verified this pass (pricing page returned 403); capability surface observed in OpenClaw's Codex docs (S19) |
| OpenCode | Open-source coding CLI/agent; web client; Go paid tier per S2 | Permission prompts; local execution | Repo/PR sharing | Not verified this pass; tier structure and rising complaint volume in S2 |
| Pi | Minimal open-source harness; four modes (interactive, print/JSON, RPC, SDK); extensions/skills/packages; no sub-agents or plan mode by default | Minimal defaults; customization is the user's responsibility | Package sharing via npm/git | Open-source install; no vendor price observed (S20) |
| Multi-agent orchestrators | Decomposition into small plans, supervisor loops, isolated worktrees, reviewer agents | Human review at merge; per-agent permissions vary by tool | Repo-level | Mixed open-source and bundled; evidence in S2, S21, S18 |

## 3. Comparison table B - documented weaknesses and reusable patterns

| Player | Documented / observed weakness (tagged) | Reusable pattern worth copying | Where Hutch differentiates |
|---|---|---|---|
| OpenClaw | Onboarding "too many hurdles" (S22 issue); upgrade breakage and rollback gaps (S23 incident write-up); worst security-risk and ethics complaint profile in measured set (S2); not a multi-tenant boundary by design (S4) | Chat channels as clients; unified Automations with ran/delivered/completed states; standing orders with approval gates and escalation; metadata-only audit ledger and decision receipts; bot loop guard | Make the trust boundary and the sharing boundary explicit from day one; ship a receipt-facing UI instead of a docs page |
| Hermes | Newcomer; self-written skills increase trust surface (HYPOTHESIS); high measured complaint volume, 1,502 posts in the current window (S2) | Safer defaults as a selling point; self-improving skills | Keep self-extension review-gated; local evidence for every skill change |
| n8n | Self-hosting is real ops work; editor assumes technical skill; cloud capped by monthly executions; Business plan not on Cloud (S7) | Visual workflow plus code escape hatch; execution-based billing; self-host option; MCP | Own the scheduler and state locally; no per-execution meter for personal ops |
| Zapier | Task-based cost scales with activity; cloud-only; deep connector breadth is its moat | Connector breadth as an integration layer; AI agents and MCP exposure | Ship a small set of first-class, owned integrations with receipts rather than 9,000 shallow ones |
| Make | Credit meter with frequency caps; hidden switching costs (S10) | Module-level composability | Predictable cost, no module counting for personal commitments |
| Lindy | No permanently free plan; credits do not roll over; actions pause when exhausted (S11, S12) | Per-integration guardrails (auto vs approval); Watch-and-Learn to capture a process; editable team memory files | Local execution removes per-action credit anxiety; approvals stay local and inspectable |
| Reclaim AI | Calendar-only scope; cloud-hosted; no tasks/projects outside the calendar (S13) | Preview Mode: stage proposed schedule changes in a sandbox until the human applies them | Apply the same staged-proposal pattern to calendar writes and to commitments, not just scheduling |
| Motion | No free plan; US-hosted data; AI credit top-ups (S14) | Replanning around changed constraints; dependency-aware auto-scheduling | Local-first data ownership; deterministic plan review instead of opaque replanning |
| Notion AI | AI value gated behind higher workspace tiers and per-seat credits (S15) | Workspace as source of truth; agents inside the document context | Keep the user's operating record in a local DB the user owns |
| Google Workspace AI | Cloud/tenant assumptions; admin-gated AI; automation tied to the suite | Assistants embedded where documents and mail already live | Local files and local credentials; no tenant admin required for a household |
| Microsoft Copilot / Power Automate | Enterprise-first admin/compliance model; automation tied to M365 licensing | Copilot Studio-style agent definitions and connector policies | Household-scale permissions and explicit, revocable bot grants |
| Claude Code | Runaway polling/fan-out cost (S18, S24); worktree contention loses work (S25); subagents falsely claim completion (S26) | Plan mode, subagent decomposition, worktree isolation (when correctly implemented), hooks | Supervise coding CLIs with isolated worktrees, verified completion and budget caps |
| OpenAI Codex | Cloud dependency; pricing opacity (not verified); harness complexity | Delegation harness and app-server routing (per S19) | Keep coding execution local and reviewable; no cloud round-trip required |
| OpenCode | Rising complaint volume as adoption grows (S2); paid-tier ambiguity | Open-source coding runtime that a platform can embed | Treat coding agents as supervised workers with receipts |
| Pi | Deliberately minimal: no sub-agents or plan mode by default (S20) | Token-efficient minimal harness; four execution modes; self-extension via packages | Ship the durable orchestration layer Pi deliberately omits, without forking the coding loop |
| Multi-agent orchestrators | Repo corruption and lost work under parallelism (S25); recursive fan-out charges (S24); unreviewed code and maintenance burden (S2) | Decompose into small plans; supervisor loop; isolated branches; reviewer agent | Queue of reviewed briefs with worktree isolation, approval binding and run receipts |

## 4. Cluster notes

### 4.1 Personal AI operations (OpenClaw, Hermes, Lindy)
The category sells "an AI employee" and then delivers a supervised assistant. The most credible
public positioning is the least flashy: OpenClaw's own community write-up says "if you expected
autopilot, it feels overrated. if you want to own the stack and build unfair workflows, it's worth
going deep" (S21, COMPLAINT aggregate; OBSERVED quote). Lindy productises the guardrail idea with
per-integration auto-vs-approval rules (S12). Neither sells the thing Hutch needs to sell: a
durable record of what the user promised, what the system did, and what is still unverified.

### 4.2 Workflow automation (n8n, Zapier, Make)
These are the mature competitors for "connect services and run on a schedule", and they win on
connector breadth and enterprise trust. Their weaknesses are structural for personal use:
execution/credit meters, cloud dependency, and an editor built for builders. n8n's self-hosted
Community Edition is the closest existing analogue to local-first automation, but it is
workflow-authoring-first: a household commitment is not a first-class object.

### 4.3 Calendar and task scheduling (Reclaim AI, Motion)
Reclaim's Preview Mode is the single most transferable pattern in this cluster: proposed schedule
changes are staged in a sandbox until the human applies them (S13). Motion's strength is
continuous replanning; its cost is opacity plus a credit system and US-only data storage. Both are
calendar-centric, which leaves the cross-surface commitment (school test, grocery run, invoice,
follow-up) largely unserved.

### 4.4 Workspace AI (Notion, Google, Microsoft)
Embedded assistants are winning distribution, not trust: they inherit the suite's permission model
and billing tier. For a household or a two-person family workflow, requiring an admin console and
per-seat AI credits is a mismatch. The reusable pattern is context proximity (the agent sees the
document/mail it acts on); the pattern to avoid is cloud-tenant lock-in of the operating record.

### 4.5 Coding agents and orchestration (Claude Code, Codex, OpenCode, Pi, orchestrators)
The tools are now good enough that the orchestration layer is the differentiator and the failure
site. Primary issues show the exact shapes: 195 consecutive requests for 32 lines of code in 19
minutes (S18), parallel worktree agents losing uncommitted work to git lock contention (S25), and
subagents reporting completion without writing files (S26). Pi's minimalism and Claude Code's plan
mode pull in opposite directions; a dependable platform needs Pi's small surface plus Claude
Code's supervision affordances, with local receipts.

## 5. What Hutch should not copy

1. Do not copy chat-as-the-only-interface. Conversation is the trigger, not the record.
2. Do not ship a "verified showcase" without publishing run receipts or rollback evidence.
3. Do not use model instructions as a security boundary. OpenClaw's bundled-hook incident
   (#8776), the Slack-description injection CVE (S27) and the Promptfoo exploit chain (S28) all
   show prompt-level defenses failing at the action boundary.
4. Do not make credentials ambient. A single read-write vault for a generalist agent (E4 in
   RESEARCH.md) is a liability without per-tool, per-run scoping.
5. Do not copy credit-meter economics. Per-action credits, non-rolling balances and pausing when
   exhausted are incompatible with commitments that must fire on time.
6. Do not copy "multi-user is usability, not security". For family/household workflows that is
   backwards; sharing must be a scoped, revocable grant.
7. Do not copy unbounded recursive fan-out. Caps on agent depth, concurrency and spend are
   load-bearing (S24, S2).
8. Do not copy auto-applied calendar writes. Copy Reclaim's Preview Mode staging instead.
9. Do not copy self-modifying skills without review, signing and a trust boundary.
10. Do not copy silent success. Ran, delivered, completed, unknown and failed must be distinct.
11. Do not copy the connector-breadth arms race. Depth on owned workflows beats 9,000 shallow
    integrations for a local-first personal platform.
12. Do not copy "autopilot" marketing. The honest positioning (supervised assistant that owns
    state) is both more defensible and better supported by the evidence.

## 6. Differentiation thesis for Hutch

Hutch competes where these products are weakest in combination: the operating record is local and
user-owned (not a tenant), the schedule is first-class and fail-closed (not a credit meter), the
shared boundary is a scoped grant (not a shared chat), completion is verified with receipts (not
claimed), and coding work is supervised delegation (not a second coding agent). "Local-first" is
necessary but not sufficient; the claim that can be defended is "your bots, your machine, your
rules, with evidence".

## Sources cited in this file

| ID | Source | URL | Published / observed | Access | Tag |
|---|---|---|---|---|---|
| S1 | The Agent Times, OpenClaw adoption analysis | https://theagenttimes.com/v1/articles/openclaw-s-350k-github-stars-haven-t-answered-our-hardest-qu-9e0718e6 | published 2026-04-16 | 2026-10-31 | OBSERVED |
| S2 | OpenChamber, "A year of AI coding complaints" | https://openchamber.dev/blog/ai-coding-complaints/ | published 2026-09-21 | 2026-10-31 | OBSERVED |
| S3 | OpenClaw showcase | https://openclaw.ai/showcase | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S4 | OpenClaw security doc / multi-user doc | https://docs.openclaw.ai/gateway/security.md ; https://docs.openclaw.ai/concepts/multi-user.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S5 | Gizmodo, "OpenClaw vs Hermes Agent 2026" | https://gizmodo.com/best-web-hosting/openclaw-vs-hermes | published 2026-10-01 | 2026-10-31 | OBSERVED |
| S6 | n8n official pricing | https://n8n.io/pricing/ | observed 2026-10-31 | 2026-10-31 | VERIFIED |
| S7 | The AI Agent Index, n8n review | https://theaiagentindex.com/agents/n8n | published 2026-04-23, updated 2026-10-29 | 2026-10-31 | OBSERVED |
| S8 | Zapier official pricing | https://zapier.com/pricing | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S9 | Zapier help, Next-Gen Zaps/SDK billing | https://help.zapier.com/hc/en-us/articles/49965546559117-How-Next-Gen-Zaps-and-the-Zapier-SDK-are-billed | observed 2026-10-31 | 2026-10-31 | VERIFIED |
| S10 | Activepieces, "Make.com Pricing 2026" | https://www.activepieces.com/blog/makecom-pricing-2026-plans-credits-and-real-costs | published 2026-10-15 | 2026-10-31 | OBSERVED |
| S11 | Lindy pricing (official docs) | https://docs.lindy.ai/pricing.md | observed 2026-10-31 | 2026-10-31 | VERIFIED |
| S12 | The AI Agent Index, Lindy review | https://theaiagentindex.com/agents/lindy | published 2026-03-18, updated 2026-10-29 | 2026-10-31 | OBSERVED |
| S13 | The AI Agent Index, Reclaim.ai review | https://theaiagentindex.com/agents/reclaim-ai | published 2026-04-01, updated 2026-09-29 | 2026-10-31 | OBSERVED |
| S14 | The AI Agent Index, Motion review | https://theaiagentindex.com/agents/motion | published 2026-05-06, updated 2026-10-14 | 2026-10-31 | OBSERVED |
| S15 | Notion pricing and AI product pages | https://www.notion.com/pricing ; https://www.notion.com/product/ai | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S16 | Google Workspace pricing page | https://workspace.google.com/pricing | observed 2026-10-31 | 2026-10-31 | OBSERVED (prices not verifiable) |
| S17 | Microsoft Copilot for business | https://www.microsoft.com/en-us/microsoft-365/business/copilot-for-microsoft-365 | observed 2026-10-31 | 2026-10-31 | OBSERVED (prices not verifiable) |
| S18 | Claude Code issue #103406, runaway polling loop | https://github.com/anthropics/claude-code/issues/103406 | opened 2026-10-19, closed | 2026-10-31 | VERIFIED |
| S19 | OpenClaw docs index, Codex/OpenCode harness pages | https://docs.openclaw.ai/llms.txt | observed 2026-10-31 | 2026-10-31 | VERIFIED |
| S20 | Pi coding agent homepage | https://pi.dev/ | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S21 | Hacker News item 46931805 (mirror) | https://hn.nuxt.dev/item/46931805 | ~2026-02 (264 days before access) | 2026-10-31 | COMPLAINT |
| S22 | OpenClaw issue #79330, onboarding hurdles | https://github.com/openclaw/openclaw/issues/79330 | opened 2026-05-08, open | 2026-10-31 | VERIFIED |
| S23 | DEV, "OpenClaw 2026.7.1 broke installs..." | https://dev.to/lars_winstand/openclaw-202671-broke-installs-and-the-reddit-thread-was-way-more-useful-than-the-release-notes-2kmd | published 2026-07-15 | 2026-10-31 | OBSERVED |
| S24 | Claude Code issue #72861, recursive subagent fan-out charges | https://github.com/anthropics/claude-code/issues/72861 | opened 2026-07-01, closed | 2026-10-31 | VERIFIED |
| S25 | Claude Code issue #55724, worktree parallel agents lose work | https://github.com/anthropics/claude-code/issues/55724 | opened 2026-05-03, closed | 2026-10-31 | VERIFIED |
| S26 | Claude Code issue #46755, subagents falsely report completion | https://github.com/anthropics/claude-code/issues/46755 | opened 2026-04-11, closed | 2026-10-31 | VERIFIED |
| S27 | CVE-2026-24764 / GHSA-782P-5FR5-7FJ8 | https://vulnerability.circl.lu/vuln/brew-openclaw-cli-cve-2026-24764 | published 2026-08-13, updated 2026-10-29 | 2026-10-31 | VERIFIED |
| S28 | Promptfoo, "OpenClaw at Work" | https://www.promptfoo.dev/blog/openclaw-at-work/ | published 2026-03-12 | 2026-10-31 | OBSERVED |
| S29 | OpenClaw issue #8776, bundled hook can hijack the agent | https://github.com/openclaw/openclaw/issues/8776 | opened 2026-02-04, closed | 2026-10-31 | VERIFIED |
