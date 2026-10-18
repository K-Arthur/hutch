"""Untrusted-content ingestion assessment: flag, never rewrite (mission §7).

Hutch does not try to detect and delete "system-level directives". A PDF may
legitimately quote an attack phrase, a README may contain real installation
commands, and a social thread may discuss prompt injection. Deleting or
rewriting any of that would corrupt evidence and make the tool useless.

What this module provides instead is a small, deterministic, bounded scan that
*annotates* externally sourced text before a model sees it:

* instruction-override phrasing (several languages), system-prompt requests,
  role impersonation, forged tool/envelope markers, requests to send secrets
  somewhere, "don't tell the user", "don't ask for approval", and
  fetch-and-execute shell pipelines;
* invisible format characters (bidi overrides, zero-width joiners/spaces) that
  a human reader cannot see but the model can;
* hidden HTML comments, which are removed from the visible text and assessed
  separately, with the count disclosed.

Findings point at exact character spans, carry a bounded excerpt, and never
change the payload. The host-authored annotation is what travels alongside the
text; the text itself is preserved byte for byte. This is a heuristic, not a
classifier: absence of findings is not proof of safety, and authorization is
enforced at the broker regardless of what this scan returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

#: scanning is bounded so a huge page cannot turn ingestion into a CPU sink
DEFAULT_SCAN_CHARS = 200_000
MAX_FINDINGS = 12
EXCERPT_CHARS = 90

#: characters that are invisible or reorder text for a human reader
_BIDI_CONTROLS = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
_CONTROL_NAMES = {
    "\u202a": "LRE", "\u202b": "RLE", "\u202c": "PDF", "\u202d": "LRO", "\u202e": "RLO",
    "\u2066": "LRI", "\u2067": "RLI", "\u2068": "FSI", "\u2069": "PDI",
    "\u200b": "zero-width space", "\u200c": "zero-width non-joiner", "\u200d": "zero-width joiner",
    "\u2060": "word joiner", "\ufeff": "BOM/zero-width no-break space", "\u00ad": "soft hyphen",
}


@dataclass(frozen=True)
class Finding:
    """One flagged passage: where, what shape, one bounded excerpt."""

    rule: str
    label: str
    start: int
    end: int
    excerpt: str
    severity: str = "note"          # note | warn
    source: str = "text"            # text | html-comment | unicode

    def to_json(self) -> dict:
        return {"rule": self.rule, "label": self.label, "start": self.start, "end": self.end,
                "excerpt": self.excerpt, "severity": self.severity, "source": self.source}


#: (rule, severity, label, pattern). Patterns use bounded repetition and simple
#: classes only: no nested quantifiers, so scanning stays linear in practice.
_TEXT_RULES: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    ("instruction-override", "warn",
     "text asking to ignore previous instructions",
     re.compile(r"(?i)\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,60}?"
                r"\b(?:previous|prior|above|earlier|all)\b[^.\n]{0,30}?"
                r"\b(?:instructions?|prompts?|rules?|directions?|guidelines?)\b")),
    ("instruction-override-es", "warn",
     "text asking to ignore instructions (Spanish)",
     re.compile(r"(?i)\b(?:ignora|olvida|descarta|omite)\b[^.\n]{0,60}?"
                r"\b(?:instrucciones|indicaciones|reglas|directrices)\b")),
    ("instruction-override-fr", "warn",
     "text asking to ignore instructions (French)",
     re.compile(r"(?i)\b(?:ignorez|oubliez|ne\s+tenez\s+pas\s+compte)\b[^.\n]{0,60}?"
                r"\b(?:instructions|consignes|r[eè]gles)\b")),
    ("instruction-override-de", "warn",
     "text asking to ignore instructions (German)",
     re.compile(r"(?i)\b(?:ignoriere|vergiss|missachte)\b[^.\n]{0,60}?"
                r"\b(?:anweisungen|instruktionen|regeln)\b")),
    ("instruction-override-it", "warn",
     "text asking to ignore instructions (Italian)",
     re.compile(r"(?i)\b(?:ignora|dimentica)\b[^.\n]{0,60}?"
                r"\b(?:istruzioni|indicazioni|regole)\b")),
    ("instruction-override-zh", "warn",
     "text asking to ignore instructions (Chinese)",
     re.compile(r"(?:忽略|无视|忘掉|覆盖)[^。\n]{0,30}?(?:指令|指示|提示|规则)")),
    ("instruction-override-ja", "warn",
     "text asking to ignore instructions (Japanese)",
     re.compile(r"(?:以前|これまで|上記)の?(?:指示|命令|プロンプト)[^。\n]{0,20}?(?:無視|忘れ|従わない)")),
    ("system-prompt-request", "warn",
     "text asking for hidden system instructions",
     re.compile(r"(?i)\b(?:reveal|show|print|repeat|output|disclose)\b[^.\n]{0,40}?"
                r"\b(?:system\s*prompt|initial\s+instructions?|hidden\s+instructions?|developer\s+message)\b")),
    ("role-impersonation", "warn",
     "text formatted as a system/developer/assistant turn",
     re.compile(r"(?im)^\s*(?:system|developer|assistant)\s*[:>\]]")),
    ("forged-envelope", "warn",
     "text containing tool/envelope framing",
     re.compile(r"(?i)</?tool_result\b|<tool_call\b|\"action\"\s*:\s*\"call\"")),
    ("credential-exfiltration", "warn",
     "text asking to send credentials or secrets somewhere",
     re.compile(r"(?i)\b(?:send|upload|post|email|exfiltrate|transmit|forward)\b[^.\n]{0,60}?"
                r"\b(?:api[_\s-]?key|token|credential|password|passcode|secret|\.ssh|id_rsa|env\b)")),
    ("credential-access", "warn",
     "text asking to read credential files",
     re.compile(r"(?i)\b(?:read|open|cat|print|dump|access|copy|show)\b[^.\n]{0,40}?"
                r"(?:\.ssh|id_rsa|id_ed25519|\.aws|\.gnupg|\.netrc|\.git-credentials|"
                r"credentials\.json|/etc/shadow)")),
    ("secrecy-request", "warn",
     "text asking to hide actions from the user",
     re.compile(r"(?i)\b(?:do\s+not|don't|never)\s+(?:tell|inform|mention|reveal|show)\b[^.\n]{0,40}?"
                r"\b(?:the\s+)?(?:user|operator|human|owner)\b")),
    ("approval-bypass", "warn",
     "text asking to act without approval or confirmation",
     re.compile(r"(?i)\b(?:without|no\s+need\s+(?:for|to))\b[^.\n]{0,30}?"
                r"\b(?:asking|approval|permission|confirmation|review)\b")),
    ("fetch-and-execute", "warn",
     "shell pipeline that downloads and runs code",
     re.compile(r"(?i)\b(?:curl|wget)\b[^\n]{0,100}?\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python3?|node|perl)\b")),
    ("decode-and-execute", "warn",
     "pipeline that decodes a blob and runs it",
     re.compile(r"(?i)\bbase64\s+(?:-d|--decode)\b[^\n]{0,60}?\|\s*(?:sh|bash|python3?|node)\b")),
)

_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
#: how much hidden-comment text is retained for assessment (bounded)
MAX_COMMENT_TEXT = 20_000


def strip_html_comments(html: str) -> tuple[str, str, int]:
    """Remove HTML comments from the visible text; return (text, hidden_text, count).

    Comments are not visible to a human reader of the page, but a model fed
    extracted text would read them verbatim. They are removed from the visible
    payload and handed back separately so they can be assessed and disclosed —
    never silently trusted and never silently dropped without a trace.
    """
    hidden_parts: list[str] = []
    count = 0

    def collect(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        if sum(len(p) for p in hidden_parts) < MAX_COMMENT_TEXT:
            hidden_parts.append(match.group(1))
        return " "

    cleaned = _COMMENT_RE.sub(collect, html)
    return cleaned, "\n".join(hidden_parts), count


def _control_findings(text: str, source: str = "unicode") -> list[Finding]:
    """One finding per invisible-control kind, aggregated with its codepoints."""
    findings: list[Finding] = []
    groups = (("bidi-control", _BIDI_CONTROLS), ("zero-width", _ZERO_WIDTH))
    for rule, chars in groups:
        hits: dict[str, int] = {}
        first: Optional[int] = None
        for index, char in enumerate(text):
            if char in chars:
                hits[char] = hits.get(char, 0) + 1
                if first is None:
                    first = index
        if not hits:
            continue
        names = ", ".join(f"{_CONTROL_NAMES.get(c, repr(c))} U+{ord(c):04X}×{n}"
                          for c, n in sorted(hits.items()))
        findings.append(Finding(
            rule=rule, label=f"invisible characters that a human reader cannot see ({names})",
            start=first or 0, end=(first or 0) + 1, excerpt="", severity="note", source=source))
    return findings


def assess(text: str, *, scan_chars: int = DEFAULT_SCAN_CHARS, source: str = "text",
           max_findings: int = MAX_FINDINGS) -> list[Finding]:
    """Bounded, deterministic findings over (at most) the first ``scan_chars``.

    The text is never modified. Findings are capped; the caller can compare
    ``scan_chars`` with the real length to disclose what was not scanned.
    """
    window = text[:scan_chars] if scan_chars > 0 else ""
    findings: list[Finding] = []
    findings.extend(_control_findings(window, source=source))
    for rule, severity, label, pattern in _TEXT_RULES:
        for match in pattern.finditer(window):
            excerpt = window[match.start():match.end()]
            findings.append(Finding(rule=rule, label=label, start=match.start(), end=match.end(),
                                    excerpt=excerpt[:EXCERPT_CHARS], severity=severity, source=source))
            if len(findings) >= max_findings:
                return findings
    findings.sort(key=lambda f: (f.start, f.rule))
    return findings[:max_findings]


def annotation(findings: Iterable[Finding], *, assessed_chars: int, total_chars: int,
               comments_removed: int = 0) -> str:
    """The host-authored note shown beside untrusted content; empty when clean.

    Claims only what was done: flagged, not removed. The content below the note
    is unchanged, and the note says so, so a reader (human or model) can still
    use quoted attack phrases for legitimate analysis.
    """
    items = [f for f in findings if f.severity in ("warn", "note")]
    if not items and not comments_removed:
        return ""
    lines = ["[content scan: flagged passages remain in the text below as data; nothing was removed]"]
    if comments_removed:
        lines.append(f"- {comments_removed} hidden HTML comment(s) omitted from the visible text "
                     "and assessed separately")
    for finding in items:
        where = f"char {finding.start}" if finding.excerpt else "invisible content"
        detail = f' ("…{finding.excerpt}…")' if finding.excerpt else ""
        lines.append(f"- {where}: {finding.label}{detail}")
    if assessed_chars < total_chars:
        lines.append(f"- scanned the first {assessed_chars:,} of {total_chars:,} characters")
    return "\n".join(lines)
