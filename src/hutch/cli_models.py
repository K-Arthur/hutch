"""`hutch models`: what fits this machine, presets, installing and removing local models, and a reliability bench.

Split out of cli.py (a frozen file) when installation and removal were added; behaviour is unchanged.
"""

from __future__ import annotations

import typer
from rich.console import Console

from .config import get_config
from .store import Store

console = Console()
err = Console(stderr=True)


def _store() -> Store:
    return Store(get_config())


models_app = typer.Typer(no_args_is_help=True, help="Local models: what fits this machine, presets, swap cost.")


@models_app.command("list")
def models_list() -> None:
    """Installed local models, each marked fits / tight / won't fit with the context it will actually get."""
    from .modelview import build_models_view, residency_note
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
        measured = residency_note(r.meta)
        if measured:
            console.print(f"  [cyan]now loaded:[/cyan] {measured}")
    if v.suggestions:
        console.print("\n[bold]suggested (estimates, not installed):[/bold]")
        for tag, fit, meta in v.suggestions[:8]:
            console.print(f"  {tag:<22} {fit.label:<9} {fit.reason}   [dim]ollama pull {tag}[/dim]")


@models_app.command("install")
def models_install(tag: str = typer.Argument(..., help="a model tag from the runtime's registry, e.g. qwen3:4b"),
                   yes: bool = typer.Option(False, "--yes", "-y", help="skip the download-size confirmation")) -> None:
    """Download a model through the local runtime's own registry (Ollama).

    This is the explicit, user-initiated install path: choosing a model anywhere else in
    Hutch never starts a download. Progress comes from the runtime's own byte counters,
    the runtime verifies each blob's digest, and an interrupted download resumes.
    """
    import time as _time

    from .providers.base import ProviderError
    from .providers.model_install import ModelInstaller, validate_model_name
    from .runtime.ladder import get_provider

    try:
        name = validate_model_name(tag)
    except ValueError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    prov = get_provider("ollama", None)
    if not prov.health().ok:
        err.print("[red]Ollama is not reachable.[/red] Start it with `ollama serve`, then try again.")
        raise typer.Exit(code=1)
    est = _catalog_size_gib(name)
    if est:
        console.print(f"{name} is about [bold]{est:.1f} GiB[/bold] to download.")
    if not yes and not typer.confirm(f"download {name}?", default=True):
        raise typer.Exit(code=1)
    installer = ModelInstaller(prov)
    job = installer.start(name)
    last = ""
    try:
        while job.state in ("starting", "running"):
            line = job.status + (f"  {job.percent:.0f}%" if job.percent is not None else "")
            if line != last:
                last = line
                console.print(f"  [dim]{line}[/dim]")
            _time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[dim]cancelling; verified parts are kept, so re-running resumes[/dim]")
        installer.cancel(job.id)
        raise typer.Exit(code=130) from None
    if job.state == "done":
        console.print(f"[green]installed[/green] {name}")
        return
    err.print(f"[red]could not install {name}:[/red] {job.error}")
    raise typer.Exit(code=1)


def _catalog_size_gib(tag: str) -> float:
    """Approximate download size from the bundled catalog, when it knows this tag."""
    from .fit import weights_gib
    from .presets import catalog_meta
    meta = catalog_meta(tag)
    if meta is None:
        return 0.0
    return weights_gib(meta)[0]


@models_app.command("remove")
def models_remove(tag: str = typer.Argument(..., help="an installed model tag"),
                  yes: bool = typer.Option(False, "--yes", "-y", help="skip the confirmation")) -> None:
    """Delete a model from the local runtime. Refuses while it is being installed."""
    from .providers.base import ProviderError
    from .providers.model_install import ModelInstaller, validate_model_name
    from .runtime.ladder import get_provider

    try:
        name = validate_model_name(tag)
    except ValueError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    store = _store()
    users = [b.name for b in store.list_bots() if (b.model or "") in (f"ollama/{name}", f"ollama/{tag}")]
    if users:
        err.print(f"[yellow]{name} is the saved route for {', '.join(users)}.[/yellow] Those assistants will "
                  "fail on their next run until they get another model.")
    if not yes and not typer.confirm(f"delete {name} from this machine?"):
        raise typer.Exit(code=1)
    try:
        ModelInstaller(get_provider("ollama", None)).remove(name)
    except ProviderError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]removed[/green] {name}")


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
def models_bench(model: str = typer.Argument(..., help="an installed model, e.g. qwen3:4b"),
                 trials: int = typer.Option(3, "--trials", "-n", min=1, max=20, help="runs per probe"),
                 ctx: int = typer.Option(8192, "--ctx", help="context window to measure at"),
                 recall: bool = typer.Option(True, "--recall/--no-recall", help="include the long-prompt recall probe"),
                 provider: str = typer.Option("ollama", "--provider",
                                              help="ollama (default), llamacpp, lmstudio or openai-compatible"),
                 base_url: str = typer.Option("", "--base-url", help="server URL for a local runtime")) -> None:
    """Profile how reliably a model forms tool calls, picks tools and uses results, on THIS machine."""
    from .hardware import probe
    from .reliability import VERDICT_TEXT, profile_model
    from .runtime.ladder import get_provider
    config, store = get_config(), _store()
    prov = get_provider(provider, base_url or None)
    health = prov.health()
    if not health.ok:
        hint = " Start it with `ollama serve`." if provider == "ollama" else " Check --base-url and that the server is up."
        err.print(f"[red]{provider} is not reachable ({health.detail}).[/red]{hint}")
        raise typer.Exit(code=1)
    hw = probe(with_runtimes=False)
    console.print(f"profiling [bold]{model}[/bold] on {provider}: {trials} trial(s) per probe at {ctx:,} tokens "
                  f"(each trial is one model call; on CPU this can take a while)")
    prof = profile_model(prov, model, runtime=provider, num_ctx=ctx, trials=trials, hardware=hw.summary,
                         with_recall=recall, progress=lambda s: console.print(f"  [dim]{s}[/dim]"))
    store.save_profile(prof)
    from rich.table import Table
    t = Table(show_header=True, header_style="bold")
    t.add_column("probe", no_wrap=True)
    t.add_column("passed", justify="right")
    t.add_column("unaided", justify="right")
    t.add_column("what went wrong")
    t.add_column("causes")
    for p in prof.probes:
        causes = ", ".join(f"{name} {count}" for name, count in sorted(p.causes.items())) or "-"
        t.add_row(p.title, f"{p.repaired}/{p.trials}", f"{p.raw}/{p.trials}", p.detail or "-", causes)
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


