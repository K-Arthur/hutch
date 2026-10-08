"""hutch command line interface."""

from __future__ import annotations

import json
import ipaddress
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import get_config
from .models import (
    ApprovalMode,
    Bot,
    CatchUpPolicy,
    Limits,
    InferenceMode,
    RiskTier,
    RunStatus,
    RuntimeKind,
    Schedule,
)
from .lifecycle import TERMINAL
from .store import Store
from .templates import TEMPLATE_INFO, TEMPLATES, gallery, seed
from .tools import ALL_TOOL_NAMES, expand_tools

# NOTE (PF-6): Engine, the runtimes, providers, fastapi and playwright are imported inside the
# commands that need them, so `hutch status` / `hutch version` stay fast.

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="hutch — local-first multi-bot agent platform.")
bot_app = typer.Typer(no_args_is_help=True, help="Manage bots.")
run_app = typer.Typer(no_args_is_help=True, help="Inspect runs.")
apr_app = typer.Typer(no_args_is_help=True, help="Resolve pending approvals.")
app.add_typer(bot_app, name="bot")
app.add_typer(run_app, name="runs")
app.add_typer(apr_app, name="approvals")
conn_app = typer.Typer(no_args_is_help=True, help="Hosted endpoints and subscription plans, each with its own key.")
usage_app = typer.Typer(no_args_is_help=True, help="Inspect and reconcile model-usage reservations.")
app.add_typer(conn_app, name="connections")
app.add_typer(usage_app, name="usage")
state_app = typer.Typer(no_args_is_help=True, help="Snapshot the database and review an isolated restore.")
app.add_typer(state_app, name="state")

console = Console()
err = Console(stderr=True)


def _store() -> Store:
    return Store(get_config())


def _require_bot(store: Store, ref: str) -> Bot:
    bot = store.get_bot(ref)
    if bot is None:
        err.print(f"[red]no such bot:[/red] {ref} (see `hutch bot list`)")
        raise typer.Exit(code=1)
    return bot


def _require_run(store: Store, run_id: str) -> "Run":
    run = store.get_run(run_id)
    if run is None:
        err.print(f"[red]no such run:[/red] {run_id}")
        raise typer.Exit(code=1)
    return run


# ------------------------------------------------------------------- setup

@app.command()
def init() -> None:
    """Create the state directory, database, and starter bot templates."""
    config = get_config()
    store = _store()
    created = seed(store)
    config.ensure()
    console.print(Panel.fit(
        f"[green]hutch initialized[/green]\n"
        f"state dir: [cyan]{config.state_dir}[/cyan]\n"
        f"database:  [cyan]{config.db_path}[/cyan]",
        title="hutch init"))
    if created:
        for name in created:
            console.print(f"  seeded bot [bold]{name}[/bold] (template, mock model — free to try)")
    else:
        console.print("  templates already present; nothing new seeded")
    console.print("\nnext: [bold]hutch serve[/bold] → dashboard, or [bold]hutch run <bot> \"task\"[/bold]")


@app.command()
def version() -> None:
    """Print version."""
    console.print(f"hutch {__version__}")


@app.command()
def status() -> None:
    """System overview: bots, active runs, queue, pending approvals."""
    from .scheduler import Scheduler
    store = _store()
    restoration = store.restoration_status()
    if restoration and restoration['execution_held']:
        console.print('Restored history — execution held for local review.', style='yellow')
        console.print(f"Inspect: hutch state report {restoration['id']}", markup=False)
    scheduler = Scheduler(store)
    bots = store.list_bots()
    table = Table(title="hutch status")
    for col in ("bot", "model", "schedule", "paused", "next run (local tz)", "last success"):
        table.add_column(col)
    import datetime as dt
    for bot in bots:
        nxt = scheduler.next_fire(bot)
        nxt_s = nxt.astimezone().strftime("%a %H:%M %Z") if nxt else "—"
        last = store.last_successful_run(bot.id)
        last_s = "never (stale)" if last is None else f"{dt.datetime.fromisoformat(last.finished_at or last.created_at).astimezone().strftime('%b %d %H:%M')}"
        sched = f"{bot.schedule.cron} ({bot.schedule.timezone})" if bot.schedule else "on demand"
        table.add_row(bot.name, bot.model, sched, "yes" if bot.paused else "no", nxt_s, last_s)
    console.print(table)

    active = store.active_runs()
    pending = store.pending_approvals()
    console.print(f"active runs: [bold]{len(active)}[/bold]   queued tasks: {len(store.pending_tasks())}   pending approvals: [yellow]{len(pending)}[/yellow]")
    for req in pending:
        console.print(f"  [yellow]![/yellow] {req.id}  [{req.tool}] {req.action}")


@state_app.command('backup')
def state_backup(destination: Path = typer.Argument(..., help='New snapshot directory; must not exist.'),
                 database: Optional[Path] = typer.Option(None, '--database', help='Optional pre-upgrade database backup to snapshot.')) -> None:
    """Back up committed database history, including WAL pages. Excludes files and credentials."""
    from .state_snapshot import backup
    try:
        manifest = backup(get_config(), destination, source_database=database)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        err.print(str(exc), style='red', markup=False)
        raise typer.Exit(1) from None
    console.print_json(json.dumps(manifest))


@state_app.command('restore')
def state_restore(snapshot: Path, destination: Path = typer.Option(..., '--to', help='New private state directory.')) -> None:
    """Verify/migrate a snapshot and quarantine old work. Does not stop source services or overwrite state."""
    from .state_snapshot import restore
    try:
        report = restore(snapshot, destination)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        err.print(str(exc), style='red', markup=False)
        raise typer.Exit(1) from None
    console.print_json(json.dumps(report))


@state_app.command('report')
def state_report(restore_id: str, limit: int = typer.Option(100, min=1, max=200),
                 offset: int = typer.Option(0, min=0)) -> None:
    """Inspect the current restore hold and a bounded page of quarantined resource IDs."""
    store = _store()
    try:
        report = store.restoration_status()
        if report is None or report['id'] != restore_id:
            err.print('No current restore with that ID.', style='red')
            raise typer.Exit(1)
        console.print_json(json.dumps({'report': report, 'items': store.restoration_items(restore_id, limit=limit, offset=offset),
                                      'limit': limit, 'offset': offset}))
    finally:
        store.close()


