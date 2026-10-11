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


# ------------------------------------------------------ service controls

def _fake_service_status(**overrides):
    from hutch.service import ServiceStatus

    values = dict(state="active", installed=True, active=True, port=8787, unit_path=None,
                  ready=True, detail="ready", instance={"id": "x", "pid": 1}, linger="disabled",
                  main_pid=1)
    values.update(overrides)
    return ServiceStatus(**values)


def test_service_controls_require_exact_confirmation(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    called: list[str] = []
    monkeypatch.setattr("hutch.service.install_user_service",
                        lambda *a, **k: called.append("install"))
    with client:
        for route, payload in (
            ("install", {"confirm": "yes"}),
            ("restart", {"confirm": "nope"}),
            ("stop", {"confirm": ""}),
            ("uninstall", {"confirm": "delete"}),
        ):
            response = client.post(f"/api/v1/runtime/service/{route}", json=payload)
            assert response.status_code in (422,), (route, response.text)
        assert called == [], "no service action may run without the exact confirmation"


def test_service_install_and_restart_report_readiness(tmp_path, monkeypatch):
    from hutch.service import ServiceInstall, ServiceProbe

    app, client = _client(tmp_path, monkeypatch)
    installs: list[dict] = []
    monkeypatch.setattr("hutch.service.install_user_service",
                        lambda state_dir, port=8787, ready_timeout=10.0: installs.append(
                            {"state_dir": state_dir, "port": port, "ready_timeout": ready_timeout})
                        or ServiceInstall(path=tmp_path / "unit", started=True, ready=True))
    monkeypatch.setattr("hutch.service.user_service_status", lambda **k: _fake_service_status())
    with client:
        response = client.post("/api/v1/runtime/service/install",
                               json={"confirm": "install", "port": 18899})
        assert response.status_code == 200, response.text
        assert installs and installs[0]["port"] == 18899
        assert response.json()["ready"] is True

        monkeypatch.setattr("hutch.service.restart_user_service", lambda **k: None)
        restarted = client.post("/api/v1/runtime/service/restart", json={"confirm": "restart"})
        assert restarted.status_code == 200 and restarted.json()["state"] == "active"


def test_service_restart_fails_loudly_when_not_ready(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr("hutch.service.restart_user_service", lambda **k: None)
    monkeypatch.setattr("hutch.service.user_service_status", lambda **k: _fake_service_status(
        ready=False, detail="a different Hutch instance owns this port"))
    with client:
        response = client.post("/api/v1/runtime/service/restart", json={"confirm": "restart"})
        assert response.status_code == 502
        assert "readiness handshake" in response.json()["detail"]


def test_service_install_failure_is_honest(tmp_path, monkeypatch):
    from hutch.service import ServiceError

    def boom(*a, **k):
        raise ServiceError("unit file was written and systemd reports hutch.service active, but the readiness "
                           "check did not confirm the expected instance: no Hutch answered")

    app, client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr("hutch.service.install_user_service", boom)
    with client:
        response = client.post("/api/v1/runtime/service/install", json={"confirm": "install"})
        assert response.status_code == 502
        assert "did not confirm" in response.json()["detail"]


def test_service_stop_issues_the_action_after_responding(tmp_path, monkeypatch):
    import time

    app, client = _client(tmp_path, monkeypatch)
    stopped: list[str] = []
    monkeypatch.setattr("hutch.service.stop_user_service", lambda **k: stopped.append("stop"))
    with client:
        response = client.post("/api/v1/runtime/service/stop",
                               json={"confirm": "stop", "delay_seconds": 0.2})
        assert response.status_code == 200 and response.json()["stopping"] is True
        deadline = time.time() + 5
        while time.time() < deadline and not stopped:
            time.sleep(0.05)
        assert stopped == ["stop"], "the delayed stop must actually run after the response"


def test_service_uninstall_and_startup(tmp_path, monkeypatch):
    app, client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr("hutch.service.remove_user_service", lambda **k: False)
    monkeypatch.setattr("hutch.service.user_service_status", lambda **k: _fake_service_status(
        installed=False, active=False, state="not installed", ready=None))
    with client:
        assert client.post("/api/v1/runtime/service/uninstall",
                           json={"confirm": "uninstall"}).status_code == 404

        monkeypatch.setattr("hutch.service.remove_user_service", lambda **k: True)
        removed = client.post("/api/v1/runtime/service/uninstall", json={"confirm": "uninstall"})
        assert removed.status_code == 200 and removed.json()["removed"] is True

        linger_calls: list[bool] = []
        monkeypatch.setattr("hutch.service.set_linger", lambda enabled, **k: linger_calls.append(enabled)
                            or ("enabled" if enabled else "disabled"))
        started = client.post("/api/v1/runtime/service/startup",
                              json={"confirm": "startup", "enabled": True})
        assert started.status_code == 200 and linger_calls == [True]
        assert started.json()["linger"] == "enabled"


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
