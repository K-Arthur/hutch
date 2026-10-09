from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request, WebSocket
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


def test_trusted_https_proxy_keeps_pairing_origin_and_secure_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    code = app.state.store.create_pairing_code()
    proxy = TestClient(app, base_url="http://hutch-origin.internal", client=("127.0.0.1", 43120))
    forwarded = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
                 "X-Forwarded-For": "198.51.100.42"}

    page = proxy.get("/pair", headers=forwarded)
    assert page.status_code == 200, page.text
    assert "secure" in page.headers["set-cookie"].lower()
    csrf = proxy.cookies.get("hutch_csrf")
    downgraded_origin = proxy.post(
        "/api/v1/pairing/exchange", json={"code": code, "label": "Phone"},
        headers={**forwarded, "Origin": "http://hutch.example", "Cookie": f"hutch_csrf={csrf}"})
    assert downgraded_origin.status_code == 403
    paired = proxy.post("/api/v1/pairing/exchange", json={"code": code, "label": "Phone"},
                        headers={**forwarded, "Origin": "https://hutch.example", "Cookie": f"hutch_csrf={csrf}"})
    assert paired.status_code == 200, paired.text
    assert "secure" in paired.headers["set-cookie"].lower()
    device = paired.cookies.get("hutch_device")
    assert device
    assert proxy.get("/api/bots", headers={**forwarded, "Cookie": f"hutch_device={device}"}).status_code == 200


def test_trusted_proxy_requires_an_explicit_public_host_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "operator-token")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    client = TestClient(create_app(), base_url="http://origin.internal", client=("127.0.0.1", 43120))
    response = client.get("/api/bots", headers={"Host": "origin.internal", "X-Forwarded-Proto": "https",
                                                 "X-Forwarded-Host": "attacker.example",
                                                 "Authorization": "Bearer operator-token"})
    assert response.status_code == 421
    assert "not in HUTCH_ALLOWED_HOSTS" in response.text


def test_untrusted_peer_cannot_spoof_https_forwarding(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    client = TestClient(create_app(), base_url="http://origin.internal", client=("198.51.100.77", 43120))
    response = client.get("/api/bots", headers={"Host": "origin.internal", "X-Forwarded-Proto": "https",
                                                 "X-Forwarded-Host": "hutch.example"})
    assert response.status_code == 426
    assert "requires HTTPS" in response.text


def test_untrusted_forwarding_headers_are_not_passed_to_the_application(monkeypatch):
    from hutch.server.security import SecurityMiddleware

    app = FastAPI()

    @app.get("/forwarded")
    async def forwarded(request: Request):
        return {"host": request.headers.get("x-forwarded-host"),
                "proto": request.headers.get("x-forwarded-proto"),
                "for": request.headers.get("x-forwarded-for"),
                "standard": request.headers.get("forwarded"),
                "real_ip": request.headers.get("x-real-ip")}

    client = TestClient(SecurityMiddleware(app), base_url="http://localhost",
                        client=("127.0.0.1", 43120))
    response = client.get("/forwarded", headers={
        "X-Forwarded-Host": "hutch.example", "X-Forwarded-Proto": "https",
        "X-Forwarded-For": "198.51.100.42", "Forwarded": "for=198.51.100.42;proto=https;host=hutch.example",
        "X-Real-IP": "198.51.100.42"})
    assert response.status_code == 200
    assert response.json() == {"host": None, "proto": None, "for": None, "standard": None, "real_ip": None}


def test_trusted_proxy_rejects_malformed_public_host_port(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    client = TestClient(create_app(), base_url="http://origin.internal", client=("127.0.0.1", 43120))
    response = client.get("/api/bots", headers={"X-Forwarded-Proto": "https",
                                                 "X-Forwarded-Host": "hutch.example:99999"})
    assert response.status_code == 400
    assert "invalid public host" in response.text


def test_trusted_proxy_rejects_duplicate_required_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    client = TestClient(create_app(), base_url="http://origin.internal", client=("127.0.0.1", 43120))
    response = client.get("/api/bots", headers=[
        ("X-Forwarded-Proto", "https"), ("X-Forwarded-Host", "hutch.example"),
        ("X-Forwarded-Host", "attacker.example")])
    assert response.status_code == 400
    assert "one X-Forwarded-Host" in response.text


def test_trusted_proxy_uses_validated_forwarded_client_for_source_limits(monkeypatch):
    from hutch.server.security import SecurityMiddleware

    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "operator-token")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = FastAPI()

    @app.get("/client")
    async def client_address(request: Request):
        return {"client": request.client.host}

    secured = SecurityMiddleware(app, auth_token="operator-token")
    client = TestClient(secured, base_url="http://origin.internal", client=("127.0.0.1", 43120))
    response = client.get("/client", headers={
        "X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
        "X-Forwarded-For": "198.51.100.42", "Authorization": "Bearer operator-token"})
    assert response.status_code == 200
    assert response.json() == {"client": "198.51.100.42"}


def test_trusted_proxy_capability_requires_explicit_remote_and_host_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "operator-token")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
               "Authorization": "Bearer operator-token"}
    with TestClient(create_app(), base_url="http://localhost", client=("127.0.0.1", 43120)) as client:
        capabilities = {row["id"]: row for row in client.get("/api/v1/capabilities", headers=headers).json()}
    assert capabilities["trusted_https_proxy"]["status"] == "experimental"
    assert capabilities["trusted_https_proxy"]["verification"] == "local_forwarded_scope_fixtures"

    monkeypatch.delenv("HUTCH_TRUSTED_PROXIES")
    with TestClient(create_app(), base_url="http://localhost", client=("127.0.0.1", 43120)) as client:
        capabilities = {row["id"]: row for row in client.get("/api/v1/capabilities", headers=headers).json()}
    assert capabilities["trusted_https_proxy"]["status"] == "unavailable"


def test_trusted_proxy_websocket_uses_forwarded_https_host_and_device_auth(monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    from hutch.server.security import SecurityMiddleware

    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = FastAPI()

    @app.websocket("/ws")
    async def socket(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"scheme": ws.scope["scheme"], "host": ws.headers["host"]})
        await ws.close()

    secured = SecurityMiddleware(app, device_auth=lambda token: token == "device-secret")
    client = TestClient(secured, base_url="http://origin.internal", client=("127.0.0.1", 43120))
    headers = {"Host": "origin.internal", "Origin": "https://hutch.example",
               "X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
               "Cookie": "hutch_device=device-secret"}
    with client.websocket_connect("/ws", headers=headers) as ws:
        assert ws.receive_json() == {"scheme": "wss", "host": "hutch.example"}

    try:
        with client.websocket_connect("/ws", headers={k: v for k, v in headers.items() if k != "Cookie"}):
            raise AssertionError("unauthenticated proxied socket was accepted")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401

    downgraded = {**headers, "Origin": "http://hutch.example"}
    try:
        with client.websocket_connect("/ws", headers=downgraded):
            raise AssertionError("proxied socket accepted an HTTP Origin for an HTTPS page")
    except WebSocketDisconnect as exc:
        assert exc.code == 4403
