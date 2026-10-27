"""Which model runs the next turn, and may it be called? (SR-8, LM-9, LM-10, SR-2)

Two different failures need two different responses: availability failures move through configured fallbacks, while
quality failures may take one explicitly configured escalation step.

* **availability** (runtime down, rate-limited, out of memory, model not installed, refusal) -> *fallback*:
  the next model in ``bot.fallbacks``, in order (SR-8).
* **quality** (malformed tool calls again and again, a loop, the prompt overflowing the window) -> *escalation*:
  ONE rung up ``bot.escalation.to`` (LM-9), never straight to the top and never restarting the run.

Every hop to a hosted model passes the SpendGuard first: estimate-based run and daily limits are respected, and - for a
bot that is local by default - a human said yes to the first hosted call (LM-10).
"""

from __future__ import annotations

import threading
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..models import Bot, Run, iso, utcnow
from ..money import parse_usd, to_store_reserved
from ..providers import Provider, make_provider, parse_spec
from ..providers.pricing import PriceBook
from ..store import CallQuote, Reservation

_PROVIDERS: dict[tuple, Provider] = {}
_LOCK = threading.Lock()


def get_provider(provider: str, base_url: Optional[str]) -> Provider:
    """Providers are cached so HTTP connections and `show()` metadata are reused across runs."""
    # Long-lived executors must not retain revoked/rotated ambient credentials or endpoints.
    ambient_env = dict(os.environ)
    relevant = {k: ambient_env.get(k, "") for k in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "HUTCH_API_KEY", "HUTCH_BASE_URL", "OLLAMA_HOST")}
    digest = hashlib.sha256(repr(sorted(relevant.items())).encode()).hexdigest()
    key = (provider, base_url, digest)
    with _LOCK:
        if key not in _PROVIDERS:
            _PROVIDERS[key] = make_provider(provider, base_url, env=ambient_env)
        return _PROVIDERS[key]


def reset_provider_cache() -> None:
    with _LOCK:
        _PROVIDERS.clear()


@dataclass(frozen=True)
class Rung:
    spec: str
    provider: str
    model: str
    local: bool
    role: str                 # primary | fallback | escalation

    @property
    def label(self) -> str:
        return self.spec


def make_rung(spec: str, role: str) -> Rung:
    from ..providers.pricing import is_local_route
    provider, model = parse_spec(spec)
    return Rung(spec=spec, provider=provider, model=model, local=is_local_route(provider, model), role=role)


class Ladder:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.primary = make_rung(bot.model, "primary")
        self.fallbacks = [make_rung(s, "fallback") for s in bot.fallbacks]
        self.escalations = [make_rung(s, "escalation") for s in (bot.escalation.to if bot.escalation else [])]
        self.current = self.primary
        #: rungs that were refused (spend cap, not usable) for the rest of this run, and whether a human said
        #: no to hosted calls: neither may be re-asked on every later bad turn (a denial must stick)
        self.blocked: set[str] = set()
        self.hosted_denied = False
        self.authorized_routes: set[tuple] = set()   # per-run authority; never a generic standing hosted grant

    @property
    def local_default(self) -> bool:
        """LM-10 applies to bots whose own model is local."""
        return self.primary.local

    def base_url_for(self, rung: Rung) -> Optional[str]:
        return self.bot.base_url if rung.provider == self.primary.provider else None

    def next_fallback(self) -> Optional[Rung]:
        """Next model after an AVAILABILITY failure of the current one."""
        if self.current.role == "escalation":
            i = [r.spec for r in self.escalations].index(self.current.spec)
            return self.escalations[i + 1] if i + 1 < len(self.escalations) else None
        if self.current.role == "primary":
            return self.fallbacks[0] if self.fallbacks else None
        i = [r.spec for r in self.fallbacks].index(self.current.spec)
        return self.fallbacks[i + 1] if i + 1 < len(self.fallbacks) else None

    def next_escalation(self) -> Optional[Rung]:
        """ONE rung above the current model after a QUALITY failure."""
        if not self.escalations:
            return None
        if self.current.role != "escalation":
            return self.escalations[0]
        i = [r.spec for r in self.escalations].index(self.current.spec)
        return self.escalations[i + 1] if i + 1 < len(self.escalations) else None


