"""Onboarding slice 02: pure decisions for the in-context AI-service chooser.

The chooser is a domain step, not a provider check: it records which of the
three offered routes the owner intends to set up. Detection, probing, key
handling and external-login waiting belong to later slices and must not appear
here. This module is pure (no store, templates, filesystem, or network) and
builds on the slice-01 setup record and resume view. Expected outcomes are
returned as dataclasses, never raised.

State tokens are part of the browser-test contract; the page renders them as
data-onboarding-state. Copy is separate and lives in the HTTP/template layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import iso
from .onboarding import (
    ONBOARDING_CONTRACT_VERSION,
    ONBOARDING_REQUIREMENTS_VERSION,
    RESUME_TTL,
    STEP_ORDER,
    OnboardingSetup,
    resume_view,
)

ROUTE_KINDS = ("hosted_key", "local_service", "opencode")
ROUTE_LABELS = {
    "hosted_key": "Hosted provider key",
    "local_service": "Local model service",
    "opencode": "Existing OpenCode login",
}
ROUTE_DESCRIPTIONS = {
    "hosted_key": (
        "Paste a key from a hosted AI provider on the next step. Use a provider "
        "you already have; this step does not create one."
    ),
    "local_service": (
        "Use a model server you run on this machine, such as Ollama. Hutch "
        "reaches it over this machine's network."
    ),
    "opencode": (
        "Use the OpenCode CLI and a login that already exists on this machine. "
        "Hutch checks that login; you do not sign in here."
    ),
}
RECOMMENDED_ROUTE = "hosted_key"
RECOMMENDED_QUALIFIER = "recommended only if you already have a provider key"

STATE_AI_SERVICE_CHOOSE = "setup.ai_service.choose"
STATE_AI_SERVICE_CHOSEN = "setup.ai_service.chosen"
STATE_AI_SERVICE_STALE = "setup.ai_service.stale"
STATE_AI_SERVICE_INVALID = "setup.ai_service.invalid"
STATE_AI_SERVICE_CONFLICT = "setup.ai_service.conflict"
STATE_AI_SERVICE_NO_REQUEST = "setup.ai_service.no_request"

# Machine stale-reason tokens. The first four mirror onboarding.resume_view;
# route_removed and expired are chooser-specific projections.
STALE_ROUTE_REMOVED = "route_removed"
STALE_EXPIRED = "expired"


@dataclass(frozen=True)
class RouteOption:
    """One offered route as rendered by the chooser page."""

    kind: str
    label: str
    description: str
    recommended: bool


@dataclass(frozen=True)
class ChooserView:
    """Render-safe projection of the setup record for the chooser step."""

    state: str
    options: tuple[RouteOption, ...]
    recommended: str
    recommended_qualifier: str
    selected_route: str | None
    selected_label: str
    request_text: str
    revision: int
    step_index: int
    required_total: int
    can_choose: bool
    stale: bool
    stale_reasons: tuple[str, ...]
    expired: bool
    newer_version: bool


@dataclass(frozen=True)
class ChooseResult:
    """Outcome of one route submission: chosen, replayed, conflict, stale, invalid, or no_request."""

    kind: str
    setup: OnboardingSetup | None
    reason: str = ""


def route_options() -> tuple[RouteOption, ...]:
    """The three offered routes; exactly one carries the honest recommendation."""
    return tuple(
        RouteOption(kind=kind, label=ROUTE_LABELS[kind],
                    description=ROUTE_DESCRIPTIONS[kind],
                    recommended=kind == RECOMMENDED_ROUTE)
        for kind in ROUTE_KINDS
    )


def chooser_ready(setup: OnboardingSetup) -> bool:
    """The chooser needs a saved request to carry; it never creates one."""
    return bool(setup.request_text.strip())


def _chooser_stale_reasons(view, setup: OnboardingSetup) -> tuple[str, ...]:
    """Version/expiry reasons plus the chooser's own unknown-route reason."""
    reasons = list(view.stale_reasons)
    if setup.route_kind and setup.route_kind not in ROUTE_KINDS:
        reasons.append(STALE_ROUTE_REMOVED)
    if not reasons and view.expired:
        reasons.append(STALE_EXPIRED)
    return tuple(reasons)


