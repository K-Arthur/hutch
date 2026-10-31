"""Installation review API: what an earlier version left behind, and the person's acknowledgement.

Owner configuration only: paired phones are refused by the default-deny inventory. The state is computed on
read; recording a review writes one marker and changes nothing else.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from .. import installation


def install_installation_routes(app: FastAPI, store) -> None:
    from .bot_deletion_api import require_local_owner

    @app.get("/api/v1/installation")
    def installation_state() -> dict:
        return installation.installation_state(store)

    @app.post("/api/v1/installation/review")
    def review_installation(request: Request) -> dict:
        require_local_owner(request)
        return installation.record_review(store)
