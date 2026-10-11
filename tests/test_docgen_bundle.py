"""ZIP bundle generation: manifest audit, path safety, bounds, and preview shape."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile

import pytest

from hutch.documents.docgen import DocumentGenerationError, generate


def _bundle_spec(**extra):
    return {"files": [
        {"name": "README.md", "text": "# Bundle\n\nGenerated locally.\n"},
        {"name": "data/results.json", "text": json.dumps({"ok": True})},
        {"name": "data/export.csv", "text": "id,total\r\n00123,5\r\n"},
        {"name": "assets/dot.bin", "bytes_base64": base64.b64encode(b"\x00\x01\x02hutch").decode()},
    ], **extra}


def test_bundle_roundtrip_and_manifest_audit():
    result = generate("zip", _bundle_spec())
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        assert archive.testzip() is None, "every entry must pass its CRC check"
        assert set(archive.namelist()) == {
            "README.md", "data/results.json", "data/export.csv", "assets/dot.bin", "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["entry_count"] == 4
        for entry in manifest["entries"]:
            stored = archive.read(entry["name"])
            assert len(stored) == entry["bytes"]
            assert hashlib.sha256(stored).hexdigest() == entry["sha256"]
        assert archive.read("data/export.csv") == b"id,total\r\n00123,5\r\n"
    assert result.validation_state == "passed"
    assert any(f["code"] == "bundle_binary_entries" for f in result.findings)
    assert result.preview_data["kind"] == "bundle" and result.preview_data["entry_count"] == 4


def test_bundle_rejects_unsafe_paths_and_duplicates():
    for bad in ("../evil.txt", "/absolute.txt", "a/../../b.txt", "dir/", ""):
        with pytest.raises(DocumentGenerationError, match="safe relative path|non-empty name"):
            generate("zip", {"files": [{"name": bad, "text": "x"}]})
    with pytest.raises(DocumentGenerationError, match="duplicate"):
        generate("zip", {"files": [{"name": "a.txt", "text": "1"},
                                   {"name": "A.txt", "text": "2"}]})
    with pytest.raises(DocumentGenerationError, match="needs either"):
        generate("zip", {"files": [{"name": "empty.bin"}]})


def test_bundle_rejects_invalid_base64_and_bounds():
    with pytest.raises(DocumentGenerationError, match="base64"):
        generate("zip", {"files": [{"name": "x.bin", "bytes_base64": "not-base64!!"}]})
    with pytest.raises(DocumentGenerationError, match="512 entries"):
        generate("zip", {"files": [{"name": f"f{i}.txt", "text": "x"} for i in range(513)]})
    # entries stay under the per-entry limit while the bundle total crosses 64 MB
    with pytest.raises(DocumentGenerationError, match="64 MB"):
        generate("zip", {"files": [{"name": f"big{i}.bin",
                                    "bytes_base64": base64.b64encode(b"\0" * (22_000_000)).decode()}
                                   for i in range(3)]})
    with pytest.raises(DocumentGenerationError, match="files"):
        generate("zip", {"files": "not-a-list"})


def test_bundle_deterministic_bytes():
    first = generate("zip", _bundle_spec()).data
    second = generate("zip", _bundle_spec()).data
    assert first == second, "same spec must produce byte-identical archives (stable timestamps, order)"
