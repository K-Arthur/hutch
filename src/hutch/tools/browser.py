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
import json
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
_CLICK_SNAPSHOT_JS = r"""async function() {
  const source = this && this.nodeType === 1 ? this : this && this.parentElement;
  if (!source) return {error: 'browser target could not be resolved'};
  const control = source.closest('button, input[type=submit], input[type=image], input[type=button], a') || source;
  const form = control.form || control.closest('form');
  const tag = String(control.tagName || '').toLowerCase();
  const type = String(control.type || control.getAttribute('type') || '').toLowerCase();
  const sensitive = /(?:password|passcode|one[-_ ]?time[-_ ]?code|verification[-_ ]?code|security[-_ ]?code|recovery[-_ ]?code|authenticator|\botp\b|\btotp\b|\bpin\b|\bcvv\b|\bcvc\b|card[-_ ]?number|client[-_ ]?secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token)/i;
  const visible = field => {
    const rect = field.getBoundingClientRect();
    const style = getComputedStyle(field);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const fields = form ? Array.from(form.elements).filter(field => {
    const fieldType = String(field.type || '').toLowerCase();
    return field.matches('input,textarea,select') && 'value' in field &&
      !['submit','reset','button','image'].includes(fieldType);
  }).slice(0, 129).map(field => {
    const fieldType = String(field.type || '').toLowerCase();
    const label = field.labels ? Array.from(field.labels).map(item => item.innerText || '').join(' ') : '';
    const metadata = [fieldType, field.name, field.id, field.getAttribute('autocomplete'), field.getAttribute('placeholder'),
      field.getAttribute('aria-label'), label].filter(Boolean).join(' ');
    const name = String(field.name || field.id || '').slice(0, 120);
    const displayLabel = String(label || field.getAttribute('aria-label') || field.getAttribute('placeholder') || name || fieldType)
      .replace(/\s+/g, ' ').trim().slice(0, 120);
    if (fieldType === 'file') return {name, label: displayLabel, type: fieldType, visible: visible(field), selected: Boolean(field.files && field.files.length)};
    const value = field.matches('select[multiple]')
      ? Array.from(field.selectedOptions).map(option => option.value)
      : String(field.value || '');
    return {name, label: displayLabel, type: fieldType, visible: visible(field), sensitive: sensitive.test(metadata), value,
      checked: ['checkbox','radio'].includes(fieldType) ? Boolean(field.checked) : undefined};
  }) : [];
  const label = control.getAttribute('aria-label') || control.innerText || control.value || control.title || '';
  const target = {
    tag, type,
    label: String(label).replace(/\s+/g, ' ').trim().slice(0, 200),
    destination: control.href ? (() => { const url = new URL(control.href, location.href); return url.origin + url.pathname; })() : '',
    form: form ? {action: control.formAction || form.action || location.href,
      method: String(control.formMethod || form.method || 'get').toLowerCase(), enctype: control.formEnctype || form.enctype,
      target: control.formTarget || form.target, noValidate: Boolean(control.formNoValidate || form.noValidate),
      submitter: {name: String(control.name || ''), value: String(control.value || ''),
        noValidate: Boolean(control.formNoValidate)}, fields} : null
  };
  if (fields.length > 128 || fields.some(field => field.type !== 'file' && JSON.stringify(field.value || '').length > 16384))
    return {error: 'form fields exceed the safe review limit; action was not performed'};
  const raw = JSON.stringify({target, fields});
  if (raw.length > 65536) return {error: 'form fields exceed the safe review limit; action was not performed'};
  let fingerprint = '';
  if (window.crypto && window.crypto.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
    fingerprint = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  } else if (form) {
    return {error: 'secure browser form review is unavailable on this page'};
  }
  const safeFields = fields.filter(field => field.visible).map(field => ({label: field.label, type: field.type,
    ...(field.sensitive ? {sensitive: true, present: String(field.value || '').length > 0} : {}),
    ...(field.type === 'file' ? {selected: field.selected} : {})}));
  return {target: {tag, type, label: target.label, destination: target.destination,
    form: form ? {destination: new URL(target.form.action, location.href).origin,
      method: target.form.method, fields: safeFields} : null}, fingerprint};
}"""
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
    def _click_review_snapshot(page, locator) -> tuple[dict[str, Any], str]:
        """Return safe approval details plus a page-computed binding to live form state."""
        session = None
        try:
            locator.scroll_into_view_if_needed(timeout=5_000)
            box = locator.bounding_box()
            if not box or box["width"] <= 0 or box["height"] <= 0:
                raise BrowserUnavailable("browser target is not visible; action was not performed")
            session = page.context.new_cdp_session(page)
            session.send("DOM.enable")
            session.send("Page.enable")
            node = session.send("DOM.getNodeForLocation", {
                "x": int(box["x"] + box["width"] / 2),
                "y": int(box["y"] + box["height"] / 2),
                "includeUserAgentShadowDOM": True,
            })
            frame_id = node.get("frameId") or session.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
            world = session.send("Page.createIsolatedWorld", {
                "frameId": frame_id, "worldName": f"hutch-review-{secrets.token_hex(8)}",
                "grantUniversalAccess": False,
            })
            resolved = session.send("DOM.resolveNode", {
                "backendNodeId": node["backendNodeId"], "executionContextId": world["executionContextId"],
            })
            evaluated = session.send("Runtime.callFunctionOn", {
                "objectId": resolved["object"]["objectId"], "functionDeclaration": _CLICK_SNAPSHOT_JS,
                "awaitPromise": True, "returnByValue": True,
            })
            if evaluated.get("exceptionDetails"):
                raise BrowserUnavailable("cannot safely inspect the browser target; action was not performed")
            snapshot = evaluated.get("result", {}).get("value")
        except Exception as exc:
            if isinstance(exc, BrowserUnavailable):
                raise
            raise BrowserUnavailable("cannot safely inspect the browser target; action was not performed") from exc
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
        if not isinstance(snapshot, dict) or snapshot.get("error"):
            message = snapshot.get("error") if isinstance(snapshot, dict) else ""
            raise BrowserUnavailable(message or "browser target is too large to review safely; action was not performed")
        target_snapshot = snapshot.get("target")
        fingerprint = snapshot.get("fingerprint", "")
        if not isinstance(target_snapshot, dict) or not isinstance(fingerprint, str):
            raise BrowserUnavailable("browser target could not be bound to the approval; action was not performed")
        form = target_snapshot.get("form") if isinstance(target_snapshot.get("form"), dict) else None
        fields = form.get("fields", []) if form else []
        if form and (not isinstance(fields, list) or len(fields) > 128):
            raise BrowserUnavailable("form fields exceed the safe review limit; action was not performed")
        if fingerprint and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise BrowserUnavailable("browser target could not be bound to the approval; action was not performed")
        if form and not fingerprint:
            raise BrowserUnavailable("secure browser form review is unavailable on this page")
        target_kind = "form_submit" if form and (
            target_snapshot.get("tag") == "button" and target_snapshot.get("type") in ("", "submit") or
            target_snapshot.get("tag") == "input" and target_snapshot.get("type") in {"submit", "image"}
        ) else "element"
        target = {
            "kind": target_kind,
            "label": str(target_snapshot.get("label", ""))[:200],
            "tag": str(target_snapshot.get("tag", ""))[:24],
            "type": str(target_snapshot.get("type", ""))[:24],
        }
        if form:
            target["method"] = str(form.get("method", "get"))[:12]
            target["destination"] = str(form.get("destination", "")) or "unknown destination"
            target["fields"] = fields
        elif target_snapshot.get("destination"):
            target["destination"] = str(target_snapshot["destination"])
        # Form-value digests are computed in the page and wrapped before they
        # can enter an approval record. Ordinary targets contain no field
        # values, so their safe description can be fingerprinted here too.
        binding = fingerprint or json.dumps(target_snapshot, sort_keys=True, separators=(",", ":"))
        keyed = hmac.new(_APPROVAL_FINGERPRINT_KEY, binding.encode("utf-8"), hashlib.sha256).hexdigest()
        return {"target_kind": target_kind, "target": target, "target_fingerprint": keyed}, keyed

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
    def _await_human_challenge(page, ctx: ToolContext, *, completed_action: str = "") -> ToolResult | None:
        """Pause before continuing when a challenge appears after any browser action.

        Sites can reveal bot checks asynchronously or after a click. Reinspect the
        same page after every explicit resume; never read or act through a challenge
        simply because the initial navigation was clean.
        """
        try:
            body_sample = page.inner_text("body")[:8192].lower()
            markers = BrowserTool._human_challenge_markers(page, body_sample)
        except Exception:
            note = f" The {completed_action} already happened; do not repeat it until the destination is checked." if completed_action else " No further action was taken."
            return ToolResult(False, "error: Hutch could not verify the browser page state." + note,
                              {"page_state_unverified": True, "action_completed": bool(completed_action)})
        if not markers:
            return None

        current_url = getattr(page, "url", "")
        origin = display_url_origin(current_url) or "the current page"
        if ctx.headless or not ctx.bot.local_browser_handoff:
            completed = f" The {completed_action} already happened; check the site before deciding whether to try again." if completed_action else ""
            return ToolResult(
                False,
                (f"error: a login, CAPTCHA, identity check, or verification step is active at {origin}, but this run "
                 "has no visible human handoff. Hutch did not continue. Enable Local browser handoff on a Linux desktop "
                 "and start the task again; Hutch does not solve or bypass challenges." + completed),
                {"handoff_available": False, "url": _redact_sensitive_url(current_url),
                 "action_completed": bool(completed_action)},
            )

        reason = (f"Human verification is needed at {origin}: complete the login, CAPTCHA, identity check, or "
                  "two-factor prompt in the visible Hutch browser.")
        handoff = ("Automation is paused in this bot's browser. Check the site and complete the human step in this same "
                   "window, then resume. Hutch will not solve or bypass challenges, and it will not reload the page.")
        while markers:
            ctx.gate.wait_for_human(reason, _redact_sensitive_url(getattr(page, "url", "")), handoff=handoff)
            try:
                body_sample = page.inner_text("body")[:8192].lower()
                markers = BrowserTool._human_challenge_markers(page, body_sample)
            except Exception:
                note = f" The {completed_action} already happened; verify the site before retrying." if completed_action else ""
                return ToolResult(False, "error: Hutch could not verify the browser page after your resume; automation remains stopped." + note,
                                  {"page_state_unverified": True, "action_completed": bool(completed_action)})
        return None

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

    @staticmethod
    def _new_sensitive_field_result(page, ctx: ToolContext, *, had_sensitive_fields: bool,
                                   completed_action: str) -> ToolResult | None:
        """Hand off when an action or wait reveals a sensitive field on the live page."""
        if had_sensitive_fields or not BrowserTool._page_has_sensitive_fields(page):
            return None
        result = BrowserTool._sensitive_entry_result(page, ctx)
        result.data["sensitive_field_revealed"] = True
        result.data["action_completed"] = True
        if completed_action == "click":
            result.output += " The click already happened and revealed the field; verify the page before retrying."
        elif completed_action == "text entry":
            result.output += " The text entry already happened and revealed the field; verify the page before retrying."
        elif completed_action == "wait":
            result.output += " The wait completed and a sensitive field appeared; inspect the page before continuing."
        return result

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
            checkpoint = self._await_human_challenge(page, ctx, completed_action="navigation")
            if checkpoint:
                return checkpoint
            title = page.title()
            sensitive_fields = self._page_has_sensitive_fields(page)
            if sensitive_fields:
                if ctx.headless or not ctx.bot.local_browser_handoff:
                    return ToolResult(
                        ok=False,
                        output=("error: the page contains a password or other sensitive field, but this run has no visible "
                                "human handoff. Enable Local browser handoff in the bot settings on a Linux desktop. "
                                "Complete the step in the visible browser; Hutch does not solve challenges or type secrets."),
                        data={"handoff_available": False, "url": recorded_url},
                    )
                origin = display_url_origin(page.url)
                ctx.gate.wait_for_human(
                    f"A password, passcode, or other sensitive field needs you at {origin}; Hutch will not type or save its value.",
                    _redact_sensitive_url(page.url),
                    handoff=("Automation is paused in this bot's browser. Check the site, enter the value yourself in this "
                             "same visible window, and finish the step. Hutch will not type or save it."),
                )
                checkpoint = self._await_human_challenge(page, ctx)
                if checkpoint:
                    return checkpoint
                title = page.title()
            return ToolResult(ok=True, output=f"opened {display_url_origin(url)}\ntitle: {title}", data={"url": recorded_url})

        if action != "type":
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint

        if action == "read":
            text = page.inner_text("body")
            return ToolResult(ok=True, output=clip(text), data={"url": page.url})

        if action == "click":
            target = args.get("selector") or args.get("label") or ""
            locator = page.locator(args["selector"]) if args.get("selector") else page.get_by_text(args.get("label", ""), exact=False)
            locator = locator.first
            try:
                reviewed_target, reviewed_fingerprint = self._click_review_snapshot(page, locator)
            except BrowserUnavailable as exc:
                return ToolResult(ok=False, output=f"error: {exc}")
            if reviewed_target["target_kind"] == "form_submit" and any(
                field.get("type") == "file" and field.get("selected") for field in reviewed_target["target"].get("fields", [])
            ):
                return ToolResult(ok=False, output=("error: Hutch cannot submit an attached file because its contents "
                                                     "are not available for this approval review"))
            url = page.url
            target_detail = reviewed_target["target"]
            if reviewed_target["target_kind"] == "form_submit":
                action_text = (f"submit form to {target_detail.get('destination', 'unknown destination')} "
                               f"({target_detail.get('method', 'get').upper()}) with {target_detail.get('label') or target or 'submit control'}")
            else:
                action_text = f"click {target or '(current focus)'}"
            ctx.gate.decide("browser", action_text, {
                "action": action, "selector": args.get("selector", ""), "label": args.get("label", ""),
                "url": _redact_sensitive_url(url), "profile_bot_id": ctx.bot.id,
                "target_kind": reviewed_target["target_kind"], "target": target_detail,
                "target_fingerprint": reviewed_fingerprint}, outward=True)
            if page.url != url:
                return ToolResult(ok=False, output="error: browser navigated after review; request a new approval")
            try:
                _, current_fingerprint = self._click_review_snapshot(page, locator)
            except BrowserUnavailable as exc:
                return ToolResult(ok=False, output=f"error: {exc}")
            if not hmac.compare_digest(reviewed_fingerprint, current_fingerprint):
                return ToolResult(ok=False, output="error: browser target or form changed after review; request a new approval")
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
            had_sensitive_fields = self._page_has_sensitive_fields(page)
            locator.click(timeout=10_000)
            checkpoint = self._await_human_challenge(page, ctx, completed_action="click")
            if checkpoint:
                return checkpoint
            sensitive = self._new_sensitive_field_result(
                page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="click")
            if sensitive:
                return sensitive
            return ToolResult(ok=True, output=f"clicked {target}", data={"url": page.url})

        if action == "type":
            selector, text = args.get("selector", ""), args.get("text", "")
            if self._is_sensitive_target(page, selector):
                return self._sensitive_entry_result(page, ctx)
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint
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
            had_sensitive_fields = self._page_has_sensitive_fields(page)
            page.fill(selector, text, timeout=10_000)
            checkpoint = self._await_human_challenge(page, ctx, completed_action="text entry")
            if checkpoint:
                return checkpoint
            sensitive = self._new_sensitive_field_result(
                page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="text entry")
            if sensitive:
                return sensitive
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
                had_sensitive_fields = self._page_has_sensitive_fields(page)
                page.wait_for_selector(args["selector"], timeout=15_000)
                checkpoint = self._await_human_challenge(page, ctx)
                if checkpoint:
                    return checkpoint
                sensitive = self._new_sensitive_field_result(
                    page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="wait")
                if sensitive:
                    return sensitive
                return ToolResult(ok=True, output=f"selector appeared: {args['selector']}")
            seconds = min(float(args.get("seconds") or 1), 30)
            had_sensitive_fields = self._page_has_sensitive_fields(page)
            page.wait_for_timeout(int(seconds * 1000))
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint
            sensitive = self._new_sensitive_field_result(
                page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="wait")
            if sensitive:
                return sensitive
            return ToolResult(ok=True, output=f"waited {seconds}s")

        return ToolResult(ok=False, output=f"unhandled action {action}")  # pragma: no cover
