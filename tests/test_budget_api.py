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


def test_preflight_estimates_the_selected_task_route_and_respects_model_override(client):
    bot = client.store.create_bot(Bot(name="task-route-preflight", model="ollama/fake:8b",
                                      task_routes={"code_analysis": "ollama/tiny:1b"}))
    url = f"/api/bots/{bot.id}/estimate"
    routed = client.get(url, params={"task_role": "code_analysis"}).json()
    assert routed["spec"] == "ollama/tiny:1b" and routed["price_source"] == "local"
    overridden = client.get(url, params={"task_role": "code_analysis", "model": "ollama/other:3b"}).json()
    assert overridden["spec"] == "ollama/other:3b" and overridden["price_source"] == "local"


def test_composer_preflight_estimates_current_draft_and_bounded_context_without_url_prompt(client):
    from hutch.models import iso, utcnow

    bot = client.store.create_bot(Bot(name="draft-preflight", model="ollama/fake:8b"))
    conversation, _ = client.store.create_conversation(bot.id, "Draft context", idem_key="draft-context",
                                                       request_hash="draft-context")
    with client.store._tx() as db:
        client.store._insert_conversation_message(
            db, message_id="draft-history", conversation_id=conversation["id"], seq=1, run_id="history-run",
            role="user", content="Earlier constraint: preserve the public API.", created_at=iso(utcnow()))
        client.store._insert_conversation_message(
            db, message_id="draft-reply", conversation_id=conversation["id"], seq=2, run_id="reply-run",
            role="assistant", content="Keep the compatibility layer intact.", created_at=iso(utcnow()))

    preview_context = client.store.preview_conversation_context(
        conversation["id"], reply_to_message_id="draft-reply")
    assert preview_context[0]["content"] == "Earlier constraint: preserve the public API."
    assert "Keep the compatibility layer intact." in preview_context[-1]["content"]
    assert "untrusted conversation content" in preview_context[-1]["content"]

    baseline = client.get(f"/api/bots/{bot.id}/estimate", params={"conversation_id": conversation["id"]}).json()
    preview = client.post(f"/api/bots/{bot.id}/estimate", json={
        "conversation_id": conversation["id"],
        "prompt": "Review the complete repository diff and preserve every public compatibility guarantee. " * 20,
        "reply_to_message_id": "draft-reply",
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["message_tokens"] > baseline["message_tokens"]
    assert preview.json()["spec"] == "ollama/fake:8b"
    assert client.post(f"/api/bots/{bot.id}/estimate", json={
        "conversation_id": conversation["id"], "prompt": "test", "reply_to_message_id": "foreign-message",
    }).status_code == 422


def test_composer_preflight_cannot_read_another_bots_conversation(client):
    first = client.store.create_bot(Bot(name="preflight-owner-a", model="ollama/fake:8b"))
    second = client.store.create_bot(Bot(name="preflight-owner-b", model="ollama/fake:8b"))
    conversation, _ = client.store.create_conversation(first.id, "Private", idem_key="private-preflight",
                                                       request_hash="private-preflight")
    response = client.post(f"/api/bots/{second.id}/estimate", json={
        "conversation_id": conversation["id"], "prompt": "do not leak context",
    })
    assert response.status_code == 404


def test_composer_preflight_counts_selected_skill_instructions_and_tool_schema(client):
    from tests.test_skills_api import install_builtin

    install_builtin(client, name="workspace-summary")
    install_builtin(client, name="repo-review")
    plain_bot = client.store.create_bot(Bot(name="plain-preflight", model="ollama/fake:8b"))
    plain_conversation, _ = client.store.create_conversation(plain_bot.id, "Plain preflight", idem_key="plain-preflight",
                                                            request_hash="plain-preflight")
    bot = client.store.create_bot(Bot(name="skill-preflight", model="ollama/fake:8b",
                                      skills=["workspace-summary"]))
    conversation, _ = client.store.create_conversation(bot.id, "Skill preflight", idem_key="skill-preflight",
                                                       request_hash="skill-preflight")
    plain = client.post(f"/api/bots/{plain_bot.id}/estimate", json={
        "conversation_id": plain_conversation["id"], "prompt": "Summarize this folder."}).json()
    url = f"/api/bots/{bot.id}/estimate"
    selected = client.post(url, json={"conversation_id": conversation["id"],
                                      "prompt": "Summarize this folder.",
                                      "skills": ["workspace-summary"], "rehearse": True})
    assert selected.status_code == 200, selected.text
    selected = selected.json()
    assert selected["message_tokens"] > plain["message_tokens"]
    assert selected["tool_tokens"] > plain["tool_tokens"]
    invalid = client.post(url, json={"conversation_id": conversation["id"], "prompt": "test",
                                    "skills": ["repo-review"]})
    assert invalid.status_code == 422 and "not assigned" in invalid.json()["detail"]


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
