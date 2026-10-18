from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import ipaddress
import multiprocessing
import os
import secrets
import socket
import ssl
import threading
import time

from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.server.app import (PUBLIC_REMOTE_ROUTES, REMOTE_ROUTE_CAPABILITIES, create_app)
from hutch.server.security import SESSION_COOKIE
from hutch.models import iso, utcnow


def _enroll_test_passkey(store, code: str, label: str = "Phone", *, allow_start: bool = False):
    enrollment, outcome = store.exchange_pairing_code(code, label, "test-address")
    assert outcome == "ok" and enrollment
    handle = store.webauthn_user_handle()
    credential = secrets.token_bytes(24)
    return store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": credential, "public_key": b"test-public-key", "sign_count": 0,
        "backup_eligible": True, "backed_up": True, "user_handle": handle,
    })


def _phone_headers(extra=None):
    return {"Host": "hutch.example", "Origin": "https://hutch.example", **(extra or {})}


def _revoke_credential_in_child(state_dir: str, credential_id: str, result_queue) -> None:
    os.environ["HUTCH_STATE_DIR"] = state_dir
    from hutch.config import get_config
    from hutch.store import Store

    store = Store(get_config())
    try:
        result_queue.put(store.revoke_device_session(credential_id))
    finally:
        store.close()


def test_pairing_creates_enrollment_only_cookie_then_passkey_session_is_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    app = create_app()
    code = app.state.store.create_pairing_code(allow_start=True)
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
                               headers=_phone_headers({"X-Hutch-Request": "1"}))
        assert response.status_code == 200, response.text
        enrollment = response.json()
        assert enrollment["enrollment"] and enrollment["label"] == "Kevin phone"
        assert "token" not in response.text
        assert "paired" not in enrollment
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "secure" in response.headers["set-cookie"].lower()
        assert client.cookies.get("hutch_enroll")
        assert client.cookies.get(SESSION_COOKIE) is None
        options = client.post("/api/v1/passkeys/registration/options",
                              headers=_phone_headers({"X-Hutch-Request": "1"}))
        assert options.status_code == 200, options.text
        assert options.json()["authenticatorSelection"]["userVerification"] == "required"
        assert client.get("/api/bots", headers={"Host": "hutch.example"}).status_code == 401

        session = app.state.store.finish_passkey_enrollment(client.cookies.get("hutch_enroll"), {
            "credential_id": secrets.token_bytes(24), "public_key": b"test-public-key", "sign_count": 0,
            "backup_eligible": True, "backed_up": True, "user_handle": app.state.store.webauthn_user_handle(),
        })
        client.cookies.set(SESSION_COOKIE, session["session_token"])
        status = client.get("/api/v1/session", headers={"Host": "hutch.example"})
        assert status.status_code == 200 and status.json()["principal"] == "paired"
        assert status.json()["capabilities"] == ["monitor", "review", "start"]
        assert client.get("/api/bots", headers={"Host": "hutch.example"}).status_code == 200
        private_view = client.get("/api/bots", headers={"Host": "hutch.example"})
        assert "private" in private_view.headers["cache-control"] and "no-store" in private_view.headers["cache-control"]
        assert "frame-ancestors 'none'" in private_view.headers["content-security-policy"]
        assert client.get("/api/v1/devices", headers={"Host": "hutch.example"}).status_code == 403

        replay = client.post("/api/v1/pairing/exchange", json={"code": code},
                             headers=_phone_headers({"X-Hutch-Request": "1"}))
        assert replay.status_code == 401
        device_id = session["id"]
        assert app.state.store.revoke_device_session(device_id)
        assert client.get("/api/bots", headers={"Host": "hutch.example"}).status_code == 401


def test_device_inventory_marks_only_the_authenticated_current_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "local-owner-token")
    app = create_app()
    first_code = app.state.store.create_pairing_code(allow_start=False)
    second_code = app.state.store.create_pairing_code(allow_start=True)
    one = _enroll_test_passkey(app.state.store, first_code, "Laptop")
    two = _enroll_test_passkey(app.state.store, second_code, "Phone")
    with TestClient(app, base_url="https://testserver") as client:
        owner = {"Host": "localhost", "Authorization": "Bearer local-owner-token"}
        rows = client.get("/api/v1/devices", headers=owner).json()
        assert {row["id"] for row in rows} == {one["id"], two["id"]}
        assert {tuple(row["capabilities"]) for row in rows} == {("monitor", "review"), ("monitor", "review", "start")}


def test_credential_revocation_is_visible_across_processes(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    owner_store = app.state.store
    phone = _enroll_test_passkey(owner_store, owner_store.create_pairing_code(), "cross-connection phone")
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    child = context.Process(target=_revoke_credential_in_child,
                            args=(str(app.state.config.state_dir), phone["id"], result_queue))
    try:
        assert owner_store.authenticate_session(phone["session_token"])
        child.start()
        assert result_queue.get(timeout=15) is True
        child.join(timeout=15)
        assert child.exitcode == 0
        assert owner_store.authenticate_session(phone["session_token"]) is None
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        result_queue.close()
        owner_store.close()


def test_pairing_code_race_mints_only_one_device(store):
    code = store.create_pairing_code()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda i: store.exchange_pairing_code(code, f"device {i}", f"192.0.2.{i+1}")[1],
                                  range(6)))
    assert outcomes.count("ok") == 1
    assert outcomes.count("invalid") == 5
    with store._lock:
        assert store._db.execute("SELECT COUNT(*) FROM auth_sessions WHERE purpose='enrollment'").fetchone()[0] == 1
    assert store.list_device_sessions() == []


