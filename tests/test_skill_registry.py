"""Registry discovery, digest pinning, and dependency resolution.

The registry is the most attacker-controlled input in the skills subsystem: a document at a URL
that names packages and digests. These tests cover what it may do (list packages, pin bytes) and
what it may not do (install anything implicitly, make a package trusted, or pass a lying digest).
Dependency resolution is covered alongside it, because its whole value is knowing where a missing
dependency could come from.
"""

from __future__ import annotations

import io
import json
import zipfile
import hashlib
from pathlib import Path

import httpx
import pytest

from hutch import skills as sk
from hutch.skill_dependency import MAX_DEPTH, resolve_dependencies
from hutch.skill_registry_index import (INDEX_FORMAT, MAX_REGISTRIES, Entry, RegistryError,
                                        RegistryIndex, parse_index)

PUBLIC = {"packages.example": ["93.184.216.34"]}
SKILL = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "1.0"
{deps}
---

## Steps
{body}
"""


def _resolver(table=PUBLIC):
    def resolve(host, port, *args, **kwargs):
        addresses = table.get(host)
        if addresses is None:
            import socket
            raise socket.gaierror("no such host")
        return [(2, 1, 6, "", (address, port)) for address in addresses]
    return resolve


def archive(name: str, *, body: str = "Do the thing.", deps: str = "", description: str = "A skill.") -> bytes:
    buffer = io.BytesIO()
    depends = f'  hutch.requires-skills: "{deps}"' if deps else ""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("SKILL.md", SKILL.format(name=name, description=description, deps=depends, body=body))
    return buffer.getvalue()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def serve(routes: dict[str, bytes], *, seen: list[str] | None = None):
    """A transport that answers named URLs and records every request it received.

    ``netguard`` dials the address it validated and keeps the hostname in the Host header, so
    routing has to look at the header rather than the connection URL. That is itself evidence the
    pinning is real: the URL httpx sees is the numeric address.
    """
    def handler(request):
        host = request.headers.get("host") or ""
        url = f"https://{host}{request.url.path}"
        if seen is not None:
            seen.append(url)
        body = routes.get(url)
        if body is None:
            return httpx.Response(404)
        content_type = "application/zip" if url.endswith(".zip") else "application/json"
        return httpx.Response(200, content=body, headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def index_document(entries: list[dict]) -> bytes:
    return json.dumps({"format": INDEX_FORMAT, "skills": entries}).encode()


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"


# ------------------------------------------------------------------ index validation


def test_a_valid_index_lists_entries():
    entries, diagnostics, truncated = parse_index(index_document([
        {"name": "alpha", "url": "https://packages.example/alpha.zip", "version": "1.0",
         "publisher": "someone", "sha256": "a" * 64}]), "r1")
    assert diagnostics == [] and truncated is False
    assert entries[0].name == "alpha" and entries[0].sha256 == "a" * 64


@pytest.mark.parametrize("entry, fragment", [
    ({"name": "Bad Name", "url": "https://x.example/a.zip"}, "invalid name"),
    ({"name": "ok", "url": "http://x.example/a.zip"}, "https package URL"),
    ({"name": "ok", "url": "file:///etc/passwd"}, "https package URL"),
    ({"name": "ok", "url": "https://x.example/a.zip", "sha256": "notadigest"}, "malformed sha256"),
    ({"name": "ok"}, "https package URL"),
])
def test_invalid_entries_are_refused_with_a_reason(entry, fragment):
    entries, diagnostics, _ = parse_index(index_document([entry]), "r1")
    assert entries == []
    assert any(fragment in message for message in diagnostics)


@pytest.mark.parametrize("document, fragment", [
    (b"not json", "not valid JSON"),
    (json.dumps({"skills": []}).encode(), "format"),
    (json.dumps({"format": "other/9", "skills": []}).encode(), "format"),
    (json.dumps({"format": INDEX_FORMAT}).encode(), "skills list"),
])
def test_a_malformed_index_is_refused(document, fragment):
    with pytest.raises(RegistryError) as exc:
        parse_index(document.decode(), "r1")
    assert fragment in str(exc.value)


def test_a_duplicate_entry_inside_one_index_keeps_the_first():
    entries, diagnostics, _ = parse_index(index_document([
        {"name": "dup", "url": "https://x.example/one.zip"},
        {"name": "dup", "url": "https://x.example/two.zip"}]), "r1")
    assert len(entries) == 1 and entries[0].url.endswith("one.zip")
    assert any("listed twice" in message for message in diagnostics)


# ------------------------------------------------------------------ configuration


def test_a_registry_must_be_https_and_a_slug(state):
    index = RegistryIndex(state)
    with pytest.raises(RegistryError):
        index.add("r1", "http://packages.example/index.json")
    with pytest.raises(RegistryError):
        index.add("Not A Slug", "https://packages.example/index.json")
    assert index.configured() == []


def test_the_number_of_registries_is_bounded(state):
    index = RegistryIndex(state)
    for number in range(MAX_REGISTRIES):
        index.add(f"r{number}", f"https://packages.example/{number}.json")
    with pytest.raises(RegistryError):
        index.add("overflow", "https://packages.example/x.json")


def test_adding_a_registry_does_not_fetch_or_install(state, monkeypatch):
    """Discovery must not be a side effect of configuration."""
    seen: list[str] = []
    index = RegistryIndex(state, resolver=_resolver(), transport=serve({}, seen=seen))
    index.add("r1", "https://packages.example/index.json")
    assert seen == []
    assert sk.SkillRegistry(state).library()["skills"] == []


# ------------------------------------------------------------------ reading a catalog


def test_a_catalog_merges_registries_and_reports_duplicates(state):
    alpha = index_document([{"name": "alpha", "url": "https://packages.example/a.zip",
                             "description": "First."}])
    both = index_document([{"name": "alpha", "url": "https://packages.example/other.zip"},
                           {"name": "beta", "url": "https://packages.example/b.zip"}])
    routes = {"https://packages.example/one.json": alpha,
              "https://packages.example/two.json": both}
    index = RegistryIndex(state, resolver=_resolver(), transport=serve(routes))
    index.add("one", "https://packages.example/one.json")
    index.add("two", "https://packages.example/two.json")

    catalog = index.catalog()
    assert {entry.name for entry in catalog.entries} == {"alpha", "beta"}
    assert catalog.duplicates == ["alpha"]
    # The first registry to list a name wins, so the result is stable across reads.
    assert next(e for e in catalog.entries if e.name == "alpha").registry_id == "one"
    assert all(state_.ok for state_ in catalog.states)


def test_a_failed_registry_falls_back_to_the_last_saved_listing(state):
    routes = {"https://packages.example/index.json":
              index_document([{"name": "alpha", "url": "https://packages.example/a.zip"}])}
    index = RegistryIndex(state, resolver=_resolver(), transport=serve(routes))
    index.add("r1", "https://packages.example/index.json")
    assert [entry.name for entry in index.catalog().entries] == ["alpha"]

    # The registry now 404s. The saved listing is still usable, and says where it came from.
    broken = RegistryIndex(state, resolver=_resolver(), transport=serve({}))
    catalog = broken.catalog()
    assert [entry.name for entry in catalog.entries] == ["alpha"]
    assert catalog.states[0].ok is False
    assert "last saved listing" in catalog.states[0].reason


def test_a_registry_resolving_privately_is_refused(state):
    index = RegistryIndex(state, resolver=_resolver({"internal.example": ["10.0.0.4"]}),
                          transport=serve({}))
    index.add("r1", "https://internal.example/index.json")
    catalog = index.catalog()
    assert catalog.entries == []
    assert catalog.states[0].ok is False
    assert "cannot be fetched" in catalog.states[0].reason


# ------------------------------------------------------------------ install and digest pinning


def _configured(state, package: bytes, *, name: str = "alpha", publish_digest: bool = True,
                digest_override: str = ""):
    entry = {"name": name, "url": "https://packages.example/a.zip", "version": "1.0",
             "publisher": "someone"}
    if publish_digest:
        entry["sha256"] = digest_override or digest(package)
    routes = {"https://packages.example/index.json": index_document([entry]),
              "https://packages.example/a.zip": package}
    index = RegistryIndex(state, resolver=_resolver(), transport=serve(routes))
    index.add("r1", "https://packages.example/index.json")
    return index


def test_installing_a_listed_package_verifies_its_digest_and_stays_untrusted(state, monkeypatch):
    package = archive("alpha")
    index = _configured(state, package)
    _stub_package_fetch(monkeypatch, package)

    detail = index.install(sk.SkillRegistry(state), "alpha")
    assert detail["name"] == "alpha"
    assert detail["trusted"] is False and detail["enabled"] is False
    assert detail["source"]["kind"] == "registry"
    assert detail["provenance"]["registry_id"] == "r1"
    assert detail["provenance"]["sha256"] == digest(package)


def test_a_package_that_does_not_match_the_published_digest_is_refused(state, monkeypatch):
    """The pin is the only integrity claim a registry makes, so it has to be enforced."""
    package = archive("alpha")
    index = _configured(state, package, digest_override="b" * 64)
    _stub_package_fetch(monkeypatch, package)

    registry = sk.SkillRegistry(state)
    with pytest.raises(RegistryError) as exc:
        index.install(registry, "alpha")
    assert "does not match the digest" in str(exc.value)
    assert registry.library()["skills"] == []


def test_a_listed_package_without_a_digest_installs_but_says_it_is_unpinned(state, monkeypatch):
    package = archive("alpha")
    index = _configured(state, package, publish_digest=False)
    _stub_package_fetch(monkeypatch, package)
    detail = index.install(sk.SkillRegistry(state), "alpha")
    assert detail["name"] == "alpha"
    assert detail["provenance"]["registry_index"]["sha256"] == ""


def test_an_unlisted_package_cannot_be_installed_by_name(state):
    index = _configured(state, archive("alpha"))
    with pytest.raises(RegistryError) as exc:
        index.install(sk.SkillRegistry(state), "not-listed")
    assert "no configured registry lists" in str(exc.value)


def _stub_package_fetch(monkeypatch, package: bytes):
    """Point the download at the mock transport; the egress screening is unchanged."""
    from hutch.netguard import safe_get as real_safe_get

    def fetch(url, **kwargs):
        kwargs.pop("resolver", None)
        kwargs.pop("transport", None)
        return real_safe_get(url, resolver=_resolver(), transport=serve(
            {url: package}), **kwargs)

    monkeypatch.setattr("hutch.skill_remote.safe_get", fetch)

# ------------------------------------------------------------------ the API surface


def _install_plain(registry, name: str) -> None:
    """Install a package that exists only for this test, without trusting it."""
    import tempfile

    registry.state_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=registry.state_dir) as staging:
        directory = Path(staging) / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            SKILL.format(name=name, description="d", deps="", body="b"), encoding="utf-8")
        registry.install_path(directory)


@pytest.fixture()
def api(state, monkeypatch):
    from fastapi.testclient import TestClient

    from hutch.server.app import create_app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(state))
    app = create_app()
    with TestClient(app) as client:
        yield client


def _patch_index_transport(monkeypatch, routes):
    from hutch.netguard import safe_get as real_safe_get

    def fetch(url, **kwargs):
        kwargs.pop("resolver", None)
        kwargs.pop("transport", None)
        return real_safe_get(url, resolver=_resolver(), transport=serve(routes), **kwargs)

    monkeypatch.setattr("hutch.skill_registry_index.safe_get", fetch)


def test_registries_are_managed_over_the_api(api):
    created = api.post("/api/v1/skills/registries",
                       json={"id": "team", "url": "https://packages.example/index.json",
                             "title": "Team packages"})
    assert created.status_code == 201, created.text
    listed = api.get("/api/v1/skills/registries").json()
    assert [entry["id"] for entry in listed["registries"]] == ["team"]
    assert "not a review" in listed["note"]
    assert api.delete("/api/v1/skills/registries/team").json()["removed"] is True
    assert api.get("/api/v1/skills/registries").json()["registries"] == []


def test_an_http_registry_is_refused_over_the_api(api):
    response = api.post("/api/v1/skills/registries",
                        json={"id": "team", "url": "http://packages.example/index.json"})
    assert response.status_code == 422
    assert "https" in response.json()["detail"]


def test_available_marks_what_is_already_installed(api, state, monkeypatch):
    package = archive("alpha")
    routes = {"https://packages.example/index.json": index_document([
        {"name": "alpha", "url": "https://packages.example/a.zip", "sha256": digest(package)},
        {"name": "beta", "url": "https://packages.example/b.zip"}])}
    _patch_index_transport(monkeypatch, routes)
    api.post("/api/v1/skills/registries", json={"id": "r1", "url": "https://packages.example/index.json"})
    _install_plain(sk.SkillRegistry(state), "alpha")

    body = api.get("/api/v1/skills/available").json()
    flags = {entry["name"]: entry["installed"] for entry in body["entries"]}
    assert flags == {"alpha": True, "beta": False}
