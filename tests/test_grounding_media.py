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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_hard_cut_is_sampled_even_when_it_misses_the_uniform_grid(tmp_path):
    """The grid at 25/50/75% of a 2 s clip is 500/1000/1500 ms; a cut at 1300 ms is 200 ms
    from the nearest grid point, scene detection must catch it anyway."""
    import subprocess
    video = tmp_path / "cut.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=160x120:d=1.3:r=10",
        "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=0.7:r=10",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(video)],
        check=True, timeout=60)
    bundle = media_mod.inspect_media(str(video), store_dir=tmp_path / "store", media_id="media_cut",
                                     clock=CLOCK, workspace=tmp_path)
    times = [f["at_ms"] for f in bundle.frames if f.get("path")]
    assert times, bundle.limitations
    assert min(abs(t - 1300) for t in times) <= 250, f"no frame near the hard cut: {times}"
    assert len(times) <= media_mod.MAX_FRAMES
    plan = next(o for o in bundle.observations if o["kind"] == "sampling_plan")
    assert "scene changes" in plan["text"]


def test_region_crop_maps_back_to_original_coordinates(tmp_path):
    """A claim about a sign or a receipt total is inspected as a crop of the *original*
    coordinates, and the mapping back is recorded; nothing outside the region is claimed."""
    from PIL import Image
    source = tmp_path / "receipt.png"
    image = Image.new("RGB", (200, 100), (200, 30, 30))
    for x in range(100, 200):
        for y in range(100):
            image.putpixel((x, y), (20, 30, 200))
    image.save(source, "PNG")
    bundle = media_mod.inspect_media(str(source), store_dir=tmp_path / "store", media_id="media_region",
                                     clock=CLOCK, claim="the total reads 250.00", workspace=tmp_path,
                                     region="100,0,100,100")
    assert bundle.frames, bundle.limitations
    with Image.open(bundle.frames[0]["path"]) as crop:
        assert crop.size == (100, 100), "the attachment must contain only the requested region"
        assert crop.getpixel((50, 50))[2] > 150 and crop.getpixel((50, 50))[0] < 100
    transformation = bundle.transformations[0]
    assert transformation["region"] == {"x": 100, "y": 0, "width": 100, "height": 100}
    assert "100 +" in transformation["coordinate_mapping"]
    assert any(o["kind"] == "region_applied" for o in bundle.observations)


def test_region_out_of_bounds_is_refused_with_real_dimensions(tmp_path):
    source = _png(tmp_path / "small.png", size=(60, 30))
    with pytest.raises(media_mod.MediaError) as exc:
        media_mod.inspect_media(str(source), store_dir=tmp_path / "store", media_id="media_bad_region",
                                clock=CLOCK, workspace=tmp_path, region="50,0,40,30")
    assert "60x30" in str(exc.value)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_video_region_is_applied_to_every_sampled_frame(tmp_path):
    import subprocess
    video = tmp_path / "clip2.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=160x120:rate=10:duration=1.0", "-pix_fmt", "yuv420p", str(video)],
                   check=True, timeout=60)
    bundle = media_mod.inspect_media(str(video), store_dir=tmp_path / "store", media_id="media_vregion",
                                     clock=CLOCK, workspace=tmp_path, region="0,0,80,120")
    frames = [f for f in bundle.frames if f.get("path")]
    assert frames
    from PIL import Image
    for frame in frames:
        with Image.open(frame["path"]) as shot:
            assert shot.size == (80, 120)
    assert any(t.get("region") == {"x": 0, "y": 0, "width": 80, "height": 120}
               for t in bundle.transformations)
    assert any(o["kind"] == "region_applied" for o in bundle.observations)


def test_reverse_image_search_is_unsupported_not_simulated():
    status = media_mod.reverse_image_search_status()
    assert status["state"] == "unsupported" and "permission" in status["detail"]
