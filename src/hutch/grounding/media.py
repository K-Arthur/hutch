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
import shutil
import struct
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


def _sample_frame(source: Path, at_ms: int, out_path: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"at_ms": at_ms, "error": "ffmpeg is not installed"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, at_ms) / 1000:.3f}",
             "-i", str(source), "-frames:v", "1",
             "-vf", f"scale='min({MAX_FRAME_EDGE},iw)':-2", "-q:v", "4", "-y", str(out_path)],
            capture_output=True, timeout=FFMPEG_TIMEOUT, text=True)
        if result.returncode != 0 or not out_path.exists():
            return {"at_ms": at_ms, "error": (result.stderr or "ffmpeg produced no frame")[:300]}
        os.chmod(out_path, 0o600)
        digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
        return {"at_ms": at_ms, "path": str(out_path), "sha256": digest}
    except subprocess.TimeoutExpired:
        return {"at_ms": at_ms, "error": "frame extraction timed out (bounded at 40 s)"}


def _default_frame_times(duration_ms: int, claim_times: list[int]) -> list[int]:
    """Claim-relevant times first, then a small boundary-aware spread; deduped and sorted."""
    times = [int(max(0, t)) for t in claim_times]
    if duration_ms > 0:
        spread = [0, int(duration_ms * 0.25), int(duration_ms * 0.5), int(duration_ms * 0.75),
                  max(0, duration_ms - 200)]
        times.extend(spread)
    unique: list[int] = []
    for value in sorted(times):
        if value not in unique:
            unique.append(value)
    return unique[:MAX_FRAMES]


def inspect_media(source: str, *, store_dir: Path, media_id: str, clock: Clock,
                  claim: str = "", claim_times_ms: Optional[list[int]] = None,
                  workspace: Optional[Path] = None, allow_remote: bool = True,
                  max_frames: int = MAX_FRAMES) -> MediaBundle:
    """Acquire + inspect one image/video/audio artifact.

    ``source`` is either a public https URL (fetched through the SSRF guard and stored as a
    derivative original) or a path inside ``workspace`` (never read outside it).
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
        _inspect_image(bundle, data, bundle_dir)
    elif kind in ("video", "audio"):
        probe = _ffprobe(original_path)
        bundle.probe = probe
        if probe.get("tags", {}).get("creation_time"):
            bundle.metadata["creation_time"] = probe["tags"]["creation_time"]
            bundle.metadata["creation_time_note"] = ("container creation_time is a device/software clue; it can be "
                                                     "edited and does not establish when the depicted event occurred")
        duration_s = float(probe.get("duration_s") or 0.0)
        if kind == "video" and probe.get("available") and duration_s > 0:
            times = _default_frame_times(int(duration_s * 1000), claim_times_ms)[:max_frames]
            for at_ms in times:
                frame = _sample_frame(original_path, at_ms, bundle_dir / "frames" / f"{at_ms:08d}.jpg")
                bundle.frames.append(frame)
            inspected = [f["at_ms"] for f in bundle.frames if f.get("path")]
            if bundle.frames and not inspected:
                bundle.limitations.append("frame extraction failed for every sampled time; no visual frames reached the model")
            else:
                bundle.limitations.append(
                    f"inspected {len(inspected)} frames at {inspected} ms; intervals between frames and all audio "
                    "were not inspected (no audio track analysis in this slice)")
            bundle.observations.append({
                "kind": "sampling_plan", "text":
                    f"claim-relevant times {sorted(claim_times_ms)} plus a boundary-aware spread over "
                    f"{duration_s:.1f}s; frames are separate derivatives of the stored original"})
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


def _inspect_image(bundle: MediaBundle, data: bytes, bundle_dir: Path) -> None:
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
            derivative = bundle_dir / "attachment.jpg"
            preview = image.convert("RGB")
            scale = min(1.0, MAX_FRAME_EDGE / max(preview.width, preview.height))
            if scale < 1.0:
                preview = preview.resize((max(1, int(preview.width * scale)), max(1, int(preview.height * scale))))
            preview.save(derivative, "JPEG", quality=82)
            os.chmod(derivative, 0o600)
            bundle.transformations.append({
                "from": "original", "to": str(derivative),
                "steps": ([f"scale {scale:.3f}"] if scale < 1.0 else []) + ["re-encode JPEG q82"],
                "coordinate_mapping": f"attachment pixel (x,y) maps to original ({x_scale(scale):.3f}*x, {x_scale(scale):.3f}*y)"})
            bundle.frames.append({"at_ms": 0, "path": str(derivative),
                                  "sha256": hashlib.sha256(derivative.read_bytes()).hexdigest()})
    except (OSError, ValueError) as exc:
        bundle.limitations.append(f"the image could not be decoded safely ({type(exc).__name__}); "
                                  "no visual observation was made")
        bundle.probe = {"available": False, "error": str(exc)[:300]}


def x_scale(scale: float) -> float:
    return 1.0 / scale if scale > 0 else 1.0


def reverse_image_search_status() -> dict[str, str]:
    """The reverse-image/fact-check lane is intentionally not enabled here.

    Sending a user's media to a public matching service is a data-egress permission this
    slice does not hold, and the documented image-search APIs require a public URL. The
    honest state is ``unsupported``.
    """
    return {"state": "unsupported",
            "detail": ("no reverse-image or image fact-check service is configured; uploading user media to a "
                       "public matching service requires a separate, explicit permission and public URL")}
