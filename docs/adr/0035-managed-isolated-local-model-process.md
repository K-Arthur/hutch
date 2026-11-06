# ADR-0035: A Hutch-managed isolated model process for Strict Offline

Status: accepted, 2026-11-06. The decision and its constraints are recorded here. The
managed process is **not implemented** in the 2026-11 Phase 6 work; until it ships, the
claims in section 5 of `docs/realignment/offline-models-2026-10-31.md` are the only ones
Hutch may make.

## Context

Phase 6 drove a real governed tool-and-image turn through the per-run broker inside the
Strict Offline worker, on Ollama and llama.cpp, and repeated it with the whole stack inside
`unshare -rn`. The worker had no network in every case. The model server remained an
ordinary user-run process on the host: it was reachable from the worker only through the
broker, but Hutch did not start it, stop it, or constrain its own network access. A user-run
Ollama or LM Studio can still check for updates, fetch a model, or proxy a cloud-tagged
model; a user-run server is not air-gapped merely because Hutch talks to it on loopback.

Three options were put to the owner on 2026-11-06: keep the status-quo wording, ship a
user-run offline profile plus a checker, or have Hutch manage an isolated model process.
The owner chose the managed process. This ADR records that choice and the conditions under
which the stronger claim may be made.

## Decision

1. **Hutch starts the model process for a route that claims model-server isolation.**
   The process runs in a fresh Linux network namespace with no external route. It is
   started and stopped by Hutch, and its lifetime is a visible run/service state.
2. **Eligible runtimes are the ones Hutch can launch from documented flags.** Ollama and
   llama.cpp are the first targets; vLLM and SGLang join when a documented launch path and
   a real test exist. LM Studio is proprietary and is not eligible unless it offers a
   documented headless launch path; a user-run LM Studio route keeps the weaker wording.
3. **The model is on disk before launch.** The managed process gets a model store that is
   read-only for inference, or a dedicated writable directory whose writes are not a
   download. `-hf`, automatic pulls, catalog requests and update checks are refused in
   this mode. Acquisition stays runtime-native and happens outside the isolated process.
4. **The supervisor reaches the runtime through a Unix socket inside the namespace.**
   A small bridge process or socket relay lives in the same namespace and forwards only
   the validated loopback origin. The worker's per-run broker remains the only model path;
   no TCP port is exposed to the host. The existing broker's authority and body limits are
   reused rather than re-implemented.
5. **The stronger label is conditional on evidence.** The UI and docs say "model server
   isolated by Hutch" only after the manager has verified that the process is in its own
   network namespace, that the bridge socket is its only model path, and that the model is
   on disk. A failed start is a state with an action, never a silent fallback to a
   user-run server.
6. **Cloud and credentials stay out.** Cloud-tagged or remote models are refused. A local
   server that needs a key uses the existing origin-scoped key and the Unix-socket bridge;
   the key is never placed in a URL, a page, a log or the namespace environment.
7. **A user-run server remains a supported, weaker choice.** Its routes keep the current
   wording: the worker had no network and the route was loopback, but the model server was
   not isolated by Hutch. No route may inherit the stronger label from a process Hutch did
   not start.

## Rejected options

- **Status-quo wording.** It is honest and already enforced, but it cannot support the
  trust claim the owner selected.
- **A user-run offline profile plus a checker.** It is cheaper and useful, but Hutch can
  only observe the profile; it cannot enforce it, and a checker run before a server change
  can go stale. It remains a possible diagnostic for operators, not the boundary.

## Consequences

- A new managed-process package is required (launch/stop, namespace, bridge, state) plus
  per-runtime launch adapters. Frozen files must not grow; the run loop delegates through
  a new module.
- The tests must be real: start the actual Ollama/llama.cpp process in a network namespace,
  prove an external connect fails from inside, run a worker turn through the bridge, and
  cover process exit, model-load failure, bridge loss, cancellation and a read-only model
  store. A fake process or a captured response is not evidence for this claim.
- The dashboard needs the managed/running/failed/stopped states and the conditional label;
  that relationship is work for the frontend phase, not this ADR.
- **What may be said today:** "this run's worker could not reach the network, and its model
  route went only to your loopback address." Not: "the model server was isolated" or
  "nothing left this machine."
- **What may be said after this ADR is implemented and dated in the progress ledger:**
  "Hutch started the model server in a network namespace with no external route, and the
  worker's only model path was a Unix socket to it." The dated live test, not the design,
  is what permits the sentence.
- The Phase 6 evidence (Ollama 0.40.13, llama.cpp b12144, real images and tools) establishes
  the worker boundary only. This ADR does not retroactively strengthen it.
