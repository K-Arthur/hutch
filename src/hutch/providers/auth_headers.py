"""Keys that travel in a named header instead of ``Authorization: Bearer``.

Some hosts read a resource key from a vendor header and treat a Bearer value as a Microsoft Entra ID token
(Azure OpenAI v1 reads ``api-key``). A template declares that with a header whose whole value is
``{api_key}``. The key is substituted only when a provider is built, so the template, the stored connection,
the catalogue and every API response keep the placeholder and never the key.
"""

from __future__ import annotations

from typing import Mapping

KEY_PLACEHOLDER = "{api_key}"


def uses_key_header(headers: Mapping[str, str]) -> bool:
    return any(value == KEY_PLACEHOLDER for value in headers.values())


def bind_key_headers(headers: Mapping[str, str], key: str) -> tuple[dict[str, str], str]:
    """Return ``(headers with the key filled in, bearer key to hand the provider)``.

    When a header carries the key, the bearer key is empty so the key is sent in exactly one place. A
    placeholder embedded in a longer value is a template bug and is refused rather than sent literally.
    """
    bound: dict[str, str] = {}
    for name, value in headers.items():
        if value == KEY_PLACEHOLDER:
            bound[name] = key
        elif KEY_PLACEHOLDER in str(value):
            raise ValueError(f"header '{name}' must be exactly {KEY_PLACEHOLDER} or contain no placeholder")
        else:
            bound[name] = value
    return bound, "" if uses_key_header(headers) else key