def test_pairing_exchange_rate_limits_invalid_codes(store):
    outcomes = [store.exchange_pairing_code("NOT-A-VALID-CODE", "phone", "192.0.2.44")[1] for _ in range(6)]
    assert outcomes == ["invalid"] * 5 + ["rate_limited"]


def test_expired_pairing_and_enrollment_sessions_are_rejected(store):
    code = store.create_pairing_code(ttl_seconds=-1)
    assert store.exchange_pairing_code(code, "phone", "192.0.2.1")[1] == "invalid"

    fresh_code = store.create_pairing_code()
    session, outcome = store.exchange_pairing_code(fresh_code, "phone", "192.0.2.2")
    assert outcome == "ok" and session is not None
    store._db.execute("UPDATE auth_sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                      (session["id"],))
    store._db.commit()
    assert store.auth_flow(session["token"], ("enrollment",)) is None


def test_registration_challenge_issuance_is_bounded_per_enrollment(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    app = create_app()
    headers = _phone_headers({"X-Hutch-Request": "1"})

    with TestClient(app, base_url="https://testserver") as client:
        exchange = client.post("/api/v1/pairing/exchange", json={"code": app.state.store.create_pairing_code()},
                               headers=headers)
        assert exchange.status_code == 200, exchange.text
        for _ in range(16):
            options = client.post("/api/v1/passkeys/registration/options", headers=headers)
            assert options.status_code == 200, options.text
        limited = client.post("/api/v1/passkeys/registration/options", headers=headers)
        assert limited.status_code == 429, limited.text
        with app.state.store._lock:
            count = app.state.store._db.execute("SELECT COUNT(*) FROM auth_challenges").fetchone()[0]
        assert count == 16


def test_registration_challenge_limit_is_atomic_under_concurrent_requests(store):
    from hutch.store import AuthChallengeLimitExceeded

    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "racing enrollment", "test-address")
    assert outcome == "ok" and enrollment

    def issue_challenge(_index):
        try:
            store.create_auth_challenge(enrollment["token"], "registration")
            return "created"
        except AuthChallengeLimitExceeded:
            return "limited"

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(issue_challenge, range(32)))
    assert results.count("created") == 16
    assert results.count("limited") == 16
    with store._lock:
        count = store._db.execute("SELECT COUNT(*) FROM auth_challenges WHERE session_id=?",
                                  (enrollment["id"],)).fetchone()[0]
    assert count == 16


