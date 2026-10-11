"""Versioned response-style contracts: sparse per-scope values, resolution by precedence, write-once run plans."""

from __future__ import annotations

import json
import time

import pytest

from hutch.models import Bot, Run, RunStatus, Task
from hutch.persona import (APPLICATION_DEFAULT, LAYER_LABELS, PERSONA_PROFILE_VERSION, PERSONA_VERSION,
                           PersonaPlan, PersonaStyle,
                           apply_persona_changes, contextualize_persona, decode_persona_state,
                           encode_persona_state, guidance, resolve_persona)
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
    assert {key: plan.sources[key] for key in ("depth", "tone", "banter")} == {
        "depth": "turn", "tone": "agent_override", "banter": "conversation"}
    assert plan.version == PERSONA_VERSION


def test_resolution_falls_back_to_the_application_default():
    plan = resolve_persona()
    assert (plan.depth, plan.tone, plan.humor, plan.banter) == ("auto", "neutral", "subtle", True)
    assert all(source == "application" for source in plan.sources.values())


def test_a_sparse_application_layer_keeps_the_built_in_fallbacks():
    plan = resolve_persona(application=PersonaStyle(depth="thorough"))
    assert (plan.depth, plan.tone) == ("detailed", "neutral")
    assert plan.sources["depth"] == plan.sources["tone"] == plan.sources["banter"] == "application"


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


def test_named_presets_set_voice_and_humor_without_changing_answer_depth():
    direct = resolve_persona(agent_override=PersonaStyle(preset="direct"))
    warm = resolve_persona(agent_override=PersonaStyle(preset="warm"))
    wit = resolve_persona(agent_override=PersonaStyle(preset="dry_wit"))
    assert (direct.preset, direct.tone, direct.humor, direct.depth) == ("direct", "direct", "off", "auto")
    assert (warm.preset, warm.tone, warm.humor, warm.depth) == ("warm", "warm", "off", "auto")
    assert (wit.preset, wit.tone, wit.humor, wit.depth) == ("dry_wit", "direct", "playful", "auto")


def test_higher_explicit_humor_overrides_a_preset_and_legacy_banter_stays_subtle():
    plan = resolve_persona(agent_preset=PersonaStyle(preset="dry_wit"),
                           agent_override=PersonaStyle(humor="off"))
    assert plan.humor == "off" and plan.banter is False and plan.sources["humor"] == "agent_override"
    legacy = resolve_persona(agent_override=PersonaStyle(banter=True))
    assert legacy.humor == "subtle" and legacy.banter is True
    migrated = apply_persona_changes(PersonaStyle(tone="warm", banter=True), {"preset": "dry_wit"})
    assert migrated.tone is None and migrated.banter is None
    assert resolve_persona(agent_override=migrated).humor == "playful"


def test_depth_alias_and_bounded_customization_round_trip_zero_and_empty_values():
    style = PersonaStyle(depth="thorough", warmth=0, directness=100, formality=0,
                         profanity="mirror", format_style="bullets", avoid_habits=[])
    encoded = encode_persona_state(style, 1)
    restored, revision = decode_persona_state(encoded)
    assert restored == style and revision == 1
    plan = resolve_persona(agent_override=style)
    assert plan.depth == "detailed"
    assert (plan.warmth, plan.directness, plan.formality) == (0, 100, 0)
    assert plan.profanity == "mirror" and plan.format_style == "bullets" and plan.avoid_habits == []


def test_depth_reads_v1_state_and_new_customization_is_bounded():
    assert decode_persona_state('{"version": 1, "revision": 2, "values": {"depth": "thorough"}}') == (
        PersonaStyle(depth="thorough"), 2)
    assert decode_persona_state('{"revision": 2, "values": {"banter": false}}') == (PersonaStyle(banter=False), 2)
    with pytest.raises(ValueError, match="version 1"):
        decode_persona_state('{"version": 1, "revision": 2, "values": {"humor": "off"}}')
    with pytest.raises(ValueError):
        PersonaStyle.model_validate({"warmth": 101})
    with pytest.raises(ValueError):
        PersonaStyle.model_validate({"avoid_habits": ["filler"] * 6})


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
    assert plan.version == PERSONA_VERSION and plan.humor_eligible is False
    text = guidance(plan)
    assert "Response style chosen for this run" in text
    assert "never overrides safety, permissions" in text
    assert "sensitive topics" in text.lower()
    assert "keep this turn plain" in text.lower()


