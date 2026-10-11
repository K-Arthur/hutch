from __future__ import annotations

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from types import SimpleNamespace

from hutch.google_calendar import GoogleCalendarBook, GoogleCalendarError, GoogleCalendarOutcomeUnknown, SecretToolStore
from hutch.models import Bot, InferenceMode


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


def seed_account(book: GoogleCalendarBook, account_id: str):
    book._write_accounts({"version": 1, "accounts": {account_id: {
        "id": account_id, "label": "Test calendar", "created_at": "2026-10-09T00:00:00+00:00",
        "scopes": ["https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                   "https://www.googleapis.com/auth/calendar.events.readonly"], "status": "connected"}}})


def test_authorization_uses_pkce_exact_loopback_callback_and_narrow_read_scopes(tmp_path):
    secrets = MemorySecrets()
    book = GoogleCalendarBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              clock=lambda: 1000)
    result = book.start("Personal calendar", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")
    params = parse_qs(urlsplit(result.url).query)

    assert urlsplit(result.url).hostname == "accounts.google.com"
    assert params["client_id"] == ["desktop-client.apps.googleusercontent.com"]
    assert params["redirect_uri"] == ["http://127.0.0.1:18787/api/v1/connections/google-calendar/callback"]
    assert params["response_type"] == ["code"]
    assert params["access_type"] == ["offline"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["https://www.googleapis.com/auth/calendar.calendarlist.readonly "
                                "https://www.googleapis.com/auth/calendar.events.readonly"]
    verifier = book._read_pending(params["state"][0])["verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == [expected]
    assert "verifier" not in result.url
    assert "calendar.events" not in " ".join(params.get("scope", [])) or "readonly" in params["scope"][0]


def test_event_creation_signin_is_explicit_and_keeps_read_only_default(tmp_path):
    callback = "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback"
    book = GoogleCalendarBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=MemorySecrets(),
                              clock=lambda: 1000)
    read = book.start("Personal", callback)
    read_scopes = set(parse_qs(urlsplit(read.url).query)["scope"][0].split())
    assert read_scopes == set(book.oauth_scopes)

    write = book.start("Work writing", callback, allow_event_creation=True)
    write_scopes = set(parse_qs(urlsplit(write.url).query)["scope"][0].split())
    assert set(book.oauth_scopes) <= write_scopes
    assert write_scopes - set(book.oauth_scopes) == {"https://www.googleapis.com/auth/calendar.events.owned"}


def test_finish_persists_write_opt_in_only_for_separately_requested_scope(tmp_path):
    callback = "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback"
    write_scope = "https://www.googleapis.com/auth/calendar.events.owned"
    secrets = MemorySecrets()

    def handler(request):
        assert request.url == "https://oauth2.googleapis.com/token"
        return httpx.Response(200, json={
            "access_token": "short-lived-access-token", "token_type": "Bearer", "expires_in": 3600,
            "refresh_token": "long-lived-refresh-token",
            "scope": " ".join((*GoogleCalendarBook.oauth_scopes, write_scope)),
        })

    book = GoogleCalendarBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    start = book.start("Writing", callback, allow_event_creation=True)
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    account = book.finish(state, "one-time-code", callback)

    assert account["event_creation_opted_in"] is True
    assert GoogleCalendarBook.account_can_create_events(account) is True


def test_event_creation_posts_only_reviewable_fields_to_selected_writable_calendar(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.method == "GET":
            if request.url.path.endswith("/users/me/calendarList"):
                return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                              "accessRole": "owner"}]})
            assert request.url.path.endswith("/calendars/primary/events/event-123")
            assert request.url.params["fields"] == "id,status,summary,start(dateTime),end(dateTime),description,location"
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed", "summary": "Planning review",
                                             "start": {"dateTime": "2026-10-12T10:00:00-07:00"},
                                             "end": {"dateTime": "2026-10-12T10:30:00-07:00"},
                                             "description": "Review the release plan", "location": "Room 4"})
        assert request.method == "POST"
        assert request.url.host == "www.googleapis.com"
        assert request.url.path.endswith("/calendars/primary/events")
        assert "sendUpdates" not in request.url.params
        assert request.headers["Authorization"] == "Bearer access-token"
        body = json.loads(request.content)
        assert set(body) == {"summary", "start", "end", "description", "location"}
        assert "attendees" not in body and "conferenceData" not in body
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                         "summary": body["summary"], "start": body["start"], "end": body["end"]})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    event = book.create_event(account_id, "primary", summary="Planning review",
                              start="2026-10-12T10:00:00-07:00", end="2026-10-12T10:30:00-07:00",
                              description="Review the release plan", location="Room 4")

    assert event == {"id": "event-123", "summary": "Planning review",
                     "start": "2026-10-12T10:00:00-07:00", "end": "2026-10-12T10:30:00-07:00"}
    assert len(requests) == 4


