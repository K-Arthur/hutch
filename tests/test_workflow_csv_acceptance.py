"""Acceptance: a messy CSV becomes a verified report with no model call at all.

This is the mission's non-coding acceptance scenario, executed for real: a sizeable messy
CSV is parsed, the plan branches on what the data actually contains (ragged rows, missing
columns), results are computed deterministically, a report is published as a verified
artifact, and the outcome is verified with independent evidence (schema, artifact hash
read-back, and a person's answer to a durable question).

Budget ``max_model_calls`` is zero: nothing here needs a planner or a worker model, which
is exactly the point - a complete local workflow that runs on the deterministic executor.
"""
from __future__ import annotations

import csv
import io
import random
import time

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from tests.test_workflow_engine import drive, make_bot

CATEGORIES = ["hardware", "software", "services", "training", "travel"]


def messy_csv(rows: int = 400, seed: int = 7) -> str:
    """A sizeable CSV with real mess: blank lines, ragged rows, quoted commas."""
    rng = random.Random(seed)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "category", "vendor", "amount", "note"])
    for index in range(rows):
        line = [
            f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            rng.choice(CATEGORIES),
            f"vendor-{rng.randint(1, 40)}",
            f"{rng.randint(5, 900)}.{rng.randint(0, 99):02d}",
            'note, with a comma' if index % 37 == 0 else "ok",
        ]
        if index % 53 == 0:
            out.write("\n")                                   # blank line
        if index % 71 == 0:
            line = line[:3]                                    # ragged row
        writer.writerow(line)
    return out.getvalue()


def csv_plan() -> dict:
    return {
        "name": "expense-audit",
        "description": "Parse a messy expense export, branch on what it actually contains, "
                       "and publish a verified summary.",
        "inputs": {
            "csv": {"type": "string", "required": True, "max_length": 100_000},
            "period": {"type": "string", "default": "current export"},
        },
        "envelope": {"tools": [], "models": [], "max_parallel_steps": 1},
        "budget": {"max_nodes": 40, "max_model_calls": 0, "max_wall_seconds": 300,
                   "max_fanout": 10, "max_repairs": 0},
        "nodes": [
            {"kind": "transform", "id": "table", "op": "parse_table",
             "args": {"text": {"ref": "input.csv"}, "max_rows": 5000}},
            # Branch on the observed columns: only group when the column is really there.
            {"kind": "branch", "id": "shape",
             "condition": {"ref": "table.columns", "op": "contains", "value": "category"},
             "then": [
                 {"kind": "transform", "id": "by_category", "op": "group_count",
                  "args": {"items": {"ref": "table.rows"}, "by": "category"}},
                 {"kind": "transform", "id": "totals", "op": "total",
                  "args": {"items": {"ref": "table.rows"}, "of": "amount"}},
                 # A bounded construct exposes its own aggregate only, so the branch packs
                 # what it wants to hand on into one value.
                 {"kind": "transform", "id": "packed", "op": "merge",
                  "args": {"values": [
                      {"by_category": {"ref": "shape.then.by_category"},
                       "total": {"ref": "shape.then.totals"}}]}},
             ],
             "else": [
                 {"kind": "transform", "id": "no_category", "op": "constant",
                  "args": {"value": "the export has no 'category' column"}},
             ]},
            {"kind": "transform", "id": "problems", "op": "join_text",
             "args": {"items": {"ref": "table.bad_rows"}, "separator": "\n", "of": "line"}},
            {"kind": "transform", "id": "report", "op": "join_text",
             "args": {"separator": "\n", "items": [
                 {"template": "Expense audit — {{period}}", "values": {"period": {"ref": "input.period"}}},
                 {"template": "Rows kept: {{kept}} of {{total}}",
                  "values": {"kept": {"ref": "table.kept"}, "total": {"ref": "table.total"}}},
                 {"template": "Rows rejected: {{bad}}", "values": {"bad": {"ref": "table.bad"}}},
                 {"template": "Total amount: {{total}}",
                  "values": {"total": {"ref": "shape.result.total"}}},
                 {"template": "By category:\n{{groups}}",
                  "values": {"groups": {"ref": "shape.result.by_category"}}},
                 {"template": "Rejected lines:\n{{lines}}",
                  "values": {"lines": {"ref": "problems"}}},
             ]}},
            {"kind": "publish", "id": "deliver", "artifacts": [
                {"name": "expense-report", "ref": "report", "media_type": "text/markdown",
                 "primary": True}]},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "table.kept", "schema": {"type": "integer", "minimum": 300}},
                {"kind": "schema", "ref": "table.bad", "schema": {"type": "integer", "minimum": 1}},
                {"kind": "artifact", "ref": "deliver.artifacts[0]", "min_bytes": 100},
                {"kind": "human", "prompt": "Does this expense summary look right for the sample data?",
                 "timeout_seconds": 600},
            ], "on_fail": {"action": "stop"}},
        ],
        "outputs": ["report", "deliver"],
    }