def test_guidance_distinguishes_banter_on_and_off_without_stale_consent():
    on = guidance(contextualize_persona(resolve_persona(agent_override=PersonaStyle(banter=True)),
                                        "Tell me a joke about databases."))
    off = guidance(contextualize_persona(resolve_persona(agent_override=PersonaStyle(banter=False)),
                                         "Tell me a joke about databases."))
    assert "clearly playful" in on and "clearly playful" not in off
    assert "judge each turn fresh" in on            # playfulness is re-decided per turn, never carried over
    assert "direct request for safe, low-stakes humor" in off  # explicit current task beats a wording preference

    serious = contextualize_persona(resolve_persona(agent_override=PersonaStyle(banter=False)),
                                    "Tell me a joke about my debt and bankruptcy options.")
    assert "keep this turn plain" in guidance(serious)


def test_contextual_plan_keeps_clear_banter_brief_and_unretrieved():
    plan = contextualize_persona(resolve_persona(), "Tell me a silly pun about a database.")
    assert plan.intent == "banter"
    assert plan.resolved_depth == "brief"
    assert plan.humor_eligible is True
    assert plan.grounding_needs == []
    assert plan.diagnostic_reasons == ["clear_humor_request"]


def test_contextual_plan_preserves_existing_subtle_humor_discretion_on_unrestricted_turns():
    plan = contextualize_persona(resolve_persona(), "What is two plus two?")
    assert plan.intent == "general"
    assert plan.humor_eligible is True
    assert "judge each turn fresh" in guidance(plan)

    no_jokes = contextualize_persona(resolve_persona(), "No jokes, please.")
    assert no_jokes.humor_eligible is False
    assert no_jokes.intent == "general"


def test_contextual_plan_suppresses_humor_for_current_or_high_stakes_requests():
    current = contextualize_persona(resolve_persona(), "What is the latest weather forecast for Vancouver?")
    assert current.intent == "current_facts"
    assert current.resolved_depth == "detailed"
    assert current.grounding_needs == ["current_facts"]
    assert current.humor_eligible is False

    consequential = contextualize_persona(resolve_persona(), "Tell me a joke about my debt and bankruptcy options.")
    assert consequential.intent == "high_stakes"
    assert consequential.humor_eligible is False
    assert "high_stakes_cue" in consequential.diagnostic_reasons


def test_contextual_plan_preserves_recipient_and_output_contracts():
    draft = contextualize_persona(resolve_persona(), "Draft an email to my landlord asking for a repair.")
    assert draft.audience == "recipient"
    assert draft.intent == "recipient_draft"
    assert draft.output_contract == "recipient_draft"

    json_plan = contextualize_persona(resolve_persona(), "Return valid JSON with a name and status.")
    assert json_plan.output_contract == "json"

    code = contextualize_persona(resolve_persona(), "Write a Python function that sorts these records.")
    assert code.intent == "coding" and code.output_contract == "code"
    assert code.grounding_needs == ["workspace"]

    citations = contextualize_persona(resolve_persona(), "Explain the trade-offs with citations.")
    assert citations.output_contract == "citations"


