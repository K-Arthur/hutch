"""Process cleanup must remain unresolved when /proc cannot be inspected."""

from __future__ import annotations

from hutch import procguard


def test_cleanup_helpers_report_unverifiable_when_proc_is_unavailable(monkeypatch):
    monkeypatch.setattr(procguard, "available", lambda: False)
    monkeypatch.setattr(procguard, "boot_id", lambda: "test-boot")

    def unexpected_signal(*_args, **_kwargs):
        raise AssertionError("cleanup must not signal when process identity cannot be inspected")

    monkeypatch.setattr(procguard, "_signal_exact", unexpected_signal)
    record = {"pid": 1234, "pgid": 1234, "starttime": 99, "boot_id": "test-boot"}
    root = procguard.Proc(1234, 1, 1234, 1234, 99, "S")

    results = [
        procguard.end_recorded([record], term_grace=0, kill_grace=0),
        procguard.end_groups([1234], term_grace=0, kill_grace=0),
        procguard.unverified_group(1234),
        procguard.end_tree(root, term_grace=0, kill_grace=0),
    ]

    for result in results:
        assert len(result) == 1
        assert result[0].state == "?"
        assert result[0].pgrp == 1234


def test_missing_boot_identity_does_not_prove_a_saved_process_is_from_another_boot(monkeypatch):
    monkeypatch.setattr(procguard, "available", lambda: False)
    monkeypatch.setattr(procguard, "boot_id", lambda: "")

    result = procguard.end_recorded(
        [{"pid": 1234, "pgid": 1234, "starttime": 99, "boot_id": "saved-boot"}],
        term_grace=0,
        kill_grace=0,
    )

    assert len(result) == 1
    assert result[0].state == "?"
