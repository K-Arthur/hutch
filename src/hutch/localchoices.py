"""First-class local choices for every reachable runtime (G3).

Ollama already had a group; llama.cpp, LM Studio, vLLM and SGLang were discoverable but had no
entry, fit note or state. This module builds the same ``Choice`` rows from each runtime's own
report. A model is offered as ready because the runtime reports it and the fit arithmetic agrees,
never because a port answered.
"""

from __future__ import annotations

from typing import Any, Optional

from .fit import estimate_fit
from .hardware import Hardware
from .providers.base import ModelMeta
from .providers.discovery import ENDPOINTS, probe_local_services
from .providers.registry import is_local


def _ollama_choices(hw: Hardware, provider: Any, want: int) -> list[Any]:
    from .modelchoices import Choice, _cached
    from .modelview import installed
    out: list[Any] = []
    for name, meta in sorted(_cached("installed", lambda: installed(provider)).items()):
        spec = f"ollama/{name}"
        if not is_local(spec):
            out.append(Choice(spec=spec, label=name, group="Hosted", state="setup", hosted=True,
                              note="Ollama Cloud model; inference runs on ollama.com",
                              fix="Sign in to Ollama, then use this only with Hybrid routing.",
                              detail=["Ollama classifies this tag as a cloud model",
                                      "Hutch has no price row for this route; cost caps refuse it until priced"]))
            continue
        fit = estimate_fit(meta, hw, want)
        ok = fit.status != "wont_fit"
        out.append(Choice(
            spec=spec, label=name, group="On this machine", state="ready" if ok else "wont_fit",
            note=(f"{'fits' if fit.status == 'fits' else 'tight fit'}, {fit.effective_ctx // 1024}k context"
                  if ok else "does not fit this machine"),
            fix="" if ok else fit.reason, detail=[fit.reason]))
    return out


def _runtime_rows(state_dir: Any = None) -> list[dict[str, Any]]:
    """Probe every non-Ollama local runtime; llama.cpp's stock port is not the hardware probe's.

    A dead loopback port refuses immediately, and a five-second cache keeps the picker from
    repeating the probe for every message. A key is supplied only for a matching connection origin.
    """
    from .modelchoices import _cached
    from .providers.local.credentials import runtime_credentials
    endpoints = [e for e in ENDPOINTS if e.provider_id != "ollama"]
    credential_for = runtime_credentials(state_dir) if state_dir else None
    rows = _cached("local-runtime-rows",
                   lambda: probe_local_services(timeout=0.4, endpoints=endpoints,
                                                credential_for=credential_for), ttl=5.0)
    return list(rows.values())


def _note(row: dict[str, Any], applied: Optional[int], fit: Any) -> str:
    slots = row.get("parallel")
    title = str(row.get("title") or row.get("provider") or "local runtime")
    if applied:
        text = f"{title}: loaded at {applied // 1024}k tokens"
        if row.get("runtime") == "llamacpp" and slots and slots > 1:
            text += f" per request across {slots} slots"
        elif slots and slots > 1:
            text += f" (parallel {slots})"
        return text + ", reported by the runtime"
    if fit.status == "wont_fit":
        return f"{title}: {fit.reason}"
    return f"{title}: the runtime does not report the window it serves"


def _endpoint(row: dict[str, Any]) -> str:
    url = str(row.get("url") or "")
    return url[: -len("/models")] if url.endswith("/models") else url


def _runtime_choices(hw: Hardware, row: dict[str, Any], want: int) -> list[Any]:
    from .modelchoices import Choice
    if row.get("state") == "needs_key" or not row.get("reachable"):
        return []
    out: list[Any] = []
    for raw in row.get("model_meta") or []:
        try:
            meta = ModelMeta(**raw)
        except TypeError:
            continue
        if "embedding" in meta.capabilities:
            continue
        applied = (row.get("applied_context") or {}).get(meta.name)
        fit = estimate_fit(meta, hw, applied or min(want, meta.max_context or want))
        measured = bool(applied)
        if not measured and fit.status == "wont_fit":
            state, fix = "wont_fit", fit.reason
        else:
            state, fix = "ready", ""
        detail = [f"endpoint {_endpoint(row)}"]
        if applied and row.get("parallel"):
            detail.append(f"{row['parallel']} slot(s); the headline context is not the per-request window")
        if meta.capabilities:
            detail.append("runtime lists: " + ", ".join(meta.capabilities))
        if row.get("policy_detail"):
            detail.append(str(row["policy_detail"]))
        out.append(Choice(spec=f"{row['provider']}/{meta.name}", label=meta.name, group="On this machine",
                          state=state, note=_note(row, applied, fit), fix=fix, detail=detail))
    return out


def local_choices(bot: Any, hw: Hardware, provider: Any, *, state_dir: Any = None) -> list[Any]:
    """Every local model Hutch can see, grouped by where inference happens."""
    want = bot.num_ctx or 16384
    out: list[Any] = []
    if any(r.name == "ollama" and r.reachable for r in hw.runtimes):
        out.extend(_ollama_choices(hw, provider, want))
    for row in _runtime_rows(state_dir):
        out.extend(_runtime_choices(hw, row, want))
    return out
