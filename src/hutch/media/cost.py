"""A cost estimate shown before a billable media call, and what it may and may not claim.

The rows are in ``data/media-prices.json`` with the vendor page and the date each was read. An
estimate is arithmetic on a documented rate (a per-image price, a per-second audio rate with the
seconds guessed from the text length); it is never a quote, and the sentence says so. When no rate
was readable the route is ``unpriced`` and the sentence says that instead of printing a plausible
number. Prices change: a row can carry a dated ``changes`` note, which is shown with the estimate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Mapping, Optional

BASES = ("per_item", "per_audio_second", "per_video_second", "unpriced")


@dataclass(frozen=True)
class CostEstimate:
    usd: Optional[float]
    basis: str
    detail: str
    read: str
    source: str
    changes: str = ""

    @property
    def priced(self) -> bool:
        return self.usd is not None

    def sentence(self) -> str:
        if self.usd is None:
            return f"cost unknown: {self.detail} (read {self.read}); check the provider account"
        extra = f"; {self.changes}" if self.changes else ""
        return (f"estimated about ${self.usd:.4f} ({self.detail}, read {self.read}){extra}; an "
                "estimate, not a quote - the provider account is authoritative")

    def as_dict(self) -> dict[str, Any]:
        return {"usd": self.usd, "basis": self.basis, "detail": self.detail, "read": self.read,
                "source": self.source, "changes": self.changes, "priced": self.priced}


def load_prices() -> dict[str, dict[str, Any]]:
    path = resources.files("hutch") / "data" / "media-prices.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["prices"]
    for key, row in rows.items():
        if row.get("basis") not in BASES:
            raise ValueError(f"media price {key!r}: basis must be one of {BASES}")
    return rows


def estimate(price_key: str, request: Mapping[str, Any]) -> CostEstimate:
    """The estimate for one request against a route's price row (unpriced when absent)."""
    row = load_prices().get(price_key)
    if row is None:
        return CostEstimate(None, "unpriced", "no price row is recorded for this route", "", "")
    common = {"detail": row.get("detail", ""), "read": row.get("read", ""),
              "source": row.get("source", ""), "changes": row.get("changes", "")}
    basis = row["basis"]
    usd = _usd(basis, row, request)
    return CostEstimate(usd, basis if usd is not None else "unpriced", **common)


def _usd(basis: str, row: Mapping[str, Any], request: Mapping[str, Any]) -> Optional[float]:
    if basis == "per_item":
        return float(row["usd"])
    if basis == "per_audio_second":
        chars = len(str(request.get("prompt") or ""))
        seconds = max(1.0, chars / float(row.get("chars_per_second", 15)))
        return round(seconds * float(row["usd_per_second"]), 6)
    if basis == "per_video_second":
        seconds = request.get("seconds")
        if not isinstance(seconds, (int, float)):
            return None
        return round(float(seconds) * float(row["usd_per_second"]), 6)
    return None
