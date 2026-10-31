"""Persistence for shared spaces: membership and per-assistant scope grants.

A space is a data-scope boundary, not an account system and not a credential
store. The only execution authority it confers is the explicit, revocable
`bot_space_grants` row that lets one assistant read and write commitments in
that space through its tools. Everything else (integrations, memory, run
evidence, documents) keeps its existing per-bot ownership.
"""
from __future__ import annotations

from typing import Any, Optional

from ..models import iso, utcnow
from ..store import RevisionConflict
from .models import (
    Space, SpaceKind, SpaceMember, SpaceMemberStatus, SpaceRole,
)
from .commitments import CommitmentRepo


def space_public(space: Space, *, members: list[SpaceMember], bot_ids: list[str],
                 open_commitments: int) -> dict[str, Any]:
    return {
        **space.model_dump(mode="json"),
        "members": [member.model_dump(mode="json") for member in members],
        "active_members": sum(1 for member in members if member.status is SpaceMemberStatus.active),
        "bot_grants": bot_ids,
        "open_commitments": open_commitments,
    }


class SpaceRepo:
    def __init__(self, store):
        self.store = store
        self.commitments = CommitmentRepo(store)

    # ------------------------------------------------------------- reads

    def get(self, space_id: str) -> Optional[Space]:
        with self.store._lock:
            row = self.store._db.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()
        return Space.model_validate(dict(row)) if row else None

    def list(self, *, include_archived: bool = False) -> list[Space]:
        clause = "" if include_archived else " WHERE archived = 0"
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT * FROM spaces" + clause + " ORDER BY created_at, id").fetchall()
        return [Space.model_validate(dict(row)) for row in rows]

    def members(self, space_id: str, *, include_revoked: bool = True) -> list[SpaceMember]:
        clause = "" if include_revoked else " AND status = 'active'"
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT * FROM space_members WHERE space_id = ?" + clause +
                " ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'adult' THEN 1 ELSE 2 END, created_at",
                (space_id,)).fetchall()
        return [SpaceMember.model_validate(dict(row)) for row in rows]

    def grants(self, space_id: str) -> list[str]:
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT bot_id FROM bot_space_grants WHERE space_id = ? ORDER BY bot_id",
                (space_id,)).fetchall()
        return [row["bot_id"] for row in rows]

    def bot_space_ids(self, bot_id: str) -> set[str]:
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT g.space_id FROM bot_space_grants g JOIN spaces s ON s.id = g.space_id "
                "WHERE g.bot_id = ? AND s.archived = 0", (bot_id,)).fetchall()
        return {row["space_id"] for row in rows}

    def bot_can_access(self, bot_id: str, space_id: str) -> bool:
        return space_id in self.bot_space_ids(bot_id)

    def summary(self) -> list[dict[str, Any]]:
        return [space_public(space, members=self.members(space.id), bot_ids=self.grants(space.id),
                             open_commitments=self.commitments.count_open(space=space.id))
                for space in self.list()]

    def public(self, space_id: str) -> dict[str, Any]:
        space = self.get(space_id)
        if space is None:
            raise KeyError(space_id)
        return space_public(space, members=self.members(space_id), bot_ids=self.grants(space_id),
                            open_commitments=self.commitments.count_open(space=space_id))

    # ------------------------------------------------------------ writes

    def create(self, space: Space) -> Space:
        with self.store._tx() as db:
            data = space.model_dump(mode="json")
            keys = ", ".join(data)
            db.execute(f"INSERT INTO spaces ({keys}) VALUES ({', '.join('?' for _ in data)})",
                       tuple(data.values()))
            return space

    def update(self, space_id: str, changes: dict[str, Any], *, expected_revision: int) -> Space:
        editable = {"name", "description", "kind"}
        unknown = set(changes) - editable
        if unknown:
            raise ValueError(f"not editable through this command: {', '.join(sorted(unknown))}")
        with self.store._tx() as db:
            row = db.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()
            if row is None:
                raise KeyError(space_id)
            current = Space.model_validate(dict(row))
            if current.revision != expected_revision:
                raise RevisionConflict("this shared space changed elsewhere; reload it before editing")
            merged = current.model_dump(mode="json")
            merged.update({key: changes[key] for key in changes})
            merged.update(revision=current.revision + 1, updated_at=iso(utcnow()))
            updated = Space(**merged)
            db.execute("UPDATE spaces SET name = ?, kind = ?, description = ?, revision = ?, updated_at = ? "
                       "WHERE id = ? AND revision = ?",
                       (updated.name, updated.kind.value, updated.description, updated.revision,
                        updated.updated_at, space_id, expected_revision))
            return updated

    def archive(self, space_id: str, *, expected_revision: int) -> Space:
        with self.store._tx() as db:
            row = db.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()
            if row is None:
                raise KeyError(space_id)
            current = Space.model_validate(dict(row))
            if current.revision != expected_revision:
                raise RevisionConflict("this shared space changed elsewhere; reload it before archiving")
            now = iso(utcnow())
            db.execute("UPDATE spaces SET archived = 1, revision = revision + 1, updated_at = ? "
                       "WHERE id = ? AND revision = ?", (now, space_id, expected_revision))
            # Archiving revokes assistant access immediately; the shared history stays readable to the owner.
            db.execute("DELETE FROM bot_space_grants WHERE space_id = ?", (space_id,))
            return Space.model_validate({**dict(row), "archived": 1, "revision": current.revision + 1,
                                         "updated_at": now})

    def add_member(self, space_id: str, member: SpaceMember) -> SpaceMember:
        with self.store._tx() as db:
            if db.execute("SELECT 1 FROM spaces WHERE id = ? AND archived = 0", (space_id,)).fetchone() is None:
                raise KeyError(space_id)
            row = db.execute("SELECT * FROM space_members WHERE space_id = ? AND member_id = ?",
                             (space_id, member.member_id)).fetchone()
            if row is not None:
                existing = SpaceMember.model_validate(dict(row))
                if existing.status is SpaceMemberStatus.active:
                    raise ValueError("that participant is already a member of this space")
                db.execute("UPDATE space_members SET display_name = ?, role = ?, status = 'active', "
                           "updated_at = ? WHERE space_id = ? AND member_id = ?",
                           (member.display_name, member.role.value, iso(utcnow()), space_id, member.member_id))
                return SpaceMember.model_validate({**member.model_dump(mode="json"), "status": "active"})
            data = {**member.model_dump(mode="json"), "space_id": space_id}
            keys = ", ".join(data)
            db.execute(f"INSERT INTO space_members ({keys}) VALUES ({', '.join('?' for _ in data)})",
                       tuple(data.values()))
            return SpaceMember.model_validate(data)

    def update_member(self, space_id: str, member_id: str, changes: dict[str, Any]) -> SpaceMember:
        editable = {"display_name", "role", "status"}
        unknown = set(changes) - editable
        if unknown:
            raise ValueError(f"not editable through this command: {', '.join(sorted(unknown))}")
        with self.store._tx() as db:
            row = db.execute("SELECT * FROM space_members WHERE space_id = ? AND member_id = ?",
                             (space_id, member_id)).fetchone()
            if row is None:
                raise KeyError(member_id)
            current = SpaceMember.model_validate(dict(row))
            merged = current.model_dump(mode="json")
            merged.update({key: changes[key] for key in changes})
            merged["updated_at"] = iso(utcnow())
            updated = SpaceMember(**merged)
            self._protect_last_owner(db, space_id, current, updated)
            db.execute("UPDATE space_members SET display_name = ?, role = ?, status = ?, updated_at = ? "
                       "WHERE space_id = ? AND member_id = ?",
                       (updated.display_name, updated.role.value, updated.status.value,
                        updated.updated_at, space_id, member_id))
            return updated

    def revoke_member(self, space_id: str, member_id: str) -> SpaceMember:
        return self.update_member(space_id, member_id, {"status": "revoked"})

    @staticmethod
    def _protect_last_owner(db, space_id: str, current: SpaceMember, updated: SpaceMember) -> None:
        losing_owner = (current.role is SpaceRole.owner and current.status is SpaceMemberStatus.active
                        and (updated.role is not SpaceRole.owner
                             or updated.status is not SpaceMemberStatus.active))
        if not losing_owner:
            return
        owners = db.execute("SELECT COUNT(*) AS n FROM space_members WHERE space_id = ? AND role = 'owner' "
                            "AND status = 'active' AND member_id != ?", (space_id, current.member_id)).fetchone()
        if int(owners["n"]) == 0:
            raise ValueError("a shared space keeps at least one active owner")

    def grant(self, space_id: str, bot_id: str, *, expected_revision: Optional[int] = None) -> dict[str, Any]:
        with self.store._tx() as db:
            row = db.execute("SELECT * FROM spaces WHERE id = ? AND archived = 0", (space_id,)).fetchone()
            if row is None:
                raise KeyError(space_id)
            if expected_revision is not None and Space.model_validate(dict(row)).revision != expected_revision:
                raise RevisionConflict("this shared space changed elsewhere; reload it before changing access")
            if db.execute("SELECT 1 FROM bots WHERE id = ?", (bot_id,)).fetchone() is None:
                raise KeyError(bot_id)
            db.execute("DELETE FROM bot_space_grants WHERE space_id = ? AND bot_id = ?", (space_id, bot_id))
            db.execute("INSERT INTO bot_space_grants (space_id, bot_id, created_at) VALUES (?, ?, ?)",
                       (space_id, bot_id, iso(utcnow())))
            return self.public(space_id)

    def revoke_grant(self, space_id: str, bot_id: str) -> dict[str, Any]:
        with self.store._tx() as db:
            db.execute("DELETE FROM bot_space_grants WHERE space_id = ? AND bot_id = ?", (space_id, bot_id))
        return self.public(space_id)
