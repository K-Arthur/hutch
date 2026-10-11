"""Durable state for dynamic workflows.

Migration schema v53 adds workflow tables and one ``runs`` column; schema v54 adds
effect-receipt identities and workflow-question generation fields. Every write here
goes through the owning :class:`hutch.store.Store` transaction and lock, so workflow
state is in the same SQLite file, the same durability rules and the same resource
outbox as the rest of Hutch.

Identities, and why each exists:

``workflow_definitions``  a saved, reviewable method (a name people recognise).
``workflow_revisions``    an immutable plan + hash. Editing a definition makes a new
                          revision; a run always names the exact revision it executes.
``workflow_runs``         one *instance*: stable across orchestration attempts, owns the
                          input snapshot, the budget ledger, node records and the result.
``workflow_nodes``        one *instance of one site*: ``(site_id, instance_key)`` is the
                          stable key, so a reordered item or a repeated call site can
                          never alias another invocation. This is the replay boundary.
``workflow_questions``    a durable question with its own id, answer and expiry.

Attempts remain ordinary ``runs`` rows (``kind='workflow'`` for orchestration,
``kind='step'`` for a model node). They keep every existing guarantee: one owned
process, lease + fence, honest terminal states, and no mid-flight resume.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Optional

from ..lifecycle import IllegalTransition, LeaseLost, TERMINAL
from ..models import Run, RunStatus, Task, iso, new_id, utcnow

#: Node instance states.
NODE_STATES = ("pending", "running", "waiting", "succeeded", "failed", "skipped", "cancelled")
#: Workflow instance states (a small, honest set; the attempt run carries the run-level truth).
WORKFLOW_STATES = ("pending", "running", "waiting", "succeeded", "failed", "stopped", "outcome_unknown")

MAX_NODES_PER_RUN = 4_000
MAX_LEDGER_KEYS = 64


def migrate(db: sqlite3.Connection) -> None:
    """Ensure workflow definitions, revisions, runs, nodes and questions exist."""
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_definitions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'operator',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_revisions (
        id TEXT PRIMARY KEY,
        definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
        revision INTEGER NOT NULL CHECK(revision >= 1),
        plan_hash TEXT NOT NULL CHECK(length(plan_hash) = 64),
        plan_json TEXT NOT NULL CHECK(json_valid(plan_json)),
        note TEXT NOT NULL DEFAULT '',
        created_by TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(definition_id, revision)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_runs (
        id TEXT PRIMARY KEY,
        definition_id TEXT,
        revision_id TEXT NOT NULL REFERENCES workflow_revisions(id),
        plan_hash TEXT NOT NULL CHECK(length(plan_hash) = 64),
        bot_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL DEFAULT '',
        origin TEXT NOT NULL DEFAULT 'operator',
        inputs_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(inputs_json)),
        budget_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(budget_json)),
        ledger_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(ledger_json)),
        status TEXT NOT NULL CHECK(status IN ('pending','running','waiting','succeeded','failed','stopped','outcome_unknown')),
        reason TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
        attempt_run_id TEXT NOT NULL DEFAULT '',
        stop_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        finished_at TEXT
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_bot ON workflow_runs(bot_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status, updated_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
        site_id TEXT NOT NULL,
        instance_key TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','running','waiting','succeeded','failed','skipped','cancelled')),
        attempt INTEGER NOT NULL DEFAULT 1 CHECK(attempt >= 1),
        input_hash TEXT NOT NULL DEFAULT '',
        input_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(input_json)),
        result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
        error_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(error_json)),
        run_id TEXT,
        started_at TEXT,
        finished_at TEXT,
        UNIQUE(workflow_run_id, site_id, instance_key)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_nodes_run ON workflow_nodes(workflow_run_id, id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_nodes_step ON workflow_nodes(run_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_questions (
        id TEXT PRIMARY KEY,
        workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
        site_id TEXT NOT NULL,
        instance_key TEXT NOT NULL,
        question TEXT NOT NULL,
        options_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(options_json)),
        status TEXT NOT NULL CHECK(status IN ('pending','answered','expired','cancelled')),
        answer TEXT NOT NULL DEFAULT '',
        asked_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        answered_at TEXT,
        UNIQUE(workflow_run_id, site_id, instance_key)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_questions_pending "
               "ON workflow_questions(status, expires_at)")
    # Attempt identity on the hot runs table. Existing rows are ordinary attempts.
    columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
    if "kind" not in columns:
        db.execute("ALTER TABLE runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'attempt'")
    db.execute("CREATE INDEX IF NOT EXISTS idx_runs_kind_status ON runs(kind, status)")


# --------------------------------------------------------------------------- helpers

def _json(value: Any, *, cap: int = 256 * 1024) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    if len(text) > cap:
        raise ValueError(f"workflow value exceeds {cap} bytes")
    return text


def _row_to_workflow(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("inputs_json", "budget_json", "ledger_json", "result_json"):
        item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
    item["stop_requested"] = bool(item.get("stop_requested"))
    return item


def _row_to_node(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in ("input_json", "result_json", "error_json"):
        item[key.removesuffix("_json")] = json.loads(item.pop(key) or "{}")
    return item


# ------------------------------------------------------------------- definitions

def save_definition(store: Any, *, name: str, plan: dict[str, Any], description: str = "",
                    note: str = "", created_by: str = "", source: str = "operator",
                    activate: bool = False) -> dict[str, Any]:
    """Create or extend a definition with a new immutable revision.

    A saved definition is inert until it is activated, and activation is a separate,
    explicit act: saving a method never schedules it or grants it authority.
    """
    from ..workflow.compile import compile_plan

    compiled = compile_plan(plan)  # fail closed: only a valid plan is ever stored
    now = iso(utcnow())
    with store._tx() as db:
        row = db.execute("SELECT id FROM workflow_definitions WHERE name = ?", (name,)).fetchone()
        if row is None:
            definition_id = new_id("wdef")
            db.execute("INSERT INTO workflow_definitions (id, name, description, active, source, created_at, updated_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (definition_id, name, description, 1 if activate else 0, source, now, now))
            revision = 1
        else:
            definition_id = str(row["id"])
            last = db.execute("SELECT MAX(revision) AS r FROM workflow_revisions WHERE definition_id = ?",
                              (definition_id,)).fetchone()
            revision = int(last["r"] or 0) + 1
            db.execute("UPDATE workflow_definitions SET description = ?, updated_at = ? WHERE id = ?",
                       (description or "", now, definition_id))
        revision_id = new_id("wrev")
        db.execute("INSERT INTO workflow_revisions (id, definition_id, revision, plan_hash, plan_json, note, created_by, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (revision_id, definition_id, revision, compiled.plan_hash,
                    _json(plan), note, created_by, now))
    return {"definition_id": definition_id, "revision_id": revision_id, "revision": revision,
            "plan_hash": compiled.plan_hash}


def definition(store: Any, ref: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute(
            """SELECT d.*, (SELECT MAX(revision) FROM workflow_revisions r WHERE r.definition_id = d.id) AS revisions
               FROM workflow_definitions d WHERE d.id = ? OR d.name = ?""", (ref, ref)).fetchone()
    return dict(row) if row else None


def list_definitions(store: Any, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("definition pagination is out of range")
    with store._lock:
        rows = store._db.execute(
            """SELECT d.*, (SELECT MAX(revision) FROM workflow_revisions r WHERE r.definition_id = d.id) AS revisions
               FROM workflow_definitions d ORDER BY d.updated_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)).fetchall()
    return [dict(row) for row in rows]


