"""One direct chat per assistant, with deliberate access to historical/task threads."""
import json

from hutch.models import Bot
from tests.e2e.test_browser import browser, live, switcher_env, wait_for_page  # noqa: F401
from tests.support.artifacts import artifact_path


def test_main_and_specialist_homes_persist_without_absorbing_history(browser, switcher_env):
    base, app, _fake = switcher_env
    main = app.state.store.create_bot(Bot(name="hutch", display_name="Hutch", model="ollama/tiny:1b", tools=[]))
    app.state.store.set_workspace_coordinator(main.id)
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("persistent-chat")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/chat")
        page.locator("#chat-prompt").wait_for()
        assert page.locator(".ctx-id h1").inner_text() == "Hutch"
        main_home = page.request.get(f"{base}/api/v1/bots/{main.id}/home-conversation").json()["conversation"]["id"]
        assert page.locator("#conversation-switcher").is_hidden()
        assert page.locator("#studio-new-conversation").count() == 0
        page.goto(base + "/#/chat/chatty")
        wait_for_page(page, "document.querySelector('.ctx-id h1')?.textContent === 'Chatty'")
        specialist = app.state.store.get_bot("chatty")
        specialist_home = page.request.get(f"{base}/api/v1/bots/{specialist.id}/home-conversation").json()["conversation"]["id"]
        assert specialist_home != main_home
        earlier, _ = app.state.store.create_conversation(specialist.id, "Earlier research",
            idem_key="retained-history", request_hash="retained-history")
        page.goto(f"{base}/#/conversation/{earlier['id']}")
        page.locator("#conversation-switcher").wait_for()
        assert page.locator("#conversation-switcher").input_value() == earlier["id"]
        page.reload()
        page.locator("#conversation-switcher").wait_for()
        assert page.url.endswith(f"#/conversation/{earlier['id']}")
        page.locator("#studio-conversation-options").click()
        page.get_by_role("link", name="Return to main chat", exact=True).click()
        wait_for_page(page, "id => document.querySelector('#conversation-switcher')?.value === id", arg=specialist_home)
        assert page.locator("#conversation-switcher").is_hidden()
        assert page.locator("#conversation-switcher").input_value() == specialist_home
        page.locator('[data-nav="chat"]').click()
        wait_for_page(page, "document.querySelector('.ctx-id h1')?.textContent === 'Hutch'")
        assert page.locator("#conversation-switcher").input_value() == main_home
        for width, height in ((1440, 900), (768, 1024), (320, 900)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(out / f"main-{width}.png"), animations="disabled")
        second = browser.new_context()
        try:
            fresh = second.new_page()
            fresh.goto(base + "/#/chat")
            fresh.locator("#chat-prompt").wait_for()
            assert fresh.locator("#conversation-switcher").input_value() == main_home
        finally:
            second.close()
        assert app.state.store.get_conversation(earlier["id"])["title"] == "Earlier research"
        assert app.state.store.list_runs(limit=10) == []
        assert not errors, errors
        (out / "validation.json").write_text(json.dumps({"browser": browser.version,
            "viewports": [[1440, 900], [768, 1024], [320, 900]], "page_errors": errors,
            "scenario": "stable main/specialist homes, deliberate history, reload, fresh browser profile; no inference"}, indent=2) + "\n")
    finally:
        context.close()
