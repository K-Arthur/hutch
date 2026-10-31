"""Kv-backed persistence for the onboarding setup record.

The single onboarding:setup:v1 record is read, decided, and written under one
process-local lock, so two request saves cannot both win the same expected
revision. One Hutch server per state directory is the supported model; writes
from separate processes are documented out of scope.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from .onboarding import (
    ONBOARDING_CONTRACT_VERSION,
    OnboardingSetup,
    apply_request_edit,
    default_setup,
    encode_setup,
    parse_setup,
)
from .onboarding_choices import choose_route

SETUP_KEY = "onboarding:setup:v1"

_LOCK = threading.Lock()


@dataclass(frozen=True)
class SetupLoad:
    """Outcome of reading the stored setup: absent, present, or damaged."""

    kind: str
    setup: OnboardingSetup | None


@dataclass(frozen=True)
class SaveResult:
    """Outcome of one request save; only accepted writes."""

    kind: str
    setup: OnboardingSetup | None
    reason: str = ""


def load_setup(store) -> SetupLoad:
    """Read and validate the stored setup record."""
    record = parse_setup(store.kv_get(SETUP_KEY))
    return SetupLoad(record.kind, record.setup)


def save_request(store, *, expected_revision: int, request_text: str, now: datetime) -> SaveResult:
    """Apply one request edit under the process lock; persist only on accept."""
    with _LOCK:
        loaded = load_setup(store)
        if loaded.kind == "damaged":
            return SaveResult("damaged", None, "The saved setup is unreadable.")
        setup = loaded.setup if loaded.setup is not None else default_setup(now)
        if setup.contract_version > ONBOARDING_CONTRACT_VERSION:
            return SaveResult("newer_version", setup, "The saved setup uses a newer version.")
        result = apply_request_edit(setup, expected_revision=expected_revision,
                                    request_text=request_text, now=now)
        if result.kind != "accepted" or result.setup is None:
            return SaveResult(result.kind, result.setup, result.reason)
        store.kv_set(SETUP_KEY, encode_setup(result.setup))
        return SaveResult("accepted", result.setup)


def save_route(store, *, expected_revision: int, route_kind: str, now: datetime) -> SaveResult:
    """Apply one route choice under the same process lock; persist only on accept.

    The lock is shared with save_request/reset_setup, so a request edit in one
    tab and a route choice in another cannot both win the same revision. The
    domain decides chosen/replayed/conflict/stale/invalid/no_request; this
    adapter only adds the damaged and newer-version gates, exactly like save_request.
    """
    with _LOCK:
        loaded = load_setup(store)
        if loaded.kind == "damaged":
            return SaveResult("damaged", None, "The saved setup is unreadable.")
        if loaded.setup is None:
            return SaveResult("no_request", None, "Write your request first.")
        setup = loaded.setup
        if setup.contract_version > ONBOARDING_CONTRACT_VERSION:
            return SaveResult("newer_version", setup, "The saved setup uses a newer version.")
        result = choose_route(setup, expected_revision=expected_revision,
                              route_kind=route_kind, now=now)
        if result.kind != "chosen" or result.setup is None:
            return SaveResult(result.kind, result.setup, result.reason)
        store.kv_set(SETUP_KEY, encode_setup(result.setup))
        return SaveResult("chosen", result.setup)


def save_connection(store, *, expected_revision: int, connection_name: str, now: datetime) -> SaveResult:
    """Save the configured connection name and advance step to assistant."""
    with _LOCK:
        loaded = load_setup(store)
        if loaded.kind == "damaged":
            return SaveResult("damaged", None, "The saved setup is unreadable.")
        if loaded.setup is None:
            return SaveResult("no_request", None, "Write your request first.")
        setup = loaded.setup
        if setup.contract_version > ONBOARDING_CONTRACT_VERSION:
            return SaveResult("newer_version", setup, "The saved setup uses a newer version.")
        if expected_revision != setup.revision:
            return SaveResult("conflict", setup, "The setup changed in another window.")
        updated = setup.model_copy(update={
            "revision": setup.revision + 1,
            "connection_name": connection_name,
            "step": "assistant",
            "updated_at": setup.updated_at,
        })
        store.kv_set(SETUP_KEY, encode_setup(updated))
        return SaveResult("accepted", updated)


def save_assistant(store, *, expected_revision: int, assistant_id: str, now: datetime) -> SaveResult:
    """Save the created assistant id and advance step to first_request."""
    with _LOCK:
        loaded = load_setup(store)
        if loaded.kind == "damaged":
            return SaveResult("damaged", None, "The saved setup is unreadable.")
        if loaded.setup is None:
            return SaveResult("no_request", None, "Write your request first.")
        setup = loaded.setup
        if setup.contract_version > ONBOARDING_CONTRACT_VERSION:
            return SaveResult("newer_version", setup, "The saved setup uses a newer version.")
        if expected_revision != setup.revision:
            return SaveResult("conflict", setup, "The setup changed in another window.")
        from .models import iso
        updated = setup.model_copy(update={
            "revision": setup.revision + 1,
            "assistant_id": assistant_id,
            "step": "first_request",
            "updated_at": iso(now),
        })
        store.kv_set(SETUP_KEY, encode_setup(updated))
        return SaveResult("accepted", updated)


def save_first_request_completion(store, *, expected_revision: int, now: datetime) -> SaveResult:
    """Record completion timestamp of the first task."""
    with _LOCK:
        loaded = load_setup(store)
        if loaded.kind == "damaged":
            return SaveResult("damaged", None, "The saved setup is unreadable.")
        if loaded.setup is None:
            return SaveResult("no_request", None, "Write your request first.")
        setup = loaded.setup
        if setup.contract_version > ONBOARDING_CONTRACT_VERSION:
            return SaveResult("newer_version", setup, "The saved setup uses a newer version.")
        from .models import iso
        updated = setup.model_copy(update={
            "revision": setup.revision + 1,
            "first_request_completed_at": iso(now),
            "updated_at": iso(now),
        })
        store.kv_set(SETUP_KEY, encode_setup(updated))
        return SaveResult("accepted", updated)


def dismiss_checklist(store, *, now: datetime) -> SaveResult:
    """Mark the contextual Getting Started checklist as dismissed."""
    with _LOCK:
        loaded = load_setup(store)
        from .models import iso
        setup = loaded.setup if (loaded.kind == "present" and loaded.setup is not None) else default_setup(now)
        updated = setup.model_copy(update={
            "checklist_dismissed": True,
            "updated_at": iso(now),
        })
        store.kv_set(SETUP_KEY, encode_setup(updated))
        return SaveResult("accepted", updated)


def reset_setup(store, now: datetime) -> OnboardingSetup:
    """Write a fresh default record (revision 0) instead of deleting the key."""
    setup = default_setup(now)
    with _LOCK:
        store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup
