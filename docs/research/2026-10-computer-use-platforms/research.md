# Computer-use platforms: grounding, failure modes, safety patterns, triggers, remote operation

**Prepared:** 2026-10-31 · **Purpose:** input to Hutch engineering decisions · **All sources accessed:** 2026-10-31.

## How claims are labelled

| Label | Meaning |
| --- | --- |
| `verified` | I read the primary source and it states this. Numbers I computed from a primary dataset are marked `verified (computed)`. |
| `vendor claim` | A vendor's docs or marketing assert it; not independently demonstrated. |
| `anecdote` | A user or researcher report; not reproduced by me. |

No vendor benchmark number below is treated as evidence of production reliability. Every `S#` reference resolves to an exact URL with its access date in the ledger (§9).

## 1. Findings that should change decisions

1. **The DOM/accessibility-tree versus pixel debate is settled differently for web and desktop.** Anthropic's browser tool prefers element references "where the page has a usable accessibility tree" and falls back to coordinates, and says a tree read "often costs fewer input tokens than a screenshot" (`vendor claim`, S2). But on OSWorld's official verified leaderboard, 142 of 144 scored entries are marked as using no additional accessibility tree, and every one of the top 12 entries is in that group (`verified (computed)`, S23). Desktop SOTA today is screenshot-grounded, not tree-grounded; web is where trees pay.
2. **Step budget is a first-order success variable, not a tuning detail.** On the same leaderboard, entries run at 15 steps average 28.9% success, at 50 steps 41.6%, at 100 steps 53.8% (max 90.2) (`verified (computed)`, S23). A hard step cap is therefore a direct quality/cost dial, and a low cap silently converts hard tasks into failures.
3. **Vendor web benchmarks overstate field reliability by roughly 2x.** OpenAI published 87% on WebVoyager for CUA (`vendor claim`, S9); independent human evaluation on 300 live tasks measured Operator at 61.3% and Claude Computer Use at 29.0% (`verified`, S26). The independent authors state their results "suggest over-optimism in previously reported results."
4. **Failure is expensive before it is visible.** On failed tasks, agents take "nearly twice as many steps" as on successful ones, "primarily due to repeated actions or unexpected pop-up windows" (`verified`, S26). Operator's trajectories there exceeded 100 screenshots and ran "up to 44 minutes for challenging tasks."
5. **Screenshots dominate token cost.** Anthropic documents 1,000–1,800 input tokens per screenshot and about 4,500 input tokens of toolset definition overhead (6,600 for the browser toolset) (`verified`, S1, S2). A 100-step loop is therefore ~100k–180k image tokens before any reasoning text: at Anthropic's published input prices that is roughly $0.20–$0.72 per run for the image stream alone ($2/MTok on Sonnet 5.5, $4/MTok on Opus 5.5), before output tokens or retries (`verified` arithmetic, S7).
6. **Confirmation gates are the best-evidenced mitigation and they are imperfect.** OpenAI measured 92% recall for asking confirmation on risky actions across 607 tasks (`verified`, S10) — i.e. roughly 1 in 12 risky actions proceeds without asking. Anthropic calls human-in-the-loop "the single most effective mitigation against prompt injection" (`vendor claim`, S3). Both are arguments for a deterministic gate in the harness, not a prompt instruction.
7. **Provider availability is an unattended-run failure mode with a measurable rate.** Anthropic's status feed returned 50 incidents between 2026-08-05 and 2026-10-28: 2 critical, 24 major, 21 minor (`verified (computed)`, S57). Any cron-triggered run will sometimes land inside one.
8. **Webhook delivery is at-least-once, unordered, and silently lossy.** Anthropic: three attempts with jittered backoff, then "the event is dropped… there's no signal that it was lost", plus duplicates and no ordering (`verified`, S6). GitHub: receivers must answer within 10 seconds or the delivery counts as failed (`verified`, S59). A trigger design that assumes exactly-once or ordering is wrong at the protocol level.
9. **Allowlists are a parsing problem before they are a policy problem.** browser-use's `allowed_domains` was bypassable because userinfo can be placed in the URL authority (CVE-2025-47241) (`verified`, S41). Anthropic's own guidance is to enforce host allowlists "at the network layer and re-checked in your `navigate` handler after redirects", parsing with a URL parser rather than string prefixes (`verified`, S2).
10. **Hutch's desktop path matches where the field actually is; its browser path is leaving value on the table.** Hutch has no AT-SPI semantic adapter at HEAD (`verified`, `docs/computer-use.md`), which is consistent with pixel-first desktop SOTA. Its browser observation returns a "value-free list of visible interactive elements" but no addressable element references, which is exactly the capability Anthropic, Playwright MCP and WebArena all build on (S2, S15, S24). Note: the working tree also contains uncommitted accessibility modules (`src/hutch/computer/accessibility.py`, `src/hutch/computer/native/a11y_bus.py`) that I did not review; see §8.

## 2. Grounding: what each platform observes and acts on

### 2.1 Vendor surfaces

Every cell in this table is drawn from the named vendor's own documentation, so read each as `vendor claim` unless a stronger label appears inline (the quoted numbers are vendor-reported, not independently reproduced).

