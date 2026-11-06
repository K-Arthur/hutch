# Master prompt: provider, runtime and media expansion (2026-11)

Paste the "Launch prompt" block at the bottom into a fresh session. Everything above it is the
contract the agent reads. Work sequentially through `01-PHASES.md`; record state in
`02-PROGRESS.md`. One phase per session where possible (AGENTS.md: fresh session per task, under
about 120K tokens).

## Goal

Make Hutch's provider layer honest, complete and usable for the provider families below, with
model choice, authentication and execution runtime kept as three separate things, plus media,
speech and search services. "Complete" means a user can find a provider, sign in or add a key,
see truthfully what works, pick a model, run it, and recover from failure, all from the dashboard.

Families (reference for each: `https://docs.openclaw.ai/providers/<slug>`; the index is
`/providers`, `/concepts/model-providers`, `/providers/models#additional-provider-variants`):

- Flagship, multi-route: opencode (API + CLI), anthropic (API + Claude CLI), google (Gemini API +
  CLI OAuth, chat/search/media/voice), minimax (Coding Plan OAuth + key, chat + media), moonshot
  (Kimi general + separate Kimi coding provider), openai (API + ChatGPT/Codex sign-in + native
  Codex execution), qwen (Cloud, Coding Plan, Portal), xai (Grok OAuth + API; search, code, image,
  video, speech), zai (GLM Coding Plan + general API).
- Hosted: mistral, deepseek, opencode, opencode-go, claude-max-api-proxy, github-copilot, alibaba,
  xiaomi, stepfun, volcengine, tencent, qianfan, cohere, synthetic, venice, arcee, vydra, gmi.
- Gateways and clouds: bedrock, bedrock-mantle, anthropic-vertex, cloudflare-ai-gateway,
  vercel-ai-gateway, openrouter, clawrouter, litellm, microsoft-foundry, groq, cerebras, together,
  fireworks, nvidia, huggingface, deepinfra, chutes, novita, kilocode, byteplus, ollama-cloud.
- Local: ollama, lmstudio, vllm, sglang, inferrs, ds4, custom OpenAI/Anthropic-compatible APIs.
- Media, speech, search: OpenAI media, Google media, xAI media, MiniMax media, fal, ComfyUI,
  Runway, PixVerse, Deepgram, ElevenLabs.

Note: the source docs say "OpenClaw". Hutch is not OpenClaw; use their pages as a feature
checklist and a source of known pitfalls, never copy their wording, naming or behavior wholesale.

## Starting state (verified 2026-11-05; recheck before relying)

Much of this exists. Do not rebuild it; diagnose against it.

- 62 catalogue entries in `src/hutch/data/providers.json` (validated by
  `src/hutch/providers/catalog.py`). Statuses today: implemented (opencode, deepseek, xiaomi),
  experimental (opencode-go), blocked (github-copilot, claude-max-proxy), documented only (qwen,
  alibaba-model-studio, qianfan, vydra, bedrock, bedrock-mantle, google-vertex, anthropic-vertex,
  cloudflare-ai-gateway, vercel-ai-gateway, clawrouter, litellm, microsoft-foundry, sglang,
  inferrs, ds4, runway, pixverse, deepgram, elevenlabs), deferred (fal), the rest
  implemented-unverified. Live-verified: only DeepSeek text, managed OpenCode, Xiaomi MiMo
  (text, tools, streaming, STT, TTS).
- Guide: `docs/provider-platform.md`; ADR `docs/adr/0026-provider-identity-accounts-capabilities-and-runtimes.md`;
  research package `docs/research/2026-10-provider-platform/` (00-07; `02-FAILURES-AND-COMPLAINTS.md`
  and `03-PROVIDER-CAPABILITY-MATRIX.md` are the prior art, extend them, do not restart);
  `docs/realignment/provider-compatibility.md` and `src/hutch/data/compat.json`.
