"""Vault cryptography: a passphrase-derived KEK, one DEK per vault, AES-256-GCM for everything.

The shape is deliberate and narrow.

* The **DEK** is 32 random bytes, created once per vault. It is the only key that ever encrypts a
  secret value. It is never derived from anything and never leaves the process.
* A **KEK** wraps the DEK. There is one KEK per credential path: a passphrase KEK (scrypt) and a
  recovery-key KEK (HKDF). Each wrap has its own random salt and nonce, so two wraps of the same
  DEK share no ciphertext.
* Every ciphertext is bound to its identity with associated data. A wrapped DEK is bound to
  ``(vault id, wrap version, wrap kind)``; a secret is bound to
  ``(secret id, version, scope, category)``. Moving a row, or replaying an old version number,
  fails authentication instead of decrypting the wrong thing.

Why scrypt rather than Argon2id is recorded in ``docs/security/vault-and-authentication/decisions.md``
(D1): OWASP names scrypt as the correct fallback, ``cryptography`` is already a pinned dependency
and ``argon2`` is not installed. The KDF identifier and its parameters travel with each wrap, so an
Argon2id wrap can be added later and old wraps keep working.

Nothing here writes a file, logs a value, or falls back to a weaker path. Every failure raises.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

#: AES-256-GCM keys and the DEK are 32 bytes.
KEY_BYTES = 32
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
MAX_CIPHERTEXT_BYTES = 128 * 1024

#: A recovery key is 160 bits of randomness. That is far beyond brute force for a random key and
#: short enough to write down; unlike a passphrase it needs no memory-hard stretching.
RECOVERY_KEY_BYTES = 20
RECOVERY_KEY_CHARS = RECOVERY_KEY_BYTES * 8 // 5          # 32
RECOVERY_CHECK_CHARS = 4
RECOVERY_TOTAL_CHARS = RECOVERY_KEY_CHARS + RECOVERY_CHECK_CHARS

#: OWASP Password Storage Cheat Sheet: Argon2id first, scrypt with N=2^17, r=8, p=1 if not.
DEFAULT_SCRYPT_N = 1 << 17
#: Structural bounds for parameters read back from storage. A tampered low value breaks the wrap
#: (the tag no longer verifies) rather than weakening it, and passphrase changes always re-wrap at
#: ``DEFAULT_SCRYPT_N`` regardless of what the old row said.
MIN_SCRYPT_N = 1 << 14
MAX_SCRYPT_N = 1 << 20
MAX_SCRYPT_R = 32
MAX_SCRYPT_P = 4

MIN_PASSPHRASE_CHARS = 12
MAX_PASSPHRASE_BYTES = 1024

KDF_SCRYPT = "scrypt"
KDF_HKDF_SHA256 = "hkdf-sha256"
WRAP_KINDS = ("passphrase", "recovery")

_WRAP_PREFIX = b"hutch.vault.wrap.v1"
_SECRET_PREFIX = b"hutch.vault.secret.v1"
_RECOVERY_CHECK_PREFIX = b"hutch.vault.recovery.checksum.v1"
_RECOVERY_KDF_INFO = b"hutch.vault.recovery.v1"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
#: Crockford's confusable aliases, so a person can read a key aloud without losing it to I/L/O.
_CROCKFORD_ALIASES = str.maketrans({"I": "1", "L": "1", "O": "0"})

#: Obvious passphrases. Not a substitute for a breach corpus; it removes the worst choices and
#: keeps the message actionable without pretending to be comprehensive.
_COMMON_PASSPHRASES = frozenset({
    "password", "password1", "passw0rd", "password123", "passwordpassword",
    "123456789012", "qwertyuiopas", "letmeinletmein", "administrator",
    "changemechangeme", "correcthorsebattery", "correcthorsebatterystaple",
    "iloveyouiloveyou", "welcomewelcome", "secretsecret", "hutchhutchhutch",
    "defaultpassword", "temporarypassword",
})


class VaultCryptoError(Exception):
    """A cryptographic operation refused to produce or accept key material."""


class WrongKey(VaultCryptoError):
    """The supplied credential does not unwrap this vault. Carries no detail on purpose."""


@dataclass(frozen=True)
class ScryptParams:
    """Cost parameters for one passphrase wrap. Stored with the wrap so cost can be raised later."""

    n: int = DEFAULT_SCRYPT_N
    r: int = 8
    p: int = 1

    @property
    def memory_bytes(self) -> int:
        """scrypt's working set, from RFC 7914: 128 * N * r."""
        return 128 * self.n * self.r

    def validate(self) -> None:
        if not isinstance(self.n, int) or isinstance(self.n, bool):
            raise VaultCryptoError("scrypt N must be an integer")
        if self.n < MIN_SCRYPT_N or self.n > MAX_SCRYPT_N or self.n & (self.n - 1):
            raise VaultCryptoError("scrypt N must be a power of two between 2^14 and 2^20")
        if not isinstance(self.r, int) or not 1 <= self.r <= MAX_SCRYPT_R:
            raise VaultCryptoError(f"scrypt r must be between 1 and {MAX_SCRYPT_R}")
        if not isinstance(self.p, int) or not 1 <= self.p <= MAX_SCRYPT_P:
            raise VaultCryptoError(f"scrypt p must be between 1 and {MAX_SCRYPT_P}")

    def as_dict(self) -> dict[str, int]:
        self.validate()
        return {"n": self.n, "r": self.r, "p": self.p}

    @classmethod
    def from_dict(cls, value: object) -> "ScryptParams":
        if not isinstance(value, dict):
            raise VaultCryptoError("stored scrypt parameters are not an object")
        extra = set(value) - {"n", "r", "p"}
        if extra:
            raise VaultCryptoError("stored scrypt parameters contain unknown fields")
        # Exact integers only: a string here would be silently coerced and could hide a
        # tampered record behind a value that looks valid.
        if any(not isinstance(value.get(key), int) or isinstance(value.get(key), bool)
               for key in ("n", "r", "p")):
            raise VaultCryptoError("stored scrypt parameters must be integers")
        params = cls(n=value["n"], r=value["r"], p=value["p"])
        params.validate()
        return params

    @classmethod
    def for_tests(cls) -> "ScryptParams":
        """A deliberately cheap cost, for tests and benchmarks only.

        Never returned by vault creation or a passphrase change: both use ``DEFAULT_SCRYPT``. A
        vault created with these parameters is weaker against offline guessing, which is exactly
        why only tests and the benchmark harness call this.
        """
        return cls(n=MIN_SCRYPT_N, r=8, p=1)


