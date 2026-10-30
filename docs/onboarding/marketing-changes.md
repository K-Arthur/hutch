# Marketing site changes for onboarding truthfulness

Date: 2026-10-29. Status: planning artifact for the onboarding/setup surface. This document changes no
production code; it is the only file written by task-2. It inventories the real static marketing site
(`website/`) against the onboarding reality the installed product delivers, and specifies exact
make-true/remove/disclose actions with binary acceptance criteria.

Evidence labels used below: **[repo]** = read in this checkout during this pass; **[primary]** /
**[external]** = external standards, vendor docs or design-system guidance inherited from
[research.md](research.md) section 7 and [marketing-boundary.md](notes/marketing-boundary.md) (I did not
re-fetch those URLs in this docs-only pass); **[open]** = not verifiable from the repository alone and
left for the implementation slice.

Working-tree drift note (important): another session has uncommitted brand/dashboard work in the same
tree. At the time of this pass `website/index.html` is modified (brand wordmark SVGs, favicon set,
`site.webmanifest` link, og-image hashes), `website/src/input.css` and generated `website/app.css` are
modified, and `website/site.webmanifest` plus the favicon/icon files are untracked. `website/site.js`,
`website/downloads.json`, `website/llms.txt` and `website/styles.css` are clean/tracked. All line
anchors below were re-read from the working tree on 2026-10-29. The cross-checked anchors in
[research.md:82](research.md) (`website/index.html:293-327`, `788-844`) and
[marketing-boundary.md](notes/marketing-boundary.md) (:7, :43-48, :75-78, :94, :300, :445, :481) still
hold in this tree; only the head/footer grew by the brand edits, so later anchors can move by a few
lines once that work is committed. Do not revert or reformat that work while applying this inventory.

## 1. Scope and boundary rules

### 1.1 What the marketing site is

The surface is the single static page in `website/`, published from `website/` by
`.github/workflows/pages.yml` to GitHub Pages at `https://k-arthur.github.io/hutch/`
[repo] [docs/marketing-site.md:272-280](../marketing-site.md). It is a development-preview
explanation page: no server, no account, no app logic beyond small presentation enhancements in
`website/site.js` (reveals, drawer, tabs, pointer-reactive art) [repo]
[website/site.js:1-5](../../website/site.js). Every claim on it must fit the claims envelope in
[docs/marketing-site.md](../marketing-site.md), the single stage term "development preview"
[docs/marketing-site.md:27](../marketing-site.md), and the no-analytics/no-browser-storage rule
[docs/marketing-site.md:1-8](../marketing-site.md).

### 1.2 What it is not, and must not become

- Not a hosted sign-up, account, waitlist or email-capture funnel. There is no hosted service to sign
  up for [repo] [docs/marketing-site.md:3-4](../marketing-site.md); the brief says the same.
- Not an installer-distribution page. There are no packaged desktop installers, no public package, and
  no artifact for any platform yet [repo] [website/downloads.json:9-38](../../website/downloads.json).
- Not a pricing page: no tiers, no plan selector, no payment-card field, no trial, no urgency UI
  [repo] (audited below).
- Not an analytics or cookie-consent surface: no third-party scripts and no browser storage
  [repo] [website/site.js:1-159](../../website/site.js); the no-external-request gate is
  `tests/e2e/test_website.py:568-576`.
- Not the place where post-install welcome/confirmation banners live; those belong to the installed
  app and its state, never to the marketing page or a marketing-injected app banner (section 4).

### 1.3 Rules binding every change

1. **Claims match the installed product.** Source-install only, Linux-first, Python 3.11+ source
   checkout, English UI, a configured model route required for real runs, MIT license, no hosted
   sign-up, no hosted inference, development preview. [repo]
   [README.md:108-118](../../README.md), [docs/runtime-setup.md:6-30](../runtime-setup.md).
2. **Single stage term.** "development preview" everywhere; "private preview"/"private alpha" stay
   retired [repo] [docs/marketing-site.md:27](../marketing-site.md).
3. **External-link policy.** Today the page's only external anchors are
   `https://github.com/K-Arthur/hutch` and `https://github.com/K-Arthur/hutch#quickstart`, and
   `tests/e2e/test_website.py:532-541` asserts that exact set. Adding a license link, issue-tracker
   link or docs link therefore requires the same change to update the test and the rule in
   [docs/marketing-site.md:6](../marketing-site.md); do not widen external links silently.
4. **No false download affordance.** Do not render a Download/Install action while the release
   manifest has empty artifact lists; never point a Download label at a release page. Enforced today
   by `tests/e2e/test_website.py:544-562`.
5. **Availability is explicit and dated.** A claim that can change (installers, platforms, versions,
   support) must carry a dated single source of record; the visible date and the data source must
   move together.
6. **Entry names the real path before the click.** Source install, prerequisites and the model-route
   dependency must be visible near the entry point, not only in the FAQ or in a repository README.
7. **No fabricated trust.** No testimonials, star counts, "trusted by", benchmark rankings, security
   seals or invented user counts; link the actual repository and issue tracker instead.
8. **No fabricated welcome, personalisation or success.** The site cannot know a returning visitor
   without client state; it must not pretend to. The app must not greet a first-run user as a
   returning one. Section 4 is the allowed/forbidden state machine.
9. **Edit sources, never generated CSS.** `website/app.css` and `website/styles.min.css` are build
   outputs; edit `website/styles.css` and `website/src/input.css`, then run
   `npm run build:css --silent` (it also stamps asset hashes) [repo] [package.json](../../package.json).
10. **Do not touch unrelated uncommitted work.** Preserve the other session's brand/dashboard edits;
    apply marketing edits on top of them, do not revert, clean, format or stage them.

### 1.4 Verification limits of this pass

This is a docs-only planning pass. I read the repository sources listed in "Sources" and ran
read-only greps; I did **not** run the site, a browser, Playwright, a server, or any test, and I did
not fetch external URLs. Therefore: the deployed page may differ from repository source **[open]**
(open question 21 in [research.md:424](research.md)); external URL status is inherited evidence, not
re-verified; the quickstart fragment was checked only against the local `README.md` headings; and the
app first-run copy was inspected by grep/read of
`src/hutch/server/static/app.js`, not by launching the app.

## 2. Surface inventory

