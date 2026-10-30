"""Optional native XLSX write kernel (Rust/PyO3) with a pure-Python fallback.

The extension is optional by design: an installed wheel/source tree without the built
artifact simply uses the reference Python writer in ``xlsx.py``. The independent openpyxl
read-back gate is never replaced by this module; it validates whichever writer produced
the bytes. Build with ``scripts/build_native_docgen.py``.

Wire format (mirrored from native/docgen_xlsx/src/spec.rs):
{"sheets": [{"name": str, "header": [str], "rows": [[["str"|"num"|"date"|"formula", ...]]],
            "freeze": bool, "col_widths": [float]}]}
A formula cell is ["formula", expression_without_leading_equals, cached_number]; a date is
["date", "YYYY-MM-DD"].
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

MODULE_NAME = "hutch_docgen_native"
_NATIVE_DIR = Path(__file__).resolve().parent / "_native"
_LOADED: Any = None
_LOAD_ATTEMPTED = False


class NativeUnavailable(RuntimeError):
    """The optional native writer is not built or cannot be loaded; use the Python writer."""


def _candidate_files() -> list[Path]:
    if not _NATIVE_DIR.is_dir():
        return []
    suffixes = (".so", ".pyd", ".dylib")
    return sorted(path for path in _NATIVE_DIR.iterdir()
                  if path.name.startswith(MODULE_NAME) and path.suffix in suffixes)


def _load() -> Any:
    global _LOADED, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _LOADED
    _LOAD_ATTEMPTED = True
    if os.environ.get("HUTCH_DISABLE_NATIVE_DOCGEN") == "1":
        return None
    try:
        _LOADED = importlib.import_module(MODULE_NAME)
        return _LOADED
    except Exception:
        _LOADED = None
    for path in _candidate_files():
        try:
            loader = importlib.machinery.ExtensionFileLoader(MODULE_NAME, str(path))
            spec = importlib.util.spec_from_loader(MODULE_NAME, loader)
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[MODULE_NAME] = module
            loader.exec_module(module)
            _LOADED = module
            return module
        except Exception:
            sys.modules.pop(MODULE_NAME, None)
            _LOADED = None
    return None


def available() -> bool:
    """Whether the optional native writer can be used in this installation."""
    return _load() is not None


def _cell_json(cell: Any) -> list[Any]:
    kind = cell[0]
    if kind == "date":
        value = cell[1]
        return ["date", value.isoformat()[:10] if hasattr(value, "isoformat") else str(value)[:10]]
    if kind == "formula":
        expression = str(cell[1])
        if expression.startswith("="):
            expression = expression[1:]
        return ["formula", expression, float(cell[2])]
    if kind == "num":
        number = cell[1]
        if isinstance(number, int) and not isinstance(number, bool):
            return ["num", number]
        return ["num", float(number)]
    return ["str", str(cell[1])]


def _sheet_json(sheet: Any) -> dict[str, Any]:
    return {
        "name": str(sheet.name),
        "header": [str(text) for text in sheet.header],
        "rows": [[_cell_json(cell) for cell in row] for row in sheet.rows],
        "freeze": bool(sheet.freeze),
        "col_widths": [float(width) for width in sheet.col_widths],
    }


def write_workbook(sheets: list[Any]) -> bytes:
    """Render normalized sheets with the native writer; raises NativeUnavailable if absent.

    A present-but-broken extension is a real error, not a silent fallback: falling back for
    every exception would hide divergence from the reference writer. The optional build is
    guarded by parity tests and by the unchanged independent openpyxl gate downstream.
    """
    module = _load()
    if module is None:
        raise NativeUnavailable("the optional native XLSX writer is not built for this installation")
    from . import DocumentGenerationError
    payload = json.dumps({"sheets": [_sheet_json(sheet) for sheet in sheets]},
                         separators=(",", ":"), ensure_ascii=False)
    try:
        data = module.write_workbook(payload)
    except ValueError as error:
        raise DocumentGenerationError(str(error)) from None
    raw = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
    if not raw.startswith(b"PK"):
        raise DocumentGenerationError("the native XLSX writer returned data that is not an xlsx archive")
    return raw


def _reset_loader() -> None:
    """For tests: forget a loaded module so availability can be re-probed."""
    global _LOADED, _LOAD_ATTEMPTED
    _LOADED = None
    _LOAD_ATTEMPTED = False
    sys.modules.pop(MODULE_NAME, None)
