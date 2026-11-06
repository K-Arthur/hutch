from __future__ import annotations

import os

import pytest

from hutch.offline import OfflineBrokerSet, broker_socket_path
from hutch.providers.local.probe import ProbeError, get_json


def test_local_runtime_probe_uses_the_offline_broker(tmp_path, monkeypatch):
    from tests.fakes import FakeOllama

    fake = FakeOllama()
    brokers = OfflineBrokerSet([fake.url])
    brokers.start()
    monkeypatch.setenv("HUTCH_OFFLINE_BROKER_DIR", brokers.directory)
    try:
        result = get_json(fake.url + "/api/version")
        assert result.json()["version"] == "0.0-fake"
        localhost_url = fake.url.replace("127.0.0.1", "localhost")
        assert get_json(localhost_url + "/api/version").json()["version"] == "0.0-fake"
        assert len(fake.of("/api/version")) == 2

        os.unlink(broker_socket_path(brokers.directory, fake.url))
        with pytest.raises(ProbeError) as raised:
            get_json(fake.url + "/api/version")
        assert "broker is missing" in str(raised.value)
        assert len(fake.of("/api/version")) == 2
    finally:
        brokers.close()
        fake.close()
