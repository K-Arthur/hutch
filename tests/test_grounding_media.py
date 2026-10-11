"""Media acquisition/inspection: real decode, frame sampling, C2PA presence, no verdicts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hutch.grounding import media as media_mod
from hutch.grounding.clock import FrozenClock

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")

pytestmark = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def _png(path: Path, size=(60, 30), color=(20, 120, 200)) -> Path:
    from PIL import Image
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def test_image_is_stored_hashed_and_previewed(tmp_path):
    source = _png(tmp_path / "shot.png")
    bundle = media_mod.inspect_media(str(source), store_dir=tmp_path / "store", media_id="media_x",
                                     clock=CLOCK, claim="the sign says CLOSED", workspace=tmp_path)
    assert bundle.kind == "image" and bundle.mime == "image/png"
    assert bundle.sha256 and Path(bundle.local_path).read_bytes() == source.read_bytes()
    assert bundle.probe["width"] == 60 and bundle.probe["height"] == 30
    assert bundle.frames and Path(bundle.frames[0]["path"]).exists()
    assert any(o["kind"] == "scope_statement" for o in bundle.observations)
    assert bundle.c2pa["state"] == "absent"


def test_media_outside_the_workspace_is_refused(tmp_path):
    outside = _png(tmp_path / "outside.png")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(media_mod.MediaError):
        media_mod.inspect_media(str(outside), store_dir=tmp_path / "store", media_id="media_y",
                                clock=CLOCK, workspace=workspace)


def test_c2pa_presence_is_detected_but_never_asserted_as_valid(tmp_path):
    from PIL import Image
    jpeg = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(jpeg, "JPEG")
    jpeg.write_bytes(jpeg.read_bytes() + media_mod.C2PA_JUMBF_UUID + b"\x00" * 64)
    bundle = media_mod.inspect_media(str(jpeg), store_dir=tmp_path / "store", media_id="media_j",
                                     clock=CLOCK, workspace=tmp_path)
    assert bundle.c2pa["state"] == "present_unverified"
    assert "requires a maintained verifier" in bundle.c2pa["detail"]


def test_oversized_media_is_refused_before_decoding(tmp_path):
    big = tmp_path / "big.png"
    with big.open("wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.seek(media_mod.MAX_IMAGE_BYTES + 1)
        fh.write(b"\x00")
    with pytest.raises(media_mod.MediaError):
        media_mod.inspect_media(str(big), store_dir=tmp_path / "store", media_id="media_big",
                                clock=CLOCK, workspace=tmp_path)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_video_frames_are_sampled_at_boundaries_and_claim_times(tmp_path):
    import subprocess
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=160x120:rate=10:duration=1.2", "-pix_fmt", "yuv420p", str(video)],
                   check=True, timeout=60)
    bundle = media_mod.inspect_media(str(video), store_dir=tmp_path / "store", media_id="media_v",
                                     clock=CLOCK, claim="the lights were already on", claim_times_ms=[600],
                                     workspace=tmp_path)
    times = [f["at_ms"] for f in bundle.frames if f.get("path")]
    assert bundle.kind == "video" and bundle.probe.get("duration_s", 0) > 0.5
    assert 600 in times and 0 in times and len(times) <= media_mod.MAX_FRAMES
    assert all(Path(f["path"]).exists() for f in bundle.frames if f.get("path"))
    limitations = " ".join(bundle.limitations)
    assert "not inspected" in limitations and "audio" in limitations
    assert any(o["kind"] == "sampling_plan" for o in bundle.observations)


def test_reverse_image_search_is_unsupported_not_simulated():
    status = media_mod.reverse_image_search_status()
    assert status["state"] == "unsupported" and "permission" in status["detail"]
