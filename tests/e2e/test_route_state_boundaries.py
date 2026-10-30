"""Route state boundaries for the five dashboard routes (completion-plan Slice C).

Against a real local uvicorn app with an empty store: first-run empty states and
calls to action (no horizontal overflow at 1440x900, 900x900, 360x800), the SPA
route error boundary with retry, the /models flash error banner, and the paired
phone permission boundary. Authored against HEAD 33b55776 and run from the clean
export .worktrees/completion-c-scratch/head; evidence and residual gaps go under
docs/realignment/artifacts/completion-2026-10-29/states/.
"""

from __future__ import annotations

import hashlib, json, os, platform, secrets, subprocess, sys, threading, time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from types import SimpleNamespace

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.modelview import ModelsView  # noqa: E402
from hutch.models import Bot, Event, EventType, Run, RunStatus  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path, repository_path  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

ARTIFACTS = "completion-2026-10-29/states"
VIEWPORTS = ((1440, 900), (900, 900), (360, 800))
OWNER_ROUTES = ("/bots", "/usage", "/models", "/approvals", "/connections")
EMPTY_ROUTES = (("bots", "/bots", 302, "/#/bots"), ("usage", "/usage", 200, None),
                ("models", "/models", 200, None), ("approvals", "/approvals", 302, "/#/approvals"),
                ("connections", "/connections", 302, "/#/connections"))
SPA_ERRORS = (("bots", "/bots", "**/api/bots", "bots unavailable", "No assistants yet — create one."),
              ("approvals", "/approvals", "**/api/bots", "bots unavailable", "What would you like help with?"),
              ("connections", "/connections", "**/api/connections", "connections unavailable", "Connect your work"))
SOURCE_FILES = ("src/hutch/server/pages.py", "src/hutch/server/pages_usage.py",
                "src/hutch/server/pages_models.py", "src/hutch/server/templates/usage.html",
                "src/hutch/server/templates/models.html", "src/hutch/server/static/app.js",
                "tests/e2e/test_route_state_boundaries.py")
