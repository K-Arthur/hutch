"""Console summary table for one harness run (presentation only)."""

from __future__ import annotations

import json


def print_summary(payload: dict) -> None:
    analysis = payload.get("analysis") or {}
    machine = payload.get("machine") or {}
    sides = payload.get("sides") or {}
    print("")
    print("mode=" + str(payload.get("mode")) + "  load_start=" + str(machine.get("loadavg_start"))
          + "  load_end=" + str(machine.get("loadavg_end")))
    for name, side in sides.items():
        print("  " + name + ": " + str(side.get("tree")) + " @ "
              + str((side.get("git") or {}).get("head")))
    for side, viewports in (analysis.get("per_side") or {}).items():
        for viewport, data in viewports.items():
            metrics = data["metrics"]
            print("  " + side + " " + viewport + " reps=" + str(data["reps"])
                  + " refetch/burst=" + str(metrics["refetches_per_burst"]["median"])
                  + " commit->render=" + str(metrics["commit_to_render_ms"]["median"]) + "ms"
                  + " innerHTML=" + str(metrics["innerhtml_ms"]["median"]) + "ms"
                  + " longtask=" + str(metrics["longtask_ms_per_burst"]["median"]) + "ms"
                  + " dom=" + str(metrics["dom_nodes"]["median"])
                  + " overflow=" + str(metrics["overflow_px"]["max"])
                  + " frameP95=" + str(metrics["frame_gap_p95_ms"]["median"]) + "ms")
    if analysis.get("noise_floor"):
        print("noise floor: " + json.dumps(analysis["noise_floor"])[:400])
    for error in payload.get("errors") or []:
        print("ERROR: " + json.dumps(error), flush=True)
