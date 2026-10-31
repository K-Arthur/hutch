"""Durable commitments: provenance, confirmation, evidence and audit history."""

from __future__ import annotations

import sqlite3

import pytest

from hutch.personal import Commitment, CompletionKind
from hutch.personal.models import CommitmentPriority, CommitmentStatus
from hutch.personal.store import PersonalStore
from hutch.personal_schema import migrate


@pytest.fixture()
def personal(store):
    return PersonalStore(store)


def _commitment(**overrides) -> Commitment:
    data = {"title": "Pay the water bill", "detail": "before the 5th",
            "due_at": "2026-11-05T17:00:00-08:00", "due_timezone": "America/Vancouver",
            "category": "bills", "priority": CommitmentPriority.high}
    data.update(overrides)
    return Commitment(**data)


def test_owner_commitment_round_trip_and_audit(personal):
    saved, created = personal.commitments.create(_commitment(), actor="owner")
    assert created and saved.status is CommitmentStatus.open
    assert saved.due_at == "2026-11-06T01:00:00+00:00"
    assert saved.title == "Pay the water bill"

    fetched = personal.commitments.get(saved.id)
    assert fetched is not None and fetched.revision == 1

    updated = personal.commitments.update(
        saved.id, {"title": "Pay the water bill online", "priority": "normal"}, expected_revision=1)
    assert updated.revision == 2 and updated.priority is CommitmentPriority.normal

    with pytest.raises(Exception):
        personal.commitments.update(saved.id, {"title": "stale write"}, expected_revision=1)

    done = personal.commitments.complete(saved.id, evidence="Confirmation 8821",
                                         kind=CompletionKind.owner_confirmed, actor="owner")
    assert done.status is CommitmentStatus.done and done.completed_at
    reopened = personal.commitments.reopen(saved.id)
    assert reopened.status is CommitmentStatus.open and not reopened.completed_at
    kinds = [event["kind"] for event in personal.commitments.events(saved.id)]
    assert kinds == ["reopened", "completed", "updated", "created"]


def test_assistant_capture_is_proposed_until_the_owner_confirms(personal):
    proposed, _ = personal.commitments.create(_commitment(
        title="Book the dentist", created_by="assistant", confirmation="proposed", source="assistant",
        source_detail="capture_commitment", run_id="run_proposed"))
    assert proposed.confirmation == "proposed"

    with pytest.raises(ValueError):
        personal.commitments.complete(proposed.id, evidence="called", kind=CompletionKind.unverified,
                                      actor="assistant")

    confirmed = personal.commitments.confirm(proposed.id)
    assert confirmed.confirmation == "confirmed" and confirmed.created_by == "assistant"
    reported = personal.commitments.complete(proposed.id, evidence="Called the clinic on Tuesday",
                                             kind=CompletionKind.unverified, actor="assistant")
    assert reported.completion_kind is CompletionKind.unverified
    verified = personal.commitments.verify_completion(proposed.id)
    assert verified.completion_kind is CompletionKind.owner_confirmed and verified.completed_by == "owner"


def test_completion_requires_evidence(personal):
    saved, _ = personal.commitments.create(_commitment())
    with pytest.raises(ValueError):
        personal.commitments.complete(saved.id, evidence="  ", kind=CompletionKind.owner_confirmed, actor="owner")
    with pytest.raises(ValueError):
        Commitment(title="x", status=CommitmentStatus.done, completed_at="2026-10-31T00:00:00+00:00",
                   completion_evidence="", completion_kind=CompletionKind.owner_confirmed)


def test_dependencies_block_and_reject_cycles(personal):
    first, _ = personal.commitments.create(_commitment(title="Get the keys"))
    second, _ = personal.commitments.create(_commitment(title="Move the furniture"))
    personal.commitments.set_dependencies(second.id, [first.id])
    assert personal.commitments.blocked_map([second.id]) == {second.id: True}
    personal.commitments.complete(first.id, evidence="Keys collected", kind=CompletionKind.owner_confirmed,
                                  actor="owner")
    assert personal.commitments.blocked_map([second.id]) == {second.id: False}
    with pytest.raises(ValueError):
        personal.commitments.set_dependencies(first.id, [second.id])
    with pytest.raises(ValueError):
        personal.commitments.set_dependencies(second.id, [second.id])


