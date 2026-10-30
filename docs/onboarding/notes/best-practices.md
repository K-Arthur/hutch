# Best-in-class first-run mechanics for Hutch onboarding (2026-10-29)

Live-web research note for Hutch's first-run AI-readiness surface. Nothing here is a claim about Hutch's current code; Hutch steps are marked "TBD, Lead to verify". Every URL was opened on 2026-10-29 unless marked otherwise.

## Method and limits

- Eight products closest to Hutch's situation: self-hosted/local-first chat UIs (Open WebUI, Jan, LM Studio, Ollama, HuggingChat), a self-hosted automation platform with an AI setup wizard (n8n), a local-first device platform with browser onboarding (Home Assistant), and an agent CLI with provider login (OpenCode).
- Primary sources: official docs, merged-PR descriptions that state shipped behaviour, and the live HuggingChat page. GitHub issue bodies are individual reports; they are catalogued in failure-catalog.md, not used here as prevalence evidence.
- Vendor time claims are quoted as claims. No first run was executed and no screen was measured; "observed" below means the page text/behaviour was read, not that the product was installed.
- Hutch context: local-first, MIT, in development preview, no hosted sign-up, no payment, no KYC. Cloud-trial mechanics are marked as not transferable.

## Table 1. Observed path to first output

| Product | Entry | Step 1 | Step 2 | Step 3 | Deferred or skipped | First-value claim |
|---|---|---|---|---|---|---|
| Open WebUI | Docs: install method table (Docker recommended, Python, Kubernetes, desktop) | Run one docker command with a fixed WEBUI_SECRET_KEY and a data volume | Open localhost:3000; first screen says "Get started with Open WebUI" and offers "Create Admin Account" | Avatar > Settings > Admin > Connections; add Ollama URL or a hosted API key; models appear in the dropdown; send a short test message | Plugins, RAG, web search, tools, sharing/SSO all moved to "Essentials" and later pages | "From zero to your first AI conversation in under five minutes" (headline; quick-start text does not quantify setup) |
| Jan | Install desktop app | Launch: "Jan automatically downloads its default foundation model on first launch" | Type a message in the default chat | Optional: Hub for more local models; Settings > Model Providers to paste a cloud API key | Provider choice, key entry, model install are skipped for the default local path; Projects/Assistants/Agents/MCP are deferred | "Get up and running with Jan in minutes... no setup required" |
| LM Studio | Install app | Discover tab: pick a curated model or search | Download | Chat tab > open model loader > select downloaded model (optional load config) > chat | No account and no provider configuration for local use; documents/MCP/API server deferred; fully offline after model download | No time claim observed; hardware requirements documented up front |
| Ollama | Download app or open terminal | Run "ollama" and "follow the setup prompts" | Sign in for cloud models, or choose a local model; local model download is about 7.2 GB with an 8 GB VRAM/unified-memory recommendation | Chat in terminal, or use integrations (Claude, ChatGPT, coding agents) via ollama launch | Cloud account/API key skipped for local; integrations deferred | No time claim; download size and memory stated before the heavy step |
| n8n (self-hosted) | Host an instance (or cloud trial) | Tutorial: Create workflow, name it | Schedule Trigger only (no real credentials) | Add HTTP Request node against a sample-data service, format with Edit Fields, save to a data table, execute each step, then publish | No accounts, API keys or coding needed for the tutorial; real integrations deferred | "The build takes about 15 minutes" |
| Home Assistant | Open the local address | "Preparing Home Assistant" downloads the latest version; "may take 20 minutes or more" | Welcome screen: "Create my smart home" owner account (Name, Username, Password, Confirm) or restore a backup | Home location (search or one-time "Detect"), country/units, optional anonymised sharing (off by default), final screen "We found compatible devices!" or "All set!" | Device integrations deferred or partially pre-added; settings changeable later | "The entire onboarding takes only a few minutes" (after preparation) |
| OpenCode | Install script, npm/bun/pnpm, Homebrew, pacman, Docker | Run "opencode"; configure a provider with /connect. For newcomers it recommends OpenCode Zen: browser sign-in, billing, copy key, paste | Run /models and pick a model | cd into a project, run /init to generate AGENTS.md, then ask a question | Project init and provider breadth deferred; 75+ providers are optional | No time claim |
| HuggingChat | Open the public page | Welcome copy: "Omni automatically picks the best AI model... You can also choose from any available open source models" | "Start chatting" | Optional model picker (page showed "Models 137") | No model/provider decision required; account requirement not tested (unverified) | None observed |

## Table 2. First-run surface specifics

