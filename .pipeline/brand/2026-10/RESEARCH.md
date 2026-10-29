# Run 1 - Source verification and gap fill of the Phase 0 plan research

Artifact type: review / gap-fill of an existing plan. Plan under review: `docs/brand/00-PLAN.md`
on branch `brand/plan` (section R at lines 234-560, gap register C at 903-943, unknowns D at 944-978).
This file records what fetched sources say as of **2026-10-28** and how that compares to the plan's
and `docs/brand-assets.md`'s claims. It is not new strategy.

## Method and scope

- Read-only inspection of the plan via `git show brand/plan:docs/brand/00-PLAN.md` (targeted line
  ranges and keyword grep) and of `docs/brand-assets.md` (lines 1-60) to pin the exact claims each
  citation is asked to support.
- PART 1: exactly one `web_fetch` attempt per priority URL (18 URLs). For each, status, a one-line
  summary of what the fetched body says, and a comparison verdict against the plan or
  `docs/brand-assets.md`: CONFIRMED / CHANGED / CONTRADICTS / NOT STATED, or UNVERIFIED where the
  fetched body did not contain the source text.
- PART 2: gap research limited to 4 additional page fetches, spent on U17 (X card dimensions via the
  redirect target and one alternate path; the Facebook leg was the Part 1 fetch) and U23 (NN/g
  5-second test page and a first-click source).
- Extraction method: HTML bodies were stripped of script/style/tags and scanned for the specific
  claim keywords. `web_fetch` truncates large bodies at 100,000 characters; several vendor docs sites
  serve client-rendered shells in which no article text is present. Where the article body was absent,
  the verdict is UNVERIFIED with that reason - no content is inferred.
- Status meanings here describe the fetcher's result: LIVE (HTTP 200 with extractable body),
  LIVE (shell) (HTTP 200 but no article text in the fetched body), REDIRECT (redirect not followed by
  the fetcher), 404, 403, PAYWALLED.

## Verification table

