"""Turn a runtime's install failure into a state a person can act on.

The runtime's text is useful evidence but is not a UI. This module maps the failure
classes Phase 4 can produce on a real machine (disk full, network drop, dead runtime,
missing tag, credential, digest) to a short message and one action, and removes
credentials before the text reaches a job, a page or a log.

The matching is deliberately text-based: the Ollama pull stream has no error codes, and
an HTTP status alone cannot distinguish a full disk from a dropped connection. Tests use
the exact bytes captured from the real stack or the runtime's documented shapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..hardware import GIB

_DISK = re.compile(r"no space left|disk full|enospc|not enough (?:disk )?space", re.IGNORECASE)
_NETWORK = re.compile(
    r"connection (?:reset|aborted|refused)|timed out|timeout|unexpected eof|\beof\b|"
    r"max retries|network is unreachable|no such host|temporary failure|tls handshake|"
    r"context deadline|broken pipe|remote end closed",
    re.IGNORECASE)
_AUTH = re.compile(r"unauthorized|forbidden|\b401\b|\b403\b|authentication|sign[- ]?in|"
                   r"invalid (?:api )?(?:key|token)|access token", re.IGNORECASE)
_INTEGRITY = re.compile(r"digest|sha256|checksum|verification failed|corrupt", re.IGNORECASE)
_MISSING = re.compile(r"not found|manifest unknown|does not exist|no such model|unknown model|"
                      r"pull access denied", re.IGNORECASE)
_DOWN = re.compile(r"cannot connect|connection refused|server (?:is )?(?:down|unavailable)|"
                   r"runtime (?:is )?(?:down|not running)|ollama.*not running", re.IGNORECASE)

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(key|token|password|secret|api_key|access_token)=([^&\s\"']+)"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
)
_MAX_DETAIL = 600


@dataclass(frozen=True)
class InstallFailure:
    code: str
    message: str
    action: str
    detail: str = ""

    def to_json(self) -> dict:
        return {"code": self.code, "message": self.message, "action": self.action, "detail": self.detail}


def redact_secrets(text: str) -> str:
    """Remove credentials from runtime text; never return the original value."""
    out = str(text or "")
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            out = pattern.sub(r"\1=[redacted]", out)
        else:
            out = pattern.sub("[redacted]", out)
    return out[:_MAX_DETAIL]


def _gib(value: Optional[int]) -> str:
    return f"{(value or 0) / GIB:.1f} GiB"


def cancelled_failure() -> InstallFailure:
    return InstallFailure(
        "cancelled",
        "Cancelled. Press Install again to resume; verified parts are kept.",
        "retry", "cancelled before the download finished")


def interrupted_failure() -> InstallFailure:
    return InstallFailure(
        "interrupted",
        "The download stream ended early. Verified parts are kept; press Install to resume.",
        "retry", "the runtime closed the stream before reporting success")


def unconfirmed_failure() -> InstallFailure:
    return InstallFailure(
        "unconfirmed",
        "The runtime reported success but does not list the model. Check `ollama list`, then try again.",
        "retry", "success without the model in the runtime's registry")


def classify_install_error(text: str, *, free_bytes: Optional[int] = None,
                           size_bytes: Optional[int] = None) -> InstallFailure:
    """Map one failure string to a code, a message and an action."""
    detail = redact_secrets(text)
    if _DISK.search(detail):
        room = ""
        if free_bytes is not None:
            room = f" {_gib(free_bytes)} is free"
            if size_bytes:
                room += f" and the model needs about {_gib(size_bytes)}"
            room += "."
        return InstallFailure(
            "disk_full",
            f"The disk filled during the download.{room} Free space, then press Install to resume; "
            "verified parts are kept.", "free_space", detail)
    if _AUTH.search(detail):
        return InstallFailure(
            "needs_auth",
            "The runtime needs its own credential for this model (a gated repository or a cloud model). "
            "Configure it in the runtime; Hutch never puts a token in a URL.", "runtime_auth", detail)
    if _INTEGRITY.search(detail):
        return InstallFailure(
            "integrity",
            "The runtime rejected a downloaded blob's digest. Press Install to fetch it again; "
            "the runtime verifies every blob.", "retry", detail)
    if _MISSING.search(detail):
        return InstallFailure(
            "model_missing",
            "The runtime does not know that model or tag. Check the spelling and the tag; "
            "a renamed or removed tag is a different model.", "check_name", detail)
    if _DOWN.search(detail):
        return InstallFailure(
            "runtime_down",
            "The model runtime stopped answering. Start it, then press Install to resume; "
            "verified parts are kept.", "start_runtime", detail)
    if _NETWORK.search(detail):
        return InstallFailure(
            "network",
            "The download stopped because the network dropped. Verified parts are kept; "
            "press Install to resume.", "retry", detail)
    return InstallFailure(
        "unknown",
        "The download failed. Press Install to try again; the runtime keeps verified parts.",
        "retry", detail or "no error text from the runtime")
