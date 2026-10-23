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
