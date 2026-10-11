"""Durable state for dynamic workflows.

Migration schema v53 adds workflow tables and one ``runs`` column; schema v54 adds
effect-receipt identities and workflow-question generation fields; schema v55 binds
provider usage reservations to the root workflow. Every write here
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
from ..models import Bot, Run, RunStatus, Task, iso, new_id, utcnow

#: Node instance states.
NODE_STATES = ("pending", "running", "waiting", "succeeded", "failed", "skipped", "cancelled")
#: Workflow instance states (a small, honest set; the attempt run carries the run-level truth).
WORKFLOW_STATES = ("pending", "running", "waiting", "succeeded", "failed", "stopped", "outcome_unknown")

MAX_NODES_PER_RUN = 4_000
MAX_LEDGER_KEYS = 64
MAX_AMENDMENT_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_AUTOMATIC_WORKFLOW_RECOVERIES = 2
RECOVERABLE_WORKFLOW_EXIT_REASONS = frozenset({"interrupted", "event_delivery_failed"})


def is_recoverable_workflow_attempt(status: str, exit_reason: str) -> bool:
    """Only crash or canonical-outbox failures may start an automatic continuation."""
    return status == "failed" and exit_reason in RECOVERABLE_WORKFLOW_EXIT_REASONS


def workflow_recovery_exhausted(store: Any, wf_id: str) -> bool:
    """Return whether this workflow has used its bounded automatic continuations."""
    with store._lock:
        row = store._db.execute("SELECT ledger_json FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
    if row is None:
        return False
    try:
        continuations = int(json.loads(str(row["ledger_json"] or "{}")).get("recoveries", 0))
    except (TypeError, ValueError):
        continuations = 0
    return continuations >= MAX_AUTOMATIC_WORKFLOW_RECOVERIES


class AmendmentSnapshotLimit(ValueError):
    """Historical result state exceeds the bounded amendment archive size."""


class WorkflowPauseRequested(RuntimeError):
    """A node has not started because the owner requested a safe-boundary pause."""


class ScheduleClaimLost(RuntimeError):
    """A due routine changed or was claimed before its linked workflow could be admitted."""


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


def migrate_usage_reservations(db: sqlite3.Connection) -> None:
    """Bind provider attempts to workflow roots and conservatively mark legacy starts."""
    columns = {str(row[1]) for row in db.execute("PRAGMA table_info(usage_reservations)")}
    if "workflow_run_id" not in columns:
        db.execute("ALTER TABLE usage_reservations ADD COLUMN workflow_run_id TEXT NOT NULL DEFAULT ''")
    if "request_started_at" not in columns:
        db.execute("ALTER TABLE usage_reservations ADD COLUMN request_started_at TEXT")
    db.execute("""UPDATE usage_reservations
                  SET workflow_run_id = COALESCE((SELECT CASE WHEN json_valid(r.doc)
                                                              THEN json_extract(r.doc, '$.workflow_run_id')
                                                              ELSE '' END
                                                  FROM runs r WHERE r.id = usage_reservations.run_id), '')
                  WHERE workflow_run_id = ''""")
    # Settled and unresolved reservations were created immediately before provider dispatch
    # in the old runtime. Count them as started when preserving the root allowance.
    db.execute("""UPDATE usage_reservations SET request_started_at = created_at
                  WHERE request_started_at IS NULL AND status IN ('reserved', 'uncertain', 'settled')""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_usage_reservations_workflow "
               "ON usage_reservations(workflow_run_id, status, request_started_at) "
               "WHERE workflow_run_id != ''")


