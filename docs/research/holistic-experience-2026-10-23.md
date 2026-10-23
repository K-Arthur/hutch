# Holistic experience review — 2026-10-23

## Scope and checkpoint

App and marketing experience, including navigation, setup/settings placement,
menus/selects, disclosure behavior, typography, containers, icons and shared controls.
Prior first-run approval does not approve this expanded work. No implementation yet.
Preserve local-first permissions, factual claims and the current brand/tokens while
choosing a composition and interaction approach. User requests progressive commits,
documentation, visual validation, review, integration and worktree cleanup after approval.

## Evidence inspected

Six user screenshots: Skills, FAQ, example requests, first run, Activity, and the
three-step marketing section with its first disclosure expanded.

Observed: Activity has three unrelated content widths; Skills combines wide cards,
distant actions and a large empty-state gap; example icons have inconsistent framing;
FAQ has one visibly unstyled row; expanded step copy stretches peer cards into largely
empty columns. First run has multiple layers of explanatory copy around its main task.

Source confirmation: website/index.html line 662 lacks the collapse-title class used
by adjacent FAQ summaries. app.js openModal is a shared dialog mechanism with wide/tall
variants and unconditional backdrop/Escape dismissal; suitability and recovery need
workflow-specific testing before changing behavior. Settings includes native selects;
closed-control screenshots do not establish opened-menu consistency.

Fresh local desktop captures inspected: chat (readiness still checking), workspace
settings, marketing hero, at 1440x1000. Temporary evidence:
/tmp/opencode/hutch-holistic-review/{chat,settings,website}.png.
Playwright's default browser executable was missing; existing Chromium 1248 worked
via explicit executable_path, with no installation. Review servers restarted at
18890 and 8099 after host restart; these are the user's existing review servers.
Phone, tablet, open native dropdown, modal journeys and accessibility are not yet verified.

## Public research

Access date: 2026-10-23. Actual public preview images downloaded and opened, not just
search snippets. These are design-kit examples, not shipped-product usability evidence.
No assets or code licensed for reuse by this research.

1. shadcncraft Settings: https://shadcncraft.com/pages/settings
   Preview: https://assets.shadcncraft.com/images/pages/settings-preview-dark.webp
   Observed aligned label/control columns, section separators, category tabs and a
   consistent save/discard location. Useful for persistent configuration. Do not copy
   enterprise account navigation, billing, branding or its generous row heights wholesale.
2. shadcncraft FAQ: https://shadcncraft.com/pages/faq
   Preview: https://assets.shadcncraft.com/images/pages/faq-preview-dark.webp
   Observed consistently framed icons and unboxed short answers in aligned columns.
   Useful for concise overview content; its large hero and multi-column answers are
   unsuitable for Hutch's long technical explanations.
3. Obra Studio Community component preview: https://shadcn.obra.studio/
   Community: https://www.figma.com/community/file/1514746685758799870/shadcn-ui-kit-community-edition
   Preview: https://shadcn.obra.studio/blog/demo.png
   Observed coordinated button variants, inputs, badges, icon buttons and disclosure
   affordances. Useful for a single control grammar, not a reason to adopt React,
   copy the light palette or make all controls circular. Figma fetch returned no usable
   content; inspected the creator's public preview instead. Exact Figma properties,
   interaction states and responsive behavior were not retrieved.

## Routes presented for approval

All retain graphite/emerald, Archivo headings, system-sans prose and existing token
values; normalize their roles, spacing, icon sizing and control application.

1. Task-first pages (recommended): stable app navigation, aligned page headers and
   content rails; dedicated setup/configuration pages; dialogs for short decisions.
   Marketing uses short steps with shared full-width explanatory content below,
   not expanding text inside equal-height columns. Moderate density, restrained
   headings. Explicit save/cancel and draft recovery; inline errors/loading; phone
   stacks in reading order. References: shadcncraft Settings/FAQ, Obra controls.
   Tradeoff: more route/navigation work and occasional departure from conversation.
2. Contextual workspace: chat stays primary; configuration/review in one consistent
   side panel, full-screen on phones; full pages for libraries. Marketing ties each
   short step to a contextual explanation/proof panel. Compact type and density using
   the same tokens. Clear panel title/back/close, preserved draft and focus, local
   loading/errors. References: Settings label/control alignment adapted to panels,
   Obra controls, FAQ concise overview. Panel placement is a proposal, not an inspected
   interaction in those previews. Tradeoff: limited width and more panel-state complexity.
3. Guided task flows: explicit setup/connect/review steps with a visible summary;
   stable library/settings destinations for repeat use. Marketing follows the same
   sequence vertically with explanations at reading width. More spacious forms,
   same typography/color roles; Back/Continue, retained drafts, step-local validation,
   single-column phone flow. References: Settings grouped fields, FAQ short answers,
   Obra controls. Wizard behavior is a proposed adaptation, not observed reference
   behavior. Tradeoff: extra steps for experienced users and greater flow restructuring.

Approval: user selected **Task-first pages (Recommended)** through the direction
question on 2026-10-23. Next: inventory representative workflows,
implement shared foundations and complete workflow slices, validate desktop/tablet/phone
and expanded/loading/error/focus/empty states, review, progressively commit and integrate.

## Implementation checkpoint

Worktree: `/home/kevina/.local/share/opencode/worktree/5b4899/holistic-experience`.
Original checkout has unrelated backend/test edits; preserve them during integration.
Marketing slice: moved long step disclosures below the overview, increased explanation
prose to the existing body token, and restored the missing FAQ summary class. No factual
content removed. Site CSS built successfully using the existing node_modules via symlink.
Rendered captures at 1440, 768 and 390 opened: overview no longer stretches, reading
measure expands appropriately; screenshots caught scroll-reveal transitions on mobile,
so final evidence must use settled animation or reduced motion. Browser measurements
confirm unchanged card heights after expansion (0.1px tolerance for float precision),
no page overflow and consistent FAQ font sizes. Evidence is temporary under
`/tmp/opencode/hutch-holistic-review/`. Added keyboard/geometry regression coverage;
focused pytest passed: 5 tests (three responsive keyboard/geometry cases, existing
workflow copy, and current asset hashes), 31 deselected. Used existing Chromium 1248
through a process-local Playwright launch override because the installed Python
package's default browser revision is absent. This is a partial slice, not whole-product validation.

Remaining: app shared page/control rules; setup/configuration journeys; Skills/Activity
layouts; marketing icon and technical-content layouts; rendered state matrix; test
suites; code review; progressive integration and cleanup. Existing surface brief for
marketing contains stale square/brutalist guidance; current DESIGN.md and this approved
route take precedence. No unrelated brief repair undertaken.
