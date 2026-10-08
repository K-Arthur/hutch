# Navigation functional and visual verification

Captured 2026-10-08 at 09:31 UTC with Python 3.13.15, Playwright 1.63.0, Firefox 155
and Pillow 12.3.0. The capture used `632add2` with the bounded local-inference admission, timing and sidebar
containment changes in its working tree. Source hashes are retained. This is local fixture
evidence, not a physical-phone, screen-reader or live provider certification.

## Reproduce

```bash
cd .worktrees/realign
PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers \
  .venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning tests/e2e
HUTCH_IMAGE_PYTHON=/home/kevina/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers \
  .venv/bin/python docs/realignment/capture_navigation.py
node --check src/hutch/server/static/app.js
.venv/bin/python scripts/build_site_tokens.py --check
.venv/bin/python scripts/audit_emoji.py
```

The image Python is the bundled runtime; a different Python with Pillow can be supplied.
The application itself has no Pillow dependency. The script starts two loopback-only
services on ephemeral ports, uses disposable state, joins service threads, and removes the
state after capture. No operator data is loaded. It refreshes the four static-site images
from its own desktop captures. Playwright traces include fixture requests and local paths;
they are sanitized demonstration material, not production telemetry.

## Results and inspection

The full offline suite after the approval, history, shutdown, provider and local-admission repairs passed **1,056 tests in
240.21s**, with unhandled background-thread warnings promoted to failures. The browser and
website suites passed **29 tests in 55.00s**. Conversation-order assertions verify
one user prompt preceding its assistant block, with no prompt echoed as an assistant answer
while waiting. A two-message queue checks that the earlier active run stays fresh after the
later message becomes current.

`artifacts/navigation/results.json` records **39 screenshots**, with zero page errors and
zero horizontal overflow at 1440×1000, 900×1024 and 390×844. Each viewport covers empty,
waiting, expanded Needs you, settings, Fleet, Activity, completion, run detail, model loading,
cancelling, error, reconnecting and the website. The approval and completion are real
deterministic mock journeys. Loading/cancelling use held synthetic lifecycle records;
error/reconnecting use intercepted failed requests. They do not prove physical cleanup,
actual model loading or remote-device reconnection; backend regressions cover their authority.

Inspected all three refreshed contact sheets for layout and state changes, plus individual full-size
phone drawer/cancellation, desktop completion and desktop queue captures. Earlier individual
phone waiting, tablet error and site fold captures were also inspected. Earlier full-size desktop/tablet/Fleet checks informed the repairs. The full
website captures are retained; contact sheets show their first fold only. Two additional
desktop/phone screenshots and metadata in `artifacts/fleet-attention/` cover failed queue
discovery, 51 persisted requests and a human wait preceded by an older queued turn. Both
were inspected in the preceding refinement; the browser suite refreshed them against the current
sources, with the same containment assertions. These waits are fixtures, not a real browser handoff. Six more captures and viewport/source
metadata in `artifacts/inference-admission/` show a held queue and recorded step timing on all
three sizes. Full-size desktop wait, phone wait/timing and tablet timing were inspected. These
are synthetic records; cross-process and runtime HTTP fixtures verify actual admission separately.

| Check | Observed result |
|---|---|
| Identity and conversation controls | Phone title truncates within its row; conversation, New, Stop and settings wrap below without overlapping the feed. A geometry regression checks header containment. |
| Approval visibility | Chat decisions remain outside collapsed tool activity. Phone drawer details scroll within a bounded region so the decision buttons stay visible; full arguments remain keyboard-reachable. |
| Focus and drafts | Escape restores menu focus, queue polls retain expanded review and focused decisions, and drafts survive immediate bot/conversation switches in their own scope. |
| Large queues | A 51-request fixture pages all requests and resolves the final request once, then reconciles the remaining 50. No bulk approval is offered. |
| Attention under failure | Both approval and human waits remain in Fleet's Needs you filter when queue discovery fails. The phone reminder ends above the content and has 44px Review/Dismiss targets. |
| Failed refresh | Retained cards show a refresh error and Retry; failure never becomes an empty queue or success receipt. |
| Inference queue | Queue position/reason is visible without typing. Recorded step timing separates queue wait; the sidebar filter fits within its own panel. |
| Cancellation and usage | Stopping remains nonterminal and disables duplicate Stop. Run detail and Activity use recorded cost and reported-token labels. |
| Reduced motion and keyboard | Reduced-motion capture, model-menu navigation, mobile-sheet focus/Tab/Escape and alias Back behavior are exercised by browser checks. |
| Marketing | Local anonymous CTA targets resolve, screenshots match the current shell, and provider/runtime limitations remain visible. The static site requests only its own assets. |

The final queue inspection found a sidebar filter extending past its panel despite zero page-wide
overflow. A scoped width and component geometry check repair this. Initial inspection found a cramped identity row, clipped approval label, reminder overlap,
an incorrect mobile scrim layer and a leftover 52px header rule. Those were repaired and
recaptured. The expanded full-payload request needed a bounded review region to keep phone
decisions visible. Two capture attempts failed on fixture/dependency assumptions (the status
label is Done, and Pillow lives in the image runtime); neither is counted as a passing capture.

## Design detector disposition

The primary workflow was Impeccable with the existing Hutch tokens and layout. The initial
detector pass and one confirmation returned design advisories; exit 2 is not a code/test
failure. `artifacts/navigation/design-detection.json` retains the confirmation output.

The 15 compact-padding and 12 small-text findings concern inherited metadata, compact tool
rows and tokens; primary body copy and decisions remain distinct, and phone decisions are
44px high. Two clipped-container warnings were checked against the native top-layer drawer
and phone model menu, including overflow/focus tests. The side accent and border/shadow
advisories retain the established state/overlay treatment. Typing/status animation is tied to
active state or successful health checks; reduced effects are available, with waits excluded
from typing. The bounce/hierarchy advisories concern incumbent decorative styles, not
blocking layout defects. These are explicit design acceptances, not a claim of perfect
accessibility or an invented quality score.

Screenshots, three traces and contact sheets are in `artifacts/navigation/`. No paid provider,
Ollama model, real browser handoff, Wayland portal, physical device or screen reader was used.
