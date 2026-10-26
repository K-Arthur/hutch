"""Allowlisted OpenRouter routing controls, configured by the operator.

These are endpoint filters, not a dollar budget. Hutch still reserves the full
worst-case call cost and reconciles provider-reported usage independently.
"""

from __future__ import annotations

import copy
import math


def validate_policy(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("OpenRouter routing must be an object")
    allowed = {"order", "allow_fallbacks", "require_parameters", "data_collection", "zdr", "max_price"}
    if set(value) - allowed:
        raise ValueError("unsupported OpenRouter routing control")
    for key in ("allow_fallbacks", "require_parameters", "zdr"):
        if key in value and type(value[key]) is not bool:
            raise ValueError(f"OpenRouter {key} must be a boolean")
    if "data_collection" in value and value["data_collection"] not in ("allow", "deny"):
        raise ValueError("OpenRouter data_collection must be allow or deny")
    if "order" in value:
        order = value["order"]
        if not isinstance(order, list) or not 1 <= len(order) <= 16 or any(
                not isinstance(item, str) or not item.strip() or len(item) > 100 for item in order):
            raise ValueError("OpenRouter order must contain 1-16 provider identifiers")
    if "max_price" in value:
        prices = value["max_price"]
        if not isinstance(prices, dict) or not prices or set(prices) - {"prompt", "completion", "request"}:
            raise ValueError("OpenRouter max_price requires prompt/completion per million or request prices")
        for price in prices.values():
            try:
                finite = math.isfinite(price) if type(price) in (int, float) else False
            except OverflowError:
                finite = False
            if not finite or price < 0:
                raise ValueError("OpenRouter maximum prices must be finite non-negative numbers")
    return copy.deepcopy(value)
