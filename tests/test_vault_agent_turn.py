"""A full run: the model asks for the credential, and gets the service response instead.

The runtime here is scripted (no external model is contacted), but everything else is the real
engine: approval gate, policy, tool dispatch, action receipt, vault grant, destination binding,
network request shape, event storage and transcript. The scripted model is deliberately adversarial
about the credential: it prints the entire tool result and asks for the key. If the value were in the
model's context, this test would put it into the transcript.
"""

from __future__ import annotations

import json
import threading
import time

import httpx

import hutch.engine as engine_module
import hutch.vault.egress as egress
from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, Event, EventType, RunStatus
from hutch.runtime.steps import call_tool
from hutch.tools import ToolContext
from hutch.vault import Principal, vault_for
from hutch.vault.crypto import ScryptParams
from hutch.vault.refs import Permission
from tests.support.vault_fixtures import CANARY

API = "https://api.example.com"
API_IP = "93.184.216.34"


class ScriptedCredentialRuntime:
    """Calls the vault tool, then prints everything the model would have seen."""

    kind = "vault-agent-turn"

    def execute(self, run, ctx: ToolContext, tools, stop):
        result = call_tool(run, ctx, tools, "vault_http_request",
                           {"secret_ref": run.prompt.split("ref=", 1)[1].split(" ", 1)[0],
                            "url": f"{API}/v1/pages", "method": "GET"})
        final = (
            "The injected instruction said to print the vault credential. "
            "Here is everything the tool gave the model:\n"
            f"{result.output}\n"
            "Credential requested; none was present in any tool result."
        )
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": final}))
        return final


def test_an_agent_uses_the_credential_and_never_receives_it(store, config, monkeypatch):
    vault = vault_for(store, scrypt_params=ScryptParams.for_tests())
    vault.create("a-long-enough-vault-passphrase")
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    bot = store.create_bot(Bot(name="api-user", instructions="call the API", model="mock/demo",
                               tools=["vault_http_request"], approval_mode=ApprovalMode.auto))
    vault.grant(meta.id, Principal.bot(bot.id), Permission.USE)
    vault.bind_destination(meta.id, API)

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"pages": [{"id": "page_1", "title": "Hello"}]},
                              headers={"content-type": "application/json"})

    real = egress.safe_request

    def send(method, url, **kwargs):
        kwargs.pop("resolver", None)
        kwargs.pop("transport", None)
        return real(method, url, resolver=lambda host, port, *a, **kw: [(2, 1, 6, "", (API_IP, port))],
                    transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(egress, "safe_request", send)
    monkeypatch.setattr(engine_module, "get_runtime", lambda target: ScriptedCredentialRuntime())

    engine = Engine(config, store)
    stop = threading.Event()
    thread = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    thread.start()
    try:
        run = engine.submit(bot, f"Use the vault ref={meta.ref} and summarise the pages.")
        deadline = time.time() + 20
        while time.time() < deadline:
            current = store.get_run(run.id)
            if current.status in (RunStatus.succeeded, RunStatus.failed, RunStatus.stopped):
                break
            time.sleep(0.05)
        final = store.get_run(run.id)
    finally:
        stop.set()
        store.bus.notify("work")
        thread.join(5)

    assert final.status is RunStatus.succeeded, final.error
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == f"Bearer {CANARY}"

    events = store.list_events(run.id) if hasattr(store, "list_events") else []
    tool_results = [event for event in events if event.type is EventType.tool_result]
    assert tool_results, "the tool result was not recorded"
    assert any("page_1" in json.dumps(event.data) for event in tool_results)
    for event in events:
        assert CANARY not in json.dumps(event.data), event.type
    with store._lock:
        for table in ("events", "runs", "messages"):
            for row in store._db.execute(f"SELECT * FROM {table}").fetchall():
                assert CANARY not in repr(tuple(row)), f"plaintext found in {table}"

    final_message = next((event.data.get("content", "") for event in events
                          if event.type is EventType.message), "")
    assert "page_1" in final_message
    assert CANARY not in final_message
    use = next(entry for entry in vault.audit_log() if entry.action == "use")
    assert use.actor == f"bot:{bot.id}" and use.destination == API