def test_passkey_challenges_are_expiring_and_single_use(store):
    code = store.create_pairing_code()
    enrollment, outcome = store.exchange_pairing_code(code, "phone", "192.0.2.8")
    assert outcome == "ok" and enrollment
    registration = store.create_auth_challenge(enrollment["token"], "registration")
    assert store.consume_auth_challenge(enrollment["token"], registration["id"], "registration")
    assert store.consume_auth_challenge(enrollment["token"], registration["id"], "registration") is None
    expired = store.create_auth_challenge(enrollment["token"], "registration")
    store._db.execute("UPDATE auth_challenges SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                      (expired["id"],))
    store._db.commit()
    assert store.consume_auth_challenge(enrollment["token"], expired["id"], "registration") is None

    session = _enroll_test_passkey(store, store.create_pairing_code(), "laptop")
    login = store.create_auth_flow("login")
    challenge = store.create_auth_challenge(login["token"], "authentication")
    assert store.consume_auth_challenge(login["token"], challenge["id"], "authentication")
    assert store.consume_auth_challenge(login["token"], challenge["id"], "authentication") is None
    assert session["session_token"]


def test_idle_and_absolute_session_expiry_and_reads_do_not_renew(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    session = _enroll_test_passkey(app.state.store, app.state.store.create_pairing_code())
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(SESSION_COOKIE, session["session_token"])
        headers = {"Host": "hutch.example"}
        before = app.state.store._db.execute("SELECT last_activity_at FROM auth_sessions WHERE id=?",
                                             (session["session_id"],)).fetchone()[0]
        assert client.get("/api/v1/session", headers=headers).status_code == 200
        assert client.get("/api/bots", headers=headers).status_code == 200
        after = app.state.store._db.execute("SELECT last_activity_at FROM auth_sessions WHERE id=?",
                                            (session["session_id"],)).fetchone()[0]
        assert after == before
        activity = client.post("/api/v1/session/activity", json={}, headers=_phone_headers({"X-Hutch-Request": "1"}))
        assert activity.status_code == 403  # activity also requires the session-bound CSRF token
        token = app.state.store.auth_csrf_token(session["session_token"], session["session_id"])
        activity = client.post("/api/v1/session/activity", json={}, headers=_phone_headers(
            {"X-Hutch-Request": "1", "X-Hutch-CSRF": token}))
        assert activity.status_code == 200
        app.state.store._db.execute("UPDATE auth_sessions SET last_activity_at=? WHERE id=?",
                                    (iso(utcnow() - timedelta(minutes=31)), session["session_id"]))
        app.state.store._db.commit()
        assert app.state.store.authenticate_session(session["session_token"]) is None
        assert app.state.store.touch_auth_session(session["session_token"]) is False

        second = _enroll_test_passkey(app.state.store, app.state.store.create_pairing_code(), "tablet")
        app.state.store._db.execute("UPDATE auth_sessions SET absolute_expires_at=? WHERE id=?",
                                    (iso(utcnow() - timedelta(seconds=1)), second["session_id"]))
        app.state.store._db.commit()
        assert app.state.store.authenticate_session(second["session_token"]) is None


def test_passkey_synced_credential_supports_concurrent_login_flows(store):
    session = _enroll_test_passkey(store, store.create_pairing_code(), "synced phone")
    with store._lock:
        row = store._db.execute("SELECT id, credential_id FROM paired_credentials WHERE id=?",
                                (session["id"],)).fetchone()
    verified = {"credential_row_id": row["id"], "credential_id": bytes(row["credential_id"]),
                "sign_count": 0, "backed_up": True,
                "user_handle": store.webauthn_user_handle()}
    flows = [store.create_auth_flow("login") for _ in range(2)]
    def finish(flow):
        return store.finish_passkey_login(flow["token"], flow["id"], verified)
    with ThreadPoolExecutor(max_workers=2) as pool:
        sessions = list(pool.map(finish, flows))
    assert len({item["session_id"] for item in sessions}) == 2
    assert all(store.authenticate_session(item["session_token"]) for item in sessions)


def test_passkey_attempt_limit_is_atomic_and_success_clears_window(store):
    address = "198.51.100.52"
    assert all(store.begin_passkey_attempt(address) for _ in range(10))
    assert store.begin_passkey_attempt(address) is False
    store.record_passkey_attempt(address, succeeded=True)
    assert store.begin_passkey_attempt(address)
    assert all(store.begin_passkey_attempt(address, limit=30, purpose="login_options") for _ in range(30))
    assert store.begin_passkey_attempt(address, limit=30, purpose="login_options") is False
    # Requesting ceremony options and submitting a proof use independent buckets.
    assert store.begin_passkey_attempt(address)
    store.record_passkey_attempt(address, succeeded=True, purpose="login_options")
    assert store.begin_passkey_attempt(address, limit=30, purpose="login_options")


def test_passkey_login_options_are_rate_limited_per_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    app = create_app()
    _enroll_test_passkey(app.state.store, app.state.store.create_pairing_code(), "rate-limit phone")
    headers = _phone_headers({"X-Hutch-Request": "1"})
    with TestClient(app, base_url="https://testserver") as client:
        for _ in range(30):
            assert client.post("/api/v1/passkeys/login/options", headers=headers).status_code == 200
        blocked = client.post("/api/v1/passkeys/login/options", headers=headers)
        assert blocked.status_code == 429


def test_webauthn_configuration_requires_one_canonical_https_origin(monkeypatch):
    from hutch.server.passkeys import PasskeyConfigError, relying_party

    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    assert relying_party() == ("hutch.example", "https://hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example:8787")
    assert relying_party() == ("hutch.example", "https://hutch.example:8787")
    for origin in ("http://hutch.example", "https://other.example", "https://hutch.example:443",
                   "https://hutch.example:8787/", "https://hutch.example:8787/path",
                   "https://hutch.example:bad"):
        monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", origin)
        try:
            relying_party()
        except PasskeyConfigError:
            pass
        else:
            raise AssertionError(f"accepted non-canonical WebAuthn origin: {origin}")


def test_paired_route_inventory_is_total_and_sensitive_aliases_stay_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    registered = {(method.upper(), route.path) for route in app.routes if isinstance(route, APIRoute)
                  for method in (route.methods or ())}
    assert registered <= REMOTE_ROUTE_CAPABILITIES.keys()
    assert PUBLIC_REMOTE_ROUTES <= REMOTE_ROUTE_CAPABILITIES.keys()
    for key in {
        ("GET", "/legacy"),
        ("GET", "/api/stats"),
        ("GET", "/api/overview"),
        ("GET", "/api/runs"),
        ("GET", "/api/v1/runtime"),
        ("POST", "/api/v1/runtime/service/install"),
        ("POST", "/api/v1/runtime/service/restart"),
        ("POST", "/api/v1/runtime/service/stop"),
        ("POST", "/api/v1/runtime/service/uninstall"),
        ("POST", "/api/v1/runtime/service/startup"),
        ("GET", "/api/v1/sources"),
        ("POST", "/api/v1/sources"),
        ("PUT", "/api/v1/sources/{source_id}"),
        ("DELETE", "/api/v1/sources/{source_id}"),
        ("GET", "/api/v1/sources/{source_id}/events"),
        ("POST", "/api/v1/sources/{source_id}/check"),
        ("GET", "/api/v1/jobs"),
        ("GET", "/api/v1/jobs/{job_id}"),
        ("POST", "/api/v1/jobs/{job_id}/cancel"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/events/stream"),
        ("GET", "/api/v1/tasks/runs/{run_id}/artifacts"),
        ("GET", "/api/v1/conversations/{conversation_id}/export"),
        ("POST", "/api/runs/{run_id}/stop"),
        ("POST", "/api/approvals/{approval_id}/approve"),
        ("POST", "/login"),
    }:
        assert REMOTE_ROUTE_CAPABILITIES[key] is None


def test_paired_routes_require_origin_csrf_and_deny_legacy_mutation_aliases(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    session = _enroll_test_passkey(app.state.store, app.state.store.create_pairing_code(), allow_start=True)
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(SESSION_COOKIE, session["session_token"])
        bad_origin = client.post("/api/v1/tasks/runs/missing/stop", json={}, headers={
            "Host": "hutch.example", "Origin": "https://evil.example", "X-Hutch-Request": "1"})
        assert bad_origin.status_code == 403
        missing_csrf = client.post("/api/v1/tasks/runs/missing/stop", json={}, headers=_phone_headers(
            {"X-Hutch-Request": "1", "Idempotency-Key": "stop-1"}))
        assert missing_csrf.status_code == 403
        csrf = app.state.store.auth_csrf_token(session["session_token"], session["session_id"])
        assert client.post("/api/v1/search/messages", json={"q": "private phrase"}, headers=_phone_headers(
            {"X-Hutch-Request": "1"})).status_code == 403
        search_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": csrf})
        assert client.post("/api/v1/search/messages", json={"q": "private phrase"},
                           headers=search_headers).status_code == 200
        secure_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": csrf,
                                         "Idempotency-Key": "stop-1"})
        assert client.post("/api/runs/missing/stop", json={}, headers=secure_headers).status_code == 403
        assert client.get("/api/v1/tasks/runs/missing/artifacts", headers={"Host": "hutch.example"}).status_code == 403
        assert client.get("/api/v1/conversations/missing/export", headers={"Host": "hutch.example"}).status_code == 403


def test_phone_workflow_monitor_and_review_permissions_use_redacted_projections(tmp_path, monkeypatch):
    from hutch.models import Bot, Run
    from hutch.workflow import persistence as wstore
    from hutch.workflow.submit import submit_workflow

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="phone-workflow", model="mock/demo", tools=[]))
    plan = {"name": "phone-workflow-review", "inputs": {"memo": {"type": "string"}},
            "envelope": {"tools": []}, "budget": {"max_nodes": 3, "max_model_calls": 0},
            "nodes": [{"kind": "ask", "id": "confirm", "question": "Continue?",
                       "options": ["yes", "no"], "timeout_seconds": 300},
                      {"kind": "ask", "id": "confirm_scope", "question": "Which scope?",
                       "options": ["summary", "full"], "timeout_seconds": 300}]}

    def submit(name: str):
        candidate = {**plan, "name": name}
        return submit_workflow(store, bot=bot, plan=candidate, inputs={"memo": "PRIVATE_INPUT_SENTINEL"},
                               definition_name=name)

    first = submit("phone-workflow-review")
    second = submit("phone-workflow-stop")
    monitor = _enroll_test_passkey(store, store.create_pairing_code(), "Monitor-only phone")
    store._db.execute("UPDATE paired_credentials SET capabilities_json='[\"monitor\"]' WHERE id=?",
                      (monitor["id"],))
    store._db.commit()
    review = _enroll_test_passkey(store, store.create_pairing_code(), "Review phone")

    with TestClient(app, base_url="https://testserver") as client:
        deadline = time.monotonic() + 10
        first_questions = second_questions = []
        while time.monotonic() < deadline:
            first_questions = wstore.questions(store, first.workflow_run_id, status="pending")
            second_questions = wstore.questions(store, second.workflow_run_id, status="pending")
            if len(first_questions) == len(second_questions) == 2:
                break
            time.sleep(0.05)
        assert len(first_questions) == len(second_questions) == 2, "workflow ask nodes should park with durable question IDs"
        first_question = next(question for question in first_questions if question["site_id"] == "confirm")
        deadline = time.monotonic() + 10
        parked_attempt = wstore.workflow_attempt_quiescence(store, second.attempt_run_id)
        while time.monotonic() < deadline and not parked_attempt["attempt_parked"]:
            time.sleep(0.05)
            parked_attempt = wstore.workflow_attempt_quiescence(store, second.attempt_run_id)
        assert parked_attempt["attempt_parked"]
        assert wstore.workflow_pause_controls(store, second.workflow_run_id)["pause_available"]
        pause_child = Run(bot_id=bot.id, prompt="phone pause projection child", kind="step")
        with store._tx() as db:
            db.execute("INSERT INTO runs (id, bot_id, doc, status, created_at, parent_run_id, kind) "
                       "VALUES (?, ?, ?, 'waiting_human', ?, ?, 'step')",
                       (pause_child.id, bot.id, pause_child.model_dump_json(), iso(utcnow()),
                        second.attempt_run_id))
        assert not wstore.workflow_attempt_quiescence(store, second.attempt_run_id)["owned_work_quiet"]
        pause_result = wstore.set_workflow_pause(
            store, second.workflow_run_id, paused=True,
            expected_revision_id=second.revision_id,
            expected_generation=second.attempt_run_id,
            idem_key="phone-pause-requested-projection", request_hash="phone-pause-requested-projection")
        assert pause_result["paused"] is True and pause_result["parked"] is False
        assert wstore.workflow_pause_controls(store, second.workflow_run_id)["pause_ready"] is False
        # A private result in the authoritative record must remain absent from phone projections.
        with store._tx() as db:
            db.execute("UPDATE workflow_nodes SET result_json=? WHERE workflow_run_id=? AND site_id='confirm'",
                       ('{"private":"PRIVATE_RESULT_SENTINEL"}', first.workflow_run_id))

        client.cookies.set(SESSION_COOKIE, monitor["session_token"])
        phone_runs = client.get("/api/v1/phone/workflows/runs", headers=_phone_headers())
        assert phone_runs.status_code == 200
        requested = next(item for item in phone_runs.json()["items"] if item["id"] == second.workflow_run_id)
        assert requested["pause_requested"] is True and requested["pause_ready"] is False
        monitor_detail = client.get(f"/api/v1/phone/workflows/runs/{first.workflow_run_id}",
                                    headers=_phone_headers())
        assert monitor_detail.status_code == 200, monitor_detail.text
        assert "PRIVATE_INPUT_SENTINEL" not in monitor_detail.text
        assert "PRIVATE_RESULT_SENTINEL" not in monitor_detail.text
        assert "instance_key" not in monitor_detail.text
        assert monitor_detail.json()["nodes"] == [
            {"site_id": "confirm", "instance_number": 1, "kind": "ask", "status": "waiting"},
            {"site_id": "confirm_scope", "instance_number": 1, "kind": "ask", "status": "waiting"},
        ]
        requested_detail = client.get(f"/api/v1/phone/workflows/runs/{second.workflow_run_id}",
                                      headers=_phone_headers())
        assert requested_detail.status_code == 200
        assert requested_detail.json()["pause_requested"] is True
        assert requested_detail.json()["pause_ready"] is False
        with store._tx() as db:
            db.execute("UPDATE runs SET status='failed' WHERE id=?", (pause_child.id,))
        settled_detail = client.get(f"/api/v1/phone/workflows/runs/{second.workflow_run_id}",
                                    headers=_phone_headers())
        assert settled_detail.json()["pause_ready"] is True
        assert client.get("/api/v1/phone/workflows/questions", headers=_phone_headers()).status_code == 403
        monitor_csrf = store.auth_csrf_token(monitor["session_token"], monitor["session_id"])
        monitor_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": monitor_csrf,
                                          "Idempotency-Key": "monitor-answer-denied"})
        assert client.post(f"/api/v1/phone/workflows/questions/{first_question['id']}/answer",
                           json={"answer": "yes"}, headers=monitor_headers).status_code == 403
        assert client.post(f"/api/v1/phone/workflows/runs/{second.workflow_run_id}/stop",
                           json={"expected_revision_id": second.revision_id}, headers=monitor_headers).status_code == 403
        assert client.get("/api/v1/workflows/runs", headers=_phone_headers()).status_code == 403
        assert client.post("/api/v1/workflows/policy", json={"bot": bot.name, "mode": "off"},
                           headers=_phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": monitor_csrf,
                                                  "Idempotency-Key": "phone-policy-denied"})).status_code == 403
        owner_only_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": monitor_csrf,
                                             "Idempotency-Key": "phone-owner-only-denied"})
        assert client.post("/api/v1/workflows/plans", json={"bot": bot.name, "plan": plan},
                           headers=owner_only_headers).status_code == 403
        assert client.post("/api/v1/workflows/qualifications/probe",
                           json={"bot": bot.name, "role": "author"},
                           headers=owner_only_headers).status_code == 403
        assert client.post(f"/api/v1/workflows/runs/{first.workflow_run_id}/amendments/preview",
                           json={"expected_revision_id": first.revision_id,
                                 "expected_generation": first.attempt_run_id, "plan": plan},
                           headers=owner_only_headers).status_code == 403
        pause_body = {"expected_revision_id": first.revision_id,
                      "expected_generation": first.attempt_run_id}
        assert client.post(f"/api/v1/workflows/runs/{first.workflow_run_id}/pause",
                           json=pause_body,
                           headers=_phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": monitor_csrf,
                                                   "Idempotency-Key": "phone-pause-denied"})).status_code == 403
        assert client.post(f"/api/v1/workflows/runs/{first.workflow_run_id}/resume",
                           json=pause_body,
                           headers=_phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": monitor_csrf,
                                                   "Idempotency-Key": "phone-resume-denied"})).status_code == 403

        client.cookies.set(SESSION_COOKIE, review["session_token"])
        review_csrf = store.auth_csrf_token(review["session_token"], review["session_id"])
        review_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": review_csrf,
                                         "Idempotency-Key": "phone-question-answer"})
        queue = client.get("/api/v1/phone/workflows/questions", headers=_phone_headers())
        assert queue.status_code == 200, queue.text
        first_question_ids = {item["id"] for item in queue.json()["items"]
                              if item["workflow_run_id"] == first.workflow_run_id}
        assert first_question_ids == {question["id"] for question in first_questions}
        question = next(item for item in queue.json()["items"] if item["id"] == first_question["id"])
        assert question["question"] == "Continue?" and question["options"] == ["yes", "no"]
        assert "instance_key" not in question and "PRIVATE_INPUT_SENTINEL" not in queue.text
        answer = client.post(f"/api/v1/phone/workflows/questions/{question['id']}/answer",
                             json={"answer": "yes"}, headers=review_headers)
        assert answer.status_code == 200, answer.text
        assert answer.json() == {"workflow_run_id": first.workflow_run_id, "status": "answered",
                                 "question_id": question["id"], "stop_requested": None}
        queue_after_partial_answer = client.get("/api/v1/phone/workflows/questions", headers=_phone_headers())
        assert {item["id"] for item in queue_after_partial_answer.json()["items"]
                if item["workflow_run_id"] == first.workflow_run_id} == first_question_ids - {question["id"]}
        stop_headers = _phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": review_csrf,
                                       "Idempotency-Key": "phone-workflow-stop"})
        stopped = client.post(f"/api/v1/phone/workflows/runs/{second.workflow_run_id}/stop",
                              json={"expected_revision_id": second.revision_id}, headers=stop_headers)
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["workflow_run_id"] == second.workflow_run_id
        assert stopped.json()["status"] in {"waiting", "stopped"}
        assert stopped.json()["stop_requested"] is True
        assert "PRIVATE_INPUT_SENTINEL" not in stopped.text


