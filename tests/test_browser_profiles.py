from __future__ import annotations

import sys
import types

import pytest

from hutch.models import Bot
from hutch.tools.browser import BrowserTool, BrowserUnavailable


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

    same_profile = BrowserTool()
    with pytest.raises(BrowserUnavailable, match="profile is already in use"):
        same_profile._ensure(ctx("profile-a"))

    first._teardown()
    assert browser_a.closed and not hasattr(browser_b, "closed")
    reused = same_profile._ensure(ctx("profile-a"))
    assert reused.profile == browser_a.profile
    same_profile._teardown()
    second._teardown()


def test_browser_route_setup_failure_closes_process_and_releases_profile_lease(monkeypatch, config):
    sync_api = pytest.importorskip("playwright.sync_api")

    browser_state = {"closed": False, "stopped": False}

    class Browser:
        pages = []

        def route(self, *_args, **_kwargs):
            raise RuntimeError("route registration failed")

        def close(self):
            browser_state["closed"] = True

    class Chromium:
        def launch_persistent_context(self, **_kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

        def stop(self):
            browser_state["stopped"] = True

    class Driver:
        def start(self):
            return Playwright()

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: Driver())
    bot = Bot(name="route-failure")
    context = types.SimpleNamespace(headless=True, config=config, bot=bot, on_finish=[])
    tool = BrowserTool()
    with pytest.raises(BrowserUnavailable, match="route registration failed"):
        tool._ensure(context)

    assert browser_state == {"closed": True, "stopped": True}
    profile_dir = config.bot_profiles_dir(bot.name)
    probe = BrowserTool()
    probe._lease_fds.append(probe._lock(profile_dir.parent / "browser-profile.lock", "this bot's browser profile"))
    probe._release_leases()


@pytest.mark.parametrize("headless", [True, False])
def test_login_challenge_only_waits_when_same_live_browser_is_visible(config, headless):
    page_state = {"body": "Sign in to continue", "reloads": 0}

    class Page:
        url = "https://example.com/login"

        def goto(self, *_args, **_kwargs):
            pass

        def title(self):
            return "Example login"

        def inner_text(self, _selector):
            return page_state["body"]

        def reload(self, **_kwargs):
            page_state["reloads"] += 1
            page_state["body"] = "Signed in dashboard"

    class Gate:
        waited = []

        def decide(self, *_args, **_kwargs):
            pass

        def wait_for_human(self, *args, **kwargs):
            self.waited.append((args, kwargs))
            page_state["body"] = "Signed in dashboard"

    gate = Gate()
    ctx = types.SimpleNamespace(
        bot=Bot(name="handoff", local_browser_handoff=not headless),
        run=types.SimpleNamespace(id="run-handoff"), config=config, headless=headless,
        policy=types.SimpleNamespace(check_url=lambda _url: None), gate=gate,
        on_finish=[], emit=lambda _event: None, dry_run=False,
    )
    page = Page()
    tool = BrowserTool()
    tool._ensure = lambda _ctx: types.SimpleNamespace(pages=[page])

    result = tool.run({"action": "goto", "url": page.url}, ctx)
    assert page_state["reloads"] == (0 if headless else 1)
    assert len(gate.waited) == (0 if headless else 1)
    if headless:
        assert not result.ok and "Enable Local browser handoff" in result.output
        assert result.data["handoff_available"] is False
    else:
        assert result.ok
        args, kwargs = gate.waited[0]
        assert "login/CAPTCHA wall" in args[0]
        assert kwargs["handoff"].startswith("Complete this step in the visible Hutch browser window")


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
