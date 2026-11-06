/* Models page: install a suggested model without leaving Hutch.
   The button is the only thing that starts a download. Pressing it first asks the
   server for a preflight (size, free disk, fit, measured-rate ETA); only Confirm
   posts the install. Selecting a model never downloads anything.

   Progress comes from the runtime's own byte counters through /api/models/install,
   the runtime verifies each blob's digest, and a cancelled download keeps its verified
   parts so pressing Install again resumes. A page reload reattaches to a running job.
   Nothing here renders server text as HTML: every value is textContent. */
(() => {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const GIB = 1073741824;

  const gib = bytes => (bytes / GIB).toFixed(1);
  const mb = rate => (rate / (1024 * 1024)).toFixed(1);

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
      const error = new Error(detail || `request failed (HTTP ${response.status})`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "unknown";
    if (seconds < 60) return "under a minute";
    const minutes = Math.round(seconds / 60);
    if (minutes < 90) return `about ${minutes} min`;
    return `about ${(minutes / 60).toFixed(1)} h`;
  }

  function planPanel(tag, plan, button) {
    const panel = document.createElement("div");
    panel.dataset.installPlanFor = tag;
    const facts = [];
    if (plan.size_bytes) facts.push(`${gib(plan.size_bytes)} GiB download`);
    else facts.push("download size unknown");
    if (plan.free_bytes !== null && plan.free_bytes !== undefined) {
      facts.push(`${gib(plan.free_bytes)} GiB free on ${plan.model_dir}`);
    } else if (plan.model_dir_source === "unknown") {
      facts.push("free disk on the runtime's host is unknown");
    } else {
      facts.push(`free disk on ${plan.model_dir} is unknown`);
    }
    if (plan.fit_label) facts.push(`fit: ${plan.fit_label} at ${plan.fit_effective_ctx.toLocaleString()} tokens`);
    if (plan.eta_seconds !== null && plan.eta_seconds !== undefined) {
      const when = plan.speed_measured_at ? ` (measured ${plan.speed_measured_at.slice(0, 10)})` : "";
      facts.push(`estimated time ${duration(plan.eta_seconds)} at ${mb(plan.speed_bytes_per_s)} MB/s${when}`);
    } else {
      facts.push("download time unknown");
    }

    const summary = document.createElement("p");
    summary.className = "muted small";
    summary.textContent = facts.join(" · ");
    panel.append(summary);

    if (plan.warnings?.length) {
      const list = document.createElement("ul");
      list.className = "muted small";
      for (const warning of plan.warnings) {
        const item = document.createElement("li");
        item.textContent = warning;
        list.append(item);
      }
      panel.append(list);
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "btn small primary";
    confirm.textContent = "Confirm download";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "btn small ghost";
    back.textContent = "Back";
    actions.append(confirm, back);
    panel.append(actions);

    confirm.addEventListener("click", () => {
      panel.remove();
      void begin(tag, button);
    });
    back.addEventListener("click", () => {
      panel.remove();
      setState(tag, "", "");
      reset(tag);
    });
    stateEl(tag)?.after(panel);
    button.disabled = true;
    button.textContent = "Reviewing…";
    setState(tag, "Review the download before confirming.", "busy");
  }

  function removePlan(tag) {
    document.querySelector(`[data-install-plan-for="${CSS.escape(tag)}"]`)?.remove();
  }

  async function review(tag, button) {
    removePlan(tag);
    button.dataset.installLabel = button.dataset.installLabel || button.textContent.trim();
    button.disabled = true;
    button.textContent = "Checking…";
    setState(tag, "Checking size, free disk and fit…", "busy");
    try {
      const plan = await api("GET", `/api/models/install/plan?model=${encodeURIComponent(tag)}`);
      if (plan.blocked) {
        setState(tag, plan.blocked, "error");
        reset(tag);
        return;
      }
      planPanel(tag, plan, button);
    } catch (error) {
      setState(tag, error.message, "error");
      reset(tag);
    }
  }

  async function begin(tag, button) {
    const size = button.dataset.installSize;
    if (size) setState(tag, `Starting the ${size} GiB download…`, "busy");
    else setState(tag, "Starting the download…", "busy");
    button.disabled = true;
    button.textContent = "Installing…";
    try {
      const job = await api("POST", "/api/models/install", { model: tag });
      poll(tag, job.id);
    } catch (error) {
      setState(tag, error.message, "error");
      reset(tag);
    }
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
          const rate = job.bytes_per_second ? ` · ${mb(job.bytes_per_second)} MB/s` : "";
          const eta = job.eta_seconds === null || job.eta_seconds === undefined ? "" : ` · ${duration(job.eta_seconds)} left`;
          const prefix = job.resumed ? "Resuming" : "Downloading";
          setState(tag, `${prefix}${pct}${size}${rate}${eta}`, "busy");
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
          setState(tag, "Cancelled. Press Install again to resume; verified parts are kept.", "warn");
          reset(tag);
          return;
        }
        setState(tag, job.error_message || job.error || "The download failed.", "error");
        reset(tag);
      } catch (error) {
        if (error.status === 404) {
          setState(tag, "Hutch restarted during the download. Press Install again to resume; "
            + "the runtime keeps verified parts.", "warn");
        } else {
          setState(tag, error.message, "error");
        }
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

  // A reload can happen while the server still owns a job: reattach to it instead of
  // pretending the download vanished. The job list is the same one the poll reads.
  async function restore() {
    let jobs = [];
    try {
      jobs = (await api("GET", "/api/models/install")).jobs || [];
    } catch {
      return;
    }
    const seen = new Set();
    for (const job of jobs) {
      const tag = job.model;
      if (seen.has(tag)) continue;
      const button = document.querySelector(`[data-install-model="${CSS.escape(tag)}"]`);
      if (!button) continue;
      seen.add(tag);
      if (job.state === "starting" || job.state === "running") {
        button.disabled = true;
        button.textContent = "Installing…";
        poll(tag, job.id);
      } else if (job.state === "cancelled" || job.state === "failed") {
        setState(tag, job.error_message || job.error || (job.state === "cancelled"
          ? "Cancelled. Press Install again to resume." : "The download failed."),
          job.state === "cancelled" ? "warn" : "error");
        reset(tag);
      }
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

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-install-model]");
    if (!button || button.disabled) return;
    const tag = button.dataset.installModel;
    void review(tag, button);
  });

  void restore();
})();
