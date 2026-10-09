"""Account-scoped permission for ChatGPT plan use by unattended Hutch runs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Bot, Run

CHATGPT_TERMS_REVISION = "2026-09-29"
BACKGROUND_ORIGINS = frozenset({"schedule", "workspace_task", "plan"})


def is_background_run(run: Run) -> bool:
    """Scheduled and coordinated specialist work can run without a live user turn."""
    return (run.origin in BACKGROUND_ORIGINS or bool(run.schedule_id) or
            run.parent_run_id is not None)


def bot_route_specs(bot: Bot) -> list[str]:
    """The persisted order and role of every route that a background run can reach."""
    specs = [bot.model] if bot.model else []
    specs.extend(bot.fallbacks)
    if bot.escalation:
        specs.extend(bot.escalation.to)
    return specs


def background_route_fingerprint(bot: Bot) -> str:
    payload = {
        "model": bot.model,
        "base_url": bot.base_url or "",
        "fallbacks": list(bot.fallbacks),
        "escalation": list(bot.escalation.to) if bot.escalation else [],
        "inference_mode": bot.inference_mode.value,
        "runtime": bot.runtime.value,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def bot_route_provider_names(bot: Bot) -> set[str]:
    return {spec.split("/", 1)[0] for spec in bot_route_specs(bot) if "/" in spec}


def has_background_provider_consent(bot: Bot, provider: str, account_id: str) -> bool:
    fingerprint = background_route_fingerprint(bot)
    return any(
        consent.provider == provider and consent.account_id == account_id and
        consent.route_fingerprint == fingerprint and consent.terms_revision == CHATGPT_TERMS_REVISION
        for consent in bot.background_provider_consents
    )


def chatgpt_background_view(bot: Bot, connections: Any) -> list[dict[str, str]]:
    """Safe, typed-to-JSON view; local account identifiers stay out of Bot API responses."""
    fingerprint = background_route_fingerprint(bot)
    route_names = bot_route_provider_names(bot)
    rows: list[dict[str, str]] = []
    for name in sorted(route_names):
        connection = connections.get(name)
        if connection is None or connection.auth_type != "chatgpt-siws":
            continue
        if not connections.has_key(name):
            state = "sign_in_required"
        elif has_background_provider_consent(bot, name, connection.auth_account_id):
            state = "allowed"
        else:
            state = "needs_consent"
        rows.append({"provider": name, "title": connection.title, "state": state,
                     "route_fingerprint": fingerprint})
    return rows