def test_event_creation_never_reports_unverified_or_uncertain_post_as_success(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    writes = []

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "POST":
            writes.append(request)
            return httpx.Response(200, json={"id": "event-123"})
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed", "summary": "Planning review",
                                         "start": {"dateTime": "2026-10-12T10:00:00Z"},
                                         "end": {"dateTime": "2026-10-12T10:30:00Z"}})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    with pytest.raises(GoogleCalendarError, match="details could not be verified exactly"):
        book.create_event(account_id, "primary", summary="Planning review", start="2026-10-12T10:00:00-07:00",
                          end="2026-10-12T10:30:00-07:00")
    assert len(writes) == 1


def test_event_creation_readback_catches_silently_dropped_location(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    writes = []

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "POST":
            writes.append(request)
            return httpx.Response(200, json={"id": "event-123"})
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed", "summary": "Planning review",
                                         "start": {"dateTime": "2026-10-12T10:00:00Z"},
                                         "end": {"dateTime": "2026-10-12T10:30:00Z"}})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    with pytest.raises(GoogleCalendarOutcomeUnknown, match="details could not be verified exactly"):
        book.create_event(account_id, "primary", summary="Planning review", start="2026-10-12T10:00:00Z",
                          end="2026-10-12T10:30:00Z", location="Room 4")
    assert len(writes) == 1


def test_event_creation_does_not_retry_a_write_after_401(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    writes = []

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "POST":
            writes.append(request)
            return httpx.Response(401, json={"error": "unauthorized"})
        pytest.fail("event must not be verified after an authorization error")

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    with pytest.raises(GoogleCalendarError, match="rejected the event creation"):
        book.create_event(account_id, "primary", summary="Planning review", start="2026-10-12T10:00:00Z",
                          end="2026-10-12T10:30:00Z")
    assert len(writes) == 1


@pytest.mark.parametrize(("start", "end", "message"), [
    ("2026-10-12T10:00:00", "2026-10-12T10:30:00Z", "time zone"),
    ("2026-10-12T10:30:00Z", "2026-10-12T10:00:00Z", "end after start"),
    ("2026-10-12T10:00:00Z", "2028-10-12T10:00:00Z", "366 days"),
])
def test_event_creation_rejects_unbounded_or_ambiguous_times_before_provider_call(tmp_path, start, end, message):
    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=MemorySecrets(),
                              transport=httpx.MockTransport(lambda request: pytest.fail("provider should not be called")))
    account_id = "gcal_0123456789abcdef01234567"
    seed_account(book, account_id)
    with pytest.raises(GoogleCalendarError, match=message):
        book.create_event(account_id, "primary", summary="Planning", start=start, end=end)


def test_event_creation_refuses_read_only_scope_and_nonwritable_calendar(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"
    secrets = MemorySecrets()
    secrets.values[account_id] = "refresh-token"
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                       "accessRole": "reader"}]})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    with pytest.raises(GoogleCalendarError, match="event-creation permission"):
        book.create_event(account_id, "primary", summary="Planning", start="2026-10-12T10:00:00Z",
                          end="2026-10-12T10:30:00Z")
    assert len(calls) == 0

    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    with pytest.raises(GoogleCalendarError, match="calendars you own"):
        book.create_event(account_id, "primary", summary="Planning", start="2026-10-12T10:00:00Z",
                          end="2026-10-12T10:30:00Z")
    assert len(calls) == 2  # token refresh plus permission recheck; no event insertion


