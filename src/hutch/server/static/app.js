/* hutch dashboard — local-first agent studio & dashboard.
   Vanilla JS SPA, hash-routed, live polling. Zero external assets. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const view = $("#view");

const ACTIVE = new Set(["pending", "running", "waiting_approval"]);
let pollTimer = null;
let currentStudioBot = null;
let currentRunId = null;
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
  if (s < 60) return "just now";
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

// ------------------------------------------------------------------ modal

function openModal({ title, bodyHtml, onConfirm, confirmText = "Confirm", confirmClass = "primary" }) {
  const root = $("#modal-root");
  root.innerHTML = `
    <div class="modal-backdrop">
      <div class="modal-card">
        <div class="modal-header">
          <h3>${esc(title)}</h3>
          <button class="ghost small" id="modal-close">✕</button>
        </div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-footer">
          <button class="ghost" id="modal-cancel">Cancel</button>
          <button class="${confirmClass}" id="modal-confirm">${esc(confirmText)}</button>
        </div>
      </div>
    </div>
  `;
  const close = () => { root.innerHTML = ""; };
  $("#modal-close").addEventListener("click", close);
  $("#modal-cancel").addEventListener("click", close);
  $("#modal-confirm").addEventListener("click", async () => {
    if (onConfirm) {
      const ok = await onConfirm();
      if (ok !== false) close();
    } else {
      close();
    }
  });
}

function closeModal() {
  $("#modal-root").innerHTML = "";
}

// -------------------------------------------------------------- router

const routes = [
  [/^#\/chat(?:\/([\w-]+))?$/, m => renderChatStudio(m ? m[1] : null), "chat"],
  [/^#\/overview$/, () => renderChatStudio(), "chat"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs$/, renderRuns, "runs"],
  [/^#\/approvals$/, renderApprovals, "approvals"],
  [/^#\/bot\/([\w-]+)$/, m => renderBotDetail(decodeURIComponent(m[1])), "bots"],
  [/^#\/run\/([\w-]+)$/, m => renderRunDetail(m[1]), "runs"],
];

async function route() {
  const hash = location.hash || "#/chat";
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
  location.hash = "#/chat";
}

function errorState(err) {
  return `<div class="container"><div class="empty-state">
    <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="var(--amber)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 3.5 22 20.5H2z"/><path d="M12 10v5"/><path d="M12 18.2v.01"/>
    </svg>
    <p>${esc(err.message || err)}</p><p><a href="#/chat">back to studio</a></p></div></div>`;
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

window.addEventListener("hashchange", route);

async function refreshBadge() {
  try {
    const stats = await api("/stats");
    const badge = $("#approval-badge");
    if (badge) {
      badge.textContent = stats.pending_approvals;
      badge.classList.toggle("hidden", stats.pending_approvals === 0);
    }
  } catch {}
}

// ------------------------------------------------------- CHAT STUDIO (CORE)

async function renderChatStudio(preferredBot = null) {
  const bots = await api("/bots");
  if (!bots.length) {
    view.innerHTML = `<div class="container"><div class="panel">No bots found. <button class="primary small" id="btn-create-first">Create a bot</button> or run <span class="mono">hutch init</span>.</div></div>`;
    $("#btn-create-first")?.addEventListener("click", promptNewBot);
    return;
  }

  // Determine active bot
  let bot = bots.find(b => b.name === preferredBot) ||
            bots.find(b => b.name === currentStudioBot) ||
            bots[0];
  currentStudioBot = bot.name;

  // Fetch full details of current bot
  const botDetail = await api(`/bots/${encodeURIComponent(bot.name)}`);
  const activeRun = botDetail.recent_runs.find(r => ACTIVE.has(r.status)) || botDetail.recent_runs[0] || null;
  currentRunId = activeRun ? activeRun.id : null;

  view.innerHTML = `
    <div class="studio-container">
      <!-- Left Sidebar: Bots & Status -->
      <aside class="studio-sidebar">
        <div class="sidebar-header">
          <h3>Your Bots (${bots.length})</h3>
          <button class="ghost small" id="sidebar-new-bot">+ New</button>
        </div>
        <div class="sidebar-bots">
          ${bots.map(b => {
            const isActive = b.name === bot.name;
            const isRun = b.active_run_id;
            return `
              <div class="bot-nav-item ${isActive ? "active" : ""}" data-switch-bot="${esc(b.name)}">
                <div class="bot-nav-row">
                  <span class="bot-nav-name">${esc(b.name)}</span>
                  ${b.paused ? `<span class="tag warn" style="font-size:10px">paused</span>` : ""}
                  ${isRun ? `<span class="tag ok" style="font-size:10px">running</span>` : ""}
                </div>
                <div class="bot-nav-row">
                  <span class="bot-nav-model">${esc(b.model)}</span>
                  <span class="bot-nav-badge">${b.schedule ? esc(b.schedule.cron) : "on demand"}</span>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </aside>

      <!-- Center Stage: Conversation & Live Execution -->
      <main class="studio-main">
        <header class="studio-main-header">
          <div class="bot-header-info">
            <span class="bot-header-title">${esc(bot.name)}</span>
            <div class="bot-header-chips">
              <span class="tag model">${esc(bot.model)}</span>
              ${bot.schedule ? `<span class="tag schedule">${esc(bot.schedule.cron)}</span>` : `<span class="tag">manual</span>`}
              ${bot.paused ? `<span class="tag warn">paused</span>` : `<span class="tag ok">active</span>`}
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            ${activeRun && ACTIVE.has(activeRun.status) ? `
              <button class="danger small" id="studio-stop-run">■ Stop run</button>
            ` : ""}
            <a class="btn ghost small" href="#/bot/${esc(bot.name)}">Settings ⚙</a>
          </div>
        </header>

        <div class="chat-stream" id="chat-stream">
          <!-- Feed of prompt + tool calls + approvals + thoughts -->
        </div>

        <footer class="studio-composer">
          <div class="composer-tools-row">
            <div class="composer-chips">
              <span class="composer-chip" data-quick-prompt="Sort this week's downloads and move invoices">📁 Sort downloads</span>
              <span class="composer-chip" data-quick-prompt="Research this week's AI news and write summary">📰 Research news</span>
              <span class="composer-chip" data-quick-prompt="Inspect repository for TODOs and report">🔍 Repo sweep</span>
            </div>
            <div class="composer-stats">
              <span>Tokens today: <b>${fmtTokens(bot.tokens_today)}</b> / ${fmtTokens(bot.limits.daily_token_cap)}</span>
              <span>Max steps: <b>${bot.limits.max_steps}</b></span>
            </div>
          </div>
          <div class="composer-input-box">
            <textarea class="composer-textarea" id="chat-prompt" placeholder="Ask ${esc(bot.name)} to run a task… (Enter to send, Shift+Enter for new line)"></textarea>
            <button class="primary" id="chat-send" style="height:40px;padding:0 16px;">Send</button>
          </div>
        </footer>
      </main>

      <!-- Right Inspector Panel -->
      <aside class="studio-inspector">
        <div class="inspector-section">
          <h4>Bot Specifications</h4>
          <div class="meta-row"><span>Runtime</span><span>${esc(bot.runtime)}</span></div>
          <div class="meta-row"><span>Approval mode</span><span class="tag ${bot.approval_mode === 'ask' ? 'warn' : 'ok'}">${esc(bot.approval_mode)}</span></div>
          <div class="meta-row"><span>Timezone</span><span>${esc(bot.schedule ? bot.schedule.timezone : 'UTC')}</span></div>
          <div class="meta-row"><span>Next run</span><span>${esc(bot.next_run_local || '—')}</span></div>
          <div class="meta-row"><span>Last success</span><span>${timeAgo(bot.last_success)}</span></div>
        </div>

        <div class="inspector-section">
          <h4>Active Memory (${botDetail.memory.length})</h4>
          <div class="interactive-chip-list" id="memory-list">
            ${botDetail.memory.map(m => `
              <div class="interactive-chip">
                <div><b style="color:var(--violet)">${esc(m.key)}</b><br><span style="color:var(--text-dim);font-size:11px;">${esc(m.value)}</span></div>
                <span class="chip-del" title="Delete memory" data-del-mem="${esc(m.key)}">✕</span>
              </div>
            `).join("") || `<span style="font-size:12px;color:var(--text-faint)">No memories recorded</span>`}
          </div>
        </div>

        <div class="inspector-section">
          <h4>Sticky Permissions (${botDetail.sticky_allows.length})</h4>
          <div class="interactive-chip-list" id="sticky-list">
            ${botDetail.sticky_allows.map(s => `
              <div class="interactive-chip">
                <span class="chip-label" style="color:var(--accent)">✓ ${esc(s)}</span>
                <span class="chip-del" title="Revoke permission" data-revoke-sticky="${esc(s)}">✕</span>
              </div>
            `).join("") || `<span style="font-size:12px;color:var(--text-faint)">None — all risky commands ask</span>`}
          </div>
        </div>
      </aside>
    </div>
  `;

  // Wire sidebar bot switching
  $$("[data-switch-bot]").forEach(item => {
    item.addEventListener("click", () => {
      renderChatStudio(item.dataset.switchBot);
    });
  });

  // Wire memory deletion
  $$("[data-del-mem]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const k = btn.dataset.delMem;
      if (!confirm(`Delete memory "${k}"?`)) return;
      await api(`/bots/${encodeURIComponent(bot.name)}/memory/${encodeURIComponent(k)}`, { method: "DELETE" });
      toast(`Forgot "${k}"`);
      renderChatStudio(bot.name);
    });
  });

  // Wire sticky allow revocation
  $$("[data-revoke-sticky]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const k = btn.dataset.revokeSticky;
      await api(`/bots/${encodeURIComponent(bot.name)}/sticky-allows/${encodeURIComponent(k)}`, { method: "DELETE" });
      toast(`Revoked permission: ${k}`);
      renderChatStudio(bot.name);
    });
  });

  // Wire prompt submit & quick prompts
  const txt = $("#chat-prompt");
  const send = $("#chat-send");
  const triggerRun = async (promptVal) => {
    if (!promptVal.trim()) return;
    send.disabled = true;
    send.textContent = "Running…";
    try {
      const r = await api(`/bots/${encodeURIComponent(bot.name)}/run`, { method: "POST", body: { prompt: promptVal.trim() } });
      toast(`Run started`);
      currentRunId = r.id;
      txt.value = "";
      await renderChatFeed(currentRunId);
    } catch (err) {
      toast(err.message, true);
    } finally {
      send.disabled = false;
      send.textContent = "Send";
    }
  };

  send.addEventListener("click", () => triggerRun(txt.value));
  txt.addEventListener("keydown", ev => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      triggerRun(txt.value);
    }
  });

  $$("[data-quick-prompt]").forEach(chip => {
    chip.addEventListener("click", () => {
      txt.value = chip.dataset.quickPrompt;
      txt.focus();
    });
  });

  // Wire Stop Run
  const stopBtn = $("#studio-stop-run");
  if (stopBtn && currentRunId) {
    stopBtn.addEventListener("click", async () => {
      await api(`/runs/${currentRunId}/stop`, { method: "POST" });
      toast("Stop requested");
      stopBtn.remove();
    });
  }

  // Load chat feed
  if (currentRunId) {
    await renderChatFeed(currentRunId);
  } else {
    $("#chat-stream").innerHTML = `
      <div class="empty-state">
        <p>No active runs for <b>${esc(bot.name)}</b>.</p>
        <p class="hint">Type a prompt below or pick a suggestion to start working.</p>
      </div>
    `;
  }

  // Wire new bot trigger in sidebar
  $("#sidebar-new-bot")?.addEventListener("click", promptNewBot);
}

// Render conversation stream for a run
async function renderChatFeed(runId) {
  const stream = $("#chat-stream");
  if (!stream) return;

  const run = await api(`/runs/${runId}`);
  const events = await api(`/runs/${runId}/events?after=0`);

  let html = `
    <div class="chat-msg user">
      <span class="msg-role">Prompt</span>
      <div class="msg-text">${esc(run.prompt)}</div>
    </div>
  `;

  if (events.events.length) {
    events.events.forEach(ev => {
      html += renderChatEvent(ev);
    });
  }

  if (run.error) {
    html += `
      <div class="tool-card error">
        <div class="tool-card-head"><span style="color:var(--red);font-weight:700">Error</span></div>
        <div class="tool-card-body">${esc(run.error)}</div>
      </div>
    `;
  }

  stream.innerHTML = html;
  stream.scrollTop = stream.scrollHeight;

  // Wire inline approvals
  wireApprovals();

  // If run is active, poll for updates
  if (ACTIVE.has(run.status)) {
    pollTimer = setInterval(async () => {
      const updated = await api(`/runs/${runId}/events?after=0`);
      if (updated.events.length !== events.events.length) {
        renderChatFeed(runId);
      }
    }, 2000);
  }
}

function renderChatEvent(e) {
  const t = e.ts ? e.ts.slice(11, 19) : "";
  const d = e.data || {};

  switch (e.type) {
    case "message":
      return `
        <div class="chat-msg agent">
          <span class="msg-role">${esc(d.role || "Agent")} · <span style="color:var(--text-faint)">${t}</span></span>
          <div class="msg-text">${esc(d.content || "")}</div>
        </div>
      `;
    case "tool_call":
      return `
        <div class="tool-card">
          <div class="tool-card-head">
            <div><span class="tool-name">⚡ ${esc(d.tool)}</span> <span class="tool-args">${esc(JSON.stringify(d.args ?? {}))}</span></div>
            <span style="font-size:11px;color:var(--text-faint)">${t}</span>
          </div>
        </div>
      `;
    case "tool_result": {
      const ok = d.ok !== false;
      return `
        <div class="tool-card ${ok ? 'success' : 'error'}">
          <div class="tool-card-head">
            <div><span>${ok ? '✓' : '✗'} <b>${esc(d.tool)} result</b></span></div>
            <span style="font-size:11px;color:var(--text-faint)">${t}</span>
          </div>
          <div class="tool-card-body">${esc(d.output || "")}</div>
        </div>
      `;
    }
    case "approval_request":
      return `
        <div class="approval-card-chat" data-approval-card="${esc(d.approval_id)}">
          <div class="approval-badge-bar">
            <span class="tag warn">APPROVAL REQUIRED</span>
            <span class="ttl-countdown">⏳ 10m fail-closed timer</span>
          </div>
          <div class="approval-action-text">${esc(d.action || "Perform action")}</div>
          <pre class="mono" style="font-size:11px;background:#0d1219;padding:8px;border-radius:6px;overflow-x:auto;">${esc(JSON.stringify(d.detail ?? {}, null, 2))}</pre>
          <div class="approval-buttons" data-approval="${esc(d.approval_id)}">
            <button class="primary small" data-approve="1">Approve</button>
            <button class="danger small" data-approve="0">Deny</button>
            <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input type="checkbox" class="always"> always allow this action
            </label>
          </div>
        </div>
      `;
    default:
      return "";
  }
}

// ------------------------------------------------------------- BOTS VIEW

async function renderBots() {
  const [bots, templates] = await Promise.all([api("/bots"), api("/bots/templates")]);
  view.innerHTML = `
    <div class="container">
      <div class="section-head">
        <div>
          <h1 class="page-title">Bots</h1>
          <p class="page-subtitle">Configured agents on your machine. Each has isolated workspace, limits, and memory.</p>
        </div>
        <button class="primary" id="btn-create-bot">+ New Bot</button>
      </div>

      <div class="bot-grid">
        ${bots.map(b => `
          <div class="bot-card">
            <div class="bot-head">
              <span class="bot-name">${esc(b.name)}</span>
              ${b.paused ? `<span class="tag warn">paused</span>` : `<span class="tag ok">active</span>`}
            </div>
            <div class="bot-desc">${esc(b.description || "No description provided.")}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              <span class="tag model">${esc(b.model)}</span>
              ${b.schedule ? `<span class="tag schedule">${esc(b.schedule.cron)}</span>` : `<span class="tag">on demand</span>`}
              <span class="tag">${esc(b.approval_mode)}</span>
            </div>
            <div class="bot-facts">
              <div>next run: <b>${esc(b.next_run_local || '—')}</b></div>
              <div>last run: <b>${timeAgo(b.last_success)}</b></div>
              <div>tokens: <b>${fmtTokens(b.tokens_today)}</b></div>
              <div>memories: <b>${b.memory_count}</b></div>
            </div>
            <div class="card-actions">
              <button class="primary small" data-action="run" data-bot="${esc(b.name)}">Run</button>
              <button class="ghost small" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                ${b.paused ? "Resume" : "Pause"}
              </button>
              <a class="btn ghost small" href="#/chat/${esc(b.name)}">Open in Studio →</a>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;

  $("#btn-create-bot")?.addEventListener("click", promptNewBot);
  wireCommon();
}

// ------------------------------------------------------------- RUNS ARCHIVE

async function renderRuns() {
  const runs = await api("/runs?limit=50");
  view.innerHTML = `
    <div class="container">
      <h1 class="page-title">Runs Archive</h1>
      <p class="page-subtitle">Complete transcript log of every task executed on this machine.</p>

      <div style="margin-bottom:14px;display:flex;gap:10px;align-items:center;">
        <input type="text" id="run-search" placeholder="Filter runs by bot or keyword…" style="max-width:320px;">
        <div style="display:flex;gap:6px;">
          <button class="ghost small active" data-filter="all">All</button>
          <button class="ghost small" data-filter="succeeded">Succeeded</button>
          <button class="ghost small" data-filter="failed">Failed</button>
          <button class="ghost small" data-filter="waiting_approval">Waiting</button>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Bot</th>
              <th>Status</th>
              <th>Prompt</th>
              <th>Steps</th>
              <th>Tokens</th>
              <th>Executed</th>
            </tr>
          </thead>
          <tbody id="runs-table-body">
            ${runs.map(r => `
              <tr class="clickable" data-goto="#/run/${esc(r.id)}">
                <td class="mono">${esc(r.id.slice(0, 16))}…</td>
                <td><b>${esc(r.bot_name)}</b></td>
                <td>${statusChip(r.status)}</td>
                <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(r.prompt)}</td>
                <td class="mono">${r.steps}</td>
                <td class="mono">${fmtTokens(r.tokens)}</td>
                <td class="mono">${timeAgo(r.created_at)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  $$("tr[data-goto]").forEach(tr => tr.addEventListener("click", () => location.hash = tr.dataset.goto));
}

// ------------------------------------------------------------- APPROVALS

async function renderApprovals() {
  const approvals = await api("/approvals");
  view.innerHTML = `
    <div class="container">
      <h1 class="page-title">Approvals Queue</h1>
      <p class="page-subtitle">A bot wants to perform an irreversible machine action. Unanswered requests expire as <b>denied</b>.</p>

      <div style="display:flex;flex-direction:column;gap:12px;">
        ${approvals.map(a => `
          <div class="panel" data-approval-card="${esc(a.id)}">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
              <div>
                <b>${esc(a.bot_name)}</b> &middot; <span class="tag">${esc(a.tool)}</span>
              </div>
              <span class="ttl-countdown">⏳ 10m TTL &middot; ${timeAgo(a.created_at)}</span>
            </div>
            <p style="font-size:14.5px;font-weight:600;margin:4px 0 10px;">${esc(a.action)}</p>
            <pre class="mono" style="font-size:12px;background:#0d1219;padding:10px;border-radius:6px;overflow-x:auto;">${esc(JSON.stringify(a.detail, null, 2))}</pre>
            <div class="approval-buttons" data-approval="${esc(a.id)}">
              <button class="primary small" data-approve="1">Approve</button>
              <button class="danger small" data-approve="0">Deny</button>
              <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:4px;cursor:pointer;">
                <input type="checkbox" class="always"> always allow for this bot
              </label>
              <a class="btn ghost small" href="#/run/${esc(a.run_id)}">Open run &rarr;</a>
            </div>
          </div>
        `).join("") || `<div class="panel" style="color:var(--text-dim)">No pending approvals. All runs clear.</div>`}
      </div>
    </div>
  `;
  wireApprovals();
}

// ------------------------------------------------------------- DETAILS

async function renderBotDetail(name) {
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  view.innerHTML = `
    <div class="container">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <div>
          <h1 class="page-title">${esc(b.name)}</h1>
          <p class="page-subtitle" style="margin:0">${esc(b.description || "No description")}</p>
        </div>
        <div style="display:flex;gap:8px;">
          <a class="btn primary" href="#/chat/${esc(b.name)}">Open Studio 💬</a>
          <button class="danger" id="btn-delete-bot">Delete Bot</button>
        </div>
      </div>

      <div class="panel" style="margin-bottom:18px;">
        <h3 style="margin-top:0">Instructions</h3>
        <textarea id="bot-instructions" style="min-height:120px;font-family:var(--mono);">${esc(b.instructions || "")}</textarea>
        <button class="primary small" id="btn-save-instructions" style="margin-top:8px;">Save instructions</button>
      </div>
    </div>
  `;

  $("#btn-save-instructions")?.addEventListener("click", async () => {
    const next = $("#bot-instructions").value;
    await api(`/bots/${encodeURIComponent(b.name)}`, { method: "PATCH", body: { instructions: next } });
    toast("Instructions saved");
  });

  $("#btn-delete-bot")?.addEventListener("click", async () => {
    if (!confirm(`Delete bot "${b.name}"?`)) return;
    await api(`/bots/${encodeURIComponent(b.name)}`, { method: "DELETE" });
    toast(`Deleted ${b.name}`);
    location.hash = "#/bots";
  });
}

async function renderRunDetail(runId) {
  const r = await api(`/runs/${runId}`);
  view.innerHTML = `
    <div class="container">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <div>
          <h1>Run <span class="mono">${esc(r.id)}</span></h1>
          <p class="page-subtitle">Bot: <a href="#/chat/${esc(r.bot_name)}">${esc(r.bot_name)}</a> &middot; Status: ${statusChip(r.status)}</p>
        </div>
        <a class="btn ghost" href="#/runs">&larr; Back to Runs</a>
      </div>
      <div class="panel" style="margin-bottom:16px;">
        <b>Prompt:</b><br><span style="color:var(--text-dim)">${esc(r.prompt)}</span>
      </div>
      <div id="chat-stream"></div>
    </div>
  `;
  renderChatFeed(runId);
}

// ------------------------------------------------------------- MODALS & HELPERS

async function promptNewBot() {
  const templates = await api("/bots/templates");
  const html = `
    <form id="modal-bot-form" style="display:flex;flex-direction:column;gap:12px;">
      <label class="field">Bot Name
        <input type="text" name="name" placeholder="my-agent" pattern="[a-z0-9][a-z0-9-]{1,40}" required>
      </label>
      <label class="field">Template
        <select name="template">
          <option value="">&mdash; blank &mdash;</option>
          ${templates.map(t => `<option value="${esc(t.name)}">${esc(t.name)} &mdash; ${esc(t.description)}</option>`).join("")}
        </select>
      </label>
      <label class="field">Model
        <input type="text" name="model" value="mock/demo" required>
        <span class="hint">mock/demo &middot; openai/gpt-4o-mini &middot; ollama/llama3.2</span>
      </label>
      <label class="field">Schedule (cron, optional)
        <input type="text" name="cron" placeholder="0 9 * * 1">
      </label>
      <label class="field">Description
        <input type="text" name="description" placeholder="What this bot does">
      </label>
    </form>
  `;

  openModal({
    title: "Create New Bot",
    bodyHtml: html,
    confirmText: "Create Bot",
    onConfirm: async () => {
      const form = $("#modal-bot-form");
      const fd = new FormData(form);
      const name = fd.get("name").trim();
      if (!name) return false;
      try {
        await api("/bots", {
          method: "POST",
          body: {
            name,
            template: fd.get("template") || null,
            model: fd.get("model").trim(),
            cron: fd.get("cron").trim() || null,
            description: fd.get("description").trim(),
          }
        });
        toast(`Bot "${name}" created!`);
        location.hash = `#/chat/${encodeURIComponent(name)}`;
        return true;
      } catch (err) {
        toast(err.message, true);
        return false;
      }
    }
  });
}

function wireApprovals() {
  $$("[data-approve]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const wrap = btn.closest("[data-approval]");
      const id = wrap.dataset.approval;
      const always = wrap.querySelector(".always")?.checked ?? false;
      const approve = btn.dataset.approve === "1";
      try {
        await api(`/approvals/${id}/${approve ? "approve" : "deny"}`, {
          method: "POST",
          body: approve ? { always } : {}
        });
        toast(approve ? "Approved & continuing" : "Denied");
        const card = wrap.closest("[data-approval-card]");
        if (card) card.remove();
      } catch (err) {
        toast(err.message, true);
      }
    });
  });
}

function wireCommon() {
  $$('[data-action="run"]').forEach(btn => {
    btn.addEventListener("click", () => {
      location.hash = `#/chat/${encodeURIComponent(btn.dataset.bot)}`;
    });
  });

  $$('[data-action="toggle-pause"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      const bot = btn.dataset.bot;
      const paused = btn.dataset.paused !== "true";
      await api(`/bots/${encodeURIComponent(bot)}`, { method: "PATCH", body: { paused } });
      toast(paused ? "Paused" : "Resumed");
      route();
    });
  });

  $("#topbar-new-bot")?.addEventListener("click", promptNewBot);
}

// ------------------------------------------------------------- BOOT

route();
setInterval(refreshBadge, 4000);
