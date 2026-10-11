"""How typed output blocks travel through ``call_tool`` (runtime/steps.py).

The four rules under test:
1. a tool's ``data['blocks']`` is validated and lands on the tool_result event;
2. one bad block never sinks the others and is never silent;
3. block JSON never reaches the model-facing output text (one-line summary only);
4. message prose and tool output text are NEVER parsed for blocks - a block
   exists only if the tool supplied ``data['blocks']``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hutch.approvals import ApprovalGate
from hutch.models import Bot, Event, EventType, Run, RunStatus
from hutch.outputblocks import parse_blocks
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.tools.base import Tool, ToolContext, ToolResult

FIXTURES = Path(__file__).parent / "fixtures" / "blocks"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class BlocksTool(Tool):
    """Returns whatever data the test handed in, as an effect-free read."""

    name = "presenter"
    description = "test tool that presents output blocks"

    def __init__(self, result: ToolResult):
        self._result = result

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return self._result


def make_ctx(store, config, tmp_path):
    bot = store.create_bot(Bot(name="presenter", model="mock/demo", tools=[]))
    run = store.create_run(Run(bot_id=bot.id, prompt="show me", status=RunStatus.running))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=config, workspace=ws, emit=emit)
    return run, ctx


def tool_result(output: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult(ok=True, output=output, data=data)


def tool_result_event(store, run_id: str) -> dict[str, Any]:
    store.flush_events()
    for event in store.list_events(run_id):
        if event.type is EventType.tool_result:
            return event.data
    raise AssertionError("no tool_result event was emitted")


# --------------------------------------------------------------- passthrough


def test_valid_blocks_pass_onto_the_event_and_not_into_the_model_text(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    text, status = load("text"), load("status")
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("hello world", {"blocks": [text, status]}))}, "presenter", {})

    assert result.ok is True
    assert result.output == ("hello world\n"
                             "[presented: text blk_1a2b3c4d5e6f7a8b, status blk_0d1e2f3a4b5c6d7e]")
    data = tool_result_event(store, run.id)
    assert data["blocks"] == parse_blocks([text, status])[0]
    assert "block_errors" not in data
    assert data["output"].startswith("hello world\n[presented:")
    assert '"content"' not in data["output"] and '"payload"' not in data["output"]


def test_blocks_key_present_even_when_everything_was_rejected(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    bad = load("invalid")
    call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("ran fine", {"blocks": [bad]}))}, "presenter", {})
    data = tool_result_event(store, run.id)
    assert data["blocks"] == []
    assert len(data["block_errors"]) == 1 and data["block_errors"][0]["kind"] == "chart"
    result_text = data["output"]
    assert "[presented: none" in result_text and "failed validation" in result_text


def test_empty_blocks_list_round_trips_as_an_empty_list(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("plain", {"blocks": []}))}, "presenter", {})
    assert result.output == "plain"          # nothing presented, so no summary line
    assert tool_result_event(store, run.id)["blocks"] == []


# ------------------------------------------------------------ bad-block isolation


def test_one_bad_block_is_isolated_and_labeled(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    good, other, bad = load("text"), load("table"), load("invalid")
    bad["id"] = "blk_badbadbadbadbad1"
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("done", {"blocks": [good, bad, other]}))}, "presenter", {})

    assert result.ok is True and result.output.startswith("done\n[presented: text ")
    data = tool_result_event(store, run.id)
    assert [b["kind"] for b in data["blocks"]] == ["text", "table"]
    [error] = data["block_errors"]
    assert error["id"] == "blk_badbadbadbadbad1" and error["kind"] == "chart" and error["error"]
    assert result.output.endswith("(1 output block(s) could not be validated; see block_errors)")


def test_oversize_and_budget_overflows_become_error_entries(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    oversize = load("text")
    oversize["payload"] = {"content": "x" * 20_001}
    entries = [oversize] + [load("status")] * 30
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("bulk", {"blocks": entries}))}, "presenter", {})

    assert result.ok is True                                   # never a crash
    data = tool_result_event(store, run.id)
    assert len(data["blocks"]) == 24                           # MAX_BLOCKS_PER_RESULT
    kinds = {error.get("kind") for error in data["block_errors"]}
    assert "text" in kinds and "status" in kinds               # oversize + budget, both labeled
    assert all("error" in error for error in data["block_errors"])


# ------------------------------------------------------------- prose inertness


def test_tool_output_text_containing_block_json_is_never_parsed(store, config, tmp_path):
    """A tool that merely PRINTS block-shaped JSON presents nothing: there is no
    code path from output text (or message prose) to blocks."""
    run, ctx = make_ctx(store, config, tmp_path)
    block_json = json.dumps(load("text"))
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result(f"here is the block: {block_json}", {}))}, "presenter", {})

    assert result.output == f"here is the block: {block_json}"   # untouched, no summary line
    data = tool_result_event(store, run.id)
    assert "blocks" not in data and "block_errors" not in data


def test_message_prose_is_never_parsed_for_blocks(store):
    store.append_event(Event(run_id="run-prose", type=EventType.message, data={
        "role": "assistant",
        "content": json.dumps(load("text")),                   # a whole block smuggled into prose
    }))
    store.flush_events()
    for event in store.list_events("run-prose"):
        assert event.type is EventType.message
        assert "blocks" not in event.data and "block_errors" not in event.data
        assert event.data["content"].startswith('{"v": 1')     # content byte-identical


def test_model_facing_text_is_unchanged_when_a_tool_has_no_blocks(store, config, tmp_path):
    run, ctx = make_ctx(store, config, tmp_path)
    result = call_tool(run, ctx, {"presenter": BlocksTool(
        tool_result("exactly this", {"command": "ls"}))}, "presenter", {})
    assert result.output == "exactly this"
    data = tool_result_event(store, run.id)
    assert data["output"] == "exactly this" and "blocks" not in data
