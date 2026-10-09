"""Browser tool — optional Playwright automation with per-bot profiles.

Answers the documented browser-agent failures:
- Session expiry: each bot gets a PERSISTENT browser profile, so logins survive
  across runs instead of being re-harvested by hand.
- One desktop: browser contexts are serialized behind a global lock — two bots
  never fight over one GUI; OS file leases extend ownership across worker processes.
- CAPTCHA/MFA walls: navigating to a login/captcha challenge emits a
  pause_to_human event only when this bot has opted into a visible local
  desktop browser. Headless runs report that no handoff exists; the bot never
  solves challenges itself.

Requires the optional extra:  pip install "hutch[browser]"
"""

from __future__ import annotations

import os
import hashlib
import hmac
import re
import secrets
import stat
import sys
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import fcntl
except ImportError:  # pragma: no cover - browser execution is Linux-first
    fcntl = None

from ..models import Event, EventType
from ..approvals import DeniedError
from ..browser_proxy import PinnedBrowserProxy
from ..netguard import display_url_origin
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

# One browser automation at a time per process. OS file leases extend profile
# and visible-desktop ownership across run worker processes. Contexts are
# instance-owned so a bot cannot inherit another bot's cookies or page.
_GLOBAL_BROWSER_LOCK = threading.Lock()

_LOGIN_WALL_RE = ("captcha", "are you a robot", "are you human", "sign in to continue", "log in to continue",
                  "two-factor", "verification code", "one-time code", "verify your identity",
                  "security check", "human verification", "authenticator app", "security code",
                  "confirm your purchase", "confirm payment", "payment confirmation", "accept cookies to continue",
                  "consent required", "touch your security key", "scan the qr code")
_SENSITIVE_FIELD_RE = re.compile(
    r"(?:password|passcode|one[-_ ]?time[-_ ]?code|verification[-_ ]?code|security[-_ ]?code|"
    r"recovery[-_ ]?code|authenticator|\botp\b|\btotp\b|\bpin\b|\bcvv\b|\bcvc\b|"
    r"card[-_ ]?number|client[-_ ]?secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token)",
    re.IGNORECASE,
)
_SENSITIVE_FIELD_JS = r"""els => els.some(el => {
  const autocomplete = (el.getAttribute('autocomplete') || '').trim().toLowerCase();
  const labelText = el.labels ? Array.from(el.labels).map(label => label.innerText || '').join(' ') : '';
  const metadata = [el.type, autocomplete, el.name, el.id, el.getAttribute('aria-label'),
    el.getAttribute('placeholder'), el.getAttribute('data-testid'), labelText].filter(Boolean).join(' ');
  return String(el.type || '').toLowerCase() === 'password' ||
    ['current-password','new-password','one-time-code','cc-number','cc-csc','cc-exp',
     'cc-exp-month','cc-exp-year'].includes(autocomplete) ||
    /(?:password|passcode|one[-_ ]?time[-_ ]?code|verification[-_ ]?code|security[-_ ]?code|recovery[-_ ]?code|authenticator|\botp\b|\btotp\b|\bpin\b|\bcvv\b|\bcvc\b|card[-_ ]?number|client[-_ ]?secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token)/i.test(metadata);
})"""
_VISIBLE_SENSITIVE_FIELD_JS = r"""() => {
  const visible = el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const nodes = Array.from(document.querySelectorAll('input,textarea')).filter(visible);
  return nodes.some(el => {
    const autocomplete = (el.getAttribute('autocomplete') || '').trim().toLowerCase();
    const labelText = el.labels ? Array.from(el.labels).map(label => label.innerText || '').join(' ') : '';
    const metadata = [el.type, autocomplete, el.name, el.id, el.getAttribute('aria-label'),
      el.getAttribute('placeholder'), el.getAttribute('data-testid'), labelText].filter(Boolean).join(' ');
    return String(el.type || '').toLowerCase() === 'password' ||
      ['current-password','new-password','one-time-code','cc-number','cc-csc','cc-exp',
       'cc-exp-month','cc-exp-year'].includes(autocomplete) ||
      /(?:password|passcode|one[-_ ]?time[-_ ]?code|verification[-_ ]?code|security[-_ ]?code|recovery[-_ ]?code|authenticator|\botp\b|\btotp\b|\bpin\b|\bcvv\b|\bcvc\b|card[-_ ]?number|client[-_ ]?secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token)/i.test(metadata);
  });
}"""
_URL_SECRET_KEY_RE = re.compile(
    r"(?:token|secret|password|credential|auth|code|state|otp|ticket|assertion|session|key)", re.I
)
_APPROVAL_FINGERPRINT_KEY = secrets.token_bytes(32)

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


