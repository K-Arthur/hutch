# Phase 6 design: Strict Offline with a live model (2026-11-06)

Phase 6 has three deliverables: live evidence that a governed tool run works through the
broker in an isolated worker, live evidence for the airplane case and the failure modes,
and a boundary ADR that says exactly what Hutch may claim. No feature is invented; source
changes happen only where a live failure shows the current behaviour is misleading.

## Task 1 - Live governed tool-and-image run

No product source file changes. The harness is a throwaway script in the session
scratchpad that drives the real app over HTTP and writes JSON evidence under
`~/.hutch-tmp/offline-models-2026-11/evidence/`.

- Real stack: retained Ollama 0.40.13 on `127.0.0.1:11434`, `OLLAMA_MODELS` pointing at the
  retained store, `gemma4:e2b` (vision, tools), a real 640 px JPEG, fresh
  `HUTCH_STATE_DIR`, uvicorn on an ephemeral loopback port.
- Bot: `inference_mode=offline`, `tools=["files", "shell"]`, `sandbox=strict`,
  `approval_mode=auto`, no memory or self-check noise.
- Turn: ask the model to identify the animal in the attached image, then call `write_file`
  to save the answer and `shell` to print the file. That covers a governed file tool and
  the contained shell in one run, with an image on the wire.
- Capture: status timeline, answer, tool results, workspace bytes, broker socket path,
  worker PID and `/proc/<pid>/ns/net` plus `/proc/<pid>/net/{dev,route}` compared with the
  supervisor. Those proc views are the in-worker network facts.

## Task 2 - Airplane run and failure modes

No product source file changes for the airplane run. Harness only.

- Airplane: the same turn with app, Ollama and the worker inside one `unshare -rn`
  namespace, `lo` up, no external route; record an external `connect()` failure from that
  namespace and the same run result.
- Failure modes, each on the real stack: kill the Ollama runner mid-stream; kill and
  restart the server; unlink the broker socket during a run; a long streamed answer;
  cancel a slow run; a broker request body over 64 MiB.
- `llama.cpp`: start the retained `llama-server` with a local GGUF and `--offline` inside
  `unshare -rn`, and record a chat; start it with `-hf` and no network and record the
  failure text. This proves F23 rather than asserting it.

## Task 3 - Only if a live failure is misclassified

Candidate files: `src/hutch/runtime/outcomes.py` and `tests/test_local_failure.py` (or a
new `tests/test_offline_bridge.py` if the existing file would grow past a readable size).
The captured error text is the regression input; the classifier gets a distinct
offline-bridge state instead of "is the runtime running?". A test is written from the
captured text and must fail before the fix. No frozen file grows.

## Task 4 - Boundary decision and docs

- Ask the owner once for the 6.3 choice. Then write `docs/adr/0034-strict-offline-boundary.md`
  comparing (a) status-quo wording, (b) a Hutch-managed model process in its own network
  namespace, and (c) a user-run offline profile script plus checker. The ADR records the
  chosen option, the rejected options and the exact claim.
- Update `docs/realignment/offline-models-2026-10-31.md` with a Phase 6 evidence section and
  close phase D; update `docs/runtime-setup.md` with the per-runtime offline recipe
  (Ollama `OLLAMA_NO_CLOUD`, llama.cpp `--offline` and no `-hf`, LM Studio update checks);
  update `02-PROGRESS.md` at every checkpoint.
- No website change is in this phase; Phase 8 owns public wording.

## Task 5 - Gates

Focused tests for any changed code, `npm run check:agent`, the emoji audit on changed text,
and the real-setup evidence rows. No UI changed, so the visual gate does not apply; the
multimodal gate is covered by the real image in Tasks 1 and 2.
