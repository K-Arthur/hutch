"""Budget policy API, preflight provenance, and compaction manifests in run detail (SR-2/LM-3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.store = c.app.state.store
        c.config = c.app.state.config
        yield c


def test_budget_policy_round_trip_and_validation(client):
    bot = client.store.create_bot(Bot(name="budget-api-bot", model="mock/demo"))
    created = client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id,
                                                  "warn_usd": 0.05, "pause_usd": 0.10, "ceiling_usd": 0.15})
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 1

    fetched = client.get("/api/v1/budgets", params={"scope_kind": "bot", "scope_id": bot.id}).json()
    assert fetched["policy"]["warn_usd"] == 0.05 and fetched["policy"]["ceiling_usd"] == 0.15
    assert fetched["spent_usd"] == 0.0 and fetched["held_usd"] == 0.0

    updated = client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id,
                                                  "warn_usd": 0.05, "pause_usd": 0.10, "ceiling_usd": 0.20})
    assert updated.json()["revision"] == 2

    zero = client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id, "ceiling_usd": 0})
    assert zero.status_code == 200 and zero.json()["ceiling_usd"] == 0.0  # a real threshold of zero

    bad_order = client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id,
                                                    "warn_usd": 0.3, "pause_usd": 0.2})
    assert bad_order.status_code == 422
    bad_scope = client.put("/api/v1/budgets", json={"scope_kind": "run", "scope_id": "run_missing",
                                                    "ceiling_usd": 1.0})
    assert bad_scope.status_code == 422
    negative = client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id, "warn_usd": -1})
    assert negative.status_code == 422

    removed = client.delete("/api/v1/budgets", params={"scope_kind": "bot", "scope_id": bot.id})
    assert removed.json() == {"removed": True}
    assert client.get("/api/v1/budgets", params={"scope_kind": "bot", "scope_id": bot.id}).json()["policy"] is None


def test_estimate_carries_quote_provenance_and_scope_budget(client):
    from hutch.providers.pricing import PriceBook
    priced_spec = PriceBook().rows()[0].model
    bot = client.store.create_bot(Bot(name="preflight-bot", model=priced_spec))
    client.put("/api/v1/budgets", json={"scope_kind": "bot", "scope_id": bot.id, "warn_usd": 0.5})

    estimate = client.get(f"/api/bots/{bot.id}/estimate").json()
    assert estimate["price_source"] == "price_file"
    assert estimate["price_verified_on"]
    assert estimate["next_call_usd"] is not None and estimate["next_call_usd"] > 0
    assert estimate["message_tokens"] > 0 and estimate["tool_tokens"] > 0
    assert estimate["budget_scope"] == "bot" and estimate["budget_scope_id"] == bot.id
    assert estimate["warn_usd"] == 0.5 and estimate["ceiling_usd"] is None

    unpriced = client.store.create_bot(Bot(name="unpriced-bot", model="openai/gpt-unpriced"))
    un = client.get(f"/api/bots/{unpriced.id}/estimate").json()
    assert un["price_source"] == "unknown" and un["next_call_usd"] is None and un["kind"] == "unpriced"
    assert "No price on file" in un["summary"]


def test_run_detail_exposes_compaction_manifests(client):
    bot = client.store.create_bot(Bot(name="compaction-bot", model="mock/demo"))
    run = client.store.create_run(Run(bot_id=bot.id, prompt="compact me"))
    client.store.record_compaction(run_id=run.id, reason="context overflow", destination="ollama/fake:8b",
                                   before_tokens=12_000, after_tokens=4_000, attempts=1, status="compacted",
                                   dropped_units=3, kept_units=2, input_digest="a" * 64,
                                   summary_digest="b" * 32, summary_text="summary text")
    detail = client.get(f"/api/runs/{run.id}").json()
    assert len(detail["compactions"]) == 1
    entry = detail["compactions"][0]
    assert entry["status"] == "compacted" and entry["before_tokens"] == 12_000 and entry["after_tokens"] == 4_000
    assert entry["summary_text"] == "summary text"
