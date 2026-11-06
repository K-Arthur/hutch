"""Who can pay for media, and the whole tool path through the real service and SQLite store.

Backends exist only where a credential exists; several capable backends is a refusal to choose,
not a coin toss between billing accounts. Provider replies are ``httpx.MockTransport`` shaped
after each vendor's documentation (protocol evidence, not live evidence).
"""

from __future__ import annotations

import json

import httpx
import pytest

from hutch.connections import ConnectionBook
from hutch.media import MediaJobService, MediaStorage, MediaUnavailableError
from hutch.media.backends import build_backends
from hutch.media.spool import MediaSpool
from hutch.tools.media import CreateMediaTool
from tests.support.audio import install_fake_transport, make_ctx
from tests.test_media_durability import PNG, _wav

WAV = _wav()
NO_ENV: dict = {}


def connect(config, template: str, *, name: str = "", key: str = "sk-unit-secret-value") -> None:
    book = ConnectionBook(config.state_dir)
    book.add(template, name=name or template)
    if key:
        book.set_key(name or template, key)


# ---------------------------------------------------------------- who can pay


def test_a_connection_with_a_key_yields_its_routes_and_nothing_else(config):
    connect(config, "xai")
    names = sorted(build_backends(config.state_dir, environ=NO_ENV))
    assert names == ["xai-image:xai", "xai-speech:xai", "xai-video:xai"]


def test_a_connection_without_a_key_yields_nothing(config):
    connect(config, "xai", key="")
    assert build_backends(config.state_dir, environ=NO_ENV) == {}


def test_documented_blocked_and_retired_routes_are_never_built(config):
    for template in ("xai", "minimax", "google-gemini", "openai-api"):
        connect(config, template)
    names = " ".join(build_backends(config.state_dir, environ=NO_ENV))
    for dead in ("openai-video", "google-veo", "google-omni-video", "minimax-video", "runway"):
        assert dead not in names


def test_an_environment_key_makes_an_ambient_backend_that_says_so(config):
    backends = build_backends(config.state_dir, environ={"FAL_KEY": "fal-unit-secret"})
    assert sorted(backends) == ["fal-image", "fal-video"]
    caps = backends["fal-image"].capabilities()
    assert caps["credential"] == "environment variable FAL_KEY (ambient)"
    assert "fal-unit-secret" not in json.dumps(caps) and caps["billing"] == "vendor account (per request)"


def test_the_approval_detail_names_the_connection_and_never_the_key(config):
    connect(config, "xai", key="sk-unit-secret-value")
    backend = build_backends(config.state_dir, environ=NO_ENV)["xai-image:xai"]
    detail = backend.approval_detail({"prompt": "a fox"})
    assert detail["connection"] == "xai" and detail["credential"].startswith("connection xai")
    assert "sk-unit-secret-value" not in json.dumps(detail) + json.dumps(backend.capabilities())


def test_two_accounts_that_could_pay_are_never_chosen_between(config, store):
    connect(config, "xai")
    connect(config, "openai-api")
    backends = build_backends(config.state_dir, environ=NO_ENV)
    service = MediaJobService(store, MediaStorage(config), backends=backends)
    with pytest.raises(MediaUnavailableError, match="name one with backend_hint.*does not choose"):
        service.backend_for("image")
    assert service.backend_for("image", "xai-image:xai").name == "xai-image:xai"
    assert service.backend_for("video").name == "xai-video:xai", "one capable backend needs no hint"


def test_an_ambient_openai_key_and_a_connection_are_two_backends_not_one(config):
    connect(config, "openai-api")
    backends = build_backends(config.state_dir, environ={"OPENAI_API_KEY": "sk-ambient-unit"})
    assert {"openai-image:openai-api", "openai-images"} <= set(backends)
    assert "ambient" in backends["openai-images"].capabilities()["credential"]


def test_backends_are_built_with_a_durable_spool_when_one_is_given(config, tmp_path):
    connect(config, "xai")
    spool = MediaSpool(tmp_path / "media")
    backend = build_backends(config.state_dir, spool=spool, environ=NO_ENV)["xai-speech:xai"]
    assert backend.capabilities()["durable_results"] is True


# ---------------------------------------------------------------- the tool path


