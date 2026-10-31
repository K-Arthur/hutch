"""Gemini wire conversion: messages, tools, schemas, signatures, usage and finish reasons.

Split out of ``providers/gemini.py`` so the transport/adapter module stays small. Everything here is
pure conversion or a bounded process-local cache; nothing performs network I/O.

Evidence for the shapes (read 2026-10-31):

* the published discovery document ``https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta``
  (revision 20261030) defines ``Part`` (``text`` / ``inlineData`` / ``functionCall`` / ``functionResponse``
  / ``thought`` / ``thoughtSignature``), ``FunctionDeclaration.parametersJsonSchema``, ``UsageMetadata``
  and the ``finishReason`` enum;
* ``https://ai.google.dev/gemini-api/docs/thinking`` documents that generateContent carries thought
  signatures as part metadata and that they must be replayed with the history.
"""

from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict
from typing import Any

from .base import ProviderError, parse_tool_args_state

OFFICIAL_HOST = "generativelanguage.googleapis.com"
DEFAULT_BASE_URL = f"https://{OFFICIAL_HOST}/v1beta"

MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
MAX_MODELS = 10000
MAX_PAGES = 10
DATA_IMAGE = re.compile(r"data:(image/(?:png|jpeg|jpg|gif|webp|avif|heic|heif));base64,([A-Za-z0-9+/=]+)")
#: Models whose published input is multimodal: 1.5 and later, including the 1.0 vision variant.
MULTIMODAL_MODEL = re.compile(r"^gemini-(?:1\.0-pro-vision|1\.[5-9]|[2-9]|\d{2,})", re.IGNORECASE)
#: thinkingLevel is documented as Gemini 3 or later only ("use with earlier models results in an error")
THINKING_LEVEL_MODEL = re.compile(r"^gemini-(?:[3-9]|\d{2,})\b", re.IGNORECASE)
EFFORT_LEVELS = {"minimal": "MINIMAL", "low": "LOW", "medium": "MEDIUM", "high": "HIGH"}
#: The finish reasons the schema names as refusals/filters rather than truncation or success.
REFUSAL_REASONS = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE",
                   "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION", "ESCALATION",
                   "PUP_LIMITED_DISABLED"}
#: Keys that carry no meaning on the wire and may reference a network document.
_SCHEMA_DROPPED_KEYS = {"$schema", "$id", "examples"}

SIGNATURE_LIMIT = 512
MAX_SIGNATURE_CHARS = 16_384
_SIGNATURES: "OrderedDict[tuple[str, str], str]" = OrderedDict()
_SIGNATURE_LOCK = threading.Lock()


# ------------------------------------------------------------------ signatures

def remember_signature(base_url: str, call_id: str, signature: Any) -> None:
    """Keep one opaque provider signature for ``call_id`` in a bounded process-local cache.

    Hutch's normalized assistant message has no field for provider part metadata yet, so a signature
    lives only as long as the process. No prompt or output text is stored here.
    """
    if not isinstance(signature, str) or not signature or len(signature) > MAX_SIGNATURE_CHARS or not call_id:
        return
    key = (base_url, call_id)
    with _SIGNATURE_LOCK:
        _SIGNATURES[key] = signature
        _SIGNATURES.move_to_end(key)
        while len(_SIGNATURES) > SIGNATURE_LIMIT:
            _SIGNATURES.popitem(last=False)


def signature_for(base_url: str, call_id: str) -> str:
    """The signature this process observed for ``call_id`` on ``base_url`` ("" when it was lost)."""
    with _SIGNATURE_LOCK:
        return _SIGNATURES.get((base_url, call_id), "")


def forget_signatures(base_url: str) -> None:
    """Drop cached signatures for one endpoint (tests and explicit disconnects)."""
    with _SIGNATURE_LOCK:
        for key in [k for k in _SIGNATURES if k[0] == base_url]:
            del _SIGNATURES[key]


# ------------------------------------------------------------------ schemas and tools

def clean_schema(schema: Any, path: str = "parameters", provider: str = "google") -> Any:
    """A bounded JSON-Schema copy for ``parametersJsonSchema``.

    A remote ``$ref`` would make Google fetch an arbitrary URL on Hutch's behalf, so it is refused
    rather than silently dropped (dropping it would change the tool's contract).
    """
    if isinstance(schema, list):
        return [clean_schema(item, f"{path}[{index}]", provider) for index, item in enumerate(schema)]
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _SCHEMA_DROPPED_KEYS:
            continue
        if key == "$ref" and (not isinstance(value, str) or not value.startswith("#")):
            raise ProviderError("bad_request", f"{path} uses a non-local $ref, which Gemini cannot resolve",
                                provider=provider)
        cleaned[key] = clean_schema(value, f"{path}.{key}", provider)
    return cleaned


def tool_declarations(tools: list[dict[str, Any]], provider: str = "google") -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ProviderError("bad_request", "Gemini function calling accepts function tools only",
                                provider=provider)
        function = tool.get("function") or {}
        name = str(function.get("name") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name):
            raise ProviderError("bad_request", f"tool name {name!r} is not a valid Gemini function name",
                                provider=provider)
        declarations.append({
            "name": name,
            "description": str(function.get("description") or "")[:2000],
            "parametersJsonSchema": clean_schema(function.get("parameters") or {"type": "object",
                                                                               "properties": {}},
                                                 provider=provider),
        })
    return declarations


# ------------------------------------------------------------------ content conversion

