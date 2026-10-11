"""Fresh capability checks and the explicit workspace grant for isolated native apps."""
from __future__ import annotations

import os
from pathlib import Path
import stat

AUTHORITY_FIELDS = ("tools", "computer_apps", "local_dev_origins", "observation_to_hosted", "remote_computer_access",
                    "risk_tier", "approval_mode", "command_rules", "inference_mode", "paused")


def authority(ctx, surface):
    store = getattr(ctx, "store", None)
    if store is None:
        return  # driver-only harnesses have no persistent configuration
    try:
        bot = store.get_bot(ctx.bot.id)
    except Exception:
        raise ValueError("computer authority state is unavailable; stop and start a new authorized run") from None
    name = "computer" if surface == "desktop" else "browser"
    if bot is None or name not in bot.tools or any(getattr(bot, field) != getattr(ctx.bot, field) for field in AUTHORITY_FIELDS):
        raise ValueError("computer capability/configuration changed or was revoked; stop and start a new authorized run")


def workspace_grant(ctx):
    """Fail closed before GUI observation/input when the workspace contains policy-denied resources.

    The grant is this whole clean workspace, including new ordinary documents. The
    local owner must not add private material concurrently; this is no content classifier.
    """
    from ..safety import PolicyEngine
    policy = getattr(ctx, "policy", None) or PolicyEngine()
    root = Path(ctx.workspace)
    if root.is_symlink():
        raise ValueError("native workspace cannot be a symlink")
    root = root.resolve(strict=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    count, total = 0, 0

    def scan(fd, parts=()):
        nonlocal count, total
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                if count > 10000 or len(parts) > 16:
                    raise ValueError("native workspace inspection exceeds its 10000 entry / 16 level budget")
                path = "/".join((*parts, entry.name))
                decision = policy.check_path(path, root, write=False)
                if decision.verdict.value == "deny":
                    raise ValueError("native workspace contains a policy-denied resource; choose a clean workspace")
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, flags, dir_fd=fd)
                    try:
                        scan(child, (*parts, entry.name))
                    finally:
                        os.close(child)
                elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("native workspace may contain only regular files/directories, without links or devices")
                else:
                    total += info.st_size
                    if total > 128 * 1024 * 1024:
                        raise ValueError("native workspace exceeds its 128 MiB resource grant")

    fd = os.open(root, flags)
    try:
        scan(fd)
    finally:
        os.close(fd)
    return {"workspace": str(root), "scope": "whole clean workspace, including new ordinary documents",
            "entries": count, "bytes": total, "links": "denied", "known_credential_paths": "denied"}
