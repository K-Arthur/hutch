"""Web fetch tool — read-only HTTP GET with SSRF guards.

Only public http(s) targets: the name is resolved, every address must be public, redirects are
followed by us and re-checked, and the connection is pinned to the validated address (see
``hutch.netguard``). Response bodies are clipped hard so a hostile page cannot eat the context
window (the "MCP tools dump huge JSON" failure).
"""

from __future__ import annotations

import re
from typing import Any

from ..netguard import NetGuardError, safe_get
from .base import Tool, ToolContext, ToolResult, _schema, clip

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
            resp = safe_get(url, timeout=20, headers={"User-Agent": "hutch/0.1 (+local agent platform)"})
        except NetGuardError as exc:
            return ToolResult(ok=False, output=f"error: {exc.reason}")
        except Exception as exc:                      # network errors, timeouts, TLS failures
            return ToolResult(ok=False, output=f"error fetching {url}: {exc}")
        body = resp.text
        if "html" in resp.headers.get("content-type", "").lower():
            body = html_to_text(body)
        status = f"HTTP {resp.status} {resp.reason}"
        note = "\n[response clipped at the size limit]" if resp.truncated else ""
        return ToolResult(
            ok=resp.ok,
            output=clip(f"{status}\n{resp.url}\n\n{body.strip()}{note}"),
            data={"url": resp.url, "status": resp.status, "redirects": len(resp.redirects)},
        )
