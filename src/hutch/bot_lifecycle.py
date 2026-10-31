"""Assistant lifecycle: retiring a Bot without deleting it.

`archived` is a lifecycle state, not a permission and not a deletion. It answers one question: may
this assistant be given new work? Everything else about the Bot is preserved, so the owner can read
its conversations, review its runs and bring it back.

Three refusals are deliberately distinct, because each calls for a different action from the owner:

- ``BotArchived``: restore the assistant, or choose a different one.
- ``ArchiveRefused``: stop the run that is still working, then archive.
- ``PermissionError``: the coordinator role has to move first.

Nothing here decides *whether* to archive; that is the Store's transactional command. This module
holds the rules so that every admission path shares one definition of "accepts new work", and so
that the Store module does not grow another orchestration block.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .models import ACTIVE_STATUSES, Bot


class BotArchived(ValueError):
    """New work was refused because the owner retired this assistant without deleting it.

    Derives from ``ValueError`` so existing request handlers already translate it into a client
    error rather than a server fault, matching the way an archived conversation is refused.
    """

    def __init__(self, bot_id: str, name: str = ""):
        super().__init__(f"assistant {name or bot_id} is archived; restore it before starting new work")
        self.bot_id = bot_id
        self.name = name


class ArchiveRefused(RuntimeError):
    """Archiving was refused because one of the assistant's runs is still active."""

    def __init__(self, run_id: str, status: str):
        super().__init__(f"run {run_id} is still {status}")
        self.run_id = run_id
        self.status = status


def _stored_bot(db: sqlite3.Connection, bot_id: str) -> Bot | None:
    row = db.execute("SELECT doc FROM bots WHERE id = ?", (bot_id,)).fetchone()
    if row is None:
        return None
    try:
        return Bot.from_store_json(row["doc"])
    except (TypeError, ValueError):
        return None


def assert_accepts_work(db: sqlite3.Connection, bot_id: str) -> None:
    """One admission predicate, called inside the write transaction that admits the work.

    A missing Bot is not this function's concern: callers that need existence raise ``KeyError``.
    An unreadable document is also not decided here; the run paths validate that separately.
    """
    bot = _stored_bot(db, bot_id)
    if bot is not None and bot.archived:
        row = db.execute("SELECT name FROM bots WHERE id = ?", (bot_id,)).fetchone()
        raise BotArchived(bot_id, str(row["name"]) if row else bot.name)


def check_can_archive(db: sqlite3.Connection, bot: Bot, archived: bool) -> None:
    """Refuse an archive that would strand work or remove the product's main entry point.

    Only a transition *into* the archived state is checked. Restoring is always allowed: an owner
    must be able to undo a retirement even if a newer run appeared in the meantime.
    """
    if not archived or bot.archived:
        return
    settings: Any = db.execute("SELECT coordinator_bot_id FROM workspace_settings WHERE id = 1").fetchone()
    if settings is not None and settings["coordinator_bot_id"] == bot.id:
        raise PermissionError("the workspace coordinator cannot be archived; make another assistant main first")
    live = tuple(status.value for status in ACTIVE_STATUSES)
    active = db.execute(
        f"SELECT id, status FROM runs WHERE bot_id = ? AND status IN ({','.join('?' for _ in live)}) "
        "ORDER BY created_at LIMIT 1", (bot.id, *live)).fetchone()
    if active is not None:
        raise ArchiveRefused(active["id"], active["status"])


def is_archived(bot: Bot) -> bool:
    """Read-side helper for views that must not offer a retired assistant for new work."""
    return bool(bot.archived)


def archive_bot(store: Any, ref: str, archived: bool, *, idem_key: str, request_hash: str) -> tuple[Bot, bool]:
    """Retire an assistant without deleting it, or bring it back, in one write transaction.

    Conversations, messages, runs, events and memory records are untouched in both directions.
    Returns the Bot and whether the stored state actually changed, so a repeated command is
    distinguishable from a first one.
    """
    import json

    from .models import iso, utcnow

    with store._tx() as db:
        row = db.execute("SELECT id, name, doc FROM bots WHERE id = ? OR name = ? LIMIT 1",
                         (ref, ref)).fetchone()
        if row is None:
            raise KeyError(ref)
        bot = Bot.from_store_json(row["doc"])
        bot.id = str(row["id"])
        scope = f"api:v1:bot:{bot.id}:archive"
        if store._idempotency_replay(db, scope, idem_key, request_hash) is not None:
            stored = db.execute("SELECT doc FROM bots WHERE id = ?", (bot.id,)).fetchone()
            return (Bot.from_store_json(stored["doc"]) if stored else bot), False
        check_can_archive(db, bot, archived)
        changed = bot.archived != archived
        bot.archived = archived
        db.execute("UPDATE bots SET doc = ? WHERE id = ?", (bot.store_json(), bot.id))
        db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?)",
                   (scope, idem_key, request_hash,
                    json.dumps({"bot_id": bot.id, "archived": archived}, ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")), iso(utcnow())))
    store.bus.notify("work", "bots")
    return bot, changed
