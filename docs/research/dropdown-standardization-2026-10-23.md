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
| D1 | Shared semantic control family; all select/menu consumers inventoried | In progress |
| D2 | Chat/model/skill/roster focus, refresh, one-message state and mobile discovery | Pending |
| D3 | Setup/settings/schedule/integration/filter/widget/server control coverage | Pending |
| D4 | Marketing navigation/disclosures and affected real-product proof aligned | Pending |
| D5 | Opened responsive captures, real public image/file scenario, keyboard/resilience checks | Pending |
| D6 | Focused/full regression results, code review, docs and progressive local commits | Pending |

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
