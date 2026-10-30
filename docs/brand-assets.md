# Brand artwork used for service identification

Hutch uses a provider mark only when the UI connects to or manages that named
service. The complete service name and connection state remain visible. Artwork
is bundled locally, unchanged, and is never presented as a Hutch endorsement,
partnership, or product logo. Generic categories continue to use Hutch's local
outline icon family. These notes record source and presentation boundaries; they
are not a legal opinion or a grant of trademark rights.

| Service | Local asset | Source and use |
|---|---|---|
| OpenAI / ChatGPT | `openai-white-monoblossom.svg` | OpenAI's published brand resources. Preserve the white mark; label the service as either **OpenAI API** or **ChatGPT** so API billing is not confused with a ChatGPT plan. |
| Anthropic API | `anthropic-symbol-ivory.svg` | Anthropic's official [press kit](https://www.anthropic.com/press-kit), Anthropic symbol in Ivory. Use on Hutch's dark surface beside **Anthropic API**. |
| OpenRouter | `openrouter-glyph-volt.svg` | OpenRouter's [official brand assets](https://openrouter.ai/brand), Volt glyph for dark backgrounds. Do not stretch, recolor, or remix. |
| Gmail | `google-gmail-2026q2.png` | Google Workspace [branding kit](https://knowledge.workspace.google.com/admin/getting-started/brand-your-internal-communications-with-google-workspace), 2026 Q2 color icon at 2× web resolution. Use the approved artwork unchanged beside **Gmail**. |
| Google Calendar | `google-calendar-2026q2.png` | The same Google Workspace branding kit, 2026 Q2 color icon at 2× web resolution. Use unchanged beside **Google Calendar**. |
| Google Drive | `google-drive.svg` | Unchanged [official Workspace product artwork](https://knowledge.workspace.google.com/static/images/icons/product/drive.svg), linked from the branding kit, retrieved 2026-10-26. Functional connector identification only. SHA-256: `60a6496d705d8bf010ce126469be89889db331622b14d8ae1645a38c2aaa23f5`. |
| Google Docs | `google-docs.svg` | Unchanged [official Workspace product artwork](https://knowledge.workspace.google.com/static/images/icons/product/docs.svg), linked from the branding kit, retrieved 2026-10-26. Functional connector identification only. SHA-256: `5e9bbbba853ebe62ddce006e41465f9d44e7a6a7cb083a770d1667bdd6e87140`. |
| Google Sheets | `google-sheets.svg` | Unchanged [official Workspace product artwork](https://knowledge.workspace.google.com/static/images/icons/product/sheets.svg), linked from the branding kit, retrieved 2026-10-26. Functional connector identification only. SHA-256: `3538632f4b58f1b5f5bd9490b69f6eda036d8a4c544b1b336121c07fd6d040cf`. |
| Microsoft Outlook | `microsoft-outlook.svg` | Microsoft's [Fluent product icon asset](https://static2.sharepointonline.com/files/fabric/assets/brand-icons/product-fluent/svg/outlook_48x1.svg). Use only as a functional account-access cue, on a neutral background, with the full name **Microsoft Outlook** nearby. |
| Notion | `notion.ico` | Unmodified icon published at [Notion's own site](https://www.notion.com/front-static/favicon.ico), retrieved 2026-10-26. Use only beside **Notion** to identify the account connector, without endorsement claims. SHA-256: `541fc85f92e348bcf46f70944b95fd558d16adbc5a0698eaa1239dccd8c9e455`. |

**Model picker.** The OpenAI and Anthropic marks also appear on model rows and the composer's model pill, where they identify the model's maker beside its name and where it runs (the connection or group name stays visible, so an API route and a ChatGPT plan are still told apart). They are decorative (`aria-hidden`), fetched from the same bundled files, and never imply endorsement. Models from makers without bundled artwork show a letter tile for their model family; no remote icon is ever requested.

Google's published guidance permits Google icons and logos in materials made
for an organization in conjunction with its deployment, requires approved
artwork without alteration, and prohibits implying affiliation or endorsement.
Hutch uses the icons to identify the actual Google connection being set up;
they are not used in marketing artwork. Microsoft's icon guidance limits app
marks to functional use and asks for the full product name nearby. OpenRouter
specifies background-specific variants and prohibits altering its marks. Recheck
the linked vendor guidance before changing or adding an asset. No remote image
requests are made at runtime.

## Typefaces

| Font | Local asset | Source and licence |
|---|---|---|
| Geist, Geist Mono | `src/hutch/server/static/fonts/geist-latin-var.woff2`, `geist-mono-latin-var.woff2` and the same pair under `website/assets/fonts/` | Vercel's Geist family (npm package `geist` 1.8.2), SIL Open Font License 1.1, copyright © 2023 Vercel in collaboration with basement.studio. Latin, Latin-1, Latin Extended-A, punctuation, arrows and a few symbols were subset with fontTools `pyftsubset` (variable weight axis and OpenType features kept). The licence text is `OFL-geist.txt` beside each pair. Replaces the earlier Archivo files; no remote font request is made. |
| Bricolage Grotesque | `src/hutch/server/static/fonts/bricolage-grotesque-latin-800.woff2` and `website/assets/fonts/bricolage-grotesque-latin-800.woff2` | The Bricolage Grotesque Project (`https://github.com/ateliertriay/bricolage`), SIL Open Font License 1.1, Copyright 2022 The Bricolage Grotesque Project Authors. Latin subset pinned at weight `800` (`wdth: 100`, `opsz: 48`), subset with fontTools `pyftsubset` for the Hutch wordmark (`hutch.` / `hutch`). The licence text is `OFL-bricolage-grotesque.txt` beside each file; no remote font request is made. |

## Hutch identity assets

These are Hutch's own marks, separate from the third-party service artwork above. The notes
below record their form, colors and usage boundaries; they are not a legal opinion. Complete
geometric specifications, size-tier coordinates, and validation matrices are recorded in
[`.pipeline/brand/2026-10/BRAND-GUIDELINES.md`](../.pipeline/brand/2026-10/BRAND-GUIDELINES.md).

| Asset | Form and location |
|---|---|
| Logomark ("Visor Hutch") | Single `fill-rule="evenodd"` compound vector path on a `32x32` grid combining a hooded shelter dome, three grounded timber posts (`4.40u` wide) flanking two concave semicircular burrow arches (`5.40u` wide), and a recessed upper loft visor containing two inward-tilted (`-8 deg` left, `+8 deg` right) positive-space oval bot eyes. Built in two redrawn size tiers so counterforms survive small rasterisation: **Master tier** (`>= 25px`, `hutch-mark-master.svg`) and **Small tier** (`16px-24px`, `hutch-mark-small.svg`), staged in `.pipeline/brand/2026-10/assets/production/svg/`. |
| Wordmark | Lowercase `hutch` set in **Bricolage Grotesque** (weight `800`, `-0.03em` tracking). Marketing, social cards, press kit and standalone brand lockups include an emerald period (`hutch.`); the operator dashboard (`src/hutch/server/static/index.html`) and server-rendered headers (`src/hutch/server/templates/base.html`) use the compact period-less variant (`hutch`). The wordmark is a logo form only; in public prose, page `<title>` tags, JSON-LD and Open Graph metadata, write "Hutch". Outlined `<path>` SVGs (zero `<text>` dependency) live in `.pipeline/brand/2026-10/assets/production/lockups/`. |
| Standard lockups | Marketing header: `26px` Master mark + `9px` gap + `20px` wordmark (`hutch.`). Mobile drawer, site footer, Studio sidebar and server header: `22px` Small mark + `8px` gap + `18px` wordmark. |
| Operator bot avatars ("The Hutch Colony") | Eight 2D architectural-creature resident silhouettes on a `64x64` grid (`orb` Ghost Bell, `capsule` Gable Hutch, `bean` Hopper Hare, `drop` Lantern Cowl, `pebble` Transceiver Pod, `shield` Bastion Keep, `triangle` Beacon Spire, `hex` Mecha Chassis) paired with shape-fitted `#0b1511` contrast-ink oval eyes across 8 distinct vertical face rows (`cy = 25.6..39.8`) and 8 decorative identity colours (`ID_COLORS`). Specified with `Path2D` verification in [`.pipeline/brand/2026-10/AVATAR-SYSTEM.md`](../.pipeline/brand/2026-10/AVATAR-SYSTEM.md). |
| Platform icons & manifest | Production package in `.pipeline/brand/2026-10/assets/production/icons/` (`favicon.svg`, `favicon.ico` `16/32/48`, `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`, `apple-touch-icon.png` `180x180` opaque `#09090b`, PWA `icon-192.png`/`icon-512.png` in `any`, `maskable` within the W3C `40%`-radius safe circle, and `monochrome`, plus `site.webmanifest`). |
| Social card | `website/assets/og-card-1200x630.png` (and `.pipeline/brand/2026-10/assets/production/social/og-card-1200x630.png`), 1200 by 630 pixels, referenced as `og:image` and `twitter:image` from `website/index.html`. |
| GitHub social preview | `website/assets/github-social-preview-1280x640.png` (and `.pipeline/brand/2026-10/assets/production/social/github-social-preview-1280x640.png`), 1280 by 640 pixels. Upload it manually in the repository's **Settings > General > Social preview**; GitHub does not read the file from the repository automatically. |

### Identity colors

| Token (`website/tokens.json`) | Value | Role and measured WCAG 2.x contrast |
|---|---|---|
| `color.primitive.ink.950` (`--bg`) | `#09090b` | Page background, icon tile background and primary dark surface |
| `color.primitive.paper` (`--text`) | `#ededf0` | Primary text and reversed monochrome mark on dark surfaces (`17.03:1` on `ink-950`, AAA) |
| `color.primitive.emerald.400` (`--brand`) | `#34d399` | Brand accent for the logomark, wordmark period, links and primary actions on dark surfaces (`10.35:1` on `ink-950`, AAA) |
| `color.primitive.emerald.ink` (`--on-brand`) | `#052e21` | Ink text and icons placed directly on `#34d399` fills (`7.70:1`, AAA; never use white on `#34d399`) |
| `color.primitive.mist` (`--text-2`) | `#a3a3ae` | Secondary body copy on dark surfaces (`7.97:1` on `ink-950`, AAA) |
| `color.primitive.faint` (`--text-3`) | `#8e8e99` | Tertiary and muted metadata text on dark surfaces (`6.14:1` on `ink-950`, AA) |
| Light-surface brand (`emerald-700`) | `#047857` | Brand mark, wordmark period and links on `paper` (`#ededf0`) or white light surfaces (`4.69:1` on `paper`, `5.48:1` on `#ffffff`, AA; never use `#34d399` on light surfaces where it measures `1.65:1`) |

The governing token source is `website/tokens.json`; [design-system.md](design-system.md) documents the
shared UI tokens, contrast pairs and component geometry.

### Usage rules

- Use the marks to identify Hutch. Do not imply that Hutch endorses, sponsors or is affiliated
  with another product, project or person.
- Switch between the redrawn **Master tier** (`>= 25px`) and **Small tier** (`16px-24px`) at the
  `24px` boundary; do not scale the Master SVG down to `16px` or `22px`, and do not recolour the
  positive eyes separately from the outer shell.
- Do not recolour, stretch, crop or remix third-party service marks. Follow each vendor's
  guidance linked above, and keep the service name visible beside its mark.
- Do not present the Hutch logomark or wordmark as a registered trademark. This page is not a
  legal opinion and grants no trademark rights.
- The mascot artwork (`website/assets/hutch-agent.webp` and the frame grid under
  `website/assets/agent/`) is decorative product art, not a logo or application screenshot; see
  the provenance rules in [marketing-site.md](marketing-site.md).
