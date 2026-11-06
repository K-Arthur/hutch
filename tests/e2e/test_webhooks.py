"""End-to-end browser tests for inbound webhook management on #/schedules."""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from playwright.sync_api import expect  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from hutch.webhook_receiver import admit_webhook  # noqa: E402
from hutch.webhook_store import create_webhook_source  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import PageWatch, horizontal_overflow, serve  # noqa: E402

VIEWPORTS = ((360, 800), (768, 1024), (1280, 800), (1920, 1080))


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def _seed(app) -> None:
    store = app.state.store
    bot = store.create_bot(Bot(name="deploy-agent", display_name="Deploy Agent", tools=[]))
    source, raw_token = create_webhook_source(
        store,
        bot_id=bot.id,
        name="Production Webhook",
        prompt_template="Deploy requested: {payload}",
        cooldown_seconds=0.0,
        max_per_hour=60,
    )
    admit_webhook(
        store,
        raw_token,
        b'{"action": "deploy", "env": "prod"}',
        "application/json",
        idempotency_key="seed_deploy_1",
    )


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    _seed(app)
    with serve(app) as url:
        yield url


def test_webhooks_ui_management(browser, base):
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        color_scheme="dark",
        reduced_motion="reduce",
    )
    page = context.new_page()
    watch = PageWatch(page)
    try:
        page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
        section = page.locator(".webhook-management-section")
        section.wait_for(timeout=20_000)

        expect(section).to_contain_text("Inbound Webhooks")
        expect(section).to_contain_text("Inbound webhooks listen on loopback (127.0.0.1)")

        card = page.locator(".webhook-source-card", has_text="Production Webhook")
        card.wait_for(timeout=20_000)
        expect(card).to_contain_text("Active")
        expect(card).to_contain_text("Deploy Agent")
        expect(card).to_contain_text("Token prefix:")

        # Open deliveries disclosure
        deliveries_details = card.locator(".webhook-deliveries-details summary")
        deliveries_details.click()
        delivery_item = card.locator(".webhook-delivery-item")
        delivery_item.first.wait_for(timeout=20_000)
        expect(delivery_item.first).to_contain_text("HTTP 200")
        expect(delivery_item.first).to_contain_text("processed", ignore_case=True)

        # Pause webhook
        pause_btn = card.locator('button[data-action="toggle-pause"]')
        pause_btn.click()
        expect(card.locator(".webhook-source-head .webhook-badge")).to_contain_text("Paused")

        # Resume webhook
        pause_btn.click()
        expect(card.locator(".webhook-source-head .webhook-badge")).to_contain_text("Active")

        # Create new webhook source
        create_btn = page.locator("#webhook-create-btn")
        create_btn.click()
        dialog = page.locator(".webhook-create-dialog")
        dialog.wait_for(timeout=10_000)

        page.fill("#wh-name", "Stripe Ingress")
        page.locator('#webhook-create-form button[type="submit"]').click()

        # Secret callout should appear
        secret_box = page.locator(".webhook-secret-callout")
        secret_box.wait_for(timeout=10_000)
        expect(secret_box).to_contain_text("Save webhook secret for \"Stripe Ingress\"")
        expect(secret_box.locator("code")).to_contain_text("whsec_")

        # Dismiss callout
        secret_box.locator("#webhook-dismiss-token").click()
        expect(secret_box).not_to_be_visible()

        assert watch.errors == [], watch.errors
    finally:
        context.close()


def test_webhooks_surface_responsive_and_no_overflow(browser, base):
    for width, height in VIEWPORTS:
        for scheme in ("dark", "light"):
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme=scheme,
                reduced_motion="reduce",
            )
            page = context.new_page()
            watch = PageWatch(page)
            try:
                page.goto(f"{base}/#/schedules", wait_until="domcontentloaded")
                if scheme == "light":
                    page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")
                section = page.locator(".webhook-management-section")
                section.wait_for(timeout=20_000)
                card = page.locator(".webhook-source-card", has_text="Production Webhook")
                card.wait_for(timeout=20_000)

                assert horizontal_overflow(page) <= 1, (width, scheme, horizontal_overflow(page))
                assert watch.errors == [], (width, scheme, watch.errors)
            finally:
                context.close()
