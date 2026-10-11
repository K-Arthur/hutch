"""The content-addressed media store: commit protocol, integrity, bounds, and
the no-symlink path discipline (mirrors documents/storage.py's guarantees)."""

from __future__ import annotations

import os
import stat
import struct
import zlib

import pytest

from hutch.media.storage import (EXT_BY_FORMAT, MEDIA_FORMATS, MAX_MEDIA_BYTES,
                                 MAX_MEDIA_PER_JOB, MediaIntegrityError,
                                 MediaStorage, MediaStorageError, new_job_id,
                                 new_media_id, reconcile_media_store,
                                 sanitize_media_name)


def make_png(width: int = 4, height: int = 4) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        blob = struct.pack(">I", len(data)) + tag + data
        return blob + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xde\xad\xbe" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_new_media_id_shape_and_format_tables():
    for _ in range(50):
        assert new_media_id().startswith("media_")
    assert MEDIA_FORMATS == ("png", "jpeg", "webp", "svg+xml", "webm", "mp4", "wav")
    from hutch.media.storage import MIME_BY_FORMAT
    assert MIME_BY_FORMAT == {
        "png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp",
        "svg+xml": "image/svg+xml", "webm": "video/webm", "mp4": "video/mp4",
        "wav": "audio/wav",
    }
    assert EXT_BY_FORMAT["jpeg"] == ".jpg" and EXT_BY_FORMAT["svg+xml"] == ".svg"


def test_sanitize_media_name_keeps_the_canonical_extension():
    assert sanitize_media_name("My Diagram!.svg", "svg+xml") == "My-Diagram.svg"
    assert sanitize_media_name("video.mp4", "webm") == "video.webm"
    assert sanitize_media_name("привет.png", "png") == "png.png"
    with pytest.raises(MediaStorageError, match="unsupported"):
        sanitize_media_name("x.gif", "gif")


