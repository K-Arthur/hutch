"""Server-rendered slice 01 onboarding page: states, CSRF, persistence, escaping."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import iso, utcnow
from hutch.onboarding import (
    ONBOARDING_REQUIREMENTS_VERSION,
    apply_request_edit,
    default_setup,
    encode_setup,
    empty_view,
)
from hutch.onboarding_store import SETUP_KEY, save_request
from hutch.server.app import REMOTE_ROUTE_CAPABILITIES, create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.state_dir = tmp_path / "state"
        yield c


def csrf(c) -> str:
    body = c.get("/onboarding").text
    return re.search(r'<meta name="csrf" content="([^"]+)">', body).group(1)


def record_revision(c) -> int:
    return json.loads(c.app.state.store.kv_get(SETUP_KEY))["revision"]


def seed(c, *, text="A seeded request", contract_version=1, requirements_version=1,
         expires_in=timedelta(days=30), step="request"):
    now = utcnow()
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    setup = result.setup.model_copy(update={
        "contract_version": contract_version,
        "requirements_version": requirements_version,
        "resume_expires_at": iso(now + expires_in),
        "step": step,
    })
    c.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup


def test_get_renders_chrome_less_empty_state(client):
    r = client.get("/onboarding")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    text = r.text
    assert 'data-onboarding-state="setup.empty_no_route"' in text
    assert 'id="primary-nav"' not in text
    assert "topbar" not in text
    assert 'class="foot"' not in text
    assert text.count("<h1") == 1
    assert "Step 1 of 5" in text
    assert '<meta name="csrf"' in text
    assert 'name="revision" value="0"' in text
    assert 'maxlength="20000"' in text
    assert "Save and continue" in text


def test_the_request_form_explains_what_a_useful_request_contains(client):
    """A8: guidance replaces invented prompt buttons; it is copy in the form, not a canned request."""
    text = client.get("/onboarding").text
    assert 'id="request-guidance"' in text
    assert ("A useful request names the outcome you want, where to look, what to avoid, what to hand "
            "back, and when the assistant should stop and ask you.") in text
    described = re.search(r'aria-describedby="([^"]*request-guidance[^"]*)"', text)
    assert described, "the guidance is wired into the textarea's accessible description"


def test_save_redirects_to_saved_state_and_stores_request(client):
    token = csrf(client)
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": "0", "request": "Plan my week honestly"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding"
    page = client.get("/onboarding")
    assert 'data-onboarding-state="setup.draft.saved"' in page.text
    assert "Saved on this machine." in page.text
    assert "Plan my week honestly" in page.text
    stored = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert stored["revision"] == 1
    assert stored["request_text"] == "Plan my week honestly"
    assert stored["step"] == "request"
    assert stored["requirements_version"] == ONBOARDING_REQUIREMENTS_VERSION


def test_request_survives_a_full_store_and_app_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as first:
        token = csrf(first)
        first.post("/onboarding/request",
                   data={"csrf": token, "revision": "0", "request": "Juno 助手 Zoë Ångström محمد"},
                   follow_redirects=False)
    with TestClient(create_app()) as reopened:
        page = reopened.get("/onboarding")
        assert page.status_code == 200
        assert 'data-onboarding-state="setup.resume.current"' in page.text
        assert "Juno 助手 Zoë Ångström محمد" in page.text
        assert "You left off here" in page.text


def test_duplicate_submit_is_replayed_and_creates_no_second_write(client):
    token = csrf(client)
    data = {"csrf": token, "revision": "0", "request": "Same request"}
    first = client.post("/onboarding/request", data=data, follow_redirects=False)
    second = client.post("/onboarding/request", data=data, follow_redirects=True)
    assert first.status_code == 303
    assert second.status_code == 200
    assert "Already saved - nothing changed." in second.text
    assert record_revision(client) == 1
    stored = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert stored["request_text"] == "Same request"


def test_stale_revision_renders_explicit_conflict_and_never_overwrites(client):
    client.get("/onboarding")
    store = client.app.state.store
    save_request(store, expected_revision=0, request_text="Saved in another window", now=utcnow())
    token = csrf(client)
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": "0", "request": "My text from this tab"},
                    follow_redirects=False)
    assert r.status_code == 409
    assert 'data-onboarding-state="setup.conflict"' in r.text
    assert "This setup changed in another window" in r.text
    assert "Saved in another window" in r.text
    assert "My text from this tab" in r.text
    still = json.loads(store.kv_get(SETUP_KEY))
    assert still["request_text"] == "Saved in another window"
    assert still["revision"] == 1


def test_validation_errors_are_explicit_and_preserve_input(client):
    token = csrf(client)
    blank = client.post("/onboarding/request",
                        data={"csrf": token, "revision": "0", "request": "   "},
                        follow_redirects=False)
    assert blank.status_code == 422
    assert 'data-onboarding-state="input.invalid"' in blank.text
    assert 'role="alert"' in blank.text
    assert "data-error-summary" in blank.text
    assert 'href="#request"' in blank.text
    too_long = client.post("/onboarding/request",
                           data={"csrf": token, "revision": "0", "request": "x" * 20001},
                           follow_redirects=False)
    assert too_long.status_code == 422
    assert "20000" in too_long.text or "20,000" in too_long.text
    bad_revision = client.post("/onboarding/request",
                               data={"csrf": token, "revision": "not-a-number", "request": "kept"},
                               follow_redirects=False)
    assert bad_revision.status_code == 422
    assert "out of date" in bad_revision.text
    assert "kept" in bad_revision.text
    assert client.app.state.store.kv_get(SETUP_KEY) is None


def test_20000_character_request_is_the_server_side_boundary(client):
    token = csrf(client)
    accepted = client.post("/onboarding/request",
                           data={"csrf": token, "revision": "0", "request": "a" * 20000},
                           follow_redirects=False)
    assert accepted.status_code == 303
    assert len(json.loads(client.app.state.store.kv_get(SETUP_KEY))["request_text"]) == 20000


def test_missing_or_invalid_csrf_returns_explicit_forbidden_state(client):
    missing = client.post("/onboarding/request", data={"revision": "0", "request": "typed but not saved"})
    assert missing.status_code == 403
    assert 'data-onboarding-state="auth.csrf_rejected"' in missing.text
    assert "not available from this session" in missing.text
    assert "typed but not saved" in missing.text
    assert client.app.state.store.kv_get(SETUP_KEY) is None
    token = csrf(client)
    wrong = client.post("/onboarding/request",
                        data={"csrf": token + "x", "revision": "0", "request": "no"},
                        follow_redirects=False)
    assert wrong.status_code == 403
    assert client.app.state.store.kv_get(SETUP_KEY) is None


def test_reset_from_a_current_saved_record_is_refused(client):
    token = csrf(client)
    client.post("/onboarding/request", data={"csrf": token, "revision": "0", "request": "Keep me"},
                follow_redirects=False)
    page = client.get("/onboarding")
    token = re.search(r'<meta name="csrf" content="([^"]+)">', page.text).group(1)
    blocked = client.post("/onboarding/reset", data={"csrf": token}, follow_redirects=False)
    assert blocked.status_code == 409
    assert 'data-onboarding-state="setup.reset_blocked"' in blocked.text
    assert "still current" in blocked.text
    stored = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert stored["request_text"] == "Keep me"
    assert stored["revision"] == 1


def test_reset_from_an_expired_record_is_allowed(client):
    seed(client, text="Old but recoverable", expires_in=timedelta(days=-1))
    token = csrf(client)
    reset = client.post("/onboarding/reset", data={"csrf": token}, follow_redirects=False)
    assert reset.status_code == 303
    fresh = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert fresh["revision"] == 0
    assert fresh["request_text"] == ""


def test_reset_requires_csrf(client):
    r = client.post("/onboarding/reset", data={}, follow_redirects=False)
    assert r.status_code == 403
    assert 'data-onboarding-state="auth.csrf_rejected"' in r.text


def test_user_text_is_html_escaped(client):
    token = csrf(client)
    client.post("/onboarding/request",
                data={"csrf": token, "revision": "0",
                      "request": '<script>alert("x")</script> & "quoted"'}, follow_redirects=False)
    page = client.get("/onboarding")
    assert '<script>alert("x")</script>' not in page.text
    assert "&lt;script&gt;" in page.text


def test_damaged_record_renders_recovery_and_reset_starts_over(client):
    store = client.app.state.store
    store.kv_set(SETUP_KEY, "{not valid json")
    damaged = client.get("/onboarding")
    assert damaged.status_code == 200
    assert 'data-onboarding-state="setup.damaged"' in damaged.text
    assert "unreadable" in damaged.text
    assert "Start over" in damaged.text
    token = csrf(client)
    reset = client.post("/onboarding/reset", data={"csrf": token}, follow_redirects=False)
    assert reset.status_code == 303
    fresh = json.loads(store.kv_get(SETUP_KEY))
    assert fresh["revision"] == 0
    assert fresh["request_text"] == ""
    empty = client.get("/onboarding")
    assert 'data-onboarding-state="setup.empty_no_route"' in empty.text


def test_stale_requirements_offer_resave_that_refreshes_versions(client):
    seeded = seed(client, text="Keep this request", requirements_version=0)
    stale = client.get("/onboarding")
    assert 'data-onboarding-state="setup.resume.stale"' in stale.text
    assert "setup requirements changed" in stale.text
    assert "Keep this request" in stale.text
    token = csrf(client)
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": str(seeded.revision), "request": "Keep this request"},
                    follow_redirects=False)
    assert r.status_code == 303
    refreshed = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert refreshed["requirements_version"] == ONBOARDING_REQUIREMENTS_VERSION
    assert refreshed["revision"] == seeded.revision + 1


def test_expired_setup_offers_refresh_and_keeps_request_text(client):
    seeded = seed(client, text="An old request", expires_in=timedelta(days=-1))
    expired = client.get("/onboarding")
    assert 'data-onboarding-state="setup.resume.expired"' in expired.text
    assert "saved a while ago" in expired.text
    assert "An old request" in expired.text
    token = csrf(client)
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": str(seeded.revision), "request": "An old request"},
                    follow_redirects=False)
    assert r.status_code == 303
    refreshed = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert refreshed["resume_expires_at"] > seeded.resume_expires_at
    assert refreshed["request_text"] == "An old request"


def test_unknown_step_is_stale_not_damaged(client):
    seed(client, text="Legacy step request", step="legacy_step")
    page = client.get("/onboarding")
    assert 'data-onboarding-state="setup.resume.stale"' in page.text
    assert "no longer part of the setup" in page.text
    assert "Legacy step request" in page.text


def test_newer_contract_version_is_never_reported_as_damaged(client):
    seeded = seed(client, text="Written by the future", contract_version=2)
    page = client.get("/onboarding")
    assert 'data-onboarding-state="setup.resume.stale"' in page.text
    assert "newer Hutch version" in page.text
    assert "unreadable" not in page.text
    token = csrf(client)
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": str(seeded.revision), "request": "Written by the future"},
                    follow_redirects=False)
    assert r.status_code == 409
    still = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert still["contract_version"] == 2
    assert still["revision"] == seeded.revision


def test_edit_mode_saves_changes(client):
    token = csrf(client)
    client.post("/onboarding/request",
                data={"csrf": token, "revision": "0", "request": "First wording"},
                follow_redirects=False)
    edit = client.get("/onboarding?edit=1")
    assert edit.status_code == 200
    assert 'data-onboarding-mode="edit"' in edit.text
    assert "First wording" in edit.text
    assert "Save changes" in edit.text
    r = client.post("/onboarding/request",
                    data={"csrf": token, "revision": "1", "request": "Second wording"},
                    follow_redirects=True)
    assert "Second wording" in r.text
    stored = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert stored["request_text"] == "Second wording"
    assert stored["revision"] == 2


def test_outer_whitespace_is_trimmed_but_inner_text_is_intact(client):
    token = csrf(client)
    client.post("/onboarding/request",
                data={"csrf": token, "revision": "0", "request": "  Zoë  keeps  inner  spaces  "},
                follow_redirects=False)
    stored = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert stored["request_text"] == "Zoë  keeps  inner  spaces"


def test_onboarding_routes_are_closed_to_paired_phones(client):
    for route in (("GET", "/onboarding"), ("POST", "/onboarding/request"), ("POST", "/onboarding/reset")):
        assert route in REMOTE_ROUTE_CAPABILITIES
        assert REMOTE_ROUTE_CAPABILITIES[route] is None


def test_existing_server_pages_keep_their_chrome(client):
    page = client.get("/legacy/connections")
    assert page.status_code == 200
    assert 'id="primary-nav"' in page.text
    assert 'class="foot"' in page.text


def test_empty_view_contract_is_machine_assertable():
    view = empty_view()
    assert view.state == "setup.empty_no_route"
    assert view.step_index == 1
    assert view.request_text == ""