@pytest.mark.parametrize("redirect", [
    "http://localhost:18787/api/v1/connections/google-calendar/callback",
    "https://127.0.0.1:18787/api/v1/connections/google-calendar/callback",
    "http://127.0.0.1:18787.evil.test/api/v1/connections/google-calendar/callback",
    "http://user@127.0.0.1:18787/api/v1/connections/google-calendar/callback",
])
def test_authorization_rejects_noncanonical_callback(tmp_path, redirect):
    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=MemorySecrets())
    with pytest.raises(GoogleCalendarError, match="127.0.0.1"):
        book.start("Personal", redirect)


def test_finish_consumes_state_once_and_keeps_refresh_token_only_in_secret_store(tmp_path):
    secrets = MemorySecrets()
    requested = []

    def handler(request):
        requested.append(request)
        assert request.url == "https://oauth2.googleapis.com/token"
        fields = parse_qs(request.content.decode())
        assert fields["code"] == ["one-time-code"]
        assert fields["grant_type"] == ["authorization_code"]
        assert len(fields["code_verifier"][0]) >= 43
        assert "refresh_token" not in fields
        return httpx.Response(200, json={
            "access_token": "short-lived-access-token", "token_type": "Bearer", "expires_in": 3600,
            "refresh_token": "long-lived-refresh-token",
            # Google may report a previously granted write scope during this
            # read-only sign-in; only requested scopes count as local opt-in.
            "scope": "https://www.googleapis.com/auth/calendar.calendarlist.readonly "
                     "https://www.googleapis.com/auth/calendar.events.readonly "
                     "https://www.googleapis.com/auth/calendar.events.owned",
        })

    transport = httpx.MockTransport(handler)
    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=transport, clock=lambda: 1000)
    start = book.start("Team calendar", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    account = book.finish(state, "one-time-code", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")

    assert account["label"] == "Team calendar"
    assert account["id"].startswith("gcal_")
    assert account["event_creation_opted_in"] is False
    assert GoogleCalendarBook.account_can_create_events(account) is False
    assert secrets.values[account["id"]] == "long-lived-refresh-token"
    assert "long-lived-refresh-token" not in (tmp_path / "google-calendar" / "accounts.json").read_text()
    assert "short-lived-access-token" not in (tmp_path / "google-calendar" / "accounts.json").read_text()
    with pytest.raises(GoogleCalendarError, match="already used"):
        book.finish(state, "other-code", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")


def test_calendar_reads_refresh_then_use_only_google_api_host_and_bound_event_fields(tmp_path):
    secrets = MemorySecrets()
    secrets.values["gcal_0123456789abcdef01234567"] = "refresh-token"
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.host == "www.googleapis.com" and request.url.path.endswith("/users/me/calendarList"):
            assert request.headers["authorization"] == "Bearer access-token"
            assert request.url.params["fields"] == "items(id,summary,primary,accessRole),nextPageToken"
            return httpx.Response(200, json={"items": [
                {"id": "primary", "summary": "Primary", "primary": True, "accessRole": "owner"},
                {"id": "team@example.com", "summary": "Team", "accessRole": "reader"},
            ]})
        if request.url.host == "www.googleapis.com" and "/events" in request.url.path:
            assert request.headers["authorization"] == "Bearer access-token"
            assert request.url.params["maxResults"] == "10"
            assert request.url.params["fields"] == "items(summary,start,end,location),nextPageToken"
            assert request.url.params["singleEvents"] == "true"
            assert request.url.params["timeMin"] == "2026-10-09T00:00:00Z"
            return httpx.Response(200, json={"items": [
                {"summary": "Planning", "start": {"dateTime": "2026-10-09T12:00:00Z"},
                 "end": {"dateTime": "2026-10-09T12:30:00Z"}, "location": "Room 4",
                 "description": "do not return this private free-form content"},
            ]})
        raise AssertionError(f"unexpected host/path {request.url}")

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, "gcal_0123456789abcdef01234567")
    calendars = book.list_calendars("gcal_0123456789abcdef01234567")
    assert [c["id"] for c in calendars] == ["primary", "team@example.com"]
    events = book.list_events("gcal_0123456789abcdef01234567", "primary",
                              "2026-10-09T00:00:00Z", "2026-10-10T00:00:00Z", limit=10)
    assert events == [{"summary": "Planning", "start": "2026-10-09T12:00:00Z",
                       "end": "2026-10-09T12:30:00Z", "location": "Room 4"}]
    assert all(r.url.host in {"oauth2.googleapis.com", "www.googleapis.com"} for r in seen)


def test_calendar_read_refreshes_once_after_expired_access_token(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    sequence: list[tuple[str, str]] = []
    refresh_count = 0

    def handler(request):
        nonlocal refresh_count
        if request.url.host == "oauth2.googleapis.com":
            refresh_count += 1
            token = "expired-token" if refresh_count == 1 else "replacement-token"
            sequence.append(("refresh", token))
            return httpx.Response(200, json={"access_token": token, "token_type": "Bearer",
                                             "expires_in": 3600})
        token = request.headers["authorization"].removeprefix("Bearer ")
        sequence.append(("calendar", token))
        if token == "expired-token":
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(200, json={"items": []})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    result = book.list_events(account_id, "primary", "2026-10-09T00:00:00Z", "2026-10-10T00:00:00Z")

    assert result == []
    assert sequence == [("refresh", "expired-token"), ("calendar", "expired-token"),
                        ("refresh", "replacement-token"), ("calendar", "replacement-token")]


def test_calendar_read_does_not_retry_permission_denial(tmp_path):
    secrets = MemorySecrets()
    account_id = "gcal_0123456789abcdef01234567"
    secrets.values[account_id] = "refresh-token"
    refresh_count = 0
    calendar_count = 0

    def handler(request):
        nonlocal refresh_count, calendar_count
        if request.url.host == "oauth2.googleapis.com":
            refresh_count += 1
            return httpx.Response(200, json={"access_token": f"access-{refresh_count}",
                                             "token_type": "Bearer", "expires_in": 3600})
        calendar_count += 1
        return httpx.Response(403, json={"error": "insufficientPermissions"})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    with pytest.raises(GoogleCalendarError, match="reconnect the calendar and check its permissions"):
        book.list_calendars(account_id)

    assert refresh_count == 1
    assert calendar_count == 1


def test_calendar_event_queries_are_bounded_and_ids_are_encoded(tmp_path):
    secrets = MemorySecrets()
    secrets.values["gcal_0123456789abcdef01234567"] = "refresh-token"
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        return httpx.Response(200, json={"items": []})

    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, "gcal_0123456789abcdef01234567")
    with pytest.raises(GoogleCalendarError, match="limit"):
        book.list_events("gcal_0123456789abcdef01234567", "primary", "2026-10-09T00:00:00Z",
                         "2026-10-10T00:00:00Z", limit=101)
    with pytest.raises(GoogleCalendarError, match="time range"):
        book.list_events("gcal_0123456789abcdef01234567", "primary", "2026-10-10T00:00:00Z",
                         "2026-10-09T00:00:00Z")
    with pytest.raises(GoogleCalendarError, match="query"):
        book.list_events("gcal_0123456789abcdef01234567", "primary", "2026-10-09T00:00:00Z",
                         "2026-10-10T00:00:00Z", query="x" * 300)
    book.list_events("gcal_0123456789abcdef01234567", "a/b?x=1", "2026-10-09T00:00:00Z",
                     "2026-10-10T00:00:00Z")
    assert "/calendars/a%2Fb%3Fx%3D1/events" in str(requests[-1].url)
    assert "a%2Fb%3Fx%3D1" in str(requests[-1].url)


def test_disconnect_deletes_provider_grant_and_local_metadata(tmp_path):
    secrets = MemorySecrets()
    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                                  "access_token": "a", "token_type": "Bearer", "expires_in": 3600,
                                  "refresh_token": "r", "scope": "https://www.googleapis.com/auth/calendar.calendarlist.readonly "
                                                               "https://www.googleapis.com/auth/calendar.events.readonly"})))
    start = book.start("Personal", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")
    state = parse_qs(urlsplit(start.url).query)["state"][0]
    account = book.finish(state, "code", "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback")
    assert book.disconnect(account["id"])
    assert account["id"] not in secrets.values
    assert book.accounts() == []
    assert not book.disconnect(account["id"])["removed"]


def test_secret_tool_receives_refresh_token_over_stdin_never_as_argument(monkeypatch):
    calls = []
    monkeypatch.setattr("hutch.google_calendar._SECRET_PROBE_RESULT", None)

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr("hutch.google_calendar.shutil.which", lambda _: "/usr/bin/secret-tool")
    monkeypatch.setattr("hutch.google_calendar.subprocess.run", run)
    store = SecretToolStore()
    store.put("gcal_0123456789abcdef01234567", "refresh-token-secret")
    assert calls[0][0][1:3] == ["lookup", "service"]
    assert "refresh-token-secret" not in " ".join(calls[1][0])
    assert calls[1][1]["input"] == "refresh-token-secret\n"
    assert calls[1][1]["capture_output"] is True
    assert store.get("gcal_0123456789abcdef01234567") is None


def test_bot_calendar_grant_is_single_calendar_revocable_and_available_only_online(store):
    from hutch.tools import build_tools

    bot = store.create_bot(Bot(name="calendar-reader", model="mock/demo", tools=[]))
    grant = store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "primary", "Personal")
    assert grant and grant["calendar_id"] == "primary"
    context = SimpleNamespace(bot=bot, run=SimpleNamespace(conversation_id=""), store=store)
    context.store.get_bot(bot.id)
    online = build_tools([], context)
    assert "google_calendar_events" in online
    assert "Personal" in online["google_calendar_events"].description

    store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "team@example.com", "Team")
    assert store.google_calendar_grant(bot.id)["calendar_id"] == "team@example.com"
    offline_bot = bot.model_copy(update={"inference_mode": InferenceMode.offline})
    offline = build_tools([], SimpleNamespace(bot=offline_bot, run=SimpleNamespace(conversation_id=""), store=store))
    assert "google_calendar_events" not in offline
    assert store.remove_google_calendar_grant(bot.id) is True
    assert store.google_calendar_grant(bot.id) is None


