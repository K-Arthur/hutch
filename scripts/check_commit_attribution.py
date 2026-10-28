#!/usr/bin/env python3
"""Reject AI attribution in commit messages.

This is the repository's commit-message gate. It is deliberately narrow: it
flags attribution syntax that names an AI tool, model, assistant or vendor and
leaves ordinary prose that discusses AI products alone. It also rejects
AI-keyed session trailers and trailer links to AI coding sessions.

Modes:
  --message-file PATH   check one candidate message (the commit-msg hook)
  --range BASE..HEAD    check every commit added in a revision range (CI)

Exit codes: 0 clean, 1 attribution found, 2 usage or git error.

Usage:
  python3 scripts/check_commit_attribution.py --message-file .git/COMMIT_EDITMSG
  python3 scripts/check_commit_attribution.py --range origin/main..main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

POLICY_PATH = "docs/commit-attribution-policy.md"

# AI tools, models, assistants and vendors that must never be named as a
# commit author, co-author or generated-by attribution. Only attribution
# syntax is checked against this list, never ordinary body prose.
AI_IDENTITY_RE = re.compile(
    r"\b(?:"
    r"claude|anthropic|opencode|openai|chatgpt|codex|copilot|cursor|windsurf|"
    r"devin|cognition|gemini|aider|codeium|tabnine|replit|gpt|"
    r"ai[-\s]assistant|ai[-\s]agent"
    r")\b"
    r"|\bsourcegraph\s+cody\b|\bamazon\s+q\b",
    re.IGNORECASE,
)

# Trailer keys that express attribution when their value names an AI identity.
# A human co-author, Signed-off-by, Reviewed-by or Tested-by is always allowed.
ATTRIBUTION_TRAILER_KEYS = frozenset(
    {
        "co-authored-by",
        "co-author",
        "assisted-by",
        "generated-by",
        "created-by",
        "written-by",
    }
)

# Session links emitted by AI coding tools, for example
# "Claude-Session: https://claude.ai/code/session_01...". Checking these only
# inside trailer lines keeps ordinary prose links to AI products allowed.
AI_SESSION_URL_RES = (
    re.compile(r"\bclaude\.ai/code/session", re.IGNORECASE),
    re.compile(r"\bchatgpt\.com/c/", re.IGNORECASE),
    re.compile(r"\bcursor\.com/[^\s]*session", re.IGNORECASE),
)

# A trailer starts at column zero: "Key: value" or "Key : value".
TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)[ \t]*:[ \t]*(.*)$")

# Signature lines: "Generated with Claude Code", "Created with Cursor",
# "Assisted by Devin", optionally prefixed by "This commit was" or "Auto-".
_THIS_COMMIT = r"(?:this\s+(?:commit|change|patch)\s+(?:was|is)\s+)?"
_ATTRIBUTION_VERB = r"(?:auto[-\s]?)?(?:generated|created|written|assisted|made)"
_SIGNATURE_RE = re.compile(
    rf"^{_THIS_COMMIT}{_ATTRIBUTION_VERB}(?:\s+(?:with|by|using|via))\b",
    re.IGNORECASE,
)
_EXPLICIT_AI_RE = re.compile(
    rf"^{_THIS_COMMIT}{_ATTRIBUTION_VERB}(?:\s+(?:with|by|using|via))?\s+"
    r"(?:an?\s+)?(?:ai|a\.i\.|artificial\s+intelligence|llm|"
    r"large\s+language\s+model|language\s+model)\b",
    re.IGNORECASE,
)
_AI_GENERATED_RE = re.compile(r"^(?:auto[-\s]?)?ai[-\s]generated\b", re.IGNORECASE)

# Markdown emphasis, bullets and emoji decorate some signatures; strip them
# before matching the leading verb. Whitespace is handled separately so an
# indented line is treated as prose or a quoted example, not a signature.
_LEADING_DECORATION_RE = re.compile(r"^[^A-Za-z0-9]+")

# How far after "Generated with" the tool name may appear; this keeps a
# signature line from matching an AI mention late in a long prose sentence.
SIGNATURE_NAME_WINDOW = 160

# git strips comment lines and the scissors block before creating a commit.
# The commit-msg hook runs first, so ignore the same lines here.
_SCISSORS_RE = re.compile(r"^# -{2,} >8 -{2,}")


@dataclass(frozen=True)
class Violation:
    """One attribution line found in a commit message."""

    line_number: int
    kind: str
    text: str


def find_violations(message: str, *, hook_cleanup: bool = False) -> list[Violation]:
    """Return attribution-syntax violations in one commit message."""
    violations: list[Violation] = []
    for number, raw in enumerate(message.splitlines(), start=1):
        line = raw.rstrip("\r")
        if hook_cleanup:
            if _SCISSORS_RE.match(line):
                break
            if line.lstrip().startswith("#"):
                continue
        if not line.strip():
            continue
        kind = _violation_kind(line)
        if kind is not None:
            violations.append(Violation(number, kind, line.strip()))
    return violations


def _violation_kind(line: str) -> str | None:
    """Classify one line as attribution syntax, or None when it is allowed."""
    trailer = TRAILER_RE.match(line)
    if trailer is not None:
        key_token = trailer.group(1)
        key = key_token.lower()
        value = trailer.group(2)
        if key in ATTRIBUTION_TRAILER_KEYS and AI_IDENTITY_RE.search(value):
            return f"AI attribution trailer ({key_token})"
        if AI_IDENTITY_RE.search(key_token):
            # e.g. "Claude-Session: ..." or "Anthropic-Session: ...".
            return f"AI attribution trailer ({key_token})"
        if any(pattern.search(value) for pattern in AI_SESSION_URL_RES):
            # e.g. "Session: https://claude.ai/code/session_01...".
            return f"AI session trailer ({key_token})"
        return None

    if line[:1] in (" ", "\t"):
        # Indented text is body prose or a quoted example, not a signature.
        return None

    candidate = _LEADING_DECORATION_RE.sub("", line)
    if _AI_GENERATED_RE.match(candidate):
        return "AI-generated signature"
    if _EXPLICIT_AI_RE.match(candidate):
        return "AI-generated signature"

    signature = _SIGNATURE_RE.match(candidate)
    if signature is not None:
        window = candidate[signature.end() : signature.end() + SIGNATURE_NAME_WINDOW]
        if AI_IDENTITY_RE.search(window):
            return "AI tool signature"
    return None


def _valid_range(spec: str) -> bool:
    """Accept BASE..HEAD only; reject symmetric ranges and option-like input."""
    if spec.count("..") != 1:
        return False
    base, head = spec.split("..")
    for part in (base, head):
        if not part or part.startswith((".", "-")) or part.endswith("."):
            return False
        if any(character.isspace() for character in part):
            return False
    return True


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError("git is not installed or not on PATH") from None


def _commits_in_range(range_spec: str) -> list[tuple[str, str, str]] | None:
    """Return (sha, subject, message) for every commit in the range."""
    listing = _git(["rev-list", "--reverse", range_spec])
    if listing.returncode != 0:
        detail = listing.stderr.strip() or "git rev-list failed"
        print(
            f"check-commit-attribution: cannot list commits in {range_spec!r}: {detail}",
            file=sys.stderr,
        )
        return None

    commits: list[tuple[str, str, str]] = []
    for sha in listing.stdout.split():
        log = _git(["log", "-1", "--format=%B", sha])
        if log.returncode != 0:
            detail = log.stderr.strip() or "git log failed"
            print(
                f"check-commit-attribution: cannot read commit {sha}: {detail}",
                file=sys.stderr,
            )
            return None
        message = log.stdout
        subject = message.splitlines()[0].strip() if message.splitlines() else "(no subject)"
        if not subject:
            subject = "(no subject)"
        commits.append((sha, subject, message))
    return commits


def _print_remediation() -> None:
    print(
        "\nAI attribution is not allowed in commit messages in this repository.\n"
        "Remove the trailer or signature. If the commit is not published yet,\n"
        "amend or reword it locally. Never rewrite published history without\n"
        f"maintainer coordination; see {POLICY_PATH}.",
        file=sys.stderr,
    )


def _check_message_file(path: Path) -> int:
    try:
        message = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        print(
            f"check-commit-attribution: cannot read {path}: {error}",
            file=sys.stderr,
        )
        return 2

    violations = find_violations(message, hook_cleanup=True)
    if not violations:
        print("commit attribution: clean")
        return 0

    print(f"commit attribution check failed for {path}:", file=sys.stderr)
    for violation in violations:
        print(
            f"  line {violation.line_number}: {violation.kind}: {violation.text[:160]}",
            file=sys.stderr,
        )
    _print_remediation()
    return 1


def _check_range(range_spec: str) -> int:
    commits = _commits_in_range(range_spec)
    if commits is None:
        return 2
    if not commits:
        print(f"commit attribution: clean (no commits in {range_spec})")
        return 0

    findings: dict[tuple[str, str], list[Violation]] = {}
    for sha, subject, message in commits:
        violations = find_violations(message)
        if violations:
            findings[(sha, subject)] = violations

    if not findings:
        print(f"commit attribution: clean ({len(commits)} commit(s) in {range_spec})")
        return 0

    print(
        f"commit attribution check failed: {len(findings)} of {len(commits)} "
        f"commit(s) in {range_spec} carry AI attribution.",
        file=sys.stderr,
    )
    for (sha, subject), violations in findings.items():
        print(f"  {sha}  {subject[:100]}", file=sys.stderr)
        for violation in violations:
            print(
                f"      line {violation.line_number}: {violation.kind}: "
                f"{violation.text[:160]}",
                file=sys.stderr,
            )
    _print_remediation()
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject AI attribution trailers and signatures in commit messages.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--message-file",
        type=Path,
        metavar="PATH",
        help="check a single commit message file (commit-msg hook mode)",
    )
    mode.add_argument(
        "--range",
        dest="range_spec",
        metavar="BASE..HEAD",
        help="check every commit added in this revision range (CI mode)",
    )
    args = parser.parse_args(argv)

    if args.message_file is not None:
        try:
            return _check_message_file(args.message_file)
        except RuntimeError as error:
            print(f"check-commit-attribution: {error}", file=sys.stderr)
            return 2

    if not _valid_range(args.range_spec):
        print(
            f"check-commit-attribution: invalid range {args.range_spec!r}; "
            "expected BASE..HEAD",
            file=sys.stderr,
        )
        return 2
    try:
        return _check_range(args.range_spec)
    except RuntimeError as error:
        print(f"check-commit-attribution: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
