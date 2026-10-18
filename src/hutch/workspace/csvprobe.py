"""Bounded, honest CSV/TSV inspection — what a person would want to know before
trusting a file, computed from the bytes without executing anything.

``probe_csv_path`` answers the questions the typed-outputs plan (S2) demands be
disclosed rather than silently decided: encoding and BOM, delimiter, whether a
header row is present (a heuristic, labeled as such), duplicate column names,
rows whose field count disagrees with the file's own majority (malformed rows,
with the first few line numbers — never silently dropped), empty/null-token
tallies per column, columns that look like leading-zero identifiers or
timezone-bearing timestamps, and records that contain quoted newlines (why
"line count" and "record count" disagree). Everything is computed from a
bounded sample and the truncation is disclosed in the result.

This module is deliberately importable both server-side (the upload report
route) and inside the contained workspace kernel (the same venv and source are
bound read-only into the sandbox), so the model's in-kernel ``inspect_csv``
helper and the UI's upload report cannot disagree.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

#: How many bytes are decoded and parsed for the probe. The scan never reads
#: beyond this, and ``truncated_sample`` says so when the file is larger.
SAMPLE_BYTES = 1_048_576

#: Physical rows parsed at most, as a second bound independent of bytes.
MAX_ROWS_SCANNED = 20_000

#: Columns described individually, at most; further columns are counted under
#: ``columns_omitted`` rather than silently widened.
MAX_COLUMNS_DESCRIBED = 64

#: Tokens that commonly stand for "no value". The probe only *counts* them;
#: deciding that they mean null is the reader's call and is disclosed per column.
NULL_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-"}

_LEADING_ZERO_RE = re.compile(r"^0[0-9]+$")
_TZ_LIKE_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def _decode(raw: bytes) -> tuple[str, str, str]:
    """Return (text, encoding, note). BOM wins; strict UTF-8 next; Latin-1 last,
    disclosed, so a probe never refuses a file for its encoding."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "utf-8-sig", ""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), "utf-16", ""
    try:
        return raw.decode("utf-8"), "utf-8", ""
    except UnicodeDecodeError:
        return (raw.decode("latin-1"), "latin-1",
                "non-UTF-8 bytes; the preview decodes as Latin-1 and may misrender some text")


def _sniff_delimiter(text: str) -> tuple[str, str]:
    """Return (delimiter, note). ``csv.Sniffer`` is a heuristic; when it cannot
    decide the file is parsed as comma-separated and the fallback is disclosed."""
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter, ""
    except csv.Error:
        return ",", "delimiter not confidently detected; parsed as comma-separated"


def _row_has_number(row: list[str]) -> bool:
    for cell in row:
        try:
            float(cell.replace(",", ""))
            return True
        except ValueError:
            continue
    return False


def _looks_like_header(first: list[str], data_sample: list[list[str]]) -> tuple[bool | None, str]:
    """A labeled heuristic, not a fact. Rules, in order: a numeric first row is
    data; a non-numeric first row above rows with numbers is a header; a distinct,
    non-empty first row whose values never repeat in their columns reads as a
    header; anything else is disclosed as ambiguous rather than guessed."""
    if not first:
        return None, "file has no rows"
    if not data_sample:
        return None, "only one row; header presence cannot be inferred"
    if _row_has_number(first):
        return False, "first row already contains numbers; treated as data, not a header"
    if any(_row_has_number(row) for row in data_sample):
        return True, ""
    if any(cell.strip() == "" for cell in first):
        return None, "first row has blank cells; header presence is ambiguous"
    if len(set(first)) != len(first):
        return None, "first row repeats values and no numbers distinguish it; header presence is ambiguous"
    for row in data_sample[:50]:
        for i, cell in enumerate(first):
            if i < len(row) and row[i] == cell:
                return None, (f"a data row repeats the first row's value {cell!r}; "
                              "header presence is ambiguous")
    return True, ""


