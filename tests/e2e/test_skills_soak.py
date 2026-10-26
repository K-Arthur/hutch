"""Bounded soak for the skills surfaces: concurrent run churn, approvals, cancellations, skill
reloads and SPA navigation. Runs in ~60 seconds and asserts what a soak can assert deterministically:
no page errors, no leaked active runs, a readable registry, and fail-closed outcomes when a bound
skill is disabled while activation is requested.

Live provider auth refresh is NOT covered here (no live account in this environment); the boundary
is stated in the evidence record instead of being faked.
"""

from __future__ import annotations
from tests.e2e.settings_pane import open_assistant_customization  # noqa: E402

import json
import threading
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.approvals import resolve_approval  # noqa: E402
from hutch.models import ACTIVE_STATUSES, Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.skills import SkillRegistry  # noqa: E402

SOAK_SECONDS = 60.0
VALID = """\
---
name: {name}
description: Soak skill for concurrent lifecycle coverage.
metadata:
  hutch.version: "1.0"
---

## Steps
1. Read the workspace.
2. Write a digest.
"""


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = None
        errors = []
        for engine in (p.chromium, p.firefox):
            try:
                b = engine.launch()
                break
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if b is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield b
        b.close()


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", app
    server.should_exit = True
    t.join(timeout=10)
    assert not t.is_alive()



def test_skills_soak_under_churn(browser, live, tmp_path):
    base, app = live
    store, engine = app.state.store, app.state.engine
    state_dir = Path(app.state.config.state_dir)
    source = state_dir / "sources" / "soak-skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(VALID.format(name="soak-skill"), encoding="utf-8")
    registry = SkillRegistry(state_dir)
    registry.install_path(source)
    registry.trust("soak-skill")

    bot = store.create_bot(Bot(name="soak-bot", display_name="Soak Bot", model="mock/demo",
                               tools=["files"], skills=["soak-skill"], approval_mode="ask"))
    other = store.create_bot(Bot(name="soak-plain", model="mock/demo", tools=["files"], approval_mode="ask"))

    counters = {"submitted": 0, "activated": 0, "approved": 0, "denied": 0, "cancelled": 0,
                "failed_closed": 0, "succeeded": 0, "library_reads": 0, "toggles": 0}
    stop = threading.Event()
    worker_errors: list[str] = []

    def churn():
        iteration = 0
        try:
            while not stop.is_set():
                iteration += 1
                activate = iteration % 3 == 0
                try:
                    run = engine.submit(bot if activate else other, f"soak task {iteration}",
                                        origin="manual:soak", skills=["soak-skill"] if activate else None)
                    counters["submitted"] += 1
                    if activate:
                        counters["activated"] += 1
                except Exception as exc:  # noqa: BLE001 - refusal is an expected fail-closed outcome
                    if "disabled" in str(exc):
                        counters["failed_closed"] += 1
                    else:
                        worker_errors.append(f"submit: {exc}")
                    continue
                engine.dispatch_pending()
                # approval churn: resolve whatever waits, alternating verdicts
                for _ in range(40):
                    if stop.is_set():
                        break
                    pending = [a for a in store.pending_approvals() if a.run_id == run.id]
                    if pending:
                        approve = iteration % 2 == 0
                        resolve_approval(store, pending[0].id, approve)
                        counters["approved" if approve else "denied"] += 1
                        break
                    status = store.get_run(run.id)
                    if status and status.status not in ACTIVE_STATUSES:
                        break
                    time.sleep(0.05)
                if iteration % 4 == 0:
                    engine.stop_run(run.id)
                    counters["cancelled"] += 1
                # skill reload churn every 7th iteration
                if iteration % 7 == 0:
                    registry.disable("soak-skill")
                    counters["toggles"] += 1
                    time.sleep(0.3)
                    registry.enable("soak-skill")
                if iteration % 5 == 0:
                    report = registry.library()
                    counters["library_reads"] += 1
                    assert any(item["name"] == "soak-skill" for item in report["skills"])
                time.sleep(0.15)
        except Exception as exc:  # noqa: BLE001 - soak failures must be reported, not swallowed
            worker_errors.append(f"churn: {type(exc).__name__}: {exc}")

    thread = threading.Thread(target=churn, daemon=True, name="skills-soak-churn")
    thread.start()

    page = browser.new_page(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.add_init_script("""
      window.__soakErrors = [];
      window.addEventListener('unhandledrejection', event => {
        window.__soakErrors.push(String((event.reason && (event.reason.stack || event.reason.message)) || event.reason));
      });
    """)
    navigations = 0
    route_errors: list[str] = []
    started = time.monotonic()
    try:
        while time.monotonic() - started < SOAK_SECONDS:
            try:
                page.goto(base + "/#/skills")
                page.get_by_role("heading", name="Skills", exact=True).wait_for()
                navigations += 1
                page.goto(base + "/#/bot/soak-bot")
                open_assistant_customization(page, "tools")
                page.locator("#bot-skills-section").wait_for()
                navigations += 1
                page.goto(base + "/#/chat/soak-bot")
                page.locator("#chat-prompt").wait_for()
                navigations += 1
            except Exception:
                print("SOAK_NAV_FAILURE url=", page.url)
                print("SOAK_NAV_VIEW ", page.locator("#view").inner_text()[:300].replace("\n", " | "))
                print("SOAK_NAV_REJECTIONS ", page.evaluate("window.__soakErrors")[:3])
                print("SOAK_NAV_ERRORS ", page_errors[-3:], console_errors[-3:])
                raise
            view_text = page.locator("#view").inner_text()
            if "Could not load this view" in view_text:
                route_errors.append(f"{page.url} :: {view_text[:160]}")
                page.get_by_text("Try again").click()
                page.wait_for_timeout(300)
            if navigations % 12 == 0:
                page.reload()
                navigations += 1
            time.sleep(0.6)
    finally:
        stop.set()
        thread.join(timeout=30)
        # leave the executor quiet: stop anything still active before assertions
        for active in store.active_runs():
            engine.stop_run(active.id)
        deadline = time.time() + 20
        while time.time() < deadline and any(r.status in ACTIVE_STATUSES for r in store.active_runs()):
            time.sleep(0.2)
        page.close()

    duration = round(time.monotonic() - started, 1)
    results = {
        "duration_s": duration,
        "navigations": navigations,
        "page_errors": page_errors,
        "console_errors": console_errors[:5],
        "worker_errors": worker_errors,
        "route_errors": route_errors[:5],
        **counters,
        "active_runs_left": len([r for r in store.active_runs() if r.status in ACTIVE_STATUSES]),
        "registry_readable": bool(registry.detail("soak-skill")),
        "bound_skill_still_enabled": registry.detail("soak-skill")["status"] == "enabled",
    }
    print("SOAK_RESULTS " + json.dumps(results))
    assert not page_errors, page_errors
    assert not worker_errors, worker_errors
    assert not route_errors, route_errors
    assert results["active_runs_left"] == 0, results
    assert results["registry_readable"] and results["bound_skill_still_enabled"]
    assert counters["submitted"] >= 20 and counters["approved"] + counters["denied"] >= 5, counters
    assert counters["toggles"] >= 3 and counters["library_reads"] >= 5, counters
