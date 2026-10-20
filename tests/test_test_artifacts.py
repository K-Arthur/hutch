from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.artifacts import artifact_path, repository_path


def test_artifacts_use_the_configured_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HUTCH_TEST_ARTIFACTS_DIR", str(tmp_path / "run-artifacts"))

    assert artifact_path("browser/phone.png") == tmp_path / "run-artifacts/browser/phone.png"


def test_repository_inputs_do_not_depend_on_the_artifact_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HUTCH_TEST_ARTIFACTS_DIR", str(tmp_path / "run-artifacts"))

    assert repository_path("src/hutch/server/static/app.js").is_file()


@pytest.mark.parametrize("path", ["../outside.txt", "/tmp/outside.txt"])
def test_artifact_paths_cannot_escape_the_configured_root(monkeypatch, tmp_path, path):
    monkeypatch.setenv("HUTCH_TEST_ARTIFACTS_DIR", str(tmp_path / "run-artifacts"))

    with pytest.raises(ValueError, match="within their artifact root"):
        artifact_path(path)


@pytest.mark.parametrize("path", ["../outside.py", "/tmp/outside.py"])
def test_repository_paths_cannot_escape_the_candidate_checkout(path):
    with pytest.raises(ValueError, match="within the candidate checkout"):
        repository_path(path)
