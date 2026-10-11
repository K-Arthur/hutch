"""The typed output-block contract (src/hutch/outputblocks.py).

Golden fixtures in tests/fixtures/blocks/ are the lanes' canonical examples:
every valid fixture must parse, serialize stably, and re-parse to itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hutch.outputblocks import (BLOCK_SCHEMA_VERSION, KNOWN_BLOCK_KINDS, MAX_BLOCK_JSON_CHARS,
                                MAX_BLOCKS_PER_RESULT, OutputBlock, block_json_chars, new_block_id,
                                new_media_id, parse_blocks, serialize_block)

FIXTURES = Path(__file__).parent / "fixtures" / "blocks"
VALID_FIXTURES = sorted(p for p in FIXTURES.glob("*.json") if p.name != "invalid.json")


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def text_block(content: str, *, id_hex: str = "1111111111111111", **overrides) -> dict:
    block = {
        "v": BLOCK_SCHEMA_VERSION, "id": f"blk_{id_hex}", "kind": "text", "revision": 1,
        "availability": "ready", "text_fallback": "readable fallback",
        "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
        "payload": {"content": content},
    }
    block.update(overrides)
    return block


# ------------------------------------------------------------- golden fixtures


@pytest.mark.parametrize("path", VALID_FIXTURES, ids=[p.stem for p in VALID_FIXTURES])
def test_every_valid_fixture_parses_and_serializes_stably(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    blocks, errors = parse_blocks([raw])
    assert errors == [], f"{path.name} must be valid: {errors}"
    assert len(blocks) == 1
    again, second_errors = parse_blocks(blocks)
    assert second_errors == []
    assert again == blocks, "serialization must be a fixed point of parsing"


def test_the_invalid_fixture_is_rejected_with_one_labeled_error():
    raw = load("invalid")
    blocks, errors = parse_blocks([raw])
    assert blocks == []
    assert len(errors) == 1
    assert errors[0]["kind"] == "chart" and "id" in errors[0] and errors[0]["error"]


def test_every_known_kind_has_a_fixture():
    covered = {p.stem for p in VALID_FIXTURES}
    assert covered == set(KNOWN_BLOCK_KINDS)


def test_fixture_examples_are_all_schema_v1():
    for path in VALID_FIXTURES:
        assert json.loads(path.read_text(encoding="utf-8"))["v"] == BLOCK_SCHEMA_VERSION == 1


# ------------------------------------------------------- round trip and shapes


def test_new_ids_match_the_contract_shapes():
    assert new_block_id().startswith("blk_") and len(new_block_id()) == 20
    assert new_media_id().startswith("media_") and len(new_media_id()) == 22


def test_serialized_blocks_are_json_ready_and_compact():
    blocks, errors = parse_blocks([load("code_receipt")])
    assert errors == []
    encoded = json.dumps(blocks, ensure_ascii=False, separators=(",", ":"))
    reparsed = json.loads(encoded)
    assert reparsed == blocks
    assert block_json_chars(blocks[0]) == len(json.dumps(blocks[0], ensure_ascii=False, separators=(",", ":")))
    assert len(encoded) == block_json_chars(blocks[0]) + 2  # + the wrapping brackets of the list


def test_optional_fields_stay_absent_not_null():
    blocks, _ = parse_blocks([load("status")])
    assert "error" not in json.dumps(blocks)  # no nulls leaking into the event data


def test_round_trip_preserves_flowchart_from_alias():
    blocks, errors = parse_blocks([load("flowchart")])
    assert errors == []
    edges = blocks[0]["payload"]["edges"]
    assert all("from" in edge and "from_id" not in edge for edge in edges)


# ------------------------------------------------------------- rejections


def test_unknown_kind_degrades_to_a_labeled_fallback_error():
    raw = load("text")
    raw["kind"] = "slideshow"
    blocks, errors = parse_blocks([raw])
    assert blocks == []
    assert errors[0]["id"] == raw["id"] and errors[0]["kind"] == "slideshow"
    assert "unknown block kind" in errors[0]["error"]


def test_unknown_schema_version_is_labeled_not_crashed():
    raw = load("text")
    raw["v"] = 999
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "unsupported block schema version 999" in errors[0]["error"]


def test_missing_schema_version_is_labeled():
    raw = load("text")
    del raw["v"]
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "missing the required schema version" in errors[0]["error"]


@pytest.mark.parametrize("fallback", ["", "   ", None])
def test_text_fallback_is_required_and_must_be_readable(fallback):
    raw = load("text")
    if fallback is None:
        del raw["text_fallback"]
    else:
        raw["text_fallback"] = fallback
    blocks, errors = parse_blocks([raw])
    assert blocks == []
    assert errors and "text_fallback" in errors[0]["error"]


def test_text_fallback_over_4000_chars_is_rejected():
    raw = load("text")
    raw["text_fallback"] = "x" * 4001
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "4000" in errors[0]["error"]


@pytest.mark.parametrize("id_hex", ["blk_NOPE", "blk_1a2b3c4d5e6f7a8", "blk_1A2B3C4D5E6F7A8B", "doc_1a2b3c4d5e6f7a8b"])
def test_envelope_id_shape_is_enforced(id_hex):
    blocks, errors = parse_blocks([text_block("hi", id_hex=id_hex.removeprefix("blk_"))])
    assert blocks == [] and errors


def test_bad_revision_availability_and_extra_fields_are_rejected():
    for mutation in ({"revision": 0}, {"revision": True}, {"availability": "eventually"}, {"surprise": 1}):
        blocks, errors = parse_blocks([text_block("hi", **mutation)])
        assert blocks == [] and errors, mutation


def test_non_list_and_non_object_inputs_never_raise():
    for bad_input in (None, "text", 42, {"blocks": True}, [42], ["{}"], [[]]):
        blocks, errors = parse_blocks(bad_input)
        assert blocks == [] and errors


def test_empty_block_list_is_valid_and_empty():
    assert parse_blocks([]) == ([], [])


def test_code_receipt_hash_binding_rejects_a_drifted_source():
    raw = load("code_receipt")
    raw["payload"]["source"] = raw["payload"]["source"] + "# edited after execution\n"
    blocks, errors = parse_blocks([raw])
    assert blocks == []
    assert "source_sha256" in errors[0]["error"]


def test_code_receipt_over_100k_chars_is_rejected():
    big = "x" * 100_001
    raw = load("code_receipt")
    raw["payload"]["source"] = big
    raw["payload"]["source_sha256"] = hashlib.sha256(big.encode()).hexdigest()
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "100000" in errors[0]["error"]


def test_table_row_total_must_cover_the_rows_present():
    raw = load("table")
    raw["payload"]["row_total"] = 1
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "row_total" in errors[0]["error"]


def test_table_rows_are_capped_at_500():
    raw = load("table")
    raw["payload"]["rows"] = [["x", 1]] * 501
    raw["payload"]["row_total"] = 501
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and errors


def test_flowchart_accepts_cycles_but_not_dangling_edges():
    raw = load("flowchart")
    assert parse_blocks([raw])[1] == []                       # fixture already contains a cycle
    dangling = load("flowchart")
    dangling["payload"]["edges"].append({"from": "collect", "to": "ghost"})
    blocks, errors = parse_blocks([dangling])
    assert blocks == [] and "ghost" in errors[0]["error"]


def test_comparison_cells_need_exactly_one_of_value_or_state():
    base = load("comparison")
    both = json.loads(json.dumps(base))
    both["payload"]["cells"][0]["state"] = "unknown"
    neither = json.loads(json.dumps(base))
    del neither["payload"]["cells"][0]["value"]
    for raw in (both, neither):
        blocks, errors = parse_blocks([raw])
        assert blocks == [] and "exactly one of value or state" in errors[0]["error"]


def test_comparison_cells_reference_declared_axes():
    raw = load("comparison")
    raw["payload"]["cells"][0]["item"] = "ghost"
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "ghost" in errors[0]["error"]


def test_timeline_rejects_unparseable_timestamps():
    raw = load("timeline")
    raw["payload"]["events"][0]["when"]["iso8601"] = "sometime last week"
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "iso8601" in errors[0]["error"]


def test_media_requires_mime_enum_alt_text_and_media_id_shape():
    raw = load("media")
    bad_mime = json.loads(json.dumps(raw))
    bad_mime["payload"]["mime"] = "image/gif"
    blank_alt = json.loads(json.dumps(raw))
    blank_alt["payload"]["alt_text"] = "  "
    bad_id = json.loads(json.dumps(raw))
    bad_id["payload"]["media_id"] = "media_XYZZY"
    for probe in (bad_mime, blank_alt, bad_id):
        blocks, errors = parse_blocks([probe])
        assert blocks == [] and errors, probe["payload"]["mime"]


def test_artifact_ref_prefix_must_match_ref_kind():
    raw = load("artifact_ref")
    raw["payload"]["id"] = "media_0f1e2d3c4b5a6978"
    blocks, errors = parse_blocks([raw])
    assert blocks == [] and "media_" in errors[0]["error"]


# --------------------------------------------------------------------- budgets


def test_block_budget_keeps_the_first_24_and_reports_the_rest():
    many = [text_block(f"block {n}", id_hex=f"{n:016x}") for n in range(30)]
    blocks, errors = parse_blocks(many)
    assert len(blocks) == MAX_BLOCKS_PER_RESULT == 24
    assert len(errors) == 6 and all("budget exceeded" in e["error"] for e in errors)
    assert [b["id"] for b in blocks] == [f"blk_{n:016x}" for n in range(24)]


def test_json_char_budget_downgrades_overflow_to_an_error_entry():
    # each code_receipt serializes to ~100k chars, so the third breaks the 256k budget
    source = "x" * 90_000
    raw = load("code_receipt")
    raw["payload"]["source"] = source
    raw["payload"]["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    entries = []
    for n in range(3):
        probe = json.loads(json.dumps(raw))
        probe["id"] = f"blk_{n:016x}"
        entries.append(probe)
    blocks, errors = parse_blocks(entries)
    assert len(blocks) == 2 and len(errors) == 1
    assert "compact-JSON characters" in errors[0]["error"]
    total = sum(block_json_chars(b) for b in blocks)
    assert total <= MAX_BLOCK_JSON_CHARS


def test_error_entries_are_bounded_for_a_hostile_input():
    entries = [{"kind": f"nope-{n}"} for n in range(500)]
    blocks, errors = parse_blocks(entries)
    assert blocks == []
    assert len(errors) <= MAX_BLOCKS_PER_RESULT + 2
    assert any("suppressed" in e["error"] or "were not examined" in e["error"] for e in errors)


def test_enormous_input_is_not_examined_entry_by_entry():
    entries = [{"kind": "text"}] * (MAX_BLOCKS_PER_RESULT * 4 + 50)
    blocks, errors = parse_blocks(entries)
    assert blocks == []
    assert any("were not examined" in e["error"] for e in errors)


def test_direct_model_validation_still_enforces_the_kind_payload_match():
    raw = load("text")
    raw["payload"] = load("status")["payload"]
    with pytest.raises(Exception):
        OutputBlock.model_validate(raw)


def test_serialize_block_helper_matches_parse_output():
    block = OutputBlock.model_validate(load("text"))
    assert serialize_block(block) == parse_blocks([load("text")])[0][0]
