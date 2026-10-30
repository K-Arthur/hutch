# Responsive Adaptation - Phase 1 Audit

Date: 2026-10-29. Baseline commit 2a89909a; audit performed on the current
working tree, which also contains another session's uncommitted brand/dashboard
changes. Source was read-only for this audit; no file was modified except this
document and inventory.md. Method: static source audit (CSS/HTML/JS/templates)
targeted at the surfaces scored in docs/responsive/inventory.md. Every finding
carries an exact file:line. No browser, Playwright or device pass was run.

Severity scale: Critical = a primary workflow cannot be completed at a target
viewport or input mode; High = primary workflow significantly degraded or a
control becomes unreachable/overlapped; Medium = friction, overlap, sub-44px
target or missing adaptation at a target; Low = cosmetic or maintenance debt.

Target viewports: 1366x1024 (13in iPad landscape), 1180x820, 1024x768
landscape tablets, 768x1024 portrait tablet, 320x568, 375x667, 390x844 phones,
and phone landscape 844x390 / 932x430.

## Target-viewport matrix (what the current CSS does)

| Viewport | Surface behaviour | Risk |
|----------|-------------------|------|
| 1366x1024 (iPad landscape) | SPA: desktop shell, sidebar 304px at >=1001 (app/src/input.css:39-43); workflow status visible. Server pages: hamburger + full-screen overlay because the nav collapses at <=1400 (hutch.css:331). Coarse pointer: generic icon buttons 40px (style.css:1800), approval filters 30px (style.css:1883). | High: server navigation is phone-style on a 13in tablet; touch targets under 44 |
| 1180x820 | SPA desktop, rail 304px, workflow visible (>1100, studio.css:513). Server pages: hamburger. Nothing in any sheet is tuned for 1180 specifically. | Medium |
| 1024x768 (landscape tablet) | SPA desktop (>900, style.css:1680) with rail 272px (style.css:235); workflow cluster hidden at <=1100 (studio.css:513). Server pages: hamburger. Height tuning only in first-run rules (studio.css:776, 781). | Medium |
| 768x1024 (portrait tablet) | SPA drawer mode <=900; server pages still hamburger; marketing drawer <=1023. Coarse-pointer sizes apply. | Medium |
| 320x568 / 375x667 / 390x844 | SPA drawer; server topbar wraps at <=720 (hutch.css:304); forms stack; 16px input floors; only SPA composer gets a safe-area bottom pad. No rules tuned below 359px except the 360/359 edges (style.css:1283, 2440). | Medium-High: on-screen keyboard and target sizes |
| 844x390 / 932x430 phone landscape | SPA drawer mode (<=900); 100dvh shell minus 56px header leaves about 334px of content (style.css:236-239); chat keyboard overlap (E1); marketing hero scene min-height 340px fills most of the 390px height (website/styles.css:266). | High for chat while typing |

# A. Breakpoints

## A1. Inventory per stylesheet

All values are literal px; no breakpoint tokens exist. Aggregated over the 23
CSS sources: 359 (1 use), 360 (2), 420 (1), 480 (8), 520 (3), 521 (1), 560 (11),
561 (2), 600 (1), 620 (1), 640 (36), 641 (5), 720 (4), 760 (4), 800 (1),
900 (9), 901 (3), 940 (7), 1000 (2), 1001 (1), 1023 (1), 1100 (3), 1400 (1).
Height-based queries exist only in studio.css (max-height 760/520). Container
queries: app/src/input.css:55-63, studio.css:767 and 965, style.css:2189-2198.

