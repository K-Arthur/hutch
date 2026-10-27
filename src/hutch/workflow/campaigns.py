"""Pure, bounded campaign arithmetic. No model, network, credentials or writes.

Version 1 accepts one same-unit CSV export, not mixed currencies, attribution
windows or account summaries. Reporting days are an operator assertion, never
inferred from spend. Exact source bytes remain identifiable in the artifact.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any

SOURCE_FIELDS = ["campaign", "impressions", "clicks", "spend", "conversions", "revenue", "daily_budget"]
METRIC_FIELDS = ["campaign", "ctr", "cvr", "cpa", "roas", "alert"]
MAX_NUMBER = Decimal("1000000000000000")


def _number(value: str, field: str, campaign: str, *, maximum: Decimal = MAX_NUMBER) -> Decimal:
    # Fixed notation and a magnitude bound also prevent decimal exponent/CPU
    # bombs. Counts may include attributed fractional conversions, but not clicks.
    if len(value) > 40 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,6})?", value):
        raise ValueError(f"{campaign}: {field} must be a nonnegative fixed-point number (at most 6 decimals)")
    number = Decimal(value)
    if number > maximum:
        raise ValueError(f"{campaign}: {field} exceeds the supported bound")
    if field in {"impressions", "clicks"} and number != number.to_integral_value():
        raise ValueError(f"{campaign}: {field} must be a whole count")
    return number


def _ratio(numerator: Decimal, denominator: Decimal) -> str | None:
    if not denominator:
        return None
    value = (numerator / denominator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(value, "f").rstrip("0").rstrip(".") if value else "0"


def _metrics(values: dict[str, Decimal]) -> dict[str, str | None]:
    return {"ctr": _ratio(values["clicks"], values["impressions"]),
            "cvr": _ratio(values["conversions"], values["clicks"]),
            "cpa": _ratio(values["spend"], values["conversions"]),
            "roas": _ratio(values["revenue"], values["spend"])}


def _parse(text: str, fields: list[str]) -> list[dict[str, str]]:
    # Reuse the workflow parser's text/row/shape bounds, with strict quoting.
    from .ops import MAX_TEXT, _op_parse_csv
    if len(text) > MAX_TEXT:
        raise ValueError("the CSV text is too large")
    try:
        header = next(csv.reader(io.StringIO(text), strict=True))
        if [field.strip() for field in header] != fields:
            raise ValueError("CSV columns must be exactly " + ",".join(fields))
        # Validate quoting separately; the shared parser remains compatible.
        for _ in csv.reader(io.StringIO(text), strict=True):
            pass
        rows = _op_parse_csv({"text": text, "max_rows": 5_000})
    except (csv.Error, StopIteration):
        raise ValueError("the campaign CSV has invalid quoting or is empty") from None
    if not rows:
        raise ValueError("the campaign CSV must contain at least one campaign")
    names: set[str] = set()
    for row in rows:
        name = row["campaign"]
        if (not name.strip() or name != name.strip() or len(name) > 200
                or any(ord(char) < 32 or ord(char) == 127 for char in name)
                or name.startswith(("=", "+", "-", "@"))):
            raise ValueError("campaign names must be plain text, without spreadsheet formulas or control characters")
        if name in names:
            raise ValueError(f"duplicate campaign {name!r}; aggregate source rows deliberately first")
        names.add(name)
    return rows


def campaign_report(text: str, reporting_days: int = 0) -> dict[str, Any]:
    if type(reporting_days) is not int or not 0 <= reporting_days <= 3660:
        raise ValueError("reporting_days must be a whole number from 0 (unknown) to 3660")
    source = _parse(text, SOURCE_FIELDS)
    output = []
    totals = {field: Decimal(0) for field in SOURCE_FIELDS[1:]}
    with localcontext() as context:
        context.prec = 48
        for row in source:
            name = row["campaign"]
            values = {field: _number(row[field], field, name) for field in SOURCE_FIELDS[1:]}
            if values["clicks"] > values["impressions"]:
                raise ValueError(f"{name}: clicks exceed impressions; check the export's units and scope")
            alerts = []
            if values["conversions"] == 0:
                alerts.append("zero_conversions")
            if reporting_days and values["spend"] > values["daily_budget"] * reporting_days:
                alerts.append("over_budget")
            output.append({"campaign": name, **_metrics(values), "alert": ";".join(alerts)})
            for field, value in values.items():
                totals[field] += value
        total_metrics = _metrics(totals)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=METRIC_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(output)  # None is an empty cell, never numeric zero.
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    period = (f"Reporting period: {reporting_days} whole day(s), supplied by you. Budget checks assume "
              "each daily budget was constant throughout this same window."
              if reporting_days else "Reporting period is unknown. Daily-budget overspend and pacing cannot be verified.")
    markdown = ("# Campaign metrics draft\n\n" + period + "\n\n"
                "CTR = clicks / impressions; CVR = conversions / clicks; CPA = spend / conversions; "
                "ROAS = revenue / spend. Rates are fractions; metrics are rounded half up to four decimals. "
                "Empty cells are undefined, not zero. Totals use summed inputs, not averaged rates.\n\n"
                "Amounts use the source's reported units. Currency, attribution accuracy, refunds and full costs "
                "are not verified. ROAS is not a profit measure. Zero conversions is a review flag, not proof "
                "that a campaign should stop. Budget comparisons assume complete, matching reporting windows.\n\n"
                "Review flagged campaigns and confirm the reporting window before recommending changes. "
                "Any campaign or spend change requires your approval; this report changes no campaigns.\n\n"
                f"Source SHA-256: `{source_hash}`\n")
    return {"contract_version": 1, "source_sha256": source_hash,
            "reporting_days": reporting_days or None, "rows": output,
            "totals": total_metrics, "metrics_csv": stream.getvalue(), "report_markdown": markdown}


def validate_campaign_report(text: str, metrics_csv: str, reporting_days: int = 0) -> dict[str, Any]:
    expected = campaign_report(text, reporting_days)
    actual = _parse(metrics_csv, METRIC_FIELDS)
    indexed = {row["campaign"]: row for row in actual}
    if set(indexed) != {row["campaign"] for row in expected["rows"]}:
        raise ValueError("metrics must contain exactly the source campaigns")
    for row in expected["rows"]:
        for field in METRIC_FIELDS[1:]:
            observed, wanted = indexed[row["campaign"]][field], row[field]
            if wanted is None:
                if observed != "":
                    raise ValueError(f"{row['campaign']}: {field} is undefined and must be empty")
            elif field == "alert":
                if observed != wanted:
                    raise ValueError(f"{row['campaign']}: alert does not match the verified reporting window")
            elif _number(observed, field, row["campaign"], maximum=Decimal("1e25")) != Decimal(wanted):
                raise ValueError(f"{row['campaign']}: {field} does not match source arithmetic")
    return {"verified": True, "contract_version": 1, "campaign_count": len(actual),
            "source_sha256": expected["source_sha256"],
            "metrics_sha256": hashlib.sha256(metrics_csv.encode("utf-8")).hexdigest(),
            "scope": "CSV campaign identity, rounded arithmetic and period-dependent flags only; no prose or external data verification"}


def campaign_report_plan() -> dict[str, Any]:
    """A reviewable method for the existing engine; no tool or model authority."""
    return {
        "name": "campaign-metrics-report",
        "description": "Compute source-based campaign metrics and publish local draft artifacts. No model calls or campaign changes.",
        "inputs": {
            "source_csv": {"type": "string", "max_length": 65536,
                           "description": "One same-unit campaign export with the seven documented CSV columns."},
            "reporting_days": {"type": "integer", "required": False, "default": 0,
                               "description": "Whole reporting days with constant daily budgets. Use 0 if the window is unknown."},
        },
        "envelope": {"tools": [], "models": [], "max_parallel_steps": 1},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_tokens": 0,
                   "max_wall_seconds": 30, "max_repairs": 0},
        "nodes": [
            {"kind": "transform", "id": "calculate", "title": "Calculate campaign metrics",
             "op": "campaign_report", "args": {"text": {"ref": "input.source_csv"},
                                                 "reporting_days": {"ref": "input.reporting_days"}}},
            {"kind": "transform", "id": "validate", "title": "Check CSV against source",
             "op": "validate_campaign_report", "args": {
                 "text": {"ref": "input.source_csv"}, "reporting_days": {"ref": "input.reporting_days"},
                 "metrics_csv": {"ref": "calculate.metrics_csv"}}},
            {"kind": "publish", "id": "publish", "title": "Save local draft artifacts",
             "needs": ["validate"], "artifacts": [
                 {"name": "campaign-metrics", "ref": "calculate.metrics_csv", "media_type": "text/csv", "primary": True},
                 {"name": "campaign-report", "ref": "calculate.report_markdown", "media_type": "text/markdown"},
                 {"name": "campaign-calculation", "ref": "calculate", "media_type": "application/json"},
             ]},
            {"kind": "verify", "id": "verify", "title": "Verify saved artifact bytes", "checks": [
                {"kind": "schema", "ref": "validate.verified", "schema": {"const": True}},
                *[{"kind": "artifact", "ref": f"publish.artifacts[{index}]", "min_bytes": 1}
                  for index in range(3)],
             ]},
        ],
        "outputs": ["calculate", "validate"],
    }
