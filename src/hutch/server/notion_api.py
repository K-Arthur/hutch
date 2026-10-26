"""Local-owner Notion setup; paired devices never administer provider connections."""
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from ..integrations.notion import NotionBook, NotionError
from ..integrations.notion_mcp import NotionMCP
from ..integrations import notion_access


class NotionSignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="Notion", min_length=1, max_length=80)


class NotionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot: str = Field(min_length=1, max_length=100)
    tools: list[Literal["notion-search", "notion-fetch"]] = Field(min_length=1, max_length=2)
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def install_notion_routes(app, store, config):
    @app.get("/api/v1/connections/notion")
    def connections(response: Response):
        response.headers["Cache-Control"] = "no-store"
        book = NotionBook(config.state_dir)
        grants = [{key: item[key] for key in ("account_id", "bot_id", "name", "canonical_name", "schema_revision")}
                  for item in notion_access.bindings(store)]
        return {"secret_store_available": book.secrets.available(), "accounts": book.accounts(), "grants": grants,
                "read_only": True, "detail": "Notion search and page reads only. Each assistant needs an explicit grant; read queries use that grant. OAuth can authorize broader Notion access than the read tools Hutch exposes."}

    @app.post("/api/v1/connections/notion/sign-in")
    def sign_in(request: Request, body: NotionSignIn, response: Response):
        book = NotionBook(config.state_dir)
        try:
            result = book.start(body.label, book.callback_uri(request))
        except NotionError as error:
            raise HTTPException(409, str(error)) from None
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return {"authorization_url": result.url}

    @app.get("/api/v1/connections/notion/callback", include_in_schema=False)
    def callback(request: Request):
        status, detail = "connected", ""
        book = NotionBook(config.state_dir)
        try:
            uri = book.callback_uri(request)
            values = {}
            for key in ("state", "code", "error", "iss"):
                entries = request.scope.get("hutch_oauth_query", {}).get(key, [])
                if len(entries) > 1:
                    raise NotionError("Notion returned duplicate sign-in fields; start again")
                values[key] = entries[0] if entries else ""
            if not values["state"]:
                raise NotionError("Notion did not return sign-in state; start again")
            if values["error"]:
                book.cancel(values["state"])
                raise NotionError("Notion access was not granted; no account was connected")
            book.finish(values["state"], values["code"], uri, issuer=values["iss"])
        except NotionError as error:
            status, detail = "error", str(error)
        location = f"/?notion_result={status}"
        if detail:
            location += "&detail=" + quote(detail)
        response = RedirectResponse(location + "#/connections", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.post("/api/v1/connections/notion/accounts/{account_id}/discover")
    def discover(account_id: str):
        try:
            book = NotionBook(config.state_dir)
            book._account(account_id)
            result = NotionMCP(book, account_id).discover()
            return notion_access.save_discovery(store, account_id, result)
        except NotionError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/connections/notion/accounts/{account_id}/grants")
    def grant(account_id: str, body: NotionGrant):
        try:
            NotionBook(config.state_dir)._account(account_id)
            return notion_access.grant_tools(store, account_id, body.bot, body.tools, body.revision)
        except NotionError as error:
            raise HTTPException(409, str(error)) from None

    @app.delete("/api/v1/connections/notion/accounts/{account_id}/grants/{bot}")
    def revoke(account_id: str, bot: str):
        try:
            notion_access.revoke(store, account_id, bot)
            return {"removed": True}
        except NotionError as error:
            raise HTTPException(422, str(error)) from None

    @app.post("/api/v1/connections/notion/accounts/{account_id}/disconnect")
    def disconnect(account_id: str):
        try:
            notion_access.revoke(store, account_id)
            result = NotionBook(config.state_dir).disconnect(account_id)
            return {**result, "detail": "Local Notion access and assistant grants were removed. " +
                    ("Provider revocation confirmed." if result["provider_revocation"] == "confirmed" else
                     "Provider revocation was not confirmed; review connected apps in Notion.")}
        except NotionError as error:
            raise HTTPException(422, str(error)) from None
