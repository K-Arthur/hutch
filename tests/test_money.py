"""Money arithmetic: exact parsing, conservative rounding, and honest display (SR-2)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hutch import money


def test_provider_decimal_strings_parse_exactly():
    assert money.parse_usd("0.00003") == Decimal("0.00003")
    assert money.parse_usd("0.0000005") == Decimal("5E-7")
    assert money.parse_usd(Decimal("12.345678")) == Decimal("12.345678")
    assert money.parse_usd("1.25") + money.parse_usd("2.75") == Decimal("4")


def test_float_input_goes_through_its_shortest_repr():
    # 0.1 as a float is not exactly 0.1, but its repr is, and that is what an operator typed.
    assert money.parse_usd(0.1) == Decimal("0.1")


def test_missing_is_unset_and_invalid_is_rejected():
    assert money.parse_usd(None) is None
    for bad in ("-1", -0.01, float("nan"), float("inf"), "abc", True):
        with pytest.raises(money.MoneyError):
            money.parse_usd(bad)


@given(st.decimals(min_value=0, max_value=10**6, places=12))
def test_reservation_rounding_never_under_reserves(value):
    assert money.quantize_up(value) >= value


@given(st.decimals(min_value=0, max_value=10**6, places=12))
def test_store_roundtrip_preserves_nano_precision(value):
    recorded = money.quantize(value)
    assert abs(money.from_store(money.to_store(recorded)) - recorded) <= money.NANO_USD / 2


def test_per_token_and_per_million_conversions_are_exact():
    assert money.usd_from_per_token(Decimal("0.00006"), 1_000_000) == Decimal("60")
    assert money.usd_from_per_million(Decimal("3"), 1_000_000) == Decimal("3")
    assert money.per_million_from_per_token(Decimal("0.00003")) == Decimal("30")
    assert money.usd_from_per_token(None, 12345) == 0
    assert money.usd_from_per_million(Decimal("5"), -3) == 0


def test_call_cost_splits_cache_tokens_out_of_the_prompt():
    cost = money.call_cost(
        prompt_tokens=1000, completion_tokens=200,
        input_per_million=Decimal("3"), output_per_million=Decimal("15"),
        cache_read_per_million=Decimal("0.3"), cache_write_per_million=Decimal("3.75"),
        cached_tokens=200, cache_write_tokens=100, request_fee=Decimal("0.002"))
    # 700*3 + 200*0.3 + 100*3.75 + 200*15 per million, plus the flat request fee
    assert cost == Decimal("0.007535")


def test_call_cost_without_published_cache_rates_charges_input_rate():
    cost = money.call_cost(prompt_tokens=1000, completion_tokens=0,
                           input_per_million=Decimal("3"), output_per_million=Decimal("15"),
                           cached_tokens=500)
    assert cost == Decimal("0.003")  # conservative: no unverified discount


def test_call_cost_clamps_impossible_provider_usage():
    cost = money.call_cost(prompt_tokens=100, completion_tokens=0,
                           input_per_million=Decimal("3"), output_per_million=Decimal("15"),
                           cached_tokens=500, cache_write_tokens=500)
    # more cached tokens than a prompt is impossible; the prompt is still charged once at the input rate
    assert cost == Decimal("0.0003")


def test_format_never_hides_a_nonzero_charge():
    assert money.format_usd(0) == "$0.00"
    assert money.format_usd("0.15") == "$0.1500"
    assert money.format_usd("0.000001") == "$0.000001"
    assert money.format_usd("0.0000001") == "$0.0000001"
    assert money.format_usd(None) == "unknown"
    assert money.format_usd(1234.5) == "$1234.50"


def test_micro_units_are_fixed_point():
    assert money.micro_units("0.15") == 150_000
    assert money.micro_units("0.0000004", reserved=True) == 1
    assert money.micro_units("0.0000004", reserved=False) == 0


def test_sub_micro_provider_charge_survives_sqlite_round_trip():
    charge = Decimal("0.0000004")
    stored = money.to_store(charge)
    assert stored != 0
    assert money.from_store(stored) == charge
    assert money.format_usd(money.from_store(stored)) == "$0.0000004"


def test_sum_usd_skips_unknowns():
    assert money.sum_usd([Decimal("0.1"), None, Decimal("0.2")]) == Decimal("0.3")
