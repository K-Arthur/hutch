# Phase 7 research: Frontend

Access date: 2026-11-06. Classification: frontend usability.

## Sources read (primary)

- Jan model management docs (https://docs.jan.ai/desktop/manage-models), accessed 2026-11-06:
  fit pills ("Fits" / "May be slow" / "Won't fit") based on hardware, no network
  request to determine fit; quantization tiers Small/Balanced/Large with a
  Recommended tag; download progress in the top bar with a cancel control; import
  local files through engine settings; cloud models in a separate section with
  API keys. Complaint classes: downloads cleared from the queue on failure with a
  toast; retry by re-clicking Download.
- Open WebUI quick-start (https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-ollama/),
  accessed 2026-11-06: num_ctx is an advanced per-model parameter, unset by default
  so Ollama's OLLAMA_CONTEXT_LENGTH applies. Complaint class: silent 4k default
  truncation when the user never sets num_ctx.
- Hutch design system (docs/design-system.md, DESIGN.md) and the existing
  models.html / models-detect.js / model-install.js / model-switcher.js.

## Failure and complaint mining (frontend)

- F-P7-1 (frontend usability): a model card that says "local" without saying
  whether inference is on this machine, on the LAN, or cloud-routed through a
  local server is the same defect as G2 at the UI layer. Fix: group by where
  inference happens and label measured vs predicted vs unknown. Mitigate.
- F-P7-2 (frontend usability): a runtime card that shows only "Online/Offline"
  hides version, applied window, CPU/GPU split and loaded models, so a user
  cannot tell why a request is slow or why the window is 4096. Fix: one card per
  runtime with identity, version, state, applied window, CPU/GPU split, loaded
  models, single next action. Mitigate.
- F-P7-3 (frontend usability): install progress that disappears on reload
  makes a multi-gigabyte pull look lost. Fix: reattach to the live job list on
  load (already implemented in model-install.js restore()). Keep.
- F-P7-4 (frontend usability): a first-run recommendation that auto-downloads
  violates the "selecting a model never downloads anything" rule. Fix: button
  only, preflight before confirm. Already implemented.
- F-P7-5 (frontend usability): capability claims without evidence (tools/vision/
  reasoning) are status inflation. Fix: show capability chips only where the
  runtime reports them; unknown is "unknown", never "supported". Mitigate.
- F-P7-6 (frontend usability): empty/error/loading/offline/key-protected states
  that are not rendered or not announced leave screen readers and keyboard users
  stuck. Fix: aria-live regions, keyboard operable controls, focus order. Mitigate.

## Decisions

- D-P7-1: reuse the existing runtimes grid and configured-routes table; do not
  create a second model list. Group configured routes by locality (On this
  machine / On your network / Cloud via local runtime) inside the existing table
  using section rows, not a new component.
- D-P7-2: capability chips come from runtime signals (Ollama /api/show
  capabilities, llama.cpp /props + modalities, LM Studio capabilities). Where
  the runtime is unreachable, show "unknown", never a guess.
- D-P7-3: measured values (applied window, resident bytes, VRAM) are labelled
  "measured"; fit estimates are labelled "predicted"; unreadable runtimes show
  "unknown". No silent fallback to a default.
- D-P7-4: no new CSS files beyond app/src edits; reuse hutch.css classes and
  the existing chip/tag vocabulary.
- D-P7-5: new UI logic goes in new JS modules (local-runtimes.js,
  model-groups.js) rather than growing model-install.js or models-detect.js.
  app.js is frozen.
}