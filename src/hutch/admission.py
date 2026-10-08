"""One Hutch local-inference caller, with eight waiting callers, across processes.

Kernel file locks carry ownership, so SIGKILL releases both a call and its queue
ticket. Ticket files are never unlinked/replaced while locks may reference their
inodes. This controls Hutch callers, not unrelated clients of a model server.
"""
from __future__ import annotations

import json
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

WAITING_LIMIT = 8


class AdmissionError(RuntimeError):
    pass


class QueueFull(AdmissionError):
    pass


class AdmissionCancelled(AdmissionError):
    pass


def _open(directory: int, name: str) -> int:
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        os.close(fd)
        raise AdmissionError("inference lock files must be owned regular files with one link")
    return fd


def _write(fd: int, ticket: dict) -> None:
    data = json.dumps(ticket, sort_keys=True).encode()
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    while data:
        written = os.write(fd, data)
        data = data[written:]


def _read(fd: int) -> dict:
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        ticket = json.loads(os.read(fd, 4096))
        if (not isinstance(ticket.get("order"), int) or ticket["order"] < 0 or type(ticket.get("active")) is not bool
                or not isinstance(ticket.get("run_id"), str)):
            raise ValueError("invalid ticket")
        return ticket
    except (ValueError, AttributeError) as exc:
        raise AdmissionError("an owned inference ticket is unreadable; wait for its owner to exit") from exc


@contextmanager
def inference_slot(state_dir: Path, run_id: str, model: str, stop: Callable[[], bool],
                   on_wait: Callable[[int], None] | None = None) -> Iterator[None]:
    """FIFO admission per call; release before tool execution or a human wait.

    on_wait receives the current one-based queue position. Unknown occupied
    tickets fail closed. The queue and slot cannot be widened through an env flag.
    """
    import fcntl

    path = state_dir / "inference"
    path.mkdir(mode=0o700, exist_ok=True)
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    gate = active = seat = None

    def check_stop():
        if stop():
            raise AdmissionCancelled("run stopped while waiting for local inference")

    @contextmanager
    def locked_gate():
        while True:
            check_stop()
            try:
                fcntl.flock(gate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(gate, fcntl.LOCK_UN)

    try:
        gate = _open(directory, "queue.lock")
        active = _open(directory, "active.lock")
        with locked_gate():
            for index in range(WAITING_LIMIT + 1):
                candidate = _open(directory, f"ticket-{index}.lock")
                try:
                    fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(candidate)
                    continue
                seat = candidate
                ticket = {"run_id": run_id, "model": model, "order": time.monotonic_ns(), "active": False}
                _write(seat, ticket)
                break
            if seat is None:
                raise QueueFull("local inference queue is full: one caller and eight waiting; retry after a call finishes")
        last_position = None
        while True:
            acquired = False
            with locked_gate():
                waiting = []
                for index in range(WAITING_LIMIT + 1):
                    candidate = _open(directory, f"ticket-{index}.lock")
                    try:
                        try:
                            fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            owned = _read(candidate)
                            if not owned["active"]:
                                waiting.append((owned["order"], index, owned["run_id"]))
                    finally:
                        os.close(candidate)
                waiting.sort()
                position = next(i + 1 for i, item in enumerate(waiting) if item[2] == run_id and item[0] == ticket["order"])
                if position == 1:
                    try:
                        fcntl.flock(active, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        ticket["active"] = True
                        _write(seat, ticket)
                        acquired = True
            if acquired:
                break
            if position != last_position and on_wait is not None:
                on_wait(position)
            last_position = position
            time.sleep(0.05)
        check_stop()
        yield
    finally:
        for fd in (active, seat, gate, directory):
            if fd is not None:
                os.close(fd)
