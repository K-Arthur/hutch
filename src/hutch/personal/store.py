"""Facade wiring the personal operations repositories to the owning Store."""
from __future__ import annotations

from .commitments import ANY_SPACE, CommitmentRepo, public
from .spaces import SpaceRepo, space_public


class PersonalStore:
    """One entry point for personal-operations persistence.

    Callers (API routes, tools, the Today builder) receive this facade from
    Store.personal. It delegates to repositories that all use the same
    connection, lock and transaction context as the rest of Hutch.
    """

    def __init__(self, store):
        self.commitments = CommitmentRepo(store)
        self.spaces = SpaceRepo(store)

    def bot_visible_commitments(self, bot, *, status=None, limit: int = 50):
        """Commitments an assistant may see: personal scope plus its explicitly granted spaces."""
        allowed = self.spaces.bot_space_ids(bot.id)
        personal = self.commitments.list(status=status, space=None, limit=limit)
        shared = []
        for space_id in sorted(allowed):
            shared.extend(self.commitments.list(status=status, space=space_id, limit=limit))
        rows = personal + shared
        rows.sort(key=lambda item: (item.status.value != "open", item.due_at or "9999", item.created_at))
        return rows[:limit]


__all__ = ["ANY_SPACE", "PersonalStore", "public", "space_public"]
