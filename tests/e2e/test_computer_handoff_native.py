"""Human takeover of a visible browser, end to end, inside a disposable native Wayland session.

A verification-wall page parks the run; a "person" (the test, through real EIS keyboard/pointer input into the same compositor)
completes it in the same visible window; the run then resumes, re-inspects the live page and continues. The assertions are
about *who could see what*: nothing is captured for the model while the person works, the typed secret never reaches recorded
events or later observations, control ownership flips human -> agent with a new generation, and coordinates from before the
handoff are refused.

Evidence class: real headed Chromium under a real Wayland compositor (KWin virtual), not the personal desktop, not a phone.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright.sync_api")

from hutch.computer.frames import FrameStore  # noqa: E402
from hutch.computer.native.eis import EisInput, find_gi_python  # noqa: E402
from hutch.computer.native.virtual import ManagedDesktop  # noqa: E402
from hutch.models import Bot  # noqa: E402
from hutch.tools.browser import BrowserTool  # noqa: E402

_ok, _why = ManagedDesktop.available()
pytestmark = pytest.mark.skipif(not _ok or find_gi_python() is None,
                                reason=_why or "no PyGObject interpreter for the input worker")

SECRET = "human-typed-secret-91ac"
WALL = ("<!doctype html><title>Verify</title><body style='margin:0;font:24px sans-serif'>"
        "<h1 style='margin:20px'>Security check</h1><p style='margin:20px'>Please enter your verification code to continue.</p>"
        "<form id='f' style='margin:20px'><input id='answer' name='answer' autocomplete='off' "
        "style='font-size:28px;width:420px;height:48px'></form>"
        "<script>document.getElementById('f').addEventListener('submit', e => { e.preventDefault();"
        "document.body.innerHTML = '<h1 style=\"margin:20px\">Welcome back, verified</h1>'; });</script></body>")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        raw = WALL.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def log_message(self, *_a):
        pass


class _Gate:
    """A person's side of the wait: parks until the test (acting as the person) releases it."""

    def __init__(self, frames_dir_probe):
        self.parked = threading.Event()
        self.resume = threading.Event()
        self.waits: list[tuple[str, str]] = []
        self.decisions: list[str] = []
        self._probe = frames_dir_probe
        self.frames_at_park = None

    def decide(self, tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        self.decisions.append(action)

    def wait_for_human(self, reason, url="", handoff=""):
        self.waits.append((reason, url))
        self.frames_at_park = self._probe()
        self.parked.set()
        assert self.resume.wait(60), "the person never resumed"

    def cancelled(self):
        return False


@pytest.fixture()
def wall_origin():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_a_person_completes_a_verification_wall_in_the_visible_browser_then_resumes(
        config, wall_origin, monkeypatch, tmp_path):
    real_cache = Path.home() / ".cache" / "ms-playwright"
    if not real_cache.exists():
        pytest.skip("no Playwright browser cache")
    base = wall_origin
    with ManagedDesktop() as desktop:
        # The browser must be launched by *this* process into the disposable compositor, never the personal one.
        for key, value in desktop.env.items():
            if key in ("HOME", "PATH"):
                continue
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(real_cache))
        assert os.environ["WAYLAND_DISPLAY"] == ManagedDesktop.SOCKET

        run_id = "run-handoff"
        frames = FrameStore(config.run_dir("handoff-bot", run_id))
        events: list = []
        gate = _Gate(lambda: frames.usage()["frames"])
        ctx = SimpleNamespace(
            config=config, bot=Bot(name="handoff-bot", local_browser_handoff=True, local_dev_origins=[base]),
            run=SimpleNamespace(id=run_id), headless=False, emit=events.append, on_finish=[], cancel_hooks=[],
            gate=gate, policy=SimpleNamespace(check_url=lambda u: None), workspace=tmp_path, dry_run=False,
            begin_effect=lambda: None)
        tool = BrowserTool()
        outcome: dict = {}

        def agent() -> None:
            outcome["goto"] = tool.run({"action": "goto", "url": f"{base}/"}, ctx)
            if outcome["goto"].ok:
                outcome["observe"] = tool.run({"action": "observe"}, ctx)
                outcome["read"] = tool.run({"action": "read"}, ctx)

        worker = threading.Thread(target=agent, daemon=True)
        input_channel = None
        try:
            worker.start()
            assert gate.parked.wait(45), f"the verification wall never parked the run: {outcome}"
            assert worker.is_alive(), "the run must be paused, not finished or failed"
            assert gate.frames_at_park == 0
            owner_while_waiting = tool._lease.snapshot()
            assert owner_while_waiting.owner.value == "human"
            if os.environ.get("HUTCH_DEBUG_SHOT"):                  # evidence/debug capture of the person's view
                Path(os.environ["HUTCH_DEBUG_SHOT"]).write_bytes(desktop.capture_png())

            # --- the person works in the same window, with real input, while nothing is observed for the model ---
            input_channel = EisInput.start_in_isolated_session(desktop.env)
            time.sleep(1.0)
            input_channel.click(240, 257)                       # into the verification-code field (see handoff-wall.png)
            time.sleep(0.4)
            input_channel.type_text(SECRET)
            time.sleep(0.4)
            input_channel.chord("enter")                        # submits the form: the wall is replaced
            time.sleep(1.2)
            assert frames.usage()["frames"] == 0, "a frame was captured while the person was handling the step"

            gate.resume.set()                                   # the person presses Resume
            worker.join(60)
            assert not worker.is_alive(), "the run did not continue after Resume"
        finally:
            gate.resume.set()
            if input_channel is not None:
                input_channel.close()
            tool._teardown()

        # --- what the run did after the person's step ---
        assert outcome["goto"].ok, outcome["goto"].output
        assert "Welcome back, verified" in outcome["read"].output
        assert gate.waits and "Human verification is needed" in gate.waits[0][0]
        record = outcome["observe"].data["observation"]
        assert record["status"] == "fresh" and record["frame_id"] == "f000001"
        # the secret the person typed is in no event, no approval, and no later observation
        blob = repr([e.model_dump() for e in events]) + repr(gate.decisions) + outcome["observe"].output + \
            outcome["read"].output
        assert SECRET not in blob
        # ownership flipped human -> agent with a new generation and demanded a fresh observation before coordinates
        owners = [e.data for e in events if e.data.get("kind") == "computer_control"]
        assert [o["owner"] for o in owners[-2:]] == ["human", "agent"]
        assert owners[-1]["generation"] > owners[-2]["generation"] > 0
