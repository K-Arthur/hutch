# Slice 7C Verification Report

Slice: 7C - Hutch Colony 8-resident avatars + 5-state motion, dashboard brand assets, server header lockup
Pipeline: Run 7, Slice 7C (code-complete verification)
Verification date: 2026-10-29 (America/Vancouver, PDT)
Verifier: verifier (independent teammate; no product source, test, or desktop-icon writes)
Shared task: task-4
Repo HEAD at verification: 135d8038 docs(brand): complete Run 6 Visor Hutch mark, guidelines, and asset package (2026-10-29 01:52:13 -0700)
Working tree: heavily dirty from a concurrent unrelated session (68 modified, 1 deleted, 82 untracked); see Known-unrelated issues. Slice-7C writes are app.js, studio.css, brand.css (new), static/index.html, templates/base.html and new static icon/manifest/font assets, all with mtime 2026-10-29 03:01-03:02.

## Verdict

PASS (after two verification-found, slice-caused defects were fixed by the Lead before final sign-off).

- Independent browser/asset capture: 65 of 65 checks pass against the final tree (54 of 55 before Lead follow-up fix 1; 55 of 55 between fix 1 and fix 2; the ten checks added for fix 2 cover lockup geometry and content-hashed brand.css refs on both dashboard heads).
- Focused automated checks: all green. tests/test_site_tokens.py 8 passed; avatar eye e2e 1 passed (rerun after fix 1: 17.03s; rerun after fix 2: 18.89s); shared-token e2e 1 passed (rerun after fix 1: 23.89s; rerun after fix 2: 26.84s); roster e2e 1 passed; emoji audit clean.
- Whole-file tests/e2e/test_design_system.py: 1 failed, 18 passed post-fix (run 3); the single deterministic failure (persona live preview button 40px < 44px) is known-unrelated, caused by the concurrent session's form-migration CSS, not Slice 7C. The one first-run answer-feedback timeout did not reproduce.
- Context hygiene: the only violation is the known pre-existing tests/test_commit_attribution.py 419-line file from another session; Slice 7C files are within their frozen line caps.
- Two Lead follow-up fixes were applied after the initial verification pass and both were independently re-verified: SLICE-7C-F1 (SPA wordmark font cascade) and SLICE-7C-F2 (lockup geometry 22px mark + 8px gap + 18px wordmark plus content-hashed brand.css refs).
- Known-unrelated issues are listed at the end.

## Environment

| Item | Value |
|---|---|
| OS | Linux |
| Python | 3.13.15 (.venv) |
| pytest | 9.1.1 |
| Playwright | 1.63.0 |
| Chromium | Chromium 153.0.8010.12 (Playwright bundled revision chromium-1243, /home/kevina/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome) |
| uvicorn | 0.54.0 |
| uv | 0.13.6 |
| Browser launch | playwright.chromium.launch() default bundled build; no HUTCH_TEST_CHROMIUM_EXECUTABLE override |
| Capture viewport | 1440x960, reduced_motion="reduce" |
| Test artifact root | .pipeline/brand/2026-10/evidence/slice-7c/verification/artifacts |
| uv cache | /tmp/hutch-uv-cache (the command sandbox gives each bash call an ephemeral /tmp, so all evidence logs are written under the verification directory instead) |

Focused tests were run with the prescribed command form:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line <targets>

The independent capture script was run with the venv interpreter:
    .venv/bin/python .pipeline/brand/2026-10/evidence/slice-7c/verification/capture_slice_7c.py

## Command log and exact results

### 1. Shared site tokens

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py

Exact output:
    ........                                                                 [100%]
    8 passed in 1.12s

Exit code 0. Includes the guard that src/hutch/server/static/brand-tokens.css must be byte-identical to website/tokens.css.

### 2. Context-hygiene drift guard

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_context_hygiene.py

Exact output:
    ...........F                                                             [100%]
    1 failed, 11 passed in 0.63s

Failure:
    tests/test_context_hygiene.py:194: AssertionError: assert ['new source ...s); split it'] == []
    Left contains one more item: 'new source file over 400 lines: tests/test_commit_attribution.py (419 lines); split it'

Attribution: known-unrelated. tests/test_commit_attribution.py is committed at bee491d5 (2026-10-28 14:39:50 -0700) from another session and is not touched by Slice 7C.

### 3a. Context-hygiene inventory report

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync python scripts/audit_context_hygiene.py --report

