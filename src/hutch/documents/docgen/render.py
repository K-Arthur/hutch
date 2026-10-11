"""Optional layout rendering for previews (LibreOffice headless, PDF pages).

LibreOffice is an *optional* system dependency: its single-instance profile lock has
caused serialized machines, hung listeners and corrupted bridges elsewhere (evidence rows
E10), so hutch runs one `soffice` process per job with a fresh ``UserInstallation``
profile, a hard wall-clock timeout, and an owned process group that is killed on
timeout/cancel. When the binary is absent the pipeline degrades honestly to structure
previews; it never blocks download or validation.

PDF page previews take the other path: ``render_pdf_pages`` rasterizes an
already-validated, already-committed pdf in-process with pypdfium2 (also treated as
optional — absence degrades the preview, never the document), writing bounded-size
``preview-NNN.png`` assets into the immutable version directory.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

#: formats LibreOffice can lay out for us (input) — pdf is rendered by pypdfium2 instead
LAYOUT_RENDER_FORMATS = frozenset({"docx", "xlsx", "pptx"})
#: formats whose preview without a renderer is the extracted content itself
#: (office structure previews come from the generator libraries; layout pages need soffice)
STRUCTURE_PREVIEW_FORMATS = frozenset({"md", "txt", "csv", "json", "yaml", "docx", "xlsx", "pptx"})

SOFFICE_TIMEOUT_SECONDS = 120.0
MAX_PREVIEW_PAGES = 60
PREVIEW_PAGE_MAX_PX = 1600


def soffice_renderer_path() -> Optional[str]:
    """Path to a usable soffice binary, or None when layout previews are unavailable."""
    return shutil.which("soffice") or shutil.which("libreoffice")


class RenderError(RuntimeError):
    """The optional renderer failed or timed out; the document itself is unaffected."""


def soffice_convert(source: Path, target_format: str, *, timeout: float = SOFFICE_TIMEOUT_SECONDS) -> bytes:
    """Convert one document with a per-job profile; kill the whole process group on overrun.

    The child never sees the caller's HOME (unoconv#449: unwritable HOME hangs silently)
    and never inherits the caller's profile lock.
    """
    binary = soffice_renderer_path()
    if binary is None:
        raise RenderError("LibreOffice is not installed; layout previews are unavailable")
    if not source.is_file():
        raise RenderError("the document to render is missing")
    with tempfile.TemporaryDirectory(prefix="hutch-render-") as tmp:
        profile = Path(tmp) / "profile"
        out_dir = Path(tmp) / "out"
        out_dir.mkdir()
        command = [binary, "--headless", "--norestore", "--nolockcheck",
                   f"-env:UserInstallation=file://{profile}",
                   "--convert-to", target_format, "--outdir", str(out_dir), str(source)]
        try:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        except OSError as exc:
            raise RenderError(f"the renderer could not start: {exc}") from None
        deadline = time.monotonic() + timeout
        while True:
            code = proc.poll()
            if code is not None:
                break
            if time.monotonic() > deadline:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)
                raise RenderError(f"the renderer exceeded its {timeout:.0f}s budget and was stopped")
            time.sleep(0.05)
        if code != 0:
            raise RenderError(f"the renderer exited with status {code}")
        produced = sorted(out_dir.iterdir())
        if not produced:
            raise RenderError("the renderer produced no output")
        return produced[0].read_bytes()


def _pdfium_document(data: bytes):
    """Open pdf bytes with pypdfium2, degrading honestly when it is not installed."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise RenderError("pypdfium2 is not installed; pdf page previews are unavailable") from None
    try:
        return pdfium.PdfDocument(data)
    except Exception as exc:
        raise RenderError(f"the pdf could not be opened for preview rendering: {exc}") from None


def _pdf_page_count(data: bytes) -> int:
    document = _pdfium_document(data)
    try:
        return len(document)
    finally:
        document.close()


def render_pdf_pages(data: bytes, version_dir: Path, *,
                     max_pages: int = MAX_PREVIEW_PAGES,
                     max_px: int = PREVIEW_PAGE_MAX_PX) -> int:
    """Rasterize at most ``max_pages`` pages of a committed pdf into ``version_dir``.

    Each page becomes ``preview-NNN.png`` (1-based, the names ``DocumentStorage.
    read_preview_png`` serves) at a scale bounded so neither side exceeds ``max_px``
    pixels, chmod ``0400`` like the version bytes they decorate. Returns the number of
    pages actually rendered; any failure raises ``RenderError`` — the committed document
    itself is never at stake.
    """
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise RenderError("there are no pdf bytes to render")
    if not 1 <= int(max_pages) <= 999:
        raise RenderError("preview page cap must be between 1 and 999")
    if int(max_px) < 16:
        raise RenderError("preview pixel bound is too small to render a page")
    try:
        version_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise RenderError(f"the preview directory is not writable: {exc}") from None

    document = _pdfium_document(bytes(data))
    rendered = 0
    try:
        page_count = min(len(document), int(max_pages))
        for index in range(page_count):
            page = document[index]
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                raise RenderError(f"page {index + 1} has a degenerate page size")
            scale = min(max_px / width, max_px / height)
            target = version_dir / f"preview-{index + 1:03d}.png"
            try:
                image = page.render(scale=scale).to_pil()
                image.save(target, format="PNG")
                os.chmod(target, 0o400)
            except Exception as exc:
                raise RenderError(f"page {index + 1} could not be rendered: {exc}") from None
            rendered += 1
    except RenderError:
        raise
    except Exception as exc:
        raise RenderError(f"the pdf preview renderer failed: {exc}") from None
    finally:
        document.close()
    if rendered < 1:
        raise RenderError("the pdf has no pages to render")
    return rendered


def soffice_pages_for(source_path: Path, fmt: str) -> int:
    """Page count of an office document as LibreOffice lays it out (optional renderer).

    Used to fill ``page_count`` for formats whose own libraries cannot know it; raises
    ``RenderError`` (not ``DocumentGenerationError``) whenever soffice is absent or fails,
    because layout knowledge is a preview concern, never a validity gate.
    """
    if fmt not in LAYOUT_RENDER_FORMATS:
        raise RenderError(f"soffice layout page counts do not apply to {fmt} documents")
    pdf_bytes = soffice_convert(Path(source_path), "pdf")
    count = _pdf_page_count(pdf_bytes)
    if count < 1:
        raise RenderError("the rendered layout has no pages")
    return count
