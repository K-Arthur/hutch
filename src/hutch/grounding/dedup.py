"""Deduplication, origin clustering, and explainable noise indicators.

The rule this module implements: **ten thousand copies of one rumor are evidence of
spread, not ten thousand independent witnesses.**

* Exact and near-duplicate grouping is done locally (no model calls): normalized text
  hash first, then a 64-bit SimHash over character shingles, grouped within a bounded
  Hamming distance. This is a convenience sample of a *cluster*, never a truth score.
* Origin clusters separate: the same object seen twice (mirror), one poster's copy on
  another account (repost), a headline syndicated across many domains, and genuinely
  different reporting. Independence is computed from origin structure and text, never
  from popularity or engagement.
* Noise indicators are **reasons with evidence attached**, reversible, and never label a
  person as a bot from writing style, username, language, age or disagreement. Legitimate
  automated feeds are valuable evidence; they are grouped/downranked only when their
  repetition actually inflates counts, and the reason is recorded.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Optional, Sequence

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_RT_RE = re.compile(r"^(?:rt\s+@\w+[: ]+|>\s?)", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

#: a small, documented list of public multi-label suffixes; not a complete PSL.
_MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "co.jp", "ne.jp", "or.jp", "com.au", "net.au",
    "org.au", "co.nz", "com.br", "com.mx", "co.in", "com.sg", "com.hk", "com.tw", "co.kr",
    "co.za", "com.ar", "com.tr", "co.il", "com.cn", "gov.cn",
}


def normalize_text(text: str) -> str:
    """Casefolded, punctuation-stripped, URL-stripped text for comparison only.

    The original text is always preserved elsewhere; this is a comparison key.
    """
    value = unicodedata.normalize("NFKC", text or "")
    value = _RT_RE.sub("", value)
    value = _URL_RE.sub(" ", value)
    value = _NON_WORD_RE.sub(" ", value.casefold())
    return _WS_RE.sub(" ", value).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:32]


def shingles(text: str, k: int = 5, limit: int = 4000) -> list[str]:
    value = normalize_text(text)[:limit]
    if len(value) < k:
        return [value] if value else []
    return [value[i:i + k] for i in range(0, len(value) - k + 1)]


def simhash64(text: str, k: int = 5) -> int:
    """64-bit SimHash over character shingles; 0 means "no content to compare"."""
    counts = [0] * 64
    grams = shingles(text, k=k)
    if not grams:
        return 0
    for gram in grams:
        hashed = int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            counts[bit] += 1 if hashed & (1 << bit) else -1
    out = 0
    for bit in range(64):
        if counts[bit] > 0:
            out |= 1 << bit
    return out


def hamming64(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def near_duplicate(a: str, b: str, *, threshold: float = 0.6) -> bool:
    """Near-duplicate decision for post-length texts.

    Character 5-gram Jaccard similarity, chosen over a SimHash threshold because it is
    stable and explainable at this text size (a handful of changed words must not flip
    eight independent bits). The threshold is a grouping convenience, not a truth claim.
    """
    ga, gb = set(shingles(a)), set(shingles(b))
    return _jaccard(ga, gb) >= threshold


#: near-duplicate threshold (Jaccard over character 5-grams)




@dataclass
class DedupItem:
    """The minimum a caller must provide about one acquired item to cluster it."""

    key: str                       # stable id (source row id or adapter-local key)
    text: str = ""                 # title/body used for comparison
    url: str = ""
    origin: str = ""               # account handle / DID / domain
    origin_id: str = ""            # platform id of the object when known
    published_instant: Optional[str] = None
    labels: tuple[str, ...] = ()   # explicit platform labels only (e.g. automated account)
    extras: dict = field(default_factory=dict)


@dataclass
class DuplicateGroup:
    kind: str                      # "exact" | "near"
    representative: str            # DedupItem.key
    members: list[str]
    note: str = ""


def group_duplicates(items: Sequence[DedupItem], *, threshold: float = 0.6,
                     max_items: int = 400) -> list[DuplicateGroup]:
    """Group exact then near duplicates. Bounded: beyond ``max_items`` the remainder is
    reported as ungrouped rather than silently compared (the caller records that)."""
    exact: dict[str, list[str]] = {}
    by_key: dict[str, DedupItem] = {}
    for item in items[:max_items]:
        by_key[item.key] = item
        exact.setdefault(content_hash(item.text) or f"empty:{item.key}", []).append(item.key)
    groups: list[DuplicateGroup] = []
    ungrouped: list[str] = []
    for digest, keys in exact.items():
        if len(keys) > 1 and not digest.startswith("empty:"):
            groups.append(DuplicateGroup(kind="exact", representative=keys[0], members=list(keys),
                                         note=f"{len(keys)} items with identical normalized text"))
        elif len(keys) == 1 and not digest.startswith("empty:"):
            ungrouped.append(keys[0])
    # near duplicates among exact-group representatives + singletons
    pool: list[DedupItem] = [by_key[key] for key in ungrouped]
    used: set[str] = set()
    for i, item in enumerate(pool):
        if item.key in used:
            continue
        members = [item.key]
        for other in pool[i + 1:]:
            if other.key in used:
                continue
            if near_duplicate(item.text, other.text, threshold=threshold):
                members.append(other.key)
                used.add(other.key)
        used.add(item.key)
        if len(members) > 1:
            groups.append(DuplicateGroup(kind="near", representative=item.key, members=members,
                                         note=f"{len(members)} items at >= {threshold:.0%} 5-gram similarity"))
    if len(items) > max_items:
        groups.append(DuplicateGroup(kind="near", representative="", members=[i.key for i in items[max_items:]],
                                     note=f"not compared: bounded at {max_items} items"))
    return groups


def domain_of(url: str) -> str:
    """Best-effort registrable domain (eTLD+1). Documented limitation: a small suffix
    list, not the Public Suffix List."""
    host = (url or "").split("://", 1)[-1].split("/", 1)[0].split("@")[-1].split(":")[0].strip(".").lower()
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


@dataclass
class ClusterMember:
    key: str
    origin: str = ""
    url: str = ""
    account: str = ""
    note: str = ""


@dataclass
class OriginCluster:
    """One plausible origin of a claim or media item, with its members."""

    cluster_id: str
    kind: str                      # "origin" | "mirror" | "repost" | "syndication" | "shared_headline"
    label: str
    members: list[ClusterMember] = field(default_factory=list)
    distinct_origins: int = 0
    note: str = ""


def origin_clusters(items: Sequence[DedupItem], *, headline_share_min: int = 3,
                    max_items: int = 400) -> list[OriginCluster]:
    """Cluster items into origin groups and report which groups can count as independent.

    Rules, in order:
      1. same platform object id -> ``mirror`` (the same object retrieved twice)
      2. same origin (account/DID) + near-duplicate text -> ``repost``
      3. >= ``headline_share_min`` distinct registrable domains share one normalized
         headline -> ``syndication`` (one origin, N copies) — counted as ONE origin
      4. everything else -> its own ``origin`` cluster
    """
    items = list(items[:max_items])
    order = {item.key: index for index, item in enumerate(items)}
    assigned: dict[str, OriginCluster] = {}
    by_object: dict[str, list[DedupItem]] = {}
    by_origin: dict[str, list[DedupItem]] = {}
    by_headline: dict[str, list[DedupItem]] = {}
    for item in items:
        if item.origin_id:
            by_object.setdefault(f"{item.origin or '?'}|{item.origin_id}", []).append(item)
        if item.origin:
            by_origin.setdefault(item.origin, []).append(item)
        head = content_hash(item.text)
        if head:
            by_headline.setdefault(head, []).append(item)

    def new_cluster(kind: str, label: str, note: str) -> OriginCluster:
        cid = f"cl_{uuid.uuid4().hex[:10]}"
        return OriginCluster(cluster_id=cid, kind=kind, label=label, note=note)

    for object_key, group in sorted(by_object.items(), key=lambda kv: order[kv[1][0].key]):
        if len(group) < 2:
            continue
        cluster = new_cluster("mirror", object_key, f"the same object id was retrieved {len(group)} times")
        for item in group:
            cluster.members.append(ClusterMember(key=item.key, origin=item.origin, url=item.url))
            assigned[item.key] = cluster
        cluster.distinct_origins = 1

    syndicated: dict[str, list[DedupItem]] = {}
    for head, group in by_headline.items():
        domains = {domain_of(item.url) for item in group if item.url}
        if len(domains) >= headline_share_min:
            syndicated[head] = group

    for head, group in sorted(syndicated.items(), key=lambda kv: order[kv[1][0].key]):
        pending = [item for item in group if item.key not in assigned]
        if len(pending) < headline_share_min:
            continue
        cluster = new_cluster("syndication", (pending[0].text or "")[:80],
                              f"one headline appears on {len(pending)} domains; counts as one origin, "
                              "not independent confirmation")
        for item in pending:
            cluster.members.append(ClusterMember(key=item.key, origin=item.origin, url=item.url))
            assigned[item.key] = cluster
        cluster.distinct_origins = 1

    for origin, group in sorted(by_origin.items(), key=lambda kv: order[kv[1][0].key]):
        pending = [item for item in group if item.key not in assigned]
        if len(pending) < 2:
            continue
        merged: set[str] = set()
        for i, item in enumerate(pending):
            if item.key in merged:
                continue
            members = [item]
            for other in pending[i + 1:]:
                if other.key in merged:
                    continue
                if near_duplicate(item.text, other.text):
                    members.append(other)
                    merged.add(other.key)
            if len(members) > 1:
                cluster = new_cluster("repost", origin,
                                      f"{len(members)} near-identical items from one origin")
                for member in members:
                    cluster.members.append(ClusterMember(key=member.key, origin=origin, url=member.url))
                    assigned[member.key] = cluster
                cluster.distinct_origins = 1

    for item in items:
        if item.key in assigned:
            continue
        origin = item.origin or domain_of(item.url) or item.key
        cluster = new_cluster("origin", origin, "distinct origin by account/domain and text")
        cluster.members.append(ClusterMember(key=item.key, origin=item.origin, url=item.url, account=item.origin))
        assigned[item.key] = cluster
        cluster.distinct_origins = 1

    unique: dict[str, OriginCluster] = {}
    for cluster in assigned.values():
        unique[cluster.cluster_id] = cluster
    return sorted(unique.values(), key=lambda c: min(order[m.key] for m in c.members))


def independence_for(items: Sequence[DedupItem], *, same_origin_kinds=("mirror", "repost", "syndication")) -> dict[str, str]:
    """Map each item key to ``independent|same_origin|unknown`` for evidence scoring.

    Items in the same non-origin cluster are ``same_origin``; ``origin`` clusters that
    share a domain with another cluster are still independent (one outlet can publish
    several distinct reports), but the caller must not count the same outlet's copies
    twice — the queen rule stays: distinct origin clusters, not distinct URLs.
    """
    clusters = origin_clusters(items)
    result: dict[str, str] = {}
    for cluster in clusters:
        state = "same_origin" if cluster.kind in same_origin_kinds else "independent"
        for member in cluster.members:
            result[member.key] = state
    return result


@dataclass
class NoiseSignal:
    reason: str
    evidence: str
    action: str = "group"          # "group" | "downrank" — never "block"

    def to_json(self) -> dict[str, str]:
        return {"reason": self.reason, "evidence": self.evidence, "action": self.action}


def noise_signals(items: Sequence[DedupItem], *, metadata: Optional[dict[str, dict]] = None,
                  burst_seconds: int = 60, burst_ratio: float = 0.8) -> dict[str, list[NoiseSignal]]:
    """Explainable, reversible indicators keyed by item key.

    Allowed signals: exact/near duplication (grouped), link-only posts, explicit
    platform-declared automated labels, and synchronized bursts of identical text.
    Not allowed, and deliberately absent: writing-style/username/language/account-age
    "bot scores" and any per-person verdict.
    """
    metadata = metadata or {}
    signals: dict[str, list[NoiseSignal]] = {}
    groups = group_duplicates(items)
    by_key = {item.key: item for item in items}
    group_of: dict[str, DuplicateGroup] = {}
    for group in groups:
        for key in group.members:
            group_of[key] = group
    for item in items:
        found: list[NoiseSignal] = []
        group = group_of.get(item.key)
        if group and group.representative and item.key != group.representative:
            found.append(NoiseSignal("duplicate_text",
                                     f"same/near text as {group.representative} ({group.note})", "group"))
        meta = metadata.get(item.key, {})
        explicit = tuple(item.labels) + tuple(meta.get("platform_labels", ()))
        for label in explicit:
            found.append(NoiseSignal("declared_automation",
                                     f"platform metadata labels this account as {label!r}", "downrank"))
        if _URL_RE.fullmatch((item.text or "").strip() or "x"):
            found.append(NoiseSignal("link_only", "the post body is only a URL", "downrank"))
        if found:
            signals[item.key] = found
    # bursts: many near-identical posts inside a short window
    buckets: dict[str, list[DedupItem]] = {}
    for item in items:
        if not item.published_instant:
            continue
        hour = item.published_instant[:13]
        buckets.setdefault(f"{hour}|{content_hash(item.text)}", []).append(item)
    for bucket, group_items in buckets.items():
        if len(group_items) < 5:
            continue
        stamps = sorted(i.published_instant for i in group_items if i.published_instant)
        spread = 0
        try:
            from datetime import datetime
            if len(stamps) >= 2:
                t0 = datetime.fromisoformat(stamps[0])
                t1 = datetime.fromisoformat(stamps[-1])
                spread = (t1 - t0).total_seconds()
        except ValueError:
            spread = burst_seconds + 1
        if spread <= burst_seconds:
            for item in group_items:
                signals.setdefault(item.key, []).append(NoiseSignal(
                    "synchronized_burst",
                    f"{len(group_items)} identical posts within {spread:.0f}s of one another", "group"))
    return signals


def filter_sensitivity_summary(items: Sequence[DedupItem]) -> dict:
    """Denominators for an honest 'observed sample' panel: raw, unique, clustered origins,
    and the largest cluster's share."""
    groups = origin_clusters(items)
    largest = max((len(c.members) for c in groups), default=0)
    return {
        "raw_items": len(items),
        "unique_items": len({i.key for i in items}),
        "origin_clusters": len(groups),
        "distinct_origins": len(groups),
        "largest_cluster_items": largest,
        "note": ("origin clusters group mirrors/reposts/syndication; counting URLs as "
                 "separate voices would overstate independent reporting"),
    }
