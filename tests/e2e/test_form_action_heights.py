"""Form action buttons follow the documented control-height scale.

docs/design-system.md: 40px for primary and decision controls on a fine pointer, and the 44px
touch height under ``pointer: coarse``. The height is measured on a probe form appended to the live
dashboard, so the check depends on the shared form stylesheet and not on any one page's content.
"""
from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from tests.e2e.test_browser import live  # real isolated HTTP app fixture
from tests.support.browser import launch_browser

PROBE = """() => {
  const form = document.createElement('form');
  form.className = 'hutch-form';
  form.innerHTML = '<div class="hutch-actions"><button class="btn ghost small" type="button">Probe</button></div>';
  document.body.appendChild(form);
  const height = Math.round(form.querySelector('button').getBoundingClientRect().height);
  form.remove();
  return height;
}"""


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def _action_height(browser, base: str, **context_options) -> int:
    """Height in px of a small ghost button inside a form's action row, for one pointer type."""
    context = browser.new_context(reduced_motion="reduce", **context_options)
    page = context.new_page()
    try:
        page.goto(base + "/#/settings")
        page.locator("#workspace-settings-mode").wait_for()
        return page.evaluate(PROBE)
    finally:
        context.close()


def test_fine_pointer_form_actions_use_the_40px_decision_height(browser, live):
    base, _ = live
    height = _action_height(browser, base, viewport={"width": 1440, "height": 900})
    assert 40 <= height < 44, height


def test_coarse_pointer_form_actions_use_the_44px_touch_height(browser, live):
    base, _ = live
    height = _action_height(browser, base, viewport={"width": 390, "height": 844},
                            is_mobile=True, has_touch=True)
    assert height >= 44, height
