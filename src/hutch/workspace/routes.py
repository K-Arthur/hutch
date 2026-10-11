"""HTTP surface for the conversation workspace: session status and reset.

A factory, not a mount: ``build_workspace_router(store, manager_factory)``
returns an :class:`~fastapi.APIRouter` the integrator includes on the app
(the way ``server/app.py`` mounts the remote sub-application with
``dependencies=[Depends(authorize_remote_route)]``). The route bodies are
plain closures over ``store`` — the same style as the document routes — so
auth stays the app's single decision point: these paths are NOT in
``REMOTE_ROUTE_CAPABILITIES``, which keeps them local-owner-only until the
integrator deliberately adds them.

The reset route mirrors the ``reset_workspace`` tool honestly: a running
cell refuses the reset (busy), success bumps the generation, and the
response carries the same stale marker the tool emits so consumers can mark
prior outputs by comparing ``environment_generation`` on their receipts.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ..store import Store
from .manager import WorkspaceManager

ManagerFactory = Callable[[str], WorkspaceManager]


def build_workspace_router(store: Store, manager_factory: ManagerFactory) -> APIRouter:
    """``GET  /api/v1/conversations/{id}/workspace/session`` — status, generation,
    environment fingerprint (manager state plus the durable store row).

    ``POST /api/v1/conversations/{id}/workspace/reset`` — mirrors the
    reset_workspace tool: verified teardown, generation bump, stale marker.
    """

    router = APIRouter(prefix="/api/v1")

    def _session_or_404(conversation_id: str) -> dict[str, Any]:
        row = store.get_workspace_session(conversation_id)
        if row is None:
            raise HTTPException(404, f"no workspace session for conversation {conversation_id}")
        return row

    def _fingerprint(row: dict[str, Any]) -> dict[str, Any] | None:
        raw = row.get("env_fingerprint")
        if isinstance(raw, str) and raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        return None

    @router.get("/conversations/{conversation_id}/workspace/session")
    def workspace_session(conversation_id: str) -> dict[str, Any]:
        row = _session_or_404(conversation_id)
        manager = manager_factory(conversation_id)
        info = manager.session_info()
        return {
            "conversation_id": conversation_id,
            "status": info["status"],                    # stopped | ready | busy | lost
            "generation": int(row["generation"]),
            "store_status": row["status"],               # active | expired | terminated
            "env_fingerprint": _fingerprint(row),
            "workspace_dir": row.get("workspace_dir") or info["workspace_dir"],
            "ordinal": info["ordinal"],
            "child_alive": info["child_alive"],
            "last_error": info["last_error"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    @router.post("/conversations/{conversation_id}/workspace/reset")
    def workspace_reset(conversation_id: str) -> dict[str, Any]:
        _session_or_404(conversation_id)                 # resetting a never-started workspace is a 404, not a fiction
        manager = manager_factory(conversation_id)
        result = manager.restart(reason="workspace reset via API")
        if not result.get("ok"):
            raise HTTPException(409, str((result.get("error") or {}).get("value", "busy")))
        return {
            "ok": True,
            "conversation_id": conversation_id,
            "generation": result.get("generation"),
            "stale": result.get("stale"),
            "survivors": result.get("survivors", 0),
            "detail": ("in-memory state is gone; files in the workspace directory remain; "
                       "outputs from the previous generation are stale"),
        }

    return router
