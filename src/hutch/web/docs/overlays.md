# Hutch overlay design specification

This is the quality bar for every modal and popover in the product. It is the
contract behind `src/hutch/server/static/hutch-overlays.css`,
`src/hutch/web/styles/hutch-tokens.css`, the runtime modules
`src/hutch/server/static/hutch-overlay-*.js`, and the Jinja macros
`src/hutch/server/templates/macros/{modal,popover}.html`.

The token layer is authoritative; this sheet is the shipped mirror that makes the
same tokens available to server-rendered pages. If a value changes in
`hutch-tokens.css`, change the mirror in `hutch-overlays.css` too.

## Artifacts

| Artifact | Path | Role |
| --- | --- | --- |
| Tokens | `src/hutch/web/styles/hutch-tokens.css` | Source of the z/scrim/elevation/motion/focus families |
| Light theme | `src/hutch/web/styles/hutch-theme-overrides.css` | Per-theme scrim opacity and elevation |
| Shipped sheet | `src/hutch/server/static/hutch-overlays.css` | Token mirror + modal primitive |
| Shipped sheet | `src/hutch/server/static/hutch-popovers.css` | Popover/dropdown/tooltip primitives + surface adoption |
| Runtime | `src/hutch/server/static/hutch-overlay-{core,dialog,modal,popover,tooltip}.js` | Behaviour |
| Markup | `src/hutch/server/templates/macros/modal.html` | Server-rendered modal + destructive confirm form |
| Markup | `src/hutch/server/templates/macros/popover.html` | Server-rendered popover shell |
| Audit | `docs/overlays/audit.md` | Matrix, gap list, decisions |

## 1. Elevation hierarchy

Four floating categories, strongest to lightest, so a person can read how far a
surface sits above the page before reading its content:

| Category | Elevation token | Z token | Visual job |
| --- | --- | --- | --- |
| Modal | `--hutch-elevation-overlay-modal` | `--hutch-z-modal: 50` | Highest floating surface, scrimmed, page blocked |
| Popover (rich) | `--hutch-elevation-overlay-popover` | `--hutch-z-popover: 46` | Pickers, form popovers, review panels |
| Dropdown menu | `--hutch-elevation-overlay-dropdown` | `--hutch-z-dropdown: 44` | Action lists and menubar panels |
| Tooltip | `--hutch-elevation-overlay-tooltip` | `--hutch-z-tooltip: 42` | Descriptive only, lightest depth, never interactive |

The z ordering is deliberately not a copy of the elevation order: a tooltip is
the lightest surface (least shadow) but must still be readable above arbitrary
content, so it is a positioned layer with the lowest floating z value. Modals
and popovers stack in the native top layer, where the browser owns ordering and
the z numbers are inert. `--hutch-z-toast: 60` sits above every dialog (a
receipt for an action must be visible even while a dialog is open) and
`--hutch-z-skip: 70` remains the skip-link escape hatch. Base content is 0.

No overlay stylesheet may declare `z-index` with a literal after this pass.

## 2. Scrim (modals only)

- Only the **Modal** category gets a scrim. Popovers, dropdowns and tooltips
  never dim the page.
- Tokens: `--hutch-overlay-scrim-color` (the deepest ink), `--hutch-overlay-scrim-opacity`
  (0.72 dark, 0.52 light), `--hutch-overlay-scrim-strong-opacity` for the
  non-dismissible destructive case, `--hutch-overlay-scrim-blur` (0 by default -
  blur is opt-in when a host has a compelling reason).
- Implementation: `dialog::backdrop`. Stacked dialogs each add their scrim, so
  depth reads correctly; the topmost dialog owns dismissal.
- The scrim is never a colour surface: in both themes it is an ink material that
  dims whatever is behind it. Only its opacity adapts per theme.

## 3. Motion choreography

All motion comes from `--hutch-motion-overlay-*`; no component declares a
duration or easing literal.

| Category | Enter | Exit |
| --- | --- | --- |
| Modal | opacity 0 -> 1, translateY(10px) -> 0, scale(.985) -> 1; 180ms decelerating from the dialog origin | opacity -> 0, translateY(5px), scale(.99); 120ms; pointer-events none immediately |
| Popover / dropdown | opacity 0 -> 1, scale(.985) -> 1 from `transform-origin` derived from the final placement (above/below/left/right of the anchor); 180ms | opacity -> 0, translateY(-3px), scale(.99); 120ms; pointer-events none immediately |
| Tooltip | same shape as popover, 180ms, origin from the computed placement | 120ms fade |
| Toast / status | existing toast motion is out of scope; it consumes the same duration family |

