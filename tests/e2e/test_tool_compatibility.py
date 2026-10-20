"""Real-browser checks for the Bot-settings Tool Compatibility section (Route A).

Skipped automatically when Playwright or a browser build is unavailable. Captures
screenshots + a trace under docs/realignment/artifacts/tool-compatibility/ and
writes the validation summary next to them.
"""

from __future__ import annotations

import json
import platform
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import ApprovalMode, Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        instance = None
        errors = []
        for engine in (p.chromium, p.firefox):
            try:
                instance = engine.launch()
                break
            except Exception as exc:  # pragma: no cover - environment-dependent
                errors.append(f"{engine.name}: {exc}")
        if instance is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield instance
        instance.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def wait_for(fn, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out")


def open_assistant_customization(page):
    details = page.locator("#assistant-more-settings")
    details.wait_for(state="attached")
    if not details.evaluate("element => element.open"):
        details.locator(":scope > summary").click()
    assert details.evaluate("element => element.open")


def test_tool_compatibility_reports_evidence_and_saves_the_choice(browser, live):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="tool-compat-bot", display_name="Tool compat bot", model="ollama/llama3.2",
                         tools=["files"], approval_mode=ApprovalMode.auto))
    store.create_bot(Bot(name="lmstudio-bot", display_name="LM Studio bot", model="lmstudio/qwen2.5-7b",
                         tools=["files"], approval_mode=ApprovalMode.auto))
    artifact_dir = artifact_path("tool-compatibility")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    captures: list[dict] = []
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
            page.goto(f"{base}/#/bot/tool-compat-bot")
            open_assistant_customization(page)
            select = page.locator('#form-model select[name="tool_protocol"]')
            select.wait_for()
            assert select.input_value() == "auto"
            help_text = page.locator("#tool-protocol-help")
            assert "Automatic keeps this route’s native tool protocol" in help_text.inner_text()
            assert "Constrained and prompt modes are explicit choices" in help_text.inner_text()

            page.locator("#tool-compat > summary").click()
            result = page.locator("#tool-compat-result")
            wait_for(lambda: "Route" in result.inner_text())
            assert "Argument validator" in result.inner_text()
            assert "observed in a governed run" not in help_text.inner_text()
            assert "documented" in help_text.inner_text()
            assert "No governed run has recorded a call on this exact route yet" in result.inner_text()
            assert "advertised is not verified" in result.inner_text()
            assert select.locator('option[value="constrained"]').evaluate("o => !o.disabled")
            assert select.locator('option[value="prompt"]').evaluate("o => !o.disabled")
            assert "Available — the backend exposes a documented schema-constrained generation control" \
                in result.inner_text()

            select.select_option("constrained")
            with page.expect_response(lambda response: response.url.endswith("/api/bots/tool-compat-bot")
                                      and response.request.method == "PATCH") as saved:
                page.locator('#form-model button[type="submit"]').click()
            assert saved.value.ok
            assert "Constrained JSON" in result.inner_text() or select.input_value() == "constrained"

            page.reload()
            open_assistant_customization(page)
            wait_for(lambda: page.locator('#form-model select[name="tool_protocol"]').count() == 1)
            assert page.locator('#form-model select[name="tool_protocol"]').input_value() == "constrained"
            page.locator("#tool-compat > summary").click()
            result = page.locator("#tool-compat-result")
            wait_for(lambda: "Route" in result.inner_text())
            assert "Constrained JSON" in result.inner_text()
            page.locator("#tool-compat").scroll_into_view_if_needed()
            page.wait_for_timeout(120)
            page.screenshot(path=str(artifact_dir / "compat-desktop-evidence.png"), animations="disabled")

            # A model change invalidates the loaded evidence instead of showing stale states.
            page.locator('#form-model input[name="model"]').fill("ollama/other:3b")
            assert "Route changed" in result.inner_text()
            assert page.locator('#form-model select[name="tool_protocol"] option[value="constrained"]').evaluate("o => !o.disabled")

            sizes = {"desktop": (1440, 1000), "tablet": (768, 1024), "phone": (390, 844), "compact-phone": (360, 720)}
            for size, (width, height) in sizes.items():
                page.set_viewport_size({"width": width, "height": height})
                page.locator("#tool-compat").scroll_into_view_if_needed()
                page.wait_for_timeout(120)
                page.screenshot(path=str(artifact_dir / f"compat-{size}.png"), full_page=True, animations="disabled")
                metrics = page.evaluate("""() => ({
                    viewport: [innerWidth, innerHeight],
                    document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                    selectVisible: Boolean(document.querySelector('#tool-protocol-select')?.offsetParent),
                    resultVisible: Boolean(document.querySelector('#tool-compat-result')?.offsetParent)
                })""")
                assert metrics["document"][0] - metrics["viewport"][0] <= 1, (size, metrics)
                assert metrics["selectVisible"] and metrics["resultVisible"], (size, metrics)
                captures.append({"size": size, **metrics})

            # An unavailable mode is disabled in the UI and blocked before saving.
            page.set_viewport_size({"width": 900, "height": 1024})
            page.goto(f"{base}/#/bots")
            page.goto(f"{base}/#/bot/lmstudio-bot")
            open_assistant_customization(page)
            blocked_select = page.locator('#form-model select[name="tool_protocol"]')
            blocked_select.wait_for()
            page.locator("#tool-compat > summary").click()
            blocked_result = page.locator("#tool-compat-result")
            wait_for(lambda: "Route" in blocked_result.inner_text())
            blocked_option = blocked_select.locator('option[value="constrained"]')
            assert blocked_option.evaluate("o => o.disabled")
            assert "unavailable here" in blocked_option.inner_text()
            assert "Unavailable —" in blocked_result.inner_text()
            # Simulate a stale client (the option was enabled when the page loaded): force
            # the choice past the disabled option and confirm the guard still blocks it.
            patch_requests: list[str] = []
            page.on("request", lambda req: patch_requests.append(req.url)
                    if (req.method == "PATCH" and req.url.endswith("/api/bots/lmstudio-bot")) else None)
            page.evaluate("""() => {
                const select = document.querySelector('#tool-protocol-select');
                select.querySelector('option[value="constrained"]').disabled = false;
                select.value = 'constrained';
            }""")
            assert page.locator("#tool-protocol-select").input_value() == "constrained"
            page.locator('#form-model button[type="submit"]').click()
            wait_for(lambda: "cannot generate tool calls" in page.locator(".toast.error").first.inner_text())
            assert patch_requests == [], "an unavailable mode must be blocked before the PATCH"
            fetched = page.request.get(f"{base}/api/bots/lmstudio-bot").json()
            assert fetched["tool_protocol"] == "auto", "an unavailable mode must not be saved"
            page.screenshot(path=str(artifact_dir / "compat-blocked-tablet.png"), animations="disabled")
    finally:
        try:
            context.tracing.stop(path=str(artifact_dir / "compat-trace.zip"))
        except Exception:
            pass
        assert page_errors == [], page_errors
        context.close()

    (artifact_dir / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_tool_compatibility.py::test_tool_compatibility_reports_evidence_and_saves_the_choice",
        "command": "PYTHONPATH=src pytest -q " + __file__,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "hutch_version": package_version("hutch"),
        "browser": browser.version,
        "viewports": [name for name in captures],
        "states": ["auto-selected", "evidence-loaded", "constrained-saved", "route-changed", "blocked-unavailable-mode"],
        "inspected_screenshots": ["compat-desktop-evidence.png"] + [f"compat-{c['size']}.png" for c in captures] + ["compat-blocked-tablet.png"],
        "captures": captures,
        "page_errors": page_errors,
    }, indent=2) + "\n", encoding="utf-8")
