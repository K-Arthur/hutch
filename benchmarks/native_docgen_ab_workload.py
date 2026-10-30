"""Workload, boundary encoding, verification and measurement helpers for the native XLSX
writer A/B driver (`benchmarks/native_docgen_ab.py`).

Kept separate so both files stay under the repository's 400-line new-source cap. This
module owns the measured workload (the repository's own 5000-row xlsx case), the exact
JSON boundary the integrated loader pays, openpyxl decode-compare verification, the
paired-interleaved samplers, and machine/run metadata.

The workload is `benchmarks/hotpath_workloads/documents.py::_spec` so numbers are comparable
with the pre-registered baseline in `docs/perf/plan-2026-10-29.md`; it is not tuned for the
native path.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import io
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from openpyxl import load_workbook  # noqa: E402

from hutch.documents.docgen import generate  # noqa: E402
from hutch.documents.docgen import xlsx  # noqa: E402

MODULE_NAME = "hutch_docgen_native"
NATIVE_DIR = Path(xlsx.__file__).resolve().parent / "_native"
EXTENSION_SUFFIXES = {".so", ".pyd", ".dylib"}
TINY_SPEC = '{"sheets": [{"name": "Tiny"}]}'


class Abort(RuntimeError):
    """Preflight failed: timings must not be reported for unverified output."""


def native_extension() -> tuple[Any, Path]:
    """Load the optional extension module directly from its installed location."""
    if not NATIVE_DIR.is_dir():
        raise Abort("native extension is not built: run scripts/build_native_docgen.py --check")
    for path in sorted(NATIVE_DIR.iterdir()):
        if not (path.name.startswith(MODULE_NAME) and path.suffix in EXTENSION_SUFFIXES):
            continue
        loader = importlib.machinery.ExtensionFileLoader(MODULE_NAME, str(path))
        try:
            module = importlib.util.module_from_spec(
                importlib.util.spec_from_loader(MODULE_NAME, loader))
            loader.exec_module(module)
            return module, path
        except Exception as error:  # noqa: BLE001 - report the real loader failure
            raise Abort(f"cannot load {path}: {error}") from error
    raise Abort(f"no {MODULE_NAME} extension in {NATIVE_DIR}; run the build script")


def integrated_loader() -> Any:
    """The Lead-integrated optional loader (native.py) that xlsx.py calls first."""
    from hutch.documents.docgen import native as loader

    if not loader.available():
        raise Abort("the integrated loader reports the native extension as unavailable")
    return loader


@contextmanager
def reference_writer() -> Iterator[None]:
    """Force xlsx.py's pure-Python writer even though the integrated loader is present."""
    loader = getattr(xlsx, "_native_write_workbook", None)
    if loader is None:
        yield
        return

    def _unavailable(_sheets: list[Any]) -> bytes:
        from hutch.documents.docgen.native import NativeUnavailable

        raise NativeUnavailable("A/B driver selected the reference writer")

    xlsx._native_write_workbook = _unavailable
    try:
        yield
    finally:
        xlsx._native_write_workbook = loader


def workload(rows: int) -> dict[str, Any]:
    """The repository's 5000-row case: week/region/units/revenue, strings+ints+floats."""
    body = [[f"2026-W{index % 52:02d}", f"region-{index % 12}", index % 500,
             round(index * 1.75, 2)] for index in range(rows)]
    return {"sheets": [{"name": "Weekly", "header": ["week", "region", "units", "revenue"],
                        "rows": body}]}


def normalized_sheets(spec: dict[str, Any]) -> list[Any]:
    return xlsx._normalize_sheets(spec)[0]


def _encode_cell(cell: tuple[Any, ...]) -> list[Any]:
    kind = cell[0]
    if kind == "str":
        return ["str", cell[1]]
    if kind == "num":
        return ["num", cell[1]]
    if kind == "date":
        return ["date", cell[1].isoformat()]
    return ["formula", cell[1], cell[2]]


