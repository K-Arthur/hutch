# Workflow soak recheck

This recheck ran the existing deterministic saved-workflow soak against the current interpreter source after map-key preflight was added. It completed the full 600-second interval with 60/60 successful runs and verified output `value`, 781 engine ticks, a maximum of one active run, zero model requests, zero network requests, and no reported failure.

The script's `test` label says process-executor, but the recorded executor is `thread`; classify this evidence as a thread-executor soak. The workflow interpreter is Hutch production code; `tests.support.runtime.test_runtime_for` is used only for mock-route readiness. This does not validate live model quality, process-executor behavior, or multi-worker concurrency.

Resource measurements from Python `resource.getrusage`: parent maximum RSS 951,396 KiB and child maximum RSS 122,228 KiB. The JSON records the complete run list and SHA-256 for every source file.

Command:

```sh
HUTCH_STATE_DIR=/<local-path-redacted> \
TMPDIR=/<local-path-redacted> .venv/bin/python \
docs/realignment/artifacts/workflow-studio/workflow-soak-2026-10-11/workflow_process_soak.py \
  --duration-seconds 600 --interval-seconds 10 --run-timeout-seconds 30 \
  --output /<local-path-redacted>
```

SHA-256 of `validation.json`: `aeabf6392730d6cd4fdd8bd6ddeb4f2293c483665b6860cf61b5ef7ffbe9b476`.
