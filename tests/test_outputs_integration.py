"""T-OUTPUTS-INTEGRATION: the three lanes wired together on the integration tree.

Pins the integration glue the lanes deliberately left to the integrator:

* the tool catalog exposes and groups the media and workspace tools;
* ``create_app`` mounts the media serving router and the workspace session router,
  local-owner-only by default;
* ``render_diagram`` runs end-to-end (real deterministic SVG, real media store) and
  its blocks survive the contract's own validator; the content route serves the
  verified bytes;
* ``run_python`` fails closed with containment off and runs for real when the host
  can contain it;
* the widgets assets are shipped and referenced by index.html.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch import sandbox
from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.outputblocks import parse_blocks
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.server.app import create_app
from hutch.tools import ALL_TOOL_NAMES, GROUPS, build_tools, expand_tools
from hutch.tools.base import ToolContext


def test_catalog_and_groups_expose_the_lane_tools():
    for name in ("create_media", "render_diagram", "run_python", "reset_workspace"):
        assert name in ALL_TOOL_NAMES
    assert GROUPS["media"] == ["create_media", "render_diagram"]
    assert GROUPS["workspace"] == ["run_python", "reset_workspace"]
    assert set(expand_tools(["media", "workspace"])) == {
        "create_media", "render_diagram", "run_python", "reset_workspace"}


def test_app_mounts_media_and_workspace_routers(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    # Included routers are wrapped (``_IncludedRouter``) in this FastAPI version, so the
    # schema — which resolves nested routes — is the honest inventory.
    paths = app.openapi().get("paths", {})
    assert "/api/v1/media/{media_id}/versions/{version}/content" in paths
    assert "/api/v1/media/{media_id}/versions/{version}/poster" in paths
    assert "/api/v1/conversations/{conversation_id}/workspace/session" in paths
    assert "/api/v1/conversations/{conversation_id}/workspace/reset" in paths


def test_widget_assets_are_shipped_and_referenced():
    static = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "static"
    for name in ("widgets.js", "widgets.css", "vendor/uplot/uPlot.iife.min.js",
                 "vendor/uplot/uPlot.min.css", "vendor/uplot/LICENSE"):
        assert (static / name).is_file(), name
    index = (static / "index.html").read_text()
    assert "/static/widgets.js" in index and "/static/widgets.css" in index
    assert "/static/vendor/uplot/uPlot.iife.min.js" in index
    app_js = (static / "app.js").read_text()
    assert "hutchWidgetsFeedItemHtml" in app_js and "HutchWidgets" in app_js


def _ctx(store, config, tmp_path, *, tools: list[str], sandbox_mode: str = "strict",
         approval: ApprovalMode = ApprovalMode.auto) -> ToolContext:
    bot = store.get_bot("int-bot") or store.create_bot(
        Bot(name="int-bot", model="mock/demo", tools=tools, approval_mode=approval,
            sandbox=sandbox_mode))
    conversation, _ = store.create_conversation(bot.id, "integration", idem_key=f"k-{bot.id}",
                                                request_hash="h")
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running,
                               conversation_id=conversation["id"]))
    workspace = tmp_path / "run-ws"
    workspace.mkdir(exist_ok=True)
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    return ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                       workspace=workspace, emit=emit)


def test_render_diagram_end_to_end_produces_valid_blocks(store, config, tmp_path):
    ctx = _ctx(store, config, tmp_path, tools=["render_diagram"])
    result = call_tool(ctx.run, ctx, build_tools(["render_diagram"], ctx), "render_diagram", {
        "title": "Ingest pipeline",
        "nodes": [{"id": "collect", "label": "Collect input", "group": "ingest"},
                  {"id": "validate", "label": "Validate"},
                  {"id": "store", "label": "Store"}],
        "edges": [{"from": "collect", "to": "validate"},
                  {"from": "validate", "to": "store", "label": "on success"},
                  {"from": "validate", "to": "collect", "label": "on rejection"}],
        "direction": "LR"})
    assert result.ok is True, result.output
    events = [e for e in store.list_events(ctx.run.id) if e.type.value == "tool_result"]
    blocks, errors = parse_blocks(events[-1].data.get("blocks"))
    assert errors == []
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["media", "flowchart"]
    media = blocks[0]["payload"]
    assert media["mime"] == "image/svg+xml" and media["generated_by"] == "deterministic"
    assert media["alt_text"] and media["sha256"]
    flowchart = blocks[1]["payload"]
    assert len(flowchart["nodes"]) == 3 and len(flowchart["edges"]) == 3


def test_media_content_route_serves_the_verified_diagram_bytes(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(config.state_dir))
    ctx = _ctx(store, config, tmp_path, tools=["render_diagram"])
    result = call_tool(ctx.run, ctx, build_tools(["render_diagram"], ctx), "render_diagram", {
        "title": "Tiny flow",
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [{"from": "a", "to": "b"}]})
    assert result.ok is True, result.output
    media = result.data["media"]
    with TestClient(create_app()) as client:
        response = client.get(f"/api/v1/media/{media['media_id']}/versions/{media['version']}/content")
        assert response.status_code == 200, response.text
        assert response.headers["x-hutch-artifact-verified"] == "sha256"
        assert hashlib.sha256(response.content).hexdigest() == media["sha256"]
        ranged = client.get(f"/api/v1/media/{media['media_id']}/versions/{media['version']}/content",
                            headers={"Range": "bytes=0-9"})
        assert ranged.status_code == 206 and len(ranged.content) == 10


def test_run_python_fails_closed_when_containment_is_off(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "off")
    sandbox.reset_cache()
    ctx = _ctx(store, config, tmp_path, tools=["run_python"])
    result = call_tool(ctx.run, ctx, build_tools(["run_python"], ctx), "run_python",
                       {"code": "print('must not run')"})
    assert result.ok is False
    assert "no uncontained Python workspace" in result.output
    assert "must not run" not in result.output


pytestmark_sandbox = pytest.mark.skipif(not sandbox.status().ok,
                                        reason=f"no usable sandbox here: {sandbox.status().reason}")


@pytestmark_sandbox
def test_run_python_end_to_end_in_the_integrated_tree(store, config, tmp_path, monkeypatch):
    monkeypatch.delenv("HUTCH_SANDBOX", raising=False)
    sandbox.reset_cache()
    from hutch.workspace.manager import _MANAGERS
    _MANAGERS.clear()
    try:
        ctx = _ctx(store, config, tmp_path, tools=["run_python"])
        first = call_tool(ctx.run, ctx, build_tools(["run_python"], ctx), "run_python",
                          {"code": "total = 40 + 2\nprint(f'the answer is {total}')\ntotal + 100",
                           "timeout_seconds": 30})
        assert first.ok is True, first.output
        assert "142" in first.output, "the trailing expression is reported to the model"
        events = [e for e in store.list_events(ctx.run.id) if e.type.value == "tool_result"]
        blocks, errors = parse_blocks(events[-1].data.get("blocks"))
        assert errors == []
        receipt = next(b for b in blocks if b["kind"] == "code_receipt")
        payload = receipt["payload"]
        assert payload["source_sha256"] == hashlib.sha256(payload["source"].encode()).hexdigest()
        assert payload["execution"]["status"] == "ok"
        assert payload["execution"]["environment_generation"] >= 1
        assert payload["result_repr"] == "142"
        assert "the answer is 42" in payload["stdout_tail"]
        second = call_tool(ctx.run, ctx, build_tools(["run_python"], ctx), "run_python",
                           {"code": "print('kept', total)", "timeout_seconds": 30})
        events = [e for e in store.list_events(ctx.run.id) if e.type.value == "tool_result"]
        blocks, errors = parse_blocks(events[-1].data.get("blocks"))
        assert errors == []
        receipt = next(b for b in blocks if b["kind"] == "code_receipt")
        assert "kept 42" in receipt["payload"]["stdout_tail"], "state persists within one generation"
    finally:
        from hutch.workspace.manager import _MANAGERS as managers
        for manager in list(managers.values()):
            try:
                manager.close()
            except Exception:  # noqa: BLE001
                pass
        managers.clear()
        sandbox.reset_cache()
