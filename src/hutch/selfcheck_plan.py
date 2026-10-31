"""Sizing the context self-check from what this machine can do, and saying what it will cost before it runs.

The self-check proves a requested window really is in effect. It used to send a fixed ~12,000-token prompt; on a CPU-only machine
that is about ten minutes of prompt processing (measured at 16-19 tokens/s, docs/realignment/offline-models-2026-10-31.md section
3.2) with one log line and no estimate. Two changes, neither of which removes the check:

* The runtime reports the window it actually applied (`/api/ps` `context_length`). That is a *measurement* of exactly what the
  prompt probe was standing in for, and it is read *after* the probe: a runtime loads a model at its own default window when Hutch
  preloads it and only switches to the requested one on the first real request, so a report taken earlier describes the wrong load.
* The recall probe (does the model still find a fact at the top of a long prompt) is sized from measured prompt throughput so it fits
  a time budget, and the person is told the estimate first. When it is sized below the full window, the result says how far it was
  verified rather than implying the whole window was.

Throughput is measured from the check itself and kept per model; until one is measured, a CPU-only machine is assumed slow and
anything else is assumed fast, so only machines that need it are reduced.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from .context import SelfCheck, run_selfcheck

BUDGET_SECONDS = 120.0           # how long the recall probe may take before it is shortened
FLOOR_TOKENS = 1024              # never shortened below this; the window itself is proven by the runtime's own report
CPU_DEFAULT_TPS = 12.0           # prompt tokens/second assumed for a CPU-only machine until one is measured
FULL_CAP = 12_000


def _key(model: str) -> str:
    return f"prompt_tps:{model}"


@dataclass(frozen=True)
class Plan:
    size: int                    # tokens the recall probe will use
    full: int                    # tokens it would use with no time budget
    tokens_per_second: Optional[float]
    measured: bool               # throughput measured on this machine, not assumed
    seconds: Optional[float]     # estimated duration of the probe

    @property
    def reduced(self) -> bool:
        return self.size < self.full

    def announce(self, model: str, num_ctx: int) -> str:
        how = "measured" if self.measured else "assumed for this hardware"
        if self.seconds is None:
            return f"checking that {model} really recalls a fact placed at the top of a long prompt in a {num_ctx:,}-token window..."
        minutes = self.seconds / 60.0
        cost = f"about {minutes:.1f} minutes" if minutes >= 1.5 else f"about {max(1, round(self.seconds))} seconds"
        scope = (f"a {self.size:,}-token probe (shortened from {self.full:,} to fit; throughput {self.tokens_per_second:.0f} tokens/s {how})"
                 if self.reduced else f"a {self.size:,}-token probe ({self.tokens_per_second:.0f} tokens/s {how})")
        return (f"checking that {model} uses its {num_ctx:,}-token window and recalls a fact from the top of a long prompt: {scope}, "
                f"{cost}. This runs once per model and window.")


def measured_throughput(store: Any, model: str) -> Optional[float]:
    try:
        saved = json.loads(store.kv_get(_key(model)) or "null")
        value = float(saved["tps"])
    except (TypeError, ValueError, KeyError):
        return None
    return value if value > 0 else None


def plan_for(store: Any, model: str, num_ctx: int, accelerator: str = "") -> Plan:
    full = max(256, min(int(num_ctx * 0.8), FULL_CAP))
    tps = measured_throughput(store, model)
    measured = tps is not None
    if tps is None and accelerator == "cpu":
        tps = CPU_DEFAULT_TPS
    if tps is None:
        return Plan(size=full, full=full, tokens_per_second=None, measured=False, seconds=None)
    size = max(min(FLOOR_TOKENS, full), min(full, int(tps * BUDGET_SECONDS)))
    return Plan(size=size, full=full, tokens_per_second=tps, measured=measured, seconds=size / tps)


def announce(store: Any, model: str, num_ctx: int, accelerator: str = "") -> str:
    return plan_for(store, model, num_ctx, accelerator).announce(model, num_ctx)


def run_planned_selfcheck(provider: Any, store: Any, model: str, num_ctx: int, *, accelerator: str = "",
                          request_runner=None) -> SelfCheck:
    """The recall probe sized to this machine, then the runtime's own report of the window it applied. Same result type and meaning."""
    plan = plan_for(store, model, num_ctx, accelerator)
    started = time.perf_counter()
    result = run_selfcheck(provider, model, num_ctx, size_tokens=plan.size, request_runner=request_runner)
    elapsed = time.perf_counter() - started
    if result.prompt_tokens and elapsed > 1.0:                 # remember what this machine really does, even when the probe fails
        store.kv_set(_key(model), json.dumps({"tps": round(result.prompt_tokens / elapsed, 2), "at": time.time()}))
    if not result.ok:
        return result
    live = provider.residency(model) if hasattr(provider, "residency") else None      # taken after a request at this window
    applied = (live or {}).get("context_length")
    if isinstance(applied, (int, float)) and 0 < applied < num_ctx:
        return SelfCheck(False, f"the runtime applied a {int(applied):,}-token window, not the {num_ctx:,} requested "
                                "(reported by the runtime itself)", result.prompt_tokens, num_ctx, result.seconds, True)
    if plan.reduced:
        result.detail += f" (verified to {plan.size:,} tokens, shortened from {plan.full:,} to fit this machine's speed)"
    if isinstance(applied, (int, float)) and applied >= num_ctx:
        result.detail += f"; the runtime reports a {int(applied):,}-token window in effect"
    return result
