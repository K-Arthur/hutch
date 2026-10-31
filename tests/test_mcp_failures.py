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
