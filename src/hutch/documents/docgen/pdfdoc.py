"""PDF generator: typed block specification → hutch-authored HTML → WeasyPrint.

Blocks share the vocabulary and shape rules of :mod:`.docxgen`, one content key per
block, string-only text, table header and rows, ``align`` on ``p`` only, so one
specification renders to either format. The HTML comes only from this module's fixed
template filled with validated, escaped block content: a specification can never inject
markup (``html.escape`` at every insertion point), and WeasyPrint's resource fetcher is
replaced with one that refuses every URL, so a document can neither read ``file://``
paths, nor touch the network, nor pull ``data:`` payloads (vendor security guidance for
untrusted HTML; evidence rows E9, E11). Wide tables cannot clip: the print stylesheet
pins ``table-layout: fixed`` with break-anywhere wrapping, so cell text wraps and
survives as selectable text (WeasyPrint#2417 class). Generation is one gate: the bytes
are re-opened with pypdf (an independent reader) and the page count, metadata title,
first-page title and last content unit must be present as selectable text before
anything is returned. Layout runs in-process here; the bounded subprocess that keeps
large renders off the host's memory is the pipeline's concern.
"""

from __future__ import annotations

import html
import io
import logging
import re
import string
from typing import Any

import weasyprint
from pypdf import PdfReader
from weasyprint.urls import FatalURLFetchingError, URLFetcher

from . import DocumentGenerationError, GeneratedDocument, register
from .render import MAX_PREVIEW_PAGES

GENERATOR = f"hutch docgen pdf 1.0 (WeasyPrint {weasyprint.__version__})"
MAX_BLOCKS = 2_000
MAX_TABLE_ROWS = 500
MAX_TEXT_CHARS = 100_000
MAX_PAGES = 120
_MAX_FINDINGS = 20
_MAX_FINDING_DETAIL = 300

_CONTENT_KEYS = frozenset({"h1", "h2", "h3", "h4", "p", "bullets", "numbers", "quote",
                           "table", "caption", "pagebreak"})
_BLOCK_KEYS = _CONTENT_KEYS | {"align"}
_ALIGNMENTS = frozenset({"left", "center", "right"})
#: control characters that XML/HTML toolchains replace or drop; rejecting them here
#: fails the spec at the boundary instead of corrupting text extraction late
_INVALID_TEXT_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")

_FONT_STACK = '"Liberation Sans", "DejaVu Sans", sans-serif'

#: print stylesheet owned by this module: A4 page with a running page-number footer,
#: the probed font stack, heading hierarchy and blockquote styling, and the wide-table
#: defense, fixed layout plus break-anywhere wrapping so long cells wrap, never clip
_CSS = f"""
@page {{
  size: A4;
  margin: 22mm 18mm 24mm 18mm;
  @bottom-center {{
    content: counter(page) " / " counter(pages);
    font-family: {_FONT_STACK};
    font-size: 8.5pt;
    color: #555555;
  }}
}}
body {{
  font-family: {_FONT_STACK};
  font-size: 10.5pt;
  line-height: 1.45;
  color: #1a1a1a;
  margin: 0;
  overflow-wrap: anywhere;
  word-wrap: break-word;
}}
h1, h2, h3, h4 {{ line-height: 1.25; color: #111111; }}
h1 {{ font-size: 20pt; margin: 18pt 0 6pt 0; }}
h2 {{ font-size: 15pt; margin: 14pt 0 5pt 0; }}
h3 {{ font-size: 12.5pt; margin: 12pt 0 4pt 0; }}
h4 {{ font-size: 11pt; margin: 10pt 0 4pt 0; }}
p {{ margin: 0 0 7pt 0; }}
h1.doc-title {{ font-size: 22pt; margin: 0 0 4pt 0; }}
p.doc-subtitle {{ font-size: 12.5pt; color: #444444; margin: 0 0 16pt 0; }}
p.doc-caption {{ font-size: 9pt; color: #555555; font-style: italic;
                 margin: 3pt 0 10pt 0; }}
p.doc-align-left {{ text-align: left; }}
p.doc-align-center {{ text-align: center; }}
p.doc-align-right {{ text-align: right; }}
blockquote {{
  margin: 8pt 0 10pt 0;
  padding: 2pt 0 2pt 10pt;
  border-left: 2.5pt solid #888888;
  color: #333333;
  font-style: italic;
}}
blockquote p {{ margin: 0; }}
ul, ol {{ margin: 4pt 0 9pt 0; padding-left: 18pt; }}
li {{ margin: 0 0 2.5pt 0; overflow-wrap: anywhere; word-wrap: break-word; }}
table {{
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  margin: 8pt 0 10pt 0;
}}
th, td {{
  border: 0.5pt solid #999999;
  padding: 3pt 5pt;
  text-align: left;
  vertical-align: top;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}}
thead th {{ background-color: #ececec; }}
tbody tr:nth-child(even) td {{ background-color: #f7f7f7; }}
.doc-pagebreak {{ break-before: page; }}
"""