| Stylesheet | Width tokens | Layout/grid rules they change |
|------------|--------------|-------------------------------|
| app/src/input.css | 1001, 1100, 640 | sidebar column 304px at >=1001 (39-43); service grid 3 -> 2 -> 1 (90, 164-166, 167-177); channel form 1 col at 620 (375-380); container query for service tiles (55-63) |
| app/src/model-switcher.css | 560, 640 | menu width/full-bleed (94-97, 103-106) |
| static/hutch.css | 1100, 1000, 760, 720, 1400 | home grid 3 -> 2 -> 1 (292-301); two-col/settings 1 col (296); gutter 12 and wrapped topbar (302-317); coarse target block (318); nav overlay/hamburger at <=1400 (331-343) |
| static/hutch-pages.css | 800, 560 | connection grid 1 col (17); device rows stack (47-50); usage table becomes labelled cards (68-81) |
| static/style.css | 901, 900, 640, 561, 560, 520, 521, 480, 420, 360, 359, 720, 600, 1100 | SPA drawer vs rail (380-408, 1680-1692); header wrap and 3-row shell (1939-1974); bottom-sheet modal (1756-1763); touch/coarse block (1794-1813, 1926-1936); remaining feature breakpoints (1722-1786, 1912-1925, 2023-2035, 2123, 2406-2440, 2588, 2637, 2713, 2730) |
| static/studio.css | 901, 1100, 640, 561, 560, 520, 480, 360 | collapsed rail rules >=901 (449-461); one-row header >=901 (476-482); workflow hidden <=1100 (513); reminder row >=641 (520-532); phone header grid <=640 (535-559); first-run short-height rules (776-797); coarse targets scattered (132, 156, 166, 356, 506, 658, 791-797, 906, 934, 1004-1012) |
| static/hutch-form-controls.css | 1000, 720 | two-up form grid 1 col (172-174); inline/action bars stack (225-243); coarse density+16px floor (248-259) |
| static/hutch-composer.css | 900, 640 | composer seat safe-area padding (103-105); meta hidden and 44px seats (208-211, 370-371, 386-392) |
| static/hutch-composer-context.css | 640, coarse | context strip wrap (112) |
| static/hutch-select.css | coarse/forced | 44px select at coarse (262-271) |
| static/hutch-messages.css | 640, 560 | message identity density (310-318) |
| static/widgets.css | 480 | widget card/table density (448-456) |
| static/computer.css | 480 | action stack (72-75) |
| static/skills.css | 720 | skill grid 1 col, picker menu right-aligned (102-108) |
| web/styles/hutch-bot-card.css | 640, coarse | card layout (111-118) |
| web/styles/hutch-surfaces.css | 640, coarse | approval surface layout (357-373) |
| website/styles.css | 640, 760, 900, 940, 1023 | marketing section grids, hero, proof, FAQ, CTA, nav drawer (46-49, 178-201, 245-274, 275-276, 335-338, 410-416, 528-539, 575-581) |

## A2. Findings

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| src/hutch/server/static/hutch.css:331 | Server-page primary nav collapses into a full-screen overlay at max-width:1400px; the hamburger is the only entry point at 1366, 1180 and 1024 widths. The same shell keeps a desktop topbar, so a 13in iPad or a 1440-1366 laptop gets phone-style navigation. | 1366x1024, 1180x820, 1024x768, all laptop widths <=1400 | High |
| src/hutch/server/static/hutch.css:337 | The overlay is hidden with transform/opacity/pointer-events and only opens from hutch.js. hutch.js:188 uses the same 1400px matchMedia. If the deferred script fails or JS is off, navigation is unreachable at every width <=1400, although server pages are explicitly built to work without JavaScript (src/hutch/server/pages.py:1-6). | JS-disabled or script failure, any width <=1400 | High |
| src/hutch/server/static/hutch.css:90 | At >1400 the horizontal nav becomes scrollable but hides its scrollbar (hutch.css:91). Nine nav items (src/hutch/server/pages.py:37-47) plus brand and topbar actions do not fit comfortably at 1401-1500, so trailing items can require horizontal scrolling with no visible affordance. | 1401-1500 desktop | Low |
| src/hutch/server/static/style.css:2713 | Unclosed @media (max-width: 720px) block: the file has 1773 opening and 1772 closing braces, and the media query that starts at 2713 never closes before the nested 480px query at 2730/2732. Consequently the .preflight*, .context-line*, .run-cost-provenance, .compaction-list and .budget-meter rules (2716-2729) apply only at <=720px instead of at all widths, and the stylesheet structure is unbalanced. | All desktop widths >720 (intended global styles lost); parser recovery to EOF | High |
| src/hutch/server/static/style.css:235 vs app/src/input.css:39-43 | The SPA rail is 272px (style.css) but becomes 304px at >=1001px (ui.css source), a 32px jump with no other layout change, adjacent to the 1000/1001 collapse thresholds. Sidebar geometry has two owners and two values. | 1000/1001 boundary; 1024x768 vs 1180x820 | Medium |
| src/hutch/server/static/hutch.css:114 | Sticky run header is pinned at top:54px, but at <=720 the server topbar grows to an auto height with wrapped rows (hutch.css:304). The run title/status stick under or behind the taller topbar while scrolling. | server /runs/<id> at <=720 (phones, narrow window) | Medium |
| src/hutch/server/static/hutch.css:80 | html { scroll-padding-top: 4.5rem } assumes a fixed 72px topbar, but the topbar is 54px on desktop (hutch.css:86) and auto-height when wrapped. Focused anchors are obscured or over-padded once the bar wraps. | <=720 server pages; also slight on desktop | Low |
| src/hutch/server/static/style.css:1283, 2440 | The only rules tighter than the 360 token are 359/360px; there is no breakpoint at 320, 375 or 390, and no height-based layout for phone landscape outside studio.css:776/781. Each phone width therefore reuses the 640px phone rules unchanged. | 320x568, 375x667, 390x844, phone landscape | Medium |
| src/hutch/server/static/studio.css:513 | Workflow/activity cluster disappears at <=1100 while the surrounding header remains otherwise unchanged; on an 11in landscape tablet (1180) it is present, at 1024 it vanishes with no alternate surface beyond the Needs-you drawer and runtime page. | 1024x768, 1100 and below | Low |
| website/styles.css:275-276 vs website/index.html:256 | Marketing navbar switches at 1023 while the button visibility is Tailwind lg:hidden (>=1024 hidden) - consistent, but the token differs from the app's 1024 expectations; low risk, noted for token consolidation. | 1023/1024 boundary | Low |

