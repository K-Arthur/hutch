"""Live OpenRouter endpoint quotes, in Decimal, with an explicit freshness policy (SR-2).

Contracts verified 2026-10-11 against the official API reference
(https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties and
.../endpoints/list-all-endpoints-for-a-model):

* ``GET /api/v1/models/{author}/{slug}/endpoints`` returns ``data.endpoints[]``; each endpoint carries
  ``context_length``, ``max_prompt_tokens``, ``max_completion_tokens``, ``provider_name``,
  ``supported_parameters``, ``status`` and ``pricing`` as decimal **strings in USD per token**
  (``prompt``, ``completion``, ``request``, ``input_cache_read``, ``input_cache_write``, ...).
* The reference shows a bearer header and a management-key 403 example, but an unauthenticated public
  GET of both ``/models`` and one ``/models/{author}/{slug}/endpoints`` returned HTTP 200 on this date.
  Hutch reads only public metadata and never sends the user's inference key to another host.
* ``pricing.overrides`` was present in current live metadata for long-context rates, but its conditional
  schema is not fully documented. Hutch accepts only known price dimensions and prompt-token bounds;
  strict reservation uses the highest declared rate, while unknown conditions/dimensions make an endpoint
  ineligible.
* Prices change without notice, so a quote is only trusted within ``DEFAULT_TTL_SECONDS``. Stale and
  reviewed-file rates are fallbacks only when a strict currency ceiling does not require fresh metadata.

The service never invents a number. A missing, null, negative, or non-finite required rate makes the
endpoint ineligible; if no endpoint survives, strict admission refuses and non-strict paths may use a
labeled stale quote or reviewed local price file.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

from ..money import ZERO, call_cost, per_million_from_per_token, quantize_up

DEFAULT_TTL_SECONDS = 300.0        # 5 minutes: an expired quote must be refreshed before strict admission
HTTP_TIMEOUT_SECONDS = 5.0
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
MAX_CACHE_ENTRIES = 128
MAX_CONCURRENT_FETCHES = 4
MAX_RESPONSE_BYTES = 1_000_000
MAX_ENDPOINTS = 512
MAX_OVERRIDES_PER_ENDPOINT = 64


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
class PriceOverride:
    """One conditional endpoint rate row. Unknown conditions are handled conservatively as applicable."""

    min_prompt_tokens: int
    max_prompt_tokens: int
    input_per_million: Decimal
    output_per_million: Decimal
    request_fee_usd: Decimal = ZERO
    cache_read_per_million: Optional[Decimal] = None
    cache_write_per_million: Optional[Decimal] = None

    def applies(self, prompt_tokens: int) -> bool:
        return (prompt_tokens >= self.min_prompt_tokens
                and (self.max_prompt_tokens <= 0 or prompt_tokens <= self.max_prompt_tokens))


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
    max_prompt_tokens: int = 0
    max_completion_tokens: int = 0
    supports_tools: Optional[bool] = None   # None = the catalog did not say
    status: int = 0                    # OpenRouter: 0 is healthy; negative values are degraded/unavailable
    identity: str = ""
    overrides: tuple[PriceOverride, ...] = ()

    def effective_rates(self, prompt_tokens: int, *,
                        conservative_tiers: bool = False) -> tuple[Decimal, Decimal, Decimal, Optional[Decimal], Optional[Decimal]]:
        # Estimates are useful for display, but strict admission must allow for token-count error around a
        # published tier boundary. In that case the highest rate from every declared tier is the safe bound.
        applicable = (list(self.overrides) if conservative_tiers else
                      [override for override in self.overrides if override.applies(max(0, int(prompt_tokens)))])
        input_rates = [self.input_per_million, *(item.input_per_million for item in applicable)]
        output_rates = [self.output_per_million, *(item.output_per_million for item in applicable)]
        request_fees = [self.request_fee_usd, *(item.request_fee_usd for item in applicable)]
        read_rates = [item for item in (self.cache_read_per_million,
                                        *(override.cache_read_per_million for override in applicable))
                      if item is not None]
        write_rates = [item for item in (self.cache_write_per_million,
                                         *(override.cache_write_per_million for override in applicable))
                       if item is not None]
        return (max(input_rates), max(output_rates), max(request_fees),
                max(read_rates) if read_rates else None, max(write_rates) if write_rates else None)

    def call_cost(self, prompt_tokens: int, completion_tokens: int, *,
                  cached_tokens: int = 0, cache_write_tokens: int = 0,
                  conservative_tiers: bool = False) -> Decimal:
        input_rate, output_rate, request_fee, cache_read, cache_write = self.effective_rates(
            prompt_tokens, conservative_tiers=conservative_tiers)
        if conservative_tiers:
            # A miss can write cached input at a premium. Reserve the entire possible prompt at the highest
            # published input/cache rate; actual settlement still uses provider-reported token dimensions.
            input_rate = max(rate for rate in (input_rate, cache_read, cache_write) if rate is not None)
            cached_tokens = cache_write_tokens = 0
        return call_cost(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                         input_per_million=input_rate, output_per_million=output_rate,
                         cache_read_per_million=cache_read, cache_write_per_million=cache_write,
                         cached_tokens=cached_tokens, cache_write_tokens=cache_write_tokens,
                         request_fee=request_fee)


@dataclass(frozen=True)
class ModelQuote:
    model: str
    endpoints: tuple[EndpointQuote, ...]
    fetched_at: datetime
    source: str = ""
    stale: bool = False
    snapshot_digest: str = ""
    expires_at: Optional[datetime] = None

    def worst_case(self, prompt_tokens: int, completion_tokens: int, *,
                   cached_tokens: int = 0, cache_write_tokens: int = 0,
                   conservative_tiers: bool = False,
                   eligible: Optional[Callable[[EndpointQuote], bool]] = None) -> Optional[Decimal]:
        """Max full-call cost across eligible endpoints, rounded up. Mixing rates from different
        endpoints is not a routable price, so the maximum of each endpoint's whole cost is used."""
        predicate = eligible or (lambda endpoint: endpoint.status == 0)
        costs = [endpoint.call_cost(prompt_tokens, completion_tokens, cached_tokens=cached_tokens,
                                    cache_write_tokens=cache_write_tokens,
                                    conservative_tiers=conservative_tiers)
                 for endpoint in self.endpoints if predicate(endpoint)]
        if not costs:
            return None
        return quantize_up(max(costs))

    def worst_input_per_million(self, eligible: Optional[Callable[[EndpointQuote], bool]] = None) -> Decimal:
        predicate = eligible or (lambda endpoint: endpoint.status == 0)
        rates = [endpoint.effective_rates(0)[0] for endpoint in self.endpoints if predicate(endpoint)]
        return max(rates) if rates else ZERO


