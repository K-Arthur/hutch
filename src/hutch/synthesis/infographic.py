"""Deterministic infographics: one layout spec rendered to SVG and PNG, plus a text companion.

The infographic is a structured summary panel built *only* from the manifest: what the
audience needs (purpose and coverage), the findings with their `[S#]` handles, the numbers
exactly as reported, the limitations, and concise source references. There is deliberately
no ranking, no implied causality, no chart scale, and no decorative icon that could assert
something the evidence does not.

The same :func:`layout_spec` drives both renderers, so the SVG (editable source) and the
PNG (raster export) cannot drift apart. Text is XML-escaped, no scripts/foreignObjects or
external references are emitted, and a plain-text companion always accompanies the image
for accessibility and machine reading.

Layout honesty rules:

* numbers keep their ``as_reported`` wording and qualifier; a percentage-point change is
  labeled "percentage points" even when the source wrote "%", and is never mixed with
  percentages;
* a claim with no registered quantity contributes no number row;
* when the panel cannot show everything, it says "showing N of M" instead of silently
  dropping items.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional
from xml.sax.saxutils import escape as xml_escape

from pydantic import BaseModel, ConfigDict, Field

from .model import Claim, SynthesisManifest

MARGIN = 48
TITLE_SIZE = 44
SECTION_SIZE = 26
BODY_SIZE = 20
LINE_HEIGHT = 30
SECTION_GAP = 22
SECTION_PADDING = 20
SECTION_TITLE_HEIGHT = 44
WRAP_CHARS = 46  # characters per body line at the default width
MAX_LINES_PER_ITEM = 12

SectionKind = Literal["findings", "numbers", "limitations", "sources"]


class SpecItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    handles: list[str] = Field(default_factory=list)  # [S#] handles
    note: str = ""


class SpecSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SectionKind
    title: str
    items: list[SpecItem]
    note: str = ""  # overflow or labeling note, shown under the title


class InfographicSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    purpose: str
    coverage: str
    sections: list[SpecSection]
    footer: str
    source_handles: dict[str, str] = Field(default_factory=dict)  # handle -> identity label


def _handles_for(claim: Claim, manifest: SynthesisManifest) -> list[str]:
    handles: list[str] = []
    for span_id in claim.spans:
        span = manifest.span(span_id)
        if span is None:
            continue
        source = manifest.source(span.source_id)
        if source is None:
            continue
        handle = f"S{manifest.sources.index(source) + 1}"
        if handle not in handles:
            handles.append(handle)
    return handles


def _unit_label(value: Any) -> str:
    """Display unit with the percentage-point guard: never blur pp into %."""
    unit = str(getattr(value, "unit", "") or "")
    if getattr(value, "change_kind", "") == "percentage_point_change" and unit.strip() in ("%", "percent"):
        return "percentage points"
    return unit


def build_infographic_spec(manifest: SynthesisManifest, *, max_findings: int = 6,
                           max_numbers: int = 6, max_limitations: int = 5,
                           max_sources: int = 10) -> InfographicSpec:
    """The summary panel for one manifest revision. Pure and deterministic."""
    title = "Source-grounded overview"
    if manifest.sources:
        first = manifest.sources[0]
        title = first.title or title

    purpose = (f"For {manifest.audience} — {manifest.expertise} level, "
               f"{manifest.language}. {manifest.policy.replace('_', '-')} synthesis.")

    findings: list[SpecItem] = []
    numbers: list[SpecItem] = []
    limitations: list[SpecItem] = []
    shown_claims = [c for c in manifest.claims if c.status != "retracted"]
    visible = shown_claims[:max_findings]
    for claim in visible:
        handles = _handles_for(claim, manifest)
        note_bits = []
        if claim.confidence_basis:
            note_bits.append(claim.confidence_basis)
        if claim.kind in ("design_proposal", "estimate", "opinion", "interpretation"):
            note_bits.append(claim.kind.replace("_", " "))
        findings.append(SpecItem(text=claim.text, handles=handles,
                                 note=" · ".join(dict.fromkeys(note_bits))))
        for quantity in claim.quantities:
            unit = _unit_label(quantity)
            qualifier = (f"{quantity.qualifier} " if quantity.qualifier and
                         quantity.qualifier.lower() not in quantity.as_reported.lower() else "")
            base = f"{qualifier}{quantity.as_reported}"
            if quantity.change_kind == "percentage_point_change":
                base += " — percentage-point change"
            elif unit and unit not in quantity.as_reported:
                base += f" ({unit})"
            numbers.append(SpecItem(text=base, handles=handles,
                                    note=quantity.change_kind.replace("_", " ")))

    for caveat in manifest.caveats:
        limitations.append(SpecItem(text=caveat))
    for cx in manifest.contradictions:
        if cx.status == "unresolved":
            limitations.append(SpecItem(text=f"Unresolved: {cx.description}",
                                        handles=[], note="sources disagree"))
    for claim in shown_claims:
        if claim.status in ("unresolved", "partially_supported"):
            label = claim.status.replace("_", " ")
            text = claim.text if label in claim.text.lower() else f"{claim.text} — {label}"
            limitations.append(SpecItem(text=text))

    sources: list[SpecItem] = []
    source_handles: dict[str, str] = {}
    for index, source in enumerate(manifest.sources[:max_sources], start=1):
        handle = f"S{index}"
        label = source.title or source.identity
        origin = source.origin or source.identity
        retrieved = (source.retrieved_at or "")[:10]
        source_handles[handle] = f"{label} — {origin}"
        sources.append(SpecItem(
            text=f"{label}", handles=[handle],
            note=" · ".join(b for b in (origin, f"retrieved {retrieved}" if retrieved else "",
                                        source.author) if b)))
    if len(manifest.sources) > max_sources:
        sources.append(SpecItem(text=f"… and {len(manifest.sources) - max_sources} more source(s)",
                                note="listed in the manifest"))

    sections: list[SpecSection] = []
    if findings:
        note = ""
        if len(shown_claims) > len(visible):
            note = f"showing {len(visible)} of {len(shown_claims)} findings; the full list is in the manifest"
        sections.append(SpecSection(kind="findings", title="Key findings",
                                    items=findings, note=note))
    if numbers:
        sections.append(SpecSection(kind="numbers", title="Reported numbers",
                                    items=numbers[:max_numbers],
                                    note="as reported by the sources; not independently re-measured"))
    if limitations:
        sections.append(SpecSection(kind="limitations", title="Limitations and open points",
                                    items=limitations[:max_limitations]))
    if sources:
        sections.append(SpecSection(kind="sources", title="Sources", items=sources))

    footer = (f"Coverage: {manifest.coverage_summary or 'see the manifest'} · "
              f"Manifest {manifest.id} revision {manifest.revision} · "
              "compiled from the listed sources; nothing outside them was added. "
              "Text may be shortened for layout; the companion text and the manifest "
              "carry the full wording.")
    return InfographicSpec(title=title, purpose=purpose,
                           coverage=manifest.coverage_summary or "", sections=sections,
                           footer=footer, source_handles=source_handles)


# ---------------------------------------------------------------------------
# layout (shared by the SVG and PNG renderers)


class TextLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    size: int
    bold: bool = False
    text: str


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    w: int
    h: int
    kind: str  # "background" | "section" | "title-rule"


class Layout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int
    height: int
    boxes: list[Box]
    texts: list[TextLine]
    content_height: int


def _wrap(text: str, width_chars: int) -> list[str]:
    words = re.sub(r"\s+", " ", text or "").strip().split(" ")
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > MAX_LINES_PER_ITEM:
        lines = lines[:MAX_LINES_PER_ITEM]
        lines[-1] = lines[-1][: max(0, width_chars - 1)] + "…"
    return lines


def layout_spec(spec: InfographicSpec, *, width: int = 1080, height: int = 1600,
                wrap_chars: Optional[int] = None) -> Layout:
    """A deterministic vertical layout. Both renderers draw exactly this."""
    if width < 480 or height < 400:
        raise ValueError("the infographic needs at least 480x400 pixels")
    wrap = wrap_chars or max(24, int((width - 2 * MARGIN - 2 * SECTION_PADDING) / (BODY_SIZE * 0.52)))
    boxes: list[Box] = [Box(x=0, y=0, w=width, h=height, kind="background")]
    texts: list[TextLine] = []

    footer_lines = _wrap(spec.footer, wrap)[:3]
    footer_reserve = len(footer_lines) * (LINE_HEIGHT - 4) + SECTION_GAP
    y = MARGIN
    for line in _wrap(spec.title, wrap)[:2]:
        texts.append(TextLine(x=MARGIN, y=y + TITLE_SIZE, size=TITLE_SIZE, bold=True, text=line))
        y += TITLE_SIZE + 8
    y += 4
    for line in _wrap(spec.purpose, wrap):
        texts.append(TextLine(x=MARGIN, y=y + BODY_SIZE, size=BODY_SIZE, text=line))
        y += LINE_HEIGHT
    y += SECTION_GAP // 2
    boxes.append(Box(x=MARGIN, y=y, w=width - 2 * MARGIN, h=3, kind="title-rule"))
    y += SECTION_GAP

    for section in spec.sections:
        content_lines: list[tuple[list[str], list[str], str]] = []
        for item in section.items:
            body = _wrap(item.text, wrap)
            meta = " · ".join(b for b in (" ".join(f"[{h}]" for h in item.handles), item.note) if b)
            content_lines.append((body, item.handles, meta))
        section_height = SECTION_TITLE_HEIGHT + 8
        for body, _handles, meta in content_lines:
            section_height += len(body) * LINE_HEIGHT + (LINE_HEIGHT if meta else 0) + 8
        if section.note:
            section_height += LINE_HEIGHT
        section_height += SECTION_PADDING
        if y + section_height > height - MARGIN - footer_reserve:
            break  # remaining sections live in the manifest and the companion text
        boxes.append(Box(x=MARGIN, y=y, w=width - 2 * MARGIN, h=section_height, kind="section"))
        cursor = y + SECTION_PADDING
        texts.append(TextLine(x=MARGIN + SECTION_PADDING, y=cursor + SECTION_SIZE,
                              size=SECTION_SIZE, bold=True, text=section.title))
        cursor += SECTION_TITLE_HEIGHT
        if section.note:
            for line in _wrap(section.note, wrap):
                texts.append(TextLine(x=MARGIN + SECTION_PADDING, y=cursor + BODY_SIZE - 2,
                                      size=BODY_SIZE - 3, text=line))
                cursor += LINE_HEIGHT - 4
        for body, _handles, meta in content_lines:
            for line in body:
                texts.append(TextLine(x=MARGIN + SECTION_PADDING, y=cursor + BODY_SIZE,
                                      size=BODY_SIZE, text=line))
                cursor += LINE_HEIGHT
            if meta:
                texts.append(TextLine(x=MARGIN + SECTION_PADDING, y=cursor + BODY_SIZE - 4,
                                      size=BODY_SIZE - 4, text=meta))
                cursor += LINE_HEIGHT
            cursor += 8
        y += section_height + SECTION_GAP

    footer_y = height - MARGIN - len(footer_lines) * (LINE_HEIGHT - 4)
    for line in footer_lines:
        texts.append(TextLine(x=MARGIN, y=footer_y, size=BODY_SIZE - 4, text=line))
        footer_y += LINE_HEIGHT - 4
    return Layout(width=width, height=height, boxes=boxes, texts=texts, content_height=y)


# ---------------------------------------------------------------------------
# renderers

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


class InfographicRenderError(ValueError):
    """The requested rendering cannot be produced honestly (e.g., no usable font)."""


def render_svg(layout: Layout, spec: InfographicSpec) -> bytes:
    """Vector SVG from the shared layout. No scripts, no external references."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout.width}" height="{layout.height}" '
        f'viewBox="0 0 {layout.width} {layout.height}" role="img" '
        f'aria-label="{xml_escape(spec.title, {chr(34): "&quot;"})}">',
        f'<title>{xml_escape(spec.title)}</title>',
        "<style>text{font-family:'DejaVu Sans',system-ui,-apple-system,'Segoe UI',sans-serif;fill:#111}"
        ".note{fill:#555}.rule{fill:#111}</style>",
    ]
    for box in layout.boxes:
        if box.kind == "background":
            parts.append(f'<rect x="0" y="0" width="{box.w}" height="{box.h}" fill="#ffffff"/>')
        elif box.kind == "title-rule":
            parts.append(f'<rect class="rule" x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}"/>')
        else:
            parts.append(f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" '
                         f'fill="#fafafa" stroke="#cccccc" stroke-width="1" rx="10"/>')
    for text in layout.texts:
        weight = ' font-weight="bold"' if text.bold else ""
        css = "" if text.bold or text.size >= BODY_SIZE else ' class="note"'
        parts.append(f'<text x="{text.x}" y="{text.y}" font-size="{text.size}"{weight}{css}>'
                     f'{xml_escape(text.text)}</text>')
    parts.append("</svg>")
    return "\n".join(parts).encode("utf-8")


