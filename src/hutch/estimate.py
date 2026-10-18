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
    # --- preflight detail (SR-2): the basis a reservation would hold, and the scope's current state
    message_tokens: int = 0
    tool_tokens: int = 0
    next_call_usd: Optional[float] = None     # worst-case price basis for ONE call (what admission holds)
    price_source: str = ""                    # local | flat | openrouter | openrouter_unavailable | price_file | unknown
    price_verified_on: str = ""               # price row date, or the live quote fetch time (UTC ISO)
    price_stale: bool = False
    price_snapshot_sha256: str = ""
    price_expires_at: str = ""
    price_endpoint_identities: tuple[str, ...] = ()
    currency: str = "USD"
    billing_unit: str = "USD/call-estimate"
    window_tokens: int = 0                    # 0 = the destination has not reported a window
    window_note: str = ""
    budget_scope: str = ""                    # conversation | bot | "" when no policy applies
    budget_scope_id: str = ""
    warn_usd: Optional[float] = None
    pause_usd: Optional[float] = None
    ceiling_usd: Optional[float] = None
    budget_measured_usd: float = 0.0
    budget_held_usd: float = 0.0

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
            if self.price_source.startswith("openrouter_"):
                return (f"A fresh eligible OpenRouter quote is unavailable for {self.spec}; this capped request is blocked. "
                        "Retry when endpoint pricing and limits can be refreshed.")
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

    def __init__(self, config: Any, store: Any, bot: Bot, prompt: str = "",
                 conversation_context: Optional[list[dict[str, str]]] = None,
                 conversation_id: str = "", skills: Optional[list[str]] = None, rehearse: bool = False):
        self.config, self.store, self.bot = config, store, bot
        from .runtime.builtin import COORDINATOR_GUIDANCE, REHEARSAL_NOTE, SYSTEM_TEMPLATE
        coordination = COORDINATOR_GUIDANCE if store.workspace_coordinator_id() == bot.id else ""
        system = SYSTEM_TEMPLATE.format(name=bot.name, description=bot.description or "(none given)",
                                        instructions=bot.instructions or "(none given)", workspace="/workspace",
                                        rehearsal=REHEARSAL_NOTE if rehearse else "",
                                        coordination=coordination, date="2026-01-01")
        from .readiness import available_connection_services
        from .skills import SkillRegistry, activated_block, catalog_block
        resolved_skills = SkillRegistry(config.state_dir).effective_for_bot(
            bot, activation=list(skills or []), runtime=bot.runtime.value,
            connections=available_connection_services(store, bot))
        skill_blocks = [block for block in (catalog_block(resolved_skills), activated_block(resolved_skills)) if block]
        if skill_blocks:
            system = system + "\n\n" + "\n\n".join(skill_blocks)
        specs = [t.spec() for t in build_tools(bot.tools, None, memory_enabled=bot.memory_enabled).values()]
        if resolved_skills.catalog:
            from .tools.skill import UseSkillTool
            specs.append(UseSkillTool(resolved_skills).spec())
        if conversation_id:
            from .tools.choice import AskUserChoiceTool
            specs.append(AskUserChoiceTool().spec())
        msg, tool = prompt_tokens([{"role": "system", "content": system}, *(conversation_context or []),
                                   {"role": "user", "content": prompt or "(your task)"}], specs)
        self.message_tokens, self.tool_tokens = msg, tool
        self.prompt_tokens = msg + tool
        self.prices = PriceBook(config.state_dir / "prices.json")
        book = ConnectionBook(config.state_dir)
        self.book = book
        self.prices.flat_providers = book.flat_providers()

    def for_model(self, spec: Optional[str] = None, conversation_id: str = "",
                  fetch_quotes: bool = False) -> RunEstimate:
        spec = spec or self.bot.model
        provider, model = parse_spec(spec)
        lim = self.bot.limits
        local = self.prices.is_local(provider, model)
        turn = lim.max_turn_tokens or (DEFAULT_LOCAL_TURN_TOKENS if local else DEFAULT_HOSTED_TURN_TOKENS)
        from .runtime.ladder import make_rung, resolve_quote
        rung = make_rung(spec, "primary")
        scope_kind, scope_id = "", ""
        if conversation_id and self.store.get_budget_policy("conversation", conversation_id) is not None:
            scope_kind, scope_id = "conversation", conversation_id
        elif self.store.get_budget_policy("bot", self.bot.id) is not None:
            scope_kind, scope_id = "bot", self.bot.id
        policy = self.store.get_budget_policy(scope_kind, scope_id) if scope_kind else None
        conn = self.book.get(provider)
        account_cap = self.book.account_policy(conn.account_id)[0] if conn is not None else 0.0
        strict_quote = (lim.max_cost_usd > 0 or lim.daily_cost_cap_usd > 0 or account_cap > 0
                        or bool(policy and policy.ceiling_usd is not None))
        quote = resolve_quote(rung, self.prices, self.book, self.prompt_tokens, turn, fetch=fetch_quotes,
                              require_fresh_openrouter=strict_quote)
        strict_quote_unavailable = (strict_quote and provider == "openrouter" and quote.usd is None
                                    and quote.source.startswith("openrouter_"))
        file_cost = (None if strict_quote_unavailable else
                     self.prices.estimate_run_ceiling(provider, model, self.prompt_tokens, turn, lim.max_steps))
        if local:
            kind = "local"
        elif provider in self.prices.flat_providers:
            kind = "flat"
        elif quote.usd is not None or file_cost is not None:
            kind = "priced"
        else:
            kind = "unpriced"
        if strict_quote_unavailable:
            worst = None
        elif quote.source == "openrouter" and quote.usd is not None:
            worst = quote.usd * lim.max_steps
        else:
            worst = file_cost if file_cost is not None else (quote.usd * lim.max_steps if quote.usd is not None else None)
        window, window_note = 0, "this runtime has not reported a window yet"
        if quote.source == "openrouter":
            try:
                from .providers import openrouter_pricing
                service = openrouter_pricing.live_pricing(quote_base_url(self.book, provider))
                live = service.quote(model)
                windows = [endpoint.context_length for endpoint in live.endpoints
                           if endpoint.context_length > 0 and endpoint.status == 0] if live else []
                if windows:
                    window = min(windows)
                    window_note = "smallest window across the admissible live endpoints"
                else:
                    window_note = "the live quote did not report a usable window"
            except Exception:
                pass
        elif local:
            window_note = "computed from the model and this machine when the run starts"
        measured_tokens, held_tokens, measured_cost, held_cost = self.store.bot_budget_today(self.bot.id)
        scope_measured = scope_held = 0.0
        if scope_kind:
            scope_measured, scope_held = self.store.scope_spend(scope_kind=scope_kind, scope_id=scope_id)
        return RunEstimate(spec=spec, kind=kind, prompt_tokens=self.prompt_tokens, steps=lim.max_steps, turn_tokens=turn,
                           worst_case_usd=worst if kind == "priced" else None, run_cap_usd=lim.max_cost_usd,
                           daily_cap_usd=lim.daily_cost_cap_usd, spent_today_usd=measured_cost,
                           tokens_today=measured_tokens, daily_token_cap=lim.daily_token_cap,
                           reserved_tokens_today=held_tokens, reserved_cost_today_usd=held_cost,
                           message_tokens=self.message_tokens, tool_tokens=self.tool_tokens,
                           next_call_usd=quote.usd, price_source=quote.source,
                           price_verified_on=quote.verified_on, price_stale=quote.stale,
                           price_snapshot_sha256=quote.snapshot_digest, price_expires_at=quote.expires_at,
                           price_endpoint_identities=quote.endpoint_identities,
                           currency=quote.currency, billing_unit=quote.billing_unit,
                           window_tokens=window, window_note=window_note,
                           budget_scope=scope_kind, budget_scope_id=scope_id,
                           warn_usd=(policy.warn_usd if policy else None),
                           pause_usd=(policy.pause_usd if policy else None),
                           ceiling_usd=(policy.ceiling_usd if policy else None),
                           budget_measured_usd=scope_measured, budget_held_usd=scope_held)


