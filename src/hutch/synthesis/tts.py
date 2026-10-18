"""Two-host speech rendering: provider adapters, segmentation, assembly, transcripts.

Design against the verified provider facts (R3/R4, 2026-10-11):

* Gemini TTS multi-speaker requests carry **at most two prebuilt voices**; custom or
  replicated voices require per-turn synthesis. ``GeminiTTSEngine`` refuses anything else
  with a capability error instead of silently degrading.
* Unary requests return WAV; streaming returns headerless 16-bit PCM. This module asks
  for ``AUDIO_L16`` so segments concatenate as raw frames, and always wraps stored
  segments in a real WAV container — complete encoded files are never treated as samples.
* ``text`` is strictly verbatim; delivery lives in ``style`` and R3 whitelisted vocal
  tags. Stage directions in text are refused before a request is made.
* Providers are only called with a key explicitly bound to that provider's official host
  (or an explicit custom endpoint, which never receives an ambient key).

Money/duplication rules: every provider call is journaled in the effect ledger keyed by a
content hash (manifest + script version + segment text + voices + engine/model). A retry
reuses a verified stored segment instead of paying twice; an uncertain outcome reconciles
by reusing the stored artifact when it exists and re-rendering only when it does not.
"""

from __future__ import annotations

import base64
import hashlib
import io
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol
from urllib.parse import urlsplit

import httpx

from .model import Script, SynthesisManifest, Utterance, spoken_text_problems, utterance_number_problems
from .storage import MAX_KIND_BYTES, MAX_RUN_SYNTHESIS_BYTES, SynthesisStorage, new_artifact_id

# ---------------------------------------------------------------------------
# vocabulary

DEFAULT_MAX_SEGMENT_CHARS = 1_500
MAX_SEGMENT_CHARS = 4_000
PAUSE_BOUNDARY_MS = 200
MAX_PAUSE_MS = 10_000
MAX_SCRIPT_CHARS = 1_000_000
MAX_RUN_SYNTHESIS_SEGMENTS = 256
MAX_TTS_ERROR_BYTES = 1_000_000

GEMINI_HOST = "generativelanguage.googleapis.com"
OPENAI_HOST = "api.openai.com"


