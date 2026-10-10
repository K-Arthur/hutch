from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.outlook_calendar import OutlookCalendarError
from hutch.outlook_calendar_write import (
    CALENDAR_WRITE_CALLBACK_PATH,
    CALENDAR_WRITE_SCOPE,
    OutlookCalendarWriteBook,
    OutlookCalendarWriteOutcomeUnknown,
)


class MemorySecrets:
    def __init__(self):
        self.values = {}

    @staticmethod
    def available():
        return True

    def put(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


def seed_account(book, account_id="mscalw_0123456789abcdef01234567", scopes=None):
    book._write_accounts({"version": 1, "accounts": {account_id: {
        "id": account_id, "label": "Work calendar", "created_at": "2026-10-10T00:00:00+00:00",
        "scopes": scopes or [CALENDAR_WRITE_SCOPE], "status": "connected"}}})
    book.secrets.put(account_id, "refresh-token")
    return account_id


def test_write_oauth_uses_distinct_scope_callback_account_and_secret_namespace(tmp_path):
    def handler(request):
        assert request.url.host == "login.microsoftonline.com"
        return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                         "expires_in": 3600, "token_type": "Bearer",
                                         "scope": "Calendars.ReadWrite offline_access"})

    secrets = MemorySecrets()
    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=secrets,
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    callback = "http://localhost:18787" + CALENDAR_WRITE_CALLBACK_PATH
    auth = book.start("Work events", callback)
    query = parse_qs(urlsplit(auth.url).query)
    assert query["scope"] == ["Calendars.ReadWrite offline_access"]
    assert query["redirect_uri"] == [callback]
    account = book.finish(auth.state, "single-use-code", callback)
    assert account["id"].startswith("mscalw_")
    assert account["scopes"] == [CALENDAR_WRITE_SCOPE]
    assert secrets.values[account["id"]] == "refresh-token"
    assert book.root.name == "outlook-calendar-write"


def test_write_oauth_refuses_read_only_scope_response(tmp_path):
    def handler(_request):
        return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                         "expires_in": 3600, "token_type": "Bearer",
                                         "scope": "Calendars.ReadBasic offline_access"})

    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=MemorySecrets(),
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    callback = "http://localhost:18787" + CALENDAR_WRITE_CALLBACK_PATH
    auth = book.start("Work events", callback)
    with pytest.raises(OutlookCalendarError, match="Calendars.ReadWrite permission"):
        book.finish(auth.state, "single-use-code", callback)


@pytest.mark.parametrize("summary,start,end", [
    ("", "2026-10-12T10:00:00-07:00", "2026-10-12T10:30:00-07:00"),
    ("Meeting\r\nInjected", "2026-10-12T10:00:00-07:00", "2026-10-12T10:30:00-07:00"),
    ("Meeting", "2026-10-12T10:00:00", "2026-10-12T10:30:00-07:00"),
    ("Meeting", "2026-10-12T10:00:00-07:00", "2026-10-12T09:30:00-07:00"),
    ("Meeting", "2026-10-12T10:00:00-07:00", "2027-11-01T10:00:00-07:00"),
])
def test_event_arguments_are_bounded_and_require_explicit_valid_times(tmp_path, summary, start, end):
    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=MemorySecrets())
    with pytest.raises(OutlookCalendarError):
        book.prepare_event(summary=summary, start=start, end=end)


def test_create_is_one_fixed_host_write_then_exact_readback_verification(tmp_path):
    requests = []
    secrets = MemorySecrets()

    def handler(request):
        requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        if request.method == "GET" and request.url.path == "/v1.0/me/calendars":
            return httpx.Response(200, json={"value": [{"id": "primary", "name": "Work", "isDefaultCalendar": True}]})
        if request.method == "POST" and request.url.path == "/v1.0/me/calendars/primary/events":
            return httpx.Response(201, json={"id": "event-123", "subject": "Planning", "showAs": "busy"})
        if request.method == "GET" and request.url.path == "/v1.0/me/calendars/primary/events/event-123":
            return httpx.Response(200, json={"id": "event-123", "subject": "Planning",
                "start": {"dateTime": "2026-10-12T17:00:00.0000000", "timeZone": "UTC"},
                "end": {"dateTime": "2026-10-12T17:30:00.0000000", "timeZone": "UTC"},
                "location": {"displayName": "Room 1"}, "attendees": [],
                "body": {"contentType": "text", "content": "Bring the current draft"}})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=secrets,
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account = seed_account(book)
    effects = []
    result = book.create_event(account, "primary", summary="Planning", start="2026-10-12T10:00:00-07:00",
        end="2026-10-12T10:30:00-07:00", description="Bring the current draft", location="Room 1",
        before_write=lambda: effects.append("effect"))

    write = next(request for request in requests if request.method == "POST" and request.url.host == "graph.microsoft.com")
    assert write.headers["authorization"] == "Bearer access-token"
    import json
    assert json.loads(write.read()) == {
        "subject": "Planning",
        "start": {"dateTime": "2026-10-12T17:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-10-12T17:30:00", "timeZone": "UTC"},
        "location": {"displayName": "Room 1"},
        "body": {"contentType": "Text", "content": "Bring the current draft"},
        "attendees": [],
    }
    verification = next(request for request in requests if request.method == "GET" and request.url.path.endswith("/events/event-123"))
    assert "body" in verification.url.params["$select"].split(",")
    assert effects == ["effect"]
    assert len([request for request in requests if request.method == "POST" and request.url.host == "graph.microsoft.com"]) == 1
    assert result == {"id": "event-123", "summary": "Planning", "start": "2026-10-12T17:00:00+00:00",
                      "end": "2026-10-12T17:30:00+00:00", "location": "Room 1"}


