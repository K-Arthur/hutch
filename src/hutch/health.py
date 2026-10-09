"""Per-runtime health (SR-1): a dead runtime or model must be *visible* and must affect only its own runs.

Isolation itself is structural (every run is its own thread with its own provider call and typed errors). What was
missing is the visibility: when Ollama is down or a plan's key is wrong, the user should see *that*, per runtime,
with the cause and the fix - not a pile of failed runs that all say "error".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import iso, utcnow

FAIL_DEGRADED_AT = 2      # consecutive failures before a runtime is called degraded
FAIL_DOWN_AT = 4


@dataclass
class ProviderHealth:
    name: str
    kind: str                         # local-runtime | connection | hosted
    state: str                        # healthy | degraded | down | needs_setup | idle
    detail: str = ""
    fix: str = ""
    version: str = ""
    loaded: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    consecutive_failures: int = 0
    last_error: str = ""
    last_error_at: str = ""


# ------------------------------------------------------------------ failure tracking (written by the runtime)

def record_outcome(store: Any, provider: str, ok: bool, error: str = "") -> None:
    key = f"provider_health:{provider}"
    if ok:
        raw = store.kv_get(key)
        if raw and json.loads(raw).get("fails"):
            store.kv_set(key, json.dumps({"fails": 0, "last_error": json.loads(raw).get("last_error", ""),
                                          "at": json.loads(raw).get("at", "")}))
        return
    prev = json.loads(store.kv_get(key) or "{}")
    store.kv_set(key, json.dumps({"fails": int(prev.get("fails", 0)) + 1, "last_error": error[:300], "at": iso(utcnow())}))


def failures(store: Any, provider: str) -> tuple[int, str, str]:
    d = json.loads(store.kv_get(f"provider_health:{provider}") or "{}")
    return int(d.get("fails", 0)), d.get("last_error", ""), d.get("at", "")


def _state_from(fails: int, base: str = "healthy") -> str:
    return "down" if fails >= FAIL_DOWN_AT else "degraded" if fails >= FAIL_DEGRADED_AT else base


# ------------------------------------------------------------------ the picture

def runtime_health(config: Any, store: Any, hw: Any = None, bot_models: Optional[list[str]] = None,
                   ollama: Any = None) -> list[ProviderHealth]:
    from .connections import ConnectionBook
    from .hardware import probe
    hw = hw or probe()
    used = {m.partition("/")[0] for m in (bot_models or [])}
    out: list[ProviderHealth] = []

    for rt in hw.runtimes:
        fails, last, at = failures(store, {"llama.cpp": "llamacpp"}.get(rt.name, rt.name))
        h = ProviderHealth(rt.name, "local-runtime", "idle", rt.detail, version=rt.version,
                           consecutive_failures=fails, last_error=last, last_error_at=at)
        if rt.reachable:
            h.state = _state_from(fails, "healthy")
            h.detail = f"running{(' ' + rt.version) if rt.version else ''} at {rt.url}"
            if rt.name == "ollama":
                p = ollama
                if p is None:
                    from .runtime.ladder import get_provider
                    p = get_provider("ollama", None)
                hh = p.health()
                h.latency_ms, h.loaded = hh.latency_ms, [m.get("name", "") for m in hh.loaded]
        elif rt.installed:
            h.state, h.fix = "down", {"ollama": "start it with `ollama serve`", "llama.cpp": "start `llama-server`",
                                      "lmstudio": "start the LM Studio server"}.get(rt.name, "start it")
        elif rt.name in used or rt.name.replace(".", "") in used:
            h.state = "needs_setup"
            h.fix = {"ollama": "install Ollama from ollama.com, then `ollama pull <model>`"}.get(
                rt.name, f"install and start {rt.name}")
        else:
            h.state, h.detail = "idle", "not installed (no bot uses it)"
        if fails:
            h.detail += f" - {fails} recent call failure(s), last: {last}"
        out.append(h)

    book = ConnectionBook(config.state_dir)
    for name, c in book.configured().items():
        fails, last, at = failures(store, name)
        ack = book.ack_status(store, name)
        has_key = book.has_key(name)
        h = ProviderHealth(name, "connection", _state_from(fails, "healthy"), c.title,
                           consecutive_failures=fails, last_error=last, last_error_at=at)
        if not has_key:
            h.state = "needs_setup"
            h.fix = ("sign in with ChatGPT and authorize plan use on Connections" if c.auth_type == "chatgpt-siws"
                     else f"set ${c.api_key_env} or run `hutch connections set-key {name}`")
            h.detail = "no plan-authorized ChatGPT account" if c.auth_type == "chatgpt-siws" else "no API key"
        elif ack in ("required", "stale"):
            h.state, h.fix, h.detail = "needs_setup", f"acknowledge its terms: `hutch connections ack {name}`", \
                "terms not acknowledged"
        elif fails:
            h.detail = f"{fails} recent failure(s), last: {last}"
        out.append(h)

    for name, env in (("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")):
        if name in used:
            fails, last, at = failures(store, name)
            has = bool(os.environ.get(env))
            out.append(ProviderHealth(name, "hosted", _state_from(fails, "healthy") if has else "needs_setup",
                                      "API key present" if has else "no API key",
                                      fix="" if has else f"set {env} in the environment that starts hutch",
                                      consecutive_failures=fails, last_error=last, last_error_at=at))
    return out
