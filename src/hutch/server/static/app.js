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

// Bounded screen-reader announcer. The main view is deliberately no longer a live
// region: re-rendering it announced the entire page on every poll. Only deliberate
// lifecycle changes go through here, and repeats are cleared first so assistive tech
// does not swallow an identical message.
let announceTimer = null;
function announce(msg) {
  const el = $("#live-status");
  if (!el) return;
  clearTimeout(announceTimer);
  el.textContent = "";
  announceTimer = setTimeout(() => { el.textContent = msg; }, 40);
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
// Identity hues (not status): the first was the retired emerald, which read as a
// leftover green accent beside the blue UI. Kept in the brand family, distinct
// from the success/warning *state* colours on purpose.
const AVATAR_HUES = [
  { fg: "#52a8ff", bg: "rgba(82, 168, 255, 0.1)" },
  { fg: "#7c9cff", bg: "rgba(124, 156, 255, 0.1)" },
  { fg: "#9daebf", bg: "rgba(157, 174, 191, 0.1)" },
  { fg: "#fbbf24", bg: "rgba(251, 191, 36, 0.1)" },
];

function botHue(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_HUES[h % AVATAR_HUES.length];
}

function hexAvatar(name, size = 40) {
  const hue = botHue(name);
  // Pointy-top hexagon echoing the hutch logo mark, with a real 2px stroke —
  // a clip-path hexagon cannot carry a border, which read as a flat chip.
  return `<svg class="hex-avatar" width="${size}" height="${size}" viewBox="0 0 36 40" aria-hidden="true" style="color:${hue.fg}">
    <path d="M18 2.5 33.5 11.5v17L18 37.5 2.5 28.5v-17z" fill="${hue.bg}" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
    <text x="18" y="25.5" text-anchor="middle" font-family="var(--font-mono)" font-size="${Math.round(size * 0.36)}" font-weight="700" fill="currentColor">${esc(String(name)[0].toUpperCase())}</text>
  </svg>`;
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
  [/^#\/overview$/, renderOverview, "overview"],
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
  if (approvalsTimer) { clearInterval(approvalsTimer); approvalsTimer = null; }
}

window.addEventListener("hashchange", route);

// App-wide attention: the Approvals nav item carries the pending count everywhere,
// and a new arrival is announced once through the bounded live region.
let lastPendingCount = null;
async function refreshBadge() {
  try {
    const stats = await api("/stats");
    const n = stats.pending_approvals || 0;
    const badge = $("#approval-badge");
    if (badge) {
      badge.textContent = n;
      badge.classList.toggle("hidden", n === 0);
    }
    $('[data-nav="approvals"]')?.classList.toggle("attention", n > 0);
    if (lastPendingCount !== null && n > lastPendingCount) {
      announce(`${n} approval${n === 1 ? "" : "s"} waiting for you.`);
    }
    lastPendingCount = n;
  } catch {}
}

// ------------------------------------------------------------- executor health

// The old badge said "live" in static markup regardless of reality. Health is now
// established from the server (version + schema) with a heartbeat, and degrades to
// reconnecting/offline so a dead backend is never shown as green.
const HEARTBEAT_MS = 15000;
let lastHealthAt = 0;
let lastDaemonState = "";

function setDaemon(state, title) {
  const pill = $("#daemon-pill");
  if (!pill) return;
  const label = { live: "live", reconnecting: "reconnecting", offline: "offline", connecting: "checking" }[state] || state;
  if (lastDaemonState === state) { pill.title = title; return; }
  lastDaemonState = state;
  pill.dataset.state = state;
  pill.className = `pill daemon ${state}${state === "live" ? " pulse" : ""}`;
  pill.textContent = label;
  pill.title = title;
}

async function pollHealth() {
  try {
    const h = await api("/health");
    lastHealthAt = Date.now();
    setDaemon("live", `daemon live — v${h.version} · schema ${h.schema}`);
  } catch {
    const recent = lastHealthAt && Date.now() - lastHealthAt < 3 * HEARTBEAT_MS;
    const state = recent ? "reconnecting" : "offline";
    const changed = lastDaemonState !== state;
    setDaemon(state,
      recent ? "Server unreachable — retrying on the next heartbeat"
             : "Server offline — commands will not run until it returns");
    if (changed) announce("Connection to the hutch server was lost. Commands are paused until it returns.");
  }
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
      <!-- Left rail: bot personas (the single switcher) -->
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
        <div class="rail-foot">
          <a class="rail-add" href="#/bot/${esc(bot.name)}" title="Specs and memory" aria-label="Specs and memory">${icon("sliders")}</a>
          <button class="rail-add" type="button" id="sidebar-new-bot" title="New bot" aria-label="New bot">${icon("plus")}</button>
        </div>
      </aside>

      <!-- Center Stage: Conversation & Live Execution -->
      <div class="studio-main" role="region" aria-label="Conversation">
        <header class="studio-main-header">
          <div class="bot-header-info">
            ${hexAvatar(bot.name, 34)}
            <div class="bot-header-id">
              <h1 class="bot-header-title">${esc(bot.name)}</h1>
              <span class="bot-header-meta">${esc(bot.model)} &middot; asks before running</span>
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
            <div class="composer-meta-row" hidden>
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
              <button class="composer-add" type="button" id="composer-toggle" aria-label="Suggestions and budget" aria-expanded="false">${icon("plus")}</button>
              <label class="visually-hidden" for="chat-prompt">Task prompt for ${esc(bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message ${esc(bot.name)}…"></textarea>
              <span class="model-switch-slot" id="model-switch-slot"></span>
              <button class="composer-send" id="chat-send" aria-label="Send prompt">${icon("send")}</button>
            </div>
          </div>
        </footer>
      </div>

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

  // Wire sidebar bot switching (mouse + keyboard)
  $$("[data-switch-bot]").forEach(item => {
    const activate = () => renderChatStudio(item.dataset.switchBot);
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
  const switcher = window.hutchModelSwitcher?.mount($("#model-switch-slot"), bot);   // model-switcher.js
  const triggerRun = async (promptVal) => {
    if (!promptVal.trim()) return;
    send.disabled = true;
    send.textContent = "Running…";
    lastPrompt = promptVal.trim();
    try {
      const r = await api(`/bots/${encodeURIComponent(bot.name)}/run`, { method: "POST", body: { prompt: promptVal.trim(), model: switcher?.selected() || undefined } });
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

  // The plus button reveals suggestions and the budget row (collapsed by default,
  // mirroring the reference composer's plus affordance).
  const composerToggle = $("#composer-toggle");
  const metaRow = $(".composer-meta-row");
  composerToggle?.addEventListener("click", () => {
    const open = metaRow.hasAttribute("hidden");
    if (open) metaRow.removeAttribute("hidden");
    else metaRow.setAttribute("hidden", "");
    composerToggle.setAttribute("aria-expanded", String(open));
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

  // Announce lifecycle changes once (started -> waiting/finished), and show the
  // working indicator only while the bot is actually computing.
  const prevStatus = seenRunStatus.get(runId);
  if (prevStatus !== run.status) {
    seenRunStatus.set(runId, run.status);
    if (run.status === "waiting_approval") {
      announce(`${run.bot_name || "A bot"} needs your approval before it can continue.`);
    } else if (prevStatus && ACTIVE.has(prevStatus) && !ACTIVE.has(run.status)) {
      announce(`Run ${run.status.replace(/_/g, " ")}.`);
    }
  }
  if (run.status === "running" || run.status === "pending") {
    stream.insertAdjacentHTML("beforeend", typingHtml());
  }
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

// Visual "the bot is working" indicator. Deliberately aria-hidden: the run status
// chip and the bounded announcer convey state, so a screen reader is not told
// "typing" on every poll. A waiting-for-human run is not computing, so it gets none.
// Reference: Grok Bot dropped the Bot's name from its working status (v0.67.0) — the
// chat header already identifies the bot, so repeating it in a busy region is noise.
function typingHtml() {
  return `<div class="typing" aria-hidden="true">
    <span class="typing-dots"><span></span><span></span><span></span></span>
    <span class="typing-label">Working…</span>
  </div>`;
}

// Remember the last status we rendered per run so lifecycle changes are announced
// once (started -> waiting/finished) instead of on every poll.
const seenRunStatus = new Map();

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

// Live fail-closed countdowns: any [data-deadline] (epoch ms) ticks down, and at
// zero the gate flips to its resolved state rather than leaving dead controls.
function updateTtls() {
  $$("[data-deadline]").forEach(el => {
    const ms = Number(el.dataset.deadline) - Date.now();
    if (ms <= 0) {
      const card = el.closest("[data-approval-card]");
      if (card && !card.classList.contains("expired")) {
        const action = card.querySelector(".approval-action-text")?.textContent || "";
        card.outerHTML = approvalResolvedHtml({ approval_id: card.dataset.approvalCard, action }, "expired");
      }
      return;
    }
    el.classList.remove("expired");
    const target = el.querySelector("[data-ttl-text]");
    if (!target) return;
    const m = Math.floor(ms / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    target.textContent = `${m}:${String(s).padStart(2, "0")} left`;
  });
}
setInterval(updateTtls, 1000);

// --------------------------------------------------------- approvals (shared)

// One approval, rendered identically in the chat feed and the approvals queue:
// the action in plain language first, the technical detail behind a disclosure, and
// the exact scope of an "always allow" grant. System-generated cards stay visually
// distinct from model prose so a message cannot impersonate a gate.
function approvalCardHtml(a, { botName = "", resolved = "" } = {}) {
  const id = a.approval_id || a.id;
  if (resolved && resolved !== "pending") return approvalResolvedHtml(a, resolved, botName);

  const action = a.action || "Perform action";
  const tool = a.tool || "";
  const rule = a.rule || "";
  const risk = a.risk || "medium";
  const outward = !!a.outward;
  const deadline = a.deadline
    || (a.expires_at ? new Date(a.expires_at).getTime()
      : (a.created_at ? new Date(a.created_at).getTime() + 10 * 60 * 1000 : 0));
  const expired = deadline && deadline <= Date.now();
  const detail = a.detail && Object.keys(a.detail || {}).length ? JSON.stringify(a.detail, null, 2) : "";
  const segments = a.segments || [];
  const stickyKey = a.sticky_key || "";
  const canAlways = !!(stickyKey && !outward);
  const runId = a.run_id || "";

  const rows = [
    ["Tool", tool],
    rule ? ["Why you are asked", rule] : null,
    ["Reversibility", outward
      ? "Sends data out of this machine — Stop cannot recall it once it has gone"
      : "Confined to this machine's workspace"],
  ].filter(Boolean).map(([k, v]) =>
    `<div class="review-row"><span class="review-key">${esc(k)}</span><span>${esc(v)}</span></div>`).join("");

  return `
    <div class="approval-card-chat risk-${esc(risk)} ${outward ? "outward" : ""} ${expired ? "expired" : ""}"
         data-approval-card="${esc(id)}" ${deadline ? `data-deadline="${deadline}"` : ""}>
      <div class="approval-badge-bar">
        <div class="approval-head-left">
          <span class="tag warn">Approval required</span>
          ${botName ? `<b class="approval-bot">${esc(botName)}</b>` : ""}
          ${tool ? `<span class="tag">${esc(tool)}</span>` : ""}
          <span class="tag ${risk === "high" ? "danger" : risk === "low" ? "" : "warn"}">${esc(risk)} risk</span>
          ${outward ? `<span class="tag danger" title="Leaves this machine; always-allow is not offered">outward</span>` : ""}
        </div>
        <span class="ttl-countdown" data-deadline-parent>${icon("hourglass")}<span data-ttl-text>${expired ? "expired — denied" : ""}</span></span>
      </div>
      <div class="approval-action-text">${esc(action)}</div>
      <details class="approval-review">
        <summary>Review details</summary>
        <div class="review-rows">${rows}</div>
        ${segments.length ? `<div class="approval-segments">${segments.map(s => `
          <div class="approval-seg">
            <code>${esc(s.text)}</code>
            <span class="tag ${s.verdict === "deny" ? "danger" : s.verdict === "ask" ? "warn" : ""}">${esc(s.verdict)}</span>
            <span class="seg-why">${esc(s.reason || "")}</span>
          </div>`).join("")}</div>` : ""}
        ${detail ? `<span class="review-label">Raw request</span><pre class="approval-detail mono">${esc(detail)}</pre>` : ""}
      </details>
      ${canAlways
        ? `<p class="hint approval-scope">Always-allow remembers <code>${esc(stickyKey)}</code> for this bot. Revoke it any time in the bot's Sticky permissions.</p>`
        : outward
          ? `<p class="hint approval-scope">This action leaves the machine, so always-allow is not offered — you decide each time.</p>`
          : ""}
      <div class="approval-buttons" data-approval="${esc(id)}">
        <button class="primary small" data-approve="1">Allow once</button>
        ${canAlways ? `<button class="ghost small" data-approve="always">Always allow for this bot</button>` : ""}
        <button class="ghost small" data-approve="0">Deny</button>
        ${runId ? `<a class="btn ghost small" href="#/run/${esc(runId)}">Open run</a>` : ""}
      </div>
    </div>`;
}

// A resolved gate. Server-authoritative: it names who decided and when, so two
// devices racing to answer the same card end up agreeing rather than diverging.
function approvalResolvedHtml(a, outcome, botName = "") {
  const labels = {
    approved: "Approved", denied: "Denied",
    expired: "Expired — denied by timeout", missing: "No longer exists",
  };
  const ok = outcome === "approved";
  const by = a.decided_by && outcome !== "expired" && outcome !== "missing" ? ` by ${esc(a.decided_by)}` : "";
  const at = a.resolved_at ? ` · ${timeAgo(a.resolved_at)}` : "";
  return `
    <div class="approval-card-chat resolved ${ok ? "allowed" : "denied"}" data-approval-card="${esc(a.approval_id || a.id || "")}">
      <div class="approval-badge-bar">
        <span class="tag ${ok ? "ok" : "danger"}">${icon(ok ? "check" : "x")} ${esc(labels[outcome] || "Resolved")}${by}${at}</span>
        ${botName ? `<b class="approval-bot">${esc(botName)}</b>` : ""}
      </div>
      ${a.action ? `<div class="approval-action-text muted">${esc(a.action)}</div>` : ""}
    </div>`;
}

// Resolve, then reconcile against the real state on any failure (409 = answered
// elsewhere, 404 = gone). We never claim a success the server did not confirm.
async function resolveApproval(id, choice, card) {
  const always = choice === "always";
  const approve = choice === "1" || always;
  const action = card?.querySelector(".approval-action-text")?.textContent || "";
  card?.querySelectorAll("button").forEach(b => { b.disabled = true; });   // no double-submit
  try {
    await api(`/approvals/${encodeURIComponent(id)}/${approve ? "approve" : "deny"}`, {
      method: "POST", body: approve ? { always } : {},
    });
    toast(approve ? (always ? "Allowed — remembered for this bot" : "Allowed once") : "Denied");
    if (card) card.outerHTML = approvalResolvedHtml({ approval_id: id, action }, approve ? "approved" : "denied");
  } catch (err) {
    let current = null;
    try { current = await api(`/approvals/${encodeURIComponent(id)}`); } catch { /* 404: gone */ }
    if (current && current.status && current.status !== "pending") {
      if (card) card.outerHTML = approvalResolvedHtml({ ...current, approval_id: id }, current.status, current.bot_name || "");
      toast(`Already ${current.status}${current.decided_by ? ` by ${current.decided_by}` : ""} — nothing changed.`);
    } else if (!current) {
      if (card) card.outerHTML = approvalResolvedHtml({ approval_id: id, action }, "missing");
      toast("This request no longer exists — it may have been replaced.", true);
    } else {
      card?.querySelectorAll("button").forEach(b => { b.disabled = false; });
      toast(err.message || "Could not resolve approval", true);
    }
  }
  refreshBadge();
}

function renderChatEvent(e) {
  const t = e.ts ? e.ts.slice(11, 19) : "";
  const d = e.data || {};

  switch (e.type) {
    case "message": {
      const hue = currentStudioBot ? botHue(currentStudioBot) : null;
      return `
        <div class="chat-msg agent">
          ${currentStudioBot ? hexAvatar(currentStudioBot, 30) : ""}
          <div class="chat-msg-stack">
            <span class="msg-role"${hue ? ` style="color:${hue.fg}"` : ""}>${esc(currentStudioBot || d.role || "Agent")} <span class="msg-time">· ${t}</span></span>
            <div class="msg-bubble"><div class="msg-text">${esc(d.content || "")}</div></div>
          </div>
        </div>
      `;
    }
    case "approval_request": {
      const deadline = d.expires_at ? new Date(d.expires_at).getTime()
        : (e.ts ? new Date(e.ts).getTime() + 10 * 60 * 1000 : 0);
      return approvalCardHtml({ ...d, deadline, run_id: currentRunId || e.run_id },
        { botName: currentStudioBot || "" });
    }
    default:
      // tool_call / tool_result are consumed by pairToolEvents()
      return "";
  }
}

// ------------------------------------------------------------- BOTS VIEW

async function renderOverview() {
  const o = await api("/overview");
  const s = o.stats || {};
  const fmt = (n) => Number(n || 0).toLocaleString();
  const row = (r) => `
    <a class="ov-row" href="#/run/${esc(r.id)}">
      <span class="ov-row-main"><b>${esc(r.bot_name)}</b>${statusChip(r.status)}</span>
      <span class="ov-row-prompt">${esc((r.prompt || "").slice(0, 84))}</span>
      <span class="ov-row-meta mono">${r.steps} steps · ${fmt(r.tokens)} tok</span>
    </a>`;
  const waitBox = (w) => w && w.cause ? `<div class="ov-wait banner ${esc(w.kind || "wait")}"><b>Why:</b> ${esc(w.cause)}<br><b>What to do:</b> ${esc(w.fix)}</div>` : "";
  view.innerHTML = `
    <div class="container">
      <div class="page-head"><div><h1 class="page-title">Overview</h1>
        <p class="page-subtitle">What needs you, what is running, and what has gone quiet.</p></div>
        <a class="btn ghost" href="#/bots">All bots ${icon("arrow")}</a></div>
      <div class="bento kpi-bento">
        <div class="card kpi"><span class="kpi-label">Bots</span><span class="kpi-val mono">${fmt(s.bots)}</span></div>
        <div class="card kpi"><span class="kpi-label">Runs today</span><span class="kpi-val mono">${fmt(s.runs_today)}</span></div>
        <div class="card kpi"><span class="kpi-label">Tokens today</span><span class="kpi-val mono">${fmt(s.tokens_today)}</span></div>
        <div class="card kpi"><span class="kpi-label">Spend today</span><span class="kpi-val mono">$${Number(s.spend_today || 0).toFixed(2)}</span></div>
      </div>
      <div class="bento ov-grid">
        <section class="card ov-col loud">
          <h2 class="ov-h">${icon("inbox")} Needs you <span class="badge ${o.needs_count ? "" : "hidden"}">${o.needs_count}</span></h2>
          ${o.needs_count ? "" : `<div class="empty-state">${icon("check", "icon-lg")}<p>Nothing needs you.</p></div>`}
          ${(o.approvals || []).map(a => `
            <a class="ov-approval" href="#/approvals">
              <span class="kicker">Approval required</span>
              <span class="ov-approval-head"><b>${esc(a.bot_name)}</b> <span class="tag">${esc(a.tool)}</span> <span class="tag ${a.risk === "high" ? "danger" : "warn"}">${esc(a.risk)} risk</span></span>
              <span class="ov-approval-action">${esc(a.action)}</span>
            </a>`).join("")}
          ${(o.humans || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
          ${(o.failures || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
        </section>
        <section class="card ov-col quiet">
          <h2 class="ov-h">${icon("play")} Running now <span class="count">${(o.running || []).length}</span></h2>
          ${(o.running || []).length ? (o.running || []).map(row).join("") : `<div class="empty-state"><p>Nothing is running.</p></div>`}
        </section>
        <section class="card ov-col quiet">
          <h2 class="ov-h">${icon("clock")} Stale <span class="count">${(o.stale || []).length}</span></h2>
          ${(o.stale || []).length ? (o.stale || []).map(x => `
            <a class="ov-row" href="#/bot/${esc(x.bot_name)}">
              <span class="ov-row-main"><b>${esc(x.bot_name)}</b>${statusChip("stale")}</span>
              <span class="ov-row-meta">last success ${timeAgo(x.last_success)}</span>
            </a>`).join("") : `<div class="empty-state">${icon("check", "icon-lg")}<p>Every scheduled bot is up to date.</p></div>`}
        </section>
      </div>
    </div>`;
}

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
      const nowMs = Date.now();
      const durMs = (r) => {
        const a = r.created_at ? new Date(r.created_at).getTime() : nowMs;
        const b = r.finished_at ? new Date(r.finished_at).getTime() : nowMs;
        return Math.max(0, b - a);
      };
      const fmtDur = (ms) => ms < 1000 ? `${ms}ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : ms < 3600000 ? `${Math.round(ms / 60000)}m` : `${(ms / 3600000).toFixed(1)}h`;
      const maxDur = Math.max(1, ...rows.map(durMs));
      wrap.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Bot</th>
              <th>Status</th>
              <th>Prompt</th>
              <th>Timeline</th>
              <th class="num">Steps</th>
              <th class="num">Tokens</th>
              <th>Executed</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => {
              const d = durMs(r);
              const cls = r.status === "failed" ? "bad" : r.status === "waiting_approval" ? "warn" : "";
              return `
              <tr class="clickable" tabindex="0" role="link" aria-label="Open run ${esc(r.id)}" data-goto="#/run/${esc(r.id)}" title="${esc(r.created_at || "")}">
                <td class="mono">${esc(r.id.slice(0, 16))}…</td>
                <td><b>${esc(r.bot_name)}</b></td>
                <td>${statusChip(r.status)}</td>
                <td class="cell-truncate">${esc(r.prompt)}</td>
                <td><span class="timeline"><span class="timeline-track"><i class="timeline-fill ${cls}" style="width:${Math.max(3, Math.round(d / maxDur * 100))}%"></i></span><span class="timeline-label">${fmtDur(d)}</span></span></td>
                <td class="num">${r.steps}</td>
                <td class="num">${fmtTokens(r.tokens)}</td>
                <td class="mono" title="${esc(r.created_at || "")}">${timeAgo(r.created_at)}</td>
              </tr>`;
            }).join("")}
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

let approvalsTimer = null;

async function renderApprovals() {
  clearInterval(approvalsTimer);
  view.innerHTML = `
    <div class="container">
      <h1 class="page-title">Approvals</h1>
      <p class="page-subtitle">A bot wants to perform an irreversible action. Unanswered requests expire as <b>denied</b>.</p>
      <div id="approvals-pending"></div>
      <h2 class="section-sub">Recently decided</h2>
      <div id="approvals-resolved"></div>
    </div>`;
  await refreshApprovals();
  // Keep the queue honest across devices: a card answered on your phone (or by a
  // timeout) must clear or update here without a manual reload.
  approvalsTimer = setInterval(refreshApprovals, 5000);
}

async function refreshApprovals() {
  const [pending, resolved] = await Promise.all([
    api("/approvals").catch(() => []),
    api("/approvals?status=resolved&limit=8").catch(() => []),
  ]);
  const list = $("#approvals-pending");
  const done = $("#approvals-resolved");
  if (!list || !done) return;                      // route changed mid-flight
  list.innerHTML = pending.length
    ? pending.map(a => approvalCardHtml(a, { botName: a.bot_name })).join("")
    : `<div class="empty-state">${icon("check", "icon-lg")}
         <p>No pending approvals.</p>
         <p class="hint">When a bot hits a gated action, it waits here for your decision.</p></div>`;
  done.innerHTML = (resolved || []).length
    ? resolved.map(a => approvalResolvedHtml(a, a.status, a.bot_name)).join("")
    : `<p class="hint">Decided approvals appear here.</p>`;
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
        <h2 class="panel-title">Instructions</h2>
        <label class="visually-hidden" for="bot-instructions">Bot instructions</label>
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

function fmtDur(ms) {
  ms = Math.max(0, ms || 0);
  return ms < 1000 ? `${Math.round(ms)}ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}s`
    : ms < 3600000 ? `${Math.round(ms / 60000)}m` : `${(ms / 3600000).toFixed(1)}h`;
}

async function renderRunDetail(runId) {
  const r = await api(`/runs/${runId}`);
  const nowMs = Date.now();
  const a = r.created_at ? new Date(r.created_at).getTime() : nowMs;
  const b = r.finished_at ? new Date(r.finished_at).getTime() : nowMs;
  const steps = (r.events || []).filter(e => e.type === "step").map(e => e.data);
  const sum = (k) => steps.reduce((t, d) => t + (d[k] || 0), 0);
  const model = sum("model_ms"), tool = sum("tool_ms"), over = sum("overhead_ms");
  const total = Math.max(1, model + tool + over);
  const pct = (v) => (v / total * 100).toFixed(1);
  view.innerHTML = `
    <div class="container">
      <div class="page-head">
        <div>
          <p class="crumb"><a href="#/runs">Runs</a></p>
          <h1 class="page-title">Run <span class="mono">${esc(r.id.slice(0, 16))}</span></h1>
          <p class="page-subtitle">Bot: <a href="#/chat/${esc(r.bot_name)}">${esc(r.bot_name)}</a> &middot; ${statusChip(r.status)} &middot; started by ${esc(r.origin || "you")}</p>
        </div>
        <a class="btn ghost" href="#/runs">${icon("arrow-left")} Back to Runs</a>
      </div>
      <div class="bento kpi-bento">
        <div class="card kpi"><span class="kpi-label">Steps</span><span class="kpi-val mono">${r.steps}</span></div>
        <div class="card kpi"><span class="kpi-label">Elapsed</span><span class="kpi-val mono">${fmtDur(Math.max(0, b - a))}</span></div>
        <div class="card kpi"><span class="kpi-label">Spend</span><span class="kpi-val mono">$${(r.cost_usd || 0).toFixed(4)}</span></div>
        <div class="card kpi"><span class="kpi-label">Tokens</span><span class="kpi-val mono">${fmtTokens(r.tokens)}</span></div>
      </div>
      ${steps.length ? `
      <div class="card run-timing">
        <h2 class="ov-h">${icon("chart")} Where the time went</h2>
        <div class="timeline-stack" role="img" aria-label="model ${Math.round(model)}ms, tools ${Math.round(tool)}ms, hutch ${Math.round(over)}ms">
          <i class="s-model" style="width:${pct(model)}%"></i>
          <i class="s-tool" style="width:${pct(tool)}%"></i>
          <i class="s-over" style="width:${pct(over)}%"></i>
        </div>
        <div class="timeline-legend mono">
          <span><i class="dot s-model"></i>model ${Math.round(model)}ms</span>
          <span><i class="dot s-tool"></i>tools ${Math.round(tool)}ms</span>
          <span><i class="dot s-over"></i>hutch ${Math.round(over)}ms</span>
        </div>
        <div class="step-strip" aria-hidden="true">
          ${steps.map(d => {
            const tot = (d.model_ms || 0) + (d.tool_ms || 0) + (d.overhead_ms || 0);
            return `<span class="step-seg" title="step ${d.n}" style="flex:${Math.max(1, tot)}"><i class="s-model" style="flex:${Math.max(0, d.model_ms || 0)}"></i><i class="s-tool" style="flex:${Math.max(0, d.tool_ms || 0)}"></i><i class="s-over" style="flex:${Math.max(0, d.overhead_ms || 0)}"></i></span>`;
          }).join("")}
        </div>
      </div>` : ""}
      <div class="card" style="margin-bottom:16px;"><b>Prompt:</b><br><span style="color:var(--text-dim)">${esc(r.prompt)}</span></div>
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
    btn.addEventListener("click", () => {
      const wrap = btn.closest("[data-approval]");
      if (!wrap) return;
      resolveApproval(wrap.dataset.approval, btn.dataset.approve, btn.closest("[data-approval-card]"));
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
pollHealth();
setInterval(pollHealth, HEARTBEAT_MS);

/* Full-screen mobile menu (header nav collapses to an overlay) */
(function () {
  const btn = document.getElementById("nav-toggle");
  const nav = document.getElementById("primary-nav");
  if (!btn || !nav) return;
  const setOpen = (open) => {
    nav.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };
  btn.addEventListener("click", () => setOpen(!nav.classList.contains("open")));
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
})();
