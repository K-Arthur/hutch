"""OpenAI-compatible streaming tool-call assembly as one explicit state machine.

Requirements this encodes (docs/realignment/tool-calling.md, assignment section 8):

* a call is complete only when the provider says it is - an opening event with
  ``arguments: ""`` is not an executable call, and the first balanced brace is not
  the boundary either;
* names may arrive once, as repeated chunks, or as cumulative snapshots; argument
  fragments are appended in arrival order and never reformatted (vLLM #39380:
  a server-side parser corrupted decimals; a client must not add its own);
* ids may be missing (llama.cpp's documented shape) and are assigned by the loop,
  never invented here; two different ids on one slot are a conflicting identifier;
* bounds: calls, argument bytes, and slot count are enforced during assembly so a
  broken or hostile stream cannot grow memory without limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

MAX_CALLS = 32
MAX_ARGUMENT_BYTES = 1_000_000
MAX_NAME_CHARS = 200


class StreamAssemblyError(ValueError):
    """The stream cannot be assembled into unambiguous calls."""


@dataclass
class _Slot:
    index: int
    id: str = ""
    id_seen: bool = False
    name: str = ""
    args: list[str] = field(default_factory=list)
    args_bytes: int = 0
    finish: str = ""

    def raw_args(self) -> str:
        return "".join(self.args)


def _merge_name_fragment(current: str, fragment: str) -> str:
    """Append only a genuine continuation; repeats and cumulative snapshots are inert."""
    if not fragment:
        return current
    if not current:
        return fragment
    if fragment == current:
        return current
    if fragment.startswith(current):
        return fragment                     # a cumulative snapshot replaces the prefix
    if current.endswith(fragment):
        return current                      # a re-sent tail fragment
    return current + fragment


class OpenAIChatStreamAssembler:
    """Fold one ``/chat/completions`` SSE stream into content, calls, usage, and notes."""

    def __init__(self, *, max_calls: int = MAX_CALLS, max_argument_bytes: int = MAX_ARGUMENT_BYTES):
        self._content: list[str] = []
        self._slots: dict[int, _Slot] = {}
        self._usage: dict[str, Any] = {}
        self._finish: str = ""
        self._model: str = ""
        self._done = False
        self._max_calls = max_calls
        self._max_argument_bytes = max_argument_bytes
        self.notes: list[str] = []

    # ------------------------------------------------------------------ state

    @property
    def content(self) -> str:
        return "".join(self._content)

    @property
    def usage(self) -> dict[str, Any]:
        return dict(self._usage)

    @property
    def finish(self) -> str:
        return self._finish or "stop"

    @property
    def model(self) -> str:
        return self._model

    @property
    def done(self) -> bool:
        return self._done

    def mark_done(self) -> None:
        self._done = True

    # ------------------------------------------------------------------ input

    def feed(self, chunk: Any) -> None:
        if not isinstance(chunk, dict):
            raise StreamAssemblyError("a stream chunk was not a JSON object")
        if "error" in chunk and chunk["error"]:
            raise StreamAssemblyError(f"the provider reported an error mid-stream: {chunk['error']}")
        if isinstance(chunk.get("model"), str):
            self._model = chunk["model"]
        if isinstance(chunk.get("usage"), dict):
            self._usage = chunk["usage"]
        choices = chunk.get("choices")
        if choices is None:
            return
        if not isinstance(choices, list):
            raise StreamAssemblyError("choices was not a list")
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                self._feed_delta(delta, choice)
            reason = choice.get("finish_reason")
            if isinstance(reason, str) and reason:
                if choice.get("index") in (0, None) or not self._finish:
                    self._finish = reason
        if len(self._slots) > self._max_calls:
            raise StreamAssemblyError(f"the stream reported more than {self._max_calls} tool calls")

    def _feed_delta(self, delta: dict[str, Any], choice: dict[str, Any]) -> None:
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._content.append(content)
        tool_calls = delta.get("tool_calls")
        if tool_calls is None:
            return
        if not isinstance(tool_calls, list):
            raise StreamAssemblyError("delta.tool_calls was not a list")
        for entry in tool_calls:
            if not isinstance(entry, dict):
                raise StreamAssemblyError("a tool_calls entry was not a JSON object")
            self._feed_call_entry(entry)

    def _feed_call_entry(self, entry: dict[str, Any]) -> None:
        raw_index = entry.get("index")
        slot = self._select_slot(raw_index, entry)
        call_id = entry.get("id")
        if isinstance(call_id, str) and call_id:
            if slot.id_seen and slot.id != call_id:
                self.notes.append(
                    f"call {slot.index} carried two different ids ({slot.id!r}, {call_id!r}); the first was kept")
            if not slot.id_seen:
                slot.id = call_id
                slot.id_seen = True
        function = entry.get("function")
        if function is None:
            return
        if not isinstance(function, dict):
            raise StreamAssemblyError("tool_calls.function was not a JSON object")
        name = function.get("name")
        if isinstance(name, str) and name:
            slot.name = _merge_name_fragment(slot.name, name)[:MAX_NAME_CHARS]
        arguments = function.get("arguments")
        if arguments is None or arguments == "":
            return
        if not isinstance(arguments, str):
            raise StreamAssemblyError("tool_call arguments fragments must be strings")
        slot.args.append(arguments)
        slot.args_bytes += len(arguments.encode("utf-8", errors="replace"))
        if slot.args_bytes > self._max_argument_bytes:
            raise StreamAssemblyError(
                f"arguments for call {slot.index} exceeded {self._max_argument_bytes:,} bytes")

    def _select_slot(self, raw_index: Any, entry: dict[str, Any]) -> _Slot:
        index: Optional[int] = None
        if isinstance(raw_index, bool):
            raise StreamAssemblyError("tool_call index was a boolean")
        if isinstance(raw_index, int):
            index = raw_index
        elif isinstance(raw_index, str) and raw_index.strip().lstrip("-").isdigit():
            index = int(raw_index.strip())
        if index is None:
            # Some gateways omit index on every delta. Without it, a conflicting id or
            # a new function name starts a new slot; bare argument deltas continue the last.
            function = entry.get("function") if isinstance(entry.get("function"), dict) else {}
            new_name = function.get("name") if isinstance(function.get("name"), str) else ""
            new_id = entry.get("id") if isinstance(entry.get("id"), str) else ""
            last = self._slots[max(self._slots)] if self._slots else None
            conflicts = bool(last) and ((new_id and last.id_seen and new_id != last.id)
                                        or (new_name and last.name and new_name != last.name))
            if last is None or conflicts:
                index = 0 if last is None else last.index + 1
            else:
                index = last.index
        if index < 0:
            raise StreamAssemblyError("tool_call index was negative")
        slot = self._slots.get(index)
        if slot is None:
            if len(self._slots) >= self._max_calls:
                raise StreamAssemblyError(f"the stream reported more than {self._max_calls} tool calls")
            slot = self._slots[index] = _Slot(index=index)
        return slot

    # ------------------------------------------------------------------ output

    def calls(self) -> list[dict[str, Any]]:
        """Assembled calls in index order; ``arguments`` is the exact concatenated text."""
        return [{"index": slot.index, "id": slot.id, "name": slot.name, "arguments": slot.raw_args()}
                for slot in sorted(self._slots.values(), key=lambda s: s.index)]


def should_reject_empty_stream(assembler: OpenAIChatStreamAssembler) -> bool:
    """Whether a stream that ended here proves the provider produced nothing usable."""
    return (not assembler.done and not assembler.usage and assembler.finish == "stop"
            and not assembler.content and not assembler.calls())
