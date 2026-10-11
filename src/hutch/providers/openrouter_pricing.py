"""Live OpenRouter endpoint quotes, in Decimal, with an explicit freshness policy (SR-2).

Contracts verified 2026-10-11 against the official API reference
(https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties and
.../endpoints/list-all-endpoints-for-a-model):

* ``GET /api/v1/models/{author}/{slug}/endpoints`` returns ``data.endpoints[]``; each endpoint carries
  ``context_length``, ``max_prompt_tokens``, ``max_completion_tokens``, ``provider_name``,
  ``supported_parameters``, ``status`` and ``pricing`` as decimal **strings in USD per token**
  (``prompt``, ``completion``, ``request``, ``input_cache_read``, ``input_cache_write``, ...).
* Public reads need no key; per-endpoint latency/throughput stats are simply null when unauthenticated.
* Conditional ``overrides`` (long-context/time-based rates) are not applied to a conservative worst
  case: Hutch uses the base rates and labels the quote basis as such. Top-level pricing reflects the
  default conditions.
* Prices change without notice, so a quote is only trusted within ``DEFAULT_TTL_SECONDS``; a stale one
  is still usable as a *labeled* fallback (:class:`QuotePolicy`), never silently refreshed as "live".

The service never invents a number. A missing, null, negative, or non-finite required rate makes the
endpoint ineligible; if no endpoint survives, the model has no quote and admission falls back to the
reviewed price file or refuses under a strict policy.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

from ..money import ZERO, call_cost, per_million_from_per_token, quantize_up

DEFAULT_TTL_SECONDS = 900.0        # 15 minutes: short enough to catch drift, long enough to dedupe a run
HTTP_TIMEOUT_SECONDS = 5.0
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class QuoteUnavailable(RuntimeError):
    """No usable quote could be established for this model (network, schema, or all endpoints invalid)."""


def _decimal(raw: Any, *, field_name: str, allow_none: bool = False) -> Optional[Decimal]:
    """Parse a provider decimal string exactly; reject anything that cannot be a real rate."""
    if raw is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} is missing")
    if isinstance(raw, bool):
        raise ValueError(f"{field_name} is not a number")
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} is not a decimal number") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return value


@dataclass(frozen=True)
class EndpointQuote:
    """One provider endpoint's published rates (USD per million tokens, Decimal)."""

    name: str
    provider_name: str
    input_per_million: Decimal
    output_per_million: Decimal
    request_fee_usd: Decimal = ZERO
    cache_read_per_million: Optional[Decimal] = None
    cache_write_per_million: Optional[Decimal] = None
    context_length: int = 0            # 0 = unknown (kept, conservatively admissible)
    max_completion_tokens: int = 0
    supports_tools: Optional[bool] = None   # None = the catalog did not say
    status: int = 0                    # OpenRouter: 0 is healthy; negative values are degraded/unavailable

    def call_cost(self, prompt_tokens: int, completion_tokens: int, *,
                  cached_tokens: int = 0, cache_write_tokens: int = 0) -> Decimal:
        return call_cost(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                         input_per_million=self.input_per_million, output_per_million=self.output_per_million,
                         cache_read_per_million=self.cache_read_per_million,
                         cache_write_per_million=self.cache_write_per_million,
                         cached_tokens=cached_tokens, cache_write_tokens=cache_write_tokens,
                         request_fee=self.request_fee_usd)


