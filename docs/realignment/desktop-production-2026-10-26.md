# Desktop and production implementation

Accepted brief: user conversation of 2026-10-26, including the final implementation plan and the subsequent OpenRouter / existing OpenCode login correction. Implementation authorized explicitly. This document is the portable task checkpoint; it contains no credentials.

## Acceptance and constraints

| ID | Required result | State |
| --- | --- | --- |
| P1 | Functional unsigned desktop previews: Windows 11 x64, macOS 14+ arm64/x64, Ubuntu 24.04 x64 deb/AppImage; bundled backend; native lifecycle and installed-package checks | Pending |
| P2 | Platform boundaries for owned process cancellation, workspace safety, locks, credentials, IPC and background operation; preserve Linux containment and fail closed where unsupported | Pending |
| P3 | Main assistant coordinates scoped specialists through the existing durable workflow engine; reviewed plan, two workers, progress, pause/redirect/stop-all, recovery and isolated context | Pending |
| P4 | Hybrid learning: automatic explicit nonsensitive preferences and nonexecutable drafts; review sensitive/inferred facts, executable skills and authority changes; provenance/undo/revocation; opt-in migration | Pending |
| P5 | Telegram, Slack Socket Mode, signed webhooks; allowlists, replay/duplicate protection and durable delivery | Pending |
| P6 | Complete governed integration execution and core Docs/Sheets/Drive, Gmail/Calendar, Google Ads reporting, Slack, Notion, GitHub and CSV workflow support | Pending |
| P7 | OpenCode uses Hutch's canonical tools for documents, integrations, browser and bounded delegation, including approvals, receipts and cancellation | Pending |
| P8 | Low-cost OpenRouter and existing selected OpenCode login; shared US$10 evaluation ceiling, $8 planned plus $2 reserve; no purchases/overages or ambient unrelated credentials | In progress |
| P9 | Live marketing, performance marketing, founder sales plus meetings, document research and coding repair; paired baselines, target three final repetitions/scenario within budget; both runtime paths for the three business workflows | Pending |
| P10 | All critical safety/correctness checks; artifact quality >=85/100 with no dimension below 4/5; actual artifacts/readbacks and costs; incomplete evidence is not a pass | Pending |
| P11 | Rust native host; additional Rust performance replacement only after equivalent tests and >=20% p95 or >=30% memory improvement including IPC | Pending |
| P12 | Progressive focused commits, docs, accurate marketing/download availability, source provenance, full applicable validation and distinct requirements/standards review | In progress |

Audience: individuals and solo professionals. Desktop first, then breadth. Supervised defaults plus revocable, precise automation grants. Unsigned previews precede production signing/notarization and safe update recovery. No public repository visibility change, no live ads/budget changes, no unreviewed outreach or publication. Advanced unsupported OS tools remain unavailable. Hardware, training, extra channels/voice, ACP/TUI expansion and remote backends follow the validated core.

## Authoritative pointers

- Project: `AGENTS.md`, `PRODUCT.md`, `DESIGN.md`, `docs/architecture.md`, `docs/runtime-setup.md`.
- Boundaries: ADR 0016 (Rust supervisor deferred), 0017 (governed integration plane), 0019 (cost/context/routing).
- Benchmarks: `benchmarks/`, `tests/test_benchmarks.py`; existing production executor depends on Linux pidfd and /proc. Cross-platform packaging alone does not port it.
- Guides: https://x.ai/bot/guides/grok-bot-for-marketing ; https://x.ai/bot/guides/grok-bot-for-performance-marketing ; https://x.ai/bot/guides/grok-bot-for-founder-led-sales . Core stack chosen; enterprise/optional vendor parity deferred.
- Inspiration: https://github.com/NousResearch/hermes-agent (MIT), https://github.com/openclaw/openclaw (MIT), https://github.com/zeroclaw-labs/zeroclaw (MIT/Apache-2.0). Pin revisions and attribute any copied code. Hermes IDE BSL code reuse excluded. Muse primary docs inform bounded delegation; musecodes.io is unofficial.
- Issue-derived regressions: Hermes #143547/#141758/#144949, OpenClaw #177077/#143524/#184378/#184358, ZeroClaw #10780/#10921/#10673. These are reported incidents, not independently reproduced competitor defects.