@state_app.command('activate')
def state_activate(restore_id: str, evidence: str = typer.Option(..., '--evidence',
                   help='Record review of source-service shutdown, later effects, provider usage and excluded files.')) -> None:
    """Record local review and allow new work. Old work stays quarantined and schedules stay paused."""
    store = _store()
    try:
        store.activate_restoration(restore_id, evidence)
    except (KeyError, ValueError, RuntimeError) as exc:
        err.print(str(exc), style='red', markup=False)
        raise typer.Exit(1) from None
    finally:
        store.close()
    console.print('Review recorded. New work is allowed; old work will not resume. Activation does not unpause schedules.')


# --------------------------------------------------------------------- bots

@bot_app.command("list")
def bot_list() -> None:
    """List bots."""
    store = _store()
    bots = store.list_bots()
    if not bots:
        console.print("no bots yet — try [bold]hutch init[/bold]")
        return
    table = Table()
    for col in ("name", "model", "runtime", "tools", "schedule", "approvals", "paused"):
        table.add_column(col)
    for b in bots:
        sched = b.schedule.cron if b.schedule else "on demand"
        table.add_row(b.name, b.model, b.runtime.value, ",".join(b.tools), sched,
                      b.approval_mode.value, "yes" if b.paused else "")
    console.print(table)


@bot_app.command("templates")
def bot_templates() -> None:
    """Show starter templates, grouped by what they are for."""
    for category, items in gallery():
        console.print(f"[bold]{category}[/bold]")
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 2))
        table.add_column(no_wrap=True, style="cyan")
        table.add_column()
        table.add_column(no_wrap=True, style="dim")
        for i in items:
            table.add_row(i.key, i.tagline, "needs a folder" if i.needs_folder else "")
        console.print(table)
    console.print("\n[dim]hutch bot create <name> --template <template> [--workdir ~/folder][/dim]")


