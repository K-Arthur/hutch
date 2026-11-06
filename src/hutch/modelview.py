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
from .hardware import GIB, Hardware, probe
from .health import ProviderHealth, runtime_health
from .presets import Resolution, catalog_meta, load_presets, resolve_preset, _data
from .providers.base import ModelMeta
from .providers.pricing import PriceBook, Price, LOCAL_PROVIDERS
from .route_problem import model_route_problem, route_problem
from .slots import recorded_swaps

REFERENCE_WINDOWS = (16384, 32768)


@dataclass
class ConfiguredModelRoute:
    spec: str
    provider: str
    model_id: str
    label: str
    status: str
    is_default: bool
    bots: list[str]
    has_key: bool
    is_local: bool
    problem: Optional[str] = None


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
    configured_routes: list[ConfiguredModelRoute] = field(default_factory=list)
    available_bots: list[tuple[str, str]] = field(default_factory=list)
    default_model: str = ""


def _selfcheck_status(store: Any, model: str) -> str:
    with store._lock:
        rows = store._db.execute("SELECT value FROM kv WHERE key LIKE ?", (f"selfcheck:%:{model}:%",)).fetchall()
    if not rows:
        return "not run"
    return "passed" if any(json.loads(r["value"]).get("ok") for r in rows) else "failed"


def residency_note(meta: ModelMeta) -> str:
    """One line of *measured* facts about a loaded model, or "" when it is not loaded.

    Deliberately separate from the fit estimate: fit is arithmetic about what should happen,
    this is what the runtime says is happening. `size_vram` is the only evidence that a model
    is on the GPU; reporting "GPU accelerated" without it would be a guess.
    """
    if meta.applied_context is None and meta.resident_bytes is None:
        return ""
    parts: list[str] = []
    if meta.applied_context:
        parts.append(f"loaded at {meta.applied_context:,} tokens")
    if meta.resident_bytes:
        parts.append(f"{meta.resident_bytes / GIB:.1f} GiB resident")
    if meta.vram_bytes is not None:
        parts.append("on the GPU" if meta.vram_bytes > 0 else "entirely on the CPU")
    return ", ".join(parts)


