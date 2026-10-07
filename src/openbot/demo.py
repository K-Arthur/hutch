"""Demo data seeding — `openbot demo seed`.

Produces a dashboard-ready state entirely offline: template bots, completed
runs with real transcripts (mock runtime through the real tool/policy
pipeline), one live run waiting on a human approval, and one historical
failure. Used for screenshots, first-run tours, and manual testing.
"""

from __future__ import annotations

import time

from .config import OpenBotConfig
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


def seed_demo(config: OpenBotConfig, store: Store, engine: Engine) -> dict:
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

    # 2) One live run parked on a human approval (write_file gate)
    tidy = store.get_bot("tidy-downloads")
    if tidy is not None:
        run = engine.submit(tidy, "sort this week's downloads into folders")
        engine.dispatch_pending()
        deadline = time.time() + 10
        while time.time() < deadline:
            current = store.get_run(run.id)
            if current and current.status is RunStatus.waiting_approval:
                break
            time.sleep(0.1)
        summary["runs"].append({"bot": tidy.name, "run": run.id,
                                "status": store.get_run(run.id).status.value})

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