def migrate_amendment_history(db: sqlite3.Connection) -> None:
    """Preserve the exact node/question/result snapshot retired by an amendment."""
    db.execute("""CREATE TABLE IF NOT EXISTS workflow_amendment_history (
        id TEXT PRIMARY KEY,
        workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
        previous_revision_id TEXT NOT NULL REFERENCES workflow_revisions(id),
        adopted_revision_id TEXT NOT NULL REFERENCES workflow_revisions(id),
        previous_attempt_run_id TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        previous_plan_hash TEXT NOT NULL,
        adopted_plan_hash TEXT NOT NULL,
        preview_json TEXT NOT NULL CHECK(json_valid(preview_json)),
        nodes_json TEXT NOT NULL CHECK(json_valid(nodes_json)),
        questions_json TEXT NOT NULL CHECK(json_valid(questions_json)),
        result_json TEXT NOT NULL CHECK(json_valid(result_json)),
        created_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_workflow_amendment_history_run "
               "ON workflow_amendment_history(workflow_run_id, created_at)")


def migrate_workflow_pause(db: sqlite3.Connection) -> None:
    """Add the durable owner pause flag without changing workflow terminal states."""
    columns = {str(row[1]) for row in db.execute("PRAGMA table_info(workflow_runs)")}
    if "pause_requested" not in columns:
        db.execute("ALTER TABLE workflow_runs ADD COLUMN pause_requested INTEGER NOT NULL DEFAULT 0 "
                   "CHECK(pause_requested IN (0,1))")


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
    item["pause_requested"] = bool(item.get("pause_requested"))
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
            """SELECT d.*,
                      (SELECT MAX(revision) FROM workflow_revisions r WHERE r.definition_id = d.id) AS revisions,
                      (SELECT id FROM workflow_revisions r WHERE r.definition_id = d.id
                       ORDER BY revision DESC LIMIT 1) AS latest_revision_id
               FROM workflow_definitions d WHERE d.id = ? OR d.name = ?""", (ref, ref)).fetchone()
    return dict(row) if row else None


def list_definitions(store: Any, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("definition pagination is out of range")
    with store._lock:
        rows = store._db.execute(
            """SELECT d.*,
                      (SELECT MAX(revision) FROM workflow_revisions r WHERE r.definition_id = d.id) AS revisions,
                      (SELECT id FROM workflow_revisions r WHERE r.definition_id = d.id
                       ORDER BY revision DESC LIMIT 1) AS latest_revision_id
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


def amendment_history_summaries(store: Any, wf_id: str, *, limit: int = 50,
                                offset: int = 0) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("amendment history pagination is out of range")
    with store._lock:
        rows = store._db.execute(
            """SELECT id, previous_revision_id, adopted_revision_id, previous_attempt_run_id,
                      previous_status, previous_plan_hash, adopted_plan_hash, created_at
                 FROM workflow_amendment_history WHERE workflow_run_id = ?
                 ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
            (wf_id, limit, offset)).fetchall()
    return [dict(row) for row in rows]


def amendment_history_detail(store: Any, wf_id: str, amendment_id: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute(
            "SELECT * FROM workflow_amendment_history WHERE workflow_run_id = ? AND id = ?",
            (wf_id, amendment_id)).fetchone()
    if row is None:
        return None
    item = dict(row)
    for field in ("preview_json", "nodes_json", "questions_json", "result_json"):
        item[field.removesuffix("_json")] = json.loads(item.pop(field) or "{}")
    return item


def _workflow_execution_tree_quiet(db: sqlite3.Connection, attempt_id: str) -> bool:
    """Prove no child work or owned process remains; human questions are checked separately."""
    from ..store import _TERMINAL_VALUES

    marks = ",".join("?" for _ in _TERMINAL_VALUES)
    tree = """WITH RECURSIVE tree(id) AS (
                 SELECT ? UNION ALL SELECT r.id FROM runs r JOIN tree t ON r.parent_run_id = t.id
             )"""
    active_child = db.execute(
        f"""{tree} SELECT 1 FROM tree t JOIN runs r ON r.id = t.id
            WHERE r.id != ? AND r.status NOT IN ({marks}) LIMIT 1""",
        (attempt_id, attempt_id, *_TERMINAL_VALUES)).fetchone()
    if active_child:
        return False
    owned_process = db.execute(
        f"""{tree} SELECT 1 FROM tree t JOIN run_procs rp ON rp.run_id = t.id
            WHERE rp.ended_at IS NULL AND rp.detached_at IS NULL LIMIT 1""",
        (attempt_id,)).fetchone()
    return owned_process is None


def workflow_attempt_quiescence(store: Any, attempt_id: str) -> dict[str, Any]:
    """Return a read-only snapshot of attempt parking and its owned child/process tree."""
    if not attempt_id:
        return {"attempt_status": "", "attempt_parked": False, "owned_work_quiet": False}
    with store._lock:
        attempt = store._db.execute(
            "SELECT status, cancel_requested, lease_owner FROM runs WHERE id = ?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            return {"attempt_status": "", "attempt_parked": False, "owned_work_quiet": False}
        status = str(attempt["status"])
        parked = (status == "waiting_workflow" and not int(attempt["cancel_requested"] or 0)
                  and not str(attempt["lease_owner"] or ""))
        return {"attempt_status": status, "attempt_parked": parked,
                "owned_work_quiet": _workflow_execution_tree_quiet(store._db, attempt_id)}


def workflow_pause_requested(store: Any, wf_id: str) -> bool:
    with store._lock:
        row = store._db.execute("SELECT pause_requested FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
    return bool(row and row["pause_requested"])


def workflow_pause_controls(store: Any, wf_id: str) -> dict[str, bool]:
    """Return owner-control availability without mistaking a pending drain for a parked run."""
    with store._lock:
        workflow = store._db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
        if workflow is None:
            return {"pause_available": False, "pause_after_work_available": False,
                    "resume_available": False, "pause_ready": False}
        attempt_id = str(workflow["attempt_run_id"] or "")
        attempt = store._db.execute("SELECT status, cancel_requested, lease_owner FROM runs WHERE id = ?",
                                    (attempt_id,)).fetchone() if attempt_id else None
        status = str(workflow["status"])
        paused = bool(workflow["pause_requested"])
        stopping = bool(workflow["stop_requested"] or workflow["finished_at"])
        attempt_status = str(attempt["status"]) if attempt else ""
        owner = str(attempt["lease_owner"] or "") if attempt else ""
        cancelled = bool(attempt["cancel_requested"]) if attempt else True
        parked = (status == "waiting" and attempt_status == "waiting_workflow"
                  and not owner and not cancelled)
        quiet = bool(attempt and _workflow_execution_tree_quiet(store._db, attempt_id))
        ready = parked and quiet
        resume = paused and not stopping and ready
        can_pause = (not paused and not stopping and not cancelled and
                     ((status == "running" and attempt_status == "running" and bool(owner))
                      or (status == "waiting" and attempt_status == "waiting_workflow" and not owner)))
        return {"pause_available": can_pause,
                "pause_after_work_available": can_pause and not ready,
                "resume_available": resume, "pause_ready": paused and ready}


def adopt_workflow_amendment(store: Any, *, wf_id: str, expected_revision_id: str,
                             expected_generation: str, plan: dict[str, Any], plan_hash: str,
                             inputs: dict[str, Any], budget: dict[str, Any],
                             preview: dict[str, Any], cancel_pending_questions: bool,
                             authorize: Any, idem_key: str, request_hash: str) -> dict[str, Any]:
    """Atomically adopt a new revision on a parked, quiescent workflow instance.

    Active model/tool children are never killed by adoption. Pending human questions are
    cancelled only when the owner explicitly requests it; all prior node/question/result
    state is archived before invalidated rows are removed for the next continuation.
    """
    scope = f"api:v1:workflow-amendments:{wf_id}"
    now = iso(utcnow())
    response: dict[str, Any]
    with store._tx() as db:
        store._assert_execution_ready(db)
        replay = store._idempotency_replay(db, scope, idem_key, request_hash)
        if replay is not None:
            return replay

        row = db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
        if row is None:
            raise KeyError(wf_id)
        if str(row["revision_id"]) != expected_revision_id:
            raise ValueError("the workflow revision changed; refresh before adopting an amendment")
        if str(row["attempt_run_id"]) != expected_generation:
            raise ValueError("the workflow generation changed; refresh before adopting an amendment")
        workflow_status = str(row["status"])
        if workflow_status in ("succeeded", "failed", "stopped", "outcome_unknown"):
            raise ValueError("terminal workflow amendments are unsupported; start a new run from the saved workflow")
        if workflow_status != "waiting" or int(row["stop_requested"]):
            raise ValueError("amendment adoption requires a parked workflow with no stop in progress")
        if not row["definition_id"]:
            raise ValueError("the workflow run has no saved definition to attach the adopted revision to")

        attempt = db.execute("SELECT status, cancel_requested, lease_owner FROM runs WHERE id = ?",
                             (expected_generation,)).fetchone()
        if (attempt is None or str(attempt["status"]) != "waiting_workflow"
                or int(attempt["cancel_requested"]) or attempt["lease_owner"]):
            raise ValueError("the current workflow attempt has not released its process and owner lease")
        if not _workflow_execution_tree_quiet(db, expected_generation):
            raise ValueError("amendment adoption cannot proceed while child work or an owned process is active")

        questions_before = db.execute(
            "SELECT * FROM workflow_questions WHERE workflow_run_id = ? ORDER BY asked_at, id",
            (wf_id,)).fetchall()
        pending = [dict(question) for question in questions_before if str(question["status"]) == "pending"]
        pending_ids = [str(question["id"]) for question in pending]
        if pending_ids and not cancel_pending_questions:
            raise ValueError(f"adoption would cancel pending questions {pending_ids}; set cancel_pending_questions=true")
        pending_ask_sites = {(str(question["site_id"]), str(question["instance_key"]))
                             for question in pending}
        active_nodes = db.execute(
            """SELECT site_id, instance_key, kind, status FROM workflow_nodes
               WHERE workflow_run_id = ? AND status IN ('pending','running','waiting')""",
            (wf_id,)).fetchall()
        blockers = [dict(node) for node in active_nodes
                    if str(node["status"]) != "waiting"
                    or str(node["kind"]) != "ask"
                    or (str(node["site_id"]), str(node["instance_key"])) not in pending_ask_sites]
        if blockers:
            raise ValueError("amendment adoption cannot proceed while workflow nodes are active")
        if pending_ids:
            db.execute("UPDATE workflow_questions SET status = 'cancelled' "
                       "WHERE workflow_run_id = ? AND status = 'pending'", (wf_id,))
            questions_before = db.execute(
                "SELECT * FROM workflow_questions WHERE workflow_run_id = ? ORDER BY asked_at, id",
                (wf_id,)).fetchall()

        active_questions = {str(question["id"]) for question in questions_before
                            if str(question["status"]) == "pending"}
        if active_questions:
            raise ValueError("a workflow question became pending while adopting the amendment")

        node_rows = db.execute("SELECT * FROM workflow_nodes WHERE workflow_run_id = ? ORDER BY id",
                               (wf_id,)).fetchall()
        node_snapshot = [_row_to_node(node) for node in node_rows]
        question_snapshot = [_question_row(question) for question in questions_before]
        prior_result = json.loads(str(row["result_json"] or "{}"))
        preview_copy = dict(preview)
        preview_copy["roles"] = authorize()
        preview_copy["eligible"] = True
        preview_copy["quiescence"] = {
            "workflow_status": str(row["status"]),
            "attempt_status": "waiting_workflow",
            "attempt_parked": True,
            "owned_work_quiet": True,
            "active_nodes": [{"site_id": str(node["site_id"]),
                              "instance_key": str(node["instance_key"]),
                              "status": str(node["status"])} for node in active_nodes],
            "pending_question_ids": pending_ids,
            "required": True,
        }
        encoded = {
            "preview": _json(preview_copy),
            "nodes": _json(node_snapshot),
            "questions": _json(question_snapshot),
            "result": _json(prior_result),
        }
        snapshot_size = sum(len(value.encode("utf-8")) for value in encoded.values())
        if snapshot_size > MAX_AMENDMENT_SNAPSHOT_BYTES:
            raise AmendmentSnapshotLimit(
                f"historical workflow snapshot is {snapshot_size} bytes; the adoption limit is "
                f"{MAX_AMENDMENT_SNAPSHOT_BYTES} bytes")

        definition_id = str(row["definition_id"])
        definition = db.execute("SELECT id FROM workflow_definitions WHERE id = ?",
                                (definition_id,)).fetchone()
        if definition is None:
            raise ValueError("the workflow definition was removed; the revision cannot be adopted")
        revision_number = int(db.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM workflow_revisions WHERE definition_id = ?",
            (definition_id,)).fetchone()[0])
        revision_id = new_id("wrev")
        history_id = new_id("wamend")
        db.execute("""INSERT INTO workflow_revisions
                      (id, definition_id, revision, plan_hash, plan_json, note, created_by, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                   (revision_id, definition_id, revision_number, plan_hash, _json(plan),
                    "Adopted from a parked workflow run", "local-owner", now))
        db.execute("UPDATE workflow_definitions SET updated_at = ? WHERE id = ?",
                   (now, definition_id))
        db.execute("""INSERT INTO workflow_amendment_history
                      (id, workflow_run_id, previous_revision_id, adopted_revision_id,
                       previous_attempt_run_id, previous_status, previous_plan_hash, adopted_plan_hash,
                       preview_json, nodes_json, questions_json, result_json, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (history_id, wf_id, expected_revision_id, revision_id, expected_generation,
                    str(row["status"]), str(row["plan_hash"]), plan_hash, encoded["preview"],
                    encoded["nodes"], encoded["questions"], encoded["result"], now))

        reusable = {(str(item["site_id"]), str(item["instance_key"])) for item in preview.get("reuse", [])}
        for node in node_rows:
            key = (str(node["site_id"]), str(node["instance_key"]))
            if key not in reusable:
                db.execute("DELETE FROM workflow_nodes WHERE id = ?", (int(node["id"]),))
        db.execute("DELETE FROM workflow_questions WHERE workflow_run_id = ?", (wf_id,))

        # The preview has already refused wider ceilings; min() keeps the root ledger's
        # remaining allowances bounded even if a future caller bypasses that check.
        effective_budget = dict(budget)
        prior_budget = json.loads(str(row["budget_json"] or "{}"))
        for key in ("max_nodes", "max_model_calls", "max_tokens", "max_wall_seconds",
                    "max_fanout", "max_repairs", "max_steps_per_node", "max_step_seconds"):
            if isinstance(prior_budget.get(key), int) and isinstance(effective_budget.get(key), int):
                effective_budget[key] = min(int(prior_budget[key]), int(effective_budget[key]))
        cur = db.execute(
            """UPDATE workflow_runs SET revision_id = ?, plan_hash = ?, inputs_json = ?, budget_json = ?,
                      status = 'waiting', reason = ?, result_json = '{}', pause_requested = 0,
                      finished_at = NULL, updated_at = ?
               WHERE id = ? AND revision_id = ? AND attempt_run_id = ? AND status = 'waiting'
                 AND stop_requested = 0""",
            (revision_id, plan_hash, _json(inputs), _json(effective_budget),
             "amendment adopted; waiting for a fresh continuation", now,
             wf_id, expected_revision_id, expected_generation))
        if cur.rowcount != 1:
            raise ValueError("workflow state changed while adopting the amendment")

        response = {
            "workflow_run_id": wf_id,
            "history_id": history_id,
            "previous_revision_id": expected_revision_id,
            "revision_id": revision_id,
            "attempt_run_id": expected_generation,
            "plan_hash": plan_hash,
            "cancelled_question_ids": pending_ids,
            "preview": preview_copy,
        }
        db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?)", (scope, idem_key, request_hash, _json(response), now))
    store.bus.notify("work", "runs", "workflows", f"workflow:{wf_id}")
    return response


# ------------------------------------------------------------------------ runs

def submit_workflow_run(store: Any, *, plan: dict[str, Any], definition_id: Optional[str],
                        revision_id: Optional[str], plan_hash: str, bot_id: str, inputs: dict[str, Any],
                        budget: dict[str, Any], origin: str, conversation_id: str,
                        run: Run, task: Task, idem_key: str = "",
                        request_hash: str = "", schedule_claim: Optional[dict[str, Any]] = None
                        ) -> tuple[dict[str, Any], bool]:
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
    if schedule_claim is not None:
        if not idem_key:
            raise ValueError("a scheduled workflow occurrence requires an idempotency key")
        run.schedule_id = str(schedule_claim["schedule_id"])
        run.missed_windows = int(schedule_claim.get("missed_windows") or 0)
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
        if schedule_claim is not None:
            schedule_id = str(schedule_claim["schedule_id"])
            schedule_marker = f"{schedule_id}:last_fire"
            dispatch_marker = f"{schedule_id}:last_dispatch"
            control = db.execute("SELECT schedules_paused FROM workspace_settings WHERE id = 1").fetchone()
            if control is None or bool(control["schedules_paused"]):
                raise ScheduleClaimLost("workspace schedules were paused before admission")
            bot_row = db.execute("SELECT doc FROM bots WHERE id = ?", (bot_id,)).fetchone()
            if bot_row is None:
                raise ScheduleClaimLost("the routine's assistant no longer exists")
            current_bot = Bot.model_validate_json(str(bot_row["doc"]))
            current_schedules = current_bot.schedules or ([current_bot.schedule] if current_bot.schedule else [])
            current_schedule = next((item for item in current_schedules if item.id == schedule_id), None)
            if (current_bot.paused or current_schedule is None or not current_schedule.enabled
                    or current_schedule.workflow_definition_id != definition_id
                    or current_schedule.workflow_revision_id != revision_id
                    or current_schedule.workflow_inputs != inputs):
                raise ScheduleClaimLost("the routine or its pinned workflow changed before admission")
            active_revision = db.execute(
                """SELECT d.active FROM workflow_definitions d JOIN workflow_revisions r
                     ON r.definition_id = d.id WHERE d.id = ? AND r.id = ?""",
                (definition_id, revision_id)).fetchone()
            if active_revision is None or not bool(active_revision["active"]):
                raise ScheduleClaimLost("the linked workflow is no longer active")
            marker = db.execute("SELECT value FROM kv WHERE key = ?", (schedule_marker,)).fetchone()
            actual_marker = marker["value"] if marker else None
            if actual_marker != schedule_claim.get("expected_marker"):
                raise ScheduleClaimLost("another scheduler claimed this routine occurrence")
            try:
                db.execute("""INSERT INTO schedule_occurrences_v20
                    (schedule_id, occurrence, bot_id, run_id, claimed_at, claimed_by)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (schedule_id, str(schedule_claim["occurrence"]), bot_id, run.id, now,
                     str(schedule_claim.get("claimed_by") or "")))
            except sqlite3.IntegrityError:
                raise ScheduleClaimLost("another scheduler claimed this routine occurrence") from None
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
        if schedule_claim is not None:
            db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (schedule_marker, str(schedule_claim["occurrence"])))
            note = {"scheduled_workflow": wf_id, "workflow_attempt": run.id,
                    "schedule_id": schedule_id, "revision_id": revision_id,
                    "missed_windows": run.missed_windows, "occurrence": schedule_claim["occurrence"]}
            db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (dispatch_marker, json.dumps(note, sort_keys=True)))
    store.bus.notify("work", "runs", f"run:{run.id}", *(('schedules',) if schedule_claim is not None else ()))
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
                        stop_requested: Optional[bool] = None, pause_requested: Optional[bool] = None,
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
    if pause_requested is not None:
        sets.append("pause_requested = ?")
        args.append(1 if pause_requested else 0)
    if finished:
        sets.append("finished_at = ?")
        args.append(iso(utcnow()))
    where = "id = ?"
    args.append(wf_id)
    if revision_id is not None and attempt_run_id is None:
        where += " AND revision_id = ?"
        args.append(revision_id)
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


