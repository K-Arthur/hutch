/* hutch dashboard — local-first agent studio & dashboard.
   Vanilla JS SPA, hash-routed, live polling. Zero external assets. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const view = $("#view");

const ACTIVE = new Set(["pending", "running", "waiting_approval"]);
let pollTimer = null;
let currentStudioBot = null;
let currentStudioTab = "chat";
let currentRunId = null;
let lastPrompt = "";

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
  const root = $("#toast-root");
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.innerHTML = `<span class="toast-msg">${esc(msg)}</span>
    <button class="toast-close" aria-label="Dismiss notification">${icon("x")}</button>`;
  const dismiss = () => el.remove();
  el.querySelector(".toast-close").addEventListener("click", dismiss);
  root.appendChild(el);
  // Transient notices auto-dismiss; errors persist until dismissed (Primer
  // guidance: toasts that vanish are how errors get missed).
  if (!isError) setTimeout(dismiss, 4200);
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

// Inline SVG icon set — the only permitted iconography (see scripts/audit_emoji.py).
// 24x24 viewBox, stroked with currentColor so context sets the color.
const ICON_PATHS = {
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  zap: '<path d="M13 2 3 14h7l-1 8 11-12h-7l1-8z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.2 3.9A2 2 0 0 0 7.5 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  fileText: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  hourglass: '<path d="M5 22h14M5 2h14M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2"/>',
  bot: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
  caret: '<path d="m9 18 6-6-6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  alert: '<path d="M12 3.5 22 20.5H2z"/><path d="M12 10v5"/><path d="M12 18.2v.01"/>',
};

function icon(name, cls = "") {
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}

function truncate(s, n) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

// One-line flattening of tool output for the woven feed entry.
function summarizeOutput(output) {
  if (!output) return "";
  const flat = String(output).replace(/\s+/g, " ").trim();
  return flat ? flat : "";
}

// Bot persona: hexagon avatar (the hutch logo shape) tinted per bot, plus a
// derived status so the rail reads at a glance.
const AVATAR_HUES = [
  { fg: "#34d399", bg: "rgba(52, 211, 153, 0.1)" },
  { fg: "#60a5fa", bg: "rgba(96, 165, 250, 0.1)" },
  { fg: "#a78bfa", bg: "rgba(167, 139, 250, 0.1)" },
  { fg: "#fbbf24", bg: "rgba(251, 191, 36, 0.1)" },
];

function botHue(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_HUES[h % AVATAR_HUES.length];
}

function hexAvatar(name, size = 40) {
  const hue = botHue(name);
  return `<span class="hex-avatar" style="width:${size}px;height:${size}px;color:${hue.fg};background:${hue.bg};font-size:${Math.round(size * 0.34)}px" aria-hidden="true">${esc(String(name)[0].toUpperCase())}</span>`;
}

function botState(b) {
  if (b.active_run_id) return "running";
  if (b.paused) return "paused";
  return "idle";
}

// Per-bot daily token budget meter. Amber near the cap, red over it — the
// spend should never be a surprise (documented failure of usage-based tools).
function budgetMeterHtml(bot) {
  const cap = bot.limits.daily_token_cap || 0;
  const used = bot.tokens_today || 0;
  const pct = cap ? Math.round((used / cap) * 100) : 0;
  const state = pct >= 100 ? "over" : pct >= 70 ? "warn" : "";
  return `
    <span class="budget-meter ${state}" title="Daily token budget: ${used} of ${cap}">
      <span class="meter-track"><span class="meter-fill" style="width:${Math.min(pct, 100)}%"></span></span>
      <span>${fmtTokens(used)} / ${fmtTokens(cap)} tokens (${pct}%)</span>
    </span>
  `;
}

// ------------------------------------------------------------------ modal

let modalReturnFocus = null;

function openModal({ title, bodyHtml, onConfirm, onCancel, confirmText = "Confirm", confirmClass = "primary" }) {
  const root = $("#modal-root");
  modalReturnFocus = document.activeElement;
  root.innerHTML = `
    <div class="modal-backdrop" data-modal-backdrop>
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-header">
          <h3 id="modal-title">${esc(title)}</h3>
          <button class="ghost small icon-btn" id="modal-close" aria-label="Close dialog">${icon("x")}</button>
        </div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-footer">
          <button class="ghost" id="modal-cancel">Cancel</button>
          <button class="${confirmClass}" id="modal-confirm">${esc(confirmText)}</button>
        </div>
      </div>
    </div>
  `;
  const card = $(".modal-card", root);
  const close = (cancelled = true) => {
    document.removeEventListener("keydown", keyHandler, true);
    root.innerHTML = "";
    if (cancelled && onCancel) onCancel();
    modalReturnFocus?.focus?.();
  };
  const keyHandler = ev => {
    if (ev.key === "Escape") {
      ev.stopPropagation();
      close();
      return;
    }
    if (ev.key === "Tab") {
      // Focus trap: cycle within the dialog.
      const focusables = $$("button, input, select, textarea, a[href]", card)
        .filter(el => !el.disabled && el.offsetParent !== null);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener("keydown", keyHandler, true);
  $("[data-modal-backdrop]", root).addEventListener("mousedown", ev => {
    if (ev.target === ev.currentTarget) close();
  });
  $("#modal-close").addEventListener("click", () => close());
  $("#modal-cancel").addEventListener("click", () => close());
  $("#modal-confirm").addEventListener("click", async () => {
    if (onConfirm) {
      const ok = await onConfirm();
      if (ok !== false) close(false);
    } else {
      close(false);
    }
  });
  // Initial focus: first form field if present, else the confirm action.
  const firstField = $("input, select, textarea", card);
  (firstField || $("#modal-confirm")).focus();
}

function closeModal() {
  $("#modal-root").innerHTML = "";
}

// Promise-based replacement for window.confirm(): keeps the native dialog
// out of the visual language and gives destructive actions a styled path.
function confirmDialog({ title, body, confirmText = "Confirm", danger = false }) {
  return new Promise(resolve => {
    openModal({
      title,
      bodyHtml: `<p class="confirm-body">${body}</p>`,
      confirmText,
      confirmClass: danger ? "danger" : "primary",
      onCancel: () => resolve(false),
      onConfirm: async () => { resolve(true); return true; },
    });
  });
}

// -------------------------------------------------------------- router

const routes = [
  [/^#\/chat(?:\/([\w-]+))?$/, m => renderChatStudio(m ? m[1] : null), "chat"],
  [/^#\/overview$/, () => renderChatStudio(), "chat"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs(?:\?(.*))?$/, m => renderRuns(m ? m[1] : ""), "runs"],
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
      $$(".topbar nav a").forEach(a => {
        const isActive = a.dataset.nav === nav;
        a.classList.toggle("active", isActive);
        if (isActive) a.setAttribute("aria-current", "page");
        else a.removeAttribute("aria-current");
      });
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
    ${icon("alert", "icon-lg")}
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
    <div class="studio-mobile-nav">
      <button class="sm-tab ${currentStudioTab === 'chat' ? 'active' : ''}" data-studio-tab="chat">${icon("chat")} Chat</button>
      <button class="sm-tab ${currentStudioTab === 'fleet' ? 'active' : ''}" data-studio-tab="fleet">${icon("bot")} Fleet (${bots.length})</button>
      <button class="sm-tab ${currentStudioTab === 'inspector' ? 'active' : ''}" data-studio-tab="inspector">${icon("sliders")} Specs &amp; Memory</button>
    </div>

    <div class="studio-container" data-tab="${currentStudioTab}">
      <!-- Left Sidebar: Bots & Status -->
      <aside class="bot-rail" aria-label="Your bots">
        ${bots.map(b => {
          const isActive = b.name === bot.name;
          const state = botState(b);
          return `
            <button class="rail-bot ${isActive ? "active" : ""}" type="button" ${isActive ? 'aria-current="true"' : ""} data-switch-bot="${esc(b.name)}" title="${esc(b.name)} — ${state}">
              ${hexAvatar(b.name, 40)}
              <span class="rail-dot ${state}" aria-hidden="true"></span>
            </button>
          `;
        }).join("")}
        <button class="rail-add" type="button" id="sidebar-new-bot" title="New bot" aria-label="New bot">${icon("plus")}</button>
      </aside>

      <!-- Center Stage: Conversation & Live Execution -->
      <main class="studio-main">
        <header class="studio-main-header">
          <div class="bot-header-info">
            ${hexAvatar(bot.name, 34)}
            <div class="bot-header-id">
              <span class="bot-header-title">${esc(bot.name)}</span>
              <span class="bot-header-meta">${esc(bot.model)} &middot; approval: ${esc(bot.approval_mode)}</span>
            </div>
          </div>
          <div class="studio-header-actions">
            ${activeRun && ACTIVE.has(activeRun.status) ? `
              <button class="danger small" id="studio-stop-run">${icon("stop")} Stop run</button>
            ` : ""}
            <a class="btn ghost small" href="#/bot/${esc(bot.name)}">${icon("sliders")} Settings</a>
          </div>
        </header>

        <div class="chat-stream" id="chat-stream">
          <!-- Feed of prompt + tool calls + approvals + thoughts -->
        </div>

        <footer class="studio-composer">
          <div class="composer-pill">
            <div class="composer-meta-row">
              <div class="composer-chips">
                <span class="composer-chip" data-quick-prompt="Sort this week's downloads and move invoices">${icon("folder")} Sort downloads</span>
                <span class="composer-chip" data-quick-prompt="Research this week's AI news and write summary">${icon("fileText")} Research news</span>
                <span class="composer-chip" data-quick-prompt="Inspect repository for TODOs and report">${icon("search")} Repo sweep</span>
              </div>
              <div class="composer-stats">
                ${budgetMeterHtml(bot)}
                <span>Steps <b>${bot.limits.max_steps}</b></span>
              </div>
            </div>
            <div class="composer-input-row">
              ${hexAvatar(bot.name, 28)}
              <label class="visually-hidden" for="chat-prompt">Task prompt for ${esc(bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message ${esc(bot.name)}… (Enter to send, Shift+Enter for a new line, Up to recall)"></textarea>
              <button class="composer-send" id="chat-send" aria-label="Send prompt">${icon("send")}</button>
            </div>
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
                <button class="chip-del" title="Delete memory" aria-label="Delete memory ${esc(m.key)}" data-del-mem="${esc(m.key)}">${icon("x")}</button>
              </div>
            `).join("") || `<span style="font-size:12px;color:var(--text-faint)">No memories recorded</span>`}
          </div>
        </div>

        <div class="inspector-section">
          <h4>Sticky Permissions (${botDetail.sticky_allows.length})</h4>
          <div class="interactive-chip-list" id="sticky-list">
            ${botDetail.sticky_allows.map(s => `
              <div class="interactive-chip">
                <span class="chip-label">${icon("check")} ${esc(s)}</span>
                <button class="chip-del" title="Revoke permission" aria-label="Revoke permission ${esc(s)}" data-revoke-sticky="${esc(s)}">${icon("x")}</button>
              </div>
            `).join("") || `<span style="font-size:12px;color:var(--text-faint)">None — all risky commands ask</span>`}
          </div>
        </div>
      </aside>
    </div>
  `;

  // Wire mobile tab switcher
  $$("[data-studio-tab]").forEach(btn => {
    btn.addEventListener("click", () => {
      currentStudioTab = btn.dataset.studioTab;
      const c = $(".studio-container");
      if (c) c.dataset.tab = currentStudioTab;
      $$("[data-studio-tab]").forEach(b => b.classList.toggle("active", b === btn));
    });
  });

  // Wire mobile bot select dropdown
  $("#bot-mobile-select")?.addEventListener("change", (e) => {
    currentStudioBot = e.target.value;
    currentStudioTab = "chat";
    renderChatStudio(currentStudioBot);
  });

  // Wire sidebar bot switching (mouse + keyboard)
  $$("[data-switch-bot]").forEach(item => {
    const activate = () => {
      currentStudioTab = "chat";
      renderChatStudio(item.dataset.switchBot);
    };
    item.addEventListener("click", activate);
    item.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); activate(); }
    });
  });

  // Wire memory deletion
  $$("[data-del-mem]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const k = btn.dataset.delMem;
      if (!(await confirmDialog({
        title: "Forget memory",
        body: `Delete the memory <b>${esc(k)}</b>? The bot will no longer recall it.`,
        confirmText: "Forget",
        danger: true,
      }))) return;
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
    lastPrompt = promptVal.trim();
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
      send.innerHTML = `${icon("send")} Send`;
    }
  };

  send.addEventListener("click", () => triggerRun(txt.value));
  txt.addEventListener("keydown", ev => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      triggerRun(txt.value);
    } else if (ev.key === "ArrowUp" && !txt.value && lastPrompt) {
      ev.preventDefault();
      txt.value = lastPrompt;
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

// Render conversation stream for a run.
// Tool activity renders as compact Codex-style lines: call+result merge into
// one row, runs of 4+ collapse under a "Ran N tools" group, and expansion
// state survives re-renders via localStorage (per run).
async function renderChatFeed(runId) {
  const stream = $("#chat-stream");
  if (!stream) return;
  stopPolling();

  const run = await api(`/runs/${runId}`);
  const events = await api(`/runs/${runId}/events?after=0`);
  const items = groupToolItems(pairToolEvents(events.events));

  let html = `
    <div class="chat-msg user">
      <span class="msg-role">Prompt</span>
      <div class="msg-text">${esc(run.prompt)}</div>
    </div>
  `;
  items.forEach(item => { html += renderFeedItem(item, runId); });

  if (run.error) {
    html += `
      <div class="run-error">
        <span class="run-error-label">Error</span>
        <span>${esc(run.error)}</span>
      </div>
    `;
  }

  stream.innerHTML = html;
  stream.scrollTop = stream.scrollHeight;

  wireApprovals();
  wireFeedInteractions(runId);
  updateTtls();

  // Cursor-based polling: only refetch events newer than the last one seen.
  const lastSeq = events.events.length ? events.events[events.events.length - 1].seq : 0;
  if (ACTIVE.has(run.status)) {
    pollTimer = setInterval(async () => {
      try {
        const updated = await api(`/runs/${runId}/events?after=${lastSeq}`);
        if (updated.events.length) renderChatFeed(runId);
      } catch { /* transient poll errors retry on the next tick */ }
    }, 2000);
  }
}

