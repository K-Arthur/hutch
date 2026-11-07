"""First run and the Models page state what was found in one voice (audit finding S2, gap G15).

Both read the sentence from `starter-route.js`. These checks fail if either surface goes back to composing its
own, which is how "OpenCode is ready with 10 model options" ended up beside "No default route" on one page.
"""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "static"


def test_first_run_and_the_models_page_use_the_shared_sentence():
    for name in ("app.js", "models-detect.js"):
        source = (STATIC / name).read_text(encoding="utf-8")
        assert "availability(" in source, name
        assert "is ready with" not in source, name


def test_the_sentence_lives_only_in_the_shared_module():
    shared = (STATIC / "starter-route.js").read_text(encoding="utf-8")
    assert "is available with" in shared and "None is saved as the default for new assistants yet." in shared
    for name in ("app.js", "models-detect.js"):
        assert "None is saved as the default" not in (STATIC / name).read_text(encoding="utf-8"), name