def encode_sheets(sheets: list[Any]) -> str:
    """The same compact JSON boundary the integrated loader sends to the extension."""
    return json.dumps(
        {"sheets": [{"name": s.name, "header": s.header,
                     "rows": [[_encode_cell(cell) for cell in row] for row in s.rows],
                     "freeze": s.freeze, "col_widths": s.col_widths} for s in sheets]},
        ensure_ascii=False, separators=(",", ":"))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def decoded(data: bytes) -> dict[str, Any]:
    """Openpyxl decode used to prove the native output equals the reference output."""
    cached = load_workbook(io.BytesIO(data), data_only=True)
    raw = load_workbook(io.BytesIO(data), data_only=False)
    try:
        result: dict[str, Any] = {"sheetnames": cached.sheetnames, "sheets": {}}
        for name in cached.sheetnames:
            values_ws, raw_ws = cached[name], raw[name]
            formulas = {(c.coordinate, re.sub(r"[\s$]", "", c.value)) for row in
                        raw_ws.iter_rows() for c in row
                        if isinstance(c.value, str) and c.value.startswith("=")}
            widths = tuple(sorted((col, round(dim.width, 9)) for col, dim in
                                  raw_ws.column_dimensions.items() if dim.width is not None))
            result["sheets"][name] = (
                [[_normalize_value(cell.value) for cell in row] for row in values_ws.iter_rows()],
                values_ws.freeze_panes, formulas, widths)
        return result
    finally:
        cached.close()
        raw.close()


def assert_valid_xlsx(data: bytes, label: str) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise Abort(f"{label}: output is not a zip archive")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise Abort(f"{label}: corrupt xlsx member")
        if b'fullCalcOnLoad="1"' not in archive.read("xl/workbook.xml"):
            raise Abort(f"{label}: workbook does not request recalculation on load")


def preflight(spec: dict[str, Any], loader: Any, native_module: Any) -> dict[str, Any]:
    """Prove both paths pass the unchanged gate and decode equal before timing anything."""
    sheets = normalized_sheets(spec)
    with reference_writer():
        python_doc = generate("xlsx", spec)
    native_doc = generate("xlsx", spec)  # integrated: native writer + unchanged gate
    candidates = {"reference": python_doc.data, "integrated": native_doc.data,
                  "loader-stage": loader.write_workbook(sheets),
                  "direct-stage": native_module.write_workbook(encode_sheets(sheets))}
    for label, data in candidates.items():
        assert_valid_xlsx(data, label)
    if native_doc.validation_state not in {"passed", "passed_with_warnings"}:
        raise Abort(f"integrated native validation_state={native_doc.validation_state!r}")
    reference_decoded = decoded(python_doc.data)
    for label in ("integrated", "loader-stage", "direct-stage"):
        if decoded(candidates[label]) != reference_decoded:
            raise Abort(f"{label}: openpyxl decode differs from the reference writer")
    return {"bytes_python": len(python_doc.data), "bytes_native": len(native_doc.data),
            "validation_state": native_doc.validation_state,
            "gate_passed": True, "decode_equal": True}