One row per surface that can affect what the first screen promises. "Change type" is one of MAKE TRUE,
REMOVE, ADD DISCLOSURE, RENAME, or NO-OP (keep absent). Priority: P1 = blocks a binary gate or points
at a dead destination; P2 = required for the ten checks in section 6; P3 = clarity/polish. Owner roles
are defined in section 5.

| ID | Exact surface | Current copy / behaviour (quoted) | Conflict with onboarding reality | Required change (type) | Owner | Priority | Binary acceptance criterion (evidence) |
|---|---|---|---|---|---|---|---|
| MKT-01 | Hero entry CTA set: @website/index.html:299-303 (hero actions), @website/index.html:287 (mobile drawer footer), @website/index.html:256 (header CTA) | `See the app` -> `#proof` (:301, :256); `Check availability` -> `#get` (:302, :287) | The entry does not name the real path (source install on Linux + prerequisites) before the click; "Check availability" does not tell a visitor a source checkout is required. Fails research 7.4 check 1 and 2 if read literally. [repo] | RENAME + ADD DISCLOSURE: keep `See the app` as the in-page product tour; relabel the secondary entry CTA to `Run from source on Linux` (same `#get` destination) in hero and drawer; add one expectation line under the hero actions naming Linux, source install, development preview, model route required, with the working install link from MKT-05. | Marketing/website | P2 | PASS if at 375/768/1440 the hero entry block contains exactly one visible `Run from source on Linux` link to `#get`, one visible line containing Linux + source install + development preview + model route required, and no label promising a download, package or one-click install; DOM assertion + screenshots recorded. |
| MKT-02 | Trust microcopy adjacent to entry: @website/index.html:300, inside `.hero-actions` | `MIT-licensed · open source · Linux` only | No adjacent link to license/source/issues, no preview/no-warranty note, and the data-flow note lives far below (FAQ :891-892; availability table :832). Fails research 7.4 check 4. [repo] | ADD DISCLOSURE: replace with a compact trust row next to the CTAs: MIT license link, source repo link, issue tracker link, `Development preview` badge, preview/no-warranty note, and one data-flow line: `Local by default; hosted model routes send the prompt and context to the provider you choose. See what leaves your machine (#faq).` Update `tests/e2e/test_website.py:540` external-link allowlist and [docs/marketing-site.md:6](../marketing-site.md) in the same change. | Marketing/website + Docs | P2 | PASS if one entry-block screenshot at 375/768/1440 shows all six items; every link returns HTTP 200 or resolves to an in-page id; the updated external-link test passes; docs/marketing-site.md rule matches the new link set. |
| MKT-03 | Availability section framing + date: @website/index.html:788-800 (heading, description, CTA block) and :836-847 (availability term) | `The source is open. Desktop apps are next.` (:791); `Windows, macOS and packaged Linux desktop apps are still in progress.` (:792); `Native desktop installers remain under development.` (:844) | "are next"/"still in progress"/"under development" are undated roadmap promises. Reality: macOS/Windows executors are not implemented and no installer is published [repo] README.md:262. No visible last-checked date anywhere (only JSON-LD `dateModified` :57 and the proof capture date :354). Fails research 7.4 checks 3 and 10. [repo] | MAKE TRUE + ADD DISCLOSURE: replace forward-looking wording with dated state, e.g. `Development preview. No packaged desktop installer and no macOS or Windows executor is published today. Availability checked <YYYY-MM-DD>; source of record: downloads.json and GitHub Releases.` Do not add "coming soon", countdowns or urgency. | Marketing/website + Release (date) | P2 | PASS if the visible `#get` text contains one ISO date, explicitly says no desktop installer and no macOS/Windows executor are available today, contains none of the availability promises "coming soon", "next", "in progress", or "soon", and the date equals the single source recorded in validation.json. |
| MKT-04 | Source-install prerequisites and post-install sequence: @website/index.html:793-800, :842-844 | `Source setup requires a Linux computer and a model route you configure.` (:800); `Source setup: follow the Linux quickstart. Native desktop installers remain under development.` (:844) | Omits Python 3.11+, uv, start-the-local-server and English UI; there is no "what happens after install" sequence. Reality is install from source -> start local server -> first request -> choose/verify a model route, with bot/channel steps optional. Fails research 7.4 check 2 and research 7.2 M-03/M-07. [repo] | ADD DISCLOSURE: add a prerequisite line (Linux, Python 3.11+, uv, a local service or provider route) and a numbered sequence: 1 install from source on Linux; 2 start the local server; 3 write a first request; 4 choose/verify a model route (hosted key, local service, or provider login). Mark creating a bot, connecting channels and learning approvals as optional. | Marketing/website + Docs | P2 | PASS if the rendered `#get` block contains Linux, Python 3.11+, uv, "start the local server", "model route", and the four ordered steps at 375/768/1440; no step implies bundled runtimes, bundled models, hosted inference or one-click install. |
| MKT-05 | Quickstart handoff destination: @website/index.html:795 (`Linux setup`) and :844 (`Linux quickstart`), @website/downloads.json:6 (`setup`) | `https://github.com/K-Arthur/hutch#quickstart` in all three places | [repo] `README.md` has no quickstart heading or anchor (headings list: `## Setup details` at README.md:116; no "quickstart"/"quick start"; no quickstart file exists via glob). GitHub returns 200 for the repo but the fragment does not resolve to a section, so the install CTA lands at the repository top. The only install handoff is therefore a dead fragment; fails research 7.4 check 1 evidence. | MAKE TRUE: either add a `## Quickstart` section to README.md containing the real prerequisites (Docs), or repoint all references to the existing `#setup-details` anchor; keep `website/downloads.json` `source.setup` in sync; update the e2e external-link allowlist if the URL changes. | Docs + Marketing/website (Release for downloads.json) | P1 | PASS if the target fragment resolves to a heading that exists in the README as served from GitHub main at implementation time, all three references use that target, HTTP status is 200, and no reference contains an unresolvable fragment; heading + curl output recorded. |
| MKT-06 | Desktop release manifest link: @website/index.html:8 and @website/downloads.json:1-39 | `<link rel="alternate" type="application/json" href="downloads.json?v=34dc6a4b" title="Hutch desktop release manifest">`; manifest `channel: "preview"`, four platforms (Windows 11 x86_64, macOS 14 aarch64/x86_64, Ubuntu 24.04 x86_64), every `artifacts` array empty (:15, :22, :29, :36) | The title "release manifest" implies a desktop release exists; a browser or crawler surfacing the alternates sees an availability payload with no artifacts. [repo] `website/site.js` never fetches `downloads.json` (no fetch/XHR; site.js:1-159), so no CTA is generated from it today. Research 7.2 M-04 / open question 21. | MAKE TRUE (keep, retitle + date): retitle the alternate link, e.g. `Hutch desktop release status (preview; no published artifacts)`; add a dated status field to `downloads.json` (`checked_at` or `status: "no-published-artifacts"`) and display the same date in `#get` (MKT-03); never add a visible Download CTA. | Release + Marketing/website | P2 | PASS if the alternate link title states no published artifacts; `downloads.json` carries the dated empty status; all four artifact lists remain empty; visible page still has zero `a[download]` or `/releases/download/` anchors; manifest e2e test updated and passing. |
| MKT-07 | FAQ + JSON-LD claims and dated metadata: @website/index.html:34-232 (SoftwareApplication :34-59, FAQPage :60-232) and visible FAQ :855-944 | `"isAccessibleForFree": true` (:44); MIT license (:43); no `offers`/`publisher` per docs/marketing-site.md:226; `"dateModified": "2026-10-28"` (:57); visible and schema FAQ parity is 20/20 (verified counts) | The claims are honest today, but every copy change in MKT-01..MKT-11 must be mirrored in the visible FAQ and JSON-LD; the parity test is the gate and `dateModified` must advance with copy changes. [repo] | MAKE TRUE (metadata sync): regenerate/update the FAQ schema block in lockstep with visible copy; bump `dateModified` when claims change; keep no `offers`, no `publisher`, no `aggregateRating`. | Marketing/website + Docs (claims wording) | P2 | PASS if `tests/e2e/test_website.py:1408` passes, both JSON-LD blocks parse, visible FAQ count equals schema question count (20/20), `dateModified` is not older than the copy-change date, and none of offers/publisher/aggregateRating/ratingValue appear. |
| MKT-08 | Provider plan wording: @website/index.html:574-580 (`Plans &amp; keys` card), FAQ :928, JSON-LD :198 | Card title `Plans &amp; keys` (:577); body is entirely provider keys/sign-ins (:578); FAQ/JSON-LD include `no plan is silently upgraded or selected as a fallback` (provider plan, not a Hutch plan) | "Plans" alone can be misread as Hutch subscription/pricing tiers; the product has no Hutch plan or tier. The body is provider-scoped, so this is ambiguity, not a pricing claim. [repo] | RENAME (make true): retitle to `Provider plans &amp; keys` (or `Provider keys and sign-ins`); optionally add "No Hutch plan or account is required" in the card. | Marketing/website | P3 | PASS if no standalone "Plans" heading remains that can read as a Hutch offering; card renders without overflow at 375/768/1440; text audit shows provider-scoped wording only. |
| MKT-09 | Free / free-forever / no-card claims: FAQ @website/index.html:866-869 and :874-876, JSON-LD :78 and :94, README.md:244-246 | `Yes — the software itself is free. Hutch is MIT-licensed with no subscription, hosted tier or usage fees of its own. A hosted model route uses your own provider account and pays that provider's prices...` (:868); `Hutch does not include hosted inference.` (:876); FAQ question `Do I need an API key, a credit card, or a GPU?` (:875) | Checked and REAL: the free claim is scoped to the MIT software and provider costs are disclosed; "free forever" does not appear; "no card"/"no credit card" is never claimed. Keep the question wording because provider accounts may require a card; do not add badges. [repo] | NO-OP (keep absent). Forbidden additions: "free forever", "no credit card required", "no card", trial/plan badges, urgency. | Marketing/website | P2 (gate constraint) | PASS if the FAQ answer still scopes provider billing, the JSON-LD answer matches, and the text audit finds no `free forever`/`no credit card`/`no card required` claims. |
| MKT-10 | Provider-cost scope near the availability CTA: @website/index.html:793-796 | The `#get` CTA block is only `View source on GitHub` (:794) and `Linux setup` (:795); cost scope appears only in the FAQ (:868, :932) and the JSON-LD (:78) | The cost boundary ("MIT software; hosted model usage is billed by the provider") is not adjacent to the availability action, the point where a reader decides to try it. Research 7.1 B-7 and notes/marketing-boundary.md §4 ask for the scope near the CTA without adding pricing. [repo] | ADD DISCLOSURE: add one sentence next to the `#get` CTAs: `MIT-licensed software; hosted model usage is billed by your own provider account. No Hutch subscription, hosted tier, or usage fee.` Keep the FAQ wording; do not add a pricing table or tiers. | Marketing/website | P2 | PASS if the sentence is visible within the `#get` entry block at 375/768/1440, no pricing/tier/card UI was added, and research 7.4 check 5's link/CTA inventory still shows no pricing capture. |
| MKT-11 | Support matrix / locale claims: @website/index.html:300, :792-800, :831-832, :843, :974-975, :997-998; @website/llms.txt:11; README.md:109, :118, :262 | Linux is stated repeatedly; Python 3.11+ appears only in README/llms.txt, not on the page; English-only is never stated; the page declares `<html lang="en">` (:2). No "worldwide"/"any computer"/localization claim exists. [repo] | Research 7.4 check 9 requires Linux-first and English UI stated and version support scoped. Without it, "runs on your own computer" can be read as multi-platform/localized. Research open question 11 (English-only) is [open] for app i18n. | ADD DISCLOSURE: add one support-matrix line in `#get`: `Supported today: Linux x86_64 source checkout; Python 3.11+; English UI (en). macOS and Windows executors, and packaged installers, are unavailable.` Never claim localization, units, or Windows/macOS parity. | Marketing/website + Docs | P2 | PASS if the rendered sentence contains Linux, Python 3.11+, English; text audit finds no worldwide/any-device/localized claim; screenshots at 375/768/1440; JSON-LD `operatingSystem` remains `Linux`. |
| MKT-12 | Welcome / confirmation banner surface: @website/index.html:798-801 (only banner-like element), @website/site.js:1-159 (no state, no storage), @src/hutch/server/static/app.js:3273-3281 (real first-run welcome) | Site: `Desktop installers are not available yet` availability notice (:800), not a welcome or success banner. App first-run: `<h1 id="first-run-title">What would you like help with?</h1>` and `Start with a request. Hutch carries it into setup for review.` (:3279-3280). No `welcome back` string anywhere in app.js/templates/site (grep). [repo] | The requested welcome/confirmation pattern assumes a sign-up or returning-user banner; the static site has no stateful banner and must not pretend, and the app has only real state-driven first-run copy. Research 7.4 check 7 and 7.3. | NO-OP (keep absent on the marketing site; pattern OUT). If a post-install confirmation is later added it is app-owned, state-driven and follows section 4. Forbidden: marketing banner injected into the app; "Welcome back" without a completed-session marker. | Onboarding frontend (app) + Marketing/website (site) | P2 (gate constraint) | PASS if `website/site.js` still contains no storage/network calls, no first-run and no returning state exists on the marketing page, the app has no `Welcome back` on first run, and any future banner has a recorded state + allowed/forbidden-copy row. |
| MKT-13 | Social proof / fabricated-trust surface: whole page + JSON-LD; competitor prose @website/index.html:870-873 (FAQ comparison) | No testimonials, star counts, "trusted by", badges, user counts, benchmarks or `aggregateRating` (text/schema audit). The FAQ names Open WebUI and OpenClaw in prose only, no links, limited to verifiable architectural differences (:872), which [docs/marketing-site.md:228](../marketing-site.md) permits. [repo] | None today; gate 6 must keep it that way. Adding a logo wall, install count, review stars or benchmark ranking would be a new false claim. | NO-OP (keep absent). Forbidden: testimonials, stars, "trusted by", download/install counts, benchmark rankings, invented security certifications. | Marketing/website | P2 (gate constraint) | PASS if text/schema audit for testimonial/trusted-by/rating/aggregateRating returns nothing, competitor names remain unlinked prose, and every remaining numeric claim has a source in the page or docs. |
| MKT-14 | Analytics / cookie-consent surface: @website/index.html:1009 (only `site.js`, self-hosted), @website/site.js:1-159 | No analytics script, no CDN, no font/asset request off-origin; `site.js` makes no fetch/XHR/sendBeacon and uses no storage; no cookie banner. [repo] The no-external-request gate is `tests/e2e/test_website.py:568-576`; docs/marketing-site.md:1-8 states the policy. | None: adding analytics would violate the local-first/no-telemetry posture (research section 9 OUT row). | NO-OP (keep absent; pattern OUT). Forbidden: third-party analytics, funnel tracking, cookie-consent banner (there is nothing to consent to), heatmaps, A/B services. If measurement is ever required, it must be local and opt-in and say so. | Marketing/website | P2 (gate constraint) | PASS if the section 6.4 site.js storage/network audit is empty, the no-external-request test passes, and no consent/analytics UI exists. |
| MKT-15 | Web app manifest: @website/index.html:28 (`<link rel="manifest" href="site.webmanifest?v=0987b2ff">`) and @website/site.webmanifest:1-47 | `name`/`short_name` `Hutch`, `start_url` `./`, `display` `standalone`, `theme_color` `#09090b`, six icons; description `Local-first AI assistants. Your bots. Your machine. Your rules.` The file is currently untracked brand work. [repo] | A standalone-display manifest can trigger browser "Install app" affordances even though no packaged app exists; the file is not in the claims envelope in docs/marketing-site.md and has no test coverage yet. Risk of a false installable-app impression. | ADD DISCLOSURE / VERIFY (coordinate, do not edit the brand session's file blindly): verify no install prompt or "install app" affordance appears in Chromium at 375/768/1440; either document the manifest as site metadata only in docs/marketing-site.md and add a manifest-validity test, or drop `display: standalone` until a desktop app ships; never imply an installer is available. | Marketing/website (brand session) + Release | P3 | PASS if the manifest fetches 200 and parses, docs/marketing-site.md records it, a test asserts the served manifest, the browser check records no install prompt, and no install/download copy is added to the page. |
| MKT-16 | Product capture provenance (`#proof`): @website/index.html:336-357 | `Real application` badge (:340); alt `The actual Hutch welcome screen. A person can describe a request, see whether OpenCode or another AI service is ready, and set up an assistant without repeating the request.` (:346); `Captured from the current local application on 2026-10-23...` (:354) | Uncommitted dashboard/brand work can change the first-run screen; docs/marketing-site.md:211-218 says source merges do not regenerate these images and the capture must be refreshed after a UI change. A stale capture would make the `Real application` badge and alt text false. [repo] | MAKE TRUE (evidence refresh): recapture with `docs/realignment/capture_first_run.py` against the final first-run UI in slice 11, replace the WebP assets, run `npm run build:css --silent` to stamp new hashes, and update the proof-meta date plus alt/copy if the first-run screen changed. | Release + Onboarding frontend | P2 | PASS if the proof-meta date is not older than the last first-run UI change date, the alt matches the actual first screen, the image renders at 375/768/1440, and `tests/e2e/test_website.py::test_real_setup_capture_is_truthful_and_fits_anonymous_viewports` passes. |

Inventory summary: 16 surfaces, 12 CHANGE rows (MKT-01..MKT-08, MKT-10, MKT-11, MKT-15, MKT-16) and
4 NO-OP/OUT rows (MKT-09, MKT-12, MKT-13, MKT-14).

## 3. Requested-vs-actual category reconciliation

The six requested categories come from a generic signup/pricing funnel. Most do not exist here; the
table records what is actually on the page rather than inventing the pattern. Verdicts: REAL = present
and truthful; PARTIAL = truthful but incomplete against the boundary checklist; ABSENT = not on the
page; NO-OP = keep absent; OUT = pattern not applicable to this product.

| Requested category | Actual current state (quoted, anchored) | Verdict | Action | Evidence |
|---|---|---|---|---|
| Signup form fields | No signup UI at all: `grep` finds no `<form>`, no `<input>`, no email/waitlist capture in `website/index.html`; the only button-like controls are menu/drawer/tab buttons (:257, :270, :676-678); copy says `Hutch has no hosted sign-up` (:800) and `There are no packaged desktop installers or hosted sign-up today` (:813). [repo] | ABSENT -> NO-OP (keep absent) | Add nothing. Do not add email capture, waitlist, account creation or a field that pretends to be one. Re-open only if a hosted account/waitlist is actually added; then re-run the boundary classes in notes/marketing-boundary.md §2. | the section 6.4 signup audit returns nothing; @website/index.html:800, :813; README.md:262. |
| CTA copy (hero) | `See the app` -> `#proof` (:301, header :256); `Check availability` -> `#get` (:302, drawer :287); availability CTAs `View source on GitHub` (:794) and `Linux setup` (:795); closing CTA `Explore the source` (:956) and `See the app` (:957). None says Download/Get started/Install; a download-anchor guard exists in tests/e2e/test_website.py:562. [repo] | PARTIAL (truthful labels, but the entry does not name the source-install path and the "Linux setup" destination fragment is dead) | MKT-01 (rename secondary entry CTA + name the path before the click) and MKT-05 (fix the destination anchor). Keep `See the app` as the in-page product tour. Do not relabel to "Download". | @website/index.html:301-302, :287, :794-795, :956-957; README headings (no quickstart anchor); e2e :540, :562. |
| Trust microcopy | `MIT-licensed · open source · Linux` appears as a single compact caption at @website/index.html:300; MIT license and repo also appear in JSON-LD (:43, :46); the footer states `Linux computer required today` / `No desktop installer yet` (:997-998). No issue tracker, requirements, data-flow line or preview/no-warranty note adjacent to the entry. [repo] | PARTIAL | MKT-02 (add the trust row adjacent to the entry) and MKT-11 (support matrix). External-link allowlist and docs rule must change with it. | @website/index.html:300, :997-998; @website/index.html:43-48; e2e :532-541. |
| Pricing / plan wording | No pricing page, no tiers, no card gate, no plan selector, no trial. FAQ: `no subscription, hosted tier or usage fees of its own` (:868). The only "plan" surfaces are: `Plans &amp; keys` provider card (:577), provider-plan prose `no plan is silently upgraded` (:928, JSON-LD :198), and workflow "plan" meaning a multi-step plan (:314, :446). [repo] | ABSENT for Hutch pricing -> NO-OP (keep pricing absent); PARTIAL ambiguity in "Plans & keys" | Keep pricing/tiers/card absent (re-open only if a paid or hosted tier is added, and then change the onboarding promise and the site together). MKT-08 renames the provider card; MKT-10 adds the scoped cost note near the CTA; MKT-09 forbids free-forever badges. | @website/index.html:577-578, :868, :928; JSON-LD :78, :198; e2e :562. |
| Welcome / confirmation banner | Marketing site has no banner state: site.js has no storage or fetch (:1-159), the only banner-like element is the static availability notice `Desktop installers are not available yet` (:798-801). App first run is real and stateful: `What would you like help with?` (app.js:3279); no `welcome back` string in app.js/templates/site. [repo] | ABSENT on site -> OUT (pattern not applicable); app-side pattern is present but truthful | Keep absent. If a post-install confirmation is added later it renders in the app only, is state-driven and follows section 4. Never inject a marketing banner into the app and never render "Welcome back" on a first run. | @website/site.js:1-159; @website/index.html:798-801; @src/hutch/server/static/app.js:3273-3281; grep `welcome back` (empty). |
| Free-forever / no-card claims | FAQ: `Yes — the software itself is free. Hutch is MIT-licensed with no subscription, hosted tier or usage fees of its own. A hosted model route uses your own provider account and pays that provider's prices...` (:868); `Hutch does not include hosted inference.` (:876); JSON-LD `"isAccessibleForFree": true` (:44). The string "free forever" does not appear; no "no card"/"no credit card required" claim appears; the FAQ question does ask about a credit card (:875) without promising absence. [repo] | REAL (free claim correctly scoped); "free forever" ABSENT -> NO-OP; "no card" ABSENT -> NO-OP | Keep the scoped wording; do not add "free forever", "no credit card required" or plan badges. MKT-10 surfaces the same scope near the availability CTA so the free claim cannot be read as hosted-usage-included. | @website/index.html:868, :875-876; JSON-LD :44, :78, :94; README.md:244-246. |

Additional surfaces audited although they were not among the six requested categories:

| Surface | Actual state | Verdict | Action |
|---|---|---|---|
| Download/install affordance | No Download labels or release-download anchors (e2e :562); empty-artifact manifest linked as an alternate at :8; `Desktop installers are not available yet` (:800); footer `No desktop installer yet` (:998). [repo] | REAL (no false download CTA); manifest label needs MKT-06 | MKT-06 (retitle/date the manifest), MKT-03 (dated availability), MKT-15 (manifest affordance check). |
| Social proof | Absent (no testimonials/stars/trusted-by/aggregateRating); competitor comparison is prose-only (:872) and permitted by docs/marketing-site.md:228. [repo] | ABSENT -> NO-OP | MKT-13. |
| Analytics / cookie consent | Absent; self-hosted assets; no storage/fetch in site.js; no-external-request test at e2e :568-576. [repo] | ABSENT -> OUT | MKT-14. |
| Locale / support matrix | Linux stated in five places; Python 3.11+ only in README/llms.txt; English UI unstated; no worldwide/units claim. [repo] | PARTIAL | MKT-11. |

## 4. Welcome/confirmation banner state machine

Where banners may render: **only the marketing site for static availability/status notices, and only
the installed app for first-run/success/failure state.** A marketing banner must never be injected
into the dashboard, and the marketing page must never fake a returning user. The site stores no
browser preference and sends no request today [repo] [docs/marketing-site.md:6-8](../marketing-site.md),
so it has no legal "returning visitor" state unless a local completion marker is deliberately added
and disclosed. The app's first-run surface is real and stateful
[repo] [app.js:3273-3281](../../src/hutch/server/static/app.js); it contains no "Welcome back" string.

| State / event | May render where | Allowed copy | Forbidden copy |
|---|---|---|---|
| First visit to the marketing page (no client state) | Marketing site only, as a static availability/status notice | `Development preview. No packaged desktop installer is published; run from source on Linux. Availability checked <YYYY-MM-DD>.` plus the real next step (prerequisites / quickstart) | "Welcome back", "Thanks for signing up", "Your account", "You're in", fake progress, invented name/profile |
| Returning visitor to the marketing page | Nowhere stateful (static site stores nothing) | Same static copy as a first visit; no greeting at all | Any "welcome back"/"we missed you"/personalisation; adding client storage to distinguish visitors without a disclosed reason |
| Post-install first run on a fresh state | Installed app only (app.js:3273-3281) | `What would you like help with?` / `Start with a request. Hutch carries it into setup for review.` and real next-action copy | "Welcome back"; marketing banner injected; pre-filled name/profile |
| Returning after completed onboarding (app, only with an explicit completed-session marker) | Installed app only | "Welcome back" only if the marker exists; dismissible; shown at most once per completion | Greeting a first-run user as returning; showing it twice; the marketing site claiming it |
| Action succeeded (first request sent, bot created) | Installed app, adjacent to the result | Success banner confirming exactly that action, dismissible | Success before completion; success surviving a later failure; any success banner on the marketing site |
| Action failed / provider unavailable | Installed app state; the site may show manifest/release-unavailable problem copy only if a fetch is added | `There is a problem. Try again later.` plus what was saved and a retry/switch route | Blank skeleton; "coming soon" as a substitute for a failure; success shell; blaming the user |
| Pairing code expired | Installed app pairing UI only | `Code expired. Generate a new one.` | Infinite spinner; silently reusing the code |
| Server / release manifest unavailable | Marketing site availability block only, for the data-driven state | Plain heading, "try again later", the date of the last successful check, and what is known | Rendering stale success as current; onboarding steps that cannot run; hiding the failure |

Semantics for any future banner: use `role="alert"` for important/time-critical messages and
`role="region"` for contextual ones [external] (GOV.UK notification-banner guidance, carried in
[marketing-boundary.md:73](notes/marketing-boundary.md)); never auto-dismiss an error; never let a
banner block or obscure a focused control; never re-show a stale success after a later failure. This
mirrors [research.md section 7.3](research.md) and [marketing-boundary.md section 6](notes/marketing-boundary.md).

## 5. Owners

Role-based ownership; named individuals are assigned by the Lead. A row's owner is the primary owner;
"+" marks a required reviewer/co-editor in the same change.

| Role | Exact surfaces owned | Inventory rows | Handoffs and notes |
|---|---|---|---|
| Marketing/website owner | `website/index.html` (hero, `#proof`, `#get`, visible FAQ, footer, head metadata/structured-data blocks), `website/styles.css` and `website/src/input.css` for any styling, `website/site.js` behaviour, site-level assertions in `tests/e2e/test_website.py`, and the site half of `docs/marketing-site.md` | MKT-01, MKT-02+, MKT-03+, MKT-06+, MKT-08, MKT-09, MKT-10, MKT-11+, MKT-13, MKT-14, MKT-15+ | Never hand-edit `website/app.css` or `website/styles.min.css`; rebuild with `npm run build:css --silent`. Preserve the other session's brand edits in index.html (favicons, manifest link, wordmarks) when applying changes. Update the external-link allowlist test and the docs rule whenever MKT-02 adds links. |
| Docs owner | `README.md` (`## Setup details` at :116 and a new `## Quickstart` section or a repointed anchor), `docs/runtime-setup.md`, `docs/marketing-site.md` (claims envelope, external-link rule, manifest documentation), `website/llms.txt` parity, and claim wording in the visible FAQ/JSON-LD | MKT-04+, MKT-05, MKT-02+ (rule), MKT-07+, MKT-11+ | Keep README/llms.txt/runtime-setup prerequisites consistent with the new on-page prerequisites. The external-link policy change must be one commit with the page change. |
| Onboarding frontend owner | `src/hutch/server/static/app.js` first-run welcome and any state-driven success/failure banner, first-run state evidence in `tests/e2e/test_design_system.py`, and the app half of the welcome state machine | MKT-12, MKT-16+ | Guarantees the app keeps real state-driven copy (`What would you like help with?`, no "Welcome back" on first run) and never hosts a marketing banner. Supplies the final first-run copy and change date so MKT-16 recapture is not stale. |
| Release owner | `website/downloads.json` truth and dated status, GitHub Releases/artifact completeness checks, dated availability source of record, Pages deployment (`.github/workflows/pages.yml`), capture refresh per `docs/marketing-site.md:211-218`, and the evidence bundle under `docs/onboarding/artifacts/marketing-<YYYY-MM-DD>/` | MKT-03+ (date), MKT-05+ (downloads.json setup URL), MKT-06, MKT-15+, MKT-16 | Owns "is this date/artifact state true today?" and the final evidence archive. Must not publish or link an artifact that does not exist; records HTTP status evidence for every external link. |

## 6. Acceptance and evidence plan

### 6.1 The ten binary entry-surface checks mapped to slices 01-11

Definitive slice map from the Lead (2026-10-29): 01 onboarding route + resume; 02 first-run handoff +
AI-service chooser; 03 readiness states; 04 hosted key; 05 local service; 06 external login recovery;
07 assistant fast path; 08 first request + completion; 09 keyboard/a11y hardening; 10 phone pairing
countdown; 11 marketing boundary + docs + final gate. **None of the ten checks is a gate for slices
01/02** (additive onboarding routes and the first-run handoff; the marketing site is not touched by
those slices); all ten are gates for slice 11. Slices 01-10 contribute only the app-side counterparts
that the marketing page cannot prove: real state-driven first-run copy (check 7's app half), real
success/failure banner behaviour (check 8's app half), and the final first-run UI that keeps MKT-16
current. Marketing checks are never satisfied by a docs-only statement; they are satisfied by the
rendered page and dated evidence in slice 11.

| # | Check (from research.md 7.4) | Satisfied by rows | Gated in slices 01/02? | Gated in slice 11? | Required evidence |
|---|---|---|---|---|---|
| 1 | Primary entry action names the real path (source install), not "download the app" | MKT-01, MKT-05, MKT-06 | No | Yes | CTA label + destination screenshot at 375/768/1440; working quickstart anchor; `grep` for Download anchors (empty) |
| 2 | Prerequisites listed before the click (Linux, Python 3.11+, local server start, model route) | MKT-01, MKT-04, MKT-11 | No | Yes | Rendered entry/`#get` blocks at 375/768/1440; text assertion for each prerequisite |
| 3 | Availability explicit and dated; empty/no-artifact release renders honestly, never as Download | MKT-03, MKT-06 | No | Yes | Screenshots of dated availability + manifest state; artifact lists empty; date matches source |
| 4 | Trust row adjacent to entry: MIT license, repo, issue tracker, preview status, data-flow note | MKT-02, MKT-11 | No | Yes | One entry-block screenshot at 3 widths; each link 200 or in-page; updated allowlist test |
| 5 | No pricing tiers, card gate, account/waitlist capture, urgency or countdown UI | MKT-08, MKT-09, MKT-10 (and reconciliation) | No | Yes | Link/CTA inventory + text/audit commands; no form/input; no pricing sections |
| 6 | No fabricated social proof or unverified numeric claims | MKT-13 | No | Yes | Whole-page text/schema search; each remaining number has a source |
| 7 | First-run vs returning copy is state-driven; "Welcome back" cannot appear on a first run | MKT-12 + app evidence from slices 01-10 | No (app half lands in 01/02; state copy re-verified later) | Yes (site half + re-verification) | Banner state-machine walk (section 4); app first-run screenshot; grep for `welcome back` (empty) |
| 8 | Success banners only after the action; failures carry retry/switch-route; expired pairing says expired and offers regenerate | MKT-12 + app evidence from slices 01-10 | No (app half lands in 01/02 and 08) | Yes (site half + re-verification) | App state screenshots/validation rows supplied by onboarding frontend; marketing page has no success banner |
| 9 | Locale/units/platform claims scoped; English UI and Linux-first stated | MKT-11, MKT-03 | No | Yes | Support-matrix screenshot at 3 widths; audit for worldwide/any-device wording (empty) |
| 10 | Every changeable claim (availability, versions, pricing) carries a date or a single dated source | MKT-03, MKT-06, MKT-07, MKT-16 | No | Yes | Page copy audit; ISO date in `#get`; JSON-LD `dateModified`; proof-meta date |

Two dependencies need care: MKT-05 (dead quickstart fragment) is cheap and can land as soon as the
Docs owner decides the README target, but its link evidence is checked in slice 11; MKT-16 must follow
the last first-run UI change (slices 01-10) and is therefore recaptured inside slice 11. Neither can be
closed by a docs-only assertion because their evidence is a live link or a rendered capture.

### 6.2 Screenshot and evidence protocol (binary gate)

- **Widths:** 375, 768, 1440 are required for this gate. Existing site lanes at 320/390/900/1440
  [repo] `tests/e2e/test_website.py:267-268` remain and must stay green; the new gate adds the three
  required widths, it does not replace the existing lanes.
- **States to capture on the marketing site:** entry block with trust row (hero, above the fold);
  availability section default; availability details expanded; FAQ with one answer open; footer;
  plus the dated-availability and manifest-state views. For the app-side input to check 7/8, use the
  onboarding frontend's first-run/state captures, not a marketing mock.
- **Verdict:** baseline-first live screenshots of the real served page, opened and reviewed by a human
  reviewer, with a binary **APPROVED / NEEDS WORK** verdict per state and width. Missing evidence is
  **FAIL**, not partial. Record `state, viewport, artifact, verdict, finding, source commit, source
  sha256 (website/index.html, website/styles.css, website/styles.min.css, website/site.js), reviewer,
  date` under `docs/onboarding/artifacts/marketing-<YYYY-MM-DD>/validation.json` (new directory; never
  modify previously reviewed evidence directories). The existing site test already writes a
  validation.json of this shape [repo] `tests/e2e/test_website.py:279-286`; extend it rather than
  inventing a second protocol.
- **Automation is additive, never the gate:** only after the opened-image verdicts are APPROVED may
  `toHaveScreenshot`/`expect(...).toHaveScreenshot()` be added (Chromium/Linux, fixed clock,
  animations disabled, limited masks per [research-brief.md:35](research-brief.md)). Record
  Chromium-only as a limitation; no mobile-native or screen-reader claim.
- **Dated availability:** the date in `#get` is the date of the last successful release/artifact
  check, not the planning date. 2026-10-29 (this document's date) is the planning date only; the
  implementation must record its own checked date and keep it equal to the manifest/GitHub check.

### 6.3 Link and manifest checks (run in slice 11; not run in this docs pass)

```bash
# 1 The quickstart target fragment must exist in the README that GitHub serves.
grep -nE '^#{1,3} ' README.md | grep -iE 'quick ?start|setup details'
curl -fsSL https://raw.githubusercontent.com/K-Arthur/hutch/main/README.md \
  | grep -nE '^#{1,3} .*(quick ?start|setup details)'

# 2 HTTP status for every external anchor on the page (fragments still need step 1).
for u in https://github.com/K-Arthur/hutch \
         https://github.com/K-Arthur/hutch/issues \
         https://github.com/K-Arthur/hutch/blob/main/LICENSE ; do
  printf '%s ' "$u"; curl -sS -o /dev/null -w '%{http_code}\n' "$u"; done

# 3 Manifest is the honest empty preview contract.
uv run --frozen --no-sync python - <<'PY'
import json
m = json.load(open("website/downloads.json"))
assert m["channel"] == "preview"
assert all(platform["artifacts"] == [] for platform in m["platforms"]), "unexpected artifact"
print("manifest ok; checked_at =", m.get("checked_at", "MISSING"))
PY

# 4 Release-completeness cross-check (Release owner, network lane).
curl -fsSL https://api.github.com/repos/K-Arthur/hutch/releases/latest \
  | uv run --frozen --no-sync python -c "import json,sys; d=json.load(sys.stdin); print(d.get('tag_name'), len(d.get('assets',[])))"
```

Record each command's output in the validation.json evidence bundle. A fragment that returns HTTP 200
but does not exist in the README is a FAIL (that is the current MKT-05 state).

### 6.4 Text audits (read-only; run before and after the change)

```bash
# No signup/account/email-capture surface.
grep -nE '<(form|input)[ >]|type="email"' website/index.html          # expect no output

# No banned claims or fake welcome copy.
grep -rniE 'free forever|no credit card|no card required|welcome back|trusted by|testimonial|aggregateRating|ratingValue|worldwide|any computer|one-click' \
  website/index.html website/site.js website/llms.txt                  # expect no output (plus truthful "no hosted sign-up" only)

# No analytics, tracking, or browser storage.
grep -rniE 'analytics|gtag|plausible|umami|googletagmanager|sendBeacon|cookie consent' \
  website/index.html website/site.js                                   # expect no output
grep -nE 'fetch\(|XMLHttpRequest|localStorage|sessionStorage' website/site.js   # expect no output

# No download affordance while artifacts are empty.
grep -nE 'a[^>]+download|releases/download/|>[^<]*Download' website/index.html    # expect no output

# FAQ visible/schema parity (20/20 today).
printf 'visible '; grep -c '<summary class="collapse-title">' website/index.html
printf 'schema  '; grep -c '"@type": "Question"' website/index.html

# Both JSON-LD blocks parse.
uv run --frozen --no-sync python - <<'PY'
import json, re
from pathlib import Path
h = Path("website/index.html").read_text()
blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
for block in blocks:
    json.loads(block)
print("json-ld blocks parse:", len(blocks))
PY

# Emoji ban (repo convention) and local asset hashes after any CSS rebuild.
python scripts/audit_emoji.py
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_emoji_audit.py
```

### 6.5 Focused browser/test lane for slice 11 (not to be run in planning)

```bash
# Site claims, links, manifest, no-analytics, structured data, no overflow.
uv run --frozen --no-sync pytest -q --no-header --tb=line \
  tests/e2e/test_website.py::test_internal_links_resolve_and_external_links_point_to_public_source \
  tests/e2e/test_website.py::test_desktop_manifest_reports_no_installers_before_artifacts_exist \
  tests/e2e/test_website.py::test_static_site_makes_no_external_requests \
  tests/e2e/test_website.py::test_structured_data_and_discovery_metadata_match_the_page \
  tests/e2e/test_website.py::test_home_loads_real_assets_and_truthful_availability \
  tests/e2e/test_website.py::test_local_asset_urls_use_current_content_hashes

# Only if website/styles.css or website/src/input.css changed: rebuild and re-stamp hashes.
npm run build:css --silent
```

The browser lane requires the Playwright Chromium revision and is a release-slice check, not part of
this docs pass. Do not run the full suite or Playwright while planning.

## 7. Rollback

### 7.1 Change shape

All marketing changes are static-file, docs and test edits. There is **no data migration, no server
route, no database change, no user state** and no hosted-service change. Rollback is a git revert plus
one CSS rebuild plus one Pages redeploy.

### 7.2 Revert procedure

1. Revert the single marketing commit (or the marketing hunks) touching: `website/index.html`,
   `website/styles.css`, `website/src/input.css` (only if styling changed), `website/downloads.json`,
   `README.md`, `docs/marketing-site.md`, `website/llms.txt`, `tests/e2e/test_website.py` (and any new
   evidence directory).
2. Rebuild generated outputs so the reverted sources and the stamped asset hashes agree:
   `npm run build:css --silent` (regenerates `website/app.css`, `website/styles.min.css` and the
   `?v=<hash>` references; never hand-edit these files).
3. Commit the revert, then let `.github/workflows/pages.yml` redeploy; Pages fixes cache headers at
   about ten minutes [repo] [docs/marketing-site.md:272-280](../marketing-site.md). Record the check
   time with the evidence.
4. Verify the deployed page: external-link audit (6.3), text audits (6.4), focused site e2e (6.5) and
   a screenshot spot check at 375/768/1440 with the same binary verdict rule.

Partial rollback rule: keep claim pairs together. Visible FAQ and JSON-LD FAQ must revert together
(parity test), `downloads.json` and the dated `#get` copy must revert together, and the trust row and
its external-link test/rule must revert together. A half-revert is worse than no revert because it
creates a false claim or a failing gate.

### 7.3 What not to touch during rollback

- Generated CSS: `website/app.css`, `website/styles.min.css` (rebuild only, never hand-edit);
  `src/hutch/server/static/ui.css` and `model-switcher.css` are dashboard build outputs from the
  other session.
- Another session's uncommitted brand/dashboard work: current modified/untracked files include
  `website/index.html` brand edits, `website/src/input.css`, `website/app.css`,
  `website/site.webmanifest` and the favicon/icon files, plus the `src/hutch/server/static/` and
  template changes. Preserve them; do not revert, clean, format or stage them.
- Reviewed evidence under `docs/**/artifacts/**`; lockfiles, `node_modules/`, `.venv/`, `.pipeline/`
  brand work, and runtime state (`*.db*`, `.state/`, secrets).
- Product onboarding code (`app.js` first-run behaviour) unless the change is explicitly an app-side
  banner/state fix owned by the onboarding frontend owner.

### 7.4 Rollback acceptance

Rollback is complete when the reverted page passes the same ten checks at its prior honest state: no
dead link, dated availability preserved or explicitly removed rather than falsified, no fake download
or welcome copy, JSON-LD parses and matches the FAQ, and the focused site tests pass. If the prior
state already failed a check (for example the pre-change quickstart fragment at MKT-05), the rollback
must note that known failure rather than claiming a pass.

## Sources

Read in this pass (all repository files):

- [research.md](research.md) (sections 1.3, 7.1-7.4, 8 open questions 11, 21, 22)
- [research-brief.md](research-brief.md) (boundaries, visual gate, section 5)
- [notes/marketing-boundary.md](notes/marketing-boundary.md) (failure classes, change inventory,
  banner state machine, binary checklist, sources)
- [docs/marketing-site.md](../marketing-site.md) (claims envelope, external links, hosting, capture
  regeneration, FAQ/JSON-LD rules)
- [docs/runtime-setup.md](../runtime-setup.md):1-34 (what is and is not bundled)
- [README.md](../../README.md):108-118, :116-146, :244-262 (support matrix, setup details, FAQ backing,
  absence of a quickstart anchor)
- [website/index.html](../../website/index.html) (head, JSON-LD, hero, proof, availability, FAQ,
  closing CTA, footer)
- [website/site.js](../../website/site.js) (no analytics, no storage, no manifest fetch)
- [website/downloads.json](../../website/downloads.json) (empty artifact lists)
- [website/site.webmanifest](../../website/site.webmanifest) (untracked brand work)
- [website/llms.txt](../../website/llms.txt) (answer-engine facts and honest "not claims")
- [tests/e2e/test_website.py](../../tests/e2e/test_website.py) (link allowlist, manifest, no external
  requests, structured-data parity, capture provenance, viewport lanes)
- [src/hutch/server/static/app.js](../../src/hutch/server/static/app.js) (first-run welcome
  :3273-3281; no returning-user banner string)
- [package.json](../../package.json) (build:css and verification scripts)
- [.github/workflows/pages.yml](../../.github/workflows/pages.yml) (deployment)

External evidence inherited (not re-fetched in this pass) is listed in
[notes/marketing-boundary.md](notes/marketing-boundary.md) and [research.md](research.md) section 7
(Tauri, GitHub Releases docs, NN/g trust and error guidance, GOV.UK notification/problem patterns,
W3C i18n, Google review-snippet guidance, and the cited public issue reports), marked [external] or
[primary] there.
