"""Sharing an assistant as a catalog template: sanitised, bounded, never automatic.

Export maps a saved assistant to the catalog manifest format (`hutch.catalog/1`) and runs a checklist over
the text that would be shared. Credential shapes block the export; URLs, e-mail addresses and absolute
paths are warnings the person must acknowledge. Memory, history, attachments, saved facts, connected
accounts and schedules are not in the manifest at all. Import never overwrites: it validates the manifest
and returns the values the normal setup review pre-fills, and only that separate creation action saves.

The exporter is a pure function over a Bot and text: it writes nothing and calls no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .catalog import CatalogError, content_hash, parse_manifest
from .models import Bot

PUBLISHER_DEFAULT = "You"
CATEGORY_DEFAULT = "Yours"
OMITTED = (
    "memory values and saved facts",
    "chat and run history",
    "attachments and workspace files",
    "schedules and recurring work",
    "connected accounts, API keys and provider URLs",
    "local folder paths and browser handoff state",
)
CHECKLIST = (
    "No API keys, tokens or private keys (checked automatically)",
    "No private URLs, e-mail addresses or absolute paths you would not share (warned automatically)",
    "No customer, teammate or incident data in the instructions",
    "The instructions and enabled tools are exactly what you intend to publish",
)
_CREDENTIALS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|password)\s*[:=]\s*\S{8,}"),
)
_PRIVATE_SHAPES = (
    (re.compile(r"https?://[^\s'\"<>]+"), "a URL"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "an e-mail address"),
    (re.compile(r"(?<![\w.])/(?:home|Users|root|var|opt|srv)/[^\s'\"]+"), "an absolute local path"),
)


class ExportBlocked(ValueError):
    """The text contains a credential shape; it must not leave this machine."""


@dataclass
class ExportReview:
    manifest: dict[str, Any] | None
    content_hash: str
    warnings: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return {"manifest": self.manifest, "content_hash": self.content_hash,
                "warnings": self.warnings, "blocked": self.blocked,
                "omitted": list(self.omitted), "checklist": list(self.checklist)}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")[:40]
    if len(slug) < 2:
        slug = f"assistant-{slug or 'copy'}"[:40]
    return slug


def build_manifest(bot: Bot, *, publisher: str = PUBLISHER_DEFAULT, version: str = "1.0.0",
                   category: str = CATEGORY_DEFAULT, tagline: str = "") -> dict[str, Any]:
    """The manifest a person would publish, before the checklist runs."""
    name = (bot.display_name or bot.name).strip()
    assistant = {
        "instructions": bot.instructions or "",
        "tools": list(bot.tools or []),
        "preset": bot.preset or "",
        "command_rules": [{"verdict": rule.verdict, "match": rule.match} for rule in (bot.command_rules or [])],
    }
    manifest = {
        "format": "hutch.catalog/1",
        "id": _slug(bot.name),
        "version": version,
        "order": 100,
        "name": name[:60] or "Assistant",
        "category": (category or CATEGORY_DEFAULT)[:40],
        "tagline": (tagline.strip() or (bot.description or f"A copy of {name}"))[:140],
        "reads": "",
        "produces": "",
        "safety": "",
        "needs_folder": False,
        "publisher": (publisher or PUBLISHER_DEFAULT)[:60],
        "assistant": assistant,
    }
    return manifest


def _scan(texts: list[str]) -> tuple[list[str], list[str]]:
    blocked: list[str] = []
    warnings: list[str] = []
    for text in texts:
        for pattern in _CREDENTIALS:
            if pattern.search(text):
                blocked.append("the text contains something shaped like a credential or API key")
                break
        for pattern, label in _PRIVATE_SHAPES:
            if pattern.search(text):
                warnings.append(f"the text contains {label}; review it before sharing")
    return blocked, sorted(set(warnings))


def review_export(bot: Bot, *, publisher: str = PUBLISHER_DEFAULT, version: str = "1.0.0",
                  category: str = CATEGORY_DEFAULT, tagline: str = "") -> ExportReview:
    """Validate the manifest and run the sharing checklist. Nothing is written or sent."""
    manifest = build_manifest(bot, publisher=publisher, version=version, category=category, tagline=tagline)
    entry = parse_manifest(manifest)          # strict: the exported file must import again
    texts = [manifest["assistant"]["instructions"], manifest["name"], manifest["tagline"],
             *(rule["match"] for rule in manifest["assistant"]["command_rules"])]
    blocked, warnings = _scan(texts)
    return ExportReview(manifest=None if blocked else manifest,
                        content_hash=content_hash(manifest),
                        warnings=warnings, blocked=blocked,
                        omitted=list(OMITTED), checklist=list(CHECKLIST))


def configuration_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """The unsaved setup draft an import pre-fills. The person still reviews and creates it."""
    entry = parse_manifest(manifest)
    spec = entry.assistant
    return {
        "name": entry.id,
        "display_name": entry.name,
        "description": entry.tagline,
        "instructions": spec.instructions,
        "template": "",
        "preset": spec.preset,
        "model": "",
        "runtime": "builtin",
        "inference_mode": "hybrid",
        "tools": list(spec.tools),
        "memory_enabled": False,
        "memory_learning": "review",
        "approval_mode": "ask",
        "risk_tier": "supervised",
        "command_rules": [{"verdict": rule.verdict, "match": rule.match} for rule in spec.command_rules],
        "workspace_mode": "managed",
        "local_browser_handoff": False,
        "limits": {},
        "cron": "",
        "timezone": "UTC",
        "catch_up": "coalesce",
        "schedule_prompt": "",
    }


def permissions_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """What an entry asks for, in plain words, before anyone creates it."""
    entry = parse_manifest(manifest)
    spec = entry.assistant
    elevated = sorted(set(spec.tools) & {"shell", "browser", "computer_control", "delegation"})
    return {
        "tools": list(spec.tools),
        "elevated_tools": elevated,
        "needs_folder": entry.needs_folder,
        "command_rules": [{"verdict": rule.verdict, "match": rule.match} for rule in spec.command_rules],
        "publisher": entry.publisher,
        "version": entry.version,
        "content_hash": content_hash(manifest),
        "note": "Creating a copy never grants more than the copy's own saved settings and Hutch's approvals allow.",
    }
