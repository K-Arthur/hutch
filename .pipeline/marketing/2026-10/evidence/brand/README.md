# Evidence: GitHub social preview card (1280x640)

Date: 2026-10-28. Task: task-3, brand asset for the public repository
github.com/K-Arthur/hutch (campaign folder .pipeline/marketing/2026-10/).
Status: rendered and visually verified; not committed by this task (Lead commits).

## Deliverables

| Path | What | Dimensions | Bytes | SHA-256 |
|---|---|---|---|---|
| website/assets/github-social-preview-1280x640.png | GitHub repository social preview asset | 1280x640 | 133259 | cc1a0b08fdacd14ea2680386313f087b17a0ee19cae4a2f1948675c2ae6fed7c |
| .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py | Reproducible renderer (adapted from the S-c og-card renderer) | - | 11426 | - |
| .pipeline/marketing/2026-10/evidence/brand/github-social-preview-1280x640-thumb-320w.png | 320 px wide legibility thumbnail (render with --thumbnail) | 320x160 | 14794 | b2329acc9c6055daf5712d4c960fe5677ccb40873bb86587f77872ef9a8f747d |

Format: PNG, 8-bit/color RGB, non-interlaced (no alpha channel, matching the
committed og card). Under the 1 MB preferred size and far under the 5 MB
GitHub limit. The committed og card website/assets/og-card-1200x630.png was not
modified; this is a separate 2:1 asset for the GitHub surface.

## Render command

From the repository root, with the project environment already synced
(`uv sync --extra dev --extra browser`), the exact command is:

```bash
uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py --thumbnail
```

In this sandboxed session the default uv cache (~/.cache/uv) is read-only, so the
run used a temporary cache directory on top of the same frozen environment:

```bash
UV_CACHE_DIR=/tmp/uv-cache-brand uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/brand/render_github_social_preview.py --thumbnail
```

On a normal checkout the plain command above is sufficient; UV_CACHE_DIR changes
nothing about the rendered bytes. `--out PATH` writes the card elsewhere. The
script prints dimensions, bytes and SHA-256 for the file it wrote.

Renderer environment used for these hashes: Python 3.13.15, Playwright 1.63.0,
Chromium 153.0.8010.12, Linux x86_64. The same environment renders the same
bytes on rerun (re-rendered once, identical SHA-256). A different Chromium or
font stack can change the bytes while the layout stays the same, so treat the
hash as "as rendered here", not as a hardcoded invariant.

## Inputs and network isolation

- website/tokens.css is read at render time and inlined into the card document;
  the card references tokens through var(--color-semantic-*) and
  var(--font-display). Rendering fails loudly if a required token is missing
  from tokens.css, rather than silently rendering unstyled colors.
- website/assets/fonts/geist-latin-var.woff2 is the only font, loaded over
  file://. The script refuses to write a card unless the Geist font reports
  loaded (no fallback-font fallback).
- Zero network requests. The run logged exactly 2 page requests, both file://:
  the local scratch HTML document and the committed font. The script asserts
  that every request is file:// and exits non-zero otherwise.
- No external URL strings in the script (a scheme scan returns 0 hits).

## Approved strings only

The card uses exactly the strings already approved for the S-c og card; no new
copy was written.

- "Hutch"
- "Local-first AI assistants"
- "that run on your machine."
- "MIT-licensed · open source · Linux · Development preview"

"Local-first" is capitalized only because it starts a line, the same orthographic
point recorded in the CLAIM-REGISTER review log for S-c. The card asserts nothing
from the CLAIM-REGISTER prohibited table: no superlatives, no comparative or
measured-performance claims, no social proof or maturity claims, no privacy
absolutes. The stage is stated only as "Development preview". No emoji, no em
dashes.

## Layout and edge safety

Canvas: 1280x640 (2:1, GitHub's documented social preview size). Content is kept
inside a 112 px inset on every side so the side crops used by link-card surfaces
cannot cut the mark, statement or footer.

Measured at render time (the script asserts these bounds before writing):

- mark row (hexagon plus "Hutch"): x 112.0 to 318.0, top 74, mark 56x56
- statement: x 112.0 to 1062.0, top 224, two lines at 80 px / 1.07
- footer: x 112.0 to 837.2, bottom edge at y 574.0

Crop arithmetic: a 1.91:1 center crop of this canvas trims 28.5 px per side; a
16:9 crop trims 71.1 px per side. Even at 16:9 the left content edge is still
40.9 px inside the cropped frame and the widest line ends 146.7 px before the
cropped right edge. The top and bottom margins are 74 px and 66 px.

The layout deliberately mirrors the human-approved og card (top-left hexagon and
wordmark, two-line statement, muted footer, one emerald radial glow top-right)
rather than inventing a second visual language.

## Visual verification

Both images were opened at full resolution with read_image.

Full-size card (1280x640): hexagon mark and wordmark are crisp against the
near-black background; the statement is high contrast with no clipping, wrap or
cut descenders; the muted footer is legible but clearly secondary; the top-right
glow is smooth with no visible banding at 1:1.

Thumbnail (320x160, the size a small link card can reach): the wordmark and both
statement lines stay legible, the footer remains readable, and nothing overlaps
or clips.

Measured WCAG contrast against the #09090b background: statement line 1
(#ededf0) 17.03:1, statement line 2 (#34d399) 10.35:1, footer (#8e8e99) 6.14:1.
All clear AA for normal text; line 1 and line 2 clear AAA.

## Scope and follow-ups

- This task writes only website/assets/ and this evidence directory. No changes
  were made to website/index.html, docs/, .github/, README or src/. No git
  stage/commit/push was run.
- Wiring the image into GitHub repository settings (social preview upload) or
  into the site's og:image tags is outside this task. The GitHub repo already
  uses the committed og card for site sharing; this asset is the 2:1 repository
  preview candidate.
- Reproduction note: the S-c renderer hardcodes the brand values in its CSS.
  This renderer adapts that structure but inlines website/tokens.css and uses
  the token variables, with a hard failure on any missing required token.
