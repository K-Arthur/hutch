/* hutch dashboard — vanilla JS SPA, hash-routed, polling. No build step. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const view = $("#view");

const ACTIVE = new Set(["pending", "running", "waiting_approval"]);
let pollTimer = null;
let lastEventId = 0;

// ------------------------------------------------------------------ utils

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function timeAgo(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function fmtTokens(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(n ?? 0);
}

function statusChip(status) {
  return `<span class="status ${esc(status)}">${esc(status.replace("_", " "))}</span>`;
}

// -------------------------------------------------------------- router

const routes = [
  [/^#\/overview$/, renderOverview, "overview"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs$/, renderRuns, "runs"],
  [/^#\/approvals$/, renderApprovals, "approvals"],
  [/^#\/bot\/([\w-]+)$/, m => renderBotDetail(decodeURIComponent(m[1])), "bots"],
  [/^#\/run\/([\w-]+)$/, m => renderRunDetail(m[1]), "runs"],
];

async function route() {
  const hash = location.hash || "#/overview";
  stopPolling();
  for (const [re, handler, nav] of routes) {
    const m = hash.match(re);
    if (m) {
      $$(".topbar nav a").forEach(a => a.classList.toggle("active", a.dataset.nav === nav));
      try { await handler(m); }
      catch (err) { view.innerHTML = errorState(err); }
      refreshBadge();
      return;
    }
  }
  location.hash = "#/overview";
}

function errorState(err) {
  return `<div class="empty-state"><div class="big">⚠️</div>
    <p>${esc(err.message || err)}</p><p><a href="#/overview">back to overview</a></p></div>`;
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

window.addEventListener("hashchange", route);

async function refreshBadge() {
  try {
    const stats = await api("/stats");
    const badge = $("#approval-badge");
    badge.textContent = stats.pending_approvals;
    badge.classList.toggle("hidden", stats.pending_approvals === 0);
  } catch {}
}

// ------------------------------------------------------------- overview

async function renderOverview() {
  const [bots, stats, runs] = await Promise.all([api("/bots"), api("/stats"), api("/runs?limit=8")]);
  const approvals = await api("/approvals");

  view.innerHTML = `
    <h1 class="page-title">Overview</h1>
    <p class="page-subtitle">Every bot, run, and approval on this machine — nothing leaves it.</p>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-label">Bots</div>
        <div class="stat-value">${stats.bots}</div>
        <div class="stat-note">${stats.paused} paused</div></div>
      <div class="stat-card accent"><div class="stat-label">Active runs</div>
        <div class="stat-value">${stats.active_runs}</div>
        <div class="stat-note">${stats.queued_tasks} queued</div></div>
      <div class="stat-card ${stats.pending_approvals ? "warn" : ""}"><div class="stat-label">Awaiting you</div>
        <div class="stat-value">${stats.pending_approvals}</div>
        <div class="stat-note">approvals pending</div></div>
      <div class="stat-card"><div class="stat-label">Tokens today</div>
        <div class="stat-value">${fmtTokens(stats.tokens_today)}</div>
        <div class="stat-note">across all bots</div></div>
    </div>

    ${approvals.length ? `
    <div class="section-head"><h2>Needs a human</h2></div>
    ${approvals.map(a => approvalCard(a, false)).join("")}` : ""}

    <div class="section-head"><h2>Bots</h2>
      <a class="btn" href="#/bots">manage →</a></div>
    <div class="bot-grid">${bots.map(botCard).join("") || emptyBotState()}</div>

    <div class="section-head"><h2>Recent runs</h2>
      <a class="btn" href="#/runs">all runs →</a></div>
    ${runsTable(runs)}
  `;

  wireCommon();
  pollTimer = setInterval(() => route.reload ?? refreshOverviewLive(), 4000);
}

async function refreshOverviewLive() {
  const stats = await api("/stats");
  const cards = $$(".stat-card .stat-value");
  if (cards.length === 4) {
    cards[0].textContent = stats.bots;
    cards[1].textContent = stats.active_runs;
    cards[2].textContent = stats.pending_approvals;
    cards[3].textContent = fmtTokens(stats.tokens_today);
  }
  refreshBadge();
}

function emptyBotState() {
  return `<div class="panel">No bots yet. <a href="#/bots">Create your first bot</a> — or run
    <span class="mono">hutch init</span> to get the starter templates.</div>`;
}

function botCard(b) {
  const stale = b.schedule && (!b.last_success || (Date.now() - new Date(b.last_success).getTime()) > 7 * 86400e3);
  return `
  <div class="bot-card" data-bot="${esc(b.name)}">
    <div class="bot-head">
      <span class="bot-name">${esc(b.name)}</span>
      ${b.paused ? `<span class="tag warn">paused</span>` : ""}
      ${b.active_run_id ? `<a href="#/run/${b.active_run_id}">${statusChip("running")}</a>` : ""}
    </div>
    <div class="bot-desc">${esc(b.description || "")}</div>
    <div class="bot-meta">
      <span class="tag model">${esc(b.model)}</span>
      ${b.schedule ? `<span class="tag schedule">${esc(b.schedule.cron)} · ${esc(b.schedule.timezone)}</span>` : `<span class="tag">on demand</span>`}
      <span class="tag">${b.approval_mode === "ask" ? "approvals: ask" : "approvals: auto"}</span>
    </div>
    <div class="bot-facts">
      <div>next run <b>${b.next_run_local || "—"}</b></div>
      <div class="${stale ? "fact-stale" : ""}">last success <b>${timeAgo(b.last_success)}</b>${stale ? " ⚠" : ""}</div>
      <div>runs <b>${Object.values(b.run_counts).reduce((a, c) => a + c, 0)}</b></div>
      <div>tokens today <b>${fmtTokens(b.tokens_today)}</b> / ${fmtTokens(b.limits.daily_token_cap)}</div>
    </div>
    <div class="card-actions">
      <button class="primary small" data-action="run" data-bot="${esc(b.name)}">Run now</button>
      <button class="small ghost" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
        ${b.paused ? "Resume" : "Pause"}</button>
      <a class="btn small ghost" href="#/bot/${esc(b.name)}">Details</a>
    </div>
  </div>`;
}

function runsTable(runs, clickable = true) {
  if (!runs.length) return `<div class="panel" style="color:var(--text-dim)">No runs yet.</div>`;
  return `
  <div class="table-wrap"><table>
    <thead><tr><th>Run</th><th>Bot</th><th>Status</th><th>Steps</th><th>Tokens</th><th>Started</th></tr></thead>
    <tbody>
    ${runs.map(r => `
      <tr class="${clickable ? "clickable" : ""}" ${clickable ? `data-goto="#/run/${r.id}"` : ""}>
        <td class="mono">${esc(r.id.slice(0, 16))}…</td>
        <td><a href="#/bot/${esc(r.bot_name)}">${esc(r.bot_name)}</a></td>
        <td>${statusChip(r.status)}${r.missed_windows ? ` <span class="tag warn" title="catch-up run">+${r.missed_windows} missed</span>` : ""}</td>
        <td class="mono">${r.steps}</td>
        <td class="mono">${fmtTokens(r.tokens)}</td>
        <td class="mono" title="${esc(r.created_at)}">${timeAgo(r.created_at)}</td>
      </tr>`).join("")}
    </tbody></table></div>`;
}

// ----------------------------------------------------------------- bots

async function renderBots() {
  const [bots, templates] = await Promise.all([api("/bots"), api("/bots/templates")]);
  view.innerHTML = `
    <h1 class="page-title">Bots</h1>
    <p class="page-subtitle">Each bot is a named agent: its own model, tools, schedule, memory, and workspace.</p>

    <div class="panel" style="margin-bottom:24px">
      <form id="bot-form">
        <div class="form-grid">
          <label class="field">Name
            <input type="text" name="name" placeholder="my-scout" pattern="[a-z0-9][a-z0-9-]{1,40}" required>
          </label>
          <label class="field">Start from template
            <select name="template"><option value="">— blank —</option>
              ${templates.map(t => `<option value="${esc(t.name)}">${esc(t.name)} — ${esc(t.description)}</option>`).join("")}
            </select>
          </label>
          <label class="field">Model
            <input type="text" name="model" value="mock/demo" required>
            <span class="hint">mock/demo · openai/gpt-4o-mini · ollama/llama3.2</span>
          </label>
          <label class="field">Approval mode
            <select name="approval_mode">
              <option value="ask">ask — human approves risky actions</option>
              <option value="auto">auto — allowlist only</option>
            </select>
          </label>
          <label class="field">Cron schedule <span class="hint">(optional)</span>
            <input type="text" name="cron" placeholder="0 9 * * 1">
          </label>
          <label class="field">Timezone
            <input type="text" name="timezone" value="UTC" placeholder="Europe/Berlin">
          </label>
          <label class="field full">Description
            <input type="text" name="description" placeholder="What this bot is for">
          </label>
          <div class="field full">Tools
            <div class="checks">
              ${["shell", "files", "memory", "web_fetch", "browser"].map(t =>
                `<label><input type="checkbox" name="tools" value="${t}" ${["shell", "files", "memory"].includes(t) ? "checked" : ""}> ${t}</label>`).join("")}
            </div>
            <span class="hint">browser needs <span class="mono">hutch[browser]</span>; everything runs inside the bot's workspace jail</span>
          </div>
          <label class="field full">Instructions
            <textarea name="instructions" placeholder="Standing instructions the bot follows on every run…"></textarea>
          </label>
        </div>
        <div style="margin-top:16px;display:flex;gap:10px">
          <button class="primary" type="submit">Create bot</button>
        </div>
      </form>
    </div>

    <div class="bot-grid">${bots.map(botCard).join("") || emptyBotState()}</div>
  `;

  $("#bot-form").addEventListener("submit", async ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const tools = fd.getAll("tools");
    try {
      await api("/bots", { method: "POST", body: {
        name: fd.get("name").trim(),
        template: fd.get("template") || null,
        model: fd.get("model").trim(),
        approval_mode: fd.get("approval_mode"),
        cron: fd.get("cron").trim() || null,
        timezone: fd.get("timezone").trim() || "UTC",
        description: fd.get("description").trim(),
        instructions: fd.get("instructions").trim(),
        tools: tools.length ? tools : ["files", "memory"],
      }});
      toast(`Bot ${fd.get("name")} created`);
      renderBots();
    } catch (err) { toast(err.message, true); }
  });
  wireCommon();
}

async function renderBotDetail(name) {
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  view.innerHTML = `
    <div class="detail-header">
      <div>
        <h1>${esc(b.name)} ${b.paused ? `<span class="tag warn">paused</span>` : ""}</h1>
        <p class="page-subtitle" style="margin:4px 0 0">${esc(b.description || "no description")}</p>
      </div>
      <div class="card-actions">
        <button class="primary" data-action="run" data-bot="${esc(b.name)}">Run now</button>
        <button class="ghost" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
          ${b.paused ? "Resume schedules" : "Pause schedules"}</button>
        <button class="danger" id="delete-bot">Delete</button>
      </div>
    </div>

    <div class="kv-strip">
      <span class="tag model">${esc(b.model)}</span>
      <span class="tag">runtime: ${esc(b.runtime)}</span>
      ${b.schedule ? `<span class="tag schedule">${esc(b.schedule.cron)} · ${esc(b.schedule.timezone)} · catch-up: ${esc(b.schedule.catch_up)}</span>` : `<span class="tag">on demand</span>`}
      <span class="tag">approvals: ${esc(b.approval_mode)}</span>
      <span class="tag">limits: ${b.limits.max_steps} steps · ${Math.round(b.limits.timeout_seconds / 60)}min · ${fmtTokens(b.limits.daily_token_cap)} tok/day</span>
      <span class="tag ok">next: ${b.next_run_local || "—"}</span>
    </div>

    <div class="two-col">
      <div>
        <div class="section-head"><h2>Runs</h2></div>
        ${runsTable(b.recent_runs)}

        <div class="section-head"><h2>Instructions</h2>
          <button class="small ghost" id="edit-instructions">Edit</button></div>
        <div class="panel"><pre class="mono" style="white-space:pre-wrap;margin:0;color:var(--text-dim)">${esc(b.instructions || "(none)")}</pre></div>
      </div>
      <div>
        <div class="section-head"><h2>Memory <span class="hint">(${b.memory_count})</span></h2></div>
        <div class="memory-list">
          ${b.memory.map(m => `<div class="memory-item"><span class="k">${esc(m.key)}</span><br>${esc(m.value)}</div>`).join("") || `<div class="hint">nothing remembered yet</div>`}
        </div>
        <div class="section-head"><h2>Sticky allows</h2></div>
        <div class="bot-meta">${b.sticky_allows.map(s => `<span class="tag ok">${esc(s)}</span>`).join("") || `<span class="hint">none — every risky action asks</span>`}</div>
      </div>
    </div>
  `;

  $("#delete-bot").addEventListener("click", async () => {
    if (!confirm(`Delete bot "${b.name}"? Runs and workspaces on disk are kept.`)) return;
    try { await api(`/bots/${encodeURIComponent(b.name)}`, { method: "DELETE" }); toast("deleted"); location.hash = "#/bots"; }
    catch (err) { toast(err.message, true); }
  });

  $("#edit-instructions").addEventListener("click", async () => {
    const next = prompt("New instructions:", b.instructions);
    if (next === null) return;
    await api(`/bots/${encodeURIComponent(b.name)}`, { method: "PATCH", body: { instructions: next }});
    toast("instructions updated");
    renderBotDetail(name);
  });

  wireCommon();
}

// ----------------------------------------------------------------- runs

async function renderRuns() {
  const runs = await api("/runs?limit=50");
  view.innerHTML = `
    <h1 class="page-title">Runs</h1>
    <p class="page-subtitle">Every run keeps a full append-only transcript — silence is never mistaken for success.</p>
    ${runsTable(runs)}`;
  $$("tr[data-goto]").forEach(tr => tr.addEventListener("click", () => location.hash = tr.dataset.goto));
}

async function renderRunDetail(runId) {
  const r = await api(`/runs/${runId}`);
  lastEventId = 0;
  view.innerHTML = `
    <div class="detail-header">
      <div>
        <h1>${statusChip(r.status)} <span class="mono" style="font-size:14px">${esc(r.id)}</span></h1>
        <p class="page-subtitle" style="margin:6px 0 0">
          bot <a href="#/bot/${esc(r.bot_name)}">${esc(r.bot_name)}</a>
          ${r.missed_windows ? ` · <span class="tag warn">catch-up: ${r.missed_windows} missed windows</span>` : ""}
          ${r.exit_reason && r.exit_reason !== "completed" ? ` · exit: ${esc(r.exit_reason)}` : ""}
        </p>
      </div>
      ${ACTIVE.has(r.status) ? `<button class="danger" id="stop-run">■ Stop run</button>` : ""}
    </div>

    <div class="kv-strip">
      <span class="tag">steps ${r.steps}</span>
      <span class="tag">tokens ≈${fmtTokens(r.tokens)}</span>
      <span class="tag">started ${r.started_at ? timeAgo(r.started_at) : "—"}</span>
      ${r.finished_at ? `<span class="tag">finished ${timeAgo(r.finished_at)}</span>` : `<span class="tag schedule">live</span>`}
    </div>

    <div class="panel" style="margin-bottom:16px"><b>Prompt</b><br>
      <span style="color:var(--text-dim)">${esc(r.prompt)}</span></div>
    ${r.error ? `<div class="panel" style="border-color:rgba(248,113,113,.4);margin-bottom:16px"><b style="color:var(--red)">Error</b><br><span class="mono" style="font-size:12px;color:var(--text-dim)">${esc(r.error)}</span></div>` : ""}

    <div class="section-head"><h2>Transcript</h2>
      <span class="hint">append-only · also on disk as transcript.jsonl</span></div>
    <div class="transcript" id="transcript"></div>
  `;

  const stopBtn = $("#stop-run");
  if (stopBtn) stopBtn.addEventListener("click", async () => {
    await api(`/runs/${runId}/stop`, { method: "POST" });
    toast("stop requested");
  });

  const render = (events, status) => {
    const box = $("#transcript");
    if (!box) return;
    if (events.length) box.insertAdjacentHTML("beforeend", events.map(transcriptItem).join(""));
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    if (atBottom) box.scrollTop = box.scrollHeight;
    if (!ACTIVE.has(status)) {
      stopPolling();
      const stopB = $("#stop-run");
      if (stopB) stopB.remove();
      box.insertAdjacentHTML("beforeend",
        `<div class="tl-item log"><span class="tl-type">end</span> <span class="tl-time">run ${esc(status)}</span></div>`);
    }
  };

  const tick = async () => {
    try {
      const data = await api(`/runs/${runId}/events?after=${lastEventId}`);
      if (data.events.length) {
        lastEventId = data.events[data.events.length - 1].id;
        render(data.events, data.status);
      } else {
        const box = $("#transcript");
        const chip = $(".detail-header .status");
        if (chip && !ACTIVE.has(data.status)) render([], data.status);
      }
    } catch {}
  };
  await tick();
  pollTimer = setInterval(tick, 1500);
}

function transcriptItem(e) {
  const t = e.ts.slice(11, 19);
  const d = e.data || {};
  switch (e.type) {
    case "message":
      return `<div class="tl-item message">
        <div class="tl-head"><span class="tl-type">${esc(d.role || "message")}</span><span class="tl-time">${t}</span></div>
        <div class="tl-out">${esc(d.content || "")}</div></div>`;
    case "tool_call":
      return `<div class="tl-item tool_call">
        <div class="tl-head"><span class="tl-type">tool</span><span class="tl-tool">${esc(d.tool)}</span>
        <span class="tl-args">${esc(JSON.stringify(d.args ?? {}))}</span><span class="tl-time">${t}</span></div></div>`;
    case "tool_result": {
      const mark = d.ok ? `<span class="tl-ok">✓</span>` : `<span class="tl-no">✗</span>`;
      const first = (d.output || "").split("\n").slice(0, 3).join("\n");
      return `<div class="tl-item tool_result">
        <div class="tl-head">${mark} <span class="tl-tool">${esc(d.tool)}</span><span class="tl-time">${t}</span></div>
        <div class="tl-out dim">${esc(first)}</div></div>`;
    }
    case "approval_request":
      return `<div class="tl-item approval_request">
        <div class="tl-head"><span class="tl-type">approval needed</span><span class="tl-time">${t}</span></div>
        <div class="tl-out">${esc(d.action || "")}</div>
        <div class="inline-approval" data-approval="${esc(d.approval_id)}">
          <button class="primary small" data-approve="1">Approve</button>
          <button class="danger small" data-approve="0">Deny</button>
          <label><input type="checkbox" class="always"> always allow this action</label>
        </div></div>`;
    case "approval_resolved":
      return `<div class="tl-item log">
        <div class="tl-head"><span class="tl-type">approval</span> ${esc(String(d.result))} <span class="tl-time">${t}</span></div></div>`;
    case "error":
      return `<div class="tl-item error">
        <div class="tl-head"><span class="tl-type">error</span><span class="tl-time">${t}</span></div>
        <div class="tl-out">${esc(d.error || "")}</div></div>`;
    case "status":
      return `<div class="tl-item log">
        <div class="tl-head"><span class="tl-type">status</span> ${esc(d.status || "")} <span class="tl-time">${t}</span></div></div>`;
    default:
      return `<div class="tl-item log">
        <div class="tl-head"><span class="tl-type">${esc(e.type)}</span>
        <span class="tl-args">${esc(JSON.stringify(d))}</span><span class="tl-time">${t}</span></div></div>`;
  }
}

// ------------------------------------------------------------ approvals

async function renderApprovals() {
  const approvals = await api("/approvals");
  view.innerHTML = `
    <h1 class="page-title">Approvals</h1>
    <p class="page-subtitle">A bot wants to do something irreversible. You decide. Unanswered requests
      expire as <b>denied</b> — silence never becomes consent.</p>
    ${approvals.map(a => approvalCard(a, true)).join("") ||
      `<div class="panel" style="color:var(--text-dim)">Nothing waiting on you. 🎉</div>`}
    <div class="section-head"><h2>How this works</h2></div>
    <div class="panel">
      <p style="margin:0;color:var(--text-dim);font-size:13.5px">
        Mutating commands, file writes, browser clicks and network uploads require your approval the first time.
        Tick <b>always allow</b> to make it sticky for that bot — revoke any time from the bot's detail page.
        Hard-denied classes (privilege escalation, secret paths, pipe-to-interpreter, exfiltration channels)
        never reach this queue.</p>
    </div>`;
  wireApprovals();
  pollTimer = setInterval(async () => {
    const still = await api("/approvals");
    if (still.length !== approvals.length) renderApprovals();
  }, 2500);
}

function approvalCard(a, withBot = true) {
  return `
  <div class="panel" style="margin-bottom:12px" data-approval-card="${esc(a.id)}">
    <div class="bot-head">
      ${withBot ? `<span class="bot-name"><a href="#/bot/${esc(a.bot_name)}">${esc(a.bot_name)}</a></span>` : ""}
      <span class="tag">${esc(a.tool)}</span>
      <span class="tag warn">waiting ${timeAgo(a.created_at)}</span>
    </div>
    <p style="margin:10px 0"><b>${esc(a.action)}</b></p>
    <pre class="mono" style="background:var(--bg-raised);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:12px;overflow-x:auto">${esc(JSON.stringify(a.detail, null, 2))}</pre>
    <div class="inline-approval" style="margin-top:12px" data-approval="${esc(a.id)}">
      <button class="primary" data-approve="1">Approve</button>
      <button class="danger" data-approve="0">Deny</button>
      <label><input type="checkbox" class="always"> always allow for this bot</label>
      <a class="btn ghost" href="#/run/${esc(a.run_id)}">open run →</a>
    </div>
  </div>`;
}

function wireApprovals() {
  $$('[data-approve]').forEach(btn => btn.addEventListener("click", async () => {
    const wrap = btn.closest("[data-approval]");
    const id = wrap.dataset.approval;
    const always = wrap.querySelector(".always")?.checked ?? false;
    const approve = btn.dataset.approve === "1";
    try {
      await api(`/approvals/${id}/${approve ? "approve" : "deny"}`, {
        method: "POST", body: approve ? { always } : {} });
      toast(approve ? "approved — the run continues" : "denied — the run adapts");
      const card = wrap.closest("[data-approval-card]");
      if (card) card.remove();
      if (!$('[data-approval-card]') && !$('#transcript')) renderApprovals();
    } catch (err) {
      if (String(err.message).includes("already")) {
        toast("already resolved elsewhere");
        const card = wrap.closest("[data-approval-card]");
        if (card) card.remove();
      } else {
        toast(err.message, true);
      }
    }
  }));
}

// ------------------------------------------------------------ shared wiring

function wireCommon() {
  $$('[data-action="run"]').forEach(btn => btn.addEventListener("click", async () => {
    const bot = btn.dataset.bot;
    const prompt = prompt(`What should ${bot} do?`, "do your standing task and write report.md");
    if (!prompt) return;
    btn.disabled = true; btn.textContent = "starting…";
    try {
      const r = await api(`/bots/${encodeURIComponent(bot)}/run`, { method: "POST", body: { prompt } });
      toast(`run ${r.id} started`);
      location.hash = `#/run/${r.id}`;
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = "Run now"; }
  }));

  $$('[data-action="toggle-pause"]').forEach(btn => btn.addEventListener("click", async () => {
    const bot = btn.dataset.bot;
    const paused = btn.dataset.paused !== "true";
    try {
      await api(`/bots/${encodeURIComponent(bot)}`, { method: "PATCH", body: { paused } });
      toast(paused ? "schedules paused" : "schedules resumed");
      route();
    } catch (err) { toast(err.message, true); }
  }));

  $$("tr[data-goto]").forEach(tr => tr.addEventListener("click", () => location.hash = tr.dataset.goto));

  // inline approvals inside live transcripts
  wireApprovals();
}

// ------------------------------------------------------------------ boot

route();
setInterval(refreshBadge, 5000);
