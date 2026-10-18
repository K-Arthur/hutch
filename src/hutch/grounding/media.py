"""Bounded media acquisition, sampling, and provenance — evidence, never a verdict.

What this module will and will not do (mission sections 9-10):

* Acquire the permitted original/highest-quality available artifact (bounded fetch or a
  workspace file), hash it, keep acquisition metadata, and store analysis derivatives
  **separately** from the original with recorded transformations.
* Inspect safely and locally: magic-byte sniffing, Pillow decode for images (decompression
  bombs refused), ``ffprobe`` for container/stream metadata, ``ffmpeg`` for frame sampling
  at claim-relevant times. All child processes are bounded and time-limited.
* Sample **claim-relevant** moments, not a uniform sparse grid that misses a brief edit.
  The report always lists the exact inspected frame times and the intervals/audio that
  were NOT inspected. A model sampling at 1 fps can miss fast action (documented); the
  frame list is what makes the limitation visible.
* C2PA: detect manifest presence in JPEG/PNG containers and, only when a maintained
  ``c2pa`` verifier is importable, run it. ``absent`` is a normal state (most media has no
  Content Credentials); ``present_unverified`` is not a truth claim; no cryptography is
  hand-rolled and no truth badge is ever rendered.
* Never upload media to a reverse-image/fact-check service: egress of the user's private
  media is a separate permission that this slice does not hold (the check is reported as
  ``unsupported``, not simulated).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..netguard import NetGuardError, safe_get
from .clock import Clock

#: per-artifact acquisition bounds (bytes)
MAX_IMAGE_BYTES = 8_000_000
MAX_VIDEO_BYTES = 40_000_000
MAX_AUDIO_BYTES = 20_000_000
MAX_FRAMES = 6
MAX_FRAME_EDGE = 1280
FFPROBE_TIMEOUT = 20.0
FFMPEG_TIMEOUT = 40.0
#: decompression-bomb guard for Pillow
MAX_IMAGE_PIXELS = 60_000_000

C2PA_JUMBF_UUID = bytes.fromhex("6332706100110010800000aa00389b71")  # 'c2pa' as a UUID


class MediaError(ValueError):
    """Acquisition or inspection refused; the caller reports the reason, never a guess."""


@dataclass
class MediaBundle:
    media_id: str
    kind: str                      # image | video | audio | other
    origin: str                    # remote URL or workspace path
    local_path: str                # stored original (Hutch-managed derivative directory)
    sha256: str
    bytes: int
    mime: str
    probe: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    c2pa: dict[str, Any] = field(default_factory=dict)
    frames: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    transformations: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in
                ("media_id", "kind", "origin", "local_path", "sha256", "bytes", "mime", "probe",
                 "metadata", "c2pa", "frames", "observations", "limitations", "transformations")}


def _sniff_kind(data: bytes) -> tuple[str, str]:
    """Magic-byte sniffing; returns (kind, mime). Never trusts a Content-Type alone."""
    if data[:3] == b"\xff\xd8\xff":
        return "image", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image", "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio", "audio/wav"
    if len(data) > 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        return "video", {"isom": "video/mp4", "mp42": "video/mp4", "M4V ": "video/x-m4v",
                         "qt  ": "video/quicktime"}.get(brand.decode("latin-1"), "video/mp4")
    if data[:4] == b"\x1aE\xdf\xa3":
        return "video", "video/webm"
    if data[:4] == b"OggS":
        return "audio", "audio/ogg"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio", "audio/mpeg"
    if data[:5] == b"%PDF-":
        return "other", "application/pdf"
    return "other", "application/octet-stream"


def _c2pa_presence(data: bytes) -> dict[str, Any]:
    """Container-level manifest presence + optional maintained-verifier result.

    Presence detection reads bounded windows only; it says NOTHING about validity or truth.
    """
    report: dict[str, Any] = {"state": "absent", "detail": "", "manifest_offset": None}
    marker = C2PA_JUMBF_UUID
    offset = data.find(marker)
    if offset >= 0:
        report.update(state="present_unverified", manifest_offset=offset,
                      detail="a C2PA/-family JUMBF marker is present; validity requires a maintained verifier")
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data.find(b"caBX") >= 0:
        report.update(state="present_unverified",
                      detail="a PNG 'caBX' (C2PA) chunk is present; validity requires a maintained verifier")
    try:
        import c2pa  # type: ignore  # noqa: F401
    except ImportError:
        report["verifier"] = "not installed; install the 'c2pa' Python package to validate signatures"
        return report
    try:
        import io
        from c2pa import Reader  # type: ignore
        reader = Reader(io.BytesIO(data), "image/*")
        json_report = reader.json()
        parsed = json.loads(json_report) if isinstance(json_report, str) else json_report
        validation = (parsed or {}).get("validation_status") if isinstance(parsed, dict) else None
        report.update(verifier="c2pa-python", state="verified" if not validation else "invalid",
                      validation=validation if isinstance(validation, list) else [],
                      detail="signature checked by the maintained C2PA verifier; signer trust and claim "
                             "truth remain separate questions")
    except Exception as exc:  # noqa: BLE001 - verifier errors are recorded, never guessed
        report.update(state="present_unverified", verifier="c2pa-python",
                      detail=f"the verifier could not validate this asset here: {type(exc).__name__}: {exc}")
    return report


def _exif_clues(image) -> dict[str, Any]:
    """A few untrusted capture clues. EXIF is a clue with known limitations, not proof."""
    clues: dict[str, Any] = {}
    try:
        exif = image.getexif()
    except Exception:  # noqa: BLE001
        return clues
    names = {271: "make", 272: "model", 305: "software", 306: "datetime", 36867: "datetime_original",
             274: "orientation"}
    for tag, name in names.items():
        value = exif.get(tag)
        if value:
            clues[name] = str(value)[:120]
    if clues:
        clues["note"] = ("EXIF fields are editable and often stripped by platforms; they are clues about "
                         "capture, not proof of when an event occurred")
    return clues


def _ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"available": False, "detail": "ffprobe is not installed; container metadata unavailable"}
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, timeout=FFPROBE_TIMEOUT, text=True)
        if result.returncode != 0:
            return {"available": True, "error": (result.stderr or "ffprobe failed")[:400]}
        data = json.loads(result.stdout or "{}")
        fmt = data.get("format") or {}
        streams = []
        for stream in (data.get("streams") or [])[:8]:
            streams.append({k: stream.get(k) for k in
                            ("codec_type", "codec_name", "width", "height", "avg_frame_rate", "sample_rate",
                             "channels", "duration", "nb_frames") if stream.get(k) is not None})
        return {"available": True, "duration_s": float(fmt.get("duration") or 0.0),
                "format_name": fmt.get("format_name"), "tags": {k: str(v)[:160] for k, v in
                (fmt.get("tags") or {}).items() if k.lower() in ("creation_time", "com.apple.quicktime.creationdate", "encoder")},
                "streams": streams}
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "ffprobe timed out (bounded at 20 s)"}
    except (ValueError, OSError) as exc:
        return {"available": True, "error": f"{type(exc).__name__}: {exc}"}


def _sample_frame(source: Path, at_ms: int, out_path: Path,
                  region: Optional[tuple[int, int, int, int]] = None) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"at_ms": at_ms, "error": "ffmpeg is not installed"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    if region is not None:
        x, y, w, h = region
        filters.append(f"crop={w}:{h}:{x}:{y}")
    filters.append(f"scale='min({MAX_FRAME_EDGE},iw)':-2")
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, at_ms) / 1000:.3f}",
             "-i", str(source), "-frames:v", "1",
             "-vf", ",".join(filters), "-q:v", "4", "-y", str(out_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, text=True)
        if result.returncode != 0 or not out_path.exists():
            return {"at_ms": at_ms, "error": (result.stderr or "ffmpeg produced no frame")[:300]}
        os.chmod(out_path, 0o600)
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
        return {"at_ms": at_ms, "path": str(out_path), "sha256": digest}
    except subprocess.TimeoutExpired:
        return {"at_ms": at_ms, "error": "frame extraction timed out (bounded at 40 s)"}


def parse_region(text: str, width: int, height: int) -> Optional[tuple[int, int, int, int]]:
    """Parse an ``x,y,w,h`` pixel region against the artifact's real dimensions.

    Out-of-bounds regions are refused with the actual dimensions in the message — never
    silently clamped, because a clamped crop would misrepresent what was inspected.
    """
    value = (text or "").strip()
    if not value:
        return None
    parts = [p.strip() for p in value.replace(" ", "").split(",")]
    if len(parts) != 4 or not all(p.lstrip("-").isdigit() for p in parts):
        raise MediaError(f"region must be 'x,y,w,h' in pixels, got {text!r}")
    x, y, w, h = (int(p) for p in parts)
    if w < 16 or h < 16:
        raise MediaError("region must be at least 16x16 pixels")
    if x < 0 or y < 0 or x + w > width or y + h > height:
        raise MediaError(f"region {x},{y},{w},{h} exceeds the {width}x{height} artifact; "
                         "adjust it instead of relying on a silent clamp")
    return (x, y, w, h)


def _scene_change_times(source: Path, *, threshold: float = 0.3, limit: int = 8) -> tuple[list[int], str]:
    """Scene-change timestamps via ffmpeg's scene score (bounded, out-of-process).

    A uniform sparse grid can step over a brief inserted clip or a hard edit; scene changes
    are exactly where a claim about footage ("the video shows X") most often breaks. Returns
    ``(times_ms, note)``; a failure returns an empty list and a note the caller records.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [], "ffmpeg is not installed so scene changes were not detected"
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(source),
             "-vf", f"select='gt(scene,{threshold:.2f})',showinfo", "-an", "-f", "null", "-"],
            capture_output=True, timeout=FFMPEG_TIMEOUT, text=True)
        times: list[int] = []
        for match in re.finditer(r"pts_time:(\d+(?:\.\d+)?)", result.stderr or ""):
            value = int(float(match.group(1)) * 1000)
            if value >= 0 and value not in times:
                times.append(value)
        times = times[:limit]
        return times, (f"scene detection (threshold {threshold:.2f}) found {len(times)} change(s)"
                       if times else "no scene changes above the detection threshold were found; "
                                     "brief edits below it can still be missed")
    except subprocess.TimeoutExpired:
        return [], "scene detection timed out (bounded at 40 s)"
    except OSError as exc:
        return [], f"scene detection failed: {type(exc).__name__}"


