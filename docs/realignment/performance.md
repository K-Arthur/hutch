# Performance measurements

The comparison uses the same repeated harness against the coherent pre-realignment revision and the current revision on one machine.
The harness runs local mock workloads; it does not include hosted-provider latency, model loading, real inference, browser startup,
queue wait, or external tool time.

## Method

`benchmarks/run.py` retains every sample and reports the median (p50), nearest-rank p90, sample count, minimum and maximum. A full
capture uses 11 CLI samples per command, five 20,000-event throughput samples, twelve mock-run overhead samples, and three daemon
and three dashboard idle samples (8 seconds of CPU observation after 2.5 seconds warm-up). The comparison artifacts preserve raw
samples and machine, revision, working-tree and harness-hash metadata under `docs/realignment/artifacts/performance/`.

The p90 is a coarse tail indicator at these sample sizes. With three or five samples, nearest-rank p90 is the maximum; it must not be
read as an SLA or a statistically stable production percentile. Raw repetitions are the inspection surface. The regression gate still
compares medians and ignores changes below its established absolute noise floor.

Idle CPU uses `/proc/<pid>/stat` clock ticks and an eight-second observation. One 10 ms tick across that window is about 4.5 CPU
seconds per hour. A stored `0.0 s/h` therefore means below this measurement's resolution, not literal zero CPU. RSS is sampled once
per repetition after warm-up. The device was an AMD Ryzen 3 5300U with 8 reported logical cores, Linux, Python 3.13.15; these figures
are machine-specific.

## Results

The controlled comparison uses the same Ryzen 3 5300U host, Python 3.13.15, and harness SHA-256
`66dab3a98f9fbd7619977274442f287e82131a155bd678618775c58efd7babd6`. The baseline source was a clean Git archive of `b3e4b15`
with that harness copied in; the current source was clean commit `bf09d97`. The archive has no `.git` metadata, so its `git_head`
is `unknown` and its `working_tree_dirty` flag reflects the injected harness, not a source edit. Raw repetitions and complete
metadata are preserved in [`baseline-b3e4b15.json`](artifacts/performance/baseline-b3e4b15.json) and
[`current-bf09d97.json`](artifacts/performance/current-bf09d97.json).

| Metric | Baseline p50 / p90 (n) | Current p50 / p90 (n) | Reading |
|---|---:|---:|---|
| CLI version startup | 235.6 / 241.5 ms (11) | 247.1 / 260.4 ms (11) | p50 +4.9%; modestly slower |
| CLI status | 259.6 / 271.8 ms (11) | 272.9 / 291.1 ms (11) | p50 +5.1%; modestly slower |
| Event throughput | 61,051 / 65,531 events/s (5) | 76,431 / 81,022 events/s (5) | p50 +25.2% |
| Mock step overhead | 0.202 / 0.240 ms (12) | 0.041 / 0.046 ms (12) | p50 lower by 79.5% |
| Idle daemon RSS | 40.6 / 40.7 MB (3) | 41.3 / 41.8 MB (3) | p50 +0.7 MB |
| Idle serve RSS | 59.9 / 61.2 MB (3) | 61.0 / 61.0 MB (3) | p50 +1.1 MB |

The benchmark records idle CPU, but the 8-second observation quantizes results in approximately 4.5 CPU-seconds/hour steps.
Values varied by one such step and cannot support a useful before/after conclusion. The old aggregate files
[`pre-realign.json`](../../benchmarks/baselines/pre-realign.json) and [`local.json`](../../benchmarks/baselines/local.json) have no
raw repetitions; they remain historical context, not a controlled comparison. The reproducible
[`quality_audit.ipynb`](../../benchmarks/quality_audit.ipynb) validates sample integrity and calculates the reported table.

## Limits

### Navigation checkpoint repeat, 2026-10-08

An initial navigation capture ran during substantial shared-host contention (observed load
13.27). Its CLI version median was 795.7 ms and event throughput 18,500 events/s. Raw
[`contended samples`](artifacts/performance/current-956b925-navigation-contended.json) and
[`context`](artifacts/performance/current-956b925-navigation-contended.context.json) are retained;
they cannot establish a code regression against the historical idle capture.

