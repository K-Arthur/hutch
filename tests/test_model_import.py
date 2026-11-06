"""Local GGUF import: header check, digest, blob reuse, license and confirmation."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from hutch.providers.base import ModelMeta, ProviderError
from hutch.providers.model_import import import_local_model, inspect_gguf


def make_gguf(tmp_path: Path, name: str = "tiny.gguf", *, magic: bytes = b"GGUF",
              version: int = 3, tensors: int = 1) -> Path:
    data = magic + struct.pack("<IQQ", version, tensors, 0) + b"\0" * 64
    path = tmp_path / name
    path.write_bytes(data)
    return path


class FakeImportProvider:
    name = "ollama"

    def __init__(self, models: list[ModelMeta] | None = None, license: str = "", fail: str = ""):
        self.models = list(models or [])
        self.license = license
        self.fail = fail
        self.blobs: set[str] = set()
        self.uploaded: list[tuple[str, str]] = []
        self.created: list[tuple[str, dict[str, str], str, dict | None]] = []

    def list_models(self):
        return list(self.models)

    def blob_exists(self, digest: str) -> bool:
        return digest in self.blobs

    def put_blob(self, digest: str, path: Path) -> None:
        self.uploaded.append((digest, Path(path).name))
        self.blobs.add(digest)

    def create_model(self, model, files, *, license_text="", parameters=None):
        self.created.append((model, dict(files), license_text, parameters))
        if self.fail:
            yield {"error": self.fail}
            return
        yield {"status": "parsing GGUF"}
        yield {"status": "success"}
        self.models.append(ModelMeta(name=model, license=self.license, capabilities=["tools"], family="llama"))

    def show(self, model):
        return next((meta for meta in self.models if meta.name == model), None)


def test_import_uploads_the_blob_and_confirms_the_model(tmp_path):
    path = make_gguf(tmp_path)
    provider = FakeImportProvider(license="Apache-2.0")
    result = import_local_model(provider, str(path), "imported:1b")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.model == "imported:1b"
    assert result.sha256 == expected
    assert result.digest == f"sha256:{expected}"
    assert provider.uploaded == [(result.digest, "tiny.gguf")]
    assert provider.created[0][1] == {"tiny.gguf": result.digest}
    assert result.license_text == "Apache-2.0"
    assert result.license_source == "runtime"
    assert result.capabilities == ["tools"]
    assert result.details["family"] == "llama"


def test_an_existing_blob_is_not_uploaded_again(tmp_path):
    path = make_gguf(tmp_path)
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    provider = FakeImportProvider()
    provider.blobs.add(digest)
    result = import_local_model(provider, str(path), "imported:1b")
    assert result.digest == digest
    assert provider.uploaded == []


def test_a_checksum_mismatch_refuses_before_any_upload(tmp_path):
    path = make_gguf(tmp_path)
    provider = FakeImportProvider()
    with pytest.raises(ValueError, match="does not match"):
        import_local_model(provider, str(path), "imported:1b", expected_sha256="0" * 64)
    assert provider.uploaded == []
    assert provider.created == []


def test_a_non_gguf_file_is_refused(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"not a gguf at all" + b"\0" * 64)
    with pytest.raises(ValueError, match="magic bytes"):
        import_local_model(FakeImportProvider(), str(path), "imported:1b")


def test_a_file_without_the_gguf_extension_is_refused(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"GGUF" + b"\0" * 80)
    with pytest.raises(ValueError, match="ends in .gguf"):
        inspect_gguf(str(path))


def test_a_missing_file_is_a_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_gguf(str(tmp_path / "absent.gguf"))


def test_a_split_shard_is_refused_with_the_merge_hint(tmp_path):
    path = make_gguf(tmp_path, "model-00001-of-00002.gguf")
    with pytest.raises(ValueError, match="split GGUF"):
        inspect_gguf(str(path))


def test_an_unsupported_gguf_version_is_refused(tmp_path):
    path = make_gguf(tmp_path, version=1)
    with pytest.raises(ValueError, match="version 1"):
        inspect_gguf(str(path))


def test_a_file_with_no_tensors_is_refused(tmp_path):
    path = make_gguf(tmp_path, tensors=0)
    with pytest.raises(ValueError, match="no tensors"):
        inspect_gguf(str(path))


def test_a_sidecar_license_is_read_and_named(tmp_path):
    path = make_gguf(tmp_path)
    (tmp_path / "tiny.LICENSE").write_text("MIT License\n\nCopyright someone", "utf-8")
    provider = FakeImportProvider()
    result = import_local_model(provider, str(path), "imported:1b")
    assert result.license_source == "sidecar: tiny.LICENSE"
    assert "MIT License" in result.license_text
    assert provider.created[0][2] == result.license_text


def test_a_provided_license_is_sent_and_reported(tmp_path):
    path = make_gguf(tmp_path)
    provider = FakeImportProvider()
    result = import_local_model(provider, str(path), "imported:1b", license_text="CC-BY-4.0")
    assert result.license_source == "provided"
    assert provider.created[0][2] == "CC-BY-4.0"


def test_a_runtime_error_is_raised_without_its_secret(tmp_path):
    path = make_gguf(tmp_path)
    provider = FakeImportProvider(fail="unauthorized key=SUPERSECRET123")
    with pytest.raises(ProviderError) as excinfo:
        import_local_model(provider, str(path), "imported:1b")
    assert "SUPERSECRET123" not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


def test_an_already_installed_name_is_refused_before_reading_the_blob(tmp_path):
    path = make_gguf(tmp_path)
    provider = FakeImportProvider(models=[ModelMeta(name="imported:1b")])
    with pytest.raises(ProviderError, match="already installed"):
        import_local_model(provider, str(path), "imported:1b")
    assert provider.uploaded == []


def test_a_cloud_name_is_refused_before_the_file_is_read(tmp_path):
    path = make_gguf(tmp_path)
    with pytest.raises(ValueError, match="cloud model"):
        import_local_model(FakeImportProvider(), str(path), "gpt-oss:20b-cloud")


def test_the_result_is_plain_json(tmp_path):
    path = make_gguf(tmp_path)
    result = import_local_model(FakeImportProvider(), str(path), "imported:1b")
    payload = result.to_json()
    assert payload["model"] == "imported:1b"
    assert payload["sha256"] == result.sha256
    assert payload["license_source"] == "none"
    assert payload["details"] == {"family": "llama", "quant": "", "params_b": None,
                                  "max_context": None, "size_bytes": None}
