"""Use disposable indexes/repos; never stage into the developer's checkout."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repo_hygiene", ROOT / "scripts/check_repo_hygiene.py")
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    git(tmp_path, "config", "user.name", "Fixture")
    (tmp_path / ".gitignore").write_bytes((ROOT / ".gitignore").read_bytes())
    git(tmp_path, "add", ".gitignore")
    git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


@pytest.mark.parametrize("path", [
    ".env", ".env.local", "nested/.env.production", ".aws/credentials", ".ssh/id_ed25519",
    ".state/config.toml", "hutch.db-wal", "hutch.sqlite3-shm", "serve.pid",
    ".coverage.worker", ".hypothesis/examples/new", "var/cache/fontconfig/test.cache",
    "desktop/target/debug/host", "desktop/gen/schemas/test.json",
    "docs/realignment/artifacts/new/trace.zip", ".v2c/plugin_root",
])
def test_forced_ignored_additions_are_rejected(repo, path):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("synthetic fixture")
    git(repo, "add", "-f", "--", path)
    assert any("ignore policy" in error for error in hygiene.check(repo))
    assert target.read_text() == "synthetic fixture"


@pytest.mark.parametrize("path", [
    ".env.example", "nested/.env.sample", ".env.template", ".python-version",
    "uv.lock", "package-lock.json", "desktop/Cargo.lock", "desktop/process-guard/Cargo.lock",
    "desktop/backend.spec", "desktop/web/startup.css", "desktop/icons/icon.svg",
    "src/hutch/build/source.py", "src/hutch/data/new.json",
    "src/hutch/server/static/ui.css", "website/styles.min.css",
    "tests/fixtures/new.db.fixture", "benchmarks/baselines/new.json",
    "docs/realignment/artifacts/review/pytest.log", "research_notes/new.md",
])
def test_required_source_and_reviewed_evidence_remain_trackable(repo, path):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("public fixture")
    git(repo, "add", "--", path)
    assert hygiene.check(repo) == []


def test_size_checks_the_index_not_unstaged_contents(repo):
    target = repo / "large.bin"
    target.write_bytes(b"x" * (hygiene.MAX_BYTES + 1))
    git(repo, "add", "large.bin")
    target.write_text("small unstaged replacement")
    assert any("staged blob" in error for error in hygiene.check(repo))


def test_unchanged_legacy_blobs_and_deletions_do_not_fail(repo):
    target = repo / "legacy.bin"
    target.write_bytes(b"x" * (hygiene.MAX_BYTES + 1))
    git(repo, "add", "legacy.bin")
    git(repo, "commit", "-qm", "legacy evidence")
    assert hygiene.check(repo) == []
    git(repo, "rm", "legacy.bin")
    assert hygiene.check(repo) == []


def test_rename_and_unusual_filename_are_checked(repo):
    target = repo / "source.txt"
    target.write_text("fixture")
    git(repo, "add", "source.txt")
    git(repo, "commit", "-qm", "source")
    git(repo, "mv", "source.txt", ".env.local")
    assert any("ignore policy" in error for error in hygiene.check(repo))
    odd = "large\nfile.bin"
    (repo / odd).write_bytes(b"x" * (hygiene.MAX_BYTES + 1))
    git(repo, "add", "--", odd)
    assert any("large\\nfile.bin" in error for error in hygiene.check(repo))