def test_cancelled_is_terminal_and_timezones_fail_closed(personal):
    saved, _ = personal.commitments.create(_commitment())
    personal.commitments.cancel(saved.id)
    with pytest.raises(ValueError):
        personal.commitments.reopen(saved.id)
    with pytest.raises(ValueError):
        _commitment(due_timezone="Mars/Olympus")
    with pytest.raises(ValueError):
        _commitment(due_at="2026-11-05T17:00:00")  # naive local times are not accepted


def test_create_is_idempotent_for_the_same_command(personal):
    first, created = personal.commitments.create(_commitment(), idem_key="cmd-1", request_hash="abc")
    replay, again = personal.commitments.create(_commitment(), idem_key="cmd-1", request_hash="abc")
    assert created is True and again is False and replay.id == first.id
    with pytest.raises(Exception):
        personal.commitments.create(_commitment(), idem_key="cmd-1", request_hash="different")


def test_migration_is_additive_and_repeatable():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY)")
    try:
        migrate(db)
        migrate(db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"spaces", "space_members", "bot_space_grants", "commitments",
                "commitment_dependencies", "commitment_events"} <= tables
        db.execute("INSERT INTO bots VALUES ('bot-a')")
        # An audit trail cannot be rewritten even by direct SQL.
        db.execute("INSERT INTO commitments (id, title, created_at, updated_at) "
                   "VALUES ('cmt-a', 'x', 'now', 'now')")
        db.execute("INSERT INTO commitment_events (commitment_id, revision, kind, actor, detail_json, created_at) "
                   "VALUES ('cmt-a', 1, 'created', 'owner', '{}', 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE commitment_events SET kind = 'rewritten'")
    finally:
        db.close()


def test_commitments_spaces_and_a_schedule_survive_a_store_restart(config):
    """Reopen the same state directory: committed rows, grants and schedule timing persist."""
    from datetime import timedelta

    from hutch.models import Bot, Schedule, TriggerKind, iso, utcnow
    from hutch.scheduler import Scheduler
    from hutch.personal import Space, SpaceMember, SpaceRole
    from hutch.store import Store

    now = utcnow()
    first = Store(config)
    try:
        personal = PersonalStore(first)
        bot = first.create_bot(Bot(name="restart-bot", tools=["commitments"]))
        space = personal.spaces.create(Space(name="Restart household"))
        personal.spaces.add_member(space.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
        personal.spaces.grant(space.id, bot.id)
        saved, _ = personal.commitments.create(_commitment(title="Restart task", space_id=space.id), actor="owner")
        schedule = Schedule(name="Restart check", trigger=TriggerKind.interval, interval_seconds=3600,
                            timezone="America/Vancouver", anchor_at=iso(now - timedelta(minutes=10)),
                            prompt="check the shared list")
        bot = first.upsert_bot(bot, primary_schedule_update=schedule)
        next_before = Scheduler(first).next_fire(bot, now, bot.schedules[0])
        assert next_before is not None
    finally:
        first.close()

    second = Store(config)
    try:
        personal = PersonalStore(second)
        restored = personal.commitments.get(saved.id)
        assert restored is not None and restored.title == "Restart task" and restored.space_id == space.id
        assert personal.spaces.bot_space_ids(bot.id) == {space.id}
        assert [member.display_name for member in personal.spaces.members(space.id)] == ["Kevin"]
        reopened = second.get_bot("restart-bot")
        next_after = Scheduler(second).next_fire(reopened, now, reopened.schedules[0])
        assert next_after == next_before
        assert reopened.schedules[0].name == "Restart check"
    finally:
        second.close()
