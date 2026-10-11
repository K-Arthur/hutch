# Persona runtime evaluation checkpoint

This checkpoint records deterministic local routing cost separately from provider quality and end-to-end response latency.

- `local-routing-latency.json` is the reproducible 500-sample run from `09850b2`, with 100 warmups and eight synthetic scenario classes. It measures `resolve_persona` + `contextualize_persona` + `guidance`, using a deterministic round-robin order.
- Environment: Python 3.13.15 on Linux x86_64, AMD Ryzen 3 5300U, 8 logical CPUs, 22.78 GiB reported RAM. No model or provider call was made.
- Result: p50 **0.060859 ms**, nearest-rank p95 **0.070031 ms**, max **0.099014 ms**; the p95 is below the 20 ms local-routing target.
- The script is `scripts/measure_persona_resolution.py`. Reproduce with:

  ```sh
  .venv/bin/python scripts/measure_persona_resolution.py --samples 500 --warmup 100 --output /tmp/persona-routing.json
  ```

This result excludes retrieval, engine scheduling, network, streaming, provider inference, first-useful-content latency, completion latency, and actual model adherence. It does not substitute for the matched live-model runs or human review in the approved evaluation plan.

The isolated ChatGPT sign-in flow is currently awaiting the user to complete authentication and approve plan-use scope. No account is connected and no model response has been requested in this isolated state yet. Any follow-on live run is limited to 12 responses, uses synthetic test prompts and the supported Hutch flow, and will be recorded separately from this local benchmark.

The pre-registered response allocation is in `openai-fallback-protocol.md`. It is prepared but not run, and does not
replace the Go-model matrix, long-session recovery tests or human review requirements in the approved plan.
