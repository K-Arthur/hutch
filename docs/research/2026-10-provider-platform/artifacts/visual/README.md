# Visual validation captures (2026-10-30)

Real Hutch application and real static site, captured with Playwright Chromium from branch
provider-platform. The app ran against an isolated state directory; the website was served over HTTP.

- app-<surface>-<width>x<height>.png: full-page app captures at 1440x960, 1280x720, 900x1024,
  390x844 and 320x740 for /providers, /models and /legacy/connections.
- site-providers-<width>x<height>.png: the marketing #providers section at the same five viewports.
- review/: viewport-sized and scrolled review copies (accounts, catalogue, filters, local inference,
  runtime boundaries, route readiness, collapsed and expanded website section, 200 percent text reflow).
- capture-results.json: HTTP status, horizontal-overflow checks, 200 percent text reflow checks and
  console error/warning collection (zero console errors in the accepted run).
- server.log / site-server.log: the servers used for the run.

Boundary: no provider credential existed, so no authenticated provider state is shown. Accounts render
their real needs-authentication state. No screenshot was synthesised or edited beyond viewport cropping
by Playwright. No vendor partnership or endorsement is implied by any provider name.
