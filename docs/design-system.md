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
| accent (emerald) | `#34d399` (+bg `.12` alpha, border `.38`) | 10.5:1 |
| accent-ink (text on accent fills) | `#052e21` | 7.7:1 |
| info (blue) | `#60a5fa` | running, tool calls |
| warning (amber) | `#fbbf24` | approvals, TTL, budget >= 70% |
| danger (red) | `#f87171` | failures, denials, destructive |
| meta (violet) | `#a78bfa` | model tags, tool names |

Semantic colors are for **state only** — never decoration. If a red or green
mark doesn't tell the user something happened, it doesn't ship.

Verified with the luminance formula (WCAG 2.1 rel. 1.4.3). The audit lives in
git history; re-verify after changing any value in this table.

## Scales

- **Radius:** 4 (chips, small buttons) / 8 (inputs, buttons, tool lines) /
  12 (cards, panels) / 16 (modals) / 9999 (pills). No other values.
- **Type:** 11, 12, 13, 14 (body), 16, 18. System sans; `ui-monospace` stack
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
check/x when done) + tool name (violet mono) + truncated argument summary +
timestamp. Expanding (click or keyboard, `aria-expanded` on a real button)
reveals full input and output; long output clips behind "Show more".
Call/result pairs merge into one line; 4+ consecutive steps collapse under a
"N/M tool steps" group row. Expansion state persists per run (localStorage in
the SPA; `<details>` in the server-rendered transcript).

### Approval gate

Amber card, the loudest surface in the product: "Approval required" tag, live
fail-closed TTL countdown (ticks every second, flips to "expired — denied" in
red at zero), the action in bold, detail JSON in a capped well, Approve (accent)
/ Deny (danger) / always-allow checkbox. Same anatomy in the studio feed, the
approvals queue, and the server-rendered approval cards.

### Status chip

Glyph (dot) + word, tinted bg: succeeded (green), failed (red), running
(blue, pulsing), waiting_approval (amber, pulsing), paused/pending (dim).
Words come from the API status vocabulary verbatim.

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

The incident-level product requirements (the $447 bill, silent cron failures,
allowlist bypasses, …) and their traceability live in
[docs/research/complaints.md](docs/research/complaints.md); this file covers
the UI layer only.
