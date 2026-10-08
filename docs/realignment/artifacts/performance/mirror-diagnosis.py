import json, pathlib, tempfile, time, os, statistics
from hutch.config import hutchConfig
from hutch.models import Bot, Run, Event, EventType
from hutch.store import Store
from hutch.transcript_mirror import TranscriptMirror
real_start = TranscriptMirror.start
results = []
for mode in ('running', 'paused-fixture', 'running'):
    with tempfile.TemporaryDirectory(prefix='hutch-mirror-profile-') as directory:
        if mode == 'paused-fixture':
            TranscriptMirror.start = lambda self: None
        else:
            TranscriptMirror.start = real_start
        store = Store(hutchConfig(state_dir=pathlib.Path(directory)))
        bot = store.create_bot(Bot(name='profile'))
        run = store.create_run(Run(bot_id=bot.id, prompt='profile'))
        samples = []
        for j in range(5):
            t = time.perf_counter()
            for i in range(20000):
                store.append_event(Event(run_id=run.id,type=EventType.log,data={'i':i,'pad':'x'*64}))
            store.flush_events()
            samples.append(20000/(time.perf_counter()-t))
        before = store._mirror.status(run.id)
        t = time.perf_counter()
        if mode == 'running': store.flush_transcripts(timeout=30)
        tail_ms = (time.perf_counter()-t)*1000
        row = {'mode':mode,'samples':samples,'median':statistics.median(samples),'mirror_before_final_flush':before,
            'tail_delivery_ms':tail_ms,'synchronous':store._db.execute('PRAGMA synchronous').fetchone()[0], 'load':os.getloadavg()}
        results.append(row)
        print(json.dumps(row),flush=True)
        store.close()
TranscriptMirror.start = real_start
pathlib.Path('docs/realignment/artifacts/performance/mirror-diagnosis.json').write_text(json.dumps(results,indent=2)+'\n')
