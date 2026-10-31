"""Parsing an OpenAI-shaped model catalogue, shared by the providers that read one.

Kept separate from the adapter so the rules - a bounded list, string ids only, a strict id shape, sorted
and de-duplicated - are testable without a transport, and so ``openai_compat.py`` does not grow each time
another plan publishes a slightly different catalogue envelope.
"""

from __future__ import annotations

import re
from typing import Any

from .base import ProviderError

MAX_DISCOVERED_MODELS = 5000
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/~@-]{0,200}$")


def parse_catalog_ids(payload: Any, provider_name: str) -> list[str]:
    """Model ids from a ``{"data": [{"id": ...}]}`` catalogue, refusing anything unexpected."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderError("other", f"{provider_name} returned an invalid model catalog", provider=provider_name)
    if len(payload["data"]) > MAX_DISCOVERED_MODELS:
        raise ProviderError("other", f"{provider_name}'s model catalog exceeded Hutch's discovery limit",
                            provider=provider_name)
    ids = {row.get("id") for row in payload["data"] if isinstance(row, dict)
           and isinstance(row.get("id"), str) and MODEL_ID.fullmatch(row["id"])}
    return sorted(ids)
