"""Versioned response-style contracts: sparse per-scope values, resolution by precedence, write-once run plans."""

from __future__ import annotations

import time

import pytest

from hutch.models import Bot, Run, RunStatus, Task
from hutch.persona import (APPLICATION_DEFAULT, LAYER_LABELS, PERSONA_VERSION, PersonaPlan, PersonaStyle,
                           apply_persona_changes, decode_persona_state, encode_persona_state, guidance,
                           resolve_persona)
from hutch.store import LeaseLost, PersonaConflict


def test_unset_fields_inherit_and_explicit_false_is_kept():
    style = PersonaStyle(banter=False)
    assert style.depth is None and style.banter is False
    merged = apply_persona_changes(style, {"depth": "brief", "banter": None})
    assert merged.depth == "brief" and merged.banter is None and merged.tone is None


def test_resolution_prefers_the_highest_layer_and_records_origins():
    plan = resolve_persona(
        agent_preset=PersonaStyle(depth="thorough", tone="warm"),
        agent_override=PersonaStyle(tone="direct", banter=False),
        conversation=PersonaStyle(banter=True),
        turn=PersonaStyle(depth="brief"))
    assert (plan.depth, plan.tone, plan.banter) == ("brief", "direct", True)      # turn -> conversation -> override
    assert plan.sources == {"depth": "turn", "tone": "agent_override", "banter": "conversation"}
    assert plan.version == PERSONA_VERSION


def test_resolution_falls_back_to_the_application_default():
    plan = resolve_persona()
    assert (plan.depth, plan.tone, plan.banter) == ("standard", "neutral", APPLICATION_DEFAULT.banter)
    assert plan.sources == {"depth": "application", "tone": "application", "banter": "application"}


def test_a_sparse_application_layer_keeps_the_built_in_fallbacks():
    plan = resolve_persona(application=PersonaStyle(depth="thorough"))
    assert (plan.depth, plan.tone) == ("thorough", "neutral")
    assert plan.sources == {"depth": "application", "tone": "application", "banter": "application"}


def test_reset_clears_one_layer_without_touching_the_others():
    style = PersonaStyle(depth="brief", tone="warm", banter=False)
    reset = apply_persona_changes(style, {"tone": None})
    assert reset.depth == "brief" and reset.tone is None and reset.banter is False
    plan = resolve_persona(agent_override=reset)
    assert plan.tone == "neutral" and plan.sources["tone"] == "application"


def test_override_precedence_beats_preset_and_preset_beats_default():
    plan = resolve_persona(agent_preset=PersonaStyle(banter=True))
    assert plan.banter is True and plan.sources["banter"] == "agent_preset"
    plan = resolve_persona(agent_preset=PersonaStyle(banter=True), agent_override=PersonaStyle(banter=False))
    assert plan.banter is False and plan.sources["banter"] == "agent_override"


def test_state_round_trip_and_revision_guards():
    style = PersonaStyle(depth="thorough", banter=False)
    raw = encode_persona_state(style, 3)
    assert decode_persona_state(raw) == (style, 3)
    assert decode_persona_state("") == (None, 0)
    assert decode_persona_state(encode_persona_state(None, 2)) == (None, 2)
    with pytest.raises(ValueError, match="newer"):
        decode_persona_state('{"version": 99, "revision": 1, "values": {}}')


def test_invalid_values_are_rejected():
    with pytest.raises(ValueError):
        PersonaStyle.model_validate({"depth": "verbose"})
    with pytest.raises(ValueError):
        apply_persona_changes(None, {"warmth": "high"})


def test_layer_labels_cover_every_resolution_source():
    assert set(LAYER_LABELS) == {"application", "agent_preset", "agent_override", "conversation", "turn"}


# ============================================================ rendering and the local budget

