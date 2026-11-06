"""Real processes must not spend a rotating refresh token twice."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.chatgpt_auth import AUTH_ORIGIN, ChatGPTAuthBook, ChatGPTAuthError
from tests.test_chatgpt_auth import setup_auth

SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


def _sign_in(tmp_path) -> tuple[str, float, Path]:
    auth, callback_nonce, now = setup_auth(tmp_path)
    url = auth.start("http://127.0.0.1:8787/auth/callback")
    params = parse_qs(urlsplit(url).query)
    callback_nonce[0] = params["nonce"][0]
    account_id = auth.finish(state=params["state"][0], code="one-time-code",
                             returned_client_id="oaiapp_fixture")["account_id"]
    path = tmp_path / "state/chatgpt/accounts.json"
    data = json.loads(path.read_text())
    data["accounts"][account_id]["expires_at"] = now + 1
    path.write_text(json.dumps(data))
    return account_id, now, path


def _refresh_child(state_dir, account_id, now, counter, started, release, queue):
    def handler(request):
        if request.url == httpx.URL(AUTH_ORIGIN + "/api/accounts/oauth/token"):
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["refresh_token"]:
                with counter.get_lock():
                    counter.value += 1
                started.set()
                release.wait(10)
                return httpx.Response(200, json={"access_token": "access-2", "refresh_token": "refresh-2",
                                                 "token_type": "Bearer", "expires_in": 3600, "scope": SCOPE})
        return httpx.Response(404)

    book = ChatGPTAuthBook(Path(state_dir), transport=httpx.MockTransport(handler), clock=lambda: now)
    try:
        queue.put(("ok", book.access_token(account_id)))
    except BaseException as exc:  # noqa: BLE001 - reported to the parent assertion
        queue.put(("error", type(exc).__name__ + ": " + str(exc)))


@pytest.mark.skipif(os.name != "posix", reason="cross-process flock is POSIX")
def test_two_processes_refresh_a_rotating_token_exactly_once(tmp_path):
    account_id, now, path = _sign_in(tmp_path)
    context = mp.get_context("fork")
    counter, started = context.Value("i", 0), context.Event()
    release, queue = context.Event(), context.Queue()
    first = context.Process(target=_refresh_child,
                            args=(tmp_path / "state", account_id, now, counter, started, release, queue))
    first.start()
    assert started.wait(10), "the first process never entered the refresh"
    second = context.Process(target=_refresh_child,
                             args=(tmp_path / "state", account_id, now, counter, started, release, queue))
    second.start()
    time.sleep(0.3)      # the second process is now blocked on the same account lock
    release.set()
    for process in (first, second):
        process.join(15)
        assert process.exitcode == 0
    results = [queue.get(timeout=5) for _ in range(2)]
    assert results == [("ok", "access-2"), ("ok", "access-2")], results
    assert counter.value == 1, f"the refresh token was spent {counter.value} times"
    saved = json.loads(path.read_text())["accounts"][account_id]
    assert saved["refresh_token"] == "refresh-2"


def test_a_failed_refresh_keeps_the_stored_credential(tmp_path):
    account_id, now, path = _sign_in(tmp_path)
    failing = ChatGPTAuthBook(tmp_path / "state", transport=httpx.MockTransport(lambda request: httpx.Response(500)),
                              clock=lambda: now)
    with pytest.raises(ChatGPTAuthError):
        failing.access_token(account_id)
    saved = json.loads(path.read_text())["accounts"][account_id]
    assert saved["access_token"] == "access-1"
    assert saved["refresh_token"] == "refresh-1"
