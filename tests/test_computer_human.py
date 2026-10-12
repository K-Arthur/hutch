"""Bounded human authority, private frames, input deduplication and lost-supervision behavior."""
import threading
import time
from types import SimpleNamespace

import pytest

from hutch.computer.control import ControlLease, ControlOwner
from hutch.computer.human import HumanSession, HumanError
from tests.test_computer_image_delivery import FRAMES


@pytest.fixture()
def human(config):
    calls = []
    ctx = SimpleNamespace(config=config, run=SimpleNamespace(id="human-test"), on_finish=[], cancel_hooks=[])
    def dispatch(command, identity, check):
        check()
        calls.append((command["action"], command.get("text")))
    session = HumanSession(ctx, "browser", ControlLease("session1"), lambda: (FRAMES[0], {"tab": "t1"}), dispatch)
    yield session, calls
    session.close()


def _call(session, owner, body):
    result = []
    def call():
        try: result.append(session.command(owner, body))
        except Exception as exc: result.append(exc)
    thread = threading.Thread(target=call)
    thread.start()
    deadline = time.monotonic() + 2
    while not session._queue and not result and time.monotonic() < deadline:
        time.sleep(0.01)
    session.pump()
    thread.join(timeout=2)
    assert result, "worker command did not settle"
    return result[0]


def _capture(session, owner="viewer1"):
    grant = session.takeover(owner)
    body = {"action": "capture", "control_token": grant["control_token"], "generation": grant["generation"], "sequence": 1}
    answer = _call(session, owner, body)
    assert isinstance(answer, dict), answer
    return grant, answer["frame"]


def test_fresh_frame_only_one_viewer_and_no_old_input_replay(human):
    session, calls = human
    grant, frame = _capture(session)
    with pytest.raises(HumanError, match="another viewer"):
        session.takeover("viewer2")
    time.sleep(0.21)
    body = {"action": "type", "control_token": grant["control_token"], "generation": grant["generation"],
            "sequence": 2, "frame_id": frame["frame_id"], "text": "PRIVATE-HUMAN-SENTINEL"}
    answer = _call(session, "viewer1", body)
    assert isinstance(answer, dict) and calls == [("type", "PRIVATE-HUMAN-SENTINEL")]
    assert "PRIVATE-HUMAN-SENTINEL" not in str(answer) + str(session.public())
    assert session.command("viewer1", body) == answer and len(calls) == 1
    with pytest.raises(HumanError, match="different command"):
        session.command("viewer1", {**body, "text": "other"})
    time.sleep(0.21)
    stale = _call(session, "viewer1", {**body, "sequence": 3})
    assert isinstance(stale, HumanError) and "fresh human frame" in str(stale) and len(calls) == 1


def test_stop_expiry_and_revocation_fence_human_input(human):
    session, calls = human
    grant, frame = _capture(session)
    session._authorized = lambda: False
    with pytest.raises(HumanError, match="revoked"):
        session.command("viewer1", {"action": "heartbeat", "control_token": grant["control_token"], "generation": grant["generation"]})
    assert session.lease.snapshot().owner is ControlOwner.paused and not calls
    session._authorized = lambda: True
    grant = session.takeover("viewer2")
    session._expires = time.monotonic() - 1
    assert session._closed.wait(1.2) is False
    assert session.lease.snapshot().owner is ControlOwner.paused and not session.public()["controller_present"]
    grant = session.takeover("viewer3")
    session.lease.request_stop()
    with pytest.raises(HumanError, match="generation changed"):
        session.command("viewer3", {"action": "heartbeat", "control_token": grant["control_token"], "generation": grant["generation"]})
    with pytest.raises(HumanError): session.takeover("viewer4")


def test_wrong_viewer_old_generation_coordinates_and_queue_budget(human):
    session, calls = human
    grant, frame = _capture(session)
    base = {"action": "click", "control_token": grant["control_token"], "generation": grant["generation"], "sequence": 2,
            "frame_id": frame["frame_id"], "x": frame["width"], "y": 0}
    with pytest.raises(HumanError, match="does not own"):
        session.command("different-viewer", base)
    time.sleep(0.21)
    result = _call(session, "viewer1", base)
    assert isinstance(result, HumanError) and "outside" in str(result) and not calls
    with pytest.raises(HumanError, match="generation changed"):
        session.command("viewer1", {**base, "generation": base["generation"] + 1})


def test_timed_out_queued_input_never_arrives_later(human, monkeypatch):
    import hutch.computer.human as channel
    session, calls = human
    grant, frame = _capture(session)
    time.sleep(0.21)
    monkeypatch.setattr(channel, "COMMAND_SECONDS", 0.04)
    monkeypatch.setattr(channel, "ACK_SECONDS", 0.08)
    body = {"action": "type", "control_token": grant["control_token"], "generation": grant["generation"],
            "sequence": 2, "frame_id": frame["frame_id"], "text": "EXPIRED-INPUT"}
    with pytest.raises(HumanError, match="not acknowledged"):
        session.command("viewer1", body)  # the owning worker is deliberately not pumping
    session.pump()
    assert not calls and not session._queue
    with pytest.raises(HumanError, match="expired before dispatch"):
        session.command("viewer1", body)


def test_plan_is_invalid_after_a_complete_takeover_during_inference():
    from hutch.computer.human import plan_fence, plan_changed
    lease = ControlLease("surface")
    ctx = SimpleNamespace(computer_leases=[lease])
    fence = plan_fence(ctx)
    lease.take_over()
    lease.hand_back()
    assert plan_changed(ctx, fence) and lease.snapshot().owner is ControlOwner.agent
    # A surface created by the first tool in a batch is also invalid after intervention.
    assert plan_changed(ctx, {})


def test_handback_cannot_overlap_an_inflight_input(human):
    session, calls = human
    grant, frame = _capture(session)
    base = {"control_token": grant["control_token"], "generation": grant["generation"]}
    def dispatch(command, identity, check):
        check()
        with pytest.raises(HumanError, match="still pending"):
            session.command("viewer1", {**base, "action": "resume"})
        calls.append(command["action"])
    session.dispatch = dispatch
    time.sleep(0.21)
    result = _call(session, "viewer1", {**base, "action": "type", "sequence": 2,
                                      "frame_id": frame["frame_id"], "text": "hello"})
    assert isinstance(result, dict) and calls == ["type"]


def test_runtime_discards_a_reply_after_takeover_and_handback_during_model_call(store, config, tmp_path):
    from tests.fakes import FakeOllama
    from tests.test_runtime_builtin import build, factory, runtime, run_it, WRITE
    server = FakeOllama({"fake:8b": {}})
    ctx, run, events, tools = build(store, config, tmp_path)
    lease = ControlLease("inference-surface")
    ctx.computer_leases.append(lease)
    count = 0
    def reply(body):
        nonlocal count
        count += 1
        if count == 1:
            lease.take_over()
            lease.hand_back()
            return {"tool_calls": [WRITE]}
        return {"content": "fresh response"}
    server.script = reply
    try:
        assert run_it(runtime(provider_factory=factory(ollama=server)), run, ctx, tools) == "fresh response"
        assert not (ctx.workspace / "out.md").exists() and count == 2
    finally:
        server.close()
