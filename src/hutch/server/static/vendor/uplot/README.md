# Vendored: uPlot 1.6.32 (MIT)

Pinned chart engine used by `src/hutch/server/static/widgets.js` to render `chart`
output blocks. Do not edit these files; bump by re-fetching a new pinned version.

| File | Source URL (fetched 2026-10-11) | SHA-256 |
|---|---|---|
| `uPlot.iife.min.js` | `https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.iife.min.js` | `19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f` |
| `uPlot.min.css` | `https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css` | `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04` |
| `LICENSE` | `https://raw.githubusercontent.com/leeoniya/uPlot/master/LICENSE` (tag `v1.6.32` has no LICENSE path; the MIT text is identical across the 1.x line, copyright Leon Sorokin 2022) | `8f989229699b4fe2f1a0432d0e9edc338a8a911e250e2d1b01ecd770a5f5b1bd` |

- Version: **1.6.32** (banner comment in `uPlot.iife.min.js` line 1: `/*! https://github.com/leeoniya/uPlot (v1.6.32) */`).
- Format: classic-script IIFE (`var uPlot = function(){...}()`) — defines the global
  `uPlot` when loaded via `<script src>`; verified with `node --check` (full-file
  syntax parse, so a truncated file cannot pass) and a `vm.runInThisContext` load
  (`typeof uPlot === "function"`, static keys: assign, fmtNum, rangeNum, rangeLog,
  rangeAsinh, orient, pxRatio, join, fmtDate, tzDate, sync, addGap, clipGaps, paths).
- License: MIT (see `LICENSE`). No other files from the package are used; the app
  never fetches uPlot at runtime.
- `uPlot.min.css` is imported by `widgets.css` conventions: it is linked directly
  from `index.html` before `style.css` so the app's tokens can restyle the chart
  chrome. Its rules only target `.uplot`-scoped classes.