Exact output (first lines):
    Context hygiene report: 637 source files scanned; 118 over 400 lines; 117 frozen in .file-size-baseline.json.
    Policy findings (1):
      new source file over 400 lines: tests/test_commit_attribution.py (419 lines); split it
    Top offenders:
       14262  src/hutch/server/static/app.js
       13265  tests/e2e/test_browser.py
       12624  src/hutch/store.py
        7461  src/hutch/server/app.py
        3334  tests/e2e/test_design_system.py

Exit code 0 (--report mode is advisory).

Slice file sizes against the frozen baseline:

| File | Lines | Cap / status |
|---|---|---|
| src/hutch/server/static/app.js | 14262 | cap 14532 (frozen baseline), within |
| src/hutch/server/static/studio.css | 1016 | cap 1115 (frozen baseline), within |
| src/hutch/server/static/brand.css | 14 | new small file, no cap |
| src/hutch/server/static/index.html | 188 | below 400; not in frozen baseline |
| src/hutch/server/static/brand-tokens.css | 120 | byte-identical to website/tokens.css |

Byte-identity evidence (sha256):
    7e5b0d00fb6ed8c46e3e50e6ce8c48a878a31902fb57445f988ff823305c4a86  src/hutch/server/static/brand-tokens.css
    7e5b0d00fb6ed8c46e3e50e6ce8c48a878a31902fb57445f988ff823305c4a86  website/tokens.css

### 3b. Context-hygiene policy gate

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync python scripts/audit_context_hygiene.py

Exact output:
    Context hygiene violations (1):
      new source file over 400 lines: tests/test_commit_attribution.py (419 lines); split it

Exit code 1. The single violation is the known-unrelated committed file above; no Slice 7C file appears in the report.

### 4. No-emoji audit

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync python scripts/audit_emoji.py

Exact output:
    audit:emoji - clean (scanned 2901 files, 10 waiver(s)).

Exit code 0.

### 5. Focused avatar e2e (authoritative slice check)

Test: tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette
It asserts 8 distinct silhouette colors, two #0b1511 ink oval eyes per head, 48-point Path2D containment of every eye contour inside its own head, balanced/mirrored eye tilt, distinct eye geometry for all 8, at least 6 distinct face rows, 44px shape and colour controls, picker/live-preview parity, two-row picker at phone and compact-phone widths, no overflow, minimum eye contrast >= 3, no page errors.

Command (HUTCH_TEST_ARTIFACTS_DIR = verification/artifacts):
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette

Exact output:
    .                                                                        [100%]
    1 passed in 12.02s

Exit code 0. The test's own validation.json reports: browser Chromium 153.0.8010.12, silhouettes 8, colours 8, minimum_eye_contrast 5.95, page_errors [], provider_calls 0.

Post-fix rerun (after the index.html stylesheet-order fix):
    1 passed in 17.03s
Log: postfix-rerun-avatar-e2e.log

### 6. Shared-token e2e

Test: tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces
It asserts #workspace .brand-name text is exactly "hutch" on both Studio and Connections, shared token values across Studio/Connections/marketing, button/panel/type tokens, 200% text scaling, 320px reflow, no overflow, no page errors, no external requests.

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces

Exact output:
    .                                                                        [100%]
    1 passed in 15.60s

Exit code 0. Its validation.json reports external_requests [] and provider_calls 0.

Post-fix rerun:
    1 passed in 23.89s
Log: postfix-rerun-shared-token-e2e.log

### 7. Whole-file tests/e2e/test_design_system.py

Command (background job; artifacts root = verification/artifacts):
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py

Run 1 (pre-fix, overlapped with the verifier's first Chromium capture for part of its runtime):
    2 failed, 17 passed in 204.48s
Run 2 (pre-fix, run alone; --tb=short):
    1 failed, 18 passed in 213.86s
Run 3 (post-fix, run alone; --tb=short):
    1 failed, 18 passed in 245.23s

Failures and attribution:

1) tests/e2e/test_design_system.py::test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive
   Assertion: tests/e2e/test_design_system.py:2514
       assert button.evaluate("el => Math.round(el.getBoundingClientRect().height)") >= 44
       AssertionError: assert 40 >= 44
       element: #persona-form-slot .persona-form >> .persona-live-preview >> [data-persona-preview-run]
   Reproduced in isolation: 1 failed in 5.12s (rerun-persona-preview.log); fails in all three whole-file runs.
   Attribution: known-unrelated, concurrent session. The dirty tree's persona.js replaces the HEAD div.btn-row with div.hutch-actions (git diff persona.js adds the wrapper). The new untracked hutch-form-controls.css:196-197 sets ".hutch-actions .btn { min-height: var(--hutch-form-height-button); }" which resolves to 40px via hutch-forms.css:93 (--hutch-size-control-lg, 40px) and wins over the pre-existing style.css:2574 ".persona-live-preview button { min-height: 44px; }". The concurrent CSS/JS files have mtime 2026-10-28 14:56-16:30, i.e. before the Slice 7C writes at 2026-10-29 03:01-03:02, and none are in the Slice 7C write scope.

