"""The catalogue, the route table and the docs must say the same thing about media (Phase 6).

A catalogue row is a support claim a person reads. These tests fail when a status rises above what
the route table can back, or when a retired route is not explained where people look.
"""

from __future__ import annotations

import pytest

from hutch.media.providers.route_spec import BUILDABLE, load_routes
from hutch.providers.catalog import bundled_catalog

ROUTES = load_routes()
SERVICE_FOR_KIND = {"image": "images", "video": "video", "audio": "speech"}


@pytest.fixture(scope="module")
def catalogue():
    return bundled_catalog()


def test_every_buildable_route_has_a_catalogue_provider_that_offers_the_service(catalogue):
    for route in ROUTES.values():
        if not route.buildable:
            continue
        provider = catalogue.require(route.provider)
        assert SERVICE_FOR_KIND[route.kind] in provider.services, route.id
        assert provider.integration_status == BUILDABLE, (
            f"{route.id}: the route is protocol-tested only, so {provider.id} may not claim more")


def test_no_provider_claims_a_media_service_through_a_route_that_is_only_documented(catalogue):
    """Providers whose only route for a kind is documented or retired must say so in their notes."""
    for route in ROUTES.values():
        if route.buildable:
            continue
        provider = catalogue.require(route.provider)
        notes = (provider.notes or "").lower()
        if route.status == "retired":
            assert route.retired_on in (provider.notes or ""), (
                f"{route.id} retired on {route.retired_on} but {provider.id} notes do not say when")
        if route.status == "documented" and provider.integration_status == BUILDABLE:
            assert "not built" in notes or "documented" in notes or "documented only" in notes, (
                f"{provider.id} is implemented-unverified; its notes must say {route.id} is not built")


def test_the_route_table_names_only_providers_the_catalogue_knows(catalogue):
    known = {p.id for p in catalogue.providers}
    assert {route.provider for route in ROUTES.values()} <= known


def test_env_credentialed_routes_are_not_given_a_connection_template_they_do_not_have(catalogue):
    for route in ROUTES.values():
        if route.buildable and route.env_var:
            assert not catalogue.require(route.provider).connection_templates, route.id
