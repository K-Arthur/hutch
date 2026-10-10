"""Dashboard roster must use a constant SQL budget as bot count grows (no nested all-bot scans)."""

from __future__ import annotations

import sqlite3

from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.store import Store


class _CountingConnection:
    def __init__(self, real: sqlite3.Connection):
        self._real = real
        self.n = 0

    def execute(self, *a, **k):
        self.n += 1
        return self._real.execute(*a, **k)

    def executemany(self, *a, **k):
        self.n += 1
        return self._real.executemany(*a, **k)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _seed(store: Store, n: int) -> None:
    for i in range(n):
        bot = store.create_bot(Bot(
            name=f"scale-{i:04d}", model="mock/demo", tools=["files"],
            approval_mode=ApprovalMode.auto,
        ))
        if i % 4 == 0:
            store.create_run(Run(bot_id=bot.id, prompt="queued"))
        if i % 7 == 0:
            store.create_run(Run(bot_id=bot.id, prompt="done", status=RunStatus.succeeded))


def test_bot_stats_is_one_grouped_scan(store: Store):
    _seed(store, 12)
    stats = store.bot_stats()
    assert len(stats) == 12
    assert any(v["counts"] for v in stats.values())
    # Zero-count bots stay present.
    empty = [bid for bid, v in stats.items() if not v["counts"]]
    assert empty


def test_roster_aggregates_sql_stays_flat_as_bots_grow(config, tmp_path, monkeypatch):
    """SQL for roster_aggregates must not grow with N²."""
    counts: dict[int, int] = {}
    for n in (10, 50, 100):
        monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / f"n{n}"))
        from hutch.config import get_config
        cfg = get_config()
        store = Store(cfg)
        _seed(store, n)
        counter = _CountingConnection(store._db)
        store._db = counter
        counter.n = 0
        agg = store.roster_aggregates()
        assert len(agg["stats"]) == n
        counts[n] = counter.n
        store.close()
    # Constant-ish: 100 bots must not cost ~100× the 10-bot query count.
    assert counts[100] < counts[10] * 4
    assert counts[100] < 80


def test_runs_bot_status_index_used_for_grouped_counts(store: Store):
    _seed(store, 5)
    plan = store._db.execute(
        "EXPLAIN QUERY PLAN SELECT bot_id, status, COUNT(*) FROM runs GROUP BY bot_id, status"
    ).fetchall()
    detail = " ".join(str(row[-1]) for row in plan).lower()
    assert "runs" in detail
    # Prefer the covering (bot_id, status) index when present.
    assert "idx_runs_bot_status" in detail or "using index" in detail or "using covering index" in detail


def test_active_run_for_bot_does_not_scan_all_live_runs(store: Store):
    bots = [store.create_bot(Bot(name=f"ar-{i}", model="mock/demo", tools=[],
                                 approval_mode=ApprovalMode.auto)) for i in range(8)]
    for bot in bots:
        store.create_run(Run(bot_id=bot.id, prompt="x"))
    counter = _CountingConnection(store._db)
    store._db = counter
    counter.n = 0
    store.active_run_for_bot(bots[0].id)
    # One filtered SELECT — not one full active_runs materialization reused poorly.
    assert counter.n == 1
