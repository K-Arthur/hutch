"""Focused tests for the cached tool-argument validation path (perf programme D6-A).

The invariant is equality with the canonical ``validate_call``; the cache is only a
performance mechanism. These tests also pin the identity-cache preconditions: registered
tool schemas are treated as immutable, the cache is bounded, and it still yields the
identical refusal text with or without the optional ``jsonschema`` package.
"""

from __future__ import annotations

import gc
import threading

import pytest

import hutch.toolcalling.validate as validation
from hutch.toolcalling.schema_analysis import analysis_cache_info, clear_analysis_cache
from hutch.toolcalling.validate import (
    clear_validation_cache,
    validate_call,
    validate_tool_call_cached,
    validation_cache_info,
)


def _catalog_schemas() -> dict[str, dict]:
    from hutch.tools import _CATALOG
    return {name: cls().parameters for name, cls in sorted(_CATALOG.items())}


def _corpus() -> list[tuple[str, object]]:
    """Representative valid, empty, wrong-typed and nested argument shapes."""
    return [
        ("shell", {"command": "ls -la"}),
        ("shell", {}),
        ("shell", {"command": 42}),
        ("read_file", {"path": "notes/a.md"}),
        ("read_file", {"path": "notes/a.md", "offset": "x"}),
        ("write_file", {"path": "out/a.md", "content": "# title\n"}),
        ("write_file", {"path": "out/a.md", "content": None}),
        ("remember", {"key": "k", "value": "v"}),
        ("create_document", {"format": "xlsx", "filename": "x.xlsx", "title": "t", "content": {}}),
        ("create_document", {"format": "odt", "filename": "x", "title": "t", "content": {}}),
        ("run_python", {"code": "print(1)"}),
        ("run_python", {"code": ["nope"]}),
        ("list_files", {"path": "reports"}),
        ("list_files", {"path": 7}),
        ("reset_workspace", {}),
    ]


@pytest.fixture(autouse=True)
def _clean_caches():
    clear_analysis_cache()
    clear_validation_cache()
    yield
    clear_analysis_cache()
    clear_validation_cache()


def test_cached_path_is_identical_to_canonical_validation_for_the_catalog():
    schemas = _catalog_schemas()
    for name, args in _corpus():
        expected = validate_call(schemas[name], args)
        actual = validate_tool_call_cached(schemas[name], args)
        assert actual == expected, f"{name} {args!r}: {actual!r} != {expected!r}"


def test_cached_path_matches_uncached_for_every_schema_and_argument_shape():
    schemas = _catalog_schemas()
    arguments: list[object] = [{}, {"unexpected": True}, {"command": "ls"}, "not-an-object", None]
    for name, schema in schemas.items():
        for args in arguments:
            assert validate_tool_call_cached(schema, args) == validate_call(schema, args)


def test_repeated_calls_reuse_static_analysis():
    schema = _catalog_schemas()["shell"]
    args = {"command": "ls -la"}
    assert validate_tool_call_cached(schema, args) == []
    first = analysis_cache_info()
    assert first["misses"] == 1
    for _ in range(5):
        assert validate_tool_call_cached(schema, args) == []
    info = analysis_cache_info()
    assert info["size"] == 1 and info["hits"] >= 5


def test_compiled_validator_is_reused_across_calls(monkeypatch):
    if not validation._HAVE_JSONSCHEMA:
        pytest.skip("optional jsonschema package is not installed")
    schema = _catalog_schemas()["shell"]
    constructions = []
    real = validation._Draft202012Validator

    def counting(candidate):
        constructions.append(candidate)
        return real(candidate)

    monkeypatch.setattr(validation, "_Draft202012Validator", counting)
    for _ in range(3):
        assert validate_tool_call_cached(schema, {"command": "ls"}) == []
    assert len(constructions) == 1
    assert validation_cache_info()["size"] == 1


def test_bounded_analysis_cache_evicts_old_entries():
    for index in range(300):
        validate_tool_call_cached({"type": "object", "properties": {"x": {"type": "integer"}}}, {"x": index})
    assert analysis_cache_info()["size"] <= 128


def test_cache_holds_the_schema_strongly_so_a_identity_cannot_be_recycled():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    assert validate_tool_call_cached(schema, {"n": 1}) == []
    del schema
    gc.collect()
    assert analysis_cache_info()["size"] == 1
    clear_analysis_cache()
    assert analysis_cache_info()["size"] == 0


def test_unsupported_schema_refusal_text_is_unchanged():
    schema = {"type": "object", "patternProperties": {"^x": {"type": "string"}}}
    assert validate_tool_call_cached(schema, {"x": "v"}) == validate_call(schema, {"x": "v"})
    assert validate_tool_call_cached(schema, {"x": "v"})


def test_cached_path_fails_closed_without_the_optional_jsonschema_package(monkeypatch):
    monkeypatch.setattr(validation, "_HAVE_JSONSCHEMA", False)
    clear_validation_cache()
    schema = _catalog_schemas()["shell"]
    assert validation_cache_info()["size"] == 0
    assert validate_tool_call_cached(schema, {"command": "ls"}) == []
    assert validate_tool_call_cached(schema, {"command": 7})
    assert validation_cache_info()["size"] == 0, "no validator should be compiled without the package"


def test_cache_is_consistent_under_concurrent_validation():
    schema = _catalog_schemas()["shell"]
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(50):
                assert validate_tool_call_cached(schema, {"command": "ls"}) == []
                assert validate_tool_call_cached(schema, {"command": 7})
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    assert analysis_cache_info()["size"] == 1