def _default_frame_times(duration_ms: int, claim_times: list[int], scene_times: Optional[list[int]] = None,
                         *, merge_window_ms: int = 150) -> tuple[list[int], dict[str, int]]:
    """Claim-relevant times first, then scene changes, then a boundary-aware spread.

    Near-duplicate times (within ``merge_window_ms``) collapse to one frame. The plan is
    returned with counts per source so the brief can state what drove the sampling.
    """
    scene_times = scene_times or []
    ordered: list[int] = []
    for group, label in ((claim_times, "claim"), (scene_times, "scene")):
        for value in sorted(int(max(0, t)) for t in group):
            if all(abs(value - existing) > merge_window_ms for existing in ordered):
                ordered.append(value)
    spread: list[int] = []
    if duration_ms > 0:
        spread = [0, int(duration_ms * 0.25), int(duration_ms * 0.5), int(duration_ms * 0.75),
                  max(0, duration_ms - 200)]
    for value in spread:
        if all(abs(value - existing) > merge_window_ms for existing in ordered):
            ordered.append(value)
    ordered = sorted(ordered)[:MAX_FRAMES]
    counts = {
        "claim": sum(1 for t in ordered if any(abs(t - c) <= merge_window_ms for c in claim_times)),
        "scene": sum(1 for t in ordered if any(abs(t - s) <= merge_window_ms for s in scene_times)),
        "boundary_spread": len(ordered),
    }
    return ordered, counts


