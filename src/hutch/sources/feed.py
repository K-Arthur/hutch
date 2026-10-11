"""RSS 2.0 / Atom source: conditional GET with bounded, validator-first polling.

Transport choice is explicit, not assumed:

* If the server supports ``ETag``/``Last-Modified``, an unchanged feed costs one
  HTTP 304 and zero parsing.
* Providers may drop, delay, or rate-limit deliveries, so this adapter always
  reconciles from the feed's authoritative item list rather than trusting any
  push signal. Item revisions (same id, changed content) are separate events
  from new items.
* Parsing is bounded: a hard byte ceiling, a doctype/entity-expansion refusal
  (XML entity bombs), and namespace-agnostic element matching for RSS/Atom.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from . import CheckOutcome, EventDraft, SourceRuntime, SourceUnavailable

MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 50
MAX_SEEN_IDS = 500


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element:
        if _local(child.tag) in names:
            if child.text:
                return child.text.strip()
            href = child.get("href")
            if href:
                return href.strip()
    return ""


def _parse_when(raw: str, now: datetime) -> str:
    raw = (raw or "").strip()
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (TypeError, ValueError):
            pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except ValueError:
            pass
    return _iso(now.timestamp())


def _items(root: ET.Element) -> list[ET.Element]:
    entries = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    return entries


def parse_feed(text: str, *, now: datetime, max_items: int) -> tuple[list[dict], bool]:
    """Return (items, truncated). Raises SourceUnavailable on malformed or hostile XML."""
    head = text[:4096].lower()
    if "<!doctype" in head or "<!entity" in head:
        raise SourceUnavailable("the feed contains a doctype/entity declaration and was refused")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceUnavailable(f"the feed is not valid XML: {exc}") from exc
    entries = _items(root)
    truncated = len(entries) > max_items
    out: list[dict] = []
    for element in entries[:max_items]:
        title = _child_text(element, ("title",))
        link = _child_text(element, ("link",))
        guid = _child_text(element, ("guid", "id")) or link or hashlib.sha256(
            f"{_child_text(element, ('title',))}|{_child_text(element, ('pubdate', 'published', 'updated'))}".encode()).hexdigest()[:24]
        published = _child_text(element, ("pubdate", "published", "updated", "date"))
        body = _child_text(element, ("description", "summary", "content", "encoded"))
        digest = hashlib.sha256("\x1f".join((title, link, published, body)).encode("utf-8", "replace")).hexdigest()
        out.append({"id": guid[:300], "title": " ".join(title.split())[:200] or "(untitled)",
                    "hash": digest, "occurrence": _parse_when(published, now)})
    return out, truncated


def _default_fetch(url: str, headers: dict[str, str], timeout: float, runtime: SourceRuntime) -> Any:
    from ..netguard import safe_get

    return safe_get(url, timeout=timeout, headers=headers, resolver=runtime.resolver,
                    max_bytes=MAX_BYTES)


def check(config: dict, cursor: dict, *, runtime: SourceRuntime, now: datetime) -> CheckOutcome:
    url = str(config.get("url") or "").strip()
    if not url:
        raise SourceUnavailable("the feed URL is required")
    fetch = runtime.fetch or _default_fetch
    headers: dict[str, str] = {"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    if cursor.get("etag"):
        headers["If-None-Match"] = str(cursor["etag"])
    if cursor.get("last_modified"):
        headers["If-Modified-Since"] = str(cursor["last_modified"])
    timeout = max(5.0, min(float(runtime.timeout), 60.0))
    try:
        response = fetch(url, headers, timeout, runtime)
    except SourceUnavailable:
        raise
    except Exception as exc:  # network layers raise many exception types; one honest error
        raise SourceUnavailable(f"the feed could not be fetched: {' '.join(str(exc).split())[:200]}") from exc

    status = int(getattr(response, "status", 0) or 0)
    response_headers = {str(k).lower(): str(v) for k, v in (getattr(response, "headers", {}) or {}).items()}
    if status == 304:
        new_cursor = dict(cursor)
        new_cursor["etag"] = response_headers.get("etag", cursor.get("etag", ""))
        new_cursor["last_modified"] = response_headers.get("last-modified", cursor.get("last_modified", ""))
        return CheckOutcome(cursor=new_cursor, events=(), summary="no change (304)")
    if status == 429 or status >= 500:
        retry_after = None
        raw_retry = response_headers.get("retry-after", "")
        try:
            retry_after = float(raw_retry)
        except (TypeError, ValueError):
            pass
        raise SourceUnavailable(f"the feed answered HTTP {status}", retry_after=retry_after)
    if not 200 <= status < 300:
        raise SourceUnavailable(f"the feed answered HTTP {status}")
    body = getattr(response, "text", "") or ""
    if getattr(response, "truncated", False):
        raise SourceUnavailable("the feed exceeded the 2 MB read limit and was refused")
    items, truncated = parse_feed(body, now=now, max_items=min(MAX_ITEMS, max(1, runtime.max_events)))

    seen: dict = dict(cursor.get("items") or {})
    events: list[EventDraft] = []
    budget = max(1, runtime.max_events)
    for item in items:
        previous = seen.get(item["id"])
        if previous is None:
            if len(events) < budget:
                events.append(EventDraft(key=item["id"], kind="new_items", occurrence=item["occurrence"],
                                         content_hash=item["hash"], summary=f"new item: {item['title']}").normalized())
        elif previous.get("hash") != item["hash"]:
            if len(events) < budget:
                events.append(EventDraft(key=item["id"], kind="revised", occurrence=item["occurrence"],
                                         content_hash=item["hash"],
                                         summary=f"item changed: {item['title']}").normalized())
        seen[item["id"]] = {"hash": item["hash"], "occurrence": item["occurrence"]}
    if len(seen) > MAX_SEEN_IDS:
        for key in list(seen)[: len(seen) - MAX_SEEN_IDS]:
            seen.pop(key, None)
    new_cursor = {"etag": response_headers.get("etag", ""), "last_modified": response_headers.get("last-modified", ""),
                  "items": seen}
    material = len(events)
    return CheckOutcome(cursor=new_cursor, events=tuple(events),
                        summary="no change" if not material else f"{material} feed item(s) changed",
                        truncated=truncated)
