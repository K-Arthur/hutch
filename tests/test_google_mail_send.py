from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.google_calendar import GoogleCalendarError
from hutch.google_mail_send import (
    GOOGLE_MAIL_SEND_CALLBACK_PATH,
    GOOGLE_MAIL_SEND_SCOPE,
    GoogleMailSendBook,
    GoogleMailSendOutcomeUnknown,
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


def seed_account(book, scopes=None, account_id="gmail_send_0123456789abcdef01234567"):
    scopes = scopes or [GOOGLE_MAIL_SEND_SCOPE]
    book._write_accounts({"version": 1, "accounts": {account_id: {
        "id": account_id, "label": "Work sender", "from_address": "owner@example.test",
        "created_at": "2026-10-10T00:00:00+00:00", "scopes": scopes, "status": "connected"}}})
    book.secrets.put(account_id, "refresh-token")
    return account_id


def callback_uri():
    return f"http://127.0.0.1:18787{GOOGLE_MAIL_SEND_CALLBACK_PATH}"


def test_send_sign_in_uses_only_sensitive_send_scope_and_separate_storage(tmp_path):
    secrets = MemorySecrets()

    def handler(request):
        assert request.url == "https://oauth2.googleapis.com/token"
        fields = parse_qs(request.content.decode())
        assert fields["code"] == ["one-time-code"]
        return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                         "expires_in": 3600, "token_type": "Bearer",
                                         "scope": GOOGLE_MAIL_SEND_SCOPE})

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    started = book.start("Work sender", callback_uri(), "owner@example.test")
    query = parse_qs(urlsplit(started.url).query)
    assert query["scope"] == [GOOGLE_MAIL_SEND_SCOPE]
    assert query["redirect_uri"] == [callback_uri()]
    account = book.finish(started.state, "one-time-code", callback_uri())
    assert account["id"].startswith("gmail_send_")
    assert account["scopes"] == [GOOGLE_MAIL_SEND_SCOPE]
    assert account["from_address"] == "owner@example.test"
    assert book.root.name == "google-mail-send"
    assert secrets.values[account["id"]] == "refresh-token"


def test_send_sign_in_rejects_any_additional_gmail_scope(tmp_path):
    secrets = MemorySecrets()

    def handler(request):
        return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                         "expires_in": 3600, "token_type": "Bearer",
                                         "scope": f"{GOOGLE_MAIL_SEND_SCOPE} https://www.googleapis.com/auth/gmail.readonly"})

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    started = book.start("Work sender", callback_uri(), "owner@example.test")
    with pytest.raises(GoogleCalendarError, match="did not grant the requested Gmail sending scopes"):
        book.finish(started.state, "one-time-code", callback_uri())
    assert book.accounts() == []
    assert secrets.values == {}


def test_send_submits_one_bounded_plain_text_mime_message_after_effect_intent(tmp_path):
    requests = []
    secrets = MemorySecrets()

    def handler(request):
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        assert request.url.host == "gmail.googleapis.com"
        assert request.url.path == "/gmail/v1/users/me/messages/send"
        assert request.url.params["fields"] == "id,threadId"
        return httpx.Response(200, json={"id": "sent-message", "threadId": "sent-thread"})

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account_id = seed_account(book)
    order = []
    result = book.send_message(account_id, ["person@example.test"], "A note", "Hello from Hutch.",
                               before_write=lambda: order.append("effect"))
    send_requests = [request for request in requests if request.url.path.endswith("/messages/send")]
    assert len(send_requests) == 1
    request = send_requests[0]
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer access-token"
    encoded = request.read()
    import json
    raw = json.loads(encoded)["raw"]
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert str(message["From"]) == "owner@example.test"
    assert str(message["To"]) == "person@example.test"
    assert str(message["Subject"]) == "A note"
    assert message.get_content().strip() == "Hello from Hutch."
    assert message["Cc"] is None and message["Bcc"] is None
    assert result == {"accepted": True, "delivery_verified": False,
                      "message_id": "sent-message", "thread_id": "sent-thread"}
    assert order == ["effect"]


