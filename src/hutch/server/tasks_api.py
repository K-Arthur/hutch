"""Coordinated workspace-task API: create (1-2 specialists), list, continue, redirect and stop-all.

Lives outside ``app.py`` (frozen for size); ``install_workspace_task_routes`` is called from there
with the shared request-identity helpers. Model ownership is per assignment: an explicit
``model_override`` is validated against that specialist's own policy, otherwise the specialist's
saved model is used. Neither choice grants tools, permissions or memory.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from .. import coordinator_redirect as redirect_ops
from .. import coordinator_tasks as ops
from ..engine import Engine
from ..models import Bot, Run, Task
from ..store import IdempotencyConflict
from .tasks_api_models import WorkspaceTaskCreate, WorkspaceTaskRedirect, WorkspaceTaskResource

_STATUS_FOR_VALUE_ERROR = 409


def _resolve_route(config: Any, store: Any, target: Bot, override: str) -> tuple[str, str]:
    """Return ``(model_source, override)`` after validating the route for this specialist."""
    from ..modelchoices import ModelNotUsable, validate_override
    chosen = override.strip()
    try:
        model = validate_override(config, store, target, chosen or target.model)
    except ModelNotUsable as exc:
        raise HTTPException(exc.status, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
    if not chosen:
        if model != target.model:
            raise HTTPException(409, "The specialist's configured model changed; review its settings and try again")
        return "specialist_default", ""
    return "assignment_override", model


def _build_assignment(store: Any, config: Any, target_id: str, brief: str, assumptions: str,
                      override: str) -> dict[str, Any]:
    target = store.get_bot(target_id)
    if target is None:
        raise HTTPException(404, "No such specialist Bot")
    source, model = _resolve_route(config, store, target, override)
    prompt = f"{brief}\n\nUser-reviewed assumptions and constraints:\n{assumptions}" if assumptions else brief
    snapshot = Engine.capability_snapshot(target, integration_tools=store.integration_tool_names(target.id))
    return {"target_bot_id": target.id, "task_brief": brief, "capability_snapshot": snapshot,
            "run": Run(bot_id=target.id, prompt=prompt, origin="workspace_task"),
            "task": Task(bot_id=target.id, kind="on_demand", prompt=prompt),
            "model_override": model, "model_source": source}


def _submit(store: Any, config: Any, body: WorkspaceTaskCreate, key: str, digest: str) -> None:
    store.assert_execution_ready()
    brief, assumptions = body.task_brief.strip(), body.assumptions.strip()
    primary = _build_assignment(store, config, body.target_bot_id, brief, assumptions, body.model_override)
    extras = [_build_assignment(store, config, item.target_bot_id, item.task_brief.strip(), assumptions,
                                item.model_override) for item in body.additional_assignments]
    ops.submit_workspace_task(
        store, parent_conversation_id=body.parent_conversation_id, source_run_id=body.source_run_id,
        source_user_message_id=body.source_user_message_id,
        source_assistant_message_id=body.source_assistant_message_id,
        target_bot_id=primary["target_bot_id"], task_brief=brief, assumptions=assumptions,
        run=primary["run"], task=primary["task"], capability_snapshot=primary["capability_snapshot"],
        idem_key=key, request_hash=digest, memory_fact_ids=body.memory_fact_ids,
        model_override=primary["model_override"], model_source=primary["model_source"],
        additional_assignments=extras)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "No such conversation, task or specialist Bot")
    return HTTPException(_STATUS_FOR_VALUE_ERROR, str(exc))


def _create_route(app: FastAPI, store: Any, config: Any, idem: Callable, digest_of: Callable) -> None:
    @app.post("/api/v1/workspace/tasks", response_model=WorkspaceTaskResource)
    def create_workspace_task(body: WorkspaceTaskCreate, request: Request, response: Response) -> dict:
        key, digest = idem(request), digest_of(body.model_dump())
        try:
            replay = ops.replay_task(store, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if replay is not None:
            response.status_code = 200
            return replay
        if store.get_conversation(body.parent_conversation_id) is None:
            raise HTTPException(404, "No such coordinator conversation")
        try:
            _submit(store, config, body, key, digest)
        except (IdempotencyConflict, KeyError, PermissionError, ValueError) as exc:
            raise _error(exc) from None
        response.status_code = 201
        result = ops.replay_task(store, idem_key=key, request_hash=digest)
        if result is None:
            raise HTTPException(500, "The task was admitted but its durable task record could not be read")
        return result


def _list_route(app: FastAPI, store: Any) -> None:
    @app.get("/api/v1/workspace/tasks", response_model=list[WorkspaceTaskResource])
    def list_workspace_tasks(conversation_id: str | None = None, limit: int = 100) -> list[dict]:
        if conversation_id is not None and store.get_conversation(conversation_id) is None:
            raise HTTPException(404, "No such coordinator conversation")
        return ops.list_tasks(store, conversation_id, limit=limit)


def _continue_route(app: FastAPI, store: Any, config: Any, idem: Callable, digest_of: Callable) -> None:
    @app.post("/api/v1/workspace/tasks/{task_id}/continue", response_model=WorkspaceTaskResource)
    def continue_workspace_task(task_id: str, request: Request, response: Response) -> dict:
        """Start a fresh attempt from a no-effect committed checkpoint; never resume an old worker."""
        key = idem(request)
        digest = digest_of({"command": "continue-safe-workspace-task", "task_id": task_id})
        try:
            replay = store.replay_workspace_task_continuation(idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if replay is not None:
            response.status_code = 200
            return _enriched(store, replay)
        candidate = store.workspace_task_continuation_candidate(task_id)
        if not candidate["available"]:
            missing = candidate["reason"] == "This task is no longer available."
            raise HTTPException(404 if missing else 409, candidate["reason"])
        target = store.get_bot(candidate["target_bot_id"])
        if target is None:
            raise HTTPException(404, "The specialist Bot is no longer available")
        store.assert_execution_ready()
        _resolve_route(config, store, target, "")
        run, task = Run(bot_id=target.id, prompt="", origin="workspace_task"), Task(bot_id=target.id, kind="on_demand", prompt="")
        try:
            _, created = store.continue_workspace_task(
                task_id, run=run, task=task, idem_key=key, request_hash=digest,
                capability_snapshot=Engine.capability_snapshot(target, integration_tools=store.integration_tool_names(target.id)))
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, "The specialist task is no longer available") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        result = store.replay_workspace_task_continuation(idem_key=key, request_hash=digest)
        if result is None:
            raise HTTPException(500, "The continuation was admitted but its durable task record could not be read")
        return _enriched(store, result)


def _enriched(store: Any, task: dict) -> dict:
    ops.enrich_workspace_tasks(store, [task])
    return task


def _control_routes(app: FastAPI, store: Any, engine: Any, idem: Callable, digest_of: Callable) -> None:
    @app.post("/api/v1/workspace/tasks/{task_id}/redirect", response_model=WorkspaceTaskResource)
    def redirect_workspace_task(task_id: str, body: WorkspaceTaskRedirect, request: Request,
                                response: Response) -> dict:
        """Revise the brief: stops active work, bumps the brief revision, starts a fresh run."""
        key, digest = idem(request), digest_of({"task_id": task_id, **body.model_dump()})
        try:
            task, created = redirect_ops.redirect_workspace_task(
                store, engine, task_id, task_brief=body.task_brief, assumptions=body.assumptions,
                idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except (KeyError, PermissionError, ValueError) as exc:
            raise _error(exc) from None
        response.status_code = 201 if created else 200
        return task

    @app.post("/api/v1/workspace/tasks/{task_id}/stop-all", response_model=list[WorkspaceTaskResource])
    def stop_all_workspace_task_runs(task_id: str, request: Request, response: Response) -> list[dict]:
        """Stop every active run across all assignments in this task's plan."""
        key, digest = idem(request), digest_of({"command": "stop-all", "task_id": task_id})
        try:
            tasks, created = redirect_ops.stop_workspace_task_group(
                store, engine, task_id, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError as exc:
            raise _error(exc) from None
        response.status_code = 200
        return tasks


def install_workspace_task_routes(app: FastAPI, store: Any, engine: Any, config: Any, *,
                                  idempotency_key: Callable, request_digest: Callable) -> None:
    _list_route(app, store)
    _create_route(app, store, config, idempotency_key, request_digest)
    _continue_route(app, store, config, idempotency_key, request_digest)
    _control_routes(app, store, engine, idempotency_key, request_digest)

