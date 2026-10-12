"""Stop races, text egress and official image wire format; no external request or model call."""
from types import SimpleNamespace

import httpx
import pytest

from hutch.computer.control import ControlLease, ControlOwner, StaleControl
from hutch.computer.frames import FrameStore
from hutch.providers.base import ChatRequest
from hutch.providers.images import prepare_messages
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.runtime.builtin import BuiltinRuntime
from tests.test_computer_image_delivery import FRAMES


@pytest.mark.parametrize("transition", ["take_over", "hand_back", "pause"])
def test_stop_wins_between_transition_precheck_and_mutation(monkeypatch, transition):
    lease = ControlLease("owned-session")
    original = lease._move

    def raced(owner, reason, **kwargs):
        if owner in (ControlOwner.agent, ControlOwner.human, ControlOwner.paused):
            original(ControlOwner.stopping, "concurrent stop")
        return original(owner, reason, **kwargs)

    monkeypatch.setattr(lease, "_move", raced)
    with pytest.raises(StaleControl):
        getattr(lease, transition)()
    assert lease.snapshot().owner is ControlOwner.stopping
    with pytest.raises(StaleControl):
        lease.begin_action()


def test_text_only_observation_is_withheld_without_requiring_an_image():
    original = [{"role": "tool", "name": "browser", "content": "PRIVATE-PAGE-SENTINEL",
                 "computer_observation": True, "tool_call_id": "call1"}]
    prepared, _ = prepare_messages(original, vision=False, frames=None, allow_observation_text=False)
    assert "PRIVATE-PAGE-SENTINEL" not in str(prepared)
    assert "withheld" in prepared[0]["content"]
    assert "computer_observation" not in prepared[0]
    assert original[0]["content"] == "PRIVATE-PAGE-SENTINEL", "local history is not mutated"


@pytest.mark.parametrize("consent", [False, True])
def test_runtime_checks_text_and_image_consent_before_the_official_request(config, consent):
    ref = FrameStore(config.run_dir("private-bot", "run1")).save(FRAMES[0], "image/png")
    requests = []

    def wire(request):
        import json
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
                                        "usage": {"prompt_tokens": 5, "completion_tokens": 1}})

    provider = OpenAICompatProvider("https://api.openai.com/v1", "wire-test-only", provider_name="openai")
    provider._client = httpx.Client(base_url=provider.base_url, transport=httpx.MockTransport(wire))
    ctx = SimpleNamespace(config=config, bot=SimpleNamespace(name="private-bot", observation_to_hosted=consent),
                          emit=lambda _event: None)
    run = SimpleNamespace(id="run1")
    session = SimpleNamespace(provider=provider, rung=SimpleNamespace(model="gpt-4.1"))
    messages = [{"role": "tool", "tool_call_id": "call1", "name": "browser",
                 "content": "PRIVATE-PAGE-SENTINEL", "images": [ref.internal()]}]
    prepared = BuiltinRuntime()._request_messages(ctx, run, session, messages)
    try:
        assert provider.chat(ChatRequest(model="gpt-4.1", messages=prepared, stream=False)).content == "done"
    finally:
        provider._client.close()
    body = str(requests[0])
    assert ("PRIVATE-PAGE-SENTINEL" in body) is consent
    assert ("data:image/png;base64," in body) is consent
    assert "frames/" not in body and "computer_observation" not in body


def test_model_name_does_not_infer_vision_for_a_custom_endpoint():
    assert not OpenAICompatProvider("http://localhost:1234/v1").supports_vision("gpt-4.1")
    official = OpenAICompatProvider("https://api.openai.com/v1")
    assert official.supports_vision("gpt-4.1") and official.supports_vision("gpt-4.1-2025-04-14")
    assert not official.supports_vision("gpt-4.1-imaginary") and not official.supports_vision("unknown")


def test_private_local_observations_block_hosted_fallback_including_derived_replies(config):
    from hutch.runtime.builtin import RunAborted
    ctx = SimpleNamespace(config=config, bot=SimpleNamespace(name="private", observation_to_hosted=False),
                          emit=lambda event: None)
    run = SimpleNamespace(id="r1")
    messages = [{"role": "tool", "name": "browser", "content": "PRIVATE-SENTINEL"}]
    local = SimpleNamespace(provider=SimpleNamespace(data_stays_local=lambda: True, supports_vision=lambda m: False),
                            rung=SimpleNamespace(model="local"))
    runtime = BuiltinRuntime()
    assert runtime._request_messages(ctx, run, local, messages)[0]["content"] == "PRIVATE-SENTINEL"
    messages.append({"role": "assistant", "content": "I saw PRIVATE-SENTINEL"})
    hosted = SimpleNamespace(provider=OpenAICompatProvider("https://api.openai.com/v1"),
                             rung=SimpleNamespace(model="gpt-4.1"))
    with pytest.raises(RunAborted, match="private local computer observations"):
        runtime._request_messages(ctx, run, hosted, messages)
