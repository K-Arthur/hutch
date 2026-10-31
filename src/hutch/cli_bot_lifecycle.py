"""Bot lifecycle commands: retire an assistant, and bring it back.

The command is a thin shell over the same command layer the JSON API uses
(``hutch.bot_lifecycle``); no storage logic lives here. ``archive`` and
``restore`` keep the assistant and its history and only stop it accepting new
work, which is why they are separate from ``pause`` (schedules only) and from
``destroy`` (permanent, governed erasure).
"""
from __future__ import annotations

import hashlib
import json

import typer

from . import bot_lifecycle


def install_bot_lifecycle_commands(bot_app, store_factory, require_bot, err, console) -> None:
    """Attach archive and restore to the existing bot command group."""

    @bot_app.command("archive")
    def bot_archive(name: str = typer.Argument(...)) -> None:
        """Retire an assistant: no new work, but every chat and run is kept."""
        _set_archived(name, True, store_factory, require_bot, err, console)

    @bot_app.command("restore")
    def bot_restore(name: str = typer.Argument(...)) -> None:
        """Bring an archived assistant back; its chats and schedules are intact."""
        _set_archived(name, False, store_factory, require_bot, err, console)


def _set_archived(name, archived, store_factory, require_bot, err, console) -> None:
    """One refusal path for both directions, with the same rules as the dashboard."""
    store = store_factory()
    require_bot(store, name)
    digest = hashlib.sha256(json.dumps({"bot": name, "archived": archived}, sort_keys=True).encode()).hexdigest()
    try:
        bot, changed = bot_lifecycle.archive_bot(store, name, archived,
                                                 idem_key=f"cli:archive:{name}:{archived}",
                                                 request_hash=digest)
    except PermissionError as exc:
        err.print(f"[red]not archived:[/red] {exc}")
        raise typer.Exit(code=1) from None
    except bot_lifecycle.ArchiveRefused as exc:
        err.print(f"[red]not archived:[/red] run {exc.run_id} is still {exc.status}; stop it first")
        raise typer.Exit(code=1) from None
    state = "archived" if bot.archived else "restored"
    console.print(f"{state} {bot.name}" + ("" if changed else " (already in that state)"))
    if bot.archived:
        console.print("New work is refused while archived; conversations, runs and memory are kept.")
