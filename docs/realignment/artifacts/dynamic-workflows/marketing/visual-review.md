# Dynamic workflow marketing preview — visual review

Date: 2026-10-12. Surface: static Hutch landing page, `#workflow` preview and
`#get` availability table. This is a human review of opened Chromium captures,
not a full accessibility certification.

## Captures and checks

The browser test ran at 1440×900, 768×1024, 360×800 and 320×800 CSS pixels
with reduced motion enabled. It opened the workflow teaser and availability-row
captures at every size. A separate 320×800 pass applied WCAG 1.4.12 text-spacing
values (letter spacing `.12em`, word spacing `.16em`, line height `1.5`,
paragraph spacing `2em`) and browser `forced-colors: active`. Keyboard Tab and
Shift+Tab moved focus to and from the “Workflow questions” link. The test checked
the FAQ answers, `#faq` destination, element bounds, 44px target height, focus
outline and document horizontal overflow. There were no page errors, external
requests or provider calls.

```sh
TMPDIR=/var/tmp .venv/bin/pytest -q tests/e2e/test_website.py::test_local_asset_urls_use_current_content_hashes tests/e2e/test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive --basetemp=/var/tmp/hutch-marketing-a11y-review
```

Result: **2 passed in 5.94s**, including the dedicated marketing journey
(Chromium 153.0.8010.12 / Playwright 1.63.0). Browser and source hashes, measured
bounds, zero overflow, and screenshot/trace hashes are in
[`results.json`](results.json).

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
- The availability copy is intentionally shorter than the workflow preview. It
  keeps the pin, separate enable action, Run now behavior, local-supervisor
  requirement, exact-profile qualification and provider limitation while reducing
  the tall table row on phone screens.
- The teaser preserves Hutch’s dark surface, blue information marker, green
  brand rail, existing type scale and button treatment. It explains that chat
  route cards and saved-workflow Auto starts require exact-profile selector
  qualification; the two local profiles tested did not qualify. It states that
  generated-plan Auto does not create plans. An owner can link an activated
  method to an existing routine, with a pinned revision and checked inputs; the
  FAQ explains the separate enable action and one-off Run now behavior. The
  workflow copy explains that an owner can request Pause during a running step; the current
  node and owned work settle before the next step is held. A run that is already
  parked can be resumed from the same chat. The FAQ explains that pending
  questions remain answerable and no downstream work starts before Resume.
- With text spacing applied, the 320px teaser grows to 858.5px and its action
  falls below the initial viewport. Keyboard focus scrolls it into view. The
  first run found a 40px action target; the link now has a 44px minimum height.
  The re-run measures 44px, and the blue focus outline remains visible against
  the dark surface.
- In forced-colors mode Chromium switches to a black-and-white system palette.
  The card boundary and focused link remain visible, with a high-contrast double
  outline around the target. The 320px view has no horizontal overflow.

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

Not covered: real screen readers, actual browser-chrome zoom, RTL, physical
devices, or a full keyboard-only audit of the entire landing page. Text-spacing
values and the forced-colors palette were browser-emulated, not configured
through an operating-system accessibility setting.
