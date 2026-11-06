"""One bounded download for a provider's result URL.

Providers return finished media as a short-lived URL (Runway 24 to 48 hours, MiniMax 24 hours,
fal per account setting). Every adapter used to fetch that URL its own way, with the body read
into memory before any size check. This helper is the single place that does it:

* the URL must be ``https`` (plain ``http`` only to a loopback or private address, which the
  pinned transport still judges), and it must not carry credentials;
* the request goes through the address-pinning transport (``offline.httpx_offline_options``), so a
  result URL cannot be used to reach a link-local or metadata address;
* provider credentials are never sent to the result host;
* up to three redirects are followed (result hosts are CDNs), every hop judged again;
* the body is streamed and the download stops the moment it exceeds the limit.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlsplit

from .storage import MAX_MEDIA_BYTES

_MAX_REDIRECTS = 3
_CHUNK = 64 * 1024


class FetchError(RuntimeError):
    """The result could not be downloaded within the rules above."""


def _check_url(url: str) -> str:
    parts = urlsplit(str(url or ""))
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise FetchError("the provider's result URL is not an http(s) address")
    if parts.username or parts.password:
        raise FetchError("the provider's result URL carries credentials and was refused")
    return parts.geturl()


def download(url: str, *, max_bytes: int = MAX_MEDIA_BYTES, timeout: float = 60.0,
             client: Optional[Any] = None) -> bytes:
    """Return the body of ``url``, or raise :class:`FetchError`. ``client`` is injectable for
    tests that need failure injection; the default path builds a pinned client per hop."""
    import httpx

    from ..providers.endpoint_policy import EndpointRefused

    current = _check_url(url)
    for _ in range(_MAX_REDIRECTS + 1):
        owned = client is None
        http = client or _pinned_client(current, timeout)
        try:
            with http.stream("GET", current if not owned else _relative(current),
                             headers={"User-Agent": "hutch/media"}) as response:
                status = response.status_code
                if 300 <= status < 400:
                    current = _check_url(_resolve(current, response.headers.get("location")))
                    continue
                if status != 200:
                    raise FetchError(
                        f"the result URL answered HTTP {status}; it may have expired "
                        "(result URLs are short-lived and are not retried)")
                return read_bounded(response, max_bytes)
        except EndpointRefused as exc:
            raise FetchError(f"the result address was refused: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise FetchError("the result download timed out") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"the result could not be downloaded: {exc}") from exc
        finally:
            if owned:
                http.close()
    raise FetchError(f"the result URL redirected more than {_MAX_REDIRECTS} times")


def read_bounded(response: Any, max_bytes: int, *, allow_empty: bool = False) -> bytes:
    """Stream a response body, stopping the moment it passes ``max_bytes``."""
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise FetchError(f"the result is {int(declared)} bytes, over the {max_bytes} byte limit")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes(_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise FetchError(f"the result passed the {max_bytes} byte limit while downloading")
        chunks.append(chunk)
    if total == 0 and not allow_empty:
        raise FetchError("the result URL returned an empty body")
    return b"".join(chunks)


def _pinned_client(url: str, timeout: float) -> Any:
    import httpx

    from ..offline import httpx_offline_options

    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    base_url, transport, trust_env = httpx_offline_options(origin, "media-result")
    return httpx.Client(base_url=base_url, transport=transport, trust_env=trust_env,
                        timeout=httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=5.0))


def _relative(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "") or "/"


def _resolve(current: str, location: Optional[str]) -> str:
    from urllib.parse import urljoin

    if not location:
        raise FetchError("the result URL redirected without a Location header")
    return urljoin(current, location)