RESIDUAL_GAPS = [
 {"id": "usage-no-error-state", "files": ["src/hutch/server/pages_usage.py:20-66", "src/hutch/server/templates/usage.html:7-77"], "summary": "/usage has no server-rendered error banner or retry action: usage.html renders only empty/list states and pages_usage.py sets no error context, so failures fall through to the generic error page."},
 {"id": "usage-empty-no-cta", "files": ["src/hutch/server/templates/usage.html:51"], "summary": "The /usage empty state ('No model calls in the last 30 days.') has no first-run call to action for connecting a provider or starting work."},
 {"id": "models-empty-no-cta", "files": ["src/hutch/server/templates/models.html:25", "src/hutch/server/templates/models.html:52-54"], "summary": "The /models empty state ('No runtimes detected.' plus 'Start Ollama ...') is hint text only; no button-level call to action for the missing runtime."},
 {"id": "approvals-empty-no-cta", "files": ["src/hutch/server/static/app.js:7946-7953", "src/hutch/server/static/app.js:8083-8133"], "summary": "The approvals empty state ('No pending approvals.') has no call to action; data-API errors are handled inline by the needs-you drawer with its own Retry button rather than by the route error boundary."},
 {"id": "approvals-retry-loses-route", "files": ["src/hutch/server/static/app.js:7888-7897", "src/hutch/server/static/app.js:2287-2313"], "summary": "renderApprovals replaces the hash with #/chat before loading; when the shell then fails, the route error boundary's Try again re-runs the #/chat route, so retry recovers the chat studio rather than the approvals drawer."},
 {"id": "bots-empty-route-collapses", "files": ["src/hutch/server/static/app.js:7291-7294", "src/hutch/server/static/app.js:7342-7347", "src/hutch/server/static/app.js:2388-2390"], "summary": "GET /bots redirects to #/bots, but renderBots redirects to #/chat whenever fewer than ten assistants exist, so the fleet empty state and its 'Create your first assistant' button are unreachable on an empty store; the visible copy is the roster's 'No assistants yet — create one.'"},
 {"id": "connections-empty-hidden-until-detail", "files": ["src/hutch/server/static/connection-browser.js:31-32", "src/hutch/server/static/app.js:10192-10197"], "summary": "The 'No connections configured.' state and its 'Connect a provider' button live behind the AI model providers detail: connection-browser.js hides #connection-management in the directory view, and the directory always renders the full connection catalog."},
 {"id": "form-post-origin-null", "files": ["src/hutch/server/security.py:314-318", "src/hutch/server/security.py:374-377", "src/hutch/server/security.py:428-435", "src/hutch/server/templates/models.html:112-124", "src/hutch/server/templates/base.html:34-38"], "summary": "Plain server-rendered form POSTs are refused in Chromium: Referrer-Policy no-referrer makes Chromium submit with 'Origin: null', and SecurityMiddleware._same_origin rejects null even though Sec-Fetch-Site is same-origin. The /models flash error is exercised through a browser-context request carrying the page CSRF token, and the refused direct submit is recorded."},
]
DEVIATIONS = [
 {"id": "deterministic-models-view", "summary": "The /models empty view is forced with a stub ModelsView (empty runtimes/rows/notes) via monkeypatch of hutch.server.pages_models.build_models_view, because host hardware and runtime probes inject non-deterministic notes and runtime rows."},
 {"id": "flash-error-via-context-request", "summary": "The /models flash error is produced by a POST through the page's browser-context request with the page CSRF token, because a direct Chromium form submit is refused at HEAD (see residual gap form-post-origin-null)."},
 {"id": "approvals-route-boundary-via-shell-api", "summary": "The approvals route error boundary is exercised by failing the studio-shell API (GET /api/bots), which the route requires before opening the drawer; the approvals data-API failure path is asserted separately as an inline drawer error."},
]
EVIDENCE = {"browser": {}, "empty_states": {}, "error_states": {}, "permission": {}, "tests": [], "started_at": None}


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for evidence."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _artifact(relative: str) -> Path:
    """Resolve an artifact path inside this slice's evidence directory, creating parents."""
    path = artifact_path(f"{ARTIFACTS}/{relative}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _screenshot(page, relative: str) -> str:
    """Capture a screenshot and return its path relative to the artifact root."""
    path = _artifact(relative)
    page.screenshot(path=str(path), animations="disabled")
    return str(path.relative_to(Path(os.environ["HUTCH_TEST_ARTIFACTS_DIR"]).expanduser()))


def _sha256(relative: str) -> str:
    """Return the sha256 of a file in the clean export."""
    return hashlib.sha256(repository_path(relative).read_bytes()).hexdigest()


def _new_page(browser, width: int = 1440, height: int = 900):
    """Open a fresh context/page pair and collect page errors."""
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors


def _overflow(page) -> int:
    """Return the horizontal overflow in CSS pixels (0 or less means no overflow)."""
    return page.evaluate("document.documentElement.scrollWidth - innerWidth")


def _check_empty(page, slug: str):
    """Assert one route's empty state and return its copy and call to action."""
    if slug == "bots":
        page.get_by_text("No assistants yet — create one.", exact=True).wait_for(state="visible", timeout=20000)
        cta = page.locator("#first-run-submit")
        cta.wait_for(state="visible", timeout=20000)
        assert "Set up my assistant" in cta.inner_text()
        return "No assistants yet — create one.", {"kind": "button", "selector": "#first-run-submit", "text": cta.inner_text().strip()}
    if slug == "usage":
        copy = page.get_by_text("No model calls in the last 30 days.", exact=True)
        copy.wait_for(state="visible", timeout=20000)
        page.get_by_text("No assistants yet.", exact=True).wait_for(state="visible", timeout=20000)
        return copy.inner_text().strip(), {"kind": "none", "note": "no first-run call to action"}
    if slug == "models":
        page.get_by_text("No runtimes detected.", exact=True).wait_for(state="visible", timeout=20000)
        hint = page.get_by_text("Start Ollama to list installed models", exact=False)
        hint.first.wait_for(state="visible", timeout=20000)
        return "No runtimes detected.", {"kind": "hint", "text": hint.first.inner_text().strip()[:160]}
    if slug == "approvals":
        page.locator("#needs-you[open]").wait_for(state="attached", timeout=20000)
        page.get_by_text("No pending approvals.", exact=True).first.wait_for(state="visible", timeout=20000)
        return "No pending approvals.", {"kind": "none", "note": "empty needs-you drawer has no CTA"}
    page.get_by_text("Connect your work", exact=True).wait_for(state="visible", timeout=20000)
    page.get_by_text("Connect a provider", exact=True).first.click()
    empty = page.get_by_text("No connections configured.", exact=True)
    empty.first.wait_for(state="visible", timeout=20000)
    add = page.locator("#btn-add-conn")
    add.wait_for(state="visible", timeout=20000)
    assert "Connect a provider" in add.inner_text()
    return empty.first.inner_text().strip(), {"kind": "button", "selector": "#btn-add-conn", "text": add.inner_text().strip()}


@pytest.fixture(scope="module")
def browser():
    """Launch the documented default Chromium and record its exact build for evidence."""
    with pw.sync_playwright() as playwright:
        launched = launch_browser(playwright)
        executable = Path(playwright.chromium.executable_path)
        build_dir = executable.parents[1]
        shell = build_dir.parent / f"chromium_headless_shell-{build_dir.name.split('-', 1)[-1]}" / "chrome-headless-shell-linux64" / "chrome-headless-shell"
        EVIDENCE["browser"] = {"engine": launched.browser_type.name, "version": launched.version,
                               "playwright_chromium_executable_path": str(executable),
                               "chromium_revision_build_dir": build_dir.name,
                               "headless_shell_path": str(shell) if shell.exists() else None,
                               "launch": "tests.support.browser.launch_browser (default headless Chromium)"}
        yield launched
        launched.close()


@pytest.fixture()
def live(tmp_path, monkeypatch, browser):
    """Serve a real app on a fresh empty store with a deterministic empty Models view."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    import hutch.server.pages_models as pages_models
    empty_view = ModelsView(hw=SimpleNamespace(summary="route-state fixture: no runtime detected"),
                            runtimes=[], ollama_up=False, rows=[], presets=[], suggestions=[],
                            prices=[], price_errors=[], swaps=[], notes=[])
    monkeypatch.setattr(pages_models, "build_models_view", lambda config, store: empty_view)
    existing_contexts = set(browser.contexts)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not start within 15 seconds"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        for context in set(browser.contexts) - existing_contexts:
            context.close()
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.parametrize("slug,route,status,location", EMPTY_ROUTES, ids=[case[0] for case in EMPTY_ROUTES])
def test_first_run_empty_state_and_cta(browser, live, slug, route, status, location):
    """Assert the empty first-run state and any call to action, without horizontal overflow."""
    base, _app = live
    raw = browser.new_context()
    try:
        response = raw.request.get(base + route, max_redirects=0)
        assert response.status == status, f"{route}: expected {status}, got {response.status}"
        assert response.headers.get("location") == location
    finally:
        raw.close()
    for width, height in VIEWPORTS:
        context, page, errors = _new_page(browser, width, height)
        try:
            page.goto(base + route)
            copy_text, cta = _check_empty(page, slug)
            overflow = _overflow(page)
            assert overflow <= 1, f"{route} overflows horizontally by {overflow}px at {width}x{height}"
            assert not errors, f"{route} raised page errors at {width}x{height}: {errors}"
            EVIDENCE["empty_states"].setdefault(route, {})[f"{width}x{height}"] = {
                "expected_status": status, "expected_location": location, "final_url": page.url,
                "empty_copy": copy_text, "call_to_action": cta, "horizontal_overflow_px": overflow,
                "page_errors": errors, "screenshot": _screenshot(page, f"empty/{slug}-{width}x{height}.png")}
        finally:
            context.close()


@pytest.mark.parametrize("slug,route,api_pattern,detail,marker", SPA_ERRORS, ids=[case[0] for case in SPA_ERRORS])
def test_spa_route_error_state_and_retry(browser, live, slug, route, api_pattern, detail, marker):
    """A failing data request shows the route error boundary; retry recovers a view."""
    base, _app = live
    context, page, errors = _new_page(browser)
    try:
        page.route(api_pattern, lambda fulfill: fulfill.fulfill(
            status=503, content_type="application/json", body=json.dumps({"detail": detail})))
        page.goto(base + route)
        copy = page.get_by_text("Could not load this view.", exact=True)
        copy.wait_for(state="visible", timeout=20000)
        error_text = copy.inner_text()
        retry = page.locator("button[data-retry-route]")
        retry.wait_for(state="visible", timeout=20000)
        assert retry.inner_text().strip() == "Try again"
        failed_shot = _screenshot(page, f"error/{slug}-failed-1440x900.png")
        page.unroute(api_pattern)
        retry.click()
        page.get_by_text(marker, exact=False).first.wait_for(state="visible", timeout=20000)
        assert page.locator("button[data-retry-route]").count() == 0
        assert not errors, f"{route} raised page errors: {errors}"
        EVIDENCE["error_states"][route] = {
            "intercepted_api": api_pattern, "injected_status": 503, "visible_error": error_text.strip(),
            "retry_button": "Try again", "recovered_marker": marker, "recovered_url": page.url,
            "page_errors": errors, "failed_screenshot": failed_shot,
            "recovered_screenshot": _screenshot(page, f"error/{slug}-retried-1440x900.png")}
    finally:
        context.close()


def test_approvals_data_api_error_is_reported_inline(browser, live):
    """The approvals data API failure is handled by the drawer with its own Retry control."""
    base, _app = live
    context, page, errors = _new_page(browser)
    pattern = "**/api/v1/actions/approvals*"
    try:
        page.route(pattern, lambda fulfill: fulfill.fulfill(
            status=503, content_type="application/json", body=json.dumps({"detail": "approvals unavailable"})))
        page.goto(base + "/approvals")
        error = page.locator("#needs-you-error")
        error.wait_for(state="visible", timeout=20000)
        text = error.inner_text()
        assert "Could not refresh requests" in text
        retry = page.locator("#needs-you-retry")
        retry.wait_for(state="visible", timeout=20000)
        shot = _screenshot(page, "error/approvals-inline-1440x900.png")
        page.unroute(pattern)
        retry.click()
        page.get_by_text("No pending approvals.", exact=True).first.wait_for(state="visible", timeout=20000)
        assert page.locator("#needs-you-error").is_hidden() and not errors
        EVIDENCE["error_states"]["approvals-inline"] = {"intercepted_api": pattern, "visible_error": text.strip(),
                                                        "retry_button": "Retry", "recovered": True, "screenshot": shot}
    finally:
        context.close()


def test_models_server_flash_error_banner(browser, live):
    """Invalid price POST redirects to /models with div.flash.error[role=alert]."""
    base, _app = live
    context, page, errors = _new_page(browser)
    try:
        page.goto(base + "/models")
        page.get_by_text("No runtimes detected.", exact=True).wait_for(state="visible", timeout=20000)
        csrf = page.locator('meta[name="csrf"]').get_attribute("content")
        assert csrf
        response = page.request.post(base + "/models/prices/save", max_redirects=0,
                                     form={"csrf": csrf, "model": "route-state/invalid", "input": "not-a-number", "output": "1.0"})
        assert response.status == 303
        page.reload()
        banner = page.locator("div.flash.error[role='alert']")
        banner.wait_for(state="visible", timeout=20000)
        text = banner.inner_text()
        assert "input must be a number" in text
        page.evaluate("window.scrollTo(0, 0)")
        flash_shot = _screenshot(page, "error/models-flash-1440x900.png")
        page.goto(base + "/models")
        page.get_by_text("Add or correct a price", exact=True).click()
        page.locator('input[name="model"]').fill("route-state/invalid")
        page.locator('input[name="input"]').fill("not-a-number")
        page.locator('input[name="output"]').fill("1.0")
        page.get_by_role("button", name="Save price", exact=True).click()
        refused = page.get_by_text("cross-site request refused", exact=False)
        refused.first.wait_for(state="visible", timeout=20000)
        assert not errors
        EVIDENCE["error_states"]["/models"] = {
            "flash_banner": text.strip(), "post_status": response.status,
            "direct_form_submit_refused": refused.first.inner_text().strip()[:160], "page_errors": errors,
            "flash_screenshot": flash_shot,
            "origin_refused_screenshot": _screenshot(page, "error/models-form-origin-refused-1440x900.png")}
    finally:
        context.close()


def test_paired_monitor_is_denied_owner_routes_and_owner_controls(browser, live):
    """A monitor-only paired phone gets 403 on every owner route and sees no owner controls."""
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="phone-private-bot", display_name="Private phone fixture",
                               model="ollama/qwen3:4b", tools=[], remote_start_enabled=True))
    run = store.create_run(Run(bot_id=bot.id, prompt="Review the progress safely", status=RunStatus.running))
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"role": "assistant", "content": "Phone transcript fixture marker."}))
    store.flush_events()
    enrollment, outcome = store.exchange_pairing_code(store.create_pairing_code(), "Route state phone", "route-state-boundary")
    assert outcome == "ok" and enrollment
    paired = store.finish_passkey_enrollment(enrollment["token"], {
        "credential_id": secrets.token_bytes(24), "public_key": b"route-state-boundary-key",
        "sign_count": 0, "backup_eligible": True, "backed_up": True, "user_handle": store.webauthn_user_handle()})
    store._db.execute("UPDATE paired_credentials SET capabilities_json='[\"monitor\"]' WHERE id=?", (paired["id"],))
    store._db.commit()
    assert store.authenticate_session(paired["session_token"])["capabilities"] == ["monitor"]
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.add_cookies([{"name": "hutch_session", "value": paired["session_token"], "url": base}])
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    denied = {}
    try:
        for route in OWNER_ROUTES:
            response = context.request.get(base + route, max_redirects=0)
            denied[route] = response.status
            assert response.status == 403, f"{route} returned {response.status} for a paired phone"
            assert "this route is not available to paired phones" in response.text()
        page.goto(base + "/")
        page.locator("#phone-root .phone-brand").wait_for(timeout=20000)
        assert page.locator("body").evaluate("element => element.classList.contains('paired-phone')")
        assert page.locator(".app-shell").is_hidden()
        phone_text = page.locator("#phone-root").inner_text()
        assert "Monitor only" in phone_text
        assert page.locator('.phone-tabs [data-phone-tab="review"]').count() == 0
        assert page.locator("form[action='/stop-all']").count() == 0
        assert page.locator("[data-device-revoke]").count() == 0
        for word in ("Stop all", "Purge", "Delete assistant", "Revoke device"):
            assert word not in phone_text, f"owner-only copy {word!r} leaked into the paired view"
        supervision_shot = _screenshot(page, "permission/paired-supervision-390x844.png")
        page.get_by_role("button", name="Runs").click()
        run_button = page.locator(f'[data-phone-run="{run.id}"]')
        run_button.wait_for(state="visible", timeout=20000)
        run_button.click()
        page.locator(".phone-run-detail").wait_for(state="visible", timeout=20000)
        assert page.locator("[data-phone-stop], [data-phone-resume]").count() == 0
        run_shot = _screenshot(page, "permission/paired-run-detail-390x844.png")
        assert _overflow(page) <= 1 and not errors
        EVIDENCE["permission"] = {"owner_route_statuses": denied, "capabilities": ["monitor"],
                                  "paired_view": {"final_url": page.url, "body_class": "paired-phone",
                                                  "app_shell_hidden": True, "monitor_only_notice": True,
                                                  "review_tab": False, "owner_controls_absent": True,
                                                  "page_errors": errors},
                                  "screenshots": [supervision_shot, run_shot]}
    finally:
        context.close()


@pytest.fixture(autouse=True)
def _record(request):
    """Record each test's node id and duration for validation.json."""
    started = time.monotonic()
    yield
    EVIDENCE["tests"].append({"nodeid": request.node.nodeid, "seconds": round(time.monotonic() - started, 2)})


def _git_head() -> str:
    """Return HEAD of the main checkout containing this clean export."""
    candidate = Path(repository_path("."))
    checkout = next((parent for parent in candidate.parents if (parent / ".git").exists()), candidate.parents[2])
    try:
        result = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


@pytest.fixture(scope="session", autouse=True)
def _evidence(request):
    """Write the single validation.json artifact when the focused run finishes."""
    yield
    artifacts = Path(os.environ["HUTCH_TEST_ARTIFACTS_DIR"]).expanduser()
    command = ("cd {cwd} && PYTHONPATH=$PWD/src HUTCH_TEST_ARTIFACTS_DIR={artifacts} {python} -m pytest "
               "-q --no-header --tb=line tests/e2e/test_route_state_boundaries.py").format(
        cwd=Path.cwd(), artifacts=artifacts, python=sys.executable)
    slice_dir = artifact_path(ARTIFACTS)
    payload = {"schema": 1, "slice": "completion-plan Slice C: dashboard route state boundaries",
               "generated_at": _now(), "test_file": "tests/e2e/test_route_state_boundaries.py",
               "clean_export": str(Path.cwd()), "git_head": _git_head(), "exact_command": command,
               "environment": {"python": sys.version.split()[0], "python_executable": sys.executable,
                               "platform": platform.platform(), "playwright": package_version("playwright"),
                               "uvicorn": package_version("uvicorn")},
               "browser": EVIDENCE["browser"], "viewports": [f"{w}x{h}" for w, h in VIEWPORTS],
               "routes": list(OWNER_ROUTES), "empty_states": EVIDENCE["empty_states"],
               "error_states": EVIDENCE["error_states"], "permission": EVIDENCE["permission"],
               "tests": EVIDENCE["tests"],
               "source_sha256": {relative: _sha256(relative) for relative in SOURCE_FILES},
               "residual_gaps": RESIDUAL_GAPS, "deviations": DEVIATIONS,
               "artifacts": sorted(str(path.relative_to(artifacts)) for path in slice_dir.rglob("*")
                                   if path.is_file() and path.name != "validation.json")}
    _artifact("validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
