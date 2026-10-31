"""Speech-to-text over an OpenAI-shaped chat request that carries an audio content part.

A connection only gets this route when its bundled template declares a ``transcription``
block. The declaration is deliberately per-route, not per-vendor: "Xiaomi offers audio
models" must never be enough to send a user's recording to whichever account happens to be
configured.

Wire contract, observed live on 2026-10-31 against Xiaomi MiMo (Token Plan, Singapore):

    POST {base_url}/chat/completions
    {"model": "mimo-v2.5-asr",
     "messages": [{"role": "user", "content": [
        {"type": "input_audio",
         "input_audio": {"data": "data:audio/wav;base64,<...>"}}]}]}

The reply is an ordinary chat completion whose ``message.content`` is the transcript, with
``usage.prompt_tokens_details.audio_tokens`` and (for this provider) ``usage.seconds``.
Documented limits: wav or mp3 only, and the base64 string must not exceed 10 MB
(https://mimo.mi.com/docs/en-US/quick-start/usage-guide/audio/Speech-Recognition).

Honesty rules encoded here rather than left to callers:

* an empty ``message.content`` is an error, never an empty successful transcript;
* a reply from a different model id is reported, so a silent substitution is visible;
* the key travels only to the configured endpoint, and redirects are refused because the
  bearer token would follow the ``Location`` header to another host.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Optional

from ..connection_endpoints import redirect_refusal
from .base import ProviderError

#: The vendor's documented ceiling for the base64-encoded audio string.
MAX_AUDIO_BASE64_BYTES = 10 * 1024 * 1024

#: Formats this route accepts. Hutch refuses anything else instead of guessing or converting.
SUPPORTED_FORMATS = ("wav", "mp3")

_MIME_BY_FORMAT = {"wav": "audio/wav", "mp3": "audio/mpeg"}
_SUPPORTED_PROTOCOL = "chat-audio"
_MAX_ERROR_DETAIL = 400


# ------------------------------------------------------------------ route


@dataclass(frozen=True)
class TranscriptionRoute:
    """What one connection's template declares about its speech-to-text endpoint."""

    model: str
    languages: tuple[str, ...] = ("auto",)
    max_audio_base64_bytes: int = MAX_AUDIO_BASE64_BYTES
    source: str = ""

    def check_language(self, language: str) -> str:
        value = str(language or "auto").strip().lower()
        if value not in self.languages:
            raise ProviderError(
                "bad_request",
                f"language {value!r} is not offered by this transcription route "
                f"(supported: {', '.join(self.languages)})")
        return value


def route_from_template(template: Optional[dict[str, Any]]) -> Optional[TranscriptionRoute]:
    """Read and validate the optional ``transcription`` block of a connection template.

    ``None`` means the route is not offered. A malformed block raises ``ValueError`` so a
    configuration mistake is loud rather than silently disabling the capability.
    """
    if not template:
        return None
    block = template.get("transcription")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("transcription must be a JSON object")
    protocol = block.get("protocol", _SUPPORTED_PROTOCOL)
    if protocol != _SUPPORTED_PROTOCOL:
        raise ValueError(f"unsupported transcription protocol {protocol!r}")
    model = block.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 160:
        raise ValueError("transcription.model must be a non-empty model id")
    if "languages" in block:
        languages_value = block.get("languages")
        if not isinstance(languages_value, list) or not languages_value:
            raise ValueError("transcription.languages must be a non-empty list")
    else:
        languages_value = ["auto"]
    languages: list[str] = []
    for item in languages_value:
        if not isinstance(item, str) or not item.strip() or len(item) > 16:
            raise ValueError("transcription.languages entries must be short strings")
        languages.append(item.strip().lower())
    limit = block.get("max_audio_base64_bytes", MAX_AUDIO_BASE64_BYTES)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_AUDIO_BASE64_BYTES:
        raise ValueError("transcription.max_audio_base64_bytes must be an integer within the vendor limit")
    source = block.get("source", "")
    if source and (not isinstance(source, str) or not source.startswith("https://")):
        raise ValueError("transcription.source must be an https URL when present")
    return TranscriptionRoute(model=model.strip(), languages=tuple(languages),
                              max_audio_base64_bytes=limit, source=source)


