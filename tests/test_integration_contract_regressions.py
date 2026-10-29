"""ADR-0017 integration contracts: current compaction checks and remaining skeletons.

ADR-0017 §5 S0 required failing skeletons before implementation. The three S6
compaction contracts now use current owner fencing, persistent events, real
compaction manifests and finite scripted HTTP responses. The remaining S5/S7
contracts retain strict xfail markers; their gaps are not declared implemented.
An unexpected pass still fails that gate until the owning implementation lands.

Failure mode -> slice mapping (each test cites its ADR text in place):

1. Tool bindings survive compaction            opencode#40901  -> S6 ("tool specs re-derived each
    request (regression for opencode#40901)", ADR-0017 §5 S6; §10 row "Long-session continuity ...
    (S0 regressions land here)")
2. Last user request retained verbatim         claude-code#22376 -> S6 (pinned set "preserved verbatim
    (operator policy, exact constraints, last user request, unexecuted work, pending call/result
    pairs)", ADR-0017 §5 S6; §3.2)
3. Stale skill invocations not re-executed     claude-code#40193 -> S6 ("stale invocations scoped to
    their turn", ADR-0017 §5 S6; brief §9 "Do not restore completed or obsolete skill invocations
    as new requests", Appendix A)
4. Tool-catalog/manifest context size bounded  opencode#35376  -> S5 (the composer's fragment registry
    with per-fragment token budgets over the tool_definitions fragment, budget.py serialized-request
    accounting, ADR-0017 §3.2, §5 S5; §9 "Catalog exposure" targets (a)-(c) anchored on #35376)
5. Auth recovery re-reads persisted state      notebooklm-py#2161 -> S7 ("auth loss mid-upload ...
    reconcile, never assume", ADR-0017 §5 S7; §10 row "Authentication boundaries: ... refresh race
    guarded by generation/CAS on persisted state (#2161 lesson)")
6. No success without a live probe/read-back   false-sync / false-generation -> S7 ("verify via
    sources.get metadata read-back; batchDelete returns {} even for missing names, verify by
    re-get", ADR-0017 §5 S7; §4.3 "A provider job id or URL is never reported as a completed
    artifact"; §11 "Nothing is declared successful from ... passing mocks alone". The media mirror
    of the same guard is S8; S7 lands first and this skeleton pins the shared receipt-level rule.)

The first three exercise implemented compaction through a leased runtime and bounded
scripted HTTP responses. Their original fixtures predated owner fencing and compaction.
The final three remain strict expected failures for their documented integration gaps.
These are controlled Hutch regressions inspired by reports, not reproduced upstream defects.
"""

from __future__ import annotations

import json

import pytest

from hutch import skills as sk
from hutch.approvals import ApprovalGate
from hutch.connections import ConnectionBook
from hutch.context import prompt_tokens
from hutch.hardware import Gpu, Hardware
from hutch.models import ApprovalMode, Bot, EventType, Run
from hutch.providers import ChatRequest
from hutch.providers.ollama import OllamaProvider
from hutch.runtime.builtin import BuiltinRuntime, reset_connection_cache
from hutch.runtime.ladder import Ladder, reset_provider_cache
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.toolcalling.compiler import clear_plan_cache, compile_plan
from hutch.toolcalling.profiles import resolve_profile
from hutch.tools import build_tools
from hutch.tools.base import Tool, ToolContext, ToolResult
from tests.fakes import FakeOllama, FakeOpenAI, agent_script
from tests.test_runtime_builtin import run_it

BIG_BOX = Hardware(gpus=[Gpu("X", "nvidia", 24.0, False, 24.0)], ram_total_gb=64, ram_available_gb=48)
WINDOW = 16384  # The bounded compaction fixture, including pinned tool/instruction overhead.
WRITE = {"name": "write_file", "arguments": {"path": "out.md", "content": "hello"}}
NEEDLE = "deliver the finished report to archive-box-77f3c2 and state all lengths in millimetres"


@pytest.fixture(autouse=True)
def _fresh_providers():
    reset_provider_cache()
    reset_connection_cache()


@pytest.fixture()
def ollama():
    s = FakeOllama({"fake:8b": {}})
    yield s
    s.close()


@pytest.fixture()
def oai():
    s = FakeOpenAI()
    yield s
    s.close()


