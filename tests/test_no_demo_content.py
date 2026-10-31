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
    "Create a helper from an example", "Choosing an example opens setup", "Optional setup; message below",
)

# file -> most `mock` mentions allowed. Lower these as the legacy handling is removed (gap analysis C3).
# The browser no longer names the retired route at all: the roster, picker and workspace default read the
# server's `route_problem` instead, so only migration and refusal code keeps the name.
MOCK_ALLOWED = {
    "src/hutch/connections.py": 1,             # `mock` stays a reserved connection name
    "src/hutch/doctor.py": 1,                  # warns about assistants still on a mock route
    "src/hutch/demo_leftovers.py": 2,          # one-time account of demo assistants an earlier version left (remove with the migration)
    "src/hutch/server/static/assistant-removal.js": 2,   # the governed removal of those same assistants; the pair goes together
    "src/hutch/engine.py": 1,                  # docstring of the refusal to start them
    "src/hutch/modelchoices.py": 3,            # marks the route "setup" and refuses it
    "src/hutch/models.py": 2,                  # the legacy enum value, kept so old rows still load
    "src/hutch/route_problem.py": 3,           # the single server-side answer
    "src/hutch/runtime/__init__.py": 3,        # the refusal itself
    "src/hutch/runtime/builtin.py": 1,
    "src/hutch/server/pages_usage.py": 2,      # labels old usage rows truthfully
}


def _product_files():
    for path in sorted(SRC.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".js", ".html") and "static/vendor" not in path.as_posix():
            yield path


def test_the_interface_invents_no_starter_prompts():
    found = []
    for path in _product_files():
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


def test_no_seeded_assistants_or_sample_runs_are_created_by_the_product(tmp_path, monkeypatch):
    """`hutch init` and startup create no assistants (PRODUCT.md: no demo runtime or seeded demo command)."""
    text = (SRC / "hutch" / "cli.py").read_text(encoding="utf-8")
    init = text[text.index("def init("):text.index("def init(") + 3500]
    assert "create_bot" not in init and "TEMPLATES" not in init
    # And a real fresh install starts empty: no module seeds an assistant at import or startup.
    from fastapi.testclient import TestClient
    from hutch.runtime.ladder import reset_provider_cache
    from hutch.server.app import create_app
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    reset_provider_cache()
    with TestClient(create_app()) as client:
        assert client.get("/api/bots").json() == []


def test_the_templates_render_no_fixture_or_evidence_content():
    """Product templates never point at a fixture tree or a captured evidence file."""
    templates = SRC / "hutch" / "server" / "templates"
    forbidden = ("fixtures/", "docs/artifacts", "docs/onboarding/evidence")
    found = [(path.name, token) for path in sorted(templates.glob("*.html"))
             for token in forbidden if token in path.read_text(encoding="utf-8", errors="ignore")]
    assert found == [], f"template content points at non-product files: {found}"
