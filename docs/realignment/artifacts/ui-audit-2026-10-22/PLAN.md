# Plan — measured UI audit fixes, 2026-10-22

Gate: no item changes a global token, removes or relocates a feature, adds a dependency, or
changes an API contract, so the plan proceeds under "proceed, flag decisions" (auto mode). Each
change is reversible by reverting its commit. Research IDs refer to RESEARCH.md.

| Card | Fixes | Level | Change | Alternatives rejected | Blast radius | Parity | Acceptance (measured) |
|---|---|---|---|---|---|---|---|
| TC-1 | F-01 | Shared component (`style.css` legacy-button rule) | Add a `:focus-visible` ring to the `all: unset` legacy-button selectors, same token (`--focus`, 2 px, offset 2 px) as the global rule. | Raising the global rule's specificity (`:root :focus-visible`) would also re-add rings that components deliberately move to a container (composer) — double rings. Removing `all: unset` is a wider visual change. (A-2, D-5) | Every primary/ghost/danger/small button and `a.primary/a.ghost` on every route. | None. | Focused vs blurred crops differ for Allow once, Review, Refresh, New assistant; computed `outline-style: solid`; ui-audit `focus-invisible` on those selectors → 0. |
| TC-2 | F-02, F-03 | Screen (`app.js` shell) | Remove the faulty `#ws-close` Tab handler. Set `#workspace.inert` while the ≤900 px media query matches and the sheet is closed; clear it when open or wide (matchMedia `change`, so load-vs-resize agree). | `visibility: hidden` on the closed sheet would fight the slide transition; a hand-written tab filter repeats the bug class. (D-1) | Navigation shell at ≤900 px on every route. | None: same controls, now reachable. | 390 px: Open menu is the first stop after the skip link; with the sheet open Tab reaches Chats, Needs you, More, assistants, Settings and wraps; ui-audit `focus-obscured` "clipped away" → 0 at 320/375/768; desktop unaffected after resize 390→1440→390. |
| TC-3 | F-04, F-05, F-06 | Screen + component (`style.css` header/reminder, small `app.js` hook) | (a) Header: keep `.ctx-meta` at its size; let `.app-top-context` wrap so actions drop under the identity when they do not fit; identity keeps ≥18 rem before wrapping. (b) Reminder: in chat from 641 px, place it in the main view's grid cell aligned to the top (below the header at any height, moving with the page, under the navigation sheet) with conversation scroll padding while shown; phones keep the in-flow row; on page routes reserve bottom clearance in `.page-scroll` while it floats (C43). (Revised twice after measurement; see RUNLOG.) (c) Make the reminder a labelled `aside` (F-13). | Icon-only Review/Stop between 901–1279 px (hides labels people rely on); hiding the status chip (truthful-state principle); fixed overlay under measured header at 641–900 px (still covers the top of the feed). (A-3, B-*, D-6) | Chat header on all chat routes; reminder on every route. | None. No added layout shift (re-measured after the revision). | 901/1024/1280/1440: no rectangle overlap between identity, actions and status clusters; 641–900: reminder does not intersect header controls; 1024 Work history: focused "Show more" centre point is the button itself; ui-audit `fixed-layer-overlap`/`occluded-control` against `#attention-bar` → 0 outside the modal case; axe `region` → 0. |
| TC-4 | F-07 | Component (service tile) | `container-type: inline-size` on `.service-tile`; below 20 rem the state badge moves under the name. | Raising the grid minimum (fewer tiles per row on wide screens, still letter-breaks long names). (D-4) | Apps & AI tiles. | None. | Every tile `h3` at 320–1440 renders at most two lines and never narrower than its longest word. |
| TC-5 | F-08 | Screen (Work history toolbar) | Count on its own row. | Shorter loading text only (still shifts when "Showing N of more than M" wraps). | Work history. | None. | CLS on `#/runs` at 768 < 0.1 on three loads. |
| TC-6 | F-09, F-12, F-14, F-16 | Server templates/CSS | Focusable, named table regions; hidden header text for the actions column; skip link hidden off the top with logical start; 12 px floor for table headers/meter labels. | — | `/models`, `/usage`, all server pages (skip link). | None. | axe `scrollable-region-focusable` and `empty-table-header` → 0; RTL scrollWidth = viewport; small-text candidates on those pages → 0. |
| TC-7 | F-10 | Shared form controls | 16 px floor for text inputs/selects on `(pointer: coarse)`. | `maximum-scale=1` (breaks zoom; forbidden). (D-3) | Every text field on touch devices. | None. | ui-audit `input-zoom-ios` → 0 at 320/375. Real iOS: Needs human check. |
| TC-8 | F-11 | Screen (Activity) | Await the roster refresh when the cache is empty before the first render. | Adding `bot_display_name` to `/api/overview` (API change; coordinate separately). | Activity. | None. | Direct load of `#/overview` shows display names on five consecutive loads. |

