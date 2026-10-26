"""Wire checks for the official MCP SDK behind Hutch's fixed, bounded transport."""
import json

import httpx
import pytest

from hutch.integrations.notion import ORIGIN, NotionError
from hutch.integrations.notion_mcp import NotionMCP, revision

SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}


class Book:
    def access_token(self, account):
        assert account == "fixture-account"
        return "PRIVATE-ACCESS-SENTINEL"


@pytest.fixture
def server():
    state = {"requests": [], "legacy": False, "schema": SCHEMA, "calls": 0, "sse": False, "deny": False, "token": "PRIVATE-ACCESS-SENTINEL"}
    async def handle(request):
        assert str(request.url) == ORIGIN + "/mcp"
        assert request.headers["authorization"] == "Bearer " + state["token"]
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(405)
        body = json.loads(request.content)
        state["requests"].append((dict(request.headers), body))
        method = body["method"]
        if state["deny"]:
            return httpx.Response(401, text="PRIVATE-ACCESS-SENTINEL")
        if method == "server/discover":
            if state["legacy"]:
                return httpx.Response(400, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "method not found"}})
            result = {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}, "resultType": "complete"}
        elif method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "Notion fixture", "version": "1"}}
        elif method == "notifications/initialized":
            return httpx.Response(202)
        elif method == "tools/list":
            result = {"tools": [
                {"name": "notion-search", "description": state.get("description", "Untrusted provider description"), "inputSchema": state["schema"]},
                {"name": "notion-delete-page", "inputSchema": SCHEMA},
                {"name": "notion-connector-search", "inputSchema": SCHEMA}]}
        elif method == "tools/call":
            state["calls"] += 1
            assert body["params"]["name"] == "notion-search"
            result = {"content": [{"type": "text", "text": state.get("text", "Untrusted fixture page results")}], "isError": False}
        else:
            raise AssertionError(method)
        if not state["legacy"]:
            result = {"ttlMs": 0, "cacheScope": "private", "resultType": "complete", **result}
        message = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if state["sse"] and method != "server/discover":
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="event: message\ndata: " + json.dumps(message) + "\n\n")
        return httpx.Response(200, json=message)
    return state, httpx.MockTransport(handle)


@pytest.mark.parametrize("legacy,sse", [(False, False), (True, False), (True, True)])
def test_discovery_and_read_use_sdk_wire_contract_without_exposing_other_tools(server, legacy, sse):
    state, transport = server
    state.update(legacy=legacy, sse=sse)
    client = NotionMCP(Book(), "fixture-account", transport=transport)
    discovery = client.discover()
    assert set(discovery["tools"]) == {"notion-search"}
    assert discovery["protocol"] == ("2025-06-18" if legacy else "2026-07-28")
    item = discovery["tools"]["notion-search"]
    allowed = []
    result = client.call("notion-search", {"query": "meeting notes"}, revision(item), before_call=lambda: allowed.append(True))
    assert result["ok"] and "fixture page" in result["output"]
    assert allowed == [True] and state["calls"] == 1
    if not legacy:
        for headers, body in state["requests"]:
            if body["method"] in {"tools/list", "tools/call"}:
                assert headers["mcp-protocol-version"] == "2026-07-28"
                assert body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"


def test_changed_schema_and_invalid_arguments_never_call_the_tool(server):
    state, transport = server
    client = NotionMCP(Book(), "fixture-account", transport=transport)
    item = client.discover()["tools"]["notion-search"]
    with pytest.raises(NotionError, match="arguments do not match"):
        client.call("notion-search", {}, revision(item))
    state["schema"] = {**SCHEMA, "description": "changed"}
    with pytest.raises(NotionError, match="definition changed"):
        client.call("notion-search", {"query": "x"}, revision(item))
    assert state["calls"] == 0


def test_revocation_checked_immediately_before_call_and_errors_never_expose_tokens(server):
    state, transport = server
    client = NotionMCP(Book(), "fixture-account", transport=transport)
    item = client.discover()["tools"]["notion-search"]
    def revoked():
        raise NotionError("grant revoked")
    with pytest.raises(NotionError, match="grant revoked"):
        client.call("notion-search", {"query": "x"}, revision(item), before_call=revoked)
    assert state["calls"] == 0
    state["deny"] = True
    with pytest.raises(NotionError) as error:
        client.discover()
    assert "PRIVATE-ACCESS-SENTINEL" not in str(error.value)
    with pytest.raises(NotionError, match="only reviewed search and fetch"):
        client.call("notion-delete-page", {}, "anything")


def test_response_bytes_are_bounded_and_redirects_never_reach_another_origin():
    from hutch.integrations.notion_mcp import MAX_BYTES
    seen = []
    async def oversized(request):
        seen.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"x" * (MAX_BYTES + 1))
    with pytest.raises(NotionError):
        NotionMCP(Book(), "fixture-account", transport=httpx.MockTransport(oversized)).discover()
    assert set(seen) == {ORIGIN + "/mcp"}
    seen.clear()
    async def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://attacker.example/mcp"})
    with pytest.raises(NotionError):
        NotionMCP(Book(), "fixture-account", transport=httpx.MockTransport(redirect)).discover()
    assert set(seen) == {ORIGIN + "/mcp"}


def test_cancelled_read_closes_without_waiting_for_network_timeout(server):
    import threading
    import time
    import anyio
    state, transport = server
    client = NotionMCP(Book(), "fixture-account", transport=transport)
    item = client.discover()["tools"]["notion-search"]
    entered, cancelled = threading.Event(), threading.Event()
    async def stalled(request):
        if request.method == "POST" and json.loads(request.content)["method"] == "tools/call":
            entered.set()
            await anyio.sleep(10)
        return await transport.handle_async_request(request)
    client.transport = httpx.MockTransport(stalled)
    result = []
    def call():
        try:
            client.call("notion-search", {"query": "x"}, revision(item), cancelled=cancelled.is_set)
        except NotionError as error:
            result.append(str(error))
    thread = threading.Thread(target=call)
    thread.start()
    try:
        assert entered.wait(3)
        started = time.monotonic()
        cancelled.set()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert time.monotonic() - started < 2
        assert result == ["Notion read cancelled"]
        assert state["calls"] == 0
    finally:
        cancelled.set()
        thread.join(timeout=3)


def test_provider_cannot_echo_credentials_into_the_catalog_or_model_output(server):
    state, transport = server
    client = NotionMCP(Book(), "fixture-account", transport=transport)
    item = client.discover()["tools"]["notion-search"]
    state["text"] = "PRIVATE-ACCESS-SENTINEL"
    with pytest.raises(NotionError, match="credential data"):
        client.call("notion-search", {"query": "x"}, revision(item))
    state["description"] = "PRIVATE-ACCESS-SENTINEL"
    with pytest.raises(NotionError, match="credential data"):
        client.discover()