def _build(store, config, tmp_path, *, tools=("files",), prompt="write a file", **bot_kw):
    """A real Bot + Run + ToolContext + registry, in the tests/test_runtime_builtin.py style."""
    bot_kw.setdefault("selfcheck", False)
    bot = Bot(name="s0-regression", model="ollama/fake:8b", tools=list(tools),
              approval_mode=ApprovalMode.auto, description="d", **bot_kw)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt=prompt)
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emitted: list = []

    def emit(ev):
        emitted.append(ev)
        store.append_event(ev)

    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.05)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                      workspace=ws, emit=emit)
    return bot, run, ctx, emitted, build_tools(bot.tools, ctx)


def _runtime(ollama):
    def factory(provider, base_url):
        if provider == "ollama":
            return OllamaProvider(ollama.url)
        raise AssertionError(provider)
    return BuiltinRuntime(hardware=BIG_BOX, provider_factory=factory, sleep=lambda s: None)


def _compacting_script(ollama, workspace, *, first_calls=()):
    """Grow history through real bounded reads, then finish after compaction.

    Summarizer requests have a distinct response, so they cannot consume or
    accidentally repeat the main agent's next action. A finite terminal response
    keeps the fixture from turning into an unrelated max-steps failure.
    """
    calls = list(first_calls)
    for index in range(8):
        name = f"source_{index:02}.txt"
        (workspace / name).write_text(f"Source {index}: retain evidence and constraints. " * 1000)
        calls.append({"tool_calls": [{"name": "read_file", "arguments": {"path": name}}]})
    calls.extend([{"tool_calls": [WRITE]}, {"content": "done after compaction"}])
    main = agent_script(calls)

    def script(body):
        if _is_compactor(body):
            return {"content": "Sources were read. Keep the original request and constraints; finish the report."}
        return main(body)
    ollama.script = script


def _is_compactor(body):
    return any("compact part of a conversation" in str(message.get("content", ""))
               for message in body.get("messages", []) if isinstance(message, dict))


def _compacted_main_requests(store, run, ollama):
    manifests = store.run_compactions(run.id)
    assert manifests, "the fixture must actually compact, not merely complete a short run"
    assert all(manifest["status"] == "compacted" for manifest in manifests)
    assert all(manifest["before_tokens"] > manifest["after_tokens"] > 0 for manifest in manifests)
    assert all(manifest["summary_digest"] and manifest["reservation_id"] for manifest in manifests)
    requests = [request["body"] for request in ollama.of("/api/chat")
                if not _is_compactor(request["body"])]
    assert any("<compacted_history>" in str(body["messages"]) for body in requests)
    return requests


# ========================================================================= compaction regressions
# Proactive compaction should prevent provider overflow. The persisted manifests,
# shrinking token counts and subsequent compacted-history requests are the proof;
# requiring an oversized HTTP request would reward the former truncation defect.


def test_tool_bindings_survive_compaction(store, config, tmp_path, ollama):
    """S6 / opencode#40901 inspiration: every main request retains authorized tools."""
    _, run, ctx, _, tools = _build(store, config, tmp_path, num_ctx=WINDOW)
    _compacting_script(ollama, ctx.workspace)
    assert run_it(_runtime(ollama), run, ctx, tools) == "done after compaction"
    requests = _compacted_main_requests(store, run, ollama)
    assert tools
    for body in requests:
        assert sorted(tool["function"]["name"] for tool in body.get("tools") or []) == sorted(tools)
    assert (ctx.workspace / "out.md").read_text() == "hello", "tools must still execute after compaction"


def test_last_user_request_survives_compaction_verbatim(store, config, tmp_path, ollama):
    """S6 / claude-code#22376 inspiration: summarization cannot rewrite constraints."""
    prompt = f"Prepare the site report. {NEEDLE}"
    _, run, ctx, _, tools = _build(store, config, tmp_path, num_ctx=WINDOW, prompt=prompt)
    _compacting_script(ollama, ctx.workspace)
    assert run_it(_runtime(ollama), run, ctx, tools) == "done after compaction"
    for body in _compacted_main_requests(store, run, ollama):
        users = [message for message in body["messages"] if message.get("role") == "user"]
        assert users and prompt in users[-1]["content"], "retain the exact original request through every main call"
    assert store.get_run(run.id).prompt == prompt, "canonical evidence is never summarized in place"


