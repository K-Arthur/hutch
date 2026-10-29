# ASSET-INVENTORY - Hutch visual assets, provenance and licence STATUS

Run 1 review/gap-fill artifact for the brand-identity pipeline (gap items C01, C19, C27, U07 of
Phase 0 plan `docs/brand/00-PLAN.md` as read from branch `brand/plan` via `git show`; that file
is not present on the checked-out `main` branch).

Scope: every visual asset the product ships (marketing site `website/`, dashboard
`src/hutch/server/static/`, Tauri host `desktop/icons/`). Method: local only - `ls`, `find`,
`sha256sum`, `file(1)`, plus small `python3` header parses for .ico/.icns. No web fetches were
made; vendor URLs below are quoted from tracked repo docs, not re-verified today. Inventory taken
2026-10-28 against `main` at commit `577e1154`. STATUS only: this file records what the tracked
docs say and what hashes/dimensions were measured; it makes no licence-compliance, clearance,
distinctiveness or non-infringement conclusions.

## Summary counts

| Location | Files | Total bytes | Note |
|---|---|---|---|
| `website/assets/` (top level) | 3 | 292,460 | social cards + mascot still |
| `website/assets/agent/` | 21 | 884,208 | 7 frames x 3 poses, 620x880 WebP |
| `website/assets/captures/` | 4 | 94,290 | app screenshot crops |
| `website/assets/fonts/` | 3 | 80,708 | 2 woff2 + OFL text |
| `src/hutch/server/static/agent/` | 21 | 884,208 | byte-identical duplicate of the website grid |
| `src/hutch/server/static/fonts/` | 3 | 80,708 | byte-identical duplicate of the website font set |
| `src/hutch/server/static/brands/` | 11 | 59,949 | third-party service marks |
| `desktop/icons/` | 4 | 135,126 | Tauri app icon family |
| Shipped total (visual assets on disk) | 70 | ~2,411,367 | excluding inline SVG and non-shipped images (below) |

Not "shipped" and therefore outside the inventory tables: screenshots under `.validation/**`,
`.pipeline/marketing/2026-10/evidence/**` and `reports/message-system/*.png` (audit/validation
evidence, not product surfaces); `docs/**` evidence artifacts (not read, per repo rules).

## 1. Identity marks

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| Logomark (inline favicon, data-URI SVG) | `website/index.html:24` | n/a (embedded; extracted data-URI string hashes to `78602c5cd50e323cce0b606eb29a80c386fa0002d00a395e8fe746d66a28c5da`) | viewBox 0 0 32 32 | n/a | Hutch-own | docs/brand-assets.md:48 ("Hexagon outline with a centre dot, drawn as an inline SVG data URI in the <head> of website/index.html") | No licence statement for the mark itself in tracked docs; brand-assets.md:57-60 records usage rules only | Identity-critical; no standalone file exists by design |
| Logomark (dashboard favicon, data-URI SVG) | `src/hutch/server/static/index.html:9` | n/a (embedded) | viewBox 0 0 32 32 | same data-URI string, byte-identical to website copy (sha256 `78602c5c...`) | Hutch-own | docs/brand-assets.md:48 (documented for the website head only) | as above | Identical to website copy |
| Logomark (server-rendered pages favicon, data-URI SVG) | `src/hutch/server/templates/base.html:9` | n/a (embedded) | viewBox 0 0 32 32 | same data-URI string, byte-identical to website copy (sha256 `78602c5c...`) | Hutch-own | as above | as above | Identical to website copy |
| Header logomark (website) | `website/index.html:263` | n/a (inline) | viewBox 0 0 32 32 | n/a | Hutch-own | docs/brand-assets.md:50 (standard lockup, 22px beside wordmark) | as above | Uses `var(--color-semantic-brand)`; favicon hard-codes `#34d399` |
| Header logomark (dashboard) | `src/hutch/server/static/index.html:46-49` | n/a (inline) | viewBox 0 0 32 32 | n/a | Hutch-own | brand-assets.md:48 applies by shape; dashboard use not separately documented | as above | - |
| Header logomark (server templates) | `src/hutch/server/templates/base.html:37` | n/a (inline) | viewBox 0 0 32 32 | n/a | Hutch-own | as above | as above | Uses `var(--accent)` |
| Wordmark ("hutch." lowercase, Geist extrabold + emerald period) | text, no file (site header/drawer/footer; `website/index.html` header area) | n/a | n/a | n/a | Hutch-own | docs/brand-assets.md:49; docs/marketing-site.md:26 | as above | Logo form only; no image file |

