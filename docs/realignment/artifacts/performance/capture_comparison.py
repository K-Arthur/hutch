"""Sequential offline comparison with source/load context; run after checks finish.

From the worktree: .venv/bin/python docs/realignment/artifacts/performance/capture_comparison.py
This does not update a baseline or compare against the legacy machine baseline.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREVIOUS = '4bdd936'
LABEL = 'action-intents'


def source_hashes(root):
    paths = sorted((root/'src/hutch').rglob('*.py')) + [root/'benchmarks/run.py']
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def measure(root, name, revision):
    command = [sys.executable,'-m','benchmarks.run']
    before = source_hashes(root)
    context = {'source_revision':revision,'start_utc':stamp(),'start_load':os.getloadavg(),
               'command':command,'cwd':str(root),'source_sha256':before,'comparison':'sequential after tests, unmodified harness'}
    env = {**os.environ,'PYTHONPATH':str(root/'src'),'HUTCH_BENCH_SOURCE_REVISION':revision}
    with (OUT/f'{name}.log').open('w') as log:
        result = subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    context.update(end_utc=stamp(),end_load=os.getloadavg(),exit_code=result.returncode)
    (OUT/f'{name}.context.json').write_text(json.dumps(context,indent=2)+'\n')
    if source_hashes(root) != before:
        raise RuntimeError('benchmark sources changed while measuring')
    result.check_returncode()
    data = json.loads((root/'benchmarks/results/latest.json').read_text())
    (OUT/f'{name}.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'completed':name,'metrics':data['metrics']}),flush=True)
    return data


def main():
    if sys.argv[1:] == ['--summarize-only']:
        previous = json.loads((OUT/f'previous-{PREVIOUS}-{LABEL}.json').read_text())
        current = json.loads((OUT/f'current-{PREVIOUS}-{LABEL}.json').read_text())
        summarize(current, previous)
        return
    with tempfile.TemporaryDirectory(prefix='hutch-comparison-') as directory:
        source = Path(directory)/'source'
        archive = subprocess.run(['git','archive',PREVIOUS],cwd=ROOT,check=True,capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(source,filter='data')
        if source_hashes(source)['benchmarks/run.py'] != source_hashes(ROOT)['benchmarks/run.py']:
            raise RuntimeError('comparison requires identical benchmark harnesses')
        previous = measure(source,f'previous-{PREVIOUS}-{LABEL}',PREVIOUS)
        current = measure(ROOT,f'current-{PREVIOUS}-{LABEL}',PREVIOUS+'+schema13')
    # Printed change ratios supplement raw distributions, not a claim about
    # live model loading/inference, browser startup or network/physical devices.
    summarize(current, previous)


def summarize(current, previous):
    sys.path.insert(0, str(ROOT))
    from benchmarks.run import compare
    print(json.dumps({'regressions_vs_previous':compare(current,previous)}),flush=True)


if __name__ == '__main__':
    main()
