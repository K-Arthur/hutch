"""A shell-line analyser for the safety policy (SR-13).

The policy can only judge what it can see. A command line hides executable text in more places than the first words:

* command substitution ``$(...)`` and backticks, which also run inside double quotes;
* process substitution ``<(...)`` / ``>(...)``, and subshells ``( ... )`` and groups ``{ ...; }``;
* separators other than ``&& || ; |``: a bare ``&`` (background) and a newline;
* here-document bodies (data, unless the delimiter is unquoted, when ``$(...)`` inside them runs);
* redirections, which write wherever they point.

So the line is split into segments the way a shell reads it, every nested command is collected for the policy to
analyse recursively, redirect targets are pulled out of the arguments, and anything this parser cannot read with
confidence raises ``ParseError``: the policy denies on that, because "I could not tell what this does" must never
become "allowed". It is deliberately a conservative reader, not a shell: it never expands anything, it only has to
find every place a command can hide.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

MAX_COMMAND_CHARS = 20_000
#: stands for a substituted command in the text handed to the tokenizer; a program word containing it is "computed"
SUBST = ""


class ParseError(ValueError):
    """The line cannot be read with confidence; the policy treats it as a deny."""


@dataclass
class Segment:
    text: str                                   # the raw text of this segment (nested commands included)
    tokens: list[str]                           # words only: no redirect operators or their targets
    piped_in: bool = False                      # something is piped INTO this segment
    piped_out: bool = False                     # this segment pipes into the next
    background: bool = False                    # ended with a bare &
    nested: list[str] = field(default_factory=list)      # commands inside $(), backticks, <(), ( ) in this segment
    redirects: list[str] = field(default_factory=list)   # targets of > >> >| &>
    heredoc: bool = False
    subshell: bool = False                      # the whole segment is a ( ... ) group: judged by its contents


# ------------------------------------------------------------------ scanning helpers

def _match_paren(s: str, open_idx: int) -> int:
    """Index of the ``)`` that closes the ``(`` at ``open_idx``; quotes and escapes are honoured."""
    depth, i, n = 0, open_idx, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                break
            i = j + 1
            continue
        if c == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "\\":
                    i += 1
                elif s[i] == "$" and s[i + 1:i + 2] == "(":
                    i = _match_paren(s, i + 1)
                i += 1
            i += 1
            continue
        if c == "`":
            j = _find_backtick(s, i + 1)
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ParseError("an unterminated ( ) substitution or group")


def _find_backtick(s: str, start: int) -> int:
    i, n = start, len(s)
    while i < n:
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "`":
            return i
        i += 1
    raise ParseError("an unterminated backtick substitution")


def nested_in(text: str) -> list[str]:
    """Commands that would run from ``$(...)``, backticks and ``<(...)`` inside ``text`` (a heredoc body or an
    arithmetic expansion): the characters are data, but these constructs inside them are not."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and text[i + 1:i + 2] == "(" and text[i + 1:i + 3] != "((":
            j = _match_paren(text, i + 1)
            out.append(text[i + 2:j])
            i = j + 1
            continue
        if c == "`":
            j = _find_backtick(text, i + 1)
            out.append(text[i + 1:j])
            i = j + 1
            continue
        i += 1
    return out


_NOT_ARITHMETIC = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s+[A-Za-z0-9_./~$-]|;")


def _arith_nested(inner: str) -> list[str]:
    """Commands hiding in the inside of ``$(( ... ))``.

    Bash reads ``$((`` as arithmetic when it can and as ``$( (subshell) )`` when it cannot, and the two are easy to
    confuse. Two words with no operator between them, or a ``;``, is never valid arithmetic, so such content is
    analysed as a command as well (fail closed); ``$(( 1 + x ))`` stays arithmetic.
    """
    out = nested_in(inner)
    if _NOT_ARITHMETIC.search(inner):
        out.append(inner.strip())
    return out


@dataclass
class _Piece:
    raw: list[str] = field(default_factory=list)       # exact text
    clean: list[str] = field(default_factory=list)     # same, nested commands replaced by SUBST
    nested: list[str] = field(default_factory=list)
    heredoc: bool = False
    subshell: bool = False

    def add(self, s: str) -> None:
        self.raw.append(s)
        self.clean.append(s)

    def add_subst(self, raw: str, inner: str) -> None:
        self.raw.append(raw)
        self.clean.append(SUBST)
        self.nested.append(inner)

    def blank(self) -> bool:
        return not "".join(self.clean).strip()


_HEREDOC_RE = re.compile(r"<<(-?)\s*(\\?)(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|<>()]+))")


def _tokenize(clean: str) -> tuple[list[str], list[str]]:
    """(words, redirect targets) of one segment. Redirect operators and their targets are not words."""
    lex = shlex.shlex(clean, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        toks = list(lex)
    except ValueError as exc:
        raise ParseError(str(exc)) from None
    words: list[str] = []
    redirects: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t and set(t) <= set("<>&|;()"):
            if ">" in t:
                if words and words[-1].isdigit():
                    words.pop()                              # the fd in 2> / 1>> (a stray digit word is harmless)
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if t.endswith("&") and (nxt.isdigit() or nxt == "-"):
                    i += 2                                    # >&2 : duplicating a descriptor, no file
                    continue
                if not nxt:
                    raise ParseError("a redirect with no target")
                redirects.append(nxt)
                i += 2
                continue
            if "<" in t:                                      # < file, << delim, <<< string: nothing is written
                i += 2
                continue
            if t in ("(", ")"):
                raise ParseError("an unexpected parenthesis")
            i += 1                                            # a stray separator char: ignore
            continue
        words.append(t)
        i += 1
    return words, redirects


# ------------------------------------------------------------------------ the splitter

def split_compound(command: str) -> list[Segment]:
    """Split a shell line into segments the way a shell reads it, collecting nested commands and redirects."""
    if len(command) > MAX_COMMAND_CHARS:
        raise ParseError(f"the command is longer than {MAX_COMMAND_CHARS:,} characters")
    pieces: list[_Piece] = []
    seps: list[str] = []
    cur = _Piece()
    pending: list[tuple[str, bool, bool]] = []                 # heredocs: (delimiter, strip tabs, quoted)
    i, n = 0, len(command)

    def end_piece(sep: str) -> None:
        nonlocal cur
        pieces.append(cur)
        seps.append(sep)
        cur = _Piece()

    while i < n:
        c = command[i]
        nxt = command[i + 1] if i + 1 < n else ""

        if c == "\\":
            if nxt == "\n":                                      # line continuation
                cur.add(" ")
            else:
                cur.add(command[i:i + 2])
            i += 2
            continue
        if c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise ParseError("an unterminated single quote")
            cur.add(command[i:j + 1])
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            cur.add('"')
            while True:
                if j >= n:
                    raise ParseError("an unterminated double quote")
                d = command[j]
                if d == "\\":
                    cur.add(command[j:j + 2])
                    j += 2
                elif d == '"':
                    cur.add('"')
                    j += 1
                    break
                elif d == "$" and command[j + 1:j + 2] == "(" and command[j + 1:j + 3] != "((":
                    k = _match_paren(command, j + 1)
                    cur.add_subst(command[j:k + 1], command[j + 2:k])
                    j = k + 1
                elif d == "$" and command.startswith("$((", j):
                    k = _match_paren(command, j + 2)
                    cur.nested.extend(_arith_nested(command[j + 3:k - 1]))
                    cur.add(command[j:k + 1])
                    j = k + 1
                elif d == "`":
                    k = _find_backtick(command, j + 1)
                    cur.add_subst(command[j:k + 1], command[j + 1:k])
                    j = k + 1
                else:
                    cur.add(d)
                    j += 1
            i = j
            continue
        if c == "$" and nxt == "(":
            if command.startswith("$((", i):
                k = _match_paren(command, i + 1)
                cur.nested.extend(_arith_nested(command[i + 3:k - 1]))
                cur.add("0")
                cur.raw[-1] = command[i:k + 1]
                i = k + 1
                continue
            k = _match_paren(command, i + 1)
            cur.add_subst(command[i:k + 1], command[i + 2:k])
            i = k + 1
            continue
        if c == "`":
            k = _find_backtick(command, i + 1)
            cur.add_subst(command[i:k + 1], command[i + 1:k])
            i = k + 1
            continue
        if c in "<>" and nxt == "(":
            k = _match_paren(command, i + 1)
            cur.add_subst(command[i:k + 1], command[i + 2:k])
            i = k + 1
            continue
        if c == "(" and cur.blank():                             # a subshell
            k = _match_paren(command, i)
            cur.subshell = True
            cur.add_subst(command[i:k + 1], command[i + 1:k])
            i = k + 1
            continue
        if c == "{" and cur.blank() and (nxt.isspace() or nxt == ""):    # a group: its body is ordinary segments
            i += 1
            continue
        if c == "}" and cur.blank() and (i + 1 >= n or command[i + 1] in " \t\n;&|)"):
            i += 1
            continue

        two = command[i:i + 2]
        if two in ("&&", "||"):
            end_piece(two)
            i += 2
            continue
        if two == "|&":
            end_piece("|")
            i += 2
            continue
        if c in ";|":
            end_piece(c)
            i += 1
            continue
        if c == "&":
            prev = command[i - 1] if i else ""
            if nxt == ">" or prev in "<>":                       # &>file, >&2, 2>&1: part of a redirect
                cur.add(c)
                i += 1
                continue
            end_piece("&")
            i += 1
            continue
        if c in "\n\r":
            if pending:                                          # heredoc bodies start on the next line
                i += 1
                for delim, strip, quoted in pending:
                    body_lines: list[str] = []
                    while i < n:
                        eol = command.find("\n", i)
                        line = command[i:] if eol < 0 else command[i:eol]
                        i = n if eol < 0 else eol + 1
                        if (line.lstrip("\t") if strip else line) == delim:
                            break
                        body_lines.append(line)
                    body = "\n".join(body_lines)
                    cur.raw.append("\n" + body)                  # kept in the raw text so secret scanning sees it
                    if not quoted:
                        cur.nested.extend(nested_in(body))
                pending = []
                end_piece(";")                                   # what follows the body is a new command
                continue
            end_piece(";")
            i += 1
            continue
        if command.startswith("<<", i) and command[i + 2:i + 3] != "<":
            m = _HEREDOC_RE.match(command, i)
            if m:
                quoted = bool(m.group(2) or m.group(3) is not None or m.group(4) is not None)
                delim = m.group(3) if m.group(3) is not None else m.group(4) if m.group(4) is not None else m.group(5)
                pending.append((delim, m.group(1) == "-", quoted))
                cur.heredoc = True
                cur.raw.append(m.group(0))
                cur.clean.append("<<x")                           # an input redirect with a dummy word
                i = m.end()
                continue
        cur.add(c)
        i += 1
    pieces.append(cur)

    segments: list[Segment] = []
    for idx, p in enumerate(pieces):
        text = "".join(p.raw).strip()
        clean = "".join(p.clean).strip()
        if not clean and not p.nested:
            continue
        words, redirects = _tokenize(clean)
        seg = Segment(text=text, tokens=words, nested=p.nested, redirects=redirects, heredoc=p.heredoc,
                      subshell=p.subshell and words == [SUBST])
        sep_before = seps[idx - 1] if idx > 0 else ""
        if sep_before == "|":
            seg.piped_in = True
            if segments:
                segments[-1].piped_out = True
        if idx < len(seps) and seps[idx] == "&":
            seg.background = True
        segments.append(seg)
    return segments
