"""Installing a skill from a URL: bounded, and never trusted because it downloaded.

The value of a URL install is sharing. The risk is that it hands Hutch an archive. These tests
drive the real fetch path (``netguard.safe_get`` with an injected resolver and transport, the same
seam the netguard suite uses) and pin the four things that must hold: the egress rules still
apply, an archive cannot escape its staging directory, the size budgets are enforced before
extraction, and arriving over the network never implies review.
"""

from __future__ import annotations

import httpx
import pytest

from hutch import skills as sk
from hutch.models import ApprovalMode, Bot
from hutch.skill_remote import MAX_ARCHIVE_BYTES, RemoteSkillError, fetch_package, install_from_url

SKILL = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "{version}"
---

## Steps
{body}
"""

PUBLIC = {"packages.example": ["93.184.216.34"]}


def _resolver(table):
    def resolve(host, port, *args, **kwargs):
        addresses = table.get(host)
        if addresses is None:
            import socket
            raise socket.gaierror("no such host")
        return [(2, 1, 6, "", (address, port)) for address in addresses]
    return resolve


def _archive(files: dict[str, str]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def _serve(body: bytes, *, content_type: str = "application/zip", status: int = 200):
    def handler(request):
        return httpx.Response(status, content=body, headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def _installer(tmp_path):
    return sk.SkillRegistry(tmp_path / "state"), _resolver(PUBLIC)


# ------------------------------------------------------------------ a working install


def test_a_published_package_installs_untrusted_with_provenance(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = _archive({"SKILL.md": SKILL.format(name="shared", description="A shared procedure.",
                                              version="2.1", body="Do the thing."),
                     "references/notes.md": "Extra detail."})
    detail = install_from_url(registry, "https://packages.example/shared.zip",
                              resolver=resolver, transport=_serve(body))

    assert detail["name"] == "shared"
    assert detail["trusted"] is False and detail["enabled"] is False
    assert detail["review_required"] is True
    assert detail["version"] == "2.1"
    assert detail["source"]["kind"] == "url"
    assert detail["source"]["detail"] == "https://packages.example/shared.zip"
    provenance = detail["provenance"]
    assert provenance["host"] == "packages.example"
    assert provenance["kind"] == "archive"
    assert provenance["files"] == 2
    assert len(provenance["sha256"]) == 64
    # The reference file came with it.
    assert any(item["path"] == "references/notes.md" for item in detail["resources"])


def test_a_single_skill_markdown_file_is_accepted(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = SKILL.format(name="single", description="One file.", version="1.0", body="Do it.").encode()
    detail = install_from_url(registry, "https://packages.example/SKILL.md",
                              resolver=resolver, transport=_serve(body, content_type="text/markdown"))
    assert detail["name"] == "single"
    assert detail["provenance"]["kind"] == "skill_md"


def test_an_installed_url_skill_can_be_replaced_and_loses_trust(tmp_path):
    """Anyone can publish new bytes at a URL, so a re-fetch must not inherit a review."""
    registry, resolver = _installer(tmp_path)
    first = _archive({"SKILL.md": SKILL.format(name="shared", description="v1.", version="1", body="One.")})
    install_from_url(registry, "https://packages.example/shared.zip",
                     resolver=resolver, transport=_serve(first))
    registry.trust("shared")
    assert registry.detail("shared")["trusted"] is True

    second = _archive({"SKILL.md": SKILL.format(name="shared", description="v2.", version="2", body="Two.")})
    again = install_from_url(registry, "https://packages.example/shared.zip", replace=True,
                             resolver=resolver, transport=_serve(second))
    assert again["trusted"] is False
    assert again["version"] == "2"
    assert registry.detail("shared")["trusted"] is False


def test_installing_over_an_existing_skill_needs_an_explicit_replace(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = _archive({"SKILL.md": SKILL.format(name="shared", description="v1.", version="1", body="One.")})
    install_from_url(registry, "https://packages.example/shared.zip", resolver=resolver, transport=_serve(body))
    with pytest.raises(sk.SkillError) as exc:
        install_from_url(registry, "https://packages.example/shared.zip", resolver=resolver, transport=_serve(body))
    assert "already installed" in str(exc.value)


# ------------------------------------------------------------------ refusal paths


def test_a_url_that_resolves_to_a_private_address_is_refused(tmp_path):
    registry, _ = _installer(tmp_path)
    resolver = _resolver({"internal.example": ["10.0.0.9"]})
    with pytest.raises(RemoteSkillError) as exc:
        install_from_url(registry, "https://internal.example/pkg.zip", resolver=resolver,
                         transport=_serve(b"PK.."))
    assert "cannot be fetched" in str(exc.value)


def test_a_redirect_to_a_private_address_is_not_followed(tmp_path):
    registry, resolver = _installer(tmp_path)

    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    with pytest.raises(RemoteSkillError):
        install_from_url(registry, "https://packages.example/pkg.zip", resolver=resolver,
                         transport=httpx.MockTransport(handler))


def test_an_http_error_is_reported_as_one(tmp_path):
    registry, resolver = _installer(tmp_path)
    with pytest.raises(RemoteSkillError) as exc:
        install_from_url(registry, "https://packages.example/pkg.zip", resolver=resolver,
                         transport=_serve(b"nope", status=404))
    assert "HTTP 404" in str(exc.value)


def test_a_member_that_escapes_the_package_is_refused(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = _archive({"SKILL.md": SKILL.format(name="evil", description="x", version="1", body="x"),
                     "../../escaped.txt": "should never be written"})
    with pytest.raises(RemoteSkillError) as exc:
        install_from_url(registry, "https://packages.example/evil.zip", resolver=resolver,
                         transport=_serve(body))
    assert "escapes the package" in str(exc.value)
    assert not (tmp_path / "escaped.txt").exists()


def test_an_absolute_member_path_is_refused(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = _archive({"SKILL.md": SKILL.format(name="evil", description="x", version="1", body="x"),
                     "/etc/passwd": "x"})
    with pytest.raises(RemoteSkillError) as exc:
        install_from_url(registry, "https://packages.example/evil.zip", resolver=resolver,
                         transport=_serve(body))
    assert "absolute path" in str(exc.value)


def test_an_archive_without_a_skill_document_is_refused(tmp_path):
    registry, resolver = _installer(tmp_path)
    body = _archive({"README.md": "no skill here"})
    with pytest.raises(RemoteSkillError) as exc:
        install_from_url(registry, "https://packages.example/pkg.zip", resolver=resolver,
                         transport=_serve(body))
    assert "SKILL.md" in str(exc.value)


def test_a_download_that_is_not_a_zip_and_not_markdown_too_large_is_refused(tmp_path):
    destination = tmp_path / "out"
    with pytest.raises(RemoteSkillError) as exc:
        fetch_package("https://packages.example/big.txt", destination, resolver=_resolver(PUBLIC),
                      transport=_serve(b"x" * 300_000, content_type="text/plain"))
    assert "neither a zip archive nor a single SKILL.md" in str(exc.value)


def test_a_compression_bomb_is_refused_before_extraction(tmp_path):
    """Twenty megabytes of zeros compresses to almost nothing; the budget is on expansion."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("SKILL.md", SKILL.format(name="bomb", description="x", version="1", body="x"))
        bundle.writestr("padding.bin", b"\0" * (70 * 1024 * 1024))
    body = buffer.getvalue()
    assert len(body) < MAX_ARCHIVE_BYTES          # it fits the download budget...

    registry, resolver = _installer(tmp_path)
    with pytest.raises(RemoteSkillError) as exc:  # ...but not the expansion budget
        install_from_url(registry, "https://packages.example/bomb.zip", resolver=resolver,
                         transport=_serve(body))
    assert "unpacked size limit" in str(exc.value) or "larger than one package file" in str(exc.value)


