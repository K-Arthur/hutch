"""Demo data seeding — `hutch demo seed`.

Produces a dashboard-ready state entirely offline: template bots, completed
runs with real transcripts (mock runtime through the real tool/policy
pipeline), one live run waiting on a human approval, and one historical
failure. Used for screenshots, first-run tours, and manual testing.
"""

from __future__ import annotations

from .config import hutchConfig
from .engine import Engine
from .models import (
    ApprovalMode,
    Bot,
    Event,
    EventType,
    Run,
    RunStatus,
    Task,
    iso,
    utcnow,
)
from .store import Store
from .templates import TEMPLATES, seed


def seed_demo(config: hutchConfig, store: Store, engine: Engine) -> dict:
    created = seed(store)
    summary = {"bots_created": created, "runs": []}

    # 1) Two completed runs (auto-approve, mock runtime)
    for name in ("research-briefing", "repo-sweeper"):
        bot = store.get_bot(name)
        if bot is None:
            continue
        bot.approval_mode = ApprovalMode.auto
        store.upsert_bot(bot)
        prompts = {
            "research-briefing": "research this week's developments in local-first AI tools and summarize",
            "repo-sweeper": "find all TODOs and FIXMEs in this repository and suggest fixes",
        }
        run = engine.run_blocking(bot, prompts.get(name, "do your standing task"))
        summary["runs"].append({"bot": name, "run": run.id, "status": run.status.value})
        # restore template approval mode
        bot.approval_mode = TEMPLATES[name].approval_mode
        store.upsert_bot(bot)

    # 2) One run QUEUED for a live engine. It must be executed by a long-lived process (`hutch serve` or
    #    `hutch daemon`): parked on an approval inside this short-lived CLI it would become a zombie that
    #    nothing is waiting on, and "Approve" in the dashboard would do nothing.
    tidy = store.get_bot("tidy-downloads")
    if tidy is not None:
        run = engine.submit(tidy, "sort this week's downloads into folders", origin="manual:demo")
        summary["runs"].append({"bot": tidy.name, "run": run.id, "status": "queued (starts with hutch serve)"})

    # 3) One historical failure for the run list (timeout story)
    research = store.get_bot("research-briefing")
    if research is not None:
        failed = Run(bot_id=research.id,
                     prompt="research last month's releases (historical demo run)",
                     status=RunStatus.failed, exit_reason="timeout",
                     error="run exceeded 900s wall clock and was killed",
                     steps=7, tokens=8_450,
                     started_at=iso(utcnow()), finished_at=iso(utcnow()))
        store.create_run(failed)
        store.append_event(Event(run_id=failed.id, type=EventType.status, data={"status": "running"}))
        store.append_event(Event(run_id=failed.id, type=EventType.tool_call,
                                 data={"tool": "web_fetch", "args": {"url": "https://example.com/posts"}}))
        store.append_event(Event(run_id=failed.id, type=EventType.error,
                                 data={"error": "run exceeded 900s wall clock and was killed"}))
        summary["runs"].append({"bot": research.name, "run": failed.id, "status": "failed"})

    return summary
