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
        return ClaudeProvider(base_url=base_url)
    from .openai_compat import PRESET_URLS, OpenAICompatProvider
    if provider == "openai-compatible":
        url = base_url or env.get("HUTCH_BASE_URL")
        if not url:
            raise ProviderError("bad_request", "openai-compatible models need bot.base_url (or HUTCH_BASE_URL)",
                                provider=provider)
        return OpenAICompatProvider(url, env.get("OPENAI_API_KEY", ""), provider_name="openai-compatible")
    if provider in PRESET_URLS:
        key = env.get("OPENAI_API_KEY", "") if provider == "openai" else ""
        return OpenAICompatProvider(base_url or PRESET_URLS[provider], key, provider_name=provider)
    raise ProviderError("bad_request", f"unknown provider '{provider}' (try ollama, anthropic, openai, lmstudio, "
                                       "llamacpp, openai-compatible, mock)", provider=provider)
