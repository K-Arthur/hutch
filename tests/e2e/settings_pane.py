"""Navigate the assistant settings page (a section rail; every pane stays in the DOM).

The settings are grouped into panes behind an ARIA tablist: profile, behavior, model, tools, schedule, safety
and limits. Only the selected pane is painted, so a test that touches a field first selects the pane that owns it.
"""

from __future__ import annotations

PANES = ("profile", "behavior", "model", "tools", "schedule", "safety", "limits")


def open_assistant_customization(page, section="profile"):
    """Select one settings pane and wait until it is visible.

    Straight after a navigation the helper can click a tab on the page that is about to be replaced (the settings page
    re-renders as its data arrives, and a different assistant's page starts from Profile). The click is retried if the
    pane does not appear, so the helper survives that transition without waiting a fixed time.
    """
    assert section in PANES, section
    shell = page.locator("#assistant-more-settings")
    shell.wait_for(state="attached")
    pane = page.locator(f"#settings-pane-{section}")
    for _ in range(3):
        tab = shell.locator(f'[data-settings-tab="{section}"]')
        tab.wait_for(state="visible")
        if tab.get_attribute("aria-selected") != "true":
            tab.click()
        try:
            pane.wait_for(state="visible", timeout=4_000)
            return
        except Exception:                      # the page was replaced under the click: look again
            page.wait_for_timeout(150)
    pane.wait_for(state="visible")
