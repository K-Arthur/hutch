import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from hutch.models import Bot, Run, RunStatus, Task
from hutch.store import IdempotencyConflict, Store


def _running_parent(store):
    bot = store.create_bot(Bot(name="delegate-parent", model="mock/demo", tools=[]))
    parent = store.submit_run(Run(bot_id=bot.id, prompt="coordinate work"),
                              Task(bot_id=bot.id, prompt="coordinate work"))
    claimed = store.claim_run(parent.id, "delegation-test-owner", 60)
    assert claimed is not None
    return bot, store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence)


def _child(store, parent, prompt="inspect one bounded area", key="delegate"):
    return store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=parent.bot_id, prompt=prompt),
        task=Task(bot_id=parent.bot_id, kind="delegated", prompt=prompt),
        idem_key=key,
        request_hash=f"sha256:{key}",
    )


def test_delegated_run_creation_persists_parent_and_replays_exact_command(store):
    bot, parent = _running_parent(store)
    child = Run(bot_id=bot.id, prompt="inspect one bounded area", parent_run_id=parent.id)
    task = Task(bot_id=bot.id, kind="delegated", prompt=child.prompt)

    created, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=child,
        task=task,
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )

    assert inserted is True
    assert created.parent_run_id == parent.id
    assert store.get_run(created.id).parent_run_id == parent.id
    with pytest.raises(sqlite3.IntegrityError, match="run parent is immutable"):
        with store._tx() as db:
            db.execute("UPDATE runs SET parent_run_id = NULL WHERE id = ?", (created.id,))
    replayed, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=bot.id, prompt=child.prompt),
        task=Task(bot_id=bot.id, kind="delegated", prompt=child.prompt),
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )
    assert inserted is False
    assert replayed.id == created.id
    store.transition_run(parent.id, RunStatus.succeeded, fence=parent.fence, exit_reason="completed")
    replayed, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=bot.id, prompt=child.prompt),
        task=Task(bot_id=bot.id, kind="delegated", prompt=child.prompt),
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )
    assert inserted is False and replayed.id == created.id
    with pytest.raises(IdempotencyConflict):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(bot_id=bot.id, prompt="changed arguments"),
            task=Task(bot_id=bot.id, kind="delegated", prompt="changed arguments"),
            idem_key="delegate-command-1",
            request_hash="sha256:different-request",
        )


