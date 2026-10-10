# Research v2: what Dots and Grok Bot offer, and what they get wrong

Sources read on **2026-10-07**. This file extends [complaints.md](complaints.md) (which covers
agent products generally) with a narrower question: *Hutch is aiming at the same shape of product as
**OpenAI Dots** and **Grok Bot / Grok Team Bots** — named, always-on bots that work while you are away —
so what exactly do those two offer, and where do their users say they fail?*

**How to read the evidence.** Vendor documentation and primary issue trackers are stated as fact.
Reviews and aggregator blogs are labelled *reported*. A few pages were read through a summarising
fetch tool; where a number appears only in a secondary source it is marked *(unconfirmed)*. Nothing
here was tested against the live products — neither is available to us.

---

## 1. The two reference products

### OpenAI Dots (launched ~30 Sep 2026)

Persistent agents that keep working after you close the chat. Each dot has its own cloud computer
and browser, connects to "more than 4,000 applications" through plugins, and can be messaged from
ChatGPT (desktop/web/mobile), Slack and Teams. **ChatGPT Space** is the shared layer where people,
ChatGPT, Codex and dots work against the same context.
([VentureBeat](https://venturebeat.com/technology/openai-launches-dots-always-on-ai-agent-coworkers-and-chatgpt-space-where-they-can-collaborate-with-human-teams),
[The Rundown](https://www.therundown.ai/articles/openai-connects-the-dots-on-always-on-agents))

Control surface (per VentureBeat): **Custom Rules** that "permit particular actions, require approval
or prohibit them"; an **Activity View**; an auto-review step on consequential actions; password changes
stay human-only; proactive research tools are read-only. OpenAI "acknowledges that Dots can still make
mistakes and advises users to review consequential work."

### Grok Bot (11 Aug 2026) and Team Bots (28 Sep 2026)

Each member gets a persistent managed Linux VM ("Agent Computer") with Chrome and a terminal; bots run
as a non-root user in a workspace directory. Features: memory across sessions; **"watch me once"** routine
capture; scheduled routines; asynchronous bot-to-bot messaging; **Team Bots** = shared bots with their own
context/plugins/credentials/memory, per-user private conversations, their own Slack handle, and role
templates (sales, PM, marketing, data analytics). Sold via Cursor Ultra ($200/mo) or Cursor Premium Teams
($120/seat/mo), bundled with SuperGrok Heavy.
([eesel review](https://www.eesel.ai/blog/grok-bot),
[AlphaSignal](https://alphasignal.ai/news/xai-s-grok-team-bots-give-entire-teams-one-shared-ai-agent),
[Digital Applied](https://www.digitalapplied.com/blog/grok-bot-ai-teammates-launch-cloud-computer-2026))

---

## 2. What users report as broken — and the Hutch answer

Every row names the requirement (see [requirements.md](../requirements.md)) that answers it.

### Grok Bot

| Reported failure | Evidence | Hutch answer |
|---|---|---|
| **One shared computer for all bots** — files, browser sessions and CLI credentials are common to the whole roster; the docs say "do not use separate Bots as a security boundary". | [eesel](https://www.eesel.ai/blog/grok-bot), [CellCog](https://cellcog.ai/blog/grok-bot-problems/) | Per-bot workspace, per-bot browser profile, per-bot memory (existing); per-specialist workspace with *explicit, logged* file copies (**CO-4**). |
| **Shared computer wedged → every bot stopped at once** (20–21 Aug 2026; reset can lose unsynced work). | [CellCog](https://cellcog.ai/blog/grok-bot-problems/) | A crash in one runtime or model affects only its own runs; health shown per runtime (**SR-1**). |
| **No spend cap; weekly allowance unpublished; overage at raw model rates; no model picker; metering showed "48% consumed as 0%" at launch.** One business user with 6 agents burned 42% of a weekly allowance on day one *(reported)*. | [Continuum](https://continuumcode.ai/guides/grok-bot-limits/), [CellCog](https://cellcog.ai/blog/grok-bot-problems/) | Record exact response tokens and reserve shared-account allowance plus price-based cost estimates before a call (**SR-2**, partial); enforce step, execution-time and token limits; price estimates are admission signals, not external billing guarantees (**LM-9**); editable price file with a verified-on date (**LM-14**); usage page (**UI-11**, pulled forward). |
| **Approvals are "text-based descriptions rather than enforced gatekeepers"**; "an approval controls the proposed action, and it does not reverse work already completed." | [eesel](https://www.eesel.ai/blog/grok-bot) | A deterministic policy engine decides allow/ask/deny *before* execution; the approval shows the parsed command segments and the rule that fired (**UI-5**, **SR-12**). |
| **No dry run** — "testing performs real work". No confidence thresholds or historical simulation. | [eesel](https://www.eesel.ai/blog/grok-bot) | **Rehearse** mode (new): run a bot with every mutating action simulated and logged; reads still run. |
| **Audit logging "in the future tense"; all actions attributed to the human owner.** No SOC 2/ISO/GDPR/HIPAA claims. | [eesel](https://www.eesel.ai/blog/grok-bot) | Hash-chained event log per run so edits to history are detectable (**SR-11**, pulled forward); every run carries its parent bot or plan (**SR-7**). |
| **Unbounded context** — each bot is one growing thread, full history reloaded each turn; no fresh-session control, no manual compaction, no context meter. | [CellCog](https://cellcog.ai/blog/grok-bot-problems/) | A run is the unit (fresh context by default; memory is explicit and editable — **UI-10**); Bot settings keep its inventory beside the Bot and can export revision/review/share history without adding another global page; context-use meter against the effective window (**UI-4**, **LM-3**). |
| **Lopsided limits**: 50 bots+chats per account, 2–6 bots per group chat, 20 run records retained, 10-minute demo recordings *(all unconfirmed by xAI)*. | [Continuum](https://continuumcode.ai/guides/grok-bot-limits/) | No artificial counts; transcripts are kept; limits are *engine-enforced per plan* (hops, tasks, parallelism, wall-clock — **CO-6**). |
| **Slow and flaky**: tasks "take about an hour end to end" vs ~10 minutes locally; "overloaded-provider errors"; sites block datacenter IPs; sessions drop when the VM is recreated; files outside `/workspace` vanish on update. | [HN 49899033](https://news.ycombinator.com/item?id=49899033), [CellCog](https://cellcog.ai/blog/grok-bot-problems/), [Flavio Copes](https://flaviocopes.com/grok-bot/) | Runs on *your* machine and IP with persistent browser profiles; provider fallback chain (**SR-8**) and streaming retry (**SR-9**); state in one inspectable directory. |
| **Opaque waits** — "Bot failed to respond" persisting through reinstall. | [CellCog](https://cellcog.ai/blog/grok-bot-problems/) | Every waiting state names its cause and a fix (**UI-6**). |

### OpenAI Dots

| Reported failure | Evidence | Hutch answer |
|---|---|---|
| **Eligibility and price**: Pro / Business Premium only (not Plus or legacy Team); first-dot price and per-token rate unpublished; "barrier to entry is kinda absurd"; ~$100 entry point *(reported)*. | [Rewarx](https://www.rewarx.com/blogs/what-are-developers-saying-about-openai-dots-reddit-and-x-consensus), [AIPass](https://aipass.one/blog/openai-dots-hype-reactions-clones) | Free, MIT, runs offline on a mock model; bring any model, pay only the model provider (prices shown in-app). |
| **Region gate**: not available in the EEA, Switzerland or the UK. | [HN 49896604](https://news.ycombinator.com/item?id=49896604), [Rewarx](https://www.rewarx.com/blogs/what-are-developers-saying-about-openai-dots-reddit-and-x-consensus) | Nothing to gate: data stays on your disk; only the model you choose is called. |
| **Desktop-only creation** ("asked to switch to desktop"). | [AIPass](https://aipass.one/blog/openai-dots-hype-reactions-clones) | Responsive dashboard; approvals inbox usable at phone width (**UI-13**). |
| **No API/SDK announced; no published throughput or context length.** | [Rewarx](https://www.rewarx.com/blogs/what-are-developers-saying-about-openai-dots-reddit-and-x-consensus) | Full REST API; Models page shows the context each model will *actually* get (**LM-5**). |
| **"Agents going off the rails"; claim completion of work they didn't do.** | [HN 49896604](https://news.ycombinator.com/item?id=49896604) | Artifacts and exit codes live in the transcript, not only the model's claim; loop detector and caps (**SR-5**). |

### What they do well (and we should match)

- **Rules that permit / require approval / prohibit** → per-bot risk tier plus per-command rules (**SR-12**).
- **An activity overview** → Home with *Needs you / Running now / Stale* (**UI-1**).
- **Templates for common roles** → template gallery (**UI-7**) with sales, PM, marketing and analytics starters.
- **Scheduled work and recurring automations** → already shipped; now with a Schedules page (**UI-9**).
- **Bots collaborating while keeping context small** — praised in the HN threads
  ("domain-specific expertise without overloading context windows") → planner + specialists (**CO-1…11**).

### What we deliberately do **not** copy

4,000-app plugin catalogue, voice/phone calling, Slack/Teams handles, multi-user workspaces, a mobile app,
hosted cloud computers. These are in the v0.2 out-of-scope list. Hutch is a *self-hosted, single-user*
product with the same shape; it is not a multi-tenant hosted service. See
[roadmap.md](../roadmap.md) for the open question on a hosted offering.

---

## 3. Adjacent failures that hit exactly these features

### Stop that doesn't stop (UI-2)
Claude Code: *Stop* did not stop spawned sub-agents ([#95138](https://github.com/anthropics/claude-code/issues/95138));
sub-agents of sub-agents stay "Running" forever ([#73916](https://github.com/anthropics/claude-code/issues/73916));
one runaway needed the window force-closed — the stop path was queued behind model processing, not independent
([#98708](https://github.com/anthropics/claude-code/issues/98708)). A community dashboard lost its only
`ChildProcess` handle after ~3 s, making sessions unstoppable
([claude-agents-dashboard #97](https://github.com/futin/claude-agents-dashboard/issues/97)).
→ **Stop kills process groups and every child run, independent of the model loop.**

### Live view that silently loses events (UI-3)
OpenCode's SSE endpoint ignored `Last-Event-ID`: background a tab for ~30 s mid-task and the gap is gone
([#25657](https://github.com/anomalyco/opencode/issues/25657)). Browsers send `Last-Event-ID` automatically,
but many servers ignore it and keep no replay buffer.
→ **Per-run event sequence numbers, replay from the database, `Last-Event-ID` honoured, client-side gap detection.**

### Local models that quietly forget (LM-1, LM-2, LM-3)
Ollama defaults to **4k context below 24 GiB VRAM**; its docs recommend **≥ 64,000 tokens for agents**
([context-length docs](https://docs.ollama.com/context-length)). Through the OpenAI-compatible endpoint
`num_ctx` cannot be set, so prompts are silently truncated from the front — one report logs
`truncating input prompt limit=4096 prompt=10573`, and the system-prompt files simply vanish
([openclaw #4028](https://github.com/openclaw/openclaw/issues/4028)).
→ **Native chat API, explicit `num_ctx` every call, a needle-at-the-top self-check that fails loudly, and a
pre-run warning when prompt + tools exceed the effective window.**

### Small-model tool calls (LM-11, LM-13, SR-5)
Malformed or string-encoded tool calls, especially in long contexts
([ollama #18506](https://github.com/ollama/ollama/issues/18506)); reliability scales with model size and
agentic training. Thinking modes add latency and tokens on short routing/extraction turns
([Ollama tool-calling docs](https://docs.ollama.com/capabilities/tool-calling)).
→ **Parse → validate against schema → one retry with the error; ≤ 8 tools per bot; thinking off by default;
loop detector; per-model reliability profiles measured rather than assumed.**

### Cold loads and model swapping (LM-6)
Ollama unloads after 5 minutes idle by default; the next request pays a reload of seconds to tens of seconds;
too-tight VRAM makes models swap on every request. → **Models are scheduled resources; queued runs sharing a
model are batched; "loading model" is a visible run state with the measured load time.**

### Multi-agent collaboration (CO-1…11)
MAST (1,600+ annotated traces, 7 frameworks, 14 failure modes) attributes **41.8%** of failures to specification
and design (missing termination conditions, role ambiguity), **36.9%** to inter-agent misalignment and
**21.3%** to weak verification ([Cemri et al.](https://arxiv.org/pdf/2503.13657)). Anthropic reports early
multi-agent systems "spawning 50 subagents for simple queries", duplicated investigations from vague tasks,
and ~**15×** the tokens of a chat ([engineering post](https://www.anthropic.com/engineering/multi-agent-research-system)).
Infinite hand-off loops (A→B→C→A) are reported as the top production failure mode.
→ **One planner, a fixed specialist list, structured messages only, no specialist-to-specialist chat, hard
limits on hops/tasks/parallelism/wall-clock/budget, duplicate-task detection that pauses the plan.**

### Fallbacks that become spend storms (SR-8, LM-9)
"A single misconfigured fallback line turned a $40/month API bill into $2,300 in 48 hours" *(quarantined 2026-10-07: no source was recorded and none could be found; the design rule it motivated stands on its own, without the figure)*
([DEV](https://dev.to/ai-gateway-veteran/the-2300-weekend-when-fallback-routing-goes-wrong-in-ai-gateways-1iip)).
→ **Fallback is an ordered chain with price-estimate admission limits; every escalation is logged and moves one step; the
first hosted call from a local-default bot asks first (LM-10).**

### Prompt-cache invalidation (PF-1)
Timestamps in system prompts, non-deterministic tool ordering and tool lists that change mid-run each wipe the
cached prefix ([claude-code #49038](https://github.com/anthropics/claude-code/issues/49038),
[openclaw #156977](https://github.com/openclaw/openclaw/issues/156977),
[husearch #59](https://github.com/AsemAbdelfattah/husearch/issues/59)).
→ **Byte-identical system prompt and tool list for a whole run; prefix hash recorded per step; cached-token share reported.**

### Approval fatigue and unreadable prompts (UI-5)
Claude Code users approve 93% of prompts *(reported)*; Anthropic's own study found "ask for everything" misses
most threats; one issue asks for the requesting agent and reasoning instead of "tool name + truncated command"
([#85023](https://github.com/anthropics/claude-code/issues/85023),
[auto-mode post](https://www.anthropic.com/engineering/claude-code-auto-mode)).
→ **Command split into parsed segments, the rule that fired, three choices (once / always for this bot / deny),
visible default-deny countdown; sticky allows so the prompt volume stays low.**

### Local dashboards drivable from any web page (UI-12)
A localhost approval endpoint can be hit cross-origin by any page the user visits, or via DNS rebinding:
[serialwarden #56](https://github.com/SheldonChangL/serialwarden/pull/56) (approve pending writes via a
body-less cross-origin POST), [GAIA #3365](https://github.com/amd/gaia/issues/3365),
MCP Inspector RCE [CVE-2025-49596](https://www.oligo.security/blog/critical-rce-vulnerability-in-anthropic-mcp-inspector-cve-2025-49596),
and OpenClaw's dashboard exposing management APIs on all interfaces with a bearer token printed in a log URL
([#27323](https://github.com/openclaw/openclaw/issues/27323),
[CVSS 9.0 write-up](https://dev.to/oolongtea2026/when-your-dashboard-leaks-the-keys-a-cvss-90-credential-exposure-in-openclaw-1bg0)).
**Historical gap in Hutch v0.1, fixed locally in the realignment.** The dashboard now checks Host and Origin/Fetch-Metadata, uses a
CSRF token for form actions, and atomically records approvals/stops. Remote access remains opt-in: direct non-loopback binding requires
TLS and an operator-issued single-use device pairing code; sessions can be revoked in Connections or by CLI. The pairing and device
management UI has local browser-fixture coverage; no physical-device or network test has been performed, and no public exposure is
supported.
→ **Acceptance boundary:** hostile cross-origin posts and Host rebinding fail closed; pairing is single-use and rate-limited; the host
does not print bearer tokens in URLs or logs. See [ADR-0010](../adr/0010-api-transport-and-remote-supervision.md).

### Silent non-runs (UI-1, UI-9)
n8n: "active" only means the trigger is armed; a workflow that stopped running produces zero failures and zero
alerts ([community thread](https://community.n8n.io/t/the-silent-failure-when-your-n8n-workflow-succeeds-but-does-nothing/307116);
one audit of 50,669 runs found most failures alerted nobody —
[DEV](https://dev.to/achiya-automation/i-audited-50669-n8n-runs-85-of-failures-alerted-nobody-47pm)).
→ **A *Stale* list on the first screen: last success older than the schedule implies, with cause and fix.**

### Browser zombies (PF-8)
Orphaned or defunct Chromium processes accumulate and eventually hit PID/RAM limits
([playwright-mcp #1568](https://github.com/microsoft/playwright-mcp/issues/1568),
[onyx #15664](https://github.com/onyx-dot-app/onyx/issues/15664)).
→ **Launch on first use, close after 5 idle minutes and on run end, killed with the run's process group.**

### Duplicate side effects (CO-8, SR-4)
Retries and planner loops send the email twice; the fix is stable intent keys, not fresh UUIDs per retry
([DEV](https://dev.to/loopandretry/your-retry-just-sent-the-email-twice-idempotency-keys-for-agents-ip)).
→ **Same task posted twice pauses the plan; outward-sending actions always ask, regardless of sticky allows.**

### First-run friction on local models
The #1 reason first-time local setups fail is memory fit, not installation; a model that silently falls to CPU
runs at a fraction of the speed with no error ([MindStudio](https://www.mindstudio.ai/blog/how-to-run-local-ai-models-with-ollama)).
→ **Hardware probe; every model marked fits / tight / won't fit with the context it will actually get; first-run
offers mock demo, a model that fits, or an API key (UI-8).**

---

## 4. Pricing facts used in the app

Claude prices (USD per million tokens) were read from the official page
[platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)
on 2026-10-07: Fable 5.1 $10/$50, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 (prompts ≤ 100k),
Haiku 4.5 $1/$5; cache reads 0.1× base (0.05× on Opus 5.5 / Sonnet 5.5, 0.025× on Fable 5.1).
OpenAI's pricing page was read through a summarising fetch; only gpt-4o ($2.50/$10) and gpt-4o-mini
($0.15/$0.60) are carried into the price file and flagged for re-verification. The file is user-editable
(**LM-14**) and the UI shows the verified-on date for each row.

## 5. Not verified / limits of this research

- Dots and Grok Bot were not used hands-on; every claim is from vendor docs, press or user reports.
- Limit figures for Grok Bot (50 bots, 2–6 per chat, 20 run records, 10-minute recordings) are *unconfirmed* by xAI.
- Model reliability percentages quoted in blog posts (e.g. "qwen3:8b ≈ 85%") were **not** relied on; Hutch measures
  reliability on the user's own machine (**LM-11**).
- No local LLM runtime exists on the development machine (4-core Ryzen 3 5300U, no usable GPU), so local-model
  behaviour was built against the documented Ollama API plus a scripted fake server, not measured on real models.
