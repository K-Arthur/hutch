"""ADR-0017 S1: shared contracts and the single derived tool catalog.

Covers the slice's additions: the v1 capability snapshot stays byte-stable for existing bots while
gaining only optional keys (``integration_tools``), the four tool enumerations derive from
``hutch.integrations.catalog``, the integrations tables ship empty and disabled (schema v73), and
the S0 reconciliation's single endpoint-derivation chain is shared by route identity and
capability resolution.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from hutch.engine import Engine
from hutch.integrations.base import (Integration, IntegrationState, IntegrationTransport,
                                     canonical_tool_name, validate_integration_id)
from hutch.integrations.catalog import (BROWSER_TOOL_NAME, CONNECTION_TOOL_SPECS,
                                        OFFLINE_WITHHELD_TOOLS, SNAPSHOT_OFFLINE_WITHHELD_TOOLS,
                                        available_connection_services, construct_connection_tools,
                                        is_known_tool_name, known_tool_names, offline_withheld,
                                        snapshot_tool_names)
from hutch.models import ApprovalMode, Bot, InferenceMode, Run
from hutch.providers.registry import resolve_route_endpoint
from hutch.readiness import bot_readiness
from hutch.store import SCHEMA_VERSION, _migrate_73
from hutch.tools import build_tools, expand_tools
from hutch.tools.base import ToolContext

GOLDEN_BOT_ID = "bot_goldens1fixed000000000"


def golden_bot(**updates) -> Bot:
    bot = Bot(id=GOLDEN_BOT_ID, name="golden-bot", model="ollama/fake:8b", instructions="Be careful.",
              description="A golden test bot", tools=["files", "memory", "shell", "browser", "web_fetch"],
              approval_mode=ApprovalMode.auto)
    return bot.model_copy(update=updates) if updates else bot


# =============================================================================== golden snapshot
# Recorded from the pre-S1 tree (the S1 baseline): json.dumps(snapshot, sort_keys=True,
# separators=(",", ":")) for the three bot shapes below. S1's catalog derivation and the additive
# integration_tools key must leave these byte-identical (ADR-0017 §5 S1: "golden snapshot test
# asserting the v1 snapshot is unchanged for existing bots").

GOLDEN_HYBRID = ('{"approval_mode":"auto","base_url_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",'
                 '"bot_id":"bot_goldens1fixed000000000","browser_handoff":false,"command_rules":[],'
                 '"description_sha256":"f312b0092864238c19e45189d1b5ae147625479efffa970d4f3a6481d28d0d8b","escalation":null,'
                 '"fallbacks":[],"inference_mode":"hybrid","instructions_sha256":"489fb53a49997003c69fb9dce959bf0e843ba893a51a658e95ad4bb1fee0abbd",'
                 '"limits":{"daily_cost_cap_usd":0.0,"daily_token_cap":200000,"max_cost_usd":0.0,"max_steps":24,"max_turn_tokens":0,"timeout_seconds":900},'
                 '"memory_enabled":true,"model":"ollama/fake:8b","num_ctx":null,"risk_tier":"supervised","runtime":"builtin","sandbox":"strict",'
                 '"selfcheck":true,"shell_network":false,"skills":[],"snapshot_version":1,"think":null,"tool_limits":{},'
                 '"tools":["browser","list_files","read_file","recall","remember","shell","web_fetch","write_file"],'
                 '"workdir_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","workspace_mode":"fresh"}')

GOLDEN_OFFLINE = ('{"approval_mode":"auto","base_url_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",'
                  '"bot_id":"bot_goldens1fixed000000000","browser_handoff":false,"command_rules":[],'
                  '"description_sha256":"f312b0092864238c19e45189d1b5ae147625479efffa970d4f3a6481d28d0d8b","escalation":null,'
                  '"fallbacks":[],"inference_mode":"offline","instructions_sha256":"489fb53a49997003c69fb9dce959bf0e843ba893a51a658e95ad4bb1fee0abbd",'
                  '"limits":{"daily_cost_cap_usd":0.0,"daily_token_cap":200000,"max_cost_usd":0.0,"max_steps":24,"max_turn_tokens":0,"timeout_seconds":900},'
                  '"memory_enabled":true,"model":"ollama/fake:8b","num_ctx":null,"risk_tier":"supervised","runtime":"builtin","sandbox":"strict",'
                  '"selfcheck":true,"shell_network":false,"skills":[],"snapshot_version":1,"think":null,"tool_limits":{},'
                  '"tools":["list_files","read_file","recall","remember","shell","write_file"],'
                  '"workdir_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","workspace_mode":"fresh"}')

GOLDEN_TOOL_FREE = ('{"approval_mode":"auto","base_url_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",'
                    '"bot_id":"bot_goldens1fixed000000000","browser_handoff":false,"command_rules":[],'
                    '"description_sha256":"f312b0092864238c19e45189d1b5ae147625479efffa970d4f3a6481d28d0d8b","escalation":null,'
                    '"execution_purpose":"conversation",'
                    '"fallbacks":[],"inference_mode":"hybrid","instructions_sha256":"489fb53a49997003c69fb9dce959bf0e843ba893a51a658e95ad4bb1fee0abbd",'
                    '"limits":{"daily_cost_cap_usd":0.0,"daily_token_cap":200000,"max_cost_usd":0.0,"max_steps":24,"max_turn_tokens":0,"timeout_seconds":900},'
                    '"memory_enabled":false,"model":"ollama/fake:8b","num_ctx":null,"risk_tier":"supervised","runtime":"builtin","sandbox":"strict",'
                    '"selfcheck":true,"shell_network":false,"skills":[],"snapshot_version":1,"think":null,"tool_access":"none","tool_limits":{},'
                    '"tools":[],"workdir_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","workspace_mode":"fresh"}')


def _canonical(snapshot: dict) -> str:
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"))


def test_capability_snapshot_v1_is_byte_stable_for_existing_bots():
    assert _canonical(Engine.capability_snapshot(golden_bot())) == GOLDEN_HYBRID
    assert _canonical(Engine.capability_snapshot(
        golden_bot(inference_mode=InferenceMode.offline))) == GOLDEN_OFFLINE
    assert _canonical(Engine.capability_snapshot(golden_bot(), "none", "conversation")) == GOLDEN_TOOL_FREE


def test_capability_snapshot_extension_is_additive_under_v1(store):
    """integration_tools is optional: present only when grants exist, version stays 1, and the
    delegation admission gate (which hard-rejects any other version) still accepts the snapshot."""
    bot = golden_bot()
    store.create_bot(bot)
    assert "integration_tools" not in Engine.capability_snapshot(bot)
    with store._tx() as db:
        db.execute("INSERT INTO integrations (integration_id, revision, transport, created_at) "
                   "VALUES ('notebooklm', 'rev-1', 'in_process', '2026-10-11T00:00:00Z')")
        db.execute("INSERT INTO integration_tool_grants (integration_id, bot_id, server_tool_name, "
                   "canonical_name, schema_revision, granted_at) VALUES "
                   "('notebooklm', ?, 'search', 'mcp__notebooklm__search', ?, '2026-10-11T00:00:00Z')",
                   (bot.id, "a" * 64))
        db.execute("INSERT INTO integration_tool_grants (integration_id, bot_id, server_tool_name, "
                   "canonical_name, schema_revision, granted_at) VALUES "
                   "('notebooklm', ?, 'ingest', 'mcp__notebooklm__ingest', '', '2026-10-11T00:00:00Z')",
                   (bot.id,))
    assert store.integration_tool_names(bot.id) == []  # disabled integration authority stays out of snapshots
    with store._tx() as db:
        db.execute("UPDATE integrations SET enabled=1, state='operation_authorized' "
                   "WHERE integration_id='notebooklm'")
    assert store.integration_tool_names(bot.id) == ["mcp__notebooklm__ingest", "mcp__notebooklm__search"]

    snapshot = Engine.capability_snapshot(bot, integration_tools=store.integration_tool_names(bot.id))
    assert snapshot["snapshot_version"] == 1
    assert snapshot["integration_tools"] == ["mcp__notebooklm__ingest", "mcp__notebooklm__search"]
    # the delegation admission gate still accepts it (engine._delegated_bot pins version 1)
    delegated = Engine._delegated_bot(bot.model_copy(update={"inference_mode": InferenceMode.offline}),
                                      Engine.capability_snapshot(
                                          golden_bot(inference_mode=InferenceMode.offline),
                                          integration_tools=store.integration_tool_names(bot.id)))
    assert delegated.model == "ollama/fake:8b"
    # tool-free runs record no tools at all, integration ones included
    assert "integration_tools" not in Engine.capability_snapshot(
        bot, "none", "conversation", integration_tools=store.integration_tool_names(bot.id))


# ================================================================================ catalog contract

def test_offline_withheld_list_is_the_single_source():
    assert OFFLINE_WITHHELD_TOOLS == frozenset({
        "web_fetch", "browser", "computer", "live_search", "render_audio_overview", "run_workspace_plan",
        "google_calendar_events", "google_calendar_create_event", "google_mail_search", "google_mail_send",
        "outlook_calendar_events", "outlook_calendar_create_event", "outlook_mail_search", "outlook_mail_send"})
    assert offline_withheld(["web_fetch", "shell", "browser"]) == ["web_fetch", "browser"]
    assert SNAPSHOT_OFFLINE_WITHHELD_TOOLS == frozenset({"web_fetch", "browser"}), \
        "the snapshot's narrower set is deliberate and pinned byte-stable under v1"


def test_build_tools_withholds_exactly_the_catalog_list(store, config, tmp_path):
    bot = Bot(name="offline-withheld", model="ollama/fake:8b", inference_mode=InferenceMode.offline,
              tools=["shell", "files", "web_fetch", "browser", "documents"], approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="x")
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=None, gate=None, config=config, workspace=ws)
    tools = build_tools(bot.tools, ctx)
    assert set(tools).isdisjoint(OFFLINE_WITHHELD_TOOLS)
    assert {"shell", "read_file", "list_files", "write_file"} <= set(tools)


def test_known_tool_names_cover_the_browser_and_groups():
    assert BROWSER_TOOL_NAME == "browser"
    known = known_tool_names()
    assert {"browser", "shell", "web_fetch", "remember", "recall", "create_document",
            "run_python", "plan_workspace_action", "google_calendar_events"} <= known
    assert is_known_tool_name("browser") and is_known_tool_name("write_file")
    assert not is_known_tool_name("totally_unknown_tool")
    assert not is_known_tool_name("")


def test_connection_tools_are_constructed_from_the_catalog(store):
    bot = Bot(name="granted-bot", model="ollama/fake:8b", tools=["files"], approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    assert construct_connection_tools(store, bot) == {}

    store.set_google_calendar_grant(bot.id, "account-a", "primary", "Personal")
    # the read grant alone yields the events tool but not event creation
    tools = construct_connection_tools(store, bot)
    assert set(tools) == {"google_calendar_events"}

    store.set_google_calendar_grant(bot.id, "account-a", "primary", "Personal", allow_event_creation=True)
    tools = construct_connection_tools(store, bot)
    assert set(tools) == {"google_calendar_events", "google_calendar_create_event"}

    store.set_outlook_calendar_grant(bot.id, "account-b", "cal-b", "Work")
    store.set_outlook_mail_send_grant(bot.id, "account-c", "Work sender")
    tools = construct_connection_tools(store, bot)
    assert set(tools) == {"google_calendar_events", "google_calendar_create_event",
                          "outlook_calendar_events", "outlook_mail_send"}

    # revoking a grant removes exactly its tool at build_tools time (memory re-check precedent)
    assert store.remove_outlook_mail_send_grant(bot.id)
    tools = construct_connection_tools(store, bot)
    assert "outlook_mail_send" not in tools
    # local-only tools need the caller's local-gmail eligibility, not just a grant
    store.set_google_mail_grant(bot.id, "account-d")
    assert construct_connection_tools(store, bot, local_gmail_ok=False).keys() >= {"google_calendar_events"}
    assert "google_mail_search" not in construct_connection_tools(store, bot, local_gmail_ok=False)


def test_build_tools_constructs_the_same_grant_tools_in_the_same_order(store, config, tmp_path):
    bot = Bot(name="grant-order", model="ollama/fake:8b", tools=["files"], approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    store.set_google_calendar_grant(bot.id, "account-a", "primary", "Personal")
    store.set_outlook_calendar_grant(bot.id, "account-b", "cal-b", "Work")
    store.set_outlook_mail_grant(bot.id, "account-c")
    run = Run(bot_id=bot.id, prompt="x")
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=None, gate=None, config=config, workspace=ws)
    tools = build_tools(bot.tools, ctx)
    granted = [name for name in tools if name in {spec.name for spec in CONNECTION_TOOL_SPECS}]
    assert granted == ["google_calendar_events", "outlook_calendar_events", "outlook_mail_search"]
    assert [spec.name for spec in CONNECTION_TOOL_SPECS][0] == "google_calendar_events"


def test_readiness_derives_from_the_catalog(store, config):
    bot = Bot(name="readiness-catalog", model="ollama/fake:8b", inference_mode=InferenceMode.offline,
              tools=["web_fetch", "browser", "shell", "google_calendar_events", "unknown_tool"],
              approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    report = bot_readiness(store, config, bot)
    tools_area = next(area for area in report["areas"] if area["id"] == "tools")
    by_name = {item["name"]: item for item in tools_area["items"]}
    assert by_name["web_fetch"]["detail"] == "withheld in Strict Offline mode"
    assert by_name["browser"]["detail"] == "withheld in Strict Offline mode"
    assert by_name["shell"]["status"] == "ok"
    assert by_name["unknown_tool"] == {"name": "unknown_tool", "status": "missing", "detail": "unknown tool name"}
    connections_area = next(area for area in report["areas"] if area["id"] == "connections")
    item = next(item for item in connections_area["items"] if item["name"] == "google_calendar_events")
    assert item["status"] == "missing" and "Google Calendar" in item["detail"]
    assert available_connection_services(store, bot) == set()


def test_connection_service_grants_follow_consent_fields(store):
    bot = Bot(name="consent-bot", model="ollama/fake:8b", tools=["files"], approval_mode=ApprovalMode.auto)
    store.create_bot(bot)
    store.set_google_calendar_grant(bot.id, "account-a", "primary", "Personal")
    assert available_connection_services(store, bot) == {"google-calendar"}
    store.set_google_calendar_grant(bot.id, "account-a", "primary", "Personal", allow_event_creation=True)
    assert available_connection_services(store, bot) == {"google-calendar", "google-calendar-write"}


# ============================================================================= identity contracts

def test_integration_identity_and_canonical_names_are_validated():
    assert canonical_tool_name("notebooklm", "search") == "mcp__notebooklm__search"
    with pytest.raises(ValueError):
        canonical_tool_name("Bad Slug", "search")
    with pytest.raises(ValueError):
        validate_integration_id("")
    integration = Integration(integration_id="notebooklm", revision="rev-1",
                              transport=IntegrationTransport.IN_PROCESS)
    assert integration.enabled is False                      # new authority ships disabled
    assert integration.state is IntegrationState.INSTALLED
    assert not integration.consent_reached(IntegrationState.AUTHENTICATED)
    assert Integration(integration_id="x", revision="r", transport=IntegrationTransport.MCP_HTTP,
                       state=IntegrationState.CAPABILITIES_DISCOVERED
                       ).consent_reached(IntegrationState.REACHABLE)


def test_snapshot_tool_names_matches_the_pinned_derivation():
    bot_tools = ["files", "memory", "shell", "browser", "web_fetch"]
    assert snapshot_tool_names(bot_tools, offline=False) == sorted(expand_tools(bot_tools))
    assert snapshot_tool_names(bot_tools, offline=True) == ["list_files", "read_file", "recall",
                                                            "remember", "shell", "write_file"]
    assert snapshot_tool_names(bot_tools, offline=True, tool_access="none") == []


# ================================================================================== schema v73

def test_v73_integration_tables_ship_empty_and_disabled():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO bots VALUES ('bot-a')")
        _migrate_73(db)
        _migrate_73(db)                                     # idempotent, like the grant migrations before it
        assert db.execute("SELECT COUNT(*) FROM integrations").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM integration_tool_grants").fetchone()[0] == 0
        columns = [row[1] for row in db.execute("PRAGMA table_info(integrations)")]
        assert columns == ["integration_id", "revision", "title", "transport", "credential_id",
                           "state", "enabled", "created_at"]
        db.execute("INSERT INTO integrations (integration_id, revision, transport, created_at) "
                   "VALUES ('notebooklm', 'rev-1', 'in_process', 'now')")
        row = db.execute("SELECT state, enabled FROM integrations WHERE integration_id='notebooklm'").fetchone()
        assert tuple(row) == ("installed", 0)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO integrations (integration_id, revision, transport, created_at) "
                       "VALUES ('x', 'r', 'carrier_pigeon', 'now')")       # transport vocabulary pinned
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute("INSERT INTO integration_tool_grants (integration_id, bot_id, server_tool_name, "
                       "canonical_name, granted_at) VALUES ('notebooklm', 'missing-bot', 'search', "
                       "'mcp__notebooklm__search', 'now')")
        db.execute("INSERT INTO integration_tool_grants (integration_id, bot_id, server_tool_name, "
                   "canonical_name, granted_at) VALUES ('notebooklm', 'bot-a', 'search', "
                   "'mcp__notebooklm__search', 'now')")
        db.execute("DELETE FROM bots WHERE id = 'bot-a'")
        assert db.execute("SELECT COUNT(*) FROM integration_tool_grants").fetchone()[0] == 0  # cascade
        assert SCHEMA_VERSION >= 73
    finally:
        db.close()


# ================================================== shared endpoint derivation (S0 reconciliation)

def test_resolve_route_endpoint_precedence(monkeypatch):
    for name in ("OLLAMA_HOST", "ANTHROPIC_BASE_URL", "HUTCH_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert resolve_route_endpoint("openai") == "https://api.openai.com/v1"
    assert resolve_route_endpoint("anthropic") == "https://api.anthropic.com"
    assert resolve_route_endpoint("ollama") == "http://localhost:11434"
    assert resolve_route_endpoint("openai-compatible") == ""
    assert resolve_route_endpoint("ollama", configured="http://127.0.0.1:9") == "http://127.0.0.1:9"
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert resolve_route_endpoint("ollama") == "http://localhost:11434"
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://relay.example.com")
    assert resolve_route_endpoint("anthropic") == "https://relay.example.com"
    monkeypatch.setenv("HUTCH_BASE_URL", "http://127.0.0.1:8080")
    assert resolve_route_endpoint("openai-compatible") == "http://127.0.0.1:8080"
    assert resolve_route_endpoint("anthropic", connection_endpoint="https://conn.example.com") == \
        "https://conn.example.com"