def probe_csv_text(text: str, *, max_rows: int = MAX_ROWS_SCANNED) -> dict[str, Any]:
    """Parse the decoded sample and return the disclosure dict. Malformed content
    is reported, never raised: the probe's job is to describe the file as it is."""
    delimiter, delimiter_note = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    first: list[str] | None = None
    data_sample: list[list[str]] = []
    rows_scanned = 0
    widths: list[int] = []
    row_lines: list[int] = []
    per_col: list[dict[str, int]] = []
    quoted_newline_records = 0
    prev_line = 0
    parser_note = ""
    try:
        for record in reader:
            if rows_scanned >= max_rows:
                break
            rows_scanned += 1
            if reader.line_num > prev_line + 1:
                quoted_newline_records += 1
            prev_line = reader.line_num
            if first is None:
                first = record
                continue
            if len(data_sample) < 50:
                data_sample.append(record)
            widths.append(len(record))
            row_lines.append(reader.line_num)
            if len(per_col) < len(record):
                per_col.extend({"empty": 0, "null_tokens": 0, "leading_zeros": 0, "tz_like": 0}
                               for _ in range(len(record) - len(per_col)))
            for i, cell in enumerate(record[:MAX_COLUMNS_DESCRIBED]):
                stats = per_col[i]
                if cell == "":
                    stats["empty"] += 1
                if cell.strip().lower() in NULL_TOKENS and cell.strip() != "":
                    stats["null_tokens"] += 1
                if _LEADING_ZERO_RE.match(cell):
                    stats["leading_zeros"] += 1
                if _TZ_LIKE_RE.match(cell.strip()):
                    stats["tz_like"] += 1
    except csv.Error:
        parser_note = "CSV parser stopped at a field that exceeds Python's configured field-size limit"
    # Malformed rows are decided against the file's own majority width, computed
    # after the scan — an online "majority" would mislabel rows while the scan
    # is still undecided (a 4-wide row early in a 3-wide file looks fine).
    counts: dict[int, int] = {}
    for width in widths:
        counts[width] = counts.get(width, 0) + 1
    expected = max(counts, key=lambda w: (counts[w], w)) if counts else 0
    malformed_count = 0
    malformed_lines: list[int] = []
    for width, line in zip(widths, row_lines):
        if width != expected:
            malformed_count += 1
            if len(malformed_lines) < 5:
                malformed_lines.append(line)
    header_present, header_note = _looks_like_header(first or [], data_sample)
    names: list[str] = []
    if first:
        names = [c.strip() for c in first[:MAX_COLUMNS_DESCRIBED]]
        if header_present is not True:
            names = [f"column_{i + 1}" for i in range(len(first[:MAX_COLUMNS_DESCRIBED]))]
    duplicates = sorted({n for n in names if names.count(n) > 1}) if names else []
    columns = [
        {
            "name": names[i] if i < len(names) else f"column_{i + 1}",
            **(per_col[i] if i < len(per_col) else {"empty": 0, "null_tokens": 0,
                                                    "leading_zeros": 0, "tz_like": 0}),
        }
        for i in range(min(MAX_COLUMNS_DESCRIBED, max(len(names), len(per_col))))
    ]
    notes = [n for n in (delimiter_note, header_note) if n]
    if parser_note:
        notes.append(parser_note)
    if rows_scanned >= max_rows:
        notes.append(f"scan stopped at {max_rows:,} rows; totals cover the scan only")
    return {
        "delimiter": delimiter,
        "header_present": header_present,
        "columns": columns,
        "duplicate_columns": duplicates,
        "rows_scanned": rows_scanned,
        "truncated_sample": rows_scanned >= max_rows,
        "expected_field_count": expected,
        "malformed_rows": {"count": malformed_count, "first_line_numbers": malformed_lines},
        "quoted_newline_records": quoted_newline_records,
        "notes": notes,
    }


def probe_csv_path(path: Path | str, *, sample_bytes: int = SAMPLE_BYTES) -> dict[str, Any]:
    """Probe a file on disk from a bounded byte sample. Returns the disclosure
    dict for delimited text; other uploads (JSON/Markdown/plain text) are the
    route's business — this function is for tabular text."""
    source = Path(path)
    sample_bytes = max(0, min(int(sample_bytes), SAMPLE_BYTES))
    with source.open("rb") as stream:
        raw = stream.read(sample_bytes)
    return probe_csv_bytes(raw, sample_bytes=sample_bytes, total_size=source.stat().st_size)


def probe_csv_bytes(data: bytes, *, sample_bytes: int = SAMPLE_BYTES,
                    total_size: int | None = None) -> dict[str, Any]:
    """Probe already-verified bytes, without reopening a mutable workspace path."""
    sample_bytes = max(0, min(int(sample_bytes), SAMPLE_BYTES))
    raw = data[:sample_bytes]
    truncated = len(raw) == sample_bytes and (len(data) if total_size is None else total_size) > sample_bytes
    text, encoding, note = _decode(raw)
    result = probe_csv_text(text)
    result["encoding"] = encoding
    result["truncated_sample"] = bool(result["truncated_sample"] or truncated)
    if note:
        result["notes"] = [note, *result["notes"]]
    return result
