"""Discovering skill packages from published indexes, without trusting one because it exists.

A skill index is a JSON document at a URL that lists packages. That is the whole idea, and it is
also the whole risk: an index is attacker-controlled text that names URLs and digests, so it can
only ever be *review material*. This module keeps three promises and no more:

1. **The index is data.** It is fetched through ``netguard``, bounded, and every field is validated
   against a fixed shape before it can appear in an interface. A description cannot become markup,
   a name cannot escape its pattern, and a URL cannot be anything but https.
2. **A digest is a pin, not a proof of authorship.** When an entry publishes ``sha256``, the
   downloaded package must match it byte for byte or the install is refused. That protects against
   a package being swapped after the index was published. It does **not** prove who wrote the
   package, and it does not protect against a malicious index: an index that lies about a digest
   is indistinguishable from one that lies about a URL. The documentation says so.
3. **Discovery is not installation, and installation is not trust.** Nothing here installs
   anything implicitly. A package installed through an index is exactly as untrusted as one from a
   URL, because it arrived the same way.

Registries are configured as a small JSON file under the state directory rather than a table: the
skill subsystem already keeps its trust state in a file beside the packages, and this is the same
kind of local configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import iso, utcnow
from .netguard import NetGuardError, safe_get
from .skills import SkillError

#: The only index format this client understands. A different value is refused, not guessed at.
INDEX_FORMAT = "hutch.skill-index/1"
#: How many entries an index may list. A larger one is truncated with a diagnostic, not trusted.
MAX_ENTRIES = 500
#: How many registries may be configured.
MAX_REGISTRIES = 8
#: Bounds on cached text. These are display fields, not prose.
MAX_DESCRIPTION = 300
MAX_PUBLISHER = 120
MAX_VERSION = 40
MAX_FETCH_BYTES = 512 * 1024
#: A digest is lowercase hex sha256, and nothing else.
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_REGISTRY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class RegistryError(SkillError):
    """An index could not be read, or an entry cannot be used."""


@dataclass
class Entry:
    """One package an index lists. Every field has been validated; none is trusted."""

    name: str
    url: str
    registry_id: str
    description: str = ""
    version: str = ""
    license: str = ""
    publisher: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "url": self.url, "registry_id": self.registry_id,
                "description": self.description, "version": self.version, "license": self.license,
                "publisher": self.publisher, "sha256": self.sha256}


@dataclass
class FetchState:
    """What happened the last time a registry was read."""

    registry_id: str
    index_url: str
    fetched_at: str = ""
    ok: bool = False
    reason: str = ""
    entries: int = 0
    truncated: bool = False


@dataclass
class Catalog:
    """The merged result of reading every configured registry."""

    entries: list[Entry] = field(default_factory=list)
    states: list[FetchState] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)

    def to_dict(self, *, installed: Optional[set[str]] = None) -> dict[str, Any]:
        installed = installed or set()
        return {
            "entries": [{**entry.to_dict(), "installed": entry.name in installed}
                        for entry in self.entries],
            "registries": [state.__dict__ for state in self.states],
            "duplicates": self.duplicates,
            "note": ("A registry is a list someone published, not a review. Installing from one "
                     "lands untrusted like any other download, and a published digest pins the "
                     "bytes it names without proving who wrote them."),
        }


def _text(value: Any, limit: int) -> str:
    """One display field: a scalar string, whitespace-collapsed and bounded."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _parse_entry(raw: Any, registry_id: str) -> tuple[Optional[Entry], str]:
    """Validate one index entry. Returns the entry, or a diagnostic explaining the refusal."""
    if not isinstance(raw, dict):
        return None, "an entry is not an object"
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        return None, "an entry has an invalid name"
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip().lower().startswith("https://"):
        return None, f"'{name}' does not name an https package URL"
    if len(url) > 2048:
        return None, f"'{name}' has an oversized package URL"
    digest = raw.get("sha256", "")
    if digest and (not isinstance(digest, str) or not _DIGEST.match(digest)):
        return None, f"'{name}' publishes a malformed sha256"
    return Entry(name=name, url=url.strip(), registry_id=registry_id,
                 description=_text(raw.get("description"), MAX_DESCRIPTION),
                 version=_text(raw.get("version"), MAX_VERSION),
                 license=_text(raw.get("license"), MAX_VERSION),
                 publisher=_text(raw.get("publisher"), MAX_PUBLISHER),
                 sha256=digest or ""), ""