def set_active(store: Any, definition_id: str, active: bool) -> bool:
    with store._tx() as db:
        cur = db.execute("UPDATE workflow_definitions SET active = ?, updated_at = ? WHERE id = ?",
                         (1 if active else 0, iso(utcnow()), definition_id))
        return cur.rowcount == 1


def revision(store: Any, revision_id: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute("SELECT * FROM workflow_revisions WHERE id = ?", (revision_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["plan"] = json.loads(item.pop("plan_json"))
    return item


def latest_revision(store: Any, definition_id: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute(
            "SELECT id FROM workflow_revisions WHERE definition_id = ? ORDER BY revision DESC LIMIT 1",
            (definition_id,)).fetchone()
    return revision(store, str(row["id"])) if row else None


# ------------------------------------------------------------------------ runs

def submit_workflow_run(store: Any, *, plan: dict[str, Any], definition_id: Optional[str],
                        revision_id: Optional[str], plan_hash: str, bot_id: str, inputs: dict[str, Any],
                        budget: dict[str, Any], origin: str, conversation_id: str,
                        run: Run, task: Task, idem_key: str = "",
                        request_hash: str = "") -> tuple[dict[str, Any], bool]:
    """Admit one workflow instance and its first orchestration attempt, atomically.

    Returns ``(workflow, created)``; a replayed idempotency key returns the original
    instance instead of starting a second one.
    """
    if run.parent_run_id is not None:
        raise ValueError("a workflow attempt is admitted as a root run")
    wf_id = new_id("wrun")
    now = iso(utcnow())
    run.kind = "workflow"
    run.workflow_run_id = wf_id
    run.task_id = task.id
    scope = "api:v1:workflow-runs"
    with store._tx() as db:
        store._assert_execution_ready(db)
        if idem_key:
            replay = store._idempotency_replay(db, scope, idem_key, request_hash)
            if replay is not None:
                row = db.execute("SELECT * FROM workflow_runs WHERE id = ?",
                                 (str(replay["workflow_run_id"]),)).fetchone()
                if row is None:
                    raise RuntimeError("idempotent workflow response points to missing state")
                return _row_to_workflow(row), False
        db.execute("""INSERT INTO workflow_runs (id, definition_id, revision_id, plan_hash, bot_id,
                        conversation_id, origin, inputs_json, budget_json, ledger_json, status, reason,
                        attempt_run_id, created_at, updated_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 'pending', '', ?, ?, ?)""",
                   (wf_id, definition_id, revision_id, plan_hash, bot_id, conversation_id, origin,
                    _json(inputs), _json(budget), run.id, now, now))
        db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                   "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                   (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
        db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, "
                   "conversation_context, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'workflow')",
                   (run.id, run.bot_id, task.id, store._run_json(run), run.status.value, run.created_at,
                    run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False)))
        if idem_key:
            db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                       "VALUES (?, ?, ?, ?, ?)",
                       (scope, idem_key, request_hash,
                        _json({"workflow_run_id": wf_id, "attempt_run_id": run.id}), iso(utcnow())))
    store.bus.notify("work", "runs", f"run:{run.id}")
    return workflow_run(store, wf_id) or {}, True


def workflow_run(store: Any, wf_id: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
    return _row_to_workflow(row) if row else None


def workflow_run_by_attempt(store: Any, attempt_run_id: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute("SELECT * FROM workflow_runs WHERE attempt_run_id = ?",
                                (attempt_run_id,)).fetchone()
    return _row_to_workflow(row) if row else None


def list_workflow_runs(store: Any, *, bot_id: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("workflow run pagination is out of range")
    with store._lock:
        if bot_id:
            rows = store._db.execute(
                "SELECT * FROM workflow_runs WHERE bot_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (bot_id, limit, offset)).fetchall()
        else:
            rows = store._db.execute(
                "SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()
    return [_row_to_workflow(row) for row in rows]


def _assert_workflow_owner(db: sqlite3.Connection, store: Any, *, wf_id: str,
                           revision_id: str, attempt_run_id: str, owner_fence: int,
                           allow_cancelling: bool = False,
                           allow_stopping: bool = False) -> sqlite3.Row:
    """Prove the current workflow generation and ordinary-run lease in one transaction."""
    from ..lifecycle import LeaseLost
    from ..models import RunStatus
    from ..store import _RUN_COLS

    workflow = db.execute("SELECT revision_id, attempt_run_id, status, stop_requested "
                          "FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
    if (workflow is None or str(workflow["revision_id"]) != revision_id
            or str(workflow["attempt_run_id"]) != attempt_run_id
            or (int(workflow["stop_requested"]) and not allow_stopping)):
        raise LeaseLost(attempt_run_id, "workflow attempt or revision is no longer current")
    if str(workflow["status"]) not in ("pending", "running", "waiting"):
        raise LeaseLost(attempt_run_id, "workflow instance is already settled")
    row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (attempt_run_id,)).fetchone()
    store._check_lease(row, attempt_run_id, owner_fence)
    status = RunStatus(row["status"])
    allowed = {RunStatus.running}
    if allow_cancelling:
        allowed.add(RunStatus.cancelling)
    if status not in allowed or (int(row["cancel_requested"]) and not allow_cancelling):
        raise LeaseLost(attempt_run_id, "workflow attempt is not an active owner")
    return row


def update_workflow_run(store: Any, wf_id: str, *, attempt_run_id: Optional[str] = None,
                        owner_fence: Optional[int] = None, revision_id: Optional[str] = None,
                        allow_cancelling: bool = False, allow_stopping: bool = False,
                        status: Optional[str] = None, reason: Optional[str] = None,
                        ledger: Optional[dict[str, Any]] = None, result: Optional[dict[str, Any]] = None,
                        stop_requested: Optional[bool] = None,
                        finished: bool = False) -> bool:
    """Update workflow state, proving attempt, revision and current run lease when owner-scoped."""
    if status is not None and status not in WORKFLOW_STATES:
        raise ValueError(f"unknown workflow state {status!r}")
    sets: list[str] = ["updated_at = ?"]
    args: list[Any] = [iso(utcnow())]
    if status is not None:
        sets.append("status = ?")
        args.append(status)
    if reason is not None:
        sets.append("reason = ?")
        args.append(reason[:500])
    if ledger is not None:
        if len(ledger) > MAX_LEDGER_KEYS:
            raise ValueError("workflow ledger has too many keys")
        sets.append("ledger_json = ?")
        args.append(_json(ledger))
    if result is not None:
        sets.append("result_json = ?")
        args.append(_json(result))
    if stop_requested is not None:
        sets.append("stop_requested = ?")
        args.append(1 if stop_requested else 0)
    if finished:
        sets.append("finished_at = ?")
        args.append(iso(utcnow()))
    where = "id = ?"
    args.append(wf_id)
    if attempt_run_id is not None:
        where += " AND attempt_run_id = ?"
        args.append(attempt_run_id)
    with store._tx() as db:
        if attempt_run_id is not None:
            if owner_fence is None or revision_id is None:
                raise ValueError("owner-scoped workflow updates require a fence and revision")
            _assert_workflow_owner(db, store, wf_id=wf_id, revision_id=revision_id,
                                   attempt_run_id=attempt_run_id, owner_fence=owner_fence,
                                   allow_cancelling=allow_cancelling,
                                   allow_stopping=allow_stopping)
        cur = db.execute(f"UPDATE workflow_runs SET {', '.join(sets)} WHERE {where}", args)
        changed = cur.rowcount == 1
    if changed:
        store.bus.notify("workflows", f"workflow:{wf_id}")
    return changed


def claim_workflow_attempt(store: Any, wf_id: str, attempt_run_id: str, *,
                           owner_fence: int, revision_id: str) -> bool:
    """Confirm the already-admitted attempt is still the instance's current owner.

    Attempt replacement happens atomically during continuation admission. A late process
    from the prior generation must never bind itself over the new attempt.
    """
    from ..lifecycle import LeaseLost

    with store._tx() as db:
        try:
            _assert_workflow_owner(db, store, wf_id=wf_id, revision_id=revision_id,
                                   attempt_run_id=attempt_run_id, owner_fence=owner_fence)
        except LeaseLost:
            return False
        cur = db.execute(
            """UPDATE workflow_runs SET status = 'running', reason = '', updated_at = ?
               WHERE id = ? AND attempt_run_id = ? AND revision_id = ? AND stop_requested = 0
                 AND status IN ('pending','running','waiting')""",
            (iso(utcnow()), wf_id, attempt_run_id, revision_id))
        return cur.rowcount == 1


def request_workflow_stop(store: Any, wf_id: str) -> dict[str, Any]:
    """Durable stop intent: no continuation may be admitted, and the attempt tree is cancelled."""
    with store._lock:
        row = store._db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
    if row is None:
        raise KeyError(wf_id)
    attempt = str(row["attempt_run_id"] or "")
    update_workflow_run(store, wf_id, status=None, stop_requested=True)
    if attempt:
        store.request_cancel_tree(attempt)
    cancel_questions(store, wf_id)
    store.bus.notify("work", "workflows", f"workflow:{wf_id}")
    return {"workflow_run_id": wf_id, "attempt_run_id": attempt, "stop_requested": True}


def workflow_runs_needing_attempt(store: Any, *, limit: int = 4,
                                  quiet_seconds: float = 2.0) -> list[dict[str, Any]]:
    """Live workflow instances whose orchestration attempt is gone (crashed or killed).

    A stopped instance is never continued, and an instance is left alone while its attempt
    is queued, running, or still has an unreaped process.
    """
    from datetime import timedelta

    from ..store import _TERMINAL_VALUES

    if not 1 <= limit <= 50:
        raise ValueError("continuation limit is out of range")
    cutoff = iso(utcnow() - timedelta(seconds=max(0.0, quiet_seconds)))
    with store._lock:
        rows = store._db.execute(
            """SELECT w.* FROM workflow_runs w
               WHERE w.status IN ('pending','running','waiting') AND w.stop_requested = 0
               ORDER BY w.updated_at LIMIT 500""").fetchall()
        ready: list[sqlite3.Row] = []
        terminal = set(_TERMINAL_VALUES)
        for workflow in rows:
            attempt_id = str(workflow["attempt_run_id"] or "")
            previous = store._db.execute(
                "SELECT status, cancel_requested FROM runs WHERE id = ?", (attempt_id,)).fetchone()
            if previous is None:
                if str(workflow["updated_at"]) <= cutoff:
                    ready.append(workflow)
            elif (str(previous["status"]) in terminal
                  and (str(workflow["updated_at"]) <= cutoff or
                       str(previous["status"]) == "stopped")):
                if _workflow_branch_ready(store._db, str(workflow["id"]), attempt_id):
                    ready.append(workflow)
            elif (str(previous["status"]) == "waiting_workflow"
                  and str(workflow["status"]) == "waiting"
                  and _workflow_branch_ready(store._db, str(workflow["id"]), attempt_id)):
                ready.append(workflow)
        return [_row_to_workflow(row) for row in ready[:limit]]


def _workflow_branch_ready(db: sqlite3.Connection, wf_id: str, attempt_id: str) -> bool:
    """No person question, child run, or owned process is left before a fresh pass."""
    if db.execute("SELECT 1 FROM workflow_questions WHERE workflow_run_id = ? AND status = 'pending' LIMIT 1",
                  (wf_id,)).fetchone():
        return False
    from ..store import _TERMINAL_VALUES

    marks = ",".join("?" for _ in _TERMINAL_VALUES)
    branch = """WITH RECURSIVE tree(id) AS (
                   SELECT ? UNION ALL SELECT r.id FROM runs r JOIN tree t ON r.parent_run_id = t.id
               )"""
    active_child = db.execute(
        f"""{branch} SELECT 1 FROM tree t JOIN runs r ON r.id = t.id
            WHERE r.id != ? AND r.status NOT IN ({marks}) LIMIT 1""",
        (attempt_id, attempt_id, *_TERMINAL_VALUES)).fetchone()
    if active_child:
        return False
    owned_process = db.execute(
        f"""{branch} SELECT 1 FROM tree t JOIN run_procs rp ON rp.run_id = t.id
            WHERE rp.ended_at IS NULL AND rp.detached_at IS NULL LIMIT 1""",
        (attempt_id,)).fetchone()
    return owned_process is None


def admit_workflow_continuation(store: Any, wf_id: str) -> Optional[Run]:
    """Admit one fresh orchestration attempt for a live instance, atomically.

    This is a *continuation*, not a resume: the previous attempt stays terminal, and the new
    interpreter pass skips every settled node record. A previous attempt that was cancelled
    means the person stopped the workflow - it is never continued.
    """
    from ..store import _TERMINAL_VALUES

    with store._tx() as db:
        store._assert_execution_ready(db)
        row = db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
        if row is None:
            raise KeyError(wf_id)
        if str(row["status"]) not in ("pending", "running", "waiting") or int(row["stop_requested"]):
            return None
        previous = db.execute("SELECT id, status, cancel_requested FROM runs WHERE id = ?",
                              (str(row["attempt_run_id"]),)).fetchone()
        if previous is not None:
            if int(previous["cancel_requested"]):
                return None
            previous_status = str(previous["status"])
            if previous_status == "waiting_workflow":
                if str(row["status"]) != "waiting" or not _workflow_branch_ready(
                        db, wf_id, str(row["attempt_run_id"])):
                    return None
            elif previous_status not in _TERMINAL_VALUES:
                return None
            elif not _workflow_branch_ready(db, wf_id, str(row["attempt_run_id"])):
                return None
        revision = db.execute("SELECT plan_json FROM workflow_revisions WHERE id = ?",
                              (str(row["revision_id"]),)).fetchone()
        name = "workflow"
        if revision is not None:
            try:
                name = str(json.loads(str(revision["plan_json"])).get("name") or name)
            except (ValueError, TypeError):
                pass
        ledger = json.loads(str(row["ledger_json"]) or "{}") or {}
        attempt = 1 + int(ledger.get("attempts", 0))
        prompt = f"workflow: {name}"[:4_000]
        run = Run(bot_id=str(row["bot_id"]), prompt=prompt, kind="workflow",
                  workflow_run_id=wf_id,
                  origin="workflow" if attempt == 1 else "workflow:continuation",
                  conversation_id=str(row["conversation_id"] or ""))
        task = Task(bot_id=str(row["bot_id"]), kind="workflow", prompt=prompt)
        run.task_id = task.id
        db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                   "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                   (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
        db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, "
                   "conversation_context, kind) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', 'workflow')",
                   (run.id, run.bot_id, task.id, store._run_json(run), run.status.value, run.created_at,
                    run.conversation_id))
        ledger["attempts"] = attempt
        cur = db.execute("UPDATE workflow_runs SET attempt_run_id = ?, status = 'running', updated_at = ?, "
                         "ledger_json = ? WHERE id = ? AND attempt_run_id = ?",
                         (run.id, iso(utcnow()), _json(ledger), wf_id, str(row["attempt_run_id"])))
        if cur.rowcount != 1:
            return None
    return run


# ----------------------------------------------------------------------- nodes

def nodes(store: Any, wf_id: str) -> list[dict[str, Any]]:
    with store._lock:
        rows = store._db.execute(
            "SELECT * FROM workflow_nodes WHERE workflow_run_id = ? ORDER BY id", (wf_id,)).fetchall()
    return [_row_to_node(row) for row in rows]


def node(store: Any, wf_id: str, site_id: str, instance_key: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute(
            "SELECT * FROM workflow_nodes WHERE workflow_run_id = ? AND site_id = ? AND instance_key = ?",
            (wf_id, site_id, instance_key)).fetchone()
    return _row_to_node(row) if row else None


def open_node(store: Any, wf_id: str, *, owner_run_id: str, owner_fence: int, revision_id: str,
              site_id: str, instance_key: str, kind: str,
              input_value: Any, input_hash: str, attempt: int = 1) -> dict[str, Any]:
    """Insert or re-open one node instance. Re-opening the same identity is idempotent.

    A node that already settled is never re-opened: the caller must treat its recorded
    result as the answer (that is the reuse rule that keeps completed work from being
    re-executed after a crash or an amendment).
    """
    payload = _json(input_value)
    now = iso(utcnow())
    with store._tx() as db:
        _assert_workflow_owner(db, store, wf_id=wf_id, revision_id=revision_id,
                               attempt_run_id=owner_run_id, owner_fence=owner_fence)
        count = db.execute("SELECT COUNT(*) AS n FROM workflow_nodes WHERE workflow_run_id = ?",
                           (wf_id,)).fetchone()["n"]
        if int(count) >= MAX_NODES_PER_RUN:
            raise ValueError("this workflow has reached its node-record limit")
        row = db.execute(
            "SELECT id, status, attempt FROM workflow_nodes WHERE workflow_run_id = ? AND site_id = ? AND instance_key = ?",
            (wf_id, site_id, instance_key)).fetchone()
        if row is None:
            db.execute("""INSERT INTO workflow_nodes (workflow_run_id, site_id, instance_key, kind, status,
                            attempt, input_hash, input_json, started_at)
                          VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
                       (wf_id, site_id, instance_key, kind, attempt, input_hash, payload, now))
        else:
            if str(row["status"]) in ("succeeded", "failed", "skipped", "cancelled"):
                raise ValueError("node instance is already settled and cannot be re-opened")
            db.execute("""UPDATE workflow_nodes SET status = 'running', attempt = ?, input_hash = ?,
                            input_json = ?, started_at = ?, finished_at = NULL
                          WHERE id = ?""",
                       (attempt, input_hash, payload, now, int(row["id"])))
    store.bus.notify("workflows", f"workflow:{wf_id}")
    return node(store, wf_id, site_id, instance_key) or {}


def settle_node(store: Any, wf_id: str, site_id: str, instance_key: str, *,
                owner_run_id: str, owner_fence: int, revision_id: str,
                status: str, result: Any = None, error: str = "", run_id: Optional[str] = None,
                input_hash: str = "") -> None:
    if status not in ("succeeded", "failed", "skipped", "cancelled"):
        raise ValueError("a settled node needs a terminal status")
    with store._tx() as db:
        _assert_workflow_owner(db, store, wf_id=wf_id, revision_id=revision_id,
                               attempt_run_id=owner_run_id, owner_fence=owner_fence)
        cur = db.execute("""UPDATE workflow_nodes SET status = ?, result_json = ?, error_json = ?,
                               run_id = COALESCE(?, run_id), finished_at = ?,
                               input_hash = CASE WHEN ? != '' THEN ? ELSE input_hash END
                            WHERE workflow_run_id = ? AND site_id = ? AND instance_key = ?
                              AND status NOT IN ('succeeded','failed','skipped','cancelled')""",
                         (status, _json(result if result is not None else {}),
                          _json({"reason": error} if error else {}), run_id, iso(utcnow()),
                          input_hash, input_hash, wf_id, site_id, instance_key))
        if cur.rowcount != 1:
            raise ValueError("node instance is already settled")
    store.bus.notify("workflows", f"workflow:{wf_id}")


def submit_step_run(store: Any, *, workflow_run_id: str, site_id: str, instance_key: str,
                    run: Run, task: Task, parent_run_id: str, parent_fence: int,
                    idem_key: str, request_hash: str) -> tuple[Run, bool]:
    """Admit one model-node step as an ordinary child run, idempotently."""
    if run.parent_run_id is not None:
        raise ValueError("a step run's parent is set by admission")
    run.parent_run_id = parent_run_id
    run.kind = "step"
    run.workflow_run_id = workflow_run_id
    run.task_id = task.id
    scope = f"workflow:{workflow_run_id}:{site_id}"
    from ..store import _RUN_COLS

    with store._tx() as db:
        store._assert_execution_ready(db)
        replay = store._idempotency_replay(db, scope, idem_key, request_hash)
        if replay is not None:
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (replay["run_id"],)).fetchone()
            if row is None:
                raise RuntimeError("idempotent step response points to missing state")
            return store._run(row), False
        parent = db.execute("SELECT fence, status, cancel_requested FROM runs WHERE id = ?",
                            (parent_run_id,)).fetchone()
        if parent is None or int(parent["fence"]) != int(parent_fence):
            raise ValueError("the orchestration attempt no longer owns this workflow")
        if str(parent["status"]) != "running" or int(parent["cancel_requested"]):
            raise ValueError("the orchestration attempt is not running")
        node_row = db.execute(
            "SELECT id, status FROM workflow_nodes WHERE workflow_run_id = ? AND site_id = ? AND instance_key = ?",
            (workflow_run_id, site_id, instance_key)).fetchone()
        if node_row is None:
            raise ValueError("no node instance exists for this step")
        db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                   "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                   (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
        db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, "
                   "conversation_context, parent_run_id, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'step')",
                   (run.id, run.bot_id, task.id, store._run_json(run), run.status.value, run.created_at,
                    run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False),
                    parent_run_id))
        db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (scope, idem_key, request_hash, _json({"run_id": run.id}), iso(utcnow())))
        db.execute("UPDATE workflow_nodes SET run_id = ? WHERE id = ?", (run.id, int(node_row["id"])))
    store.bus.notify("work", "runs", "workflows", f"workflow:{workflow_run_id}", f"run:{run.id}")
    return run, True


def step_run_result(store: Any, run_id: str) -> dict[str, Any]:
    """Read a settled step's final assistant text and its terminal facts."""
    run = store.get_run(run_id)
    if run is None:
        return {"status": "missing", "text": ""}
    text = ""
    for event in reversed(store.tail_events(run_id, limit=100)):
        if event.type.value == "message" and event.data.get("role") == "assistant":
            text = str(event.data.get("content") or "")
            break
    return {"status": run.status.value, "text": text, "exit_reason": run.exit_reason,
            "error": run.error, "steps": run.steps, "tokens": run.tokens, "cost_usd": run.cost_usd}


# ------------------------------------------------------------------- questions

def create_question(store: Any, *, wf_id: str, owner_run_id: str, owner_fence: int, revision_id: str,
                    site_id: str, instance_key: str, question: str,
                    options: Iterable[str], expires_at: str) -> dict[str, Any]:
    qid = new_id("wq")
    with store._tx() as db:
        _assert_workflow_owner(db, store, wf_id=wf_id, revision_id=revision_id,
                               attempt_run_id=owner_run_id, owner_fence=owner_fence)
        db.execute("""INSERT INTO workflow_questions (id, workflow_run_id, site_id, instance_key,
                        question, options_json, status, asked_at, expires_at, revision_id, attempt_run_id)
                      VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                      ON CONFLICT(workflow_run_id, site_id, instance_key) DO NOTHING""",
                   (qid, wf_id, site_id, instance_key, question[:2000],
                    _json(list(options)[:20]), iso(utcnow()), expires_at, revision_id, owner_run_id))
        row = db.execute("SELECT * FROM workflow_questions WHERE workflow_run_id = ? AND site_id = ? "
                         "AND instance_key = ?", (wf_id, site_id, instance_key)).fetchone()
    store.bus.notify("workflows", f"workflow:{wf_id}")
    return _question_row(row)


def _question_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["options"] = json.loads(item.pop("options_json") or "[]")
    return item


def question(store: Any, qid: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute("SELECT * FROM workflow_questions WHERE id = ?", (qid,)).fetchone()
    return _question_row(row) if row else None


def questions(store: Any, wf_id: str, *, status: str = "") -> list[dict[str, Any]]:
    with store._lock:
        if status:
            rows = store._db.execute(
                "SELECT * FROM workflow_questions WHERE workflow_run_id = ? AND status = ? ORDER BY asked_at",
                (wf_id, status)).fetchall()
        else:
            rows = store._db.execute(
                "SELECT * FROM workflow_questions WHERE workflow_run_id = ? ORDER BY asked_at",
                (wf_id,)).fetchall()
    return [_question_row(row) for row in rows]


def answer_question(store: Any, qid: str, answer: str) -> str:
    """Resolve one pending question by its own id. Returns won|already|expired|missing."""
    if len(answer) > 4_000:
        raise ValueError("the answer is too long")
    now = iso(utcnow())
    with store._tx() as db:
        cur = db.execute(
            """UPDATE workflow_questions SET status = 'answered', answer = ?, answered_at = ?
               WHERE id = ? AND status = 'pending' AND expires_at >= ?
                 AND EXISTS (SELECT 1 FROM workflow_runs w
                             WHERE w.id = workflow_questions.workflow_run_id
                               AND w.revision_id = workflow_questions.revision_id
                               AND w.attempt_run_id = workflow_questions.attempt_run_id
                               AND w.status IN ('running','waiting') AND w.stop_requested = 0)""",
            (answer, now, qid, now))
        if cur.rowcount == 1:
            return "won"
        row = db.execute("SELECT status, expires_at FROM workflow_questions WHERE id = ?", (qid,)).fetchone()
        if row is None:
            return "missing"
        if str(row["status"]) == "pending" and str(row["expires_at"]) < now:
            db.execute("UPDATE workflow_questions SET status = 'expired' WHERE id = ? AND status = 'pending'", (qid,))
            return "expired"
        return "already"


def expire_questions(store: Any, *, now: Optional[str] = None, limit: int = 200) -> int:
    stamp = now or iso(utcnow())
    with store._tx() as db:
        rows = db.execute("SELECT id FROM workflow_questions WHERE status = 'pending' AND expires_at < ? LIMIT ?",
                          (stamp, limit)).fetchall()
        for row in rows:
            db.execute("UPDATE workflow_questions SET status = 'expired' WHERE id = ? AND status = 'pending'",
                       (str(row["id"]),))
    if rows:
        store.bus.notify("workflows")
    return len(rows)


def cancel_questions(store: Any, wf_id: str) -> int:
    with store._tx() as db:
        cur = db.execute("UPDATE workflow_questions SET status = 'cancelled' WHERE workflow_run_id = ? "
                         "AND status = 'pending'", (wf_id,))
    if cur.rowcount:
        store.bus.notify("workflows", f"workflow:{wf_id}")
    return int(cur.rowcount)


def finalize_stopped_workflows(store: Any, *, limit: int = 50) -> int:
    """Finish cancellation only after the attempt tree has terminal states and verified cleanup."""
    with store._lock:
        workflows = store._db.execute(
            "SELECT id, attempt_run_id, stop_requested FROM workflow_runs "
            "WHERE status IN ('pending','running','waiting') ORDER BY updated_at LIMIT ?", (limit,)
        ).fetchall()
    changed = 0
    terminal_values = {status.value for status in TERMINAL}
    for workflow in workflows:
        wf_id, attempt_id = str(workflow["id"]), str(workflow["attempt_run_id"] or "")
        run = store.get_run(attempt_id) if attempt_id else None
        if run is None or run.status.value not in terminal_values | {"cancelling"}:
            continue
        if not bool(workflow["stop_requested"]) and not run.cancel_requested:
            continue
        cancel_questions(store, wf_id)
        if run.status.value == "cancelling":
            if run.lease_owner:
                continue
            with store._lock:
                if not _workflow_branch_ready(store._db, wf_id, attempt_id):
                    continue
            try:
                run = store.transition_run(
                    run.id, RunStatus.stopped,
                    exit_reason="stopped", error="stopped after owned workflow processes were verified gone",
                    event={"reason": "stopped", "cleanup_verified": True})
            except (IllegalTransition, LeaseLost, KeyError):
                continue
        if run.status.value not in terminal_values:
            continue
        with store._lock:
            if not _workflow_branch_ready(store._db, wf_id, attempt_id):
                continue
        outcome = run.status.value if run.status.value in ("stopped", "failed", "outcome_unknown") else "stopped"
        nodes_now = nodes(store, wf_id)
        counts: dict[str, int] = {}
        for item in nodes_now:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        artifacts: list[dict[str, Any]] = []
        for item in nodes_now:
            if item["status"] == "succeeded" and isinstance(item.get("result"), dict):
                artifacts.extend(ref for ref in (item["result"].get("artifacts") or [])
                                 if isinstance(ref, dict))
        result = {"counts": counts, "artifacts": artifacts}
        if update_workflow_run(store, wf_id, status=outcome,
                               reason=(run.error or run.exit_reason or "stopped")[:500],
                               result=result, finished=True):
            changed += 1
    return changed
