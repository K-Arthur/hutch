from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.models import Bot, InferenceMode, Run
from hutch.outlook_calendar import (AUTH_URL, CALENDAR_SCOPE, TOKEN_URL,
                                    OutlookCalendarBook, OutlookCalendarError)
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext


class MemorySecrets:
    def __init__(self):
        self.values: dict[str, str] = {}

    def available(self):
        return True

    def put(self, account_id: str, value: str):
        self.values[account_id] = value

    def get(self, account_id: str):
        return self.values.get(account_id)

    def delete(self, account_id: str):
        self.values.pop(account_id, None)


def seed_account(book: OutlookCalendarBook, account_id="mscal_0123456789abcdef01234567"):
    book._write_accounts({"version": 1, "accounts": {account_id: {
        "id": account_id, "label": "Work calendar", "created_at": "2026-10-09T00:00:00+00:00",
        "scopes": [CALENDAR_SCOPE], "status": "connected"}}})
    return account_id


def test_authorization_uses_pkce_localhost_loopback_and_only_read_basic_scope(tmp_path):
    secrets = MemorySecrets()
    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=secrets, clock=lambda: 1000)
    callback = "http://localhost:18787/api/v1/connections/outlook-calendar/callback"
    result = book.start(" Work   calendar ", callback)
    params = parse_qs(urlsplit(result.url).query)

    assert urlsplit(result.url).geturl().startswith(AUTH_URL + "?")
    assert params["client_id"] == ["fixture-public-client"]
    assert params["redirect_uri"] == [callback]
    assert params["response_type"] == ["code"]
    assert params["response_mode"] == ["query"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["Calendars.ReadBasic offline_access"]
    verifier = book._read_pending(params["state"][0])["verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == [expected]
    assert "client_secret" not in params and "verifier" not in result.url
    assert "Mail." not in params["scope"][0] and "Calendars.ReadWrite" not in params["scope"][0]


@pytest.mark.parametrize("callback", [
    "http://127.0.0.1:18787/api/v1/connections/outlook-calendar/callback",
    "https://localhost:18787/api/v1/connections/outlook-calendar/callback",
    "http://localhost.evil.test:18787/api/v1/connections/outlook-calendar/callback",
    "http://user@localhost:18787/api/v1/connections/outlook-calendar/callback",
    "http://localhost:18787/api/v1/connections/outlook-calendar/callback?next=https://evil.test",
])
def test_authorization_rejects_noncanonical_callback(tmp_path, callback):
    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=MemorySecrets())
    with pytest.raises(OutlookCalendarError, match="localhost callback"):
        book.start("Work", callback)


def test_callback_uri_requires_local_peer_and_returns_registered_localhost(tmp_path):
    request = SimpleNamespace(
        headers={"host": "127.0.0.1:18787"},
        scope={"server": ("127.0.0.1", 18787)},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(scheme="http"),
    )
    assert OutlookCalendarBook.callback_uri(request) == (
        "http://localhost:18787/api/v1/connections/outlook-calendar/callback")
    request.client.host = "192.0.2.10"
    with pytest.raises(OutlookCalendarError, match="loopback"):
        OutlookCalendarBook.callback_uri(request)


def test_finish_consumes_state_once_and_keeps_refresh_token_out_of_local_metadata(tmp_path):
    secrets = MemorySecrets()
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url == TOKEN_URL
        fields = parse_qs(request.content.decode())
        assert fields["code"] == ["one-time-code"]
        assert fields["grant_type"] == ["authorization_code"]
        assert len(fields["code_verifier"][0]) >= 43
        assert "client_secret" not in fields and "refresh_token" not in fields
        return httpx.Response(200, json={
            "access_token": "short-lived-access-token", "token_type": "Bearer", "expires_in": 3600,
            "refresh_token": "long-lived-refresh-token", "scope": "Calendars.ReadBasic offline_access",
        })

    callback = "http://localhost:18787/api/v1/connections/outlook-calendar/callback"
    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(handler), clock=lambda: 1000)
    start = book.start("Work calendar", callback)
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    account = book.finish(state, "one-time-code", callback)

    assert account["label"] == "Work calendar" and account["id"].startswith("mscal_")
    assert account["scopes"] == ["Calendars.ReadBasic"]
    assert secrets.values[account["id"]] == "long-lived-refresh-token"
    metadata = (tmp_path / "outlook-calendar" / "accounts.json").read_text()
    assert "long-lived-refresh-token" not in metadata and "short-lived-access-token" not in metadata
    assert len(requests) == 1
    with pytest.raises(OutlookCalendarError, match="already used"):
        book.finish(state, "other-code", callback)


