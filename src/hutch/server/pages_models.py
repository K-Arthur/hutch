"""Models page (LM-5, LM-7, LM-14): what fits this machine, what each preset resolves to, runtime health, swap cost
and editable hosted prices. Registered from ``pages.py`` with the shared page helpers so look and behaviour match."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import routes
from ..modelview import build_models_view
from ..providers.base import ProviderError
from ..providers.model_install import ModelInstaller
from ..providers.pricing import PriceBook
from .security import check_csrf


def register_model_pages(app: FastAPI, page: Callable, go: Callable, read_form: Callable) -> None:
    config, store = app.state.config, app.state.store

    def require_csrf(request: Request) -> None:
        """These routes are called by script with the page's token in a header, like every other write from a server page."""
        if not check_csrf(request, request.headers.get("x-csrf-token")):
            raise HTTPException(403, "the page's security token did not match; reload the page and try again")

    def installer() -> ModelInstaller:
        """One installer per server process: it owns the bounded job registry."""
        existing = getattr(app.state, "model_installer", None)
        if existing is None:
            from ..runtime.ladder import get_provider
            existing = ModelInstaller(get_provider("ollama", None))
            app.state.model_installer = existing
        return existing

    def workspace_default() -> str:
        """The one parser for the route that seeds new built-in assistants (hutch.routes)."""
        return str(routes.workspace_default(store).get("model") or "")

    def workspace_mode() -> str:
        return str(routes.workspace_default(store).get("inference_mode") or "hybrid")

    @app.get("/models", response_class=HTMLResponse, include_in_schema=False)
    def models_page(request: Request):
        view = build_models_view(config, store)
        # Explicit readiness for the saved routes: local facts only, no inference and no token refresh.
        from ..connections import ConnectionBook
        from ..providers.readiness import route_readiness
        book = ConnectionBook(config.state_dir)
        readiness = [{"spec": row.spec, "status": row.status, "readiness": route_readiness(book, row.spec)}
                     for row in view.configured_routes]
        # Price errors belong beside the price form, not above the page head;
        # the template overrides the base flash and renders it inside #prices.
        return page(request, "models.html", nav="models", v=view, readiness=readiness,
                    authority=routes.authority(store, config))

    @app.get("/api/models/install")
    def model_install_list() -> dict:
        """Every install this process knows about, newest first."""
        return {"jobs": [job.to_json() for job in installer().jobs()]}

    @app.post("/api/models/install")
    async def model_install_start(request: Request) -> dict:
        """Begin downloading a model from the runtime's own registry.

        This is the only path that starts a download: selecting a model never does.
        """
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(422, "expected a JSON object with a 'model' field")
        require_csrf(request)
        try:
            job = installer().start(str(body.get("model") or ""),
                                    allow_existing=bool(body.get("reinstall")))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except ProviderError as exc:
            raise HTTPException(409, str(exc)) from None
        return job.to_json()

    @app.get("/api/models/install/{job_id}")
    def model_install_status(job_id: str) -> dict:
        job = installer().job(job_id)
        if job is None:
            raise HTTPException(404, "no install with that id (the server may have restarted)")
        return job.to_json()

    @app.delete("/api/models/install/{job_id}")
    def model_install_cancel(job_id: str, request: Request) -> dict:
        """Ask a running install to stop. Verified blobs are kept, so re-running resumes."""
        require_csrf(request)
        if not installer().cancel(job_id):
            raise HTTPException(404, "no running install with that id")
        return {"cancelling": job_id}

    @app.post("/api/models/remove")
    async def model_remove(request: Request) -> dict:
        """Delete a model from the runtime. A JSON body is used because model names contain ':' and '/'."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(422, "expected a JSON object with a 'model' field")
        require_csrf(request)
        try:
            return {"removed": installer().remove(str(body.get("model") or ""))}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except ProviderError as exc:
            raise HTTPException(404 if exc.kind == "model_missing" else 409, str(exc)) from None

    @app.post("/models/prices/save", include_in_schema=False)
    async def price_save(request: Request):
        f = await read_form(request)

        def num(key: str, required: bool = False):
            raw = (f.get(key) or "").strip()
            if not raw:
                if required:
                    raise ValueError(f"{key.replace('_', ' ')} is required")
                return None
            try:
                return float(raw)
            except ValueError:
                raise ValueError(f"{key.replace('_', ' ')} must be a number (USD per 1M tokens), got '{raw}'") from None

        try:
            model = (f.get("model") or "").strip()
            if not model:
                raise ValueError("model is required")
            book = PriceBook(config.state_dir / "prices.json")
            source = (f.get("source") or "").strip()
            p = book.set_price(model, num("input", True), num("output", True), num("cache_read"),
                               num("cache_write"), source=source)
        except ValueError as exc:
            return go("/models?price=1#prices", error=str(exc))
        return go("/models?price=1#prices", notice=f"Saved a price for {p.model}, stamped {p.verified_on}.")

    @app.post("/models/prices/reset", include_in_schema=False)
    async def price_reset(request: Request):
        f = await read_form(request)
        model = (f.get("model") or "").strip()
        if not model:
            return go("/models?price=1#prices", error="model is required")
        PriceBook(config.state_dir / "prices.json").remove_override(model)
        return go("/models?price=1#prices", notice=f"Your override for {model} was removed.")

    @app.post("/models/set-default", include_in_schema=False)
    async def model_set_default(request: Request):
        """Compatibility redirect: the default is written only in Settings (one writer, one record)."""
        await read_form(request)
        return go("/#/settings", notice="Set the default for new assistants in Settings, then save.")

    @app.post("/models/test", include_in_schema=False)
    async def model_test(request: Request):
        f = await read_form(request)
        model = (f.get("model") or "").strip()
        provider = (f.get("provider") or "").strip() or model.partition("/")[0]
        if not provider:
            return go("/models", error="Provider or model spec is required for testing.")
        from ..connections import ConnectionBook
        book = ConnectionBook(config.state_dir)
        if provider == "ollama":
            from ..runtime.ladder import get_provider
            p = get_provider("ollama", None)
            health = p.health()
            if health.ok:
                return go("/models", notice=f"Ollama connection verified: {health.detail or 'ready'}.")
            return go("/models", error=f"Ollama connection test failed: {health.detail}")
        if provider in book.names():
            from ..providers.connection import check_connection
            res = check_connection(book, provider)
            detail = (res.detail or "").strip()[:500]
            secret = book.key(provider) or ""
            if secret:
                detail = detail.replace(secret, "[redacted]")
            if res.ok:
                return go("/models", notice=f"{provider}: connection verified ({detail}).")
            return go("/models", error=f"{provider}: connection test failed ({detail}).")
        return go("/models", error=f"{provider} is not a configured connection, so Hutch cannot test it. Add the provider in Apps & AI first.")

    @app.post("/models/add", include_in_schema=False)
    async def model_add(request: Request):
        """Compatibility redirect: accounts, keys and endpoints are added in Apps & AI; this page never creates them."""
        await read_form(request)
        return go("/#/connections", notice="Add or repair an AI service in Apps & AI, then choose its route.")

    @app.post("/models/delete", include_in_schema=False)
    async def model_delete(request: Request):
        f = await read_form(request)
        model = (f.get("model") or "").strip()
        if not model:
            return go("/models", error="Model spec is required.")
        stored_routes = [s.strip() for s in (store.kv_get("configured_model_routes") or "").split(",") if s.strip()]
        was_stored = model in stored_routes
        cleared_default = workspace_default() == model
        changed = []
        for bot in store.list_bots():
            if bot.model == model:
                bot.model = ""
                store.upsert_bot(bot, preserve_schedules=True)
                changed.append(bot.name)
        if cleared_default:
            routes.clear_workspace_default(store)
        store.kv_set(f"model_label:{model}", "")
        if model in stored_routes:
            stored_routes.remove(model)
            store.kv_set("configured_model_routes", ",".join(stored_routes))
        PriceBook(config.state_dir / "prices.json").remove_override(model)
        if model.startswith("ollama/") and not (cleared_default or changed or was_stored):
            return go("/models", error=f"{model} is installed locally; Hutch does not uninstall model files. "
                                       f"Run `ollama rm {model.split('/', 1)[1]}` to delete it.")
        if changed or cleared_default or was_stored:
            note = f"Removed {model} from {len(changed)} bot(s), the default and saved routes."
        else:
            note = f"Removed the saved route {model}."
        if model.startswith("ollama/"):
            note += f" The installed model file is unchanged; run `ollama rm {model.split('/', 1)[1]}` to delete it."
        return go("/models", notice=note)