Follow-ups (not in this change): F-15 forced-colors palette inheritance (design decision), F-17
marketing image candidate, O-01 skip-to-composer (product decision).

Rollout: ordinary commit series on `agent/claude-wcag22m/measured-audit`; each card is one commit
carrying its Finding IDs. Rollback: revert the card's commit.

Verification commands (after each card and at the end):

```
node <scratchpad>/tools/ui-audit.mjs --selftest
B=http://127.0.0.1:8797 SITE=http://127.0.0.1:8798 RA=<run> RD=<run> run_shards.sh <out> --widths=320,375,768,1024,1440,1920 --schemes=dark --stress=none
… --stress=textspacing,pseudo,rtl --no-keyboard ; … --widths=400,480,560,639,641,720,899,901,1099,1101,1280 --no-keyboard
uv run pytest -q tests/e2e/test_wcag_measured_audit.py tests/e2e/test_wcag_fixes.py
uv run pytest --ignore=tests/e2e -q
```

## Design-level cards (added after the user asked for component fit, streamlining, colour and
## other disabilities, alignment and arrangement, text load, breathing room and processing time)

| Card | Fixes | Level | Change | Acceptance (measured) |
|---|---|---|---|---|
| DC-1 | F-18 | Component (reminder) | Rebuild only when the message changes; restore focus if rebuilt. | Focus stays on Review across ≥9 s of polling (was lost after 4.5 s). |
| DC-2 | F-19 | System rule | Underline class-less links in running text. | axe `link-in-text-block` → 0; computed underline on Runtime's in-text link. |
| DC-3 | D-01 | System rule | 72ch cap for block hints and muted notes (app + server pages). | No hint/muted block wider than 72ch at 1920 px on Skills and Models. |
| DC-4 | D-02 | New shared component | `.switch` (button `role=switch` / checkbox `role=switch`), On/Off word, forced-colors and touch sizes; Automatic starts ×2, Enter sends. | `role=switch`, `aria-checked` flips with Space, focus kept on both pages; existing Scheduled work and Runtime tests updated and passing. |
| DC-5 | D-03 | Screen | Work history filter as native radios drawn as segments. | One Tab stop; ArrowRight selects next and filters; 4 radios in a named radiogroup. |
| DC-6 | D-05 | Screen | Hide the empty action-outcomes bucket. | Section hidden when there are no receipts. |
| DC-7 | D-06 | Component (toast) | ≥5 s, +1 s per ~90 characters, paused while hovered/focused; errors persist. | Notice present at 4.6 s, held for 6.5 s under the pointer, then dismisses. |
| DC-8 | D-07, D-08 | Screen + component | Per-card Open as ghost with a named link; failed chips use ✕. | One visible primary on Manage assistants; failed `::before` is a polygon, success a dot; protan/deutan simulation keeps them distinct by shape. |
| DC-9 | D-09, D-10 | System + screen | Shared `.btn-row` gap; Skills title row, spacing and matched control heights; crumb gap; equal heights in chat message heads (44 px on touch). | Refresh on the title row, ≥16 px before the panel, field = button height, sample buttons ≥6 px apart; no mixed-height rows except the server topbar. |
