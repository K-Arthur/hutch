"""Role-specific model capability gates.

A model is not "workflow-capable". It is, at most, qualified for *one role* on *one exact
route revision*, for a *stated scope*, on a *date*. This module turns the evidence Hutch
already has - the versioned route profile, governed capability observations, and explicit
probe or operator records - into an explainable verdict, and it is the only place that
decides whether a role may run.

Evidence states (kept compatible with :mod:`hutch.toolcalling.profiles`):

``documented``  a versioned product document says so (not tested here);
``advertised``  a compatible endpoint is expected to behave that way (unverified);
``probed``      an explicit, bounded, held-out probe suite passed on this route revision;
``observed``    a governed Hutch run actually produced the capability on this revision;
``limited``     a local operator explicitly acknowledged a narrower scope, with a reason;
``unsupported`` the route is known *not* to provide it;
``stale``       evidence exists but was recorded for a different route revision;
``unknown``     no evidence.

Rules that matter and are enforced here:

* A **negative** evidence state (``unsupported``) blocks the capability; an unknown or
  advertised state allows it with an explicit caveat recorded in the verdict - Hutch's
  existing validation, receipts and bounded repair still apply at run time.
* ``author`` and ``selector`` require ``probed`` evidence (or an operator ``limited``
  acknowledgement, which permits a bounded worker/verifier scope only). Declared
  capability, connectivity, a tools flag or grammar-valid output are never enough.
* A verifier that would run on the same route as the producer is marked non-independent;
  only schema/artifact/command/human checks can then establish a verified outcome.
* Qualifications are keyed by the *same* route identity digest the runtime records
  observations under, so changing the connection, endpoint, template, quantization or
  backend invalidates them automatically - a stale record simply does not match.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..providers import parse_spec
from ..route_identity import route_revision, route_tuple
from ..toolcalling.profiles import resolve_profile, strategy_eligibility

ROLES = ("selector", "author", "worker", "verifier", "executor")
#: Roles that require explicit probed evidence before they may run at all.
PROBE_ONLY_ROLES = ("author", "selector")
#: Evidence states that count as positive support.
POSITIVE = ("documented", "probed", "observed")
CAVEAT_STATES = ("advertised", "unknown")

#: Providers the runtime can actually speak to. This is the same set the model catalog
#: offers, so a provider added there is never refused here as "no adapter".
from ..modelchoices import KNOWN_PROVIDERS


class QualificationBlocked(RuntimeError):
    """Raised by :func:`require` when a role may not run on this route."""

    def __init__(self, verdict: "RoleVerdict"):
        self.verdict = verdict
        super().__init__(verdict.summary())


@dataclass(frozen=True)
class RouteRef:
    spec: str
    provider: str
    model: str
    local: bool
    endpoint: str
    account_id: str
    revision: str

    def as_dict(self) -> dict[str, Any]:
        return {"spec": self.spec, "provider": self.provider, "model": self.model,
                "local": self.local, "endpoint": self.endpoint,
                "account_id": self.account_id, "revision": self.revision}


@dataclass(frozen=True)
class RoleVerdict:
    role: str
    state: str                     # qualified | caveated | limited | blocked
    allowed: bool
    reasons: tuple[str, ...]
    route: Optional[RouteRef]
    evidence: dict[str, Any] = field(default_factory=dict)
    tested_at: str = ""
    scope: dict[str, Any] = field(default_factory=dict)
    independent: Optional[bool] = None

    def summary(self) -> str:
        head = f"{self.role} on {self.route.spec if self.route else 'unknown route'}: {self.state}"
        return head + ("; " + "; ".join(self.reasons) if self.reasons else "")

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "state": self.state, "allowed": self.allowed,
                "reasons": list(self.reasons), "route": self.route.as_dict() if self.route else None,
                "evidence": self.evidence, "tested_at": self.tested_at, "scope": self.scope,
                "independent": self.independent}


def route_ref(spec: str, *, base_url: Optional[str] = None, connections: Any = None) -> RouteRef:
    """Resolve a model spec to the exact route identity used by authority and observations."""
    provider, model = parse_spec(spec)
    route = route_tuple(provider=provider, model=model, base_url=base_url, connections=connections)
    from ..providers.pricing import is_local_route

    return RouteRef(spec=spec, provider=provider, model=model,
                    local=bool(is_local_route(provider, model)),
                    endpoint=str(route[4]), account_id=str(route[1]),
                    revision=route_revision(route))


def _records(store: Any, route: RouteRef, role: str) -> list[dict[str, Any]]:
    if store is None or not hasattr(store, "role_qualifications"):
        return []
    return [r for r in store.role_qualifications(route.provider, route.model, route.revision)
            if r.get("role") == role]


def _observations(store: Any, route: RouteRef) -> list[dict[str, Any]]:
    if store is None or not hasattr(store, "model_capability_observations_for"):
        return []
    return store.model_capability_observations_for(route.provider, route.model, limit=20)


def assess(role: str, *, spec: str, store: Any = None, connections: Any = None,
           base_url: Optional[str] = None, requires_tools: bool = False,
           producer_spec: Optional[str] = None,
           requires_structured_output: bool = False,
           execution_profile_hash: Optional[str] = None) -> RoleVerdict:
    """Explain whether ``role`` may run on ``spec`` right now, and why."""
    if role not in ROLES:
        raise ValueError(f"unknown workflow role {role!r}")
    if role == "executor":
        return RoleVerdict(role=role, state="qualified", allowed=True,
                           reasons=("the deterministic interpreter is application-owned",),
                           route=None)

    try:
        route = route_ref(spec, base_url=base_url, connections=connections)
    except Exception as exc:
        return RoleVerdict(role=role, state="blocked", allowed=False,
                           reasons=(f"the route could not be resolved: {exc}",), route=None)
    if route.provider not in KNOWN_PROVIDERS and not (
            connections is not None and connections.get(route.provider)):
        return RoleVerdict(role=role, state="blocked", allowed=False,
                           reasons=(f"unknown provider {route.provider!r}: Hutch has no adapter for it",),
                           route=route)

    records = _records(store, route, role)
    probed = [r for r in records if r.get("state") == "probed"]
    limited = [r for r in records if r.get("state") == "limited"]
    negative = [r for r in records if r.get("state") in ("unsupported", "stale")]

    if role in PROBE_ONLY_ROLES:
        exact = [record for record in probed
                 if execution_profile_hash and record.get("execution_profile_hash") == execution_profile_hash]
        if exact:
            latest = exact[0]
            return RoleVerdict(role=role, state="qualified", allowed=True,
                               reasons=("all held-out checks passed on this exact route and execution profile",),
                               route=route, evidence={"records": len(probed)},
                               tested_at=str(latest.get("tested_at", "")),
                               scope=latest.get("scope") or {})
        reason = ("this role needs all held-out checks to pass on the exact route and execution profile; "
                  "the active model build/settings were not verified")
        if negative:
            exact_negative = [record for record in negative
                              if not execution_profile_hash
                              or record.get("execution_profile_hash") in ("", execution_profile_hash)]
            if exact_negative:
                reason = (f"evidence for this execution profile is negative: "
                          f"{exact_negative[0].get('reason') or exact_negative[0].get('state')}")
        elif probed and execution_profile_hash:
            reason = "held-out evidence exists for a different execution profile and is stale for this model setup"
        elif limited:
            reason = ("only a limited worker/verifier scope was acknowledged for this route; "
                      "authoring stays blocked until a probe passes")
        return RoleVerdict(role=role, state="blocked", allowed=False, reasons=(reason,),
                           route=route, evidence={"records": len(records)})

    # worker / verifier ------------------------------------------------------
    observations = _observations(store, route)
    profile = resolve_profile(provider=route.provider, endpoint=route.endpoint, model=route.model,
                              revision=route.revision, observations=observations)
    eligibility = strategy_eligibility(profile)
    native = profile.native_tools
    constrained_ok = eligibility["constrained"][0]

    reasons: list[str] = []
    state = "qualified"
    if requires_tools:
        if native.state == "unsupported":
            return RoleVerdict(role=role, state="blocked", allowed=False,
                               reasons=(f"this route does not support tool calls ({native.detail or 'unsupported'})",),
                               route=route, evidence={"native_tools": native.state})
        if native.state in POSITIVE:
            reasons.append(f"tool support is {native.state} on this route")
        elif native.state in CAVEAT_STATES and constrained_ok:
            reasons.append(f"tool support is {native.state}; {eligibility['constrained'][1]}")
            state = "caveated"
        elif constrained_ok:
            reasons.append("tool calls run through the documented schema-constrained control")
            state = "caveated"
        else:
            return RoleVerdict(role=role, state="blocked", allowed=False,
                               reasons=(f"tool support on this route is {native.state} and the backend "
                                        f"offers no documented schema-constrained control",),
                               route=route, evidence={"native_tools": native.state})
    else:
        if native.state in POSITIVE:
            reasons.append("text and tool support are documented for this route")
        else:
            reasons.append(f"no tools requested; route capability is {native.state}")
            state = "caveated" if native.state in CAVEAT_STATES else state

    if requires_structured_output:
        if profile.constrained_schema.supports:
            reasons.append("the output contract can be enforced by the backend's schema control")
        else:
            reasons.append("the output contract is validated locally after generation "
                           "(the route has no verified schema control)")

    if limited and state == "qualified":
        state = "limited"
        reasons.append("an operator acknowledged a narrower scope for this route")

    independent: Optional[bool] = None
    if role == "verifier":
        independent = True
        if producer_spec:
            try:
                producer = route_ref(producer_spec, base_url=base_url, connections=connections)
                if producer.revision == route.revision and producer.model == route.model:
                    independent = False
                    reasons.append("this verifier runs on the same route as the producer, so its "
                                   "review is advisory and cannot establish a verified outcome")
            except Exception:
                independent = None
    return RoleVerdict(role=role, state=state, allowed=True, reasons=tuple(reasons), route=route,
                       evidence={"native_tools": native.state,
                                 "constrained_schema": profile.constrained_schema.state,
                                 "observations": len(observations)},
                       scope={"tools": requires_tools, "structured_output": requires_structured_output},
                       independent=independent)


def require(role: str, **kwargs: Any) -> RoleVerdict:
    verdict = assess(role, **kwargs)
    if not verdict.allowed:
        raise QualificationBlocked(verdict)
    return verdict


def record_probe(store: Any, *, probe_run_id: str, base_url: Optional[str] = None) -> RoleVerdict:
    """Read qualification evidence produced by a completed, durable held-out probe run."""
    run = store.workflow_probe_run(probe_run_id) if hasattr(store, "workflow_probe_run") else None
    if run is None:
        raise ValueError("no durable probe run has that id")
    if run.get("status") != "passed":
        raise ValueError("only a completed passing probe can qualify a role")
    return assess(str(run["role"]), spec=f"{run['provider']}/{run['model']}", store=store,
                  base_url=base_url,
                  execution_profile_hash=str(run["execution_profile_hash"]))


def acknowledge_limited(store: Any, *, spec: str, role: str, reason: str, scope: dict[str, Any],
                        connections: Any = None, base_url: Optional[str] = None) -> RoleVerdict:
    """Record a local operator's explicit, scoped acknowledgement for worker/verifier use.

    This can never unlock ``author`` or ``selector``: those roles need a passed probe.
    """
    if role in PROBE_ONLY_ROLES:
        raise ValueError("a limited acknowledgement cannot qualify an author or selector role")
    if not reason.strip():
        raise ValueError("a limited acknowledgement requires a reason")
    route = route_ref(spec, base_url=base_url, connections=connections)
    store.record_role_qualification(
        provider=route.provider, model=route.model, route_revision=route.revision, role=role,
        state="limited", scope=scope, evidence={"acknowledged": True}, reason=reason,
        source="operator")
    return assess(role, spec=spec, store=store, connections=connections, base_url=base_url)


def revoke(store: Any, *, spec: str, role: str, connections: Any = None,
           base_url: Optional[str] = None) -> int:
    route = route_ref(spec, base_url=base_url, connections=connections)
    return store.delete_role_qualifications(route.provider, route.model, route.revision, role)
