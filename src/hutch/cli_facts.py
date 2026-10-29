"""Bot reference-fact commands: reversible archive and governed permanent purge."""
from __future__ import annotations

from typing import Optional

import typer

from . import fact_purge


def install_bot_fact_commands(bot_app, store_factory, require_bot, err, console) -> None:
    """Attach the fact-memory commands to the existing bot Typer group."""
    _install_forget(bot_app, store_factory, require_bot, console)
    _install_purge(bot_app, store_factory, require_bot, err, console)


def _install_forget(bot_app, store_factory, require_bot, console) -> None:
    """Register the reversible archive command; it never claims to erase content."""

    @bot_app.command("forget")
    def bot_forget(name: str = typer.Argument(...),
                   key: Optional[str] = typer.Option(None, "--key")) -> None:
        """Archive fact memory (all scopes, or one key); keep history. Revoke sticky allows unless --key."""
        store = store_factory(); bot = require_bot(store, name)
        if key:
            store.forget(bot.id, key)
            console.print(f"archived '{key}' across this bot's scopes; history and backups remain")
        else:
            store.archive_all_facts(bot.id)
            for sticky in store.list_sticky_allows(bot.id):
                store.revoke_sticky(bot.id, sticky)
            console.print("fact memory archived and sticky allows revoked; history and backups remain")


def _install_purge(bot_app, store_factory, require_bot, err, console) -> None:
    """Register the governed two-step permanent-deletion command."""

    @bot_app.command("purge")
    def bot_purge(name: str = typer.Argument(...),
                  key: Optional[str] = typer.Option(None, "--key",
                                                    help="permanently erase saved facts with this exact key"),
                  all_facts: bool = typer.Option(False, "--all",
                                                 help="permanently erase every saved reference fact for this bot"),
                  yes: bool = typer.Option(False, "--yes", "-y",
                                           help="skip the typed confirmation prompt")) -> None:
        """Permanently erase saved reference-fact content after an explicit two-step confirmation.

        This cannot be undone by Hutch. Conversation history, transcripts, files,
        provider-side copies and backups are not erased; the preview names what remains.
        """
        if (key is None) == (not all_facts):
            err.print("[red]choose exactly one of --key or --all[/red]")
            raise typer.Exit(code=1)
        store = store_factory(); bot = require_bot(store, name)
        preview = _preview(store, bot, key, all_facts, err)
        _print_preview(preview, key, all_facts, console)
        expected = key if key else bot.name
        if not yes and not _typed_confirmation(expected, err):
            raise typer.Exit(code=1)
        result = _confirm(store, bot, preview, expected, err)
        console.print(f"[green]erased[/green] {result['counts']['total']} saved row(s); "
                      f"credential-free audit kept as {result['request_id']}")


def _preview(store, bot, key, all_facts, err) -> dict:
    """Issue a purge preview or exit with the refusal reason."""
    try:
        return fact_purge.preview(store, bot.id, key=key, all=all_facts, actor='cli')
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


def _print_preview(preview, key, all_facts, console) -> None:
    """Show exact erase counts and the consequences that the purge cannot remove."""
    counts = preview['counts']
    console.print(f"scope: {'all saved reference facts' if all_facts else repr(key)}")
    console.print(f"erase: {counts['fact_revisions']} fact revision(s), "
                  f"{counts['outgoing_shares']} outgoing share(s), "
                  f"{counts['incoming_shares']} incoming share(s), "
                  f"{counts['task_snapshots']} task snapshot(s), "
                  f"{counts['receipts_redacted']} API receipt(s), "
                  f"{counts['legacy_rows']} legacy row(s)")
    for line in preview['remaining']:
        console.print(f"  remains: {line}")


def _typed_confirmation(expected, err) -> bool:
    """Require the exact scope text before a destructive confirmation."""
    typed = typer.prompt(f"type {expected!r} to permanently erase this scope")
    if typed.strip() == expected:
        return True
    err.print("[red]confirmation did not match; nothing was erased[/red]")
    return False


def _confirm(store, bot, preview, expected, err) -> dict:
    """Apply the previewed purge or exit with the refusal reason."""
    try:
        return fact_purge.confirm(store, bot.id, preview['request_id'],
                                  token=preview['token'], confirmation=expected, actor='cli')
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
