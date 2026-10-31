# Onboarding 2026-10: decisions

| ID | Decision | Reason | Alternative rejected |
|---|---|---|---|
| D-01 | Keep the dedicated server-rendered `/onboarding/*` routes; no separate funnel and no product tour | Works without JavaScript, matches Home Assistant/Jellyfin pattern, already shipped | SPA wizard (would grow frozen `app.js`) |
| D-02 | Onboarding completion is derived from store facts, never a flag | Reinstalls, restores, other tabs and cleared storage must not hide or re-trigger setup | Browser-only flag |
| D-03 | "Verified" only from a generation. The probe is owner-triggered, one-shot, tool-free, disclosed as possibly using a small amount of credit. Metadata success is "saved, not tested". Residual gap: it bypasses governed-run usage reservation; recorded as a risk for maintainer sign-off | Honest readiness (C-01, C-05) with the least hidden spend | Hidden probe on save; or never verifying before first run |
| D-04 | Reuse slice 03/04 briefs as the contract (state tokens, routes, file names) | Already reviewed and approved | New vocabulary |
| D-05 | Readiness snapshots are process-local, never persisted | No provider text or secret in SQLite; restart forces revalidation | Persisting results |
| D-06 | Existing users: onboarding is offered, never imposed. If a route is verified or an assistant exists, `/onboarding` links onward and the empty-chat hand-off does not trigger | Never remove or hide existing configuration | Redirecting all users |
| D-07 | No fabricated trust, welcome-back banners, analytics, or mock demos on the website or in the app | `docs/marketing-site.md`, local-first model | Common SaaS onboarding patterns |
| D-08 | Baseline `check:agent` failure (F-09) is recorded, not fixed here | Unrelated to onboarding; the cap and map are another owner's policy | Raising the cap |
