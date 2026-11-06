# Phase 6 research: Strict Offline with a live model (2026-11-06)

Narrow pass for Phase 6: what the three runtimes do without a network, what the kernel
namespace and Unix-socket broker actually enforce, what a model with tools tried to do in a
published sandbox, and which failure reports match Hutch's own boundary. Phase 0 API notes
and R1-R56 remain valid. Every page below was opened on 2026-11-06; search snippets were
leads only and are not asserted.

## Sources and decisions

| # | Source | Fact taken | Class | Decision it changed |
|---|---|---|---|---|
| P6-1 | https://docs.ollama.com/faq | Cloud features are disabled with `disable_ollama_cloud: true` in `~/.ollama/server.json` or `OLLAMA_NO_CLOUD=1`; after restart the log says `Ollama cloud disabled: true`. Local runs do not send prompts to ollama.com; cloud-hosted models are processed remotely. | configuration | Strict Offline still refuses a cloud-routed model from the server's own signal (`remote_host`/`remote_model`). `OLLAMA_NO_CLOUD` is recommended in setup docs as belt-and-braces, never treated as a Hutch-verified fact about a user-run server. |
| P6-2 | https://docs.ollama.com/cloud | Cloud models are served through the local Ollama server and do not need a download; data handling is remote. | integration/protocol | "Local endpoint" is not "local inference". The exact claim must name the model route as well as the endpoint (Phase 1 behaviour, restated for the ADR). |
| P6-3 | https://lmstudio.ai/docs/app/offline | Core operations do not need the internet: chatting with downloaded models, chatting with documents, and running a local server. Searching, downloading, runtime downloads and update checks do need it. No single global offline switch is documented. | configuration | The LM Studio adapter may be used under Strict Offline. Hutch cannot claim the app makes no update or catalog request; only the worker namespace is enforced, and the boundary text says so. |
| P6-4 | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md | `--offline` forces use of the cache and prevents network access. The default bind is `127.0.0.1:9931`. `-hf` downloads a model and projector at launch. `--host` accepts a Unix-socket path. `/health` returns 503 while loading. | integration/protocol | An offline route must have a local model file and must not rely on `-hf`. Health 200 is readiness, not proof the server is air-gapped. The launch flags are invisible to Hutch, so readiness stays `unknown` unless the operator uses `--offline`. |
| P6-5 | https://man.archlinux.org/man/bwrap.1.en | `--unshare-all` is equivalent to `--unshare-user-try --unshare-ipc --unshare-pid --unshare-net --unshare-uts --unshare-cgroup-try`; `--share-net` restores the host network namespace. `--ro-bind` is a filesystem mount, so a Unix socket crosses the network boundary as a file. | integration/protocol | The worker's only model path is the broker socket mounted at `/run/hutch-offline`; a missing socket must fail closed with no TCP fallback. The live evidence must inspect the worker's network namespace, not only the host probe. |
| P6-6 | https://man7.org/linux/man-pages/man1/unshare.1.html | `unshare -n` creates a new network namespace; `-r` maps the current user to root in a new user namespace; a new namespace has only its own loopback. `--kill-child` and `--fork` bound the process tree. | integration/protocol | The airplane test runs the app, the model server and the worker inside one `unshare -rn` namespace, brings `lo` up, and proves an external connect fails there. This is the host-level network-down case, distinct from the worker's own namespace. |
| P6-7 | https://cohere.com/blog/concerning-behaviour-popular-open-weight-ai-model | A Qwen3.8 model with shell tools inventoried the machine and attempted an upload to a cloud bucket; the sandbox had no route out and the request died. Cohere's advice: deny agent egress by default; a reasoning trace is not a security boundary. | integration/protocol + model-specific | A model's stated intent and its tool calls are not evidence of containment. Hutch's worker and shell namespaces are the enforcement point, and the tool-run egress test must be live. |
| P6-8 | https://www.notebookcheck.net/Ollama-and-LM-Studio-How-to-make-sure-your-local-AI-stays-offline.1435420.0.html | "Local does not mean offline": Ollama cloud features and updates, LM Studio discovery/downloads/updates, and tool-using agents can all reach the internet. The article finds no single LM Studio switch and recommends OS-level egress removal for agents. | frontend usability + configuration | The product must separate "local route" from "worker had no network". The UI and website may claim the latter only with the namespace evidence; they must not imply the runtime itself is silent. |
| P6-9 | https://github.com/ollama/ollama/issues/11632 | The Ollama desktop app failed to answer offline even with downloaded models while the CLI worked; the cause was a client-side offline state, fixed in a later release, and model switching also needed connectivity in the reported versions. | frontend usability | Hutch talks to the HTTP API, not the desktop UI, and reports a local model that is on disk as usable. A runtime version below the fix is not a Hutch defect; setup docs name the API path. |
| P6-10 | https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1217 | Just-in-time loading can fail or serve a different loaded model when no model is loaded; reports continue in 2026. | model-specific + integration | Hutch keeps the explicit load/read-back path from Phases 2 and 3. It does not treat a successful `/v1/models` list as proof the requested model was loaded. |

