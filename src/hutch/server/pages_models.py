"""Models page (LM-5, LM-7, LM-14): what fits this machine, what each preset resolves to, runtime health, swap cost
and editable hosted prices. Registered from ``pages.py`` with the shared page helpers so look and behaviour match."""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from ..modelview import build_models_view
from ..providers.pricing import PriceBook


def register_model_pages(app: FastAPI, page: Callable, go: Callable, read_form: Callable) -> None:
    config, store = app.state.config, app.state.store

    @app.get("/models", response_class=HTMLResponse, include_in_schema=False)
    def models_page(request: Request):
        view = build_models_view(config, store)
        return page(request, "models.html", nav="models", v=view)

    @app.post("/models/prices/save", include_in_schema=False)
    async def price_save(request: Request):
        f = await read_form(request)

        def num(key: str, required: bool = False):
            raw = f.get(key).strip()
            if not raw:
                if required:
                    raise ValueError(f"{key.replace('_', ' ')} is required")
                return None
            try:
                return float(raw)
            except ValueError:
                raise ValueError(f"{key.replace('_', ' ')} must be a number (USD per 1M tokens), got '{raw}'") from None

        try:
            book = PriceBook(config.state_dir / "prices.json")
            p = book.set_price(f.get("model").strip(), num("input", True), num("output", True), num("cache_read"),
                               num("cache_write"), source=f.get("source"))
        except ValueError as exc:
            return go("/models#prices", error=str(exc))
        return go("/models#prices", notice=f"Saved a price for {p.model}, stamped {p.verified_on}.")

    @app.post("/models/prices/reset", include_in_schema=False)
    async def price_reset(request: Request):
        f = await read_form(request)
        model = f.get("model").strip()
        PriceBook(config.state_dir / "prices.json").remove_override(model)
        return go("/models#prices", notice=f"Your override for {model} was removed.")
