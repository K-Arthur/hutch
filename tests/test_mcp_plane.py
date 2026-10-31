"""The governed MCP plane: definition review, discovery, grants and the real contained transport.

The last group of tests launches an actual MCP server process through Hutch's sandbox and speaks
the protocol to it. They are the ones that would catch a launcher that stopped working, which a
pure unit test cannot.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from hutch.integrations.base import canonical_tool_name
from hutch.integrations.mcp import config, discovery, network, persistence, service
from hutch.integrations.mcp.tool import McpToolAdapter, construct_mcp_tools
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.approvals import ApprovalGate
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"


# --------------------------------------------------------------------------- definition review


def _python() -> str:
    return "/usr/bin/python3"


@pytest.mark.parametrize("raw, message", [
    ({"transport": "mcp_stdio", "command": "python3 -c 'import os'"}, "could not be resolved"),
    ({"transport": "mcp_stdio", "command": ""}, "needs an executable path"),
])
def test_a_definition_that_is_not_an_argv_is_refused(raw, message):
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_stdio_definition(raw)
    assert message in str(exc.value)


def test_credential_shaped_flags_cannot_be_stored_in_a_command_line():
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_stdio_definition(
            {"transport": "mcp_stdio", "command": _python(), "args": ["--api-key=abc123"]})
    assert "credential" in str(exc.value)


def test_a_literal_secret_value_is_refused_where_a_reference_is_required():
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_stdio_definition(
            {"transport": "mcp_stdio", "command": _python(),
             "env": {"SERVICE_API_TOKEN": "literal-value"}})
    assert "from_env" in str(exc.value)


def test_a_non_secret_literal_environment_value_is_allowed():
    normalized = config.validate_stdio_definition(
        {"transport": "mcp_stdio", "command": _python(), "env": {"LOG_LEVEL": "debug"}})
    assert normalized["env"] == {"LOG_LEVEL": "literal:debug"}


def test_home_and_state_directories_cannot_be_mounted_into_a_server():
    for path in (str(Path.home()), "/"):
        with pytest.raises(config.McpConfigurationError):
            config.validate_stdio_definition(
                {"transport": "mcp_stdio", "command": _python(), "read_only_paths": [path]})


def test_a_plaintext_remote_endpoint_is_refused():
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_http_definition({"transport": "mcp_http", "url": "http://mcp.example.com/mcp"})
    assert "loopback" in str(exc.value)


def test_an_endpoint_with_embedded_credentials_is_refused():
    with pytest.raises(config.McpConfigurationError):
        config.validate_http_definition(
            {"transport": "mcp_http", "url": "https://user:pw@mcp.example.com/mcp"})


def test_bearer_auth_must_name_an_environment_reference():
    with pytest.raises(config.McpConfigurationError):
        config.validate_http_definition(
            {"transport": "mcp_http", "url": "https://mcp.example.com/mcp",
             "auth": {"type": "bearer", "token": "secret"}})
    normalized = config.validate_http_definition(
        {"transport": "mcp_http", "url": "https://mcp.example.com/mcp",
         "auth": {"type": "bearer", "from_env": "MCP_TOKEN"}})
    assert normalized["auth"] == {"type": "bearer", "from_env": "MCP_TOKEN"}


def test_a_missing_credential_reference_fails_closed(monkeypatch):
    monkeypatch.delenv("HUTCH_TEST_ABSENT_TOKEN", raising=False)
    with pytest.raises(config.McpConfigurationError) as exc:
        config.resolve_environment({"env": {"TOKEN": "env:HUTCH_TEST_ABSENT_TOKEN"}})
    assert "not set" in str(exc.value)


# --------------------------------------------------------------------------- endpoint screening


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/mcp",
    "http://localhost:9000/mcp",
])
def test_loopback_plaintext_endpoints_are_acceptable(url):
    assert network.validate_mcp_endpoint(url, resolver=lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])


def test_a_remote_hostname_resolving_to_a_private_address_is_refused():
    with pytest.raises(network.McpEndpointError) as exc:
        network.validate_mcp_endpoint(
            "https://intranet.example.com/mcp",
            resolver=lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 0))])
    assert "private" in str(exc.value)


def test_a_loopback_hostname_resolving_off_loopback_is_refused():
    with pytest.raises(network.McpEndpointError):
        network.validate_mcp_endpoint(
            "http://localhost:8080/mcp",
            resolver=lambda *a, **k: [(2, 1, 6, "", ("203.0.113.9", 0))])


def test_an_unreviewed_loopback_origin_is_refused_by_the_pinned_transport():
    """A local endpoint must match the reviewed origin exactly, not merely be local.

    Screening the URL once is not enough: a request is only allowed if its origin is one the
    owner reviewed. Without this, a definition reviewed for one local port could be redirected
    by the server to any other service on the machine.
    """
    import asyncio
    import httpx2

    transport = network.PinnedMcpHTTPTransport(
        allowed_local_origins=("http://127.0.0.1:9999/mcp",),
        transport_factory=lambda: httpx2.AsyncHTTPTransport(trust_env=False))

    async def attempt(url: str) -> str:
        request = httpx2.Request("POST", url, content=b"{}")
        try:
            await transport.handle_async_request(request)
        except network.McpEndpointError as exc:
            return str(exc)
        return ""

    refused = asyncio.run(attempt("http://127.0.0.1:8888/mcp"))
    assert "reviewed endpoint" in refused


def test_a_public_endpoint_is_refused_without_https():
    """Pinning never widens the scheme rule: a non-TLS public endpoint is refused outright."""
    import asyncio
    import httpx2

    transport = network.PinnedMcpHTTPTransport(
        resolver=lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
        transport_factory=lambda: httpx2.AsyncHTTPTransport(trust_env=False))

    async def attempt() -> str:
        request = httpx2.Request("POST", "http://example.com/mcp", content=b"{}")
        try:
            await transport.handle_async_request(request)
        except network.McpEndpointError as exc:
            return str(exc)
        return ""

    assert "allowed public HTTPS address" in asyncio.run(attempt())


def test_an_endpoint_with_a_query_string_is_refused():
    with pytest.raises(network.McpEndpointError):
        network.validate_mcp_endpoint("https://mcp.example.com/mcp?token=x",
                                      resolver=lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])


# --------------------------------------------------------------------------- catalog normalization


def _tool(name="search", **overrides):
    raw = {"name": name, "description": "Find things", "inputSchema": {
        "type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}
    raw.update(overrides)
    return raw


def test_normalization_namespaces_and_digests_a_tool():
    [item] = discovery.normalize_mcp_tools("acme", [_tool()])
    assert item["canonical_name"] == canonical_tool_name("acme", "search")
    assert item["supported"] is True and len(item["schema_revision"]) == 64


def test_server_annotations_never_classify_a_tool():
    [item] = discovery.normalize_mcp_tools("acme", [_tool(annotations={"readOnlyHint": True})])
    assert item["annotations"]["readOnlyHint"] is True  # kept as display evidence
    # ...and the evidence is not authority: the adapter still defaults to approval-required.
    adapter = McpToolAdapter(integration_id="acme", server_tool_name="search",
                             canonical_name=item["canonical_name"], schema_revision=item["schema_revision"],
                             input_schema=item["input_schema"], description=item["description"],
                             operation_class="unknown", definition={"transport": "mcp_stdio"})
    assert adapter.effect({}, None) == "process"


def test_schema_samples_are_stripped_so_a_default_never_becomes_an_argument():
    raw = _tool(inputSchema={"type": "object", "properties": {
        "q": {"type": "string", "default": "cats", "examples": ["dogs"]}}})
    [item] = discovery.normalize_mcp_tools("acme", [raw])
    assert "default" not in item["input_schema"]["properties"]["q"]
    assert "examples" not in item["input_schema"]["properties"]["q"]


def test_an_uncertifiable_schema_is_kept_but_marked_unsupported():
    raw = _tool(inputSchema={"type": "object", "properties": {"q": {"type": "string"}},
                             "patternProperties": {"^x": {"type": "string"}}})
    [item] = discovery.normalize_mcp_tools("acme", [raw])
    assert item["supported"] is False and item["diagnostics"]


def test_a_schema_root_that_is_not_an_object_is_unsupported():
    [item] = discovery.normalize_mcp_tools("acme", [_tool(inputSchema={"type": "string"})])
    assert item["supported"] is False


def test_duplicate_tool_names_refuse_the_whole_catalog():
    with pytest.raises(discovery.McpToolSchemaError):
        discovery.normalize_mcp_tools("acme", [_tool(), _tool()])


def test_oversized_catalogs_are_refused():
    with pytest.raises(discovery.McpToolSchemaError):
        discovery.normalize_mcp_tools("acme", [_tool(f"t{i}") for i in range(201)])


# --------------------------------------------------------------------------- persistence rules


def _definition(tmp_path):
    return config.validate_stdio_definition(
        {"transport": "mcp_stdio", "command": _python(), "args": [str(FIXTURE)]})


def test_saving_a_changed_definition_withdraws_authority(store, tmp_path):
    definition = _definition(tmp_path)
    revision = config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
    assert persistence.definition_for(store._db, "acme")["state"] == "installed"

    other = config.definition_revision({**definition, "args": ["other"]})
    with store._tx() as db:
        result = persistence.save_definition(db, integration_id="acme", title="Acme",
                                             definition={**definition, "args": ["other"]}, revision=other)
    assert result["invalidated"] is True
    assert persistence.definition_for(store._db, "acme")["enabled"] is False


def test_a_catalog_refresh_invalidates_grants_whose_schema_changed(store):
    bot = store.create_bot(Bot(name="mcp-bot", model="mock/demo", tools=[]))
    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [tool_one] = discovery.normalize_mcp_tools("acme", [_tool()])
        persistence.save_catalog(db, "acme", [tool_one])
        persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                operation_classes={"search": "read"}, expected_revision=revision)
    assert store.integration_tool_granted(bot.id, "acme", "search")

    # The server now describes the same tool differently.
    changed = _tool(description="Find even more things")
    [tool_changed] = discovery.normalize_mcp_tools("acme", [changed])
    with store._tx() as db:
        result = persistence.save_catalog(db, "acme", [tool_changed])

    assert result["invalidated"] == ["search"]
    assert not store.integration_tool_granted(bot.id, "acme", "search")


def test_a_grant_cannot_name_a_tool_outside_the_reviewed_catalog(store):
    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = config.definition_revision(definition)
    bot = store.create_bot(Bot(name="b", model="mock/demo", tools=[]))
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [tool_one] = discovery.normalize_mcp_tools("acme", [_tool()])
        persistence.save_catalog(db, "acme", [tool_one])
    with pytest.raises(persistence.McpStoreError):
        with store._tx() as db:
            persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["exfiltrate"],
                                    operation_classes={}, expected_revision=revision)


def test_an_unsupported_tool_cannot_be_granted(store):
    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = config.definition_revision(definition)
    bot = store.create_bot(Bot(name="b", model="mock/demo", tools=[]))
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [bad] = discovery.normalize_mcp_tools("acme", [_tool(
            inputSchema={"type": "string"})])
        persistence.save_catalog(db, "acme", [bad])
    assert bad["supported"] is False
    with pytest.raises(persistence.McpStoreError):
        with store._tx() as db:
            persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                    operation_classes={}, expected_revision=revision)


def test_removing_a_server_removes_every_grant(store):
    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = config.definition_revision(definition)
    bot = store.create_bot(Bot(name="b", model="mock/demo", tools=[]))
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [tool_one] = discovery.normalize_mcp_tools("acme", [_tool()])
        persistence.save_catalog(db, "acme", [tool_one])
        persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                operation_classes={"search": "read"}, expected_revision=revision)
    with store._tx() as db:
        persistence.delete_server(db, "acme")
    assert persistence.definition_for(store._db, "acme") is None
    assert not store.integration_tool_granted(bot.id, "acme", "search")


def test_revoking_one_assistant_leaves_others_intact(store):
    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = config.definition_revision(definition)
    first = store.create_bot(Bot(name="one", model="mock/demo", tools=[]))
    second = store.create_bot(Bot(name="two", model="mock/demo", tools=[]))
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [tool_one] = discovery.normalize_mcp_tools("acme", [_tool()])
        persistence.save_catalog(db, "acme", [tool_one])
        for bot in (first, second):
            persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                    operation_classes={"search": "read"}, expected_revision=revision)
    with store._tx() as db:
        result = persistence.revoke_tools(db, integration_id="acme", bot_id=first.id)
    assert result["remaining_grants"] == 1
    assert not store.integration_tool_granted(first.id, "acme", "search")
    assert store.integration_tool_granted(second.id, "acme", "search")


# --------------------------------------------------------------------------- readiness


def test_readiness_separates_granted_connector_tools_from_installed_ones(store, config):
    """An assistant's readiness names what it may call, and what exists but was never granted."""
    from hutch.readiness import bot_readiness
    from hutch.integrations.mcp import config as mcp_config

    bot = store.create_bot(Bot(name="readiness-bot", model="mock/demo", tools=[],
                               approval_mode=ApprovalMode.auto))
    report = bot_readiness(store, config, bot)
    area = next(a for a in report["areas"] if a["id"] == "connectors")
    assert area["status"] == "ok"
    assert area["items"][0]["detail"] == "no connectors installed or granted"

    definition = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
                  "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}
    revision = mcp_config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [tool_one] = discovery.normalize_mcp_tools("acme", [_tool()])
        persistence.save_catalog(db, "acme", [tool_one])

    report = bot_readiness(store, config, bot)
    area = next(a for a in report["areas"] if a["id"] == "connectors")
    assert "installed but not granted to this assistant: Acme" in area["items"][0]["detail"]

    with store._tx() as db:
        persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                operation_classes={"search": "read"}, expected_revision=revision)
    report = bot_readiness(store, config, bot)
    area = next(a for a in report["areas"] if a["id"] == "connectors")
    by_name = {item["name"]: item for item in area["items"]}
    assert by_name["mcp__acme__search"]["status"] == "ok"
    assert "read effect" in by_name["mcp__acme__search"]["detail"]
