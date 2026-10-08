# Visual validation record

Captured 2026-10-07 from the `realign/platform` worktree after the shared-budget UI and marketing copy changes. The marketing site was
served from this worktree. Hutch used `/tmp/hutch-s5-visual.mbtpt6`, a disposable state directory populated by `hutch init` and one
OpenCode Go connection configured with a synthetic account ID, a 100k token allowance, and a $5 estimate limit. No API key was stored,
and no provider request was made. No personal workspace files were used. Both servers bound to loopback only.

## Reproduction

```bash
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch init
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch connections add opencode-go \
  --account-id shared-dev --account-daily-cap-usd 5 --allowance-tokens 100000 --allowance-window month
python3 -m http.server 18001 --bind 127.0.0.1 --directory website
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch serve --host 127.0.0.1 --port 18877
PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers .venv/bin/python \
  docs/realignment/capture_visual_validation.py \
  --site http://127.0.0.1:18001/ --app http://127.0.0.1:18877/
```

Capture environment: Python 3.13.15, Playwright 1.63.0, bundled Firefox 155.0. The site, dashboard, Connections and Usage pages
returned HTTP 200 at 1440×1000 desktop, 900×1024 tablet and 390×844 phone. `capture-results.json` records dimensions, CTA targets,
errors and phone-menu behavior. Each desktop page has a Playwright trace with screenshots and DOM snapshots. Both servers were stopped
after capture.

## Inspected artifacts

The screenshots are under [artifacts/visual-validation](artifacts/visual-validation/). The complete page captures are
[site desktop](artifacts/visual-validation/site-desktop.png), [site tablet](artifacts/visual-validation/site-tablet.png),
[site phone](artifacts/visual-validation/site-phone.png), [app desktop](artifacts/visual-validation/app-desktop.png),
[app tablet](artifacts/visual-validation/app-tablet.png), [app phone](artifacts/visual-validation/app-phone.png),
[Connections desktop](artifacts/visual-validation/connections-desktop.png), [Connections tablet](artifacts/visual-validation/connections-tablet.png),
[Connections phone](artifacts/visual-validation/connections-phone.png), [Usage desktop](artifacts/visual-validation/usage-desktop.png),
[Usage tablet](artifacts/visual-validation/usage-tablet.png), and [Usage phone](artifacts/visual-validation/usage-phone.png). Fold-sized
site images are also saved for desktop, tablet and phone.

App phone state captures cover [empty](artifacts/visual-validation/app-phone-empty.png),
[loading](artifacts/visual-validation/app-phone-loading.png), [API error](artifacts/visual-validation/app-phone-error.png),
[pending approval](artifacts/visual-validation/app-phone-approvals.png), [cancelling](artifacts/visual-validation/app-phone-cancelling.png),
[reconnecting](artifacts/visual-validation/app-phone-reconnecting.png), and the [open navigation menu](artifacts/visual-validation/app-phone-menu-open.png).
Empty/loading/error used intercepted fixture responses. Cancelling is a synthetic local database row with no worker. Reconnecting used
a failed health-check route after an initial successful connection. The approval is from Hutch's offline demo seed.

## Findings

All 12 site/app/Connections/Usage captures had `document.scrollWidth == innerWidth`; captured pages had no JavaScript page errors. The site CTAs all
targeted existing internal sections and worked without authentication. The quickstart section truthfully says the source repository is
private and no PyPI package is published; anonymous visitors are not shown a dead public install link.

Connections and Usage were inspected after adding account caps and reservation estimates. Their forms and disclosure text fit at all
tested widths. The Usage page's per-bot budget table becomes labelled, stacked cards on a narrow screen; measured values stay distinct
from held estimates. The connection capture has no credentials configured and shows its missing-key state.

The final site screenshot shows the illustrated run badge as **DEMO supervised run** with an accessible name that calls it a demo
preview; it no longer suggests that an example is live system activity. The pending approval card and its decision buttons remain
visible on the phone viewport. The Studio keeps the composer reachable on desktop, tablet and phone. Conversation selector, New,
Archive and Settings wrap onto a second row at phone width without clipping.
Lifecycle chips use plain-language labels; the cancelling-state browser regression checks that “Stopping” remains visible while the
run is nonterminal. The full-screen app menu now moves focus to its first link, wraps Tab within the menu, closes on Escape and
returns focus to its toggle. The focused Playwright browser regression passed. The marketing-site menu also opened/closed by keyboard
and restored focus; site tablists changed selection with arrow keys. Reduced-motion mode was used for the repeatable screenshot pass.

The Impeccable static detector was rerun over the edited website and application HTML/CSS. It returned 44 heuristic findings: 41
warnings and 3 advisories, with no error-severity finding. Most flag the existing visual language (tracking, small labels, borders,
gradients/glows and a scripted demo typing animation), not measured user defects. Decorative pulse animation was removed from the site
status dots. The machine-readable source scan is in
[`impeccable-detect-source.json`](artifacts/visual-validation/impeccable-detect-source.json). A fresh URL/browser detector pass was
attempted but unavailable because Impeccable's URL mode requires Chromium and this host only has Firefox; the earlier
[`impeccable-detect.json`](artifacts/visual-validation/impeccable-detect.json) predates the current S5 page additions. No automated
contrast calculation or screen-reader audit was performed.

These are local UI checks, not a screen-reader certification, physical phone test, or test of a real supervised browser session.
Playwright used desktop Firefox at phone/tablet viewport sizes; it did not emulate touch input. Provider, Pi, local-model, portal
and physical-device workflows remain separate verification gaps in [the continuation ledger](ledger.md).

## Action intent review continuation

Schema v13 adds an uncertain-action card in chat and paginated older/cross-bot receipts in
Needs you. `tests/e2e/test_browser.py::test_uncertain_action_review_in_chat_preserves_history_and_recovers_lost_response`
captures uncertain, review-dialog and recorded-report views at desktop, tablet and phone sizes.
The fixture commits an operator report on the real API, drops its response and retries with the
same idempotency key. It verifies unchanged execution status/receipt/chain, retained draft and
restored focus. A second fixture checks 22 older receipts over two pages with real phone menu
and keyboard navigation. No live external effect, physical phone or screen reader is exercised.

Images, traces, timestamps and source hashes are in
[action-receipts](artifacts/action-receipts/). The app labels the recorded result a human report;
the original execution error remains inspectable under a folded report after all receipts are
reconciled. Marketing figure checks load anonymously at three widths and verify labelled fixture
copy and the responsive phone image. Inspection prompted this image-source improvement rather
than accepting a technically fitting but unreadable desktop thumbnail. Final counts/boundaries
are recorded in the continuation ledger.
