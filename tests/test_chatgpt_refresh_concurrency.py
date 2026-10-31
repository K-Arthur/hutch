"""Two Hutch processes must not rotate the same refresh token twice.

A rotating refresh token is single-use: if two concurrent callers both spend it, the provider may
invalidate the grant and the account has to be reconnected. The chatgpt auth store serialises refresh
across processes with an exclusive file lock, so the second caller must find the token already renewed
and reuse it rather than posting its own refresh.

This test runs the real lock (two ChatGPTAuthBook instances holding separate file descriptors, which
is how two processes contend) and counts the refresh calls the provider saw.
"""
from __future__ import annotations

import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tests.test_chatgpt_auth import setup_auth

from hutch.chatgpt_auth import AUTH_ORIGIN, RESOURCE


def test_concurrent_refresh_rotates_the_token_exactly_once(tmp_path):
    auth, callback_nonce, now = setup_auth(tmp_path)
    url = auth.start("http://127.0.0.1:8787/auth/callback")
    params = parse_qs(urlsplit(url).query)
    callback_nonce[0] = params["nonce"][0]
    account_id = auth.finish(state=params["state"][0], code="one-time-code",
                             returned_client_id="oaiapp_fixture")["account_id"]

    # Force the token to be expired so both callers must refresh.
    path = tmp_path / "state/chatgpt/accounts.json"
    data = json.loads(path.read_text())
    record = data["accounts"][account_id]
    record["expires_at"] = now + 1
    path.write_text(json.dumps(data))

    refresh_calls = []
    gate = threading.Event()

    def counting_handler(request):
        if request.url == httpx.URL(AUTH_ORIGIN + "/api/accounts/oauth/token"):
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["refresh_token"]:
                refresh_calls.append(form["refresh_token"][0])
                # Hold the first refresh long enough that a second caller would overlap if the lock
                # were not doing its job.
                gate.wait(2.0)
                return httpx.Response(200, json={"access_token": "access-2", "refresh_token": "refresh-2",
                                                 "token_type": "Bearer", "expires_in": 3600,
                                                 "scope": record["scopes"] and " ".join(record["scopes"])})
        return httpx.Response(404)

    transport = httpx.MockTransport(counting_handler)
    # Separate instances = separate file descriptors = real cross-process contention on the same lock.
    first = type(auth)(tmp_path / "state", transport=transport, clock=lambda: now)
    second = type(auth)(tmp_path / "state", transport=transport, clock=lambda: now)

    results = []

    def call(book):
        try:
            results.append(book.access_token(account_id))
        except Exception as exc:  # noqa: BLE001 - reported through the assertion below
            results.append(exc)

    t1 = threading.Thread(target=call, args=(first,))
    t2 = threading.Thread(target=call, args=(second,))
    t1.start()
    time.sleep(0.15)          # let the first caller take the lock and start refreshing
    t2.start()
    time.sleep(0.15)
    gate.set()                # release the in-flight refresh
    t1.join(10)
    t2.join(10)

    assert results == ["access-2", "access-2"], results
    assert refresh_calls == ["refresh-1"], f"the refresh token was spent {len(refresh_calls)} times"
    saved = json.loads(path.read_text())["accounts"][account_id]
    assert saved["refresh_token"] == "refresh-2"
