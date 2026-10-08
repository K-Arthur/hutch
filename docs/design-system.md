# hutch design system

The visual system for hutch's three surfaces: the server-rendered dashboard
(`src/hutch/server/static/hutch.css` + `templates/`), the legacy single-page
dashboard (`src/hutch/server/static/{style.css,app.js,index.html}`, served at
`/legacy`), and the marketing site (`website/`). All three consume the same
token **values**; names differ per surface and are mapped in each file's
`:root`.

Design goals, in priority order:

1. **Governance you can see.** hutch is a safety product: approvals, spend,
   and run state are the loudest things on every screen. Status is always
   glyph + word, never color alone.
2. **Quiet chrome, dense evidence.** Obsidian surfaces, one emerald accent,
   hairline borders. Decoration must communicate structure or state, or it is
   deleted.
3. **Tool output is compact by default.** Agent transcripts render as
   expandable one-line tool entries (Codex/Grok pattern), never as stacks of
   cards — see the complaint traceability table below.
4. **WCAG AA everywhere.** Every text token is verified >= 4.5:1 against every
   surface it appears on (ratios below are computed, not eyeballed).

## Color tokens

| Role | Value | Contrast vs darkest surface it appears on |
|---|---|---|
| bg (app) | `#05070a` | — |
| surface 1 (panels) | `#0a0e15` | text 18.3:1 |
| surface 2 (cards, inputs) | `#10161f` | text 16.4:1 |
| surface 3 (hover/raised) | `#171f2b` | text 15.0:1 |
| sunken (output wells) | `#070a10` | — |
| overlay (modal, toast) | `#0d1219` | — |
| text | `#f0f4f9` | 15.0:1 min |
| text-dim (secondary) | `#9daebf` | 7.3:1 min |
| text-faint (metadata, hints) | `#7d8ea4` | 4.9:1 min |
| border-subtle | `rgba(255,255,255,.06)` | decorative |
| border | `rgba(255,255,255,.10)` / `#1a2330` solid | — |
| border-strong | `rgba(255,255,255,.18)` / `#283649` solid | — |
| accent (emerald) | `#34d399` | 10.5:1 |
| accent-ink (text on accent fills) | `#052e21` | 7.7:1 |
| info (blue) | `#60a5fa` | running only |
| warning (amber) | `#fbbf24` | approval, stale, budget >= 70% |
| danger (red) | `#f87171` | failure, deny, destructive |

There is **no violet**: the `meta` hue was retired in Oct 2026 (non-semantic tags use the dim
greys). The old `-bg` tint tokens were retired too — a colour is a **dot, a 2px rail, or a thin
underline**, never a large fill (see *Status is not a fill*).

Semantic colors are for **state only** — never decoration. If a red or green
mark doesn't tell the user something happened, it doesn't ship.

**Status is not a fill.** A status colour appears as at most three small things: a 6px dot inside a
neutral pill, a 2px left rail on a card, or a thin underline — never a tinted card, banner, or
button background. Shape and wording carry the state; hue only reinforces it (WCAG 2.1 SC 1.4.1,
and the colour-only status-dot complaint in
[research/complaints.md](research/complaints.md)). This is the Oct 2026 *monochrome-first*
correction: the dashboard had read as too colourful and playful.

Verified with the luminance formula (WCAG 2.1 rel. 1.4.3). The audit lives in
git history; re-verify after changing any value in this table.

## Scales

- **Radius:** one coherent rounded scale, one rect radius per role — 4 (micro
  affordances: chip delete, toast close) / 8 (buttons, inputs, selects, nav,
  tool lines) / 12 (cards, panels, table wrappers) / 16 (composer, modals,
  sheets) / 9999 (pill chips, status, meters). Circular geometry (avatars,
  icon-only buttons, dots, spinners) is `50%`. **Sharp (0px) corners are
  reserved for dense data cells inside a rounded wrapper** — never for buttons.
  The earlier square-button pass was corrected after review (see below): the mix
  of 0px buttons beside 50% circles, 5px inputs and 8px panels is what read as
  inconsistent, not the roundness itself.
- **Type:** 11, 12, 13, 14 (body), 16, 18. System sans for all UI; a system
  serif for the page `<h1>` only (the one editorial signature); `ui-monospace`
  for tool names, IDs, cron, timestamps, and code.
- **Spacing:** 4 / 8 / 12 / 16 / 20 / 24.
- **Motion:** 120–180ms ease-out; transform/opacity only; every animation
  respects `prefers-reduced-motion`.
- **Layers:** sticky 40, nav 50, modal 100, toast 110. Never increase an
  arbitrary z-index to fix stacking.
- **Focus:** one treatment everywhere — `:focus-visible { outline: 2px solid
  var(--accent); outline-offset: 2px }`. Never remove or dim it (the single
  most common failure in component libraries this was benchmarked against).

