"""Browser tool — optional Playwright automation with per-bot profiles.

Answers the documented browser-agent failures:
- Session expiry: each bot gets a PERSISTENT browser profile, so logins survive
  across runs instead of being re-harvested by hand.
- One desktop: browser contexts are serialized behind a global lock — two bots
  never fight over one GUI.
- CAPTCHA/MFA walls: navigating to a login/captcha challenge emits a
  pause_to_human event; with a human watching the dashboard they finish the
  challenge and the bot continues. The bot never solves challenges itself.

Requires the optional extra:  pip install "hutch[browser]"
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from ..models import Event, EventType
from ..approvals import DeniedError
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

# One browser automation at a time on a single desktop.
_GLOBAL_BROWSER_LOCK = threading.Lock()

_LOGIN_WALL_RE = ("captcha", "are you a robot", "sign in", "log in", "two-factor",
                  "verification code", "one-time code", "authenticate")

_ACTIONS = {
    "goto": "Navigate to a URL (public http/https).",
    "read": "Read the page's visible text.",
    "click": "Click an element by CSS selector or its accessible/text name.",
    "type": "Type text into a form field identified by CSS selector.",
    "screenshot": "Save a screenshot of the current page into the workspace.",
    "wait": "Wait for a CSS selector (or seconds) to appear.",
}


class BrowserUnavailable(Exception):
    pass


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Automate a real (Chromium) browser in this bot's own persistent profile. "
        "Actions: " + "; ".join(f"{k} — {v}" for k, v in _ACTIONS.items())
    )
    parameters = _schema(
        ["action"],
        {
            "action": {"type": "string", "enum": list(_ACTIONS)},
            "url": {"type": "string", "description": "for goto"},
            "selector": {"type": "string", "description": "CSS selector for click/type/wait"},
            "text": {"type": "string", "description": "text to type, for type"},
            "label": {"type": "string", "description": "accessible/text name for click"},
            "seconds": {"type": "number", "description": "for wait without selector"},
        },
    )

    _pw = None
    _browser = None

    def _ensure(self, ctx: ToolContext):
        if BrowserTool._browser is not None:
            return BrowserTool._browser
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserUnavailable()
        BrowserTool._pw = sync_playwright().start()
        profile_dir = ctx.config.bot_profiles_dir(ctx.bot.name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        BrowserTool._browser = BrowserTool._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=ctx.headless,
            accept_downloads=True,
        )
        # every request the page makes (navigation, redirect, sub-resource) is judged by the same rules as web_fetch
        from ..netguard import RequestGuard
        BrowserTool._browser.route("**/*", RequestGuard().route_handler(
            lambda url, why: ctx.emit and ctx.emit(Event(run_id=ctx.run.id, type=EventType.log,
                                                         data={"denied": url, "reason": why, "rule": "deny:private-address"}))))
        ctx.on_finish.append(self._teardown)
        return BrowserTool._browser

    @staticmethod
    def _teardown():
        if BrowserTool._browser is not None:
            try:
                BrowserTool._browser.close()
            finally:
                BrowserTool._browser = None
        if BrowserTool._pw is not None:
            try:
                BrowserTool._pw.stop()
            finally:
                BrowserTool._pw = None

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        action = (args.get("action") or "").strip()
        if action not in _ACTIONS:
            return ToolResult(ok=False, output=f"error: unknown action '{action}'")

        if ctx.dry_run and action in ("click", "type", "screenshot"):
            # a click or keystroke can submit a form, send a message or buy something; a screenshot writes a file
            return rehearsed(f"browser {action} {args.get('selector') or args.get('label') or ''}".strip())
        # Policy gates per action class
        if action == "goto":
            url = (args.get("url") or "").strip()
            decision = ctx.policy.check_url(url)
        else:
            decision = None
        try:
            with _GLOBAL_BROWSER_LOCK:
                return self._run_locked(action, args, ctx, decision)
        except (BrowserUnavailable, DeniedError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        except Exception as exc:  # playwright errors are runtime-dependent
            return ToolResult(ok=False, output=f"browser error: {exc}")

    def _run_locked(self, action: str, args: dict[str, Any], ctx: ToolContext, decision) -> ToolResult:
        browser = self._ensure(ctx)
        pages = browser.pages
        page = pages[0] if pages else browser.new_page()

        if action == "goto":
            url = (args.get("url") or "").strip()
            ctx.gate.decide("browser", f"open {url}", {"url": url}, decision)
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            title = page.title()
            body_sample = page.inner_text("body")[:500].lower()
            walls = [w for w in _LOGIN_WALL_RE if w in body_sample]
            if walls:
                # Park the run for a human instead of barrelling on: the person clears the wall in
                # the bot's own browser profile, presses Resume, and the session persists (UI-1).
                ctx.gate.wait_for_human(f"login/CAPTCHA wall at {url} ({', '.join(walls)})", url)
                page.reload(wait_until="domcontentloaded")
                title = page.title()
            return ToolResult(ok=True, output=f"opened {url}\ntitle: {title}", data={"url": url})

        if action == "read":
            text = page.inner_text("body")
            return ToolResult(ok=True, output=clip(text), data={"url": page.url})

        if action == "click":
            target = args.get("selector") or args.get("label") or ""
            ctx.gate.decide("browser", f"click {target or '(current focus)'}", {"target": target})
            locator = page.locator(args["selector"]) if args.get("selector") else page.get_by_text(args.get("label", ""), exact=False)
            locator.first.click(timeout=10_000)
            return ToolResult(ok=True, output=f"clicked {target}", data={"url": page.url})

        if action == "type":
            selector, text = args.get("selector", ""), args.get("text", "")
            ctx.gate.decide("browser", f"type into {selector}", {"selector": selector})
            page.fill(selector, text, timeout=10_000)
            return ToolResult(ok=True, output=f"typed {len(text)} chars into {selector}")

        if action == "screenshot":
            path = ctx.workspace / f"screenshot-{int(time.time())}.png"
            page.screenshot(path=str(path))
            return ToolResult(ok=True, output=f"saved {path.name}")

        if action == "wait":
            if args.get("selector"):
                page.wait_for_selector(args["selector"], timeout=15_000)
                return ToolResult(ok=True, output=f"selector appeared: {args['selector']}")
            seconds = min(float(args.get("seconds") or 1), 30)
            page.wait_for_timeout(int(seconds * 1000))
            return ToolResult(ok=True, output=f"waited {seconds}s")

        return ToolResult(ok=False, output=f"unhandled action {action}")  # pragma: no cover