# B. Viewport units and fixed chrome

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| src/hutch/server/static/hutch.css:57 | Server pages use body { min-height: 100vh }; on mobile Safari the largest viewport height makes the page taller than the visible viewport, producing a spurious scroll and footer offset when the URL bar is expanded. Use dvh/svh with a vh fallback. | mobile Safari/Chrome URL-bar states, all phone widths | Low |
| src/hutch/server/static/style.css:237-239 | SPA shell locks height to 100dvh (with a 100vh fallback). No companion visual-viewport adjustment exists for the shell; only popups subscribe to visualViewport (src/hutch/server/static/controls.js:185-188). See E1 for the keyboard consequence. | phones with on-screen keyboard; iOS Safari | Medium (tracked as E1) |
| src/hutch/server/static/style.css:1402-1404 | Toast stack is position:fixed at bottom/right var(--s-5)=24px with no env(safe-area-inset-bottom). On viewport-fit=cover phones toasts can sit under the home indicator. | notched iPhones, standalone PWA, landscape | Medium |
| src/hutch/server/static/style.css:1683-1688 | Workspace drawer is position:fixed left/top/bottom with width min(300px,86vw) and no env() side insets; with viewport-fit=cover (src/hutch/server/static/index.html:5) the rail content can slide under the left notch in landscape. | iPhone landscape / notched tablet, drawer open | Medium |
| src/hutch/server/static/style.css:1855-1862 | Needs-you drawer is a fixed 100dvh panel with padding 0 24px 24px; the 24px bottom pad is smaller than a 34px home indicator and no env() inset is applied, so the last approval row/button can sit under the indicator. | notched iPhones, drawer open | Medium |
| src/hutch/server/static/style.css:1759 | Bottom-sheet modal is capped at max-height:100dvh; on 844x390 landscape this can leave the sheet header off-screen when the browser's dynamic bar is expanded; the 93dvh cap on the base card (style.css:1758) is the safer value. | phone landscape, browser chrome expanded | Low |
| src/hutch/server/static/style.css:733 | Chat scroller uses internal overflow (flex:1; min-height:0; overflow-y:auto) inside the fixed-height shell; fixed chrome at the top and the composer at the bottom do not participate in page scroll. This is fine for wheel/touch, but leaves no page-level scroll to fall back on when the layout viewport is reduced externally. | see E1 | Medium (tracked as E1) |
| src/hutch/server/static/computer.css:57 | Computer-use screenshot is capped at 60vh; on short landscape windows (390-430px high) the preview occupies most of the content area but remains scrollable, so it does not clip. | phone landscape content density only | Low |
| src/hutch/server/static/style.css:2041 | Positive example: the paired-phone surface uses min-height:100svh and max(env(safe-area-inset-top),12px)/max(env(safe-area-inset-bottom),24px) padding. This is the only top-inset use in the product. | n/a (works) | Non-finding |