Favicon data-URI content (identical in all three HTML roots; URL-decoded):
`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><path d='M16 2 28 9v14L16 30 4 23V9z' fill='none' stroke='#34d399' stroke-width='2.5'/><circle cx='16' cy='16' r='4' fill='#34d399'/></svg>`
- Stroke/centre colour `#34d399` = documented `emerald` token (docs/brand-assets.md:54-57).
- The three copies do not differ; verified by hashing the extracted data-URI string from each root.

## 2. Social cards

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| Open Graph card | `website/assets/og-card-1200x630.png` | 118,901 | 1200x630 PNG RGB | `b905c4170ed568b474d90f0b1ef93f0efe15207c6155fbb702b7f46bb366c2a1` | Hutch-own | docs/brand-assets.md:51 (referenced as og:image/twitter:image from `website/index.html:16,23`) | No licence statement; treated as Hutch identity asset per brand-assets.md "Hutch identity assets" section | How the card was rendered is NOT recorded in tracked docs (no render script for it found under `scripts/`) |
| GitHub social preview | `website/assets/github-social-preview-1280x640.png` | 133,259 | 1280x640 PNG RGB | `cc1a0b08fdacd14ea2680386313f087b17a0ee19cae4a2f1948675c2ae6fed7c` | Hutch-own | docs/brand-assets.md:52 (manual upload to repo Settings > General > Social preview; GitHub does not read it from the repo) | as above | Prior evidence exists at `.pipeline/marketing/2026-10/evidence/brand/` (render script + 320w thumbnail + README); listed, not opened |

## 3. Mascot / character

Provenance as recorded in docs/marketing-site.md:207-209 and :239-240: "an original Blender render
(`scripts/render_hutch_agent.py`), shipped as `website/assets/hutch-agent.webp` plus a 7x3
look-at-cursor frame grid in `website/assets/agent/`; it is decorative product art, not an
application screenshot"; render details (bpy 5.0.1, Cycles CPU, 96 samples, denoise, transparent
film, blue palette, 620x880 canvas, webp q82). This is a provenance STATEMENT in a tracked doc;
no licence term, copyright line or usage rules for the artwork itself appear in tracked docs
(see Gaps, C27).

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| Mascot still (hero/CTA) | `website/assets/hutch-agent.webp` | 40,300 | 620x880 WebP, alpha | `da73ea5e42ebe5a0f9af5c2e9071467be90bbb34508ae1767321160b9dce34b7` | mascot | docs/marketing-site.md:240 ("Copy of the centre frame (f3-p1)") | UNKNOWN - no licence/usage terms stated in tracked docs | Byte-identical to `agent/f3-p1.webp` (separate inode, not a hardlink); confirms doc claim |
| Frame grid, 21 files (7 frames x 3 poses) | `website/assets/agent/f{0-6}-p{0-2}.webp` | 884,208 total | each 620x880 WebP, alpha | see per-frame table below | mascot | docs/marketing-site.md:239 (original Blender render, `scripts/render_hutch_agent.py`) | UNKNOWN - no licence/usage terms stated in tracked docs | Referenced by `website/site.js:104` (data-frames base `assets/agent/f`) |
| Frame grid duplicate (dashboard) | `src/hutch/server/static/agent/f{0-6}-p{0-2}.webp` | 884,208 total | each 620x880 | per-file hashes byte-identical to the website grid (`diff` of both sha256 lists empty) | mascot | same render pipeline by identity of bytes | UNKNOWN as above | No reference to `/static/agent/` found in `src/hutch/server` code or tests on `main` (usage UNVERIFIED; possibly legacy duplicate) - third duplicated asset family besides fonts and favicon |

Per-frame table (website copy; the `src/hutch/server/static/agent/` copies hash identically):

