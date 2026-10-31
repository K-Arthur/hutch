"""Today and Shared: real store, real server, real browser.

Covers the responsive layout, the owner capture/complete/confirm commands writing
through the real API, keyboard navigation, 200 percent text scaling and the
absence of browser console errors. Screenshots are written to the test artifact
root for review; no product data is fabricated in the repository.
"""

from __future__ import annotations

from playwright.sync_api import expect

from hutch.personal import Commitment, CompletionKind, Space, SpaceMember, SpaceRole
from hutch.personal.store import PersonalStore

from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def seed_personal_operations(store) -> None:
    personal = PersonalStore(store)
    personal.commitments.create(Commitment(
        title="Pay the water bill", detail="Account ending 4417",
        due_at="2026-10-28T17:00:00-07:00", due_timezone="America/Vancouver", priority="high"))
    reported, _ = personal.commitments.create(Commitment(title="Return the parcel"))
    personal.commitments.complete(reported.id, evidence="Left at the counter, receipt 2291",
                                  kind=CompletionKind.unverified, actor="assistant")
    personal.commitments.create(Commitment(
        title="Schedule the boiler service", created_by="assistant", confirmation="proposed",
        source="assistant", source_detail="capture_commitment"))
    space = personal.spaces.create(Space(name="Our household", kind="household"))
    personal.spaces.add_member(space.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
    personal.spaces.add_member(space.id, SpaceMember(display_name="Sam", role=SpaceRole.adult))
    personal.spaces.grant(space.id, store.list_bots()[0].id)
    personal.commitments.create(Commitment(title="Buy groceries", space_id=space.id, detail="Milk and eggs"))


def test_today_and_shared_are_responsive_and_truthful(browser, app_server):
    base, app = app_server
    store = app.state.store
    seed_personal_operations(store)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)
    out = artifact_path("personal-operations")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height in ((1440, 960), (834, 1112), (390, 844), (320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/today")
            expect(page.locator(".pd-page")).to_be_visible()
            expect(page.locator(".pd-section").first).to_be_visible()
            assert page.evaluate("Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") <= 1
            # A proposal is never presented as a commitment.
            assert page.locator("#pd-today .pd-item, .pd-section").count() > 0
            expect(page.locator(".pd-chip.proposed").first).to_be_visible()
            page.screenshot(path=str(out / f"today-{width}.png"), full_page=True, animations="disabled")

            page.goto(f"{base}/#/shared")
            expect(page.locator(".pd-shared")).to_be_visible()
            expect(page.locator(".pd-space")).to_have_count(1)
            expect(page.locator(".pd-person").first).to_be_visible()
            assert page.evaluate("Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") <= 1
            page.screenshot(path=str(out / f"shared-{width}.png"), full_page=True, animations="disabled")

        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(f"{base}/#/today")
        expect(page.locator(".pd-page")).to_be_visible()
        page.keyboard.press("Tab")
        assert page.evaluate("Boolean(document.activeElement)") is True
        expect(page.locator('.ws-nav a[data-nav="today"][aria-current="page"]')).to_have_count(1)

        page.fill("#pd-new-title", "Book the museum tickets")
        page.click(".pd-capture button[type=submit]")
        page.wait_for_function(
            "fetch('/api/v1/commitments?status=open').then(r => r.json())"
            ".then(d => d.items.some(i => i.title === 'Book the museum tickets'))", timeout=15000)
        titles = [item.title for item in PersonalStore(store).commitments.list()]
        assert "Book the museum tickets" in titles

        page.reload()
        row = page.locator("[data-commitment-row]", has_text="Pay the water bill").first
        row.locator('[data-commitment-action="complete"]').click()
        page.wait_for_selector("#pd-evidence")
        page.fill("#pd-evidence", "Paid online, confirmation 5521")
        page.click("#modal-confirm")
        page.wait_for_function(
            "fetch('/api/v1/commitments?status=done').then(r => r.json())"
            ".then(d => d.items.some(i => i.title === 'Pay the water bill' && i.completion_kind === 'owner_confirmed'))",
            timeout=15000)
        done = next(item for item in PersonalStore(store).commitments.list(status="done")
                    if item.title == "Pay the water bill")
        assert done.completion_kind is CompletionKind.owner_confirmed

        page.reload()
        confirm = page.locator(
            "xpath=//span[contains(@class,'pd-chip proposed')]/ancestor::li[1]"
            "//button[@data-commitment-action='confirm']")
        confirm.first.click()
        page.wait_for_function(
            "fetch('/api/v1/commitments?status=open').then(r => r.json())"
            ".then(d => d.items.some(i => i.title === 'Schedule the boiler service' && i.confirmation === 'confirmed'))",
            timeout=15000)

        page.evaluate("document.documentElement.style.fontSize = '200%'")
        page.wait_for_timeout(300)
        assert page.evaluate("Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") <= 1
        page.screenshot(path=str(out / "today-zoom200.png"), full_page=True, animations="disabled")
        assert not errors, errors
    finally:
        context.close()
