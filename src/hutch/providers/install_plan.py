"""Preflight for a local model install: size, free disk, fit and a measured-rate ETA.

The numbers come from three different owners and must not be mixed up:

* **size** is the catalog's figure when the model is a known suggestion; otherwise the
  runtime has not reported a size yet and the honest value is unknown;
* **free disk** belongs to the runtime's model directory (``OLLAMA_MODELS`` or the
  documented ``$HOME/.ollama/models``), and only when the runtime is on this host;
* **time** is derived from a rate Hutch measured on a previous transfer, never from a
  guessed bandwidth. With no sample, the time is unknown.

The plan blocks only what it can prove: a known size that does not fit beside a small
reserve. An unknown size or an unreadable directory is a warning, not a refusal.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from ..fit import Fit, estimate_fit
from ..hardware import GIB, Hardware, probe
from ..models import iso, utcnow
from ..presets import catalog_meta
from .model_names import parse_model_name

DISK_RESERVE_BYTES = 512 * 1024 * 1024
WANTED_CTX = 16384
SPEED_FILE = "install_speed.json"
SPEED_MAX_AGE_SECONDS = 30 * 24 * 60 * 60.0
MIN_SPEED_SAMPLE_BYTES = 16 * 1024 * 1024
MIN_SPEED_SAMPLE_SECONDS = 1.0


@dataclass(frozen=True)
class ModelDir:
    path: Path
    source: str            # "OLLAMA_MODELS" | "default" | "unknown"
    exists: bool


@dataclass(frozen=True)
class SpeedSample:
    bytes_per_second: float
    measured_at: str
    model: str = ""


@dataclass
class InstallPlan:
    model: str
    size_bytes: Optional[int] = None
    size_source: str = "unknown"          # catalog | unknown
    model_dir: str = ""
    model_dir_source: str = "unknown"
    free_bytes: Optional[int] = None
    reserve_bytes: int = DISK_RESERVE_BYTES
    fit_status: str = ""
    fit_label: str = ""
    fit_reason: str = ""
    fit_effective_ctx: int = 0
    fit_estimated: bool = False
    eta_seconds: Optional[float] = None
    speed_bytes_per_s: Optional[float] = None
    speed_measured_at: str = ""
    blocked: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "model": self.model, "size_bytes": self.size_bytes, "size_source": self.size_source,
            "model_dir": self.model_dir, "model_dir_source": self.model_dir_source,
            "free_bytes": self.free_bytes, "reserve_bytes": self.reserve_bytes,
            "fit_status": self.fit_status, "fit_label": self.fit_label, "fit_reason": self.fit_reason,
            "fit_effective_ctx": self.fit_effective_ctx, "fit_estimated": self.fit_estimated,
            "eta_seconds": self.eta_seconds, "speed_bytes_per_s": self.speed_bytes_per_s,
            "speed_measured_at": self.speed_measured_at,
            "blocked": self.blocked, "warnings": list(self.warnings),
        }


def _host_is_loopback(base_url: str) -> bool:
    if not base_url:
        return True
    parts = urlsplit(base_url if "://" in base_url else f"http://{base_url}")
    host = (parts.hostname or "").strip("[]")
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.casefold() == "localhost"


def ollama_model_dir(env: Optional[dict[str, str]] = None) -> ModelDir:
    """The runtime's documented model directory, on this host only."""
    values = os.environ if env is None else env
    configured = (values.get("OLLAMA_MODELS") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        return ModelDir(path, "OLLAMA_MODELS", path.exists())
    path = Path.home() / ".ollama" / "models"
    return ModelDir(path, "default", path.exists())


def free_bytes(path: Path) -> Optional[int]:
    """Free bytes on the filesystem that holds ``path``; the nearest existing parent counts."""
    probe_path = path
    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    try:
        return shutil.disk_usage(probe_path).free
    except OSError:
        return None


def read_speed(state_dir: Optional[Path]) -> Optional[SpeedSample]:
    if state_dir is None:
        return None
    try:
        payload = json.loads((Path(state_dir) / SPEED_FILE).read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    rate = payload.get("bytes_per_second")
    measured = payload.get("measured_at")
    if not isinstance(rate, (int, float)) or rate <= 0 or not isinstance(measured, str):
        return None
    try:
        from datetime import datetime
        when = datetime.fromisoformat(measured.replace("Z", "+00:00"))
        age = (utcnow() - when).total_seconds()
    except (ValueError, TypeError):
        return None
    if age < 0 or age > SPEED_MAX_AGE_SECONDS:
        return None
    return SpeedSample(float(rate), measured, str(payload.get("model") or ""))


def record_rate(state_dir: Optional[Path], rate: Optional[float], model: str = "") -> None:
    """Persist one measured transfer rate, when the caller already measured it."""
    if state_dir is None or rate is None or rate <= 0:
        return
    path = Path(state_dir) / SPEED_FILE
    payload = {"bytes_per_second": round(float(rate), 2), "measured_at": iso(utcnow()), "model": model}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(payload, sort_keys=True), "utf-8")
        os.replace(temporary, path)
    except OSError:
        return


def record_speed(state_dir: Optional[Path], bytes_moved: int, seconds: float, model: str = "") -> None:
    """Persist a rate computed from a transfer, only when the sample is large enough to mean something."""
    if bytes_moved < MIN_SPEED_SAMPLE_BYTES or seconds < MIN_SPEED_SAMPLE_SECONDS:
        return
    record_rate(state_dir, bytes_moved / seconds, model)


def _gib(value: Optional[int]) -> str:
    return f"{(value or 0) / GIB:.1f} GiB"


def _fit(meta: object, hw: Hardware) -> Optional[Fit]:
    try:
        return estimate_fit(meta, hw, WANTED_CTX)  # type: ignore[arg-type]
    except (AttributeError, TypeError, ValueError):
        return None


def build_plan(model: str, *, base_url: str = "", state_dir: Optional[Path] = None,
               hw: Optional[Hardware] = None, meta: object = None) -> InstallPlan:
    """Everything known before a pull, with unknowns left as unknown."""
    parsed = parse_model_name(model)
    name = parsed.canonical()
    meta = meta if meta is not None else catalog_meta(name)
    size = int(meta.size_bytes) if meta is not None and meta.size_bytes else None
    plan = InstallPlan(model=name, size_bytes=size, size_source="catalog" if size else "unknown")

    directory = ollama_model_dir() if _host_is_loopback(base_url) else ModelDir(Path(""), "unknown", False)
    plan.model_dir, plan.model_dir_source = str(directory.path), directory.source
    if directory.source != "unknown":
        plan.free_bytes = free_bytes(directory.path)
    plan.reserve_bytes = max(DISK_RESERVE_BYTES, int(size * 0.05)) if size else DISK_RESERVE_BYTES

    hardware = hw if hw is not None else probe(with_runtimes=False)
    fit = _fit(meta, hardware) if meta is not None else None
    if fit is not None:
        plan.fit_status, plan.fit_label = fit.status, fit.label
        plan.fit_reason, plan.fit_effective_ctx, plan.fit_estimated = fit.reason, fit.effective_ctx, fit.estimated
        if fit.status == "wont_fit":
            plan.warnings.append("the fit estimate says this model will not fit at 16k tokens; "
                                 "installing is still your choice.")

    sample = read_speed(state_dir)
    if sample is not None:
        plan.speed_bytes_per_s, plan.speed_measured_at = sample.bytes_per_second, sample.measured_at
        if size:
            plan.eta_seconds = size / sample.bytes_per_second

    if plan.free_bytes is None:
        if directory.source == "unknown":
            plan.warnings.append("the runtime is not on this host, so free disk space there is unknown.")
        else:
            plan.warnings.append(f"free space on {plan.model_dir} could not be read; the runtime will stop "
                                 "if the disk fills.")
    elif size is None:
        plan.warnings.append(f"the download size is unknown; {_gib(plan.free_bytes)} is free on {plan.model_dir}.")
    if parsed.host.casefold() in ("hf.co", "huggingface.co"):
        plan.warnings.append("a gated Hugging Face repo needs the runtime's own token; "
                             "Hutch never puts a token in a URL.")
    if parsed.digest:
        plan.warnings.append("a pinned digest is passed to the runtime unchanged; support depends on its version.")

    if size is not None and plan.free_bytes is not None and plan.free_bytes < size + plan.reserve_bytes:
        plan.blocked = (f"{name} needs about {_gib(size)} plus {_gib(plan.reserve_bytes)} free; "
                        f"{plan.model_dir} has {_gib(plan.free_bytes)} free. "
                        "Remove a model or choose a smaller one.")
    return plan
