/* Scheduled work enhancement: fleet roll call, attention filter, history and policy.
 *
 * app.js owns the shipped schedules view. This module observes #view and adds a
 * small, isolated layer after each render; it never edits app.js. All new data
 * comes from the Phase 2 schedule APIs, and history is fetched lazily on open.
 */
(function () {
  "use strict";

  const state = {
    enhanced: new WeakSet(),
    roll: null,
    bySchedule: new Map(),
    attention: new Set(),
    filter: false,
    pending: null,
  };

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }
  function callApi(path, options) {
    if (typeof window.api === "function") return window.api(path, options || {});
    const opts = options || {};
    return fetch(`/api${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      method: opts.method || "GET",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(async response => {
      if (!response.ok) throw new Error(`${response.status}`);
      return response.json();
    });
  }
  function notify(message, isError) {
    if (typeof window.toast === "function") window.toast(message, !!isError);
  }
  function formatTime(value) {
    if (!value) return "No time recorded";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return String(value);
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }
  function formatRelative(value) {
    if (typeof window.timeAgo === "function") return window.timeAgo(value);
    return formatTime(value);
  }
  function statusLabel(status) {
    const labels = {
      succeeded: "Succeeded", failed: "Failed", outcome_unknown: "Needs review",
      skipped: "Skipped", running: "Running", pending: "Queued",
      waiting_approval: "Waiting for approval", waiting_human: "Waiting for you",
      waiting_resources: "Waiting for a slot", waiting_workflow: "Waiting for workflow",
      waiting_child: "Waiting for delegated work", recovering: "Cleaning up",
      cancelling: "Stopping", stopped: "Cancelled", loading_model: "Loading model",
    };
    return labels[status] || (status ? status.replaceAll("_", " ") : "No recorded result");
  }
  function formatValue(value) {
    if (value === null || value === undefined) return "not set";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }
  function formatCondition(condition) {
    const value = Array.isArray(condition.value)
      ? condition.value.map(formatValue).join(", ")
      : formatValue(condition.value);
    return `${condition.field} ${condition.op.replaceAll("_", " ")} ${value}`;
  }
  function conditionsSummary(conditions) {
    if (!conditions || !conditions.length) return "Conditions: none. Runs whenever the schedule is due.";
    return `Conditions: ${conditions.map(formatCondition).join("; ")}.`;
  }

  function botFromRow(row) {
    const link = $('.schedule-overview-bot a[href^="#/chat/"]', row);
    if (!link) return "";
    return decodeURIComponent((link.getAttribute("href") || "").slice("#/chat/".length));
  }

  function rollCallHtml(roll) {
    const totals = roll.totals || {};
    const spend = totals.spend || {};
    const next = totals.next_due;
    const spendText = spend.state === "no_cap"
      ? `$${Number(spend.measured_cost_usd || 0).toFixed(2)} measured today · no daily cap set`
      : `${spend.state === "over" ? "Over cap" : spend.state === "near" ? "Near cap" : "Within cap"}: ` +
        `$${Number(spend.measured_cost_usd || 0).toFixed(2)} measured + ` +
        `$${Number(spend.reserved_cost_usd || 0).toFixed(2)} reserved of ` +
        `$${Number(spend.configured_cost_cap_usd || 0).toFixed(2)}`;
    const nextText = next
      ? `Next due ${esc(next.name)} · ${esc(next.bot_name)} · ${esc(formatTime(next.at))}`
      : "No upcoming routine";
    return `<div class="schedule-roll-call-head"><h2 id="schedule-roll-call-title">Fleet roll call</h2>
        <span class="hint" role="status">Updated ${esc(formatRelative(roll.generated_at))}</span></div>
      <div class="schedule-roll-call-grid">
        <div class="schedule-roll-call-stat"><span>Routines</span><strong>${Number(totals.routines || 0)}</strong></div>
        <div class="schedule-roll-call-stat"><span>Active</span><strong>${Number(totals.active || 0)}</strong></div>
        <div class="schedule-roll-call-stat"><span>Blocked</span><strong>${Number(totals.blocked || 0)}</strong></div>
        <div class="schedule-roll-call-stat"><span>Needs attention</span><strong>${Number(totals.needs_attention || 0)}</strong></div>
        <div class="schedule-roll-call-stat"><span>Pending approvals</span><strong>${Number(totals.pending_approvals || 0)}</strong></div>
        <div class="schedule-roll-call-stat"><span>Failed last 24h</span><strong>${Number(totals.failed_last_24h || 0)}</strong></div>
      </div>
      <p class="schedule-roll-call-next">${nextText}</p>
      <p class="schedule-roll-call-spend${spend.state === "over" ? " schedule-roll-call-spend-over" : ""}">${esc(spendText)}</p>`;
  }

  function occurrenceHtml(item) {
    const workflow = item.workflow_run_id
      ? `<span class="schedule-history-workflow" title="Linked workflow run">workflow ${esc(item.workflow_run_id)}</span>`
      : "";
    const reason = String(item.exit_reason || "").replaceAll("_", " ");
    return `<li class="schedule-history-item">
        <div class="schedule-history-line"><b>${esc(statusLabel(item.run_status))}</b><span>${esc(formatTime(item.occurrence))}</span></div>
        ${reason ? `<p class="hint">${esc(reason)}</p>` : ""}
        <div class="schedule-history-links">${item.run_id ? `<a href="#/run/${encodeURIComponent(item.run_id)}">Open run</a>` : ""}${workflow}</div>
      </li>`;
  }

  function changeHtml(change) {
    if (change.redacted) {
      return `<li><code>${esc(change.field)}</code> changed · value hidden</li>`;
    }
    const suffix = change.truncated ? " (truncated)" : "";
    return `<li><code>${esc(change.field)}</code>: ${esc(formatValue(change.before))} -> ${esc(formatValue(change.after))}${suffix}</li>`;
  }

  function revisionHtml(revision) {
    const label = revision.change_type === "created" ? "Created" : revision.change_type === "removed" ? "Removed" : "Updated";
    const changes = (revision.changes || []).length
      ? `<ul class="schedule-history-changes">${revision.changes.map(changeHtml).join("")}</ul>`
      : "";
    return `<li class="schedule-history-item">
        <div class="schedule-history-line"><b>${esc(label)}</b><span>${esc(formatTime(revision.changed_at))}</span></div>
        ${changes}
      </li>`;
  }

  function policyHtml(policy, workflowLinked) {
    const disabled = workflowLinked ? "disabled" : "";
    const note = workflowLinked
      ? "Linked saved workflows keep their own step approvals; a schedule-level pre-check is not available."
      : "A parked run waits for you and expires closed if nobody decides.";
    return `<section class="schedule-history-section" aria-labelledby="schedule-policy-title">
        <h3 id="schedule-policy-title">Policy</h3>
        <label class="schedule-policy-toggle"><input type="checkbox" data-schedule-approval ${policy.approval_required ? "checked" : ""} ${disabled}><span>Ask before each run</span></label>
        <p class="hint">${esc(note)}</p>
        <p class="hint">${esc(conditionsSummary(policy.conditions || []))}</p>
      </section>`;
  }

  function historyHtml(data) {
    const occurrences = (data.occurrences || []).length
      ? `<ul class="schedule-history-list">${data.occurrences.map(occurrenceHtml).join("")}</ul>`
      : `<p class="hint">No claimed runs yet.</p>`;
    const revisions = (data.revisions || []).length
      ? `<ul class="schedule-history-list">${data.revisions.map(revisionHtml).join("")}</ul>`
      : `<p class="hint">No recorded schedule changes yet.</p>`;
    return `${policyHtml(data.policy || {}, data.workflow_linked)}
      <section class="schedule-history-section" aria-labelledby="schedule-runs-title"><h3 id="schedule-runs-title">Recent runs</h3>${occurrences}</section>
      <section class="schedule-history-section" aria-labelledby="schedule-changes-title"><h3 id="schedule-changes-title">Schedule changes</h3>${revisions}</section>`;
  }

  async function savePolicy(input, data, botName, scheduleId) {
    const current = data.policy || {};
    input.disabled = true;
    input.setAttribute("aria-busy", "true");
    try {
      const saved = await callApi(`/v1/bots/${encodeURIComponent(botName)}/schedules/${encodeURIComponent(scheduleId)}/policy`, {
        method: "PUT",
        body: {
          approval_required: input.checked,
          conditions: current.conditions || [],
          expected_revision: current.revision || 0,
        },
      });
      data.policy = saved;
      notify(saved.approval_required ? "Each new occurrence will wait for you." : "Occurrences run without a pre-check.");
    } catch (error) {
      input.checked = !input.checked;
      notify(`Policy not saved: ${error.message}`, true);
    } finally {
      input.disabled = false;
      input.removeAttribute("aria-busy");
    }
  }

  async function loadHistory(details, botName, scheduleId) {
    if (details.dataset.loading === "1") return;
    details.dataset.loading = "1";
    const body = $(".schedule-history-body", details);
    body.innerHTML = `<p class="hint" role="status">Loading history…</p>`;
    try {
      const data = await callApi(`/v1/bots/${encodeURIComponent(botName)}/schedules/${encodeURIComponent(scheduleId)}/history?limit=20`);
      body.innerHTML = historyHtml(data);
      details.dataset.loaded = "1";
      const input = $("[data-schedule-approval]", body);
      input?.addEventListener("change", () => void savePolicy(input, data, botName, scheduleId));
    } catch (error) {
      body.innerHTML = `<p class="hint" role="status">History unavailable: ${esc(error.message)}</p>
        <button class="btn ghost small" type="button" data-retry-history>Retry</button>`;
      $("[data-retry-history]", body)?.addEventListener("click", () => {
        delete details.dataset.loaded;
        delete details.dataset.loading;
        void loadHistory(details, botName, scheduleId);
      });
    } finally {
      delete details.dataset.loading;
    }
  }

  function updateLastRun(row) {
    const routine = state.bySchedule.get(row.dataset.scheduleId);
    const last = $(".schedule-last", row);
    if (!routine || !last || routine.last_run_status !== "waiting_approval") return;
    if (last.dataset.scheduleWaiting === "1") return;
    last.dataset.scheduleWaiting = "1";
    const runId = routine.last_occurrence?.run_id || "";
    last.classList.add("schedule-last-attention");
    last.innerHTML = `Last run is waiting for your approval.${runId ? ` <a href="#/run/${encodeURIComponent(runId)}">Open run</a> ·` : ""} <a href="#/approvals">Review approvals</a>`;
  }

  function updateAttentionNote(container, roll) {
    const note = $(".schedule-attention-note", container);
    if (!note) return;
    const totals = roll.totals || {};
    const count = Number(totals.needs_attention || 0);
    if (!count) {
      note.hidden = true;
      return;
    }
    note.hidden = false;
    const causes = [];
    if (Number(totals.failed_last_24h || 0)) causes.push(`${Number(totals.failed_last_24h)} with a failed last run`);
    if (Number(totals.pending_approvals || 0)) causes.push(`${Number(totals.pending_approvals)} waiting for approval`);
    if (Number(totals.blocked || 0)) causes.push(`${Number(totals.blocked)} blocked`);
    const message = `${count} recurring task${count === 1 ? " needs" : "s need"} attention${causes.length ? `: ${causes.join(", ")}` : ""}. Each card says why.`;
    if (note.textContent !== message) note.textContent = message;
  }

  function addHistory(row) {
    if (!row || row.querySelector(".schedule-history")) return;
    const scheduleId = row.dataset.scheduleId || "";
    if (!scheduleId) return;
    const details = document.createElement("details");
    details.className = "schedule-history";
    details.innerHTML = `<summary>History and policy</summary><div class="schedule-history-body"><p class="hint">Open to load recent runs and schedule changes.</p></div>`;
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.loaded === "1") return;
      const botName = (state.bySchedule.get(scheduleId) || {}).bot_name || botFromRow(row);
      if (botName) void loadHistory(details, botName, scheduleId);
    });
    const task = $(".schedule-overview-task", row) || row;
    task.append(details);
  }

  function applyFilter(container) {
    const rows = $$(".schedule-overview-row", container);
    const toggle = $("#schedule-attention-only", container);
    const count = $("#schedule-attention-count", container);
    if (!toggle || !count) return;
    const ready = state.roll !== null;
    toggle.disabled = !ready || rows.length === 0;
    if (!ready) toggle.checked = false;
    const only = ready && state.filter;
    let visible = 0;
    rows.forEach(row => {
      const show = !only || state.attention.has(row.dataset.scheduleId);
      row.hidden = !show;
      if (show) visible += 1;
    });
    if (!ready) count.textContent = "Attention data unavailable";
    else if (only) count.textContent = `${visible} of ${rows.length} need attention`;
    else count.textContent = `Showing all ${rows.length}`;
  }

  async function loadRollCall(container, mount) {
    try {
      const roll = await callApi("/v1/schedules/roll-call");
      state.roll = roll;
      state.bySchedule = new Map((roll.routines || []).map(item => [item.schedule_id, item]));
      state.attention = new Set((roll.routines || []).filter(item => item.needs_attention).map(item => item.schedule_id));
      mount.innerHTML = rollCallHtml(roll);
      updateAttentionNote(container, roll);
      $$(".schedule-overview-row", container).forEach(updateLastRun);
      applyFilter(container);
    } catch (error) {
      state.roll = null;
      mount.innerHTML = `<p class="hint" role="status">Roll call unavailable: ${esc(error.message)}. The routine list below is still shown.</p>`;
      applyFilter(container);
    }
  }

  function enhance() {
    if (location.hash !== "#/schedules") return;
    const container = $("#view .schedule-overview");
    if (!container) return;
    const rows = $$(".schedule-overview-row", container);
    if (state.enhanced.has(container)) {
      rows.forEach(addHistory);
      rows.forEach(updateLastRun);
      if (state.roll) updateAttentionNote(container, state.roll);
      applyFilter(container);
      return;
    }
    state.enhanced.add(container);

    const roll = document.createElement("section");
    roll.className = "schedule-roll-call";
    roll.setAttribute("aria-labelledby", "schedule-roll-call-title");
    roll.innerHTML = `<p class="hint" role="status">Loading fleet roll call…</p>`;
    const note = $(".schedule-overview-note", container);
    if (note) note.after(roll); else container.prepend(roll);

    if (rows.length) {
      const filter = document.createElement("div");
      filter.className = "schedule-attention-filter";
      filter.innerHTML = `<label class="schedule-attention-toggle"><input type="checkbox" id="schedule-attention-only"><span>Needs attention only</span></label>
        <span class="hint" id="schedule-attention-count" role="status">Loading attention data…</span>`;
      const heading = $(".schedule-overview-heading", container);
      if (heading) heading.before(filter); else container.append(filter);
      $("#schedule-attention-only", container)?.addEventListener("change", event => {
        state.filter = event.target.checked;
        applyFilter(container);
      });
    }

    rows.forEach(addHistory);
    rows.forEach(updateLastRun);
    applyFilter(container);
    void loadRollCall(container, roll);
  }

  function scheduleSoon() {
    clearTimeout(state.pending);
    state.pending = setTimeout(enhance, 120);
  }

  const view = document.getElementById("view");
  if (view) new MutationObserver(scheduleSoon).observe(view, { childList: true, subtree: true });
  window.addEventListener("hashchange", scheduleSoon);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scheduleSoon);
  else scheduleSoon();
})();
