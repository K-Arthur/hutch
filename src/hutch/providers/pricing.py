"""Hosted prices live in an editable file with a verified-on date shown in the UI (LM-14).

Why a file and not constants: vendor prices move (Sonnet 5 had an "introductory" price that became permanent;
Opus 5.5 undercut Opus 5), and the two products Hutch is benchmarked against both hide their per-token rates.
A cost number you cannot trace to a source and a date is worse than none, so every row carries both, and rows
older than STALE_DAYS are flagged. Unknown hosted models have *no* price: anything that needs a price (a spend
cap, an estimate) refuses rather than guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Optional

STALE_DAYS = 90
LOCAL_PROVIDERS = {"ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm", "mock"}


@dataclass
class Price:
    model: str                      # "provider/model"
    input: float
    output: float
    cache_read: Optional[float] = None
    cache_write: Optional[float] = None
    verified_on: str = ""
    source: str = ""
    note: str = ""
    user: bool = False              # from the user's file

    @property
    def age_days(self) -> Optional[int]:
        try:
            return (date.today() - datetime.fromisoformat(self.verified_on).date()).days
        except ValueError:
            return None

    @property
    def stale(self) -> bool:
        age = self.age_days
        return age is None or age > STALE_DAYS


def bundled_path() -> Path:
    return Path(str(resources.files("hutch") / "data" / "prices.json"))


class PriceBook:
    def __init__(self, user_path: Optional[Path] = None):
        self.user_path = user_path
        self.prices: dict[str, Price] = {}
        self.errors: list[str] = []
        #: connections billed flat (subscription / free): no per-call cost, but usage is still tracked
        self.flat_providers: set[str] = set()
        self._load(bundled_path(), user=False)
        if user_path and user_path.exists():
            self._load(user_path, user=True)

    def _load(self, path: Path, user: bool) -> None:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            self.errors.append(f"{path}: {exc}")
            return
        for key, row in (data.get("models") or {}).items():
            try:
                self.prices[key] = Price(
                    model=key, input=float(row["input"]), output=float(row["output"]),
                    cache_read=_opt(row.get("cache_read")), cache_write=_opt(row.get("cache_write")),
                    verified_on=str(row.get("verified_on", "")), source=str(row.get("source", "")),
                    note=str(row.get("note", "")), user=user)
            except (KeyError, TypeError, ValueError) as exc:
                self.errors.append(f"{path}: row '{key}' is invalid ({exc})")

    @staticmethod
    def is_local(provider: str) -> bool:
        return provider in LOCAL_PROVIDERS

    def lookup(self, provider: str, model: str) -> Optional[Price]:
        return self.prices.get(f"{provider}/{model}")

    def has_price(self, provider: str, model: str) -> bool:
        return (self.is_local(provider) or provider in self.flat_providers
                or self.lookup(provider, model) is not None)

    def cost(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int,
             cached_tokens: int = 0, cache_write_tokens: int = 0) -> Optional[float]:
        """USD for one call, or None when the model has no price. Local models are free."""
        if self.is_local(provider) or provider in self.flat_providers:
            return 0.0
        p = self.lookup(provider, model)
        if p is None:
            return None
        uncached = max(0, prompt_tokens - cached_tokens - cache_write_tokens)
        read_rate = p.cache_read if p.cache_read is not None else p.input * 0.1
        write_rate = p.cache_write if p.cache_write is not None else p.input * 1.25
        return (uncached * p.input + cached_tokens * read_rate + cache_write_tokens * write_rate
                + completion_tokens * p.output) / 1_000_000.0

    def estimate_run_ceiling(self, provider: str, model: str, prompt_tokens: int, max_turn_tokens: int,
                             max_steps: int) -> Optional[float]:
        """Local estimate before a run starts; provider tokenization and final billing can differ."""
        return self.cost(provider, model, prompt_tokens * max_steps, max_turn_tokens * max_steps)

    def rows(self) -> list[Price]:
        return sorted(self.prices.values(), key=lambda p: p.model)

    # ------------------------------------------------------------- editing (LM-14)

    def _user_rows(self) -> dict:
        if not self.user_path or not self.user_path.exists():
            return {}
        try:
            return dict(json.loads(self.user_path.read_text()).get("models") or {})
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_user(self, rows: dict) -> None:
        if not self.user_path:
            raise ValueError("no user price file configured")
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.user_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"_readme": "Your price overrides, USD per 1M tokens. Rows here win over the bundled "
                                              "ones. Edited by hutch or by hand.", "models": rows}, indent=2) + "\n")
        tmp.replace(self.user_path)

    def set_price(self, model: str, input: float, output: float, cache_read: Optional[float] = None,
                  cache_write: Optional[float] = None, source: str = "", note: str = "") -> Price:
        """Add or override a row in the user's file, stamped today. Rejects what would make cost maths wrong."""
        provider, _, name = model.partition("/")
        if not provider or not name:
            raise ValueError("a price row is keyed 'provider/model', for example anthropic/claude-opus-5-5")
        if self.is_local(provider):
            raise ValueError(f"{provider} models run on your machine and cost nothing; they need no price row")
        for label, v in (("input", input), ("output", output), ("cache_read", cache_read), ("cache_write", cache_write)):
            if v is not None and (v != v or v < 0 or v > 100_000):
                raise ValueError(f"{label} must be a price in USD per 1M tokens between 0 and 100,000 (got {v})")
        rows = self._user_rows()
        row = {"input": float(input), "output": float(output), "verified_on": date.today().isoformat(),
               "source": source.strip() or "entered by you"}
        if cache_read is not None:
            row["cache_read"] = float(cache_read)
        if cache_write is not None:
            row["cache_write"] = float(cache_write)
        if note.strip():
            row["note"] = note.strip()
        rows[model] = row
        self._write_user(rows)
        price = Price(model=model, input=row["input"], output=row["output"], cache_read=_opt(row.get("cache_read")),
                      cache_write=_opt(row.get("cache_write")), verified_on=row["verified_on"], source=row["source"],
                      note=row.get("note", ""), user=True)
        self.prices[model] = price
        return price

    def remove_override(self, model: str) -> bool:
        """Drop the user's row; the bundled one (if any) applies again."""
        rows = self._user_rows()
        if model not in rows:
            return False
        del rows[model]
        self._write_user(rows)
        self.prices.pop(model, None)
        bundled = PriceBook()
        if model in bundled.prices:
            self.prices[model] = bundled.prices[model]
        return True


def _opt(v) -> Optional[float]:
    return None if v is None else float(v)
