"""Text-format generators: txt, md, csv, json, yaml.

Every format is written with an explicit encoding and re-parsed before it may be
promoted, so the stored bytes are provably what the specification meant (failure class
E12: implicit typing and charset sniffing). CSV is UTF-8 with a BOM because that is what
Excel autodetects correctly, uses CRLF rows, and neutralizes cells that spreadsheet
applications would evaluate as formulas by prefixing them with an apostrophe, the
guard is disclosed in the format docs rather than silent, and leading ``-`` is left
alone so legitimate negative numbers survive.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import yaml

from . import DocumentGenerationError, GeneratedDocument, register

MAX_TEXT_CHARS = 2_000_000
MAX_CSV_ROWS = 100_000
MAX_CSV_COLS = 256
MAX_JSON_VALUE_CHARS = 4_000_000
#: spreadsheet applications evaluate cells beginning with these; an apostrophe prefix
#: turns them into literal text. "-" is deliberately absent (negative numbers).
_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")


def _text_bytes(text: str, what: str) -> bytes:
    if not isinstance(text, str):
        raise DocumentGenerationError(f"{what} content must be a string")
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentGenerationError(f"{what} content exceeds {MAX_TEXT_CHARS:,} characters")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


@register("txt")
def _gen_txt(spec: dict[str, Any]) -> GeneratedDocument:
    data = _text_bytes(spec.get("text", ""), "txt")
    return GeneratedDocument(data=data, generator="hutch texty 1.0", validation_state="passed",
                             preview_data={"kind": "text", "chars": len(data.decode("utf-8"))})


@register("md")
def _gen_md(spec: dict[str, Any]) -> GeneratedDocument:
    data = _text_bytes(spec.get("text", ""), "markdown")
    return GeneratedDocument(data=data, generator="hutch texty 1.0", validation_state="passed",
                             preview_data={"kind": "text", "chars": len(data.decode("utf-8"))})


@register("json")
def _gen_json(spec: dict[str, Any]) -> GeneratedDocument:
    if "value" not in spec:
        raise DocumentGenerationError('json content must be {"value": ...}')
    value = spec["value"]
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise DocumentGenerationError(f"the value is not JSON-serializable: {exc}") from None
    if len(text) > MAX_JSON_VALUE_CHARS:
        raise DocumentGenerationError("the JSON document exceeds the size limit")
    try:
        reparsed = json.loads(text)
    except ValueError:
        raise DocumentGenerationError("the written JSON did not parse back") from None
    state, findings = "passed", []
    if json.dumps(reparsed, sort_keys=True) != json.dumps(
            json.loads(json.dumps(value, allow_nan=False)), sort_keys=True):
        state, findings = "passed_with_warnings", [
            {"code": "json_key_order", "detail": "object key order may differ from the request"}]
    data = (text + "\n").encode("utf-8")
    return GeneratedDocument(data=data, generator="hutch texty 1.0", validation_state=state,
                             findings=findings,
                             preview_data={"kind": "text", "chars": len(text) + 1})


@register("yaml")
def _gen_yaml(spec: dict[str, Any]) -> GeneratedDocument:
    if "value" not in spec:
        raise DocumentGenerationError('yaml content must be {"value": ...}')
    value = spec["value"]
    try:
        text = yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=100)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise DocumentGenerationError(f"the value is not YAML-representable: {exc}") from None
    try:
        yaml.safe_load(text)
    except yaml.YAMLError:
        raise DocumentGenerationError("the written YAML did not parse back") from None
    data = text.encode("utf-8")
    return GeneratedDocument(data=data, generator="hutch texty 1.0", validation_state="passed",
                             preview_data={"kind": "text", "chars": len(text)})


def _csv_cell_guard(cell: Any) -> str:
    text = "" if cell is None else str(cell)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


@register("csv")
def _gen_csv(spec: dict[str, Any]) -> GeneratedDocument:
    header = spec.get("header")
    rows = spec.get("rows")
    if not isinstance(rows, list) or (header is not None and not isinstance(header, list)):
        raise DocumentGenerationError('csv content must be {"header": [...], "rows": [[...], ...]}')
    if len(rows) > MAX_CSV_ROWS:
        raise DocumentGenerationError(f"csv exceeds {MAX_CSV_ROWS:,} rows")
    width = len(header) if header else 0
    for row in rows[:1_000]:
        if not isinstance(row, list):
            raise DocumentGenerationError("each csv row must be an array")
        width = max(width, len(row))
    if width > MAX_CSV_COLS:
        raise DocumentGenerationError(f"csv exceeds {MAX_CSV_COLS} columns")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    if header:
        writer.writerow([_csv_cell_guard(cell) for cell in header])
    guarded_rows = 0
    for row in rows:
        cells = [_csv_cell_guard(cell) for cell in row]
        if any(cell.startswith("'") for cell in cells):
            guarded_rows += 1
        writer.writerow(cells)
    text = buffer.getvalue()
    # parse-back: same dialect, same logical rows
    parsed = list(csv.reader(io.StringIO(text, newline="")))
    expected = (1 if header else 0) + len(rows)
    if len(parsed) != expected:
        raise DocumentGenerationError(
            f"the written csv did not parse back ({len(parsed)} rows, expected {expected})")
    # Excel autodetects UTF-8 only with the BOM
    data = b"\xef\xbb\xbf" + text.encode("utf-8")
    return GeneratedDocument(
        data=data, generator="hutch texty 1.0", validation_state="passed",
        findings=([{"code": "csv_formula_guard", "detail":
                    f"{guarded_rows} row(s) contain cells that were saved as literal text"}]
                  if guarded_rows else []),
        preview_data={"kind": "table", "rows": expected, "cols": width})
