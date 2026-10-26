# Dropdown standardization — 2026-10-23

## Authority and scope

User approved **Unified adaptive controls** and **Public content** validation in this
session. Preserve `DESIGN.md`, vanilla JS/Jinja, local assets, existing form values,
model-route scope, and explicit permissions. No provider inference, private data,
new dependencies, push, or publication is authorized. Commit reviewed task files
progressively; leave the existing uncommitted memory/runtime work untouched.

## Fresh research

Inspected live in Chromium on 2026-10-23, using interaction, rendered DOM bounds,
roles and computed styles (not screenshots of these external demos):

| Source | Observed | Adaptation / limit |
|---|---|---|
| [shadcn menu](https://ui.shadcn.com/docs/components/base/dropdown-menu) | Group labels, separators, reserved icon/shortcut lanes, arrow navigation; 14px labels and 28px demo rows. | Shared action anatomy, not tiny touch rows. Component demo, not customer usability evidence. |
| [shadcn combobox](https://ui.shadcn.com/docs/components/base/combobox) | Typing `nu` retained Nuxt.js; unmatched query showed “No items found.” | Keep query/focus and explicit no-results; do not force search into short enums. |
| [assistant-ui model selector](https://www.assistant-ui.com/elements/model-selector) | Search, provider filters/groups, selected indicator, secondary context line, bounded scroll; 12px panel radius and 52px two-line rows. | Group identity and useful metadata, not unverified model claims or React dependencies. |

Community scouting: [Obra Studio kit](https://www.figma.com/community/file/1514746685758799870/shadcn-ui-kit-community-edition)
and [bob.fyi AI Elements kit](https://www.figma.com/community/file/1555856339129556457/ai-elements-vercel).
Listings were readable; preview image delivery failed in the image-fetch tool.
No unseen Figma frames/properties or license to reuse assets are claimed. AI Elements'
documentation was readable but its live preview was not inspected. Live demos above
provide three examples from two independent libraries; do not call these shipped-product studies.

### Complaint → regression scenario

- [Open WebUI #17307](https://github.com/open-webui/open-webui/issues/17307), closed/fixed:
  typing dismissed the model menu. Keep filtering open and keyboard selection stable.
- [Open WebUI #24578](https://github.com/open-webui/open-webui/issues/24578), closed:
  overlapping model IDs crashed selection. Preserve canonical values; distinguish providers.
- [shadcn #9712](https://github.com/shadcn-ui/ui/issues/9712), open when read:
  choices inside a dialog were visible but unclickable. Keep popup ownership in its
  originating DOM/dialog and test hit targets, focus, scrolling and Escape order.
- [Open WebUI #12093](https://github.com/open-webui/open-webui/issues/12093), converted
  to discussion: mobile switching was undiscoverable to a reporter. Retain a visible
  model label on phone. This is a discovery report, not a confirmed product defect.
- [WAI menu button](https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/) and
  [combobox](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) define distinct semantics.

Individual reports are scenario evidence, not prevalence statistics or proof of current bugs.

## Presented routes and approval

1. **Unified adaptive (approved):** shared anatomy with distinct menu/select/search/
   multi-select/form behavior; larger phone presentation when needed. More validation work.
2. Normalize existing: retain native selects/composition; less risk, platform-dependent
   popup styling and crowded panels remain.
3. Picker-first: short action menus, dialogs/sheets for richer choices; more room but
   more interruption/steps.

All keep graphite, emerald actions, azure focus, system-sans labels, 8px controls,
12px popup panels, and 44px touch targets. Adapt behavior, not reference branding.

## Acceptance and progress

| ID | Required evidence | Status |
|---|---|---|
| D1 | Shared semantic control family; all select/menu consumers inventoried | Implemented; native and popup behavior verified |
| D2 | Chat/model/skill/roster focus, refresh, one-message state and mobile discovery | Focused browser checks pass |
| D3 | Setup/settings/schedule/integration/filter/widget/server control coverage | Shared styling applies to all 66 declarations; representative journeys verified, broader route sweep pending |
| D4 | Marketing navigation/disclosures and affected real-product proof aligned | Verified; unaffected genuine first-run proof retained |
| D5 | Opened responsive captures, real public image/file scenario, keyboard/resilience checks | Verified at recorded scope; limitations below |
| D6 | Focused/full regression results, code review, docs and progressive local commits | Three slices committed; final review corrections and full offline regression pending |

Initial static inventory: 54 selects in `app.js`, two in `persona.js`, one in
`widgets.js`, nine in Jinja templates; setup has a model datalist. Native select,
action menus, model radio menu/full picker, skill checklist, mixed composer/chat
popovers and inline disclosures must not collapse into one ARIA role.
The 2026-10-23 holistic capture hashes match current app/style/skills/site source.
Older menu captures were inspected for context, not current regression certification.

Implementation checkpoints and actual validation results are added below. No tests
or post-change visual passes are claimed by this initial record.

### Foundation checkpoint

- Implemented shared popup styling/lifecycle and semantic select enhancement in
  `controls.css`/`controls.js`, loaded by SPA and server pages. Pure settings/fleet
  action menus and the mixed chat-options popover consume the controller.
- Native select remains authoritative; `appearance: base-select` customizes the
  browser picker where supported rather than hiding/reimplementing form controls.
  Other engines retain a usable native fallback. No new dependency was installed.
  Keyboard consequence (found when a routine-editor e2e failure triaged on
  2026-10-25): under `base-select` a closed select's first ArrowDown opens the
  picker instead of cycling the value, so keyboard selection flows are
  Down → Down → Enter (see
  `tests/e2e/test_browser.py::test_routine_editor_links_an_activated_workflow_accessibly_across_viewports`).
- Explicit QA executable: cached Chromium **156.0.8078.4**, configured through
  `HUTCH_TEST_CHROMIUM_EXECUTABLE`; default Playwright expects a missing build.
- `tests/e2e/test_dropdown_controls.py`: **6 passed**; genuine settings save/reload
  at 1440/900/390/320, action-menu keyboard/Tab/Escape and an additional hostile
  native-dialog/40-choice clipping and scroll fixture. `tests/test_site_tokens.py`:
  **8 passed**. The initial broad command named nonexistent `test_server.py` and
  ran no tests; it is not counted. Restart-cancelled runs are not counted.
- Opened `/tmp/opencode/hutch-dropdowns/dropdowns/select/open-1440.png` and
  `open-320.png`: graphite popup, aligned check lane and readable rows; narrow
  picker flips above the trigger within the viewport. Remaining screenshots and
  real-public-content journeys are still pending, not implied by this checkpoint.
- Next slice: migrate model/skill/composer/roster behavior to the shared controller,
  preserve refresh focus and next-message semantics, retain visible phone labels.

### Chat and catalog checkpoint (implementation in progress)

- Model, skill, composer and roster popups now use the shared controller. Skills
  use a searchable native-checkbox form, update checks in place and retain focus;
  model names remain visible on phone, with a separate utility row preserving the
  writing area. Suggestions/usage are optional composer disclosures; Done stays
  reachable in a sticky popup header. Model choices expose canonical route IDs.
- Setup's datalist is progressively enhanced into a typing-focus-preserving
  combobox; its original input/value/validation and arbitrary explicit routes
  remain intact. Search renders at most 100 suggestions and reports truncation.
- Existing selected browser regressions: **9 passed** (model override/default,
  full picker, delayed OpenRouter discovery, phone bounds, large roster and
  rehearsal behavior); skill send/consume: **1 passed**. New control checks:
  **10 passed**, plus separate setup/public-image checks **2 passed** before
  the latest long-filename correction. Final frozen-source rerun is pending.
- A genuine public **593,338-byte NASA Blue Marble JPEG** was downloaded from
  `https://upload.wikimedia.org/wikipedia/commons/7/7b/Earth_Western_Hemisphere.jpg`
  after reading its [credit/public-domain page](https://commons.wikimedia.org/wiki/File:Earth_Western_Hemisphere.jpg).
  SHA-256: `b79e0577e7565a2c7e9f7165284ccb53ece2872ddc429c687b6d3ae1aaa85780`.
  Actual browser file chooser → local upload endpoint → persisted attachment and
  draft reload succeeded, with zero runs and zero external app requests. This
  verifies workspace file storage, **not model vision or image-chat input**.
- Opened real-image, setup, skills, model and composer captures. The real image's
  long filename exposed a clipped remove button missed by the short fixtures;
  shrinkable chip tracks and a bounds regression now address it (rerun pending).
  Updated the composer explanation to distinguish workspace image files from
  unsupported direct image input, instead of contradicting its file chooser.
- Regression discovery caught async catalog growth escaping the viewport. A
  shared ResizeObserver and explicit refresh placement correct this; the delayed
  OpenRouter regression passed afterward. Historical failures remain in tool
  logs and are not counted as final passes.
- Remaining: frozen-source checks/captures, marketing alignment, select-surface
  matrix/resilience, review and final documentation. No private keys or inference.

Chat/catalog slice rerun: **12 passed**, including the real NASA file and the
long-filename remove-button bounds check. Opened the corrected real-image phone
capture and setup suggestions capture: remove action remains visible, the file
label truncates without hiding its full accessible name, and the route input uses
the shared 44px field geometry. Broad offline regression is now running on
root-filesystem scratch, not the nearly full shared `/tmp` tmpfs.

### Marketing checkpoint

- Native site navigation now has the shared graphite surface, 12px panel / 8px
  link geometry, 44px targets, bounded scrolling, and dedicated header/footer.
  Trigger ownership and native modal semantics remain explicit; the responsive
  close threshold now matches the 1024px CSS breakpoint. Section links are not
  mislabeled as application menu items. FAQ focus uses one azure outline.
- Added truthful phone-model/one-message/default copy. Existing first-run proof
  is unaffected (no changed picker appears in that capture), so it was retained
  rather than replaced with a synthetic chat. Assets rebuilt and cache keys stamped.
- **8 website checks passed**: responsive menu/disclosures at 1440/900/390/320,
  native Escape/focus restoration, no-JS readability, local asset hashes and no
  external requests. Opened navigation at 320/390/900 and expanded FAQ at 1440;
  row alignment, readable names and reachable Close/availability action confirmed.
- Four existing design-system checks also passed after updating pure action-menu
  test queries to their correct `menuitem` role: settings header, shared tokens,
  settings disclosure axes and persona round-trip/conflict behavior.

## Consumer matrix

| Family | Consumers / authority | Migration and evidence |
|---|---|---|
| Native selected values | `app.js` (54 declarations: settings, routing, permissions, schedules, integration grants, conversation/filter/destination choices); `persona.js` (2 templates); `widgets.js` (timeline filter); Jinja templates (9) | All consume `controls.css`; names, values, `change`, required/disabled/reset and native form submission remain unchanged. Representative live workspace save/reload, nested chat choice, server/no-JS form-data and existing persona/settings tests pass. This is not an individual test of every enum in every state. |
| Editable route | Setup `input[list]` | Preserves explicit input value and validation; accessible listbox suggestions, stable input focus, provider-qualified IDs, no-match state and 100-row bound verified. |
| Pure actions | Roster, assistant settings, fleet card | Shared menu lifecycle; arrows/Home/End/typeahead, Escape/Tab, outside press and teardown. Existing pin/default/fleet checks remain applicable. |
| Model choice | Composer menu + full modal | Five-choice quick path, canonical identities, current/default check, separate save-default action, searchable full list. Delayed discovery and detached-view guards protect state. |
| Multi-select | Skills | Searchable checkbox form, not nested menuitem-checkbox/native-checkbox roles. Changes do not replace focused rows. Send/consume contract unchanged. |
| Mixed forms | Composer and conversation options | Nonmodal dialog popovers with normal form Tab order, sticky Done, bounded scrolling; native picker Escape does not dismiss its parent. Optional content stays in inline disclosures. |
| Inline disclosures / navigation | Settings, schedule assistant chooser, site FAQ and mobile navigation | Inline disclosure semantics retained; site section links remain links inside a native modal, with app-compatible geometry/focus. |

## Distinct code-review passes

Reviewed this task's committed delta from `eff7ebd2^` plus its in-scope uncommitted
corrections. Excluded the unrelated memory/runtime/store/ADR working-tree changes.
This was a **self-review**, not an independent-agent or security certification.

Requirements pass found and corrected:

- Async model discovery could increase popup height past the viewport: explicit
  placement plus ResizeObserver; delayed OpenRouter regression passed afterward.
- Native select Escape was intercepted by its parent popover: preserve browser
  default dismissal and stop outer handlers; dedicated nested-select test passes.
- A late “All models” response could open a dialog after leaving chat: detached
  slot/search guards; delayed-response navigation regression passes.
- Public-photo filename overflow hid the remove button: shrinkable grid/flex
  tracks, full accessible filename and 44px remove control; real JPEG bounds pass.

Standards/accessibility pass corrected the autocomplete's result status to be a
persistent sibling of the owned listbox options, kept canonical provider IDs in
the full model list, and removed hidden file inputs from popup Tab order. Text
passes 4.5:1 in the targeted browser check.

Follow-up visual review (user-reported colour mismatch, 2026-10-23): the first
cut set `--control-line` to an opaque `color-mix(text-3 70%, panel)` ≈ `rgb(92,106,124)`
to chase a standalone 3:1 boundary. That made every dropdown edge a bright grey
that matched none of the design system's white-alpha hairlines — visible in the
composer, model, skills, setup and server-page screenshots the user flagged. It
was reverted to `--color-semantic-border-strong` (`rgba(255,255,255,0.14)`, the same
`--line-strong` used by the pre-existing `.cmenu`/`.ms-menu`/inputs), with internal
separators at `--color-semantic-border` (`0.07`, matching `.cmenu-sep`). The popup
header title moved from muted to primary text for clearer hierarchy, and the three
iconless composer actions (Import task-template, Export conversation, Review cost)
received icons so the action list is visually consistent. A computed-style regression
(`test_popup_edges_and_surfaces_match_design_tokens`) now asserts the app popover and
server-page select resolve their border and surface to the same design-system tokens,
normalised through the browser so no hex is hardcoded — this cannot drift again.

Latest new-control suite: **19 passed**, including real public JPEG storage,
hostile modal clipping/scroll, no-JS server form values, 100-result bound, stale
navigation, emulated missing Popover API, forced colors, reduced motion,
320px simultaneous WCAG text-spacing tolerance overrides, and the new
design-token edge/surface regression. `node --check` passes for changed
application scripts; `git diff --check` passes.

Broad route sweep: `test_every_workspace_route_renders_independently_at_responsive_sizes`
and `test_chat_library_recovers_history_beyond_quick_switcher_and_workspace_settings`
**2 passed** (1440/900/390/320) — the native-select surface covers every
settings, schedule, integration, filter, and history route without overflow.
Guided assistant creation **1 passed** after making every "Model route" test
query exact, so it targets the input and not the new suggestion listbox.

Full offline suite (`pytest --ignore=tests/e2e`): **3284 passed, 8 skipped, 6 xfailed,
4 failed** in 26m31s on root-filesystem scratch (the shared `/tmp` tmpfs was 97% full).
All four failures were environment artifacts, not dropdown behavior: two
`AF_UNIX path too long` from an over-long `TMPDIR` exceeding the 108-char socket
limit, one 1000-events/s disk benchmark on the slow root fs instead of RAM, and one
Playwright launch that bypassed the shared `launch_browser` helper. The two path and
benchmark tests **3 passed** in 2.57s when re-run with a short RAM-backed `TMPDIR`.
The fourth now routes through `launch_browser` and **1 passed** in 10.08s with the
explicit QA executable. These four were environment-blocked before this work, so
none is attributed to the dropdown changes.

Mechanical Impeccable detector ran once across changed targets. It reported only
three pre-existing advisories outside the changed controls: a 4px radius and
`#e1e5e9` in `style.css`, and an 11px marketing metadata role already documented
in `DESIGN.md`. They were not silently “fixed” as unrelated redesign work.

### Verification limits

Screenshots were opened and inspected, not merely saved. Checked 1440/900/390/320
layouts and relevant expanded/selected/error/overflow states. Real public imagery
supplements, rather than replaces, deterministic edge-case fixtures. No live model
quality/vision, hosted-provider billing, physical phone, Safari/Firefox, assistive
screen-reader or actual browser/text zoom pass is claimed. Text-spacing/reflow
and forced-colors emulation do not establish complete WCAG conformance or a
measured usability/aesthetic score. Browser-native select appearance is necessarily
platform-dependent where customizable select is unsupported.
