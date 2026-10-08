"""T-APPROVAL-CAS: a decision is made once, for the exact action shown, before its deadline.

Baseline defect: resolve_approval read the row, checked 'pending', then wrote - so two clients (or a client and the timeout) could
both pass the check, and "always allow" could be granted by the loser. An approval also was not tied to the action it was shown for.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from datetime import timedelta
from pathlib import Path

import pytest

from hutch.approvals import ApprovalGate, DeniedError, action_fingerprint, expire_stale_approvals, resolve_approval, resolve_approval_ex
from hutch.models import ApprovalMode, ApprovalRequest, ApprovalStatus, Bot, Run, RunStatus, iso, utcnow
from hutch.safety import PolicyEngine

SRC = str(Path(__file__).resolve().parents[1] / "src")


def test_stop_expires_existing_and_late_approvals_without_a_sticky_grant(store):
    req = make_req(store)
    store.request_cancel(req.run_id)
    assert store.pending_approvals() == []
    old = store.get_approval(req.id)
    assert old.status is ApprovalStatus.expired and old.decided_by == "stopped"
    assert not resolve_approval_ex(store, req.id, True, by="late-client", sticky=True).won
    assert not store.is_sticky_allowed(req.bot_id, req.sticky_key)
    later = store.create_approval(ApprovalRequest(
        run_id=req.run_id, bot_id=req.bot_id, tool="files", action="late request", detail={"content": "fixture"}))
    assert later.status is ApprovalStatus.expired and later.decided_by == "stopped"
    assert store.pending_approvals() == []


def test_stale_worker_cannot_create_an_approval_after_ownership_changed(store):
    from hutch.lifecycle import LeaseLost
    bot = store.create_bot(Bot(name="stale-review"))
    run = store.create_run(Run(bot_id=bot.id, prompt="fixture"))
    claimed = store.claim_run(run.id, "new-owner", 30)
    assert claimed.fence > run.fence
    with pytest.raises(LeaseLost, match="stale ownership"):
        store.create_approval(ApprovalRequest(
            run_id=run.id, bot_id=bot.id, tool="files", action="stale request"), expected_fence=run.fence)
    assert store.pending_approvals() == []


def make_req(store, **kw) -> ApprovalRequest:
    bot = store.get_bot("b") or store.create_bot(Bot(name="b", model="mock/demo", tools=["shell"]))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    detail = {"command": "rm -rf build/"}
    req = ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="shell", action="$ rm -rf build/", detail=detail,
                          sticky_key="shell:rm", expires_at=iso(utcnow() + timedelta(seconds=600)),
                          action_hash=action_fingerprint("shell", detail, "shell:rm"), **kw)
    return store.create_approval(req)


def test_two_resolutions_exactly_one_wins_and_the_loser_changes_nothing(store):
    req = make_req(store)
    first = resolve_approval_ex(store, req.id, True, by="alice", sticky=True)
    second = resolve_approval_ex(store, req.id, False, by="bob")
    assert first.won and first.outcome == "won"
    assert not second.won and second.outcome == "already"
    final = store.get_approval(req.id)
    assert final.status is ApprovalStatus.approved and final.decided_by == "alice"
    assert store.is_sticky_allowed(final.bot_id, "shell:rm")


def test_the_loser_cannot_grant_an_always_allow(store):
    req = make_req(store)
    assert resolve_approval_ex(store, req.id, False, by="alice").won                      # denied first
    late = resolve_approval_ex(store, req.id, True, by="bob", sticky=True)                # tries to approve + remember
    assert late.outcome == "already" and not store.is_sticky_allowed(req.bot_id, "shell:rm")


RACER = """
    import os, sys, time
    sys.path.insert(0, {src!r})
    from pathlib import Path
    from hutch.config import get_config
    from hutch.store import Store
    from hutch.approvals import resolve_approval_ex
    store = Store(get_config())
    while not Path({go!r}).exists():
        time.sleep(0.001)
    r = resolve_approval_ex(store, {aid!r}, approve={approve}, by=f"proc-{{os.getpid()}}", sticky={approve})
    print(r.outcome)
    store.close()