def inspect_media(source: str, *, store_dir: Path, media_id: str, clock: Clock,
                  claim: str = "", claim_times_ms: Optional[list[int]] = None,
                  workspace: Optional[Path] = None, allow_remote: bool = True,
                  max_frames: int = MAX_FRAMES, region: str = "") -> MediaBundle:
    """Acquire + inspect one image/video/audio artifact.

    ``source`` is either a public https URL (fetched through the SSRF guard and stored as a
    derivative original) or a path inside ``workspace`` (never read outside it).

    ``region`` is an optional ``x,y,w,h`` pixel rectangle of a specific claim-relevant area
    (a sign, a plate, a receipt total). The crop is taken from the original coordinates,
    the attachment contains *only* that region, and the mapping back to original pixels is
    recorded — anything outside the region is explicitly not inspected.
    """
    claim_times_ms = claim_times_ms or []
    bundle_dir = store_dir / media_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(bundle_dir, 0o700)
    except OSError:
        pass
    acquired_from = source
    if source.lower().startswith(("http://", "https://")):
        if not allow_remote:
            raise MediaError("remote media acquisition is disabled for this run")
        try:
            resp = safe_get(source, timeout=25.0, max_bytes=max(MAX_IMAGE_BYTES, MAX_VIDEO_BYTES),
                            headers={"User-Agent": "hutch/0.1 (+local agent platform)", "Accept": "image/*,video/*,audio/*"})
        except NetGuardError as exc:
            raise MediaError(f"media fetch refused: {exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            raise MediaError(f"media fetch failed: {type(exc).__name__}: {exc}") from exc
        if resp.status != 200:
            raise MediaError(f"media fetch returned HTTP {resp.status}")
        data = resp.body
    else:
        if workspace is None:
            raise MediaError("a workspace root is required for local media paths")
        candidate = Path(source)
        resolved = (workspace / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            resolved.relative_to(workspace.resolve())
        except ValueError:
            raise MediaError("the media path is outside this run's workspace") from None
        if not resolved.is_file():
            raise MediaError("the media path does not exist in the workspace")
        data = resolved.read_bytes()
        acquired_from = str(resolved)
    kind, mime = _sniff_kind(data)
    limit = {"image": MAX_IMAGE_BYTES, "video": MAX_VIDEO_BYTES, "audio": MAX_AUDIO_BYTES}.get(kind, MAX_IMAGE_BYTES)
    if len(data) > limit:
        raise MediaError(f"media exceeds the {limit // 1_000_000} MB {kind} limit")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
              "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
              "audio/wav": ".wav", "audio/ogg": ".ogg", "audio/mpeg": ".mp3"}.get(mime, ".bin")
    original_path = bundle_dir / f"original{suffix}"
    original_path.write_bytes(data)
    os.chmod(original_path, 0o400)
    digest = hashlib.sha256(data).hexdigest()
    bundle = MediaBundle(media_id=media_id, kind=kind, origin=acquired_from, local_path=str(original_path),
                         sha256=digest, bytes=len(data), mime=mime)
    bundle.metadata["retrieved_at"] = clock.now().isoformat()
    bundle.metadata["acquisition"] = "remote fetch (SSRF-guarded, bounded)" if source.lower().startswith("http") else "workspace file"
    bundle.metadata["filename_claim"] = Path(source.split("?")[0]).name[:120]
    bundle.metadata["filename_note"] = "a filename is uploader-controlled text; it is not a timestamp or origin"
    bundle.c2pa = _c2pa_presence(data)

    if kind == "image":
        _inspect_image(bundle, data, bundle_dir, region)
    elif kind in ("video", "audio"):
        probe = _ffprobe(original_path)
        bundle.probe = probe
        if probe.get("tags", {}).get("creation_time"):
            bundle.metadata["creation_time"] = probe["tags"]["creation_time"]
            bundle.metadata["creation_time_note"] = ("container creation_time is a device/software clue; it can be "
                                                     "edited and does not establish when the depicted event occurred")
        duration_s = float(probe.get("duration_s") or 0.0)
        if kind == "video" and probe.get("available") and duration_s > 0:
            video_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
            rect = None
            if region:
                width, height = int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)
                if not width or not height:
                    raise MediaError("the region could not be applied: the video's pixel dimensions were not reported")
                rect = parse_region(region, width, height)
            scene_times, scene_note = _scene_change_times(original_path)
            times, plan_counts = _default_frame_times(int(duration_s * 1000), claim_times_ms, scene_times)
            times = times[:max_frames]
            for at_ms in times:
                frame = _sample_frame(original_path, at_ms, bundle_dir / "frames" / f"{at_ms:08d}.jpg", rect)
                bundle.frames.append(frame)
            inspected = [f["at_ms"] for f in bundle.frames if f.get("path")]
            if bundle.frames and not inspected:
                bundle.limitations.append("frame extraction failed for every sampled time; no visual frames reached the model")
            else:
                bundle.limitations.append(
                    f"inspected {len(inspected)} frames at {inspected} ms; intervals between frames and all audio "
                    "were not inspected (no audio track analysis in this slice)")
            if rect is not None:
                bundle.transformations.append({
                    "from": "sampled frames", "to": "attachments",
                    "steps": [f"crop {rect[2]}x{rect[3]}+{rect[0]}+{rect[1]} on each sampled frame",
                              f"scale to at most {MAX_FRAME_EDGE}px"],
                    "region": {"x": rect[0], "y": rect[1], "width": rect[2], "height": rect[3]},
                    "coordinate_mapping": (f"attachment pixel (px,py) maps to frame coordinates "
                                           f"({rect[0]} + k*px, {rect[1]} + k*py) where k is the per-frame scale")})
                bundle.observations.append({
                    "kind": "region_applied",
                    "text": (f"inspected region x={rect[0]} y={rect[1]} w={rect[2]} h={rect[3]} on every sampled "
                             "frame; anything outside the region was not inspected")})
            bundle.observations.append({
                "kind": "sampling_plan", "text":
                    f"claim-relevant times {sorted(claim_times_ms)}, scene changes {scene_times}, plus a boundary-aware "
                    f"spread over {duration_s:.1f}s (plan: {plan_counts['claim']} claim / "
                    f"{plan_counts['scene']} scene / {plan_counts['boundary_spread']} total); frames are separate "
                    f"derivatives of the stored original"})
            if not scene_times:
                bundle.observations.append({"kind": "limitation", "text": scene_note})
        elif kind == "video":
            bundle.limitations.append(f"video frames were not sampled: {probe.get('error') or 'no duration'}")
        else:
            bundle.limitations.append("audio content was not transcribed or analyzed in this slice")
    else:
        bundle.limitations.append(f"format {mime} is not a supported image/video/audio type for inspection")

    if claim:
        bundle.observations.append({"kind": "claim_under_check", "text": claim[:600],
                                    "note": "the claim is stored as claim text; inspection findings are separate"})
    bundle.observations.append({
        "kind": "scope_statement",
        "text": ("file provenance, container/metadata clues and (when frames reached the model) visual observations "
                 "are recorded separately; no authenticity, authorship, intent or truth verdict is produced here")})
    return bundle


