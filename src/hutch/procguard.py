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
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


def boot_id() -> str:
    """Stable identity for this kernel boot, paired with /proc start ticks."""
    try:
        return BOOT_ID.read_text().strip()
    except OSError:
        return ""


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


def pidfd_available() -> bool:
    """Whether this Python/kernel pair can safely signal verified identities."""
    return available() and hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal") and bool(boot_id())


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


def unverified_group(pgid: int, *, session_id: int | None = None) -> list[Proc]:
    """List possible members without signalling when no persisted group identity is available."""
    return [p for p in _all().values() if p.pgrp == pgid and (session_id is None or p.session == session_id)
            and _alive(p)]


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


def _signal_exact(p: Proc, sig: int, expected_boot: str) -> bool:
    """Signal one verified process with pidfd, never a numeric PID after an identity check race."""
    if not expected_boot or boot_id() != expected_boot or not hasattr(os, "pidfd_open") \
            or not hasattr(signal, "pidfd_send_signal"):
        return False
    try:
        fd = os.pidfd_open(p.pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    try:
        current = _read(p.pid)
        if (current is None or current.starttime != p.starttime or current.pgrp != p.pgrp
                or current.session != p.session):
            return False
        try:
            signal.pidfd_send_signal(fd, sig)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
    finally:
        os.close(fd)


def signal_exact(p: Proc, sig: int, expected_boot: str) -> bool:
    """Signal one previously inspected process through its pidfd identity."""
    return _signal_exact(p, sig, expected_boot)


def _group_snapshot(pgid: int, anchor_pid: int, anchor_start: int,
                    expected_session: int | None = None) -> Optional[list[Proc]]:
    """Return members only while the recorded process-group identity still matches.

    A new group reusing a numeric PGID must be led by the same numeric PID. If that PID now has a different start tick, this
    is a different group and must never be signalled.
    """
    anchor = _read(anchor_pid)
    if anchor is not None and (anchor.starttime != anchor_start or anchor.pgrp != pgid
                               or (expected_session is not None and anchor.session != expected_session)):
        return None
    table = _all()
    members = [p for p in table.values() if p.pgrp == pgid and p.starttime >= anchor_start
               and (expected_session is None or p.session == expected_session) and _alive(p)]
    if anchor is not None and anchor.pid not in {p.pid for p in members} and _alive(anchor):
        return None
    found = {p.pid: p for p in members}
    changed = True
    while changed:
        changed = False
        for p in table.values():
            if p.pid not in found and p.ppid in found and _alive(p):
                found[p.pid] = p
                changed = True
    return list(found.values())


def end_recorded(records: Iterable[dict], term_grace: float = 2.0, kill_grace: float = 2.0) -> list[Proc]:
    """End processes using persisted boot/PID/start and optional session identities, then verify each group is empty."""
    anchors: dict[int, tuple[int, int, str, int | None]] = {}
    unresolved: list[Proc] = []
    for row in records:
        pgid, pid = int(row.get("pgid", 0)), int(row.get("pid", 0))
        start, saved_boot = int(row.get("starttime", 0)), str(row.get("boot_id", ""))
        if not pgid or not pid or not start:
            continue
        if saved_boot and saved_boot != boot_id():  # every process from that boot is gone
            continue
        if not saved_boot:
            # Old rows did not store enough identity to signal safely. A missing PID is already clean; a live one is unresolved.
            cur = _read(pid)
            if cur is not None and cur.starttime == start:
                unresolved.append(cur)
            unresolved.extend(p for p in unverified_group(pgid) if p.pid != pid)
            continue
        old = anchors.get(pgid)
        if old is None or start < old[1]:
            raw_session = row.get("session")
            anchors[pgid] = (pid, start, saved_boot, int(raw_session) if raw_session is not None else None)

    def snapshot() -> tuple[list[Proc], list[Proc]]:
        found: dict[int, Proc] = {}
        unknown: list[Proc] = []
        for pgid, (pid, start, saved_boot, session_id) in anchors.items():
            members = _group_snapshot(pgid, pid, start, expected_session=session_id)
            if members is None:
                # The original leader PID was reused. Do not act on the numeric group.
                continue
            found.update((p.pid, p) for p in members)
        return list(found.values()), unresolved + unknown

    expected_boot = boot_id()
    current, unknown = snapshot()
    for p in current:
        _signal_exact(p, signal.SIGTERM, expected_boot)
    deadline = time.monotonic() + term_grace
    while time.monotonic() < deadline:
        current, _ = snapshot()
        if not current:
            break
        time.sleep(0.05)
    current, _ = snapshot()
    for p in current:
        _signal_exact(p, signal.SIGKILL, expected_boot)
    deadline = time.monotonic() + kill_grace
    while time.monotonic() < deadline:
        current, _ = snapshot()
        if not current:
            break
        time.sleep(0.05)
    current, _ = snapshot()
    return current + unknown


def end_groups(pgids: Iterable[int], not_before: int = 0, term_grace: float = 2.0, kill_grace: float = 2.0) -> list[Proc]:
    """SIGTERM everything reachable from ``pgids``, wait, SIGKILL what remains, wait again.

    Returns the processes still alive afterwards (empty means verified gone). Signals go to individual pids, not
    ``killpg``, so a recycled process-group id cannot take down an unrelated group."""
    pgids = [g for g in pgids if g and g != os.getpgrp()]
    if not pgids or not available():
        return []
    anchors = []
    for pgid in pgids:
        anchor = _read(pgid)
        if anchor is not None and anchor.pgrp == pgid and anchor.starttime >= not_before:
            anchors.append({"pid": pgid, "pgid": pgid, "starttime": anchor.starttime, "boot_id": boot_id(),
                            "session": anchor.session})
    return end_recorded(anchors, term_grace=term_grace, kill_grace=kill_grace)


def describe(procs: Iterable[Proc]) -> str:
    out = []
    for p in procs:
        try:
            cmd = (PROC / str(p.pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            cmd = ""
        out.append(f"{p.pid} {cmd[:60]}".strip())
    return ", ".join(out)


# ------------------------------------------------------------------ a process tree below one known process


def cmdline(pid: int) -> list[str]:
    """The argument vector of ``pid`` ([] if it is gone or unreadable)."""
    try:
        raw = (PROC / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def children(pid: int, table: Optional[dict[int, Proc]] = None) -> list[Proc]:
    """Live direct children of ``pid``."""
    table = table if table is not None else _all()
    return [p for p in table.values() if p.ppid == pid and _alive(p)]


def descendants(pid: int, table: Optional[dict[int, Proc]] = None) -> list[Proc]:
    """Live descendants of ``pid`` (children, grandchildren, ...), excluding ``pid`` itself."""
    table = table if table is not None else _all()
    found: dict[int, Proc] = {}
    frontier = {pid}
    while frontier:
        nxt = {p.pid for p in table.values() if p.ppid in frontier and p.pid not in found and _alive(p)}
        for child in nxt:
            found[child] = table[child]
        frontier = nxt
    return list(found.values())


def end_tree(root: Proc, term_grace: float = 1.0, kill_grace: float = 1.5) -> list[Proc]:
    """End ``root`` and everything below it, then VERIFY. Returns the processes still alive afterwards (empty = ended).

    Used for a helper this process spawned itself (a browser automation driver) that is not in its own process group, so group
    signalling would hit the supervisor too. Every signal goes through a pidfd after an identity check, so a recycled pid is
    never signalled.
    """
    expected_boot = boot_id()
    current = identity(root.pid)
    if current is None or current.starttime != root.starttime:
        return []                                        # already gone (or the pid was reused: not ours to signal)
    victims = {p.pid: p for p in descendants(root.pid)}
    victims[root.pid] = current

    def survivors() -> list[Proc]:
        out = []
        for p in victims.values():
            now = identity(p.pid)
            if now is not None and now.starttime == p.starttime and _alive(now):
                out.append(p)
        return out

    for sig, grace in ((signal.SIGTERM, term_grace), (signal.SIGKILL, kill_grace)):
        # descendants first and the root last, so a parent cannot respawn what we just ended
        for p in sorted(survivors(), key=lambda q: q.pid == root.pid):
            _signal_exact(p, sig, expected_boot)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not survivors():
                return []
            time.sleep(0.02)
        # descendants started during the grace period are part of the tree too
        for p in descendants(root.pid):
            victims.setdefault(p.pid, p)
    return survivors()