# ------------------------------------------------------------------ audio


def sniff_audio(data: bytes) -> Optional[str]:
    """Identify wav/mp3 by magic bytes, or None.

    This is intentionally narrower than the media store's general sniffer: it answers only
    "can this route accept that file", and the route accepts two containers.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"ID3"):
        return "mp3"
    # MPEG audio frame sync: 11 set bits, then version/layer/bitrate/sample-rate fields that
    # cannot be their reserved values. This rejects most random byte pairs.
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        version = (data[1] >> 3) & 0x03
        layer = (data[1] >> 1) & 0x03
        bitrate = (data[2] >> 4) & 0x0F
        sample_rate = (data[2] >> 2) & 0x03
        if version != 0x01 and layer != 0x00 and bitrate != 0x0F and sample_rate != 0x03:
            return "mp3"
    return None


def encoded_size(raw_bytes: int) -> int:
    """Exact base64 length for ``raw_bytes`` bytes (4 characters per 3-byte group)."""
    return 4 * ((int(raw_bytes) + 2) // 3)


# ------------------------------------------------------------------ result


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    model: str                        # the model id the provider says answered
    requested_model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    audio_tokens: int = 0
    audio_seconds: Optional[float] = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def substituted_model(self) -> bool:
        return bool(self.model) and self.model != self.requested_model


# ------------------------------------------------------------------ parsing


def build_payload(route: TranscriptionRoute, audio: bytes, audio_format: str,
                  language: str = "auto") -> dict[str, Any]:
    """The exact request body for one transcription call."""
    if audio_format not in _MIME_BY_FORMAT:
        raise ProviderError("bad_request", f"unsupported audio format {audio_format!r}")
    if not audio:
        raise ProviderError("bad_request", "the audio file is empty")
    data_url = f"data:{_MIME_BY_FORMAT[audio_format]};base64," + base64.b64encode(audio).decode("ascii")
    payload: dict[str, Any] = {
        "model": route.model,
        "messages": [{
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_url}}],
        }],
    }
    if language and language != "auto":
        payload["asr_options"] = {"language": language}
    return payload


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def parse_transcription_response(body: Any, route: TranscriptionRoute) -> TranscriptionResult:
    """Turn a provider reply into a result, or raise when it is not a transcript."""
    if not isinstance(body, dict):
        raise ProviderError("incomplete", "the transcription endpoint did not return a JSON object")
    if body.get("error"):
        detail = body["error"].get("message") if isinstance(body["error"], dict) else body["error"]
        raise ProviderError("incomplete", f"the transcription endpoint reported an error: {detail}")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError("incomplete", "the transcription endpoint returned no choices")
    message = choices[0].get("message") or {}
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ProviderError(
            "incomplete",
            "the transcription endpoint returned no transcript (empty content); "
            "Hutch does not report silence as a successful transcription")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    seconds = usage.get("seconds")
    audio_seconds = float(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else None
    answered_model = body.get("model") if isinstance(body.get("model"), str) else ""
    notes: list[str] = []
    if answered_model and answered_model != route.model:
        notes.append(f"requested {route.model}, and the provider answered with {answered_model}")
    return TranscriptionResult(
        text=text.strip(),
        model=answered_model or route.model,
        requested_model=route.model,
        prompt_tokens=_int(usage.get("prompt_tokens")),
        completion_tokens=_int(usage.get("completion_tokens")),
        audio_tokens=_int(details.get("audio_tokens")),
        audio_seconds=audio_seconds,
        notes=tuple(notes),
    )


# ------------------------------------------------------------------ transport


class ChatAudioTranscriber:
    """One transcription request to one configured endpoint. Nothing is retried here."""

    def __init__(self, *, base_url: str, api_key: str, route: TranscriptionRoute,
                 provider_name: str = "transcription", headers: Optional[dict[str, str]] = None,
                 timeout: float = 120.0):
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = api_key
        self.route = route
        self.provider_name = provider_name
        self.headers = dict(headers or {})
        self.timeout = max(5.0, min(float(timeout), 300.0))
        if not self.base_url:
            raise ProviderError("bad_request", "this connection has no endpoint to send audio to")

    def _client(self):
        import httpx

        from ..offline import httpx_offline_options

        base_url, transport, trust_env = httpx_offline_options(self.base_url, self.provider_name)
        headers = {"Authorization": f"Bearer {self.api_key}", **self.headers}
        return httpx.Client(base_url=base_url, headers=headers, trust_env=trust_env,
                            transport=transport, timeout=httpx.Timeout(
                                connect=10.0, read=self.timeout, write=60.0, pool=5.0))

    def transcribe(self, audio: bytes, *, language: str = "auto",
                   audio_format: Optional[str] = None) -> TranscriptionResult:
        detected = sniff_audio(audio)
        if audio_format and detected and audio_format != detected:
            raise ProviderError(
                "bad_request",
                f"the audio was declared {audio_format!r} but its bytes are {detected!r}; "
                "Hutch will not relabel a file to make a route accept it")
        fmt = audio_format or detected
        if fmt not in SUPPORTED_FORMATS:
            raise ProviderError(
                "bad_request",
                "this transcription route accepts wav or mp3 audio only; the file's bytes are "
                "neither, and Hutch does not guess a container or convert it silently")
        if encoded_size(len(audio)) > self.route.max_audio_base64_bytes:
            limit_mb = self.route.max_audio_base64_bytes / (1024 * 1024)
            raise ProviderError(
                "bad_request",
                f"the audio is too large for this route: encoded size exceeds {limit_mb:g} MB")
        language = self.route.check_language(language)
        payload = build_payload(self.route, audio, fmt, language)
        import httpx

        try:
            client = self._client()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - offline broker / TLS setup failures are "unreachable"
            raise ProviderError(
                "unreachable",
                f"cannot open a connection to the transcription endpoint at {self.base_url}: {exc}",
                provider=self.provider_name) from exc
        try:
            with client:
                resp = client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "timeout",
                f"{self.provider_name} did not answer the transcription request within "
                f"{self.timeout:g}s. The provider may have received and billed the request; "
                "Hutch did not retry it.", provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "unreachable",
                f"cannot reach the transcription endpoint at {self.base_url}: {exc}",
                provider=self.provider_name) from exc
        if 300 <= resp.status_code < 400:
            raise redirect_refusal(self.provider_name, resp.headers.get("location"))
        if resp.status_code >= 400:
            raise self._error_from_response(resp)
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError("incomplete", "the transcription endpoint returned a non-JSON body",
                                provider=self.provider_name, status=resp.status_code) from exc
        return parse_transcription_response(body, self.route)

    def _error_from_response(self, resp) -> ProviderError:
        status = resp.status_code
        detail = ""
        try:
            body = resp.json()
            error = body.get("error") if isinstance(body, dict) else None
            detail = error.get("message") if isinstance(error, dict) else (str(error) if error else "")
        except ValueError:
            detail = ""
        detail = " ".join(str(detail or f"HTTP {status}").split())[:_MAX_ERROR_DETAIL]
        low = detail.lower()
        if status in (401, 403):
            return ProviderError("auth", f"{self.provider_name} rejected the credential for transcription "
                                        f"({detail}). Check the connection key.", provider=self.provider_name, status=status)
        if status == 402 or (status == 429 and ("quota" in low or "credit" in low or "balance" in low)):
            return ProviderError("quota", f"{self.provider_name} has no available credit or quota: {detail}",
                                 provider=self.provider_name, status=status)
        if status == 429:
            retry_after = resp.headers.get("retry-after")
            return ProviderError("rate_limit", f"{self.provider_name} rate-limited the request: {detail}",
                                 provider=self.provider_name, status=status,
                                 retry_after=float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else None)
        if status == 404 and "model" in low:
            return ProviderError("model_missing", detail, provider=self.provider_name, status=status)
        if status in (400, 413, 422):
            return ProviderError("bad_request", detail, provider=self.provider_name, status=status)
        return ProviderError("server", f"{self.provider_name} returned HTTP {status}: {detail}",
                             provider=self.provider_name, status=status)

