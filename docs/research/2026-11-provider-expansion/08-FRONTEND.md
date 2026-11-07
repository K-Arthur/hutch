# Phase 7: frontend (2026-11-06)

Scope: catalogue filters, provider detail with a per-route setup wizard, account list with readiness, a route
picker that shows the resolved tuple, a media/speech/search section, and one voice for "what was found, what is
saved" on first run and Models. Decision record: ADR-0037. Evidence: `docs/realignment/artifacts/provider-expansion-2026-11/phase7/`.

## Sources read (accessed 2026-11-06) and what each changed

| Source | What it said | What it changed here |
|---|---|---|
| https://docs.openwebui.com/troubleshooting/connection-error/ | The Verify Connection button calls the provider's `/models` and reports success; an empty model list after a green check is a recurring report. | The wizard's test step says it asks the model list endpoint and that an answering list is reachability evidence, not proof a model runs. No "connected" badge is printed anywhere. |
| https://github.com/danny-avila/LibreChat/issues/16155 | Models were not listed behind a reverse proxy until the user typed in the search box. | The picker takes a typed model id and does not depend on a discovered list being complete. |
| https://github.com/edenai/docs/pull/186 | Open WebUI's per-feature settings (embeddings, speech to text, images) sent requests to the default host with an empty key. | A vendor template cannot be re-pointed from the wizard (only custom endpoints take a base URL), and media-only vendors state the environment variable and the word "ambient" instead of silently reusing a key. |
| https://github.com/LibreChat-AI/LibreChat/discussions/10193 | An Azure `baseURL` ending in `/v1` produced a mangled final URL and changed behavior with a toggle. | Custom endpoints get an explicit Base URL field with a placeholder and a "required" mark when the template ships only a scheme. Address policy stays in ADR-0034. |
| https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/ | Ollama ignores the key but the field must be non-empty. | Reinforces the existing "not key-verified" wording for custom endpoints; no new claim was added. |
| https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | SC 2.5.8: pointer targets are at least 24 by 24 CSS px unless the spacing exception applies. | Provider-name links have `min-height: 24px`; coarse-pointer controls are 44px. |
| https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/ | A disclosure button toggles on Enter and Space and exposes `aria-expanded`. | Native `details/summary` is used everywhere; no custom disclosure was built. |
| https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA22 | `role="status"` announces a result count after a filter or search. | The filter count and the route-picker result are always-rendered status regions whose text changes. |

## Failure classes (UI-facing) and how each was classed

| Complaint | Class | Response |
|---|---|---|
| A green "connected" next to an empty or unusable model list | fixable | Nothing says connected. The test step and chips say what was actually checked. |
| A setting that quietly uses another host or key | fixable | Wizard cannot override a vendor host; ambient keys are labeled; the picker names the account source. |
| Not knowing which account pays before the first send | fixable | Route picker and the resolved route under each saved route on Models. |
| One account picked for you when several exist | fixable | The picker reports "not chosen: N named account(s)"; it never resolves to the only one. |
| Setup forms that offer something that cannot work | fixable | A route Hutch has not built, or the provider blocks, gets one honest step and no form. |
| A form that can mint a sign-in account | found by review | Refused with a pointer to Apps & AI (it also used to return a 500). |
| Vendor-side quota and billing ambiguity | vendor-side | Out of scope for a page; the media section states "cost unknown" instead of guessing. |

## Design as built

- **Index, not a wall.** One row per provider (`providers/catalog_view.py`), filters for search, category, status,
  sign-in route and service held in the query string. The form is hidden until the script runs, so without script the
  full list is shown and nothing claims to filter. A route chip says built or not built and is never the green of a
  live-verified provider; only the provider's own status chip can be green.
- **Detail page and wizard.** `providers/wizard.py` derives ordered steps from the catalogue, the connection
  templates, the account book, loopback probes and the runtime registry. `server/pages_provider_detail.py` holds
  the four actions (add, key, terms, test), each refusing an account that does not belong to the provider.
- **Route picker.** A plain GET form; `provider-picker.js` fetches the same page and swaps the result element, so
  labels live in one place. It adds an inference-mode check using the runtime's own validator.
- **Media section.** `media/view.py` reads the route table, the dated price rows, the job ledger and the connection
  templates' declared search routes. Jobs can be checked or cancelled in place; cancel takes a second click.
- **One sentence.** `starter-route.js` now owns "OpenCode is available with N model options ... None is saved as the
  default for new assistants yet." First run and Models both call it; `app.js` shrank by four lines.
