"""Tool-schema keywords a host rejects are dropped from the wire copy only; local validation keeps them."""

from __future__ import annotations

import copy

from hutch.connections import ConnectionBook, load_templates
from hutch.providers.base import ChatRequest
from hutch.providers.connection import provider_for_connection
from hutch.providers.schema_trim import trim_tools

DROP = frozenset({"minLength", "maxLength", "minItems", "maxItems"})

TOOL = {"type": "function", "function": {
    "name": "note", "description": "Save a note.",
    "parameters": {
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 80},
            "tags": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 20}},
            "minLength": {"type": "integer", "description": "a property that is merely named like a keyword"},
            "mode": {"enum": ["maxLength", "minItems"], "type": "string"},
            "either": {"anyOf": [{"type": "string", "minLength": 2}, {"type": "null"}]},
        },
        "$defs": {"unit": {"type": "string", "maxLength": 3}},
    },
}}


def test_trim_removes_the_listed_keywords_at_every_schema_depth():
    trimmed = trim_tools([TOOL], DROP)[0]["function"]["parameters"]
    props = trimmed["properties"]
    assert props["title"] == {"type": "string"}
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert props["either"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert trimmed["$defs"]["unit"] == {"type": "string"}
    assert trimmed["required"] == ["title"]


def test_trim_keeps_property_names_and_enum_values_that_look_like_keywords():
    trimmed = trim_tools([TOOL], DROP)[0]["function"]["parameters"]["properties"]
    assert "minLength" in trimmed and trimmed["minLength"]["type"] == "integer"
    assert trimmed["mode"]["enum"] == ["maxLength", "minItems"]


def test_trim_never_mutates_the_canonical_schema():
    before = copy.deepcopy(TOOL)
    trim_tools([TOOL], DROP)
    assert TOOL == before


def test_trim_with_nothing_to_drop_returns_the_tools_unchanged():
    assert trim_tools([TOOL], frozenset()) == [TOOL]


def test_volcengine_declares_the_keywords_its_tool_api_rejects():
    declared = set(load_templates()["volcengine"]["tool_schema_unsupported_keywords"])
    assert {"minLength", "maxLength", "minItems", "maxItems", "minContains", "maxContains"} <= declared
    assert "tool_schema_unsupported_keywords" not in load_templates()["byteplus"], "no evidence for BytePlus"


def test_the_wire_body_omits_dropped_keywords_and_the_request_object_is_left_intact(tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
        book = ConnectionBook(tmp_path)
        book.add("volcengine", name="ark-test", base_url=f"{oai.url}/v1")
        provider = provider_for_connection(book, "ark-test", "some-endpoint")
        req = ChatRequest(model="some-endpoint", messages=[{"role": "user", "content": "hi"}], tools=[TOOL],
                          stream=False)
        provider.chat(req)
        sent = oai.of("/v1/chat/completions")[0]["body"]
        wire = sent["tools"][0]["function"]["parameters"]["properties"]["title"]
        assert wire == {"type": "string"}
        assert req.tools[0]["function"]["parameters"]["properties"]["title"]["minLength"] == 1
    finally:
        oai.close()


def test_a_template_without_the_declaration_sends_the_schema_unchanged(tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    try:
        monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
        book = ConnectionBook(tmp_path)
        book.add("groq", name="groq-test", base_url=f"{oai.url}/v1")
        provider = provider_for_connection(book, "groq-test", "some-model")
        provider.chat(ChatRequest(model="some-model", messages=[{"role": "user", "content": "hi"}], tools=[TOOL],
                                  stream=False))
        sent = oai.of("/v1/chat/completions")[0]["body"]
        assert sent["tools"][0]["function"]["parameters"]["properties"]["title"]["minLength"] == 1
    finally:
        oai.close()
