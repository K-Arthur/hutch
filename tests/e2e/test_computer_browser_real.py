"""Real Chromium, real DOM: target identity, live re-resolution and tab ownership (computer use, slice 1).

The origin is a local fixture app reached through the pinned egress proxy (fake public DNS answer + connector that
redirects to the loopback origin), so SSRF protection is exercised rather than bypassed. Approvals are auto-granted by a
gate double; the *review snapshot* (CDP form fingerprint) is the real implementation.
"""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.approvals import DeniedError  # noqa: E402
from hutch.safety import Decision, Verdict  # noqa: E402
from hutch.tools.browser import BrowserTool  # noqa: E402

_PAGE = b"""<!doctype html><title>Fixture shop</title>
<main>
  <h1>Records</h1>
  <ul>
    <li>Alpha <button class="del" data-id="1">Delete</button></li>
    <li>Beta <button class="del" data-id="2">Delete</button></li>
  </ul>
  <form id="f" method="post" action="/submit">
    <label>Note <input id="note" name="note" autocomplete="off"></label>
    <button id="submit" type="submit" disabled>Submit</button>
    <button id="back" type="button" onclick="document.title='clicked back'">Back</button>
  </form>
  <a id="help" href="/popup" target="_blank">Open help</a>
</main>
<script>
  const note = document.getElementById('note'), submit = document.getElementById('submit');
  note.addEventListener('input', () => { submit.disabled = note.value.length < 3; });
</script>"""
_POPUP = b"<!doctype html><title>Help popup</title><p id='msg'>Help center popup content</p>"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body: bytes, status: int = 200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            # The stop-during-navigation check deliberately closes Chromium
            # while this fixture is holding the response open.
            pass
        self.close_connection = True

    def do_GET(self):
        self.server.log.append(("GET", self.path))
        if self.path.startswith("/popup"):
            self._send(_POPUP)
        elif self.path.startswith("/public"):       # served by the "public internet" origin
            local = self.server.local_url
            self._send((f"<!doctype html><title>Public page</title><p>public content</p>"
                        f"<img src='{local}/pixel' alt=''><a id='go' href='{local}/'>Open the dev app</a>").encode())
        elif self.path.startswith("/canvas"):
            self._send(b"<!doctype html><title>Canvas</title><body style='margin:0'>"
                       b"<canvas id='c' width='300' height='200' style='position:absolute;left:40px;top:60px;"
                       b"background:#ddd'></canvas><p id='log' style='position:absolute;top:300px'>none</p>"
                       b"<div style='height:2400px'></div><script>"
                       b"document.getElementById('c').addEventListener('click', e => { document.getElementById('log')"
                       b".textContent = 'clicked:' + Math.round(e.offsetX) + ',' + Math.round(e.offsetY); });</script>")
        elif self.path.startswith("/slow"):
            time.sleep(20)                       # a navigation that will not complete during the test
            self._send(b"<!doctype html><title>slow</title><p>late</p>")
        elif self.path.startswith("/login"):
            self._send(b"<!doctype html><title>Sign in</title><form><label>Password <input id='pw' type='password' "
                       b"name='pw'></label><button type='submit'>Sign in</button></form>")
        elif self.path.startswith("/to-local"):
            self._send(b"", 302, [("Location", f"{self.server.local_url}/redirected")])
        else:
            self._send(_PAGE)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode()
        self.server.log.append(("POST", self.path, parse_qs(body)))
        self._send(b"<!doctype html><title>Done</title><p>Submitted</p>")

    def log_message(self, *_args):
        pass


