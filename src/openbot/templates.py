"""Starter bot templates seeded by `openbot init`.

All templates default to the free, offline mock model — new users can explore
the whole pipeline (scheduling, tools, approvals, transcripts) without an API
key, then flip `--model` to openai/* or ollama/* when ready.
"""

from __future__ import annotations

from .models import ApprovalMode, Bot, Schedule

TEMPLATES: dict[str, Bot] = {
    "research-briefing": Bot(
        name="research-briefing",
        description="Weekly research briefing on topics you pick",
        instructions=(
            "Search the public web for developments since the last briefing on the topics below, "
            "then write report.md: 5-8 bullets, each with a source URL. Save a memory note listing "
            "the URLs you already covered so the next briefing only adds what's new.\n"
            "Topics: replace this line with your topics."
        ),
        model="mock/demo",
        tools=["web_fetch", "files", "memory"],
        schedule=Schedule(cron="0 9 * * 1", timezone="UTC"),
        template="research-briefing",
    ),
    "repo-sweeper": Bot(
        name="repo-sweeper",
        description="Sweep a git repo for TODOs and stale code, on demand",
        instructions=(
            "You run inside a copy of a git repository. Find TODO/FIXME/HACK comments and obviously "
            "stale code paths; write findings.md with file:line references and a suggested fix for "
            "each. Do NOT modify source files — reports only."
        ),
        model="mock/demo",
        tools=["shell", "files", "memory"],
        template="repo-sweeper",
    ),
    "tidy-downloads": Bot(
        name="tidy-downloads",
        description="Sort this week's downloads into folders (with approval before each move)",
        instructions=(
            "List the files in the workspace, propose a simple folder structure (docs/images/installers/"
            "archives/other), and move files into it. Every move needs the operator's approval — "
            "that is intentional; batch your proposals so one approval covers a group."
        ),
        model="mock/demo",
        tools=["files", "shell", "memory"],
        approval_mode=ApprovalMode.ask,
        template="tidy-downloads",
    ),
}


def seed(store) -> list[str]:
    """Create any missing template bots. Returns names created."""
    created = []
    for tpl in TEMPLATES.values():
        if store.get_bot(tpl.name) is None:
            store.create_bot(tpl.model_copy(deep=True))
            created.append(tpl.name)
    return created