def test_uncertain_write_response_is_never_retried(tmp_path):
    writes = []

    def handler(request):
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        if request.method == "GET" and request.url.path == "/v1.0/me/calendars":
            return httpx.Response(200, json={"value": [{"id": "primary", "name": "Work"}]})
        writes.append(request)
        return httpx.Response(503)

    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=MemorySecrets(),
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account = seed_account(book)
    with pytest.raises(OutlookCalendarWriteOutcomeUnknown, match="check the calendar before retrying"):
        book.create_event(account, "primary", summary="Planning", start="2026-10-12T10:00:00-07:00",
            end="2026-10-12T10:30:00-07:00", before_write=lambda: None)
    assert len(writes) == 1


def test_create_readback_must_match_requested_description(tmp_path):
    writes = []

    def handler(request):
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        if request.method == "GET" and request.url.path == "/v1.0/me/calendars":
            return httpx.Response(200, json={"value": [{"id": "primary", "name": "Work"}]})
        if request.method == "POST":
            writes.append(request)
            return httpx.Response(201, json={"id": "event-123"})
        if request.method == "GET" and request.url.path.endswith("/events/event-123"):
            return httpx.Response(200, json={"id": "event-123", "subject": "Planning",
                "start": {"dateTime": "2026-10-12T17:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2026-10-12T17:30:00Z", "timeZone": "UTC"},
                "location": {"displayName": "Room 1"}, "attendees": [],
                "body": {"contentType": "text", "content": "Different description"}})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=MemorySecrets(),
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account = seed_account(book)
    with pytest.raises(OutlookCalendarWriteOutcomeUnknown, match="could not verify the exact"):
        book.create_event(account, "primary", summary="Planning", start="2026-10-12T10:00:00-07:00",
            end="2026-10-12T10:30:00-07:00", description="Bring the draft", location="Room 1",
            before_write=lambda: None)
    assert len(writes) == 1


