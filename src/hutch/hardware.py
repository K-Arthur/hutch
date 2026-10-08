"""Hardware probe (LM-4): RAM, GPU memory, Apple Silicon, and which model runtimes are installed or running.

First-run failure #1 for local agents is memory fit, not installation: a model that does not fit either fails to
load or silently runs on the CPU at a fraction of the speed with no error (research, "first-run friction"). So
the dashboard asks the machine, then tells the user what fits.

Every OS touch goes through an injectable reader, so the probe is unit-tested against canned Mac / NVIDIA /
CPU-only machines instead of only ever being exercised on the author's laptop.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

GIB = 1024 ** 3


@dataclass
class Gpu:
    name: str
    vendor: str                 # nvidia | amd | apple | intel | other
    vram_gb: Optional[float]    # dedicated memory; None when unknown
    integrated: bool = False    # shares system RAM and usually cannot accelerate llama.cpp/Ollama usefully
    free_gb: Optional[float] = None


@dataclass
class RuntimeInfo:
    name: str                   # ollama | llama.cpp | lmstudio
    installed: bool = False
    reachable: bool = False
    url: str = ""
    version: str = ""
    detail: str = ""


@dataclass
class Hardware:
    os: str = ""
    arch: str = ""
    cpu: str = ""
    cores: int = 0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    gpus: list[Gpu] = field(default_factory=list)
    apple_silicon: bool = False
    runtimes: list[RuntimeInfo] = field(default_factory=list)

    # ---- what models may use
    @property
    def accelerator(self) -> str:
        """gpu | unified | cpu: where model weights will actually live."""
        if self.apple_silicon:
            return "unified"
        if any(g.vram_gb and not g.integrated and g.vendor in ("nvidia", "amd") for g in self.gpus):
            return "gpu"
        return "cpu"

    @property
    def budget_gb(self) -> float:
        """Memory available to model weights + KV cache, with headroom for the OS and runtime."""
        if self.accelerator == "gpu":
            best = max((g.free_gb if g.free_gb is not None else g.vram_gb or 0.0) for g in self.gpus if not g.integrated)
            return round(best * 0.92, 2)
        if self.accelerator == "unified":
            return round(min(self.ram_total_gb * 0.70, self.ram_available_gb * 0.90 + 0.1 * self.ram_total_gb), 2)
        # CPU: only what is actually free right now counts; a swapping model is useless
        return round(max(0.0, min(self.ram_total_gb * 0.70, self.ram_available_gb * 0.85)), 2)

    @property
    def tier(self) -> str:
        b = self.budget_gb
        return ("tiny" if b < 3 else "small" if b < 6.5 else "medium" if b < 12 else "large" if b < 24 else "xl")

    @property
    def summary(self) -> str:
        acc = {"gpu": "discrete GPU", "unified": "Apple Silicon unified memory", "cpu": "CPU only"}[self.accelerator]
        return f"{acc}, {self.budget_gb:.1f} GiB usable for models ({self.tier} tier)"

    @property
    def notes(self) -> list[str]:
        out = []
        if self.accelerator == "cpu":
            ig = [g for g in self.gpus if g.integrated]
            if ig:
                out.append(f"{ig[0].name} is an integrated GPU sharing system RAM; models run on the CPU "
                           "unless the runtime has Vulkan/ROCm support for it.")
            out.append("CPU inference works but is slow: expect a few tokens/second on 7B-class models, and "
                       "long prompts can take minutes before the first token.")
        if self.ram_available_gb and self.ram_total_gb and self.ram_available_gb < self.ram_total_gb * 0.35:
            out.append(f"Only {self.ram_available_gb:.1f} of {self.ram_total_gb:.1f} GiB RAM is free right now; "
                       "close other applications before loading a larger model.")
        return out


# ---------------------------------------------------------------- readers (injectable)

def _read(path: str) -> Optional[str]:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def _run(argv: list[str], timeout: float = 3.0) -> Optional[str]:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _http_get(url: str, timeout: float = 0.6) -> Optional[str]:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - fixed loopback URLs
            return r.read(65536).decode("utf-8", "replace")
    except Exception:
        return None


@dataclass
class Readers:
    read: Callable[[str], Optional[str]] = _read
    run: Callable[[list[str]], Optional[str]] = _run
    http_get: Callable[[str], Optional[str]] = _http_get
    which: Callable[[str], Optional[str]] = shutil.which
    system: str = field(default_factory=lambda: sys.platform)
    machine: str = field(default_factory=platform.machine)
    cpu_count: int = field(default_factory=lambda: os.cpu_count() or 1)
    env: dict = field(default_factory=lambda: dict(os.environ))
    listdir: Callable[[str], list[str]] = lambda p: sorted(os.listdir(p)) if os.path.isdir(p) else []


# ---------------------------------------------------------------- probes

def _probe_memory(r: Readers) -> tuple[float, float]:
    if r.system == "darwin":
        total = r.run(["sysctl", "-n", "hw.memsize"])
        vm = r.run(["vm_stat"]) or ""
        page = int(m.group(1)) if (m := re.search(r"page size of (\d+) bytes", vm)) else 16384
        free = sum(int(m.group(1)) for k in ("Pages free", "Pages inactive", "Pages speculative")
                   if (m := re.search(rf"{k}:\s+(\d+)", vm)))
        t = int(total) / GIB if total and total.strip().isdigit() else 0.0
        return t, (free * page) / GIB if free else t * 0.5
    info = r.read("/proc/meminfo") or ""
    tot = re.search(r"MemTotal:\s+(\d+) kB", info)
    avail = re.search(r"MemAvailable:\s+(\d+) kB", info)
    t = int(tot.group(1)) * 1024 / GIB if tot else 0.0
    return t, (int(avail.group(1)) * 1024 / GIB if avail else 0.0)


def _probe_cpu(r: Readers) -> str:
    if r.system == "darwin":
        return (r.run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "").strip() or "Apple Silicon"
    info = r.read("/proc/cpuinfo") or ""
    m = re.search(r"model name\s*:\s*(.+)", info)
    return m.group(1).strip() if m else ""


def _probe_gpus(r: Readers) -> list[Gpu]:
    gpus: list[Gpu] = []
    if r.which("nvidia-smi"):
        out = r.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"])
        for line in (out or "").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[1].replace(".", "").isdigit():
                gpus.append(Gpu(parts[0], "nvidia", float(parts[1]) / 1024, False, float(parts[2]) / 1024))
    # sysfs: AMD / Intel / anything the kernel exposes (also catches an iGPU)
    for card in r.listdir("/sys/class/drm"):
        if not re.fullmatch(r"card\d+", card):
            continue
        base = f"/sys/class/drm/{card}/device"
        vid = (r.read(f"{base}/vendor") or "").strip().lower()
        vendor = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}.get(vid)
        if vendor is None or (vendor == "nvidia" and gpus):
            continue
        vram = r.read(f"{base}/mem_info_vram_total")
        gtt = r.read(f"{base}/mem_info_gtt_total")
        vram_gb = int(vram) / GIB if vram and vram.strip().isdigit() else None
        # an AMD APU reports a small carve-out of system RAM as "VRAM"; treat it as integrated
        integrated = vendor == "intel" or (vendor == "amd" and (vram_gb is None or vram_gb < 3.0 or bool(gtt) and
                                                                vram_gb < 3.0))
        name = {"amd": "AMD GPU", "intel": "Intel GPU", "nvidia": "NVIDIA GPU"}[vendor]
        uevent = r.read(f"{base}/uevent") or ""
        if m := re.search(r"PRODUCT_NAME=(.+)", uevent):
            name = m.group(1).strip()
        if not any(g.vendor == vendor and g.vram_gb == vram_gb for g in gpus):
            gpus.append(Gpu(name, vendor, vram_gb, integrated))
    _name_gpus_from_lspci(r, gpus)
    return gpus


_LSPCI_RE = re.compile(r"^\S+ (?:VGA compatible controller|3D controller|Display controller): "
                       r"(.+?)(?: \(rev [0-9a-f]+\))?$")


def _tidy_pci_name(raw: str) -> str:
    raw = re.sub(r"Advanced Micro Devices, Inc\. \[AMD/ATI\]\s*", "AMD ", raw)
    raw = re.sub(r"^(NVIDIA|Intel) Corporation\s*", r"\1 ", raw)
    return raw.strip()


def _name_gpus_from_lspci(r: Readers, gpus: list[Gpu]) -> None:
    """sysfs gives vendor and memory but not a product name; `lspci` (when present) does."""
    if not r.which("lspci"):
        return
    names = [_tidy_pci_name(m.group(1)) for line in (r.run(["lspci"]) or "").splitlines()
             if (m := _LSPCI_RE.match(line))]
    for g in gpus:
        if g.name in ("AMD GPU", "Intel GPU", "NVIDIA GPU"):
            key = {"amd": "AMD", "intel": "Intel", "nvidia": "NVIDIA"}.get(g.vendor, "")
            g.name = next((n for n in names if n.startswith(key)), g.name)


def _probe_runtimes(r: Readers) -> list[RuntimeInfo]:
    ollama_url = (r.env.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    if not ollama_url.startswith("http"):
        ollama_url = "http://" + ollama_url
    specs = [
        ("ollama", ollama_url, "/api/version", ["ollama"]),
        ("llama.cpp", "http://localhost:8080", "/v1/models", ["llama-server"]),
        ("lmstudio", "http://localhost:1234", "/v1/models", ["lms"]),
    ]
    results: dict[str, RuntimeInfo] = {}

    def check(name, url, path, bins):
        info = RuntimeInfo(name=name, url=url, installed=any(r.which(b) for b in bins))
        body = r.http_get(url + path)
        if body is not None:
            info.reachable = True
            if name == "ollama":
                m = re.search(r'"version"\s*:\s*"([^"]+)"', body)
                info.version = m.group(1) if m else ""
        info.detail = ("running" if info.reachable else "installed but not running" if info.installed
                       else "not found")
        results[name] = info

    threads = [threading.Thread(target=check, args=s) for s in specs]
    [t.start() for t in threads]
    [t.join(timeout=3) for t in threads]
    return [results[n] for n, *_ in specs if n in results]


def probe(readers: Optional[Readers] = None, with_runtimes: bool = True) -> Hardware:
    r = readers or Readers()
    total, avail = _probe_memory(r)
    apple = r.system == "darwin" and r.machine in ("arm64", "aarch64")
    gpus = _probe_gpus(r)
    if apple:
        gpus = [Gpu("Apple GPU (unified memory)", "apple", total, False, avail)]
    return Hardware(
        os=r.system, arch=r.machine, cpu=_probe_cpu(r), cores=r.cpu_count, ram_total_gb=round(total, 2),
        ram_available_gb=round(avail, 2), gpus=gpus, apple_silicon=apple,
        runtimes=_probe_runtimes(r) if with_runtimes else [])
