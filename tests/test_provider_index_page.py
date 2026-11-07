"""The Providers index as served: one row per provider, honest chips, no script needed to read it."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.providers.catalog import bundled_catalog
from hutch.server.app import create_app


@pytest.fixture()
def state(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(directory))
    with TestClient(create_app()) as client:
        yield client, directory


def _rows(html: str) -> list[re.Match]:
    return list(re.finditer(r'<li class="provider-row" data-provider-card data-id="([^"]+)"([^>]*)>', html))


def test_every_provider_is_one_row_linking_to_its_detail_page(state):
    client, _ = state
    html = client.get("/providers").text
    ids = [match.group(1) for match in _rows(html)]
    assert ids == [p.id for p in bundled_catalog().providers] or sorted(ids) == sorted(
        p.id for p in bundled_catalog().providers)
    assert len(ids) == len(set(ids)) == len(bundled_catalog().providers)
    for provider_id in ids:
        assert f'href="/providers/{provider_id}"' in html


def test_the_green_works_chip_belongs_only_to_live_verified_providers(state):
    """Status honesty on the index: only a provider with a dated live run may read as working."""
    client, _ = state
    html = client.get("/providers").text
    catalogue = html[html.index('id="catalogue"'):]
    green = re.findall(r'<span class="chip st-succeeded" title="[^"]*">([^<]+)</span>', catalogue)
    implemented = [p for p in bundled_catalog().providers if p.integration_status == "implemented"]
    assert green and set(green) == {"works"} and len(green) == len(implemented)


def test_filters_are_hidden_until_script_runs_and_the_list_is_complete_without_it(state):
    client, _ = state
    html = client.get("/providers").text
    assert re.search(r'<form class="provider-filters" id="provider-filters"[^>]*\bhidden\b', html)
    assert "Filtering needs JavaScript. Every provider is listed below." in html
    assert 'role="status"' in html and "Showing all 64 providers." in html


def test_filter_options_carry_counts_from_the_catalogue(state):
    client, _ = state
    html = client.get("/providers").text
    total = len(bundled_catalog().providers)
    assert re.search(rf'<option value="implemented">[^<]*\(3\)</option>', html)
    assert f"Provider catalogue ({total})" in html
    for facet in ("filter-category", "filter-status", "filter-auth", "filter-service"):
        assert f'id="{facet}"' in html


def test_an_account_shows_its_detail_once_not_the_same_instruction_twice(state):
    client, directory = state
    book = ConnectionBook(directory)
    book.add("openai-api", "openai-api")
    html = client.get("/providers").text
    assert html.count("No local credential found: set OPENAI_API_KEY where Hutch starts") == 1
    assert "store a key on the connection page" not in html


def test_the_page_never_carries_a_stored_key_and_links_each_account_to_its_provider(state):
    client, directory = state
    book = ConnectionBook(directory)
    book.add("deepseek", "deepseek-work")
    book.set_key("deepseek-work", "sk-index-page-placeholder")
    html = client.get("/providers").text
    assert "sk-index-page-placeholder" not in html
    assert re.search(r'<h3 class="card-title"><a href="/providers/deepseek">DeepSeek</a>', html)
