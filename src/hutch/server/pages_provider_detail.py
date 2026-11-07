"""Provider detail page and its route-wizard actions.

``GET /providers/{id}`` shows one provider: its status, every route (auth method) with a step-by-step guide
derived from real account state, and the dated capability evidence. The four POST actions are the wizard's
forms: add an account from one of the provider's own templates, store a key, acknowledge terms, test the
connection. They call the same ConnectionBook operations as the legacy connections page, return to this page,
never echo a key, and refuse any account that does not belong to this provider.

Only custom-endpoint templates accept a base URL here; a vendor template keeps its own host, so a key
cannot be redirected by editing a form field.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from ..connections import ConnectionBook
from ..media.providers.route_spec import load_routes
from ..providers.accounts import BILLING_LABELS
from ..providers.capabilities import capability_report
from ..providers.catalog import STATUS_TEXT, Provider, bundled_catalog
from ..providers.catalog_view import (CATEGORY_LABELS, SERVICE_LABELS, capability_rows, resolution_view,
                                      route_chips, status_chip_class)
from ..providers.connection import check_connection
from ..providers.discovery import services_json
from ..providers.readiness import account_readiness
from ..providers.registry import validate_inference_mode
from ..providers.routing import resolve_route
from ..providers.wizard import Context, route_guides



def _is_local(provider: Provider) -> bool:
    """Only a provider with a local-service route needs the loopback probes; the others skip them."""
    return any(method.type == "local_service" for method in provider.auth_methods)


def _media_env(provider: Provider) -> str:
    """The environment variable a media-only vendor's key comes from, when it has no connection template."""
    if provider.connection_templates:
        return ""
    return next((route.env_var for route in load_routes().values()
                 if route.provider == provider.id and route.env_var), "")


#: Inference modes a route can be checked against, and how a person reads them.
MODES = (("hybrid", "Hybrid (default)"), ("local", "Local only"), ("offline", "Strict Offline"))


def _mode_verdict(mode: str, spec: str, endpoint: str) -> dict[str, Any]:
    """Whether the chosen inference mode would allow this route, in the policy's own words."""
    label = dict(MODES)[mode]
    try:
        validate_inference_mode(mode, spec, base_url=endpoint or None)
    except ValueError as exc:
        return {"mode": mode, "label": label, "allowed": False, "text": str(exc)}
    return {"mode": mode, "label": label, "allowed": True,
            "text": f"{label} allows this route: its endpoint and model are on this computer."}


def _picker(provider: Provider, current: ConnectionBook, runtimes: list[dict], local: Callable[[], dict],
            account: str, model: str, runtime: str, mode: str = "hybrid") -> dict[str, Any]:
    """The route picker: choices from local facts, and the resolution when a model was entered.

    The prefix is the connection name (or the provider id for a built-in route); the resolver reports who pays,
    and never substitutes a different account, model or runtime."""
    accounts = sorted(name for name, conn in current.configured().items()
                      if conn.template in provider.connection_templates)
    prefixes = [provider.id, *accounts]
    usable = [item for item in runtimes if item.get("enabled")] or [{"id": "builtin", "title": "Hutch built-in runtime"}]
    chosen = account if account in prefixes else prefixes[0]
    picked = runtime if runtime in {item["id"] for item in usable} else usable[0]["id"]
    model = model.strip()
    mode = mode if mode in dict(MODES) else "hybrid"
    resolution = None
    if model:
        resolved = resolve_route(current, f"{chosen}/{model}", runtime=picked,
                                 local_services=local() if _is_local(provider) else None)
        resolution = resolution_view(resolved.json())
        if mode != "hybrid":
            resolution["mode"] = _mode_verdict(mode, resolved.spec, resolved.endpoint)
            if not resolution["mode"]["allowed"]:   # the readiness hint would say to run a route this mode refuses
                resolution["next_action"] = "Choose a local model route, or switch the inference mode to Hybrid."
    return {"prefixes": prefixes, "accounts": accounts, "runtimes": usable, "account": chosen,
            "model": model, "runtime": picked, "mode": mode, "modes": MODES, "resolution": resolution}