| # | URL | Status (2026-10-28) | What it says (from fetched body) | Comparison verdict |
|---|---|---|---|---|
| 1 | [developers.google.com/search/docs/appearance/favicon-in-search](https://developers.google.com/search/docs/appearance/favicon-in-search) | LIVE (shell) - HTTP 200, body truncated at 100,000 chars, no article text after script/style stripping ("favicon" absent) | Page reachable; requirement text (stable crawlable favicon URL, 16/32px guidance, doc update date) not present in the fetched body | UNVERIFIED at execution time. Plan R.4/C07 claim ("stable crawlable URL is a Google Search requirement, doc updated 2026-10-27") neither confirmed nor contradicted by this fetch |
| 2 | [docs.github.com .../customizing-your-repositorys-social-media-preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview) | LIVE (shell) - HTTP 200, body truncated at 100,000 chars, "1280"/"640"/"social preview" absent | Page reachable; the 1280x640, <1 MB, JPEG/PNG spec text not present in the fetched body | UNVERIFIED at execution time. Plan R.4 row and `docs/brand-assets.md:52` (1280x640, manual upload) not re-confirmed by this fetch |
| 3 | [ogp.me](https://ogp.me/) | LIVE - HTTP 200, full body (23,128 chars) | og:title, og:type, og:image, og:url are the four required properties; og:image has optional structured properties (og:image:url/secure_url/type/width/height/alt); "If the page specifies an og:image it should specify og:image:alt"; no pixel dimensions appear anywhere in the document | CONFIRMED. Plan R.4 claim "OG no fixed pixel size in OGP; use 1200x630 PNG" matches: OGP defines no sizes, so 1200x630 is a convention, not an OGP requirement. The og:image:alt recommendation is new supporting detail |
| 4 | [developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image](https://developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image) | REDIRECT - cross-origin redirect to `https://docs.x.com`, not followed automatically by the fetcher | Nothing; no body retrieved | UNVERIFIED. Plan U17 ("X/Facebook card dimensions unverified, sources blocked") still holds; the URL host has migrated to docs.x.com (see Gap research U17 for follow-up fetches) |
| 5 | [developers.facebook.com/docs/sharing/webmasters/](https://developers.facebook.com/docs/sharing/webmasters/) | LIVE (shell) - HTTP 200, body truncated at 100,000 chars; extracted text is Facebook app chrome (CSS custom properties); "og:image"/"1200"/"630" absent | Page reachable; the Open Graph image dimension guidance not present in the fetched body | UNVERIFIED at execution time. Plan U17 remains open for the Facebook leg |
| 6 | [developer.apple.com/design/human-interface-guidelines/app-icons](https://developer.apple.com/design/human-interface-guidelines/app-icons) | LIVE (shell) - HTTP 200, body not truncated (18,047 chars) but contains no article text; "1024"/"alpha"/"layered"/"Icon Composer" all absent (client-rendered page) | Page reachable; icon size/transparency/variant guidance not present in the fetched body | UNVERIFIED at execution time. Plan R.4 iOS row and U16 ("no-alpha rule absent from current HIG/review text") could not be re-checked; U16 stays open as written |
| 7 | [developer.android.com/distribute/google-play/resources/icon-design-specifications](https://developer.android.com/distribute/google-play/resources/icon-design-specifications) | LIVE (shell) - HTTP 200, body truncated at 100,000 chars; "512"/"32-bit"/"sRGB"/"1 MB" absent | Page reachable; the Play listing icon spec not present in the fetched body | UNVERIFIED at execution time. Plan R.4 Google Play row (512x512, 32-bit PNG, sRGB, <=1 MB, 30% corner mask) not re-confirmed |
| 8 | [web.dev/articles/maskable-icon](https://web.dev/articles/maskable-icon) | LIVE - HTTP 200, article body extracted | "The maskable icon specification includes a standardized minimum safe zone... the important parts of your icon, such as your logo, must be within a circular area in the center of the icon with a radius equal to 40% of the icon width. The outer 10% edge might be cropped on some platforms." Maskable icons require "an opaque image with some padding"; Chrome DevTools can show the minimum safe area | CONFIRMED. Plan R.4/C06 claim "centred circle of radius 40% of icon size (80% diameter)" and "opaque padding required" match the source (40% radius = 80% diameter) |
| 9 | [openfontlicense.org/documents/OFL-FAQ.txt](https://openfontlicense.org/documents/OFL-FAQ.txt) | LIVE - HTTP 200, full text (61,615 chars); header: "OFL FAQ... Version 1.1-update7 - November 2023" | 1.1: OFL fonts may be used "to create logos or other graphics" with no additional permission; 1.1.1: that does not restrict the license/distribution of the resulting artwork. 1.12: embedding in a document is allowed, full or subset. 1.13: embedding does not change the license of the document; the OFL requirement "does not apply to any document created using the fonts and their derivatives" | CONFIRMED for the three numbered items the plan cites (1.1, 1.12, 1.13). Plan C01's remaining sub-claims (fonts cannot be sold alone; OFL notices must travel with redistributed files; RFN restriction applies only if one is declared) are in the same fetched document but were not separately extracted in this pass - NOT RE-EXTRACTED, not contradicted |
| 10 | [raw.githubusercontent.com/vercel/geist-font/main/LICENSE.txt](https://raw.githubusercontent.com/vercel/geist-font/main/LICENSE.txt) | LIVE - HTTP 200, full text (4,368 chars) | "Copyright (c) 2023 Vercel, in collaboration with basement.studio / This Font Software is licensed under the SIL Open Font License, Version 1.1", followed by the full OFL 1.1 text (26 February 2007). No Reserved Font Name is specified after the copyright statement; the text defines RFN as "any names specified as such after the copyright statement(s)" | CONFIRMED. Matches plan C01 and `docs/brand-assets.md:39` (OFL 1.1, copyright 2023 Vercel in collaboration with basement.studio); consistent with the plan's "no Reserved Font Name" reading |
| 11 | [uspto.gov/trademarks/trademark-fee-information](https://www.uspto.gov/trademarks/trademark-fee-information) | LIVE (shell) - HTTP 200, body truncated at 100,000 chars; "350"/"per class"/"surcharge"/"insufficient"/"free-form" absent | Page reachable; the fee schedule text not present in the fetched body | UNVERIFIED at execution time. Plan R.3 figures (USPTO $350/class plus $100 insufficient-information and $200 free-form-description surcharges) are not re-confirmed; the plan's own "dated official fee inputs... confirm at filing time" caveat governs |
| 12 | [nclpub.wipo.int/enfr/](https://nclpub.wipo.int/enfr/) | LIVE - HTTP 200, full body (40,190 chars) | Nice Classification publication tool; edition-version picker lists 13-2027, 13-2026, 12-2025, 12-2024, 12-2023, 11-2022 and older; class index 1-45; footer "NCLPUB v5.0.3 Last modified: 2026.06.04" | CONFIRMED for plan C03/R.3 claim "Nice 13-2026, updated 2026-06-04" (13-2026 present; last-modified 2026.06.04). CHANGED context: a 13-2027 edition is now also listed; the governing edition at filing time is a filing-time confirmation, per the plan |
| 13 | [python.org/psf/trademarks/](https://www.python.org/psf/trademarks/) | LIVE - HTTP 200, full body (49,657 chars) | PSF Trademark Usage Policy: "'Python' and the Python logos are trademarks or registered trademarks of the Python Software Foundation, used by ... with permission from the Foundation"; classes of permitted use (free distribution allowed; company-name use needs prior written permission); the policy text itself is CC0 | CONFIRMED as the Python leg of plan C21's OSS trademark-separation model: a trademark policy maintained separately from the language's open-source copyright licence |
| 14 | [foundation.rust-lang.org/policies/logo-policy-and-media-guide/](https://foundation.rust-lang.org/policies/logo-policy-and-media-guide/) | REDIRECT - cross-origin redirect to `http://rustfoundation.org` (note: http scheme in the redirect target), not followed automatically | Nothing; no body retrieved | UNVERIFIED. Plan C21's Rust leg ("Python, Rust and Go show the separation model") not re-verified from source; the cited URL no longer serves content directly and needs re-citing |
| 15 | [go.dev/brand](https://go.dev/brand) | LIVE - HTTP 200, full body (39,117 chars) | "The Go trademark and the Go Logo ... collectively, the 'Go Trademarks' - are trademarks of Google and are treated separately from the copyright license grants contained in the BSD-licensed Go repositories"; nominative fair-use rules; authorization is non-transferable; the Gopher mascot is Creative Commons 4.0 Attribution (created by Renee French) | CONFIRMED - explicit "treated separately from the copyright license grants" language, the clearest of the three C21 examples |
| 16 | [anthropic.com/press-kit](https://www.anthropic.com/press-kit) | REDIRECT - cross-origin redirect to `https://www-cdn.anthropic.com`, not followed automatically | Nothing; no body retrieved | UNVERIFIED. `docs/brand-assets.md:13` cites this URL as the source of "Anthropic symbol in Ivory"; at execution time the URL is not directly fetchable and the claim cannot be re-verified from the cited source |
| 17 | [openrouter.ai/brand](https://openrouter.ai/brand) | LIVE - HTTP 200, article body extracted (page title "Brand Assets - Official OpenRouter Logos") | "Every configuration of the OpenRouter mark, ready to use. SVG scales anywhere; PNGs are exported at 2x. Please don't stretch, recolor, or remix the marks." Matrix: Horizontal (primary lockup), Vertical, Square canvas, and Glyph ("The mark alone - avatars, favicons, small sizes"); colourways Grape and Ink for light backgrounds, Volt and Cloud for dark backgrounds | CONFIRMED. `docs/brand-assets.md:14` ("Volt glyph for dark backgrounds. Do not stretch, recolor, or remix.") matches the source: Volt is the dark-background colourway, Glyph is the small-size form, and the no-alteration instruction is verbatim. Also supports plan C19 (marks must not be restyled) |
| 18 | [nngroup.com/articles/5-second-usability-test/](https://www.nngroup.com/articles/5-second-usability-test/) | 404 - NN/g serves its own "Profile Page Not Found (404)" page | No such article exists at this path | CONTRADICTS the URL as written: this is not a citable NN/g source. Plan R.2 cites the different, live URL `https://www.nngroup.com/videos/5-second-usability-test/` (verified live in gap research below). Plan C23/U23's stance ("the 5-second protocol lacked a verifiable primary source") is unchanged |

## Changed or dead sources

- **X developer docs host migration (plan U17).** The `developer.x.com` deep link now cross-origin
  redirects to `https://docs.x.com`; the fetcher does not follow cross-origin redirects. Both
  docs.x.com paths attempted in gap research returned 404 (see below). The old deep link should not be
  cited as a live source without a rendering-browser re-check.
- **NN/g 5-second test article URL (offered in this task's brief) is dead (404).** The plan's own
  citation, `https://www.nngroup.com/videos/5-second-usability-test/`, is live (200). Any downstream
  citation should use the videos page, not an /articles/ URL.
- **Rust logo policy URL (plan C21).**
  `foundation.rust-lang.org/policies/logo-policy-and-media-guide/` now redirects (to
  `http://rustfoundation.org`, http scheme as reported by the fetch error). The Rust leg of the C21
  claim is unverified until re-cited from the canonical page.
- **Anthropic press-kit URL (`docs/brand-assets.md:13`).** Redirects to `www-cdn.anthropic.com`; not
  fetchable at the cited URL. The "Anthropic symbol in Ivory" sourcing note needs a canonical-URL
  refresh before Phase 7 relies on it.
- **WIPO Nice edition drift (plan C03).** The plan cites Nice 13-2026 (updated 2026-06-04), which is
  confirmed as the current default view; the publication tool now also lists a 13-2027 edition.
- **Pattern, not death: six citations returned HTTP 200 with no article text** (Google favicon, GitHub
  social preview, Facebook sharing/webmasters, Apple HIG app-icons, Android Play icon specs, USPTO fee
  information). These pages are alive in a browser but their content was client-rendered or beyond the
  fetcher's 100,000-character body truncation. They are recorded as UNVERIFIED at execution time, not
  as changed or dead.

## Gap research (U17, U23)

### U17 - X/Facebook card dimensions

Status: **still unreachable as of 2026-10-28.**

- `https://developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image`
  -> REDIRECT to `https://docs.x.com` (cross-origin, not followed).
- `https://docs.x.com/x-for-websites/cards/overview/summary-card-with-large-image` -> 404.
- `https://docs.x.com/x-for-websites/cards/overview/cards-with-large-image` -> 404.
  (Both docs.x.com 404 bodies were client-rendered shells; no card-dimension text present.)
- Facebook leg: `https://developers.facebook.com/docs/sharing/webmasters/` -> HTTP 200 but only the
  Facebook app shell was returned; no og:image dimension guidance extractable.
- What U17 gains this run: the OG protocol source itself (ogp.me, row 3) is now fully verified - OGP
  makes og:image a required property, defines optional og:image:width/height/alt, recommends alt when
  og:image is present, and specifies **no** pixel dimensions. The plan's framing ("OGP has no fixed
  pixel size; 1200x630 is a working convention") is therefore CONFIRMED at the protocol level, while
  the X- and Facebook-platform-specific dimension recommendations remain UNVERIFIED.

### U23 - 5-second test and first-click sources

- The article URL offered in this task's brief,
  `https://www.nngroup.com/articles/5-second-usability-test/`, returns 404 - it is not a citable
  source.
- The plan's cited page, `https://www.nngroup.com/videos/5-second-usability-test/`, is **live** (HTTP
  200, page title "5-Second Usability Test (Video) - NN/g"). This is a primary Nielsen Norman Group
  page naming the method, so a citable primary source for the method's existence now verifies.
- However, the fetched portion of that page contains only site navigation/title text; no protocol
  parameters (question script, exposure timing, sample size, scoring) were extractable from the
  shell, and NN/g gates the video content itself.
- `https://www.nngroup.com/articles/first-click-testing/` -> 404 (the first-click method article could
  not be sourced at that path either).
- Net: U23 is **partially closed** - the method-existence source verifies live; a citable source for
  the method's parameters is **still unreachable as of 2026-10-28**. Plan C23's position (use
  pre-registered first-click/first-run tasks; treat the 5-second test as a diagnostic, not a pass/fail
  gate; predictive validity unverified) is not contradicted by anything found this run.

## What this does NOT establish

- **No legal clearance.** Nothing here clears the name "Hutch", any proposed mark, or any tagline; no
  clearance opinion, non-infringement conclusion, or distinctiveness assessment is expressed or
  implied. The plan's [COUNSEL] flags and its own stop conditions (including C04 similarity search)
  are untouched.
- **No legal advice.** All rows are source snapshots recorded for a planning artifact.
- **Fees and classification are not settled.** USPTO fee figures remain UNVERIFIED from source this
  run; the plan's requirement to confirm official fees and the governing Nice edition at filing time
  stands.
- **Web sources are point-in-time snapshots** fetched 2026-10-28 through a single, non-rendering
  fetcher with a 100,000-character body truncation and no cross-origin redirect following. "LIVE
  (shell)" means the page answered 200 but its article text was not in the fetched body - the live page
  in a browser may differ from, or may contain text this pipeline never saw. Statuses describe the
  fetcher's result, not site availability.
- **No repository or platform state was verified**: GitHub repository social-preview settings, App
  Store Connect upload behaviour, Google Search Console favicon treatment, and trademark register
  search results are all out of scope and remain as the plan states them.

## Evidence

All operations were read-only except the creation of this file. Commands run (working directory
`/home/kevina/CodingProjects/hutch`):

```bash
git show brand/plan:docs/brand/00-PLAN.md | sed -n '234,560p'
git show brand/plan:docs/brand/00-PLAN.md | sed -n '944,990p'
git show brand/plan:docs/brand/00-PLAN.md | grep -n -i -E 'favicon|1280|og:image|ogp|1024|maskable|OFL|Geist|USPTO|Nice|press-kit|openrouter|anthropic|5-second|summary-card|twitter|card'
git show brand/plan:docs/brand/00-PLAN.md | sed -n '330,360p;398,430p'
ls -la .pipeline/brand/2026-10/
```

File read: `docs/brand-assets.md` lines 1-60 (via read tool).

Fetch list, one attempt each, all accessed 2026-10-28 via `web_fetch`:

| Group | URL | Result |
|---|---|---|
| Part 1 | https://developers.google.com/search/docs/appearance/favicon-in-search | 200, shell/truncated |
| Part 1 | https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview | 200, shell/truncated |
| Part 1 | https://ogp.me/ | 200, full |
| Part 1 | https://developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image | redirect to https://docs.x.com, not followed |
| Part 1 | https://developers.facebook.com/docs/sharing/webmasters/ | 200, shell/truncated |
| Part 1 | https://developer.apple.com/design/human-interface-guidelines/app-icons | 200, shell only |
| Part 1 | https://developer.android.com/distribute/google-play/resources/icon-design-specifications | 200, shell/truncated |
| Part 1 | https://web.dev/articles/maskable-icon | 200, article body extracted |
| Part 1 | https://openfontlicense.org/documents/OFL-FAQ.txt | 200, full text |
| Part 1 | https://raw.githubusercontent.com/vercel/geist-font/main/LICENSE.txt | 200, full text |
| Part 1 | https://www.uspto.gov/trademarks/trademark-fee-information | 200, shell/truncated |
| Part 1 | https://nclpub.wipo.int/enfr/ | 200, full |
| Part 1 | https://www.python.org/psf/trademarks/ | 200, full |
| Part 1 | https://foundation.rust-lang.org/policies/logo-policy-and-media-guide/ | redirect to http://rustfoundation.org, not followed |
| Part 1 | https://go.dev/brand | 200, full |
| Part 1 | https://www.anthropic.com/press-kit | redirect to https://www-cdn.anthropic.com, not followed |
| Part 1 | https://openrouter.ai/brand | 200, article body extracted |
| Part 1 | https://www.nngroup.com/articles/5-second-usability-test/ | 404 |
| Part 2 (U17) | https://docs.x.com/x-for-websites/cards/overview/summary-card-with-large-image | 404 |
| Part 2 (U17) | https://docs.x.com/x-for-websites/cards/overview/cards-with-large-image | 404 |
| Part 2 (U23) | https://www.nngroup.com/videos/5-second-usability-test/ | 200, title extracted |
| Part 2 (U23) | https://www.nngroup.com/articles/first-click-testing/ | 404 |

Extraction detail: HTML bodies were stripped of script/style elements and tags, then scanned for the
claim keywords named per row in the verification table. Bodies reported `truncated: true` were cut by
the fetcher at exactly 100,000 characters; in those cases the article text was not located within the
returned portion.

## Recommended follow-ups for Run 2

1. Re-verify the six LIVE (shell) citations with a rendering browser (or manual capture with date):
   Google favicon guidance, GitHub social preview spec, Apple HIG app-icons, Android Play icon
   specifications, USPTO trademark fee information, Facebook sharing/webmasters. Until then their plan
   rows (R.4, C07, C05/U16, C29, U17) are sourced only as of Phase 0.
2. U17: keep X and Facebook platform dimension claims out of decision paths. Re-cite X card specs from
   docs.x.com via a rendering session if Phase 7 needs them; the old developer.x.com deep links do not
   resolve.
3. U23: cite `https://www.nngroup.com/videos/5-second-usability-test/` (live 2026-10-28) as the NN/g
   method page; drop the 404 `/articles/5-second-usability-test/` form. A parameter-level method source
   is still missing, which supports keeping C23's "diagnostic, not gate" stance.
4. Refresh two third-party citations before Phase 7 relies on them: the Rust logo policy URL
   (foundation.rust-lang.org now redirects to rustfoundation.org) and the Anthropic press-kit URL
   (`docs/brand-assets.md:13`, now redirecting to www-cdn.anthropic.com).
5. C03: note in the plan that the WIPO Nice tool now lists edition 13-2027 alongside the cited
   13-2026; confirm the governing edition at filing time together with the fee re-confirmation the plan
   already requires.
6. Cheap verified addition available from this run: ogp.me recommends og:image:alt whenever og:image
   is set (row 3); `docs/brand-assets.md:51` records alt/width/height already present on the marketing
   card, so this is a checklist confirmation for Phase 7 rather than new work.
7. [Lead follow-up, same date] Two redirect legs were retried directly by the lead after worker
   follow-up #4: (a) `https://rustfoundation.org/policies/logo-policy-and-media-guide/` (the
   redirect target's HTTPS host) returned 200 with the article text "Rust Language Trademark Policy",
   including "The Rust and Cargo logos (bitmap and vector) are owned by the Rust Foundation and
   distributed under the terms of the Creative Commons Attribution license (CC-BY)" - so the plan's
   C21 Rust leg (trademark policy maintained separately from the open-source copyright licence) is
   now VERIFIED at execution time, and the canonical citation to use is the rustfoundation.org URL.
   Note: page body was truncated by the fetcher (11,970 chars returned); only the quoted Art License
   section and page structure were read. (b) The Anthropic leg remains OPEN: the CDN redirect target
   `https://www-cdn.anthropic.com/press-kit` returns 404, `https://www.anthropic.com/press`
   returns 404, and `https://www.anthropic.com/news` returns 200 (Newsroom) with no press-kit
   reference found in the fetched body. `docs/brand-assets.md:13` therefore still cites a source
   that cannot be re-verified as of 2026-10-28; keep this open for Phase 7 and prefer a source that
   can be re-fetched before relying on it.
