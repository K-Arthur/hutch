# Overlay unification pass

Every modal, popover, dropdown menu and tooltip in the Hutch product now routes
through two shared primitives (modal and popover) instead of a growing
collection of one-off overlays. This directory is the durable memory for that
work: a fresh session should be able to resume from `STATE.md` plus git history
alone.

## Status

- Complete: [COMPLETION.md](COMPLETION.md).
- Audit gate (inventory, matrix, gap list): [inventory.md](inventory.md) and
  [audit.md](audit.md).
- Design spec: [`src/hutch/web/docs/overlays.md`](../../src/hutch/web/docs/overlays.md).

## Document map

| File | Purpose |
| --- | --- |
| inventory.md | Step 1: every overlay, file/line, trigger, category, missing state |
| audit.md | Step 2: audit matrix and the gap list that drove the migration; final status per gap |
| COMPLETION.md | What shipped, by category, with test evidence and residual risk |
| STATE.md | Run history, commands, evidence index and handoff |
| screenshots/<label>/ | Committed visual evidence: PNG captures, summary.json, assertions.txt |

## Reproducing validation

    # fast loop: contract assertions, no screenshots
    .venv/bin/python scripts/validate_overlays.py --no-screenshots --no-light --label quick

    # full evidence run for a tree
    .venv/bin/python scripts/validate_overlays.py --label "$(git rev-parse --short HEAD)" --light

    # focused browser contract tests
    UV_CACHE_DIR=/tmp/uv-cache-ov uv run --frozen --no-sync pytest -q tests/e2e/test_overlays.py

The harness boots the real FastAPI app on an ephemeral loopback port with a
seeded assistant, drives Chromium through the checklist in `audit.md` and writes
`docs/overlays/screenshots/<label>/`. It is read-only with respect to product
code. Exit code is non-zero on any failed assertion.

## Conventions

- No emoji in source, docs or UI.
- Tokens only: overlay rules read `--hutch-*` tokens; the token mirror at the top
  of `static/hutch-overlays.css` is the one documented literal site because
  server pages do not load compiled `ui.css` (same pattern as
  `static/hutch-forms.css`).
- A category is never silently converted: a panel that blocks the page is a
  modal even when it looks like a drawer, and a panel that dismisses on outside
  click is a popover even when its role is `dialog`.
- Works only through the two primitives: new overlays call
  `window.HutchOverlay.modal` / `HutchOverlay.popover` or the Jinja macros; they
  do not invent a third overlay system.
