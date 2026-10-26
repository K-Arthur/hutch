"""LockFileEx adapter; only imported on Windows. No plaintext lock metadata.

Only the acquire/shared/nonblocking/unlock subset used by Hutch is supported;
this does not emulate fcntl ioctls, mandatory-mode flags or lock upgrades.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import errno
import msvcrt

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_Overlapped)]
_kernel.LockFileEx.restype = wintypes.BOOL
_kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                wintypes.DWORD, ctypes.POINTER(_Overlapped)]
_kernel.UnlockFileEx.restype = wintypes.BOOL


def flock(fd, operation):
    if not isinstance(fd, int):
        fd = fd.fileno()
    if not isinstance(operation, int):
        raise TypeError("lock operation must be an integer")
    kind = operation & ~LOCK_NB
    if kind not in {LOCK_SH, LOCK_EX, LOCK_UN}:
        raise ValueError("unsupported file lock operation")
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
    state = _Overlapped()  # zero offset/event; do not move the caller's file pointer
    maximum = 0xFFFFFFFF
    if kind == LOCK_UN:
        ok = _kernel.UnlockFileEx(handle, 0, maximum, maximum, ctypes.byref(state))
        if not ok and ctypes.get_last_error() == 158:  # ERROR_NOT_LOCKED: same no-op as Unix unlock
            return
    else:
        flags = (2 if kind == LOCK_EX else 0) | (1 if operation & LOCK_NB else 0)
        ok = _kernel.LockFileEx(handle, flags, 0, maximum, maximum, ctypes.byref(state))
    if not ok:
        code = ctypes.get_last_error()
        if code == 33 and operation & LOCK_NB:  # ERROR_LOCK_VIOLATION
            raise BlockingIOError(errno.EAGAIN, "File is locked") from None
        raise ctypes.WinError(code)
