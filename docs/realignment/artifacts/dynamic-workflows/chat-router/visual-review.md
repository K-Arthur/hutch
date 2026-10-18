# Chat workflow suggestion — visual review

Date: 2026-10-11. Surface: Hutch chat route card and its saved-workflow review dialog.
The browser fixture is synthetic and validates the presentation/interaction contract;
the qualified runtime tool loop is covered separately by scripted model/API tests.

## Captures and checks

The Chromium test ran at 1440×960, 768×1024, 360×800 and 320×740 CSS pixels. It opened
the card in the app panel and captured the explicit saved-workflow review dialog. The
long workflow label was intentional. The test checked reflow and document width, the
44px review target, Enter activation, Cancel focus restoration, and that review did not
start a run. No page errors, failed requests or external requests occurred.

```sh
uv run pytest tests/e2e/test_workflow_route_card.py -q -s
```

Result: **1 passed**. Browser version, computed type/spacing, element bounds, interaction
notes and artifact/source hashes are in [`results.json`](results.json). Opened captures:
[`suggestion-desktop.png`](suggestion-desktop.png),
[`suggestion-tablet.png`](suggestion-tablet.png),
[`suggestion-phone.png`](suggestion-phone.png),
[`suggestion-compact-phone.png`](suggestion-compact-phone.png), and
[`suggestion-review-dialog.png`](suggestion-review-dialog.png).

The journey was rerun on 2026-10-12 with Chromium 153.0.8010.12 and Playwright 1.63.0;
it again passed (1 test in 4.86s) with no page errors, failed requests or external requests.
At 320×740 it additionally applies the WCAG text-spacing values (line height 1.5, letter
spacing 0.12em, word spacing 0.16em, paragraph spacing 2em) and emulates forced colors.
Both states assert zero document overflow, a visible heading, a 44px focused action and
the action above the fixed composer. The result JSON records current source and artifact hashes.

## Opened-view observations

- At desktop and tablet widths the suggestion reads as a compact card above the composer;
  its title, route label, rationale, simpler option and review action stay in one readable
  hierarchy.
- At 360px and 320px the long method title wraps without clipping. The rationale and simpler
  option remain distinct, and the review action stays visible at the bottom of the card.
- The action is 44px high. Enter opens the explicit saved-method dialog; Cancel returns
  keyboard focus to the action and leaves the conversation without a workflow run.
- The empty workflow inspector is a short “Saved workflows” disclosure, not a false dynamic
  run panel. The card uses the established dark panel, neutral border, emerald action, 16px
  UI type, 24.8px line height and 12px padding/radius. The desktop layout remains visually
  quiet beside chat content.
- In the 320px fixture, the existing floating “Jump to latest” control appears because the
  preserved scroll position is above the latest message; it overlays one line of rationale.
  The review action remains unobscured. This narrow-view limitation belongs with the broader
  chat scroll/reconnect work.
- All captures have zero horizontal overflow, and the page emitted no errors or network
  failures. These fixture captures do not prove that a live local selector is qualified;
  both tested Qwen3 profiles failed that gate.
- Under the text-spacing override the card grows taller than the chat viewport, so the CTA
  is below the initial fold and partly behind the fixed composer until the user scrolls or
  tabs to it. Keyboard focus scrolls the full 44px target above the composer; document width
  remains 320px with no horizontal overflow. This is usable through the scroll region, though
  the initial view does not show the entire card at once.
- Forced-colors emulation changes the canvas to white with black text and borders; the card,
  conversation text and outlined review action remain distinguishable. The browser assertions
  confirm system foreground colors for user and assistant messages. The capture is Chromium
  emulation and does not prove behavior on every operating-system high-contrast theme.

## Scorecard

Scores follow the project's shape-and-background weighting (aesthetic 45%, functionality
40%, regression health 15%). Browser assertions do not replace assistive-technology testing.

| Dimension | Score | Basis |
|---|---:|---|
| Aesthetic *(human)* | 8.7/10 | Clear hierarchy and consistent Hutch styling; the floating latest control overlaps rationale in one narrow scrolled state. |
| Functionality | 9.0/10 | The review action is keyboard-operable and non-starting; viewport and focus assertions passed, with a documented scroll-control overlap. |
| Regression health | 9.0/10 | No overflow, page errors, failed requests or external calls in the focused E2E run. |
| **Combined** | **8.9/10** | Weighted visual score for this card and dialog only. |

Not covered: real screen readers, actual browser zoom, app-wide text-spacing/forced-colors
coverage, offline/reconnect in this route-card slice, paired-phone surfaces, or live behavior
from a qualified selector model.
