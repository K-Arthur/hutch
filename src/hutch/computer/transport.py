"""Private Linux IPC from authenticated HTTP handlers to the owned run worker.

No TCP listener, pickle, durable input or frame spool. Pathname sockets are owner-only; peer credentials are checked on
both ends. Only four bounded RPC handlers run at once, independently of the driver thread and emergency-stop route.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import stat
import struct
import threading
from types import SimpleNamespace

REQUEST_LIMIT = 17_408
RESPONSE_LIMIT = 1_310_720


def _directory(config, create=False):
    path = config.state_dir / "human-channels"
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise OSError("human channel directory must be private and owned")
    return path, os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _name(run_id, fence, surface):
    return hashlib.sha256(f"{run_id}:{fence}:{surface}".encode()).hexdigest()[:24] + ".sock"


def _peer(sock):
    pid, uid, _gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != os.getuid():
        raise OSError("human channel peer is not the local owner")
    return pid


def _read(sock, limit):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(min(65536, size - len(data)))
            if not chunk:
                raise OSError("human channel disconnected")
            data.extend(chunk)
        return bytes(data)
    size = struct.unpack("!I", exact(4))[0]
    if not 0 < size <= limit:
        raise OSError("human channel payload exceeds its budget")
    value = json.loads(exact(size))
    if not isinstance(value, dict):
        raise OSError("invalid human channel envelope")
    return value


def _write(sock, value, limit):
    data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(data) > limit:
        raise OSError("human channel payload exceeds its budget")
    sock.sendall(struct.pack("!I", len(data)) + data)


class WorkerBridge:
    def __init__(self, session):
        self.session = session
        self.path, self.fd = _directory(session.ctx.config, create=True)
        self.name = _name(session.ctx.run.id, session.ctx.run.fence, session.surface)
        # /proc/self/fd keeps long configured state paths below sockaddr_un's pathname limit. It still resolves to a
        # real owner-only pathname socket; no abstract/public namespace or process-wide cwd change is used.
        self.address = f"/proc/self/fd/{self.fd}/{self.name}"
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._closed = threading.Event()
        self._slots = threading.BoundedSemaphore(4)
        self._clients = set()
        self._lock = threading.Lock()
        self.inode = None
        try:
            if len(list(self.path.iterdir())) >= 64:
                raise OSError("human channel directory is full; reconcile old stopped workers")
            self.socket.bind(self.address)  # never replace another worker's socket
            self.inode = os.stat(self.name, dir_fd=self.fd, follow_symlinks=False).st_ino
            os.chmod(self.name, 0o600, dir_fd=self.fd, follow_symlinks=False)
            self.socket.listen(4)
            self.socket.settimeout(0.25)
        except Exception:
            self.socket.close()
            if self.inode is not None:
                try:
                    if os.stat(self.name, dir_fd=self.fd, follow_symlinks=False).st_ino == self.inode:
                        os.unlink(self.name, dir_fd=self.fd)
                except FileNotFoundError:
                    pass
            os.close(self.fd)
            raise
        self.thread = threading.Thread(target=self._serve, name="hutch-human-ipc", daemon=True)
        self.thread.start()

    def _serve(self):
        while not self._closed.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                connection.close()
                continue
            with self._lock:
                if self._closed.is_set():
                    connection.close()
                    self._slots.release()
                    return
                self._clients.add(connection)
            threading.Thread(target=self._handle, args=(connection,), name="hutch-human-rpc", daemon=True).start()

    def _handle(self, connection):
        from .human import HumanError
        request = {}
        try:
            connection.settimeout(1)
            _peer(connection)
            request = _read(connection, REQUEST_LIMIT)
            connection.settimeout(9)
            operation, viewer = request.get("operation"), request.get("viewer", "")
            if operation == "public":
                answer = self.session.public()
            elif operation == "takeover":
                answer = self.session.takeover(viewer, auth_session=request.get("auth_session", ""))
            elif operation == "command":
                answer = self.session.command(viewer, request.get("body", {}))
            elif operation == "pixels":
                png = self.session.pixels(viewer, request.get("token", ""), request.get("generation"), request.get("frame_id", ""))
                answer = {"png": base64.b64encode(png).decode()}
            else:
                raise HumanError("unsupported human IPC command", 422)
            _write(connection, {"ok": True, "answer": answer}, RESPONSE_LIMIT)
        except Exception as exc:
            try:
                message = str(exc) if isinstance(exc, HumanError) else "human worker channel failed; inspect before retrying"
                _write(connection, {"ok": False, "message": message, "status": getattr(exc, "status", 409)}, RESPONSE_LIMIT)
            except OSError:
                pass
        finally:
            connection.close()
            request.clear()
            with self._lock:
                self._clients.discard(connection)
            self._slots.release()

    def close(self):
        self._closed.set()
        self.socket.close()
        with self._lock:
            for connection in self._clients:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
        try:
            if os.stat(self.name, dir_fd=self.fd, follow_symlinks=False).st_ino == self.inode:
                os.unlink(self.name, dir_fd=self.fd)
        except FileNotFoundError:
            pass
        os.close(self.fd)


class HumanProxy:
    def __init__(self, config, run_id, fence, surface):
        self.config, self.surface = config, surface
        self.ctx = SimpleNamespace(run=SimpleNamespace(fence=fence))
        self.name = _name(run_id, fence, surface)
        self._public = {}

    def _rpc(self, operation, **body):
        from .human import HumanError
        fd = None
        try:
            path, fd = _directory(self.config)
            info = os.stat(self.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise OSError("unsafe human channel socket")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(9)
                connection.connect(f"/proc/self/fd/{fd}/{self.name}")
                _peer(connection)
                _write(connection, {"operation": operation, **body}, REQUEST_LIMIT)
                result = _read(connection, RESPONSE_LIMIT)
            if not result.get("ok"):
                raise HumanError(result.get("message", "human channel failed"), result.get("status", 409))
            return result["answer"]
        except (OSError, ValueError, KeyError):
            raise HumanError("human worker unavailable or response uncertain; no command is retried", 409) from None
        finally:
            if fd is not None: os.close(fd)

    def public(self):
        from .human import HumanError
        try:
            return self._rpc("public")
        except HumanError:
            return {"surface": self.surface, "controller_present": False, "step_control": False,
                    "control": {"owner": "recovery_required", "reason": "worker channel unavailable; no input was sent"}}

    def takeover(self, viewer, authorized=None, auth_session=""):
        return self._rpc("takeover", viewer=viewer, auth_session=auth_session)

    def command(self, viewer, body):
        return self._rpc("command", viewer=viewer, body=body)

    def pixels(self, viewer, token, generation, frame_id):
        answer = self._rpc("pixels", viewer=viewer, token=token, generation=generation, frame_id=frame_id)
        return base64.b64decode(answer["png"], validate=True)


def discover(config, run_id, fence):
    from .human import HumanError
    result = []
    for surface in ("browser", "desktop"):
        proxy = HumanProxy(config, run_id, fence, surface)
        try:
            if proxy.public().get("step_control"):
                result.append(proxy)
        except HumanError:
            pass  # absent/stale/closed channels confer no control
    return result
