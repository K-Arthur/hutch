"""Typed output blocks: the versioned contract for rich tool results (schema v1).

A tool that produced something richer than printable text may attach a ``blocks``
list to its ``ToolResult.data``. ``runtime.steps.call_tool`` validates that list
with :func:`parse_blocks` and puts the serialized blocks on the ``tool_result``
event (``data["blocks"]``) plus per-block problems on ``data["block_errors"]``.
The MODEL never sees block JSON - only a one-line ``[presented: ...]`` summary
appended to the tool output text.

Contract rules (each one answers a documented failure in another app; see
``docs/research/outputs-failures-2026-10-10.md``):

* Every block carries a human-readable ``text_fallback`` (open-webui #14541: a
  failed fancy render must never cost the reader the content or the diagnostic).
* ``code_receipt.source_sha256`` must equal the SHA-256 of ``source`` (open-webui
  #14823: what is displayed can never drift from what actually ran).
* Blocks are plain data, validated once, then immutable; stream/prose handling
  never re-derives them (open-webui #27399, #22267: per-token re-entry and
  prose scraping are the two root causes of duplicated/leaked previews).
* One bad block never sinks the others: :func:`parse_blocks` returns the valid
  subset plus labeled error entries and never raises (ComfyUI #9393: a client
  that cannot parse a notification must still see everything else).
* Every payload is hard-bounded, and result-level budgets
  (``MAX_BLOCKS_PER_RESULT``, ``MAX_BLOCK_JSON_CHARS``) are enforced here so a
  tool cannot balloon an event (ComfyUI #6888/#9393 class: unbounded state).

Validation is pydantic v2 in ``strict`` mode with ``extra="forbid"``: unknown
fields are contract violations, not decoration.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

#: The version this module parses. Blocks declaring any other ``v`` are
#: reported as errors, never guessed at.
BLOCK_SCHEMA_VERSION = 1

#: Most serialized blocks a single tool result may present.
MAX_BLOCKS_PER_RESULT = 24

#: Maximum combined compact-JSON size of the serialized blocks in one result.
MAX_BLOCK_JSON_CHARS = 256_000

#: Input entries examined per parse call. Beyond this the remainder becomes one
#: aggregate error entry, so a hostile tool cannot make validation itself the
#: memory bug.
_MAX_INPUT_ENTRIES = 4 * MAX_BLOCKS_PER_RESULT

#: Error entries reported per parse call (bounded the same way as blocks).
_MAX_ERROR_ENTRIES = MAX_BLOCKS_PER_RESULT

__all__ = [
    "BLOCK_SCHEMA_VERSION",
    "MAX_BLOCKS_PER_RESULT",
    "MAX_BLOCK_JSON_CHARS",
    "KNOWN_BLOCK_KINDS",
    "OutputBlock",
    "parse_blocks",
    "serialize_block",
    "new_block_id",
    "new_media_id",
    "block_json_chars",
]

ModelConfig = ConfigDict(strict=True, extra="forbid", frozen=True)

Hex64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
BlockId = Annotated[str, Field(pattern=r"^blk_[0-9a-f]{16}$")]
MediaId = Annotated[str, Field(pattern=r"^media_[0-9a-f]{16}$")]

#: A JSON number: int stays int, float stays float; NaN/Infinity are refused.
#: (Strictness comes from the model config, so ints never coerce to strings.)
_Number = Annotated[float, Field(allow_inf_nan=False)]
JSONNumber = Union[int, _Number]

#: One chart point: a two-element [number, number] array.
Point = Annotated[list[JSONNumber], Field(min_length=2, max_length=2)]

#: One table cell: a JSON scalar (strings bounded so a row cannot smuggle a novel).
TableCell = Union[None, bool, int, _Number, Annotated[str, Field(max_length=2000)]]

BlockKind = Literal[
    "text", "code_receipt", "table", "chart", "flowchart",
    "timeline", "comparison", "media", "artifact_ref", "status",
]
KNOWN_BLOCK_KINDS: tuple[str, ...] = (
    "text", "code_receipt", "table", "chart", "flowchart",
    "timeline", "comparison", "media", "artifact_ref", "status",
)

BlockAvailability = Literal["ready", "pending", "failed", "revoked", "stale"]


def new_block_id() -> str:
    """A fresh envelope id ('blk_' + 16 lowercase hex)."""
    return f"blk_{secrets.token_hex(8)}"


def new_media_id() -> str:
    """A fresh media id ('media_' + 16 lowercase hex)."""
    return f"media_{secrets.token_hex(8)}"


# --------------------------------------------------------------------- payloads


class TextPayload(BaseModel):
    """Plain prose or notes presented as a first-class block."""

    model_config = ModelConfig

    content: Annotated[str, Field(min_length=1, max_length=20_000)]


class CodeExecution(BaseModel):
    """What actually happened when the recorded source ran."""

    model_config = ModelConfig

    ordinal: Annotated[int, Field(ge=1)]
    environment_generation: Annotated[int, Field(ge=1)]
    started_at: Annotated[str, Field(min_length=1, max_length=64)]
    finished_at: Annotated[str, Field(min_length=1, max_length=64)]
    status: Literal["ok", "error", "timeout", "cancelled", "interrupt_unconfirmed"]
    stdout_chars_total: Annotated[int, Field(ge=0)]
    stderr_chars_total: Annotated[int, Field(ge=0)]


class ProducedFile(BaseModel):
    model_config = ModelConfig

    name: Annotated[str, Field(min_length=1, max_length=200)]
    sha256: Hex64
    bytes: Annotated[int, Field(ge=0)]


class CodeReceiptPayload(BaseModel):
    """The exact source that ran, hash-bound, plus bounded execution evidence.

    ``source_sha256`` is validated against ``source`` so the display copy can
    never silently diverge from the bytes that executed (open-webui #14823).
    """

    model_config = ModelConfig

    source: Annotated[str, Field(min_length=1, max_length=100_000)]
    language: Annotated[str, Field(min_length=1, max_length=40)] = "python"
    source_sha256: Hex64
    execution: CodeExecution
    stdout_tail: Annotated[str, Field(max_length=4_000)] = ""
    stderr_tail: Annotated[str, Field(max_length=4_000)] = ""
    result_repr: Annotated[str, Field(max_length=2_000)] = ""
    produced_files: Annotated[list[ProducedFile], Field(max_length=32)] = []

    @field_validator("source_sha256")
    @classmethod
    def _hash_matches_source(cls, value: str, info) -> str:
        source = info.data.get("source")
        if source is not None:
            actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if actual != value:
                raise ValueError(
                    "source_sha256 does not match sha256(source); the receipt must record "
                    "the hash of the exact source it displays")
        return value


class TableColumn(BaseModel):
    model_config = ModelConfig

    name: Annotated[str, Field(min_length=1, max_length=200)]
    dtype: Literal["text", "number", "boolean", "date", "unknown"] = "unknown"


class TableTruncation(BaseModel):
    model_config = ModelConfig

    omitted_rows: Annotated[int, Field(ge=0)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class TablePayload(BaseModel):
    """A bounded preview table; ``row_total`` discloses what was left out."""

    model_config = ModelConfig

    columns: Annotated[list[TableColumn], Field(max_length=64)]
    rows: Annotated[list[list[TableCell]], Field(max_length=500)]
    row_total: Annotated[int, Field(ge=0)]
    truncation: TableTruncation | None = None
    notes: Annotated[str, Field(max_length=1_000)] | None = None

    @model_validator(mode="after")
    def _row_total_covers_rows(self) -> "TablePayload":
        if self.row_total < len(self.rows):
            raise ValueError(
                f"row_total ({self.row_total}) is smaller than the {len(self.rows)} rows present; "
                "row_total must be a true total")
        return self


class Axis(BaseModel):
    model_config = ModelConfig

    label: Annotated[str, Field(min_length=1, max_length=200)]
    unit: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    scale: Literal["linear", "log", "time"]


class ChartSeries(BaseModel):
    model_config = ModelConfig

    label: Annotated[str, Field(min_length=1, max_length=120)]
    points: Annotated[list[Point], Field(max_length=2_000)]


class ChartPayload(BaseModel):
    """Numeric series with declared units/scales and an honesty tag for origin."""

    model_config = ModelConfig

    kind: Literal["line", "bar", "scatter", "area"]
    series: Annotated[list[ChartSeries], Field(min_length=1, max_length=8)]
    x: Axis
    y: Axis
    source: Literal["executed", "deterministic", "estimated"]
    dataset_ref: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    notes: Annotated[str, Field(max_length=500)] | None = None


class FlowchartNode(BaseModel):
    model_config = ModelConfig

    id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    group: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    detail: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None


class FlowchartEdge(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, populate_by_name=True)

    from_id: Annotated[str, Field(alias="from", pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    to: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    label: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class FlowchartPayload(BaseModel):
    """A directed graph. Cycles are valid; dangling edge endpoints are not."""

    model_config = ModelConfig

    nodes: Annotated[list[FlowchartNode], Field(max_length=64)]
    edges: Annotated[list[FlowchartEdge], Field(max_length=128)]
    direction: Literal["LR", "TB"]
    assumptions_note: Annotated[str, Field(min_length=1, max_length=1_000)] | None = None

    @model_validator(mode="after")
    def _edges_reference_declared_nodes(self) -> "FlowchartPayload":
        declared = {node.id for node in self.nodes}
        for edge in self.edges:
            for endpoint, field in ((edge.from_id, "from"), (edge.to, "to")):
                if endpoint not in declared:
                    raise ValueError(
                        f"edge endpoint {endpoint!r} ({field}) does not match any declared node id; "
                        "dangling edges are invalid")
        return self


class TimestampMoment(BaseModel):
    model_config = ModelConfig

    iso8601: Annotated[str, Field(min_length=1, max_length=40)]
    precision: Literal["year", "month", "day", "hour", "minute", "second"]
    timezone: Annotated[str, Field(min_length=1, max_length=64)] | None = None

    @field_validator("iso8601")
    @classmethod
    def _parses_as_iso8601(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"iso8601 {value!r} is not a parseable ISO-8601 timestamp") from None
        return value


class TimelineEvent(BaseModel):
    model_config = ModelConfig

    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    when: TimestampMoment
    state: Literal["reported", "confirmed", "planned", "corrected"]
    source: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    corrected_from: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class TimelinePayload(BaseModel):
    model_config = ModelConfig

    events: Annotated[list[TimelineEvent], Field(max_length=200)]


class ComparisonItem(BaseModel):
    model_config = ModelConfig

    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=200)]


class ComparisonCriterion(BaseModel):
    model_config = ModelConfig

    id: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    unit: Annotated[str, Field(min_length=1, max_length=40)] | None = None


class ComparisonCell(BaseModel):
    """One grid cell: either a value or an explicit empty-state, never both,
    never an invented value."""

    model_config = ModelConfig

    item: Annotated[str, Field(min_length=1, max_length=64)]
    criterion: Annotated[str, Field(min_length=1, max_length=64)]
    value: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    state: Literal["unknown", "not_applicable", "unsupported"] | None = None
    citations: Annotated[str, Field(min_length=1, max_length=300)] | None = None

    @model_validator(mode="after")
    def _value_xor_state(self) -> "ComparisonCell":
        if (self.value is None) == (self.state is None):
            raise ValueError(
                "a comparison cell must carry exactly one of value or state "
                "(unknown/not_applicable/unsupported); never invent a value")
        return self


class ComparisonPayload(BaseModel):
    model_config = ModelConfig

    items: Annotated[list[ComparisonItem], Field(max_length=24)]
    criteria: Annotated[list[ComparisonCriterion], Field(max_length=24)]
    cells: Annotated[list[ComparisonCell], Field(max_length=576)]
    ranking_note: Annotated[str, Field(min_length=1, max_length=500)] | None = None

    @model_validator(mode="after")
    def _cells_reference_declared_axes(self) -> "ComparisonPayload":
        items = {item.id for item in self.items}
        criteria = {criterion.id for criterion in self.criteria}
        for cell in self.cells:
            if cell.item not in items:
                raise ValueError(f"cell item {cell.item!r} does not match any declared item id")
            if cell.criterion not in criteria:
                raise ValueError(f"cell criterion {cell.criterion!r} does not match any declared criterion id")
        return self


class MediaRef(BaseModel):
    model_config = ModelConfig

    media_id: MediaId
    version: Annotated[int, Field(ge=1)]


class MediaPayload(BaseModel):
    """A reference to stored media bytes. ``alt_text`` is required: the
    readable alternative is part of the block, not a nice-to-have."""

    model_config = ModelConfig

    media_id: MediaId
    version: Annotated[int, Field(ge=1)]
    sha256: Hex64
    mime: Literal["image/png", "image/jpeg", "image/webp", "image/svg+xml",
                  "video/webm", "video/mp4", "audio/wav"]
    kind: Literal["image", "video", "animation", "audio"]
    alt_text: Annotated[str, Field(min_length=1, max_length=600)]
    poster: MediaRef | None = None
    captions: MediaRef | None = None
    duration_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    width: Annotated[int, Field(ge=1)] | None = None
    height: Annotated[int, Field(ge=1)] | None = None
    backend: Annotated[str, Field(min_length=1, max_length=64)]
    generated_by: Literal["deterministic", "provider"]

    @field_validator("alt_text")
    @classmethod
    def _alt_text_readable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("alt_text must contain readable text, not only whitespace")
        return value


class ArtifactRefPayload(BaseModel):
    """A pointer to a durable document or media version (documents/storage.py
    owns the bytes; this block only certifies which one to present)."""

    model_config = ModelConfig

    ref_kind: Literal["document", "media"]
    id: Annotated[str, Field(pattern=r"^(doc|media)_[0-9a-f]{16}$")]
    version: Annotated[int, Field(ge=1)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    mime: Annotated[str, Field(min_length=1, max_length=128)]
    bytes: Annotated[int, Field(ge=0)]
    sha256: Hex64

    @model_validator(mode="after")
    def _id_prefix_matches_ref_kind(self) -> "ArtifactRefPayload":
        prefix = "doc_" if self.ref_kind == "document" else "media_"
        if not self.id.startswith(prefix):
            raise ValueError(
                f"ref_kind {self.ref_kind!r} requires an id prefixed {prefix!r}, got {self.id!r}")
        return self


class StatusPayload(BaseModel):
    """Progress/status presented as a block (availability lives on the envelope)."""

    model_config = ModelConfig

    stage: Annotated[str, Field(min_length=1, max_length=64)]
    detail: Annotated[str, Field(max_length=2_000)]
    state: Literal["pending", "running", "final", "failed", "cancelled", "stale", "blocked", "unknown"]


_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "text": TextPayload,
    "code_receipt": CodeReceiptPayload,
    "table": TablePayload,
    "chart": ChartPayload,
    "flowchart": FlowchartPayload,
    "timeline": TimelinePayload,
    "comparison": ComparisonPayload,
    "media": MediaPayload,
    "artifact_ref": ArtifactRefPayload,
    "status": StatusPayload,
}


# --------------------------------------------------------------------- envelope


class OutputBlock(BaseModel):
    """The versioned envelope around every payload."""

    model_config = ModelConfig

    v: Literal[BLOCK_SCHEMA_VERSION]
    id: BlockId
    kind: BlockKind
    revision: Annotated[int, Field(ge=1)]
    availability: BlockAvailability
    text_fallback: Annotated[str, Field(min_length=1, max_length=4_000)]
    provenance: "BlockProvenance"
    #: Parsed separately with the kind-specific model (see parse_blocks) so
    #: errors name the right fields; the validator below enforces the match.
    payload: Any

    @field_validator("text_fallback")
    @classmethod
    def _fallback_readable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text_fallback must contain readable text, not only whitespace")
        return value

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> "OutputBlock":
        expected = _PAYLOAD_MODELS[self.kind]
        if type(self.payload) is not expected:
            if isinstance(self.payload, dict):
                # Direct model_validate of raw JSON: parse the payload the way
                # parse_blocks would, so both paths accept the same inputs.
                return self.model_copy(update={"payload": expected.model_validate(self.payload)})
            raise ValueError(
                f"payload is {type(self.payload).__name__} but kind {self.kind!r} "
                f"requires {expected.__name__}")
        return self


class BlockProvenance(BaseModel):
    """Which run and tool produced this block (binds a block to its origin so
    previews can never be shared across sessions, ComfyUI #6888)."""

    model_config = ModelConfig

    run_id: Annotated[str, Field(min_length=1, max_length=128)]
    tool: Annotated[str, Field(min_length=1, max_length=128)]
    job_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


OutputBlock.model_rebuild()


# ----------------------------------------------------------------------- parsing


def serialize_block(block: OutputBlock) -> dict[str, Any]:
    """Canonical JSON-ready dict for one validated block (compact, stable order;
    absent optional fields stay absent, never null)."""
    return block.model_dump(mode="json", by_alias=True, exclude_none=True)


def block_json_chars(entry: dict[str, Any]) -> int:
    """The compact-JSON size used for the ``MAX_BLOCK_JSON_CHARS`` budget."""
    return len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))