def test_graph_calendar_views_are_bounded_and_request_only_basic_event_fields(tmp_path):
    secrets = MemorySecrets()
    account_id = "mscal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    seen = []

    def handler(request):
        seen.append(request)
        if request.url == TOKEN_URL:
            assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
            return httpx.Response(200, json={"access_token": "graph-access", "token_type": "Bearer",
                                             "expires_in": 3600})
        assert request.url.host == "graph.microsoft.com"
        assert request.headers["authorization"] == "Bearer graph-access"
        assert request.headers["prefer"] == 'outlook.timezone="UTC"'
        if request.url.path == "/v1.0/me/calendars":
            assert request.url.params["$select"] == "id,name,isDefaultCalendar"
            return httpx.Response(200, json={"value": [
                {"id": "primary", "name": "Primary", "isDefaultCalendar": True},
                {"id": "work", "name": "Work", "isDefaultCalendar": False},
            ]})
        if request.url.path.endswith("/calendarView"):
            assert request.url.params["$select"] == "subject,start,end,location"
            assert request.url.params["$top"] == "12"
            assert request.url.params["startDateTime"] == "2026-10-09T00:00:00Z"
            return httpx.Response(200, json={"value": [{
                "subject": "Planning <script>", "start": {"dateTime": "2026-10-09T12:00:00.0000000", "timeZone": "UTC"},
                "end": {"dateTime": "2026-10-09T12:30:00.0000000", "timeZone": "UTC"},
                "location": {"displayName": "Room 4"},
                "body": {"content": "private body must not be returned"}, "attendees": ["private@example.test"],
            }]})
        raise AssertionError(f"unexpected Graph endpoint: {request.url}")

    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    calendars = book.list_calendars(account_id)
    events = book.list_events(account_id, "primary", "2026-10-09T00:00:00Z", "2026-10-10T00:00:00Z", limit=12)

    assert calendars == [{"id": "primary", "name": "Primary", "primary": True},
                         {"id": "work", "name": "Work", "primary": False}]
    assert events == [{"summary": "Planning <script>", "start": "2026-10-09T12:00:00.0000000 UTC",
                       "end": "2026-10-09T12:30:00.0000000 UTC", "location": "Room 4"}]
    assert all(request.url.host in {"login.microsoftonline.com", "graph.microsoft.com"} for request in seen)
    serialized = str(events)
    assert "body" not in serialized and "private body" not in serialized and "attendees" not in serialized


def test_graph_continuation_link_is_validated_before_any_second_request(tmp_path):
    secrets = MemorySecrets()
    account_id = "mscal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "graph-access", "token_type": "Bearer", "expires_in": 3600})
        return httpx.Response(200, json={"value": [], "@odata.nextLink": "https://attacker.invalid/v1.0/me/calendars?skip=x"})

    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    with pytest.raises(OutlookCalendarError, match="outside the verified"):
        book.list_calendars(account_id)
    assert "attacker.invalid" not in hosts