def _inspect_image(bundle: MediaBundle, data: bytes, bundle_dir: Path, region_text: str = "") -> None:
    try:
        from PIL import Image
    except ImportError:
        bundle.limitations.append("Pillow is not installed; image dimensions and EXIF were not inspected")
        return
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        import io
        with Image.open(io.BytesIO(data)) as image:
            bundle.probe = {"available": True, "format": image.format, "width": image.width,
                            "height": image.height, "mode": image.mode}
            bundle.metadata["exif"] = _exif_clues(image)
            rect = parse_region(region_text, image.width, image.height)
            preview = image.convert("RGB")
            offset = (0, 0)
            if rect is not None:
                x, y, w, h = rect
                preview = preview.crop((x, y, x + w, y + h))
                offset = (x, y)
            scale = min(1.0, MAX_FRAME_EDGE / max(preview.width, preview.height))
            if scale < 1.0:
                preview = preview.resize((max(1, int(preview.width * scale)), max(1, int(preview.height * scale))))
            derivative = bundle_dir / "attachment.jpg"
            preview.save(derivative, "JPEG", quality=82)
            os.chmod(derivative, 0o600)
            steps = ([f"crop {w}x{h}+{offset[0]}+{offset[1]} from the original"] if rect else []) \
                + ([f"scale {scale:.3f}"] if scale < 1.0 else []) + ["re-encode JPEG q82"]
            bundle.transformations.append({
                "from": "original", "to": str(derivative), "steps": steps,
                "region": {"x": offset[0], "y": offset[1], "width": rect[2], "height": rect[3]} if rect else None,
                "coordinate_mapping": (
                    f"attachment pixel (px,py) maps to original "
                    f"({offset[0]} + {1 / scale if scale else 1:.3f}*px, {offset[1]} + {1 / scale if scale else 1:.3f}*py)"
                    if rect else
                    f"attachment pixel (px,py) maps to original (px,py) scaled x{1 / scale if scale else 1:.3f}")})
            bundle.frames.append({"at_ms": 0, "path": str(derivative),
                                  "sha256": hashlib.sha256(derivative.read_bytes()).hexdigest()})
            if rect:
                bundle.observations.append({
                    "kind": "region_applied",
                    "text": (f"inspected region x={offset[0]} y={offset[1]} "
                             f"w={rect[2]} h={rect[3]} of the {image.width}x{image.height} original; the attachment "
                             "is that crop only, so anything outside it was not inspected")})
    except MediaError:
        raise                              # a refused region is an error, not a decode limitation
    except (OSError, ValueError) as exc:
        bundle.limitations.append(f"the image could not be decoded safely ({type(exc).__name__}); "
                                  "no visual observation was made")
        bundle.probe = {"available": False, "error": str(exc)[:300]}


def reverse_image_search_status() -> dict[str, str]:
    """The reverse-image/fact-check lane is intentionally not enabled here.

    Sending a user's media to a public matching service is a data-egress permission this
    slice does not hold, and the documented image-search APIs require a public URL. The
    honest state is ``unsupported``.
    """
    return {"state": "unsupported",
            "detail": ("no reverse-image or image fact-check service is configured; uploading user media to a "
                       "public matching service requires a separate, explicit permission and public URL")}
