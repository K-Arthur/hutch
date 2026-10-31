"""Speech-to-text tool: turn one workspace audio file into a transcript.

This is the governed surface for a capability Hutch did not have before: audio the user
already owns (a voice note, a meeting recording) becomes text the model can work with.
Everything that leaves the machine is named before it leaves:

* the connection, its endpoint, the model and the language hint are in the approval prompt;
* the audio is read from the workspace jail only - no URL, no arbitrary host;
* the file must be wav or mp3 (the route's documented formats); Hutch will not guess a
  container, and it will not re-encode one silently;
* the call is never retried, so an uncertain outcome cannot spend twice;
* the provider's reported token usage is written to the run ledger and shown in the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..connections import Connection, ConnectionBook
from ..providers import parse_spec
from ..providers.base import ProviderError
from ..providers.transcription import (MAX_AUDIO_BASE64_BYTES, ChatAudioTranscriber,
                                      TranscriptionRoute, encoded_size, route_from_template,
                                      sniff_audio)
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

#: The largest raw file whose base64 form still fits the documented 10 MB ceiling.
MAX_AUDIO_BYTES = (MAX_AUDIO_BASE64_BYTES // 4) * 3

_TRANSCRIBE_DECISION = Decision(
    verdict=Verdict.ask,
    reason="transcribing sends the recording to an external speech service and may be billed",
    sticky_key="",            # outward: never sticky (SR-4)
    rule="audio:transcribe",
    risk="medium",
    outward=True,
)


class _NoRoute(ValueError):
    """No configured connection can transcribe. Carries a message a person can act on."""


def _configured_routes(book: ConnectionBook) -> tuple[list[tuple[str, Connection, TranscriptionRoute]], list[str]]:
    """Every configured connection that declares a transcription route, plus malformed ones."""
    routes: list[tuple[str, Connection, TranscriptionRoute]] = []
    problems: list[str] = []
    templates = book.templates()
    for name, conn in sorted(book.configured().items()):
        try:
            route = route_from_template(templates.get(conn.template))
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            continue
        if route is not None:
            routes.append((name, conn, route))
    return routes, problems


def _provider_identity(conn: Connection) -> str:
    from ..providers.catalog import bundled_catalog

    entry = bundled_catalog().provider_for_template(conn.template)
    return entry.id if entry is not None else conn.name


def _select_route(ctx: ToolContext, requested: str) -> tuple[str, Connection, TranscriptionRoute]:
    """Resolve exactly one transcription account, or refuse with the choices spelled out."""
    book = ConnectionBook(ctx.config.state_dir)
    routes, problems = _configured_routes(book)
    if requested:
        for name, conn, route in routes:
            if name == requested:
                return name, conn, route
        known = ", ".join(name for name, _conn, _route in routes) or "none"
        raise _NoRoute(f"connection {requested!r} does not declare a transcription route "
                       f"(transcription-capable connections: {known})")
    if len(routes) == 1:
        return routes[0]
    if not routes:
        detail = f" ({'; '.join(problems)})" if problems else ""
        raise _NoRoute("no configured connection offers transcription. Hutch does not send "
                       "audio to a provider that was not connected for it" + detail)
    provider_name = ""
    try:
        provider_name = parse_spec(ctx.bot.model)[0]
    except ValueError:
        provider_name = ""
    matching = [(name, conn, route) for name, conn, route in routes
                if _provider_identity(conn) == provider_name]
    if len(matching) == 1:
        return matching[0]
    names = ", ".join(name for name, _conn, _route in routes)
    raise _NoRoute(f"several connections offer transcription ({names}); name the one to use "
                   "with the 'connection' argument so the account that pays is explicit")


def _read_audio(path: str, ctx: ToolContext) -> tuple[Path, bytes]:
    decision = ctx.policy.check_path(path, ctx.workspace, write=False)
    if decision.verdict.value == "deny":
        raise ValueError(decision.reason)
    resolved = (ctx.workspace.resolve() / path if not Path(path).is_absolute()
                else Path(path)).resolve()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"not a regular file: {path}")
    with resolved.open("rb") as handle:
        data = handle.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError(f"{path} is larger than the {MAX_AUDIO_BYTES / (1024 * 1024):g} MB "
                         "this transcription route accepts")
    if not data:
        raise ValueError(f"{path} is empty")
    return resolved, data


def _record_usage(ctx: ToolContext, conn: Connection, result) -> Optional[str]:
    """Write the provider's reported usage to the run ledger. Returns a warning on failure."""
    provider_id = _provider_identity(conn)
    try:
        ctx.store.add_usage(ctx.run.id, ctx.bot.id, provider_id, result.model,
                            result.prompt_tokens, result.completion_tokens, 0, 0.0,
                            kind="transcription", account_id=conn.account_id,
                            cost_source="unpriced")
        ctx.run.prompt_tokens += result.prompt_tokens
        ctx.run.completion_tokens += result.completion_tokens
        ctx.store.update_run(ctx.run)
    except Exception as exc:  # noqa: BLE001 - the transcript is still real and must be returned
        return f"usage could not be recorded in the run ledger: {exc}"
    return None


