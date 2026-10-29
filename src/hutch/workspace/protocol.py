"""JSON-line protocol v1 between Hutch and the contained workspace kernel.

This is the containment story of the executable workspace, stated where it is
implemented rather than only in ``docs/safety.md``:

* The child (``python -m hutch.workspace.kernel``) never runs outside the same
  bubblewrap strict profile the shell tool uses: workspace-only writable
  directory, read-only ``/usr`` + venv, fresh ``/proc``, no network namespace,
  cgroup CPU/memory/task caps, and a cleared environment with a fixed
  allowlist (see ``manager.kernel_argv``). There is no uncontained fallback:
  if strict containment is unavailable the manager refuses, exactly as
  ``tools/shell.py`` fails closed.
* The protocol is the *only* channel between parent and child. User code's
  ``print()`` never touches it: the kernel captures ``sys.stdout``/``stderr``
  into bounded ring buffers and writes protocol lines through a saved file
  descriptor, so a chatty cell cannot corrupt the conversation between the
  processes (bounded output is a contract requirement, not a courtesy).
* Every response carries a receipt whose ``source_sha256`` is the hash of the
  EXACT submitted code and whose ``environment_generation`` binds the
  execution to one durable environment (schema v55 ``workspace_sessions``).
  That is what makes "which environment produced this output" queryable and
  stale outputs detectable instead of silently wrong (the silent
  code-interpreter state-loss class in
  ``docs/research/outputs-failures-2026-10-10.md`` A.7).
* Everything a cell may produce is hard-bounded here: stdout/stderr tails,
  ``result_repr``, table previews, produced-file listings. A cell that
  exceeds its output budget is terminated and reported honestly with status
  ``'timeout'``, never truncated silently.

Stdlib only: the data path (csv/json/statistics-class work) works with no
third-party packages installed in the child; ``pandas``/``matplotlib`` are
detected extras surfaced in the session's ``env_fingerprint``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

#: The protocol version this module speaks. A parent that reads a hello line
#: announcing another version refuses to start the session rather than guess.
PROTOCOL_VERSION = 1

#: Tails preserved on every receipt (contract: code_receipt.stdout_tail /
#: stderr_tail <= 4000).
STDOUT_TAIL_CHARS = 4_000
STDERR_TAIL_CHARS = 4_000

#: result_repr bound (contract: <= 2000).
RESULT_REPR_CHARS = 2_000

#: A trailing dict/list expression becomes a table payload preview of at most
#: this many rows (contract: table preview <= 500 rows).
TABLE_PREVIEW_ROWS = 500

#: Table width cap; a wider trailing value does not become a table.
MAX_TABLE_COLUMNS = 64

#: One table cell string bound (contract: cells are JSON scalars, strings
#: bounded so a row cannot smuggle a novel).
TABLE_CELL_CHARS = 2_000

#: Produced files reported per exec (contract: <= 32, each with name, sha256,
#: bytes).
MAX_PRODUCED_FILES = 32

#: Per-cell combined stdout+stderr budget. A cell that exceeds it is
#: terminated and reported with status 'timeout', tail preserved.
OUTPUT_BUDGET_CHARS = 200_000

#: Longest protocol line the parent will read from a child before declaring
#: the child hostile/lost (tails + a full valid block set stay far below this;
#: parse_blocks applies the real 256k block budget afterwards).
MAX_RESPONSE_LINE_CHARS = 4_000_000

#: How long interrupt() waits for the protocol ack (a receipt with status
#: 'interrupted') before marking the receipt 'interrupt_unconfirmed'.
INTERRUPT_ACK_SECONDS = 3.0

#: Files larger than this are never hashed for produced_files (a runaway
#: cell must not turn the parent into a hashing service); they are simply
#: left out of the bounded listing.
FILE_HASH_MAX_BYTES = 8 * 1024 * 1024

#: Workspace entries examined when looking for files a cell produced.
WORKSPACE_SCAN_CAP = 512

#: Margin added to the child-side deadline before the parent's watchdog
#: gives up on a response, terminates the child, and fabricates an honest
#: timeout receipt (the child normally reports first, preserving tails).
PARENT_RESPONSE_MARGIN_SECONDS = 4.0

_STATUSES = ("ok", "error", "busy", "unknown_id")
_RECEIPT_STATUSES = ("ok", "error", "timeout", "interrupted", "interrupt_unconfirmed")


def encode_message(message: dict[str, Any]) -> str:
    """One compact JSON line (newline-terminated)."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode_message(line: str) -> dict[str, Any]:
    """Parse one protocol line. Raises ValueError on anything but a JSON object."""
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("protocol message is not a JSON object")
    return message


