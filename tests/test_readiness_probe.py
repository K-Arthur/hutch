from datetime import datetime, timezone

import pytest

from hutch import route_readiness as rr
from hutch.connections import ConnectionBook
from hutch.providers.connection import probe_connection_typed
from tests.support.fake_provider import (FakeProvider, Step, closed_port_url, error_body)

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
KEY = "sk-test-SECRET-1234567890"


@pytest.fixture()
def make(tmp_path):
    servers = []

    def build(models=None, chat=None, base_url=None):
        fake = FakeProvider(models, chat)
        servers.append(fake)
        book = ConnectionBook(tmp_path / "state")
        book.add("custom-openai", "probe-route", base_url=base_url or fake.base_url)
        book.set_key("probe-route", KEY)
        return book, fake

    yield build
    for fake in servers:
        fake.close()


def meta(book):
    return probe_connection_typed(book, "probe-route", now=NOW)


def gen(book, model="model-a"):
    return probe_connection_typed(book, "probe-route", mode=rr.MODE_GENERATION, model=model, now=NOW)


def test_metadata_success_is_saved_unverified_and_lists_models(make):
    book, fake = make()
    result = meta(book)
    assert result.state == rr.SAVED_UNVERIFIED and result.models == ("model-a", "model-b")
    assert fake.paths() == ["GET /v1/models"]  # no generation was made


def test_models_200_but_generation_401_is_invalid_credential_not_verified(make):
    book, fake = make(chat=Step(401, error_body("Incorrect API key provided")))
    assert meta(book).state == rr.SAVED_UNVERIFIED
    result = gen(book)
    assert result.state == rr.INVALID_CREDENTIAL and result.http_status == 401
    assert result.state != rr.VERIFIED


def test_generation_success_is_the_only_verified_path(make):
    book, fake = make()
    result = gen(book)
    assert result.state == rr.VERIFIED and result.models == ("model-a",)
    chat = [r for r in fake.requests if r["method"] == "POST"]
    assert len(chat) == 1  # one attempt, no hidden retry
    assert '"max_tokens":1' in chat[0]["body"] or '"max_tokens": 1' in chat[0]["body"]
    assert "tools" not in chat[0]["body"]


@pytest.mark.parametrize("step,state", [
    (Step(402, error_body("insufficient credits")), rr.NO_CREDIT),
    (Step(403, error_body("forbidden")), rr.PERMISSION_DENIED),
    (Step(429, error_body("slow down"), {"Retry-After": "120"}), rr.RATE_LIMITED),
    (Step(503, error_body("line one\nline two\nline three " + "z" * 900)), rr.UNAVAILABLE),
    (Step(404, error_body("The model `model-a` does not exist")), rr.MODEL_MISSING),
    (Step(400, error_body("unsupported parameter")), rr.INVALID_ROUTE),
])
def test_generation_failures_map_to_distinct_states(make, step, state):
    book, _ = make(chat=step)
    result = gen(book)
    assert result.state == state
    assert len(result.detail) <= rr.DETAIL_LIMIT


def test_retry_after_is_carried_from_the_provider(make):
    book, _ = make(chat=Step(429, error_body("slow down"), {"Retry-After": "120"}))
    result = gen(book)
    assert result.retry_after == 120 and rr.retry_in_seconds(result, NOW) == 120


@pytest.mark.parametrize("step", [Step(401, error_body("bad")), Step(403, error_body("no"))])
def test_metadata_auth_failures_are_typed(make, step):
    book, _ = make(models=step)
    result = meta(book)
    assert result.state in (rr.INVALID_CREDENTIAL, rr.PERMISSION_DENIED)


def test_unreachable_endpoint_is_provider_unreachable(make):
    book, _ = make(base_url=closed_port_url())
    assert meta(book).state == rr.UNREACHABLE
    assert gen(book).state == rr.UNREACHABLE


def test_the_stored_key_never_appears_in_detail(make):
    book, _ = make(chat=Step(401, error_body(f"Incorrect API key provided: {KEY}")))
    result = gen(book)
    assert KEY not in result.detail and KEY not in repr(result)


def test_missing_key_is_invalid_credential(make, tmp_path):
    book, _ = make()
    book.clear_key("probe-route")
    assert meta(book).state == rr.INVALID_CREDENTIAL


def test_unknown_connection_and_missing_model(make):
    book, _ = make()
    assert probe_connection_typed(book, "nope", now=NOW).state == rr.INVALID_ROUTE
    assert probe_connection_typed(book, "probe-route", mode=rr.MODE_GENERATION, now=NOW).state == rr.MODEL_MISSING


def test_legacy_check_connection_is_unchanged(make):
    from hutch.providers.connection import check_connection
    book, _ = make()
    check = check_connection(book, "probe-route")
    assert check.ok and check.verified and check.models == ["model-a", "model-b"]
