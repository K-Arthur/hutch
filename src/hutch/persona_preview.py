"""Isolated, explicitly requested one-response samples of an adaptive persona."""

from __future__ import annotations

from typing import Any

from .connections import ConnectionBook
from .persona import PersonaPlan, guidance
from .providers.pricing import PriceBook
from .providers.registry import parse_spec

PREVIEW_PROMPT = "Give me a funny, low-effort way to make peace with my houseplants after their tiny protest."
PREVIEW_MAX_INPUT_TOKENS = 1_024
PREVIEW_MAX_OUTPUT_TOKENS = 128

PREVIEW_SYSTEM = (
    "You are answering a fixed, fictional sample request so the operator can preview response style. "
    "Use only the sample in this request. This is an isolated preview, not a real conversation: do not infer or "
    "ask for personal context, claim to have taken an action, or add unrelated details. Keep the reply compact."
)


def preview_messages(plan: PersonaPlan) -> list[dict[str, str]]:
    """A preview contains only Hutch's fixed sample, its neutral system instruction, and the candidate style."""
    return [
        {"role": "system", "content": PREVIEW_SYSTEM + "\n\n" + guidance(plan)},
        {"role": "user", "content": PREVIEW_PROMPT},
    ]


def preview_budget(config: Any, store: Any, bot: Any) -> dict[str, Any]:
    """Return a conservative one-call estimate without contacting the model provider."""
    from .models import RuntimeKind

    output_cap = min(bot.limits.max_turn_tokens, PREVIEW_MAX_OUTPUT_TOKENS) if bot.limits.max_turn_tokens else PREVIEW_MAX_OUTPUT_TOKENS
    result: dict[str, Any] = {
        "available": False,
        "reason": "",
        "model": bot.model,
        "profile_revision": bot.persona_revision,
        "max_model_requests": 1,
        "max_input_tokens": PREVIEW_MAX_INPUT_TOKENS,
        "max_output_tokens": output_cap,
        "estimated_max_cost_usd": None,
        "budget_kind": "unavailable",
        "budget_label": "",
        "estimate_note": "The local estimate may differ from provider tokenization and billing.",
    }
    if bot.persona_profile_error:
        result["reason"] = bot.persona_profile_error
        return result
    if bot.runtime is not RuntimeKind.builtin:
        result["reason"] = "Live style preview is available only for the built-in runtime."
        return result
    if bot.limits.max_steps <= 0:
        result["reason"] = "This assistant's step limit does not allow a preview response."
        return result

    try:
        provider, model = parse_spec(bot.model)
    except ValueError as exc:
        result["reason"] = f"The configured model cannot be priced for a live preview: {exc}"
        return result
    connections = ConnectionBook(config.state_dir)
    connection = connections.get(provider)
    if connection is not None and connection.auth_type == "chatgpt-siws":
        result["reason"] = (
            "This ChatGPT connection does not let Hutch enforce an output-token cap, so live preview is unavailable. "
            "The written examples remain available without a model request."
        )
        return result

    prices = PriceBook(config.state_dir / "prices.json")
    prices.flat_providers = connections.flat_providers()
    local = prices.is_local(provider, model)
    flat = provider in prices.flat_providers
    if not prices.has_price(provider, model):
        result["reason"] = (
            f"Hutch has no current price for {bot.model}, so it cannot show a cost estimate before this hosted preview. "
            "Add a model price or choose a priced/local model."
        )
        return result

    ceiling = prices.cost(provider, model, PREVIEW_MAX_INPUT_TOKENS, output_cap)
    result["estimated_max_cost_usd"] = ceiling
    if local:
        result["budget_kind"] = "local"
        result["budget_label"] = (f"One response, up to {output_cap} output tokens. "
                                   "This local model has no per-token Hutch charge.")
    elif flat:
        result["budget_kind"] = "flat"
        result["budget_label"] = (
            f"One response, up to {output_cap} output tokens. Hutch lists no per-token price for this connection; its provider "
            "allowance may still count."
        )
    else:
        result["budget_kind"] = "priced"
        result["budget_label"] = (
            f"One response, up to {output_cap} output tokens. Hutch estimates up to ${ceiling:.6f} for this call; "
            "actual provider billing can differ."
        )

    if bot.limits.max_cost_usd and ceiling is not None and ceiling > bot.limits.max_cost_usd:
        result["reason"] = "The estimate exceeds this assistant's per-run cost limit."
        return result
    if bot.limits.daily_cost_cap_usd and ceiling is not None:
        _, _, measured_cost, reserved_cost = store.bot_budget_today(bot.id)
        if measured_cost + reserved_cost + ceiling > bot.limits.daily_cost_cap_usd:
            result["reason"] = "The estimate exceeds the remaining daily cost limit for this assistant."
            return result
    if bot.limits.daily_token_cap:
        measured_tokens, reserved_tokens, _, _ = store.bot_budget_today(bot.id)
        if measured_tokens + reserved_tokens + PREVIEW_MAX_INPUT_TOKENS + output_cap > bot.limits.daily_token_cap:
            result["reason"] = "The one-response estimate exceeds the remaining daily token limit for this assistant."
            return result

    result["available"] = True
    return result