def test_remote_owner_token_is_rejected_but_local_owner_token_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "owner-secret")
    app = create_app()
    with TestClient(app, base_url="https://testserver") as client:
        remote = client.get("/api/bots", headers={"Host": "hutch.example", "Authorization": "Bearer owner-secret"})
        assert remote.status_code == 401
        remote_login = client.post("/login", data={"token": "owner-secret"},
                                   headers={"Host": "hutch.example", "Origin": "https://hutch.example"})
        assert remote_login.status_code == 403
    local_app = create_app()
    with TestClient(local_app, base_url="http://localhost") as local:
        owner = local.get("/api/v1/devices", headers={"Authorization": "Bearer owner-secret"})
        assert owner.status_code == 200


def test_remote_start_idempotency_is_scoped_to_credential_and_authority_precedes_replay(tmp_path, monkeypatch):
    from hutch.models import Bot, RunStatus

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="phone-starts", model="mock/demo", remote_start_enabled=True))
    first = _enroll_test_passkey(store, store.create_pairing_code(allow_start=True), "first phone")
    second = _enroll_test_passkey(store, store.create_pairing_code(allow_start=True), "second phone")
    # Keep the command queued so revocation and local opt-out boundaries can be inspected.
    app.state.engine.start_background = lambda: (None, threading.Event())

    with TestClient(app, base_url="https://testserver") as client:
        def start_as(session, key, *, model="", rehearse=False):
            client.cookies.clear()
            client.cookies.set(SESSION_COOKIE, session["session_token"])
            csrf = store.auth_csrf_token(session["session_token"], session["session_id"])
            body = {"bot": bot.name, "prompt": "inspect current work"}
            if model:
                body["model"] = model
            if rehearse:
                body["rehearse"] = True
            return client.post("/api/v1/tasks/runs", json=body,
                               headers=_phone_headers({"X-Hutch-Request": "1", "X-Hutch-CSRF": csrf,
                                                       "Idempotency-Key": key}))

        assert start_as(first, "override-key", model="mock/other").status_code == 403
        assert start_as(first, "rehearse-key", rehearse=True).status_code == 403
        first_response = start_as(first, "same-browser-key")
        assert first_response.status_code == 201, first_response.text
        replay = start_as(first, "same-browser-key")
        assert replay.status_code == 200 and replay.json()["replayed"]
        assert replay.json()["id"] == first_response.json()["id"]
        assert not {"workspace", "owner", "lease_owner", "lease_expires_at", "pgid", "origin",
                    "conversation_id", "parent_run_id"} & replay.json().keys()

        second_response = start_as(second, "same-browser-key")
        assert second_response.status_code == 201, second_response.text
        assert second_response.json()["id"] != first_response.json()["id"]
        assert not second_response.json()["replayed"]

        assert store.revoke_device_session(first["id"])
        assert store.get_run(first_response.json()["id"]).status is RunStatus.stopped
        assert store.get_run(second_response.json()["id"]).status is RunStatus.pending

        bot.remote_start_enabled = False
        store.upsert_bot(bot)
        assert store.get_run(second_response.json()["id"]).status is RunStatus.stopped
        denied_replay = start_as(second, "same-browser-key")
        assert denied_replay.status_code == 403


