#!/usr/bin/env python
"""Independent Slice 7C verification capture.

Stands up the same local Hutch preview recipe used by
tests/e2e/test_design_system.py (app_server fixture, lines 68-90): isolated
HUTCH_STATE_DIR, HUTCH_MAX_CONCURRENT=2, create_app(), one Bot, uvicorn on
127.0.0.1 port 0. Then, in Playwright Chromium at 1440x960 with reduced motion:

  * "/" (SPA): five icon/manifest links, same-origin HTTP status and
    content-type of each, manifest JSON icon fetch with PNG dimension checks,
    Bricolage Grotesque font availability and wordmark computed family,
    single-path Visor Hutch Small-tier mark with fill var(--brand), and
    desktop screenshot.
  * a server-rendered page from templates/base.html: HTTP status, 22px
    single-path Visor Hutch mark and "hutch" wordmark in .topbar .brand,
    topbar/brand close-up and full-page screenshots.
  * page errors, console errors, failed responses and non-localhost requests.

Writes only under this verification directory. Exit code 1 if any check fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import struct
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

VERIFY_DIR = Path(__file__).resolve().parent
ARTIFACTS = VERIFY_DIR / "artifacts"
RESULT_JSON = VERIFY_DIR / "capture-results.json"
SPA_SCREENSHOT = VERIFY_DIR / "spa-desktop.png"
SPA_BRAND_SCREENSHOT = VERIFY_DIR / "spa-brand-closeup.png"
SERVER_TOPBAR_SCREENSHOT = VERIFY_DIR / "server-page-topbar.png"
SERVER_BRAND_SCREENSHOT = VERIFY_DIR / "server-page-brand.png"
SERVER_FULL_SCREENSHOT = VERIFY_DIR / "server-page-full.png"

# Slice 7C follow-up 2: BRAND-GUIDELINES.md 3.2 / docs/brand-assets.md line 53
# lockup geometry (22px mark + 8px gap + 18px wordmark) and the content-hashed
# brand.css reference both dashboard heads must carry.
REPO_ROOT = Path(__file__).resolve().parents[6]
EXPECTED_BRAND_CSS_SHA8 = "581315bf"

# Visor Hutch Small tier, exactly the d in
# .pipeline/brand/2026-10/assets/production/svg/hutch-mark-small.svg and
# src/hutch/server/static/favicon.svg (32x32 grid).
SMALL_TIER_D = (
    "M 16.00 2.80 C 23.80 2.80 29.00 7.90 29.00 14.80 L 29.00 26.80 "
    "A 2.40 2.40 0 0 1 24.20 26.80 L 24.20 25.40 A 2.90 2.90 0 0 0 18.40 25.40 "
    "L 18.40 26.80 A 2.40 2.40 0 0 1 13.60 26.80 L 13.60 25.40 "
    "A 2.90 2.90 0 0 0 7.80 25.40 L 7.80 26.80 A 2.40 2.40 0 0 1 3.00 26.80 "
    "L 3.00 14.80 C 3.00 7.90 8.20 2.80 16.00 2.80 Z "
    "M 12.00 7.60 L 20.00 7.60 A 5.80 5.80 0 0 1 25.80 13.40 L 25.80 14.80 "
    "A 3.80 3.80 0 0 1 22.00 18.60 L 10.00 18.60 A 3.80 3.80 0 0 1 6.20 14.80 "
    "L 6.20 13.40 A 5.80 5.80 0 0 1 12.00 7.60 Z "
    "M 11.63 10.63 C 12.81 10.46 13.93 11.50 14.13 12.95 C 14.33 14.40 13.54 15.71 "
    "12.37 15.87 C 11.19 16.04 10.07 15.00 9.87 13.55 C 9.67 12.10 10.46 10.79 "
    "11.63 10.63 Z "
    "M 20.37 10.38 C 21.54 10.54 22.33 11.85 22.13 13.30 C 21.93 14.75 20.81 15.79 "
    "19.63 15.62 C 18.46 15.46 17.67 14.15 17.87 12.70 C 18.07 11.25 19.19 10.21 "
    "20.37 10.38 Z"
)

CHECKS: list[dict] = []
RESULT: dict = {}


def record(name: str, ok: bool, detail=None) -> bool:
    entry = {"check": name, "ok": bool(ok), "detail": detail}
    CHECKS.append(entry)
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        print("      " + json.dumps(detail, default=str)[:1800])
    return bool(ok)


def expect(name: str, condition, detail=None) -> bool:
    return record(name, bool(condition), detail)


def header_value(response, name: str) -> str:
    for key, value in response.headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG payload")
    return struct.unpack(">II", data[16:24])


def expected_content_type(href: str, content_type: str) -> bool:
    kind = content_type.split(";")[0].strip().lower()
    path = href.split("?")[0].lower()
    if path.endswith(".svg"):
        return kind == "image/svg+xml"
    if path.endswith(".png"):
        return kind == "image/png"
    if path.endswith(".ico"):
        return kind in {"image/x-icon", "image/vnd.microsoft.icon"}
    if path.endswith(".webmanifest"):
        return kind in {"application/manifest+json", "application/json"}
    return False


SPA_BRAND_JS = """async () => {
  const spec = '800 16px "Bricolage Grotesque"';
  const checkBefore = document.fonts.check(spec);
  let fontLoadError = null;
  try { await document.fonts.load(spec); } catch (error) { fontLoadError = String(error); }
  await document.fonts.ready;
  const wordmark = document.querySelector("#workspace .brand-wordmark");
  const style = getComputedStyle(wordmark);
  const brand = document.querySelector("#workspace .brand");
  const svgs = [...brand.querySelectorAll("svg")];
  const svg = svgs[0];
  const paths = svg ? [...svg.querySelectorAll("path")] : [];
  const markBox = svg ? svg.getBoundingClientRect() : null;
  const wordmarkBox = wordmark.getBoundingClientRect();
  return {
    font: {
      spec,
      checkAfter: document.fonts.check(spec),
      checkBefore,
      fontLoadError,
      fontFamily: style.fontFamily,
      fontWeight: style.fontWeight,
      fontSize: style.fontSize,
      letterSpacing: style.letterSpacing,
      loadedBricolageFaces: [...document.fonts]
        .filter(face => face.family.replace(/["']/g, "") === "Bricolage Grotesque")
        .map(face => ({family: face.family, weight: face.weight, status: face.status})),
      wordmarkText: wordmark.textContent.trim(),
    },
    mark: {
      svgCount: svgs.length,
      viewBox: svg ? svg.getAttribute("viewBox") : null,
      width: markBox ? markBox.width : null,
      height: markBox ? markBox.height : null,
      pathCount: paths.length,
      d: paths.map(path => path.getAttribute("d")),
      fill: paths.map(path => path.getAttribute("fill")),
      fillRule: paths.map(path => path.getAttribute("fill-rule")),
      circleCount: svg ? svg.querySelectorAll("circle").length : null,
      strokeElements: svg ? [...svg.querySelectorAll("[stroke]")].map(el => el.tagName.toLowerCase()) : null,
      brandGap: getComputedStyle(brand).gap,
      wordmarkText: wordmark.textContent.trim(),
      lockupGap: Math.round((wordmarkBox.left - markBox.right) * 100) / 100,
    },
  };
}"""

SERVER_BRAND_JS = """() => {
  const topbar = document.querySelector(".topbar");
  const brand = topbar ? topbar.querySelector(".brand") : null;
  const svgs = brand ? [...brand.querySelectorAll("svg")] : [];
  const svg = svgs[0];
  const paths = svg ? [...svg.querySelectorAll("path")] : [];
  const wordmark = brand ? brand.querySelector(".brand-wordmark") : null;
  const markBox = svg ? svg.getBoundingClientRect() : null;
  const wordmarkBox = wordmark ? wordmark.getBoundingClientRect() : null;
  return {
    topbarPresent: !!topbar,
    brandPresent: !!brand,
    svgCount: svgs.length,
    svgWidthAttr: svg ? svg.getAttribute("width") : null,
    svgHeightAttr: svg ? svg.getAttribute("height") : null,
    viewBox: svg ? svg.getAttribute("viewBox") : null,
    width: markBox ? markBox.width : null,
    height: markBox ? markBox.height : null,
    pathCount: paths.length,
    d: paths.map(path => path.getAttribute("d")),
    fill: paths.map(path => path.getAttribute("fill")),
    fillRule: paths.map(path => path.getAttribute("fill-rule")),
    circleCount: svg ? svg.querySelectorAll("circle").length : null,
    strokeElements: svg ? [...svg.querySelectorAll("[stroke]")].map(el => el.tagName.toLowerCase()) : null,
    wordmarkText: wordmark ? wordmark.textContent.trim() : null,
    wordmarkFontFamily: wordmark ? getComputedStyle(wordmark).fontFamily : null,
    wordmarkFontSize: wordmark ? getComputedStyle(wordmark).fontSize : null,
    wordmarkFontWeight: wordmark ? getComputedStyle(wordmark).fontWeight : null,
    wordmarkLetterSpacing: wordmark ? getComputedStyle(wordmark).letterSpacing : null,
    brandGap: brand ? getComputedStyle(brand).gap : null,
    lockupGap: markBox && wordmarkBox ? Math.round((wordmarkBox.left - markBox.right) * 100) / 100 : null,
    bricolageReady: document.fonts.check('800 16px "Bricolage Grotesque"'),
  };
}"""


def main() -> int:
    started = datetime.now(timezone.utc)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # Source-level lockup contract: one content-hashed brand.css referenced by both heads.
    brand_css_path = REPO_ROOT / "src/hutch/server/static/brand.css"
    brand_css_bytes = brand_css_path.read_bytes()
    brand_css_sha256 = hashlib.sha256(brand_css_bytes).hexdigest()
    brand_css_lines = brand_css_bytes.count(b"\n")
    expect(
        "source brand.css content-hash is 581315bf",
        brand_css_sha256.startswith(EXPECTED_BRAND_CSS_SHA8),
        {"path": str(brand_css_path), "sha256": brand_css_sha256, "lines": brand_css_lines},
    )
    index_html = (REPO_ROOT / "src/hutch/server/static/index.html").read_text(encoding="utf-8")
    base_html = (REPO_ROOT / "src/hutch/server/templates/base.html").read_text(encoding="utf-8")
    brand_ref = f"/static/brand.css?v={EXPECTED_BRAND_CSS_SHA8}"
    expect(
        "index.html and base.html reference brand.css?v=581315bf",
        brand_ref in index_html and brand_ref in base_html,
        {"ref": brand_ref, "index_html": brand_ref in index_html, "base_html": brand_ref in base_html},
    )

    state_root = Path(tempfile.mkdtemp(prefix="hutch-slice7c-state-"))
    os.environ["HUTCH_STATE_DIR"] = str(state_root / "state")
    os.environ["HUTCH_MAX_CONCURRENT"] = "2"
    os.environ["HUTCH_TESTING"] = "1"   # same process environment the pytest session uses
    os.environ["HUTCH_SANDBOX"] = "off"

    import uvicorn
    from importlib.metadata import version as package_version

    from hutch.models import Bot
    from hutch.server.app import create_app
    from playwright.sync_api import sync_playwright

    app = create_app()
    bot = app.state.store.create_bot(
        Bot(name="design-system-review", display_name="Design Partner", model="mock/demo", tools=[])
    )
    expect("fixture bot created", bot.name == "design-system-review", {"bot": bot.name})

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    expect("local Hutch preview started", server.started, {"state_root": str(state_root)})
    if not server.started:
        _finish(started, None, [], {})
        return 1
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    local_host = urlparse(base).netloc

    events = {
        "page_errors": [],
        "console_errors": [],
        "failed_responses": [],
        "request_failures": [],
        "external_requests": [],
        "woff2_requests": [],
    }
    environment = {
        "app_base_url": base,
        "state_root": str(state_root),
        "viewport": [1440, 960],
        "reduced_motion": "reduce",
        "brand_css_sha256": brand_css_sha256,
        "brand_css_lines": brand_css_lines,
    }
    asset_rows: list[dict] = []
    manifest_rows: list[dict] = []
    server_pages: list[dict] = []
    server_page = None
    spa_brand = {}
    server_brand = {}
    spa_woff2: list[str] = []
    server_woff2: list[str] = []

    try:
        with sync_playwright() as playwright:
            chromium = playwright.chromium
            browser = chromium.launch()
            environment["browser"] = f"Chromium {browser.version}"
            environment["chromium_executable"] = chromium.executable_path
            environment["playwright"] = package_version("playwright")
            environment["python"] = platform.python_version()
            environment["pytest"] = package_version("pytest")
            environment["uvicorn"] = uvicorn.__version__

            context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
            page = context.new_page()
            page.on("pageerror", lambda error: events["page_errors"].append(str(error)))
            page.on(
                "console",
                lambda message: events["console_errors"].append({"type": message.type, "text": message.text})
                if message.type == "error"
                else None,
            )
            page.on(
                "requestfailed",
                lambda request: events["request_failures"].append(
                    {"url": request.url, "failure": request.failure}
                ),
            )
            page.on(
                "response",
                lambda response: events["failed_responses"].append(
                    {"url": response.url, "status": response.status}
                )
                if response.status >= 400
                else None,
            )

            def note_external(request) -> None:
                parsed = urlparse(request.url)
                if parsed.scheme in {"http", "https"} and parsed.hostname not in {"127.0.0.1", "localhost"}:
                    events["external_requests"].append(request.url)

            page.on("request", note_external)
            page.on(
                "request",
                lambda request: events["woff2_requests"].append(request.url)
                if request.url.split("?")[0].endswith(".woff2")
                else None,
            )

            # ---------------- SPA "/" ----------------
            response = page.goto(base + "/", wait_until="domcontentloaded")
            expect(
                "SPA GET / returns HTTP 200",
                response is not None and response.status == 200,
                {"status": response.status if response else None},
            )
            page.locator("#chat-prompt").wait_for(timeout=20_000)
            page.evaluate("document.fonts.ready")
            expect("SPA chat shell rendered (#chat-prompt)", True, {"title": page.title()})

            links = page.evaluate(
                """() => [...document.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"], link[rel="manifest"]')]
                   .map(link => ({rel: link.getAttribute("rel"), href: link.getAttribute("href"),
                                  type: link.getAttribute("type"), sizes: link.getAttribute("sizes")}))"""
            )
            icon_links = [link for link in links if link["rel"] == "icon"]
            touch_links = [link for link in links if link["rel"] == "apple-touch-icon"]
            manifest_links = [link for link in links if link["rel"] == "manifest"]
            expect("SPA head declares three rel=icon links", len(icon_links) == 3, icon_links)
            expect("SPA head declares one apple-touch-icon link", len(touch_links) == 1, touch_links)
            expect("SPA head declares one rel=manifest link", len(manifest_links) == 1, manifest_links)
            expect("SPA head declares exactly five icon/manifest links", len(links) == 5, links)

            for link in links:
                url = base + link["href"]
                fetched = context.request.get(url)
                content_type = header_value(fetched, "content-type")
                body = fetched.body()
                row = {
                    "rel": link["rel"],
                    "href": link["href"],
                    "declared_type": link["type"],
                    "status": fetched.status,
                    "content_type": content_type,
                    "bytes": len(body),
                    "same_origin": urlparse(url).netloc == local_host,
                }
                asset_rows.append(row)
                expect(
                    f"asset {link['href']} -> HTTP 200 same-origin",
                    fetched.status == 200 and row["same_origin"],
                    row,
                )
                expect(
                    f"asset {link['href']} content-type {content_type}",
                    expected_content_type(link["href"], content_type),
                    {"content_type": content_type, "declared_type": link["type"]},
                )
                if link["rel"] == "icon" and link["href"].split("?")[0].endswith(".ico"):
                    expect("favicon.ico payload has ICO magic", body[:4] == b"\x00\x00\x01\x00", {"magic": body[:4].hex()})
                if link["href"].split("?")[0].endswith(".png"):
                    width, height = png_dimensions(body)
                    row["png_dimensions"] = f"{width}x{height}"
                    expect(
                        f"asset {link['href']} PNG payload decodes",
                        width > 0 and height > 0,
                        {"png_dimensions": row["png_dimensions"]},
                    )

            manifest_url = base + manifest_links[0]["href"]
            manifest_response = context.request.get(manifest_url)
            manifest = json.loads(manifest_response.body())
            expect("manifest JSON parses", isinstance(manifest, dict), {"keys": sorted(manifest)})
            expect("manifest declares six PNG icons", len(manifest.get("icons", [])) == 6, manifest.get("icons"))
            for icon in manifest["icons"]:
                icon_url = urljoin(manifest_url, icon["src"])
                icon_response = context.request.get(icon_url)
                icon_bytes = icon_response.body()
                width, height = png_dimensions(icon_bytes)
                declared = icon["sizes"]
                row = {
                    "src": icon["src"],
                    "resolved_url": icon_url,
                    "sizes": declared,
                    "purpose": icon.get("purpose"),
                    "status": icon_response.status,
                    "content_type": header_value(icon_response, "content-type"),
                    "png_dimensions": f"{width}x{height}",
                }
                manifest_rows.append(row)
                expect(
                    f"manifest icon {icon['src']} -> HTTP 200 PNG",
                    icon_response.status == 200
                    and header_value(icon_response, "content-type").split(";")[0].strip() == "image/png",
                    row,
                )
                expect(
                    f"manifest icon {icon['src']} dimensions match {declared}",
                    f"{width}x{height}" == declared,
                    row,
                )

            spa = page.evaluate(SPA_BRAND_JS)
            spa_brand = spa
            expect(
                'document.fonts.check(\'800 16px "Bricolage Grotesque"\') is true',
                spa["font"]["checkAfter"] is True,
                spa["font"],
            )
            expect(
                "SPA .brand-wordmark computed font-family includes Bricolage Grotesque",
                "Bricolage Grotesque" in spa["font"]["fontFamily"],
                {
                    "fontFamily": spa["font"]["fontFamily"],
                    "fontWeight": spa["font"]["fontWeight"],
                    "fontSize": spa["font"]["fontSize"],
                    "loadedBricolageFaces": spa["font"]["loadedBricolageFaces"],
                },
            )
            expect("SPA .brand-wordmark text is hutch", spa["mark"]["wordmarkText"] == "hutch", spa["mark"]["wordmarkText"])
            expect("#workspace .brand contains exactly one SVG", spa["mark"]["svgCount"] == 1, spa["mark"]["svgCount"])
            expect("Visor Hutch SPA mark is a single path", spa["mark"]["pathCount"] == 1, spa["mark"]["pathCount"])
            expect(
                "Visor Hutch SPA mark uses the Small-tier d",
                spa["mark"]["d"] == [SMALL_TIER_D],
                {"d_prefix": (spa["mark"]["d"] or [""])[0][:100], "expected_prefix": SMALL_TIER_D[:100]},
            )
            expect(
                "Visor Hutch SPA mark fill is var(--brand)",
                spa["mark"]["fill"] == ["var(--brand)"],
                spa["mark"]["fill"],
            )
            expect(
                "Visor Hutch SPA mark has no circle/stroke",
                spa["mark"]["circleCount"] == 0 and not spa["mark"]["strokeElements"],
                {"circles": spa["mark"]["circleCount"], "stroke_elements": spa["mark"]["strokeElements"]},
            )
            expect(
                "Visor Hutch SPA mark renders at 22x22 CSS px",
                spa["mark"]["width"] is not None
                and abs(spa["mark"]["width"] - 22) < 0.01
                and abs(spa["mark"]["height"] - 22) < 0.01,
                {"width": spa["mark"]["width"], "height": spa["mark"]["height"], "viewBox": spa["mark"]["viewBox"]},
            )
            expect(
                "SPA lockup gap is 8px",
                spa["mark"]["brandGap"] == "8px"
                and abs((spa["mark"]["lockupGap"] or 0) - 8) <= 0.6,
                {"computed_gap": spa["mark"]["brandGap"], "measured_gap": spa["mark"]["lockupGap"]},
            )
            expect(
                "SPA wordmark font-size is 18px",
                spa["font"]["fontSize"] == "18px",
                {"fontSize": spa["font"]["fontSize"], "fontWeight": spa["font"]["fontWeight"]},
            )
            expect(
                "SPA wordmark tracking is -0.54px (-0.03em at 18px)",
                abs(float((spa["font"]["letterSpacing"] or "0px").replace("px", "")) + 0.54) <= 0.02,
                {"letterSpacing": spa["font"]["letterSpacing"]},
            )
            spa_css_href = page.evaluate(
                """() => [...document.querySelectorAll('link[rel="stylesheet"]')]
                   .map(link => link.getAttribute("href"))
                   .find(href => href && href.includes("brand.css")) || null"""
            )
            spa_css_response = context.request.get(base + spa_css_href) if spa_css_href else None
            spa_css_sha256 = hashlib.sha256(spa_css_response.body()).hexdigest() if spa_css_response else ""
            expect(
                "SPA loads content-hashed brand.css v=581315bf and serves matching bytes",
                bool(spa_css_href)
                and EXPECTED_BRAND_CSS_SHA8 in (spa_css_href or "")
                and spa_css_response is not None
                and spa_css_response.status == 200
                and spa_css_sha256.startswith(EXPECTED_BRAND_CSS_SHA8),
                {"href": spa_css_href, "status": getattr(spa_css_response, "status", None), "sha256": spa_css_sha256},
            )

            page.screenshot(path=str(SPA_SCREENSHOT), animations="disabled")
            page.locator("#workspace .brand").screenshot(
                path=str(SPA_BRAND_SCREENSHOT), animations="disabled"
            )
            spa_woff2 = list(events["woff2_requests"])
            expect(
                "SPA desktop and brand screenshots captured",
                SPA_SCREENSHOT.exists() and SPA_BRAND_SCREENSHOT.exists(),
                [str(SPA_SCREENSHOT), str(SPA_BRAND_SCREENSHOT)],
            )

            # ---------------- server-rendered page from templates/base.html ----------------
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            for candidate in ("/models", "/usage", "/login"):
                fetched_page = page.goto(base + candidate, wait_until="domcontentloaded")
                status = fetched_page.status if fetched_page else None
                final_path = urlparse(page.url).path
                server_pages.append(
                    {"requested": candidate, "final_url": page.url, "final_path": final_path, "status": status}
                )
                if status == 200 and final_path == candidate:
                    server_page = candidate
                    break
            expect(
                "server-rendered page from templates/base.html returns HTTP 200",
                server_page is not None,
                server_pages,
            )
            if server_page is not None:
                page.locator(".topbar").wait_for(timeout=10_000)
                server_brand = page.evaluate(SERVER_BRAND_JS)
                topbar = page.locator(".topbar")
                topbar.screenshot(path=str(SERVER_TOPBAR_SCREENSHOT), animations="disabled")
                page.locator(".topbar .brand").screenshot(
                    path=str(SERVER_BRAND_SCREENSHOT), animations="disabled"
                )
                page.screenshot(path=str(SERVER_FULL_SCREENSHOT), full_page=True, animations="disabled")
                expect(
                    "server page .topbar .brand contains one 22px single-path Small-tier mark",
                    server_brand["svgCount"] == 1
                    and server_brand["pathCount"] == 1
                    and server_brand["d"] == [SMALL_TIER_D]
                    and server_brand["svgWidthAttr"] == "22"
                    and server_brand["svgHeightAttr"] == "22"
                    and abs((server_brand["width"] or 0) - 22) < 0.01,
                    server_brand,
                )
                expect(
                    "server page mark has no circle/stroke",
                    server_brand["circleCount"] == 0 and not server_brand["strokeElements"],
                    {"circles": server_brand["circleCount"], "stroke_elements": server_brand["strokeElements"]},
                )
                expect(
                    "server page .brand-wordmark text is hutch",
                    (server_brand["wordmarkText"] or "") == "hutch",
                    server_brand["wordmarkText"],
                )
                expect(
                    "server page .brand-wordmark computed font-family includes Bricolage Grotesque",
                    "Bricolage Grotesque" in (server_brand["wordmarkFontFamily"] or ""),
                    {
                        "fontFamily": server_brand["wordmarkFontFamily"],
                        "fontSize": server_brand["wordmarkFontSize"],
                        "fontWeight": server_brand["wordmarkFontWeight"],
                    },
                )
                server_woff2 = [url for url in events["woff2_requests"] if url not in spa_woff2]
                expect(
                    "server page lockup gap is 8px",
                    server_brand["brandGap"] == "8px"
                    and abs((server_brand["lockupGap"] or 0) - 8) <= 0.6,
                    {"computed_gap": server_brand["brandGap"], "measured_gap": server_brand["lockupGap"]},
                )
                expect(
                    "server page wordmark font-size is 18px",
                    server_brand["wordmarkFontSize"] == "18px",
                    {"fontSize": server_brand["wordmarkFontSize"], "fontWeight": server_brand["wordmarkFontWeight"]},
                )
                expect(
                    "server page wordmark tracking is -0.54px (-0.03em at 18px)",
                    abs(float((server_brand["wordmarkLetterSpacing"] or "0px").replace("px", "")) + 0.54) <= 0.02,
                    {"letterSpacing": server_brand["wordmarkLetterSpacing"]},
                )
                server_css_href = page.evaluate(
                    """() => [...document.querySelectorAll('link[rel="stylesheet"]')]
                       .map(link => link.getAttribute("href"))
                       .find(href => href && href.includes("brand.css")) || null"""
                )
                server_css_response = context.request.get(base + server_css_href) if server_css_href else None
                server_css_sha256 = hashlib.sha256(server_css_response.body()).hexdigest() if server_css_response else ""
                expect(
                    "server page loads content-hashed brand.css v=581315bf and serves matching bytes",
                    bool(server_css_href)
                    and EXPECTED_BRAND_CSS_SHA8 in (server_css_href or "")
                    and server_css_response is not None
                    and server_css_response.status == 200
                    and server_css_sha256.startswith(EXPECTED_BRAND_CSS_SHA8),
                    {
                        "href": server_css_href,
                        "status": getattr(server_css_response, "status", None),
                        "sha256": server_css_sha256,
                    },
                )
                expect(
                    "server topbar screenshots captured",
                    SERVER_TOPBAR_SCREENSHOT.exists() and SERVER_FULL_SCREENSHOT.exists(),
                    [str(SERVER_TOPBAR_SCREENSHOT), str(SERVER_FULL_SCREENSHOT)],
                )
            try:
                context.tracing.stop(path=str(ARTIFACTS / "capture-trace.zip"))
            except Exception:
                pass

            expect("no page errors", not events["page_errors"], events["page_errors"])
            expect("no console errors", not events["console_errors"], events["console_errors"])
            expect(
                "no failed responses",
                not events["failed_responses"],
                events["failed_responses"],
            )
            expect(
                "no non-localhost requests",
                not events["external_requests"],
                events["external_requests"],
            )
            context.close()
            browser.close()
    except Exception as error:  # noqa: BLE001 - report the first hard failure as evidence
        record("capture completed without an uncaught exception", False, repr(error))
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            record("local Hutch preview stopped", False, "uvicorn thread still alive")
        _finish(
            started,
            environment,
            asset_rows,
            {
                "manifest_rows": manifest_rows,
                "server_pages": server_pages,
                "server_page_selected": server_page,
                "spa_brand": spa_brand,
                "server_brand": server_brand,
                "network_events": events,
                "font_requests": {"spa_woff2": spa_woff2, "server_woff2": server_woff2},
                "brand_css_contract": {
                    "path": str(brand_css_path),
                    "sha256": brand_css_sha256,
                    "sha8": EXPECTED_BRAND_CSS_SHA8,
                    "lines": brand_css_lines,
                    "refs": {"index_html": brand_ref in index_html, "base_html": brand_ref in base_html},
                },
                "artifacts": {
                    "root": str(ARTIFACTS),
                    "spa_desktop": str(SPA_SCREENSHOT),
                    "spa_brand_closeup": str(SPA_BRAND_SCREENSHOT),
                    "server_page_topbar": str(SERVER_TOPBAR_SCREENSHOT),
                    "server_page_brand": str(SERVER_BRAND_SCREENSHOT),
                    "server_page_full": str(SERVER_FULL_SCREENSHOT),
                },
            },
        )
    return 0 if all(check["ok"] for check in CHECKS) else 1


def _finish(started, environment, asset_rows, extra) -> None:
    finished = datetime.now(timezone.utc)
    passed = sum(1 for check in CHECKS if check["ok"])
    failed = sum(1 for check in CHECKS if not check["ok"])
    payload = {
        "slice": "7C",
        "verdict": "PASS" if CHECKS and failed == 0 else "FAIL",
        "checks_passed": passed,
        "checks_failed": failed,
        "captured_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "environment": environment,
        "checks": CHECKS,
        "passed": passed,
        "failed": failed,
        "asset_http_table": asset_rows,
    }
    payload.update(extra)
    RESULT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print()
    print(f"checks passed: {payload['passed']}, failed: {payload['failed']}")
    print(f"results: {RESULT_JSON}")
    failed = [check for check in CHECKS if not check["ok"]]
    for check in failed:
        print(f"FAILED CHECK: {check['check']}")


if __name__ == "__main__":
    raise SystemExit(main())
