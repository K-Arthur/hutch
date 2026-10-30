"""Brief redirect and group stop for coordinated specialist tasks (see coordinator_tasks)."""
from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from .coordinator_tasks import _TERMINAL_SQL, _canon, ensure_schema, list_tasks
from .models import Bot, Event, EventType, Run, Task, iso, new_id, utcnow

if TYPE_CHECKING:
    from .engine import Engine
    from .store import Store


def _verify_redirect_target(store: Store, task_id: str) -> tuple[sqlite3.Row, Bot, dict[str, Any], list[str]]:
    from .engine import Engine as EngineCls
    row = store._db.execute(
        "SELECT wt.*, c.archived AS parent_archived, b.doc AS bot_doc, r.capability_snapshot_json "
        "FROM workspace_tasks wt JOIN conversations c ON c.id = wt.parent_conversation_id "
        "JOIN bots b ON b.id = wt.target_bot_id JOIN runs r ON r.id = wt.child_run_id WHERE wt.id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(task_id)
    if row["parent_archived"]:
        raise ValueError("unarchive the coordinator conversation before redirecting this task")
    bot = Bot.from_store_json(row["bot_doc"])
    if bot.paused:
        raise ValueError("unpause the specialist Bot before redirecting this task")
    saved_snapshot = json.loads(row["capability_snapshot_json"] or "{}")
    current_snapshot = EngineCls.capability_snapshot(bot, integration_tools=store.integration_tool_names(bot.id))
    if saved_snapshot != current_snapshot:
        raise ValueError("the specialist's saved model or permissions changed; review the Bot settings first")
    active_runs = [str(r["id"]) for r in store._db.execute(
        f"SELECT id FROM runs WHERE conversation_id = ? AND status NOT IN {_TERMINAL_SQL}", (row["child_conversation_id"],)).fetchall()]
    return row, bot, current_snapshot, active_runs


def _record_redirect_run(store: Store, db: sqlite3.Connection, *, task_id: str, current: sqlite3.Row,
                         bot: Bot, current_snapshot: dict[str, Any], brief: str, new_assumptions: str, now: str) -> tuple[str, str, int]:
    new_revision = int(current["brief_revision"] or 1) + 1
    effective_prompt = (f"[Owner-redirected task brief (revision {new_revision}). Treat earlier assistant output "
                        f"as historical context only; follow this updated brief and constraints.]\n{brief}")
    if new_assumptions:
        effective_prompt += f"\n\nUser-reviewed assumptions and constraints:\n{new_assumptions}"
    child_conv_id = str(current["child_conversation_id"])
    override_spec = str(current["model_override"] or "") if current["model_source"] == "assignment_override" else ""
    redirect_run = Run(bot_id=bot.id, prompt=effective_prompt, origin="workspace_task", conversation_id=child_conv_id, model_override=override_spec)
    redirect_task = Task(bot_id=bot.id, kind="on_demand", prompt=effective_prompt)
    redirect_run.task_id, msg_id = redirect_task.id, new_id("msg")
    seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?", (child_conv_id,)).fetchone()[0]
    db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) VALUES (?, ?, 'on_demand', ?, ?, 0, 'queued', ?)",
               (redirect_task.id, bot.id, brief, redirect_task.created_at, redirect_run.id))
    db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context, capability_snapshot_json) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)",
               (redirect_run.id, bot.id, redirect_task.id, store._run_json(redirect_run), redirect_run.status.value,
                redirect_run.created_at, child_conv_id, _canon(current_snapshot)))
    store._insert_conversation_message(db, message_id=msg_id, conversation_id=child_conv_id, seq=seq,
                                       run_id=redirect_run.id, role="user", content=effective_prompt, created_at=now)
    db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)", (child_conv_id, redirect_run.id, now))
    db.execute("UPDATE conversation_questions SET status = 'answered', answer_run_id = ?, answer_message_id = ?, "
               "selected_option_ids_json = '[]', answered_at = ? WHERE conversation_id = ? AND status = 'pending'",
               (redirect_run.id, msg_id, now, child_conv_id))
    db.execute("UPDATE workspace_tasks SET task_brief = ?, assumptions = ?, brief_revision = ? WHERE id = ?",
               (brief, new_assumptions, new_revision, task_id))
    store._insert_events(db, redirect_run.id, [Event(
        run_id=redirect_run.id, type=EventType.message,
        data={"role": "user", "content": effective_prompt, "message_id": msg_id, "brief_revision": new_revision})])
    ev_row = db.execute("SELECT id, seq FROM events WHERE run_id = ? ORDER BY seq DESC LIMIT 1", (redirect_run.id,)).fetchone()
    if ev_row is not None:
        db.execute("INSERT INTO workspace_task_checkpoints (workspace_task_id, child_run_id, event_id, event_seq, "
                   "event_type, run_status, kind, recovery_state, reference_id, created_at) "
                   "VALUES (?, ?, ?, ?, 'message', 'pending', 'brief_redirected', 'queued', ?, ?)",
                   (task_id, redirect_run.id, int(ev_row["id"]), int(ev_row["seq"]), f"rev:{new_revision}", now))
    return redirect_run.id, child_conv_id, new_revision


