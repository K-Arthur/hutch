"""Document generation (optional): xlsx render+validate at 500 / 5000 rows.

Calls the public hutch.documents.docgen.generate("xlsx", spec) path, which renders the workbook
and then parses it back to verify every declared value before returning bytes. Times the whole
gate, not just the ZIP writer.
"""

from __future__ import annotations

import statistics
import time

SAMPLES_FULL = 25   # render+parse-back is expensive; p95(n=25) labelled in the report
SAMPLES_QUICK = 3


def _spec(rows: int) -> dict:
    header = ["week", "region", "units", "revenue"]
    body = [[f"2026-W{index % 52:02d}", f"region-{index % 12}", index % 500, round(index * 1.75, 2)]
            for index in range(rows)]
    return {"sheets": [{"name": "Weekly", "header": header, "rows": body}]}


def run(quick: bool, state) -> list[dict]:
    from hutch.documents.docgen import generate

    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    sizes = [500] if quick else [500, 5000]
    cases: list[dict] = []
    for size in sizes:
        spec = _spec(size)
        generated = generate("xlsx", spec)
        if not generated.data or generated.validation_state not in {"passed", "passed_with_warnings"}:
            raise RuntimeError(f"xlsx generation gate failed at {size} rows: {generated.validation_state}")
        samples = []
        for _ in range(n):
            started = time.perf_counter()
            result = generate("xlsx", spec)
            samples.append((time.perf_counter() - started) * 1000.0)
            if not result.data:
                raise RuntimeError(f"xlsx generation returned no bytes at {size} rows")
        cases.append({
            "name": f"documents.xlsx_{size}rows_ms", "unit": "ms", "samples": samples, "better": "lower",
            "note": f"{size:,} rows; {len(generated.data) / 1024:.0f} KiB; validation={generated.validation_state}",
            "detail": {"rows": size, "bytes": len(generated.data),
                       "ms_per_1000_rows": statistics.median(samples) / size * 1000},
        })
    return cases