def test_guidance_states_the_style_and_stays_subordinate():
    plan = resolve_persona(agent_override=PersonaStyle(depth="brief", tone="warm", banter=False))
    text = guidance(plan)
    assert "Response style chosen for this run" in text
    assert "never overrides safety, permissions" in text
    assert "sensitive topics" in text.lower()
    assert "do not use playful or joking language" in text.lower()


def test_guidance_distinguishes_banter_on_and_off_without_stale_consent():
    on = guidance(resolve_persona(agent_override=PersonaStyle(banter=True)))
    off = guidance(resolve_persona(agent_override=PersonaStyle(banter=False)))
    assert "clearly joking" in on and "clearly joking" not in off
    assert "judge every turn fresh" in on            # playfulness is re-decided per turn, never carried over


def test_style_resolution_and_guidance_stay_under_the_local_budget():
    """The local p95 target is ≤20 ms; this measures Hutch's own work, never model latency."""
    import time as _time

    layers = dict(agent_preset=PersonaStyle(depth="thorough", tone="warm"),
                  agent_override=PersonaStyle(tone="direct", banter=False),
                  conversation=PersonaStyle(banter=True), turn=PersonaStyle(depth="brief"))
    samples = []
    for _ in range(200):
        start = _time.perf_counter()
        guidance(resolve_persona(revisions={"agent": 3, "conversation": 2}, **layers))
        samples.append((_time.perf_counter() - start) * 1000.0)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 <= 20.0, f"local style resolution p95 was {p95:.2f} ms"


# ============================================================ durable scopes and the write-once run plan

def test_bot_persona_round_trip_conflict_and_reset(store):
    bot = store.create_bot(Bot(name="style-bot", model="mock/demo", tools=[]))
    assert bot.persona_revision == 0 and bot.persona_override is None

    updated, created = store.update_bot_persona(bot.id, {"tone": "warm", "banter": False},
                                                expected_revision=0, idem_key="bp-1", request_hash="bp-1")
    assert created and updated.persona_revision == 1
    assert updated.persona_override.tone == "warm" and updated.persona_override.banter is False

    replay, created = store.update_bot_persona(bot.id, {"tone": "warm", "banter": False},
                                               expected_revision=0, idem_key="bp-1", request_hash="bp-1")
    assert not created and replay.persona_revision == 1

    with pytest.raises(PersonaConflict):
        store.update_bot_persona(bot.id, {"depth": "brief"}, expected_revision=0,
                                 idem_key="bp-2", request_hash="bp-2")

    cleared, created = store.update_bot_persona(bot.id, {"tone": None}, expected_revision=1,
                                                idem_key="bp-3", request_hash="bp-3")
    assert created and cleared.persona_revision == 2 and cleared.persona_override.tone is None
    assert cleared.persona_override.banter is False            # untouched fields stay

    stored = store.get_bot(bot.id)
    assert stored.persona_revision == 2 and stored.persona_override.banter is False