#: the only HTML hutch ever renders for this format; every slot is validated content
_PAGE_TEMPLATE = string.Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>$title</title>
<style>$css</style>
</head>
<body>
<h1 class="doc-title">$title</h1>$subtitle
$body
</body>
</html>
""")


class _DenyEveryURL(URLFetcher):
    """Fetcher that refuses every resource; hutch PDFs embed no external assets.

    ``fail_on_errors`` promotes the refusal to WeasyPrint's fatal error, which stops
    rendering instead of leaving a gap where an image or stylesheet would have been.
    """

    def __init__(self) -> None:
        super().__init__(fail_on_errors=True)

    def fetch(self, url: str, headers: Any = None) -> Any:
        raise DocumentGenerationError(
            f"hutch documents embed no external resources (refused: {url})")


class _EngineWarnings(logging.Handler):
    """Collects the render engine's warnings so they surface as findings, not silence."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if len(self.messages) < _MAX_FINDINGS:
            self.messages.append(record.getMessage()[:_MAX_FINDING_DETAIL])


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _text_field(value: Any, what: str) -> str:
    """Every string slot of the spec: typed, bounded, control-char free, no coercion."""
    if not isinstance(value, str):
        raise DocumentGenerationError(f"{what} must be a string")
    if len(value) > MAX_TEXT_CHARS:
        raise DocumentGenerationError(f"{what} exceeds {MAX_TEXT_CHARS:,} characters")
    if _INVALID_TEXT_CHARS.search(value) is not None:
        raise DocumentGenerationError(
            f"{what} contains characters that are not valid in document text")
    return value


def _string_list(value: Any, what: str) -> list[str]:
    if not isinstance(value, list):
        raise DocumentGenerationError(f"{what} must be an array of strings")
    return [_text_field(item, f"{what}[{index}]") for index, item in enumerate(value)]


