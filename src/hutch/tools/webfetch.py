"""Web fetch tool: read-only HTTP GET with SSRF guards and evidence metadata.

Beyond the original behavior (public http(s) targets only, pinned validated addresses,
redirect re-checks, hard size clips) this preserves what the grounding layer needs from a
single page: the final URL, a canonical URL, source-declared publication/modification
times with their raw text and method, site identity, and a bounded evidence passage. Every
fetch is recorded as a source item in the run's investigation, so a later answer can cite
the exact retrieval and a correction can be traced to it.

Dates found here are *claims of the page*, not proof of when an event occurred: they are
parsed with their role (publication/modification) and never promoted to occurrence time.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from ..grounding.clock import SYSTEM_CLOCK
from ..grounding.temporal import TimestampRole, TimestampValue, parse_iso
from ..ingest import DEFAULT_SCAN_CHARS, annotation, assess, strip_html_comments
from ..netguard import NetGuardError, safe_get
from .base import Tool, ToolContext, ToolResult, _schema, clip

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\n{3,}")

_CANONICAL_RE = re.compile(r"<link[^>]+rel=[\"']canonical[\"'][^>]*>", re.IGNORECASE)
_HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)
_META_RE = re.compile(r"<meta\s+[^>]*>", re.IGNORECASE)
_LD_RE = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
                    re.DOTALL | re.IGNORECASE)


def html_to_text(html: str) -> str:
    html = _TAG_RE.sub(" ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (
        html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'")
    )
    return _WS_RE.sub("\n\n", html)


def _meta_pairs(html: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for tag in _META_RE.findall(html)[:200]:
        def attr(name: str) -> str:
            m = re.search(rf"{name}=[\"']([^\"']*)[\"']", tag, re.IGNORECASE)
            return m.group(1).strip() if m else ""
        key = attr("property") or attr("name") or attr("itemprop")
        content = attr("content")
        if key and content and len(content) <= 500:
            pairs.setdefault(key.casefold(), content)
    return pairs


def extract_metadata(html: str, *, url: str, headers: dict[str, str],
                     reference: Optional[datetime] = None) -> dict[str, Any]:
    """Bounded, best-effort metadata: canonical URL, site, declared dates and a title."""
    meta = _meta_pairs(html)
    out: dict[str, Any] = {"canonical_url": "", "site_name": meta.get("og:site_name", ""),
                           "title": meta.get("og:title", ""), "dates": []}
    canonical = _CANONICAL_RE.search(html)
    if canonical:
        href = _HREF_RE.search(canonical.group(0))
        if href:
            out["canonical_url"] = urljoin(url, href.group(1))

    def add_date(key: str, role: str, method: str) -> None:
        raw = meta.get(key)
        if not raw:
            return
        value = parse_iso(raw, role=role, method=method)
        if value is not None:
            out["dates"].append(value)

    add_date("article:published_time", TimestampRole.publication.value, "meta_article_published")
    add_date("article:modified_time", TimestampRole.modification.value, "meta_article_modified")
    add_date("datepublished", TimestampRole.publication.value, "meta_datePublished")
    add_date("datemodified", TimestampRole.modification.value, "meta_dateModified")
    # JSON-LD (bounded): look at the first four blocks only
    for block in _LD_RE.findall(html)[:4]:
        try:
            payload = json.loads(block.strip()[:20000])
        except ValueError:
            continue
        for node in payload if isinstance(payload, list) else [payload]:
            if not isinstance(node, dict):
                continue
            for key, role, method in (("datePublished", TimestampRole.publication.value, "jsonld_datePublished"),
                                      ("dateModified", TimestampRole.modification.value, "jsonld_dateModified")):
                raw = node.get(key)
                if isinstance(raw, str):
                    value = parse_iso(raw, role=role, method=method)
                    if value is not None:
                        out["dates"].append(value)
            if not out["title"] and isinstance(node.get("headline"), str):
                out["title"] = node["headline"][:300]
    last_modified = headers.get("last-modified")
    if last_modified:
        from email.utils import parsedate_to_datetime
        try:
            parsed = parsedate_to_datetime(last_modified)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=None)
            value = parse_iso(parsed.isoformat(), role=TimestampRole.modification.value,
                              method="http_last_modified")
            if value is not None:
                out["dates"].append(value)
        except (TypeError, ValueError):
            pass
    # newest declared modification/publication wins for the headline row, unless none parsed
    out["dates"] = [d for d in out["dates"] if d is not None]
    return out


class WebFetchTool(Tool):
    name = "web_fetch"
    description = ("Fetch a public http(s) URL and return readable text (HTML tags stripped, truncated) plus "
                   "source metadata: final/canonical URL, source-declared publication/modification times with "
                   "their method, and a recorded evidence snapshot row.")
    parameters = _schema(["url"], {"url": {"type": "string", "description": "Absolute http(s) URL"}})

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = (args.get("url") or "").strip()
        decision = ctx.policy.check_url(url)
        if decision.verdict.value == "deny":
            return ToolResult(ok=False, output=f"error: {decision.reason}")
        try:
            resp = safe_get(url, timeout=20, headers={"User-Agent": "hutch/0.1 (+local agent platform)"})
        except NetGuardError as exc:
            return ToolResult(ok=False, output=f"error: {exc.reason}")
        except Exception as exc:                      # network errors, timeouts, TLS failures
            return ToolResult(ok=False, output=f"error fetching {url}: {exc}")
        body = resp.text
        html = "html" in resp.headers.get("content-type", "").lower()
        comments_removed = 0
        hidden_comment_text = ""
        comments_truncated = False
        if html:
            cleaned, hidden_comment_text, comments_removed, comments_truncated = strip_html_comments(resp.text)
            body = html_to_text(cleaned)
        status = f"HTTP {resp.status} {resp.reason}"
        note = "\n[response clipped at the size limit]" if resp.truncated else ""
        clock = getattr(ctx, "clock", None) or SYSTEM_CLOCK
        metadata: dict[str, Any] = {}
        if html:
            try:
                metadata = extract_metadata(resp.text, url=resp.url, headers=resp.headers)
            except Exception as exc:  # metadata is a convenience; a parse bug must not fail the read
                metadata = {"error": f"metadata extraction failed: {type(exc).__name__}: {exc}"}
        header_lines = [status, resp.url]
        if metadata.get("canonical_url"):
            header_lines.append(f"canonical: {metadata['canonical_url']}")
        if metadata.get("site_name"):
            header_lines.append(f"site: {metadata['site_name']}")
        for value in metadata.get("dates", []):
            header_lines.append(f"{value.role}: {value.instant or value.raw} (method {value.method}, "
                                f"precision {value.precision}{', uncertain' if value.uncertain else ''})")
        if html and not metadata.get("dates"):
            header_lines.append("source-declared dates: none found (absence is not evidence about the event time)")
        # Untrusted-content scan: flag and disclose; never rewrite the payload.
        findings = assess(body)
        if hidden_comment_text:
            findings = sorted(findings + assess(hidden_comment_text, source="html-comment"),
                              key=lambda f: (f.start, f.rule))
        scan_note = annotation(findings,
                               assessed_chars=min(len(body), DEFAULT_SCAN_CHARS),
                               total_chars=len(body), comments_removed=comments_removed,
                               comments_truncated=comments_truncated)
        excerpt = body.strip()[:600]
        text = f"{chr(10).join(header_lines)}\n\n{scan_note + chr(10) + chr(10) if scan_note else ''}{excerpt}{note}"
        security = {"findings": [f.to_json() for f in findings], "comments_removed": comments_removed,
                    "comments_truncated": comments_truncated,
                    "assessed_chars": min(len(body), DEFAULT_SCAN_CHARS), "total_chars": len(body)}
        try:
            self._record_source(ctx, resp, metadata, excerpt, clock)
        except Exception as exc:  # evidence bookkeeping must never fail the read itself
            text += f"\n[evidence snapshot was not recorded: {type(exc).__name__}: {exc}]"
        return ToolResult(
            ok=resp.ok,
            output=clip(text),
            data={"url": resp.url, "status": resp.status, "redirects": len(resp.redirects),
                  "canonical_url": metadata.get("canonical_url", ""),
                  "dates": [v.to_json() for v in metadata.get("dates", [])],
                  "security": security,
                  "evidence": {"recorded": bool(metadata)}},
        )

    @staticmethod
    def _record_source(ctx: ToolContext, resp, metadata: dict[str, Any], excerpt: str, clock) -> None:
        investigation = ctx.store.investigation_for_run(ctx.run.id) or ctx.store.create_investigation(
            run_id=ctx.run.id, conversation_id=ctx.run.conversation_id or "", bot_id=ctx.bot.id,
            question=str(getattr(ctx.run, "prompt", "") or "")[:500] or "web fetch",
            reference_instant=clock.now().isoformat(), user_timezone="UTC", question_kind="fetch")
        published: Optional[TimestampValue] = None
        updated: Optional[TimestampValue] = None
        for value in metadata.get("dates", []):
            if value.role == TimestampRole.publication.value and published is None:
                published = value
            elif value.role == TimestampRole.modification.value and updated is None:
                updated = value
        ctx.store.record_sources(investigation["id"], [{
            "adapter": "web_fetch", "lane": "fetch", "platform": "web", "kind": "page",
            "url": resp.url, "canonical_url": metadata.get("canonical_url") or resp.url,
            "origin": metadata.get("site_name", ""), "origin_id": metadata.get("canonical_url") or resp.url,
            "title": metadata.get("title", ""), "excerpt": excerpt,
            "published": published.to_json() if published else None,
            "updated": updated.to_json() if updated else None,
            "retrieved_at": clock.now().isoformat(),
            "note": "directly fetched page; declared dates are the source's claims",
        }])
