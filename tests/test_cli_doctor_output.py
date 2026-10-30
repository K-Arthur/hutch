"""`hutch doctor` prints fix hints verbatim.

Rich treats `[browser]` as a style tag and drops it, so the hint for the optional browser
tool read `pip install 'hutch'` (a different thing) instead of `pip install 'hutch[browser]'`.
"""

from __future__ import annotations

from typer.testing import CliRunner

from hutch.cli import app
from hutch.doctor import INFO, WARN, Check


def test_doctor_prints_brackets_in_detail_and_fix_literally(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("hutch.doctor.run_doctor", lambda *a, **k: [
        Check("browser", "Browser tool", INFO, "playwright not installed [optional]", "pip install 'hutch[browser]'"),
        Check("x", "Other", WARN, "detail with [bold]markup-looking[/bold] text", "run `hutch state` [now]"),
    ])
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code in (0, 1), result.output
    out = " ".join(result.output.split())
    assert "pip install 'hutch[browser]'" in out
    assert "playwright not installed [optional]" in out
    assert "[bold]markup-looking[/bold]" in out
    assert "run `hutch state` [now]" in out