def request_workflow_stop(store: Any, wf_id: str, *, expected_revision_id: str = "") -> dict[str, Any]:
    """Durable stop intent: no continuation may be admitted, and the attempt tree is cancelled."""
    with store._lock:
        row = store._db.execute("SELECT revision_id, attempt_run_id FROM workflow_runs WHERE id = ?",
                                (wf_id,)).fetchone()
    if row is None:
        raise KeyError(wf_id)
    if expected_revision_id and str(row["revision_id"]) != expected_revision_id:
        raise ValueError("workflow revision changed; refresh before stopping")
    attempt = str(row["attempt_run_id"] or "")
    if not update_workflow_run(store, wf_id, status=None, stop_requested=True, pause_requested=False,
                               revision_id=expected_revision_id or str(row["revision_id"])):
        raise ValueError("workflow revision changed; refresh before stopping")
    if attempt:
        store.request_cancel_tree(attempt)
    cancel_questions(store, wf_id)
    store.bus.notify("work", "workflows", f"workflow:{wf_id}")
    return {"workflow_run_id": wf_id, "attempt_run_id": attempt, "stop_requested": True}


def set_workflow_pause(store: Any, wf_id: str, *, paused: bool, expected_revision_id: str,
                       expected_generation: str, idem_key: str, request_hash: str) -> dict[str, Any]:
    """Request a safe-boundary pause, or resume after the run is fully parked.

    A pause request never cancels active work. The current node and owned children settle,
    while node admission and continuation remain blocked. Resume requires verified cleanup.
    Revision/generation checks, pause state and the idempotency receipt share one transaction.
    """
    scope = f"api:v1:workflow-pause:{wf_id}"
    with store._tx() as db:
        store._assert_execution_ready(db)
        replay = store._idempotency_replay(db, scope, idem_key, request_hash)
        if replay is not None:
            return replay
        row = db.execute("SELECT * FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
        if row is None:
            raise KeyError(wf_id)
        if str(row["revision_id"]) != expected_revision_id:
            raise ValueError("the workflow revision changed; refresh before pausing or resuming")
        if str(row["attempt_run_id"] or "") != expected_generation:
            raise ValueError("the workflow generation changed; refresh before pausing or resuming")
        workflow_status = str(row["status"])
        if (workflow_status not in ("running", "waiting") or int(row["stop_requested"])
                or bool(row["finished_at"])):
            raise ValueError("pause and resume require a live workflow")
        attempt = db.execute("SELECT status, cancel_requested, lease_owner FROM runs WHERE id = ?",
                             (expected_generation,)).fetchone()
        if attempt is None or int(attempt["cancel_requested"] or 0):
            raise ValueError("the current workflow attempt is stopping or unavailable")
        attempt_status = str(attempt["status"])
        owner = str(attempt["lease_owner"] or "")
        if paused:
            can_request = ((workflow_status == "running" and attempt_status == "running" and bool(owner))
                           or (workflow_status == "waiting" and attempt_status == "waiting_workflow" and not owner))
            if not can_request:
                raise ValueError("pause requires the current attempt to be running or parked while waiting")
        else:
            if (workflow_status != "waiting" or attempt_status != "waiting_workflow" or owner):
                raise ValueError("resume requires the current attempt to be parked and to have released its lease")
            if not _workflow_execution_tree_quiet(db, expected_generation):
                raise ValueError("resume is unavailable while child work or an owned process is active")

        actual = bool(row["pause_requested"])
        quiet = _workflow_execution_tree_quiet(db, expected_generation)
        parked = (workflow_status == "waiting" and attempt_status == "waiting_workflow"
                  and not owner and not int(attempt["cancel_requested"] or 0) and quiet)
        now = iso(utcnow())
        if actual != paused:
            reason = (("paused by owner; workflow remains parked" if parked else
                       "pause requested; waiting for current owned work to settle") if paused
                      else "resumed by owner; continuation is eligible")
            db.execute("UPDATE workflow_runs SET pause_requested = ?, reason = ?, updated_at = ? WHERE id = ? "
                       "AND revision_id = ? AND attempt_run_id = ? "
                       "AND status IN ('running','waiting') AND stop_requested = 0",
                       (1 if paused else 0, reason, now, wf_id, expected_revision_id, expected_generation))
        response = {"workflow_run_id": wf_id, "revision_id": expected_revision_id,
                    "attempt_run_id": expected_generation, "status": workflow_status,
                    "paused": paused, "parked": parked}
        db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (scope, idem_key, request_hash, _json(response), now))
    store.bus.notify("workflows", f"workflow:{wf_id}")
    if not paused:
        store.bus.notify("work")
    return response