def test_calendar_event_tool_is_installed_only_for_a_write_enabled_bot_calendar(store):
    from hutch.tools import build_tools

    bot = store.create_bot(Bot(name="calendar-writer", model="mock/demo", tools=[]))
    read = store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "primary", "Personal")
    context = SimpleNamespace(bot=bot, run=SimpleNamespace(conversation_id=""), store=store)
    assert "google_calendar_events" in build_tools([], context)
    assert "google_calendar_create_event" not in build_tools([], context)
    assert read["allow_event_creation"] is False

    grant = store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "primary", "Personal",
                                            allow_event_creation=True)
    assert grant["allow_event_creation"] is True
    assert "google_calendar_create_event" in build_tools([], context)
    offline_bot = bot.model_copy(update={"inference_mode": InferenceMode.offline})
    offline = build_tools([], SimpleNamespace(bot=offline_bot, run=SimpleNamespace(conversation_id=""), store=store))
    assert "google_calendar_create_event" not in offline


def test_calendar_event_tool_asks_exact_outward_approval_and_fences_before_write(store, monkeypatch):
    from hutch.tools.google_calendar import GoogleCalendarCreateEventTool

    bot = store.create_bot(Bot(name="calendar-writer", model="mock/demo", tools=[]))
    grant = store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "primary", "Personal",
                                            allow_event_creation=True)
    tool = GoogleCalendarCreateEventTool(grant)
    approvals, effects, writes = [], [], []

    class Gate:
        def decide(self, *args, **kwargs):
            approvals.append((args, kwargs))

    class FakeBook:
        prepare_event = staticmethod(GoogleCalendarBook.prepare_event)

        def __init__(self, *args):
            pass

        def create_event(self, account_id, calendar_id, *, before_write=None, **event):
            assert before_write() is None
            writes.append((account_id, calendar_id, event))
            return {"id": "event-123", "summary": event["summary"], "start": event["start"], "end": event["end"]}

    monkeypatch.setattr("hutch.tools.google_calendar.GoogleCalendarBook", FakeBook)
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    ctx = SimpleNamespace(bot=bot, store=store, config=SimpleNamespace(state_dir="state"), gate=Gate(), dry_run=False,
                          begin_effect=lambda: effects.append("fenced") or None)
    arguments = {"summary": "  Planning review  ", "start": "2026-10-12T10:00:00-07:00",
                 "end": "2026-10-12T10:30:00-07:00", "location": " Room 4 ",
                 "description": " Review the release plan "}
    prepared = {"summary": "Planning review", "start": "2026-10-12T10:00:00-07:00",
                "end": "2026-10-12T10:30:00-07:00", "location": "Room 4",
                "description": "Review the release plan"}
    result = tool.run(arguments, ctx)

    assert result.ok and result.data["created"] is True
    assert approvals[0][1]["outward"] is True and approvals[0][1]["ask_in_auto"] is True
    assert approvals[0][0][2]["account_id"] == grant["account_id"]
    assert approvals[0][0][2]["calendar_id"] == "primary"
    assert approvals[0][0][2]["event"] == prepared
    assert effects == ["fenced"]
    assert writes == [(grant["account_id"], "primary", prepared)]
    assert tool.recorded_arguments(arguments, ctx) == {**prepared, "account_id": grant["account_id"],
        "calendar_id": "primary", "calendar_name": "Personal", "allow_event_creation": True}