def redirect_workspace_task(
    store: Store, engine: Engine, task_id: str, *, task_brief: str,
    assumptions: str | None = None, idem_key: str, request_hash: str,
) -> tuple[dict[str, Any], bool]:
    """Update a task's brief revision, stop active work, and start a redirected run in its conversation."""
    brief = task_brief.strip()
    if not brief or len(brief) > 20_000:
        raise ValueError("redirected task brief must be non-empty and at most 20,000 characters")
    if assumptions is not None and len(assumptions.strip()) > 4_000:
        raise ValueError("assumptions must be at most 4,000 characters")
    scope = f"api:v1:workspace:task:{task_id}:redirect"
    with store._lock:
        ensure_schema(store._db)
        if store._idempotency_replay(store._db, scope, idem_key, request_hash) is not None:
            found = list_tasks(store, task_id=task_id, limit=1)
            if not found:
                raise KeyError(task_id)
            return found[0], False
        _, bot, current_snapshot, active_runs = _verify_redirect_target(store, task_id)
    for active_id in active_runs:
        engine.stop_run(active_id)
    now = iso(utcnow())
    with store._tx() as db:
        if store._idempotency_replay(db, scope, idem_key, request_hash) is not None:
            return list_tasks(store, task_id=task_id, limit=1)[0], False
        store._assert_execution_ready(db)
        current = db.execute("SELECT * FROM workspace_tasks WHERE id = ?", (task_id,)).fetchone()
        if current is None:
            raise KeyError(task_id)
        new_assumptions = current["assumptions"] if assumptions is None else assumptions.strip()
        run_id, child_conv_id, new_revision = _record_redirect_run(
            store, db, task_id=task_id, current=current, bot=bot,
            current_snapshot=current_snapshot, brief=brief, new_assumptions=new_assumptions, now=now)
        db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                   (scope, idem_key, request_hash, _canon({"task_id": task_id, "brief_revision": new_revision, "run_id": run_id}), now))
    store._mirror.wake.set()
    store.bus.notify("work", "runs", f"run:{run_id}", "conversations", f"conversation:{child_conv_id}",
                     f"conversation:{current['parent_conversation_id']}", "workspace_tasks")
    return list_tasks(store, task_id=task_id, limit=1)[0], True


def stop_workspace_task_group(
    store: Store, engine: Engine, task_id: str, *, idem_key: str, request_hash: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Stop all active runs across every specialist assignment in the task's plan group."""
    scope = f"api:v1:workspace:task:{task_id}:stop-all"
    with store._lock:
        ensure_schema(store._db)
        replay = store._idempotency_replay(store._db, scope, idem_key, request_hash)
        row = store._db.execute("SELECT id, plan_group_id, parent_conversation_id FROM workspace_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        group_id = str(row["plan_group_id"] or row["id"])
        if replay is not None:
            return list_tasks(store, plan_group_id=group_id, limit=10), False
        group_rows = store._db.execute(
            "SELECT id, child_conversation_id FROM workspace_tasks WHERE plan_group_id = ? OR id = ? ORDER BY assignment_index, id",
            (group_id, task_id)).fetchall()
        conv_ids = [str(r["child_conversation_id"]) for r in group_rows]
        marks = ",".join("?" for _ in conv_ids)
        active_runs = [str(r["id"]) for r in store._db.execute(
            f"SELECT id FROM runs WHERE conversation_id IN ({marks}) AND status NOT IN {_TERMINAL_SQL}", tuple(conv_ids)).fetchall()]
    for run_id in active_runs:
        engine.stop_run(run_id)
    now = iso(utcnow())
    with store._tx() as db:
        if store._idempotency_replay(db, scope, idem_key, request_hash) is None:
            db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                       (scope, idem_key, request_hash, _canon({"plan_group_id": group_id, "stopped_runs": active_runs}), now))
    store.bus.notify("work", "runs", "workspace_tasks", f"conversation:{row['parent_conversation_id']}")
    return list_tasks(store, plan_group_id=group_id, limit=10), True