@dataclass(frozen=True)
class ModelQuote:
    model: str
    endpoints: tuple[EndpointQuote, ...]
    fetched_at: datetime
    source: str = ""
    stale: bool = False

    def worst_case(self, prompt_tokens: int, completion_tokens: int, *,
                   cached_tokens: int = 0, cache_write_tokens: int = 0,
                   eligible: Optional[Callable[[EndpointQuote], bool]] = None) -> Optional[Decimal]:
        """Max full-call cost across eligible endpoints, rounded up. Mixing rates from different
        endpoints is not a routable price, so the maximum of each endpoint's whole cost is used."""
        predicate = eligible or (lambda endpoint: endpoint.status == 0)
        costs = [endpoint.call_cost(prompt_tokens, completion_tokens, cached_tokens=cached_tokens,
                                    cache_write_tokens=cache_write_tokens)
                 for endpoint in self.endpoints if predicate(endpoint)]
        if not costs:
            return None
        return quantize_up(max(costs))

    def worst_input_per_million(self, eligible: Optional[Callable[[EndpointQuote], bool]] = None) -> Decimal:
        predicate = eligible or (lambda endpoint: endpoint.status == 0)
        rates = [endpoint.input_per_million for endpoint in self.endpoints if predicate(endpoint)]
        return max(rates) if rates else ZERO


