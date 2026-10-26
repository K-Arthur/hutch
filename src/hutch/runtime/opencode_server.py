"""Owned, fail-closed client for the OpenCode V2 HTTP server.

Hutch starts a private ``opencode serve`` process with its own isolated
profile. No shared background service is used, ambient provider credentials
are removed from the environment, and the server password stays in memory.

The volatile SSE stream is deliberately not the source of truth. This client
reads session messages and permission requests through the durable HTTP
endpoints, so a dropped client can reconcile after reconnecting.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import select
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..code_handoff import safe_opencode_environment, write_profile_config

def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class OpenCodeServerError(RuntimeError):
    """The private OpenCode server could not start or rejected a request."""

    def __init__(self, message: str, *, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body[:2000]


@dataclass(frozen=True)
class OpenCodeModel:
    provider_id: str
    model_id: str
    name: str
    context: int = 0
    output: int = 0
    capabilities: tuple[str, ...] = ()
    input_modalities: tuple[str, ...] = ()    # from OpenCode's `capabilities.input`; includes "image" for vision models

    @property
    def spec(self) -> str:
        return f"opencode/{self.provider_id}/{self.model_id}"


RUNTIME_CONTROL_VERSION = 1
_MAINTENANCE_AGENTS = ('title', 'summary', 'compaction')


def _write_runtime_config(state_dir: Path, agents: dict[str, Any],
                          plugins: Optional[list[Any]] = None) -> Path:
    """Write the private runtime config containing this assistant's agent."""
    from ..code_handoff import opencode_profile_paths
    paths = opencode_profile_paths(state_dir)
    # Each owned server watches its configuration. Sharing a filename lets a
    # second Bot replace the first Bot's agent, route and run-bound bridge.
    path = paths["root"] / f"runtime-config-{secrets.token_hex(16)}.json"
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "update": "disable",
        "compaction": {"auto": False},
        "warming": False,
        "mcp": {},
        "plugins": list(plugins or []),
        "agents": {**agents, **{name: {"disabled": True} for name in _MAINTENANCE_AGENTS}},
    }
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path


