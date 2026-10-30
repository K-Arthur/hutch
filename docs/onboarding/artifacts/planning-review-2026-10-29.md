# CP0 planning review record - 2026-10-29

Reviewer: independent planning review agent (fresh context, read-only; session 12936c57-d3ea-439b-b92d-e630c33d9ad8).
Scope: docs/onboarding/task-plan.md, edge-case-matrix.md, marketing-changes.md, review-checklist.md, slices/slice-01.md, slices/slice-02.md, checked against the research brief/research and the user's planning requirements. No repository-wide review was requested; every check named files/routes/anchors.
Outcome: PASS after findings resolved. No production code, tests, generated CSS, or marketing source was modified by planning or review.

## Findings and dispositions

| # | Finding | Disposition |
|---|---|---|
| 1 | Readiness seam could not produce the promised states: check_connection sets verified on a metadata list and flattens ProviderError kinds. | Fixed in plan: structured ProbeResult + pure route_readiness classifier over all 14 ProviderError.KINDS and HTTP status; metadata => saved_unverified; only explicit generation => verified; ConnectionCheck.verified discarded. Slice 03 implements. |
| 2 | State ID vocabulary clashed (provider.* vs route.* and missing families). | Fixed: canonical families documented in edge-case-matrix section 4; route.* aliases mapped to provider.*; pairing/secret/consent/revalidation families added; task-plan no longer claims states are copied from KINDS. |
| 3 | Flow destination contradiction (SPA -> /onboarding vs chooser, auto-redirect). | Fixed single rule: SPA always navigates to /onboarding (request step); saved request's single primary action opens /onboarding/ai-service; no auto-redirect. Task-plan row 02/CP2 and slice-02 updated. |
| 4 | "Reuse POST /api/connections" not executable from HTML forms. | Fixed: slice 04 extracts src/hutch/connections_service.py (key normalise/4 KiB validation, probe, terms ack), used by onboarding forms and rewired JSON handlers with net-zero-or-shrink app.py diffs and parity tests. |
| 5 | Frozen-file/scope contradictions (app.py cap vs readiness routes; connections.py/security.py omitted). | Fixed: readiness routes stay in onboarding_api.py; app.py budget clarified; connections.py (448) and security.py (513) listed as read-only frozen; providers/connection.py may grow within its 400-line cap. |
| 6 | Dirty-tree gate unverifiable. | Fixed: CP0 now requires docs/onboarding/artifacts/planning-baseline.txt (created here) with git status/diff stat covering app.py, app.js, base.html, connections.html, pair.html, pinned e2e, website/index.html, docs/design-system.md; targeted-hunk edits only. |
| 7 | EC-06 offline/server-down and EC-01 resume TTL had no owner. | Fixed: offline/server-down owned by slice 03 (client shell + retry) and gated by slice 09/CP6; resume TTL (resume_expires_at, setup.resume.expired) added to the slice-01 record and tests. |
| 8 | Pydantic Literals would classify stale records as damaged. | Fixed: contract_version int and route_kind str with pure allowlist validation; newer contract => explicit newer-version stale state, never damaged. |
| 9 | Persistence API naming inconsistent (save_setup_with_revision vs save_request). | Fixed: adapter API is load_setup + save_request (slice 01) and save_route (slice 02), revision-checked under the process lock. |
| 10 | Review rule forbade the bounded onboarding render helper that the plan intentionally adds. | Fixed: explicit exemption in review-checklist section 2; helper may not duplicate business logic; pagekit extraction deferred to a separate reviewed task. |
| 11 | CP7 docs list omitted README.md and website/llms.txt. | Fixed in task-plan CP7 and review-checklist section 8. |
| 12 | Error-summary anchor pointed at a JS alert banner; head-block/skip-target details off. | Fixed: slice-01 defines a server-rendered error summary (role alert, tabindex -1, field links) and uses base.html's existing #main skip link; head block placed before </head>. |
| 13 | Broken section references, slice gate labels, dependency cycles, page-module naming, welcome-back scope. | Fixed: section 10 -> section 8; gate labels CP1/CP2; slice 08 dependency CP5 and slice 10 CP5/CP6; pages_onboarding -> onboarding_api; "Welcome back" allowed only in-app after a completed-session marker, never on the site or first run. |

## Residual open items (assigned, not blockers)

- Desktop-host (Tauri) origin/webview differences for OAuth loopback, passkeys, pairing: checked in slices 06/10; no parity claimed before then.
- Browser engines beyond Chromium/Linux: unverified; every evidence bundle must state the limitation.
- Live phone reachability, OS keyring/operator-managed key behaviour: manual target-host checks before claiming EC-05/EC-07 complete (evidence lane L6).

## Planning-phase attestation

- No production code, tests, generated CSS, or marketing source changed by the planning phase; only new/modified docs under docs/onboarding/.
- The six planning artifacts and this record are the CP0 evidence set; the git/size baseline is in planning-baseline.txt.
- CP0 verdict: PASS, with implementation reviewers named per slice in review-checklist.md section 12 before CP1 starts.
