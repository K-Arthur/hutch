"""Catalog sources: local folders and static URL indexes, hash-pinned and explicitly fetched.

A source is something the person adds. A local source is a folder of `hutch.catalog/1` manifests (the same
strict format the bundled catalog uses). A URL source is a static `index.json` the person chooses; fetching
it is an explicit action, never background work, and the default fetcher goes through `netguard.safe_get`
(no private, loopback or metadata addresses). Every entry is inert until its exact content hash is trusted,
so a changed manifest comes back as `changed` and must be reviewed again. Nothing here creates an assistant
or runs a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .catalog import CatalogError, content_hash, load_directory, parse_manifest
from .models import iso, utcnow

FORMAT = "hutch.catalog.index/1"
MAX_INDEX_BYTES = 64 * 1024
MAX_ENTRIES = 100
MAX_SOURCES = 20
FETCHER = Callable[[str], str]
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class SourceError(ValueError):
    """A source or entry that cannot be used, with a reason a person can act on."""


class SourceConflict(SourceError):
    """The saved revision moved since the reviewer loaded it."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IndexEntry(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    manifest_url: str = Field(min_length=8, max_length=2048)
    entry_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    publisher: str = Field(min_length=1, max_length=60)


class CatalogIndex(_Strict):
    format: Literal["hutch.catalog.index/1"]
    entries: list[IndexEntry] = Field(default_factory=list, max_length=MAX_ENTRIES)


class PinnedEntry(BaseModel):
    version: str = ""
    manifest_hash: str = ""       # sha256 of the exact manifest content last seen
    trusted_hash: str = ""        # the exact content the person reviewed; empty = inert
    trusted_at: str = ""
    changed: bool = False


class CatalogSource(BaseModel):
    id: str
    kind: Literal["local", "url"]
    location: str
    enabled: bool = True
    pinned: dict[str, PinnedEntry] = Field(default_factory=dict)
    added_at: str = ""
    last_fetched_at: str = ""
    last_error: str = ""


class SourcesDocument(BaseModel):
    version: int = 1
    revision: int = 0
    sources: list[CatalogSource] = Field(default_factory=list, max_length=MAX_SOURCES)

    @field_validator("sources")
    @classmethod
    def _unique_ids(cls, sources: list[CatalogSource]) -> list[CatalogSource]:
        ids = [source.id for source in sources]
        if len(ids) != len(set(ids)):
            raise ValueError("two catalog sources share an id")
        return sources


def _directory(state_dir: Path | str) -> Path:
    directory = Path(state_dir) / "catalog"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def sources_path(state_dir: Path | str) -> Path:
    return _directory(state_dir) / "sources.json"


def load_sources(state_dir: Path | str):
    path = sources_path(state_dir)
    if not path.exists():
        return SourcesDocument(), None
    try:
        text = path.read_text(encoding="utf-8")
        if len(text.encode("utf-8")) > MAX_INDEX_BYTES:
            raise SourceError(f"larger than {MAX_INDEX_BYTES // 1024} KB")
        return SourcesDocument.model_validate_json(text), None
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        return SourcesDocument(), f"{path.name} could not be read ({exc}); no source is applied until you save one"


