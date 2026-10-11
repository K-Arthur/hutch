"""Live OpenRouter endpoint quotes: Decimal precision, TTL, single-flight, and eligibility (SR-2)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hutch.providers.openrouter_pricing import (
    ModelQuote,
    OpenRouterPricing,
    parse_endpoints_payload,
    split_model_id,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def endpoint(prompt: str, completion: str, *, request: str = "0", context: int = 128000,
             status: int = 0, tools: bool = True, name: str = "Vendor A",
             cache_read: str | None = None, cache_write: str | None = None) -> dict:
    pricing = {"prompt": prompt, "completion": completion, "request": request}
    if cache_read is not None:
        pricing["input_cache_read"] = cache_read
    if cache_write is not None:
        pricing["input_cache_write"] = cache_write
    return {"name": name, "provider_name": name, "context_length": context, "max_completion_tokens": 4096,
            "pricing": pricing, "status": status,
            "supported_parameters": (["temperature", "tools"] if tools else ["temperature"])}


def payload(*endpoints: dict, model: str = "acme/model-1") -> dict:
    return {"data": {"id": model, "name": model, "endpoints": list(endpoints)}}


def test_worst_case_is_the_max_of_whole_endpoint_costs_not_mixed_rates():
    quote = parse_endpoints_payload(
        payload(endpoint("0.0000001", "0.0000004", name="cheap-in"),      # $0.10/M in, $0.40/M out
                endpoint("0.0000002", "0.0000003", name="cheap-out")),    # $0.20/M in, $0.30/M out
        "acme/model-1", fetched_at=NOW)
    # 1000 prompt + 100 completion: A = 0.00014, B = 0.00023 -> the max whole cost wins
    assert quote.worst_case(1000, 100) == Decimal("0.000230")


def test_cache_and_request_fees_are_included_and_rounded_up():
    quote = parse_endpoints_payload(
        payload(endpoint("0.000003", "0.000015", request="0.002",
                         cache_read="0.0000003", cache_write="0.00000375")),
        "acme/model-1", fetched_at=NOW)
    cost = quote.worst_case(1000, 200, cached_tokens=200, cache_write_tokens=100,
                            eligible=lambda endpoint: True)
    assert cost == Decimal("0.007535")


def test_invalid_or_missing_prices_make_an_endpoint_ineligible():
    quote = parse_endpoints_payload(
        payload(endpoint("0.000001", "0.000002"),
                endpoint("not-a-number", "0.000002", name="broken"),
                {"name": "no pricing", "provider_name": "X", "pricing": None}),
        "acme/model-1", fetched_at=NOW)
    assert len(quote.endpoints) == 1
    with pytest.raises(ValueError):
        parse_endpoints_payload(payload(endpoint("-1", "0.000002")), "acme/model-1", fetched_at=NOW)
    with pytest.raises(ValueError):
        parse_endpoints_payload({"data": {"endpoints": []}}, "acme/model-1", fetched_at=NOW)


def test_negative_or_nonfinite_rates_are_rejected_by_parse():
    for bad in ("-0.1", "NaN", "Infinity", None):
        with pytest.raises(ValueError):
            parse_endpoints_payload(payload(endpoint(bad, "0.000002")), "acme/model-1", fetched_at=NOW)


def test_fresh_quote_is_reused_within_ttl_and_refetched_after():
    calls: list[str] = []
    clock = [NOW]

    def fetcher(model):
        calls.append(model)
        return payload(endpoint("0.000001", "0.000002"))

    service = OpenRouterPricing("https://router.example/api/v1", fetcher=fetcher, clock=lambda: clock[0])
    first = service.quote("acme/model-1")
    assert first is not None and not first.stale
    clock[0] = NOW + timedelta(minutes=5)
    assert service.quote("acme/model-1") is first     # cached within the 15-minute TTL
    assert calls == ["acme/model-1"]
    clock[0] = NOW + timedelta(minutes=16)
    assert service.quote("acme/model-1") is not None
    assert calls == ["acme/model-1", "acme/model-1"]


def test_a_failed_refetch_keeps_the_last_quote_labeled_stale():
    clock = [NOW]
    fail = [False]

    def fetcher(model):
        if fail[0]:
            raise OSError("network down")
        return payload(endpoint("0.000001", "0.000002"))

    service = OpenRouterPricing("https://router.example/api/v1", fetcher=fetcher, clock=lambda: clock[0])
    assert service.quote("acme/model-1") is not None
    fail[0] = True
    clock[0] = NOW + timedelta(minutes=20)
    stale = service.quote("acme/model-1")
    assert stale is not None and stale.stale
    assert "network down" in service.last_error
    assert service.quote("acme/model-1", allow_stale=False) is None


def test_single_flight_dedupes_concurrent_refreshes():
    calls: list[str] = []

    def fetcher(model):
        calls.append(model)
        time.sleep(0.2)
        return payload(endpoint("0.000001", "0.000002"))

    service = OpenRouterPricing("https://router.example/api/v1", fetcher=fetcher, clock=lambda: NOW)
    results: list[ModelQuote | None] = []

    def worker():
        results.append(service.quote("acme/model-1"))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(result is not None for result in results)
    assert calls == ["acme/model-1"], "concurrent callers share one fetch"


def test_degraded_and_context_capped_endpoints_can_be_excluded_by_eligibility():
    quote = parse_endpoints_payload(
        payload(endpoint("0.0000001", "0.0000001", status=-1, name="degraded"),
                endpoint("0.0000002", "0.0000002", context=8192, name="small"),
                endpoint("0.0000003", "0.0000003", context=200000, name="big")),
        "acme/model-1", fetched_at=NOW)
    assert quote.worst_case(1000, 100) == Decimal("0.00033")                     # degraded excluded; max = big
    eligible = lambda endpoint: endpoint.context_length >= 100000 or endpoint.context_length == 0
    assert quote.worst_case(1000, 100, eligible=eligible) == Decimal("0.00033")  # only the 200k one


def test_split_model_id_handles_variants_and_latest_aliases():
    assert split_model_id("anthropic/claude-sonnet-4.5") == ("anthropic", "claude-sonnet-4.5")
    assert split_model_id("~anthropic/claude-sonnet-latest") == ("anthropic", "claude-sonnet-latest")
    assert split_model_id("acme/model-1:nitro") == ("acme", "model-1")
