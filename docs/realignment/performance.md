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

Repeated same-harness baseline and current captures are being collected. The existing aggregate files
[`pre-realign.json`](../../benchmarks/baselines/pre-realign.json) and [`local.json`](../../benchmarks/baselines/local.json) have no
raw repetitions, so they are retained as historical context only and are not a controlled before/after comparison. The notebook
[`quality_audit.ipynb`](../../benchmarks/quality_audit.ipynb) documents the measurement-quality checks and will consume the raw captures.

## Limits

This is a local mock/control-plane benchmark, not a cost, provider, throughput-under-load, or user-experience measurement. CPU and
memory represent the observed supervisor process while idle. Do not infer multi-user capacity or broad hardware performance from
this single host.
