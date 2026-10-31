"""Suggested assistants: list what the main assistant has proposed, and dismiss a suggestion.

Read and dismiss only. There is deliberately no route that creates an assistant from a proposal: the person opens it, lands
in the normal reviewed setup with the name and job filled in, and creates it there like any other assistant.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from .. import proposals


def install_proposal_routes(app: FastAPI, store) -> None:
    from .bot_deletion_api import require_local_owner

    @app.get("/api/v1/assistant-proposals")
    def list_proposals() -> dict:
        return {"proposals": [{key: item[key] for key in ("id", "name", "job", "why", "created_at")} for item in proposals.pending(store)],
                "limit": proposals.MAX_PENDING}

    @app.post("/api/v1/assistant-proposals/{proposal_id}/dismiss")
    def dismiss_proposal(proposal_id: str, request: Request) -> dict:
        require_local_owner(request)
        try:
            proposals.resolve(store, proposal_id, "dismissed")
        except KeyError:
            raise HTTPException(404, "no such suggestion") from None
        return {"proposals": [item["id"] for item in proposals.pending(store)]}
