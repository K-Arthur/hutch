from __future__ import annotations

import json
import os

import pytest

from hutch.runtime.opencode_login import LocalLoginError, local_logins, reuse_local_login


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = tmp_path / "opencode" / "auth.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "opencode-go": {"type": "api", "key": "selected-secret"},
        "other": {"type": "api", "key": "unrelated-secret"},
        "openai": {"type": "oauth", "access": "oauth-secret"},
    }))
    path.chmod(0o600)
    return path


class Server:
    def __init__(self):
        self.calls = []

    def integrations(self):
        return [{"id": "opencode-go", "methods": [{"type": "key"}]}]

    def connect_key(self, provider, key, *, label):
        self.calls.append((provider, key, label))


def test_discovery_returns_no_secret_and_marks_oauth_as_sign_in(auth):
    rows = local_logins()
    assert "secret" not in json.dumps(rows)
    assert next(row for row in rows if row["provider_id"] == "opencode-go")["reusable"]
    assert not next(row for row in rows if row["provider_id"] == "openai")["reusable"]


def test_reuse_only_transfers_selected_key_and_preserves_source(auth):
    original = auth.read_bytes()
    server = Server()
    reuse_local_login(server, "opencode-go")
    assert server.calls == [("opencode-go", "selected-secret", "Existing local login")]
    assert auth.read_bytes() == original


@pytest.mark.parametrize("provider", ["openai", "other", "missing", "../../auth.json"])
def test_oauth_unknown_and_unsupported_providers_cannot_be_imported(auth, provider):
    server = Server()
    with pytest.raises(LocalLoginError):
        reuse_local_login(server, provider)
    assert not server.calls


def test_provider_error_cannot_echo_key(auth):
    server = Server()
    def fail(*args, **kwargs):
        raise ValueError("selected-secret")
    server.connect_key = fail
    with pytest.raises(LocalLoginError) as error:
        reuse_local_login(server, "opencode-go")
    assert "selected-secret" not in str(error.value)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner/mode enforcement")
def test_shared_or_symlinked_login_is_rejected(auth, tmp_path):
    auth.chmod(0o644)
    with pytest.raises(LocalLoginError):
        local_logins()
    auth.chmod(0o600)
    target = tmp_path / "private.json"
    auth.rename(target)
    auth.symlink_to(target)
    with pytest.raises(LocalLoginError):
        local_logins()


def test_malformed_auth_never_includes_its_contents(auth):
    auth.write_text("secret-is-not-json")
    with pytest.raises(LocalLoginError) as error:
        local_logins()
    assert "secret-is-not-json" not in str(error.value)
