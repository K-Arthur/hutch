"""Small statistics helpers used by the harness analysis (no dependencies)."""

from __future__ import annotations




def _clean(values) -> list:
    return [float(value) for value in values if value is not None]


def median(values):
    data = _clean(values)
    if not data:
        return None
    ordered = sorted(data)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def percentile(values, fraction: float):
    data = sorted(_clean(values))
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    position = (len(data) - 1) * (fraction / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(data) - 1)
    weight = position - lower
    return data[lower] * (1.0 - weight) + data[upper] * weight


def stats(values) -> dict:
    data = _clean(values)
    if not data:
        return {"n": 0, "median": None, "p95": None, "min": None, "max": None,
                "mean": None, "stdev": None, "cv": None}
    mean = sum(data) / len(data)
    variance = sum((value - mean) ** 2 for value in data) / len(data) if len(data) > 1 else 0.0
    stdev = variance ** 0.5
    return {"n": len(data), "median": round(median(data), 4), "p95": round(percentile(data, 95), 4),
            "min": round(min(data), 4), "max": round(max(data), 4), "mean": round(mean, 4),
            "stdev": round(stdev, 4), "cv": round(stdev / mean, 4) if mean else None}


def _summarize_metrics(records: list, keys) -> dict:
    summary = {}
    for key in keys:
        summary[key] = stats([record["metrics"].get(key) for record in records])
    return summary
