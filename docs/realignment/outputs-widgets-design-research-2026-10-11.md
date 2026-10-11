# Typed-output widgets — design research ledger (2026-10-11)

Task: render typed output blocks (chart, table, code_receipt, media, timeline, comparison,
flowchart, artifact_ref, status) in Studio chat and the workspace, keeping Hutch's existing
dark/emerald identity and tokens.

## Incumbent (inspected)

* `DESIGN.md` tokens: near-black surfaces (`#05070a` ground, `#080c12` panel, `#10161f`
  raised), emerald accent (`#34d399`), Archivo display + system body, 12px caption/mono
  metadata, radius scale `--r-*`.
* Studio transcript (screenshot `docs/realignment/artifacts/versioned-artifacts/desktop.png`,
  inspected): compact tool-line chips with check/x verdicts, `source` flag chips,
  hash-verified "Saved full output / Download" cards, dense left sidebar.
* Constraint: keep identity and tokens; vary composition/interaction only.

## Online examples inspected (actual pixels, 2026-10-11)

Method: headless Chromium 1243 screenshots (1440×900) of live public interfaces, read as
images. Figma Community was attempted first per the selected route but its pages/CDN began
rate-limiting after one fetch (cover URL returned a 919-byte placeholder; Community API 404)
— disclosed blocker, replaced with live shipped interfaces.

| # | Product / source | What was inspected | Observations used |
|---|---|---|---|
| 1 | Mermaid Live Editor — https://mermaid.live | live flowchart renderer with code pane | source beside render; edge labels inline; node shapes carry meaning; diagram-type chips |
| 2 | Chart.js samples — https://www.chartjs.org/docs/latest/samples/line/line.html | live line chart page | legend pills top-centered; gridlines; sample control buttons; tooltip-on-hover |
| 3 | Vega Editor — https://vega.github.io/editor/#/examples/vega-lite/bar | live spec editor + bar chart | spec pane + render pane; DATA VIEWER / SIGNAL VIEWER tabs = inspect the values behind a view |
| 4 | MCP Apps spec — https://apps.extensions.modelcontextprotocol.io/api/documents/overview.html | docs | "UI is a progressive enhancement, not a requirement"; host-rendered UI in sandboxed iframes; declarative CSP |
| 5 | Ant Design Timeline — https://ant.design/components/timeline | live component docs | vertical rail, dot variants, secondary timestamp line, dense lists |
| 6 | AG Grid example — https://www.ag-grid.com/example/ | live 1000-row grid demo | sticky header, per-column filters, right-side column panel, drag-to-group, compact toolbar |

Concept templates vs shipped products: all six are shipped products/docs (live interfaces),
not concept kits. No Figma Community frame was visually inspected (blocked, disclosed).

## Patterns worth adapting

* Show the **source/spec** and the **rendered view** as two inspectable sides (Mermaid,
  Vega), and let chart readers open the underlying values (Vega data viewer).
* **Text fallback is first-class**, not a failure mode (MCP Apps progressive enhancement;
  Hutch's block contract already requires `text_fallback`).
* Dense tables need **per-column controls and a sticky header** (AG Grid) without turning
  the transcript into a spreadsheet app.
* Timeline state can ride on **dot treatment + secondary timestamp** (AntD) instead of color
  alone.
* Charts: **legend pills + gridlines + hover tooltip** (Chart.js) are familiar and cheap;
  drag-zoom and keyboard traversal are additive, not required to look "interactive".

## Patterns deliberately not transferred

* Light themes and large hero chart canvases (Chart.js/Vega docs are light-themed).
* Mermaid's code-first mental model as the *only* view: Hutch blocks come from executed
  data, so the render leads and the source/data is the inspection layer.
* AG Grid's full spreadsheet feature set (pivot, grouping, column reordering) — out of
  scope and a maintenance trap; comparison matrices get sort/filter/highlight only.
* Sandboxed-iframe widget hosting (MCP Apps) for ordinary output: Hutch renders typed data
  with its own trusted components; the isolated rich-view path stays optional.

## Routes presented to the user (2026-10-11)

1. **Inline cards + side peek** (recommended): compact cards in the transcript; "Open"
   expands a right-side inspection panel (View / Source / Data tabs) without moving the
   reading position.
2. **Workspace-first tabbed canvas**: blocks are chips; opening one takes over a full-height
   workspace with tabs; multiple blocks become tabs.
3. **Receipt-forward provenance cards**: every output is a receipt card (status, generation,
   hash, files) with the render inside.
4. **Minimal text-first, inline expansion only**: no side panel; expand in place; smallest
   footprint.

## Approval

Asked in the conversation on 2026-10-11 via the question tool. Chosen route: _(pending)_

* **Chosen:** _(recorded after the user answers)_