def parse_endpoints_payload(payload: Any, model: str, *, fetched_at: datetime,
                            source: str = "") -> ModelQuote:
    """Validate an endpoints response. Invalid endpoints are dropped with the rest still usable."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("endpoints"), list):
        raise ValueError("endpoint payload does not contain a data.endpoints list")
    endpoints: list[EndpointQuote] = []
    for row in data["endpoints"]:
        if not isinstance(row, dict):
            continue
        pricing = row.get("pricing")
        if not isinstance(pricing, dict):
            continue
        try:
            input_per_million = per_million_from_per_token(_decimal(pricing.get("prompt"), field_name="prompt"))
            output_per_million = per_million_from_per_token(_decimal(pricing.get("completion"), field_name="completion"))
            request_fee = _decimal(pricing.get("request"), field_name="request", allow_none=True) or ZERO
            cache_read = _decimal(pricing.get("input_cache_read"), field_name="input_cache_read", allow_none=True)
            cache_write = _decimal(pricing.get("input_cache_write"), field_name="input_cache_write", allow_none=True)
        except ValueError:
            continue
        if cache_read is not None:
            cache_read = per_million_from_per_token(cache_read)
        if cache_write is not None:
            cache_write = per_million_from_per_token(cache_write)
        parameters = row.get("supported_parameters")
        supports_tools = ("tools" in parameters) if isinstance(parameters, list) else None
        endpoints.append(EndpointQuote(
            name=str(row.get("name") or row.get("provider_name") or "endpoint")[:120],
            provider_name=str(row.get("provider_name") or "")[:80],
            input_per_million=input_per_million, output_per_million=output_per_million,
            request_fee_usd=request_fee, cache_read_per_million=cache_read,
            cache_write_per_million=cache_write,
            context_length=_positive_int(row.get("context_length")),
            max_completion_tokens=_positive_int(row.get("max_completion_tokens")),
            supports_tools=supports_tools, status=_status(row.get("status"))))
    if not endpoints:
        raise ValueError("no endpoint carried a usable price")
    return ModelQuote(model=model, endpoints=tuple(endpoints), fetched_at=fetched_at, source=source)


def _positive_int(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return 0
    return raw


def _status(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw


def split_model_id(model: str) -> tuple[str, str]:
    """'author/slug:variant' -> ('author', 'slug'); a leading '~' latest-alias marker is dropped."""
    base = (model or "").strip().lstrip("~")
    base = base.split(":", 1)[0]
    author, _, slug = base.partition("/")
    return author.strip(), slug.strip()


class OpenRouterPricing:
    """In-process quote cache with single-flight refreshes and a documented TTL.

    A stale quote is returned with ``stale=True`` and must be treated as a labeled fallback; this class
    never claims a stale value is live. Cross-process dedupe is deliberately not attempted: a duplicate
    public GET is cheaper than a shared lock file that could wedge admission.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *,
                 fetcher: Optional[Callable[[str], Any]] = None,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 clock: Optional[Callable[[], datetime]] = None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._fetcher = fetcher or self._http_fetch
        self._ttl = max(0.0, float(ttl_seconds))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: dict[str, ModelQuote] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self.last_error: str = ""

    # ------------------------------------------------------------------ fetch

    def _http_fetch(self, model: str) -> Any:
        import httpx
        author, slug = split_model_id(model)
        if not author or not slug:
            raise QuoteUnavailable(f"'{model}' is not an OpenRouter model id")
        url = f"{self.base_url}/models/{author}/{slug}/endpoints"
        response = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS,
                             headers={"User-Agent": "hutch/0.4 (endpoint pricing; metadata only)"})
        if response.status_code >= 400:
            raise QuoteUnavailable(f"OpenRouter endpoint metadata returned HTTP {response.status_code}")
        return response.json()

    def refresh(self, model: str, *, force: bool = False) -> Optional[ModelQuote]:
        """Fetch (or return a cached) quote. ``None`` means no quote could be parsed; the reason is in
        ``last_error``. Concurrent callers for the same model share one fetch."""
        key = model.strip()
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and not force and (now - cached.fetched_at).total_seconds() <= self._ttl:
                return cached
            event = self._inflight.get(key)
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
                owner = True
            else:
                owner = False
        if not owner:
            event.wait(timeout=HTTP_TIMEOUT_SECONDS + 2.0)
            with self._lock:
                return self._cache.get(key)
        try:
            try:
                payload = self._fetcher(key)
                quote = parse_endpoints_payload(payload, key, fetched_at=self._clock(),
                                                source=f"{self.base_url}/models/{key}/endpoints")
            except Exception as exc:  # network, HTTP, or schema: no quote, never a guess
                self.last_error = f"{type(exc).__name__}: {exc}"
                with self._lock:
                    cached = self._cache.get(key)
                    if cached is not None:
                        cached = ModelQuote(model=cached.model, endpoints=cached.endpoints,
                                            fetched_at=cached.fetched_at, source=cached.source, stale=True)
                        self._cache[key] = cached
                    return cached
            with self._lock:
                self._cache[key] = quote
            return quote
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            event.set()

    def quote(self, model: str, *, allow_stale: bool = True) -> Optional[ModelQuote]:
        """A cached fresh quote, else a refresh; a stale entry is labeled when allowed."""
        key = model.strip()
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                age = (now - cached.fetched_at).total_seconds()
                if age <= self._ttl:
                    return cached
        quote = self.refresh(key, force=True)
        if quote is not None and quote.stale and not allow_stale:
            return None
        return quote

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int, *,
             cached_tokens: int = 0, cache_write_tokens: int = 0,
             eligible: Optional[Callable[[EndpointQuote], bool]] = None,
             allow_stale: bool = True) -> Optional[Decimal]:
        """Conservative worst-case USD for one call, or None when no quote exists."""
        quote = self.quote(model, allow_stale=allow_stale)
        if quote is None:
            return None
        return quote.worst_case(prompt_tokens, completion_tokens, cached_tokens=cached_tokens,
                                cache_write_tokens=cache_write_tokens, eligible=eligible)

    def invalidate(self, model: str = "") -> None:
        with self._lock:
            if model:
                self._cache.pop(model.strip(), None)
            else:
                self._cache.clear()

    def fetched_at_iso(self, model: str) -> str:
        with self._lock:
            cached = self._cache.get(model.strip())
        return cached.fetched_at.isoformat() if cached is not None else ""


_LIVE_LOCK = threading.Lock()
_LIVE: dict[str, OpenRouterPricing] = {}


def live_pricing(base_url: str = DEFAULT_BASE_URL, **kwargs) -> OpenRouterPricing:
    """One pricing service per base URL, so concurrent runs share the TTL cache."""
    key = (base_url or DEFAULT_BASE_URL).rstrip("/")
    with _LIVE_LOCK:
        service = _LIVE.get(key)
        if service is None or kwargs:
            service = OpenRouterPricing(key, **kwargs)
            if not kwargs:
                _LIVE[key] = service
        return service
