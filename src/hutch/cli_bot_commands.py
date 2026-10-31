"""Install every Bot subcommand group on the one shared ``bot_app``.

The Bot group is assembled from cohesive modules rather than one large command file:
``cli_facts`` (saved notes and purges), ``cli_bot_deletion`` (governed permanent removal) and
``cli_bot_lifecycle`` (archive and restore). This module is the single place that wires them, so
``cli.py`` keeps one import and one call regardless of how many groups exist.
"""
from __future__ import annotations

from .cli_bot_deletion import install_bot_data_commands
from .cli_bot_lifecycle import install_bot_lifecycle_commands


def install_bot_commands(bot_app, store_factory, require_bot, err, console) -> None:
    """Attach every Bot subcommand group to ``bot_app``."""
    install_bot_data_commands(bot_app, store_factory, require_bot, err, console)
    install_bot_lifecycle_commands(bot_app, store_factory, require_bot, err, console)
