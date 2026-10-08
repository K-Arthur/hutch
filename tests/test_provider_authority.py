"""Provider/account changes require outward authority; credential rotation remains effective."""
from contextlib import contextmanager
import threading
import time

import pytest

from hutch.approvals import DeniedError, resolve_approval
from hutch.connections import ConnectionBook
from hutch.models import RunStatus
from hutch.providers.base import ProviderError
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.runtime import RunAborted
from hutch.runtime.ladder import Ladder, get_provider, make_rung
from hutch.models import ApprovalMode, Limits
from tests.fakes import FakeOpenAI, agent_script
from tests.test_runtime_builtin import build, run_it, runtime, factory


@contextmanager
def in_worker(ctx, fn):
    result = {}
    def execute():
        try:
            result["reply"] = fn()
        except BaseException as exc:
            result["error"] = exc
    t = threading.Thread(target=execute)
    t.start()
    try:
        yield result
    finally:
        ctx.gate.cancel_requested = True
        t.join(5)
        assert not t.is_alive(), "the approval worker must finish before persistence closes"


def pending(store):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if requests := store.pending_approvals():
            return requests[0]
        time.sleep(.01)
    pytest.fail("no outward approval appeared")


def test_account_policy_is_refreshed_after_a_tool_approval(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_TEST_ACCOUNT_KEY", "fixture-only-key")
    server = FakeOpenAI()
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", name="metered", base_url=server.url + "/v1", account_id="original",
             api_key_env="HUTCH_TEST_ACCOUNT_KEY", quota={"tokens": 100000, "window": "day"})
    server.script = agent_script([
        {"content": "write", "tool_calls": [{"name": "write_file", "arguments": {"path": "proof.txt", "content": "reviewed"}}],
         "prompt_tokens": 10, "completion_tokens": 3},
        {"content": "must not be requested", "prompt_tokens": 10, "completion_tokens": 3}])
    ctx, run, emitted, tools = build(store, config, tmp_path, model="metered/m", mode=ApprovalMode.ask,
                                     limits=Limits(max_turn_tokens=64))
    store.set_status(run, RunStatus.running)
    try:
        with in_worker(ctx, lambda: run_it(runtime(), run, ctx, tools)) as result:
            req = pending(store)
            assert req.tool == "files"
            book.update("metered", account_id="replacement", quota={"tokens": 1, "window": "day"})
            assert resolve_approval(store, req.id, approve=True, by="fixture")
        assert isinstance(result["error"], RunAborted) and "allowance" in result["error"].detail
        assert len(server.of("/v1/chat/completions")) == 1
        with store._lock:
            rows = store._db.execute("SELECT account_id, status FROM usage_reservations WHERE run_id = ?", (run.id,)).fetchall()
        assert [(r["account_id"], r["status"]) for r in rows] == [("original", "settled")]
    finally:
        server.close()


def test_hosted_to_different_hosted_fallback_does_not_send_without_a_decision(store, config, tmp_path):
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", fallbacks=["anthropic/claude-test"])
    store.set_status(run, RunStatus.running)
    store.allow_sticky(ctx.bot.id, "escalate:hosted")
    calls = []
    def factory(provider, base):
        calls.append(provider)
        if provider == "openai":
            raise ProviderError("unreachable", "fixture primary down")
        pytest.fail("a denied fallback must never construct/call its provider")
    rt = runtime(provider_factory=factory)
    with in_worker(ctx, lambda: run_it(rt, run, ctx, tools)) as result:
        req = pending(store)
        assert req.outward and not req.sticky_key
        assert req.detail["account"] == "anthropic"
        assert req.detail["destination"] == "https://api.anthropic.com"
        assert req.detail["scope"] == "provider calls in this run on this exact route"
        assert req.action_hash
        resolve_approval(store, req.id, approve=False, by="fixture")
    assert isinstance(result["error"], RunAborted)
    assert calls == ["openai"]


@pytest.mark.parametrize(("status", "message", "headers", "expected_attempts"), [
    (401, "invalid API key", {}, 1),
    (429, "quota exceeded", {"retry-after": "1"}, 2),
])
def test_provider_auth_or_quota_rejection_waits_for_review_before_paid_fallback(
        store, config, tmp_path, status, message, headers, expected_attempts):
    server = FakeOpenAI()
    server.force_status = (status, {"error": {"message": message}}, headers)
    constructed = []

    def provider_factory(provider, base_url):
        constructed.append(provider)
        if provider == "openai":
            return OpenAICompatProvider(server.url + "/v1", "fixture-key", "openai")
        pytest.fail(f"fallback provider {provider} must not start before approval")

    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o-mini",
                                         fallbacks=["anthropic/claude-test"], tools=())
        store.set_status(run, RunStatus.running)
        with in_worker(ctx, lambda: run_it(runtime(provider_factory=provider_factory), run, ctx, tools)) as result:
            req = pending(store)
            assert req.outward and not req.sticky_key
            assert req.detail["account"] == "anthropic"
            assert message in req.detail["reason"]
            assert constructed and set(constructed) == {"openai"}
            assert len(server.of("/v1/chat/completions")) == expected_attempts
            assert all(row["status"] == "uncertain" for row in store.unresolved_usage_reservations())
            assert resolve_approval(store, req.id, approve=False, by="fixture")
        assert isinstance(result["error"], RunAborted)
        assert constructed and set(constructed) == {"openai"}
    finally:
        server.close()


