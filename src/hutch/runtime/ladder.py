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
from dataclasses import dataclass
from typing import Optional

from ..models import Bot, Run, iso, utcnow
from ..providers import Provider, make_provider, parse_spec
from ..providers.pricing import PriceBook
from ..store import UsageBudgetRefusal

_PROVIDERS: dict[tuple[str, Optional[str]], Provider] = {}
_LOCK = threading.Lock()


def get_provider(provider: str, base_url: Optional[str]) -> Provider:
    """Providers are cached so HTTP connections and `show()` metadata are reused across runs."""
    key = (provider, base_url)
    with _LOCK:
        if key not in _PROVIDERS:
            _PROVIDERS[key] = make_provider(provider, base_url)
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
    from ..providers.pricing import LOCAL_PROVIDERS
    provider, model = parse_spec(spec)
    return Rung(spec=spec, provider=provider, model=model, local=provider in LOCAL_PROVIDERS, role=role)


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


class SpendGuard:
    """Estimate-based admission limits for hosted calls; provider billing can differ from Hutch's estimate."""

    def __init__(self, store, bot: Bot, run: Run, prices: PriceBook, connections=None):
        self.store, self.bot, self.run, self.prices = store, bot, run, prices
        self.connections = connections

    def spent_today(self) -> float:
        return self.store.cost_today(self.bot.id)

    @property
    def has_cost_caps(self) -> bool:
        lim = self.bot.limits
        return bool(lim.max_cost_usd or lim.daily_cost_cap_usd)

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

    def reserve(self, rung: Rung, est_prompt_tokens: int, max_turn_tokens: int) -> str:
        """Acquire a cross-process reservation before this provider call may start."""
        account_id, account_cap, quotas = self.account_policy(rung)
        worst = self.prices.cost(rung.provider, rung.model, est_prompt_tokens, max_turn_tokens) or 0.0
        try:
            return self.store.reserve_usage(
                run_id=self.run.id, bot_id=self.bot.id, provider=rung.provider, account_id=account_id,
                model=rung.model, reserved_tokens=est_prompt_tokens + max_turn_tokens, reserved_cost_usd=worst,
                daily_token_cap=self.bot.limits.daily_token_cap, max_run_cost_usd=self.bot.limits.max_cost_usd,
                daily_bot_cost_cap_usd=self.bot.limits.daily_cost_cap_usd, expected_fence=self.run.fence,
                daily_account_cost_cap_usd=account_cap, account_quotas=quotas)
        except UsageBudgetRefusal:
            raise

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
        _, account_cap, _ = self.account_policy(rung)
        quota = self.quota_refusal(rung, est_prompt_tokens, max_turn_tokens)
        if quota:
            return quota
        if not self.prices.has_price(rung.provider, rung.model):
            if self.has_cost_caps or account_cap:
                return (f"{rung.spec} has no price in prices.json, so Hutch cannot calculate a currency estimate "
                        "for the configured limit; add a row (or remove the limit) to use it")
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
