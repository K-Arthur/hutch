"""One read model for AI services, routes and assistant routing.

Models, the composer picker, Settings and first run each used to re-derive part of this: the saved workspace
default was parsed in three places, Models kept its own inventory in modelview.py, and "which assistant uses
what" was inferred from a raw model string comparison. This module is the single consolidation point:

* the workspace default (parsed once, with the same shape rules the run validator uses);
* every assistant's saved routes (primary, fallbacks, escalation) with its truthful usability state;
* a service summary grouped by what actually runs the model, with counts of broken routes;
* warnings that only need the saved configuration to state.

It reads state and returns data; it never writes, starts a model server or changes an assistant. Health probes
(the hardware page, OpenCode detection) stay on their existing paths and can be layered on top by the caller.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .models import RuntimeKind
from .route_problem import model_route_problem

DEFAULTS_KEY = "workspace:model-defaults"


def _defaults_record(store) -> dict[str, Any]:
    raw = store.kv_get(DEFAULTS_KEY)
    if raw is None:
        legacy = (store.kv_get("default_model") or "").strip()
        return {"model": legacy, "inference_mode": "hybrid", "configured": bool(legacy), "damaged": False,
                "route_problem": model_route_problem(legacy) if legacy else None}
    try:
        saved = json.loads(raw)
        model = str(saved.get("model") or "").strip()
        mode = str(saved.get("inference_mode") or "hybrid")
        if mode not in ("hybrid", "local", "offline"):
            mode = "hybrid"
    except (TypeError, ValueError, AttributeError):
        return {"model": "", "inference_mode": "hybrid", "configured": False, "damaged": True,
                "route_problem": None}
    return {"model": model, "inference_mode": mode, "configured": bool(model), "damaged": False,
            "route_problem": model_route_problem(model) if model else None}


def workspace_default(store) -> dict[str, Any]:
    """The one parser for the saved default used to seed new built-in assistants (API contract)."""
    record = _defaults_record(store)
    record.pop("damaged", None)
    return record


def assistant_routes(bot) -> list[dict[str, Any]]:
    routes = [{"spec": (bot.model or "").strip(), "role": "primary"}]
    routes += [{"spec": spec, "role": "fallback"} for spec in (bot.fallbacks or []) if spec]
    if bot.escalation is not None:
        routes += [{"spec": spec, "role": "escalation"} for spec in (bot.escalation.to or []) if spec]
    return routes


def assistant_summary(bot) -> dict[str, Any]:
    problem = model_route_problem(bot.model, bot.runtime)
    return {"name": bot.name, "display_name": bot.display_name or bot.name, "model": bot.model,
            "runtime": bot.runtime.value, "inference_mode": bot.inference_mode.value, "paused": bool(bot.paused),
            "usable": problem is None, "route_problem": problem,
            "routes": assistant_routes(bot),
            "fix_href": f"/#/bot/{bot.name}" if problem else ""}


def authority(store, config=None) -> dict[str, Any]:
    """The read answer every surface can share: services, assistant routing, defaults, warnings."""
    assistants = [assistant_summary(bot) for bot in store.list_bots()]
    services: dict[str, dict[str, Any]] = {}
    for entry in assistants:
        service = entry["routes"][0]["spec"].partition("/")[0].lower() or "unset"
        if entry["runtime"] == "opencode":
            service = "opencode"
        elif entry["runtime"] == "pi":
            service = "pi"
        bucket = services.setdefault(service, {"id": service, "assistants": 0, "working": 0, "needs_model": 0,
                                               "leaves_machine": service not in ("ollama", "llamacpp", "llama.cpp",
                                                                                 "lmstudio", "vllm", "unset")})
        bucket["assistants"] += 1
        bucket["working" if entry["usable"] else "needs_model"] += 1
    defaults = _defaults_record(store)
    warnings: list[str] = []
    if defaults["damaged"]:
        warnings.append("The saved workspace default could not be read; choose a route for new assistants again.")
    if defaults["route_problem"]:
        warnings.append(f"The saved workspace default cannot run: {defaults['route_problem']}.")
    broken = [entry for entry in assistants if not entry["usable"]]
    if broken:
        warnings.append(f"{len(broken)} assistant(s) have a saved route that cannot run.")
    return {"workspace_default": defaults, "assistants": assistants, "services": sorted(services.values(),
            key=lambda item: item["id"]), "warnings": warnings, "counts": {"assistants": len(assistants),
            "usable": sum(1 for entry in assistants if entry["usable"]), "needs_model": len(broken)},
            "one_destination": {"add_or_repair": "#/connections", "per_assistant": "each assistant's settings",
                                "defaults": "#/settings"}}