@pytest.mark.parametrize(
    ("prompt", "expected_depth", "eligible"),
    [("Shorter, please.", "brief", False),
     ("Go deeper.", "detailed", False),
     ("Less banter.", "detailed", False),
     ("Please make that shorter, then explain why it matters, and use less banter in the revised answer.",
      "brief", False)],
)
def test_contextual_plan_applies_only_exact_current_answer_corrections(prompt, expected_depth, eligible):
    base = resolve_persona(agent_override=PersonaStyle(depth="detailed", humor="playful"))
    context = [{"role": "assistant", "content": "A previous answer."}]
    plan = contextualize_persona(base, prompt, conversation_context=context)
    assert plan.intent == "correction"
    assert plan.resolved_depth == expected_depth
    assert plan.humor_eligible is eligible
    assert plan.sources["resolved_depth"] == (
        "current_turn" if expected_depth != "detailed" or "Go deeper" in prompt else "agent_override")
    assert plan.grounding_needs == ["conversation"]


def test_correction_words_without_a_referenced_answer_do_not_become_durable_preferences():
    plan = contextualize_persona(resolve_persona(), "Please make future replies shorter.")
    assert plan.intent == "general"
    assert plan.resolved_depth == "standard"
    assert "answer_correction" not in plan.diagnostic_reasons

    unrelated = contextualize_persona(
        resolve_persona(), "Use the shorter route and keep the explanation factual.",
        conversation_context=[{"role": "assistant", "content": "A previous answer."}],
    )
    assert unrelated.intent == "general" and unrelated.resolved_depth == "standard"

    without_answer = contextualize_persona(
        resolve_persona(), "Shorter, please.", conversation_context=[{"role": "user", "content": "Question."}],
    )
    assert without_answer.intent == "general"


def test_contextual_plan_diagnostics_are_bounded_labels_not_user_text():
    sensitive_number = "123-45-6789"
    prompt = (f"Tell me a joke about {sensitive_number}, analyze the latest legal and financial news, "
              "write code, and return valid JSON with citations.")
    plan = contextualize_persona(resolve_persona(), prompt)
    assert len(plan.diagnostic_reasons) <= 4
    serialized = json.dumps(plan.model_dump(mode="json"))
    assert sensitive_number not in serialized
    assert "123-45-6789" not in serialized


def test_contextual_plan_marks_research_grounding_without_recording_queries():
    plan = contextualize_persona(resolve_persona(), "Research how the city changed after the 1906 earthquake.")
    assert plan.intent == "analysis"
    assert plan.grounding_needs == ["external_sources"]
    assert plan.output_contract == "freeform"
    assert plan.diagnostic_reasons == ["external_sources", "analytical_work"]


def test_version_two_write_once_plan_decodes_with_its_prior_depth_and_humor_behavior():
    old = PersonaPlan.model_validate({"version": 2, "depth": "brief", "tone": "warm", "banter": True})
    assert old.version == 2 and old.resolved_depth == "brief"
    assert old.humor_eligible is True


@pytest.mark.parametrize("bad_version", [True, 0, -1, "3"])
def test_response_plan_rejects_invalid_version_types_and_values(bad_version):
    with pytest.raises(ValueError, match="response-plan version"):
        PersonaPlan.model_validate({"version": bad_version, "depth": "brief", "tone": "neutral"})


def test_style_resolution_and_guidance_stay_under_the_local_budget():
    """The local p95 target is ≤20 ms; this measures Hutch's own work, never model latency."""
    import time as _time

    layers = dict(agent_preset=PersonaStyle(depth="thorough", tone="warm"),
                  agent_override=PersonaStyle(tone="direct", banter=False),
                  conversation=PersonaStyle(banter=True), turn=PersonaStyle(depth="brief"))
    prompt = "Tell me a joke about the database."
    context = [{"role": "assistant", "content": "A previous answer."}]
    samples = []
    for _ in range(500):
        start = _time.perf_counter()
        plan = contextualize_persona(resolve_persona(revisions={"agent": 3, "conversation": 2}, **layers),
                                     prompt, conversation_context=context)
        guidance(plan)
        samples.append((_time.perf_counter() - start) * 1000.0)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 <= 20.0, f"local style resolution p95 was {p95:.2f} ms"


# ============================================================ durable scopes and the write-once run plan

