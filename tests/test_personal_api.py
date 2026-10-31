"""Owner-facing personal operations API: commitments, spaces, grants and Today."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.personal.store import PersonalStore
from hutch.personal.today import build_today
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.store = c.app.state.store
        yield c


def _key() -> dict[str, str]:
    import uuid
    return {"Idempotency-Key": uuid.uuid4().hex}


def test_commitment_crud_contract(client):
    created = client.post("/api/v1/commitments", headers=_key(), json={
        "title": "Renew the passport",
        "detail": "Book an appointment first",
        "due_at": "2026-11-20T09:00:00-08:00",
        "due_timezone": "America/Vancouver",
        "priority": "high",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["confirmation"] == "confirmed" and body["status"] == "open"
    assert body["due_at"] == "2026-11-20T17:00:00+00:00"

    page = client.get("/api/v1/commitments").json()
    assert [item["id"] for item in page["items"]] == [body["id"]]
    assert page["counts"]["open"] == 1

    patched = client.patch(f"/api/v1/commitments/{body['id']}", json={
        "expected_revision": body["revision"], "title": "Renew the passport now"})
    assert patched.status_code == 200 and patched.json()["revision"] == 2
    stale = client.patch(f"/api/v1/commitments/{body['id']}", json={
        "expected_revision": 1, "title": "Stale"})
    assert stale.status_code == 409

    done = client.post(f"/api/v1/commitments/{body['id']}/complete",
                       json={"evidence": "Appointment booked, reference 42"})
    assert done.status_code == 200
    assert done.json()["completion_kind"] == "owner_confirmed"

    events = client.get(f"/api/v1/commitments/{body['id']}/events").json()["items"]
    assert [item["kind"] for item in events] == ["completed", "updated", "created"]


def test_commitment_validation_and_provenance(client):
    missing = client.post("/api/v1/commitments", headers=_key(), json={"title": " "})
    assert missing.status_code == 422
    bad_zone = client.post("/api/v1/commitments", headers=_key(), json={
        "title": "Bad zone", "due_at": "2026-11-20T09:00:00+00:00", "due_timezone": "Mars/Olympus"})
    assert bad_zone.status_code == 422
    naive = client.post("/api/v1/commitments", headers=_key(), json={
        "title": "Naive", "due_at": "2026-11-20T09:00:00", "due_timezone": "UTC"})
    assert naive.status_code == 422 and "offset" in naive.text
    no_key = client.post("/api/v1/commitments", json={"title": "No key"})
    assert no_key.status_code == 428


def test_assistant_proposals_are_confirmed_by_the_owner(client):
    personal = PersonalStore(client.store)
    from hutch.personal import Commitment
    proposed, _ = personal.commitments.create(Commitment(
        title="Schedule the boiler service", created_by="assistant", confirmation="proposed",
        source="assistant", run_id="run_api"))
    replay = client.post("/api/v1/commitments", headers=_key(), json={"title": "Idempotent capture",
                                                                       "space_id": None})
    assert replay.status_code == 201
    confirmed = client.post(f"/api/v1/commitments/{proposed.id}/confirm", json={})
    assert confirmed.status_code == 200 and confirmed.json()["confirmation"] == "confirmed"


def test_spaces_and_grants_contract(client):
    bot = client.store.create_bot(Bot(name="family-assistant"))
    space = client.post("/api/v1/spaces", json={"name": "Household", "kind": "household"})
    assert space.status_code == 201, space.text
    space_id = space.json()["id"]
    joined = client.post(f"/api/v1/spaces/{space_id}/members",
                         json={"display_name": "Kevin", "role": "owner"})
    assert joined.status_code == 201
    assert joined.json()["active_members"] == 1
    granted = client.post(f"/api/v1/spaces/{space_id}/bots", json={"bot_id": bot.id})
    assert granted.status_code == 200 and bot.id in granted.json()["bot_grants"]

    shared = client.post("/api/v1/commitments", headers=_key(), json={
        "title": "Buy milk", "space_id": space_id, "category": "shopping"})
    assert shared.status_code == 201 and shared.json()["space_id"] == space_id
    filtered = client.get("/api/v1/commitments", params={"space": space_id}).json()
    assert [item["title"] for item in filtered["items"]] == ["Buy milk"]
    personal_only = client.get("/api/v1/commitments", params={"space": "personal"}).json()
    assert personal_only["items"] == []

    revoked = client.delete(f"/api/v1/spaces/{space_id}/bots/{bot.id}")
    assert revoked.status_code == 200 and revoked.json()["bot_grants"] == []
    archived = client.post(f"/api/v1/spaces/{space_id}/archive",
                           json={"expected_revision": space.json()["revision"]})
    assert archived.status_code == 200 and archived.json()["archived"] is True


def test_today_endpoint_reports_real_state_and_rejects_unknown_zones(client):
    from hutch.personal import Commitment
    PersonalStore(client.store).commitments.create(
        Commitment(title="Overdue invoice", due_at="2026-10-20T17:00:00+00:00"))
    response = client.get("/api/v1/today", params={"timezone": "America/Vancouver"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["timezone"] == "America/Vancouver"
    assert body["counts"]["overdue"] == 1
    assert body["sections"]["commitments"]["overdue"][0]["title"] == "Overdue invoice"
    assert "Calendar events and email are not read automatically" in " ".join(body["not_included"])
    assert client.get("/api/v1/today", params={"timezone": "Mars/Olympus"}).status_code == 422
    assert client.get("/api/v1/today").status_code == 422


def test_today_uses_local_day_boundaries_across_dst(store):
    from hutch.personal import Commitment
    personal = PersonalStore(store)
    # 2026-11-01 is the US fall-back day (25 hours long in America/Vancouver).
    personal.commitments.create(Commitment(title="Sunday morning", due_at="2026-11-01T16:00:00+00:00",
                                           due_timezone="America/Vancouver"))
    personal.commitments.create(Commitment(title="Monday morning", due_at="2026-11-02T16:00:00+00:00",
                                           due_timezone="America/Vancouver"))
    briefing = build_today(store, now=datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc),
                           timezone_name="America/Vancouver")
    due_today = [item["title"] for item in briefing["sections"]["commitments"]["due_today"]]
    assert due_today == ["Sunday morning"]
    assert briefing["local_date"] == "2026-11-01"
    # A local day is 23, 24 or 25 hours; the bounds are converted per boundary.
    span = datetime.fromisoformat(briefing["day_end"]) - datetime.fromisoformat(briefing["day_start"])
    assert span.total_seconds() in (23 * 3600, 24 * 3600, 25 * 3600)


def test_today_measures_a_real_dst_transition_day(store):
    """Find whatever transition the installed tz database defines and measure that day."""
    from datetime import date, time, timedelta
    from zoneinfo import ZoneInfo
    from hutch.personal import Commitment
    zone = ZoneInfo("America/Vancouver")
    cursor, transition = date(2026, 1, 1), None
    while cursor < date(2027, 1, 1):
        here = datetime.combine(cursor, time.min, tzinfo=zone).utcoffset()
        after = datetime.combine(cursor + timedelta(days=1), time.min, tzinfo=zone).utcoffset()
        if here != after:
            transition = cursor
            break
        cursor += timedelta(days=1)
    assert transition is not None, "the installed tz database has no 2026 transition"
    noon = datetime.combine(transition, time(12), tzinfo=zone).astimezone(timezone.utc)
    PersonalStore(store).commitments.create(
        Commitment(title="Transition day task", due_at=noon.isoformat(), due_timezone="America/Vancouver"))
    briefing = build_today(store, now=noon + timedelta(hours=1), timezone_name="America/Vancouver")
    assert [item["title"] for item in briefing["sections"]["commitments"]["due_today"]] == ["Transition day task"]
    span = datetime.fromisoformat(briefing["day_end"]) - datetime.fromisoformat(briefing["day_start"])
    assert span.total_seconds() in (23 * 3600, 24 * 3600, 25 * 3600)
