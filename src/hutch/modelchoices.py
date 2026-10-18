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

import hashlib
import os
import time
from collections import OrderedDict
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
_CACHE_MAX = 128
OPENROUTER_POPULAR_LIMIT = 40
OPENROUTER_SEARCH_LIMIT = 80
OPENROUTER_QUERY_MAX = 80
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


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


def _cached(key: str, fn, *, ttl: float = _TTL):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        _cache.move_to_end(key)
        return hit[1]
    if hit:
        _cache.pop(key, None)
    val = fn()
    _cache[key] = (time.monotonic(), val)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
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


def _connection_choices(bot: Bot, store: Any, book: ConnectionBook, extra: set[str], *,
                        discover_hosted_models: bool = True, model_query: str = "") -> list[Choice]:
    out: list[Choice] = []
    model_query = (model_query or "").strip()[:OPENROUTER_QUERY_MAX]
    for name, c in book.configured().items():
        has_key = book.has_key(name)
        ack = book.ack_status(store, name)
        models = {m for m in extra if m.startswith(name + "/")}
        catalog_by_spec: dict[str, dict[str, Any]] = {}
        model_error = ""
        if has_key and c.auth_type == "chatgpt-siws" and discover_hosted_models and not model_query:
            # Model selection is an explicit user action; it may refresh the
            # protected plan token and fetch the account's non-billable catalog.
            from .chatgpt_auth import ChatGPTAuthBook, ChatGPTAuthError
            try:
                models.update(f"{name}/{row['slug']}"
                              for row in ChatGPTAuthBook(book.state_dir).list_models(c.auth_account_id))
            except ChatGPTAuthError as exc:
                model_error = str(exc)
        elif has_key and c.template == "openrouter" and discover_hosted_models and c.models_endpoint:
            from .providers.base import ProviderError
            from .providers.connection import provider_for_connection
            key_hash = hashlib.sha256((book.key(name) or "").encode()).hexdigest()
            query_key = model_query.casefold() if len(model_query) >= 2 else ""
            cache_key = f"openrouter-catalog:{name}:{c.base_url}:{key_hash}:{query_key}"
            try:
                rows = _cached(cache_key,
                               lambda: provider_for_connection(book, name, "catalog").list_openrouter_catalog(
                                   query_key, limit=OPENROUTER_SEARCH_LIMIT if query_key else OPENROUTER_POPULAR_LIMIT),
                               ttl=60.0)
                catalog_by_spec = {f"{name}/{row['id']}": row for row in rows}
                models.update(catalog_by_spec)
            except ProviderError:
                # A catalog outage must not disable a route already selected by the
                # user; ordinary run admission still checks its key and policy.
                catalog_by_spec = {}
        elif has_key and discover_hosted_models and c.models_endpoint:
            from .providers.base import ProviderError
            from .providers.connection import provider_for_connection
            key_hash = hashlib.sha256((book.key(name) or "").encode()).hexdigest()
            cache_key = f"provider-catalog:{name}:{c.base_url}:{key_hash}"
            try:
                rows = _cached(cache_key,
                               lambda: provider_for_connection(book, name, "catalog").list_models(),
                               ttl=60.0)
                discovered = {row.name for row in rows if row.name}
                if len(model_query) >= 2:
                    q = model_query.casefold()
                    discovered = {model for model in discovered if q in model.casefold()}
                models.update(f"{name}/{model}" for model in discovered)
            except ProviderError as exc:
                model_error = str(exc)
        ordered_specs = list(catalog_by_spec) + sorted(models - set(catalog_by_spec))
        for spec in ordered_specs:
            if not has_key:
                state = "setup"
                fix = ("sign in with ChatGPT and authorize plan use on Connections" if c.auth_type == "chatgpt-siws"
                       else f"set ${c.api_key_env} or run `hutch connections set-key {name}`")
            elif ack in ("required", "stale"):
                state, fix = "setup", f"acknowledge its terms: `hutch connections ack {name}`"
            else:
                state, fix = "ready", ""
            catalog_row = catalog_by_spec.get(spec)
            note = ("needs a key" if not has_key else
                    "terms not acknowledged" if ack in ("required", "stale") else
                    _openrouter_price_note(catalog_row) if catalog_row and catalog_row.get("pricing") else
                    "listed in OpenRouter's model catalog" if catalog_row else
                    "subscription; output limit is provider-unbounded" if c.auth_type == "chatgpt-siws" else
                    "flat-rate plan" if c.flat else "pay per token")
            detail = [f"connection {name}: {c.billing.replace('_', ' ')}",
                      f"sends this chat to {c.title}"]
            if model_error:
                detail.append("model list unavailable; retry from Connections")
            if catalog_row:
                detail.append("OpenRouter's published catalog price does not verify the final charge; Hutch requires a reviewed price entry for currency-limited admission.")
                if catalog_row.get("supports_tools"):
                    detail.append("OpenRouter lists tool support for this model; actual tool-call behavior is not verified.")
                else:
                    detail.append("OpenRouter does not list tool support for this model; model behavior is not verified.")
                if catalog_row.get("context_length"):
                    detail.append(f"OpenRouter lists a {catalog_row['context_length']:,}-token context window; upstream availability may vary.")
            out.append(Choice(spec=spec, label=(catalog_row["name"] if catalog_row else short_label(spec)),
                              group=c.title, state=state, hosted=True,
                              note=note, fix=fix,
                              detail=detail +
                                     (["Responses preview does not accept a provider-enforced output-token limit; Hutch estimates usage"]
                                      if c.auth_type == "chatgpt-siws" else [])))
    return out