def test_paired_snapshot_and_change_feed_redact_conversation_metadata(tmp_path, monkeypatch):
    import asyncio
    from hutch.models import Bot
    from hutch.server.sse import resource_change_stream

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="phone-safe-roster", model="mock/demo"))
    cursor = store.list_resource_changes()["cursor"]
    secret_title = "private-conversation-title-should-not-leak"
    conversation, _ = store.create_conversation(bot.id, secret_title,
                                                idem_key="conversation-phone-safe",
                                                request_hash="conversation-phone-safe")
    phone = _enroll_test_passkey(store, store.create_pairing_code(), "monitor phone")

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(SESSION_COOKIE, phone["session_token"])
        snapshot_response = client.get("/api/v1/snapshot", headers={"Host": "hutch.example"})
        assert snapshot_response.status_code == 200
        snapshot = snapshot_response.json()
        assert snapshot["items"]["conversations"] == []
        assert snapshot["totals"]["conversations"] == 0
        assert snapshot["next"]["conversations"] is None
        assert secret_title not in snapshot_response.text and conversation["id"] not in snapshot_response.text

        page_response = client.get("/api/v1/changes", params={"cursor": cursor},
                                   headers={"Host": "hutch.example"})
        assert page_response.status_code == 200
        page = page_response.json()
        assert len(page["changes"]) == 1
        change = page["changes"][0]
        assert change["resource"] == change["resource_id"] == "state"
        assert change["operation"] == "updated" and change["context"] == {}
        assert secret_title not in page_response.text and conversation["id"] not in page_response.text

        async def read_phone_stream():
            stream = resource_change_stream(None, store, cursor,
                                            auth_check=lambda: bool(store.authenticate_session(phone["session_token"])),
                                            redact=True)
            try:
                assert await anext(stream) == b"retry: 1500\n\n"
                return await asyncio.wait_for(anext(stream), timeout=2)
            finally:
                await stream.aclose()

        event = asyncio.run(read_phone_stream())
    assert b'"resource":"state"' in event and b'"context":{}' in event
    assert secret_title.encode() not in event and conversation["id"].encode() not in event