| Frame | Bytes | sha256 |
|---|---|---|
| f0-p0.webp | 43,240 | `63213e7b65a9711b1151a0fe8553f862138ee489bd01e5947a68ac408b82d577` |
| f0-p1.webp | 42,160 | `fa3ae62fee93297f250826d3aeaa2c8e3c997d4295fd1c454f93e745605d5bf0` |
| f0-p2.webp | 42,574 | `190ca0c6f9a40c0d74f8c98d547b65b09ee53d7b9beaede3f822494974dfbe2d` |
| f1-p0.webp | 41,578 | `7104039f73ef9a1fdbc92d130eb971a0322fad51cf7ee837f01d332958addaa6` |
| f1-p1.webp | 43,420 | `a93a4816aed3b60cd7d61d0f1f31a5fd50dd0d30b524349ecaa4d0be3477ffc4` |
| f1-p2.webp | 44,346 | `e4f78454987096d6cbbd064b9b7521338440b43c07fbf833badca7954e7fd4e3` |
| f2-p0.webp | 41,088 | `fecf561e1528e09169a32d942522d117d7653b9f78b5d00c7f9b3b0a95ddbbe8` |
| f2-p1.webp | 41,160 | `103e05c91d2cfbf5ce63c602770d2fb83d6881ba1805d16a7df569fedb3c0d27` |
| f2-p2.webp | 42,162 | `058089f4aa52efc850baa00a33bb47ce29a1a08c1ef3d10f4ecd8f714d02c0cf` |
| f3-p0.webp | 40,240 | `d677a7a556b1087b7bd0460227113313bb8a17a5eb22678a824d7a3cebc216e5` |
| f3-p1.webp | 40,300 | `da73ea5e42ebe5a0f9af5c2e9071467be90bbb34508ae1767321160b9dce34b7` (same bytes as `hutch-agent.webp`) |
| f3-p2.webp | 40,336 | `c9fde9d2df52b3cfa32645dfccd6dab412c2b057d1f3e2d34d78fa70c2c5c24f` |
| f4-p0.webp | 40,790 | `a14d47b88d2fb7bef35859f9d78389d8ae8fc9732473ca68dc750bf1f3f2bf64` |
| f4-p1.webp | 41,556 | `382cb739bcfc7373aee70658e1241bb1be79347b6aeafbae1ea45a0af81f07a7` |
| f4-p2.webp | 42,712 | `38571cf6fa698fad0818c8927a3045c463a13ab83bb55d17e7aeae5b0fa1a31a` |
| f5-p0.webp | 41,928 | `a495868e29359d621926acf0edc9ca05b8fad469a3e1f7c1a1d5d3c33e77a929` |
| f5-p1.webp | 42,502 | `b54a1fe3b34b8015d178cb51955e0bb36256a8766dca6d0af24d9d2566232e93` |
| f5-p2.webp | 43,274 | `2bde6becff4a9975d472f30403b21ada090b79426e4972178ba51ea8e0c372cd` |
| f6-p0.webp | 42,516 | `013cc042d8a524cdf9e6e62347c7875bd32ef39f8b99d0846efa7c9d38505a68` |
| f6-p1.webp | 42,642 | `5adc91d18f54157b3158554a4088a374a62fb18e5459183debacbedba3ed9048` |
| f6-p2.webp | 43,684 | `3f7c832430025cd866c45ca0b03016a3f08ae3b6762695993494fe315396b77a` |

Product screenshots shipped on the marketing site (not mascot, not marks):

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status | Flag |
|---|---|---|---|---|---|---|---|---|
| First-run desktop capture | `website/assets/captures/setup-desktop.webp` | 39,356 | 1440x1000 | `da748fab806a7f124902e08632a6cde5677749abba4af17f1e61c40016b48162` | Hutch-own | docs/marketing-site.md:203,241 (`docs/realignment/capture_first_run.py`, empty temp state dir) | No licence statement; product screenshot | - |
| First-run phone capture | `website/assets/captures/setup-phone.webp` | 32,126 | 390x1200 | `b1672b9cfe190da6d17fbabe171b5b4fa9e47f5dd4e7582da6df69d0c4b35f3b` | Hutch-own | docs/marketing-site.md:203,241 | as above | - |
| Response style desktop crop | `website/assets/captures/response-style-desktop.webp` | 11,212 | 586x383 | `c859b96fd6c8eb1c0d827118bb171428d980a55887d3cdcf98c7e87c369977ee` | Hutch-own | docs/marketing-site.md:242 (`docs/realignment/capture_response_style.py`, 2026-10-26) | as above | - |
| Response style phone crop | `website/assets/captures/response-style-phone.webp` | 11,596 | 340x544 | `abfc5bb403a1fc8ffdda9bbcdbcad96075ef6164d0cb572e5852f61ada4dce59` | Hutch-own | docs/marketing-site.md:242 | as above | - |

## 4. Fonts

