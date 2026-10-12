"""Real shell, iframe UI, reviewed upload, service receipt and bounded managed download."""
from __future__ import annotations

from email.parser import BytesParser
from email.policy import default
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time

import pytest

from hutch.approvals import resolve_approval
from hutch.models import Bot
from hutch.runtime.steps import call_tool
from hutch.tools.browser import BrowserTool
from hutch.tools.shell import ShellTool
from tests.test_tools import make_ctx

pytest.importorskip("playwright.sync_api")

DOCUMENT = b"record,title\n42,Reviewed local report\n"


def test_whole_form_file_limit_refuses_before_hashing_or_transmitting(store, config, tmp_path, app):
    server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="form-budget", tools=["browser"], local_dev_origins=[base]))
    tool = BrowserTool()
    try:
        assert tool.run({"action": "goto", "url": base}, ctx).ok
        page = tool._tabs[tool._active_tab]
        page.set_content('<form method=post action="/upload"><input id=a type=file><input id=b type=file><button id=send>Send</button></form>')
        page.evaluate("""() => {
          for (const id of ['a', 'b']) {
            const data = new DataTransfer(); data.items.add(new File(['test'], id + '.txt'));
            document.getElementById(id).files = data.files;
          }
          File.prototype.arrayBuffer = () => { throw new Error('hashing must not begin'); };
        }""")
        result = tool.run({"action": "click", "selector": "#send"}, ctx)
        assert not result.ok and "one-file" in result.output
        assert server.receipts == [] and store.pending_approvals() == []
    finally:
        tool._teardown()


class App(BaseHTTPRequestHandler):
    def send(self, body, content_type="text/html; charset=utf-8", status=200, headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        self.server.requests.append(("GET", self.path))
        if self.path == "/":
            self.send(b"<!doctype html><title>Local record workflow</title><h1>Records</h1>"
                      b"<p>Inspect the generated report and upload the reviewed version.</p>"
                      b"<iframe id=editor title='Report editor' src=/form style='width:800px;height:400px'></iframe>")
        elif self.path == "/form":
            self.send(b"<!doctype html><title>Report editor</title><h2>Record 42</h2><pre>" + DOCUMENT +
                      b"</pre><form action=/upload method=post enctype=multipart/form-data>"
                      b"<label>Title <input id=title name=title></label><button id=next type=button disabled>Next</button>"
                      b"<fieldset id=files hidden>"
                      b"<label>Report <input id=file name=report type=file accept='.csv'></label>"
                      b"<button id=submit disabled>Upload report</button></fieldset></form><script>"
                      b"document.querySelector('#title').oninput = e => document.querySelector('#next').disabled = !e.target.value;"
                      b"document.querySelector('#next').onclick = () => document.querySelector('#files').hidden = false;"
                      b"document.querySelector('#file').onchange = e => document.querySelector('#submit').disabled = !e.target.files.length;"
                      b"</script>")
        elif self.path == "/download":
            self.send(DOCUMENT, "text/csv", headers=[("Content-Disposition", 'attachment; filename="report.csv"')])
        elif self.path == "/oversize":
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", "4000001")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
        elif self.path == "/redirect":
            self.send(b"", status=302, headers=[("Location", "/download")])
        elif self.path == "/links":
            self.send(b"<!doctype html><a id=download href=/download download>Download</a>"
                      b"<a id=oversize href=/oversize download>Too large</a><a id=redirect href=/redirect download>Redirect</a>")
        elif self.path == "/sensitive":
            self.send(b"<!doctype html><iframe id=secret src=/password></iframe>")
        elif self.path == "/password":
            self.send(b"<!doctype html><input type=password aria-label=Password>")
        else:
            self.send(b"missing", status=404)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {self.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body)
        fields = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in message.iter_parts()}
        uploaded = fields.get("report")
        self.server.requests.append(("POST", self.path))
        self.server.receipts.append({"bytes": uploaded, "title": fields.get("title")})
        if uploaded != DOCUMENT or fields.get("title") != b"Reviewed record":
            self.send(b"Incorrect upload", status=422)
            return
        digest = hashlib.sha256(uploaded).hexdigest()
        self.send(f"<!doctype html><title>Upload receipt</title><h1>Upload accepted</h1><p id=hash>{digest}</p>"
                  "<a id=download href=/download download>Download reviewed report</a>".encode())

    def log_message(self, *_args):
        pass


