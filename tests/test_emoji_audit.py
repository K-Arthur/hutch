"""Emoji-ban audit gate.

Runs scripts/audit_emoji.py over the repository, so the default `pytest`
invocation fails on emoji or icon-character regressions, no separate tool
invocation to forget (the varve approach required remembering a recipe).
Also unit-tests the matcher itself on synthetic lines, without needing
banned characters in this file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "audit_emoji.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_emoji", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_repository_is_emoji_clean():
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"emoji audit found violations — run "
        f"`python scripts/audit_emoji.py` for the full list:\n{proc.stdout}{proc.stderr}"
    )


def test_pictographic_emoji_detected_in_any_file():
    mod = _load_audit_module()
    assert mod.line_violations("hello \U0001F4C1 folder", ui=False) == ["EMOJI"]  # hutch-emoji-allow: test data
    assert mod.line_violations("flag \U0001F1FA\U0001F1F8", ui=False) == ["EMOJI"]  # hutch-emoji-allow: test data
    assert mod.line_violations("keycap 1\u20E3", ui=False) == ["EMOJI"]  # hutch-emoji-allow: test data
    assert mod.line_violations("spark \u26A1", ui=False) == []  # text-presentation dingbat: UI rule only
    assert mod.line_violations("spark \u26A1", ui=True) == ["ICON"]
    assert mod.line_violations("variation \u2713\uFE0F", ui=False) == ["EMOJI"]  # hutch-emoji-allow: test data


def test_icon_chars_detected_only_in_ui_files():
    mod = _load_audit_module()
    assert mod.line_violations("x \u2192 y", ui=True) == ["ICON"]
    assert mod.line_violations("x \u2192 y", ui=False) == []
    assert mod.line_violations("close \u2715", ui=True) == ["ICON"]
    assert mod.line_violations("gear \u2699", ui=True) == ["ICON"]


def test_html_entities_detected_in_ui_files():
    mod = _load_audit_module()
    assert mod.line_violations('<a href="#">see &rarr;</a>', ui=True) == ["ICON-ENTITY"]
    assert mod.line_violations("<b>&check;</b>", ui=True) == ["ICON-ENTITY"]
    assert mod.line_violations("<b>&amp;</b>", ui=True) == []
    # numeric entity forms of banned codepoints
    assert mod.line_violations("&#x1F4C1;", ui=True) == ["ICON-ENTITY"]
    assert mod.line_violations("&#128193;", ui=True) == ["ICON-ENTITY"]
    assert mod.line_violations("&#9889;", ui=True) == ["ICON-ENTITY"]
    assert mod.line_violations("a &amp; b &lt; c", ui=True) == []


def test_escape_sequences_detected():
    mod = _load_audit_module()
    assert mod.line_violations('const s = "\\u{1F4C1}";', ui=True) == ["EMOJI-ESCAPE"]  # hutch-emoji-allow: test data
    assert mod.line_violations('const s = "\\uD83D\\uDE00";', ui=False) == ["EMOJI-ESCAPE"]  # hutch-emoji-allow: test data
    assert mod.line_violations('x = "\\u0041"', ui=True) == []  # plain A


def test_line_matcher_does_not_apply_waivers():
    mod = _load_audit_module()
    line = "spark \u26A1  # hutch-emoji-allow (terminal transcript)"
    assert mod.line_violations(line, ui=True) == ["ICON"]


def test_audit_counts_waivers():
    import tempfile

    mod = _load_audit_module()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ui = root / "website"
        ui.mkdir()
        (ui / "index.html").write_text("<p>done \u2713</p>\n", encoding="utf-8")
        (ui / "ok.html").write_text(
            f"<p>done \u2713</p> <!-- hutch-emoji-allow: fixture -->\n", encoding="utf-8"
        )
        violations, waivers, scanned = mod.audit(root)
        assert scanned == 2
        assert waivers == 1
        assert len(violations) == 1
        assert "ICON" in violations[0] and "website/index.html" in violations[0]
