"""Deterministic, model-free change detection for external sources.

A source adapter answers one question: *what changed since the cursor we last
committed?* It never calls a model, never mutates the source, and always
returns a bounded result. The engine records the outcome transactionally
(cursor + events together), so a crash re-scans and the event-identity unique
constraint absorbs duplicates.

Adapters must distinguish "no change" from "cannot read right now":
unreadable sources raise :class:`SourceUnavailable` and are recorded as errors
with backoff; they are never silently reported as unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

#: bounded per check; extra material stays queued for the next scan
DEFAULT_MAX_EVENTS = 50

#: kinds that appear in the durable inbox
EVENT_KINDS = (
    "created", "changed", "deleted", "renamed", "new_items", "revised",
    "history_rewritten", "baseline", "excluded", "truncated",
)


class SourceUnavailable(RuntimeError):
    """The source cannot be read right now (missing volume, network failure...).

    ``retry_after`` lets an adapter carry a provider hint (HTTP Retry-After);
    the store still applies its own exponential backoff floor.
    """

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class EventDraft:
    """One material occurrence, identified by (source, key, content hash)."""

    key: str
    kind: str
    occurrence: str
    summary: str
    content_hash: str = ""
    excluded: bool = False

    def normalized(self) -> "EventDraft":
        kind = self.kind if self.kind in EVENT_KINDS else "changed"
        return EventDraft(key=self.key[:400], kind=kind, occurrence=self.occurrence,
                          summary=" ".join(self.summary.split())[:400],
                          content_hash=self.content_hash[:128], excluded=self.excluded)


@dataclass(frozen=True)
class CheckOutcome:
    cursor: dict
    events: tuple[EventDraft, ...]
    summary: str
    truncated: bool = False


@dataclass(frozen=True)
class SourceRuntime:
    """Bounded execution context handed to adapters (never the whole config)."""

    max_events: int = DEFAULT_MAX_EVENTS
    timeout: float = 15.0
    #: absolute paths that must never feed a source back into Hutch (state dir,
    #: workspace roots): changes there are recorded as intentionally excluded.
    exclude_paths: tuple[str, ...] = ()
    #: injectable transport for feed tests: (url, headers, timeout) -> Fetched-like
    fetch: Optional[Callable[..., Any]] = None
    resolver: Optional[Callable[..., list]] = None


def check_source(kind: str, config: dict, cursor: dict, *, runtime: SourceRuntime,
                 now: datetime) -> CheckOutcome:
    """Dispatch one bounded check for a registered source kind."""
    if kind == "folder":
        from . import folder

        return folder.check(config, cursor, runtime=runtime, now=now)
    if kind == "git":
        from . import git

        return git.check(config, cursor, runtime=runtime, now=now)
    if kind == "feed":
        from . import feed

        return feed.check(config, cursor, runtime=runtime, now=now)
    raise SourceUnavailable(f"unsupported source kind: {kind}")


def default_interval(kind: str, config: dict) -> float:
    """Seconds until the next check when nothing changed (per-kind sensible floor)."""
    if kind == "folder":
        return max(15.0, min(float(config.get("check_seconds", 60) or 60), 3600.0))
    if kind == "git":
        return max(30.0, min(float(config.get("check_seconds", 120) or 120), 3600.0))
    if kind == "feed":
        return max(120.0, min(float(config.get("check_seconds", 900) or 900), 86_400.0))
    return 300.0


def build_registration_config(kind: str, *, path: str = "", url: str = "", ref: str = "",
                              include: Optional[list] = None, ignore: Optional[list] = None,
                              every_seconds: Optional[int] = None) -> dict:
    """Validate one registration into the adapter's bounded config.

    Shared by the CLI and the API so both refuse the same shapes. Raises
    ``ValueError`` with a human-readable reason; callers add transport detail.
    """
    if kind not in ("folder", "git", "feed"):
        raise ValueError("source kind must be folder, git, or feed")
    if kind == "feed":
        candidate = (url or "").strip()
        if not candidate:
            raise ValueError("a feed source needs an http(s) url")
        from ..netguard import screen_url

        blocked = screen_url(candidate)
        if blocked:
            raise ValueError(f"that feed URL is not allowed: {blocked}")
        config: dict = {"url": candidate}
    else:
        raw = (path or "").strip()
        if not raw:
            raise ValueError("a folder or git source needs an absolute path")
        from pathlib import Path as _Path

        candidate_path = _Path(raw).expanduser()
        if not candidate_path.is_absolute():
            raise ValueError("a folder or git source needs an absolute path")
        config = {"path": str(candidate_path)}
        if kind == "folder":
            if include:
                config["include"] = [str(pattern)[:200] for pattern in include]
            if ignore:
                config["ignore_globs"] = [str(pattern)[:200] for pattern in ignore]
        else:
            config["ref"] = (ref or "HEAD").strip() or "HEAD"
    interval = int(every_seconds) if every_seconds else int(default_interval(kind, config))
    config["check_seconds"] = max(10, min(interval, 86_400))
    return config