def parse_endpoints_payload(payload: Any, model: str, *, fetched_at: datetime,
                            source: str = "", ttl_seconds: float = DEFAULT_TTL_SECONDS) -> ModelQuote:
    """Validate an endpoints response. Invalid endpoints are dropped with the rest still usable."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("endpoints"), list):
        raise ValueError("endpoint payload does not contain a data.endpoints list")
    if len(data["endpoints"]) > MAX_ENDPOINTS:
        raise ValueError(f"response exceeds the {MAX_ENDPOINTS}-endpoint metadata limit")
    endpoints: list[EndpointQuote] = []
    for row in data["endpoints"]:
        if not isinstance(row, dict):
            continue
        pricing = row.get("pricing")
        if not isinstance(pricing, dict):
            continue
        override_rows = pricing.get("overrides", [])
        if isinstance(override_rows, list) and len(override_rows) > MAX_OVERRIDES_PER_ENDPOINT:
            raise ValueError(f"pricing.overrides exceeds the {MAX_OVERRIDES_PER_ENDPOINT}-row limit")
        try:
            input_per_million = per_million_from_per_token(_decimal(pricing.get("prompt"), field_name="prompt"))
            output_per_million = per_million_from_per_token(_decimal(pricing.get("completion"), field_name="completion"))
            request_fee = _decimal(pricing.get("request"), field_name="request", allow_none=True) or ZERO
            cache_read = _decimal(pricing.get("input_cache_read"), field_name="input_cache_read", allow_none=True)
            cache_write = _decimal(pricing.get("input_cache_write"), field_name="input_cache_write", allow_none=True)
            cache_read_per_million = (per_million_from_per_token(cache_read) if cache_read is not None else None)
            cache_write_per_million = (per_million_from_per_token(cache_write) if cache_write is not None else None)
            if not isinstance(override_rows, list):
                raise ValueError("pricing.overrides must be a list")
            overrides = tuple(_parse_override(row, input_per_million=input_per_million,
                                              output_per_million=output_per_million,
                                              request_fee=request_fee,
                                              cache_read=cache_read_per_million,
                                              cache_write=cache_write_per_million)
                              for row in override_rows)
        except ValueError:
            continue
        parameters = row.get("supported_parameters")
        supports_tools = ("tools" in parameters) if isinstance(parameters, list) else None
        endpoints.append(EndpointQuote(
            name=str(row.get("name") or row.get("provider_name") or "endpoint")[:120],
            provider_name=str(row.get("provider_name") or "")[:80],
            input_per_million=input_per_million, output_per_million=output_per_million,
            request_fee_usd=request_fee, cache_read_per_million=cache_read_per_million,
            cache_write_per_million=cache_write_per_million,
            context_length=_positive_int(row.get("context_length")),
            max_prompt_tokens=_positive_int(row.get("max_prompt_tokens")),
            max_completion_tokens=_positive_int(row.get("max_completion_tokens")),
            supports_tools=supports_tools, status=_status(row.get("status")),
            identity="|".join(str(row.get(key) or "")[:120] for key in ("tag", "name", "provider_name")),
            overrides=overrides))
    if not endpoints:
        raise ValueError("no endpoint carried a usable price")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False, default=str).encode()).hexdigest()
    return ModelQuote(model=model, endpoints=tuple(endpoints), fetched_at=fetched_at, source=source,
                      snapshot_digest=digest,
                      expires_at=fetched_at + timedelta(seconds=max(0.0, float(ttl_seconds))))


def _parse_override(row: Any, *, input_per_million: Decimal, output_per_million: Decimal,
                    request_fee: Decimal, cache_read: Optional[Decimal],
                    cache_write: Optional[Decimal]) -> PriceOverride:
    if not isinstance(row, dict):
        raise ValueError("pricing override is not an object")
    supported = {"min_prompt_tokens", "max_prompt_tokens", "prompt", "completion", "request",
                 "input_cache_read", "input_cache_write", "input_cache_write_1h"}
    if set(row) - supported:
        raise ValueError("pricing override contains unsupported conditions or price dimensions")
    min_prompt = row.get("min_prompt_tokens", 0)
    max_prompt = row.get("max_prompt_tokens", 0)
    if (isinstance(min_prompt, bool) or not isinstance(min_prompt, int) or min_prompt < 0
            or isinstance(max_prompt, bool) or not isinstance(max_prompt, int) or max_prompt < 0
            or (max_prompt and min_prompt > max_prompt)):
        raise ValueError("pricing override has invalid prompt token thresholds")
    prompt = _decimal(row.get("prompt"), field_name="override.prompt", allow_none=True)
    completion = _decimal(row.get("completion"), field_name="override.completion", allow_none=True)
    fee = _decimal(row.get("request"), field_name="override.request", allow_none=True)
    read = _decimal(row.get("input_cache_read"), field_name="override.input_cache_read", allow_none=True)
    write = _decimal(row.get("input_cache_write"), field_name="override.input_cache_write", allow_none=True)
    write_1h = _decimal(row.get("input_cache_write_1h"), field_name="override.input_cache_write_1h", allow_none=True)
    # OpenRouter's longer cache-write tier is distinct; reserve the higher published rate when both exist.
    writes = [value for value in (write, write_1h) if value is not None]
    return PriceOverride(
        min_prompt_tokens=min_prompt, max_prompt_tokens=max_prompt,
        input_per_million=per_million_from_per_token(prompt) if prompt is not None else input_per_million,
        output_per_million=per_million_from_per_token(completion) if completion is not None else output_per_million,
        request_fee_usd=fee if fee is not None else request_fee,
        cache_read_per_million=per_million_from_per_token(read) if read is not None else cache_read,
        cache_write_per_million=max(per_million_from_per_token(value) for value in writes) if writes
        else cache_write)


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
        self._fetch_slots = threading.BoundedSemaphore(MAX_CONCURRENT_FETCHES)
        self.last_error: str = ""

    # ------------------------------------------------------------------ fetch

    def _http_fetch(self, model: str) -> Any:
        import httpx
        author, slug = split_model_id(model)
        if not author or not slug:
            raise QuoteUnavailable(f"'{model}' is not an OpenRouter model id")
        url = f"{self.base_url}/models/{author}/{slug}/endpoints"
        headers = {"User-Agent": "hutch/0.4 (endpoint pricing; metadata only)", "Accept-Encoding": "identity"}
        try:
            with httpx.stream("GET", url, timeout=HTTP_TIMEOUT_SECONDS, headers=headers) as response:
                if response.status_code >= 400:
                    raise QuoteUnavailable(f"OpenRouter endpoint metadata returned HTTP {response.status_code}")
                encoding = response.headers.get("content-encoding", "identity").strip().lower()
                if encoding not in ("", "identity"):
                    raise QuoteUnavailable("OpenRouter endpoint metadata used unsupported content encoding")
                content_length = response.headers.get("content-length", "")
                if content_length.isdecimal() and int(content_length) > MAX_RESPONSE_BYTES:
                    raise QuoteUnavailable(f"OpenRouter endpoint metadata exceeds the {MAX_RESPONSE_BYTES}-byte limit")
                body = bytearray()
                for chunk in response.iter_raw():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise QuoteUnavailable(f"OpenRouter endpoint metadata exceeds the {MAX_RESPONSE_BYTES}-byte limit")
                    body.extend(chunk)
        except QuoteUnavailable:
            raise
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise QuoteUnavailable("OpenRouter endpoint metadata was not valid bounded JSON") from exc

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
            completed = event.wait(timeout=HTTP_TIMEOUT_SECONDS + 2.0)
            with self._lock:
                if not completed:
                    self.last_error = "timed out waiting for concurrent quote refresh"
                    return None
                return self._cache.get(key)
        if not self._fetch_slots.acquire(timeout=HTTP_TIMEOUT_SECONDS):
            self.last_error = "quote metadata concurrency limit reached"
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache[key] = ModelQuote(model=cached.model, endpoints=cached.endpoints,
                                                  fetched_at=cached.fetched_at, source=cached.source, stale=True,
                                                  snapshot_digest=cached.snapshot_digest,
                                                  expires_at=cached.expires_at)
                self._inflight.pop(key, None)
            event.set()
            with self._lock:
                return self._cache.get(key)
        try:
            try:
                payload = self._fetcher(key)
                quote = parse_endpoints_payload(payload, key, fetched_at=self._clock(),
                                                source=f"{self.base_url}/models/{key}/endpoints",
                                                ttl_seconds=self._ttl)
            except Exception as exc:  # network, HTTP, or schema: no quote, never a guess
                self.last_error = f"{type(exc).__name__}: {exc}"
                with self._lock:
                    cached = self._cache.get(key)
                    if cached is not None:
                        cached = ModelQuote(model=cached.model, endpoints=cached.endpoints,
                                            fetched_at=cached.fetched_at, source=cached.source, stale=True,
                                            snapshot_digest=cached.snapshot_digest,
                                            expires_at=cached.expires_at)
                        self._cache[key] = cached
                    return cached
            with self._lock:
                self._cache[key] = quote
                if len(self._cache) > MAX_CACHE_ENTRIES:
                    oldest = sorted(self._cache, key=lambda item: self._cache[item].fetched_at)
                    for evict in oldest[:len(self._cache) - MAX_CACHE_ENTRIES]:
                        if evict != key:
                            self._cache.pop(evict, None)
            return quote
        finally:
            self._fetch_slots.release()
            with self._lock:
                self._inflight.pop(key, None)
            event.set()

    def cached(self, model: str) -> Optional[ModelQuote]:
        """The last quote already in memory, fresh or stale; never fetches. For listing/pricing displays."""
        now = self._clock()
        with self._lock:
            key = model.strip()
            quote = self._cache.get(key)
            if quote is not None and quote.expires_at is not None and now >= quote.expires_at and not quote.stale:
                quote = ModelQuote(model=quote.model, endpoints=quote.endpoints, fetched_at=quote.fetched_at,
                                   source=quote.source, stale=True, snapshot_digest=quote.snapshot_digest,
                                   expires_at=quote.expires_at)
                self._cache[key] = quote
            return quote

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
