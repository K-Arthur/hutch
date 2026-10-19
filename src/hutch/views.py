"""View-model logic shared by the dashboard and the CLI.

Everything a person needs to read the system's state at a glance lives here, free of web
dependencies so it is unit-testable:

* ``explain_run``   — UI-6: every waiting state names its **cause** and a **fix**. No bare spinners.
* ``explain_outcome`` — the same for finished runs that did not succeed.
* ``stale_info``    — UI-1: a scheduled bot whose last success is older than its schedule implies.
* ``home_state``    — UI-1: *Needs you* / *Running now* / *Stale*.
* ``run_meters``    — UI-4: steps, elapsed time, spend, tokens and context against their caps.

The research behind the shapes (n8n "active but silently failing", Grok Bot "no context meter",
Dots/Grok "opaque waits") is in docs/research/offerings-and-failures.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .lifecycle import TERMINAL
from .models import ACTIVE_STATUSES, Bot, Run, RunStatus, iso, utcnow

FINISHED = tuple(TERMINAL)    # one definition: hutch.lifecycle

# ------------------------------------------------------------------ formatting


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def timeago(value: Optional[str], now: Optional[datetime] = None) -> str:
    dt = parse_ts(value)
    if dt is None:
        return "never"
    s = ((now or utcnow()) - dt).total_seconds()
    if s < 0:
        return "in " + fmt_duration(-s)
    if s < 45:
        return "just now"
    return fmt_duration(s) + " ago"


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{round(seconds / 60)}m"
    if seconds < 172800:
        return f"{round(seconds / 3600)}h"
    return f"{round(seconds / 86400)}d"


def fmt_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def fmt_money(usd: float) -> str:
    if usd == 0:
        return "$0"
    return f"${usd:.4f}" if usd < 0.01 else f"${usd:.2f}"


def fmt_tokens(n: float) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1e3:.1f}k".replace(".0k", "k")
    return str(n)


def origin_label(run: Run) -> str:
    """SR-7: who or what started this run."""
    o = run.origin or "manual"
    if o == "schedule":
        return "schedule"
    if o.startswith("plan") or run.plan_id:
        return f"plan {run.plan_id or ''}".strip()
    if o.startswith("manual:"):
        return f"you ({o.split(':', 1)[1]})"
    return "you" if o == "manual" else o


# ------------------------------------------------------------------ explanations


@dataclass
class Wait:
    """A state explained: what is happening, why, and what to do about it."""

    cause: str
    fix: str
    href: str = ""
    link_text: str = ""
    kind: str = "wait"      # wait (informational) | action (needs a human) | error
    deadline: Optional[str] = None  # ISO time shown as a countdown


def _approvals_for(store, run_id: str):
    return [a for a in store.pending_approvals() if a.run_id == run_id]


def explain_run(store, run: Run, engine: Any = None, bot: Optional[Bot] = None) -> Optional[Wait]:
    """The cause and fix for a run that is not simply running. None when nothing needs explaining."""
    st = run.status
    if st is RunStatus.pending:
        active = [r for r in store.active_runs() if r.id != run.id and r.status is not RunStatus.pending]
        same_bot = next((r for r in active if r.bot_id == run.bot_id), None)
        if same_bot is not None:
            return Wait(
                cause=f"Queued behind this bot's own run {same_bot.id[:14]}. A bot never runs two jobs at once, "
                      "so schedules and manual runs cannot overlap.",
                fix="Wait for it to finish, or stop it.", href=f"/runs/{same_bot.id}",
                link_text="open the running job")
        if engine is not None and len([r for r in active]) >= getattr(engine, "max_concurrent", 2):
            n = getattr(engine, "max_concurrent", 2)
            return Wait(
                cause=f"All {n} run slots are busy. Runs start in order as slots free up.",
                fix=f"Stop a running job, or raise the limit (HUTCH_MAX_CONCURRENT={n + 1}).",
                href="/?view=running", link_text="see what is running")
        if getattr(engine, "slot_reason", None):
            reason = engine.slot_reason(run)
            if reason:
                return reason
        return Wait(cause="Queued; the dispatcher picks it up as soon as a slot is free.",
                    fix="Nothing to do. If it stays here, the scheduler may not be running: `hutch doctor`.",
                    href="", kind="wait")
    if st is RunStatus.loading_model:
        model = run.model_used or (bot.model if bot else "the model")
        return Wait(
            cause=f"Loading {model} into memory (a cold load). The first request after a model is evicted "
                  "pays this; it is not a hang.",
            fix="Keep it resident (Ollama keep_alive) or pick a smaller model on the Models page.",
            href="/models", link_text="Models")
    if st is RunStatus.waiting_approval:
        mine = _approvals_for(store, run.id)
        if mine:
            a = mine[0]
            return Wait(
                cause=f"Needs your decision: {a.action}",
                fix="Approve once, approve always for this bot, or deny. Unanswered, it is denied at the deadline.",
                href=f"/approvals#{a.id}", link_text="Open the approval", kind="action",
                deadline=a.expires_at)
        return Wait(cause="Waiting on an approval that has just been resolved.", fix="It resumes in a moment.")
    if st is RunStatus.waiting_human:
        if bot and bot.local_browser_handoff:
            return Wait(
                cause="The bot's browser is paused for a login, CAPTCHA or two-factor step.",
                fix="Complete the step in the visible Hutch browser window, then resume this run.",
                href=f"/runs/{run.id}", link_text="Open the run", kind="action")
        return Wait(
            cause="A browser login step needs a person, but this run has no live desktop handoff.",
            fix="Enable Local browser handoff for this bot on a Linux desktop, then start the task again.",
            href=f"/runs/{run.id}", link_text="Open the run", kind="action")
    if st is RunStatus.waiting_workflow:
        return Wait(
            cause=run.reason or "The workflow is waiting for a child step or an answer.",
            fix="Hutch released the worker slot. A fresh attempt starts when every outstanding step and question settles.",
            href=f"/runs/{run.id}", link_text="Open the workflow", kind="wait")
    if st is RunStatus.waiting_child:
        return Wait(
            cause=run.reason or "The delegated child is working on its bounded task.",
            fix="Hutch released the parent worker. The same conversation resumes after child work and cleanup finish.",
            href=f"/runs/{run.id}", link_text="Open the run", kind="wait")
    return None


_ERROR_HINTS = (
    ("connection refused", "The model server is not reachable.",
     "Start it (for Ollama: `ollama serve`), check the bot's model/base_url, then run `hutch doctor`."),
    ("connection error", "The model server is not reachable.",
     "Start it, check the bot's model/base_url, then run `hutch doctor`."),
    ("api key", "The provider rejected the request for a missing or invalid API key.",
     "Set the key in the environment (e.g. OPENAI_API_KEY / ANTHROPIC_API_KEY) and re-run."),
    ("401", "The provider rejected the credentials.", "Check the API key for this provider."),
    ("429", "The provider rate-limited the request.",
     "Add a fallback model to the bot, or retry later."),
    ("context", "The prompt did not fit the model's context window.",
     "Choose a model with a larger window, raise num_ctx, or shorten the instructions/tools."),
)


def explain_outcome(run: Run, bot: Optional[Bot] = None) -> Optional[Wait]:
    """Cause and fix for a finished run that did not succeed."""
    if run.status is RunStatus.succeeded:
        return None
    lim = bot.limits if bot else None
    r = run.exit_reason
    if run.status is RunStatus.stopped or r == "stopped":
        return Wait("You (or a plan) stopped this run before it finished.",
                    "Re-run it when ready. Child processes were killed; the workspace is kept.", kind="wait")
    if r == "timeout":
        return Wait(f"The run hit its wall-clock limit ({lim.timeout_seconds if lim else '?'}s) and was killed.",
                    "Raise timeout_seconds, lower max_steps, or give the bot a smaller task.", kind="error")
    if r == "steps_exceeded":
        return Wait(f"The bot used all {lim.max_steps if lim else '?'} steps without finishing.",
                    "Check the transcript for a loop; raise max_steps only if the task is genuinely long.",
                    kind="error")
    if r == "token_cap":
        return Wait(f"The bot reached its daily token cap ({fmt_tokens(lim.daily_token_cap) if lim else '?'}).",
                    "Raise daily_token_cap on the bot, or wait for tomorrow (UTC).", kind="error")
    if r == "cost_cap":
        return Wait("The next request estimate reached this bot's currency limit.",
                    "Review the recorded price and prompt estimate before raising the limit.",
                    kind="error")
    if r == "approval_expired":
        return Wait("An approval went unanswered and was denied at its deadline.",
                    "Answer sooner, or use 'always for this bot' on actions you trust.", kind="error")
    if r == "loop":
        return Wait("The bot repeated the same tool call with the same arguments three times.",
                    "Open the transcript to see what it was stuck on; clarify the instructions.", kind="error")
    text = (run.error or "").lower()
    for needle, cause, fix in _ERROR_HINTS:
        if needle in text:
            return Wait(cause, fix, href="/models", link_text="Models", kind="error")
    return Wait(f"The run ended with an error: {(run.error or r or 'unknown')[:200]}",
                "Open the transcript for the failing step.", kind="error")


# ------------------------------------------------------------------ staleness


@dataclass
class Stale:
    bot: Bot
    cause: str
    fix: str
    last_success: Optional[str]
    expected_after: Optional[str]
    last_run: Optional[Run] = None


def _prev_fire(scheduler, bot: Bot, now: datetime) -> Optional[datetime]:
    """Most recent scheduled fire time at or before ``now`` (UTC-aware), in the bot's own zone."""
    zone = scheduler.try_zone(bot)
    if zone is None or bot.schedule is None:
        return None
    return scheduler._newest_on_or_before(bot.schedule, now, zone)


