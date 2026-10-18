"""Model specs -> providers.

A spec is ``provider/model``:  ollama/llama3.2 - anthropic/claude-opus-5-5 - openai/gpt-4o-mini -
lmstudio/qwen2.5-7b - llamacpp/<name> - openai-compatible/<name> (base_url required).

Routing rule that matters (LM-1): an ``openai-compatible`` URL that is really an Ollama server is sent to the
NATIVE Ollama provider, because Ollama's ``/v1`` endpoint cannot set the context size and silently truncates.
"""

from __future__ import annotations

import os
import ipaddress
import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .base import Provider, ProviderError

OLLAMA_PORT = 11434


#: The only host an AMBIENT key (one picked up from the environment) may be sent to, per provider. A key belongs to
#: the service that issued it: pointing a bot at a custom or local URL must never hand it the OpenAI or Anthropic key.
#: A Connection (providers/connection.py) names its own key and endpoint on purpose and is not filtered here.
OFFICIAL_HOSTS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}


def reject_endpoint_credentials(url: str) -> str:
    """No HTTP basic credentials in URLs: endpoints are visible in status, errors and reviews."""
    try:
        parts = urlsplit(url)
        if parts.username is not None or parts.password is not None:
            raise ProviderError("bad_request", "provider endpoints cannot embed credentials; use a connection key reference")
    except ValueError as exc:
        raise ProviderError("bad_request", "provider endpoint is malformed") from exc
    return url

def is_official_endpoint(provider: str, url: Optional[str]) -> bool:
    """True if ``url`` is exactly the provider's own HTTPS host (look-alikes, userinfo tricks and plain HTTP are not)."""
    host = OFFICIAL_HOSTS.get(provider)
    if not host or not url:
        return False
    try:
        parts = urlsplit(url.strip())
        return (parts.scheme == "https" and (parts.hostname or "").lower() == host
                and parts.port in (None, 443) and parts.username is None and parts.password is None)
    except ValueError:
        return False


def ambient_key(provider: str, url: Optional[str], env) -> tuple[str, str]:
    """(key, hint): the environment key for ``provider`` if it may be sent to ``url``, else ("", why it was withheld)."""
    name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
    key = env.get(name, "") if name else ""
    if not key:
        return "", ""
    if is_official_endpoint(provider, url):
        return key, ""
    return "", (f"{name} is only ever sent to {OFFICIAL_HOSTS[provider]} (https). This endpoint is {url or 'custom'}, so no key "
                "was sent: create a connection with its own key (`hutch connections`) or set HUTCH_API_KEY for a custom endpoint")


def parse_spec(spec: str) -> tuple[str, str]:
    provider, sep, model = spec.partition("/")
    if not sep:
        return "openai-compatible", spec
    return provider.strip().lower(), model.strip()


#: provider/model: the provider is a lowercase slug, the model may contain further slashes (OpenRouter ids)
_SPEC_RE = re.compile(r"^([a-z0-9][a-z0-9._-]{0,40})/([A-Za-z0-9~][A-Za-z0-9._:+/~-]{0,160})$")


def validate_spec(spec: str) -> tuple[str, str]:
    """An explicit provider/model routing spec; an unresolved alias or prose is rejected, never guessed."""
    match = _SPEC_RE.match(str(spec or "").strip())
    if not match:
        raise ValueError("expected an explicit 'provider/model' spec")
    return match.group(1), match.group(2)


def looks_like_ollama(base_url: Optional[str]) -> bool:
    if not base_url:
        return False
    parts = urlsplit(base_url)
    return parts.port == OLLAMA_PORT


def is_local(spec: str) -> bool:
    from .pricing import is_local_route
    provider, model = parse_spec(spec)
    return is_local_route(provider, model)


def validate_inference_mode(mode, spec: str, *, base_url: Optional[str] = None) -> None:
    """Validate the primary route for local-routing or strict-offline policy."""
    value = getattr(mode, "value", mode)
    if value in ("local", "offline") and not is_local(spec):
        raise ValueError(
            f"{spec} is not an allowed local model route; choose a local model or switch inference mode to Hybrid."
        )
    if value == "offline":
        validate_offline_route(spec, base_url)


