"""Local models are scheduled resources (LM-6).

A machine keeps one or two models resident. Every swap costs seconds to minutes of reload (measured, not guessed:
``measure_swap``), and a naive queue that alternates between bots on different models spends its life swapping.
So the dispatcher treats a model as a slot:

* a run for a model that is already in use or resident shares it and may start at once;
* a run for a different model starts only if a slot is free, otherwise it waits and says why (UI-6);
* among waiting runs, those whose model is already loaded go first (batching), so runs that share a model run
  together; a run that has waited longer than ``FAIRNESS_SECONDS`` jumps the queue so nothing starves;
* hosted and mock runs are not constrained.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from .models import Bot, Run, RunStatus, utcnow
from .providers.base import Provider, ProviderError

FAIRNESS_SECONDS = 15 * 60
LOADED_CACHE_SECONDS = 3.0


def default_capacity(tier: str) -> int:
    """Models resident at once: one unless the machine has the memory for two."""
    return 2 if tier in ("large", "xl") else 1


class ModelSlots:
    def __init__(self, store, capacity: Optional[int] = None, tier: str = "small",
                 loaded: Optional[Callable[[], set[str]]] = None):
        self.store = store
        self.capacity = capacity or int(os.environ.get("HUTCH_MODEL_SLOTS", "0") or 0) or default_capacity(tier)
        self._loaded_fn = loaded
        self._loaded_cache: tuple[float, set[str]] = (0.0, set())
        self.last_blocked: dict[str, str] = {}      # run id -> why it is waiting

    # ---------------------------------------------------------------- models

    def model_of(self, run: Run) -> Optional[str]:
        """The local model a run will use, or None for hosted / mock runs."""
        bot = self.store.get_bot(run.bot_id)
        if bot is None:
            return None
        provider, _, model = bot.model.partition("/")
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
        """Dispatch order for ``pending``: batch by loaded model, gate by free slots, keep fairness."""
        busy = {m for r in active if r.status is not RunStatus.pending and (m := self.model_of(r))}
        wants_local = any(self.model_of(r) for r in pending)
        resident = (self.loaded() if wants_local else set()) | busy      # no HTTP at all for hosted/mock queues
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

        ordered = sorted(pending, key=rank)
        taken = set(busy)
        out: list[Run] = []
        self.last_blocked = {}
        for r in ordered:
            m = self.model_of(r)
            if m is None or m in taken:
                out.append(r)
                continue
            if len(taken) < self.capacity:
                taken.add(m)
                out.append(r)
                continue
            self.last_blocked[r.id] = (
                f"waiting for a model slot: {', '.join(sorted(taken)) or 'another model'} "
                f"{'is' if len(taken) == 1 else 'are'} in use, and this machine keeps {self.capacity} local "
                f"model{'' if self.capacity == 1 else 's'} loaded at a time. Switching would unload "
                f"{'it' if len(taken) == 1 else 'one'} mid-run, so this run starts when the model it needs is free")
        return out

    def reason(self, run: Run):
        """UI-6: why a pending run is waiting for a model."""
        from .views import Wait
        why = self.last_blocked.get(run.id)
        if not why:
            return None
        return Wait(cause=why[0].upper() + why[1:] + ".",
                    fix=f"Wait for the running job, stop it, or raise HUTCH_MODEL_SLOTS if you have memory for more "
                        f"(now {self.capacity}).", href="/models", link_text="Models")


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
