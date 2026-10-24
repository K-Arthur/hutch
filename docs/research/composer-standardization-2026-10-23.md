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

Implementation checkpoints and actual validation results are appended below. No test or
post-change visual pass is claimed by this initial record.
