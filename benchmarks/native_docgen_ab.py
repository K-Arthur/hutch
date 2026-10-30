"""CLI driver + summary report for the native XLSX writer A/B comparison.

Workload, boundary encoding, openpyxl verification and the paired samplers live in
`benchmarks/native_docgen_ab_workload.py` (kept separate so both files stay under the
repository's 400-line new-source cap). Two comparisons are measured in one process,
interleaved A/B/A/B:

(a) write stage only -- `xlsx._write_workbook` pure-Python vs the native path including the
    JSON boundary (serializing the normalized sheets + the .so call);
(b) full generation -- `generate("xlsx", spec)` pure-Python vs the same public path with only
    the writer native; the independent openpyxl read-back gate runs unchanged in both.

Preflight gates and decodes both paths before any timing; on failure the driver exits
non-zero without reporting numbers. The JSON artifact goes to `benchmarks/results/`
(gitignored).

    PYTHONPATH=$PWD/src .venv/bin/python benchmarks/native_docgen_ab.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.native_docgen_ab_workload import (  # noqa: E402
    TINY_SPEC,
    Abort,
    full_generation_samples,
    integrated_loader,
    machine,
    native_extension,
    normalized_sheets,
    paired_ratio,
    preflight,
    summarize,
    timed,
    workload,
    write_stage_samples,
)

_TABLE_HEAD = ["", "| case | n | min ms | median ms | p95 ms | max ms |",
               "|---|---:|---:|---:|---:|---:|"]


def _row(label: str, stats: dict[str, float]) -> str:
    return (f"| {label:<31} | {int(stats['n']):>3} | {stats['min']:>9.2f} | {stats['median']:>9.2f}"
            f" | {stats['p95']:>9.2f} | {stats['max']:>9.2f} |")


def report(results: dict[str, Any], meta: dict[str, Any]) -> str:
    write, full, boundary = (results["write_stage"], results["full_generation"],
                             results["boundary"])
    write_gain = (write["python"]["median"] - write["native"]["median"]) / write["python"]["median"]
    write_p95_gain = (write["python"]["p95"] - write["native"]["p95"]) / write["python"]["p95"]
    full_gain = (full["python"]["median"] - full["native"]["median"]) / full["python"]["median"]
    full_p95_gain = (full["python"]["p95"] - full["native"]["p95"]) / full["python"]["p95"]
    return "\n".join([
        "", "## Machine / run metadata",
        f"- CPU: {meta['cpu']} ({meta['logical_cores']} logical cores); "
        f"Python {meta['python']} on {meta['platform']}",
        f"- loadavg at start (1/5/15): {meta['load_avg_1m_5m_15m']}",
        f"- git {meta['git_head'][:12]}{' (dirty)' if meta['git_dirty'] else ''}; harness "
        f"sha256 {meta['harness_sha256'][:12]}; native extension {meta['native_extension']} "
        f"({meta['native_extension_bytes']:,} bytes)",
        f"- workload: {meta['workload_rows']:,} rows x {meta['workload_columns']} columns "
        f"({meta['workload_rows'] * meta['workload_columns']:,} cells); no formulas/freeze",
        f"- preflight: unchanged openpyxl gate passed on both paths, decode equal "
        f"(python {results['preflight']['bytes_python']:,} bytes, "
        f"native {results['preflight']['bytes_native']:,} bytes)",
        "", "### (a) write stage only", *_TABLE_HEAD,
        _row("python _write_workbook", write["python"]),
        _row("native: encode + .so call", write["native"]),
        _row("  of which JSON encode", write["encode"]),
        _row("  of which .so call", write["call"]),
        "", "### (b) full generation (generate('xlsx', spec), gate included)", *_TABLE_HEAD,
        _row("python writer", full["python"]),
        _row("native writer, gate unchanged", full["native"]), "",
        f"- write stage: paired median ratio native/python {write['paired_ratio']:.3f}; "
        f"median gain {write_gain * 100:.1f}%, p95 gain {write_p95_gain * 100:.1f}%",
        f"- boundary: payload {boundary['payload_kib']:.1f} KiB, 1 Python<->Rust crossing; JSON "
        f"encode median {write['encode']['median']:.2f} ms, .so call median "
        f"{write['call']['median']:.2f} ms, trivial .so call median {boundary['trivial_call_us']:.1f} us",
        f"- full generation: paired median ratio native/python {full['paired_ratio']:.3f}; "
        f"median gain {full_gain * 100:.1f}%, p95 gain {full_p95_gain * 100:.1f}%",
        f"- write stage = {write['python']['median'] / full['python']['median'] * 100:.0f}% of "
        f"the pure-Python full-generation median",
        f"- pre-registered P11 bar (>=20% p95 on the operation, boundary included): "
        f"{full_p95_gain * 100:.1f}% native full-generation p95 gain -> "
        f"{'MEETS' if full_p95_gain >= 0.20 else 'DOES NOT MEET'} the bar "
        f"(operation-level only; the end-to-end document workflow is dominated by other work)",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-driver native XLSX writer A/B harness")
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--samples-write", type=int, default=20)
    parser.add_argument("--samples-full", type=int, default=15)
    parser.add_argument("--quick", action="store_true", help="5 write / 3 full samples")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--no-json", action="store_true")
    args = parser.parse_args(argv)
    if args.quick:
        args.samples_write, args.samples_full = 5, 3

    try:
        native_module, native_path = native_extension()
        loader = integrated_loader()
        spec = workload(args.rows)
        meta = machine(native_path, spec)
        preflight_result = preflight(spec, loader, native_module)
        write_samples = write_stage_samples(normalized_sheets(spec), loader, native_module,
                                            args.samples_write)
        full_samples = full_generation_samples(spec, args.samples_full)
        trivial = [timed(lambda: native_module.write_workbook(TINY_SPEC))[0] * 1000.0
                   for _ in range(50)]
    except Abort as error:
        print(f"native_docgen_ab: PREFLIGHT FAILED: {error}", file=sys.stderr)
        return 2

    results = {
        "preflight": preflight_result,
        "write_stage": {
            "python": summarize(write_samples["python"]),
            "native": summarize(write_samples["native"]),
            "encode": summarize(write_samples["encode"]),
            "call": summarize(write_samples["call"]),
            "paired_ratio": paired_ratio(write_samples["python"], write_samples["native"])},
        "full_generation": {
            "python": summarize(full_samples["python"]),
            "native": summarize(full_samples["native"]),
            "paired_ratio": paired_ratio(full_samples["python"], full_samples["native"])},
        "boundary": {"payload_bytes": write_samples["payload_bytes"],
                     "payload_kib": write_samples["payload_bytes"] / 1024.0,
                     "trivial_call_us": statistics.median(trivial),
                     "boundary_crossings_per_operation": 1},
    }
    print(report(results, meta))
    try:
        print(f"- loadavg at end (1/5/15): {[round(v, 2) for v in os.getloadavg()]}")
    except OSError:
        pass
    if not args.no_json:
        path = args.json or (ROOT / "benchmarks" / "results"
                             / f"native-docgen-ab-{datetime.now(tz=timezone.utc):%Y%m%d}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"meta": meta, "results": results}, indent=2, sort_keys=True)
                        + "\n", encoding="utf-8")
        print(f"- JSON artifact: {path} (gitignored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
