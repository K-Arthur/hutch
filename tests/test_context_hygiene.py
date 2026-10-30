"""Context-hygiene file-size guard: tmp fixtures plus one real-checkout check.

The fixtures never touch the real checkout. The final test runs the audit against
this repository, so a new god file, a grown frozen file, or a missing baseline
fails CI even when nothing else notices.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "context_hygiene", ROOT / "scripts" / "audit_context_hygiene.py")
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)

BASELINE_NAME = hygiene.BASELINE_NAME


def write_source(root: Path, relative: str, lines: int) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {index}" for index in range(lines)) + "\n",
                    encoding="utf-8")
    return path


def write_baseline(root: Path, files: dict[str, int]) -> Path:
    path = root / BASELINE_NAME
    path.write_text(json.dumps({"version": 1, "max_lines": hygiene.MAX_LINES,
                                "files": files}), encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src/hutch").mkdir(parents=True)
    return tmp_path


def test_line_count_matches_wc_convention(tmp_path: Path):
    no_trailing = tmp_path / "a.py"
    no_trailing.write_text("a\nb\nc", encoding="utf-8")
    assert hygiene.line_count(no_trailing) == 3
    trailing = tmp_path / "b.py"
    trailing.write_text("a\nb\nc\n", encoding="utf-8")
    assert hygiene.line_count(trailing) == 3
    empty = tmp_path / "c.py"
    empty.write_text("", encoding="utf-8")
    assert hygiene.line_count(empty) == 0


def test_small_source_file_passes(repo: Path):
    write_baseline(repo, {})
    write_source(repo, "src/hutch/small.py", 120)
    assert hygiene.check(repo) == []


def test_new_over_cap_file_fails(repo: Path):
    write_baseline(repo, {})
    write_source(repo, "src/hutch/big.py", hygiene.MAX_LINES + 1)
    findings = hygiene.check(repo)
    assert len(findings) == 1
    assert "new source file over" in findings[0]
    assert "big.py" in findings[0]


def test_budgeted_extensions_cover_python_js_mjs_ts_astro(repo: Path):
    write_baseline(repo, {})
    for name in ("a.py", "b.js", "c.mjs", "d.ts", "e.astro"):
        write_source(repo, f"src/hutch/{name}", hygiene.MAX_LINES + 1)
    findings = hygiene.check(repo)
    assert len(findings) == 5
    assert {finding.split(": ", 1)[1].split(" (", 1)[0] for finding in findings} == {
        "src/hutch/a.py", "src/hutch/b.js", "src/hutch/c.mjs",
        "src/hutch/d.ts", "src/hutch/e.astro"}


def test_frozen_file_may_shrink_but_not_grow(repo: Path):
    write_source(repo, "src/hutch/legacy.py", 500)
    write_baseline(repo, {"src/hutch/legacy.py": 500})
    assert hygiene.check(repo) == []
    write_source(repo, "src/hutch/legacy.py", 480)
    assert hygiene.check(repo) == []
    write_source(repo, "src/hutch/legacy.py", 501)
    findings = hygiene.check(repo)
    assert len(findings) == 1
    assert "frozen file grew" in findings[0]


def test_css_sources_are_budgeted_but_generated_css_is_not(repo: Path):
    write_baseline(repo, {})
    for relative in ("app/src/new.css", "website/src/new.css",
                     "website/styles.css", "src/hutch/server/static/style.css"):
        write_source(repo, relative, hygiene.MAX_LINES + 10)
    for relative in (
        "src/hutch/server/static/ui.css",
        "src/hutch/server/static/model-switcher.css",
        "website/app.css",
        "website/styles.min.css",
        "src/hutch/server/static/vendor/lib.css",
        "src/hutch/server/static/vendor/lib.min.css",
    ):
        write_source(repo, relative, 10_000)
    inventory = hygiene.collect_inventory(repo)
    assert set(inventory) == {
        "app/src/new.css", "website/src/new.css", "website/styles.css",
        "src/hutch/server/static/style.css"}
    assert len(hygiene.check(repo)) == 4


def test_excluded_trees_and_hidden_dirs_are_not_scanned(repo: Path):
    write_baseline(repo, {})
    for relative in (
        "node_modules/pkg/big.js",
        "__pycache__/big.py",
        ".venv/big.py",
        ".worktrees/wt/big.py",
        ".pytest_cache/big.py",
        ".validation/big.py",
        "desktop/target/debug/big.py",
        "desktop/process-guard/target/debug/big.py",
        "desktop/binaries/big.py",
        "desktop/gen/big.py",
        "docs/realignment/artifacts/evidence/big.py",
        "docs/research/artifacts/evidence/notes.css",
        "build/big.py",
        "dist/big.js",
        "var/big.py",
        "reports/big.py",
        "playwright-report/big.js",
        "test-results/big.js",
    ):
        write_source(repo, relative, 1000)
    assert hygiene.collect_inventory(repo) == {}


def test_baseline_is_deterministic_sorted_compact():
    expected = '{"files":{"a.py":600,"b.py":500},"max_lines":400,"version":1}\n'
    assert hygiene.format_baseline({"b.py": 500, "a.py": 600}) == expected
    assert hygiene.format_baseline({"a.py": 600, "b.py": 500}) == expected


def test_update_bootstraps_then_only_shrinks(repo: Path):
    write_source(repo, "src/hutch/legacy.py", 500)
    frozen, errors = hygiene.update(repo)
    assert errors == [] and frozen == {"src/hutch/legacy.py": 500}
    assert hygiene.check(repo) == []

    write_source(repo, "src/hutch/new.py", 450)
    frozen, errors = hygiene.update(repo)
    assert frozen == {} and any("refuse to add" in error for error in errors)

    write_source(repo, "src/hutch/new.py", 100)
    write_source(repo, "src/hutch/legacy.py", 520)
    frozen, errors = hygiene.update(repo)
    assert frozen == {} and any("refuse to raise" in error for error in errors)

    write_source(repo, "src/hutch/legacy.py", 100)
    frozen, errors = hygiene.update(repo)
    assert errors == [] and frozen == {}
    stored = json.loads((repo / BASELINE_NAME).read_text(encoding="utf-8"))
    assert stored["files"] == {}


def test_missing_or_invalid_baseline_is_an_error(repo: Path):
    with pytest.raises(hygiene.BaselineError):
        hygiene.check(repo)
    (repo / BASELINE_NAME).write_text("not json", encoding="utf-8")
    with pytest.raises(hygiene.BaselineError):
        hygiene.check(repo)
    (repo / BASELINE_NAME).write_text(
        json.dumps({"version": 1, "max_lines": 300, "files": {}}), encoding="utf-8")
    with pytest.raises(hygiene.BaselineError):
        hygiene.check(repo)


def test_cli_exit_codes(repo: Path):
    assert hygiene.main(["--root", str(repo)]) == 2
    write_baseline(repo, {})
    assert hygiene.main(["--root", str(repo)]) == 0
    write_source(repo, "src/hutch/big.py", hygiene.MAX_LINES + 1)
    assert hygiene.main(["--root", str(repo)]) == 1
    assert hygiene.main(["--root", str(repo), "--report"]) == 0
    assert hygiene.main(["--root", str(repo), "--update"]) == 1


def test_real_repository_has_no_context_violations():
    """CI drift guard: the checkout itself must satisfy the frozen baseline."""
    assert hygiene.check(ROOT) == []
    baseline = hygiene.load_baseline(ROOT / BASELINE_NAME)
    inventory = hygiene.collect_inventory(ROOT)
    over_cap = {relative: lines for relative, lines in inventory.items()
                if lines > hygiene.MAX_LINES}
    for relative, lines in over_cap.items():
        assert relative in baseline, f"{relative} is not frozen in {BASELINE_NAME}"
        assert lines <= baseline[relative]