def workflow_runs_needing_attempt(store: Any, *, limit: int = 4,
                                  quiet_seconds: float = 2.0) -> list[dict[str, Any]]:
    """Live workflow instances whose orchestration attempt is terminal or missing.

    The supervisor only continues an interrupted attempt after a quiet period. Ordinary
    model/runtime failures are returned immediately so the supervisor can settle the
    workflow as failed instead of retrying them as if they were process crashes. A stopped
    instance is never continued, and owned descendants must be quiescent first.
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
                "SELECT status, cancel_requested, doc FROM runs WHERE id = ?", (attempt_id,)).fetchone()
            previous_exit_reason = ""
            if previous is not None:
                try:
                    previous_exit_reason = str(json.loads(str(previous["doc"] or "{}")).get("exit_reason") or "")
                except (TypeError, ValueError):
                    previous_exit_reason = ""
            if int(workflow["pause_requested"]):
                # A paused, parked generation stays parked when its wait resolves. If an
                # active attempt disappeared during a pause request, admit one fresh
                # attempt to establish the parked state; run_attempt observes the bit
                # before interpreting any node.
                if previous is None:
                    if str(workflow["updated_at"]) <= cutoff:
                        ready.append(workflow)
                elif (str(previous["status"]) in terminal
                      and (str(previous["status"]) != "failed"
                           or not is_recoverable_workflow_attempt(
                               str(previous["status"]), previous_exit_reason)
                           or str(workflow["updated_at"]) <= cutoff)):
                    if _workflow_branch_ready(store._db, str(workflow["id"]), attempt_id):
                        ready.append(workflow)
                continue
            if previous is None:
                if str(workflow["updated_at"]) <= cutoff:
                    ready.append(workflow)
            elif (str(previous["status"]) in terminal
                  and (str(previous["status"]) != "failed"
                       or not is_recoverable_workflow_attempt(
                           str(previous["status"]), previous_exit_reason)
                       or str(workflow["updated_at"]) <= cutoff)):
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
        if (str(row["status"]) not in ("pending", "running", "waiting")
                or int(row["stop_requested"])):
            return None
        pause_requested = bool(row["pause_requested"])
        previous = db.execute("SELECT id, status, cancel_requested, doc FROM runs WHERE id = ?",
                              (str(row["attempt_run_id"]),)).fetchone()
        ledger = json.loads(str(row["ledger_json"]) or "{}") or {}
        previous_status = ""
        previous_exit_reason = ""
        if previous is not None:
            if int(previous["cancel_requested"]):
                return None
            previous_status = str(previous["status"])
            try:
                previous_exit_reason = str(json.loads(str(previous["doc"] or "{}")).get("exit_reason") or "")
            except (TypeError, ValueError):
                previous_exit_reason = ""
            if pause_requested:
                if (not is_recoverable_workflow_attempt(previous_status, previous_exit_reason)
                        or not _workflow_branch_ready(
                            db, wf_id, str(row["attempt_run_id"]))):
                    return None
            elif previous_status == "waiting_workflow":
                if str(row["status"]) != "waiting" or not _workflow_branch_ready(
                        db, wf_id, str(row["attempt_run_id"])):
                    return None
            elif (previous_status not in _TERMINAL_VALUES
                  or (previous_status != "outcome_unknown"
                      and not is_recoverable_workflow_attempt(previous_status, previous_exit_reason))):
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
        continuations = int(ledger.get("attempts", 0))
        is_recovery = previous is not None and is_recoverable_workflow_attempt(
            previous_status, previous_exit_reason)
        recoveries = int(ledger.get("recoveries", 0))
        if is_recovery and recoveries >= MAX_AUTOMATIC_WORKFLOW_RECOVERIES:
            return None
        attempt = 2 + continuations
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
        ledger["attempts"] = continuations + 1
        if is_recovery:
            ledger["recoveries"] = recoveries + 1
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
        pause = db.execute("SELECT pause_requested FROM workflow_runs WHERE id = ?", (wf_id,)).fetchone()
        if pause is not None and int(pause["pause_requested"]):
            raise WorkflowPauseRequested("the owner requested a pause before this node started")
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
        if row is not None and str(row["status"]) == "pending":
            pending_count = int(db.execute(
                """SELECT COUNT(*) FROM workflow_questions
                   WHERE workflow_run_id = ? AND revision_id = ? AND attempt_run_id = ?
                     AND status = 'pending'""",
                (wf_id, revision_id, owner_run_id),
            ).fetchone()[0])
            # Publish the human-wait state in the same transaction as the durable
            # question so readers never observe a pending question with a running
            # workflow status. The attempt itself is parked immediately afterward.
            cur = db.execute(
                """UPDATE workflow_runs SET status = 'waiting', reason = ?, updated_at = ?
                   WHERE id = ? AND revision_id = ? AND attempt_run_id = ?
                     AND stop_requested = 0 AND status IN ('pending','running','waiting')""",
                (f"waiting for {pending_count} answer(s)", iso(utcnow()),
                 wf_id, revision_id, owner_run_id),
            )
            if cur.rowcount != 1:
                raise ValueError("workflow question could not publish a current waiting state")
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


def pending_questions_for_review(store: Any, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Read pending questions with only their workflow association for a review projection."""
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("pending workflow question pagination is out of range")
    with store._lock:
        rows = store._db.execute(
            """SELECT q.*, w.bot_id, w.revision_id, w.status AS workflow_status
                 FROM workflow_questions q JOIN workflow_runs w ON w.id = q.workflow_run_id
                WHERE q.status = 'pending' AND q.revision_id = w.revision_id
                  AND q.attempt_run_id = w.attempt_run_id
                  AND w.status IN ('pending','running','waiting') AND w.stop_requested = 0
                ORDER BY q.asked_at, q.id LIMIT ? OFFSET ?""",
            (limit, offset)).fetchall()
    return [dict(row) for row in rows]


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
        current = workflow_run(store, wf_id) or {}
        saved_revision = revision(store, str(current.get("revision_id") or ""))
        output_sites = (saved_revision or {}).get("plan", {}).get("outputs", [])
        # The stop finalizer shares the same output categories as ordinary terminal
        # outcomes; node counts still describe execution state independently.
        from .runtime import workflow_result_projection

        result = workflow_result_projection(store, wf_id, status=outcome,
                                            output_sites=output_sites)
        if update_workflow_run(store, wf_id, status=outcome,
                               reason=(run.error or run.exit_reason or "stopped")[:500],
                               result=result, finished=True):
            changed += 1
    return changed
