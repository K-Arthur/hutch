"""Role qualification contracts: evidence states, gating and invalidation.

These tests are offline and deterministic. They pin the rules that keep a workflow from
running a model in a role it has not earned: authoring needs probed evidence, a negative
evidence state blocks the capability, a same-route verifier is not independent, and
qualification records are keyed to the exact route revision so a route change invalidates
them.
"""
from __future__ import annotations

import pytest

from hutch.store import SCHEMA_VERSION
from hutch.workflow import qualify
from hutch.workflow.qualify import QualificationBlocked, assess, require


def test_schema_has_the_qualification_table(store):
    assert store.schema_version == SCHEMA_VERSION
    assert store.list_role_qualifications() == []


def test_executor_role_is_application_owned(store):
    verdict = assess("executor", spec="ollama/qwen3:4b", store=store)
    assert verdict.allowed and verdict.state == "qualified" and verdict.route is None


def test_author_and_selector_need_probed_evidence(store):
    for role in ("author", "selector"):
        verdict = assess(role, spec="ollama/qwen3:4b", store=store)
        assert not verdict.allowed and verdict.state == "blocked"
        assert "probed evidence" in verdict.reasons[0]
    # A limited acknowledgement can never unlock authoring.
    with pytest.raises(ValueError):
        qualify.acknowledge_limited(store, spec="ollama/qwen3:4b", role="author", reason="try it",
                                    scope={})


def test_probe_evidence_qualifies_authoring_for_the_exact_route_only(store):
    verdict = qualify.record_probe(store, spec="ollama/qwen3:4b", role="author", passed=True,
                                   scope={"families": ["fan-out", "branch"]},
                                   evidence={"scenarios": 6, "passed": 6})
    assert verdict.allowed and verdict.state == "qualified"
    # Same model, different route revision (e.g. a different endpoint) is not qualified.
    other = assess("author", spec="ollama/qwen3:4b", store=store, base_url="http://elsewhere:11434")
    assert not other.allowed
    # Revocation is explicit.
    assert qualify.revoke(store, spec="ollama/qwen3:4b", role="author") == 1
    assert not assess("author", spec="ollama/qwen3:4b", store=store).allowed


def test_failed_probe_records_negative_evidence_and_blocks(store):
    verdict = qualify.record_probe(store, spec="ollama/qwen3:4b", role="selector", passed=False,
                                   scope={}, evidence={"scenarios": 4, "passed": 1},
                                   reason="abstention failed on two held-out cases")
    assert not verdict.allowed
    assert "negative" in verdict.reasons[0]
    rows = store.role_qualifications("ollama", "qwen3:4b")
    assert rows[0]["state"] == "unsupported" and "abstention" in rows[0]["reason"]


def test_worker_uses_documented_local_tool_evidence(store):
    verdict = assess("worker", spec="ollama/qwen3:4b", store=store, requires_tools=True)
    assert verdict.allowed
    assert verdict.state in ("qualified", "caveated")
    assert verdict.evidence["native_tools"] == "documented"
    assert any("tool support" in reason for reason in verdict.reasons)


def test_worker_without_tools_is_allowed_but_caveated_on_unknown_routes(store):
    verdict = assess("worker", spec="ollama/cloud-tagged-model", store=store)
    assert verdict.allowed and verdict.state == "caveated"
    assert verdict.evidence["native_tools"] in ("unknown", "advertised")


def test_anthropic_worker_with_tools_is_allowed_via_native_documentation(store):
    verdict = assess("worker", spec="anthropic/claude-sonnet-4-5", store=store, requires_tools=True)
    assert verdict.allowed
    assert verdict.evidence["native_tools"] == "documented"


def test_operator_acknowledgement_qualifies_a_bounded_worker_scope(store):
    verdict = qualify.acknowledge_limited(store, spec="ollama/qwen3:4b", role="worker",
                                          reason="small local model, text-only extraction only",
                                          scope={"tools": False, "max_steps": 4})
    assert verdict.allowed and verdict.state == "limited"
    rows = store.role_qualifications("ollama", "qwen3:4b")
    assert rows[0]["state"] == "limited" and rows[0]["source"] == "operator"


def test_verifier_independence_is_reported(store):
    same = assess("verifier", spec="ollama/qwen3:4b", store=store, requires_tools=False,
                  producer_spec="ollama/qwen3:4b")
    assert same.allowed and same.independent is False
    other = assess("verifier", spec="ollama/qwen3:4b", store=store, requires_tools=False,
                   producer_spec="anthropic/claude-sonnet-4-5")
    assert other.independent is True


def test_unresolvable_route_is_blocked_with_a_reason(store):
    verdict = assess("worker", spec="definitely-not-a-provider/model", store=store)
    assert not verdict.allowed
    assert "unknown provider" in verdict.reasons[0]


def test_require_raises_a_structured_block(store):
    with pytest.raises(QualificationBlocked) as info:
        require("author", spec="ollama/qwen3:4b", store=store)
    assert info.value.verdict.role == "author"
    assert "author on ollama/qwen3:4b" in str(info.value)


def test_observation_matching_is_route_scoped(store):
    # No observations for this route yet: the verdict says so honestly.
    verdict = assess("worker", spec="ollama/qwen3:4b", store=store, requires_tools=True)
    assert verdict.evidence["observations"] == 0
    assert store.model_capability_observations_for("ollama", "qwen3:4b") == []


def test_qualification_records_validate_their_inputs(store):
    with pytest.raises(ValueError):
        store.record_role_qualification(provider="ollama", model="m", route_revision="short",
                                        role="worker", state="probed", source="probe")
    with pytest.raises(ValueError):
        store.record_role_qualification(provider="ollama", model="m", route_revision="a" * 64,
                                        role="executor", state="probed", source="probe")
    with pytest.raises(ValueError):
        store.record_role_qualification(provider="ollama", model="m", route_revision="a" * 64,
                                        role="worker", state="guessed", source="probe")
    with pytest.raises(ValueError):
        store.record_role_qualification(provider="ollama", model="m", route_revision="a" * 64,
                                        role="worker", state="probed", source="probe",
                                        evidence={"blob": "x" * 9_000})
