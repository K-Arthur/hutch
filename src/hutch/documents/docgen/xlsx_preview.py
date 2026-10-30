"""Structure-preview helpers for the XLSX generator.

Kept in a separate module so the frozen ``xlsx.py`` generator stays within its
shrink-only line budget while the optional native writer is wired in.
"""

from __future__ import annotations

from typing import Any

PREVIEW_SAMPLE_ROWS = 8
PREVIEW_CELL_CHARS = 120


def preview_cell(cell: Any) -> str | int | float:
    if cell[0] == "str":
        text = cell[1]
        return text if len(text) <= PREVIEW_CELL_CHARS else text[:PREVIEW_CELL_CHARS] + "\u2026"
    if cell[0] == "num":
        return cell[1]
    if cell[0] == "date":
        return cell[1].isoformat()
    return cell[2]


def preview(sheets: list[Any]) -> dict[str, Any]:
    previews = []
    for sheet in sheets:
        sample: list[list[str | int | float]] = []
        if sheet.header:
            sample.append([preview_cell(("str", text)) for text in sheet.header])
        for row in sheet.rows[: PREVIEW_SAMPLE_ROWS - len(sample)]:
            sample.append([preview_cell(cell) for cell in row])
        previews.append({"name": sheet.name, "rows": len(sheet.rows), "cols": sheet.width,
                         "sample": sample})
    return {"kind": "grid", "sheets": previews}
