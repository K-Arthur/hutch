"""Server-rendered AI-service chooser (slice 02): states, CSRF, replay, conflict.

The chooser is reached only with a saved request; no provider or localhost call
is made by the page or these tests. Seeded records use the same kv adapter as
the app; browser history is covered by tests/e2e/test_onboarding_chooser.py.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import iso, utcnow
from hutch.onboarding import (
    ONBOARDING_CONTRACT_VERSION,
    ONBOARDING_REQUIREMENTS_VERSION,
    apply_request_edit,
    default_setup,
    encode_setup,
)
from hutch.onboarding_choices import RECOMMENDED_ROUTE, ROUTE_KINDS, ROUTE_LABELS
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import REMOTE_ROUTE_CAPABILITIES, create_app

CHOOSER = "/onboarding/ai-service"
SUBMIT = "/onboarding/ai-service/choose"
NON_LATIN = "Juno 助手 - Zoë Ångström - محمد - plan the launch"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        yield c


def seed(c, *, text="A seeded request", route_kind="", **overrides):
    now = utcnow()
    result = apply_request_edit(default_setup(now), expected_revision=0,
                                request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    setup = result.setup.model_copy(update={
        "resume_expires_at": iso(now + timedelta(days=30)),
        "route_kind": route_kind,
        "route_chosen_at": iso(now) if route_kind else "",
    } | overrides)
    c.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup


def stored(c) -> dict:
    return json.loads(c.app.state.store.kv_get(SETUP_KEY))


def state(html: str) -> str:
    return re.search(r'data-onboarding-state="([^"]+)"', html).group(1)


def csrf(c) -> str:
    body = c.get(CHOOSER).text
    return re.search(r'<meta name="csrf" content="([^"]+)">', body).group(1)


def submit(c, *, route="hosted_key", revision=None, token=None, follow=False):
    token = token if token is not None else csrf(c)
    rev = revision if revision is not None else stored(c)["revision"]
    return c.post(SUBMIT, data={"csrf": token, "revision": str(rev), "route_kind": route},
                  follow_redirects=follow)


def test_get_without_a_saved_request_redirects_to_the_request_step(client):
    r = client.get(CHOOSER, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/onboarding"
    followed = client.get(CHOOSER)
    assert state(followed.text) == "setup.empty_no_route"
    assert "Write your request first" in followed.text


def test_get_with_a_blank_stored_request_redirects(client):
    client.app.state.store.kv_set(SETUP_KEY, encode_setup(default_setup(utcnow())))
    r = client.get(CHOOSER, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/onboarding"


def test_chooser_renders_exactly_three_routes_and_keeps_the_request(client):
    seed(client, text=NON_LATIN)
    r = client.get(CHOOSER)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    html = r.text
    assert state(html) == "setup.ai_service.choose"
    assert html.count('name="route_kind"') == 3
    assert [kind for kind in ROUTE_KINDS if f'value="{kind}"' in html] == list(ROUTE_KINDS)
    assert html.count("Recommended") >= 1
    assert "already have a provider key" in html
    assert NON_LATIN in html
    assert html.count("<h1") == 1
    assert "Apps and devices can be connected later" in html
    assert "connect later" in html or "can wait" in html
    assert "Telegram" not in html
    assert "http://" not in html and "https://" not in html
    assert html.count("data-primary") == 1


def test_chooser_copy_makes_no_account_download_or_pricing_claim(client):
    seed(client)
    html = client.get(CHOOSER).text.lower()
    for forbidden in ("sign up", "download", "free forever", "trial", "account", "telegram", "channel"):
        assert forbidden not in html, forbidden
    assert "not checked" in html or "does not check" in html


@pytest.mark.parametrize("kind", ROUTE_KINDS)
def test_valid_choice_redirects_persists_and_shows_the_chosen_state(client, kind):
    saved = seed(client)
    r = submit(client, route=kind)
    assert r.status_code == 303 and r.headers["location"] == CHOOSER
    record = stored(client)
    assert record["route_kind"] == kind
    assert record["route_chosen_at"]
    assert record["revision"] == saved.revision + 1
    assert record["request_text"] == saved.request_text
    assert record["step"] == "ai_service"
    page = client.get(CHOOSER).text
    assert state(page) == "setup.ai_service.chosen"
    assert f"You chose {ROUTE_LABELS[kind]}" in page
    assert "Selected" in page
    assert "Step 2 of 5" in page
    assert "Continue to Apps &amp; AI" in page
    assert "Change route" in page
    assert page.count("data-primary") == 1
    assert saved.request_text in page


def test_choice_survives_a_full_store_and_app_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as first:
        seed(first)
        assert submit(first, route="local_service").status_code == 303
    with TestClient(create_app()) as reopened:
        page = reopened.get(CHOOSER)
        assert state(page.text) == "setup.ai_service.chosen"
        assert ROUTE_LABELS["local_service"] in page.text


def test_same_choice_resubmit_replays_without_a_second_write(client):
    seed(client)
    submit(client, route="opencode")
    before = stored(client)
    replay = submit(client, route="opencode", revision=0)
    assert replay.status_code == 303
    page = client.get(CHOOSER).text
    assert "already selected" in page.lower()
    assert stored(client) == before


def test_different_choice_on_the_current_revision_is_a_deliberate_change(client):
    seed(client)
    submit(client, route="hosted_key")
    before = stored(client)
    changed = submit(client, route="local_service", revision=before["revision"])
    assert changed.status_code == 303
    record = stored(client)
    assert record["route_kind"] == "local_service"
    assert record["revision"] == before["revision"] + 1


def test_different_choice_from_a_stale_revision_is_an_explicit_conflict(client):
    saved = seed(client)
    submit(client, route="hosted_key")
    before = stored(client)
    conflict = submit(client, route="opencode", revision=saved.revision)
    assert conflict.status_code == 409
    assert state(conflict.text) == "setup.ai_service.conflict"
    assert ROUTE_LABELS["hosted_key"] in conflict.text
    assert ROUTE_LABELS["opencode"] in conflict.text
    assert "changed in another window" in conflict.text
    assert "Review latest saved setup" in conflict.text
    assert stored(client) == before


def test_unknown_or_missing_route_is_an_explicit_invalid_state(client):
    seed(client)
    before = stored(client)
    unknown = submit(client, route="telegram")
    assert unknown.status_code == 422
    assert state(unknown.text) == "setup.ai_service.invalid"
    assert "Choose one of the three AI service routes" in unknown.text
    assert 'data-error-summary' in unknown.text
    missing = submit(client, route="")
    assert missing.status_code == 422
    assert "exactly three AI service routes" not in missing.text
    assert stored(client) == before


def test_malformed_revision_is_a_fixable_form_error(client):
    seed(client)
    before = stored(client)
    r = client.post(SUBMIT, data={"csrf": csrf(client), "revision": "many", "route_kind": "opencode"},
                    follow_redirects=False)
    assert r.status_code == 422
    assert state(r.text) == "setup.ai_service.invalid"
    assert stored(client) == before


def test_missing_or_invalid_csrf_is_an_explicit_forbidden_state(client):
    seed(client)
    before = stored(client)
    missing = client.post(SUBMIT, data={"revision": "1", "route_kind": "opencode"},
                          follow_redirects=False)
    assert missing.status_code == 403
    assert state(missing.text) == "auth.csrf_rejected"
    assert "Reload the chooser" in missing.text
    assert stored(client) == before
    invalid = client.post(SUBMIT, data={"csrf": "wrong", "revision": "1", "route_kind": "opencode"},
                          follow_redirects=False)
    assert invalid.status_code == 403 and stored(client) == before


def test_requirements_mismatch_renders_stale_and_blocks_choosing(client):
    saved = seed(client, requirements_version=ONBOARDING_REQUIREMENTS_VERSION - 1)
    page = client.get(CHOOSER)
    assert page.status_code == 200
    assert state(page.text) == "setup.ai_service.stale"
    assert "Review my setup" in page.text
    assert saved.request_text in page.text
    assert 'name="route_kind"' not in page.text
    r = submit(client, route="hosted_key", revision=saved.revision)
    assert r.status_code == 409
    assert state(r.text) == "setup.ai_service.stale"


def test_removed_stored_route_is_stale_but_can_be_re_chosen(client):
    saved = seed(client, route_kind="retired_route")
    page = client.get(CHOOSER)
    assert state(page.text) == "setup.ai_service.stale"
    assert "no longer offered" in page.text
    assert page.text.count('name="route_kind"') == 3
    changed = submit(client, route="opencode", revision=saved.revision)
    assert changed.status_code == 303
    assert stored(client)["route_kind"] == "opencode"


def test_newer_contract_record_renders_stale_and_is_never_overwritten(client):
    saved = seed(client, contract_version=ONBOARDING_CONTRACT_VERSION + 1)
    page = client.get(CHOOSER)
    assert state(page.text) == "setup.ai_service.stale"
    assert "newer Hutch version" in page.text
    before = stored(client)
    r = submit(client, route="hosted_key", revision=saved.revision)
    assert r.status_code == 409
    assert stored(client) == before


def test_damaged_record_recovery_is_explicit_and_never_overwritten(client):
    client.app.state.store.kv_set(SETUP_KEY, "{not-json")
    page = client.get(CHOOSER, follow_redirects=True)
    assert state(page.text) == "setup.damaged"
    assert "unreadable" in page.text
    r = client.post(SUBMIT, data={"csrf": csrf_from_request_page(client), "revision": "0",
                                  "route_kind": "hosted_key"}, follow_redirects=True)
    assert state(r.text) == "setup.damaged"
    assert client.app.state.store.kv_get(SETUP_KEY) == "{not-json"


def csrf_from_request_page(c) -> str:
    body = c.get("/onboarding").text
    return re.search(r'<meta name="csrf" content="([^"]+)">', body).group(1)


def test_no_request_post_returns_to_the_request_step(client):
    r = client.post(SUBMIT, data={"csrf": csrf_from_request_page(client), "revision": "0",
                                  "route_kind": "hosted_key"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/onboarding"
    followed = client.get("/onboarding").text
    assert "Write your request first" in followed
    assert client.app.state.store.kv_get(SETUP_KEY) is None


def test_change_mode_preselects_the_saved_route(client):
    seed(client, route_kind=RECOMMENDED_ROUTE)
    page = client.get(CHOOSER + "?change=1").text
    assert state(page) == "setup.ai_service.choose"
    assert "Change your AI service route" in page
    assert re.search(r'value="hosted_key"\s+required\s+checked', page)


def test_chooser_routes_are_closed_to_paired_phones(client):
    for route in (("GET", CHOOSER), ("POST", SUBMIT)):
        assert route in REMOTE_ROUTE_CAPABILITIES
        assert REMOTE_ROUTE_CAPABILITIES[route] is None


def test_request_text_is_escaped_not_interpreted(client):
    seed(client, text='<script>alert("x")</script> plan the launch')
    for path in (CHOOSER,):
        html = client.get(path).text
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html
