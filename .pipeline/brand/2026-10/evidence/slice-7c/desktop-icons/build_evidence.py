#!/usr/bin/env python3
"""Build Slice 7C evidence for the Tauri desktop icon family.

Re-runnable evidence builder (writes only under
.pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/ plus the two declared
write scopes: assets/production/desktop/ and desktop/icons/):

  1. capture pre-replacement hashes of the legacy desktop/icons/ family
  2. run build_desktop_icons.py twice and prove byte-identical output
  3. stage byte-identical copies into desktop/icons/ and cmp-verify them
  4. file(1) + identify(1) the PNGs, extract and inspect container payloads
  5. byte-level parse of the ICO and ICNS containers
  6. alpha checks: corners transparent, plate pixels opaque #09090b
  7. ICNS ic14 (512 px) payload parity against approved icon-512.png
  8. ImageMagick contact sheet on a dark #18181b background
  9. desktop-icons-evidence.json with all paths, sizes, hashes and commands

Usage:
    .venv/bin/python .pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/build_evidence.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from importlib.metadata import version as package_version
from pathlib import Path

REPO = Path("/home/kevina/CodingProjects/hutch")
ASSETS = REPO / ".pipeline/brand/2026-10/assets"
PROD = ASSETS / "production"
GDIR = PROD / "desktop"
ICONS = REPO / "desktop/icons"
EVID = REPO / ".pipeline/brand/2026-10/evidence/slice-7c/desktop-icons"
PAYLOADS = EVID / "payloads"
GENERATOR = ASSETS / "build_desktop_icons.py"
MARK_MASTER = PROD / "svg/hutch-mark-master.svg"
APPROVED_ICON_512 = PROD / "icons/icon-512.png"

sys.path.insert(0, str(ASSETS))
import build_desktop_icons as bdi  # noqa: E402

FILES = ["32x32.png", "128x128.png", "128x128@2x.png", "icon.png", "icon.ico", "icon.icns", "icon.svg"]
PNG_FILES = FILES[:4]
PNG_DIMS = {"32x32.png": 32, "128x128.png": 128, "128x128@2x.png": 256, "icon.png": 1024}
LEGACY_FILES = ["icon.icns", "icon.ico", "icon.png", "icon.svg"]

PLATE_RGB = (9.0, 9.0, 11.0)
CORNER_KEYS = ("corner_tl", "corner_tr", "corner_bl", "corner_br")
# 8-bit alpha tolerance for Chromium sub-pixel antialiasing of the rx=7 plate
# arc at the 16 px payload (observed max 12/255); a real opaque background fill
# would be 255/255. The four standalone PNGs (>=32 px) measure exactly 0.
CORNER_ALPHA_TOLERANCE = 0.05


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
    )


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def rel_or_abs(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise (venv symlinks resolve outside)."""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path.resolve())


def parse_pixel(value: str) -> dict:
    match = re.fullmatch(r"(s?rgba?)\(([^)]*)\)", value)
    if not match:
        raise ValueError(f"unexpected pixel value {value!r}")
    numbers = [float(part) for part in match.group(2).split(",")]
    if len(numbers) == 3:
        numbers.append(1.0)
    return {"value": value, "r": numbers[0], "g": numbers[1], "b": numbers[2], "a": numbers[3]}


def image_pixels(path: Path, samples: dict) -> dict:
    expr = " ".join(f"{name}=%[pixel:p{{{x},{y}}}]" for name, (x, y) in samples.items())
    out = run(["convert", str(path), "-format", expr, "info:"]).stdout
    found = dict(re.findall(r"(\w+)=((?:s?rgba?)\([^)]*\))", out))
    if set(found) != set(samples):
        raise RuntimeError(f"pixel read mismatch for {path}: {out!r}")
    return {name: parse_pixel(found[name]) for name in samples}


