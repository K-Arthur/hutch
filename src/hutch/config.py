"""Application configuration and state-directory layout.

All hutch state lives under a single directory (default: ~/.local/state/hutch)
so it is easy to inspect, back up, or delete. Tests override it with the
HUTCH_STATE_DIR environment variable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "hutch"


def _default_state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / APP_NAME


@dataclass(frozen=True)
class hutchConfig:
    """Paths and defaults for one hutch installation."""

    state_dir: Path

    @property
    def db_path(self) -> Path:
        return self.state_dir / "hutch.db"

    @property
    def bots_dir(self) -> Path:
        return self.state_dir / "bots"

    @property
    def downloads_dir(self) -> Path:
        return self.state_dir / "downloads"

    def bot_dir(self, bot_name: str) -> Path:
        return self.bots_dir / bot_name

    def bot_profiles_dir(self, bot_name: str) -> Path:
        """Legacy name-scoped profile location, retained for manual migration only."""
        return self.bot_dir(bot_name) / "browser-profile"

    def browser_profile_dir(self, bot_id: str) -> Path:
        """Persistent account state follows immutable bot identity, never a recycled name."""
        if not re.fullmatch(r"bot_[0-9a-f]{12}", bot_id):
            raise ValueError("invalid bot identity for browser profile")
        root = self.state_dir / "browser-profiles"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(root, flags)
        try:
            for name in (bot_id, "browser-profile"):
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(name, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                os.fchmod(fd, 0o700)
        finally:
            os.close(fd)
        return root / bot_id / "browser-profile"

    def run_dir(self, bot_name: str, run_id: str) -> Path:
        return self.bot_dir(bot_name) / "runs" / run_id

    def workspace(self, bot_name: str, run_id: str) -> Path:
        return self.run_dir(bot_name, run_id) / "workspace"

    def ensure_run_workspace(self, bot_name: str, run_id: str) -> Path:
        """Create a private per-run workspace, even when this bot normally reuses a folder."""
        run_dir = self.run_dir(bot_name, run_id)
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise ValueError("the run directory is not a private directory")
        os.chmod(run_dir, 0o700)
        workspace = run_dir / "workspace"
        workspace.mkdir(exist_ok=True, mode=0o700)
        if workspace.is_symlink() or not workspace.is_dir():
            raise ValueError("the run workspace is not a private directory")
        os.chmod(workspace, 0o700)
        return workspace

    def managed_workspace_path(self, bot_id: str) -> Path:
        """Return the identity-scoped managed workspace path without creating it."""
        if not re.fullmatch(r"bot_[0-9a-f]{12}", bot_id):
            raise ValueError("invalid bot identity for managed workspace")
        return self.state_dir / "workspaces" / bot_id

    def ensure_managed_workspace(self, bot_id: str) -> Path:
        """Create or open a private per-bot folder without following a bot-folder symlink."""
        path = self.managed_workspace_path(bot_id)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(parent, flags)
        try:
            try:
                os.mkdir(path.name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
            workspace_fd = os.open(path.name, flags, dir_fd=parent_fd)
            try:
                os.fchmod(workspace_fd, 0o700)
            finally:
                os.close(workspace_fd)
        finally:
            os.close(parent_fd)
        os.chmod(parent, 0o700)
        return path

    def ensure(self) -> None:
        """Create the state directory PRIVATE (0700): it holds transcripts, memory and, optionally, API keys.
        An existing directory is left as the user made it (`hutch doctor` warns if it is open to others)."""
        fresh = not self.state_dir.exists()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if fresh:
            os.chmod(self.state_dir, 0o700)
        for path in (self.bots_dir, self.downloads_dir):
            path.mkdir(parents=True, exist_ok=True)

    # Defaults tuned from documented agent incidents (see docs/research/complaints.md):
    # runaway loops and silent over-spend are the two most common failures.
    default_max_steps: int = 24
    default_timeout_seconds: int = 900
    default_daily_token_cap: int = 200_000
    default_approval_ttl_seconds: int = 600  # unanswered approvals expire as DENIED


def get_config() -> hutchConfig:
    override = os.environ.get("HUTCH_STATE_DIR")
    return hutchConfig(state_dir=Path(override) if override else _default_state_dir())
