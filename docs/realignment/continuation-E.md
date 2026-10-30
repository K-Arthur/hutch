# Continuation: Slices C-E after whole-Bot deletion (run 4 and later)

Date: 2026-10-29. Base: local `main` at the run-3 deletion commits. Status: whole-Bot permanent
deletion is implemented and locally verified; this file is the handoff for the remaining completion
slices, all of which were blocked by the parked dashboard/website session.

## Completed in run 3 (context)

- Whole-Bot permanent deletion: schema v83, command layer, typed API, CLI `hutch bot destroy`,
  dashboard picker/danger zone, tests and real-world script. See `continuation-B.md` update section
  and the ledger entry "Whole-Bot permanent deletion implemented (2026-10-29)".
- Dashboard states for the new page: empty, loading, error (aria-live + retry), success with live
  cleanup state, permission-refused surface, keyboard and 44 px phone targets, zero horizontal
  overflow at 1440x900 / 900x900 / 360x800. Evidence under
  `docs/realignment/artifacts/completion-2026-10-29/deletion/`.
- Docs updated: `docs/operations.md` implemented section, `docs/bot-config.md`, `docs/safety.md`,
  `docs/realignment/tests.md` T-DELETE-SEMANTICS, `README.md`, `website/llms.txt`.
- Shared NAV gained the "Delete bot" entry; the SPA home still has no link until the parked session's
  static bundle commits (recorded limit).

## Remaining (exact paths and owners)

1. Frontend state hardening on the parked-session pages (blocked until those files are committed:
   `src/hutch/server/templates/{usage,models,approvals,bots,connections}.html`,
   `src/hutch/server/static/app.js`, `tests/e2e/test_browser.py` and sibling e2e files):
   - `/usage`: no server-rendered error banner or retry (`pages_usage.py`, `templates/usage.html`);
     empty state has no call to action.
   - `/models`: empty state is hint text only; the origin-null form-POST finding is recorded in the
     ledger and needs the template owner.
   - `/approvals`: empty state has no call to action; retry rewrites the hash to #/chat.
   - `/bots` SPA: fleet empty state/CTA unreachable below ten assistants.
   - Connections empty state sits behind the provider detail screen.
2. Marketing refresh (blocked on `website/index.html` and brand assets being committed): capture the
   finished dashboard at 1440/900/360 with Playwright, place at least one real capture in
   `website/assets/`, and re-check canonical/og/sitemap/llms.txt claims. Prior committed-HEAD
   marketing evidence is in `docs/realignment/artifacts/completion-2026-10-29/marketing/`.
3. Visual baselines: the new deletion captures are reviewed evidence, not SSIM baselines. If baselines
   are wanted, add them in a new module with a Docker-pinned Chromium; document the exact revision
   otherwise (this host: Chromium headless shell revision 1243 / 153.0.8010.12, Playwright 1.63.0).
4. Accessibility: run an axe-core audit and a screen-reader pass on the new danger-zone page and the
   parked pages once available; record gaps honestly.
5. Final gates: full non-browser pytest suite is still to be run once on the merged tree (the fast lane
   was focused groups); the parked-session dirty `tests/test_workflow_usage_budget.py` currently has
   unrelated failures and must not be edited by this task.
6. Optional follow-ups recorded by run 3: background drain phase with verified process exit; OS
   keyring clearing; settings-panel placement of the danger-zone control; deletion history after a Bot
   is deleted by name; pagination for purge-request history; delegation e2e for
   `workspace_task_fact_shares` erasure.

## Copy-paste prompt for the next run

> Continue the Hutch completion work from `docs/realignment/continuation-E.md`. Whole-Bot permanent
> deletion is implemented, committed and verified (see the run-3 ledger entry and commit `f231959b`).
> First confirm `git status` is clean for `src/hutch/server/templates/`, `src/hutch/server/static/`,
> `website/index.html` and the e2e files the parked dashboard session owned. Then: (1) harden the
> parked-session pages listed above (empty/loading/error/permission states, retry actions, no overflow
> at 1440/900/360) and add a new e2e module rather than editing the parked tests; (2) refresh the
> marketing site with real completed-dashboard captures and re-check canonical/og/sitemap claims;
> (3) run the full non-browser pytest suite once and record exact counts, then the focused Playwright
> journeys; (4) update `docs/realignment/ledger.md` with evidence and append a fresh continuation.
> Never stage another session's uncommitted files; stage explicit paths only.