def stale_info(store, scheduler, bot: Bot, now: Optional[datetime] = None) -> Optional[Stale]:
    """UI-1: the bot should have succeeded since its last scheduled window, but has not.

    "Active" only means the trigger is armed; a job that quietly stopped producing results looks
    exactly like a calm week (the n8n failure). So we compare the last *success* with the schedule.
    """
    if not bot.schedule or bot.paused:
        return None
    now = now or utcnow()
    prev = _prev_fire(scheduler, bot, now)
    created = parse_ts(bot.created_at)
    if prev is None or (created and created > prev):
        return None  # it has not had a window yet
    nxt = scheduler.next_fire(bot, now)
    interval = (nxt - prev).total_seconds() if nxt else 86400.0
    grace = timedelta(seconds=min(max(interval * 0.1, 120.0), 3600.0))
    if now - prev < grace:
        return None  # the window just opened; the run may still be starting
    if store.active_run_for_bot(bot.id) is not None:
        return None
    last = store.last_successful_run(bot.id)
    last_ok = parse_ts(last.finished_at or last.created_at) if last else None
    if last_ok and last_ok >= prev - grace:
        return None
    latest = store.latest_finished_run(bot.id)
    zone = scheduler.try_zone(bot)
    if zone is None:
        return None
    when = prev.astimezone(zone).strftime("%a %d %b %H:%M %Z")
    skip = scheduler.last_skip(bot)
    if latest and latest.status is RunStatus.failed and parse_ts(latest.created_at) >= prev - grace:
        why = explain_outcome(latest, bot)
        cause = f"It ran at the {when} window but failed: {why.cause if why else latest.error[:120]}"
        fix = why.fix if why else "Open the last run."
    elif skip:
        cause = (f"The {when} window was skipped by the catch-up policy "
                 f"({skip.get('windows', '?')} window(s) missed while hutch was not running).")
        fix = "Set catch_up to 'coalesce' to run once after downtime, or run it now."
    elif latest is None or parse_ts(latest.created_at) < prev - grace:
        cause = (f"No run was started for the {when} window. The scheduler (hutch serve or hutch daemon) "
                 "was probably not running then.")
        fix = ("Start the scheduler (`hutch serve` or `hutch daemon`), keep it running with "
               "`hutch service install`, or run the bot now.")
    else:
        cause = f"The latest run did not succeed ({latest.status.value})."
        fix = "Open the last run."
    return Stale(bot=bot, cause=cause, fix=fix,
                 last_success=(last.finished_at or last.created_at) if last else None,
                 expected_after=iso(prev), last_run=latest)