Two byte-identical copies exist (plan item C01): `src/hutch/server/static/fonts/` and
`website/assets/fonts/`. All three files match pairwise by sha256.

| Asset | Path (both copies) | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| Geist variable, Latin subset | `src/hutch/server/static/fonts/geist-latin-var.woff2`; `website/assets/fonts/geist-latin-var.woff2` | 37,832 | woff2 (no pixel dims) | `62cce2065edc12d5069a490f00c00d42c4248e86f117be9afab99b39dd02c7c7` | font | docs/brand-assets.md:39 (Vercel Geist, npm `geist` 1.8.2, subset with fontTools pyftsubset) | "SIL Open Font License 1.1, copyright 2023 Vercel in collaboration with basement.studio; licence text is OFL-geist.txt beside each pair" (brand-assets.md:39) | Plan C01 (redistribution/derivative-subset terms) flagged for verification in Phase 1 per plan line 911; no conclusion here |
| Geist Mono variable, Latin subset | `src/hutch/server/static/fonts/geist-mono-latin-var.woff2`; `website/assets/fonts/geist-mono-latin-var.woff2` | 38,508 | woff2 | `4b617a4082284f303c4159c66fb73d1fe71f7eadd4cd2387e9bf872b426dd539` | font | docs/brand-assets.md:39 | same as above | as above |
| OFL licence text | `src/hutch/server/static/fonts/OFL-geist.txt`; `website/assets/fonts/OFL-geist.txt` | 4,368 | ASCII text | `930853ee1daa68554d9e35c8a9175affb74f699fad9a5da6ee5ebe76379d9137` | font (licence file) | docs/brand-assets.md:39 | "OFL 1.1 - licence file present" in both font directories | Doc inconsistency: `website/THIRD_PARTY_NOTICES.txt:104` still lists the earlier "Archivo variable font" with `OFL-archivo.txt` paths that no longer exist on disk; no Geist entry in that notices file |

## 5. Third-party service marks

