"""Preflight arithmetic and the measured transfer rate.

The plan must never turn "unknown" into a number: an unreadable directory is None, a
catalog size is labelled, and a refusal only happens when a known size does not fit.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hutch.hardware import GIB
from hutch.models import iso, utcnow
from hutch.providers.base import ModelMeta
from hutch.providers.install_plan import (
    DISK_RESERVE_BYTES, InstallPlan, _host_is_loopback, build_plan, free_bytes,
    ollama_model_dir, read_speed, record_rate, record_speed,
)
from hutch.providers.install_jobs import InstallJob, _apply

MIB = 1024 * 1024


def meta(size: int = 100 * MIB) -> ModelMeta:
    return ModelMeta(name="qwen2.5:3b", params_b=3.1, quant="Q4_K_M", size_bytes=size,
                     n_layers=36, n_kv_heads=2, head_dim=128, max_context=32768)


def hw(budget_gb: float = 8.0):
    return SimpleNamespace(budget_gb=budget_gb)


def test_model_dir_comes_from_ollama_models_when_set():
    directory = ollama_model_dir({"OLLAMA_MODELS": "/var/lib/ollama/models"})
    assert directory.path == Path("/var/lib/ollama/models")
    assert directory.source == "OLLAMA_MODELS"


def test_model_dir_default_is_the_documented_path():
    directory = ollama_model_dir({})
    assert directory.path == Path.home() / ".ollama" / "models"
    assert directory.source == "default"


@pytest.mark.parametrize("url,loopback", [
    ("http://127.0.0.1:11434", True),
    ("http://localhost:11434", True),
    ("http://[::1]:11434", True),
    ("", True),
    ("http://192.168.1.5:11434", False),
    ("https://example.com", False),
])
def test_loopback_detection(url, loopback):
    assert _host_is_loopback(url) is loopback


def test_a_non_loopback_runtime_reports_unknown_disk(monkeypatch):
    plan = build_plan("qwen2.5:3b", base_url="http://192.168.1.5:11434",
                      hw=hw(), meta=meta())
    assert plan.model_dir_source == "unknown"
    assert plan.free_bytes is None
    assert any("not on this host" in warning for warning in plan.warnings)
    assert plan.blocked == ""


def test_a_known_size_that_does_not_fit_blocks_with_the_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.install_plan.free_bytes", lambda path: 100 * MIB)
    plan = build_plan("qwen2.5:3b", state_dir=tmp_path, hw=hw(), meta=meta(2 * GIB))
    assert plan.free_bytes == 100 * MIB
    assert "needs about 2.0 GiB" in plan.blocked
    assert plan.reserve_bytes >= DISK_RESERVE_BYTES


def test_an_unknown_size_is_a_warning_not_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.install_plan.free_bytes", lambda path: 100 * MIB)
    plan = build_plan("unknown:1b", state_dir=tmp_path, hw=hw())
    assert plan.size_bytes is None
    assert plan.size_source == "unknown"
    assert plan.blocked == ""
    assert any("size is unknown" in warning for warning in plan.warnings)


def test_an_unreadable_directory_is_unknown_not_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.install_plan.free_bytes", lambda path: None)
    plan = build_plan("qwen2.5:3b", state_dir=tmp_path, hw=hw(), meta=meta())
    assert plan.free_bytes is None
    assert plan.blocked == ""
    assert any("could not be read" in warning for warning in plan.warnings)


def test_a_measured_rate_produces_an_eta(tmp_path, monkeypatch):
    record_rate(tmp_path, 10 * MIB, "qwen2.5:3b")
    monkeypatch.setattr("hutch.providers.install_plan.free_bytes", lambda path: 10 * GIB)
    plan = build_plan("qwen2.5:3b", state_dir=tmp_path, hw=hw(), meta=meta(100 * MIB))
    assert plan.speed_bytes_per_s == pytest.approx(10 * MIB, rel=0.01)
    assert plan.eta_seconds == pytest.approx(10.0, rel=0.05)


def test_an_old_speed_sample_is_ignored(tmp_path):
    old = iso(utcnow() - timedelta(days=45))
    (tmp_path / "install_speed.json").write_text(json.dumps(
        {"bytes_per_second": 123, "measured_at": old, "model": "x"}), "utf-8")
    assert read_speed(tmp_path) is None


def test_a_small_sample_is_not_recorded(tmp_path):
    record_speed(tmp_path, 1 * MIB, 30.0)
    assert read_speed(tmp_path) is None
    record_speed(tmp_path, 32 * MIB, 2.0)
    assert read_speed(tmp_path) is not None


def test_fit_is_reported_for_a_catalog_estimate(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.install_plan.free_bytes", lambda path: 10 * GIB)
    plan = build_plan("qwen2.5:3b", state_dir=tmp_path, hw=hw(), meta=meta(2 * GIB))
    assert plan.fit_status in ("fits", "tight", "wont_fit")
    assert plan.fit_label
    assert plan.fit_reason


def test_free_bytes_uses_the_nearest_existing_parent(tmp_path):
    assert free_bytes(tmp_path / "not" / "created" / "yet") is not None


def test_the_live_rate_is_measured_from_new_bytes_only(monkeypatch):
    ticks = iter([100.0, 101.0, 102.0])
    monkeypatch.setattr("hutch.providers.install_jobs.time.monotonic", lambda: next(ticks))
    job = InstallJob(id="j", model="m")
    _apply(job, {"status": "pulling", "digest": "sha256:a", "total": 1000, "completed": 0})
    _apply(job, {"status": "pulling", "digest": "sha256:a", "total": 1000, "completed": 500})
    assert job.bytes_per_second == pytest.approx(500.0)
    _apply(job, {"status": "pulling", "digest": "sha256:a", "total": 1000, "completed": 1000})
    assert job.bytes_per_second == pytest.approx(500.0, rel=0.01)
    assert job.eta_seconds == pytest.approx(0.0, abs=0.01)


def test_a_resumed_blob_does_not_inflate_the_rate(monkeypatch):
    ticks = iter([100.0, 101.0])
    monkeypatch.setattr("hutch.providers.install_jobs.time.monotonic", lambda: next(ticks))
    job = InstallJob(id="j", model="m")
    _apply(job, {"status": "pulling", "digest": "sha256:a", "total": 2000, "completed": 1500})
    _apply(job, {"status": "pulling", "digest": "sha256:a", "total": 2000, "completed": 1600})
    assert job.bytes_per_second == pytest.approx(100.0)