class OpenCodeServer:
    """One private OpenCode server, owned by a Hutch run or a setup check."""

    def __init__(self, state_dir: Path, *, executable: Optional[str] = None,
                 cwd: Optional[Path] = None, startup_timeout: float = 20.0,
                 agents: Optional[dict[str, Any]] = None,
                 plugins: Optional[list[Any]] = None):
        self.state_dir = Path(state_dir)
        self.executable = executable or "opencode"
        self.cwd = Path(cwd) if cwd is not None else None
        self.startup_timeout = startup_timeout
        self.agents = agents or {}
        self.plugins = list(plugins or [])
        self.process: Optional[subprocess.Popen] = None
        self.base_url = ""
        self._password = ""
        self._client = None
        self._stderr: list[str] = []
        self._runtime_config: Optional[Path] = None

    # ---------------------------------------------------------------- lifecycle

    def __enter__(self) -> "OpenCodeServer":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @staticmethod
    def _version_major(executable: str, *, env: Optional[dict[str, str]] = None) -> int:
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                    timeout=5, check=False, env=env,
                                    cwd=env.get("HOME") if env else None)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OpenCodeServerError("OpenCode CLI could not be checked; install or repair it") from exc
        text = (result.stdout + "\n" + result.stderr).strip()
        match = re.search(r"\bv?(\d+)\.\d+\.\d+", text)
        if result.returncode != 0 or match is None:
            raise OpenCodeServerError("OpenCode CLI did not report a usable version; install OpenCode V2")
        return int(match.group(1))

    def start(self) -> None:
        if self.process is not None:
            return
        config_path = (write_profile_config(self.state_dir) if not self.agents
                       else _write_runtime_config(self.state_dir, self.agents, self.plugins))
        self._runtime_config = config_path if self.agents else None
        try:
            self._start(config_path)
        except BaseException:
            self.close()
            raise

    def _start(self, config_path: Path) -> None:
        env = safe_opencode_environment(config_path, state_dir=self.state_dir)
        if self._version_major(self.executable, env=env) < 2:
            raise OpenCodeServerError(
                "Hutch requires OpenCode V2. The installed CLI is OpenCode V1; update it from "
                "https://opencode.ai before connecting the assistant.")
        # The coding-handoff profile disables catalog fetches so an interactive
        # task never changes account state. A connected assistant must be able
        # to read the models this profile is actually authorised to use.
        env.pop("OPENCODE_DISABLE_MODELS_FETCH", None)
        port = _free_loopback_port()
        self.base_url = f"http://127.0.0.1:{port}"
        self._password = secrets.token_urlsafe(32)
        env["OPENCODE_SERVER_PASSWORD"] = self._password
        cwd = self.cwd or Path(env["HOME"])
        try:
            self.process = subprocess.Popen(
                [self.executable, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True,
            )
        except OSError as exc:
            raise OpenCodeServerError("OpenCode could not be started; check that the CLI is installed") from exc
        self._wait_ready()
        if self.agents:
            self._verify_runtime_controls(config_path, cwd)

    def _verify_runtime_controls(self, config_path: Path, workspace: Path) -> None:
        """Read-only preflight; unknown controls cannot precede a paid prompt.

        Agent lists omit hidden maintenance agents. Check their explicit lookup
        contracts and the location's loaded configuration instead.
        """
        message = "OpenCode maintenance generation controls could not be verified; no model request was sent"
        params = {"location[directory]": str(workspace)}
        try:
            # Agent/config endpoints can expose partial startup state. Model
            # discovery has a documented plugin-activation barrier; it performs
            # no inference and must settle before checking effective controls.
            readiness = self._get_with_params('/api/model', params, timeout=5.0)
            if not isinstance(readiness, dict) or not isinstance(readiness.get('data'), list):
                raise ValueError('plugin activation did not settle')
            entries = self._get_with_params('/api/config', params, timeout=5.0)
            if not isinstance(entries, list):
                raise ValueError('unreadable configuration list')
            own_index = next(index for index, entry in enumerate(entries)
                             if isinstance(entry, dict) and entry.get('type') == 'document'
                             and entry.get('path') == str(config_path))
            own = entries[own_index].get('info')
            if not isinstance(own, dict) or own.get('update') != 'disable':
                raise ValueError('runtime configuration not loaded')
            if own.get('warming') is not False:
                raise ValueError('background warming not disabled')
            compaction = own.get('compaction')
            if not isinstance(compaction, dict) or compaction.get('auto') is not False:
                raise ValueError('automatic compaction not disabled')
            definitions = own.get('agents')
            if not isinstance(definitions, dict) or any(
                    not isinstance(definitions.get(name), dict) or definitions[name].get('disabled') is not True
                    for name in _MAINTENANCE_AGENTS):
                raise ValueError('maintenance agent not disabled')
            for entry in entries[own_index + 1:]:
                info = entry.get('info') if isinstance(entry, dict) else None
                if not isinstance(info, dict):
                    continue  # directory-discovered agents are also checked by lookup below
                if 'update' in info and info['update'] != 'disable':
                    raise ValueError('later update override')
                if 'warming' in info and info['warming'] is not False:
                    raise ValueError('later warming override')
                if 'compaction' in info:
                    compact = info['compaction']
                    if not isinstance(compact, dict) or ('auto' in compact and compact['auto'] is not False):
                        raise ValueError('later compaction override')
                later = info.get('agents', {})
                if not isinstance(later, dict) or any(
                        name in later and (not isinstance(later[name], dict) or later[name].get('disabled') is not True)
                        for name in _MAINTENANCE_AGENTS):
                    raise ValueError('later maintenance override')
            for name in _MAINTENANCE_AGENTS:
                try:
                    self._get_with_params('/api/agent/' + name, params, timeout=5.0)
                except OpenCodeServerError as error:
                    body = json.loads(error.body)
                    if (error.status == 404 and isinstance(body, dict)
                            and body.get('_tag') == 'AgentNotFoundError' and body.get('agentID') == name):
                        continue
                    raise ValueError('unverified agent lookup') from None
                raise ValueError('maintenance agent still registered')
        except (OpenCodeServerError, ValueError, StopIteration, TypeError, KeyError):
            raise OpenCodeServerError(message) from None

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last = ""
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise OpenCodeServerError(f"OpenCode exited before it was ready: {self._stderr_text()}")
            try:
                self.request("GET", "/api/info", timeout=2.0)
                return
            except OpenCodeServerError as exc:
                last = str(exc)
                time.sleep(0.2)
        raise OpenCodeServerError(f"OpenCode did not become ready: {last or 'no response'}")

    def _drain_stderr(self) -> None:
        """Read whatever stderr is available without blocking the caller."""
        assert self.process is not None and self.process.stderr is not None
        fd = self.process.stderr.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                return
            line = self.process.stderr.readline()
            if not line:
                return
            text = line.strip()
            if text:
                self._stderr.append(text[-500:])
                del self._stderr[:-30]

    def _stderr_text(self) -> str:
        self._drain_stderr()
        return " | ".join(self._stderr[-3:])[:800]

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                except OSError:
                    pass
            except OSError:
                pass
        if process is not None:
            try:
                process.stderr.close()
            except Exception:
                pass
        config, self._runtime_config = self._runtime_config, None
        if config is not None:
            try:
                config.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------- HTTP

    def _http(self):
        if self._client is None:
            import httpx
            token = base64.b64encode(f"opencode:{self._password}".encode()).decode()
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Basic {token}"},
                timeout=httpx.Timeout(connect=5.0, read=20.0, write=30.0, pool=5.0),
                trust_env=False,
            )
        return self._client

    def request(self, method: str, path: str, *, json_body: Any = None, timeout: float = 20.0) -> Any:
        self._drain_stderr()
        try:
            response = self._http().request(method, path, json=json_body, timeout=timeout)
        except Exception as exc:
            raise OpenCodeServerError(f"OpenCode request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            body = response.text
            detail = body.strip()[:800] or f"HTTP {response.status_code}"
            raise OpenCodeServerError(
                f"OpenCode rejected {method} {path}: {detail}", status=response.status_code, body=body)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise OpenCodeServerError(f"OpenCode returned invalid JSON for {path}") from exc

    # --------------------------------------------------------------- operations

    def info(self) -> dict[str, Any]:
        value = self.request("GET", "/api/info")
        return value if isinstance(value, dict) else {}

    def integrations(self) -> list[dict[str, Any]]:
        value = self.request("GET", "/api/integration")
        rows = value.get("data") if isinstance(value, dict) else None
        return [row for row in rows or [] if isinstance(row, dict)]

    def models(self, directory: Optional[Path] = None) -> list[OpenCodeModel]:
        params = {"location[directory]": str(directory)} if directory is not None else None
        value = self.request("GET", "/api/model", timeout=30.0) if params is None else \
            self._get_with_params("/api/model", params)
        rows = value.get("data") if isinstance(value, dict) else None
        out: list[OpenCodeModel] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            provider_id, model_id = row.get("providerID"), row.get("modelID") or row.get("id")
            if not isinstance(provider_id, str) or not isinstance(model_id, str):
                continue
            limit = row.get("limit") if isinstance(row.get("limit"), dict) else {}
            capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
            raw_modalities = capabilities.get("input") if isinstance(capabilities.get("input"), list) else ()
            input_modalities = tuple(sorted({str(item).lower() for item in raw_modalities
                                             if isinstance(item, str)}))
            out.append(OpenCodeModel(
                provider_id=provider_id, model_id=model_id,
                name=str(row.get("name") or model_id)[:160],
                context=int(limit.get("context") or 0), output=int(limit.get("output") or 0),
                capabilities=tuple(sorted(k for k, v in capabilities.items() if v is True)),
                input_modalities=input_modalities,
            ))
        return out

    def _get_with_params(self, path: str, params: dict[str, str], *, timeout: float = 20.0) -> Any:
        try:
            response = self._http().get(path, params=params, timeout=timeout)
        except Exception as exc:
            raise OpenCodeServerError(f"OpenCode request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise OpenCodeServerError(f"OpenCode rejected GET {path}: {response.text[:800]}",
                                      status=response.status_code, body=response.text)
        try:
            return response.json()
        except ValueError as exc:
            raise OpenCodeServerError(f"OpenCode returned invalid JSON for {path}") from exc

    def create_session(self, *, workspace: Path, title: str, provider_id: str, model_id: str,
                       agent: str = "", permissions: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "title": title[:200],
            "model": {"providerID": provider_id, "id": model_id},
            "location": {"directory": str(workspace)},
        }
        if agent:
            body["agent"] = agent
        if permissions:
            body["permissions"] = permissions
        value = self.request("POST", "/api/session", json_body=body, timeout=30.0)
        data = value.get("data") if isinstance(value, dict) else None
        if not isinstance(data, dict) or not data.get("id"):
            raise OpenCodeServerError("OpenCode created no readable session")
        return data

    def prompt(self, session_id: str, text: str, *, message_id: str = "",
               files: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if message_id:
            body["id"] = message_id
        if files:
            # V2 PromptInput.FileAttachment: {uri, name} references the model
            # actually receives when its input modalities include images.
            body["files"] = files
        value = self.request("POST", f"/api/session/{session_id}/prompt", json_body=body, timeout=30.0)
        data = value.get("data") if isinstance(value, dict) else None
        if not isinstance(data, dict):
            raise OpenCodeServerError("OpenCode did not admit the prompt")
        return data

    def messages(self, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        # Ask for the newest page, then restore chronological order for the
        # caller. An ascending limit would pin long sessions to their oldest
        # messages and hide the reply that just arrived.
        value = self._get_with_params(f"/api/session/{session_id}/message",
                                      {"order": "desc", "limit": str(max(1, min(limit, 500)))})
        rows = value.get("data") if isinstance(value, dict) else None
        return [row for row in reversed(rows or []) if isinstance(row, dict)]

    def session(self, session_id: str) -> dict[str, Any]:
        value = self.request("GET", f"/api/session/{session_id}")
        data = value.get("data") if isinstance(value, dict) else None
        return data if isinstance(data, dict) else {}

    def interrupt(self, session_id: str) -> None:
        self.request("POST", f"/api/session/{session_id}/interrupt?resume=false", json_body={}, timeout=10.0)

    def permissions(self, session_id: str) -> list[dict[str, Any]]:
        value = self.request("GET", f"/api/session/{session_id}/permission", timeout=10.0)
        rows = value.get("data") if isinstance(value, dict) else value
        return [row for row in rows or [] if isinstance(row, dict)]

    def reply_permission(self, session_id: str, request_id: str, decision: str, message: str = "") -> None:
        if decision not in ("once", "reject"):
            raise ValueError("Hutch never emits a persistent OpenCode permission grant")
        body: dict[str, Any] = {"decision": decision}
        if message:
            body["message"] = message[:500]
        self.request("POST", f"/api/session/{session_id}/permission/{request_id}/reply",
                     json_body=body, timeout=10.0)

    def connect_key(self, integration_id: str, key: str, *, label: str = "") -> None:
        body: dict[str, Any] = {"key": key}
        if label:
            body["label"] = label[:80]
        self.request("POST", f"/api/integration/{integration_id}/connect/key",
                     json_body=body, timeout=30.0)

    def start_oauth(self, integration_id: str, method_id: str) -> dict[str, Any]:
        value = self.request("POST", f"/api/integration/{integration_id}/connect/oauth",
                             json_body={"methodID": method_id}, timeout=30.0)
        data = value.get("data") if isinstance(value, dict) else None
        return data if isinstance(data, dict) else {}

    def oauth_status(self, integration_id: str, attempt_id: str) -> dict[str, Any]:
        value = self.request("GET", f"/api/integration/{integration_id}/connect/oauth/{attempt_id}",
                             timeout=15.0)
        data = value.get("data") if isinstance(value, dict) else None
        return data if isinstance(data, dict) else {}

    def complete_oauth(self, integration_id: str, attempt_id: str, code: str = "") -> None:
        body: dict[str, Any] = {} if not code else {"code": code}
        self.request("POST", f"/api/integration/{integration_id}/connect/oauth/{attempt_id}/complete",
                     json_body=body, timeout=30.0)

    def cancel_oauth(self, integration_id: str, attempt_id: str) -> None:
        self.request("DELETE", f"/api/integration/{integration_id}/connect/oauth/{attempt_id}",
                     timeout=10.0)


def status_summary(server: OpenCodeServer, *, workspace: Optional[Path] = None) -> dict[str, Any]:
    """Non-secret setup state for the dashboard. Never returns credentials."""
    info = server.info()
    integrations = server.integrations()
    models = server.models(workspace)
    rows = []
    for integration in integrations:
        methods = [m for m in integration.get("methods") or [] if isinstance(m, dict)]
        connections = [c for c in integration.get("connections") or [] if isinstance(c, dict)]
        rows.append({
            "id": str(integration.get("id") or "")[:100],
            "name": str(integration.get("name") or integration.get("id") or "")[:100],
            "connected": bool(connections),
            "methods": [{"id": str(m.get("id") or ""), "type": str(m.get("type") or ""),
                         "label": str(m.get("label") or "")[:120]} for m in methods],
            "connections": [{"id": str(c.get("id") or "")[:100], "label": str(c.get("label") or "")[:100]}
                            for c in connections],
        })
    return {
        "version": str(info.get("version") or ""),
        "integrations": rows,
        "models": [{"spec": m.spec, "provider_id": m.provider_id, "model_id": m.model_id,
                    "name": m.name, "context": m.context, "output": m.output,
                    "capabilities": list(m.capabilities)} for m in models],
        "authenticated": any(row["connected"] for row in rows),
        # Free OpenCode models are usable without a saved provider account;
        # readiness means the profile exposed at least one selectable model.
        "ready": bool(models),
    }
