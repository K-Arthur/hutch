"""Export maps an assistant to the catalog format behind a sanitising checklist; import stays inert.

The share flow must never leak a credential, must not include memory/history/schedules by construction, and
must produce a manifest that imports again. Import returns an unsaved setup configuration; the normal review
creates the person's own copy.
"""

from __future__ import annotations

from hutch.catalog import parse_manifest
from hutch.catalog_export import (
    OMITTED,
    configuration_from_manifest,
    permissions_from_manifest,
    review_export,
)
from hutch.models import Bot, CommandRule

BUNDLED = "day-planner"


def _bot(**kw) -> Bot:
    values = dict(name="release-notes", display_name="Release Notes", instructions="Summarize the changes.",
                  tools=["files", "memory"], preset="planner",
                  command_rules=[CommandRule(verdict="deny", match="curl*")])
    values.update(kw)
    return Bot(**values)


def test_export_produces_a_valid_manifest_and_nothing_private():
    review = review_export(_bot(), publisher="Kev", version="1.2.0")
    assert review.blocked == [] and review.warnings == []
    assert review.manifest is not None
    entry = parse_manifest(review.manifest)
    assert entry.id == "release-notes" and entry.name == "Release Notes"
    assert entry.publisher == "Kev" and entry.version == "1.2.0"
    assert entry.assistant.tools == ["files", "memory"]
    assert entry.assistant.command_rules[0].verdict == "deny"
    assert review.omitted == list(OMITTED) and review.checklist
    assert review.content_hash and len(review.content_hash) == 64


def test_a_credential_shape_blocks_the_export():
    review = review_export(_bot(instructions="Use sk-abcdefghijklmnopqrstuvwx for the API."))
    assert review.manifest is None and review.blocked
    assert "credential" in review.blocked[0]


def test_private_shapes_are_warnings_the_person_must_acknowledge():
    review = review_export(_bot(instructions="Read /home/kev/customers.csv and mail ada@example.com "
                                            "the summary at https://internal.example.com/report."))
    assert review.manifest is not None
    assert any("URL" in line for line in review.warnings)
    assert any("e-mail" in line or "email" in line for line in review.warnings)
    assert any("absolute local path" in line for line in review.warnings)


def test_import_configuration_is_an_unsaved_bot_draft():
    manifest = review_export(_bot()).manifest
    configuration = configuration_from_manifest(manifest)
    assert configuration["name"] == "release-notes" and configuration["display_name"] == "Release Notes"
    assert configuration["instructions"] == "Summarize the changes."
    assert configuration["tools"] == ["files", "memory"]
    assert configuration["model"] == "" and configuration["memory_enabled"] is False
    assert configuration["cron"] == "" and configuration["approval_mode"] == "ask"
    permissions = permissions_from_manifest(manifest)
    assert permissions["tools"] == ["files", "memory"] and permissions["content_hash"]


def test_shell_is_called_out_as_elevated():
    manifest = review_export(_bot(tools=["files", "shell"])).manifest
    permissions = permissions_from_manifest(manifest)
    assert permissions["elevated_tools"] == ["shell"]
