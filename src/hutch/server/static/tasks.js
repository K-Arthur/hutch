/* Tasks surface for the workspace SPA: every coordinated specialist assignment in one place.
 *
 *   renderTasksPage()   the #/tasks view: tasks grouped by plan, each assignment with its
 *                       specialist, model route and where it came from, usage, progress
 *                       checkpoints, and the owner actions (open chat, redirect, stop all).
 *
 * Presentation and explicit owner actions only. The server decides what may run; a model
 * choice or brief wording shown here never grants tools, memory or permissions. Vanilla ES,
 * no build step, app.js globals (api, setTopContext, openConversation, toast) at call time.
 */
(function () {
  "use strict";

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const key = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const notify = (message, isError = false) => (typeof toast === "function" ? toast(message, isError) : null);
  const LIVE = new Set(["pending", "loading_model", "running", "waiting_approval", "waiting_human",
    "waiting_resources", "waiting_workflow", "waiting_child", "recovering", "cancelling"]);
  const STATUS_LABELS = {
    needs_input: "Needs your answer", pending: "Queued", running: "Working", succeeded: "Done",
    failed: "Interrupted", stopped: "Stopped", cancelling: "Stopping", outcome_unknown: "Needs review",
    waiting_approval: "Waiting for approval", waiting_human: "Waiting for you",
  };
  const MODEL_SOURCE = { specialist_default: "Specialist default", assignment_override: "Assignment override" };
  let generation = 0;

  const statusLabel = task => STATUS_LABELS[task.status] || String(task.status || "Status unavailable").replace(/_/g, " ");
  const money = value => (value > 0 ? `$${Number(value).toFixed(4)}` : "no cost recorded");

  function usageText(task) {
    const tokens = Number(task.tokens || 0);
    return `${tokens ? tokens.toLocaleString() : "No"} tokens measured · ${money(task.cost_usd)}`;
  }

  function modelHtml(task) {
    const used = task.model_used && task.model_used !== task.model ? ` · ran on ${esc(task.model_used)}` : "";
    return `<span class="task-model">${esc(task.model || "No model recorded")}${used}</span>
      <span class="task-source tone-${task.model_source === "assignment_override" ? "info" : "muted"}">${esc(MODEL_SOURCE[task.model_source] || task.model_source)}</span>`;
  }

  function questionHtml(task) {
    if (!task.pending_question) return "";
    return `<p class="task-question" role="status"><strong>${esc(task.target_display_name)} asks:</strong>
      ${esc(task.pending_question.question)}
      <button class="btn small" type="button" data-task-open="${esc(task.child_conversation_id)}">Answer in specialist chat</button></p>`;
  }

  function checkpointHtml(task) {
    const count = Number(task.checkpoint_count || 0);
    const latest = (task.checkpoints || []).slice(-3).map(item =>
      `<li>${esc(String(item.kind || "").replace(/_/g, " "))} · ${esc(String(item.recovery_state || "").replace(/_/g, " "))}</li>`).join("");
    return `<details class="task-checkpoints"><summary>Progress checkpoints (${count.toLocaleString()})</summary>
      <p class="hint">Committed events, not a snapshot of execution state.</p><ul>${latest || "<li>None yet</li>"}</ul></details>`;
  }

  function redirectHtml(task) {
    return `<details class="task-redirect"><summary>Redirect brief</summary>
      <form class="hutch-form" data-task-redirect="${esc(task.id)}">
        <div class="hutch-field"><label class="hutch-label" for="redirect-${esc(task.id)}">New brief (revision ${Number(task.brief_revision || 1) + 1})</label>
          <textarea class="hutch-textarea" id="redirect-${esc(task.id)}" name="task_brief" rows="4" maxlength="20000" required>${esc(task.task_brief)}</textarea>
          <span class="hutch-help">Stops this assignment's active run and starts a fresh one with the new brief. Earlier results and receipts are kept.</span></div>
        <div class="hutch-actions"><button class="btn small" type="submit">Redirect</button></div></form></details>`;
  }

  function assignmentHtml(task) {
    const live = LIVE.has(task.status) || task.status === "needs_input";
    return `<article class="panel task-assignment" data-task-id="${esc(task.id)}" aria-label="${esc(task.target_display_name)} assignment">
      <header><h3>${esc(task.target_display_name)}</h3><span class="task-status status-${esc(task.status)}">${esc(statusLabel(task))}</span></header>
      <p class="task-brief">${esc(task.task_brief)}</p>
      <p class="task-meta">${modelHtml(task)}</p>
      <p class="hint">${esc(usageText(task))} · brief revision ${Number(task.brief_revision || 1)}${task.shared_facts?.length ? ` · ${task.shared_facts.length} shared fact${task.shared_facts.length === 1 ? "" : "s"}` : ""}</p>
      ${questionHtml(task)}${task.reason && !live ? `<p class="hint">${esc(task.reason)}</p>` : ""}${checkpointHtml(task)}
      <div class="hutch-actions"><button class="btn ghost small" type="button" data-task-open="${esc(task.child_conversation_id)}">Open specialist chat</button>
        ${task.continuation_available ? `<button class="btn ghost small" type="button" data-task-continue="${esc(task.id)}">Continue from checkpoint</button>` : ""}</div>
      ${redirectHtml(task)}</article>`;
  }

  function groupTasks(tasks) {
    const groups = new Map();
    for (const task of tasks) {
      const id = task.plan_group_id || task.id;
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(task);
    }
    return [...groups.values()].map(items => items.sort((a, b) => a.assignment_index - b.assignment_index));
  }

  function groupHtml(items) {
    const live = items.some(task => LIVE.has(task.status) || task.status === "needs_input");
    const tokens = items.reduce((sum, task) => sum + Number(task.tokens || 0), 0);
    const cost = items.reduce((sum, task) => sum + Number(task.cost_usd || 0), 0);
    const lead = items[0];
    return `<section class="task-plan" aria-label="Task: ${esc(lead.task_brief.slice(0, 60))}">
      <header class="task-plan-head"><div><strong>${items.length === 1 ? "1 specialist" : `${items.length} specialists working together`}</strong>
        <span class="hint">${tokens.toLocaleString()} tokens · ${esc(money(cost))} across this task</span></div>
        ${live ? `<button class="btn danger small" type="button" data-task-stop-all="${esc(lead.id)}">Stop all</button>` : ""}</header>
      <div class="task-assignments">${items.map(assignmentHtml).join("")}</div></section>`;
  }

  async function post(path, body) {
    return api(path, { method: "POST", headers: { "Idempotency-Key": key() }, body });
  }

  async function runAction(button, work, done) {
    button.disabled = true;
    try { await work(); notify(done); await renderTasksPage(); }
    catch (error) { notify(error.message || "That did not work.", true); button.disabled = false; }
  }

  function bind(container) {
    container.addEventListener("click", ev => {
      const open = ev.target.closest("[data-task-open]");
      if (open) { void openConversation(open.dataset.taskOpen); return; }
      const stop = ev.target.closest("[data-task-stop-all]");
      if (stop) void runAction(stop, () => post(`/v1/workspace/tasks/${encodeURIComponent(stop.dataset.taskStopAll)}/stop-all`), "Stopping every active assignment in this task.");
      const cont = ev.target.closest("[data-task-continue]");
      if (cont) void runAction(cont, () => post(`/v1/workspace/tasks/${encodeURIComponent(cont.dataset.taskContinue)}/continue`), "Started a fresh attempt from the checkpoint.");
    });
    container.addEventListener("submit", ev => {
      const form = ev.target.closest("[data-task-redirect]");
      if (!form) return;
      ev.preventDefault();
      const brief = new FormData(form).get("task_brief");
      void runAction(form.querySelector("button[type=submit]"), () =>
        post(`/v1/workspace/tasks/${encodeURIComponent(form.dataset.taskRedirect)}/redirect`, { task_brief: String(brief) }),
        "Brief redirected. A fresh run has started.");
    });
  }

  let pollTimer = null;

  function stopPolling() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  }

  function scheduleNextPoll(tasks) {
    stopPolling();
    const isTasksView = (location.hash || "#/chat") === "#/tasks";
    const hasActive = tasks.some(t => LIVE.has(t.status) || t.status === "needs_input");
    if (isTasksView && hasActive && !document.hidden) {
      pollTimer = setTimeout(() => { void refreshTasks(); }, 3500);
    }
  }

  async function refreshTasks() {
    if ((location.hash || "#/chat") !== "#/tasks") { stopPolling(); return; }
    const body = document.querySelector("#tasks-body");
    if (!body || body.querySelector(":focus")) {
      scheduleNextPoll([{ status: "running" }]);
      return;
    }
    try {
      const tasks = await api("/v1/workspace/tasks?limit=100");
      if ((location.hash || "#/chat") !== "#/tasks") return;
      body.innerHTML = tasks.length
        ? groupTasks(tasks).map(groupHtml).join("")
        : `<div class="empty-state"><p>No tasks yet. Ask your main assistant to prepare one and assign it to a specialist.</p></div>`;
      scheduleNextPoll(tasks);
    } catch { scheduleNextPoll([{ status: "running" }]); }
  }

  async function renderTasksPage() {
    stopPolling();
    const mine = ++generation;
    const container = document.querySelector("#view");
    setTopContext(`<div class="ctx-id"><div class="ctx-heading"><h1>Tasks</h1><span class="ctx-subtitle">Work your main assistant has handed to specialists</span></div></div>`);
    container.innerHTML = `<div class="page-scroll"><div class="container" id="tasks-body"><div class="empty-state"><div class="spinner" role="status" aria-label="Loading"></div><p>Loading tasks…</p></div></div></div>`;
    const body = container.querySelector("#tasks-body");
    bind(body);
    try {
      const tasks = await api("/v1/workspace/tasks?limit=100");
      if (mine !== generation) return;
      body.innerHTML = tasks.length
        ? groupTasks(tasks).map(groupHtml).join("")
        : `<div class="empty-state"><p>No tasks yet. Ask your main assistant to prepare one and assign it to a specialist.</p></div>`;
      scheduleNextPoll(tasks);
    } catch (error) {
      if (mine === generation) body.innerHTML = `<div class="panel" role="alert">${esc(error.message || "Tasks could not be loaded.")}</div>`;
    }
  }

  window.hutchTasks = { renderTasksPage, refresh: refreshTasks };
})();


