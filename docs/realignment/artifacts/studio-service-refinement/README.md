# Studio and Apps & AI refinement captures

Captured by `tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes` on 2026-10-10 with Chromium 153.0.8010.12 and Playwright 1.63.0. Each listed image was opened and inspected independently after the final CSS adjustment.

| Surface | Desktop | Tablet | Phone |
|---|---|---|---|
| Studio | [1440×960](studio-desktop.png) | [900×1024](studio-tablet.png) | [390×844](studio-phone.png) |
| Apps & AI | [1440×960](connections-desktop.png) | [900×1024](connections-tablet.png) | [390×844](connections-phone.png) |

The browser suite also checked all workspace routes and the marketing site at the three sizes above, plus a 320×740 compact-phone overflow pass. The focused route, gallery-refresh, and roster checks passed **3 tests in 23.02s**. No external requests or provider calls occurred; fixture assistants use `mock/demo` only in the test process.
