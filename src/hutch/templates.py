"""Starter assistants, loaded from the bundled catalog (`data/catalog/*.json`).

The presets are data, not code: each is a reviewable manifest with a publisher, a version and a content hash
(see `hutch.catalog`). This module keeps the shapes the CLI, API and dashboard already use (`TEMPLATE_INFO`,
`TEMPLATES`, `gallery`, `instantiate`) and builds them from the catalog. None chooses a model, starts a schedule,
sends a message or fabricates a result; templates that read files need a working folder.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import LoadedEntry, bundled
from .models import Bot, CommandRule


@dataclass(frozen=True)
class TemplateInfo:
    key: str
    category: str
    tagline: str
    reads: str                    # what it expects to find (and where)
    produces: str                 # what it leaves behind
    safety: str                   # one honest line about what it can and cannot do
    needs_folder: bool            # reads files you provide: give it a working folder
    bot: Bot
    version: str = ""
    publisher: str = ""
    content_hash: str = ""


def _info(item: LoadedEntry) -> TemplateInfo:
    entry, spec = item.entry, item.entry.assistant
    bot = Bot(name=entry.id, template=entry.id, model="", description=entry.tagline, display_name=entry.name,
              instructions=spec.instructions, tools=list(spec.tools), preset=spec.preset,
              command_rules=[CommandRule(verdict=rule.verdict, match=rule.match) for rule in spec.command_rules])
    return TemplateInfo(entry.id, entry.category, entry.tagline, entry.reads, entry.produces, entry.safety,
                        entry.needs_folder, bot, entry.version, entry.publisher, item.content_hash)


_T: list[TemplateInfo] = [_info(item) for item in bundled().entries]

#: name -> everything a gallery shows
TEMPLATE_INFO: dict[str, TemplateInfo] = {t.key: t for t in _T}

#: name -> a ready-to-copy Bot (what the CLI, API and dashboard create from)
TEMPLATES: dict[str, Bot] = {t.key: t.bot for t in _T}

CATEGORIES = ["Personal", "Research", "Operations", "Documents", "Analytics"]


def instantiate(key: str, name: str) -> Bot:
    """Create a fresh Bot from a template with its own identity.

    ``TEMPLATES`` entries are process-wide singletons; every copy must receive a new immutable
    Bot ID, or a second Bot created from the same template collides with the first.
    """
    from .models import new_id
    bot = TEMPLATES[key].model_copy(deep=True)
    bot.id = new_id("bot")
    bot.name, bot.template = name, key
    return bot


def gallery() -> list[tuple[str, list[TemplateInfo]]]:
    """Templates grouped by category, in a stable order."""
    out = []
    for cat in CATEGORIES:
        items = [t for t in _T if t.category == cat]
        if items:
            out.append((cat, items))
    return out
