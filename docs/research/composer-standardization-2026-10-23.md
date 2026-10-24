# Composer standardization — 2026-10-23

## Authority and scope

User approved **Unified adaptive**, **chat vision end to end**, and **approve-the-route-before-inference**
in this session. Preserve `DESIGN.md`, vanilla JS/Jinja, local assets, existing form values,
model-route scope, and explicit permissions. No new dependencies, push, or publication is
authorized. Commit reviewed task files progressively; leave the existing uncommitted
memory/runtime/dropdown work untouched.

## Fresh research

Inspected live in Chromium **156.0.8078.4** on 2026-10-23, using interaction, rendered DOM
bounds, computed styles, and real text entry (not screenshots alone):

| Source | Observed | Adaptation / limit |
|---|---|---|
| [shadcn Input Group](https://ui.shadcn.com/docs/components/base/input-group) | One input boundary with block-start header, block-end footer, addons and helper content; footer textarea demo auto-grows (64→96px at 390px width) with a trailing action and character count. | Shared anatomy (context above, writing area, toolbar below), not its 14px text or 24–32px demo buttons. Component demo, not customer evidence. |
| [shadcn Prompt Input](https://ui.shadcn.com/docs/ai-elements/base/prompt-input) | Full-width textarea above a toolbar: attach (32px) left, model + effort chips and send (32px) right; empty send disabled; 18px radius; no horizontal overflow at 390px. | Control placement and honest disabled-empty-send. Coding-specific controls do not transfer. |
| [assistant-ui Composer](https://www.assistant-ui.com/elements/composer) | Composable bar: attachments, 490px input, model trigger (93×32), context ring, voice, send (32px round) in one 10px-padded, 24px-radius, 8px-gap column; one-line input is 44px tall. | Composition model and vertical stacking. Its Send→Stop swap does **not** transfer: Hutch deliberately keeps Send enabled during a run so follow-ups queue. |
| [assistant-ui Attachments](https://www.assistant-ui.com/elements/composer-attachments) | Files stage in the composer with per-file state: `screenshot.png uploading`, `trace.log 38 KB`, 20px remove control, before the message sends. | Per-file lifecycle and removal. A successful upload is never described as proof the model saw the image. |

Community scouting: [bob.fyi AI Elements kit](https://www.figma.com/community/file/1555856339129556457/ai-elements-vercel)
and [Obra shadcn kit](https://www.figma.com/community/file/1514746685758799870/shadcn-ui-kit-community-edition).
Listings were readable; preview-image delivery failed (403 / unsupported image fetch), so no
unseen Figma frame or property is claimed. Live demos above supply the inspected evidence.

### Complaint → regression scenario

- [Open WebUI #16608](https://github.com/open-webui/open-webui/issues/16608): Enter during a
  Chinese IME composition sent the partial message. Hutch already guards `isComposing`/`keyCode
  229`; keep it and test it.
- [assistant-ui #3923](https://github.com/assistant-ui/assistant-ui/issues/3923) (fixed): a
  missed `compositionend` left the composer permanently frozen. Recover composition state on
  the next non-composing input instead of trusting the flag forever.
- [Open WebUI #1721](https://github.com/open-webui/open-webui/issues/1721): Enter-as-send made
  newlines hard on phones. Enter sends by default only under fine pointers; coarse pointers
  default to Enter=newline, and the setting stays per assistant and visible.
- [Open WebUI #31656](https://github.com/open-webui/open-webui/issues/31656): closing a menu by
  outside tap forced focus back into the chat input and raised the iPhone keyboard. Menu
  dismissal must not restore textarea focus under a coarse pointer.
- [Open WebUI #17492](https://github.com/open-webui/open-webui/issues/17492): uploads were
  ignored when the message text was empty. A staged image alone must remain a sendable draft
  state with honest server behaviour, never a silent drop.
- [Open WebUI #8909](https://github.com/open-webui/open-webui/issues/8909): a mobile image-Q&A
  failure froze the thread and hid the error. Failed uploads and failed sends keep the draft
  and the staged file and explain the reason.

Individual reports are scenario evidence, not prevalence statistics or proof that a current
release still has the bug.

## Presented routes and approval

1. **Unified adaptive (approved):** one composer family. Chat gets a full-width writing area
   above a stable toolbar; setup, scheduled prompts, task briefs and inline answers adopt
   purpose-specific variants. More migration work, but consistency without forcing chat
   behavior onto ordinary forms.
2. Compact-first: one-line drafts that expand. Preserves vertical space but adds expansion
   thresholds and toolbar movement to validate.
3. Writing-first: always-expanded editor. Best for long briefs, worst for phone height.

All keep graphite surfaces, emerald actions, azure focus, system-sans text at 1rem or above,
the 8/12/18/22/100 radius scale, and 44px coarse-pointer targets. Behavior and anatomy adapt;
reference branding does not.

## Scope decisions

- **Chat vision is in scope end to end.** Direct chat image input is an integration gap, not a
  missing provider capability: `ConversationMessageRequest` (`server/app.py`) is text-only, the
  composer blocks image paste (`app.js`), and `providers/images.py` already converts image
  references into OpenAI-shaped `image_url` parts for tool-produced frames. The plan wires
  validated upload references into admission and runtime delivery, with an honest refusal when
  the selected route or runtime cannot receive images.
- **User-attached images are message content**, distinct from computer observations.
  `observation_to_hosted` keeps its current meaning (computer observation egress) and is not
  widened. Transmission is recorded honestly either way.
- **Send stays available during a run** so a follow-up queues; the header Stop control remains
  the cancellation path. This deliberately diverges from the reference Send→Stop swap.
- **Real-model inference requires route + spend-cap approval** after local UI and upload QA.
  Until then, model-level vision remains explicitly unverified.

## Acceptance and progress

| ID | Required evidence | Status |
|---|---|---|
| C1 | Shared composer family in one module; chat, first-run, setup, task and inline-answer consumers inventoried | Pending |
| C2 | Chat composer anatomy, focus order, drafts, queue-during-run, IME and phone keyboard behavior | Pending |
| C3 | Attachment picker/paste/drop with real images, per-file states, honest unsupported-route refusal, draft survival | Pending |
| C4 | Built-in runtime delivers image parts only on verified vision routes and records what reached the model | Pending |
| C5 | Opened responsive captures at 1440/900/390/320, 200% text resize, text-spacing override, keyboard pass | Pending |
| C6 | Marketing proof, `DESIGN.md`, design-system, requirements and contract docs updated to verified capability | Pending |
| C7 | Focused/full regression results, two-pass code review, progressive local commits | Pending |

Initial inventory: 27 `<textarea>` call sites in `app.js` (18 request/composer-like, 9 ordinary
fields), one in `computer.js` (remote typing — out of composer scope), one in `widgets.js`
(clipboard helper), plus the Jinja `/bots/{name}/run` compose form. The chat composer is the
only surface with attachments, model/skill switches and a live run relationship today.

### Surface classes (confirmed by source inventory)

Not every textarea is a composer. Migrating ordinary form fields onto the chat box would strip
their label/help semantics and add toolbar affordances they do not need. The plan therefore
treats two classes:

| Class | Surfaces | Adopts |
|---|---|---|
| **Composer box** | chat (`#composer-box`, app.js:3483), first-run request (`.first-run-request`, app.js:3226), phone start (`.phone-start-form`, app.js:12239) | Shared writing-area geometry, 1rem+ text, autogrow, Enter/IME rules. Keeps its own action: chat's circular send; first-run's labeled "Set up my assistant"; phone's labeled "Start work". |
| **Attachment row** | workspace upload chips (`.composer-attachments` / `.upload-chip`, app.js:13265) | Composer-family chips; real thumbnails for images in the vision slice. |
| **Plain form textarea** | assistant instructions, setup purpose/schedule, template editors, workflow inputs/answers, task briefs, receipt evidence, local_dev_origins, runtime source | Stays a normal `<textarea>` with form label/help semantics. Shares only type roles and focus, not the composer chrome. |

This keeps the "unified family" promise scoped to surfaces that actually behave like a request
composer, and avoids a cosmetic reskin of every settings field.

Implementation checkpoints and actual validation results are appended below. No test or
post-change visual pass is claimed by this initial record.

## Checkpoints

### 1. Shared composer module + chat anatomy (committed `db23546c`)

- Added `composer.css` (box, textarea, toolbar, send, util) and `composer.js`
  (`mountAutogrow`, `mountEnterSubmit`, `isComposing`) as the one composer family.
- Restructured the chat composer in `app.js` to the new anatomy: full-width
  writing area (`composer-body`) with `+`/model/send in a `composer-toolbar`
  below, per the shadcn/assistant-ui references. Removed the old inline
  `.composer-row` and the duplicated block in `style.css` (committed `e848f0c5`).
- Autogrow and Enter/IME handling now come from the shared module, so other
  request surfaces adopt them without drift.

### 2. Surface inventory + class split (committed `b8893e39`)

- Inventoried all 27 `app.js` textareas plus the Jinja compose form. Split into
  composer-boxes (chat, first-run, phone-start), the attachment row, and plain
  form textareas that keep normal form semantics — recorded in the table above.

### Visual + behavioral validation (this session, Chromium 156.0.8078.4)

Opened the actual renders at 1440 / 900 / 390 / 320:

- **Chat composer** (`composer-{desktop,phone,compact}-typed.png`): writing area
  spans the full box; `+` lower-left, model chip + emerald send lower-right;
  focus ring visible; no horizontal overflow; 44px send on phone/compact.
- **Popovers** (`popover-plus-{desktop,phone}.png`, `popover-model-*`): the `+`
  menu and model switcher still anchor above the box from the new bottom toolbar;
  on phone the `+` menu becomes the bounded sheet with a "Done" header, fully
  on-screen (not clipped). Escape restores focus to `#composer-menu-btn`.
- **First-run** (`firstrun-desktop.png`): already at 16px text with a comfortable
  writing area and a labeled primary action — adopted the shared writing-area
  token without a cosmetic reskin.
- **Keyboard**: tab order is textarea → `+` → model → send; Shift+Enter inserts a
  newline; Enter opens the `+` dialog but does not toggle it while open.
- **Resilience**: no horizontal overflow at 320px or at 200% root text size.
- **Draft persistence**: survives reload for the same conversation.
- **Honest failure path**: sending on the `mock/demo` route preserves the draft
  and shows "Mock inference is test-only… Your draft is kept" (by design, not a
  regression).
- **e2e**: `tests/e2e/test_design_system.py -k "composer or first_run"` → 3 passed.

### Radius amendment (user direction, 2026-10-23): the composer owns no private shape

User review of the opened captures: the composer's edges were "far too rounded
and not consistent with the overall design of everything else", calling out the
box and its send button individually. The individual component inventory
confirmed it — and found the miss was mine: the earlier pass verified anatomy,
states and responsiveness but preserved the documented 22px/circle exceptions
without re-judging them as a composition.

| Composer component | Was | Now | Why |
|---|---|---|---|
| chat `.composer-box` | 22px (`--r-composer`) | **12px panel** | first-run request box was already 12px — two family members had different shapes; docs reserve 12 for cards/panels |
| `.composer-send` | 36px circle | **40×40 @ 8px** | primary-button proportions; buttons are 8px rounded squares everywhere |
| `+` `.composer-util` | 32px circle | **32×32 @ 8px** | `.icon-btn` proportions; the skill button beside it already rendered at 8px, so one toolbar mixed two shapes |
| `.upload-chip` | 100px pill | **8px row** | the pill role is status chips/badges/counts; a file row is a row |
| `.ms-btn` model trigger | 100px pill | **8px** | a control, not a badge |
| `.cmenu` popover | 18px (`--r-card`) | **12px** | docs put menus/popovers at 12; its sibling `.ms-menu` was already 12 — two composer popovers disagreed |
| `.modal-card` (desktop + phone sheet) | 22px | **12px** | same over-round family; docs already specified 12 for modals — this retired `--r-composer` entirely |
| `.skill-status`, `.ms-tag`, status dots | pill | pill (kept) | genuine status/badge roles per `rounded.chip` |
| `.bubble-image`, chip thumbnails | 8px | 8px | already on scale |

`--r-composer` is removed from `style.css`, `app/src/input.css` and the compiled
`ui.css` (rebuilt with `npm run build:css:app`); `DESIGN.md` frontmatter,
Shapes, Primary button and Composer sections plus `docs/design-system.md`'s
radius row now document the 8/12/18/100 scale with no per-surface exception.
Out of scope and unchanged unless directed: conversation bubbles (18px) and the
connection-setup cards that use `--r-card` (18px where docs say cards are 12).

### Chat vision — scoped, not yet implemented (pending clean file ownership)

The runtime already has `image_url` media transmission (`builtin.py`, used by
`inspect_media` frames) and the upload path carries `mime` + `state`, so chat
vision is a genuine integration gap, not a missing capability. Wiring it is
cross-cutting and additive: `ConversationMessageRequest` needs an attachment
field (absent today), threaded through `submit_conversation_message` → `Run` →
the runtime's media path → a vision-capability gate with an honest refusal when
the selected route cannot receive images.

Chat vision was subsequently **implemented** (commits `dcc85e85`, `a38d3192`,
`34f4c197`): admission validation, the verification snapshot on the run, builtin
delivery with honest capability gates, composer tray staging through picker,
paste and drag-drop, transcript rendering from real bytes, and the e2e journeys
described below. No live provider call was made in that slice; the approved
route gate was exercised on 2026-10-24 with OpenCode's free tier — see the next
section.

### OpenCode model testing with the free tier (2026-10-24): the refusal was wrong

Live protocol probe against a private `opencode serve` (isolated XDG profile, no
host credentials, free port) corrected an assumption this slice had shipped on:

- **The V2 prompt API carries files**: `POST /api/session/{id}/prompt` accepts
  `files: [{uri, name, description?, mention?}]` (`PromptInput.FileAttachment`)
  alongside `text` — image references reach the model; the path is not
  text-only.
- **Capability is per model**: `GET /api/model` reports `capabilities.input`
  lists. Free tier observed: `big-pickle`, `flint-40b-free`, `beam-free` and the
  `nemotron-3-*` models → `["text"]`; **`deepseek-v4.1-flash-free` and
  `nemotron-3.5-super-vl-free` → `["text","image"]`; `glm-5.3-flash-free` →
  image+video+pdf; `mimo-v2.6-flash-free` → image+audio+video**.
- **Keyless free access works** in the private-profile environment: a real
  `glm-5.3-flash-free` prompt returned its answer in ~2.5s at cost 0, and the
  same model described the bundled Google Calendar PNG from a `file://`
  reference ("the Google Calendar app icon — a blue calendar tile with 31").

Changes: `OpenCodeModel` parses `input_modalities`; `prompt()` accepts verified
file references; the runtime verifies each attachment (digest, size, id shape),
stages a copy inside the run's own workspace (`hutch-attachments/` — the session
denies external directories), and refuses non-image models at run start by name.
The blanket "OpenCode receives text only" admission refusal is removed —
capability now lives where it can actually be known: OpenCode's own model list.

**Real end-to-end evidence through Hutch**
(`test_real_opencode_free_vision_model_describes_a_real_image`, live calls, zero
spend): the bundled 96×96 PNG was answered *"It's a calendar app icon —
specifically the Google Calendar style with its signature blue background and
the date '31.'"*, and the real 1440×1000 first-run capture was described as
*"the Hutch app's assistant setup/onboarding screen… 'Your first request'
box… 'AI Service' panel confirming OpenCode is ready with 9 model options"*
(reading the screenshot's own text). The transmission record logged
`{"transmitted": 1, "prepared": 1, "route": "opencode/glm-5.3-flash-free"}`,
and `big-pickle` refused a real image with "does not accept image input".
The runtime suites pass (107) alongside the pending runtime work; 24 hermetic
unit tests cover parsing, file references, the capability gate and staging.