def test_paired_run_stream_closes_when_credential_is_revoked(tmp_path, monkeypatch):
    import asyncio
    from hutch.models import Bot, Run
    from hutch.server.sse import run_event_stream

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = create_app()
    store = app.state.store
    bot = store.create_bot(Bot(name="stream-auth", model="mock/demo"))
    run = store.create_run(Run(bot_id=bot.id, prompt="wait for transcript"))
    phone = _enroll_test_passkey(store, store.create_pairing_code(), "stream phone")
    async def check_stream():
        stream = run_event_stream(None, store, run.id, 0, lambda _events, _run: {},
                                  auth_check=lambda: bool(store.authenticate_session(phone["session_token"])))
        assert await anext(stream) == b"retry: 1500\n\n"

        async def revoke_after_idle():
            await asyncio.sleep(0.05)
            await asyncio.to_thread(store.revoke_device_session, phone["id"])

        revoke = asyncio.create_task(revoke_after_idle())
        event = await asyncio.wait_for(anext(stream), timeout=2)
        await revoke
        assert b"event: auth_expired" in event
        assert b"session_expired_or_revoked" in event
        await stream.aclose()

    asyncio.run(check_stream())


def test_store_requires_start_capability_at_admission_and_claim_rechecks_races(store):
    import pytest
    from hutch.models import Bot, Run, RunStatus, Task

    bot = store.create_bot(Bot(name="store-phone-authority", remote_start_enabled=True))
    monitor = _enroll_test_passkey(store, store.create_pairing_code(), "monitor only")
    unauthorized = Run(bot_id=bot.id, prompt="must not queue", origin=f"remote:{monitor['id']}")
    with pytest.raises(PermissionError, match="authority"):
        store.submit_run_idempotent(unauthorized, Task(bot_id=bot.id, kind="on_demand", prompt=unauthorized.prompt),
                                    idem_key="monitor-start", request_hash="monitor-start")
    assert store.get_run(unauthorized.id) is None

    start = _enroll_test_passkey(store, store.create_pairing_code(allow_start=True), "start allowed")
    queued = Run(bot_id=bot.id, prompt="claim race", origin=f"remote:{start['id']}")
    task = Task(bot_id=bot.id, kind="on_demand", prompt=queued.prompt)
    stored, created = store.submit_run_idempotent(queued, task, idem_key="claim-race", request_hash="claim-race")
    assert created
    # Simulate revocation committing between enqueue and claim. The public revoke
    # path also cancels pending work eagerly; claim_run is the final admission fence.
    store._db.execute("UPDATE paired_credentials SET revoked_at=? WHERE id=?", (iso(utcnow()), start["id"]))
    store._db.commit()
    assert store.claim_run(stored.id, "dispatch-owner", 30) is None
    assert store.get_run(stored.id).status is RunStatus.stopped
    event = store.list_events(stored.id)[-1]
    assert event.type.value == "status"
    assert event.data.get("reason") == "remote_authority_revoked"