## Core components

### Tool line (run transcripts)

One row per tool step, ~28px closed: verdict glyph (spinner while running,
check/x when done) + tool name (mono, full text colour) + truncated argument summary +
timestamp. Expanding (click or keyboard, `aria-expanded` on a real button)
reveals full input and output; long output clips behind "Show more".
Call/result pairs merge into one line; 4+ consecutive steps collapse under a
"N/M tool steps" group row. Expansion state persists per run (localStorage in
the SPA; `<details>` in the server-rendered transcript).

### Approval gate

The loudest surface — but loud through structure, not colour: a neutral card
with a 2px amber rail (red when the risk is high or the action is outward), the
action in bold, a live fail-closed TTL countdown that flips to "expired —
denied" in red at zero, the parsed segments, and the rule that fired. Actions:
Allow once (emerald fill) / Always / For this plan / Deny (red outline). Same
anatomy in the studio feed, the approvals queue, and the server-rendered cards.

**Review before deciding.** The action summary is plain language; the technical
detail sits behind a native `<details>` "Review details" disclosure (tool, why you
are asked, reversibility, parsed segments, raw request). An always-allow grant shows
its exact scope (`files:write` for this bot) and where to revoke it; outward actions
never offer it.

**Server-authoritative resolution.** The client never marks a request complete from
its own click. If a decision loses a cross-device race (409), it reconciles against
`GET /api/approvals/{id}` and renders the real state: "Approved by phone · just now",
"Denied", or "Expired — denied by timeout". A card that expires mid-view flips to the
resolved state rather than leaving dead buttons. The queue and a "Recently decided"
list (`?status=resolved`) refresh every 5 s.

**Attention.** The Approvals nav item carries the pending count and a pulsing dot
anywhere in the app; a newly-arrived approval is announced once through the bounded
live region. It is the same 6px dot + word pattern as every other status — never
colour alone — and its pulse is disabled under `prefers-reduced-motion`.

### Status chip

A neutral pill (surface + hairline border + dim text) with a 6px dot in the
state colour: succeeded (emerald), failed (red), running (blue),
waiting_approval (amber), paused/pending (dim). The word comes from the API
status vocabulary verbatim; the dot only reinforces it. No tinted chip fills.

### Budget meter

Track + fill with numeric readout (`1.8k / 200k tokens (9%)`). Amber at
>= 70%, red at >= 100%. Spend must never be a surprise (see traceability).

### Empty states

Every list has three distinct states: never-used (icon + one-line explanation
+ single CTA), no-matches (offer "Clear filters"), and all-clear (approvals).
No dead-end "Nothing here."

### Dialogs

`role="dialog"` + `aria-modal` + labelled title, focus trapped, initial focus
on the first field, Escape and backdrop close, focus restored on close.
Destructive confirms use the danger variant via a promise-based dialog —
never `window.confirm`.

### Toasts

Transient notices auto-dismiss after ~4s; **errors persist until dismissed**;
every toast has a visible dismiss button; the container is `aria-live="polite"`.

## Iconography

Inline SVG only — 24×24 viewBox, `stroke="currentColor"`, 1.7 stroke width,
round caps. The dashboard set lives in `app.js` (`ICON_PATHS`) and
`templates/_icons.html`; the website uses data-URI CSS masks for repeated
glyphs. **Pictographic emoji and icon-like text characters (arrows, dingbats,
geometric shapes) are banned**, and enforced: `python scripts/audit_emoji.py`
(also wired into `pytest` via `tests/test_emoji_audit.py`). Waive a deliberate
case with a `hutch-emoji-allow` comment on the line.

The auditor is an improved Python port of varve's `scripts/audit-emoji.mjs`:
two passes (pictographic emoji everywhere; icon-like characters in UI
surfaces only), plus HTML-entity, escape-sequence, and UTF-16 surrogate-pair
detection, greppable waivers instead of hardcoded skips, and pytest
integration so the default test run is the gate.

## Accessibility rules

- Real `<button>`/`<a>` for anything clickable; keyboard handlers on the
  few non-native interactive rows (`role`, `tabindex`, Enter/Space).
- `aria-expanded` on every collapsible; `aria-current` on active nav;
  `aria-pressed` on filter toggles; labelled form fields (visible or
  `.visually-hidden`).
- Skip link on every surface; `<main>` landmark present.
- Live regions: polite for feed/toast updates; the approval TTL is
  deliberately **not** announced every second.
- `prefers-reduced-motion` disables animation everywhere.

## Benchmark gaps we deliberately resolved

