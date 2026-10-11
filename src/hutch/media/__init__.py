"""Media pipeline for typed output blocks: durable byte store, validators, job
service, deterministic renderers, and provider adapters.

The block contract lives in ``outputblocks.py``; this package owns the bytes a
``media`` block points at. ``tools/media.py`` exposes the tools; ``routes.py``
builds the serving router the integrator mounts.
"""

from .jobs import (MEDIA_KINDS, TERMINAL_STATUSES, MediaJobError,
                   MediaUnavailableError, MediaJobService, service_status)
from .render import (AnimationInvalid, GraphInvalid, RenderError, WebMUnavailable,
                     assemble_webm, ffmpeg_available, render_animation,
                     render_animation_poster, render_flowchart, validate_animation,
                     validate_flowchart)
from .storage import (EXT_BY_FORMAT, MEDIA_FORMATS, MAX_MEDIA_BYTES,
                      MAX_MEDIA_PER_JOB, MIME_BY_FORMAT, MediaIntegrityError,
                      MediaStorage, MediaStorageError, StagedMedia, new_job_id,
                      new_media_id, reconcile_media_store)
from .validate import (MediaValidationError, MediaValidation, image_dimensions,
                       sanitize_svg, scrub_jpeg, sniff_format, validate_media)

__all__ = [
    # jobs
    "MEDIA_KINDS", "TERMINAL_STATUSES", "MediaJobError", "MediaUnavailableError",
    "MediaJobService", "service_status",
    # render
    "AnimationInvalid", "GraphInvalid", "RenderError", "WebMUnavailable",
    "assemble_webm", "ffmpeg_available", "render_animation",
    "render_animation_poster", "render_flowchart", "validate_animation",
    "validate_flowchart",
    # storage
    "EXT_BY_FORMAT", "MEDIA_FORMATS", "MAX_MEDIA_BYTES", "MAX_MEDIA_PER_JOB",
    "MIME_BY_FORMAT", "MediaIntegrityError", "MediaStorage", "MediaStorageError",
    "StagedMedia", "new_job_id", "new_media_id", "reconcile_media_store",
    # validate
    "MediaValidationError", "MediaValidation", "image_dimensions", "sanitize_svg",
    "scrub_jpeg", "sniff_format", "validate_media",
]
