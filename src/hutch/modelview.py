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
from .configured_routes import (ConfiguredModelRoute, _configured_routes, locality_for_route,
                                privacy_label_for)
from .providers.pricing import PriceBook, Price
from .route_problem import route_problem
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
    local_runtimes: list[dict[str, Any]] = field(default_factory=list)
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


def _local_service_rows(state_dir: Any = None) -> dict[str, dict[str, Any]]:
    from .providers.discovery import ENDPOINTS, probe_local_services
    from .providers.local.credentials import runtime_credentials
    credential_for = runtime_credentials(state_dir) if state_dir else None
    return probe_local_services(timeout=0.4,
                                endpoints=[e for e in ENDPOINTS if e.provider_id != "ollama"],
                                credential_for=credential_for)


def local_window_notes(state_dir: Any = None, *,
                       probed: Optional[dict[str, dict[str, Any]]] = None) -> list[str]:
    """Measured windows from non-Ollama runtimes that answer.

    The hardware probe checks llama.cpp's old 8080, so this uses the same candidate list as
    discovery and never infers a window from the hardware snapshot. A stored key is supplied only
    for its matching connection origin.
    """
    probed = probed if probed is not None else _local_service_rows(state_dir)
    notes: list[str] = []
    for row in probed.values():
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


def local_runtime_cards(state_dir: Any = None, *,
                        probed: Optional[dict[str, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """One card per detected non-Ollama local runtime, from the same discovery probes the notes use.

    Ollama has its own richer health card (version and loaded models from /api/ps). A runtime
    that is not reachable is not a card; the section's empty state says so. `state` is the
    runtime's own word (ready, loading, needs_key, unknown) and values it did not report stay
    None so the page can say unknown rather than guess.
    """
    probed = probed if probed is not None else _local_service_rows(state_dir)
    cards: list[dict[str, Any]] = []
    for provider_id, row in probed.items():
        if not row.get("reachable"):
            continue
        cards.append({
            "title": row.get("title") or provider_id,
            "state": row.get("state") or "unknown",
            "detail": row.get("detail") or "",
            "runtime": row.get("runtime") or "unknown",
            "confidence": row.get("confidence") or "unknown",
            "version": row.get("version") or "",
            "models": list(row.get("models") or []),
            "applied_context": dict(row.get("applied_context") or {}),
            "parallel": row.get("parallel"),
            "fix": row.get("fix") or "",
            "url": row.get("url") or "",
        })
    cards.sort(key=lambda card: card["title"].lower())
    return cards


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


def _installed_rows(store: Any, inst: dict[str, ModelMeta], hw: Hardware,
                    used_by: dict[str, list[str]]) -> list[ModelRow]:
    rows: list[ModelRow] = []
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
        profile = store.latest_profile(f"ollama/{name}")
        if profile is not None:
            rows[-1].profile = profile
            rows[-1].profile_stale = bool(
                (meta.template_hash and profile.template_hash and meta.template_hash != profile.template_hash)
                or (meta.digest and profile.digest and meta.digest != profile.digest))
    return rows


def _suggestions(inst: dict[str, ModelMeta], hw: Hardware) -> list[tuple[str, Fit, ModelMeta]]:
    out: list[tuple[str, Fit, ModelMeta]] = []
    for tag in _data("catalog.json")["models"]:
        if tag in inst:
            continue
        meta = catalog_meta(tag)
        if meta:
            out.append((tag, estimate_fit(meta, hw, REFERENCE_WINDOWS[0]), meta))
    out.sort(key=lambda t: (t[1].status == "wont_fit", t[2].params_b or 0))
    return out


def build_models_view(config: Any, store: Any, hw: Optional[Hardware] = None, provider: Any = None,
                      with_runtimes: bool = True) -> ModelsView:
    hw = hw or probe(with_runtimes=with_runtimes)
    if provider is None:
        from .runtime.ladder import get_provider
        provider = get_provider("ollama", None)
    ollama_up = any(r.name == "ollama" and r.reachable for r in hw.runtimes) if hw.runtimes else bool(provider.health().ok)
    inst = installed(provider) if ollama_up else {}
    tags_rows: list[dict[str, Any]] = []
    if ollama_up:
        try:
            from .providers.locality import fetch_ollama_rows
            tags_rows = fetch_ollama_rows(getattr(provider, "base_url", "http://127.0.0.1:11434")) or []
        except Exception:
            tags_rows = []
    bots = store.list_bots()
    used_by: dict[str, list[str]] = {}
    by_provider: dict[str, list[str]] = {}
    for b in bots:
        used_by.setdefault(b.model, []).append(b.name)
        by_provider.setdefault(b.model.partition("/")[0], []).append(b.name)
    rows = _installed_rows(store, inst, hw, used_by)
    presets = [resolve_preset(p, hw, inst) for p in load_presets(config.state_dir / "presets.json").values()]
    sugg = _suggestions(inst, hw)
    book = PriceBook(config.state_dir / "prices.json")
    local_rows = _local_service_rows(config.state_dir) if with_runtimes else None
    notes = list(hw.notes) + (local_window_notes(probed=local_rows) if local_rows is not None else [])
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
    configured_routes = _configured_routes(store, conn_book, inst, tags_rows, used_by, saved_default,
                                           ollama_up, usable_bots)
    default_spec = saved_default

    return ModelsView(hw=hw, runtimes=runtime_health(config, store, hw, [b.model for b in bots], provider if ollama_up else None,
                                                      used_by=by_provider)
                      if with_runtimes else [], ollama_up=ollama_up, rows=rows, presets=presets,
                      suggestions=sugg, prices=book.rows(), price_errors=book.errors, swaps=recorded_swaps(store),
                      notes=notes, local_runtimes=local_runtime_cards(probed=local_rows)
                      if local_rows is not None else [],
                      configured_routes=configured_routes, available_bots=available_bots,
                      default_model=default_spec)
