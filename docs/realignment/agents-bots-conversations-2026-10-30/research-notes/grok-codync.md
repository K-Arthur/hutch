# Grok Bot and Codync: bots, agents, conversations, groups, teamwork

External research note for Hutch. All nine URLs fetched 2026-10-30 and returned HTTP 200. Method: `curl -sSL` piped to a local HTML-to-text pass (Python stdlib; script/style/nav stripped, `main` or `article` retained). Quotes are verbatim from that text, whitespace normalised, capped at 25 words. "Documented" means stated on these pages only; `INFERENCE` marks my reading, not the docs. The three Grok pages each carry "Last updated: October 28, 2026"; the six Codync pages show no revision date. Pages: `https://docs.x.ai/grok-bot/{bots,shared-bots,chat-and-collaboration}` and `https://www.codync.dev/docs/{bots,agents,conversations,groups,teamwork,cloud-assistants}`.

---

# Product 1: Grok Bot (Cursor)

## 1. Units of work: bot, agent, conversation, group, task

- Bot is the only user-named object: "A Bot is a durable AI teammate with a name, a job, its own conversation, and working context that develops over time." Primary Bot is a role on an ordinary bot, not a type: "Your primary Bot is your main point of contact." (https://docs.x.ai/grok-bot/bots)
- Agent is not a user-facing entity on these pages: there is no agent to create, name or swap and no agent field in any setup step. The pages only say "Bots have separate roles and conversations, but they share the computer." (https://docs.x.ai/grok-bot/bots)
- Conversation is 1:1 with a bot and not separately creatable. Reset exists ("Reset this conversation? The conversation history starts over") and memory survives it. (https://docs.x.ai/grok-bot/bots)
- Group is a second container, not a kind of bot: "Use a group when several Bots need one shared outcome and visible handoffs." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Task and session are absent as objects. Work arrives as messages; the unit of control is a turn: "A direct message from you takes priority over background work and can redirect the current turn." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- INFERENCE: Grok handles multi-bot work by adding a container beside a strict one-chat-per-bot model, rather than by giving a conversation a participant list.

## 2. Creation, identity, instructions, model, tools, memory, ownership

- Creation collects identity only ("type a name, pick a shape and color for its picture, and choose Create"); instructions are taught in conversation: "give the Bot its job, sources, and approval boundaries, and ask it to remember them." (https://docs.x.ai/grok-bot/bots)
- Personal bots keep no settings surface: "Personal Bots no longer have a description or a Bot settings page; to change what a Bot does, tell it in chat." (https://docs.x.ai/grok-bot/bots)
- Memory is written without asking: "A Bot decides on its own when something is worth keeping. It doesn't ask first." (https://docs.x.ai/grok-bot/bots)
- Memory has no UI: "There is no memory screen for a personal Bot." Inspection and correction happen in chat. (https://docs.x.ai/grok-bot/bots)
- Memory is per bot plus a shared layer: "Each Bot has its own memory, but a few facts about you, such as your name and time zone, are shared by all your Bots." (https://docs.x.ai/grok-bot/bots)
- Tools are apps, secrets, skills and files, and they travel with sharing: "Before you share, check its apps, secrets, skills, and files, since they work in every teammate's chat." (https://docs.x.ai/grok-bot/shared-bots)
- Ownership is narrow: "Only the Bot's owner can change these" (name, picture, label) (https://docs.x.ai/grok-bot/bots); "Only the owner can delete a shared Bot." (https://docs.x.ai/grok-bot/shared-bots)
- Templates are the copy mechanism, kept distinct from sharing: "Adding a shared template creates a copy on the recipient's account." (https://docs.x.ai/grok-bot/bots)
- No model selection is documented for a bot on any of the three pages: no picker, no model field, no statement that the model is fixed. Recorded as absent, not as unsupported.

## 3. Personal vs shared bots

- The split is binary: "A Bot is either personal or shared." (https://docs.x.ai/grok-bot/shared-bots)
- Sharing grants access without duplicating, and each transcript stays private: "Sharing doesn't make a copy, and each person's chat with a shared Bot is private." (https://docs.x.ai/grok-bot/shared-bots)
- Residency differs by kind: "Shared Bots always run in the cloud. A Bot that runs on your own computer can't be shared." (https://docs.x.ai/grok-bot/shared-bots)
- Two access modes and two roles: whole team or "People you invite"; "Collaborator to let them chat with the Bot, or Manager to let them also change how it works". (https://docs.x.ai/grok-bot/shared-bots)
- What is shared is configuration plus team-level learning: "A shared Bot uses the apps and secrets its owner added"; the bot "doesn't save anything about you personally for the team." (https://docs.x.ai/grok-bot/shared-bots)

## 4. Conversations: ownership, multiple bots, mentions, handoffs, notifications

- One chat per bot; several bots require a group, bounded at "In the To: field, add two to six Bots." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Default routing is silent triage ("Write normally to let the participating Bots decide who should respond"), with mention and reply as the explicit forms; "@everyone" is advised "sparingly". (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Handoffs are asynchronous inter-bot messages ("A Bot can send an asynchronous message to another Bot") and they leave the room: those messages "show up in the Bots' own chats, not in the group." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- There is no control for inter-bot messaging: "There is no switch for this." The remedy is an instruction plus memory. (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Notifications are per bot but not per group: "Group chats don't have the per-Bot Notifications switch." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Private context reaches groups by design: "In a group chat, your Bot can use what you told it in your private chat"; the only defence is "If something should stay out of a group chat, tell your Bot." (https://docs.x.ai/grok-bot/bots)

## 5. Governance: permissions, membership, visibility, spend

- Control is two-axis (who may use, who may administer) and admins sit above owners: Auto-add inserts a bot into sidebars and "Those members can't hide it." (https://docs.x.ai/grok-bot/shared-bots)
- Approval is answered by the asker, per message: "In a group chat, only the person whose message the Bot is answering can answer." (https://docs.x.ai/grok-bot/shared-bots)
- Identity binding is per connection: "A connected account always acts as the person the Bot is answering." (https://docs.x.ai/grok-bot/shared-bots)
- Billing follows the asker: "A shared Bot reply uses the Grok Bot usage of the person it's answering." No per-bot budget or spend ceiling is documented, only account limits and their error strings. (https://docs.x.ai/grok-bot/shared-bots)
- Machine access is a privacy boundary: a teammate's shared bot "usually works on your Grok Bot computer", and a stricter local mode blocks it: "Your privacy mode setting is stricter than the owner's, so this chat can't use your computer." (https://docs.x.ai/grok-bot/shared-bots)
- Secret hygiene is advice, not enforcement: "Remove API keys, internal URLs, customer data" before sharing, because "A public link can be opened by anyone who has it" and it "exposes the Bot's shared configuration". (https://docs.x.ai/grok-bot/bots)
- Deletion does not isolate machine state: "Files and sign-ins on the shared computer aren't isolated per Bot and can remain there". (https://docs.x.ai/grok-bot/bots)

## 6. Teamwork and delegation

- Coordination is a role plus a room: the primary bot "checks in with you on its own and coordinates work with your other Bots", and "Put Bots in a group chat when the handoff itself needs to be visible." (https://docs.x.ai/grok-bot/bots)
- Topology guidance is explicit: "Ask for a single owner at each stage. Parallel handoffs create duplicate work and noisy updates." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- No round cap, reply cap or all-pass rule is documented for a group exchange; only user action (Stop, a new message) ends it. Recorded as an absence, not a design claim.
- Stop is scoped to the future: "Send a direct “Stop now” message when work should end immediately. This does not undo actions the Bot already completed." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- The only stated brake on delegation is economic: "Every Bot reply counts toward your usage, including replies in a group and messages between Bots". (https://docs.x.ai/grok-bot/chat-and-collaboration)

## 7. Explicit limits, experimental statements, caveats

- Rollout limits: "X Chat support is rolling out gradually"; "Search availability can vary during rollout." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Groups exclude sensitive cards and lose media: "Approval requests, secret and login requests, and email or Slack drafts do not appear in a group"; "Bot-to-group handoff messages are text-only". (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Mixing residency in one group is prohibited: a shared bot can join, "but not alongside Bots that run on your own computer." (https://docs.x.ai/grok-bot/chat-and-collaboration)
- Memory is explicitly not authoritative: "Memory is not a substitute for an authoritative source". Bot deletion is irreversible and partial: history goes, machine files stay. (https://docs.x.ai/grok-bot/bots)

## Contradictions and unresolved tensions (Grok)

- Residency, same page: "Shared Bots always run in the cloud" versus a shared bot in your own chat that "usually works on your Grok Bot computer" and "can use the files there". (https://docs.x.ai/grok-bot/shared-bots) The docs never reconcile where execution happens.
- Group completeness: the bots page recommends groups so "the group preserves the handoffs in one conversation" (https://docs.x.ai/grok-bot/bots), while the collaboration page says bot-to-bot messages "show up in the Bots' own chats, not in the group." (https://docs.x.ai/grok-bot/chat-and-collaboration) INFERENCE: the group transcript is not a complete audit trail.
- Memory scope is ambiguous: "a few facts about you ... are shared by all your Bots" versus "A teammate's shared Bot doesn't get the facts your own Bots share about you." Both on https://docs.x.ai/grok-bot/bots, which never says whether shared bots you own count as "your Bots".

---

# Product 2: Codync

## 1. Units of work: bot, agent, conversation, group, task

- Bot: "A bot is a persistent, named teammate that lives on your computer." and "Each bot runs one coding agent ... with its own name, avatar, standing instructions, folder and approval setting." (https://www.codync.dev/docs/bots)
- Agent is the harness, one per bot, chosen independently: "Every bot runs one coding agent on your computer."; "Each bot picks its own agent, and different bots can use different ones." (https://www.codync.dev/docs/agents)
- Chat and session are explicitly different: "A bot's chat and its agent's session are two different things." The session is "the agent's working context: what the model currently remembers of the conversation." (https://www.codync.dev/docs/bots)
- Group has no execution identity: "A group has no agent, folder or session of its own."; "It's a room for bots you already have." (https://www.codync.dev/docs/groups)
- Task is not an object, and external callers are senders rather than members: a message starts a turn whose status is completed, failed or timeout, and a cloud assistant's request shows as "Message from Cloud assistant" in the bot's chat. (https://www.codync.dev/docs/cloud-assistants)

## 2. Creation, customization, identity, instructions, model, tools, memory

- Profile fields include "Standing instructions: rules that always apply" with task-specific requests left to chat, and a bot may rewrite itself with a visible notice: "You can also ask a bot in its chat to rename itself or change its own instructions." (https://www.codync.dev/docs/bots)
- Model comes from the agent, not a product catalogue: "There's no separate default-agent setting."; "A registry agent is never picked on its own." (https://www.codync.dev/docs/agents)
- Credentials stay local and stay the agent's: "It never calls a provider's API with your login."; API keys "never leave the computer." (https://www.codync.dev/docs/agents)
- Memory is per bot and inspectable: "Each bot keeps a long-term memory across sessions", read on its Memory tab. (https://www.codync.dev/docs/bots)
- Reconfiguration has defined session effects: changing agent, model or folder "starts a new agent session", while "the chat history stays." (https://www.codync.dev/docs/bots)
- Ownership is single-owner throughout: no role, ACL or collaborator concept appears on any of the six pages. Reachability, not ownership, is what varies.

## 3. Personal vs shared: what is shared, what stays private

- There is no personal/shared bot split. The equivalent is per-bot reachability: `Offered to the network` off means other computers "don't list this bot and can't message it"; `Reachable by cloud assistants` off means assistants "don't list this bot and can't message it". (https://www.codync.dev/docs/bots)
- Hiding is the third gate: "a bot you hid from the bot list can't be messaged", and neither can a group. (https://www.codync.dev/docs/teamwork)
- What stays private is the owning chat, even inside a room: "Its tool calls, thoughts and approval cards for that turn appear in the group. The member's own chat doesn't show them." (https://www.codync.dev/docs/groups)
- What is exposed to peers is metadata: assistants can "List your bots, with their names, descriptions, status and kind". (https://www.codync.dev/docs/cloud-assistants)

## 4. Conversations: one chat, groups, mentions, handoffs, notifications

- One enduring chat per bot and no user-created conversations: "Each bot has one chat that keeps going."; "There's no command to start a new session". (https://www.codync.dev/docs/conversations)
- Several bots require a group; groups cannot nest and duplicates collapse: "A group can't contain another group."; "If a group with exactly the same bots already exists, you get that group instead of a second one." (https://www.codync.dev/docs/groups)
- Replies are serialised: "Members answer in order, each after the previous one finished"; silence is legitimate: "A member with nothing new to add passes, and nothing appears in the chat." (https://www.codync.dev/docs/groups)
- Termination is explicit and capped: "The exchange stops after three rounds, ten replies in all, or a round where every member passes." (https://www.codync.dev/docs/groups)
- Mention matching is loose (full name, name without spaces, or first word, any case) and "Replying to a member's message counts as mentioning it." (https://www.codync.dev/docs/groups)
- A busy member does not block the room, but "Her late answer is dropped if you press Stop in the group". (https://www.codync.dev/docs/groups)
- Group notification aggregates once per exchange: "You get one “done” notification per exchange, from the last member that replied". (https://www.codync.dev/docs/groups)
- Fresh sessions show an editable handoff card carrying "the latest summary of the conversation, your last four messages word for word, the bot's last reply and its open plan"; "The bot can still search the earlier chat." (https://www.codync.dev/docs/conversations)

## 5. Governance: permissions, membership, visibility, spend

- One human holds all authority: "Only you can turn this on, and it's off by default" (of Manage the team). (https://www.codync.dev/docs/bots)
- Approval default is permissive and stated plainly: "New bots start on Approve automatically." (https://www.codync.dev/docs/bots); "With Approve automatically, no cards appear: Codync allows each request for you." (https://www.codync.dev/docs/conversations)
- Cross-computer access is rule-based, deny-capable and decided locally: "Deny: any bot on server → any bot here"; "The first rule that matches decides"; "A refused bot is told why, and its request ends failed." (https://www.codync.dev/docs/teamwork)
- The cloud-assistant path breaks end-to-end confidentiality: "a cloud assistant's requests and the bots' replies pass through the Codync relay in readable form, over HTTPS." (https://www.codync.dev/docs/cloud-assistants)
- Revocation lags: removing access "leaves a sign-in it already has working for up to a day." (https://www.codync.dev/docs/cloud-assistants)
- Spend is observed, not budgeted: "Codync reads plan limits from the agents installed on your computer." No per-bot ceiling appears. (https://www.codync.dev/docs/conversations)

## 6. Teamwork: delegation, ownership, aggregation, failure and cancel

- Flat topology with no setup and no waiting: "There's no team to configure."; "Bots never wait on each other."; "The answer goes back to the sender, not to you." (https://www.codync.dev/docs/teamwork)
- Context is not forwarded: "The sender's conversation isn't copied over, only the request." While on a request the recipient "can't message you or other bots." (https://www.codync.dev/docs/teamwork)
- Aggregation is minimal by design: one collapsed row per exchange ("3 messages with Owen"), the body hidden ("The request text itself stays out of the chat"), and a read-only two-party sheet for the full exchange. (https://www.codync.dev/docs/teamwork)
- Caps are numeric: up to 16 queued or running per bot, 64 per computer, and "a chain of requests stops after eight handoffs." (https://www.codync.dev/docs/teamwork)
- Restart is fail-closed: "they're marked as failed and not run again." No timeout exists: "there's no time limit". (https://www.codync.dev/docs/teamwork)
- Stop does not propagate: stopping the sender "doesn't cancel what it already sent"; stopping the recipient cancels queued requests and "may leave partial changes." (https://www.codync.dev/docs/teamwork)
- Manager bots are bounded and attributable: 20-bot creation cap, cards that expire after "about four and a half minutes", changes over 2,000 characters "refused before the card appears", and a stamp "Created by Lead · Oct 20, 2026". (https://www.codync.dev/docs/teamwork)

## 7. Explicit limits, experimental statements, caveats

- "Networks are a beta feature." (https://www.codync.dev/docs/teamwork)
- Concurrency hazard is stated, not solved, and the workspace is not a jail: "Codync doesn't create separate Git worktrees for them."; "A workspace isn't a sandbox: the bot can reach whatever its agent's own permissions allow." (https://www.codync.dev/docs/bots)
- Group privacy is prompt-level only: "That's only an instruction to the agent: the same session holds both conversations." (https://www.codync.dev/docs/groups)
- Group memory is append-only: "In a group, a bot can add to its memory but can't change or remove what's there."; "Group chats don't feed dreaming". (https://www.codync.dev/docs/groups)
- Member failure is absorbed as silence: "If a member fails while answering, the room counts it as a pass and shows the error." (https://www.codync.dev/docs/groups); files too: "Bots share files only in their own chat, not in group chats or routine runs." (https://www.codync.dev/docs/conversations)
- Cloud assistants are lossy and pull-only: newest 50 requests kept and forgotten on restart, "It can't be told when a reply is ready", 120 requests per minute per account, and "There is no version to run on your own server". (https://www.codync.dev/docs/cloud-assistants)

## Contradictions and unresolved tensions (Codync)

- Continuity: "It has one chat that never ends" (https://www.codync.dev/docs/bots) sits against automatic fresh sessions and summarisation (https://www.codync.dev/docs/conversations). The chat/session split resolves it technically, but the summary sentence overstates how much context survives.
- Reachability: "Every bot can reach your other bots as soon as they exist" (https://www.codync.dev/docs/teamwork) is immediately qualified by hidden bots, groups and per-computer deny rules. Stated exceptions under a misleading absolute.
- Room visibility: "Each member's reply is the one message the room sees" versus "Its tool calls, thoughts and approval cards for that turn appear in the group", both on https://www.codync.dev/docs/groups; the second widens what the room sees.
- Stop guarantees differ by scope: group Stop "stops members working in the group" (https://www.codync.dev/docs/groups), while a delegated request already sent "doesn't cancel what it already sent" (https://www.codync.dev/docs/teamwork). One word, two promises.

---

# Design implications for a local-first single-owner product

- Separate the durable transcript from the model context. Codync's chat-versus-session split is the cleanest published model: the chat keeps everything, the session rotates, and rotation hands off an editable summary plus recent verbatim turns.
- Make the bot chat the container and a task a turn inside it. Both products give each bot exactly one continuing chat and never ask the user to create a conversation; Hutch today treats a conversation as a list of independent runs (docs/realignment/baseline.md), the opposite shape, and that is the main gap.
- Model a group as membership over existing bots, with no agent, folder or model of its own, so a room cannot silently acquire execution identity or a second config surface to keep in sync.
- Put termination in the runtime, not the prompt: a round cap, a reply cap and an all-pass stop are deterministic and make room cost bounded. Grok documents none of these.
- Keep the per-exchange audit row: one collapsed row plus a read-only two-party transcript gives delegation traceability without filling the chat with request bodies.
- Treat delegation as a queue with hard caps and fail-closed restarts: depth limit on handoff chains, per-bot and per-host queue limits, and pending work marked failed after a crash rather than replayed. Hutch has step and time caps; handoff depth is the missing one.
- Do not inherit approval semantics by accident. Grok suppresses approval, secret and draft cards in groups; Codync shows them. For a single owner the Codync choice is coherent, but it should be a stated decision because it changes what a room transcript can hold.
- Prefer capability switches over roles. With one owner, `Offered to the network` and `Reachable by cloud assistants` booleans plus first-match host rules cover the same ground as Grok's owner, Manager, Collaborator and admin tiers at a fraction of the surface.
- Never promote prompt-level privacy to a documented guarantee. Codync shares one session between a bot's private chat and a room and relies on an instruction not to reveal it; Hutch should separate the data or label the limit.
- State what Stop does not do. Both products say stopping is not rollback; Hutch's cross-process Stop gap makes the contract worth writing explicitly: stopped means no further steps, not undone steps.

# Unresolved questions

- Does a Grok bot have any per-bot model or tool configuration, or is all depth delegated to skills and memory? None of the three pages say.
- What ends a Grok group exchange in practice: a reply cap, a quiet period, or only the user? Routing is documented, termination is not.
- Is there any Grok spending control below account level (per bot, per group, per teammate)? Only usage accounting is described.
- Does deleting a shared Grok bot delete the team-level facts it saved, and do teammates lose them? Deletion is described for the owner only.
- Does Codync's group round-robin have fairness or cost accounting beyond the three-round and ten-reply caps? No per-round cost statement appears.
- What happens to a Codync approval card raised in a group if the requester leaves the group or the member is removed mid-turn? Not stated.
- How are Codync network rules stored and ordered for review, beyond "the first rule that matches decides" (https://www.codync.dev/docs/teamwork)? The rule editor is not shown.
- Neither product documents a per-bot spend ceiling or a task record separate from the chat, so Hutch's spend ceilings and task list have no prior art here.
