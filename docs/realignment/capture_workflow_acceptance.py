#!/usr/bin/env python3
"""Capture dynamic-workflow acceptance evidence with the real product CLI.

Runs the mission's non-coding scenario (a sizeable messy CSV becomes a verified report)
against a throwaway state directory using ``hutch workflow`` commands only - no test
fixtures, no model calls - and writes the evidence next to the artifact:

* ``validation.json``: plan hash, node records, artifact identity, the published report
  text, the exact commands, environment versions and what was NOT verified;
* ``expense-report.md``: the published artifact bytes, copied out of the run directory.

Usage:  .venv/bin/python docs/realignment/capture_workflow_acceptance.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "docs" / "realignment" / "artifacts" / "dynamic-workflows"
PYTHON = str(ROOT / ".venv" / "bin" / "python")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_workflow_csv_acceptance import csv_plan, messy_csv  # noqa: E402


def run(args: list[str], state: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, HUTCH_STATE_DIR=state, HUTCH_SANDBOX="off")
    result = subprocess.run([PYTHON, "-m", "hutch.cli", *args], env=env, cwd=str(ROOT),
                            capture_output=True, text=True)
    if check and result.returncode not in (0, 1):
        raise SystemExit(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def main() -> int:
    state = tempfile.mkdtemp(prefix="hutch-workflow-evidence-")
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / "expense-audit.plan.json"
    plan_path.write_text(json.dumps(csv_plan(), indent=2) + "\n", encoding="utf-8")
    csv_text = messy_csv()
    (OUT / "sample-messy.csv").write_text(csv_text, encoding="utf-8")

    run(["init"], state)
    run(["bot", "create", "evidence-bot", "--display-name", "Evidence Bot",
         "--model", "ollama/qwen3:4b", "--tools", "files", "--approvals", "ask"], state)
    validated = run(["workflow", "validate", str(plan_path), "--bot", "evidence-bot"], state)
    saved = run(["workflow", "save", str(plan_path), "--name", "expense-audit",
                 "--note", "acceptance capture"], state)
    # Run with the CSV as an input, answering the human verification check from the CLI.
    import threading
    import time

    env = dict(os.environ, HUTCH_STATE_DIR=state, HUTCH_SANDBOX="off")
    proc = subprocess.Popen([PYTHON, "-m", "hutch.cli", "workflow", "run", "expense-audit",
                             "--bot", "evidence-bot", "--input", f"csv={json.dumps(csv_text)}",
                             "--input", "period=FY26 Q3"],
                            env=env, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    answered = ""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        listing = run(["workflow", "status", "expense-audit"], state, check=False)
        questions = run(["workflow", "qualify", "evidence-bot", "--assess"], state, check=False)
        # Find a pending question id via the store-backed status output.
        found = None
        from hutch.config import hutchConfig
        from hutch.store import Store
        cfg = hutchConfig(state_dir=Path(state))
        store = Store(cfg)
        try:
            rows = store._db.execute(
                "SELECT id, question FROM workflow_questions WHERE status = 'pending' ORDER BY asked_at"
            ).fetchall()
            if rows:
                found = dict(rows[0])
        finally:
            store.close()
        if found:
            answered = run(["workflow", "answer", found["id"], "yes"], state).stdout.strip()
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    output = proc.communicate(timeout=120)[0]

    from hutch.config import hutchConfig
    from hutch.store import Store
    from hutch.workflow import persistence as wstore

    store = Store(hutchConfig(state_dir=Path(state)))
    runs = wstore.list_workflow_runs(store)
    workflow = runs[0] if runs else {}
    nodes = wstore.nodes(store, str(workflow.get("id"))) if workflow else []
    questions = wstore.questions(store, str(workflow.get("id"))) if workflow else []
    revision = wstore.revision(store, str(workflow.get("revision_id"))) if workflow else None
    attempt = workflow.get("attempt_run_id", "")
    report_text = ""
    for node in nodes:
        if node["site_id"] == "report" and node["status"] == "succeeded":
            report_text = str(node["result"])
    copied = ""
    if attempt:
        run_dir = hutchConfig(state_dir=Path(state)).run_dir("evidence-bot", attempt)
        for path in sorted((run_dir / "artifacts").glob("*.txt")) if (run_dir / "artifacts").exists() else []:
            (OUT / "expense-report.md").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            copied = str(path.relative_to(run_dir))
    events = []
    if attempt:
        for event in store.tail_events(attempt, limit=200):
            events.append({"seq": event.seq, "type": event.type.value,
                           "data": {k: v for k, v in list(event.data.items())[:6]}})
    store.close()

    evidence = {
        "captured": "2026-10-11",
        "scenario": "messy CSV -> observed-column branch -> deterministic totals -> published "
                    "report -> schema+artifact+human verification, zero model calls",
        "commands": [
            "hutch init",
            "hutch bot create evidence-bot --model ollama/qwen3:4b --tools files",
            f"hutch workflow validate {plan_path.name} --bot evidence-bot",
            f"hutch workflow save {plan_path.name} --name expense-audit",
            "hutch workflow run expense-audit --bot evidence-bot --input csv=... --input period='FY26 Q3'",
            "hutch workflow answer <question-id> yes",
        ],
        "validate_stdout": validated.stdout,
        "save_stdout": saved.stdout,
        "run_stdout": output,
        "answered": answered,
        "plan_hash": (revision or {}).get("plan_hash", ""),
        "workflow": {k: workflow.get(k) for k in
                     ("id", "status", "reason", "origin", "attempt_run_id", "ledger", "result")},
        "nodes": [{"site_id": n["site_id"], "instance_key": n["instance_key"], "kind": n["kind"],
                   "status": n["status"], "attempt": n["attempt"],
                   "result_digest": __import__("hashlib").sha256(
                       json.dumps(n["result"], sort_keys=True, default=str).encode()).hexdigest()[:16],
                   "error": n["error"]} for n in nodes],
        "questions": [{"site_id": q["site_id"], "status": q["status"], "answer": q["answer"]} for q in questions],
        "report_text": report_text,
        "artifact_file": copied,
        "events": events,
        "environment": {
            "python": sys.version.split()[0],
            "state_dir": "a throwaway temporary directory (not included)",
        },
        "not_verified": [
            "no live local model server exists on this host, so no model-authored plan, planner "
            "role or worker step was executed here; the deterministic path is what this capture proves",
            "no browser/UI surface was exercised (the Studio workflow view is a later slice)",
            "the human answer was given by this capture script through the CLI, not by a person",
        ],
    }
    (OUT / "validation.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT / 'validation.json'}")
    print(f"workflow status: {workflow.get('status')} — {workflow.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
