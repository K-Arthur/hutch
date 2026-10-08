"""Versioned, evidence-backed provider route compatibility contracts."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from importlib import resources
from typing import Any
from urllib.parse import urlsplit


_STATES = {"supported", "experimental", "unavailable", "blocked"}
_ROUTE_FIELDS = {
    "id", "title", "state", "harness", "api_shape", "auth_flow", "models", "streaming", "tool_calls",
    "structured_output", "vision", "context_limits", "cancellation", "usage_reporting", "quota_reporting",
    "retention", "hutch_request_mapping", "verification", "verified_on", "policy_evidence",
}


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@lru_cache(maxsize=1)
def compatibility_matrix() -> dict[str, Any]:
    """Read and validate the bundled matrix before exposing it to CLI/API clients."""
    path = resources.files("hutch").joinpath("data", "compat.json")
    try:
        matrix = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"the provider compatibility matrix cannot be read: {exc}") from exc
    if not isinstance(matrix, dict) or matrix.get("version") != 1 or not _valid_date(matrix.get("reviewed_on")):
        raise RuntimeError("the provider compatibility matrix has an invalid version or review date")
    routes = matrix.get("routes")
    if not isinstance(routes, list) or not routes:
        raise RuntimeError("the provider compatibility matrix has no routes")
    ids: set[str] = set()
    for route in routes:
        if not isinstance(route, dict) or not _ROUTE_FIELDS <= route.keys():
            raise RuntimeError("a provider compatibility route is missing required fields")
        route_id = route["id"]
        if not isinstance(route_id, str) or not route_id or route_id in ids:
            raise RuntimeError("provider compatibility route ids must be non-empty and unique")
        ids.add(route_id)
        if not isinstance(route["state"], str) or route["state"] not in _STATES or not _valid_date(route["verified_on"]):
            raise RuntimeError(f"provider compatibility route {route_id!r} has an invalid state or review date")
        mapping = route["hutch_request_mapping"]
        if not isinstance(mapping, dict) or not all(
            isinstance(mapping.get(key), list) and all(isinstance(item, str) for item in mapping[key])
            for key in ("sent", "omitted")
        ):
            raise RuntimeError(f"provider compatibility route {route_id!r} has an invalid request mapping")
        evidence = route["policy_evidence"]
        if not isinstance(evidence, list) or not evidence:
            raise RuntimeError(f"provider compatibility route {route_id!r} has no policy evidence")
        for source in evidence:
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("title"), str)
                or not source["title"].strip()
                or not isinstance(source.get("url"), str)
                or not _valid_date(source.get("observed_on"))
            ):
                raise RuntimeError(f"provider compatibility route {route_id!r} has malformed evidence")
            try:
                url = urlsplit(source["url"])
                if url.scheme != "https" or not url.hostname or url.username or url.password:
                    raise ValueError
            except (TypeError, ValueError):
                raise RuntimeError(f"provider compatibility route {route_id!r} has a non-HTTPS evidence URL") from None
    return matrix
