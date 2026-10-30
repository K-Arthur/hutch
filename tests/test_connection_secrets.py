"""Stored connection secrets never come back to the browser through provider error text."""

from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.server.app import create_app
from tests.fakes import FakeOpenAI


def test_connection_test_redacts_the_stored_key_from_provider_errors(config):
    """A provider that echoes Authorization must not put the key back into the response."""
    oai = FakeOpenAI()
    try:
        pasted = "pasted-secret-that-must-not-return"
        book = ConnectionBook(config.state_dir)
        book.add("custom-openai", "echo-provider", base_url=f"{oai.url}/v1")
        book.set_key("echo-provider", pasted)
        oai.force_status = (400, {"error": {"message": f"the key Bearer {pasted} is not valid"}}, {})

        with TestClient(create_app()) as client:
            response = client.post("/api/connections/echo-provider/test", json={})

        assert response.status_code == 400
        assert pasted not in response.text
        assert "[redacted]" in response.text
    finally:
        oai.close()
