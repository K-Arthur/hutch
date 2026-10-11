#!/usr/bin/env python3
"""Capture dynamic-workflow acceptance evidence with the real product CLI.

Runs the mission's non-coding scenario (a sizeable messy CSV becomes a verified report)
against a throwaway state directory using ``hutch workflow`` commands only, and writes the
evidence next to the artifact:

* ``validation.json``: plan hash, node records, artifact identity, the published report
  text, every command with its exit code, environment versions and what was NOT verified;
* ``expense-report.md``: the published artifact bytes, copied out of the run directory and
  re-hashed against the digest the engine recorded.

The script fails (non-zero) if the workflow does not succeed, if the CLI never shows the
pending question, or if the copied artifact does not match its recorded hash.

Usage:  .venv/bin/python docs/realignment/capture_workflow_acceptance.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "docs" / "realignment" / "artifacts" / "dynamic-workflows"
PYTHON = str(ROOT / ".venv" / "bin" / "python")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_workflow_csv_acceptance import csv_plan, messy_csv  # noqa: E402


class Capture:
    def __init__(self, state: str):
        self.state = state
        self.commands: list[dict] = []

    def run(self, args: list[str], check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
        env = dict(os.environ, HUTCH_STATE_DIR=self.state, HUTCH_SANDBOX="off")
        result = subprocess.run([PYTHON, "-m", "hutch.cli", *args], env=env, cwd=str(ROOT),
                                capture_output=True, text=True, timeout=timeout)
        self.commands.append({"args": args, "exit_code": result.returncode,
                              "stdout": result.stdout[-4_000:], "stderr": result.stderr[-2_000:]})
        if check and result.returncode != 0:
            raise SystemExit(f"command failed ({result.returncode}): {' '.join(args)}\n"
                             f"{result.stdout}\n{result.stderr}")
        return result


def main() -> int:
    state = tempfile.mkdtemp(prefix="hutch-workflow-evidence-")
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / "expense-audit.plan.json"
    plan_path.write_text(json.dumps(csv_plan(), indent=2) + "\n", encoding="utf-8")
    csv_text = messy_csv()
    (OUT / "sample-messy.csv").write_text(csv_text, encoding="utf-8")

    capture = Capture(state)
    capture.run(["init"])
    capture.run(["bot", "create", "evidence-bot", "--display-name", "Evidence Bot",
                 "--model", "ollama/qwen3:4b", "--tools", "files", "--approvals", "ask"])
    validated = capture.run(["workflow", "validate", str(plan_path), "--bot", "evidence-bot"])
    saved = capture.run(["workflow", "save", str(plan_path), "--name", "expense-audit",
                         "--note", "acceptance capture"])

    # Start the run with the CLI and read the pending question from *its own* output, then
    # answer it with the CLI. Nothing here reaches into the database to drive the product.
    env = dict(os.environ, HUTCH_STATE_DIR=state, HUTCH_SANDBOX="off")
    proc = subprocess.Popen(
        [PYTHON, "-m", "hutch.cli", "workflow", "run", "expense-audit", "--bot", "evidence-bot",
         "--input", f"csv={json.dumps(csv_text)}", "--input", "period=FY26 Q3"],
        env=env, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output, question_id = "", ""
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline and not question_id:
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        # The run prints "answer with: hutch workflow answer <id> \"...\"" while it waits.
        try:
            output += proc.stdout.readline() if proc.stdout else ""
        except Exception:
            break
        if "hutch workflow answer" in output:
            for line in output.splitlines():
                if "hutch workflow answer" in line:
                    question_id = line.split("hutch workflow answer", 1)[1].strip().split()[0]
    if question_id:
        capture.run(["workflow", "answer", question_id, "yes"])
    try:
        rest = proc.communicate(timeout=180)[0] or ""
    except subprocess.TimeoutExpired:
        proc.kill()
        rest = ""
    output += rest
    capture.commands.append({"args": ["workflow", "run", "expense-audit", "--bot", "evidence-bot"],
                             "exit_code": proc.returncode, "stdout": output[-6_000:], "stderr": ""})

    from hutch.config import hutchConfig
    from hutch.store import Store
    from hutch.workflow import persistence as wstore

    config = hutchConfig(state_dir=Path(state))
    store = Store(config)
    try:
        runs = wstore.list_workflow_runs(store)
        workflow = runs[0] if runs else {}
        wf_id = str(workflow.get("id") or "")
        nodes = wstore.nodes(store, wf_id) if wf_id else []
        questions = wstore.questions(store, wf_id) if wf_id else []
        revision = wstore.revision(store, str(workflow.get("revision_id"))) if wf_id else None
        attempt = str(workflow.get("attempt_run_id") or "")
        events = [{"seq": event.seq, "type": event.type.value, "data": event.data}
                  for event in store.tail_events(attempt, limit=200)] if attempt else []
    finally:
        store.close()

    report_text = ""
    for node in nodes:
        if node["site_id"] == "report" and node["status"] == "succeeded":
            report_text = str(node["result"])
    published = next((item for item in (workflow.get("result") or {}).get("artifacts", [])
                      if item.get("name") == "expense-report"), {})
    copied = ""
    artifact_match = False
    if attempt and published:
        run_dir = config.run_dir("evidence-bot", attempt)
        source = run_dir / str(published["artifact"])
        if source.is_file():
            content = source.read_bytes()
            copied = str(published["artifact"])
            (OUT / "expense-report.md").write_bytes(content)
            artifact_match = hashlib.sha256(content).hexdigest() == published.get("sha256")

    evidence = {
        "captured": "2026-10-11",
        "scenario": "messy CSV -> observed-column branch -> deterministic totals -> published "
                    "report -> schema+artifact+human verification, zero model calls",
        "commands": capture.commands,
        "validate_stdout": validated.stdout,
        "save_stdout": saved.stdout,
        "run_stdout": output,
        "question_id_from_cli": question_id,
        "plan_hash": (revision or {}).get("plan_hash", ""),
        "workflow": {k: workflow.get(k) for k in
                     ("id", "status", "reason", "origin", "attempt_run_id", "ledger", "result")},
        "nodes": [{"site_id": n["site_id"], "instance_key": n["instance_key"], "kind": n["kind"],
                   "status": n["status"], "attempt": n["attempt"],
                   "result_digest": hashlib.sha256(
                       json.dumps(n["result"], sort_keys=True, default=str).encode()).hexdigest()[:16],
                   "error": n["error"]} for n in nodes],
        "questions": [{"site_id": q["site_id"], "status": q["status"], "answer": q["answer"]}
                      for q in questions],
        "report_text": report_text,
        "artifact": {**published, "copied_to": copied, "copied_bytes_match_recorded_sha256": artifact_match},
        "events": events,
        "environment": {"python": sys.version.split()[0],
                        "sandbox": "HUTCH_SANDBOX=off (no Linux shell containment in this capture)",
                        "state_dir": "a throwaway temporary directory (not included)"},
        "not_verified": [
            "no live local model server exists on this host, so no model-authored plan, planner "
            "role or worker step ran here; the deterministic path is what this capture proves",
            "the plan and sample CSV are generated by tests/test_workflow_csv_acceptance.py",
            "the human answer was given by this capture script through the CLI, not by a person",
            "no browser/UI surface was exercised (the Studio workflow view is a later slice)",
        ],
    }
    (OUT / "validation.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    status = workflow.get("status")
    print(f"wrote {OUT / 'validation.json'}")
    print(f"workflow status: {status} — {workflow.get('reason')}")
    print(f"question id seen by the CLI: {question_id or '(none)'}")
    print(f"artifact copy matches recorded sha256: {artifact_match}")
    if status != "succeeded" or not question_id or not artifact_match:
        print("CAPTURE FAILED: the evidence does not support a success claim", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
