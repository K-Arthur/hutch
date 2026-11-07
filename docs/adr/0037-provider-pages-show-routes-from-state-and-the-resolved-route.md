# ADR-0037: Provider pages show routes from real state, and the resolved route before the first send

Status: accepted, 2026-11-06.

## Context

Phase 7 of the provider expansion built the frontend over what Phases 1 to 6 made true (research record
`docs/research/2026-11-provider-expansion/08-FRONTEND.md`). The baseline page was a 13,279 px wall of 62 cards that
repeated "Services, Auth, Protocols" under each name, had no route-level view, no setup path, no way to see who would
pay, and no media surface. First run and Models each composed their own "OpenCode is ready with N model options",
which read as saved beside "No default route". The workspace theme is dark-only by product decision.

## Decision

1. **The index lists routes, and a route is never "works".** One compact row per provider; the route chip says
   "built" or "not built" (the code path) and is never the green of a live-verified provider. Only the provider's own
   status chip can be green, and only for a dated live run. Filters (search, category, status, sign-in route,
   service) live in the query string and need script; without script the full list is shown and the form stays hidden.
2. **A setup wizard is derived from state, not scripted.** Each auth method gets steps computed from the catalogue,
   the connection templates, the account book, loopback probes and the runtime registry, so a page resumes where the
   person left off. A route Hutch has not built, or the provider blocks, gets one honest step and no form. The actions
   call ConnectionBook, return to the page, never echo a key, refuse an account that does not belong to the
   provider, and refuse sign-in templates (those start from Apps & AI). Only custom endpoints take a base URL here,
   so a key cannot be redirected from a form field.
3. **The resolved route is shown before anything is sent.** A picker takes an account, a model id, a runtime and an
   inference mode, and shows provider, account and its source, billing, runtime, protocol, endpoint and readiness from
   local settings only. Choosing no named account is reported as not chosen, never resolved to the only account. The
   mode check uses the runtime's own validator (`validate_inference_mode`), so Strict Offline refuses a hosted route
   in the policy's words. The same tuple appears under each saved route on Models. The picker is a plain GET form;
   script only swaps the result element from the server's own render, so labels live in one place.
4. **The media section reads data.** Routes, dated prices ("cost unknown" when there is none), jobs and built search
   routes come from the route table, price rows, the ledger and the connection templates. No route is called working.
   Jobs can be checked or cancelled in place; cancel takes a second click because a provider cannot take it back, and
   an unconfirmed cancel or a refusal is shown in its own words.
5. **One sentence for what was found.** `starter-route.js` owns "OpenCode is available with N model options ... None
   is saved as the default for new assistants yet." First run and Models both call it.
6. **The workspace stays dark-only (G16).** A light theme is a product decision larger than this phase. The
   workspace visual gate is dark at 360, 768, 1280 and 1920 px; the light/dark gate stays with the marketing site.
7. **New styles are a hand-written sheet** (`static/providers.css`), not a rebuild of the generated Tailwind output,
   so this phase touched no generated CSS and absorbed no other session's uncommitted CSS source.

## Consequences

- The Providers page is 8,011 px tall at 1280 (was 13,279) and 14,513 at 360 (was 25,471), media section included, and
  every provider has a page of its own to link to.
- The wizard cannot offer a stored-key form for media-only vendors (fal, PixVerse, ElevenLabs, Deepgram): they have no
  connection template (frozen `connections.py`), so the page names the environment variable and calls it ambient.
- The jobs panel is for the owner only (the job routes are not in the remote capability set).
- A new service tag or auth type must get a label or `test_provider_catalog_view` fails; a new job status must get
  wording or `test_media_view` fails.

## Alternatives considered

- **Filtering in Python and again in script.** Rejected: two implementations of one rule drift. The script is the one
  implementation; a real-browser check compares its result with the JSON API.
- **Rendering labels in script for the picker and the jobs list.** Rejected for the same reason; script fetches the
  server's HTML and swaps one element.
- **Reusing the legacy form handlers.** `pages.py` is a frozen over-cap file and its handlers redirect to the legacy
  page; the wizard has its own small module that calls the same ConnectionBook operations.
- **A light theme now.** Deferred; recorded as a product choice.