Rules:

1. Exit never blocks the surface it reveals. On close the panel becomes
   `pointer-events: none` immediately, focus moves synchronously, and the node is
   removed after the exit duration.
2. `@media (prefers-reduced-motion: reduce)` collapses every enter/exit duration
   to 1ms, removes travel, and keeps the state change (open, focus movement,
   scrim appearance) intact. The product's explicit Reduce effects switch does
   the same.
3. Motion is compositor-only (`opacity`, `transform`). No width, height, top or
   left animation.

## 4. Density and spacing

One 4px grid; sizes are token reads only.

| Size | Width | Use |
| --- | --- | --- |
| `data-size="sm"` | 420px | Confirmations, short decisions |
| `data-size="md"` | 640px | Default form dialog / review |
| `data-size="lg"` | 780px | Dense forms, plan review |
| `data-size="xl"` | 960px | Wide readers (documents, amendments) |
| `data-variant="sheet"` | min(580px, 100vw) right sheet | Needs-you review only |

| Spacing | Token | Value |
| --- | --- | --- |
| Header padding | `--hutch-space-5` / `--hutch-space-3` bottom | 24 / 12 |
| Title to description | `--hutch-space-3` | 12 |
| Description to body | `--hutch-space-4` | 16 |
| Body padding | `--hutch-space-4` / `--hutch-space-5` | 16 / 24 |
| Body to actions | `--hutch-space-3` | 12 |
| Action gap | `--hutch-space-2` | 8 |
| Body scroll | `.hutch-modal__body { overflow-y:auto; overscroll-behavior:contain }` | page never scrolls behind a dialog |

