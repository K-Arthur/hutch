# Independent verifier report

Target: commit ffc686a9 on branch provider-platform (worktree .worktrees/provider-platform), frozen for
verification. Verifier: independent teammate, fresh context, read-only. Date: 2026-10-30.

Result: PASS for D1-D13, with one documentation discrepancy (D12) that was fixed in 8226879a before the
final delivery record. Deterministic suite totals at the verified code tree: focused provider/connection
tests 118 passed; named existing provider/authority suites 187 passed, 1 skipped; audit exit 0.

| Row | Result | Key evidence accepted by the verifier |
|---|---|---|
| D1 | PASS | scripts/audit_provider_research.py RESULT: PASS; 9 docs + 4 drafts; 62 identities in the matrix; no live-verified claim |
| D2 | PASS | 16 new provider-platform source files + ADR-0026; focused contract tests 118 passed; existing-behaviour edits are additive registration/template lines |
| D3 | PASS | account tests 11 passed including rename persistence and disconnect semantics; API shows grouped accounts and needs_authentication |
| D4 | PASS | capability API returns documented level with scope/provider and dated source; 62 reports; no live-verified level in build |
| D5 | PASS | readiness API states for needs_authentication/blocked_by_policy/endpoint_unavailable; /models renders route-readiness; discovery performs no inference |
| D6 | PASS | runtime catalog enabled [builtin, opencode]; only builtin has usage_reservation; OpenCode suites pass |
| D7 | PASS | 62 unique providers, closed vocabularies, 11 templates each mapping to one provider; ambient-key/SSRF suites pass |
| D8 | PASS | media suites pass; diff under media is the research draft only; no media adapter/fixture additions; deferral documented |
| D9 | PASS | 15 app captures at five viewports; capture-results.json statuses {200}, zero console entries, zero overflow; screenshots inspected |
| D10 | PASS | website #providers shipped vs research-tracked lists; FAQ visible 21 == JSON-LD 21 and order matches; CSS hash unchanged after source rebuild; site captures present |
| D11 | PASS | nine required docs updated + ADR-0026; compat.json reviewed_on and stale Anthropic/OpenCode/vision claims corrected |
| D12 | PASS* | env probe zero credentials/local services; no secret in provider API/page responses; CSRF 403; loopback-only discovery; no live claim. *Documentation discrepancy: the security review pointed at 00-SCOPE/07-ROLLOUT for the SSRF gap but those files did not contain it; fixed by commit 6eb26045 by adding the record to both. |
| D13 | PASS | branch clean and HEAD equals frozen target; 19 provider-platform commits, no AI attribution; main contains the target (plus later unrelated other-session commits) |

Notes accepted from the verifier: ADR-0026 heading was corrected before freeze (e6ce49e9); STATE/EVIDENCE
needed their completion refresh (done at completion); 06-VALIDATION-LEDGER status line was still
"in progress" (corrected by commit 6eb26045); no regression found in the named suites.