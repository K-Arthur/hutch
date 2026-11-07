"""Per-assistant data-sharing confirmation for non-local model routes (EC-28).

Read the disclosure before the client asks; record the one-use confirmation the
save or one-message override will consume. Nothing here sends a prompt or
contacts a model: the read uses the Phase 1 locality classifier and a bounded
Ollama tag read, and the write only stores a digest.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..route_sharing import disclosure_for, record_ack
from .security import check_csrf


class SharingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)
    scope: Literal["default", "override"]


def _bot_or_404(store: Any, ref: str):
    bot = store.get_bot(ref)
    if bot is None:
        raise HTTPException(404, f"no such bot: {ref}")
    return bot


def install_model_sharing_routes(app, store, config) -> None:
    @app.get("/api/bots/{ref}/model-sharing")
    def read_model_sharing(ref: str, model: str) -> dict:
        """Whether this route needs a confirmation, and the exact words to show."""
        bot = _bot_or_404(store, ref)
        disclosure = disclosure_for(bot, model, config)
        return {"required": disclosure is not None,
                "disclosure": disclosure.to_json() if disclosure else None}

    @app.post("/api/bots/{ref}/model-sharing")
    async def record_model_sharing(ref: str, body: SharingRequest, request: Request) -> dict:
        """Record one confirmation; the save or send that follows consumes it once."""
        submitted = request.headers.get("x-csrf-token") or request.headers.get("x-hutch-csrf")
        if not check_csrf(request, submitted):
            raise HTTPException(403, "the page's security token did not match; reload the page and try again")
        bot = _bot_or_404(store, ref)
        disclosure = disclosure_for(bot, body.model, config)
        if disclosure is None:
            return {"required": False, "recorded": False, "disclosure": None}
        record_ack(store, bot.id, body.model, body.scope, disclosure)
        return {"required": True, "recorded": True, "disclosure": disclosure.to_json()}
