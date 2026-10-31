"""The vault tool through the real dispatcher: authorization, approval, audit and no value in context."""

from __future__ import annotations

import json

import httpx
import pytest

import hutch.vault.egress as egress
from hutch.approvals import ApprovalGate, resolve_approval
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext
from hutch.vault import Principal, vault_for
from hutch.vault.crypto import ScryptParams
from hutch.vault.refs import Permission
from hutch.runtime.steps import call_tool
from tests.support.vault_fixtures import BOT_A, CANARY, DESTINATION

API = "https://api.example.com"
API_IP = "93.184.216.34"


def _resolver(mapping):
    def resolve(host, port, *a, **kw):
        ips = mapping[host] if isinstance(mapping, dict) else mapping(host)
        return [(2 if ":" not in ip else 10, 1, 6, "", (ip, port)) for ip in ips]
    return resolve


class Recorder:
    def __init__(self, response):
        self.requests: list[httpx.Request] = []
        self.response = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response


def _ctx(store, config, tmp_path, *, approval_mode=ApprovalMode.auto, tools=("vault_http_request",)):
    bot = Bot(id=BOT_A, name="vault-user", instructions="use the API", model="mock/demo",
              tools=list(tools), approval_mode=approval_mode)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="call the API", status=RunStatus.running)
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda event: store.append_event(event),
                        poll_seconds=0.01)
    return ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                       config=config, workspace=workspace, emit=store.append_event)


def _ready(store, config, tmp_path, **kwargs):
    ctx = _ctx(store, config, tmp_path, **kwargs)
    vault = vault_for(store, scrypt_params=ScryptParams.for_tests())
    vault.create("a-long-enough-vault-passphrase")
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, API)
    return ctx, vault, meta


def _wire(monkeypatch, handler, mapping=None):
    real = egress.safe_request
    recorder = Recorder(handler)
    resolver = _resolver(mapping or {"api.example.com": [API_IP]})

    def send(method, url, **kwargs):
        kwargs.pop("resolver", None)
        kwargs.pop("transport", None)
        return real(method, url, resolver=resolver, transport=httpx.MockTransport(recorder), **kwargs)

    monkeypatch.setattr(egress, "safe_request", send)
    return recorder


def _call(ctx, meta, **overrides):
    args = {"secret_ref": meta.ref, "url": f"{API}/v1/pages", "method": "GET"}
    args.update(overrides)
    tools = build_tools(ctx.bot.tools, ctx)
    return call_tool(ctx.run, ctx, tools, "vault_http_request", args)


def test_a_real_dispatch_uses_the_credential_and_returns_only_the_response(store, config, tmp_path, monkeypatch):
    ctx, vault, meta = _ready(store, config, tmp_path)
    recorder = _wire(monkeypatch, httpx.Response(200, json={"pages": [{"id": "page_1"}]},
                                                 headers={"content-type": "application/json"}))
    result = _call(ctx, meta)

    assert result.ok, result.output
    assert "page_1" in result.output
    assert CANARY not in result.output and CANARY not in json.dumps(result.data)
    [request] = recorder.requests
    assert request.headers["authorization"] == f"Bearer {CANARY}"
    assert request.headers["host"] == "api.example.com"

    # Nothing persisted about the call contains the value: events, action receipts, or messages.
    with store._lock:
        for table in ("events", "runs", "messages", "tool_actions"):
            try:
                rows = store._db.execute(f"SELECT * FROM {table}").fetchall()
            except Exception:
                continue
            for row in rows:
                assert CANARY not in repr(tuple(row)), f"plaintext found in {table}"
    use = next(entry for entry in vault.audit_log() if entry.action == "use")
    assert use.destination == API and use.outcome == "ok"