def register_provider_detail(app: FastAPI, page: Callable, go: Callable, read_form: Callable, *,
                             local_services: Callable[[], dict], runtime_catalog: Callable[[], dict]) -> None:
    config, store = app.state.config, app.state.store

    def book() -> ConnectionBook:
        return ConnectionBook(config.state_dir)

    def provider_or_404(provider_id: str) -> Provider:
        provider = bundled_catalog().get(provider_id)
        if provider is None:
            raise HTTPException(404, f"No provider named '{provider_id}'.")
        return provider

    def owned(provider: Provider, name: str) -> ConnectionBook:
        """The book, after proving that account ``name`` was made from one of this provider's templates."""
        current = book()
        conn = current.get(name)
        if conn is None or conn.template not in provider.connection_templates:
            raise HTTPException(404, f"No account named '{name}' for {provider.title}.")
        return current

    def back(provider: Provider, route: str, account: str = "") -> str:
        known = {method.id for method in provider.auth_methods}
        query = f"?account={account}" if account else ""
        return f"/providers/{provider.id}{query}" + (f"#route-{route}" if route in known else "")

    # ------------------------------------------------------------------ page

    @app.get("/providers/{provider_id}", response_class=HTMLResponse, include_in_schema=False)
    def provider_detail(request: Request, provider_id: str,
                        account: str = Query(default="", max_length=41),   # an unknown account is ignored, not trusted
                        pick_account: str = Query(default="", max_length=41),
                        pick_model: str = Query(default="", max_length=200),
                        pick_runtime: str = Query(default="", max_length=41),
                        pick_mode: str = Query(default="", max_length=20)):
        provider, catalog = provider_or_404(provider_id), bundled_catalog()
        current = book()
        guides = route_guides(Context(
            provider=provider, book=current, store=store, templates=current.templates(),
            local_services=tuple(services_json(local_services())) if _is_local(provider) else (),
            runtimes=tuple(runtime_catalog().get("runtimes", [])), media_env=_media_env(provider), focus=account))
        readiness = {name: account_readiness(current, name, catalog=catalog)
                     for guide in guides for name in guide.accounts}
        label, meaning = STATUS_TEXT.get(provider.integration_status, (provider.integration_status, ""))
        return page(request, "provider.html", nav="connections", provider=provider, guides=guides,
                    readiness=readiness, status_label=label, status_meaning=meaning,
                    chip_class=status_chip_class(provider.integration_status),
                    category_label=CATEGORY_LABELS.get(provider.category, provider.category),
                    routes_by_id={chip["id"]: chip for chip in route_chips(provider)},
                    service_labels=SERVICE_LABELS, billing_labels=BILLING_LABELS,
                    capabilities=capability_rows(capability_report(provider.id, store=store)),
                    picker=_picker(provider, current, list(runtime_catalog().get("runtimes", [])), local_services,
                                   pick_account, pick_model, pick_runtime, pick_mode),
                    reviewed_on=catalog.reviewed_on)

    # --------------------------------------------------------------- actions

    @app.post("/providers/{provider_id}/connect", include_in_schema=False)
    async def wizard_connect(request: Request, provider_id: str):
        provider, form = provider_or_404(provider_id), await read_form(request)
        route, template = form.get("route"), form.get("template")
        if template not in provider.connection_templates:
            return go(back(provider, route), error=f"{template or 'That'} is not an account type for {provider.title}.")
        current = book()
        offered = current.templates().get(template)
        if offered is None or offered.get("auth_method", "api_key") not in ("api_key", "custom_endpoint"):
            return go(back(provider, route),
                      error=f"{template} is a sign-in account. Start it from Apps & AI, which owns the sign-in.")
        try:
            overrides: dict[str, Any] = {}
            if offered.get("auth_method") == "custom_endpoint":
                overrides["base_url"] = form.get("base_url").strip() or None
            conn = current.add(template, form.get("name").strip() or None, **overrides)
        except ValueError as exc:
            return go(back(provider, route), error=str(exc))
        return go(back(provider, route, conn.name), notice=f"Added {conn.name}. Next, store its key.")

    @app.post("/providers/{provider_id}/accounts/{name}/key", include_in_schema=False)
    async def wizard_key(request: Request, provider_id: str, name: str):
        provider, form = provider_or_404(provider_id), await read_form(request)
        current, route = owned(provider, name), form.get("route")
        key = form.get("key").strip()
        if not key:
            return go(back(provider, route, name), error="That key was empty.")
        try:
            current.set_key(name, key)       # written to a 0600 file; never echoed, logged or stored in the database
        except ValueError as exc:
            return go(back(provider, route, name), error=str(exc))
        return go(back(provider, route, name), notice=f"Key stored for {name}.")

    @app.post("/providers/{provider_id}/accounts/{name}/ack", include_in_schema=False)
    async def wizard_ack(request: Request, provider_id: str, name: str):
        provider, form = provider_or_404(provider_id), await read_form(request)
        current, route = owned(provider, name), form.get("route")
        if not form.flag("agree"):
            return go(back(provider, route, name), error="Tick the box to confirm you read the terms.")
        current.acknowledge(store, name)
        return go(back(provider, route, name), notice=f"Terms acknowledged for {name}.")

    @app.post("/providers/{provider_id}/accounts/{name}/test", include_in_schema=False)
    async def wizard_test(request: Request, provider_id: str, name: str):
        provider, form = provider_or_404(provider_id), await read_form(request)
        current, route = owned(provider, name), form.get("route")
        result = await run_in_threadpool(check_connection, current, name)   # a network read: keep it off the event loop
        message = {"notice": f"{name}: {result.detail}"} if result.ok else {"error": f"{name}: {result.detail}"}
        return go(back(provider, route, name), **message)
