"""Chooser-step state tests (slice 02): pure route decisions, no HTTP.

Clocks are fixed at 2026-10-29T18:00:00+00:00 so revision, TTL and expiry
boundaries are deterministic. Copy lives in the page layer and is not asserted
here except where the honest recommendation qualifier is contractual.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import hutch.onboarding_choices as onboarding_choices
from hutch.models import iso
from hutch.onboarding import (
    ONBOARDING_CONTRACT_VERSION,
    ONBOARDING_REQUIREMENTS_VERSION,
    apply_request_edit,
    default_setup,
    encode_setup,
    parse_setup,
)
from hutch.onboarding_store import SETUP_KEY, load_setup, save_request, save_route
from hutch.onboarding_choices import (
    RECOMMENDED_ROUTE,
    ROUTE_KINDS,
    ROUTE_LABELS,
    STATE_AI_SERVICE_CHOOSE,
    STATE_AI_SERVICE_CHOSEN,
    STATE_AI_SERVICE_NO_REQUEST,
    STATE_AI_SERVICE_STALE,
    STALE_EXPIRED,
    STALE_ROUTE_REMOVED,
    choose_route,
    chooser_ready,
    chooser_view,
    route_options,
)

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)
NON_LATIN_REQUEST = "Juno 助手 - Zoë Ångström - محمد - plan the launch"


def _saved(text: str = "Help me plan a launch week", *, now: datetime = NOW):
    """Accepted request save, the record the chooser carries."""
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    return result.setup


def _raw(**overrides) -> str:
    return json.dumps(default_setup(NOW).model_dump() | overrides)


def test_options_offer_exactly_three_routes_with_one_honest_recommendation():
    options = route_options()
    assert tuple(option.kind for option in options) == ROUTE_KINDS
    recommended = [option for option in options if option.recommended]
    assert [option.kind for option in recommended] == [RECOMMENDED_ROUTE]
    assert all(option.label and option.description for option in options)
    view = chooser_view(_saved(), now=NOW)
    assert "already have" in view.recommended_qualifier.lower()
    assert "provider key" in view.recommended_qualifier.lower()


def test_default_view_carries_the_request_and_offers_a_choice():
    saved = _saved(NON_LATIN_REQUEST)
    view = chooser_view(saved, now=LATER)
    assert view.state == STATE_AI_SERVICE_CHOOSE
    assert view.selected_route is None and view.selected_label == ""
    assert view.request_text == NON_LATIN_REQUEST
    assert (view.revision, view.step_index, view.required_total) == (saved.revision, 1, 5)
    assert view.can_choose and not view.stale and not view.expired and not view.newer_version


@pytest.mark.parametrize("kind", ROUTE_KINDS)
def test_each_route_kind_is_accepted_and_recorded(kind):
    saved = _saved()
    result = choose_route(saved, expected_revision=saved.revision, route_kind=kind, now=LATER)
    assert result.kind == "chosen" and result.setup is not None
    chosen = result.setup
    assert chosen.route_kind == kind
    assert chosen.route_chosen_at == iso(LATER)
    assert chosen.revision == saved.revision + 1
    assert chosen.step == "ai_service"
    assert chosen.request_text == saved.request_text
    assert chosen.updated_at == iso(LATER)
    view = chooser_view(chosen, now=LATER)
    assert view.state == STATE_AI_SERVICE_CHOSEN
    assert view.selected_route == kind and view.selected_label == ROUTE_LABELS[kind]
    assert not view.can_choose
    assert view.step_index == 2


@pytest.mark.parametrize("kind", ["", "  ", "telegram", "local_stub", "HOSTED_KEY"])
def test_unknown_route_is_invalid_and_writes_nothing(kind):
    saved = _saved()
    result = choose_route(saved, expected_revision=saved.revision, route_kind=kind, now=LATER)
    assert result.kind == "invalid" and result.setup == saved and result.reason


def test_negative_expected_revision_is_invalid():
    saved = _saved()
    result = choose_route(saved, expected_revision=-1, route_kind="opencode", now=LATER)
    assert result.kind == "invalid" and result.setup == saved


def test_same_choice_replays_even_from_a_duplicate_submit_revision():
    saved = _saved()
    chosen = choose_route(saved, expected_revision=saved.revision, route_kind="opencode", now=NOW)
    assert chosen.kind == "chosen"
    replay = choose_route(chosen.setup, expected_revision=saved.revision, route_kind="opencode", now=LATER)
    assert replay.kind == "replayed" and replay.setup == chosen.setup
    assert replay.setup.revision == chosen.setup.revision


def test_different_choice_on_current_revision_is_a_deliberate_change():
    saved = _saved()
    first = choose_route(saved, expected_revision=saved.revision, route_kind="hosted_key", now=NOW)
    changed = choose_route(first.setup, expected_revision=first.setup.revision,
                           route_kind="local_service", now=LATER)
    assert changed.kind == "chosen" and changed.setup is not None
    assert changed.setup.route_kind == "local_service"
    assert changed.setup.revision == first.setup.revision + 1


def test_different_choice_from_a_stale_revision_is_a_conflict_carrying_current_record():
    saved = _saved()
    first = choose_route(saved, expected_revision=saved.revision, route_kind="hosted_key", now=NOW)
    conflict = choose_route(first.setup, expected_revision=saved.revision,
                            route_kind="opencode", now=LATER)
    assert conflict.kind == "conflict" and conflict.setup == first.setup
    assert conflict.setup.route_kind == "hosted_key"


def test_chooser_is_not_ready_without_a_saved_request():
    blank = default_setup(NOW)
    assert chooser_ready(blank) is False
    view = chooser_view(blank, now=NOW)
    assert view.state == STATE_AI_SERVICE_NO_REQUEST
    assert not view.can_choose
    result = choose_route(blank, expected_revision=0, route_kind="hosted_key", now=NOW)
    assert result.kind == "no_request" and result.setup == blank


def test_route_fields_round_trip_through_encoding():
    saved = _saved()
    chosen = choose_route(saved, expected_revision=saved.revision, route_kind="local_service", now=NOW)
    raw = encode_setup(chosen.setup)
    record = parse_setup(raw)
    assert record.kind == "present" and record.setup is not None
    assert record.setup.route_kind == "local_service"
    assert record.setup.route_chosen_at == chosen.setup.route_chosen_at
    assert record.setup == chosen.setup


def test_a_slice_01_record_without_route_fields_parses_and_offers_a_choice():
    legacy = {key: value for key, value in _saved().model_dump().items()
              if key not in {"route_kind", "route_chosen_at"}}
    record = parse_setup(json.dumps(legacy))
    assert record.kind == "present" and record.setup is not None
    assert record.setup.route_kind == "" and record.setup.route_chosen_at == ""
    view = chooser_view(record.setup, now=NOW)
    assert view.state == STATE_AI_SERVICE_CHOOSE and view.selected_route is None


def test_request_edit_after_a_choice_keeps_the_route():
    saved = _saved()
    chosen = choose_route(saved, expected_revision=saved.revision, route_kind="opencode", now=NOW)
    edited = apply_request_edit(chosen.setup, expected_revision=chosen.setup.revision,
                                request_text="A refined request", now=LATER)
    assert edited.kind == "accepted" and edited.setup is not None
    assert (edited.setup.route_kind, edited.setup.route_chosen_at) == ("opencode", iso(NOW))
    assert edited.setup.step == "ai_service"


def test_requirements_mismatch_is_stale_and_blocks_choosing():
    saved = _saved()
    view = chooser_view(saved, now=NOW,
                        active_requirements_version=ONBOARDING_REQUIREMENTS_VERSION + 1)
    assert view.state == STATE_AI_SERVICE_STALE
    assert "requirements_version" in view.stale_reasons
    assert view.request_text == saved.request_text
    assert not view.can_choose
    result = choose_route(saved, expected_revision=saved.revision, route_kind="hosted_key", now=NOW,
                          requirements_version=ONBOARDING_REQUIREMENTS_VERSION + 1)
    assert result.kind == "stale" and result.setup == saved


def test_newer_contract_is_stale_not_unknown_and_blocks_choosing():
    future = _saved().model_copy(update={"contract_version": ONBOARDING_CONTRACT_VERSION + 1})
    view = chooser_view(future, now=NOW)
    assert view.state == STATE_AI_SERVICE_STALE and view.newer_version
    assert "newer_contract" in view.stale_reasons and not view.can_choose
    result = choose_route(future, expected_revision=future.revision, route_kind="hosted_key", now=NOW)
    assert result.kind == "stale"


def test_expired_record_is_stale_and_blocks_choosing():
    saved = _saved()
    expiry = datetime.fromisoformat(saved.resume_expires_at)
    view = chooser_view(saved, now=expiry)
    assert view.state == STATE_AI_SERVICE_STALE
    assert view.expired is True and STALE_EXPIRED in view.stale_reasons
    assert not view.can_choose
    result = choose_route(saved, expected_revision=saved.revision, route_kind="hosted_key", now=expiry)
    assert result.kind == "stale" and result.setup == saved


def test_removed_stored_route_is_stale_but_re_choosing_is_allowed():
    saved = _saved().model_copy(update={"route_kind": "retired_route"})
    view = chooser_view(saved, now=NOW)
    assert view.state == STATE_AI_SERVICE_STALE
    assert view.stale_reasons == (STALE_ROUTE_REMOVED,)
    assert view.can_choose and view.selected_route is None and view.selected_label == ""
    result = choose_route(saved, expected_revision=saved.revision, route_kind="opencode", now=NOW)
    assert result.kind == "chosen" and result.setup is not None
    assert result.setup.route_kind == "opencode"


def test_chooser_states_are_machine_assertable_tokens():
    tokens = {STATE_AI_SERVICE_CHOOSE, STATE_AI_SERVICE_CHOSEN,
              STATE_AI_SERVICE_STALE, STATE_AI_SERVICE_NO_REQUEST}
    assert tokens == {
        "setup.ai_service.choose", "setup.ai_service.chosen",
        "setup.ai_service.stale", "setup.ai_service.no_request",
    }
    assert onboarding_choices.STATE_AI_SERVICE_INVALID == "setup.ai_service.invalid"
    assert onboarding_choices.STATE_AI_SERVICE_CONFLICT == "setup.ai_service.conflict"


def test_store_save_route_persists_once_and_replays(store):
    saved = save_request(store, expected_revision=0, request_text="A stored request", now=NOW)
    assert saved.kind == "accepted"
    chosen = save_route(store, expected_revision=saved.setup.revision,
                        route_kind="hosted_key", now=LATER)
    assert chosen.kind == "chosen" and chosen.setup is not None
    loaded = load_setup(store)
    assert loaded.kind == "present" and loaded.setup == chosen.setup
    replay = save_route(store, expected_revision=saved.setup.revision,
                        route_kind="hosted_key", now=NOW)
    assert replay.kind == "replayed"
    assert load_setup(store).setup == chosen.setup


def test_store_save_route_does_not_overwrite_damaged_or_newer_records(store):
    store.kv_set(SETUP_KEY, "{not-json")
    assert save_route(store, expected_revision=0, route_kind="opencode", now=NOW).kind == "damaged"
    assert store.kv_get(SETUP_KEY) == "{not-json"
    future = _raw(contract_version=ONBOARDING_CONTRACT_VERSION + 1,
                  request_text="From newer", revision=4)
    store.kv_set(SETUP_KEY, future)
    result = save_route(store, expected_revision=4, route_kind="opencode", now=NOW)
    assert result.kind == "newer_version"
    assert store.kv_get(SETUP_KEY) == future


def test_store_save_route_without_a_request_writes_nothing(store):
    result = save_route(store, expected_revision=0, route_kind="opencode", now=NOW)
    assert result.kind == "no_request"
    assert store.kv_get(SETUP_KEY) is None


def test_pure_chooser_module_has_no_io_imports():
    source = Path(onboarding_choices.__file__).read_text(encoding="utf-8")
    for forbidden in ("fastapi", "hutch.server", "hutch.onboarding_store", "sqlite3", "urllib", "requests"):
        assert forbidden not in source