def test_connection_revision_change_during_review_is_refused(store, config, tmp_path, monkeypatch):
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", name="secondary", base_url="https://old.example.test/v1", account_id="shared-account")
    ctx, run, emitted, tools = build(store, config, tmp_path)
    store.set_status(run, RunStatus.running)
    rt = runtime()
    ladder = Ladder(ctx.bot)
    rung = make_rung("secondary/model", "fallback")
    with in_worker(ctx, lambda: rt._ask_first_hosted(ctx, ladder, rung, "primary down", 50)) as result:
        req = pending(store)
        assert req.detail["destination"] == "https://old.example.test/v1"
        book.update("secondary", base_url="https://new.example.test/v1")
        resolve_approval(store, req.id, approve=True, by="fixture")
    assert isinstance(result["error"], DeniedError)
    assert not ladder.authorized_routes


def test_approved_route_is_scoped_to_one_run_not_all_hosted_accounts(store, config, tmp_path, monkeypatch):
    ctx, run, emitted, tools = build(store, config, tmp_path)
    rt = runtime()
    ladder = Ladder(ctx.bot)
    decisions = []
    monkeypatch.setattr(ctx.gate, "decide", lambda *args, **kw: decisions.append((args, kw)))
    for spec in ("openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-test"):
        rt._ask_first_hosted(ctx, ladder, make_rung(spec, "fallback"), "fixture", 50)
    assert len(decisions) == 2  # same authority may change explicitly configured models in this run
    rt._ask_first_hosted(ctx, Ladder(ctx.bot), make_rung("openai/gpt-4o", "fallback"), "new run", 50)
    assert len(decisions) == 3
    assert all(kw["outward"] and kw["ask_in_auto"] for args, kw in decisions)


def test_rotated_and_removed_connection_key_never_reuses_a_previous_client(store, config, tmp_path, monkeypatch):
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", name="rotation", base_url="https://provider.example.test/v1", api_key_env="HUTCH_TEST_ROTATION_KEY")
    ctx, run, emitted, tools = build(store, config, tmp_path, model="rotation/m")
    rt = runtime()
    ladder = Ladder(ctx.bot)
    monkeypatch.setenv("HUTCH_TEST_ROTATION_KEY", "first-fixture-key")
    first = rt._provider_for(ctx, ladder, ladder.primary)
    monkeypatch.setenv("HUTCH_TEST_ROTATION_KEY", "replacement-fixture-key")
    second = rt._provider_for(ctx, ladder, ladder.primary)
    assert first is not second and second.api_key == "replacement-fixture-key"
    monkeypatch.delenv("HUTCH_TEST_ROTATION_KEY")
    with pytest.raises(ProviderError, match="no API key"):
        rt._provider_for(ctx, ladder, ladder.primary)


def test_ambient_key_rotation_replaces_cached_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "first-fixture-key")
    first = get_provider("openai", None)
    monkeypatch.setenv("OPENAI_API_KEY", "replacement-fixture-key")
    second = get_provider("openai", None)
    assert first is not second and second.api_key == "replacement-fixture-key"


def test_reviewed_connection_cannot_be_swapped_at_provider_creation(store, config, tmp_path, monkeypatch):
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", name="reviewed", base_url="https://old.example.test/v1", api_key_env="HUTCH_TEST_ROTATION_KEY")
    monkeypatch.setenv("HUTCH_TEST_ROTATION_KEY", "fixture-key")
    ctx, run, emitted, tools = build(store, config, tmp_path, model="reviewed/m")
    rt, ladder = runtime(), Ladder(ctx.bot)
    reviewed = rt._route_identity(ctx, ladder, ladder.primary)
    book.update("reviewed", base_url="https://different.example.test/v1")
    with pytest.raises(ProviderError, match="changed after review"):
        rt._provider_for(ctx, ladder, ladder.primary, expected_route=reviewed)


def test_connection_cannot_store_embedded_basic_credentials(config):
    book = ConnectionBook(config.state_dir)
    with pytest.raises(ValueError, match="embedded credentials"):
        book.add("custom-openai", name="unsafe-url", base_url="https://user:password@example.test/v1")
    assert not book.get("unsafe-url")


def test_stream_retry_gets_another_reservation_and_retains_uncertain_first_usage(store, config, tmp_path):
    server = FakeOpenAI()
    try:
        server.fail_stream_once = True
        server.script = lambda body: {"content": "fixture done", "prompt_tokens": 10, "completion_tokens": 3}
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", tools=())
        store.set_status(run, RunStatus.running)
        assert run_it(runtime(provider_factory=factory(oai=server)), run, ctx, tools) == "fixture done"
        assert [r["body"]["stream"] for r in server.of("/v1/chat/completions")] == [True, False]
        rows = store._db.execute("SELECT status FROM usage_reservations WHERE run_id=? ORDER BY rowid", (run.id,)).fetchall()
        assert [r["status"] for r in rows] == ["uncertain", "settled"]
        assert len(store.unresolved_usage_reservations()) == 1
    finally:
        server.close()


def test_stream_retry_refuses_when_another_reservation_would_exceed_the_bot_budget(store, config, tmp_path):
    server = FakeOpenAI()
    try:
        server.fail_stream_once = True
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", tools=(),
                                         limits=Limits(max_turn_tokens=1000, daily_token_cap=2000))
        store.set_status(run, RunStatus.running)
        # Each attempt reserves a 1,000-token response plus the same nonempty prompt.
        with pytest.raises(RunAborted) as exc:
            run_it(runtime(provider_factory=factory(oai=server)), run, ctx, tools)
        assert exc.value.reason == "token_cap"
        assert [r["body"]["stream"] for r in server.of("/v1/chat/completions")] == [True]
        assert len(store.unresolved_usage_reservations()) == 1
    finally:
        server.close()
