"""Parity between the optional native XLSX writer and the pure-Python reference writer.

Skipped cleanly (not failed) when the extension has not been built; see
`scripts/build_native_docgen.py`. For every corpus case:

(a) the native bytes pass `xlsx.py::_verify_written_workbook` -- the unchanged independent
    openpyxl promotion gate,
(b) openpyxl decodes the native workbook equal to the pure-Python writer's output
    (sheet names/order, cell values, formula text, frozen pane, column widths),
(c) the native bytes are a valid xlsx archive requesting recalculation on load.

The reference writer is authoritative: a mismatch here is a native bug. The reference
bytes come from the XlsxWriter path even when the Lead's integrated loader would route
`_write_workbook` through the native extension.
"""

from __future__ import annotations

import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import re
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from openpyxl import load_workbook

from hutch.documents.docgen import xlsx

_MODULE_NAME = "hutch_docgen_native"
_NATIVE_DIR = Path(xlsx.__file__).resolve().parent / "_native"
_EXTENSION_SUFFIXES = {".so", ".pyd", ".dylib"}


def _load_native() -> ModuleType | None:
    if not _NATIVE_DIR.is_dir():
        return None
    for path in sorted(_NATIVE_DIR.iterdir()):
        if not (path.name.startswith(_MODULE_NAME) and path.suffix in _EXTENSION_SUFFIXES):
            continue
        try:
            loader = importlib.machinery.ExtensionFileLoader(_MODULE_NAME, str(path))
            spec = importlib.util.spec_from_loader(_MODULE_NAME, loader)
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module
        except Exception:  # pragma: no cover - an unloadable build counts as absent
            continue
    return None


_NATIVE = _load_native()

pytestmark = pytest.mark.skipif(
    _NATIVE is None,
    reason="native docgen extension is not built (run scripts/build_native_docgen.py --check)",
)


def _encode_cell(cell: tuple[Any, ...]) -> list[Any]:
    kind = cell[0]
    if kind == "str":
        return ["str", cell[1]]
    if kind == "num":
        return ["num", cell[1]]
    if kind == "date":
        return ["date", cell[1].isoformat()]
    return ["formula", cell[1], cell[2]]


def _encode_sheets(sheets: list[Any]) -> str:
    return json.dumps(
        {"sheets": [
            {"name": sheet.name, "header": sheet.header,
             "rows": [[_encode_cell(cell) for cell in row] for row in sheet.rows],
             "freeze": sheet.freeze, "col_widths": sheet.col_widths}
            for sheet in sheets
        ]},
        ensure_ascii=False, separators=(",", ":"),
    )


def _native_bytes(sheets: list[Any]) -> bytes:
    assert _NATIVE is not None
    data = _NATIVE.write_workbook(_encode_sheets(sheets))
    assert isinstance(data, bytes)
    return data


def _reference_bytes(sheets: list[Any]) -> bytes:
    """Pure-Python XlsxWriter bytes, even when the integrated loader is present."""
    loader = getattr(xlsx, "_native_write_workbook", None)
    if loader is None:
        return xlsx._write_workbook(sheets)

    def _force_reference(_sheets: list[Any]) -> bytes:
        from hutch.documents.docgen.native import NativeUnavailable

        raise NativeUnavailable("parity test forces the reference writer")

    xlsx._native_write_workbook = _force_reference
    try:
        return xlsx._write_workbook(sheets)
    finally:
        xlsx._native_write_workbook = loader


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")
    return value


def _decode(data: bytes) -> dict[str, Any]:
    """Sheet names/order, cell values, formula text, freeze pane and column widths."""
    cached = load_workbook(io.BytesIO(data), data_only=True)
    raw = load_workbook(io.BytesIO(data), data_only=False)
    try:
        decoded: dict[str, Any] = {"sheetnames": cached.sheetnames, "sheets": {}}
        for name in cached.sheetnames:
            values_ws, raw_ws = cached[name], raw[name]
            rows = [[_normalize_value(cell.value) for cell in row] for row in values_ws.iter_rows()]
            formulas = {
                cell.coordinate: re.sub(r"[\s$]", "", cell.value)
                for row in raw_ws.iter_rows() for cell in row
                if isinstance(cell.value, str) and cell.value.startswith("=")
            }
            widths = {
                column: dimension.width
                for column, dimension in raw_ws.column_dimensions.items()
                if dimension.width is not None
            }
            decoded["sheets"][name] = {
                "rows": rows, "freeze": values_ws.freeze_panes,
                "formula_cells": formulas, "widths": widths,
            }
        return decoded
    finally:
        cached.close()
        raw.close()


