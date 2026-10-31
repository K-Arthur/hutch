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
        return OpenAICompatProvider(base, key, provider_name=name, headers=headers, session_header=conn.session_header,
                                    openrouter=conn.template == "openrouter", routing_policy=conn.openrouter_policy)
    if protocol == "anthropic":
        from .claude import ClaudeProvider
        return ClaudeProvider(api_key=key, base_url=base, provider_name=name, headers=headers,
                              session_header=conn.session_header)
    if protocol == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(api_key=key, base_url=base, provider_name=name, headers=headers,
                              session_header=conn.session_header)
    raise ProviderError("bad_request", f"protocol '{protocol}' is not supported", provider=name)


@dataclass
class ConnectionCheck:
    ok: bool
    detail: str
    models: list[str] = field(default_factory=list)
    verified: bool = False


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
    if not conn.models_endpoint:
        return ConnectionCheck(True, "a key is present, but this endpoint has no model list to authenticate against, "
                                     "so it was not verified. Run a normal bot request to check model behavior through "
                                     "Hutch's usage and approval controls.", verified=False)
    ok, detail, models = provider.probe_models()
    return ConnectionCheck(ok, detail, models, verified=ok)


# ----------------------------------------------------------------- typed probe

_READY_PROMPT = "Reply with the word ready."


def _datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _openrouter_kind(detail: str) -> tuple[str, int]:
    """OpenRouter's public catalog answers 200 even for a bad key; read its /key verdict."""
    low = detail.lower()
    if "management" in low or "provisioning" in low:
        return "auth", 403
    if "rejected" in low:
        return "auth", 401
    return "server", 0


def probe_connection_typed(book: ConnectionBook, name: str, *, mode: str = "metadata",
                           model: str = "", now=None):
    """Typed readiness probe (server-side only). Returns a ``route_readiness.ProbeResult``.

    ``metadata`` lists models and can only yield saved-unverified. ``generation`` makes one
    explicit, tool-free, one-token request and is the only path that can yield verified. The
    stored key is redacted from every detail; nothing here logs, stores or returns it.
    """
    from .. import route_readiness as rr

    at = now or _datetime_now()
    key = book.key(name) if book.get(name) else None

    def fail(kind: str, text: object, status=None, retry_after=None):
        return rr.failure_result(kind, mode=mode, detail=rr.safe_detail(text, key), now=at,
                                 http_status=status, retry_after=retry_after)

    conn = book.get(name)
    if conn is None:
        return fail("bad_request", f"no connection named '{name}'")
    if mode == rr.MODE_GENERATION and not model:
        return fail("model_missing", "choose a model to test")
    try:
        provider = provider_for_connection(book, name, model or "probe")
    except ProviderError as exc:
        return fail(exc.kind, exc, exc.status, exc.retry_after)
    if mode == rr.MODE_GENERATION:
        return _generation_probe(provider, model, at, fail, key)
    if not conn.models_endpoint or conn.auth_type != "api_key":
        return rr.metadata_result((), "This route has no model list to check, so Hutch has not "
                                      "tested it. Run a small test generation to find out.", at)
    ok, detail, models = provider.probe_models()
    if ok:
        return rr.metadata_result(models, rr.safe_detail(detail, key), at)
    try:
        provider.list_models()
    except ProviderError as exc:
        return fail(exc.kind, exc, exc.status, exc.retry_after)
    except Exception as exc:  # transport failure the adapter did not type
        return fail("other", exc)
    kind, status = _openrouter_kind(detail)
    return fail(kind, detail, status or None)


def _generation_probe(provider, model: str, at, fail, key):
    from .. import route_readiness as rr
    from .base import ChatRequest

    req = ChatRequest(model=model, messages=[{"role": "user", "content": _READY_PROMPT}],
                      stream=False, max_tokens=1, temperature=0, session_id="onboarding-readiness",
                      first_token_timeout=float(rr.PROBE_DEADLINE_SECONDS),
                      idle_timeout=float(rr.PROBE_DEADLINE_SECONDS), allow_stream_retry=False)
    try:
        provider.chat(req)
    except ProviderError as exc:
        return fail(exc.kind, exc, exc.status, exc.retry_after)
    except Exception as exc:
        return fail("other", exc)
    return rr.generation_result(model, "The route answered a one-token test request.", at)
