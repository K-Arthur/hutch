"""The Media, speech and search section as served: routes from data, jobs from the ledger, honest wording."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.media.providers.route_spec import load_routes
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.server.app import create_app


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "XAI_API_KEY", "FAL_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        yield client


def _jobs(client, rows):
    store = client.app.state.store
    bot = Bot(name="media-page-bot", model="x/y", tools=[], approval_mode=ApprovalMode.ask)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="p", status=RunStatus.running)
    store.create_run(run)
    with store._lock:
        for index, (status, error, prompt) in enumerate(rows):
            store._db.execute(
                "INSERT INTO media_jobs (id, run_id, conversation_id, kind, backend, status, requested, created_at,"
                " updated_at, error, idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"mj_{index:016x}", run.id, run.conversation_id, "video", "xai-video:xai", status,
                 '{"prompt": "%s"}' % prompt, "2026-11-06T00:00:00Z", "2026-11-06T00:00:00Z", error, f"key-{index}"))
        store._db.commit()


def _section(html: str) -> str:
    return html[html.index('id="media"'):html.index('aria-labelledby="local-h"')]


def test_every_media_route_is_in_the_table_and_none_is_called_working(env):
    section = _section(env.get("/providers").text)
    for route_id in load_routes():
        assert f'<span class="mono">{route_id}</span>' in section, route_id
    assert "No route in the table below has a dated live run" in section
    table = section[section.index('class="media-table"'):section.index("</table>")]
    assert "chip st-succeeded" not in table


def test_retired_routes_say_retired_and_since_when(env):
    section = _section(env.get("/providers").text)
    assert "retired by provider" in section and re.search(r"since 20\d\d-\d\d-\d\d", section)


def test_an_open_job_offers_check_and_cancel_and_a_refusal_offers_neither(env):
    _jobs(env, [("running", None, "waves"), ("failed", "refused: policy says no", "bad prompt"),
                ("failed", "cancel_unconfirmed: no reply", "slow prompt"), ("succeeded", None, "done prompt")])
    section = _section(env.get("/providers").text)
    assert section.count('data-job-action="advance"') == 1 and section.count('data-job-action="cancel"') == 1
    assert "waves" in section and "bad prompt" not in section          # finished jobs are hidden by default
    everything = _section(env.get("/providers", params={"jobs": "all"}).text)
    assert "declined this request under its content policy" in everything
    assert "Reason: refused: policy says no" in everything
    assert "may still run and bill" in everything
    assert everything.count('data-job-action="advance"') == 1          # still only the running one


def test_with_no_jobs_the_section_says_so(env):
    section = _section(env.get("/providers").text)
    assert "No media jobs are open." in section and 'data-job-action' not in section


def test_search_lists_built_routes_and_the_providers_that_only_claim_the_service(env):
    section = _section(env.get("/providers").text)
    search = section[section.index("provider search and Hutch's live_search") - 400:]
    assert "Xiaomi MiMo" in search and "A built provider search route" in search
    assert re.search(r"no route in Hutch yet: [^<]*Google[^<]*xAI|no route in Hutch yet: [^<]*xAI[^<]*Google", search)
    assert "Hutch never switches from one to the other for you" in search


def test_the_job_calls_the_script_makes_are_refused_cross_site_and_accepted_same_origin(env):
    path = "/api/v1/media/jobs/mj_0000000000000000/advance"
    assert env.post(path, headers={"Origin": "https://evil.example"}).status_code == 403
    assert env.post(path, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert env.post(path, headers={"Origin": "http://testserver"}).status_code == 404     # accepted, then no such job


def test_the_script_calls_the_job_api_and_asks_twice_before_cancelling():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "src/hutch/server/static/media-jobs.js").read_text()
    assert "/api/v1/media/jobs/" in source and "X-CSRF" not in source
    assert "Confirm: cancel this job" in source and "may not confirm, and may still bill" in source
