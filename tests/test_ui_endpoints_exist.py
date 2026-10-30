"""Every control's backend exists: SPA API calls and template forms resolve to registered routes.

P4 of docs/realignment/release-readiness-progress.md ("no control may promise more than its backend").
A button wired to an endpoint that was renamed or never built is the plainest way a UI promises
more than the product does. Dynamic parts (`${id}`, `{{ id }}`) are wildcards, so a call such as
`/v1/workflows/runs/${id}/${action}` is satisfied by any registered route of that shape.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hutch.server.app import create_app

SERVER = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server"
CALL = re.compile(r"""\b(?:api|hutchApi)\(\s*([`'"])(/[^`'"]*)\1\s*(?:,\s*\{([^}]{0,200}))?""")
FORM = re.compile(r'<form[^>]*\baction="(/[^"?]*)', re.I)


@pytest.fixture(scope="module")
def routes(tmp_path_factory):
    import os
    state = tmp_path_factory.mktemp("endpoints")
    previous = os.environ.get("HUTCH_STATE_DIR")
    os.environ["HUTCH_STATE_DIR"] = str(state)
    try:
        app = create_app()
    finally:
        if previous is None:
            os.environ.pop("HUTCH_STATE_DIR", None)
        else:
            os.environ["HUTCH_STATE_DIR"] = previous
    found = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            found.add((method.upper(), getattr(route, "path", "")))
    return found


def _answered(routes, method: str, path: str) -> bool:
    """True when a registered route of `method` has the shape of `path`.

    Compared segment by segment: a `{param}` in the route, or a dynamic `X` in the call, matches any
    segment; a `{name:path}` route swallows the rest of the path.
    """
    want = [part for part in path.strip("/").split("/")]
    for registered_method, template in routes:
        if registered_method != method:
            continue
        have = template.strip("/").split("/")
        for index, segment in enumerate(have):
            if segment.startswith("{") and segment.endswith(":path}"):
                if index <= len(want):
                    return True
            if index >= len(want):
                break
            if not (segment.startswith("{") or want[index] == "X" or segment == want[index]):
                break
        else:
            if len(have) == len(want):
                return True
    return False


def _call_path(raw: str) -> str:
    raw = re.sub(r"(?<=[^/])\$\{[^}]*\}$", "", raw)  # `models${query}`: a suffix glued to the last segment is a query string
    return re.sub(r"\$\{[^}]*\}", "X", raw.split("?")[0])


def _spa_calls():
    for script in sorted((SERVER / "static").glob("*.js")):
        source = script.read_text(encoding="utf-8")
        for match in CALL.finditer(source):
            path = _call_path(match.group(2))
            if path.startswith("/X") or path in ("", "/"):
                continue  # a fully dynamic path cannot be checked by name
            verb = re.search(r"""method:\s*["'](\w+)["']""", match.group(3) or "")
            line = source.count("\n", 0, match.start()) + 1
            yield f"{script.name}:{line}", (verb.group(1).upper() if verb else "GET"), "/api" + path


def test_every_spa_api_call_has_a_registered_route(routes):
    calls = list(_spa_calls())
    assert len(calls) > 250, "the scan should see the SPA's API surface; the pattern may have stopped matching"
    missing = [(where, method, path) for where, method, path in calls if not _answered(routes, method, path)]
    assert missing == [], f"SPA calls with no registered route: {missing[:10]}"


def test_every_template_form_posts_to_a_registered_route(routes):
    missing = []
    forms = 0
    for template in sorted((SERVER / "templates").rglob("*.html")):
        for match in FORM.finditer(template.read_text(encoding="utf-8")):
            forms += 1
            path = re.sub(r"\{\{.*?\}\}", "X", match.group(1))
            if not (_answered(routes, "POST", path) or _answered(routes, "GET", path)):
                missing.append((template.name, path))
    assert forms > 10
    assert missing == [], f"template forms with no registered route: {missing}"


def test_the_checker_notices_a_missing_route(routes):
    assert _answered(routes, "GET", "/api/health")
    assert not _answered(routes, "POST", "/api/v1/this-endpoint-was-never-built/X")
    assert not _answered(routes, "DELETE", "/api/health")
