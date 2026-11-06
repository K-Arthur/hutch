"""Turn a media job request into the placeholder values a route's templates use.

Validation lives here, before any billable call: a prompt over the route's bound, a voice the
route does not offer, a duration the model cannot render. The route's limits are the vendor's
documented limits, so a request outside them is refused with the number, not sent to fail (or to
be silently clamped upstream, which is how a user pays for a clip other than the one requested).
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Mapping

from .route_spec import MediaRoute

_DEFAULT_PROMPT_CHARS = 4000


class RouteInputError(ValueError):
    """The request is outside what the route can honestly do."""


def request_values(route: MediaRoute, req: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(req.get("prompt") or "").strip()
    limit = int(route.limits.get("prompt_chars") or _DEFAULT_PROMPT_CHARS)
    if not prompt:
        raise RouteInputError("the request carries no prompt")
    if len(prompt) > limit:
        raise RouteInputError(f"{route.title} accepts at most {limit} characters; this prompt "
                              f"has {len(prompt)}")
    style = str(req.get("style") or "").strip() or None
    if style and not route.limits.get("style"):
        raise RouteInputError(f"{route.title} does not take a style instruction; remove it or "
                              "choose a route that does")
    values: dict[str, Any] = dict(route.defaults)
    values.update({"prompt": prompt, "model": route.model,
                   "model_app": "/".join(route.model.split("/")[:2]), "uuid": str(uuid.uuid4()),
                   "aspect_ratio": _aspect(route, req), "seconds": _seconds(route, req),
                   "voice": _voice(route, req), "style": style})
    return values


def _voice(route: MediaRoute, req: Mapping[str, Any]) -> Any:
    offered = list(route.limits.get("voices") or [])
    voice = str(req.get("voice") or route.defaults.get("voice") or "").strip() or None
    if voice and offered and voice not in offered:
        raise RouteInputError(f"voice {voice!r} is not offered by {route.title} "
                              f"(offered: {', '.join(offered)})")
    return voice


def _aspect(route: MediaRoute, req: Mapping[str, Any]) -> Any:
    ratios = list(route.limits.get("aspect_ratios") or [])
    width, height = req.get("width"), req.get("height")
    if not ratios or not (isinstance(width, int) and isinstance(height, int)
                          and width > 0 and height > 0):
        return route.defaults.get("aspect_ratio")
    target = math.log(width / height)

    def distance(text: str) -> float:
        left, right = (float(part) for part in text.split(":"))
        return abs(math.log(left / right) - target)

    return min(ratios, key=distance)


def _seconds(route: MediaRoute, req: Mapping[str, Any]) -> Any:
    spec = route.limits.get("seconds")
    if not spec:
        return None
    asked = req.get("seconds")
    default = spec.get("default")
    if not isinstance(asked, (int, float)) or isinstance(asked, bool):
        return default
    allowed = spec.get("allowed")
    if allowed:
        if asked not in allowed:
            raise RouteInputError(f"{route.title} renders {', '.join(str(a) for a in allowed)} "
                                  f"seconds; {asked:g} was requested")
        return int(asked)
    low, high = spec.get("min", 1), spec.get("max", 600)
    if not low <= asked <= high:
        raise RouteInputError(f"{route.title} renders {low} to {high} seconds; {asked:g} was "
                              "requested")
    return int(round(asked))