def _error_entry(raw: Any, message: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"error": message}
    if isinstance(raw, dict):
        raw_id, raw_kind = raw.get("id"), raw.get("kind")
        if isinstance(raw_id, str) and raw_id:
            entry["id"] = raw_id
        if isinstance(raw_kind, str) and raw_kind:
            entry["kind"] = raw_kind
    return entry


def _summarize_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        loc = ".".join(str(item) for item in error.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {error.get('msg', 'invalid')}")
    summary = "; ".join(parts)
    return summary[:400]


def _validate_one(raw: Any) -> tuple[OutputBlock | None, str | None]:
    """Validate one entry. Returns (block, None) or (None, a labeled reason)."""
    if not isinstance(raw, dict):
        return None, "block entry is not a JSON object"
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in _PAYLOAD_MODELS:
        return None, f"unknown block kind {kind!r}; known kinds: {', '.join(KNOWN_BLOCK_KINDS)}"
    if "v" not in raw:
        return None, f"{kind} block is missing the required schema version field 'v'"
    if raw["v"] != BLOCK_SCHEMA_VERSION:
        return None, (f"unsupported block schema version {raw['v']!r}; "
                      f"this hutch parses version {BLOCK_SCHEMA_VERSION}")
    if "payload" not in raw:
        return None, f"{kind} block is missing its payload"
    payload_model = _PAYLOAD_MODELS[kind]
    try:
        payload = payload_model.model_validate(raw["payload"])
    except ValidationError as exc:
        return None, f"invalid {kind} payload: {_summarize_validation_error(exc)}"
    except Exception as exc:  # never let one block crash the batch
        return None, f"invalid {kind} payload: {exc!r}"
    try:
        return OutputBlock.model_validate({**raw, "payload": payload}), None
    except ValidationError as exc:
        return None, f"invalid {kind} block: {_summarize_validation_error(exc)}"
    except Exception as exc:  # never let one block crash the batch
        return None, f"invalid {kind} block: {exc!r}"


def parse_blocks(value: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a tool-supplied ``blocks`` list. Never raises.

    Returns ``(blocks, errors)``: ``blocks`` holds the canonical serialized dicts
    of every valid block, in order, within both budgets; ``errors`` holds
    ``{id?, kind?, error}`` entries for each invalid, unknown-kind or
    unknown-version block (and for anything that fell to a budget). A non-list
    input is one error entry, not an exception.
    """
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, (list, tuple)):
        return [], [_error_entry(value, f"blocks must be a JSON array, got {type(value).__name__}")]
    blocks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    used_chars = 0
    suppressed = 0
    examined = 0
    for position, raw in enumerate(value):
        if examined >= _MAX_INPUT_ENTRIES:
            errors.append(_error_entry(
                None, f"{len(value) - position} block entries beyond the first "
                      f"{_MAX_INPUT_ENTRIES} were not examined"))
            break
        examined += 1
        block, problem = _validate_one(raw)
        if problem is not None:
            if len(errors) >= _MAX_ERROR_ENTRIES:
                suppressed += 1
            else:
                errors.append(_error_entry(raw, problem))
            continue
        assert block is not None
        serialized = serialize_block(block)
        size = block_json_chars(serialized)
        if len(blocks) >= MAX_BLOCKS_PER_RESULT:
            entry = _error_entry(raw, f"output-block budget exceeded: at most "
                                      f"{MAX_BLOCKS_PER_RESULT} blocks per result")
            if len(errors) >= _MAX_ERROR_ENTRIES:
                suppressed += 1
            else:
                errors.append(entry)
            continue
        if used_chars + size > MAX_BLOCK_JSON_CHARS:
            entry = _error_entry(raw, f"output-block budget exceeded: the result's blocks are "
                                      f"limited to {MAX_BLOCK_JSON_CHARS} compact-JSON characters")
            if len(errors) >= _MAX_ERROR_ENTRIES:
                suppressed += 1
            else:
                errors.append(entry)
            continue
        blocks.append(serialized)
        used_chars += size
    if suppressed:
        errors.append({"error": f"{suppressed} further block error(s) suppressed"})
    return blocks, errors