@pytest.mark.parametrize("limit", [0, 26, True])
def test_outlook_calendar_event_limit_is_rejected_before_network(tmp_path, limit):
    account_id = "mscal_0123456789abcdef01234567"
    book = OutlookCalendarBook(tmp_path, "fixture-public-client", secrets_store=MemorySecrets(),
                               transport=httpx.MockTransport(lambda request: pytest.fail("must not call Graph")))
    seed_account(book, account_id)
    with pytest.raises(OutlookCalendarError, match="between 1 and 25"):
        book.list_events(account_id, "primary", "2026-10-09T00:00:00Z", "2026-10-10T00:00:00Z", limit=limit)


def test_tool_escapes_provider_content_and_reads_only_current_bot_grant(monkeypatch, tmp_path, store, config):
    from hutch.tools.outlook_calendar import OutlookCalendarEventsTool

    bot = store.create_bot(Bot(name="outlook-tool", model="mock/demo", tools=[]))
    grant = store.set_outlook_calendar_grant(bot.id, "mscal_0123456789abcdef01234567", "work", "<Team>")
    assert grant
    run = Run(bot_id=bot.id, prompt="Read this calendar")
    store.create_run(run)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=SimpleNamespace(), config=config,
                      workspace=tmp_path)
    captured = {}

    class FixtureBook:
        def __init__(self, state_dir, client_id):
            assert client_id == "fixture-client"

        @staticmethod
        def list_events(account_id, calendar_id, time_min, time_max, *, limit):
            captured.update(account_id=account_id, calendar_id=calendar_id, limit=limit)
            return [{"summary": "<script>alert(1)</script>", "start": "2026-10-09T12:00 UTC",
                     "end": "2026-10-09T12:30 UTC", "location": "Room & A"}]

    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-client")
    monkeypatch.setattr("hutch.tools.outlook_calendar.OutlookCalendarBook", FixtureBook)
    tool = OutlookCalendarEventsTool(grant)
    result = tool.run({"time_min": "2026-10-09T00:00:00Z", "time_max": "2026-10-10T00:00:00Z"}, ctx)
    assert result.ok and result.data["untrusted"] and result.data["read_only"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.output
    assert "<script>" not in result.output
    assert captured["account_id"] == grant["account_id"] and captured["calendar_id"] == "work" and captured["limit"] == 25
    assert "access_token" not in tool.recorded_arguments({"time_min": "a", "time_max": "b"}, ctx)

    assert store.remove_outlook_calendar_grant(bot.id)
    result = tool.run({"time_min": "2026-10-09T00:00:00Z", "time_max": "2026-10-10T00:00:00Z"}, ctx)
    assert not result.ok and "removed or changed" in result.output


def test_calendar_tool_is_added_from_explicit_grant_and_removed_for_strict_offline(tmp_path, store, config):
    coordinator = store.create_bot(Bot(name="outlook-coordinator", model="mock/demo", tools=[]))
    store.set_outlook_calendar_grant(coordinator.id, "mscal_0123456789abcdef01234567", "work", "Work")
    run = Run(bot_id=coordinator.id, prompt="Check meetings")
    store.create_run(run)
    ctx = ToolContext(bot=coordinator, run=run, store=store, policy=PolicyEngine(), gate=SimpleNamespace(),
                      config=config, workspace=tmp_path)
    assert "outlook_calendar_events" in build_tools(coordinator.tools, ctx)

    offline = store.create_bot(Bot(name="outlook-offline", model="ollama/local", tools=[],
                                   inference_mode=InferenceMode.offline))
    store.set_outlook_calendar_grant(offline.id, "mscal_0123456789abcdef01234567", "work", "Work")
    offline_run = Run(bot_id=offline.id, prompt="Check meetings")
    store.create_run(offline_run)
    offline_ctx = ToolContext(bot=offline, run=offline_run, store=store, policy=PolicyEngine(),
                              gate=SimpleNamespace(), config=config, workspace=tmp_path)
    assert "outlook_calendar_events" not in build_tools(offline.tools, offline_ctx)
