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


def parse_sse(lines):
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
            id_ = int(line[3:].strip())
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
