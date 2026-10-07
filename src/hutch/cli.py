"""hutch command line interface."""

from __future__ import annotations

import json
import time
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
    RunStatus,
    RuntimeKind,
    Schedule,
)
from .store import Store
from .templates import TEMPLATES, seed
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
app.add_typer(conn_app, name="connections")

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
    """Show starter templates."""
    table = Table()
    table.add_column("template"); table.add_column("description"); table.add_column("default tools")
    for t in TEMPLATES.values():
        table.add_row(t.name, t.description, ",".join(t.tools))
    console.print(table)


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
    tools: str = typer.Option("shell,files,memory", "--tools",
                              help=f"comma list; groups shell/files/memory/browser; all: {','.join(ALL_TOOL_NAMES)}"),
    cron: Optional[str] = typer.Option(None, "--cron", help="5-field cron schedule"),
    tz: str = typer.Option("UTC", "--tz", help="IANA timezone for the schedule"),
    catch_up: CatchUpPolicy = typer.Option(CatchUpPolicy.coalesce, "--catch-up"),
    approval: ApprovalMode = typer.Option(ApprovalMode.ask, "--approvals", help="ask | auto"),
    max_steps: int = typer.Option(Limits().max_steps, "--max-steps"),
    timeout: int = typer.Option(Limits().timeout_seconds, "--timeout-seconds"),
    token_cap: int = typer.Option(Limits().daily_token_cap, "--daily-token-cap"),
) -> None:
    """Create a bot."""
    import re as _re
    if not _re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", name):
        err.print("[red]name must be a lowercase slug[/red] (a-z, 0-9, -, 2-41 chars)")
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
    bot.base_url = base_url
    bot.runtime = runtime
    bot.tools = tool_list
    bot.approval_mode = approval
    bot.limits = Limits(max_steps=max_steps, timeout_seconds=timeout, daily_token_cap=token_cap)
    if cron:
        bot.schedule = Schedule(cron=cron, timezone=tz, catch_up=catch_up)
    store.create_bot(bot)
    console.print(f"[green]created[/green] [bold]{name}[/bold] "
                  f"(model {bot.model}, runtime {bot.runtime.value}, tools: {', '.join(bot.tools)})")


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
    instructions: Optional[str] = typer.Option(None, "--instructions"),
    description: Optional[str] = typer.Option(None, "--description"),
    approval: Optional[ApprovalMode] = typer.Option(None, "--approvals"),
    cron: Optional[str] = typer.Option(None, "--cron", help="new cron expression"),
    clear_cron: bool = typer.Option(False, "--clear-cron", help="remove scheduling (on-demand only)"),
    tz: Optional[str] = typer.Option(None, "--tz"),
    paused: Optional[bool] = typer.Option(None, "--paused/--resumed"),
) -> None:
    """Update bot settings."""
    store = _store()
    bot = _require_bot(store, name)
    if model is not None: bot.model = model
    if instructions is not None: bot.instructions = instructions
    if description is not None: bot.description = description
    if approval is not None: bot.approval_mode = approval
    if paused is not None: bot.paused = paused
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
    """Clear a bot's memory (all, or one key). Also clears sticky allows unless --key."""
    store = _store(); bot = _require_bot(store, name)
    if key:
        store.forget(bot.id, key)
        console.print(f"forgot '{key}'")
    else:
        for m in store.recall_all(bot.id):
            store.forget(bot.id, m.key)
        for sticky in store.list_sticky_allows(bot.id):
            store.revoke_sticky(bot.id, sticky)
        console.print("memory and sticky allows cleared")


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
    engine = Engine(config, store)

    created = engine.submit(bot, prompt, origin="manual:cli", rehearsal=rehearse)
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
        if current and current.status.value not in ("pending", "loading_model", "running",
                                                    "waiting_approval", "waiting_human"):
            for ev in store.list_events(created.id, after_seq=seen):
                if watch:
                    _print_event(ev)
            break
        if current and current.status is RunStatus.pending:
            engine.dispatch_pending()  # capacity may have freed up
        store.bus.wait(topic, version, timeout=5.0)
    final = store.get_run(created.id)

    color = {"succeeded": "green", "failed": "red", "stopped": "yellow"}.get(final.status.value, "white")
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
) -> None:
    """Add a connection from a template."""
    book = _book()
    try:
        over: dict = {"api_key_env": key_env, "base_url": base_url, "billing": billing}
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


@conn_app.command("remove")
def conn_remove(name: str = typer.Argument(...), yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Remove a connection and its stored key file."""
    if not yes and not typer.confirm(f"remove connection '{name}' and its stored key?"):
        raise typer.Exit()
    console.print("removed" if _book().remove(name) else "no such connection")


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
    engine = Engine(config, store)

    def on_tick(runs):
        for r in runs:
            console.print(f"[magenta]dispatched scheduled run[/magenta] {r.id}")

    console.print(f"[bold]hutch daemon[/bold] — state: {config.state_dir} (Ctrl-C to stop)")
    engine.run_daemon(on_tick=on_tick)
    engine.shutdown()
    console.print("daemon stopped")


@app.command()
def serve(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8787)) -> None:
    """Serve the web dashboard + API."""
    import uvicorn
    console.print(f"[bold]hutch[/bold] dashboard → http://{host}:{port}")
    uvicorn.run("hutch.server.app:create_app", factory=True, host=host, port=port, log_level="warning")


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
