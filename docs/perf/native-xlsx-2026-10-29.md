# Optional native XLSX writer (2026-10-29)

Status: implemented as an **optional** accelerator. The pure-Python generator remains the reference
implementation and the fallback; the independent openpyxl read-back gate is unchanged and still
decides whether a generated workbook is promoted.

## Why this shape

The earlier programme measured the XLSX write stage at ~109 ms of a ~297 ms 5000-row generation and
prototyped a PyO3 + rust_xlsxwriter writer at ~24 ms. Opening the writes to Rust yields a real CPU win
without changing the document-safety contract, but it must not make Rust a mandatory dependency for a
Python-first local install. It is therefore an optional extension module with an explicit fallback.

## Layout

| Path | Purpose |
|---|---|
| `native/docgen_xlsx/` | Pinned Rust crate (`Cargo.lock` committed). Pure-Rust spec parser and writer; the PyO3 binding is behind the non-default `python` feature so `cargo test`/`cargo clippy` do not link libpython. `write_workbook(spec_json) -> bytes`; every bad input raises a Python `ValueError`, never a panic. |
| `scripts/build_native_docgen.py` | Builds with the interpreter running the script (`PYO3_PYTHON`), keeps `CARGO_HOME`/`CARGO_TARGET_DIR` inside the checkout, copies the module to `src/hutch/documents/docgen/_native/`, smoke-tests it, and supports `--check` / `--clean`. |
| `src/hutch/documents/docgen/native.py` | Optional loader. Looks for the installed module, serializes the normalized `_Sheet` structures to the crate's deterministic JSON boundary, and raises `NativeUnavailable` when it is absent. `HUTCH_DISABLE_NATIVE_DOCGEN=1` forces the Python path for tests and operators. |
| `src/hutch/documents/docgen/xlsx.py` | `_write_workbook` tries the native writer only when it is present; the reference writer code is unchanged below it. The generator file remains below its frozen line cap because the preview helpers moved to `xlsx_preview.py`. |
| `tests/test_docgen_native_parity.py` | Parity corpus: both writers must pass the existing `_verify_written_workbook` and decode equal through openpyxl (strings incl. leading zeros and unicode, numbers, dates, cached formulas, freeze, column widths, multi-sheet, empty strings, bounds). Skips cleanly when the extension is absent. |
| `benchmarks/native_docgen_ab.py` | One-driver paired A/B with preflight verification: write-stage only (Python vs native incl. JSON boundary and `.so` call) and full `generate('xlsx', ...)` where only the writer is native while the independent read-back gate still runs. |

## Build and run

```bash
# from the repository root, using the project venv interpreter
python scripts/build_native_docgen.py --check   # build + install + smoke test
python -m pytest -q tests/test_docgen_native_parity.py tests/test_docgen_xlsx.py
HUTCH_DISABLE_NATIVE_DOCGEN=1 python -m pytest -q tests/test_docgen_xlsx.py   # fallback proof
python benchmarks/native_docgen_ab.py           # paired measurement
```

CI: `.github/workflows/ci.yml` has a `native-xlsx` job that installs pinned Rust 1.97.1, runs
`cargo test` + `cargo clippy -D warnings` on the pure-Rust core, builds the extension with `--check`,
runs the parity/docgen tests through the native path, and re-runs the docgen suite with the native
module disabled. The ordinary Python test matrix is unchanged and does not require Rust.

## Packaging status

- This repository is installed from source for local-first use. The extension is an optional build
  artifact: nothing in `pyproject.toml`, `uv.lock` or the default install path was changed, so a plain
  install simply uses the Python writer. Maturin/abi3 wheel integration is a deliberate follow-up,
  not a safety prerequisite; it is also why this slice does not touch the manifest files.
- Desktop/PyInstaller builds can opt in by running the build script before the backend freeze; that
  wiring is documented as a follow-up so the Python-only desktop path stays unchanged.
- Platform note: the build script maps `.so`/`.dylib`/`.pyd` names for Linux/macOS/Windows, but only
  Linux was built and validated in this programme; macOS/Windows compilation and loading remain
  unverified.

## Behaviour notes

- Empty strings: rust_xlsxwriter deliberately ignores them. The crate substitutes a collision-free
  private-use placeholder and rewrites `sharedStrings.xml` so the cell reads back as an empty string,
  matching the reference writer; this was found by the existing preview/round-trip test and is covered
  by crate unit tests incl. placeholder collision.
- Dates use the Excel 1900 system serial with the same `yyyy-mm-dd` format; formulas carry the declared
  cached value; the workbook requests recalculation on open, as the existing archive assertion requires.
- On any native error the Python path is **not** silently substituted (that would hide divergence).
  The kernel is guarded by parity tests and by the unchanged independent read-back gate.

## Measured result

One Python driver, paired samples, same process; preflight verified both writers passed the unchanged
openpyxl gate and decoded output equal before timing. Two runs were recorded because the host is shared
and the relative split depends on how much of the pure-Python time is the (unchanged) validation gate:

| Run (load) | Write stage median (Python -> native) | Write p95 | Full generation median | Full p95 |
|---|---|---|---|---|
| loaded (loadavg 3.3 start / 5.2 end), n=20 write / 15 full | 82.98 -> 44.34 ms (-46.6%) | 161.48 -> 95.68 ms (-40.7%) | 291.54 -> 237.26 ms (-18.6%) | 343.41 -> 273.96 ms (-20.2%) |
| quiet (loadavg 2.1, n=30 write / 25 full) | 53.4% median gain (ratio 0.467) | -27.3% | 170.25 -> 132.47 ms (-22.2%) | 205.99 -> 178.16 ms (-13.5%) |

Boundary per workbook: one Python<->Rust crossing, 328.8 KiB JSON payload; JSON encode 10.7-15.3 ms and
`.so` call 21.8-24.6 ms, i.e. the boundary is included in the numbers above. The write stage is ~28-42%
of pure-Python full generation, so full-generation gains are bounded by that share and by the unchanged
independent read-back gate (the largest component).

**Honest reading of the pre-registered bar.** The plan's threshold was an absolute p95 <=252 ms for the
5000-row case (20% below the 315.3 ms baseline). The quiet run meets that absolute target (native p95
178 ms); the loaded run does not (274 ms) while its *relative* paired p95 gain is 20.2%. The relative
gain ranged 13.5-20.2% across the two runs and is host-load dependent, so this programme does **not**
claim a stable >=20% p95 improvement. What is consistent and large is the write-stage gain (-47% to
-53% median) and the full-generation median gain (-19% to -22%). The kernel stays optional, is guarded
by the parity corpus and the unchanged gate, and is documented as an experimental accelerator rather
than as a validated replacement of the reference writer on every host.

Artifacts: `.dsh/long-horizon/hutch-wins/artifacts/native/ab.json` (first run) and `ab-rerun.json`
(second run), each with every sample, machine metadata and load average.