// Merge tool_call + tool_result pairs into single display items.
function pairToolEvents(events) {
  const items = [];
  let pending = null;
  for (const e of events) {
    const d = e.data || {};
    if (e.type === "tool_call") {
      if (pending) items.push({ kind: "tool", call: pending, result: null });
      pending = { e, d };
    } else if (e.type === "tool_result") {
      items.push({ kind: "tool", call: pending, result: { e, d } });
      pending = null;
    } else {
      if (pending) { items.push({ kind: "tool", call: pending, result: null }); pending = null; }
      items.push({ kind: "event", e, d });
    }
  }
  if (pending) items.push({ kind: "tool", call: pending, result: null });
  return items;
}

// Collapse runs of 4+ consecutive tool lines under one group row.
const TOOL_GROUP_THRESHOLD = 4;

function groupToolItems(items) {
  const out = [];
  let run = [];
  const flush = () => {
    if (run.length >= TOOL_GROUP_THRESHOLD) out.push({ kind: "group", items: run });
    else out.push(...run);
    run = [];
  };
  for (const it of items) {
    if (it.kind === "tool") run.push(it);
    else { flush(); out.push(it); }
  }
  flush();
  return out;
}

function expandedStore(runId) {
  try { return new Set(JSON.parse(localStorage.getItem(`hutch-expanded:${runId}`)) || []); }
  catch { return new Set(); }
}

