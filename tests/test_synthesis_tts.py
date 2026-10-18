"""Protocol and pipeline tests for two-host speech rendering.

The provider endpoints are local fake HTTP servers; no real provider is contacted and no
key exists on this machine (recorded in the lane ledger). The tests pin the request shapes
(verbatim text, style as metadata, two prebuilt voices), the failure semantics (bounded
retry, no retry on 4xx, redaction), segmentation, concatenation, and the idempotent
re-render path that must not pay twice.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import struct
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest

from hutch.synthesis.model import (
    Chapter,
    Claim,
    EvidenceSpan,
    Quantity,
    Script,
    SourceCoverage,
    SourceRecord,
    Speaker,
    SynthesisManifest,
    Utterance,
)
from hutch.synthesis.storage import MAX_KIND_BYTES, SynthesisStorage
from hutch.synthesis.tts import (
    DEFAULT_MAX_SEGMENT_CHARS,
    GeminiTTSEngine,
    OpenAITTSEngine,
    TTSCapabilityError,
    TTSError,
    build_transcript,
    concat_wav,
    _segment_key,
    plan_segments,
    plausible_segment,
    render_audio,
    silence_wav,
    synthesize_with_retry,
    _segment_key,
    wav_duration_ms,
    wav_params,
    wrap_pcm,
)

# ---------------------------------------------------------------------------
# fakes


class _Handler(BaseHTTPRequestHandler):
    server_version = "fake-tts/1"

    def log_message(self, *args):  # silence test output
        pass

    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        record: dict = {"path": self.path, "headers": dict(self.headers)}
        try:
            record["json"] = json.loads(raw)
        except ValueError:
            record["json"] = None
        self.server.calls.append(record)  # type: ignore[attr-defined]
        responses = self.server.responses  # type: ignore[attr-defined]
        status, payload, ctype = responses.pop(0) if responses else (500, b"{}", "application/json")
        if callable(payload):
            payload = payload(record)
        if ctype == "drop-response":
            self.close_connection = True
            self.connection.shutdown(2)
            self.connection.close()
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if ctype == "gzip" else ctype)
        if ctype == "gzip":
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.calls = []  # type: ignore[attr-defined]
    server.responses = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)


def pcm_bytes(seconds: float, *, rate: int = 24_000) -> bytes:
    return b"\x00\x10" * int(rate * seconds)


def gemini_response(pcm: bytes, *, parts: int = 1) -> bytes:
    chunk = max(1, len(pcm) // parts)
    payload = {
        "candidates": [{"content": {"parts": [
            {"inlineData": {"data": base64.b64encode(pcm[i:i + chunk]).decode(),
                            "mimeType": "audio/l16;rate=24000"}}
            for i in range(0, len(pcm), chunk)
        ]}}]
    }
    return json.dumps(payload).encode()


# ---------------------------------------------------------------------------
# request shapes


def _turns_a_b():
    from hutch.synthesis.tts import TTSTurn
    return [
        TTSTurn(speaker_id="host_a", speaker_name="Ada", text="The paper claims a 12% gain."),
        TTSTurn(speaker_id="host_b", speaker_name="Ben", text="Only in one benchmark.", style="curious"),
    ]


def test_gemini_multi_speaker_request_shape_and_verbatim_text(fake_server):
    pcm = pcm_bytes(1.0)
    fake_server.responses.append((200, gemini_response(pcm), "application/json"))
    engine = GeminiTTSEngine("test-key", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    audio = engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")

    call = fake_server.calls[0]
    assert call["path"].endswith("/models/gemini-3.8-flash-tts:generateContent")
    assert call["headers"].get("x-goog-api-key") == "test-key"
    body = call["json"]
    parts = body["contents"][0]["parts"]
    assert [p["text"] for p in parts] == ["The paper claims a 12% gain.", "Only in one benchmark."]
    # style travels as metadata, never inside the spoken text
    assert "curious" not in parts[1]["text"]
    assert parts[1]["speech_metadata"] == {"speaker": "Ben", "style": "curious"}
    assert parts[0]["speech_metadata"]["speaker"] == "Ada"
    gen = body["generationConfig"]
    assert gen["responseModalities"] == ["AUDIO"]
    assert gen["responseFormat"]["audio"]["mimeType"] == "AUDIO_L16"
    configs = gen["speechConfig"]["multiSpeakerVoiceConfig"]["speakerVoiceConfigs"]
    assert configs == [
        {"speaker": "Ada", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}},
        {"speaker": "Ben", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
    ]
    assert audio.container == "pcm" and audio.data == pcm and audio.sample_rate == 24_000


def test_gemini_concatenates_multipart_audio(fake_server):
    pcm = pcm_bytes(0.5)
    fake_server.responses.append((200, gemini_response(pcm, parts=3), "application/json"))
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    audio = engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")
    assert audio.data == pcm


def test_gemini_refuses_three_speakers_and_custom_voices(fake_server):
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    from hutch.synthesis.tts import TTSTurn
    three = [TTSTurn("host_a", "Ada", "a"), TTSTurn("host_b", "Ben", "b"), TTSTurn("host_c", "Cy", "c")]
    with pytest.raises(TTSCapabilityError):
        engine.synthesize(three, voices={"host_a": "Puck", "host_b": "Kore", "host_c": "Zephyr"},
                          language="en")
    with pytest.raises(TTSCapabilityError) as exc:
        engine.synthesize(_turns_a_b(), voices={"host_a": "voice_abc123", "host_b": "Kore"}, language="en")
    assert "individually" in str(exc.value)
    assert fake_server.calls == []  # nothing was sent


def test_openai_per_turn_request_shape(fake_server):
    fake_server.responses.append((200, pcm_bytes(0.5), "audio/l16"))
    engine = OpenAITTSEngine("sk-test", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1",
                             allow_custom_endpoint=True)
    from hutch.synthesis.tts import TTSTurn
    audio = engine.synthesize([TTSTurn("host_a", "Ada", "Hello.", style="warm")],
                              voices={"host_a": "alloy"}, language="en")
    call = fake_server.calls[0]
    assert call["path"].endswith("/audio/speech")
    assert call["headers"].get("Authorization") == "Bearer sk-test"
    assert call["json"]["voice"] == "alloy"
    assert call["json"]["input"] == "Hello."
    assert call["json"]["response_format"] == "pcm"
    assert call["json"]["instructions"] == "warm"
    assert audio.container == "pcm"

    with pytest.raises(TTSCapabilityError):
        engine.synthesize(_turns_a_b(), voices={"host_a": "alloy", "host_b": "echo"}, language="en")
    assert len(fake_server.calls) == 1


# ---------------------------------------------------------------------------
# failure semantics


def test_retry_bounded_on_rate_limit_but_not_ambiguous_5xx_or_400(fake_server):
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    fake_server.responses.append((429, b"{}", "application/json"))
    fake_server.responses.append((200, gemini_response(pcm_bytes(0.4)), "application/json"))
    sleeps: list[float] = []
    audio = synthesize_with_retry(engine, _turns_a_b(),
                                  voices={"host_a": "Puck", "host_b": "Kore"}, language="en",
                                  attempts=3, sleep=sleeps.append)
    assert len(fake_server.calls) == 2 and sleeps == [0.5]
    assert audio.data

    fake_server.responses.append((503, b"{}", "application/json"))
    with pytest.raises(TTSError) as exc:
        synthesize_with_retry(engine, _turns_a_b(),
                              voices={"host_a": "Puck", "host_b": "Kore"}, language="en",
                              attempts=3, sleep=sleeps.append)
    assert exc.value.uncertain is True and exc.value.retryable is False
    assert len(fake_server.calls) == 3 and sleeps == [0.5]

    fake_server.responses.append((400, b'{"error": "bad request"}', "application/json"))
    with pytest.raises(TTSError) as exc:
        synthesize_with_retry(engine, _turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"},
                              language="en", attempts=3, sleep=sleeps.append)
    assert exc.value.retryable is False and exc.value.status == 400
    assert len(fake_server.calls) == 4  # no retry after the 400


def test_provider_key_never_appears_in_errors(fake_server):
    engine = GeminiTTSEngine("super-secret-value", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    fake_server.responses.append((500, b'{"error": "super-secret-value leaked"}', "application/json"))
    with pytest.raises(TTSError) as exc:
        engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")
    assert "super-secret-value" not in str(exc.value)


def test_custom_endpoint_needs_explicit_binding():
    with pytest.raises(TTSError) as exc:
        GeminiTTSEngine("ambient-key", base_url="https://evil.example.test/v1beta")
    assert "refusing to send" in str(exc.value)
    # the official endpoint is accepted without the flag
    engine = GeminiTTSEngine("k")
    assert engine.base_url.startswith("https://generativelanguage.googleapis.com")


# ---------------------------------------------------------------------------
# segmentation and WAV handling


def _script(utterances: list[tuple[str, str, int]], *, version: int = 1) -> Script:
    chapter0 = Chapter(index=0, title="Intro")
    chapter1 = Chapter(index=1, title="Evidence")
    return Script(
        manifest_id="syn_" + "0" * 16, manifest_revision=version, version=version,
        speakers=[Speaker(id="host_a", name="Ada", role="guide", voice={"gemini": "Puck", "openai": "alloy"}),
                  Speaker(id="host_b", name="Ben", role="probe", voice={"gemini": "Kore", "openai": "echo"})],
        chapters=[chapter0, chapter1],
        utterances=[Utterance(id=f"utt_{i}", speaker_id=s, text=t, pause_after_ms=p,
                              chapter_id=chapter0.id if i < 2 else chapter1.id)
                    for i, (s, t, p) in enumerate(utterances)],
    )


def test_plan_segments_char_budget_and_pause_boundaries():
    script = _script([
        ("host_a", "x" * 100, 0),
        ("host_b", "y" * 100, 0),
        ("host_a", "z" * 100, 700),   # explicit pause closes the segment
        ("host_b", "w" * 100, 0),
    ])
    segs = plan_segments(script, max_chars=250)
    assert [len(s.turns) for s in segs] == [2, 1, 1]
    assert segs[1].pause_after_ms == 700 and segs[2].pause_after_ms == 0
    assert segs[0].chapter_ids == [script.chapters[0].id]
    assert segs[1].chapter_ids == [script.chapters[1].id]

    long = _script([("host_a", "x" * 4000, 0)])
    with pytest.raises(TTSCapabilityError) as exc:
        plan_segments(long, max_chars=1000)
    assert "will not be split silently" in str(exc.value)


def test_plan_segments_single_voice_engine_splits_speakers():
    script = _script([("host_a", "one", 0), ("host_b", "two", 0), ("host_a", "three", 0)])
    segs = plan_segments(script, max_chars=1000, multi_speaker=False)
    assert [s.speaker_ids for s in segs] == [["host_a"], ["host_b"], ["host_a"]]


def test_concat_wav_with_pause_and_format_mismatch():
    a = wrap_pcm(pcm_bytes(1.0), rate=24_000)
    b = wrap_pcm(pcm_bytes(0.5), rate=24_000)
    joined = concat_wav([a, b], [500, 0])
    ms = wav_duration_ms(joined)
    assert abs(ms - 2000) <= 5
    other = wrap_pcm(pcm_bytes(0.2), rate=16_000)
    with pytest.raises(ValueError):
        concat_wav([a, other])
    assert wav_params(joined)[0] == 24_000


def test_plausible_segment_flags_empty_and_absurd():
    tiny = wrap_pcm(b"", rate=24_000)
    assert plausible_segment(tiny, 1500)
    quick = silence_wav(100, rate=24_000, channels=1, sample_width=2)
    assert plausible_segment(quick, 1500), "0.1s of audio cannot read 1500 characters"
    fine = silence_wav(2000, rate=24_000, channels=1, sample_width=2)
    assert plausible_segment(fine, 30) == []  # 2s for a short line is believable


# ---------------------------------------------------------------------------
# end-to-end render with the fake provider (no real credentials)


def _manifest_and_script(tmp_manifest_id="syn_" + "1" * 16):
    src = SourceRecord(kind="thread", identity="https://social.example/t/1",
                       coverage=SourceCoverage(state="complete", expected_units=1, accessible_units=1))
    span = EvidenceSpan(source_id=src.id, source_revision=1, container="post",
                        locator={"post_id": "p1"}, quote="hit rate rose 12%", quote_kind="quoted")
    claim = Claim(id="cl_1", text="The hit rate rose 12%.", spans=[span.id],
                  quantities=[Quantity(value=12.0, unit="%", as_reported="hit rate rose 12%")])
    manifest = SynthesisManifest(id=tmp_manifest_id, sources=[src], spans=[span], claims=[claim])
    chapter0 = Chapter(index=0, title="Intro")
    chapter1 = Chapter(index=1, title="Evidence")
    script = Script(
        id="scr_" + "2" * 16, manifest_id=manifest.id, manifest_revision=1, version=1,
        speakers=[Speaker(id="host_a", name="Ada", role="guide", voice={"gemini": "Puck"}),
                  Speaker(id="host_b", name="Ben", role="probe", voice={"gemini": "Kore"})],
        chapters=[chapter0, chapter1],
        utterances=[
            Utterance(id="utt_1", speaker_id="host_a", text="Welcome. The hit rate rose 12%.",
                      claim_ids=["cl_1"], span_ids=[span.id], chapter_id=chapter0.id),
            Utterance(id="utt_2", speaker_id="host_b", text="Where does that number come from?",
                      chapter_id=chapter0.id, kind="question"),
            Utterance(id="utt_3", speaker_id="host_a", text="From the thread's measurement.",
                      claim_ids=["cl_1"], chapter_id=chapter1.id),
            Utterance(id="utt_4", speaker_id="host_b", text="And the caveat is it is one source.",
                      chapter_id=chapter1.id, pause_after_ms=600),
        ],
    )
    return manifest, script


def test_render_audio_end_to_end_and_idempotent_retry(config, store, fake_server):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    fake_server.responses.append((200, gemini_response(pcm_bytes(2.0)), "application/json"))
    fake_server.responses.append((200, gemini_response(pcm_bytes(2.0)), "application/json"))
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)

    result = render_audio(manifest, script, engines=[engine], storage=storage, store=store,
                          output_name="overview.wav")
    assert result.segments_rendered == 2 and result.segments_reused == 0
    assert len(fake_server.calls) == 2

    audio_row = store.get_synthesis_artifact(result.audio_artifact_id)
    assert audio_row["status"] == "validated" and audio_row["sha256"] == result.audio_sha256
    bytes_back = storage.read_artifact(audio_row["storage_path"], audio_row["sha256"],
                                       int(audio_row["bytes"]))
    assert wav_duration_ms(bytes_back) == result.duration_ms

    transcript_row = store.get_synthesis_artifact(result.transcript_artifact_id)
    vtt = storage.read_artifact(transcript_row["storage_path"], transcript_row["sha256"],
                                int(transcript_row["bytes"])).decode("utf-8")
    assert vtt.startswith("WEBVTT")
    assert "Ada: Welcome. The hit rate rose 12%." in vtt
    assert "Ben: Where does that number come from?" in vtt
    assert "estimate" in vtt

    segments = store.list_synthesis_artifacts(manifest.id, kind="audio_segment")
    assert len(segments) == 2
    assert {int(a["meta"]["segment_index"]) for a in segments} == {0, 1}

    # Retry of the identical render reuses every verified segment and both outputs.
    again = render_audio(manifest, script, engines=[engine], storage=storage, store=store,
                         output_name="overview.wav")
    assert again.segments_reused == 2 and again.segments_rendered == 0
    assert len(fake_server.calls) == 2  # no second provider call, no second charge
    assert again.audio_sha256 == result.audio_sha256
    assert again.transcript_sha256 == result.transcript_sha256
    assert any("reused" in w for w in again.warnings)


def test_render_audio_rejects_stale_script_revision(config, store, fake_server):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    script.manifest_revision = 99
    with pytest.raises(TTSError) as exc:
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)
    assert "current revision" in str(exc.value)
    assert fake_server.calls == []


def test_render_audio_enforces_aggregate_limit_before_staging(config, store, fake_server, monkeypatch):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    fake_server.responses.append((200, gemini_response(pcm_bytes(2.0)), "application/json"))
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    monkeypatch.setattr("hutch.synthesis.tts.MAX_RUN_SYNTHESIS_BYTES", 64)

    with pytest.raises(TTSError, match="aggregate audio-byte limit"):
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)

    assert len(fake_server.calls) == 1
    assert store.list_synthesis_artifacts(manifest.id) == []
    assert not storage.staging.exists() or list(storage.staging.iterdir()) == []


def test_render_audio_enforces_cumulative_limit_for_new_segments(config, store, fake_server, monkeypatch):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    pcm = pcm_bytes(2.0)
    fake_server.responses.extend([
        (200, gemini_response(pcm), "application/json"),
        (200, gemini_response(pcm), "application/json"),
    ])
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    one_segment = len(wrap_pcm(pcm, rate=24000, channels=1, sample_width=2))
    monkeypatch.setattr("hutch.synthesis.tts.MAX_RUN_SYNTHESIS_BYTES", one_segment + 1)

    with pytest.raises(TTSError, match="aggregate audio-byte limit"):
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)

    assert len(fake_server.calls) == 2
    assert len(store.list_synthesis_artifacts(manifest.id, kind="audio_segment")) == 1
    assert store.find_synthesis_artifact(manifest.id, "audio_overview", script.version) is None


def test_render_audio_does_not_retry_unresolved_effect(config, store, fake_server):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    segment = plan_segments(script, manifest=manifest, multi_speaker=True)[0]
    language = manifest.language
    model = str(getattr(engine, "model", engine.name))
    key = _segment_key(manifest.id, script.version, segment, engine,
                       {speaker.id: speaker.voice[engine.name] for speaker in script.speakers},
                       model, language)
    store.begin_synthesis_effect(
        effect_id=f"eff_{hashlib.sha256(key.encode()).hexdigest()[:16]}",
        plan_id=manifest.id, step_id=f"segment-{segment.index}", kind="tts.segment",
        idempotency_key=key, request_hash=key.split(":", 1)[1],
        target={"segment": segment.index, "engine": engine.name, "model": model,
                "speakers": segment.speaker_ids, "chars": segment.chars})

    with pytest.raises(TTSError, match="previous TTS attempt is prepared"):
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)
    assert fake_server.calls == []


def test_ambiguous_provider_disconnect_is_not_retried(config, store, fake_server):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    fake_server.responses.append((200, b"", "drop-response"))
    segment = plan_segments(script, manifest=manifest, multi_speaker=True)[0]
    key = _segment_key(manifest.id, script.version, segment, engine,
                       {speaker.id: speaker.voice[engine.name] for speaker in script.speakers},
                       engine.model, manifest.language)

    with pytest.raises(TTSError) as exc:
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)

    assert exc.value.uncertain is True
    assert len(fake_server.calls) == 1
    assert store.find_synthesis_effect(key)["status"] == "uncertain"


def test_provider_response_is_bounded_while_streaming(fake_server, monkeypatch):
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    monkeypatch.setitem(MAX_KIND_BYTES, "audio_segment", 1)
    fake_server.responses.append((200, b"x" * 1100, "application/json"))

    with pytest.raises(TTSError, match="bounded response size") as exc:
        engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")
    assert exc.value.uncertain is True
    assert len(fake_server.calls) == 1


def test_compressed_provider_response_is_rejected_before_decompression(fake_server, monkeypatch):
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    monkeypatch.setitem(MAX_KIND_BYTES, "audio_segment", 1)
    fake_server.responses.append((200, gzip.compress(b"x" * 100_000), "gzip"))

    with pytest.raises(TTSError, match="compressed TTS responses") as exc:
        engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")
    assert exc.value.uncertain is True
    assert len(fake_server.calls) == 1


def test_oversized_5xx_response_remains_an_uncertain_effect(fake_server):
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    fake_server.responses.append((503, b"x" * 1_000_001, "application/json"))

    with pytest.raises(TTSError, match="bounded response size") as exc:
        engine.synthesize(_turns_a_b(), voices={"host_a": "Puck", "host_b": "Kore"}, language="en")
    assert exc.value.uncertain is True
    assert exc.value.status == 503


def test_successful_effect_with_missing_artifact_is_not_re_rendered(config, store, fake_server):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    fake_server.responses.extend([
        (200, gemini_response(pcm_bytes(2.0)), "application/json"),
        (200, gemini_response(pcm_bytes(2.0)), "application/json"),
    ])
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    render_audio(manifest, script, engines=[engine], storage=storage, store=store)
    before = len(fake_server.calls)
    segment_row = store.list_synthesis_artifacts(manifest.id, kind="audio_segment")[0]
    (config.synthesis_dir / segment_row["storage_path"]).unlink()

    with pytest.raises(TTSError, match="stored audio failed verification"):
        render_audio(manifest, script, engines=[engine], storage=storage, store=store)
    assert len(fake_server.calls) == before


def test_concurrent_render_claims_only_one_tts_effect(config, store, fake_server, monkeypatch):
    manifest, script = _manifest_and_script()
    storage = SynthesisStorage(config)
    fake_server.responses.extend([
        (200, gemini_response(pcm_bytes(2.0)), "application/json"),
        (200, gemini_response(pcm_bytes(2.0)), "application/json"),
    ])
    engine = GeminiTTSEngine("k", base_url=f"http://127.0.0.1:{fake_server.server_port}/v1beta",
                             allow_custom_endpoint=True)
    barrier = threading.Barrier(2)
    local = threading.local()
    original = store.begin_synthesis_effect

    def synchronized_begin(**kwargs):
        if kwargs["kind"] == "tts.segment" and not getattr(local, "waited", False):
            local.waited = True
            barrier.wait()
        return original(**kwargs)

    monkeypatch.setattr(store, "begin_synthesis_effect", synchronized_begin)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(render_audio, manifest, script, engines=[engine], storage=storage, store=store)
                   for _ in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except TTSError as exc:
                outcomes.append(exc)

    assert sum(not isinstance(outcome, TTSError) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, TTSError) for outcome in outcomes) == 1
    assert len(fake_server.calls) == 2


def test_transcript_cues_start_and_end_monotonically():
    manifest, script = _manifest_and_script()
    segs = plan_segments(script, max_chars=1000)
    durations = [2000] * len(segs)
    pauses = [s.pause_after_ms for s in segs]
    t = build_transcript(manifest, script, segs, durations, pauses)
    cues = t["cues"]
    assert len(cues) == 4
    assert cues[0]["start_ms"] == 0
    for a, b in zip(cues, cues[1:]):
        assert b["start_ms"] >= a["end_ms"] - 1
    assert cues[0]["speaker"] == "Ada" and cues[1]["speaker"] == "Ben"
    assert t["alignment"] == "segment-duration estimate"
