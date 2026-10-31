"""Per-route readiness truth for onboarding (pure: no network, store or FastAPI).

One classifier maps a provider failure kind to a canonical state token. Two rules
are enforced in code rather than by caller discipline:

* a metadata check (a model list) can only ever yield ``setup.saved_unverified``;
* only ``generation_result`` can yield ``setup.verified``.

Snapshots built here are process-local display data. They are never persisted and
never hold a secret: ``safe_detail`` redacts the stored key and bounds the text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

MODE_METADATA = "metadata"
MODE_GENERATION = "generation"

PROBE_DEADLINE_SECONDS = 20
SNAPSHOT_TTL_SECONDS = 600
RETRY_AFTER_CAP_SECONDS = 600
DEFAULT_RETRY_SECONDS = 30
MAX_ATTEMPTS = 3
GENERATION_COOLDOWN_SECONDS = 60
DETAIL_LIMIT = 500

CHECKING = "setup.checking"
SAVED_UNVERIFIED = "setup.saved_unverified"
VERIFIED = "setup.verified"
INVALID_CREDENTIAL = "provider.invalid_credential"
PERMISSION_DENIED = "provider.permission_denied"
NO_CREDIT = "provider.no_credit"
RATE_LIMITED = "provider.rate_limited"
RETRY_SCHEDULED = "provider.retry_scheduled"
UNAVAILABLE = "provider.unavailable"
TIMED_OUT = "provider.timed_out"
UNREACHABLE = "provider.unreachable"
INVALID_ROUTE = "provider.invalid_route"
MODEL_MISSING = "provider.model_missing"
CONTEXT_OR_INCOMPLETE = "provider.context_or_incomplete"

_KIND_STATE = {
    "unreachable": UNREACHABLE,
    "timeout": TIMED_OUT,
    "quota": NO_CREDIT,
    "rate_limit": RATE_LIMITED,
    "server": UNAVAILABLE,
    "stream": UNAVAILABLE,
    "oom": UNAVAILABLE,
    "refused": UNAVAILABLE,
    "other": UNAVAILABLE,
    "bad_request": INVALID_ROUTE,
    "model_missing": MODEL_MISSING,
    "context": CONTEXT_OR_INCOMPLETE,
    "incomplete": CONTEXT_OR_INCOMPLETE,
}

_RETRYABLE = frozenset({RATE_LIMITED, TIMED_OUT, UNAVAILABLE, UNREACHABLE})


@dataclass(frozen=True)
class ProbeResult:
    state: str
    kind: str
    http_status: Optional[int]
    retry_after: Optional[float]
    detail: str
    models: tuple[str, ...]
    checked_at: str
    mode: str


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat()


def classify(kind: str, *, http_status: Optional[int] = None,
             retry_after: Optional[float] = None) -> str:
    """Map a ProviderError kind to one canonical state; never a bare error."""
    if kind == "auth":
        return PERMISSION_DENIED if http_status == 403 else INVALID_CREDENTIAL
    return _KIND_STATE.get(kind, UNAVAILABLE)


def safe_detail(text: object, secret: Optional[str] = None, limit: int = DETAIL_LIMIT) -> str:
    """Redact the stored key and bound provider text before it is kept or shown."""
    out = str(text or "")
    if secret:
        out = out.replace(secret, "[key]")
    out = out.strip()
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "\u2026"


def metadata_result(models, detail: str, now: datetime) -> ProbeResult:
    """A reachable, authenticated model list: saved, never verified."""
    return ProbeResult(SAVED_UNVERIFIED, "", None, None, detail, tuple(models), _iso(now), MODE_METADATA)


def generation_result(model: str, detail: str, now: datetime) -> ProbeResult:
    """The only constructor allowed to yield ``setup.verified``."""
    return ProbeResult(VERIFIED, "", None, None, detail, (model,) if model else (), _iso(now),
                       MODE_GENERATION)


def failure_result(kind: str, *, mode: str, detail: str, now: datetime,
                   http_status: Optional[int] = None,
                   retry_after: Optional[float] = None) -> ProbeResult:
    state = classify(kind, http_status=http_status, retry_after=retry_after)
    return ProbeResult(state, kind, http_status, retry_after, detail, (), _iso(now), mode)


def _parse(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def retry_allowed(state: str) -> bool:
    """Credential, permission, credit, route, model and context problems are not transient."""
    return state in _RETRYABLE


def retry_in_seconds(result: ProbeResult, now: datetime) -> int:
    """Seconds still to wait before a retry; zero when none, capped for 429 Retry-After."""
    if result.state != RATE_LIMITED:
        return 0
    checked = _parse(result.checked_at)
    if checked is None:
        return 0
    wait = result.retry_after if result.retry_after else DEFAULT_RETRY_SECONDS
    wait = min(max(float(wait), 0.0), RETRY_AFTER_CAP_SECONDS)
    remaining = wait - (now - checked).total_seconds()
    return max(0, int(remaining + 0.999))


def display_state(result: ProbeResult, now: datetime) -> str:
    """Rate-limited with a wait still running is shown as retry-scheduled."""
    if result.state == RATE_LIMITED and retry_in_seconds(result, now) > 0:
        return RETRY_SCHEDULED
    return result.state


def is_stale(result: ProbeResult, now: datetime) -> bool:
    checked = _parse(result.checked_at)
    return checked is None or (now - checked).total_seconds() > SNAPSHOT_TTL_SECONDS


def revalidation_required(previous: Optional[ProbeResult], now: datetime) -> bool:
    """A missing or stale snapshot is rechecked; an old success is never replayed."""
    return previous is None or is_stale(previous, now)