def test_calendar_tool_rechecks_current_grant_and_returns_only_untrusted_read_data(store, monkeypatch):
    from hutch.tools.google_calendar import GoogleCalendarEventsTool

    bot = store.create_bot(Bot(name="calendar-tool", model="mock/demo", tools=[]))
    grant = store.set_google_calendar_grant(bot.id, "gcal_0123456789abcdef01234567", "primary", "Personal")
    tool = GoogleCalendarEventsTool(grant)
    calls = []

    class FakeBook:
        def __init__(self, state_dir, client_id):
            calls.append((state_dir, client_id))

        def list_events(self, account_id, calendar_id, time_min, time_max, *, query, limit):
            calls.append((account_id, calendar_id, time_min, time_max, query, limit))
            return [{"summary": "Planning", "start": "2026-10-09T12:00:00Z", "end": "2026-10-09T12:30:00Z",
                     "location": "Room 4"}]

    monkeypatch.setattr("hutch.tools.google_calendar.GoogleCalendarBook", FakeBook)
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    result = tool.run({"time_min": "2026-10-09T00:00:00Z", "time_max": "2026-10-10T00:00:00Z"},
                      SimpleNamespace(bot=bot, store=store, config=SimpleNamespace(state_dir="state")))
    assert result.ok and result.data == {"count": 1, "calendar_id": "primary", "read_only": True, "untrusted": True}
    assert "<calendar_events_untrusted>" in result.output and "Planning" in result.output
    assert calls[-1][-1] == 25
    store.remove_google_calendar_grant(bot.id)
    denied = tool.run({"time_min": "x", "time_max": "y"},
                      SimpleNamespace(bot=bot, store=store, config=SimpleNamespace(state_dir="state")))
    assert not denied.ok and "access was removed" in denied.output


