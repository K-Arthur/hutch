"""Explicit channel connections into Hutch's existing conversation/run engine.

Channel input never carries approval authority. Transport receipts describe
delivery, separately from tool-action receipts and the agent's completion text.
"""

CONTRACT_VERSION = 1


class ChannelError(ValueError):
    """An operator-facing error that must not contain credentials or payloads."""


class ChannelConflict(ChannelError):
    """A stale configuration or reused transport identity was refused."""