2) tests/e2e/test_design_system.py::test_answer_feedback_stays_local_revisioned_and_accessible (run 1 only)
   Assertion: 30s wait_for_page predicate timeout waiting for two answer-feedback rating controls with the expected data-feedback-revision and aria-disabled != "true".
   Did NOT reproduce: 1 passed in 9.38s in isolation (rerun-answer-feedback.log) and passed in whole-file runs 2 and 3.
   Attribution: sequence/load flake, not Slice 7C.

### 8. Roster identity e2e

Test: tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct
It asserts name-derived roster avatars remain distinguishable, exactly two ink eyes, no glints/outlines/masks, and compact face span <= 16.

Command:
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct

Exact output:
    .                                                                        [100%]
    1 passed in 12.41s

Exit code 0. Log: roster-mascot-e2e.log

### 13. Extended independent capture after Lead follow-up fix 2 (lockup geometry)

Command:
    .venv/bin/python .pipeline/brand/2026-10/evidence/slice-7c/verification/capture_slice_7c.py

Exact output (tail):
    checks passed: 65, failed: 0
    results: .../capture-results.json

Exit code 0. The ten new checks added for SLICE-7C-F2 verify: source brand.css content-hash 581315bf; index.html and base.html both reference /static/brand.css?v=581315bf; SPA computed gap 8px and measured mark-to-wordmark gap 8px; SPA wordmark font-size 18px and tracking -0.54px; server-page computed gap 8px and measured gap 8px; server wordmark font-size 18px and tracking -0.54px; both pages load content-hashed brand.css v=581315bf and are served bytes whose sha256 starts 581315bf.

Focused e2e reruns after follow-up fix 2:

| Test | Result |
|---|---|
| tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces | 1 passed in 26.84s |
| tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette | 1 passed in 18.89s |

Logs: followup-rerun-shared-token-e2e.log and followup-rerun-avatar-e2e.log. No whole-file design-system rerun was performed for fix 2 (Lead instruction); the known-unrelated persona failure stands.

## Slice-caused defect found by verification and fixed before sign-off

ID: SLICE-7C-F1 (acceptance-criterion failure, now fixed)

Symptom (pre-fix): the SPA dashboard wordmark did not render in Bricolage Grotesque.
Measured at 1440x960 in Chromium 153.0.8010.12 on "/":

    document.querySelector("#workspace .brand-wordmark")
      computed font-family: Geist, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif
      computed font-weight: 650
      computed font-size: 18px
    document.fonts.check('800 16px "Bricolage Grotesque"') before forcing a load: false

Root cause: src/hutch/server/static/index.html gave the wordmark span class="brand-name brand-wordmark". brand.css .brand-wordmark set the Bricolage family, but brand.css was loaded at index.html line 18 BEFORE studio.css at line 27. The pre-existing studio.css:376 rule ".brand-name { font: 650 var(--fs-lg)/1 var(--font-ui); letter-spacing: -0.035em; }" is an equal-specificity font shorthand that won by later cascade order and reset font-family to Geist. HEAD index.html had class="brand-name" only and there was no brand.css, so the suppression of the new Bricolage rule was introduced by this slice's dashboard wiring. Server-rendered pages were correct because base.html's span has only class="brand-wordmark" and brand.css loads after hutch.css there.

