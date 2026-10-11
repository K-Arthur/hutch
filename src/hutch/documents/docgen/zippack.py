"""Deterministic ZIP repacking for OOXML documents.

python-docx and python-pptx write archive entries stamped with the local clock at
two-second resolution, so two generations of the *same* specification can differ across a
second boundary — under load, the documents slice's own reproducibility test caught
exactly that. Hutch promises byte-identical output for identical specs (hashes are
recorded for every version), so the archive is repacked here with fixed timestamps while
preserving entry order and content. The libraries already produce deterministic part
bytes; only the container metadata varies.
"""

from __future__ import annotations

import io
import zipfile

FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def normalize_ooxml_zip(data: bytes) -> bytes:
    """Rewrite an OOXML container with fixed entry timestamps (content untouched)."""
    source = zipfile.ZipFile(io.BytesIO(data))
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in source.namelist():
                info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, source.read(name))
        return buffer.getvalue()
    finally:
        source.close()