function renderFeedItem(item, runId) {
  if (item.kind === "tool") return toolLineHtml(item, item.call?.e ?? item.result.e, runId);
  if (item.kind === "group") return toolGroupHtml(item, runId);
  return renderChatEvent(item.e);
}

function toolLineHtml(item, anchorEvent, runId) {
  const idx = anchorEvent.seq ?? anchorEvent.ts;
  const call = item.call, res = item.result;
  const tool = (res || call).d.tool;
  const running = !res;
  const ok = res ? res.d.ok !== false : true;
  const cls = running ? "running" : ok ? "success" : "error";
  const argsStr = JSON.stringify(call?.d.args ?? {});
  const summary = res
    ? summarizeOutput(res.d.output) || argsStr
    : argsStr;
  const t = (res || call).e.ts?.slice(11, 19) || "";
  const open = expandedStore(runId).has(String(idx));
  const verdict = running
    ? '<span class="spin-line" role="status" aria-label="running"></span>'
    : icon(ok ? "check" : "x");

  return `
    <div class="tool-line ${cls}" data-tool-line="${esc(String(idx))}">
      <button class="tool-line-head" type="button" aria-expanded="${open}" aria-controls="tlb-${esc(String(idx))}" data-tool-toggle="${esc(String(idx))}">
        <span class="tool-verdict">${verdict}</span>
        <span class="tool-name">${esc(tool)}</span>
        <span class="tool-args">${icon("caret", "tool-arrow")}${esc(truncate(summary, 80))}</span>
        <span class="tool-time">${t}</span>
        <span class="tool-caret">${icon("caret")}</span>
      </button>
      <div class="tool-line-body" id="tlb-${esc(String(idx))}" ${open ? "" : "hidden"}>
        <div class="tool-line-section">
          <span class="tool-line-label">Input</span>
          ${esc(JSON.stringify(call?.d.args ?? {}, null, 2))}
        </div>
        ${res ? toolOutputHtml(res.d.output) : '<div class="tool-line-section"><span class="tool-line-label">Output</span>pending…</div>'}
      </div>
    </div>
  `;
}

