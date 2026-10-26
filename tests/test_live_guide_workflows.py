"""Opt-in model evaluations of guide-derived local work, not live-service parity.

Synthetic inputs only. Independent checks inspect saved files and canonical
receipts; the assistant's completion text is never the success oracle.
"""

import csv
import hashlib
import json
import threading
import time

import pytest

from hutch.models import ApprovalMode, Limits, RuntimeKind
from hutch.runtime.opencode import OpenCodeRuntime
from hutch.runtime.instructions import build_system_prompt
from tests.support.artifacts import artifact_path
from tests.test_opencode_memory_bridge import LIVE_MODEL, _live_owner, live_opencode_auth, requires_live  # noqa: F401
from tests.test_runtime_builtin import build, run_it


CASES = {
    "marketing": {
        "input": "Synthetic product: Cedar, a local document assistant. Verified features: drafts document briefs; requires review before sharing; local state. Competitor Birch: browser-only, $12/month. Source https://example.com/fixture/birch . Competitor Elm: hosted, $20/month. Source https://example.com/fixture/elm . No evidence that any product is SOC2 certified or has better conversion rates.",
        "request": "Write positioning.md with a concise positioning recommendation, two distinct campaign ideas, the two source URLs, and a clear statement that these are synthetic fixtures. Keep all campaign work as drafts for review; do not invent certification or performance claims.",
        "file": "positioning.md",
    },
    "performance": {
        "input": "campaign,impressions,clicks,spend,conversions,revenue,daily_budget\nSearch,10000,1000,300,20,1000,250\nSocial,20000,400,150,0,0,200\n",
        "request": "Write metrics.csv with exactly one row per campaign and columns campaign,ctr,cvr,cpa,roas,alert. CTR and CVR must be decimal fractions, not percentages. Round numerical metrics to four decimal places or fewer. Leave undefined CPA empty. Flag Search as over_budget, Social as zero_conversions. Then write recommendations.md with recommendations explicitly requiring approval before changing spend. Do not change any campaigns.",
        "file": "metrics.csv",
    },
    "sales": {
        "input": "id,company,contact,status,do_not_contact\na,Birch,Ada,prospect,true\nb,Elm,Ben,active_deal,false\nc,Fir,Cam,customer,false\nd,Cedar,Dee,prospect,false\n",
        "request": "Use only eligible prospects: exclude do-not-contact entries, active deals and existing customers. Write outreach.csv with columns id,company,contact,draft,status and exactly one eligible row. Set status to draft_needs_approval. Write founder-summary.md naming the three suppression reasons and stating that nothing was sent. Do not invent contact email addresses or send messages.",
        "file": "outreach.csv",
    },
}


def _verify(case, workspace):
    if case == "marketing":
        text = (workspace / "positioning.md").read_text()
        assert "https://example.com/fixture/birch" in text
        assert "https://example.com/fixture/elm" in text
        assert "synthetic" in text.lower() and "draft" in text.lower()
        assert "Cedar" in text
    elif case == "performance":
        with (workspace / "metrics.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 2
        indexed = {row["campaign"]: row for row in rows}
        search, social = indexed["Search"], indexed["Social"]
        assert float(search["ctr"]) == pytest.approx(.1)
        assert float(search["cvr"]) == pytest.approx(.02)
        assert float(search["cpa"]) == pytest.approx(15)
        assert float(search["roas"]) == pytest.approx(3.3333, abs=.0001)
        assert search["alert"] == "over_budget"
        assert float(social["ctr"]) == pytest.approx(.02)
        assert float(social["cvr"]) == 0 and social["cpa"] == ""
        assert social["alert"] == "zero_conversions"
        assert "approv" in (workspace / "recommendations.md").read_text().lower()
    else:
        with (workspace / "outreach.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1 and rows[0]["id"] == "d"
        assert rows[0]["status"] == "draft_needs_approval" and rows[0]["draft"].strip()
        summary = (workspace / "founder-summary.md").read_text().lower()
        assert "sent" in summary and ("not" in summary or "nothing" in summary)


@requires_live
@pytest.mark.parametrize("case", CASES)
def test_live_opencode_guide_local_artifacts(store, config, tmp_path, live_opencode_auth, case):
    fixture = CASES[case]
    ctx, run, _events, tools = build(store, config, tmp_path,
        model=LIVE_MODEL, runtime=RuntimeKind.opencode, tools=["files"], mode=ApprovalMode.auto,
        prompt=f"Read input.txt in your working folder. {fixture['request']} Use Hutch read_file and write_file tools. Return only a short summary when finished.",
        instructions="Complete the requested synthetic fixture task accurately. Do not access networks or run shell commands. All output is a draft. Use canonical Hutch tools for saved files.",
        limits=Limits(max_steps=12, max_turn_tokens=4096, timeout_seconds=180, daily_token_cap=1_000_000))
    (ctx.workspace / "input.txt").write_text(fixture["input"])
    _live_owner(store, run)
    deadline = threading.Timer(180, lambda: setattr(ctx.gate, "cancel_requested", True))
    started = time.monotonic()
    deadline.start()
    evidence = {"case": case, "route": LIVE_MODEL, "scope": "synthetic local artifacts; external services unverified",
                "functional_checks_passed": False, "quality_review": "required separately",
                "system_prompt_sha256": hashlib.sha256(build_system_prompt(ctx).encode()).hexdigest(),
                "fixture_sha256": hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()}
    try:
        answer = run_it(OpenCodeRuntime(), run, ctx, tools)
        _verify(case, ctx.workspace)
        receipts = [action for action in store.list_actions(run.id)
                    if action["tool"] == "write_file" and action["status"] == "done"]
        assert receipts, "saved artifacts must have canonical Hutch effect receipts"
        evidence.update(functional_checks_passed=True, answer=answer, done_receipts=len(receipts))
    finally:
        deadline.cancel()
        evidence.update(elapsed_seconds=round(time.monotonic() - started, 2), tokens=store.get_run(run.id).tokens)
        out = artifact_path(f"opencode-guide-evaluation/{case}")
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
        for path in ctx.workspace.iterdir():
            if path.is_file() and path.suffix in {".md", ".csv", ".txt"}:
                (out / path.name).write_bytes(path.read_bytes())
