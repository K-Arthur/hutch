# Adaptive response-style UI visual review (2026-10-11)

The screenshots in `artifacts/persona-ui-v2-2026-10-11/` were manually inspected after the real-app Chromium test passed.
The test uses isolated SQLite state, Chromium 153.0.8010.12, reduced motion, no configured model route, no provider calls,
and a network rule that blocks non-local requests.

Reviewed settings screenshots: `settings-controls-phone.png`, `settings-controls-tablet.png`,
`settings-controls-desktop.png`, `settings-controls-compact-phone.png`, `settings-custom-phone.png`, and
`settings-controls-zoom-200-effective.png`. The three top-level controls remain easy to scan; customization follows in a
separate group. The form stacks at phone width, uses two columns at tablet/desktop, and the compact-phone layout stays
within the viewport. Custom slider and inheritance states are distinguishable, and the optional controls continue below
the viewport using the existing page scroll.

Reviewed conversation screenshots: `chat-phone.png`, `chat-tablet.png`, `chat-desktop.png`, `chat-compact-phone.png`,
`chat-zoom-200-effective.png`, and `chat-compact-text-spacing.png`. The scoped style controls remain inside the existing
bounded, scrollable conversation menu; the next-reply chip remains attached to the composer, including at phone width.
The text-spacing override produces no horizontal page overflow. The existing conversation-title selector can visually
truncate its selected title when space is tight; it remains a native selector and this check does not change that shared
chat-header behavior.

Automated evidence in `validation.json` records zero page errors, zero external requests, zero inference requests, exactly
two expected 409 conflict responses, reduced-motion preference, and a composited hint-text contrast ratio of 9.80:1. The
browser regression exercises labeled range controls and checkboxes, keyboard disclosure/save, dirty state, reset, focus
recovery after save, persistence, concurrent profile/conversation updates, local next-reply storage, and reflow at 320,
360, 720×480, 768 and 1440 CSS pixels. `tests/test_persona.py` plus `tests/test_runtime_builtin.py` also pass (100 tests).
The Playwright trace is `trace.zip`.

The 720×480 viewport tests the effective CSS layout width corresponding to 200% zoom at 1440×960. A native browser zoom
gesture could not be applied through this headless browser runner, so this is documented as equivalent-width reflow
evidence, not a direct browser-zoom test. Screen readers, Firefox/WebKit, and physical devices remain untested.

The `impeccable detect` scan returned three advisory findings in unchanged shared stylesheet rules (lines 1359, 1705,
and 2291 at capture time); none is in the persona CSS diff. New persona styles use Hutch's documented radius, spacing,
and color tokens.

## Answer corrections

The actual-app chat regression passed in Chromium 153.0.8010.12 with reduced motion and touch input. I inspected
`chat-answer-actions-phone.png`, `chat-answer-actions-tablet.png`, `chat-answer-actions-desktop.png`,
`chat-answer-actions-compact-phone.png` and `chat-answer-actions-zoom-200-effective.png` individually. The three
correction actions sit next to the existing Reply action, wrap cleanly at 320px, retain Hutch's dark palette and
do not cause horizontal overflow. The measured buttons are 44px high and their text has 9.92:1 contrast against
the chat surface across all captured widths. Focus returns to the activated action when the feed refreshes.

The test navigates among Shorter and Go deeper with the keyboard, activates Shorter, and checks that the exact
answer id and typed correction are sent once. The composer text and selected range remain intact, and the reader's
scroll offset is unchanged when the new run appears. A completed OpenCode fixture still renders its answer but
does not show corrections. The mock route's engine is disabled: there are zero provider calls, page errors,
console errors, failed local responses or external requests. See `validation.json`, `impeccable-detect.json` and
`trace.zip` beside the screenshots.

Viewport checks cover 360×844, 768×960, 1440×960, 320×800 and 720×480 as the effective CSS viewport for 200%
reflow at 1440×960. The browser runner does not provide a native zoom gesture. Screen readers, Firefox/WebKit and
physical devices remain untested; this browser fixture verifies UI handling and does not measure provider
adherence or response quality.

## Local answer feedback

The local feedback controls passed the real-app Chromium regression with captures at 360×844, 768×960, 1440×960,
320×800, and 720×480 effective CSS pixels for 200% reflow. I inspected `feedback-phone.png`, `feedback-compact-phone.png`,
`feedback-tablet.png`, `feedback-desktop.png`, `feedback-zoom-200-effective.png`, and the selected-reason state
`feedback-needs-work-reason.png` individually. The two ratings wrap at 320px without horizontal overflow; the reason
selector remains reachable below the rating controls. In the selected-reason screenshot, the local saved-state message
stays beside the controls and repeated saves do not leave stacked notifications over the composer.

Both rating buttons measure 44px high with 9.92:1 text contrast. Keyboard activation, optional reason selection and
clearing are covered. The selected answer's composer draft, selected text range, reader position and focus survive the
refresh. Four revision-checked PUTs were observed (revisions 0–3); there were no message POSTs, provider calls, page or
console errors, failed responses, or external requests. The disabled OpenCode fixture does not expose these controls.
The trace, screenshots and measured request/viewport record are in
`artifacts/persona-feedback-2026-10-11/`; `impeccable-detect.json` has no reported findings. This is local UI and
storage-path verification, not evidence about model response quality. Screen readers, Firefox/WebKit, physical devices
and native browser zoom remain untested.