def truncate(text: str, limit: int) -> str:
    """Bound a string to ``limit`` chars, disclosing the omission honestly."""
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    marker = f"… [+{omitted} chars omitted]"
    return text[: max(0, limit - len(marker))] + marker


def new_request_id() -> str:
    """A caller-side request id ('wx_' + 16 lowercase hex)."""
    return "wx_" + os.urandom(8).hex()


def redact_path(path: str, workspace: Path | str) -> str:
    """Frame paths outside the workspace become ``<redacted>``.

    The workspace path itself (and synthetic names like ``<cell>``) stay
    readable: the submitted source is already shown in the code_receipt.
    """
    text = str(path)
    if not text.startswith("/"):
        return text
    try:
        inside = Path(text).resolve().is_relative_to(Path(workspace).resolve())
    except (OSError, ValueError):
        inside = False
    return text if inside else "<redacted>"


def redacted_traceback(exc: BaseException, workspace: Path | str) -> list[str]:
    """Traceback frames as strings, with out-of-workspace paths redacted.

    Local variables are NEVER included, an error receipt must not become a
    side channel onto the cell's memory. The final exception line is the last
    frame; everything above it is the frame list.
    """
    import traceback

    frames: list[str] = []
    stack = traceback.extract_tb(exc.__traceback__)
    for entry in stack:
        location = redact_path(entry.filename, workspace)
        frames.append(f'File "{location}", line {entry.lineno}, in {entry.name}')
        if entry.line:
            frames.append(f"    {entry.line.strip()}")
    frames.append(f"{type(exc).__name__}: {exc}")
    return frames