def quote_base_url(book: ConnectionBook, provider: str) -> str:
    conn = book.get(provider)
    from .providers import openrouter_pricing
    return (getattr(conn, "base_url", "") if conn is not None else "") or openrouter_pricing.DEFAULT_BASE_URL


def estimate_run(config: Any, store: Any, bot: Bot, prompt: str = "", model: Optional[str] = None,
                 conversation_id: str = "", fetch_quotes: bool = False,
                 conversation_context: Optional[list[dict[str, str]]] = None,
                 reply_to_message_id: Optional[str] = None,
                 workspace_task_result_id: Optional[str] = None,
                 workspace_task_result_message_id: Optional[str] = None,
                 skills: Optional[list[str]] = None, rehearse: bool = False) -> RunEstimate:
    if conversation_context is None and conversation_id:
        conversation_context = store.preview_conversation_context(
            conversation_id, reply_to_message_id=reply_to_message_id,
            workspace_task_result_id=workspace_task_result_id,
            workspace_task_result_message_id=workspace_task_result_message_id)
    if skills:
        from .skills import SkillRegistry
        SkillRegistry(config.state_dir).validate_activation(bot, skills)
    return RunEstimator(config, store, bot, prompt, conversation_context,
                        conversation_id=conversation_id, skills=skills, rehearse=rehearse).for_model(
                            model, conversation_id=conversation_id, fetch_quotes=fetch_quotes)
