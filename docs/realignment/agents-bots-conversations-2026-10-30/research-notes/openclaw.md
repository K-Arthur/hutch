# OpenClaw - agents, bots, conversations (documentation research)

Source set: nine pages under https://docs.openclaw.ai/gateway/config-agents/, fetched 2026-10-30 with curl (all HTTP 200) and converted from HTML to text; every quoted string below was re-checked against the live page text after drafting. Quotes are verbatim and short with the page URL. "INFERENCE" marks my reading, not documented text. No emoji reproduced. Note that /gateway/config-agents is now an index: "Every heading this page used to publish keeps its anchor here" (https://docs.openclaw.ai/gateway/config-agents).

## 1. Agent config schema

- Two documented layers: `agents.defaults.*` (global) and `agents.entries.<agentId>.*` (per-agent). "The agents.entries object key is the stable agent id." (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent)
- Onboarding: interactive setup asks for the first agent name and "uses main as the suggested value"; automated onboarding keeps the historical `main` default unless `--agent-name` is passed; "main is an ordinary agent id." (https://docs.openclaw.ai/gateway/config-agents)
- A sole named agent "uses the same default workspace and shared auth store as main", and onboarding migrates legacy `agent:main:*` session history to it (https://docs.openclaw.ai/gateway/config-agents).
- `default` is retired as an implicit agent: "default is retired. Exactly one configured agent resolves implicitly"; multi-agent operations require a binding, surface agentId, scoped store owner, or `--agent` (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).
- `agents.ownership: "explicit"` is stamped when creating a fleet; such fleets "have no default", so channels and ambient services need bindings or agentId targets (https://docs.openclaw.ai/gateway/config-agents).
- Inheritance is not uniform. Four documented patterns: (a) inherit-when-omitted - contextInjection, bootstrapMaxChars, bootstrapTotalMaxChars, contextLimits, utilityModel ("Omitted values inherit ..."); (b) replace-not-merge - skills: "A non-empty agents.entries.*.skills list is the final set for that agent; it does not merge with defaults."; (c) deep-merge - "The agent block deep-merges over global tts"; (d) layered params merge: "agents.defaults.params (global base), then agents.defaults.models[...].params ..., then agents.entries.*.params (agent-wide)" (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap, .../models, .../entries-and-multi-agent).
- Precedence examples: workspace config beats env - "An explicit agents.defaults.workspace value takes precedence over OPENCLAW_WORKSPACE_DIR."; cwd - "Session-spawned working directories take precedence, then agents.entries.*.cwd, then agents.defaults.cwd." (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap)
- Model edit scope: `agents.defaults.modelSelectionScope` defaults to "session": "changing a model in one chat does not change other chats"; "Agent/global writes require an explicit scope flag or configuration choice"; "There are no per-agent or per-channel overrides of this setting." (https://docs.openclaw.ai/gateway/config-agents/models)
- Per-agent `model` string form is strict: "string form sets a strict per-agent primary with no model fallback"; `{ primary, fallbacks: [] }` makes strictness explicit (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).
- Runtime policy is deliberately not an agent field: "Runtime policy ... lives on providers and models, not on agents.defaults." (https://docs.openclaw.ai/gateway/config-agents/runtime-and-cli-backends); "A provider/model prefix alone never selects a harness." (https://docs.openclaw.ai/gateway/config-agents/models)
- Config-file vs runtime: the docs describe config as the source of agent identity and per-agent limits; runtime commands (`/model`) only mutate session/agent/global selection within the declared scope. INFERENCE: there is no documented path for a runtime caller to mint a new agent id or new defaults; agent topology is deploy-time state.
- Ambiguity: page 1 says a fleet gets `ownership` stamped automatically, while the entries page says `default` is retired. Both are consistent only if "retired" means "no implicit default agent", not "key rejected"; the docs never show `default` being rejected by the schema.

## 2. Isolation

- Workspace: default `OPENCLAW_WORKSPACE_DIR` or `<state-dir>/workspace`; "In a multi-agent fleet, agents without their own workspace use an agent-id subdirectory so no implicit owner claims the shared root" (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap).
- Explicit separate `cwd` is a sandbox boundary: "A distinct working directory requires an unsandboxed run; sandboxed runs reject it." (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap)
- Sandbox modes: `off` (default), `non-main`, `all`; scope `session`, `agent` (default), `shared`, where "shared: shared container and workspace (no cross-session isolation)" (https://docs.openclaw.ai/gateway/config-agents/sandbox).
- Workspace access: `none` gives a per-scope workspace under `~/.openclaw/sandboxes`; `ro` mounts the agent workspace read-only at `/agent`; `rw` mounts it read/write at `/workspace` (https://docs.openclaw.ai/gateway/config-agents/sandbox).
- Network: "Containers default to `network: none`"; "`host` is blocked."; `container:<id>` join is blocked unless `dangerouslyAllowContainerNamespaceJoin: true` (described as break-glass) (https://docs.openclaw.ai/gateway/config-agents/sandbox).
- Per-agent tools: `tools.profile`, `tools.allow`, `tools.deny`, `tools.elevated` per entry; the sandbox default allowlist includes `exec`, `process`, `read`, `write`, `sessions_send`, `sessions_spawn`, and denies `browser`, `canvas`, `nodes`, `cron`, `discord`, `gateway` (https://docs.openclaw.ai/gateway/config-agents/sandbox, .../entries-and-multi-agent).
- Credentials: these pages document a shared auth store, an upgrade-only `agents.defaults.authInheritance.agentId`, and relocation of the store to `state/openclaw.sqlite`; no per-agent credential vault is described here (https://docs.openclaw.ai/gateway/config-agents). INFERENCE: credential isolation is weaker than workspace isolation in the documented model; per-agent `tts`/provider keys are config fields, not per-agent secret scoping.
- Cross-agent visibility is policy, not a wall: `session.communication.send`/`receive` accept always/ask/never and "omitted values default to always"; sharing modes are readOnly/suggest/draft (https://docs.openclaw.ai/gateway/config-agents/sessions).
- The docs state the boundary explicitly: "These controls coordinate operators sharing one agent; they are not a security boundary between tenants." and "Use separate Gateways or agents when work requires isolation." (https://docs.openclaw.ai/gateway/config-agents/sessions)
- Sub-agent spawn is same-agent by default: `subagents.allowAgents` defaults to "same agent only"; stale ids are "rejected by sessions_spawn and omitted from agents_list" (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).

## 3. Session routing and identity

- Message to agent: `bindings[]` with `match.channel` (required), optional accountId (`*` = any), peer, guildId, teamId; fixed tier order peer, guildId, teamId, accountId, accountId "*", then sole-agent fallback. "Within each tier, the first matching bindings entry wins." (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent)
- Unmatched multi-agent traffic is rejected, not defaulted: "explicit multi-agent fleets without a matching binding reject the request" (same URL).
- `type: "acp"` bindings bypass tier ordering: OpenClaw "resolves by exact conversation identity (match.channel + account + match.peer.id)" (same URL).
- Message to session: `session.scope` per-sender (default) or global; `dmScope` shown as `main` in the example (prose never labels it default) with `per-channel-peer` "recommended for multi-user inboxes"; `groupScope` per-group (default) or main; `bindings[].session` overrides dmScope/groupScope for matched peers (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Cross-channel identity: `session.identityLinks` maps shared identity ids to provider-prefixed peers (e.g. one person as telegram + discord) (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Reset: "none disables automatic reset and is the default; compaction bounds active context instead." (the config example nevertheless shows `mode: "daily"` - example and prose disagree); `daily` uses `sessionStartedAt`, `idle` uses `lastInteractionAt`; heartbeat/cron/exec writes do not keep a session fresh; "/new and /reset remain available in every mode" (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Reset precedence: `resetByChannel` "wins outright over resetByType/reset"; `resetByType` covers direct/group/thread and "the schema rejects dm"; `resetTriggers` are case-insensitive and "command aliases are not added automatically" (same URL).
- Communication gate: always/ask/never per direction; "ask requires a human decision before sending or admitting the message as new peer input" (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Reset cost: the startup prelude is skipped for bare commands - "Bare chat /new and /reset commands acknowledge the reset without invoking the model" (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap).
- Retention: `pruneAfter` 30d, `archiveDashboardAfter` 7d, `maxEntries` 5000, `maxDiskBytes` 10gb with `highWaterBytes` at 80%, `resetArchiveRetention`, optional `coldStorage` after 30 days; `maintenance.mode` enforce (default) or warn (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Resume: thread bindings unbind after `idleHours: 24` by default; for cold storage, "opening or resuming one restores its history before use" (same URL).
- Behaviour on config change: "Changes apply to new admissions, not already accepted messages."; "Reset removes the override, so later configuration changes apply again."; "Adopting an existing session never replaces its settings." (same URL)
- Model-scope writes "can affect new and existing unpinned sessions and cron jobs that inherit the changed default on their next run. They do not rewrite other sessions' explicit model selections." (https://docs.openclaw.ai/gateway/config-agents/models)
- A changed `session.store` path is not hot-migrated: if an older version split the store, "stop the Gateway and run openclaw doctor --fix to merge its sessions with backups" (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Concurrency: runs are capped per agent ("max parallel agent runs across sessions (each session still serialized)"), default `max(8, CPUs * 4)` (https://docs.openclaw.ai/gateway/config-agents/models).

## 4. Multi-agent

- Routing is binding-driven; the entries page gives three named access profiles: full access (`sandbox.mode: "off"`), read-only tools + workspace (`workspaceAccess: "ro"`, no write/edit/exec/browser), and messaging only (`workspaceAccess: "none"`, sessions tools plus channel senders) (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).
- Agent-to-agent messaging: `session.communication` gates send/receive; `tools.agentToAgent.send` restricts targets. Omit to keep "global policy and visibility checks", `[]` "denies ordinary cross-agent sends" (same URL).
- Send does not imply read: "Matches permit send-only access under narrow visibility without granting history, search, list, status, or session controls." (same URL)
- Steering across sessions is separately authorized: "explicit cross-session sessions_send(mode="steer") authorization remain authoritative" (https://docs.openclaw.ai/gateway/config-agents/messages-and-talk).
- Same-conversation steering defaults open: `allowCollaborativeSteering` is true, so admitted human input "may steer under the active turn's original identity and prepared permissions" (https://docs.openclaw.ai/gateway/config-agents/messages-and-talk). INFERENCE: this is an authority-confusion risk distinct from cross-agent permissions.
- Handoff: no `handoff` primitive appears on these nine pages. Nearest documented mechanisms are `sessions_spawn` (child session), `agents.defaults.systemAgent` (ambient owner and fallback), and `talk.agentId` (owner of unscoped Talk sessions). INFERENCE: "handoff" in OpenClaw is composition of spawn + send + systemAgent ownership, not a first-class transfer with transcript custody rules.
- Depth and breadth limits: `subagents.maxConcurrent` 8 per spawning session, `maxChildrenPerAgent` 5, `maxSpawnDepth` 1-5 with default 5, `archiveAfterMinutes` 60, `requireAgentId` false (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).
- Sandbox guard on spawn: "if the requester session is sandboxed, sessions_spawn rejects targets that would run unsandboxed" (same URL).
- Consent is per-agent and security-relevant: `nativeRuntimeConsent` means "An administrator selecting a remembered harness or creating a chat with it automatically uses Full access with the optional sandbox disabled", re-checked "immediately before native dispatch" (same URL).
- Fleet identity: `systemAgent.agentId` supplies the recorded default for unbound routing and unscoped reads; "An ownerless multi-agent fleet has no default badge." (https://docs.openclaw.ai/gateway/config-agents/heartbeat-compaction-and-streaming)
- Scope of a consult: "Delegated consults with a requesting agent keep that requester as their owner." (same URL)

## 5. Streaming, compaction, heartbeat

- Heartbeat is retired as config: "Heartbeat configuration has moved to ordinary automation jobs."; `openclaw doctor --fix` migrates it, and "reloads and restarts do not recreate deleted jobs" (https://docs.openclaw.ai/gateway/config-agents/heartbeat-compaction-and-streaming).
- Partial output is opt-in per channel: "Non-Telegram channels require explicit *.streaming.block.enabled: true to enable block replies."; QQ Bot is the exception (https://docs.openclaw.ai/gateway/config-agents/heartbeat-compaction-and-streaming).
- Chunking defaults: `blockStreamingDefault: "off"`, chunk 800-1200 chars, `breakPreference: "paragraph"`, `coalesce.idleMs: 1000`; Discord, Google Chat, Mattermost, MS Teams, Signal, Slack default to 1500 chars (same URL).
- Humanised pacing: `humanDelay` "Default: off", natural 800-2500ms; `typingMode` never/instant/thinking/message, `typingIntervalSeconds` 6 (same URL).
- Compaction: enabled by default; `mode` is `default` or `safeguard`; `keepRecentTokens` "Default: 20000" in prose while the example block shows 50000 - an internal inconsistency to treat as unresolved (same URL).
- Compaction timeouts: `timeoutSeconds` 180 refreshed by progress; "The complete compaction stops after 10 windows (30 minutes by default) even if it keeps streaming." (same URL).
- Summary quality: `qualityGuard` retries once, then stores the best summary "marked details.qualityDegraded"; "Retention is best-effort on this path"; "the user receives a warning even when notifyUser is false" (same URL).
- Interrupted turns: queue `interrupt` "abort the active run before starting the newest prompt"; `midTurnPrecheck` is "Default: disabled"; compaction `enabled: false` still leaves "preflight and overflow-recovery compaction paths and manual /compact" available (same URL, .../messages-and-talk).
- Attempt budgets: unset `timeoutSeconds` gives "each model attempt the 48-hour default"; each fallback "receives a fresh budget"; "Set 0 for unlimited execution"; "cancellation of the operation does not start another candidate" (https://docs.openclaw.ai/gateway/config-agents/models).
- Server-side compaction is automatic on some routes: Anthropic API-key models document threshold compaction, OpenAI Responses with store; both delay local preflight compaction (same URL).
- Duplicate/overlap suppression: inbound debounce `2000ms` global, Telegram 300ms when unset, and "Batching is a bounded timing heuristic, not a guarantee that every part of a long message becomes one turn."; queue cap 20 with `drop: "summarize"`, plus a built-in 500ms queue debounce (https://docs.openclaw.ai/gateway/config-agents/messages-and-talk).
- Notices are bounded: `notifyOnCreate` shares "one bounded summary with available title, creator, and creation source, without copying messages", and the summary "does not survive a Gateway restart" (https://docs.openclaw.ai/gateway/config-agents/sessions).

## 6. Failure modes the docs warn about

- Silent legacy keys: "Whole-agent runtime keys are legacy." and are "ignored by runtime selection"; `mainKey` is "accepted but ignored"; `rotateBytes` is rejected; `dm` in resetByType is rejected (https://docs.openclaw.ai/gateway/config-agents/runtime-and-cli-backends, .../sessions).
- Missing bindings fail closed: unmatched multi-agent requests are rejected rather than falling back to a default agent (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent).
- Doctor is load-bearing: legacy `main` re-use returns `legacy-session-migration-required` or `shared-auth-store-owned-by-main` and requires `openclaw doctor --fix` before the new `main` gets fresh storage (https://docs.openclaw.ai/gateway/config-agents).
- Retention is not a hard ceiling: `maxDiskBytes` "is not a guaranteed physical ceiling", and protected rows can keep a store above `maxEntries` (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Sandbox setup traps: `setupCommand` "Needs network egress, writable root, root user"; browser sandbox `network: "none"` is unsupported; upgrade disables affected sidecars (https://docs.openclaw.ai/gateway/config-agents/sandbox).
- Remote workspaces diverge: SSH backend "does not sync remote changes back to the host automatically" and "does not support sandbox browser containers" (same URL).
- Downgrade hazard: "Older versions do not enforce these preferences" for session communication; "Before downgrading, remove the new configuration keys" (https://docs.openclaw.ai/gateway/config-agents/sessions).
- Degraded state is visible but not fatal: compaction can continue on a degraded summary, and dashboard revocation "does not retract its saved widget or layout" (same URL).
- Privilege promotion by remembered consent: a remembered harness id yields Full access with sandbox off for admins without a new prompt (https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent). INFERENCE: this is the highest-risk documented default for a multi-tenant deployment.

## 7. Explicit non-goals and limitations

- Session sharing is explicitly not tenant isolation: "Use separate Gateways or agents when work requires isolation." (https://docs.openclaw.ai/gateway/config-agents/sessions)
- Sandbox `scope: "shared"` gives "no cross-session isolation" (https://docs.openclaw.ai/gateway/config-agents/sandbox).
- Custom compaction instructions are "code-owned"; custom summaries require a compaction provider plugin; retired instruction fields are stripped by Doctor (https://docs.openclaw.ai/gateway/config-agents/heartbeat-compaction-and-streaming).
- The bootstrap truncation notice is "built in and not configurable" and deliberately omits per-file diagnostics (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap).
- `USER.md` has "a fixed 4,000-character cap"; `bootstrapMaxChars` "can only lower it for USER.md, never raise it" (https://docs.openclaw.ai/gateway/config-agents/workspace-and-bootstrap).
- No per-agent or per-channel override of `modelSelectionScope`; Telegram pickers and the embedded TUI "remain session-only even when this setting is configured" (https://docs.openclaw.ai/gateway/config-agents/models).
- Media generation, vision, PDF, music, video and TTS are outside runtime policy (https://docs.openclaw.ai/gateway/config-agents/runtime-and-cli-backends).
- Flat Talk keys and `claude-cli/<model>` refs are "compatibility-only" / legacy (https://docs.openclaw.ai/gateway/config-agents/messages-and-talk, .../runtime-and-cli-backends).

## Expose to ordinary users vs advanced config

- Ordinary: agent name, avatar, emoji/ack reaction, response prefix, typing indicators.
- Ordinary: per-chat model choice, with the guarantee that it stays in that chat (scope defaults to session).
- Ordinary: `/new` and `/reset`, plus daily or idle auto-reset as a simple policy.
- Ordinary: read-only or messaging-only access profile for a shared bot; these are three documented presets.
- Advanced: bindings and match tiers; a wrong order silently routes to the first matching entry.
- Advanced: sandbox scope (session/agent/shared), workspaceAccess, and network policy; shared scope removes isolation.
- Advanced: subagent breadth/depth limits, `allowAgents`, and `agentToAgent.send`; defaults are conservative but unforgiving of stale ids.
- Advanced: compaction tuning, quality guard, cold storage, disk budgets; several knobs are best-effort, not guarantees.
- Advanced: `nativeRuntimeConsent`; it converts a remembered harness into Full access with sandbox off for admins.
- Keep internal: `agents.ownership`, `systemAgent`, `authInheritance`, store paths, and Doctor migration codes.

## Open questions

- Is `keepRecentTokens` 20000 or 50000? Prose and example disagree; which one ships?
- Does `agents.entries.default` still parse, and what error does reusing `main` after a named-agent install actually surface to a user?
- Where is per-agent credential scoping documented, if it exists outside these pages (`authInheritance` is described as upgrade-only)?
- What is the supported handoff story, given no `handoff` primitive and no transcript-custody rule on these pages?
- Do `session.communication` defaults (`always/always`) ship that way in a fleet with `ownership: "explicit"`, or do bindings narrow them in practice?
- What is the real duplicate-suppression contract under gateway restart, given that inbound batching is "a bounded timing heuristic"?
- How does `nativeRuntimeConsent` interact with channel-originated (non-admin) chats after an admin has remembered a harness?
- Are `maxDiskBytes`/`maxEntries` overruns observable to operators other than in logs and `openclaw sessions cleanup --enforce`?
