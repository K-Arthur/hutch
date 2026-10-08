"""Race N processes for ONE schedule occurrence and count the runs they create.

    python docs/realignment/race_schedule.py <path-to-src> <python>

Run it against a checkout of the baseline (commit b3e4b15: prints TOTAL: 6) and against this branch (prints TOTAL: 1).
Everything happens in a throwaway state directory with the offline mock model.
"""
import os, subprocess, sys, tempfile, textwrap, time
from pathlib import Path
src, py = sys.argv[1], sys.argv[2]
state = Path(tempfile.mkdtemp(prefix="race-"))
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
n = len(eng.tick())
time.sleep(0.5)
print(n)
eng.shutdown(timeout=2)
"""
procs = [subprocess.Popen([py, "-I", "-c", body], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
time.sleep(2.0); go.write_text("go")
outs = [p.communicate(timeout=60)[0].strip() for p in procs]
print("per-process runs created:", outs, "TOTAL:", sum(int(o) for o in outs if o.isdigit()))
