"""Read-only `hutch doctor` findings for the first-run page.

The doctor already knows whether the install is healthy and whether scheduled work will
run; first run said nothing about either. This exposes its checks (no network, no deep
probes) and changes nothing. Installing the background service stays a separate, confirmed
action (`POST /api/v1/runtime/service/install`). Paired phones get no access: new API routes
are default-deny until REMOTE_ROUTE_CAPABILITIES grants one.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException


def install_setup_check_routes(app: FastAPI) -> None:
    config, store = app.state.config, app.state.store

    @app.get("/api/v1/setup/check")
    def setup_check() -> dict:
        from .. import doctor

        try:
            checks = doctor.run_doctor(config, store)
        except Exception:  # a probe failure must not become a traceback on the first screen
            raise HTTPException(503, "the setup check could not run") from None
        return {"worst": doctor.worst(checks), "checks": [asdict(check) for check in checks]}
