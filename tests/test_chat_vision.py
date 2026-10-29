"""Chat image input: admission honesty, wire parts, and runtime capability gates.

Covers the chat-vision slice end to end at the route level (validation before any
run is admitted, attachment references recorded on the run, prompt-optional
image-only sends) plus the pure attachment module and the two runtime guards.

Real images throughout: the workspace PNG is Hutch's bundled Google Calendar mark
and the WebP is a real 1440x1000 first-run capture, not synthetic stubs. The live
free-model test at the end of this file attempts actual OpenCode inference on a
named free route, without provider keys, only with explicit live-test opt-in and
the CLI installed; everything above it stays hermetic. Trial quota and route
availability are external acceptance conditions, not regression prerequisites.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run
from hutch.providers.attachments import (
    IMAGE_MIMES,
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_MESSAGE,
    ImageAttachmentError,
    chat_image_parts,
    image_route_refusal,
    is_image_upload,
    validate_image_rows,
)
from hutch.runtime.base import RunAborted
from hutch.server.app import create_app
from hutch.workspace.manager import workspace_dir_for

REPO = Path(__file__).resolve().parents[1]
REAL_PNG = REPO / "src/hutch/server/static/brands/google-calendar-2026q2.png"
REAL_WEBP = REPO / "website/assets/captures/setup-desktop.webp"


@pytest.fixture()
def api_client(config):
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture()
def conversation(api_client):
    bot = api_client.post("/api/bots", json={"name": "vision-lane", "model": "mock/demo", "tools": []}).json()
    conversation, _ = api_client.app.state.store.create_conversation(
        bot["id"], "Vision lane", idem_key="vision-lane", request_hash="vision-lane")
    return conversation["id"]


def _upload(client, conversation_id: str, name: str, data: bytes):
    return client.post(f"/api/v1/conversations/{conversation_id}/uploads",
                       files={"file": (name, data, "application/octet-stream")})


def _send(client, conversation_id: str, payload: dict, key: str = "vision-send"):
    return client.post(f"/api/v1/conversations/{conversation_id}/messages", json=payload,
                       headers={"Idempotency-Key": key})


def _place_upload(config, conversation_id: str, upload: dict, data: bytes) -> Path:
    """Put real bytes where the intake would have promoted them (same naming)."""
    workspace = workspace_dir_for(config.state_dir, conversation_id)
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = workspace / f"{upload['id']}-{upload['filename']}"
    path.write_bytes(data)
    return path


def _message_count(client, conversation_id: str) -> int:
    return client.get(f"/api/v1/conversations/{conversation_id}").json()["message_count"]


# --------------------------------------------------------------- admission

def test_image_only_send_is_admitted_and_records_attachments(api_client, conversation):
    """No prompt + verified image is a complete message; refs land on the run."""
    uploaded = _upload(api_client, conversation, "calendar.png", REAL_PNG.read_bytes())
    assert uploaded.status_code == 200, uploaded.text
    upload = uploaded.json()
    assert upload["mime"] == "image/png"

    created = _send(api_client, conversation, {"image_attachment_ids": [upload["id"]]}, key="img-only-1")
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["prompt"] == ""
    # The admission snapshot carries everything the runtime re-verifies against disk.
    attachment = run["image_attachments"][0]
    assert attachment["id"] == upload["id"]
    assert attachment["conversation_id"] == conversation
    assert attachment["filename"] == "calendar.png"
    assert attachment["mime"] == "image/png"
    assert attachment["byte_size"] == len(REAL_PNG.read_bytes())
    assert attachment["state"] == "ready"
    assert len(attachment["sha256"]) == 64

    # The message row carries empty text; the run is the attachment authority the
    # transcript renders from (run_view flows the model dump).
    detail = api_client.get(f"/api/v1/conversations/{conversation}").json()
    assert [m for m in detail["messages"] if m["role"] == "user"][-1]["content"] == ""
    fetched = api_client.get(f"/api/v1/tasks/runs/{run['id']}").json()
    assert fetched["image_attachments"][0]["id"] == upload["id"]

    # The tray's images travel with the NEXT message too (attachment-tray contract).
    again = _send(api_client, conversation, {"prompt": "Same image again",
                                             "image_attachment_ids": [upload["id"]]}, key="img-again-1")
    assert again.status_code == 201, again.text
    assert again.json()["image_attachments"][0]["id"] == upload["id"]


def test_text_and_image_send_records_both(api_client, conversation):
    uploaded = _upload(api_client, conversation, "capture.webp", REAL_WEBP.read_bytes())
    created = _send(api_client, conversation, {"prompt": "What does this show?",
                                               "image_attachment_ids": [uploaded.json()["id"]]},
                    key="text-img-1")
    assert created.status_code == 201, created.text
    assert created.json()["prompt"] == "What does this show?"
    assert created.json()["image_attachments"][0]["mime"] == "image/webp"


def test_prompt_is_still_required_without_images(api_client, conversation):
    refused = _send(api_client, conversation, {}, key="no-prompt-no-img")
    assert refused.status_code == 422
    assert "a message prompt is required" in refused.json()["detail"]
    assert _message_count(api_client, conversation) == 0


def test_unknown_attachment_is_refused_before_admission(api_client, conversation):
    refused = _send(api_client, conversation,
                    {"prompt": "Look", "image_attachment_ids": ["upl_0000000000000000"]}, key="unknown-1")
    assert refused.status_code == 422
    assert "no longer available" in refused.json()["detail"]
    assert _message_count(api_client, conversation) == 0, "a refused message must not create a message"


def test_attachment_from_another_conversation_is_refused(api_client):
    first = api_client.post("/api/bots", json={"name": "vision-a", "model": "mock/demo", "tools": []}).json()
    second = api_client.post("/api/bots", json={"name": "vision-b", "model": "mock/demo", "tools": []}).json()
    conv_a, _ = api_client.app.state.store.create_conversation(
        first["id"], "A", idem_key="va", request_hash="va")
    conv_b, _ = api_client.app.state.store.create_conversation(
        second["id"], "B", idem_key="vb", request_hash="vb")
    foreign = _upload(api_client, conv_b["id"], "calendar.png", REAL_PNG.read_bytes()).json()
    refused = _send(api_client, conv_a["id"], {"prompt": "Look",
                                               "image_attachment_ids": [foreign["id"]]}, key="foreign-1")
    assert refused.status_code == 422
    assert "belongs to another chat" in refused.json()["detail"]
    assert _message_count(api_client, conv_a["id"]) == 0


def test_non_image_upload_is_refused_as_attachment(api_client, conversation):
    csv = _upload(api_client, conversation, "notes.csv", b"a,b\n1,2\n")
    assert csv.status_code == 200, csv.text
    refused = _send(api_client, conversation, {"prompt": "Look",
                                               "image_attachment_ids": [csv.json()["id"]]}, key="csv-1")
    assert refused.status_code == 422
    assert "not a supported image" in refused.json()["detail"]


def test_oversized_image_is_refused_at_admission(api_client, conversation):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_IMAGE_BYTES + 1024)
    uploaded = _upload(api_client, conversation, "huge.png", big)
    assert uploaded.status_code == 200, uploaded.text   # intake allows it as a workspace file
    refused = _send(api_client, conversation, {"prompt": "Look",
                                               "image_attachment_ids": [uploaded.json()["id"]]}, key="huge-1")
    assert refused.status_code == 422
    assert "too large to send as an image" in refused.json()["detail"]
    assert "1.5 MB" in refused.json()["detail"]


def test_more_than_four_images_are_refused(api_client, conversation):
    ids = [f"upl_{index:016x}" for index in range(MAX_IMAGES_PER_MESSAGE + 1)]
    refused = _send(api_client, conversation, {"prompt": "Look", "image_attachment_ids": ids}, key="five-1")
    assert refused.status_code == 422
    assert _message_count(api_client, conversation) == 0


def test_correction_with_images_is_refused(api_client, conversation):
    refused = _send(api_client, conversation, {"prompt": "Look", "correction": "shorter",
                                               "image_attachment_ids": ["upl_0000000000000000"]},
                    key="correction-img")
    assert refused.status_code == 422
    assert "image attachments" in refused.json()["detail"]


def test_route_without_media_input_is_refused_at_admission(api_client, conversation, monkeypatch):
    """The capability gate refuses before a run exists; no model work happens."""
    class _NoMedia:
        supports_media_input = False
        def supports_vision(self, model: str) -> bool:
            return False

    monkeypatch.setattr("hutch.runtime.ladder.get_provider", lambda provider, base_url=None: _NoMedia())
    uploaded = _upload(api_client, conversation, "calendar.png", REAL_PNG.read_bytes()).json()
    refused = _send(api_client, conversation, {"prompt": "Describe",
                                               "image_attachment_ids": [uploaded["id"]]}, key="nomedia-1")
    assert refused.status_code == 422
    assert "cannot receive image input" in refused.json()["detail"]
    assert "vision-capable route" in refused.json()["detail"]
    assert _message_count(api_client, conversation) == 0


def test_opencode_runtime_admits_images_and_defers_capability_to_the_runtime(api_client, monkeypatch):
    """OpenCode's V2 prompt carries file references, so images are admitted and
    recorded; per-model capability is enforced at run start, not at admission."""
    from hutch.models import RuntimeKind
    from hutch.runtime.opencode import OpenCodeRuntime
    from tests.support.runtime import TestScenarioRuntime

    # This test proves the ADMISSION contract, so the engine gets the scenario
    # runtime instead of starting a real isolated serve in the background.
    monkeypatch.setattr("hutch.engine.get_runtime",
                        lambda bot: TestScenarioRuntime() if bot.runtime is RuntimeKind.opencode
                        else OpenCodeRuntime())
    bot = api_client.app.state.store.create_bot(
        Bot(name="vision-opencode", model="opencode/opencode/glm-5.3-flash-free",
            tools=[], runtime="opencode"))
    conv, _ = api_client.app.state.store.create_conversation(
        bot.id, "OC", idem_key="voc", request_hash="voc")
    uploaded = _upload(api_client, conv["id"], "calendar.png", REAL_PNG.read_bytes()).json()
    sent = _send(api_client, conv["id"], {"prompt": "Describe", "image_attachment_ids": [uploaded["id"]]},
                 key="oc-img-1")
    assert sent.status_code == 201, sent.text
    assert sent.json()["image_attachments"][0]["id"] == uploaded["id"]
    assert sent.json()["image_attachments"][0]["mime"] == "image/png"
    assert _message_count(api_client, conv["id"]) == 1


# ------------------------------------------------------------- pure module

def test_is_image_upload_recognises_mimes_and_legacy_chips():
    assert is_image_upload({"mime": "image/png"})
    assert is_image_upload({"mime": "image/jpeg"})
    assert is_image_upload({"mime": "image/webp"})
    assert not is_image_upload({"mime": "image/gif"})
    assert not is_image_upload({"mime": "text/csv"})
    # legacy chips stored before the mime field existed
    assert is_image_upload({"filename": "screenshot.PNG"})
    assert is_image_upload({"filename": "photo.jpeg"})
    assert not is_image_upload({"filename": "notes.csv"})


def test_validate_image_rows_reports_every_refusal_branch():
    base = {"id": "upl_" + "a" * 16, "conversation_id": "conv1", "state": "ready",
            "mime": "image/png", "filename": "shot.png", "byte_size": 1000}
    _, problems = validate_image_rows(["upl_x"], [None], conversation_id="conv1")
    assert problems == ["attached image upl_x is no longer available"]

    _, problems = validate_image_rows([base["id"]], [{**base, "conversation_id": "conv2"}],
                                      conversation_id="conv1")
    assert "belongs to another chat" in problems[0]

    _, problems = validate_image_rows([base["id"]], [{**base, "state": "quarantined"}],
                                      conversation_id="conv1")
    assert "quarantined" in problems[0]

    _, problems = validate_image_rows([base["id"]], [{**base, "mime": "text/plain", "filename": "x.txt"}],
                                      conversation_id="conv1")
    assert "not a supported image" in problems[0]

    _, problems = validate_image_rows([base["id"]], [{**base, "byte_size": MAX_IMAGE_BYTES + 1}],
                                      conversation_id="conv1")
    assert "too large to send as an image" in problems[0]

    too_many = [f"upl_{i:016x}" for i in range(MAX_IMAGES_PER_MESSAGE + 1)]
    _, problems = validate_image_rows(too_many, [None] * len(too_many), conversation_id="conv1")
    assert "at most" in problems[0]

    rows, problems = validate_image_rows([base["id"]], [base], conversation_id="conv1")
    assert problems == [] and rows[0]["mime"] == "image/png"


def test_image_route_refusal_layers_wire_and_model_checks():
    class NoMedia:
        supports_media_input = False
    class NoVision:
        supports_media_input = True
        def supports_vision(self, model):
            return False
    class Fine:
        supports_media_input = True
        def supports_vision(self, model):
            return True

    assert image_route_refusal(NoMedia(), "m") == "the selected model route cannot receive image input"
    assert image_route_refusal(NoVision(), "llava") == "the model 'llava' does not accept image input"
    # admission on local routes skips the model check (it would query /api/show)
    assert image_route_refusal(NoVision(), "llava", verify_model=False) is None
    assert image_route_refusal(Fine(), "m") is None


# -------------------------------------------------- verified bytes → parts

def test_chat_image_parts_encodes_real_image_bytes(config, store):
    bot = store.create_bot(Bot(name="parts-bot", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Parts", idem_key="p1", request_hash="p1")
    data = REAL_PNG.read_bytes()
    upload = store.add_upload(conv["id"], "calendar.png", "image/png", len(data),
                              hashlib.sha256(data).hexdigest())
    _place_upload(config, conv["id"], upload, data)

    parts, problems = chat_image_parts([upload], state_dir=config.state_dir, conversation_id=conv["id"])
    assert problems == []
    assert [p["type"] for p in parts] == ["text", "image_url"]
    assert parts[0]["text"] == "Image: calendar.png"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    decoded = base64.b64decode(parts[1]["image_url"]["url"].split(",", 1)[1])
    assert decoded == data, "the exact uploaded bytes travel to the provider"


def test_chat_image_parts_refuses_tampered_and_missing_files(config, store):
    bot = store.create_bot(Bot(name="tamper-bot", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Tamper", idem_key="t1", request_hash="t1")
    data = REAL_PNG.read_bytes()
    upload = store.add_upload(conv["id"], "calendar.png", "image/png", len(data),
                              hashlib.sha256(data).hexdigest())
    workspace = workspace_dir_for(config.state_dir, conv["id"])
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = workspace / f"{upload['id']}-calendar.png"

    # missing file: nothing is invented, nothing is partially sent
    _, problems = chat_image_parts([upload], state_dir=config.state_dir, conversation_id=conv["id"])
    assert problems and "missing" in problems[0]

    # tampered bytes: digest mismatch is a refusal, not a quiet substitution
    path.write_bytes(b"\x89PNG\r\n\x1a\n tampered")
    _, problems = chat_image_parts([upload], state_dir=config.state_dir, conversation_id=conv["id"])
    assert problems and "does not match its recorded digest" in problems[0]

    # a symlinked impostor is never read
    path.unlink()
    impostor = workspace / "impostor.png"
    impostor.write_bytes(data)
    path.symlink_to(impostor)
    with pytest.raises(ImageAttachmentError):
        from hutch.providers.attachments import read_image_upload
        read_image_upload(config.state_dir, conv["id"], upload)
    impostor.unlink()
    path.unlink(missing_ok=True)


# --------------------------------------------------------- runtime layers

def _runtime_context(config, events, store=None):
    """The two runtime hooks use ctx.config, ctx.store (live state) and ctx.emit."""
    if store is None:
        store = SimpleNamespace(get_upload=lambda upload_id: {"state": "ready"})
    return SimpleNamespace(config=config, store=store, emit=events.append)


def _image_run(conv_id: str, row: dict, prompt: str = "What color is this?") -> Run:
    """Compose a run exactly as admission does: validate the row into the snapshot."""
    rows, problems = validate_image_rows([row["id"]], [row], conversation_id=conv_id)
    assert problems == [], problems
    return Run(bot_id="bot_x", prompt=prompt, conversation_id=conv_id, image_attachments=rows)


class _Provider:
    def __init__(self, media: bool, vision: bool):
        self.supports_media_input = media
        self._vision = vision
    def supports_vision(self, model: str) -> bool:
        return self._vision


def test_builtin_attaches_images_to_the_user_turn_and_logs_transmission(config, store):
    from hutch.runtime.builtin import BuiltinRuntime

    bot = store.create_bot(Bot(name="attach-bot", model="ollama/llava:7b", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Attach", idem_key="a1", request_hash="a1")
    data = REAL_WEBP.read_bytes()
    upload = store.add_upload(conv["id"], "capture.webp", "image/webp", len(data),
                              hashlib.sha256(data).hexdigest())
    _place_upload(config, conv["id"], upload, data)

    run = _image_run(conv["id"], upload)

    events = []
    ctx = _runtime_context(config, events)
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": run.prompt}]

    BuiltinRuntime()._attach_chat_images(ctx, run, messages)

    content = messages[-1]["content"]
    assert [part["type"] for part in content] == ["text", "text", "image_url"]
    assert content[0] == {"type": "text", "text": run.prompt}
    assert content[1]["text"] == "Image: capture.webp"
    assert content[2]["image_url"]["url"].startswith("data:image/webp;base64,")
    logged = [e for e in events if e.type.value == "log" and e.data.get("kind") == "media"]
    assert logged and logged[-1].data["prepared"] == 1

    # capability accepted → recorded transmission with the exact route
    session = SimpleNamespace(provider=_Provider(True, True),
                              rung=SimpleNamespace(spec="ollama/llava:7b", model="llava:7b"))
    BuiltinRuntime()._verify_chat_images(ctx, run, session)
    logged = [e for e in events if e.type.value == "log" and e.data.get("kind") == "media"]
    assert logged[-1].data["transmitted"] == 1
    assert logged[-1].data["route"] == "ollama/llava:7b"

    # capability refused → the run aborts with an honest, actionable message
    blocked = SimpleNamespace(provider=_Provider(False, False),
                              rung=SimpleNamespace(spec="mock/demo", model="demo"))
    with pytest.raises(RunAborted) as excinfo:
        BuiltinRuntime()._verify_chat_images(ctx, run, blocked)
    assert "were not sent to the model" in str(excinfo.value)
    assert "vision-capable route" in str(excinfo.value)


def test_builtin_aborts_when_an_attached_image_cannot_be_verified(config, store):
    from hutch.runtime.builtin import BuiltinRuntime

    bot = store.create_bot(Bot(name="missing-bot", model="ollama/llava:7b", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Missing", idem_key="m1", request_hash="m1")
    row = {"id": "upl_000000000000dead", "conversation_id": conv["id"], "filename": "gone.png",
           "mime": "image/png", "byte_size": 4096, "sha256": "0" * 64, "state": "ready"}
    run = _image_run(conv["id"], row)   # id references nothing on disk
    events = []
    with pytest.raises(RunAborted) as excinfo:
        BuiltinRuntime()._attach_chat_images(_runtime_context(config, events), run,
                                             [{"role": "user", "content": run.prompt}])
    assert "missing from this chat's workspace" in str(excinfo.value)
    assert "nothing was sent" in str(excinfo.value)


def test_image_only_turn_builds_content_without_an_empty_text_part(config, store):
    from hutch.runtime.builtin import BuiltinRuntime

    bot = store.create_bot(Bot(name="empty-text-bot", model="ollama/llava:7b", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Empty", idem_key="e1", request_hash="e1")
    data = REAL_PNG.read_bytes()
    upload = store.add_upload(conv["id"], "calendar.png", "image/png", len(data),
                              hashlib.sha256(data).hexdigest())
    _place_upload(config, conv["id"], upload, data)
    run = _image_run(conv["id"], upload, prompt="")
    messages = [{"role": "user", "content": ""}]
    BuiltinRuntime()._attach_chat_images(_runtime_context(config, []), run, messages)
    content = messages[-1]["content"]
    text_parts = [part for part in content if part["type"] == "text"]
    assert text_parts, "an image-only turn still carries its filename label as text"
    assert all(part["text"].strip() for part in text_parts), "no empty text parts"
    assert content[0]["text"] == "Image: calendar.png"
    assert content[-1]["type"] == "image_url"


# --------------------------------------------------- OpenCode runtime seams

def test_opencode_model_modalities_are_parsed_from_the_capability_shape():
    from hutch.runtime.opencode_server import OpenCodeServer
    server = OpenCodeServer.__new__(OpenCodeServer)   # parsing needs no lifecycle
    payload = {"data": [
        {"providerID": "opencode", "modelID": "glm-5.3-flash-free", "name": "GLM",
         "limit": {"context": 200000},
         "capabilities": {"tools": True, "input": ["text", "image", "video", "pdf"],
                          "output": ["text"], "temperature": True}},
        {"providerID": "opencode", "modelID": "big-pickle", "name": "Big Pickle",
         "capabilities": {"tools": True, "input": ["text"], "output": ["text"], "temperature": True}},
    ]}
    server._get_with_params = lambda path, params: payload
    by_id = {m.model_id: m for m in server.models(Path("/tmp"))}
    assert by_id["glm-5.3-flash-free"].input_modalities == ("image", "pdf", "text", "video")
    assert by_id["big-pickle"].input_modalities == ("text",)
    assert "tools" in by_id["big-pickle"].capabilities


def test_opencode_prompt_sends_file_references_with_the_text():
    from hutch.runtime.opencode_server import OpenCodeServer
    server = OpenCodeServer.__new__(OpenCodeServer)
    captured = {}

    def fake_request(method, path, json_body=None, timeout=0.0):
        captured.update(method=method, path=path, body=json_body)
        return {"data": {"id": "sub_1"}}

    server.request = fake_request
    files = [{"uri": "file:///w/hutch-attachments/upl_x-icon.png", "name": "icon.png"}]
    server.prompt("ses_1", "what is this?", message_id="msg_1", files=files)
    assert captured["path"] == "/api/session/ses_1/prompt"
    assert captured["body"]["text"] == "what is this?" and captured["body"]["id"] == "msg_1"
    assert captured["body"]["files"] == files
    captured.clear()
    server.prompt("ses_1", "plain")
    assert "files" not in captured["body"], "text-only prompts must not gain a files key"


def test_opencode_image_capability_gate_names_the_model_and_the_fix():
    from hutch.runtime.opencode import OpenCodeRuntime
    from hutch.runtime.opencode_server import OpenCodeModel
    runtime = OpenCodeRuntime()
    text_only = [OpenCodeModel("opencode", "big-pickle", "Big Pickle", input_modalities=("text",))]
    with pytest.raises(RunAborted) as excinfo:
        runtime._require_image_input_model(text_only, "opencode", "big-pickle")
    assert "does not accept image input" in str(excinfo.value)
    assert "inputs include images" in str(excinfo.value)
    vision = [OpenCodeModel("opencode", "glm-5.3-flash-free", "GLM", input_modalities=("text", "image"))]
    runtime._require_image_input_model(vision, "opencode", "glm-5.3-flash-free")   # no raise
    with pytest.raises(RunAborted) as excinfo:
        runtime._require_image_input_model([], "opencode", "missing")
    assert "could not be verified" in str(excinfo.value)


def test_opencode_stages_verified_image_copies_inside_the_run_workspace(config, store, tmp_path):
    """The session reads only its own folder, so verified bytes are staged there."""
    from hutch.runtime.opencode import OpenCodeRuntime
    bot = store.create_bot(Bot(name="oc-stage-bot", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "Stage", idem_key="os1", request_hash="os1")
    data = REAL_PNG.read_bytes()
    upload = store.add_upload(conv["id"], "calendar.png", "image/png", len(data),
                              hashlib.sha256(data).hexdigest())
    _place_upload(config, conv["id"], upload, data)
    run = _image_run(conv["id"], upload)
    workspace = tmp_path / "run-ws"
    workspace.mkdir()
    ctx = SimpleNamespace(workspace=workspace, config=config)

    staged = OpenCodeRuntime()._stage_chat_images(ctx, run)
    assert [s["name"] for s in staged] == ["calendar.png"]
    assert staged[0]["uri"].startswith("file://")
    staged_path = Path(staged[0]["uri"].removeprefix("file://"))
    assert staged_path.parent.name == "hutch-attachments"
    assert staged_path.read_bytes() == data, "the exact verified bytes are staged"
    assert oct(staged_path.stat().st_mode)[-3:] == "600"

    # a tampered source aborts before anything could be sent
    (workspace_dir_for(config.state_dir, conv["id"]) / f"{upload['id']}-calendar.png").write_bytes(b"\x89PNG tampered")
    with pytest.raises(RunAborted) as excinfo:
        OpenCodeRuntime()._stage_chat_images(ctx, run)
    assert "does not match its recorded digest" in str(excinfo.value)


# ------------------------------------------------------- real free models

@pytest.mark.skipif(not (os.environ.get('HUTCH_LIVE_OPENCODE') == '1' and shutil.which('opencode')),
                    reason='explicit external free-tier inference: set HUTCH_LIVE_OPENCODE=1 and install OpenCode')
def test_real_opencode_free_vision_model_describes_a_real_image(tmp_path, monkeypatch):
    """Live validation against OpenCode's FREE models: no spend, no provider keys.

    Proves the whole chain the user asked to see, composer upload, admission,
    the private isolated OpenCode serve, real vision inference on a real PNG, plus the honest runtime refusal on a text-only free model. Requires explicit
    live-test opt-in as well as the CLI: installing a local CLI must not cause
    ordinary regression runs to send images to an external service. Free-tier
    availability can fail and remains a failed live result when opted in.
    """
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        vision_bot = app.state.store.create_bot(
            Bot(name="free-vision", model="opencode/opencode/glm-5.3-flash-free", tools=[], runtime="opencode"))
        conv, _ = app.state.store.create_conversation(
            vision_bot.id, "Real vision", idem_key="rov", request_hash="rov")
        uploaded = _upload(client, conv["id"], "calendar.png", REAL_PNG.read_bytes()).json()
        sent = _send(client, conv["id"], {"prompt": "What service does this icon represent? One short sentence.",
                                          "image_attachment_ids": [uploaded["id"]]}, key="real-ov-img")
        assert sent.status_code == 201, sent.text
        run = _await_terminal(client, sent.json()["id"], seconds=300)
        assert run["status"] == "succeeded", run.get("error")
        events = client.get(f"/api/v1/tasks/runs/{sent.json()['id']}").json()["events"]
        media = [e for e in events if e.get("type") == "log" and (e.get("data") or {}).get("kind") == "media"]
        assert media, "the transmission record is missing"
        assert media[-1]["data"]["transmitted"] == 1
        detail = client.get(f"/api/v1/conversations/{conv['id']}").json()
        answer = " ".join(m["content"] for m in detail["messages"] if m["role"] == "assistant")
        assert "calendar" in answer.lower(), answer[:300]

        text_bot = app.state.store.create_bot(
            Bot(name="free-text-only", model="opencode/opencode/big-pickle", tools=[], runtime="opencode"))
        conv2, _ = app.state.store.create_conversation(
            text_bot.id, "Real refusal", idem_key="rot", request_hash="rot")
        uploaded2 = _upload(client, conv2["id"], "calendar.png", REAL_PNG.read_bytes()).json()
        sent2 = _send(client, conv2["id"], {"prompt": "What is in this image?",
                                            "image_attachment_ids": [uploaded2["id"]]}, key="real-ot-img")
        assert sent2.status_code == 201, sent2.text
        run2 = _await_terminal(client, sent2.json()["id"], seconds=300)
        assert run2["status"] == "failed", run2.get("status")
        assert "does not accept image input" in (run2.get("error") or ""), run2.get("error")


def _await_terminal(client, run_id: str, seconds: int) -> dict:
    deadline = time.time() + seconds
    run: dict = {}
    while time.time() < deadline:
        run = client.get(f"/api/v1/tasks/runs/{run_id}").json()
        if run.get("terminal"):
            return run
        time.sleep(2)
    raise AssertionError(f"run {run_id} never reached a terminal state in {seconds}s: {run.get('status')}")


def test_supported_image_mimes_match_the_upload_intake():
    from hutch.server.uploads import MIME_BY_SUFFIX
    intake_images = {mime for mime in MIME_BY_SUFFIX.values() if mime.startswith("image/")}
    assert intake_images == set(IMAGE_MIMES), "intake and send capability must agree"
