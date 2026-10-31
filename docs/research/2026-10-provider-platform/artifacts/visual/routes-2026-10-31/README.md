# Provider route captures (2026-10-31)

Real Hutch application and the real static site, captured with Playwright Chromium.

- `app-providers-<w>x<h>.png`, `app-connections-<w>x<h>.png`: full-page app captures at 1440x960,
  1280x720, 900x1024, 390x844 and 320x740.
- `site-providers-<w>x<h>.png`: the marketing `#providers` panel, expanded, at the same five viewports.
- `review/`: viewport-sized copies (accounts and catalogue) for reading at native scale.
- `capture-results.json`: HTTP status, horizontal overflow, console error counts and the site-panel
  assertions for each viewport.
- `app-providers-zoom200-1280x720.png`, `site-zoom200-1280x720.png`: 200 percent text reflow.

State: four real connections (groq, cerebras, xai, minimax) created through the connection store with no
key, so every account truthfully renders needs-authentication. No authenticated provider state is shown
because no credential exists in this environment. No vendor partnership is implied by any name here.
