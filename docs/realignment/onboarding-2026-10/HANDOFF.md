# Handoff: Onboarding & Getting Started Implementation (2026-10)

**Date:** 2026-10-30  
**Branch:** `onboarding-2026-10`  
**Worktree:** `/home/kevina/CodingProjects/hutch/.worktrees/onboarding-2026-10`  
**Target:** Ready for clean merge to `main`

---

## 1. What Was Delivered

1. **Research & Analysis:**
   - Authored `docs/research/onboarding-and-getting-started-2026-10.md` covering competitive analysis (OpenClaw, Grok Bot, MausBot, OpenAI Dots, Claude Code, Codex, Ollama, n8n), real GitHub issue complaints, root causes, architecture, UX, accessibility, and prioritized requirements.
2. **Canonical Route Readiness & Typed Probing:**
   - `src/hutch/route_readiness.py`: Pure mapping from all 14 `ProviderError` kinds to canonical `provider.*` tokens, TTL calculation, capped `Retry-After`, and key redaction.
   - `src/hutch/providers/connection.py`: `probe_connection_typed()` executing a bounded 1-token generation test.
   - `tests/test_route_readiness.py` (24 tests) and `tests/test_readiness_probe.py` (17 tests).
3. **Secret Storage & Connection Service:**
   - `src/hutch/connections_service.py`: Normalizes keys, strips `Bearer ` prefixes, validates 4096-byte limits, writes 0600 files via `ConnectionBook.set_key()`, records terms acknowledgment.
   - `tests/test_connections_service.py` (7 tests).
4. **Onboarding State Extension:**
   - Extended `OnboardingSetup` in `src/hutch/onboarding.py` with `connection_name`, `assistant_id`, `first_request_completed_at`, `checklist_dismissed`.
   - Added persistence functions to `src/hutch/onboarding_store.py`: `save_connection()`, `save_assistant()`, `save_first_request_completion()`, `dismiss_checklist()`.
5. **Real Connection Steps (Replaced Interim Bridge):**
   - Removed temporary `/#/connections` bridge from `onboarding_chooser_api.py` and `onboarding_ai_service.html`.
   - `onboarding_hosted_key_api.py`: Hosted API key entry, terms ack, managed environment variable detection.
   - `onboarding_local_service_api.py`: Ollama/LM Studio loopback probe, hardware/RAM guidance.
   - `onboarding_opencode_api.py`: OpenCode binary discovery at `~/.opencode/bin/opencode`, live model listing (including `opencode-go/beam-free`).
   - `onboarding_readiness_api.py`: Shared readiness status checking and verification polling.
6. **Assistant Creation Step (Step 4):**
   - `onboarding_assistant_api.py`: Name & slug suggestion, model selection, explicit security boundaries (`ApprovalMode.ask`, `fresh` workspace, local memory).
   - `tests/test_onboarding_assistant.py` (6 tests).
7. **First Request Execution & Human-in-the-Loop Approval (Step 5):**
   - `onboarding_first_request_api.py`: Reviews prompt, explains approval model, submits real run via `engine.submit(bot, prompt, origin="onboarding")`, marks completion.
   - `tests/test_onboarding_first_request.py` (5 tests).
8. **Contextual Getting Started Checklist:**
   - `getting_started.py`: Computes 5-point progress from store facts, dismissible with CSRF, suppressed for experienced users.
   - `tests/test_getting_started.py` (4 tests).
9. **Desktop Startup Diagnostics & Recovery:**
   - Updated `desktop/web/index.html` and `desktop/web/startup.css` with structured diagnostic presentation and troubleshooting on startup errors.
10. **Documentation & Marketing Website:**
    - Authored `docs/getting-started.md` (comprehensive guide from architecture to troubleshooting).
    - Fixed dead `#quickstart` anchor in `README.md` and linked `docs/getting-started.md` in `docs/README.md`.
11. **Visual Validation:**
    - Captured 80 visual artifacts in `docs/realignment/onboarding-2026-10/artifacts/` across 8 viewports, 200% zoom, text spacing, reduced motion, keyboard focus.
    - Authored `docs/realignment/onboarding-2026-10/VISUAL-VALIDATION.md` and `CODE-REVIEW.md`.

---

## 2. Verification Commands and Results

```bash
# 1. Hygiene and tool contract audits
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/home/kevina/CodingProjects/hutch/.venv uv run --frozen --no-sync python scripts/audit_context_hygiene.py
# Result: Context hygiene check passed (861 source files; 117 frozen over-cap files)

PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/home/kevina/CodingProjects/hutch/.venv uv run --frozen --no-sync python scripts/audit_tool_contracts.py
# Result: Tool contract check passed (43 registered tools; canonical schemas certifiable; specs match)

PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/home/kevina/CodingProjects/hutch/.venv uv run --frozen --no-sync python scripts/audit_constitution.py
# Result: Constitution check passed (3 roles, 14 rules; every rule maps to existing enforcement)

UV_PROJECT_ENVIRONMENT=/home/kevina/CodingProjects/hutch/.venv python scripts/audit_emoji.py
# Result: audit:emoji — clean (scanned 2039 files, 10 waiver(s))

# 2. Focused test suites
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=/home/kevina/CodingProjects/hutch/.venv uv run --frozen --no-sync pytest -q --no-header \
  tests/test_onboarding*.py \
  tests/test_route_readiness.py \
  tests/test_readiness_probe.py \
  tests/test_connections_service.py \
  tests/test_getting_started.py
# Result: 173 passed
```

---

## 3. Operational Invariants Preserved

1. **Local-First & Explicit Approvals:** No automated execution of shell commands, destructive writes, or external network calls.
2. **File Size Budget:** Every new file is strictly under the 400-line cap (`audit_context_hygiene.py`). No frozen over-cap legacy file grew.
3. **No Mocks in Core Flows:** Real OpenCode CLI models (`opencode-go/beam-free`), real SQLite persistence, and real engine submission.
4. **Secret Privacy:** Keys are never rendered in HTML, sent over query parameters, or stored in SQLite tables; they reside in private `0600` files.
