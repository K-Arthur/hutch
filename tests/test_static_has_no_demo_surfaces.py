"""The served static directory never carries a preview, fixture, demo or sample page.

``app.py`` mounts ``src/hutch/server/static`` whole, so any file placed there is reachable by URL. A
fixture-driven prototype page there would show invented data inside the real product. Design previews and
their fixtures belong outside the served tree (or outside the repository), never under ``static/``.
"""
from __future__ import annotations

import re

from tests.support.artifacts import repository_path

STATIC = repository_path("src/hutch/server/static")
FORBIDDEN = re.compile(r"(preview|fixture|demo|sample|mock)", re.IGNORECASE)


def test_no_served_static_file_is_named_like_a_preview_fixture_or_demo():
    offenders = sorted(str(path.relative_to(STATIC)) for path in STATIC.rglob("*")
                       if path.is_file() and FORBIDDEN.search(path.name))
    assert offenders == [], f"demo-like files are served from static/: {offenders}"


def test_the_guard_actually_sees_the_static_directory():
    assert (STATIC / "index.html").is_file()
    assert sum(1 for path in STATIC.rglob("*") if path.is_file()) > 50