const OUTPUT_CLIP = 600;

function toolOutputHtml(output) {
  const text = output || "(no output)";
  if (text.length <= OUTPUT_CLIP) {
    return `<div class="tool-line-section"><span class="tool-line-label">Output</span>${esc(text)}</div>`;
  }
  return `
    <div class="tool-line-section">
      <span class="tool-line-label">Output</span>
      <span data-out-clip>${esc(text.slice(0, OUTPUT_CLIP))}</span><span data-out-full hidden>…${esc(text.slice(OUTPUT_CLIP))}</span>
      <button class="tool-line-more" type="button" data-show-more>Show ${text.length - OUTPUT_CLIP} more characters</button>
    </div>
  `;
}

function toolGroupHtml(item, runId) {
  const open = localStorage.getItem(`hutch-group:${runId}`) === "1";
  const tools = item.items.map(it => (it.result || it.call).d.tool);
  const uniq = [...new Set(tools)];
  const label = uniq.length <= 3 ? uniq.join(", ") : `${uniq.slice(0, 3).join(", ")} +${uniq.length - 3}`;
  const done = item.items.filter(it => it.result).length;
  const summary = `${done}/${item.items.length} tool steps — ${label}`;
  const allOk = done === item.items.length && item.items.every(it => (it.result?.d.ok ?? true) !== false);
  return `
    <div class="tool-group ${open ? "open" : ""}" data-tool-group>
      <div class="feed-divider">
        <button class="feed-pill" type="button" aria-expanded="${open}" data-group-toggle>
          ${icon(allOk ? "check" : "zap")}
          <span>${esc(summary)}</span>
          <span class="tool-caret">${icon("caret")}</span>
        </button>
      </div>
      <div class="tool-group-items" ${open ? "" : "hidden"}>
        ${item.items.map(it => toolLineHtml(it, it.call?.e ?? it.result.e, runId)).join("")}
      </div>
    </div>
  `;
}

