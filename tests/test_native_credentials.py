"""Native-store contracts; only the marked host roundtrip is OS-vault evidence."""
import builtins
import sys
from types import SimpleNamespace
import uuid

import pytest

from hutch.google_calendar import GoogleCalendarError, SecretToolStore
from hutch.gsuite.client import WorkspaceSecretToolStore, GoogleWorkspaceError
from hutch.platforms import credentials
from hutch.outlook_calendar import SecretToolStore as OutlookSecrets


class VaultFixture:
    priority = 5

    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[service, account] = value

    def delete_password(self, service, account):
        del self.values[service, account]


@pytest.mark.parametrize("host,expected_module,expected_attribute", [
    ("win32", "keyring.backends.Windows", "persist"),
    ("darwin", "keyring.backends.macOS", "keychain"),
])
def test_native_selector_pins_backend_and_ignores_environment_properties(monkeypatch, host, expected_module, expected_attribute):
    class Backend(VaultFixture):
        def __init__(self):
            raise AssertionError("ambient backend constructor must not run")
    original_import = builtins.__import__
    calls = []
    def selected_import(name, *args, **kwargs):
        if name.startswith("keyring"):
            calls.append(name)
            assert name == expected_module
            return SimpleNamespace(WinVaultKeyring=Backend, Keyring=Backend)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", selected_import)
    monkeypatch.setattr(credentials, "sys", SimpleNamespace(platform=host))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")
    monkeypatch.setenv("KEYCHAIN_PATH", "unrelated-private-keychain")
    monkeypatch.setenv("KEYRING_PROPERTY_PERSIST", "enterprise")
    credentials._backend.cache_clear()
    try:
        backend = credentials._backend()
        assert getattr(backend, expected_attribute) == ("local machine" if host == "win32" else None)
        assert calls == [expected_module]
    finally:
        credentials._backend.cache_clear()


def test_shared_secret_store_native_path_preserves_namespaces_and_never_uses_subprocess(monkeypatch):
    vault = VaultFixture()
    monkeypatch.setattr(credentials, "native_host", lambda: True)
    monkeypatch.setattr(credentials, "_backend", lambda: vault)
    monkeypatch.setattr("hutch.google_calendar.subprocess.run", lambda *a, **kw: pytest.fail("native credentials must not use subprocess argv"))
    calendar = SecretToolStore()
    workspace = WorkspaceSecretToolStore()
    outlook = OutlookSecrets()
    calendar_id = "gcal_0123456789abcdef01234567"
    workspace_id = "gws_0123456789abcdef01234567"
    assert calendar.available() and workspace.available() and outlook.available()
    outlook.put("mscal_0123456789abcdef01234567", '{"refresh_token":"fixture-outlook"}')
    calendar.put(calendar_id, '{"refresh_token":"fixture-calendar"}')
    workspace.put(workspace_id, '{"refresh_token":"fixture-workspace"}')
    assert calendar.get(calendar_id) == '{"refresh_token":"fixture-calendar"}'
    assert workspace.get(workspace_id) == '{"refresh_token":"fixture-workspace"}'
    assert {service for service, _ in vault.values} == {f"{calendar.service}:{calendar_id}", f"{workspace.service}:{workspace_id}", f"{outlook.service}:mscal_0123456789abcdef01234567"}
    workspace.delete(workspace_id)
    workspace.delete(workspace_id)
    assert calendar.get(calendar_id)
    with pytest.raises(GoogleWorkspaceError, match="invalid"):
        workspace.get(calendar_id)


@pytest.mark.parametrize("operation", ["lookup", "store", "clear"])
def test_native_errors_cannot_disclose_backend_arguments(monkeypatch, operation):
    class BrokenVault(VaultFixture):
        def get_password(self, *args):
            raise RuntimeError("a-secret-that-must-not-escape")
        def set_password(self, *args):
            raise RuntimeError("a-secret-that-must-not-escape")
    monkeypatch.setattr(credentials, "_backend", BrokenVault)
    with pytest.raises(credentials.NativeCredentialError) as error:
        credentials.operate(operation, "hutch.test", "account", "a-secret-that-must-not-escape")
    assert "a-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_native_backend_absence_is_not_a_plaintext_fallback(monkeypatch):
    monkeypatch.setattr(credentials, "sys", SimpleNamespace(platform="unsupported"))
    credentials._backend.cache_clear()
    try:
        assert not credentials.available()
        with pytest.raises(credentials.NativeCredentialError):
            credentials.operate("store", "hutch.test", "account", "fixture")
    finally:
        credentials._backend.cache_clear()


def test_native_error_uses_existing_feature_specific_error_type(monkeypatch):
    monkeypatch.setattr(credentials, "native_host", lambda: True)
    def fail(*args, **kwargs):
        raise credentials.NativeCredentialError("unlock the operating system store")
    monkeypatch.setattr(credentials, "operate", fail)
    with pytest.raises(GoogleWorkspaceError, match="unlock"):
        WorkspaceSecretToolStore().get("gws_0123456789abcdef01234567")
    with pytest.raises(GoogleCalendarError, match="unlock"):
        SecretToolStore().get("gcal_0123456789abcdef01234567")


@pytest.mark.skipif(sys.platform not in ("win32", "darwin"), reason="requires an actual native Windows/macOS vault")
def test_actual_native_vault_roundtrip_and_idempotent_disconnect():
    service = "hutch.native-tests." + uuid.uuid4().hex
    account = "synthetic-account"
    value = "synthetic-fixture-" + uuid.uuid4().hex
    assert credentials.available(), "native credential backend must be present"
    try:
        assert credentials.operate("lookup", service, account) == ""
        credentials.operate("store", service, account, value)
        assert credentials.operate("lookup", service, account) == value
        credentials.operate("store", service, account, value + "-updated")
        assert credentials.operate("lookup", service, account) == value + "-updated"
        credentials.operate("clear", service, account)
        credentials.operate("clear", service, account)
        assert credentials.operate("lookup", service, account) == ""
    finally:
        credentials.operate("clear", service, account)



def test_native_target_is_unique_per_account_even_for_service_level_backends(monkeypatch):
    class OneTargetVault:
        def __init__(self):
            self.values = {}
        def set_password(self, target, account, value):
            self.values[target] = value
        def get_password(self, target, account):
            return self.values.get(target)
        def delete_password(self, target, account):
            self.values.pop(target, None)
    vault = OneTargetVault()
    monkeypatch.setattr(credentials, "_backend", lambda: vault)
    credentials.operate("store", "hutch.test", "account-a", "fixture-a")
    credentials.operate("store", "hutch.test", "account-b", "fixture-b")
    assert credentials.operate("lookup", "hutch.test", "account-a") == "fixture-a"
    assert credentials.operate("lookup", "hutch.test", "account-b") == "fixture-b"
    credentials.operate("clear", "hutch.test", "account-a")
    assert credentials.operate("lookup", "hutch.test", "account-b") == "fixture-b"
