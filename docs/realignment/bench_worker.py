"""Cost of the process executor: start-up latency and resident memory of one worker, vs the in-process executor.

    python docs/realignment/bench_worker.py [repeats]

Offline (mock model). 'dispatch->terminal' is wall time from dispatch_pending() to the run being terminal for a run that does 4 tool
steps; 'worker RSS' is the worker's resident set while it waits on an approval (the common long-lived state).
"""
import os, re, statistics, sys, tempfile, time
from pathlib import Path
state = tempfile.mkdtemp(prefix="bench-worker-")
os.environ["HUTCH_STATE_DIR"] = state
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hutch.config import get_config
from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, RunStatus
from hutch.store import Store

cfg, st = get_config(), None
st = Store(cfg)
auto = st.create_bot(Bot(name="auto", model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.auto))
ask = st.create_bot(Bot(name="ask", model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.ask))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 7

def wait(cond, t=30):
    end = time.time() + t
    while time.time() < end:
        if cond(): return True
        time.sleep(0.005)
    return False

def one(executor):
    eng = Engine(cfg, st, executor=executor)
    t0 = time.perf_counter()
    run = eng.submit(auto, "research the news and write a report")
    eng.dispatch_pending()
    assert wait(lambda: st.get_run(run.id).terminal)
    dt = (time.perf_counter() - t0) * 1000
    eng.shutdown(timeout=3)
    return dt

def rss_mb(pid):
    m = re.search(r"VmRSS:\s+(\d+) kB", Path(f"/proc/{pid}/status").read_text())
    return int(m.group(1)) / 1024

for ex in ("thread", "process"):
    one(ex)                                    # warm
    xs = [one(ex) for _ in range(n)]
    print(f"{ex:8} dispatch->terminal: median {statistics.median(xs):7.1f} ms   min {min(xs):7.1f}   max {max(xs):7.1f}   (n={n})")

eng = Engine(cfg, st, executor="process")
run = eng.submit(ask, "write a report"); eng.dispatch_pending()
assert wait(lambda: st.get_run(run.id).status is RunStatus.waiting_approval)
pid = st.get_run(run.id).pgid
print(f"worker RSS while waiting for an approval: {rss_mb(pid):.1f} MB   (supervisor process: {rss_mb(os.getpid()):.1f} MB)")
eng.stop_run(run.id); wait(lambda: st.get_run(run.id).terminal); eng.shutdown(timeout=3)