"""


def test_processes_racing_to_approve_and_deny_produce_one_decision(store, config):
    req = make_req(store)
    go = config.state_dir / "GO"
    env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir))
    procs = [subprocess.Popen([sys.executable, "-I", "-c", textwrap.dedent(RACER).format(src=SRC, go=str(go), aid=req.id,
                                                                                      approve=(i % 2 == 0))],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(6)]
    time.sleep(1.5)
    go.write_text("go")
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        outs.append(out.strip())
    assert outs.count("won") == 1 and outs.count("already") == 5
    final = store.get_approval(req.id)
    assert final.status in (ApprovalStatus.approved, ApprovalStatus.denied)
    # "always allow" exists only if the winner was an approver
    assert store.is_sticky_allowed(req.bot_id, "shell:rm") == (final.status is ApprovalStatus.approved)


def test_an_expired_approval_cannot_be_approved_late(store):
    req = make_req(store)
    store._db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (iso(utcnow() - timedelta(seconds=1)), req.id))
    store._db.commit()
    res = resolve_approval_ex(store, req.id, True, by="alice", sticky=True)
    assert res.outcome == "expired" and not res.won
    final = store.get_approval(req.id)
    assert final.status is ApprovalStatus.expired and final.decided_by == "timeout"       # silence is never consent
    assert not store.is_sticky_allowed(req.bot_id, "shell:rm")


def test_an_approval_is_only_valid_for_the_action_it_was_shown_for(store):
    req = make_req(store)
    shown = req.action_hash
    revised = action_fingerprint("shell", {"command": "rm -rf /home/me"}, "shell:rm")
    assert revised != shown                                                                # editing the action changes its identity
    res = resolve_approval_ex(store, req.id, True, by="alice", expected_hash=revised)
    assert res.outcome == "mismatch" and store.get_approval(req.id).status is ApprovalStatus.pending
    assert resolve_approval_ex(store, req.id, True, by="alice", expected_hash=shown).won


def test_the_fingerprint_depends_on_every_relevant_part():
    base = action_fingerprint("shell", {"command": "git push origin main"}, "shell:git")
    assert base == action_fingerprint("shell", {"command": "git push origin main"}, "shell:git")
    assert base != action_fingerprint("shell", {"command": "git push origin dev"}, "shell:git")       # arguments
    assert base != action_fingerprint("browser", {"command": "git push origin main"}, "shell:git")    # tool
    assert base != action_fingerprint("shell", {"command": "git push origin main"}, "shell:git", outward=True)
    assert action_fingerprint("browser", {"url": "https://a.example"}) != action_fingerprint("browser", {"url": "https://b.example"})


def test_a_timeout_does_not_overwrite_a_decision_that_arrived_first(store):
    req = make_req(store)
    assert resolve_approval_ex(store, req.id, True, by="alice").won
    store._db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (iso(utcnow() - timedelta(seconds=1)), req.id))
    store._db.commit()
    assert expire_stale_approvals(store) == []                                             # nothing pending: nothing to expire
    assert store.get_approval(req.id).status is ApprovalStatus.approved


def test_the_gate_honours_a_decision_that_lands_at_the_deadline(store, config, tmp_path, monkeypatch):
    """The gate's own timeout is the same compare-and-swap: if a person decided first, that decision stands."""
    bot = store.create_bot(Bot(name="g", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.ask))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda ev: store.append_event(ev), poll_seconds=0.01)
    gate.ttl = 1                                                          # the approval times out after one second
    real = store.decide_approval

    def human_first(approval_id, status, by, **kw):
        if status is ApprovalStatus.expired and by == "timeout":
            store._db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?",   # the stored deadline is still open ...
                              (iso(utcnow() + timedelta(seconds=30)), approval_id))
            store._db.commit()
            real(approval_id, ApprovalStatus.approved, "alice")           # ... when the person clicks, as the gate's timer fires
        return real(approval_id, status, by, **kw)

    monkeypatch.setattr(store, "decide_approval", human_first)
    gate.decide("shell", "$ touch x", {"command": "touch x"})            # must return (approved), not raise DeniedError
    [a] = store.recent_approvals()
    assert a.status is ApprovalStatus.approved and a.decided_by == "alice"


def test_the_api_reports_a_lost_race_and_a_changed_action_as_409(store, config, monkeypatch):
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app
    with TestClient(create_app()) as c:
        st = c.app.state.store
        req = make_req(st)
        c.get("/api/health")
        bad = c.post(f"/api/approvals/{req.id}/approve", json={"action_hash": "0" * 32})
        assert bad.status_code == 409 and "changed" in bad.json()["detail"]
        ok = c.post(f"/api/approvals/{req.id}/approve", json={"action_hash": req.action_hash})
        assert ok.status_code == 200
        again = c.post(f"/api/approvals/{req.id}/deny")
        assert again.status_code == 409 and "already" in again.json()["detail"]
        gone = c.post("/api/approvals/apr_nope/approve", json={})
        assert gone.status_code == 404
        listing = c.get("/api/approvals").json()
        assert listing == []                                                              # decided: no longer pending
