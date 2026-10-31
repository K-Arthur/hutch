# Security and honesty review (2026-10-30)

Scope: the provider-platform slice at commit 9167d653. This is the authoring agent's review; the
independent verifier separately re-runs the definition-of-done checks.

## Preserved boundaries (checked by tests or direct inspection)

| Area | Check and result |
|---|---|
| Credential scoping | Ambient provider keys remain exact-official-host only; a custom endpoint receives only its own connection key. tests/test_provider_authority.py and tests/test_connections.py pass. |
| No secret exposure | Provider APIs and the /providers page are tested to contain no key value; the account objects expose credential source labels only. tests/test_provider_surfaces.py asserts an installed key never appears in the rendered page and that forbidden secret-shaped fields are absent from the provider API. |
| CSRF | New account-management POSTs use the shared read_form CSRF validation. A POST without a CSRF token returns 403 (tests/test_provider_surfaces.py::test_account_actions_require_csrf). |
| Loopback-only discovery | Discovery accepts only plain HTTP to exact loopback hosts, refuses embedded credentials, refuses redirects and caps the response size; caller-supplied non-loopback endpoints are rejected before any request. tests/test_provider_discovery.py covers all of these. |
| CLI version probing | Only --version is executed with a bounded timeout, a minimal environment (no provider credentials), stdin closed, and output sanitized to a short token or blank. Error text is not rendered. tests/test_runtime_registry.py covers a noisy probe. |
| Runtime authority | The runtime registry is descriptive: only built-in and managed OpenCode are selectable, only the built-in runtime reserves provider usage before calls, and documented CLIs cannot be enabled by registration. tests/test_runtime_registry.py. |
| Disconnect semantics | Removing a key reports local removal only and never claims provider-side revocation; the ChatGPT account store is not bypassed. tests/test_provider_accounts.py. |
| Honest claims | The catalogue uses a closed status vocabulary; implemented statuses require a real route; capability reports cannot produce live-verified evidence in this build; the matrix audit fails any row that claims live verification. scripts/audit_provider_research.py passes. |
| Uncertain paid outcomes | No new provider call, retry or replay path was added in this slice; the existing reservation, reconciliation and media idempotency code paths were not relaxed. Media adapters were not added (research only), so no new billable submission path exists. |
| Demo fixtures | Per the direct instruction, no demo provider implementation, seeded account, fake model catalogue or synthetic screenshot was added. Captures use real app state with genuinely unauthenticated accounts. |

## Findings and residual gaps

1. Medium, documented: outside Strict Offline, the provider layer does not implement a private-range
   allowlist or redirect/DNS pinning for operator-configured custom endpoints. Embedded URL credentials
   are refused and ambient keys are official-host-only, so this is not a credential leak; it is a
   documented SSRF-adjacent hardening gap recorded in 00-SCOPE (Known security gap), 04-ARCHITECTURE-AND-ADRS, docs/provider-platform.md and 07-ROLLOUT-AND-MIGRATION. Not
   introduced by this slice; it should be addressed before recommending untrusted operator input for
   endpoints.
2. Low, documented: CLI version detection shells out to installed binaries for informational display.
   It uses a minimal environment and no credential, but a hostile binary on PATH could report arbitrary
   text; output is sanitized and never used for an authorization decision.
3. Low, environment: the main checkout currently carries another session's uncommitted files
   (including .codewhale harness state with non-ASCII content). Repo audits that scan the working tree
   can report those files; the committed tree at 9167d653 is clean under the same audits when run from
   the branch worktree.
4. No blocking findings were identified in the code introduced by this slice.

## Independent review

The verifier teammate re-runs the checks independently; its report is stored beside this file as
verifier-report.md when available.

## Live-testing handling (2026-10-30, owner-authorized)

The owner explicitly authorized using the installed OpenCode CLI account, including its DeepSeek key, for
live tests. Handling rules used:

- Credentials were extracted only in memory from the owner's own OpenCode export for the duration of a
  single test process. They were never written to the repository, a committed artifact, a connection
  template, a document, a screenshot, or the final report.
- Isolated test state directories were deleted immediately after each test; the copied private-profile
  credential was removed with them.
- The final artifacts under artifacts/live-verification/ contain model ids, run ids, token counts, provider
  errors and assistant text only. A secret-pattern scan of the changed files found no credential.
- One failure is kept as evidence rather than retried: the stored OpenCode Go key was expired, the managed
  run failed explicitly with cost 0.0, and no account switch occurred.

Disclosure: while discovering where the installed OpenCode account stores providers, a credential-export
command printed provider credential values into this session's local agent transcript. Those values were
not copied into any file, commit or artifact, and no further export output was printed. Because local
session transcripts can be retained by the harness, the owner should treat the OpenCode account
credentials that appeared there as potentially exposed and rotate any long-lived API key among them if
that transcript may be shared. This was a testing-tooling mistake, not a product-code path.