DEFAULT_SCRYPT = ScryptParams()


def _bind(prefix: bytes, *parts: str) -> bytes:
    """Length-prefixed associated data, so two different part sequences cannot collide."""
    out = bytearray(prefix)
    for part in parts:
        raw = part.encode("utf-8", "strict")
        out += len(raw).to_bytes(4, "big")
        out += raw
    return bytes(out)


def wrap_aad(vault_id: str, version: int, kind: str) -> bytes:
    if kind not in WRAP_KINDS:
        raise VaultCryptoError("unknown key-wrap kind")
    if not isinstance(version, int) or version < 1:
        raise VaultCryptoError("a wrap version must be a positive integer")
    return _bind(_WRAP_PREFIX, vault_id, str(version), kind)


def secret_aad(secret_id: str, version: int, scope: str, category: str) -> bytes:
    if not isinstance(version, int) or version < 1:
        raise VaultCryptoError("a secret version must be a positive integer")
    return _bind(_SECRET_PREFIX, secret_id, str(version), scope, category)


def new_vault_id() -> str:
    return secrets.token_hex(16)


def new_dek() -> bytearray:
    return bytearray(secrets.token_bytes(KEY_BYTES))


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def derive_passphrase_kek(passphrase: str, salt: bytes, params: ScryptParams = DEFAULT_SCRYPT) -> bytearray:
    """Stretch a passphrase into a wrapping key. The passphrase is never used as a key itself."""
    if not isinstance(passphrase, str) or not passphrase:
        raise VaultCryptoError("a passphrase is required")
    if len(salt) != SALT_BYTES:
        raise VaultCryptoError("a passphrase salt must be 16 bytes")
    params.validate()
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=params.n, r=params.r, p=params.p)
    return bytearray(kdf.derive(passphrase.encode("utf-8")))


def derive_recovery_kek(recovery_key: bytes, salt: bytes) -> bytearray:
    """A 160-bit random key needs extraction, not stretching."""
    if not isinstance(recovery_key, bytes) or len(recovery_key) != RECOVERY_KEY_BYTES:
        raise VaultCryptoError("a recovery key must be 20 bytes")
    if len(salt) != SALT_BYTES:
        raise VaultCryptoError("a recovery salt must be 16 bytes")
    hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=salt, info=_RECOVERY_KDF_INFO)
    return bytearray(hkdf.derive(recovery_key))


def wrap_dek(kek: bytes, dek: bytes, aad: bytes) -> tuple[bytes, bytes]:
    if len(kek) != KEY_BYTES or len(dek) != KEY_BYTES:
        raise VaultCryptoError("wrapping keys must be 32 bytes")
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce, AESGCM(bytes(kek)).encrypt(nonce, bytes(dek), aad)


def unwrap_dek(kek: bytes, nonce: bytes, wrapped: bytes, aad: bytes) -> bytearray:
    if len(kek) != KEY_BYTES or len(nonce) != NONCE_BYTES or len(wrapped) != KEY_BYTES + TAG_BYTES:
        raise WrongKey("the vault key record is malformed")
    try:
        return bytearray(AESGCM(bytes(kek)).decrypt(nonce, wrapped, aad))
    except (InvalidTag, ValueError):
        # Identical failure for a wrong passphrase and a tampered wrap: the caller learns only that
        # this credential does not open this vault.
        raise WrongKey("the supplied credential does not open this vault") from None


