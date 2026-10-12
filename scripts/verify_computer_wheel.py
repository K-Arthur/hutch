"""Run with an isolated wheel install's `python -I`; uses only throwaway state and loopback.

No provider inference, personal desktop input, dependency install or OS permission change.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--native", action="store_true", help="also require delivered input in a disposable KWin/KWrite session")
    args = parser.parse_args()
    import hutch
    package = Path(hutch.__file__).resolve().parent
    source = Path(args.source_root).resolve()
    assert not package.is_relative_to(source), "this check must import the installed wheel"
    report = {"python": sys.version.split()[0], "package_origin": str(package), "assets": {},
              "dependencies": {name: importlib.metadata.version(name) for name in
                               ("hutch", "playwright", "fastapi", "openai", "pydantic", "anthropic")}}
    for relative in ("server/static/index.html", "server/static/computer.js", "server/static/computer.css",
                     "computer/native/eis_worker.py", "computer/native/virtual.py", "computer/transport.py"):
        installed = (package / relative).read_bytes()
        assert installed == (source / "src/hutch" / relative).read_bytes(), relative
        report["assets"][relative] = {"bytes": len(installed), "sha256": hashlib.sha256(installed).hexdigest()}
    with tempfile.TemporaryDirectory(prefix="hutch-wheel-") as state:
        os.environ["HUTCH_STATE_DIR"] = state
        from hutch.server.app import create_app
        from fastapi.testclient import TestClient
        with TestClient(create_app(), base_url="http://127.0.0.1") as client:
            for route in ("/", "/static/computer.js", "/static/computer.css", "/api/v1/computer/readiness"):
                response = client.get(route)
                assert response.status_code == 200, (route, response.status_code)
            report["http_assets_and_readiness"] = "passed"
        command = subprocess.run([str(Path(sys.executable).parent / "hutch"), "computer", "doctor", "--deep", "--json"],
                                 text=True, capture_output=True, timeout=40, check=True)
        report["installed_cli_doctor"] = json.loads(command.stdout)
        from hutch.config import get_config
        from hutch.models import Bot
        from hutch.safety import PolicyEngine
        from hutch.tools.base import ProcRegistry
        from hutch.tools.browser import BrowserTool
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"<!doctype html><title>Installed wheel outcome</title><main>Installed wheel outcome</main>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://localhost:{server.server_address[1]}"
        config = get_config()
        ctx = SimpleNamespace(config=config, bot=Bot(name="wheel-check", tools=["browser"], local_dev_origins=[origin]),
                              run=SimpleNamespace(id="wheel-check"), workspace=Path(state), gate=SimpleNamespace(
                                  decide=lambda *_a, **_k: None, cancelled=lambda: False), policy=PolicyEngine(),
                              headless=True, dry_run=False, begin_effect=lambda: None, emit=lambda _e: None,
                              on_finish=[], cancel_hooks=[], procs=ProcRegistry())
        tool = BrowserTool()
        try:
            assert tool.run({"action": "goto", "url": origin}, ctx).ok
            observation = tool.run({"action": "observe"}, ctx)
            assert observation.ok and observation.data["images"]
            assert "Installed wheel outcome" in tool.run({"action": "read"}, ctx).output
            report["installed_real_browser"] = {"status": "passed", "frame": observation.data["observation"]["image"]}
        finally:
            tool._teardown()
            server.shutdown()
            server.server_close()
            thread.join(3)
        if args.native:
            from hutch.computer.frames import FrameStore, ImageRef
            from hutch.tools.computer import ComputerTool
            workspace = Path(state) / "native-workspace"
            workspace.mkdir(mode=0o700)
            document = workspace / "installed-wheel.txt"
            document.write_text("")
            native_ctx = SimpleNamespace(**{**vars(ctx), "bot": Bot(name="wheel-native", tools=["computer"],
                                        computer_apps=["kwrite"]), "run": SimpleNamespace(id="wheel-native"),
                                        "workspace": workspace, "on_finish": [], "cancel_hooks": [],
                                        "procs": ProcRegistry()})
            native = ComputerTool()
            try:
                result = native.run({"action": "launch", "app": "kwrite", "path": document.name}, native_ctx)
                assert result.ok, result.output
                result = native.run({"action": "observe"}, native_ctx)
                assert result.ok, result.output
                for action in ({"action": "click", "x": 640, "y": 400},
                               {"action": "type", "text": "Installed wheel native outcome"},
                               {"action": "key", "keys": "ctrl+s"}):
                    result = native.run({**action, "frame_id": result.data["observation"]["frame_id"]}, native_ctx)
                    assert result.ok, result.output
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and document.read_text().rstrip("\n") != "Installed wheel native outcome":
                    time.sleep(.05)
                assert document.read_text().rstrip("\n") == "Installed wheel native outcome", "installed native UI did not save the expected text"
                png = FrameStore(config.run_dir("wheel-native", "wheel-native")).load(ImageRef.from_internal(result.data["images"][0]))
                screenshot = Path(args.evidence).with_name("native-installed-wheel.png")
                screenshot.write_bytes(png)
                report["installed_real_native"] = {"status": "passed", "saved_sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
                                                   "screenshot": screenshot.name}
            finally:
                native._emergency_stop()
                native._shutdown(native_ctx)
                native_ctx.procs.kill_all(.2)
    Path(args.evidence).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"http_assets_and_readiness": report["http_assets_and_readiness"],
                      "installed_real_browser": "passed", "installed_real_native": report.get("installed_real_native", "not run"),
                      "dependencies": report["dependencies"]}))


if __name__ == "__main__":
    main()
