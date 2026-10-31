"""Cryptographic primitives: real scrypt, real AES-GCM, no substitutes.

These tests exercise the actual primitives Hutch uses. The only thing shortened is the scrypt cost
in tests that do not measure it; ``test_default_cost_meets_documented_floor`` pins the production
parameters to the OWASP floor so a cheaper default cannot slip in unnoticed.
"""

from __future__ import annotations

import pytest

from hutch.vault import crypto


def test_default_cost_meets_documented_floor():
    """OWASP scrypt fallback: N=2^17, r=8, p=1. Raising it is fine; lowering it is not."""
    params = crypto.DEFAULT_SCRYPT
    assert params.n == 1 << 17
    assert params.r == 8
    assert params.p == 1
    assert params.memory_bytes == 128 * 1024 * 1024
    params.validate()


@pytest.mark.parametrize("n", [0, 1, 4096, (1 << 14) - 1, 1 << 21, 100_000])
def test_scrypt_rejects_out_of_range_or_non_power_of_two_n(n):
    with pytest.raises(crypto.VaultCryptoError):
        crypto.ScryptParams(n=n).validate()


@pytest.mark.parametrize("r,p", [(0, 1), (33, 1), (8, 0), (8, 5)])
def test_scrypt_rejects_out_of_range_r_and_p(r, p):
    with pytest.raises(crypto.VaultCryptoError):
        crypto.ScryptParams(n=crypto.MIN_SCRYPT_N, r=r, p=p).validate()


def test_scrypt_params_round_trip_and_refuse_extra_fields():
    params = crypto.ScryptParams(n=crypto.MIN_SCRYPT_N, r=8, p=2)
    assert crypto.ScryptParams.from_dict(params.as_dict()) == params
    with pytest.raises(crypto.VaultCryptoError):
        crypto.ScryptParams.from_dict({"n": 16384, "r": 8, "p": 1, "extra": 1})
    with pytest.raises(crypto.VaultCryptoError):
        crypto.ScryptParams.from_dict({"n": "16384", "r": 8, "p": 1})


def test_passphrase_kek_is_deterministic_per_salt_and_differs_across_salts():
    params = crypto.ScryptParams.for_tests()
    salt = crypto.new_salt()
    first = crypto.derive_passphrase_kek("correct horse battery staple", salt, params)
    second = crypto.derive_passphrase_kek("correct horse battery staple", salt, params)
    assert bytes(first) == bytes(second)
    other = crypto.derive_passphrase_kek("correct horse battery staple", crypto.new_salt(), params)
    assert bytes(first) != bytes(other)
    third = crypto.derive_passphrase_kek("correct horse battery stapl3", salt, params)
    assert bytes(first) != bytes(third)
    crypto.zero(first)
    assert bytes(first) == bytes(len(first))


def test_passphrase_kek_requires_a_passphrase_and_a_full_salt():
    with pytest.raises(crypto.VaultCryptoError):
        crypto.derive_passphrase_kek("", crypto.new_salt(), crypto.ScryptParams.for_tests())
    with pytest.raises(crypto.VaultCryptoError):
        crypto.derive_passphrase_kek("a-passphrase", b"short", crypto.ScryptParams.for_tests())


def test_dek_wrap_round_trip_and_wrong_key_refused():
    dek = crypto.new_dek()
    aad = crypto.wrap_aad("a" * 32, 1, "passphrase")
    kek = crypto.derive_passphrase_kek("a-passphrase", crypto.new_salt(), crypto.ScryptParams.for_tests())
    nonce, wrapped = crypto.wrap_dek(kek, dek, aad)
    assert crypto.unwrap_dek(kek, nonce, wrapped, aad) == dek

    other = crypto.derive_passphrase_kek("a-different-passphrase", crypto.new_salt(),
                                         crypto.ScryptParams.for_tests())
    with pytest.raises(crypto.WrongKey):
        crypto.unwrap_dek(other, nonce, wrapped, aad)


def test_dek_wrap_is_bound_to_vault_version_and_kind():
    dek = crypto.new_dek()
    kek = crypto.derive_passphrase_kek("a-passphrase", crypto.new_salt(), crypto.ScryptParams.for_tests())
    aad = crypto.wrap_aad("a" * 32, 1, "passphrase")
    nonce, wrapped = crypto.wrap_dek(kek, dek, aad)

    for wrong in (crypto.wrap_aad("b" * 32, 1, "passphrase"),
                  crypto.wrap_aad("a" * 32, 2, "passphrase"),
                  crypto.wrap_aad("a" * 32, 1, "recovery")):
        assert wrong != aad
        with pytest.raises(crypto.WrongKey):
            crypto.unwrap_dek(kek, nonce, wrapped, wrong)


def test_dek_wrap_detects_tampering():
    dek = crypto.new_dek()
    kek = crypto.derive_passphrase_kek("a-passphrase", crypto.new_salt(), crypto.ScryptParams.for_tests())
    aad = crypto.wrap_aad("a" * 32, 1, "passphrase")
    nonce, wrapped = crypto.wrap_dek(kek, dek, aad)

    flipped = bytearray(wrapped)
    flipped[0] ^= 0x01
    with pytest.raises(crypto.WrongKey):
        crypto.unwrap_dek(kek, nonce, bytes(flipped), aad)

    with pytest.raises(crypto.WrongKey):
        crypto.unwrap_dek(kek, nonce, wrapped[:-1], aad)