Lead fix applied 2026-10-29 (after receiving the verifier's failure report): in src/hutch/server/static/index.html the brand.css link was removed from after style.css and re-inserted as the last stylesheet in <head> (now line 41, after /static/hutch-messages.css) with a comment explaining that the lockup sheet must win over surface font shorthands. brand.css content was not modified (sha256 3b517691f9a68d41fce5608a2640e45fc1e44280ed836ffa5cae3900276a19dc; sha8 3b517691 matches the existing query string), so no asset hash references changed. index.html is 188 lines, below the 400-line context-hygiene cap and not part of the frozen .file-size-baseline.json.

Post-fix verification of the same check (same script, same fixture):

    #workspace .brand-wordmark
      computed font-family: "Bricolage Grotesque", Geist, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif, ui-sans-serif, system-ui, sans-serif
      computed font-weight: 800
      computed font-size: 18px
      computed letter-spacing: -0.54px
    document.fonts.check('800 16px "Bricolage Grotesque"') before forcing a load: true
    Bricolage Grotesque 800 face status: loaded
    Bricolage WOFF2 is fetched by the SPA naturally (no forced load needed)

Re-run results after fix 1: capture script 55 of 55 checks passed (exit 0); post-fix focused avatar e2e 1 passed in 17.03s; post-fix shared-token e2e 1 passed in 23.89s; post-fix whole-file e2e 1 failed (known-unrelated persona button) and 18 passed.

## Second Lead follow-up fix (SLICE-7C-F2): lockup geometry

After the first report was delivered, the Lead aligned both dashboard lockups to BRAND-GUIDELINES.md 3.2 and docs/brand-assets.md line 53: 22px Small-tier mark + 8px gap + 18px wordmark for the Studio sidebar and the Jinja header.

Before fix 2 (recorded as a non-blocking observation in the first report):
- SPA sidebar: 22px mark, 12px gap, 18px wordmark.
- Server topbar: 22px mark, 12px gap, 16px wordmark.
- The 18px/16px difference came from the wordmark inheriting .brand font-size; no wordmark font-size was declared.

Fix applied by the Lead 2026-10-29: src/hutch/server/static/brand.css is now 19 lines and adds

    .ws-brand .brand, .topbar .brand { gap: 8px; }
    .brand-wordmark { ... font-size: 18px; }

with @font-face, family, weight 800 and -0.03em tracking unchanged. New brand.css sha256 is 581315bfbabe6649da7ba92e12557e51ec517e775d3125340d6e5cb829e9475f (sha8 581315bf). The stylesheet references in src/hutch/server/static/index.html line 41 and src/hutch/server/templates/base.html line 16 were updated to /static/brand.css?v=581315bf. Line counts after the fix: index.html 188, base.html 71, brand.css 19; frozen-line budgets unaffected.

Independent post-fix measurements (same capture script, 1440x960 Chromium 153.0.8010.12):

| Surface | Mark | CSS gap | Measured gap | Wordmark size | Family / weight / tracking | brand.css ref and served sha256 |
|---|---|---|---|---|---|---|
| SPA #workspace .brand | 22x22 CSS px | 8px | 8px | 18px | Bricolage Grotesque / 800 / -0.54px | v=581315bf; served sha256 581315bf... |
| server .topbar .brand | 22x22 CSS px | 8px | 8px | 18px | Bricolage Grotesque / 800 / -0.54px | v=581315bf; served sha256 581315bf... |

document.fonts.check('800 16px "Bricolage Grotesque"') is true before any forced load on both surfaces; no page errors, no console errors, no failed responses, no non-localhost requests. The regenerated close-ups visually confirm a tighter tooled lockup and no layout breakage.

Post-fix focused reruns after fix 2: shared-token e2e 1 passed in 26.84s; avatar e2e 1 passed in 18.89s. The whole-file design-system suite was not rerun for fix 2 (Lead instruction); the known-unrelated persona-button failure stands.

## Independent browser and asset capture

Script: .pipeline/brand/2026-10/evidence/slice-7c/verification/capture_slice_7c.py
Full machine-readable results: .pipeline/brand/2026-10/evidence/slice-7c/verification/capture-results.json

Fixture recipe replicated from tests/e2e/test_design_system.py app_server fixture: fresh HUTCH_STATE_DIR under a temp dir, HUTCH_MAX_CONCURRENT=2, HUTCH_TESTING=1, HUTCH_SANDBOX=off, create_app(), one Bot(name="design-system-review", display_name="Design Partner", model="mock/demo", tools=[]), uvicorn.Server on 127.0.0.1 port 0, wait until started, then Playwright Chromium context 1440x960 reduced_motion="reduce".

Result (after Lead follow-up 2): 65 checks passed, 0 failed, exit code 0.
Result (after Lead follow-up 1, before follow-up 2): 55 checks passed, 0 failed.
Result (initial, before any fix): 54 passed, 1 failed (the wordmark font cascade above).

### Dashboard icon and manifest links on "/"

Five links found in head: three rel="icon", one rel="apple-touch-icon", one rel="manifest".

| rel | href | HTTP status | content-type | bytes | notes |
|---|---|---|---|---|---|
| icon | /static/favicon.svg?v=cada88dd | 200 | image/svg+xml | 1054 | same-origin |
| icon | /static/favicon-32x32.png?v=2d2d3d2c | 200 | image/png | 1124 | PNG 32x32 |
| icon | /static/favicon.ico?v=9096fd72 | 200 | image/vnd.microsoft.icon | 3537 | ICO magic 00 00 01 00 |
| apple-touch-icon | /static/apple-touch-icon.png?v=2351b1e0 | 200 | image/png | 3978 | PNG 180x180 |
| manifest | /static/site.webmanifest?v=187682d3 | 200 | application/manifest+json | 1064 | JSON parses |

All five are same-origin and return HTTP 200 with a content type appropriate to the asset (ICO served as image/vnd.microsoft.icon is accepted).

### Web app manifest icons

The manifest (name "Hutch", short_name "Hutch", start_url "/", display "standalone", theme #09090b) declares six PNG icons. Each resolved icon URL was fetched and its PNG IHDR dimensions decoded:

| src | declared sizes | purpose | HTTP | content-type | decoded PNG |
|---|---|---|---|---|---|
| icons/icon-192.png | 192x192 | any | 200 | image/png | 192x192 |
| icons/icon-512.png | 512x512 | any | 200 | image/png | 512x512 |
| icons/icon-192-maskable.png | 192x192 | maskable | 200 | image/png | 192x192 |
| icons/icon-512-maskable.png | 512x512 | maskable | 200 | image/png | 512x512 |
| icons/icon-192-monochrome.png | 192x192 | monochrome | 200 | image/png | 192x192 |
| icons/icon-512-monochrome.png | 512x512 | monochrome | 200 | image/png | 512x512 |

All six return HTTP 200, image/png, and match their declared dimensions.

### Fonts

- Bricolage Grotesque availability check: document.fonts.check('800 16px "Bricolage Grotesque"') is true post-fix (and was true only after a forced document.fonts.load() pre-fix).
- Declared face: family "Bricolage Grotesque", weight 800, status loaded; served locally from /static/fonts/bricolage-grotesque-latin-800.woff2; no remote font request.
- SPA wordmark computed family leads with "Bricolage Grotesque" at weight 800, size 18px, letter-spacing -0.54px.
- Server-page wordmark computed family leads with "Bricolage Grotesque" at weight 800, size 18px, letter-spacing -0.54px (16px before Lead follow-up fix 2).

### Inline Visor Hutch marks (single Small-tier path)

Both marks were compared character-for-character against the production Small-tier path (.pipeline/brand/2026-10/assets/production/svg/hutch-mark-small.svg / src/hutch/server/static/favicon.svg, 32x32 grid).

SPA "#workspace .brand" (index.html:51):
- exactly one SVG, viewBox "0 0 32 32"
- exactly one path: d equals the Small-tier path exactly
- fill "var(--brand)", fill-rule "evenodd"
- no circle elements, no stroke attributes anywhere in the SVG
- rendered size 22x22 CSS px; wordmark text "hutch"; computed gap 8px; measured mark-to-wordmark box gap 8px

Server-rendered ".topbar .brand" on /models (templates/base.html:42):
- exactly one SVG, width="22" height="22", viewBox "0 0 32 32"
- exactly one path: d equals the Small-tier path exactly
- fill "var(--accent)", fill-rule "evenodd"
- no circle elements, no stroke attributes
- rendered size 22x22 CSS px; wordmark text "hutch"; computed gap 8px; measured mark-to-wordmark box gap 8px

### Lockup geometry (BRAND-GUIDELINES.md 3.2)

After Lead follow-up fix 2, both dashboard heads implement the specified 22px Small-tier mark + 8px gap + 18px wordmark lockup. The capture script verifies this explicitly on both surfaces: mark bounding box 22x22 CSS px, computed CSS gap "8px", measured horizontal box gap between mark and wordmark 8px, wordmark computed font-size 18px, family Bricolage Grotesque at weight 800 with -0.54px tracking, and document fonts loaded. It also verifies that both rendered heads reference /static/brand.css?v=581315bf and that the served stylesheet bytes hash to sha256 581315bf..., matching the file on disk (19 lines).

### Server-rendered page from templates/base.html

- GET /models returned HTTP 200 with no redirect (candidates /models, /usage, /login were tried in that order; /models passed on the first attempt).
- .topbar present and .brand present; mark and wordmark checks above all pass.
- All 22 Slice 7C checks in the capture script plus network checks pass on this page.

### Network integrity (both pages)

| Signal | Count |
|---|---|
| pageerror events | 0 |
| console errors | 0 |
| responses with status >= 400 | 0 |
| failed requests | 0 |
| non-localhost requests | 0 |

No remote font, icon, or analytics requests were observed; both pages are fully local.

## Screenshot evidence and visual observations

All captures were inspected with the image-reading tool, not just listed by filename. Paths are relative to .pipeline/brand/2026-10/evidence/slice-7c/verification/.

| Screenshot | Size | Observation |
|---|---|---|
| spa-desktop.png | 1440x960 | SPA "/" at desktop: sidebar lockup top-left (22px emerald Small-tier mark + "hutch" wordmark), search/dock controls, nav, roster, chat empty state and composer. No layout breakage or horizontal overflow. Wordmark renders in Bricolage 800 post-fix. |
| spa-brand-closeup.png | 78x22 (after fix 2; 82x22 after fix 1; 83x22 initially) | SPA sidebar lockup: mark + wordmark with the specified 8px gap. Wordmark is Bricolage Grotesque 800 at 18px with -0.03em tracking; after fix 2 the element is slightly narrower (8px gap instead of 12px). |
| server-page-topbar.png | 1440x54 | /models topbar: 22px mark + "hutch" wordmark, primary nav (Chats, Activity, Assistants, Work history, Needs you, Models active, Usage, Apps and AI), Stop all and live status. Even 54px bar, no clipping. |
| server-page-brand.png | 78x29 | Close-up of the server topbar brand after fix 2: emerald Small-tier mark + "hutch" in Bricolage Grotesque 800 at 18px (16px before fix 2), 8px gap. |
| server-page-full.png | 1440x3369 (full page) | Full /models page: topbar, runtime/connection notes, model tables, hosted-price table, footer "hutch 0.10.0 local-first...". No layout breakage. |
| artifacts/mascot-eye-review-2026-10-10/desktop.png | 1440x960 | Studio roster with Design Partner plus mascot-0..mascot-7. The eight colony silhouettes are distinct and readable at roster size (ghost/orb, gable house, hare/bean, lantern cowl/drop, round pod, shield/keep, beacon spire/triangle, hex chassis), each with two dark eyes inside the head. No layout breakage. |
| artifacts/mascot-eye-review-2026-10-10/shape-picker-desktop.png | 736x414 | "Look and feel" picker: large selected preview (green ghost with fitted eyes), eight colour swatches with a clear selected ring, eight 44px shape buttons each showing its own silhouette and its own eye geometry, Surprise me action, honest helper note. Preview parity and 44px targets are visible. |
| artifacts/mascot-eye-review-2026-10-10/face-orb.png | 128x129 | Ghost bell silhouette; two balanced dark oval eyes fully inside the head; no glints, outlines or masks. |
| artifacts/mascot-eye-review-2026-10-10/face-drop.png | 128x129 | Lantern cowl silhouette with pointed crown and arch base; two oval eyes inside the body. |
| artifacts/mascot-eye-review-2026-10-10/face-hex.png | 128x129 | Hex chassis silhouette; two oval eyes inside the usable face area. |
| artifacts/mascot-eye-review-2026-10-10/face-triangle.png | 128x129 | Beacon spire silhouette; two oval eyes below the neck, inside the body. |
| artifacts/mascot-eye-review-2026-10-10/phone-roster.png | 390x844 | Phone-width roster overlay: mark and wordmark, nav, search and the colony list; no horizontal overflow and readable silhouettes. |

Additional capture artifacts from the test runs: artifacts/mascot-eye-review-2026-10-10/validation.json (silhouettes 8, colours 8, minimum eye contrast 5.95, page errors none), shape-picker-tablet/phone/compact-phone.png, phone-studio.png, trace.zip; artifacts/design-system/studio-*.png, connections-*.png, marketing-*.png and validation.json (external_requests [], provider_calls 0).

## Non-blocking observations

1. Lockup geometry drift versus docs/brand-assets.md (server 22px mark + 12px gap + 16px wordmark; SPA 12px gap) was recorded as a non-blocking observation in the first report. The Lead resolved it after sign-off with SLICE-7C-F2 and the fix was independently re-verified: both surfaces now measure 22px mark + 8px gap + 18px Bricolage Grotesque 800 wordmark with content-hashed brand.css v=581315bf.
2. The capture script deliberately calls document.fonts.load() to assert font availability. Pre-fix this is why the Bricolage WOFF2 appeared in the SPA network log despite the wordmark not using it; the authoritative pre-fix signals were document.fonts.check() false before that call and the Geist computed family.
3. Pre-fix whole-file run 1 overlapped with the verifier's first Chromium capture for part of its runtime; runs 2 and 3 ran alone. The answer-feedback timeout appeared only in run 1.

## Known-unrelated issues

1. Context-hygiene violation: tests/test_commit_attribution.py (419 lines) over the 400-line cap. Committed at bee491d5 (2026-10-28 14:39:50 -0700), not touched by Slice 7C. Confirmed by both tests/test_context_hygiene.py and scripts/audit_context_hygiene.py.
2. Persona live preview run button is 40px high instead of the 44px asserted at tests/e2e/test_design_system.py:2514. Caused by the concurrent session's form migration: persona.js in the dirty tree wraps buttons in div.hutch-actions, and the new untracked hutch-form-controls.css:196-197 sets .hutch-actions .btn min-height to 40px, which wins over the pre-existing style.css:2574 .persona-live-preview button 44px rule. Concurrent files are dated 2026-10-28, before the Slice 7C writes. Fails deterministically in isolation and in all three whole-file runs; not caused by Slice 7C.
3. tests/e2e/test_design_system.py::test_answer_feedback_stays_local_revisioned_and_accessible timed out once in whole-file run 1 and passed in isolation and in runs 2 and 3. Sequence/load flake, not Slice 7C.
4. The working tree is heavily dirty from a concurrent unrelated session (68 modified, 1 deleted, 82 untracked entries), including a large hutch-msg CSS/JS refactor and the form-system migration (hutch-forms.css, hutch-form-controls.css, hutch-select.css, hutch-messages.css, persona.js). None of those changes were interpreted as Slice 7C failures; attribution above is by file, rule, specificity and mtime.

## Evidence file index

- VERIFICATION.md (this file)
- verification-report.json (machine-readable report)
- capture_slice_7c.py (independent capture script, re-runnable)
- capture-results.json (65 passed, 0 failed after Lead follow-up 2; 55/0 after follow-up 1; 54/1 initially; includes all check names, asset HTTP table, manifest icon table, fonts, lockup geometry, content-hashed brand.css contract, network events, screenshots)
- whole-file-design-system-e2e-postfix-run3.log (1 failed known-unrelated, 18 passed, 245.23s)
- whole-file-design-system-e2e-run2.log (1 failed known-unrelated, 18 passed, 213.86s)
- postfix-rerun-avatar-e2e.log (1 passed, 17.03s)
- postfix-rerun-shared-token-e2e.log (1 passed, 23.89s)
- followup-rerun-avatar-e2e.log (1 passed, 18.89s)
- followup-rerun-shared-token-e2e.log (1 passed, 26.84s)
- rerun-persona-preview.log (1 failed known-unrelated, 5.12s)
- rerun-answer-feedback.log (1 passed, 9.38s)
- roster-mascot-e2e.log (1 passed, 12.41s)
- screenshots listed above at the verification directory root
- artifacts/ (test-generated screenshots, traces and validation.json files; 230 files)

Note: whole-file run 1's full log lived in the bash sandbox ephemeral /tmp and is not retained; its exact summary (2 failed, 17 passed in 204.48s) and both failure lines are reproduced in this report and in verification-report.json.

## Reproduction

    cd /home/kevina/CodingProjects/hutch
    export HUTCH_TEST_ARTIFACTS_DIR="$PWD/.pipeline/brand/2026-10/evidence/slice-7c/verification/artifacts"
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_site_tokens.py
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_context_hygiene.py
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync python scripts/audit_context_hygiene.py --report
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync python scripts/audit_emoji.py
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces
    UV_CACHE_DIR=/tmp/hutch-uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=line tests/e2e/test_design_system.py
    .venv/bin/python .pipeline/brand/2026-10/evidence/slice-7c/verification/capture_slice_7c.py
