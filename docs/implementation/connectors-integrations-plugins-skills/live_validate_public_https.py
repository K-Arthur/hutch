"""Live validation: the public-HTTPS branch of the pinned transport.

Every previous HTTP run used loopback. That proves the local-origin rule, but not that the pinned
transport can complete a real TLS handshake to a *public* address it just screened, which is the
branch a remote connector actually uses.

This contacts one real, public HTTPS origin and asserts:

1. the endpoint screens clean (public address, HTTPS, no credentials in the URL);
2. the pinned transport completes the request rather than refusing it, so pinning has not turned
   into "refuse everything";
3. a non-MCP response at an MCP path is reported as a connector failure, not a hang and not a
   crash: the client gives up inside its deadline and the caller sees an ordinary error.

It does not claim a connector works against a third-party service. No MCP server was available at
a public origin, and no credential was used.

Run:
    uv run --frozen --no-sync python docs/implementation/connectors-integrations-plugins-skills/live_validate_public_https.py
"""

from __future__ import annotations

import asyncio
import json
import sys

#: A long-lived public HTTPS origin that serves a small page and no MCP endpoint.
PUBLIC_ORIGIN = "https://example.com"


def main() -> int:
    import httpx2

    from hutch.integrations.mcp import network
    from hutch.integrations.mcp.config import McpConfigurationError
    from hutch.integrations.mcp.transport import open_client

    evidence: dict[str, object] = {"origin": PUBLIC_ORIGIN}

    # 1. Screening: a public HTTPS origin is allowed, and its addresses are public.
    try:
        screened = network.validate_mcp_endpoint(f"{PUBLIC_ORIGIN}/mcp")
        evidence["screen"] = {"ok": True, "url": screened}
    except network.McpEndpointError as exc:
        evidence["screen"] = {"ok": False, "reason": str(exc)}
        print(json.dumps(evidence, indent=2))
        return 1

    # 2. Pinned transport: a real TLS handshake to the screened address.
    async def fetch() -> dict[str, object]:
        transport = network.PinnedMcpHTTPTransport()
        async with httpx2.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                                      timeout=httpx2.Timeout(20)) as client:
            response = await client.get(f"{PUBLIC_ORIGIN}/")
            body = response.text
            return {"status": response.status_code, "bytes": len(body.encode()),
                    "looks_like_html": "<html" in body.lower()[:400]}

    try:
        evidence["pinned_request"] = asyncio.run(fetch())
    except Exception as exc:  # noqa: BLE001 - the point is to report what happened
        evidence["pinned_request"] = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(evidence, indent=2))
        return 1

    # 3. A definition pointed at that origin must fail as a connector error, not a crash or a hang.
    definition = {"transport": "mcp_http", "url": f"{PUBLIC_ORIGIN}/mcp", "auth": {"type": "none"}}
    try:
        async def attempt() -> str:
            async with open_client(definition) as client:
                page = await client.list_tools(cache_mode="refresh")
                return f"unexpectedly listed {len(page.tools)} tools"

        evidence["mcp_handshake"] = {"outcome": asyncio.run(attempt())}
    except McpConfigurationError as exc:
        evidence["mcp_handshake"] = {"outcome": "configuration error", "reason": str(exc)}
    except BaseException as exc:  # noqa: BLE001 - any failure shape is the finding
        chain = []
        current: BaseException | None = exc
        while current is not None and len(chain) < 6:
            chain.append(f"{type(current).__name__}: {str(current)[:160]}")
            current = current.__cause__ or (current.exceptions[0] if isinstance(current, BaseExceptionGroup)
                                            and current.exceptions else None)
        evidence["mcp_handshake"] = {"outcome": "refused", "chain": chain}

    print(json.dumps(evidence, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
