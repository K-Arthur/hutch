# RUNLOG — approval triage lane (2026-10-22)

## Route decision

- User approved **Route A — priority queue with triage summary** on 2026-10-22. No API change; the existing 50-per-page access is retained as client-side pagination over a globally deadline-sorted pending set.

## Scope

- Target: Hutch dashboard, `#/approvals` (“Needs you” drawer) and the inline approval cards in `#/chat/:bot`.
- Task (user-selected): **approval triage** — an owner reviews pending approvals and uncertain outcomes across bots without missing critical ones.
- Autonomy: proceed, flag decisions. Design direction still requires the user’s route choice per the local research gate.
- Out of scope: bulk approve, API-contract changes, provider/OAuth flows, marketing site, light theme, new dependencies.

## Phase 0 — situational awareness (2026-10-22T00:54-07:00)

- Repo: `/home/kevina/CodingProjects/hutch`, branch `main` at `ceb9d36b` (merge of `wcag22-audit-fixes`).
- Concurrent lane: `claude-wcag22m` (claim active since 2026-10-21T23:45-07:00, TTL 4 h). It is committing WCAG fixes F-01…F-14 in `.worktrees/wcag22-measured` and claims `src/hutch/server/static/*.js`, `*.css`, `templates/**`, `website/**`, and WCAG e2e tests.
  - F-01 (`a403a598`) restores focus rings on shared button variants. Main still lacks it. This lane does **not** duplicate that fix; it verifies it after rebase.
  - F-04…F-06 fix header/attention-bar overlaps; those were visible as audit false positives behind the modal.
- Eight dev servers are listening on 8795–8802 from other worktrees. This lane uses port **8810** and state `/tmp/opencode/hutch-approval-triage/state`.
- Claim written: `.git/agent-claims/approval-triage.md`. No exclusive paths requested; no token/theme/lockfile ownership.

## Phase 0.3 — isolation

- Worktree: `.worktrees/approval-triage`, branch `agent/approval-triage/approvals` from `main@ceb9d36b`.
- `uv sync --extra dev` completed (74 packages).
- Audit tooling installed outside the repo: `/tmp/opencode/hutch-audit-tools` (Playwright 1.63 + Chromium 156 + axe-core). `node ui-audit.mjs --selftest` → **SELFTEST PASS** (12 checks fired; no false positives).
- Seed/serve harness (test-only, outside the repo): `/tmp/opencode/hutch-approval-triage/seed_and_serve.py`. It creates 4 bots and 14 realistic approvals, or a 52-approval stress set, in an isolated `HUTCH_STATE_DIR`.

## Assumptions recorded

- “Users” = the local Hutch owner/supervisor on desktop and phone-width browser; no real customer data exists. States that are hard to hold naturally (receipts-only) are held with Playwright route interception and labelled synthetic.
- The app is fixed dark theme by product decision; `prefers-contrast` is out of scope; forced-colors remains a verification mode.
- The queue’s existing safety model (one decision per exact request, no bulk approve, sticky allows never cover outward actions) is a do-not-lose contract.

## Gates passed

- Phase 1 recon, Phase 2 research (see `RESEARCH.md`), Phase 4 baseline measurements (see `FINDINGS.md`).
- Pending: user route choice before implementation (design research gate). Plan is drafted in `PLAN.md`.

## Things skipped / blockers

- Figma Community previews are behind an AWS WAF challenge in this environment; the cover CDN returns HTTP 403 and pages return the challenge shell. Per the research gate, other accessible online interfaces were inspected instead (Linear, Atlassian Jira, GitHub; see `RESEARCH.md`).
- Mobbin search returned HTTP 429 and a paid-plan requirement; not used.
- No screen reader or physical device available. Keyboard and DOM measurements only; screen-reader checks are labelled as unrun.
