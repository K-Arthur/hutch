"""End-to-end coding repair through the real workflow interpreter.

The provider response is scripted, so this accepts runtime, tool, test, and browser behavior;
it does not qualify a live model for coding. All generated files stay in the disposable run
workspace. The browser inspection uses those exact files after the workflow settles.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version as package_version
from pathlib import Path

from playwright.sync_api import sync_playwright

from hutch.models import ApprovalMode
from hutch.workflow import submit as wfsubmit
from tests.fakes import FakeOllama
from tests.test_workflow_engine import drive, make_bot


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/realignment/artifacts/dynamic-workflows/coding-repair"

FILE_PATHS = {
    "metrics": "workflow_metrics.py",
    "view": "workflow_view.py",
    "metrics_tests": "tests/test_workflow_metrics.py",
    "view_tests": "tests/test_workflow_view.py",
    "index": "public/index.html",
    "css": "public/app.css",
    "format": "public/format.js",
    "app": "public/app.js",
    "data": "public/data.json",
}

FIXED_FILES = {
    "workflow_metrics.py": '''\
def summarize_steps(steps):
    if not isinstance(steps, list):
        raise TypeError("steps must be a list")
    states = [str(step.get("status", "unknown")).casefold() for step in steps]
    done = sum(state in {"succeeded", "verified"} for state in states)
    needs_you = sum(state in {"waiting_approval", "waiting_human", "needs_you"} for state in states)
    return {"total": len(states), "completed": done, "needs_you": needs_you,
            "remaining": len(states) - done - needs_you}
''',
    "workflow_view.py": '''\
from workflow_metrics import summarize_steps


def header_summary(workflow, steps):
    metrics = summarize_steps(steps)
    title = str(workflow.get("title") or "Workflow result")
    summary = f"{metrics['completed']} of {metrics['total']} steps complete"
    if metrics["needs_you"]:
        summary += f" · {metrics['needs_you']} needs you"
    return {"title": title, "summary": summary, "metrics": metrics}
''',
    "tests/test_workflow_metrics.py": '''\
import unittest

from workflow_metrics import summarize_steps


class WorkflowMetricsTests(unittest.TestCase):
    def test_success_and_verified_are_complete(self):
        self.assertEqual(summarize_steps([{"status": "succeeded"}, {"status": "verified"}]),
                         {"total": 2, "completed": 2, "needs_you": 0, "remaining": 0})

    def test_waiting_states_remain_visible(self):
        result = summarize_steps([{"status": "succeeded"}, {"status": "waiting_human"},
                                  {"status": "running"}])
        self.assertEqual((result["completed"], result["needs_you"], result["remaining"]), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
''',
    "tests/test_workflow_view.py": '''\
import unittest

from workflow_view import header_summary


class WorkflowViewTests(unittest.TestCase):
    def test_header_uses_real_status_and_keeps_long_title(self):
        title = "Review the full regional supplier reconciliation and supporting statements"
        view = header_summary({"title": title}, [{"status": "succeeded"}, {"status": "succeeded"}])
        self.assertEqual(view["title"], title)
        self.assertEqual(view["summary"], "2 of 2 steps complete")


if __name__ == "__main__":
    unittest.main()
''',
    "public/index.html": '''\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="dark">
    <title>Workflow result</title>
    <link rel="stylesheet" href="./app.css">
  </head>
  <body>
    <main class="page" aria-labelledby="workflow-title">
      <header class="summary">
        <div class="summary-row"><p class="eyebrow">Workflow result</p><span id="run-state" class="state">Loading</span></div>
        <h1 id="workflow-title">Loading workflow</h1>
        <p id="workflow-summary" role="status" aria-live="polite">Checking the recorded steps…</p>
      </header>
      <section class="steps" aria-labelledby="steps-title">
        <div class="section-heading"><h2 id="steps-title">Steps</h2><span id="step-count"></span></div>
        <ol id="workflow-steps" class="step-list"></ol>
      </section>
      <details class="result">
        <summary>Open the verified result</summary>
        <p id="report-text"></p>
      </details>
    </main>
    <script type="module" src="./app.js"></script>
  </body>
</html>
''',
    "public/app.css": '''\
:root { color-scheme: dark; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  color: #f0f4f9; background: #05070a; font-synthesis: none; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 0; background: #05070a; color: #f0f4f9; font-size: 1rem; line-height: 1.55; }
.page { width: min(100% - 40px, 880px); margin: 0 auto; padding: clamp(24px, 5vw, 56px) 0 48px; }
.summary { padding: 24px; border: 1px solid #27313d; border-radius: 12px; background: #0b1118; }
.summary-row, .section-heading, .step { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.eyebrow { margin: 0; color: #9daebf; font-size: .875rem; font-weight: 650; }
.state { display: inline-flex; align-items: center; min-height: 28px; padding: 2px 10px; border-radius: 999px;
  color: #052e21; background: #34d399; font-size: .8rem; font-weight: 700; }
h1 { max-width: 24ch; margin: 18px 0 8px; font-size: clamp(1.65rem, 4vw, 2.35rem); line-height: 1.15; letter-spacing: -.025em; overflow-wrap: anywhere; }
.summary > p:last-child { margin: 0; color: #b8c5d3; }
.steps { margin-top: 28px; }
.section-heading { align-items: baseline; margin-bottom: 12px; }
h2 { margin: 0; font-size: 1.15rem; line-height: 1.3; }
#step-count { color: #9daebf; font-size: .875rem; }
.step-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.step { min-width: 0; padding: 16px; border: 1px solid #27313d; border-radius: 10px; background: #0b1118; }
.step-title { min-width: 0; margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.step-state { flex: 0 0 auto; color: #9daebf; font-size: .875rem; }
.step[data-state="succeeded"] .step-state { color: #6ee7b7; }
.result { margin-top: 18px; border-top: 1px solid #27313d; padding-top: 16px; }
.result summary { width: fit-content; min-height: 44px; padding: 10px 12px; border-radius: 8px; cursor: pointer; font-weight: 650; }
.result summary:hover { background: #10161f; }
.result summary:focus-visible { outline: 3px solid #60a5fa; outline-offset: 3px; }
.result p { max-width: 70ch; margin: 8px 12px 0; color: #b8c5d3; overflow-wrap: anywhere; }
@media (max-width: 520px) {
  .page { width: min(100% - 32px, 880px); padding-top: 20px; }
  .summary { padding: 18px; }
  .step { align-items: flex-start; padding: 14px; }
  .step-state { text-align: right; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; } }
''',
    "public/format.js": '''\
const labels = { succeeded: "Complete", verified: "Verified", running: "In progress",
  waiting_human: "Needs you", waiting_approval: "Needs you", failed: "Failed" };

export function statusLabel(status) {
  return labels[status] || "Status unknown";
}
''',
    "public/app.js": '''\
import { statusLabel } from "./format.js";

const $ = (selector) => document.querySelector(selector);

async function renderWorkflow() {
  const response = await fetch("./data.json", { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Could not load the workflow result (${response.status}).`);
  const data = await response.json();
  $("#workflow-title").textContent = data.title;
  $("#workflow-summary").textContent = data.summary;
  $("#run-state").textContent = data.state;
  $("#step-count").textContent = `${data.steps.length} steps`;
  $("#report-text").textContent = data.report;
  const list = $("#workflow-steps");
  list.replaceChildren(...data.steps.map((step) => {
    const item = document.createElement("li");
    item.className = "step";
    item.dataset.state = step.status;
    const title = document.createElement("p");
    title.className = "step-title";
    title.textContent = step.title;
    const status = document.createElement("span");
    status.className = "step-state";
    status.textContent = statusLabel(step.status);
    item.append(title, status);
    return item;
  }));
}

renderWorkflow().catch((error) => {
  $("#run-state").textContent = "Unavailable";
  $("#workflow-summary").textContent = error.message;
});
''',
    "public/data.json": json.dumps({
        "title": "Review the full regional supplier reconciliation and supporting statements",
        "state": "Verified",
        "summary": "The source totals and published summary passed their independent checks.",
        "report": "Four source statements were reconciled. The total matches the reviewed ledger.",
        "steps": [
            {"title": "Collect the regional supplier statements", "status": "succeeded"},
            {"title": "Check formulas against the source totals", "status": "verified"},
            {"title": "Publish the reviewed reconciliation summary", "status": "succeeded"},
        ],
    }, ensure_ascii=False, indent=2) + "\n",
}

REPAIR_OUTPUT = {"replacement": {"status": "ready", "files": {
    key: FIXED_FILES[path] for key, path in FILE_PATHS.items()
}}}


def _plan() -> dict:
    nodes = [
        {"kind": "transform", "id": "starter", "op": "constant", "args": {"value": {
            "status": "needs_repair", "files": {"metrics": "return len(steps)\n"}}}},
        {"kind": "verify", "id": "repair", "checks": [{"kind": "schema", "ref": "starter", "schema": {
            "type": "object", "required": ["status", "files"], "properties": {
                "status": {"type": "string", "enum": ["ready"]},
                "files": {"type": "object", "required": list(FILE_PATHS)},
            }}}], "on_fail": {"action": "repair", "rounds": 1, "adopt": "starter",
                            "instruction": "Repair the multi-module workflow summary and responsive result view. "
                                          "Return the complete set of files in the replacement object."}},
    ]
    for index, (key, path) in enumerate(FILE_PATHS.items()):
        nodes.append({"kind": "tool", "id": f"write_{index}", "tool": "write_file",
                      "args": {"path": path, "content": {"ref": f"starter.files.{key}"}}})
    nodes.extend([
        {"kind": "verify", "id": "tests", "checks": [{"kind": "command", "argv": [
            sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "expect_exit": 0, "timeout_seconds": 90}]},
        {"kind": "publish", "id": "report", "artifacts": [{"name": "coding-repair-test-results",
            "ref": "tests", "media_type": "application/json", "primary": True}]},
        {"kind": "verify", "id": "artifact_check", "checks": [
            {"kind": "schema", "ref": "report", "schema": {"type": "object",
             "required": ["artifacts"], "properties": {"artifacts": {"type": "array", "minItems": 1}}}},
            {"kind": "artifact", "ref": "report.artifacts[0]"},
        ]},
    ])
    return {
        "name": "disposable-multi-module-coding-repair",
        "envelope": {"tools": ["write_file", "shell"], "models": ["ollama/tiny:1b"],
                     "max_parallel_steps": 1},
        "budget": {"max_nodes": 20, "max_model_calls": 2, "max_tokens": 12_000,
                   "max_wall_seconds": 300, "max_repairs": 1},
        "outputs": ["report"], "nodes": nodes,
    }


class _StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_disposable_multi_module_repair_runs_tests_and_inspects_ui(store, config, monkeypatch):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMPDIR", "/var/tmp/pytest-of-kevina")
    provider = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    provider.script = lambda _body: {"content": json.dumps(REPAIR_OUTPUT, ensure_ascii=False)}
    monkeypatch.setenv("OLLAMA_HOST", provider.url)
    bot = make_bot(store, name="coding-repair-acceptance", model="ollama/tiny:1b",
                   tools=["files", "shell"], approval_mode=ApprovalMode.auto, selfcheck=False)
    plan = _plan()
    engine = __import__("hutch.engine", fromlist=["Engine"]).Engine(
        config, store, executor="process", max_concurrent=2)
    try:
        submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan,
                                              definition_name="coding-repair-acceptance")
        drive(engine, store, submission.attempt_run_id, timeout=240)
        view = wfsubmit.status(store, submission.workflow_run_id)
        assert view["workflow"]["status"] == "succeeded", view["workflow"].get("reason")
        assert view["workflow"]["ledger"]["model_calls"] == 1
        assert view["workflow"]["ledger"]["repairs"] == 1
        nodes = {(node["site_id"], node["instance_key"]): node for node in view["nodes"]}
        assert nodes[("repair", "once")]["result"]["repair"]["round"] == 1
        assert nodes[("repair", "once|r1")]["result"]["verified"] is True
        assert nodes[("tests", "once")]["result"]["verified"] is True
        assert nodes[("artifact_check", "once")]["result"]["verified"] is True
        assert view["workflow"]["result"]["output_outcomes"]["verified"] == ["report"]
        assert len(view["workflow"]["result"]["artifacts"]) == 1

        final_attempt_id = view["workflow"]["attempt_run_id"]
        assert final_attempt_id != submission.attempt_run_id, "the child step should park and resume the workflow owner"
        attempt = store.get_run(final_attempt_id)
        workspace = Path(attempt.workspace)
        for relative, content in FIXED_FILES.items():
            written = workspace / relative
            assert written.read_text(encoding="utf-8") == content
        test_output = "\n".join(item.get("output", "")
                                  for item in nodes[("tests", "once")]["result"]["checks"])
        assert "Ran 3 tests" in test_output and "OK" in test_output, test_output

        # Preserve the exact executable plan, scripted repair, and test output alongside
        # the rendered artifacts so this result can be inspected without trusting the UI.
        (EVIDENCE / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
        (EVIDENCE / "provider-repair-response.json").write_text(
            json.dumps(REPAIR_OUTPUT, indent=2, ensure_ascii=False) + "\n")
        (EVIDENCE / "tests-output.txt").write_text(test_output + "\n")

        public_dir = workspace / "public"
        handler = lambda *args, **kwargs: _StaticHandler(*args, directory=str(public_dir), **kwargs)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        port = server.server_address[1]
        page_errors: list[str] = []
        failed_requests: list[str] = []
        viewports = [(1440, 1000, "desktop"), (768, 1024, "tablet"),
                     (360, 800, "phone"), (320, 800, "reflow-320")]
        measurements = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                              reduced_motion="reduce")
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("requestfailed", lambda request: failed_requests.append(request.url))
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                page.get_by_role("heading", name="Review the full regional supplier reconciliation and supporting statements").wait_for()
                assert page.locator("#workflow-steps li").count() == 3
                assert page.get_by_text("The source totals and published summary passed their independent checks.").is_visible()
                summary = page.get_by_text("Open the verified result")
                summary.focus()
                page.keyboard.press("Enter")
                assert page.locator("details").evaluate("el => el.open") is True
                assert page.get_by_text("Four source statements were reconciled.").is_visible()
                for width, height, name in viewports:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(50)
                    metrics = page.evaluate("""() => {
                      const summary = document.querySelector('.result summary');
                      const r = summary.getBoundingClientRect();
                      const s = getComputedStyle(document.querySelector('h1'));
                      return {width: innerWidth, scrollWidth: document.scrollingElement.scrollWidth,
                        bodyScrollWidth: document.body.scrollWidth, titleFont: s.fontFamily,
                        titleSize: s.fontSize, titleLineHeight: s.lineHeight,
                        summaryBounds: {width:r.width,height:r.height},
                        steps: [...document.querySelectorAll('.step')].map(el => ({
                          title: el.querySelector('.step-title').textContent,
                          width: Math.round(el.getBoundingClientRect().width),
                          height: Math.round(el.getBoundingClientRect().height)}))};
                    }""")
                    assert metrics["scrollWidth"] <= width and metrics["bodyScrollWidth"] <= width, metrics
                    assert metrics["summaryBounds"]["height"] >= 24, metrics
                    measurements.append({"viewport": name, "size": [width, height], **metrics})
                    page.screenshot(path=str(EVIDENCE / f"{name}.png"), full_page=True,
                                    animations="disabled")
                page.add_style_tag(content="""
                  *, *::before, *::after { line-height: 1.5 !important;
                    letter-spacing: .12em !important; word-spacing: .16em !important; }
                  p { margin-block-end: 2em !important; }
                """)
                spacing = page.evaluate("""() => ({width:innerWidth,
                  scrollWidth:document.scrollingElement.scrollWidth,
                  summaryHeight:document.querySelector('.result summary').getBoundingClientRect().height,
                  titleHeight:document.querySelector('h1').getBoundingClientRect().height})""")
                assert spacing["scrollWidth"] <= 320 and spacing["summaryHeight"] >= 24, spacing
                assert not page_errors, page_errors
                assert not failed_requests, failed_requests
                context.tracing.stop(path=str(EVIDENCE / "trace.zip"))
                browser_version = browser.version
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
            assert not server_thread.is_alive(), "the temporary UI server did not stop"

        artifacts = sorted(EVIDENCE.glob("*.png")) + [EVIDENCE / "trace.zip"]
        (EVIDENCE / "results.json").write_text(json.dumps({
            "test": "tests/test_workflow_coding_repair_acceptance.py::test_disposable_multi_module_repair_runs_tests_and_inspects_ui",
            "provider": {"server": "scripted Ollama wire-compatible fixture", "model": "tiny:1b",
                         "calls": len(provider.of("/api/chat")), "live_model_quality": "unverified"},
            "workflow": {"status": view["workflow"]["status"], "initial_attempt_id": submission.attempt_run_id,
                         "final_attempt_id": final_attempt_id,
                         "model_calls": view["workflow"]["ledger"]["model_calls"],
                         "repairs": view["workflow"]["ledger"]["repairs"], "verified_nodes": ["repair", "tests", "artifact_check"],
                         "output_outcomes": view["workflow"]["result"]["output_outcomes"]},
            "test_output": test_output,
            "browser": {"name": "chromium", "version": browser_version,
                        "playwright": package_version("playwright"), "reduced_motion": "reduce",
                        "viewports": measurements, "text_spacing_override": spacing,
                        "page_errors": page_errors, "failed_requests": failed_requests},
            "source_sha256": {"test": _sha256(Path(__file__)),
                              "workspace_files": {relative: _sha256(workspace / relative)
                                                  for relative in FIXED_FILES}},
            "artifact_sha256": {path.name: _sha256(path) for path in artifacts},
            "limitations": ["The provider response is scripted; this is runtime and integration evidence, not live model quality.",
                            "The generated files are a disposable test fixture, not a supported workflow scripting language.",
                            "Actual browser zoom and screen-reader testing remain open."],
        }, indent=2, ensure_ascii=False) + "\n")
        assert len(provider.of("/api/chat")) == 1
    finally:
        engine.shutdown()
        provider.close()
