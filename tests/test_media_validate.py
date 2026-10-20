"""Result-byte validation: magic-byte sniffing, dimension extraction, the SVG
sanitizer (including bypass attempts), and JPEG EXIF scrubbing."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zlib

import pytest

from hutch.media.validate import (MediaValidationError, image_dimensions,
                                  sanitize_svg, scrub_jpeg, sniff_format,
                                  validate_media)


def make_png(width: int = 7, height: int = 5) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        blob = struct.pack(">I", len(data)) + tag + data
        return blob + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_jpeg(width: int = 6, height: int = 4, *, exif: bytes | None = None,
              comment: bytes | None = None) -> bytes:
    out = bytearray(b"\xff\xd8")
    if comment is not None:
        out += b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment
    if exif is not None:
        seg = b"Exif\x00\x00" + exif
        out += b"\xff\xe1" + struct.pack(">H", len(seg) + 2) + seg
    sof = struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x02\x03\x00\x00"
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
    out += b"\xff\xd9"
    return bytes(out)


def make_exif_tiff(*, orientation: int = 6, model: bytes = b"CamModel-9000",
                   serial: bytes = b"SN-123456", gps_pointer: int = 64) -> bytes:
    """Big-endian IFD0 with orientation, camera model, serial, and a GPS IFD pointer."""
    entries = [
        (0x0112, 3, 1, struct.pack(">H", orientation) + b"\x00\x00"),      # Orientation
        (0x0110, 2, len(model), model),                                    # Model
        (0xA431, 2, len(serial), serial),                                  # BodySerialNumber
        (0x8825, 4, 1, struct.pack(">I", gps_pointer)),                    # GPS IFD pointer
    ]
    entries.sort()
    n = len(entries)
    header = b"MM\x00\x2a" + struct.pack(">I", 8)
    ifd = struct.pack(">H", n)
    data_area = b""
    data_offset = 8 + 2 + n * 12 + 4
    for tag, typ, count, raw in entries:
        if len(raw) <= 4:
            ifd += struct.pack(">HHI", tag, typ, count) + raw.ljust(4, b"\x00")
        else:
            ifd += struct.pack(">HHI", tag, typ, count) \
                + struct.pack(">I", data_offset + len(data_area))
            data_area += raw
    ifd += struct.pack(">I", 0)
    return header + ifd + data_area


def make_webp(width: int = 10, height: int = 6) -> bytes:
    # VP8X payload: 1 flags byte + 3 reserved + 3 width-1 + 3 height-1 = 10 bytes.
    vp8x = b"\x10\x00\x00\x00" + (width - 1).to_bytes(3, "little") \
        + (height - 1).to_bytes(3, "little")
    assert len(vp8x) == 10
    body = b"VP8X" + struct.pack("<I", len(vp8x)) + vp8x
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def make_webm() -> bytes:
    doctype = b"\x42\x82\x84webm"
    return b"\x1a\x45\xdf\xa3" + bytes([0x80 | len(doctype)]) + doctype + b"\x1a\x45\xdf\xa3"


def make_mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1" + b"\x00" * 16


def make_wav() -> bytes:
    fmt = b"\x01\x00\x01\x00" + struct.pack("<I", 8000) + struct.pack("<I", 8000) \
        + b"\x01\x00\x08\x00"
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" \
        + struct.pack("<I", 2) + b"\x00\x00"
    return b"RIFF" + struct.pack("<I", len(body)) + body


# ---------------------------------------------------------------- sniffing


def test_magic_byte_sniffing_identifies_the_supported_containers():
    assert sniff_format(make_png()) == "png"
    assert sniff_format(make_jpeg(exif=b"MM\x00\x2a\x00\x00\x00\x00")) == "jpeg"
    assert sniff_format(make_jpeg()) == "jpeg"
    assert sniff_format(make_webp()) == "webp"
    assert sniff_format(make_webm()) == "webm"
    assert sniff_format(make_mp4()) == "mp4"
    assert sniff_format(make_wav()) == "wav"


def test_sniffing_separates_riff_siblings_and_rejects_lookalikes():
    gif = b"GIF89a" + b"\x00" * 20
    assert sniff_format(gif) == "gif"
    assert sniff_format(b"RIFF" + struct.pack("<I", 4) + b"AVI ") is None
    ebml_without_webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
    assert sniff_format(ebml_without_webm) is None, "MKV shares EBML; it is not webm"
    assert sniff_format(b"\x00\x00\x00\x20notpng") is None
    assert sniff_format(b"<svg>") is None, "SVG is text; the tag probe owns it"
    assert sniff_format(b"short") is None


def test_gif_is_refused_honestly_never_transcoded():
    with pytest.raises(MediaValidationError, match="GIF"):
        validate_media(b"GIF89a" + b"\x00" * 20)


def test_validate_media_rejects_unidentifiable_bytes_and_mismatches():
    with pytest.raises(MediaValidationError, match="could not be identified"):
        validate_media(b"definitely not media bytes at all")
    with pytest.raises(MediaValidationError, match="empty"):
        validate_media(b"")
    png = make_png()
    with pytest.raises(MediaValidationError, match="mismatch|expected"):
        validate_media(png, expected_format="jpeg")
    validated = validate_media(png, expected_format="png")
    assert validated.format == "png" and validated.mime == "image/png"
    assert (validated.width, validated.height) == (7, 5)
    assert validated.scrubbed == png


def test_dimension_extraction_for_stills():
    assert image_dimensions(make_png(13, 9), "png") == (13, 9)
    assert image_dimensions(make_jpeg(20, 11), "jpeg") == (20, 11)
    assert image_dimensions(make_webp(44, 33), "webp") == (44, 33)
    assert image_dimensions(make_webm(), "webm") == (None, None)
    assert image_dimensions(make_mp4(), "mp4") == (None, None)


def test_svg_dimensions_from_width_height_or_viewbox():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="320px" height="200px"><rect/></svg>'
    assert image_dimensions(svg, "svg+xml") == (320, 200)
    svg2 = b'<svg viewBox="0 0 640 480"><rect/></svg>'
    assert image_dimensions(svg2, "svg+xml") == (640, 480)


# ---------------------------------------------------------------- SVG sanitizer


def svg(body: str, attrs: str = 'xmlns="http://www.w3.org/2000/svg"') -> bytes:
    return f"<svg {attrs}>{body}</svg>".encode()


def test_a_clean_svg_passes_unchanged():
    clean = svg('<title>flow</title><rect x="0" y="0" width="4" height="4" fill="#fff"/>'
                '<use href="#local"/>'
                '<text x="1" y="2">learn javascript: the basics</text>')
    out, findings = sanitize_svg(clean)
    assert out == clean, "the sanitizer refuses, it never rewrites silently"
    assert findings


@pytest.mark.parametrize("attempt", [
    svg("<script>alert(1)</script>"),
    svg("<svg:script>alert(1)</svg:script>"),
    svg('<SCrIPt xmlns="x">alert(1)</SCrIPt>'),
    svg('<rect onload="alert(1)" width="1" height="1"/>'),
    svg('<rect ONCLICK="alert(1)" width="1" height="1"/>'),
    svg('<a href="javascript:alert(1)"><rect/></a>'),
    svg('<a xlink:href="javascript:alert(1)" xmlns:xlink="http://www.w3.org/1999/xlink"><rect/></a>'),
    svg('<a href="JaVaScRiPt:alert(1)"><rect/></a>'),
    svg('<a href="jav&#x09;ascript:alert(1)"><rect/></a>'),      # entity-encoded tab
    svg('<a href="&#106;avascript:alert(1)"><rect/></a>'),       # entity-encoded 'j'
    svg('<a href=" javascript:alert(1)"><rect/></a>'),           # leading whitespace
    svg('<a href="java\nscript:alert(1)"><rect/></a>'),          # newline inside scheme
    svg('<animate attributeName="href" values="javascript:alert(1)"/>'),
    svg('<animate attributeName="onbegin" to="alert(1)"/>'),
    svg('<foreignObject><body><img src="x" onerror="alert(1)"/></body></foreignObject>'),
    svg('<image href="http://evil.example/one.svg"/>'),
    svg('<image href="https://evil.example/one.png"/>'),
    svg('<use href="//evil.example/one.svg"/>'),
    svg('<image href="data:text/html;base64,PHNjcmlwdD4="/>'),
    svg('<image href="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="/>'),
    svg('<handler xmlns="http://www.w3.org/2000/svg">alert(1)</handler>'),
    # CSS can also fetch: url(...)/@import must not become an external beacon
    svg('<style>rect{fill:url(https://evil.example/x.svg#f)}</style><rect/>'),
    svg(r'<style>rect{background-image:u\72l(h\74 tps\3a \2f \2f evil.example/x)}</style><rect/>'),
    svg('<style>@import "https://evil.example/sheet.css";</style><rect/>'),
    svg('<rect style="fill:url(//evil.example/y.svg#f)"/>'),
    svg(r'<rect style="background-image:url(h\74 tps\3a \2f \2f evil.example/x)"/>'),
    svg('<rect style="background:url(http://evil.example/z)"/>'),
])
def test_svg_bypass_attempts_are_rejected(attempt):
    with pytest.raises(MediaValidationError):
        sanitize_svg(attempt)
    with pytest.raises(MediaValidationError):
        validate_media(attempt)


def test_css_that_never_fetches_is_still_allowed():
    keep = svg('<style>.a{fill:red;stroke:#123}</style>'
               '<defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs>'
               '<rect class="a" style="fill:url(#g)"/>')
    sanitize_svg(keep)  # must not raise: internal fragment and plain CSS are fine



def test_svg_rejects_doctype_and_entity_expansion():
    with pytest.raises(MediaValidationError, match="DOCTYPE|ENTITY"):
        sanitize_svg(b'<!DOCTYPE svg [<!ENTITY xxe "x">]><svg><text>&xxe;</text></svg>')
    laughs = (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaa">'
              b'<!ENTITY b "&a;&a;&a;&a;">]><svg><text>&b;</text></svg>')
    with pytest.raises(MediaValidationError):
        sanitize_svg(laughs)


def test_svg_rejects_a_non_svg_root_and_element_bombs():
    with pytest.raises(MediaValidationError, match="root"):
        sanitize_svg(b"<html><body>nope</body></html>")
    bomb = svg("".join(f'<rect x="{i}" y="0" width="1" height="1"/>'
                       for i in range(20_001)).encode())
    with pytest.raises(MediaValidationError, match="elements"):
        sanitize_svg(bomb)


def test_inline_data_image_urls_are_allowed_but_bounded_by_the_regex():
    allowed = svg('<image href="data:image/png;base64,iVBORw0KGgo="/>')
    sanitize_svg(allowed)  # must not raise


# ---------------------------------------------------------------- JPEG EXIF


def test_exif_scrub_keeps_orientation_strips_gps_model_serial():
    tiff = make_exif_tiff(orientation=6)
    jpeg = make_jpeg(exif=tiff, comment=b"created by a secret lab")
    scrubbed, findings = scrub_jpeg(jpeg)
    assert scrubbed.startswith(b"\xff\xd8") and scrubbed.endswith(b"\xff\xd9")
    # The rebuilt APP1 must still carry orientation 6 so images display upright:
    # the entry bytes are tag 0x0112, type SHORT(3), count 1, value 6.
    orientation_entry = struct.pack(">HHI", 0x0112, 3, 1) + struct.pack(">H", 6) + b"\x00\x00"
    assert orientation_entry in scrubbed
    assert b"CamModel-9000" not in scrubbed, "camera model stripped"
    assert b"SN-123456" not in scrubbed, "serial stripped"
    assert b"secret lab" not in scrubbed, "comment segment dropped"
    assert any("GPS" in finding or "stripped" in finding for finding in findings)
    assert scrub_jpeg(scrubbed)[0] == scrubbed, "scrubbing is idempotent"


def test_jpeg_dimensions_survive_scrubbing():
    jpeg = make_jpeg(60, 40, exif=make_exif_tiff())
    scrubbed, _ = scrub_jpeg(jpeg)
    assert image_dimensions(scrubbed, "jpeg") == (60, 40)
    assert sniff_format(scrubbed) == "jpeg"


def test_jpeg_without_exif_is_reported_and_kept_whole():
    jpeg = make_jpeg(6, 4)
    scrubbed, findings = scrub_jpeg(jpeg)
    assert scrubbed == jpeg
    assert any("no EXIF" in finding for finding in findings)


def test_unreadable_exif_is_removed_not_kept():
    jpeg = make_jpeg(exif=b"MM\x00\xffbroken")
    scrubbed, findings = scrub_jpeg(jpeg)
    assert b"broken" not in scrubbed
    assert any("unreadable EXIF" in finding for finding in findings)
    assert image_dimensions(scrubbed, "jpeg") == (6, 4)


def test_validate_media_end_to_end_scrubs_jpeg():
    validated = validate_media(make_jpeg(6, 4, exif=make_exif_tiff()))
    assert validated.format == "jpeg" and validated.mime == "image/jpeg"
    assert b"CamModel-9000" not in validated.scrubbed


def test_byte_ceiling_is_enforced_before_parsing():
    png = make_png()
    with pytest.raises(MediaValidationError, match="limit"):
        validate_media(png, max_bytes=8)
