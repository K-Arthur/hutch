"""Browser tool — optional Playwright automation with per-bot profiles.

What it guarantees (see docs/computer-use.md):
- Session expiry: each bot gets a PERSISTENT browser profile, so logins survive across runs instead of being re-harvested
  by hand. A profile has exactly one writer (an OS file lease across worker processes); contexts are instance-owned, so a bot
  never inherits another bot's cookies, tabs or pages.
- Waiting is not driving: a bounded driver slot covers browser work only, and is released while a call waits for an approval
  or for a person, so one bot's pending decision never freezes another bot's browser.
- Targets are identified, not guessed: zero or several matching elements are refused; tabs have stable ids; coordinates are
  only accepted against the latest observation frame.
- CAPTCHA/MFA walls: a login/challenge page parks the run in ``waiting_human`` only when this bot has opted into a visible
  local desktop browser. Headless runs report that no handoff exists; the bot never solves challenges itself.
- Stop works while a call is hung: a run-cancel hook ends the browser driver's process tree from outside the owning thread.

Requires the optional extra:  pip install "hutch[browser]"
"""

from __future__ import annotations

import contextlib
import datetime
import os
import hashlib
import hmac
import json
import math
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

from .. import procguard
from ..models import Event, EventType
from ..approvals import DeniedError
from ..safety import Decision, Verdict
from ..browser_proxy import PinnedBrowserProxy
from ..computer.control import ControlLease, StaleControl
from ..computer.frames import FrameError, FrameStore
from ..netguard import LocalAccess, LocalOrigins, dashboard_ports, display_url_origin
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

class _DriverSlot:
    """Bounds concurrent live browser driver calls in this process.

    The slot covers *driver work only*. Waiting for an approval or for a person to finish a login
    step is not driver work, so those waits release the slot (``released``) and re-take it
    afterwards; otherwise one bot's pending approval would freeze every other bot's browser for
    the whole approval TTL. OS file leases still extend profile and visible-desktop ownership
    across worker processes, and contexts stay instance-owned so a bot cannot inherit another
    bot's cookies or page. Acquisition polls for a stop request so a queued call cannot outlive
    its run.
    """

    POLL_SECONDS = 0.25

    def __init__(self, limit: int):
        self._sem = threading.BoundedSemaphore(limit)
        self._local = threading.local()

    def _held(self) -> bool:
        return bool(getattr(self._local, "held", 0))

    def _take(self, cancelled: Optional[Callable[[], bool]]) -> None:
        while not self._sem.acquire(timeout=self.POLL_SECONDS):
            if cancelled is not None and cancelled():
                raise DeniedError("run was stopped while waiting for the browser")
        self._local.held = 1

    def _give(self) -> None:
        self._local.held = 0
        self._sem.release()

    @contextlib.contextmanager
    def acquire(self, cancelled: Optional[Callable[[], bool]] = None):
        if self._held():                       # re-entrant within one driver call
            yield
            return
        self._take(cancelled)
        try:
            yield
        finally:
            if self._held():
                self._give()

    @contextlib.contextmanager
    def released(self, cancelled: Optional[Callable[[], bool]] = None):
        """Give the slot up for a human/approval wait; retake it (stop-aware) before driver work resumes."""
        if not self._held():
            yield
            return
        self._give()
        try:
            yield
        finally:
            self._take(cancelled)


def _slot_limit() -> int:
    try:
        value = int(os.environ.get("HUTCH_BROWSER_MAX_ACTIVE", "1"))
    except ValueError:
        value = 1
    return min(max(value, 1), 8)


_DRIVER_SLOT = _DriverSlot(_slot_limit())


def _cancelled_probe(ctx) -> Optional[Callable[[], bool]]:
    gate = getattr(ctx, "gate", None)
    probe = getattr(gate, "cancelled", None)
    return probe if callable(probe) else None


#: control leases by run id (one browser session per run). Module-level so the static page helpers that only receive
#: ``ctx`` can mark a human takeover without an instance.
_LEASES: dict[str, ControlLease] = {}


def _lease_for(ctx) -> Optional[ControlLease]:
    run = getattr(ctx, "run", None)
    return _LEASES.get(getattr(run, "id", ""))


def _wait_for_human(ctx, reason: str, url: str = "", handoff: str = "") -> None:
    """Park for a person without holding the driver slot (see ``_DriverSlot``), and mark who controls the surface."""
    lease = _lease_for(ctx)
    if lease is not None:
        lease.take_over("waiting for a person: " + reason[:120])
    with _DRIVER_SLOT.released(_cancelled_probe(ctx)):
        if getattr(ctx, "computer_sessions", []):
            from ..computer.human import pump
            ctx.gate.wait_for_human(reason, url, handoff=handoff, service=lambda: pump(ctx))
        else:
            ctx.gate.wait_for_human(reason, url, handoff=handoff)
    if lease is not None:
        lease.hand_back("the person resumed the run")
        # The action in progress re-reads the live page after this point; give it the new generation.
        lease.action_ticket = lease.begin_action()


