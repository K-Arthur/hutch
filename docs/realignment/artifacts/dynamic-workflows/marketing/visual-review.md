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
uv run pytest tests/e2e/test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive -q
```

Result: **1 passed**. Browser and source hashes, measured bounds, zero overflow,
and screenshot/trace hashes are in [`results.json`](results.json).

## Opened-view observations

- At 1440px, the teaser follows the established three-card “How it helps” story
  with a 32px gap. The heading and explanatory copy stay in a readable text
  column; the FAQ action is aligned on the right. The additional qualifier copy
  makes the card taller while retaining the original hierarchy.
- At 768px, the same two-column card remains legible without colliding with the
  action. At 360px and 320px it becomes a single column; the status, title,
  selector qualification, Auto limitation and link remain visible, with no
  horizontal clipping.
- On desktop and tablet, the availability row carries an Experimental status
  chip. The phone layout hides the table’s repeated status column, so the row’s
  own text begins “Experimental” to keep that state visible at narrow widths.
  The long neighboring availability entries wrap within the table and cause no
  document overflow.
- The teaser preserves Hutch’s dark surface, blue information marker, green
  brand rail, existing type scale and button treatment. It explains that chat
  route cards and saved-workflow Auto starts require exact-profile selector
  qualification; the two local profiles tested did not qualify. It states that
  generated-plan Auto and routine links are unavailable. The workflow copy now
  explains that an owner can request Pause during a running step; the current
  node and owned work settle before the next step is held. A run that is already
  parked can be resumed from the same chat. The FAQ explains that pending
  questions remain answerable and no downstream work starts before Resume.

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
| Aesthetic *(human)* | 9.0/10 | Existing journey and tokens remain intact; the taller preview keeps a clear hierarchy and responsive spacing. |
| Functionality | 9.5/10 | Copy, qualification and availability claims, FAQ answers, CTA navigation, responsive bounds and overflow assertions passed. |
| Regression health | 9.0/10 | The focused browser test passed; source and screenshot hashes are recorded, with no page errors or external requests. |
| **Combined** | **9.2/10** | Weighted score; evidence supports landing-page copy and layout only. |

Not covered: real screen readers, forced-colors mode, browser zoom, text-spacing
overrides, RTL, physical devices, or a full keyboard-only audit of the entire
landing page.
