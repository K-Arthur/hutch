"""What a staged skill update would change, before it is applied.

An update is a write path: it can add a required tool, drop one, widen the declared allowed-tools
or rewrite the instructions. The registry already staged new bytes and re-hashed them before
applying, but it could not say *what differed*, so "review the staged update" meant diffing two
versions by eye. These tests pin the comparison and the API field that exposes it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app
from hutch.skill_update import compare_packages

TEMPLATE = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "{version}"
  hutch.requires-tools: "{tools}"
---

## Steps
{body}
"""


def write_package(directory: Path, *, name="reviewable", description="A skill under review.",
                  version="1.0", tools="files", body="Read the workspace.",
                  extra_files: dict[str, str] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        TEMPLATE.format(name=name, description=description, version=version, tools=tools, body=body),
        encoding="utf-8")
    for relative, content in (extra_files or {}).items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return directory


# ------------------------------------------------------------------ the comparison


def test_identical_packages_report_no_change(tmp_path):
    installed = write_package(tmp_path / "installed")
    staged = write_package(tmp_path / "staged")
    changes = compare_packages(installed, staged)
    assert changes["comparable"] is True
    assert changes["identical"] is True
    assert changes["material"] == []
    assert "identical" in changes["summary"]


def test_an_added_requirement_is_material_and_named(tmp_path):
    installed = write_package(tmp_path / "installed", tools="files")
    staged = write_package(tmp_path / "staged", tools="files, shell")
    changes = compare_packages(installed, staged)
    assert changes["identical"] is False
    assert changes["capabilities"]["requires_tools"] == {"added": ["shell"], "removed": []}
    assert any("shell" in note for note in changes["material"])
    assert "requires the shell" in changes["summary"]


def test_a_removed_requirement_is_reported_too(tmp_path):
    installed = write_package(tmp_path / "installed", tools="files, shell")
    staged = write_package(tmp_path / "staged", tools="files")
    changes = compare_packages(installed, staged)
    assert changes["capabilities"]["requires_tools"] == {"added": [], "removed": ["shell"]}
    assert any("no longer requires" in note for note in changes["material"])


def test_a_new_connection_requirement_is_material(tmp_path):
    installed = write_package(tmp_path / "installed", tools="files")
    staged = write_package(tmp_path / "staged", tools="files")
    text = (staged / "SKILL.md").read_text(encoding="utf-8").replace(
        '  hutch.requires-tools: "files"',
        '  hutch.requires-tools: "files"\n  hutch.requires-connections: "google-calendar"')
    (staged / "SKILL.md").write_text(text, encoding="utf-8")
    changes = compare_packages(installed, staged)
    assert changes["capabilities"]["requires_connections"]["added"] == ["google-calendar"]
    assert any("connection" in note for note in changes["material"])


def test_an_instruction_change_is_reported_without_being_material(tmp_path):
    installed = write_package(tmp_path / "installed", body="Read the workspace.")
    staged = write_package(tmp_path / "staged", body="Read the workspace carefully, then summarise it.")
    changes = compare_packages(installed, staged)
    assert changes["instructions"]["changed"] is True
    assert changes["instructions"]["bytes_to"] > changes["instructions"]["bytes_from"]
    assert changes["material"] == []
    assert "instructions changed" in changes["summary"]


def test_a_same_size_edit_is_still_a_change(tmp_path):
    """Hash, not size and mtime: a restored timestamp must not hide an edit."""
    installed = write_package(tmp_path / "installed", body="AAAA")
    staged = write_package(tmp_path / "staged", body="BBBB")
    os.utime(staged / "SKILL.md", (installed.joinpath("SKILL.md").stat().st_atime,
                                   installed.joinpath("SKILL.md").stat().st_mtime))
    changes = compare_packages(installed, staged)
    assert changes["instructions"]["changed"] is True
    assert changes["identical"] is False


def test_added_and_removed_files_are_listed_with_their_paths(tmp_path):
    installed = write_package(tmp_path / "installed", extra_files={"references/old.md": "old"})
    staged = write_package(tmp_path / "staged", extra_files={"references/new.md": "new"})
    changes = compare_packages(installed, staged)
    assert changes["files"]["added"]["paths"] == ["references/new.md"]
    assert changes["files"]["removed"]["paths"] == ["references/old.md"]
    assert changes["files"]["changed"]["paths"] == []


def test_a_changed_resource_is_listed_as_changed(tmp_path):
    installed = write_package(tmp_path / "installed", extra_files={"templates/a.txt": "one"})
    staged = write_package(tmp_path / "staged", extra_files={"templates/a.txt": "two"})
    changes = compare_packages(installed, staged)
    assert changes["files"]["changed"]["paths"] == ["templates/a.txt"]
    assert changes["files"]["added"]["count"] == 0


def test_a_symlink_is_skipped_rather_than_followed(tmp_path):
    installed = write_package(tmp_path / "installed")
    staged = write_package(tmp_path / "staged")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (staged / "link.txt").symlink_to(outside)
    changes = compare_packages(installed, staged)
    assert "link.txt" not in changes["files"]["added"]["paths"]


def test_a_missing_side_is_reported_as_not_comparable(tmp_path):
    installed = write_package(tmp_path / "installed")
    changes = compare_packages(installed, tmp_path / "gone")
    assert changes["comparable"] is False
    assert "no longer on disk" in changes["reason"]


# ------------------------------------------------------------------ the API surface


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_the_api_reports_what_a_staged_update_changes(client, tmp_path):
    source = write_package(tmp_path / "source", tools="files")
    installed = client.post("/api/v1/skills/install", json={"source": "path", "path": str(source)})
    assert installed.status_code == 201, installed.text
    name = installed.json()["name"]
    assert client.post(f"/api/v1/skills/{name}/trust").status_code == 200

    # The source gains a tool requirement, then stages as an update.
    write_package(source, tools="files, shell")
    staged = client.post(f"/api/v1/skills/{name}/update")
    assert staged.status_code == 200, staged.text

    detail = client.get(f"/api/v1/skills/{name}").json()
    changes = detail["staged_changes"]
    assert changes["comparable"] is True
    assert changes["capabilities"]["requires_tools"]["added"] == ["shell"]
    assert any("shell" in note for note in changes["material"])

    # Applying is a separate, explicit act; the reviewed version stays active until then.
    applied = client.post(f"/api/v1/skills/{name}/update/apply")
    assert applied.status_code == 200, applied.text
    after = client.get(f"/api/v1/skills/{name}").json()
    assert after["staged_update"] is None
    assert "staged_changes" not in after


def test_no_staged_update_means_no_preview_field(client, tmp_path):
    source = write_package(tmp_path / "source")
    installed = client.post("/api/v1/skills/install", json={"source": "path", "path": str(source)})
    name = installed.json()["name"]
    detail = client.get(f"/api/v1/skills/{name}").json()
    assert "staged_changes" not in detail
