"""Speech-synthesis route declaration and wire contract (chat-completions audio).

A connection only gets this route when its bundled template declares a ``speech`` block.
The declaration is per-route, not per-vendor: "the vendor sells TTS" must never be enough to
send a user's words to whichever account happens to be configured.

Wire contract, read from the vendor's own API reference on 2026-10-31
(https://mimo.mi.com/static/docs/api/audio/tts.md and
https://mimo.mi.com/static/docs/quick-start/usage-guide/audio/speech-synthesis-v2.5.md):

    POST {base_url}/chat/completions
    {"model": "mimo-v2.5-tts",
     "messages": [{"role": "user", "content": "<style instruction, optional>"},
                  {"role": "assistant", "content": "<the text to speak>"}],
     "audio": {"format": "wav", "voice": "mimo_default"}}

The reply is an ordinary chat completion whose ``choices[0].message.audio.data`` is
base64-encoded audio in the requested format, with token usage under ``usage``. The text to
speak belongs in the ``assistant`` message; the optional ``user`` message only carries style
or director instructions and is never spoken.

Honesty rules encoded here rather than left to callers:

* missing or empty ``audio.data`` is an error, never silence presented as success;
* only wav is requested and accepted, because the media store validates a real RIFF/WAVE
  container (the vendor also offers mp3/pcm, which Hutch does not store today);
* a reply from a different model id is reported, so a silent substitution is visible;
* a ``length`` finish reason notes that the audio may be truncated.

The transport lives in :mod:`hutch.media.providers.speech`; this module has no HTTP client,
so the pure request/response rules are testable without a network.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Optional

#: Hutch's own bound for one utterance. The vendor page read 2026-10-31 states no character
#: limit for these models, so this is a tool limit, not a vendor claim.
MAX_TEXT_CHARS = 4000

#: The media store stores wav only (``media.storage.MEDIA_FORMATS``). Requesting anything
#: else would produce bytes Hutch cannot present, so the route asks for wav.
SUPPORTED_FORMATS = ("wav",)

#: A decoded speech clip larger than this is refused before it reaches the store.
MAX_AUDIO_BYTES = 32_000_000

_MAX_STYLE_CHARS = 2000
_SUPPORTED_PROTOCOL = "chat-speech"

_RIFF = b"RIFF"
_WAVE = b"WAVE"


# ------------------------------------------------------------------ route


class SpeechError(RuntimeError):
    """The speech request was refused or failed; the message is the provider's own."""


@dataclass(frozen=True)
class SpeechRoute:
    """What one connection's template declares about its speech-synthesis endpoint."""

    model: str
    voices: tuple[str, ...] = ("mimo_default",)
    format: str = "wav"
    max_text_chars: int = MAX_TEXT_CHARS
    source: str = ""

    @property
    def default_voice(self) -> str:
        return self.voices[0]

    def check_voice(self, voice: str) -> str:
        value = str(voice or "").strip()
        if not value:
            return self.default_voice
        if value not in self.voices:
            raise SpeechError(
                f"voice {value!r} is not offered by this speech route "
                f"(supported: {', '.join(self.voices)})")
        return value


def route_from_template(template: Optional[dict[str, Any]]) -> Optional[SpeechRoute]:
    """Read and validate the optional ``speech`` block of a connection template.

    ``None`` means the route is not offered. A malformed block raises ``ValueError`` so a
    configuration mistake is loud rather than silently disabling the capability.
    """
    if not template:
        return None
    block = template.get("speech")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("speech must be a JSON object")
    protocol = block.get("protocol", _SUPPORTED_PROTOCOL)
    if protocol != _SUPPORTED_PROTOCOL:
        raise ValueError(f"unsupported speech protocol {protocol!r}")
    model = block.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 160:
        raise ValueError("speech.model must be a non-empty model id")
    fmt = block.get("format", "wav")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"speech.format must be one of {', '.join(SUPPORTED_FORMATS)}")
    voices_value = block.get("voices", ["mimo_default"])
    if not isinstance(voices_value, list) or not voices_value:
        raise ValueError("speech.voices must be a non-empty list")
    voices: list[str] = []
    for item in voices_value:
        if not isinstance(item, str) or not item.strip() or len(item) > 64:
            raise ValueError("speech.voices entries must be short non-empty strings")
        voices.append(item.strip())
    limit = block.get("max_text_chars", MAX_TEXT_CHARS)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TEXT_CHARS:
        raise ValueError("speech.max_text_chars must be an integer within the tool bound")
    source = block.get("source", "")
    if source and (not isinstance(source, str) or not source.startswith("https://")):
        raise ValueError("speech.source must be an https URL when present")
    return SpeechRoute(model=model.strip(), voices=tuple(voices), format=fmt,
                       max_text_chars=limit, source=source)


# ------------------------------------------------------------------ wire


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    model: str                        # the model id the provider says answered
    requested_model: str
    format: str = "wav"
    duration_seconds: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    audio_tokens: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def substituted_model(self) -> bool:
        return bool(self.model) and self.model != self.requested_model


