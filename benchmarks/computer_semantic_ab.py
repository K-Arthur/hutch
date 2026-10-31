#!/usr/bin/env python3
"""Bake-off: the same native-desktop task through pixels and through the accessibility tree.

There is no model in this loop, so this does **not** measure model accuracy, and it must not be read as one. What it does
measure is everything the harness controls, on the real disposable KWin session:

  * how many tool calls a task takes each way,
  * how many characters of observation a model would have to read (the dominant per-step cost),
  * whether the effect is verified by reading state back, or only by "the screen changed",
  * wall time per step including capture, action and verification,
  * whether the result actually landed, checked against the file on disk.

The pixel arm supplies a fixed coordinate because a harness without a model has nothing else to go on. That is a property
of this benchmark, not evidence that a model would mis-click; the point is that the pixel path *needs* a coordinate from
somewhere, and cannot confirm the result without another screenshot.

Run:  PYTHONPATH=src python benchmarks/computer_semantic_ab.py --repetitions 5 --json out.json
Everything stays in a disposable session with a temporary workspace. Nothing paid or personal is touched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hutch.computer.native.eis import find_gi_python  # noqa: E402
from hutch.computer.native.virtual import ManagedDesktop  # noqa: E402
from hutch.models import Bot  # noqa: E402
from hutch.tools.base import ProcRegistry  # noqa: E402
from hutch.tools.computer import ComputerTool  # noqa: E402

TEXT = "bake-off sentinel"


class Gate:
    def __init__(self) -> None:
        self.count = 0

    def decide(self, tool, action, detail, decision=None, outward=False, ask_in_auto=False):
        self.count += 1

    def cancelled(self) -> bool:
        return False


def _ctx(config, workspace: Path, run_id: str):
    return SimpleNamespace(
        config=config, bot=Bot(name="bench-bot", computer_apps=["kwrite"]),
        run=SimpleNamespace(id=run_id), workspace=workspace, gate=Gate(), dry_run=False,
        begin_effect=lambda: None, emit=lambda event: None, on_finish=[], cancel_hooks=[],
        procs=ProcRegistry(), headless=True)


def _frames_and_bytes(result) -> tuple[int, int]:
    observation = (result.data or {}).get("observation") if result.ok else None
    if not observation or not observation.get("image"):
        return 0, 0
    return 1, int(observation["image"].get("bytes") or 0)


def _pixel_arm(tool, ctx, target: Path, coordinate: tuple[int, int]) -> dict:
    """Observe, click a remembered coordinate, type, save with a chord, observe again."""
    steps, observed, started = 0, 0, time.monotonic()
    frames, image_bytes = 0, 0
    launched = tool.run({"action": "launch", "app": "kwrite", "path": target.name}, ctx)
    steps += 1
    if not launched.ok:
        return {"ok": False, "steps": steps, "note": launched.output[:200]}
    observed += len(launched.output)
    count, size = _frames_and_bytes(launched)
    frames, image_bytes = frames + count, image_bytes + size
    clicked = tool.run({"action": "click", "frame_id": launched.data["observation"]["frame_id"],
                        "x": coordinate[0], "y": coordinate[1]}, ctx)
    steps += 1
    if not clicked.ok:
        return {"ok": False, "steps": steps, "note": clicked.output[:200]}
    typed = tool.run({"action": "type", "frame_id": clicked.data["observation"]["frame_id"], "text": TEXT}, ctx)
    steps += 1
    if not typed.ok:
        return {"ok": False, "steps": steps, "note": typed.output[:200]}
    saved = tool.run({"action": "key", "frame_id": typed.data["observation"]["frame_id"], "keys": "ctrl+s"}, ctx)
    steps += 1
    if not saved.ok:
        return {"ok": False, "steps": steps, "note": saved.output[:200]}
    for result in (clicked, typed, saved):
        count, size = _frames_and_bytes(result)
        frames, image_bytes = frames + count, image_bytes + size
    observed += len(clicked.output) + len(typed.output) + len(saved.output)
    # Without a tree there is nothing to read back: only "the screen changed" is available.
    followed = tool.run({"action": "observe"}, ctx)
    steps += 1
    observed += len(followed.output) if followed.ok else 0
    count, size = _frames_and_bytes(followed)
    frames, image_bytes = frames + count, image_bytes + size
    return {"ok": TEXT in target.read_text(encoding="utf-8"), "steps": steps,
            "observation_chars": observed, "image_frames": frames, "image_bytes": image_bytes,
            "verification": "visual_change_only", "seconds": round(time.monotonic() - started, 2)}


def _semantic_arm(tool, ctx, target: Path, coordinate: tuple[int, int]) -> dict:
    """Read the tree, set the text by element id, press Save by name, read the tree back."""
    steps, observed, started = 0, 0, time.monotonic()
    launched = tool.run({"action": "launch", "app": "kwrite", "path": target.name}, ctx)
    steps += 1
    if not launched.ok:
        return {"ok": False, "steps": steps, "note": launched.output[:200]}
    elements = tool.run({"action": "elements"}, ctx)
    steps += 1
    if not elements.ok:
        return {"ok": False, "steps": steps, "note": elements.output[:200]}
    observed += len(elements.output)
    snapshot = elements.data["elements"]
    editor = next((node for node in snapshot["nodes"]
                   if node["role"] == "text" and node.get("name") == target.name), None)
    if editor is None:
        return {"ok": False, "steps": steps, "note": "no editor element in the tree"}
    written = tool.run({"action": "set_text", "snapshot_id": snapshot["snapshot_id"],
                        "element_id": editor["id"], "text": TEXT}, ctx)
    steps += 1
    if not written.ok:
        return {"ok": False, "steps": steps, "note": written.output[:200]}
    observed += len(written.output)
    tree = written.data["elements"]
    save = next((node for node in tree["nodes"]
                 if node["role"] in ("button", "push button") and node.get("name") == "Save"), None)
    if save is None:
        return {"ok": False, "steps": steps, "note": "no Save button in the tree"}
    pressed = tool.run({"action": "activate", "snapshot_id": written.data["snapshot_id"],
                        "element_id": save["id"]}, ctx)
    steps += 1
    if pressed.ok:
        observed += len(pressed.output)
    return {"ok": TEXT in target.read_text(encoding="utf-8"), "steps": steps,
            "observation_chars": observed, "image_frames": 0, "image_bytes": 0,
            "verification": "effect_verified" if written.data.get("outcome") == "effect_verified"
                            else str(written.data.get("outcome")),
            "seconds": round(time.monotonic() - started, 2)}


def _summary(rows: list[dict]) -> dict:
    ok = [row for row in rows if row.get("ok")]
    return {
        "runs": len(rows),
        "succeeded": len(ok),
        "median_steps": statistics.median([row["steps"] for row in rows]) if rows else 0,
        "median_observation_chars": statistics.median([row.get("observation_chars", 0) for row in rows]) if rows else 0,
        "median_image_frames": statistics.median([row.get("image_frames", 0) for row in rows]) if rows else 0,
        "median_image_bytes": statistics.median([row.get("image_bytes", 0) for row in rows]) if rows else 0,
        "median_seconds": statistics.median([row.get("seconds", 0) for row in rows]) if rows else 0,
        "verification": sorted({row.get("verification", "?") for row in ok}) or ["none"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()

    ready, why = ManagedDesktop.available()
    if not ready or shutil.which("kwrite") is None:
        print(f"SKIP: {why or 'kwrite is not installed'}")
        return 0
    from hutch.computer.accessibility import find_atspi_python
    if find_gi_python() is None or find_atspi_python() is None:
        print("SKIP: no PyGObject interpreter for input or the accessibility worker")
        return 0

    from hutch.config import get_config
    root = Path(tempfile.mkdtemp(prefix="semantic-ab-", dir=os.environ.get("TMPDIR") or None))
    os.environ.setdefault("HUTCH_STATE_DIR", str(root / "state"))
    config = get_config()
    rows: dict[str, list[dict]] = {"pixel": [], "semantic": []}
    tool = ComputerTool()
    try:
        for index in range(args.repetitions):
            for arm, fn in (("pixel", _pixel_arm), ("semantic", _semantic_arm)):
                workspace = root / f"ws-{index}-{arm}"
                workspace.mkdir()
                target = workspace / "note.txt"
                target.write_text("placeholder\n")
                ctx = _ctx(config, workspace, f"run-{index}-{arm}")
                # The pixel arm needs a coordinate up front. The semantic arm ignores it.
                try:
                    result = fn(tool, ctx, target, (640, 400))
                except Exception as exc:  # noqa: BLE001 - a failed arm is a result, not a crash
                    result = {"ok": False, "steps": 0, "note": f"{type(exc).__name__}: {exc}"[:200]}
                result["iteration"] = index
                rows[arm].append(result)
                print(f"{arm:9} iteration {index}: ok={result.get('ok')} steps={result.get('steps')} "
                      f"chars={result.get('observation_chars', 0)} frames={result.get('image_frames', 0)} "
                      f"({result.get('image_bytes', 0)} image bytes) {result.get('note', '')}")
                tool._shutdown(ctx)
                ctx.procs.kill_all(0.2)
    finally:
        tool._shutdown(None)
        shutil.rmtree(root, ignore_errors=True)

    report = {arm: _summary(found) for arm, found in rows.items()}
    print(json.dumps({"summary": report, "runs": rows}, indent=2))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps({"summary": report, "runs": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
