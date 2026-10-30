"""Shared select component contract: one class, token-driven states, live shell.

Complements test_dropdown_controls.py (native form, picker, Escape, no-JS and
token assertions) with the component-specific promises: every select carries
.hutch-select, the wrapper enhances selects injected after load, focus wears the
Hutch focus token as a single ring, hover is a fill shift with the border held,
disabled is muted and reduced, and the header conversation chip keeps its shape.
"""
from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot
from tests.e2e.test_browser import live  # real isolated HTTP app fixture
from tests.support.artifacts import artifact_path
from tests.support.browser import launch_browser


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def test_select_component_states_and_wrapper(browser, live):
    base, app = live
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    try:
        page.goto(base + "/#/settings")
        control = page.locator("#workspace-settings-mode")
        control.wait_for()
        assert control.evaluate("el => el.classList.contains('hutch-select')")
        assert page.evaluate(
            "() => [...document.querySelectorAll('select')]"
            ".filter(el => !el.classList.contains('hutch-select')).length"
        ) == 0, "every select on the page wears the component class"

        # Field geometry and the token surface (SPA: the full --hutch-alias layer).
        facts = control.evaluate(
            """el => {
              const cs = getComputedStyle(el);
              const root = getComputedStyle(document.documentElement);
              const norm = tok => {
                const probe = document.createElement('span');
                probe.style.color = root.getPropertyValue(tok);
                document.body.append(probe);
                const value = getComputedStyle(probe).color;
                probe.remove();
                return value;
              };
              return {
                minHeight: cs.minHeight,
                fontSize: cs.fontSize,
                border: cs.borderTopColor,
                expectedBorder: norm('--hutch-alias-select-border'),
                bg: cs.backgroundColor,
                expectedBg: norm('--hutch-alias-select-bg'),
              };
            }"""
        )
        assert facts["minHeight"] == "44px", facts
        assert facts["fontSize"] == "16px", facts
        assert facts["border"] == facts["expectedBorder"], facts
        assert facts["bg"] == facts["expectedBg"], facts

        # Hover: the fill lifts to the hover token, the boundary does not move.
        rest_bg = control.evaluate("el => getComputedStyle(el).backgroundColor")
        rest_border = control.evaluate("el => getComputedStyle(el).borderTopColor")
        control.hover()
        # The fill transition is 120ms; read the settled hover value.
        page.wait_for_function(
            """() => {
              const el = document.getElementById('workspace-settings-mode');
              const root = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = root.getPropertyValue('--hutch-alias-select-bg-hover');
              document.body.append(probe);
              const expected = getComputedStyle(probe).color;
              probe.remove();
              return getComputedStyle(el).backgroundColor === expected;
            }"""
        )
        hovered = control.evaluate(
            """el => {
              const cs = getComputedStyle(el);
              const root = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = root.getPropertyValue('--hutch-alias-select-bg-hover');
              document.body.append(probe);
              const expected = getComputedStyle(probe).color;
              probe.remove();
              return { bg: cs.backgroundColor, expected, border: cs.borderTopColor };
            }"""
        )
        assert hovered["bg"] == hovered["expected"], (rest_bg, hovered)
        assert hovered["bg"] != rest_bg, "hover must shift the fill"
        assert hovered["border"] == rest_border, "hover must not recolour the border"
        out = artifact_path("select-component")
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / "settings-hover.png"))

        # Focus: keyboard modality, one azure ring from the focus token, no
        # leftover form-system box-shadow underneath it.
        page.keyboard.press("Tab")
        control.focus()
        focus = control.evaluate(
            """el => {
              const cs = getComputedStyle(el);
              const root = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = root.getPropertyValue('--hutch-alias-select-focus-ring');
              document.body.append(probe);
              const expected = getComputedStyle(probe).color;
              probe.remove();
              return {
                visible: el.matches(':focus-visible'),
                color: cs.outlineColor,
                expected,
                width: cs.outlineWidth,
                style: cs.outlineStyle,
                shadow: cs.boxShadow,
              };
            }"""
        )
        assert focus["visible"], focus
        assert focus["color"] == focus["expected"], focus
        assert focus["width"] == "2px" and focus["style"] == "solid", focus
        assert focus["shadow"] == "none", focus
        page.screenshot(path=str(out / "settings-focus-ring.png"))

        # The wrapper enhances selects injected after load, and disabled state
        # is muted ink plus reduced opacity with a refused cursor.
        page.evaluate(
            """() => {
              const select = document.createElement('select');
              select.id = 'wrapper-probe';
              select.innerHTML = '<option value="a">a</option>';
              const disabled = document.createElement('select');
              disabled.id = 'disabled-probe';
              disabled.disabled = true;
              disabled.innerHTML = '<option value="a">a</option>';
              document.body.append(select, disabled);
            }"""
        )
        page.wait_for_function(
            "() => document.getElementById('wrapper-probe')"
            "?.classList.contains('hutch-select')"
        )
        probe = page.locator("#disabled-probe")
        assert probe.evaluate("el => el.classList.contains('hutch-select')")
        off = probe.evaluate(
            """el => {
              const cs = getComputedStyle(el);
              return { opacity: cs.opacity, cursor: cs.cursor, color: cs.color };
            }"""
        )
        assert off["opacity"] == "0.6", off
        assert off["cursor"] == "not-allowed", off
        muted = probe.evaluate(
            """el => {
              const root = getComputedStyle(document.documentElement);
              const select = getComputedStyle(el);
              const probe = document.createElement('span');
              probe.style.color = root.getPropertyValue('--hutch-alias-select-disabled');
              document.body.append(probe);
              const expected = getComputedStyle(probe).color;
              probe.remove();
              return { color: select.color, expected };
            }"""
        )
        assert muted["color"] == muted["expected"], muted
        page.locator("#disabled-probe").screenshot(path=str(out / "disabled-state.png"))
    finally:
        context.close()


def test_select_chip_variant_keeps_header_shape(browser, live):
    base, app = live
    bot = app.state.store.create_bot(
        Bot(name="select-chip", display_name="Select chip", model="mock/demo", tools=[])
    )
    conversation, _ = app.state.store.create_conversation(
        bot.id,
        "Chip conversation",
        idem_key="select-chip-conversation",
        request_hash="select-chip-conversation-request",
    )
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    try:
        # The conversation switcher chip only shows on a conversation route;
        # open one so the chip renders in its real header context.
        page.goto(base + "/#/conversation/" + conversation["id"])
        chip = page.locator("#conversation-switcher")
        chip.wait_for(state="visible")
        classes = chip.get_attribute("class") or ""
        assert "hutch-select" in classes and "hutch-select--chip" in classes, classes
        shape = chip.evaluate(
            """el => {
              const cs = getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              return {
                height: cs.height,
                bg: cs.backgroundColor,
                radius: cs.borderTopLeftRadius,
                width: rect.width,
                top: rect.top,
              };
            }"""
        )
        assert shape["height"] == "36px", shape
        assert shape["bg"] == "rgba(0, 0, 0, 0)", shape
        assert shape["radius"] == "8px", shape
        assert shape["width"] > 100 and shape["top"] > 0, shape
        out = artifact_path("select-component")
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / "header-chip.png"))
    finally:
        context.close()
