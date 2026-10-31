# Independent Code Review: Onboarding & Getting Started (2026-10)

**Date:** 2026-10-30  
**Scope:** `src/hutch/route_readiness.py`, `src/hutch/connections_service.py`, `src/hutch/onboarding.py`, `src/hutch/onboarding_store.py`, `src/hutch/server/onboarding_*.py`, `src/hutch/server/getting_started.py`, `desktop/web/`, `docs/getting-started.md`  
**Review Status:** APPROVED

---

## 1. Security Architecture & Boundary Review

### 1.1 Secret Handling
- **Invariant:** Secrets and API keys must never appear in HTML markup, query parameters, logging output, or unencrypted database tables.
- **Verification:**
  - `normalise_and_validate_key()` in `connections_service.py` sanitizes keys, trims leading `Bearer ` prefixes, enforces a 4096-byte ceiling, and refuses control characters.
  - Keys are persisted directly into private 0600 files via `ConnectionBook.set_key()`.
  - In `onboarding_hosted_key_api.py`, passwords use `type="password"`, `autocomplete="off"`, and `spellcheck="false"`.
  - Error messages in `route_readiness.py` use `safe_detail()` which strips query parameters, tokens, and authorization headers before surfacing diagnostics.

### 1.2 State Isolation and CSRF Protection
- **Invariant:** All state mutations must be gated by double-submit CSRF checks and protected against concurrent multi-tab clobbering.
- **Verification:**
  - Every form submission in `/onboarding/*` and dismissal in `/api/v1/getting-started/dismiss` verifies CSRF tokens via `check_csrf()`.
  - Optimistic locking using `expected_revision` in `OnboardingSetup` detects when another tab advanced the setup and rejects stale writes with HTTP 409 Conflict without data loss.

### 1.3 Human-in-the-Loop Permissions
- **Invariant:** Newly created assistants must default to explicit human supervision.
- **Verification:**
  - `onboarding_assistant_api.py` sets `approval_mode = ApprovalMode.ask` and `workspace_mode = "fresh"`.
  - Sensitive operations (shell execution, external file mutations, network egress) require manual approval in the dashboard.

---

## 2. Tool Seam & Schema Contracts

- **Tool Protocol:** No new tool was added; existing canonical tools (`shell`, `files`, `documents`, `memory`) remain unchanged.
- **Audits:**
  - `python scripts/audit_tool_contracts.py` passed cleanly (43 registered tools; canonical schemas certifiable; specs match).
  - `python scripts/audit_context_hygiene.py` passed cleanly (all new files well under the 400-line cap; frozen legacy files untouched).

---

## 3. Resilience and Error Handling

- **Probe Safety:** `probe_connection_typed()` generates exactly 1 token (`max_tokens: 1`) to verify generation path without unbounded billing.
- **Backoff & Rate Limiting:** `Retry-After` headers are parsed and capped at 60 seconds (`MAX_RETRY_AFTER_SECS = 60.0`).
- **Network Resilience:** Network timeouts, unreachable loopbacks, 401s, 402s, 403s, 429s, and 503s all map to typed `ProviderError` tokens with human-actionable troubleshooting copy.

---

## 4. Craft & Accessibility

- **No Emoji Rule:** Verified via `scripts/audit_emoji.py` (0 emoji in source, templates, CSS, or documentation).
- **Responsive Design:** 8 viewports verified from 1440x1000 down to 320x740 with full reflow and 44px+ touch targets.
- **WCAG Standards:** Conforms to WCAG 2.1 AA (200% zoom, text spacing override, reduced motion, focus visible).

---

## 5. Review Conclusion

The implementation delivers a genuine, local-first onboarding journey without demo fixtures, superficial wizards, or security compromises. Approved for merge.
