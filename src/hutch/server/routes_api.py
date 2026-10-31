"""AI service and route authority API: one read model for Models, Settings and first run.

Owner configuration only (paired phones are refused by the default-deny inventory). Read-only: it never
starts a model server or changes an assistant.
"""

from __future__ import annotations

from fastapi import FastAPI

from .. import routes


def install_routes_api(app: FastAPI, store, config) -> None:
    @app.get("/api/v1/routes")
    def route_authority() -> dict:
        return routes.authority(store, config)
