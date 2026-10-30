"""Tiny plain-form reader shared by the server-rendered pages.

Every action is a plain HTML form that must work without JavaScript; this wrapper
turns an urlencoded body into last-value-wins fields plus checkbox flags.
"""

from __future__ import annotations


class Form:
    def __init__(self, data: dict[str, list[str]]):
        self._d = data

    def get(self, key: str, default: str = "") -> str:
        v = self._d.get(key)
        return v[-1] if v else default

    def getlist(self, key: str) -> list[str]:
        return list(self._d.get(key, []))

    def has(self, key: str) -> bool:
        return key in self._d

    def flag(self, key: str) -> bool:
        return self.get(key) in ("1", "on", "true", "yes")
