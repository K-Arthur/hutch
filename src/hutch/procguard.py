"""Find, end and VERIFY the end of the processes a run started (ADR-0004).

``Popen.terminate()`` on the direct child is not cancellation: the child's own children survive it, and a supervisor that did
not spawn a process (it was recovering a crashed owner) has no handle at all. So every process a run starts is recorded with an
identity (pid, process group, session, and start time from /proc), and ending a run ends everything reachable from those:
the members of each recorded process group, plus their descendants (which also catches a child that called ``setsid`` while its
parent is still alive). Success is *measured* (nothing alive afterwards), not assumed.

Honest limits: a process that detaches completely (double fork + ``setsid``, so it is re-parented to init and leaves the group)
is not reachable from outside. The only complete answer to that is a PID namespace, which the OS sandbox provides (ADR-0006).
Linux only (/proc); on other systems every function reports "cannot verify" rather than pretending.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

PROC = Path("/proc")


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    pgrp: int
    session: int
    starttime: int          # clock ticks since boot: unique together with the pid for the life of the boot
    state: str


def available() -> bool:
    return PROC.is_dir() and (PROC / "self" / "stat").exists()


def _read(pid: int) -> Optional[Proc]:
    try:
        raw = (PROC / str(pid) / "stat").read_text()
    except (OSError, ValueError):
        return None
    try:
        rest = raw.rsplit(") ", 1)[1].split()
        return Proc(pid=pid, state=rest[0], ppid=int(rest[1]), pgrp=int(rest[2]), session=int(rest[3]),
                    starttime=int(rest[19]))
    except (IndexError, ValueError):
        return None


def identity(pid: int) -> Optional[Proc]:
    """What this pid is right now, or None if it does not exist."""
    return _read(pid)


def _all() -> dict[int, Proc]:
    out: dict[int, Proc] = {}
    if not available():
        return out
    for entry in PROC.iterdir():
        if entry.name.isdigit():
            p = _read(int(entry.name))
            if p is not None:
                out[p.pid] = p
    return out


def _alive(p: Proc) -> bool:
    return p.state not in ("Z", "X")                 # a zombie is dead for our purposes (it only awaits its parent's wait())


def reachable(pgids: Iterable[int], not_before: int = 0, procs: Optional[dict[int, Proc]] = None) -> list[Proc]:
    """Live processes that belong to any of ``pgids`` (started at or after ``not_before``), plus all their descendants."""
    table = procs if procs is not None else _all()
    groups = set(pgids)
    found = {p.pid: p for p in table.values() if p.pgrp in groups and p.starttime >= not_before and _alive(p)}
    changed = True
    while changed:                                    # descendants: children of anything already found
        changed = False
        for p in table.values():
            if p.pid not in found and p.ppid in found and _alive(p):
                found[p.pid] = p
                changed = True
    return list(found.values())


def _signal(p: Proc, sig: int) -> None:
    try:
        os.kill(p.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def end_groups(pgids: Iterable[int], not_before: int = 0, term_grace: float = 2.0, kill_grace: float = 2.0) -> list[Proc]:
    """SIGTERM everything reachable from ``pgids``, wait, SIGKILL what remains, wait again.

    Returns the processes still alive afterwards (empty means verified gone). Signals go to individual pids, not
    ``killpg``, so a recycled process-group id cannot take down an unrelated group."""
    pgids = [g for g in pgids if g and g != os.getpgrp()]
    if not pgids or not available():
        return []
    for p in reachable(pgids, not_before):
        _signal(p, signal.SIGTERM)
    deadline = time.monotonic() + term_grace
    while time.monotonic() < deadline and reachable(pgids, not_before):
        time.sleep(0.05)
    left = reachable(pgids, not_before)
    for p in left:
        _signal(p, signal.SIGKILL)
    deadline = time.monotonic() + kill_grace
    while time.monotonic() < deadline and reachable(pgids, not_before):
        time.sleep(0.05)
    return reachable(pgids, not_before)


def describe(procs: Iterable[Proc]) -> str:
    out = []
    for p in procs:
        try:
            cmd = (PROC / str(p.pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            cmd = ""
        out.append(f"{p.pid} {cmd[:60]}".strip())
    return ", ".join(out)
