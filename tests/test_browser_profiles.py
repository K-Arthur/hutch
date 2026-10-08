from __future__ import annotations

import sys
import types

import pytest

from hutch.models import Bot
from hutch.tools.browser import BrowserTool


def test_browser_tool_instances_own_distinct_bot_profiles(monkeypatch, config):
    created = []

    class Context:
        pages = []

        def route(self, _pattern, handler):
            self.handler = handler

        def close(self):
            self.closed = True

    class Chromium:
        def launch_persistent_context(self, *, user_data_dir, **_kwargs):
            context = Context()
            context.profile = user_data_dir
            created.append(context)
            return context

    class Playwright:
        chromium = Chromium()

        def stop(self):
            self.stopped = True

    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: types.SimpleNamespace(start=Playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)

    def ctx(name):
        bot = Bot(name=name)
        run = types.SimpleNamespace(id=f"run-{name}")
        return types.SimpleNamespace(
            config=config, bot=bot, run=run, headless=True,
            emit=lambda _event: None, on_finish=[]
        )

    first, second = BrowserTool(), BrowserTool()
    a, b = ctx("profile-a"), ctx("profile-b")
    browser_a = first._ensure(a)
    browser_b = second._ensure(b)

    assert browser_a is not browser_b
    assert browser_a.profile != browser_b.profile
    assert browser_a.profile.endswith("profile-a/browser-profile")
    assert browser_b.profile.endswith("profile-b/browser-profile")
    assert len(a.on_finish) == len(b.on_finish) == 1

    first._teardown()
    assert browser_a.closed and not hasattr(browser_b, "closed")
    second._teardown()


@pytest.mark.parametrize("navigate_during_review", [False, True])
def test_browser_typing_approval_binds_text_destination_and_profile(
    monkeypatch, config, store, tmp_path, navigate_during_review
):
    from hutch.approvals import resolve_approval_ex
    from hutch.models import ApprovalMode
    from tests.test_tools import make_ctx
    ctx = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.auto)
    store.allow_sticky(ctx.bot.id, "browser:*")
    args = {"action": "type", "selector": "#recipient", "text": "reviewed recipient"}
    fills = []
    page = types.SimpleNamespace(url="https://example.com/compose", fill=lambda *a, **kw: fills.append(a))
    tool = BrowserTool()
    monkeypatch.setattr(tool, "_ensure", lambda _: types.SimpleNamespace(pages=[page]))
    wait = ctx.gate._wait

    def human(req, action, **wait_args):
        stored = store.get_approval(req.id)
        assert stored.outward and not stored.sticky_key
        assert stored.detail == {"action": "type", "selector": "#recipient", "text": "reviewed recipient",
                                 "url": "https://example.com/compose", "profile_bot_id": ctx.bot.id}
        args["text"] = "unreviewed recipient"
        if navigate_during_review:
            page.url = "https://elsewhere.example/compose"
        assert resolve_approval_ex(store, req.id, True, expected_hash=stored.action_hash).won
        return wait(req, action, **wait_args)

    monkeypatch.setattr(ctx.gate, "_wait", human)
    result = tool.run(args, ctx)
    if navigate_during_review:
        assert not result.ok and "navigated after review" in result.output
        assert fills == []
    else:
        assert result.ok and fills == [("#recipient", "reviewed recipient")]
