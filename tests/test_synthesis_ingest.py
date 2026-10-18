"""Ingestion contract tests: thread reconstruction and whitepaper structure.

The thread fixture is the mission's acceptance case: a 20-post thread with a quote post,
an attachment, a correction, a duplicate, a deleted post, and an unreachable remainder.
The paper fixture is built as a real PDF so extraction runs on actual bytes.
"""

from __future__ import annotations

from io import BytesIO

import pytest

from hutch.synthesis.ingest import (
    PaperEncryptedError,
    ThreadPost,
    ingest_paper,
    ingest_thread,
)

# ---------------------------------------------------------------------------
# thread fixtures


def _post(pid, author, text="", **kw):
    return ThreadPost(post_id=pid, author_id=author, author=author.upper(), text=text, **kw)


def _twenty_post_thread():
    """Author A's argument p1..p18 plus: B's reply, a foreign quote, a duplicate, a
    correction, an edit, an attachment, a deleted post (p12), and expected total 20."""
    posts = [
        _post("p1", "A", "20 things about caching. 1/20"),
        _post("p2", "A", "2/20 Caching is about locality.", reply_to="p1",
              engagement={"likes": 5000, "reposts": 400}),
        _post("p3", "A", "3/20 See this chart.", reply_to="p2",
              attachments=[{"kind": "image", "url": "https://cdn.example.org/chart.png",
                            "alt": "hit rate by size"}],
              edited_at="2026-10-01T10:00:00Z", engagement={"likes": 1}),
        _post("pb", "B", "But what about invalidation?", reply_to="p2"),
        _post("p5", "A", "4/20 On invalidation:", reply_to="p3", quoted="pb"),
        _post("p6", "A", "2/20 Caching is about locality.", reply_to="p5"),  # duplicate
        _post("p7", "A", "Correction to 2/20: locality AND reuse.", reply_to="p6"),
        _post("p8", "A", "5/20 Reuse matters.", reply_to="p7"),
        _post("p9", "A", "6/20 Writes are harder.", reply_to="p8"),
        _post("p10", "A", "7/20 TTLs are blunt.", reply_to="p9"),
        _post("p11", "A", "8/20 Consistency costs latency.", reply_to="p10"),
        _post("p12", "A", "", reply_to="p11", accessible=False, unavailable_reason="deleted"),
        _post("p13", "A", "10/20 Sharding changes the math.", reply_to="p12"),
        _post("p14", "A", "11/20 Measure first.", reply_to="p13"),
        _post("p15", "A", "12/20 Then tune.", reply_to="p14"),
        _post("p16", "A", "13/20 Eviction is policy.", reply_to="p15"),
        _post("p17", "A", "14/20 Cold starts hurt.", reply_to="p16"),
        _post("p18", "A", "15/20 Summary and caveats.", reply_to="p17"),
    ]
    return posts


def test_thread_reconstructs_author_chain_not_engagement_or_others():
    result = ingest_thread(_twenty_post_thread(), expected_count=20)

    ordered_ids = [p.post_id for p in result.ordered]
    # p6 is a duplicate (excluded), p12 is deleted (traversed, not content), B's pb is
    # never in the argument even though it has the most engagement.
    assert ordered_ids == ["p1", "p2", "p3", "p5", "p7", "p8", "p9", "p10", "p11",
                           "p13", "p14", "p15", "p16", "p17", "p18"]
    assert "pb" not in ordered_ids
    assert [p.post_id for p in result.context_replies] == ["pb"]

    # p5 quote-posts pb, so pb is also the quoted foreign post.
    assert [p.post_id for p in result.quoted_foreign] == ["pb"]

    # Engagement (p2 with 5000 likes vs p3 with 1) did not reorder anything.
    assert ordered_ids.index("p2") < ordered_ids.index("p3") < ordered_ids.index("p5")


