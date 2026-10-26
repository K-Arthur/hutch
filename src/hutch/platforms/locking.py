"""Whole-file locking used by migrations, credentials, transcripts and uploads.

Unix keeps its existing flock semantics. Windows uses native byte-range locks
over the full file range on synchronous CRT file handles. Locks are owned by
the open handle and released on close/process death; no PID lock files or
stale-owner guesses substitute for kernel exclusion.
"""
from __future__ import annotations

import os

CONTRACT_VERSION = 1

if os.name == "nt":
    from ._windows_lock import flock, LOCK_EX, LOCK_SH, LOCK_UN, LOCK_NB
    BACKEND = "windows-lockfileex"
else:
    from fcntl import flock, LOCK_EX, LOCK_SH, LOCK_UN, LOCK_NB
    BACKEND = "posix-flock"

__all__ = ["CONTRACT_VERSION", "BACKEND", "flock", "LOCK_EX", "LOCK_SH", "LOCK_UN", "LOCK_NB"]
