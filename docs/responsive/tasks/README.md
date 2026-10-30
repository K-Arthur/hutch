# Responsive task files

Numbered, independently executable tasks. Run them in order unless a task note
says otherwise. Each file states scope, failure mode, the change in prose,
validation evidence and rollback. A fresh session can execute one task without
reading the others.

| # | Task | Depends on | Status |
| --- | --- | --- | --- |
| 01 | Viewport and safe-area contract (01-viewport-and-safe-area-contract.md) | audit P1 | not-started |
| 02 | Server navigation model (02-server-navigation-model.md) | 01 | not-started |
| 03 | Dynamic viewport and keyboard (03-dynamic-viewport-and-keyboard.md) | 01 | not-started |
| 04 | Stylesheet structure and sticky offsets (04-stylesheet-structure-and-sticky-offsets.md) | none | not-started |
| 05 | Touch-target floor (05-touch-target-floor.md) | 01 | not-started |
| 06 | Safe-area chrome (06-safe-area-chrome.md) | 01 | not-started |
| 07 | 13-inch and tablet device bands (07-device-band-shell-tuning.md) | 02, 03, 05 | not-started |
| 08 | Marketing site adaptation (08-marketing-site.md) | 01, 05 | not-started |
| 09 | Final validation, review and docs (09-final-validation-review.md) | 01-08 | not-started |

Task status lives in ../STATE.md, which is the source of truth; this table only
orients a reader.

Parked-tree rule: this checkout carries another session's uncommitted
brand/dashboard work. Tasks favour additive files (a new responsive stylesheet or
script) and, where an existing shared file must change, stage HEAD plus only the
task hunk with the git hash-object recipe in ../README.md. Never stage the parked
hunks.
