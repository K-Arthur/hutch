"""The catalogue index: rows and filter facets come from the catalogue, never from page text."""

from __future__ import annotations

import pytest

from hutch.providers.catalog import INTEGRATION_STATUSES, SERVICE_TAGS, bundled_catalog
from hutch.providers.catalog_view import (AUTH_TYPE_LABELS, CODE_LABELS, SERVICE_LABELS, catalog_facets,
                                          catalog_rows, distinct_next_action, readiness_chip_class,
                                          resolution_view, route_chip_class, route_chips, status_chip_class)


@pytest.fixture(scope="module")
def catalog():
    return bundled_catalog()


def test_every_catalogue_provider_has_exactly_one_row(catalog):
    rows = catalog_rows(catalog, {})
    assert [row["id"] for row in rows] == [provider.id for provider in catalog.providers]
    assert all(row["href"] == f"/providers/{row['id']}" for row in rows)


def test_labels_cover_every_vocabulary_value(catalog):
    """A new service tag or auth type must get a person-readable label or this fails."""
    assert set(SERVICE_TAGS) <= set(SERVICE_LABELS)
    used = {method.type for provider in catalog.providers for method in provider.auth_methods}
    assert used <= set(AUTH_TYPE_LABELS)
    assert {status_chip_class(status) for status in INTEGRATION_STATUSES} == {
        "st-succeeded", "st-waiting_approval", "st-failed", "st-stopped"}


def test_a_route_is_labeled_built_only_when_the_code_path_exists(catalog):
    """Honest vocabulary: the route chip says built or not built, and never repeats the verified word."""
    assert CODE_LABELS["implemented"] == "built"
    assert CODE_LABELS["documented"] == "not built"
    assert "works" not in CODE_LABELS.values() and "verified" not in " ".join(CODE_LABELS.values())
    deepseek = next(p for p in catalog.providers if p.id == "deepseek")
    chips = route_chips(deepseek)
    assert chips and all(chip["code_label"] in set(CODE_LABELS.values()) for chip in chips)


def test_row_search_text_carries_title_services_status_and_routes(catalog):
    row = next(r for r in catalog_rows(catalog, {}) if r["id"] == "deepseek")
    for needle in ("deepseek", "chat", "api key", row["status_label"].lower()):
        assert needle in row["search"], needle
    assert row["search"] == row["search"].lower()


def test_account_counts_reach_the_rows(catalog):
    rows = {row["id"]: row for row in catalog_rows(catalog, {"openai": 2})}
    assert rows["openai"]["account_count"] == 2
    assert rows["deepseek"]["account_count"] == 0


def test_facets_list_only_values_that_exist_and_count_them(catalog):
    facets = catalog_facets(catalog)
    assert [item["id"] for item in facets["statuses"]] == [
        status for status in INTEGRATION_STATUSES
        if any(p.integration_status == status for p in catalog.providers)]
    assert sum(item["count"] for item in facets["statuses"]) == len(catalog.providers)
    assert {item["id"] for item in facets["auth_types"]} == {
        m.type for p in catalog.providers for m in p.auth_methods}
    assert all(item["count"] > 0 for key in facets for item in facets[key])
    chat = next(item for item in facets["services"] if item["id"] == "chat")
    assert chat["count"] == sum(1 for p in catalog.providers if "chat" in p.services)


def test_a_next_action_that_restates_the_detail_is_dropped_but_a_new_one_is_kept():
    detail = "No local credential found: set DEEPSEEK_API_KEY where Hutch starts, or store a key on Connections."
    repeat = "Set DEEPSEEK_API_KEY where Hutch starts, or store a key on the connection page."
    assert distinct_next_action(detail, detail) == ""
    assert distinct_next_action(detail, repeat) == ""
    kept = "Sign in again on Connections; Hutch kept the account record."
    assert distinct_next_action("The sign-in expired.", kept) == kept
    assert distinct_next_action(detail, "") == ""


def test_status_chip_classes_keep_unverified_apart_from_verified():
    assert status_chip_class("implemented") != status_chip_class("implemented-unverified")
    assert status_chip_class("blocked") == status_chip_class("retired")


def test_a_built_route_is_never_the_green_of_a_live_verified_provider():
    assert route_chip_class("implemented") not in ("st-succeeded",)
    assert status_chip_class("implemented") == "st-succeeded"
    assert route_chip_class("blocked") == "st-failed" and route_chip_class("experimental") == "st-waiting_approval"


def test_only_an_available_route_is_green_and_unknown_evidence_is_amber():
    from hutch.providers.readiness import STATES
    assert readiness_chip_class("available") == "st-succeeded"
    assert {state for state in STATES if readiness_chip_class(state) == "st-succeeded"} == {"available"}
    assert readiness_chip_class("capability_unverified") == "st-waiting_approval"
    assert readiness_chip_class("blocked_by_policy") == "st-failed"


def test_a_resolution_with_no_account_says_so_and_never_invents_one():
    view = resolution_view({"status": "needs_configuration", "billing": "unknown", "account": "", "spec": "x/y"})
    assert view["account_text"] == "no account chosen" and view["billing_label"] == "Billing not reported"
    assert view["chip_class"] == "st-stopped" and view["state_text"] == "needs configuration"
