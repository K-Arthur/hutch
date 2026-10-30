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

One Python driver, paired samples, same process, loadavg 3.3 at start / 5.2 at end; preflight verified
both writers passed the unchanged openpyxl gate and decoded equal before any timing:

| Case | Pure Python (median / p95) | Native (median / p95) | Paired effect |
|---|---|---|---|
| Write stage only (JSON encode + `.so` call included) | 82.98 / 161.48 ms | 44.34 / 95.68 ms | median **-46.6%**, p95 **-40.7%** |
| Full `generate('xlsx', spec)` (independent gate included) | 291.54 / 343.41 ms | 237.26 / 273.96 ms | median **-18.6%**, p95 **-20.2%** |

The boundary is one Python<->Rust crossing per workbook: 328.8 KiB JSON payload, JSON encode 15.34 ms,
`.so` call 24.64 ms of the native write stage. The write stage is ~28% of pure-Python full generation,
so the full-generation gain is bounded by that share; the measured p95 gain **meets the repository P11
operation-level bar (>=20% p95 including the boundary)**. This is an operation-level result: end-to-end
document workflows are dominated by model drafting and by the independent validation gate, and no
user-latency claim beyond large workbook generation is made. Artifact:
`.dsh/long-horizon/hutch-wins/artifacts/native/ab.json` (19 samples per side for the write stage,
15 per side for full generation; min/median/p95/max in the JSON).