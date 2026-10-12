"""Frame store bounds/integrity and the provider-boundary image preparer (no browser, no network)."""

from __future__ import annotations

import base64
import os
import struct
import zlib

import pytest

from hutch.computer.frames import (MAX_FRAME_BYTES, MAX_FRAME_EDGE, FrameError, FrameStore, ImageRef, image_size)
from hutch.providers.images import has_images, prepare_messages


def _png(width: int, height: int, fill: int = 0x40) -> bytes:
    """A real, valid grayscale PNG of the requested size."""
    raw = b"".join(b"\x00" + bytes([fill]) * width for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_png_and_jpeg_dimensions_are_read_from_headers():
    assert image_size(_png(37, 11), "image/png") == (37, 11)
    # minimal JPEG header: SOI, APP0-less, SOF0 with height 19 and width 41
    jpeg = b"\xff\xd8" + b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 19, 41, 1) + b"\x01\x11\x00" + b"\xff\xd9"
    assert image_size(jpeg, "image/jpeg") == (41, 19)
    with pytest.raises(FrameError):
        image_size(b"not an image", "image/png")


def test_a_saved_frame_is_private_verified_and_readable(tmp_path):
    store = FrameStore(tmp_path / "run")
    data = _png(64, 48)
    ref = store.save(data, "image/png")
    assert ref.frame_id == "f000001" and (ref.width, ref.height) == (64, 48)
    path = tmp_path / "run" / ref.path
    assert oct(os.stat(path).st_mode & 0o777) == "0o400"
    assert oct(os.stat(path.parent).st_mode & 0o777) == "0o700"
    assert store.load(ref) == data
    assert "path" not in ref.public()


def test_frames_are_bounded_per_image_and_by_edge(tmp_path):
    store = FrameStore(tmp_path / "run")
    with pytest.raises(FrameError, match="long edge"):
        store.save(_png(MAX_FRAME_EDGE + 1, 4), "image/png")
    big = _png(32, 32) + b"\x00" * (MAX_FRAME_BYTES + 1)
    with pytest.raises(FrameError, match="limit"):
        store.save(big, "image/png")
    with pytest.raises(FrameError):
        store.save(b"", "image/png")
    with pytest.raises(FrameError, match="unsupported"):
        store.save(_png(4, 4), "image/svg+xml")


def test_the_run_budget_evicts_oldest_frames_but_never_the_newest(tmp_path):
    store = FrameStore(tmp_path / "run", max_bytes=3_000, max_frames=3)
    refs = [store.save(_png(30, 30, fill=i), "image/png") for i in range(6)]
    usage = store.usage()
    assert usage["frames"] <= 3
    assert store.load(refs[-1])                                   # newest survives
    with pytest.raises(FrameError, match="no longer available"):
        store.load(refs[0])                                       # oldest was evicted, reported not crashed


def test_tampering_and_substitution_are_detected(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(16, 16), "image/png")
    path = tmp_path / "run" / ref.path
    os.chmod(path, 0o600)
    path.write_bytes(_png(16, 16, fill=0x99))                     # same size and dims, different pixels
    with pytest.raises(FrameError, match="integrity"):
        store.load(ref)
    forged = ImageRef(**{**ref.internal(), "path": "../../etc/passwd"})
    with pytest.raises(FrameError, match="does not point"):
        store.load(forged)


def test_symlinked_frames_are_refused(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(16, 16), "image/png")
    path = tmp_path / "run" / ref.path
    outside = tmp_path / "secret.png"
    outside.write_bytes(_png(16, 16))
    os.chmod(path, 0o600)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(FrameError):
        store.load(ref)


# ------------------------------------------------------------------ provider boundary


def _tool_msg(call_id: str, ref: ImageRef | None, text: str = "ok") -> dict:
    message = {"role": "tool", "tool_call_id": call_id, "name": "browser", "content": text}
    if ref is not None:
        message["images"] = [ref.internal()]
    return message


def _conversation(refs: list[ImageRef]) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "s"}, {"role": "user", "content": "do it"}]
    for index, ref in enumerate(refs):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{index}", "type": "function", "function": {"name": "browser", "arguments": "{}"}}]})
        msgs.append(_tool_msg(f"c{index}", ref, f"observed {index}"))
    return msgs


def test_messages_without_images_are_passed_through_untouched():
    msgs = [{"role": "user", "content": "hi"}]
    prepared, report = prepare_messages(msgs, vision=True, frames=None)
    assert prepared is msgs and report == {"delivered": [], "omitted": []}


def test_only_the_newest_frame_is_delivered_and_older_ones_become_notes(tmp_path):
    store = FrameStore(tmp_path / "run")
    refs = [store.save(_png(20, 20, fill=i), "image/png") for i in range(3)]
    msgs = _conversation(refs)
    snapshot = [dict(m) for m in msgs]

    prepared, report = prepare_messages(msgs, vision=True, frames=store)

    assert msgs == snapshot, "the persistent conversation must not be mutated or gain image bytes"
    assert report["delivered"] == [refs[2].frame_id]
    assert [o["frame_id"] for o in report["omitted"]] == [refs[0].frame_id, refs[1].frame_id]
    assert not has_images(prepared) and all("images" not in m for m in prepared)
    images = [p for m in prepared if isinstance(m.get("content"), list) for p in m["content"] if p["type"] == "image_url"]
    assert len(images) == 1
    url = images[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == store.load(refs[2])
    tool_texts = [m["content"] for m in prepared if m["role"] == "tool"]
    assert "superseded" in tool_texts[0] and "superseded" in tool_texts[1] and "attached" in tool_texts[2]


def test_the_image_message_follows_the_whole_tool_result_block(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(20, 20), "image/png")
    msgs = [{"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "browser", "arguments": "{}"}},
                {"id": "b", "type": "function", "function": {"name": "browser", "arguments": "{}"}}]},
            _tool_msg("a", ref), _tool_msg("b", None, "second result")]
    prepared, _ = prepare_messages(msgs, vision=True, frames=store)
    roles = [m["role"] for m in prepared]
    assert roles == ["user", "assistant", "tool", "tool", "user"], roles


def test_a_text_only_model_gets_an_explicit_note_not_image_bytes(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(20, 20), "image/png")
    prepared, report = prepare_messages(_conversation([ref]), vision=False, frames=store)
    assert report["delivered"] == [] and report["omitted"][0]["reason"] == "model_has_no_vision"
    assert all(not isinstance(m.get("content"), list) for m in prepared)
    assert "cannot receive images" in [m for m in prepared if m["role"] == "tool"][0]["content"]


def test_a_missing_or_tampered_frame_degrades_to_a_note(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(20, 20), "image/png")
    (tmp_path / "run" / ref.path).chmod(0o600)
    (tmp_path / "run" / ref.path).write_bytes(b"garbage")
    prepared, report = prepare_messages(_conversation([ref]), vision=True, frames=store)
    assert report["delivered"] == [] and report["omitted"][0]["reason"] == "unavailable"
    assert all(not isinstance(m.get("content"), list) for m in prepared)


def test_the_request_image_budget_is_enforced(tmp_path):
    store = FrameStore(tmp_path / "run")
    ref = store.save(_png(40, 40), "image/png")
    prepared, report = prepare_messages(_conversation([ref]), vision=True, frames=store, max_payload_bytes=10)
    assert report["omitted"][0]["reason"] == "payload_budget"
