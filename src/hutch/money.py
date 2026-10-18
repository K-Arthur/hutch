"""Money arithmetic for a ledger that must never invent or lose a charge (SR-2).

Why Decimal and not float: provider rates arrive as exact decimal strings ("0.00003" USD per token) and
sub-cent calls are routine. Binary floats cannot represent those values exactly, so cap comparisons and
reservation rounding can drift in either direction. Every money operation in this module is Decimal.

Canonical unit
--------------
The ledger unit is the **nano-USD** (``0.000000001`` USD, 9 decimal places). Provider usage can be smaller
than a micro-dollar per call; six places silently turned a reported ``$0.0000004`` into zero. Values are
quantized to nano-USD:

* **reservations round up** (``quantize_up``): admission must never under-estimate the amount it holds;
* **settlements and reported values round half-up** (``quantize``): an actual charge is recorded as near
  to its reported value as the ledger unit allows;
* **display never hides a nonzero charge** (``format_usd``): a sub-cent amount shows its leading digits
  instead of ``$0.00``.

Storage boundary
----------------
The SQLite columns are legacy ``REAL`` (float) columns. Every write goes through ``to_store`` (a
nano-quantized Decimal converted to float) and every read through ``from_store`` (the float converted
back through its shortest decimal string and re-quantized). Existing six-decimal ledger values round-trip
unchanged; new values retain nine decimal places. Comparisons carry ``TOL_USD = 1e-12`` for float
conversion noise.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from typing import Iterable, Optional, Union

MICRO = Decimal("0.000001")  # retained for callers that explicitly need micro-dollar units
NANO_USD = Decimal("0.000000001")
ZERO = Decimal("0")
USD = "USD"
#: comparison tolerance for values that round-trip through REAL columns
TOL_USD = Decimal("0.000000000001")

NumberLike = Union[int, float, str, Decimal]


class MoneyError(ValueError):
    """A value that cannot be a USD amount (negative, non-finite, malformed)."""


def parse_usd(value: NumberLike, *, field: str = "amount") -> Optional[Decimal]:
    """Parse a USD value without ever guessing. Decimal/str parse exactly; float goes through its repr.

    ``None`` stays ``None`` (an unset threshold is distinct from zero). Booleans, negatives, NaN and
    infinities are rejected: they cannot be legitimate money.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise MoneyError(f"{field} must be a USD amount, not a boolean")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError(f"{field} is not a valid USD amount: {value!r}") from exc
    if not parsed.is_finite():
        raise MoneyError(f"{field} must be finite, got {value!r}")
    if parsed < 0:
        raise MoneyError(f"{field} must be non-negative, got {value!r}")
    return parsed


def quantize(value: Decimal) -> Decimal:
    """Round half-up to nano-USD for values being recorded (actual charges, reported costs)."""
    return value.quantize(NANO_USD, rounding=ROUND_HALF_UP)


def quantize_up(value: Decimal) -> Decimal:
    """Round up to nano-USD for values being held. Admission never under-reserves."""
    return value.quantize(NANO_USD, rounding=ROUND_CEILING)


def to_store(value: Optional[Decimal]) -> Optional[float]:
    """Convert a recorded (half-up) amount to the legacy REAL column representation."""
    if value is None:
        return None
    return float(quantize(value))


def to_store_reserved(value: Optional[Decimal]) -> Optional[float]:
    """Convert a held amount to the legacy REAL column representation, rounding up."""
    if value is None:
        return None
    return float(quantize_up(value))


def from_store(value: Optional[float]) -> Decimal:
    """Read a legacy REAL amount back into Decimal nano-USD (missing/NULL reads as zero)."""
    if value is None:
        return ZERO
    return quantize(Decimal(str(value)))


def usd_from_per_million(rate_per_million: Optional[Decimal], tokens: int) -> Decimal:
    """Cost of ``tokens`` at a rate quoted in USD per 1M tokens. Negative token counts are clamped."""
    if rate_per_million is None or tokens <= 0:
        return ZERO
    return rate_per_million * Decimal(int(tokens)) / Decimal(1_000_000)


def usd_from_per_token(rate_per_token: Optional[Decimal], tokens: int) -> Decimal:
    """Cost of ``tokens`` at a rate quoted in USD per single token (the OpenRouter catalog unit)."""
    if rate_per_token is None or tokens <= 0:
        return ZERO
    return rate_per_token * Decimal(int(tokens))


def per_million_from_per_token(rate_per_token: Decimal) -> Decimal:
    """Convert USD/token to USD/1M tokens for display next to the file-based price book."""
    return rate_per_token * Decimal(1_000_000)


def call_cost(*, prompt_tokens: int, completion_tokens: int,
              input_per_million: Decimal, output_per_million: Decimal,
              cache_read_per_million: Optional[Decimal] = None, cache_write_per_million: Optional[Decimal] = None,
              cached_tokens: int = 0, cache_write_tokens: int = 0, request_fee: Decimal = ZERO) -> Decimal:
    """The unrounded Decimal cost of one call, with cache tokens split out of the prompt count.

    ``cached_tokens`` and ``cache_write_tokens`` are billed at their own rates and removed from the
    uncached input; the uncached count is clamped at zero so inconsistent provider usage can never
    produce a negative input charge. ``cache_read`` defaults to the input rate when the caller has no
    separately published read rate: charging cached tokens at full price over-reserves, which is the
    conservative direction for admission (settlement passes the provider's own numbers instead).
    """
    prompt = max(0, int(prompt_tokens))
    cached = min(max(0, int(cached_tokens)), prompt)
    written = min(max(0, int(cache_write_tokens)), prompt - cached)
    uncached = prompt - cached - written
    read_rate = cache_read_per_million if cache_read_per_million is not None else input_per_million
    write_rate = cache_write_per_million if cache_write_per_million is not None else input_per_million
    fee = parse_usd(request_fee, field="request fee") or ZERO
    return (usd_from_per_million(input_per_million, uncached)
            + usd_from_per_million(read_rate, cached)
            + usd_from_per_million(write_rate, written)
            + usd_from_per_million(output_per_million, int(completion_tokens))
            + fee)


def sum_usd(values: Iterable[Optional[Decimal]]) -> Decimal:
    return sum((v for v in values if v is not None), ZERO)


def format_usd(value: Optional[NumberLike], *, places: Optional[int] = None) -> str:
    """Human formatting that never shows a nonzero charge as free.

    Up to 6 decimal places for sub-cent amounts, 4 below $1,000, otherwise 2. A value that is nonzero but
    would round to all zeros at the chosen precision is shown with more places (never ``$0.00``).
    """
    if value is None:
        return "unknown"
    amount = parse_usd(value) or ZERO
    if places is None:
        if amount == ZERO:
            places = 2
        elif amount < Decimal("0.01"):
            places = min(9, max(6, -amount.normalize().as_tuple().exponent))
        elif amount < Decimal("1000"):
            places = 4
        else:
            places = 2
    text = f"{amount:.{places}f}"
    if amount != ZERO and Decimal(text) == ZERO:
        # A nonzero value below one ledger unit must never render as free.
        text = f"{amount:.9f}"
        if Decimal(text) == ZERO:
            return f"<${NANO_USD:.9f}"
    return f"${text}"


def micro_units(value: NumberLike, *, reserved: bool = False) -> int:
    """Exact integer micro-USD units for integrations that explicitly need six-place values."""
    amount = parse_usd(value)
    if amount is None:
        return 0
    rounded = amount.quantize(MICRO, rounding=ROUND_CEILING if reserved else ROUND_HALF_UP)
    return int(rounded / MICRO)
