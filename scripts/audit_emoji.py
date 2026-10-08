#!/usr/bin/env python3
"""hutch emoji-ban audit.

Zero pictographic emoji anywhere in tracked source; zero icon-like text
characters (arrows, geometric shapes, dingbats, technical symbols) in UI
surface files, where inline SVG icons are the only permitted iconography.

Two passes per line:
  1. EMOJI  — pictographic emoji and emoji presentation selectors, all files
  2. ICON   — icon-like text chars and HTML pictographic entities, UI files

UI surface files (anything under src/hutch/server/static/ or website/) are
held to both passes. Other tracked sources are held to pass 1 only, so
documentation may quote plain-text terminal glyphs (checkmarks, arrows) that
the CLI itself prints.

Improvements over the varve scripts/audit-emoji.mjs approach this is based on:
  - Python, matching this repo's toolchain (no Node runtime required)
  - HTML entities caught too (&check; &rarr; &#x1F4C1; &#128193; ...)
  - JS/Python escape sequences caught (see tests; spelled here only via a
    waiver so this docstring does not trip the audit itself)
  - Greppable inline waivers instead of hardcoded filename skips
  - Wired into pytest, so the default test run fails on violations

Run:  python scripts/audit_emoji.py          (exit 1 on violations)
      pytest tests/test_emoji_audit.py       (same gate via the test suite)

Waive a line with the marker `hutch-emoji-allow` (the waiver is counted in
the summary). Generated and vendored trees are skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Pass 1: pictographic emoji, scanned in every tracked file -------------
# High planes (Supplemental Symbols & Pictographs, Emoticons, Transport,
# CJK extras, EnclosedAlphanumericSupplement), the emoji presentation
# selector, and stray pictographs outside those planes. Deliberately NOT
# banned as "emoji": (c) (r) (tm) and plain-text dingbats in documentation —
# pass 2 is what holds the UI to SVG-only iconography.
EMOJI_CODEPOINTS: frozenset[int] = frozenset(
    [0xFE0F, 0x1F004, 0x1F0CF, 0x1F18E, 0x1F191, 0x1F19A]
    + list(range(0x1F0E0, 0x1F0FF + 1))
    + list(range(0x1F200, 0x1F2FF + 1))
    + list(range(0x1F300, 0x1FAFF + 1))
    + list(range(0x1FB00, 0x1FBFF + 1))
)

# --- Pass 2: icon-like text chars, UI surface files only --------------------
UI_DIRS = ("src/hutch/server/static/", "website/")

ICON_CODEPOINTS: frozenset[int] = frozenset(
    [0x00D7, 0x00F7]                       # multiplication / division sign
    + [0x2022, 0x25CF]                     # bullets used as icons
    + list(range(0x2190, 0x21FF + 1))      # arrows
    + list(range(0x2300, 0x23FF + 1))      # misc technical (gear, hourglass, eject)
    + list(range(0x2460, 0x24FF + 1))      # enclosed alphanumerics (circled digits)
    + list(range(0x25A0, 0x25FF + 1))      # geometric shapes (squares, triangles)
    + list(range(0x2600, 0x27BF + 1))      # misc symbols + dingbats (zap, check, x)
    + list(range(0x2B00, 0x2BFF + 1))      # misc symbols and arrows (stars)
    + list(range(0x1F100, 0x1F1FF + 1))    # enclosed alphanumerics supplement
)

# HTML entities that resolve to banned pictographs / icon chars.
ICON_ENTITIES = frozenset(
    """&check; &checkmark; &cross; &x; &zap; &rarr; &larr; &uarr; &darr;
    &leftrightarrow; &Rightarrow; &Leftarrow; &Updownarrow; &Rarr; &Larr;
    &rrarr; &llarr; &nharr; &nearr; &searr; &nwarr; &swarr; &times; &bigtimes;
    &starf; &star; &bigstar; &Sstar; &lozf; &blacktriangle;
    &blacktriangleright; &blacktriangleleft; &blacktriangledown;
    &blacksquare; &squf; &bull; &bullet; &circ; &diamond; &loz;""".split()
)

ENTITY_RE = re.compile(r"&(?:#x([0-9a-fA-F]+)|#([0-9]+)|([a-zA-Z][a-zA-Z0-9]*));")
ESCAPE_RE = re.compile(
    r"\\u\{([0-9a-fA-F]{1,6})\}|\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})"
)

ALL_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".css", ".html", ".htm", ".md", ".markdown",
    ".toml", ".cfg", ".ini", ".yml", ".yaml", ".json", ".svg", ".txt", ".sh",
    ".zsh", ".bash", ".just", ".astro", ".ts", ".tsx",
}

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dist", "build", ".zcode",
    ".v2c", ".video_agent", ".hutch", "test-results", "playwright-report",
    ".worktrees", ".zcodeignore-plans", ".superdesign", ".agents", ".codex",
    ".impeccable", ".opencode",
}

SKIP_FILES = {"uv.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}

WAIVER_MARKER = "hutch-emoji-allow"


def build_class(codepoints: frozenset[int]) -> re.Pattern[str]:
    parts = sorted(codepoints)
    spans: list[str] = []
    start = prev = parts[0]
    for cp in parts[1:]:
        if cp == prev + 1:
            prev = cp
            continue
        spans.append(_span(start, prev))
        start = prev = cp
    spans.append(_span(start, prev))
    return re.compile("[" + "".join(spans) + "]")


def _span(a: int, b: int) -> str:
    if a == b:
        return f"\\U{a:08X}"
    return f"\\U{a:08X}-\\U{b:08X}"


EMOJI_RE = build_class(EMOJI_CODEPOINTS)
ICON_RE = build_class(ICON_CODEPOINTS)


def is_ui_file(rel: str) -> bool:
    return any(rel.startswith(d) for d in UI_DIRS)


def iter_files(root: Path = ROOT) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix.lower() in ALL_EXTENSIONS:
            out.append(path)
    return out


def line_violations(line: str, ui: bool) -> list[str]:
    """Return violation labels for one line (first hit per category)."""
    found: list[str] = []

    def note(label: str) -> None:
        if not any(f.startswith(label) for f in found):
            found.append(label)

    if EMOJI_RE.search(line):
        note("EMOJI")
    cps = [int(next(g for g in m.groups() if g), 16) for m in ESCAPE_RE.finditer(line)]
    # Recombine UTF-16 surrogate pairs written as separate escapes
    # a surrogate pair written as two escapes is one emoji, not two plain codepoints.
    combined: list[int] = []
    i = 0
    while i < len(cps):
        if 0xD800 <= cps[i] <= 0xDBFF and i + 1 < len(cps) and 0xDC00 <= cps[i + 1] <= 0xDFFF:
            combined.append(0x10000 + ((cps[i] - 0xD800) << 10) + (cps[i + 1] - 0xDC00))
            i += 2
        else:
            combined.append(cps[i])
            i += 1
    for cp in combined:
        if cp in EMOJI_CODEPOINTS:
            note("EMOJI-ESCAPE")
        elif ui and cp in ICON_CODEPOINTS:
            note("ICON-ESCAPE")
    if ui:
        if ICON_RE.search(line):
            note("ICON")
        for m in ENTITY_RE.finditer(line):
            named, hexpart, decpart = m.group(3), m.group(1), m.group(2)
            if named and f"&{named.lower()};" in ICON_ENTITIES:
                note("ICON-ENTITY")
                continue
            cp = int(hexpart, 16) if hexpart else int(decpart) if decpart else None
            if cp is not None and (cp in EMOJI_CODEPOINTS or cp in ICON_CODEPOINTS):
                note("ICON-ENTITY")
    return found


def audit(root: Path = ROOT) -> tuple[list[str], int, int]:
    violations: list[str] = []
    waivers = 0
    files = iter_files(root)
    for path in files:
        rel = path.relative_to(root).as_posix()
        ui = is_ui_file(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            violations.append(f"READ:       {rel}: {exc}")
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if WAIVER_MARKER in line:
                waivers += 1
                continue
            for kind in line_violations(line, ui):
                violations.append(f"{kind:<11} {rel}:{i}: {line.strip()[:110]}")
    return violations, waivers, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="hutch emoji-ban audit")
    parser.add_argument("--root", type=Path, default=ROOT, help="scan root")
    args = parser.parse_args()

    violations, waivers, scanned = audit(args.root)
    if violations:
        print(f"audit:emoji — {len(violations)} violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nUI surfaces allow inline SVG icons only; everywhere else bans\n"
            f"pictographic emoji. Waive a deliberate case with `{WAIVER_MARKER}`\n"
            "in a comment on the line.",
            file=sys.stderr,
        )
        return 1
    print(f"audit:emoji — clean (scanned {scanned} files, {waivers} waiver(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
