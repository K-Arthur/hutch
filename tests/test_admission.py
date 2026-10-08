"""Real kernel locks: bounded local callers, FIFO waits, cancellation and crash release."""
from __future__ import annotations

import multiprocessing
import os
import sys
import threading

import pytest

from hutch.admission import AdmissionCancelled, AdmissionError, QueueFull, inference_slot

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux inference admission")


def test_one_caller_and_eight_waiters_without_same_model_bypass(tmp_path):
    release = threading.Event()
    signals = [threading.Event() for _ in range(9)]
    threads, errors, calls = [], [], []
    count, peak = 0, 0
    lock = threading.Lock()

    def caller(index):
        nonlocal count, peak
        try:
            with inference_slot(tmp_path, f"run-{index}", "ollama/same", lambda: False,
                                on_wait=lambda position: signals[index].set()):
                with lock:
                    count += 1
                    peak = max(peak, count)
                    calls.append(index)
                signals[index].set()
                assert release.wait(5)
                with lock:
                    count -= 1
        except Exception as exc:
            errors.append(exc)

    try:
        for index in range(9):
            thread = threading.Thread(target=caller, args=(index,))
            threads.append(thread)
            thread.start()
            assert signals[index].wait(2)
        assert calls == [0]
        with pytest.raises(QueueFull, match="eight waiting"):
            with inference_slot(tmp_path, "overflow", "ollama/same", lambda: False):
                pytest.fail("a tenth caller was admitted")
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=3)
    assert not errors and all(not thread.is_alive() for thread in threads)
    assert peak == 1 and calls == list(range(9))


def _process_caller(state, name, pipe):
    try:
        with inference_slot(state, name, "ollama/same", lambda: False,
                            on_wait=lambda position: pipe.send(("waiting", position))):
            pipe.send(("entered", os.getpid()))
            if not pipe.poll(15) or pipe.recv() != "release":
                raise RuntimeError("test did not release the process")
    except Exception as exc:
        pipe.send(("error", str(exc)))
        raise
    finally:
        pipe.close()


def _recv(pipe):
    assert pipe.poll(5), "admission process did not report"
    return pipe.recv()


def test_separate_processes_serialize_and_sigkill_releases_slot_and_ticket(tmp_path):
    mp = multiprocessing.get_context("spawn")
    pipes, procs = [], []
    try:
        for name in ("owner", "waiter"):
            parent, child = mp.Pipe()
            proc = mp.Process(target=_process_caller, args=(tmp_path, name, child))
            pipes.append(parent)
            procs.append(proc)
            proc.start()
            child.close()
            report = _recv(parent)
            assert report[0] == ("entered" if name == "owner" else "waiting"), report
        assert not pipes[1].poll(0), "the second process overlapped the held call"
        procs[0].kill()
        procs[0].join(timeout=3)
        assert procs[0].exitcode == -9
        assert _recv(pipes[1])[0] == "entered"
        pipes[1].send("release")
        procs[1].join(timeout=3)
        assert procs[1].exitcode == 0
        with inference_slot(tmp_path, "after-crash", "ollama/other", lambda: False):
            pass  # stale ticket text does not retain ownership after process death
    finally:
        for proc, pipe in zip(procs, pipes):
            if proc.is_alive():
                try:
                    pipe.send("release")
                except (BrokenPipeError, EOFError):
                    pass
        for proc in procs:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
        for pipe in pipes:
            pipe.close()


def test_cancellation_removes_a_waiter_without_entering_inference(tmp_path):
    stopped, waiting = threading.Event(), threading.Event()
    outcomes = []

    def waiter():
        try:
            with inference_slot(tmp_path, "cancelled", "ollama/same", stopped.is_set,
                                on_wait=lambda position: waiting.set()):
                outcomes.append("entered")
        except AdmissionCancelled:
            outcomes.append("cancelled")

    with inference_slot(tmp_path, "held", "ollama/same", lambda: False):
        thread = threading.Thread(target=waiter)
        thread.start()
        try:
            assert waiting.wait(2)
        finally:
            stopped.set()
            thread.join(timeout=2)
        assert not thread.is_alive() and outcomes == ["cancelled"]
    with inference_slot(tmp_path, "next", "ollama/same", lambda: False):
        pass


def test_an_occupied_unreadable_ticket_fails_closed(tmp_path):
    import fcntl
    directory = tmp_path / "inference"
    directory.mkdir(mode=0o700)
    with (directory / "ticket-0.lock").open("w+") as corrupt:
        fcntl.flock(corrupt.fileno(), fcntl.LOCK_EX)
        corrupt.write("incomplete metadata")
        corrupt.flush()
        with pytest.raises(AdmissionError, match="unreadable"):
            with inference_slot(tmp_path, "refused", "ollama/same", lambda: False):
                pytest.fail("an unknown owner was bypassed")
    with inference_slot(tmp_path, "restored", "ollama/same", lambda: False):
        pass