After all Hutch tests/captures finished, the baseline archive and current tree were measured
sequentially with the same interpreter and harness. Load at the two starts was 1.47 and 0.88.
The current tree was `f4f8732` with the navigation subsequently committed as `4bd0e0d`.
Shared-host activity was observed, not controlled. No safety setting was weakened.

| Metric | Repeat baseline p50 / p90 (n) | Repeat current p50 / p90 (n) |
|---|---:|---:|
| CLI version | 243.4 / 280.5 ms (11) | 248.1 / 269.1 ms (11) |
| CLI status | 251.5 / 272.2 ms (11) | 261.1 / 271.8 ms (11) |
| Events | 59,669 / 62,206 events/s (5) | 77,820 / 80,255 events/s (5) |
| Mock step overhead | 0.191 / 0.202 ms (12) | 0.043 / 0.049 ms (12) |
| Idle daemon RSS | 40.5 / 40.5 MB (3) | 41.4 / 41.8 MB (3) |
| Idle dashboard RSS | 59.5 / 61.1 MB (3) | 61.3 / 61.4 MB (3) |

The harness median regression gate reports no regression above its 20% and absolute-noise
thresholds. Samples are finite/nonnegative, their medians match the saved summaries and
the harness hashes match. Raw [`baseline`](artifacts/performance/baseline-b3e4b15-navigation-repeat.json)
and [`current`](artifacts/performance/current-f4f8732-navigation-repeat.json) files have accompanying
context files with start/end load and timing. CPU remained below or at one observation tick;
it still does not support an optimization claim. The earlier large slowdown is not reproduced
in this pair; this supports a contention explanation, without proving its exclusive cause.

### Interpretation boundary

This is a local mock/control-plane benchmark, not a cost, provider, throughput-under-load, or user-experience measurement. CPU and
memory represent the observed supervisor process while idle. Do not infer multi-user capacity or broad hardware performance from
this single host. The 11, 5, and 3 sample distributions are diagnostic evidence, not stable production percentiles. Do not use them
to claim an SLA or to explain provider latency, inference, model loading, browser startup, or queueing.

To reproduce the current capture from the repository root, run `.venv/bin/python -m benchmarks.run`. To reproduce the baseline,
extract `b3e4b15` with `git archive`, copy `benchmarks/run.py` and its package files from the current revision into the archive, then
run the same command there with `HUTCH_BENCH_SOURCE_REVISION=b3e4b15`. The full command and harness hash are also recorded in each
artifact's metadata and the notebook.

### Transcript-delivery checkpoint, 2026-10-08

The clean `f5696ce` archive and schema-v12 tree use the same harness/interpreter and full
repetitions. The final capture ran after all tests and visual capture finished. Source hashes,
start/end load and raw samples are retained. The existing default machine baseline printed
by the harness is historical; this table and comparison use the measured `f5696ce` archive.

| Metric | Previous p50 / p90 (n) | Final p50 / p90 (n) |
|---|---:|---:|
| CLI version (ms) | 241.2 / 313.3 (11) | 231.8 / 260.2 (11) |
| CLI status (ms) | 265.7 / 307.7 (11) | 257.8 / 265.1 (11) |
| Events/s | 72,973 / 76,778 (5) | 51,817 / 66,714 (5) |
| Mock overhead (ms) | 0.045 / 0.050 (12) | 0.041 / 0.045 (12) |
| Idle daemon RSS (MB) | 41.7 / 42.2 (3) | 42.0 / 42.3 (3) |
| Idle dashboard RSS (MB) | 61.8 / 63.3 (3) | 62.1 / 62.1 (3) |
| Idle daemon CPU (s/h) | 0.0 / 0.0 (3) | 0.0 / 0.0 (3) |
| Idle dashboard CPU (s/h) | 4.5 / 4.5 (3) | 4.5 / 4.5 (3) |

