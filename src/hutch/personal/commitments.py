"""Persistence for commitments: durable promises with provenance and evidence.

All reads and writes go through the owning Store's connection and lock, so this
module never opens a second database and never bypasses the single-writer rule.
Mutations are atomic compare-and-swap units; each one appends an audit event in
the same transaction.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..models import iso, utcnow
from ..store import RevisionConflict
from .models import (
    Commitment, CommitmentPriority, CommitmentStatus, CompletionKind, MAX_DEPENDENCIES,
)

#: sentinel: list across every visible scope (personal + all spaces)
ANY_SPACE = object()
DEFAULT_LIMIT = 200


def public(commitment: Commitment, *, blocked: bool = False,
           now: Optional[str] = None) -> dict[str, Any]:
    """API projection with the derived flags; the caller's clock keeps Today consistent."""
    current = now or iso(utcnow())
    data = commitment.model_dump(mode="json")
    data["blocked"] = blocked
    data["overdue"] = bool(commitment.due_at and commitment.due_at < current
                           and commitment.status is CommitmentStatus.open)
    return data


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row(row) -> Commitment:
    data = dict(row)
    data["dependencies"] = json.loads(data.pop("dependencies") or "[]")
    data["status"] = CommitmentStatus(data["status"])
    data["priority"] = CommitmentPriority(data["priority"])
    if data.get("completion_kind"):
        data["completion_kind"] = CompletionKind(data["completion_kind"])
    return Commitment(**data)


