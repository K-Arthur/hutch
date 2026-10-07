"""Application configuration and state-directory layout.

All OpenBot state lives under a single directory (default: ~/.local/state/openbot)
so it is easy to inspect, back up, or delete. Tests override it with the
OPENBOT_STATE_DIR environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "openbot"


def _default_state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / APP_NAME


@dataclass(frozen=True)
class OpenBotConfig:
    """Paths and defaults for one OpenBot installation."""

    state_dir: Path

    @property
    def db_path(self) -> Path:
        return self.state_dir / "openbot.db"

    @property
    def bots_dir(self) -> Path:
        return self.state_dir / "bots"

    @property
    def downloads_dir(self) -> Path:
        return self.state_dir / "downloads"

    def bot_dir(self, bot_name: str) -> Path:
        return self.bots_dir / bot_name

    def bot_profiles_dir(self, bot_name: str) -> Path:
        """Per-bot persistent browser profiles (logins survive across runs)."""
        return self.bot_dir(bot_name) / "browser-profile"

    def run_dir(self, bot_name: str, run_id: str) -> Path:
        return self.bot_dir(bot_name) / "runs" / run_id

    def workspace(self, bot_name: str, run_id: str) -> Path:
        return self.run_dir(bot_name, run_id) / "workspace"

    def ensure(self) -> None:
        for path in (self.state_dir, self.bots_dir, self.downloads_dir):
            path.mkdir(parents=True, exist_ok=True)

    # Defaults tuned from documented agent incidents (see docs/research/complaints.md):
    # runaway loops and silent over-spend are the two most common failures.
    default_max_steps: int = 24
    default_timeout_seconds: int = 900
    default_daily_token_cap: int = 200_000
    default_approval_ttl_seconds: int = 600  # unanswered approvals expire as DENIED


def get_config() -> OpenBotConfig:
    override = os.environ.get("OPENBOT_STATE_DIR")
    return OpenBotConfig(state_dir=Path(override) if override else _default_state_dir())
