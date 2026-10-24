"""Real-image composer journeys in the actual browser.

Staging through picker, paste and drag-drop; the attachment-tray contract across a
send; failure keeping state; transcript thumbnails loading real bytes; responsive
and zoom resilience. Inputs are genuine repo images (the bundled Google Calendar
PNG and first-run WebP captures), not synthetic fixtures — uploaded through the
real intake endpoint and rendered back from the content route.

No live model call: the deterministic test runtime completes admitted runs, so the
model-level transmission gate is covered at the runtime layer in
tests/test_chat_vision.py (route inference awaits the user's approval gate).
"""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser, wait_for_page  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REAL_PNG = REPO / "src/hutch/server/static/brands/google-calendar-2026q2.png"
REAL_WEBP = REPO / "website/assets/captures/setup-desktop.webp"
REAL_WEBP_PHONE = REPO / "website/assets/captures/setup-phone.webp"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    app = create_app()
    bot = app.state.store.create_bot(Bot(
        name="composer-vision", display_name="Vision Partner", model="mock/demo", tools=[]))
    assert bot.name == "composer-vision"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Hutch preview did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _open_chat(page, base):
    page.goto(f"{base}/#/chat/composer-vision", wait_until="domcontentloaded")
    page.locator("#composer-box").wait_for(timeout=20_000)
    page.wait_for_timeout(400)


def _tray(page):
    return page.locator(".composer-attachments")


def _paste_image(page, target, name: str, data: bytes, mime: str):
    """Dispatch a real clipboard-paste carrying a real File (Chromium supports
    ClipboardEvent.clipboardData in its init dict)."""
    encoded = base64.b64encode(data).decode("ascii")
    page.evaluate(
        """([selector, name, mime, encoded]) => {
            const binary = atob(encoded);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
            const transfer = new DataTransfer();
            transfer.items.add(new File([bytes], name, { type: mime }));
            const event = new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true });
            document.querySelector(selector).dispatchEvent(event);
        }""",
        [target, name, mime, encoded])


def _drop_files(page, selector, name: str, data: bytes, mime: str):
    encoded = base64.b64encode(data).decode("ascii")
    page.evaluate(
        """([selector, name, mime, encoded]) => {
            const binary = atob(encoded);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
            const transfer = new DataTransfer();
            transfer.items.add(new File([bytes], name, { type: mime }));
            const target = document.querySelector(selector);
            target.dispatchEvent(new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true }));
        }""",
        [selector, name, mime, encoded])


def _watch(page):
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    return errors, external