def test_remote_bind_requires_explicit_flag_and_tls_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    runner = CliRunner()
    blocked = runner.invoke(cli_app, ["serve", "--host", "0.0.0.0"])
    assert blocked.exit_code == 2 and "--allow-remote" in blocked.output

    no_tls = runner.invoke(cli_app, ["serve", "--host", "0.0.0.0", "--allow-remote"])
    assert no_tls.exit_code == 2 and "--tls-cert" in no_tls.output

    cert, key = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
    cert.write_text("test certificate placeholder")
    key.write_text("test key placeholder")
    for address in ("0.0.0.0", "::", "8.8.8.8"):
        refused = runner.invoke(cli_app, ["serve", "--host", address, "--allow-remote",
                                          "--tls-cert", str(cert), "--tls-key", str(key)])
        assert refused.exit_code == 2
        assert "private LAN or Tailscale address" in refused.output

    pairing = runner.invoke(cli_app, ["pairing", "create"])
    assert pairing.exit_code == 0 and "expires in 60 seconds" in pairing.output
    assert runner.invoke(cli_app, ["pairing", "list"]).exit_code == 0


def test_local_cli_launch_ignores_inherited_remote_enable_switch(monkeypatch):
    import uvicorn

    monkeypatch.setenv("HUTCH_EXECUTOR", "thread")
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    observed = {}

    def capture_launch(*_args, **_kwargs):
        observed["remote_enabled"] = os.environ.get("HUTCH_REMOTE_ENABLED")

    monkeypatch.setattr(uvicorn, "run", capture_launch)
    result = CliRunner().invoke(cli_app, ["serve", "--host", "127.0.0.1"])

    assert result.exit_code == 0, result.output
    assert observed["remote_enabled"] is None