def resolve_quote(rung: Rung, prices: PriceBook, connections, est_prompt_tokens: int,
                  max_turn_tokens: int, *, fetch: bool = True,
                  require_fresh_openrouter: bool = False) -> CallQuote:
    """The price basis admission holds, from the best available source.

    Resolution order: local -> flat subscription -> fresh live OpenRouter quote -> labeled stale live quote
    -> the reviewed price file (labeled with its verified-on date) -> "no basis". A strict OpenRouter
    ceiling requires a live quote and reserves each eligible endpoint's published
    input capacity plus the requested output, at conservative tier/cache rates.
    It fails closed when refresh fails, never falling through to stale or file
    pricing. Capacity reservation bounds tokenizer-estimate error for this one
    request; it is not a guarantee of external provider billing. ``usd=None``
    means no basis exists; it is never treated as free, and the applicable budget policy decides whether
    that refuses admission or is recorded as unknown.

    ``fetch=False`` restricts the live source to a quote already cached in this process: listing and
    other background displays must never make a network request, while admission and an explicitly
    opened preflight review may refresh it.
    """
    if rung.local:
        return CallQuote(usd=0.0, source="local")
    if rung.provider in prices.flat_providers:
        return CallQuote(usd=0.0, source="flat")
    conn = connections.get(rung.provider) if connections else None
    if conn is not None and getattr(conn, "template", "") == "openrouter":
        from ..providers import openrouter_pricing
        service = openrouter_pricing.live_pricing(
            getattr(conn, "base_url", "") or openrouter_pricing.DEFAULT_BASE_URL)
        live_quote = (service.quote(rung.model, allow_stale=not require_fresh_openrouter)
                      if fetch else service.cached(rung.model))
        if (require_fresh_openrouter and
                (live_quote is None or live_quote.stale or live_quote.expires_at is None
                 or live_quote.expires_at <= datetime.now(timezone.utc))):
            return CallQuote(usd=None, source="openrouter_unavailable", stale=True,
                             snapshot_digest=(live_quote.snapshot_digest if live_quote else ""),
                             expires_at=(live_quote.expires_at.isoformat() if live_quote and live_quote.expires_at else ""),
                             currency="USD", billing_unit="USD/call-estimate")
        if live_quote is not None:
            eligible = lambda endpoint: (endpoint.status == 0
                and (endpoint.supports_tools is None or endpoint.supports_tools)
                and ((endpoint.context_length >= est_prompt_tokens + max_turn_tokens)
                     if require_fresh_openrouter else
                     (endpoint.context_length == 0 or endpoint.context_length >= est_prompt_tokens + max_turn_tokens))
                and (endpoint.max_prompt_tokens == 0 or endpoint.max_prompt_tokens >= est_prompt_tokens)
                and (endpoint.max_completion_tokens == 0 or endpoint.max_completion_tokens >= max_turn_tokens))
            live = live_quote.worst_case(
                est_prompt_tokens, max_turn_tokens,
                conservative_tiers=True,
                reserve_context_capacity=require_fresh_openrouter,
                eligible=eligible)
            if live is not None:
                identities = tuple(endpoint.identity or f"{endpoint.provider_name}:{endpoint.name}"
                                   for endpoint in live_quote.endpoints if eligible(endpoint))
                return CallQuote(usd=to_store_reserved(live), source="openrouter",
                                 verified_on=live_quote.fetched_at.isoformat(), stale=live_quote.stale,
                                 endpoints_considered=len(identities), snapshot_digest=live_quote.snapshot_digest,
                                 expires_at=(live_quote.expires_at.isoformat() if live_quote.expires_at else ""),
                                 endpoint_identities=identities, currency="USD",
                                 billing_unit=("USD/context-capacity-reserve" if require_fresh_openrouter
                                               else "USD/call-estimate"))
            if require_fresh_openrouter:
                return CallQuote(usd=None, source="openrouter_no_eligible_endpoint", stale=True,
                                 snapshot_digest=live_quote.snapshot_digest,
                                 expires_at=(live_quote.expires_at.isoformat() if live_quote.expires_at else ""),
                                 endpoint_identities=(), currency="USD", billing_unit="USD/call-estimate")
        elif require_fresh_openrouter:
            return CallQuote(usd=None, source="openrouter_unavailable", stale=True,
                             currency="USD", billing_unit="USD/call-estimate")
    cost = prices.cost(rung.provider, rung.model, est_prompt_tokens, max_turn_tokens)
    if cost is None:
        return CallQuote(usd=None, source="unknown")
    price = prices.lookup(rung.provider, rung.model)
    return CallQuote(usd=to_store_reserved(parse_usd(cost)), source="price_file",
                     verified_on=(price.verified_on if price else ""),
                     stale=(price.stale if price else True))