@pytest.fixture()
def app():
    server = ThreadingHTTPServer(("127.0.0.1", 0), App)
    server.daemon_threads = True
    server.requests, server.receipts = [], []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://localhost:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_real_governed_shell_iframe_upload_receipt_and_download(store, config, tmp_path, app):
    server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="mixed-files", tools=["shell", "browser"], local_dev_origins=[base]))
    browser, shell = BrowserTool(), ShellTool()
    tools = {"browser": browser, "shell": shell}
    approvals, failures = [], []
    done = threading.Event()

    def reviewer():
        while not done.wait(.01):
            for approval in store.pending_approvals():
                try:
                    assert approval.run_id == ctx.run.id
                    assert approval.tool in {"shell", "browser"}
                    if approval.tool == "shell":
                        assert approval.detail["command"] == "printf 'record,title\\n42,Reviewed local report\\n' > report.csv"
                    else:
                        assert approval.detail["profile_bot_id"] == ctx.bot.id
                        assert approval.detail["action"] in {"type", "upload", "click", "download"}
                    approvals.append(approval.model_dump(mode="json"))
                    assert resolve_approval(store, approval.id, approve=True, by="controlled-local-test")
                except BaseException as exc:
                    failures.append(exc)
                    done.set()

    reviewer_thread = threading.Thread(target=reviewer, daemon=True)
    reviewer_thread.start()
    results = []
    evidence = os.environ.get("HUTCH_EVIDENCE_DIR")
    tracing = False
    console_errors = []

    def invoke(action, **args):
        result = call_tool(ctx.run, ctx, tools, "browser", {"action": action, **args})
        results.append({"action": action, "ok": result.ok, "output": result.output, "data": result.data})
        assert result.ok, result.output
        return result

    try:
        command = "printf 'record,title\\n42,Reviewed local report\\n' > report.csv"
        generated = call_tool(ctx.run, ctx, tools, "shell", {"command": command})
        assert generated.ok, generated.output
        assert (ctx.workspace / "report.csv").read_bytes() == DOCUMENT
        invoke("goto", url=base)
        page = browser._tabs[browser._active_tab]
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        if evidence:
            # Only this credential-free local fixture is traced. Authentication
            # scenarios must not export entered secrets via Playwright traces.
            browser._browser.tracing.start(screenshots=True, snapshots=True, sources=False)
            tracing = True
        assert "Reviewed local report" in invoke("read", frame="#editor").output
        invoke("type", selector="#title", frame="#editor", text="Reviewed record")
        invoke("click", selector="#next", frame="#editor")
        selected = invoke("upload", selector="#file", frame="#editor", path="report.csv")
        assert selected.data["transfer"]["sha256"] == hashlib.sha256(DOCUMENT).hexdigest()
        assert selected.data["transfer"]["destination"] == base + "/upload"
        invoke("click", selector="#submit", frame="#editor")
        receipt = invoke("read", frame="#editor")
        assert "Upload accepted" in receipt.output and hashlib.sha256(DOCUMENT).hexdigest() in receipt.output
        assert server.receipts == [{"bytes": DOCUMENT, "title": b"Reviewed record"}]
        downloaded = invoke("download", selector="#download", frame="#editor", path="received/report.csv")
        assert (ctx.workspace / "received/report.csv").read_bytes() == DOCUMENT
        ref = downloaded.data["workspace_file"]
        artifact = config.run_dir(ctx.bot.name, ctx.run.id) / ref["artifact"]
        assert artifact.read_bytes() == DOCUMENT and artifact.stat().st_mode & 0o777 == 0o400
        assert server.requests.count(("GET", "/download")) == 1, "download must never repeat an uncertain GET"
        assert any(a["detail"].get("file", {}).get("sha256") == ref["sha256"] and a["outward"] for a in approvals)
        assert any(a["detail"].get("target_kind") == "form_submit" and a["outward"] for a in approvals)
        assert not failures
        assert not console_errors, console_errors
        if evidence:
            out = Path(evidence)
            out.mkdir(parents=True, exist_ok=True)
            page = browser._tabs[browser._active_tab]
            page.screenshot(path=str(out / "mixed-workflow.png"), scale="css")
            browser._browser.tracing.stop(path=str(out / "mixed-workflow-trace.zip"))
            tracing = False
            (out / "mixed-workflow.json").write_text(json.dumps({"document_sha256": ref["sha256"],
                "requests": server.requests, "results": results, "approval_count": len(approvals),
                "console_errors": console_errors, "trace": "mixed-workflow-trace.zip",
                "a11y": page.locator("body").aria_snapshot(),
                "iframe_a11y": page.frame_locator("#editor").locator("body").aria_snapshot()}, indent=2))
    finally:
        done.set()
        reviewer_thread.join(3)
        if tracing:
            browser._browser.tracing.stop()
        browser._teardown()


