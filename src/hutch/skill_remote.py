"""Installing a skill package from a URL, as reviewable material rather than a trusted artifact.

A skill can arrive as a directory on disk or as a bundle Hutch ships. A third form is the useful
one for sharing: a package published at a URL. That is also the form that can hand Hutch a
hostile archive, so the rules here are about what a fetched package is *not* allowed to do:

* the fetch goes through ``netguard``, so a URL that resolves to a private address, or redirects
  to one, is refused before any body is read;
* the archive is read in memory with an explicit byte budget, so a compression bomb costs memory
  it declared rather than memory it expanded to;
* entries are written one at a time through a path check, so no member can escape the staging
  directory, create a symlink, or overwrite a file that already exists;
* the package lands **untrusted**. Fetching proves where bytes came from, nothing more.

Provenance is recorded with the install: the URL requested, the URL that was actually reached
after redirects, the archive digest, the size, and the host. That is what an operator needs to
answer "who gave me this" later, when the answer matters.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Optional
from urllib.parse import urlsplit

from .models import iso, utcnow
from .netguard import NetGuardError, safe_get
from .skills import SKILL_FILENAME, SkillError

#: A skill package is text and small references. Anything larger is not a skill.
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
#: Members, with headroom over the registry's own file cap so the registry still has the last word.
MAX_MEMBERS = 2_000
#: Declared expansion budget. A package that expands past this is refused before extraction.
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
#: Per-member ceiling, so one huge entry cannot consume the whole budget.
MAX_MEMBER_BYTES = 16 * 1024 * 1024
#: A single SKILL.md is accepted, but not an unbounded one.
MAX_STANDALONE_BYTES = 256 * 1024


class RemoteSkillError(SkillError):
    """A remote package could not be fetched or safely unpacked."""


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _safe_member(name: str) -> PurePosixPath:
    """Normalise one archive member, refusing anything that could escape the staging root."""
    if not name or "\x00" in name or "\\" in name:
        raise RemoteSkillError("the archive contains an invalid entry name")
    relative = PurePosixPath(name)
    if relative.is_absolute():
        raise RemoteSkillError("the archive contains an absolute path")
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RemoteSkillError("the archive contains a path that escapes the package")
    return relative


def _extract(body: bytes, destination: Path) -> dict[str, Any]:
    """Write archive members under ``destination`` without trusting any of their metadata."""
    written = 0
    declared = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        raise RemoteSkillError("the download is not a readable zip archive") from None
    with archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise RemoteSkillError(f"the archive contains more than {MAX_MEMBERS} entries")
        for member in members:
            if member.is_dir():
                continue
            relative = _safe_member(member.filename)
            declared += member.file_size
            if declared > MAX_EXPANDED_BYTES:
                raise RemoteSkillError("the archive expands past Hutch's unpacked size limit")
            if member.file_size > MAX_MEMBER_BYTES:
                raise RemoteSkillError(f"{relative.as_posix()} is larger than one package file may be")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            # A member may not arrive through an existing symlink, even one it created earlier.
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise RemoteSkillError(f"{relative.as_posix()} would overwrite a non-regular entry")
            with archive.open(member) as source:
                data = source.read(MAX_MEMBER_BYTES + 1)
            if len(data) > MAX_MEMBER_BYTES:
                raise RemoteSkillError(f"{relative.as_posix()} grew while being unpacked")
            target.write_bytes(data)
            written += 1
    return {"files": written, "expanded_bytes": declared}


def fetch_package(url: str, destination: Path, *, resolver=None, transport=None) -> dict[str, Any]:
    """Download and unpack one package, returning the provenance to record with the install.

    ``resolver`` and ``transport`` exist so tests can point at a local server without weakening
    the egress rules the production path uses.
    """
    target = url.strip()
    if not target:
        raise RemoteSkillError("Enter the URL of a skill package")
    try:
        fetched = safe_get(target, max_bytes=MAX_ARCHIVE_BYTES, resolver=resolver, transport=transport)
    except NetGuardError as exc:
        raise RemoteSkillError(f"this URL cannot be fetched: {exc}") from None
    if not fetched.ok:
        raise RemoteSkillError(f"the package could not be downloaded (HTTP {fetched.status})")
    if fetched.truncated:
        raise RemoteSkillError(f"the package is larger than Hutch's {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB limit")
    body = fetched.body or fetched.text.encode("utf-8")
    if not body:
        raise RemoteSkillError("the download was empty")
    digest = hashlib.sha256(body).hexdigest()

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    content_type = (fetched.headers.get("content-type") or "").lower()
    if body[:2] == b"PK" or "zip" in content_type:
        extracted = _extract(body, destination)
        kind = "archive"
    else:
        # A single file is accepted only when it is the instruction document itself.
        if len(body) > MAX_STANDALONE_BYTES:
            raise RemoteSkillError("the download is neither a zip archive nor a single SKILL.md")
        (destination / SKILL_FILENAME).write_bytes(body)
        extracted = {"files": 1, "expanded_bytes": len(body)}
        kind = "skill_md"

    if not (destination / SKILL_FILENAME).is_file():
        raise RemoteSkillError(f"the package does not contain {SKILL_FILENAME} at its root")
    return {
        "kind": kind,
        "url": target,
        "final_url": fetched.url or target,
        "host": _host(fetched.url or target),
        "sha256": digest,
        "bytes": len(body),
        "redirects": list(fetched.redirects),
        "fetched_at": iso(utcnow()),
        **extracted,
    }


def install_from_url(registry, url: str, *, staging_root: Optional[Path] = None,
                     resolver=None, transport=None, replace: bool = False) -> dict:
    """Fetch a package and install it untrusted, describing where it came from.

    The record is what the review surface shows, and what an operator can check later: the bytes
    were fetched from a named host at a named time and hash. Nothing about it implies review.

    ``replace`` re-fetches over an existing install. It deliberately goes through the registry's
    own install path with ``allow_existing``, because that path writes ``trust: None`` and
    ``enabled: False`` for any new bytes: a fresh download never inherits the review the previous
    one earned. Anyone can publish a new version at the same URL.
    """
    import tempfile

    root = staging_root or (Path(registry.state_dir) / "skill-downloads")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="fetch-", dir=root) as staging:
        provenance = fetch_package(url, Path(staging), resolver=resolver, transport=transport)
        # ``_install`` rather than ``install_path``: the fetched directory is temporary, so the
        # recorded source has to be the URL, and replacement must reset trust. Both are what the
        # private entry point does and what no public method accepts together.
        detail = registry._install(Path(staging), {"kind": "url", "detail": provenance["final_url"],
                                                   "scope": "remote"},
                                   allow_existing=replace)
    detail["provenance"] = provenance
    detail["review_required"] = detail.get("trusted") is not True
    return detail


__all__ = ["MAX_ARCHIVE_BYTES", "RemoteSkillError", "fetch_package", "install_from_url"]
