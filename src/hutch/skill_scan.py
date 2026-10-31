"""Content-level review of a skill package, beyond what structure can prove.

The registry already refuses symlinks, escapes and oversized packages, hashes every byte, and
re-reads a staged update before applying it. None of that looks at what the instructions *say*. A
skill is text that gets placed in front of a model, so the risks that matter are the ones a person
would only catch by reading carefully:

* invisible characters that hide text from a human reviewer while a model still reads it;
* instructions that try to rearrange the model's priorities rather than describe a procedure;
* references to credential locations, which a skill has no reason to need;
* bundled programs, which are inert in Hutch today but are the thing an owner most wants to notice;
* a body so much larger than its description that the description cannot represent it.

Everything here is **advisory**. The brief is explicit that scanning is supplementary and never an
authorization boundary, and that ordering matters in both directions: a clean scan must not stand
in for review, and a finding must not silently veto an owner's decision. So findings are shown at
review time and recorded with the reviewed hash; nothing here grants or removes trust.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Severities, most serious first. ``danger`` means a person should read the quoted text before
#: trusting the package; it is not a block.
SEVERITIES = ("danger", "warning", "info")

#: A body longer than this cannot be represented by a one-line description; worth noticing.
LARGE_BODY_BYTES = 40_000
#: How many findings to keep. Beyond this the report says so rather than growing without bound.
MAX_FINDINGS = 40
#: How much of each file is inspected. A skill's instructions are small; a huge file is reported,
#: not read.
MAX_SCANNED_BYTES = 1_000_000

_TEXT_SUFFIXES = frozenset({".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".csv", ".tsv", ".rst"})
_PROGRAM_SUFFIXES = frozenset({".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb",
                               ".pl", ".ps1", ".bat", ".cmd"})
_EXECUTABLE_MAGIC = (b"\x7fELF", b"MZ", b"#!")

#: Characters that render as nothing or reorder text, so a reviewer sees different words than a
#: model does. The Unicode tag block is the classic "invisible instruction" carrier.
_INVISIBLE_CODEPOINTS = frozenset({0x00AD, 0x034F, 0x061C, 0x180E, 0x200B, 0x200C, 0x200D, 0x200E,
                                   0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060, 0x2061,
                                   0x2062, 0x2063, 0x2064, 0xFEFF})

def _is_invisible(char: str) -> bool:
    """True for a character that renders as nothing, or reorders what a reader sees.

    Format characters (``Cf``) cover the tag block, bidi overrides and zero-width joiners, which is
    the whole family an invisible instruction can hide in. The variation-selector supplement is
    added by hand because those characters render as a modifier rather than a glyph, so a payload
    of them is invisible while still being text a model reads.
    """
    code = ord(char)
    if code in _INVISIBLE_CODEPOINTS:
        return True
    if 0xE0100 <= code <= 0xE01EF:
        return True
    return unicodedata.category(char) == "Cf"


#: Phrases that try to change what the model is allowed to do, rather than describe a procedure.
#: Deliberately narrow: a false "danger" trains an owner to ignore the report.
_ESCALATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_prior_instructions",
     re.compile(r"(?i)\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
                r"(instructions?|rules?|prompts?|directions?)")),
    ("override_system_prompt",
     re.compile(r"(?i)\b(you\s+are\s+now|from\s+now\s+on\s+you|your\s+new\s+(role|instructions?)\s+(is|are))\b")),
    ("bypass_controls",
     re.compile(r"(?i)\b(bypass|disable|turn\s+off|circumvent|skip)\s+(the\s+)?"
                r"(approval|approvals|sandbox|safety|policy|guardrails?|confirmation|permission)")),
    ("conceal_from_owner",
     re.compile(r"(?i)\b(do\s+not|don\x27t|never)\s+(tell|inform|mention\s+to|reveal\s+to)\s+"
                r"(the\s+)?(user|owner|human)")),
    ("secret_exfiltration",
     re.compile(r"(?i)\b(send|post|upload|transmit|exfiltrate|forward)\b[^.\n]{0,60}\b"
                r"(api[\s-]?key|token|password|secret|credential|private\s+key)")),
)

#: Paths a procedure has no ordinary reason to reach.
_CREDENTIAL_PATHS = re.compile(
    r"(?i)(~/\.ssh|/\.ssh/|\.aws/credentials|~/\.aws|id_rsa|id_ed25519|\.env\b|~/\.netrc|\.gnupg|"
    r"/credentials\b|secrets?\.(json|yaml|yml)|/etc/shadow|keychain)")


@dataclass(frozen=True)
class Finding:
    """One advisory observation about a package's content."""

    severity: str        # danger | warning | info
    code: str
    message: str
    where: str = ""
    excerpt: str = ""    # bounded, and never a credential value

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message,
                "where": self.where, "excerpt": self.excerpt}