# C. Touch and hover

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| src/hutch/server/static/hutch.css:328-329 | Server-page hamburger is 38x38px, below the 44px standard. The coarse-pointer block only enlarges .btn/.btn.small (hutch.css:318-320); .nav-toggle is not a .btn and gets no coarse treatment. | all touch devices on server pages, especially 768x1024 and iPads | Medium |
| src/hutch/server/static/style.css:1800 | Under pointer:coarse the generic .icon-btn is set to 40x40 even though the surrounding comment claims a 44x44 standard. The sidebar toggle, workspace search, new-assistant and needs-you close buttons stay 40px unless a more specific rule overrides them. | touch tablet widths >640 (e.g. 768x1024, 1024x768, 1366x1024) | Medium |
| src/hutch/server/static/style.css:1877, 1966 | Needs-you close button has only a font-size rule; the 44px minimum lives inside a max-width:640px block, so on a 768/1024px coarse-pointer tablet the drawer close control is smaller than 44px. | 768-1366 coarse-pointer tablets | Medium |
| src/hutch/server/static/style.css:1883 | Approval filter chips are min-height:30px with the 44px override only at <=640 (style.css:1915); on tablets the most-used approval filtering controls are 30px tall. | coarse tablet 641-1366 | Medium |
| src/hutch/server/static/style.css:1291, 1298 | Runs filter pills are roughly 30px tall (8px vertical padding, 14px label) and the search input is fixed at 260px wide (1291). No coarse-pointer rule enlarges the pills; the input widens to 100% only at <=640 (1750). | coarse tablet 641-1024 | Medium |
| src/hutch/server/static/controls.css:64 | Popup header close button is min-height:40px while popup rows are raised to 44px at coarse (controls.css:85-87). A frequently used close target stays 4px under the standard. | coarse pointers, all widths | Low |
| website/index.html:255, 269, 300-301 | Marketing header CTA and drawer close use daisyUI btn-sm (32px effective height); hero CTAs use the default button height (40px). website/styles.css has no pointer: coarse block at all (only pointer:fine at 568), so no touch enlargement exists on the public site. | all touch devices; 320-1024 widths | Medium |
| website/index.html:263 | Drawer links do get the 44px --size-target (website/styles.css:291-297), so the drawer body is fine; only the header/footer buttons are undersized. | touch devices | Low |
| src/hutch/server/static/hutch.css:122 | .btn.small is 32px on desktop but the coarse block raises .btn.small to 44px, so no issue on touch; noted because the same 32px value is reused in the marketing build without the coarse override. | desktop only | Non-finding |
| src/hutch/server/static/style.css:1842, 1850-1853 | Roster options stay visible at opacity .62 and only gain full opacity/hover reveal on (hover:hover) and (pointer:fine); no action is hover-gated, and focus-within expands the same control. | none | Non-finding |
| src/hutch/server/static/style.css:217; hutch.css:83; website/styles.css:34 | Global :focus-visible rings exist on all three surfaces, and component sheets restate them where all: unset clears the ring (e.g. style.css:510-513). | none | Non-finding |
| src/hutch/server/static/style.css:1930-1935 | SPA input/select/textarea get a max(1rem,16px) font floor under pointer:coarse, preventing iOS focus zoom (zoom itself is never disabled). | none | Non-finding |
| src/hutch/server/static/hutch.css:226 | The legacy server-page 16px floor covers only text/password/textarea. The form system covers all .hutch-input/.hutch-textarea/.hutch-select controls (hutch-form-controls.css:248-259), and no template currently renders a raw search input, so current exposure is limited to ad-hoc legacy inputs. | hypothetical raw email/url/number/date inputs on server pages | Low |