def test_stale_skill_invocations_are_not_restored_as_new_requests(store, config, tmp_path, ollama):
    """S6 / claude-code#40193 inspiration: completed skills are not replayed."""
    source = tmp_path / "sources" / "helper"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: helper\ndescription: Helps with a thing.\nmetadata:\n  hutch.version: \"1.0\"\n---\n\n"
        "## Steps\n1. Review the supplied source carefully.\n", encoding="utf-8")
    registry = sk.SkillRegistry(config.state_dir)
    registry.install_path(source)
    registry.trust("helper")
    bot, run, ctx, emitted, _ = _build(store, config, tmp_path, skills=["helper"], num_ctx=WINDOW)
    ctx.skills = registry.effective_for_bot(bot)
    tools = build_tools(bot.tools, ctx)
    assert "use_skill" in tools
    _compacting_script(ollama, ctx.workspace, first_calls=[{
        "tool_calls": [{"name": "use_skill", "arguments": {"name": "helper"}}]}])
    assert run_it(_runtime(ollama), run, ctx, tools) == "done after compaction"
    executions = [event for event in emitted if event.type is EventType.tool_result
                  and event.data.get("tool") == "use_skill" and event.data.get("ok")]
    assert len(executions) == 1, "the completed invocation must not execute twice"
    for body in _compacted_main_requests(store, run, ollama):
        messages = body["messages"]
        for index, message in enumerate(messages):
            for call in message.get("tool_calls") or []:
                if call.get("function", {}).get("name") == "use_skill":
                    assert any(result.get("role") == "tool" and result.get("tool_call_id") == call.get("id")
                               for result in messages[index + 1:]), "no stale unanswered skill invocation may survive"


# ========================================================================= manifest-size regression
# ADR-0017 assigns this to S5: the composer's fragment registry prices the tool_definitions
# fragment and budget-parameterized profiles bound it (§3.2 modules fragments.py/profiles.py/
# budget.py), with §9 "Catalog exposure" naming the three targets: "(a) per-server schema byte cap
# on tools/list retention; (b) per-turn visible integration tools cap; (c) tool-search threshold,# anchor: Claude docs recommend lazy exposure past ~20 tools". Nothing bounds the catalog today:
# the real compiler emits a full OpenAI schema for every catalog entry
# (src/hutch/toolcalling/compiler.py:110-111, native branch), the loop freezes and sends all of
# them every turn (builtin.py:631, 708), and the estimator only counts the result
# (src/hutch/context.py:33-38).


