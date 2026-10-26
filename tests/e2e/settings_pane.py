"""Navigate the assistant settings page (a section rail; every pane stays in the DOM).

The settings are grouped into panes behind an ARIA tablist: profile, behavior, model, tools, schedule, safety
and limits. Only the selected pane is painted, so a test that touches a field first selects the pane that owns it.
"""

from __future__ import annotations

PANES = ("profile", "behavior", "model", "tools", "schedule", "safety", "limits")


def open_assistant_customization(page, section="profile"):
    """Select one settings pane and wait until it is visible."""
    assert section in PANES, section
    shell = page.locator("#assistant-more-settings")
    shell.wait_for(state="attached")
    tab = shell.locator(f'[data-settings-tab="{section}"]')
    tab.wait_for(state="visible")
    if tab.get_attribute("aria-selected") != "true":
        tab.click()
    page.locator(f"#settings-pane-{section}").wait_for(state="visible")
