"""Canonical environment paths must name the read-only mounted dependency tree."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hutch import sandbox
from hutch.workspace.manager import kernel_env


def test_sandbox_dependency_paths_resolve_virtualenv_aliases(tmp_path, monkeypatch):
    real = tmp_path / "real-env"
    packages = real / "lib/python3.13/site-packages"
    packages.mkdir(parents=True)
    alias = tmp_path / "alias-env"
    alias.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr("sysconfig.get_paths", lambda: {"purelib": str(alias / "lib/python3.13/site-packages")})
    worker = sandbox.offline_worker_environment({"OPENAI_API_KEY": "fixture-never-inherited"}, str(tmp_path / "state"), 30, "/fixture-broker")
    kernel = kernel_env(tmp_path / "workspace", 1)
    for env in (worker, kernel):
        paths = env["PYTHONPATH"].split(os.pathsep)
        assert str(packages) in paths
        assert all(str(alias) not in path for path in paths)
        assert "OPENAI_API_KEY" not in env


@pytest.mark.skipif(sys.platform != "linux", reason="requires real Linux strict containment")
def test_symlinked_environment_still_starts_a_real_contained_kernel(tmp_path):
    if not sandbox.status().ok:
        pytest.skip("host lacks strict kernel containment")
    root = Path(__file__).resolve().parents[1]
    alias = tmp_path / "venv-alias"
    alias.symlink_to(Path(sys.prefix).resolve(), target_is_directory=True)
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root)))}
    result = subprocess.run([str(alias / "bin/python"), "-m", "pytest", "-q",
        "tests/test_native_containment.py::test_effective_backend_identity_and_argv_are_the_strict_profile",
        f"--basetemp={tmp_path / 'native'}", "--tb=short"], cwd=root, env=environment,
        capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout, "a skipped child check is not native evidence"