@pytest.mark.xfail(strict=True, reason="ADR-0017 S5")
def test_integration_catalog_context_stays_bounded():
    """opencode#35376: ~290 connected tools cost 40-70k tokens of upfront catalog context.

    ADR-0017 §5 S5 fixes this via the composer's bounded tool_definitions fragment and §9's
    exposure targets. Required behavior: at the anchor's scale (290 tools, 10 real native tools
    from the merged tree plus integration-scale entries), the per-turn visible tool set and the
    serialized catalog's token cost stay bounded instead of growing with the connected catalog.
    The bounds below are the ADR's §9 anchors, not measured targets: S5/S10 own establishing the
    measured numbers ("measurements first, no invented results"); this skeleton pins the bounded
    property itself.
    """
    clear_plan_cache()
    catalog = build_tools(["files", "documents", "memory", "shell", "web_fetch"], None)
    assert len(catalog) == 10, "the real native registry is the base of the scaled catalog"

    class IntegrationScaleTool(Tool):
        """A realistic integration tool at the shape integration manifests actually ship."""

        def __init__(self, name: str):
            self.name = name
            self.description = ("Integration tool " + name + ": searches the connected acme "
                                "workspace and returns structured results with snippets, "
                                "permissions and provenance metadata for the calling agent. "
                                "Supports filters, pagination, and field selection; results are "
                                "capped and rate-limited per connection. " ) * 2
            self.parameters = {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query text."},
                    "filters": {"type": "object", "description": "Facets to narrow the search.",
                                "properties": {"space": {"type": "string"},
                                               "author": {"type": "string"},
                                               "updated_after": {"type": "string"}}},
                    "page": {"type": "integer", "description": "Zero-based page number."},
                    "page_size": {"type": "integer", "description": "Results per page (1-100)."},
                    "sort": {"type": "string", "enum": ["relevance", "updated", "created"],
                             "description": "Result ordering."},
                    "fields": {"type": "array", "items": {"type": "string"},
                               "description": "Projection of returned fields."},
                    "include_snippets": {"type": "boolean",
                                         "description": "Attach highlighted snippets."},
                    "workspace": {"type": "string", "description": "Bound workspace id."},
                    "trace": {"type": "string", "description": "Caller trace correlation id."},
                },
                "required": ["query"],
            }

        def run(self, args, ctx):
            return ToolResult(ok=True, output="ok")

    for i in range(280):
        catalog[f"acme_integration_tool_{i:03d}"] = IntegrationScaleTool(f"acme_integration_tool_{i:03d}")
    assert len(catalog) == 290, "the scenario reproduces the #35376 anchor scale of ~290 tools"

    profile = resolve_profile(provider="ollama", model="fake:8b")
    plan = compile_plan(tools=catalog, profile=profile, strategy="native")
    visible = list(plan.wire_tools)

    # (c) per-turn visible tools cap, anchor ~20 past which lazy exposure is recommended (§9).
    assert len(visible) <= 20, f"{len(visible)} tools are offered to the model in one turn; the " \
                               "catalog must be bounded (manifest-first / progressive exposure)"
    # (a)+(b) the serialized catalog's context cost stays a bounded fragment, not 40-70k tokens.
    _, tool_tokens = prompt_tokens([{"role": "user", "content": "task"}], visible)
    assert tool_tokens <= 800, f"the tool catalog alone costs {tool_tokens:,} estimated tokens; " \
                               "the manifest must stay a bounded fragment (opencode#35376)"


# ==================================================================== NotebookLM-plane regressions
# ADR-0017 assigns both to S7 (NotebookLM sync; §5 S7, §10 rows "Notebook source lifecycle" and
# "Authentication boundaries"). The integration does not exist yet (ADR-0017 §2.2), so the
# skeletons pin the S7 contracts at the real seams that already exist: the persisted ConnectionBook
# state and the provider acquisition path for the auth contract, and the immutable action-receipt
# bracket (store.begin_action/finish_action via runtime.steps) for the read-back contract.


@pytest.mark.xfail(strict=True, reason="ADR-0017 S7")
def test_auth_recovery_rereads_persisted_connection_state(store, config, tmp_path, oai, monkeypatch):
    """notebooklm-py#2161: long-lived sessions loop on auth because recovery never re-reads the
    persisted connection state, and nothing guards a refresh race.

    ADR-0017 §5 S7 fixes this ("auth loss mid-upload ... -> reconcile, never assume") and the §10
    "Authentication boundaries" row pins the contract: "expired credentials -> honest failure (no
    loop, no empty-success); refresh race guarded by generation/CAS on persisted state (#2161
    lesson)". Required behavior: (a) recovery re-reads the persisted credential instead of
    replaying the stale session, and (b) every persisted rotation bumps a generation marker on the
    persisted connection row so a refresh race is CAS-guarded and recovery is bounded, never an
    endless loop.
    """
    monkeypatch.delenv("CUSTOM_API_KEY", raising=False)   # the persisted key file is authoritative
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", "acme", base_url=oai.url + "/v1", title="Acme")
    book.set_key("acme", "key-v1")

    bot = Bot(name="s0-auth", model="acme/fake-model", tools=[], selfcheck=False)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="ping")
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda ev: None, poll_seconds=0.05)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                      workspace=ws, emit=lambda ev: None)
    rt = BuiltinRuntime(hardware=BIG_BOX, sleep=lambda s: None)
    ladder = Ladder(bot)
    rung = ladder.primary

    def acquire_and_call() -> str:
        provider = rt._provider_for(ctx, ladder, rung, book=book)
        result = provider.chat(ChatRequest(model="fake-model",
                                           messages=[{"role": "user", "content": "ping"}],
                                           stream=False, max_tokens=16, think=False))
        return result.content

    oai.require_key = "key-v1"
    assert acquire_and_call() == "ok", "the long-lived session starts authenticated"

    # The credential expires; recovery persists a fresh one (the #2161 loop scenario).
    oai.require_key = "key-v2"
    book.set_key("acme", "key-v2")

    # (a) re-read of persisted state, this half holds today via the per-acquisition credential
    # fingerprint (builtin.py:245-251) and is recorded as a surprise, not faked into a failure.
    assert acquire_and_call() == "ok", "recovery must re-read the persisted credential"
    sent = oai.of("/v1/chat/completions")
    assert sent[-1]["headers"]["authorization"] == "Bearer key-v2"

    # (b) the missing half (today's red): the persisted connection row carries no generation/CAS
    # marker, so a refresh race has nothing to CAS against and recovery cannot be bounded by
    # state. ADR-0017 §10 requires the guard on persisted state; `auth_generation` is the
    # skeleton's pin for it, S7 renames the assertion if the landed schema chooses another name.
    row = json.loads(book.path.read_text())["connections"]["acme"]
    assert isinstance(row.get("auth_generation"), int), "each persisted rotation must bump a " \
        "generation marker on the persisted connection row (generation/CAS guard, #2161 lesson)"
    book.set_key("acme", "key-v3")
    row_after = json.loads(book.path.read_text())["connections"]["acme"]
    assert row_after["auth_generation"] > row["auth_generation"], "generations are monotonic"