Directory `src/hutch/server/static/brands/` (11 files, 59,949 bytes). Ten are listed in
docs/brand-assets.md:12-21 with sources; the eleventh (`ms-symbollockup_signin_dark.svg`) is
referenced in code but not listed in that table. All are consumed from `src/hutch/server/static/app.js`
(BRAND_MARK_FILES map, lines 1374-1385) except the Microsoft sign-in lockup
(`app.js:9863, 9879, 9899, 9914`).

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| OpenAI mark (white, mono blossom) | `src/hutch/server/static/brands/openai-white-monoblossom.svg` | 2,961 | 721x721 (svg) | `b94ea61d860fae6f82f43571f36f17111fcf5d348e8e9cc22ae4b441c7560011` | third-party | docs/brand-assets.md:12 ("OpenAI's published brand resources") | "vendor published - see brand-assets.md"; doc records use boundaries, no licence text bundled | Plan C19 |
| Anthropic symbol (ivory) | `src/hutch/server/static/brands/anthropic-symbol-ivory.svg` | 340 | 92x64 (svg viewBox) | `38fc06d8e9390654cc4e96aa53691e2e78d929667c0034805b6d1b3891ba22dd` | third-party | docs/brand-assets.md:13 (anthropic.com/press-kit, symbol in Ivory) | "vendor published - see brand-assets.md" | Plan C19 |
| OpenRouter glyph (volt) | `src/hutch/server/static/brands/openrouter-glyph-volt.svg` | 563 | 1024x730 (svg) | `0d22462e4f2835a5a5b9000af0a55fc9238e39996100f54706e41ec45b9d1727` | third-party | docs/brand-assets.md:14 (openrouter.ai/brand, "do not stretch, recolor, or remix") | "vendor published - see brand-assets.md" | Plan C19 |
| Gmail color icon | `src/hutch/server/static/brands/google-gmail-2026q2.png` | 2,786 | 96x96 PNG RGBA | `ab8e9e880a28e2bc29207a62394aa7d296f435113fcc922819dab629ffbd64e6` | third-party | docs/brand-assets.md:15 (Google Workspace branding kit, 2026 Q2) | "vendor published - see brand-assets.md" | Plan C19 |
| Google Calendar color icon | `src/hutch/server/static/brands/google-calendar-2026q2.png` | 3,803 | 96x96 PNG RGBA | `eac7b1d7c78a7c7fb40d74b6d879ba5fe781cbf2cd5f8d7d40f3c28fea73f77e` | third-party | docs/brand-assets.md:16 (same branding kit) | "vendor published - see brand-assets.md" | Plan C19 |
| Google Drive icon | `src/hutch/server/static/brands/google-drive.svg` | 1,293 | 192x192 (svg) | `60a6496d705d8bf010ce126469be89889db331622b14d8ae1645a38c2aaa23f5` | third-party | docs/brand-assets.md:17 (official Workspace artwork, retrieved 2026-10-26; doc hash matches measured hash) | "vendor published - see brand-assets.md" | Plan C19; doc hash verified equal |
| Google Docs icon | `src/hutch/server/static/brands/google-docs.svg` | 1,497 | 192x192 (svg) | `5e9bbbba853ebe62ddce006e41465f9d44e7a6a7cb083a770d1667bdd6e87140` | third-party | docs/brand-assets.md:18 (retrieved 2026-10-26; doc hash matches) | "vendor published - see brand-assets.md" | Plan C19; doc hash verified equal |
| Google Sheets icon | `src/hutch/server/static/brands/google-sheets.svg` | 3,524 | 192x192 (svg) | `3538632f4b58f1b5f5bd9490b69f6eda036d8a4c544b1b336121c07fd6d040cf` | third-party | docs/brand-assets.md:19 (retrieved 2026-10-26; doc hash matches) | "vendor published - see brand-assets.md" | Plan C19; doc hash verified equal |
| Microsoft Outlook product icon | `src/hutch/server/static/brands/microsoft-outlook.svg` | 3,730 | 48x48 (svg viewBox, no width/height attrs) | `4a3b6ab15d36e7c5317f75a83d1781708d68cce4d8b9073a3c82f0af662eaf18` | third-party | docs/brand-assets.md:20 (Microsoft Fluent product icon asset) | "vendor published - see brand-assets.md" | Plan C19 |
| Microsoft "Sign in with Microsoft" lockup | `src/hutch/server/static/brands/ms-symbollockup_signin_dark.svg` | 7,414 | 215x41 (svg; embedded `<title>MS-SymbolLockup</title>`, dark `#2f2f2f` button field) | `3f7dfc3df9b510da57a925cf1ece829545fc11a3d30e75a07b3accf55d3b7755` | third-party | UNKNOWN - not listed in docs/brand-assets.md:12-21 table (only Microsoft's general guidance is discussed at brand-assets.md:31-33; Phase 0 plan line 130 mentions "Microsoft Outlook + sign-in") | UNKNOWN - no per-file source/retrieval-date record in tracked docs | Gap: file ships and renders in 4 places in `app.js` but has no table row |
| Notion favicon icon | `src/hutch/server/static/brands/notion.ico` | 32,038 | 4 embedded sizes: 16, 32, 48, 64 (32-bit) | `541fc85f92e348bcf46f70944b95fd558d16adbc5a0698eaa1239dccd8c9e455` | third-party | docs/brand-assets.md:21 (notion.com/front-static/favicon.ico, retrieved 2026-10-26; doc hash matches) | "vendor published - see brand-assets.md" | Plan C19; doc hash verified equal |

docs/brand-assets.md:25-33 records the presentation rules the doc says apply (service name visible,
no endorsement, no recolour/remix, decorative aria-hidden use in the model picker, no remote icon
requests). Recorded as the doc's statements, not as a compliance conclusion.

## 6. Desktop icons (plan U07)

Directory `desktop/icons/` (4 files, 135,126 bytes). Bundled for release: `desktop/tauri.bundle.conf.json:6`
lists `icons/icon.png`, `icons/icon.ico`, `icons/icon.icns` - `icon.svg` is NOT in the bundle list.

| Asset | Path | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| App icon source SVG | `desktop/icons/icon.svg` | 295 | declares width/height 1024, viewBox 0 0 32 32 | `550abe9084cb9367bb55e168c0d8310e29f2e544cf8def03fed255a02257e950` | Hutch-own (mark-like; see flag) | PARTIAL: docs/realignment/desktop-production-2026-10-26.md:83 ("icon derived from the existing Hutch brand mark"); docs/repository-hygiene.md:52 (keeps `desktop/icons/` tracked as "packaging artwork") | UNKNOWN - no licence/provenance record for these files in docs/brand-assets.md (which covers only the web inline mark) | U07 investigated: content below; colour `#28cd9d` on `#0f151e` is NOT the documented emerald token `#34d399` (brand-assets.md:54-57) and `#28cd9d` appears nowhere else in tracked docs/config; hexagon path geometry also differs from the web favicon |
| App icon PNG | `desktop/icons/icon.png` | 10,306 | 256x256 PNG RGBA | `ce575c6f700894a823ad72b6ca21d24debf50049581c26505d7f743fec82a911` | Hutch-own | as above (desktop-production-2026-10-26.md:83) | UNKNOWN as above | Inspected: depicts the hexagon-outline-plus-centre-dot logomark, green on dark rounded square - same mark concept as the web favicon, different colour/background |
| App icon ICO | `desktop/icons/icon.ico` | 21,880 | 6 sizes: 16, 32, 48, 64, 128, 256 (32-bit) | `974b1bd7755b3c95b0168cef05d0f2a1d84d8fea07d8837c8ebb38ce78c25217` | Hutch-own | as above | UNKNOWN as above | The 256px entry is 10,306 bytes = exactly `icon.png`, i.e. the PNG is embedded verbatim |
| App icon ICNS | `desktop/icons/icon.icns` | 102,645 | 8 image entries (types ic07, ic08, ic09, ic10, ic11, ic12, ic13, ic14; per Apple type codes these span 32-1024 px - type-code reading UNVERIFIED against Apple docs, only entry order/sizes were parsed) | `d6b63e51e3c0066dd13dc122cad67080acba922a44362c4d4d713a2f01efdf41` | Hutch-own | as above | UNKNOWN as above | Bundled for macOS |

Full content of `desktop/icons/icon.svg` (295 bytes, shown because it is identity-critical and tiny):

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#0f151e"/>
  <path d="M16 3 27 9.5v13L16 29 5 22.5v-13z" fill="none" stroke="#28cd9d" stroke-width="2.2"/>
  <circle cx="16" cy="16" r="4" fill="#28cd9d"/>
</svg>
```

What it depicts (measured, not inferred from docs): a pointy-top hexagon outline with a filled
centre circle - the same mark concept as the website favicon - on a dark rounded-square background.
Differences from the web favicon (`website/index.html:24`): background rect present (favicon is
transparent), stroke `#28cd9d` vs `#34d399`, stroke-width 2.2 vs 2.5, hexagon path
`M16 3 27 9.5v13L16 29 5 22.5v-13z` vs `M16 2 28 9v14L16 30 4 23V9z`. Author, tool, date and
licence for these four files are UNKNOWN in tracked docs.

## 7. Dashboard icons (no image files)

The dashboard icon family is NOT shipped as files or an icon font; it is an inline 24x24
stroke-outline SVG family embedded in templates and JS:

| Asset | Location | Bytes | Dimensions | sha256 (full) | Kind | Provenance source | Licence status (per docs) | Flag |
|---|---|---|---|---|---|---|---|---|
| Jinja icon macro, 34 named glyphs | `src/hutch/server/templates/_icons.html` (3,802 bytes, 42 lines; used 83 times across templates) | 3,802 (file) | 24x24 viewBox | `n/a for embedded glyphs; file hash not taken (template, not artwork)` | Hutch-own (stated: "The repo bans emoji / icon characters in UI surfaces; every glyph is SVG", _icons.html:1) | UNKNOWN - no per-glyph provenance (hand-drawn vs copied from a library) recorded in tracked docs | Glyph set: chat, menu, bot, play, stop, pause, shield, clock, check, x, alert, inbox, list, calendar, cpu, chart, brain, plan, plus, trash, arrow, arrow-left, refresh, terminal, file, globe, lock, user, layers, zap, eye, download, spinner, mobile (+ home) |
| JS icon helper + path map | `src/hutch/server/static/app.js` - `function icon()` at line 1370-1372, path map immediately above (lines ~1290-1369) | n/a (embedded) | 24x24 viewBox, rendered 16px | n/a | Hutch-own | UNKNOWN as above | Map includes many Lucide-style glyph names (chart, arrow, layers, shield, key, brain, terminal, code, users, copy, externalLink, helpCircle, lock, image, command, pencil, ...) - upstream library provenance NOT recorded in tracked docs (UNVERIFIED; naming/paths resemble Lucide but no doc says so) |
| SPA shell inline glyphs | `src/hutch/server/static/index.html` (13 inline `<svg>`, e.g. nav icons lines 74-77) | n/a | 24x24 viewBox | n/a | Hutch-own | UNKNOWN as above | - |
| Avatar/sigil SVGs | `src/hutch/server/static/app.js:1517, 1551` | n/a | 24x24 / 64x64 viewBox | n/a | Hutch-own | UNKNOWN as above | - |
| Website inline glyphs | `website/index.html` (35 inline `<svg>`, e.g. lines 234-237, 254, 263, 292-658) | n/a | mixed 24/28/32/48/1120x340 viewBoxes | n/a | Hutch-own | UNKNOWN as above | Includes the header lockup and the large `viewBox="0 0 1120 340"` diagram at lines 591-633 |

## 8. Missing-expected assets (confirmed absent)

Searched repo-wide (excluding `.worktrees/`, `node_modules/`, `.venv/`, `.git/`,
`desktop/target|binaries|gen/`; docs/ included in the final pass):

| Expected asset | Result | Evidence |
|---|---|---|
| `favicon.ico` / any `favicon*` file | ABSENT | repo-wide `find` returned none; all three HTML roots use the inline data-URI SVG instead |
| `apple-touch-icon*` | ABSENT | repo-wide `find` returned none |
| `manifest.json` / `*.webmanifest` (PWA manifest) for site or dashboard | ABSENT | only match is `docs/realignment/artifacts/holistic-experience-2026-10-23/manifest.json`, a docs evidence artifact, not a web manifest |
| `.ico` files anywhere | PRESENT, 2 only | `desktop/icons/icon.ico` (Tauri app icon) and `src/hutch/server/static/brands/notion.ico` (third-party) |
| `.icns` files anywhere | PRESENT, 1 only | `desktop/icons/icon.icns` |
| Web font files other than Geist | ABSENT | repo-wide find found only the two Geist woff2 copies per directory; `OFL-archivo.txt` files referenced by `website/THIRD_PARTY_NOTICES.txt:104` do not exist |

## 9. Prior brand evidence assets (listed only, not read)

`.pipeline/marketing/2026-10/evidence/brand/` (3 files, sizes from `ls -la` on 2026-10-28):
- `README.md` - 6,372 bytes
- `render_github_social_preview.py` - 11,426 bytes
- `github-social-preview-1280x640-thumb-320w.png` - 14,794 bytes (320w thumbnail render of the GitHub social preview)

Contents not opened (listed only, per this artifact scope).

## Gaps and flags

Every row below is a STATUS gap, not a conclusion.

1. **U07 desktop `icon.svg` (now partially resolved).** Content measured and shown above: it
   depicts the hexagon-plus-dot logomark on a dark rounded square. Tracked docs say only
   "derived from the existing Hutch brand mark" (docs/realignment/desktop-production-2026-10-26.md:83).
   Author, date, tool, and any licence record are UNKNOWN. The stroke colour `#28cd9d` and
   background `#0f151e` are undocumented variants (documented accent is `#34d399`, brand
   assets.md:54-57; `#28cd9d` appears nowhere in tracked docs/config). Phase 0 plan line 127 said
   "no evidence they match the inline mark" - measured status: same mark CONCEPT, different
   geometry, colour and background; not byte- or path-identical to the web favicon.
2. **C27 mascot provenance (plan premise is stale).** Plan line 937 says "unknown provenance/
   licence"; tracked docs now DO record provenance: original Blender render via
   `scripts/render_hutch_agent.py` (docs/marketing-site.md:207-209, 239-240), and the still is
   confirmed to be byte-identical to frame f3-p1. What remains UNKNOWN: licence terms, copyright
   holder line, and published usage rules for the artwork (docs call it "decorative product art"
   and describe render mechanics only). Also unrecorded: the second shipped copy under
   `src/hutch/server/static/agent/` (21 files, 884,208 B) - no doc mentions it and no code
   reference to it was found on `main` (usage UNVERIFIED).
3. **C19 third-party marks - one file without a doc row.** `ms-symbollockup_signin_dark.svg`
   (7,414 B, sha256 `3f7dfc3d...`) ships in `brands/` and renders in four places in `app.js`
   but has no row in docs/brand-assets.md:12-21: no source URL, no retrieval date, no use-boundary
   note (Microsoft's general guidance at brand-assets.md:31-33 does not name this file). Plan line
   130 does mention "Microsoft Outlook + sign-in", so the file is known to the plan but not to the
   asset doc.
4. **C01 fonts - two copies, one stale notices file.** The Geist pair plus OFL text exist twice,
   byte-identical (docs/brand-assets.md:39 documents both locations). Gap: `website/THIRD_PARTY_
   NOTICES.txt:104` still lists "Archivo variable font ... OFL-archivo.txt" paths that no longer
   exist, and contains no Geist entry - the shipped notices text does not match the shipped fonts.
   Redistribution/subset-terms verification remains the plan's Phase 1 item (plan line 911); no
   conclusion drawn here.
5. **Identity marks have no standalone files or licence record.** The favicon/logomark exists only
   as three identical inline data-URIs; docs/brand-assets.md:48-57 gives form/colour/usage notes but
   no licence or clearance statement (by design: the doc says it "is not a legal opinion and grants
   no trademark rights"). The wordmark and social-card render method are likewise unrecorded
   beyond their doc rows.
6. **Dashboard icon provenance unknown.** Three embedded icon families (Jinja macro, JS map, inline
   shell glyphs) have no provenance record; the JS map glyph names/paths resemble a common
   open-source outline set but no tracked doc states an origin (UNVERIFIED - no library attribution
   found in tracked docs or notices files).
7. **No web-manifest / touch-icon / .ico favicon.** Confirmed absent (section 8). Recorded as
   fact only; whether that matters is outside this inventory's scope.

## Evidence

All inspection was local, on `main` at commit `577e1154`, on 2026-10-28. No network access, no
writes except this file. Commands (abridged only where the pattern repeats):

```bash
ls -la website/ website/assets/
find website/assets -type f | sort | xargs ls -la
find website/assets -type f -print0 | sort -z | xargs -0 sha256sum
find website/assets -type f | sort | xargs file
du -sb website/assets/agent website/assets/captures website/assets/fonts website/assets

grep -n -i 'favicon|icon|svg|og:image|twitter:image|manifest|apple-touch' website/index.html
grep -n -i 'favicon|icon|svg|manifest|apple-touch|data:image' src/hutch/server/static/index.html
grep -n -i 'favicon|icon|svg|manifest|apple-touch|data:image' src/hutch/server/templates/base.html
for f in website/index.html src/hutch/server/static/index.html src/hutch/server/templates/base.html; do
  grep -o 'data:image/svg+xml,[^" ]*' "$f" | head -1 | sha256sum; done

ls -la src/hutch/server/static/fonts/ src/hutch/server/static/brands/ desktop/icons/
find src/hutch/server/static/fonts src/hutch/server/static/brands desktop/icons -type f -print0   | sort -z | xargs -0 sha256sum
find src/hutch/server/static/fonts src/hutch/server/static/brands desktop/icons -type f | sort | xargs file
cat desktop/icons/icon.svg; wc -c desktop/icons/icon.svg

find . -path ./.worktrees -prune -o -path ./node_modules -prune -o -path ./.venv -prune -o   -path ./.git -prune -o -type f \( -iname 'favicon*' -o -iname 'apple-touch*' -o -iname 'manifest*'   -o -iname '*.webmanifest' -o -iname '*.ico' -o -iname '*.icns' \) -print | sort

grep -n -i 'mascot|hutch-agent|assets/agent|frame|provenance|capture|og-card|github-social|icon' docs/marketing-site.md
grep -n 'openai-white|anthropic-symbol|...|Geist' docs/brand-assets.md
grep -rn 'ms-symbollockup' --include='*.py' --include='*.js' --include='*.html' --include='*.md' src website docs desktop scripts
grep -rn '28cd9d' --include='*.md' --include='*.json' --include='*.py' --include='*.rs' --include='*.html' docs desktop scripts website
git show brand/plan:docs/brand/00-PLAN.md | grep -n 'C01|C19|C27|U07'
git ls-files src/hutch/server/static/agent | wc -l
diff <(cd website/assets/agent && sha256sum *.webp) <(cd src/hutch/server/static/agent && sha256sum *.webp)

# python3 header parses (read-only): .ico entry directories and .icns entry table
python3 - <<'EOF'   # struct-parse of desktop/icons/icon.ico, brands/notion.ico, desktop/icons/icon.icns
...
EOF
```

Vendor URLs appearing above are quoted from docs/brand-assets.md and were NOT fetched or re-
verified in this run (access date for the doc statements: 2026-10-28). `docs/brand/00-PLAN.md`
does not exist on `main`; plan line references are line numbers in
`git show brand/plan:docs/brand/00-PLAN.md` output.
