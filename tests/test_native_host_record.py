"""Reject a mislabeled self-hosted runner instead of producing misleading evidence."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("native_host_record", Path(__file__).resolve().parents[1] / "scripts/record_native_host.py")
record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(record)


@pytest.mark.parametrize("target,system,machine,version", [
    ("linux-x64", "Linux", "x86_64", "ubuntu 24.04"),
    ("windows-x64", "Windows", "AMD64", "10.0.26100"),
    ("macos-arm64", "Darwin", "arm64", "14.7"),
    ("macos-x64", "Darwin", "x86_64", "15.4"),
])
def test_native_runner_target_matches_actual_host(target, system, machine, version):
    record.validate_target(target, {"system": system, "machine": machine, "os_version": version, "python_bits": 64})


@pytest.mark.parametrize("changes", [
    {"system": "Darwin"}, {"machine": "aarch64"}, {"python_bits": 32},
    {"os_version": "arch rolling"}, {"os_version": "ubuntu 22.04"},
])
def test_mislabeled_linux_host_is_rejected(changes):
    report = {"system": "Linux", "machine": "x86_64", "os_version": "ubuntu 24.04", "python_bits": 64, **changes}
    with pytest.raises(ValueError):
        record.validate_target("linux-x64", report)


def test_older_macos_is_rejected():
    with pytest.raises(ValueError, match="version 14"):
        record.validate_target("macos-x64", {"system": "Darwin", "machine": "x86_64", "os_version": "13.7", "python_bits": 64})