@bot_app.command("create")
def bot_create(
    name: str = typer.Argument(..., help="Bot name (slug)"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Start from a template"),
    description: str = typer.Option("", "--description", "-d"),
    instructions: str = typer.Option("", "--instructions", "-i"),
    model: str = typer.Option("mock/demo", "--model", "-m",
                              help="provider/model, e.g. openai/gpt-4o-mini, ollama/llama3.2, mock/demo"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="OpenAI-compatible endpoint override"),
    runtime: RuntimeKind = typer.Option(RuntimeKind.builtin, "--runtime",
                                        help="builtin | mock | pi | opencode"),
    inference_mode: InferenceMode = typer.Option(
        InferenceMode.hybrid, "--inference-mode",
        help="local model routes only (services/tools may still use network traffic) | hybrid",
    ),
    tools: str = typer.Option("shell,files,memory", "--tools",
                              help=f"comma list; groups shell/files/memory/browser; all: {','.join(ALL_TOOL_NAMES)}"),
    cron: Optional[str] = typer.Option(None, "--cron", help="5-field cron schedule"),
    tz: str = typer.Option("UTC", "--tz", help="IANA timezone for the schedule"),
    catch_up: CatchUpPolicy = typer.Option(CatchUpPolicy.coalesce, "--catch-up"),
    approval: ApprovalMode = typer.Option(ApprovalMode.ask, "--approvals", help="ask | auto"),
    workdir: Optional[str] = typer.Option(None, "--workdir", help="a folder of yours the bot works in, e.g. ~/Downloads"),
    risk_tier: RiskTier = typer.Option(RiskTier.supervised, "--risk-tier",
                                       help="readonly (medium-risk actions blocked) | supervised (ask) | trusted (run)"),
    sandbox_mode: str = typer.Option("strict", "--sandbox", help="strict (Linux bubblewrap) | off (uncontained shell)"),
    rule: list[str] = typer.Option([], "--rule", help="per-command rule, e.g. --rule 'deny: git push*' (repeatable)"),
    max_steps: int = typer.Option(Limits().max_steps, "--max-steps", min=1),
    timeout: int = typer.Option(Limits().timeout_seconds, "--timeout-seconds", min=1),
    max_turn_tokens: int = typer.Option(Limits().max_turn_tokens, "--max-turn-tokens", min=0),
    token_cap: int = typer.Option(Limits().daily_token_cap, "--daily-token-cap", min=0),
    max_cost_usd: float = typer.Option(0.0, "--max-cost-usd", min=0),
    daily_cost_cap_usd: float = typer.Option(0.0, "--daily-cost-cap-usd", min=0),
) -> None:
    """Create a bot."""
    import re as _re
    if not _re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", name):
        err.print("[red]name must be a lowercase slug[/red] (a-z, 0-9, -, 2-41 chars)")
        raise typer.Exit(code=1)
    if sandbox_mode not in ("strict", "off"):
        err.print("[red]--sandbox must be 'strict' or 'off'[/red]")
        raise typer.Exit(code=1)
    store = _store()
    if store.get_bot(name):
        err.print(f"[red]bot already exists:[/red] {name}")
        raise typer.Exit(code=1)

    if template:
        base = TEMPLATES.get(template)
        if base is None:
            err.print(f"[red]unknown template:[/red] {template} (see `hutch bot templates`)")
            raise typer.Exit(code=1)
        bot = base.model_copy(deep=True)
        bot.name, bot.template = name, template
    else:
        bot = Bot(name=name)

    tool_list = expand_tools([t.strip() for t in tools.split(",") if t.strip()])
    unknown = [t for t in tool_list if t not in ALL_TOOL_NAMES]
    if unknown:
        err.print(f"[red]unknown tools:[/red] {', '.join(unknown)} — valid: {', '.join(ALL_TOOL_NAMES)}")
        raise typer.Exit(code=1)

    bot.description = description or bot.description
    bot.instructions = instructions or bot.instructions
    bot.model = model
    from .providers.registry import validate_inference_mode
    try:
        validate_inference_mode(inference_mode, model)
    except ValueError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    bot.inference_mode = inference_mode
    bot.base_url = base_url
    bot.runtime = runtime
    bot.tools = tool_list
    bot.approval_mode = approval
    bot.risk_tier = risk_tier
    bot.sandbox = sandbox_mode
    if workdir:
        bot.workdir = _check_workdir_option(workdir)
    if rule:
        bot.command_rules = _parse_rule_options(rule)
    bot.limits = Limits(max_steps=max_steps, timeout_seconds=timeout, max_turn_tokens=max_turn_tokens,
                        daily_token_cap=token_cap, max_cost_usd=max_cost_usd,
                        daily_cost_cap_usd=daily_cost_cap_usd)
    if cron:
        bot.schedule = Schedule(cron=cron, timezone=tz, catch_up=catch_up)
    store.create_bot(bot)
    info = TEMPLATE_INFO.get(template or "")
    if info and info.needs_folder and not bot.workdir:
        console.print(f"[yellow]note:[/yellow] {template} reads files ({info.reads}). It has no working folder yet, so it starts "
                      f"with an empty workspace: set one with `hutch bot update {name} --workdir <folder>`.")
    console.print(f"[green]created[/green] [bold]{name}[/bold] "
                  f"(model {bot.model}, runtime {bot.runtime.value}, tools: {', '.join(bot.tools)})")


@bot_app.command("estimate")
def bot_estimate(name: str = typer.Argument(...), model: Optional[str] = typer.Option(None, "--model", help="price another model"),
                 prompt: str = typer.Option("", "--prompt", help="the task text, for a closer prompt size")) -> None:
    """Estimate one run's priced usage before it starts; provider billing can differ."""
    from .estimate import estimate_run
    store = _store()
    bot = _require_bot(store, name)
    e = estimate_run(get_config(), store, bot, prompt, model)
    console.print(f"[bold]{e.spec}[/bold]: ~{e.prompt_tokens:,} prompt tokens, up to {e.steps} steps of {e.turn_tokens:,} tokens each")
    console.print(e.summary)
    if e.kind == "priced" and e.daily_token_cap:
        console.print(f"[dim]tokens today: {e.tokens_today:,} of the {e.daily_token_cap:,} daily cap[/dim]")


def _check_workdir_option(raw: str) -> str:
    from .workdir import validate_workdir
    try:
        return str(validate_workdir(raw, get_config().state_dir))
    except ValueError as exc:
        err.print(f"[red]invalid --workdir:[/red] {exc}")
        raise typer.Exit(code=1)


def _parse_rule_options(rules: list[str]):
    from .models import CommandRule
    from .safety import parse_rules
    try:
        return [CommandRule(verdict=v, match=g) for v, g in parse_rules("\n".join(rules))]
    except ValueError as exc:
        err.print(f"[red]invalid --rule:[/red] {exc}")
        raise typer.Exit(code=1)


@bot_app.command("show")
def bot_show(name: str = typer.Argument(...)) -> None:
    """Show a bot's config, memory, sticky allows, and recent runs."""
    store = _store()
    bot = _require_bot(store, name)
    console.print_json(bot.model_dump_json(exclude={"id"}))

    mem = store.recall_all(bot.id)
    if mem:
        console.print(f"\n[bold]memory[/bold] ({len(mem)}):")
        for m in mem:
            console.print(f"  • {m.key}: {m.value}")
    allows = store.list_sticky_allows(bot.id)
    if allows:
        console.print(f"\n[bold]sticky allows[/bold]: {', '.join(allows)}")

    runs = store.list_runs(bot.id, limit=5)
    if runs:
        console.print("\n[bold]recent runs[/bold]:")
        for r in runs:
            console.print(f"  {r.id}  {r.status.value:<18} {r.created_at[:19]}  steps={r.steps} tokens={r.tokens}")


@bot_app.command("update")
def bot_update(
    name: str = typer.Argument(...),
    model: Optional[str] = typer.Option(None, "--model"),
    inference_mode: Optional[InferenceMode] = typer.Option(
        None, "--inference-mode", help="local model routes only (services/tools may still use network) | hybrid"),
    instructions: Optional[str] = typer.Option(None, "--instructions"),
    description: Optional[str] = typer.Option(None, "--description"),
    approval: Optional[ApprovalMode] = typer.Option(None, "--approvals"),
    risk_tier: Optional[RiskTier] = typer.Option(None, "--risk-tier", help="readonly | supervised | trusted"),
    sandbox_mode: Optional[str] = typer.Option(None, "--sandbox", help="strict (Linux bubblewrap) | off (uncontained shell)"),
    workdir: Optional[str] = typer.Option(None, "--workdir", help="a folder of yours the bot works in"),
    clear_workdir: bool = typer.Option(False, "--clear-workdir", help="go back to a fresh empty workspace per run"),
    rule: list[str] = typer.Option([], "--rule", help="replace the bot's command rules, e.g. --rule 'deny: git push*'"),
    clear_rules: bool = typer.Option(False, "--clear-rules", help="remove all command rules"),
    cron: Optional[str] = typer.Option(None, "--cron", help="new cron expression"),
    clear_cron: bool = typer.Option(False, "--clear-cron", help="remove scheduling (on-demand only)"),
    tz: Optional[str] = typer.Option(None, "--tz"),
    paused: Optional[bool] = typer.Option(None, "--paused/--resumed"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps", min=1),
    timeout_seconds: Optional[int] = typer.Option(None, "--timeout-seconds", min=1),
    max_turn_tokens: Optional[int] = typer.Option(None, "--max-turn-tokens", min=0),
    daily_token_cap: Optional[int] = typer.Option(None, "--daily-token-cap", min=0),
    max_cost_usd: Optional[float] = typer.Option(None, "--max-cost-usd", min=0),
    daily_cost_cap_usd: Optional[float] = typer.Option(None, "--daily-cost-cap-usd", min=0),
) -> None:
    """Update bot settings."""
    store = _store()
    bot = _require_bot(store, name)
    proposed_model = model if model is not None else bot.model
    proposed_mode = inference_mode if inference_mode is not None else bot.inference_mode
    from .providers.registry import validate_inference_mode
    try:
        validate_inference_mode(proposed_mode, proposed_model)
    except ValueError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    if model is not None: bot.model = model
    if inference_mode is not None: bot.inference_mode = inference_mode
    if instructions is not None: bot.instructions = instructions
    if description is not None: bot.description = description
    if approval is not None: bot.approval_mode = approval
    if risk_tier is not None: bot.risk_tier = risk_tier
    if sandbox_mode is not None:
        if sandbox_mode not in ("strict", "off"):
            err.print("[red]--sandbox must be 'strict' or 'off'[/red]")
            raise typer.Exit(code=1)
        bot.sandbox = sandbox_mode
    if clear_workdir: bot.workdir = None
    if workdir: bot.workdir = _check_workdir_option(workdir)
    if clear_rules: bot.command_rules = []
    if rule: bot.command_rules = _parse_rule_options(rule)
    if paused is not None: bot.paused = paused
    limit_updates = {key: value for key, value in {
        "max_steps": max_steps, "timeout_seconds": timeout_seconds, "max_turn_tokens": max_turn_tokens,
        "daily_token_cap": daily_token_cap, "max_cost_usd": max_cost_usd,
        "daily_cost_cap_usd": daily_cost_cap_usd,
    }.items() if value is not None}
    if limit_updates:
        bot.limits = Limits.model_validate({**bot.limits.model_dump(), **limit_updates})
    if clear_cron: bot.schedule = None
    elif cron or tz:
        sched = bot.schedule or Schedule(cron=cron or "0 9 * * *", timezone=tz or "UTC")
        if cron: sched = sched.model_copy(update={"cron": cron})
        if tz: sched = sched.model_copy(update={"timezone": tz})
        bot.schedule = sched
    store.upsert_bot(bot)
    console.print(f"[green]updated[/green] {bot.name}")


@bot_app.command("delete")
def bot_delete(name: str = typer.Argument(...),
               yes: bool = typer.Option(False, "--yes", "-y", help="skip confirmation")) -> None:
    """Delete a bot (workspaces on disk are kept)."""
    store = _store()
    _require_bot(store, name)
    if not yes and not typer.confirm(f"delete bot '{name}'?"):
        raise typer.Exit()
    store.delete_bot(name)
    console.print(f"deleted {name}")


@bot_app.command("pause")
def bot_pause(name: str = typer.Argument(...)) -> None:
    store = _store(); bot = _require_bot(store, name)
    bot.paused = True; store.upsert_bot(bot)
    console.print(f"paused {name} (schedules disabled)")


@bot_app.command("resume")
def bot_resume(name: str = typer.Argument(...)) -> None:
    store = _store(); bot = _require_bot(store, name)
    bot.paused = False; store.upsert_bot(bot)
    console.print(f"resumed {name}")


@bot_app.command("forget")
def bot_forget(name: str = typer.Argument(...), key: Optional[str] = typer.Option(None, "--key")) -> None:
    """Archive fact memory (all scopes, or one key); keep history. Revoke sticky allows unless --key."""
    store = _store(); bot = _require_bot(store, name)
    if key:
        store.forget(bot.id, key)
        console.print(f"archived '{key}' across this bot's scopes; history and backups remain")
    else:
        store.archive_all_facts(bot.id)
        for sticky in store.list_sticky_allows(bot.id):
            store.revoke_sticky(bot.id, sticky)
        console.print("fact memory archived and sticky allows revoked; history and backups remain")


# --------------------------------------------------------------------- runs

@app.command()
def run(
    bot_ref: str = typer.Argument(..., help="Bot name"),
    prompt: str = typer.Argument(..., help="What the bot should do"),
    watch: bool = typer.Option(True, "--watch/--no-watch", help="stream events while running"),
    rehearse: bool = typer.Option(False, "--rehearse", help="dry run: mutating actions are simulated and logged"),
) -> None:
    """Run a bot once, now (blocking)."""
    from .engine import Engine
    config = get_config()
    store = _store()
    bot = _require_bot(store, bot_ref)
    engine = Engine(config, store, executor=os.environ.get("HUTCH_EXECUTOR") or "process")

    created = engine.submit(bot, prompt, origin="manual:cli", rehearsal=rehearse)
    try:
        engine.dispatch_pending()
        topic, seen = f"run:{created.id}", 0
        deadline = time.monotonic() + bot.limits.timeout_seconds + 60
        while time.monotonic() < deadline:
            version = store.bus.version(topic)  # read before querying: no lost wake-ups
            for ev in store.list_events(created.id, after_seq=seen):
                seen = ev.seq
                if watch:
                    _print_event(ev)
            current = store.get_run(created.id)
            if current and current.status in TERMINAL:
                for ev in store.list_events(created.id, after_seq=seen):
                    if watch:
                        _print_event(ev)
                break
            if current and current.status is RunStatus.pending:
                engine.dispatch_pending()  # capacity may have freed up
            store.bus.wait(topic, version, timeout=5.0)
        final = store.get_run(created.id)
    finally:
        # The dispatcher owns subprocess attempts; stop and join it even when the user interrupts the command.
        engine.shutdown()

    if final is None:
        raise typer.Exit(code=1)
    color = {"succeeded": "green", "failed": "red", "stopped": "yellow", "outcome_unknown": "yellow"}.get(final.status.value, "white")
    console.print(f"\nrun [bold]{final.id}[/bold] → [{color}]{final.status.value}[/{color}] "
                  f"({final.exit_reason or 'ok'}, steps={final.steps}, tokens≈{final.tokens})")
    raise typer.Exit(code=0 if final.status is RunStatus.succeeded else 1)


def _print_event(ev) -> None:  # pragma: no cover
    from .models import EventType
    if ev.type is EventType.message and ev.data.get("role") == "assistant":
        console.print(Panel(ev.data.get("content", ""), title="assistant"))
    elif ev.type is EventType.tool_call:
        args = json.dumps(ev.data.get("args", {}))[:120]
        console.print(f"  [cyan]→ {ev.data.get('tool')}[/cyan] {args}")
    elif ev.type is EventType.tool_result:
        mark = "[green]✓[/green]" if ev.data.get("ok") else "[red]✗[/red]"
        out = (ev.data.get("output") or "").splitlines()[0][:120] if ev.data.get("output") else ""
        console.print(f"  {mark} {out}")
    elif ev.type is EventType.approval_request:
        console.print(f"[yellow]approval needed:[/yellow] {ev.data.get('action')} — "
                      f"resolve with `hutch approvals approve {ev.data.get('approval_id')}`")
    elif ev.type is EventType.error:
        console.print(f"[red]error:[/red] {str(ev.data)[:200]}")
    elif ev.type is EventType.status and "status" in ev.data:
        pass  # final line printed by caller


@run_app.command("list")
def runs_list(bot_ref: Optional[str] = typer.Option(None, "--bot", "-b"), 
              limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """List recent runs."""
    store = _store()
    bot = _require_bot(store, bot_ref) if bot_ref else None
    runs = store.list_runs(bot.id if bot else None, limit=limit)
    if not runs:
        console.print("no runs yet")
        return
    table = Table()
    for col in ("run", "bot", "status", "reason", "steps", "tokens", "created"):
        table.add_column(col)
    for r in runs:
        rbot = store.get_bot(r.bot_id)
        table.add_row(r.id, rbot.name if rbot else "?", r.status.value, r.exit_reason,
                      str(r.steps), str(r.tokens), r.created_at[:19])
    console.print(table)


@run_app.command("show")
def runs_show(run_id: str = typer.Argument(...)) -> None:
    """Print a run's full transcript."""
    store = _store()
    r = _require_run(store, run_id)
    bot = store.get_bot(r.bot_id)
    console.print(Panel(
        f"bot: {bot.name if bot else '?'}\nprompt: {r.prompt}\nstatus: {r.status.value} "
        f"({r.exit_reason})\nsteps: {r.steps}  tokens≈{r.tokens}\nworkspace: {r.workspace}",
        title=f"run {r.id}"))
    for ev in store.list_events(r.id):
        _print_event(ev)


@app.command()
def stop(run_id: str = typer.Argument(...)) -> None:
    """Stop a run."""
    store = _store()
    _require_run(store, run_id)
    from .engine import Engine
    engine = Engine(get_config(), store)
    engine.stop_run(run_id)
    console.print(f"stop requested for {run_id}")


@app.command("stop-all")
def stop_all() -> None:
    """Emergency stop: request stop on every active run."""
    from .engine import Engine
    store = _store()
    engine = Engine(get_config(), store)
    n = engine.stop_all()
    console.print(f"[red]stop requested for {n} run(s)[/red]")


# -------------------------------------------------------------- connections

def _book():
    from .connections import ConnectionBook
    return ConnectionBook(get_config().state_dir)


@conn_app.command("templates")
def conn_templates() -> None:
    """Endpoints and plans Hutch knows how to talk to."""
    book = _book()
    table = Table(title="connection templates")
    table.add_column("template", no_wrap=True)       # the exact name to type must never be truncated
    for col in ("billing", "protocol", "endpoint", "get a key"):
        table.add_column(col)
    for name, t in book.templates().items():
        table.add_row(name, t.get("billing", ""), t.get("protocol", ""), t.get("base_url", ""),
                      t.get("get_key_url", "-"))
    console.print(table)
    console.print("add one with: [bold]hutch connections add <template>[/bold]  "
                  "then [bold]hutch connections set-key <name>[/bold]")


@conn_app.command("list")
def conn_list() -> None:
    """Configured connections: key, terms, and allowance used."""
    book, store = _book(), _store()
    conns = book.configured()
    if not conns:
        console.print("no connections yet - see [bold]hutch connections templates[/bold]")
        return
    for name, c in conns.items():
        console.print(f"[bold]{name}[/bold]  {c.title}")
        console.print(f"  billing: {c.billing.replace('_', ' ')}   protocol: {c.protocol}   endpoint: {c.base_url}")
        console.print(f"  account: {c.account_id}" + (f"   shared daily cap: ${c.account_daily_cost_cap_usd:.2f}"
                                                          if c.account_daily_cost_cap_usd else ""))
        src = book.key_source(name)
        console.print("  key: " + (f"present ({src})" if src != "missing" else
                                   f"[red]missing[/red] - set ${c.api_key_env} or run "
                                   f"`hutch connections set-key {name}`"))
        ack = book.ack_status(store, name)
        if ack == "ok":
            console.print("  terms: acknowledged")
        elif ack in ("required", "stale"):
            console.print(f"  terms: [yellow]{'ACK REQUIRED' if ack == 'required' else 'CHANGED - ACK REQUIRED'}"
                          f"[/yellow] - run `hutch connections ack {name}`")
        if c.quota.tokens:
            u = store.usage_tokens_since(name, c.quota.seconds)
            console.print(f"  allowance: {u:,} / {c.quota.tokens:,} tokens ({c.quota.window} window)")
        else:
            console.print("  allowance: none declared (`hutch connections set-allowance`)")
        console.print()


@conn_app.command("add")
def conn_add(
    template: str = typer.Argument(..., help="see `hutch connections templates`"),
    name: Optional[str] = typer.Option(None, "--name", help="name used in model specs: <name>/<model>"),
    key_env: Optional[str] = typer.Option(None, "--key-env", help="environment variable that holds the key"),
    base_url: Optional[str] = typer.Option(None, "--base-url"),
    billing: Optional[str] = typer.Option(None, "--billing", help="per_token | subscription | free"),
    quota_tokens: int = typer.Option(0, "--allowance-tokens", help="stop before this many tokens per window"),
    quota_window: str = typer.Option("month", "--allowance-window", help="5h | day | week | month"),
    account_id: Optional[str] = typer.Option(None, "--account-id", help="share usage limits with connections using this ID"),
    account_daily_cap: float = typer.Option(0.0, "--account-daily-cap-usd", min=0,
                                            help="shared daily currency cap across this billing account"),
) -> None:
    """Add a connection from a template."""
    book = _book()
    try:
        over: dict = {"api_key_env": key_env, "base_url": base_url, "billing": billing,
                      "account_id": account_id, "account_daily_cost_cap_usd": account_daily_cap}
        if quota_tokens:
            over["quota"] = {"window": quota_window, "tokens": quota_tokens}
        c = book.add(template, name, **over)
    except ValueError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]added[/green] [bold]{c.name}[/bold] ({c.title})")
    console.print(f"  use it in a bot:  [bold]hutch bot update <bot> --model {c.name}/<model-id>[/bold]")
    console.print(f"  next: put the key in ${c.api_key_env}, or run [bold]hutch connections set-key {c.name}[/bold]")
    if c.terms.requires_ack:
        console.print(f"  [yellow]read the terms, then[/yellow] [bold]hutch connections ack {c.name}[/bold]")
    if c.get_key_url:
        console.print(f"  get a key: {c.get_key_url}")


@conn_app.command("set-key")
def conn_set_key(name: str = typer.Argument(...)) -> None:
    """Store a key in a 0600 file under the state directory (it is never printed or put in the database)."""
    book = _book()
    if book.get(name) is None:
        err.print(f"[red]no connection named {name}[/red]")
        raise typer.Exit(code=1)
    key = typer.prompt(f"API key for {name} (input hidden)", hide_input=True).strip()
    if not key:
        err.print("[red]empty key[/red]")
        raise typer.Exit(code=1)
    book.set_key(name, key)
    console.print(f"[green]stored[/green] in {book.key_file(name)} (mode 0600)")


@conn_app.command("ack")
def conn_ack(name: str = typer.Argument(...), yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Read and acknowledge a plan's terms notice - required before a bot may use the connection."""
    book, store = _book(), _store()
    c = book.get(name)
    if c is None:
        err.print(f"[red]no connection named {name}[/red]")
        raise typer.Exit(code=1)
    if not c.terms.requires_ack:
        console.print("this connection has no terms notice to acknowledge")
        return
    console.print(Panel(c.terms.notice, title=f"{c.title} - terms notice", subtitle=c.terms.url))
    if not (yes or typer.confirm("I have read this and take responsibility for how my bots use this plan")):
        raise typer.Exit(code=1)
    book.acknowledge(store, name)
    console.print("[green]acknowledged[/green]")


@conn_app.command("test")
def conn_test(name: str = typer.Argument(...),
              chat: Optional[str] = typer.Option(None, "--chat", help="also send ONE tiny chat to this model "
                                                                      "(spends a few tokens)")) -> None:
    """Check the key and endpoint. Spends no tokens unless --chat is given."""
    from .providers.connection import check_connection
    res = check_connection(_book(), name, chat or "")
    console.print(("[green]ok[/green] " if res.ok else "[red]failed[/red] ") + res.detail)
    for m in res.models[:40]:
        console.print(f"  {name}/{m}")
    if len(res.models) > 40:
        console.print(f"  ... and {len(res.models) - 40} more")
    raise typer.Exit(code=0 if res.ok else 1)


@conn_app.command("set-protocol")
def conn_set_protocol(name: str = typer.Argument(...), model: str = typer.Argument(...),
                      protocol: str = typer.Argument(..., help="openai-chat | anthropic")) -> None:
    """Serve one model over a different protocol (some plans split models across endpoints)."""
    try:
        _book().set_model_protocol(name, model, protocol)
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"{name}/{model} now uses the {protocol} protocol")


@conn_app.command("set-allowance")
def conn_set_allowance(name: str = typer.Argument(...), tokens: int = typer.Argument(...),
                       window: str = typer.Option("month", "--window", help="5h | day | week | month")) -> None:
    """Declare how many tokens the plan allows per window; Hutch stops BEFORE the vendor does (0 = none)."""
    try:
        _book().set_quota(name, window, tokens)
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"{name}: allowance {tokens:,} tokens per {window} (rolling window)")


@conn_app.command("set-account-cap")
def conn_set_account_cap(name: str = typer.Argument(...), daily_usd: float = typer.Argument(..., min=0),
                         account_id: Optional[str] = typer.Option(None, "--account-id")) -> None:
    """Set a shared account daily cap; reuse --account-id to group multiple connections."""
    try:
        book = _book()
        fields = {"account_daily_cost_cap_usd": daily_usd}
        if account_id is not None:
            fields["account_id"] = account_id
        c = book.update(name, **fields)
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"{c.name}: account {c.account_id}, shared daily cap ${c.account_daily_cost_cap_usd:.2f}")


