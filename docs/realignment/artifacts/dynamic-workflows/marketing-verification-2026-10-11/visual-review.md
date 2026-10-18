# Workflow marketing visual review — 2026-10-11

Scope: the real local marketing website, the private-preview workflow card, and its Availability row. The copy was reduced to 99 visible words so the card, including its action, fits inside the 320×800 viewport. Routine schedule behavior remains in the Availability row and FAQ.

I opened the Chromium screenshots at 1440×900, 768×1024, 360×800, and 320×800 for both the card and Availability row. The card keeps the site's dark surface, fine border, and teal edge accent. Its status and heading lead into the behavior limits; the action sits beside the copy on desktop/tablet and below it on phones. At 320px the complete card and action are visible without horizontal scrolling. The Availability row retains its label and full description at compact width, with dense wrapping that remains readable.

The browser journey passed with no page errors, external requests, or horizontal overflow. It exercised the live static marketing page, expanded Availability and FAQ content, and verified the workflow claims. Screenshots and the Playwright trace are retained beside this review. The evidence and source hashes are in `validation.json` and `results.json`.

| Dimension | Score | Evidence |
|---|---:|---|
| Aesthetic | 8.8/10 | Clear status-to-heading hierarchy and consistent Hutch colors; the 320px Availability description is information-dense. |
| Functionality | 9.5/10 | Dedicated browser journey passed; copy claims, FAQ, CTA, and four widths checked; card height is 643.7px at 320px. |
| Regression health | 9.0/10 | Focused live-site test passed with zero overflow, page errors, external requests, or provider calls. |
| Combined | **9.1/10** | Weighted per project rubric: aesthetic 45%, functionality 40%, regression health 15%. |

Limits: this is Chromium emulation, not a physical-phone or screen-reader review. Browser-chrome zoom, system text scaling, and forced-colors were not part of this site-specific journey. The score is a recorded visual judgment with measured layout evidence, not an accessibility certification.

## Captures

- Workflow card: `workflow-desktop.png`, `workflow-tablet.png`, `workflow-phone.png`, `workflow-compact-phone.png`
- Availability row: `availability-desktop.png`, `availability-tablet.png`, `availability-phone.png`, `availability-compact-phone.png`
- Interaction trace: `trace.zip`
