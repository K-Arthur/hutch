"""Install failures become a state, an action and a credential-free detail."""

from __future__ import annotations

import pytest

from hutch.providers.install_errors import (
    cancelled_failure, classify_install_error, interrupted_failure, redact_secrets,
    unconfirmed_failure,
)


@pytest.mark.parametrize("text,code", [
    ("write /tmp/p4small/models/blobs/sha256-5ee4f07cdb9b-partial: no space left on device", "disk_full"),
    ('pull model manifest: Get "https://registry.ollama.ai/v2/library/qwen2.5/manifests/3b": '
     "dial tcp [2606:4700::6812:11aa]:443: connect: network is unreachable", "network"),
])
def test_captured_runtime_errors_are_classified(text, code):
    """The exact strings from the real 2026-11-06 disk-full and no-route pulls."""
    failure = classify_install_error(text)
    assert failure.code == code
    assert failure.action in ("free_space", "retry")


def test_a_full_disk_names_the_free_and_needed_sizes():
    failure = classify_install_error("no space left on device", free_bytes=300 * 1024 * 1024,
                                     size_bytes=2 * 1024 ** 3)
    assert failure.code == "disk_full"
    assert failure.action == "free_space"
    assert "0.3 GiB is free" in failure.message
    assert "2.0 GiB" in failure.message
    assert "no space left" in failure.detail


@pytest.mark.parametrize("text", [
    "unexpected EOF",
    "max retries exceeded with url: /v2/... (Caused by NewConnectionError(...))",
    "connection reset by peer",
    "read timed out",
    "network is unreachable",
])
def test_network_failures_offer_resume(text):
    failure = classify_install_error(text)
    assert failure.code == "network"
    assert failure.action == "retry"
    assert "network dropped" in failure.message
    assert "Verified parts are kept" in failure.message


@pytest.mark.parametrize("text", [
    "cannot connect to http://127.0.0.1:11434",
    "Connection refused",
    "the runtime is not running",
])
def test_a_dead_runtime_is_not_a_network_problem(text):
    failure = classify_install_error(text)
    assert failure.code == "runtime_down"
    assert failure.action == "start_runtime"


def test_an_authorisation_failure_never_keeps_the_key():
    failure = classify_install_error(
        "unauthorized: https://ollama.com/connect?name=x&key=SUPERSECRET123")
    assert failure.code == "needs_auth"
    assert failure.action == "runtime_auth"
    assert "SUPERSECRET123" not in failure.message
    assert "SUPERSECRET123" not in failure.detail
    assert "key=[redacted]" in failure.detail


def test_a_missing_tag_is_a_name_problem():
    failure = classify_install_error("manifest unknown")
    assert failure.code == "model_missing"
    assert failure.action == "check_name"
    assert "tag" in failure.message


def test_a_digest_failure_is_an_integrity_problem():
    failure = classify_install_error("verifying sha256 digest failed: digest mismatch")
    assert failure.code == "integrity"
    assert failure.action == "retry"


def test_an_unknown_failure_keeps_the_detail_but_does_not_invent_a_cause():
    failure = classify_install_error("boom")
    assert failure.code == "unknown"
    assert failure.action == "retry"
    assert failure.detail == "boom"


def test_an_empty_failure_is_stated_as_empty():
    failure = classify_install_error("")
    assert failure.code == "unknown"
    assert failure.detail == "no error text from the runtime"


def test_special_failures_have_their_own_codes():
    assert cancelled_failure().code == "cancelled"
    assert interrupted_failure().code == "interrupted"
    assert unconfirmed_failure().code == "unconfirmed"
    for failure in (cancelled_failure(), interrupted_failure(), unconfirmed_failure()):
        assert failure.action == "retry"
        assert failure.message


def test_redaction_covers_bearer_hf_and_sk_tokens():
    text = ("Authorization: Bearer abcdefgh12345678 token=topsecret "
            "hf_abcdefghijklmnop sk-abcdefghijkl")
    cleaned = redact_secrets(text)
    for secret in ("abcdefgh12345678", "topsecret", "hf_abcdefghijklmnop", "sk-abcdefghijkl"):
        assert secret not in cleaned
    assert "[redacted]" in cleaned


def test_the_failure_json_is_plain_data():
    assert classify_install_error("boom").to_json() == {
        "code": "unknown", "message": "The download failed. Press Install to try again; "
        "the runtime keeps verified parts.", "action": "retry", "detail": "boom"}
