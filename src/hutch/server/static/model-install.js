/* Models page: install a suggested model without leaving Hutch.
   The button is the only thing that starts a download; selecting a model never does.
   Progress comes from the runtime's own byte counters through /api/models/install,
   the runtime verifies each blob's digest, and a cancelled download keeps its verified
   parts so pressing Install again resumes instead of restarting.
   Nothing here renders server text as HTML: every value is textContent. */
(() => {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const GIB = 1073741824;

  const gib = bytes => (bytes / GIB).toFixed(1);

  function stateEl(tag) {
    return document.querySelector(`[data-install-state="${CSS.escape(tag)}"]`);
  }

  function setState(tag, text, kind) {
    const el = stateEl(tag);
    if (!el) return;
    el.textContent = text;
    el.dataset.kind = kind || "";
  }

  async function api(method, path, body) {
    const response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { "content-type": "application/json", "x-csrf-token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let payload = null;
    try { payload = await response.json(); } catch { /* a non-JSON error is reported by status */ }
    if (!response.ok) {
      const detail = payload && (payload.detail || payload.message);
      throw new Error(detail || `request failed (HTTP ${response.status})`);
    }
    return payload;
  }

  // One poll loop per row. It stops on a terminal state or when the row leaves the DOM.
  function poll(tag, jobId) {
    let cancelled = false;
    const tick = async () => {
      if (cancelled || !stateEl(tag)) return;
      try {
        const job = await api("GET", `/api/models/install/${encodeURIComponent(jobId)}`);
        if (job.state === "running" || job.state === "starting") {
          const size = job.total ? ` · ${gib(job.completed)} of ${gib(job.total)} GiB` : "";
          const pct = job.percent === null || job.percent === undefined ? "" : ` ${job.percent.toFixed(0)}%`;
          setState(tag, `Downloading${pct}${size}`, "busy");
          ensureCancel(tag, jobId);
          setTimeout(tick, 900);
          return;
        }
        if (job.state === "done") {
          cancelOf(tag)?.remove();
          setState(tag, "Installed. Reloading…", "ok");
          cancelled = true;
          window.setTimeout(() => window.location.reload(), 900);
          return;
        }
        if (job.state === "cancelled") {
          setState(tag, "Cancelled. Press Install again to resume.", "warn");
          reset(tag);
          return;
        }
        setState(tag, job.error || "The download failed.", "error");
        reset(tag);
      } catch (error) {
        setState(tag, error.message, "error");
        reset(tag);
      }
    };
    setTimeout(tick, 700);
    return () => { cancelled = true; };
  }

  const cancelOf = tag => document.querySelector(`[data-install-cancel-for="${CSS.escape(tag)}"]`);

  // A running download can be stopped; verified parts are kept, so Install again resumes.
  function ensureCancel(tag, jobId) {
    const state = stateEl(tag);
    if (!state || cancelOf(tag)) return;
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn small ghost";
    cancel.dataset.installCancelFor = tag;
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", async () => {
      cancel.disabled = true;
      try { await api("DELETE", `/api/models/install/${encodeURIComponent(jobId)}`); setState(tag, "Cancelling…", "busy"); }
      catch (error) { setState(tag, error.message, "error"); cancel.disabled = false; }
    });
    state.after(cancel);
  }

  function reset(tag) {
    cancelOf(tag)?.remove();
    const button = document.querySelector(`[data-install-model="${CSS.escape(tag)}"]`);
    if (button) {
      button.disabled = false;
      button.textContent = button.dataset.installLabel || "Install";
    }
  }

  // A link to the section (or to something inside it) opens the collapsed details it lives in.
  function openTarget() {
    const target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    for (let node = target; node; node = node.parentElement) if (node.tagName === "DETAILS") node.open = true;
    target?.scrollIntoView?.({ block: "start" });
  }
  window.addEventListener("hashchange", openTarget);
  openTarget();

  document.addEventListener("click", async event => {
    const button = event.target.closest("[data-install-model]");
    if (!button || button.disabled) return;
    const tag = button.dataset.installModel;
    const size = button.dataset.installSize;
    button.dataset.installLabel = button.dataset.installLabel || button.textContent.trim();
    if (size) setState(tag, `Starting ${size} GiB download…`, "busy");
    else setState(tag, "Starting download…", "busy");
    button.disabled = true;
    button.textContent = "Installing…";
    try {
      const job = await api("POST", "/api/models/install", { model: tag });
      poll(tag, job.id);
    } catch (error) {
      setState(tag, error.message, "error");
      reset(tag);
    }
  });
})();
