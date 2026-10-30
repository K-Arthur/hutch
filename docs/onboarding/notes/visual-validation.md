# Visual validation: baseline-first captures, state matrix, and what pixel diffs miss

**Access date: 2026-10-29.** Docs-only research note for the first-run onboarding surface of Hutch (locally served dashboard / desktop host). Onboarding is desktop-first but also used at phone widths; exact routes and step order are TBD and must be verified by the Lead against code. In scope here: model-route selection (hosted provider key, local model service such as Ollama, provider login), provider/connection acknowledgement, first request and first useful output, bot creation (name, model, response style), channel connection (Telegram bot token, phone pairing by QR), and learning the approval model. **Not in scope for this product:** document upload, liveness, signature, or KYC identity verification. The program brief lists no such steps; a checklist built for fintech KYC would misdirect effort. That negative finding is based on the brief only; the Lead confirms it against code.

## 1. Why a screenshot diff alone is insufficient

- **A diff compares one stable frame, not a timeline.** Playwright waits until two consecutive page screenshots yield the same result before comparing, so transient paints are invisible by construction ([Playwright page assertions](https://playwright.dev/docs/api/class-pageassertions): "wait until two consecutive page screenshots yield the same result"; it does not score visual stability over time).
- **Animations are disabled by default.** `toHaveScreenshot` defaults to `animations: "disabled"`: finite animations are fast-forwarded, infinite ones are cancelled for the capture ([Playwright](https://playwright.dev/docs/api/class-pageassertions)). Motion/transition regressions therefore cannot show up unless a test explicitly allows animations.
- **Layout shift is a temporal metric, not a snapshot property.** CLS measures unexpected movement over the page lifetime; shifts within 500 ms of user input are excluded via `hadRecentInput` ([web.dev CLS](https://web.dev/articles/cls): good threshold 0.1 at the 75th percentile; the article does not define a screenshot test). Chrome DevTools needs the **Layout Shift Regions** overlay to show *where and when* areas shift in purple ([DevTools rendering reference](https://developer.chrome.com/docs/devtools/rendering/performance.md.txt): the tool animates the shifts; a still screenshot cannot).
- **Tolerance knobs intentionally hide small changes.** Pixelmatch `threshold` tolerates perceived colour difference (default 0.2) and `maxDiffPixels`/ratio swallow whole regions; `mask` and `stylePath` replace dynamic areas entirely ([Playwright visual comparisons](https://playwright.dev/docs/test-snapshots): options documented; the docs do not warn that this can mask layout shift).
- **Cross-platform rendering is genuinely different.** Snapshot names include browser and platform because "screenshots differ between browsers and platforms due to different rendering, fonts and more" ([Playwright](https://playwright.dev/docs/test-snapshots)). Disabling subpixel text and font hinting removes common noise but "does not make macOS and Linux render text identically, so capture your screenshots in a single environment, usually CI" ([Argos CI](https://argos-ci.com/docs/learn/reliability-and-flakiness/flaky-tests/stabilize-text-rendering): vendor guidance; it does not eliminate cross-browser differences).
- **A Chromium-only baseline set leaves other engines unverified.** Since baselines are browser+platform keyed, a Linux/Chromium project covers that combination only; treat Firefox/WebKit as unverified unless separately captured (inference from Playwright docs, not a documented guarantee).
- **DOM/unit tests cannot see paint at all.** jsdom "does not have the capability to render visual content"; layout is expressly out of scope, with zeros returned for many layout-related properties ([jsdom README](https://github.com/jsdom/jsdom#unimplemented-parts-of-the-web-platform): no layout engine, no painting).
- **Accessibility failures are visual and common.** The WebAIM Million 2026 found 95.9% of home pages had detected WCAG 2 failures, 56.1 detected errors per page, low-contrast text on 83.9%, missing form labels on 51% and empty buttons on 30.6% ([WebAIM](https://webaim.org/projects/million/): automated WAVE analysis of rendered DOM; the report itself says automated tools cannot detect everything). Playwright's own accessibility page agrees: "many accessibility problems can only be discovered through manual testing" ([Playwright accessibility testing](https://raw.githubusercontent.com/microsoft/playwright/main/docs/src/accessibility-testing-js.md)).

## 2. Baseline-first method: live screenshots, binary verdict, then regression tooling

Do not add visual-regression tooling first. Tooling will faithfully freeze whatever exists, including the bugs, because Playwright's first run "will generate reference screenshots" and you are told to "commit this directory ... and review any changes to it" ([Playwright](https://playwright.dev/docs/test-snapshots)). The baseline is the decision, so judge it first.

1. **Start the real local app from source** (backend + dashboard) and reach onboarding states with fixture data, not by unit-mocking HTML. Where available, use the repo's unlinked preview harness documented at [docs/prompts/prompt-4b-surface-report.md:69](../../prompts/prompt-4b-surface-report.md) (`/static/redesign-preview.html?fixtures=1`; Lead verifies it still exists).
2. **Freeze time and data.** Use Playwright's Clock API (`setFixedTime`, `install`, `pauseAt`, `fastForward`) so date/time-dependent UI is deterministic ([Playwright clock](https://playwright.dev/docs/clock)). Use 1-2 realistic fixtures per state, including deliberately hostile strings.
3. **Capture one screenshot per required state per required viewport** (sections 4-5). Capture the viewport, and also the scrolled position wherever sticky headers/footers or dialogs can cover a focused control (see WCAG 2.4.11 below).
4. **Open every image and record a binary verdict**: APPROVED or NEEDS WORK, with at most 3 findings. "Generated" is not "reviewed"; repo practice already separates computed checks from the human judgement of the opened screenshots ([docs/qa/shape-and-background-review.md:69-71](../../qa/shape-and-background-review.md)).
5. **Record evidence** under `docs/realignment/artifacts/<task>/` with a `validation.json` row per state: `state`, `viewport`, `artifact`, `verdict`, `finding`, `source_commit`, `reviewer`. This matches the repo's documented capture convention ("three-viewport UI captures with overflow 0, validation.json", [docs/file-formats.md:67](../../file-formats.md); captures at 320/360/768/1440 in [docs/realignment/dynamic-workflows.md:265](../../realignment/dynamic-workflows.md)).
6. **Only then adopt tooling, for APPROVED states only:** Playwright `toHaveScreenshot` on chromium-linux, fixed clock, animations disabled, a committed baseline directory, and masks limited to genuinely dynamic regions (spinner, live clock). Treat `--update-snapshots` as a code review of the baseline, not a fix ([Playwright](https://playwright.dev/docs/test-snapshots): update flag and the instruction to review baseline changes).
7. **Keep the binary gate for new states:** a first-run state with no judged screenshot is NEEDS WORK, not "covered by CI".

Evidence lanes: `tests/e2e/` and full browser runs are excluded from the fast lane by [AGENTS.md](../../../AGENTS.md); decide explicitly which visual checks run pre-PR and which run nightly, and never claim a browser check that was not actually run ([docs/prompts/prompt-2-icon-pipeline.md:45](../../prompts/prompt-2-icon-pipeline.md)).

## 3. Breakpoints to capture

| Width (CSS px) | Role | Evidence / note |
|---|---|---|
| 320 | Reflow floor and 400% zoom equivalent | WCAG 1.4.10 requires no two-dimensional scrolling for vertical content at a width equivalent to 320 CSS px (= 1280 at 400% zoom) ([W3C](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html)). Lead should confirm 320 still renders the dashboard shell. |
| 375 | Required phone baseline | Program requirement; closest widely used phone logical width. StatCounter's Sep 2026 mobile table lists 414x896 (13.35%) then 360x800, 384x832, 390x844 (6.05%) ([StatCounter mobile](https://gs.statcounter.com/screen-resolution-stats/mobile/worldwide): screen resolutions, not CSS widths, so use as a cluster indicator only). |
| 390 | Extra phone state (repo responsive baseline) | 390x844 is a top-6 mobile resolution ([StatCounter mobile](https://gs.statcounter.com/screen-resolution-stats/mobile/worldwide)); 390 also appears in repo responsive work. |
| 768 | Required tablet baseline | 768x1024 was the most common tablet resolution in Sep 2026 at 8.09% ([StatCounter tablet](https://gs.statcounter.com/screen-resolution-stats/tablet/worldwide)). Bootstrap's `md` starts at 768px and Tailwind's `md` is 48rem ([Bootstrap](https://getbootstrap.com/docs/5.3/layout/breakpoints/); [Tailwind theme](https://raw.githubusercontent.com/tailwindlabs/tailwindcss/main/packages/tailwindcss/theme.css)). |
| 900 | Extra repo responsive state | Repo convention; no external standard claims this width. Use as "tablet landscape / narrow desktop" transition probe. |
| 1024 | Extra repo responsive state | Tailwind `lg` = 64rem = 1024px ([Tailwind theme](https://raw.githubusercontent.com/tailwindlabs/tailwindcss/main/packages/tailwindcss/theme.css)). |
| 1440 | Required desktop baseline | Dense-laptop review width. Desktop share is fragmented: 1920x1080 28.07%, 1536x864 10%, 1366x768 7.95%, 2560x1440 3.95% ([StatCounter desktop](https://gs.statcounter.com/screen-resolution-stats/desktop/worldwide): screen resolutions, not viewport widths). Cheap extra: also capture 1366x768 because it remains a common laptop resolution. |

## 4. Interaction states to capture (one row = one evidence row)

| State | How to force it | What can break visually | Binary criterion |
|---|---|---|---|
| Empty, no provider | Fresh state directory, no provider configured | Empty-state layout, missing next step, dead CTA | Exactly one primary next action visible; no blank panels |
| Filled provider form | Pasted key, valid format, not yet saved | Button state, helper text, key masking | Save action enabled/disabled matches validity |
| Loading (first request or health probe) | Slow/held response | Spinner vs progress, layout collapse, double submit | Status visible within 1 s; estimate if >10 s ([NN/g response times](https://www.nngroup.com/articles/response-times-3-important-limits/); [NN/g progress indicators](https://www.nngroup.com/articles/progress-indicators/)) |
| Saving | Submit + held write | Duplicate submit, frozen form, lost focus | Button disabled, progress shown, form state preserved |
| Validation error | Invalid key / wrong base URL | Error placement, red-only signalling, layout jump | Message visible and specific next to the field ([NN/g error messages](https://www.nngroup.com/articles/error-message-guidelines/); [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/)) |
| Blocked by approval | Approval gate pending | Blocked vs disabled confusion, action hidden | User can tell what is blocked and why |
| Provider unavailable | Stop/local service down, or bad base URL | Retry path, offline banner, stale data | Retry or switch-route path visible; no silent failure |
| Permission denied | OS keyring/permission refusal if present | Error swallowed, raw exception string | Human-readable cause + recovery |
| Offline / local server down | Kill server after load; reload | Whole-shell dead ends, stuck skeleton | Shell explains connection loss; no infinite spinner |
| Stale resume | Reload mid-onboarding, stale persisted step | Wrong step rendered, duplicated welcome, lost draft | Resumes at the correct step; no false success |
| Success / first output | Complete first request | Success state layout, next-step CTA | Success is unambiguous; next action offered |
| Long error (provider stack text) | Return a long upstream error | Overflow, clipped message, no scroll | Text wraps or expands; copyable; no clipping |
| Long / non-Latin / transliterated bot name | e.g. 60 chars, CJK, accented transliteration | Truncation or overlap in header/card/list | No lost characters in the editable field; intentional ellipsis elsewhere |
| Dark and light | Toggle `data-hutch-theme` if present, or emulated `prefers-color-scheme` | Unreadable borders/text, inverted icons | WCAG non-text contrast 3:1 for controls/state ([W3C 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)) |
| Reduced motion | Emulate `prefers-reduced-motion: reduce` | Essential animation removed, or not removed | Non-essential motion suppressed; no functionality lost ([web.dev](https://web.dev/articles/prefers-reduced-motion.md.txt)) |
| Keyboard focus | Tab through full flow, including dialogs | Invisible ring, ring clipped, sticky header covers it | Visible focus; not entirely obscured ([W3C 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)); 2 px/3:1 indicator guidance ([W3C 2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)) |
| 200% / 400% | Browser text zoom 200%; 320 px wide at 400% | Truncation, overlap, lost controls | Text resizes to 200% with no loss ([W3C 1.4.4](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html)); reflow per 1.4.10 |
| Forced-colors | Emulate `forced-colors: active` | Custom colours vanish, focus disappears | Usable in system colours ([MDN forced-colors](https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/reference/at-rules/@media/forced-colors/index.md); [DevTools emulation](https://developer.chrome.com/docs/devtools/rendering/emulate-css.md.txt)) |
| Hover / disabled | Mouse rest and hover; disabled button | Hover-only affordance captured in screenshots, disabled looks enabled | Hover is not the only affordance; disabled is visually distinct ([Playwright](https://playwright.dev/docs/test-snapshots): screenshots capture hover state; it warns to move the mouse away) |
| Touch targets | Phone viewports, coarse pointer | Tight icon buttons, adjacent destructive actions | Minimum 24x24 CSS px with spacing ([W3C 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)); repo floor for coarse pointers is 44px as documented in [docs/prompts/prompt-6-visual-regression-docs.md](../../prompts/prompt-6-visual-regression-docs.md) |

## 5. Real-data scenarios to capture

| Scenario | Data setup | Expected evidence |
|---|---|---|
| First run with no provider | Empty state | Empty-state screenshot; next action; no fake model list |
| One hosted provider connected | A single key route (fake key, no live call) | Route card and first-request reachable; no other-provider defaults implied |
| Local model service present | Ollama-compatible endpoint reporting one model | Local route chosen and labelled local; health output visible |
| Local model failing health check | Endpoint returns error/timeout | Failure reason + retry/switch route; not a blank spinner |
| Bot name with non-Latin/transliterated characters | e.g. "Juno 助手", "Zoë", 60-char name | Editing, list, header and card all preserve/ellipsize intentionally; real bug class: name truncated to first word ([rsdouglas/proof#121](https://github.com/rsdouglas/proof/issues/121): a first-login page showed "Welcome back, Audit" for "Audit User Fresh") |
| Long provider error | Upstream returns multi-line stack/API message | Message readable, copyable, not overflowing the dialog |
| Expired pairing code | Stale QR/token, then attempt pairing | Explicit expired state and regenerate action; no silent hang |
| No bots after onboarding | Skip bot creation | Roster empty state; no broken nav or "create bot" dead end |

## 6. The claimed "13-item pre-PR visual checklist": provenance

Searches for a published "13-item pre-PR visual checklist" found no primary source (W3C, Playwright, NN/g, web.dev) and no traceable standard. The closest indexed artifact is a community AI-skill listing: **LobeHub's page for `ui-visual-validator` (author kumaran-is, listed 21 Oct 2026) advertises "a 13-item mandatory verification checklist for systematic pre-PR reviews"** ([LobeHub listing](https://lobehub.com/skills/kumaran-is-claude-code-onboarding-ui-visual-validator): a marketplace description, not a published checklist; the item list is not shown in the page text I read). An adjacent community UI-testing skill uses a similar but not identical checklist ([alinaqi/claude-bootstrap UI-testing SKILL.md](https://raw.githubusercontent.com/alinaqi/claude-bootstrap/55aabe2493627e1de9cd09459d555181d66f3111/skills/ui-testing/SKILL.md)), which suggests the number is a community convention rather than an industry standard. **Verdict: provenance unverified; do not cite "13-item" as a standard.** Use the sourced 13-row gate below instead; it keeps the useful count without inheriting an unsourced authority claim.

## 7. Sourced 13-item visual gate (each row is binary pass/fail)

| # | Check | Pass condition | Source |
|---|---|---|---|
| 1 | No horizontal overflow | No clipping or two-dimensional scrolling at 320/375/768/1440 | [WCAG 1.4.10](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) |
| 2 | Text zoom | 200% text zoom loses no content or function | [WCAG 1.4.4](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html) |
| 3 | Text contrast | No low-contrast text on any captured surface | [WebAIM Million 2026](https://webaim.org/projects/million/) (83.9% of pages fail); repo floor text >=5:1 in [prompt-6](../../prompts/prompt-6-visual-regression-docs.md) |
| 4 | Control boundaries and states | 3:1 against adjacent colours for control edges, focus and state cues | [WCAG 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) |
| 5 | Focus not obscured | Sticky chrome/dialogs never fully hide the focused control | [WCAG 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html) |
| 6 | Focus appearance | Visible ring; at least 2 CSS px perimeter-equivalent area and 3:1 change | [WCAG 2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html) (AAA: stricter than the AA floor, used as repo bar) |
| 7 | Target size | 24x24 CSS px minimum with spacing at phone widths | [WCAG 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) |
| 8 | Dark/light both evaluated | Both scopes captured, not inferred from one | [web.dev prefers-color-scheme](https://web.dev/articles/prefers-color-scheme.md.txt); [DevTools emulation](https://developer.chrome.com/docs/devtools/rendering/emulate-css.md.txt) |
| 9 | Forced colours | Flow usable in system colours | [MDN forced-colors](https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/reference/at-rules/@media/forced-colors/index.md) |
| 10 | Reduced motion | Non-essential animation suppressed | [web.dev prefers-reduced-motion](https://web.dev/articles/prefers-reduced-motion.md.txt) |
| 11 | Feedback timing | Loading is visible within 1 s; an estimate appears for >10 s operations | [NN/g response times](https://www.nngroup.com/articles/response-times-3-important-limits/); [NN/g progress indicators](https://www.nngroup.com/articles/progress-indicators/) |
| 12 | Error visibility | Errors specific, adjacent to the field, and not colour-only | [NN/g error messages](https://www.nngroup.com/articles/error-message-guidelines/); [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/) |
| 13 | Evidence chain | Every required state has an opened screenshot and a validation.json row with verdict | Repo convention: [docs/file-formats.md:67](../../file-formats.md); [docs/qa/shape-and-background-review.md:69-71](../../qa/shape-and-background-review.md) |

Missing evidence is a FAIL, not a pass; there is no partial score (§2 step 4).

## 8. What unit/DOM tests cannot catch

| Class | Why it is invisible to jsdom/unit tests | Anchor |
|---|---|---|
| Paint, layout, overflow, clipping | jsdom has no layout engine and no renderer; layout properties return zeros | [jsdom README](https://github.com/jsdom/jsdom#unimplemented-parts-of-the-web-platform) |
| Contrast and colour-only state | Needs computed rendered colours, not classes | [WCAG 1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) |
| Focus ring quality/obscuring | Needs geometry plus ruling chrome | [WCAG 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html), [2.4.13](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html) |
| Touch target spacing | Needs rendered boxes at coarse-pointer viewports | [WCAG 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) |
| Viewport/responsive reflow | CSS/media queries are not evaluated for layout by jsdom | [WCAG 1.4.10](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) |
| Font fallback and FOUT shift | Fonts render larger/smaller than fallback and move content | [web.dev CLS](https://web.dev/articles/cls) |
| Dark/forced colours | Media-feature-driven colours only exist at paint time | [MDN forced-colors](https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/reference/at-rules/@media/forced-colors/index.md) |
| Loading/error/transient states | Assertions see DOM, not what the user sees mid-flight | [Playwright](https://playwright.dev/docs/api/class-pageassertions) |
| Cross-platform glyph rendering | Platform fonts/AA differ; CI and laptop differ | [Argos](https://argos-ci.com/docs/learn/reliability-and-flakiness/flaky-tests/stabilize-text-rendering) |

## 9. Open questions for code inspection (Lead)

- Which onboarding routes/states actually exist, and is there a fixtures/preview harness to reach them without real providers?
- Does the dashboard implement dark/light scopes, reduced motion, and forced-colours handling already (repo mentions explicit dark/light scopes in [prompt-6](../../prompts/prompt-6-visual-regression-docs.md), but the live tree must be checked)?
- How is 200% zoom exercised: browser zoom only, or in-app text-size control?
- What is the pairing-code expiry behaviour, and how does the UI show an expired QR?
- Which browser is actually supported for the locally served dashboard (desktop host uses a webview; phone use is a browser), and therefore which visual baselines are authoritative?
- Lane: which of these checks can run in the fast/pre-PR path versus a heavy browser lane (see [AGENTS.md](../../../AGENTS.md))?

## Sources (all opened 2026-10-29 unless marked)

| URL | Title | Type | Supports |
|---|---|---|---|
| https://playwright.dev/docs/test-snapshots | Playwright: Visual comparisons | primary | §1, §2, §4, §7 |
| https://playwright.dev/docs/api/class-pageassertions | Playwright: PageAssertions.toHaveScreenshot | primary | §1, §2, §4 |
| https://playwright.dev/docs/clock | Playwright: Clock | primary | §2 |
| https://playwright.dev/docs/emulation | Playwright: Emulation/devices | primary | §2, §3 |
| https://raw.githubusercontent.com/microsoft/playwright/main/docs/src/accessibility-testing-js.md | Playwright: Accessibility testing | primary | §1, §8 |
| https://web.dev/articles/cls | web.dev: Cumulative Layout Shift | primary | §1, §8 |
| https://raw.githubusercontent.com/GoogleChrome/web-vitals/main/README.md | web-vitals: metric thresholds (CLS 0.1/0.25) | secondary | §1 |
| https://developer.chrome.com/docs/devtools/rendering/performance.md.txt | Chrome DevTools: Rendering performance reference | primary | §1, §2 |
| https://developer.chrome.com/docs/devtools/rendering/emulate-css.md.txt | Chrome DevTools: Emulate CSS media features | primary | §4, §7 |
| https://argos-ci.com/docs/learn/reliability-and-flakiness/flaky-tests/stabilize-text-rendering | Argos: Stabilize text rendering | secondary | §1, §8 |
| https://github.com/jsdom/jsdom | jsdom README (unimplemented: layout) | primary | §1, §8 |
| https://webaim.org/projects/million/ | WebAIM Million 2026 | primary (research) | §1, §7, §8 |
| https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html | WCAG 2.2 SC 1.4.11 | primary (standard) | §4, §7, §8 |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html | WCAG 2.2 SC 2.4.13 | primary (standard) | §4, §7 |
| https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html | WCAG 2.2 SC 2.4.11 | primary (standard) | §2, §4, §7, §8 |
| https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html | WCAG 2.2 SC 1.4.4 | primary (standard) | §4, §7, §8 |
| https://www.w3.org/WAI/WCAG22/Understanding/reflow.html | WCAG 2.2 SC 1.4.10 | primary (standard) | §3, §4, §7, §8 |
| https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html | WCAG 2.2 SC 2.5.8 | primary (standard) | §4, §7, §8 |
| https://web.dev/articles/prefers-reduced-motion.md.txt | web.dev: prefers-reduced-motion | primary | §4, §7 |
| https://web.dev/articles/prefers-color-scheme.md.txt | web.dev: prefers-color-scheme | primary | §4, §7 |
| https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/css/reference/at-rules/@media/forced-colors/index.md | MDN: forced-colors media feature | primary | §4, §7, §8 |
| https://www.nngroup.com/articles/response-times-3-important-limits/ | NN/g: Response times (0.1/1/10 s) | secondary (research) | §4, §7 |
| https://www.nngroup.com/articles/progress-indicators/ | NN/g: Progress indicators | secondary (research) | §4, §7 |
| https://www.nngroup.com/articles/error-message-guidelines/ | NN/g: Error-message guidelines | secondary (research) | §4, §7 |
| https://design-system.service.gov.uk/components/error-message/ | GOV.UK Design System: Error message | primary (design system) | §4, §7 |
| https://lobehub.com/skills/kumaran-is-claude-code-onboarding-ui-visual-validator | LobeHub: ui-visual-validator community skill ("13-item" claim) | secondary (community) | §6 |
| https://raw.githubusercontent.com/alinaqi/claude-bootstrap/55aabe2493627e1de9cd09459d555181d66f3111/skills/ui-testing/SKILL.md | Community UI-testing skill checklist | secondary (community) | §6 |
| https://raw.githubusercontent.com/tailwindlabs/tailwindcss/main/packages/tailwindcss/theme.css | Tailwind default breakpoints | primary (framework source) | §3 |
| https://getbootstrap.com/docs/5.3/layout/breakpoints/ | Bootstrap 5.3 breakpoints | primary (framework docs) | §3 |
| https://gs.statcounter.com/screen-resolution-stats/mobile/worldwide | StatCounter: mobile screen resolutions, Sep 2026 | secondary (statistics) | §3 |
| https://gs.statcounter.com/screen-resolution-stats/tablet/worldwide | StatCounter: tablet screen resolutions, Sep 2026 | secondary (statistics) | §3 |
| https://gs.statcounter.com/screen-resolution-stats/desktop/worldwide | StatCounter: desktop screen resolutions, Sep 2026 | secondary (statistics) | §3 |

**Unverified / not usable:** a specific "13-item" published checklist (not found; §6); no item list was retrievable from the LobeHub listing beyond the description. Fetch of FTC pages (used in the companion marketing note) returned 403 and is marked unverified there.
