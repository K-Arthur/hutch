/* hutch live-updates — incremental live transcript updates for run detail.

   Why this file exists: the dashboard refreshes a live run by refetching /runs/:id and
   replacing the whole run-detail DOM on every coalesced burst (driven by the changes
   stream). The run SSE stream already carries the committed event batch, but the server
   sends it as a NAMED "batch" event while app.js only listened with onmessage, so the
   payload was ignored. This module (a) binds the named event, (b) applies safe batches by
   rebuilding only the transcript block from a cached authoritative snapshot, and (c)
   suppresses the redundant full refresh that the change stream would trigger right after.

   Safety: approval/choice/human/status/terminal/gap/window-boundary batches fall through
   to the existing full refresh (returns false), and any error re-schedules it. Only
   message/tool_call/tool_result/step/log events on an active run are applied in place.

   Loaded after app.js as a classic script on purpose: app.js exposes its classic-script
   globals (api, runBlockHtml, feedMode, currentRunId, ACTIVE, wireApprovals, ...), which
   this module reuses instead of duplicating rendering logic. */
(() => {
  "use strict";

  const SAFE_EVENT_TYPES = new Set(["message", "tool_call", "tool_result", "step", "log"]);
  const MAX_WINDOW_EVENTS = 220;      // keep the server-bounded transcript window
  const SKIP_FULL_REFRESH_MS = 2500;  // a change-stream refresh right after an apply is redundant

  const runs = new Map();   // runId -> { snapshot, lastSeq, lastAppliedAt, applying, queued }
  let forceRefresh = false;  // set when a safe fast path cannot render: the next full render must not be skipped
  const stats = { batchesSeen: 0, batchesApplied: 0, fallbacks: 0, skippedFullRefreshes: 0,
                  duplicateBatches: 0, errors: 0, fullRefreshCalls: 0, refreshAllowed: 0,
                  lastSkipReason: "" };

  const history = [];
  function note(kind, detail) { if (history.length < 200) history.push({ t: Math.round(performance.now()), kind, detail: detail || "" }); }

  function logError(error) {
    stats.errors += 1;
    if (window.console && console.warn) console.warn("hutch live-update fallback:", error);
  }

  function rememberSnapshot(run) {
    if (!run || typeof run.id !== "string") return;
    const events = Array.isArray(run.events) ? run.events : [];
    const lastSeq = events.reduce((max, event) => Math.max(max, Number(event.seq) || 0), 0);
    runs.set(run.id, { snapshot: run, lastSeq, lastAppliedAt: 0, applying: false, queued: null });
  }

  function snapshotFor(runId) {
    const state = runs.get(runId);
    return state ? state.snapshot : null;
  }

  function viewIsThisRun(runId) {
    // Top-level let bindings from app.js are global lexical bindings shared by classic scripts.
    if (feedMode !== "run" || currentRunId !== runId) return false;
    const hash = location.hash || "";
    return hash === `#/run/${runId}` || hash.startsWith(`#/run/${runId}?`);
  }

  function threadNode(runId) {
    const nodes = [...document.querySelectorAll("#chat-stream [data-run-id]")];
    return nodes.find(node => node.dataset.runId === runId && node.classList.contains("thread")) || null;
  }

  function parseBatch(event) {
    if (!event || typeof event.data !== "string") return null;
    try {
      const payload = JSON.parse(event.data);
      if (!payload || !Array.isArray(payload.events)) return null;
      return payload;
    } catch { return null; }
  }

  function eventIsSafe(event) {
    return !!event && SAFE_EVENT_TYPES.has(event.type) && Number.isInteger(Number(event.seq));
  }

  function mergeEvents(existing, incoming) {
    const bySeq = new Map();
    for (const event of existing || []) {
      if (event && Number.isInteger(Number(event.seq))) bySeq.set(Number(event.seq), event);
    }
    for (const event of incoming || []) {
      if (event && Number.isInteger(Number(event.seq))) bySeq.set(Number(event.seq), event);
    }
    return [...bySeq.values()].sort((a, b) => Number(a.seq) - Number(b.seq));
  }

  function detailsOpenState() {
    const node = document.querySelector("#chat-stream .thread[data-run-id]");
    if (!node) return [];
    return [...node.querySelectorAll("details")].map(detail => detail.open);
  }

  function restoreDetailsOpenState(node, openStates) {
    if (!node || !openStates.length) return;
    const details = [...node.querySelectorAll("details")];
    details.forEach((detail, index) => { if (index < openStates.length) detail.open = openStates[index]; });
  }

  function applyThreadHtml(runId, html) {
    const state = runs.get(runId);
    if (!state || !viewIsThisRun(runId)) return false;
    if (window.HutchComputer && window.HutchComputer.hasControl && window.HutchComputer.hasControl(runId)) return false;
    const stream = document.querySelector("#chat-stream");
    const node = threadNode(runId);
    if (!stream || !node) return false;
    const scroll = document.querySelector("#chat-scroll");
    const nearBottom = !scroll || (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < 120;
    const scrollTop = scroll ? scroll.scrollTop : 0;
    const openStates = detailsOpenState();
    node.outerHTML = html;
    const replacement = threadNode(runId);
    if (!replacement) return false;
    restoreDetailsOpenState(replacement, openStates);
    if (scroll) {
      if (nearBottom) scroll.scrollTop = scroll.scrollHeight;
      else scroll.scrollTop = scrollTop;
    }
    try { wireApprovals(); } catch (error) { logError(error); }
    return true;
  }

  async function applyBatch(runId, payload, fallback) {
    const state = runs.get(runId);
    if (!state) { stats.fallbacks += 1; fallbackToFullRender(fallback); return; }
    const merged = mergeEvents(state.snapshot.events || [], payload.events);
    const nextSnapshot = Object.assign({}, state.snapshot, { events: merged });
    let html;
    try {
      // One rendering function, one source of truth: the same block builder the full render uses.
      html = await runBlockHtml(runId, null, [], [], nextSnapshot);
    } catch (error) {
      logError(error);
      stats.fallbacks += 1;
      fallbackToFullRender(fallback);
      return;
    }
    if (!viewIsThisRun(runId)) return;   // navigated away while rendering: drop the stale result
    if (!applyThreadHtml(runId, html)) {
      stats.fallbacks += 1;
      fallbackToFullRender(fallback);
      return;
    }
    state.snapshot = nextSnapshot;
    state.lastSeq = merged.length ? Number(merged[merged.length - 1].seq) : state.lastSeq;
    state.lastAppliedAt = Date.now();
    stats.batchesApplied += 1;
    note("apply", "lastSeq=" + state.lastSeq);
  }

  function handleBatch(runId, event, fallback) {
    const payload = parseBatch(event);
    if (!payload) return false;
    stats.batchesSeen += 1;
    if (!viewIsThisRun(runId)) return true;   // ignore batches for a run we are not showing
    const state = runs.get(runId);
    if (!state) return false;                 // first batch before any authoritative snapshot
    if (window.HutchComputer && window.HutchComputer.hasControl && window.HutchComputer.hasControl(runId)) return false;
    if (state.applying) { state.queued = payload; return true; }
    const batchEvents = payload.events;
    if (payload.status && ACTIVE.has(payload.status) === false) return false;   // terminal: full render
    if (payload.status && payload.status !== state.snapshot.status) return false; // status transition
    if (batchEvents.some(event => !eventIsSafe(event))) return false;
    const lastSeq = batchEvents.reduce((max, event) => Math.max(max, Number(event.seq)), 0);
    if (lastSeq <= state.lastSeq) { stats.duplicateBatches += 1; return true; }
    const firstSeq = batchEvents.reduce((min, event) => Math.min(min, Number(event.seq)), Infinity);
    if (state.lastSeq && firstSeq > state.lastSeq + 1) return false;   // resume gap: let the server replay
    const existing = state.snapshot.events || [];
    const added = batchEvents.filter(event => Number(event.seq) > state.lastSeq).length;
    if (existing.length + added > MAX_WINDOW_EVENTS) return false;      // window boundary: re-window
    if (document.querySelector("#run-technical-details")?.open
        && batchEvents.some(event => event.type === "step")) return false; // visible stats must stay exact
    state.applying = true;
    applyBatch(runId, payload, fallback).catch(error => { logError(error); stats.fallbacks += 1; fallbackToFullRender(fallback); })
      .finally(() => {
        const current = runs.get(runId);
        if (!current) return;
        current.applying = false;
        const queued = current.queued;
        current.queued = null;
        if (queued) {
          // A newer batch arrived mid-apply; process it now instead of forcing a full refresh.
          if (!handleBatch(runId, { data: JSON.stringify(queued) }, fallback)) fallbackToFullRender(fallback);
        }
      });
    return true;
  }

  function skipReason(runId, params) {
    let rendered = "";
    if (params != null) {
      try { rendered = typeof params.toString === "function" ? params.toString() : String(params); }
      catch (error) { logError(error); return false; }
    }
    if (rendered !== "") return "params";
    if (!viewIsThisRun(runId)) return "view";
    if (window.HutchComputer && window.HutchComputer.hasControl && window.HutchComputer.hasControl(runId)) return "computer";
    const state = runs.get(runId);
    if (!state) return "no-state";
    if (!state.lastAppliedAt) return "never-applied";
    if ((Date.now() - state.lastAppliedAt) > SKIP_FULL_REFRESH_MS) return "stale-window";
    return "";
  }

  function shouldSkipFullRefresh(runId, params) {
    if (forceRefresh) { forceRefresh = false; return false; }
    const reason = skipReason(runId, params);
    stats.lastSkipReason = reason || "skip";
    return reason === "";
  }

  function fallbackToFullRender(fallback) {
    forceRefresh = true;
    try { fallback(); } catch (error) { logError(error); }
  }

  function bindRunStream(runStream, runId, fallback) {
    try {
      if (!runStream) return false;
      if (runStream.__hutchLiveBound) return true;
      runStream.__hutchLiveBound = true;
      runStream.onmessage = () => fallback();   // unchanged path for unnamed/polling messages
      runStream.addEventListener("batch", event => {
        try {
          if (handleBatch(runId, event, fallback)) return;
        } catch (error) { logError(error); }
        fallbackToFullRender(fallback);
      });
      return true;
    } catch (error) {
      logError(error);
      return false;
    }
  }

  function install() {
    try {
      // Capture every authoritative /runs/:id response (page render, polling, fallback) as the
      // merge base; no extra request is made for it.
      const originalApi = window.api;
      if (typeof originalApi === "function") {
        window.api = function patchedApi(path, opts) {
          const result = originalApi.apply(this, arguments);
          try {
            const method = opts && opts.method ? String(opts.method).toUpperCase() : "GET";
            const match = typeof path === "string" ? /^\/runs\/([\w-]+)$/.exec(path) : null;
            if (match && method === "GET" && result && typeof result.then === "function") {
              result.then(run => { if (run && run.id === match[1]) rememberSnapshot(run); }).catch(() => {});
            }
          } catch { /* capture is best-effort; a miss only costs one fallback */ }
          return result;
        };
      }
      // app.js and index.html are another session's parked tree, so this module cannot add its
      // one-line hook there. Wrap the existing global subscription function instead: the wrapped
      // call attaches the named batch listener to the run EventSource app.js just created, and an
      // already-open stream (first route is a run page) is attached at install time too.
      try {
        const originalSubscribe = window.subscribeRun;
        if (typeof originalSubscribe === "function" && !originalSubscribe.__hutchLiveWrapped) {
          const wrapped = function hutchLiveSubscribeRun(runId) {
            originalSubscribe.apply(this, arguments);
            try {
              if (runStream) bindRunStream(runStream, runId, scheduleFeedRender);
            } catch (error) { logError(error); }
          };
          wrapped.__hutchLiveWrapped = true;
          window.subscribeRun = wrapped;
          if (runStream && subRunId) bindRunStream(runStream, subRunId, scheduleFeedRender);
        }
      } catch (error) { logError(error); }
      // A change-stream refresh immediately after an applied batch would replace the whole page
      // for no new information. Skip only that narrow window; everything else stays authoritative.
      const originalRender = window.renderRunDetail;
      if (typeof originalRender === "function") {
        window.renderRunDetail = async function liveRenderRunDetail(runId, params) {
          stats.fullRefreshCalls += 1;
          note("refresh-call");
          try {
            if (shouldSkipFullRefresh(runId, params)) { stats.skippedFullRefreshes += 1; note("skip", stats.lastSkipReason); return; }
          } catch (error) { logError(error); }
          stats.refreshAllowed += 1;
          note("refresh-allowed", stats.lastSkipReason);
          return originalRender.apply(this, arguments);
        };
      }
    } catch (error) {
      logError(error);
    }
  }

  window.HutchLive = {
    bindRunStream,
    stats: () => Object.assign({}, stats),
    history: () => history.slice(),
    cacheSize: () => runs.size,
    reset: () => { runs.clear(); Object.keys(stats).forEach(key => { stats[key] = 0; }); },
  };
  install();
})();