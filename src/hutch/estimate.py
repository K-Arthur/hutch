"""What a run can cost, before it starts (SR-2).

The two products Hutch is measured against hide spend: Grok Bot shows no per-token rates, and Dots users report allowance
vanishing "42% of weekly on day one" with no warning. Hutch shows a number *before* a run, and it is deliberately a
**estimate**: every step re-sends the whole estimated prompt and uses its full per-turn output budget. Actual provider
tokenization and billing can differ, so the estimate is an admission signal, not a guarantee of the final charge.

A model with no price on file has no currency estimate, and says so: the guess is never invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .connections import ConnectionBook
from .context import estimate_tokens, prompt_tokens
from .models import Bot
from .providers.pricing import PriceBook
from .providers.registry import parse_spec
from .tools import build_tools

DEFAULT_LOCAL_TURN_TOKENS = 2048
DEFAULT_HOSTED_TURN_TOKENS = 16000


@dataclass
class RunEstimate:
    spec: str
    kind: str                       # local | flat | priced | unpriced
    prompt_tokens: int
    steps: int
    turn_tokens: int
    worst_case_usd: Optional[float]  # legacy field name; this is a local estimate, not a billing guarantee
    run_cap_usd: float               # the bot's per-run cap (0 = none)
    daily_cap_usd: float
    spent_today_usd: float
    tokens_today: int
    daily_token_cap: int
    reserved_tokens_today: int = 0
    reserved_cost_today_usd: float = 0.0
    note: str = ""

    @property
    def effective_ceiling_usd(self) -> Optional[float]:
        """Legacy field name: the lower of Hutch's estimate and the configured per-run admission limit."""
        if self.worst_case_usd is None:
            return None
        return min(self.worst_case_usd, self.run_cap_usd) if self.run_cap_usd else self.worst_case_usd

    @property
    def summary(self) -> str:
        if self.kind == "local":
            return "Runs on this machine: no per-token cost."
        if self.kind == "flat":
            return "Flat-rate plan: no per-token cost; every call still counts against your declared allowance."
        if self.kind == "unpriced":
            return (f"No price on file for {self.spec}, so a currency estimate cannot be computed, and a hosted model with no "
                    "price cannot run while a currency limit is set. Add one on the Models page.")
        if self.run_cap_usd and self.run_cap_usd < (self.worst_case_usd or 0):
            parts = [f"Estimated at up to ${self.run_cap_usd:.2f} per run under this bot's admission limit (without it, "
                     f"{self.steps} steps at full budget estimate ${self.worst_case_usd:.2f}; provider billing can differ)"]
        else:
            parts = [f"Estimated at ${self.worst_case_usd:.2f} if all {self.steps} steps use their full budget; "
                     "provider billing can differ"]
        if self.daily_cap_usd:
            parts.append(f"${self.spent_today_usd:.2f} measured + ${self.reserved_cost_today_usd:.2f} held of the "
                         f"${self.daily_cap_usd:.2f} daily limit today")
        return "; ".join(parts) + "."


class RunEstimator:
    """Computes the prompt size once; ``for_model`` prices it for any model spec."""

    def __init__(self, config: Any, store: Any, bot: Bot, prompt: str = ""):
        self.config, self.store, self.bot = config, store, bot
        from .runtime.builtin import SYSTEM_TEMPLATE
        system = SYSTEM_TEMPLATE.format(name=bot.name, description=bot.description or "(none given)",
                                        instructions=bot.instructions or "(none given)", workspace="/workspace",
                                        rehearsal="", date="2026-01-01")
        specs = [t.spec() for t in build_tools(bot.tools, None, memory_enabled=bot.memory_enabled).values()]
        msg, tool = prompt_tokens([{"role": "system", "content": system},
                                   {"role": "user", "content": prompt or "(your task)"}], specs)
        self.prompt_tokens = msg + tool
        self.prices = PriceBook(config.state_dir / "prices.json")
        book = ConnectionBook(config.state_dir)
        self.prices.flat_providers = book.flat_providers()

    def for_model(self, spec: Optional[str] = None) -> RunEstimate:
        spec = spec or self.bot.model
        provider, model = parse_spec(spec)
        lim = self.bot.limits
        local = self.prices.is_local(provider, model)
        turn = lim.max_turn_tokens or (DEFAULT_LOCAL_TURN_TOKENS if local else DEFAULT_HOSTED_TURN_TOKENS)
        worst = self.prices.estimate_run_ceiling(provider, model, self.prompt_tokens, turn, lim.max_steps)
        if local:
            kind = "local"
        elif provider in self.prices.flat_providers:
            kind = "flat"
        elif worst is None:
            kind = "unpriced"
        else:
            kind = "priced"
        measured_tokens, held_tokens, measured_cost, held_cost = self.store.bot_budget_today(self.bot.id)
        return RunEstimate(spec=spec, kind=kind, prompt_tokens=self.prompt_tokens, steps=lim.max_steps, turn_tokens=turn,
                           worst_case_usd=worst if kind == "priced" else None, run_cap_usd=lim.max_cost_usd,
                           daily_cap_usd=lim.daily_cost_cap_usd, spent_today_usd=measured_cost,
                           tokens_today=measured_tokens, daily_token_cap=lim.daily_token_cap,
                           reserved_tokens_today=held_tokens, reserved_cost_today_usd=held_cost)


def estimate_run(config: Any, store: Any, bot: Bot, prompt: str = "", model: Optional[str] = None) -> RunEstimate:
    return RunEstimator(config, store, bot, prompt).for_model(model)
