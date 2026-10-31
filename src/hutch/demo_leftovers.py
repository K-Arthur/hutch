"""Assistants an earlier demo version left behind, and what to tell a person who still has them.

Hutch no longer seeds or runs demo assistants, but a workspace created by an earlier version can still hold some,
saved on the removed demo runtime (`mock/...`, or the bare demo-era `demo`). They cannot run. `hutch init` used to say
"No bots were created" even when such assistants were sitting there, so first run never started and nothing said why.
The dashboard offers one governed removal (Review install); this is the terminal's honest account, with the command.
The pattern and the seeded names are mirrored in `static/assistant-removal.js`; keep the two in step.
"""

from __future__ import annotations

import re

RETIRED_DEMO = re.compile(r"^(mock/|demo$)", re.IGNORECASE)
#: The assistants the old `demo seed` created, plus the design-review fixture that landed in some workspaces.
SEEDED_NAMES = frozenset({"repo-sweeper", "research-briefing", "tidy-downloads", "design-system-review"})


def retired_demo_assistants(store) -> list:
    return [bot for bot in store.list_bots() if RETIRED_DEMO.match((bot.model or "").strip()) or bot.name in SEEDED_NAMES]


def demo_warning(store) -> str:
    """One paragraph naming the demo assistants and the two ways out; empty when there are none."""
    demo = retired_demo_assistants(store)
    if not demo:
        return ""
    names = ", ".join(bot.display_name or bot.name for bot in demo)
    return (f"{len(demo)} assistant{'s' if len(demo) != 1 else ''} left over from an earlier demo version ({names}); you did not create "
            f"{'them' if len(demo) != 1 else 'it'}. In the dashboard open an assistant's menu and choose Remove, or Review install to remove "
            "them all with a preview, or run `hutch bot destroy <name>` for each. Removing them lets first run start.")


def init_summary(store) -> str:
    """What `hutch init` found, truthfully: it never creates assistants, and it should not claim there are none."""
    bots = store.list_bots()
    if not bots:
        return "No assistants exist yet. Open the dashboard with `hutch serve`: first run helps you pick a model and create one."
    text = f"{len(bots)} assistant{'s' if len(bots) != 1 else ''} already exist; init created none."
    warning = demo_warning(store)
    return text + ("\n" + warning if warning else "")
