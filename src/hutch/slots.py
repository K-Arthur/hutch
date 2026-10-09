"""Prefer resident models when ordering runs, without retaining inference across human waits.

Actual one-call/eight-waiter admission is process-safe in admission.py. This
dispatcher preference is only an optimization; it grants no inference authority.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from .models import Bot, Run, RunStatus, utcnow
from .providers.base import Provider, ProviderError

FAIRNESS_SECONDS = 15 * 60
LOADED_CACHE_SECONDS = 3.0


def default_capacity(tier: str) -> int:
    """Compatibility metadata; actual local inference has one slot on every tier."""
    return 1


class ModelSlots:
    def __init__(self, store, capacity: Optional[int] = None, tier: str = "small",
                 loaded: Optional[Callable[[], set[str]]] = None):
        self.store = store
        self.capacity = default_capacity(tier)
        self._loaded_fn = loaded
        self._loaded_cache: tuple[float, set[str]] = (0.0, set())
        self.last_blocked: dict[str, str] = {}      # run id -> why it is waiting

    # ---------------------------------------------------------------- models

    def model_of(self, run: Run) -> Optional[str]:
        """The local model a run will use, or None for hosted and unavailable legacy routes."""
        if run.parent_run_id is not None:
            snapshot = self.store.run_capability_snapshot(run.id)
            if snapshot is None:
                return None
            spec = str(snapshot.get("model", ""))
            provider, _, model = spec.partition("/")
            if provider in ("ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm"):
                return f"{provider}/{model}"
            return None
        bot = self.store.get_bot(run.bot_id)
        if bot is None:
            return None
        provider, _, model = (run.model_override or bot.model).partition("/")
        if provider in ("ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm"):
            return f"{provider}/{model}"
        return None

    def loaded(self) -> set[str]:
        now = time.monotonic()
        if now - self._loaded_cache[0] < LOADED_CACHE_SECONDS:
            return self._loaded_cache[1]
        names: set[str] = set()
        if self._loaded_fn is not None:
            try:
                names = set(self._loaded_fn())
            except Exception:
                names = set()
        self._loaded_cache = (now, names)
        return names

    # ----------------------------------------------------------------- order

    def filter(self, pending: list[Run], active: list[Run]) -> list[Run]:
        """Prefer resident models, retain starvation priority, never gate an entire run."""
        busy = {m for r in active if r.status in (RunStatus.running, RunStatus.loading_model) and (m := self.model_of(r))}
        wants_local = any(self.model_of(r) for r in pending)
        resident = (self.loaded() if wants_local else set()) | busy      # no HTTP at all for hosted queues
        now = utcnow()

        def waited(r: Run) -> float:
            try:
                return (now - datetime.fromisoformat(r.created_at)).total_seconds()
            except ValueError:
                return 0.0

        def rank(r: Run):
            m = self.model_of(r)
            starving = waited(r) > FAIRNESS_SECONDS
            sharing = m is None or m in resident
            return (0 if starving else 1, 0 if sharing else 1, r.created_at)

        self.last_blocked = {}
        return sorted(pending, key=rank)

    def reason(self, run: Run):
        """UI-6: why a pending run is waiting for a model."""
        return None  # active queue state/reason is persisted by the runtime


# ------------------------------------------------------------- swap measurement

@dataclass
class SwapReport:
    a: str
    b: str
    cold_a_ms: float          # loading A from nothing
    swap_a_to_b_ms: float     # loading B while A is resident
    swap_b_to_a_ms: float     # loading A back
    evicted: bool             # was A actually unloaded when B loaded? (False: the runtime kept both)

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @property
    def summary(self) -> str:
        if not self.evicted:
            return (f"{self.a} and {self.b} stayed resident together: no swap cost "
                    f"(loads took {self.swap_a_to_b_ms / 1000:.1f}s and {self.swap_b_to_a_ms / 1000:.1f}s)")
        return (f"{self.a} -> {self.b}: {self.swap_a_to_b_ms / 1000:.1f}s;  "
                f"{self.b} -> {self.a}: {self.swap_b_to_a_ms / 1000:.1f}s  (cold load of {self.a}: "
                f"{self.cold_a_ms / 1000:.1f}s)")


def measure_swap(provider: Any, a: str, b: str) -> SwapReport:
    """Time loading A cold, then B on top of A, then A back - the real cost of alternating between two models.

    Uses the runtime's own preload (an empty-prompt request), so no tokens are generated. It really unloads and
    reloads your models: run it when the machine is idle.
    """
    for m in (a, b):
        provider.unload(m)
    cold_a = provider.preload(a)
    ab = provider.preload(b)
    evicted = not provider.is_loaded(a)
    ba = provider.preload(a)
    return SwapReport(a, b, cold_a, ab, ba, evicted)


def record_swap(store, report: SwapReport) -> None:
    store.kv_set(f"swap:{report.a}->{report.b}", report.to_json())


def recorded_swaps(store) -> list[dict[str, Any]]:
    out = []
    with store._lock:
        rows = store._db.execute("SELECT key, value FROM kv WHERE key LIKE 'swap:%'").fetchall()
    for r in rows:
        try:
            out.append(json.loads(r["value"]))
        except ValueError:
            continue
    return out