class _Gate:
    def __init__(self):
        self.decisions = []

    def decide(self, tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        if decision is not None and decision.verdict is Verdict.deny:     # the real gate raises before any prompt
            raise DeniedError(f"denied by policy: {decision.reason}")
        self.decisions.append((action, detail))

    def wait_for_human(self, *_args, **_kwargs):  # pragma: no cover - the fixture has no challenge
        raise AssertionError("the fixture page must not need a human")

    def cancelled(self):
        return False


class _Policy:
    def check_url(self, url):
        from hutch.netguard import screen_url
        reason = screen_url(url)
        if reason:
            return Decision(Verdict.deny, reason, rule="deny:test", risk="high")
        return Decision(Verdict.allow, "fixture", rule="allow:test", risk="low")


def _serve():
    origin = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    origin.daemon_threads = True
    origin.log = []
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    return origin, thread


_PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture()
def shop(config):
    """An approved local dev app (http://localhost:PORT) and a separate fake-public origin (http://public.example:PORT)."""
    local, local_thread = _serve()
    public, public_thread = _serve()
    local_port, public_port = local.server_address[1], public.server_address[1]
    local.local_url = public.local_url = f"http://localhost:{local_port}"

    def resolver(host, p, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_ADDRESS, p))]

    def connector(address, port, timeout):
        if address == _PUBLIC_ADDRESS:               # the pinned, validated public address -> the fixture public origin
            return socket.create_connection(public.server_address, timeout=timeout)
        return socket.create_connection((address, port), timeout=timeout)   # approved loopback literal

    tool = BrowserTool(resolver=resolver, connector=connector)
    gate = _Gate()
    bot = Bot(name="real-shop", local_dev_origins=[f"http://localhost:{local_port}"])
    ctx = SimpleNamespace(
        config=config, bot=bot, run=SimpleNamespace(id="run-real-shop"), headless=True,
        emit=lambda _e: None, on_finish=[], gate=gate, policy=_Policy(), workspace=config.state_dir,
        effect_started=False,
        dry_run=False, begin_effect=lambda: None, cancel_hooks=[])
    try:
        yield SimpleNamespace(tool=tool, ctx=ctx, gate=gate, base=f"http://localhost:{local_port}/",
                              public_base=f"http://public.example:{public_port}/", origin=local, public=public,
                              local_port=local_port)
    finally:
        tool._teardown()
        for server, thread in ((local, local_thread), (public, public_thread)):
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def _open(shop):
    result = shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx)
    assert result.ok, result.output
    return result


def test_duplicate_labels_are_refused_with_candidates_in_a_real_dom(shop):
    _open(shop)
    result = shop.tool.run({"action": "click", "label": "Delete"}, shop.ctx)
    assert not result.ok
    assert result.data["ambiguous_matches"] == 2
    assert [c["tag"] for c in result.data["candidates"]] == ["button", "button"]
    assert [action for action, _ in shop.gate.decisions] == [f"open http://localhost:{shop.local_port}"], \
        "no approval may be requested for an ambiguous click"
    assert not [e for e in shop.origin.log if e[0] == "POST"]


def test_a_scoped_selector_resolves_the_intended_duplicate(shop):
    _open(shop)
    result = shop.tool.run({"action": "click", "selector": 'button.del[data-id="2"]'}, shop.ctx)
    assert result.ok, result.output
    # the click was approved with the real, CDP-derived review of exactly that element
    action, detail = shop.gate.decisions[-1]
    assert action == "click button.del[data-id=\"2\"]"
    assert detail["target"]["label"] == "Delete"


def test_a_button_enabled_only_after_typing_is_resolved_against_the_live_dom(shop):
    _open(shop)
    typed = shop.tool.run({"action": "type", "selector": "#note", "text": "hello"}, shop.ctx)
    assert typed.ok, typed.output
    clicked = shop.tool.run({"action": "click", "label": "Submit"}, shop.ctx)
    assert clicked.ok, clicked.output
    posts = [e for e in shop.origin.log if e[0] == "POST"]
    assert posts == [("POST", "/submit", {"note": ["hello"]})], "the form must be submitted exactly once with the typed value"
    # the neighbouring button that a stale index would have hit was never clicked
    assert "Done" in shop.tool._tabs[shop.tool._active_tab].title()


def test_a_popup_becomes_the_active_tab_and_the_original_stays_addressable(shop):
    _open(shop)
    clicked = shop.tool.run({"action": "click", "label": "Open help"}, shop.ctx)
    assert clicked.ok, clicked.output
    read = shop.tool.run({"action": "read"}, shop.ctx)
    assert read.ok and "Help center popup content" in read.output, read.output
    assert read.data["tab"] == "t2"
    assert read.data.get("tab_changed") is True or clicked.data.get("tab_changed") is True
    assert [t["id"] for t in read.data["tabs"]] == ["t1", "t2"]

    back = shop.tool.run({"action": "read", "tab": "t1"}, shop.ctx)
    assert back.ok and "Records" in back.output and back.data["tab"] == "t1"

    missing = shop.tool.run({"action": "read", "tab": "t9"}, shop.ctx)
    assert not missing.ok and "no open tab" in missing.output


