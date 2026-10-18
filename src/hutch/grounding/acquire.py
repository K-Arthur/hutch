"""Bounded live acquisition: pluggable adapters, distinct outcomes, local date validation.

Design rules (mission sections 4-5):

* **Adapters are contracts, not business logic per provider.** Each adapter returns
  ``FoundSource`` rows plus an ``AdapterOutcome`` that names *which* kind of nothing
  happened: ``ok / zero_results / partial / disabled / unavailable / blocked /
  rate_limited / timeout / error``. "Nothing happened" is never a single outcome.
* **A query-aid is not a guarantee.** Search time filters are query aids; every adapter
  validates date bounds locally and counts what it dropped (SearXNG #3358, #3400).
* **One slow provider must not block the rest.** The fan-out uses bounded concurrency,
  per-adapter timeouts, a per-host spacing gate, single retry with jitter and an
  investigation-wide deadline; partial findings ship with a missing-source ledger.
* **Everything from outside is untrusted evidence.** Titles, excerpts, captions and
  metadata are quoted as data; they can never grant permissions or change policy.

Adapters shipped here: GDELT DOC 2.0 (verified live), RSS/Atom feeds (verified live),
Hacker News Algolia (verified live), SearXNG JSON (needs a configured instance), and
Bluesky public search (implemented; the public host is currently blocked from this
network — the adapter says so honestly). Streams live in ``streams.py``.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlencode, urljoin, urlsplit

from ..netguard import NetGuardError, safe_get
from .clock import Clock
from .dedup import DedupItem, domain_of
from .temporal import EvidenceCutoff, TimestampRole, TimestampValue, parse_epoch, parse_gdelt, parse_iso, parse_rfc822
from . import streams as stream_mod

USER_AGENT = "hutch/0.1 (+local agent platform; evidence retrieval)"
GDELT_MIN_INTERVAL = 5.0        # GDELT's documented courtesy limit: one request / 5 s
DEFAULT_FEEDS = (
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://hnrss.org/frontpage",
)

_LANE_ADAPTERS = {
    "news": ("gdelt",),
    "feeds": ("feeds",),
    "discussion": ("hn",),
    "social": ("bluesky",),
    "stream": ("jetstream",),
    "search": ("searxng",),
}
LANES = tuple(_LANE_ADAPTERS)

#: tokens that carry no retrieval value
_STOPWORDS = frozenset(
    "a an and or the of in on at to for from with by is are was were be been this that these those it its as what "
    "when where who whom whose why how did does do has have had will would can could should may might about into over "
    "after before during under again more most some such no not only own same than too very just now latest new news".split())


@dataclass(frozen=True)
class GroundingConfig:
    feeds: tuple[str, ...] = DEFAULT_FEEDS
    searxng_base: str = ""
    searxng_accepts_json: bool = False
    bluesky_base: str = "https://public.api.bsky.app"
    jetstream_host: str = "jetstream.us-west.bsky.network"
    language: str = ""
    max_feed_age_hours: float = 168.0
    #: per-adapter resume cursors supplied by the caller (usually loaded from the store);
    #: never invented here — an absent cursor means "start at the live tip"
    stream_cursors: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir) -> "GroundingConfig":
        path = config_dir / "grounding.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        feeds = data.get("feeds")
        return cls(
            feeds=tuple(str(f) for f in feeds) if isinstance(feeds, list) else DEFAULT_FEEDS,
            searxng_base=str(data.get("searxng_base") or "").rstrip("/"),
            searxng_accepts_json=bool(data.get("searxng_accepts_json", False)),
            bluesky_base=str(data.get("bluesky_base") or "https://public.api.bsky.app").rstrip("/"),
            jetstream_host=str(data.get("jetstream_host") or "jetstream.us-west.bsky.network"),
            language=str(data.get("language") or ""),
            max_feed_age_hours=float(data.get("max_feed_age_hours", 168.0)),
        )


@dataclass
class AcquireBudget:
    """Numeric budgets, agreed before optimization (mission section 14)."""

    max_adapters: int = 6
    max_concurrency: int = 4
    per_adapter_timeout: float = 25.0
    wall_seconds: float = 90.0
    max_results_per_adapter: int = 8
    max_total_sources: int = 40
    max_body_chars: int = 1_500_000
    retry_after_jitter: bool = True


@dataclass
class FoundSource:
    adapter: str
    lane: str
    platform: str
    kind: str                        # article | feed_item | post | story | result
    url: str
    title: str = ""
    excerpt: str = ""
    language: str = ""
    canonical_url: str = ""
    origin: str = ""                 # account handle/DID or domain
    origin_id: str = ""              # platform object id (post uri, story id, article key)
    published: Optional[TimestampValue] = None
    updated: Optional[TimestampValue] = None
    retrieved_at: str = ""
    engagement: dict[str, int] = field(default_factory=dict)
    access_state: str = "ok"          # ok | login_wall | paywalled | partial | unknown
    freshness: str = "polled"         # snapshot | polled | stream
    note: str = ""

    def dedup_item(self) -> DedupItem:
        return DedupItem(key=self.origin_id or self.url, text=f"{self.title} {self.excerpt}".strip(),
                         url=self.canonical_url or self.url, origin=self.origin or domain_of(self.url),
                         origin_id=self.origin_id, labels=())

    def to_json(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter, "lane": self.lane, "platform": self.platform, "kind": self.kind,
            "url": self.url, "canonical_url": self.canonical_url, "title": self.title,
            "excerpt": self.excerpt[:1200], "language": self.language, "origin": self.origin,
            "origin_id": self.origin_id,
            "published": self.published.to_json() if self.published else None,
            "updated": self.updated.to_json() if self.updated else None,
            "retrieved_at": self.retrieved_at, "engagement": self.engagement,
            "access_state": self.access_state, "freshness": self.freshness, "note": self.note,
        }


@dataclass
class AdapterOutcome:
    adapter: str
    lane: str
    query: str
    state: str                        # ok | zero_results | partial | disabled | unavailable | blocked | rate_limited | timeout | error
    detail: str = ""
    http_status: Optional[int] = None
    returned: int = 0
    retained: int = 0
    dropped_out_of_range: int = 0
    dropped_undated: int = 0
    disabled_engines: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    freshness: str = "polled"
    attempts: int = 1
    #: streaming adapters: the resume cursor and liveness report travel with the outcome so
    #: the caller can persist them and a later run resumes instead of restarting blind
    cursor_json: dict = field(default_factory=dict)
    liveness_json: dict = field(default_factory=dict)
    gap_note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AcquireResult:
    sources: list[FoundSource] = field(default_factory=list)
    outcomes: list[AdapterOutcome] = field(default_factory=list)
    truncated: bool = False
    deadline_hit: bool = False

    def missing_ledger(self) -> list[dict[str, Any]]:
        return [o.to_json() for o in self.outcomes if o.state not in ("ok", "zero_results")]


# ------------------------------------------------------------------ helpers

class HostGate:
    """Serialize requests per host with a minimum spacing (GDELT: one per five seconds)."""

    _lock = threading.Lock()
    _last: dict[str, float] = {}

    @classmethod
    def wait(cls, url: str, minimum: float, stop: Callable[[], bool]) -> None:
        if minimum <= 0:
            return
        host = urlsplit(url).netloc.lower()
        while True:
            with cls._lock:
                now = time.monotonic()
                last = cls._last.get(host, 0.0)
                if now - last >= minimum:
                    cls._last[host] = now
                    return
                delay = minimum - (now - last)
            if stop():
                return
            time.sleep(min(delay, 0.5) + random.uniform(0.0, 0.2))


def _query_terms(query: str) -> list[str]:
    terms = [t for t in re.split(r"[^\w']+", (query or "").casefold()) if len(t) >= 2 and t not in _STOPWORDS]
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen[:10]


def _relevance(text: str, terms: Sequence[str]) -> float:
    if not terms:
        return 1.0
    hay = (text or "").casefold()
    hits = sum(1 for term in terms if term in hay)
    return hits / len(terms)


def _fetch(url: str, *, timeout: float, headers: Optional[dict[str, str]] = None, max_bytes: int = 1_500_000):
    merged = {"User-Agent": USER_AGENT, "Accept-Language": "*", **(headers or {})}
    return safe_get(url, timeout=timeout, max_bytes=max_bytes, headers=merged)


def _classify_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, NetGuardError):
        return "blocked", exc.reason
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text:
        return "timeout", str(exc)
    return "error", f"{type(exc).__name__}: {exc}"


def _el_text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


# ------------------------------------------------------------------ adapters

def search_gdelt(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
                 cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "gdelt",
                 lane: str = "news") -> tuple[list[FoundSource], AdapterOutcome]:
    """GDELT DOC 2.0 article list — verified reachable 2026-10-11; ``seendate`` is tagged as
    an index observation, and every returned article is bounds-checked locally."""
    started = time.monotonic()
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="error", freshness="polled")
    params = {
        "query": query, "mode": "artlist", "format": "json",
        "maxrecords": min(budget.max_results_per_adapter, 50), "sort": "datedesc",
        "startdatetime": (cutoff.effective - timedelta(hours=cutoff.horizon_hours or 168)).strftime("%Y%m%d%H%M%S"),
        "enddatetime": cutoff.effective.strftime("%Y%m%d%H%M%S"),
    }
    if cfg.language:
        params["sourcelang"] = cfg.language
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(params)
    try:
        HostGate.wait(url, GDELT_MIN_INTERVAL, stop)
        resp = _fetch(url, timeout=budget.per_adapter_timeout, max_bytes=budget.max_body_chars)
        outcome.http_status = resp.status
        if resp.status == 429:
            outcome.state = "rate_limited"
            outcome.detail = "GDELT rate limit (one request per 5 s); no results were accepted from this call"
            return [], outcome
        if resp.status != 200:
            outcome.state = "unavailable"
            outcome.detail = f"HTTP {resp.status}"
            return [], outcome
        try:
            payload = json.loads(resp.text)
        except ValueError:
            outcome.state = "error"
            outcome.detail = "response was not JSON (a rate-limit or block page may have been served)"
            return [], outcome
        articles = payload.get("articles") or []
        sources: list[FoundSource] = []
        for article in articles:
            if stop():
                outcome.state = "partial"
                outcome.detail = "cancelled during fan-out"
                break
            if not isinstance(article, dict):
                continue
            outcome.returned += 1
            # GDELT seendate records crawler indexing, not publisher publication time.
            seen = parse_gdelt(str(article.get("seendate", "")), role=TimestampRole.index.value, clock=clock)
            if seen and seen.instant and not cutoff.contains(seen):
                outcome.dropped_out_of_range += 1
                continue
            article_url = str(article.get("url") or "")
            sources.append(FoundSource(
                adapter=adapter, lane=lane, platform="web", kind="article", url=article_url,
                canonical_url=article_url, title=str(article.get("title") or ""),
                excerpt="", language=str(article.get("language") or ""),
                origin=str(article.get("domain") or domain_of(article_url)),
                origin_id="", published=seen, retrieved_at=clock.now().isoformat(),
                note="GDELT index listing; open the article to verify its own publication time"))
        outcome.retained = len(sources)
        outcome.state = "ok" if sources else "zero_results"
    except Exception as exc:  # noqa: BLE001 - adapters report, they never crash the fan-out
        outcome.state, outcome.detail = _classify_error(exc)
    finally:
        outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return locals().get("sources", []) or [], outcome


def _parse_feed(xml_text: str) -> list[dict[str, str]]:
    """RSS 2.0 / Atom items with only the fields Hutch uses. Bounded by the fetch size."""
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []

    def text(node, *names, default=""):
        for name in names:
            found = node.find(name) if node is not None else None
            if found is not None and (found.text or found.attrib.get("href")):
                return (found.text or found.attrib.get("href") or "").strip()
        return default

    ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/"}
    for item in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        row = {
            "title": text(item, "title", "{http://www.w3.org/2005/Atom}title"),
            "link": text(item, "link", "{http://www.w3.org/2005/Atom}link"),
            "description": text(item, "description", "summary", "{http://www.w3.org/2005/Atom}summary",
                                "content", "{http://www.w3.org/2005/Atom}content"),
            "guid": text(item, "guid", "id", "{http://www.w3.org/2005/Atom}id"),
            "pub": text(item, "pubDate", "{http://purl.org/dc/elements/1.1/date}",
                        "published", "{http://www.w3.org/2005/Atom}published"),
            "updated": text(item, "updated", "{http://www.w3.org/2005/Atom}updated"),
            "language": text(item, "{http://purl.org/dc/elements/1.1/language}"),
        }
        row["link"] = row["link"] or row["guid"]
        items.append(row)
    return items


def search_feeds(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
                 cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "feeds",
                 lane: str = "feeds",
                 feed_urls: Optional[Sequence[str]] = None) -> tuple[list[FoundSource], AdapterOutcome]:
    """First-party RSS/Atom feeds: the publisher's own declared dates are preserved as
    publication timestamps (RFC 822 ``-0000`` stays marked unknown)."""
    started = time.monotonic()
    feeds = tuple(feed_urls if feed_urls is not None else cfg.feeds)[:6]
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="unavailable",
                             detail="no feeds are configured", freshness="polled")
    if not feeds:
        return [], outcome
    terms = _query_terms(query)
    sources: list[FoundSource] = []
    errors: list[str] = []
    ok_feeds = 0
    newest_age = timedelta(0)
    for feed_url in feeds:
        if stop():
            break
        try:
            resp = _fetch(feed_url, timeout=budget.per_adapter_timeout, max_bytes=budget.max_body_chars)
            outcome.http_status = resp.status
            if resp.status != 200:
                errors.append(f"{domain_of(feed_url)}: HTTP {resp.status}")
                continue
            entries = _parse_feed(resp.text)
            ok_feeds += 1
            scored: list[tuple[float, dict[str, str], TimestampValue | None,
                               TimestampValue | None, TimestampValue | None]] = []
            for entry in entries[:120]:
                raw_pub = entry.get("pub")
                raw_updated = entry.get("updated")
                published = parse_rfc822(raw_pub, role=TimestampRole.publication.value) if raw_pub else None
                if published is None and raw_pub:
                    published = parse_iso(raw_pub, role=TimestampRole.publication.value)
                updated = parse_rfc822(raw_updated, role=TimestampRole.modification.value) if raw_updated else None
                if updated is None and raw_updated:
                    updated = parse_iso(raw_updated, role=TimestampRole.modification.value)
                effective_time = published or updated
                if effective_time and effective_time.instant and not cutoff.contains(effective_time):
                    outcome.dropped_out_of_range += 1
                    continue
                score = _relevance(f"{entry.get('title','')} {entry.get('description','')}", terms)
                if not terms or score > 0:
                    scored.append((score, entry, effective_time, published, updated))
            scored.sort(key=lambda item: (item[0], item[2].instant if item[2] and item[2].instant else ""),
                        reverse=True)
            for score, entry, effective_time, published, updated in scored[:budget.max_results_per_adapter]:
                link = urljoin(feed_url, entry.get("link") or "")
                source = FoundSource(
                    adapter=adapter, lane=lane, platform="web", kind="feed_item", url=link,
                    canonical_url=link, title=entry.get("title", ""), language=entry.get("language", ""),
                    excerpt=_strip_html(entry.get("description", ""))[:800],
                    origin=domain_of(feed_url), origin_id=str(entry.get("guid") or link)[:200],
                    published=published, updated=updated, retrieved_at=clock.now().isoformat(),
                    note=f"feed {domain_of(feed_url)}; score {score:.2f}")
                sources.append(source)
        except ET.ParseError as exc:
            errors.append(f"{domain_of(feed_url)}: unreadable feed ({exc})")
        except Exception as exc:  # noqa: BLE001
            state, detail = _classify_error(exc)
            errors.append(f"{domain_of(feed_url)}: {state} ({detail[:120]})")
    outcome.retained = len(sources)
    if ok_feeds == 0:
        outcome.state = "unavailable"
        outcome.detail = "; ".join(errors[:3]) or "no feed responded"
    elif errors:
        outcome.state = "partial"
        outcome.detail = "; ".join(errors[:3])
    else:
        outcome.state = "ok" if sources else "zero_results"
    outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return sources, outcome


def search_hn(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
              cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "hn",
              lane: str = "discussion") -> tuple[list[FoundSource], AdapterOutcome]:
    """Hacker News (Algolia) story search — public, no account; snapshots, not a stream."""
    started = time.monotonic()
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="error", freshness="snapshot")
    since = int((cutoff.effective - timedelta(hours=cutoff.horizon_hours or 168)).timestamp())
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode({
        "query": query, "tags": "story", "hitsPerPage": min(budget.max_results_per_adapter, 20),
        "numericFilters": f"created_at_i>{since}",
    })
    try:
        resp = _fetch(url, timeout=budget.per_adapter_timeout, max_bytes=budget.max_body_chars)
        outcome.http_status = resp.status
        if resp.status != 200:
            outcome.state = "unavailable"
            outcome.detail = f"HTTP {resp.status}"
            return [], outcome
        payload = json.loads(resp.text)
        hits = payload.get("hits") or []
        sources: list[FoundSource] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            outcome.returned += 1
            created = parse_epoch(hit.get("created_at_i"), unit="seconds", role=TimestampRole.publication.value,
                                  method="hn_created_at", clock=clock)
            if created and created.instant and not cutoff.contains(created):
                outcome.dropped_out_of_range += 1
                continue
            object_id = str(hit.get("objectID") or "")
            target = str(hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}")
            sources.append(FoundSource(
                adapter=adapter, lane=lane, platform="hackernews", kind="story", url=target,
                canonical_url=f"https://news.ycombinator.com/item?id={object_id}",
                title=str(hit.get("title") or ""), origin=str(hit.get("author") or ""), origin_id=object_id,
                published=created, retrieved_at=clock.now().isoformat(),
                engagement={"points": int(hit.get("points") or 0), "comments": int(hit.get("num_comments") or 0)},
                note="HN submission; engagement is a sample of one forum, not popularity at large"))
        outcome.retained = len(sources)
        outcome.state = "ok" if sources else "zero_results"
    except Exception as exc:  # noqa: BLE001
        outcome.state, outcome.detail = _classify_error(exc)
    finally:
        outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return locals().get("sources", []) or [], outcome


_TIME_RANGE = ((24, "day"), (24 * 7, "week"), (24 * 31, "month"), (24 * 366, "year"))


def search_searxng(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
                   cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "searxng",
                   lane: str = "search") -> tuple[list[FoundSource], AdapterOutcome]:
    """SearXNG JSON API against the operator's configured instance.

    Mirrors the two documented failure classes: out-of-range results under a time filter
    (#3358) are dropped locally and counted; losing news engines to a time filter (#3400)
    is surfaced as ``disabled`` rather than "nothing happened". A filterless retry runs
    once and is labelled as such.
    """
    started = time.monotonic()
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="disabled",
                             freshness="polled")
    if not cfg.searxng_base:
        outcome.detail = ("no SearXNG instance is configured; create grounding.json in the Hutch state "
                          "directory with {\"searxng_base\": \"http://127.0.0.1:8080\", \"searxng_accepts_json\": true}")
        return [], outcome
    terms = _query_terms(query)
    horizon = cutoff.horizon_hours or 168
    time_range = next((label for hours, label in _TIME_RANGE if horizon <= hours), None)
    if time_range is None and horizon > 24 * 366:
        time_range = None  # "all time": no filter, no engine loss
    base_params = {"q": query, "format": "json", "pageno": "1", "safesearch": "1"}
    if cfg.language:
        base_params["language"] = cfg.language
    attempts: list[tuple[dict[str, str], bool]] = []
    if time_range:
        attempts.append(({**base_params, "time_range": time_range}, True))
        attempts.append((base_params, False))
    else:
        attempts.append((base_params, False))
    sources: list[FoundSource] = []
    for params, filtered in attempts:
        if stop():
            break
        url = f"{cfg.searxng_base}/search?" + urlencode(params)
        try:
            outcome.attempts = attempts.index((params, filtered)) + 1
            resp = _fetch(url, timeout=budget.per_adapter_timeout, max_bytes=budget.max_body_chars,
                          headers={"Accept": "application/json"})
            outcome.http_status = resp.status
            if resp.status in (401, 403):
                outcome.state = "blocked"
                outcome.detail = f"HTTP {resp.status}: the instance refused an unauthenticated JSON request"
                break
            if resp.status != 200:
                outcome.state = "unavailable"
                outcome.detail = f"HTTP {resp.status}"
                continue
            try:
                payload = json.loads(resp.text)
            except ValueError:
                outcome.state = "unavailable"
                outcome.detail = ("the instance does not serve JSON (enable the json format in its settings "
                                  "or point at another instance)")
                break
            for engine in payload.get("unresponsive_engines") or []:
                name = engine[0] if isinstance(engine, (list, tuple)) and engine else str(engine)
                outcome.disabled_engines.append(str(name))
            results = payload.get("results") or []
            for result in results:
                if not isinstance(result, dict):
                    continue
                outcome.returned += 1
                published_raw = str(result.get("publishedDate") or "")
                published = parse_iso(published_raw, role=TimestampRole.publication.value) if published_raw else None
                if published and published.instant and not cutoff.contains(published):
                    outcome.dropped_out_of_range += 1
                    continue
                if published is None:
                    outcome.dropped_undated += 1
                if filtered and published is None:
                    # a recency filter the instance cannot honor is not silently upgraded
                    continue
                result_url = str(result.get("url") or "")
                notes = []
                if not filtered and time_range:
                    notes.append("filterless retry after the instance disabled engines under a time filter "
                                 "(#3400); dates validated locally")
                if published is None:
                    notes.append("date-unvalidated result retained")
                sources.append(FoundSource(
                    adapter=adapter, lane=lane, platform="web", kind="result", url=result_url,
                    canonical_url=result_url, title=str(result.get("title") or ""),
                    excerpt=_strip_html(str(result.get("content") or ""))[:800],
                    origin=domain_of(result_url), origin_id=str(result.get("id") or result_url)[:200],
                    published=published, retrieved_at=clock.now().isoformat(),
                    language=cfg.language, note="; ".join(notes)))
            if sources:
                outcome.state = "ok" if len(sources) >= outcome.retained else "partial"
                outcome.retained = len(sources)
                if time_range and not filtered:
                    outcome.detail = ("time_range was dropped by the retry; recency is enforced locally from "
                                      "publishedDate")
                break
            if filtered:
                outcome.state = "zero_results"
                outcome.detail = ("no results under time_range; a filterless retry follows "
                                  "(news engines are often disabled by time filters)")
            else:
                outcome.state = "zero_results"
                outcome.retained = 0
        except Exception as exc:  # noqa: BLE001
            outcome.state, outcome.detail = _classify_error(exc)
            continue
    if outcome.retained:
        outcome.state = "ok" if outcome.state != "partial" else "partial"
    outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return sources, outcome


def search_bluesky(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
                   cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "bluesky",
                   lane: str = "social") -> tuple[list[FoundSource], AdapterOutcome]:
    """Bluesky public search (no account). Observed state 2026-10-11: the public host is
    blocked from this network; the outcome says ``blocked`` instead of pretending zero
    results. The endpoint contract follows the documented ``app.bsky.feed.searchPosts``."""
    started = time.monotonic()
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="error", freshness="snapshot")
    params = {"q": query, "limit": str(min(budget.max_results_per_adapter, 25)), "sort": "latest"}
    if cfg.language:
        params["lang"] = cfg.language
    since = cutoff.effective - timedelta(hours=cutoff.horizon_hours or 168)
    params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    params["until"] = cutoff.effective.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{cfg.bluesky_base}/xrpc/app.bsky.feed.searchPosts?" + urlencode(params)
    try:
        resp = _fetch(url, timeout=budget.per_adapter_timeout, max_bytes=budget.max_body_chars,
                      headers={"Accept": "application/json"})
        outcome.http_status = resp.status
        if resp.status in (401, 403):
            outcome.state = "blocked"
            outcome.detail = (f"HTTP {resp.status}: the public AppView refused this network; no social results "
                              "were observed (this is not 'no posts exist')")
            return [], outcome
        if resp.status != 200:
            outcome.state = "unavailable"
            outcome.detail = f"HTTP {resp.status}"
            return [], outcome
        content_type = (resp.headers.get("content-type") or "").lower()
        if "json" not in content_type:
            outcome.state = "blocked"
            outcome.detail = "the host answered with a non-JSON page (CDN block or login wall)"
            return [], outcome
        payload = json.loads(resp.text)
        sources: list[FoundSource] = []
        for post in payload.get("posts") or []:
            if not isinstance(post, dict):
                continue
            outcome.returned += 1
            record = post.get("record") or {}
            created_raw = str(record.get("createdAt") or post.get("indexedAt") or "")
            created = parse_iso(created_raw, role=TimestampRole.upload.value, method="bluesky_createdAt",
                                clock=clock)
            if created and created.instant and not cutoff.contains(created):
                outcome.dropped_out_of_range += 1
                continue
            author = post.get("author") or {}
            uri = str(post.get("uri") or "")
            sources.append(FoundSource(
                adapter=adapter, lane=lane, platform="bluesky", kind="post",
                url=f"https://bsky.app/profile/{author.get('handle','')}/post/{uri.rsplit('/', 1)[-1]}"
                    if author.get("handle") and uri else uri,
                canonical_url=uri, title="", excerpt=str(record.get("text") or "")[:800],
                language=",".join(record.get("langs") or []) if isinstance(record.get("langs"), list) else "",
                origin=str(author.get("handle") or author.get("did") or ""), origin_id=uri,
                published=created, retrieved_at=clock.now().isoformat(),
                engagement={"likes": int(post.get("likeCount") or 0), "reposts": int(post.get("repostCount") or 0),
                            "replies": int(post.get("replyCount") or 0)},
                note="public AppView search sample; engagement numbers are platform-reported"))
        outcome.retained = len(sources)
        outcome.state = "ok" if sources else "zero_results"
    except Exception as exc:  # noqa: BLE001
        outcome.state, outcome.detail = _classify_error(exc)
    finally:
        outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return locals().get("sources", []) or [], outcome


def search_jetstream_stream(query: str, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
                            cfg: GroundingConfig, stop: Callable[[], bool], *, adapter: str = "jetstream",
                            lane: str = "stream",
                            window_seconds: float = 20.0,
                            max_scanned: int = 400) -> tuple[list[FoundSource], AdapterOutcome]:
    """A bounded live window from the Bluesky Jetstream firehose, filtered client-side.

    The server has no keyword search; this observes the live post firehose for a *bounded*
    window, keeps posts whose text matches the query terms, and reports exactly what was
    scanned. A window with no matches is ``zero_results`` with the window stated — never a
    claim that nobody posted. A stored cursor (per investigation) resumes at-least-once;
    ``CursorTooOld`` becomes an explicit gap, not a silent skip.
    """
    started = time.monotonic()
    readiness, detail = stream_mod.jetstream_readiness()
    outcome = AdapterOutcome(adapter=adapter, lane=lane, query=query, state="unsupported",
                             freshness="stream", detail=detail)
    if readiness != "ready":
        return [], outcome
    terms = _query_terms(query)
    window = max(3.0, min(window_seconds, max(5.0, budget.per_adapter_timeout)))
    stored = cfg.stream_cursors.get(adapter) if cfg.stream_cursors else None
    cursor = None
    if isinstance(stored, dict) and stored.get("value") is not None:
        try:
            if str(stored.get("adapter", "")) == "jetstream" and str(stored.get("instance", "")) == cfg.jetstream_host:
                cursor = stream_mod.StreamCursor.from_json(stored)
            elif str(stored.get("adapter", "")) == "jetstream":
                # instance switch: sequence cursors rewind explicitly; timestamps cannot be rewound here
                cursor = stream_mod.StreamCursor.from_json({**stored, "kind": stream_mod.CursorKind.seq.value})
                cursor, note = stream_mod.migrate_jetstream_cursor(cursor, new_instance=cfg.jetstream_host)
                outcome.gap_note = note
        except (ValueError, stream_mod.CursorMismatch):
            cursor = None
            outcome.gap_note = "the stored stream cursor could not be resumed; this window starts at the live tip"
    sources: list[FoundSource] = []

    def post_text(event) -> str:
        record = (event.payload.get("commit") or {}).get("record")
        return str(record.get("text") or "") if isinstance(record, dict) else ""

    def keep(event) -> bool:
        return _relevance(post_text(event), terms) >= 0.5 if terms else False

    def collect(event) -> None:
        if len(sources) >= budget.max_results_per_adapter:
            return
        record = (event.payload.get("commit") or {}).get("record")
        record = record if isinstance(record, dict) else {}
        did = event.did or ""
        rkey = event.rkey or ""
        url = f"https://bsky.app/profile/{did}/post/{rkey}" if did and rkey else ""
        langs = record.get("langs") if isinstance(record.get("langs"), list) else []
        sources.append(FoundSource(
            adapter=adapter, lane=lane, platform="bluesky", kind="post", url=url,
            canonical_url=f"at://{did}/{event.collection}/{rkey}" if did and rkey else "",
            excerpt=post_text(event)[:800], language=",".join(str(x) for x in langs[:3]),
            origin=did, origin_id=f"{did}|{event.collection}|{rkey}".strip("|"),
            published=parse_epoch(event.time_us, unit="microseconds", role=TimestampRole.upload.value,
                                  method="jetstream_time_us", clock=clock) if event.time_us else None,
            retrieved_at=clock.now().isoformat(), freshness="stream",
            note=(f"observed in a bounded live window ({window:.0f}s); not a complete sample of the network "
                  "and not evidence the posting is representative")))

    pump = stream_mod.StreamPump(key_fn=lambda e: e.get("id", ""), clock=clock)
    report = stream_mod.read_jetstream_stream(
        pump=pump, host=cfg.jetstream_host, cursor=cursor, kinds=("commit",),
        collections=("app.bsky.feed.post",), max_events=max_scanned, max_seconds=window,
        filter_fn=keep, sink=collect, stop=stop, clock=clock)
    outcome.liveness_json = report
    state = report.get("state")
    outcome.cursor_json = pump.cursor.to_json() if pump.cursor is not None else {}
    if state == "unsupported":
        outcome.state = "unsupported"
        return [], outcome
    if state == "blocked":
        outcome.state = "blocked"
        outcome.detail = report.get("gap_note") or "the Jetstream instance refused the connection"
        return [], outcome
    if state == "gap":
        outcome.state = "partial"
        outcome.detail = report.get("gap_note") or "stream coverage gap"
    if stop():
        outcome.state = "partial"
        outcome.detail = outcome.detail or "cancelled during the live window"
    outcome.returned = int(report.get("scanned") or 0)          # traffic observed
    outcome.retained = len(sources)
    if outcome.state not in ("partial",):
        outcome.state = "ok" if sources else "zero_results"
    outcome.detail = outcome.detail or report.get("scanned_note", "")
    outcome.latency_ms = round((time.monotonic() - started) * 1000, 1)
    return sources, outcome


ADAPTERS: dict[str, Callable[..., tuple[list[FoundSource], AdapterOutcome]]] = {
    "gdelt": search_gdelt, "feeds": search_feeds, "hn": search_hn,
    "searxng": search_searxng, "bluesky": search_bluesky, "jetstream": search_jetstream_stream,
}


# ------------------------------------------------------------------ fan-out

def run_search(question: str, *, cutoff: EvidenceCutoff, budget: AcquireBudget, clock: Clock,
               cfg: GroundingConfig, lanes: Sequence[str] = ("news", "feeds", "discussion", "social"),
               queries: Optional[Sequence[str]] = None, stop: Optional[Callable[[], bool]] = None,
               adapter_overrides: Optional[dict[str, Callable]] = None) -> AcquireResult:
    """Fan out across the selected lanes with bounded concurrency and a wall deadline.

    ``queries`` may carry disconfirming / original-language formulations; each adapter runs
    up to two of them (the first two distinct) and merges outcomes. One adapter failing is
    one ledger row, never a failed investigation.
    """
    stop = stop or (lambda: False)
    overrides = adapter_overrides or {}
    selected: list[str] = []
    for lane in lanes:
        for name in _LANE_ADAPTERS.get(lane, ()):
            if name not in selected:
                selected.append(name)
    selected = selected[:budget.max_adapters]
    query_list = [q for q in (queries or [question]) if q][:2]
    result = AcquireResult()
    deadline = time.monotonic() + budget.wall_seconds

    def run_one(name: str, query: str, stop_fn: Callable[[], bool]) -> list[tuple[list[FoundSource], AdapterOutcome]]:
        fn = overrides.get(name, ADAPTERS.get(name))
        if fn is None:
            outcome = AdapterOutcome(adapter=name, lane="?", query=query, state="unavailable",
                                     detail="adapter is not registered")
            return [([], outcome)]
        out: list[tuple[list[FoundSource], AdapterOutcome]] = []
        for attempt in range(2):
            try:
                out.append(fn(query, cutoff, budget, clock, cfg, stop_fn))
                break
            except Exception as exc:  # noqa: BLE001 - last-line defense; adapters already report
                if attempt == 1:
                    out.append(([], AdapterOutcome(adapter=name, lane="?", query=query, state="error",
                                                   detail=f"adapter contract failure: {type(exc).__name__}: {exc}")))
                else:
                    time.sleep(random.uniform(0.1, 0.4))
        return out

    jobs = [(name, query) for name in selected for query in query_list]
    deadline_flag = threading.Event()

    def stop_or_deadline() -> bool:
        return stop() or deadline_flag.is_set()

    def absorb(name: str, query: str, pairs: list[tuple[list[FoundSource], AdapterOutcome]]) -> None:
        for sources, outcome in pairs:
            if len(result.sources) + len(sources) > budget.max_total_sources:
                room = max(0, budget.max_total_sources - len(result.sources))
                sources, result.truncated = sources[:room], True
            result.sources.extend(sources)
            result.outcomes.append(outcome)

    pool = ThreadPoolExecutor(max_workers=max(1, min(budget.max_concurrency, len(jobs) or 1)),
                              thread_name_prefix="hutch-grounding")
    try:
        futures = {pool.submit(run_one, name, query, stop_or_deadline): (name, query)
                   for name, query in jobs}
        while futures:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or stop():
                # The wall budget is a hard bound on THIS call: late results are discarded and
                # reported as a ledger entry, never silently merged after the deadline. Adapter
                # threads see stop_or_deadline, so cooperative adapters stop at the next check;
                # an in-flight socket read is still bounded by its own timeout. Results that
                # finished before the deadline check are still harvested.
                result.deadline_hit = not stop()
                deadline_flag.set()
                for future, (name, query) in list(futures.items()):
                    if future.done() and not future.cancelled():
                        try:
                            absorb(name, query, future.result())
                        except Exception as exc:  # pragma: no cover - run_one catches
                            absorb(name, query, [([], AdapterOutcome(
                                adapter=name, lane="?", query=query, state="error",
                                detail=f"{type(exc).__name__}: {exc}"))])
                    else:
                        future.cancel()
                        result.outcomes.append(AdapterOutcome(
                            adapter=name, lane="?", query=query, state="partial",
                            detail=("discarded at the investigation deadline: no result was accepted from this "
                                    "call; the adapter may finish in the background and its output is not used")))
                futures.clear()
                break
            done, _ = wait(list(futures), timeout=min(remaining, 1.0), return_when=FIRST_COMPLETED)
            for future in done:
                name, query = futures.pop(future)
                try:
                    absorb(name, query, future.result())
                except Exception as exc:  # pragma: no cover - run_one catches
                    absorb(name, query, [([], AdapterOutcome(adapter=name, lane="?", query=query, state="error",
                                                             detail=f"{type(exc).__name__}: {exc}"))])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    # stable, newest-first ordering for the reader (unknown dates last)
    result.sources.sort(key=lambda s: (s.published.ordering_key() if s.published else (1, "")), reverse=True)
    return result
