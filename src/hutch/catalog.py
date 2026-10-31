"""The assistant catalog: ready-made assistants as reviewable data, not code.

A catalog entry is a JSON manifest (format `hutch.catalog/1`) describing the assistant it creates, who published
it, its version and what it asks to be allowed. Bundled entries ship in `data/catalog/`. Creating an assistant
from an entry never skips the person's review: it opens the normal setup page, and the result is the person's own
copy (design after Grok Bot's templates and OpenClaw's role definitions, see docs/realignment/platform-gap-analysis).

Manifests are validated strictly (unknown fields, unknown tools, oversize text and bad verdicts are refused with a
reason). A bad file becomes a diagnostic; it never stops the catalog from loading.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

FORMAT = "hutch.catalog/1"
BUNDLED_DIR = Path(__file__).parent / "data" / "catalog"
MAX_MANIFEST_BYTES = 64 * 1024
_ID = r"^[a-z0-9][a-z0-9-]{1,40}$"
_VERSION = r"^\d+\.\d+\.\d+$"


class CatalogError(ValueError):
    """A manifest that cannot be used, with the reason a person can act on."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CommandRuleSpec(_Strict):
    verdict: Literal["allow", "ask", "deny"]
    match: str = Field(min_length=1, max_length=200)


class AssistantSpec(_Strict):
    instructions: str = Field(min_length=1, max_length=20000)
    tools: list[str] = Field(default_factory=list, max_length=40)
    preset: str = Field(default="", max_length=40)
    command_rules: list[CommandRuleSpec] = Field(default_factory=list, max_length=40)

    @field_validator("tools")
    @classmethod
    def _known_tools(cls, tools: list[str]) -> list[str]:
        from .tools import ALL_TOOL_NAMES, GROUPS
        known = set(ALL_TOOL_NAMES) | set(GROUPS)
        unknown = sorted(set(tools) - known)
        if unknown:
            raise ValueError(f"unknown tool {', '.join(unknown)}")
        return tools


class CatalogEntry(_Strict):
    format: Literal["hutch.catalog/1"]
    id: str = Field(pattern=_ID)
    version: str = Field(pattern=_VERSION)
    order: int = Field(default=100, ge=0, le=1000)   # position in the catalog; ties sort by id
    name: str = Field(min_length=1, max_length=60)
    category: str = Field(min_length=1, max_length=40)
    tagline: str = Field(min_length=1, max_length=140)
    reads: str = Field(max_length=400)
    produces: str = Field(max_length=400)
    safety: str = Field(max_length=400)
    needs_folder: bool
    publisher: str = Field(min_length=1, max_length=60)
    assistant: AssistantSpec


@dataclass(frozen=True)
class LoadedEntry:
    entry: CatalogEntry
    source: str            # "bundled" or "yours"
    content_hash: str      # sha256 of the canonical manifest: what the person reviewed


@dataclass
class CatalogLoad:
    entries: list[LoadedEntry] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def content_hash(data: dict[str, Any]) -> str:
    """Hash of the manifest's content, independent of whitespace and key order."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_manifest(data: Any) -> CatalogEntry:
    if not isinstance(data, dict):
        raise CatalogError("a manifest must be a JSON object")
    try:
        return CatalogEntry.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "manifest"
        raise CatalogError(f"{where}: {first['msg']} ({first['type']})") from None


def load_directory(path: Path, source: str) -> CatalogLoad:
    loaded = CatalogLoad()
    if not path.is_dir():
        return loaded
    seen: set[str] = set()
    for file in sorted(path.glob("*.json")):
        try:
            if file.stat().st_size > MAX_MANIFEST_BYTES:
                raise CatalogError(f"larger than {MAX_MANIFEST_BYTES // 1024} KB")
            data = json.loads(file.read_text(encoding="utf-8"))
            entry = parse_manifest(data)
            if entry.id in seen:
                raise CatalogError(f"duplicate id {entry.id}")
        except (CatalogError, json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            loaded.diagnostics.append(f"{file.name}: {exc}")
            continue
        seen.add(entry.id)
        loaded.entries.append(LoadedEntry(entry, source, content_hash(data)))
    loaded.entries.sort(key=lambda item: (item.entry.order, item.entry.id))
    return loaded


@lru_cache(maxsize=1)
def bundled() -> CatalogLoad:
    return load_directory(BUNDLED_DIR, "bundled")