def test_public_page_cannot_load_subresources_from_the_approved_local_origin(shop):
    opened = shop.tool.run({"action": "goto", "url": shop.public_base + "public"}, shop.ctx)
    assert opened.ok, opened.output
    shop.tool.run({"action": "wait", "seconds": 0.5}, shop.ctx)          # let the <img> request be attempted
    assert ("GET", "/pixel") not in shop.origin.log, "a public page reached the approved local development origin"
    assert shop.origin.log == [], "nothing may have reached the local app from a public page"


def test_public_redirect_into_the_approved_local_origin_is_refused(shop):
    result = shop.tool.run({"action": "goto", "url": shop.public_base + "to-local"}, shop.ctx)
    assert not result.ok
    assert ("GET", "/redirected") not in shop.origin.log


def test_an_unapproved_loopback_port_is_still_refused(shop):
    other, thread = _serve()
    try:
        port = other.server_address[1]
        result = shop.tool.run({"action": "goto", "url": f"http://localhost:{port}/"}, shop.ctx)
        assert not result.ok and "denied by policy" in result.output
        assert other.log == []
        # an address that is not loopback can never be approved, even when written into the allowlist directly
        with pytest.raises(ValueError):
            Bot(name="lan", local_dev_origins=["http://192.168.0.10:3000"])
    finally:
        other.shutdown()
        other.server_close()
        thread.join(timeout=3)


def test_the_approved_local_app_is_reachable_and_public_names_still_resolve_publicly(shop):
    assert shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx).ok
    assert ("GET", "/") in shop.origin.log
    assert shop.tool.run({"action": "goto", "url": shop.public_base + "public"}, shop.ctx).ok
    assert [e for e in shop.public.log if e[0] == "GET" and e[1].startswith("/public")]


def _frames(shop, ref):
    from hutch.computer.frames import FrameStore, ImageRef
    run_dir = shop.ctx.config.run_dir(shop.ctx.bot.name, shop.ctx.run.id)
    return FrameStore(run_dir), ImageRef.from_internal(ref)


def test_observe_returns_a_real_bounded_frame_and_a_value_free_element_list(shop):
    _open(shop)
    assert shop.tool.run({"action": "type", "selector": "#note", "text": "private-typed-value"}, shop.ctx).ok
    result = shop.tool.run({"action": "observe"}, shop.ctx)
    assert result.ok, result.output
    record = result.data["observation"]
    assert record["status"] == "fresh" and record["surface"]["id"] == "t1"
    assert record["transform"] == {"scale": 1.0, "crop": None}
    store, ref = _frames(shop, result.data["images"][0])
    png = store.load(ref)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    viewport = record["viewport"]
    assert (ref.width, ref.height) == (viewport["css_width"], viewport["css_height"]), \
        "the image must be in CSS pixels so image coordinates and page coordinates agree"
    assert ref.bytes <= 900_000 and record["image"]["frame_id"] == ref.frame_id
    out = result.output
    assert "#note" in out and "#submit" in out and "disabled" not in out.split("#note")[0].split("\n")[-1]
    assert out.count('"Delete"') == 2
    assert "private-typed-value" not in out and "private-typed-value" not in str(record), \
        "field values must never enter an observation"


def test_observe_refuses_a_page_with_a_visible_password_field_and_keeps_no_frame(shop):
    shop.tool.run({"action": "goto", "url": shop.base + "login"}, shop.ctx)   # headless: reports there is no handoff
    result = shop.tool.run({"action": "observe"}, shop.ctx)
    assert not result.ok and result.data["observation"]["status"] == "blocked_sensitive"
    assert "images" not in result.data
    frames_dir = shop.ctx.config.run_dir(shop.ctx.bot.name, shop.ctx.run.id) / "frames"
    assert not frames_dir.exists() or list(frames_dir.iterdir()) == []


def test_two_observations_get_distinct_ordered_frame_ids(shop):
    _open(shop)
    first = shop.tool.run({"action": "observe"}, shop.ctx).data["observation"]
    second = shop.tool.run({"action": "observe"}, shop.ctx).data["observation"]
    assert first["frame_id"] < second["frame_id"]
    assert second["monotonic_ms"] >= first["monotonic_ms"]


