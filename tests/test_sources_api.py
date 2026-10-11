"""Sources API: registration, inspection, and bounded manual checks (local owners only)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from hutch.store import Store


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = create_app()
    return app, TestClient(app)


def _bot(store: Store, name="watcher") -> Bot:
    return store.create_bot(Bot(name=name, model="mock/demo"))


def test_source_api_creates_lists_updates_and_deletes(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    bot = _bot(app.state.store, name="folder-bot")
    root = tmp_path / "watched"
    root.mkdir()
    with client:
        created = client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "folder", "name": "Inbox", "path": str(root),
            "every_seconds": 60, "prompt": "Summarize {summary}", "cooldown_seconds": 120,
        })
        assert created.status_code == 201, created.text
        source = created.json()
        assert source["kind"] == "folder" and source["enabled"] is True
        assert source["config"]["check_seconds"] == 60

        listed = client.get("/api/v1/sources").json()
        assert [item["id"] for item in listed["items"]] == [source["id"]]
        assert listed["stats"]["total"] == 1

        updated = client.put(f"/api/v1/sources/{source['id']}", json={"enabled": False, "name": "Paused"})
        assert updated.status_code == 200 and updated.json()["enabled"] is False
        assert updated.json()["revision"] == source["revision"] + 1

        events = client.get(f"/api/v1/sources/{source['id']}/events").json()
        assert events["items"] == []

        removed = client.delete(f"/api/v1/sources/{source['id']}")
        assert removed.status_code == 200
        assert client.get("/api/v1/sources").json()["items"] == []


def test_source_api_refuses_unsafe_or_incomplete_config(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    bot = _bot(app.state.store)
    with client:
        relative = client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "folder", "name": "bad", "path": "relative/path"})
        assert relative.status_code == 422
        private_feed = client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "feed", "name": "bad", "url": "http://127.0.0.1:8080/feed"})
        assert private_feed.status_code == 422, "a feed source must never target a private address"
        missing_feed = client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "feed", "name": "bad", "url": ""})
        assert missing_feed.status_code == 422


def test_source_api_check_now_schedules_without_blocking_the_request(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    bot = _bot(app.state.store)
    root = tmp_path / "watched"
    root.mkdir()
    with client:
        source = client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "folder", "name": "Inbox", "path": str(root)}).json()
        before = app.state.store.get_event_source(source["id"])
        assert client.post(f"/api/v1/sources/{source['id']}/check").status_code == 200
        after = app.state.store.get_event_source(source["id"])
        from hutch.models import iso, utcnow
        assert after["next_check_at"] <= iso(utcnow()), "a manual check makes the source due immediately"
        assert before["revision"] == after["revision"], "scheduling a check is not a registration edit"
        assert app.state.store.due_event_sources(limit=5), "the supervisor will pick it up"
        assert client.post("/api/v1/sources/src_missing/check").status_code == 404


def test_source_api_events_are_bounded_and_filterable(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    store = app.state.store
    bot = _bot(store)
    root = tmp_path / "watched"
    root.mkdir()
    source = store.create_event_source(bot_id=bot.id, kind="folder", name="Inbox",
                                       config={"path": str(root), "settle_seconds": 0})

    from hutch import sources
    from hutch.sources import SourceRuntime
    from hutch.models import utcnow

    (root / "a.txt").write_bytes(b"one")
    row = store.get_event_source(source["id"])
    outcome = sources.check_source("folder", row["config"], row["cursor"], runtime=SourceRuntime(), now=utcnow())
    store.record_source_check(source["id"], row["revision"], cursor=outcome.cursor, events=outcome.events,
                              summary=outcome.summary, interval=60)
    with client:
        items = client.get(f"/api/v1/sources/{source['id']}/events", params={"status": "recorded"}).json()["items"]
        assert len(items) == 1 and "a.txt" in items[0]["summary"]
        assert client.get(f"/api/v1/sources/{source['id']}/events", params={"status": "nope"}).status_code == 422


def test_runtime_endpoint_includes_source_summary(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    bot = _bot(app.state.store)
    with client:
        body = client.get("/api/v1/runtime").json()
        assert "sources" in body and body["sources"]["total"] == 0
        client.post("/api/v1/sources", json={
            "bot": bot.id, "kind": "folder", "name": "Inbox", "path": str(tmp_path / "watched")})
        body = client.get("/api/v1/runtime").json()
        assert body["sources"]["total"] == 1 and body["sources"]["enabled"] == 1


def test_source_cli_add_list_check_remove(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from hutch.cli import app as cli_app
    from hutch.config import get_config

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    store = Store(get_config())
    store.create_bot(Bot(name="cli-bot", model="mock/demo"))
    root = tmp_path / "watched"
    root.mkdir()
    runner = CliRunner()

    added = runner.invoke(cli_app, ["source", "add", "cli-bot", "--kind", "folder",
                                    "--path", str(root), "--name", "Inbox"])
    assert added.exit_code == 0, added.output
    source = store.list_event_sources()[0]

    listed = runner.invoke(cli_app, ["source", "list"])
    assert listed.exit_code == 0 and "Inbox" in listed.output and "enabled" in listed.output

    checked = runner.invoke(cli_app, ["source", "check", source["id"]])
    assert checked.exit_code == 0 and "Scheduled" in checked.output

    refused = runner.invoke(cli_app, ["source", "add", "cli-bot", "--kind", "folder", "--path", "relative"])
    assert refused.exit_code == 2 and "absolute path" in refused.output

    events = runner.invoke(cli_app, ["source", "events", source["id"]])
    assert events.exit_code == 0

    removed = runner.invoke(cli_app, ["source", "remove", source["id"]])
    assert removed.exit_code == 0 and "Removed" in removed.output
    assert store.list_event_sources() == []
