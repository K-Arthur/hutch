"""Server-rendered dashboard (UI-1..6, UI-12) and its security posture."""

from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

from hutch.models import ApprovalMode, ApprovalRequest, Bot, Event, EventType, Run, RunStatus, iso, utcnow
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        c.app_ = app
        yield c


def token(client) -> str:
    html = client.get("/connections").text
    return re.search(r'<meta name="csrf" content="([^"]+)"', html).group(1)


def post(client, path, **data):
    data.setdefault("csrf", token(client))
    return client.post(path, data=data, follow_redirects=False)


def make_bot(client, name="dash-bot", **kw):
    store = client.app_.state.store
    bot = Bot(name=name, model="mock/demo", approval_mode=ApprovalMode.ask, tools=["files", "shell", "memory"], **kw)
    return store.create_bot(bot)


def wait_for(fn, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


# ------------------------------------------------------------------ pages render

def test_retired_pages_redirect_to_the_studio(client):
    for path in ("/overview", "/bots", "/bots/new", "/runs", "/approvals"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].startswith("/#/"), path
    assert client.get("/").status_code == 200          # the app home is the chat studio
    for path in ("/_home", "/_badge"):
        assert client.get(path).status_code == 200, path


def test_pages_are_server_rendered_with_htmx_and_no_build_step(client):
    html = client.get("/connections").text
    assert "/static/vendor/htmx.min.js" in html and "/static/hutch.js" in html
    assert client.get("/static/vendor/htmx.min.js").status_code == 200
    assert "<script" in html and "node_modules" not in html


def test_overview_api_has_the_three_questions(client):
    make_bot(client)
    d = client.get("/api/overview").json()
    assert {"approvals", "running", "stale", "stats", "needs_count"} <= set(d)


def test_unknown_page_is_a_helpful_404_not_a_stack_trace(client):
    r = client.get("/bots/nope", headers={"accept": "text/html"})
    assert r.status_code == 404 and "No bot named" in r.text


def test_legacy_spa_stays_reachable(client):
    assert client.get("/legacy/").status_code == 200


def test_home_is_the_chat_studio(client):
    """The app opens into the chat interface (Grok-bot style), not the triage dashboard."""
    html = client.get("/").text
    assert "/static/app.js" in html and "/static/style.css" in html
    assert 'id="view"' in html


# ------------------------------------------------------------------ approvals (UI-5)

def seed_pending_shell_approval(client):
    store = client.app_.state.store
    bot = make_bot(client)
    run = store.create_run(Run(bot_id=bot.id, prompt="tidy up", status=RunStatus.waiting_approval))
    from hutch.safety import PolicyEngine
    d = PolicyEngine().check_shell("git status && rm -rf build/")
    req = store.create_approval(ApprovalRequest(
        run_id=run.id, bot_id=bot.id, tool="shell", action="$ git status && rm -rf build/",
        detail={"command": "git status && rm -rf build/"}, sticky_key=d.sticky_key, segments=d.segments,
        rule=d.rule, risk=d.risk, outward=d.outward, expires_at=iso(utcnow().replace(microsecond=0)
        + __import__("datetime").timedelta(seconds=300))))
    return bot, run, req


def test_approval_card_shows_segments_rule_choices_and_countdown(client):
    _, _, req = seed_pending_shell_approval(client)
    html = client.get("/_approvals").text
    assert "Parsed into 2 segments" in html
    assert "git status" in html and "rm -rf build/" in html
    assert "ask:rm" in html                                   # the rule that fired
    for label in ("Allow once", "Always for this bot", "Deny"):
        assert label in html
    assert "data-countdown-to" in html and "denies in" in html


def test_deciding_once_always_and_deny_over_plain_post(client):
    store = client.app_.state.store
    bot, run, req = seed_pending_shell_approval(client)
    r = post(client, f"/approvals/{req.id}/decide", choice="always", next="/approvals")
    assert r.status_code == 303
    assert store.get_approval(req.id).status.value == "approved"
    assert store.is_sticky_allowed(bot.id, "shell:rm")
    # a second decision is refused politely, not applied twice
    r2 = post(client, f"/approvals/{req.id}/decide", choice="deny", next="/approvals")
    assert store.get_approval(req.id).status.value == "approved"

    run2 = store.create_run(Run(bot_id=bot.id, prompt="again", status=RunStatus.waiting_approval))
    req2 = store.create_approval(ApprovalRequest(run_id=run2.id, bot_id=bot.id, tool="files", action="write x"))
    post(client, f"/approvals/{req2.id}/decide", choice="deny")
    assert store.get_approval(req2.id).status.value == "denied"


def test_htmx_decision_swaps_the_card_in_place(client):
    _, _, req = seed_pending_shell_approval(client)
    r = client.post(f"/approvals/{req.id}/decide", data={"csrf": token(client), "choice": "once"},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200 and "Allowed" in r.text and "<html" not in r.text


def test_outward_actions_never_offer_always(client):
    store = client.app_.state.store
    bot = make_bot(client)
    run = store.create_run(Run(bot_id=bot.id, prompt="deploy", status=RunStatus.waiting_approval))
    req = store.create_approval(ApprovalRequest(
        run_id=run.id, bot_id=bot.id, tool="shell", action="$ git push origin main", sticky_key="shell:git",
        outward=True, risk="high", rule="ask:git-push"))
    html = client.get("/_approvals").text
    assert "Always for this bot" not in html and "outward" in html
    post(client, f"/approvals/{req.id}/decide", choice="always")
    assert not store.is_sticky_allowed(bot.id, "shell:git")     # even a forged 'always' is ignored


# ------------------------------------------------------------------ stop / controls (UI-2)

def test_stop_all_is_in_the_app_header_and_stops_a_run(client):
    bot = make_bot(client)
    assert "/stop-all" in client.get("/connections").text
    assert "/stop-all" not in client.get("/login").text
    store, engine = client.app_.state.store, client.app_.state.engine
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    r = post(client, "/stop-all", next="/")
    assert r.status_code == 303
    wait_for(lambda: store.get_run(run.id).status is RunStatus.stopped)


def test_per_run_stop_form_is_a_plain_post(client):
    bot = make_bot(client)
    store, engine = client.app_.state.store, client.app_.state.engine
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    post(client, f"/runs/{run.id}/stop")
    wait_for(lambda: store.get_run(run.id).status is RunStatus.stopped)


# ------------------------------------------------------------------ run page: waits, meters, pagination

def test_waiting_run_page_names_cause_and_fix(client):
    bot = make_bot(client)
    store, engine = client.app_.state.store, client.app_.state.engine
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    wait = client.get(f"/runs/{run.id}/wait")
    assert "Why:" in wait.text and "What to do:" in wait.text
    meters = client.get(f"/runs/{run.id}/meters")                       # UI-4 meters
    assert "Steps" in meters.text and "Elapsed" in meters.text and "Spend" in meters.text and "Context" in meters.text
    client.app_.state.engine.stop_all()


def test_failed_run_page_explains_the_failure(client):
    bot = make_bot(client)
    store = client.app_.state.store
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.failed, exit_reason="steps_exceeded",
                               finished_at=iso(utcnow())))
    html = client.get(f"/runs/{run.id}/wait").text
    assert "used all 24 steps" in html and "max_steps" in html