def alpha_check(path: Path, width: int, height: int, label: str | None = None) -> dict:
    samples = {
        "corner_tl": (0, 0),
        "corner_tr": (width - 1, 0),
        "corner_bl": (0, height - 1),
        "corner_br": (width - 1, height - 1),
        "center": (width // 2, height // 2),
        "plate_left_mid": (max(1, width // 8), height // 2),
    }
    pixels = image_pixels(path, samples)
    corner_max_alpha = max(pixels[key]["a"] for key in CORNER_KEYS)
    corners_transparent = corner_max_alpha <= CORNER_ALPHA_TOLERANCE

    def is_plate(pixel: dict) -> bool:
        return (
            pixel["a"] == 1.0
            and all(abs(pixel[channel] - plate) <= 0.01 for channel, plate in zip(("r", "g", "b"), PLATE_RGB))
        )

    return {
        "file": label or rel(path),
        "width": width,
        "height": height,
        "samples": pixels,
        "corner_max_alpha": corner_max_alpha,
        "corners_transparent": corners_transparent,
        "center_plate_opaque": is_plate(pixels["center"]),
        "plate_left_mid_opaque": is_plate(pixels["plate_left_mid"]),
        "pass": corners_transparent and is_plate(pixels["center"]) and is_plate(pixels["plate_left_mid"]),
    }


def parse_ico_container(path: Path) -> dict:
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    entries = []
    for index in range(count):
        start = 6 + 16 * index
        w, h, colours, res, planes, bpp, length, offset = struct.unpack("<BBBBHHII", data[start : start + 16])
        payload = data[offset : offset + length]
        width, height = bdi.png_dimensions(payload)
        declared = 256 if w == 0 else w
        entries.append(
            {
                "index": index,
                "declared_size": declared,
                "width_byte": w,
                "height_byte": h,
                "planes": planes,
                "bit_count": bpp,
                "offset": offset,
                "length": length,
                "payload_sha256": sha256_bytes(payload),
                "png_magic": payload[:8] == bdi.PNG_MAGIC,
                "width": width,
                "height": height,
                "payload": payload,
            }
        )
    return {
        "header": {"reserved": reserved, "type": kind, "count": count},
        "file_bytes": len(data),
        "entries": entries,
        "declared_and_actual_dims_match": all(
            entry["width"] == entry["declared_size"] == entry["height"] for entry in entries
        ),
        "all_png_magic": all(entry["png_magic"] for entry in entries),
    }


def parse_icns_container(path: Path) -> dict:
    data = path.read_bytes()
    magic = data[:4].decode("ascii")
    total = struct.unpack(">I", data[4:8])[0]
    entries = []
    offset = 8
    while offset < len(data):
        type_code = data[offset : offset + 4].decode("ascii")
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        payload = data[offset + 8 : offset + length]
        width, height = bdi.png_dimensions(payload)
        entries.append(
            {
                "type": type_code,
                "offset": offset,
                "length": length,
                "payload_length": len(payload),
                "payload_sha256": sha256_bytes(payload),
                "png_magic": payload[:8] == bdi.PNG_MAGIC,
                "width": width,
                "height": height,
                "payload": payload,
            }
        )
        offset += length
    return {
        "magic": magic,
        "declared_total_length": total,
        "file_bytes": len(data),
        "length_matches_file": total == len(data),
        "entries": entries,
        "all_png_magic": all(entry["png_magic"] for entry in entries),
    }


def chromium_version() -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            return browser.version
        finally:
            browser.close()


def svg_vector_parity(svg_text: str) -> dict:
    """Render the icon.svg single vector source at 1024 and compare to icon.png."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 1024}, device_scale_factor=1)
            try:
                page.set_content(
                    "<!doctype html><html><body style='margin:0;padding:0;overflow:hidden;"
                    "background:transparent'>" + svg_text + "</body></html>"
                )
                rendered = page.screenshot(omit_background=True)
            finally:
                page.close()
        finally:
            browser.close()
    icon_png = (GDIR / "icon.png").read_bytes()
    return {
        "method": (
            "Chromium renders icon.svg inline at 1024x1024 (device_scale_factor=1, "
            "omit_background=True) and the screenshot is compared byte-for-byte with icon.png"
        ),
        "rendered_sha256": sha256_bytes(rendered),
        "icon_png_sha256": sha256_bytes(icon_png),
        "byte_identical": rendered == icon_png,
    }


def main() -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    GDIR.mkdir(parents=True, exist_ok=True)
    ICONS.mkdir(parents=True, exist_ok=True)

    # -- 1. legacy pre-replacement hashes (pinned on first run) -------------
    legacy_file = EVID / "legacy-before.json"
    if legacy_file.exists():
        legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
    else:
        legacy = {}
        for name in LEGACY_FILES:
            path = ICONS / name
            legacy[name] = {"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        legacy_file.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")

    # -- 2. deterministic generator: two runs, identical bytes --------------
    gen_cmd = [sys.executable, str(GENERATOR)]
    first = run(gen_cmd)
    run1_hashes = {name: sha256_file(GDIR / name) for name in FILES}
    second = run(gen_cmd)
    run2_hashes = {name: sha256_file(GDIR / name) for name in FILES}
    generated_names = sorted(path.name for path in GDIR.iterdir())
    if generated_names != sorted(FILES):
        raise RuntimeError(f"unexpected generated files: {generated_names}")

    determinism = {
        "command": ".venv/bin/python .pipeline/brand/2026-10/assets/build_desktop_icons.py",
        "runs": 2,
        "identical_sha256": run1_hashes == run2_hashes,
        "identical_stdout": first.stdout == second.stdout,
        "run1_sha256": run1_hashes,
        "run2_sha256": run2_hashes,
    }
    if not (determinism["identical_sha256"] and determinism["identical_stdout"]):
        raise RuntimeError("generator is not deterministic")
    (EVID / "generator-run.log").write_text(first.stdout, encoding="utf-8")

    # -- 3. stage byte-identical copies into desktop/icons/ ------------------
    staged = []
    parity_lines = [
        "Byte parity: generated (.pipeline/brand/2026-10/assets/production/desktop/)",
        "vs staged (desktop/icons/), verified with cmp -s (exit 0 == identical).",
        "",
    ]
    for name in FILES:
        source = GDIR / name
        target = ICONS / name
        shutil.copyfile(source, target)
        result = run(["cmp", "-s", rel(source), rel(target)])
        identical = source.read_bytes() == target.read_bytes()
        if result.returncode != 0 or not identical:
            raise RuntimeError(f"staged copy differs for {name}")
        parity_lines.append(f"cmp -s {rel(source)} {rel(target)} => exit {result.returncode} OK")
        staged.append(
            {
                "path": rel(target),
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "generated_path": rel(source),
                "generated_sha256": sha256_file(source),
                "byte_identical_to_generated": identical,
                "cmp_exit": result.returncode,
            }
        )
    parity_lines.append("")
    parity_lines.append(f"all {len(FILES)} staged files byte-identical: True")
    (EVID / "parity.txt").write_text("\n".join(parity_lines) + "\n", encoding="utf-8")

    # -- 4. sha256sum output ------------------------------------------------
    generated_sum = run(["sha256sum"] + [rel(GDIR / name) for name in FILES]).stdout
    staged_sum = run(["sha256sum"] + [rel(ICONS / name) for name in FILES]).stdout
    (EVID / "sha256sums.txt").write_text(
        "# Generated (assets/production/desktop)\n"
        + generated_sum
        + "\n# Staged (desktop/icons)\n"
        + staged_sum,
        encoding="utf-8",
    )

    # -- 5. file(1) and identify(1) for all PNGs ----------------------------
    file_lines = ["file(1) - generated:", run(["file"] + [rel(GDIR / name) for name in FILES]).stdout.rstrip(), ""]
    file_lines.append("file(1) - staged:")
    file_lines.append(run(["file"] + [rel(ICONS / name) for name in FILES]).stdout.rstrip())
    file_lines.append("")

    def identify_line(path: Path) -> str:
        dims_channels = run(["identify", "-format", "%wx%h %[channels]", str(path)]).stdout
        return f"{rel(path)}\t{dims_channels}"

    file_lines.append("identify -format '%wx%h %[channels]' - generated PNGs:")
    for name in PNG_FILES:
        file_lines.append(identify_line(GDIR / name))
    file_lines.append("")
    file_lines.append("identify -format '%wx%h %[channels]' - staged PNGs:")
    for name in PNG_FILES:
        file_lines.append(identify_line(ICONS / name))
    file_lines.append("")

    # -- 6. container byte-level parsing ------------------------------------
    ico = parse_ico_container(GDIR / "icon.ico")
    icns = parse_icns_container(GDIR / "icon.icns")
    if [entry["declared_size"] for entry in ico["entries"]] != [16, 32, 48, 64, 128, 256]:
        raise RuntimeError("unexpected ICO entry sizes")
    expected_icns = [
        ("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic08", 256),
        ("ic09", 512), ("ic10", 1024), ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512),
    ]
    if [(entry["type"], entry["width"]) for entry in icns["entries"]] != expected_icns:
        raise RuntimeError("unexpected ICNS entry types/dimensions")
    if not all(entry["height"] == entry["width"] for entry in icns["entries"]):
        raise RuntimeError("unexpected ICNS non-square payload")

    container_lines = [
        f"ICO container: {rel(GDIR / 'icon.ico')}",
        f"  header: reserved={ico['header']['reserved']} type={ico['header']['type']} "
        f"count={ico['header']['count']} file_bytes={ico['file_bytes']}",
        "  index  size  width  height  planes  bit_count  offset  length  payload_sha256  png_magic",
    ]
    for entry in ico["entries"]:
        container_lines.append(
            f"  {entry['index']}      {entry['declared_size']:<5} {entry['width']:<6} {entry['height']:<6} "
            f"{entry['planes']:<6} {entry['bit_count']:<9} {entry['offset']:<7} {entry['length']:<7} "
            f"{entry['payload_sha256']}  {entry['png_magic']}"
        )
    container_lines += [
        f"  checks: count={ico['header']['count']} sizes={[entry['declared_size'] for entry in ico['entries']]}",
        f"  checks: all PNG magic=True actual={ico['all_png_magic']} "
        f"declared/actual dims match={ico['declared_and_actual_dims_match']}",
        "",
        f"ICNS container: {rel(GDIR / 'icon.icns')}",
        f"  magic={icns['magic']} declared_total_length={icns['declared_total_length']} "
        f"file_bytes={icns['file_bytes']} matches={icns['length_matches_file']}",
        "  type  width  height  offset  length  payload_length  payload_sha256  png_magic",
    ]
    for entry in icns["entries"]:
        container_lines.append(
            f"  {entry['type']}  {entry['width']:<6} {entry['height']:<6} {entry['offset']:<7} "
            f"{entry['length']:<7} {entry['payload_length']:<15} {entry['payload_sha256']}  {entry['png_magic']}"
        )
    container_lines += [
        f"  checks: {len(icns['entries'])} entries, all PNG magic={icns['all_png_magic']}, "
        f"container length matches file={icns['length_matches_file']}",
        "",
    ]

    # -- 7. extract container payloads, verify PNG payloads + alpha ---------
    approved_512_bytes = APPROVED_ICON_512.read_bytes()
    payload_dir = Path(tempfile.mkdtemp(prefix="slice-7c-payloads-"))
    payload_parity = []
    alpha_records = []
    try:
        standalone_by_size = {
            32: GDIR / "32x32.png",
            128: GDIR / "128x128.png",
            256: GDIR / "128x128@2x.png",
            1024: GDIR / "icon.png",
        }
        for entry in ico["entries"]:
            extracted = payload_dir / f"ico-{entry['index']:02d}-{entry['declared_size']:04d}.png"
            extracted.write_bytes(entry["payload"])
            check = alpha_check(
                extracted,
                entry["width"],
                entry["height"],
                label=f"icon.ico entry {entry['index']} ({entry['declared_size']} px)",
            )
            alpha_records.append(check)
            target = standalone_by_size.get(entry["declared_size"])
            payload_parity.append(
                {
                    "container": "icon.ico",
                    "entry": str(entry["index"]),
                    "size": entry["declared_size"],
                    "payload_sha256": entry["payload_sha256"],
                    "standalone_path": rel(target) if target else None,
                    "standalone_sha256": sha256_bytes(target.read_bytes()) if target else None,
                    "byte_identical": bool(target) and target.read_bytes() == entry["payload"],
                }
            )
        for entry in icns["entries"]:
            extracted = payload_dir / f"icns-{entry['type']}-{entry['width']:04d}.png"
            extracted.write_bytes(entry["payload"])
            check = alpha_check(
                extracted,
                entry["width"],
                entry["height"],
                label=f"icon.icns {entry['type']} ({entry['width']} px)",
            )
            alpha_records.append(check)
            target = standalone_by_size.get(entry["width"])
            if entry["width"] == 512:
                target = APPROVED_ICON_512
            payload_parity.append(
                {
                    "container": "icon.icns",
                    "entry": entry["type"],
                    "size": entry["width"],
                    "payload_sha256": entry["payload_sha256"],
                    "standalone_path": rel(target) if target else None,
                    "standalone_sha256": sha256_bytes(target.read_bytes()) if target else None,
                    "byte_identical": bool(target) and target.read_bytes() == entry["payload"],
                }
            )
        file_lines.append("identify -format '%wx%h %[channels]' - container payloads (extracted):")
        for extracted in sorted(payload_dir.iterdir()):
            dims_channels = run(["identify", "-format", "%wx%h %[channels]", str(extracted)]).stdout
            file_lines.append(f"{extracted.name}\t{dims_channels}")
        file_lines.append("")
        failing = [record for record in alpha_records if not record["pass"]]
        if failing:
            raise RuntimeError(f"alpha check failed for container payloads: {[record['file'] for record in failing]}")
        if not all(record["byte_identical"] for record in payload_parity if record["standalone_path"]):
            raise RuntimeError("container payload parity check failed")
    finally:
        shutil.rmtree(payload_dir, ignore_errors=True)

    # -- 8. named PNG alpha checks ------------------------------------------
    named_alpha = {}
    for name in PNG_FILES:
        check = alpha_check(GDIR / name, PNG_DIMS[name], PNG_DIMS[name], label=rel(GDIR / name))
        named_alpha[name] = check
        if not check["pass"]:
            raise RuntimeError(f"alpha check failed for {name}: {check}")

    (EVID / "file-identify.txt").write_text("\n".join(file_lines), encoding="utf-8")
    (EVID / "containers.txt").write_text("\n".join(container_lines), encoding="utf-8")

    # -- 9. ICNS ic14 payload vs approved icon-512.png ----------------------
    ic14 = next(entry for entry in icns["entries"] if entry["type"] == "ic14")
    approved_512_sha = sha256_bytes(approved_512_bytes)
    icon_512_parity = {
        "container": rel(GDIR / "icon.icns"),
        "entry_type": "ic14",
        "payload_size": ic14["payload_length"],
        "payload_sha256": ic14["payload_sha256"],
        "approved_asset": rel(APPROVED_ICON_512),
        "approved_asset_sha256": approved_512_sha,
        "byte_identical": ic14["payload"] == approved_512_bytes,
    }
    if not icon_512_parity["byte_identical"]:
        raise RuntimeError("ICNS ic14 payload does not match approved icon-512.png")

    # -- 10. icon.svg single-vector checks ----------------------------------
    svg_text = (GDIR / "icon.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg_text)
    ns = "{http://www.w3.org/2000/svg}"
    rect = root.find(f"{ns}rect")
    group = root.find(f"{ns}g")
    path = group.find(f"{ns}path") if group is not None else None
    master_d = bdi.read_master_d()
    svg_checks = {
        "root_tag": root.tag,
        "width": root.get("width"),
        "height": root.get("height"),
        "viewBox": root.get("viewBox"),
        "rect_width": rect.get("width") if rect is not None else None,
        "rect_height": rect.get("height") if rect is not None else None,
        "rect_rx": rect.get("rx") if rect is not None else None,
        "rect_fill": rect.get("fill") if rect is not None else None,
        "group_transform": group.get("transform") if group is not None else None,
        "path_fill": path.get("fill") if path is not None else None,
        "path_fill_rule": path.get("fill-rule") if path is not None else None,
        "path_matches_master_svg": bool(path is not None) and path.get("d") == master_d,
        "tokens_expected": "<rect width=\"32\" height=\"32\" rx=\"7\" fill=\"#09090b\"/> present: "
        + str('<rect width="32" height="32" rx="7" fill="#09090b"/>' in svg_text),
    }
    if not (
        svg_checks["width"] == svg_checks["height"] == "1024"
        and svg_checks["viewBox"] == "0 0 32 32"
        and (svg_checks["rect_rx"], svg_checks["rect_fill"]) == ("7", "#09090b")
        and svg_checks["path_fill"] == "#34d399"
        and svg_checks["path_fill_rule"] == "evenodd"
        and svg_checks["path_matches_master_svg"]
    ):
        raise RuntimeError("icon.svg single-vector checks failed")
    svg_render_parity = svg_vector_parity(svg_text)
    if not svg_render_parity["byte_identical"]:
        raise RuntimeError("icon.svg render does not match icon.png")
    (EVID / "alpha-pixels.txt").write_text(
        "\n".join(
            [
                "Alpha/corner pixel checks (ImageMagick pixel sampling, RGBA).",
                "Expectation: the four canvas corners are effectively transparent (alpha=0 exactly for",
                "the four standalone PNGs and every >=32 px payload; up to 12/255 sub-pixel",
                "antialiasing residual at the 16 px payload, tolerance 0.05), the plate pixels are",
                "opaque #09090b (alpha=1), and the mark's visor cutout exposes the plate at the image",
                "center.",
                "",
            ]
            + [
                f"{record['file']}"
                + "\n  corners: "
                + ", ".join(f"{key}={record['samples'][key]['value']}" for key in CORNER_KEYS)
                + f"\n  center={record['samples']['center']['value']} "
                + f"plate_left_mid={record['samples']['plate_left_mid']['value']}"
                + f"\n  corner_max_alpha={record['corner_max_alpha']:.6f} "
                + f"corners_transparent={record['corners_transparent']} "
                + f"center_plate_opaque={record['center_plate_opaque']} "
                + f"plate_left_mid_opaque={record['plate_left_mid_opaque']} pass={record['pass']}"
                for record in named_alpha.values()
            ]
            + [
                "",
                "Container payloads (extracted from icon.ico / icon.icns):",
            ]
            + [
                f"  {record['file']}: corner_max_alpha={record['corner_max_alpha']:.6f} "
                f"corners_transparent={record['corners_transparent']} "
                f"center_plate_opaque={record['center_plate_opaque']} pass={record['pass']}"
                for record in alpha_records
            ]
            + [""]
        ),
        encoding="utf-8",
    )

    # -- 11. contact sheet (native sizes + nearest-neighbour zooms) ---------
    SHEET_BG = "#18181b"
    SHEET_LABEL_COLOR = "#ededf0"
    SHEET_FONT = "DejaVu-Sans"
    SHEET_POINT_SIZE = 18
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    ic14_png = PAYLOADS / "icns-ic14-512.png"
    ic14_png.write_bytes(ic14["payload"])
    montage_tmp = Path(tempfile.mkdtemp(prefix="slice-7c-montage-"))
    try:
        zoom_32 = montage_tmp / "32-at-8x.png"
        zoom_128 = montage_tmp / "128-at-2x.png"
        run(["convert", str(GDIR / "32x32.png"), "-filter", "point", "-resize", "800%", str(zoom_32)])
        run(["convert", str(GDIR / "128x128.png"), "-filter", "point", "-resize", "200%", str(zoom_128)])

        def label_width(text: str) -> int:
            return int(
                run(
                    [
                        "convert",
                        "-background", SHEET_BG,
                        "-fill", SHEET_LABEL_COLOR,
                        "-font", SHEET_FONT,
                        "-pointsize", str(SHEET_POINT_SIZE),
                        f"label:{text}",
                        "-format", "%w",
                        "info:",
                    ]
                ).stdout
            )

        def padded_cell(source: Path, label: str, name: str) -> Path:
            width, height = bdi.png_dimensions(source.read_bytes())
            cell_width = max(width, label_width(label) + 12)
            cell_path = montage_tmp / name
            run(
                [
                    "convert", str(source),
                    "-background", SHEET_BG,
                    "-gravity", "center",
                    "-extent", f"{cell_width}x{height}",
                    str(cell_path),
                ]
            )
            return cell_path

        tiles = [
            (
                padded_cell(GDIR / "icon.png", "icon.png - 1024 px native", "cell-1024.png"),
                "icon.png - 1024 px native",
            ),
            (
                padded_cell(ic14_png, "icon.icns ic14 payload - 512 px native", "cell-512.png"),
                "icon.icns ic14 payload - 512 px native",
            ),
            (
                padded_cell(GDIR / "128x128@2x.png", "128x128@2x.png - 256 px native", "cell-256.png"),
                "128x128@2x.png - 256 px native",
            ),
            (
                padded_cell(GDIR / "128x128.png", "128x128.png - 128 px native", "cell-128.png"),
                "128x128.png - 128 px native",
            ),
            (
                padded_cell(GDIR / "32x32.png", "32x32.png - 32 px native", "cell-32.png"),
                "32x32.png - 32 px native",
            ),
            (
                padded_cell(zoom_32, "32 px - 8x nearest-neighbour zoom", "cell-zoom-32.png"),
                "32 px - 8x nearest-neighbour zoom",
            ),
            (
                padded_cell(zoom_128, "128 px - 2x nearest-neighbour zoom", "cell-zoom-128.png"),
                "128 px - 2x nearest-neighbour zoom",
            ),
        ]
        grid_path = EVID / "icon-grid.png"
        montage_cmd = [
            "montage",
            "-background", SHEET_BG,
            "-fill", SHEET_LABEL_COLOR,
            "-font", SHEET_FONT,
            "-pointsize", str(SHEET_POINT_SIZE),
        ]
        for cell, label in tiles:
            montage_cmd += ["-label", label, str(cell)]
        montage_cmd += ["-tile", "5x2", "-geometry", "+24+24", str(grid_path)]
        run(montage_cmd)
        grid_identify = run(["identify", "-format", "%wx%h %[channels]", str(grid_path)]).stdout
    finally:
        shutil.rmtree(montage_tmp, ignore_errors=True)

    # -- 12. assemble evidence JSON -----------------------------------------
    environment = {
        "python": sys.version.split()[0],
        "python_executable": rel_or_abs(Path(sys.executable)),
        "playwright": package_version("playwright"),
        "chromium": chromium_version(),
        "imagemagick": run(["convert", "-version"]).stdout.splitlines()[0],
        "renderer": "Playwright headless Chromium, device_scale_factor=1, exact viewport",
    }

    generated_records = []
    for name in FILES:
        path = GDIR / name
        record = {
            "path": rel(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "format": path.suffix.lstrip(".").upper(),
        }
        if name in PNG_DIMS:
            record["width"] = PNG_DIMS[name]
            record["height"] = PNG_DIMS[name]
            record["identify"] = run(["identify", "-format", "%wx%h %[channels]", str(path)]).stdout
        if name == "icon.ico":
            record["container_entries"] = ico["header"]["count"]
        if name == "icon.icns":
            record["container_entries"] = len(icns["entries"])
        generated_records.append(record)

    evidence = {
        "slice": "Pipeline Run 7 / Slice 7C - Tauri desktop icon family",
        "task_id": "task-3",
        "owner": "desktop-icons",
        "evidence_date": "2026-10-29",
        "generator": {
            "path": rel(GENERATOR),
            "sha256": sha256_file(GENERATOR),
            "command": ".venv/bin/python .pipeline/brand/2026-10/assets/build_desktop_icons.py",
            "deterministic": True,
        },
        "source_assets": {
            "mark_svg": {"path": rel(MARK_MASTER), "sha256": sha256_file(MARK_MASTER)},
            "approved_icon_512": {
                "path": rel(APPROVED_ICON_512),
                "sha256": approved_512_sha,
                "bytes": len(approved_512_bytes),
            },
        },
        "composition": {
            "plate": {"full_bleed_rect": True, "fill": "#09090b", "rx": 7},
            "mark": {
                "source": rel(MARK_MASTER),
                "path_d": "byte-for-byte the hutch-mark-master.svg compound path",
                "fill": "#34d399",
                "fill_rule": "evenodd",
                "transform": bdi.MARK_TRANSFORM,
            },
            "raster": {
                "omit_background": bdi.OMIT_BACKGROUND,
                "device_scale_factor": 1,
                "png": "8-bit RGBA, rounded-plate corners transparent outside the rx=7 plate",
            },
        },
        "generated": generated_records,
        "staged": staged,
        "replaced_legacy": legacy,
        "container_listings": {
            "icon.ico": {
                "header": ico["header"],
                "file_bytes": ico["file_bytes"],
                "entries": [
                    {
                        key: value
                        for key, value in entry.items()
                        if key not in ("payload", "width_byte", "height_byte", "planes")
                    }
                    for entry in ico["entries"]
                ],
                "declared_and_actual_dims_match": ico["declared_and_actual_dims_match"],
                "all_png_magic": ico["all_png_magic"],
            },
            "icon.icns": {
                "magic": icns["magic"],
                "declared_total_length": icns["declared_total_length"],
                "file_bytes": icns["file_bytes"],
                "length_matches_file": icns["length_matches_file"],
                "entries": [
                    {
                        key: value
                        for key, value in entry.items()
                        if key not in ("payload", "payload_length")
                    }
                    for entry in icns["entries"]
                ],
                "all_png_magic": icns["all_png_magic"],
            },
        },
        "payload_parity": payload_parity,
        "alpha_check": {
            "method": (
                "ImageMagick pixel sampling: RGBA values read at the four canvas corners, the "
                "image center and a plate-only left-mid pixel for every standalone PNG and for "
                "every PNG payload extracted from the ICO and ICNS containers."
            ),
            "expectation": (
                "corners fully transparent because the plate is rounded (the four standalone PNGs "
                "measure alpha=0 exactly; the 16 px container payload shows up to 12/255 residual "
                "alpha from Chromium sub-pixel antialiasing of the rx=7 arc, not a background fill; "
                "tolerance 0.05); plate pixels fully opaque #09090b (srgba(9,9,11,1)); image center "
                "exposes the plate through the mark's visor cutout."
            ),
            "standalone_pngs": named_alpha,
            "container_payloads": alpha_records,
            "all_pass": all(record["pass"] for record in named_alpha.values())
            and all(record["pass"] for record in alpha_records),
        },
        "icon_512_parity": icon_512_parity,
        "determinism": determinism,
        "svg_checks": svg_checks,
        "svg_vector_parity": svg_render_parity,
        "validation_sheet": {
            "path": rel(EVID / "icon-grid.png"),
            "bytes": (EVID / "icon-grid.png").stat().st_size,
            "sha256": sha256_file(EVID / "icon-grid.png"),
            "dimensions": grid_identify.strip(),
            "background": "#18181b dark (slightly lighter than the #09090b plate so the rounded plate silhouette is visible)",
            "command": "montage -background '#18181b' ... (native 32/128/256/512/1024 + nearest-neighbour zooms)",
            "renders_shown": [
                "icon.png (1024)",
                "icon.icns ic14 payload (512)",
                "128x128@2x.png (256)",
                "128x128.png (128)",
                "32x32.png (32)",
                "32 px 8x nearest-neighbour zoom",
                "128 px 2x nearest-neighbour zoom",
            ],
            "inspection": {"status": "pending", "method": "read_image on the contact sheet"},

        },
        "commands": [
            ".venv/bin/python .pipeline/brand/2026-10/assets/build_desktop_icons.py  # run twice for determinism",
            "sha256sum <generated 7 files>",
            "sha256sum <staged 7 files>",
            "cmp -s <generated file> <staged file>  # for each of the 7 staged files",
            "file <generated files>; file <staged files>",
            "identify -format '%wx%h %[channels]' <generated/staged PNGs and extracted container payloads>",
            "python3: struct-parse icon.ico (count/sizes/offsets/bit counts) and icon.icns (magic/total length/type codes/lengths/PNG magic/IHDR dims)",
            "convert <png> -format '%[pixel:p{x,y}]' info:  # corner/center/plate alpha checks",
            ".venv/bin/python .pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/build_evidence.py",
            "montage -background '#18181b' ... icon-grid.png",
            "Chromium icon.svg -> 1024 px render, byte-compared with icon.png (single-vector parity)",
            "read_image .pipeline/brand/2026-10/evidence/slice-7c/desktop-icons/icon-grid.png",
        ],
        "environment": environment,
        "decision_note": (
            "A-vs-B/C omit_background decision: the four plated PNGs are rendered with "
            "omit_background=True (Option A). The original task wording said "
            "'opaque plate (omit_background=False)'; with the reference recipe (transparent "
            "page body) Chromium fills the area outside the rx=7 plate with white at "
            "omit_background=False (Option B), producing white corner blocks, and a "
            "variation that sets an opaque #09090b page background (Option C) loses the "
            "rounded-plate silhouette. Lead confirmed Option A: Tauri/deb/AppImage/macOS "
            "app-icon conventions expect the opaque rounded plate as the shape with "
            "transparency outside it, and the approved production/icons/icon-512.png was "
            "itself rendered with omit_background=True (byte parity proof below). All plate "
            "pixels remain fully opaque #09090b and every PNG is 8-bit RGBA."
        ),
        "u07_resolution": (
            "U07 (desktop icon family drift) is closed at source and raster level. The four "
            "legacy files (icon.svg/icon.png/icon.ico/icon.icns) used an undocumented "
            "pointy-top hexagon mark: #28cd9d stroke on a #0f151e rounded plate, geometry "
            "differing from every documented Hutch mark. They are now replaced by the "
            "maintainer-approved 'Visor Hutch' master mark (hutch-mark-master.svg, #34d399, "
            "fill-rule evenodd) centred on the documented full-bleed #09090b rx=7 plate - "
            "the exact composition already used by production/icons/icon-512.png. Seven "
            "files are generated deterministically into "
            ".pipeline/brand/2026-10/assets/production/desktop/ (32x32.png, 128x128.png, "
            "128x128@2x.png, icon.png, icon.ico, icon.icns, icon.svg) and staged "
            "byte-identically into desktop/icons/; icon.svg is now a 1024x1024 single-vector "
            "source (viewBox 0 0 32 32) that matches the rasters, and the ICNS ic14 512 px "
            "payload is byte-identical to the approved icon-512.png (sha256 "
            "ce3da0b9be7a4ee66a168f639cc854d3493cc2f132e43a7c3120756ae5226af5), so the "
            "desktop host no longer carries a divergent mark variant. "
            "desktop/tauri.bundle.conf.json is intentionally unchanged (it lists only "
            "icons/icon.png, icons/icon.ico, icons/icon.icns)."
        ),
        "caveats": [
            "ImageMagick 7 in this environment has no ICNS decode delegate, so icon.icns is validated by byte-level Python parsing plus PNG payload extraction/IHDR/alpha checks, not by identify(1) on the .icns file itself.",
            "PNG bytes are Chromium-build dependent; determinism is guaranteed for a fixed toolchain (versions recorded in environment) and was verified by two consecutive generator runs with identical sha256 for all 7 outputs.",
            "The staged Tauri-convention PNGs 32x32.png, 128x128.png and 128x128@2x.png are not referenced by desktop/tauri.bundle.conf.json (which lists only icon.png/icon.ico/icon.icns); the config was left unchanged as required.",
            "Legacy desktop/icons/ files were replaced in the working tree; they remain tracked so the maintainer can review/revert via git (no commit was made).",
        ],
    }
    evidence_path = EVID / "desktop-icons-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    # -- 13. concise console summary ---------------------------------------
    print("Slice 7C evidence written to", rel(EVID))
    print("generated + staged files:")
    for record in generated_records:
        print(f"  {record['path']:<86} {record['bytes']:>8} B  {record['sha256']}")
    print("determinism:", determinism["identical_sha256"], "| ICNS ic14 == approved icon-512:", icon_512_parity["byte_identical"])
    print("icon.svg render == icon.png:", svg_render_parity["byte_identical"])
    print("container checks: ICO", ico["header"]["count"], "entries", [entry["declared_size"] for entry in ico["entries"]])
    print("                  ICNS", len(icns["entries"]), "entries", [entry["type"] for entry in icns["entries"]])
    print("alpha checks:", "ALL PASS" if evidence["alpha_check"]["all_pass"] else "FAIL")
    print("evidence JSON:", rel(evidence_path))
    print("contact sheet:", rel(EVID / "icon-grid.png"))


if __name__ == "__main__":
    main()

