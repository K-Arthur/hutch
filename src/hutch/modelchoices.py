"""The model switcher (composer menu + "all models" view).

One list, built once, for both surfaces: the default model of the bot first, then what is genuinely usable right
now, then what needs setup, each with one honest line of secondary text - the way a chat product says "Leaving on
October 14" under a model, except ours says what is true here: "fits, 16k context", "needs ANTHROPIC_API_KEY",
"asks before first use: sends this chat off your machine".

Switching is per message (a run's ``model_override``), never a silent edit of the bot: a scheduled run of the same bot
keeps using the bot's own model. Picking a hosted model here is the person's explicit choice for that message, so it does
not trigger the "ask before the first hosted call" rule that protects a local-first bot from drifting off the machine on
its own; the menu says which entries send the chat elsewhere, and estimate-based usage limits still apply.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .connections import ConnectionBook
from .fit import estimate_fit
from .hardware import Hardware, probe
from .models import Bot
from .providers.pricing import LOCAL_PROVIDERS, PriceBook
from .providers.registry import is_local, parse_spec

HOSTED_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
LOCAL_RUNTIMES = {"ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm"}
KNOWN_PROVIDERS = LOCAL_PROVIDERS | set(HOSTED_KEYS) | {"openai-compatible"}
_TTL = 5.0
_cache: dict[str, tuple[float, Any]] = {}


@dataclass
class Choice:
    spec: str                    # provider/model, exactly what a bot's `model` field takes
    label: str                   # short name shown in the menu
    group: str                   # "This bot" | "On this machine" | "Hosted" | a connection's title
    state: str                   # ready | setup | wont_fit
    note: str = ""               # one secondary line
    fix: str = ""                # what to do when state != ready
    default: bool = False        # the bot's own model
    hosted: bool = False         # the chat leaves this machine
    worst_case_usd: Optional[float] = None   # legacy name; local one-run cost estimate when priced
    detail: list[str] = field(default_factory=list)


class ModelNotUsable(ValueError):
    """A requested model cannot be used right now; ``fix`` says what to do."""

    def __init__(self, message: str, fix: str = "", status: int = 409):
        super().__init__(message)
        self.fix, self.status = fix, status


def short_label(spec: str) -> str:
    return parse_spec(spec)[1] or spec


def _cached(key: str, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def reset_cache() -> None:
    _cache.clear()


def _per_million(price) -> str:
    return f"${price.input:g} in / ${price.output:g} out per 1M tokens"


def _local_choices(bot: Bot, hw: Hardware, provider: Any) -> list[Choice]:
    from .modelview import installed
    out: list[Choice] = []
    ollama_up = any(r.name == "ollama" and r.reachable for r in hw.runtimes)
    if not ollama_up:
        return out
    want = bot.num_ctx or 16384
    for name, meta in sorted(_cached("installed", lambda: installed(provider)).items()):
        spec = f"ollama/{name}"
        if not is_local(spec):
            out.append(Choice(spec=spec, label=name, group="Hosted", state="setup", hosted=True,
                              note="Ollama Cloud model; inference runs on ollama.com",
                              fix="Sign in to Ollama, then use this only with Hybrid routing.",
                              detail=["Ollama classifies this tag as a cloud model",
                                      "Hutch has no price row for this route; cost caps refuse it until priced"]))
            continue
        fit = estimate_fit(meta, hw, want)
        ok = fit.status != "wont_fit"
        out.append(Choice(
            spec=spec, label=name, group="On this machine", state="ready" if ok else "wont_fit",
            note=(f"{'fits' if fit.status == 'fits' else 'tight fit'}, {fit.effective_ctx // 1024}k context"
                  if ok else "does not fit this machine"),
            fix="" if ok else fit.reason, detail=[fit.reason]))
    return out


def _hosted_choices(bot: Bot, book: PriceBook) -> list[Choice]:
    out: list[Choice] = []
    for p in book.rows():
        provider, _, model = p.model.partition("/")
        if provider not in HOSTED_KEYS:
            continue
        env = HOSTED_KEYS[provider]
        has = bool(os.environ.get(env))
        notes = [_per_million(p)]
        if p.stale:
            notes.append("price last checked " + (p.verified_on or "never"))
        out.append(Choice(
            spec=p.model, label=model, group="Hosted", state="ready" if has else "setup", hosted=True,
            note=(notes[0] if has else f"needs {env}"), fix="" if has else f"set {env} where hutch starts",
            detail=notes + [f"sends this chat to {provider}"]))
    return out


def _connection_choices(bot: Bot, store: Any, book: ConnectionBook, extra: set[str]) -> list[Choice]:
    out: list[Choice] = []
    for name, c in book.configured().items():
        has_key = book.key(name) is not None
        ack = book.ack_status(store, name)
        models = sorted({m for m in extra if m.startswith(name + "/")})
        for spec in models:
            if not has_key:
                state, fix = "setup", f"set ${c.api_key_env} or run `hutch connections set-key {name}`"
            elif ack in ("required", "stale"):
                state, fix = "setup", f"acknowledge its terms: `hutch connections ack {name}`"
            else:
                state, fix = "ready", ""
            note = fix and ("needs a key" if not has_key else "terms not acknowledged") or \
                ("flat-rate plan" if c.flat else "pay per token")
            out.append(Choice(spec=spec, label=short_label(spec), group=c.title, state=state, hosted=True,
                              note=note, fix=fix,
                              detail=[f"connection {name}: {c.billing.replace('_', ' ')}", f"sends this chat to {c.title}"]))
    return out


def model_choices(config: Any, store: Any, bot: Bot, hw: Optional[Hardware] = None, provider: Any = None) -> list[Choice]:
    hw = hw or _cached("hw", probe)
    if provider is None:
        from .runtime.ladder import get_provider
        provider = get_provider("ollama", None)
    book = PriceBook(config.state_dir / "prices.json")
    cbook = ConnectionBook(config.state_dir)

    # connection models we know about: ones bots use, ones that have actually been called
    known: set[str] = set()
    for b in store.list_bots():
        known.update(s for s in [b.model, *b.fallbacks, *(b.escalation.to if b.escalation else [])])
    known.update(f"{p}/{m}" for p, m in store.usage_models())

    from .estimate import RunEstimator
    est = RunEstimator(config, store, bot)
    choices: list[Choice] = []
    own_local = is_local(bot.model)
    own = Choice(spec=bot.model, label=short_label(bot.model), group="This bot", state="ready", default=True,
                 hosted=not own_local,
                 note="this bot's own model" if own_local else "this bot's own hosted model route",
                 detail=[] if own_local else ["this route sends the chat to a hosted model service"])
    choices.append(own)
    seen = {bot.model}
    for c in (_local_choices(bot, hw, provider) + _hosted_choices(bot, book)
              + _connection_choices(bot, store, cbook, known)):
        if bot.inference_mode.value == "local" and not is_local(c.spec):
            continue
        if c.spec in seen:
            # the bot's own model keeps its place but gains the real state/notes
            mine = next(x for x in choices if x.spec == c.spec)
            mine.state, mine.fix, mine.detail = c.state, c.fix, c.detail
            mine.note = c.note or mine.note
            continue
        seen.add(c.spec)
        choices.append(c)
    for c in choices:
        if c.hosted:
            e = est.for_model(c.spec)
            c.worst_case_usd = e.worst_case_usd
            if e.worst_case_usd is not None:
                c.detail.append(f"estimated ${e.worst_case_usd:.2f} for one run of up to {e.steps} steps; provider billing can differ")
    return choices


def validate_override(config: Any, store: Any, bot: Bot, spec: str, hw: Optional[Hardware] = None) -> str:
    """Return the normalised spec, or raise ``ModelNotUsable`` saying exactly what is wrong and how to fix it."""
    spec = (spec or "").strip()
    if not spec:
        return ""
    if "/" not in spec:
        raise ModelNotUsable(f"'{spec}' is not a model spec", "write it as provider/model, e.g. ollama/qwen3:4b",
                             status=422)
    provider, model = parse_spec(spec)
    if not model:
        raise ModelNotUsable(f"'{spec}' names a provider but no model", "add the model name after the slash", 422)
    if bot.inference_mode.value == "local" and not is_local(spec):
        raise ModelNotUsable(
            f"{spec} is blocked by {bot.name}'s Local model routes setting",
            "choose a local model, or change the bot's inference mode to Hybrid",
            409,
        )
    if bot.runtime.value not in ("builtin", "mock"):
        raise ModelNotUsable(f"{bot.name} runs on the {bot.runtime.value} runtime, which chooses its own model",
                             "switch models inside that runtime's own settings", 422)
    cbook = ConnectionBook(config.state_dir)
    if provider in cbook.names():
        if cbook.key(provider) is None:
            c = cbook.get(provider)
            raise ModelNotUsable(f"{provider} has no API key", f"set ${c.api_key_env} or run "
                                 f"`hutch connections set-key {provider}`")
        if cbook.ack_status(store, provider) in ("required", "stale"):
            raise ModelNotUsable(f"{provider}'s terms are not acknowledged yet",
                                 f"run `hutch connections ack {provider}` or use the Connections page")
        return spec
    if provider not in KNOWN_PROVIDERS:
        raise ModelNotUsable(f"'{provider}' is not a provider or connection Hutch knows",
                             "add it under Connections, or use ollama/, anthropic/, openai/, lmstudio/", 422)
    if provider in HOSTED_KEYS and not os.environ.get(HOSTED_KEYS[provider]):
        raise ModelNotUsable(f"{provider} needs an API key", f"set {HOSTED_KEYS[provider]} where hutch starts")
    return spec


def choices_json(choices: list[Choice]) -> list[dict]:
    return [asdict(c) for c in choices]