def test_commit_protocol_stage_journal_promote_row(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    staged = storage.stage_bytes(new_job_id(), "png", "chart.png", make_png())
    calls = []

    def insert_row():
        calls.append(1)

    rel_path = storage.commit(staged, media_id, 1, meta={"kind": "image",
                                                         "alt_text": "red squares"},
                              insert_row=insert_row)
    assert calls == [1], "the row insert (the caller's transaction) must run exactly once"
    version_dir = f"v001-{staged.sha256[:8]}"
    assert rel_path == f"{media_id}/{version_dir}/chart.png"
    content = storage.root / media_id / version_dir / "chart.png"
    manifest = storage.root / media_id / version_dir / "manifest.json"
    assert content.is_file() and manifest.is_file()
    assert stat.S_IMODE(content.stat().st_mode) == 0o400, "promoted bytes are read-only"
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o400
    assert stat.S_IMODE((storage.root / media_id).stat().st_mode) == 0o700
    assert stat.S_IMODE(storage.root.stat().st_mode) == 0o700
    assert not (storage.staging / staged.job_id).exists(), "staging is cleared after commit"
    assert not (storage.staging / f"{staged.job_id}.json").exists(), "journal cleared"
    data, loaded = storage.read_version(media_id, 1)
    assert data == make_png()
    assert loaded["sha256"] == staged.sha256 and loaded["mime"] == "image/png"
    assert loaded["kind"] == "image" and loaded["alt_text"] == "red squares"


def test_failed_row_insert_rolls_the_promotion_back(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    staged = storage.stage_bytes(new_job_id(), "png", "a.png", make_png())

    def boom():
        raise RuntimeError("the row insert failed")

    with pytest.raises(RuntimeError):
        storage.commit(staged, media_id, 1, insert_row=boom)
    # Nothing servable remains: the version was never visible, so it must be gone.
    with pytest.raises(MediaStorageError):
        storage.read_version(media_id, 1)


def test_integrity_failure_is_honest_size_and_hash(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    staged = storage.stage_bytes(new_job_id(), "png", "a.png", make_png())
    storage.commit(staged, media_id, 1, insert_row=lambda: None)
    version_dir = f"v001-{staged.sha256[:8]}"
    path = storage.root / media_id / version_dir / "a.png"
    original = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(original[:-1] + b"\x00")
    with pytest.raises(MediaIntegrityError, match="SHA-256"):
        storage.read_version(media_id, 1)
    path.write_bytes(original[:5])
    with pytest.raises(MediaIntegrityError, match="size"):
        storage.read_version(media_id, 1)
    path.unlink()
    with pytest.raises(MediaStorageError, match="missing"):
        storage.read_version(media_id, 1)


def test_bounds_byte_ceiling_and_assets_per_staging_job(tmp_path, config, monkeypatch):
    import hutch.media.storage as storage_module
    monkeypatch.setattr(storage_module, "MAX_MEDIA_BYTES", 1024)
    storage = MediaStorage(config)
    with pytest.raises(MediaStorageError, match="storage limit"):
        storage.stage_bytes(new_job_id(), "png", "big.png", make_png() + b"\x00" * 2000)
    job = new_job_id()
    for i in range(MAX_MEDIA_PER_JOB):
        storage.stage_bytes(job, "png", f"asset-{i}.png", make_png())
    with pytest.raises(MediaStorageError, match="per-job limit"):
        storage.stage_bytes(job, "png", "asset-8.png", make_png())


def test_unsupported_formats_and_bad_ids_are_refused(tmp_path, config):
    storage = MediaStorage(config)
    with pytest.raises(MediaStorageError, match="unsupported media format"):
        storage.stage_bytes(new_job_id(), "gif", "anim.gif", b"GIF89a" + b"\x00" * 20)
    with pytest.raises(MediaStorageError, match="invalid staging job id"):
        storage.stage_bytes("../escape", "png", "x.png", make_png())
    staged = storage.stage_bytes(new_job_id(), "png", "x.png", make_png())
    with pytest.raises(MediaStorageError, match="invalid media id"):
        storage.commit(staged, "../../etc", 1, insert_row=lambda: None)
    with pytest.raises(MediaStorageError, match="version must be 1–999"):
        storage.commit(staged, new_media_id(), 0, insert_row=lambda: None)


def test_no_symlink_traversal_on_read_or_write(tmp_path, config, tmp_path_factory):
    storage = MediaStorage(config)
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.txt").write_text("not media")
    # A media_id that is really a symlink to somewhere else must never be followed.
    storage.ensure_root()
    evil_id = new_media_id()
    os.symlink(outside, storage.root / evil_id)
    with pytest.raises(MediaStorageError):
        storage.locate(evil_id, 1)
    staged = storage.stage_bytes(new_job_id(), "png", "x.png", make_png())
    with pytest.raises(MediaStorageError, match="not a private directory"):
        storage.commit(staged, evil_id, 1, insert_row=lambda: None)
    assert (outside / "secret.txt").read_text() == "not media"
    assert not list(outside.glob("*.png"))
    # A version directory that is a symlink is not a version.
    real_id = new_media_id()
    s = storage.stage_bytes(new_job_id(), "png", "x.png", make_png())
    storage.commit(s, real_id, 1, insert_row=lambda: None)
    version_dir = storage.locate(real_id, 1)[0]
    (storage.root / real_id / version_dir).chmod(0o700)
    os.symlink(outside, storage.root / real_id / "v002-00000000")
    with pytest.raises(MediaStorageError, match="no such media version"):
        storage.locate(real_id, 2)


def test_reconcile_deletes_unreferenced_versions_and_old_staging(tmp_path, config):
    storage = MediaStorage(config)
    referenced, orphan = new_media_id(), new_media_id()
    s1 = storage.stage_bytes(new_job_id(), "png", "r.png", make_png())
    storage.commit(s1, referenced, 1, insert_row=lambda: None)
    s2 = storage.stage_bytes(new_job_id(), "png", "o.png", make_png())
    storage.commit(s2, orphan, 1, insert_row=lambda: None)
    abandoned = storage.staging / new_job_id()
    abandoned.mkdir(mode=0o700)
    old = 24 * 3600 + 60
    os.utime(abandoned, (old, old))

    def version_exists(media_id: str, version: int) -> bool:
        return media_id == referenced and version == 1

    report = reconcile_media_store(config, version_exists, max_staging_age=24 * 3600)
    assert report["removed_versions"] == 1
    assert report["removed_staging"] == 1
    assert storage.read_version(referenced, 1)[0] == make_png()
    with pytest.raises(MediaStorageError):
        storage.read_version(orphan, 1)
    assert not abandoned.exists()


def test_poster_commit_and_verified_read(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    job = new_job_id()
    staged = storage.stage_bytes(job, "webm", "clip.webm", b"\x1aE\xdf\xa3webm-pad-pad-pad")
    poster = storage.stage_bytes(job, "png", "poster", make_png(8, 8))
    storage.commit(staged, media_id, 1, meta={"kind": "video"}, poster=poster,
                   insert_row=lambda: None)
    data, entry = storage.read_poster(media_id, 1)
    assert data == make_png(8, 8)
    assert entry["sha256"] == poster.sha256 and entry["mime"] == "image/png"
    with pytest.raises(MediaStorageError, match="no poster"):
        other = new_media_id()
        s = storage.stage_bytes(new_job_id(), "png", "x.png", make_png())
        storage.commit(s, other, 1, insert_row=lambda: None)
        storage.read_poster(other, 1)


# ------------------------------------------------------------------ routes


def _client_for(config):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hutch.media.routes import build_media_router

    app = FastAPI()
    app.include_router(build_media_router(store=None, media_store=MediaStorage(config)))
    return TestClient(app)


def test_media_routes_serve_verified_bytes_with_etag_and_304(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    staged = storage.stage_bytes(new_job_id(), "png", "pic.png", make_png())
    storage.commit(staged, media_id, 1, meta={"kind": "image"}, insert_row=lambda: None)
    client = _client_for(config)
    response = client.get(f"/api/v1/media/{media_id}/versions/1/content")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["etag"] == f'"{staged.sha256}"'
    assert response.headers["x-hutch-artifact-verified"] == "sha256"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == make_png()
    cached = client.get(f"/api/v1/media/{media_id}/versions/1/content",
                        headers={"if-none-match": f'"{staged.sha256}"'})
    assert cached.status_code == 304


def test_media_routes_are_honest_on_missing_and_corrupt(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    staged = storage.stage_bytes(new_job_id(), "png", "pic.png", make_png())
    storage.commit(staged, media_id, 1, meta={"kind": "image"}, insert_row=lambda: None)
    client = _client_for(config)
    assert client.get(f"/api/v1/media/{media_id}/versions/2/content").status_code == 404
    assert client.get("/api/v1/media/mediadeadbeefdeadbeef/versions/1/content").status_code == 404
    assert client.get(f"/api/v1/media/{media_id}/versions/1/poster").status_code == 404
    assert client.get("/api/v1/media/../../etc/versions/1/content").status_code in (404, 403)
    # Corrupt the promoted bytes: serving answers 410 Gone, never unverified content.
    path = storage.root / media_id / f"v001-{staged.sha256[:8]}" / "pic.png"
    path.chmod(0o600)
    path.write_bytes(make_png()[:-1] + b"\x00")
    gone = client.get(f"/api/v1/media/{media_id}/versions/1/content")
    assert gone.status_code == 410
    assert "integrity" in gone.json()["detail"].lower()


def test_media_routes_serve_a_verified_poster(tmp_path, config):
    storage = MediaStorage(config)
    media_id = new_media_id()
    job = new_job_id()
    staged = storage.stage_bytes(job, "webm", "clip.webm", b"\x1aE\xdf\xa3webm-pad-pad-pad")
    poster = storage.stage_bytes(job, "png", "poster", make_png(8, 8))
    storage.commit(staged, media_id, 1, meta={"kind": "video"}, poster=poster,
                   insert_row=lambda: None)
    client = _client_for(config)
    response = client.get(f"/api/v1/media/{media_id}/versions/1/poster")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == make_png(8, 8)
