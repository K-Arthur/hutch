"""Media section scenarios for capture_provider_ui.py.

Real jobs are submitted through the real job service against a loopback stand-in that speaks the xAI video wire
shape (the one from run_media_resume_check.py), then driven from the browser: check a job twice until it
finishes, and cancel one that the provider cannot confirm. The stand-in proves Hutch's UI, API and ledger; it says
nothing about any vendor, and every media route stays implemented-unverified.
"""

from __future__ import annotations

import http.server
import threading
from pathlib import Path
from typing import Any, Callable

from capture_provider_ui_scenarios import Gate
from run_media_resume_check import MP4, StandIn

XAI_KEY = "sk-gate-xai-standin-never-rendered"


def start_standin() -> tuple[http.server.ThreadingHTTPServer, str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StandIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def seed_media(state: Path, origin: str) -> list[str]:
    """An xAI connection pointing at the stand-in, and two real video jobs submitted through it."""
    from hutch.config import get_config
    from hutch.connections import ConnectionBook
    from hutch.media import MediaJobService, MediaStorage
    from hutch.media.backends import build_backends
    from hutch.media.spool import MediaSpool
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    from hutch.store import Store
    book = ConnectionBook(state)
    book.add("xai", name="xai", base_url=f"{origin}/v1")
    book.set_key("xai", XAI_KEY)
    config, store = get_config(), Store(get_config())
    bot = Bot(name="media-gate-bot", model="xai/none", tools=["create_media"], approval_mode=ApprovalMode.ask)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="media gate", status=RunStatus.running)
    store.create_run(run)
    storage = MediaStorage(config)
    service = MediaJobService(store, storage, backends=build_backends(config.state_dir, spool=MediaSpool(storage.root)))
    StandIn.video_status = "pending"
    return [service.submit(run_id=run.id, conversation_id=run.conversation_id, kind="video", prompt=prompt,
                           idempotency_key=key, backend_hint="xai-video:xai")["id"]
            for key, prompt in (("gate-video-1", "waves on a shore"), ("gate-video-2", "a second render"))]


def _job_card(page, prompt: str):
    return page.locator(".media-job").filter(has_text=prompt)


def scenario_media(gate: Gate, browser) -> None:
    gate.secrets.append(XAI_KEY)
    for label, width, height in gate.viewports:
        page = gate.page(browser, width, height)
        gate.visit(page, "/providers#media", label, ready="#media-jobs .media-job")
        gate.measure(page, f"media-{label}")
        page.context.close()
    page = gate.page(browser, 1280, 900)
    gate.visit(page, "/providers", "media", ready="#media-jobs .media-job")
    first, second = _job_card(page, "waves on a shore"), _job_card(page, "a second render")
    gate.check("two open jobs are listed with Check and Cancel offered", first.count() == 1 and second.count() == 1
               and first.get_by_role("button", name="Check now").is_visible(), text=first.inner_text()[:200])
    first.get_by_role("button", name="Check now").click()
    page.locator(".media-jobs-bar .hint").filter(has_text="job").wait_for()
    gate.check("a check while the provider is still working leaves the job running",
               "running" in _job_card(page, "waves on a shore").inner_text(), text=_job_card(page, "waves on a shore").inner_text()[:160])
    StandIn.video_status = "done"
    _job_card(page, "waves on a shore").get_by_role("button", name="Check now").click()
    _job_card(page, "waves on a shore").wait_for(state="detached", timeout=15000)   # open-only list drops it
    page.get_by_role("link", name="Show finished jobs too").click()
    page.wait_for_selector("#media-jobs .media-job")
    done = _job_card(page, "waves on a shore")
    link = done.get_by_role("link", name="Open result")
    gate.check("the finished job offers its stored result and no further actions",
               link.count() == 1 and done.get_by_role("button", name="Check now").count() == 0, text=done.inner_text()[:200])
    served = page.request.get(gate.url(link.get_attribute("href"))).body()
    gate.check("the served result is the stand-in's bytes", served == MP4, served=len(served), expected=len(MP4))
    StandIn.video_status = "pending"
    cancel = _job_card(page, "a second render").locator('[data-job-action="cancel"]')   # its label changes on click
    cancel.click()
    gate.check("the first click on Cancel only asks for confirmation",
               "Confirm: cancel this job" in cancel.inner_text()
               and "may still bill" in page.locator(".media-jobs-bar .hint").inner_text())
    cancel.click()
    page.locator(".media-job").filter(has_text="a second render").filter(has_text="cancel not confirmed").wait_for(timeout=20000)
    text = _job_card(page, "a second render").inner_text()
    gate.check("a cancel the provider cannot confirm is shown as not confirmed and says it may still bill",
               "cancel not confirmed" in text and "may still run and bill" in text, text=text[:240])
    gate.measure(page, "media-after-actions")
    page.context.close()


def scenario_media_axe(gate: Gate, browser) -> None:
    page = gate.page(browser, 1280, 900, bypass_csp=True)
    gate.visit(page, "/providers?jobs=all", "media-axe", ready="#media-jobs")
    page.locator("details.media-details").first.locator("summary").click()
    gate.axe(page, "/providers (media section open)")
    page.context.close()


SCENARIOS: dict[str, Callable[[Gate, Any], None]] = {"media": scenario_media, "media-axe": scenario_media_axe}
