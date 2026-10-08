from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.server.app import create_app


def test_pairing_is_single_use_and_device_session_is_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    app = create_app()
    code = app.state.store.create_pairing_code()
    with TestClient(create_app()) as client_http:
        assert client_http.get("/pair", headers={"Host": "hutch.example"}).status_code == 426
        refused = client_http.post("/api/v1/pairing/exchange", json={"code": code},
                                   headers={"Host": "hutch.example"})
        assert refused.status_code == 426

    with TestClient(app, base_url="https://testserver") as client:
        page = client.get("/pair", headers={"Host": "hutch.example"})
        assert page.status_code == 200
        assert "Pair this device" in page.text and "/static/pair.js" in page.text
        assert str(tmp_path) not in page.text
        login = client.get("/login", headers={"Host": "hutch.example"})
        assert login.status_code == 200 and 'href="/pair"' in login.text
        response = client.post("/api/v1/pairing/exchange", json={"code": code, "label": "Kevin phone"},
                               headers={"Host": "hutch.example"})
        assert response.status_code == 200, response.text
        device = response.json()
        assert device["paired"] and device["label"] == "Kevin phone"
        assert "token" not in response.text
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "secure" in response.headers["set-cookie"].lower()
        listed = client.get("/api/v1/devices", headers={"Host": "hutch.example"})
        assert listed.status_code == 200
        assert len(listed.json()) == 1 and listed.json()[0]["id"] == device["id"]
        assert listed.json()[0]["current"] is True
        assert client.get("/api/bots", headers={"Host": "hutch.example"}).status_code == 200

        replay = client.post("/api/v1/pairing/exchange", json={"code": code},
                             headers={"Host": "hutch.example"})
        assert replay.status_code == 401
        revoked = client.post(f"/api/v1/devices/{device['id']}/revoke", headers={"Host": "hutch.example"})
        assert revoked.status_code == 200 and revoked.json() == {"revoked": device["id"]}
        assert client.get("/api/bots", headers={"Host": "hutch.example"}).status_code == 401


def test_device_list_marks_only_the_authenticated_current_session(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    app = create_app()
    first_code = app.state.store.create_pairing_code()
    second_code = app.state.store.create_pairing_code()
    with TestClient(app, base_url="https://testserver") as client:
        one = client.post("/api/v1/pairing/exchange", json={"code": first_code, "label": "Laptop"},
                          headers={"Host": "hutch.example"}).json()
        first_cookie = client.cookies.get("hutch_device")
        two = client.post("/api/v1/pairing/exchange", json={"code": second_code, "label": "Phone"},
                          headers={"Host": "hutch.example"}).json()
        rows = client.get("/api/v1/devices", headers={"Host": "hutch.example"}).json()
        assert {row["id"]: row["current"] for row in rows} == {one["id"]: False, two["id"]: True}
        first_rows = client.get("/api/v1/devices", headers={"Host": "hutch.example", "Cookie": f"hutch_device={first_cookie}"}).json()
        assert {row["id"]: row["current"] for row in first_rows} == {one["id"]: True, two["id"]: False}


def test_pairing_code_race_mints_only_one_device(store):
    code = store.create_pairing_code()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda i: store.exchange_pairing_code(code, f"device {i}", f"192.0.2.{i+1}")[1],
                                  range(6)))
    assert outcomes.count("ok") == 1
    assert outcomes.count("invalid") == 5
    assert len(store.list_device_sessions()) == 1


def test_pairing_exchange_rate_limits_invalid_codes(store):
    outcomes = [store.exchange_pairing_code("NOT-A-VALID-CODE", "phone", "192.0.2.44")[1] for _ in range(6)]
    assert outcomes == ["invalid"] * 5 + ["rate_limited"]


def test_expired_pairing_code_and_expired_device_session_are_rejected(store):
    code = store.create_pairing_code(ttl_seconds=-1)
    assert store.exchange_pairing_code(code, "phone", "192.0.2.1")[1] == "invalid"

    fresh_code = store.create_pairing_code()
    session, outcome = store.exchange_pairing_code(fresh_code, "phone", "192.0.2.2")
    assert outcome == "ok" and session is not None
    store._db.execute("UPDATE device_sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                      (session["id"],))
    store._db.commit()
    assert store.validate_device_token(session["token"]) is False
    assert store.list_device_sessions() == []


def test_remote_bind_requires_explicit_flag_and_tls_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    runner = CliRunner()
    blocked = runner.invoke(cli_app, ["serve", "--host", "0.0.0.0"])
    assert blocked.exit_code == 2 and "--allow-remote" in blocked.output

    no_tls = runner.invoke(cli_app, ["serve", "--host", "0.0.0.0", "--allow-remote"])
    assert no_tls.exit_code == 2 and "--tls-cert" in no_tls.output

    pairing = runner.invoke(cli_app, ["pairing", "create"])
    assert pairing.exit_code == 0 and "expires in 60 seconds" in pairing.output
    assert runner.invoke(cli_app, ["pairing", "list"]).exit_code == 0
