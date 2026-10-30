"""Agent-map generator: disposable git fixtures plus the real checkout.

The map is derived from the git index, never working-tree content, so these
fixtures exercise determinism, drift detection and exclusion of derived trees.
The final test verifies this repository's committed map, so a stale map fails CI.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "generate_agent_map", ROOT / "scripts" / "generate_agent_map.py")
agent_map = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_map)


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True)


def write_file(root: Path, relative: str, content: str = "fixture\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src/hutch").mkdir(parents=True)
    write_file(tmp_path, "AGENTS.md", "# AGENTS\n")
    write_file(tmp_path, "src/hutch/engine.py")
    write_file(tmp_path, "tests/test_engine.py")
    write_file(tmp_path, "website/src/input.css")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def test_render_is_deterministic(repo: Path):
    first = agent_map.render(repo)
    second = agent_map.render(repo)
    assert first == second
    assert "## Top-level layout" in first
    assert "## Largest frozen files" in first


def test_check_passes_after_write(repo: Path):
    assert agent_map.main(["--root", str(repo), "--write"]) == 0
    assert agent_map.main(["--root", str(repo)]) == 0
    assert agent_map.main(["--root", str(repo), "--check"]) == 0


def test_check_fails_when_map_is_missing(repo: Path):
    assert agent_map.main(["--root", str(repo)]) == 1


def test_stale_map_fails_and_write_fixes_it(repo: Path):
    assert agent_map.main(["--root", str(repo), "--write"]) == 0
    write_file(repo, "src/hutch/new.py")
    git(repo, "add", "src/hutch/new.py")
    assert agent_map.main(["--root", str(repo), "--check"]) == 1
    assert agent_map.main(["--root", str(repo), "--write"]) == 0
    assert agent_map.main(["--root", str(repo), "--check"]) == 0


def test_existing_content_change_does_not_change_map(repo: Path):
    assert agent_map.main(["--root", str(repo), "--write"]) == 0
    before = agent_map.render(repo)
    write_file(repo, "src/hutch/engine.py", "\n".join(
        f"line {index}" for index in range(500)))
    assert agent_map.render(repo) == before
    assert agent_map.main(["--root", str(repo), "--check"]) == 0


def test_adding_a_file_changes_map(repo: Path):
    before = agent_map.render(repo)
    write_file(repo, "src/hutch/toolcalling/validate.py")
    git(repo, "add", "src/hutch/toolcalling/validate.py")
    after = agent_map.render(repo)
    assert before != after
    assert "toolcalling/" in after


def test_excluded_trees_do_not_change_map(repo: Path):
    before = agent_map.render(repo)
    for relative in (".venv/lib/python.py", "node_modules/pkg/index.js",
                     "docs/realignment/artifacts/trace.zip", ".worktrees/tree/file.py"):
        write_file(repo, relative)
        git(repo, "add", "-f", relative)
    assert agent_map.render(repo) == before
    assert "node_modules" not in before
    assert "artifacts" not in before


def test_output_stays_within_line_cap(repo: Path):
    rendered = agent_map.render(repo)
    assert len(rendered.splitlines()) <= agent_map.MAX_LINES


def test_missing_baseline_is_reported_gracefully(repo: Path):
    rendered = agent_map.render(repo)
    assert "No readable" in rendered
    assert agent_map.frozen_files(repo) is None


def test_frozen_table_uses_top_ten_from_baseline(repo: Path):
    baseline = {"version": 1, "max_lines": 400, "files": {
        "src/hutch/big.py": 1200, "src/hutch/mid.py": 800,
        "src/hutch/small.py": 500}}
    write_file(repo, ".file-size-baseline.json", json.dumps(baseline))
    frozen = agent_map.frozen_files(repo)
    assert frozen == [("src/hutch/big.py", 1200), ("src/hutch/mid.py", 800),
                      ("src/hutch/small.py", 500)]
    rendered = agent_map.render(repo)
    assert "| `src/hutch/big.py` | 1200 |" in rendered


def test_frozen_table_is_capped(repo: Path):
    files = {f"src/hutch/f{index:02d}.py": 500 + index for index in range(20)}
    write_file(repo, ".file-size-baseline.json",
               json.dumps({"version": 1, "max_lines": 400, "files": files}))
    assert len(agent_map.frozen_files(repo)) == agent_map.FROZEN_ROWS


def test_non_git_tree_is_unusable(tmp_path: Path):
    assert agent_map.main(["--root", str(tmp_path)]) == 2


def test_real_repository_check_passes():
    assert agent_map.main(["--root", str(ROOT)]) == 0