# --- relative reminder overrides and existing-event updates (synthesis lane) ---

def _writable_book(tmp_path, handler, account_id):
    secrets = MemorySecrets()
    secrets.values[account_id] = "refresh-token"
    book = GoogleCalendarBook(tmp_path, "client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1000)
    seed_account(book, account_id)
    account = book._read_accounts()["accounts"][account_id]
    account["scopes"].append("https://www.googleapis.com/auth/calendar.events.owned")
    account["event_creation_opted_in"] = True
    book._write_accounts({"version": 1, "accounts": {account_id: account}})
    return book


def _base_handler(requests, *, verify_json):
    def handler(request):
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.method == "GET" and request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "PATCH":
            requests[-1] = request
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed"})
        if request.method == "GET":
            return httpx.Response(200, json=verify_json(request))
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed"})

    return handler


def test_event_creation_with_relative_reminders_is_posted_and_verified(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"
    requests = []

    def verify(request):
        assert request.url.params["fields"] == ("id,status,summary,start(dateTime),end(dateTime),"
                                                "description,location,reminders")
        return {"id": "event-123", "status": "confirmed", "summary": "Planning review",
                "start": {"dateTime": "2026-10-12T10:00:00-07:00"},
                "end": {"dateTime": "2026-10-12T10:30:00-07:00"}, "description": "", "location": "",
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}}

    handler = _base_handler(requests, verify_json=verify)
    book = _writable_book(tmp_path, handler, account_id)
    original_post = handler

    def wrapped(request):
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["reminders"] == {"useDefault": False,
                                        "overrides": [{"method": "popup", "minutes": 10}]}
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                             "summary": body["summary"], "start": body["start"],
                                             "end": body["end"]})
        return original_post(request)

    book._transport = httpx.MockTransport(wrapped)
    event = book.create_event(account_id, "primary", summary="Planning review",
                              start="2026-10-12T10:00:00-07:00", end="2026-10-12T10:30:00-07:00",
                              reminders={"popup": 10})
    assert event["id"] == "event-123"


