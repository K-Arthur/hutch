"""Model specs -> providers.

A spec is ``provider/model``:  ollama/llama3.2 - anthropic/claude-opus-5-5 - openai/gpt-4o-mini -
lmstudio/qwen2.5-7b - llamacpp/<name> - openai-compatible/<name> (base_url required) - mock/demo.

Routing rule that matters (LM-1): an ``openai-compatible`` URL that is really an Ollama server is sent to the
NATIVE Ollama provider, because Ollama's ``/v1`` endpoint cannot set the context size and silently truncates.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlsplit

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


def looks_like_ollama(base_url: Optional[str]) -> bool:
    if not base_url:
        return False
    parts = urlsplit(base_url)
    return parts.port == OLLAMA_PORT


def is_local(spec: str) -> bool:
    from .pricing import LOCAL_PROVIDERS
    provider, _ = parse_spec(spec)
    return provider in LOCAL_PROVIDERS


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
                                       "llamacpp, openai-compatible, mock)", provider=provider)