| Source gap | hutch answer |
|---|---|
| shadcn: weak default focus rings | 2px emerald ring token, never overridden |
| shadcn: no empty states shipped | three named empty-state patterns with CTAs |
| shadcn: data-table wiring is DIY (filters shipped dead here once) | filters/search/pagination are wired + hash-shareable |
| shadcn/Primer: toasts lose errors | errors persist, all toasts dismissible |
| ChatGPT: tool cards flood transcripts | merged compact tool lines + groups (pattern above) |
| Codex: expansion state resets | per-run localStorage / native `<details>` |
| Claude.ai: no timestamps | every event carries a timestamp |
| GitHub Actions: logs crash / invisible mid-run | capped output wells + SSE/live polling |
| Cursor: surprise spend | budget meters + run spend meters |
| Color-only status | glyph + word chips everywhere |
| Claude Code: saturated blue on pure black ("harsh", eye strain) | monochrome-first; one softened emerald accent for the primary action only |
| ChatGPT: accent churn with no opt-out | one documented token set; no runtime accent surprises |
| Codex: user/assistant turns indistinguishable | non-colour role cues (raised vs flat surface, role label, timestamp) |
| Claude Code: colour-only status dots (WCAG 1.4.1) | glyph + word + dot/rail on every status |
| Claude Code: "needs action" buried in output | approvals/failures carry a bold label + glyph + 2px rail; count on the nav |

The incident-level product requirements (the $447 bill, silent cron failures,
allowlist bypasses, …) and their traceability live in
[docs/research/complaints.md](docs/research/complaints.md); this file covers
the UI layer only.

## Surfaces covered by the Oct 2026 monochrome-first pass

All three surfaces now share the retired-violet / neutral-tint rule:

- **Server-rendered dashboard** (`src/hutch/server/static/hutch.css` + `templates/`): full pass —
  neutral chips/tags/banners, dot/rail status, 12px panels, restrained serif title, asymmetric
  triage, role-labelled transcript turns.
- **Legacy SPA studio** (`src/hutch/server/static/{style.css,app.js}`, served at `/legacy`): the
  `-bg` tint tokens are neutral, violet is retired (tool names, memory keys, the third bot-avatar
  hue), the dot-grid background is gone, panels are 12px. Structure unchanged.
- **Marketing site** (`website/`): keeps its loud personality (display type, motion, glow) but drops
  the `--violet` token and its last uses; labels moved to sentence case.

Remaining website follow-up (optional, not blocking): re-verify every text token against the site's
surfaces with the luminance formula, and confirm no comparison/incident section carries a second hue
beyond emerald.

## Current tokens (Oct 2026 — brutalist-modern)

The palette was re-based from emerald to a blue/green system with neutral cards.

| Role | Value | Notes |
|---|---|---|
| bg | `#050505` | page |
| surface / card | `#0a0a0a` | every card, with a 1px glass ring (`inset 0 0 0 1px rgba(255,255,255,.08)`) |
| surface raised | `#151515` | hover / raised |
| text / dim / faint | `#f0f4f9` / `#9daebf` / `#7d8ea4` | unchanged (AA) |
| accent (active) | `#52a8ff` | active nav, primary buttons, running state, focus |
| accent ink | `#04121f` | text on the blue fill |
| success | `#62c073` | succeeded, allowed, positive indicators |
| warning | `#fbbf24` | approvals, stale, budget |
| danger | `#f87171` | failure, deny, destructive |

- **Shape:** one rounded radius scale (buttons/inputs 8, panels/cards 12, composer
  and modals 16, pill chips full). The earlier 0px-button brutalist pass was
  corrected after review: square primary buttons beside circular icon buttons,
  pill chips and rounded panels read as inconsistent, and the shape literature
  (Material 3 shape scale, Atlassian radius tokens) plus the perceptual research
  on corner shape favour a small, consistent rounded scale for interactive and
  containment surfaces. Dense table cells stay square inside a rounded wrapper.
- **Atmosphere:** a single faint, centred top wash on a solid surface — no corner
  gradients, no full-screen animation, no universal blur. Panels are solid with a
  1px ring. The background never changes hue between views.
- **Data:** every data row is monospace (table `th`/`td`); mono for tool names, ids, cron, timestamps, code.
- **Navigation:** the header nav collapses to a full-screen mobile menu (hamburger, Escape, `aria-expanded`) on the app and the server dashboard; the marketing drawer is full-screen too.
- **Marketing only:** dot-grid background, scroll-reveal animations, floating parallax cards, stacked text echo, asymmetrical grids.

These values supersede the emerald-era rows above wherever they conflict.

### Layout patterns (Oct 2026)

- **Bento grids** carry the Overview triage (Needs you is the wide feature tile, Running/Stale
  smaller) and the Bots page (the first bot is a two-column feature tile). Every tile is a card:
  `#0a0a0a`, 1px ring, 8px radius.