# ------------------------------------------------------------------ home


@dataclass
class HomeState:
    approvals: list = field(default_factory=list)       # [(ApprovalRequest, bot_name)]
    humans: list = field(default_factory=list)          # [(Run, bot_name, Wait)]
    failures: list = field(default_factory=list)        # [(Run, bot_name, Wait)]
    running: list = field(default_factory=list)         # [(Run, bot_name, Optional[Wait])]
    stale: list = field(default_factory=list)           # [Stale]
    stats: dict = field(default_factory=dict)

    @property
    def needs_count(self) -> int:
        return len(self.approvals) + len(self.humans) + len(self.failures)


FAILURE_WINDOW = timedelta(days=7)


def is_dismissed(store, run_id: str) -> bool:
    return store.kv_get(f"dismissed:{run_id}") == "1"


def home_state(store, scheduler, engine: Any = None, now: Optional[datetime] = None) -> HomeState:
    now = now or utcnow()
    bots = {b.id: b for b in store.list_bots()}
    h = HomeState()
    for a in store.pending_approvals():
        b = bots.get(a.bot_id)
        h.approvals.append((a, b.name if b else "?"))
    for run in store.active_runs():
        b = bots.get(run.bot_id)
        name = b.name if b else "?"
        wait = explain_run(store, run, engine, b)
        if run.status is RunStatus.waiting_human:
            h.humans.append((run, name, wait))
        else:
            h.running.append((run, name, wait))
    for b in bots.values():
        latest = store.latest_finished_run(b.id)
        if latest and latest.status is RunStatus.failed and not is_dismissed(store, latest.id):
            fin = parse_ts(latest.finished_at or latest.created_at)
            if fin and now - fin <= FAILURE_WINDOW:
                h.failures.append((latest, b.name, explain_outcome(latest, b)))
        st = stale_info(store, scheduler, b, now)
        if st:
            h.stale.append(st)
    h.failures.sort(key=lambda t: t[0].finished_at or "", reverse=True)
    h.running.sort(key=lambda t: t[0].created_at, reverse=True)
    runs_today = store._runs_today(now=now)
    h.stats = {
        "bots": len(bots), "paused": sum(1 for b in bots.values() if b.paused),
        "runs_today": len(runs_today),
        "tokens_today": sum(r.tokens for r in runs_today),
        "spend_today": sum(r.cost_usd for r in runs_today),
    }
    return h