class TTSError(Exception):
    """A speech request failed. ``retryable`` distinguishes provider/network hiccups
    from requests that must be fixed before asking again."""

    def __init__(self, message: str, *, retryable: bool = False, status: int = 0,
                 uncertain: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.uncertain = uncertain


class TTSCapabilityError(TTSError):
    """The provider cannot express this request (e.g. three speakers in one Gemini
    request); the caller must change the strategy, not retry."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


@dataclass
class TTSTurn:
    speaker_id: str  # stable script speaker id ("host_a")
    speaker_name: str  # provider-facing name (unique, human-safe)
    text: str  # verbatim; no stage directions
    style: str = ""


@dataclass
class TTSAudio:
    data: bytes
    container: str  # "pcm" or "wav"
    sample_rate: int
    channels: int = 1
    sample_width: int = 2
    provider_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSCapabilities:
    multi_speaker: bool
    max_chars_per_request: int
    formats: tuple[str, ...]
    notes: list[str] = field(default_factory=list)


class TTSEngine(Protocol):
    name: str

    def capabilities(self) -> TTSCapabilities: ...
    def synthesize(self, turns: list[TTSTurn], *, voices: dict[str, str], language: str) -> TTSAudio: ...


# ---------------------------------------------------------------------------
# WAV helpers (pure Python; no encoded-container concatenation)


def wav_params(data: bytes) -> tuple[int, int, int, int]:
    """(rate, channels, sample_width, frames) of a WAV container."""
    with wave.open(io.BytesIO(data), "rb") as reader:
        return (reader.getframerate(), reader.getnchannels(), reader.getsampwidth(), reader.getnframes())


def wrap_pcm(pcm: bytes, *, rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(rate)
        writer.writeframes(pcm)
    return out.getvalue()


def _ambiguous_response_status(status: int) -> bool:
    return status == 200 or status == 408 or 500 <= status <= 599


def _post_bounded(url: str, *, json_body: dict[str, Any], timeout_s: float,
                  headers: dict[str, str], max_response_bytes: int) -> httpx.Response:
    """Stream a provider response under a hard memory bound.

    A transport failure after the request starts is ambiguous: the paid operation may have
    completed. Only failures known to occur before sending are safe for automatic retry.
    """
    try:
        request_headers = {**headers, "Accept-Encoding": "identity"}
        with httpx.stream("POST", url, json=json_body, timeout=timeout_s,
                          headers=request_headers) as response:
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise TTSError("compressed TTS responses are not accepted", status=response.status_code,
                               uncertain=_ambiguous_response_status(response.status_code))
            limit = max_response_bytes if response.status_code == 200 else MAX_TTS_ERROR_BYTES
            body = bytearray()
            for chunk in response.iter_raw():
                if len(body) + len(chunk) > limit:
                    raise TTSError("TTS response exceeded its bounded response size",
                                   status=response.status_code,
                                   uncertain=_ambiguous_response_status(response.status_code))
                body.extend(chunk)
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=bytes(body), request=response.request)
    except TTSError:
        raise
    except httpx.HTTPError as exc:
        definitely_not_sent = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout))
        raise TTSError(f"TTS request failed: {type(exc).__name__}",
                       retryable=definitely_not_sent, uncertain=not definitely_not_sent) from exc


def _pcm_frames(data: bytes) -> tuple[bytes, int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        return reader.readframes(reader.getnframes()), reader.getframerate(), reader.getnchannels(), reader.getsampwidth()


def silence_wav(ms: int, *, rate: int, channels: int, sample_width: int) -> bytes:
    frames = max(0, int(round(rate * ms / 1000.0)))
    return wrap_pcm(b"\x00" * frames * channels * sample_width, rate=rate,
                    channels=channels, sample_width=sample_width)


def concat_wav(parts: list[bytes], pauses_ms: Optional[list[int]] = None, *,
               max_bytes: Optional[int] = None) -> bytes:
    """Concatenate decoded WAV frames (with optional silence between parts).

    Every part must share rate/channels/width; anything else raises instead of
    producing garbled audio.
    """
    if not parts:
        raise ValueError("no audio parts to concatenate")
    rate, channels, width, _ = wav_params(parts[0])
    estimated_bytes = 44
    for idx, part in enumerate(parts[1:], start=1):
        prate, pch, pwidth, _ = wav_params(part)
        if (prate, pch, pwidth) != (rate, channels, width):
            raise ValueError(
                f"segment {idx} has format {prate}Hz/{pch}ch/{pwidth * 8}bit but segment 0 is "
                f"{rate}Hz/{channels}ch/{width * 8}bit; refusing to concatenate")
    for idx, part in enumerate(parts):
        _rate, _channels, _width, frames = wav_params(part)
        estimated_bytes += frames * channels * width
        if pauses_ms and idx < len(pauses_ms) and pauses_ms[idx] > 0:
            estimated_bytes += int(round(rate * min(pauses_ms[idx], MAX_PAUSE_MS) / 1000.0)) * channels * width
    if max_bytes is not None and estimated_bytes > max_bytes:
        raise ValueError(f"assembled audio exceeds the {max_bytes // 1_000_000} MB limit")
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        for idx, part in enumerate(parts):
            frames, _, _, _ = _pcm_frames(part)
            writer.writeframes(frames)
            if pauses_ms and idx < len(pauses_ms) and pauses_ms[idx] > 0:
                writer.writeframes(b"\x00" * int(round(rate * min(pauses_ms[idx], MAX_PAUSE_MS) / 1000.0))
                                   * channels * width)
    return out.getvalue()


def wav_duration_ms(data: bytes) -> int:
    rate, _, _, frames = wav_params(data)
    return int(round(frames * 1000.0 / rate)) if rate else 0


def plausible_segment(data: bytes, expected_chars: int) -> list[str]:
    """Sanity-check a rendered segment: non-empty and in a believable duration band.

    Speech runs roughly 8-18 characters/second; the band is intentionally wide because
    hosts pause, but a 3 kB segment claiming to read 1,500 characters is broken.
    """
    problems: list[str] = []
    try:
        rate, channels, width, frames = wav_params(data)
    except wave.Error as exc:
        return [f"not a readable WAV container: {exc}"]
    if frames <= 0:
        return ["segment has zero audio frames"]
    seconds = frames / float(rate or 1)
    expected = max(1.0, expected_chars / 18.0)
    if seconds < expected * 0.2:
        problems.append(f"segment is {seconds:.1f}s but text implies at least ~{expected:.1f}s")
    if seconds > expected * 6 + 30:
        problems.append(f"segment is {seconds:.1f}s for {expected_chars} characters; possible loop or silence")
    if channels * width not in (1, 2, 4):
        problems.append(f"unexpected sample layout: {channels}ch x {width * 8}bit")
    return problems


# ---------------------------------------------------------------------------
# segment planning


@dataclass
class SegmentPlan:
    index: int
    utterance_ids: list[str]
    chapter_ids: list[str]
    speaker_ids: list[str]
    turns: list[TTSTurn]
    chars: int
    pause_after_ms: int = 0


def plan_segments(script: Script, *, max_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
                  manifest: Optional[SynthesisManifest] = None,
                  multi_speaker: bool = True) -> list[SegmentPlan]:
    """Group utterances into provider requests without splitting any utterance.

    An utterance longer than the budget is refused: silently splitting it would break the
    utterance↔audio mapping a correction must follow. Explicit pauses (>= 200 ms) and
    chapter boundaries close a segment so assembly can honour them. Engines that render
    one voice per request (``multi_speaker=False``) get one speaker per segment.
    """
    if max_chars < 50:
        raise ValueError("max_chars is too small to be useful")
    if manifest is not None:
        _validate_script_text(script, manifest)
    names = {s.id: s.name for s in script.speakers}
    # Provider-facing names must be unique and free of characters TTS would read oddly.
    seen_names: set[str] = set()
    for s in script.speakers:
        clean = " ".join(str(s.name).split())[:40]
        if not clean or clean in seen_names:
            raise TTSCapabilityError("speaker names must be non-empty and unique before synthesis")
        seen_names.add(clean)

    segments: list[SegmentPlan] = []
    current: list[Utterance] = []

    def flush(pause_after_ms: int = 0) -> None:
        if not current:
            return
        turns: list[TTSTurn] = []
        for u in current:
            problems = spoken_text_problems(u.text)
            if problems:
                raise TTSCapabilityError(f"utterance {u.id}: {problems[0]}")
            turns.append(TTSTurn(speaker_id=u.speaker_id, speaker_name=names[u.speaker_id],
                                 text=u.text, style=u.style))
        chapters: list[str] = []
        for u in current:
            if u.chapter_id and u.chapter_id not in chapters:
                chapters.append(u.chapter_id)
        segments.append(SegmentPlan(
            index=len(segments),
            utterance_ids=[u.id for u in current],
            chapter_ids=chapters,
            speaker_ids=list(dict.fromkeys(u.speaker_id for u in current)),
            turns=turns,
            chars=sum(len(u.text) for u in current),
            pause_after_ms=pause_after_ms,
        ))
        current.clear()

    for u in script.utterances:
        if len(u.text) > max_chars:
            raise TTSCapabilityError(
                f"utterance {u.id} is {len(u.text)} characters, over the {max_chars} budget; "
                "split it in the script (it will not be split silently)")
        if current and sum(len(x.text) for x in current) + len(u.text) > max_chars:
            flush()
        if current and (u.chapter_id or "") != (current[-1].chapter_id or ""):
            flush()
        if current and not multi_speaker and current[-1].speaker_id != u.speaker_id:
            flush()
        current.append(u)
        if u.pause_after_ms >= PAUSE_BOUNDARY_MS:
            flush(pause_after_ms=min(u.pause_after_ms, MAX_PAUSE_MS))
    flush()
    if not segments:
        raise TTSCapabilityError("the script has no utterances to synthesize")
    return segments


def _validate_script_text(script: Script, manifest: SynthesisManifest) -> None:
    problems: list[str] = []
    for u in script.utterances:
        if u.claim_ids:
            unknown = [cid for cid in u.claim_ids if manifest.claim(cid) is None]
            if unknown:
                problems.append(f"utterance {u.id} cites unknown claims {unknown}")
        for p in utterance_number_problems(u, manifest):
            problems.append(p)
        for p in spoken_text_problems(u.text):
            problems.append(f"utterance {u.id}: {p}")
    if problems:
        raise TTSCapabilityError("; ".join(problems[:5]))


# ---------------------------------------------------------------------------
# engines


def _official_or_explicit(base_url: str, host: str, allow_custom: bool) -> str:
    parts = urlsplit(base_url)
    if (parts.scheme == "https" and (parts.hostname or "").lower() == host
            and parts.port in (None, 443)):
        return base_url
    if allow_custom:
        return base_url
    raise TTSError(
        f"refusing to send this provider key to {base_url or 'a custom endpoint'}; "
        "use the official endpoint or an explicit connection (allow_custom_endpoint=True)")


def _redact(text: str, key: str) -> str:
    if key and key in text:
        text = text.replace(key, "***")
    return text[:600]


class GeminiTTSEngine:
    """Google Gemini TTS. Multi-speaker requests support exactly two prebuilt voices."""

    name = "gemini"

    def __init__(self, api_key: str, *, model: str = "gemini-3.8-flash-tts",
                 base_url: str = f"https://{GEMINI_HOST}/v1beta",
                 allow_custom_endpoint: bool = False, timeout_s: float = 120.0):
        if not api_key:
            raise TTSError("no Gemini API key configured")
        self.api_key = api_key
        self.model = model
        self.base_url = _official_or_explicit(base_url, GEMINI_HOST, allow_custom_endpoint).rstrip("/")
        self.timeout_s = timeout_s

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            multi_speaker=True, max_chars_per_request=MAX_SEGMENT_CHARS,
            formats=("AUDIO_L16", "AUDIO_WAV"),
            notes=["multi-speaker requests support exactly two prebuilt voices",
                   "custom/replicated voices require per-turn synthesis"],
        )

    def synthesize(self, turns: list[TTSTurn], *, voices: dict[str, str], language: str) -> TTSAudio:
        if not turns:
            raise TTSCapabilityError("no turns to synthesize")
        speakers = list(dict.fromkeys(t.speaker_id for t in turns))
        if len(speakers) > 2:
            raise TTSCapabilityError(
                "Gemini multi-speaker requests support at most two voices; split the segment "
                "or use the per-turn engine")
        chars = sum(len(t.text) for t in turns)
        if chars > MAX_SEGMENT_CHARS:
            raise TTSCapabilityError(f"segment is {chars} characters, over {MAX_SEGMENT_CHARS}")
        for sid in speakers:
            voice = voices.get(sid, "")
            if not voice:
                raise TTSCapabilityError(f"speaker {sid} has no Gemini voice configured")
            if voice.startswith(("voice_", "voicekey_")):
                raise TTSCapabilityError(
                    f"speaker {sid} uses a custom voice ({voice[:12]}...), which cannot ride a "
                    "multi-speaker request; synthesize turns individually")
        parts = []
        for t in turns:
            part: dict[str, Any] = {"text": t.text}
            meta: dict[str, Any] = {"speaker": t.speaker_name}
            if t.style:
                meta["style"] = t.style
            part["speech_metadata"] = meta
            parts.append(part)
        speaker_configs = []
        for sid in speakers:
            name = next(t.speaker_name for t in turns if t.speaker_id == sid)
            speaker_configs.append({
                "speaker": name,
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[sid]}},
            })
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "responseFormat": {"audio": {"mimeType": "AUDIO_L16", "sampleRate": 24000}},
                "speechConfig": {
                    "multiSpeakerVoiceConfig": {"speakerVoiceConfigs": speaker_configs}
                },
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        encoded_limit = MAX_KIND_BYTES["audio_segment"] * 4 // 3 + 1024
        response = _post_bounded(url, json_body=payload, timeout_s=self.timeout_s,
                                 headers={"x-goog-api-key": self.api_key},
                                 max_response_bytes=encoded_limit)
        if response.status_code != 200:
            retryable = response.status_code == 429
            uncertain = _ambiguous_response_status(response.status_code)
            raise TTSError(
                f"Gemini TTS returned {response.status_code}: {_redact(response.text, self.api_key)}",
                retryable=retryable, status=response.status_code, uncertain=uncertain)
        try:
            body = response.json()
            parts_out = body["candidates"][0]["content"]["parts"]
            chunks = []
            decoded_total = 0
            for part in parts_out:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    encoded = inline["data"]
                    # Base64 padding is at most two bytes. Reject based on its upper bound
                    # before allocating the decoded chunk.
                    padding = len(encoded) - len(encoded.rstrip("="))
                    decoded_size = (len(encoded) * 3) // 4 - padding
                    if decoded_total + decoded_size > MAX_KIND_BYTES["audio_segment"]:
                        raise TTSError("decoded TTS segment exceeds its storage size limit", uncertain=True)
                    decoded = base64.b64decode(encoded)
                    decoded_total += len(decoded)
                    chunks.append(decoded)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTSError(f"Gemini TTS response had no audio: {_redact(response.text[:1000], self.api_key)}"
                           ) from exc
        if not chunks:
            raise TTSError("Gemini TTS response contained no audio payload")
        mime = ""
        try:
            mime = (parts_out[0].get("inlineData") or parts_out[0].get("inline_data") or {}).get("mimeType", "")
        except Exception:  # noqa: BLE001
            pass
        pcm = b"".join(chunks)
        return TTSAudio(data=pcm, container="pcm", sample_rate=24_000, channels=1, sample_width=2,
                        provider_meta={"provider": "gemini", "model": self.model,
                                       "mime": mime or "audio/l16;rate=24000"})


class OpenAITTSEngine:
    """OpenAI speech endpoint: one voice per request, so turns are synthesized separately."""

    name = "openai"

    def __init__(self, api_key: str, *, model: str = "gpt-4o-mini-tts",
                 base_url: str = f"https://{OPENAI_HOST}/v1",
                 allow_custom_endpoint: bool = False, timeout_s: float = 120.0):
        if not api_key:
            raise TTSError("no OpenAI API key configured")
        self.api_key = api_key
        self.model = model
        self.base_url = _official_or_explicit(base_url, OPENAI_HOST, allow_custom_endpoint).rstrip("/")
        self.timeout_s = timeout_s

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            multi_speaker=False, max_chars_per_request=MAX_SEGMENT_CHARS,
            formats=("pcm", "wav"),
            notes=["one voice per request; dialogue needs per-turn synthesis"],
        )

    def synthesize(self, turns: list[TTSTurn], *, voices: dict[str, str], language: str) -> TTSAudio:
        speakers = list(dict.fromkeys(t.speaker_id for t in turns))
        if len(speakers) != 1:
            raise TTSCapabilityError(
                "OpenAI speech requests carry one voice; synthesize one speaker per call")
        sid = speakers[0]
        voice = voices.get(sid, "")
        if not voice:
            raise TTSCapabilityError(f"speaker {sid} has no OpenAI voice configured")
        text = " ".join(t.text for t in turns)
        style = next((t.style for t in turns if t.style), "")
        instructions = style or None
        payload: dict[str, Any] = {"model": self.model, "input": text, "voice": voice,
                                   "response_format": "pcm"}
        if instructions:
            payload["instructions"] = instructions
        url = f"{self.base_url}/audio/speech"
        response = _post_bounded(url, json_body=payload, timeout_s=self.timeout_s,
                                 headers={"Authorization": f"Bearer {self.api_key}"},
                                 max_response_bytes=MAX_KIND_BYTES["audio_segment"])
        if response.status_code != 200:
            retryable = response.status_code == 429
            uncertain = _ambiguous_response_status(response.status_code)
            raise TTSError(
                f"OpenAI TTS returned {response.status_code}: {_redact(response.text, self.api_key)}",
                retryable=retryable, status=response.status_code, uncertain=uncertain)
        if not response.content:
            raise TTSError("OpenAI TTS returned an empty audio body")
        return TTSAudio(data=response.content, container="pcm", sample_rate=24_000, channels=1,
                        sample_width=2,
                        provider_meta={"provider": "openai", "model": self.model, "mime": "audio/l16"})


def synthesize_with_retry(engine: TTSEngine, turns: list[TTSTurn], *, voices: dict[str, str],
                          language: str, attempts: int = 3,
                          sleep: Callable[[float], None] = time.sleep) -> TTSAudio:
    """Retry explicit rate limits and pre-send failures; ambiguous outcomes stop."""
    last: Optional[TTSError] = None
    for attempt in range(max(1, attempts)):
        try:
            return engine.synthesize(turns, voices=voices, language=language)
        except TTSCapabilityError:
            raise
        except TTSError as exc:
            last = exc
            if not exc.retryable or attempt == attempts - 1:
                raise
            sleep(min(4.0, 0.5 * (2 ** attempt)))
    raise last if last else TTSError("synthesis failed")


# ---------------------------------------------------------------------------
# rendering orchestration


@dataclass
class RenderResult:
    audio_artifact_id: str
    audio_sha256: str
    audio_bytes: int
    duration_ms: int
    transcript_artifact_id: str
    transcript_sha256: str
    segments_rendered: int
    segments_reused: int
    warnings: list[str] = field(default_factory=list)


def _segment_key(manifest_id: str, script_version: int, segment: SegmentPlan, engine: TTSEngine,
                 voices: dict[str, str], model: str, language: str) -> str:
    h = hashlib.sha256()
    endpoint = str(getattr(engine, "base_url", ""))
    engine_type = f"{type(engine).__module__}.{type(engine).__qualname__}"
    identity = (f"{manifest_id}|{script_version}|{segment.index}|{engine_type}|{engine.name}|{model}|"
                f"{endpoint}|{language}|")
    h.update(identity.encode())
    for sid in sorted(voices):
        h.update(f"{sid}={voices[sid]}|".encode())
    for turn in segment.turns:
        h.update(turn.speaker_id.encode())
        h.update(b"\x00")
        h.update(turn.speaker_name.encode())
        h.update(b"\x00")
        h.update(turn.text.encode())
        h.update(b"\x00")
        h.update(turn.style.encode())
        h.update(b"\x1e")
    return "tts-seg:" + h.hexdigest()


def render_audio(manifest: SynthesisManifest, script: Script, *, engines: list[TTSEngine],
                 storage: SynthesisStorage, store, max_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
                 output_name: str = "", language: str = "",
                 progress: Optional[Callable[[str, dict], None]] = None,
                 sleep: Callable[[float], None] = time.sleep) -> RenderResult:
    """Render every segment (reusing verified ones), assemble the episode, emit transcript.

    ``store`` provides the synthesis store methods (effect ledger + artifacts). Each
    provider call is journaled under a content-derived idempotency key before it starts.
    """
    if script.manifest_id != manifest.id:
        raise TTSError("script belongs to a different manifest")
    if script.manifest_revision != manifest.revision:
        raise TTSError("script is not on the manifest's current revision")
    script_chars = sum(len(utterance.text) for utterance in script.utterances)
    if script_chars > MAX_SCRIPT_CHARS:
        raise TTSError(f"script exceeds the {MAX_SCRIPT_CHARS:,}-character synthesis limit")
    if not engines:
        raise TTSError("no TTS engine is configured/available")
    engine = engines[0]
    caps = engine.capabilities()
    voices: dict[str, str] = {}
    for speaker in script.speakers:
        voice = speaker.voice.get(engine.name, "")
        if voice:
            voices[speaker.id] = voice
    model = getattr(engine, "model", engine.name)
    segments = plan_segments(script, max_chars=max_chars, manifest=manifest,
                             multi_speaker=caps.multi_speaker)
    if len(segments) > MAX_RUN_SYNTHESIS_SEGMENTS:
        raise TTSError(f"script creates more than {MAX_RUN_SYNTHESIS_SEGMENTS} audio segments")

    warnings: list[str] = []
    missing_voices = [s.id for s in script.speakers if s.id not in voices]
    if missing_voices:
        raise TTSError(f"speakers without a {engine.name} voice: {missing_voices}")

    lang = language or manifest.language
    rendered: int = 0
    reused: int = 0
    segment_parts: list[bytes] = []
    segment_pauses: list[int] = []
    aggregate_bytes = 0
    for segment in segments:
        key = _segment_key(manifest.id, script.version, segment, engine, voices, str(model), lang)
        existing = store.find_synthesis_effect(key)
        artifact_row = None
        if existing:
            status = existing.get("status")
            if status == "succeeded":
                artifact_row = store.get_synthesis_artifact(str(existing.get("remote_id") or ""))
                if artifact_row is None:
                    raise TTSError(f"segment {segment.index}: completed TTS effect has no stored artifact; "
                                   "reconcile it before rendering again")
            elif status == "failed":
                raise TTSError(f"segment {segment.index}: a previous TTS attempt failed; "
                               "explicitly reconcile it before retrying")
            else:
                raise TTSError(f"segment {segment.index}: a previous TTS attempt is {status}; "
                               "reconcile it before rendering again")
        if artifact_row is not None:
            stored_bytes = int(artifact_row["bytes"])
            if aggregate_bytes + stored_bytes > MAX_RUN_SYNTHESIS_BYTES:
                raise TTSError("synthesis run exceeds its aggregate audio-byte limit")
            try:
                data = storage.read_artifact(artifact_row["storage_path"], artifact_row["sha256"],
                                             stored_bytes)
            except Exception as exc:  # noqa: BLE001 - never regenerate a previously successful paid effect
                raise TTSError(f"segment {segment.index}: stored audio failed verification; "
                               "reconcile it before rendering again") from exc
            segment_parts.append(data)
            aggregate_bytes += len(data)
            segment_pauses.append(segment.pause_after_ms)
            reused += 1
            if progress:
                progress("segment_reused", {"segment": segment.index})
            continue
        effect = store.begin_synthesis_effect(
            effect_id=f"eff_{hashlib.sha256(key.encode()).hexdigest()[:16]}",
            plan_id=manifest.id, step_id=f"segment-{segment.index}", kind="tts.segment",
            idempotency_key=key, request_hash=key.split(":", 1)[1],
            target={"segment": segment.index, "engine": engine.name, "model": str(model),
                    "speakers": segment.speaker_ids, "chars": segment.chars},
        )
        if not effect.get("created"):
            if effect.get("status") == "succeeded":
                artifact_row = store.get_synthesis_artifact(str(effect.get("remote_id") or ""))
                if artifact_row is not None:
                    stored_bytes = int(artifact_row["bytes"])
                    if aggregate_bytes + stored_bytes > MAX_RUN_SYNTHESIS_BYTES:
                        raise TTSError("synthesis run exceeds its aggregate audio-byte limit")
                    try:
                        data = storage.read_artifact(artifact_row["storage_path"], artifact_row["sha256"],
                                                     stored_bytes)
                    except Exception as exc:  # noqa: BLE001
                        raise TTSError(f"segment {segment.index}: completed audio failed verification; "
                                       "reconcile it before rendering again") from exc
                    if aggregate_bytes + len(data) > MAX_RUN_SYNTHESIS_BYTES:
                        raise TTSError("synthesis run exceeds its aggregate audio-byte limit")
                    segment_parts.append(data)
                    aggregate_bytes += len(data)
                    segment_pauses.append(segment.pause_after_ms)
                    reused += 1
                    continue
            raise TTSError(f"segment {segment.index}: a previous TTS effect is {effect.get('status')}; "
                           "reconcile it before rendering again")
        try:
            audio = synthesize_with_retry(engine, segment.turns, voices=voices, language=lang, sleep=sleep)
        except TTSError as exc:
            store.finish_synthesis_effect(effect["id"], status="uncertain" if exc.uncertain else "failed",
                                          result={"error": str(exc)[:300], "retryable": exc.retryable})
            raise
        if audio.container == "pcm":
            wav = wrap_pcm(audio.data, rate=audio.sample_rate, channels=audio.channels,
                           sample_width=audio.sample_width)
        else:
            wav = audio.data
        problems = plausible_segment(wav, segment.chars)
        if problems:
            store.finish_synthesis_effect(effect["id"], status="failed",
                                          result={"error": "; ".join(problems)[:300]})
            raise TTSError(f"segment {segment.index} failed validation: {problems[0]}")
        if aggregate_bytes + len(wav) > MAX_RUN_SYNTHESIS_BYTES:
            store.finish_synthesis_effect(effect["id"], status="failed",
                                          result={"error": "aggregate synthesis audio-byte limit exceeded"})
            raise TTSError("synthesis run exceeds its aggregate audio-byte limit")
        version = _next_kind_version(store, manifest.id, "audio_segment")
        artifact_id = new_artifact_id()
        staged = storage.stage_bytes("audio_segment", f"segment-{segment.index:03d}.wav", wav)
        rel_path = storage.version_rel_path(manifest.id, "audio_segment", version,
                                            staged.sha256, staged.storage_name)
        storage.commit(staged, manifest.id, version, insert_row=lambda: store.record_synthesis_artifact(
            artifact_id=artifact_id, manifest_id=manifest.id, kind="audio_segment",
            version=version, status="committed", storage_path=rel_path,
            storage_name=staged.storage_name, mime=staged.mime, bytes_=staged.bytes,
            sha256=staged.sha256,
            meta={"segment_index": segment.index, "utterance_ids": segment.utterance_ids,
                  "duration_ms": wav_duration_ms(wav), "provider": audio.provider_meta}))
        store.finish_synthesis_effect(effect["id"], status="succeeded",
                                      result={"artifact_id": artifact_id, "sha256": staged.sha256,
                                              "duration_ms": wav_duration_ms(wav)},
                                      remote_id=artifact_id)
        segment_parts.append(wav)
        segment_pauses.append(segment.pause_after_ms)
        aggregate_bytes += len(wav)
        rendered += 1
        if progress:
            progress("segment_rendered", {"segment": segment.index, "chars": segment.chars})

    if not segment_parts:
        raise TTSError("no audio segments were produced")
    try:
        joined = concat_wav(segment_parts, segment_pauses,
                            max_bytes=MAX_KIND_BYTES["audio_overview"])
    except ValueError as exc:
        raise TTSError(str(exc)) from exc
    duration_ms = wav_duration_ms(joined)
    audio_version = script.version
    name = output_name or f"audio-overview-v{audio_version}.wav"

    # Idempotent retry: if this script revision already produced an episode (a crash
    # between the audio and transcript commits, or a tool-level retry), verify and reuse
    # it instead of paying for a second render or overwriting history.
    existing_audio = store.find_synthesis_artifact(manifest.id, "audio_overview", audio_version)
    if existing_audio is not None:
        meta = existing_audio.get("meta") or {}
        if meta.get("script_id") != script.id:
            raise TTSError(
                f"{manifest.id} already has an audio overview v{audio_version} from a different "
                "script; bump the script version instead of overwriting")
        storage.read_artifact(existing_audio["storage_path"], existing_audio["sha256"],
                              int(existing_audio["bytes"]))
        audio_id = existing_audio["id"]
        audio_sha = existing_audio["sha256"]
        audio_bytes = int(existing_audio["bytes"])
        duration_ms = int(meta.get("duration_ms") or duration_ms)
        warnings.append("audio for this script revision already existed and was reused")
    else:
        audio_id = new_artifact_id()
        staged_audio = storage.stage_bytes("audio_overview", name, joined)
        audio_sha = staged_audio.sha256
        audio_bytes = staged_audio.bytes
        audio_rel = storage.version_rel_path(manifest.id, "audio_overview", audio_version,
                                             staged_audio.sha256, staged_audio.storage_name)
        storage.commit(staged_audio, manifest.id, audio_version,
                       insert_row=lambda: store.record_synthesis_artifact(
                           artifact_id=audio_id, manifest_id=manifest.id, kind="audio_overview",
                           version=audio_version, status="validated", storage_path=audio_rel,
                           storage_name=staged_audio.storage_name, mime=staged_audio.mime,
                           bytes_=staged_audio.bytes, sha256=staged_audio.sha256,
                           meta={"script_id": script.id, "script_version": script.version,
                                 "segments": len(segments), "duration_ms": duration_ms,
                                 "engine": engine.name, "model": str(model),
                                 "speakers": [{"id": s.id, "name": s.name, "role": s.role,
                                               "voice": voices.get(s.id, "")}
                                              for s in script.speakers],
                                 "language": lang, "alignment": "segment-duration estimate",
                                 "reused_segments": reused, "rendered_segments": rendered}))

    transcript = build_transcript(manifest, script, segments, [wav_duration_ms(p) for p in segment_parts],
                                  segment_pauses, language=lang)
    existing_transcript = store.find_synthesis_artifact(manifest.id, "transcript", script.version)
    if existing_transcript is not None:
        meta = existing_transcript.get("meta") or {}
        if meta.get("script_id") != script.id:
            raise TTSError("a transcript exists for this version with different script content")
        storage.read_artifact(existing_transcript["storage_path"], existing_transcript["sha256"],
                              int(existing_transcript["bytes"]))
        transcript_id = existing_transcript["id"]
        transcript_sha = existing_transcript["sha256"]
        warnings.append("transcript for this script revision already existed and was reused")
    else:
        transcript_bytes = transcript["vtt"].encode("utf-8")
        transcript_id = new_artifact_id()
        staged_t = storage.stage_bytes("transcript", name.rsplit(".", 1)[0] + ".vtt", transcript_bytes)
        t_version = script.version
        t_rel = storage.version_rel_path(manifest.id, "transcript", t_version, staged_t.sha256,
                                         staged_t.storage_name)
        transcript_sha = staged_t.sha256
        storage.commit(staged_t, manifest.id, t_version,
                       insert_row=lambda: store.record_synthesis_artifact(
                           artifact_id=transcript_id, manifest_id=manifest.id, kind="transcript",
                           version=t_version, status="validated", storage_path=t_rel,
                           storage_name=staged_t.storage_name, mime=staged_t.mime,
                           bytes_=staged_t.bytes, sha256=staged_t.sha256,
                           meta={"script_id": script.id, "language": lang,
                                 "alignment": "segment-duration estimate",
                                 "cues": len(transcript["cues"])}))

    return RenderResult(
        audio_artifact_id=audio_id, audio_sha256=audio_sha, audio_bytes=audio_bytes,
        duration_ms=duration_ms, transcript_artifact_id=transcript_id,
        transcript_sha256=transcript_sha, segments_rendered=rendered, segments_reused=reused,
        warnings=warnings,
    )


def _next_kind_version(store, manifest_id: str, kind: str) -> int:
    from .storage import next_kind_version

    return next_kind_version(store, manifest_id, kind)


# ---------------------------------------------------------------------------
# transcript


def _fmt_ts(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"


def build_transcript(manifest: SynthesisManifest, script: Script, segments: list[SegmentPlan],
                     segment_durations: list[int], pauses: list[int], *, language: str = "") -> dict[str, Any]:
    """VTT + JSON cues from segment durations.

    Alignment is apportioned by text length inside a segment and labeled as an estimate:
    a provider that returns no word timings cannot support finer claims, so none are made.
    """
    names = {s.id: s.name for s in script.speakers}
    utterances = {u.id: u for u in script.utterances}
    chapters = {c.id: c for c in script.chapters}
    cues: list[dict[str, Any]] = []
    cursor = 0
    for seg, duration in zip(segments, segment_durations):
        total_chars = max(1, sum(len(t.text) for t in seg.turns))
        offset = cursor
        for turn in seg.turns:
            uid = next((i for i in seg.utterance_ids
                        if utterances.get(i) and utterances[i].speaker_id == turn.speaker_id
                        and utterances[i].text == turn.text), None)
            share = max(200, int(round(duration * len(turn.text) / total_chars)))
            start = offset
            end = min(cursor + duration, start + share)
            utterance = utterances.get(uid) if uid else None
            cues.append({
                "start_ms": start, "end_ms": max(end, start + 200),
                "speaker_id": turn.speaker_id, "speaker": names.get(turn.speaker_id, turn.speaker_id),
                "text": turn.text,
                "utterance_id": uid or "",
                "chapter_id": (utterance.chapter_id if utterance else ""),
                "chapter": (chapters[utterance.chapter_id].title if utterance and utterance.chapter_id in chapters else ""),
                "claim_ids": list(utterance.claim_ids) if utterance else [],
                "span_ids": list(utterance.span_ids) if utterance else [],
            })
            offset = max(end, start + 200)
        cursor += duration + (pauses[seg.index] if seg.index < len(pauses) else 0)

    lines = ["WEBVTT", "", "NOTE speaker labels and timings are estimates from segment durations", ""]
    for i, cue in enumerate(cues, start=1):
        lines.append(f"{i}")
        lines.append(f"{_fmt_ts(cue['start_ms'])} --> {_fmt_ts(cue['end_ms'])}")
        lines.append(f"{cue['speaker']}: {cue['text']}")
        lines.append("")
    return {
        "vtt": "\n".join(lines) + "\n",
        "cues": cues,
        "language": language or manifest.language,
        "alignment": "segment-duration estimate",
        "chapters": [{"id": c.id, "index": c.index, "title": c.title} for c in script.chapters],
    }
