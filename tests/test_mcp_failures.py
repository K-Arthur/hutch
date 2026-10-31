"""What a failed connector operation says, and what it must not say.

A wrong URL, an endpoint that is not an MCP server, and an unreachable host are ordinary operator
mistakes, and each has a different fix. Before this was translated, the SDK's protocol exception
escaped the route as a 500 and the server's own response text came with it.

These are separate from the plane's contract tests because they are about error reporting: the
same transport, exercised through its failure paths.
"""

from __future__ import annotations

import http.server
import threading

import pytest

from hutch.integrations.mcp import config, persistence, service


class _NotMcp(http.server.BaseHTTPRequestHandler):
    """Reachable over HTTP, and not an MCP server: it answers 404 everywhere."""

    def do_GET(self):                                       # noqa: N802 - stdlib naming
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"not an mcp server")

    do_POST = do_GET                                        # noqa: N815 - same handler

    def log_message(self, *args):                           # keep test output clean
        pass


@pytest.fixture
def not_mcp_origin():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _NotMcp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def test_discovery_against_a_non_mcp_endpoint_explains_the_failure(store, not_mcp_origin):
    """A wrong URL reads as "this is not an MCP endpoint", not as a crash or an empty catalog."""
    definition = {"transport": "mcp_http", "url": f"http://127.0.0.1:{not_mcp_origin}/mcp",
                  "auth": {"type": "none"}}
    revision = config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)

    with pytest.raises(config.McpConfigurationError) as exc:
        service.discover(store, integration_id="acme")

    message = str(exc.value)
    assert "MCP" in message
    assert "not as an MCP server" in message or "did not complete" in message
    # The server's own text is never forwarded: a response body is untrusted input.
    assert "not an mcp server" not in message
    # ...and nothing was recorded as a reviewable catalog.
    assert persistence.catalog_for(store._db, "acme") == []


def test_an_unknown_transport_is_refused_before_any_connection(store):
    with pytest.raises(config.McpConfigurationError):
        service.configure(store, integration_id="acme", title="Acme",
                          raw_definition={"transport": "carrier-pigeon"})
    assert persistence.definition_for(store._db, "acme") is None


# ------------------------------------------------------------------ bearer credentials


class _Recorder:
    """A tiny HTTP server that records the Authorization header it receives."""

    def __init__(self) -> None:
        import http.server
        import threading

        recorder = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):                              # noqa: N802 - stdlib naming
                recorder.headers.append(self.headers.get("Authorization", ""))
                self.send_response(401)                     # not an MCP server; the header is the point
                self.send_header("content-length", "0")
                self.end_headers()

            do_GET = do_POST                                # noqa: N815 - same handler

            def log_message(self, *args):
                pass

        self.headers: list[str] = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_a_missing_bearer_variable_is_refused_and_named(store):
    definition = {"transport": "mcp_http", "url": "http://127.0.0.1:9/mcp",
                  "auth": {"type": "bearer", "from_env": "HUTCH_TEST_ABSENT_CONNECTOR_TOKEN"}}
    revision = config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="bearer", title="Bearer",
                                    definition=definition, revision=revision)
    with pytest.raises(config.McpConfigurationError) as exc:
        service.discover(store, integration_id="bearer")
    assert "HUTCH_TEST_ABSENT_CONNECTOR_TOKEN" in str(exc.value)
    assert "is not set" in str(exc.value)


def test_a_bearer_token_is_actually_sent_and_never_echoed(store, monkeypatch):
    """Building the header and not passing it is exactly the bug a live run caught once."""
    recorded = _Recorder()
    token = "test-token-value-9f2c"
    monkeypatch.setenv("HUTCH_TEST_CONNECTOR_TOKEN", token)
    try:
        definition = {"transport": "mcp_http", "url": f"http://127.0.0.1:{recorded.port}/mcp",
                      "auth": {"type": "bearer", "from_env": "HUTCH_TEST_CONNECTOR_TOKEN"}}
        revision = config.definition_revision(definition)
        with store._tx() as db:
            persistence.save_definition(db, integration_id="bearer", title="Bearer",
                                        definition=definition, revision=revision)
        with pytest.raises(config.McpConfigurationError) as exc:
            service.discover(store, integration_id="bearer")

        assert recorded.headers, "the server received no request at all"
        assert recorded.headers[0] == f"Bearer {token}"
        # The refusal must describe the stage, not repeat the credential.
        assert token not in str(exc.value)
    finally:
        recorded.close()
