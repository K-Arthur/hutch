# RESEARCH: the OpenClaw showcase, six named workflows, and reusable patterns

Dated: 2026-10-31. Access date for all sources: 2026-10-31. Evidence tags: VERIFIED, OBSERVED,
COMPLAINT, HYPOTHESIS (definitions in 00-BRIEF.md). This file is external evidence and product
pattern analysis; it is not a repo audit and not a feature list for Hutch.

## 1. What the showcase is

The OpenClaw showcase (S1) presents itself as "OpenClaw builds verified in public: X threads,
shipped workflows, and automations people run daily." It is a curated marketing surface: featured
builds plus community cards, each linking to an X thread. No run history, approval log or failure
rate is published with any build. The page is useful as a demand signal and as a catalogue of
workflow shapes, not as reliability evidence (OBSERVED; the "verified" claim is OpenClaw's).

The page also surfaces a live failure anecdote in its own community section: a user reports having
"Sent thousands of messages in a loop to an innocent and unsuspecting person who happened to
message me on WhatsApp" (S1, OBSERVED). That single line is the strongest argument in this
research for idempotent external actions, loop budgets and approval binding on first contact.

## 2. Featured builds on the showcase page (S1, OBSERVED)

| Featured build | One-line workflow | Pattern it demonstrates |
|---|---|---|
| jdrhyne, "15+ Agent Army Running Across 3 Machines" | Fleet clearing email, reviewing decks, building CLI tools, optimizing Google Ads, drafting posts and orchestrating Codex workers across a Discord-driven agent fleet | Multi-agent division of labour, chat as control plane, cross-machine execution |
| danpeguine, "Personal Operating System With Daily Briefings" | Timeblocking, weekly reviews from meeting notes, pre-meeting briefs, family school deadlines, calendar-conflict resolution, invoices | Personal operations as a scheduled operating loop with memory |
| georgedagg_, "Voice-Guided Production Fix While Walking the Dog" | Inspected failed Railway builds, diagnosed root cause, changed deploy configs, redeployed, fixed a design issue, submitted a PR over voice | Voice as a trigger, production mutation by an agent, human review at the end |
| dreetje, "One Chat Controlling Mail, Messages, Orders, Calls, and a Vault" | Mail, Beeper messages, orders, reminders, GitHub issues, bookmarks, voice calls, a dedicated 1Password vault | Single assistant with broad account authority and credential access |
| davekiss, "Entire Website Rebuilt From Telegram" | Notion to Astro, 18 posts migrated, DNS moved to Cloudflare, done from bed over Telegram | Long-running deliverable completed end-to-end with no laptop |
| stevecaldwell, "Family Meal Planning System Built Overnight" | Year-long meal template, aisle-sorted shopping lists, weather-aware dinner planning, reminders | Shared household workflow with a durable artifact and recurring nudges |

## 3. Showcase example matrix (one row per required post)

Table A: problem, workflow, services, agents, trigger. Table B: approvals, deliverable, value,
failure scenarios, Hutch implication. The split is for readability; each row is the same example.
All X texts are OBSERVED on 2026-10-31 from the status page's embedded payload; publish dates are
from the page metadata.

### Table A - what was done

| # | Example (published) | User problem | Workflow | Services / tools | Agents and responsibilities | Trigger / execution model |
|---|---|---|---|---|---|---|
| E1 | jdrhyne (2026-01-18) | Too much operational work across email, docs, ads, content and coding; one person cannot be in several places | Standing agent fleet plus delegated coding work; daily roll call; self-updating skills | X, GitHub, Jira, GA4, GSC, Google Ads, npm, Codex agents, Discord, Slack webhooks | 15+ named agents across 3 machines; a lead coordinating Codex workers; agents own email, deck review, ads, content, RAG/support | Always-on, chat-triggered and scheduled ("Daily roll call"); user issues intent in Discord, agents act |
| E2 | danpeguine (2026-01-17) | Calendar and priorities are chaotic; meeting notes, family deadlines and commitments are scattered | Importance-scored timeblocking; weekly review over meeting transcripts and Notion notes; briefing docs | Calendar, Notion, meeting transcriptions, health stats, RSS, X/LinkedIn trends | Personal chief-of-staff agent plus background research sub-agents; wife is a second recipient of school-test reminders | Scheduled daily brief, weekly review ritual, on-demand research; agent maintains a scoring algorithm co-developed with the user |
| E3 | georgedagg_ (2026-01-16) | Production deployment is broken and the operator is away from a laptop | Inspect Railway build logs, find root cause, fix service configs, redeploy, verify, then fix a design issue and open a PR | Railway, logs, repo/PR, voice channel | One production agent ("BigC") with deploy and repo authority; user is the reviewer | Voice-triggered while walking the dog; agent executes a multi-step remediation loop |
| E4 | dreetje (2026-01-17) | Personal admin is fragmented across mail, messages, orders, reminders, files and logins | One assistant for mail triage, Beeper messaging, ordering, reminders to Tana, GitHub issues, Places sync, PDF recaps, cost splitting, calls, email/contact search | Beeper, Gmail, Tana, GitHub, Google Places, 1Password, typeless voice, trains, Amazon/bol | One generalist personal agent; a read-only 1Password vault for logins and a separate read-write vault; group-chat impersonation | Chat/message-triggered on demand, plus standing duties ("Check my incoming mail, and remove spam") |
| E5 | davekiss (2026-01-07) | Personal site needed a full rebuild but the user would not sit at a laptop | Migrate Notion to Astro, migrate 18 posts, move DNS to Cloudflare, deploy, verify | Telegram, Notion, Astro, Cloudflare | One coding/orchestration agent acting as a delegated web team | Conversational trigger from Telegram, long-running execution; no laptop |
| E6 | stevecaldwell (2026-01-04) | Weekly family meal planning, shopping and cooking rotation is repetitive and easy to drop | Build a 2026 master meal plan, aisle-sorted lists per store, weather-aware dinner planning, recipe catalogue; morning/evening digests | Notion, weather forecast, Kroger/Costco/Lowes, digest messages | Household assistant ("Crawdad") shared by the poster and spouse; cooking rotation encoded as rules | Initial build in one chat session; ongoing scheduled digests and plan updates |

### Table B - approval, deliverable, value, failure, lesson

| # | Human approvals seen or implied | Deliverable | Why valuable (as claimed) | Failure scenarios (basis) | What a dependable local-first platform should do better |
|---|---|---|---|---|---|
| E1 | Not stated in the post; the showcase describes autonomous action. Docs later add exec approvals and standing orders (S13) | PRs, CLI tools published to npm, ads changes, drafted posts, support bot, daily roll call | One person operating like a team; "And yes - IT built most of this, just by chatting." | Fleet-wide loop or spam (S25, S1); unbounded spend from many agents (#42475); cross-agent authority leakage (#44925); no published run ledger (HYPOTHESIS for this fleet) | Per-bot budgets and concurrency caps; per-agent run receipts; a fleet view showing last run, next run, spend and failures; scoped grants rather than machine-wide authority |
| E2 | "Timeblocks tasks" and "resolves calendar conflicts" imply calendar writes; no approval detail given | Daily brief, weekly review, briefing docs, invoice drafts, school-test reminders | Turns scattered context into a daily operating ritual; family deadlines are shared | Wrong reminder time when the agent guesses the clock (#10841); double-booking from concurrent calendar writes (HYPOTHESIS); stale meeting notes reused as context (#7707 class); notification to a second person without explicit consent (HYPOTHESIS) | Deterministic Today view built from stored rows; IANA fail-closed scheduling; proposed-then-confirmed commitments; provenance on every brief line; explicit recipient consent for family notifications |
| E3 | Human tested afterwards and the PR was reviewed in the story; no pre-action approval described | Fixed Railway services and a submitted PR | Removes a production outage without a laptop; real end-to-end work, not advice | Change that breaks production with no rollback (HYPOTHESIS); secrets or logs carrying injected instructions into the model (S16, S17); agent claims success prematurely (#46755); unreviewed PR (HYPOTHESIS) | Approval bound to the exact action hash before deploy; isolated worktree per coding task; run receipt with commands, diffs and test output; rollback plan required for production mutations |
| E4 | Read-only vs read-write vault split is the only stated control; otherwise broad standing authority | Mail triage, orders, reminders, issues, PDF recap, cost split, group-chat impersonation | Replaces a personal assistant across many services; one interface | Credential exposure via prompt injection (S16, S23, CVE-2026-24764); unintended order duplicates (HYPOTHESIS); impersonation harms trust; no clear per-action audit shown | Secrets never in agent-reachable context; per-tool grants reviewed and revocable; idempotency keys on external writes (orders, messages); receipts that name the credential and action; no silent impersonation without explicit consent |
| E5 | Not stated; DNS move is a destructive external mutation | Rebuilt site, 18 migrated posts, DNS on Cloudflare | A complete deliverable from a chat thread, no laptop | Half-migrated content; DNS propagated but site broken; no rollback; lost post formatting (HYPOTHESIS except migration risk class) | Preflight checklist and dry-run; explicit destructive-action approval; versioned artifacts and diff review; post-change verification receipt; rollback plan stored with the run |
| E6 | Shared with spouse; no per-item approval described | Notion meal template for 2026, shopping lists, recipe catalogue, digests | Saves "at least an hour a week"; reduces household coordination load | Duplicate list items from repeated runs; stale weather/week mapping; spouse edits overwritten; digest fires late or on the wrong day (HYPOTHESIS for this workflow) | Shared space with explicit member grants and scoped visibility; idempotent append/update semantics on lists; deterministic week/date mapping; catch-up and missed-run visibility; owner-confirmed completion |

Note on E2: the X source's note-tweet payload is itself truncated mid-sentence ("...research
business ideas when i say"); this document does not complete the sentence.

## 4. Key patterns worth building against

P1 - Chat is the interface; a persistent runtime is the product. Every example starts with a
message (Telegram, Discord, voice, iMessage) but the value comes from state that outlives the
chat: schedules, memory files, plans, artifacts (S1, S2, S7). Hutch implication: treat chat as
one client of durable state, never as the state.

P2 - Scheduling is the load-bearing feature. Daily briefs, weekly reviews, morning/evening
digests and plan reminders recur across E1, E2 and E6. OpenClaw needed a whole release,
2026.8.1, to unify them under Automations and to separate ran/delivered/completed states (S12).
Hutch implication: scheduler correctness and run history are product surface, not plumbing.

P3 - Human approval is per-action, not per-session. OpenClaw's standing-orders model defines
scope, triggers, approval gates and escalation rules per program (S13); the strongest real
example is the read-only vault in E4. Hutch implication: approval must bind to the action being
taken (hash, parameters, target), not to the conversation that spawned the agent.

P4 - Deliverables are artifacts, not chat text. The examples produce PRs, a rebuilt site, a
Notion plan, PDF recaps, invoiced drafts, npm packages and decks. The delivery docs show why:
delivery is a separate state from execution, with confirmed/unknown outcomes (S10). Hutch
implication: every run should end in a named artifact or an explicit no-artifact outcome.

P5 - Multi-agent division of labour works when roles and authority are explicit. E1 (15+
agents), E4 (one generalist plus vault split) and the community's 4-agent founder setup (S1)
all name responsibilities. OpenClaw's docs add routing, bindings and per-agent tool policy.
Hutch implication: roles without per-role authority are decoration.

P6 - Memory must have provenance or it becomes a liability. OpenClaw memory is plain Markdown in
a workspace (S14), which is inspectable and local-first, and the project's own issue tracker asks
for memory trust tagging by source to stop memory poisoning (#7707). Hutch implication: fact
memory separated from instructions, with source and observed date, is the right shape; auto-memory
without provenance is not.

P7 - Fleets need a roll call. E1's "daily roll call across 10+ agents" is an operator need in
disguise: which agent is alive, what did it do, what is next. Hutch implication: a per-bot status
line (last run, next run, spend, failures) is worth more than another agent type.

P8 - Authority should be captured at creation and revalidated at run. OpenClaw's 2026.8.1 release
states that connected tools keep only the authority captured when the automation was created or
reauthorized, checked against current policy and availability each time it runs (S12, VERIFIED).
Hutch implication: scheduled work must re-check grants and permissions at execution time.

P9 - Unknown is a first-class outcome. OpenClaw delivery records Not delivered for a rejection and
Unknown for a lost/timed-out response, and does not retry ambiguous sends (S10). That is better
than most products' "success" optimism. Hutch implication: expose unknown/uncertain states in the
UI instead of collapsing them into failed or done.

P10 - Family workflows are multi-owner by default. E2 notifies a spouse; E6 is co-owned with a
spouse; E1 mentions a 3-machine fleet. OpenClaw explicitly says its multi-user features are
"usability features, not security boundaries" (S24). Hutch implication: shared spaces need real
scoping (who sees which commitment, which bot has which grant), not just shared chat.

P11 - Coding orchestration means delegating to coding agents, not reimplementing them. E1
"orchestrates Codex agents for coding"; OpenClaw ships Codex and OpenCode harness docs (S19) and
delegates to ACP/Pi-style runtimes; Pi calls OpenClaw a real-world integration and says it
deliberately skips sub-agents and plan mode (S18). Hutch implication: supervise existing coding
CLIs with briefs, worktrees, approvals and receipts rather than building a second coding loop.

P12 - Self-extension is a feature and an attack surface. E1's agent builds its own skills;
OpenClaw's marketplace ships security audits (S1); a bundled hook could silently swap the agent's
system prompt (#8776), and a skill injected untrusted issue bodies into sub-agents (#45740).
Hutch implication: self-authored skills need review, signing and a trust boundary before they can
widen tool access.

## 5. What "shipped deliverable" looks like in this sample

Observed artifact types across the six posts: a production fix plus PR (E3); a rebuilt personal
site with DNS cutover (E5); a durable Notion plan and recurring lists (E6); a daily/weekly
briefing package (E2); PRs, npm CLI tools, ad changes and drafted posts (E1); mail/order/reminder
side effects with a vault (E4). None of the public posts shows the verifying evidence a platform
would need: command output, diff, send confirmation, delivery receipt or rollback. That gap is
HYPOTHESIS, not an accusation: the posts are short social proof, and the platform should not be
judged by them. It is nevertheless the exact gap a dependable local-first platform can own.

## 6. Demand reality check (details in COMPETITIVE-ANALYSIS.md and FAILURE-ANALYSIS.md)

- Hype vs usage: an April 2026 "Who is using OpenClaw?" HN thread drew 229 upvotes and 267
  comments in seven hours; coverage noted ~350,000 GitHub stars while top replies described
  personal automation and one user's "just handy" verdict (S20, OBSERVED news summary).
- Cost sensitivity: the same coverage reports a user spending about $3.50/day (~$100/month) and
  concluding it "wasn't worth that" (S20, COMPLAINT as relayed by the article).
- Recurring automation is the hardest part in the field, not the demo: a widely shared community
  write-up lists flaky repeat automation, setup friction, memory pollution, persona drift, cost
  spikes when stuck, and marketplace trust as the repeated complaints (S21, COMPLAINT aggregate).
- Independent complaint data puts OpenClaw at the top of the security-risk and ethics/misuse
  categories among measured agents (S22, OBSERVED study by a competitor; see caveats).

## 7. Research gaps and hypotheses to test in-product

- HYPOTHESIS H1: users will pay for reliability of recurring personal operations (correct time,
  no duplicates, visible completion) more readily than for another agent capability.
- HYPOTHESIS H2: family/shared workflows fail mainly at consent and visibility boundaries, not
  at model quality.
- HYPOTHESIS H3: the winning coding-orchestration UX is a queue of reviewed briefs with
  worktree isolation and receipts, not a faster chat.
- Gap G1: no public OpenClaw showcase page reports a failed or rolled-back workflow; the only
  failure evidence is in docs, issues and community posts, which is a selection effect.
- Gap G2: no verifiable public data on how many showcase workflows still run 30/90 days later.
- Gap G3: X/Twitter remains the weakest source type here; all six required posts were readable
  from status pages on 2026-10-31, but one is truncated at source and all are self-selected.

## Sources cited in this file

| ID | Source | URL | Published / observed | Access | Tag |
|---|---|---|---|---|---|
| S1 | OpenClaw showcase | https://openclaw.ai/showcase | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S2 | jdrhyne X post | https://x.com/jdrhyne/status/2012778049406742632 | published 2026-01-18 | 2026-10-31 | OBSERVED |
| S3 | danpeguine X post | https://x.com/danpeguine/status/2012565160586625345 | published 2026-01-17 | 2026-10-31 | OBSERVED |
| S4 | georgedagg_ X post | https://x.com/georgedagg_/status/2012119327147798753 | published 2026-01-16 | 2026-10-31 | OBSERVED |
| S5 | dreetje X post | https://x.com/dreetje/status/2012535486401671588 | published 2026-01-17 | 2026-10-31 | OBSERVED |
| S6 | davekiss X post | https://x.com/davekiss/status/2008994096736817624 | published 2026-01-07 | 2026-10-31 | OBSERVED |
| S7 | stevecaldwell X post | https://x.com/stevecaldwell/status/2007616854689280196 | published 2026-01-04 | 2026-10-31 | OBSERVED |
| S8 | How automations work | https://docs.openclaw.ai/automation/cron-jobs/how-it-works.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S9 | Automation schedules | https://docs.openclaw.ai/automation/cron-jobs/schedules.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S10 | Automation delivery | https://docs.openclaw.ai/automation/cron-jobs/delivery.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S11 | Automation troubleshooting | https://docs.openclaw.ai/automation/cron-jobs/troubleshooting.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S12 | v2026.8.1 release notes | https://docs.openclaw.ai/releases/2026.8.1/automations-and-scheduling.md | release 2026.8.1 | 2026-10-31 | VERIFIED |
| S13 | Standing orders | https://docs.openclaw.ai/automation/standing-orders.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S14 | Memory overview | https://docs.openclaw.ai/concepts/memory.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S15 | Audit records CLI | https://docs.openclaw.ai/cli/audit.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S16 | Promptfoo, "OpenClaw at Work: Prompt Injection Risks" | https://www.promptfoo.dev/blog/openclaw-at-work/ | published 2026-03-12 | 2026-10-31 | OBSERVED |
| S17 | OpenClaw prompt-injection doc | https://docs.openclaw.ai/gateway/security/prompt-injection.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S18 | Pi coding agent | https://pi.dev/ | observed 2026-10-31 | 2026-10-31 | OBSERVED |
| S19 | OpenClaw docs index (Codex/OpenCode/ACP) | https://docs.openclaw.ai/llms.txt | observed 2026-10-31 | 2026-10-31 | VERIFIED |
| S20 | The Agent Times, "OpenClaw's 350K GitHub Stars..." | https://theagenttimes.com/v1/articles/openclaw-s-350k-github-stars-haven-t-answered-our-hardest-qu-9e0718e6 | published 2026-04-16 | 2026-10-31 | OBSERVED |
| S21 | OpenClaw Unboxed, "is openclaw all hype?" | https://openclawunboxed.com/p/is-openclaw-all-hype | published 2026-02-26 | 2026-10-31 | COMPLAINT |
| S22 | OpenChamber, "A year of AI coding complaints" | https://openchamber.dev/blog/ai-coding-complaints/ | published 2026-09-21 | 2026-10-31 | OBSERVED |
| S23 | OpenClaw security doc | https://docs.openclaw.ai/gateway/security.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S24 | OpenClaw multi-user doc | https://docs.openclaw.ai/concepts/multi-user.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S25 | OpenClaw bot loop protection | https://docs.openclaw.ai/channels/bot-loop-protection.md | current Oct 2026 | 2026-10-31 | VERIFIED |
| S26 | OpenClaw issue #10841 (wrong reminder times) | https://github.com/openclaw/openclaw/issues/10841 | opened 2026-02-07, closed | 2026-10-31 | VERIFIED |
| S27 | OpenClaw issue #7707 (memory trust tagging) | https://github.com/openclaw/openclaw/issues/7707 | opened 2026-02-03, closed | 2026-10-31 | VERIFIED |
| S28 | OpenClaw issue #44925 (lost subagent results) | https://github.com/openclaw/openclaw/issues/44925 | opened 2026-03-13, open | 2026-10-31 | VERIFIED |
| S29 | Claude Code issue #46755 (false completion) | https://github.com/anthropics/claude-code/issues/46755 | opened 2026-04-11, closed | 2026-10-31 | VERIFIED |
| S30 | OpenClaw issue #8776 (soul-evil hijack hook) | https://github.com/openclaw/openclaw/issues/8776 | opened 2026-02-04, closed | 2026-10-31 | VERIFIED |
| S31 | OpenClaw issue #45740 (untrusted issue body injection) | https://github.com/openclaw/openclaw/issues/45740 | opened 2026-03-14, closed | 2026-10-31 | VERIFIED |
| S32 | CVE-2026-24764 / GHSA-782P-5FR5-7FJ8 advisory | https://vulnerability.circl.lu/vuln/brew-openclaw-cli-cve-2026-24764 | published 2026-08-13, updated 2026-10-29 | 2026-10-31 | VERIFIED |
| S33 | OpenClaw issue #42475, per-agent cost budgets | https://github.com/openclaw/openclaw/issues/42475 | opened 2026-03-10, open | 2026-10-31 | VERIFIED |
