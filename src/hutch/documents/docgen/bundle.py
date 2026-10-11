"""ZIP bundle generator: named multi-file bundles with an audited manifest.

A bundle is a set of text entries plus optional base64-carried binary assets, wrapped
with an auto-generated ``manifest.json`` recording each entry's size and SHA-256. Paths
are validated as safe relative POSIX paths (no absolute paths, no ``..``, no duplicate
names), and the entry count and total uncompressed size are capped at write time —
the same bounds the operations docs publish. Validation re-opens the finished archive
with :mod:`zipfile` (CRC test included) and audits it against the manifest, so a bundle
that reaches storage is provably complete and uncorrupted (failure classes E14/E5).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import zipfile
from typing import Any

from . import DocumentGenerationError, GeneratedDocument, register

MAX_BUNDLE_ENTRIES = 512
MAX_BUNDLE_BYTES = 64_000_000
MAX_ENTRY_BYTES = 32_000_000
MAX_ENTRY_NAME_CHARS = 200
_PREVIEW_ENTRIES = 200


def _entry_name(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise DocumentGenerationError("every bundle entry needs a non-empty name")
    name = raw.replace("\\", "/").strip()
    parts = [part for part in name.split("/") if part not in ("", ".")]
    if (not parts or any(part == ".." for part in parts) or raw.startswith("/")
            or name.endswith("/")):
        # a trailing slash expresses a directory: ambiguous, so rejected rather
        # than silently becoming a file
        raise DocumentGenerationError(f"bundle entry name is not a safe relative path: {raw!r}")
    name = "/".join(parts)
    if len(name) > MAX_ENTRY_NAME_CHARS or name.endswith("/"):
        raise DocumentGenerationError(f"bundle entry name is too long or a directory: {raw!r}")
    return name


def _entry_payload(entry: dict[str, Any], index: int) -> tuple[bytes, str]:
    name = entry.get("name", f"entry-{index}")
    if not isinstance(entry, dict):
        raise DocumentGenerationError("each bundle entry must be an object with a name")
    if "text" in entry:
        text = entry["text"]
        if not isinstance(text, str):
            raise DocumentGenerationError(f"bundle entry {name!r} text must be a string")
        return text.encode("utf-8"), "utf-8"
    if "bytes_base64" in entry:
        encoded = entry["bytes_base64"]
        if not isinstance(encoded, str):
            raise DocumentGenerationError(f"bundle entry {name!r} bytes_base64 must be a string")
        # base64 expands 4:3, so bound the decoded size before decoding at all
        if len(encoded) > MAX_ENTRY_BYTES // 3 * 4:
            raise DocumentGenerationError(f"bundle entry {name!r} exceeds the 32 MB entry limit")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise DocumentGenerationError(f"bundle entry {name!r} is not valid base64") from None
        if len(data) > MAX_ENTRY_BYTES:
            raise DocumentGenerationError(f"bundle entry {name!r} exceeds the 32 MB entry limit")
        return data, "base64"
    raise DocumentGenerationError(
        f"bundle entry {name!r} needs either text or bytes_base64")


@register("zip")
def _gen_zip(spec: dict[str, Any]) -> GeneratedDocument:
    entries = spec.get("files")
    if not isinstance(entries, list) or not entries:
        raise DocumentGenerationError('zip content must be {"files": [{name, text | bytes_base64}, ...]}')
    if len(entries) > MAX_BUNDLE_ENTRIES:
        raise DocumentGenerationError(f"bundle exceeds {MAX_BUNDLE_ENTRIES} entries")
    seen: set[str] = set()
    manifest_entries: list[dict[str, Any]] = []
    payload: dict[str, bytes] = {}
    total = 0
    binary_entries = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise DocumentGenerationError("each bundle entry must be an object with a name")
        name = _entry_name(entry.get("name"))
        key = name.lower()
        if key in seen:
            raise DocumentGenerationError(f"bundle has duplicate entry names: {name!r}")
        seen.add(key)
        data, encoding = _entry_payload(entry, index)
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise DocumentGenerationError("bundle exceeds the 64 MB uncompressed limit")
        seen_name = name
        payload[seen_name] = data
        binary_entries += encoding == "base64"
        manifest_entries.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                 "encoding": encoding})
    manifest = {
        "generator": "hutch docgen zip 1.0",
        "entry_count": len(manifest_entries),
        "total_bytes": total,
        "entries": manifest_entries,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload[name])
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    data = buffer.getvalue()
    # independent reopen: CRC test, then audit the archive against the manifest
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise DocumentGenerationError("the written bundle failed its CRC check")
        names = set(archive.namelist())
        expected = set(payload) | {"manifest.json"}
        if names != expected:
            raise DocumentGenerationError("the written bundle does not match its entry list")
        reopened = json.loads(archive.read("manifest.json"))
        if reopened.get("entry_count") != len(payload) or reopened.get("total_bytes") != total:
            raise DocumentGenerationError("the bundle manifest does not describe the archive")
    findings: list[dict[str, Any]] = []
    if binary_entries:
        findings.append({"code": "bundle_binary_entries", "detail":
                         f"{binary_entries} binary entr(y/ies) were size- and CRC-checked but not content-validated"})
    preview = [{"name": item["name"], "bytes": item["bytes"]} for item in manifest_entries[:_PREVIEW_ENTRIES]]
    return GeneratedDocument(
        data=data, generator="hutch docgen zip 1.0 (zipfile)", validation_state="passed",
        findings=findings, preview_mode="structure",
        preview_data={"kind": "bundle", "entries": preview, "total_bytes": total,
                      "entry_count": len(manifest_entries)},
        page_count=None,
    )
