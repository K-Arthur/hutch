"""Bounded, authenticated Notion MCP reads through the pinned official SDK.

No sampling, roots, elicitation, remote URLs, third-party connector search or
writes are exposed. Server instructions and annotations never become authority.
"""
from __future__ import annotations

import hashlib
import json
import time

import anyio
import httpx
from mcp import Client
from mcp.types import Implementation
from mcp.client.streamable_http import streamable_http_client

from .notion import NotionBook, NotionError, ORIGIN
from ..toolcalling.validate import analyze_schema, validate_call

READ_TOOLS = frozenset({"notion-search", "notion-fetch"})
MAX_BYTES = 1_048_576
MAX_TOOLS = 100
DEADLINE_SECONDS = 30


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def revision(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        total, started = 0, time.monotonic()
        async for chunk in self.stream:
            total += len(chunk)
            if total > MAX_BYTES or time.monotonic() - started > DEADLINE_SECONDS:
                raise NotionError("Notion MCP response exceeded its byte or time limit")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class _FixedTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport=None):
        self.transport = transport or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        if str(request.url) != ORIGIN + "/mcp" or request.method not in {"POST", "GET", "DELETE"}:
            raise NotionError("Notion MCP attempted an unexpected destination")
        request.headers["Accept-Encoding"] = "identity"
        response = await self.transport.handle_async_request(request)
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise NotionError("Notion MCP returned unsupported compressed data")
        response.stream = _BoundedStream(response.stream)
        return response

    async def aclose(self):
        await self.transport.aclose()


class NotionMCP:
    def __init__(self, book: NotionBook, account_id: str, *, transport=None):
        self.book, self.account_id, self.transport = book, account_id, transport

    @staticmethod
    def _catalog(tools) -> dict:
        if len(tools) > MAX_TOOLS:
            raise NotionError("Notion returned too many tools")
        catalog = {}
        for tool in tools:
            if tool.name not in READ_TOOLS:
                continue
            schema = tool.input_schema
            if not isinstance(schema, dict) or schema.get("type") != "object":
                continue
            report = analyze_schema(schema)
            if not report.certifiable:
                continue
            item = {"name": tool.name, "description": str(tool.description or "")[:8000], "parameters": schema}
            if len(canonical_json(item).encode()) > 64_000:
                raise NotionError("Notion returned an oversized tool definition")
            if tool.name in catalog:
                raise NotionError("Notion returned duplicate tool identities")
            catalog[tool.name] = item
        return catalog

    async def _run(self, name=None, args=None, expected_revision="", *, before_call=None):
        token = self.book.access_token(self.account_id)
        async with httpx.AsyncClient(transport=_FixedTransport(self.transport), trust_env=False,
                follow_redirects=False, timeout=10, headers={"Authorization": "Bearer " + token}) as http:
            with anyio.fail_after(DEADLINE_SECONDS):
                async with Client(streamable_http_client(ORIGIN + "/mcp", http_client=http,
                        max_sse_event_size=MAX_BYTES), read_timeout_seconds=10,
                        input_required_max_rounds=0, cache=None,
                        client_info=Implementation(name="hutch", version="0.1.0")) as client:
                    # The SDK probes modern discovery and handles the documented
                    # legacy handshake. No server instructions are incorporated.
                    tools = []
                    cursor = None
                    for _ in range(10):
                        page = await client.list_tools(cursor=cursor, cache_mode="refresh")
                        tools.extend(page.tools)
                        if len(tools) > MAX_TOOLS:
                            raise NotionError("Notion returned too many tools")
                        cursor = page.next_cursor
                        if not cursor:
                            break
                    else:
                        raise NotionError("Notion tool discovery exceeded its page limit")
                    catalog = self._catalog(tools)
                    if token in canonical_json(catalog):
                        raise NotionError("Notion returned credential data in its tool catalog; nothing was saved")
                    if name is None:
                        return {"tools": catalog, "revision": revision(catalog), "protocol": client.protocol_version}
                    item = catalog.get(name)
                    if item is None or revision(item) != expected_revision:
                        raise NotionError("Notion's tool definition changed; review assistant access again before using it")
                    problems = validate_call(item["parameters"], args)
                    if problems:
                        raise NotionError("Notion arguments do not match the reviewed tool schema")
                    if before_call:
                        before_call()
                    result = await client.call_tool(name, args, read_timeout_seconds=10)
                    if getattr(result, "result_type", "complete") != "complete":
                        raise NotionError("Notion requested unsupported follow-up input; no extra authority was granted")
                    text = "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")
                    if token in text:
                        raise NotionError("Notion returned credential data; the read result was withheld")
                    if not text and result.structured_content is not None:
                        text = canonical_json(result.structured_content)
                    if not text:
                        raise NotionError("Notion returned no readable text")
                    if token in text:
                        raise NotionError("Notion returned credential data; the read result was withheld")
                    if len(text.encode()) > MAX_BYTES:
                        raise NotionError("Notion tool output exceeded its size limit")
                    return {"ok": not result.is_error, "output": text, "protocol": client.protocol_version}

    def _sync(self, *args, cancelled=None, **kwargs):
        async def run():
            if cancelled is None:
                return await self._run(*args, **kwargs)
            result = {}
            async with anyio.create_task_group() as group:
                async def watch():
                    while True:
                        if cancelled():
                            raise NotionError("Notion read cancelled")
                        await anyio.sleep(0.1)
                async def work():
                    result["value"] = await self._run(*args, **kwargs)
                    group.cancel_scope.cancel()
                group.start_soon(watch)
                group.start_soon(work)
            return result["value"]
        try:
            return anyio.run(run)
        except NotionError:
            raise
        except Exception as error:
            def safe_error(value, depth=0):
                if isinstance(value, NotionError):
                    return value
                if isinstance(value, BaseExceptionGroup) and depth < 8:
                    for child in value.exceptions:
                        found = safe_error(child, depth + 1)
                        if found:
                            return found
                return None
            known = safe_error(error)
            if known:
                raise known from None
            # SDK/HTTP exceptions can contain authorization headers or provider
            # response text. Return a bounded, secret-free error to the runtime.
            raise NotionError("Notion MCP could not complete this read; check the connection and try again") from None

    def discover(self) -> dict:
        return self._sync()

    def call(self, name, args, expected_revision, *, before_call=None, cancelled=None) -> dict:
        if len(canonical_json(args).encode()) > 64_000:
            raise NotionError("Notion read arguments exceeded their size limit")
        if name not in READ_TOOLS:
            raise NotionError("This Notion connector exposes only reviewed search and fetch tools")
        return self._sync(name, args, expected_revision, before_call=before_call, cancelled=cancelled)