## Evaluation contract

Candidates: OpenRouter DeepSeek V4.1 Flash and V3.2, Qwen3 Coder free; OpenCode DeepSeek V4.1 Flash Free and GLM-5.3-Flash Free. Discover actual current availability/pricing/privacy/capabilities before dispatch. Pin route and fixtures for before/after comparisons; measure mixed routing separately. Use synthetic business data before authorized real-service fixtures. Inspect artifact contents and independent math, suppression, citation and effect checks rather than trusting completion text.

Allocate up to $1 qualification, $2 baselines, $5 final evaluations, $2 recovery/rechecks. All model calls, child tasks, retries, summaries and auxiliary runtime calls count. Unknown charges remain held; no new dispatch beyond admissible remaining balance/reservations. Existing OpenCode Go credential presence was inspected without printing values; validity/entitlements are not established. Isolate only the selected credential, never the whole personal profile. Temporary credential copies must be removed after tests; the user revokes the supplied OpenRouter key. Nothing secret belongs in reports or Git.

Google Ads test accounts cannot provide real serving metrics: live reporting needs approved read-only data. Missing OAuth registrations, test accounts, signing/hosting credentials, native runners or budget leave affected acceptance explicitly unverified. Local-first desktop does not imply unattended execution while the computer sleeps.

## Progress and evidence

- Starting revision: `1bba69ce`; no tracked user edits. Preserve unrelated untracked `.codex/`, `.opencode/`, `.v2c/`, `.video_agent/`, `reports/`, `research_notes/`, `serve.pid`, `var/`, and the settings disclosure trace archive.
- Planning baseline: `uv run --frozen --no-sync pytest -q tests/test_benchmarks.py tests/test_schedule_durability.py tests/test_credential_routing.py tests/test_memory_continuity.py` — **41 passed in 6.05s**. No full suite, native builds, or inference was run in planning.
- Existing-login slice implemented: discovery is explicitly requested; transfer uses exactly one provider's API key through the owned server; OAuth sessions require their own sign-in; source stays untouched; file safety and secret-free errors are enforced. The version probe now uses the private profile too (the previous probe attempted to write the personal OpenCode log).
- Verification: `uv run --frozen --no-sync pytest -q tests/test_opencode_login.py tests/test_opencode_api.py tests/e2e/test_opencode_login.py` — **16 passed in 5.84s**. Chromium 153.0.8010.12, 1440/768/320 widths, keyboard activation, no page errors or horizontal overflow; desktop/phone captures opened and inspected. Scope is this dialog, not full-app accessibility certification. TestClient stalled in the filesystem/network sandbox; the isolated tests passed outside it.
- Live discovery only: OpenCode V2.1.4 reports `opencode/opencode/deepseek-v4.1-flash-free` and `opencode/opencode/glm-5.3-flash-free`; no inference was dispatched. Existing API credential transfer remains untested against the live account.
- Active slice: OpenRouter endpoint execution controls and correct metering for renamed OpenRouter connections, followed by live qualification and canonical tool bridging.
- Next: verify runtime/host portability, desktop packaging and capability reporting; continue through remaining acceptance, recording actual checks and blockers here.

## Verification commands

Use the existing `.venv` (`uv run --frozen --no-sync ...`) and locked dependencies. Focused pytest before `pytest --ignore=tests/e2e`, then relevant browser/full suite. `npm run build:css` for source CSS changes. New native code needs Rust checks and installed OS validation. Review committed changes from the starting revision plus staged, unstaged and task-owned untracked files. Never weaken tests or mark a check passed because it was skipped.