- **Timeline tables** — the Runs table has a Timeline column: a per-run duration bar (blue
  succeeded, amber waiting, red failed) with a monospace duration label beside it. Rows stay mono.
- **The chat SPA is the whole app**: Studio (chat), Overview (triage), Bots, Runs, Approvals are all
  SPA views on shared tokens; `GET /api/overview` feeds the triage from the same `views.home_state`
  the server page uses, so there is one source of truth and no second chrome.

### Single UI (Oct 2026)

The **studio SPA is the whole app**. The server-rendered `/overview`, `/bots`, `/bots/new`,
`/bots/{name}`, `/runs`, `/runs/{id}` and `/approvals` now **302-redirect into it** (`/#/...`), so
there is exactly one chrome and one look. The server keeps its fragments (`/_home`, `/_approvals`,
`/runs/{id}/events|meters|wait`), the JSON API, and the pages the SPA does not yet cover
(`/connections`, `/models`, `/login`).

Run detail carries Steps / Elapsed / Recorded cost / Reported tokens and a **Recorded step timing**
stacked bar — model (emerald), tools (azure), Hutch (amber), and inference queue (neutral metadata)
— with a per-step strip. Recorded admission waits include startup and completed queue admissions;
the elapsed clock also includes time outside recorded steps. Resource waits show their reason in
chat, with no typing or working-avatar animation.

### Truthful shell state (Oct 2026)

Two honesty rules for the studio shell, both regression-tested:

- **Live regions are bounded.** The whole `<main>` used to be `aria-live="polite"`, so every poll
  re-announced the entire page. Announcements now go through a single visually-hidden `#live-status`
  region that speaks only on deliberate transitions (run started/waiting/finished, approval required,
  connection lost) and is cleared before each message so repeats are not swallowed. The streamed
  transcript is never announced token by token.
- **Health is established, not asserted.** The daemon badge no longer ships `live` in static markup.
  `pollHealth()` reads `/api/health` and shows the real version/schema; on failure it degrades to
  `reconnecting` (recent) then `offline`, and the composer's working indicator only appears while a run
  is `running`. Queued, loading, resource and human waits use their authoritative labels;
  waiting does not animate as computation.

Composer options share one bounded, nonmodal dialog beside the model selector. It contains
suggestions, rehearsal and Enter behavior; Escape returns focus to its trigger, and leaving
the dialog closes it. Rehearsal explicitly simulates writes/commands while model calls and
reads still happen. The submitted request determines the confirmation text. Phone Send,
options and Stop controls have 44px targets. Stop remains in the conversation header and
individual attempt; a third duplicate composer control is unnecessary. Cancellation notices
use the server label and neutral text; uncertain outcomes remain warnings.

The working indicator is the shared **3-dot bounce** (5px dots, 1.3s loop, 0.15s stagger), `aria-hidden`
because the status chip carries the state for assistive tech. Its label is "Working…", not the bot's
name — the reference product dropped the name from its working status (v0.67.0) and the chat header
already identifies the bot. See [research/reference-map.md](research/reference-map.md).

### Marketing site signature system (Oct 2026)

The site keeps the dashboard's token values and squared-off shape language (buttons 0, panels 8px,
chips pill) while carrying its own louder personality:

- **Intro stage** — a fixed panel with one lowercase line, fading/lifting out; deleted entirely under
  `prefers-reduced-motion` and skipped on repeat visits in a session.
- **Type/subject occlusion weave** — a poster wordmark ("hutch.") rendered as two exactly-registered
  absolutely-positioned layers (back z1 / front z3) with the aurora character at z2. Each layer holds
  every letter with the unowned ones `visibility:hidden`, so the flex metrics match; exactly one letter
  sits in front of the character. This is the only way to get the effect without transforms trapping
  each letter's stacking context.
- **Character** — a diffused aurora sphere (brand blue→green) with a geometric line face (high curved
  eyebrows, dot eyes, L-shaped nose), built from CSS gradients + one inline SVG.
- **Motion** — neural connection lines (pulsing + dashed flow), a scroll-linked receding hero heading,
  spotlight cursor tracking (`--mouse-x/y`), morphing card glows, and hover-revealed card actions.
  Every effect is disabled under `prefers-reduced-motion`.
- **Deliberate deviations from the brief**: the nav is a translucent blurred bar, *not*
  `mix-blend-difference` — inverting against the brand's accent panels hurt legibility, and the site is
  single-theme. Corner radii stay 8px rather than 24–48px so the site and the app share one shape
  language. The scripted hero pill says "DEMO supervised run" and its accessible name
  identifies a preview. Application health is shown only by the application.

The hero gradient heading uses a solid accent fallback and applies `background-clip:text` only inside
`@supports`: a `filter` on the same element made Chromium paint the whole text box as a solid block
(caught in the pre-change baseline).
