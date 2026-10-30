# Marketing-to-product boundary: a dev-preview, local-first site

**Access date: 2026-10-29.** Docs-only note on where Hutch's static marketing site (repository `website/`, GitHub-Pages style, no hosted sign-up) can promise more than the installed product delivers, and what to change. The product brief (verified 2026-10-29) says: no hosted sign-up, no pricing tiers, no payment card, no KYC/identity documents, no liveness, no signature, no cloud account; the site is a development preview and its CTAs point at GitHub/availability. Exact live CTAs and the in-product first-run flow must be verified by the Lead in code; anything below marked "unverified" was not checked.

## 1. Testing the generic fintech framing: mostly inapplicable, and why that matters

The generic task framing (free-forever versus card gate, KYC document upload, liveness, signature) **does not apply to this product**. There is no hosted signup form, no plan selector, no card gate and no identity step in the brief, so "free forever" cannot collide with a later card requirement, and there is no document/liveness/signature step to mismatch. Those boundary classes should not be imported; a checklist built for them would spend effort on modalities Hutch does not have.

What replaces them, and is therefore load-bearing: **install and availability truth, model-route prerequisites, trust microcopy near the entry point, first-run versus returning-user copy, and status/locale honesty.** This note maps those classes and proposes a change inventory; it does not assert the site's exact current hero copy beyond the repository observations cited below.

## 2. Boundary failure classes that do apply