// Delegated interactions for the feed: line expansion, output clip, groups.
function wireFeedInteractions(runId) {
  const stream = $("#chat-stream");
  if (!stream) return;
  const persist = () => {
    const ids = [...stream.querySelectorAll("[data-tool-toggle][aria-expanded='true']")]
      .map(b => b.dataset.toolToggle);
    try { localStorage.setItem(`hutch-expanded:${runId}`, JSON.stringify(ids)); } catch {}
  };
  stream.addEventListener("click", ev => {
    const more = ev.target.closest("[data-show-more]");
    if (more) {
      const full = more.parentElement.querySelector("[data-out-full]");
      const clip = more.parentElement.querySelector("[data-out-clip]");
      const show = full.hidden;
      full.hidden = !show;
      clip.hidden = show;
      more.textContent = show ? "Show less" : more.textContent;
      return;
    }
    const groupBtn = ev.target.closest("[data-group-toggle]");
    if (groupBtn) {
      const group = groupBtn.closest("[data-tool-group]");
      const open = !group.classList.contains("open");
      group.classList.toggle("open", open);
      groupBtn.setAttribute("aria-expanded", String(open));
      group.querySelector(".tool-group-items").hidden = !open;
      try { localStorage.setItem(`hutch-group:${runId}`, open ? "1" : "0"); } catch {}
      return;
    }
    const lineBtn = ev.target.closest("[data-tool-toggle]");
    if (lineBtn) {
      const line = lineBtn.closest("[data-tool-line]");
      const body = document.getElementById(lineBtn.getAttribute("aria-controls"));
      const open = lineBtn.getAttribute("aria-expanded") !== "true";
      lineBtn.setAttribute("aria-expanded", String(open));
      line.classList.toggle("open", open);
      if (body) body.hidden = !open;
      persist();
    }
  });
}

