"""Web fetch tool — read-only HTTP GET with SSRF guards.

Only public http(s) targets (no localhost/private/metadata ranges, no other
schemes); response bodies are clipped hard so a hostile page cannot eat the
context window (the "MCP tools dump huge JSON" failure).
"""

from __future__ import annotations

import re
from typing import Any

from .base import Tool, ToolContext, ToolResult, _schema, clip

class _LazyHttpx:
    """`httpx` costs ~50 ms to import; only fetching a URL needs it (PF-6). Attribute access
    (and test monkeypatching of ``httpx.get``) behaves like the real module."""

    def __getattr__(self, name: str):
        import httpx as _httpx
        return getattr(_httpx, name)


httpx = _LazyHttpx()

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    html = _TAG_RE.sub(" ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (
        html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'")
    )
    return _WS_RE.sub("\n\n", html)


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a public http(s) URL and return readable text (HTML tags stripped, truncated)."
    parameters = _schema(["url"], {"url": {"type": "string", "description": "Absolute http(s) URL"}})

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = (args.get("url") or "").strip()
        decision = ctx.policy.check_url(url)
        if decision.verdict.value == "deny":
            return ToolResult(ok=False, output=f"error: {decision.reason}")
        try:
            resp = httpx.get(
                url,
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": "hutch/0.1 (+local agent platform)"},
            )
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, output=f"error fetching {url}: {exc}")
        body = resp.text
        if "html" in resp.headers.get("content-type", "").lower():
            body = html_to_text(body)
        status = f"HTTP {resp.status_code} {resp.reason_phrase}"
        return ToolResult(
            ok=resp.is_success,
            output=clip(f"{status}\n{url}\n\n{body.strip()}"),
            data={"url": url, "status": resp.status_code},
        )
