"""Notion browser sign-in and per-assistant read grants through the real local API."""
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from hutch.integrations.notion_mcp import NotionMCP
from hutch.integrations import notion_access
from hutch.models import Bot
from tests.e2e.test_browser import browser, live  # noqa: F401
from tests.test_notion_oauth import notion  # noqa: F401
from tests.test_notion_mcp import server  # noqa: F401
from tests.support.artifacts import artifact_path


@pytest.fixture
def connection(live, monkeypatch, notion, server):
    base, app = live
    book, _, _ = notion
    wire, transport = server
    wire["token"] = "ACCESS-0"
    monkeypatch.setattr("hutch.server.notion_api.NotionBook", lambda state: book)
    monkeypatch.setattr("hutch.server.notion_api.NotionMCP", lambda b, account: NotionMCP(b, account, transport=transport))
    bot = app.state.store.create_bot(Bot(name="notion-research", display_name="Research", model="mock/demo", tools=[]))
    return base, app, bot


def test_notion_signin_grant_and_revoke_are_visible_scoped_and_responsive(browser, connection):
    base, app, bot = connection
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.route("https://mcp.notion.com/authorize**", lambda route: route.fulfill(body="Fixture Notion consent"))
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/#/connections")
        page.locator('[data-connection-open="notion"]').click()
        card = page.locator("#connection-notion")
        card.wait_for()
        assert "No token or developer setup needed" in card.inner_text()
        with page.expect_popup() as popup_info:
            page.get_by_role("button", name="Connect Notion", exact=True).click()
        popup = popup_info.value
        popup.wait_for_url("https://mcp.notion.com/authorize**")
        assert popup.evaluate("window.opener === null")
        query = parse_qs(urlsplit(popup.url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert not notion_access.bindings(app.state.store, bot.id)
        popup.goto(base + "/api/v1/connections/notion/callback?" + urlencode({"state": query["state"][0], "code": "fixture-code"}))
        popup.get_by_role("heading", name="Apps & AI").wait_for()
        assert "notion_result" not in popup.url and "fixture-code" not in popup.url
        popup.close()
        page.reload()
        page.locator("#connection-detail-heading h2").get_by_text("Notion", exact=True).wait_for()
        page.get_by_role("button", name="Choose assistant access", exact=True).click()
        page.get_by_role("dialog").wait_for()
        assert page.locator("#notion-grant-bot").input_value() == bot.id
        assert "configured model providers" in page.get_by_role("dialog").inner_text()
        assert page.locator('[data-notion-tool="notion-search"]').is_checked()
        assert page.locator('[data-notion-tool="notion-delete-page"]').count() == 0
        assert not notion_access.bindings(app.state.store, bot.id)
        out = artifact_path("notion-connection")
        out.mkdir(parents=True, exist_ok=True)
        for width, height in ((1440, 900), (768, 1024), (320, 900)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.screenshot(path=str(out / f"grant-{width}.png"), animations="disabled")
        page.get_by_text("Tool definitions", exact=True).click()
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.get_by_role("button", name="Grant read access", exact=True).click()
        page.get_by_role("dialog").wait_for(state="hidden")
        assert len(notion_access.bindings(app.state.store, bot.id)) == 1
        page.get_by_role("button", name="Revoke assistant access", exact=True).click()
        page.locator('[data-notion-revoke]').wait_for(state="detached")
        assert not notion_access.bindings(app.state.store, bot.id)
        page.get_by_role("button", name="Disconnect Notion", exact=True).click()
        page.locator("#modal-confirm").click()
        page.get_by_text("No Notion accounts connected.", exact=True).wait_for()
        assert not errors
    finally:
        context.close()
