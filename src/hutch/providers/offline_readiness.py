"""Can this route run with the network gone? Answer early and in words (Phase 1.3, EC-03).

Strict Offline already proves the endpoint is loopback and the model is not cloud-served (``locality``). This adds
the next question: is the model fully on this disk right now, so that starting the run cannot trigger a download
or a sign-in? The check reads what the runtime itself reports. Where the runtime exposes nothing (llama.cpp launch
flags such as ``-hf`` are not visible over HTTP), the gap is returned as a note, never as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .locality import LOCAL_PROVIDERS, entry_is_remote, fetch_ollama_rows, find_row

_TIMEOUT = 2.0


@dataclass(frozen=True)
class Readiness:
    ready: Optional[bool]       # True, False, or None when the runtime shows nothing either way
    reason: str


def _ollama(base_url: str, model: str) -> Readiness:
    rows = fetch_ollama_rows(base_url, _TIMEOUT)
    if rows is None:
        return Readiness(None, "the Ollama server did not answer, so the model could not be checked")
    row = find_row(rows, model)
    if row is None:
        return Readiness(False, f"{model} is not downloaded on this computer; pull it while online first "
                                "(a missing model makes Ollama contact its registry)")
    if entry_is_remote(row):
        return Readiness(False, f"{model} is served by a remote host and needs a sign-in and network")
    if "size" in row and not int(row["size"] or 0):
        return Readiness(False, f"{model} has no weights on disk")
    return Readiness(True, f"{model} is on disk")


def _llamacpp(base_url: str, model: str) -> Readiness:
    try:
        import httpx
        health = httpx.get(base_url.rstrip("/").removesuffix("/v1") + "/health", timeout=_TIMEOUT)
    except Exception:
        return Readiness(None, "the llama.cpp server did not answer, so the model could not be checked")
    if health.status_code == 503:
        return Readiness(False, "llama-server is still loading its model; wait for it to finish")
    note = "llama-server does not report its launch flags; start it with --offline so it cannot download"
    return Readiness(None, note) if health.status_code == 200 else Readiness(None, f"llama-server /health {health.status_code}")


_CHECKS: dict[str, Callable[[str, str], Readiness]] = {
    "ollama": _ollama, "llamacpp": _llamacpp, "llama.cpp": _llamacpp,
}


def route_readiness(provider: str, model: str, base_url: Optional[str]) -> Readiness:
    """Readiness for one local route; unknown providers return None (no claim) rather than a guess."""
    check = _CHECKS.get(provider)
    if provider not in LOCAL_PROVIDERS or check is None:
        return Readiness(None, f"{provider}: no readiness signal is available")
    return check(base_url or _default_url(provider), model)


def _default_url(provider: str) -> str:
    return "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:9931"
