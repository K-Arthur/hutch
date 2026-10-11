"""Plan executors for Google Workspace operations.

Binds action-plan steps to :class:`~hutch.gsuite.client.GoogleWorkspaceClient` calls and
translates each result into an :class:`~hutch.actions.execute.ExecutorResult`: the client's
``verification`` list decides success (a write that landed but read back wrong is a
failure with its remote id preserved).

Executors are keyed by ``(kind, service)`` where a kind covers several services —
``cloud_create`` exists for docs, sheets and drive.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable, Optional

from ..actions.execute import Executor, ExecutorResult
from ..actions.plan import ActionPlan, PlanStep
from .client import GoogleWorkspaceClient, GoogleWorkspaceError, GoogleWorkspaceOutcomeUnknown
from . import requests as ws

MAX_LOCAL_UPLOAD = ws.MAX_UPLOAD_BYTES


def _fail(error: str, *, uncertain: bool = False, remote_id: str = "") -> ExecutorResult:
    return ExecutorResult(ok=False, error=error, uncertain=uncertain, remote_id=remote_id)


def _account(step: PlanStep) -> str:
    account = step.target.account
    if not account:
        raise GoogleWorkspaceError(
            f"step {step.id} has no Workspace account; choose the connection in the plan review")
    return account


def _columns(spec: list[dict[str, Any]]) -> list[ws.ColumnSpec]:
    out = []
    for column in spec:
        out.append(ws.ColumnSpec(name=str(column.get("name", "column")),
                                 kind=str(column.get("kind", "text"))))
    return out


def workspace_executors(client: GoogleWorkspaceClient, *,
                        read_local_file: Optional[Callable[[str], bytes]] = None) -> dict[Any, Executor]:
    """Executor map for docs/sheets/drive plan steps.

    ``read_local_file`` reads the bytes for a Drive upload step; it defaults to reading the
    validated path in the step inputs directly (the caller supplies a path it already owns).
    """

    def _read(path_value: str) -> bytes:
        if read_local_file is not None:
            return read_local_file(path_value)
        path = Path(path_value)
        data = path.read_bytes()
        if len(data) > MAX_LOCAL_UPLOAD:
            raise GoogleWorkspaceError(f"{path.name} exceeds the single-upload limit")
        return data

    def create_docs(step: PlanStep, plan: ActionPlan) -> ExecutorResult:
        inputs = step.inputs
        try:
            result = client.create_document(
                _account(step), title=str(inputs.get("title") or step.title),
                body_text=str(inputs.get("body_text") or ""),
                parent_folder_id=step.target.parent_id,
            )
        except GoogleWorkspaceOutcomeUnknown as exc:
            return _fail(str(exc), uncertain=True)
        except GoogleWorkspaceError as exc:
            return _fail(str(exc))
        return ExecutorResult(ok=True, remote_id=result["document_id"], result=result,
                              verification=result.get("verification") or [])

    def create_sheets(step: PlanStep, plan: ActionPlan) -> ExecutorResult:
        inputs = step.inputs
        try:
            result = client.create_spreadsheet(
                _account(step), title=str(inputs.get("title") or step.title),
                sheet_titles=[str(t) for t in inputs.get("sheet_titles") or ["Sheet1"]],
                parent_folder_id=step.target.parent_id,
                hutch_key=str(inputs.get("hutch_key") or ""),
            )
        except GoogleWorkspaceOutcomeUnknown as exc:
            return _fail(str(exc), uncertain=True)
        except GoogleWorkspaceError as exc:
            return _fail(str(exc))
        return ExecutorResult(ok=True, remote_id=result["spreadsheet_id"], result=result,
                              verification=result.get("verification") or [])

    def upload_drive(step: PlanStep, plan: ActionPlan) -> ExecutorResult:
        inputs = step.inputs
        name = str(inputs.get("name") or step.title)
        mime_type = str(inputs.get("mime_type") or "application/octet-stream")
        try:
            if "content_text" in inputs:
                content = str(inputs["content_text"]).encode("utf-8")
            elif "content_b64" in inputs:
                content = base64.b64decode(str(inputs["content_b64"]), validate=True)
            elif "local_path" in inputs:
                content = _read(str(inputs["local_path"]))
            else:
                return _fail("the upload step has no content (content_text/content_b64/local_path)")
            if not step.target.parent_id:
                return _fail("the upload step needs an explicit destination folder id")
            result = client.upload_file(
                _account(step), name=name, parent_id=step.target.parent_id, content=content,
                mime_type=mime_type, app_properties={"hutch_upload": "1"},
            )
        except (GoogleWorkspaceOutcomeUnknown,) as exc:
            return _fail(str(exc), uncertain=True)
        except (GoogleWorkspaceError, OSError, ValueError) as exc:
            return _fail(str(exc))
        return ExecutorResult(ok=True, remote_id=result["file_id"], result=result,
                              verification=result.get("verification") or [])

    def append_rows(step: PlanStep, plan: ActionPlan) -> ExecutorResult:
        inputs = step.inputs
        spreadsheet_id = str(inputs.get("spreadsheet_id") or step.target.resource_id or "")
        if not spreadsheet_id:
            return _fail("the append step needs a spreadsheet id")
        try:
            result = client.append_rows(
                _account(step), spreadsheet_id,
                columns=_columns(inputs.get("columns") or []),
                rows=list(inputs.get("rows") or []),
                sheet_id=inputs.get("sheet_id"),
                title=str(inputs.get("sheet_title") or ""),
                range_start=str(inputs.get("range_start") or "A1"),
            )
        except GoogleWorkspaceOutcomeUnknown as exc:
            return _fail(str(exc), uncertain=True)
        except GoogleWorkspaceError as exc:
            return _fail(str(exc))
        problems = list(result.get("verification") or [])
        return ExecutorResult(ok=True, remote_id=spreadsheet_id, result=result,
                              verification=problems)

    def update_docs(step: PlanStep, plan: ActionPlan) -> ExecutorResult:
        inputs = step.inputs
        document_id = str(inputs.get("document_id") or step.target.resource_id or "")
        requests = list(inputs.get("requests") or [])
        if not document_id or not requests:
            return _fail("the Docs update step needs a document id and requests")
        try:
            result = client.batch_update_document(
                _account(step), document_id, requests,
                required_revision_id=str(inputs.get("required_revision_id") or ""))
        except GoogleWorkspaceOutcomeUnknown as exc:
            return _fail(str(exc), uncertain=True)
        except GoogleWorkspaceError as exc:
            return _fail(str(exc))
        return ExecutorResult(ok=True, remote_id=document_id, result={"replies": result.get("replies", [])})

    return {
        ("cloud_create", "docs"): create_docs,
        ("cloud_create", "sheets"): create_sheets,
        ("cloud_create", "drive"): upload_drive,
        ("cloud_edit", "sheets"): append_rows,
        ("cloud_edit", "docs"): update_docs,
    }
