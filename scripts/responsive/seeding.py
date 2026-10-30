"""Deterministic workspace fixture for responsive measurements.

The validation run must exercise real seeds rather than empty states: a roster,
a work-history table with enough rows to scroll, a chat transcript and one
pending approval, so the densest chrome is present in screenshots.
"""

from __future__ import annotations

from datetime import timedelta


def _seed_assistants(store):
    from hutch.models import Bot

    specs = (
        ("design-review", "Design Partner", "Reviews interface work and writes short notes."),
        ("research-desk", "Research Desk", "Reads sources and writes briefings."),
        ("release-reviewer", "Release Notes Reviewer", "Turns merged work into release notes."),
        ("calendar-planner", "Calendar Planner", "Keeps the week's schedule coherent."),
        ("customer-operations-analyst",
         "Customer Operations and Knowledge Research Analyst",
         "Escalation research with a deliberately long display name."),
    )
    for name, display_name, description in specs:
        store.create_bot(Bot(name=name, display_name=display_name, model="mock/demo",
                             tools=[], description=description))
    return store.get_bot("design-review")


def _seed_history(store, bot) -> None:
    from hutch.models import Run, RunStatus, iso, utcnow

    for index in range(18):
        succeeded = index % 5 != 0
        status = RunStatus.succeeded if succeeded else RunStatus.failed
        store.create_run(Run(
            bot_id=bot.id,
            prompt="Summarize the incoming workspace item %d." % (index + 1),
            status=status,
            exit_reason="completed" if succeeded else "failed",
            finished_at=iso(utcnow() - timedelta(minutes=index + 3)),
            started_at=iso(utcnow() - timedelta(minutes=index + 7)),
            steps=2 + index % 4,
            tokens=400 + 37 * index,
        ))


def _seed_transcript(store, bot) -> None:
    from hutch.models import Event, EventType, Run, RunStatus, iso, utcnow

    run = store.create_run(Run(
        bot_id=bot.id,
        prompt="Review the settings page at tablet width.",
        status=RunStatus.succeeded,
        exit_reason="completed",
        finished_at=iso(utcnow()),
        started_at=iso(utcnow() - timedelta(minutes=2)),
    ))
    store.append_event(Event(run_id=run.id, type=EventType.message, data={
        "role": "user", "content": "Review the settings page at tablet width."}))
    store.append_event(Event(run_id=run.id, type=EventType.message, data={
        "role": "assistant",
        "content": "The form stack holds together at 768px, but the review row wraps "
                   "its buttons onto a second line. I would keep the primary action "
                   "right-aligned and let the secondary action wrap below it."}))


def _seed_pending_approval(store, bot) -> None:
    from hutch.approvals import action_fingerprint
    from hutch.models import ApprovalRequest, Run, RunStatus, iso, utcnow

    run = store.create_run(Run(
        bot_id=bot.id,
        prompt="Delete the stale build directory.",
        status=RunStatus.waiting_approval,
        started_at=iso(utcnow()),
    ))
    detail = {"command": "rm -rf build/tmp"}
    store.create_approval(ApprovalRequest(
        run_id=run.id,
        bot_id=bot.id,
        tool="shell",
        action="rm -rf build/tmp",
        detail=detail,
        action_hash=action_fingerprint("shell", detail),
        expires_at=iso(utcnow() + timedelta(minutes=10)),
    ))


def seed_workspace(store) -> None:
    """Populate a fresh store with the deterministic responsive fixture."""
    bot = _seed_assistants(store)
    _seed_history(store, bot)
    _seed_transcript(store, bot)
    _seed_pending_approval(store, bot)
