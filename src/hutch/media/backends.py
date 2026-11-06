"""Build the media backends that can honestly run on this machine, right now.

A backend exists only when its credential does. Two credential sources, both labeled so the
approval prompt can say who pays and where the key came from:

* a **connection** the user configured from a template the route names (``xai``, ``minimax``,
  ``google-gemini``, ``openai-api``): the key, endpoint and billing relationship are that
  connection's, and the backend is named ``<route>:<connection>``;
* an **environment variable** the route names (``FAL_KEY``, ``PIXVERSE_API_KEY``,
  ``ELEVENLABS_API_KEY``, ``DEEPGRAM_API_KEY``), for vendors that have no chat connection. It is
  labeled ambient: a key in the environment is not a decision the user made in Hutch.

Built per call, never cached, because connections and keys are runtime data. Nothing is chosen
between backends here; ``MediaJobService.backend_for`` refuses to pick between accounts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from ..connections import Connection, ConnectionBook
from .providers.base import MediaBackend
from .providers.route_backend import SyncRouteBackend
from .providers.route_spec import MediaRoute, load_routes
from .providers.route_task import TaskRouteBackend
from .spool import MediaSpool


def build_backends(state_dir: Path | str, *, spool: Optional[MediaSpool] = None,
                   environ: Optional[Mapping[str, str]] = None,
                   client: Any = None) -> dict[str, MediaBackend]:
    """Every backend whose credential exists. ``client`` injects an httpx client in tests."""
    env = os.environ if environ is None else environ
    book = ConnectionBook(Path(state_dir))
    found: dict[str, MediaBackend] = {}
    for route in load_routes().values():
        if route.buildable:
            for backend in _for_route(route, book, env, spool, client):
                found[backend.name] = backend
    for backend in _legacy(book, env, spool):
        found.setdefault(backend.name, backend)
    return found


def _for_route(route: MediaRoute, book: ConnectionBook, env: Mapping[str, str],
               spool: Optional[MediaSpool], client: Any) -> list[MediaBackend]:
    if route.env_var:
        key = str(env.get(route.env_var) or "").strip()
        if not key:
            return []
        return [_make(route, base_url=str(route.credential["base_url"]), key=key, conn=None,
                      label=f"environment variable {route.env_var} (ambient)",
                      spool=spool, client=client)]
    out: list[MediaBackend] = []
    for name, conn in sorted(book.configured().items()):
        key = book.key(name)
        if conn.template in route.templates and key:
            out.append(_make(route, base_url=conn.base_url, key=key, conn=conn,
                             label=_key_label(book, name), spool=spool, client=client))
    return out


def _key_label(book: ConnectionBook, name: str) -> str:
    return f"connection {name} ({book.key_source(name) or 'key source unknown'})"


def _make(route: MediaRoute, *, base_url: str, key: str, conn: Optional[Connection], label: str,
          spool: Optional[MediaSpool], client: Any) -> MediaBackend:
    connection = conn.name if conn else ""
    billing = conn.billing if conn else "vendor account (per request)"
    headers = {"User-Agent": conn.user_agent, **conn.headers} if conn else {}
    if route.protocol == "adapter":
        return _ADAPTERS[route.adapter](route, base_url, key, connection, label, spool, client)
    cls = TaskRouteBackend if route.protocol == "task" else SyncRouteBackend
    return cls(route, base_url=base_url, api_key=key, connection=connection, billing=billing,
               credential_label=label, headers=headers, client=client, spool=spool)


def _openai_images(route: MediaRoute, base_url: str, key: str, connection: str, label: str,
                   spool: Optional[MediaSpool], client: Any) -> MediaBackend:
    from .providers.openai_images import OpenAIImagesBackend

    backend = OpenAIImagesBackend(api_key=key, model=route.model, base_url=base_url,
                                  http_client=client, spool=spool, label=label)
    backend.name = f"{route.id}:{connection}" if connection else route.id
    return backend


_ADAPTERS: dict[str, Callable[..., MediaBackend]] = {"openai-images": _openai_images}


def _legacy(book: ConnectionBook, env: Mapping[str, str],
            spool: Optional[MediaSpool]) -> list[MediaBackend]:
    """Backends that predate the route table: an ambient OpenAI key, ComfyUI, chat-speech."""
    from .providers.comfyui import ComfyUIBackend
    from .providers.openai_images import OpenAIImagesBackend

    out: list[MediaBackend] = []
    if env.get("OPENAI_API_KEY"):
        ambient = OpenAIImagesBackend.from_env(spool, env)
        if ambient is not None:
            out.append(ambient)
    comfy = ComfyUIBackend.from_env(env)
    if comfy is not None:
        out.append(comfy)
    return out + _chat_speech(book, spool)


def _chat_speech(book: ConnectionBook, spool: Optional[MediaSpool]) -> list[MediaBackend]:
    """Connections whose template declares a chat-completions ``speech`` route (Xiaomi MiMo)."""
    from ..providers.catalog import bundled_catalog
    from .providers.speech import SpeechBackend, route_from_template

    templates = book.templates()
    out: list[MediaBackend] = []
    for name, conn in sorted(book.configured().items()):
        try:
            route = route_from_template(templates.get(conn.template))
        except ValueError:
            continue          # a malformed template is Hutch's bug; it is not a backend
        key = book.key(name)
        if route is None or not key:
            continue
        entry = bundled_catalog().provider_for_template(conn.template)
        out.append(SpeechBackend(
            connection=name, base_url=conn.base_url, api_key=key, route=route,
            provider=entry.id if entry is not None else conn.name, billing=conn.billing,
            headers={"User-Agent": conn.user_agent, **conn.headers}, spool=spool))
    return out
