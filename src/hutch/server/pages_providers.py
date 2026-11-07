"""Provider catalogue, account, capability and runtime surfaces.

Read-only except for two account maintenance actions (rename, remove the local key). These routes never
call a provider, never return a credential value, and never change a model selection. The provider page
is server-rendered; the JSON endpoints expose the same records for the dashboard.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from ..connections import ConnectionBook
from ..providers.accounts import disconnect_local, provider_groups, rename_account
from ..providers.capabilities import (CAPABILITIES, capability_matrix, capability_report, live_summary,
                                      report_json)
from ..providers.catalog import CATEGORIES, INTEGRATION_STATUSES, STATUS_TEXT, bundled_catalog
from ..providers.catalog_view import CATEGORY_LABELS, catalog_facets, catalog_rows, distinct_next_action
from ..providers.discovery import probe_local_services, services_json
from ..providers.readiness import account_readiness, provider_readiness, readiness_json, route_readiness
from ..providers.routing import resolve_route
from ..runtime.registry import registry_json

_RUNTIME_CACHE_SECONDS = 60.0
_runtime_cache: dict[str, Any] = {"at": 0.0, "value": None}


def _status_counts(catalog) -> list[dict]:
    """Catalogue entries per integration status, in the declared vocabulary order."""
    return [
        {"status": status, "label": STATUS_TEXT.get(status, (status, ""))[0],
         "count": sum(1 for provider in catalog.providers if provider.integration_status == status)}
        for status in INTEGRATION_STATUSES
        if any(provider.integration_status == status for provider in catalog.providers)
    ]


def runtime_catalog() -> dict:
    """Runtime descriptors plus installed-CLI detection, cached briefly (detection shells out)."""
    now = time.monotonic()
    if _runtime_cache["value"] is None or now - _runtime_cache["at"] > _RUNTIME_CACHE_SECONDS:
        _runtime_cache["value"] = registry_json(detect=True)
        _runtime_cache["at"] = now
    return _runtime_cache["value"]


def _provider_json(provider) -> dict:
    return {
        "id": provider.id, "title": provider.title, "category": provider.category,
        "summary": provider.summary, "services": list(provider.services),
        "protocols": list(provider.protocols), "integration_status": provider.integration_status,
        "connection_templates": list(provider.connection_templates), "regions": list(provider.regions),
        "notes": provider.notes,
        "auth_methods": [
            {"id": method.id, "type": method.type, "label": method.label, "billing": method.billing,
             "status": method.status, "notes": method.notes,
             "docs": [{"title": doc.title, "url": doc.url, "observed_on": doc.observed_on}
                      for doc in method.docs]}
            for method in provider.auth_methods
        ],
        "docs": [{"title": doc.title, "url": doc.url, "observed_on": doc.observed_on} for doc in provider.docs],
    }


def _profile_json(profile) -> dict:
    return {
        "name": profile.name, "title": profile.title, "provider": profile.provider_id,
        "provider_title": profile.provider_title, "provider_category": profile.provider_category,
        "provider_status": profile.provider_status, "auth_method": profile.auth_method,
        "auth_label": profile.auth_label, "billing": profile.billing, "billing_label": profile.billing_label,
        "credential": profile.credential, "credential_source": profile.credential_source,
        "credential_state": profile.credential_state,
        "credential_expires_at": profile.credential_expires_at,
        "endpoint": profile.endpoint, "protocol": profile.protocol, "status": profile.status,
        "detail": profile.detail,
    }


def _account_sections(book: ConnectionBook, catalog) -> tuple[list[dict], dict[str, int]]:
    """Accounts grouped by provider with readiness, and the account count per provider id."""
    sections, counts = [], {}
    for group in provider_groups(book):
        rows = []
        for profile in group.accounts:
            readiness = account_readiness(book, profile.name, catalog=catalog)
            rows.append({"profile": profile, "readiness": readiness,
                         "next_action": distinct_next_action(readiness.detail, readiness.next_action)})
        counts[group.provider_id] = len(rows)
        sections.append({"provider_id": group.provider_id, "provider": group.provider, "accounts": rows})
    return sections, counts


def register_provider_pages(app: FastAPI, page: Callable, go: Callable, read_form: Callable) -> None:
    config, store = app.state.config, app.state.store

    def book() -> ConnectionBook:
        return ConnectionBook(config.state_dir)

    def local_services() -> dict:
        try:
            from ..providers.local.credentials import runtime_credentials
            return probe_local_services(credential_for=runtime_credentials(config.state_dir))
        except Exception:  # noqa: BLE001 - discovery must never break a page
            return {}

    # ------------------------------------------------------------------ page

    @app.get("/providers", response_class=HTMLResponse, include_in_schema=False)
    def providers_page(request: Request):
        catalog = bundled_catalog()
        current = book()
        accounts, counts = _account_sections(current, catalog)
        rows = catalog_rows(catalog, counts)
        ecosystem = [{"category": category, "label": CATEGORY_LABELS.get(category, category),
                      "rows": [row for row in rows if row["category"] == category]} for category in CATEGORIES]
        return page(request, "providers.html", nav="connections", groups=accounts,
                    ecosystem=[section for section in ecosystem if section["rows"]],
                    facets=catalog_facets(catalog), reviewed_on=catalog.reviewed_on,
                    provider_count=len(catalog.providers), live_summary=live_summary(),
                    status_counts=_status_counts(catalog), local_services=services_json(local_services()),
                    runtime_catalog=runtime_catalog())

    # ------------------------------------------------------------------- APIs

    @app.get("/api/v1/providers")
    def providers_api() -> dict:
        catalog = bundled_catalog()
        current = book()
        accounts = provider_groups(current)
        counts: dict[str, int] = {}
        for group in accounts:
            counts[group.provider_id] = len(group.accounts)
        return {
            "reviewed_on": catalog.reviewed_on,
            "categories": [{"id": category, "label": CATEGORY_LABELS.get(category, category)} for category in CATEGORIES],
            "providers": [dict(_provider_json(provider), account_count=counts.get(provider.id, 0))
                          for provider in catalog.providers],
        }

    @app.get("/api/v1/provider-accounts")
    def provider_accounts_api() -> dict:
        catalog = bundled_catalog()
        current = book()
        groups = provider_groups(current)
        return {
            "provider_count": len({group.provider_id for group in groups}),
            "groups": [
                {
                    "provider": _provider_json(group.provider) if group.provider else None,
                    "provider_id": group.provider_id,
                    "provider_title": group.provider.title if group.provider else group.provider_id,
                    "accounts": [
                        {"profile": _profile_json(profile),
                         "readiness": readiness_json(account_readiness(current, profile.name, catalog=catalog))}
                        for profile in group.accounts
                    ],
                }
                for group in groups
            ],
        }

    @app.get("/api/v1/provider-capabilities")
    def provider_capabilities_api(provider: Optional[str] = Query(default=None, max_length=41),
                                  model: str = Query(default="", max_length=200)) -> dict:
        if provider:
            try:
                report = capability_report(provider, model=model, store=store)
            except Exception as exc:  # noqa: BLE001 - unknown provider is a client error
                raise HTTPException(404, "Unknown provider") from exc
            return {"capabilities": CAPABILITIES, "report": report_json(report)}
        return {"capabilities": CAPABILITIES,
                "reports": [report_json(report) for report in capability_matrix(store=store)]}

    @app.get("/api/v1/provider-readiness")
    def provider_readiness_api(spec: Optional[str] = Query(default=None, max_length=300)) -> dict:
        catalog = bundled_catalog()
        current = book()
        if spec is not None:
            readiness = route_readiness(current, spec, catalog=catalog, local_services=local_services())
            return {"readiness": readiness_json(readiness)}
        return {"providers": [provider_readiness(current, provider.id, catalog=catalog)
                              for provider in catalog.providers],
                "local_services": services_json(local_services())}

    @app.get("/api/v1/provider-resolution")
    def provider_resolution_api(spec: str = Query(default="", max_length=300),
                                runtime: str = Query(default="builtin", max_length=40)):
        return {"resolution": resolve_route(book(), spec, runtime=runtime,
                                            local_services=local_services()).json()}

    @app.get("/api/v1/runtime-catalog")
    def runtime_catalog_api() -> dict:
        return runtime_catalog()

    # ------------------------------------------------------- account actions

    @app.post("/providers/account/{name}/rename", include_in_schema=False)
    async def rename_provider_account(request: Request, name: str):
        form = await read_form(request)
        try:
            rename_account(book(), name, form.get("title", ""))
        except KeyError:
            return go("/providers", error="No account named " + name + ".")
        except ValueError as exc:
            return go("/providers", error=str(exc))
        return go("/providers", notice="Renamed the account label. The connection name used in model specs is unchanged.")

    @app.post("/providers/account/{name}/disconnect", include_in_schema=False)
    async def disconnect_provider_account(request: Request, name: str):
        await read_form(request)
        try:
            result = disconnect_local(book(), name)
        except KeyError:
            return go("/providers", error="No account named " + name + ".")
        return go("/providers", notice=result["detail"])
