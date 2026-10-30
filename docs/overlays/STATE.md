# Overlay unification - state

Last updated: 2026-10-30 | Last commit: 548a2d6e (working tree carries the parked
design-system work) | Goal: goal-13a1b37f-dc0b-41b5-a09b-05effbd6a77c
Status: COMPLETE for the audited scope; deferred and unverified items are listed
in COMPLETION.md.

## Run history

| Phase | Work | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Recon: two shells + design-system tree, overlay factories, tokens, tests | done | .dsh/long-horizon/overlays/CHARTER.md |
| 1 | Read-only team audit (templates, SPA, CSS/tokens, tests/docs) | done | .dsh/long-horizon/overlays/audit/*.md |
| 2 | Step 1 inventory + classification | done | docs/overlays/inventory.md |
| 3 | Step 2 matrix + gap list | done | docs/overlays/audit.md |
| 4 | Step 3 token layer (z, scrim, elevation, motion, focus ring) | done | src/hutch/web/styles/hutch-tokens.css, hutch-overlay-tokens.css, hutch-theme-overrides.css |
| 5 | Step 5 design spec before migration | done | src/hutch/web/docs/overlays.md |
| 6 | Step 4 primitives (Jinja macros, runtime, CSS contract) | done | templates/macros/{modal,popover}.html, static/hutch-overlay-*.js, static/hutch-overlays.css, static/hutch-popovers.css |
| 7 | Batch 1 destructive confirmations | done | audit.md "Destructive confirmations" |
| 8 | Batch 2 form dialogs (openModal adapter) | done | audit.md "Form dialogs" |
| 9 | Batch 3 pickers/menus (controls.js adapter) | done | audit.md "Pickers and menus" |
| 10 | Batch 4 tooltips | done | audit.md "Tooltips" |
| 11 | Batch 5 remaining overlays (needs-you, palette, nav drawers) | done with documented deferred items | audit.md, COMPLETION.md |
| 12 | Step 7 verification + evidence | done | docs/overlays/screenshots/working-tree, tests/e2e/test_overlays.py |

## Evidence index

| Label | What it proves |
| --- | --- |
| docs/overlays/screenshots/working-tree | 40/40 assertions: dropdown focus/Escape/outside click/fit, destructive non-dismissibility, scroll lock, server-page confirm form, tooltip, palette, needs-you, stacking, 320/844 viewports, 200% text, light token scope, no page errors |
| tests/e2e/test_overlays.py | 10 browser contract tests (focused path, nested dialog, portal fallback, busy/error/success, reduced motion + forced colors) |

## Commands

    .venv/bin/python scripts/validate_overlays.py --label working-tree --light
    UV_CACHE_DIR=/tmp/uv-cache-ov uv run --frozen --no-sync pytest -q tests/e2e/test_overlays.py
    UV_CACHE_DIR=/tmp/uv-cache-ov uv run --frozen --no-sync pytest -q tests/e2e/test_dropdown_controls.py tests/e2e/test_popup_layout.py
    UV_CACHE_DIR=/tmp/uv-cache-ov uv run --frozen --no-sync python scripts/audit_context_hygiene.py

## Known pre-existing failures (not caused by this pass)

The checkout already carried another session's parked brand/dashboard work.
These were failing before the overlay work and remain outside its scope:

- `scripts/audit_context_hygiene.py`: six violations in parked files
  (bot_deletion.py, cli.py, pages.py, store.py, test_bot_deletion.py,
  test_commit_attribution.py). No overlay file is over the 400-line budget.
- `tests/e2e/test_radius_scale.py`: `.task-source` 999px in untracked tasks.css.
- `tests/e2e/test_type_and_spacing_scale.py`: 11px models labels + 15px heading
  from the parked models markup/CSS.
- `tests/e2e/test_wcag_fixes.py` two tests: stale selectors for the parked
  assistant-settings restructure.
- `tests/e2e/test_design_system.py` two tests: message-search rename and a 40px
  persona-preview control, both from parked work.

## Handoff

- Re-run the two commands above after any further overlay change.
- Deferred: nav-drawer dialog semantics (A5/A6 keep their landmark structure),
  async menu loading state (S6), re-anchor during ancestor animation (P4),
  toast internals (T5), marketing nav dialog (separate surface).
- Unverified: WebKit/Safari and Firefox engines are not installed in this
  checkout; the no-Popover-API fallback is covered by stubbing `showPopover`,
  but a real Safari 16 pass is still owed.
