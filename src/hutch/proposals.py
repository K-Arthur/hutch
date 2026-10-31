"""Assistants the main assistant has suggested, waiting for the person.

Grok Bot lets its primary Bot "suggest or create a focused Bot" for a job that needs a long-term owner, and advises that it
"ask before creating several"; OpenClaw requires operator approval before an agent creates another. Here the main assistant
can only *propose*: this module keeps a short, bounded list of pending suggestions (a name, the job, why). Nothing is created
from it. The person opens one, lands in the normal setup review with the name and job filled in, and creates it themselves
(or dismisses it). A proposal disappears on its own once an assistant with that name exists. At most three can wait at once, so
the roster cannot be filled by suggestions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import iso, new_id, utcnow

KEY = "assistant:proposals:v1"
MAX_PENDING = 3
MAX_KEPT = 30
NAME_RANGE = (2, 60)
JOB_RANGE = (10, 800)
WHY_MAX = 300


class ProposalError(ValueError):
    """A suggestion that cannot be recorded, with a reason the main assistant can act on."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _load(store) -> list[dict[str, Any]]:
    raw = store.kv_get(KEY)
    try:
        items = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _save(store, items: list[dict[str, Any]]) -> None:
    store.kv_set(KEY, json.dumps(items[-MAX_KEPT:], sort_keys=True, separators=(",", ":")))


def _taken(store, name: str) -> bool:
    slug = _slug(name)
    return any(slug in {_slug(bot.display_name or ""), _slug(bot.name)} for bot in store.list_bots())


def pending(store) -> list[dict[str, Any]]:
    """Open suggestions, oldest first. One whose name now belongs to an assistant is treated as done."""
    return [item for item in _load(store) if item.get("status") == "pending" and not _taken(store, str(item.get("name", "")))]


def propose(store, *, name: str, job: str, why: str = "", from_bot_id: str = "", conversation_id: str = "") -> dict[str, Any]:
    name, job, why = (name or "").strip(), (job or "").strip(), (why or "").strip()
    if not NAME_RANGE[0] <= len(name) <= NAME_RANGE[1]:
        raise ProposalError(f"the name must be {NAME_RANGE[0]} to {NAME_RANGE[1]} characters")
    if not JOB_RANGE[0] <= len(job) <= JOB_RANGE[1]:
        raise ProposalError(f"describe the job in {JOB_RANGE[0]} to {JOB_RANGE[1]} characters: what it should own and hand back")
    if len(why) > WHY_MAX:
        raise ProposalError(f"the reason must be at most {WHY_MAX} characters")
    if len(_slug(name)) < 2:
        raise ProposalError("the name needs letters or digits")
    if _taken(store, name):
        raise ProposalError(f"an assistant named {name} already exists")
    open_items = pending(store)
    if any(_slug(item["name"]) == _slug(name) for item in open_items):
        raise ProposalError(f"{name} is already suggested and waiting for the person")
    if len(open_items) >= MAX_PENDING:
        raise ProposalError(f"{MAX_PENDING} suggestions are already waiting; ask the person about those before suggesting more")
    item = {"id": new_id("proposal"), "name": name, "job": job, "why": why, "from_bot_id": from_bot_id,
            "conversation_id": conversation_id, "status": "pending", "created_at": iso(utcnow())}
    _save(store, _load(store) + [item])
    return item


def resolve(store, proposal_id: str, status: str) -> dict[str, Any]:
    """Mark one suggestion `dismissed` (or `created`). Raises KeyError for an unknown id."""
    items = _load(store)
    for item in items:
        if item.get("id") == proposal_id:
            item["status"] = status
            item["resolved_at"] = iso(utcnow())
            _save(store, items)
            return item
    raise KeyError(proposal_id)