| Product | Provider/model selection | Empty state and sample prompts | Progress and state copy | Exit and resume |
|---|---|---|---|---|
| Open WebUI | Admin-only Connections screen; "Open WebUI has no models of its own"; Ollama on the same machine is auto-detected at host.docker.internal:11434 (Docker) or localhost:11434 (Python) | Docs pages are the empty-state teaching surface, not the app; quick start tells the admin to start a conversation with each provider and send a test message | Symptom-indexed troubleshooting table ("Can't connect to Ollama", "Model list takes forever to load / 500 on /api/models") | Volume documented as "never run without it"; fixed WEBUI_SECRET_KEY because "every recreated container logs everyone out" |
| Jan | Default local model auto-downloaded; Hub marks "whether it fits your hardware"; cloud providers via Settings > Model Providers with pasted key | Quick start lists three example asks, e.g. "Explain quantum computing in simple terms" | PR #8594: wizard pages for welcome, backend install, embedding download, analytics consent; "each stage reports its own progress" | PR #8594: "a failed stage is skippable rather than terminal"; readiness is probed by actually loading a model |
| LM Studio | Discover tab is the model catalog; Chat tab model loader | Getting-started page prescribes a sequence rather than prompts; system requirements state RAM/VRAM/AVX2 and unsupported Intel Macs | Download managed in Discover; no first-run wizard observed | Offline operation documented: "get some model files first" |
| Ollama | "Sign in to use cloud models, or choose a local model"; no account for local | Quick start's first request is a single "Say hello in one sentence" example | Download size and memory guidance before pull; server logs documented per OS with OLLAMA_DEBUG | /bye leaves terminal chat; no setup state to resume |
| n8n | Tutorial avoids credentials entirely; real credentials live in a separate resource list | One shared empty-state card per resource: title "Create your first automation", CTA "Create workflow", matching the header button | Per-node "Execute step" output before publish; empty-state skeleton while first-run counts load | Workflow name persisted on canvas click; self-hosted AI setup keeps incomplete setups hidden from members and asks only for missing steps |
| Home Assistant | No model/provider choice; device discovery is the final screen | Final screens are conditional: "We found compatible devices!" with an integration list, or "All set!" | Dedicated preparing page before welcome; owner credentials explicitly unrecoverable | Restore-from-backup offered on the welcome screen before account creation |
| OpenCode | /connect stores keys in auth.json; Zen recommended first, then 75+ providers; /models picker; blacklist/whitelist to hide models | Intro gives example tasks ("How is authentication handled in @file"); /init is the first guided action | Provider errors surface raw ("Waiting for authorization" in issue #7992) | Keys persist in auth.json; AGENTS.md persists project context |
| HuggingChat | Omni router by default; per-model displayName and description shown in the model list | Welcome paragraph explains the product; single "Start chatting" action | No checklist or progress; disclaimer notice present | No setup state; new-model default applies only to new users (PR #672) |

## Patterns worth adopting

1. Choose a default route for the user, then make the choice visible and reversible. Jan downloads a default local model at launch and says "no setup required"; HuggingChat defaults to a router that selects a model automatically. The counter-example is Jan #7658, where "Select a model" was the first screen and no model was pre-selected.
2. Make the first screen one sentence and one action. Open WebUI's first screen is "Create Admin Account"; Home Assistant's welcome screen is create-account or restore. NN/g's small qualitative study of first-time gen-AI users recommends avoiding long tutorials and skipping onboarding when possible.
3. Probe readiness; do not infer it from configuration. n8n's self-hosted AI onboarding does "live verification before setup completes"; Jan's PR #8594 loads a model to confirm the installed backend actually runs on this machine. A /models ping is not proof of chat capability: OpenCode issue #38257 shows /v1/models working while chat/completions returned 401.
4. Separate "saved" from "verified" in copy. n8n's wizard only requires missing steps and never reveals environment-managed server values; Jan's readiness is probed rather than assumed. Hutch should not label a saved workspace default "ready" without a probe (TBD: current copy is being audited by the Lead).
5. Stage the flow so a failed stage is skippable rather than terminal. Jan PR #8594's wizard is paged, reports per-stage progress, and "a failed stage is skippable rather than terminal". Home Assistant separates a potentially 20-minute preparation page from three short onboarding steps.
6. State the cost of the heavy step before it starts. Ollama states the ~7.2 GB download and memory recommendation; Home Assistant warns preparation may take 20 minutes or more; LM Studio publishes 16 GB+ RAM, AVX2 and no-Intel-Mac limits before install.
7. Use sample data for the first success so real credentials are optional. n8n's first workflow needs "no accounts, API keys, or coding experience" because it uses a sample weather API, and each node is executed to show output before publish.
8. Treat empty states as first-run surfaces and unify them. n8n PR #33670 found inconsistent title voice, CTA labels, layout and icons across first-run empty states plus list chrome flashing; the fix was one shared empty-state card with CTA labels reusing the exact i18n keys of the header create buttons.
9. Keep any checklist short, optional and instrumented. n8n added events to enable an onboarding checklist (PR #5536) and later shipped a change where "the sidebar onboarding checklist can be turned off (now disabled)" (PR #35734). NN/g again: skip onboarding when possible.
10. Give model choices short, task-oriented descriptions and fit signals. HuggingChat returns displayName and description per model plus a router description; Jan's Hub shows fit; OpenCode recommends a tested default before listing 75+ providers.
11. Provide a symptom-indexed failure surface. Open WebUI's troubleshooting page maps user-visible symptoms to guides; Ollama's page gives exact log locations per OS and OLLAMA_DEBUG. Error copy should say where to look, not just "failed".
12. Persist keys and position outside the page. OpenCode stores /connect keys in auth.json; Open WebUI warns to fix WEBUI_SECRET_KEY so recreated containers do not log everyone out; Home Assistant offers backup restore before account creation.

## Copy patterns observed (usable strings, not tone advice)

| Product | Where | Observed string | What it does |
|---|---|---|---|
| Open WebUI | First screen | "Get started with Open WebUI" with "Create Admin Account" | Names the product and the single next action |
| Open WebUI | Quick start | "Open WebUI has no models of its own." | Sets the mental model before asking for a URL/key |
| Open WebUI | Quick start | "never run without it" (about the data volume) | Warns about the exact mistake that loses state |
| Jan | First launch | "Jan automatically downloads its default foundation model on first launch... no setup required." | Removes the model decision from the first run |
| Jan | Hub | Each model shows "whether it fits your hardware" | Prevents a dead end before the download |
| LM Studio | Getting started | "Load a model to memory... Then start a back-and-forth conversation." | Explains the hidden step local chat needs |
| Ollama | Quick start | "Sign in to use cloud models, or choose a local model." | Two routes, one sentence, no account required for local |
| n8n | Empty state | Title "Create your first automation", CTA "Create workflow" | CTA labels reuse the header button's exact keys, so copy cannot drift |
| n8n | Tutorial | "Apart from n8n, you don't need any accounts, API keys, or coding experience." | Removes the three fears before the first step |
| n8n | Self-hosted AI setup | "only require the missing steps and should not reveal server values" (test criteria) | Handles operator-managed configuration explicitly |
| Home Assistant | Welcome | "Create my smart home" or restore a backup | Puts recovery on the same screen as the forward path |
| Home Assistant | Final step | "We found compatible devices!" / "All set!" | Conditional success copy instead of a generic done |
| HuggingChat | Welcome | "Omni automatically picks the best AI model... You can also choose from any available open source models." | Default plus escape hatch in two sentences |
| OpenCode | Providers | "If you are new, we recommend starting with OpenCode Zen." | Recommends one tested route before listing 75+ |

## Anti-patterns observed (do not copy)

- A generic "Select a model" placeholder as the first chat state (Jan #7658).
- Defaulting to a cloud model and surfacing an API-key error when no model exists (Jan #3537: "we default a cloud model and show API key error, which is not cool").
- Silent download progress: Jan #7728 reports "stalled in Initializing Download... no message in the console".
- Tours and mandatory setup gates: an HN comment on a tour library says tours are "often just poorly implemented, with too many steps that don't mean anything to the user"; NN/g says avoid long onboarding tutorials.
- Onboarding controls that fall below the viewport on mobile browsers (Open WebUI #16287).
- Personalised/emoji empty states that drift from the real action labels (removed in n8n PR #33670).

## Translation to Hutch (TBD against code)

| Pattern | Hutch first-run surface | Adopt how | Do not copy |
|---|---|---|---|
| Default route first | AI service picker beside the request | Show a discovered local route as "Ready" only after a probe; otherwise a clear "Choose AI" action | Silent fallback to a hosted provider |
| Verify before success | First useful output | Send a real test generation before declaring the route ready | Treating a saved key or reachable URL as verified |
| Progressive disclosure | Request, then model/bot/channels | Model route is P1; bot naming/style and channels are optional after first output | A linear wizard that blocks chat |
| Sample request | Empty composer | Editable example requests tied to what Hutch can do locally | Auto-sending a request without consent |
| Per-stage progress | Provider probe/connection | Per-route status: checking, needs key, timeout, ready, failed with retry | One global "No AI available" for partial failures |
| Optional checklist | Readiness panel | Dismissible, reflects real state, no fake progress | Mandatory setup checklist before chat |
| Secret handling | API key and bot-token fields | Paste works, masked, server-side only, never echoed | Terminal-style hidden paste with no hint |
| Resume | Draft request + chosen route | Persist across reload and provider detours (repo prior research proposes sessionStorage) | Clearing the draft on navigation |
| Modality honesty | Terms/channel steps | Copy says what is sent where; no KYC-style claims | Document upload/liveness/signature steps Hutch does not need |

## Open questions for code inspection

- Actual step count and order of Hutch's current first-run; whether provider readiness is probed or inferred.
- Whether a local route (Ollama/OpenAI-compatible) is auto-discovered and how failures are worded.
- Where the draft request and chosen route are stored, and what survives reload/navigation.
- Whether first-run includes channel connection (Telegram token, QR pairing) or defers it.
- How the Tauri desktop host changes restart/resume and localhost assumptions versus the served dashboard.

## Sources (accessed 2026-10-29)

| URL | Title | Type | Supports |
|---|---|---|---|
| https://docs.openwebui.com/getting-started.md | Getting Started with Open WebUI | primary | install/provider summary, deferral |
| https://docs.openwebui.com/getting-started/quick-start.md | Quick Start | primary | admin account, volume/warning, auto-detect Ollama, test message |
| https://docs.openwebui.com/getting-started/quick-start/connect-a-provider.md | Connect Local and Cloud Models | primary | provider fields, model dropdown, test-message step |
| https://docs.openwebui.com/troubleshooting/ | Troubleshooting | primary | symptom-indexed failure surface |
| https://www.jan.ai/docs/desktop/quickstart (redirected to https://docs.jan.ai/desktop/quickstart) | Jan Quickstart | primary | auto default model, sample prompts, cloud key path, Hub fit |
| https://github.com/janhq/jan/pull/8594 | feat(onboarding): guided first-run setup wizard | primary | staged wizard, progress, skippable stages, readiness probe |
| https://github.com/lmstudio-ai/docs/blob/28fdbdd4/0_app/1_basics/index.md (rendered at https://lmstudio.ai/docs/app/basics) | Get started with LM Studio | primary | Discover/load/chat sequence, offline |
| https://lmstudio.ai/docs/app/system-requirements | System Requirements | primary | hardware gate before first value |
| https://docs.ollama.com/quickstart.md | Ollama Quickstart | primary | setup prompts, local/cloud, 7.2 GB note |
| https://docs.ollama.com/troubleshooting | Ollama Troubleshooting | primary | per-OS logs, debug flag, GPU library selection |
| https://docs.n8n.io/try-it-out.md | Build your first workflow | primary | 15-minute claim, no credentials, sample API, Execute step |
| https://github.com/n8n-io/n8n/pull/35579 | feat: Add self-hosted AI Assistant onboarding | primary | live verification, missing-steps-only, hidden incomplete setup |
| https://github.com/n8n-io/n8n/pull/33670 | Unify onboarding empty states | primary | empty-state consistency and copy mechanics |
| https://github.com/n8n-io/n8n/pull/5536 | Add events to enable onboarding checklist | primary | checklist instrumentation intent |
| https://github.com/n8n-io/n8n/pull/35734 | Tidy Storybook for Figma import | primary | checklist can be turned off/disabled |
| https://www.home-assistant.io/getting-started/onboarding/ | Onboarding Home Assistant | primary | three steps, fields, preparing time, discovery final screen |
| https://opencode.ai/docs/ | OpenCode Intro | primary | install, /connect, /init, examples |
| https://opencode.ai/docs/providers/ | OpenCode Providers | primary | /connect, auth.json, Zen recommendation, 75+ providers, model hiding |
| https://huggingface.co/chat/ | HuggingChat live page | primary (observed) | welcome copy, Omni default, Start chatting, 137 models |
| https://github.com/huggingface/chat-ui/pull/672 | Make mixtral the default model for new users | primary | per-new-user default behaviour |
| https://www.nngroup.com/articles/new-AI-users-onboarding/ | New Users Need Support with Generative-AI Tools | primary (qual, n=6) | avoid long tutorials, skip onboarding, tool naming |
| https://news.ycombinator.com/item?id=36851650 | HN comment on Driver.js product tours | anecdote | tour fatigue mechanism |