def _decide(ctx, *args, **kwargs) -> None:
    """Ask the approval gate without holding the driver slot while a person decides."""
    with _DRIVER_SLOT.released(_cancelled_probe(ctx)):
        ctx.gate.decide(*args, **kwargs)

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
  const shadowHost = source.getRootNode && source.getRootNode().host;
  const control = shadowHost && shadowHost.matches('input[type=file]') ? shadowHost :
    source.closest('button, input[type=submit], input[type=image], input[type=button], a') || source;
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
  }).slice(0, 129) : [];
  if (fields.length > 128) return {error: "form fields exceed the safe review limit"};
  const allFiles = fields.filter(field => String(field.type || '').toLowerCase() === 'file')
    .flatMap(field => Array.from(field.files || []));
  if (allFiles.length > 1 || allFiles.reduce((sum, file) => sum + file.size, 0) > 4000000)
    return {error: 'form file selections exceed the one-file / 4 MB review limit'};
  const described = await Promise.all(fields.map(async field => {
    const fieldType = String(field.type || '').toLowerCase();
    const label = field.labels ? Array.from(field.labels).map(item => item.innerText || '').join(' ') : '';
    const metadata = [fieldType, field.name, field.id, field.getAttribute('autocomplete'), field.getAttribute('placeholder'),
      field.getAttribute('aria-label'), label].filter(Boolean).join(' ');
    const name = String(field.name || field.id || '').slice(0, 120);
    const displayLabel = String(label || field.getAttribute('aria-label') || field.getAttribute('placeholder') || name || fieldType)
      .replace(/\s+/g, ' ').trim().slice(0, 120);
    if (fieldType === 'file') {
      const files = Array.from(field.files || []);
      if (files.length > 1 || files.some(file => file.size > 4000000)) throw new Error('file selection exceeds transfer limit');
      const selected = await Promise.all(files.map(async file => {
        if (!crypto.subtle) throw new Error('secure file review unavailable');
        const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
        return {name: file.name, bytes: file.size, sha256: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2,'0')).join('')};
      }));
      return {name, label: displayLabel, type: fieldType, visible: visible(field), selected: files.length > 0, files: selected};
    }
    const value = field.matches('select[multiple]')
      ? Array.from(field.selectedOptions).map(option => option.value)
      : String(field.value || '');
    return {name, label: displayLabel, type: fieldType, visible: visible(field), sensitive: sensitive.test(metadata), value,
      checked: ['checkbox','radio'].includes(fieldType) ? Boolean(field.checked) : undefined};
  }));
  const label = control.getAttribute('aria-label') || control.innerText || control.value || control.title || '';
  const target = {
    tag, type,
    label: String(label).replace(/\s+/g, ' ').trim().slice(0, 200),
    destination: control.href ? (() => { const url = new URL(control.href, location.href); return url.origin + url.pathname; })() : '',
    form: form ? {action: control.hasAttribute('formaction') ? control.formAction : form.action || location.href,
      method: String(control.hasAttribute('formmethod') ? control.formMethod : form.method || 'get').toLowerCase(),
      enctype: control.hasAttribute('formenctype') ? control.formEnctype : form.enctype,
      target: control.hasAttribute('formtarget') ? control.formTarget : form.target,
      noValidate: Boolean(control.formNoValidate || form.noValidate),
      submitter: {name: String(control.name || ''), value: String(control.value || ''),
        noValidate: Boolean(control.formNoValidate)}, fields: described} : null
  };
  if (fields.length > 128 || described.some(field => field.type !== 'file' && JSON.stringify(field.value || '').length > 16384))
    return {error: 'form fields exceed the safe review limit; action was not performed'};
  const raw = JSON.stringify({target, fields: described});
  if (raw.length > 65536) return {error: 'form fields exceed the safe review limit; action was not performed'};
  let fingerprint = '';
  if (window.crypto && window.crypto.subtle) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
    fingerprint = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  } else if (form) {
    return {error: 'secure browser form review is unavailable on this page'};
  }
  const safeFields = described.filter(field => field.visible || field.type === 'file').map(field => ({label: field.label, type: field.type,
    ...(field.sensitive ? {sensitive: true, present: String(field.value || '').length > 0} : {}),
    ...(field.type === 'file' ? {selected: field.selected, files: field.files} : {})}));
  return {context_url: location.href, target: {tag, type, label: target.label, destination: target.destination,
    form: form ? {destination: new URL(target.form.action, location.href).origin + new URL(target.form.action, location.href).pathname,
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
_MAX_CANDIDATES = 5
_MAX_OBSERVED_ELEMENTS = 60
# Bounded, value-free listing of what a person could act on. Field *values* are never read (a field may hold a
# secret); labels, roles, states and a stable selector hint are enough to choose a target.
_OBSERVE_JS = r"""(limit) => {
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const sensitiveRe = /(password|passcode|one[-_ ]?time|verification|security[-_ ]?code|recovery|authenticator|\botp\b|\btotp\b|\bpin\b|\bcvv\b|\bcvc\b|card[-_ ]?number|secret|api[-_ ]?key|token)/i;
  const nodes = Array.from(document.querySelectorAll(
    'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=tab],[role=menuitem],[contenteditable=""],[contenteditable=true]'));
  const items = []; let total = 0;
  for (const el of nodes) {
    if (!visible(el)) continue;
    total++;
    if (items.length >= limit) continue;
    const tag = el.tagName.toLowerCase(); const type = String(el.type || '').toLowerCase();
    const labelled = el.labels && el.labels.length ? Array.from(el.labels).map(l => l.innerText).join(' ') : '';
    const label = labelled || el.getAttribute('aria-label') || (['button', 'submit', 'reset'].includes(type) ? el.value : '') ||
      el.innerText || el.getAttribute('placeholder') || el.getAttribute('title') || '';
    const meta = [type, el.name, el.id, el.getAttribute('autocomplete'), label].join(' ');
    const hint = el.id ? '#' + CSS.escape(el.id)
      : (el.getAttribute('data-testid') ? '[data-testid="' + CSS.escape(el.getAttribute('data-testid')) + '"]'
      : (el.name ? tag + '[name="' + CSS.escape(el.name) + '"]' : ''));
    items.push({tag, type, role: el.getAttribute('role') || '', name: String(label).replace(/\s+/g, ' ').trim().slice(0, 60),
      disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      sensitive: type === 'password' || sensitiveRe.test(meta), hint});
  }
  return {items, total, truncated: total > items.length, title: String(document.title || '').slice(0, 120),
    width: window.innerWidth, height: window.innerHeight, scrollX: Math.round(window.scrollX),
    scrollY: Math.round(window.scrollY), dpr: window.devicePixelRatio};
}"""
# Describes one candidate for disambiguation. Input values are never read (a field may hold a secret); only
# button-like controls contribute their value, as their label.
_DESCRIBE_TARGET_JS = r"""el => {
  const tag = String(el.tagName || '').toLowerCase();
  const type = String(el.type || '').toLowerCase();
  const buttonLike = tag === 'input' && ['button', 'submit', 'reset'].includes(type);
  const text = String(el.getAttribute('aria-label') || (buttonLike ? el.value : el.innerText) || '')
    .replace(/\s+/g, ' ').trim().slice(0, 80);
  return {tag, type, role: String(el.getAttribute('role') || ''), text,
          name: String(el.name || el.id || '').slice(0, 60)};
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
    "screenshot": "Capture the current page as a bounded private frame (alias of observe).",
    "upload": "Select one reviewed UTF-8 workspace file (at most 4 MB) in a visible file input. May transmit immediately.",
    "download": "Click a reviewed same-origin direct HTTP text download into a new workspace path (at most 4 MB).",
    "wait": "Wait for a CSS selector (or seconds) to appear.",
    "tabs": "List open tabs and which is active; pass tab=<id> on any action to act on another tab.",
    "observe": ("Capture the active tab as a bounded image frame plus an observation record: frame id, viewport, "
                "freshness and the visible interactive elements. Nothing is written to the workspace."),
    "click_at": ("Click at pixel (x, y) of a frame returned by observe, for canvases and other targets with no "
                 "accessible name. Requires that frame's frame_id; refused if the page changed since it."),
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
            "selector": {"type": "string", "description": "CSS selector for click/type/wait/upload/download"},
            "frame": {"type": "string", "description": "optional unique CSS selector of an owned iframe; actions stay in that frame"},
            "path": {"type": "string", "description": "workspace-relative UTF-8 file for upload/download (.txt/.md/.csv/.json)"},
            "text": {"type": "string", "description": "text to type, for type"},
            "label": {"type": "string", "description": "accessible/text name for click"},
            "seconds": {"type": "number", "description": "for wait without selector"},
            "tab": {"type": "string", "description": "tab id from an earlier result; defaults to the active tab"},
            "frame_id": {"type": "string", "description": "for click_at: the frame_id from the latest observe"},
            "x": {"type": "number", "description": "for click_at: horizontal pixel in that frame"},
            "y": {"type": "number", "description": "for click_at: vertical pixel in that frame"},
        },
    )

    def __init__(self, *, resolver=None, connector=None):
        self._pw = None
        self._browser = None
        self._proxy: Optional[PinnedBrowserProxy] = None
        self._local_access: Optional[LocalAccess] = None
        self._lease_fds: list[int] = []
        self._resolver = resolver
        self._connector = connector
        # Tab identity: stable ids per page object, the active tab, and a one-shot notice when the active
        # tab changed implicitly (a popup opened, or the tab we were using closed).
        self._tab_lock = threading.Lock()
        self._tabs: dict[str, Any] = {}
        self._tab_seq = 0
        self._active_tab = ""
        self._tab_notice = ""
        self._tab_listener_for: Any = None
        # Emergency stop: the automation driver process(es) this tool started, and whether stop was requested.
        self._driver_procs: list[Any] = []
        self._stopped = False
        self._owner_thread: Optional[int] = None    # sync Playwright objects must stay on the thread that launched them
        self._lease: Optional[ControlLease] = None
        self._last_observation: dict[str, Any] = {}    # what coordinates are valid against (see click_at)
        self._upload_grants: dict[tuple, float] = {}
        self._transfer_bytes = 0
        self._transfer_count = 0
        self._ctx = None
        self._budget = None
        self._budget_reason = ""

    # ------------------------------------------------------- emergency stop

    @staticmethod
    def _is_automation_driver(pid: int) -> bool:
        args = procguard.cmdline(pid)
        return "run-driver" in args and any("playwright" in part.lower() for part in args[:2])

    def _emergency_stop(self) -> None:
        """Registered as a run cancel hook; it runs on the supervisor thread, not the thread that owns the driver.

        Sync Playwright objects must not be touched from another thread, and a call stuck in a hung navigation or capture
        never returns to check a flag. Ending the driver's process tree from outside is thread-safe and model-independent:
        the stuck call then fails at once, and nothing in this browser can act again.
        """
        self._stopped = True
        if self._lease is not None:
            self._lease.request_stop("emergency stop")      # fence first: nothing queued may dispatch from now on
        survivors = 0
        for root in list(self._driver_procs):
            try:
                survivors += len(procguard.end_tree(root))
            except Exception:
                survivors += 1                               # could not verify: treat as unconfirmed
        if self._lease is not None:
            self._lease.confirm_stopped(survivors)

    # ---------------------------------------------------------------- tabs

    def _tab_id_of(self, page) -> str:
        for tab_id, known in self._tabs.items():
            if known is page:
                return tab_id
        return ""

    def _register_page(self, page, *, follow: bool = False) -> str:
        with self._tab_lock:
            existing = self._tab_id_of(page)
            if existing:
                return existing
            self._tab_seq += 1
            tab_id = f"t{self._tab_seq}"
            self._tabs[tab_id] = page
            if follow and self._active_tab:
                self._active_tab = tab_id
                self._tab_notice = (f"a new tab opened and is now the active tab ({tab_id}); the previous tab is "
                                    "still open - pass tab=<id> to return to it")
            elif not self._active_tab:
                self._active_tab = tab_id
            return tab_id

    def _on_new_page(self, page) -> None:
        try:
            opener = page.opener()
        except Exception:
            opener = None
        active = self._tabs.get(self._active_tab)
        self._register_page(page, follow=opener is None or opener is active)

    @staticmethod
    def _is_open(page) -> bool:
        closed = getattr(page, "is_closed", None)
        try:
            return not (callable(closed) and closed())
        except Exception:
            return False

    def _current_page(self, browser, requested: str = ""):
        """Resolve the page an action runs on: the requested tab, else the active one, never "whatever is first"."""
        if self._tab_listener_for is not browser:
            self._tab_listener_for = browser
            self._tabs, self._tab_seq, self._active_tab = {}, 0, ""
            on = getattr(browser, "on", None)
            if callable(on):
                try:
                    on("page", self._on_new_page)
                except Exception:
                    pass  # pages are still discovered below on every call
        # Playwright delivers page events only when its channel is next serviced. One cheap round trip on the
        # tab we were using makes a popup that opened since the last action visible before a target is chosen.
        known = self._tabs.get(self._active_tab)
        if known is not None and self._is_open(known):
            try:
                known.evaluate("0")
            except Exception:
                pass
        for page in list(getattr(browser, "pages", ()) or ()):
            if self._is_open(page):
                self._register_page(page)
        with self._tab_lock:
            for tab_id in [t for t, p in self._tabs.items() if not self._is_open(p)]:
                del self._tabs[tab_id]
                if tab_id == self._active_tab:
                    self._active_tab = ""
                    self._tab_notice = f"the active tab ({tab_id}) was closed"
            if requested:
                if requested not in self._tabs:
                    return None, ToolResult(
                        False, f"error: there is no open tab {requested!r}; open tabs: {sorted(self._tabs)}. "
                               "Nothing was done.", {"tabs": sorted(self._tabs)})
                if requested != self._active_tab:
                    self._active_tab = requested
                    self._tab_notice = f"switched to tab {requested}"
            if self._active_tab not in self._tabs and self._tabs:
                self._active_tab = list(self._tabs)[-1]
                self._tab_notice = (self._tab_notice + "; " if self._tab_notice else "") + \
                    f"now using tab {self._active_tab}"
        if not self._tabs:
            page = browser.new_page()
            self._register_page(page)
            self._active_tab = self._tab_id_of(page)
        return self._tabs[self._active_tab], None

    def _annotate_tabs(self, result: ToolResult) -> ToolResult:
        with self._tab_lock:
            active, notice = self._active_tab, self._tab_notice
            self._tab_notice = ""
            listing = []
            for tab_id, page in self._tabs.items():
                try:
                    origin = display_url_origin(getattr(page, "url", "")) or ""
                except Exception:
                    origin = ""
                listing.append({"id": tab_id, "active": tab_id == active, "origin": origin})
        if active:
            result.data.setdefault("tab", active)
        if self._lease is not None:
            result.data.setdefault("control", self._lease.snapshot().public())
        if len(listing) > 1 or notice:
            result.data["tabs"] = listing
        if notice:
            result.data["tab_changed"] = True
            result.output = f"{result.output}\n[{notice}]" if result.output else f"[{notice}]"
        return result

    @staticmethod
    def _local_origins(ctx) -> LocalOrigins:
        approved = LocalOrigins.lenient(getattr(getattr(ctx, "bot", None), "local_dev_origins", ()) or ())
        return approved.without_ports(dashboard_ports())      # never Hutch's own approval/settings screens

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
        profile_dir = ctx.config.browser_profile_dir(ctx.bot.id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        from ..computer.budgets import profile_usage
        profile_usage(profile_dir)
        self._acquire_leases(ctx, profile_dir)
        try:
            local_origins = self._local_origins(ctx)
            self._local_access = LocalAccess(local_origins)
            self._proxy = PinnedBrowserProxy(
                resolver=self._resolver,
                connector=self._connector,
                on_block=lambda url, reason: ctx.emit(Event(
                    run_id=ctx.run.id, type=EventType.log,
                    data={"denied": url, "reason": reason, "rule": "deny:private-address"})),
                local_access=self._local_access,
            ).start()
            self._owner_thread = threading.get_ident()
            known_children = {p.pid for p in procguard.children(os.getpid())}
            self._pw = sync_playwright().start()
            self._driver_procs = [p for p in procguard.children(os.getpid())
                                  if p.pid not in known_children and self._is_automation_driver(p.pid)]
            hooks = getattr(ctx, "cancel_hooks", None)
            if hooks is not None and self._emergency_stop not in hooks:
                hooks.append(self._emergency_stop)
            self._browser = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=ctx.headless,
                accept_downloads=False,  # managed bounded transfers only; no unreviewed Chromium download spool
                # Chromium implicitly bypasses proxies for localhost/link-local destinations. Remove that exception so
                # the proxy remains the network boundary even if the early Playwright route policy changes.
                proxy={"server": self._proxy.url, "bypass": "<-loopback>"},
                args=["--force-webrtc-ip-handling-policy=disable_non_proxied_udp", "--disk-cache-size=4194304", "--media-cache-size=4194304"],
                service_workers="block",
            )
            # The route check gives an early refusal; the loopback proxy independently resolves, validates and pins connections.
            from ..netguard import RequestGuard
            self._browser.route("**/*", RequestGuard(self._resolver, local_origins=local_origins).route_handler(
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
        run_id = getattr(getattr(ctx, "run", None), "id", "")
        emit = getattr(ctx, "emit", None)

        def announce(snap) -> None:
            if emit is not None and run_id:
                emit(Event(run_id=run_id, type=EventType.log,
                           data={"kind": "computer_control", "surface": "browser", **snap.public()}))

        self._lease = ControlLease(f"{run_id}:browser", on_change=announce)
        ctx.computer_leases = getattr(ctx, "computer_leases", []) + [self._lease]
        self._lease.action_ticket = None
        if run_id:
            _LEASES[run_id] = self._lease
        if getattr(ctx.bot, "remote_computer_access", "off") == "control":
            from ..computer.human import HumanSession
            self._human = HumanSession(ctx, "browser", self._lease, self._human_capture, self._human_dispatch)
        from ..computer.budgets import BrowserBudget
        from ..computer.resources import authority
        def budget_stop(reason):
            self._budget_reason = reason
            self._emergency_stop()
        self._budget = BrowserBudget(profile_dir, self._driver_procs, lambda: authority(ctx, "browser"), budget_stop)
        return self._browser

    def _human_identity(self):
        page = self._tabs.get(self._active_tab)
        if page is None or page.is_closed():
            raise BrowserUnavailable("the controlled tab is no longer open")
        return page, {"tab": self._active_tab, "url": page.url, "viewport": page.viewport_size,
                      "geometry": page.evaluate("() => [innerWidth, innerHeight, devicePixelRatio, scrollX, scrollY]")}

    def _human_capture(self):
        with _DRIVER_SLOT.acquire():
            page, identity = self._human_identity()
            # Human-only pixels are never stored in the run. Conventional sensitive fields are masked too.
            masks = [frame.locator('input[type="password"], input[autocomplete="one-time-code"], input[autocomplete="cc-number"], input[autocomplete="cc-csc"]') for frame in page.frames]
            return page.screenshot(type="png", scale="css", mask=masks), identity

    def _human_dispatch(self, command, expected, check):
        with _DRIVER_SLOT.acquire():
            page, identity = self._human_identity()
            if identity != expected:
                from ..computer.human import HumanError
                raise HumanError("tab, URL or geometry changed; capture again before input")
            check()
            if command["action"] == "click":
                page.mouse.click(command["x"], command["y"])
            elif command["action"] == "type":
                page.keyboard.insert_text(command["text"])
            elif command["action"] == "key":
                key = command["keys"].lower().replace("ctrl+", "Control+").replace("shift+", "Shift+")
                parts = key.split("+")
                parts[-1] = {"enter": "Enter", "escape": "Escape", "tab": "Tab", "backspace": "Backspace",
                             "delete": "Delete", "left": "ArrowLeft", "right": "ArrowRight", "up": "ArrowUp",
                             "down": "ArrowDown", "home": "Home", "end": "End"}.get(parts[-1], parts[-1])
                page.keyboard.press("+".join(parts))

    def _teardown(self):
        if self._budget is not None:
            self._budget.close()
            self._budget = None
        errors = []
        if getattr(self, "_human", None) is not None:
            self._human.close()
        stopped = self._stopped
        run_ids = [rid for rid, lease in _LEASES.items() if lease is self._lease]
        for rid in run_ids:
            _LEASES.pop(rid, None)
        browser, self._browser = self._browser, None
        with self._tab_lock:
            self._tabs, self._active_tab, self._tab_notice, self._tab_listener_for = {}, "", "", None
        playwright, self._pw = self._pw, None
        proxy, self._proxy = self._proxy, None
        # Synchronous Playwright objects may only be driven from the thread that launched them. Cleanup can legitimately
        # arrive from another thread (a supervisor, or after the owner exited): then closing through the API is not
        # possible, so end the driver's process tree from outside instead of reporting a cleanup failure.
        same_thread = self._owner_thread in (None, threading.get_ident())
        try:
            if not same_thread:
                for root in list(self._driver_procs):
                    try:
                        if procguard.end_tree(root):
                            errors.append(BrowserUnavailable("a browser process could not be confirmed ended"))
                    except Exception as exc:
                        errors.append(exc)
            if browser is not None and same_thread:
                try:
                    browser.close()
                except Exception as exc:
                    errors.append(exc)
            if playwright is not None and same_thread:
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
        if errors and not stopped:       # after an emergency stop the driver is already gone: closing it fails by design
            raise BrowserUnavailable(f"browser cleanup incomplete: {errors[0]}") from errors[0]

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        action = (args.get("action") or "").strip()
        return {"click": "web", "click_at": "web", "type": "web", "upload": "web", "download": "fs"}.get(action, "")

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Persist a reviewable call without persisting typed values or URL credentials."""
        action = (args.get("action") or "").strip()
        if action == "type":
            recorded = {"action": "type", "selector": args.get("selector", ""), "frame": args.get("frame", ""), "tab": args.get("tab", ""),
                        "text": "[redacted]", "text_redacted": True}
            # Different form entries must not collapse onto one action key;
            # the opaque reference contains no recoverable input data.
            recorded["value_ref"] = secrets.token_hex(12)
            return recorded
        recorded = {key: args[key] for key in ("action", "url", "selector", "label", "seconds", "tab", "frame", "path", "frame_id", "x", "y")
                    if key in args}
        if action == "goto" and isinstance(recorded.get("url"), str):
            recorded["url"] = _redact_sensitive_url(recorded["url"])
        return recorded

    @staticmethod
    def _store_frame(ctx: ToolContext, png: Any) -> tuple[Any, str]:
        """Keep a capture as a bounded, verified frame. Returns ``(ImageRef | None, reason-if-not-kept)``."""
        if not isinstance(png, (bytes, bytearray)) or not png:
            return None, "the capture returned no image"
        try:
            store = FrameStore(ctx.config.run_dir(ctx.bot.name, ctx.run.id))
            return store.save(bytes(png), "image/png"), ""
        except (FrameError, OSError, ValueError) as exc:
            return None, str(exc)

    def _observe(self, page, ctx: ToolContext) -> ToolResult:
        """One bounded observation: frame + record. Refuses rather than capturing a page with visible secret fields."""
        tab = self._active_tab
        url = _redact_sensitive_url(getattr(page, "url", ""))
        if self._page_has_sensitive_fields(page):
            return ToolResult(
                False, ("error: Hutch did not capture this page because a visible password, payment or verification "
                        "field is on it. Use the visible browser handoff to complete that step."),
                {"observation": {"schema": 1, "surface": {"kind": "browser_tab", "id": tab, "url": url},
                                 "status": "blocked_sensitive"}})
        try:
            facts = page.evaluate(_OBSERVE_JS, _MAX_OBSERVED_ELEMENTS)
        except Exception as exc:
            return ToolResult(False, f"error: the page could not be inspected ({exc}); it may still be loading",
                              {"observation": {"schema": 1, "surface": {"kind": "browser_tab", "id": tab, "url": url},
                                               "status": "unavailable"}})
        facts = facts if isinstance(facts, dict) else {}
        try:
            png = page.screenshot(type="png", scale="css")
        except Exception as exc:
            png = None
            capture_problem = f"capture failed: {exc}"
        else:
            capture_problem = ""
        ref, problem = self._store_frame(ctx, png) if png else (None, capture_problem or "no capture")
        elements = [e for e in facts.get("items", []) if isinstance(e, dict)][:_MAX_OBSERVED_ELEMENTS]
        record = {
            "schema": 1,
            "surface": {"kind": "browser_tab", "id": tab, "url": url,
                        "title": str(facts.get("title", ""))[:120]},
            "frame_id": ref.frame_id if ref else "",
            "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
            "monotonic_ms": round(time.monotonic() * 1000.0, 1),
            "viewport": {"css_width": facts.get("width"), "css_height": facts.get("height"),
                         "device_scale_factor": facts.get("dpr"), "scroll_x": facts.get("scrollX"),
                         "scroll_y": facts.get("scrollY")},
            "image": ref.public() if ref else None,
            # image pixels per CSS pixel; 1.0 for an uncropped css-scale capture
            "transform": {"scale": 1.0, "crop": None} if ref else None,
            "elements": len(elements), "elements_total": facts.get("total", len(elements)),
            "status": "fresh" if ref else "unavailable",
            "status_reason": "" if ref else problem,
        }
        lines = [f"observed tab {tab} {record['surface']['url']} \"{record['surface']['title']}\""]
        if ref:
            lines.append(f"frame {ref.frame_id} {ref.width}x{ref.height} viewport "
                         f"{facts.get('width')}x{facts.get('height')} scroll ({facts.get('scrollX')},{facts.get('scrollY')})")
        else:
            lines.append(f"no image frame: {problem}")
        lines.append(f"interactive elements ({len(elements)} of {record['elements_total']}):")
        for item in elements:
            kind = item.get("tag", "") + (f"[{item['type']}]" if item.get("type") else "")
            flags = (" disabled" if item.get("disabled") else "") + (" SENSITIVE(value hidden)" if item.get("sensitive") else "")
            lines.append(f"  - {kind} \"{item.get('name', '')}\"{flags} {item.get('hint', '')}".rstrip())
        data: dict[str, Any] = {"observation": record}
        if ref is not None:
            data["images"] = [ref.internal()]
            if self._lease is not None:
                self._lease.note_observation(ref.frame_id)
                self._last_observation = {"frame_id": ref.frame_id, "tab": tab, "url": getattr(page, "url", ""),
                                          "width": ref.width, "height": ref.height,
                                          "viewport": (facts.get("width"), facts.get("height"),
                                                       facts.get("scrollX"), facts.get("scrollY"))}
        return ToolResult(ok=True, output=clip("\n".join(lines), 8000), data=data)

    @staticmethod
    def _egress_block(response) -> str:
        """The reason, if the navigation ended on Hutch's own egress-block page; "" otherwise."""
        try:
            if response is None or not response.headers.get("x-hutch-egress-block"):
                return ""
            text = " ".join(response.text().split())
            return text.split("request:", 1)[-1].strip()[:240] or "the destination is not allowed"
        except Exception:
            return "the destination is not allowed"

    def _click_at(self, page, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """A pointer click at frame pixels. Coordinates are only meaningful against the frame they were read from, so the
        frame must still describe the live page; anything else is refused, never clamped or guessed onto another target."""
        def refuse(message: str, **data: Any) -> ToolResult:
            return ToolResult(False, f"error: {message}; nothing was clicked", {"dispatched": False,
                                                                                  "outcome": "not_dispatched", **data})

        observed = self._last_observation
        frame_id = str(args.get("frame_id") or "").strip()
        try:
            x, y = float(args["x"]), float(args["y"])
        except (KeyError, TypeError, ValueError):
            return refuse("click_at needs numeric x and y (pixels of the frame image)")
        if not (math.isfinite(x) and math.isfinite(y)):
            return refuse("x and y must be finite numbers")
        if not observed or observed.get("frame_id") != frame_id:
            return refuse(f"frame {frame_id or '(none given)'} is not the latest observation "
                          f"({observed.get('frame_id') or 'none yet'}); call observe and use its frame_id")
        if observed.get("tab") != self._active_tab:
            return refuse("the active tab changed since that frame; observe the active tab again")
        try:
            live = page.evaluate("[window.innerWidth, window.innerHeight, Math.round(window.scrollX), "
                                 "Math.round(window.scrollY)]")
        except Exception as exc:
            return refuse(f"the page geometry could not be read ({exc}); observe again")
        if tuple(live or ()) != tuple(observed.get("viewport") or ()) or getattr(page, "url", "") != observed.get("url"):
            self._stale("the page moved, resized or navigated")
            return refuse("the page was resized, scrolled or navigated since that frame; observe again")
        width, height = observed["width"], observed["height"]
        if not (0 <= x < width and 0 <= y < height):
            return refuse(f"({x:g}, {y:g}) is outside the {width}x{height} frame; coordinates are never clamped")
        css_x, css_y = x, y                      # captured with scale="css": image pixels are CSS pixels (scale 1.0)

        try:
            reviewed, fingerprint = self._click_review_snapshot(page, None, at=(css_x, css_y))
        except BrowserUnavailable as exc:
            return ToolResult(False, f"error: {exc}", {"dispatched": False, "outcome": "not_dispatched"})
        target = reviewed["target"]
        if reviewed["target_kind"] == "form_submit" and any(
                f.get("type") == "file" and f.get("selected") for f in target.get("fields", [])):
            return refuse("Hutch cannot submit an attached file because its contents are not available for review")
        url = page.url
        described = target.get("label") or target.get("tag") or "element"
        if reviewed["target_kind"] == "form_submit":
            action_text = (f"submit form to {target.get('destination', 'unknown destination')} "
                           f"({target.get('method', 'get').upper()}) by clicking at ({x:g}, {y:g})")
        else:
            action_text = f"click at ({x:g}, {y:g}) on {target.get('tag', 'element')} \"{described}\""
        _decide(ctx, "browser", action_text, {
            "action": "click_at", "frame_id": frame_id, "x": x, "y": y, "url": _redact_sensitive_url(url),
            "profile_bot_id": ctx.bot.id, "target_kind": reviewed["target_kind"], "target": target,
            "target_fingerprint": fingerprint}, outward=True)
        if page.url != url:
            return refuse("the browser navigated while the click was awaiting approval; request a new approval")
        try:
            _, current = self._click_review_snapshot(page, None, at=(css_x, css_y))
        except BrowserUnavailable as exc:
            return ToolResult(False, f"error: {exc}", {"dispatched": False, "outcome": "not_dispatched"})
        if not hmac.compare_digest(fingerprint, current):
            return refuse("the element under that point changed after review; observe again and request a new approval")
        if (blocked := ctx.begin_effect()):
            return ToolResult(False, f"error: {blocked}", {"dispatched": False, "outcome": "not_dispatched"})
        refused = self._fence(fresh=True)
        if refused is not None:
            return refused
        had_sensitive_fields = self._page_has_sensitive_fields(page)
        before_url = page.url
        page.mouse.click(css_x, css_y)
        self._stale("a click changed the page")
        self._settle(page)
        checkpoint = self._await_human_challenge(page, ctx, completed_action="click")
        if checkpoint:
            return checkpoint
        sensitive = self._new_sensitive_field_result(
            page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="click")
        if sensitive:
            return sensitive
        return ToolResult(True, f"clicked at ({x:g}, {y:g}) in frame {frame_id} on {target.get('tag', 'element')}",
                          {"url": page.url, "outcome": "dispatched", "page_changed": page.url != before_url,
                           "verification": "not_verifiable: observe the page to confirm the intended state"})

    def _fence(self, *, fresh: bool = False) -> Optional[ToolResult]:
        """Re-check, immediately before dispatching input, that this action still holds control. None = go ahead."""
        lease = self._lease
        if self._ctx is not None:
            from ..computer.resources import authority
            try:
                authority(self._ctx, "browser")
            except ValueError as exc:
                if lease is not None:
                    lease.pause(str(exc))
                return ToolResult(False, f"error: {exc}", {"outcome": "not_dispatched"})
        ticket = getattr(lease, "action_ticket", None) if lease is not None else None
        if lease is None or ticket is None:
            return None
        try:
            lease.check(ticket, needs_fresh_observation=fresh)
        except StaleControl as exc:
            return ToolResult(False, f"error: {exc.reason}",
                              {"dispatched": False, "outcome": "not_dispatched", "control": lease.snapshot().public()})
        return None

    def _stale(self, reason: str) -> None:
        if self._lease is not None:
            self._lease.invalidate_observation(reason)

    @staticmethod
    def _settle(page, milliseconds: int = 150) -> None:
        """Give a popup or new tab opened by the click time to be created and announced (page events are delivered
        when the driver channel is serviced), so this result and the next action see the same set of tabs."""
        waiter = getattr(page, "wait_for_timeout", None)
        if callable(waiter):
            try:
                waiter(milliseconds)
            except Exception:
                pass  # the page navigated or closed; the following checks report the state

    @staticmethod
    def _resolve_target(page, *, selector: str = "", label: str = "") -> tuple[Any, Optional[ToolResult]]:
        """Return ``(locator, None)`` only when exactly one element matches; otherwise a refusal.

        A name is looked up by exact text first and by substring only if nothing matches exactly. Zero or
        several matches are never resolved to "the first one": acting on a neighbouring field or the wrong
        of two ``Delete`` buttons is how an agent changes the wrong record. The refusal lists a bounded
        number of candidates so the model can choose a more specific selector.
        """
        described = selector or label
        if not described:
            return None, ToolResult(False, "error: this action needs a selector or a label; nothing was done",
                                    {"matches": 0})
        if selector:
            locator = page.locator(selector)
            count = locator.count()
        else:
            locator = page.get_by_text(label, exact=True)
            count = locator.count()
            if count == 0:
                locator = page.get_by_text(label, exact=False)
                count = locator.count()
        if count == 1:
            return locator, None
        if count == 0:
            return None, ToolResult(
                False,
                (f"error: no element matches {described!r}. The page may have changed; read it again and choose a "
                 "current target. Nothing was done."),
                {"matches": 0})
        candidates: list[Any] = []
        for index in range(min(count, _MAX_CANDIDATES)):
            try:
                candidates.append(locator.nth(index).evaluate(_DESCRIBE_TARGET_JS))
            except Exception:
                candidates.append({"unavailable": True})
        return None, ToolResult(
            False,
            (f"error: {count} elements match {described!r}; Hutch will not guess which one you mean. Use a more "
             "specific selector (for example an id, data-testid or a scoped CSS path). Nothing was done."),
            {"ambiguous_matches": count, "candidates": candidates})

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
            frames = getattr(page, "frames", None)
            return any(frame.evaluate(_VISIBLE_SENSITIVE_FIELD_JS) is not False for frame in frames) if frames else page.evaluate(_VISIBLE_SENSITIVE_FIELD_JS) is not False
        except Exception:
            # Do not capture a page if this browser implementation cannot
            # establish that visible credential fields are absent.
            return True

    @staticmethod
    def _click_review_snapshot(page, locator, at: Optional[tuple[float, float]] = None) -> tuple[dict[str, Any], str]:
        """Return safe approval details plus a page-computed binding to live form state.

        With ``at`` (CSS pixels) the element under that point is reviewed instead of a locator's centre; this is what a
        coordinate click will actually hit, overlays included."""
        session = None
        try:
            if at is None:
                locator.scroll_into_view_if_needed(timeout=5_000)
                box = locator.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    raise BrowserUnavailable("browser target is not visible; action was not performed")
                point = (int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))
            else:
                point = (int(at[0]), int(at[1]))
            session = page.context.new_cdp_session(page)
            session.send("DOM.enable")
            session.send("Page.enable")
            node = session.send("DOM.getNodeForLocation", {
                "x": point[0], "y": point[1],
                "includeUserAgentShadowDOM": True,
            })
            frame_id = node.get("frameId") or session.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
            world = session.send("Page.createIsolatedWorld", {
                # A stable name makes Chromium return the frame's existing isolated world instead of creating a new
                # JS context per reviewed click (measured: a unique name per call grew the browser ~0.5 MB per click).
                # Isolated worlds are not reachable from page scripts, so the name is not a secret.
                "frameId": frame_id, "worldName": "hutch-review",
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
        cookies = page.context.cookies([snapshot.get("context_url") or page.url])
        cookie_state = json.dumps(cookies, sort_keys=True, separators=(",", ":"))
        if len(cookies) > 128 or len(cookie_state) > 65536:
            raise BrowserUnavailable("account state exceeds the safe review limit; action was not performed")
        # The keyed binding contains account state; no cookie or usable digest enters review/log/model data.
        binding += cookie_state
        binding = f"{frame_id}:{node['backendNodeId']}:" + binding
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
        if (ctx.headless or not ctx.bot.local_browser_handoff) and getattr(ctx.bot, "remote_computer_access", "off") != "control":
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
            _wait_for_human(ctx, reason, _redact_sensitive_url(getattr(page, "url", "")), handoff=handoff)
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
        if (ctx.headless or not ctx.bot.local_browser_handoff) and getattr(ctx.bot, "remote_computer_access", "off") != "control":
            return ToolResult(
                ok=False,
                output=("error: Hutch did not enter or save that value. This field appears to contain a password, "
                        "passcode, payment credential, or verification code. Enable Local browser handoff on a Linux "
                        "desktop, then enter it directly in the visible browser; do not send it in chat."),
                data={"sensitive_input_blocked": True, "handoff_available": False, "origin": origin},
            )
        _wait_for_human(ctx,
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

    def _file_key(self, target: dict, file: dict) -> tuple:
        generation = self._lease.snapshot().generation if self._lease else 0
        return (self._active_tab, generation, target.get("destination"),
                file.get("name"), file.get("sha256"), file.get("bytes"))

    def _reviewed_files(self, target: dict) -> bool:
        for field in target.get("fields", []):
            if field.get("type") == "file" and field.get("selected"):
                files = field.get("files", [])
                if not files or any(self._upload_grants.get(self._file_key(target, file), 0) < time.monotonic()
                                    for file in files):
                    return False
        return True

    def _transfer(self, action: str, page, scope, args: dict, ctx) -> ToolResult:
        from .browser_files import (MAX_FILE_BYTES, MAX_TRANSFER_BYTES, MAX_TRANSFERS,
                                    read_upload, text_file)
        from .filewrite import destination, replace_reviewed, revision
        from ..runtime.steps import snapshot_workspace_file

        path = str(args.get("path") or "")
        try:
            if not path:
                raise ValueError("a browser transfer requires a workspace path")
            if self._transfer_count >= MAX_TRANSFERS or self._transfer_bytes + MAX_FILE_BYTES > MAX_TRANSFER_BYTES:
                raise ValueError("browser transfers exhausted this run's 8 file / 16 MB budget")
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint
            locator, refusal = self._resolve_target(scope, selector=str(args.get("selector") or ""))
            if refusal:
                return refusal
            reviewed, fingerprint = self._click_review_snapshot(page, locator)
            url, frame_url = page.url, scope.url
            detail = {"action": action, "selector": args.get("selector"), "frame": args.get("frame", ""),
                      "url": _redact_sensitive_url(url), "profile_bot_id": ctx.bot.id,
                      "target": reviewed["target"], "target_fingerprint": fingerprint}
            if action == "upload":
                if reviewed["target"].get("tag") != "input" or reviewed["target"].get("type") != "file":
                    raise ValueError("upload needs one visible file input; a native host file chooser is unsupported")
                data, source = read_upload(ctx, path)
                detail.update(file=source, consequence="the page may transmit this file immediately after selection")
            else:
                decision = ctx.policy.check_path(path, ctx.workspace, write=True)
                if decision.verdict.value == "deny":
                    raise ValueError(decision.reason)
                workspace, parts = destination(path, ctx.workspace)
                expected = revision(workspace, parts)
                if expected.get("exists"):
                    raise ValueError("download requires a new workspace file; overwriting an existing file is unsupported")
                text_file(path, b"")
                href = locator.evaluate("el => el.tagName === 'A' && (!el.target || el.target === '_self') ? el.href : ''")
                if not href or urlsplit(href).scheme != "http" or display_url_origin(href) != display_url_origin(frame_url) or display_url_origin(href) != display_url_origin(url):
                    raise ValueError("download needs a same-origin direct HTTP link; HTTPS, popups, redirects and blobs are unsupported")
                detail.update(path="/".join(parts), source=_redact_sensitive_url(href), max_bytes=MAX_FILE_BYTES,
                              source_fingerprint=hmac.new(_APPROVAL_FINGERPRINT_KEY, href.encode(), hashlib.sha256).hexdigest(),
                              consequence="one UI-initiated GET, bounded text artifact and new workspace file")
            _decide(ctx, "browser", f"{action} {path}", detail, outward=True, ask_in_auto=True)
            if page.url != url or scope.url != frame_url:
                raise ValueError("browser navigated after transfer review; request a new approval")
            _, current = self._click_review_snapshot(page, locator)
            if not hmac.compare_digest(fingerprint, current):
                raise ValueError("browser transfer target changed after review; request a new approval")

            def check():
                probe = _cancelled_probe(ctx)
                if probe and probe():
                    raise ValueError("run was stopped during transfer; inspect before retrying")
                refused = self._fence()
                if refused:
                    raise ValueError(refused.output)

            check()
            if action == "upload":
                fresh, source_now = read_upload(ctx, path)
                if source_now != source or fresh != data:
                    raise ValueError("upload source changed after review; request a new approval")
                if refusal := ctx.begin_effect():
                    raise ValueError(refusal)
                check()
                # Freeze bytes, rather than let Playwright reopen a mutable host path after approval.
                locator.set_input_files({"name": source["name"], "mimeType": source["mime_type"], "buffer": data}, timeout=5000)
                self._transfer_count += 1
                self._transfer_bytes += len(data)
                self._stale("a reviewed file was selected")
                selected, _ = self._click_review_snapshot(page, locator)
                files = [file for field in selected["target"].get("fields", []) for file in field.get("files", [])]
                proof = {key: source[key] for key in ("name", "sha256", "bytes")}
                if proof not in files:
                    return ToolResult(False, "error: file selection was dispatched but cannot be verified; inspect before retrying",
                                      {"outcome": "unknown"})
                self._upload_grants[self._file_key(selected["target"], proof)] = time.monotonic() + 120
                self._upload_grants = {key: expires for key, expires in self._upload_grants.items() if expires > time.monotonic()}
                return ToolResult(True, f"selected reviewed {source['name']} ({source['bytes']} bytes); service receipt still required",
                                  {"outcome": "effect_verified", "verification": "selected file bytes only",
                                   "transfer": {**proof, "path": source["path"], "destination": selected["target"].get("destination"),
                                                "profile_bot_id": ctx.bot.id}})

            if refusal := ctx.begin_effect():
                raise ValueError(refusal)
            with self._proxy.managed_download(href, frame_url, path, check) as captured:
                locator.click(timeout=10_000)
                deadline = time.monotonic() + 10
                while not captured.done.is_set() and time.monotonic() < deadline:
                    check()
                    page.wait_for_timeout(50)
                data, problem = captured.data, captured.error
            self._stale("a managed download was requested")
            if problem or data is None:
                raise ValueError(problem or "the UI did not issue a supported download; inspect before retrying")
            check()
            text, _ = text_file(path, data)
            ref = snapshot_workspace_file(ctx, path, text)
            replace_reviewed(workspace, parts, text, expected, lambda: (check() or None))
            self._transfer_count += 1
            self._transfer_bytes += len(data)
            return ToolResult(True, f"download verified: {ref['name']} ({ref['bytes']} bytes, SHA-256 {ref['sha256']})",
                              {"outcome": "effect_verified", "workspace_file": ref,
                               "transfer": {"source": _redact_sensitive_url(href), "profile_bot_id": ctx.bot.id,
                                            "modality": "ui_initiated_managed_download"}})
        except (ValueError, OSError, UnicodeError) as exc:
            return ToolResult(False, f"error: {exc}", {"outcome": "not_verified"})

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        args = dict(args)  # a human wait must not resume from a mutable caller argument object
        action = (args.get("action") or "").strip()
        if action not in _ACTIONS:
            return ToolResult(ok=False, output=f"error: unknown action '{action}'")

        if ctx.dry_run and action in ("click", "type", "upload", "download", "click_at"):
            # a click or keystroke can submit a form, send a message or buy something; a screenshot writes a file
            return rehearsed(f"browser {action} {args.get('selector') or args.get('label') or ''}".strip())
        # Policy gates per action class
        if action == "goto":
            url = (args.get("url") or "").strip()
            if self._local_origins(ctx).allows_url(url):
                # the person approved this exact local origin in the bot's settings; the approval is theirs, not the model's
                decision = Decision(Verdict.allow, "approved local development origin",
                                    rule="allow:local-dev-origin", risk="low")
            else:
                decision = ctx.policy.check_url(url)
        else:
            decision = None
        try:
            with _DRIVER_SLOT.acquire(_cancelled_probe(ctx)):
                return self._annotate_tabs(self._run_locked(action, args, ctx, decision))
        except (BrowserUnavailable, DeniedError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        except Exception as exc:  # playwright errors are runtime-dependent
            if self._stopped:
                return ToolResult(ok=False, output="error: the run was stopped; the browser was closed mid-action, so the "
                                                   "outcome of that action is unknown",
                                  data={"stopped": True, "outcome": "unknown"})
            return ToolResult(ok=False, output=f"browser error: {exc}")

    def _run_locked(self, action: str, args: dict[str, Any], ctx: ToolContext, decision) -> ToolResult:
        if self._stopped:
            return ToolResult(False, "error: " + (self._budget_reason or "this run was stopped and its browser was closed") + "; no further browser action runs")
        from ..computer.resources import authority
        authority(ctx, "browser")
        self._ctx = ctx
        browser = self._ensure(ctx)
        if self._owner_thread is not None and self._owner_thread != threading.get_ident():
            return ToolResult(False, ("error: this browser session belongs to another thread and cannot be driven from "
                                      "here (Playwright's synchronous API is thread-affine); nothing was done"),
                              {"thread_affinity": True})
        lease = self._lease
        if lease is not None:
            try:
                lease.action_ticket = lease.begin_action(needs_fresh_observation=action == "click_at")
            except StaleControl as exc:
                return ToolResult(False, f"error: {exc.reason}; nothing was done",
                                  {"control": lease.snapshot().public()})
        page, refusal = self._current_page(browser, str(args.get("tab") or "").strip())
        if refusal is not None:
            return refusal
        scope = page
        if args.get("frame"):
            if action not in {"read", "click", "type", "wait", "upload", "download"}:
                return ToolResult(False, "error: frame scope is supported for read/click/type/wait/upload/download only")
            iframe, refused = self._resolve_target(page, selector=str(args["frame"]))
            if refused:
                return refused
            handle = iframe.element_handle(timeout=2000)
            scope = handle.content_frame() if handle else None
            if scope is None:
                return ToolResult(False, "error: the selected iframe is unavailable; nothing was done")
        if action in {"upload", "download"}:
            return self._transfer(action, page, scope, args, ctx)
        if action == "tabs":
            with self._tab_lock:
                lines = [f"{'*' if tab_id == self._active_tab else ' '} {tab_id} "
                         f"{display_url_origin(getattr(p, 'url', '')) or '(blank)'}" for tab_id, p in self._tabs.items()]
            return ToolResult(ok=True, output="open tabs (* = active):\n" + "\n".join(lines))

        if action == "goto":
            url = (args.get("url") or "").strip()
            recorded_url = _redact_sensitive_url(url)
            _decide(ctx, "browser", f"open {display_url_origin(url)}", {"url": recorded_url}, decision)
            refused = self._fence()
            if refused is not None:
                return refused
            access = self._local_access
            # Only this deliberate navigation may reach an approved local origin without a local referrer (see LocalAccess).
            opened_permit = bool(access and access.permit_navigation(url))
            try:
                response = page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            finally:
                if opened_permit and access is not None:
                    access.clear_permit()
            self._stale("the page navigated")
            blocked = self._egress_block(response)
            if blocked:
                return ToolResult(False, f"error: Hutch's network controls blocked this navigation: {blocked}",
                                  {"egress_blocked": True, "url": recorded_url, "outcome": "failed"})
            checkpoint = self._await_human_challenge(page, ctx, completed_action="navigation")
            if checkpoint:
                return checkpoint
            title = page.title()
            sensitive_fields = self._page_has_sensitive_fields(page)
            if sensitive_fields:
                if (ctx.headless or not ctx.bot.local_browser_handoff) and getattr(ctx.bot, "remote_computer_access", "off") != "control":
                    return ToolResult(
                        ok=False,
                        output=("error: the page contains a password or other sensitive field, but this run has no visible "
                                "human handoff. Enable Local browser handoff in the bot settings on a Linux desktop. "
                                "Complete the step in the visible browser; Hutch does not solve challenges or type secrets."),
                        data={"handoff_available": False, "url": recorded_url},
                    )
                origin = display_url_origin(page.url)
                _wait_for_human(ctx,
                    f"A password, passcode, or other sensitive field needs you at {origin}; Hutch will not type or save its value.",
                    _redact_sensitive_url(page.url),
                    handoff=("Automation is paused in this bot's browser. Check the site, enter the value yourself in this "
                             "same visible window, and finish the step. Hutch will not type or save it."),
                )
                checkpoint = self._await_human_challenge(page, ctx)
                if checkpoint:
                    return checkpoint
                title = page.title()
            requested, landed = display_url_origin(url), display_url_origin(page.url)
            verified = requested == landed
            note = "" if verified else f"\n[the page redirected: now at {landed}]"
            return ToolResult(ok=True, output=f"opened {requested}\ntitle: {title}{note}",
                              data={"url": recorded_url, "outcome": "effect_verified" if verified else "navigated_elsewhere",
                                    "final_origin": landed})

        if action != "type":
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint

        if action == "observe":
            return self._observe(page, ctx)

        if action == "click_at":
            return self._click_at(page, args, ctx)

        if action == "read":
            from .base import MAX_TOOL_OUTPUT, truncation_meta
            # Bound in the page context so Playwright does not ship an unbounded DOM string.
            limit = MAX_TOOL_OUTPUT
            text = scope.evaluate(
                """(limit) => {
                    const raw = document.body ? (document.body.innerText || '') : '';
                    return raw.length > limit ? raw.slice(0, limit + 1) : raw;
                }""",
                limit,
            )
            data: dict = {"url": page.url}
            if isinstance(text, str) and len(text) > limit:
                text = text[:limit] + f"\n… [page text clipped; retained {limit:,} chars]"
                data.update(truncation_meta(stream="page", retained=limit, limit=limit,
                                            reason="capture_limit"))
            return ToolResult(ok=True, output=clip(text if isinstance(text, str) else ""), data=data)

        if action == "click":
            target = args.get("selector") or args.get("label") or ""
            locator, refusal = self._resolve_target(scope, selector=args.get("selector", ""), label=args.get("label", ""))
            if refusal is not None:
                return refusal
            try:
                reviewed_target, reviewed_fingerprint = self._click_review_snapshot(page, locator)
            except BrowserUnavailable as exc:
                return ToolResult(ok=False, output=f"error: {exc}")
            if reviewed_target["target_kind"] == "form_submit" and not self._reviewed_files(reviewed_target["target"]):
                return ToolResult(ok=False, output=("error: Hutch cannot submit an attached file because its contents "
                                                     "are not available for this approval review; use the reviewed upload action first"))
            url = page.url
            target_detail = reviewed_target["target"]
            if reviewed_target["target_kind"] == "form_submit":
                action_text = (f"submit form to {target_detail.get('destination', 'unknown destination')} "
                               f"({target_detail.get('method', 'get').upper()}) with {target_detail.get('label') or target or 'submit control'}")
            else:
                action_text = f"click {target or '(current focus)'}"
            _decide(ctx, "browser", action_text, {
                "action": action, "selector": args.get("selector", ""), "label": args.get("label", ""), "frame": args.get("frame", ""),
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
            if reviewed_target["target_kind"] == "form_submit" and not self._reviewed_files(target_detail):
                return ToolResult(False, "error: the reviewed file selection expired; request a new upload approval")
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
            refused = self._fence()
            if refused is not None:
                return refused
            had_sensitive_fields = self._page_has_sensitive_fields(page)
            before_url = page.url
            locator.click(timeout=10_000)
            self._stale("a click changed the page")
            self._settle(page)
            checkpoint = self._await_human_challenge(page, ctx, completed_action="click")
            if checkpoint:
                return checkpoint
            sensitive = self._new_sensitive_field_result(
                page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="click")
            if sensitive:
                return sensitive
            return ToolResult(ok=True, output=f"clicked {target}",
                              data={"url": page.url, "outcome": "dispatched", "page_changed": page.url != before_url,
                                    "verification": "not_verifiable: a click has no generic postcondition; observe the "
                                                    "page to confirm the intended state"})

        if action == "type":
            selector, text = args.get("selector", ""), args.get("text", "")
            if self._is_sensitive_target(scope, selector):
                return self._sensitive_entry_result(page, ctx)
            locator, refusal = self._resolve_target(scope, selector=selector, label="")
            if refusal is not None:
                return refusal
            checkpoint = self._await_human_challenge(page, ctx)
            if checkpoint:
                return checkpoint
            url = page.url
            try:
                reviewed, fingerprint = self._click_review_snapshot(page, locator)
            except BrowserUnavailable as exc:
                return ToolResult(False, f"error: {exc}")
            _decide(ctx, "browser", f"type into {selector}", {
                "action": action, "selector": selector, "frame": args.get("frame", ""), "text": "[redacted]", "text_chars": len(text),
                "value_fingerprint": hmac.new(_APPROVAL_FINGERPRINT_KEY, text.encode("utf-8"), hashlib.sha256).hexdigest(),
                "url": _redact_sensitive_url(url),
                "profile_bot_id": ctx.bot.id, "target": reviewed["target"],
                "target_fingerprint": fingerprint}, outward=True)
            if page.url != url:
                return ToolResult(ok=False, output="error: browser navigated after review; request a new approval")
            try:
                _, current_fingerprint = self._click_review_snapshot(page, locator)
            except BrowserUnavailable as exc:
                return ToolResult(False, f"error: {exc}")
            if not hmac.compare_digest(fingerprint, current_fingerprint):
                return ToolResult(False, "error: browser field or form changed after review; request a new approval",
                                  {"outcome": "not_dispatched"})
            if (refusal := ctx.begin_effect()):
                return ToolResult(ok=False, output=f"error: {refusal}")
            refused = self._fence()
            if refused is not None:
                return refused
            had_sensitive_fields = self._page_has_sensitive_fields(page)
            scope.fill(selector, text, timeout=10_000)
            self._stale("text was entered")
            checkpoint = self._await_human_challenge(page, ctx, completed_action="text entry")
            if checkpoint:
                return checkpoint
            sensitive = self._new_sensitive_field_result(
                page, ctx, had_sensitive_fields=had_sensitive_fields, completed_action="text entry")
            if sensitive:
                return sensitive
            outcome, detail = "dispatched", ""
            try:
                held = scope.input_value(selector, timeout=2_000)
                if held == text:
                    outcome = "effect_verified"
                else:
                    outcome = "mismatch"
                    detail = (f"\n[WARNING: the field now holds {len(held)} characters but {len(text)} were typed; the "
                              "page may have reformatted or rejected the input. Observe before relying on it.]")
            except Exception:
                pass                          # contenteditable or custom widgets have no readable value: stay "dispatched"
            return ToolResult(ok=True, output=f"typed {len(text)} chars into {selector}{detail}",
                              data={"outcome": outcome})

        if action == "screenshot":
            # Keep the historic action name without its unbounded, second-resolution workspace files.
            return self._observe(page, ctx)

        if action == "wait":
            if args.get("selector"):
                had_sensitive_fields = self._page_has_sensitive_fields(page)
                scope.wait_for_selector(args["selector"], timeout=15_000)
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