def test_stop_during_a_hung_navigation_unblocks_the_tool_and_ends_the_browser(shop):
    from hutch import procguard
    opened = threading.Event()
    outcome = {}

    def agent():                                  # one thread launches and drives the browser, as a run's worker does
        outcome["open"] = shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx)
        opened.set()
        outcome["result"] = shop.tool.run({"action": "goto", "url": shop.base + "slow"}, shop.ctx)

    worker = threading.Thread(target=agent, daemon=True)
    worker.start()
    assert opened.wait(30) and outcome["open"].ok, outcome
    assert shop.tool._emergency_stop in shop.ctx.cancel_hooks
    driver = list(shop.tool._driver_procs)
    assert driver, "the automation driver process must have been identified at launch"
    browser_pids = [p.pid for root in driver for p in procguard.descendants(root.pid)]
    assert browser_pids, "a real browser process tree is running under the driver"

    time.sleep(1.0)
    assert worker.is_alive(), "the navigation is genuinely stuck on the slow origin"

    started = time.monotonic()
    for hook in list(shop.ctx.cancel_hooks):                 # exactly what the engine's stop path runs, off-thread
        hook()
    worker.join(8)
    latency = time.monotonic() - started
    assert not worker.is_alive(), "stop must unblock a call stuck inside the driver"
    print(f"MEASURED stop-to-unblocked latency: {latency:.2f}s")
    assert latency < 6, f"stop took {latency:.1f}s"
    result = outcome["result"]
    assert not result.ok and result.data.get("stopped") and result.data.get("outcome") == "unknown", result

    # nothing of the browser survives, and nothing more can be started from this tool
    for pid in [d.pid for d in driver] + browser_pids:
        now = procguard.identity(pid)
        assert now is None or now.state in ("Z", "X"), f"process {pid} survived the stop"
    again = shop.tool.run({"action": "read"}, shop.ctx)
    assert not again.ok and "stopped" in again.output


def test_using_the_browser_from_another_thread_fails_clearly(shop):
    _open(shop)
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("r", shop.tool.run({"action": "read"}, shop.ctx)))
    thread.start()
    thread.join(10)
    assert not box["r"].ok and box["r"].data.get("thread_affinity") is True


# ------------------------------------------------------------------ coordinates, control, outcomes

def _page(shop):
    return shop.tool._tabs[shop.tool._active_tab]


def _observe(shop):
    result = shop.tool.run({"action": "observe"}, shop.ctx)
    assert result.ok, result.output
    return result.data["observation"]["frame_id"], result


def test_click_at_lands_on_the_pixel_the_frame_showed(shop):
    shop.tool.run({"action": "goto", "url": shop.base + "canvas"}, shop.ctx)
    frame_id, _ = _observe(shop)
    # canvas is at (40, 60); the pixel (100, 90) of the frame is (60, 30) inside the canvas
    clicked = shop.tool.run({"action": "click_at", "frame_id": frame_id, "x": 100, "y": 90}, shop.ctx)
    assert clicked.ok, clicked.output
    assert clicked.data["outcome"] == "dispatched"
    assert _page(shop).locator("#log").inner_text() == "clicked:60,30"
    action, detail = shop.gate.decisions[-1]
    assert "click at (100, 90)" in action and detail["target"]["tag"] == "canvas"
    assert detail["frame_id"] == frame_id


def test_click_at_refuses_unknown_stale_and_out_of_bounds_frames_without_clicking(shop):
    shop.tool.run({"action": "goto", "url": shop.base + "canvas"}, shop.ctx)
    frame_id, result = _observe(shop)
    width = result.data["observation"]["image"]["width"]

    for args, needle in (
        ({"frame_id": "f999999", "x": 100, "y": 90}, "not the latest observation"),
        ({"frame_id": frame_id, "x": width, "y": 10}, "outside the"),
        ({"frame_id": frame_id, "x": -1, "y": 10}, "outside the"),
        ({"frame_id": frame_id, "x": "NaN", "y": 10}, "finite"),
        ({"frame_id": frame_id, "y": 10}, "numeric"),
    ):
        refused = shop.tool.run({"action": "click_at", **args}, shop.ctx)
        assert not refused.ok and needle in refused.output, (args, refused.output)
        assert refused.data["dispatched"] is False
    assert _page(shop).locator("#log").inner_text() == "none", "no refused click may have reached the page"


def test_a_scroll_between_observation_and_click_makes_the_frame_stale(shop):
    shop.tool.run({"action": "goto", "url": shop.base + "canvas"}, shop.ctx)
    frame_id, _ = _observe(shop)
    _page(shop).evaluate("window.scrollTo(0, 120)")          # the world moved after the model looked
    refused = shop.tool.run({"action": "click_at", "frame_id": frame_id, "x": 100, "y": 90}, shop.ctx)
    assert not refused.ok and "scrolled" in refused.output
    assert _page(shop).locator("#log").inner_text() == "none"


