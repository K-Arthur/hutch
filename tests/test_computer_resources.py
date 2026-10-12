"""Resource grants, revocation during review, frame quota concurrency and failed IPC cleanup."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hutch.computer.budgets import profile_usage
from hutch.computer.frames import FrameStore
from hutch.computer.resources import workspace_grant
from hutch.models import Bot
from hutch.tools.computer import ComputerTool
from tests.test_computer_image_delivery import FRAMES
from tests.test_tools import make_ctx


@pytest.mark.parametrize("name", [".env", ".env.csv", "credentials.json", ".ssh/id_rsa"])
def test_native_picker_cannot_borrow_policy_denied_workspace_material(tmp_path, name):
    secret = tmp_path / name
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("SENTINEL-MUST-NOT-REACH-GUI")
    ctx = SimpleNamespace(workspace=tmp_path)
    with pytest.raises(ValueError, match="policy-denied"):
        workspace_grant(ctx)


def test_native_grant_rejects_aliases_and_documents_whole_clean_workspace(tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("allowed report")
    assert workspace_grant(SimpleNamespace(workspace=tmp_path))["entries"] == 1
    os.link(source, tmp_path / "alias.txt")
    with pytest.raises(ValueError, match="without links"):
        workspace_grant(SimpleNamespace(workspace=tmp_path))


def test_native_revocation_wins_after_session_approval_before_compositor_start(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path, Bot(name="revoked-native", tools=["computer"], computer_apps=["kwrite"]))
    launched = []

    class Gate:
        def decide(self, *_args, **_kwargs):
            changed = store.get_bot(ctx.bot.id)
            changed.tools = []
            store.upsert_bot(changed)

    ctx.gate = Gate()
    tool = ComputerTool(desktop_factory=lambda: launched.append(True))
    result = tool.run({"action": "observe"}, ctx)
    assert not result.ok and "revoked" in result.output and launched == []


def test_separate_surface_frame_stores_share_a_quota_and_unique_ids(tmp_path):
    def save(_):
        return FrameStore(tmp_path / "same-run", max_frames=8).save(FRAMES[0], "image/png")
    with ThreadPoolExecutor(max_workers=8) as workers:
        refs = list(workers.map(save, range(80)))
    assert len({ref.frame_id for ref in refs}) == 80
    store = FrameStore(tmp_path / "same-run")
    assert store.usage()["frames"] == 8
    latest = max(refs, key=lambda ref: ref.frame_id)
    assert store.load(latest) == FRAMES[0]


def test_profile_budget_does_not_follow_symlinks_and_refuses_oversize(tmp_path, monkeypatch):
    import hutch.computer.budgets as budgets
    profile = tmp_path / "profile"
    profile.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"private" * 100)
    (profile / "SingletonLock").symlink_to(outside)
    assert profile_usage(profile)["bytes"] < outside.stat().st_size
    monkeypatch.setattr(budgets, "MAX_PROFILE_BYTES", 1024)
    (profile / "growing-cache").write_bytes(b"x" * 2048)
    with pytest.raises(ValueError, match="128 MiB"):
        profile_usage(profile)


def test_closed_authority_store_fails_closed_without_a_watchdog_thread_crash(store, config, tmp_path):
    from hutch.computer.resources import authority
    ctx = make_ctx(store, config, tmp_path, Bot(name="closed-store", tools=["browser"]))
    store.close()
    with pytest.raises(ValueError, match="authority state is unavailable"):
        authority(ctx, "browser")


def test_failed_ipc_bind_setup_removes_only_its_new_socket_and_closes_descriptors(config, monkeypatch):
    from hutch.computer import transport
    config.ensure()
    session = SimpleNamespace(ctx=SimpleNamespace(config=config, run=SimpleNamespace(id="failed-bind", fence=1)), surface="browser")
    before = len(list(Path("/proc/self/fd").iterdir()))
    original = transport.os.chmod

    def fail_socket_mode(path, *args, **kwargs):
        if str(path).endswith(".sock"):
            raise OSError("fault injected")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(transport.os, "chmod", fail_socket_mode)
    with pytest.raises(OSError, match="fault injected"):
        transport.WorkerBridge(session)
    assert list((config.state_dir / "human-channels").iterdir()) == []
    assert len(list(Path("/proc/self/fd").iterdir())) <= before