def _openrouter_price_note(row: Optional[dict[str, Any]]) -> str:
    pricing = row.get("pricing") if isinstance(row, dict) else None
    if not isinstance(pricing, dict) or "prompt" not in pricing or "completion" not in pricing:
        return "listed in OpenRouter's model catalog"
    return (f"catalog price ${pricing['prompt']:g} in / ${pricing['completion']:g} out per 1M tokens")


def model_choices(config: Any, store: Any, bot: Bot, hw: Optional[Hardware] = None, provider: Any = None, *,
                  discover_hosted_models: bool = True, model_query: str = "") -> list[Choice]:
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
    own_local = is_local(bot.model) if bot.model else False
    retired_fixture = bot.model.startswith("mock/")
    own_hosted = bool(bot.model) and not own_local and not retired_fixture
    own = Choice(spec=bot.model, label=short_label(bot.model) if bot.model else "Choose a model",
                 group="This bot", state="setup" if not bot.model or retired_fixture else "ready",
                 default=True, hosted=own_hosted,
                 note=("no model route is configured" if not bot.model else
                       "legacy test route; choose a real model" if retired_fixture else
                       "this bot's own model" if own_local else "this bot's own hosted model route"),
                 fix="Choose a configured Ollama, OpenAI, Anthropic, or compatible route" if not bot.model or retired_fixture else "",
                 detail=["this route sends the chat to a hosted model service"] if own_hosted else [])
    choices.append(own)
    seen = {bot.model}
    allow_hosted_discovery = discover_hosted_models and bot.inference_mode.value not in ("local", "offline")
    for c in (_local_choices(bot, hw, provider) + _hosted_choices(bot, book)
              + _connection_choices(bot, store, cbook, known,
                                    discover_hosted_models=allow_hosted_discovery, model_query=model_query)):
        if bot.inference_mode.value in ("local", "offline") and not is_local(c.spec):
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


def validate_override(config: Any, store: Any, bot: Bot, spec: str, hw: Optional[Hardware] = None, *,
                      allow_unconfigured: bool = False) -> str:
    """Return the normalized route, or raise ``ModelNotUsable`` with a fix.

    ``allow_unconfigured`` is reserved for unsaved configuration import: it
    still validates route syntax, provider identity, runtime and mode policy,
    but defers local credentials and terms acknowledgement until creation.
    """
    spec = (spec or bot.model or "").strip()
    if not spec:
        raise ModelNotUsable("No model route is configured for this bot",
                             "configure a provider in Connections, then choose its model route", 422)
    if "/" not in spec:
        raise ModelNotUsable(f"'{spec}' is not a model spec", "write it as provider/model, e.g. ollama/qwen3:4b",
                             status=422)
    provider, model = parse_spec(spec)
    if not model:
        raise ModelNotUsable(f"'{spec}' names a provider but no model", "add the model name after the slash", 422)
    if provider == "mock":
        raise ModelNotUsable("Mock inference is test-only and cannot run user tasks",
                             "choose a configured Ollama, OpenAI, Anthropic, or compatible model route", 422)
    if bot.inference_mode.value in ("local", "offline") and not is_local(spec):
        label = "Strict offline" if bot.inference_mode.value == "offline" else "Local model routes"
        raise ModelNotUsable(
            f"{spec} is blocked by {bot.name}'s {label} setting",
            "choose a local model, or change the bot's inference mode to Hybrid",
            409,
        )
    if bot.inference_mode.value == "offline":
        from .providers.registry import validate_offline_route
        provider, _ = parse_spec(spec)
        try:
            validate_offline_route(spec, bot.base_url if provider == parse_spec(bot.model)[0] else None)
        except ValueError as exc:
            raise ModelNotUsable(str(exc), "choose a verified local model route", 409) from None
    if bot.runtime.value != "builtin":
        raise ModelNotUsable(f"{bot.name} runs on the {bot.runtime.value} runtime, which chooses its own model",
                             "switch models inside that runtime's own settings", 422)
    cbook = ConnectionBook(config.state_dir)
    if provider in cbook.names():
        if allow_unconfigured:
            return spec
        if not cbook.has_key(provider):
            c = cbook.get(provider)
            if c.auth_type == "chatgpt-siws":
                raise ModelNotUsable(f"{provider} has no plan-authorized ChatGPT account",
                                     "sign in with ChatGPT and authorize plan use on Connections")
            raise ModelNotUsable(f"{provider} has no API key", f"set ${c.api_key_env} or run "
                                 f"`hutch connections set-key {provider}`")
        if cbook.ack_status(store, provider) in ("required", "stale"):
            raise ModelNotUsable(f"{provider}'s terms are not acknowledged yet",
                                 f"run `hutch connections ack {provider}` or use the Connections page")
        return spec
    if provider not in KNOWN_PROVIDERS:
        raise ModelNotUsable(f"'{provider}' is not a provider or connection Hutch knows",
                             "add it under Connections, or use ollama/, anthropic/, openai/, lmstudio/", 422)
    if allow_unconfigured:
        return spec
    if provider in HOSTED_KEYS and not os.environ.get(HOSTED_KEYS[provider]):
        raise ModelNotUsable(f"{provider} needs an API key", f"set {HOSTED_KEYS[provider]} where hutch starts")
    return spec


def choices_json(choices: list[Choice]) -> list[dict]:
    return [asdict(c) for c in choices]