def test_an_ask_mode_bot_pauses_and_the_approval_detail_has_no_value(store, config, tmp_path, monkeypatch):
    ctx, vault, meta = _ready(store, config, tmp_path, approval_mode=ApprovalMode.ask)
    recorder = _wire(monkeypatch, httpx.Response(200, text="ok"))
    result = {}

    import threading
    worker = threading.Thread(target=lambda: result.setdefault("value", _call(ctx, meta)))
    worker.start()
    import time
    deadline = time.time() + 5
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.01)
    [approval] = store.pending_approvals()
    assert approval.tool == "vault_http_request"
    assert approval.detail["destination"] == API
    assert approval.detail["secret_ref"] == meta.ref
    assert CANARY not in json.dumps(approval.detail)
    assert recorder.requests == []
    resolve_approval(store, approval.id, approve=True, by="test")
    worker.join(5)
    assert result["value"].ok
    assert len(recorder.requests) == 1


def test_an_unbound_destination_fails_without_a_request(store, config, tmp_path, monkeypatch):
    ctx, vault, meta = _ready(store, config, tmp_path)
    vault.unbind_destination(meta.id, API)
    recorder = _wire(monkeypatch, httpx.Response(200, text="should not happen"))
    result = _call(ctx, meta)
    assert not result.ok
    assert "not bound" in result.output
    assert recorder.requests == []


def test_a_private_url_is_refused_by_policy_before_the_vault_is_touched(store, config, tmp_path, monkeypatch):
    ctx, _vault, meta = _ready(store, config, tmp_path)
    recorder = _wire(monkeypatch, httpx.Response(200, text="should not happen"))
    result = _call(ctx, meta, url="http://127.0.0.1:8080/admin")
    assert not result.ok
    assert "non-public" in result.output
    assert recorder.requests == []


def test_a_redirect_is_reported_and_not_followed(store, config, tmp_path, monkeypatch):
    ctx, _vault, meta = _ready(store, config, tmp_path)
    recorder = _wire(monkeypatch, httpx.Response(
        302, headers={"location": "https://evil.example/collect"}),
        {"api.example.com": [API_IP], "evil.example": ["93.184.216.35"]})
    result = _call(ctx, meta, url=f"{API}/start")
    assert not result.ok
    assert "not followed" in result.output
    assert "evil.example" in result.output
    assert len(recorder.requests) == 1


def test_the_schema_the_model_sees_accepts_only_the_opaque_reference(store, config, tmp_path):
    ctx, _vault, _meta = _ready(store, config, tmp_path)
    spec = build_tools(ctx.bot.tools, ctx)["vault_http_request"].spec()
    properties = spec["function"]["parameters"]["properties"]
    assert "value" not in properties
    assert properties["secret_ref"]["pattern"].startswith("^secret://hutch/local/sec_")
    assert set(properties["method"]["enum"]) == {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}


def test_the_recorded_call_drops_a_query_string_and_a_body(store, config, tmp_path):
    """Authorization is by origin; a model-authored query or body must not reach the event log."""
    ctx, _vault, meta = _ready(store, config, tmp_path)
    tool = build_tools(ctx.bot.tools, ctx)["vault_http_request"]
    recorded = tool.recorded_arguments(
        {"secret_ref": meta.ref, "url": "https://api.example.com/v1/pages?token=model-chosen-caption",
         "method": "POST", "body": "{\"a\": 1}"}, ctx)
    assert recorded["url"] == "https://api.example.com/v1/pages?[redacted]"
    assert "body" not in recorded
    assert recorded["secret_ref"] == meta.ref
    assert "model-chosen-caption" not in json.dumps(recorded)


def test_a_malformed_recorded_url_is_replaced_not_stored(store, config, tmp_path):
    ctx, _vault, meta = _ready(store, config, tmp_path)
    tool = build_tools(ctx.bot.tools, ctx)["vault_http_request"]
    recorded = tool.recorded_arguments({"secret_ref": meta.ref, "url": "file:///etc/passwd"}, ctx)
    assert recorded["url"] == "<invalid URL>"