def _save(state_dir: Path | str, document: SourcesDocument) -> SourcesDocument:
    current, _ = load_sources(state_dir)
    if document.revision != current.revision:
        raise SourceConflict(f"catalog sources changed since you opened them (saved revision {current.revision}, "
                             f"your revision {document.revision}); reload before saving")
    updated = document.model_copy(update={"revision": current.revision + 1})
    path = sources_path(state_dir)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(updated.model_dump_json(indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return updated


def _source(document: SourcesDocument, source_id: str) -> CatalogSource:
    for source in document.sources:
        if source.id == source_id:
            return source
    raise SourceError(f"no catalog source named {source_id}")


def _slug(location: str) -> str:
    tail = Path(urlsplit(location).path or location).name or "source"
    return re.sub(r"[^a-z0-9-]+", "-", tail.lower()).strip("-")[:40] or "source"


def add_source(state_dir: Path | str, kind: str, location: str, *, revision: int) -> SourcesDocument:
    location = (location or "").strip()
    if not location:
        raise SourceError("a catalog source needs a location")
    if kind == "local":
        path = Path(location).expanduser().resolve()
        if not path.is_dir():
            raise SourceError(f"{location} is not a folder")
        if path.is_relative_to(Path(state_dir).resolve()):
            raise SourceError("a catalog source cannot point inside Hutch's own state directory")
        location = str(path)
    elif kind == "url":
        parts = urlsplit(location)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise SourceError("a URL source needs a full http(s) address")
    else:
        raise SourceError("a catalog source is either a local folder or a static URL index")
    document, problem = load_sources(state_dir)
    if problem:
        raise SourceError(problem)
    if len(document.sources) >= MAX_SOURCES:
        raise SourceError(f"at most {MAX_SOURCES} catalog sources")
    base, index = _slug(location), 2
    existing = {source.id for source in document.sources}
    while base in existing:
        base, index = f"{_slug(location)}-{index}", index + 1
    document = document.model_copy(update={"revision": revision})
    document.sources.append(CatalogSource(id=base, kind=kind, location=location, added_at=iso(utcnow())))
    return _save(state_dir, document)


def remove_source(state_dir: Path | str, source_id: str, *, revision: int) -> SourcesDocument:
    document, problem = load_sources(state_dir)
    if problem:
        raise SourceError(problem)
    _source(document, source_id)
    document = document.model_copy(update={"revision": revision})
    document.sources = [source for source in document.sources if source.id != source_id]
    return _save(state_dir, document)


def set_enabled(state_dir: Path | str, source_id: str, enabled: bool, *, revision: int) -> SourcesDocument:
    document, problem = load_sources(state_dir)
    if problem:
        raise SourceError(problem)
    _source(document, source_id)
    document = document.model_copy(update={"revision": revision})
    for source in document.sources:
        if source.id == source_id:
            source.enabled = bool(enabled)
    return _save(state_dir, document)


def default_fetcher(url: str) -> str:
    from .netguard import safe_get
    fetched = safe_get(url, max_bytes=MAX_INDEX_BYTES)
    return fetched.text


def _parse_index(text: str) -> CatalogIndex:
    if len(text.encode("utf-8")) > MAX_INDEX_BYTES:
        raise SourceError(f"the index is larger than {MAX_INDEX_BYTES // 1024} KB")
    try:
        return CatalogIndex.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "index"
        raise SourceError(f"{where}: {first['msg']}") from None


def fetch_source(state_dir: Path | str, source_id: str, *, revision: int,
                 fetcher: Optional[FETCHER] = None) -> SourcesDocument:
    """Explicitly fetch one source. Local folders are rescanned; URL indexes are requested now, never in the background."""
    document, problem = load_sources(state_dir)
    if problem:
        raise SourceError(problem)
    source = _source(document, source_id)
    if not source.enabled:
        raise SourceError(f"catalog source {source_id} is disabled")
    fetched_at = iso(utcnow())
    error = ""
    discovered: dict[str, PinnedEntry] = {}
    try:
        if source.kind == "local":
            load = load_directory(Path(source.location), "yours")
            if load.diagnostics:
                error = "; ".join(load.diagnostics[:3])
            discovered = {item.entry.id: PinnedEntry(version=item.entry.version, manifest_hash=item.content_hash)
                          for item in load.entries}
        else:
            index = _parse_index((fetcher or default_fetcher)(source.location))
            discovered = {entry.id: PinnedEntry(version=entry.version, manifest_hash=entry.entry_hash)
                          for entry in index.entries}
    except (OSError, SourceError, CatalogError, ValueError) as exc:
        error = str(exc)
    document = document.model_copy(update={"revision": revision})
    for item in document.sources:
        if item.id != source_id:
            continue
        for entry_id, found in discovered.items():
            previous = item.pinned.get(entry_id)
            if previous and previous.manifest_hash and previous.manifest_hash != found.manifest_hash:
                found.trusted_hash = ""          # content moved: inert until reviewed again
                found.changed = True
                found.trusted_at = previous.trusted_at
            elif previous:
                found.trusted_hash, found.trusted_at = previous.trusted_hash, previous.trusted_at
            item.pinned[entry_id] = found
        for stale_id in set(item.pinned) - set(discovered):
            item.pinned[stale_id].changed = True
        item.last_fetched_at, item.last_error = fetched_at, error
    return _save(state_dir, document)


def entry_manifest(source: CatalogSource, entry_id: str, *, fetcher: Optional[FETCHER] = None) -> dict[str, Any]:
    if source.kind == "local":
        path = Path(source.location) / f"{entry_id}.json"
        if not path.is_file():
            raise SourceError(f"{entry_id} is no longer in {source.location}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceError(f"{path.name}: {exc}") from None
    else:
        index = _parse_index((fetcher or default_fetcher)(source.location))
        match = next((entry for entry in index.entries if entry.id == entry_id), None)
        if match is None:
            raise SourceError(f"{entry_id} is no longer in the index")
        data = json.loads((fetcher or default_fetcher)(match.manifest_url))
    parse_manifest(data)
    return data


def preview_entry(source: CatalogSource, entry_id: str, *, fetcher: Optional[FETCHER] = None) -> dict[str, Any]:
    """The exact manifest, its hash, its permission summary and whether the person has trusted this content."""
    from .catalog_export import permissions_from_manifest
    manifest = entry_manifest(source, entry_id, fetcher=fetcher)
    digest = content_hash(manifest)
    pin = source.pinned.get(entry_id, PinnedEntry())
    if pin.trusted_hash and pin.trusted_hash == digest:
        state = "trusted"
    elif pin.changed or (pin.trusted_hash and pin.trusted_hash != digest):
        state = "changed"
    elif pin.manifest_hash and pin.manifest_hash != digest:
        state = "changed"
    else:
        state = "untrusted"
    return {"source": source.id, "kind": source.kind, "entry": manifest, "content_hash": digest,
            "permissions": permissions_from_manifest(manifest), "state": state,
            "trusted_at": pin.trusted_at, "inert": state != "trusted",
            "note": "Nothing is created from this entry until the normal setup review creates your own copy."}


def trust_entry(state_dir: Path | str, source_id: str, entry_id: str, expected_hash: str, *,
                revision: int, fetcher: Optional[FETCHER] = None) -> SourcesDocument:
    document, problem = load_sources(state_dir)
    if problem:
        raise SourceError(problem)
    source = _source(document, source_id)
    manifest = entry_manifest(source, entry_id, fetcher=fetcher)
    digest = content_hash(manifest)
    if digest != expected_hash:
        raise SourceError("the entry changed since you reviewed it; preview it again before trusting it")
    document = document.model_copy(update={"revision": revision})
    for item in document.sources:
        if item.id == source_id:
            item.pinned[entry_id] = PinnedEntry(version=manifest.get("version", ""), manifest_hash=digest,
                                                trusted_hash=digest, trusted_at=iso(utcnow()))
    return _save(state_dir, document)


def entry_digest(manifest: dict[str, Any]) -> str:
    return content_hash(manifest)
