"""Explicit native secret stores; never discover plugins or plaintext fallbacks.

Linux retains its existing secret-tool transport in google_calendar.SecretToolStore.
The pinned keyring dependency is used only for its native Windows/macOS APIs.
"""
from __future__ import annotations

from functools import lru_cache
import sys
from typing import Any

CONTRACT_VERSION = 1


class NativeCredentialError(ValueError):
    """A deliberately secret-free native-store error."""


def native_host() -> bool:
    return sys.platform in ("win32", "darwin")


@lru_cache(maxsize=1)
def _backend() -> Any:
    # Constructors intentionally omit KeyringBackend.__init__, whose only task in
    # pinned 25.7.0 is importing KEYRING_PROPERTY_* environment overrides. Hutch
    # selects these security properties itself and never calls get_keyring().
    try:
        if sys.platform == "win32":
            from keyring.backends.Windows import WinVaultKeyring

            class LocalWindowsVault(WinVaultKeyring):
                def __init__(self):
                    self.persist = "local machine"  # per-user local persistence, no enterprise roaming

            backend = LocalWindowsVault()
        elif sys.platform == "darwin":
            from keyring.backends.macOS import Keyring

            class LocalMacKeychain(Keyring):
                def __init__(self):
                    self.keychain = None  # native default; ignore ambient KEYCHAIN_PATH

            backend = LocalMacKeychain()
        else:
            raise NativeCredentialError("this host has no selected native credential adapter")
        if backend.priority <= 0:
            raise NativeCredentialError("the native credential backend is unavailable")
        return backend
    except Exception:
        raise NativeCredentialError("the native credential backend is unavailable") from None


def available() -> bool:
    try:
        _backend()
        return True
    except NativeCredentialError:
        return False


def operate(operation: str, service: str, account: str, value: str | None = None) -> str:
    if operation not in ("store", "lookup", "clear") or not service.startswith("hutch.") or not account:
        raise NativeCredentialError("invalid native credential operation")
    try:
        backend = _backend()
        # WinVault can otherwise reuse a service-level target for different
        # usernames. A unique target per account avoids cross-account overwrite
        # during concurrent sign-ins without relying on backend relocation.
        target = f"{service}:{account}"
        if operation == "lookup":
            result = backend.get_password(target, account)
            if result is not None and not isinstance(result, str):
                raise NativeCredentialError("unexpected native credential result")
            return result or ""
        if operation == "store":
            if not isinstance(value, str):
                raise NativeCredentialError("a credential value is required")
            backend.set_password(target, account, value)
        else:
            # Idempotent disconnect. Do not reinterpret arbitrary backend errors
            # as 'absent'; only a successful missing lookup makes this a no-op.
            if backend.get_password(target, account) is not None:
                backend.delete_password(target, account)
        return ""
    except Exception:
        # Backend exceptions can contain arguments, usernames or secret data.
        raise NativeCredentialError("the operating system credential store rejected the operation; unlock it and retry") from None