def _blocks_choosing(reasons: tuple[str, ...]) -> bool:
    """An unknown old route is replaceable; version/expiry/step drift is not."""
    return any(reason != STALE_ROUTE_REMOVED for reason in reasons)


def _state_for(setup: OnboardingSetup, selected: str | None, reasons: tuple[str, ...]) -> str:
    if not chooser_ready(setup):
        return STATE_AI_SERVICE_NO_REQUEST
    if reasons:
        return STATE_AI_SERVICE_STALE
    if selected:
        return STATE_AI_SERVICE_CHOSEN
    return STATE_AI_SERVICE_CHOOSE


def chooser_view(
    setup: OnboardingSetup, *, now: datetime,
    active_requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
    active_contract_version: int = ONBOARDING_CONTRACT_VERSION,
) -> ChooserView:
    """Project a stored record for the chooser: choose, chosen, stale, or no-request."""
    view = resume_view(setup, now=now,
                       active_requirements_version=active_requirements_version,
                       active_contract_version=active_contract_version)
    options = route_options()
    selected = setup.route_kind if setup.route_kind in ROUTE_KINDS else None
    reasons = _chooser_stale_reasons(view, setup)
    state = _state_for(setup, selected, reasons)
    can_choose = state in (STATE_AI_SERVICE_CHOOSE, STATE_AI_SERVICE_STALE) and not _blocks_choosing(reasons)
    return ChooserView(
        state=state, options=options, recommended=RECOMMENDED_ROUTE,
        recommended_qualifier=RECOMMENDED_QUALIFIER,
        selected_route=selected,
        selected_label=ROUTE_LABELS[selected] if selected else "",
        request_text=setup.request_text, revision=setup.revision,
        step_index=view.step_index, required_total=view.required_total,
        can_choose=can_choose, stale=bool(reasons), stale_reasons=reasons,
        expired=view.expired, newer_version=view.newer_version,
    )


def _with_route(setup: OnboardingSetup, *, route: str, now: datetime,
                requirements_version: int, contract_version: int) -> OnboardingSetup:
    """The record a deliberate route choice writes: one revision bump, fresh TTL."""
    return setup.model_copy(update={
        "contract_version": contract_version,
        "revision": setup.revision + 1,
        "step": STEP_ORDER[1],
        "route_kind": route,
        "route_chosen_at": iso(now),
        "requirements_version": requirements_version,
        "resume_expires_at": iso(now + RESUME_TTL),
        "updated_at": iso(now),
    })


def choose_route(
    setup: OnboardingSetup, *, expected_revision: int, route_kind: str, now: datetime,
    requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
    contract_version: int = ONBOARDING_CONTRACT_VERSION,
) -> ChooseResult:
    """Decide one chooser submission against the current stored record.

    Returns chosen (persist the returned record), replayed (same route already
    selected; no write), conflict (different route from a revision the caller no
    longer holds; the returned record is current), stale (the record itself must
    be reviewed/re-saved first), invalid (fixable input), or no_request.
    """
    route = str(route_kind or "").strip()
    if route not in ROUTE_KINDS:
        return ChooseResult("invalid", setup, "Choose one of the three AI service routes.")
    if expected_revision < 0:
        return ChooseResult("invalid", setup, "Reload this page before choosing.")
    if not chooser_ready(setup):
        return ChooseResult("no_request", setup, "Write your request first.")
    view = resume_view(setup, now=now,
                       active_requirements_version=requirements_version,
                       active_contract_version=contract_version)
    reasons = list(view.stale_reasons)
    if view.expired and not reasons:
        reasons.append(STALE_EXPIRED)
    if reasons:
        return ChooseResult("stale", setup,
                            "This setup has changed since it was saved. Review it before choosing a route.")
    if route == setup.route_kind:
        return ChooseResult("replayed", setup, "This route was already selected.")
    if expected_revision != setup.revision:
        return ChooseResult("conflict", setup, "This setup changed in another window.")
    chosen = _with_route(setup, route=route, now=now,
                         requirements_version=requirements_version,
                         contract_version=contract_version)
    return ChooseResult("chosen", chosen)
