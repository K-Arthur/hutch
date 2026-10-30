#!/usr/bin/env python3
"""Build the deterministic Tauri desktop icon family for Hutch (Slice 7C).

Composition (single source of truth)
------------------------------------
BRAND-GUIDELINES.md section 8 ("Desktop Host") specifies the approved plated
mark: the hutch-mark-master.svg compound path filled #34d399 on a full-bleed
#09090b rounded plate (rx=7). That is exactly the SVG composition used by
build_production_package.py to render production/icons/icon-512.png:

    <rect width="32" height="32" rx="7" fill="#09090b"/>
    <g transform="translate(2.88, 2.88) scale(0.82)">
      <path d="<hutch-mark-master.svg path>" fill="#34d399" fill-rule="evenodd"/>
    </g>

Outputs (write scope: assets/production/desktop/ only)
------------------------------------------------------
    32x32.png          32 px plated PNG
    128x128.png        128 px plated PNG
    128x128@2x.png     256 px plated PNG
    icon.png           1024 px plated PNG
    icon.ico           ICO container, PNG payloads 16/32/48/64/128/256 px
    icon.icns          ICNS container, PNG payloads icp4, icp5, icp6, ic07..ic14
    icon.svg           1024x1024 single-vector plated source (viewBox 0 0 32 32)

Determinism
-----------
Fixed viewport, device_scale_factor=1, no clock, randomness, counters, network
or fonts; Chromium screenshot bytes for identical markup are stable, so a
re-run reproduces every output byte-for-byte.

Usage
-----
    .venv/bin/python .pipeline/brand/2026-10/assets/build_desktop_icons.py
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROD_DIR = HERE / "production"
OUT_DIR = PROD_DIR / "desktop"
MARK_MASTER_SVG = PROD_DIR / "svg" / "hutch-mark-master.svg"

PLATE_FILL = "#09090b"
PLATE_RX = 7
MARK_FILL = "#34d399"
MARK_TRANSFORM = "translate(2.88, 2.88) scale(0.82)"

# The approved production/icons/icon-512.png plate is screenshotted with
# omit_background=True, so the transparent page shows through the rounded
# corners outside the rx=7 plate. Same choice here; verified to reproduce the
# approved icon-512.png byte-for-byte (see slice-7c evidence).
OMIT_BACKGROUND = True

PNG_TARGETS: tuple[tuple[str, int], ...] = (
    ("32x32.png", 32),
    ("128x128.png", 128),
    ("128x128@2x.png", 256),
    ("icon.png", 1024),
)

ICO_SIZES: tuple[int, ...] = (16, 32, 48, 64, 128, 256)

ICNS_ENTRIES: tuple[tuple[str, int], ...] = (
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
    ("ic11", 32),
    ("ic12", 64),
    ("ic13", 256),
    ("ic14", 512),
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) from a PNG IHDR chunk."""
    if data[:8] != PNG_MAGIC:
        raise ValueError("not a PNG payload")
    if data[12:16] != b"IHDR":
        raise ValueError("first PNG chunk is not IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def read_master_d() -> str:
    """Read the single compound path d from hutch-mark-master.svg."""
    text = MARK_MASTER_SVG.read_text(encoding="utf-8")
    match = re.search(r'<path\s+d="([^"]+)"', text)
    if not match:
        raise ValueError(f"no <path d> found in {MARK_MASTER_SVG}")
    return match.group(1)


def composition_markup(size: int, mark_d: str) -> str:
    """Plated mark SVG markup for an exact-size square render."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 32 32">'
        f'<rect width="32" height="32" rx="{PLATE_RX}" fill="{PLATE_FILL}"/>'
        f'<g transform="{MARK_TRANSFORM}">'
        f'<path d="{mark_d}" fill="{MARK_FILL}" fill-rule="evenodd"/>'
        f"</g></svg>"
    )


def render_png(browser, size: int, mark_d: str) -> bytes:
    """Screenshot the plated mark at exactly size x size (device pixels)."""
    page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
    try:
        page.set_content(
            "<!doctype html><html><body style='margin:0;padding:0;overflow:hidden;"
            "background:transparent'>"
            + composition_markup(size, mark_d)
            + "</body></html>"
        )
        return page.screenshot(omit_background=OMIT_BACKGROUND)
    finally:
        page.close()


def write_ico(path: Path, payloads: list[tuple[int, bytes]]) -> None:
    """Write a standard Windows ICO container embedding PNG payloads."""
    num = len(payloads)
    header = struct.pack("<HHH", 0, 1, num)
    offset = 6 + 16 * num
    entries = bytearray()
    body = bytearray()
    for dim, data in payloads:
        width_byte = 0 if dim >= 256 else dim
        height_byte = 0 if dim >= 256 else dim
        entries += struct.pack(
            "<BBBBHHII", width_byte, height_byte, 0, 0, 1, 32, len(data), offset
        )
        body += data
        offset += len(data)
    path.write_bytes(header + bytes(entries) + bytes(body))


def parse_ico(path: Path) -> list[dict]:
    """Parse an ICO container and verify its PNG payloads."""
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if (reserved, kind) != (0, 1):
        raise ValueError(f"{path}: bad ICO header")
    entries = []
    for index in range(count):
        start = 6 + 16 * index
        w, h, colours, res, planes, bpp, length, offset = struct.unpack(
            "<BBBBHHII", data[start : start + 16]
        )
        payload = data[offset : offset + length]
        if payload[:8] != PNG_MAGIC:
            raise ValueError(f"{path}: entry {index} is not a PNG payload")
        width, height = png_dimensions(payload)
        declared = 256 if w == 0 else w
        if (width, height) != (declared, declared) or (256 if h == 0 else h) != height:
            raise ValueError(f"{path}: entry {index} IHDR mismatch")
        entries.append(
            {
                "index": index,
                "declared_size": declared,
                "width": width,
                "height": height,
                "planes": planes,
                "bit_count": bpp,
                "offset": offset,
                "length": length,
                "png_magic": True,
                "sha256": sha256_hex(payload),
            }
        )
    if sum(entry["length"] for entry in entries) + 6 + 16 * count != len(data):
        raise ValueError(f"{path}: container length mismatch")
    return entries


def write_icns(path: Path, entries: list[tuple[str, bytes]]) -> None:
    """Write an ICNS container: magic, big-endian total length, then entries."""
    body = bytearray()
    for type_code, payload in entries:
        if len(type_code) != 4:
            raise ValueError(f"ICNS type code must be 4 bytes: {type_code!r}")
        body += type_code.encode("ascii")
        body += struct.pack(">I", 8 + len(payload))
        body += payload
    data = b"icns" + struct.pack(">I", 8 + len(body)) + bytes(body)
    path.write_bytes(data)


def parse_icns(path: Path) -> list[dict]:
    """Parse an ICNS container and verify its PNG payloads."""
    data = path.read_bytes()
    if data[:4] != b"icns":
        raise ValueError(f"{path}: bad ICNS magic")
    total = struct.unpack(">I", data[4:8])[0]
    if total != len(data):
        raise ValueError(f"{path}: declared length {total} != file length {len(data)}")
    entries = []
    offset = 8
    while offset < len(data):
        type_code = data[offset : offset + 4].decode("ascii")
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        if length < 8 or offset + length > len(data):
            raise ValueError(f"{path}: bad entry length at offset {offset}")
        payload = data[offset + 8 : offset + length]
        if payload[:8] != PNG_MAGIC:
            raise ValueError(f"{path}: entry {type_code} is not a PNG payload")
        width, height = png_dimensions(payload)
        entries.append(
            {
                "type": type_code,
                "offset": offset,
                "length": length,
                "payload_length": len(payload),
                "width": width,
                "height": height,
                "png_magic": True,
                "sha256": sha256_hex(payload),
            }
        )
        offset += length
    if offset != len(data):
        raise ValueError(f"{path}: trailing bytes after last entry")
    return entries


def icon_svg(mark_d: str) -> str:
    """Single-vector plated source matching the rasters (viewBox 0 0 32 32)."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 32 32">\n'
        f'  <rect width="32" height="32" rx="{PLATE_RX}" fill="{PLATE_FILL}"/>\n'
        f'  <g transform="{MARK_TRANSFORM}">\n'
        f'    <path d="{mark_d}" fill="{MARK_FILL}" fill-rule="evenodd"/>\n'
        "  </g>\n"
        "</svg>\n"
    )


def main() -> None:
    mark_d = read_master_d()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    output_names = [name for name, _ in PNG_TARGETS] + ["icon.ico", "icon.icns", "icon.svg"]
    for name in output_names:
        (OUT_DIR / name).unlink(missing_ok=True)

    # Render each unique size once; identical sizes are reused so container
    # payloads stay byte-identical to the standalone PNG of the same size.
    payloads: dict[int, bytes] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            sizes = [size for _, size in PNG_TARGETS]
            sizes += [size for size in ICO_SIZES if size not in sizes]
            sizes += [size for _, size in ICNS_ENTRIES if size not in sizes]
            for size in sizes:
                payloads[size] = render_png(browser, size, mark_d)
        finally:
            browser.close()

    for name, size in PNG_TARGETS:
        data = payloads[size]
        if png_dimensions(data) != (size, size):
            raise ValueError(f"{name}: rendered {png_dimensions(data)}, expected {size}x{size}")
        (OUT_DIR / name).write_bytes(data)

    write_ico(OUT_DIR / "icon.ico", [(size, payloads[size]) for size in ICO_SIZES])
    write_icns(
        OUT_DIR / "icon.icns",
        [(type_code, payloads[size]) for type_code, size in ICNS_ENTRIES],
    )
    (OUT_DIR / "icon.svg").write_text(icon_svg(mark_d), encoding="utf-8")

    # Parse everything back so a bad container can never be written silently.
    ico_entries = parse_ico(OUT_DIR / "icon.ico")
    if [entry["declared_size"] for entry in ico_entries] != list(ICO_SIZES):
        raise ValueError("icon.ico entry sizes mismatch")
    icns_entries = parse_icns(OUT_DIR / "icon.icns")
    if [entry["type"] for entry in icns_entries] != [entry[0] for entry in ICNS_ENTRIES]:
        raise ValueError("icon.icns entry types mismatch")
    for (type_code, size), entry in zip(ICNS_ENTRIES, icns_entries):
        if (entry["width"], entry["height"]) != (size, size):
            raise ValueError(f"icon.icns {type_code}: expected {size}x{size}")
    svg_text = (OUT_DIR / "icon.svg").read_text(encoding="utf-8")
    for needle in (
        'width="1024" height="1024"',
        'viewBox="0 0 32 32"',
        '<rect width="32" height="32" rx="7" fill="#09090b"/>',
        'fill="#34d399" fill-rule="evenodd"',
        mark_d,
    ):
        if needle not in svg_text:
            raise ValueError(f"icon.svg missing {needle!r}")

    print(f"Wrote Tauri desktop icon family to {OUT_DIR}")
    for name in output_names:
        data = (OUT_DIR / name).read_bytes()
        print(f"  {name:<16} {len(data):>8} B  sha256 {sha256_hex(data)}")
    print(f"  icon.ico entries: {', '.join(str(entry['declared_size']) for entry in ico_entries)}")
    print(f"  icon.icns entries: {', '.join(entry['type'] for entry in icns_entries)}")
    print("Self-check: PNG dimensions, ICO/ICNS containers and icon.svg verified.")


if __name__ == "__main__":
    main()
