"""The Studio Markdown renderer: structure, plain-text fidelity and XSS safety.

The renderer is browser JavaScript that must stay escape-first (assistant output is
untrusted). The real assertions live in tests/support/markdown_check.mjs and run under
Node, mirroring tests/test_widgets_static.py. The in-browser integration (answers in
the transcript, copy control) is covered by tests/e2e/test_studio_transcript.py.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MARKDOWN_JS = REPO / "src" / "hutch" / "server" / "static" / "markdown.js"
HARNESS = REPO / "tests" / "support" / "markdown_check.mjs"

NODE = shutil.which("node")
NEEDS_NODE = pytest.mark.skipif(NODE is None, reason="node not available")


@NEEDS_NODE
def test_markdown_js_parses():
    proc = subprocess.run([NODE, "--check", str(MARKDOWN_JS)], capture_output=True, text=True)
    assert proc.returncode == 0, f"node --check failed:\n{proc.stderr}"


@NEEDS_NODE
def test_markdown_renderer_is_correct_and_inert():
    proc = subprocess.run([NODE, str(HARNESS)], capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, f"markdown harness failed:\n{proc.stdout}\n{proc.stderr}"
    assert "passed" in proc.stdout


def test_markdown_is_loaded_by_the_studio_shell():
    html = (REPO / "src" / "hutch" / "server" / "static" / "index.html").read_text()
    assert '<script src="/static/markdown.js"></script>' in html
    # It must load before app.js, which renders answers through it.
    assert html.index("/static/markdown.js") < html.index("/static/app.js")
