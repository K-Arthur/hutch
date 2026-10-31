"""Notifications: created with the fact, delivered once through the channel outbox.

The triggers are exercised on a real store; delivery is exercised through the real
ChannelService with a fake transport, so duplicate suppression, the uncertain state
and the recovery-by-evidence path are observed where they actually run.
"""

from __future__ import annotations

import hashlib

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.channels.persistence import ChannelBook
from hutch.channels.service import ChannelService
from hutch.channels.telegram import TelegramFailure
from hutch.models import (ApprovalMode, ApprovalRequest, ApprovalStatus, Bot, Run, RunStatus, iso,
                          utcnow)
from hutch.server.app import create_app

TOKEN = "123456789:" + "synthetic-not-a-real-token-value"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.store = c.app.state.store
        yield c


def start_run(store, bot, *, origin="manual:dashboard", status=RunStatus.running) -> Run:
    run = Run(bot_id=bot.id, prompt="Send the signed contract", status=status, origin=origin,
              started_at=iso(utcnow()))
    store.create_run(run)
    return run


def pending_approval(store, bot, run) -> ApprovalRequest:
    return store.create_approval(ApprovalRequest(
        run_id=run.id, bot_id=bot.id, tool="outlook_send", action="Send the signed contract",
        risk="high", outward=True))


def notifications(store) -> list[dict]:
    with store._lock:
        return [dict(row) for row in store._db.execute(
            "SELECT * FROM notifications ORDER BY rowid")]


def channel(store, bot):
    book = ChannelBook(store)
    row = book.create(name="Personal Telegram", bot_id=bot.id, allowed_senders=["123", "456"],
                      credential_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
                      remote_bot_id="123456789")
    return book, row


class Secrets:
    def get(self, _ref):
        return TOKEN


class Transport:
    def __init__(self, sent, failure=None):
        self.sent = sent
        self.failure = failure

    def send(self, sender, text):
        self.sent.append((sender, text))
        if self.failure is not None:
            raise self.failure
        return f"msg-{len(self.sent)}"

    def updates(self, _cursor):
        return []


def cycle(service, store, channel_id):
    with store._tx() as db:
        db.execute("UPDATE channel_connections SET next_poll_at='',lease_owner='',lease_until='' "
                   "WHERE id=?", (channel_id,))
    service.once()