def _render_block(index: int, block: Any, units: list[str]) -> str:
    """Validate one block against the shared vocabulary and render it to HTML."""
    what = f"block {index}"
    if not isinstance(block, dict):
        raise DocumentGenerationError(f"{what} must be an object")
    unknown_keys = set(block) - _BLOCK_KEYS
    if unknown_keys:
        raise DocumentGenerationError(
            f"{what} has unknown key(s): {', '.join(sorted(unknown_keys))}")
    content_keys = set(block) & _CONTENT_KEYS
    if len(content_keys) != 1:
        raise DocumentGenerationError(
            f"{what} must contain exactly one of: {', '.join(sorted(_CONTENT_KEYS))}")
    kind = content_keys.pop()
    if "align" in block and kind != "p":
        raise DocumentGenerationError(f"{what} align is only valid with p")

    if kind in ("h1", "h2", "h3", "h4"):
        text = _text_field(block[kind], f"{what} text")
        units.append(text)
        return f"<{kind}>{_esc(text)}</{kind}>"
    if kind == "p":
        text = _text_field(block[kind], f"{what} text")
        units.append(text)
        css = ""
        if "align" in block:
            align = block["align"]
            if not isinstance(align, str) or align not in _ALIGNMENTS:
                raise DocumentGenerationError(
                    f"{what} align must be one of: {', '.join(sorted(_ALIGNMENTS))}")
            css = f' class="doc-align-{align}"'
        return f"<p{css}>{_esc(text)}</p>"
    if kind in ("bullets", "numbers"):
        tag = "ul" if kind == "bullets" else "ol"
        items = []
        for item in _string_list(block[kind], f"{what} {kind}"):
            units.append(item)
            items.append(f"<li>{_esc(item)}</li>")
        return f"<{tag}>{''.join(items)}</{tag}>"
    if kind in ("quote", "caption"):
        text = _text_field(block[kind], f"{what} text")
        units.append(text)
        if kind == "quote":
            return f"<blockquote><p>{_esc(text)}</p></blockquote>"
        return f'<p class="doc-caption">{_esc(text)}</p>'
    if kind == "table":
        return _render_table(index, block[kind], units)
    if kind == "pagebreak":
        if block[kind] is not True:
            raise DocumentGenerationError(f'{what} must be {{"pagebreak": true}}')
        return '<div class="doc-pagebreak"></div>'
    raise DocumentGenerationError(f"{what} has an unknown block kind: {kind!r}")


def _render_table(index: int, table_spec: Any, units: list[str]) -> str:
    """Fixed-layout table: header and rows are required, all strings, one width."""
    what = f"block {index} table"
    if (not isinstance(table_spec, dict) or "header" not in table_spec
            or "rows" not in table_spec):
        raise DocumentGenerationError(
            f'{what} must be {{"table": {{"header": [...], "rows": [[...], ...]}}}}')
    unknown_table_keys = set(table_spec) - {"header", "rows"}
    if unknown_table_keys:
        raise DocumentGenerationError(
            f"{what} has unknown key(s): {', '.join(sorted(unknown_table_keys))}")
    header = _string_list(table_spec["header"], f"{what} header")
    if not header:
        raise DocumentGenerationError(f"{what} header must have at least one column")
    raw_rows = table_spec["rows"]
    if not isinstance(raw_rows, list):
        raise DocumentGenerationError(f"{what} rows must be an array")
    if len(raw_rows) > MAX_TABLE_ROWS:
        raise DocumentGenerationError(f"{what} exceeds {MAX_TABLE_ROWS:,} rows")
    head_cells = "".join(f"<th>{_esc(cell)}</th>" for cell in header)
    body_rows = []
    for row_index, row in enumerate(raw_rows):
        cells = _string_list(row, f"{what} row {row_index}")
        if len(cells) != len(header):
            raise DocumentGenerationError(
                f"{what} row {row_index} has {len(cells)} cells, expected {len(header)}")
        body_rows.append(f"<tr>{''.join(f'<td>{_esc(cell)}</td>' for cell in cells)}</tr>")
        units.extend(cells)
    units.extend(header)
    return (f"<table><thead><tr>{head_cells}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table>")


def _render_blocks(blocks: list[Any]) -> tuple[str, list[str]]:
    """Validate and render every block; returns body HTML and the document's text units."""
    parts: list[str] = []
    units: list[str] = []
    for index, block in enumerate(blocks):
        parts.append(_render_block(index, block, units))
    return "\n".join(parts), units


def _document_html(title: str, subtitle: str | None, body: str) -> str:
    subtitle_html = f'\n<p class="doc-subtitle">{_esc(subtitle)}</p>' if subtitle else ""
    return _PAGE_TEMPLATE.substitute(title=_esc(title), subtitle=subtitle_html,
                                     body=body, css=_CSS)


