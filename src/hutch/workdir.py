"""A bot's optional working folder: a real directory on this machine that the bot works in, run after run.

Without one, every run gets a fresh empty workspace, so a bot can never see your files: "sort my Downloads" or "read the
CSVs in this folder" cannot work. With one, the run's workspace *is* that folder, and the existing jail applies to it: file
tools resolve inside it, the shell starts in it, a path that escapes it is denied.

Because the folder is yours and live, the choice is validated hard: it must exist, be readable, and not be a place where
giving an agent write access would be a mistake (the system directories, your whole home, or Hutch's own state, which holds
transcripts, memory and keys). It is re-validated at the start of every run, and a folder that has gone missing fails the run
with a clear message; it is never created for you.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

#: never a working folder, nor anything inside them
_FORBIDDEN_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot", "/dev", "/proc", "/sys", "/run",
                    "/snap", "/root")


def validate_workdir(raw: str, state_dir: Path) -> Path:
    """The resolved folder, or ValueError saying exactly what is wrong."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("a working folder needs a path")
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        raise ValueError(f"'{raw}' is not an absolute path: write the full path, for example ~/Downloads")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError(f"'{raw}' does not exist. Create the folder first: Hutch will not create it for you") from None
    if not resolved.is_dir():
        raise ValueError(f"'{raw}' is not a folder")
    if not os.access(resolved, os.R_OK | os.X_OK):
        raise ValueError(f"'{raw}' is not readable by this user")
    if resolved == Path("/") or resolved == Path(resolved.anchor):
        raise ValueError("the whole disk cannot be a working folder")
    for root in _FORBIDDEN_ROOTS:
        r = Path(root)
        if resolved == r or r in resolved.parents:
            raise ValueError(f"{resolved} is inside {root}, a system location: choose a folder of your own")
    home = Path.home().resolve()
    if resolved == home:
        raise ValueError("your whole home folder is too broad: choose a folder inside it, such as ~/Downloads")
    if resolved in home.parents:
        raise ValueError(f"{resolved} contains your home folder, which is too broad")
    state = state_dir.resolve()
    if resolved == state or state in resolved.parents or resolved in state.parents:
        raise ValueError("a working folder cannot contain or sit inside Hutch's own state folder "
                         "(it holds transcripts, memory and keys)")
    from .safety import _SECRET_RE
    if _SECRET_RE.search(str(resolved)):
        raise ValueError(f"{resolved} looks like a credentials location: bots may never work there")
    return resolved


def check_workdir_at_run(workdir: Optional[str], state_dir: Path) -> Optional[str]:
    """Why a configured folder cannot be used right now (None when fine or not configured)."""
    if not workdir:
        return None
    try:
        validate_workdir(workdir, state_dir)
    except ValueError as exc:
        return f"working folder {workdir}: {exc}"
    return None