def test_ten_thousand_event_run_page_is_paginated_and_fast(client):
    bot = make_bot(client)
    store = client.app_.state.store
    run = store.create_run(Run(bot_id=bot.id, prompt="long", status=RunStatus.succeeded,
                               finished_at=iso(utcnow())))
    for i in range(10_000):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"note": f"step {i}"}))
    store.flush_events()
    t0 = time.perf_counter()
    r = client.get(f"/runs/{run.id}", follow_redirects=False)
    dt = time.perf_counter() - t0
    assert r.status_code == 302 and dt < 1.5        # retired: the studio owns run detail now
    older = client.get(f"/runs/{run.id}/events?before=9801")
    assert older.status_code == 200 and older.text.count('data-seq="') == 200
    assert 'data-seq="9601"' in older.text and 'data-seq="9800"' in older.text
    assert "tx-more" in older.text                                  # and a further 'load earlier'
    api = client.get(f"/api/runs/{run.id}").json()
    assert len(api["events"]) == 200 and api["event_count"] == 10_000 and api["events_truncated"]


# ------------------------------------------------------------------ security (CSRF, DNS rebinding)

def test_post_without_csrf_token_is_refused(client):
    r = client.post("/stop-all", data={"next": "/"}, follow_redirects=False)
    assert r.status_code == 403 and "CSRF" in r.text


def test_cross_site_post_is_refused_even_with_a_valid_token(client):
    t = token(client)
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
        r = client.post("/stop-all", data={"csrf": t}, headers=headers, follow_redirects=False)
        assert r.status_code == 403, headers
    ok = client.post("/stop-all", data={"csrf": t}, headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert ok.status_code == 303


def test_cross_site_post_to_the_json_api_is_refused_too(client):
    make_bot(client)
    r = client.post("/api/stop-all", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/stop-all").status_code == 200       # curl / scripts / the CLI are unaffected


def test_unexpected_host_header_is_refused_dns_rebinding(client):
    r = client.get("/", headers={"Host": "attacker.example:8787"})
    assert r.status_code == 421 and "unexpected Host" in r.text
    assert client.get("/", headers={"Host": "127.0.0.1:8787"}).status_code == 200
    assert client.get("/", headers={"Host": "localhost:8787"}).status_code == 200
    assert client.get("/", headers={"Host": "[::1]:8787"}).status_code == 200


def test_open_redirect_via_next_is_ignored(client):
    r = post(client, "/stop-all", next="https://evil.example/")
    assert r.status_code == 303 and r.headers["location"] == "/"
    r = post(client, "/stop-all", next="//evil.example")
    assert r.headers["location"] == "/"


def test_flash_messages_cannot_be_injected_through_a_url(client):
    html = client.get("/?notice=Your+hutch+is+compromised").text
    assert "compromised" not in html


def test_auth_token_gates_everything_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_AUTH_TOKEN", "s3cret-token")
    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200                      # health stays open
        assert c.get("/api/bots").status_code == 401
        assert c.get("/", headers={"accept": "text/html"}, follow_redirects=False).status_code == 303
        assert c.get("/api/bots", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
        t = re.search(r'<meta name="csrf" content="([^"]+)"', c.get("/login").text).group(1)
        bad = c.post("/login", data={"csrf": t, "token": "wrong"}, follow_redirects=False)
        assert bad.headers["location"] == "/login"
        good = c.post("/login", data={"csrf": t, "token": "s3cret-token"}, follow_redirects=False)
        assert good.status_code == 303 and good.headers["location"] == "/"
        assert c.get("/").status_code == 200                                # cookie now authenticates
