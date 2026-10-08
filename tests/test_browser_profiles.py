from __future__ import annotations

import sys
import types

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
