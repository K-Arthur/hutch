# Research — measured UI audit, 2026-10-22

Searches ran on 2026-10-22. Standards and official documentation are treated as authority;
practitioner articles as supporting evidence; forums only as complaint signals. The plan cites only
sources listed here.

## Track A — what works

| ID | Source | Date | Used for |
|---|---|---|---|
| A-1 | W3C, [F104: clipped or overlapped content when text spacing is adjusted](https://www.w3.org/WAI/WCAG22/Techniques/failures/F104) | updated 2026-01-12 | Text-spacing stress pass (1.4.12): fixed-size containers with hidden overflow are the failure mode to look for. |
| A-2 | W3C, [C43: using CSS scroll-padding to un-obscure content](https://www.w3.org/WAI/WCAG22/Techniques/css/C43) and [F110: sticky footers/headers hiding focused elements](https://www.w3.org/WAI/WCAG22/Techniques/failures/F110.html) | WCAG 2.2 techniques | F-05 reminder clearance, server-page topbar `scroll-padding-top`. |
| A-3 | W3C WAI-ARIA APG, [Switch pattern](https://www.w3.org/WAI/ARIA/apg/patterns/switch/) and [Button pattern (toggle buttons)](https://w3.org/WAI/ARIA/apg/patterns/button) | current APG | D-02: `role="switch"` + `aria-checked` for on/off settings; toggle-button labels must not change with state (Hutch's Pause/Resume labels did). |
| A-4 | NN/g, [Toggle-Switch Guidelines](https://www.nngroup.com/articles/toggle-switch-guidelines/) (A. Kendrick) | 2018-07-29 | D-02: switches for immediate binary system settings; label names what is on; radios/checkboxes when a Save step applies (D-04 judgment). |
| A-5 | W3C Working Group Note, [Making Content Usable for People with Cognitive and Learning Disabilities](https://www.w3.org/TR/coga-usable/) | 2021-04-29 | Text load and pacing: 4.4.5 keep text succinct, 4.4.10 use white spacing, 4.6.3 avoid too much content, 4.9.1 let users control when content moves or changes, 4.2.3 consistent design. |
| A-6 | Practitioner: [When streaming tokens meet the screen reader](https://tianpan.co/blog/2026-06-29-streaming-tokens-meet-the-screen-reader) | 2026-06-29 | Confirmed Hutch's bounded `#live-status` announcer is the right pattern (status, not the stream); no change needed. |
| A-7 | Design-system docs on single-choice groups: [eBay toggle button group](https://opensource.ebay.com/evo-web/components/toggle-button-group/accessibility), [Genesys segmented control](https://spark.genesys.com/latest/components/forms-and-inputs/segmented-control/accessibility-QWssAGSL) | current | D-03: an `aria-pressed` group is not a radio group; mutually exclusive choices need radio semantics and arrow keys. |
| A-8 | MIT 6.813, [Layout](https://web.mit.edu/6.813/www/sp18/classes/14-layout) | 2018 | Proximity and white space for grouping; insufficient white space slows scanning (D-09). |

## Track B — what failed elsewhere

| ID | Source | Date | Lesson applied |
|---|---|---|---|
| B-1 | [CMSWire on the Sonos app redesign](https://www.cmswire.com/customer-experience/sonos-app-redesign-fail-customer-outrage-and-falling-stock-prices); [Tom's Guide](https://www.tomsguide.com/audio/speakers/sonos-is-returning-the-features-its-courageous-app-redesign-left-behind) | 2024 | Parity first: every change keeps the same controls and paths; component swaps keep hooks and are tested for keyboard and screen-reader behaviour. |
| B-2 | iOS 26.1 "Tinted" Liquid Glass: [TidBITS](https://talk.tidbits.com/t/ios-26-1-to-add-optional-opacity-to-liquid-glass/32182), [Six Colors](https://sixcolors.com/post/2025/11/soaping-up-liquid-glass-less-transparency-more-contrast/) | 2025-11 | Legibility beats effects; Hutch keeps opaque graphite surfaces (no translucency added). |
| B-3 | [Bitwarden 2024.12 redesign thread](https://community.bitwarden.com/t/usability-issues-ux-in-redesigned-ui-2024-12-0/76836) | 2024–2025 | Density and one-click actions matter to frequent users: the chat header wraps only when it must; no actions moved into menus. |
| B-4 | FTC v. accessiBe ([FTC legal library](https://www.ftc.gov/legal-library/search?page=44)); final order April 2025 | 2025 | No overlays; fixes are in source. |
| B-5 | [GitHub colour-blind themes beta](https://github.blog/changelog/2022-04-19-protanopia-deuteranopia-colorblind-themes-beta/) and [community report that status hues collided](https://github.com/community/community/discussions/44944) | 2022–2023 | Hue swaps alone can still collide; D-08 adds shape (✕) rather than re-tuning hues. |

## Track C — complaints a front end can fix

| ID | Source | Date | Mapped to |
|---|---|---|---|
| C-1 | [OpenAI community: "The ChatGPT web interface is not accessible to blind users"](https://community.openai.com/t/the-chatgpt-web-interface-is-not-accessible-to-blind-users/803550) | undated thread | Keyboard/screen-reader operability of core controls → F-01, F-02, F-03, F-18. |
| C-2 | [AppleVis: regressions with VoiceOver and NVDA](https://applevis.com/comment/211605) | 2026-07-12 | Controls activating the wrong thing / unreachable options → F-02 (trap), D-03 (radio semantics). |
| C-3 | Leporini & Buzzi, [preliminary screen-reader evaluation of AI tools](https://arpi.unipi.it/handle/11568/1365967) | 2025 | Navigation structure and feedback clarity → F-13 landmark, F-18 focus continuity. |
| C-4 | Hutch's own complaint research, [`docs/research/complaints.md`](../../../research/complaints.md) (Open WebUI #30055 overlay covering delivered content; #31656 iOS keyboard/focus) | 2026-10 | Overlays covering content → F-04, F-05, F-06; iOS focus behaviour → F-10. |
| C-5 | [odysseus #6095: sending drops composer focus](https://github.com/odysseus-dev/odysseus/issues/6095) | 2026 | Focus loss after re-render → F-18 and the Runtime focus fix in D-02. |

Out of front-end scope: provider limits, pricing, model quality.

## Track D — technical ground truth

| ID | Source | Date | Finding |
|---|---|---|---|
| D-1 | MDN `inert` (Baseline since April 2023; Chrome 102, Firefox 112, Safari 15.5) | 2026 | Safe for F-03. Note: `HTMLElement.click()` is ignored on inert elements, which is why Needs you is opened directly. |
| D-2 | [Chrome: keyboard-focusable scrollers](https://developer.chrome.com/blog/keyboard-focusable-scrollers) | Chrome 130 | Chromium focuses scrollers itself; no WebKit equivalent found, so F-09 keeps explicit `tabindex`. |
| D-3 | iOS focus zoom below 16 px: [CSS-Tricks](https://css-tricks.com/?p=339455), [Rick Strahl 2023](https://weblog.west-wind.com/posts/2023/Apr/17/Preventing-iOS-Textbox-Auto-Zooming-and-ViewPort-Sizing), [HeroUI #5326](https://github.com/heroui-inc/heroui/issues/5326) | 2023–2025 | F-10: 16 px floor; never `maximum-scale`. No 2025 source showed a change in Safari behaviour (needs a device check). |
| D-4 | Container queries: [Zell Liew](https://zellwk.com/blog/container-queries-best-practice), [Ahmad Shadeed](https://ishadeed.com/article/css-container-query-guide) | 2023–2025 | F-07: a grid item can be a size container if its width comes from the track. |
| D-5 | `all: unset` clears `outline`: [W3C www-style thread](https://lists.w3.org/Archives/Public/www-style/2015Mar/0303.html), [OpenReplay](https://blog.openreplay.com/remove-native-styles-css-all-unset/) | 2015; 2025 | Root cause of F-01; element+class reset selectors outrank `:focus-visible`. |
| D-6 | Forced colours: [MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors), [csswg #6310](https://github.com/w3c/csswg-drafts/issues/6310) | current | Backgrounds/gradients are overridden; the new switch and radio segments use explicit system colours. |
| D-7 | [axe-core 4.11 release notes](https://docs.deque.com/axe-release-impact/4.11.0/en/release-notes) | 2025 | `target-size` and best-practice tags; audit used axe-core 4.14.0. |
| D-8 | Machado, Oliveira & Fernandes (2009), CVD simulation; matrices as implemented in [colour-science](https://colour.readthedocs.io/en/latest/colour.blindness.html) | 2009 | D-08 measurement (protan/deutan reliable; tritan approximate). |
| D-9 | Toast timing: [Scott O'Hara, "A toast to a11y toasts"](https://scottohara.me/blog/2019/07/08/a-toast-to-a11y-toasts.html), [W3C WAI-IG discussion of 2.2.1 scope](https://lists.w3.org/Archives/Public/w3c-wai-ig/2025AprJun/0076.html) | 2019; 2025 | D-06: pause on hover/focus, length-based duration; errors persist. |

## Rejected ideas

- Raising the global `:focus-visible` specificity (would add a second ring where components draw focus on a container, e.g. the composer).
- Icon-only Review/Stop between 901 and 1279 px to keep a one-row header (hides labels people rely on).
- A fixed reminder under a measured header at 641–900 px (still covers the top of the feed).
- Re-tuning status hues for colour blindness (B-5 shows hue swaps can still collide; shape is more robust).
- Converting every short `select` to radios (would lengthen settings pages, against the text-load goal).