def test_a_state_changing_action_invalidates_the_observation_for_coordinates(shop):
    shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx)
    frame_id, _ = _observe(shop)
    assert shop.tool.run({"action": "type", "selector": "#note", "text": "abc"}, shop.ctx).ok
    refused = shop.tool.run({"action": "click_at", "frame_id": frame_id, "x": 5, "y": 5}, shop.ctx)
    assert not refused.ok and "observe again" in refused.output
    assert refused.data["control"]["fresh_observation_required"] is True


def test_a_takeover_between_approval_and_dispatch_prevents_the_click(shop):
    """The approval gate is where a person (or a remote operator) can act; the click must not land afterwards."""
    shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx)
    lease = shop.tool._lease

    original = shop.gate.decide

    def decide_then_takeover(tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        original(tool, action, detail, decision, outward, ask_in_auto)
        if detail.get("action") == "click":
            lease.take_over("a person grabbed the surface while the approval was open")
    shop.gate.decide = decide_then_takeover

    result = shop.tool.run({"action": "click", "selector": 'button.del[data-id="1"]'}, shop.ctx)
    assert not result.ok and "control changed" in result.output
    assert result.data["dispatched"] is False and result.data["control"]["owner"] == "human"
    # and while a person holds the surface, nothing new starts
    blocked = shop.tool.run({"action": "read"}, shop.ctx)
    assert not blocked.ok and "a person is controlling" in blocked.output
    # handing back resumes, with a fresh generation
    lease.hand_back()
    assert shop.tool.run({"action": "read"}, shop.ctx).ok


def test_replacing_the_reviewed_field_at_the_same_url_refuses_typing(shop):
    _open(shop)
    page = _page(shop)
    original = shop.ctx.gate.decide

    def replace_field(*args, **kwargs):
        decision = original(*args, **kwargs)
        page.evaluate("() => { const old = document.querySelector('#note'); old.replaceWith(old.cloneNode(true)); }")
        return decision

    shop.ctx.gate.decide = replace_field
    result = shop.tool.run({"action": "type", "selector": "#note", "text": "private review"}, shop.ctx)
    assert not result.ok and "changed after review" in result.output
    assert page.input_value("#note") == "", "the unreviewed replacement field must remain untouched"


def test_typing_and_navigation_report_verified_outcomes(shop):
    opened = shop.tool.run({"action": "goto", "url": shop.base}, shop.ctx)
    assert opened.data["outcome"] == "effect_verified"
    typed = shop.tool.run({"action": "type", "selector": "#note", "text": "hello"}, shop.ctx)
    assert typed.ok and typed.data["outcome"] == "effect_verified"
    # a page script that rewrites the value is surfaced, not reported as success
    _page(shop).evaluate("document.getElementById('note').addEventListener('input', e => "
                         "{ e.target.value = e.target.value.toUpperCase(); })")
    mangled = shop.tool.run({"action": "type", "selector": "#note", "text": "world"}, shop.ctx)
    assert mangled.ok and mangled.data["outcome"] == "mismatch" and "WARNING" in mangled.output
    assert "world" not in mangled.output.replace("typed 5 chars", "")


def test_control_changes_are_announced_as_run_events(shop):
    events = []
    shop.ctx.emit = events.append
    shop.tool._teardown()                      # relaunch so the lease is created with this emit hook
    _open(shop)
    shop.tool._lease.take_over("operator")
    shop.tool._lease.hand_back()
    kinds = [e.data for e in events if e.data.get("kind") == "computer_control"]
    assert [k["owner"] for k in kinds] == ["human", "agent"] and kinds[1]["generation"] > kinds[0]["generation"]
    assert all(k["surface"] == "browser" for k in kinds)


def test_reviewed_clicks_reuse_one_isolated_world_instead_of_leaking_a_context_each(shop):
    """Measured regression: a unique isolated-world name per reviewed click grew the browser ~0.5 MB per click."""
    _open(shop)
    page = _page(shop)
    cdp = page.context.new_cdp_session(page)
    names: list[str] = []
    cdp.on("Runtime.executionContextCreated", lambda payload: names.append(payload["context"].get("name", "")))
    cdp.send("Runtime.enable")                              # replays the contexts that already exist
    names.clear()
    for _ in range(6):
        assert shop.tool.run({"action": "click", "selector": "#back"}, shop.ctx).ok
    review_worlds = [n for n in names if n.startswith("hutch-review")]
    assert len(review_worlds) <= 1, f"each reviewed click created its own JS context: {review_worlds}"