def _render_pdf(html_source: str) -> tuple[bytes, int]:
    """Render with the denying fetcher; returns bytes and the laid-out page count."""
    try:
        document = weasyprint.HTML(string=html_source,
                                   url_fetcher=_DenyEveryURL()).render()
        data = document.write_pdf()
    except FatalURLFetchingError as exc:
        raise DocumentGenerationError(
            f"the document attempted to load an external resource and was stopped: {exc}"
        ) from None
    except Exception as exc:
        raise DocumentGenerationError(
            f"the pdf engine failed to render this document: {exc}") from None
    return data, len(document.pages)


def _spot_check_word(units: list[str], subtitle: str | None, title: str) -> str:
    """The most distinctive word of the document's last text unit, for the parse-back."""
    for unit in reversed(units):
        words = unit.split()
        if words:
            return max(words, key=len)
    for fallback in (subtitle, title):
        words = (fallback or "").split()
        if words:
            return max(words, key=len)
    return ""


def _validate_pdf_bytes(data: bytes, title: str, spot_word: str) -> int:
    """Re-open the written bytes with pypdf; the gate is selectable text, not trust."""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise DocumentGenerationError(f"the written pdf did not parse back: {exc}") from None
    page_count = len(reader.pages)
    if page_count < 1:
        raise DocumentGenerationError("the written pdf has no pages")
    if page_count > MAX_PAGES:
        raise DocumentGenerationError(f"document would exceed {MAX_PAGES} pages")
    metadata_title = reader.metadata.title if reader.metadata else None
    if metadata_title != title:
        raise DocumentGenerationError("the document title did not survive into the pdf metadata")
    first_page = " ".join((reader.pages[0].extract_text() or "").split())
    if " ".join(title.split()) not in first_page:
        raise DocumentGenerationError(
            "the title is not selectable text on the first page of the written pdf")
    if spot_word:
        every_page = "\n".join((page.extract_text() or "") for page in reader.pages)
        joined = " ".join(every_page.split())
        if spot_word not in joined and spot_word not in "".join(every_page.split()):
            raise DocumentGenerationError(
                "the document's last content is missing from the written pdf")
    return page_count


@register("pdf")
def _gen_pdf(spec: dict[str, Any]) -> GeneratedDocument:
    """Render ``{"title": str, "subtitle"?: str, "blocks": [...]}`` and gate the bytes."""
    unknown = set(spec) - {"title", "subtitle", "blocks"}
    if unknown:
        raise DocumentGenerationError(f"unknown pdf spec key(s): {', '.join(sorted(unknown))}")
    title = _text_field(spec.get("title"), "title")
    if not title.strip():
        raise DocumentGenerationError("title must not be blank")
    subtitle = None
    if "subtitle" in spec:
        subtitle = _text_field(spec["subtitle"], "subtitle")
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        raise DocumentGenerationError('pdf content must include a "blocks" list')
    if not blocks:
        raise DocumentGenerationError("the document must contain at least one block")
    if len(blocks) > MAX_BLOCKS:
        raise DocumentGenerationError(f"the document exceeds {MAX_BLOCKS:,} blocks")
    body, units = _render_blocks(blocks)
    html_source = _document_html(title, subtitle, body)
    warnings = _EngineWarnings()
    logger = logging.getLogger("weasyprint")
    logger.addHandler(warnings)
    try:
        data, page_count = _render_pdf(html_source)
    finally:
        logger.removeHandler(warnings)
    if page_count > MAX_PAGES:
        raise DocumentGenerationError(f"document would exceed {MAX_PAGES} pages")
    findings = [{"code": "pdf_engine_warning", "detail": message}
                for message in warnings.messages]
    if page_count > MAX_PREVIEW_PAGES:
        findings.append({"code": "pdf_preview_page_cap", "detail":
                         f"page previews render at most {MAX_PREVIEW_PAGES} pages "
                         f"of this {page_count}-page document"})
    page_count = _validate_pdf_bytes(
        data, title, _spot_check_word(units, subtitle, title))
    return GeneratedDocument(
        data=data,
        generator=GENERATOR,
        validation_state="passed_with_warnings" if findings else "passed",
        findings=findings,
        preview_mode="pages",
        preview_data={"kind": "pages"},
        page_count=page_count)
