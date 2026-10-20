import hashlib
import os

import pytest

from hutch.wake import _sock_dir


def _configure_fallback(monkeypatch, base, state_dir):
    monkeypatch.delenv("HUTCH_WAKE_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("hutch.wake.tempfile.gettempdir", lambda: str(base))
    uid = os.getuid() if hasattr(os, "getuid") else 0
    tag = hashlib.sha1(str(state_dir.resolve()).encode()).hexdigest()[:8]
    return uid, tag


def test_default_wake_directory_refuses_leaf_symlink_without_chmodding_target(tmp_path, monkeypatch):
    base = tmp_path / "tmp"
    base.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    uid, tag = _configure_fallback(monkeypatch, base, state_dir)
    parent = base / f"hutch-{uid}"
    parent.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o755)
    victim.chmod(0o755)
    (parent / tag).symlink_to(victim, target_is_directory=True)

    with pytest.raises(RuntimeError, match="real directory"):
        _sock_dir(state_dir)

    assert victim.stat().st_mode & 0o777 == 0o755


def test_default_wake_directory_refuses_symlinked_parent(tmp_path, monkeypatch):
    base = tmp_path / "tmp"
    base.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    uid, _ = _configure_fallback(monkeypatch, base, state_dir)
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o755)
    victim.chmod(0o755)
    (base / f"hutch-{uid}").symlink_to(victim, target_is_directory=True)

    with pytest.raises(RuntimeError, match="real directory"):
        _sock_dir(state_dir)

    assert not list(victim.iterdir())
    assert victim.stat().st_mode & 0o777 == 0o755


def test_default_wake_directory_secures_existing_owned_directories(tmp_path, monkeypatch):
    base = tmp_path / "tmp"
    base.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    uid, tag = _configure_fallback(monkeypatch, base, state_dir)
    parent = base / f"hutch-{uid}"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    leaf = parent / tag
    leaf.mkdir(mode=0o755)
    leaf.chmod(0o755)

    result = _sock_dir(state_dir)

    assert result == leaf
    assert parent.stat().st_mode & 0o777 == 0o700
    assert leaf.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="requires POSIX ownership")
def test_default_wake_directory_does_not_chmod_foreign_owned_parent(tmp_path, monkeypatch):
    base = tmp_path / "tmp"
    base.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    actual_uid = os.getuid()
    foreign_uid = actual_uid + 1
    monkeypatch.setattr("hutch.wake.os.getuid", lambda: foreign_uid)
    monkeypatch.delenv("HUTCH_WAKE_DIR", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("hutch.wake.tempfile.gettempdir", lambda: str(base))
    parent = base / f"hutch-{foreign_uid}"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)

    with pytest.raises(RuntimeError, match="not owned"):
        _sock_dir(state_dir)

    assert parent.stat().st_uid == actual_uid
    assert parent.stat().st_mode & 0o777 == 0o755
