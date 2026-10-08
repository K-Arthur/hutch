"""Phase 2 gate (UI-3): ten concurrent runs stream, the connection is cut, and every transcript
resumes with no missing and no duplicated events.

Runs against a real uvicorn server over real sockets, so "cutting the connection" is an actual TCP close
and the server's cancellation / unsubscribe path is exercised, not simulated.
"""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest
import uvicorn

from hutch.models import ApprovalMode, Bot, Event, EventType
from hutch.server.app import create_app


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "10")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app
    server.should_exit = True
    t.join(timeout=10)


def parse_sse(lines, *, text_ids=False):
    """Yield (event, id, data) from an iterator of SSE lines."""
    ev, id_, data = "message", None, []
    for line in lines:
        if line == "":
            if data:
                yield ev, id_, "\n".join(data)
            ev, id_, data = "message", None, []
        elif line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("id:"):
            id_ = line[3:].strip() if text_ids else int(line[3:].strip())
        elif line.startswith("data:"):
            data.append(line[5:].strip())


def follow(base, run_id, cut_after=(12, 30), pause=0.25):
    """Stream a run, deliberately dropping the connection after N events, resuming via Last-Event-ID."""
    seqs: list[int] = []
    cuts = 0
    cursor = 0
    while True:
        headers = {"Last-Event-ID": str(cursor)} if cursor else {}
        finished = False
        with httpx.stream("GET", f"{base}/api/runs/{run_id}/stream", headers=headers, timeout=30) as r:
            assert r.status_code == 200
            for ev, id_, data in parse_sse(r.iter_lines()):
                if ev == "batch":
                    batch = json.loads(data)["events"]
                    seqs += [e["seq"] for e in batch]
                    cursor = batch[-1]["seq"]
                    assert id_ == cursor
                    if cuts < len(cut_after) and len(seqs) >= cut_after[cuts]:
                        cuts += 1
                        break                       # cut the connection mid-run
                elif ev == "end":
                    finished = True
                    break
        if finished:
            return seqs, cuts
        time.sleep(pause)                           # events keep flowing while we are disconnected


def test_ten_concurrent_runs_stream_cut_and_resume_with_no_missing_events(live, monkeypatch):
    base, app = live
    store, engine = app.state.store, app.state.engine
    import hutch.runtime.mock as mock_mod

    N = 80

    def chatty(self, run, ctx, tools, stop):
        for i in range(N):
            ctx.emit(Event(run_id=run.id, type=EventType.log, data={"note": f"event {i}"}))
            time.sleep(0.02)
        return "done"

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", chatty)
    bots = [store.create_bot(Bot(name=f"stream-{i}", model="mock/demo", approval_mode=ApprovalMode.auto))
            for i in range(10)]
    runs = [engine.submit(b, f"go {i}") for i, b in enumerate(bots)]
    engine.dispatch_pending()

    results: dict[str, tuple[list[int], int]] = {}
    errors: list[BaseException] = []

    def worker(run):
        try:
            results[run.id] = follow(base, run.id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(r,)) for r in runs]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert not errors, errors
    assert len(results) == 10

    for run in runs:
        seqs, cuts = results[run.id]
        full = httpx.get(f"{base}/api/runs/{run.id}/events?limit=1000").json()
        expected = [e["seq"] for e in full["events"]]
        assert cuts == 2, "the connection was supposed to be cut twice"
        assert seqs == expected, f"{run.id}: transcript differs after reconnects"
        assert seqs == list(range(1, len(seqs) + 1)), "gap or duplicate in the resumed stream"
        assert len(seqs) >= N                       # status + log + 80 events + final status


def test_last_event_id_wins_over_the_after_parameter(live, monkeypatch):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="cursor-bot"))
    from hutch.models import Run, RunStatus
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.succeeded))
    for i in range(10):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    store.flush_events()
    with httpx.stream("GET", f"{base}/api/runs/{run.id}/stream?after=0", headers={"Last-Event-ID": "6"},
                      timeout=10) as r:
        got = []
        for ev, id_, data in parse_sse(r.iter_lines()):
            if ev == "batch":
                got += [e["seq"] for e in json.loads(data)["events"]]
            if ev == "end":
                break
    assert got == [7, 8, 9, 10]


