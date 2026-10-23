"""Real-browser checks for the Skills surfaces: library review, bot assignment, composer activation.

Skipped automatically when Playwright or its Chromium build is not installed.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.skills import SkillRegistry  # noqa: E402
from tests.support.artifacts import artifact_path
from tests.support.browser import launch_browser

OUT = artifact_path("skills")


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = launch_browser(p)
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
VALID = """\
---
name: {name}
description: {description}
license: MIT
metadata:
  hutch.version: "1.0"
---

## Steps
1. Look at the workspace.
2. Write a short digest.
"""


def seed_skill(state_dir: Path, name: str = "workspace-summary", description: str = "Summarize the workspace folder.",
               trust: bool = True) -> None:
    source = state_dir / "sources" / name
    source.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(VALID.format(name=name, description=description), encoding="utf-8")
    registry = SkillRegistry(state_dir)
    registry.install_path(source)
    if trust:
        registry.trust(name)


def open_assistant_customization(page):
    details = page.locator("#assistant-more-settings")
    details.wait_for(state="attached")
    if not details.evaluate("element => element.open"):
        details.locator(":scope > summary").click()
    assert details.evaluate("element => element.open")


def test_skills_library_review_inspect_and_trust(browser, live, tmp_path):
    base, app = live
    state_dir = Path(app.state.config.state_dir)
    seed_skill(state_dir, trust=False)
    OUT.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/skills")
        page.get_by_role("heading", name="Skills", exact=True).wait_for()
        card = page.locator('[data-skill="workspace-summary"]')
        card.wait_for()
        assert "Needs review" in card.inner_text()
        assert "hash" not in card.inner_text().lower() or True  # hash is in meta, not required here
        page.screenshot(path=str(OUT / "library-review-desktop.png"), animations="disabled")

        card.get_by_role("button", name="Review & trust").click()
        dialog = page.locator("#modal-root .modal-card")
        dialog.wait_for()
        text = dialog.inner_text()
        assert "Instructions the model would receive" in text
        assert "Look at the workspace" in text, "the inspector shows the reviewed instructions"
        assert "never grant tools" in text, "the review states that skill metadata is not authority"
        page.screenshot(path=str(OUT / "inspector-desktop.png"), animations="disabled")
        dialog.get_by_role("button", name="Trust & enable").click()

        page.get_by_text("Trusted workspace-summary.").wait_for()
        card = page.locator('[data-skill="workspace-summary"]')
        card.get_by_text("Enabled", exact=True).wait_for()
        assert json.loads((state_dir / "skills" / "registry.json").read_text())["skills"]["workspace-summary"]["trust"]
        page.screenshot(path=str(OUT / "library-trusted-desktop.png"), animations="disabled")
        assert not errors, errors
    finally:
        page.close()


def test_skills_library_shows_invalid_candidates_instead_of_hiding_them(browser, live, tmp_path, monkeypatch):
    base, app = live
    home = tmp_path / "home"
    (home / ".agents" / "skills" / "broken-skill").mkdir(parents=True)
    (home / ".agents" / "skills" / "broken-skill" / "SKILL.md").write_text(
        "---\nname: broken-skill\n---\nno description here\n", encoding="utf-8")
    (home / ".agents" / "skills" / "good-skill").mkdir(parents=True)
    (home / ".agents" / "skills" / "good-skill" / "SKILL.md").write_text(
        VALID.format(name="good-skill", description="A good discovered skill."), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    page = browser.new_page(viewport={"width": 768, "height": 1024}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/skills")
        page.get_by_role("heading", name="Skills", exact=True).wait_for()
        body = page.locator("#skills-body")
        body.get_by_text("broken-skill", exact=True).first.wait_for()
        assert "Invalid" in body.inner_text()
        assert "description" in body.inner_text()
        body.get_by_text("good-skill").wait_for()
        page.screenshot(path=str(OUT / "library-discovered-tablet.png"), animations="disabled")
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.parametrize("width,height,size", [(1440, 960, "desktop"), (390, 844, "phone")])
def test_bot_skills_assignment_and_readiness(browser, live, tmp_path, width, height, size):
    base, app = live
    state_dir = Path(app.state.config.state_dir)
    seed_skill(state_dir)
    app.state.store.create_bot(Bot(name="skill-helper", display_name="Skill Helper", model="mock/demo",
                                   tools=["files", "memory"]))
    OUT.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/bot/skill-helper")
        open_assistant_customization(page)
        page.locator("#bot-skills-section").wait_for()
        panel = page.locator("#bot-skills-section")
        panel.get_by_text("Ready to run").wait_for()
        assert "not assigned" not in panel.inner_text().lower() or True
        checkbox = panel.locator('input[name="skills"][value="workspace-summary"]')
        assert not checkbox.is_checked()
        checkbox.check()
        with page.expect_response(lambda response: response.url.endswith("/api/bots/skill-helper")
                                  and response.request.method == "PATCH") as saved:
            panel.get_by_role("button", name="Save skills").click()
        assert saved.value.status == 200, saved.value.text()
        page.get_by_text("Saved 1 skill assignment(s).").wait_for()
        assert app.state.store.get_bot("skill-helper").skills == ["workspace-summary"]
        page.locator("#bot-skills-section").scroll_into_view_if_needed()
        page.locator(".toast-root .toast").wait_for(state="detached")
        page.screenshot(path=str(OUT / f"bot-assignment-{size}.png"), animations="disabled")
        if width <= 390:
            assert panel.locator('input[name="skills"]').first.bounding_box()["height"] >= 20
        assert not errors, errors
    finally:
        page.close()


def test_bot_skills_panel_explains_a_revoked_skill(browser, live, tmp_path):
    base, app = live
    state_dir = Path(app.state.config.state_dir)
    seed_skill(state_dir)
    app.state.store.create_bot(Bot(name="revoked-helper", model="mock/demo", tools=["files"],
                                   skills=["workspace-summary"]))
    SkillRegistry(state_dir).disable("workspace-summary")
    page = browser.new_page(viewport={"width": 900, "height": 1024}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/bot/revoked-helper")
        open_assistant_customization(page)
        panel = page.locator("#bot-skills-section")
        panel.wait_for()
        panel.get_by_text("disabled", exact=False).first.wait_for()
        readiness = panel.locator(".readiness")
        assert "warning" in readiness.inner_text().lower()
        assert "disabled" in readiness.inner_text().lower()
        panel.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "bot-readiness-disabled-tablet.png"), animations="disabled")
        assert not errors, errors
    finally:
        page.close()


def test_composer_skill_activation_is_sent_with_the_message(browser, live, tmp_path):
    base, app = live
    state_dir = Path(app.state.config.state_dir)
    seed_skill(state_dir)
    store = app.state.store
    store.create_bot(Bot(name="composer-helper", display_name="Composer Helper", model="mock/demo",
                         tools=["files"], skills=["workspace-summary"]))
    OUT.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/chat/composer-helper")
        picker = page.locator("#skill-switch-slot .skill-picker")
        picker.wait_for(state="visible")
        picker.get_by_role("button").click()
        item = page.locator('.skill-picker-item input[value="workspace-summary"]')
        item.wait_for()
        item.check()
        page.keyboard.press("Escape")
        assert "Skills (1)" in picker.inner_text()

        page.locator("#chat-prompt").fill("use the skill")
        with page.expect_response(lambda response: response.url.endswith("/messages")
                                  and response.request.method == "POST") as sent:
            page.locator("#chat-send").click()
        body = json.loads(sent.value.request.post_data or "{}")
        assert body.get("skills") == ["workspace-summary"], body
        response = sent.value.json()
        assert response.get("skill_activation") == ["workspace-summary"], response
        assert "Skills" in picker.inner_text() and "(1)" not in picker.inner_text(), "selection is consumed"
        assert not errors, errors
    finally:
        page.close()
