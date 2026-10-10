from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.outlook_calendar import OutlookCalendarError
from hutch.outlook_mail import (MAIL_SEND_CALLBACK_PATH, MAIL_SEND_SCOPE, OutlookMailSendBook,
                                OutlookMailSendOutcomeUnknown)


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


def seed_account(book, account_id="mssend_0123456789abcdef01234567"):
    book._write_accounts({"version": 1, "accounts": {account_id: {
        "id": account_id, "label": "Work sending", "created_at": "2026-10-10T00:00:00+00:00",
        "scopes": [MAIL_SEND_SCOPE], "status": "connected"}}})
    book.secrets.put(account_id, "refresh-token")
    return account_id


def test_send_oauth_uses_a_distinct_send_only_scope_callback_and_secret_namespace(tmp_path):
    def handler(request):
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                             "expires_in": 3600, "token_type": "Bearer",
                                             "scope": "Mail.Send offline_access"})
        raise AssertionError(f"unexpected request to {request.url}")

    secrets = MemorySecrets()
    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    callback = "http://localhost:18787" + MAIL_SEND_CALLBACK_PATH
    auth = book.start("Work sender", callback)
    query = parse_qs(urlsplit(auth.url).query)
    assert query["scope"] == ["Mail.Send offline_access"]
    assert query["redirect_uri"] == [callback]
    account = book.finish(auth.state, "single-use-code", callback)
    assert account["id"].startswith("mssend_")
    assert account["scopes"] == ["Mail.Send"]
    assert secrets.values[account["id"]] == "refresh-token"
    assert book.root.name == "outlook-mail-send"


def test_send_oauth_refuses_a_read_only_scope_response(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"access_token": "access-token", "refresh_token": "refresh-token",
                                         "expires_in": 3600, "token_type": "Bearer",
                                         "scope": "Mail.Read offline_access"})

    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=MemorySecrets(),
                               transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    callback = "http://localhost:18787" + MAIL_SEND_CALLBACK_PATH
    auth = book.start("Work sender", callback)
    with pytest.raises(OutlookCalendarError, match="Mail.Send permission"):
        book.finish(auth.state, "single-use-code", callback)


def test_send_is_one_fixed_host_post_and_202_means_accepted_not_delivered(tmp_path):
    requests = []
    secrets = MemorySecrets()

    def handler(request):
        requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        return httpx.Response(202)

    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(handler), clock=lambda: 1_790_000_000)
    account = seed_account(book)
    started = []
    result = book.send_message(account, ["person@example.test"], "Hello", "A short note.",
                               before_write=lambda: started.append(True))
    request = requests[-1]
    assert len(started) == 1
    assert len([item for item in requests if item.url.path.endswith("/sendMail")]) == 1
    assert request.method == "POST" and request.url.host == "graph.microsoft.com"
    assert request.url.path == "/v1.0/me/sendMail"
    assert request.headers["authorization"] == "Bearer access-token"
    assert request.read() == (b'{"message":{"subject":"Hello","body":{"contentType":"Text",'
                              b'"content":"A short note."},"toRecipients":[{"emailAddress":'
                              b'{"address":"person@example.test"}}]},"saveToSentItems":true}')
    assert result == {"accepted": True, "delivery_verified": False}


@pytest.mark.parametrize("recipients,subject,body", [
    (["not an address"], "Hello", "Body"), ([".a@example.test"], "Hello", "Body"),
    (["a..b@example.test"], "Hello", "Body"), (["a@example.test\r\nBcc: b@example.test"], "Hello", "Body"),
    (["a@example.test", "a@example.test"], "Hello", "Body"), ([], "Hello", "Body"),
    (["a@example.test"], "\r\nBcc: b@example.test", "Body"), (["a@example.test"], "", "Body"),
    (["a@example.test"], "Hello", "x" * 12001),
])
def test_send_rejects_invalid_content_before_network(tmp_path, recipients, subject, body):
    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=MemorySecrets())
    account = seed_account(book)
    with pytest.raises(OutlookCalendarError):
        book.send_message(account, recipients, subject, body, before_write=lambda: None)