def test_global_event_pages_and_sse_replay_use_one_durable_cursor(live):
    base, app = live
    store = app.state.store
    from hutch.models import Run, RunStatus

    for n, count in ((1, 3), (2, 2)):
        bot = store.create_bot(Bot(name=f"global-{n}"))
        run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.succeeded))
        for i in range(count):
            store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    store.flush_events()

    first = httpx.get(f"{base}/api/v1/events?after=0&limit=2").json()
    assert len(first["events"]) == 2 and first["has_more"]
    cursor = first["next_after"]
    remaining = httpx.get(f"{base}/api/v1/events?after={cursor}&limit=20").json()
    first_ids = [event["id"] for event in first["events"]]
    later_ids = [event["id"] for event in remaining["events"]]
    assert first_ids == sorted(first_ids) and later_ids == sorted(later_ids)
    assert min(later_ids) > max(first_ids)
    assert len(set(first_ids + later_ids)) == len(first_ids) + len(later_ids)
    assert len({event["run_id"] for event in first["events"] + remaining["events"]}) == 2

    first_batch = None
    with httpx.stream("GET", f"{base}/api/v1/events/stream?after=0",
                      headers={"Last-Event-ID": str(cursor)}, timeout=10) as response:
        assert response.status_code == 200
        for kind, stream_id, data in parse_sse(response.iter_lines()):
            if kind == "events":
                first_batch = (stream_id, json.loads(data))
                break
    assert first_batch
    stream_id, payload = first_batch
    ids = [event["id"] for event in payload["events"]]
    assert stream_id == ids[-1]
    assert ids and min(ids) > cursor


def test_global_cursor_gap_returns_bounded_snapshot_and_resume_cursor(live):
    base, app = live
    store = app.state.store
    bots = [store.create_bot(Bot(name=f"snapshot-{n}")) for n in range(2)]
    response = httpx.get(f"{base}/api/v1/events?after=999999")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "snapshot_required" and detail["snapshot_url"] == "/api/v1/snapshot"
    stream_gap = None
    with httpx.stream("GET", f"{base}/api/v1/events/stream?after=999999", timeout=10) as response:
        assert response.status_code == 200
        for kind, event_id, data in parse_sse(response.iter_lines()):
            if kind == "snapshot_required":
                stream_gap = (event_id, json.loads(data))
                break
    assert stream_gap and stream_gap[0] is None
    assert stream_gap[1]["snapshot_url"] == "/api/v1/snapshot"

    snapshot = httpx.get(f"{base}{detail['snapshot_url']}?limit=1").json()
    assert snapshot["event_cursor"] == snapshot["replay_after"]
    assert snapshot["truncated"]["bots"] is True and snapshot["next"]["bots"]
    first_names = {bot["name"] for bot in snapshot["items"]["bots"]}
    second_page = httpx.get(f"{base}{snapshot['next']['bots']}").json()
    assert len(first_names) == 1 and len(second_page) == 1
    assert second_page[0]["name"] not in first_names
    page = httpx.get(f"{base}/api/v1/events?after={snapshot['replay_after']}").json()
    assert page["after"] == snapshot["event_cursor"]
    assert all(event["id"] > snapshot["replay_after"] for event in page["events"])
    assert len(bots) == 2


def test_resource_stream_header_wins_and_silent_cross_process_write_is_polled(live):
    import sqlite3
    base, app = live
    store = app.state.store
    first = store.create_bot(Bot(name="changes-first"))
    cursor = store.list_resource_changes()["cursor"]
    second = Bot(name="changes-silent", instructions="DO NOT COPY THIS CONTENT")
    # Start with no new rows and no notification. Another SQLite connection commits
    # after response headers; the server's safety poll must discover it.
    with httpx.stream("GET", f"{base}/api/v1/changes/stream?cursor=foreign:0",
                      headers={"Last-Event-ID": cursor}, timeout=10) as response:
        assert response.status_code == 200
        with sqlite3.connect(store.config.db_path) as writer:
            writer.execute("INSERT INTO bots(id,name,doc) VALUES (?, ?, ?)",
                           (second.id, second.name, second.model_dump_json()))
        for kind, event_id, data in parse_sse(response.iter_lines(), text_ids=True):
            if kind == "changes":
                payload = json.loads(data)
                assert event_id == payload["cursor"]
                assert [item["resource_id"] for item in payload["changes"]] == [second.id]
                assert first.id not in data and second.instructions not in data
                break
            assert kind != "snapshot_required"


