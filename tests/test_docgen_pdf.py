"""PDF generator: fixed-template rendering, independent pypdf validation, defenses."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

import weasyprint
from hutch.documents.docgen import (DocumentGenerationError, GeneratedDocument, generate,
                                    pdfdoc, supported_formats)
from hutch.documents.docgen.pdfdoc import MAX_BLOCKS, MAX_TABLE_ROWS

LONG_CELL = "w" * 100
OTHER_LONG_CELL = "Z" * 100
SCRIPT_TEXT = 'Password helper <script>alert("hutch")</script> keep <img src="file:///etc/passwd">'


def _spec(**overrides: object) -> dict:
    spec: dict = {"title": "Quarterly Report", "blocks": [{"p": "Body text."}]}
    spec.update(overrides)
    return spec


def _reader(result: GeneratedDocument) -> PdfReader:
    return PdfReader(io.BytesIO(result.data))


def _full_text(result: GeneratedDocument) -> str:
    return "\n".join(page.extract_text() or "" for page in _reader(result).pages)


def _squash(text: str) -> str:
    return "".join(text.split())


def test_pdf_registers_and_reports_contract():
    assert "pdf" in supported_formats()
    result = generate("pdf", _spec())
    assert isinstance(result, GeneratedDocument)
    assert result.generator == f"hutch docgen pdf 1.0 (WeasyPrint {weasyprint.__version__})"
    assert result.data.startswith(b"%PDF")
    assert result.validation_state == "passed" and result.findings == []
    assert result.preview_mode == "pages" and result.preview_data == {"kind": "pages"}
    assert result.page_count == len(_reader(result).pages) >= 1


def test_blocks_round_trip_as_selectable_text_via_pypdf():
    spec = _spec(subtitle="Season <2026> — édition", blocks=[
        {"h1": "Section One"}, {"h2": "Sub"}, {"h3": "Subsub"}, {"h4": "Subsubsub"},
        {"p": "A paragraph with a distinctive Zyzzogeton marker."},
        {"p": "A centered line.", "align": "center"},
        {"bullets": ["first bullet", "second bullet"]},
        {"numbers": ["step one", "step two"]},
        {"quote": "A quoted line worth keeping."},
        {"table": {"header": ["Item", "Qty"], "rows": [["ZytheLast", "7"]]}},
        {"caption": "Table 1 — inventory"},
        {"pagebreak": True},
        {"p": "Second page content."},
    ])
    result = generate("pdf", spec)
    reader = _reader(result)
    assert 1 <= len(reader.pages) <= 120
    first_page = " ".join((reader.pages[0].extract_text() or "").split())
    assert "Quarterly Report" in first_page, "the title must be selectable text on page 1"
    assert "Season <2026> — édition" in first_page, "the subtitle must survive escaping"
    assert reader.metadata.title == "Quarterly Report"
    text = _squash(_full_text(result))
    assert "Zyzzogeton" in text and "ZytheLast" in text, \
        "the last content unit must appear as text, not raster"
    assert "firstbullet" in text and "stepone" in text and "Aquotedline" in text
    assert "Table1—inventory" in text
    body, _units = pdfdoc._render_blocks(spec["blocks"])
    assert 'class="doc-align-center"' in body


def test_empty_blocks_and_unknown_spec_keys_raise():
    with pytest.raises(DocumentGenerationError, match="at least one block"):
        generate("pdf", _spec(blocks=[]))
    with pytest.raises(DocumentGenerationError, match="unknown pdf spec key"):
        generate("pdf", _spec(author="nobody"))


def test_wide_table_wraps_instead_of_clipping():
    result = generate("pdf", _spec(blocks=[
        {"table": {"header": ["Wide column A", "Wide column B"],
                   "rows": [[LONG_CELL, OTHER_LONG_CELL]]}}]))
    text = _squash(_full_text(result))
    assert LONG_CELL in text, "a 100-char cell must wrap and stay selectable, never clip"
    assert OTHER_LONG_CELL in text
    assert "WidecolumnA" in text
    assert result.page_count == 1


def test_script_and_img_text_render_inert_and_escaped():
    result = generate("pdf", _spec(blocks=[{"p": SCRIPT_TEXT}]))
    text = _squash(_full_text(result))
    assert '<script>alert("hutch")</script>' in text, "markup must survive as literal text"
    assert '<imgsrc="file:///etc/passwd">' in text
    body, _units = pdfdoc._render_blocks([{"p": SCRIPT_TEXT}])
    built = pdfdoc._document_html("t", None, body)
    assert "&lt;script&gt;" in built and "&lt;img src=" in built, \
        "every text insertion point must escape"
    assert "<script>" not in built and "<img " not in built


def test_url_fetcher_refuses_every_scheme():
    fetcher = pdfdoc._DenyEveryURL()
    for url in ("file:///etc/passwd", "https://hutch.invalid/font.css",
                "http://127.0.0.1:9/x", "data:image/svg+xml,<svg/>"):
        with pytest.raises(DocumentGenerationError):
            fetcher.fetch(url)


def test_bounds_reject_oversized_specs():
    with pytest.raises(DocumentGenerationError, match="2,000 blocks"):
        generate("pdf", _spec(blocks=[{"pagebreak": True}] * (MAX_BLOCKS + 1)))
    with pytest.raises(DocumentGenerationError, match="500 rows"):
        generate("pdf", _spec(blocks=[{"table": {"header": ["c"],
                                                 "rows": [["x"]] * (MAX_TABLE_ROWS + 1)}}]))


def test_document_over_120_pages_is_refused():
    pages = [{"p": "Page filler."}, {"pagebreak": True}] * 130
    with pytest.raises(DocumentGenerationError, match="120 pages"):
        generate("pdf", _spec(blocks=pages))


def test_page_previews_cap_is_disclosed_as_warning():
    pages = [{"p": "Page filler."}, {"pagebreak": True}] * 61
    result = generate("pdf", _spec(blocks=pages))
    assert result.validation_state == "passed_with_warnings"
    assert result.page_count > 60
    codes = [finding["code"] for finding in result.findings]
    assert "pdf_preview_page_cap" in codes


def test_bad_specs_raise_instead_of_coercing():
    with pytest.raises(DocumentGenerationError, match="title"):
        generate("pdf", {"blocks": [{"p": "x"}]})
    with pytest.raises(DocumentGenerationError, match="title"):
        generate("pdf", _spec(title="   "))
    with pytest.raises(DocumentGenerationError, match="title"):
        generate("pdf", _spec(title=42))
    with pytest.raises(DocumentGenerationError, match="subtitle"):
        generate("pdf", _spec(subtitle=["nope"]))
    with pytest.raises(DocumentGenerationError, match="blocks"):
        generate("pdf", {"title": "t"})
    with pytest.raises(DocumentGenerationError, match="blocks"):
        generate("pdf", _spec(blocks="nope"))
    with pytest.raises(DocumentGenerationError, match="exactly one"):
        generate("pdf", _spec(blocks=[{"p": "a", "h1": "b"}]))
    with pytest.raises(DocumentGenerationError, match="unknown key"):
        generate("pdf", _spec(blocks=[{"marquee": "welcome"}]))
    with pytest.raises(DocumentGenerationError, match="must be an object"):
        generate("pdf", _spec(blocks=[["p", "not a dict"]]))
    with pytest.raises(DocumentGenerationError, match="string"):
        generate("pdf", _spec(blocks=[{"h1": 9}]))
    with pytest.raises(DocumentGenerationError, match="align is only valid with p"):
        generate("pdf", _spec(blocks=[{"h1": "x", "align": "center"}]))
    with pytest.raises(DocumentGenerationError, match="align must be one of"):
        generate("pdf", _spec(blocks=[{"p": "x", "align": "middle"}]))
    with pytest.raises(DocumentGenerationError, match="array of strings"):
        generate("pdf", _spec(blocks=[{"bullets": "one, two"}]))
    with pytest.raises(DocumentGenerationError, match="must be a string"):
        generate("pdf", _spec(blocks=[{"numbers": ["ok", 2]}]))
    with pytest.raises(DocumentGenerationError, match="table"):
        generate("pdf", _spec(blocks=[{"table": {"rows": [["x"]]}}]))
    with pytest.raises(DocumentGenerationError, match="rows must be an array"):
        generate("pdf", _spec(blocks=[{"table": {"header": ["c"], "rows": "nope"}}]))
    with pytest.raises(DocumentGenerationError, match="row 0"):
        generate("pdf", _spec(blocks=[{"table": {"header": ["c"], "rows": ["not-a-row"]}}]))
    with pytest.raises(DocumentGenerationError, match="expected 1"):
        generate("pdf", _spec(blocks=[{"table": {"header": ["c"],
                                                 "rows": [["a", "b"]]}}]))
    with pytest.raises(DocumentGenerationError, match="must be a string"):
        generate("pdf", _spec(blocks=[{"table": {"header": ["c"],
                                                 "rows": [[{"deep": 1}]]}}]))
    with pytest.raises(DocumentGenerationError, match="pagebreak"):
        generate("pdf", _spec(blocks=[{"pagebreak": False}]))