## Failure mining register rows

| ID | Complaint | Source | Class | Who can fix | Hutch response | Test idea |
|---|---|---|---|---|---|---|
| F19 | A local desktop app can depend on the network even when the model is on disk; model switching and first turns were affected while the CLI worked. | https://github.com/ollama/ollama/issues/11632 | frontend usability | runtime vendor, mitigated by Hutch | Hutch uses the server API and proves a real turn with the network down; it never equates an app window with a usable server. | Real app + real Ollama under `unshare -rn`; a tool-and-image turn succeeds. |
| F20 | An agent with shell tools can attempt egress from a local model; a chain-of-thought saying "no tools" is not a boundary. | https://cohere.com/blog/concerning-behaviour-popular-open-weight-ai-model | integration/protocol + model-specific | Hutch (containment), model supplier | The worker and the shell sandbox run in their own network namespaces; the tool-run test tries an external connect from inside. | Real local model calls `shell` with a connect attempt; the command fails and the run continues. |
| F21 | A cloud model served through a loopback Ollama endpoint looks local unless the client reads the server signal. | https://docs.ollama.com/cloud and https://docs.ollama.com/faq | integration/protocol | Hutch | Phase 1 already refuses `remote_host`/`remote_model` routes under Strict Offline and labels them elsewhere. Phase 6 re-tests it in the live matrix. | Real Ollama with a renaming cloud copy; refusal before dispatch. |
| F22 | LM Studio has no documented global offline switch; update checks and catalog calls are normal app behaviour. | https://lmstudio.ai/docs/app/offline and https://www.notebookcheck.net/Ollama-and-LM-Studio-How-to-make-sure-your-local-AI-stays-offline.1435420.0.html | configuration | LM Studio, disclosed by Hutch | Do not claim the runtime is silent. Only the worker's namespace is enforced; the browser panel and docs say which side is which. | Read the boundary copy and compare it with the live evidence; no runtime-level claim. |
| F23 | llama.cpp `--offline` prevents network access, but it is a launch flag Hutch cannot read; `-hf` fetches at startup. | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md | configuration | operator, guided by Hutch | Readiness is `unknown` for a normal llama-server until the operator confirms no `-hf` and `--offline`; a model already on disk is required. | Start with `-hf` under no network and record the failure; start with a local file and `--offline` and record success. |
| F24 | When the model bridge disappears, a generic provider error can blame a healthy runtime. | This phase's code read: `offline.py` sends 502 and `providers/ollama.py` wraps a connect failure as "is it running?" | integration/protocol | Hutch | If a live test reproduces it, classify an offline-bridge failure as its own state with an actionable sentence; do not retry blindly. | Remove the broker socket during a run on the real stack and inspect the run's error. |

## Code audit before the live pass

- `sandbox.offline_worker_argv` launches the worker through `systemd-run --scope`, `prlimit`
  and `bwrap --unshare-all`, mounts only the run's broker directory at `/run/hutch-offline`,
  masks saved connections, keys and ChatGPT credentials, and clears the environment.
- `offline.LoopbackBroker` is a Unix-socket HTTP/1.1 proxy bound to one numeric loopback
  origin. It rejects a different `Host`, absolute targets, `Expect`, chunked request bodies,
  duplicate lengths, methods other than the implemented set, and bodies over 64 MiB. It
  streams upstream responses as chunked frames.
- `engine._start_process` creates the broker set for an offline bot, passes the directory,
  and closes the brokers when the worker exits. The worker's provider clients call
  `httpx_offline_options`, which refuses to fall back to TCP when the socket is absent.
- `runtime/outcomes.classify_local_failure` maps `unreachable`/`stream` to one reload and a
  sentence about the local runtime; a broker 502 arrives as `server` and gets a bare stop.
  That is the candidate defect for F24.

## Live test plan

1. Real FastAPI app on a real port, fresh `HUTCH_STATE_DIR`, real retained Ollama 0.40.13,
   `gemma4:e2b`, a real image and a prompt that requires both an image answer and a governed
   tool call. Capture the status timeline, the answer, the tool results, and the worker's
   `/proc/<pid>/net` facts.
2. Repeat the same turn with the app, Ollama and the worker inside `unshare -rn` (only
   loopback, no external route). Record an external connect failure from inside that
   namespace and the same run result.
3. Failure modes on the real stack: kill the Ollama runner mid-stream, kill and restart the
   server, unlink the broker socket during a run, a long streamed answer, cancellation, and
   a request body over the broker's 64 MiB limit.
4. If a failure is misclassified, write the failing test from the captured text, fix the
   classifier in `runtime/outcomes.py`, and re-run the real case. No fixture-driven claim:
   the captured text is the regression input, the live run is the evidence.