@pytest.mark.parametrize("recipients,subject,body", [
    (["not an address"], "Hello", "Body"), (["a@example.test\r\nBcc: b@example.test"], "Hello", "Body"),
    (["a@example.test", "a@example.test"], "Hello", "Body"), ([], "Hello", "Body"),
    (["a@example.test"], "\r\nBcc: b@example.test", "Body"), (["a@example.test"], "", "Body"),
    (["a@example.test"], "Hello", "x" * 12001), (["a@example.test"], "Hello", "bad\x00body"),
    (["a@example.test"], "\ud800", "Body"),
])
def test_send_rejects_invalid_content_before_token_refresh_or_write(tmp_path, recipients, subject, body):
    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=MemorySecrets())
    account_id = seed_account(book)
    with pytest.raises(GoogleCalendarError):
        book.send_message(account_id, recipients, subject, body, before_write=lambda: None)


def test_send_marks_transport_ambiguity_unknown_and_never_retries(tmp_path):
    calls = []
    secrets = MemorySecrets()

    def handler(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        raise httpx.ConnectError("fixture disconnect after request dispatch", request=request)

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=secrets,
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account_id = seed_account(book)
    with pytest.raises(GoogleMailSendOutcomeUnknown, match="Check Gmail Sent before retrying"):
        book.send_message(account_id, ["person@example.test"], "A note", "Body", before_write=lambda: None)
    assert len([request for request in calls if request.url.path.endswith("/messages/send")]) == 1


def test_send_marks_gateway_timeout_unknown_and_never_retries(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        return httpx.Response(408)

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=MemorySecrets(),
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account_id = seed_account(book)
    with pytest.raises(GoogleMailSendOutcomeUnknown, match="Check Gmail Sent before retrying"):
        book.send_message(account_id, ["person@example.test"], "A note", "Body", before_write=lambda: None)
    assert len([request for request in calls if request.url.path.endswith("/messages/send")]) == 1


def test_send_refuses_read_only_account_and_aborted_effect_without_write(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                         "token_type": "Bearer"})

    book = GoogleMailSendBook(tmp_path, "desktop-client.apps.googleusercontent.com", secrets_store=MemorySecrets(),
                              transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account_id = seed_account(book, ["https://www.googleapis.com/auth/gmail.readonly"])
    with pytest.raises(GoogleCalendarError, match="no gmail.send grant"):
        book.send_message(account_id, ["person@example.test"], "A note", "Body", before_write=lambda: None)
    assert not [request for request in calls if request.url.path.endswith("/messages/send")]

    account_id = seed_account(book, [GOOGLE_MAIL_SEND_SCOPE, "https://www.googleapis.com/auth/gmail.readonly"])
    with pytest.raises(GoogleCalendarError, match="no gmail.send grant"):
        book.send_message(account_id, ["person@example.test"], "A note", "Body", before_write=lambda: None)
    assert not [request for request in calls if request.url.path.endswith("/messages/send")]

    account_id = seed_account(book)
    with pytest.raises(GoogleCalendarError, match="revoked"):
        book.send_message(account_id, ["person@example.test"], "A note", "Body",
                           before_write=lambda: "grant was revoked")
    assert not [request for request in calls if request.url.path.endswith("/messages/send")]


def test_send_tool_requires_exact_approval_rechecks_grant_and_records_sender(tmp_path, store, config, monkeypatch):
    from hutch.approvals import DeniedError
    from hutch.models import Bot, InferenceMode, Run
    from hutch.safety import PolicyEngine
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.tools.google_mail_send import GoogleMailSendTool

    class Gate:
        def __init__(self, on_decide=None, denied=False):
            self.calls = []
            self.on_decide = on_decide
            self.denied = denied

        def decide(self, name, summary, detail, *, outward, ask_in_auto):
            self.calls.append((name, summary, detail, outward, ask_in_auto))
            if self.on_decide:
                self.on_decide()
            if self.denied:
                raise DeniedError("owner declined")

    sent = []

    class FixtureSendBook:
        prepare_message = staticmethod(GoogleMailSendBook.prepare_message)

        def __init__(self, *args):
            pass

        def _account(self, account_id):
            assert account_id == "gmail_send_0123456789abcdef01234567"
            return {"status": "connected", "from_address": "owner@example.test"}

        def send_message(self, account_id, recipients, subject, body, *, before_write):
            sent.append((account_id, recipients, subject, body))
            assert before_write() is None
            return {"accepted": True, "delivery_verified": False,
                    "message_id": "sent-message", "thread_id": "thread"}

    monkeypatch.setattr("hutch.tools.google_mail_send.GoogleMailSendBook", FixtureSendBook)
    bot = store.create_bot(Bot(name="gmail-sender", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Send the reviewed note")
    store.create_run(run)
    account_id = "gmail_send_0123456789abcdef01234567"
    store.set_google_mail_send_grant(bot.id, account_id, "Work sender")
    gate = Gate()
    effects = []
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate,
                      config=config, workspace=tmp_path, receipt=lambda: effects.append("effect"))
    tool = build_tools(bot.tools, ctx)["google_mail_send"]
    args = {"to": ["person@example.test"], "subject": "Follow-up", "body": "Thanks for your time."}
    result = tool.run(args, ctx)
    name, _summary, detail, outward, ask_in_auto = gate.calls[0]
    assert name == "google_mail_send" and outward and ask_in_auto
    assert detail["from"] == "owner@example.test"
    assert detail["account"] == "Work sender"
    assert detail["recipients"] == args["to"] and detail["subject"] == args["subject"]
    assert detail["body"] == args["body"]
    assert result.ok and result.data["accepted"] and not result.data["delivery_verified"]
    assert len(sent) == 1 and effects == ["effect"]
    assert tool.effect(args, ctx) == "web"
    assert tool.recorded_arguments(args, ctx)["from_address"] == "owner@example.test"

    gate_on_revoke = Gate(on_decide=lambda: store.remove_google_mail_send_grant(bot.id))
    revoked_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate_on_revoke,
                              config=config, workspace=tmp_path)
    store.set_google_mail_send_grant(bot.id, account_id, "Work sender")
    revoked_tool = GoogleMailSendTool(store.google_mail_send_grant(bot.id))
    before = len(sent)
    result = revoked_tool.run(args, revoked_ctx)
    assert not result.ok and "changed while approval was pending" in result.output
    assert len(sent) == before

    offline = store.create_bot(Bot(name="gmail-sender-offline", model="ollama/local", tools=[],
                                   inference_mode=InferenceMode.offline))
    store.set_google_mail_send_grant(offline.id, account_id, "Work sender")
    offline_run = Run(bot_id=offline.id, prompt="Send the note")
    store.create_run(offline_run)
    offline_ctx = ToolContext(bot=offline, run=offline_run, store=store, policy=PolicyEngine(), gate=Gate(),
                              config=config, workspace=tmp_path)
    assert "google_mail_send" not in build_tools(offline.tools, offline_ctx)


def test_send_tool_denial_rehearsal_and_ambiguous_result_never_retry(tmp_path, store, config, monkeypatch):
    from hutch.approvals import DeniedError
    from hutch.models import Bot, Run
    from hutch.runtime.base import RunAborted
    from hutch.runtime.base import RunAborted
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from hutch.tools.google_mail_send import GoogleMailSendTool

    class Gate:
        def __init__(self, denied=False):
            self.denied = denied

        def decide(self, *args, **kwargs):
            if self.denied:
                raise DeniedError("owner declined")

    class FixtureSendBook:
        prepare_message = staticmethod(GoogleMailSendBook.prepare_message)

        def __init__(self, *args):
            pass

        def _account(self, _account_id):
            return {"status": "connected", "from_address": "owner@example.test"}

        def send_message(self, *args, **kwargs):
            raise GoogleMailSendOutcomeUnknown("Check Gmail Sent before retrying")

    monkeypatch.setattr("hutch.tools.google_mail_send.GoogleMailSendBook", FixtureSendBook)
    bot = store.create_bot(Bot(name="gmail-sender-denied", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Send the note")
    store.create_run(run)
    account_id = "gmail_send_0123456789abcdef01234567"
    store.set_google_mail_send_grant(bot.id, account_id, "Work sender")
    tool = GoogleMailSendTool(store.google_mail_send_grant(bot.id))
    args = {"to": ["person@example.test"], "subject": "Hello", "body": "Body"}
    denied_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=Gate(denied=True),
                             config=config, workspace=tmp_path)
    result = tool.run(args, denied_ctx)
    assert not result.ok and "was not approved" in result.output

    rehearsal_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=Gate(),
                                config=config, workspace=tmp_path, dry_run=True)
    rehearsal = tool.run(args, rehearsal_ctx)
    assert rehearsal.ok and rehearsal.data["simulated"]

    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=Gate(),
                      config=config, workspace=tmp_path)
    with pytest.raises(RunAborted) as aborted:
        tool.run(args, ctx)
    assert aborted.value.reason == "outcome_unknown"
    assert "Check Gmail Sent" in aborted.value.detail
