import json

import pytest

from hutch.runtime.pi_protocol import PiJsonlDecoder, PiProtocolError, PiRpcProtocol, encode_command


def test_jsonl_decoder_splits_only_lf_and_accepts_crlf_and_unicode_separators():
    decoder = PiJsonlDecoder()
    raw = '{"type":"message_update","text":"a\u2028b\u2029c"}\r\n{"type":"agent_settled"}\n'.encode()
    records = []
    for chunk in (raw[:5], raw[5:21], raw[21:39], raw[39:]):
        records.extend(decoder.feed(chunk))
    decoder.finish()
    assert records == [
        {"type": "message_update", "text": "a\u2028b\u2029c"},
        {"type": "agent_settled"},
    ]


def test_jsonl_decoder_rejects_partial_invalid_non_object_and_unbounded_records():
    with pytest.raises(PiProtocolError, match="partial record"):
        decoder = PiJsonlDecoder()
        decoder.feed(b'{"type":"agent_settled"}')
        decoder.finish()
    with pytest.raises(PiProtocolError, match="invalid UTF-8 JSON"):
        PiJsonlDecoder().feed(b"\xff\n")
    with pytest.raises(PiProtocolError, match="JSON objects"):
        PiJsonlDecoder().feed(b"[]\n")
    with pytest.raises(PiProtocolError, match="byte limit"):
        PiJsonlDecoder(max_record_bytes=3).feed(b"1234")


def test_command_encoding_uses_type_and_id_and_preserves_unicode():
    raw = encode_command("prompt", "req-1", message="line\u2028text")
    assert raw.endswith(b"\n")
    assert json.loads(raw) == {"type": "prompt", "id": "req-1", "message": "line\u2028text"}
    with pytest.raises(ValueError, match="override"):
        encode_command("prompt", "req-1", id="req-2")


def test_invalid_command_does_not_leave_a_phantom_pending_request():
    rpc = PiRpcProtocol()
    with pytest.raises(ValueError, match="serializable"):
        rpc.command("prompt", message=object())
    line = json.loads(rpc.prompt("valid"))
    assert line["id"] == "hutch-1"
    assert rpc.pending == {"hutch-1": "prompt"}


def test_response_correlation_supports_out_of_order_and_rejects_wrong_id_or_command():
    rpc = PiRpcProtocol()
    get_state = rpc.command("get_state")
    models = rpc.command("get_available_models")
    first, second = map(json.loads, (get_state, models))

    accepted = rpc.accept({"type": "response", "id": second["id"], "command": "get_available_models", "success": True})
    assert accepted.payload["id"] == second["id"]
    assert rpc.pending == {first["id"]: "get_state"}
    with pytest.raises(PiProtocolError, match="does not match"):
        rpc.accept({"type": "response", "id": first["id"], "command": "abort", "success": True})
    with pytest.raises(PiProtocolError, match="unknown request"):
        rpc.accept({"type": "response", "id": "foreign", "command": "get_state", "success": True})


def test_prompt_streaming_agent_end_and_settled_lifecycle():
    rpc = PiRpcProtocol()
    command = json.loads(rpc.prompt("summarize"))
    rpc.accept({"type": "response", "id": command["id"], "command": "prompt", "success": True,
                "data": {"disposition": "started"}})
    records = rpc.feed(
        b'{"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"Hello "}}\n'
        b'{"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"world"}}\n'
        b'{"type":"agent_end"}\n'
    )
    assert [record.text_delta for record in records if record.kind == "text_delta"] == ["Hello ", "world"]
    assert not rpc.settled
    rpc.feed(b'{"type":"agent_settled"}\n')
    assert rpc.settled and rpc.text == "Hello world"
    with pytest.raises(PiProtocolError, match="after agent_settled"):
        rpc.command("get_state")


def test_handled_prompt_does_not_wait_for_settled_and_cancel_uses_abort_command():
    rpc = PiRpcProtocol()
    prompt = json.loads(rpc.prompt("handled"))
    rpc.accept({"type": "response", "id": prompt["id"], "command": "prompt", "success": True,
                "data": {"disposition": "handled"}})
    assert rpc.prompt_handled and not rpc.settled
    abort = json.loads(rpc.cancel())
    assert abort == {"type": "abort", "id": "hutch-2"}


def test_streamed_assistant_output_is_bounded():
    rpc = PiRpcProtocol(max_output_chars=4)
    with pytest.raises(PiProtocolError, match="character limit"):
        rpc.accept({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "12345"}})


def test_streamed_output_chunk_count_is_bounded_even_for_tiny_deltas():
    rpc = PiRpcProtocol(max_output_chars=100, max_output_chunks=1)
    event = {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "a"}}
    rpc.accept(event)
    with pytest.raises(PiProtocolError, match="chunk limit"):
        rpc.accept(event)