Close control: 40px square (44px on coarse pointers), top-right of the header
row, labelled "Close <dialog title>" (or the caller's `closeLabel`), shared
`--hutch-focus-ring`, and never part of the action row. Rich popovers use the
same close placement inside their sticky `.hc-popup-header`.

At <=480px the modal fills the available width, actions become full-width and
stack, and the body keeps its own scroll. At <=480px height the dialog caps at
`100dvh - 16px`. At 200% zoom the title wraps, actions wrap, and no control is
clipped.

## 5. Action placement

One rule for every dialog and nothing else invents an order:

1. **Only one primary action**, the rightmost button. Its label is a verb
   phrase naming the outcome: "Save name", "Delete model", "Allow background
   use", "Start workflow". Never "OK".
2. **Cancel is always present and always immediately left of the primary**
   ("Cancel"), except read-only dialogs whose only action is "Close" - then
   there is one quiet button and no cancel.
3. **Destructive actions are visually separated** (`margin-inline-start: auto`
   on `.is-danger` / `.danger`), use the danger variant, and are **never the
   default focus**. A destructive dialog starts focus on Cancel (or the dialog
   itself when no safe control exists).
4. Disabled controls are disabled in DOM (`disabled`), not merely dimmed, so
   keyboard and mouse activation both fail.
5. While an action is in flight: the trigger control gets `aria-busy="true"`,
   every dialog control is disabled, the label width does not change, and the
   action cannot be submitted twice.

## 6. Content design

- **Titles** are short and specific: "Delete this model route?", "Remove
  scheduled task", "Allow scheduled ChatGPT plan use?". Sentence case, no
  punctuation in headings except a question mark when the dialog asks one.
- **Descriptions** explain the consequence in one sentence: what changes, what
  remains, whether it can be undone. They are wired with `aria-describedby`.
- **Action labels are verbs** naming the object: "Delete assistant", "Remove
  task", "Revoke permission". "Cancel" is always "Cancel"; "Done" is only for
  read-only review.
- **Error copy states what failed and what to do next**: "Could not save the
  section: <reason>. Try again." inside the dialog, in a `role="alert"` region,
  with the dialog kept open and its content intact.
- **Success** closes the dialog and produces a visible confirmation through the
  existing toast/announcer; silent closes are a defect.
- Icon-only controls carry an accessible name; tooltips describe, they never
  carry the only copy of information.

## 7. Theme behaviour

- Dark is the shipped default. The optional light scope is
  `[data-hutch-theme="light"]`; no attribute means no change.
- Scrim: ink in both themes, opacity 0.72 dark / 0.52 light.
- Surface/label/line/radius/space all resolve through `--hutch-*` aliases; the
  light scope redefines the alias tier, not the overlay rules.
- Elevation: dark uses black ambient shadows plus a white top hairline; light
  swaps both for ink alphas so depth reads as shadow, not glow.
- Focus ring: `--hutch-focus-ring` resolves to the azure interaction anchor in
  dark and its darker step in light; every overlay control uses the same ring.
- Forced colors: every overlay keeps a CanvasText border, drops shadows, uses
  Canvas/CanvasText, and uses the Highlight system colour for focus.
- No hard-coded colours in overlay rules; the only literals live in the
  documented token mirror at the top of `hutch-overlays.css`.

## 8. Category contract (what each primitive guarantees)

### Modal (`HutchOverlay.modal` / `HutchOverlay.enhance` / macros/modal.html)

- native `<dialog>` + `showModal()`: top layer, focus containment, Escape to the
  topmost dialog only, inert background;
- `role="dialog"`, `aria-modal="true"`, `aria-labelledby`; `aria-describedby`
  when a description exists;
- initial focus: explicit selector -> `[data-hutch-autofocus]` -> first form
  control -> safe control for non-dismissible; close button never first;
- focus return to the exact trigger, with a caller fallback if the trigger was
  replaced by a live refresh;
- backpack policy: dismissible dialogs close on backdrop press and Escape;
  `dismissible:false` (destructive) closes only via an explicit action;
- scroll lock with scrollbar-gutter compensation (no layout shift);
- busy/error slot; success closes.

### Popover (`HutchOverlay.popover` / macros/popover.html)

- portal-equivalent top layer when available; body portal only in the
  no-Popover-API fallback (and never from inside an open modal);
- flip to the opposite side when the preferred side lacks room, then shift
  inside the visual viewport with an 8px inset; re-anchor on scroll, resize and
  visual viewport changes;
- dismiss on outside pointerdown / focus loss / Escape (topmost only);
  menu panels also close on Tab and restore focus to the trigger;
- menu: `role="menu"`/`role="menuitem"`, roving tabindex, Arrow/Home/End,
  disabled items skipped, trigger ArrowDown/ArrowUp opens;
- rich dialog-kind popover: `role="dialog"` (not modal), normal Tab order,
  sticky header with a labelled close control;
- dropdown menus use the lighter elevation and the dropdown z rung; rich
  popovers the popover rung; both share the same surface tokens.

### Tooltip (`HutchOverlay.tooltip` + native title enhancement)

- `role="tooltip"`, `aria-describedby` while shown, pointer-events none,
  hover after 420ms / focus immediately, Escape dismisses and consumes the key;
- native `title` stays the fallback and is restored when JS is off; the
  attribute is temporarily removed while the themed bubble is up so the browser
  tooltip never double-renders.

## 9. Intentional divergences from the brief, preserved

1. **No body portal in the top-layer path.** `docs/design-system.md:74-80`
   records the approved dropdown direction: keep the panel in its owner DOM and
   let the native popover top layer escape clipping so a popover opened from a
   modal remains inside that modal's focus world. The brief's portal requirement
   is met by the **fallback** path, where no top layer exists and clipping is
   otherwise unavoidable.
2. **Needs-you stays a right-side sheet.** It is a modal by contract and a sheet
   by presentation; converting it to a centred card would lose the review flow
   the product tests pin.
3. **Navigation drawers stay inline landmarks.** They are modal in behaviour
   (block + trap + explicit close) but remain the page's `<nav>`/`<aside>`; the
   primitive supplies scroll lock, topmost Escape and focus ownership without
   moving them into `#modal-root`.
4. **Marketing navigation dialog stays outside the product overlay system**
   (separate surface, documented editorially-owned exception).
5. **Native `title` tooltips remain as the no-JS baseline** and are progressively
   enhanced rather than replaced.
6. **Rich phone panels become bottom sheets** (existing controls.js affordance),
   not tiny anchored menus.

## 10. Verification bar

An overlay is finished only when all of these are recorded as pass in
`docs/overlays/COMPLETION.md`: focus entry and return, trap/topmost Escape,
dismissal policy per category, outside-click policy, scroll lock, flip/shift at
all four edges, re-anchor, 320px and 200% zoom, short viewport, two overlays at
once, busy/double-submit guard, inline error announcement, success feedback,
accessible name/description, icon-only names, forced colors, reduced motion, and
token-only theming in both colour scopes.