def timed(call: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    result = call()
    return (time.perf_counter() - started) * 1000.0, result


def _python_write(sheets: list[Any]) -> bytes:
    with reference_writer():
        return xlsx._write_workbook(sheets)


def _native_write_sample(sheets: list[Any], loader: Any,
                         native_module: Any) -> tuple[float, float, float]:
    total, data = timed(lambda: loader.write_workbook(sheets))
    assert_valid_xlsx(data, "write-stage native")
    encode_started = time.perf_counter()
    payload = encode_sheets(sheets)
    encode_ms = (time.perf_counter() - encode_started) * 1000.0
    call_ms, direct = timed(lambda: native_module.write_workbook(payload))
    assert_valid_xlsx(direct, "write-stage direct")
    return total, encode_ms, call_ms


def write_stage_samples(sheets: list[Any], loader: Any, native_module: Any,
                        samples: int) -> dict[str, Any]:
    """Paired A/B/A/B samples of (a): write stage only, boundary included."""
    series: dict[str, list[float]] = {"python": [], "native": [], "encode": [], "call": []}
    for _ in range(2):  # warmup outside the timed window
        _python_write(sheets)
        loader.write_workbook(sheets)
    payload_bytes = len(encode_sheets(sheets).encode("utf-8"))
    for index in range(samples):
        if index % 2:
            native_result = _native_write_sample(sheets, loader, native_module)
            python_ms, data = timed(lambda: _python_write(sheets))
        else:
            python_ms, data = timed(lambda: _python_write(sheets))
            native_result = _native_write_sample(sheets, loader, native_module)
        assert_valid_xlsx(data, "write-stage reference")
        total, encode_ms, call_ms = native_result
        series["python"].append(python_ms)
        series["native"].append(total)
        series["encode"].append(encode_ms)
        series["call"].append(call_ms)
    return {**series, "payload_bytes": payload_bytes}


def full_generation_samples(spec: dict[str, Any], samples: int) -> dict[str, list[float]]:
    """Paired A/B/A/B samples of (b): full generation, writer-only difference."""
    python_samples: list[float] = []
    native_samples: list[float] = []

    def run_python() -> None:
        with reference_writer():
            document = generate("xlsx", spec)
        assert_valid_xlsx(document.data, "full reference")

    def run_native() -> None:
        document = generate("xlsx", spec)
        if document.validation_state not in {"passed", "passed_with_warnings"}:
            raise Abort(f"full native validation_state={document.validation_state!r}")
        assert_valid_xlsx(document.data, "full native")

    with reference_writer():
        generate("xlsx", spec)
    generate("xlsx", spec)
    for index in range(samples):
        if index % 2:
            native_ms, _ = timed(run_native)
            python_ms, _ = timed(run_python)
        else:
            python_ms, _ = timed(run_python)
            native_ms, _ = timed(run_native)
        python_samples.append(python_ms)
        native_samples.append(native_ms)
    return {"python": python_samples, "native": native_samples}


def _percentile(ordered: list[float], fraction: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {"n": len(ordered), "min": ordered[0], "median": statistics.median(ordered),
            "p95": _percentile(ordered, 0.95), "max": ordered[-1],
            "mean": statistics.fmean(ordered),
            "stdev": statistics.stdev(ordered) if len(ordered) > 1 else 0.0}


def paired_ratio(python_samples: list[float], native_samples: list[float]) -> float:
    return statistics.median(native / python
                             for native, python in zip(native_samples, python_samples))


def machine(native_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Machine/interpreter identity, load average and harness digest for reproducibility."""
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        load = [0.0, 0.0, 0.0]

    def git(*args: str) -> str:
        return subprocess.check_output(
            list(args), cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()

    try:
        git_head = git("git", "rev-parse", "HEAD")
        git_dirty = bool(git("git", "status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        git_head, git_dirty = "unknown", True
    harness_bytes = Path(__file__).read_bytes() + (Path(__file__).parent
                                                   / "native_docgen_ab.py").read_bytes()
    sheet = spec["sheets"][0]
    return {"cpu": cpu, "logical_cores": os.cpu_count(), "python": sys.version.split()[0],
            "platform": platform.platform(), "load_avg_1m_5m_15m": load,
            "git_head": git_head, "git_dirty": git_dirty,
            "harness_sha256": hashlib.sha256(harness_bytes).hexdigest(),
            "native_extension": str(native_path),
            "native_extension_bytes": native_path.stat().st_size,
            "native_extension_mtime": datetime.fromtimestamp(
                native_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "workload_rows": len(sheet["rows"]), "workload_columns": len(sheet["header"]),
            "measured_at": datetime.now(tz=timezone.utc).isoformat()}
