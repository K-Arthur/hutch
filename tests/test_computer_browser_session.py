"""Browser session ownership: driver-slot scope and target identity (computer use, slice 1).

Fakes here inject faults deterministically (a gate that blocks, a page with duplicate matches). They are not evidence that
real Chromium behaves this way: tests/e2e/test_computer_browser_real.py drives the same behaviours in a real browser.
"""

from __future__ import annotations

import threading
import time
import types

import pytest

from hutch.models import Bot
from hutch.safety import Decision, Verdict
from hutch.tools.browser import BrowserTool

_SNAPSHOT = ({"target_kind": "element", "target": {"kind": "element", "label": "x", "tag": "button", "type": ""},
              "target_fingerprint": "f" * 64}, "f" * 64)


class _Policy:
    def check_url(self, _url):
        return Decision(Verdict.allow, "test", rule="allow:test", risk="low")


class _Gate:
    """Approval/human gate double. ``block`` makes decide()/wait_for_human() park until released."""

    def __init__(self, block: threading.Event | None = None, on_human=None):
        self.block = block
        self.on_human = on_human          # what the person did while the run was parked
        self.entered = threading.Event()
        self.decisions: list[tuple] = []

    def _park(self):
        self.entered.set()
        if self.block is not None:
            assert self.block.wait(15), "test never released the gate"

    def decide(self, tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        self.decisions.append((tool, action, detail))
        self._park()

    def wait_for_human(self, reason, url="", handoff=""):
        self._park()
        if self.on_human is not None:
            self.on_human()

    def cancelled(self):
        return False


class _Locator:
    def __init__(self, page, key, nodes):
        self.page, self.key, self.nodes = page, key, list(nodes)

    def count(self):
        return len(self.nodes)

    @property
    def first(self):
        return _Locator(self.page, self.key, self.nodes[:1])

    def nth(self, index):
        return _Locator(self.page, self.key, self.nodes[index:index + 1])

    def scroll_into_view_if_needed(self, timeout=None):
        pass

    def bounding_box(self):
        return {"x": 1, "y": 1, "width": 10, "height": 10}

    def evaluate_all(self, _js):
        return False

    def evaluate(self, _js, *_args):
        return {}

    def click(self, timeout=None):
        assert len(self.nodes) == 1, "the driver was asked to click an ambiguous locator"
        self.page.clicks.append(self.nodes[0])


class _Page:
    url = "https://shop.example/cart"

    def __init__(self, body="Cart", selectors=None, texts=None):
        self.body = body
        self.selectors = selectors or {}
        self.texts = texts or {}
        self.clicks: list[str] = []
        self.frames: list = []

    def inner_text(self, _selector):
        return self.body

    def title(self):
        return "Cart"

    def evaluate(self, _js, arg=None):
        return False if arg is None else self.body

    def locator(self, selector):
        return _Locator(self, selector, self.selectors.get(selector, []))

    def get_by_text(self, text, exact=False):
        return _Locator(self, text, self.texts.get((text, exact), []))

    def goto(self, *_args, **_kwargs):
        pass


class _Context:
    def __init__(self, page):
        self.pages = [page]

    def on(self, _event, _callback):
        pass


def _tool(page, config, name, gate, *, handoff=False):
    tool = BrowserTool()
    tool._browser = _Context(page)
    bot = Bot(name=name, local_browser_handoff=handoff)
    ctx = types.SimpleNamespace(
        config=config, bot=bot, run=types.SimpleNamespace(id=f"run-{name}"), headless=not handoff,
        emit=lambda _event: None, on_finish=[], gate=gate, policy=_Policy(), workspace=config.state_dir,
        dry_run=False, begin_effect=lambda: None)
    return tool, ctx


@pytest.fixture(autouse=True)
def _review_snapshot(monkeypatch):
    monkeypatch.setattr(BrowserTool, "_click_review_snapshot", staticmethod(lambda _page, _locator: _SNAPSHOT))


def _run_in_thread(fn):
    box: dict = {}

    def target():
        box["result"] = fn()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, box


def test_a_pending_approval_does_not_block_another_bots_browser_action(config):
    release = threading.Event()
    blocked_gate = _Gate(block=release)
    tool_a, ctx_a = _tool(_Page(), config, "waiting-bot", blocked_gate)
    tool_b, ctx_b = _tool(_Page(body="Other bot's page"), config, "working-bot", _Gate())

    thread_a, _ = _run_in_thread(lambda: tool_a.run({"action": "goto", "url": "https://shop.example/"}, ctx_a))
    try:
        assert blocked_gate.entered.wait(5), "bot A never reached its approval wait"
        started = time.monotonic()
        thread_b, box_b = _run_in_thread(lambda: tool_b.run({"action": "read"}, ctx_b))
        thread_b.join(3)
        still_blocked = thread_b.is_alive()
    finally:
        release.set()
        thread_a.join(5)
    thread_b.join(5)
    assert not still_blocked, "a pending approval in one bot held the browser slot and blocked another bot"
    assert box_b["result"].ok and "Other bot's page" in box_b["result"].output
    assert time.monotonic() - started < 3


def test_a_human_wait_does_not_block_another_bots_browser_action(config):
    release = threading.Event()
    wall = _Page(body="Please complete the CAPTCHA")
    gate_a = _Gate(block=release, on_human=lambda: setattr(wall, "body", "Signed in"))
    tool_a, ctx_a = _tool(wall, config, "login-bot", gate_a, handoff=True)
    tool_b, ctx_b = _tool(_Page(body="Independent page"), config, "other-bot", _Gate())

    thread_a, _ = _run_in_thread(lambda: tool_a.run({"action": "read"}, ctx_a))
    try:
        assert gate_a.entered.wait(5), "bot A never reached its human wait"
        thread_b, box_b = _run_in_thread(lambda: tool_b.run({"action": "read"}, ctx_b))
        thread_b.join(3)
        still_blocked = thread_b.is_alive()
    finally:
        release.set()
        thread_a.join(5)
    thread_b.join(5)
    assert not still_blocked, "a human takeover wait held the browser slot and blocked another bot"
    assert box_b["result"].ok


def test_ambiguous_selector_is_refused_not_resolved_to_the_first_match(config):
    page = _Page(selectors={".buy": ["Buy gift card", "Buy subscription"]})
    tool, ctx = _tool(page, config, "ambiguity", _Gate())
    result = tool.run({"action": "click", "selector": ".buy"}, ctx)
    assert not result.ok
    assert "2 elements" in result.output
    assert page.clicks == [], "an ambiguous click must not be dispatched to any element"
    assert result.data.get("ambiguous_matches") == 2
    assert ctx.gate.decisions == [], "no approval is requested for a target that is not uniquely identified"


def test_missing_target_asks_for_a_new_observation_instead_of_guessing(config):
    page = _Page(selectors={}, texts={})
    tool, ctx = _tool(page, config, "missing", _Gate())
    result = tool.run({"action": "click", "label": "Place order"}, ctx)
    assert not result.ok
    assert "no element" in result.output.lower()
    assert page.clicks == []


def test_exact_label_match_wins_over_a_substring_match(config):
    page = _Page(texts={("Save", False): ["Save draft", "Save"], ("Save", True): ["Save"]})
    tool, ctx = _tool(page, config, "exact-label", _Gate())
    result = tool.run({"action": "click", "label": "Save"}, ctx)
    assert result.ok, result.output
    assert page.clicks == ["Save"]


def test_two_exact_label_matches_are_refused(config):
    page = _Page(texts={("Delete", True): ["Delete", "Delete"], ("Delete", False): ["Delete", "Delete"]})
    tool, ctx = _tool(page, config, "two-exact", _Gate())
    result = tool.run({"action": "click", "label": "Delete"}, ctx)
    assert not result.ok and "2 elements" in result.output
    assert page.clicks == []