def _assert_decoded_equal(reference: bytes, native: bytes) -> None:
    expected_all, actual_all = _decode(reference), _decode(native)
    assert actual_all["sheetnames"] == expected_all["sheetnames"]
    for name in expected_all["sheetnames"]:
        expected, actual = expected_all["sheets"][name], actual_all["sheets"][name]
        assert actual["rows"] == expected["rows"], f"cell values differ on sheet {name!r}"
        assert actual["freeze"] == expected["freeze"], f"freeze pane differs on sheet {name!r}"
        assert actual["formula_cells"] == expected["formula_cells"], (
            f"formula text differs on sheet {name!r}")
        assert set(actual["widths"]) == set(expected["widths"]), (
            f"column width columns differ on sheet {name!r}")
        for column, width in expected["widths"].items():
            assert actual["widths"][column] == pytest.approx(width, abs=1e-9), (
                f"column {column} width differs on sheet {name!r}")


# ----------------------------------------------------------------------------------
# Corpus: every case is (id, document spec). Covers the contract's typed cells, the
# write-stage features and the previously-diverging empty-string cell.
# ----------------------------------------------------------------------------------
_CORPUS: list[tuple[str, dict[str, Any]]] = [
    ("realistic", {"sheets": [{
        "name": "Weekly", "header": ["week", "region", "units", "revenue"],
        "rows": [["2026-W01", "north", 3, 1.75], ["2026-W02", "south", 0, 0.0],
                 ["007", "east", -2, -2.5],
                 [{"date": "2026-01-15"}, "naïve", 1000000, 123456789.5]],
        "freeze_header": True, "col_widths": [12.5, 8, 6.25, 0]}]}),
    ("strings_leading_zeros_and_unicode", {"sheets": [{
        "name": "Strings", "header": ["id", "note"],
        "rows": [["0001", "café"], ["00000042", "日本語"], ["0", "Ελληνικά"],
                 ["00", "straße"]]}]}),
    ("numbers_int_and_float", {"sheets": [{
        "name": "Numbers", "header": ["int", "float"],
        "rows": [[0, -0.5], [-7, 1e20], [1000000, 1e-20], [42, 0.1]]}]}),
    ("dates", {"sheets": [{
        "name": "Dates", "header": ["day"],
        "rows": [["2024-02-29"], ["2026-01-15"], ["1999-12-31"], ["9999-12-31"]]}]}),
    ("formulas_with_cached_values", {"sheets": [{
        "name": "Formulas", "header": ["a", "b", "sum", "mean"],
        "rows": [
            [1, 2, {"formula": "SUM(A2:B2)", "value": 3},
             {"formula": "AVERAGE($A$2:$B$2)", "value": 1.5}],
            [3, 4, {"formula": "SUM(A2:B3)", "value": 10},
             {"formula": "COUNT(A2:B3)", "value": 4}],
            [5, 6, {"formula": "MAX(A2:B4)", "value": 10},
             {"formula": "MIN(A2:B4)", "value": 1}],
            [7, 8, {"formula": "SUM(1,2,3)", "value": 6},
             {"formula": "AVERAGE(1,2,3)", "value": 2}]]}]}),
    ("freeze_and_column_widths", {"sheets": [{
        "name": "Frozen", "header": ["a", "b", "c", "d"],
        "rows": [[1, 2, 3, 4]], "freeze_header": True,
        "col_widths": [0, 0.5, 1, 255]}]}),
    ("multiple_sheets_and_empty_sheet", {"sheets": [
        {"name": "First", "header": ["x"], "rows": [[1], [2], [3]]},
        {"name": "Second", "rows": [[{"date": "2026-01-15"},
                                     {"formula": "SUM(A2:A4)", "value": 6}]]},
        {"name": "Empty", "rows": []},
        {"name": "OneCell", "rows": [["only"]]}]}),
    ("ragged_rows", {"sheets": [{
        "name": "Ragged", "header": ["a", "b", "c"],
        "rows": [["x"], ["y", 2], ["z", 3, 4.5]]}]}),
    ("empty_string_cells", {"sheets": [{
        "name": "EmptyStrings", "header": ["name", "note"],
        "rows": [["alpha", ""], ["beta", ""], ["gamma", "not empty"]]}]}),
    ("preview_bounded_shape", {"sheets": [{
        "name": "P", "header": ["Name", "Note"],
        "rows": [[7, "z" * 500, {"date": "2026-01-31"},
                  {"formula": "COUNT(A2:A2)", "value": 1}]]
                + [[5, ""] for _ in range(11)]}]}),
    ("mixed_types_no_header", {"sheets": [{
        "name": "Mixed",
        "rows": [["text", 1, 2.5, {"date": "2026-02-01"}],
                 [{"formula": "SUM(B1:C1)", "value": 3.5}, "", -1, "0007"]]}]}),
]

_CORPUS_IDS = [case[0] for case in _CORPUS]


