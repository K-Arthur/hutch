"""Independent arithmetic checks for the retained paid evaluation failure."""
import csv
import io
from pathlib import Path

import pytest

from hutch.workflow.ops import apply_op


SOURCE = """campaign,impressions,clicks,spend,conversions,revenue,daily_budget
Search,10000,1000,300,20,1000,250
Social,20000,400,150,0,0,200
"""


def report(text=SOURCE, days=0):
    return apply_op("campaign_report", {"text": text, "reporting_days": days})


def test_campaign_report_preserves_undefined_cpa_and_unknown_reporting_window():
    result = report()
    rows = list(csv.DictReader(io.StringIO(result["metrics_csv"])))
    assert rows == [
        {"campaign": "Search", "ctr": "0.1", "cvr": "0.02", "cpa": "15",
         "roas": "3.3333", "alert": ""},
        {"campaign": "Social", "ctr": "0.02", "cvr": "0", "cpa": "",
         "roas": "0", "alert": "zero_conversions"},
    ]
    assert result["rows"][1]["cpa"] is None
    assert result["totals"]["cpa"] == "22.5"
    assert result["totals"]["ctr"] == "0.0467"
    assert result["reporting_days"] is None
    assert "Reporting period is unknown" in result["report_markdown"]
    assert "not a profit measure" in result["report_markdown"]
    assert "approval" in result["report_markdown"]


def test_campaign_report_only_compares_budget_over_explicit_matching_days():
    assert report(days=1)["rows"][0]["alert"] == "over_budget"
    assert report(days=2)["rows"][0]["alert"] == ""
    assert report(days=1)["source_sha256"] == report(days=2)["source_sha256"]


def test_retained_paid_csv_is_rejected_instead_of_trusting_runtime_success():
    root = Path(__file__).resolve().parents[1]
    failed = root / "docs/realignment/artifacts/desktop-production-2026-10-26/funded-candidate-v2/final2-performance-01/artifact-metrics.csv"
    with pytest.raises(ValueError, match="Social.*cpa.*undefined"):
        apply_op("validate_campaign_report", {
            "text": SOURCE, "reporting_days": 1, "metrics_csv": failed.read_text(),
        })
    # The historical fixture's requested over_budget label is only meaningful if
    # the reporting window is explicitly one day; never infer that from spend.
    good = report(days=1)
    assert apply_op("validate_campaign_report", {
        "text": SOURCE, "reporting_days": 1, "metrics_csv": good["metrics_csv"],
    })["verified"] is True


@pytest.mark.parametrize("old,new", [
    ("300,20", "NaN,20"), ("300,20", "-1,20"), ("300,20", "1e20,20"),
    ("10000,1000", "0,1000"), ("10000,1000", "10000,10001"),
    ("10000,1000", "10000,1.5"), ("Social,", "Search,"),
    ("Search,", "=DANGEROUS(),"), ("daily_budget", "daily_budget,currency"),
])
def test_campaign_report_refuses_ambiguous_unsafe_or_invalid_inputs(old, new):
    with pytest.raises(ValueError):
        report(SOURCE.replace(old, new))


@pytest.mark.parametrize("days", [True, -1, 0.5, "1", 3661])
def test_campaign_report_requires_bounded_explicit_whole_days(days):
    with pytest.raises(ValueError, match="reporting_days"):
        report(days=days)


def test_zero_denominators_and_rounding_are_deterministic():
    result = report(SOURCE.replace("10000,1000,300,20,1000,250", "0,0,0,0,0,250"))
    first = result["rows"][0]
    assert all(first[key] is None for key in ("ctr", "cvr", "cpa", "roas"))
    assert report() == report()


def test_large_valid_ratios_can_be_validated_without_float_overflow():
    source = SOURCE.replace("300,20,1000,250", "0.000001,0.000001,1000000000000000,250")
    computed = report(source)
    assert apply_op("validate_campaign_report", {"text": source,
            "metrics_csv": computed["metrics_csv"]})["verified"] is True


def test_real_workflow_publishes_and_rereads_reports_without_model_or_tool_authority(store, config):
    from hutch.engine import Engine
    from hutch.workflow.campaigns import campaign_report_plan
    from hutch.workflow import submit as wfsubmit
    from tests.test_workflow_engine import drive, make_bot

    bot = make_bot(store, tools=[])
    engine = Engine(config, store)
    submitted = wfsubmit.submit_workflow(store, bot=bot, plan=campaign_report_plan(),
                                         inputs={"source_csv": SOURCE})
    drive(engine, store, submitted.attempt_run_id)
    state = wfsubmit.status(store, submitted.workflow_run_id)
    assert state["workflow"]["status"] == "succeeded", state["workflow"].get("reason")
    run = store.get_run(submitted.attempt_run_id)
    assert run.tokens == 0 and run.cost_usd == 0
    check = next(node for node in state["nodes"] if node["site_id"] == "verify")
    assert check["result"]["verified"] is True
    assert len(check["result"]["checks"]) == 4
    assert len(state["workflow"]["result"]["artifacts"]) == 3
    assert store.verify_chain(run.id)["ok"]


@pytest.mark.parametrize("replacement", ["", "extra", "Search,0,0,0,0,0,250"])
def test_validator_rejects_missing_extra_or_duplicate_campaigns(replacement):
    good = report(days=1)["metrics_csv"]
    changed = good + replacement + "\n" if replacement else good.splitlines()[0] + "\n"
    with pytest.raises(ValueError):
        apply_op("validate_campaign_report", {"text": SOURCE, "reporting_days": 1,
                                               "metrics_csv": changed})
