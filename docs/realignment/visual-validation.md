# Visual validation record

Captured 2026-10-07 from the `realign/platform` worktree after the template, Studio and marketing-copy changes were integrated. The
marketing site was served from this worktree. Hutch used `/tmp/hutch-visual-final`, a disposable state directory populated with the
built-in demo; no account keys or personal workspace files were used. The final capture bound both servers to loopback only.

## Reproduction

```bash
env HUTCH_STATE_DIR=/tmp/hutch-visual-final .venv/bin/hutch init
env HUTCH_STATE_DIR=/tmp/hutch-visual-final .venv/bin/hutch demo seed
python3 -m http.server 18001 --bind 127.0.0.1 --directory website
env HUTCH_STATE_DIR=/tmp/hutch-visual-final .venv/bin/hutch serve --port 18877
PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers .venv/bin/python \
  docs/realignment/capture_visual_validation.py \
  --site http://127.0.0.1:18001/ --app http://127.0.0.1:18877/
```

Capture environment: Python 3.13.15, Playwright 1.63.0, bundled Firefox 155.0. The app and marketing site both returned HTTP 200.
The three viewports were 1440×1000 desktop, 900×1024 tablet and 390×844 phone. `capture-results.json` records page dimensions,
CTA targets, errors and phone-menu behavior. Each desktop page has a Playwright trace with screenshots and DOM snapshots. Both
servers were stopped after the capture.

## Inspected artifacts

The screenshots are under [artifacts/visual-validation](artifacts/visual-validation/). The complete page captures are
[site desktop](artifacts/visual-validation/site-desktop.png), [site tablet](artifacts/visual-validation/site-tablet.png),
[site phone](artifacts/visual-validation/site-phone.png), [app desktop](artifacts/visual-validation/app-desktop.png),
[app tablet](artifacts/visual-validation/app-tablet.png), and [app phone](artifacts/visual-validation/app-phone.png). Fold-sized
site images are also saved for desktop, tablet and phone.

App phone state captures cover [empty](artifacts/visual-validation/app-phone-empty.png),
[loading](artifacts/visual-validation/app-phone-loading.png), [API error](artifacts/visual-validation/app-phone-error.png),
[pending approval](artifacts/visual-validation/app-phone-approvals.png), [cancelling](artifacts/visual-validation/app-phone-cancelling.png),
[reconnecting](artifacts/visual-validation/app-phone-reconnecting.png), and the [open navigation menu](artifacts/visual-validation/app-phone-menu-open.png).
Empty/loading/error used intercepted fixture responses. Cancelling is a synthetic local database row with no worker. Reconnecting used
a failed health-check route after an initial successful connection. The approval is from Hutch's offline demo seed.

## Findings

All site and app viewports had `document.scrollWidth == innerWidth`; captured pages had no JavaScript page errors. The site CTAs all
targeted existing internal sections and worked without authentication. The quickstart section truthfully says the source repository is
private and no PyPI package is published; anonymous visitors are not shown a dead public install link.

The final site screenshot shows the illustrated run badge as **DEMO supervised run** with an accessible name that calls it a demo
preview; it no longer suggests that an example is live system activity. The pending approval card and its decision buttons remain
visible on the phone viewport. The Studio keeps the composer reachable on desktop, tablet and phone. Conversation selector, New,
Archive and Settings wrap onto a second row at phone width without clipping.
Lifecycle chips use plain-language labels; the cancelling-state browser regression checks that “Stopping” remains visible while the
run is nonterminal. The full-screen app menu now moves focus to its first link, wraps Tab within the menu, closes on Escape and
returns focus to its toggle. The focused Playwright browser regression passed. The marketing-site menu also opened/closed by keyboard
and restored focus; site tablists changed selection with arrow keys. Reduced-motion mode was used for the repeatable screenshot pass.

The final Impeccable detector run covered the ten listed site/app targets and returned 54 heuristic findings: 5 error-level motion
matches, 46 warnings and 3 advisories. The motion matches include the app's actual connected, connecting and reconnecting states;
the live connection label is backed by the health poll and the reconnecting indicator reflects an active retry. The site also has
decorative pulsing dots and the `DEMO` text now makes the illustrated badge's meaning explicit. Other recurring matches concern
the incumbent site's section labels, accents, gradients/glows and small text. These are scan candidates, not 54 verified defects;
the complete machine-readable output is in
[`impeccable-detect.json`](artifacts/visual-validation/impeccable-detect.json). No automated contrast calculation or screen-reader
audit was performed.

These are local UI checks, not a screen-reader certification, physical phone test, or test of a real supervised browser session.
Playwright used desktop Firefox at phone/tablet viewport sizes; it did not emulate touch input. Provider, Pi, local-model, portal
and physical-device workflows remain separate verification gaps in [the continuation ledger](ledger.md).