def test_create_requires_write_scope_and_effect_lease_before_post(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        return httpx.Response(200, json={"value": [{"id": "primary", "name": "Work"}]})

    book = OutlookCalendarWriteBook(tmp_path, "public-client", secrets_store=MemorySecrets(),
                                    transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account = seed_account(book, scopes=["Calendars.ReadBasic"])
    with pytest.raises(OutlookCalendarError, match="no Calendars.ReadWrite grant"):
        book.create_event(account, "primary", summary="Planning", start="2026-10-12T10:00:00-07:00",
            end="2026-10-12T10:30:00-07:00", before_write=lambda: None)
    assert not any(request.method == "POST" and request.url.host == "graph.microsoft.com" for request in requests)

    seed_account(book)
    with pytest.raises(OutlookCalendarError, match="not sent"):
        book.create_event(account, "primary", summary="Planning", start="2026-10-12T10:00:00-07:00",
            end="2026-10-12T10:30:00-07:00", before_write=lambda: "run lost ownership")
    assert not any(request.method == "POST" and request.url.host == "graph.microsoft.com" for request in requests)


def test_write_grants_are_per_bot_persisted_and_revocable(store):
    from hutch.models import Bot

    bot = store.create_bot(Bot(name="outlook-event-helper", model="mock/demo", tools=[]))
    grant = store.set_outlook_calendar_write_grant(bot.id, "mscalw_0123456789abcdef01234567",
        "Work events", "calendar-1", "Work")
    assert grant == store.outlook_calendar_write_grant(bot.id)
    assert store.list_outlook_calendar_write_grants() == [{**grant, "bot_name": bot.name}]
    assert store.remove_outlook_calendar_write_account_grants(grant["account_id"]) == 1
    assert store.outlook_calendar_write_grant(bot.id) is None
    grant = store.set_outlook_calendar_write_grant(bot.id, "mscalw_0123456789abcdef01234567",
        "Work events", "calendar-1", "Work")
    assert store.remove_outlook_calendar_write_grant(bot.id)
    assert store.outlook_calendar_write_grant(bot.id) is None


def test_calendar_event_tool_shows_exact_approval_and_rechecks_revoke(store, config, tmp_path, monkeypatch):
    from hutch.approvals import DeniedError
    from hutch.models import Bot, InferenceMode, Run
    from hutch.safety import PolicyEngine
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext

    class Gate:
        def __init__(self, on_decide=None, denied=False):
            self.details = []
            self.on_decide = on_decide
            self.denied = denied

        def decide(self, name, summary, detail, *, outward, ask_in_auto):
            self.details.append((name, summary, detail, outward, ask_in_auto))
            if self.on_decide:
                self.on_decide()
            if self.denied:
                raise DeniedError("owner declined")

    writes = []

    class FixtureWriteBook:
        prepare_event = staticmethod(OutlookCalendarWriteBook.prepare_event)

        def __init__(self, *args):
            pass

        def create_event(self, account_id, calendar_id, **kwargs):
            writes.append((account_id, calendar_id, kwargs))
            assert kwargs["before_write"]() is None
            return {"id": "event-1", "summary": kwargs["summary"], "start": kwargs["start"],
                    "end": kwargs["end"], "location": kwargs["location"]}

    monkeypatch.setattr("hutch.tools.outlook_calendar_write.OutlookCalendarWriteBook", FixtureWriteBook)
    bot = store.create_bot(Bot(name="calendar-event-helper", model="ollama/local", tools=[], inference_mode=InferenceMode.local))
    run = Run(bot_id=bot.id, prompt="Add the planning meeting")
    store.create_run(run)
    grant = store.set_outlook_calendar_write_grant(bot.id, "mscalw_0123456789abcdef01234567",
        "Work events", "calendar-1", "Work")
    gate = Gate()
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate,
                      config=config, workspace=tmp_path)
    tool = build_tools(bot.tools, ctx)["outlook_calendar_create_event"]
    args = {"summary": "Planning", "start": "2026-10-12T10:00:00-07:00",
            "end": "2026-10-12T10:30:00-07:00", "location": "Room 1"}
    result = tool.run(args, ctx)
    name, summary, detail, outward, ask_in_auto = gate.details[0]
    assert (name, outward, ask_in_auto) == ("outlook_calendar_create_event", True, True)
    assert "Planning" in summary and detail["event"]["location"] == "Room 1"
    assert detail["calendar"] == "Work"
    assert "Calendars.ReadWrite" in detail["permission"]
    assert result.ok and result.data["verified"] and len(writes) == 1
    assert tool.effect(args, ctx) == "web"
    assert tool.recorded_arguments(args, ctx)["account_id"] == grant["account_id"]

    gate_on_revoke = Gate(on_decide=lambda: store.remove_outlook_calendar_write_grant(bot.id))
    revoked_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate_on_revoke,
                              config=config, workspace=tmp_path)
    store.set_outlook_calendar_write_grant(bot.id, grant["account_id"], grant["account_label"],
        grant["calendar_id"], grant["calendar_name"])
    before = len(writes)
    result = build_tools(bot.tools, revoked_ctx)["outlook_calendar_create_event"].run(args, revoked_ctx)
    assert not result.ok and "changed while approval was pending" in result.output
    assert len(writes) == before

    store.set_outlook_calendar_write_grant(bot.id, grant["account_id"], grant["account_label"],
        grant["calendar_id"], grant["calendar_name"])
    offline = store.create_bot(Bot(name="offline-event-helper", model="ollama/local", tools=[],
                                   inference_mode=InferenceMode.offline))
    store.set_outlook_calendar_write_grant(offline.id, grant["account_id"], grant["account_label"],
        grant["calendar_id"], grant["calendar_name"])
    offline_ctx = ToolContext(bot=offline, run=run, store=store, policy=PolicyEngine(), gate=Gate(),
                              config=config, workspace=tmp_path)
    assert "outlook_calendar_create_event" not in build_tools(offline.tools, offline_ctx)


def test_calendar_event_tool_preserves_ambiguous_result_as_outcome_unknown(
        tmp_path, store, config, monkeypatch):
    from hutch.models import Bot, Run
    from hutch.runtime.base import RunAborted
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from hutch.tools.outlook_calendar_write import OutlookCalendarCreateEventTool

    class ApprovingGate:
        def decide(self, *args, **kwargs):
            return None

    class AmbiguousBook:
        prepare_event = staticmethod(OutlookCalendarWriteBook.prepare_event)

        def __init__(self, *args):
            pass

        def create_event(self, account_id, calendar_id, **kwargs):
            assert kwargs["before_write"]() is None
            raise OutlookCalendarWriteOutcomeUnknown("check the selected calendar before retrying")

    monkeypatch.setattr("hutch.tools.outlook_calendar_write.OutlookCalendarWriteBook", AmbiguousBook)
    bot = store.create_bot(Bot(name="outlook-event-unknown", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Add the planning meeting")
    store.create_run(run)
    grant = store.set_outlook_calendar_write_grant(bot.id, "mscalw_0123456789abcdef01234567",
        "Work events", "calendar-1", "Work")
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=ApprovingGate(),
                      config=config, workspace=tmp_path, receipt=lambda: None)
    tool = OutlookCalendarCreateEventTool(grant)

    with pytest.raises(RunAborted) as aborted:
        tool.run({"summary": "Planning", "start": "2026-10-12T10:00:00-07:00",
                  "end": "2026-10-12T10:30:00-07:00"}, ctx)
    assert aborted.value.reason == "outcome_unknown"
    assert "check the selected calendar" in aborted.value.detail
