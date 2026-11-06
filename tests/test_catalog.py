"""The assistant catalog: presets are reviewable data entries, not code.

Bundled entries live in src/hutch/data/catalog/*.json with a manifest (format, version, publisher,
the assistant they create). Moving the eight presets out of Python must change nothing a person gets:
the digests below were taken from the old constants before they were removed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hutch import catalog
from hutch.catalog import CatalogError, bundled, load_directory, parse_manifest
from hutch.templates import TEMPLATE_INFO, TEMPLATES, gallery, instantiate

# sha256 of [Bot dump without id/timestamps, gallery facts] for each preset, from the code that shipped them
PRESET_DIGESTS = {
  "personal-assistant": "b48d5dfad2d2aceacebdfb5bbae69076ad5c67da9eac6cee3c08f8bac7057d1d",
  "day-planner": "ece56141e4560d4e77c3beab6967ee8a441d2af34c450fd2805b8ed3b6b572ae",
  "inbox-followups": "107f6e16ef9a33ef31beb8c43f3b6773e0758956b282a78761a62dc99aca611a",
  "research-decisions": "8f7e06bc6ac774fc260822e7e7052e1095f48f22488b6a27eea6a0341a3b9e20",
  "project-coordinator": "5f09e3efb044ed7aab671f4cdd1a2cec70ace848f9206a608046c4f5e5c34d95",
  "meeting-followthrough": "7a21f55e2933835578c9e6f97accfb83abec7eca52fc3ae916a1d0d45f5d823b",
  "document-workbench": "da33ec0237462ec19f49e3a3eb75be2ad9b75227b5d595f9b0c2fc9d704c8739",
  "data-brief": "e8a0b858182a0aefb232cfc2094ed1fe737ebe52de7adc065f74adb78496e2a5"
}

DIR = Path(__file__).resolve().parent.parent / "src" / "hutch" / "data" / "catalog"


def _digest(info) -> str:
    bot = info.bot.model_dump(mode="json", exclude={"id", "created_at", "updated_at", "archived"})
    facts = {"category": info.category, "tagline": info.tagline, "reads": info.reads, "produces": info.produces,
             "safety": info.safety, "needs_folder": info.needs_folder}
    return hashlib.sha256(json.dumps([bot, facts], sort_keys=True).encode()).hexdigest()


def test_the_presets_came_out_of_code_unchanged():
    assert sorted(TEMPLATE_INFO) == sorted(PRESET_DIGESTS)
    assert {key: _digest(info) for key, info in TEMPLATE_INFO.items()} == PRESET_DIGESTS


def test_the_catalog_keeps_the_original_order():
    assert list(TEMPLATE_INFO) == ["personal-assistant", "day-planner", "inbox-followups", "research-decisions",
                                   "project-coordinator", "meeting-followthrough", "document-workbench", "data-brief"]


def test_the_presets_are_loaded_from_manifests_not_defined_in_python():
    source = (Path(catalog.__file__).parent / "templates.py").read_text(encoding="utf-8")
    assert "_add(" not in source and "instructions=(" not in source, "presets must live in data/catalog/*.json"
    assert len(list(DIR.glob("*.json"))) == len(PRESET_DIGESTS)


def test_every_entry_carries_provenance():
    loaded = catalog.bundled()
    assert loaded.diagnostics == []
    assert len(loaded.entries) == len(PRESET_DIGESTS)
    for item in loaded.entries:
        assert item.source == "bundled" and item.entry.publisher == "Hutch"
        assert item.entry.version.count(".") == 2 and len(item.content_hash) == 64


def test_content_hash_ignores_formatting_and_changes_with_content():
    data = json.loads((DIR / "day-planner.json").read_text(encoding="utf-8"))
    reformatted = json.dumps(data, indent=4, sort_keys=True)
    assert catalog.content_hash(json.loads(reformatted)) == catalog.content_hash(data)
    data["assistant"]["instructions"] += " Extra."
    assert catalog.content_hash(data) != catalog.content_hash(json.loads((DIR / "day-planner.json").read_text(encoding="utf-8")))


def test_gallery_and_instantiate_still_work_for_cli_api_and_dashboard():
    assert [category for category, _ in gallery()] == ["Personal", "Research", "Operations", "Documents", "Analytics"]
    first = instantiate("day-planner", "my-planner")
    second = instantiate("day-planner", "other-planner")
    assert first.id != second.id and first.template == "day-planner" and first.name == "my-planner"
    assert TEMPLATES["day-planner"].tools == ["files", "memory"]


def _valid() -> dict:
    return json.loads((DIR / "day-planner.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d.update(format="hutch.catalog/9"), "format"),
    (lambda d: d.update(id="Bad Id"), "id"),
    (lambda d: d["assistant"].update(tools=["files", "definitely-not-a-tool"]), "tool"),
    (lambda d: d.update(surprise="field"), "extra"),
    (lambda d: d["assistant"].update(instructions="x" * 20001), "instructions"),
    (lambda d: d.update(version="one"), "version"),
    (lambda d: d["assistant"].update(command_rules=[{"verdict": "maybe", "match": "ls*"}]), "verdict"),
])
def test_an_invalid_manifest_is_refused_with_a_reason(mutate, expected):
    data = _valid()
    mutate(data)
    with pytest.raises(CatalogError) as caught:
        parse_manifest(data)
    assert expected in str(caught.value).lower()


def test_a_bad_file_becomes_a_diagnostic_not_a_crash(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "wrong.json").write_text(json.dumps({"format": "hutch.catalog/1"}), encoding="utf-8")
    good = _valid()
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "dup.json").write_text(json.dumps(good), encoding="utf-8")
    loaded = load_directory(tmp_path, "yours")
    assert [item.entry.id for item in loaded.entries] == ["day-planner"]
    assert len(loaded.diagnostics) == 3 and any("duplicate" in line for line in loaded.diagnostics)


def test_a_catalog_view_name_cannot_be_an_entry_id():
    manifest = next(item.entry for item in bundled().entries if item.entry.id == "day-planner").model_dump(mode="json")
    manifest["id"] = "skills"
    with pytest.raises(CatalogError, match="name of a catalog view"):
        parse_manifest(manifest)
