"""Call an HTTP endpoint with a vault credential, without giving the credential to the model.

The tool's whole reason to exist is the distinction between **using** and **reading** a secret. The
model supplies an opaque reference and a URL; Hutch checks the grant, checks that the owner bound
the secret to that exact origin, injects the value into one header at the network boundary, and
returns only the service's response. No output field, event or transcript contains the value.

Redirects are not followed. A 3xx is reported as the result, and a second call would need its own
authorization and its own binding for the new origin.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ..safety import Decision, Verdict
from ..vault import Principal, SecretRef, SecretRefError, VaultError, vault_for
from ..vault.destinations import DestinationError, request_origin
from ..vault.egress import EgressError, MAX_REQUEST_BYTES, mediate_http
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

#: The owner's binding is the standing authorization for *where* a secret may go. This decision
#: still pauses a bot whose approval mode is ``ask``; an ``auto`` bot proceeds, as it does for other
#: non-outward actions, because the pairing was created deliberately by the owner.
_CREDENTIAL_DECISION = Decision(
    verdict=Verdict.ask,
    reason="a vault credential is presented to an external service",
    rule="vault:use",
    risk="high",
)

_REF_PATTERN = r"^secret://hutch/local/sec_[0-9a-f]{24}(#v[1-9][0-9]{0,8})?$"
_HEADER_NAME_PATTERN = r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,64}$"

MAX_OUTPUT_CHARS = 20000


class VaultHttpTool(Tool):
    name = "vault_http_request"
    description = (
        "Call an HTTP endpoint with a credential stored in the Hutch vault. The caller passes a "
        "secret reference, never a value. Hutch injects the credential into one header at the "
        "network boundary, sends the request only to an origin the owner bound to that secret, "
        "does not follow redirects, and returns the service response. The credential is never "
        "included in the result or the transcript."
    )
    parameters = _schema(
        ["secret_ref", "url"],
        {
            "secret_ref": {
                "type": "string",
                "description": "Opaque vault reference, e.g. secret://hutch/local/sec_<24 hex>.",
                "pattern": _REF_PATTERN,
            },
            "url": {
                "type": "string",
                "description": ("Absolute http(s) URL. Its origin must already be bound to the "
                                "secret by the owner."),
                "maxLength": 2048,
            },
            "method": {
                "type": "string",
                "description": "HTTP method. A GET or HEAD request cannot carry a body.",
                "enum": ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
                "default": "GET",
            },
            "header": {
                "type": "string",
                "description": "Header that carries the credential.",
                "pattern": _HEADER_NAME_PATTERN,
                "default": "Authorization",
            },
            "prefix": {
                "type": "string",
                "description": "Text placed before the credential, e.g. 'Bearer ' or 'token '.",
                "maxLength": 32,
                "default": "Bearer ",
            },
            "body": {
                "type": "string",
                "description": "Request body for POST, PUT, PATCH or DELETE.",
                "maxLength": MAX_REQUEST_BYTES,
            },
            "content_type": {
                "type": "string",
                "description": "Content type for a request body.",
                "enum": ["application/json", "application/x-www-form-urlencoded", "text/plain"],
            },
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "web"

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Persist the reference and the destination, never a query string.

        Authorization is by origin, so a query is never what made the call legal; keeping it in an
        event or an action receipt would only give a model-authored token a durable home. The path
        stays because it says what was asked for.
        """
        recorded = dict(args)
        raw = args.get("url")
        if isinstance(raw, str):
            try:
                parts = urlsplit(raw.strip())
                origin = request_origin(raw)
            except (ValueError, DestinationError):
                recorded["url"] = "<invalid URL>"
            else:
                path = parts.path if parts.path.startswith("/") else f"/{parts.path}"
                recorded["url"] = origin + path[:2048] + ("?[redacted]" if parts.query else "")
        recorded.pop("body", None)
        return recorded

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            reference = SecretRef.parse(args.get("secret_ref"))
            url = str(args.get("url") or "").strip()
            destination = request_origin(url)
        except (SecretRefError, DestinationError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        method = str(args.get("method") or "GET").upper()
        header = str(args.get("header") or "Authorization")
        prefix = args.get("prefix")
        prefix = "Bearer " if prefix is None else str(prefix)
        body = args.get("body")
        body = "" if body is None else str(body)
        content_type = str(args.get("content_type") or "")

        decision = ctx.policy.check_url(url)
        if decision.verdict is Verdict.deny:
            return ToolResult(ok=False, output=f"error: {decision.reason}")
        if ctx.dry_run:
            return rehearsed(f"send a {method} request to {destination} with {reference}",
                             _CREDENTIAL_DECISION)
        try:
            principal = Principal.bot(ctx.bot.id)
        except SecretRefError:
            return ToolResult(ok=False, output="error: this run has no valid bot identity")

        detail = {
            "secret_ref": str(reference),
            "method": method,
            "destination": destination,
            "header": header,
            "body_bytes": len(body.encode("utf-8")),
            "note": "the credential is applied at the network boundary and is never returned",
        }
        try:
            ctx.gate.decide("vault_http_request", f"{method} {destination} with {reference}",
                            detail, _CREDENTIAL_DECISION)
        except Exception as exc:  # denial, expiry, or the run ending while waiting
            return ToolResult(ok=False, output=f"error: {exc}")
        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: the request was not started ({refusal})")

        try:
            response = mediate_http(
                vault_for(ctx.store), ref=reference, principal=principal, method=method, url=url,
                header_name=header, value_prefix=prefix, body=body, content_type=content_type)
        except (VaultError, DestinationError, EgressError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")

        content_type_out = next((value for name, value in response.headers.items()
                                 if name.lower() == "content-type"), "")
        lines = [f"HTTP {response.status} {response.reason}".rstrip(),
                 f"destination: {response.destination}"]
        if content_type_out:
            lines.append(f"content-type: {content_type_out}")
        if response.status in (301, 302, 303, 307, 308) and response.headers.get("location"):
            lines.append("not followed: the service redirected; a new request would need its own "
                         "authorization and destination binding")
            lines.append(f"location: {response.headers['location']}")
        if response.truncated:
            lines.append("[response body clipped at the size limit]")
        text = "\n".join(lines) + "\n\n" + response.body
        return ToolResult(
            ok=response.ok,
            output=clip(text, MAX_OUTPUT_CHARS),
            data={
                "status": response.status,
                "destination": response.destination,
                "content_type": content_type_out,
                "truncated": response.truncated,
                "secret_ref": str(reference),
            },
        )


__all__ = ["VaultHttpTool"]
