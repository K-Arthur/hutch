"""State-level tests for the onboarding setup record and its kv adapter.

Decisions only: no HTTP and no page rendering. Clocks are fixed at
2026-10-29T18:00:00+00:00 so TTL and expiry boundaries are deterministic.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import hutch.onboarding as onboarding
from hutch.models import iso
from hutch.onboarding import (
    ONBOARDING_CONTRACT_VERSION,
    ONBOARDING_REQUIREMENTS_VERSION,
    REQUEST_MAX_CHARS,
    REQUIRED_STEPS,
    RESUME_TTL,
    STEP_ORDER,
    STATE_EMPTY_NO_ROUTE,
    STATE_RESUME_CURRENT,
    STATE_RESUME_EXPIRED,
    STATE_RESUME_STALE,
    apply_request_edit,
    default_setup,
    empty_view,
    encode_setup,
    parse_setup,
    resume_view,
)
from hutch.onboarding_store import SETUP_KEY, load_setup, reset_setup, save_request
from hutch.store import Store

NOW = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)

# Emoji is legitimate user data here, but this source file must stay free of
# pictographs (repo emoji rule), so the character is built from its code point.
EMOJI_REQUEST = f"Plan the launch {chr(0x1F680)} for next week"

NON_LATIN_REQUESTS = (
    "Rédiger mon CV et ma lettre de motivation",
    "日本語の依頼を作成する",
    "עזור לי לכתוב בקשה בעברית",
    "اختبار طلب باللغة العربية",
    "W" * 60,
)


def _saved(text: str = "A request", *, now: datetime = NOW):
    """Accepted save of a fresh record, used as the base for edit tests."""
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    return result.setup


def _raw(**overrides) -> str:
    """Stored JSON for a default record with the given field overrides."""
    return json.dumps(default_setup(NOW).model_dump() | overrides)


def test_default_setup_is_revision_zero_with_utc_timestamps_and_ttl():
    setup = default_setup(NOW)
    assert setup.revision == 0
    assert setup.step == STEP_ORDER[0]
    assert setup.request_text == ""
    assert setup.contract_version == ONBOARDING_CONTRACT_VERSION
    assert setup.requirements_version == ONBOARDING_REQUIREMENTS_VERSION
    assert setup.created_at == setup.updated_at == "2026-10-29T18:00:00+00:00"
    assert setup.resume_expires_at == "2026-11-28T18:00:00+00:00"
    assert datetime.fromisoformat(setup.created_at).utcoffset() == timedelta(0)
    span = datetime.fromisoformat(setup.resume_expires_at) - datetime.fromisoformat(setup.created_at)
    assert span == RESUME_TTL


def test_accepted_save_strips_outer_whitespace_only_and_refreshes_timestamps():
    base = default_setup(NOW)
    result = apply_request_edit(base, expected_revision=0,
                                request_text="  line one\nline two  ", now=LATER)
    assert result.kind == "accepted" and result.setup is not None
    saved = result.setup
    assert saved.request_text == "line one\nline two"
    assert saved.revision == 1
    assert saved.created_at == base.created_at
    assert saved.updated_at == iso(LATER)
    assert saved.resume_expires_at == iso(LATER + RESUME_TTL)


def test_request_length_boundary_is_inclusive_of_the_cap():
    accepted = apply_request_edit(default_setup(NOW), expected_revision=0,
                                  request_text="x" * REQUEST_MAX_CHARS, now=NOW)
    assert accepted.kind == "accepted" and accepted.setup is not None
    assert len(accepted.setup.request_text) == REQUEST_MAX_CHARS
    rejected = apply_request_edit(default_setup(NOW), expected_revision=0,
                                  request_text="x" * (REQUEST_MAX_CHARS + 1), now=NOW)
    assert rejected.kind == "invalid" and "20,000" in rejected.reason


@pytest.mark.parametrize("text", ["", "   ", "\n\t \r\n", "\u00a0"])
def test_empty_or_whitespace_request_is_invalid(text):
    result = apply_request_edit(default_setup(NOW), expected_revision=0, request_text=text, now=NOW)
    assert result.kind == "invalid"
    assert "request" in result.reason.lower()


def test_negative_expected_revision_is_invalid():
    result = apply_request_edit(default_setup(NOW), expected_revision=-1,
                                request_text="A request", now=NOW)
    assert result.kind == "invalid" and result.reason
    assert result.setup is not None and result.setup.revision == 0


def test_identical_resubmit_on_current_record_is_replayed():
    saved = _saved("Keep exactly this")
    result = apply_request_edit(saved, expected_revision=saved.revision,
                                request_text="  Keep exactly this  ", now=LATER)
    assert result.kind == "replayed" and result.setup == saved


def test_stale_revision_with_different_text_is_conflict_carrying_current_record():
    saved = _saved("Saved first")
    result = apply_request_edit(saved, expected_revision=0, request_text="Other text", now=LATER)
    assert result.kind == "stale" and result.setup == saved and result.reason


def test_identical_text_after_requirements_or_contract_bump_is_accepted_recovery():
    saved = _saved("Keep exactly this")
    result = apply_request_edit(saved, expected_revision=saved.revision,
                                request_text="Keep exactly this", now=LATER,
                                requirements_version=ONBOARDING_REQUIREMENTS_VERSION + 1,
                                contract_version=ONBOARDING_CONTRACT_VERSION + 1)
    assert result.kind == "accepted" and result.setup is not None
    refreshed = result.setup
    assert refreshed.revision == saved.revision + 1
    assert refreshed.requirements_version == ONBOARDING_REQUIREMENTS_VERSION + 1
    assert refreshed.contract_version == ONBOARDING_CONTRACT_VERSION + 1
    assert refreshed.updated_at == iso(LATER)
    assert refreshed.resume_expires_at == iso(LATER + RESUME_TTL)


def test_identical_text_after_expiry_is_accepted_recovery():
    saved = _saved("Keep exactly this")
    expiry = datetime.fromisoformat(saved.resume_expires_at)
    result = apply_request_edit(saved, expected_revision=saved.revision,
                                request_text="Keep exactly this", now=expiry)
    assert result.kind == "accepted" and result.setup is not None
    assert result.setup.revision == saved.revision + 1
    assert result.setup.resume_expires_at == iso(expiry + RESUME_TTL)


@pytest.mark.parametrize("text", NON_LATIN_REQUESTS + (EMOJI_REQUEST,))
def test_request_text_round_trips_exactly_through_encoding(text):
    saved = _saved(text)
    assert saved.request_text == text
    record = parse_setup(encode_setup(saved))
    assert record.kind == "present" and record.setup is not None
    assert record.setup.request_text == text
    replay = apply_request_edit(saved, expected_revision=saved.revision,
                                request_text=text, now=LATER)
    assert replay.kind == "replayed"


def test_encode_setup_is_compact_sorted_json_and_round_trips():
    saved = _saved("A request")
    raw = encode_setup(saved)
    assert raw == json.dumps(saved.model_dump(), sort_keys=True, separators=(",", ":"))
    assert parse_setup(raw).setup == saved


def test_resume_view_current_record():
    saved = _saved("Help me plan a trip")
    view = resume_view(saved, now=LATER)
    assert view.state == STATE_RESUME_CURRENT
    assert (view.step, view.step_index, view.required_total) == ("request", 1, len(REQUIRED_STEPS))
    assert view.request_text == "Help me plan a trip"
    assert (view.revision, view.saved_at) == (saved.revision, saved.updated_at)
    assert view.resume_expires_at == saved.resume_expires_at
    assert not (view.stale or view.expired or view.newer_version)
    assert view.stale_reasons == ()


def test_resume_view_blank_current_record_is_empty_state():
    view = resume_view(default_setup(NOW), now=NOW)
    blank = empty_view()
    assert view.state == blank.state == STATE_EMPTY_NO_ROUTE
    assert view.request_text == "" and view.revision == 0 and view.saved_at == iso(NOW)
    assert blank.step == STEP_ORDER[0] and blank.step_index == 1
    assert (view.required_total, blank.required_total) == (len(REQUIRED_STEPS), len(REQUIRED_STEPS))
    assert not view.stale and not view.expired and blank.stale_reasons == ()


def test_resume_view_expiry_boundary_and_stale_precedence():
    saved = _saved("A request")
    deadline = datetime.fromisoformat(saved.resume_expires_at)
    assert resume_view(saved, now=deadline - timedelta(seconds=1)).state == STATE_RESUME_CURRENT
    expired = resume_view(saved, now=deadline)
    assert expired.state == STATE_RESUME_EXPIRED and expired.expired
    assert expired.request_text == "A request"
    stale_expired = resume_view(saved.model_copy(update={"requirements_version": 2}), now=deadline)
    assert stale_expired.state == STATE_RESUME_STALE and stale_expired.expired


def test_resume_view_older_contract_is_stale_not_newer():
    view = resume_view(_saved("A request"), now=NOW,
                       active_contract_version=ONBOARDING_CONTRACT_VERSION + 1)
    assert view.state == STATE_RESUME_STALE
    assert view.stale_reasons == ("contract_version",)
    assert view.newer_version is False and not view.expired


def test_resume_view_requirements_mismatch_is_stale():
    view = resume_view(_saved("A request"), now=NOW,
                       active_requirements_version=ONBOARDING_REQUIREMENTS_VERSION + 1)
    assert view.state == STATE_RESUME_STALE
    assert view.stale_reasons == ("requirements_version",)
    assert not view.expired and not view.newer_version


def test_resume_view_unknown_step_is_stale_with_clamped_index():
    saved = _saved("A request").model_copy(update={"step": "retired_step"})
    view = resume_view(saved, now=NOW)
    assert view.state == STATE_RESUME_STALE
    assert view.stale_reasons == ("unknown_step",)
    assert view.step == "retired_step" and view.step_index == 1


def test_parse_setup_absent_and_damaged_inputs():
    assert parse_setup(None).kind == "absent"
    damaged = ("{broken", "", "[]", "null", json.dumps({"contract_version": 1}),
               _raw(revision=-1), _raw(created_at="2026-10-29T18:00:00"),
               _raw(updated_at="not-a-timestamp"))
    assert [parse_setup(raw).kind for raw in damaged] == ["damaged"] * len(damaged)


def test_parse_setup_accepts_newer_contract_and_ignores_extra_fields():
    record = parse_setup(_raw(contract_version=ONBOARDING_CONTRACT_VERSION + 1,
                              request_text="Kept request", future_field={"nested": True}))
    assert record.kind == "present" and record.setup is not None
    pending = record.setup
    assert pending.contract_version == ONBOARDING_CONTRACT_VERSION + 1
    assert "future_field" not in pending.model_dump()
    view = resume_view(pending, now=NOW)
    assert view.state == STATE_RESUME_STALE
    assert view.stale_reasons == ("newer_contract",)
    assert view.newer_version is True and view.request_text == "Kept request"


def test_store_round_trip_saves_and_loads_the_record(store):
    result = save_request(store, expected_revision=0,
                          request_text="  Stored on this machine  ", now=NOW)
    assert result.kind == "accepted" and result.setup is not None
    assert (result.setup.revision, result.setup.request_text) == (1, "Stored on this machine")
    assert store.kv_get(SETUP_KEY) == encode_setup(result.setup)
    loaded = load_setup(store)
    assert loaded.kind == "present" and loaded.setup == result.setup
    replay = save_request(store, expected_revision=1,
                          request_text="Stored on this machine", now=LATER)
    assert replay.kind == "replayed" and replay.setup == result.setup


def test_verified_save_survives_store_close_and_reopen(config):
    first = Store(config)
    try:
        saved = save_request(first, expected_revision=0, request_text="Keep this", now=NOW)
        assert saved.kind == "accepted"
    finally:
        first.close()
    reopened = Store(config)
    try:
        loaded = load_setup(reopened)
        assert loaded.kind == "present" and loaded.setup is not None
        assert (loaded.setup.revision, loaded.setup.request_text) == (1, "Keep this")
        second = save_request(reopened, expected_revision=1, request_text="Updated", now=LATER)
        assert second.kind == "accepted" and second.setup is not None
        assert second.setup.revision == 2
    finally:
        reopened.close()


def test_damaged_raw_value_is_reported_and_never_overwritten(store):
    store.kv_set(SETUP_KEY, "{not-json")
    assert load_setup(store).kind == "damaged"
    result = save_request(store, expected_revision=0, request_text="A request", now=NOW)
    assert result.kind == "damaged" and result.setup is None
    assert store.kv_get(SETUP_KEY) == "{not-json"


def test_newer_contract_record_is_not_overwritten_by_save(store):
    raw = _raw(contract_version=ONBOARDING_CONTRACT_VERSION + 1,
               request_text="From newer", revision=4)
    store.kv_set(SETUP_KEY, raw)
    result = save_request(store, expected_revision=0, request_text="A request", now=NOW)
    assert result.kind == "newer_version" and result.setup is not None
    assert result.setup.contract_version == ONBOARDING_CONTRACT_VERSION + 1
    assert store.kv_get(SETUP_KEY) == raw


def test_reset_setup_writes_fresh_revision_zero_record(store):
    assert save_request(store, expected_revision=0,
                        request_text="Old request", now=NOW).kind == "accepted"
    reset = reset_setup(store, LATER)
    assert (reset.revision, reset.request_text, reset.created_at) == (0, "", iso(LATER))
    loaded = load_setup(store)
    assert loaded.kind == "present" and loaded.setup == reset


def test_concurrent_saves_on_the_same_revision_keep_one_writer(store):
    barrier = threading.Barrier(2)
    results = [None, None]

    def attempt(index: int, text: str) -> None:
        barrier.wait(timeout=5)
        results[index] = save_request(store, expected_revision=0, request_text=text, now=NOW)

    threads = [threading.Thread(target=attempt, args=(index, text))
               for index, text in enumerate(("first text", "second text"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(result is not None for result in results)
    assert sorted(result.kind for result in results) == ["accepted", "stale"]
    accepted = next(result for result in results if result.kind == "accepted")
    loaded = load_setup(store)
    assert loaded.kind == "present" and loaded.setup is not None
    assert loaded.setup.revision == 1
    assert loaded.setup.request_text == accepted.setup.request_text


def test_pure_domain_module_has_no_server_or_fastapi_imports():
    source = Path(onboarding.__file__).read_text(encoding="utf-8")
    assert "fastapi" not in source
    assert "hutch.server" not in source
