# Paired-phone workflow supervision visual review

Captured from the real browser/API workflow journey on 2026-10-11. The task submitted two
local declarative `ask` workflows, let the supervisor park both, answered one durable question,
and requested Stop on the other. No model request or external effect ran. Screenshots and the
Playwright trace are beside this review; the results JSON stores their SHA-256 hashes and source
hashes.

At 390 CSS pixels, the four-tab navigation fits without clipping. The workflow detail separates
planned structure from a question-backed waiting instance, keeps the workflow title readable,
and places status opposite the step name. The review view lists each pending question with its
durable ID, prompt, options, expiry and a full-width answer action. Two simultaneous questions
with the same prompt remain distinguishable by their workflow titles and durable IDs. Chromium's
computed accessibility semantics expose separately named forms and answer controls containing
the matching question ID and prompt; the authority-boundary explanation is associated with each
control as its description. The 320px capture shows both cards without horizontal overflow, and
the answer actions remain at least 44px high. The Stop action is visible only for a live workflow
to a review session, and disappears after the server records Stop.

At 320 CSS pixels, the detail reflows to one column with no horizontal scroll. The status and
step name remain distinguishable, and the local-only data boundary stays visible. The Hutch
descriptor wraps under the wordmark at this width; it stays legible. The captured post-Stop view
includes the confirmation notice above the stopped workflow.

The browser run measured a 320px viewport and 320px document width, a 44px minimum height for
phone tab/header/detail actions, zero page errors, and HTTP 200 for both answer and Stop. The
separate monitor-only browser case confirms the Review tab and ordinary-run Stop/Resume controls
are absent and the app makes no 403 review requests. A capability-downgrade step confirms the
phone refreshes the session before showing review data or retry controls. API tests confirm that
monitor-only cannot read or mutate questions/Stop, and that paired sessions cannot access
workflow planning, qualification probes, policy or amendment routes. Projection checks confirm
that inputs, results and `instance_key` are absent.

This pass reviews default color, responsive layout, labels and target geometry. Playwright role
queries verify the browser's computed names and descriptions; operating-system screen-reader
output, browser zoom, text-spacing overrides, forced colors, reduced motion, offline reconnect
and live iOS/Android browsers remain unverified. See `paired-phone-workflows-results.json` for
captured state, source hashes and artifact hashes.
