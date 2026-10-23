"""Governed OpenCode V2 assistant runtime.

This replaces the previous fail-closed placeholder. It owns a private
``opencode serve`` process, uses the durable message endpoint rather than the
volatile event stream, brokers every permission prompt through Hutch's
approval gate (never ``always``), and records the provider-reported token and
cost totals against a usage reservation.

The runtime is still fail-closed: if the installed server cannot provide the
endpoints it needs, if a permission cannot be reviewed, if the process exits
mid-turn, or if an action may have started without a terminal receipt, the run
ends with an explicit failure or ``outcome_unknown`` rather than success.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..approvals import DeniedError
from ..connections import ConnectionBook
from ..context import prompt_tokens as estimate_prompt_tokens
from ..models import Event, EventType, Run, RunStatus
from ..providers.pricing import PriceBook
from ..safety import Decision, Verdict
from ..tools import Tool, ToolContext
from .base import RunAborted
from .ladder import SpendGuard, make_rung
from .opencode_protocol import OpenCodeProtocolError, parse_permission_request
from .opencode_server import OpenCodeModel, OpenCodeServer, OpenCodeServerError
from .steps import StepTimer, finish_step

_MAX_SESSION_MESSAGES = 200
_POLL_SECONDS = 0.35
_SAFE_READ_ACTIONS = {"read", "list", "grep", "glob", "find", "search"}
_OUTWARD_ACTIONS = {"webfetch", "websearch", "network", "fetch"}
_SESSION_LOCK = threading.Lock()


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)[:80].strip(".-") or "assistant"


def _session_dir(state_dir: Path) -> Path:
    path = Path(state_dir) / "opencode-sessions"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _load_mapping(state_dir: Path, conversation_id: str) -> dict[str, Any]:
    path = _session_dir(state_dir) / f"{hashlib.sha256(conversation_id.encode()).hexdigest()[:32]}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_mapping(state_dir: Path, conversation_id: str, value: dict[str, Any]) -> None:
    directory = _session_dir(state_dir)
    path = directory / f"{hashlib.sha256(conversation_id.encode()).hexdigest()[:32]}.json"
    temp = directory / f".{path.name}.{os.getpid()}.tmp"
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with _SESSION_LOCK:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def _model_ref(bot_model: str, models: list[OpenCodeModel]) -> tuple[str, str]:
    """Resolve ``opencode/<provider>/<model>`` or a direct provider/model spec."""
    spec = (bot_model or "").strip()
    if spec.startswith("opencode/"):
        rest = spec[len("opencode/"):]
        provider, sep, model = rest.partition("/")
        if sep and provider and model:
            return provider, model
    provider, sep, model = spec.partition("/")
    if sep and provider and model:
        return provider, model
    raise RunAborted("model_missing", "Choose an OpenCode model before starting this assistant.")


def _agent_definition(bot_id: str, *, title: str, instructions: str,
                      provider_id: str, model_id: str, tool_names: set[str],
                      workspace: str) -> tuple[str, dict[str, Any]]:
    """Return a stable agent ID and its V2 inline config.

    The V2 config schema uses an ``agents`` object with a ``system`` field.
    Writing Markdown files under an XDG agents directory is not equivalent in
    this release, so the profile config is generated atomically instead.

    OpenCode has its own tool names. The reviewed Hutch tool list decides
    which OpenCode capabilities are enabled: no `shell` means shell execution
    is denied, no file-writing tool means edit/write are denied, and no web
    tool means web access is denied. Read-only workspace inspection remains
    available. Tools Hutch cannot broker inside OpenCode (memory, browser,
    computer, delegation) are not silently offered.
    """
    agent_id = f"hutch-{_safe_component(bot_id)}"
    edit_allowed = bool(tool_names & {"write_file", "revise_document", "create_document",
                                      "create_media", "render_diagram", "run_python"})
    shell_allowed = "shell" in tool_names
    web_allowed = bool(tool_names & {"web_fetch", "live_search", "inspect_media"})
    deny = {"action": "external_directory", "resource": "*", "effect": "deny"}
    task_deny = {"action": "task", "resource": "*", "effect": "deny"}
    permissions = [
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "list", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "allow"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "edit", "resource": "*", "effect": "ask" if edit_allowed else "deny"},
        {"action": "write", "resource": "*", "effect": "ask" if edit_allowed else "deny"},
        # OpenCode releases differ on whether the shell action is named
        # "bash" or "shell"; cover both so neither can fall through to an
        # implicit allow.
        {"action": "bash", "resource": "*", "effect": "ask" if shell_allowed else "deny"},
        {"action": "shell", "resource": "*", "effect": "ask" if shell_allowed else "deny"},
        {"action": "webfetch", "resource": "*", "effect": "ask" if web_allowed else "deny"},
        {"action": "websearch", "resource": "*", "effect": "ask" if web_allowed else "deny"},
        deny, task_deny,
    ]
    return agent_id, {
        "description": title[:160],
        "mode": "primary",
        "model": f"{provider_id}/{model_id}",
        "system": (instructions.strip() or "You are a helpful personal assistant.")
                  + f"\n\nYour working folder is {workspace}. Stay inside it unless a reviewed action explicitly "
                    "allows another destination.",
        "permissions": permissions,
    }


def _permission_decision(action: str, resources: list[str],
                         ctx: ToolContext) -> tuple[Decision, bool, bool]:
    """Map an OpenCode permission to Hutch policy, review and auto behaviour.

    Returns ``(decision, outward, ask_in_auto)``. Shell commands are checked
    through the same policy engine as Hutch's shell tool, but they always
    require review even in Auto mode: OpenCode executes them outside the
    built-in OS sandbox. A hard policy denial is final and is never sent to
    the approval queue.
    """
    normalized = (action or "").strip().lower()
    if normalized in _SAFE_READ_ACTIONS:
        return Decision(Verdict.allow, "OpenCode read-only action", "opencode:read", risk="low"), False, False
    outward = normalized in _OUTWARD_ACTIONS
    if normalized in {"shell", "bash"}:
        checked = [ctx.policy.check_shell(command) for command in resources if command.strip()]
        denied = next((item for item in checked if item.verdict is Verdict.deny), None)
        if denied is not None:
            return Decision(Verdict.deny, denied.reason, denied.rule or "opencode:shell-deny",
                            risk="high", outward=denied.outward), True, True
        return (Decision(Verdict.ask,
                         "OpenCode shell runs outside Hutch's built-in sandbox; review the exact command",
                         "opencode:shell", risk="high", outward=any(item.outward for item in checked)),
                any(item.outward for item in checked), True)
    if normalized in {"external_directory", "task"}:
        return (Decision(Verdict.ask, f"OpenCode {normalized} action", f"opencode:{normalized}",
                         risk="high"), False, True)
    if normalized in {"edit", "write", "delete", "webfetch", "websearch"}:
        return Decision(Verdict.ask, f"OpenCode {normalized} action", f"opencode:{normalized}",
                        risk="high" if outward else "medium", outward=outward), outward, outward
    return Decision(Verdict.ask, f"OpenCode {normalized or 'unknown'} action", "opencode:unknown",
                    risk="high"), outward, True


def _tool_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            if isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif item.get("type") and item.get("type") != "text":
                parts.append(f"[{item.get('type')}]")
    return "".join(parts)


def _safe_args(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"redacted": True}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if str(key).lower() in {"content", "text", "oldstring", "newstring", "patch", "file"}:
            out[str(key)] = "[omitted]"
        elif isinstance(item, (str, int, float, bool)) or item is None:
            out[str(key)] = str(item)[:500] if isinstance(item, str) else item
        elif isinstance(item, list):
            out[str(key)] = [str(v)[:200] for v in item[:20]]
        elif isinstance(item, dict):
            out[str(key)] = _safe_args(item)
    return out


def _assistant_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _assistant_usage(message: dict[str, Any]) -> tuple[int, int, int, float]:
    tokens = message.get("tokens") if isinstance(message.get("tokens"), dict) else {}
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    cost = message.get("cost")
    try:
        cost_value = float(cost) if cost is not None else 0.0
    except (TypeError, ValueError):
        cost_value = 0.0
    return (int(tokens.get("input") or 0), int(tokens.get("output") or 0),
            int(cache.get("read") or 0), cost_value)


class OpenCodeRuntime:
    kind = "opencode"

    def __init__(self, binary: str = "opencode"):
        self.binary = binary

    # ------------------------------------------------------------------ helpers

    def _emit(self, ctx: ToolContext, run: Run, kind: str, note: str, **extra: Any) -> None:
        ctx.emit(Event(run_id=run.id, type=EventType.log, data={"kind": kind, "note": note, **extra}))

    def _prompt_text(self, ctx: ToolContext, run: Run, *, new_session: bool) -> str:
        current = run.prompt.strip()
        if new_session and run.conversation_id:
            rows = ctx.store.list_conversation_messages(run.conversation_id, limit=60)
            # The current request is already persisted as the last user
            # message. Remove only that exact tail so the new session does
            # not receive the request twice.
            for index in range(len(rows) - 1, -1, -1):
                row = rows[index]
                if row.get("role") == "user" and str(row.get("content") or "").strip() == current:
                    del rows[index]
                    break
            transcript: list[str] = []
            for row in rows:
                role = row.get("role")
                content = str(row.get("content") or "").strip()
                if role not in {"user", "assistant"} or not content:
                    continue
                transcript.append(f"{role.capitalize()}: {content[:4000]}")
            if transcript:
                return ("Conversation so far (for context; do not repeat it verbatim):\n\n"
                        + "\n\n".join(transcript[-40:])
                        + "\n\nCurrent request:\n" + current)
        return current

    def _session_for(self, server: OpenCodeServer, ctx: ToolContext, run: Run,
                     provider_id: str, model_id: str, agent_id: str) -> tuple[str, bool]:
        key = run.conversation_id or run.id
        saved = _load_mapping(ctx.config.state_dir, key)
        session_id = saved.get("session_id") if isinstance(saved.get("session_id"), str) else ""
        if session_id and saved.get("provider_id") == provider_id and saved.get("model_id") == model_id:
            try:
                info = server.session(session_id)
                if info.get("id") == session_id:
                    return session_id, False
            except OpenCodeServerError:
                pass
        created = server.create_session(
            workspace=ctx.workspace, title=run.conversation_id or run.id,
            provider_id=provider_id, model_id=model_id, agent=agent_id,
        )
        session_id = str(created["id"])
        _save_mapping(ctx.config.state_dir, key, {
            "session_id": session_id, "provider_id": provider_id, "model_id": model_id,
            "bot_id": ctx.bot.id, "updated_at": time.time(),
        })
        return session_id, True

    def _reserve(self, ctx: ToolContext, run: Run, prompt: str):
        bot = ctx.bot
        rung = make_rung(bot.model, "primary")
        guard = SpendGuard(ctx.store, bot, run, PriceBook(ctx.config.state_dir / "prices.json"),
                           ConnectionBook(ctx.config.state_dir))
        turn_cap = int(bot.limits.max_turn_tokens or 16_000)
        prompt_tokens = int(estimate_prompt_tokens([{"role": "user", "content": prompt}], [])[0])
        # OpenCode may issue several internal model calls for one prompt. Hold
        # a bounded continuation allowance (two tool turns plus the answer);
        # further actual usage is still recorded and reconciled separately.
        internal_turns = max(1, min(int(bot.limits.max_steps or 1), 3))
        refusal = guard.refusal(rung, prompt_tokens, turn_cap * internal_turns)
        if refusal:
            raise RunAborted("cost_cap" if "$" in refusal or "price" in refusal else "token_cap", refusal)
        try:
            reservation = guard.reserve(rung, prompt_tokens, turn_cap * internal_turns,
                                        route_hash=hashlib.sha256(
                                            f"{bot.model}\0{bot.workdir or ''}".encode()).hexdigest(),
                                        request_hash=hashlib.sha256(prompt.encode()).hexdigest())
        except Exception as exc:
            from ..store import UsageBudgetRefusal, UsagePauseRequired
            if isinstance(exc, (UsageBudgetRefusal, UsagePauseRequired)):
                raise RunAborted("token_cap", str(exc)) from exc
            raise
        return reservation, prompt_tokens

    def _broker_permissions(self, server: OpenCodeServer, session_id: str, ctx: ToolContext, run: Run,
                            handled: set[str]) -> None:
        try:
            pending = server.permissions(session_id)
        except OpenCodeServerError:
            if ctx.closed or ctx.gate.cancelled():
                raise RunAborted("stopped", "OpenCode stopped before its permissions could be reconciled")
            raise
        for raw in pending:
            request_id = raw.get("id")
            if not isinstance(request_id, str) or not request_id or request_id in handled:
                continue
            try:
                parsed = parse_permission_request(raw)
            except OpenCodeProtocolError as exc:
                # Never leave an unparseable request pending: reject it, keep
                # the session moving, and make the reason visible.
                server.reply_permission(session_id, request_id, "reject",
                                        f"Hutch could not review this request: {exc}"[:400])
                handled.add(request_id)
                self._emit(ctx, run, "opencode", f"permission rejected as unreadable: {exc}", ok=False)
                continue
            if parsed["session_id"] != session_id:
                server.reply_permission(session_id, request_id, "reject",
                                        "Hutch rejected a permission from another session"[:400])
                handled.add(request_id)
                self._emit(ctx, run, "opencode", "permission rejected: session identity mismatch", ok=False)
                continue
            action = parsed["action"]
            resources = list(parsed["resources"])
            decision, outward, ask_in_auto = _permission_decision(action, resources, ctx)
            detail = {
                "action": action, "resources": resources[:20], "session_id": session_id,
                "message": parsed.get("message", ""), "source": parsed.get("source"),
                "metadata": parsed.get("metadata", {}),
                "what_is_sent": ("this action runs in the assistant's working folder; an outward action may send "
                                 "data off this machine" if outward else
                                 "this action runs in the assistant's working folder"),
            }
            try:
                ctx.gate.decide("opencode", f"OpenCode {action}", detail, decision,
                                outward=outward, ask_in_auto=ask_in_auto)
            except DeniedError as exc:
                server.reply_permission(session_id, request_id, "reject", str(exc)[:400])
                handled.add(request_id)
                self._emit(ctx, run, "opencode", f"permission rejected: {action}", ok=False)
                continue
            server.reply_permission(session_id, request_id, "once")
            handled.add(request_id)
            self._emit(ctx, run, "opencode", f"permission approved once: {action}", ok=True)

    def _emit_tools(self, ctx: ToolContext, run: Run, message: dict[str, Any],
                    seen: dict[str, str]) -> None:
        for block in message.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool":
                continue
            call_id = str(block.get("id") or "")
            name = str(block.get("name") or "tool")
            state = block.get("state") if isinstance(block.get("state"), dict) else {}
            status = str(state.get("status") or "streaming")
            previous = seen.get(call_id)
            if status in {"running", "completed", "error"} and previous not in {"running", "completed", "error"}:
                ctx.emit(Event(run_id=run.id, type=EventType.tool_call,
                               data={"tool": f"opencode:{name}", "args": _safe_args(state.get("input"))}))
            if status == "completed" and previous != "completed":
                text = _tool_text(state.get("content")) or "(completed without text output)"
                ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                               data={"tool": f"opencode:{name}", "ok": True, "output": text[:12_000]}))
            elif status == "error" and previous != "error":
                error = state.get("error") if isinstance(state.get("error"), dict) else {}
                text = str(error.get("message") or "the tool failed")[:12_000]
                ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                               data={"tool": f"opencode:{name}", "ok": False, "output": text}))
            seen[call_id] = status

    # ------------------------------------------------------------------- execute

    def execute(self, run: Run, ctx: ToolContext, tools: dict[str, Tool],
                stop: Callable[[], bool]) -> str:
        del tools  # OpenCode executes its own tools; Hutch brokers every permission and observes results.
        if stop() or ctx.gate.cancelled():
            raise RunAborted("stopped", "run stopped before OpenCode started")
        provider_id, model_id = _model_ref(ctx.bot.model, [])
        from ..tools import expand_tools
        reviewed_tools = set(expand_tools(list(ctx.bot.tools)))
        agent_id, agent = _agent_definition(ctx.bot.id, title=ctx.bot.name,
                                            instructions=ctx.bot.instructions,
                                            provider_id=provider_id, model_id=model_id,
                                            tool_names=reviewed_tools, workspace=str(ctx.workspace))
        server = OpenCodeServer(ctx.config.state_dir, executable=self.binary, cwd=ctx.workspace,
                                agents={agent_id: agent})
        process = None
        try:
            try:
                server.start()
            except OpenCodeServerError as exc:
                raise RunAborted("unavailable", f"OpenCode could not start: {exc}") from exc
            except Exception as exc:
                from ..code_handoff import CodeHandoffError
                if isinstance(exc, CodeHandoffError):
                    raise RunAborted("unavailable", f"OpenCode's private profile is unsafe or unreadable: {exc}") from exc
                raise
            process = server.process
            if process is not None:
                ctx.procs.register(process, "opencode")
            models = server.models(ctx.workspace)
            if models and not any(m.provider_id == provider_id and m.model_id == model_id for m in models):
                raise RunAborted("model_missing",
                                 f"OpenCode does not list {provider_id}/{model_id}. Reconnect the provider or "
                                 "choose one of its listed models.")
            session_id, new_session = self._session_for(server, ctx, run, provider_id, model_id, agent_id)
            self._emit(ctx, run, "opencode", f"session {session_id} on {provider_id}/{model_id}",
                       session_id=session_id, new_session=new_session)
            prompt = self._prompt_text(ctx, run, new_session=new_session)
            if not prompt.strip():
                raise RunAborted("empty", "there is no request to send to OpenCode")

            reservation, prompt_tokens = self._reserve(ctx, run, prompt)
            before = {str(m.get("id")) for m in server.messages(session_id) if isinstance(m, dict)}
            if stop() or ctx.gate.cancelled():
                ctx.store.release_usage_reservation(reservation.id, "stopped before OpenCode accepted the prompt",
                                                    expected_fence=run.fence)
                raise RunAborted("stopped", "run stopped before OpenCode accepted the prompt")
            try:
                admitted = server.prompt(session_id, prompt)
            except OpenCodeServerError as exc:
                ctx.store.release_usage_reservation(reservation.id, "OpenCode rejected the prompt before dispatch",
                                                    expected_fence=run.fence)
                raise RunAborted("error", f"OpenCode did not accept the request: {exc}") from exc
            if not ctx.store.start_usage_request(reservation.id, expected_fence=run.fence):
                raise RunAborted("usage_reservation", "this OpenCode reservation was already used")

            seen_tools: dict[str, str] = {}
            handled_permissions: set[str] = set()
            accounted: set[str] = set()
            first_accounting = True
            last_finish = ""
            reported_any_usage = False
            timer = StepTimer()
            while True:
                if stop() or ctx.gate.cancelled():
                    try:
                        server.interrupt(session_id)
                    except OpenCodeServerError:
                        pass
                    if not accounted:
                        ctx.store.mark_usage_uncertain(
                            reservation.id, "OpenCode was interrupted after the prompt was admitted",
                            expected_fence=run.fence)
                    running = any(state == "running" for state in seen_tools.values())
                    if running:
                        raise RunAborted(
                            "outcome_unknown",
                            "OpenCode was stopped while a tool was running; the action may have completed. "
                            "Check the working folder and the OpenCode session before retrying. Usage remains "
                            "reserved as uncertain")
                    raise RunAborted("stopped", "stopped by user")
                try:
                    self._broker_permissions(server, session_id, ctx, run, handled_permissions)
                    rows = server.messages(session_id)
                    session_info = server.session(session_id)
                except OpenCodeServerError as exc:
                    if ctx.closed or ctx.gate.cancelled():
                        running = any(state == "running" for state in seen_tools.values())
                        if running:
                            raise RunAborted(
                                "outcome_unknown",
                                "OpenCode became unreachable while a tool was running; the action may have "
                                "completed. Check the working folder before retrying") from exc
                        raise RunAborted("stopped", "OpenCode stopped while the run was ending") from exc
                    ctx.store.mark_usage_uncertain(
                        reservation.id, f"OpenCode became unreadable after the prompt was admitted: {exc}"[:500],
                        expected_fence=run.fence)
                    raise RunAborted("outcome_unknown",
                                     f"OpenCode became unreachable after accepting the request ({exc}); "
                                     "its actions and charges may have continued. Check the OpenCode session "
                                     "before retrying") from exc

                new_messages = [m for m in rows if isinstance(m, dict) and str(m.get("id")) not in before]
                for message in new_messages:
                    if message.get("type") != "assistant":
                        continue
                    message_id = str(message.get("id") or "")
                    self._emit_tools(ctx, run, message, seen_tools)
                    completed = isinstance(message.get("time"), dict) and bool(message["time"].get("completed"))
                    if not completed or message_id in accounted:
                        continue
                    accounted.add(message_id)
                    input_tokens, output_tokens, cached_tokens, cost = _assistant_usage(message)
                    if input_tokens or output_tokens:
                        reported_any_usage = True
                    if run.steps >= int(ctx.bot.limits.max_steps or 1):
                        try:
                            server.interrupt(session_id)
                        except OpenCodeServerError:
                            pass
                        raise RunAborted(
                            "steps_exceeded",
                            f"OpenCode reached this Bot's {ctx.bot.limits.max_steps}-step limit; no further "
                            "tool or model turn was started")
                    run.steps += 1
                    run.tokens += input_tokens + output_tokens
                    use_reservation = first_accounting and bool(input_tokens or output_tokens)
                    finish_step(
                        run, ctx, timer, model=ctx.bot.model, prompt_tokens=input_tokens,
                        completion_tokens=output_tokens, cached_tokens=cached_tokens,
                        cost_usd=cost, account_id="opencode",
                        reservation_id=reservation.id if use_reservation else None,
                        cost_source="provider" if cost else "unknown",
                        reported_cost_usd=cost if cost else None,
                    )
                    if use_reservation:
                        first_accounting = False
                    last_finish = str(message.get("finish") or "unknown")
                    text = _assistant_text(message)
                    # A tool-call turn is a continuation, not an answer.
                    if last_finish == "tool-calls":
                        continue
                    if last_finish == "length":
                        ctx.emit(Event(run_id=run.id, type=EventType.message,
                                       data={"role": "assistant", "content": text,
                                             "incomplete": True, "reason": "length"}))
                        raise RunAborted(
                            "length", "OpenCode stopped at the model's output limit before finishing; "
                                      "the partial text is kept, but the run is incomplete")
                    if last_finish == "content-filter":
                        raise RunAborted("refused", "OpenCode reported that the provider filtered the response")
                    if last_finish == "error":
                        error = message.get("error") if isinstance(message.get("error"), dict) else {}
                        raise RunAborted("error", f"OpenCode's model call failed: "
                                                  f"{str(error.get('message') or 'provider error')[:800]}")
                    if last_finish not in {"stop", "unknown"}:
                        raise RunAborted("incomplete", f"OpenCode ended with an unrecognised finish state: {last_finish}")
                    if not text.strip():
                        raise RunAborted("empty", "OpenCode completed without any user-visible text")
                    if first_accounting:
                        ctx.store.mark_usage_uncertain(
                            reservation.id, "OpenCode completed without reporting token usage",
                            expected_fence=run.fence)
                    ctx.emit(Event(run_id=run.id, type=EventType.message,
                                   data={"role": "assistant", "content": text}))
                    return text

                outcome = str(session_info.get("outcome") or "")
                if outcome in {"failed", "interrupted"}:
                    if outcome == "interrupted":
                        raise RunAborted("stopped", "OpenCode interrupted this session")
                    raise RunAborted("error", "OpenCode reported this session as failed")
                time.sleep(_POLL_SECONDS)
        except RunAborted:
            raise
        except OpenCodeServerError as exc:
            raise RunAborted("error", f"OpenCode failed: {exc}") from exc
        finally:
            if process is not None:
                try:
                    ctx.procs.terminate(process, grace=0.5)
                except Exception:
                    pass
                try:
                    ctx.procs.unregister(process)
                except Exception:
                    pass
            server.close()
