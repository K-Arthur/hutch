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
        raise ProviderError(
            "auth", f"no API key for connection '{name}': set {conn.api_key_env or 'an environment variable'} in the "
                    f"environment that starts hutch, or run `hutch connections set-key {name}`", provider=name)
    protocol, base = conn.endpoint_for(model)
    headers = {"User-Agent": conn.user_agent, **conn.headers}
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
    spent_tokens: bool = False


def check_connection(book: ConnectionBook, name: str, chat_model: str = "") -> ConnectionCheck:
    """Verify a connection WITHOUT spending tokens: authenticate against the models list.

    Anthropic-protocol endpoints have no standard list, and some plans do not expose one; for those the check
    only proves a key is present, and says so. ``chat_model`` opts into one real 1-token chat (spends a little).
    """
    conn = book.get(name)
    if conn is None:
        return ConnectionCheck(False, f"no connection named '{name}'")
    try:
        provider = provider_for_connection(book, name, chat_model or "probe")
    except ProviderError as exc:
        return ConnectionCheck(False, str(exc))
    if chat_model:
        from .base import ChatRequest
        try:
            res = provider.chat(ChatRequest(model=chat_model, messages=[{"role": "user", "content": "Reply with: ok"}],
                                            max_tokens=8, stream=False, session_id="hutch-connection-test"))
        except ProviderError as exc:
            return ConnectionCheck(False, f"the chat call failed ({exc.kind}): {exc}", spent_tokens=True)
        return ConnectionCheck(True, f"{chat_model} answered ({res.prompt_tokens + res.completion_tokens} tokens used)",
                               spent_tokens=True)
    if not conn.models_endpoint or conn.protocol == "anthropic":
        return ConnectionCheck(True, "a key is present, but this endpoint has no model list to authenticate against, "
                                     "so it was not verified. Use --chat <model> to spend one tiny call and prove it.")
    ok, detail, models = provider.probe_models()
    return ConnectionCheck(ok, detail, models)
