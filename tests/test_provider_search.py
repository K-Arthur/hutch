"""Provider-native web search: route declaration, request body and reply parsing.

NO NETWORK. The wire rules are pure; the one transport-facing check feeds the vendor's own
observed refusal body through ``_error_from_response`` with a constructed response.
"""

from __future__ import annotations

import pytest

from hutch.connections import load_templates
from hutch.providers.search import (MAX_QUERY_CHARS, SearchError, build_payload,
                                    parse_search_response, route_from_template)
from tests.test_search_support import OBSERVED_SEARCH_RESPONSE, observed, no_usage, template

def no_usage(body: dict) -> dict:
    body["usage"].pop("web_search_usage", None)
    return body


# ---------------------------------------------------------------- route


def test_the_route_reads_the_declared_block():
    route = route_from_template(template())
    assert route is not None
    assert route.model == "mimo-v2.6-flash"
    assert (route.max_keyword, route.results_per_keyword, route.force_search) == (2, 1, True)


def test_a_connection_without_a_search_block_offers_no_route():
    assert route_from_template({}) is None
    assert route_from_template(None) is None


@pytest.mark.parametrize("bad", [
    {"protocol": "openai-chat"},
    {"model": ""},
    {"max_keyword": 0},
    {"max_keyword": 99},
    {"results_per_keyword": 0},
    {"results_per_keyword": 99},
    {"force_search": "yes"},
    {"source": "http://not-https.test/search"},
])
def test_a_malformed_search_block_is_loud(bad):
    with pytest.raises(ValueError):
        route_from_template(template(**bad))


# ---------------------------------------------------------------- payload


def test_the_payload_declares_the_provider_tool_and_its_cost_caps():
    route = route_from_template(template())
    payload = build_payload(route, "  Wuhan weather tomorrow  ")
    assert payload["model"] == "mimo-v2.6-flash"
    assert payload["messages"] == [{"role": "user", "content": "Wuhan weather tomorrow"}]
    assert payload["tools"] == [{"type": "web_search", "max_keyword": 2,
                                 "force_search": True, "limit": 1}]
    assert payload["tool_choice"] == "auto"


def test_an_empty_or_oversized_query_is_refused_before_a_request():
    route = route_from_template(template())
    with pytest.raises(SearchError, match="no query"):
        build_payload(route, "   ")
    with pytest.raises(SearchError, match="at most"):
        build_payload(route, "x" * (MAX_QUERY_CHARS + 1))


# ---------------------------------------------------------------- parsing


def test_citations_usage_and_the_answer_are_parsed_from_the_documented_shape():
    route = route_from_template(template())
    result = parse_search_response(OBSERVED_SEARCH_RESPONSE, route)
    assert result.answer.startswith("Wuhan tomorrow")
    assert [c.site_name for c in result.citations] == ["weather.com.cn", "qweather.com"]
    assert result.citations[0].published.startswith("2026-09-21")
    assert (result.prompt_tokens, result.completion_tokens) == (1476, 60)
    assert (result.search_calls, result.page_usage) == (3, 3)
    assert result.searched is True


def test_an_empty_answer_is_a_failure_not_an_empty_success():
    route = route_from_template(template())
    body = observed()
    body["choices"][0]["message"]["content"] = "   "
    with pytest.raises(SearchError, match="no answer"):
        parse_search_response(body, route)


def test_missing_search_usage_is_reported_as_unknown_not_as_zero():
    route = route_from_template(template())
    result = parse_search_response(no_usage(observed()), route)
    assert result.search_calls is None
    assert any("unknown (not zero)" in note for note in result.notes)


def test_an_answer_without_citations_or_search_usage_says_it_was_not_grounded():
    route = route_from_template(template())
    body = no_usage(observed())
    body["choices"][0]["message"]["annotations"] = None
    result = parse_search_response(body, route)
    assert result.searched is False
    assert any("not grounded in a web search" in note for note in result.notes)


def test_a_model_that_decided_not_to_search_is_not_dressed_up_as_grounded():
    """The vendor documents this: the model may judge the query needs no search."""
    route = route_from_template(template())
    body = observed()
    body["choices"][0]["message"]["annotations"] = []
    body["usage"]["web_search_usage"] = {"tool_usage": 0, "page_usage": 0}
    result = parse_search_response(body, route)
    assert result.searched is False
    assert any("not grounded" in note for note in result.notes)


def test_annotation_types_hutch_does_not_understand_are_counted_not_dropped_silently():
    route = route_from_template(template())
    body = observed()
    body["choices"][0]["message"]["annotations"].append({"type": "video_citation",
                                                        "url": "https://example.test/v"})
    result = parse_search_response(body, route)
    assert result.dropped_annotations == 1
    assert any("not usable url_citation" in note for note in result.notes)


@pytest.mark.parametrize("bad_url", [
    "javascript:alert(1)",
    "data:text/html,<script>",
    "file:///etc/passwd",
    "not a url",
    "",
])
def test_a_citation_url_that_is_not_http_is_never_reported(bad_url):
    route = route_from_template(template())
    body = observed()
    body["choices"][0]["message"]["annotations"] = [{"type": "url_citation", "url": bad_url}]
    result = parse_search_response(body, route)
    assert result.citations == ()
    assert result.dropped_annotations == 1


def test_a_substituted_model_is_reported():
    route = route_from_template(template())
    result = parse_search_response(observed(model="mimo-v2.6-pro"), route)
    assert result.substituted_model is True
    assert any("mimo-v2.6-pro" in note for note in result.notes)


def test_a_length_finish_reason_says_the_answer_may_be_truncated():
    route = route_from_template(template())
    body = observed()
    body["choices"][0]["finish_reason"] = "length"
    result = parse_search_response(body, route)
    assert any("truncated" in note for note in result.notes)
