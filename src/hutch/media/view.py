"""View models for the Media, speech and search section of the Providers page.

Everything is read from data that already exists: the media route table, the dated price rows, the job
ledger and the connection templates' declared search routes. Nothing is hand-typed, so the page cannot say
that a route works, has a price or is built when the data does not. A cost is a dated estimate with its
basis or the words "cost unknown", never an invented number.
"""

from __future__ import annotations

from typing import Any

from ..connections import load_templates
from ..providers.catalog import STATUS_TEXT, ProviderCatalog, provider_for_template
from ..providers.catalog_view import status_chip_class
from .cost import load_prices
from .ledger import list_jobs
from .providers.route_spec import MediaRoute, load_routes

#: service status -> (label, chip class, what it means for the person). Covers every value
#: ``media.status.service_status`` can return; a test fails if one is added without wording.
JOB_STATUS: dict[str, tuple[str, str, str]] = {
    "submitting": ("sending", "st-waiting_approval",
                   "Not yet accepted by the provider. Check it to see whether it was received."),
    "running": ("running", "st-waiting_approval", "The provider accepted it and is working. Check it for progress."),
    "succeeded": ("finished", "st-succeeded", "The result is stored and verified by its checksum."),
    "failed": ("failed", "st-failed", "It failed. The reason is shown; a provider may still have billed for it."),
    "cancelled": ("cancelled", "st-stopped", "Cancelled and confirmed."),
    "refused": ("refused", "st-failed",
                "The provider declined this request under its content policy. Retrying the same prompt will not help."),
    "cancel_unconfirmed": ("cancel not confirmed", "st-failed",
                           "Cancel was requested but the provider never confirmed it. The job may still run and bill."),
}
_OPEN = ("submitting", "running")


def price_text(price_key: str) -> str:
    """A dated estimate with its basis, or "cost unknown". Never a number the data does not hold."""
    row = load_prices().get(price_key or "")
    if row is None or row.get("basis") == "unpriced":
        return "cost unknown: no price is recorded for this route"
    unit = {"per_item": f"per {row.get('unit', 'item')}", "per_audio_second": "per audio second",
            "per_video_second": "per video second"}.get(row["basis"], "")
    usd = row.get("usd", row.get("usd_per_second"))
    return f"about ${usd} {unit} (read {row.get('read', 'undated')})".replace("  ", " ")


def _credential_text(route: MediaRoute) -> str:
    parts = []
    if route.templates:
        parts.append("a named connection from the " + ", ".join(route.templates) + " template")
    if route.env_var:
        parts.append(f"the environment variable {route.env_var} (ambient: the approval names it)")
    return " or ".join(parts) or "none needed"


def route_rows() -> list[dict[str, Any]]:
    rows = []
    for route in load_routes().values():
        label, meaning = STATUS_TEXT.get(route.status, (route.status, ""))
        rows.append({
            "id": route.id, "title": route.title, "provider": route.provider, "kind": route.kind,
            "protocol": route.protocol, "status": route.status, "status_label": label,
            "status_meaning": meaning, "chip_class": status_chip_class(route.status),
            "model": route.model, "credential": _credential_text(route), "price_key": route.price,
            "price": price_text(route.price), "notes": route.notes, "retired_on": route.retired_on,
            "source": next((item.get("url", "") for item in route.sources if str(item.get("url", "")).startswith("https://")), ""),
        })
    return rows


def _stamp(value: Any) -> str:
    """"2026-11-07T02:27:06.925178+00:00" as "2026-11-07 02:27 UTC": the minute is enough to tell jobs apart."""
    text = str(value or "")
    return text[:16].replace("T", " ") + " UTC" if len(text) >= 16 else text


def job_rows(store: Any, *, finished: bool) -> list[dict[str, Any]]:
    """Jobs newest first. Only a job still open (sending or running) offers an action."""
    rows = []
    for job in list_jobs(store, open_only=not finished, limit=50):
        label, chip, meaning = JOB_STATUS.get(job["status"], (job["status"], "st-stopped", ""))
        rows.append(dict(job, status_label=label, chip_class=chip, meaning=meaning,
                         can_act=job["status"] in _OPEN, started=_stamp(job.get("created_at"))))
    return rows


def search_rows(catalog: ProviderCatalog) -> list[dict[str, str]]:
    """Providers that have a built provider-native search route: one declared in a connection template."""
    rows = []
    for template_id, template in sorted(load_templates().items()):
        if not template.get("search"):
            continue
        provider = provider_for_template(template_id)
        if provider is None:
            continue
        label = STATUS_TEXT.get(provider.integration_status, (provider.integration_status, ""))[0]
        rows.append({"template": template_id, "title": template.get("title", template_id), "provider": provider.id,
                     "provider_title": provider.title, "status": provider.integration_status,
                     "status_label": label, "chip_class": status_chip_class(provider.integration_status)})
    return rows


def media_context(store: Any, catalog: ProviderCatalog, *, finished: bool) -> dict[str, Any]:
    routes, searches = route_rows(), search_rows(catalog)
    built = {row["provider"] for row in searches}
    unbuilt_search = [provider.title for provider in catalog.providers
                      if {"search", "grounding"} & set(provider.services) and provider.id not in built]
    return {"routes": routes, "jobs": job_rows(store, finished=finished), "searches": searches,
            "unbuilt_search": unbuilt_search,
            "finished": finished, "built": sum(1 for row in routes if row["status"] == "implemented-unverified"),
            "unbuilt": sum(1 for row in routes if row["status"] == "documented"),
            "retired": sum(1 for row in routes if row["status"] in ("retired", "blocked"))}