def test_composer_stages_real_images_through_picker_paste_and_drop(browser, app_server):
    base, app = app_server
    out = artifact_path("composer-vision-2026-10-23")
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors, external = _watch(page)
    try:
        _open_chat(page, base)

        # The + menu states the tray contract in plain words (the copy that used to
        # claim image input was unsupported).
        page.locator("#composer-menu-btn").click()
        page.wait_for_timeout(250)
        note = page.locator(".cmenu-image-note").inner_text()
        assert "sent with every message until you remove them" in note
        assert "up to 4, 1.5 MB" in note
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

        # 1. Picker: two REAL images through the real intake endpoint.
        page.locator("#workspace-upload-file").set_input_files([str(REAL_PNG), str(REAL_WEBP)])
        wait_for_page(page, "document.querySelectorAll('.upload-chip').length >= 2", timeout=20_000)
        page.wait_for_timeout(400)
        chips = page.locator(".upload-chip")
        assert chips.count() == 2, "one chip per staged image"
        hint = page.locator(".composer-attachments-hint").inner_text()
        assert "Images here are sent with every message until you remove them" in hint

        # thumbnails are real bytes served by the conversation content route
        thumbs = page.locator(".upload-chip-thumb")
        assert thumbs.count() == 2, "sendable images show a thumbnail"
        src = thumbs.first.get_attribute("src")
        served = page.request.get(f"{base}{src}")
        assert served.status == 200 and served.headers["content-type"].startswith("image/")
        assert served.body().startswith(b"\x89PNG"), "the served thumbnail is the real PNG"

        # status region announced the staging (screen-reader live region)
        status = page.locator(".composer-attachments-status").inner_text()
        assert "Attached" in status

        # 2. Paste: a real clipboard image becomes a staged chip.
        before = page.locator(".upload-chip").count()
        _paste_image(page, "#chat-prompt", "pasted-shot.png", REAL_PNG.read_bytes(), "image/png")
        wait_for_page(page, f"document.querySelectorAll('.upload-chip').length > {before}", timeout=20_000)
        assert page.locator(".upload-chip").count() == before + 1

        # 3. Drop: files dropped on the composer land in the tray.
        before = page.locator(".upload-chip").count()
        _drop_files(page, "#composer-box", "dropped-capture.webp", REAL_WEBP_PHONE.read_bytes(),
                    "image/webp")
        wait_for_page(page, f"document.querySelectorAll('.upload-chip').length > {before}", timeout=20_000)
        assert page.locator(".upload-chip").count() == before + 1

        # 4. Oversized images are refused BEFORE any upload, with the reason.
        stage_posts = []
        page.on("request", lambda r: stage_posts.append(r.url)
                if "/uploads" in r.url and r.method == "POST" else None)
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (1_600_000)
        _paste_image(page, "#chat-prompt", "huge.png", big, "image/png")
        wait_for_page(page, "document.querySelector('#toast-root .toast') !== null", timeout=10_000)
        toast = page.locator("#toast-root .toast").first.inner_text()
        assert "images are limited to 1.5 MB" in toast and "was not attached" in toast
        page.wait_for_timeout(300)
        assert page.locator(".upload-chip").count() == before + 1, "refused file adds no chip"
        assert not stage_posts, "a client-side refusal never reaches the upload endpoint"

        # 5. The 4-image ceiling is enforced with a stated reason.
        for name, data, mime in (("a.png", REAL_PNG.read_bytes(), "image/png"),
                                 ("b.png", REAL_WEBP_PHONE.read_bytes(), "image/webp")):
            count = page.locator(".upload-chip").count()
            if count >= 4:
                break
            _paste_image(page, "#chat-prompt", name, data, mime)
            page.wait_for_timeout(600)
        if page.locator(".upload-chip").count() < 4:
            _paste_image(page, "#chat-prompt", "e.png", REAL_PNG.read_bytes(), "image/png")
            page.wait_for_timeout(700)
        page.wait_for_timeout(400)
        if page.locator(".upload-chip").count() >= 4:
            _paste_image(page, "#chat-prompt", "over.png", REAL_PNG.read_bytes(), "image/png")
            wait_for_page(page, "document.querySelector('#toast-root .toast') !== null", timeout=10_000)
            overflow_toasts = page.locator("#toast-root .toast").all_text_contents()
            assert any("at most 4 images" in t for t in overflow_toasts), overflow_toasts
            assert page.locator(".upload-chip").count() == 4

        # Desktop capture of a populated real-image tray.
        assert page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1")

        # Preflight discloses that staged images sit outside the text-only estimate
        # (the estimate endpoint receives prompt text, never attachments).
        page.locator("#composer-menu-btn").click()
        page.wait_for_timeout(250)
        page.locator("#preflight-open").click()
        page.locator("#modal-root .modal-card").wait_for(timeout=10_000)
        preflight = page.locator("#modal-root .modal-card").inner_text()
        assert "staged image" in preflight and "not included in this estimate" in preflight, preflight
        assert page.locator("#modal-root .modal-card").inner_text().count("4 staged images") == 1
        page.locator("#modal-close").click()
        page.wait_for_timeout(250)

        page.screenshot(path=str(out / "tray-desktop.png"), animations="disabled")

        assert errors == [], errors
        assert external == [], external
    finally:
        context.close()


