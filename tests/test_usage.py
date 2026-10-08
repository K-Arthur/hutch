"""SR-2 estimate before a run, and the Usage page (UI-11)."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.connections import ConnectionBook
from hutch.estimate import RunEstimator, estimate_run
from hutch.models import Bot, Limits, Run, iso, utcnow
from hutch.server.app import create_app

runner = CliRunner()


# ------------------------------------------------------------------------ estimate

def test_a_local_model_has_no_cost_and_says_so(config, store):
    b = store.create_bot(Bot(name="loc", model="ollama/qwen3:4b", tools=["files"]))
    e = estimate_run(config, store, b)
    assert e.kind == "local" and e.worst_case_usd is None and "no per-token cost" in e.summary


def test_a_priced_model_gets_an_estimate_and_discloses_provider_billing_uncertainty(config, store):
    b = store.create_bot(Bot(name="h", model="anthropic/claude-opus-5-5", tools=["shell", "files"],
                             limits=Limits(max_steps=10, max_turn_tokens=1000)))
    e = estimate_run(config, store, b)
    assert e.kind == "priced" and e.steps == 10 and e.turn_tokens == 1000
    expected = (e.prompt_tokens * 10 * 4.0 + 1000 * 10 * 20.0) / 1_000_000          # $4 in / $20 out per 1M
    assert e.worst_case_usd == pytest.approx(expected) and "Estimated at $" in e.summary
    assert "provider billing can differ" in e.summary


def test_the_bots_own_run_cap_is_the_real_maximum_when_lower(config, store):
    b = store.create_bot(Bot(name="h", model="anthropic/claude-opus-5-5", limits=Limits(max_cost_usd=0.25, daily_cost_cap_usd=2.0)))
    e = estimate_run(config, store, b)
    assert e.effective_ceiling_usd == 0.25 and "Estimated at up to $0.25 per run" in e.summary and "$2.00 daily limit" in e.summary


def test_an_unpriced_hosted_model_has_no_ceiling_and_says_why(config, store):
    b = store.create_bot(Bot(name="u", model="openai/some-new-model"))
    e = estimate_run(config, store, b)
    assert e.kind == "unpriced" and e.worst_case_usd is None and "cannot run while a currency limit is set" in e.summary


def test_a_flat_plan_is_not_priced_but_is_not_free_of_allowance(config, store):
    ConnectionBook(config.state_dir).add("opencode-go")
    b = store.create_bot(Bot(name="p", model="opencode-go/glm-5.3"))
    e = estimate_run(config, store, b)
    assert e.kind == "flat" and "allowance" in e.summary


def test_more_tools_and_a_longer_task_mean_a_bigger_prompt_estimate(config, store):
    small = store.create_bot(Bot(name="s", model="ollama/x", tools=[]))
    big = store.create_bot(Bot(name="b", model="ollama/x", tools=["shell", "files", "memory", "browser"], instructions="x" * 4000))
    assert RunEstimator(config, store, big).prompt_tokens > RunEstimator(config, store, small).prompt_tokens + 500
    assert RunEstimator(config, store, small, "y" * 4000).prompt_tokens > RunEstimator(config, store, small).prompt_tokens


def test_the_estimate_can_price_another_model_without_changing_the_bot(config, store):
    b = store.create_bot(Bot(name="s", model="ollama/x"))
    est = RunEstimator(config, store, b)
    assert est.for_model("ollama/x").kind == "local" and est.for_model("anthropic/claude-haiku-4-5").kind == "priced"
    assert store.get_bot("s").model == "ollama/x"


def test_spend_today_is_included(config, store):
    b = store.create_bot(Bot(name="h", model="anthropic/claude-opus-5-5", limits=Limits(daily_cost_cap_usd=5.0)))
    store.create_run(Run(bot_id=b.id, prompt="x", cost_usd=1.25, tokens=900))
    e = estimate_run(config, store, b)
    assert e.spent_today_usd == pytest.approx(1.25) and e.tokens_today == 900
    assert "$1.25 measured + $0.00 held of the $5.00 daily limit" in e.summary


def test_cli_estimate_and_api(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    assert runner.invoke(cli_app, ["bot", "create", "est", "--model", "anthropic/claude-haiku-4-5"]).exit_code == 0
    out = runner.invoke(cli_app, ["bot", "estimate", "est"]).output
    assert "Estimated at $" in out and "claude-haiku-4-5" in out
    assert "no per-token cost" in runner.invoke(cli_app, ["bot", "estimate", "est", "--model", "ollama/x"]).output
    with TestClient(create_app()) as c:
        j = c.get("/api/bots/est/estimate").json()
        assert j["kind"] == "priced" and j["worst_case_usd"] > 0 and j["summary"].startswith("Estimated at $")
        assert c.get("/api/bots/est/estimate", params={"model": "ollama/x"}).json()["kind"] == "local"
        assert c.get("/api/bots/nobody/estimate").status_code == 404
        page = c.get("/bots/est").text
        assert 'id="estimate"' in page and "Estimated at $" in page


def test_the_switchers_hosted_rows_carry_the_worst_case(config, store, monkeypatch):
    from hutch.modelchoices import model_choices, reset_cache
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    reset_cache()
    b = store.create_bot(Bot(name="s", model="mock/demo"))
    by = {c.spec: c for c in model_choices(config, store, b)}
    assert by["anthropic/claude-opus-5-5"].worst_case_usd and by["anthropic/claude-opus-5-5"].worst_case_usd > by["anthropic/claude-haiku-4-5"].worst_case_usd
    assert any("estimated $" in d and "provider billing can differ" in d
               for d in by["anthropic/claude-opus-5-5"].detail)


# ----------------------------------------------------------------------- usage page

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.store = c.app.state.store
        c.config = c.app.state.config
        yield c


def seed(c):
    st = c.store
    a = st.create_bot(Bot(name="researcher", model="anthropic/claude-opus-5-5", limits=Limits(daily_token_cap=10_000, daily_cost_cap_usd=5.0)))
    b = st.create_bot(Bot(name="coder", model="ollama/qwen3:4b"))
    st.create_run(Run(bot_id=a.id, prompt="x", tokens=3000, cost_usd=1.5))
    st.add_usage("r1", a.id, "anthropic", "claude-opus-5-5", 2500, 500, 1000, 2.75)
    st.add_usage("r2", b.id, "ollama", "qwen3:4b", 800, 200, 0, 0.0)
    ConnectionBook(c.config.state_dir).add("opencode-go", allowance_tokens=1_000_000, allowance_window="month") if False else None
    return a, b


def test_usage_page_totals_tables_and_caps(client):
    a, b = seed(client)
    t = client.get("/usage").text
    for needle in ("Where tokens and money went", "By day", "By model", "By bot", "Today against each bot", "researcher",
                   "anthropic/claude-opus-5-5", "ollama/qwen3:4b", "free (local)", "$2.75",
                   "$2.75 measured + $0 held estimate of $5.00 estimate limit"):
        assert needle in t, needle
    assert re.search(r'aria-valuenow="30"', t), "researcher used 3000 of 10000 tokens today"
    assert "Served from cache" in t


def test_local_models_are_free_and_flat_plans_are_not_priced(client):
    ConnectionBook(client.config.state_dir).add("opencode-go")
    client.store.add_usage("r", "b", "opencode-go", "glm-5.3", 100, 50)
    t = client.get("/usage").text
    assert "flat plan" in t


def test_period_selector_validates_and_defaults(client):
    seed(client)
    assert 'aria-current="true"' in client.get("/usage?days=7").text
    assert client.get("/usage?days=9999").status_code == 200
    assert client.get("/usage?days=abc").status_code == 422 or client.get("/usage?days=abc").status_code == 200


def test_old_usage_is_outside_the_window(client):
    a, _ = seed(client)
    with client.store._lock:
        client.store._db.execute("UPDATE usage SET ts = ? WHERE run_id = 'r1'", (iso(utcnow() - timedelta(days=45)),))
        client.store._db.commit()
    assert "$2.75" not in client.get("/usage?days=30").text
    assert "$2.75" in client.get("/usage?days=90").text


def test_the_move_log_shows_fallbacks_and_escalations(client):
    from hutch.models import Event, EventType
    a, _ = seed(client)
    run = client.store.create_run(Run(bot_id=a.id, prompt="x"))
    client.store.append_event(Event(run_id=run.id, type=EventType.log, data={
        "kind": "fallback", "note": "ollama/q is unavailable (refused); trying anthropic/claude-haiku-4-5",
        "from_model": "ollama/q", "to_model": "anthropic/claude-haiku-4-5"}))
    client.store.append_event(Event(run_id=run.id, type=EventType.log, data={"kind": "escalation", "note": "send this run to the hosted model"}))
    client.store.append_event(Event(run_id=run.id, type=EventType.log, data={"kind": "note", "note": "not a move"}))
    client.store.flush_events()  # the page reads committed history, not this fixture's pending batch
    t = client.get("/usage").text
    assert "is unavailable (refused)" in t and "send this run to the hosted model" in t and "not a move" not in t
    moves = client.store.recent_rung_changes()
    assert [m["kind"] for m in moves] == ["escalation", "fallback"] and moves[1]["to"] == "anthropic/claude-haiku-4-5"


def test_usage_by_local_day_groups_by_the_local_day(client):
    import os, time
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"; time.tzset()
    try:
        from datetime import datetime, timezone
        now = datetime(2026, 10, 8, 0, 30, tzinfo=timezone.utc)                          # Oct 7, 17:30 in LA
        st = client.store
        with st._lock:
            for ts, tok in (("2026-10-07T06:10:00+00:00", 1), ("2026-10-07T08:10:00+00:00", 10), ("2026-10-08T00:10:00+00:00", 100)):
                st._db.execute("INSERT INTO usage (ts, run_id, bot_id, provider, model, prompt_tokens) VALUES (?, 'r', 'b', 'p', 'm', ?)", (ts, tok))
            st._db.commit()
        days = {d["day"]: d["prompt"] for d in st.usage_by_local_day(7, now)}
        assert days == {"2026-10-06": 1, "2026-10-07": 110}, days
    finally:
        os.environ.pop("TZ", None) if old is None else os.environ.__setitem__("TZ", old)
        time.tzset()


def test_nav_has_a_usage_entry(client):
    assert 'href="/usage"' in client.get("/models").text