def parse_index(text: str, registry_id: str) -> tuple[list[Entry], list[str], bool]:
    """Read an index document. Returns entries, diagnostics, and whether it was truncated."""
    try:
        document = json.loads(text)
    except ValueError:
        raise RegistryError("the registry index is not valid JSON") from None
    if not isinstance(document, dict):
        raise RegistryError("the registry index must be a JSON object")
    if document.get("format") != INDEX_FORMAT:
        raise RegistryError(f"the registry index is not in {INDEX_FORMAT} format")
    raw_entries = document.get("skills")
    if not isinstance(raw_entries, list):
        raise RegistryError("the registry index has no skills list")
    entries: list[Entry] = []
    diagnostics: list[str] = []
    seen: set[str] = set()
    truncated = False
    for raw in raw_entries:
        if len(entries) >= MAX_ENTRIES:
            truncated = True
            break
        entry, problem = _parse_entry(raw, registry_id)
        if entry is None:
            diagnostics.append(problem)
            continue
        if entry.name in seen:
            diagnostics.append(f"'{entry.name}' is listed twice; the later one was ignored")
            continue
        seen.add(entry.name)
        entries.append(entry)
    return entries, diagnostics, truncated


class RegistryIndex:
    """The configured skill indexes, their cached listings, and the digests they published."""

    def __init__(self, state_dir: str | Path, *, resolver=None, transport=None):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "skills" / "registries.json"
        self.cache_dir = self.state_dir / "skills" / "index-cache"
        self.resolver = resolver
        self.transport = transport
        self._lock = threading.Lock()

    # -- configuration -----------------------------------------------------

    def _read(self) -> dict[str, Any]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": 1, "registries": {}}
        if not isinstance(document, dict) or not isinstance(document.get("registries"), dict):
            return {"version": 1, "registries": {}}
        return document

    def _write(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    def configured(self) -> list[dict[str, str]]:
        document = self._read()
        return [{"id": key, **{k: str(v) for k, v in value.items() if k in {"url", "title"}}}
                for key, value in sorted(document["registries"].items())]

    def add(self, registry_id: str, url: str, *, title: str = "") -> dict[str, Any]:
        """Configure one index URL. Adding does not fetch, so it cannot install anything."""
        if not _REGISTRY_ID.match(registry_id or ""):
            raise RegistryError("a registry id must be a lowercase slug of at most 32 characters")
        target = (url or "").strip()
        if not target.lower().startswith("https://"):
            raise RegistryError("a registry index URL must use https")
        with self._lock:
            document = self._read()
            if registry_id not in document["registries"] and len(document["registries"]) >= MAX_REGISTRIES:
                raise RegistryError(f"at most {MAX_REGISTRIES} registries can be configured")
            document["registries"][registry_id] = {"url": target, "title": _text(title, 80)}
            self._write(document)
        return {"id": registry_id, "url": target, "title": _text(title, 80)}

    def remove(self, registry_id: str) -> bool:
        with self._lock:
            document = self._read()
            existed = document["registries"].pop(registry_id, None) is not None
            self._write(document)
        (self.cache_dir / f"{registry_id}.json").unlink(missing_ok=True)
        return existed

    # -- reading -----------------------------------------------------------

    def _cache_path(self, registry_id: str) -> Path:
        return self.cache_dir / f"{registry_id}.json"

    def _read_cached(self, registry_id: str) -> list[Entry]:
        try:
            document = json.loads(self._cache_path(registry_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        entries, _diagnostics, _truncated = parse_index(json.dumps(document.get("index", {})), registry_id)
        return entries

    def _fetch(self, registry_id: str, url: str) -> tuple[list[Entry], list[str], bool]:
        try:
            fetched = safe_get(url, max_bytes=MAX_FETCH_BYTES, resolver=self.resolver,
                               transport=self.transport)
        except NetGuardError as exc:
            raise RegistryError(f"the registry cannot be fetched: {exc}") from None
        if not fetched.ok:
            raise RegistryError(f"the registry returned HTTP {fetched.status}")
        if fetched.truncated:
            raise RegistryError(f"the registry index is larger than {MAX_FETCH_BYTES // 1024} KiB")
        entries, diagnostics, truncated = parse_index(fetched.text, registry_id)
        # Cache the *parsed* document, not the raw bytes: what is served from cache later has
        # already been through validation once, and a cached listing can never gain a field.
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._cache_path(registry_id).write_text(json.dumps({
            "fetched_at": iso(utcnow()),
            "index": {"format": INDEX_FORMAT,
                      "skills": [{"name": e.name, "url": e.url, "description": e.description,
                                  "version": e.version, "license": e.license,
                                  "publisher": e.publisher, "sha256": e.sha256}
                                 for e in entries]},
        }, indent=2, sort_keys=True), encoding="utf-8")
        return entries, diagnostics, truncated

    def catalog(self, *, refresh: bool = False) -> Catalog:
        """Read every configured registry, falling back to the last good listing when one fails."""
        catalog = Catalog()
        by_name: dict[str, Entry] = {}
        for configured in self.configured():
            registry_id, url = configured["id"], configured["url"]
            state = FetchState(registry_id=registry_id, index_url=url)
            try:
                entries, diagnostics, truncated = self._fetch(registry_id, url)
                state.ok, state.entries, state.truncated = True, len(entries), truncated
                state.fetched_at = iso(utcnow())
                if diagnostics:
                    state.reason = "; ".join(diagnostics[:4])
            except RegistryError as exc:
                state.ok, state.reason = False, str(exc)
                entries = self._read_cached(registry_id)
                if entries:
                    state.reason += f"; showing the last saved listing ({len(entries)} entries)"
            catalog.states.append(state)
            for entry in entries:
                if entry.name in by_name:
                    if entry.name not in catalog.duplicates:
                        catalog.duplicates.append(entry.name)
                    continue
                by_name[entry.name] = entry
        catalog.entries = [by_name[name] for name in sorted(by_name)]
        return catalog

    def find(self, name: str) -> Optional[Entry]:
        """The first configured registry that lists this package, or ``None``."""
        for entry in self.catalog().entries:
            if entry.name == name:
                return entry
        return None

    def install(self, registry, name: str, *, replace: bool = False) -> dict:
        """Install one listed package, verifying its published digest when there is one.

        This is the only place a digest is enforced, and it is enforced against the bytes that
        were downloaded: a package swapped after the index was published is refused here.
        """
        from .skill_remote import fetch_package

        entry = self.find(name)
        if entry is None:
            raise RegistryError(f"no configured registry lists a skill named '{name}'")
        import tempfile

        root = self.state_dir / "skills" / "downloads"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="registry-", dir=root) as staging:
            provenance = fetch_package(entry.url, Path(staging), resolver=self.resolver,
                                       transport=self.transport)
            if entry.sha256 and provenance["sha256"] != entry.sha256:
                raise RegistryError(
                    "the downloaded package does not match the digest this registry published; "
                    "it was not installed. The registry or the package changed after publication.")
            provenance["registry_id"] = entry.registry_id
            provenance["registry_index"] = entry.to_dict()
            detail = registry._install(
                Path(staging),
                {"kind": "registry", "detail": f"{entry.registry_id}:{entry.name}", "scope": "remote"},
                allow_existing=replace)
        detail["provenance"] = provenance
        detail["review_required"] = detail.get("trusted") is not True
        return detail


__all__ = ["Catalog", "Entry", "INDEX_FORMAT", "MAX_ENTRIES", "MAX_REGISTRIES", "RegistryError",
           "RegistryIndex", "parse_index"]