def local_window_notes(hw: Hardware) -> list[str]:
    """Measured windows from non-Ollama runtimes that are actually running.

    Only called when the hardware probe already found one reachable, so a models page with no
    llama.cpp/LM Studio server does not pay for a second round of connection attempts.
    """
    if not any(r.reachable and r.name != "ollama" for r in hw.runtimes):
        return []
    from .providers.discovery import ENDPOINTS, probe_local_services
    notes: list[str] = []
    for row in probe_local_services(timeout=0.4, endpoints=[e for e in ENDPOINTS if e.provider_id != "ollama"]).values():
        if not row.get("reachable"):
            continue
        windows = row.get("applied_context") or {}
        slots = row.get("parallel")
        for model, ctx in sorted(windows.items()):
            if row.get("runtime") == "llamacpp" and slots and slots > 1:
                slot_note = f" per request across {slots} slots"
            elif slots and slots > 1:
                slot_note = f" (parallel {slots})"
            else:
                slot_note = ""
            notes.append(f"{row['title']} reports {model} loaded at {ctx:,} tokens{slot_note}")
        if not windows and row.get("state") == "needs_key":
            notes.append(f"{row['title']} is running but needs an API key before Hutch can read its models")
        elif not windows and row.get("models"):
            notes.append(f"{row['title']} reports no applied window; Hutch will not assume one")
    return notes


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
    by_provider: dict[str, list[str]] = {}
    for b in bots:
        used_by.setdefault(b.model, []).append(b.name)
        by_provider.setdefault(b.model.partition("/")[0], []).append(b.name)
    rows = []
    for name, meta in sorted(inst.items()):
        raw = store.kv_get(f"model_load:{name}")
        assigned = list(used_by.get(f"ollama/{name}", []))
        for b_name in used_by.get(name, []):
            if b_name not in assigned:
                assigned.append(b_name)
        rows.append(ModelRow(
            name=name, meta=meta,
            fits={w: estimate_fit(meta, hw, w) for w in REFERENCE_WINDOWS},
            bots=assigned, load_ms=json.loads(raw)["ms"] if raw else None,
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
    notes = list(hw.notes) + local_window_notes(hw)
    if not ollama_up:
        notes.append("Ollama is not running, so installed models cannot be listed. Start it with `ollama serve`; "
                     "suggestions below are estimates from the catalog.")
    from .connections import ConnectionBook
    conn_book = ConnectionBook(config.state_dir)
    raw_default = store.kv_get("workspace:model-defaults")
    saved_default = ""
    if raw_default:
        try:
            saved_default = str((json.loads(raw_default) or {}).get("model") or "")
        except (ValueError, TypeError):
            saved_default = ""
    saved_default = saved_default or store.kv_get("default_model") or ""

    available_bots = [(b.name, b.display_name or b.name) for b in bots]
    usable_bots = {b.name: route_problem(b) is None for b in bots}
    configured_routes = []
    seen_specs = set()

    for name, meta in sorted(inst.items()):
        spec = f"ollama/{name}"
        seen_specs.add(spec)
        seen_specs.add(name)
        assigned = list(used_by.get(spec, []))
        for b_name in used_by.get(name, []):
            if b_name not in assigned:
                assigned.append(b_name)
        is_def = spec == saved_default
        configured_routes.append(ConfiguredModelRoute(
            spec=spec, provider="ollama", model_id=name, label=store.kv_get(f"model_label:{spec}") or name,
            status="ready", is_default=is_def, bots=assigned, has_key=True, is_local=True
        ))

    for c_name, conn in conn_book.configured().items():
        has_k = bool(conn_book.key(c_name))
        for bot_spec, b_names in used_by.items():
            if bot_spec.startswith(f"{c_name}/"):
                seen_specs.add(bot_spec)
                m_id = bot_spec.split("/", 1)[1]
                is_def = bot_spec == saved_default
                configured_routes.append(ConfiguredModelRoute(
                    spec=bot_spec, provider=c_name, model_id=m_id, label=store.kv_get(f"model_label:{bot_spec}") or f"{conn.title}: {m_id}",
                    status="ready" if has_k else "needs_key", is_default=is_def,
                    bots=b_names, has_key=has_k, is_local=False
                ))

    extra_specs = set(used_by.keys())
    if saved_default:
        extra_specs.add(saved_default)
    kv_routes = [s.strip() for s in (store.kv_get("configured_model_routes") or "").split(",") if s.strip()]
    extra_specs.update(kv_routes)

    for bot_spec in sorted(extra_specs):
        if bot_spec and bot_spec not in seen_specs:
            b_names = used_by.get(bot_spec, [])
            prov, mid = bot_spec.split("/", 1) if "/" in bot_spec else ("custom", bot_spec)
            is_def = bot_spec == saved_default
            has_k = True
            if prov in conn_book.names():
                has_k = bool(conn_book.key(prov))
            problem = model_route_problem(bot_spec)
            usable = any(usable_bots.get(name, False) for name in b_names)
            status = "unusable" if problem and not usable else ("ready" if has_k else "needs_key")
            configured_routes.append(ConfiguredModelRoute(
                spec=bot_spec, provider=prov, model_id=mid, label=store.kv_get(f"model_label:{bot_spec}") or bot_spec,
                status=status, is_default=is_def, bots=b_names, has_key=has_k, is_local=prov in LOCAL_PROVIDERS,
                problem=problem,
            ))

    default_spec = saved_default

    return ModelsView(hw=hw, runtimes=runtime_health(config, store, hw, [b.model for b in bots], provider if ollama_up else None,
                                                      used_by=by_provider)
                      if with_runtimes else [], ollama_up=ollama_up, rows=rows, presets=presets,
                      suggestions=sugg, prices=book.rows(), price_errors=book.errors, swaps=recorded_swaps(store),
                      notes=notes, configured_routes=configured_routes, available_bots=available_bots,
                      default_model=default_spec)