def test_messy_csv_becomes_a_verified_report_without_any_model_call(store, config):
    bot = make_bot(store, name="csv-bot", model="ollama/qwen3:4b", tools=["files"])
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=csv_plan(),
                                          inputs={"csv": messy_csv(), "period": "FY26 Q3"},
                                          definition_name="expense-audit")
    assert submission.verdicts == []          # no agent nodes, so no model role is involved

    deadline = time.monotonic() + 60
    question = None
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        if pending:
            question = pending[0]
            break
        run = store.get_run(submission.attempt_run_id)
        if run is not None and run.status not in ACTIVE_STATUSES:
            break
        time.sleep(0.05)
    assert question is not None, "the workflow should be waiting for its human check"
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "waiting"
    assert wfsubmit.answer(store, question["id"], "yes") == "won"

    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]

    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["table"]["result"]["kept"] > 300
    assert nodes["table"]["result"]["bad"] >= 1
    assert nodes["shape"]["result"]["taken"] == "then"
    assert nodes["shape.then.by_category"]["result"]["hardware"] > 0
    assert nodes["shape.then.totals"]["result"] > 0
    assert nodes["shape.then.packed"]["result"]["total"] > 0
    assert nodes["shape.then.packed"]["result"]["by_category"]["travel"] > 0
    report_text = str(nodes["report"]["result"])
    assert "Rejected lines" in report_text
    # The prose must be internally consistent, not merely present: kept + rejected = total.
    kept = nodes["table"]["result"]["kept"]
    bad = nodes["table"]["result"]["bad"]
    assert f"Rows kept: {kept} of {kept + bad}" in report_text
    assert f"Rows rejected: {bad}" in report_text
    assert "Total amount:" in report_text and "By category:" in report_text

    # The verification recorded independent evidence, including the person's answer.
    check = nodes["check"]["result"]
    assert check["verified"] is True
    kinds = {item["kind"] for item in check["checks"]}
    assert kinds == {"schema", "artifact", "human"}

    published = view["workflow"]["result"]["artifacts"]
    assert published and published[0]["name"] == "expense-report"
    assert published[0]["bytes"] > 100

    # The artifact is reachable and hash-verified through the canonical artifact API.
    records = store.artifact_records(submission.attempt_run_id)
    assert any(kind == "tool_output" for _event, kind in records)
    # Zero model calls: the budget was never touched (the ledger only gains keys it spends).
    assert view["workflow"]["ledger"].get("model_calls", 0) == 0


def test_the_same_plan_handles_a_clean_export_without_bad_rows(store, config):
    """The same committed plan adapts to the data it actually receives."""
    bot = make_bot(store, name="csv-clean-bot", model="ollama/qwen3:4b", tools=["files"])
    engine = Engine(config, store)
    clean = "date,category,amount\n2026-01-02,hardware,10.00\n2026-01-03,software,20.50\n"
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=csv_plan(),
                                          inputs={"csv": clean},
                                          definition_name="expense-audit")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        if pending:
            wfsubmit.answer(store, pending[0]["id"], "yes")
        run = store.get_run(submission.attempt_run_id)
        if run is not None and run.status not in ACTIVE_STATUSES:
            break
        time.sleep(0.05)
    view = wfsubmit.status(store, submission.workflow_run_id)
    # The declared minimums were written for the messy sample; the plan stops honestly
    # instead of pretending a two-row file passed an audit designed for hundreds.
    assert view["workflow"]["status"] == "failed"
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["table"]["result"]["bad"] == 0
    assert ">= 300" in nodes["check"]["error"]["reason"]