| # | Failure class | Mechanism | Real evidence (opened 2026-10-29) | Hutch translation |
|---|---|---|---|---|
| 1 | CTA promise vs actual first screen | "Get started" implies a packaged app; reality is source install, local server start, then a model route | Tauri's distribution guide only gives you "the tooling you need to distribute your application ... as platform-specific installers"; `tauri build` bundles "for the configured formats" and "Most platforms requires code signing" ([Tauri distribute](https://v2.tauri.app/distribute/): framework docs, not a Hutch installer) | Hero/primary CTA must name the real path: run from source on Linux, requirements, then choose a model route |
| 2 | Download/availability mismatch | "Download" points to a release page or docs with no artifact | A real project issue reports releases can "ship empty" so "every 'Download' button ... leads users to a release with no binary" ([moollaza/nazar#42](https://github.com/moollaza/nazar/issues/42), open, 2026-08-29); another user could not find "Prebuilt Binaries" promised by docs ([meta/watchman#1299](https://github.com/meta/watchman/issues/1299), open, 2025-08-21) | Do not render a Download/Install action when the release manifest has no artifact for the platform; publish an explicit availability state and a last-checked date |
| 3 | Release mechanics assumed automatic | A GitHub release is text plus *optional* binary links; binaries are uploaded assets, not generated | GitHub docs: a release lets you "package software, along with release notes and links to binary files" ([GitHub Docs: About releases](https://raw.githubusercontent.com/github/docs/main/content/repositories/releasing-projects-on-github/about-releases.md): describes the mechanics; does not guarantee any asset exists) | Add a release-completeness check: a release without the expected artifact must not be linked as installable ([nazar#42](https://github.com/moollaza/nazar/issues/42) proposes exactly this guard) |
| 4 | Trust signal missing at the entry | Users weigh design quality, up-front disclosure, comprehensive/current content, and connection to the rest of the web | NN/g lists those four credibility factors from Nielsen's 1999 study and says the same factors still influence users ([NN/g: Trustworthiness in Web Design](https://www.nngroup.com/articles/trustworthy-design/): qualitative research summary, not a conversion statistic) | Next to the entry action: MIT license link, source repo, issue tracker, exact requirements, what is local vs what leaves the machine, and "development preview" status |
| 5 | Welcome/confirmation copy at the wrong time | First-run screen or banner greets a new user as "welcome back"; failure survives because the string is static | Real bugs: app first opened says "Welcome Back!" ([Jdrew001/closer-app#35](https://github.com/Jdrew001/closer-app/issues/35), open, 2022); new signup lands on "Welcome back, [Name]" and the name is truncated to its first word ([rsdouglas/proof#121](https://github.com/rsdouglas/proof/issues/121), closed, 2026-03-04); users ask to remove a recurring "welcome back" message ([soscripted/sox#315](https://github.com/soscripted/sox/issues/315), closed, 2018) | The greeting must be state-driven: first-run copy on a fresh state, returning copy only after a completed prior session; success banner only after the action that produced it |
| 6 | Notification/banner used decoratively | Banners are for important, not-directly-page content; success banners confirm an expected event; assertive alerts for time-critical messages | GOV.UK: a notification banner tells users "something that's not directly relevant to the thing they're trying to do on that page", with a green success variant and `role="alert"`/`role="region"` semantics ([GOV.UK notification banner](https://design-system.service.gov.uk/components/notification-banner/): design-system guidance, not Hutch-specific) | No "Welcome back" banner on first run; dismissible, non-persistent; never re-show a stale success after a later failure |
| 7 | Service-unavailable state resembles onboarding | Provider/local health fails, or the release manifest fetch fails, and the page renders an empty skeleton | GOV.UK's service-problem pattern uses a plain heading, "Try again later", and says what was saved ([GOV.UK: There is a problem with the service pages](https://design-system.service.gov.uk/patterns/problem-with-the-service-pages/)) | Provider-unavailable and manifest-unavailable states need explicit copy and a retry path, not a blank panel |
| 8 | Pricing/plan CTA the product cannot honour | A pricing table or "free forever" badge implies hosted/entitled service the local project does not provide | The brief says no pricing tiers; the repository's FAQ schema already states the software is free, with "no subscription, hosted tier or usage fees of its own" and that a hosted route "pays that provider" ([website/index.html:75-78](../../../website/index.html#L75-L78)); it also states "Hutch does not include hosted inference" ([website/index.html:94](../../../website/index.html#L94)) | Keep the FAQ wording; surface the scope near the CTA ("MIT software; provider usage billed by your provider"); do not add a pricing page/tiers |
| 9 | Locale/units/platform claims | "Works anywhere / minutes" implies localized, multi-platform support | W3C defines localization as more than translation: numeric, date/time, currency, keyboard-layout and collation adaptation ([W3C i18n: Localization vs. Internationalization](https://www.w3.org/International/questions/qa-i18n): definitions, not Hutch claims) | State the support matrix: Linux-first; English UI; supported Python/OS versions; avoid unqualified "minutes"/"worldwide" claims |
| 10 | Fake/borrowed social proof | Testimonials, stars or badges that the project cannot substantiate | Google's review-snippet docs exclude self-serving reviews of one's own business from review rich results ([Google Search Central: Review snippet](https://developers.google.com/search/docs/appearance/structured-data/review-snippet.md.txt): platform guidelines; it does not verify any review's honesty) | No invented testimonials, star counts, "trusted by", or benchmark rankings; link to the actual repo/issues instead |

## 3. What the repository already gets right (and where the boundary actually is)

Repository observations from the static site source (read 2026-10-29; Lead should confirm the deployed page matches):

- The page declares "Development preview" in the meta description and social metadata ([website/index.html:7](../../../website/index.html#L7), and the visible status chip at [website/index.html:445](../../../website/index.html#L445)).
- FAQ structured data states the free/MIT scope honestly, including that hosted inference is not included ([website/index.html:75-78,94](../../../website/index.html#L75-L78)).
- "MIT-licensed · open source · Linux" appears as a compact surface-level trust line ([website/index.html:300](../../../website/index.html#L300)); structured data repeats MIT and links the GitHub repo ([website/index.html:43-48](../../../website/index.html#L43-L48)).
- The head links a "Hutch desktop release manifest" as JSON ([website/index.html:8](../../../website/index.html#L8)) — availability is data-driven somewhere; whether the CTA consumes it is unverified.
- Explicitly honest content notes exist, e.g. "These examples are authored text, not generated previews" ([website/index.html:481](../../../website/index.html#L481)).

So the risk is not a dishonest FAQ; it is the **entry action and its immediate surroundings**: whether the first screen names source install, whether any "Download" affordance implies a package, whether the manifest can be empty, and whether first-run/banners tell the truth about a brand-new state. `website/site.js` was not inspected; CTA target/label and any welcome logic are open questions for the Lead.

## 4. Change inventory for the marketing site (docs-only proposals)

| Area | As found (repository source, 2026-10-29) | Change | Must NOT change |
|---|---|---|---|
| Signup/install entry | No hosted signup; entry action leads toward GitHub/source (exact label and target unverified) | Label the path: "Run from source on Linux" plus a 3-line prerequisite list (Python 3.11+, local server start, model route) and a link to the quickstart; add "what happens next" so the first dashboard screen is not a surprise | Do not add an email-capture signup, waitlist, or account creation to imitate SaaS |
| Pricing/availability CTA | No pricing tiers/card gate; MIT/free stated in FAQ data; release manifest linked | Add a compact "Availability" block: "Development preview. No installers published yet; run from source. Last checked <date>." Link GitHub Releases and the manifest; render a no-artifact state honestly | Do not add pricing tables, "free forever" badges, plan selectors, urgency, or countdowns |
| Trust microcopy near entry | License/repo links exist in structured data/footer; not tied to the entry action | Repeat next to the CTA: MIT license, source repo, issue tracker, data-flow one-liner (local by default; hosted model routes send content to the chosen provider), preview/no-warranty note; link the actual repo, not a badge image | Do not invent trust badges, security seals, testimonials, user counts, or independent "reviewed by" claims |
| Welcome/confirmation banner behaviour | Static site cannot know a returning visitor without client-side state; in-product first-run banner logic unverified | If the site adds any greeting, default to first-run copy; in-product: first-run copy on fresh state, returning copy only after a completed session, success banner only after the action, dismiss and never re-show stale success after failure | No "Welcome back" on first launch; no success banner before the action; no auto-dismissing error; no banner that blocks focus or overlaps a focused control |
| Copy that must match onboarding reality | FAQ says hosted inference is not included, preview status is stated | Add an "Onboarding steps" summary to the marketing/quickstart entry: (1) install from source, (2) start the local server, (3) choose/verify a model route (hosted key, local service, or provider login), (4) acknowledge provider/connection terms, (5) make a first request, (6) optionally create a bot, (7) optionally connect channels, (8) learn approvals. Mark exact steps TBD until the Lead verifies code | Do not imply one-click install, bundled models, hosted inference, or that channels work without tokens/QR pairing |
| Locale/units/platform claims | "Linux" is stated; English-only and version support unstated | Publish a short support matrix (OS/arch, Python version, UI language) and date-stamp availability claims; avoid unqualified time-to-value estimates | Do not claim Windows/macOS parity, localization, or unit/locale coverage that is not tested |
| Status/error surfaces | No service page; manifest may fail or be empty | Reuse GOV.UK's problem-page pattern for unavailable/empty states: plain heading, "Try again later", what was saved, contact/repo link ([GOV.UK pattern](https://design-system.service.gov.uk/patterns/problem-with-the-service-pages/)) | Do not present an empty release or failed manifest as "coming soon" success |

## 5. Copy-to-reality matrix (claim -> reality -> safe rule)

| Claim shape | Onboarding reality (TBD; Lead verifies) | Safe copy rule | Failure evidence |
|---|---|---|---|
| "Get started in minutes" | Source install + local server + model route + first request | Name the steps and prerequisites; time estimates only if measured and qualified | [nazar#42](https://github.com/moollaza/nazar/issues/42), [Tauri](https://v2.tauri.app/distribute/) |
| "Download the app" | No packaged installers published (brief) | Say "No installers published yet; run from source", or omit the action until an artifact exists | [watchman#1299](https://github.com/meta/watchman/issues/1299), [GitHub releases](https://raw.githubusercontent.com/github/docs/main/content/repositories/releasing-projects-on-github/about-releases.md) |
| "Free forever" | MIT software, but model usage has provider costs | "MIT-licensed software; hosted model usage is billed by your provider" — keep the FAQ's existing scoping | [website/index.html:75-78](../../../website/index.html#L75-L78) |
| "Private / local-first" | True only when a local route is used; hosted routes send content to the provider | Scope the claim and name the choice point; surface the data-flow note at the model step | [NN/g trust](https://www.nngroup.com/articles/trustworthy-design/) (up-front disclosure) |
| "Welcome back" | First-time user has no prior session | First-run wording by default; returning wording only after a completed prior session | [closer-app#35](https://github.com/Jdrew001/closer-app/issues/35), [proof#121](https://github.com/rsdouglas/proof/issues/121) |
| "Development preview" | Preview status is real and should temper warranty/support expectations | Keep it visible near the entry, not only in FAQ/meta | [website/index.html:7,445](../../../website/index.html#L7) |
| "Works on your computer" | Linux-first, Python 3.11+, local model service or provider account required | Publish requirements and support matrix; avoid "any computer" | [W3C i18n](https://www.w3.org/International/questions/qa-i18n) (scope of localization claims) |

## 6. Welcome/confirmation banner state machine (what "wrong time" means)

| Event | Allowed copy | Forbidden |
|---|---|---|
| First launch, empty state | "Welcome to Hutch. Install from source, start the server, choose a model route." | "Welcome back", fake progress, invented profile/name |
| Returning after completed onboarding | "Welcome back" (only if a completed-session marker exists) | Greeting a first-run user with it; showing it twice |
| Action succeeded (first request, bot created) | Success banner confirming exactly that action, dismissible | Success before completion; success that survives a later failure |
| Action failed / provider unavailable | Problem copy with retry/switch route; assertive announcement if blocking | Hiding the failure; rendering an empty success shell |
| Pairing code expired | "Code expired — generate a new one" | Infinite spinner; silently reusing the code |
| Server/manifest unavailable | "There is a problem… Try again later", what was saved | Blaming the user; showing onboarding steps that cannot run |

Semantics: success/status banners should be announced appropriately (`role="alert"` for important, `role="region"` for contextual) per [GOV.UK notification banner](https://design-system.service.gov.uk/components/notification-banner/); errors near the field per [NN/g error guidelines](https://www.nngroup.com/articles/error-message-guidelines/) and [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/).

## 7. Verification plan (docs-only, no production code)

1. Inventory every CTA/link in `website/index.html` and `website/site.js`; for each, record destination, expected state, and whether the destination exists today (GitHub Releases has no artifact, docs exists, manifest exists/empty).
2. Compare the entry copy against the actual first-run sequence the Lead verifies in code; produce a claim -> step matrix (as §5) with the real step names.
3. Check the release manifest path end-to-end: empty manifest, missing artifact, fetch failure. Screenshot each state at 375/768/1440 and record verdicts per [visual-validation.md](visual-validation.md).
4. Walk the banner state machine (§6) with fixtures: first run, returning, success, failure, stale success after failure, expired pairing.
5. Re-check trust microcopy at the entry: license, repo, requirements, data-flow, preview, last-checked date — all present and linked.
6. Confirm no analytics/tracking was added (brief says none), and no fake social proof, pricing, or account UI was introduced.
7. Record evidence under `docs/realignment/artifacts/<task>/` with `validation.json` rows (site screenshots, CTA matrix, link status, verdicts); only claim inspected links/screens.

## 8. Open questions for the Lead (code inspection)

- What is the actual primary CTA label and target today, and does `site.js` consume the linked release manifest ([website/index.html:8](../../../website/index.html#L8))?
- Does any "download" affordance render when the manifest is empty or the platform unsupported?
- Are there any welcome/confirmation banners in the dashboard (first-run vs returning), and what state decides them?
- What are the exact onboarding steps and required prerequisites (model route mandatory? channels optional? approval tutorial?) so site copy can match them?
- What OS/arch/Python versions and UI languages are actually supported, and is any of that stated near the entry?
- Is the existing FAQ/JSON-LD text deployed as written, or does the deployed page differ from repository source?

## 9. Entry-surface acceptance checklist (binary)

Each row is PASS or FAIL; missing evidence is FAIL, not partial. This is the marketing analogue of the binary visual gate in [visual-validation.md](visual-validation.md).

| # | Check | Evidence to record |
|---|---|---|
| 1 | The primary entry action names the real path (source install), not "download the app" | CTA label + destination screenshot; quickstart link status |
| 2 | Prerequisites are listed before the click (Linux, Python 3.11+, local server start, model route) | Rendered text at 375/768/1440 |
| 3 | Availability is explicit and dated; empty/no-artifact release renders honestly, never as "Download" | Manifest/release state screenshots; last-checked date visible |
| 4 | Trust row adjacent to entry: MIT license, repo, issue tracker, preview status, data-flow note | One screenshot of the entry block; links resolve |
| 5 | No pricing tiers, card gate, account/waitlist capture, urgency or countdown UI | Link/CTA inventory from `website/index.html` + `site.js` |
| 6 | No fabricated social proof or unverified numeric claims (testimonials, stars, "trusted by", benchmarks, install-time promises) | Search of page text/schema for such claims; each remaining number has a source |
| 7 | First-run vs returning copy is state-driven; "Welcome back" cannot appear on a first run | Banner state-machine evidence (§6) |
| 8 | Success banners only after the action; failures carry retry/switch-route; expired pairing says expired and offers regenerate | State screenshots + validation.json rows |
| 9 | Locale/units/platform claims are scoped to what is tested; English UI and Linux-first are stated | Support-matrix screenshot; no "any device/worldwide" phrasing |
| 10 | Every claim that could change (availability, versions, pricing) carries a date or links to a single dated source | Page copy audit |

## Sources (all opened 2026-10-29 unless marked)

| URL | Title | Type | Supports |
|---|---|---|---|
| https://www.nngroup.com/articles/trustworthy-design/ | NN/g: Trustworthiness in Web Design: 4 Credibility Factors | secondary (research) | §2, §3, §5 |
| https://www.nngroup.com/articles/web-form-design/ | NN/g: Website Forms Usability: Top 10 Recommendations | secondary (research) | §2 (entry/form trust, labels, placeholders) |
| https://www.nngroup.com/articles/error-message-guidelines/ | NN/g: Error-Message Guidelines | secondary (research) | §6 |
| https://design-system.service.gov.uk/components/notification-banner/ | GOV.UK Design System: Notification banner | primary (design system) | §2, §6 |
| https://design-system.service.gov.uk/patterns/problem-with-the-service-pages/ | GOV.UK Design System: There is a problem with the service pages | primary (design system) | §2, §4 |
| https://design-system.service.gov.uk/components/error-message/ | GOV.UK Design System: Error message | primary (design system) | §6 |
| https://v2.tauri.app/distribute/ | Tauri: Distribute | primary (framework docs) | §2, §5 |
| https://raw.githubusercontent.com/github/docs/main/content/repositories/releasing-projects-on-github/about-releases.md | GitHub Docs: About releases | primary (vendor docs) | §2, §5 |
| https://github.com/moollaza/nazar/issues/42 | "releases can ship without a DMG" (real issue) | anecdote | §2, §3, §5 |
| https://github.com/meta/watchman/issues/1299 | "Prebuilt Binaries Missing" (real issue) | anecdote | §2, §5 |
| https://github.com/Jdrew001/closer-app/issues/35 | "Welcome Back!" on first app open (real issue) | anecdote | §2, §5 |
| https://github.com/rsdouglas/proof/issues/121 | "Welcome back" on first login + first-word name truncation (real issue) | anecdote | §2, §5 |
| https://github.com/soscripted/sox/issues/315 | "Remove the welcome back message" (real issue) | anecdote | §2 |
| https://www.w3.org/International/questions/qa-i18n | W3C i18n: Localization vs. Internationalization | primary (standard) | §2, §4, §5 |
| https://developers.google.com/search/docs/appearance/structured-data/review-snippet.md.txt | Google Search Central: Review snippet structured data (self-serving reviews) | primary (vendor guidelines) | §2 |
| https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking | FTC: Endorsement Guides FAQ | **unverified** — fetch returned HTTP 403; no claim is based on it | §2 caution only |
| https://baymard.com/lists/cart-abandonment-rate | Baymard: Cart Abandonment Rate Statistics | **unverified** — page opened but body was not retrievable in this reader (navigation only, JS/truncation); not cited | none |
| website/index.html (local repo file) | Hutch repository: static marketing site source (inspected 2026-10-29) | repo primary | §3, §4, §5 |

**Not in scope, confirmed against the brief only (Lead verifies code):** document upload, liveness check, e-signature, KYC/identity verification, hosted sign-up, pricing tiers, card gate. If any of these appear in code, the fintech boundary classes would need re-adding; nothing found supports that.
