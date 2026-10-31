"""May this state directory admit new work right now?

Two refusals, one gate, answered inside the write transaction that would create the work:

- a **restore hold**, because an operator is reviewing a database restore and nothing may start
  until they record that review (ADR-0008);
- a **retired assistant**, because the owner archived it and it accepts no new work (ADR-0026).

Every transaction in the store that inserts a run calls this, passing the Bot it is about to give
work to. That is what makes both promises structural rather than something each caller has to
remember, and it is why a new admission path only has to reuse the existing call.
"""
from __future__ import annotations

import sqlite3
from typing import Optional


def restore_hold(db: sqlite3.Connection) -> Optional[str]:
    """The id of an activated-restore review that is still pending, or None."""
    row = db.execute(
        "SELECT id FROM state_restores WHERE activated_at IS NULL AND superseded_by = '' LIMIT 1").fetchone()
    return row[0] if row else None


def assert_ready(db: sqlite3.Connection, bot_id: str = "") -> None:
    """Restore hold first, then a retired assistant; ``bot_id`` empty skips the lifecycle check."""
    from . import bot_lifecycle
    from .state_snapshot import ExecutionHeld

    if restore_id := restore_hold(db):
        raise ExecutionHeld(restore_id)
    bot_lifecycle.assert_accepts_work(db, bot_id)