def encrypt_secret(dek: bytes, value: bytes, aad: bytes) -> tuple[bytes, bytes]:
    if len(dek) != KEY_BYTES:
        raise VaultCryptoError("the vault key is malformed")
    if not isinstance(value, bytes) or not value:
        raise VaultCryptoError("a secret value must be non-empty")
    if len(value) > MAX_CIPHERTEXT_BYTES:
        raise VaultCryptoError("the secret value is too large")
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce, AESGCM(bytes(dek)).encrypt(nonce, value, aad)


def decrypt_secret(dek: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytearray:
    if len(dek) != KEY_BYTES or len(nonce) != NONCE_BYTES:
        raise VaultCryptoError("the vault key record is malformed")
    if not isinstance(ciphertext, bytes) or len(ciphertext) < TAG_BYTES + 1:
        raise VaultCryptoError("the stored secret is malformed")
    try:
        return bytearray(AESGCM(bytes(dek)).decrypt(nonce, ciphertext, aad))
    except (InvalidTag, ValueError):
        raise VaultCryptoError("the stored secret failed authentication") from None


def zero(buffer: Optional[bytearray]) -> None:
    """Best-effort overwrite of a mutable key buffer.

    Python cannot guarantee that no copy exists in an allocator, a traceback or swap, so this is
    *not* claimed as guaranteed memory cleansing; it shortens the window and is honest about it in
    ``security-limitations.md``.
    """
    if buffer is None:
        return
    for index in range(len(buffer)):
        buffer[index] = 0


def passphrase_problem(passphrase: str) -> Optional[str]:
    """A reason the passphrase is unacceptable, or ``None``. Actionable, never echo the input."""
    if not isinstance(passphrase, str):
        return "The vault passphrase must be text."
    encoded = passphrase.encode("utf-8")
    if len(encoded) > MAX_PASSPHRASE_BYTES:
        return f"The vault passphrase must be at most {MAX_PASSPHRASE_BYTES} bytes."
    if len(passphrase.strip()) < MIN_PASSPHRASE_CHARS:
        return f"Use at least {MIN_PASSPHRASE_CHARS} characters for the vault passphrase."
    if "\x00" in passphrase:
        return "The vault passphrase cannot contain a null character."
    if "".join(passphrase.split()).lower() in _COMMON_PASSPHRASES:
        return "That passphrase is one of the most commonly used; choose a different one."
    return None


def _encode_five_bit_groups(payload: bytes) -> str:
    bits = int.from_bytes(payload, "big")
    width = len(payload) * 8
    if width % 5:
        raise VaultCryptoError("the recovery payload is not a whole number of 5-bit groups")
    return "".join(_CROCKFORD[(bits >> shift) & 31] for shift in range(width - 5, -1, -5))


def _decode_five_bit_groups(text: str) -> bytes:
    value = 0
    for char in text:
        index = _CROCKFORD.find(char)
        if index < 0:
            raise VaultCryptoError("the recovery key contains a character outside the alphabet")
        value = (value << 5) | index
    return value.to_bytes(len(text) * 5 // 8, "big")


def _recovery_check(payload: bytes) -> str:
    digest = hashlib.sha256(_RECOVERY_CHECK_PREFIX + payload).digest()
    value = int.from_bytes(digest[:3], "big") >> 4          # the top 20 bits
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(15, -1, -5))


def format_recovery_key(payload: bytes) -> str:
    if len(payload) != RECOVERY_KEY_BYTES:
        raise VaultCryptoError("a recovery payload must be 20 bytes")
    raw = _encode_five_bit_groups(payload) + _recovery_check(payload)
    return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))


def parse_recovery_key(text: str) -> bytes:
    if not isinstance(text, str):
        raise VaultCryptoError("a recovery key must be text")
    cleaned = "".join(char for char in text.upper() if not char.isspace() and char != "-")
    if len(cleaned) != RECOVERY_TOTAL_CHARS:
        raise VaultCryptoError("the recovery key is not the expected length")
    body, check = cleaned[:RECOVERY_KEY_CHARS], cleaned[RECOVERY_KEY_CHARS:]
    try:
        payload = _decode_five_bit_groups(body.translate(_CROCKFORD_ALIASES))
    except (VaultCryptoError, OverflowError):
        raise VaultCryptoError("the recovery key is not valid") from None
    if not hmac.compare_digest(_recovery_check(payload), check):
        raise VaultCryptoError("the recovery key check failed; it may have been mistyped")
    return payload


def generate_recovery_key() -> tuple[str, bytes]:
    """Return ``(display form, raw payload)``. The display form is shown to the owner exactly once."""
    payload = secrets.token_bytes(RECOVERY_KEY_BYTES)
    return format_recovery_key(payload), payload


def benchmark(params: ScryptParams = DEFAULT_SCRYPT, iterations: int = 1) -> dict[str, float | int]:
    """Measure unlock cost on this machine. Used by the CLI and by the documented floor test."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    started = time.perf_counter()
    for _ in range(iterations):
        kek = derive_passphrase_kek("benchmark-passphrase-not-a-secret", new_salt(), params)
        zero(kek)
    elapsed = time.perf_counter() - started
    return {"n": params.n, "r": params.r, "p": params.p,
            "memory_bytes": params.memory_bytes, "seconds": elapsed / iterations}
