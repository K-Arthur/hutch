"""Bot lifecycle commands: governed whole-Bot permanent deletion.

The command is a thin shell over the same command layer the JSON API uses
(hutch.bot_deletion); no erase logic lives here. hutch bot delete keeps its
reversible meaning (the Bot row plus its data is removed, but the governed
whole-Bot purge is this command).
"""
from __future__ import annotations

import typer


def install_bot_destroy_command(bot_app, store_factory, require_bot, err, console) -> None:
    """Attach the governed permanent-deletion command to the existing bot group."""
    _install_destroy(bot_app, store_factory, require_bot, err, console)


def _install_destroy(bot_app, store_factory, require_bot, err, console) -> None:
    """Register hutch bot destroy; it always previews before it can confirm."""

    @bot_app.command("destroy")
    def bot_destroy(name: str = typer.Argument(..., help="exact Bot name or id"),
                    yes: bool = typer.Option(False, "--yes", "-y",
                                             help="skip the typed confirmation prompt")) -> None:
        """Permanently delete one whole Bot after a two-step confirmation.

        This cannot be undone by Hutch: Bot data, conversations, runs, memory,
        files in the managed state directory and authority rows are erased; the
        preview names what remains. The typed Bot address is always required
        unless --yes was passed, and the preview is always shown.
        """
        store = store_factory()
        _recover(store, err)
        bot = require_bot(store, name)
        preview = _preview(store, bot, err)
        _print_preview(bot, preview, console)
        if not yes and not _typed_confirmation(bot.name, err):
            raise typer.Exit(code=1)
        result = _confirm(store, bot, preview, err)
        counts = result.get('counts', {})
        console.print(f"[green]deleted[/green] bot {bot.name}: erased {counts.get('total', 0):,} "
                      f"record(s); cleanup {result.get('cleanup_state', 'pending')}; "
                      f"evidence kept as {result['request_id']}")


def _recover(store, err) -> None:
    """Resume a committed deletion whose filesystem cleanup was interrupted."""
    from . import bot_deletion
    try:
        bot_deletion.recover_cleanup(store)
    except Exception as exc:
        err.print(f"[red]deletion cleanup recovery failed: {exc}[/red]")
        raise typer.Exit(code=1) from None


def _preview(store, bot, err) -> dict:
    """Issue the preview or exit with the refusal reason; nothing is erased yet."""
    from . import bot_deletion
    try:
        return bot_deletion.preview(store, bot.id, actor='cli')
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


def _print_preview(bot, preview, console) -> None:
    """Show the scope, exact erase counts and the honest list of what remains."""
    counts = preview['counts']
    console.print(f"scope: permanent deletion of bot {bot.name} ({bot.id})")
    for field in sorted(counts):
        if field != 'total':
            console.print(f"erase: {counts[field]:,} {field.replace('_', ' ')}")
    console.print(f"erase: {counts.get('total', 0):,} records in total")
    for line in preview['remaining']:
        console.print(f"  remains: {line}")
    console.print(f"confirmation window expires: {preview['expires_at']}")


def _typed_confirmation(expected: str, err) -> bool:
    """Require the exact Bot address before a destructive confirmation."""
    typed = typer.prompt(f"type {expected!r} to permanently delete this Bot")
    if typed.strip() == expected:
        return True
    err.print("[red]confirmation did not match; nothing was erased[/red]")
    return False


def _confirm(store, bot, preview, err) -> dict:
    """Apply the previewed deletion through the shared command layer or exit nonzero."""
    from . import bot_deletion
    try:
        return bot_deletion.confirm(store, bot.id, preview['request_id'],
                                    token=preview['token'], confirmation=bot.name,
                                    actor='cli', idem_key=f"cli:{preview['request_id']}")
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
