# Responsive task files

Numbered, independently executable tasks. Run them in order unless a task note
says otherwise. Each file states scope, failure mode, the change in prose,
validation evidence and rollback. A fresh session can execute one task without
reading the others.

| # | Task | Depends on | Status |
| --- | --- | --- | --- |
| 01 | Viewport and safe-area contract (01-viewport-and-safe-area-contract.md) | audit P1 | done |
| 02 | Server navigation model (02-server-navigation-model.md) | 01 | done |
| 03 | Dynamic viewport and keyboard (03-dynamic-viewport-and-keyboard.md) | 01 | done |
| 04 | Stylesheet structure and sticky offsets (04-stylesheet-structure-and-sticky-offsets.md) | none | done |
| 05 | Touch-target floor (05-touch-target-floor.md) | 01 | done |
| 06 | Safe-area chrome (06-safe-area-chrome.md) | 01 | done |
| 07 | 13-inch and tablet device bands (07-device-band-shell-tuning.md) | 02, 03, 05 | done |
| 08 | Marketing site adaptation (08-marketing-site.md) | 01, 05 | done |
| 09 | Final validation, review and docs (09-final-validation-review.md) | 01-08 | done |

All nine tasks are done. 07b (rail source reconciliation in app/src/input.css
plus ui.css rebuild) and 07c (SPA/server drawer breakpoint alignment) are
deferred with recorded reasons in ../STATE.md; they need the parked brand work
committed first. Task status lives in ../STATE.md, which is the source of truth.

Parked-tree rule: this checkout carries another session's uncommitted
brand/dashboard work. Tasks favour additive files (a new responsive stylesheet or
script) and, where an existing shared file must change, stage HEAD plus only the
task hunk with the git hash-object recipe in ../README.md. Never stage the parked
hunks.
