from __future__ import annotations

import socket

import pytest

from hutch.offline import broker_socket_path
from hutch.providers.registry import loopback_endpoint


@pytest.mark.parametrize(("provider_name", "base_url"), [
    ("ollama", "http://localhost:11434"),
    ("llamacpp", "http://localhost:9931/v1"),
    ("lmstudio", "http://localhost:1234/v1"),
])
def test_offline_broker_keeps_the_reviewed_endpoint_identity(
        provider_name, base_url, monkeypatch, tmp_path):
    """The worker's broker must not rewrite provider.base_url.

    Route review compares the provider endpoint with the endpoint it
    authorized. Mutating the provider to the broker's numeric origin made a
    healthy local route fail with "provider endpoint changed after review".
    """
    canonical = loopback_endpoint(provider_name, base_url)
    socket_path = broker_socket_path(str(tmp_path), canonical)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(socket_path)
    listener.listen(1)
    monkeypatch.setenv("HUTCH_OFFLINE_BROKER_DIR", str(tmp_path))
    if provider_name == "ollama":
        from hutch.providers.ollama import OllamaProvider
        provider = OllamaProvider(base_url)
    else:
        from hutch.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider(base_url, provider_name=provider_name)
    try:
        provider._http()
        assert provider.base_url == base_url
        assert str(provider._client.base_url).rstrip("/") == canonical
    finally:
        if provider._client is not None:
            provider._client.close()
        listener.close()
