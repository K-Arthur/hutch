# Delegated-wait UI visual review

Captured 2026-10-12 05:25 UTC in Chromium 153.0.8010.12 against the local mock runtime.
The fixture contains one parent in `waiting_child` and one pending child; it made zero
provider calls. The owner app was opened at 1440×1000, 768×1024, 360×800, and 320×800.
The paired review view was opened at 320×844.

## Opened views and observations

- [Desktop, 1440 px](desktop-1440.png): the parent status and Stop action are visible in the
  run view. The header correctly reads **1 waiting · 1 queued**; it does not call the parked
  parent working.
- [Tablet, 768 px](tablet-768.png): the header actions wrap into a second row without obscuring
  the run state or Stop control.
- [Phone, 360 px](phone-360.png) and [compact, 320 px](compact-320.png): the conversation title
  wraps at 320 px; the full waiting label and a text-labeled Stop control remain reachable, with
  no horizontal page overflow.
- [Text-spacing override, 320 px](text-spacing-320.png): 1.5 line height, 0.12 em letter spacing,
  0.16 em word spacing, and 2 em paragraph spacing produce no horizontal overflow; the waiting
  label remains visible and the Stop target stays 44×44 CSS px.
- [Forced colors, 320 px](forced-colors-320.png): the system renders the waiting label in
  CanvasText against Canvas at 21:1 measured contrast. This check exposed and fixed the prior
  amber-on-white label regression.
- [Paired review, 320 px](paired-review-320.png): review permission exposes the current status
  and **Stop run**. The progress entry says “Waiting for delegated work” instead of exposing the
  status event's raw object fields.

The opened captures show the existing graphite surfaces, emerald product identity, and amber
waiting state. At 360 px the global status cluster is collapsed by the narrow header, while the
run-level status remains visible. The reduced-motion preference matched and the app's fast-motion
token resolved to `0ms`. Touch emulation measured the owner Stop target at 44×44 CSS px and the
paired **Stop run** target at 102×48 px. Keyboard focus reached both controls. The browser recorded
no console errors or failed requests. Exact view widths, overflow and target measures, source hashes,
screenshot hashes, and the trace are in [validation.json](validation.json) and The raw Playwright trace was omitted after privacy review found session cookies in the archive..

## Scorecard for this slice

Scores use the project’s 0–100 gates, applied only to the delegated-wait surfaces and checks
listed above. They are a human review of opened screenshots plus automated state assertions,
not an accessibility certification.

| Dimension | Score | Evidence |
|---|---:|---|
| Aesthetic | 93/100 | Amber distinguishes a durable wait from active work; labels remain readable and the established layout reflows across all captured widths. |
| Functionality | 97/100 | API regression verifies live/waiting/queued buckets; touch-emulated browser checks status, 44 px owner and 48 px paired Stop targets, keyboard focus, paired review, text spacing, forced colors, reduced motion, zero overflow, and clean console/network state. |
| Overall | 93/100 | The project combines the two dimensions using the lower score. |

Not exercised here: 200% browser zoom, physical-device behavior, screen readers, or clicking Stop
through the paired session. The browser fixture verifies that Stop is exposed, correctly sized, and
focusable; cancellation cleanup is covered by separate runtime tests. Live model output and live
delegated work are not validated by this fixture. The Impeccable detector reported three unrelated
existing advisories elsewhere in `style.css` (4 px and 16 px radii, and `#e1e5e9`); none points to
the selectors changed for this slice.
