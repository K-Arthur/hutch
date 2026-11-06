# Phases and checkpoints

Each phase: research, design note, small commits on `main`, real-setup validation, visual
validation if UI, review, docs. Each task touches at most three source files plus one seam. A
phase is done only when its exit checks pass and `02-PROGRESS.md` says so.

## Phase 0 - Diagnose (no feature code)

- Run `npm run check:agent` and the focused provider tests to get a baseline:
  `tests/test_provider_*.py`, `test_catalog*.py`, `test_compat.py`, `test_media_*.py`,
  `test_route_readiness.py`.
- Produce `docs/research/2026-11-provider-expansion/00-GAP-AUDIT.md`: for each of the 62
  catalogue entries and each user-listed provider missing from it (check: Opencode CLI route,
  Kimi coding as separate provider, Qwen Portal, Claude CLI delegate, Codex native runtime,
  Gemini CLI OAuth, Grok OAuth, MiniMax Coding Plan OAuth, ClawRouter, BytePlus, ds4), record
  route, protocol, status today, what is missing, ToS stance, and the owner's credential
  availability (ask once, batched).
- Capture the current Providers, Models, and first-run pages with Playwright (four widths, light
  and dark). Log defects, including the S2 contradiction.
- Mine real failures (see master prompt) and write `01-FAILURE-MINING.md` with a keep/fix/vendor
  classification and a test idea per fixable item.
- Exit: audit and failure doc committed; ordered backlog agreed in `02-PROGRESS.md`.

## Phase 1 - Core model: route resolution and status truth

- Make provider / auth profile / runtime / model an explicit resolved tuple. Seams:
  `providers/registry.py`, `providers/accounts.py`, `providers/readiness.py`.
- No silent substitution; opt-in fallback record; ambient-key labeling; migration of saved
  routes (`store.py`, fixture, `test_migration.py`).
- Exit: tests for every substitution refusal; real server run with two accounts on one provider
  and an ambient env key present.

## Phase 2 - Credential and OAuth lifecycle

- Single-flight refresh, failed-login-never-deletes, device-code and loopback callback flows that
  work headless/remote/WSL, clock-skew tolerance, revoke wording. Seams:
  `providers/accounts.py`, `runtime/opencode_login.py`, `data/oauth-apps.json`.
- Only officially documented OAuth clients or vendor CLIs; ToS-blocked routes stay blocked.
- Exit: concurrency test with real processes contending for one account; expired-token and
  revoked-token states observed in the UI.

## Phase 3 - Flagship providers (one sub-phase each, own commits)

3a OpenAI (API, ChatGPT/Codex sign-in, native Codex runtime) and 3b Anthropic (API, Claude CLI)
3c Google (Gemini API, CLI OAuth, search, media, voice) 3d xAI 3e Moonshot/Kimi (general +
coding as separate providers) 3f MiniMax 3g Qwen (Cloud, Coding Plan, Portal status) 3h Z.AI
3i OpenCode and OpenCode Go (API and CLI). Per sub-phase: adapter fixes for tool schemas,
streaming, reasoning round-trip; model list discovery that reflects what the key can use; real
live check with owner credential or a recorded block.

## Phase 4 - Hosted providers and gateways

Mistral, DeepSeek, Alibaba, Xiaomi, StepFun, Volcengine, Tencent, Qianfan, Cohere, Synthetic,
Venice, Arcee, Vydra, GMI; Bedrock, Mantle, Vertex, Cloudflare, Vercel, OpenRouter, ClawRouter,
LiteLLM, Foundry, Groq, Cerebras, Together, Fireworks, NVIDIA, Hugging Face, DeepInfra, Chutes,
Novita, Kilocode, BytePlus, Ollama Cloud. Prefer data-driven presets in `data/connections.json`
and a small adapter per wire protocol over per-provider code. Resolve regional/plan host
confusion in the wizard. SigV4 (Bedrock) and Azure/Foundry auth need a dependency decision:
ask the owner before adding any.

## Phase 5 - Local and custom endpoints

Ollama, LM Studio, vLLM, SGLang, inferrs, ds4, llama.cpp, custom APIs. Real engines where
installable. Endpoint validation, layered connectivity test, SSRF/redirect/DNS pinning, context
size warnings, not-loaded and cold-start states.

## Phase 6 - Media, speech and search

OpenAI, Google, xAI, MiniMax media; fal, ComfyUI, Runway, PixVerse; Deepgram, ElevenLabs; provider
native search vs `live_search` kept distinct. Durable resumable cancellable jobs, size bounds,
cost preview, refusal handling. Seams: `media/jobs.py`, `media/providers/base.py`, one new module
per provider.

## Phase 7 - Frontend

Catalogue filters, provider detail and per-route wizard, account list with readiness, route
picker with the resolved tuple, media section, unified Models/first-run truth. New JS modules
only (app.js frozen). Edit `app/src/`; rebuild CSS. Visual validation is a gate here, not an
afterthought: screenshots, keyboard traversal, a11y check (`a11y-debugging` skill), console
clean, reduced motion, Strict Offline state.

## Phase 8 - Marketing website and docs

Update `website/index.html`, `site.js`, `llms.txt`, `sitemap.xml` and `docs/marketing-site.md` to
claim only what is live-verified or clearly labeled by status; add an honest provider/route
coverage section generated from catalogue data, not hand-typed. Visual validation at four widths,
light/dark, no-JS fallback, Lighthouse-style checks (`debug-optimize-lcp` skill), then
`docs/models.md`, `provider-platform.md`, `runtime-setup.md`, compatibility matrix, ADR.

## Phase 9 - Whole-initiative review and merge

- Re-run all focused suites, then the fast suite once, `npm run check:agent`,
  `npm run audit:context`, focused e2e for touched pages.
- Full-diff review for god functions, secrets, silent fallbacks, status inflation, dead code,
  doc/UI/website claim agreement (grep every "supported" claim against the ledger).
- Fresh-clone check: clone to a scratch dir, run the README quick start and the Providers page.
- Everything on `main`, tree clean, worktrees reconciled, `python scripts/prune_validation_tmp.py`
  dry run reported. Final report: per provider and route, status, evidence date, and what remains
  blocked and why.