class CommitmentRepo:
    def __init__(self, store):
        self.store = store

    # ------------------------------------------------------------- reads

    def get(self, commitment_id: str) -> Optional[Commitment]:
        with self.store._lock:
            row = self.store._db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        return _row(row) if row else None

    def list(self, *, status: Optional[str] = None, space: Any = ANY_SPACE,
             include_proposed: bool = True, due_before: Optional[str] = None,
             due_after: Optional[str] = None, limit: int = DEFAULT_LIMIT,
             offset: int = 0) -> list[Commitment]:
        clauses, args = ["1=1"], []
        if status:
            clauses.append("status = ?")
            args.append(status)
        if space is not ANY_SPACE:
            if space is None:
                clauses.append("space_id IS NULL")
            else:
                clauses.append("space_id = ?")
                args.append(space)
        if not include_proposed:
            clauses.append("confirmation = 'confirmed'")
        if due_before:
            clauses.append("due_at IS NOT NULL AND due_at < ?")
            args.append(due_before)
        if due_after:
            clauses.append("due_at IS NOT NULL AND due_at >= ?")
            args.append(due_after)
        args += [max(1, min(int(limit), 500)), max(0, int(offset))]
        query = ("SELECT * FROM commitments WHERE " + " AND ".join(clauses) +
                 " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'done' THEN 1 ELSE 2 END, "
                 "due_at IS NULL, due_at, created_at, id LIMIT ? OFFSET ?")
        with self.store._lock:
            rows = self.store._db.execute(query, args).fetchall()
        return [_row(row) for row in rows]

    def blocked_map(self, commitment_ids: list[str]) -> dict[str, bool]:
        if not commitment_ids:
            return {}
        marks = ",".join("?" for _ in commitment_ids)
        with self.store._lock:
            rows = self.store._db.execute(
                f"SELECT DISTINCT d.commitment_id FROM commitment_dependencies d "
                f"JOIN commitments c ON c.id = d.depends_on_id "
                f"WHERE c.status = 'open' AND d.commitment_id IN ({marks})",
                commitment_ids).fetchall()
        blocked = {row["commitment_id"] for row in rows}
        return {cid: cid in blocked for cid in commitment_ids}

    def events(self, commitment_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT id, commitment_id, revision, kind, actor, detail_json, created_at "
                "FROM commitment_events WHERE commitment_id = ? ORDER BY id DESC LIMIT ?",
                (commitment_id, max(1, min(int(limit), 500)))).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail_json"])} for row in rows]

    def find_open_proposal(self, *, run_id: str, title: str) -> Optional[Commitment]:
        if not run_id:
            return None
        with self.store._lock:
            row = self.store._db.execute(
                "SELECT * FROM commitments WHERE run_id = ? AND title = ? AND status = 'open' "
                "AND confirmation = 'proposed' ORDER BY created_at DESC LIMIT 1",
                (run_id, title)).fetchone()
        return _row(row) if row else None

    def count_open(self, *, space: Any = ANY_SPACE) -> int:
        clauses, args = ["status = 'open'"], []
        if space is not ANY_SPACE:
            if space is None:
                clauses.append("space_id IS NULL")
            else:
                clauses.append("space_id = ?")
                args.append(space)
        with self.store._lock:
            row = self.store._db.execute(
                "SELECT COUNT(*) AS n FROM commitments WHERE " + " AND ".join(clauses), args).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------ writes

    def create(self, commitment: Commitment, *, idem_key: str = "", request_hash: str = "",
               actor: str = "") -> tuple[Commitment, bool]:
        scope = "api:v1:commitments:create"
        with self.store._tx() as db:
            if idem_key:
                replay = self.store._idempotency_replay(db, scope, idem_key, request_hash)
                if replay is not None:
                    return _row(replay), False
            if commitment.space_id:
                exists = db.execute("SELECT 1 FROM spaces WHERE id = ? AND archived = 0",
                                    (commitment.space_id,)).fetchone()
                if not exists:
                    raise ValueError("no such shared space")
            core = commitment.model_dump(mode="json")
            core["dependencies"] = json.dumps(core["dependencies"])
            keys = ", ".join(core)
            marks = ", ".join("?" for _ in core)
            db.execute(f"INSERT INTO commitments ({keys}) VALUES ({marks})", tuple(core.values()))
            self._event(db, commitment, "created", actor or commitment.created_by,
                        {"confirmation": commitment.confirmation, "space_id": commitment.space_id})
            response = public(commitment)
            if idem_key:
                db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (scope, idem_key, request_hash, _canonical(response), iso(utcnow())))
            return commitment, True

    def _event(self, db, commitment: Commitment, kind: str, actor: str, detail: dict) -> None:
        db.execute("INSERT INTO commitment_events (commitment_id, revision, kind, actor, detail_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   (commitment.id, commitment.revision, kind, actor,
                    _canonical(detail), iso(utcnow())))

    def _require(self, db, commitment_id: str) -> Commitment:
        row = db.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
        if row is None:
            raise KeyError(commitment_id)
        return _row(row)

    @staticmethod
    def _check_revision(current: Commitment, expected_revision: Optional[int]) -> None:
        if expected_revision is not None and current.revision != expected_revision:
            raise RevisionConflict("this commitment changed elsewhere; reload it before editing")

    def update(self, commitment_id: str, changes: dict[str, Any], *, expected_revision: Optional[int] = None,
               actor: str = "owner") -> Commitment:
        editable = {"title", "detail", "priority", "due_at", "due_timezone", "category", "space_id"}
        unknown = set(changes) - editable
        if unknown:
            raise ValueError(f"not editable through this command: {', '.join(sorted(unknown))}")
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if changes.get("space_id"):
                exists = db.execute("SELECT 1 FROM spaces WHERE id = ? AND archived = 0",
                                    (changes["space_id"],)).fetchone()
                if not exists:
                    raise ValueError("no such shared space")
            merged = current.model_dump(mode="json")
            # Pydantic re-validates the whole record, so an invalid due date or zone fails before the write.
            merged.update({key: changes[key] for key in changes})
            merged["revision"] = current.revision + 1
            merged["updated_at"] = iso(utcnow())
            updated = Commitment(**{**merged, "dependencies": merged.get("dependencies", [])})
            self._write(db, updated)
            self._event(db, updated, "updated", actor, {"changed": sorted(changes)})
            return updated

    def _write(self, db, commitment: Commitment) -> None:
        data = commitment.model_dump(mode="json")
        data["dependencies"] = json.dumps(data["dependencies"])
        assignments = ", ".join(f"{key} = ?" for key in data if key != "id")
        values = tuple(value for key, value in data.items() if key != "id") + (commitment.id,)
        db.execute(f"UPDATE commitments SET {assignments} WHERE id = ?", values)

    def confirm(self, commitment_id: str, *, expected_revision: Optional[int] = None,
                actor: str = "owner") -> Commitment:
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if current.confirmation == "confirmed":
                return current
            if current.created_by == "owner":
                raise ValueError("this commitment is already the owner's")
            merged = current.model_dump(mode="json")
            merged.update(confirmation="confirmed", revision=current.revision + 1, updated_at=iso(utcnow()))
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "confirmed", actor, {})
            return updated

    def complete(self, commitment_id: str, *, evidence: str, kind: CompletionKind,
                 actor: str, expected_revision: Optional[int] = None) -> Commitment:
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if current.status is CommitmentStatus.done:
                return current
            if current.confirmation == "proposed":
                raise ValueError("confirm this commitment before marking it done")
            merged = current.model_dump(mode="json")
            merged.update(status="done", completed_at=iso(utcnow()), completion_evidence=evidence,
                          completion_kind=kind.value, completed_by=actor,
                          revision=current.revision + 1, updated_at=iso(utcnow()))
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "completed", actor, {"completion_kind": kind.value})
            return updated

    def verify_completion(self, commitment_id: str, *, actor: str = "owner",
                          expected_revision: Optional[int] = None) -> Commitment:
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if current.status is not CommitmentStatus.done:
                raise ValueError("only a completed commitment can be verified")
            if current.completion_kind is CompletionKind.owner_confirmed:
                return current
            merged = current.model_dump(mode="json")
            merged.update(completion_kind="owner_confirmed", completed_by=actor,
                          revision=current.revision + 1, updated_at=iso(utcnow()))
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "verified", actor, {"previous_kind": current.completion_kind.value})
            return updated

    def reopen(self, commitment_id: str, *, actor: str = "owner",
               expected_revision: Optional[int] = None) -> Commitment:
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if current.status is CommitmentStatus.open:
                return current
            if current.status is CommitmentStatus.cancelled:
                raise ValueError("a cancelled commitment cannot be reopened; create a new one")
            merged = current.model_dump(mode="json")
            merged.update(status="open", completed_at=None, completion_evidence="",
                          completion_kind=None, completed_by="",
                          revision=current.revision + 1, updated_at=iso(utcnow()))
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "reopened", actor, {})
            return updated

    def cancel(self, commitment_id: str, *, actor: str = "owner",
               expected_revision: Optional[int] = None) -> Commitment:
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            if current.status is CommitmentStatus.cancelled:
                return current
            merged = current.model_dump(mode="json")
            merged.update(status="cancelled", revision=current.revision + 1, updated_at=iso(utcnow()))
            merged.update(completed_at=None, completion_evidence="", completion_kind=None, completed_by="")
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "cancelled", actor, {})
            return updated

    def set_dependencies(self, commitment_id: str, dependency_ids: list[str], *, actor: str = "owner",
                         expected_revision: Optional[int] = None) -> Commitment:
        wanted = sorted({str(item) for item in dependency_ids if str(item).strip()})
        if len(wanted) > MAX_DEPENDENCIES:
            raise ValueError(f"at most {MAX_DEPENDENCIES} dependencies are allowed")
        if commitment_id in wanted:
            raise ValueError("a commitment cannot depend on itself")
        with self.store._tx() as db:
            current = self._require(db, commitment_id)
            self._check_revision(current, expected_revision)
            for dependency in wanted:
                row = db.execute("SELECT 1 FROM commitments WHERE id = ?", (dependency,)).fetchone()
                if row is None:
                    raise KeyError(dependency)
            # Direct cycle check: a dependency that already depends on this commitment would close a loop.
            marks = ",".join("?" for _ in wanted) or "''"
            cyclic = db.execute(
                f"SELECT 1 FROM commitment_dependencies WHERE commitment_id IN ({marks}) "
                f"AND depends_on_id = ? LIMIT 1", (*wanted, commitment_id)).fetchone()
            if cyclic:
                raise ValueError("that dependency would create a cycle")
            db.execute("DELETE FROM commitment_dependencies WHERE commitment_id = ?", (commitment_id,))
            now = iso(utcnow())
            for dependency in wanted:
                db.execute("INSERT INTO commitment_dependencies (commitment_id, depends_on_id, created_at) "
                           "VALUES (?, ?, ?)", (commitment_id, dependency, now))
            merged = current.model_dump(mode="json")
            merged.update(dependencies=wanted, revision=current.revision + 1, updated_at=now)
            updated = Commitment(**merged)
            self._write(db, updated)
            self._event(db, updated, "dependencies", actor, {"count": len(wanted)})
            return updated
