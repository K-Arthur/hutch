"""Race N processes for ONE schedule occurrence and count the runs they create.

    python docs/realignment/race_schedule.py <path-to-src> <python>

Run it against a checkout of the baseline (commit b3e4b15: prints TOTAL: 6) and against this branch (prints TOTAL: 1).
The current scheduler claims the occurrence without dispatching model work; the baseline fallback retains its original tick
path. All generated state is temporary unless ``HUTCH_REALIGNMENT_KEEP_STATE=1`` is set.
"""
import atexit, os, shutil, signal, subprocess, sys, tempfile, textwrap, time
from pathlib import Path
src, py = str(Path(sys.argv[1]).resolve()), sys.argv[2]
state = Path(tempfile.mkdtemp(prefix="race-"))
procs = []

def cleanup():
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if os.environ.get("HUTCH_REALIGNMENT_KEEP_STATE") == "1":
        print("kept state:", state)
    else:
        shutil.rmtree(state, ignore_errors=True)

atexit.register(cleanup)
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(128 + signum))
env = dict(os.environ, HUTCH_STATE_DIR=str(state), PYTHONPATH=src)
setup = f"""
import sys; sys.path.insert(0, {src!r})
from hutch.config import get_config
from hutch.store import Store
from hutch.models import Bot, Schedule
s = Store(get_config())
s.create_bot(Bot(name='nightly', model='mock/demo', tools=['files'], schedule=Schedule(cron='* * * * *', timezone='UTC'), created_at='2026-01-01T00:00:00+00:00'))
s.close()
"""
subprocess.run([py, "-I", "-c", setup], env=env, check=True)
go = state / "GO"
body = f"""
import sys, time; sys.path.insert(0, {src!r})
from pathlib import Path
from hutch.config import get_config
from hutch.store import Store
from hutch.engine import Engine
st = Store(get_config())
while not Path({str(go)!r}).exists(): time.sleep(0.001)
eng = Engine(get_config(), st, max_concurrent=1)
n = len(eng.scheduler_claims()) if hasattr(eng, "scheduler_claims") else len(eng.tick())
print(n)
eng.shutdown(timeout=2)
"""
for _ in range(6):
    procs.append(subprocess.Popen([py, "-I", "-c", body], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
time.sleep(2.0); go.write_text("go")
outs = []
for proc in procs:
    out, err = proc.communicate(timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"race worker {proc.pid} exited {proc.returncode}: {err.strip()}")
    outs.append(out.strip())
print("per-process runs created:", outs, "TOTAL:", sum(int(o) for o in outs if o.isdigit()))