def test_an_approval_creates_one_content_free_notification(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    approval = pending_approval(store, bot, run)
    rows = notifications(store)
    assert [(row["kind"], row["subject_id"]) for row in rows] == [("approval_needs_you", approval.id)]
    assert rows[0]["detail"] == "" and rows[0]["bot_id"] == bot.id
    assert "Send the signed contract" not in str(rows[0])
    _, outcome = store.decide_approval(approval.id, ApprovalStatus.denied, "fixture-owner")
    assert outcome == "won"
    kinds = [row["kind"] for row in notifications(store)]
    assert kinds == ["approval_needs_you", "approval_denied"]
    assert "fixture-owner" == notifications(store)[1]["detail"]
    # A second decision cannot repeat itself.
    store.decide_approval(approval.id, ApprovalStatus.approved, "fixture-owner")
    assert len(notifications(store)) == 2
    # The unique subject guard refuses a duplicate row even if a trigger re-fired.
    with store._lock:
        store._db.execute("INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, "
                          "subject_id, detail, created_at) VALUES ('ntf_dup','approval_needs_you',?,"
                          "'approval',?,'',?)", (bot.id, approval.id, iso(utcnow())))
    assert len(notifications(store)) == 2


def test_run_outcomes_notify_failures_and_unattended_results_only(store):
    bot = store.create_bot(Bot(name="runner", approval_mode=ApprovalMode.ask))
    manual = start_run(store, bot)
    store.transition_run(manual.id, RunStatus.failed, exit_reason="model_unavailable")
    scheduled = start_run(store, bot, origin="schedule")
    store.transition_run(scheduled.id, RunStatus.succeeded)
    ignored = start_run(store, bot, origin="manual:dashboard")
    store.transition_run(ignored.id, RunStatus.succeeded)
    rows = notifications(store)
    assert [(row["kind"], row["subject_id"]) for row in rows] == [
        ("run_failed", manual.id), ("run_succeeded", scheduled.id)]
    assert rows[0]["detail"] == "model_unavailable"
    assert "Send the signed contract" not in str(rows)


def test_a_pending_approval_delivers_once_through_the_supervisor(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    pending_approval(store, bot, run)
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert len(sent) == 1 and sent[0][0] == "123"
    assert "waiting for your decision" in sent[0][1]
    assert "Send the signed contract" not in sent[0][1]
    deliveries = book.deliveries(row["id"])
    assert len(deliveries) == 1 and deliveries[0]["state"] == "sent"
    assert deliveries[0]["notification_kind"] == "approval_needs_you"
    cycle(service, store, row["id"])
    assert len(sent) == 1


def test_an_uncertain_send_is_never_retried_without_reconciliation(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    pending_approval(store, bot, run)
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(),
                             transport=lambda _secret: Transport(sent, TelegramFailure(uncertain=True)))
    cycle(service, store, row["id"])
    delivery = book.deliveries(row["id"])[0]
    assert delivery["state"] == "uncertain" and delivery["attempts"] == 1
    cycle(service, store, row["id"])
    assert len(sent) == 1, "an unconfirmed send must not be repeated"
    with pytest.raises(Exception):
        book.reconcile(row["id"], delivery["id"], attempts=1, delivered=False, evidence="guess")
    assert book.reconcile(row["id"], delivery["id"], attempts=1, delivered=False,
                          evidence="Checked Telegram history; no message was delivered.") == "pending"
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert len(sent) == 2
    assert book.deliveries(row["id"])[0]["state"] == "sent"


def test_a_decided_approval_is_not_delivered_late(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    approval = pending_approval(store, bot, run)
    store.decide_approval(approval.id, ApprovalStatus.approved, "fixture-owner")
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert sent == []
    assert book.deliveries(row["id"]) == []


def test_a_disabled_channel_queues_nothing_and_starting_it_delivers_once(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    pending_approval(store, bot, run)
    book, row = channel(store, bot)
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert sent == [] and book.deliveries(row["id"]) == []
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    cycle(service, store, row["id"])
    assert len(sent) == 1


def test_a_reply_and_an_alert_share_one_cycle_without_swallowing_each_other(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    pending_approval(store, bot, run)
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    # A finished inbound conversation reply is pending alongside the alert.
    with store._tx() as db:
        db.execute("INSERT INTO channel_events(channel_id,revision,external_id,sender,text,content_hash,"
                   "received_at,run_id,state) VALUES (?,?,?,?,?,?,?,?,'admitted')",
                   (row["id"], row["revision"], "ext-1", "123", "hello", "h" * 64,
                    iso(utcnow()), run.id))
    with store._tx() as db:
        db.execute("UPDATE runs SET status='succeeded' WHERE id=?", (run.id,))
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert len(sent) == 2
    kinds = [delivery["notification_kind"] for delivery in book.deliveries(row["id"])]
    assert sorted(kinds) == ["", "approval_needs_you"]
    assert all(delivery["state"] == "sent" for delivery in book.deliveries(row["id"]))


def test_an_alert_older_than_the_recency_window_is_not_delivered(store, monkeypatch):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    pending_approval(store, bot, run)
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    later = utcnow() + timedelta(days=2)
    monkeypatch.setattr("hutch.channels.outbox.utcnow", lambda: later)
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert sent == [] and book.deliveries(row["id"]) == []


def test_the_outbox_rebuild_preserves_reply_deliveries_and_refuses_orphans(tmp_path):
    """A v85-shaped database upgrades without losing a reply delivery; an orphan blocks it."""
    import sqlite3

    from hutch import notification_schema

    db = sqlite3.connect(tmp_path / "v85.db")
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE channel_connections (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE channel_events (id INTEGER PRIMARY KEY, channel_id TEXT, revision INTEGER)")
        db.execute("CREATE TABLE approvals (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("""CREATE TABLE channel_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE REFERENCES channel_events(id),
            text TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL, provider_message_id TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', reconciled_at TEXT NOT NULL DEFAULT '',
            reconciliation TEXT NOT NULL DEFAULT '')""")
        db.execute("INSERT INTO channel_connections(id) VALUES ('ch_1')")
        db.execute("INSERT INTO channel_events(id,channel_id,revision) VALUES (7,'ch_1',3)")
        db.execute("INSERT INTO channel_deliveries(event_id,text,state,attempts,next_attempt_at) "
                   "VALUES (7,'a reply','sent',2,'2026-10-31T00:00:00+00:00')")
        notification_schema.migrate(db)
        row = db.execute("SELECT * FROM channel_deliveries").fetchone()
        assert (row["event_id"], row["notification_id"], row["channel_id"]) == (7, None, "ch_1")
        assert (row["text"], row["state"], row["attempts"]) == ("a reply", "sent", 2)
        assert "notifications" in {item[0] for item in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        # A second run is a no-op once the new shape is present.
        notification_schema.migrate(db)
        assert db.execute("SELECT COUNT(*) FROM channel_deliveries").fetchone()[0] == 1
    finally:
        db.close()


def test_the_outbox_rebuild_refuses_a_delivery_with_no_inbound_event(tmp_path):
    import sqlite3

    from hutch import notification_schema

    db = sqlite3.connect(tmp_path / "bad.db")
    try:
        db.execute("CREATE TABLE channel_connections (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE channel_events (id INTEGER PRIMARY KEY, channel_id TEXT, revision INTEGER)")
        db.execute("CREATE TABLE approvals (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("""CREATE TABLE channel_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE, text TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL, provider_message_id TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', reconciled_at TEXT NOT NULL DEFAULT '',
            reconciliation TEXT NOT NULL DEFAULT '')""")
        db.execute("INSERT INTO channel_deliveries(event_id,text,next_attempt_at) VALUES (99,'orphan','x')")
        with pytest.raises(RuntimeError, match="preserve the database"):
            notification_schema.migrate(db)
        assert db.execute("SELECT name FROM sqlite_master WHERE name='channel_deliveries_v86'").fetchone() is None
    finally:
        db.close()


def test_an_alert_goes_to_the_person_who_started_the_work_when_they_are_allowed(store):
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    book, row = channel(store, bot)
    row, _ = book.set_enabled(row["id"], True, row["revision"])
    with store._tx() as db:
        db.execute("INSERT INTO channel_events(channel_id,revision,external_id,sender,text,content_hash,"
                   "received_at,run_id,state) VALUES (?,?,?,?,?,?,?,?,'admitted')",
                   (row["id"], row["revision"], "ext-9", "456", "hello", "h" * 64,
                    iso(utcnow()), run.id))
    pending_approval(store, bot, run)
    sent: list[tuple[str, str]] = []
    service = ChannelService(store, secrets=Secrets(), transport=lambda _secret: Transport(sent))
    cycle(service, store, row["id"])
    assert [recipient for recipient, _text in sent] == ["456"]


def test_a_malformed_document_skips_the_alert_instead_of_failing_the_fact(store):
    """A corrupt legacy doc must not turn a status write into an error at the trigger."""
    bot = store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(store, bot)
    with store._tx() as db:
        db.execute("UPDATE runs SET doc='not json' WHERE id=?", (run.id,))
        db.execute("UPDATE runs SET status='failed' WHERE id=?", (run.id,))
    assert store._db.execute("SELECT status FROM runs WHERE id=?", (run.id,)).fetchone()[0] == "failed"
    assert notifications(store) == []
    # A well-formed document still notifies: the guard skips only what it cannot read.
    other = start_run(store, bot)
    store.transition_run(other.id, RunStatus.failed, exit_reason="model_unavailable")
    assert [row["subject_id"] for row in notifications(store)] == [other.id]


def test_a_deleted_assistant_is_not_listed_on_either_surface(client):
    bot = client.store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(client.store, bot)
    pending_approval(client.store, bot, run)
    assert client.get("/api/v1/notifications").json()["items"]
    assert client.store.delete_bot(bot.id)
    assert client.get("/api/v1/notifications").json()["items"] == []
    today = client.get("/api/v1/today", params={"timezone": "America/Vancouver"}).json()
    assert today["sections"]["alerts"] == []
    with client.store._lock:
        assert client.store._db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 1


def test_both_surfaces_report_the_same_delivery_state(client):
    bot = client.store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(client.store, bot)
    pending_approval(client.store, bot, run)
    api_item = client.get("/api/v1/notifications").json()["items"][0]
    today = client.get("/api/v1/today", params={"timezone": "America/Vancouver"}).json()
    today_item = today["sections"]["alerts"][0]
    assert api_item["delivery"]["state"] == today_item["delivery"] == "not_queued"
    assert api_item["id"] == today_item["subject_id"] or api_item["subject_id"] == today_item["subject_id"]


def test_the_notification_api_lists_receipts_without_message_bodies(client):
    bot = client.store.create_bot(Bot(name="notify-me", approval_mode=ApprovalMode.ask))
    run = start_run(client.store, bot)
    approval = pending_approval(client.store, bot, run)
    response = client.get("/api/v1/notifications")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["approval_needs_you"] == 1
    item = body["items"][0]
    assert item["kind"] == "approval_needs_you" and item["subject_id"] == approval.id
    assert item["delivery"]["state"] == "not_queued"
    assert "Send the signed contract" not in response.text
    assert client.get("/api/v1/notifications", params={"kind": "nope"}).status_code == 422
