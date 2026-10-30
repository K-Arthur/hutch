# native/docgen_xlsx

Optional PyO3 (0.29.3) + rust_xlsxwriter (0.90.2) kernel for the **write stage** of
`hutch.documents.docgen.xlsx`. The pure-Python XlsxWriter path stays the reference
implementation, the fallback, and the independent-validation anchor: this crate only
renders bytes, it never replaces the openpyxl read-back gate.

- crate: `native/docgen_xlsx` (cdylib + rlib, Cargo.lock committed)
- module: `hutch_docgen_native`, one function `write_workbook(spec_json: str) -> bytes`
- installed by: `scripts/build_native_docgen.py` into
  `src/hutch/documents/docgen/_native/` (git-excluded build output)
- Python tests: `tests/test_docgen_native_parity.py` (skip cleanly when the module is absent)
- A/B harness: `benchmarks/native_docgen_ab.py`

## Build

```bash
PYTHONPATH=$PWD/src .venv/bin/python scripts/build_native_docgen.py --check
```

The script pins `CARGO_HOME=$PWD/.cargo-home`, `CARGO_TARGET_DIR=$PWD/.cargo-target` and
`PYO3_PYTHON` (defaults to the interpreter running the script) so a read-only
`$HOME/.cargo` and a reset `/tmp` do not matter. `--clean` removes the caches and the
installed module. Cargo commands from the crate directory:

```bash
export CARGO_HOME=$PWD/.cargo-home CARGO_TARGET_DIR=$PWD/.cargo-target
export PYO3_PYTHON=/path/to/.venv/bin/python
cargo test                                             # pure-Rust core, no libpython link
cargo clippy --all-targets -- -D warnings
cargo clippy --all-targets --features python -- -D warnings
cargo build --release --locked --features python       # extension module
cargo fmt --check
```

The PyO3 binding is behind the non-default `python` feature so `cargo test` links no
libpython; the build script passes `--features python`.

## Boundary format

`xlsx.py` normalizes a document spec into `_Sheet` values; the loader serializes them
deterministically as JSON:

```json
{"sheets": [
  {"name": "Weekly",
   "header": ["week", "units"],
   "rows": [[["str", "2026-W01"], ["num", 3], ["date", "2026-01-15"],
             ["formula", "SUM(B2:B3)", 7]]],
   "freeze": true,
   "col_widths": [12.5, 8]}
]}
```

- `name`: already-sanitized sheet name (still re-validated here: <=31 chars, no
  `[]:*?/\`, no leading/trailing apostrophe, not `History`, unique
  case-insensitively).
- `header`: list of strings (the Python normalizer only produces strings).
- `rows`: list of rows, each a list of cells; cells are compact arrays:
  `["str", text]`, `["num", number]`, `["date", "YYYY-MM-DD"]`,
  `["formula", expression, cached_number]`. The formula expression must be normalized
  (leading `=` stripped) as `xlsx.py` does; cached values are always present because the
  hutch gate rejects formula cells without a real cached result.
- `freeze`: boolean; `true` requires a non-empty header and freezes row 1
  (`freeze_panes(1, 0)`).
- `col_widths`: numeric Excel character widths in `[0, 255]`, at most the sheet width.

Anything else (unknown keys, malformed cells, out-of-bounds values, bad dates) raises
Python `ValueError`; the Rust code never panics on user input.

## Render semantics (parity with `_write_workbook`)

| xlsx.py call | native behaviour |
|---|---|
| `write_string` | `Worksheet::write_string` (leading zeros stay text); empty strings are storeable text, see below |
| `write_number` | `Worksheet::write_number` |
| `write_datetime(..., yyyy-mm-dd)` | 1900-date-system serial written as a number with a `yyyy-mm-dd` format |
| `write_formula("=" + body, None, cached)` | `Formula::new` + `Formula::set_result(cached)`; workbook requests recalc on open |
| `set_calc_mode("auto")` | rust_xlsxwriter writes `<calcPr calcId="124519" fullCalcOnLoad="1"/>` |
| `freeze_panes(1, 0)` | `Worksheet::set_freeze_panes(1, 0)` |
| `set_column(c, c, width)` | `Worksheet::set_column_width(c, width)` (same XlsxWriter pixel quantization) |

### Empty strings

rust_xlsxwriter deliberately drops empty strings ("Excel ignores them") while the
reference writer stores them as shared text, so `""` must round-trip through the
openpyxl gate. The writer therefore renders empty-text cells as a collision-free
Unicode private-use placeholder and rewrites that one `xl/sharedStrings.xml` entry to
`<si><t></t></si>` after saving (`src/writer.rs`, covered by Rust unit tests and the
parity corpus's `empty_string_cells` / `preview_bounded_shape` cases). Workbooks with
no empty-string cells skip the rewrite, so there is no repacking cost on the normal
path.

Known, intentional divergences (both paths still fail the gate or still hide the column):

- Strings longer than Excel's 32,767-character cell limit are rejected with `ValueError`;
  XlsxWriter silently truncates them (the Python gate then rejects the truncation).
- A column width of exactly 0 is written as an explicitly hidden default-width column
  (openpyxl width 0.0, `hidden="1"`), while XlsxWriter writes `width="0"` without the
  hidden flag. Excel hides the column either way; the gate does not inspect widths.
