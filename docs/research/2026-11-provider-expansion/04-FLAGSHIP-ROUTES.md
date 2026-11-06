# 04 - Flagship providers (Phase 3): research, design and result

Date: 2026-11-06. Phase 3 of `docs/realignment/provider-expansion-2026-11/`. Extends
`00-GAP-AUDIT.md` (G2, G3, G6, G7, G8, G9, G10) and `01-FAILURE-MINING.md`; it does not repeat
them. A status below is a catalogue statement, not a support claim: nothing in this phase was
exercised against a live provider account (see "Live checks").

## Sources read (all accessed 2026-11-06)

| Source | What it changed |
|---|---|
| https://docs.openclaw.ai/providers/moonshot | Moonshot and Kimi Coding are separate providers: different key, endpoint, model refs. Kimi Coding speaks Anthropic Messages at `https://api.kimi.com/coding`; also OpenAI-compatible at `/coding/v1`. Confirms G2. Model ids move quickly (`kimi-k3`, `kimi-k3.1-pro`, `kimi-k2.7-code`, `kimi-for-coding`); K3 fixes sampling parameters, so Hutch must not assume `temperature` is honored. |
| https://www.kimi.com/code/docs/en/ (vendor) | Members may use their key in third-party tools. "Tampering with the client identifier (User-Agent) is considered a violation and may result in suspension of membership benefits." Design input: ack notice, Hutch keeps its own User-Agent. |
| https://docs.openclaw.ai/providers/qwen | Hosts: Standard `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (Singapore) and `https://dashscope.aliyuncs.com/compatible-mode/v1` (Beijing); Coding Plan `https://coding-intl.dashscope.aliyuncs.com/v1`; Token Plan keys start `sk-sp-`. Plan and region keys are not interchangeable. An env var name does not select a plan or region (the OpenClaw page notes a bare `QWEN_API_KEY` defaults to the Coding Plan host; that is the wrong-bill pitfall Hutch must not copy). |
| https://www.alibabacloud.com/help/en/model-studio/coding-plan (vendor) | "Prohibition of API calls: This plan is for interactive use in programming tools such as Claude Code, Qoder and OpenClaw. Do not use the plan's API key for automated scripts, application backends, or other non-interactive scenarios ... may result in subscription suspension or API key revocation." Hutch bots are unattended, so the Coding Plan route is blocked (G3). |
| https://docs.z.ai/devpack/usage-policy (vendor, page metadata `dateModified` 2026-11-02) | "GLM Coding Plan may only be used within officially supported tools and products. Use in unsupported tools may result in restricted benefits." Hutch is not a listed tool, so the coding endpoint stays blocked (G9). |
| https://docs.openclaw.ai/providers/zai | China host `https://open.bigmodel.cn/api/paas/v4`; coding endpoints `/api/coding/paas/v4` on both hosts; Coding Plan quota is drawn only on the coding endpoint, general endpoint bills the pay-as-you-go balance. |
| https://docs.openclaw.ai/providers/minimax | International `api.minimax.io`, China `api.minimaxi.com`; OAuth (Coding Plan) uses a separate `minimax-portal` identity and refuses to refresh across regions; M2.x can emit `reasoning_content` in Anthropic-path streaming deltas even when thinking is "disabled". Plan terms for third-party use were not confirmed from a primary page (the MiniMax token-plan page is client-rendered and returned no policy text), so the plan route stays documented. |
| https://docs.openclaw.ai/providers/xai | Grok OAuth uses xAI's shared OAuth client (the consent screen may show another app's name) and device-code sign-in. A shared client that is not registered to Hutch is not an "officially documented OAuth client" for Hutch; no xAI policy page covering third-party subscription use was found. Route stays documented (G7). |
| https://opencode.ai/docs/zen/ (vendor) | Zen (pay-as-you-go API) base URLs moved to `https://opencode.ai/inference/...`; each model has a native API (GPT: Responses, Claude: Messages, open models: chat completions) and the console translates between them. Free-tier chat models require the OpenCode client. |
| `GET https://opencode.ai/inference/v1/models` and `/zen/v1/models` (no key) | HTTP 200, `application/json`, identical 96,452-byte bodies on 2026-11-06: `/zen/v1` is a legacy alias. The public list means model discovery needs no credential, but chat does. |
| https://docs.openclaw.ai/providers/openai , `/anthropic` | OpenAI explicitly supports subscription OAuth in external tools; native runtime (Codex app-server) is selected by explicit runtime policy, never by the `openai/*` prefix. Anthropic: `claude-cli/*` is a separate explicit runtime and "a Claude CLI selection does not silently switch to the direct API". Both match the Hutch three-way separation; neither is implemented yet (G4, G5). |
| Gemini CLI terms and Google notice (recorded in `01-FAILURE-MINING.md`) | Gemini CLI replaced by Antigravity CLI on 2026-06-18; third-party use of Gemini CLI OAuth is a terms violation. `coding_cli` removed from Hutch's Google services (G6). |

## Failure patterns that applied here