- Code seams: `src/hutch/providers/{catalog,accounts,capabilities,readiness,registry,discovery,connection}.py`;
  adapters `openai_compat.py`, `openai_responses.py`, `claude.py`, `gemini.py`, `gemini_wire.py`,
  `ollama.py`, `transcription.py`, `search.py`, `search_wire.py`; media `src/hutch/media/{jobs,routes,storage,validate}.py`
  and `src/hutch/media/providers/{base,comfyui,openai_images,speech,speech_wire}.py`; runtimes
  `src/hutch/runtime/{registry,builtin,opencode,opencode_login,opencode_server,pi}.py`; data
  `src/hutch/data/{connections,compat,oauth-apps,presets,prices}.json`.
- UI: `src/hutch/server/pages_providers.py`, `pages_models.py`, `static/providers.js`,
  `models-detect.js`, `model-switcher.js`, `connection-browser.js`; Tailwind sources in `app/src/`.
- Marketing: `website/index.html`, `site.js`, `src/input.css`, `llms.txt`, `sitemap.xml`;
  policy in `docs/marketing-site.md`.
- Known open contradictions to confirm or close: Models page vs first-run detection (S2 in
  `docs/realignment/start-state-audit-2026-10-30.md`), provider-native search blocked on
  entitlement, no private-range/redirect/DNS pinning for custom endpoints outside Strict Offline,
  video/music/image-edit/streaming TTS deferred.

## Non-negotiable rules

1. No god functions or god files. Hard cap 400 lines per new source file (AGENTS.md). Also: a
   function does one thing, aim for 40 lines or fewer, hard stop at 60; no function with more than
   4 branches of provider-specific `if/elif` (use a table or adapter per provider; the catalogue
   JSON drives data, code drives behavior). Never extend a frozen file in
   `.file-size-baseline.json`; split first (`.ai/skills/split-god-file.md`). `app.js` is frozen:
   put new UI in new modules.
2. Real setup, not fixtures. Prove behavior against the real stack: real FastAPI server on a real
   port, real SQLite migrations on a copy of a persisted state, real browser (Playwright
   Chromium), real local engines (an actual Ollama, llama.cpp/vLLM/LM Studio-compatible server if
   installable offline; otherwise state precisely what could not be run). Mocks are allowed only
   to unit-test pure parsing and for failure injection that a real server cannot produce on
   demand (429, 5xx, truncated stream, expired token). A mock never upgrades a status above
   implemented-unverified, and no recorded fixture counts as live evidence. For paid or
   subscription providers: use only credentials the owner already provisioned, never spend money
   or create accounts, and when none exist record "blocked: no credential" with the exact missing
   input. Do not fake a green result. Before the first paid call per provider, stop and tell the
   owner what will be spent (cap it at a few cents with a token limit).
3. Terms of service are a design input. Subscription-backed routes (Claude Max/Pro, ChatGPT
   Codex, Copilot, Gemini CLI OAuth, Grok OAuth, Qwen Portal, Coding Plans) must go through the
   vendor's own official CLI or an officially documented OAuth client. Research each vendor's
   current policy on third-party use of subscription tokens (several vendors have banned or
   throttled it) and record the citation. If it is prohibited, ship the route as "blocked" with
   the reason in the UI. Do not scrape tokens from other tools' files or reimplement private
   endpoints.
4. Preserve the local-first, explicit-approval model. No new tool, permission, data sharing or
   ambient credential use as a side effect. Credentials never appear in API responses, logs,
   pages, screenshots, commits or the DB (`Tool.recorded_arguments` redaction). Never read `.env*`,
   `*.db*`, `.state/`, `.aws/`, `.ssh/`.
5. Honest status vocabulary only (implemented, implemented-unverified, experimental, documented,
   blocked, retired, deferred). A catalogue entry is not a support claim. UI, docs and the
   marketing site must not say "supported" for anything lacking a dated live-verified record.
6. Contract discipline: any new or changed tool has canonical JSON Schema in `Tool.parameters`,
   catalogue entry in `tools/__init__.py`, contract tests (valid accepted, invalid refused before
   dispatch), and passes `npm run check:agent`. Reuse `toolcalling/`; no second registry or
   validator.
7. Persisted state: pydantic models plus an ordered migration in `store.py` with a
   `tests/fixtures/` compatibility input and `test_migration.py` coverage. Timestamps via
   `models.iso`/`models.utcnow`.