def _sheets_for(spec: dict[str, Any]) -> list[Any]:
    sheets, _findings = xlsx._normalize_sheets(spec)
    return sheets


@pytest.mark.parametrize("case", _CORPUS, ids=_CORPUS_IDS)
def test_native_passes_promotion_gate(case: tuple[str, dict[str, Any]]) -> None:
    _name, spec = case
    sheets = _sheets_for(spec)
    native = _native_bytes(sheets)
    xlsx._verify_written_workbook(native, sheets)  # (a) unchanged independent gate
    assert native[:4] == b"PK\x03\x04"  # (c) real xlsx archive
    with zipfile.ZipFile(io.BytesIO(native)) as archive:
        assert archive.testzip() is None
        assert b'fullCalcOnLoad="1"' in archive.read("xl/workbook.xml")


@pytest.mark.parametrize("case", _CORPUS, ids=_CORPUS_IDS)
def test_native_decodes_equal_to_reference_writer(case: tuple[str, dict[str, Any]]) -> None:
    _name, spec = case
    sheets = _sheets_for(spec)
    reference = _reference_bytes(sheets)
    xlsx._verify_written_workbook(reference, sheets)
    _assert_decoded_equal(reference, _native_bytes(sheets))


def test_integrated_loader_round_trips_through_the_gate() -> None:
    """The Lead's loader, when integrated, produces bytes the reference gate accepts."""
    try:
        from hutch.documents.docgen import native as loader
    except ImportError:  # pragma: no cover - loader not integrated in this tree
        pytest.skip("integrated native loader module is not present")
    if not loader.available():
        pytest.skip("integrated native loader reports the extension as unavailable")
    sheets = _sheets_for(_CORPUS[0][1])
    data = loader.write_workbook(sheets)
    xlsx._verify_written_workbook(data, sheets)
    _assert_decoded_equal(_reference_bytes(sheets), data)


_BOUNDS_CASES: list[tuple[str, str]] = [
    ("not_json", "this is not json"),
    ("missing_sheets", "{}"),
    ("sheet_not_object", '{"sheets": ["nope"]}'),
    ("empty_workbook", '{"sheets": []}'),
    ("sheet_name_too_long", '{"sheets": [{"name": "' + "a" * 32 + '", "rows": []}]}'),
    ("sheet_name_bad_char", '{"sheets": [{"name": "a/b", "rows": []}]}'),
    ("sheet_name_apostrophe", json.dumps({"sheets": [{"name": "'quoted'", "rows": []}]})),
    ("duplicate_sheet_names", '{"sheets": [{"name": "S", "rows": []}, {"name": "s", "rows": []}]}'),
    ("too_many_sheets", json.dumps({"sheets": [{"name": f"S{i}", "rows": []} for i in range(21)]})),
    ("column_width_too_wide",
     '{"sheets": [{"name": "S", "rows": [[["num", 1]]], "col_widths": [300]}]}'),
    ("column_width_negative",
     '{"sheets": [{"name": "S", "rows": [[["num", 1]]], "col_widths": [-1]}]}'),
    ("freeze_without_header",
     '{"sheets": [{"name": "S", "rows": [[["num", 1]]], "freeze": true}]}'),
    ("invalid_date", '{"sheets": [{"name": "S", "rows": [[["date", "2026-02-30"]]]}]}'),
    ("malformed_date", '{"sheets": [{"name": "S", "rows": [[["date", "15-01-2026"]]]}]}'),
    ("cell_wrong_arity", '{"sheets": [{"name": "S", "rows": [[["num", 1, 2]]]}]}'),
    ("unknown_cell_kind", '{"sheets": [{"name": "S", "rows": [[["bool", true]]]}]}'),
    ("string_in_number_cell", '{"sheets": [{"name": "S", "rows": [[["num", "x"]]]}]}'),
    ("unknown_sheet_key", '{"sheets": [{"name": "S", "rows": [], "bogus": 1}]}'),
    ("long_string", '{"sheets": [{"name": "S", "rows": [[["str", "' + "x" * 32768 + '"]]]}]}'),
]
_BOUNDS_IDS = [case[0] for case in _BOUNDS_CASES]


@pytest.mark.parametrize("case", _BOUNDS_CASES, ids=_BOUNDS_IDS)
def test_bounds_errors_raise_value_error_not_panic(case: tuple[str, str]) -> None:
    _name, bad_json = case
    assert _NATIVE is not None
    with pytest.raises(ValueError):
        _NATIVE.write_workbook(bad_json)


def test_row_limit_error_is_a_value_error() -> None:
    assert _NATIVE is not None
    spec = {"sheets": [{"name": "Big", "rows": [[] for _ in range(xlsx.MAX_SHEET_ROWS + 1)]}]}
    with pytest.raises(ValueError):
        _NATIVE.write_workbook(json.dumps(spec))