@conn_app.command("remove")
def conn_remove(name: str = typer.Argument(...), yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Remove a connection and its stored key file."""
    if not yes and not typer.confirm(f"remove connection '{name}' and its stored key?"):
        raise typer.Exit()
    console.print("removed" if _book().remove(name) else "no such connection")


@usage_app.command("reservations")
def usage_reservations(limit: int = typer.Option(100, "--limit", min=1, max=500)) -> None:
    """List live and uncertain reservations that still count against token or currency caps."""
    store = _store()
    try:
        rows = store.unresolved_usage_reservations(limit)
    finally:
        store.close()
    if not rows:
        console.print("no unresolved usage reservations")
        return
    for row in rows:
        console.print(f"[bold]{row['id']}[/bold]  {row['status']}  account={row['account_id']}  "
                      f"provider={row['provider']}  held={row['reserved_tokens']:,} tokens / "
                      f"${row['reserved_cost_usd']:.4f}")
        console.print(f"  run={row['run_id']}  {row['reason'] or 'no additional reason'}")
    console.print("Uncertain reservations remain held. Check the provider's usage record before reconciling one.")


@usage_app.command("reconcile")
def usage_reconcile(reservation_id: str = typer.Argument(...),
                    not_charged: bool = typer.Option(False, "--not-charged", help="release after verifying no charge"),
                    prompt_tokens: Optional[int] = typer.Option(None, "--prompt-tokens", min=0),
                    completion_tokens: Optional[int] = typer.Option(None, "--completion-tokens", min=0),
                    cached_tokens: int = typer.Option(0, "--cached-tokens", min=0),
                    actual_cost_usd: Optional[float] = typer.Option(None, "--actual-cost-usd", min=0),
                    reason: str = typer.Option(..., "--reason")) -> None:
    """Release a verified no-charge reservation or settle it with exact provider usage."""
    charged_fields = (prompt_tokens, completion_tokens, actual_cost_usd)
    if len(reason.strip()) < 3:
        err.print("[red]--reason must contain at least three non-space characters[/red]")
        raise typer.Exit(code=2)
    if not_charged and any(value is not None for value in charged_fields):
        err.print("[red]use --not-charged or provide all exact usage fields, not both[/red]")
        raise typer.Exit(code=2)
    if not not_charged and any(value is None for value in charged_fields):
        err.print("[red]provide --prompt-tokens, --completion-tokens and --actual-cost-usd, or use --not-charged[/red]")
        raise typer.Exit(code=2)
    store = _store()
    try:
        outcome = store.resolve_usage_reservation(
            reservation_id, not_charged=not_charged, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, cached_tokens=cached_tokens,
            actual_cost_usd=actual_cost_usd, reason=reason)
    except (KeyError, ValueError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    finally:
        store.close()
    console.print(f"{reservation_id}: {outcome}")


# ------------------------------------------------------------------ doctor

@app.command()
def doctor(deep: bool = typer.Option(False, "--deep", help="also run each local bot's context self-check "
                                                            "(uses CPU/GPU, no money)"),
           online: bool = typer.Option(False, "--online", help="authenticate connections (spends no tokens)"),
           as_json: bool = typer.Option(False, "--json")) -> None:
    """Check runtimes, context size, database, permissions and the service. Each problem comes with its fix."""
    from .doctor import FAIL, INFO, OK, WARN, run_doctor, worst
    config, store = get_config(), _store()
    checks = run_doctor(config, store, deep=deep, online=online)
    if as_json:
        console.print_json(json.dumps([c.__dict__ for c in checks]))
    else:
        mark = {OK: "[green]ok  [/green]", WARN: "[yellow]warn[/yellow]", FAIL: "[red]FAIL[/red]", INFO: "[dim]info[/dim]"}
        for c in checks:
            console.print(f"{mark[c.status]} [bold]{c.title}[/bold]: {c.detail}")
            if c.fix and c.status in (WARN, FAIL, INFO):
                console.print(f"       fix: {c.fix}")
        w = worst(checks)
        console.print("\n" + {OK: "[green]everything checks out[/green]", WARN: "[yellow]warnings only[/yellow]",
                              FAIL: "[red]problems found[/red]"}[w])
    raise typer.Exit(code=1 if worst(checks) == FAIL else 0)


# ------------------------------------------------------------------ models

models_app = typer.Typer(no_args_is_help=True, help="Local models: what fits this machine, presets, swap cost.")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list() -> None:
    """Installed local models, each marked fits / tight / won't fit with the context it will actually get."""
    from .modelview import build_models_view
    config, store = get_config(), _store()
    v = build_models_view(config, store)
    console.print(f"[bold]hardware:[/bold] {v.hw.summary}")
    for n in v.notes:
        console.print(f"  [yellow]note:[/yellow] {n}")
    if not v.rows:
        console.print("no installed models found" + ("" if v.ollama_up else " (Ollama is not running)"))
    for r in v.rows:
        f16, f32 = r.fits[16384], r.fits[32768]
        console.print(f"[bold]{r.name}[/bold]  {r.meta.params_b or '?'}B {r.meta.quant}  "
                      f"max context {r.meta.max_context or '?'}")
        console.print(f"  @16k: {f16.label} (gets {f16.effective_ctx:,})    @32k: {f32.label} (gets {f32.effective_ctx:,})"
                      f"    self-check: {r.selfcheck}" + (f"    last cold load {r.load_ms / 1000:.1f}s" if r.load_ms else ""))
    if v.suggestions:
        console.print("\n[bold]suggested (estimates, not installed):[/bold]")
        for tag, fit, meta in v.suggestions[:8]:
            console.print(f"  {tag:<22} {fit.label:<9} {fit.reason}   [dim]ollama pull {tag}[/dim]")


@models_app.command("presets")
def models_presets() -> None:
    """What each task preset resolves to on THIS machine."""
    from .modelview import build_models_view
    v = build_models_view(get_config(), _store())
    console.print(f"[bold]hardware:[/bold] {v.hw.summary}\n")
    for r in v.presets:
        console.print(f"[bold]{r.preset.title}[/bold] - {r.preset.description}")
        console.print(f"  local:  {r.local_model or 'none fits'}  {r.reason}")
        if r.install_hint:
            console.print(f"          install: {r.install_hint}")
        console.print(f"  hosted: {r.hosted}")


@models_app.command("bench")
def models_bench(model: str = typer.Argument(..., help="an installed Ollama model, e.g. qwen3:4b"),
                 trials: int = typer.Option(3, "--trials", "-n", min=1, max=20, help="runs per probe"),
                 ctx: int = typer.Option(8192, "--ctx", help="context window to measure at"),
                 recall: bool = typer.Option(True, "--recall/--no-recall", help="include the long-prompt recall probe")) -> None:
    """Profile how reliably a model forms tool calls, picks tools and uses results, on THIS machine."""
    from .hardware import probe
    from .reliability import VERDICT_TEXT, profile_model
    from .runtime.ladder import get_provider
    config, store = get_config(), _store()
    prov = get_provider("ollama", None)
    health = prov.health()
    if not health.ok:
        err.print(f"[red]Ollama is not reachable ({health.detail}).[/red] Start it with `ollama serve`.")
        raise typer.Exit(code=1)
    hw = probe(with_runtimes=False)
    console.print(f"profiling [bold]{model}[/bold]: {trials} trial(s) per probe at {ctx:,} tokens "
                  f"(each trial is one model call; on CPU this can take a while)")
    prof = profile_model(prov, model, runtime="ollama", num_ctx=ctx, trials=trials, hardware=hw.summary,
                         with_recall=recall, progress=lambda s: console.print(f"  [dim]{s}[/dim]"))
    store.save_profile(prof)
    from rich.table import Table
    t = Table(show_header=True, header_style="bold")
    t.add_column("probe", no_wrap=True)
    t.add_column("passed", justify="right")
    t.add_column("unaided", justify="right")
    t.add_column("what went wrong")
    for p in prof.probes:
        t.add_row(p.title, f"{p.repaired}/{p.trials}", f"{p.raw}/{p.trials}", p.detail or "-")
    console.print(t)
    col = {"reliable": "green", "usable_with_repair": "yellow", "unreliable": "red", "inconclusive": "dim"}[prof.verdict]
    console.print(f"[{col}]{VERDICT_TEXT[prof.verdict]}[/{col}]: {prof.summary}")
    if prof.tokens_per_sec:
        console.print(f"speed: {prof.tokens_per_sec} tokens/s median;  quant {prof.quant or '?'};  measured on {hw.summary}")
    if prof.verdict == "inconclusive":
        raise typer.Exit(code=2)


@models_app.command("swap-test")
def models_swap_test(model_a: str = typer.Argument(...), model_b: str = typer.Argument(...)) -> None:
    """Measure the real cost of alternating between two local models (unloads and reloads them; run when idle)."""
    from .runtime.ladder import get_provider
    from .slots import measure_swap, record_swap
    prov = get_provider("ollama", None)
    console.print(f"measuring {model_a} <-> {model_b} (this loads both models, no tokens are generated)...")
    try:
        rep = measure_swap(prov, model_a, model_b)
    except Exception as exc:
        err.print(f"[red]could not measure: {exc}[/red]")
        raise typer.Exit(code=1)
    record_swap(_store(), rep)
    console.print(rep.summary)


# --------------------------------------------------------------- approvals

@apr_app.command("list")
def approvals_list() -> None:
    store = _store()
    reqs = store.pending_approvals()
    if not reqs:
        console.print("no pending approvals")
        return
    for req in reqs:
        bot = store.get_bot(req.bot_id)
        console.print(Panel(
            f"[bold]{req.action}[/bold]\n{json.dumps(req.detail, indent=2)}\n\n"
            f"approve:  [green]hutch approvals approve {req.id}[/green]\n"
            f"always:   [green]hutch approvals approve {req.id} --always[/green]\n"
            f"deny:     [red]hutch approvals deny {req.id}[/red]",
            title=f"{req.id} · {bot.name if bot else req.bot_id} · {req.tool}"))


@apr_app.command("approve")
def approvals_approve(approval_id: str = typer.Argument(...),
                      always: bool = typer.Option(False, "--always", "-a",
                                                  help="also remember this action as always-allowed for the bot")) -> None:
    from .approvals import resolve_approval
    store = _store()
    req = resolve_approval(store, approval_id, approve=True, by="cli", sticky=always)
    if req is None:
        err.print("[red]no such approval[/red]"); raise typer.Exit(code=1)
    console.print(f"[green]approved[/green] {approval_id}" + (" (sticky)" if always else ""))


@apr_app.command("deny")
def approvals_deny(approval_id: str = typer.Argument(...)) -> None:
    from .approvals import resolve_approval
    store = _store()
    req = resolve_approval(store, approval_id, approve=False, by="cli")
    if req is None:
        err.print("[red]no such approval[/red]"); raise typer.Exit(code=1)
    console.print(f"[red]denied[/red] {approval_id}")


# ------------------------------------------------------------------ daemon

@app.command()
def daemon() -> None:
    """Run the scheduler + dispatcher loop (foreground; Ctrl-C to stop).

    The loop sleeps until the next scheduled run or an incoming event — no polling interval.
    """
    from .engine import Engine
    config = get_config()
    store = _store()
    store.ensure_listening()
    engine = Engine(config, store, executor=os.environ.get("HUTCH_EXECUTOR") or "process")   # one OS process per run

    def on_tick(runs):
        for r in runs:
            console.print(f"[magenta]dispatched scheduled run[/magenta] {r.id}")

    console.print(f"[bold]hutch daemon[/bold] — state: {config.state_dir} (Ctrl-C to stop)")
    engine.run_daemon(on_tick=on_tick)
    engine.shutdown()
    console.print("daemon stopped")


@app.command()
def pairing(action: str = typer.Argument(..., help="create, list, or revoke"),
            device_id: Optional[str] = typer.Argument(None)) -> None:
    """Create a one-use phone pairing code or inspect/revoke paired devices."""
    store = _store()
    try:
        if action == "create":
            if device_id:
                raise typer.BadParameter("create does not accept a device id")
            code = store.create_pairing_code()
            console.print(f"Pairing code (expires in 60 seconds; show it only to your device): [bold]{code}[/bold]")
            console.print("Open the Hutch address on the device and enter this code. It can be used once.")
        elif action == "list":
            if device_id:
                raise typer.BadParameter("list does not accept a device id")
            rows = store.list_device_sessions()
            if not rows:
                console.print("No active paired devices.")
            for row in rows:
                console.print(f"{row['id']}  {row['label']}  expires {row['expires_at']}  last used {row['last_used_at'] or 'never'}")
        elif action == "revoke":
            if not device_id:
                raise typer.BadParameter("revoke requires a device id")
            if not store.revoke_device_session(device_id):
                err.print(f"[red]no active device session:[/red] {device_id}")
                raise typer.Exit(code=1)
            console.print(f"Revoked device {device_id}.")
        else:
            raise typer.BadParameter("choose create, list, or revoke")
    finally:
        store.close()


def _loopback_bind(host: str) -> bool:
    if host.lower() in ("localhost", "localhost.localdomain") or host.lower().endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@app.command()
def serve(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8787),
          allow_remote: bool = typer.Option(False, "--allow-remote"),
          tls_cert: Optional[str] = typer.Option(None, "--tls-cert"),
          tls_key: Optional[str] = typer.Option(None, "--tls-key")) -> None:
    """Serve locally, or allow explicitly paired devices over direct HTTPS."""
    import uvicorn
    loopback = _loopback_bind(host)
    if not loopback and not allow_remote:
        err.print("[red]refusing a non-loopback bind without --allow-remote[/red]")
        raise typer.Exit(code=2)
    if allow_remote:
        if not tls_cert or not tls_key or not Path(tls_cert).is_file() or not Path(tls_key).is_file():
            err.print("[red]--allow-remote requires readable --tls-cert and --tls-key files[/red]")
            raise typer.Exit(code=2)
        os.environ["HUTCH_REMOTE_ENABLED"] = "1"
        console.print("Remote HTTPS is enabled. Pair each device with `hutch pairing create`; revoke with "
                      "`hutch pairing list` / `hutch pairing revoke <id>`. Do not forward this listener publicly.")
    elif tls_cert or tls_key:
        if not tls_cert or not tls_key or not Path(tls_cert).is_file() or not Path(tls_key).is_file():
            err.print("[red]both --tls-cert and --tls-key must name readable files[/red]")
            raise typer.Exit(code=2)
    os.environ.setdefault("HUTCH_EXECUTOR", "process")      # the dashboard's runs are worker processes: Stop is a real kill
    scheme = "https" if tls_cert else "http"
    console.print(f"[bold]hutch[/bold] dashboard → {scheme}://{host}:{port}")
    uvicorn.run("hutch.server.app:create_app", factory=True, host=host, port=port, log_level="warning",
                ssl_certfile=tls_cert, ssl_keyfile=tls_key)


# --------------------------------------------------------------------- demo

demo_app = typer.Typer(help="Demo/screenshot helpers.")
app.add_typer(demo_app, name="demo")


@demo_app.command("seed")
def demo_seed() -> None:
    """Seed demo bots/runs (offline, mock models) for exploring the dashboard."""
    from .demo import seed_demo
    from .engine import Engine
    config = get_config()
    store = _store()
    engine = Engine(config, store)
    summary = seed_demo(config, store, engine)
    console.print(f"seeded {len(summary['bots_created'])} new bot(s); demo runs:")
    for r in summary["runs"]:
        console.print(f"  {r['bot']:<20} {r['run']}  {r['status']}")
    console.print("\ntry: [bold]hutch serve[/bold] → http://127.0.0.1:8787")


def main() -> None:  # console_scripts entry point
    app()


if __name__ == "__main__":
    main()