8. Use main. Commit directly on `main`, one focused change per commit, explicit paths, concise
   imperative messages, no AI-attribution trailer. Use a worktree only for a risky spike, and
   merge it back to `main` within the same phase; never leave work stranded on a branch. Never
   push, tag, publish, deploy, add dependencies (ask first), or touch another session's
   uncommitted work. `.commandcode/` is untracked and not yours.
9. No emoji in source, docs or UI. Edit `app/src/` and `website/src/`, never generated CSS; run
   `npm run build:css --silent` after CSS source changes.
10. Be surgical with context. Read line ranges, name exact files. Never read lockfiles,
    CHANGELOG, generated CSS, evidence artifacts, `.worktrees/`, `node_modules/`, `.venv/`. Do not
    "review the codebase".

## Research requirements (mandatory, before design in each phase)

Do this with live web search and by reading the linked OpenClaw pages for the families in that
phase. Record each source with URL, date accessed and what it changed in
`docs/research/2026-11-provider-expansion/` (extend, do not duplicate, the 2026-10 package).

Per provider, answer: current official model ids and naming; auth routes and exactly which are
API-key vs OAuth vs CLI; endpoint(s) and regions; protocol (OpenAI chat, Responses, Anthropic
Messages, Gemini, native); tool-calling, streaming and reasoning quirks; rate-limit and quota
behavior and its headers; pricing source; media endpoints; deprecations; ToS stance on
third-party use.