# D. Safe area and viewport meta

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| src/hutch/server/templates/base.html:6 | Server pages declare width=device-width, initial-scale=1 without viewport-fit=cover. Every env(safe-area-inset-*) rule on their stylesheets therefore resolves to 0. The only server-page safe-area rule is the composer seat (src/hutch/server/static/hutch-composer.css:103-105), so the Give it a task composer never clears the home indicator on a notched phone. The SPA document does declare viewport-fit=cover (src/hutch/server/static/index.html:5), so the two dashboards disagree. | notched iPhones/Android gesture phones on server-rendered pages | High |
| src/hutch/server/static/index.html:5 | SPA opts into viewport-fit=cover, but the primary shell ignores top/left/right insets: .app-top (style.css:425-433) and .workspace (style.css:243-250) have no env() padding, and the fixed drawer (style.css:1683) has none. Only the composer bottom (hutch-composer.css:104), bottom-sheet modal footer (style.css:1762) and paired-phone root (style.css:2041) use insets. | iOS standalone/PWA and landscape notch overlap | Medium |
| src/hutch/server/static/hutch-composer.css:104 | Correct use of env(safe-area-inset-bottom) in the composer seat, but only at <=900px and only where viewport-fit=cover exists; on server pages it is inert (see base.html:6). | server pages (inert), SPA phones (works) | Medium |
| src/hutch/server/static/style.css:1762 | Bottom-sheet modal footer does apply a safe-area bottom inset - the model implementation other bottom surfaces should copy. | none | Non-finding |
| website/index.html:5 | Marketing site does not use viewport-fit=cover and has no env() usage; the browser insets the layout viewport, so the sticky header and dialog drawer are already in the safe area. Only note: it differs from the SPA declaration. | none | Non-finding |
| src/hutch/server/static/style.css:2041 | Paired-phone surface pads with env(safe-area-inset-top/bottom) and 100svh - correct. | none | Non-finding |

# E. Tables, forms, modals and on-screen keyboard

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| E1 - src/hutch/server/static/style.css:233-240, 733; src/hutch/server/static/hutch-composer.css:95-105 | The SPA chat shell is a fixed 100dvh grid; the transcript scrolls internally and the composer is a normal-flow flex child. There is no visualViewport resize handling for the shell (app.js has none; controls.js:185-188 only repositions popups). On iOS, where the software keyboard overlays the layout viewport instead of resizing it, the composer seat and the focused textarea can be covered while typing. | iOS/Android phones in portrait and landscape, chat/composer focused | High |
| src/hutch/server/static/style.css:1855-1862 | Needs-you drawer is a fixed 100dvh panel with its own overflow-y; approval review textareas open under the keyboard with no visualViewport compensation. Browser scroll-into-view is the only fallback. | phones, approving with a comment keyboard open | Medium |
| src/hutch/server/static/hutch-forms.css:231-236 | The form system uses rows-sized textareas with resize: vertical and no scroll-margin, relying on the browser to reveal focused fields; only computer.css:84 reserves scroll-margin-block: 150px 60px for keyboard space. Dense forms (connections.html, models price form) have no equivalent reservation. | phone keyboard on dense server forms | Low |
| src/hutch/server/static/hutch.css:250 | Global th, td { white-space: nowrap } forces horizontal scrolling inside all data-table wrappers; prompt/spend columns are only hidden at <=720 via .hide-sm (hutch.css:311). At 768-1024 all nine run columns remain, requiring horizontal scroll, though the wrapper makes it operable. | 768x1024, 1024x768 | Low |
| src/hutch/server/templates/usage.html:22, 45, 57, 63; models.html:33, 79, 104; _runs_table.html:2 | All server-rendered data tables are wrapped in .table-wrap with role=region and tabindex=0 (hutch.css:248) - correct pattern; the usage-cap table additionally converts to labelled cards at 560 (hutch-pages.css:68-81). | none | Non-finding |
| src/hutch/server/static/style.css:1196-1212; src/hutch/server/static/app.js:7724 | SPA work history renders an accessible card list instead of a wide table, avoiding horizontal scrolling for the densest SPA list. | none | Non-finding |
| src/hutch/server/static/widgets.js:356, 422, 597; app/src/input.css:326 | SPA widget tables and the campaign report table are wrapped in .table-wrap / overflow-x:auto containers. | none | Non-finding |
| src/hutch/server/static/hutch-form-controls.css:172-174, 225-243, 248-259; src/hutch/server/static/hutch-forms.css:109-125 | The form system collapses two-up grids at 1000, stacks inline action/filter rows at 720, wraps actions, and floors touch controls at 44px/16px. Server forms are structurally responsive. | none | Non-finding |
| src/hutch/server/static/studio.css:956-962 | Form fields use minmax(0,1fr) tracks and percentage-width text controls, preventing a 200% text-size overflow; this directly addresses the classic form-wider-than-screen failure. | none (positive) | Non-finding |
| src/hutch/server/static/studio.css:535-546; src/hutch/server/static/style.css:1965-1974 | SPA phone header reorders identity, run controls, conversation picker, search and menu into two rows instead of squeezing them, and the attention bar stays in grid flow below the header. | none | Non-finding |

