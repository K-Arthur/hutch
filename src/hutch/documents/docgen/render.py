"""Optional layout rendering for previews (LibreOffice headless, PDF pages).

LibreOffice is an *optional* system dependency: its single-instance profile lock has
caused serialized machines, hung listeners and corrupted bridges elsewhere (evidence rows
E10), so hutch runs one `soffice` process per job with a fresh ``UserInstallation``
profile, a hard wall-clock timeout, and an owned process group that is killed on
timeout/cancel. When the binary is absent the pipeline degrades honestly to structure
previews; it never blocks download or validation.
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