def test_thread_duplicate_correction_edit_and_attachment_are_recorded():
    result = ingest_thread(_twenty_post_thread(), expected_count=20)
    assert [p.post_id for p in result.duplicates] == ["p6"]
    assert result.duplicates[0].text == result.ordered[1].text
    assert result.corrections == ["p7"]
    assert result.edited == [{"post_id": "p3", "edited_at": "2026-10-01T10:00:00Z"}]
    assert len(result.attachments) == 1 and result.attachments[0]["post_id"] == "p3"


def test_thread_coverage_statement_is_exact_and_never_invents_missing_text():
    result = ingest_thread(_twenty_post_thread(), expected_count=20)

    # 15 ordered + 1 duplicate = 16 accessible author posts; p12 is known deleted; the
    # remaining 3 expected posts were never retrieved.
    assert "p12" in result.missing_post_ids
    assert result.coverage.accessible_units == 16
    assert result.coverage.expected_units == 20
    assert result.coverage.statement == "16 of 20 accessible"
    assert result.coverage.state == "partial"

    reasons = {g.reason for g in result.gaps}
    assert "deleted" in reasons and "not_fetched" in reasons

    # The deleted post has no text anywhere and no placeholder was invented.
    assert all(p.post_id != "p12" for p in result.ordered)
    joined = " ".join(p.text for p in result.ordered)
    assert "p12" not in joined


def test_thread_total_never_trusted_over_actual_access():
    # A claimed total below what was actually retrieved is clamped, not repeated.
    result = ingest_thread(_twenty_post_thread(), expected_count=5)
    assert result.coverage.expected_units == 16
    assert result.coverage.statement == "16 of 16 accessible"


def test_thread_broken_parent_and_missing_quote_are_gaps():
    posts = [
        _post("r1", "A", "root"),
        _post("r2", "A", "child", reply_to="gone_parent"),
        _post("r3", "A", "quote holder", reply_to="r1", quoted="gone_quote"),
    ]
    result = ingest_thread(posts)
    wheres = " ".join(f"{g.where} {g.note}" for g in result.gaps)
    assert "gone_parent" in result.missing_post_ids
    assert "gone_quote" in result.missing_post_ids
    assert "r3" in wheres or "gone_quote" in wheres


def test_thread_refetch_and_engagement_do_not_create_posts():
    posts = _twenty_post_thread() + [_twenty_post_thread()[0]]
    result = ingest_thread(posts, expected_count=20)
    assert [p.post_id for p in result.ordered][0] == "p1"
    root_count = sum(1 for p in result.ordered if p.post_id == "p1")
    assert root_count == 1


def test_thread_source_record_carries_coverage_and_hash():
    result = ingest_thread(_twenty_post_thread(), expected_count=20)
    rec = result.source_record(identity="https://social.example/@a/status/1", origin="social.example")
    assert rec.kind == "thread" and rec.author == "A"
    assert rec.coverage.statement == "16 of 20 accessible"
    assert len(rec.content_sha256) == 64
    assert rec.meta["order_basis"] == "reply-chain"


# ---------------------------------------------------------------------------
# paper fixtures