# ------------------------------------------------------------------ meters


@dataclass
class Meter:
    label: str
    value: str
    cap: str          # "" when there is no cap
    pct: float        # 0-100, 0 when uncapped
    level: str = "ok"  # ok | warn | hot
    note: str = ""


def _level(pct: float) -> str:
    return "hot" if pct >= 90 else "warn" if pct >= 70 else "ok"


def run_meters(store, run: Run, bot: Optional[Bot], now: Optional[datetime] = None) -> list[Meter]:
    """UI-4: steps, elapsed time, spend and context use against their caps."""
    now = now or utcnow()
    lim = bot.limits if bot else None
    out: list[Meter] = []

    if lim:
        pct = min(100.0, run.steps / max(lim.max_steps, 1) * 100)
        out.append(Meter("Steps", str(run.steps), f"of {lim.max_steps}", pct, _level(pct)))
    else:
        out.append(Meter("Steps", str(run.steps), "", 0))

    start = parse_ts(run.started_at) or parse_ts(run.created_at)
    end = parse_ts(run.finished_at) or now
    elapsed = max(0.0, (end - start).total_seconds()) if start else 0.0
    if lim:
        pct = min(100.0, elapsed / max(lim.timeout_seconds, 1) * 100)
        out.append(Meter("Elapsed", fmt_duration(elapsed), f"of {fmt_duration(lim.timeout_seconds)}", pct, _level(pct)))
    else:
        out.append(Meter("Elapsed", fmt_duration(elapsed), "", 0))

    cap_usd = getattr(lim, "max_cost_usd", 0.0) if lim else 0.0
    if cap_usd:
        _, reserved_cost = store.run_reserved_usage(run.id)
        projected_cost = run.cost_usd + reserved_cost
        pct = min(100.0, projected_cost / cap_usd * 100)
        out.append(Meter("Spend", fmt_money(projected_cost), f"of {fmt_money(cap_usd)} estimate limit", pct,
                         _level(pct), note=f"{fmt_money(run.cost_usd)} measured + {fmt_money(reserved_cost)} held estimate"))
    else:
        note = ("local model: no per-token cost" if (run.cost_usd == 0 and run.tokens)
                else "no currency estimate limit set")
        out.append(Meter("Spend", fmt_money(run.cost_usd), "", 0, note=note))

    if bot and lim:
        measured_tokens, reserved_tokens, _, _ = store.bot_budget_today(bot.id)
        projected = measured_tokens + reserved_tokens
        pct = min(100.0, projected / max(lim.daily_token_cap, 1) * 100)
        out.append(Meter("Tokens today", fmt_tokens(projected), f"of {fmt_tokens(lim.daily_token_cap)}", pct,
                         _level(pct), note=f"{fmt_tokens(measured_tokens)} measured + {fmt_tokens(reserved_tokens)} held estimate"))
    if run.context_limit:
        pct = min(100.0, run.context_used / run.context_limit * 100)
        out.append(Meter("Context", fmt_tokens(run.context_used), f"of {fmt_tokens(run.context_limit)}", pct,
                         _level(pct), note="window the model actually got"))
    else:
        out.append(Meter("Context", fmt_tokens(run.context_used), "", 0, note="window not reported by this runtime"))
    return out


