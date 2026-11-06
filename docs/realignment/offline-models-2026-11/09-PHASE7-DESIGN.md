# Phase 7 design: Frontend

Surfaces: pages_models.py, templates/models.html, static/models-detect.js,
model-install.js, model-repair.js, model-switcher.js, starter-route.js,
templates/onboarding_local_service.html, server/onboarding_local_service_api.py,
Tailwind sources in app/src/. New UI goes in new modules; app.js is frozen.

## Tasks (each: at most three source files plus one seam)

### T7.1 Local runtimes panel (seam: modelview.residency_note + runtime_health)
Files: src/hutch/server/templates/models.html (runtimes section),
       src/hutch/server/static/local-runtimes.js (new),
       src/hutch/modelview.py (residency_note already exposes measured facts).
- Render one card per detected runtime from v.runtimes.
- Each card: identity (name + kind), version, state chip, applied window
  (measured), CPU/GPU split (measured from vram_bytes), loaded models,
  single next action (h.fix), with a "measured"/"predicted"/"unknown" label.
- Empty state: "No runtimes detected." with a link to Apps & AI.
- Key-protected state: "needs key" chip + next action.
- Offline-in-browser state: handled by the page (server-rendered; no fetch needed).

### T7.2 Grouped model list by where inference happens (seam: ConfiguredModelRoute.is_local + locality)
Files: src/hutch/server/templates/models.html (configured-models section),
       src/hutch/modelview.py (add locality_group helper),
       src/hutch/server/static/model-groups.js (new, optional client grouping).
- Group configured routes into three sections: "On this machine",
  "On your network", "Cloud via local runtime".
- Privacy label per group (from Phase 1 locality): local = "data stays on this
  machine"; network = "data leaves this machine to a service you control";
  cloud-via-local = "data is forwarded to a cloud service".
- Capability chips (tools, vision, reasoning) from runtime signals where
  available; otherwise "unknown".

### T7.3 Install/import flow states (seam: model-install.js already)
Files: src/hutch/server/static/model-install.js (no growth beyond fixes),
       src/hutch/server/templates/models.html (suggested section),
       src/hutch/server/pages_models.py (plan endpoint already).
- Preflight facts before the button (already), progress with aria-live (add
  aria-live to the state span), cancel/retry (already), reload survival
  (restore() already). Add aria-live="polite" to [data-install-state].

### T7.4 First run recommendation (seam: starter-route.js)
Files: src/hutch/server/static/starter-route.js,
       src/hutch/server/templates/onboarding_local_service.html,
       src/hutch/server/onboarding_local_service_api.py.
- Hardware-aware recommendation: fitted, tool-capable, license-visible, with
  size and time, no auto-download. Already mostly present; verify the data-
  sharing notice always shows for non-local routes.

### T7.5 Empty/error/loading/offline/key-protected states for every panel
Files: src/hutch/server/templates/models.html (all sections),
       src/hutch/server/static/local-runtimes.js (new),
       src/hutch/modelview.py (notes already carry some).
- Each panel renders an explicit empty/error/loading state with aria-live.
- Keyboard-only traversal and visible focus (existing CSS).

## Files I will touch (no more than 3 source + 1 seam per task)
- src/hutch/modelview.py (locality_group helper, capability chips data)
- src/hutch/server/templates/models.html (runtimes + configured + suggested sections)
- src/hutch/server/static/local-runtimes.js (new)
- src/hutch/server/static/model-groups.js (new) -- only if grouping needs JS
- docs/realignment/... progress update

## Frozen files not touched
modelchoices.py, providers/ollama.py, providers/openai_compat.py, runtime/builtin.py,
app.js. New modules stay under 400 lines.
