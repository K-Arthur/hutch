import pytest

from hutch.connections import ConnectionBook
from hutch.connections_service import (
    acknowledge_terms,
    key_source_view,
    normalise_and_validate_key,
    store_key,
    terms_view,
)


def test_key_normalisation_clean():
    check = normalise_and_validate_key("  sk-1234567890abcdef  \n")
    assert check.kind == "ok"
    assert check.value == "sk-1234567890abcdef"


def test_key_normalisation_bearer_prefix():
    check = normalise_and_validate_key("Bearer sk-test-key-123")
    assert check.kind == "ok"
    assert check.value == "sk-test-key-123"

    check_case = normalise_and_validate_key("bearer   sk-test-key-456")
    assert check_case.kind == "ok"
    assert check_case.value == "sk-test-key-456"


def test_key_normalisation_empty_or_whitespace():
    assert normalise_and_validate_key("").kind == "empty"
    assert normalise_and_validate_key("   \n\t ").kind == "empty"
    assert normalise_and_validate_key("Bearer   ").kind == "empty"


def test_key_normalisation_too_long():
    long_str = "x" * 4097
    check = normalise_and_validate_key(long_str)
    assert check.kind == "too_long"
    assert "maximum 4096 bytes" in check.message


def test_key_normalisation_control_chars():
    check = normalise_and_validate_key("sk-key\x00with-null")
    assert check.kind == "malformed"
    assert "invalid control" in check.message

    check_crlf = normalise_and_validate_key("sk-part1\r\nsk-part2")
    assert check_crlf.kind == "malformed"


def test_store_key_and_source_view(tmp_path):
    book = ConnectionBook(tmp_path)
    book.add("openai-api", "my-openai")
    
    assert key_source_view(book, "my-openai") == "secret.missing"
    
    res = store_key(book, "my-openai", "  sk-valid-key  ")
    assert res.kind == "stored"
    assert book.has_key("my-openai")
    assert key_source_view(book, "my-openai") == "secret.stored"


class FakeStore:
    def __init__(self):
        self._data = {}

    def kv_get(self, key):
        return self._data.get(key)

    def kv_set(self, key, value):
        self._data[key] = value


def test_terms_acknowledgement(tmp_path):
    book = ConnectionBook(tmp_path)
    # opencode-go requires terms ack
    book.add("opencode-go", "opencode-go")
    store = FakeStore()

    view = terms_view(book, store, "opencode-go")
    assert view.status == "consent.required"
    assert view.notice != ""

    # Disagreeing fails
    disagree = acknowledge_terms(book, store, "opencode-go", agree=False)
    assert disagree.kind == "required"

    # Agreeing marks it current
    agree = acknowledge_terms(book, store, "opencode-go", agree=True)
    assert agree.kind == "acknowledged"

    view_after = terms_view(book, store, "opencode-go")
    assert view_after.status == "consent.current"
    assert view_after.acknowledged_at != ""
