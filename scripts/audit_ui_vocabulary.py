#!/usr/bin/env python3
"""hutch UI vocabulary audit: the interface says "assistant", not "bot".

`bot` stays in the CLI (`hutch bot ...`), API paths, storage and identifiers
(docs/realignment/product-spine.md, section 3). This audit finds *prose* that a
person reads in the SPA scripts: text inside string and template literals, and
the visible attributes aria-label, title, placeholder and alt. It reads strings
with a small JS-aware lexer, so `bots.map(bot => ...)`, `grant.bot_id`, `data-*-bot`
attributes and `/api/bots` paths are never touched.

Run:  python scripts/audit_ui_vocabulary.py          (exit 1 when prose says bot)
      python scripts/audit_ui_vocabulary.py --fix    (rewrite in place)

Exempt by design: channels.js (Telegram's own "bot" concept) and the exact
search-synonym literals in EXEMPT_LITERALS (hidden command palette keywords).
Server templates are checked by tests/test_ui_vocabulary.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "hutch" / "server" / "static"
EXEMPT_FILES = {"channels.js"}
EXEMPT_LITERALS = {"create helper bot", "manage fleet roster helpers bots"}

VISIBLE_ATTRS = ("aria-label", "title", "placeholder", "alt")
SKIP_RUN = re.compile(r"Telegram|BotFather|bot token|hutch bot\b", re.I)
PHRASE = re.compile(r"(?<![\w./#-])[Bb]ot-to-[Bb]ot\b")
ARTICLE = re.compile(r"(?<![\w./#-])\b([Aa]) [Bb]ot\b(?![\w/-])")
# Not CLI text such as "bot purge --key"; not identifiers, paths or classes.
WORD = re.compile(r"(?<![\w./#-])\b([Bb]ots?)\b(?![\w/-]|\.\w|\s+[a-z]+\s+--)")
CAPITAL_AFTER = set("<>\"'`([:.!?—-") | {None}


def _capital_here(run: str, pos: int, prev: str | None) -> bool:
    j = pos - 1
    while j >= 0 and run[j] == " ":
        j -= 1
    c = run[j] if j >= 0 else prev
    return c in CAPITAL_AFTER or c == "\n"


def swap_run(run: str, prev: str | None) -> str:
    """Rewrite one run of visible prose; `prev` is the character before it."""
    if not re.search(r"[Bb]ot", run) or SKIP_RUN.search(run) or run.strip().lower() in EXEMPT_LITERALS:
        return run
    run = ARTICLE.sub(lambda m: ("An" if m.group(1) == "A" else "an") + " assistant", run)
    run = PHRASE.sub(lambda m: ("Assistant" if _capital_here(run, m.start(), prev) else "assistant") + "-to-assistant", run)

    def word(m: re.Match) -> str:
        if run[: m.start()].endswith("hutch "):
            return m.group(0)
        base = "assistants" if m.group(1).lower().endswith("s") else "assistant"
        return base.capitalize() if _capital_here(run, m.start(), prev) else base

    return WORD.sub(word, run)


class Rewriter:
    """Single pass over JS source; only prose inside literals is rewritten."""

    def __init__(self, src: str) -> None:
        self.s, self.n = src, len(src)

    def _html_text(self, text: str, st: dict) -> str:
        out: list[str] = []
        run: list[str] = []
        run_prev: list[str | None] = [None]

        def add(ch: str, i: int) -> None:
            if not run:
                run_prev[0] = text[i - 1] if i > 0 else st["prev"]
            run.append(ch)

        def flush() -> None:
            if run:
                out.append(swap_run("".join(run), run_prev[0]))
                run.clear()

        for i, ch in enumerate(text):
            mode = st["mode"]
            if mode == "text":
                if ch == "<" and i + 1 < len(text) and (text[i + 1].isalpha() or text[i + 1] == "/"):
                    flush(); out.append(ch); st["mode"], st["tag"] = "tag", ""
                else:
                    add(ch, i)
            elif mode == "tag":
                out.append(ch); st["tag"] += ch
                if ch == '"':
                    name = re.search(r"([\w-]+)=\"$", st["tag"])
                    st["visible"] = bool(name and name.group(1) in VISIBLE_ATTRS)
                    st["mode"] = "attr"
                elif ch == ">":
                    st["mode"] = "text"
            else:  # attribute value
                if ch == '"':
                    flush(); out.append(ch); st["mode"] = "tag"; st["tag"] += ch
                elif st["visible"]:
                    add(ch, i)
                else:
                    out.append(ch)
        if st["mode"] in ("text", "attr") and (st["mode"] == "text" or st["visible"]):
            flush()
        return "".join(out)

    def _template(self, i: int) -> tuple[str, int]:
        j, parts, buf = i + 1, [], []
        while j < self.n:
            ch = self.s[j]
            if ch == "\\":
                buf.append(self.s[j:j + 2]); j += 2; continue
            if ch == "`":
                parts.append(("t", "".join(buf)))
                break
            if ch == "$" and self.s[j + 1:j + 2] == "{":
                parts.append(("t", "".join(buf))); buf = []
                expr, j = self._code(j + 2, brace=True)
                parts.append(("e", "${" + expr + "}"))
                continue
            buf.append(ch); j += 1
        else:
            raise ValueError("unterminated template literal")
        joined = "".join(p for k, p in parts if k == "t")
        html = "<" in joined
        prose = html or (" " in joined and not re.match(r"[/#.\[]", joined))
        out, st, prev = ["`"], {"mode": "text", "prev": "`", "tag": "", "visible": False}, "`"
        for kind, part in parts:
            if kind == "e":
                out.append(part); st["prev"] = prev = "}"  # text after a value is mid-sentence
            elif html:
                out.append(self._html_text(part, st))
            elif prose:
                out.append(swap_run(part, prev))
            else:
                out.append(part)
        out.append("`")
        return "".join(out), j + 1

    def _string(self, i: int) -> tuple[str | None, int]:
        quote, j = self.s[i], i + 1
        while j < self.n and self.s[j] != "\n":
            if self.s[j] == "\\":
                j += 2; continue
            if self.s[j] == quote:
                content = self.s[i + 1:j]
                if " " in content and not re.match(r"[/#.\[]", content) and "${" not in content:
                    content = swap_run(content, quote)
                return quote + content + quote, j + 1
            j += 1
        return None, i  # not a same-line string: an ordinary character (e.g. in a regex)

    def _code(self, i: int, brace: bool = False) -> tuple[str, int]:
        out: list[str] = []
        depth = 0
        while i < self.n:
            ch, nxt = self.s[i], self.s[i + 1:i + 2]
            if ch == "/" and nxt == "/":
                k = self.s.find("\n", i); k = self.n if k < 0 else k
                out.append(self.s[i:k]); i = k; continue
            if ch == "/" and nxt == "*":
                k = self.s.find("*/", i + 2); k = self.n if k < 0 else k + 2
                out.append(self.s[i:k]); i = k; continue
            if ch == "`":
                text, i = self._template(i); out.append(text); continue
            if ch in "'\"":
                text, k = self._string(i)
                if text is None:
                    out.append(ch); i += 1
                else:
                    out.append(text); i = k
                continue
            if brace:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    if depth == 0:
                        return "".join(out), i + 1
                    depth -= 1
            out.append(ch); i += 1
        return "".join(out), i

    def run(self) -> str:
        return self._code(0)[0]


def _normalise(text: str) -> str:
    return re.sub(r"\b(?:[Aa]ssistants?|[Bb]ots?|[Aa]n?)\b", "", text)


def rewrite(src: str) -> str:
    """Return `src` with visible prose rewritten; refuse any change beyond bot/assistant words and articles."""
    new = Rewriter(src).run()
    if _normalise(src) != _normalise(new):
        raise AssertionError("rewriter changed more than bot/assistant words; refusing")
    return new


def findings(path: Path) -> list[tuple[int, str]]:
    """(line, text) pairs where visible prose in `path` still says bot."""
    src = path.read_text(encoding="utf-8")
    new = rewrite(src)
    return [(n, old.strip()[:140]) for n, (old, now) in enumerate(zip(src.splitlines(), new.splitlines()), 1) if old != now]


def script_files() -> list[Path]:
    return [p for p in sorted(STATIC.glob("*.js")) if p.name not in EXEMPT_FILES]


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    bad = 0
    for path in script_files():
        found = findings(path)
        if not found:
            continue
        if fix:
            path.write_text(rewrite(path.read_text(encoding="utf-8")), encoding="utf-8")
            print(f"fixed {len(found)} lines in {path.relative_to(ROOT)}")
        else:
            bad += len(found)
            for line, text in found:
                print(f"{path.relative_to(ROOT)}:{line}: {text}")
    if bad:
        print(f"\n{bad} line(s) say 'bot' in prose; use 'assistant' (run with --fix).", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