def _redact_sensitive_url(url: str) -> str:
    """Keep navigable public URL context without persisting common URL credentials."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname or ""
        if not hostname:
            return "[redacted URL]"
        # URL userinfo is rejected by the browser proxy, but arguments are
        # recorded before navigation policy runs. Strip it at that earlier
        # persistence boundary too.
        netloc = f"[{hostname}]" if ":" in hostname else hostname
        if parts.port is not None:
            netloc += f":{parts.port}"
        query = urlencode([
            (key, "[redacted]" if _URL_SECRET_KEY_RE.search(key) else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ])
        return urlunsplit((parts.scheme, netloc, parts.path, query, ""))
    except (TypeError, ValueError):
        return "[redacted URL]"


def local_handoff_status() -> tuple[bool, str]:
    """Whether a visible same-session browser can be opened on this host."""
    if sys.platform != "linux":
        return False, "Local browser handoff currently requires Linux."
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False, "No desktop display is available to open a visible browser window."
    if fcntl is None:
        return False, "This host does not provide the file locks needed to own a browser profile."
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False, 'Install Hutch with the browser extra: `pip install "hutch[browser]"`.'
    return True, "A visible browser can stay open while Hutch waits for you to complete the step."


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

    def __init__(self, *, resolver=None, connector=None):
        self._pw = None
        self._browser = None
        self._proxy: Optional[PinnedBrowserProxy] = None
        self._lease_fds: list[int] = []
        self._resolver = resolver
        self._connector = connector

    @staticmethod
    def _lock(path, label: str) -> int:
        if fcntl is None:
            raise BrowserUnavailable("Browser handoff needs Linux advisory file locks")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = None
        try:
            fd = os.open(path, flags, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise BrowserUnavailable(f"{label} lock is not a private file owned by this user")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError as exc:
            if fd is not None:
                os.close(fd)
            raise BrowserUnavailable(f"{label} is already in use by another Hutch run; stop or wait for that run") from exc
        except BrowserUnavailable:
            if fd is not None:
                os.close(fd)
            raise
        except OSError as exc:
            if fd is not None:
                os.close(fd)
            raise BrowserUnavailable(f"could not acquire {label}: {exc}") from exc

    def _acquire_leases(self, ctx: ToolContext, profile_dir) -> None:
        paths = []
        if not ctx.headless:
            paths.append((ctx.config.state_dir / "browser-desktop.lock", "the local browser handoff"))
        paths.append((profile_dir.parent / "browser-profile.lock", "this bot's browser profile"))
        try:
            for path, label in paths:
                self._lease_fds.append(self._lock(path, label))
        except Exception:
            self._release_leases()
            raise

    def _release_leases(self) -> None:
        errors = []
        while self._lease_fds:
            fd = self._lease_fds.pop()
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as exc:
                errors.append(exc)
            finally:
                try:
                    os.close(fd)
                except OSError as exc:
                    errors.append(exc)
        if errors:
            raise BrowserUnavailable(f"could not release browser ownership lease: {errors[0]}") from errors[0]

    def _ensure(self, ctx: ToolContext):
        if self._browser is not None:
            return self._browser
        if not ctx.headless:
            available, reason = local_handoff_status()
            if not available:
                raise BrowserUnavailable(reason)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserUnavailable()
        profile_dir = ctx.config.bot_profiles_dir(ctx.bot.name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_leases(ctx, profile_dir)
        try:
            self._proxy = PinnedBrowserProxy(
                resolver=self._resolver,
                connector=self._connector,
                on_block=lambda url, reason: ctx.emit(Event(
                    run_id=ctx.run.id, type=EventType.log,
                    data={"denied": url, "reason": reason, "rule": "deny:private-address"})),
            ).start()
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=ctx.headless,
                accept_downloads=True,
                # Chromium implicitly bypasses proxies for localhost/link-local destinations. Remove that exception so
                # the proxy remains the network boundary even if the early Playwright route policy changes.
                proxy={"server": self._proxy.url, "bypass": "<-loopback>"},
                args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                service_workers="block",
            )
            # The route check gives an early refusal; the loopback proxy independently resolves, validates and pins connections.
            from ..netguard import RequestGuard
            self._browser.route("**/*", RequestGuard(self._resolver).route_handler(
                lambda url, why: ctx.emit and ctx.emit(Event(run_id=ctx.run.id, type=EventType.log,
                                                             data={"denied": display_url_origin(url), "reason": why,
                                                                   "rule": "deny:private-address"}))))
        except Exception as exc:
            cleanup = ""
            try:
                self._teardown()
            except Exception as cleanup_exc:
                cleanup = f"; browser cleanup also failed: {cleanup_exc}"
            if not ctx.headless:
                raise BrowserUnavailable(f"could not open the visible browser window: {exc}{cleanup}") from exc
            raise BrowserUnavailable(f"could not initialize the browser: {exc}{cleanup}") from exc
        ctx.on_finish.append(self._teardown)
        return self._browser

    def _teardown(self):
        errors = []
        browser, self._browser = self._browser, None
        playwright, self._pw = self._pw, None
        proxy, self._proxy = self._proxy, None
        try:
            if browser is not None:
                try:
                    browser.close()
                except Exception as exc:
                    errors.append(exc)
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception as exc:
                    errors.append(exc)
            if proxy is not None:
                try:
                    proxy.close()
                except Exception as exc:
                    errors.append(exc)
        finally:
            try:
                self._release_leases()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise BrowserUnavailable(f"browser cleanup incomplete: {errors[0]}") from errors[0]

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        action = (args.get("action") or "").strip()
        return {"click": "web", "type": "web", "screenshot": "fs"}.get(action, "")

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Persist a reviewable call without persisting typed values or URL credentials."""
        action = (args.get("action") or "").strip()
        if action == "type":
            recorded = {"action": "type", "selector": args.get("selector", ""),
                        "text": "[redacted]", "text_redacted": True}
            # Different form entries must not collapse onto one action key;
            # the opaque reference contains no recoverable input data.
            recorded["value_ref"] = secrets.token_hex(12)
            return recorded
        recorded = {key: args[key] for key in ("action", "url", "selector", "label", "seconds") if key in args}
        if action == "goto" and isinstance(recorded.get("url"), str):
            recorded["url"] = _redact_sensitive_url(recorded["url"])
        return recorded

    @staticmethod
    def _is_sensitive_target(page, selector: str) -> bool:
        if not selector or _SENSITIVE_FIELD_RE.search(selector):
            return True
        try:
            matched = page.locator(selector).evaluate_all(_SENSITIVE_FIELD_JS)
        except Exception:
            # A selector that cannot be safely inspected must not receive text.
            return True
        return matched is not False

    @staticmethod
    def _page_has_sensitive_fields(page) -> bool:
        try:
            return page.evaluate(_VISIBLE_SENSITIVE_FIELD_JS) is not False
        except Exception:
            # Do not capture a page if this browser implementation cannot
            # establish that visible credential fields are absent.
            return True

    @staticmethod
    def _human_challenge_markers(page, body_sample: str) -> list[str]:
        markers = [marker for marker in _LOGIN_WALL_RE if marker in body_sample]
        try:
            frames = getattr(page, "frames", ())
            if any(re.search(r"captcha|recaptcha|turnstile|challenge", str(getattr(frame, "url", "")), re.I)
                   for frame in frames[1:]):
                markers.append("challenge frame")
        except Exception:
            pass
        return markers

    @staticmethod
    def _sensitive_entry_result(page, ctx: ToolContext) -> ToolResult:
        current_url = getattr(page, "url", "")
        origin = display_url_origin(current_url) or "the current page"
        if ctx.headless or not ctx.bot.local_browser_handoff:
            return ToolResult(
                ok=False,
                output=("error: Hutch did not enter or save that value. This field appears to contain a password, "
                        "passcode, payment credential, or verification code. Enable Local browser handoff on a Linux "
                        "desktop, then enter it directly in the visible browser; do not send it in chat."),
                data={"sensitive_input_blocked": True, "handoff_available": False, "origin": origin},
            )
        ctx.gate.wait_for_human(
            f"A password, passcode, or other sensitive field needs you at {origin}; Hutch will not type or save its value.",
            _redact_sensitive_url(current_url),
            handoff=("Automation is paused. Check the site and enter the password, passcode, payment detail, or "
                     "verification code directly in this visible Hutch browser window. Do not put it in chat. "
                     "Hutch will not include the value in chat events, approvals, action receipts, or screenshots. "
                     "Finish the step, then resume; this page will stay open."),
        )
        return ToolResult(
            ok=False,
            output=("error: Hutch did not type the sensitive value. The human browser step has returned; continue only "
                    "with non-sensitive actions or ask the operator to finish the form directly."),
            data={"sensitive_input_blocked": True, "handoff_available": True, "origin": origin},
        )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        args = dict(args)  # a human wait must not resume from a mutable caller argument object
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
            recorded_url = _redact_sensitive_url(url)
            ctx.gate.decide("browser", f"open {display_url_origin(url)}", {"url": recorded_url}, decision)
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            title = page.title()
            body_sample = page.inner_text("body")[:500].lower()
            walls = self._human_challenge_markers(page, body_sample)
            sensitive_fields = self._page_has_sensitive_fields(page)
            if walls or sensitive_fields:
                if ctx.headless:
                    subject = "a login, CAPTCHA or verification step" if walls else "a password or other sensitive field"
                    return ToolResult(
                        ok=False,
                        output=(f"error: the page contains {subject}, but this bot's browser is headless. Enable Local "
                                "browser handoff in the bot settings on a Linux desktop. Complete the step in the visible "
                                "browser; Hutch does not solve challenges or type secrets."),
                        data={"handoff_available": False, "url": recorded_url},
                    )
                origin = display_url_origin(page.url)
                reason = (f"Human verification is needed at {origin}: complete the login, CAPTCHA, identity check, "
                          "two-factor prompt, or sensitive form field in the visible Hutch browser.")
                handoff = ("Automation is paused in this bot's browser. Check the site, complete the human step in this "
                           "same window, then resume. Hutch will not solve or bypass challenges, and it will not reload "
                           "the page when control returns, so unsaved form state stays in place.")
                # After every explicit resume, inspect the same live page. Do
                # not reload away entered form values. If the challenge remains,
                # keep automation paused until it clears.
                if sensitive_fields or walls:
                    ctx.gate.wait_for_human(reason, _redact_sensitive_url(page.url), handoff=handoff)
                    title = page.title()
                    body_sample = page.inner_text("body")[:500].lower()
                    walls = self._human_challenge_markers(page, body_sample)
                while walls:
                    ctx.gate.wait_for_human(
                        reason, _redact_sensitive_url(page.url), handoff=handoff,
                    )
                    title = page.title()
                    body_sample = page.inner_text("body")[:500].lower()
                    walls = self._human_challenge_markers(page, body_sample)
            return ToolResult(ok=True, output=f"opened {display_url_origin(url)}\ntitle: {title}", data={"url": recorded_url})

        if action == "read":
            text = page.inner_text("body")
            return ToolResult(ok=True, output=clip(text), data={"url": page.url})

        if action == "click":
            target = args.get("selector") or args.get("label") or ""
            url = page.url
            ctx.gate.decide("browser", f"click {target or '(current focus)'}", {
                "action": action, "selector": args.get("selector", ""), "label": args.get("label", ""),
                "url": url, "profile_bot_id": ctx.bot.id}, outward=True)
            if page.url != url:
                return ToolResult(ok=False, output="error: browser navigated after review; request a new approval")
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
            locator = page.locator(args["selector"]) if args.get("selector") else page.get_by_text(args.get("label", ""), exact=False)
            locator.first.click(timeout=10_000)
            return ToolResult(ok=True, output=f"clicked {target}", data={"url": page.url})

        if action == "type":
            selector, text = args.get("selector", ""), args.get("text", "")
            if self._is_sensitive_target(page, selector):
                return self._sensitive_entry_result(page, ctx)
            url = page.url
            ctx.gate.decide("browser", f"type into {selector}", {
                "action": action, "selector": selector, "text": "[redacted]", "text_chars": len(text),
                "value_fingerprint": hmac.new(_APPROVAL_FINGERPRINT_KEY, text.encode("utf-8"), hashlib.sha256).hexdigest(),
                "url": _redact_sensitive_url(url),
                "profile_bot_id": ctx.bot.id}, outward=True)
            if page.url != url:
                return ToolResult(ok=False, output="error: browser navigated after review; request a new approval")
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
            page.fill(selector, text, timeout=10_000)
            return ToolResult(ok=True, output=f"typed {len(text)} chars into {selector}")

        if action == "screenshot":
            if self._page_has_sensitive_fields(page):
                return ToolResult(ok=False, output=("error: Hutch did not save a screenshot because a visible password, "
                                                    "payment credential, or verification field is on this page"),
                                  data={"screenshot_blocked_sensitive_fields": True})
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
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
