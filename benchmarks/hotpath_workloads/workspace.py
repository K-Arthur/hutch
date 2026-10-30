"""Workspace discovery: the files list tool's os.walk path on 1k / 5k-file synthetic workspaces.

Runs FilesListTool.run through a real ToolContext (policy engine, approval gate, store) so the
measurement includes the path check and the bounded structured-inventory construction, not just
os.walk. The output is verified to be a successful listing.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

SAMPLES_FULL = 7
SAMPLES_QUICK = 3


def _make_workspace(base: Path, count: int) -> int:
    base.mkdir(parents=True, exist_ok=True)
    per_dir = max(10, count // 40)
    written = 0
    bucket = 0
    while written < count:
        target = base / f"area-{bucket:03d}" / f"bucket-{bucket % 7}"
        target.mkdir(parents=True, exist_ok=True)
        bucket += 1
        for _ in range(per_dir):
            if written >= count:
                break
            (target / f"note-{written:05d}.md").write_text(f"# note {written}\n")
            written += 1
    return bucket


def _context(workspace: Path, name: str):
    from hutch.approvals import ApprovalGate
    from hutch.config import get_config
    from hutch.models import Bot, Run, RunStatus
    from hutch.safety import PolicyEngine
    from hutch.store import Store
    from hutch.tools.base import ToolContext

    config = get_config()
    store = Store(config)
    bot = store.create_bot(Bot(name=name, tools=["files"]))
    run = Run(bot_id=bot.id, prompt="bench", status=RunStatus.running)
    store.create_run(run)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda event: None)
    context = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                          config=config, workspace=workspace)
    return store, context


def run(quick: bool, state) -> list[dict]:
    from hutch.tools.files import FilesListTool

    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    sizes = [1000] if quick else [1000, 5000]
    tool = FilesListTool()
    store = None
    try:
        cases: list[dict] = []
        for size in sizes:
            workspace = state / f"ws-{size}"
            _make_workspace(workspace, size)
            store, context = _context(workspace, f"bench-workspace-{size}")
            first = tool.run({}, context)
            if not first.ok:
                raise RuntimeError(f"list_files failed on {size} files: {first.output[:200]}")
            samples = []
            for _ in range(n):
                started = time.perf_counter()
                result = tool.run({}, context)
                samples.append((time.perf_counter() - started) * 1000.0)
                if not result.ok:
                    raise RuntimeError(f"list_files failed on {size} files: {result.output[:200]}")
            listed = result.data.get("listed_entries", result.data.get("count"))
            cases.append({
                "name": f"workspace.list_files_{size}_ms", "unit": "ms", "samples": samples,
                "better": "lower",
                "note": f"{size:,} files; listed_entries={listed}, paths={len(result.data.get('paths', []))}",
                "detail": {"files": size, "listed_entries": listed,
                           "us_per_file": statistics.median(samples) / size * 1000},
            })
            store.close()
            store = None
        return cases
    finally:
        if store is not None:
            store.close()