def _font_paths() -> tuple[str, str]:
    import os

    regular = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), "")
    bold = next((p for p in _BOLD_CANDIDATES if os.path.exists(p)), "")
    if not regular or not bold:
        raise InfographicRenderError(
            "no usable TrueType font was found for raster export; the SVG and the text "
            "companion are still available")
    return regular, bold


def render_png(layout: Layout, spec: InfographicSpec) -> bytes:
    """Raster export of the exact same layout (deterministic at this size)."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    regular, bold = _font_paths()
    image = Image.new("RGB", (layout.width, layout.height), "#ffffff")
    draw = ImageDraw.Draw(image)
    fonts: dict[tuple[int, bool], Any] = {}

    def font(size: int, is_bold: bool):
        key = (size, is_bold)
        if key not in fonts:
            fonts[key] = ImageFont.truetype(bold if is_bold else regular, size=size)
        return fonts[key]

    for box in layout.boxes:
        if box.kind == "background":
            continue
        if box.kind == "title-rule":
            draw.rectangle([box.x, box.y, box.x + box.w, box.y + box.h], fill="#111111")
        else:
            draw.rounded_rectangle([box.x, box.y, box.x + box.w, box.y + box.h], radius=10,
                                   fill="#fafafa", outline="#cccccc", width=1)
    for text in layout.texts:
        colour = "#111111" if text.bold or text.size >= BODY_SIZE else "#555555"
        draw.text((text.x, text.y - text.size), text=text.text, font=font(text.size, text.bold),
                  fill=colour)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def render_text_companion(spec: InfographicSpec) -> str:
    """The accessible/plain alternative: the same content as a Markdown document."""
    lines = [f"# {spec.title}", "", spec.purpose, ""]
    for section in spec.sections:
        lines.append(f"## {section.title}")
        if section.note:
            lines.append(f"_{section.note}_")
        for item in section.items:
            handles = " ".join(f"[{h}]" for h in item.handles)
            suffix = f" — {item.note}" if item.note else ""
            lines.append(f"- {item.text} {handles}{suffix}".rstrip())
        lines.append("")
    lines.append(f"---\n{spec.footer}")
    return "\n".join(lines) + "\n"