def test_create_media_speaks_through_an_xai_connection_and_records_what_it_estimated(
        store, config, tmp_path, monkeypatch):
    connect(config, "xai")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})

    install_fake_transport(monkeypatch, handler)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctx, gate = make_ctx(store, config, tmp_path)

    result = CreateMediaTool().run({"kind": "audio", "prompt": "Hutch speech check.", "voice": "ara"}, ctx)

    assert result.ok, result.output
    assert seen[0].url == "https://api.x.ai/v1/tts"
    assert json.loads(seen[0].content)["voice_id"] == "ara"
    assert result.data["media"]["backend"] == "xai-speech:xai"
    detail = gate.calls[0]["detail"]
    assert detail["connection"] == "xai" and detail["provider"] == "xai"
    assert detail["cost"].startswith("cost unknown"), "no price was readable, so none is invented"
    assert "sk-unit-secret-value" not in json.dumps(detail, default=str)
    usage = tuple(store._db.execute("SELECT provider, kind, account_id, cost_usd, cost_source FROM usage "
                                    "WHERE run_id = ?", (ctx.run.id,)).fetchone())
    assert usage == ("xai", "speech", "xai", 0.0, "unpriced")
    assert "cost unknown" in result.output


def test_a_priced_route_shows_the_estimate_before_approval_and_records_it(
        store, config, tmp_path, monkeypatch):
    connect(config, "google-gemini")
    body = {"steps": [{"content": [{"type": "audio", "data": __import__("base64").b64encode(WAV).decode()}]}]}
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json=body))
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "audio", "prompt": "x" * 150}, ctx)
    assert result.ok, result.output
    assert "estimated about $0.0022" in gate.calls[0]["detail"]["cost"]
    row = store._db.execute("SELECT cost_usd, cost_source FROM usage WHERE run_id = ?",
                            (ctx.run.id,)).fetchone()
    assert (round(row["cost_usd"], 4), row["cost_source"]) == (0.0022, "estimated")


def test_an_out_of_limit_request_is_refused_before_any_approval_prompt(
        store, config, tmp_path, monkeypatch):
    connect(config, "xai")
    called: list[int] = []
    install_fake_transport(monkeypatch, lambda r: called.append(1) or httpx.Response(200))
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "video", "prompt": "waves", "seconds": 90}, ctx)
    assert not result.ok and "1 to 15 seconds" in result.output and "Nothing was sent" in result.output
    assert gate.calls == [] and called == []


def test_a_provider_refusal_reaches_the_user_as_a_refusal(store, config, tmp_path, monkeypatch):
    connect(config, "minimax")
    body = {"base_resp": {"status_code": 1026, "status_msg": "input new_sensitive"}}
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json=body))
    ctx, _ = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "image", "prompt": "x"}, ctx)
    assert not result.ok
    assert "declined" in result.output and "refusal, not an outage" in result.output
    job = store.media_jobs_for_run(ctx.run.id)[0]
    assert job["error"].startswith("refused:") and "1026" in job["error"]


def test_two_paying_accounts_make_the_tool_ask_which_one(store, config, tmp_path, monkeypatch):
    connect(config, "xai")
    connect(config, "minimax")
    install_fake_transport(monkeypatch, lambda r: httpx.Response(200, json={}))
    ctx, gate = make_ctx(store, config, tmp_path)
    result = CreateMediaTool().run({"kind": "audio", "prompt": "hello"}, ctx)
    assert not result.ok and "name one with backend_hint" in result.output and gate.calls == []


def test_a_task_route_returns_a_resumable_job_when_it_outlasts_the_tool_call(
        store, config, tmp_path, monkeypatch):
    connect(config, "xai")

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "slow-1"})
        return httpx.Response(200, json={"status": "pending"})

    install_fake_transport(monkeypatch, handler)
    ctx, _ = make_ctx(store, config, tmp_path)
    tool = CreateMediaTool(poll_interval=0.0, max_polls=2)
    result = tool.run({"kind": "video", "prompt": "waves", "seconds": 3}, ctx)
    assert not result.ok and "still running upstream" in result.output and "advance" in result.output
    job = store.media_jobs_for_run(ctx.run.id)[0]
    assert job["status"] == "running" and job["upstream_job_id"] == "slow-1"
    assert PNG  # silence unused-import lint in a file that only needs the fixture module loaded