def user_parts(content: Any, provider: str = "google") -> list[dict[str, Any]]:
    """OpenAI-shaped content -> Gemini parts. Only inline image data is accepted, never a remote URL."""
    if not isinstance(content, list):
        return [{"text": str(content or "")}]
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            parts.append({"text": str(part.get("text", ""))})
        elif part.get("type") == "image_url":
            url = str((part.get("image_url") or {}).get("url", ""))
            found = DATA_IMAGE.fullmatch(url)
            if not found:
                raise ProviderError("bad_request",
                                    "Gemini accepts inline image data; a remote image URL was not fetched",
                                    provider=provider)
            parts.append({"inlineData": {"mimeType": found.group(1).replace("image/jpg", "image/jpeg"),
                                         "data": found.group(2)}})
    return parts or [{"text": ""}]


def function_call_part(tc: dict[str, Any], base_url: str, provider: str = "google") -> dict[str, Any]:
    function = tc.get("function") or {}
    name = str(function.get("name") or "")
    if not name:
        raise ProviderError("bad_request", "a recorded tool call has no name", provider=provider)
    raw = function.get("arguments")
    if isinstance(raw, str):
        arguments, error, _state, _double = parse_tool_args_state(raw)
        if error:
            raise ProviderError("bad_request",
                                f"the recorded arguments for tool '{name}' are not valid JSON: {error}",
                                provider=provider)
    elif isinstance(raw, dict):
        arguments = raw
    else:
        arguments = {}
    call: dict[str, Any] = {"name": name, "args": arguments}
    if tc.get("id"):
        call["id"] = str(tc["id"])
    part: dict[str, Any] = {"functionCall": call}
    signature = signature_for(base_url, str(tc.get("id") or ""))
    if signature:
        part["thoughtSignature"] = signature
    return part


def to_contents(messages: list[dict[str, Any]], base_url: str,
                provider: str = "google") -> tuple[str, list[dict[str, Any]]]:
    """Internal OpenAI-shaped messages -> (system text, Gemini contents).

    Adjacent same-role contents are merged: generateContent expects alternating turns, and parallel
    tool results arrive as several messages that belong to one function-response turn.
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "system":
            system_parts.append(str(message.get("content") or ""))
            continue
        if role == "user":
            contents.append({"role": "user", "parts": user_parts(message.get("content"), provider)})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if message.get("content"):
                parts.append({"text": str(message["content"])})
            for tc in message.get("tool_calls") or []:
                if isinstance(tc, dict):
                    parts.append(function_call_part(tc, base_url, provider))
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            response: dict[str, Any] = {"name": str(message.get("name") or ""),
                                        "response": {"result": str(message.get("content") or "") or "(empty)"}}
            if message.get("tool_call_id"):
                response["id"] = str(message["tool_call_id"])
            contents.append({"role": "user", "parts": [{"functionResponse": response}]})
        if len(contents) >= 2 and contents[-2]["role"] == contents[-1]["role"]:
            contents[-2]["parts"].extend(contents[-1]["parts"])
            contents.pop()
    return "\n\n".join(p for p in system_parts if p), contents


def model_id(model: str, provider: str = "google") -> str:
    """The bare model name for a request path; a value Hutch cannot send is refused, never guessed."""
    name = str(model or "").strip().removeprefix("models/")
    if not MODEL_RE.fullmatch(name):
        raise ProviderError("bad_request", f"invalid Gemini model id: {model!r}", provider=provider)
    return name


def request_body(req: Any, base_url: str, provider: str = "google") -> dict[str, Any]:
    """One GenerateContentRequest. Thinking is only constrained where the schema permits it."""
    system, contents = to_contents(req.messages, base_url, provider)
    body: dict[str, Any] = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    config: dict[str, Any] = {}
    if req.max_tokens:
        config["maxOutputTokens"] = int(req.max_tokens)
    if req.temperature is not None:
        config["temperature"] = float(req.temperature)
    level = EFFORT_LEVELS.get(str(req.effort or "").lower())
    if level and THINKING_LEVEL_MODEL.match(model_id(req.model, provider)):
        # GenerateContent documentation: thinkingLevel is for Gemini 3+; earlier models error.
        config["thinkingConfig"] = {"thinkingLevel": level}
    if config:
        body["generationConfig"] = config
    if req.tools:
        body["tools"] = [{"functionDeclarations": tool_declarations(req.tools, provider)}]
    return body


# ------------------------------------------------------------------ results

def usage_counts(usage: dict[str, Any]) -> dict[str, int]:
    return {"prompt_tokens": int(usage.get("promptTokenCount") or 0),
            "completion_tokens": int(usage.get("candidatesTokenCount") or 0),
            "cached_tokens": int(usage.get("cachedContentTokenCount") or 0)}


def tool_calls_from(calls: list[dict[str, Any]], served_model: str, base_url: str,
                    provider: str = "google") -> list[dict[str, Any]]:
    """Gemini ``functionCall`` parts -> (id, name, arguments) rows, remembering each signature.

    The schema makes the call id optional; when it is absent Hutch derives a stable id from the call
    itself so the signature cache and the tool-result association still line up.
    """
    import hashlib

    out: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        part = call["part"]
        name = str(part.get("name") or "")
        if not name:
            raise ProviderError("bad_request", "Gemini returned a function call with no name", provider=provider)
        arguments = part.get("args") if isinstance(part.get("args"), dict) else {}
        call_id = str(part.get("id") or "")
        if not call_id:
            seed = json.dumps([name, arguments, index, served_model], sort_keys=True, ensure_ascii=False)
            call_id = "call_" + hashlib.sha256(seed.encode()).hexdigest()[:16]
        remember_signature(base_url, call_id, call.get("signature"))
        out.append({"id": call_id, "name": name, "arguments": arguments,
                    "raw": json.dumps(arguments, ensure_ascii=False)})
    return out


SIGNATURE_MESSAGE = (
    "Gemini rejected the request because a thought signature from an earlier function call is missing. "
    "Hutch keeps signatures only for the life of the running process; start a new conversation or "
    "select a model that does not require them.")
