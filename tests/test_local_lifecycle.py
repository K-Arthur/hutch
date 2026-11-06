"""Lifecycle states for local runtimes: loading is a measured wait, sleeping is reloadable."""

from __future__ import annotations

import json

from hutch.hardware import Hardware
from hutch.providers.local import HttpResult
from hutch.providers.local import admission as admission_module
from hutch.providers.local.admission import admit_local
from hutch.providers.local.base import LOADING, READY, RuntimeState
from hutch.providers.local.llamacpp import LlamaCppRuntime
from hutch.providers.local.lifecycle import observe_load

HARDWARE = Hardware(ram_total_gb=64, ram_available_gb=48)


class Sequenced:
    def __init__(self, *states):
        self.states = list(states)
        self.calls = 0

    def state(self):
        self.calls += 1
        return self.states[min(self.calls - 1, len(self.states) - 1)]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _ready(model="m", ctx=4096, sleeping=False):
    state = RuntimeState("llamacpp", reachable=True, state=READY, sleeping=sleeping)
    from hutch.providers.base import ModelMeta
    from hutch.providers.local.base import Loaded
    state.models = [ModelMeta(name=model, backend="llama.cpp", max_context=8192)]
    state.loaded = {model: Loaded(model=model, applied_context=ctx, parallel=2)}
    return state


def test_loading_is_waited_and_measured():
    clock = Clock()
    phases: list[bool] = []
    adapter = Sequenced(RuntimeState("x", reachable=True, state=LOADING),
                        RuntimeState("x", reachable=True, state=LOADING), _ready())
    observed = observe_load(adapter, "m", poll=0.25, on_loading=phases.append,
                            sleep=clock.sleep, clock=clock)
    assert observed.blocked is False
    assert observed.state_after == READY
    assert observed.waited_ms == 500
    assert observed.detail == "m became ready in 500ms"
    assert phases == [True, False]


def test_a_loading_timeout_is_a_state_with_the_reason():
    clock = Clock()
    phases: list[bool] = []
    adapter = Sequenced(RuntimeState("x", reachable=True, state=LOADING))
    observed = observe_load(adapter, "m", timeout=0.5, poll=0.25, on_loading=phases.append,
                            sleep=clock.sleep, clock=clock)
    assert observed.blocked is True
    assert observed.error_kind == "timeout"
    assert "still loading m after 0.5s" in observed.detail
    assert phases == [True, False]


def test_a_non_loopback_endpoint_is_refused_as_a_state():
    observed = observe_load(LlamaCppRuntime("http://192.168.1.20"), "m")
    assert observed.blocked is True
    assert observed.error_kind == "bad_request"
    assert "loopback" in observed.detail


def test_sleeping_is_not_a_wait_and_not_an_error():
    phases: list[bool] = []
    observed = observe_load(Sequenced(_ready(sleeping=True)), "m", on_loading=phases.append)
    assert observed.blocked is False
    assert observed.sleeping is True
    assert "next request reloads it" in observed.detail
    assert phases == []


class _Http:
    def __init__(self, routes):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url, timeout, bearer=""):
        self.calls.append(url)
        answer = self.routes[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _json(payload, status=200):
    return HttpResult(status, json.dumps(payload).encode())


PROPS = {"build_info": "b12144-69ee2ecc0", "model_path": "models/m.gguf",
         "default_generation_settings": {"n_ctx": 4096}, "is_sleeping": True}
MODELS = {"data": [{"id": "m", "owned_by": "llamacpp"}]}


def test_llamacpp_reports_sleeping_from_props():
    http = _Http({"http://h/health": _json({}), "http://h/props": _json(PROPS),
                  "http://h/v1/models": _json(MODELS), "http://h/slots": _json([{"id": 0, "n_ctx": 4096}])})
    state = LlamaCppRuntime("http://h", http=http).state()
    assert state.sleeping is True
    assert state.detail.startswith("the model is asleep")


def test_llamacpp_does_not_cache_a_loading_state():
    http = _Http({"http://h/health": _json({}, 503), "http://h/props": _json({"is_sleeping": False}),
                  "http://h/v1/models": _json(MODELS), "http://h/slots": _json([])})
    runtime = LlamaCppRuntime("http://h", http=http)
    assert runtime.state().state == LOADING
    runtime.state()
    assert http.calls.count("http://h/health") == 2


class _LoadingAdapter:
    def __init__(self):
        self.calls = 0

    def state(self):
        self.calls += 1
        return RuntimeState("llamacpp", reachable=True, state=LOADING) if self.calls == 1 else _ready()

    def load(self, model, context_length):
        return context_length


def test_admission_waits_for_a_loading_runtime_and_reports_the_measured_load(monkeypatch):
    adapter = _LoadingAdapter()
    monkeypatch.setattr(admission_module, "adapter_for", lambda *a, **k: adapter)
    monkeypatch.setattr(admission_module, "observe_load",
                        lambda target, model, **kw: observe_load(target, model, poll=0.001, **kw))
    phases: list[bool] = []
    admission = admit_local("llamacpp", provider=None, base_url="http://h", model="m",
                            want=8192, min_ctx=4096, hardware=HARDWARE, on_loading=phases.append)
    assert admission.blocked is False
    assert admission.load_ms > 0
    assert admission.num_ctx == 4096
    assert phases == [True, False]


class _Cold:
    def __init__(self):
        self.loads: list[tuple[str, int]] = []

    def state(self):
        state = _ready()
        state.loaded = {}
        for row in state.models:
            row.applied_context = None
        return state

    def load(self, model, context_length):
        self.loads.append((model, context_length))
        return context_length


def test_admission_times_a_cold_lmstudio_load_and_marks_loading(monkeypatch):
    adapter = _Cold()
    monkeypatch.setattr(admission_module, "adapter_for", lambda *a, **k: adapter)
    phases: list[bool] = []
    admission = admit_local("lmstudio", provider=None, base_url="http://h", model="m",
                            want=8192, min_ctx=4096, hardware=HARDWARE, on_loading=phases.append)
    assert admission.blocked is False
    assert admission.num_ctx == 8192
    assert adapter.loads == [("m", 8192)]
    assert admission.load_ms >= 0
    assert "loaded m at 8,192 tokens" in admission.note
    assert phases == [True, False]


def test_a_sleeping_model_is_reported_as_reloadable(monkeypatch):
    adapter = _Cold()
    monkeypatch.setattr(admission_module, "adapter_for", lambda *a, **k: adapter)

    def sleeping_state():
        state = _ready(sleeping=True)
        state.loaded = {}
        return state

    adapter.state = sleeping_state
    admission = admit_local("llamacpp", provider=None, base_url="http://h", model="m",
                            want=8192, min_ctx=4096, hardware=HARDWARE)
    assert admission.blocked is False
    assert admission.sleeping is True
    assert "asleep" in admission.note
