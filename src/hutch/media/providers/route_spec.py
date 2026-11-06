"""The media route table: what ``data/media-routes.json`` may say and how it is validated.

A route is one (provider, kind) path to a media service: where it is, how it authenticates, what
body it takes, how its answer is read, what it costs. The catalogue drives data and code drives
behavior (master prompt rule 1), so adding a provider whose wire fits the two protocols below is a
data change plus tests, and one whose wire does not fit stays ``documented`` until it has an
adapter of its own.

Protocols:

``sync``  one request returns the finished media (image, speech). The result is held durably
          before ``submit`` returns (:mod:`hutch.media.spool`).
``task``  one request starts work and returns an id; later requests poll it and name the result
          (video, long audio). Nothing is held between calls, so a job resumes after a restart
          from the id in the ledger alone.
``adapter`` the wire needs code a table cannot express (OpenAI Images picks sizes and parameters
          by model family); the row names the adapter and still carries limits, price and sources.

Statuses use the shared vocabulary. A row that is not ``implemented-unverified`` (``documented``,
``blocked``, ``retired``) carries no request and cannot be built into a backend; it exists so the
UI and the docs can say what is retired or blocked and why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Mapping

KINDS = ("image", "video", "audio")
PROTOCOLS = ("sync", "task", "adapter")
BUILDABLE = "implemented-unverified"
STATUSES = (BUILDABLE, "documented", "blocked", "retired")
_SCHEMES = ("Bearer", "Token", "Key", "")


class RouteSpecError(ValueError):
    """The bundled media route table is malformed. This is Hutch's bug, not the user's."""


@dataclass(frozen=True)
class MediaRoute:
    id: str
    provider: str
    kind: str
    protocol: str
    title: str
    status: str
    model: str
    credential: Mapping[str, Any]
    auth: Mapping[str, Any]
    headers: Mapping[str, str]
    request: Mapping[str, Any]
    response: Mapping[str, Any]
    task: Mapping[str, Any]
    limits: Mapping[str, Any]
    defaults: Mapping[str, Any]
    price: str
    sources: tuple[Mapping[str, Any], ...]
    notes: str
    retired_on: str = ""
    adapter: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def buildable(self) -> bool:
        return self.status == BUILDABLE

    @property
    def env_var(self) -> str:
        return str(self.credential.get("env") or "")

    @property
    def templates(self) -> tuple[str, ...]:
        return tuple(self.credential.get("templates") or ())


def _require(cond: bool, rid: str, message: str) -> None:
    if not cond:
        raise RouteSpecError(f"media route {rid!r}: {message}")


def _parse(rid: str, row: Mapping[str, Any]) -> MediaRoute:
    _require(row.get("kind") in KINDS, rid, f"kind must be one of {KINDS}")
    _require(row.get("status") in STATUSES, rid, f"status must be one of {STATUSES}")
    sources = tuple(row.get("sources") or ())
    _require(bool(sources) and all(s.get("url") and s.get("read") for s in sources), rid,
             "every route cites at least one source with the date it was read")
    if row["status"] == "retired":
        _require(bool(row.get("retired_on")), rid, "a retired route records the date it retired")
    elif row["status"] == BUILDABLE:
        _check_buildable(rid, row)
    return MediaRoute(
        id=rid, provider=str(row.get("provider", "")), kind=row["kind"],
        protocol=str(row.get("protocol", "")), title=str(row.get("title", rid)),
        status=row["status"], model=str(row.get("model", "")),
        credential=dict(row.get("credential") or {}),
        auth=dict(row.get("auth") or {"header": "Authorization", "scheme": "Bearer"}),
        headers=dict(row.get("headers") or {}), request=dict(row.get("request") or {}),
        response=dict(row.get("response") or {}), task=dict(row.get("task") or {}),
        limits=dict(row.get("limits") or {}), defaults=dict(row.get("defaults") or {}),
        price=str(row.get("price", "")), sources=sources, notes=str(row.get("notes", "")),
        retired_on=str(row.get("retired_on", "")), adapter=str(row.get("adapter", "")))


def _check_buildable(rid: str, row: Mapping[str, Any]) -> None:
    _require(row.get("protocol") in PROTOCOLS, rid, f"protocol must be one of {PROTOCOLS}")
    _require(bool(row.get("model")), rid, "a buildable route names its model")
    cred = row.get("credential") or {}
    _require(bool(cred.get("templates")) != bool(cred.get("env")), rid,
             "credential is either connection templates or one environment variable")
    if cred.get("env"):
        _require(str(cred.get("base_url", "")).startswith("https://"), rid,
                 "an environment-credentialed route declares an https base_url")
    _require(row.get("auth", {"scheme": "Bearer"}).get("scheme", "Bearer") in _SCHEMES, rid,
             f"auth scheme must be one of {_SCHEMES}")
    _require(bool(row.get("price")), rid, "a buildable route names its price row")
    if row["protocol"] == "adapter":
        _require(bool(row.get("adapter")), rid, "an adapter route names its adapter")
        return
    _require(row.get("request", {}).get("path", "").startswith("/"), rid,
             "request.path starts with /")
    if row["protocol"] == "task":
        task = row.get("task") or {}
        _require(bool(task.get("id_path")) and bool(task.get("poll")) and bool(task.get("result")),
                 rid, "a task route declares id_path, poll and result")
    else:
        _require(bool(row.get("response", {}).get("kind")), rid, "a sync route declares response.kind")


def load_routes() -> dict[str, MediaRoute]:
    path = resources.files("hutch") / "data" / "media-routes.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["routes"]
    except (OSError, ValueError, KeyError) as exc:
        raise RouteSpecError(f"the bundled media route table cannot be read: {exc}") from exc
    return {rid: _parse(rid, row) for rid, row in rows.items()}


def routes_for_kind(kind: str) -> list[MediaRoute]:
    return [r for r in load_routes().values() if r.kind == kind and r.buildable]
