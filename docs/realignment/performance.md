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

This is a local mock/control-plane benchmark, not a cost, provider, throughput-under-load, or user-experience measurement. CPU and
memory represent the observed supervisor process while idle. Do not infer multi-user capacity or broad hardware performance from
this single host. The 11, 5, and 3 sample distributions are diagnostic evidence, not stable production percentiles. Do not use them
to claim an SLA or to explain provider latency, inference, model loading, browser startup, or queueing.

To reproduce the current capture from the repository root, run `.venv/bin/python -m benchmarks.run`. To reproduce the baseline,
extract `b3e4b15` with `git archive`, copy `benchmarks/run.py` and its package files from the current revision into the archive, then
run the same command there with `HUTCH_BENCH_SOURCE_REVISION=b3e4b15`. The full command and harness hash are also recorded in each
artifact's metadata and the notebook.
