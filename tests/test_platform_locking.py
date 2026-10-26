"""Run the same kernel-exclusion tests on each OS; mocks are not native evidence."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from hutch.platforms import locking


CHILD = """
import os,sys
from hutch.platforms import locking
fd=os.open(sys.argv[1], os.O_CREAT|os.O_RDWR, 0o600)
try:
    mode=locking.LOCK_SH if sys.argv[2]=='shared' else locking.LOCK_EX
    try:
        locking.flock(fd, mode|locking.LOCK_NB)
    except BlockingIOError:
        print('blocked',flush=True)
        sys.exit(23)
    print('acquired',flush=True)
    if sys.argv[2]=='hold':sys.stdin.readline()
finally:
    os.close(fd)
"""


def child(path, mode):
    return subprocess.run([sys.executable, "-c", CHILD, str(path), mode], capture_output=True, text=True, timeout=8)


def test_exclusive_lock_is_cross_process_and_preserves_position_and_bytes(tmp_path):
    path = tmp_path / "shared.lock"
    path.write_bytes(b"unchanged lock contents")
    with path.open("r+b") as stream:
        stream.seek(7)
        locking.flock(stream.fileno(), locking.LOCK_EX)
        assert stream.tell() == 7
        denied = child(path, "exclusive")
        assert denied.returncode == 23 and denied.stdout.strip() == "blocked", denied.stderr
        locking.flock(stream.fileno(), locking.LOCK_UN)
        admitted = child(path, "exclusive")
        assert admitted.returncode == 0 and admitted.stdout.strip() == "acquired", admitted.stderr
        assert stream.tell() == 7
    assert path.read_bytes() == b"unchanged lock contents"


def test_shared_readers_can_coexist_but_exclude_an_exclusive_writer(tmp_path):
    path = tmp_path / "readers.lock"
    with path.open("w+b") as stream:
        locking.flock(stream.fileno(), locking.LOCK_SH)
        reader = child(path, "shared")
        assert reader.returncode == 0, reader.stderr
        writer = child(path, "exclusive")
        assert writer.returncode == 23, writer.stderr
        locking.flock(stream.fileno(), locking.LOCK_UN)


def test_kernel_releases_lock_when_the_holder_exits_without_unlocking(tmp_path):
    path = tmp_path / "owner.lock"
    process = subprocess.Popen([sys.executable, "-c", CHILD, str(path), "hold"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
        assert ready.get(timeout=8).strip() == "acquired"
        with path.open("r+b") as stream:
            with pytest.raises(BlockingIOError):
                locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
            process.kill()
            process.wait(timeout=5)
            locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
            locking.flock(stream.fileno(), locking.LOCK_UN)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()


def test_unix_keeps_the_exact_existing_flock_implementation():
    if os.name == "nt":
        assert locking.BACKEND == "windows-lockfileex"
    else:
        import fcntl
        assert locking.flock is fcntl.flock
        assert locking.LOCK_EX == fcntl.LOCK_EX and locking.LOCK_NB == fcntl.LOCK_NB
    assert locking.CONTRACT_VERSION == 1
