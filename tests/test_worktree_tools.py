"""Worktree toolkit: disposable git fixtures plus classification/prune behavior.

The fixtures create real git worktrees in tmp directories; they never touch this
checkout's worktree registry. The final test runs status against this repository
so a broken local invocation fails fast.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "worktree_tools", ROOT / "scripts" / "worktree_tools.py")
worktree_tools = importlib.util.module_from_spec(spec)
sys.modules["worktree_tools"] = worktree_tools  # dataclasses resolves the module
spec.loader.exec_module(worktree_tools)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def add_worktree(repo: Path, path: Path, branch: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-q", str(path), "-b", branch, "HEAD")
    return path


def merge_branch(repo: Path, branch: str) -> None:
    git(repo, "merge", "-q", "--no-ff", "-m", f"merge {branch}", branch)


def report_for(repo: Path, **kwargs):
    kwargs.setdefault("min_age_days", 0)
    return worktree_tools.build_report(repo, **kwargs)


def by_path(report: dict, path: Path) -> dict:
    resolved = str(path.resolve())
    return next(item for item in report["worktrees"] if item["path"] == resolved)


def worktree_paths(repo: Path) -> list[str]:
    return [line.split(" ", 1)[1]
            for line in git(repo, "worktree", "list", "--porcelain").splitlines()
            if line.startswith("worktree ")]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def test_status_classifies_merged_clean_worktree_as_stale(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "done", "done")
    merge_branch(repo, "done")
    report = report_for(repo)
    item = by_path(report, worktree)
    assert item["branch"] == "done"
    assert item["classification"] == "repo-local"
    assert item["external"] is False
    assert item["merged"] is True
    assert item["dirty"] == 0 and item["untracked"] == 0
    assert item["age_days"] == 0
    assert item["stale"] is True
    assert str(worktree.resolve()) in report["candidates"]


def test_fresh_worktree_needs_the_min_age_threshold(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "fresh", "fresh")
    merge_branch(repo, "fresh")
    fresh = by_path(worktree_tools.build_report(repo), worktree)
    assert fresh["stale"] is False
    assert fresh["merged"] is True


def test_dirty_worktree_is_not_stale(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "dirty", "dirty")
    merge_branch(repo, "dirty")
    (worktree / "file.txt").write_text("edited\n", encoding="utf-8")
    item = by_path(report_for(repo), worktree)
    assert item["merged"] is True
    assert item["dirty"] == 1
    assert item["stale"] is False


def test_untracked_file_blocks_staleness(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "untracked", "untracked")
    merge_branch(repo, "untracked")
    (worktree / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    item = by_path(report_for(repo), worktree)
    assert item["dirty"] == 0 and item["untracked"] == 1
    assert item["stale"] is False


def test_unmerged_worktree_is_not_stale(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "open", "open")
    (worktree / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(worktree, "add", "-A")
    git(worktree, "commit", "-qm", "feature")
    item = by_path(report_for(repo), worktree)
    assert item["merged"] is False
    assert item["stale"] is False


def test_external_worktree_is_classified_and_protected(repo: Path, tmp_path: Path):
    external = add_worktree(repo, tmp_path / "external" / "checkout", "external")
    merge_branch(repo, "external")
    report = report_for(repo)
    item = by_path(report, external)
    assert item["external"] is True
    assert item["classification"] == "external"
    assert item["merged"] is True
    assert item["stale"] is False
    assert str(external.resolve()) not in report["candidates"]
    before = set(worktree_paths(repo))
    status = worktree_tools.main(
        ["prune", "--root", str(repo), "--min-age-days", "0", "--apply"])
    assert status == 0
    assert external.is_dir()
    assert set(worktree_paths(repo)) == before


def test_prune_dry_run_removes_nothing(repo: Path):
    worktree = add_worktree(repo, repo / ".worktrees" / "stale", "stale")
    merge_branch(repo, "stale")
    before = worktree_paths(repo)
    status = worktree_tools.main(
        ["prune", "--root", str(repo), "--min-age-days", "0"])
    assert status == 0
    assert worktree.is_dir()
    assert worktree_paths(repo) == before


def test_prune_apply_removes_only_safe_candidates(repo: Path):
    stale = add_worktree(repo, repo / ".worktrees" / "stale", "stale-branch")
    merge_branch(repo, "stale-branch")
    dirty = add_worktree(repo, repo / ".worktrees" / "dirty", "dirty-branch")
    merge_branch(repo, "dirty-branch")
    (dirty / "file.txt").write_text("edited\n", encoding="utf-8")
    open_tree = add_worktree(repo, repo / ".worktrees" / "open", "open-branch")
    (open_tree / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(open_tree, "add", "-A")
    git(open_tree, "commit", "-qm", "feature")
    status = worktree_tools.main(
        ["prune", "--root", str(repo), "--min-age-days", "0", "--apply"])
    assert status == 0
    assert not stale.exists()
    assert dirty.is_dir()
    assert open_tree.is_dir()
    registered = {str(Path(path).resolve()) for path in worktree_paths(repo)}
    assert str(stale.resolve()) not in registered
    assert str(dirty.resolve()) in registered


def test_prune_never_removes_the_current_worktree(repo: Path):
    current = add_worktree(repo, repo / ".worktrees" / "current", "current")
    merge_branch(repo, "current")
    assert worktree_tools.main(
        ["prune", "--root", str(current), "--min-age-days", "0", "--apply"]) == 0
    assert current.is_dir()
    registered = {str(Path(path).resolve()) for path in worktree_paths(repo)}
    assert str(current.resolve()) in registered


def test_prune_protects_a_nested_parent(repo: Path):
    parent = add_worktree(repo, repo / ".worktrees" / "parent", "parent")
    merge_branch(repo, "parent")
    child = add_worktree(repo, parent / ".worktrees" / "child", "child")
    merge_branch(repo, "child")
    report = report_for(repo)
    assert by_path(report, parent)["nested_parent"] is True
    assert by_path(report, parent)["stale"] is False
    assert worktree_tools.main(
        ["prune", "--root", str(repo), "--min-age-days", "0", "--apply"]) == 0
    assert parent.is_dir()
    assert not child.exists()


def test_current_worktree_is_reported_current(repo: Path):
    report = report_for(repo)
    item = by_path(report, repo)
    assert item["main"] is True
    assert item["current"] is True
    assert item["classification"] == "main"
    assert item["stale"] is False


def test_non_git_directory_exits_two(tmp_path: Path):
    assert worktree_tools.main(["status", "--root", str(tmp_path)]) == 2
    assert worktree_tools.main(["prune", "--root", str(tmp_path)]) == 2


def test_json_shape(repo: Path, capsys):
    add_worktree(repo, repo / ".worktrees" / "listed", "listed")
    status = worktree_tools.main(["status", "--root", str(repo), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert set(payload) >= {"repo", "base", "min_age_days", "current",
                            "worktree_root", "worktrees", "duplicate_branches",
                            "candidates"}
    assert payload["base"]["ref"] == "HEAD"
    assert len(payload["base"]["commit"]) == 40
    assert payload["candidates"] == []
    item = payload["worktrees"][0]
    assert set(item) >= {"path", "branch", "detached", "head", "head_short",
                         "age_days", "dirty", "untracked", "merged", "locked",
                         "main", "current", "external", "nested",
                         "nested_parent", "classification", "stale"}


def test_prune_json_apply_reports_removed(repo: Path, capsys):
    stale = add_worktree(repo, repo / ".worktrees" / "stale-json", "stale-json")
    merge_branch(repo, "stale-json")
    status = worktree_tools.main(
        ["prune", "--root", str(repo), "--min-age-days", "0", "--json", "--apply"])
    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert payload["applied"] is True
    assert payload["removed"] == [str(stale.resolve())]
    assert payload["errors"] == []
    assert not stale.exists()


def test_status_runs_against_this_repository():
    assert worktree_tools.main(["status", "--root", str(ROOT)]) == 0