@pytest.mark.parametrize("bad", ["oversize", "redirect"])
def test_bad_download_leaves_no_workspace_file_or_automatic_retry(store, config, tmp_path, app, bad):
    from tests.e2e.test_computer_browser_real import _Gate
    server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="bounded-download", tools=["browser"], local_dev_origins=[base]))
    ctx.gate = _Gate()  # driver/limits test; the mixed test above exercises production approvals
    tool = BrowserTool()
    try:
        assert tool.run({"action": "goto", "url": base + "/links"}, ctx).ok
        result = tool.run({"action": "download", "selector": "#" + bad, "path": "out.csv"}, ctx)
        assert not result.ok and not (ctx.workspace / "out.csv").exists(), result.output
        assert server.requests.count(("GET", "/" + bad)) == 1
        assert ("GET", "/download") not in server.requests
    finally:
        tool._teardown()


def test_upload_rejects_changed_source_and_secret_or_linked_paths(store, config, tmp_path, app):
    from tests.e2e.test_computer_browser_real import _Gate
    _server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="upload-fences", tools=["browser"], local_dev_origins=[base]))
    gate = _Gate()
    ctx.gate = gate
    tool = BrowserTool()
    source = ctx.workspace / "report.csv"
    source.write_bytes(DOCUMENT)
    secret = ctx.workspace / ".env.txt"
    secret.write_text("SENTINEL-SECRET")
    (ctx.workspace / "link.csv").symlink_to(source)
    os.link(secret, ctx.workspace / "alias.csv")
    try:
        assert tool.run({"action": "goto", "url": base}, ctx).ok
        page = tool._tabs[tool._active_tab]
        # Fault-injection setup reveals the input; acceptance uses the real Next control above.
        page.frame_locator("#editor").locator("#files").evaluate("el => el.hidden = false")
        for path in (".env.txt", "link.csv", "alias.csv", "../outside.csv"):
            result = tool.run({"action": "upload", "selector": "#file", "frame": "#editor", "path": path}, ctx)
            assert not result.ok, path
        original = gate.decide

        def change_after_review(*args, **kwargs):
            original(*args, **kwargs)
            source.write_text("changed\n")

        gate.decide = change_after_review
        result = tool.run({"action": "upload", "selector": "#file", "frame": "#editor", "path": "report.csv"}, ctx)
        assert not result.ok and "changed after review" in result.output
        page = tool._tabs[tool._active_tab]
        assert page.frame_locator("#editor").locator("#file").evaluate("el => el.files.length") == 0
    finally:
        tool._teardown()


def test_iframe_secret_blocks_observation_and_replaced_frame_cannot_receive_old_review(store, config, tmp_path, app):
    from tests.e2e.test_computer_browser_real import _Gate
    _server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="frame-fences", tools=["browser"], local_dev_origins=[base]))
    ctx.gate = _Gate()
    tool = BrowserTool()
    try:
        assert not tool.run({"action": "goto", "url": base + "/sensitive"}, ctx).ok
        observed = tool.run({"action": "observe"}, ctx)
        assert not observed.ok and observed.data["observation"]["status"] == "blocked_sensitive"
        assert tool.run({"action": "goto", "url": base}, ctx).ok
        original = ctx.gate.decide

        def replace_frame(*args, **kwargs):
            original(*args, **kwargs)
            tool._tabs[tool._active_tab].evaluate("document.querySelector('#editor').replaceWith(document.querySelector('#editor').cloneNode(true))")

        ctx.gate.decide = replace_frame
        typed = tool.run({"action": "type", "selector": "#title", "frame": "#editor", "text": "must not land"}, ctx)
        assert not typed.ok
        page = tool._tabs[tool._active_tab]
        assert page.frame_locator("#editor").locator("#title").input_value() == ""
    finally:
        tool._teardown()


def test_changed_account_cookie_invalidates_review_before_input(store, config, tmp_path, app):
    from tests.e2e.test_computer_browser_real import _Gate
    _server, base = app
    ctx = make_ctx(store, config, tmp_path, Bot(name="account-fence", tools=["browser"], local_dev_origins=[base]))
    ctx.gate = _Gate()
    tool = BrowserTool()
    try:
        assert tool.run({"action": "goto", "url": base}, ctx).ok
        original = ctx.gate.decide

        def switch_account(*args, **kwargs):
            original(*args, **kwargs)
            tool._browser.add_cookies([{"name": "account", "value": "changed-identity", "url": base}])

        ctx.gate.decide = switch_account
        result = tool.run({"action": "type", "selector": "#title", "frame": "#editor", "text": "must not land"}, ctx)
        assert not result.ok and "changed after review" in result.output
        assert tool._tabs[tool._active_tab].frame_locator("#editor").locator("#title").input_value() == ""
    finally:
        tool._teardown()
