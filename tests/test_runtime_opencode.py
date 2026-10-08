import json
from pathlib import Path

import pytest

from hutch.runtime.opencode_protocol import (
    OpenCodeContract,
    OpenCodeProtocolError,
    SseDecoder,
    parse_permission_request,
    permission_reply_body,
)


FIXTURE = Path(__file__).parent / "fixtures" / "opencode_v2_0_24_contract.json"


def contract_fixture():
    return json.loads(FIXTURE.read_text())


def test_installed_2024_contract_is_experimental_and_event_loss_is_explicit():
    fixture = contract_fixture()
    api = {key: value for key, value in fixture.items() if key != "installed_binary"}
    contract = OpenCodeContract.from_openapi(api)

    assert fixture["installed_binary"] == "opencode v2.0.24"
    assert contract.api_version == "0.0.1"
    assert contract.api_experimental
    assert contract.event_stream_volatile
    assert not contract.safe_for_durable_hutch_execution
    assert set(contract.permission_fields) >= {"id", "sessionID", "action", "resources"}


def test_sse_decoder_handles_chunked_crlf_multiline_data_and_unicode():
    decoder = SseDecoder()
    source = (
        ': keepalive\r\nevent: permission.updated\r\nid: evt-7\r\n'
        'data: {"message":"first\u2028line",\r\n'
        'data: "ok":true}\r\n\r\n'
    ).encode("utf-8")
    events = []
    for size in (1, 2, 7, 3, 13, 5, 19):
        if not source:
            break
        events.extend(decoder.feed(source[:size]))
        source = source[size:]
    events.extend(decoder.feed(source))
    decoder.finish()

    assert len(events) == 1
    assert events[0].event == "permission.updated"
    assert events[0].event_id == "evt-7"
    assert events[0].json_payload() == {"message": "first\u2028line", "ok": True}


def test_last_event_id_persists_within_stream_and_json_encoded_twice_payload_is_decoded():
    decoder = SseDecoder()
    first = decoder.feed(b'id: durable-id\ndata: "{\\"kind\\":\\"tick\\"}"\n\n')
    second = decoder.feed(b'data: {"kind":"next"}\n\n')
    assert first[0].json_payload() == {"kind": "tick"}
    assert second[0].event_id == "durable-id"
    assert second[0].json_payload() == {"kind": "next"}


def test_sse_rejects_oversized_invalid_and_truncated_frames():
    decoder = SseDecoder(max_event_bytes=16)
    with pytest.raises(OpenCodeProtocolError, match="byte limit"):
        decoder.feed(b"data: 12345678901234567890")
    with pytest.raises(OpenCodeProtocolError, match="invalid UTF-8"):
        SseDecoder().feed(b"data: \xff\n\n")
    decoder = SseDecoder()
    decoder.feed(b"data: {\"ok\":true}\n")
    with pytest.raises(OpenCodeProtocolError, match="ended within an event"):
        decoder.finish()


def test_hutch_permission_mapping_never_grants_open_code_always():
    assert permission_reply_body(approve_once=True) == {"decision": "once"}
    assert permission_reply_body(approve_once=False) == {"decision": "reject"}
    assert "always" not in permission_reply_body(approve_once=True).values()


def test_permission_request_preserves_destination_and_exact_resources():
    result = parse_permission_request({
        "id": "per_fixture",
        "sessionID": "ses_fixture",
        "action": "edit",
        "resources": ["src/answer.py", "src/answer.py:1-3"],
        "message": "Write a value",
        "metadata": {"revision": "sha256:abc"},
        "source": {"kind": "tool"},
    })
    assert result == {
        "id": "per_fixture",
        "session_id": "ses_fixture",
        "action": "edit",
        "resources": ("src/answer.py", "src/answer.py:1-3"),
        "message": "Write a value",
        "source": {"kind": "tool"},
        "metadata": {"revision": "sha256:abc"},
    }
    with pytest.raises(OpenCodeProtocolError):
        parse_permission_request({"id": "per_1", "sessionID": "ses_1", "action": "edit", "resources": [1]})
