"""The product ships no demo content (owner requirement: zero demos or fixtures).

Two guards. First, the interface invents no starter prompts: a person's first request and an assistant's
first message are their own words. Second, `mock` (the removed demo runtime) may only shrink in product
source: every remaining mention is a refusal, a migration guard or a truthful label for old data, and the
allowlist below can only go down. Test fixtures that use a mock route live under tests/, not src/.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
SERVER = SRC / "hutch" / "server"

CANNED = (
    "Plan my week", "Catch up on email", "Organize a project", "Try one of these", "Tidy a folder",
    "Draft a message", "Summarize a document", "Research a topic", "Check a project folder",
    "Or start with an idea", "Sort this week", "Inspect this repository for TODOs",
)

# file -> most `mock` mentions allowed. Lower these as the legacy handling is removed (gap analysis C3).
MOCK_ALLOWED = {
    "src/hutch/connections.py": 1,             # `mock` stays a reserved connection name
    "src/hutch/doctor.py": 1,                  # warns about assistants still on a mock route
    "src/hutch/engine.py": 1,                  # docstring of the refusal to start them
    "src/hutch/modelchoices.py": 3,            # marks the route "setup" and refuses it
    "src/hutch/models.py": 2,                  # the legacy enum value, kept so old rows still load
    "src/hutch/route_problem.py": 4,           # the single server-side answer
    "src/hutch/runtime/__init__.py": 3,        # the refusal itself
    "src/hutch/runtime/builtin.py": 1,
    "src/hutch/server/pages_usage.py": 2,      # labels old usage rows truthfully
    "src/hutch/server/static/app.js": 5,       # workspace-default guard and the "Retired mock" label
    "src/hutch/server/static/model-switcher.js": 1,
}


def _product_files():
    for path in sorted(SRC.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".js", ".html") and "static/vendor" not in path.as_posix():
            yield path


def test_the_interface_invents_no_starter_prompts():
    found = []
    for path in _product_files():
        if path.suffix == ".py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        found += [(path.name, phrase) for phrase in CANNED if phrase in text]
    assert found == [], f"canned prompts in the interface: {found}"


def test_mock_mentions_in_product_source_only_shrink():
    pattern = re.compile(r"\bmock\b|mock/", re.I)
    actual = {}
    for path in _product_files():
        count = len(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
        if count:
            actual[path.relative_to(SRC.parent).as_posix()] = count
    new = {file: n for file, n in actual.items() if file not in MOCK_ALLOWED}
    grown = {file: (n, MOCK_ALLOWED[file]) for file, n in actual.items() if file in MOCK_ALLOWED and n > MOCK_ALLOWED[file]}
    assert new == {}, f"`mock` appeared in new product files: {new}"
    assert grown == {}, f"`mock` grew (found, allowed): {grown}"


def test_no_seeded_assistants_or_sample_runs_are_created_by_the_product():
    """`hutch init` and startup create no assistants (PRODUCT.md: no demo runtime or seeded demo command)."""
    text = (SRC / "hutch" / "cli.py").read_text(encoding="utf-8")
    init = text[text.index("def init("):text.index("def init(") + 3500]
    assert "create_bot" not in init and "TEMPLATES" not in init