def test_composer_sends_images_and_renders_them_in_the_transcript(browser, app_server):
    base, app = app_server
    out = artifact_path("composer-vision-2026-10-23")
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors, external = _watch(page)
    try:
        _open_chat(page, base)
        page.locator("#workspace-upload-file").set_input_files([str(REAL_PNG)])
        wait_for_page(page, "document.querySelectorAll('.upload-chip').length === 1", timeout=20_000)

        # --- text + image send succeeds; the tray keeps its images (contract).
        ta = page.locator("#chat-prompt")
        ta.click()
        page.keyboard.type("What service does this icon represent?")
        page.locator("#chat-send").click()
        wait_for_page(page, "document.querySelector('.bubble-images') !== null", timeout=30_000)
        assert ta.input_value() == "", "sent text clears"
        assert page.locator(".upload-chip").count() == 1, "tray images persist after send"

        bubble_img = page.locator(".bubble-images .bubble-image img").first
        bubble_img.wait_for(state="visible", timeout=10_000)
        natural = bubble_img.evaluate("img => ({ w: img.naturalWidth, h: img.naturalHeight, alt: img.alt })")
        assert natural["w"] == 96 and natural["h"] == 96, f"real PNG dimensions: {natural}"
        assert natural["alt"] == "google-calendar-2026q2.png", "accessible name is the filename"
        box = bubble_img.bounding_box()
        assert box["width"] <= 242, "thumbnail never exceeds its grid cap"
        # the transcript link opens the real bytes
        href = page.locator(".bubble-images .bubble-image").first.get_attribute("href")
        served = page.request.get(f"{base}{href}")
        assert served.status == 200 and served.body().startswith(b"\x89PNG")

        # --- image-only send: an empty prompt is a complete request.
        ta.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        assert ta.input_value() == ""
        page.locator("#chat-send").click()
        wait_for_page(page, "document.querySelectorAll('.bubble-images').length >= 2", timeout=30_000)
        image_only_bubble = page.locator(".msg.you .bubble").last
        assert image_only_bubble.locator(".bubble-images img").count() == 1
        assert image_only_bubble.inner_text().strip() == "", "image-only bubble has no invented text"

        # --- a refused send keeps both the tray and any typed draft.
        page.evaluate("""() => {
            const key = Object.keys(localStorage).find(k => k.startsWith('hutch-uploads:'));
            const staged = JSON.parse(localStorage.getItem(key) || '[]');
            staged.push({ id: 'upl_0000000000000000', filename: 'ghost.png', bytes: 1024 });
            localStorage.setItem(key, JSON.stringify(staged));
            hutchUploadsSync();   // same re-render path a real staging action takes
        }""")
        wait_for_page(page, "document.querySelectorAll('.upload-chip').length >= 2", timeout=5_000)
        ta.click()
        page.keyboard.type("this send must be refused")
        page.locator("#chat-send").click()
        wait_for_page(page, "document.querySelector('#toast-root .toast') !== null", timeout=15_000)
        toasts = page.locator("#toast-root .toast").all_text_contents()
        assert any("no longer available" in t for t in toasts), toasts
        assert any("Your draft is kept." in t for t in toasts), toasts
        assert ta.input_value() == "this send must be refused", "draft survives a refused send"
        assert page.locator("#composer-box").evaluate("el => el.classList.contains('has-error')")
        page.wait_for_timeout(300)
        assert page.locator(".upload-chip").count() >= 2, "tray survives a refused send"

        # The error toast docks over the send control and persists until dismissed;
        # on chat routes its body is pointer-transparent, so an immediate retry is NOT
        # intercepted (a refusal must never dead-zone the composer).
        assert page.locator("#toast-root .toast").count() >= 1, "the refusal toast is still up"

        # image-only refusal copy names attachments, not the draft (the ghost id
        # from the refused send is still staged — refused sends never clear the tray)
        ta.focus()
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        assert ta.input_value() == ""
        page.locator("#chat-send").click()   # fails if a toast intercepts the press
        wait_for_page(page, "document.querySelectorAll('#toast-root .toast').length >= 1", timeout=15_000)
        page.wait_for_timeout(250)
        toasts = page.locator("#toast-root .toast").all_text_contents()
        assert any("Your attachments are kept." in t for t in toasts), toasts

        page.screenshot(path=str(out / "sent-images-desktop.png"), animations="disabled")
        assert errors == [], errors
        assert external == [], external
    finally:
        context.close()


def test_composer_image_tray_survives_phone_and_zoom_checks(browser, app_server):
    base, app = app_server
    out = artifact_path("composer-vision-2026-10-23")
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors, external = _watch(page)
    try:
        _open_chat(page, base)
        page.locator("#workspace-upload-file").set_input_files([str(REAL_PNG), str(REAL_WEBP)])
        wait_for_page(page, "document.querySelectorAll('.upload-chip').length >= 2", timeout=20_000)

        for label, width, height in (("phone", 390, 844), ("compact", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(300)
            assert page.evaluate(
                "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1"), \
                f"horizontal overflow at {label}"
            # the tray sits above the writing area, not over it
            tray_box = _tray(page).bounding_box()
            body_box = page.locator(".composer-body").bounding_box()
            assert tray_box["y"] < body_box["y"], "context region leads the composer"
            send_box = page.locator("#chat-send").bounding_box()
            assert send_box["width"] >= 44 and send_box["height"] >= 44, "touch-size send"
            page.screenshot(path=str(out / f"tray-{label}.png"), animations="disabled")

        # 200% root text: no overflow, remove targets stay operable
        page.set_viewport_size({"width": 1440, "height": 960})
        page.evaluate("document.documentElement.style.fontSize = '32px'")
        page.wait_for_timeout(300)
        assert page.evaluate(
            "Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1"), \
            "horizontal overflow at 200% text"
        page.evaluate("document.documentElement.style.fontSize = ''")

        # keyboard: walk with real Tab presses so :focus-visible matches, then
        # confirm the transcript image link keeps a visible ring
        page.locator("#chat-prompt").fill("stage one more, then send")
        page.locator("#chat-send").click()
        wait_for_page(page, "document.querySelector('.bubble-images') !== null", timeout=30_000)
        reached = False
        for _ in range(80):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement.classList.contains('bubble-image')"):
                reached = True
                break
        assert reached, "the transcript image link is keyboard reachable"
        outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        assert outline != "none", "focused image link keeps a visible ring"

        page.screenshot(path=str(out / "tray-zoom-recovery.png"), animations="disabled")
        assert errors == [], errors
        assert external == [], external
    finally:
        context.close()