def test_send_marks_transport_and_server_errors_outcome_unknown_and_never_retries(tmp_path):
    calls = []
    secrets = MemorySecrets()

    def transport(request):
        calls.append(request)
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "access-token", "expires_in": 3600,
                                             "token_type": "Bearer"})
        return httpx.Response(503)

    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=secrets,
                               transport=httpx.MockTransport(transport), clock=lambda: 1_790_000_000)
    account = seed_account(book)
    with pytest.raises(OutlookMailSendOutcomeUnknown, match="may have accepted"):
        book.send_message(account, ["person@example.test"], "Hello", "Body", before_write=lambda: None)
    assert len([request for request in calls if request.url.path.endswith("/sendMail")]) == 1


def test_send_requires_a_send_grant_and_fixed_account_scope(tmp_path):
    book = OutlookMailSendBook(tmp_path, "public-client", secrets_store=MemorySecrets())
    account = seed_account(book)
    book._write_accounts({"version": 1, "accounts": {account: {
        "id": account, "label": "Work", "created_at": "now", "scopes": ["Mail.Read"],
        "status": "connected"}}})
    with pytest.raises(OutlookCalendarError, match="no Mail.Send grant"):
        book.send_message(account, ["person@example.test"], "Hello", "Body", before_write=lambda: None)


def test_send_tool_shows_exact_approval_and_stops_if_grant_is_revoked(tmp_path, store, config, monkeypatch):
    from types import SimpleNamespace

    from hutch.approvals import DeniedError
    from hutch.models import Bot, InferenceMode, Run
    from hutch.safety import PolicyEngine
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.tools.outlook_mail_send import OutlookMailSendTool

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

    sent = []

    class FixtureSendBook:
        prepare_message = staticmethod(OutlookMailSendBook.prepare_message)

        def __init__(self, *args):
            pass

        def send_message(self, account_id, recipients, subject, body, *, before_write):
            sent.append((account_id, recipients, subject, body))
            assert before_write() is None
            return {"accepted": True, "delivery_verified": False}

    monkeypatch.setattr("hutch.tools.outlook_mail_send.OutlookMailSendBook", FixtureSendBook)
    bot = store.create_bot(Bot(name="mail-sender", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Send the reviewed note")
    store.create_run(run)
    account_id = "mssend_0123456789abcdef01234567"
    store.set_outlook_mail_send_grant(bot.id, account_id, "Work sender")
    gate = Gate()
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate,
                      config=config, workspace=tmp_path)
    tool = build_tools(bot.tools, ctx)["outlook_mail_send"]
    args = {"to": ["person@example.test"], "subject": "Follow-up", "body": "Thanks for your time."}

    result = tool.run(args, ctx)
    name, _summary, detail, outward, ask_in_auto = gate.details[0]
    assert name == "outlook_mail_send" and outward and ask_in_auto
    assert detail["account"] == "Work sender"
    assert detail["recipients"] == args["to"] and detail["subject"] == args["subject"]
    assert detail["body"] == args["body"]
    assert result.ok and result.data["accepted"] and not result.data["delivery_verified"]
    assert len(sent) == 1
    assert tool.effect(args, ctx) == "web"
    assert tool.recorded_arguments(args, ctx)["account_id"] == account_id

    gate_on_revoke = Gate(on_decide=lambda: store.remove_outlook_mail_send_grant(bot.id))
    revoked_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=gate_on_revoke,
                              config=config, workspace=tmp_path)
    store.set_outlook_mail_send_grant(bot.id, account_id, "Work sender")
    revoked_tool = OutlookMailSendTool(store.outlook_mail_send_grant(bot.id))
    before = len(sent)
    result = revoked_tool.run(args, revoked_ctx)
    assert not result.ok and "changed while approval was pending" in result.output
    assert len(sent) == before

    store.remove_outlook_mail_send_grant(bot.id)
    offline = store.create_bot(Bot(name="mail-sender-offline", model="ollama/local", tools=[],
                                   inference_mode=InferenceMode.offline))
    store.set_outlook_mail_send_grant(offline.id, account_id, "Work sender")
    offline_run = Run(bot_id=offline.id, prompt="Send the note")
    store.create_run(offline_run)
    offline_ctx = ToolContext(bot=offline, run=offline_run, store=store, policy=PolicyEngine(), gate=Gate(),
                              config=config, workspace=tmp_path)
    assert "outlook_mail_send" not in build_tools(offline.tools, offline_ctx)