// Live fail-closed countdowns: any [data-deadline] (epoch ms) ticks down.
function updateTtls() {
  $$("[data-deadline]").forEach(el => {
    const target = el.querySelector("[data-ttl-text]") || el;
    const ms = Number(el.dataset.deadline) - Date.now();
    if (ms <= 0) {
      target.textContent = "expired — denied";
      el.classList.add("expired");
      return;
    }
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    target.textContent = `${m}:${String(s).padStart(2, "0")} left`;
  });
}
setInterval(updateTtls, 1000);

function renderChatEvent(e) {
  const t = e.ts ? e.ts.slice(11, 19) : "";
  const d = e.data || {};

  switch (e.type) {
    case "message":
      return `
        <div class="chat-msg agent">
          ${currentStudioBot ? hexAvatar(currentStudioBot, 30) : ""}
          <div class="chat-msg-stack">
            <span class="msg-role">${esc(d.role || "Agent")} <span class="msg-time">· ${t}</span></span>
            <div class="msg-bubble"><div class="msg-text">${esc(d.content || "")}</div></div>
          </div>
        </div>
      `;
    case "approval_request": {
      const deadline = e.ts ? new Date(e.ts).getTime() + 10 * 60 * 1000 : 0;
      return `
        <div class="approval-card-chat" data-approval-card="${esc(d.approval_id)}">
          <div class="approval-badge-bar">
            <span class="tag warn">Approval required</span>
            <span class="ttl-countdown" ${deadline ? `data-deadline="${deadline}"` : ""}>${icon("hourglass")}<span data-ttl-text>10:00 left</span></span>
          </div>
          <div class="approval-action-text">${esc(d.action || "Perform action")}</div>
          <pre class="approval-detail mono">${esc(JSON.stringify(d.detail ?? {}, null, 2))}</pre>
          <div class="approval-buttons" data-approval="${esc(d.approval_id)}">
            <button class="primary small" data-approve="1">Approve</button>
            <button class="danger small" data-approve="0">Deny</button>
            <label class="approval-always">
              <input type="checkbox" class="always"> always allow this action
            </label>
          </div>
        </div>
      `;
    }
    default:
      // tool_call / tool_result are consumed by pairToolEvents()
      return "";
  }
}

// ------------------------------------------------------------- BOTS VIEW

async function renderBots() {
  const bots = await api("/bots");
  view.innerHTML = `
    <div class="container">
      <div class="section-head">
        <div>
          <h1 class="page-title">Bots</h1>
          <p class="page-subtitle">Configured agents on this machine. Each has an isolated workspace, limits, and memory.</p>
        </div>
      </div>

      ${bots.length ? `
      <div class="bot-grid">
        ${bots.map(b => `
          <div class="bot-card">
            <div class="bot-head">
              <span class="bot-name">${esc(b.name)}</span>
              ${b.paused
                ? `<span class="status pending">paused</span>`
                : `<span class="status succeeded">active</span>`}
            </div>
            <p class="bot-desc">${esc(b.description || "No description provided.")}</p>
            <div class="bot-chips">
              <span class="tag model">${esc(b.model)}</span>
              ${b.schedule ? `<span class="tag schedule" title="${esc(b.schedule.timezone || "UTC")}">${esc(b.schedule.cron)}</span>` : `<span class="tag">on demand</span>`}
              <span class="tag">approval: ${esc(b.approval_mode)}</span>
            </div>
            <div class="bot-facts">
              <div>next run <b>${esc(b.next_run_local || "—")}</b></div>
              <div>last success <b title="${esc(b.last_success || "")}">${timeAgo(b.last_success)}</b></div>
              <div>tokens today <b>${fmtTokens(b.tokens_today)}</b></div>
              <div>memories <b>${b.memory_count}</b></div>
            </div>
            <div class="card-actions">
              <button class="primary small" data-action="run" data-bot="${esc(b.name)}">${icon("zap")} Run</button>
              <button class="ghost small" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                ${b.paused ? "Resume" : "Pause"}
              </button>
              <a class="btn ghost small" href="#/chat/${esc(b.name)}">Open in Studio</a>
            </div>
          </div>
        `).join("")}
      </div>
      ` : `
      <div class="empty-state">
        ${icon("bot", "icon-lg")}
        <p>No bots yet.</p>
        <p class="hint">Create a bot, or run <span class="mono">hutch init</span> for starter templates.</p>
        <button class="primary" id="btn-create-first-bot">Create your first bot</button>
      </div>
      `}
    </div>
  `;

  $("#btn-create-first-bot")?.addEventListener("click", promptNewBot);
  wireCommon();
}