def test_bot_persona_round_trip_conflict_and_reset(store):
    bot = store.create_bot(Bot(name="style-bot", model="mock/demo", tools=[]))
    assert bot.persona_revision == 0 and bot.persona_override is None
    assert bot.persona_profile_version == PERSONA_PROFILE_VERSION

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


def test_legacy_bot_profile_loads_as_v1_then_upgrades_when_a_new_field_is_saved(store):
    bot = store.create_bot(Bot(name="legacy-profile", model="mock/demo", tools=[]))
    raw = json.loads(bot.store_json())
    raw.pop("persona_profile_version")
    raw["persona_override"] = {"depth": "thorough", "banter": False}
    store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (json.dumps(raw), bot.id))
    store._db.commit()

    legacy = store.get_bot(bot.id)
    assert legacy.persona_profile_version == 1
    assert legacy.persona_override.depth == "thorough" and legacy.persona_override.banter is False
    updated, created = store.update_bot_persona(bot.id, {"humor": "subtle", "warmth": 0}, expected_revision=0,
                                                idem_key="legacy-v2", request_hash="legacy-v2")
    assert created and updated.persona_profile_version == PERSONA_PROFILE_VERSION
    assert updated.persona_override.depth == "thorough"
    assert updated.persona_override.humor == "subtle" and updated.persona_override.warmth == 0


@pytest.mark.parametrize(
    ("profile_version", "override", "error_text"),
    [
        (1, {"depth": "ultra-long"}, "unreadable response-style profile"),
        (1, {"humor": "off"}, "fields this version 1"),
        (99, {"future_field": "kept"}, "version 99"),
    ],
)
def test_unreadable_or_future_bot_profiles_do_not_break_roster_or_get_overwritten(
    store, profile_version, override, error_text
):
    bot = store.create_bot(Bot(name="profile-compat", display_name="Profile Compat", model="mock/demo", tools=[]))
    sibling = store.create_bot(Bot(name="profile-sibling", model="mock/demo", tools=[]))
    raw = json.loads(bot.store_json())
    raw["persona_profile_version"] = profile_version
    raw["persona_override"] = override
    with store._lock:
        store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (json.dumps(raw), bot.id))
        store._db.commit()

    loaded = store.get_bot(bot.id)
    assert loaded is not None and loaded.persona_profile_error
    assert "Profile Compat" in loaded.persona_profile_error
    assert error_text in loaded.persona_profile_error
    assert loaded.persona_override is None and loaded.persona_preset is None
    assert {item.id for item in store.list_bots()} == {bot.id, sibling.id}
    with pytest.raises(ValueError, match="Profile Compat"):
        store.update_bot_persona(bot.id, {"depth": "brief"}, expected_revision=0,
                                 idem_key=f"bad-profile-{profile_version}", request_hash="bad-profile")

    # A normal unrelated Bot edit preserves the exact future/invalid profile for a compatible build.
    loaded.description = "Unrelated safe edit"
    store.upsert_bot(loaded)
    persisted = json.loads(store._db.execute("SELECT doc FROM bots WHERE id = ?", (bot.id,)).fetchone()["doc"])
    assert persisted["persona_profile_version"] == profile_version
    assert persisted["persona_override"] == override


