# Runtime & Background Work — frontend research and route approval (2026-10-11)

Standing gate: research before UI design, present routes, wait for the owner's choice.
This record covers the `#/runtime` surface (approved Route A). Identity, tokens and
components stay those of `DESIGN.md`; nothing was copied from the references.

## What was inspected

| # | Source (public) | What was actually read | Useful pattern | Not transferred |
|---|---|---|---|---|
| 1 | Hutch itself: `Scheduled work` page capture (`docs/realignment/artifacts/ui-surface-review/schedules-desktop.png`) and assistant settings (`assistant-settings-everyday/settings-simple-desktop.png`) | Opened both screenshots | Header state + one aggregate pause control; progressive disclosure; one primary action in an empty state | — |
| 2 | [Zentra — AI Automation Dashboard](https://www.figma.com/community/file/1634028749342367707/ai-automation-dashboard-zentra) (Figma Community; creator cover read) | Cover preview image | Health counts as fractions; an "items that need attention" rail with one action per item | Progress rings/percentages for unknown future work |
| 3 | [Database-Monitoring](https://www.figma.com/community/file/1648041261818453317) (Figma Community; creator cover read) | Cover preview image | Subsystem rows each with an explicit state word; "View all" expansion; recent-alerts strip | Dense metric charts; monitoring is not a data-visualisation product here |
| 4 | [Template — Services Status](https://www.figma.com/community/file/1274449037867702549/template-services-status) (creator agustincairone; cover read) | Cover preview image | Per-service rows with a plain state and a time range | Uptime bars: Hutch has no measured minute-level history and will not fabricate one |
| 5 | [Syncthing GUI](https://docs.syncthing.net/intro/gui.html) (live self-hosted daemon; docs screenshot read) | Full GUI screenshot | Per-item state words ("Up to Date", "Preparing to Sync"), *Last Scan* timestamps, per-item Pause/Rescan plus one aggregate, and a separate "This Device" block for machine facts | Transfer-rate charts; "Syncing 56%" progress for unknown work |

Mobbin was checked and is **unavailable on this account's plan** (paid). No Mobbin
reference is claimed. Figma's official MCP is disabled in this environment (403);
public Community covers were downloaded and read directly instead. Covers are creator
previews, not production screens; spacing/colour decisions were not inferred from them.

## Routes presented (2026-10-11)

- **A. Dedicated Runtime page under More + status chip (recommended).** Page: This
  machine → Background service (state/readiness/linger + controls) → Watched sources
  (per-source state, freshness, pause/check/remove, lazy change log) → Queue & automation
  (counts, Needs-you link, one pause control). References: Syncthing's item/machine split,
  Zentra's attention rail, Hutch's existing disclosure and chip vocabulary.
- B. Settings-only disclosures. Smaller footprint; monitoring lives oddly inside Settings.
- C. Extend `Scheduled work` with a watchers list and a runtime strip. Reuses existing IA;
  mixes machine facts into a work surface.
- D. Status chip + drawer only. Minimal; setup actions hidden behind a transient overlay.

**Owner decision: Route A.** Recorded in the session before implementation began.

## Implementation and evidence

- `#/runtime` route, `Runtime` under More (auto-opened group), top-bar status pill now links here.
- Sections and controls exactly as approved; service controls require an exact confirmation
  string server-side and a confirm dialog client-side; paired phones receive 403 for every
  route (asserted in `tests/test_remote_pairing.py`).
- Captures + machine-readable validation: `docs/realignment/artifacts/runtime-page-2026-10-11/`
  (desktop 1440×960, tablet 900×1024, phone 390×844, compact phone 320×740; install confirm;
  add-source dialog; expanded change log; keyboard focus). `validation.json` records
  zero horizontal overflow, zero console/page errors, zero failed requests, `aria-current`
  on the Runtime nav item, section headings, and control counts.
- Regression: `tests/e2e/test_runtime_page.py` (live server + real browser) asserts the four
  sections, background check freshness without any model call, the lazy change log, pause/
  resume of automation and of one source, that opening the install confirmation is inert,
  and phone-width usability. It never installs a unit on the host.
- Defects found by inspection and fixed: the change-log disclosure loaded before `<details>`
  opened (now a `toggle` listener); `linger` reported `unknown` when the unit was simply not
  installed (now reported as `disabled`).

## What remains unverified

Screen-reader passes, real systemd install/stop/linger on this host, live RSS/Git sources
outside fixtures, and remote-device checks are separate; the test above labels its own scope.
