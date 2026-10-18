"""Deterministic renderers: identical input → identical bytes; cycles are valid
input (broken for layering, and it says so); invalid graphs raise GraphInvalid
with the source attached. ffmpeg webm assembly is capability-detected."""

from __future__ import annotations

import shutil
import struct
import xml.etree.ElementTree as ET
import zlib

import pytest

from hutch.media.render import (AnimationInvalid, GraphInvalid, WebMUnavailable,
                                assemble_webm, ffmpeg_available, render_animation,
                                render_animation_poster, render_flowchart,
                                validate_animation, validate_flowchart)


def make_png(width: int = 8, height: int = 8) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        blob = struct.pack(">I", len(data)) + tag + data
        return blob + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x01\x02\x03" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def sample_payload() -> dict:
    return {
        "nodes": [{"id": "collect", "label": "Collect input", "group": "ingest"},
                  {"id": "validate", "label": "Validate", "group": "ingest",
                   "detail": "Rejects non-ASCII filenames"},
                  {"id": "store", "label": "Store"}],
        "edges": [{"from": "collect", "to": "validate", "label": "on success"},
                  {"from": "validate", "to": "store"},
                  {"from": "validate", "to": "collect", "label": "on rejection"}],
        "direction": "LR",
        "assumptions_note": "Ordering assumes the approval gate grants every write.",
    }


# ---------------------------------------------------------------- flowchart


def test_identical_input_produces_byte_identical_svg():
    payload = sample_payload()
    first = render_flowchart(payload)
    second = render_flowchart(sample_payload())
    assert first == second, "determinism is the whole point of the verified path"
    ET.fromstring(first)     # the output is well-formed XML


def test_cycles_are_valid_and_broken_for_layering_with_a_note():
    payload = {
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"},
                  {"id": "c", "label": "C"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                  {"from": "c", "to": "a"}],
        "direction": "LR",
    }
    svg = render_flowchart(payload)
    ET.fromstring(svg)
    assert "cycles present; broken for layering" in svg, "the break is disclosed"
    for node in ("a", "b", "c"):
        assert f'data-node="{node}"' in svg, "every node of the cycle is drawn"
    assert render_flowchart(payload) == svg


def test_long_labels_wrap_without_exploding_the_canvas():
    payload = {"nodes": [{"id": "big", "label": "word " * 40}], "edges": [],
               "direction": "LR"}
    svg = render_flowchart(payload)
    ET.fromstring(svg)
    assert "…" in svg, "an oversized label is ellipsized, not truncated silently"
    widths = [float(word) for word in
              [svg.split('width="', 1)[1].split('"', 1)[0]]]
    assert widths[0] < 20_000, "the canvas stays bounded"


def test_groups_and_tb_direction_render():
    payload = sample_payload()
    payload["direction"] = "TB"
    svg = render_flowchart(payload)
    ET.fromstring(svg)
    assert 'data-group="ingest"' in svg
    assert "assumption:" in svg


def test_invalid_graphs_raise_graphinvalid_with_the_source_attached():
    payload = sample_payload()
    bad = dict(payload)
    bad["edges"] = payload["edges"] + [{"from": "validate", "to": "ghost"}]
    with pytest.raises(GraphInvalid) as exc:
        render_flowchart(bad)
    assert exc.value.source == bad, "the caller's dict comes back with the error"
    assert any("ghost" in problem for problem in exc.value.problems)

    dup = {"nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "A2"}],
           "edges": [], "direction": "LR"}
    with pytest.raises(GraphInvalid, match="duplicate"):
        render_flowchart(dup)

    many = {"nodes": [{"id": f"n{i}", "label": "n"} for i in range(65)],
            "edges": [], "direction": "LR"}
    with pytest.raises(GraphInvalid, match="at most 64"):
        render_flowchart(many)

    with pytest.raises(GraphInvalid, match="direction"):
        render_flowchart({"nodes": [{"id": "a", "label": "A"}], "edges": [],
                          "direction": "DIAGONAL"})


