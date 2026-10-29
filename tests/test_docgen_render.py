"""docgen.render: pypdfium2 page previews; the soffice page counter is smoke-only.

These tests never require LibreOffice: the pdf preview path is fully in-process. The one
soffice-dependent function, ``soffice_pages_for``, is covered only by a minimal smoke
that skips when no soffice/libreoffice binary exists, its absence must degrade the
pipeline, not the suite.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from hutch.documents.docgen import generate, pdfdoc
from hutch.documents.docgen.render import (MAX_PREVIEW_PAGES, PREVIEW_PAGE_MAX_PX,
                                           RenderError, render_pdf_pages,
                                           soffice_pages_for)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _small_pdf() -> bytes:
    """A real two-page pdf from the registered generator (WeasyPrint, in memory)."""
    result = generate("pdf", {"title": "Preview Smoke", "blocks": [
        {"h1": "First page"}, {"p": "Body text."},
        {"pagebreak": True}, {"p": "Second page."}]})
    assert result.page_count == 2
    return result.data


def _pagebreak_pdf(pages: int) -> bytes:
    """A ``pages``-page pdf from many pagebreak blocks (module internals, no gate)."""
    blocks: list[dict] = []
    for index in range(pages - 1):
        blocks.extend([{"p": f"Page {index + 1} filler."}, {"pagebreak": True}])
    blocks.append({"p": "Last page."})
    body, _units = pdfdoc._render_blocks(blocks)
    data, count = pdfdoc._render_pdf(pdfdoc._document_html("Many Pages", None, body))
    assert count == pages
    return data


def test_renders_png_pages_for_a_small_pdf(tmp_path: Path):
    version_dir = tmp_path / "v001-abcdef01"
    rendered = render_pdf_pages(_small_pdf(), version_dir)
    assert rendered == 2
    pages = sorted(version_dir.glob("preview-*.png"))
    assert [p.name for p in pages] == ["preview-001.png", "preview-002.png"]
    for page in pages:
        data = page.read_bytes()
        assert data.startswith(PNG_SIGNATURE)
        assert oct(os.stat(page).st_mode & 0o777) == "0o400", \
            "preview assets are as read-only as the version bytes they decorate"
    from PIL import Image
    for page in pages:
        with Image.open(page) as image:
            width, height = image.size
        assert width <= PREVIEW_PAGE_MAX_PX and height <= PREVIEW_PAGE_MAX_PX, \
            "the render scale must keep every page inside the pixel bound"


def test_page_cap_respected_on_a_200_page_document(tmp_path: Path):
    data = _pagebreak_pdf(200)
    rendered = render_pdf_pages(data, tmp_path / "v001-abcdef02")
    assert rendered == MAX_PREVIEW_PAGES == 60
    pages = sorted((tmp_path / "v001-abcdef02").glob("preview-*.png"))
    assert len(pages) == 60
    assert pages[-1].name == "preview-060.png"
    assert not (tmp_path / "v001-abcdef02" / "preview-061.png").exists(), \
        "no page beyond the cap may be written, even for a 200-page document"
    assert all(page.read_bytes().startswith(PNG_SIGNATURE) for page in pages)


def test_explicit_max_pages_bound_is_honoured(tmp_path: Path):
    version_dir = tmp_path / "v001-abcdef03"
    rendered = render_pdf_pages(_small_pdf(), version_dir, max_pages=1)
    assert rendered == 1
    assert (version_dir / "preview-001.png").exists()
    assert not (version_dir / "preview-002.png").exists()


def test_failures_raise_rendererror(tmp_path: Path):
    with pytest.raises(RenderError, match="no pdf bytes"):
        render_pdf_pages(b"", tmp_path / "v")
    with pytest.raises(RenderError, match="could not be opened"):
        render_pdf_pages(b"%PDF-not-really", tmp_path / "v")
    with pytest.raises(RenderError, match="page cap"):
        render_pdf_pages(_small_pdf(), tmp_path / "v", max_pages=0)


# ----------------------------------------------------- soffice-dependent (smoke only)


def test_soffice_pages_for_refuses_non_layout_formats(tmp_path: Path):
    """The format guard needs no soffice: refusing md/txt is local, honest, and testable."""
    source = tmp_path / "notes.md"
    source.write_text("# hello", encoding="utf-8")
    with pytest.raises(RenderError, match="md"):
        soffice_pages_for(source, "md")


@pytest.mark.skipif(shutil.which("soffice") is None,
                    reason="soffice is not installed; layout page counts are unavailable")
def test_soffice_pages_for_smoke(tmp_path: Path):
    """Minimal smoke: only runs when soffice exists (the suite never requires it)."""
    result = generate("docx", {"blocks": [{"p": "page one"}, {"pagebreak": True},
                                          {"p": "page two"}]})
    source = tmp_path / "two-pages.docx"
    source.write_bytes(result.data)
    count = soffice_pages_for(source, "docx")
    assert isinstance(count, int) and count >= 1