def test_an_empty_download_is_refused(tmp_path):
    with pytest.raises(RemoteSkillError) as exc:
        fetch_package("https://packages.example/empty.zip", tmp_path / "out",
                      resolver=_resolver(PUBLIC), transport=_serve(b""))
    assert "empty" in str(exc.value)


# ------------------------------------------------------------------ it is still a normal skill


def test_a_fetched_skill_behaves_like_any_other_once_reviewed(tmp_path):
    registry, resolver = _installer(tmp_path / "reg")
    body = _archive({"SKILL.md": SKILL.format(name="shared", description="Shared.", version="1",
                                              body="Read the workspace.")})
    install_from_url(registry, "https://packages.example/shared.zip", resolver=resolver, transport=_serve(body))
    registry.trust("shared")
    bot = Bot(name="remote-bot", model="mock/demo", tools=["files"], skills=["shared"],
              approval_mode=ApprovalMode.auto)
    resolved = registry.effective_for_bot(bot)
    assert [skill.name for skill in resolved.catalog] == ["shared"]


# ------------------------------------------------------------------ the API surface


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from hutch.server.app import create_app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "api-state"))
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_the_fetch_route_installs_untrusted_and_reports_provenance(api_client, monkeypatch):
    body = _archive({"SKILL.md": SKILL.format(name="published", description="From the network.",
                                              version="3.0", body="Do it.")})
    from hutch.netguard import safe_get as real_safe_get

    def with_local_egress(url, **kwargs):
        kwargs.pop("resolver", None)
        kwargs.pop("transport", None)
        return real_safe_get(url, resolver=_resolver(PUBLIC), transport=_serve(body), **kwargs)

    monkeypatch.setattr("hutch.skill_remote.safe_get", with_local_egress)
    response = api_client.post("/api/v1/skills/fetch", json={"url": "https://packages.example/pkg.zip"})
    assert response.status_code == 201, response.text
    detail = response.json()
    assert detail["name"] == "published"
    assert detail["trusted"] is False
    assert detail["provenance"]["host"] == "packages.example"

    review = api_client.get("/api/v1/skills/published").json()
    assert review["trusted"] is False
    assert review["source"]["kind"] == "url"


def test_the_fetch_route_refuses_a_private_address(api_client, monkeypatch):
    def refuse(*args, **kwargs):
        raise RemoteSkillError("this URL cannot be fetched: the address is private")

    monkeypatch.setattr("hutch.skill_remote.safe_get", refuse)
    response = api_client.post("/api/v1/skills/fetch", json={"url": "https://internal.example/pkg.zip"})
    assert response.status_code == 422
    assert "cannot be fetched" in response.json()["detail"]