def test_bot_persona_api_reports_only_the_affected_assistant_error(persona_client):
    client = persona_client
    broken = _make_bot(client, name="future-style")
    sibling = _make_bot(client, name="normal-style")
    store = client.app.state.store
    raw = json.loads(store._db.execute("SELECT doc FROM bots WHERE id = ?", (broken["id"],)).fetchone()["doc"])
    raw["persona_profile_version"] = PERSONA_PROFILE_VERSION + 10
    raw["persona_override"] = {"future": "shape"}
    store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (json.dumps(raw), broken["id"]))
    store._db.commit()

    response = client.get(f"/api/v1/bots/{broken['id']}/persona")
    assert response.status_code == 409
    assert "Future Style" in response.json()["detail"]
    roster = client.get("/api/bots")
    assert roster.status_code == 200
    bodies = roster.json()
    assert {item["id"] for item in bodies} == {broken["id"], sibling["id"]}
    failed_bot = next(item for item in bodies if item["id"] == broken["id"])
    okay_bot = next(item for item in bodies if item["id"] == sibling["id"])
    assert "persona_profile_error" in failed_bot
    assert "persona_profile_error" not in okay_bot


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
    prompt = "Tell me a joke about the database."
    run = Run(bot_id=bot.id, prompt=prompt, conversation_id=conversation["id"],
              persona_turn=PersonaStyle(banter=False))
    store.submit_conversation_message(conversation["id"], prompt, run, Task(bot_id=bot.id, prompt=prompt),
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
    assert {key: plan.sources[key] for key in ("depth", "tone", "banter")} == {
        "depth": "conversation", "tone": "agent_override", "banter": "turn"}
    assert plan.revisions["agent"] == 1 and plan.revisions["conversation"] == 1
    assert plan.intent == "banter" and plan.humor_eligible is True and plan.resolved_depth == "brief"


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
    assert state["revision"] == 0 and all(value is None for value in state["override"].values())
    assert state["effective"]["depth"] == {"value": "auto", "source": "application"}

    saved = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                         json={"preset": "warm", "depth": "brief", "humor": "off", "banter": False,
                               "warmth": 0, "avoid_habits": [], "expected_revision": 0},
                         headers={"Idempotency-Key": "persona-save-1"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["revision"] == 1 and body["profile_version"] == PERSONA_PROFILE_VERSION
    assert body["override"]["depth"] == "brief" and body["override"]["banter"] is False
    assert body["override"]["humor"] == "off" and body["override"]["warmth"] == 0
    assert body["override"]["avoid_habits"] == []
    assert body["effective"]["banter"] == {"value": False, "source": "agent_override"}

    replay = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                          json={"preset": "warm", "depth": "brief", "humor": "off", "banter": False,
                                "warmth": 0, "avoid_habits": [], "expected_revision": 0},
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
    assert cleared.json()["effective"]["depth"] == {"value": "auto", "source": "application"}

    invalid = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                           json={"depth": "verbose", "expected_revision": 2},
                           headers={"Idempotency-Key": "persona-save-4"})
    assert invalid.status_code == 422
    out_of_bounds = client.patch(f"/api/v1/bots/{bot['id']}/persona",
                                 json={"warmth": 101, "expected_revision": 2},
                                 headers={"Idempotency-Key": "persona-save-4b"})
    assert out_of_bounds.status_code == 422

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
    assert plan is not None
    assert {key: plan.sources[key] for key in ("depth", "tone", "banter")} == {
        "depth": "turn", "tone": "conversation", "banter": "application"}


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


def test_engine_fails_closed_for_a_future_bot_profile_with_an_agent_specific_error(store, config, monkeypatch):
    bot = store.create_bot(Bot(name="future-bot-style", display_name="Future Bot", model="mock/demo", tools=[]))
    raw = json.loads(store._db.execute("SELECT doc FROM bots WHERE id = ?", (bot.id,)).fetchone()["doc"])
    raw["persona_profile_version"] = PERSONA_PROFILE_VERSION + 1
    raw["persona_override"] = {"future_voice": "unknown"}
    store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (json.dumps(raw), bot.id))
    store._db.commit()
    conversation, _ = store.create_conversation(bot.id, "future profile", idem_key="fp-create", request_hash="fp-create")
    run = Run(bot_id=bot.id, prompt="hello", conversation_id=conversation["id"])
    store.submit_conversation_message(conversation["id"], "hello", run, Task(bot_id=bot.id, prompt="hello"),
                                      idem_key="fp-send", request_hash="fp-send")
    _stub_dispatch(store, config, monkeypatch)

    failed = _wait_terminal(store, run.id)
    assert failed.status is RunStatus.failed and failed.exit_reason == "persona_unavailable"
    assert "Future Bot" in failed.error and "does not support" in failed.error


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