| Platform | Observation space | Action space | Safety hooks the vendor ships | Vendor's own reliability language |
| --- | --- | --- | --- | --- |
| Anthropic computer use toolset (`computer_toolset_20260801`) | Screenshots; coordinates in the pixel space of the screenshot you return | 17 member tools (screenshot, zoom, click, type, key, scroll, drag, wait); batches of several calls per turn | Prompt-injection classifiers on tool results, default on; app-side validation and logging guidance | "might make mistakes or hallucinate when outputting specific coordinates"; latency "might be too slow" for human-speed work (S1) |
| Anthropic browser use toolset (`browser_toolset_20260801`) | `read_page` accessibility tree with `[ref_N]` tags (≤50,000 chars), `find`, `get_page_text`, screenshots, zoom | 31 members; `target` is either `{type:"ref"}` or viewport pixels; optional `javascript_exec`, `file_upload`, console/network reads (off by default) | Same classifiers; explicit network-allowlist and scheme-validation guidance; "human confirm consequential actions" | References "best-effort"; dynamic pages fall back to coordinates; "the API can't detect a stale or unknown reference" (S2) |
| OpenAI CUA / Operator | Raw pixels ("processes raw pixel data"); virtual mouse and keyboard | Click, scroll, type; single general action space | Trained confirmations, watch mode on sensitive sites, a separate prompt-injection monitor model, blocklists, refusals (banking, regulated) | 38.1% OSWorld, 58.1% WebArena, 87% WebVoyager; "not yet highly reliable for automating tasks on OS" (S9, S10) |
| Google Gemini computer use | Screenshots; normalized 0–1000 coordinates; per-action `intent` field | Click/type/scroll/drag family, browser, mobile and desktop environments | `safety_decision: regular / require_confirmation / blocked` from an out-of-model per-step service; opt-in screenshot injection scanning; custom safety system instruction | "primarily optimized for web browsers… not yet optimized for desktop OS-level control" (S12, S13) |

Two structural details matter for Hutch:

- Anthropic states that input bounds in its tool schemas are "stated to Claude, not enforced by the API, so validate inputs (including coordinates against your viewport)" (`verified`, S2). The harness owns validation; the model cannot be trusted to.
- Google's `safety_decision` is returned *per action*, and the documented client obligation is to prompt the user and echo `safety_acknowledgement` before executing (`verified`, S12). Confirmation is part of the action contract, not a chat turn.

### 2.2 Open-source and self-hostable

Project descriptions here are the projects' own claims about themselves (`vendor claim`) unless marked otherwise; the weaknesses column cites filed issues (`anecdote`) and advisories (`verified`).

| Project | Grounding approach | Evidence of what it buys | Notable weaknesses on record |
| --- | --- | --- | --- |
| Playwright MCP (Microsoft) | Accessibility snapshots only; "bypassing the need for screenshots or visually-tuned models"; "Deterministic tool application" (`vendor claim`, S15) | No vision model required; element-level determinism | Their own README now argues CLI+skills beat MCP for coding agents because MCP loads "verbose accessibility trees into the model context" (`vendor claim`, S15); users file snapshot size and context-burn issues (S35, S36) |
| browser-use | Hybrid: DOM extraction with indexed interactive elements plus screenshots | Widely used; pluggable models | Endless-loop and stuck-at-step-1 reports (S32, S33, S34); unbounded base64 image payloads reaching the model (S37); allowlist bypass CVE (S41); cleartext API keys on disk (S43); pause/verify human-in-the-loop had to be requested as a feature (S38) |
| Stagehand (Browserbase) | `observe()` returns real selectors; `act()` self-heals on redesign; `extract()` schema-validated (`vendor claim`, S17) | Keeps credentials out of model context by design ("credentials never reach the model") | Selector-based, so it inherits DOM assumptions; no published independent accuracy data found |
| Skyvern | Vision LLM plus Playwright; "swarm of agents" | Claims 85.8% on WebVoyager (`vendor claim`, S18) — the benchmark that independent work says overstates (S26) | SSTI in prompt fields (CVE-2025-49619) and a sandbox escape via double-rendered Jinja (CVE-2026-82447, 8.8) (S42, S44) |
| UI-TARS (ByteDance) | Pure screenshots, end-to-end model, absolute coordinates | OSWorld 24.6 at 50 steps vs Claude 22.0 at the time (`verified`, S20) | Absolute-coordinate handling is delicate enough to need its own guide (S19) |
| Open Interpreter | Not a GUI-grounding agent any more; now "a coding agent optimized for low-cost models" (S21) | Relevant as a caution: projects drift out of this category | Out of scope for grounding comparisons |

### 2.3 Accessibility tree versus pixels: what the evidence actually supports

| Claim | Evidence | Label |
| --- | --- | --- |
| References survive layout shifts that break coordinates | Anthropic: "A reference survives layout shifts and reflows that make pixel coordinates fragile" | `vendor claim` (S2) |
| Tree reads can be cheaper than screenshots | Anthropic: "a tree read of a typical page often costs fewer input tokens than a screenshot" | `vendor claim` (S2) |
| Trees go stale and the model API cannot tell | "References… stay valid until that tab navigates or its DOM changes materially. The API can't detect a stale or unknown reference"; the executor must return an error and force a re-read | `verified` (S2) |
| Trees are too big for large pages | `read_page` output is capped at 50,000 characters by the executor contract; MCP users file pagination and context-exhaustion issues | `verified` (S2), `anecdote` (S35, S36) |
| A11y-tree observation is a legitimate research baseline | WebArena used "an accessibility tree with element IDs as the observation space", e.g. `click [1582]` | `verified` (S24) |
| A11y observation does not make agents good | WebArena: best GPT-4 agent 14.41% versus human 78.24% | `verified` (S24) |
| Desktop SOTA does not use a11y trees | OSWorld verified leaderboard: 142/144 entries flagged "Additional a11y tree used: No"; the two flagged entries score 46.3 and 47.3 | `verified (computed)` (S23) |
| Grounding small targets is the hard part | ScreenSpot-Pro: best existing grounding model 18.9%; cascaded search (ScreenSeekeR) 48.1% | `verified` (S28) |
| Hutch has no native semantic layer today | Its own doc records "no AT-SPI semantic action adapter" and requires frame inspection plus outcome verification for desktop actions | `verified` (repo doc, `docs/computer-use.md`) |

