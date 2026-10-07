"""Everything the Models page and `hutch models` show (LM-5, LM-7, LM-14).

Each installed model is marked **fits / tight / won't fit** with the context it will *actually* get at two reference
windows; each task preset says which model it resolved to on this machine and what to install; hosted prices show the
date they were verified. Pure data in, plain objects out, so the page and the CLI cannot disagree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .fit import Fit, estimate_fit
from .hardware import Hardware, probe
from .health import ProviderHealth, runtime_health
from .presets import Resolution, catalog_meta, load_presets, resolve_preset, _data
from .providers.base import ModelMeta
from .providers.pricing import PriceBook, Price
from .slots import recorded_swaps

REFERENCE_WINDOWS = (16384, 32768)


@dataclass
class ModelRow:
    name: str
    meta: ModelMeta
    fits: dict[int, Fit]
    bots: list[str]
    load_ms: Optional[float]
    selfcheck: str                      # "passed" | "failed" | "not run"
    profile: Optional[Any] = None       # reliability Profile (LM-11), when measured
    profile_stale: bool = False         # the model file / template changed since it was measured


@dataclass
class ModelsView:
    hw: Hardware
    runtimes: list[ProviderHealth]
    ollama_up: bool
    rows: list[ModelRow]
    presets: list[Resolution]
    suggestions: list[tuple[str, Fit, ModelMeta]]
    prices: list[Price]
    price_errors: list[str]
    swaps: list[dict]
    notes: list[str] = field(default_factory=list)


def _selfcheck_status(store: Any, model: str) -> str:
    with store._lock:
        rows = store._db.execute("SELECT value FROM kv WHERE key LIKE ?", (f"selfcheck:%:{model}:%",)).fetchall()
    if not rows:
        return "not run"
    return "passed" if any(json.loads(r["value"]).get("ok") for r in rows) else "failed"


def installed(provider: Any) -> dict[str, ModelMeta]:
    """Installed Ollama models with the runtime's own architecture numbers (not estimates)."""
    out: dict[str, ModelMeta] = {}
    try:
        names = [m.name for m in provider.list_models()]
    except Exception:
        return out
    for n in names:
        meta = provider.show(n)
        if meta is not None:
            out[n] = meta
    return out


def build_models_view(config: Any, store: Any, hw: Optional[Hardware] = None, provider: Any = None,
                      with_runtimes: bool = True) -> ModelsView:
    hw = hw or probe(with_runtimes=with_runtimes)
    if provider is None:
        from .runtime.ladder import get_provider
        provider = get_provider("ollama", None)
    ollama_up = any(r.name == "ollama" and r.reachable for r in hw.runtimes) if hw.runtimes else bool(provider.health().ok)
    inst = installed(provider) if ollama_up else {}
    bots = store.list_bots()
    used_by: dict[str, list[str]] = {}
    for b in bots:
        used_by.setdefault(b.model, []).append(b.name)
    rows = []
    for name, meta in sorted(inst.items()):
        raw = store.kv_get(f"model_load:{name}")
        rows.append(ModelRow(
            name=name, meta=meta,
            fits={w: estimate_fit(meta, hw, w) for w in REFERENCE_WINDOWS},
            bots=used_by.get(f"ollama/{name}", []), load_ms=json.loads(raw)["ms"] if raw else None,
            selfcheck=_selfcheck_status(store, name)))
        prof = store.latest_profile(f"ollama/{name}")
        if prof is not None:
            rows[-1].profile = prof
            rows[-1].profile_stale = bool((meta.template_hash and prof.template_hash and meta.template_hash != prof.template_hash)
                                          or (meta.digest and prof.digest and meta.digest != prof.digest))
    presets = [resolve_preset(p, hw, inst) for p in load_presets(config.state_dir / "presets.json").values()]
    sugg = []
    for tag in _data("catalog.json")["models"]:
        if tag in inst:
            continue
        meta = catalog_meta(tag)
        if meta:
            sugg.append((tag, estimate_fit(meta, hw, REFERENCE_WINDOWS[0]), meta))
    sugg.sort(key=lambda t: (t[1].status == "wont_fit", t[2].params_b or 0))
    book = PriceBook(config.state_dir / "prices.json")
    notes = list(hw.notes)
    if not ollama_up:
        notes.append("Ollama is not running, so installed models cannot be listed. Start it with `ollama serve`; "
                     "suggestions below are estimates from the catalog.")
    return ModelsView(hw=hw, runtimes=runtime_health(config, store, hw, [b.model for b in bots], provider if ollama_up else None)
                      if with_runtimes else [], ollama_up=ollama_up, rows=rows, presets=presets,
                      suggestions=sugg, prices=book.rows(), price_errors=book.errors, swaps=recorded_swaps(store),
                      notes=notes)
