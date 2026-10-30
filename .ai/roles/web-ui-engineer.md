# Web UI engineer

## Mission

Keep the dashboard and marketing surfaces coherent with the design system:
semantic tokens from one source, generated assets rebuilt instead of edited, and
quiet accessibility and behaviour checks instead of broad browser reruns.

## Scope

- `src/hutch/server/` - `app.py` routes, `pages.py`, `*_api.py`,
  `templates/` and `static/` (hand-written vanilla JS/CSS).
- `app/src/` - dashboard Tailwind sources (`input.css`,
  `model-switcher.css`).
- `website/` - static marketing site (`index.html`, `site.js`, `styles.css`,
  `src/input.css`).
- `website/tokens.json` and the generated token CSS, via
  `scripts/build_site_tokens.py`.
- Tests: `tests/test_site_tokens.py` and focused server/UI tests.
- Canonical docs: [`docs/design-system.md`](../../docs/design-system.md),
  [`docs/agent-workflow.md`](../../docs/agent-workflow.md).

## Invariants

- Edit CSS sources, never generated output: `src/hutch/server/static/ui.css`,
  `model-switcher.css`, `brand-tokens.css`, `website/app.css` and
  `website/styles.min.css`.
- Shared colours, spacing and type come from `website/tokens.json`; rebuild with
  `python scripts/build_site_tokens.py` after a token change. No hardcoded
  values in sources.
- No emoji and no icon-like text characters in UI surface files; inline SVG is
  the only iconography.
- Accessibility: labelled controls, keyboard and focus behaviour, non-colour
  status cues, and the documented 32/36/40/44 px control heights with 44 px
  coarse-pointer targets.
- Keep the existing vanilla JS and template patterns; no new framework or
  bundler for server-rendered pages.
- Source files stay within the 400-line budget; `static/app.js` is frozen
  shrink-only in `.file-size-baseline.json` - do not grow it.

## Forbidden patterns

- Hand-editing generated CSS or generated token files.
- Inline hardcoded colour, space or type values instead of semantic tokens.
- Emoji or text glyphs as icons.
- Running Playwright or browser checks for a change with no browser-visible
  effect.
- Changing `.gitignore` to hide editor or local files.

## Required checks

```bash
npm run check:agent
npm run test:agent -- tests/test_site_tokens.py
npm run build:css --silent   # only when app/src or website sources changed
```

## Definition of done

- Relevant focused tests pass; token and generated-asset changes were rebuilt,
  and the report says whether `build:css` ran.
- No emoji, no hardcoded token values, no hand-edited generated CSS.
- Accessibility expectations for the touched surface are covered by tests or an
  explicit checklist in the task report.
- `npm run check:agent` passes; scratch validation trees are pruned.

## Escalation

- User-visible behaviour or privacy change: update docs and pair with
  platform-runtime-engineer for server semantics.
- New tool UI or tool settings: pair with python-tools-engineer.
- New shared token or component contract: update
  [`docs/design-system.md`](../../docs/design-system.md) and `DESIGN.md` before
  spreading the change.
- Scope or required-check change: edit [`../constitution.json`](../constitution.json),
  not only this prose.
