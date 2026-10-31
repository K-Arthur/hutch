"""Catalog API: the bundled agent store, reviewed export/import, and explicit catalog sources.

Owner configuration only (paired phones are refused by the default-deny inventory). Everything here is
read-only over the bundled manifests until a person acts: an export runs the sharing checklist and returns
a draft, an import returns the unsaved values the setup page reviews, and a source is only fetched when the
person asks and its entries stay inert until their exact content hash is trusted. No route creates an
assistant; creation goes through the normal reviewed setup action.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import catalog_export, catalog_sources
from ..catalog import CatalogError, bundled, content_hash, parse_manifest


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportRequest(_Strict):
    bot: str = Field(min_length=1, max_length=41)
    publisher: str = Field(default=catalog_export.PUBLISHER_DEFAULT, max_length=60)
    version: str = Field(default="1.0.0", max_length=20)
    category: str = Field(default=catalog_export.CATEGORY_DEFAULT, max_length=40)
    tagline: str = Field(default="", max_length=140)


class ImportRequest(_Strict):
    manifest: dict[str, Any]


class SourceRequest(_Strict):
    kind: Literal["local", "url"]
    location: str = Field(min_length=1, max_length=4096)
    expected_revision: int = Field(default=0, ge=0)


class SourceRevision(_Strict):
    expected_revision: int = Field(ge=0)


class SourceEnabled(SourceRevision):
    enabled: bool


class TrustRequest(SourceRevision):
    expected_hash: str = Field(min_length=64, max_length=64)


def install_catalog_routes(app: FastAPI, store, config) -> None:
    from .bot_deletion_api import require_local_owner

    state_dir = config.state_dir

    def source_summary(source: catalog_sources.CatalogSource) -> dict:
        return {"id": source.id, "kind": source.kind, "location": source.location,
                "enabled": source.enabled, "last_fetched_at": source.last_fetched_at,
                "last_error": source.last_error,
                "entries": [{"id": entry_id, "version": pin.version,
                             "trusted": bool(pin.trusted_hash), "changed": pin.changed,
                             "trusted_at": pin.trusted_at}
                            for entry_id, pin in sorted(source.pinned.items())]}

    def sources_payload(document: catalog_sources.SourcesDocument, problem: str | None = None) -> dict:
        return {"revision": document.revision, "sources": [source_summary(source) for source in document.sources],
                "diagnostics": [problem] if problem else [],
                "limits": {"max_sources": catalog_sources.MAX_SOURCES}}

    def fail(exc: Exception) -> HTTPException:
        return HTTPException(422, str(exc))

    @app.get("/api/v1/catalog")
    def catalog_index() -> dict:
        loaded = bundled()
        entries = []
        for item in loaded.entries:
            manifest = item.entry.model_dump(mode="json")
            entries.append({"id": item.entry.id, "name": item.entry.name, "version": item.entry.version,
                            "publisher": item.entry.publisher, "category": item.entry.category,
                            "tagline": item.entry.tagline, "order": item.entry.order,
                            "content_hash": item.content_hash, "manifest": manifest,
                            "permissions": catalog_export.permissions_from_manifest(manifest)})
        sources, problem = catalog_sources.load_sources(state_dir)
        return {"bundled": {"entries": entries, "diagnostics": loaded.diagnostics},
                "sources": sources_payload(sources, problem),
                "notes": ["Nothing is installed until you review a copy in setup.",
                          "Source entries stay inert until their exact content hash is trusted."]}

    @app.post("/api/v1/catalog/export-draft")
    def export_draft(body: ExportRequest) -> dict:
        """Run the sharing checklist over one saved assistant. Writes and sends nothing."""
        bot = store.get_bot(body.bot)
        if bot is None:
            raise HTTPException(404, f"no such bot: {body.bot}")
        try:
            review = catalog_export.review_export(bot, publisher=body.publisher, version=body.version,
                                                 category=body.category, tagline=body.tagline)
        except CatalogError as exc:
            raise fail(exc) from None
        payload = review.payload()
        payload["bot"] = bot.name
        return payload

    @app.post("/api/v1/catalog/import-draft")
    def import_draft(body: ImportRequest) -> dict:
        """Validate a catalog manifest and return the unsaved values the setup review pre-fills."""
        try:
            entry = parse_manifest(body.manifest)
            configuration = catalog_export.configuration_from_manifest(body.manifest)
        except CatalogError as exc:
            raise fail(exc) from None
        return {"configuration": configuration, "saved": False,
                "entry": {"id": entry.id, "name": entry.name, "version": entry.version,
                          "publisher": entry.publisher, "content_hash": content_hash(body.manifest)},
                "permissions": catalog_export.permissions_from_manifest(body.manifest),
                "note": "Nothing is saved until you review the draft and choose Create assistant."}

    @app.get("/api/v1/catalog/sources")
    def list_sources() -> dict:
        document, problem = catalog_sources.load_sources(state_dir)
        return sources_payload(document, problem)

    @app.post("/api/v1/catalog/sources")
    def add_source(body: SourceRequest, request: Request) -> dict:
        require_local_owner(request)
        try:
            document = catalog_sources.add_source(state_dir, body.kind, body.location,
                                                  revision=body.expected_revision)
        except catalog_sources.SourceConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None
        return sources_payload(document)

    @app.put("/api/v1/catalog/sources/{source_id}")
    def update_source(source_id: str, body: SourceEnabled, request: Request) -> dict:
        require_local_owner(request)
        try:
            document = catalog_sources.set_enabled(state_dir, source_id, body.enabled,
                                                   revision=body.expected_revision)
        except catalog_sources.SourceConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None
        return sources_payload(document)

    @app.delete("/api/v1/catalog/sources/{source_id}")
    def delete_source(source_id: str, expected_revision: int, request: Request) -> dict:
        require_local_owner(request)
        try:
            document = catalog_sources.remove_source(state_dir, source_id, revision=expected_revision)
        except catalog_sources.SourceConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None
        return sources_payload(document)

    @app.post("/api/v1/catalog/sources/{source_id}/fetch")
    def fetch_source(source_id: str, body: SourceRevision, request: Request) -> dict:
        """Explicit, per-source fetch. Never runs in the background and never installs anything."""
        require_local_owner(request)
        try:
            document = catalog_sources.fetch_source(state_dir, source_id, revision=body.expected_revision)
        except catalog_sources.SourceConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None
        return sources_payload(document)

    @app.get("/api/v1/catalog/sources/{source_id}/entries/{entry_id}")
    def preview_source_entry(source_id: str, entry_id: str, request: Request) -> dict:
        require_local_owner(request)
        document, problem = catalog_sources.load_sources(state_dir)
        if problem:
            raise fail(catalog_sources.SourceError(problem))
        try:
            source = catalog_sources._source(document, source_id)
            return catalog_sources.preview_entry(source, entry_id)
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None

    @app.post("/api/v1/catalog/sources/{source_id}/entries/{entry_id}/trust")
    def trust_source_entry(source_id: str, entry_id: str, body: TrustRequest, request: Request) -> dict:
        require_local_owner(request)
        try:
            document = catalog_sources.trust_entry(state_dir, source_id, entry_id, body.expected_hash,
                                                   revision=body.expected_revision)
        except catalog_sources.SourceConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except catalog_sources.SourceError as exc:
            raise fail(exc) from None
        return sources_payload(document)
