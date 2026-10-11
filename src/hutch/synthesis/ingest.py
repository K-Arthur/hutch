"""Bounded source ingestion: complete threads and difficult whitepapers.

Two ingest paths feed the synthesis manifest:

* :func:`ingest_thread` reconstructs a social thread as the **author's ordered argument**
  by following reply edges between the author's own posts. Replies from other accounts,
  quoted posts by others, and engagement order never become the argument; duplicates are
  recorded, not repeated; corrections are marked, not rewritten; inaccessible posts become
  typed gaps and the coverage statement says exactly how many posts were accessible
  ("18 of 20 accessible") — missing text is never invented.

* :func:`ingest_paper` extracts the structure of a technical paper: page text within
  bounds, numbered sections, caption candidates for figures/tables, equation candidates,
  footnote candidates, and an honest coverage record — encrypted files are refused,
  image-only (scanned) pages are reported instead of silently producing an empty summary,
  and multi-column/reading-order suspicion is disclosed. Extraction is structural:
  candidates are labeled as candidates until a verification step confirms them.

Everything here is deterministic and bounded; nothing calls a model.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .model import CoverageGap, SourceCoverage, SourceRecord, utc_now

# ---------------------------------------------------------------------------
# threads

MAX_THREAD_POSTS = 500
MAX_POST_CHARS = 20_000
MAX_ATTACHMENT_URLS = 20


class ThreadPost(BaseModel):
    """One fetched post. ``accessible`` False models an unavailable item."""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    author_id: str
    author: str = ""
    text: str = ""
    created_at: str = ""
    edited_at: str = ""
    reply_to: str = ""  # post id this replies to, "" for the root
    quoted: str = ""  # post id this quote-posts, "" for none
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    engagement: dict[str, Any] = Field(default_factory=dict)
    accessible: bool = True
    unavailable_reason: Literal["", "deleted", "protected", "not_fetched", "parse_failure"] = ""
    sequence: Optional[int] = None  # platform-reported position, if any

    def normalized_text(self) -> str:
        return re.sub(r"\s+", " ", (self.text or "").strip()).casefold()


class ThreadIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_id: str
    author_id: str
    author: str = ""
    order_basis: Literal["reply-chain"] = "reply-chain"
    ordered: list[ThreadPost] = Field(default_factory=list)  # the author's argument, in order
    author_side_replies: list[ThreadPost] = Field(default_factory=list)  # author → others
    context_replies: list[ThreadPost] = Field(default_factory=list)  # others → author
    quoted_foreign: list[ThreadPost] = Field(default_factory=list)  # quoted posts by others
    duplicates: list[ThreadPost] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)  # post ids marked as corrections
    edited: list[dict[str, str]] = Field(default_factory=list)  # {post_id, edited_at}
    attachments: list[dict[str, Any]] = Field(default_factory=list)  # preserved metadata
    gaps: list[CoverageGap] = Field(default_factory=list)
    coverage: SourceCoverage
    missing_post_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def post_by_id(self, post_id: str) -> Optional[ThreadPost]:
        for p in self.ordered + self.author_side_replies + self.context_replies + self.quoted_foreign:
            if p.post_id == post_id:
                return p
        return None

    def content_sha256(self) -> str:
        h = hashlib.sha256()
        for p in self.ordered:
            h.update(p.post_id.encode("utf-8"))
            h.update(b"\x00")
            h.update(p.text.encode("utf-8"))
            h.update(b"\x1e")
        return h.hexdigest()

    def source_record(self, *, identity: str, title: str = "", origin: str = "",
                      language: str = "") -> SourceRecord:
        return SourceRecord(
            kind="thread",
            identity=identity,
            title=title or f"Thread by {self.author or self.author_id}",
            author=self.author or self.author_id,
            origin=origin,
            content_sha256=self.content_sha256(),
            language=language,
            coverage=self.coverage,
            meta={
                "ordered_posts": len(self.ordered),
                "context_replies": len(self.context_replies),
                "quoted_foreign": len(self.quoted_foreign),
                "duplicates": len(self.duplicates),
                "corrections": list(self.corrections),
                "order_basis": self.order_basis,
            },
        )


_CORRECTION_RE = re.compile(
    r"\b(correction|correcting|i was wrong|to clarify|correction:)\b", re.IGNORECASE
)


def ingest_thread(
    posts: Iterable[ThreadPost | dict[str, Any]],
    *,
    expected_count: Optional[int] = None,
    identity: str = "",
) -> ThreadIngestResult:
    """Reconstruct the author's ordered argument from fetched posts.

    ``expected_count`` is the only trusted source of a total ("20 posts"): it must come
    from explicit evidence (the author said so, or the fetch layer knows the count).
    Otherwise gaps are derived from broken reply edges and reported without a total.
    """
    post_list: list[ThreadPost] = []
    seen_ids: set[str] = set()
    for raw in posts:
        p = raw if isinstance(raw, ThreadPost) else ThreadPost.model_validate(raw)
        if p.post_id in seen_ids:
            continue  # a refetch of the same post id is one post
        seen_ids.add(p.post_id)
        if len(p.text) > MAX_POST_CHARS:
            p = p.model_copy(update={"text": p.text[:MAX_POST_CHARS]})
        for att in p.attachments[:MAX_ATTACHMENT_URLS]:
            att.setdefault("preserved", True)
        post_list.append(p)
    if not post_list:
        raise ValueError("no posts to ingest")

    by_id = {p.post_id: p for p in post_list}
    accessible = [p for p in post_list if p.accessible]

    # Root: the only post with no reply_to, else the earliest by (sequence, created_at).
    roots = [p for p in accessible if not p.reply_to]
    if not roots:
        raise ValueError("no root post found (every post declares a reply_to)")
    roots.sort(key=lambda p: (p.sequence if p.sequence is not None else 10**9, p.created_at or ""))
    root = roots[0]
    author_id = root.author_id

    ordered: list[ThreadPost] = [root]
    author_side_replies: list[ThreadPost] = []
    context_replies: list[ThreadPost] = []
    quoted_foreign: list[ThreadPost] = []
    duplicates: list[ThreadPost] = []
    corrections: list[str] = []
    edited: list[dict[str, str]] = []
    gaps: list[CoverageGap] = []
    missing_post_ids: list[str] = []
    notes: list[str] = []

    # children index by reply_to — including posts we could not read, so a deleted post
    # in the middle of a chain does not orphan everything after it.
    children: dict[str, list[ThreadPost]] = {}
    for p in post_list:
        if p.reply_to:
            children.setdefault(p.reply_to, []).append(p)

    def _order_key(p: ThreadPost) -> tuple[int, str, str]:
        return (p.sequence if p.sequence is not None else 10**9, p.created_at or "", p.post_id)

    # Walk the author's chain: root -> the author's post replying to it -> ...
    current = root
    seen_text: dict[str, str] = {root.normalized_text(): root.post_id} if root.normalized_text() else {}
    if root.edited_at:
        edited.append({"post_id": root.post_id, "edited_at": root.edited_at})
    while True:
        kids = sorted(children.get(current.post_id, []), key=_order_key)
        nxt = next((k for k in kids if k.author_id == author_id), None)
        if nxt is None:
            break
        if not nxt.accessible:
            # Traverse through the unavailable post; it stays a gap, never content.
            current = nxt
            continue
        if nxt.normalized_text() and nxt.normalized_text() in seen_text:
            duplicates.append(nxt.model_copy(update={"sequence": nxt.sequence}))
            current = nxt  # keep walking: the chain may resume after a repeated post
            continue
        if nxt.normalized_text():
            seen_text[nxt.normalized_text()] = nxt.post_id
        if nxt.edited_at:
            edited.append({"post_id": nxt.post_id, "edited_at": nxt.edited_at})
        if _CORRECTION_RE.search(nxt.text or ""):
            corrections.append(nxt.post_id)
        # A correction that does not literally continue the chain is still surfaced when
        # it replies to an earlier author post (handled in the pass below).
        ordered.append(nxt)
        current = nxt

    # Pass 2: author posts that reply to a non-author post, and other-author replies.
    for p in accessible:
        if p.post_id in {q.post_id for q in ordered} or p.post_id in {d.post_id for d in duplicates}:
            continue
        if p.author_id == author_id:
            if p.reply_to and p.reply_to in by_id and by_id[p.reply_to].author_id != author_id:
                author_side_replies.append(p)
            elif not p.reply_to:
                continue  # an alternative root we did not choose
            else:
                # author post replying to an author post we could not place: treat as
                # a side branch; it is still the author's words, not the ordered argument.
                author_side_replies.append(p)
        else:
            # context: other accounts replying to the thread or to the author
            context_replies.append(p)
        if p.edited_at:
            edited.append({"post_id": p.post_id, "edited_at": p.edited_at})

    # Pass 3: quoted posts.
    for p in post_list:
        if not p.quoted:
            continue
        quoted = by_id.get(p.quoted)
        if quoted is None:
            missing_post_ids.append(p.quoted)
            gaps.append(CoverageGap(
                reason="not_fetched",
                where=f"quoted by {p.post_id}",
                note="the quoted post was not fetched; its text is not used",
            ))
            continue
        if quoted.author_id != author_id:
            quoted_foreign.append(quoted)
        elif quoted.post_id not in {q.post_id for q in ordered}:
            notes.append(
                f"{p.post_id} quotes an earlier post of the same author ({quoted.post_id}); "
                "it is a reference, not a new argument unit"
            )

    # Gaps: referenced posts that are not accessible, and gaps between known positions.
    for p in post_list:
        if not p.accessible:
            gaps.append(CoverageGap(
                reason=p.unavailable_reason or "unknown",
                where=f"post {p.post_id}",
                note="the post was reported but not accessible",
            ))
            missing_post_ids.append(p.post_id)
    for p in accessible:
        if p.reply_to and p.reply_to not in by_id:
            gaps.append(CoverageGap(
                reason="not_fetched",
                where=f"replied to by post {p.post_id}",
                note="the parent post was not fetched",
            ))
            missing_post_ids.append(p.reply_to)

    attachments: list[dict[str, Any]] = []
    for p in ordered + author_side_replies + quoted_foreign:
        for att in p.attachments:
            attachments.append({"post_id": p.post_id, **att})

    # Coverage counts the *author's* posts: other accounts' replies are context and a
    # quoted post by a third party is never one of "the 20 posts".
    author_accessible = len(ordered) + len(duplicates) + len(author_side_replies)
    expected = expected_count
    if expected is not None and expected < author_accessible:
        expected = author_accessible  # never report more accessible than expected
    if expected is not None:
        inaccessible_author = sum(
            1 for p in post_list if not p.accessible and p.author_id == author_id
        )
        unseen = expected - author_accessible - inaccessible_author
        if unseen > 0:
            gaps.append(CoverageGap(
                reason="not_fetched",
                where="",
                note=f"{unseen} of the {expected} expected author posts were never retrieved",
            ))
    state = "complete"
    if not author_accessible:
        state = "inaccessible"
    elif (expected is not None and author_accessible < expected) or gaps:
        state = "partial"
    if author_side_replies:
        notes.append(
            f"{len(author_side_replies)} author post(s) are outside the reply chain and are "
            "listed separately, not woven into the ordered argument"
        )
    coverage = SourceCoverage(
        state=state,
        expected_units=expected,
        accessible_units=author_accessible,
        gaps=gaps,
        limits=[
            f"ordered argument: {len(ordered)} of {author_accessible} accessible author posts",
            *([f"duplicate posts excluded from the argument: {len(duplicates)}"] if duplicates else []),
        ],
    )
    return ThreadIngestResult(
        root_id=root.post_id,
        author_id=author_id,
        author=root.author,
        ordered=ordered,
        author_side_replies=author_side_replies,
        context_replies=context_replies,
        quoted_foreign=quoted_foreign,
        duplicates=duplicates,
        corrections=corrections,
        edited=edited,
        attachments=attachments,
        gaps=gaps,
        coverage=coverage,
        missing_post_ids=sorted(set(missing_post_ids)),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# whitepapers

MAX_PAPER_PAGES = 400
MAX_PAGE_CHARS = 40_000
MAX_TOTAL_CHARS = 2_000_000
MIN_TEXT_CHARS = 25  # below this a page is treated as image-only

SectionHeading = re.compile(
    r"^\s*((?:\d+(?:\.\d+)*)|(?:[IVXLC]+))[.)]?\s+([A-Z][^\n]{2,90})\s*$"
)
#: Unnumbered headings that carry structure a summary must not miss.
CONVENTIONAL_HEADING_RE = re.compile(
    r"^\s*(abstract|references|bibliography|acknowledg(?:e)?ments|conclusions?|"
    r"limitations?|threats to validity|future work|appendix(?:\s+[A-Z])?)\s*$",
    re.IGNORECASE,
)
CAPTION_RE = re.compile(
    r"\b(Figure|Fig\.?|Table|Algorithm|Listing|Equation|Eq\.?)\s*([A-Za-z]?\d+[a-z]?)\b[:.]?\s*(.{0,300})",
    re.IGNORECASE,
)
MATH_HINT_RE = re.compile(r"[∑∫≈≤≥±×÷√∏∂∞αβγδθλμσπφψωΔΩ]|\b[a-zA-Z]\s*=\s*[-+]?\d")
#: A wide mid-line run with a word on each side: the signature of a column boundary in
#: plain-text extraction.
_COLUMN_GAP_RE = re.compile(r"^\s*\S.{8,}?\s{4,}\S")
FOOTNOTE_HINT_RE = re.compile(r"^\s*(\d{1,2}|[a-z])\s*[.)]\s+\S")


class PaperSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str = ""  # "2.1" or "IV"
    title: str
    level: int = 1
    start_page: int
    end_page: int = 0
    heading_kind: Literal["numbered", "conventional"] = "numbered"


class PaperItem(BaseModel):
    """A caption/equation/footnote candidate: located, bounded, and labeled a candidate."""

    model_config = ConfigDict(extra="forbid")

    label: str = ""  # "Table 3", "Figure 2", "Eq. 4"
    kind: Literal["table", "figure", "equation", "footnote", "algorithm", "listing", "other"]
    page: int
    text: str = ""  # caption text or equation line, bounded
    candidate: bool = True
    note: str = ""


class PaperIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceRecord
    page_count: int
    text_chars: int
    sections: list[PaperSection] = Field(default_factory=list)
    tables: list[PaperItem] = Field(default_factory=list)
    figures: list[PaperItem] = Field(default_factory=list)
    equations: list[PaperItem] = Field(default_factory=list)
    footnotes: list[PaperItem] = Field(default_factory=list)
    abstract: str = ""
    has_references: bool = False
    has_limitations_section: bool = False
    scanned_pages: list[int] = Field(default_factory=list)
    multi_column_suspected: bool = False
    extraction: str = "pypdf-text"
    notes: list[str] = Field(default_factory=list)

    def section_titles(self) -> list[str]:
        return [s.title for s in self.sections]

    @property
    def coverage(self) -> SourceCoverage:
        return self.source.coverage

    def item_by_label(self, label: str) -> Optional[PaperItem]:
        for items in (self.tables, self.figures, self.equations):
            for it in items:
                if it.label.casefold() == label.casefold():
                    return it
        return None


class PaperEncryptedError(ValueError):
    """The file is encrypted and could not be opened; nothing was extracted."""


def ingest_paper(
    data: bytes | str,
    *,
    identity: str = "",
    title: str = "",
    author: str = "",
    origin: str = "",
    language: str = "",
    max_pages: int = MAX_PAPER_PAGES,
) -> PaperIngestResult:
    """Extract the structure of a PDF technical paper within hard bounds.

    ``data`` is bytes or a filesystem path string. Encrypted inputs raise
    :class:`PaperEncryptedError`. Image-only pages are listed in ``scanned_pages`` and
    counted as gaps; this function never returns an empty success for a scanned paper.
    """
    import io

    from pypdf import PdfReader  # local import: pypdf is an application dependency

    stream = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else open(data, "rb")
    try:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            try:
                result = reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - pypdf raises several types
                raise PaperEncryptedError("encrypted PDF could not be opened") from exc
            if not result:
                raise PaperEncryptedError("encrypted PDF could not be opened")

        page_count = len(reader.pages)
        truncated_pages = False
        if page_count > max_pages:
            truncated_pages = True

        sections: list[PaperSection] = []
        tables: list[PaperItem] = []
        figures: list[PaperItem] = []
        equations: list[PaperItem] = []
        footnotes: list[PaperItem] = []
        scanned_pages: list[int] = []
        total_chars = 0
        page_texts: list[str] = []
        gap_lines = 0  # lines carrying a wide mid-line run: a column-boundary signature
        nonempty_lines = 0

        limit = min(page_count, max_pages)
        broken_pages: list[int] = []
        for idx in range(limit):
            page_no = idx + 1
            try:
                text = reader.pages[idx].extract_text() or ""
            except Exception:  # noqa: BLE001 - a broken page must not kill the ingest
                text = ""
                broken_pages.append(page_no)
            if len(text) > MAX_PAGE_CHARS:
                text = text[:MAX_PAGE_CHARS]
            if total_chars + len(text) > MAX_TOTAL_CHARS:
                text = text[: max(0, MAX_TOTAL_CHARS - total_chars)]
            total_chars += len(text)
            page_texts.append(text)

            if len(text.strip()) < MIN_TEXT_CHARS:
                # Distinguish an image-only page from a truly blank one.
                try:
                    images = reader.pages[idx].images
                    has_images = bool(images)
                except Exception:  # noqa: BLE001
                    has_images = False
                if has_images:
                    scanned_pages.append(page_no)
                continue

            lines = text.splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped:
                    nonempty_lines += 1
                    if _COLUMN_GAP_RE.search(line):
                        gap_lines += 1
                m = SectionHeading.match(line)
                if m:
                    number, heading = m.group(1), m.group(2).strip()
                    level = number.count(".") + 1 if number[0].isdigit() else 1
                    if sections:
                        # Approximate: a heading found on this page usually ends the
                        # previous section here (same-page starts are the exception).
                        sections[-1].end_page = max(sections[-1].start_page, page_no - 1)
                    sections.append(PaperSection(
                        number=number, title=heading, level=level,
                        start_page=page_no, heading_kind="numbered",
                    ))
                    continue
                cm0 = CONVENTIONAL_HEADING_RE.match(line)
                if cm0:
                    if sections:
                        sections[-1].end_page = max(sections[-1].start_page, page_no - 1)
                    sections.append(PaperSection(
                        number="", title=cm0.group(1).strip().title(), level=1,
                        start_page=page_no, heading_kind="conventional",
                    ))
                    continue
                for cm in CAPTION_RE.finditer(line):
                    kind_word = cm.group(1).lower()
                    kind = {
                        "figure": "figure", "fig.": "figure", "fig": "figure",
                        "table": "table", "algorithm": "algorithm",
                        "listing": "listing", "equation": "equation", "eq.": "equation",
                        "eq": "equation",
                    }.get(kind_word, "other")
                    item = PaperItem(
                        label=f"{cm.group(1).title()} {cm.group(2)}",
                        kind=kind,
                        page=page_no,
                        text=(cm.group(3) or "").strip()[:300],
                    )
                    if kind == "figure":
                        figures.append(item)
                    elif kind == "table":
                        tables.append(item)
                    elif kind in ("algorithm", "listing"):
                        tables.append(item)
                    elif kind == "equation":
                        equations.append(item)
                if MATH_HINT_RE.search(line) and 3 < len(line.strip()) < 200:
                    equations.append(PaperItem(
                        label="", kind="equation", page=page_no, text=line.strip()[:200],
                        note="line-level math candidate; verify against the rendered page",
                    ))
            # footnote candidates: small trailing lines near the page end
            tail = [ln for ln in lines[-6:] if FOOTNOTE_HINT_RE.match(ln) or "†" in ln or "*" in ln]
            for ln in tail:
                s = ln.strip()
                if 0 < len(s) <= 300:
                    footnotes.append(PaperItem(
                        label="", kind="footnote", page=page_no, text=s,
                        note="page-tail candidate; small-font verification pending",
                    ))

        if sections:
            sections[-1].end_page = limit

        # Multi-column suspicion: extraction interleaves columns when many lines carry a
        # wide mid-line run with content on both sides (a column boundary), not merely
        # because most lines are short.
        multi_column = False
        if nonempty_lines >= 8 and gap_lines / nonempty_lines >= 0.15:
            multi_column = True

        title_norm = [s.title.casefold() for s in sections]
        has_refs = any(t.startswith(("references", "bibliography")) for t in title_norm)
        has_limits = any(
            ("limitation" in t) or ("threats to validity" in t) or ("validity" in t and "threat" in t)
            for t in title_norm
        )

        abstract = ""
        for i, s in enumerate(sections):
            if s.title.casefold().startswith("abstract"):
                start = s.start_page
                stop = (sections[i + 1].start_page - 1) if i + 1 < len(sections) else start
                stop = max(start, stop)
                abstract = "\n".join(page_texts[start - 1:stop]).strip()[:4_000]
                break
        if not abstract and page_texts:
            # Many papers print the abstract on page 1 without a numbered heading.
            first = page_texts[0]
            m = re.search(r"abstract\b(.{0,1500})", first, re.IGNORECASE | re.DOTALL)
            if m:
                abstract = m.group(1).strip()[:1_500]

        gaps: list[CoverageGap] = []
        limits: list[str] = []
        if truncated_pages:
            gaps.append(CoverageGap(
                reason="truncated", where=f"pages {max_pages + 1}-{page_count}",
                note=f"page cap {max_pages} applied",
            ))
            limits.append(f"only the first {max_pages} of {page_count} pages were extracted")
        if scanned_pages:
            gaps.append(CoverageGap(
                reason="image_only", where=_ranges(scanned_pages),
                note="no text layer; OCR was not attempted in this pass",
            ))
        if broken_pages:
            gaps.append(CoverageGap(
                reason="parse_failure", where=_ranges(broken_pages),
                note="text extraction failed on these pages; their content is missing",
            ))
        if multi_column:
            limits.append(
                "reading order may interleave columns; verify quotes against the rendered page"
            )

        coverage_state = "complete"
        if not any(t.strip() for t in page_texts):
            coverage_state = "inaccessible" if not scanned_pages else "metadata_only"
        if gaps or limits:
            coverage_state = "partial" if any(len(t.strip()) >= MIN_TEXT_CHARS for t in page_texts) else coverage_state

        accessible_pages = sum(1 for t in page_texts if len(t.strip()) >= MIN_TEXT_CHARS)
        coverage = SourceCoverage(
            state=coverage_state,
            expected_units=page_count,
            accessible_units=accessible_pages,
            gaps=gaps,
            limits=limits,
        )

        source = SourceRecord(
            kind="paper",
            identity=identity or title or "paper.pdf",
            title=title or "Untitled paper",
            author=author,
            origin=origin,
            content_sha256=_sha_of(data),
            language=language,
            retrieved_at=utc_now(),
            coverage=coverage,
            meta={
                "sections": [s.title for s in sections],
                "has_references": has_refs,
                "has_limitations_section": has_limits,
                "scanned_pages": scanned_pages,
            },
        )
        notes: list[str] = [
            "section page ranges are approximate; candidates require rendered-page verification",
        ]
        if broken_pages:
            notes.append(f"text extraction failed on {_ranges(broken_pages)}")
        return PaperIngestResult(
            source=source,
            page_count=page_count,
            text_chars=total_chars,
            sections=sections,
            tables=_dedupe_items(tables),
            figures=_dedupe_items(figures),
            equations=_dedupe_items(equations),
            footnotes=_dedupe_items(footnotes),
            abstract=abstract,
            has_references=has_refs,
            has_limitations_section=has_limits,
            scanned_pages=scanned_pages,
            multi_column_suspected=multi_column,
            notes=notes,
        )
    finally:
        if not isinstance(data, (bytes, bytearray)):
            stream.close()


def _sha_of(data: bytes | str) -> str:
    if isinstance(data, (bytes, bytearray)):
        return hashlib.sha256(bytes(data)).hexdigest()
    with open(data, "rb") as fh:
        h = hashlib.sha256()
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
        return h.hexdigest()


def _dedupe_items(items: list[PaperItem]) -> list[PaperItem]:
    """A caption caught by both the labeled and the math pass appears once."""
    seen: set[tuple[str, str, int, str]] = set()
    out: list[PaperItem] = []
    for it in items:
        key = (it.kind, it.label.casefold(), it.page, it.text[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _ranges(pages: list[int]) -> str:
    if not pages:
        return ""
    out: list[str] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = p
    out.append(str(start) if start == prev else f"{start}-{prev}")
    return "pages " + ", ".join(out)
