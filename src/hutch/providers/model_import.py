"""Import a local GGUF into Ollama through the runtime's own blob and create APIs.

Ollama does not accept a path in ``/api/create``. The documented flow is: compute the
file's SHA-256, ask whether the blob exists (``HEAD /api/blobs/<digest>``), upload it only
when it does not (``POST``), then create a model from the original filename and digest.
Ollama verifies the digest again on upload, so Hutch's hash is a pre-upload check rather
than a replacement for the runtime's.

The import is deliberately single-file. A split GGUF needs every shard under its original
filename; silently importing one shard produces a broken model, so a split filename is
refused with the command that merges it. Licenses are read from the sidecar file if one
exists, or supplied explicitly; a missing license is reported as missing, never guessed.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .base import ModelMeta, ProviderError
from .install_errors import redact_secrets
from .model_install import validate_model_name
from .model_names import same_model

GGUF_MAGIC = b"GGUF"
_HEADER_BYTES = 24
_SPLIT_NAME = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)
_LICENSE_NAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "COPYING.txt")
_MAX_LICENSE_BYTES = 64 * 1024


@dataclass(frozen=True)
class GgufInfo:
    path: Path
    size_bytes: int
    sha256: str
    version: int


@dataclass
class ImportResult:
    model: str
    path: str
    size_bytes: int
    sha256: str
    digest: str
    license_text: str = ""
    license_source: str = "none"      # provided | sidecar: <file> | runtime | none
    capabilities: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"model": self.model, "path": self.path, "size_bytes": self.size_bytes,
                "sha256": self.sha256, "digest": self.digest,
                "license": self.license_text, "license_source": self.license_source,
                "capabilities": list(self.capabilities), "details": dict(self.details)}


def _checked_path(raw: str) -> Path:
    candidate = Path(str(raw or "")).expanduser()
    if not candidate.is_absolute():
        raise ValueError("use an absolute path to the .gguf file")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"{candidate} does not exist") from None
    except OSError as exc:
        raise ValueError(f"could not read {candidate}: {exc}") from None
    if not resolved.is_file():
        raise ValueError("choose a regular .gguf file, not a directory or device")
    for root in ("/proc", "/sys", "/dev"):
        if resolved.is_relative_to(root):
            raise ValueError("choose a model file outside /proc, /sys or /dev")
    if resolved.suffix.casefold() != ".gguf":
        raise ValueError("choose a file whose name ends in .gguf")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_gguf(path: str) -> GgufInfo:
    """Validate the GGUF header and hash the whole file; the runtime verifies the rest."""
    resolved = _checked_path(path)
    size = resolved.stat().st_size
    if size <= _HEADER_BYTES:
        raise ValueError("the file is too small to be a GGUF model")
    if _SPLIT_NAME.search(resolved.name):
        raise ValueError("split GGUF files are not supported by this form; merge the shards "
                         "with llama.cpp's gguf-split, then import the merged file")
    with resolved.open("rb") as handle:
        header = handle.read(_HEADER_BYTES)
    if len(header) < _HEADER_BYTES or header[:4] != GGUF_MAGIC:
        raise ValueError("the file does not start with the GGUF magic bytes")
    version, tensor_count, kv_count = struct.unpack("<IQQ", header[4:_HEADER_BYTES])
    if version not in (2, 3):
        raise ValueError(f"GGUF version {version} is not supported; use a version 2 or 3 file")
    if tensor_count == 0:
        raise ValueError("the GGUF header reports no tensors")
    return GgufInfo(resolved, size, _sha256(resolved), version)


def _expected_digest(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    if text and not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError("an expected checksum must be a SHA-256 digest (64 hex characters)")
    return text


def _sidecar_license(path: Path) -> tuple[str, str]:
    candidates = [path.with_name(f"{path.stem}.LICENSE"),
                  path.with_name(f"{path.stem}.LICENSE.txt")]
    candidates += [path.with_name(name) for name in _LICENSE_NAMES]
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            text = candidate.read_text("utf-8", "replace")[:_MAX_LICENSE_BYTES].strip()
        except OSError:
            continue
        if text:
            return text, candidate.name
    return "", ""


def _details(meta: Optional[ModelMeta]) -> dict[str, Any]:
    if meta is None:
        return {}
    return {"family": meta.family, "quant": meta.quant, "params_b": meta.params_b,
            "max_context": meta.max_context, "size_bytes": meta.size_bytes}


def _provider_name(provider: Any) -> str:
    return getattr(provider, "name", "ollama")


def _installed_models(provider: Any) -> list[ModelMeta]:
    try:
        return list(provider.list_models())
    except Exception as exc:
        raise ProviderError("unreachable", f"could not read the runtime's model list: {exc}",
                            provider=_provider_name(provider)) from None


def _license_choice(license_text: Optional[str], path: Path) -> tuple[str, str]:
    supplied = (license_text or "").strip()
    if supplied:
        return supplied, "provided"
    supplied, sidecar_name = _sidecar_license(path)
    return supplied, f"sidecar: {sidecar_name}" if supplied else ""


def _create_with_blob(provider: Any, model: str, info: GgufInfo, digest: str, supplied: str) -> None:
    try:
        if not provider.blob_exists(digest):
            provider.put_blob(digest, info.path)
        events = provider.create_model(model, {info.path.name: digest},
                                       license_text=supplied or "", parameters=None)
        for event in events:
            if event.get("error"):
                raise ProviderError("other", redact_secrets(str(event["error"])),
                                    provider=_provider_name(provider))
    except ProviderError as exc:
        raise ProviderError(exc.kind, redact_secrets(str(exc)), provider=exc.provider,
                            status=exc.status) from None
    except OSError as exc:
        raise ProviderError("other", redact_secrets(f"could not import {info.path.name}: {exc}"),
                            provider=_provider_name(provider)) from None


def _confirm_imported(provider: Any, model: str) -> None:
    try:
        present = any(same_model(model, meta.name) for meta in provider.list_models())
    except Exception as exc:
        raise ProviderError("unreachable", f"the runtime did not list the imported model: {exc}",
                            provider=_provider_name(provider)) from None
    if not present:
        raise ProviderError("other", "the runtime reported success but does not list the imported model",
                            provider=_provider_name(provider))


def _show_meta(provider: Any, model: str) -> Optional[ModelMeta]:
    try:
        return provider.show(model)
    except Exception:
        return None


def _license_source(supplied_source: str, runtime_license: str) -> str:
    if supplied_source:
        return supplied_source
    return "runtime" if runtime_license else "none"


def import_local_model(provider: Any, path: str, name: str, *, expected_sha256: Optional[str] = None,
                       license_text: Optional[str] = None) -> ImportResult:
    """Import one local GGUF and confirm it in the runtime's registry."""
    model = validate_model_name(name)
    info = inspect_gguf(path)
    expected = _expected_digest(expected_sha256)
    if expected and not hmac.compare_digest(expected, info.sha256):
        raise ValueError(f"the file's SHA-256 is {info.sha256[:16]}..., which does not match "
                         f"the expected {expected[:16]}...")
    if any(same_model(model, meta.name) for meta in _installed_models(provider)):
        raise ProviderError("bad_request", f"{model} is already installed; remove it before importing",
                            provider=_provider_name(provider))

    supplied, supplied_source = _license_choice(license_text, info.path)
    digest = f"sha256:{info.sha256}"
    _create_with_blob(provider, model, info, digest, supplied)
    _confirm_imported(provider, model)

    meta = _show_meta(provider, model)
    runtime_license = (meta.license if meta is not None else "").strip()
    return ImportResult(model=model, path=str(info.path), size_bytes=info.size_bytes,
                        sha256=info.sha256, digest=digest,
                        license_text=runtime_license or supplied,
                        license_source=_license_source(supplied_source, runtime_license),
                        capabilities=list(meta.capabilities) if meta is not None else [],
                        details=_details(meta))