def build_payload(route: SpeechRoute, text: str, *, voice: str = "",
                  style: str = "") -> dict[str, Any]:
    """The exact request body for one speech call. ``text`` is spoken; ``style`` is not."""
    clean_text = str(text or "").strip()
    if not clean_text:
        raise SpeechError("there is no text to speak")
    if len(clean_text) > route.max_text_chars:
        raise SpeechError(
            f"the text is {len(clean_text)} characters; this speech route accepts at most "
            f"{route.max_text_chars}")
    clean_style = " ".join(str(style or "").split())
    if len(clean_style) > _MAX_STYLE_CHARS:
        raise SpeechError(f"the style instruction is longer than {_MAX_STYLE_CHARS} characters")
    messages: list[dict[str, Any]] = []
    if clean_style:
        messages.append({"role": "user", "content": clean_style})
    messages.append({"role": "assistant", "content": clean_text})
    return {
        "model": route.model,
        "messages": messages,
        "audio": {"format": route.format, "voice": route.check_voice(voice)},
    }


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _decode_audio(data: Any) -> bytes:
    if not isinstance(data, str) or not data.strip():
        raise SpeechError(
            "the speech endpoint returned no audio data; Hutch does not present silence as "
            "a successful synthesis")
    try:
        audio = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SpeechError(
            f"the speech endpoint returned audio that is not valid base64: {exc}") from exc
    if not audio:
        raise SpeechError("the speech endpoint returned zero audio bytes")
    if len(audio) > MAX_AUDIO_BYTES:
        raise SpeechError(
            f"the speech endpoint returned {len(audio)} bytes, above the "
            f"{MAX_AUDIO_BYTES // 1_000_000} MB this adapter accepts")
    return audio


def wav_duration(audio: bytes) -> Optional[float]:
    """Duration of a PCM RIFF/WAVE file, or None when the header is not understood.

    This reads the ``fmt `` byte rate and the ``data`` chunk size; it never decodes samples,
    so a malformed or non-PCM file reports None instead of a guessed duration.
    """
    if len(audio) < 44 or audio[:4] != _RIFF or audio[8:12] != _WAVE:
        return None
    pos = 12
    byte_rate = 0
    data_size = 0
    while pos + 8 <= len(audio):
        chunk_id = audio[pos:pos + 4]
        chunk_size = int.from_bytes(audio[pos + 4:pos + 8], "little")
        body = pos + 8
        if chunk_id == b"fmt " and chunk_size >= 16 and body + 16 <= len(audio):
            byte_rate = int.from_bytes(audio[body + 8:body + 12], "little")
        elif chunk_id == b"data":
            data_size = min(chunk_size, max(0, len(audio) - body))
            break
        pos = body + chunk_size + (chunk_size % 2)
    if byte_rate <= 0 or data_size <= 0:
        return None
    return round(data_size / byte_rate, 3)


def parse_speech_response(body: Any, route: SpeechRoute) -> SpeechResult:
    """Turn a provider reply into audio plus usage, or raise when it is not speech."""
    if not isinstance(body, dict):
        raise SpeechError("the speech endpoint did not return a JSON object")
    if body.get("error"):
        error = body["error"]
        detail = error.get("message") if isinstance(error, dict) else error
        raise SpeechError(f"the speech endpoint reported an error: {detail}")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise SpeechError("the speech endpoint returned no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    audio_block = message.get("audio") if isinstance(message, dict) else None
    if not isinstance(audio_block, dict):
        raise SpeechError(
            "the speech endpoint returned no audio object; the reply was not speech")
    audio = _decode_audio(audio_block.get("data"))
    if audio[:4] != _RIFF or audio[8:12] != _WAVE:
        raise SpeechError(
            "the speech endpoint returned bytes that are not a wav container, even though "
            "wav was requested; Hutch does not relabel audio to make it acceptable")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    completion_details = (usage.get("completion_tokens_details")
                          if isinstance(usage.get("completion_tokens_details"), dict) else {})
    prompt_details = (usage.get("prompt_tokens_details")
                      if isinstance(usage.get("prompt_tokens_details"), dict) else {})
    answered_model = body.get("model") if isinstance(body.get("model"), str) else ""
    notes: list[str] = []
    if answered_model and answered_model != route.model:
        notes.append(f"requested {route.model}, and the provider answered with {answered_model}")
    finish = choice.get("finish_reason")
    if finish == "length":
        notes.append("the provider stopped at its output limit; the audio may be truncated")
    elif finish == "content_filter":
        notes.append("the provider's content filter stopped the request")
    return SpeechResult(
        audio=audio,
        model=answered_model or route.model,
        requested_model=route.model,
        duration_seconds=wav_duration(audio),
        prompt_tokens=_int(usage.get("prompt_tokens")),
        completion_tokens=_int(usage.get("completion_tokens")),
        audio_tokens=_int(completion_details.get("audio_tokens")
                          or prompt_details.get("audio_tokens")),
        notes=tuple(notes),
    )