def _scalar_ok(value: Any) -> bool:
    """True for None/bool/int/finite-float/str, the only table cells."""
    if value is None or isinstance(value, (bool, str, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False
    if value is None or isinstance(value, (bool, str)):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _cell(value: Any) -> Any:
    """Coerce one candidate cell into a JSON scalar, stringifying the rest."""
    if _scalar_ok(value):
        return value
    return truncate(repr(value), TABLE_CELL_CHARS)


def _dtype(values: list[Any]) -> str:
    seen = [v for v in values if v is not None]
    if seen and all(isinstance(v, bool) for v in seen):
        return "boolean"
    if seen and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in seen):
        return "number"
    if seen and all(isinstance(v, str) for v in seen):
        return "text"
    return "unknown"


def table_preview_from_value(value: Any) -> dict[str, Any] | None:
    """A trailing dict/list of scalars becomes a bounded table payload.

    Accepts: a dict with scalar values (key/value preview), a list of scalars
    (one column), or a list of flat dicts with scalar values (tabular, columns
    from the first row). Returns None (no preview) for anything else, for more
    than :data:`MAX_TABLE_COLUMNS` columns, or for non-finite floats anywhere
    in the first preview window. ``row_total`` is always the true total and a
    truncation entry discloses every omitted row.
    """
    rows: list[list[Any]]
    columns: list[dict[str, str]]

    def finish(columns: list[dict[str, str]], rows: list[list[Any]], total: int) -> dict[str, Any]:
        preview = rows[:TABLE_PREVIEW_ROWS]
        payload: dict[str, Any] = {
            "columns": columns,
            "rows": preview,
            "row_total": total,
        }
        if total > len(preview):
            payload["truncation"] = {
                "omitted_rows": total - len(preview),
                "reason": f"preview shows the first {len(preview)} of {total} rows",
            }
        return payload

    if isinstance(value, dict):
        pairs = list(value.items())
        if len(pairs) > TABLE_PREVIEW_ROWS or not all(_scalar_ok(v) for _, v in pairs[:TABLE_PREVIEW_ROWS]):
            return None
        columns = [{"name": "key", "dtype": "text"},
                   {"name": "value", "dtype": _dtype([v for _, v in pairs])}]
        rows = [[truncate(str(k), TABLE_CELL_CHARS), _cell(v)] for k, v in pairs]
        return finish(columns, rows, len(pairs))

    if isinstance(value, (list, tuple)):
        if all(_scalar_ok(item) for item in value[:TABLE_PREVIEW_ROWS]):
            columns = [{"name": "value", "dtype": _dtype(list(value))}]
            rows = [[_cell(item)] for item in value]
            return finish(columns, rows, len(value))
        if all(isinstance(item, dict) for item in value[:TABLE_PREVIEW_ROWS]) and value:
            first = value[0]
            if not first:
                return None
            names = list(first.keys())
            if len(names) > MAX_TABLE_COLUMNS:
                return None
            window = value[:TABLE_PREVIEW_ROWS]
            for item in window:
                if any(k not in item or not _scalar_ok(item[k]) for k in names):
                    return None
            columns = [{"name": truncate(str(name), 200), "dtype":
                        _dtype([item[name] for item in window])} for name in names]
            rows = [[_cell(item[name]) for name in names] for item in window]
            return finish(columns, rows, len(value))
    return None


def snapshot_workspace(workspace: Path) -> dict[str, tuple[int, int, int]]:
    """Bounded snapshot of the regular files directly under ``workspace``.

    Returns ``{relative name: (mtime_ns, size, inode)}``. Only the workspace's
    own entries are examined (never symlinked directories, never recursion
    into subdirectories a cell may have created to hide churn), capped at
    :data:`WORKSPACE_SCAN_CAP` entries.
    """
    listing: dict[str, tuple[int, int, int]] = {}
    try:
        with os.scandir(workspace) as entries:
            for count, entry in enumerate(entries):
                if count >= WORKSPACE_SCAN_CAP:
                    break
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                    listing[entry.name] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
                except OSError:
                    continue
    except OSError:
        pass
    return listing


def produced_files_between(before: dict[str, tuple[int, int, int]],
                           after: dict[str, tuple[int, int, int]],
                           workspace: Path) -> list[dict[str, Any]]:
    """Hash what a cell newly created or changed, bounded and honest.

    Only regular files directly under the workspace count. Files over
    :data:`FILE_HASH_MAX_BYTES` are excluded (never partially hashed, a
    prefix hash presented as a file digest would be a lie). Newest first,
    capped at :data:`MAX_PRODUCED_FILES`.
    """
    changed = [name for name, marker in after.items() if before.get(name) != marker]
    def sort_key(name: str) -> tuple[int, str]:
        mtime = after[name][0]
        return (mtime, name)
    changed.sort(key=sort_key, reverse=True)
    out: list[dict[str, Any]] = []
    for name in changed:
        if len(out) >= MAX_PRODUCED_FILES:
            break
        path = workspace / name
        try:
            size = path.stat().st_size
            if size > FILE_HASH_MAX_BYTES:
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            continue
        out.append({"name": name, "sha256": digest.hexdigest(), "bytes": size})
    return out


def fabricate_receipt(*, ordinal: int, generation: int, started_at: str, finished_at: str,
                      status: str, source_sha256: str, note: str) -> dict[str, Any]:
    """An honest receipt for an execution whose outcome the child never reported.

    The parent does not know what the cell printed or returned before it
    died, so the counters are zero and the loss is stated in the receipt's
    ``note``, never silently claimed. Used for ``timeout`` (terminated past
    every deadline), ``interrupt_unconfirmed`` (no ack to the SIGINT) and
    ``error`` (the kernel died mid-execution).
    """
    if status not in ("timeout", "interrupt_unconfirmed", "error"):
        raise ValueError("fabricated receipts only cover timeout/interrupt_unconfirmed/error")
    return {
        "ordinal": max(1, int(ordinal)),
        "environment_generation": max(1, int(generation)),
        "started_at": started_at,
        "finished_at": finished_at,
        "source_sha256": source_sha256,
        "status": status,
        "stdout_chars_total": 0,
        "stderr_chars_total": 0,
        "note": note,
    }


def sha256_of_source(code: str) -> str:
    """The receipt's display-source-of-truth binding: sha256 of the EXACT
    submitted code (open-webui #14823: what is displayed can never drift
    from what actually ran)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
