# Dynamic workflow marketing preview — visual review

Date: 2026-10-11. Surface: static Hutch landing page, `#workflow` preview and
`#get` availability table. This is a human review of opened Chromium captures,
not a full accessibility certification.

## Captures and checks

The browser test ran at 1440×900, 768×1024, 360×800 and 320×800 CSS pixels
with reduced motion enabled. It opened the workflow teaser and availability-row
captures at every size. The test checked the actual text, FAQ answers, the
“Workflow questions” link to `#faq`, element bounds, and document horizontal
overflow. There were no page errors, external requests or provider calls.

```sh
uv run pytest tests/e2e/test_website.py -q
```

Result: **29 passed**. Browser and source hashes, measured bounds, zero overflow,
and screenshot/trace hashes are in [`results.json`](results.json). The focused
test is `tests/e2e/test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive`.

## Opened-view observations

- At 1440px, the teaser follows the established three-card “How it helps” story
  with a 32px gap. The heading and explanatory copy stay in a readable text
  column; the FAQ action is aligned on the right.
- At 768px, the same two-column card remains legible without colliding with the
  action. At 360px and 320px it becomes a single column; the status, title,
  caveat and link remain visible, with no horizontal clipping.
- On desktop and tablet, the availability row carries an Experimental status
  chip. The phone layout hides the table’s repeated status column, so the row’s
  own text begins “Experimental” to keep that state visible at narrow widths.
  The long neighboring availability entries wrap within the table and cause no
  document overflow.
- The teaser preserves Hutch’s dark surface, blue information marker, green
  brand rail, existing type scale and button treatment. It states that a person
  starts a saved workflow and that chat recommendations, Auto launches, routine
  links, and local author/selector qualification are unavailable.

The viewport screenshots are focused on the teaser and availability row. The
desktop workflow screenshot places the page under the sticky navigation while
the teaser is in view; the teaser itself is fully visible. This is a scrolled
capture, not the page’s initial-load position.

## Scorecard

Scores follow the project’s shape-and-background review weighting (aesthetic
45%, functionality 40%, regression health 15%). Human judgments are marked as
such; browser assertions are not a substitute for assistive-technology testing.

| Dimension | Score | Basis |
|---|---:|---|
| Aesthetic *(human)* | 9.2/10 | Existing journey and tokens remain intact; the new preview has clear hierarchy and responsive spacing. |
| Functionality | 10/10 | Copy, four FAQ claims, CTA navigation, responsive bounds and overflow assertions passed. |
| Regression health | 9.3/10 | All 29 website browser tests passed; asset hashes match; no page errors or external requests. |
| **Combined** | **9.5/10** | Weighted score; evidence supports these landing-page changes only. |

Not covered: real screen readers, forced-colors mode, browser zoom, text-spacing
overrides, RTL, physical devices, or a full keyboard-only audit of the entire
landing page.