def timing_split(run: Run) -> dict[str, float]:
    """PF-11: where the wall time went."""
    total = run.model_ms + run.tool_ms + run.overhead_ms
    if total <= 0:
        return {"model": 0, "tool": 0, "overhead": 0}
    return {"model": run.model_ms / total * 100, "tool": run.tool_ms / total * 100,
            "overhead": run.overhead_ms / total * 100}


def timing_abs(run: Run) -> dict[str, float]:
    """PF-11 in absolute terms. A percentage misleads when everything is sub-millisecond (a test fixture run
    would read "Hutch = 46%"), so the UI shows milliseconds and the per-step overhead."""
    steps = max(run.steps, 1)
    return {"model_ms": run.model_ms, "tool_ms": run.tool_ms, "overhead_ms": run.overhead_ms,
            "per_step_ms": run.overhead_ms / steps, "total_ms": run.model_ms + run.tool_ms + run.overhead_ms}


def fmt_ms(ms: float) -> str:
    if ms < 1:
        return f"{ms:.2f} ms"
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.1f} s"


def json_pretty(obj: Any, indent: int | None = 2) -> str:
    """Readable JSON for display (autoescaping handles HTML; Jinja's tojson would emit \\u0027 for quotes)."""
    import json
    return json.dumps(obj, ensure_ascii=False, indent=indent, default=str)


def arg_summary(tool: str, args: Any, limit: int = 120) -> str:
    """One line describing what a tool call is doing, for the compact transcript line."""
    if not isinstance(args, dict) or not args:
        return ""
    a = args
    if tool == "shell":
        text = str(a.get("command", ""))
    elif tool in ("read_file", "list_files"):
        text = str(a.get("path", "") or ".")
    elif tool == "write_file":
        text = f"{a.get('path', '')} ({len(str(a.get('content', '')))} chars)"
    elif tool == "web_fetch":
        text = str(a.get("url", ""))
    elif tool == "remember":
        text = f"{a.get('key', '')} = {str(a.get('value', ''))[:60]}"
    elif tool == "recall":
        text = str(a.get("query", "")) or "(all)"
    elif tool == "browser":
        text = " ".join(str(x) for x in (a.get("action"), a.get("url") or a.get("selector") or a.get("label")) if x)
    else:
        text = ", ".join(f"{k}={str(val)[:40]}" for k, val in a.items())
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def output_summary(output: str, limit: int = 140) -> str:
    """First meaningful line of a tool result."""
    for line in (output or "").splitlines():
        if line.strip():
            return line.strip() if len(line.strip()) <= limit else line.strip()[: limit - 1] + "..."
    return "(no output)"