# F. Marketing site (website/index.html, styles.css, src/input.css, site.js)

| file:line | Finding | Breaks at viewport/orientation/input mode | Severity |
|-----------|---------|-------------------------------------------|----------|
| website/index.html:228; website/styles.css:276, 31 | Without JavaScript, the inline noscript rule forces .navbar-center to display and hides the menu button, while CSS hides the navbar links below 1024px and body { overflow-x: hidden } clips the result. The six-link horizontal menu plus CTAs then overflows and becomes partially unreachable on any no-JS phone/tablet. | <=1023 with JS disabled or blocked | Medium |
| website/index.html:255, 269 | Header CTA and drawer Close are btn-sm (32px effective) and there is no pointer:coarse rule anywhere in website/styles.css, so the public site has no 44px touch enlargement. | all touch devices | Medium |
| website/styles.css:341-357 | The .receipts table rules (min-width:760px) are now unused by index.html (the table was removed; grep finds only the section id). Dead CSS that would overflow if a future table reused the class without a wrapper. | maintenance | Low |
| website/index.html:805-806 | The availability table is correctly inside .overflow-x-auto and uses fixed layout with wrapping cells at <=640 (website/styles.css:502-511). | none | Non-finding |
| website/styles.css:232, 249, 266 | Hero figure has fixed min-heights of 460/450/340px. On phone landscape (390px high) the hero figure plus the 68px sticky bar nearly fills the viewport; content remains scrollable and is not clipped, but the hero dominates above the fold. | 844x390, 932x430 | Low |
| website/styles.css:552-581; website/site.js:9, 97 | Reduced motion is fully respected (reveal watchdog, no idle animation on touch, CSS overrides) and pointer-reactive animation is gated to pointer:fine - matching the app's approach. | none | Non-finding |
| website/styles.css:280-297; website/site.js:47-65 | Nav drawer is a native modal dialog with inset placement, max-height 100dvh, scrollable link list, outside-click/Escape/native close and focus restore; drawer links meet the 44px target token (website/tokens.json size.target). | none | Non-finding |
| website/styles.css:275-276; website/index.html:256; website/site.js:64 | The 1023/1024 nav breakpoint, Tailwind lg:hidden on the menu button and the 1024 resize-closes-drawer logic are consistent. | none | Non-finding |

# Top 10 prioritized risks

1. Server dashboard navigation collapses to a JS-dependent full-screen overlay at <=1400px (hutch.css:331-343; hutch.js:184-219): 1366x1024, 1180x820 and 1024x768 landscape tablets get phone navigation, and no-JS users lose navigation entirely. [High]
2. Server-page viewport meta lacks viewport-fit=cover (templates/base.html:6), making every env(safe-area-inset-*) rule on server pages inert (hutch-composer.css:103-105), so the server composer cannot clear the home indicator; the SPA declares cover (static/index.html:5). [High]
3. Unclosed @media (max-width:720px) in style.css:2713 with a one-brace imbalance silently re-scopes global preflight/context-meter rules to phones only. [High]
4. SPA chat composer can be covered by the on-screen keyboard: fixed 100dvh shell (style.css:233-240), internal chat-scroll (733), normal-flow composer (hutch-composer.css:95-105) and no shell visualViewport handling. [High]
5. Touch targets below 44px across otherwise touch-aware surfaces: server nav-toggle 38px (hutch.css:328), generic SPA icon buttons 40px on coarse (style.css:1800), needs-you close on tablets (style.css:1877, 1966), approval filters 30px (1883), runs filter pills ~30px (1298), marketing btn-sm 32px (index.html:255, 269). [Medium]
6. SPA opts into viewport-fit=cover but the primary chrome ignores top/side insets (style.css:425-433, 1683-1688, 1855-1862) and toasts pin 24px from the bottom (1402); notch/home-indicator overlap in standalone/landscape. [Medium]
7. Sticky run header offset breaks when the server topbar wraps: top:54px (hutch.css:114) vs auto-height topbar (hutch.css:304); plus scroll-padding 72px (hutch.css:80). [Medium]
8. Breakpoint system fragmentation: 23 width values from 359 to 1400, adjacent pairs (520/521, 560/561, 640/641, 900/901, 1000/1001, 1023/1024), two sidebar widths (272 style.css:235 vs 304 app/src/input.css:39-43), and no explicit tuning for 320/375/390/768/1024/1180/1366. [Medium]
9. Marketing no-JS overflow (index.html:228 + styles.css:276, 31) and sub-44px header/footer buttons (index.html:255, 269) with no pointer:coarse rules in website/styles.css. [Medium]
10. Residual adaptation debt: dead .receipts min-width rule (website/styles.css:341), min-height:100vh on server pages (hutch.css:57), and a scrollable desktop nav with its scrollbar hidden (hutch.css:90-91). [Low]