| Pattern | Class | Phase 3 response |
|---|---|---|
| Coding-plan key pasted into a general route silently bills the pay-as-you-go balance (Z.AI, Qwen) | fixable-in-Hutch | Plan routes are separate identities or blocked; a test asserts no template targets a plan endpoint. |
| Region mismatch (international key on China host and the reverse) | fixable-in-Hutch | Regional templates use distinct base URLs and distinct env var names; asserted by test. |
| Env var name implies a plan or region (`QWEN_API_KEY` defaults to the Coding Plan host in another app) | fixable-in-Hutch | Qwen templates name their region in the id and use `DASHSCOPE_API_KEY` / `DASHSCOPE_CN_API_KEY`. |
| Vendor flags clients that alter their User-Agent (Kimi Code, OpenCode Go) | mitigable | Acknowledged notice; Hutch never impersonates. |
| Model catalogue drift (kimi, qwen, minimax ids change monthly) | mitigable | Templates with no verified vendor list set `models_endpoint` false and say so; they do not ship a hardcoded id list. |
| Reasoning text leaking into visible output (MiniMax M2.x, Kimi Coding K2 backend) | vendor-side, partly mitigated | `openai_compat` already keeps `reasoning_content` in `thinking`, not content. The Anthropic-path variant is not exercised: recorded as unverified. |

## Decisions

1. `kimi-coding` is its own catalogue identity (category `subscription_service`, Anthropic
   Messages, `KIMI_API_KEY`, membership billing, ack-required). The `kimi-coding-key` auth method
   was removed from `moonshot`; `moonshot-cn` was added for the China host. Status:
   implemented-unverified. No model list is read.
2. `qwen` gets Standard (pay-as-you-go) templates for the international and China hosts. The
   Coding Plan auth method is `blocked` (interactive-only terms). Token Plan is not offered.
   Status: implemented-unverified. No model list is read.
3. `zai` gets `zai-cn`. The Coding Plan auth method is `blocked` (supported-tools-only policy).
4. `opencode-zen` is a new gateway identity on `https://opencode.ai/inference/v1`, pay-as-you-go,
   separate from OpenCode Go and from the managed `opencode` runtime. Status:
   implemented-unverified. GPT-through-Responses and Claude-through-Messages native routes are not
   offered by a generic connection.
5. `google` loses `coding_cli`; Antigravity is not modeled (a vendor CLI delegate, if ever added,
   goes through the Phase 3b runtime contract, not an OAuth import).
6. Not done in this phase, deliberately: the Claude CLI delegate and the Codex app-server runtime
   (3a/3b). Each needs a governed executor contract (approvals, spend, cancellation, session
   isolation) larger than the 3-file rule, and each needs the owner's own CLI sign-in to verify.
   They stay `documented` with design intent recorded in `02-PROGRESS.md`.
7. MiniMax plan/portal and xAI OAuth stay `documented`: no confirmed official third-party policy
   or Hutch-registered OAuth client.

## Files touched

`src/hutch/data/providers.json`, `src/hutch/data/connections.json` (data, one seam: catalogue),
`tests/test_flagship_routes.py`, count updates in `tests/test_provider_capabilities.py`,
`tests/test_provider_catalog.py`, `tests/test_provider_surfaces.py` and
`tests/test_provider_routes.py` (62 to 64 providers, 37 to 43 templates, multi-template check).

## Live checks and real-stack validation

- **Owner-approved provider calls (OpenAI, Anthropic, Google Gemini)**: the owner approved reading
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY` from the shell
  environment and running up to a 5-cent generation check per route. All four variables were unset in
  the environment (`OPENAI_API_KEY: unset`, `ANTHROPIC_API_KEY: unset`, `GEMINI_API_KEY: unset`,
  `GOOGLE_API_KEY: unset`), and `AGENTS.md` forbids reading `.env*`, `.state/`, `*.db*` or host
  credential stores. Zero paid calls were made; all three routes remain `implemented-unverified`
  (`blocked: no credential in shell environment`).
- **Unauthenticated vendor probe**: `GET https://opencode.ai/inference/v1/models` and
  `GET https://opencode.ai/zen/v1/models` returned HTTP 200 (`application/json`, 96,452 bytes) on
  2026-11-06 without a key. That proves the public model-list endpoint and the `/zen/v1` alias; it
  does not prove authenticated chat, so `opencode-zen` remains `implemented-unverified`.
- **Real Hutch stack**: ran `hutch init` and `hutch serve --port 18891` on an isolated temporary
  `HUTCH_STATE_DIR`, added `kimi` (`kimi-coding`), `zen` (`opencode-zen`) and `qwen`
  (`qwen-standard-intl`) via `hutch connections add`, verified `hutch connections test` fails fast
  naming `KIMI_API_KEY` and `OPENCODE_API_KEY`, and verified
  `GET /api/v1/provider-resolution?spec=kimi-coding/kimi-for-coding` resolves to
  `provider=kimi-coding`, `protocol=anthropic`, `runtime=builtin`, `status=needs_configuration`,
  `substituted=false`.
- **Visual validation**: `docs/realignment/capture_provider_pages.py --url http://127.0.0.1:18891
  --allow-populated --output docs/realignment/artifacts/provider-expansion-2026-11/phase3` captured
  32 screenshots across `providers`, `models`, `connections` and `first-run` at 360/768/1280/1920 px
  in light and dark. Result: 32/32 status 200, 0 px horizontal overflow, 0 console errors, 0 failed
  requests. Inspected `providers-dark-1280.png` and `connections-dark-360.png`: the derived status
  banner (`3 implemented, 38 implemented-unverified, 1 experimental, 19 documented, 2 blocked, 1
  deferred`), the Kimi Code yellow `acknowledgement required` terms notice, and `Template reference
  (43)` render cleanly without clipping.

