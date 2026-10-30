"""Static structure checks for hand-written stylesheets.

A missing closing brace silently re-scopes every rule that follows it: the
browser recovers at the end of the file and the styles look merely "not applied"
rather than broken. This checker strips comments and strings, then walks the
brace stack, naming each unclosed block and its line. Generated CSS is excluded:
the sources are the contract (AGENTS.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

SOURCE_PATTERNS = (
    "src/hutch/server/static/*.css",
    "src/hutch/web/styles/*.css",
    "app/src/*.css",
    "website/styles.css",
    "website/responsive.css",
)
EXCLUDED = {
    "src/hutch/server/static/ui.css",          # generated from app/src/input.css
    "src/hutch/server/static/model-switcher.css",  # generated
    "src/hutch/server/static/brand-tokens.css",    # generated token mirror
    "website/app.css",                          # generated
    "website/styles.min.css",                   # generated
    "website/tokens.css",                       # generated
}


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    message: str

    def as_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "message": self.message}


def _blank(match: re.Match) -> str:
    return "\n" * match.group(0).count("\n")


def strip_css(code: str) -> str:
    """Remove comments and string literals while preserving line numbers."""
    return STRING_RE.sub(_blank, COMMENT_RE.sub(_blank, code))


def _line_at(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def check_file(path: Path, relative: str) -> list[Problem]:
    """Return unclosed or extra brace problems in one stylesheet."""
    raw = path.read_text(encoding="utf-8")
    text = strip_css(raw)
    problems: list[Problem] = []
    stack: list[tuple[int, bool]] = []
    for index, char in enumerate(text):
        if char == "{":
            boundary = max(text.rfind("{", 0, index), text.rfind("}", 0, index))
            is_media = text.rfind("@media", 0, index) > boundary
            stack.append((index, is_media))
        elif char == "}":
            if not stack:
                problems.append(Problem(relative, _line_at(text, index),
                                        "extra closing brace"))
                break
            stack.pop()
    for index, is_media in stack:
        kind = "unclosed @media block" if is_media else "unclosed block"
        problems.append(Problem(relative, _line_at(text, index), kind))
    return problems


def check_repository(root: Path) -> list[Problem]:
    """Check every hand-written stylesheet in the repository."""
    problems: list[Problem] = []
    for pattern in SOURCE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            relative = path.relative_to(root).as_posix()
            if relative in EXCLUDED or "vendor" in path.parts:
                continue
            problems.extend(check_file(path, relative))
    return problems
