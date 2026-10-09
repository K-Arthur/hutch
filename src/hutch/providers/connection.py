"""Build a provider for a Connection + model (protocol, endpoint, key, required headers)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..connections import Connection, ConnectionBook
from .base import Provider, ProviderError


def provider_for_connection(book: ConnectionBook, name: str, model: str, *, resolved_key: str | None = None) -> Provider:
    conn: Connection | None = book.get(name)
    if conn is None:
        raise ProviderError("bad_request", f"no connection named '{name}'", provider=name)
    key = book.key(name) if resolved_key is None else resolved_key
    if not key:
        if conn.auth_type == "chatgpt-siws":
            raise ProviderError("auth", "Sign in with ChatGPT and authorize plan use on Connections",
                                provider=name)
        raise ProviderError(
            "auth", f"no API key for connection '{name}': set {conn.api_key_env or 'an environment variable'} in the "
                    f"environment that starts hutch, or run `hutch connections set-key {name}`", provider=name)
    protocol, base = conn.endpoint_for(model)
    headers = {"User-Agent": conn.user_agent, **conn.headers}
    if conn.auth_type == "chatgpt-siws":
        if protocol != "openai-responses":
            raise ProviderError("bad_request", "Sign in with ChatGPT is available only through its Responses API route",
                                provider=name)
        from .openai_responses import OpenAIResponsesProvider
        return OpenAIResponsesProvider(key, base_url=base)
    if protocol == "openai-chat":
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(base, key, provider_name=name, headers=headers, session_header=conn.session_header)
    if protocol == "anthropic":
        from .claude import ClaudeProvider
        return ClaudeProvider(api_key=key, base_url=base, provider_name=name, headers=headers,
                              session_header=conn.session_header)
    raise ProviderError("bad_request", f"protocol '{protocol}' is not supported", provider=name)


@dataclass
class ConnectionCheck:
    ok: bool
    detail: str
    models: list[str] = field(default_factory=list)


def check_connection(book: ConnectionBook, name: str) -> ConnectionCheck:
    """Check authentication/discovery without making a model request.

    Anthropic-protocol endpoints have no standard list, and some plans do not expose one; for those the check
    only proves a key is present, and says so. Model capability checks must use a normal governed bot run so
    shared usage reservations, approvals, receipts, and uncertain-outcome reconciliation apply.
    """
    conn = book.get(name)
    if conn is None:
        return ConnectionCheck(False, f"no connection named '{name}'")
    try:
        provider = provider_for_connection(book, name, "probe")
    except ProviderError as exc:
        return ConnectionCheck(False, str(exc))
    if not conn.models_endpoint or conn.protocol == "anthropic":
        return ConnectionCheck(True, "a key is present, but this endpoint has no model list to authenticate against, "
                                     "so it was not verified. Run a normal bot request to check model behavior through "
                                     "Hutch's usage and approval controls.")
    ok, detail, models = provider.probe_models()
    return ConnectionCheck(ok, detail, models)