@pytest.mark.xfail(strict=True, reason="ADR-0017 S7")
def test_external_success_requires_read_back_evidence(store, config, tmp_path):
    """False-sync/false-generation guard: no success is reported without a live probe/read-back.

    ADR-0017 §5 S7 fixes this for sync: the non-destructive workflow ends in "verify via
    sources.get metadata read-back (batchDelete returns {} even for missing names, verify by
    re-get)", the brief (Appendix A §6) adds "Do not mark a source synced merely because bytes were
    accepted", §4.3 adds "A provider job id or URL is never reported as a completed artifact", and
    §11 bars declaring success "from tool discovery, valid JSON, ... a connected badge, ... or
    passing mocks alone". (S8 mirrors the same guard for media generation.) Required behavior: an
    outward, billable external operation must not be sealed as a plain "done" receipt from its
    self-report alone, the receipt must carry read-back verification evidence of the remote state.
    """
    bot = Bot(name="s0-sync", model="mock/demo", tools=[], selfcheck=False)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="sync the quarterly sources to the team notebook")
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda ev: None, poll_seconds=0.05)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                      workspace=ws, emit=lambda ev: None)

    class NotebookSyncTool(Tool):
        """Stands in for the S7 sync tool: an outward operation that self-reports success."""

        name = "notebook_sync"
        description = "Upload selected sources to the connected notebook (external operation)."
        parameters = {"type": "object",
                      "properties": {"notebook": {"type": "string"}},
                      "required": ["notebook"]}

        def effect(self, args, ctx):
            return "web"                       # outward effect class: the receipt bracket applies

        def run(self, args, ctx):
            if ctx.begin_effect() is not None:
                return ToolResult(ok=False, output="the action could not be recorded")
            # The upstream accepted the bytes and returned a job id, but nothing has read the
            # remote state back. Ingestion may still be pending or failed upstream.
            return ToolResult(ok=True, output=f"accepted by notebook {args['notebook']} "
                                              "(job nb-job-0001)")

    result = call_tool(run, ctx, {"notebook_sync": NotebookSyncTool()}, "notebook_sync",
                       {"notebook": "nb-88"})
    assert result.ok, "the external operation really ran through the real receipt bracket"
    actions = store.list_actions(run.id)
    assert len(actions) == 1 and actions[0]["effect"] == "web"

    row = store.get_action(actions[0]["id"])
    assert row is not None and row["status"] == "done", \
        "today's behavior, recorded as the baseline: the self-reported success is sealed " \
        "'done' with no read-back (steps.py:199-210)"

    # The missing half (today's red): the receipt exposes no read-back verification evidence, so
    # a pending/failed ingestion upstream would already be reported to the operator as a success.
    # `verification.read_back` is the skeleton's pin for the S7 contract; S7 renames the assertion
    # if the landed receipt schema chooses another name.
    verification = row.get("verification")
    assert isinstance(verification, dict) and verification.get("read_back"), \
        "an outward success must carry live read-back evidence before it is reported as " \
        "complete (false-sync guard, ADR-0017 §5 S7 / §4.3)"