def _excerpt(line: str, limit: int = 140) -> str:
    """A short, single-line quote with invisible characters made visible."""
    cleaned = "".join(
        f"\\u{ord(char):04x}" if (_is_invisible(char) or
                                  (unicodedata.category(char) == "Cc" and char not in "\t"))
        else char for char in line)
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit] + ("..." if len(cleaned) > limit else "")


def _read_text(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(MAX_SCANNED_BYTES + 1)
    if len(raw) > MAX_SCANNED_BYTES:
        return ""
    return raw.decode("utf-8", errors="replace")


def _invisible_findings(relative: str, text: str, findings: list[Finding]) -> None:
    for number, line in enumerate(text.splitlines(), start=1):
        hidden = [char for char in line if _is_invisible(char)]
        if not hidden:
            continue
        points = ", ".join(sorted({f"U+{ord(char):04X}" for char in hidden}))
        findings.append(Finding(
            "danger", "content.invisible_characters",
            f"contains characters that render as nothing or reorder text ({points}); a reader "
            "and a model may see different words",
            f"{relative}:{number}", _excerpt(line)))
        return    # one finding per file is enough to send the owner to look


def _escalation_findings(relative: str, text: str, findings: list[Finding]) -> None:
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        for code, pattern in _ESCALATION_PATTERNS:
            if code in seen or not pattern.search(line):
                continue
            seen.add(code)
            findings.append(Finding(
                "danger", f"instructions.{code}",
                "contains language that changes what the assistant is allowed to do rather than "
                "describing a procedure",
                f"{relative}:{number}", _excerpt(line)))


def _credential_findings(relative: str, text: str, findings: list[Finding]) -> None:
    for number, line in enumerate(text.splitlines(), start=1):
        match = _CREDENTIAL_PATHS.search(line)
        if not match:
            continue
        findings.append(Finding(
            "warning", "content.credential_path",
            f"refers to a credential location ({match.group(0)}); a procedure rarely needs one, "
            "and a skill never grants access to it",
            f"{relative}:{number}", _excerpt(line)))
        return


def _file_findings(root: Path, path: Path, relative: str, findings: list[Finding]) -> None:
    """Programs and binaries are reported, not executed: Hutch has no script path for skills."""
    suffix = path.suffix.lower()
    try:
        head = path.open("rb").read(8)
    except OSError:
        return
    is_binary = any(head.startswith(magic) for magic in _EXECUTABLE_MAGIC)
    if suffix in _PROGRAM_SUFFIXES or is_binary:
        findings.append(Finding(
            "info", "package.contains_program",
            "bundles an executable program. Hutch does not run skill programs: this is inert here, "
            "but review it before copying the package anywhere that does",
            relative))
        return
    if suffix in _TEXT_SUFFIXES:
        text = _read_text(path)
        if "\x00" in text:
            findings.append(Finding(
                "warning", "package.binary_in_text_file",
                "a file named as text contains binary data; the instructions a model would read "
                "may not be what the package appears to contain", relative))
            return
        _invisible_findings(relative, text, findings)
        _escalation_findings(relative, text, findings)
        _credential_findings(relative, text, findings)


def scan_package(directory: str | Path) -> dict[str, Any]:
    """Review a skill package's content. Advisory only: never grants or removes trust.

    Returns ``{"findings": [...], "counts": {...}, "clean": bool, "scanned_files": n}``. ``clean``
    means nothing at ``danger`` or ``warning`` was found; it is not a statement that the package
    is safe, and the wording everywhere it is shown says so.
    """
    root = Path(directory)
    findings: list[Finding] = []
    if not root.is_dir():
        return {"findings": [], "counts": {level: 0 for level in SEVERITIES}, "clean": True,
                "scanned_files": 0, "note": "the package is not on disk, so nothing was scanned"}

    scanned = 0
    truncated = False
    for path in sorted(root.rglob("*")):
        if len(findings) >= MAX_FINDINGS:
            truncated = True
            break
        try:
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
        except OSError:
            continue
        _file_findings(root, path, relative, findings)
        if path.suffix.lower() in _TEXT_SUFFIXES:
            scanned += 1

    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        try:
            body_bytes = len(skill_md.read_bytes())
        except OSError:
            body_bytes = 0
        if body_bytes > LARGE_BODY_BYTES:
            findings.append(Finding(
                "warning", "content.large_instructions",
                f"the instruction file is {body_bytes:,} bytes; a description cannot represent "
                "that much procedure, so an assistant may activate it without knowing what it does",
                "SKILL.md"))

    findings.sort(key=lambda item: SEVERITIES.index(item.severity))
    counts = {level: sum(1 for finding in findings if finding.severity == level) for level in SEVERITIES}
    return {
        "findings": [finding.to_dict() for finding in findings],
        "counts": counts,
        "clean": counts["danger"] == 0 and counts["warning"] == 0,
        "scanned_files": scanned,
        "truncated": truncated,
        "note": ("Advisory only. A clean scan does not mean the package is safe, and a finding "
                 "does not block an owner's decision to trust it."),
    }


__all__ = ["Finding", "MAX_FINDINGS", "SEVERITIES", "scan_package"]