def test_conversation_persona_round_trip_conflict_and_reset(store):
    bot = store.create_bot(Bot(name="style-chat", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "style", idem_key="cp-create", request_hash="cp-create")
    assert store.read_conversation_persona(conversation["id"]) == (None, 0)

    style, revision, created = store.update_conversation_persona(
        conversation["id"], {"depth": "brief"}, expected_revision=0, idem_key="cp-1", request_hash="cp-1")
    assert created and revision == 1 and style.depth == "brief"

    replay, revision, created = store.update_conversation_persona(
        conversation["id"], {"depth": "brief"}, expected_revision=0, idem_key="cp-1", request_hash="cp-1")
    assert not created and revision == 1 and replay.depth == "brief"

    with pytest.raises(PersonaConflict):
        store.update_conversation_persona(conversation["id"], {"banter": False}, expected_revision=0,
                                          idem_key="cp-2", request_hash="cp-2")

    style, revision, created = store.update_conversation_persona(
        conversation["id"], {"depth": None, "banter": True}, expected_revision=1,
        idem_key="cp-3", request_hash="cp-3")
    assert created and revision == 2 and style.depth is None and style.banter is True


PLAN = {"version": PERSONA_VERSION, "depth": "brief", "tone": "neutral", "banter": True,
        "sources": {"depth": "turn", "tone": "application", "banter": "application"}, "revisions": {}}


def test_run_persona_plan_is_written_at_start(store):
    bot = store.create_bot(Bot(name="plan-bot", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="hello")
    store.submit_run(run, Task(bot_id=bot.id, prompt="hello"))
    claimed = store.claim_run(run.id, "plan-test", 60)

    started = store.transition_run(run.id, RunStatus.running, fence=claimed.fence,
                                   event={"origin": "manual"}, persona_plan=PLAN)
    assert started.persona_plan is not None and started.persona_plan.depth == "brief"
    assert started.persona_plan.sources["depth"] == "turn" and started.persona_plan.version == PERSONA_VERSION
    assert store.get_run(run.id).persona_plan.banter is True


def test_a_persisted_persona_plan_cannot_be_replaced(store):
    bot = store.create_bot(Bot(name="plan-bot", model="mock/demo", tools=[]))
    plan = PersonaPlan(depth="brief", tone="neutral", banter=True,
                       sources={"depth": "turn", "tone": "application", "banter": "application"})
    run = Run(bot_id=bot.id, prompt="hello", persona_plan=plan)
    store.submit_run(run, Task(bot_id=bot.id, prompt="hello"))
    claimed = store.claim_run(run.id, "plan-test", 60)

    different = plan.model_dump(mode="json") | {"depth": "thorough"}
    with pytest.raises(LeaseLost, match="immutable"):
        store.transition_run(run.id, RunStatus.running, fence=claimed.fence, persona_plan=different)

    started = store.transition_run(run.id, RunStatus.running, fence=claimed.fence,
                                   persona_plan=plan.model_dump(mode="json"))
    assert started.status is RunStatus.running and started.persona_plan.depth == "brief"


def test_a_persona_plan_can_only_be_captured_when_a_run_starts(store):
    bot = store.create_bot(Bot(name="plan-bot", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="hello")
    store.submit_run(run, Task(bot_id=bot.id, prompt="hello"))
    claimed = store.claim_run(run.id, "plan-test", 60)
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)

    with pytest.raises(ValueError, match="run starts"):
        store.transition_run(run.id, RunStatus.succeeded, fence=claimed.fence, persona_plan=PLAN)
    assert store.get_run(run.id).status is RunStatus.running       # the refusal changed nothing


def test_engine_captures_the_resolved_persona_plan_at_start(store, config, monkeypatch):
    import hutch.engine as engine_module
    from hutch.engine import Engine

    class Runtime:
        kind = "fixture"

        def execute(self, run, ctx, tools, stop):
            return "ok"

    monkeypatch.setattr(engine_module, "get_runtime", lambda _: Runtime())
    bot = store.create_bot(Bot(name="plan-engine", model="mock/demo", tools=[]))
    store.update_bot_persona(bot.id, {"tone": "warm"}, expected_revision=0, idem_key="eng-1", request_hash="eng-1")
    bot = store.get_bot(bot.id)
    bot.persona_preset = PersonaStyle(depth="thorough")
    store.upsert_bot(bot)

    conversation, _ = store.create_conversation(bot.id, "plan", idem_key="eng-create", request_hash="eng-create")
    store.update_conversation_persona(conversation["id"], {"depth": "brief"}, expected_revision=0,
                                      idem_key="eng-2", request_hash="eng-2")

    engine = Engine(config, store)
    run = Run(bot_id=bot.id, prompt="hello", conversation_id=conversation["id"],
              persona_turn=PersonaStyle(banter=False))
    store.submit_conversation_message(conversation["id"], "hello", run, Task(bot_id=bot.id, prompt="hello"),
                                      idem_key="eng-3", request_hash="eng-3")
    engine.dispatch_pending()
    deadline = time.time() + 10
    while time.time() < deadline:
        if store.get_run(run.id).status in (RunStatus.succeeded, RunStatus.failed, RunStatus.stopped):
            break
        time.sleep(0.05)

    stored = store.get_run(run.id)
    assert stored.status is RunStatus.succeeded, stored.reason
    plan = stored.persona_plan
    assert plan is not None
    assert (plan.depth, plan.tone, plan.banter) == ("brief", "warm", False)
    assert plan.sources == {"depth": "conversation", "tone": "agent_override", "banter": "turn"}
    assert plan.revisions["agent"] == 1 and plan.revisions["conversation"] == 1


# ============================================================ API: scoped saves with revision conflicts and reset

@pytest.fixture()
def persona_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        yield client


def _make_bot(client, name="style-api"):
    created = client.post("/api/bots", json={"name": name, "model": "mock/demo", "tools": []})
    assert created.status_code in (200, 201), created.text
    return created.json()


def test_bot_persona_api_is_revision_aware_and_resets_fields(persona_client):
    client = persona_client
    bot = _make_bot(client)

    state = client.get(f"/api/v1/bots/{bot['id']}/persona").json()
    assert state["revision"] == 0 and state["override"] == {"depth": None, "tone": None, "banter": None}
    assert state["effective"]["depth"] == {"value": "standard", "source": "application"}

    saved = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                         json={"depth": "brief", "banter": False, "expected_revision": 0},
                         headers={"Idempotency-Key": "persona-save-1"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["revision"] == 1 and body["override"]["depth"] == "brief" and body["override"]["banter"] is False
    assert body["effective"]["banter"] == {"value": False, "source": "agent_override"}

    replay = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                          json={"depth": "brief", "banter": False, "expected_revision": 0},
                          headers={"Idempotency-Key": "persona-save-1"})
    assert replay.status_code == 200 and replay.json()["revision"] == 1      # idempotent retry, not a conflict

    stale = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                         json={"depth": "thorough", "expected_revision": 0},
                         headers={"Idempotency-Key": "persona-save-2"})
    assert stale.status_code == 409 and "revision" in stale.json()["detail"]

    cleared = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                           json={"depth": None, "expected_revision": 1},
                           headers={"Idempotency-Key": "persona-save-3"})
    assert cleared.status_code == 200 and cleared.json()["revision"] == 2
    assert cleared.json()["effective"]["depth"] == {"value": "standard", "source": "application"}

    invalid = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                           json={"depth": "verbose", "expected_revision": 2},
                           headers={"Idempotency-Key": "persona-save-4"})
    assert invalid.status_code == 422

    empty = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                         json={"expected_revision": 2},
                         headers={"Idempotency-Key": "persona-save-5"})
    assert empty.status_code == 422


