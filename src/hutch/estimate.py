"""What a run can cost, before it starts (SR-2).

The two products Hutch is measured against hide spend: Grok Bot shows no per-token rates, and Dots users report allowance
vanishing "42% of weekly on day one" with no warning. Hutch shows a number *before* a run, and it is deliberately a
**ceiling**: every step re-sends the whole prompt and uses its full per-turn budget. Real runs cost much less; the ceiling
is what the spend guard will actually enforce, so it is the figure that can never be exceeded.

A model with no price on file has no ceiling, and says so: the guess is never invented.
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
    worst_case_usd: Optional[float]  # None unless kind == priced
    run_cap_usd: float               # the bot's per-run cap (0 = none)
    daily_cap_usd: float
    spent_today_usd: float
    tokens_today: int
    daily_token_cap: int
    note: str = ""

    @property
    def effective_ceiling_usd(self) -> Optional[float]:
        """The most one run can spend: the lower of the worst case and the bot's per-run cap."""
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
            return (f"No price on file for {self.spec}, so a worst case cannot be computed, and a hosted model with no "
                    "price cannot run under a spend cap. Add one on the Models page.")
        if self.run_cap_usd and self.run_cap_usd < (self.worst_case_usd or 0):
            parts = [f"At most ${self.run_cap_usd:.2f} per run: that is this bot's cap (without it, {self.steps} steps at "
                     f"full budget could reach ${self.worst_case_usd:.2f}; typical runs cost far less)"]
        else:
            parts = [f"At most ${self.worst_case_usd:.2f} if all {self.steps} steps use their full budget "
                     f"(typical runs cost far less)"]
        if self.daily_cap_usd:
            parts.append(f"${self.spent_today_usd:.2f} of the ${self.daily_cap_usd:.2f} daily cap used today")
        return "; ".join(parts) + "."


class RunEstimator:
    """Computes the prompt size once; ``for_model`` prices it for any model spec."""

    def __init__(self, config: Any, store: Any, bot: Bot, prompt: str = ""):
        self.config, self.store, self.bot = config, store, bot
        from .runtime.builtin import SYSTEM_TEMPLATE
        facts = store.recall_all(bot.id) if bot.memory_enabled else []
        memory = "What you remember from previous runs:\n" + "\n".join(f"- {m.key}: {m.value}" for m in facts[:40]) if facts else ""
        system = SYSTEM_TEMPLATE.format(name=bot.name, description=bot.description or "(none given)",
                                        instructions=bot.instructions or "(none given)", workspace="/workspace",
                                        rehearsal="", date="2026-01-01", memory_block=memory)
        specs = [t.spec() for t in build_tools(bot.tools, None).values()]
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
        local = self.prices.is_local(provider)
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
        return RunEstimate(spec=spec, kind=kind, prompt_tokens=self.prompt_tokens, steps=lim.max_steps, turn_tokens=turn,
                           worst_case_usd=worst if kind == "priced" else None, run_cap_usd=lim.max_cost_usd,
                           daily_cap_usd=lim.daily_cost_cap_usd, spent_today_usd=self.store.cost_today(self.bot.id),
                           tokens_today=self.store.tokens_today(self.bot.id), daily_token_cap=lim.daily_token_cap)


def estimate_run(config: Any, store: Any, bot: Bot, prompt: str = "", model: Optional[str] = None) -> RunEstimate:
    return RunEstimator(config, store, bot, prompt).for_model(model)