- **G16 (dark-only).** The workspace stays dark-only. Building a light theme is a product choice larger than this
  phase, so the workspace gate is dark at four widths and the light/dark gate stays with the marketing site.

## Results (real stack, 2026-11-06)

`docs/realignment/capture_provider_ui.py` starts a real `hutch serve` on a real port against an isolated populated
state and drives it with Playwright Chromium (CSP enforced; only the axe context bypasses it). Final run: 49 checks,
40 pages, 0 failures; per page zero console errors, zero failed requests, zero horizontal overflow, no credential in
any page; 360, 768, 1280 and 1920 px.

- Providers page height, baseline to now (media section included): 25,471 to 14,513 px at 360; 14,350 to 10,174 at 768;
  13,279 to 8,011 at 1280; 11,472 to 7,828 at 1920.
- Filters equal the JSON API's counts; state survives a reload; an unknown query value is ignored.
- Keyboard traversal reaches the filter fields, the wizard forms, the picker and the job controls in reading order
  with a visible focus ring. Reduced motion: no running animation on the index or a detail page.
- axe-core 4.13.0 (read from another checkout on this machine; not a Hutch dependency): no violation of any impact on
  `/providers`, `/providers/deepseek`, `/providers/openai`, `/providers/alibaba-model-studio`, `/models` and the
  media section opened.
- Wizard: add, store key (owner-only file), test against a loopback stand-in server (`/v1/models`, request seen with
  a credential), key never rendered. Media: two real jobs submitted through the job service against the Phase 6
  stand-in; check while pending, check until finished, served bytes equal the stand-in's, an unconfirmable cancel
  ends "cancel not confirmed". Strict Offline: a hosted route is refused with the policy's reason; a loopback route is
  allowed and not called working. These prove Hutch's UI, API and ledger; they say nothing about any vendor.
- Tests added: 73 (70 in new files, 3 in `test_starter_route_js`) across `test_provider_catalog_view`, `test_provider_index_page`,
  `test_provider_wizard`, `test_provider_detail_page`, `test_provider_picker`, `test_media_view`,
  `test_providers_media_section`, `test_route_truth_surfaces`, `test_starter_route_js`; adjacent suites: 753 passed.
  Focused browser tests for first run and Models (`test_models_detected_route`, `test_starter_route`,
  `test_first_run_setup_check`): 23 passed. Mutations that made the matching tests fail: ownership check, vendor
  base URL override, any-template, no-dedupe, unverified-as-green, form visible, key done without a key, unbuilt route
  with forms, ack always, shared `Query`, trusted account, no Models tuple, actions on finished jobs, fabricated price,
  buttons always, mode always allowed, unguarded sign-in template, probe always.

## Defects found by running or reading, and fixed

1. Wizard form fields sat about 200px apart: the base `.hutch-form` is a column, so `flex: 1 1 220px` became a
   height. axe was green; the screenshot showed it.
2. Every provider page led with "No summary is recorded" (the catalogue has no summaries); removed.
3. A green "built" chip read as "works"; route chips are now neutral, amber (gated) or red (blocked/retired).
4. One shared `Query()` object bound all three picker parameters to the first name, so the model never arrived.
5. A crafted POST for the sign-in template raised `KeyError` and returned a 500 (review).
6. The test action did a network read on the event loop, and every detail page probed five loopback ports (review).
7. The evidence table broke "custom-compatible" one letter per line (`overflow-wrap: anywhere`); narrow-width rules
   sat above the base rules they override (CSS source order).
8. My first CSRF premise was wrong: job routes are guarded by the same-origin check, not a token. The script no longer
   sends a header the server does not use, and a test pins the real guard.
9. A truncated scratch file (process slip, not shipped) cost a rewrite of one CSS block.

## Environment note

`/tmp` on this machine is a 12 GB tmpfs and was 100% full (about 10 GB in `/tmp/pytest-of-kevina`) during this phase.
Nothing was deleted; scratch, pytest base temp and screenshots went to `~/.hutch-tmp/provider-phase7`.

## Not run, and why

- No light theme exists, so no light capture; no Tauri desktop run; only Chromium (not Firefox or WebKit).
- No screen reader session; axe covers a subset of WCAG and the keyboard checks cover the controls listed above, not
  every control on every page.
- The wizard's connection test was run against a loopback stand-in only, never a vendor. No credential was used for
  a paid or subscription route.
- First run was covered by its existing browser tests, not re-captured at four widths in this phase.
- Strict Offline here is the policy verdict in the picker. The process-level offline sandbox was not re-run.
- A stored-key form for the media-only vendors (fal, PixVerse, ElevenLabs, Deepgram) is still not built.