// ------------------------------------------------------------- RUNS ARCHIVE

const RUNS_PAGE_SIZE = 25;
let runsState = { all: [], status: "all", q: "", shown: RUNS_PAGE_SIZE };

async function renderRuns(query = "") {
  const params = new URLSearchParams(query);
  runsState = {
    all: await api("/runs?limit=200"),
    status: params.get("status") || "all",
    q: params.get("q") || "",
    shown: RUNS_PAGE_SIZE,
  };

  view.innerHTML = `
    <div class="container">
      <h1 class="page-title">Runs</h1>
      <p class="page-subtitle">Every task executed on this machine, newest first. Click a row for the full transcript.</p>

      <div class="runs-filter-bar">
        <label class="visually-hidden" for="run-search">Filter runs</label>
        <input type="text" id="run-search" placeholder="Filter by bot or prompt…" value="${esc(runsState.q)}">
        <div class="runs-filter-pills" role="group" aria-label="Filter by status">
          ${["all", "succeeded", "failed", "waiting_approval"].map(f => `
            <button class="ghost small ${runsState.status === f ? "active" : ""}" data-filter="${f}" aria-pressed="${runsState.status === f}">
              ${f === "all" ? "All" : f === "waiting_approval" ? "Waiting" : f[0].toUpperCase() + f.slice(1)}
            </button>
          `).join("")}
        </div>
        <span class="hint" id="runs-count"></span>
      </div>

      <div class="table-wrap" id="runs-table-wrap"></div>
    </div>
  `;

  const syncHash = () => {
    const p = new URLSearchParams();
    if (runsState.status !== "all") p.set("status", runsState.status);
    if (runsState.q) p.set("q", runsState.q);
    const next = `#/runs${p.toString() ? `?${p}` : ""}`;
    // replaceState keeps filter state shareable without re-rendering the view
    history.replaceState(null, "", next);
  };

  const renderRows = () => {
    const q = runsState.q.trim().toLowerCase();
    const filtered = runsState.all.filter(r => {
      if (runsState.status !== "all" && r.status !== runsState.status) return false;
      if (q && !`${r.bot_name} ${r.prompt}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const wrap = $("#runs-table-wrap");
    if (!filtered.length) {
      wrap.innerHTML = runsState.all.length ? `
        <div class="empty-state">
          ${icon("search", "icon-lg")}
          <p>No runs match this filter.</p>
          <button class="ghost small" id="runs-clear">Clear filters</button>
        </div>` : `
        <div class="empty-state">
          ${icon("zap", "icon-lg")}
          <p>No runs yet.</p>
          <p class="hint">Start a bot from the Studio and its transcript will appear here.</p>
          <a class="btn primary small" href="#/chat">Open Studio</a>
        </div>`;
      $("#runs-clear")?.addEventListener("click", () => {
        runsState = { ...runsState, status: "all", q: "", shown: RUNS_PAGE_SIZE };
        $("#run-search").value = "";
        $$(".runs-filter-pills button").forEach(b => {
          const on = b.dataset.filter === "all";
          b.classList.toggle("active", on);
          b.setAttribute("aria-pressed", String(on));
        });
        syncHash();
        renderRows();
      });
    } else {
      const rows = filtered.slice(0, runsState.shown);
      wrap.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Bot</th>
              <th>Status</th>
              <th>Prompt</th>
              <th class="num">Steps</th>
              <th class="num">Tokens</th>
              <th>Executed</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => `
              <tr class="clickable" tabindex="0" role="link" aria-label="Open run ${esc(r.id)}" data-goto="#/run/${esc(r.id)}" title="${esc(r.created_at || "")}">
                <td class="mono">${esc(r.id.slice(0, 16))}…</td>
                <td><b>${esc(r.bot_name)}</b></td>
                <td>${statusChip(r.status)}</td>
                <td class="cell-truncate">${esc(r.prompt)}</td>
                <td class="num">${r.steps}</td>
                <td class="num">${fmtTokens(r.tokens)}</td>
                <td class="mono" title="${esc(r.created_at || "")}">${timeAgo(r.created_at)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        ${filtered.length > runsState.shown ? `
          <div style="padding:10px 16px; border-top:1px solid var(--border-subtle); text-align:center;">
            <button class="ghost small" id="runs-more">Show ${Math.min(RUNS_PAGE_SIZE, filtered.length - runsState.shown)} more of ${filtered.length}</button>
          </div>` : ""}
      `;
      $("#runs-more")?.addEventListener("click", () => {
        runsState.shown += RUNS_PAGE_SIZE;
        renderRows();
      });
      $$("tr[data-goto]", wrap).forEach(tr => {
        const go = () => { location.hash = tr.dataset.goto; };
        tr.addEventListener("click", go);
        tr.addEventListener("keydown", ev => { if (ev.key === "Enter") go(); });
      });
    }
    $("#runs-count").textContent = `${filtered.length} run${filtered.length === 1 ? "" : "s"}`;
  };

  let searchTimer = null;
  $("#run-search").addEventListener("input", ev => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      runsState.q = ev.target.value;
      runsState.shown = RUNS_PAGE_SIZE;
      syncHash();
      renderRows();
    }, 180);
  });
  $$(".runs-filter-pills button").forEach(btn => {
    btn.addEventListener("click", () => {
      runsState.status = btn.dataset.filter;
      runsState.shown = RUNS_PAGE_SIZE;
      $$(".runs-filter-pills button").forEach(b => {
        const on = b === btn;
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", String(on));
      });
      syncHash();
      renderRows();
    });
  });

  renderRows();
}

// ------------------------------------------------------------- APPROVALS

async function renderApprovals() {
  const approvals = await api("/approvals");
  view.innerHTML = `
    <div class="container">
      <h1 class="page-title">Approvals</h1>
      <p class="page-subtitle">A bot wants to perform an irreversible action. Unanswered requests expire as <b>denied</b>.</p>

      ${approvals.map(a => {
        const deadline = a.created_at ? new Date(a.created_at).getTime() + 10 * 60 * 1000 : 0;
        return `
        <div class="approval-card-chat" data-approval-card="${esc(a.id)}">
          <div class="approval-badge-bar">
            <div class="bot-header-chips">
              <b>${esc(a.bot_name)}</b>
              <span class="tag">${esc(a.tool)}</span>
            </div>
            <span class="ttl-countdown" ${deadline ? `data-deadline="${deadline}"` : ""}>${icon("hourglass")}<span data-ttl-text>10:00 left</span></span>
          </div>
          <div class="approval-action-text">${esc(a.action)}</div>
          <pre class="approval-detail mono">${esc(JSON.stringify(a.detail ?? {}, null, 2))}</pre>
          <div class="approval-buttons" data-approval="${esc(a.id)}">
            <button class="primary small" data-approve="1">Approve</button>
            <button class="danger small" data-approve="0">Deny</button>
            <label class="approval-always">
              <input type="checkbox" class="always"> always allow for this bot
            </label>
            <a class="btn ghost small" href="#/run/${esc(a.run_id)}">Open run</a>
          </div>
        </div>
        `;
      }).join("") || `
        <div class="empty-state">
          ${icon("check", "icon-lg")}
          <p>No pending approvals.</p>
          <p class="hint">When a bot hits a gated action, it waits here for your decision.</p>
        </div>
      `}
    </div>
  `;
  wireApprovals();
  updateTtls();
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
          <a class="btn primary" href="#/chat/${esc(b.name)}">${icon("chat")} Open Studio</a>
          <button class="danger" id="btn-delete-bot">Delete Bot</button>
        </div>
      </div>

      <div class="panel" style="margin-bottom:18px;">
        <h3 style="margin-top:0">Instructions</h3>
        <textarea id="bot-instructions" style="min-height:120px;font-family:var(--font-mono);">${esc(b.instructions || "")}</textarea>
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
    if (!(await confirmDialog({
      title: "Delete bot",
      body: `Delete <b>${esc(b.name)}</b>? Its workspace, memory, and transcripts stay on disk, but the bot and its schedule are removed.`,
      confirmText: "Delete bot",
      danger: true,
    }))) return;
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
        <a class="btn ghost" href="#/runs">Back to Runs</a>
      </div>
      <div class="panel" style="margin-bottom:16px;">
        <b>Prompt:</b><br><span style="color:var(--text-dim)">${esc(r.prompt)}</span>
      </div>
      <div id="chat-stream"></div>
    </div>
  `;
  await renderChatFeed(runId);
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