**Reading.** For the browser, an accessibility snapshot with stable, invalidatable references is the highest-leverage observation upgrade available, and it is what three independent implementations converged on. For the native desktop, the field has voted with its benchmark entries: pixels plus a strong model, with zoom for small targets. Building a full AT-SPI action layer for Linux desktop apps would be a large bet against current SOTA; a read-only a11y *hint* channel is the cheaper experiment.

### 2.4 Benchmarks, with provenance and caveats

| Benchmark | What it measures | Numbers I read | Label / caveat |
| --- | --- | --- | --- |
| WebArena | Self-hosted replicas of four real sites | Best GPT-4 agent 14.41%; human 78.24% | `verified` (S24). Self-hosted, so no live-site drift |
| WebVoyager | Tasks across 15 popular live websites, GPT-4V judge | 59.1% success; judge agrees with humans 85.3% | `verified` (S25). Judge-based; later work shows judge agreement collapses on long trajectories |
| Online-Mind2Web | 300 live tasks across 136 sites, human-evaluated | Operator 61.3%, SeeAct 30.7%, browser-use 30.0%, Claude Computer Use 29.0% | `verified` (S26). The strongest independent signal here |
| OSWorld | 369 real desktop tasks, execution-based scoring | Paper-era: human 72.36%, best model 12.24%. CUA launch: 38.1%. Leaderboard today: top 90.2% | `verified` (S22, S9, S23). Leaderboard is organizer-verified submissions, not a controlled study |
| TheAgentCompany | Simulated software company, professional work tasks | "The most competitive agent can complete 30% of tasks autonomously" | `verified` (S27) |
| ScreenSpot-Pro | GUI grounding on high-resolution professional screens | Best model 18.9%; ScreenSeekeR 48.1% | `verified` (S28) |

The consistent picture: web navigation on curated sites is roughly 60% for the best agent and ~30% for everything else; open-ended desktop work is far worse; grounding small targets in high-resolution screens is the weakest link in the stack.

### 2.5 Set-of-mark, OmniParser, and serialization write-ups

- **Set-of-Mark** overlays segmentation regions with alphanumeric marks so an LMM can name a region instead of emitting coordinates; it reports that GPT-4V with SoM beats a fully fine-tuned referring-expression model on RefCOCOg (`verified`, S29). The mechanism is "turn coordinates into discrete symbols".
- **OmniParser** trains an interactable-region detector plus an icon-caption model to convert a screenshot into structured elements; it improves GPT-4V on ScreenSpot and, per Microsoft's v2 post, OmniParser+GPT-4o reaches 39.6 average on ScreenSpot-Pro versus GPT-4o's original 0.8 (`verified` abstract S30; `vendor claim` S31). Even the improved number means roughly 6 in 10 high-resolution targets are still missed.
- **Anthropic's counter-evidence matters.** In their own testing, splitting screenshots into tiles and "overlaying a grid pattern with coordinates" "did not produce reliable gains" for click accuracy (`vendor claim`, but a test report rather than marketing, S3). SoM-style marking is not a free win on every model; it is a model-specific prompting trick.
- **Accessibility serialization** in practice: Playwright MCP emits an a11y snapshot per action (S15); Anthropic emits `role "name" [ref_N]` lines and lets the model click by ref (S2); WebArena emits element IDs from a pruned DOM (S24). All three cap output size; none of them ship the raw DOM, and Anthropic explicitly warns to build reads "from what the page renders… not raw DOM source, so hidden text doesn't reach Claude" (`verified`, S2) — a prompt-injection control disguised as an observation choice.

## 3. Failure modes users actually report

| Symptom | Primary evidence | Label | What it tells a harness designer |
| --- | --- | --- | --- |
| Loops and repeated actions | browser-use #951 "Task stuck in endless loop"; #1137 "Stuck on Stage 1" repeating forever; #839 only unblocks when a human types in the address bar | `anecdote` (S32–S34) | Loops are often *harness* bugs (stale page handle, no progress detection), not model bugs. Needs a no-progress detector, not a better prompt |
| Step inflation on failure | Failed tasks take "nearly twice as many steps", "primarily due to repeated actions or unexpected pop-up windows" | `verified` (S26) | Cost per failed run is structurally higher than cost per success; budgets must assume the failure case |
| Mis-clicks and coordinate drift | Anthropic's diagnostic table: uniform offset = coordinates applied to a differently sized display; DPI 2x on Retina; 4K downscaled to 720p turns a 16 px checkbox into ~5 px | `verified` (S1, S3) | Every observation must carry the exact transform used, and the dispatch layer must invert it |
| Native-resolution screenshots | "sending native resolution screenshots is the most common cause of poor click accuracy" | `vendor claim` (S3) | Bigger images are worse, not better, past the model's limit |
| Stale screenshots or references | Anthropic: refs invalid after navigation/DOM change, API can't detect it; Hutch: actions are only accepted "against the latest frame" | `verified` (S2), `verified` (repo doc) | Staleness must be a typed error the model can recover from, not a silent retry |
| CAPTCHA and login walls | browser-use #652 asks for Capsolver integration; Skyvern #9101 asks for OCR on image CAPTCHAs; Google lists "bypassing CAPTCHAs" among actions its safety layer blocks | `anecdote` (S39, S40), `verified` (S13) | Two opposite pressures: users want circumvention; vendors treat it as a blocked category. Hutch's `waiting_human` park is the defensible middle |
| Agents clicking destructive controls | OpenAI's own risk framing: "purchasing the wrong item… permanently deleting an important document"; trained confirmations catch 92% of risky actions, not 100% | `verified` (S9, S10) | A deterministic pre-dispatch gate on destructive verbs/targets is required; model willingness is a second layer |
| Runaway token and cost spend | 1,000–1,800 tokens per screenshot; 100-step loops; browser-use #5367 forwards unbounded base64 images | `verified` (S1), `anecdote` (S37) | Bound payload size at the boundary, not in the prompt |
| Prompt injection via page content or documents | Anthropic separates direct injection (user is the adversary) from indirect injection (trusted user, hostile third-party content) (S4); its classifiers are on by default for official tools only (S1, S3); OpenAI measured 23% susceptibility after mitigation, from 62% unmitigated (S10); a researcher demo got Claude Computer Use to download and run a binary from a malicious page (S45) | `verified` (S1, S3, S4, S10), `anecdote` (S45) | Model-side defences are probabilistic; scope and confirmation are the load-bearing controls |
| Unattended runs that die silently | Provider status feeds: Anthropic 50 incidents in ~12 weeks (2 critical, 24 major); OpenAI 25 incidents in 23 days (4 major) | `verified (computed)` (S57, S58) | Scheduling needs retry-with-jitter, a liveness signal, and a "run produced nothing" alert |
| Silent input loss in long sessions | browser-use #5469 reports key/mouse events "silently dropped in a long-lived session" | `anecdote` (S46) | Long-lived browser contexts need per-action acknowledgement, not fire-and-forget |