def test_delegated_child_keeps_parent_conversation_attachment_and_context(store):
    bot = store.create_bot(Bot(name="delegate-chat", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Delegation", idem_key="conversation-create", request_hash="sha256:conversation")
    parent_run = Run(bot_id=bot.id, prompt="coordinate a short task")
    parent_task = Task(bot_id=bot.id, prompt=parent_run.prompt)
    parent_id, inserted = store.submit_conversation_message(
        conversation["id"], parent_run.prompt, parent_run, parent_task,
        idem_key="conversation-message", request_hash="sha256:message")
    assert inserted is True
    claimed = store.claim_run(parent_id, "delegation-chat-owner", 60)
    assert claimed is not None
    parent = store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence)

    child, _ = _child(store, parent, key="conversation-child")

    assert child.conversation_id == conversation["id"]
    assert child.conversation_context == parent.conversation_context
    assert store._db.execute(
        "SELECT 1 FROM conversation_runs WHERE conversation_id = ? AND run_id = ?",
        (conversation["id"], child.id),
    ).fetchone()


def test_delegation_rejects_stale_parent_authority_and_cross_bot_children(store):
    _, parent = _running_parent(store)
    with pytest.raises(ValueError, match="current, live run owner"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence - 1,
            run=Run(bot_id=parent.bot_id, prompt="stale"),
            task=Task(bot_id=parent.bot_id, kind="delegated", prompt="stale"),
            idem_key="stale-delegate",
            request_hash="sha256:stale",
        )

    other = store.create_bot(Bot(name="delegate-other", model="mock/demo", tools=[]))
    with pytest.raises(ValueError, match="bot permissions"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(bot_id=other.id, prompt="cross bot"),
            task=Task(bot_id=other.id, kind="delegated", prompt="cross bot"),
            idem_key="cross-bot-delegate",
            request_hash="sha256:cross-bot",
        )
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE parent_run_id = ?", (parent.id,)).fetchone()[0] == 0


def test_delegation_cannot_link_a_run_to_itself(store):
    _, parent = _running_parent(store)
    task = Task(bot_id=parent.bot_id, kind="delegated", prompt="self link")
    with pytest.raises(sqlite3.IntegrityError, match="runs.id"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(id=parent.id, bot_id=parent.bot_id, prompt="self link", parent_run_id=parent.id),
            task=task,
            idem_key="self-link",
            request_hash="sha256:self-link",
        )
    assert store.get_run(parent.id).parent_run_id is None
    assert store._db.execute("SELECT 1 FROM tasks WHERE id = ?", (task.id,)).fetchone() is None


def test_delegation_enforces_depth_fanout_and_active_child_limits(store):
    _, root = _running_parent(store)
    child1, _ = _child(store, root, key="child-1")
    child2, _ = _child(store, root, key="child-2")
    with pytest.raises(ValueError, match="concurrent-child limit"):
        _child(store, root, key="child-3")

    store.transition_run(child1.id, RunStatus.stopped, fence=child1.fence, exit_reason="stopped")
    child3, _ = _child(store, root, key="child-3")
    with pytest.raises(ValueError, match="fan-out limit"):
        _child(store, root, key="child-4")

    # Descendants count toward a fixed root-relative depth even after the parent completes.
    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")
    claimed2 = store.claim_run(child2.id, "delegation-child-owner", 60)
    assert claimed2 is not None
    running2 = store.transition_run(claimed2.id, RunStatus.running, fence=claimed2.fence)
    grandchild, _ = _child(store, running2, key="grandchild")
    store.transition_run(running2.id, RunStatus.succeeded, fence=running2.fence, exit_reason="completed")
    claimed_grandchild = store.claim_run(grandchild.id, "delegation-grandchild-owner", 60)
    assert claimed_grandchild is not None
    running_grandchild = store.transition_run(
        claimed_grandchild.id, RunStatus.running, fence=claimed_grandchild.fence)
    with pytest.raises(ValueError, match="depth limit"):
        _child(store, running_grandchild, key="great-grandchild")


def test_delegation_admission_is_atomic_across_independent_sqlite_connections(store, config):
    _, parent = _running_parent(store)
    count = 8
    gate = Barrier(count)

    def submit(index):
        contender = Store(config)
        try:
            gate.wait(timeout=10)
            try:
                _child(contender, parent, prompt=f"inspect area {index}", key=f"racer-{index}")
                return "created"
            except ValueError as exc:
                assert "concurrent-child limit" in str(exc)
                return "limited"
        finally:
            contender.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        outcomes = list(pool.map(submit, range(count)))
    assert outcomes.count("created") == 2
    assert outcomes.count("limited") == count - 2
    children = store._db.execute("SELECT COUNT(*) FROM runs WHERE parent_run_id = ?", (parent.id,)).fetchone()[0]
    assert children == 2


def test_schema_v21_migrates_existing_runs_with_no_parent_link(config):
    store = Store(config)
    bot = store.create_bot(Bot(name="legacy-delegation", model="mock/demo", tools=[]))
    run = store.submit_run(Run(bot_id=bot.id, prompt="legacy"), Task(bot_id=bot.id, prompt="legacy"))
    store.close()

    db = sqlite3.connect(config.db_path)
    db.execute("DROP TRIGGER runs_parent_run_id_immutable")
    db.execute("DROP INDEX idx_runs_parent")
    db.execute("ALTER TABLE runs DROP COLUMN parent_run_id")
    db.execute("PRAGMA user_version = 21")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        legacy = upgraded.get_run(run.id)
        assert upgraded.schema_version == 22
        assert legacy.parent_run_id is None
        assert (config.db_path.parent / "hutch.db.bak-v21").exists()
    finally:
        upgraded.close()