def test_conversation_persona_api_and_next_reply_plan(persona_client):
    client = persona_client
    bot = _make_bot(client, name="style-chat-api")
    created = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Style"},
                          headers={"Idempotency-Key": "persona-conv-create"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    state = client.get(f"/api/v1/conversations/{conversation_id}/persona").json()
    assert state["revision"] == 0 and state["effective"]["tone"] == {"value": "neutral", "source": "application"}

    saved = client.patch(f"/api/v1/conversations/{conversation_id}/persona",
                         json={"tone": "warm", "expected_revision": 0},
                         headers={"Idempotency-Key": "persona-conv-1"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert saved.json()["effective"]["tone"] == {"value": "warm", "source": "conversation"}

    stale = client.patch(f"/api/v1/conversations/{conversation_id}/persona",
                         json={"tone": "direct", "expected_revision": 0},
                         headers={"Idempotency-Key": "persona-conv-2"})
    assert stale.status_code == 409

    sent = client.post(f"/api/v1/conversations/{conversation_id}/messages",
                       json={"prompt": "hello", "persona": {"depth": "brief"}},
                       headers={"Idempotency-Key": "persona-send-1"})
    assert sent.status_code == 201, sent.text
    run_id = sent.json()["id"]
    store = client.app.state.store
    assert store.get_run(run_id).persona_turn.depth == "brief"               # one-turn choice rides the run only
    deadline = time.time() + 15
    while time.time() < deadline:
        if store.get_run(run_id).status in (RunStatus.succeeded, RunStatus.failed, RunStatus.stopped):
            break
        time.sleep(0.1)
    plan = store.get_run(run_id).persona_plan
    assert plan is not None and plan.sources == {"depth": "turn", "tone": "conversation", "banter": "application"}


# ============================================================ independent-review regressions

def _stub_dispatch(store, config, monkeypatch):
    import hutch.engine as engine_module
    from hutch.engine import Engine

    class Runtime:
        kind = "fixture"

        def execute(self, run, ctx, tools, stop):
            return "ok"

    monkeypatch.setattr(engine_module, "get_runtime", lambda _: Runtime())
    Engine(config, store).dispatch_pending()


def _wait_terminal(store, run_id):
    deadline = time.time() + 10
    while time.time() < deadline:
        run = store.get_run(run_id)
        if run.status in (RunStatus.succeeded, RunStatus.failed, RunStatus.stopped):
            return run
        time.sleep(0.05)
    raise AssertionError("the run did not reach a terminal state")


def test_a_stale_full_document_save_cannot_roll_back_the_saved_style(store):
    bot = store.create_bot(Bot(name="stale-bot", model="mock/demo", tools=[]))
    stale = store.get_bot(bot.id)
    store.update_bot_persona(bot.id, {"depth": "brief"}, expected_revision=0, idem_key="sp-1", request_hash="sp-1")

    stale.instructions = "edited elsewhere"
    store.upsert_bot(stale)

    saved = store.get_bot(bot.id)
    assert saved.instructions == "edited elsewhere"          # the unrelated edit lands
    assert saved.persona_override.depth == "brief"           # the guarded style survives
    assert saved.persona_revision == 1


def test_engine_fails_closed_when_the_conversation_style_state_is_unreadable(store, config, monkeypatch):
    bot = store.create_bot(Bot(name="broken-style", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "broken", idem_key="bs-create", request_hash="bs-create")
    with store._lock:
        store._db.execute("UPDATE conversations SET persona = ? WHERE id = ?",
                          ('{"version": 99, "revision": 1, "values": {}}', conversation["id"]))
        store._db.commit()

    run = Run(bot_id=bot.id, prompt="hello", conversation_id=conversation["id"])
    store.submit_conversation_message(conversation["id"], "hello", run, Task(bot_id=bot.id, prompt="hello"),
                                      idem_key="bs-send", request_hash="bs-send")
    _stub_dispatch(store, config, monkeypatch)

    failed = _wait_terminal(store, run.id)
    assert failed.status is RunStatus.failed and failed.exit_reason == "persona_unavailable"
    assert "newer Hutch" in failed.error


def test_engine_fails_closed_on_a_newer_stored_plan(store, config, monkeypatch):
    bot = store.create_bot(Bot(name="newer-plan", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "newer", idem_key="np-create", request_hash="np-create")
    plan = PersonaPlan(version=PERSONA_VERSION + 1, depth="brief", tone="neutral", banter=True)
    run = Run(bot_id=bot.id, prompt="hello", conversation_id=conversation["id"], persona_plan=plan)
    store.submit_conversation_message(conversation["id"], "hello", run, Task(bot_id=bot.id, prompt="hello"),
                                      idem_key="np-send", request_hash="np-send")
    _stub_dispatch(store, config, monkeypatch)

    failed = _wait_terminal(store, run.id)
    assert failed.status is RunStatus.failed and failed.exit_reason == "persona_unavailable"
    assert "newer Hutch" in failed.error
