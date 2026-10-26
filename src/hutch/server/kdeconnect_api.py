"""Owner-only Linux device discovery and explicit status grants."""
from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ..integrations import kdeconnect, kdeconnect_access


class DeviceGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(pattern=r"^[A-Za-z0-9_]{1,128}$")
    bot: str = Field(min_length=1, max_length=100)


def install_kdeconnect_routes(app, store):
    @app.get("/api/v1/connections/kdeconnect")
    def connections(response: Response):
        response.headers["Cache-Control"] = "no-store"
        # Opening Apps & AI never enumerates devices or activates the daemon.
        return {"available": kdeconnect.available(), "grants": kdeconnect_access.bindings(store), "read_only": True}

    @app.post("/api/v1/connections/kdeconnect/discover")
    def discover(response: Response):
        response.headers["Cache-Control"] = "no-store"
        try:
            return {"devices": kdeconnect.discover(), "read_only": True}
        except kdeconnect.KDEConnectError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/connections/kdeconnect/grants")
    def grant(body: DeviceGrant):
        try:
            status = kdeconnect.device_status(body.device_id)
            return kdeconnect_access.grant(store, body.device_id, status["name"], body.bot)
        except kdeconnect.KDEConnectError as error:
            raise HTTPException(409, str(error)) from None

    @app.delete("/api/v1/connections/kdeconnect/devices/{device_id}/grants/{bot}")
    def revoke(device_id: str, bot: str):
        try:
            kdeconnect_access.revoke(store, device_id, bot)
            return {"removed": True, "detail": "Hutch status access removed. KDE Connect pairing is unchanged."}
        except kdeconnect.KDEConnectError as error:
            raise HTTPException(422, str(error)) from None
