"""Deterministic transforms available to a plan.

These are the only non-model, non-tool operations a plan can perform, and every one is
pure: no I/O, no clock, no randomness, no ``eval``. They are the "deterministic executor"
half of the role split - a small, reviewable set that a plan composes into real work.

Failure is always explicit. A malformed CSV row, an unparseable JSON body, a missing
field or an unknown operation raises :class:`ValueError` with a precise message, which the
interpreter records as that node's failure. Nothing is coerced, dropped or defaulted.
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
from typing import Any

from .expr import EvalError, compare_values, typed_eq

MAX_ITEMS = 20_000
MAX_TEXT = 4 * 1024 * 1024
MAX_ROWS = 20_000

#: The one op table: the compiler imports it to validate arguments, and :func:`apply_op`
#: dispatches on it. Adding an op in one place cannot leave the other stale.
TRANSFORM_OPS: dict[str, set[str]] = {
    "constant": {"value"},
    "parse_json": {"text"},
    "to_json": {"value"},
    "parse_csv": {"text", "delimiter", "max_rows"},
    "parse_table": {"text", "delimiter", "max_rows"},
    "select": {"items", "fields"},
    "filter": {"items", "where"},
    "sort": {"items", "by", "descending"},
    "dedupe": {"items", "by"},
    "first": {"items", "count"},
    "last": {"items", "count"},
    "slice": {"items", "start", "end"},
    "count": {"items"},
    "sum": {"items", "of"},
    "total": {"items", "of"},
    "to_number": {"value"},
    "group_count": {"items", "by"},
    "bar_chart_svg": {"values", "title"},
    "join_text": {"items", "separator", "of"},
    "merge": {"values"},
    "to_markdown_table": {"items", "fields"},
    "pluck": {"value", "path"},
}

#: Comparison operators a ``filter`` predicate may use (the same vocabulary conditions use).
_FILTER_OPS = {"eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "contains", "matches",
               "exists", "is_null", "is_empty", "not_empty"}


def apply_op(op: str, args: dict[str, Any]) -> Any:
    if op not in TRANSFORM_OPS:
        raise ValueError(f"unknown transform op {op!r}")
    handler = globals()["_op_" + op]
    return handler(args)


# --------------------------------------------------------------------- helpers

def _require(args: dict[str, Any], name: str, kinds: tuple[type, ...]) -> Any:
    if name not in args:
        raise ValueError(f"missing argument {name!r}")
    value = args[name]
    if not isinstance(value, kinds) or isinstance(value, bool) and bool not in kinds:
        expected = "/".join(kind.__name__ for kind in kinds)
        raise ValueError(f"argument {name!r} must be {expected}, got {type(value).__name__}")
    return value


def _items(args: dict[str, Any], name: str = "items") -> list[Any]:
    value = _require(args, name, (list,))
    if len(value) > MAX_ITEMS:
        raise ValueError(f"{name!r} has {len(value)} entries, over the {MAX_ITEMS} limit")
    return value


def _pluck(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(f"path {path!r} is missing the key {part!r}")
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            index = int(part)
            if not -len(current) <= index < len(current):
                raise ValueError(f"path {path!r} indexes outside the list")
            current = current[index]
        else:
            raise ValueError(f"path {path!r} cannot be followed through {type(current).__name__}")
    return current


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"expected text, got {type(value).__name__}")


def _compare(left: Any, op: str, right: Any, field: str) -> bool:
    """A filter predicate uses the same comparison rules a ``when``/``until`` condition does."""
    if op not in _FILTER_OPS:
        raise ValueError(f"unknown filter op {op!r}")
    if op == "exists":
        return left is not _MISSING
    if op == "is_null":
        return left is None
    if op == "is_empty":
        return left is _MISSING or left is None or left == "" or left == [] or left == {}
    if op == "not_empty":
        return not (left is _MISSING or left is None or left == "" or left == [] or left == {})
    if left is _MISSING:
        raise ValueError(f"filter field {field!r} does not exist on this item")
    if op == "eq":
        return typed_eq(left, right)
    if op == "ne":
        return not typed_eq(left, right)
    try:
        return compare_values(left, op, right, f"filter field {field!r}")
    except EvalError as exc:
        raise ValueError(str(exc)) from None


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()


# ------------------------------------------------------------------ operations

def _op_constant(args: dict[str, Any]) -> Any:
    return args.get("value")


def _op_parse_json(args: dict[str, Any]) -> Any:
    text = _text(_require(args, "text", (str,)))
    if len(text) > MAX_TEXT:
        raise ValueError("the JSON text is too large")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the text is not valid JSON: {exc.msg} at line {exc.lineno}") from None


def _op_to_json(args: dict[str, Any]) -> str:
    if "value" not in args:
        raise ValueError("missing argument 'value'")
    return json.dumps(args["value"], ensure_ascii=False, indent=2, default=str)


def _op_parse_csv(args: dict[str, Any]) -> list[dict[str, str]]:
    text = _text(_require(args, "text", (str,)))
    if len(text) > MAX_TEXT:
        raise ValueError("the CSV text is too large")
    delimiter = args.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter must be a single character")
    limit = min(int(args.get("max_rows", 5_000) or 5_000), MAX_ROWS)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for index, row in enumerate(reader):
        if index == 0:
            header = [cell.strip() for cell in row]
            if not header or any(not name for name in header):
                raise ValueError("the CSV header is empty or has an empty column name")
            if len(set(header)) != len(header):
                raise ValueError("the CSV header has duplicate column names")
            continue
        if index > limit:
            raise ValueError(f"the CSV has more than {limit} data rows; raise max_rows deliberately")
        if not row:
            continue
        if len(row) != len(header):
            raise ValueError(f"row {index + 1} has {len(row)} fields but the header has {len(header)}")
        rows.append({name: value for name, value in zip(header, row)})
    if header is None:
        raise ValueError("the CSV is empty")
    return rows


def _op_parse_table(args: dict[str, Any]) -> dict[str, Any]:
    """Parse a CSV that may be messy: keep good rows, report bad ones with line numbers.

    This is the "choose validation from what the data actually shows" primitive. Nothing is
    silently dropped: a ragged row, a duplicate column or an empty header is reported in
    ``bad_rows`` (bounded), and the caller decides what that means.
    """
    text = _text(_require(args, "text", (str,)))
    if len(text) > MAX_TEXT:
        raise ValueError("the CSV text is too large")
    delimiter = args.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter must be a single character")
    limit = min(int(args.get("max_rows", 5_000) or 5_000), MAX_ROWS)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    columns: list[str] = []
    rows: list[dict[str, str]] = []
    bad: list[dict[str, Any]] = []
    blank = 0
    for index, row in enumerate(reader):
        line = index + 1
        if index == 0:
            columns = [cell.strip() for cell in row]
            if not columns or any(not name for name in columns):
                raise ValueError("the CSV header is empty or has an empty column name")
            if len(set(columns)) != len(columns):
                raise ValueError("the CSV header has duplicate column names")
            continue
        if not row or all(not cell.strip() for cell in row):
            blank += 1
            continue
        if len(rows) >= limit:
            bad.append({"line": line, "reason": f"beyond the {limit}-row limit", "raw": ",".join(row)[:200]})
            continue
        if len(row) != len(columns):
            bad.append({"line": line,
                        "reason": f"{len(row)} fields but the header has {len(columns)}",
                        "raw": ",".join(row)[:200]})
            continue
        rows.append({name: value for name, value in zip(columns, row)})
    return {"columns": columns, "rows": rows, "bad_rows": bad, "kept": len(rows),
            "bad": len(bad), "blank_lines": blank, "total": len(rows) + len(bad),
            "clean": not bad}


def _op_select(args: dict[str, Any]) -> list[dict[str, Any]]:
    items = _items(args)
    fields = _require(args, "fields", (list,))
    if not fields or any(not isinstance(field, str) or not field for field in fields):
        raise ValueError("fields must be a non-empty list of names")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("select needs object items")
        out.append({field: _pluck(item, field) for field in fields if _has(item, field)})
    return out


def _has(item: dict[str, Any], path: str) -> bool:
    current: Any = item
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit() and -len(current) <= int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def _op_filter(args: dict[str, Any]) -> list[Any]:
    items = _items(args)
    where = args.get("where")
    if not isinstance(where, list) or not where:
        raise ValueError("filter needs a non-empty 'where' list")
    out = []
    for item in items:
        keep = True
        for predicate in where:
            if not isinstance(predicate, dict):
                raise ValueError("each filter predicate must be an object")
            field = predicate.get("field", "")
            op = predicate.get("op", "")
            if not isinstance(field, str) or not field:
                raise ValueError("each filter predicate needs a field name")
            if not isinstance(op, str) or op not in _FILTER_OPS:
                raise ValueError(f"unknown filter op {op!r}")
            left = _pluck(item, field) if _has(item, field) else _MISSING
            if not _compare(left, op, predicate.get("value"), field):
                keep = False
                break
        if keep:
            out.append(item)
    return out


def _op_sort(args: dict[str, Any]) -> list[Any]:
    items = _items(args)
    by = _require(args, "by", (str,))
    descending = bool(args.get("descending", False))
    missing = [item for item in items if not (isinstance(item, dict) and _has(item, by))]
    if missing:
        raise ValueError(f"sort field {by!r} is missing on {len(missing)} item(s)")

    def key(item: Any) -> tuple[int, Any]:
        value = _pluck(item, by)
        if isinstance(value, bool):
            raise ValueError(f"sort field {by!r} is boolean")
        if isinstance(value, (int, float)):
            return (0, value)
        if isinstance(value, str):
            return (1, value)
        raise ValueError(f"sort field {by!r} must be a number or text")

    return sorted(items, key=key, reverse=descending)


def _op_dedupe(args: dict[str, Any]) -> list[Any]:
    items = _items(args)
    by = args.get("by", "")
    if by and not isinstance(by, str):
        raise ValueError("'by' must be a field name")
    seen: set[str] = set()
    out = []
    for item in items:
        value = _pluck(item, by) if by else item
        token = json.dumps(value, sort_keys=True, default=str)
        if token in seen:
            continue
        seen.add(token)
        out.append(item)
    return out


def _op_first(args: dict[str, Any]) -> list[Any]:
    count = int(args.get("count", 1) or 1)
    if count < 1:
        raise ValueError("count must be at least 1")
    return _items(args)[:count]


def _op_last(args: dict[str, Any]) -> list[Any]:
    count = int(args.get("count", 1) or 1)
    if count < 1:
        raise ValueError("count must be at least 1")
    return _items(args)[-count:]


def _op_slice(args: dict[str, Any]) -> list[Any]:
    items = _items(args)
    start = int(args.get("start", 0) or 0)
    end = args.get("end")
    if end is None:
        return items[start:]
    return items[start:int(end)]


def _op_count(args: dict[str, Any]) -> int:
    return len(_items(args))


def _op_sum(args: dict[str, Any]) -> float:
    items = _items(args)
    of = args.get("of", "")
    total = 0.0
    for item in items:
        value = _pluck(item, of) if of else item
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("sum needs numbers")
        total += float(value)
    return total


def _op_to_number(args: dict[str, Any]) -> float:
    """One strict numeric conversion: a number, or a decimal string that is nothing else."""
    if "value" not in args:
        raise ValueError("missing argument 'value'")
    value = args["value"]
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number here")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        digits = text.lstrip("+-")
        if text and digits.count(".") <= 1 and digits.replace(".", "", 1).isdigit() and digits:
            return float(text)
        raise ValueError(f"{value!r} is not a decimal number")
    raise ValueError(f"cannot read a number from {type(value).__name__}")


def _op_total(args: dict[str, Any]) -> float:
    """Sum a column that may hold decimal strings (CSV values are text), failing on junk."""
    items = _items(args)
    of = args.get("of", "")
    total = 0.0
    for item in items:
        value = _pluck(item, of) if of else item
        total += _op_to_number({"value": value})
    return total


def _op_group_count(args: dict[str, Any]) -> dict[str, int]:
    items = _items(args)
    by = _require(args, "by", (str,))
    counts: dict[str, int] = {}
    for item in items:
        value = _pluck(item, by)
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise ValueError(f"group field {by!r} must be a string or number")
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _op_bar_chart_svg(args: dict[str, Any]) -> str:
    """Render a small, deterministic, self-contained horizontal bar chart.

    The operation accepts the mapping produced by ``group_count``. It rejects oversized
    or malformed input rather than silently omitting categories from an analysis artifact.
    Labels and titles are XML-escaped and the image has a text equivalent for assistive
    technology and artifact inspection.
    """
    values = _require(args, "values", (dict,))
    if len(values) > 20:
        raise ValueError("bar_chart_svg supports at most 20 categories")
    title = args.get("title", "Counts by category")
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ValueError("bar_chart_svg title must be a non-empty string of at most 160 characters")

    entries: list[tuple[str, float]] = []
    for label, value in values.items():
        if not isinstance(label, str) or not label or len(label) > 80:
            raise ValueError("bar_chart_svg category labels must be non-empty strings of at most 80 characters")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"bar_chart_svg value for {label!r} must be a finite nonnegative number")
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise ValueError(f"bar_chart_svg value for {label!r} must be a finite nonnegative number") from None
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"bar_chart_svg value for {label!r} must be a finite nonnegative number")
        entries.append((label, number))
    entries.sort(key=lambda pair: (-pair[1], pair[0]))

    safe_title = html.escape(title.strip(), quote=True)
    width, row_height, top = 720, 34, 68
    height = max(112, top + row_height * len(entries) + 16)
    maximum = max((value for _, value in entries), default=0.0)
    description = "; ".join(f"{label}: {value:g}" for label, value in entries)
    if not description:
        description = "No categories are available."
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 720 {height}" role="img" aria-labelledby="chart-title chart-description">',
        f'<title id="chart-title">{safe_title}</title>',
        f'<desc id="chart-description">{html.escape(description, quote=True)}</desc>',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="16" y="32" fill="#17211f" font-family="sans-serif" font-size="18" font-weight="700">{safe_title}</text>',
    ]
    if not entries:
        lines.append('<text x="16" y="76" fill="#53625d" font-family="sans-serif" font-size="14">No categories are available.</text>')
    for index, (label, value) in enumerate(entries):
        y = top + index * row_height
        bar_width = round(380 * (value / maximum)) if maximum else 0
        label_text = html.escape(label, quote=True)
        label_width = min(228, max(24, len(label) * 7))
        value_text = f"{value:g}"
        lines.extend([
            f'<text x="16" y="{y + 13}" textLength="{label_width}" lengthAdjust="spacingAndGlyphs" '
            f'fill="#263632" font-family="sans-serif" font-size="13">{label_text}</text>',
            f'<rect x="260" y="{y}" width="{bar_width}" height="19" rx="4" fill="#287d68"/>',
            f'<text x="{min(650, 270 + bar_width)}" y="{y + 14}" fill="#17211f" '
            f'font-family="sans-serif" font-size="13">{value_text}</text>',
        ])
    lines.append("</svg>")
    result = "\n".join(lines)
    if len(result) > MAX_TEXT:
        raise ValueError("the SVG chart is too large to publish")
    return result


def _op_join_text(args: dict[str, Any]) -> str:
    items = _items(args)
    separator = str(args.get("separator", "\n"))
    if len(separator) > 20:
        raise ValueError("separator is too long")
    of = args.get("of", "")
    parts = []
    for item in items:
        value = _pluck(item, of) if of else item
        if isinstance(value, str):
            parts.append(value)
        elif value is None or isinstance(value, (int, float, bool)):
            parts.append(json.dumps(value))
        else:
            parts.append(json.dumps(value, ensure_ascii=False, default=str))
    text = separator.join(parts)
    if len(text) > MAX_TEXT:
        raise ValueError("the joined text is too large; publish an artifact instead")
    return text


def _op_merge(args: dict[str, Any]) -> dict[str, Any]:
    values = _require(args, "values", (list,))
    out: dict[str, Any] = {}
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("merge needs object values")
        for key, item in value.items():
            if key in out:
                raise ValueError(f"merge would overwrite the key {key!r}; that is not silent here")
            out[key] = item
    return out


def _op_to_markdown_table(args: dict[str, Any]) -> str:
    items = _items(args)
    fields = args.get("fields")
    if not isinstance(fields, list) or not fields or any(not isinstance(f, str) or not f for f in fields):
        raise ValueError("to_markdown_table needs a non-empty 'fields' list")

    def cell(value: Any) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        return text.replace("|", "\\|").replace("\n", " ")[:200]

    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join("---" for _ in fields) + " |"]
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("to_markdown_table needs object items")
        lines.append("| " + " | ".join(cell(_pluck(item, f) if _has(item, f) else "") for f in fields) + " |")
    return "\n".join(lines)


def _op_pluck(args: dict[str, Any]) -> Any:
    if "value" not in args:
        raise ValueError("missing argument 'value'")
    path = args.get("path", "")
    if not isinstance(path, str):
        raise ValueError("'path' must be a string")
    return _pluck(args["value"], path)