def test_validate_flowchart_normalizes_the_payload():
    clean = validate_flowchart(sample_payload())
    assert clean["direction"] == "LR"
    assert all(set(edge) <= {"from", "to", "label"} for edge in clean["edges"])
    assert clean["assumptions_note"].startswith("Ordering assumes")


def test_svg_escapes_hostile_labels():
    payload = {"nodes": [{"id": "x", "label": '"><script>alert(1)</script>'}],
               "edges": [], "direction": "LR"}
    svg = render_flowchart(payload)
    ET.fromstring(svg)     # still well-formed
    assert "&lt;script&gt;" in svg and "<script>alert(1)</script>" not in svg


# ---------------------------------------------------------------- animation


def animation_payload(frames: int = 3) -> dict:
    return {"title": "The water cycle",
            "frames": [{"label": f"Stage {i}", "duration_seconds": 1.0 + i}
                       for i in range(frames)]}


def test_animation_renders_labeled_smil_frames_deterministically():
    payload = animation_payload()
    first = render_animation(payload)
    assert first == render_animation(animation_payload())
    root = ET.fromstring(first)
    assert root.tag.endswith("svg")
    assert root.get("data-kind") == "animation"
    assert root.get("data-frame-count") == "3"
    assert sum(1 for el in root.iter() if el.tag.endswith("animate")) == 3
    assert sum(1 for el in root.iter() if el.tag.endswith("title")) >= 1
    svg_text = first
    for i in range(3):
        assert f"Stage {i}" in svg_text


def test_animation_escapes_hostile_frame_labels():
    payload = {"frames": [{"label": "<script>alert(1)</script>"}]}
    svg = render_animation(payload)
    ET.fromstring(svg)
    assert "<script>alert(1)</script>" not in svg
    assert "&lt;script&gt;" in svg


def test_animation_rejects_bounds_violations_with_source():
    too_many = animation_payload(200)
    with pytest.raises(AnimationInvalid) as exc:
        render_animation(too_many)
    assert exc.value.source == too_many
    for bad in ({"frames": []},
                {"frames": [{"label": "x", "duration_seconds": 0.01}]},
                {"frames": [{"label": "x", "duration_seconds": 90}]},
                {"frames": [{"label": ""}]}):
        with pytest.raises(AnimationInvalid):
            validate_animation(bad)


def test_animation_poster_is_a_valid_labeled_fallback():
    poster = render_animation_poster(animation_payload())
    root = ET.fromstring(poster)
    assert root.get("data-kind") == "animation-poster"
    assert "frame 1 of 3" in poster


# ---------------------------------------------------------------- webm


def test_ffmpeg_capability_probe_matches_the_system():
    assert ffmpeg_available() == (shutil.which("ffmpeg") is not None)


def test_webm_assembly_refuses_non_png_frames_without_running_anything(monkeypatch):
    monkeypatch.setattr("hutch.media.render.ffmpeg_available", lambda: True)
    with pytest.raises(WebMUnavailable, match="PNG frames"):
        assemble_webm([b"\x00\x00\x00\x18ftypisom"], fps=2.0)


def test_webm_assembly_is_honestly_unavailable_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr("hutch.media.render.ffmpeg_available", lambda: False)
    with pytest.raises(WebMUnavailable, match="ffmpeg"):
        assemble_webm([make_png(), make_png()], fps=1.0)
    with pytest.raises(WebMUnavailable, match="no frames"):
        assemble_webm([], fps=1.0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None,
                    reason="integration check only when ffmpeg is installed")
def test_webm_assembly_with_real_ffmpeg_produces_an_ebml_stream():
    data = assemble_webm([make_png(16, 16), make_png(16, 16), make_png(16, 16)], fps=2.0)
    assert data.startswith(b"\x1a\x45\xdf\xa3")