Event throughput is **29.0% lower** than the previous commit and exceeds the 20% median gate.
The initial uncoalesced implementation measured 45,107 events/s; pending-job coalescing and
bounded group commit improve the final median to 51,817. Running/paused/running isolated
diagnostics retain FULL sync and indicate enqueue/commit cost dominates file-delivery work
in this burst. Paused delivery is a diagnostic fixture, never a production setting. The
remaining regression is recorded; no durability or containment protection was restored to
its unsafe baseline. The benchmark waits for canonical commit, not final file delivery.
Diagnostics separately record roughly 1.2–1.4 seconds for the remaining 100,000-event file
tail after the burst; these are diagnostic samples, not a user latency or SLA.

CLI and idle RSS stay close to the previous commit (+0.3 MB RSS medians). CPU retains the
same coarse observation boundary; one tick is 4.5 s/h, so no CPU optimization claim follows.
These are local mock/control-plane measurements and exclude inference, browser startup,
provider latency, queueing and multi-user capacity.

Raw [previous](artifacts/performance/previous-f5696ce-mirror.json) and
[final](artifacts/performance/current-f5696ce-mirror-final.json) samples have context files.
The [initial tree](artifacts/performance/current-f5696ce-mirror-uncoalesced.json),
[uncoalesced](artifacts/performance/mirror-diagnosis-uncoalesced.json),
[coalesced](artifacts/performance/mirror-diagnosis-coalesced.json) and
[grouped](artifacts/performance/mirror-diagnosis-grouped.json) diagnostics remain inspectable.
The [diagnostic script](artifacts/performance/mirror-diagnosis.py) reproduces the three
modes against the current tree; historic precommit variants require their recorded source
boundaries and must not be assumed identical to the final code.

### Immutable action-intent checkpoint, 2026-10-08

The clean `4bdd936` archive and schema-v13 tree were measured sequentially after all checks.
The harness hash remains `66dab3a98f9fbd7619977274442f287e82131a155bd678618775c58efd7babd6`.
Raw samples and source/load context are retained. The archive's built-in Git metadata is unknown;
the wrapper records its actual archived revision and hashes. Do not interpret that fallback
metadata as a measured dirty checkout or replace it silently.

| Metric | `4bdd936` p50 / p90 (n) | Schema v13 p50 / p90 (n) |
|---|---:|---:|
| CLI version (ms) | 239.6 / 248.0 (11) | 236.4 / 260.2 (11) |
| CLI status (ms) | 265.1 / 298.2 (11) | 255.1 / 276.4 (11) |
| Events/s | 51,832 / 66,916 (5) | 51,262 / 63,810 (5) |
| Mock step overhead (ms) | 0.043 / 0.048 (12) | 0.066 / 0.080 (12) |
| Idle daemon RSS (MB) | 42.0 / 42.3 (3) | 42.1 / 42.4 (3) |
| Idle dashboard RSS (MB) | 62.2 / 63.5 (3) | 63.6 / 63.6 (3) |
| Idle daemon CPU (s/h) | 0.0 / 0.0 (3) | 0.0 / 4.5 (3) |
| Idle dashboard CPU (s/h) | 9.0 / 9.0 (3) | 4.5 / 4.5 (3) |

This slice adds roughly 0.023 ms to the measured mock step median and 1.4 MB to idle dashboard
RSS. Neither crosses the unchanged absolute noise floor. Event median is 1.1% lower. The
same gate reports no additional regression against `4bdd936`; the earlier **29.0% event-throughput
regression against `f5696ce` remains unresolved**, not erased by this newer comparison. CPU uses
coarse eight-second windows and cannot establish an improvement. These mock/control-plane
results exclude real model loading/inference, browser startup, network latency and queueing.

[Previous](artifacts/performance/previous-4bdd936-action-intents.json) and
[current](artifacts/performance/current-4bdd936-action-intents.json) include all samples;
context files record source hashes, timing and load. Both measurement subprocesses completed
successfully, but the wrapper's final summary import initially failed. The retained
[postprocess log](artifacts/performance/action-intents-postprocess-initial.log) records that failure.
The wrapper now supports `--summarize-only`; summarizing the preserved captures passed without
remeasuring or altering their data. Finite/nonnegative samples, medians and matching harness/
current source hashes were validated. Reproduce with
`docs/realignment/artifacts/performance/capture_comparison.py` after other checks finish.
