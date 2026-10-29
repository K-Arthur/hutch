"""Result-byte validation for media: magic-byte sniffing, dimensions, SVG sanitizing,
JPEG EXIF scrubbing.

The bytes a backend returns are THE TRUTH about what was produced, never the
prompt, never the requested format, never a URL's content-type. Everything here
operates on raw bytes:

* :func:`sniff_format` identifies PNG/JPEG/WebP/GIF/RIFF(WEBM|WAV)/MP4/SVG by magic
  bytes. GIF is sniffed only to be refused honestly (it is not a supported format;
  silently transcoding it would be fabrication).
* :func:`image_dimensions` extracts still dimensions (PNG IHDR, JPEG SOFn, WebP
  VP8/VP8L/VP8X, SVG width/height/viewBox) so media blocks can declare them.
* :func:`sanitize_svg` REJECTS (never silently strips) script elements, SVG Tiny
  handlers, event-handler attributes, external references (http/https/protocol-
  relative/file/ftp), non-inline ``data:`` payloads, ``javascript:`` URLs (including
  entity-, whitespace- and case-obfuscated bypass attempts), ``foreignObject``,
  DOCTYPE/entity declarations, and oversized element counts.
* :func:`scrub_jpeg` rebuilds the EXIF APP1 segment from a small allowlist:
  orientation (so images still display upright) plus resolution tags survive; GPS
  data, camera model/serial, software, maker notes and every other metadata block
  are stripped.
"""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from .storage import MEDIA_FORMATS, MAX_MEDIA_BYTES, MIME_BY_FORMAT

#: byte ceiling applied before parsing (a hostile SVG must not be parsed at all)
MAX_SVG_TEXT_BYTES = 8_000_000

#: element-count ceiling: a bound on render cost, not just memory
MAX_SVG_ELEMENTS = 20_000

_ALLOWED_INLINE_DATA_RE = re.compile(
    r"^data:image/(?:png|jpeg|webp);base64,[a-z0-9+/=]+$", re.IGNORECASE)

_URL_ATTRS = frozenset({
    "href", "xlink:href", "src", "srcset", "poster", "action", "formaction",
    # SMIL animation targets can smuggle a URL into an href they animate:
    "values", "from", "to", "by",
})

_SCHEME_BLACKLIST = ("javascript:", "vbscript:", "livescript:", "mocha:", "data:text/html")


class MediaValidationError(ValueError):
    """The bytes are not what they must be; nothing was accepted."""


@dataclass
class MediaValidation:
    """What the bytes actually are, after validation and scrubbing."""
    format: str
    mime: str
    bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    scrubbed: bytes = b""
    findings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- sniffing


