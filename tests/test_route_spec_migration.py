"""Saved model routes keep their meaning when the implicit provider prefix is written."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from hutch import route_spec_schema
from hutch.store import SCHEMA_VERSION, Store

FIXTURE = Path(__file__).parent / "fixtures" / "state_v4.db.fixture"
BRIEFING = "bot_7eef563ee683"


@pytest.fixture()
def v4(config):
    config.ensure()
    shutil.copy(FIXTURE, config.db_path)
    return config


def test_saved_routes_gain_an_explicit_provider_prefix_without_changing_meaning():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY, doc TEXT NOT NULL)")
        legacy = {"name": "legacy", "model": "gpt-x",
                  "fallbacks": ["llama3.2", "anthropic/claude"],
                  "escalation": {"to": ["opus"]},
                  "task_routes": {"author": "author-model"}}
        explicit = {"name": "explicit", "model": "ollama/llama3.2", "fallbacks": ["xai/grok"]}
        db.execute("INSERT INTO bots VALUES (?, ?)", ("legacy", json.dumps(legacy)))
        db.execute("INSERT INTO bots VALUES (?, ?)", ("explicit", json.dumps(explicit)))
        route_spec_schema.migrate(db)
        route_spec_schema.migrate(db)
        got = json.loads(db.execute("SELECT doc FROM bots WHERE id='legacy'").fetchone()[0])
        assert got["model"] == "openai-compatible/gpt-x"
        assert got["fallbacks"] == ["openai-compatible/llama3.2", "anthropic/claude"]
        assert got["escalation"]["to"] == ["openai-compatible/opus"]
        assert got["task_routes"] == {"author": "openai-compatible/author-model"}
        kept = json.loads(db.execute("SELECT doc FROM bots WHERE id='explicit'").fetchone()[0])
        assert kept == explicit
        assert SCHEMA_VERSION >= 82
    finally:
        db.close()


def test_upgrade_keeps_an_already_explicit_saved_route_unchanged(v4):
    store = Store(v4)
    try:
        bots = {bot.id: bot for bot in store.list_bots()}
        assert all("/" in bot.model for bot in bots.values())
        assert bots[BRIEFING].model == "mock/demo"
    finally:
        store.close()