def test_remote_cli_flag_sets_internal_switch_after_configuration_validation(monkeypatch):
    import uvicorn

    monkeypatch.setenv("HUTCH_EXECUTOR", "thread")
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "0")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    observed = {}

    def capture_launch(*_args, **_kwargs):
        observed["remote_enabled"] = os.environ.get("HUTCH_REMOTE_ENABLED")

    monkeypatch.setattr(uvicorn, "run", capture_launch)
    result = CliRunner().invoke(cli_app, ["serve", "--host", "127.0.0.1", "--allow-remote"])

    assert result.exit_code == 0, result.output
    assert observed["remote_enabled"] == "1"


def test_real_uvicorn_https_rejects_owner_token_and_ignores_forwarded_downgrade(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import uvicorn
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import httpx

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "owner-secret")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hutch.example")])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("hutch.example"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "tls.crt", tmp_path / "tls.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    cert_path.chmod(0o600)
    key_path.chmod(0o600)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    server = uvicorn.Server(uvicorn.Config(create_app, factory=True, host="127.0.0.1", port=port,
                                           ssl_certfile=str(cert_path), ssl_keyfile=str(key_path),
                                           proxy_headers=False, access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        tls_context = ssl.create_default_context(cafile=str(cert_path))
        with httpx.Client(verify=tls_context, trust_env=False, timeout=3) as client:
            pair = client.get(f"https://127.0.0.1:{port}/pair", headers={
                "Host": "hutch.example", "X-Forwarded-Proto": "http"})
            assert pair.status_code == 200, pair.text
            assert "secure" in pair.headers["set-cookie"].lower()
            refused = client.get(f"https://127.0.0.1:{port}/api/v1/session", headers={
                "Host": "hutch.example", "Authorization": "Bearer owner-secret"})
            assert refused.status_code == 401
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive()


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
        headers={**forwarded, "Origin": "http://hutch.example", "X-Hutch-Request": "1",
                 "Cookie": f"hutch_csrf={csrf}"})
    assert downgraded_origin.status_code == 403
    paired = proxy.post("/api/v1/pairing/exchange", json={"code": code, "label": "Phone"},
                        headers={**forwarded, "Origin": "https://hutch.example", "X-Hutch-Request": "1",
                                 "Cookie": f"hutch_csrf={csrf}"})
    assert paired.status_code == 200, paired.text
    assert "secure" in paired.headers["set-cookie"].lower()
    enrollment = paired.cookies.get("hutch_enroll")
    assert enrollment
    assert proxy.get("/api/bots", headers={**forwarded, "Cookie": f"hutch_enroll={enrollment}"}).status_code == 401


def test_trusted_tailscale_funnel_marker_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    proxy = TestClient(create_app(), base_url="http://hutch-origin.internal", client=("127.0.0.1", 43120))
    funnel_headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
                      "X-Forwarded-For": "198.51.100.42", "Tailscale-Funnel-Request": "?1"}

    assert proxy.get("/pair", headers=funnel_headers).status_code == 403
    assert proxy.get("/api/v1/health", headers=funnel_headers).status_code == 403
    # The same trusted proxy remains usable when the Tailscale Funnel marker is absent.
    assert proxy.get("/pair", headers={key: value for key, value in funnel_headers.items()
                                      if key != "Tailscale-Funnel-Request"}).status_code == 200


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
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    app = FastAPI()

    @app.get("/client")
    async def client_address(request: Request):
        return {"client": request.client.host}

    secured = SecurityMiddleware(app, device_auth=lambda token: {"kind": "paired"} if token == "phone-session" else None)
    client = TestClient(secured, base_url="http://origin.internal", client=("127.0.0.1", 43120))
    response = client.get("/client", headers={
        "X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
        "X-Forwarded-For": "198.51.100.42", "Cookie": "hutch_session=phone-session"})
    assert response.status_code == 200
    assert response.json() == {"client": "198.51.100.42"}


def test_trusted_proxy_requires_passkey_session_and_local_owner_token_is_not_remote_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "operator-token")
    monkeypatch.setenv("HUTCH_TRUSTED_PROXIES", "127.0.0.1/32")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "hutch.example",
               "Authorization": "Bearer operator-token"}
    with TestClient(create_app(), base_url="http://localhost", client=("127.0.0.1", 43120)) as client:
        login = client.get("/login", headers={k: v for k, v in headers.items() if k != "Authorization"})
        assert login.status_code == 200
        refused = client.get("/api/v1/session", headers=headers)
        assert refused.status_code == 401


def test_trusted_proxy_websocket_is_disabled_even_for_authenticated_phone(monkeypatch):
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
    try:
        with client.websocket_connect("/ws", headers=headers):
            raise AssertionError("remote websocket was accepted")
    except WebSocketDisconnect as exc:
        assert exc.code == 4403

    downgraded = {**headers, "Origin": "http://hutch.example"}
    try:
        with client.websocket_connect("/ws", headers=downgraded):
            raise AssertionError("proxied socket accepted an HTTP Origin for an HTTPS page")
    except WebSocketDisconnect as exc:
        assert exc.code == 4403
