"""A discovered-file research slice that keeps omissions visible through publication.

The provider is a scripted local HTTP endpoint, but the real workflow interpreter,
file tools, child-run admission, schema gate, usage reservations and artifact verification
are exercised. This is integration evidence for orchestration, not model quality.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from tests.fakes import FakeOllama, agent_script
from tests.test_workflow_engine import make_bot


REVIEW_SCHEMA = {
    "type": "object",
    "required": ["path", "findings", "evidence"],
    "properties": {
        "path": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


def research_plan() -> dict:
    return {
        "name": "discovered-document-research",
        "description": "Discover bounded source files, review each one, and publish explicit coverage.",
        "inputs": {"root": {"type": "string", "default": "research"}},
        "envelope": {"tools": ["list_files", "read_file"],
                     "models": ["ollama/tiny:1b"], "max_parallel_steps": 1},
        "budget": {"max_nodes": 24, "max_model_calls": 3, "max_tokens": 12_000,
                   "max_wall_seconds": 120, "max_fanout": 3, "max_repairs": 0},
        "nodes": [
            {"kind": "tool", "id": "discover", "tool": "list_files",
             "args": {"path": {"ref": "input.root"}}},
            {"kind": "map", "id": "review_sources",
             "over": {"ref": "discover.data.entries"}, "item_key": "path",
             "max_items": 3, "concurrency": 1, "on_item_failure": "skip",
             "body": [
                 {"kind": "tool", "id": "source", "tool": "read_file",
                  "args": {"path": {"ref": "item.path"}}},
                 {"kind": "agent", "id": "review", "role": "worker",
                  "model": "ollama/tiny:1b",
                  "instruction": "Review this source only. Return concise findings and exact evidence quotes from the supplied source.",
                  "inputs": {"path": {"ref": "item.path"},
                             "source": {"ref": "review_sources.source.output"}},
                  "output_schema": REVIEW_SCHEMA, "tools": [], "max_steps": 1},
                 {"kind": "transform", "id": "bundle", "op": "merge",
                  "args": {"values": [
                      {"path": {"ref": "item.path"},
                       "source": {"ref": "review_sources.source.output"},
                       "source_truncated": {"ref": "review_sources.source.data.truncated"},
                       "result_truncated": {"ref": "review_sources.source.data.workflow_output_truncated"},
                       "review": {"ref": "review_sources.review.output"}},
                  ]}},
             ]},
            {"kind": "transform", "id": "coverage", "op": "document_coverage",
             "args": {"discovered": {"ref": "discover.data.paths"},
                      "reviews": {"ref": "review_sources.items"},
                      "skipped": {"ref": "review_sources.skipped"},
                      "failures": {"ref": "review_sources.failures"},
                      "listing_complete": {"ref": "discover.data.paths_complete"}}},
            {"kind": "publish", "id": "deliver", "artifacts": [
                {"name": "document-coverage", "ref": "coverage",
                 "media_type": "application/json", "primary": True}]},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "coverage.covered_count",
                 "schema": {"type": "integer", "minimum": 2}},
                {"kind": "schema", "ref": "coverage.omissions",
                 "schema": {"type": "array", "minItems": 1}},
                {"kind": "artifact", "ref": "deliver.artifacts[0]", "min_bytes": 100},
            ]},
        ],
        "outputs": ["coverage"],
    }


def test_discovered_document_research_publishes_exact_coverage_and_omissions(
        store, config, tmp_path, monkeypatch):
    plan_path = (Path(__file__).resolve().parents[1]
                 / "docs/realignment/artifacts/dynamic-workflows/document-research.plan.json")
    assert json.loads(plan_path.read_text()) == research_plan()

    # Keep fake model admission independent of host RAM; these tests verify workflow behavior, not model fit.
    model = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 100_000_000, "ctx": 8192}})
    model.script = agent_script([
        {"content": json.dumps({"path": "research/a.md",
                                 "findings": ["Monthly reliability reports are published."],
                                 "evidence": ["publishes monthly reliability reports"]})},
        {"content": "This response is not a JSON object matching the review contract."},
        {"content": json.dumps({"path": "research/c.md",
                                 "findings": ["Retry limits are undocumented."],
                                 "evidence": ["does not document retry limits"]})},
    ])
    monkeypatch.setenv("OLLAMA_HOST", model.url)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bot = make_bot(store, name="document-research-bot", model="ollama/tiny:1b",
                   tools=["files"], selfcheck=False, workdir=str(workspace))
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=research_plan(), definition_name="document-research")
    source_dir = workspace / "research"
    source_dir.mkdir(parents=True)
    (source_dir / "a.md").write_text("The service publishes monthly reliability reports.")
    (source_dir / "b.md").write_text("Customer exports can lose comments.")
    (source_dir / "c.md").write_text("The vendor does not document retry limits.")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        engine.tick()
        workflow = wstore.workflow_run(store, submission.workflow_run_id)
        if workflow is not None and workflow["status"] in ("succeeded", "failed", "stopped"):
            break
        time.sleep(0.03)
    else:
        raise AssertionError("document research did not settle")

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", (
        view["workflow"].get("reason"),
        [(node["site_id"], node["status"], node.get("error")) for node in view["nodes"]],
    )
    assert view["workflow"]["ledger"]["model_calls"] == 3
    assert len(model.of("/api/chat")) == 3
    coverage = next(node for node in view["nodes"] if node["site_id"] == "coverage")["result"]
    assert coverage["complete"] is False
    assert coverage["discovery_complete"] is True
    assert coverage["discovered_count"] == 3
    assert coverage["covered_count"] == 2
    assert [item["path"] for item in coverage["covered"]] == ["research/a.md", "research/c.md"]
    assert coverage["covered"][0]["evidence"] == ["publishes monthly reliability reports"]
    assert len(coverage["omissions"]) == 1
    assert coverage["omissions"][0]["path"] == "research/b.md"
    assert "did not satisfy its output contract" in coverage["omissions"][0]["reason"]
    assert view["workflow"]["result"]["output_outcomes"]["partial"] == ["coverage"]

    artifact = next(node for node in view["nodes"] if node["site_id"] == "deliver")["result"]["artifacts"][0]
    published_text = (config.run_dir(bot.name, artifact["run_id"])
                      / artifact["artifact"]).read_text()
    assert json.loads(published_text) == coverage
    assert "research/b.md" in published_text and '"omissions"' in published_text