def test_resource_pages_snapshot_and_retention_reconciliation(live):
    base, app = live
    store = app.state.store
    for i in range(3):
        store.create_bot(Bot(name=f"resource-page-{i}"))
    first = httpx.get(f"{base}/api/v1/changes?limit=1").json()
    assert len(first["changes"]) == 1 and first["has_more"]
    later = httpx.get(f"{base}/api/v1/changes", params={"cursor": first["cursor"]}).json()
    assert len(later["changes"]) == 2 and not later["has_more"]
    assert first["cursor"] != later["cursor"] == later["high_water"]
    snapshot = httpx.get(f"{base}/api/v1/snapshot?limit=1").json()
    assert snapshot["change_cursor"] == later["cursor"] and snapshot["truncated"]["bots"]
    assert httpx.get(f"{base}/api/v1/changes", params={"cursor": snapshot["change_cursor"]}).json()["changes"] == []
    with store._tx() as db:
        db.execute("DELETE FROM resource_outbox WHERE id = 2")
    response = httpx.get(f"{base}/api/v1/changes", params={"cursor": first["cursor"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "snapshot_required"
    with httpx.stream("GET", f"{base}/api/v1/changes/stream", headers={"Last-Event-ID": first["cursor"]},
                      timeout=10) as response:
        for kind, event_id, data in parse_sse(response.iter_lines(), text_ids=True):
            assert kind == "snapshot_required" and event_id is None
            assert json.loads(data)["snapshot_url"] == "/api/v1/snapshot"
            break


def test_resource_cursor_survives_a_real_server_restart(tmp_path, monkeypatch):
    import contextlib
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "resource-restart"))

    @contextlib.contextmanager
    def server_session():
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started
            yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}", app
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()

    with server_session() as (base, app):
        app.state.store.create_bot(Bot(name="before-resource-restart"))
        cursor = httpx.get(f"{base}/api/v1/changes").json()["cursor"]
    with server_session() as (base, app):
        bot = app.state.store.create_bot(Bot(name="after-resource-restart"))
        with httpx.stream("GET", f"{base}/api/v1/changes/stream", headers={"Last-Event-ID": cursor},
                          timeout=10) as response:
            for kind, event_id, data in parse_sse(response.iter_lines(), text_ids=True):
                assert kind == "changes"
                assert [item["resource_id"] for item in json.loads(data)["changes"]] == [bot.id]
                assert event_id.startswith(cursor.split(":")[0] + ":")
                break


def test_resume_survives_a_server_restart_because_the_database_is_the_source_of_truth(tmp_path, monkeypatch):
    """A ring buffer would be empty after a restart; replay-from-SQLite is not."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    from fastapi.testclient import TestClient
    from hutch.models import Run, RunStatus
    app1 = create_app()
    with TestClient(app1) as c1:
        store = app1.state.store
        bot = store.create_bot(Bot(name="restart-bot"))
        run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.succeeded))
        for i in range(15):
            store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
        store.flush_events()
    app2 = create_app()                               # "restarted" server, same state dir
    with TestClient(app2) as c2:
        with c2.stream("GET", f"/api/runs/{run.id}/stream", headers={"Last-Event-ID": "10"}) as r:
            got = []
            for ev, id_, data in parse_sse(r.iter_lines()):
                if ev == "batch":
                    got += [e["seq"] for e in json.loads(data)["events"]]
                if ev == "end":
                    break
    assert got == [11, 12, 13, 14, 15]
