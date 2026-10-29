# Continuation: Slices C-E (frontend hardening, marketing, visual validation)

Date: 2026-10-29. Status: **partially executed, blocked by the parked dashboard session**.

## Why this slice is not complete

Slices C/D of the brief (dashboard empty/loading/error/permission hardening at 1440/900/360 px, and the
marketing site) own files that another session has uncommitted and in flight: 13 templates
(`_approval_card`, `_events`, `_home_lists`, `base`, `bot`, `bot_new`, `bots`, `connections`,
`login`, `models`, `pair`, `run`, `runs`), the hand-written static JS/CSS bundle, `website/index.html`,
generated CSS, package manifests and eight `tests/e2e/*` files. `AGENTS.md` and
`docs/concurrent-agents.md` forbid editing, staging or reformatting that work, so this session did not.

## What was done instead

- Verified the current state rather than rewording it: inventory shows every server-rendered list page
  has an empty state; the gaps are e2e empty/error assertions for server-rendered bots/usage/models/
  approvals and error banners on approvals/runs/usage. Those are listed with file:line in
  `docs/realignment/completion-inventory.md`.
- Ran the existing memory-settings browser regressions (see `continuation-B.md`).
- Corrected non-owned marketing-adjacent surfaces that are clean and authoritative: `README.md` and
  `website/llms.txt` now distinguish local unsigned Ubuntu deb/AppImage acceptance builds from a
  published download; the usage page label no longer says "legacy test fixture".
- Re-checked claims against `docs/realignment/desktop-production-2026-10-26.md`; `website/index.html`
  itself remains owned by the parked session and was not reviewed or committed here.

## Remaining work (exact paths)

1. After the dashboard session commits, add empty/loading/error/permission-boundary e2e assertions for
   the server-rendered pages in a new `tests/e2e/` module (do not extend the owned files):
   `/bots`, `/usage`, `/models`, `/approvals`, and the "No connections yet" state.
2. Add a visible retry action to the error banner on the server-rendered approvals/runs/usage pages
   (templates owned elsewhere).
3. Wire the governed purge control into Bot settings after the same session commits
   (see `continuation-B.md`).
4. Marketing capture refresh: regenerate desktop/tablet/phone screenshots of the completed dashboard
   and check canonical/OG/sitemap claims at 1440 and 360 px; only after `website/index.html` is
   committed by its owner.
5. Visual baselines: this host has the installed Playwright Chromium revisions and no Docker-pinned
   baseline store, so record the exact revision instead of claiming Docker parity; the repo's existing
   capture helpers under `docs/realignment/capture_*.py` and `artifacts/` remain the evidence path.

## Copy-paste prompt for the next run

> Continue the Hutch completion work from `docs/realignment/continuation-C.md`. The frontend and
> marketing files were owned by a now-committed dashboard session; confirm `git status` is clean for
> templates/static/website first. Then add the empty/error/permission e2e coverage for `/bots`,
> `/usage`, `/models`, `/approvals` and `/connections` in a new e2e module, wire the governed fact
> purge control into Bot settings against the existing typed API, refresh the marketing captures at
> 1440/900/360 px, and record exact Chromium revision and artifact paths in
> `docs/realignment/ledger.md`. Run focused Playwright plus the quiet pytest gate; never edit files you
> did not review.