def sniff_format(data: bytes) -> Optional[str]:
    """Identify the container by magic bytes. Returns one of MEDIA_FORMATS, the
    literal ``"gif"`` (sniffed only so it can be refused honestly), or None."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 12:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and len(data) >= 12:
        if data[8:12] == b"WEBP":
            return "webp"
        if data[8:12] == b"WAVE":
            return "wav"
        return None
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm" if b"webm" in data[:4096].lower() else None
    if data[4:8] == b"ftyp":
        return "mp4"
    return None


def looks_like_svg(data: bytes) -> bool:
    """Text-based SVG has no magic number; a leading-tag probe is the honest check."""
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n")
    if not head.startswith((b"<", b"<?xml")):
        return False
    return re.search(rb"<[\s\x00]*svg[\s>/:]", data[:2048], re.IGNORECASE) is not None


# ---------------------------------------------------------------- dimensions


def _png_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None, None
    width, height = struct.unpack(">II", data[16:24])
    return width or None, height or None


def _jpeg_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xD9 or marker == 0xDA:  # EOI / SOS: dimensions come before scan data
            return None, None
        if i + 4 > n:
            return None, None
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 <= n:
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width or None, height or None
        i += 2 + seglen
    return None, None


def _webp_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    if len(data) < 30:
        return None, None
    chunk = data[12:16]
    if chunk == b"VP8X":
        # 24-bit widths/heights minus one, packed as 3-byte little-endian fields.
        w = int.from_bytes(data[24:27], "little") + 1
        h = int.from_bytes(data[27:30], "little") + 1
        return w, h
    if chunk == b"VP8 ":
        if data[23:26] == b"\x9d\x01\x2a":
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return w or None, h or None
        return None, None
    if chunk == b"VP8L":
        bits = struct.unpack("<I", data[21:25])[0]
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    return None, None


def _svg_dimensions(text: str) -> tuple[Optional[int], Optional[int]]:
    head = text[:8192]
    def _num(raw: str) -> Optional[int]:
        m = re.match(r"^\s*(\d+(?:\.\d+)?)(?:px)?\s*$", raw)
        return int(float(m.group(1))) if m else None
    m = re.search(r"<svg[^>]*\bwidth\s*=\s*[\"']([^\"']+)[\"'][^>]*\bheight\s*=\s*[\"']([^\"']+)[\"']", head, re.IGNORECASE)
    if m:
        w, h = _num(m.group(1)), _num(m.group(2))
        if w and h:
            return w, h
    m = re.search(r"<svg[^>]*\bviewBox\s*=\s*[\"']([^\s\"']+)[\s+]+([^\s\"']+)[\s+]+([^\s\"']+)[\s+]+([^\s\"']+)[\"']", head, re.IGNORECASE)
    if m:
        try:
            w = int(float(m.group(3)))
            h = int(float(m.group(4)))
            if w > 0 and h > 0:
                return w, h
        except ValueError:
            pass
    return None, None


def image_dimensions(data: bytes, fmt: str) -> tuple[Optional[int], Optional[int]]:
    """Best-effort still dimensions; containers (webm/mp4/wav) report (None, None)."""
    try:
        if fmt == "png":
            return _png_dimensions(data)
        if fmt == "jpeg":
            return _jpeg_dimensions(data)
        if fmt == "webp":
            return _webp_dimensions(data)
        if fmt == "svg+xml":
            return _svg_dimensions(data.decode("utf-8", errors="replace"))
    except (struct.error, IndexError):
        return None, None
    return None, None


# ---------------------------------------------------------------- SVG sanitizer

_SCRIPT_ELEMENTS = frozenset({"script", "handler", "listener", "foreignobject", "iframe"})

_DOCTYPE_RE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<\s*[\w:.-]*:?script", re.IGNORECASE)
_CSS_ESCAPE_RE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|(\r\n|[\n\r\f])|(.))", re.DOTALL)


def _decode_css_escapes(value: str) -> str:
    """Decode CSS escapes before checking whether a declaration can fetch a URL."""
    def replace(match: re.Match[str]) -> str:
        codepoint, continuation, escaped = match.groups()
        if codepoint:
            value = int(codepoint, 16)
            return "\ufffd" if value == 0 or value > 0x10FFFF else chr(value)
        if continuation:
            return ""
        return escaped or ""

    return _CSS_ESCAPE_RE.sub(replace, value)


def _normalize_css(value: str) -> str:
    return _normalize_url(_decode_css_escapes(value))


def _normalize_url(value: str) -> str:
    """Lowercase and remove every whitespace/control char, so 'jav&#x09;ascript:'
    (already entity-decoded by the XML parser) cannot dodge a prefix check."""
    return re.sub(r"[\s\x00-\x20\x7f]+", "", value).lower()


def _local_name(tag_or_attr: str) -> str:
    return tag_or_attr.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def sanitize_svg(data: bytes) -> tuple[bytes, list[str]]:
    """Reject-based SVG sanitizer: returns the bytes unchanged plus findings, or
    raises :class:`MediaValidationError` naming every reason it refused.

    Rejection (not silent stripping) is deliberate: an SVG whose script was
    quietly removed no longer does what its author asked, and a reader deserves
    to know the content was refused (open-webui #14541 class: never lose the
    diagnostic).
    """
    problems: list[str] = []
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise MediaValidationError("SVG bytes are empty")
    if len(data) > MAX_SVG_TEXT_BYTES:
        raise MediaValidationError(f"SVG exceeds the {MAX_SVG_TEXT_BYTES // 1_000_000} MB text limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise MediaValidationError("SVG must be UTF-8 text") from None
    if _DOCTYPE_RE.search(text[:4096]):
        problems.append("DOCTYPE/ENTITY declarations are not accepted (external-entity tricks)")
    if _SCRIPT_TAG_RE.search(text):
        problems.append("a <script> element is present")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise MediaValidationError(f"SVG is not parseable XML ({exc})") from None
    if _local_name(root.tag) != "svg":
        raise MediaValidationError("the document root element is not <svg>")

    count = 0

    def walk(element: ET.Element) -> None:
        nonlocal count
        count += 1
        if count > MAX_SVG_ELEMENTS:
            problems.append(f"more than {MAX_SVG_ELEMENTS} elements are not accepted")
            return
        tag = _local_name(element.tag)
        if tag in _SCRIPT_ELEMENTS:
            problems.append(f"<{tag}> elements are not accepted (script/embedding vector)")
        if tag == "style":
            # CSS can fetch: url(...) and @import reach whatever the sheet names.
            css = _normalize_css("".join(element.itertext()))
            if "@import" in css:
                problems.append("<style> uses @import (an external stylesheet reference)")
            if "url(" in css and any(token in css for token in
                                     ("http://", "https://", "//", "ftp:", "file:", "data:")):
                problems.append("<style> carries an external url(...) reference")
        for attr_name, attr_value in element.attrib.items():
            local = _local_name(attr_name)
            if local.startswith("on"):
                problems.append(f"event-handler attribute '{attr_name}' is not accepted")
            if local == "style":
                css = _normalize_css(attr_value)
                if "url(" in css and any(token in css for token in
                                         ("http://", "https://", "//", "ftp:", "file:", "data:")):
                    problems.append("style attribute carries an external url(...) reference")
            if local == "attributename" and attr_value.strip().lower().startswith("on"):
                problems.append("SMIL animation targeting an event-handler attribute is not accepted")
            normalized = _normalize_url(attr_value)
            if any(scheme in normalized for scheme in _SCHEME_BLACKLIST):
                problems.append(f"attribute '{attr_name}' carries a script/data-URL payload")
            if local in _URL_ATTRS:
                stripped = attr_value.strip()
                if stripped.lower().startswith(("http://", "https://", "//", "ftp:", "file:")):
                    problems.append(
                        f"attribute '{attr_name}' references an external location")
                elif stripped.lower().startswith("data:") \
                        and not _ALLOWED_INLINE_DATA_RE.fullmatch(stripped):
                    problems.append(
                        f"attribute '{attr_name}' carries a non-inline data: payload "
                        "(only base64 image/png|jpeg|webp is accepted)")
                elif "://" in stripped:
                    problems.append(f"attribute '{attr_name}' carries an absolute URL")
        for child in element:
            walk(child)

    walk(root)
    if problems:
        raise MediaValidationError("; ".join(dict.fromkeys(problems)))
    return data, ["svg passed the sanitizer: no script, handlers, or external references"]


# ---------------------------------------------------------------- JPEG EXIF scrub

_EXIF_KEEP_TAGS = frozenset({
    0x0112,  # Orientation, kept so images still display upright
    0x011A,  # XResolution
    0x011B,  # YResolution
    0x0128,  # ResolutionUnit
})

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _parse_tiff_ifd0(raw: bytes) -> dict[int, bytes]:
    """Return {tag: encoded (type, count, value/offset slice)} for IFD0 entries."""
    if len(raw) < 8:
        raise ValueError("truncated TIFF header")
    endian = raw[:2]
    if endian not in (b"II", b"MM"):
        raise ValueError("bad TIFF byte order")
    order = "<" if endian == b"II" else ">"
    if struct.unpack(order + "H", raw[2:4])[0] != 42:
        raise ValueError("bad TIFF magic")
    ifd_offset = struct.unpack(order + "I", raw[4:8])[0]
    if ifd_offset + 2 > len(raw):
        raise ValueError("truncated IFD0")
    count = struct.unpack(order + "H", raw[ifd_offset:ifd_offset + 2])[0]
    entries: dict[int, bytes] = {}
    for i in range(count):
        base = ifd_offset + 2 + i * 12
        if base + 12 > len(raw):
            raise ValueError("truncated IFD entry")
        tag, typ, num = struct.unpack(order + "HHI", raw[base:base + 8])
        size = _TYPE_SIZES.get(typ, 0) * num
        if size <= 0 or size > 65536:
            continue
        if size <= 4:
            value = raw[base + 8:base + 8 + size]
        else:
            offset = struct.unpack(order + "I", raw[base + 8:base + 12])[0]
            if offset + size > len(raw):
                continue
            value = raw[offset:offset + size]
        entries[tag] = struct.pack(order + "HHI", tag, typ, num) + value.ljust(4, b"\x00")
    return entries


def _build_exif_app1(kept: dict[int, bytes]) -> bytes:
    """Serialize IFD0 entries (big-endian, values ≤ 4 bytes only are expected here)
    into a fresh Exif APP1 segment."""
    order = ">"
    header = b"MM\x00\x2a" + struct.pack(order + "I", 8)
    ifd = struct.pack(order + "H", len(kept))
    data_area = b""
    data_offset = 8 + 2 + len(kept) * 12 + 4
    for tag in sorted(kept):
        entry = kept[tag]
        typ, num = struct.unpack(order + "HH", entry[2:6])
        size = _TYPE_SIZES.get(typ, 0) * num
        if size > 4:
            value = entry[8:8 + size]
            ifd += entry[:8] + struct.pack(order + "I", data_offset + len(data_area))
            data_area += value
            if len(data_area) % 2:
                data_area += b"\x00"
        else:
            ifd += entry
    ifd += struct.pack(order + "I", 0)  # no IFD1 (thumbnail) pointer
    payload = header + ifd + data_area
    # Segment length counts itself + the "Exif\0\0" signature + the TIFF blob.
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2 + 6) + b"Exif\x00\x00" + payload


def scrub_jpeg(data: bytes) -> tuple[bytes, list[str]]:
    """Walk JPEG segments and rebuild metadata from an allowlist.

    Kept: JFIF APP0, and an EXIF APP1 containing only Orientation and resolution
    tags. Stripped: GPS data, camera Model/Make/serial, Software, Artist, maker
    notes, thumbnails (whole Exif sub-IFDs go with their pointers), XMP, ICC
    profiles, and every comment segment. Returns (scrubbed bytes, findings).
    """
    findings: list[str] = []
    if not data.startswith(b"\xff\xd8"):
        raise MediaValidationError("not a JPEG stream (missing SOI)")
    n = len(data)
    i = 2
    exif_tiff: Optional[bytes] = None
    had_exif = False
    out = bytearray(b"\xff\xd8")
    while i + 2 <= n:
        if data[i] != 0xFF:
            raise MediaValidationError("corrupt JPEG: lost marker alignment")
        marker = data[i + 1]
        if marker == 0xD9:  # EOI
            out += b"\xff\xd9"
            i += 2
            break
        if marker == 0xDA:  # SOS: entropy-coded data follows; copy verbatim to the end
            out += data[i:]
            i = n
            break
        if marker in (0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
            out += data[i:i + 2]  # standalone markers carry no length field
            i += 2
            continue
        if i + 4 > n:
            raise MediaValidationError("corrupt JPEG: truncated segment header")
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        if seglen < 2 or i + 2 + seglen > n:
            raise MediaValidationError("corrupt JPEG: segment length overruns the stream")
        segment = data[i + 4:i + 2 + seglen]
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            # Metadata territory: APP0 (JFIF) is kept; the Exif APP1 is rebuilt
            # from the allowlist; every other APPn/COM segment (XMP, ICC, EXIF
            # extensions, comments, maker containers) is dropped.
            if marker == 0xE0:
                out += data[i:i + 2 + seglen]
            elif marker == 0xE1 and segment.startswith(b"Exif\x00\x00"):
                had_exif = True
                tiff = segment[6:]
                try:
                    entries = _parse_tiff_ifd0(tiff)
                except ValueError:
                    findings.append("unreadable EXIF was removed entirely")
                else:
                    kept = {tag: value for tag, value in entries.items() if tag in _EXIF_KEEP_TAGS}
                    stripped = [tag for tag in entries if tag not in _EXIF_KEEP_TAGS]
                    if 0x8769 in entries or 0x8825 in entries:
                        findings.append("EXIF sub-IFDs (GPS, camera details) were stripped")
                    if kept:
                        exif_app1 = _build_exif_app1(kept)
                        out += exif_app1
                    if stripped:
                        findings.append(f"{len(stripped)} EXIF metadata entr(ies) were stripped")
            else:
                findings.append(f"metadata segment FF{marker:02X} was dropped")
        else:
            out += data[i:i + 2 + seglen]   # DQT/SOF/DHT/DRI/..., the image itself, kept verbatim
        i += 2 + seglen
    else:
        raise MediaValidationError("corrupt JPEG: stream ends without EOI/SOS")
    if i < n:  # trailing garbage after EOI
        findings.append("bytes after EOI were dropped")
    if not had_exif:
        findings.append("no EXIF metadata was present")
    return bytes(out), findings


# ---------------------------------------------------------------- entry point


def validate_media(data: bytes, *, expected_format: Optional[str] = None,
                   max_bytes: int = MAX_MEDIA_BYTES) -> MediaValidation:
    """Validate result bytes end to end: sniff the real format, cross-check it
    against any declared expectation, sanitize/scrub, extract dimensions.

    Raises :class:`MediaValidationError` with a precise reason on any mismatch,    the caller never receives bytes nobody inspected.
    """
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise MediaValidationError("media bytes are empty")
    data = bytes(data)
    if len(data) > max_bytes:
        raise MediaValidationError(
            f"media exceeds the {max_bytes // 1_000_000} MB limit")
    findings: list[str] = []
    fmt = sniff_format(data)
    if fmt == "gif":
        raise MediaValidationError(
            "the result is a GIF; GIF is not a supported media format and hutch "
            "does not transcode silently")
    if fmt is None and looks_like_svg(data):
        fmt = "svg+xml"
    if fmt is None:
        raise MediaValidationError(
            "the result's format could not be identified from its magic bytes; "
            "unidentified bytes are never stored")
    if fmt not in MEDIA_FORMATS:
        raise MediaValidationError(f"unsupported media format: {fmt}")
    if expected_format is not None and expected_format != fmt:
        raise MediaValidationError(
            f"the result is {fmt} but {expected_format} was expected; the mismatch "
            "is reported, not papered over")
    if fmt == "svg+xml":
        data, findings = sanitize_svg(data)
    elif fmt == "jpeg":
        data, findings = scrub_jpeg(data)
    width, height = image_dimensions(data, fmt)
    return MediaValidation(format=fmt, mime=MIME_BY_FORMAT[fmt], bytes=len(data),
                           width=width, height=height, scrubbed=data, findings=findings)


def mime_for(fmt: str) -> str:
    if fmt not in MIME_BY_FORMAT:
        raise MediaValidationError(f"unsupported media format: {fmt}")
    return MIME_BY_FORMAT[fmt]
