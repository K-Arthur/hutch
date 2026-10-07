"""UI-1 / UI-4 / UI-6: stale detection, wait explanations, meters, failure hints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hutch import views
from hutch.engine import Engine
from hutch.models import (ApprovalMode, ApprovalRequest, Bot, Limits, Run, RunStatus, Schedule, iso, utcnow)
from hutch.scheduler import Scheduler


def mk(store, **kw) -> Bot:
    d = dict(name="viewbot", model="mock/demo", approval_mode=ApprovalMode.auto)
    d.update(kw)
    return store.create_bot(Bot(**d))


def finished(store, bot, status, when, **kw) -> Run:
    run = Run(bot_id=bot.id, prompt="p", status=status, created_at=iso(when), started_at=iso(when),
              finished_at=iso(when + timedelta(seconds=30)), **kw)
    return store.create_run(run)


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)   # a Wednesday
DAILY_9 = Schedule(cron="0 9 * * *", timezone="UTC")


# ------------------------------------------------------------------ staleness

def test_bot_with_no_run_since_its_window_is_stale_and_says_why(store):
    bot = mk(store, schedule=DAILY_9, created_at=iso(NOW - timedelta(days=5)))
    st = views.stale_info(store, Scheduler(store), bot, NOW)
    assert st is not None
    assert "No run was started" in st.cause and "scheduler" in st.cause
    assert "hutch serve" in st.fix or "daemon" in st.fix


def test_recent_success_is_not_stale(store):
    bot = mk(store, schedule=DAILY_9, created_at=iso(NOW - timedelta(days=5)))
    finished(store, bot, RunStatus.succeeded, NOW - timedelta(hours=2))   # ran at 10:00 today
    assert views.stale_info(store, Scheduler(store), bot, NOW) is None


def test_failed_last_window_names_the_failure_and_its_fix(store):
    bot = mk(store, schedule=DAILY_9, created_at=iso(NOW - timedelta(days=5)),
             limits=Limits(timeout_seconds=900))
    finished(store, bot, RunStatus.succeeded, NOW - timedelta(days=3))
    finished(store, bot, RunStatus.failed, NOW - timedelta(hours=3), exit_reason="timeout")
    st = views.stale_info(store, Scheduler(store), bot, NOW)
    assert st and "failed" in st.cause and "900s" in st.cause
    assert "timeout_seconds" in st.fix


def test_paused_unscheduled_and_brand_new_bots_are_never_stale(store):
    sched = Scheduler(store)
    assert views.stale_info(store, sched, mk(store, name="manual"), NOW) is None
    assert views.stale_info(store, sched, mk(store, name="paused", schedule=DAILY_9, paused=True,
                                             created_at=iso(NOW - timedelta(days=9))), NOW) is None
    fresh = mk(store, name="fresh", schedule=DAILY_9, created_at=iso(NOW - timedelta(hours=1)))
    assert views.stale_info(store, sched, fresh, NOW) is None   # has not had a window yet


def test_window_that_just_opened_gets_a_grace_period(store):
    bot = mk(store, schedule=DAILY_9, created_at=iso(NOW - timedelta(days=5)))
    just_after = NOW.replace(hour=9, minute=1)
    assert views.stale_info(store, Scheduler(store), bot, just_after) is None


def test_stale_uses_the_bots_own_timezone(store):
    # 09:00 in Tokyo is 00:00 UTC; at 12:00 UTC the Tokyo window has long passed
    bot = mk(store, schedule=Schedule(cron="0 9 * * *", timezone="Asia/Tokyo"),
             created_at=iso(NOW - timedelta(days=5)))
    st = views.stale_info(store, Scheduler(store), bot, NOW)
    assert st and "JST" in st.cause


# ------------------------------------------------------------------ explanations

def test_queued_behind_the_same_bots_own_run(store, config):
    bot = mk(store)
    running = store.create_run(Run(bot_id=bot.id, prompt="a", status=RunStatus.running))
    queued = store.create_run(Run(bot_id=bot.id, prompt="b"))
    w = views.explain_run(store, queued, Engine(config, store), bot)
    assert "never runs two" in w.cause and running.id[:14] in w.cause and w.fix


def test_queued_because_all_slots_busy_names_the_limit(store, config):
    a, b, c = mk(store, name="aaa"), mk(store, name="bbb"), mk(store, name="ccc")
    store.create_run(Run(bot_id=a.id, prompt="x", status=RunStatus.running))
    store.create_run(Run(bot_id=b.id, prompt="x", status=RunStatus.running))
    queued = store.create_run(Run(bot_id=c.id, prompt="x"))
    w = views.explain_run(store, queued, Engine(config, store, max_concurrent=2), c)
    assert "All 2 run slots" in w.cause and "HUTCH_MAX_CONCURRENT=3" in w.fix


def test_waiting_approval_explains_and_carries_a_deadline(store, config):
    bot = mk(store)
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.waiting_approval))
    exp = iso(utcnow() + timedelta(seconds=300))
    store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="shell", action="$ rm -rf build/",
                                          expires_at=exp))
    w = views.explain_run(store, run, None, bot)
    assert "rm -rf build" in w.cause and "denied at the deadline" in w.fix and w.deadline == exp and w.kind == "action"


def test_cold_load_and_human_pause_are_explained_not_spinners(store):
    bot = mk(store, model="ollama/llama3.1:8b")
    loading = Run(bot_id=bot.id, prompt="x", status=RunStatus.loading_model, model_used="ollama/llama3.1:8b")
    w = views.explain_run(store, loading, None, bot)
    assert "cold load" in w.cause and "not a hang" in w.cause
    human = Run(bot_id=bot.id, prompt="x", status=RunStatus.waiting_human)
    w = views.explain_run(store, human, None, bot)
    assert "never solves" in w.cause and "Resume" in w.fix


def test_every_failure_reason_has_cause_and_fix():
    bot = Bot(name="b", limits=Limits(max_steps=7, timeout_seconds=60, daily_token_cap=1000))
    for reason in ("timeout", "steps_exceeded", "token_cap", "cost_cap", "approval_expired", "loop", "stopped"):
        run = Run(bot_id="x", prompt="p", status=RunStatus.failed if reason != "stopped" else RunStatus.stopped,
                  exit_reason=reason)
        w = views.explain_outcome(run, bot)
        assert w and w.cause and w.fix, reason
    unreachable = Run(bot_id="x", prompt="p", status=RunStatus.failed, exit_reason="error",
                      error="model call failed: Connection refused")
    w = views.explain_outcome(unreachable, bot)
    assert "not reachable" in w.cause and "hutch doctor" in w.fix


# ------------------------------------------------------------------ meters

def test_meters_show_value_against_cap_and_flag_hot(store):
    bot = mk(store, limits=Limits(max_steps=10, timeout_seconds=100, daily_token_cap=1000))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running, steps=9, tokens=400,
                               started_at=iso(utcnow() - timedelta(seconds=30)),
                               context_used=3000, context_limit=4096))
    m = {x.label: x for x in views.run_meters(store, run, bot)}
    assert m["Steps"].value == "9" and m["Steps"].cap == "of 10" and m["Steps"].level == "hot"
    assert m["Elapsed"].cap == "of 2m" or "of" in m["Elapsed"].cap
    assert m["Context"].cap == "of 4.1k" and m["Context"].level == "warn"
    assert "no spend cap" in m["Spend"].note or "local" in m["Spend"].note


def test_timing_split_sums_to_100():
    run = Run(bot_id="x", prompt="p", model_ms=800, tool_ms=150, overhead_ms=50)
    s = views.timing_split(run)
    assert round(sum(s.values())) == 100 and s["overhead"] == 5


# ------------------------------------------------------------------ home

def test_home_state_partitions_needs_running_and_stale(store, config):
    sched = Scheduler(store)
    ok = mk(store, name="okbot")
    bad = mk(store, name="badbot")
    stale = mk(store, name="stalebot", schedule=DAILY_9, created_at=iso(NOW - timedelta(days=4)))
    finished(store, ok, RunStatus.succeeded, NOW - timedelta(hours=1))
    finished(store, bad, RunStatus.failed, NOW - timedelta(hours=1), exit_reason="timeout")
    store.create_run(Run(bot_id=ok.id, prompt="live", status=RunStatus.running))
    run = store.create_run(Run(bot_id=stale.id, prompt="wait", status=RunStatus.waiting_approval))
    store.create_approval(ApprovalRequest(run_id=run.id, bot_id=stale.id, tool="shell", action="$ x"))
    run.status = RunStatus.stopped  # not active (and not a failure), keep the stale bot idle
    store.update_run(run)

    h = views.home_state(store, sched, Engine(config, store), NOW)
    assert [b for _, b in h.approvals] == ["stalebot"]
    assert [b for _, b, _ in h.failures] == ["badbot"]
    assert [b for _, b, _ in h.running] == ["okbot"]
    assert h.needs_count == 2


def test_dismissed_failures_leave_needs_you_and_a_later_success_clears_them(store, config):
    sched = Scheduler(store)
    bot = mk(store)
    r = finished(store, bot, RunStatus.failed, NOW - timedelta(hours=2), exit_reason="timeout")
    assert views.home_state(store, sched, None, NOW).failures
    store.kv_set(f"dismissed:{r.id}", "1")
    assert not views.home_state(store, sched, None, NOW).failures
    r2 = finished(store, bot, RunStatus.failed, NOW - timedelta(hours=1), exit_reason="error")
    assert views.home_state(store, sched, None, NOW).failures
    finished(store, bot, RunStatus.succeeded, NOW - timedelta(minutes=10))
    assert not views.home_state(store, sched, None, NOW).failures
    del r2


def test_timing_is_shown_in_absolute_terms_so_a_mock_run_does_not_read_as_46_percent_hutch():
    run = Run(bot_id="x", prompt="p", steps=4, model_ms=0, tool_ms=4.0, overhead_ms=0.9)
    t = views.timing_abs(run)
    assert round(t["per_step_ms"], 3) == 0.225 and t["total_ms"] == 4.9
    assert views.fmt_ms(0.225) == "0.23 ms" and views.fmt_ms(840) == "840 ms" and views.fmt_ms(2500) == "2.5 s"


def test_arg_summaries_are_one_readable_line():
    assert views.arg_summary("shell", {"command": "git status\n&& ls"}) == "git status && ls"
    assert views.arg_summary("write_file", {"path": "report.md", "content": "x" * 323}) == "report.md (323 chars)"
    assert views.arg_summary("remember", {"key": "k", "value": "v"}) == "k = v"
    assert views.arg_summary("shell", {"command": "x" * 500}).endswith("...")
    assert views.fmt_tokens(200_000) == "200k" and views.fmt_tokens(1_100) == "1.1k"
    assert views.output_summary("\n\nexit=0\nfoo") == "exit=0"