class SpendGuard:
    """Estimate-based admission limits for hosted calls; provider billing can differ from Hutch's estimate."""

    def __init__(self, store, bot: Bot, run: Run, prices: PriceBook, connections=None):
        self.store, self.bot, self.run, self.prices = store, bot, run, prices
        self.connections = connections

    def spent_today(self) -> float:
        return self.store.cost_today(self.bot.id)

    def policies(self, rung: Rung) -> dict:
        """The configured warn/pause/ceiling bands that apply to a call on this rung."""
        account_id, _cap, _quotas = self.account_policy(rung)
        try:
            return self.store.budget_policies_for(run_id=self.run.id, account_id=account_id)
        except Exception:
            return {}

    @property
    def has_cost_caps(self) -> bool:
        lim = self.bot.limits
        if lim.max_cost_usd or lim.daily_cost_cap_usd:
            return True
        return bool(self.store.budget_policies_for(run_id=self.run.id))

    def worst_case(self, rung: Rung, est_prompt_tokens: int, max_turn_tokens: int) -> CallQuote:
        """The price basis admission will hold, from the best available source (see :func:`resolve_quote`)."""
        account_id, account_cap, _quotas = self.account_policy(rung)
        policies = self.store.budget_policies_for(run_id=self.run.id, account_id=account_id)
        strict = (self.bot.limits.max_cost_usd > 0 or self.bot.limits.daily_cost_cap_usd > 0
                  or account_cap > 0 or self.run.delegation_budget_cost_usd is not None
                  or any(policy.ceiling_usd is not None for policy in policies.values()))
        return resolve_quote(rung, self.prices, self.connections, est_prompt_tokens, max_turn_tokens,
                             require_fresh_openrouter=strict)

    def quota_state(self, rung: Rung) -> Optional[tuple[int, int, str]]:
        """(tokens used in the window, declared allowance, window) for a subscription connection, if one is set."""
        conn = self.connections.get(rung.provider) if self.connections else None
        if conn is None or not conn.quota.tokens:
            return None
        used = self.store.account_usage_tokens_since(conn.account_id, conn.quota.seconds)
        reserved, _ = self.store.reserved_account_usage_since(conn.account_id, conn.quota.seconds)
        return used + reserved, conn.quota.tokens, conn.quota.window

    def account_policy(self, rung: Rung) -> tuple[str, float, list[tuple[int, float]]]:
        conn = self.connections.get(rung.provider) if self.connections else None
        if conn is None:
            return rung.provider, 0.0, []
        cap, quotas = self.connections.account_policy(conn.account_id)
        return conn.account_id, cap, quotas

    def reserve(self, rung: Rung, est_prompt_tokens: int, max_turn_tokens: int, *, route_hash: str = "",
                request_hash: str = "", quote_override: Optional[CallQuote] = None) -> Reservation:
        """Acquire a cross-process reservation before this provider call may start."""
        account_id, account_cap, quotas = self.account_policy(rung)
        quote = quote_override or self.worst_case(rung, est_prompt_tokens, max_turn_tokens)
        return self.store.admit_and_reserve(
            run_id=self.run.id, bot_id=self.bot.id, provider=rung.provider, account_id=account_id,
            model=rung.model, reserved_tokens=est_prompt_tokens + max_turn_tokens, quote=quote,
            daily_token_cap=self.bot.limits.daily_token_cap, max_run_cost_usd=self.bot.limits.max_cost_usd,
            daily_bot_cost_cap_usd=self.bot.limits.daily_cost_cap_usd, expected_fence=self.run.fence,
            daily_account_cost_cap_usd=account_cap, account_quotas=quotas, route_hash=route_hash,
            request_hash=request_hash)

    def quota_refusal(self, rung: Rung, est_prompt_tokens: int, max_turn_tokens: int) -> Optional[str]:
        """CN-5: stop BEFORE the plan's allowance is spent, not after the vendor cuts you off (or bills overage)."""
        state = self.quota_state(rung)
        if state is None:
            return None
        used, limit, window = state
        label = {"5h": "the last 5 hours", "day": "the last 24 hours", "week": "the last 7 days",
                 "month": "the last 30 days"}[window]
        if used >= limit:
            return (f"the usage allowance for {rung.provider} is spent: {used:,} of {limit:,} tokens in {label}. "
                    "Raise it on the Connections page if your plan allows more")
        if used + est_prompt_tokens + max_turn_tokens > limit:
            return (f"the next call to {rung.spec} could pass the {limit:,}-token allowance for {rung.provider} "
                    f"({used:,} used in {label})")
        return None

    def refusal(self, rung: Rung, est_prompt_tokens: int, max_turn_tokens: int) -> Optional[str]:
        """Why this call must not happen, or None. Local models are free and always allowed."""
        if rung.local:
            return None
        connection = self.connections.get(rung.provider) if self.connections else None
        if connection is not None and connection.auth_type == "chatgpt-siws":
            from ..chatgpt_consent import has_background_provider_consent, is_background_run
            if is_background_run(self.run):
                # A long-lived run must observe a permission revoked after it
                # started. Providers are checked before every request, so read
                # the authoritative Bot record here instead of trusting the
                # execution process's startup snapshot.
                current_bot = self.store.get_bot(self.bot.id) if hasattr(self.store, "get_bot") else self.bot
                if current_bot is None or not has_background_provider_consent(
                        current_bot, rung.provider, connection.auth_account_id):
                    return (f"this scheduled or specialist run has no current express consent to use the ChatGPT plan "
                            f"for {rung.provider}; review and allow background use in this Bot's settings")
        _, account_cap, _ = self.account_policy(rung)
        quota = self.quota_refusal(rung, est_prompt_tokens, max_turn_tokens)
        if quota:
            return quota
        if not self.prices.has_price(rung.provider, rung.model):
            policies = self.policies(rung)
            strict = [p for p in policies.values() if p.ceiling_usd is not None or p.unknown_price == "refuse"]
            if self.bot.limits.max_cost_usd or self.bot.limits.daily_cost_cap_usd or account_cap:
                return (f"{rung.spec} has no price in prices.json, so Hutch cannot calculate a currency estimate "
                        "for the configured limit; add a row (or remove the limit) to use it")
            if strict:
                scope = strict[0]
                return (f"{rung.spec} has no price basis and the USD budget on {scope.scope_kind} "
                        f"'{scope.scope_id}' requires one; add a price row or allow unknown prices there")
            return None
        worst = self.prices.cost(rung.provider, rung.model, est_prompt_tokens, max_turn_tokens) or 0.0
        lim = self.bot.limits
        if lim.max_cost_usd and self.run.cost_usd + worst > lim.max_cost_usd:
            return (f"the next call to {rung.spec} could cost up to ${worst:.4f}; this run has spent "
                    f"${self.run.cost_usd:.4f} of its ${lim.max_cost_usd:.2f} cap")
        if lim.daily_cost_cap_usd:
            spent = self.spent_today()
            if spent + worst > lim.daily_cost_cap_usd:
                return (f"the next call to {rung.spec} could cost up to ${worst:.4f}; this bot has spent "
                        f"${spent:.4f} of its ${lim.daily_cost_cap_usd:.2f} daily cap")
        return None