class TranscribeAudioTool(Tool):
    name = "transcribe_audio"
    description = (
        "Transcribe a wav or mp3 file from the workspace with a configured speech-to-text "
        "account. The audio leaves the machine and the request may be billed, so Hutch asks "
        "for approval and names the connection, endpoint and model first. It never swaps in a "
        "different provider or model, and an empty reply is reported as a failure, not speech.")
    parameters = _schema(
        ["path"],
        {
            "path": {"type": "string", "description": "Workspace-relative .wav or .mp3 file"},
            "language": {"type": "string", "description":
                         "Language hint: auto (default), zh or en. The chosen route's supported "
                         "values are enforced before any request is sent"},
            "connection": {"type": "string", "description":
                           "Transcription account to use. Defaults to the only configured one, "
                           "or to the account matching this bot's provider"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "web"

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        return {"path": args.get("path"), "language": args.get("language"),
                "connection": args.get("connection")}

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            return ToolResult(ok=False, output="error: a workspace audio path is required")
        language = str(args.get("language") or "auto").strip().lower()
        early = ctx.policy.check_path(path, ctx.workspace, write=False)
        if early.verdict.value == "deny":
            return ToolResult(ok=False, output=f"error: {early.reason}")
        try:
            name, conn, route = _select_route(ctx, str(args.get("connection") or "").strip())
        except _NoRoute as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        try:
            language = route.check_language(language)
        except ProviderError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        try:
            resolved, audio = _read_audio(path, ctx)
        except (OSError, ValueError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        audio_format = sniff_audio(audio)
        if audio_format is None:
            return ToolResult(ok=False, output=(
                f"error: {path} is not wav or mp3 by its bytes. This route accepts those two "
                "containers only; Hutch does not guess a format or convert the file silently."))
        if encoded_size(len(audio)) > route.max_audio_base64_bytes:
            limit_mb = route.max_audio_base64_bytes / (1024 * 1024)
            return ToolResult(ok=False, output=(
                f"error: {path} is too large for this route (encoded audio exceeds {limit_mb:g} MB)"))

        if ctx.dry_run:
            return rehearsed(
                f"transcribe {resolved.name} ({len(audio):,} bytes, {audio_format}) with "
                f"{route.model} on connection {name}", _TRANSCRIBE_DECISION)

        book = ConnectionBook(ctx.config.state_dir)
        key = book.key(name)
        if not key:
            env = conn.api_key_env or "the connection's key"
            return ToolResult(ok=False, output=(
                f"error: connection {name!r} has no key. Set {env} in the environment that "
                f"starts hutch, or run `hutch connections set-key {name}`"))
        detail = {
            "connection": name,
            "provider": _provider_identity(conn),
            "endpoint": conn.base_url,
            "model": route.model,
            "language": language,
            "audio_bytes": len(audio),
            "format": audio_format,
            "billing": conn.billing,
            "note": "the audio leaves this machine; the provider's plan may charge for it",
        }
        try:
            ctx.gate.decide("audio_transcription",
                            f"transcribe {resolved.name} with {route.model} on {name}",
                            detail, _TRANSCRIBE_DECISION)
        except Exception as exc:  # noqa: BLE001 - denial and expiry both stop the call
            return ToolResult(ok=False, output=f"error: {exc}")
        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: the request was not started ({refusal})")

        transcriber = ChatAudioTranscriber(
            base_url=conn.base_url, api_key=key, route=route, provider_name=name,
            headers={"User-Agent": conn.user_agent, **conn.headers})
        try:
            result = transcriber.transcribe(audio, language=language, audio_format=audio_format)
        except ProviderError as exc:
            return ToolResult(ok=False, output=(
                f"error: transcription failed ({exc.kind}): {exc}\n"
                "Hutch did not retry, so this call was not sent twice."),
                data={"connection": name, "model": route.model, "error_kind": exc.kind})

        notes = list(result.notes)
        warning = _record_usage(ctx, conn, result)
        if warning:
            notes.append(warning)
        if conn.flat:
            notes.append(f"connection {name} bills in credits or a subscription, not per-token "
                         "currency; the token counts are not a price")
        else:
            notes.append("no reviewed price row was used, so the ledger records unpriced usage")
        if result.audio_seconds is not None:
            notes.append(f"the provider reported {result.audio_seconds:g}s of audio")
        if result.audio_tokens:
            notes.append(f"{result.audio_tokens} of the prompt tokens were audio input")

        transcript = clip(result.text, 200_000)
        usage_line = (f"{result.prompt_tokens} prompt / {result.completion_tokens} completion tokens"
                      if result.prompt_tokens or result.completion_tokens else "usage not reported")
        billing_line = "; plan bills in credits, not currency" if conn.flat else "; usage is unpriced"
        output = f"{transcript}\n\n[transcribed with {result.model} on {name}; {usage_line}{billing_line}]"
        return ToolResult(ok=True, output=output, data={
            "transcript": transcript,
            "connection": name,
            "provider": _provider_identity(conn),
            "model": result.model,
            "requested_model": result.requested_model,
            "language": language,
            "format": audio_format,
            "audio_bytes": len(audio),
            "audio_seconds": result.audio_seconds,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "audio_tokens": result.audio_tokens,
            "notes": notes,
        })
