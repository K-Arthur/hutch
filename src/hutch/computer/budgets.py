"""Sampled browser resource watchdog; verified process identities, never another run's tree."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import threading

from .. import procguard

MAX_PROFILE_BYTES = 128 * 1024 * 1024
MAX_PROFILE_ENTRIES = 10000
MAX_BROWSER_RSS_BYTES = 1536 * 1024 * 1024


def profile_usage(path):
    total, count = 0, 0
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    def scan(fd, depth=0):
        nonlocal total, count
        if depth > 16:
            raise ValueError("browser profile exceeds its directory-depth budget")
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                if count > MAX_PROFILE_ENTRIES:
                    raise ValueError("browser profile exceeds its 10000 entry budget; stop and review its retained state")
                try:
                    info = entry.stat(follow_symlinks=False)
                    total += info.st_size if not stat.S_ISDIR(info.st_mode) else 0
                    if total > MAX_PROFILE_BYTES:
                        raise ValueError("browser profile exceeds its 128 MiB budget; stop and review its retained state")
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(entry.name, flags, dir_fd=fd)
                        try:
                            scan(child, depth + 1)
                        finally:
                            os.close(child)
                except FileNotFoundError:
                    continue  # Chromium may delete cache entries while sampling
    fd = os.open(path, flags)
    try:
        scan(fd)
    finally:
        os.close(fd)
    return {"bytes": total, "entries": count}


def browser_rss(roots):
    seen, total = set(), 0
    for root in roots:
        current = procguard.identity(root.pid)
        if current is None or current.starttime != root.starttime:
            continue
        for proc in [current, *procguard.descendants(root.pid)]:
            if proc.pid in seen:
                continue
            seen.add(proc.pid)
            try:
                for line in Path(f"/proc/{proc.pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1]) * 1024
                        break
            except (OSError, ValueError):
                pass
    return total


class BrowserBudget:
    """Two-second soft checks, with possible sampling overshoot; no hard memory isolation claim."""
    def __init__(self, profile, roots, check_authority, stop, *, surface="browser"):
        self.profile, self.roots, self.check_authority, self.stop = profile, tuple(roots), check_authority, stop
        self.surface = surface
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"hutch-{surface}-budget", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.closed.wait(2):
            try:
                self.check_authority()
                profile_usage(self.profile)
                if browser_rss(self.roots) > MAX_BROWSER_RSS_BYTES:
                    raise ValueError(f"{self.surface} process tree exceeds its sampled 1.5 GiB RSS budget")
            except (ValueError, OSError) as exc:
                if not self.closed.is_set():
                    self.stop(str(exc).replace("browser profile", f"{self.surface} retained state"))
                return

    def close(self):
        self.closed.set()
        if self.thread is not threading.current_thread():
            self.thread.join(3)
