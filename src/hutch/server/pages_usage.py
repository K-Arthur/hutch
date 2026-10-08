"""Usage page (UI-11): where tokens and money went, today against the caps, plan allowances, and every time a run moved
to another model. Spend opacity is the loudest complaint about the two products Hutch is measured against."""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from ..connections import ConnectionBook
from ..models import local_day_bounds

PERIODS = (7, 30, 90)


def register_usage_page(app: FastAPI, page: Callable) -> None:
    config, store = app.state.config, app.state.store

    @app.get("/usage", response_class=HTMLResponse, include_in_schema=False)
    def usage_page(request: Request, days: int = 30):
        days = days if days in PERIODS else 30
        book = ConnectionBook(config.state_dir)
        flat = book.flat_providers()
        bots = {b.id: b for b in store.list_bots()}
        by_day = store.usage_by_local_day(days)
        totals = {k: sum(d[k] for d in by_day) for k in ("calls", "prompt", "completion", "cached", "cost")}
        peak = max([d["prompt"] + d["completion"] for d in by_day] or [1]) or 1
        peak_cost = max([d["cost"] for d in by_day] or [1.0]) or 1.0
        by_model = store.usage_by("model", days)
        for r in by_model:
            provider = r["key"].partition("/")[0]
            r["billing"] = ("local" if provider in ("ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm", "mock")
                            else "flat plan" if provider in flat else "per token")
        by_bot = []
        for r in store.usage_by("bot", days):
            b = bots.get(r["key"])
            by_bot.append({**r, "name": b.name if b else "(deleted bot)"})
        caps = []
        for b in sorted(bots.values(), key=lambda x: x.name):
            lim = b.limits
            tokens = store.tokens_today(b.id)
            spent = store.cost_today(b.id)
            caps.append({"name": b.name, "tokens": tokens, "token_cap": lim.daily_token_cap,
                         "token_pct": min(100.0, tokens / lim.daily_token_cap * 100) if lim.daily_token_cap else 0.0,
                         "spent": spent, "cost_cap": lim.daily_cost_cap_usd,
                         "cost_pct": min(100.0, spent / lim.daily_cost_cap_usd * 100) if lim.daily_cost_cap_usd else 0.0})
        plans = []
        for name, c in book.configured().items():
            if c.quota.tokens:
                used = store.usage_tokens_since(name, c.quota.seconds)
                plans.append({"name": name, "title": c.title, "window": c.quota.window, "used": used, "cap": c.quota.tokens,
                              "pct": min(100.0, used / c.quota.tokens * 100)})
        today_start, _ = local_day_bounds()
        names = {b.id: b.name for b in bots.values()}
        changes = store.recent_rung_changes(25)
        for c in changes:
            run = store.get_run(c["run_id"])
            c["bot"] = names.get(run.bot_id, "?") if run else "?"
        return page(request, "usage.html", nav="usage", days=days, periods=PERIODS, by_day=by_day, totals=totals,
                    peak=peak, peak_cost=peak_cost, by_model=by_model, by_bot=by_bot, caps=caps, plans=plans,
                    changes=changes, today=by_day[0] if by_day and by_day[0]["day"] == today_start[:10] else None)