def test_send_tool_denial_and_rehearsal_never_contact_microsoft(tmp_path, store, config, monkeypatch):
    from hutch.approvals import DeniedError
    from hutch.models import Bot, Run
    from hutch.safety import PolicyEngine
    from hutch.tools.outlook_mail_send import OutlookMailSendTool
    from hutch.tools.base import ToolContext

    class DenyingGate:
        def decide(self, *args, **kwargs):
            raise DeniedError("owner declined")

    class NeverSendBook:
        @staticmethod
        def prepare_message(recipients, subject, body):
            return OutlookMailSendBook.prepare_message(recipients, subject, body)

        def __init__(self, *args):
            pass

        def send_message(self, *args, **kwargs):
            raise AssertionError("denial/rehearsal must not call Graph")

    monkeypatch.setattr("hutch.tools.outlook_mail_send.OutlookMailSendBook", NeverSendBook)
    bot = store.create_bot(Bot(name="mail-sender-denied", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Send the note")
    store.create_run(run)
    account_id = "mssend_0123456789abcdef01234567"
    store.set_outlook_mail_send_grant(bot.id, account_id, "Work sender")
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=DenyingGate(),
                      config=config, workspace=tmp_path)
    tool = OutlookMailSendTool(store.outlook_mail_send_grant(bot.id))
    args = {"to": ["person@example.test"], "subject": "Hello", "body": "Body"}
    result = tool.run(args, ctx)
    assert not result.ok and "was not approved" in result.output

    rehearsed_ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=DenyingGate(),
                                config=config, workspace=tmp_path, dry_run=True)
    rehearsal = tool.run(args, rehearsed_ctx)
    assert rehearsal.ok and rehearsal.data["simulated"]


def test_send_tool_preserves_ambiguous_transport_as_outcome_unknown(tmp_path, store, config, monkeypatch):
    from hutch.models import Bot, Run
    from hutch.runtime.base import RunAborted
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from hutch.tools.outlook_mail_send import OutlookMailSendTool

    class ApprovingGate:
        def decide(self, *args, **kwargs):
            return None

    class AmbiguousBook:
        prepare_message = staticmethod(OutlookMailSendBook.prepare_message)

        def __init__(self, *args):
            pass

        def send_message(self, account_id, recipients, subject, body, *, before_write):
            assert before_write() is None
            raise OutlookMailSendOutcomeUnknown("check Sent Items before retrying")

    monkeypatch.setattr("hutch.tools.outlook_mail_send.OutlookMailSendBook", AmbiguousBook)
    bot = store.create_bot(Bot(name="mail-sender-unknown", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="Send the note")
    store.create_run(run)
    store.set_outlook_mail_send_grant(bot.id, "mssend_0123456789abcdef01234567", "Work sender")
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=ApprovingGate(),
                      config=config, workspace=tmp_path, receipt=lambda: None)
    tool = OutlookMailSendTool(store.outlook_mail_send_grant(bot.id))

    with pytest.raises(RunAborted) as aborted:
        tool.run({"to": ["person@example.test"], "subject": "Hello", "body": "Body"}, ctx)
    assert aborted.value.reason == "outcome_unknown"
    assert "check Sent Items" in aborted.value.detail
