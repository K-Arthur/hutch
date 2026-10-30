"""The UI says "assistant"; "bot" stays in the CLI, API paths and storage.

Spine section 3 (one canonical term per concept). Scans the text a person reads in
the live server templates (text nodes and aria-label, title, placeholder, alt
values), not classes, ids, URLs or Jinja. CLI command text is allowed because the
command group is `hutch bot` (docs/marketing-site.md).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server"
TEMPLATES = SERVER / "templates"
WORD = re.compile(r"\b[Bb]ots?\b")
VISIBLE_ATTRS = ("aria-label", "title", "placeholder", "alt")
# Text that names the CLI, where "bot" is the command group.
ALLOWED = re.compile(r"hutch bot\b")


class _Visible(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.found: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for name, value in attrs:
            if name in VISIBLE_ATTRS and value and WORD.search(value) and not ALLOWED.search(value):
                self.found.append(f"[{name}] {value}")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and WORD.search(data) and not ALLOWED.search(data):
            self.found.append(" ".join(data.split()))


def visible_bot_words(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    text = re.sub(r"\{%.*?%\}", " ", text, flags=re.S)
    text = re.sub(r"\{\{.*?\}\}", "X", text, flags=re.S)
    parser = _Visible()
    parser.feed(text)
    return parser.found


TEMPLATE_FILES = sorted([*TEMPLATES.glob("*.html"), *(TEMPLATES / "macros").glob("*.html")])


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_server_templates_say_assistant_not_bot(path):
    assert visible_bot_words(path) == [], f"{path.name}: say 'assistant' (CLI command text excepted)"


# ---------------------------------------------------------------- SPA scripts

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "audit_ui_vocabulary", Path(__file__).resolve().parent.parent / "scripts" / "audit_ui_vocabulary.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


@pytest.mark.parametrize("path", audit.script_files(), ids=lambda p: p.name)
def test_spa_scripts_say_assistant_not_bot(path):
    assert audit.findings(path) == [], f"{path.name}: run `python scripts/audit_ui_vocabulary.py --fix`"


def test_audit_rewrites_prose_and_leaves_code_alone():
    source = (
        'const html = `<p>Make a bot from this request. Share with a Bot, this Bot, ${bots.length} Bots.</p>`;\n'
        'const label = `<button aria-label="Revoke Bot access" data-grant-bot="${grant.bot_id}">Revoke Bot access</button>`;\n'
        'const rows = bots.map(bot => `<option value="${bot.id}">${bot.name}</option>`);\n'
        'api(`/bots/${name}`); const key = "bot_id"; const cls = "bot-template-preview";\n'
        'const cli = "Erase one key with hutch bot purge --key"; const cli2 = "the CLI (bot purge --key)";\n'
        'const tg = "Create a dedicated bot with Telegram’s BotFather"; toast("Bot settings saved.");\n'
    )
    result = audit.rewrite(source)
    assert "Make an assistant from this request" in result
    assert "Share with an assistant, this assistant, ${bots.length} assistants." in result
    assert 'aria-label="Revoke assistant access"' in result and ">Revoke assistant access</button>" in result
    assert 'data-grant-bot="${grant.bot_id}"' in result, "attributes that are not prose are never touched"
    assert "bots.map(bot => `<option value=\"${bot.id}\">${bot.name}</option>`)" in result
    assert "api(`/bots/${name}`)" in result and '"bot_id"' in result and '"bot-template-preview"' in result
    assert "hutch bot purge --key" in result and "(bot purge --key)" in result
    assert "dedicated bot with Telegram’s BotFather" in result
    assert 'toast("Assistant settings saved.")' in result


def test_audit_refuses_a_rewrite_that_changes_more_than_the_word(monkeypatch):
    monkeypatch.setattr(audit.Rewriter, "run", lambda self: self.s.replace("const a", "const b").replace("bot", "assistant"))
    with pytest.raises(AssertionError):
        audit.rewrite("const a = 'this bot';")
