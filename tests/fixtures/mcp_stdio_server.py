"""Tiny JSON-RPC MCP stdio server used by the local containment tests."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path


TOOLS = [
    {"name": "read_workspace", "description": "Read one requested path", "inputSchema": {
        "type": "object", "properties": {"path": {"type": "string"}},
        "required": ["path"], "additionalProperties": False}},
    {"name": "write_workspace", "description": "Write one requested path", "inputSchema": {
        "type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"], "additionalProperties": False}},
    {"name": "inspect_process", "description": "Inspect the child environment and network", "inputSchema": {
        "type": "object", "properties": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}},
        "required": ["port"], "additionalProperties": False}},
    {"name": "wait_for_cancel", "description": "Wait for Hutch to cancel the owned process", "inputSchema": {
        "type": "object", "properties": {"marker": {"type": "string"}},
        "required": ["marker"], "additionalProperties": False}},
]


def dispatch(message: dict) -> dict | None:
    method = message.get("method")
    if method in {"notifications/initialized", "notifications/cancelled"} or "id" not in message:
        return None
    if method == "server/discover":
        result = {"supportedVersions": ["2025-11-25", "2026-07-28"], "capabilities": {"tools": {}},
                  "resultType": "complete", "ttlMs": 0, "cacheScope": "private"}
    elif method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": True}},
                  "serverInfo": {"name": "hutch-local-fixture", "version": "1"}}
    elif method == "tools/list":
        cursor = (message.get("params") or {}).get("cursor")
        result = {"tools": TOOLS[2:] if cursor == "page-2" else TOOLS[:2],
                  "resultType": "complete", "ttlMs": 0, "cacheScope": "private"}
        if cursor is None:
            result["nextCursor"] = "page-2"
    elif method == "tools/call":
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        if params.get("name") == "read_workspace":
            try:
                output = Path(arguments["path"]).read_text()
            except (OSError, KeyError, TypeError) as exc:
                output = f"unavailable:{type(exc).__name__}"
        elif params.get("name") == "write_workspace":
            try:
                Path(arguments["path"]).write_text(arguments["content"])
                output = "written"
            except (OSError, KeyError, TypeError) as exc:
                output = f"unavailable:{type(exc).__name__}"
        elif params.get("name") == "inspect_process":
            try:
                with socket.create_connection(("127.0.0.1", int(arguments["port"])), timeout=1):
                    network = "connected"
            except OSError:
                network = "isolated"
            output = json.dumps({"home": os.environ.get("HOME"), "secret_env": os.environ.get("HUTCH_TEST_SECRET"),
                                 "cwd": os.getcwd(), "network": network}, sort_keys=True)
        elif params.get("name") == "wait_for_cancel":
            Path(arguments["marker"]).write_text("started")
            while True:
                import time
                time.sleep(1)
        else:
            result = {"content": [{"type": "text", "text": "unknown tool"}], "isError": True,
                      "resultType": "complete", "ttlMs": 0, "cacheScope": "private"}
            return {"jsonrpc": "2.0", "id": message["id"], "result": result}
        result = {"content": [{"type": "text", "text": output}], "isError": False,
                  "resultType": "complete", "ttlMs": 0, "cacheScope": "private"}
    else:
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "hutch-local-fixture", "version": "1"}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


for line in sys.stdin:
    try:
        response = dispatch(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    except Exception as exc:  # keep protocol stdout clean when a fixture fails
        print(f"fixture error: {type(exc).__name__}", file=sys.stderr, flush=True)