def test_two_wraps_of_the_same_dek_share_no_ciphertext():
    dek = crypto.new_dek()
    kek = crypto.derive_passphrase_kek("a-passphrase", crypto.new_salt(), crypto.ScryptParams.for_tests())
    aad = crypto.wrap_aad("a" * 32, 1, "passphrase")
    first_nonce, first = crypto.wrap_dek(kek, dek, aad)
    second_nonce, second = crypto.wrap_dek(kek, dek, aad)
    assert first_nonce != second_nonce
    assert first != second


def test_secret_encryption_round_trip():
    dek = crypto.new_dek()
    aad = crypto.secret_aad("sec_" + "a" * 24, 1, "workspace", "api_key")
    nonce, ciphertext = crypto.encrypt_secret(dek, b"sk-live-not-a-real-key", aad)
    assert b"sk-live-not-a-real-key" not in ciphertext
    assert crypto.decrypt_secret(dek, nonce, ciphertext, aad) == bytearray(b"sk-live-not-a-real-key")


def test_secret_encryption_is_bound_to_identity_and_version():
    dek = crypto.new_dek()
    nonce, ciphertext = crypto.encrypt_secret(
        dek, b"value", crypto.secret_aad("sec_" + "a" * 24, 1, "workspace", "api_key"))
    for wrong in (crypto.secret_aad("sec_" + "b" * 24, 1, "workspace", "api_key"),
                  crypto.secret_aad("sec_" + "a" * 24, 2, "workspace", "api_key"),
                  crypto.secret_aad("sec_" + "a" * 24, 1, "bot:bot_000000000000", "api_key"),
                  crypto.secret_aad("sec_" + "a" * 24, 1, "workspace", "other")):
        with pytest.raises(crypto.VaultCryptoError):
            crypto.decrypt_secret(dek, nonce, ciphertext, wrong)


def test_secret_encryption_rejects_oversized_and_empty_values():
    dek = crypto.new_dek()
    aad = crypto.secret_aad("sec_" + "a" * 24, 1, "workspace", "other")
    with pytest.raises(crypto.VaultCryptoError):
        crypto.encrypt_secret(dek, b"", aad)
    with pytest.raises(crypto.VaultCryptoError):
        crypto.encrypt_secret(dek, b"x" * (crypto.MAX_CIPHERTEXT_BYTES + 1), aad)


def test_nonces_are_unique_across_many_encryptions():
    dek = crypto.new_dek()
    aad = crypto.secret_aad("sec_" + "a" * 24, 1, "workspace", "other")
    nonces = {crypto.encrypt_secret(dek, b"same value", aad)[0] for _ in range(256)}
    assert len(nonces) == 256


def test_recovery_key_round_trip_and_display_shape():
    text, payload = crypto.generate_recovery_key()
    assert len(payload) == crypto.RECOVERY_KEY_BYTES
    groups = text.split("-")
    assert len(groups) == crypto.RECOVERY_TOTAL_CHARS // 4
    assert all(len(group) == 4 for group in groups)
    assert len("".join(groups)) == crypto.RECOVERY_TOTAL_CHARS
    assert crypto.parse_recovery_key(text) == payload
    # Whitespace, lower case and separator style do not matter to a person retyping it.
    assert crypto.parse_recovery_key(text.lower().replace("-", " ")) == payload


def test_recovery_key_accepts_confusable_characters():
    text, payload = crypto.generate_recovery_key()
    body, check = text.replace("-", "")[:-4], text.replace("-", "")[-4:]
    swapped = body.replace("0", "O").replace("1", "I")
    assert crypto.parse_recovery_key(swapped + check) == payload


def test_recovery_key_detects_a_mistyped_character():
    text, _ = crypto.generate_recovery_key()
    compact = text.replace("-", "")
    flipped = ("Z" if compact[0] != "Z" else "Y") + compact[1:]
    with pytest.raises(crypto.VaultCryptoError):
        crypto.parse_recovery_key(flipped)


@pytest.mark.parametrize("bad", ["", "short", "-" * 40, "A" * 35, "A" * 37])
def test_recovery_key_rejects_wrong_lengths(bad):
    with pytest.raises(crypto.VaultCryptoError):
        crypto.parse_recovery_key(bad)


def test_recovery_kek_is_deterministic_and_salt_bound():
    payload = bytes(range(crypto.RECOVERY_KEY_BYTES))
    salt = crypto.new_salt()
    first = crypto.derive_recovery_kek(payload, salt)
    second = crypto.derive_recovery_kek(payload, salt)
    assert bytes(first) == bytes(second)
    third = crypto.derive_recovery_kek(payload, crypto.new_salt())
    assert bytes(first) != bytes(third)
    with pytest.raises(crypto.VaultCryptoError):
        crypto.derive_recovery_kek(b"short", salt)


def test_passphrase_policy_is_actionable_and_never_echoes_the_input():
    assert crypto.passphrase_problem("a-perfectly-fine-passphrase") is None
    short = crypto.passphrase_problem("short")
    assert short and "12" in short and "short" not in short.replace("at least", "")
    common = crypto.passphrase_problem("passwordpassword")
    assert common is not None and "commonly used" in common
    with_null = crypto.passphrase_problem("a-good-passphrase\x00")
    assert with_null is not None
    assert crypto.passphrase_problem(123) is not None  # type: ignore[arg-type]


def test_benchmark_reports_the_configured_cost():
    result = crypto.benchmark(crypto.ScryptParams.for_tests())
    assert result["n"] == crypto.MIN_SCRYPT_N
    assert result["memory_bytes"] == 128 * crypto.MIN_SCRYPT_N * 8
    assert result["seconds"] > 0