# Explicit non-findings (what already works)

- Data tables are consistently wrapped and keyboard-scrollable on server pages (hutch.css:248; templates/usage.html:22, 45, 57, 63; models.html:33, 79, 104; _runs_table.html:2), in SPA widgets (widgets.js:356, 422, 597; app/src/input.css:326) and on marketing (index.html:805).
- SPA renders the densest list (runs) as cards rather than a table (style.css:1196-1212; app.js:7724).
- Form two-up grids collapse at 1000, inline bars stack at 720, and fields use minmax(0,1fr) tracks that survive 200% text size (hutch-form-controls.css:172-174, 225-243; studio.css:956-962).
- iOS focus zoom is prevented with 16px floors on form controls, SPA controls and the composer, with page zoom left enabled (hutch-form-controls.css:248-259; style.css:1930-1935; hutch-composer.css:208-211).
- Popovers are fixed-position, clamped to visualViewport, flip above/below and become a bounded sheet when anchoring cannot fit, with resize/scroll repositioning (controls.js:48-73, 68, 185-188).
- SPA mobile navigation is coherent and accessible: CSS drawer breakpoint matches matchMedia, closed drawer is inert, Tab is trapped, Escape closes, focus is restored, and resize to desktop closes it (style.css:1680-1692; app.js:2504-2543).
- Bottom-sheet modals on phones use 93dvh and a safe-area bottom inset on the footer (style.css:1756-1762).
- Paired-phone supervision is the strongest existing adaptation: 100svh plus env() top/bottom padding plus 48px controls (style.css:2039-2130).
- Reduced motion and full focus-visible coverage are present on app and site (style.css:217-224; hutch.css:83; studio.css reduced-motion blocks; website/styles.css:552-581; website/site.js:9, 97).
- Marketing drawer and availability table are correctly built for small viewports (website/styles.css:280-297, 502-511; website/site.js:47-65).
- Server pages render no modal/dialog markup at all, so SPA-only modal risk does not apply to the Jinja surface.

# Limits of this audit

- Static analysis only: no Playwright/Chromium run, no screenshots, no real iOS/Android/iPad, no computed geometry. Findings are source-derived risks, not observed render failures; the E1 keyboard risk depends on platform behaviour (iOS visual viewport) and should be confirmed in a browser pass.
- Generated CSS was not read per AGENTS.md (ui.css, static/model-switcher.css, website/app.css, website/styles.min.css, website/tokens.css); Tailwind utilities may contribute breakpoint behaviour not visible here, though their config lives in the source files read.
- app.js is 14,345 lines and only the shell, dialog, runs and paired-phone regions were read; route renderers (usage charts, tasks board, campaign report, widgets) can contain additional responsive markup.
- 24 server templates and the remaining static component scripts are listed as backlog in docs/responsive/inventory.md; their responsive risk was inferred from the shared sheets and macros read.
- Not evaluated: Tauri/WebKitGTK desktop host differences, printing, RTL, browser page zoom beyond the 200% note, forced-colors beyond the rule grep, and non-Chromium closedby fallbacks.
