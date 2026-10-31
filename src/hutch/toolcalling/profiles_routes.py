"""Route classification and the documented Google/Gemini capability declaration.

Split out of ``toolcalling/profiles.py`` to keep that frozen module from growing: the policy there
stays readable only if new route knowledge lands in its own file. Nothing here decides a tool mode;
these are inputs to ``resolve_profile``.

Evidence (read 2026-10-31):

* ``https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta`` (revision 20261030)
  defines ``functionDeclarations`` / ``functionCall`` / ``toolConfig.functionCallingConfig`` and the
  inline-media ``Part`` variant;
* ``https://ai.google.dev/gemini-api/docs/text-generation`` documents the ``alt=sse`` streaming shape;
* ``https://ai.google.dev/gemini-api/docs/thinking`` documents generateContent thought signatures.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

#: Exact official authorities. A lookalike host is never "official".
OFFICIAL_HOSTS = ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")

GOOGLE_PROTOCOL = "gemini"
GOOGLE_PARSER_ID = "hutch.gemini-tool-args.strictjson-v1"
#: Hutch's Gemini adapter sends no response schema, so constrained mode is unavailable on this route.
GOOGLE_CONSTRAINED_DEFAULT = ("unsupported", "")
GOOGLE_OBSERVED_ON = "2026-10-31"

#: ``key -> (state, detail, source)``; converted to ``Evidence`` rows in profiles.py.
GOOGLE_EVIDENCE = {
    "native_tools": ("documented", "generateContent functionDeclarations, answered with functionCall parts",
                     "Gemini API discovery document v1beta (revision 20261030)"),
    "tool_choice": ("documented", "AUTO/ANY/NONE/VALIDATED via toolConfig.functionCallingConfig",
                    "Gemini API discovery document v1beta"),
    "parallel_calls": ("documented", "several functionCall parts in one model turn",
                       "Gemini API discovery document v1beta"),
    "streaming_calls": ("documented", "functionCall parts arrive in streamGenerateContent SSE chunks",
                        "Gemini streaming docs (alt=sse)"),
    "constrained_schema": ("unsupported", "Hutch's Gemini adapter sends no response schema",
                           "hutch adapter review"),
    "strict_tool_schema": ("unknown", "", "Gemini API discovery document v1beta"),
    "multimodal": ("documented", "inline image parts on gemini chat models; Hutch never fetches a remote URL",
                   "Gemini API Blob/Part schema"),
}
GOOGLE_NOTES = ("Thought signatures travel with function-call parts; Hutch keeps them only for the life of "
                "the running process and reports the provider's MISSING_THOUGHT_SIGNATURE answer as a typed "
                "error.",)


def protocol_for_provider(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider == "anthropic":
        return "anthropic-messages"
    if provider == "google":
        return GOOGLE_PROTOCOL
    if provider == "ollama":
        return "ollama-native"
    if provider == "chatgpt":
        return "openai-responses"
    return "openai-chat"


def classify_endpoint(endpoint: Optional[str]) -> str:
    """local | official | custom | unknown - by exact authority, not a lookalike name."""
    if not endpoint:
        return "unknown"
    try:
        parts = urlsplit(endpoint.strip())
    except ValueError:
        return "unknown"
    host = (parts.hostname or "").lower()
    if not host:
        return "unknown"
    if host in LOCAL_HOSTS:
        return "local"
    if host in OFFICIAL_HOSTS:
        return "official"
    return "custom"
