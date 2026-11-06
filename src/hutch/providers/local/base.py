"""The narrow contract every local runtime adapter implements.

A local runtime answers six questions, each from its own signal: who are you, what models do
you list, which are loaded, what window is actually applied, what can this model do, and what
state are you in. The distinctions matter: a listed model is not a loaded model, a trained
maximum is not the window in effect, and a key-protected server is alive rather than absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..base import ModelMeta

READY = "ready"
LOADING = "loading"
NEEDS_KEY = "needs_key"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Identity:
    runtime: str                 # llamacpp | lmstudio | vllm | sglang | unknown
    evidence: str                # the exact observation that supports the name
    version: str = ""
    confidence: str = "strong"   # strong | weak | unknown


@dataclass
class Slot:
    n_ctx: Optional[int] = None
    processing: bool = False


@dataclass
class Loaded:
    model: str
    applied_context: Optional[int] = None   # per-request window in effect, as the runtime reports it
    parallel: Optional[int] = None
    slots: list[Slot] = field(default_factory=list)
    resident_bytes: Optional[int] = None
    vram_bytes: Optional[int] = None


@dataclass
class RuntimeState:
    provider_id: str
    reachable: bool = False
    state: str = UNREACHABLE
    detail: str = ""
    version: str = ""
    sleeping: bool = False           # unloaded but reloadable (llama.cpp /props.is_sleeping)
    models: list[ModelMeta] = field(default_factory=list)
    loaded: dict[str, Loaded] = field(default_factory=dict)
    policy: str = "unknown"          # refuse | shift | unknown
    policy_detail: str = ""
    identity: Optional[Identity] = None

    @property
    def needs_key(self) -> bool:
        return self.state == NEEDS_KEY


class LocalRuntime(Protocol):
    provider_id: str
    base_url: str
    identity: Identity

    def identify(self) -> Identity: ...

    def models(self) -> list[ModelMeta]: ...

    def loaded(self) -> dict[str, Loaded]: ...

    def capabilities(self, model: str) -> list[str]: ...

    def state(self) -> RuntimeState: ...