Failure research (equally mandatory; the point is to avoid repeating other apps' mistakes).
Mine GitHub issues, Reddit, Hacker News and forums for OpenClaw, OpenCode, Cline, Roo, Continue,
Aider, LiteLLM, OpenRouter clients, Open WebUI, LibreChat, Cursor, Codex CLI, Claude Code and
Gemini CLI. Capture the recurring complaints and classify each as fixable-in-Hutch, mitigable, or
vendor-side:

- model list stale, wrong, or showing models the key cannot use; context-window and max-token
  mismatches; silent fallback to another model or account;
- OAuth refresh races and logout loops, token expiry with a misleading "connected" badge,
  headless/remote/WSL sign-in failures, port-in-use callbacks, clock skew;
- ambient env keys silently overriding the chosen account and billing the wrong one; key leakage
  in logs or the UI;
- quota and 429 handling (retry storms, no Retry-After respect, ambiguous "quota" vs "rate" vs
  "billing" errors, unexpected spend on gateways);
- tool-call schema rejections per provider (strict-mode, unsupported keywords, empty arrays,
  parallel calls), thinking-block and reasoning-content round-trip errors, streaming that drops
  deltas or hangs;
- custom base-URL pitfalls (trailing `/v1`, path rewriting, self-signed TLS, SSRF),
  local-engine pitfalls (model not loaded, context truncated by default, cold start timeouts);
- regional endpoint confusion (China vs international, Coding Plan vs pay-as-you-go hosts that
  look alike but are billed differently);
- media: async job polling that never resolves, expired result URLs, huge files in memory,
  silent format conversion, cost surprises, content-policy refusals presented as crashes.

## Required design deliverables (account for gaps the owner did not list)

Treat each as in scope; if a gap is not solvable now, log it as deferred with reason.

- Three-way separation in data and UI: model choice, auth profile (named account, credential
  source, billing relationship: API key / subscription / free), execution runtime (built-in,
  managed OpenCode, official CLI delegate). A model spec resolves to exactly one of each, shown
  before the first send, never substituted silently.
- Same model, many routes: e.g. Claude via Anthropic API, Vertex, Bedrock, OpenRouter, CLI. Show
  cost and capability differences per route; per-route failure never reroutes without consent.
- Fallback policy is opt-in, explicit, visible in the transcript, and never crosses billing
  relationship (subscription to metered) without approval.
- Credential lifecycle: add, test (bounded, no inference unless user clicks "test with one
  token"), rotate, expire, revoke, remove-local, with accurate wording about what each does.
  Single-flight token refresh per account; no process-wide lock; failed refresh never deletes the
  stored credential.
- Readiness honesty: needs-auth, expired, subscription-restricted, model-unavailable,
  endpoint-unavailable, capability-unverified, unsupported-runtime, needs-config, policy-blocked.
- Capability evidence per model and route (text, tools, streaming, reasoning, vision, audio in,
  speech out, image, video, music, search, JSON schema output, context window) with dated sources.
- Usage and cost: pre-call reservation stays built-in-only; show cost basis, unknown-price
  handling, and subscription "no per-token price" correctly; gateway markups.
- Custom endpoints: validation (scheme, `/v1` normalization, TLS, redirect and DNS-rebinding
  pinning, private-range allowlist outside Strict Offline), a connectivity test that says which
  layer failed (DNS, TLS, auth, model list, completion).
- Local engines: detect running servers on loopback, list loaded models, warn on small default
  context, surface model-not-loaded and cold-start as states, not errors.
- Media jobs: durable, resumable, cancellable, bounded size, cost estimate before submit, result
  stored with SHA-256 via `media/storage.py`, content-policy refusal shown as a refusal.
- Accessibility, keyboard flow, empty/error/loading states, offline/Strict Offline behavior,
  desktop (Tauri) parity, and upgrade migration of existing saved routes.
- Frontend: catalogue search/filter by category, auth route, capability and status; a provider
  detail view with a sign-in/add-key wizard per route; an account list with live readiness;
  a route/model picker that exposes the three-way resolution; a media/speech/search section.
  Resolve the Models vs first-run contradiction. Follow `docs/design-system.md` and the
  `impeccable` skill for UI work; no fixture-driven preview pages in `static/`.

## Validation and review gates

Per phase, in order, and report exact commands and results:

1. Focused tests: `npm run test:agent -- tests/test_<x>.py` for every touched behavior; add tests
   that fail before the change.
2. `npm run check:agent`; `npm run audit:context` when files grew.
3. Real-setup run: start the real server, exercise the route end to end (real engine or the
   owner-provisioned credential), capture the result in the ledger
   (`docs/research/2026-10-provider-platform/06-VALIDATION-LEDGER.md` style: date, route, model,
   what was and was not exercised).
4. Visual validation for any UI or website change: Playwright screenshots at 360, 768, 1280 and
   1920 px, light and dark, plus keyboard-only traversal and console-error check; use the existing
   `docs/realignment/capture_*.py` pattern; look at the images and record defects found and fixed;
   zero console errors, zero horizontal overflow. Run focused `tests/e2e/` for touched pages only.
5. Code review: re-read the full diff of the phase as a skeptical reviewer; hunt for god
   functions, credential leakage, silent fallbacks, status inflation, missing error states, dead
   code. Fix, then record findings in the progress file. A final whole-initiative review runs at
   the end of phase 9.
6. Docs updated in the same commit series: `docs/provider-platform.md`, `docs/models.md`,
   `docs/runtime-setup.md`, `docs/realignment/provider-compatibility.md`, `compat.json`, the
   research package, and an ADR (next number after 0026) for any decision that changes a
   boundary.
7. Merge state: everything on `main`, working tree clean except others' work, worktrees removed
   only if fully merged.

## Stop conditions

Ask the owner (once, batched) only for: spending money, a missing credential needed for a live
check, adding a dependency, pushing/publishing, or an irreversible product choice. Otherwise
decide, log the decision and reason in the progress file, and continue. If blocked, say exactly
what is blocking and stop that item; do not simulate success.

## Launch prompt (paste into a fresh session)

```
Read, in this order and nothing else first: @AGENTS.md,
@docs/realignment/provider-expansion-2026-11/00-MASTER-PROMPT.md,
@docs/realignment/provider-expansion-2026-11/01-PHASES.md,
@docs/realignment/provider-expansion-2026-11/02-PROGRESS.md.

Resume at the first phase in 02-PROGRESS.md not marked done. Do only that phase in this
session: research (live web, plus failure/complaint mining, recorded under
docs/research/2026-11-provider-expansion/), a short written design with the files you will touch
(max 3 source files plus one seam per task; split the phase into tasks), then implement in small
commits on main, then run the validation and review gates from the master prompt using the real
stack, then update docs and, where the phase says so, the marketing site. No god functions, no
fixture-only validation, no status inflation, no spending or credentials without asking. Update
02-PROGRESS.md at each checkpoint (what is committed, what was verified live, what is blocked,
decisions made) and finish by stating the next phase. Do not stop at a task boundary inside the
phase.
```