_OFFLINE_DEFAULTS = {
    "ollama": "http://localhost:11434",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "llama.cpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}


def default_endpoint(provider: str) -> str:
    """The endpoint a built-in route uses when no explicit base URL is configured."""
    if provider == "anthropic":
        return "https://api.anthropic.com"
    if provider == "openai":
        return "https://api.openai.com/v1"
    return _OFFLINE_DEFAULTS.get(provider, "")


def resolve_route_endpoint(provider: str, configured: str = "", *, connection_endpoint: str = "") -> str:
    """ONE endpoint-derivation chain for a model rung (ADR-0017 §5 S0 reconciliation).

    ``runtime/builtin._route_identity`` (authorization) and ``_resolve_tool_profile`` (capability
    evidence) each re-implemented the OLLAMA_HOST / ANTHROPIC_BASE_URL / HUTCH_BASE_URL /
    preset-default fallbacks. Divergence there would let ``classify_endpoint`` return a different
    endpoint_class for the same route and silently change the route's capability evidence, so both
    call sites now derive through this function. A connection's own endpoint (from
    ``endpoint_for``) is passed in by the caller and always wins; the fallbacks run in one order:

        configured base_url -> OLLAMA_HOST (ollama) -> ANTHROPIC_BASE_URL (anthropic)
        -> HUTCH_BASE_URL (openai-compatible) -> default_endpoint(provider) -> ""

    Two documented normalizations (the S0 reconciliation, docs/realignment/artifacts/
    mcp-s0-2026-10-11/reconciliation.md): a connectionless ollama rung now resolves its loopback
    default instead of "" (route identity is only consumed for hosted rungs, so authorization is
    unaffected), and ANTHROPIC_BASE_URL is honored before the official default so relocated
    Anthropic endpoints classify the same way for authorization and capability evidence.
    """
    endpoint = connection_endpoint or configured
    if provider == "ollama":
        endpoint = endpoint or os.environ.get("OLLAMA_HOST") or ""
    if provider == "anthropic":
        endpoint = endpoint or os.environ.get("ANTHROPIC_BASE_URL") or ""
    elif provider == "openai-compatible":
        endpoint = endpoint or os.environ.get("HUTCH_BASE_URL", "")
    if not endpoint:
        endpoint = default_endpoint(provider)
    return endpoint


def loopback_endpoint(provider: str, url: Optional[str] = None) -> str:
    """Return a loopback-only local model endpoint or reject the route.

    Hostnames other than the exact ``localhost`` label are not resolved here:
    accepting arbitrary names would make the decision depend on DNS at request
    time. ``localhost`` is rewritten to its numeric IPv4 loopback address.
    """
    endpoint = url or _OFFLINE_DEFAULTS.get(provider)
    if not endpoint:
        raise ValueError(f"{provider} needs an explicit loopback endpoint in strict offline mode")
    try:
        parts = urlsplit(endpoint.strip())
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError("endpoint must be a plain HTTP loopback URL")
        if parts.username is not None or parts.password is not None:
            raise ValueError("endpoint cannot embed credentials in strict offline mode")
        if parts.query:
            raise ValueError("endpoint cannot embed query parameters in strict offline mode")
        host = parts.hostname.lower()
        if "%" in host:
            raise ValueError("scoped IPv6 endpoints are not accepted in strict offline mode")
        if host == "localhost":
            host = "127.0.0.1"
        else:
            address = ipaddress.ip_address(host)
            if not address.is_loopback:
                raise ValueError("strict offline model endpoints must use loopback")
            host = address.compressed
        port = parts.port
        if port == 0:
            raise ValueError("endpoint must use a nonzero port")
    except ValueError as exc:
        raise ValueError(f"strict offline requires a valid loopback model endpoint: {exc}") from None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def validate_offline_route(spec: str, base_url: Optional[str] = None) -> None:
    provider, model = parse_spec(spec)
    if not model or not is_local(spec):
        raise ValueError(f"{spec} is not a local inference route")
    loopback_endpoint(provider, base_url)


def offline_endpoints_for_bot(bot, *, model_override: str = "") -> list[str]:
    """Validated loopback origins needed by a Strict Offline run and its route ladder."""
    primary_provider, _ = parse_spec(bot.model)
    routes = [(bot.model, bot.base_url)]
    routes.extend((spec, bot.base_url if parse_spec(spec)[0] == primary_provider else None)
                  for spec in bot.fallbacks)
    if bot.escalation:
        routes.extend((spec, bot.base_url if parse_spec(spec)[0] == primary_provider else None)
                      for spec in bot.escalation.to)
    routes.extend((spec, bot.base_url if parse_spec(spec)[0] == primary_provider else None)
                  for spec in getattr(bot, "task_routes", {}).values())
    if model_override:
        routes.append((model_override, bot.base_url if parse_spec(model_override)[0] == primary_provider else None))
    endpoints = []
    for spec, endpoint in routes:
        validate_offline_route(spec, endpoint)
        provider, _ = parse_spec(spec)
        resolved = loopback_endpoint(provider, endpoint)
        if resolved:
            endpoints.append(resolved)
    return endpoints


def validate_offline_bot(bot, *, model_override: str = "", check_host: bool = True,
                         refresh_host: bool = False) -> None:
    """Validate persisted routing, runtime, shell and endpoint settings before an Offline run starts."""
    if getattr(getattr(bot, "inference_mode", None), "value", getattr(bot, "inference_mode", "")) != "offline":
        return
    if getattr(getattr(bot, "runtime", None), "value", getattr(bot, "runtime", "")) != "builtin":
        raise ValueError("Strict offline supports only Hutch's built-in runtime")
    offline_endpoints_for_bot(bot, model_override=model_override)
    from ..tools import expand_tools
    has_shell = "shell" in expand_tools(bot.tools)
    if has_shell and bot.sandbox != "strict":
        raise ValueError("Strict offline requires the strict shell sandbox; remove shell or enable strict sandboxing")
    if has_shell and bot.shell_network:
        raise ValueError("Strict offline cannot allow shell network access")
    if check_host:
        from .. import sandbox
        if has_shell and sandbox.global_override() == "off":
            raise ValueError("Strict offline cannot run while HUTCH_SANDBOX=off disables shell containment")
        from ..sandbox import offline_egress_status
        status = offline_egress_status(refresh=True) if refresh_host else offline_egress_status()
        if not status.ok:
            raise ValueError(f"Strict offline is unavailable on this host: {status.reason}")


def make_provider(provider: str, base_url: Optional[str] = None, env: Optional[dict] = None) -> Provider:
    """Build a provider. Imports of vendor SDKs happen lazily inside the provider on first use (PF-6)."""
    env = env if env is not None else os.environ
    if provider == "ollama" or (provider == "openai-compatible" and looks_like_ollama(base_url)):
        from .ollama import OllamaProvider
        return OllamaProvider(base_url or env.get("OLLAMA_HOST") or "http://localhost:11434")
    if provider == "anthropic":
        from .claude import ClaudeProvider
        url = base_url or env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        key, hint = ambient_key("anthropic", url, env)
        p = ClaudeProvider(api_key=key, base_url=url)
        p.key_withheld = hint
        return p
    from .openai_compat import PRESET_URLS, OpenAICompatProvider
    if provider == "openai-compatible":
        url = base_url or env.get("HUTCH_BASE_URL")
        if not url:
            raise ProviderError("bad_request", "openai-compatible models need bot.base_url (or HUTCH_BASE_URL)",
                                provider=provider)
        # A custom endpoint is not OpenAI: it never receives OPENAI_API_KEY. HUTCH_API_KEY is the variable a person sets on
        # purpose for the endpoint named by HUTCH_BASE_URL / bot.base_url.
        key, hint = env.get("HUTCH_API_KEY", ""), ""
        if not key:
            key, hint = ambient_key("openai", url, env)
        return OpenAICompatProvider(url, key, provider_name="openai-compatible", auth_hint=hint)
    if provider in PRESET_URLS:
        url = base_url or PRESET_URLS[provider]
        key, hint = ambient_key("openai", url, env) if provider == "openai" else ("", "")
        return OpenAICompatProvider(url, key, provider_name=provider, auth_hint=hint)
    raise ProviderError("bad_request", f"unknown provider '{provider}' (try ollama, anthropic, openai, lmstudio, "
                                       "llamacpp, openai-compatible)", provider=provider)