Two patterns recur across every source: (a) the model is rarely the only cause — missing progress detection, unvalidated coordinates and unbounded payloads amplify model error into run failure; (b) the failures that hurt are the ones that produce no error, only a wrong end state.

## 4. Secure design patterns with evidence behind them

| Pattern | Strongest evidence I found | Label | Limits worth knowing |
| --- | --- | --- | --- |
| Host/domain allowlists | Anthropic: enforce "at the network layer and re-checked in your `navigate` handler after redirects", block loopback/link-local/private ranges, parse schemes with a URL parser | `verified` (S2) | browser-use's allowlist was bypassed via userinfo in the authority (CVE-2025-47241, CVSS 4.0) — string-prefix checks fail (S41) |
| Frame/iframe-scoped allowlists | browser-use cloud docs: `secretBindings.allowedDomains` authorizes "the focused field's frame, not every iframe on the page" | `vendor claim` (S16) | Tells you allowlists must be scoped to the execution context, not the tab |
| Confirmation before irreversible actions | OpenAI: confirmations reduce risk by ~90%, 92% recall on 607 risky tasks; Anthropic: "single most effective mitigation"; Google: per-action `require_confirmation` decision | `verified` (S10), `vendor claim` (S3), `verified` (S12) | Recall is not 1.0. "One turn can carry several" actions, so the check must be per call, in the executor (S2) |
| Sandboxing: VM or dedicated container | Anthropic: "dedicated container or virtual machine with minimal privileges, a fresh profile that holds no credentials"; Google: "sandboxed VM or container… reference implementation includes a Docker-based sandbox" | `verified` (S2, S12) | A sandbox is not a security boundary against a hostile compositor or a template engine; Skyvern's sandbox escape (CVE-2026-82447, 8.8) came from double-rendering a prompt template (S42) |
| Egress control | Anthropic Managed Agents: "limit the network", `web_fetch` domain list, credentials in vaults, "model behavior is not a security control" | `verified` (S5) | The doc concedes limits "do not remove" risk: an agent can still exfiltrate what it is allowed to read via its reply |
| Credential minimalism | Stagehand: `observe()` returns selectors so "credentials never reach the model"; Anthropic: MCP credentials never enter the sandbox, env-var credentials appear as placeholders | `vendor claim` (S17), `verified` (S5) | Placeholders still authorize use; scope the credential at the issuer |
| Per-action audit trail | Anthropic: "log actions for debugging" with action, params, result; Hutch already emits action receipts and `computer_control` events | `vendor claim` (S1), `verified` (repo doc) | Terminal/screen recording is weaker than it looks — see below |
| Session recording as audit | Teleport records "the entire pseudo-terminal (PTY) output"; Teleport itself warns users "can conceal terminal commands by encoding them (e.g., using base64)" and points to BPF-based recording | `verified` (S54) | Recording captures pixels, not intent. Structured action receipts plus postcondition checks are the better primary record |
| Cancellation and human takeover | OpenAI "watch mode" on sensitive sites; Anthropic recommends human confirmation; Hutch implements a generation-fenced control lease | `verified` (S9), `verified` (repo doc) | Takeover must fence in-flight actions, not just future ones (Hutch's ticket re-check is the right shape) |
| Spend and scope bounds | Anthropic ships a Spend Limits API and rate limits; smallest-tool-set guidance; model choice changes cost per task by ~10x at equal score | `verified` (S5, S8), `vendor claim` (S3) | Spend limits bound money, not blast radius; scope needs its own control |

**Where a vendor explicitly says a capability is unsupported or unsafe**

- Anthropic: the computer-use toolset "isn't currently available in Claude Managed Agents"; the API does not downscale oversized screenshots for the toolset — it rejects them (`verified`, S1).
- Anthropic: prompt-injection classifiers do **not** run when you define your own computer/browser tools (`verified`, S3). If Hutch defines custom tools (it does), it gets no classifier coverage and should not plan around it.
- Anthropic: "model behavior is not a security control"; sandbox settings "lower the risk but do not remove it"; and they "do not secure your custom tools, your MCP servers, or your self-hosted infrastructure" (`verified`, S5).
- OpenAI: CUA "will decline to help with certain higher-risk tasks, like banking transactions", and OSWorld performance "indicat[es] that the model is not yet highly reliable for automating tasks on OS; human oversight is recommended" (`verified`, S9, S10).
- Google: the model is "primarily optimized for web browsers" and "not yet optimized for desktop OS-level control"; CAPTCHA bypass is treated as a prohibited action category (`verified`, S12, S13).
- Playwright MCP's own maintainers now recommend a CLI over MCP for coding agents because of context cost (`vendor claim`, S15).

## 5. Triggers and scheduling

### 5.1 What a correct webhook receiver must do

| Requirement | Primary source | Label |
| --- | --- | --- |
| Verify an HMAC over the **raw** request bytes (GitHub: `X-Hub-Signature-256`, `sha256=` prefix; Anthropic: `webhook-signature` with `whsec_` secret) | GitHub: "compare the hash that GitHub sent with the expected hash"; Anthropic's TS sample warns to use `express.raw()`, "the signature is computed over raw bytes" | `verified` (S47, S6) |
| Reject stale deliveries | Anthropic's `unwrap()` "throws if the signature is invalid or the payload is more than 5 minutes old" | `verified` (S6) |
| Deduplicate on a stable event ID | Anthropic: "An endpoint can receive the same event more than once… Deduplicate on it"; GitHub: use `X-GitHub-Delivery`, and note redelivery reuses the same ID | `verified` (S6, S59) |
| Acknowledge fast, then process | GitHub: respond 2xx "within 10 seconds"; otherwise the delivery counts as a failure; queue asynchronously | `verified` (S59) |
| Do not trust event ordering | Anthropic: events "aren't guaranteed to be delivered in the order they occurred"; "drive your state from the resource you fetch" | `verified` (S6) |
| Expect loss and reconcile | Anthropic: after three attempts "the event is dropped… there's no signal that it was lost"; "webhooks aren't a durable log" | `verified` (S6) |
| Subscribe before you need an event type | Anthropic: "An event emitted while no endpoint is subscribed to its type is never delivered… subscribing later doesn't backfill it" | `verified` (S6) |
| Pin the sender network | GitHub: "set up an IP allow list… use the GET /meta endpoint"; Anthropic auto-disables endpoints whose URL resolves to a non-public IP | `verified` (S59, S6) |

### 5.2 Cron and timers: the failure modes are documented, not hypothetical

- **Missed windows across suspend.** systemd: calendar timers that elapse while the machine sleeps "will not be acted on immediately" but are caught up on resume — and "if a calendar timer elapsed more than once while the system was continuously sleeping the timer will only result in a single service activation" (`verified`, S48). Classic cron's behaviour after downtime is implementation-specific and was not verified here; systemd's `Persistent=` is the explicit catch-up mechanism.
- **Catch-up requires opt-in.** `Persistent=true` stores the last trigger time on disk and fires once on activation "if it would have been triggered at least once during the time when the timer was inactive" (`verified`, S48).
- **Coalescing is on by default.** `AccuracySec` defaults to 1 minute specifically to coalesce CPU wake-ups, so a "9:00" timer may run at 9:00:59 (`verified`, S48).
- **Thundering herd.** `RandomizedDelaySec` exists "to stretch elapsing of timer events over a longer period to reduce workload spikes" (`verified`, S48); AWS's builders' library documents why retries without backoff and jitter amplify overload (`verified`, S50).
- **Hosted schedulers are best-effort too.** GitHub Actions `schedule`: runs "can be delayed during periods of high loads… If the load is sufficiently high enough, some queued jobs may be dropped", the minimum interval is 5 minutes, and scheduled workflows in public repos are disabled after 60 days of no repository activity (`verified`, S49).

### 5.3 Failure-mode summary for triggers

| Failure | Mechanism | Mitigation that has evidence |
| --- | --- | --- |
| Duplicate fire | At-least-once delivery; redelivery reuses IDs | Idempotency key on event ID + a durable "already handled" ledger (S6, S47) |
| Missed window | Suspend, downtime, scheduler load-shedding | `Persistent`-style catch-up plus a reconcile-by-polling path; do not treat the trigger as the source of truth (S48, S6) |
| Thundering herd | Many bots firing on the same boundary | `RandomizedDelaySec`-style jitter and per-target concurrency caps (S48, S50) |
| Silent loss | Retry exhaustion with no signal | Alert on expected-event-not-seen; reconcile from the resource API (S6) |
| Slow receiver | Processing inline past the sender's timeout | Ack immediately, enqueue, process out of band (S47) |

File-watch (inotify/fanotify) failure modes were **not** verified in this pass; see §8.

## 6. Remote computer and Linux server operation

| Product | How the agent reaches the remote host | Security posture stated in the docs | Label |
| --- | --- | --- | --- |
| GitHub Copilot coding agent | Three environments: cloud sandbox, GitHub Actions runner, or "Remote (a connection to a custom environment)" | Cloud sandboxes "honor repository and organization firewall allowlists"; Actions-based sessions can only change the one repository | `verified` (S55) |
| OpenAI Codex Cloud | A published per-task environment; "Each task has its own workspace" | "network secrets for allowed HTTPS services and limit the environment's network destinations" | `vendor claim` (S56) |
| Teleport | Identity-aware proxy in front of SSH nodes | Short-lived certificates, RBAC from SSO, session recording; recording is PTY-level and concealable, with BPF-based recording as the stronger option | `verified` (S54) |
| HashiCorp Vault SSH secrets engine | CA-signed SSH certificates | Clients "SSH into target hosts using their own local SSH keys" with a short-lived signed certificate instead of a shared key | `verified` (S53) |
| OpenSSH primitives | — | `AllowUsers` accepts `USER@HOST` patterns; `ForceCommand` "ignoring any command supplied by the client… most useful inside a Match block"; `TrustedUserCAKeys` supports CA-based auth | `verified` (S52) |

**Key-handling rules with primary backing**

- Do not forward an agent. `ssh_config`: "Agent forwarding should be enabled with caution. Users with the ability to bypass file permissions on the remote host… can access the local agent through the forwarded connection" (`verified`, S51). An agent host that can be prompt-injected must never hold a forwarded agent socket.
- Prefer short-lived certificates to long-lived keys, with the CA online and the private key never on the agent host (S53, S52).
- Pin hosts. Host-key verification against a known-hosts file is the only thing that distinguishes "the server I approved" from "a server that answered"; pair it with a per-bot host allowlist checked before the connection is attempted (S52).
- Constrain the session even after auth: `ForceCommand` inside a `Match` block turns an arbitrary shell into a fixed entrypoint (`verified`, S52).
- Record, but do not over-trust the recording: PTY capture cannot see intent, and Teleport says so itself (S54).

**Gap in the public record.** I did not find a vendor document that describes letting a general computer-use agent SSH into arbitrary customer hosts *with* a threat model; the mature products either give the agent its own ephemeral environment (Codex, Copilot cloud) or front the host with an identity-aware proxy (Teleport). That absence is itself a finding: remote-host execution for agents is currently assembled from SSH/PAM primitives, not sold as a solved pattern.

## 7. What this means for Hutch

Ranked by value-to-cost. Each item names the subsystem it extends.

1. **Add a per-route observation normalization step with an explicit transform, and fix the frame ceiling per provider.** Evidence: 1,000–1,800 tokens per screenshot and hard image limits (S1); "native resolution… is the most common cause of poor click accuracy" and uniform-offset clicks mean unscaled coordinates (S3). Hutch currently fixes `transform: {scale: 1.0}` in the observation record and caps frames at `MAX_FRAME_EDGE = 2000` with the comment "provider limits are higher" (`verified`, `src/hutch/computer/frames.py`, `desktop.py`) — but Anthropic's published limit for the 4.6 family is 1568 px / 1.15 MP, i.e. *lower* than 2000. Extends: `FrameStore`, the provider boundary image conversion, and the action-receipt transform. Cost: small; it removes a silent coordinate-offset failure class, and the only new risk is a resize step that itself must be recorded and tested.
2. **Give the browser tool an accessibility-snapshot observation with addressable refs and a typed stale-ref error.** Evidence: three independent implementations converged on refs (S2, S15, S24); refs survive reflow where coordinates do not (`vendor claim`, S2); refs invalidate on navigation and the executor must say so (S2). Hutch already returns a value-free list of visible interactive elements — this is the same data plus role, name, and a stable handle. Extends: `browser observe` / semantic actions / `ApprovalGate` candidate lists. Cost: medium; risk: output size, so cap characters and scope by subtree exactly as Anthropic does (50,000 chars, `filter: "interactive"`).
3. **Move confirmation from prompt to pre-dispatch gate for irreversible actions, and make it per action rather than per turn.** Evidence: 92% recall from trained confirmations, not 100% (S10); "one turn can carry several" actions (S2); Google's per-action `safety_decision` contract (S12); Anthropic calls HITL the single most effective mitigation (`vendor claim`, S3). Concretely: a consequential-target classifier over button labels/roles/URLs (`send`, `submit`, `buy`, `delete`, `confirm`, payment hosts) that forces an approval even when a sticky rule would allow the tool. Extends: `ApprovalGate` (outward actions are already never sticky — keep that) and action receipts. Cost: low-medium; risk: approval fatigue if the classifier is noisy, so log precision.
4. **Make step and token budgets first-class, enforced before dispatch, with a no-progress detector.** Evidence: OSWorld success rises 28.9% → 41.6% → 53.8% across 15/50/100-step budgets (`verified (computed)`, S23); failed runs take ~2x the steps (S26); loops are frequently harness-level (S32–S34). Extends: `computer/budgets.py`, the two-second watchdogs, and the scheduler's per-run capacity. Cost: low; risk: a budget that is too low converts hard tasks into failures — expose it per bot and record the exhaustion reason in the run event.
5. **Build event triggers as a separate source type with signature verification, replay window, idempotency ledger, and async ack.** Evidence: GitHub's 10-second ack and `X-GitHub-Delivery` replay guidance (S59); Anthropic's 5-minute freshness, duplicates, unordered delivery, drop-after-3-attempts (S6). Do not reuse the cron path unmodified: cron has no event identity and no dedupe requirement. Extends: the scheduler (`croniter` + IANA tz + catch-up already exists) with an event-source abstraction, plus a `trigger_events` table keyed by `(source, event_id)`. Cost: medium; risk: a webhook endpoint is a new internet-facing surface — bind it to the existing private HTTPS deployment and require a per-bot secret.
6. **Design remote-host execution as a grant with a host allowlist and no long-lived key on the agent host.** Evidence: `AllowUsers user@host` and `ForceCommand`/`Match` (S52); Vault-signed short-lived certs (S53); ForwardAgent's explicit warning (S51); Teleport's recording caveat (S54). Shape: per-bot `remote_hosts` grant, pinned host keys, certificate TTL bounded by the run's lease, all commands through a fixed entrypoint, every invocation recorded as a run event. Extends: resource grants, `ApprovalGate`, run events, and the existing "changed grant requires a new run" rule. Cost: high; risk: this is the largest new trust boundary in the list — sequence it after 1–4.
7. **Keep structured action receipts as the primary audit record; treat screen/PTY recording as secondary.** Evidence: Teleport concedes PTY recording can be defeated by base64-encoding commands (S54); Anthropic's own advice is to log action, params and result (S1). Hutch already has `effect_verified / dispatched / mismatch / navigated_elsewhere / not_dispatched / unknown` — that vocabulary is stronger than most vendors'. Extends: run events, export path, and the run panel. Cost: low (mostly export and retention policy).
8. **Do not make a native a11y path the default observation/action route until it beats pixels on Hutch's own tasks.** Evidence: 142/144 OSWorld entries use no a11y tree and the top 12 are all in that group (S23); small-target grounding is the actual bottleneck at 18.9% best-model accuracy (S28); Anthropic's mitigation for small targets is `zoom` plus keyboard alternatives, not a tree (S3). This is a sequencing recommendation, not a prohibition: the working tree already contains uncommitted AT-SPI host-side work (`src/hutch/computer/accessibility.py`, `src/hutch/computer/native/a11y_bus.py`) which I did not review, so the actionable form is a measured bake-off — same tasks, pixel path vs pixel-plus-semantic, comparing success rate, steps and tokens — before either becomes default. Extends: `ManagedDesktop` observation, `computer/doctor.py`, benchmarks. Cost: low if read-only; explicitly not a replacement for the pixel path.

## 8. What I could not verify

I located canonical pages through vendor documentation indexes (Anthropic's `llms.txt`, S60; Teleport's `llms.txt`), and read the OpenAI Operator launch post (S11) only for product framing, not for any performance claim.

- **OpenAI documentation.** `openai.com` and `platform.openai.com` returned HTTP 403 to `curl` with a browser user agent. I read the CUA launch page, "Introducing Operator", and the Operator System Card through Wayback Machine raw captures (`web.archive.org/web/2026id_/…`). Content is quoted as the vendor's, but I could not confirm it is the current live version.
- **Google Project Mariner.** `deepmind.google/technologies/project-mariner/` and `deepmind.google/models/project-mariner/` return a JavaScript shell with navigation text only (S14); two candidate blog URLs 404'd. Mariner is therefore covered only through the Gemini 2.5 Computer Use post, which says versions of that model "have also been powering Project Mariner" (`verified`, S13). No Mariner-specific safety or reliability claim is made here.
- **Reddit and forum threads.** Not fetched successfully; Hacker News search returned launch announcements rather than complaint threads. Failure-mode evidence is therefore GitHub issues, vendor docs, and independent papers — narrower than intended, and biased toward projects that use GitHub.
- **File-watch triggers.** inotify/fanotify limits, missed events under overflow, and NFS/network-filesystem behaviour were not verified in this pass. Treat §5 as covering webhook and timer triggers only.
- **Stripe's numeric replay tolerance.** The signature page I fetched discusses verification and secret rotation but the extracted text did not state a default timestamp tolerance, so I cite GitHub and Anthropic for replay windows instead.
- **Independent efficacy of Anthropic's prompt-injection classifiers.** No third-party evaluation found; the claim that they run at "approximately zero additional latency and no additional cost" is the vendor's (`vendor claim`, S3), and they do not apply to custom tool definitions at all.
- **OSWorld leaderboard methodology.** Scores are organizer-verified submissions with mixed harnesses and step budgets; my step-budget correlation is confounded by newer models being run at 100 steps. It is reported as a correlation.
- **Hutch-specific performance.** I did not run Hutch's suites or measure its click accuracy; the repo statements I cite are from `docs/computer-use.md` and source comments, not from new measurements.
- **Working-tree state versus the brief.** The brief states Hutch has no accessibility-tree interaction for native apps, and HEAD's `docs/computer-use.md` agrees. The working tree nonetheless contains untracked `src/hutch/computer/accessibility.py`, `src/hutch/computer/native/a11y_bus.py` and modified `src/hutch/computer/desktop.py` (concurrent work, not mine). I did not review or test that code; no claim in this document depends on it, and recommendation 8 is written as a sequencing gate rather than a prohibition because of it.

## 9. Source ledger

All accessed 2026-10-31.

| ID | URL | Used for |
| --- | --- | --- |
| S1 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool | Toolset shape, token costs, click diagnostics, limitations, data retention |
| S2 | https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool | Refs vs coordinates, stale refs, security warning list, token costs, limitations |
| S3 | https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude | Resolution limits, scaling, grid/tiling null result, effort levels, classifier scope, HITL claim |
| S4 | https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks | Direct vs indirect prompt injection threat model |
| S5 | https://platform.claude.com/docs/en/managed-agents/secure-deployment-risks | "Model behavior is not a security control", sandbox boundary table, egress and vault guidance |
| S6 | https://platform.claude.com/docs/en/managed-agents/webhooks | Signature freshness, duplicates, ordering, retry/drop, auto-disable |
| S7 | https://platform.claude.com/docs/en/about-claude/pricing | Per-MTok input prices used for cost arithmetic |
| S8 | https://platform.claude.com/docs/en/manage-claude/spend-limits-api | Existence of a spend-limits control surface |
| S9 | https://web.archive.org/web/2026id_/https://openai.com/index/computer-using-agent/ | CUA benchmarks, confirmation and watch mode, monitor, injection susceptibility |
| S10 | https://web.archive.org/web/2026id_/https://openai.com/index/operator-system-card/ | 92% confirmation recall on 607 tasks, banking refusal, 38.1% OSWorld caution |
| S11 | https://web.archive.org/web/2026id_/https://openai.com/index/introducing-operator/ | Operator product framing (context only) |
| S12 | https://ai.google.dev/gemini-api/docs/computer-use | Normalized coordinates, `intent`, `safety_decision`, sandbox guidance, confirmation obligations |
| S13 | https://blog.google/technology/google-deepmind/gemini-computer-use-model/ | Mariner lineage, "not optimized for desktop OS-level control", per-step safety service, CAPTCHA category |
| S14 | https://deepmind.google/technologies/project-mariner/ | Attempted; JS shell only (limitation, §8) |
| S15 | https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md | A11y-snapshot approach, "deterministic", CLI-vs-MCP context cost |
| S16 | https://raw.githubusercontent.com/browser-use/browser-use/main/README.md | Project scope; cloud `secretBindings` frame-scoped allowlist via docs index |
| S17 | https://raw.githubusercontent.com/browserbase/stagehand/main/README.md | `observe`/`act`/`extract` design, credentials-never-to-model claim |
| S18 | https://raw.githubusercontent.com/Skyvern-AI/skyvern/main/README.md | Vision-LLM approach, 85.8% WebVoyager claim |
| S19 | https://raw.githubusercontent.com/bytedance/UI-TARS/main/README.md | Pure-screenshot model, coordinate-handling guide |
| S20 | https://arxiv.org/abs/2501.12326 | UI-TARS OSWorld 24.6 / 22.7 vs Claude 22.0 / 14.9 |
| S21 | https://raw.githubusercontent.com/OpenInterpreter/open-interpreter/main/README.md | Repositioned as coding agent (category drift) |
| S22 | https://arxiv.org/abs/2404.07972 | OSWorld 369 tasks, human 72.36% vs best 12.24% |
| S23 | https://os-world.github.io/static/data/osworld_verified_results.xlsx | Leaderboard analysis: 142/144 no a11y, step-budget correlation, top score 90.2 |
| S24 | https://arxiv.org/abs/2307.13854 | A11y-tree observation space, 14.41% vs 78.24% |
| S25 | https://arxiv.org/abs/2401.13919 | WebVoyager 59.1%, 85.3% judge agreement |
| S26 | https://arxiv.org/abs/2504.01382 | Independent agent scores, step inflation on failure, 2.6x human time |
| S27 | https://arxiv.org/abs/2412.14161 | TheAgentCompany 30% autonomous completion |
| S28 | https://arxiv.org/abs/2504.07981 | ScreenSpot-Pro 18.9% best model, ScreenSeekeR 48.1% |
| S29 | https://arxiv.org/abs/2310.11441 | Set-of-Mark prompting results |
| S30 | https://arxiv.org/abs/2408.00203 | OmniParser screen parsing, ScreenSpot gains |
| S31 | https://www.microsoft.com/en-us/research/blog/omniparser-v2-turning-any-llm-into-a-computer-use-agent/ | OmniParser v2 39.6 ScreenSpot-Pro vs 0.8 baseline |
| S32 | https://github.com/browser-use/browser-use/issues/951 | Endless loop report |
| S33 | https://github.com/browser-use/browser-use/issues/1137 | Stuck at stage 1 |
| S34 | https://github.com/browser-use/browser-use/issues/839 | Chromium unresponsive until human input |
| S35 | https://github.com/microsoft/playwright-mcp/issues/395 | Snapshot length / pagination |
| S36 | https://github.com/microsoft/playwright-mcp/issues/1274 | Large responses consuming context |
| S37 | https://github.com/browser-use/browser-use/issues/5367 | Unbounded base64 image payload |
| S38 | https://github.com/browser-use/browser-use/issues/221 | Human-in-the-loop feature request |
| S39 | https://github.com/browser-use/browser-use/issues/652 | CAPTCHA solver integration request |
| S40 | https://github.com/Skyvern-AI/skyvern/issues/9101 | OCR for image CAPTCHAs request |
| S41 | https://nvd.nist.gov/vuln/detail/CVE-2025-47241 | `allowed_domains` bypass via URL userinfo |
| S42 | https://nvd.nist.gov/vuln/detail/CVE-2026-82447 | Skyvern double-render sandbox escape (8.8) |
| S43 | https://nvd.nist.gov/vuln/detail/CVE-2026-82640 | browser-use web-ui cleartext API keys |
| S44 | https://nvd.nist.gov/vuln/detail/CVE-2025-49619 | Skyvern SSTI in prompt fields |
| S45 | https://embracethered.com/blog/posts/2024/claude-computer-use-c2-the-zombais-are-coming/ | Prompt injection to malware download/execute on Claude Computer Use |
| S46 | https://github.com/browser-use/browser-use/issues/5469 | Silent input drop in long-lived sessions |
| S47 | https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries | HMAC over raw bytes, `X-Hub-Signature-256` |
| S48 | https://man7.org/linux/man-pages/man5/systemd.timer.5.html | `Persistent`, suspend catch-up, `AccuracySec`, `RandomizedDelaySec` |
| S49 | https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows | `schedule` delays, dropped jobs, 5-minute minimum, 60-day disable |
| S50 | https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ | Retry amplification, backoff with jitter |
| S51 | https://man.openbsd.org/ssh_config.5 | `ForwardAgent` warning |
| S52 | https://man.openbsd.org/sshd_config.5 | `AllowUsers user@host`, `ForceCommand`, `Match`, `TrustedUserCAKeys` |
| S53 | https://developer.hashicorp.com/vault/docs/secrets/ssh/signed-ssh-certificates | Short-lived signed SSH certificates |
| S54 | https://goteleport.com/docs/reference/architecture/session-recording | PTY recording, concealment risk, BPF alternative |
| S55 | https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent | Cloud sandbox / Actions / remote environment, firewall allowlists |
| S56 | https://developers.openai.com/codex/cloud/ | Per-task workspace, network secrets and destination limits |
| S57 | https://status.claude.com/api/v2/incidents.json | 50 incidents 2026-08-05..2026-10-28 (2 critical, 24 major, 21 minor) |
| S58 | https://status.openai.com/api/v2/incidents.json | 25 incidents 2026-10-08..2026-10-30 (4 major) |
| S59 | https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks | 10-second ack, `X-GitHub-Delivery` replay defence, IP allowlist, redelivery |
| S60 | https://platform.claude.com/llms.txt | Docs index used to locate spend-limits and managed-agents security pages |

Repo sources read (not modified): `docs/computer-use.md`, `src/hutch/computer/frames.py` (`MAX_FRAME_EDGE = 2000`), `src/hutch/computer/desktop.py` (`transform: {scale: 1.0}`), `src/hutch/computer/budgets.py` (listed), `docs/architecture.md` (scheduler: "croniter + IANA tz · catch-up").