def test_reminders_are_refused_before_any_provider_call(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    book = _writable_book(tmp_path, handler, account_id)
    book._transport = httpx.MockTransport(handler)
    for bad in ({"popup": 90_000}, {"popup": -1}, {"sms": 5}, {"popup": True}, {}):
        with pytest.raises(GoogleCalendarError):
            book.create_event(account_id, "primary", summary="x",
                              start="2026-10-12T10:00:00-07:00", end="2026-10-12T10:30:00-07:00",
                              reminders=bad)
    with pytest.raises(GoogleCalendarError):
        book.update_event_reminders(account_id, "primary", "event-123", overrides={"popup": 90_000})
    assert calls == [], "invalid reminder input must not reach Google"


def test_update_event_reminders_uses_if_match_and_verifies_readback(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"
    seen = {"patch": None}

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "GET" and request.url.params.get("fields") == "id,status,etag,summary":
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                             "etag": "etag-1", "summary": "Planning review"})
        if request.method == "PATCH":
            seen["patch"] = request
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed"})
        assert request.url.params["fields"] == "id,status,reminders"
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                         "reminders": {"useDefault": False,
                                                       "overrides": [{"method": "popup", "minutes": 15}]}})

    book = _writable_book(tmp_path, handler, account_id)
    book._transport = httpx.MockTransport(handler)
    result = book.update_event_reminders(account_id, "primary", "event-123",
                                         overrides={"popup": 15})
    assert seen["patch"].headers.get("If-Match") == "etag-1"
    body = json.loads(seen["patch"].content)
    assert body == {"reminders": {"useDefault": False,
                                  "overrides": [{"method": "popup", "minutes": 15}]}}
    assert result == {"event_id": "event-123",
                      "reminders": {"useDefault": False,
                                    "overrides": [{"method": "popup", "minutes": 15}]}}


def test_update_event_reminders_can_reset_to_default(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"
    patches = []

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "PATCH":
            patches.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "event-123"})
        if request.url.params.get("fields") == "id,status,etag,summary":
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                             "etag": "e1", "summary": "x"})
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                         "reminders": {"useDefault": True, "overrides": []}})

    book = _writable_book(tmp_path, handler, account_id)
    book._transport = httpx.MockTransport(handler)
    result = book.update_event_reminders(account_id, "primary", "event-123", overrides=None)
    assert patches == [{"reminders": {"useDefault": True, "overrides": []}}]
    assert result["reminders"] == {"useDefault": True, "overrides": []}


def test_update_event_reminders_mismatch_is_uncertain_not_success(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "event-123"})
        if request.url.params.get("fields") == "id,status,etag,summary":
            return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                             "etag": "e1", "summary": "x"})
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                         "reminders": {"useDefault": False,
                                                       "overrides": [{"method": "popup", "minutes": 30}]}})

    book = _writable_book(tmp_path, handler, account_id)
    book._transport = httpx.MockTransport(handler)
    with pytest.raises(GoogleCalendarOutcomeUnknown):
        book.update_event_reminders(account_id, "primary", "event-123", overrides={"popup": 15})


def test_update_event_reminders_conflict_is_a_clean_refusal(tmp_path):
    account_id = "gcal_0123456789abcdef01234567"

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "token_type": "Bearer",
                                             "expires_in": 3600})
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "summary": "Personal",
                                                          "accessRole": "owner"}]})
        if request.method == "PATCH":
            return httpx.Response(412, json={"error": {"message": "conditionNotMet"}})
        return httpx.Response(200, json={"id": "event-123", "status": "confirmed",
                                         "etag": "stale", "summary": "x"})

    book = _writable_book(tmp_path, handler, account_id)
    book._transport = httpx.MockTransport(handler)
    with pytest.raises(GoogleCalendarError) as exc:
        book.update_event_reminders(account_id, "primary", "event-123", overrides={"popup": 15})
    assert "changed since it was reviewed" in str(exc.value)
