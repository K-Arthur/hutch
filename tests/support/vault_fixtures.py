"""Shared fixtures for the vault tests.

These build the real ``Store`` the application uses and the real ``VaultBook``. Only the scrypt
cost is reduced, and only for vaults these helpers create.
"""

from __future__ import annotations

from hutch.vault import crypto
from hutch.vault.vault import VaultBook

PASSPHRASE = "a-long-enough-vault-passphrase"
BOT_A = "bot_aaaaaaaaaaaa"
BOT_B = "bot_bbbbbbbbbbbb"
CANARY = "[redacted]"
DESTINATION = "https://api.notion.com"


def make_vault(store, **kwargs) -> VaultBook:
    return VaultBook(store, scrypt_params=crypto.ScryptParams.for_tests(), **kwargs)


def unlocked(store, **kwargs) -> VaultBook:
    vault = make_vault(store, **kwargs)
    vault.create(PASSPHRASE)
    return vault
