"""The install name grammar, from the runtime's own parser and the real registry names.

The forms below were taken from Ollama's ``types/model/name.go`` and from the live pages
listed in ``docs/research/2026-11-offline-models/05-PHASE4-INSTALL.md`` (P4-3, P4-4). The
old validator refused six of ten of them because it only allowed lowercase.
"""

from __future__ import annotations

import pytest

from hutch.providers.model_install import validate_model_name
from hutch.providers.model_names import parse_model_name, same_model

_SHA = "sha256:" + "a" * 64


@pytest.mark.parametrize("raw,expected", [
    ("qwen3:4b", "qwen3:4b"),
    ("qwen3", "qwen3:latest"),
    ("Qwen3:4B", "Qwen3:4B"),
    ("library/qwen3:0.6b", "qwen3:0.6b"),
    ("registry.ollama.ai/library/qwen3:4b", "qwen3:4b"),
    ("llama3.2-vision:11b-instruct-q4_K_M", "llama3.2-vision:11b-instruct-q4_K_M"),
    ("qwen3:4b-instruct-2507-q4_K_M", "qwen3:4b-instruct-2507-q4_K_M"),
    ("hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M",
     "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M"),
    ("hf.co/unsloth/Qwen3-4B-GGUF:iq3_m", "hf.co/unsloth/Qwen3-4B-GGUF:iq3_m"),
    ("hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Llama-3.2-3B-Instruct-IQ3_M.gguf",
     "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Llama-3.2-3B-Instruct-IQ3_M.gguf"),
    ("huggingface.co/user/repo:q8_0", "huggingface.co/user/repo:q8_0"),
    ("localhost:5000/library/qwen3:4b", "localhost:5000/library/qwen3:4b"),
    ("myuser/mymodel:latest", "myuser/mymodel:latest"),
    (f"qwen3:4b@{_SHA}", f"qwen3:4b@{_SHA}"),
])
def test_real_names_are_accepted_and_defaults_are_dropped(raw, expected):
    assert validate_model_name(raw) == expected


def test_the_parsed_parts_match_the_runtime_shape():
    parsed = parse_model_name("hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M")
    assert (parsed.host, parsed.namespace, parsed.model, parsed.tag) == (
        "hf.co", "bartowski", "Llama-3.2-3B-Instruct-GGUF", "Q4_K_M")
    digest = parse_model_name(f"qwen3:4b@{_SHA}")
    assert digest.canonical() == f"qwen3:4b@{_SHA}"


@pytest.mark.parametrize("raw", [
    "", " ", "../evil", "a b", "model;rm -rf /", "host/ns/model/tag", "model:tag:extra",
    "-leading:tag", "ns.with.dot/model", "model:", ":4b", "model@sha256:abc",
    "x" * 601,
])
def test_malformed_names_are_refused(raw):
    with pytest.raises(ValueError):
        validate_model_name(raw)


@pytest.mark.parametrize("left,right", [
    ("qwen3", "qwen3:latest"),
    ("library/qwen3:4b", "qwen3:4b"),
    ("Qwen3:4B", "qwen3:4b"),
    ("registry.ollama.ai/library/qwen3:4b", "qwen3:4b"),
    (f"qwen3:4b@{_SHA}", "qwen3:4b"),
])
def test_equality_is_case_insensitive_and_namespace_aware(left, right):
    assert same_model(left, right)


def test_a_different_tag_or_namespace_is_a_different_model():
    assert not same_model("qwen3:4b", "qwen3:latest")
    assert not same_model("ns/qwen3:4b", "qwen3:4b")
    assert not same_model("hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M",
                          "hf.co/unsloth/Qwen3-4B-GGUF:Q5_K_M")


def test_an_unparsable_runtime_entry_does_not_break_duplicate_checks():
    assert same_model("Weird Name", "weird name")
    assert not same_model("Weird Name", "qwen3:4b")


def test_a_cloud_tag_is_refused_unless_the_caller_confirmed():
    with pytest.raises(ValueError, match="cloud model"):
        validate_model_name("gpt-oss:20b-cloud")
    assert validate_model_name("gpt-oss:20b-cloud", allow_cloud=True) == "gpt-oss:20b-cloud"
    assert validate_model_name("my-local-copy") == "my-local-copy:latest"


def test_the_full_hugging_face_filename_is_a_valid_tag():
    parsed = parse_model_name(
        "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Llama-3.2-3B-Instruct-IQ3_M.gguf")
    assert parsed.tag.endswith(".gguf")