def _pdf(pages: list[list[str]], *, image_pages: tuple[int, ...] = ()) -> bytes:
    """Build a real multi-page PDF with Helvetica text lines (and optional image pages)."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
    )

    writer = PdfWriter()
    for idx, lines in enumerate(pages):
        page = writer.add_blank_page(width=612, height=792)
        if idx + 1 in image_pages:
            img = DecodedStreamObject()
            img.set_data(b"\x80")
            img.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(1),
                NameObject("/Height"): NumberObject(1),
                NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            })
            ref = writer._add_object(img)
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject("/Im1"): ref})}
            )
            continue
        ops = ["BT /F1 11 Tf 12 TL 72 720 Td"]
        for line in lines:
            text = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            ops.append(f"({text}) Tj T*")
        ops.append("ET")
        content = DecodedStreamObject()
        content.set_data("\n".join(ops).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(content)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


PAPER_PAGES = [
    [  # 1: title-ish page with unnumbered abstract
        "Caching at the Edge",
        "Abstract",
        "We study caching behaviour under churn.",
        "1 Introduction",
        "Caching matters because latency matters.",
        "Prior work studied single-node caches.",
    ],
    [  # 2: method with a table caption and an equation
        "2 Method",
        "We ran experiments across five regions.",
        "Table 1: Throughput by object size.",
        "x = 3 + 4",
    ],
    [  # 3: results with a figure caption and a footnote
        "3 Results",
        "Figure 1: Latency over time.",
        "The hit rate was 12% higher.",
        "a) Data was collected in 2024.",
    ],
    [  # 4: limitations, references, appendix
        "Limitations",
        "Our testbed was small and homogeneous.",
        "References",
        "Smith, J. (2024). On caches.",
        "Appendix A",
        "Extra measurements live here.",
    ],
]


def test_paper_structure_sections_captions_and_abstract():
    result = ingest_paper(_pdf(PAPER_PAGES), identity="test://paper", title="Caching at the Edge",
                          author="A. Author", origin="example.org")
    titles = result.section_titles()
    assert "Introduction" in titles and "Method" in titles and "Results" in titles
    assert "Limitations" in titles and "References" in titles and "Appendix A" in titles
    assert result.has_references is True
    assert result.has_limitations_section is True
    assert "caching behaviour under churn" in result.abstract

    intro = next(s for s in result.sections if s.title == "Introduction")
    assert intro.start_page == 1 and intro.number == "1"

    assert [t.label for t in result.tables] == ["Table 1"]
    assert result.tables[0].page == 2 and "Throughput" in result.tables[0].text
    assert [f.label for f in result.figures] == ["Figure 1"]
    assert result.figures[0].page == 3
    assert any("x = 3 + 4" in e.text for e in result.equations)
    assert result.footnotes, "the page-tail footnote candidate should be found"
    assert result.coverage.state == "complete"
    assert result.coverage.statement == "4 of 4 accessible"
    assert result.source.content_sha256 and result.source.kind == "paper"


def test_paper_encrypted_is_refused_not_empty_success():
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    w.encrypt(user_password="secret")
    out = BytesIO()
    w.write(out)
    with pytest.raises(PaperEncryptedError):
        ingest_paper(out.getvalue())


def test_paper_page_cap_reports_truncation():
    result = ingest_paper(_pdf(PAPER_PAGES), max_pages=2)
    assert result.page_count == 4
    assert result.coverage.expected_units == 4
    assert result.coverage.accessible_units == 2
    assert result.coverage.statement == "2 of 4 accessible"
    assert any(g.reason == "truncated" for g in result.coverage.gaps)


def test_paper_scanned_page_is_reported_not_silently_empty():
    pages = [
        ["1 Introduction", "Real text here to keep the document extractable."],
        [],  # image-only page
        ["2 Method", "More real text."],
    ]
    result = ingest_paper(_pdf(pages, image_pages=(2,)))
    assert result.scanned_pages == [2]
    assert any(g.reason == "image_only" for g in result.coverage.gaps)
    assert result.coverage.state == "partial"
    assert "2-2" not in result.coverage.gaps[0].where  # ranges render as "pages 2"


def test_paper_fully_scanned_is_metadata_only_not_a_clean_summary():
    result = ingest_paper(_pdf([[], []], image_pages=(1, 2)))
    assert result.scanned_pages == [1, 2]
    assert result.coverage.state == "metadata_only"
    assert result.coverage.statement == "0 of 2 accessible"


def test_paper_multicolumn_suspicion_is_disclosed():
    col = [f"left side text number {i}          right side text number {i}" for i in range(1, 20)]
    result = ingest_paper(_pdf([col, col]))
    assert result.multi_column_suspected is True
    assert any("interleave" in limit for limit in result.coverage.limits)
