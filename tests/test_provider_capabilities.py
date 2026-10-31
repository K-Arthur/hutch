"""Tests for the evidence-backed capability registry (no network)."""

from __future__ import annotations

from hutch.providers.capabilities import (
    CAPABILITIES,
    LEVELS,
    SCOPE_KINDS,
    capability_matrix,
    capability_report,
    live_verified_evidence,
    report_json,
)


class _ObservationStore:
    def __init__(self, rows):
        self.rows = rows

    def model_capability_observations_for(self, provider, model, limit=20):
        return list(self.rows)


def test_every_requested_provider_has_a_report_and_documented_services():
    reports = capability_matrix()
    assert len(reports) == 62
    by_id = {report.provider_id: report for report in reports}
    openai = by_id["openai"]
    assert openai.level("text") == "documented"
    assert openai.level("image_generation") == "documented"
    assert openai.level("tool_calls") == "documented"
    # A provider that offers no media service must not inherit one from another provider.
    assert by_id["arcee"].level("image_generation") is None
    assert by_id["fal"].level("text") is None


def test_no_live_verified_evidence_exists_in_this_build():
    assert live_verified_evidence() == ()
    for report in capability_matrix():
        assert all(entry.level in LEVELS for entry in report.entries)
        assert all(entry.level != "live-verified" for entry in report.entries)
        assert all(entry.scope_kind in SCOPE_KINDS for entry in report.entries)
        assert all(entry.capability in CAPABILITIES for entry in report.entries)


def test_observed_evidence_is_model_scoped_and_never_upgrades_a_route_claim():
    store = _ObservationStore([
        {"capability": "function_tool_calls", "source_tool": "read_file",
         "observed_at": "2026-10-30T12:00:00Z"},
    ])
    report = capability_report("openai", model="gpt-4o", store=store)
    observed = [entry for entry in report.entries if entry.level == "observed"]
    assert len(observed) == 1
    assert observed[0].scope_kind == "model"
    assert observed[0].scope == "openai/gpt-4o"
    assert observed[0].capability == "tool_calls"
    assert report.level("tool_calls") == "observed"  # an owned-run observation outranks the route claim
    # Without a model, observations are not attributed to the provider in general.
    assert not [entry for entry in capability_report("openai", store=store).entries if entry.level == "observed"]


def test_unverified_capabilities_are_reported_not_called_unsupported():
    report = capability_report("mistral")
    assert "video_generation" in report.unverified()
    assert report.level("video_generation") is None
    assert report.unverified()


def test_report_json_is_serializable_and_lists_evidence_with_sources():
    body = report_json(capability_report("anthropic"))
    assert body["provider"] == "anthropic"
    assert body["levels"]["text"] == "documented"
    assert body["evidence"]
    assert all(item["source"] for item in body["evidence"])
    assert "secret" not in str(body).lower()
