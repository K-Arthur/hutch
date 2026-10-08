/* hutch — operator workspace.
   Vanilla ES, hash-routed, zero external assets, zero build step.
   State ownership: the server is authoritative for runs/approvals/bots; this file
   keeps only view state (drafts, expansion, selection, scroll) in localStorage.
   Design system: docs/design-system.md · .impeccable/surfaces/. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const view = $("#view");
const topContext = $("#app-top-context");

const ACTIVE = new Set(["pending", "loading_model", "running", "waiting_approval", "waiting_human",
  "waiting_resources", "recovering", "cancelling"]);
const DEFAULT_STATUS_INFO = {
  pending: { label: "Queued", terminal: false },
  loading_model: { label: "Loading the model", terminal: false },
  running: { label: "Working", terminal: false },
  waiting_approval: { label: "Waiting for you", terminal: false },
  waiting_human: { label: "Needs you", terminal: false },
  waiting_resources: { label: "Waiting for a free slot or quota", terminal: false },
  recovering: { label: "Recovering", terminal: false },
  cancelling: { label: "Stopping", terminal: false },
  succeeded: { label: "Done", terminal: true },
  failed: { label: "Failed", terminal: true },
  stopped: { label: "Cancelled", terminal: true },
  outcome_unknown: { label: "Needs review", terminal: true },
  skipped: { label: "Skipped", terminal: true },
  stale: { label: "Stale", terminal: true },
};
let statusInfo = { ...DEFAULT_STATUS_INFO };
let currentConversationId = null;
let currentConversations = [];

/* ------------------------------------------------------------------ utils */

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

function newIdempotencyKey() {
  return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function storageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storageSet(key, value) { try { localStorage.setItem(key, value); } catch {} }
function storageRemove(key) { try { localStorage.removeItem(key); } catch {} }

async function payloadFingerprint(body) {
  const raw = JSON.stringify(body);
  if (window.crypto?.subtle) {
    const bytes = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw));
    return [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, "0")).join("");
  }
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i++) hash = Math.imul(hash ^ raw.charCodeAt(i), 16777619);
  return (hash >>> 0).toString(16);
}

async function messageIdempotencyKey(conversationId, body) {
  const storageKey = `hutch-pending-message:${conversationId}`;
  const fingerprint = await payloadFingerprint(body);
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.fingerprint === fingerprint && previous?.key) return previous.key;
  } catch { /* discard a damaged browser-local retry marker */ }
  const key = newIdempotencyKey();
  storageSet(storageKey, JSON.stringify({ key, fingerprint }));
  return key;
}

function clearMessageIdempotencyKey(conversationId, key) {
  const storageKey = `hutch-pending-message:${conversationId}`;
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.key === key) localStorage.removeItem(storageKey);
  } catch { storageRemove(storageKey); }
}

async function createStudioConversation(bot) {
  const storageKey = `hutch-pending-conversation:${bot.id}`;
  let key = storageGet(storageKey);
  if (!key) {
    key = newIdempotencyKey();
    storageSet(storageKey, key);
  }
  const conversation = await api("/v1/conversations", {
    method: "POST", headers: { "Idempotency-Key": key }, body: { bot: bot.id, title: "" },
  });
  storageRemove(storageKey);
  return conversation;
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
  // Transient notices auto-dismiss; errors persist until dismissed.
  if (!isError) setTimeout(dismiss, 4200);
}

// Bounded screen-reader announcer. The view itself is not a live region (it
// re-rendered on every poll); only deliberate lifecycle changes pass through here.
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

function fmtDur(ms) {
  ms = Math.max(0, ms || 0);
  return ms < 1000 ? `${Math.round(ms)}ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)}s`
    : ms < 3600000 ? `${Math.round(ms / 60000)}m` : `${(ms / 3600000).toFixed(1)}h`;
}

function isActiveStatus(status, terminal = null) {
  if (typeof terminal === "boolean") return !terminal;
  return statusInfo[status] ? !statusInfo[status].terminal : true;
}

// Status word pairs text with the chip's dot — state is never color-only.
function statusChip(status, serverLabel = null) {
  const label = serverLabel || statusInfo[status]?.label || "Status unavailable";
  return `<span class="status ${esc(status)}">${esc(label)}</span>`;
}

async function loadStatusInfo() {
  try {
    const labels = await api("/v1/status-labels");
    statusInfo = Object.fromEntries(labels.map(item => [item.status, item]));
    if (!statusInfo.stale) statusInfo.stale = DEFAULT_STATUS_INFO.stale;
  } catch { /* use bundled labels until the versioned API is reachable */ }
}

/* Inline SVG icon set — the only permitted iconography (see scripts/audit_emoji.py). */
const ICON_PATHS = {
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  zap: '<path d="M13 2 3 14h7l-1 8 11-12h-7l1-8z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.2 3.9A2 2 0 0 0 7.5 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  fileText: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  hourglass: '<path d="M5 22h14M5 2h14M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2"/>',
  bot: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
  caret: '<path d="m9 18 6-6-6-6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  alert: '<path d="M12 3.5 22 20.5H2z"/><path d="M12 10v5"/><path d="M12 18.2v.01"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-6 3 4 4-7"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  arrowLeft: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  layers: '<path d="m12 2 8.5 4.7L12 11.4 3.5 6.7z"/><path d="m3.5 12.6 8.5 4.7 8.5-4.7"/><path d="m3.5 17.3 8.5 4.7 8.5-4.7"/>',
  pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  key: '<path d="m21 2-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8Zm0 0L15.5 7.5m0 0 3 3L22 4l-3-3z"/>',
  brain: '<path d="M9.5 2a2.5 2.5 0 0 1 0 5v10a2.5 2.5 0 1 1-4.9.7A3 3 0 0 1 3 15a3 3 0 0 1 .5-5.9A2.5 2.5 0 0 1 5 5a2.5 2.5 0 0 1 4.5-3Z"/><path d="M14.5 2a2.5 2.5 0 0 0 0 5v10a2.5 2.5 0 1 0 4.9.7A3 3 0 0 0 21 15a3 3 0 0 0-.5-5.9A2.5 2.5 0 0 0 19 5a2.5 2.5 0 0 0-4.5-3Z"/>',
};

function icon(name, cls = "") {
  return `<svg class="icon ${cls}" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}

function truncate(s, n) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

function summarizeOutput(output) {
  if (!output) return "";
  return String(output).replace(/\s+/g, " ").trim();
}

/* ---------------------------------------------------------------- avatars
   Identity hues — never status colors (status rides the pip + its word).
   The first hue keeps the brand emerald lineage. */
const AVATAR_HUES = [
  { fg: "#34d399", bg: "rgba(52, 211, 153, 0.10)", line: "rgba(52, 211, 153, 0.34)", glow: "rgba(52, 211, 153, 0.30)" },
  { fg: "#7c9cff", bg: "rgba(124, 156, 255, 0.10)", line: "rgba(124, 156, 255, 0.34)", glow: "rgba(124, 156, 255, 0.28)" },
  { fg: "#9daebf", bg: "rgba(157, 174, 191, 0.10)", line: "rgba(157, 174, 191, 0.32)", glow: "rgba(157, 174, 191, 0.22)" },
  { fg: "#d9a06b", bg: "rgba(217, 160, 107, 0.10)", line: "rgba(217, 160, 107, 0.34)", glow: "rgba(217, 160, 107, 0.24)" },
  { fg: "#2dd4bf", bg: "rgba(45, 212, 191, 0.10)", line: "rgba(45, 212, 191, 0.34)", glow: "rgba(45, 212, 191, 0.26)" },
];

function botHue(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_HUES[h % AVATAR_HUES.length];
}

function botAvatar(name, size = 32, state = "") {
  const hue = botHue(name);
  const initial = esc(String(name)[0] ? String(name)[0].toUpperCase() : "?");
  return `<span class="avatar" style="--av:${size}px;--av-fg:${hue.fg};--av-bg:${hue.bg};--av-line:${hue.line};--av-glow:${hue.glow}" aria-hidden="true">${initial}${
    state ? `<span class="a-pip ${esc(state)}"></span>` : ""}</span>`;
}
const hexAvatar = botAvatar;   // shared renderers still call this name

function botState(b) {
  if (b.active_run_id) return "running";
  if (b.paused) return "paused";
  return "idle";
}

/* ------------------------------------------------------- composer drafts */

const draftKey = bot => `hutch:draft:${bot}`;
function loadDraft(bot) { try { return localStorage.getItem(draftKey(bot)) || ""; } catch { return ""; } }
function saveDraft(bot, text) { try { text ? localStorage.setItem(draftKey(bot), text) : localStorage.removeItem(draftKey(bot)); } catch {} }

/* ------------------------------------------------------------ view prefs */

const store$ = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch {} },
};

/* ---------------------------------------------------------------- modal */

let modalReturnFocus = null;

function openModal({ title, bodyHtml, onConfirm, onCancel, confirmText = "Confirm", confirmClass = "primary", wide = false }) {
  const root = $("#modal-root");
  modalReturnFocus = document.activeElement;
  root.innerHTML = `
    <div class="modal-backdrop" data-modal-backdrop>
      <div class="modal-card${wide ? " modal-wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-header">
          <h3 id="modal-title">${esc(title)}</h3>
          <button class="icon-btn" id="modal-close" aria-label="Close dialog">${icon("x")}</button>
        </div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-footer">
          <button class="btn ghost" id="modal-cancel">Cancel</button>
          <button class="btn ${confirmClass}" id="modal-confirm">${esc(confirmText)}</button>
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
    if (ev.key === "Escape") { ev.stopPropagation(); close(); return; }
    if (ev.key === "Tab") {
      const focusables = $$("button, input, select, textarea, a[href]", card)
        .filter(el => !el.disabled && el.offsetParent !== null);
      if (!focusables.length) return;
      const first = focusables[0], last = focusables[focusables.length - 1];
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
    if (onConfirm) { const ok = await onConfirm(); if (ok !== false) close(false); }
    else close(false);
  });
  const firstField = $("input, select, textarea", card);
  (firstField || $("#modal-confirm")).focus();
}

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

/* --------------------------------------------------------------- router */

let botsCache = [];

const routes = [
  [/^#\/chat(?:\/([\w-]+))?$/, m => renderChatStudio(m ? m[1] : null), "chat"],
  [/^#\/overview$/, renderOverview, "overview"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs(?:\?(.*))?$/, m => renderRuns(m ? m[1] : ""), "runs"],
  [/^#\/approvals$/, renderApprovals, "approvals"],
  [/^#\/connections$/, renderConnections, "connections"],
  [/^#\/bot\/([\w-]+)$/, m => renderBotDetail(decodeURIComponent(m[1])), "bots"],
  [/^#\/run\/([\w-]+)$/, m => renderRunDetail(m[1]), "runs"],
];

async function route() {
  const hash = location.hash || "#/chat";
  stopRunSubs();
  setTopContext("");
  closeWorkspace();
  for (const [re, handler, nav] of routes) {
    const m = hash.match(re);
    if (m) {
      $$(".ws-nav a").forEach(a => {
        const isActive = a.dataset.nav === nav;
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
  return `<div class="page-scroll"><div class="container"><div class="empty-state">
    ${icon("alert", "icon-lg")}
    <p><b>Could not load this view.</b></p>
    <p class="hint">${esc(err.message || err)}</p>
    <p><a href="#/chat">Back to the studio</a> · <button class="btn ghost small" onclick="route()">Try again</button></p>
  </div></div></div>`;
}

function setTopContext(html) { if (topContext) topContext.innerHTML = html; }

window.addEventListener("hashchange", route);

/* -------------------------------------------------- roster + attention */

async function refreshRoster() {
  try {
    botsCache = await api("/bots");
    renderRoster();
    renderAttention();
  } catch { /* offline is handled by the daemon pill */ }
}

function renderRoster() {
  const list = $("#roster-list");
  if (!list) return;
  const q = ($("#bot-search")?.value || "").trim().toLowerCase();
  const bots = q ? botsCache.filter(b => b.name.toLowerCase().includes(q) || (b.description || "").toLowerCase().includes(q)) : botsCache;
  if (!bots.length) {
    list.innerHTML = `<div class="roster-empty">${botsCache.length ? "No bot matches." : "No bots yet — create one."}</div>`;
    return;
  }
  const waitingBots = new Set(attentionBots);
  list.innerHTML = bots.map(b => {
    const state = botState(b);
    const pip = waitingBots.has(b.name) ? "waiting" : state === "running" ? "running" : state === "paused" ? "paused" : "";
    const word = waitingBots.has(b.name) ? "needs you" : state === "running" ? "working" : state === "paused" ? "paused" : "idle";
    return `
      <button class="roster-row" type="button" data-switch-bot="${esc(b.name)}"
        ${b.name === currentStudioBot && location.hash.startsWith("#/chat") ? 'aria-current="true"' : ""}
        title="${esc(b.name)} — ${word}">
        ${botAvatar(b.name, 30, pip)}
        <span class="roster-id">
          <span class="roster-name">${esc(b.name)}</span>
          <span class="roster-sub">${esc(truncate(b.model || "", 20))} · ${word}</span>
        </span>
      </button>`;
  }).join("");
  $$("#roster-list [data-switch-bot]").forEach(row =>
    row.addEventListener("click", () => { location.hash = `#/chat/${encodeURIComponent(row.dataset.switchBot)}`; }));
}

/* ---------------------------------------------------------------- shell */

let currentStudioBot = null;
let currentRunId = null;
let lastPrompt = "";
let pollTimer = null;

// Mobile overlay: labeled navigation sheet with focus ownership + restore.
const wsBtn = $("#nav-toggle"), wsEl = $("#workspace"), wsScrim = $("#ws-scrim"), wsClose = $("#ws-close");
function openWorkspace() {
  wsEl.classList.add("open");
  wsScrim.hidden = false;
  wsBtn.setAttribute("aria-expanded", "true");
  wsBtn.setAttribute("aria-label", "Close menu");
  wsClose.hidden = false;
  $("#workspace a")?.focus();
}
function closeWorkspace(restoreFocus = false) {
  if (!wsEl.classList.contains("open")) return;
  wsEl.classList.remove("open");
  wsScrim.hidden = true;
  wsBtn.setAttribute("aria-expanded", "false");
  wsBtn.setAttribute("aria-label", "Open menu");
  wsClose.hidden = true;
  if (restoreFocus) wsBtn.focus();
}
wsBtn?.addEventListener("click", () => wsEl.classList.contains("open") ? closeWorkspace() : openWorkspace());
wsClose?.addEventListener("click", () => closeWorkspace(true));
wsScrim?.addEventListener("click", () => closeWorkspace(true));
document.addEventListener("keydown", ev => {
  if (!wsEl.classList.contains("open")) return;
  if (ev.key === "Escape") { closeWorkspace(true); return; }
  if (ev.key !== "Tab") return;
  const focusable = $$("#workspace a, #workspace button:not([hidden]), #workspace input:not([disabled])")
    .filter(el => el.getClientRects().length);
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (ev.shiftKey && document.activeElement === first) {
    ev.preventDefault(); last.focus();
  } else if (!ev.shiftKey && document.activeElement === last) {
    ev.preventDefault(); first.focus();
  }
});
window.addEventListener("resize", () => { if (innerWidth > 900) closeWorkspace(); });
$("#bot-search")?.addEventListener("input", renderRoster);
$("#ws-close")?.addEventListener("keydown", ev => { if (ev.key === "Tab" && !ev.shiftKey) { ev.preventDefault(); $("#workspace a, #workspace button")?.focus(); } });

// Persistent Reduce-effects control (independent of the OS media query).
const effectsBtn = $("#effects-toggle");
function applyEffects(reduced) {
  document.documentElement.classList.toggle("reduce-effects", reduced);
  effectsBtn?.setAttribute("aria-pressed", String(reduced));
}
applyEffects(store$.get("hutch:reduce-effects", matchMedia("(prefers-reduced-motion: reduce)").matches));
effectsBtn?.addEventListener("click", () => {
  const next = !document.documentElement.classList.contains("reduce-effects");
  store$.set("hutch:reduce-effects", next);
  applyEffects(next);
  toast(next ? "Effects reduced" : "Effects restored");
});

/* --------------------------------------------- executor health (truthful) */

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
  pill.className = `pill daemon ${state}`;
  $("#daemon-label").textContent = label;
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

/* ------------------------------------------ app-wide attention + badge */

let lastPendingCount = null;
let attentionBots = [];
let attentionDismissedCount = null;

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
    if (n) {
      try {
        const pend = await api("/approvals");
        attentionBots = [...new Set(pend.map(a => a.bot_name))];
      } catch { attentionBots = []; }
    } else attentionBots = [];
    renderRoster();
    renderAttention();
    if (lastPendingCount !== null && n > lastPendingCount) {
      announce(`${n} approval${n === 1 ? "" : "s"} waiting for you.`);
    }
    lastPendingCount = n;
  } catch {}
}

// The bar keeps pending approval discoverable from any surface (terminal,
// artifact, phone sheet) without modal storms: one line, one action.
function renderAttention() {
  const bar = $("#attention-bar");
  if (!bar) return;
  const n = lastPendingCount || 0;
  const onApprovals = location.hash.startsWith("#/approvals");
  if (!n || onApprovals || attentionDismissedCount === n) { bar.hidden = true; return; }
  bar.hidden = false;
  bar.innerHTML = `${icon("alert")}
    <span><b>${n} approval${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you</b> — a bot is waiting to continue.</span>
    <a href="#/approvals">Review</a>
    <button class="icon-btn" id="attention-dismiss" aria-label="Dismiss reminder">${icon("x")}</button>`;
  $("#attention-dismiss")?.addEventListener("click", () => { attentionDismissedCount = n; bar.hidden = true; });
}

/* ------------------------------------------------------- CHAT STUDIO */

async function renderChatStudio(preferredBot = null) {
  botsCache = await api("/bots");
  renderRoster();
  if (!botsCache.length) {
    view.innerHTML = `<div class="page-scroll"><div class="container"><div class="empty-state">
      ${icon("bot", "icon-lg")}
      <p><b>No bots yet.</b></p>
      <p class="hint">Create your first bot and it will live here. Nothing leaves your machine unless a bot's model is hosted.</p>
      <button class="btn primary" id="btn-create-first">Create a bot</button>
    </div></div></div>`;
    $("#btn-create-first")?.addEventListener("click", promptNewBot);
    return;
  }

  let bot = botsCache.find(b => b.name === preferredBot) ||
            botsCache.find(b => b.name === currentStudioBot) ||
            botsCache[0];
  currentStudioBot = bot.name;
  const detail = await api(`/bots/${encodeURIComponent(bot.name)}`);
  const runs = detail.recent_runs || [];
  currentConversations = await api(`/v1/conversations?bot=${encodeURIComponent(bot.id)}&include_legacy=true&limit=100`);
  const rememberedConversation = storageGet(`hutch-conversation:${bot.id}`);
  let selectedConversation = currentConversations.find(c => c.id === rememberedConversation) || null;
  if (!selectedConversation) selectedConversation = currentConversations.find(c => !c.archived && !c.is_legacy) || null;
  if (!selectedConversation) {
    selectedConversation = await createStudioConversation(bot);
    currentConversations.unshift(selectedConversation);
  }
  currentConversationId = selectedConversation.id;
  storageSet(`hutch-conversation:${bot.id}`, currentConversationId);
  const activeRun = runs.find(r => r.conversation_id === currentConversationId && isActiveStatus(r.status, r.terminal)) || null;
  currentRunId = activeRun?.id || selectedConversation.latest_run_id || null;

  const state = botState(detail);
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(bot.name, 30, state === "running" ? "running" : state === "paused" ? "paused" : "")}
      <h1>${esc(bot.name)}</h1>
      <div class="ctx-meta">
        <span class="tag mono" title="model">${esc(truncate(bot.model, 26))}</span>
        ${bot.paused ? '<span class="tag warn">paused</span>' : ""}
        ${state === "running" ? '<span class="tag ok">working</span>' : ""}
      </div>
    </div>
    <div class="ctx-actions">
      <label class="visually-hidden" for="conversation-switcher">Conversation</label>
      <select class="conversation-select" id="conversation-switcher" aria-label="Conversation">
        ${currentConversations.map(c => `<option value="${esc(c.id)}" ${c.id === currentConversationId ? "selected" : ""}>${c.is_legacy ? "Imported · " : ""}${c.archived ? "Archived · " : ""}${esc(c.title || "New conversation")}</option>`).join("")}
      </select>
      <button class="btn ghost small" id="studio-new-conversation" type="button">${icon("plus")} New</button>
      ${!selectedConversation.is_legacy && (selectedConversation.archived || !activeRun) ? `<button class="btn ghost small" id="studio-archive-conversation" type="button">${selectedConversation.archived ? "Restore" : "Archive"}</button>` : ""}
      ${activeRun ? `<button class="btn danger small" id="studio-stop-run">${icon("stop")} Stop</button>` : ""}
      <a class="btn ghost small" href="#/bot/${esc(bot.name)}">${icon("sliders")} Settings</a>
      <button class="btn ghost small" id="inspector-open" aria-controls="inspector" aria-expanded="false">${icon("layers")} Context</button>
    </div>`);

  view.innerHTML = `
    <section class="studio">
      <div class="chat-scroll" id="chat-scroll">
        <div class="feed" id="chat-stream"></div>
      </div>
      <footer class="composer">
        <div class="composer-drawer" id="composer-drawer" hidden>
          <div class="quick-prompts" id="quick-prompts">
            <button class="quick-prompt" type="button" data-quick="Sort this week's downloads and move invoices into folders">${icon("folder")} Sort downloads</button>
            <button class="quick-prompt" type="button" data-quick="Research this week's AI news and write a short summary">${icon("fileText")} Research news</button>
            <button class="quick-prompt" type="button" data-quick="Inspect this repository for TODOs and report findings">${icon("search")} Repo sweep</button>
          </div>
          <div class="composer-stats">
            ${budgetMeterHtml(detail)}
            <span>max ${esc(detail.limits?.max_steps ?? "?")} steps · ${esc((detail.tools || []).join(", ") || "no tools")}</span>
            <label class="enter-setting"><input type="checkbox" id="enter-send-setting" checked> Enter sends</label>
          </div>
        </div>
        <form id="chat-form" autocomplete="off">
          <div class="composer-box" id="composer-box">
            <div class="composer-input-row composer-row">
              <button class="composer-util" type="button" id="composer-toggle" aria-label="Suggestions and budget" aria-expanded="false" aria-controls="composer-drawer">${icon("plus")}</button>
              <label class="visually-hidden" for="chat-prompt">Message ${esc(bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message ${esc(bot.name)}…" aria-describedby="chat-help"></textarea>
              <div class="composer-actions">
                <span class="model-switch-slot" id="model-switch-slot"></span>
                <button class="composer-send" id="chat-send" type="submit" aria-label="Send message">${icon("send")}</button>
              </div>
            </div>
          </div>
          <p class="visually-hidden" id="chat-help">Enter sends, Shift+Enter adds a newline. Your draft is kept for this bot if you navigate away.</p>
        </form>
      </footer>
    </section>
    <aside class="inspector" id="inspector" aria-label="${esc(bot.name)} — context">
      <div class="insp-head">
        <h2>Context</h2>
        <button class="icon-btn" id="inspector-close" aria-label="Close context panel">${icon("x")}</button>
      </div>
      <div class="insp-sec"><h3>This bot</h3>
        <div class="meta-row"><span>Runtime</span><span class="mono">${esc(detail.runtime || "builtin")}</span></div>
        <div class="meta-row"><span>Approval</span>${statusChipTag(detail.approval_mode)}</div>
        <div class="meta-row"><span>Risk tier</span><span class="mono">${esc(detail.risk_tier || "supervised")}</span></div>
        <div class="meta-row"><span>Timezone</span><span class="mono">${esc(detail.schedule ? detail.schedule.timezone : "UTC")}</span></div>
        <div class="meta-row"><span>Next run</span><span class="mono">${esc(detail.next_run_local || "—")}</span></div>
        <div class="meta-row"><span>Last success</span><span class="mono" title="${esc(detail.last_success || "")}">${timeAgo(detail.last_success)}</span></div>
        <div class="meta-row"><span>Workspace</span><span class="mono" title="${esc(detail.workdir || "")}">${detail.workdir ? esc(truncate(detail.workdir.split("/").pop(), 18)) : "auto"}</span></div>
      </div>
      <div class="insp-sec"><h3>Memory (${detail.memory.length})</h3>
        <div class="interactive-chip-list" id="memory-list">
          ${detail.memory.map(m => `
            <div class="memory-item">
              <div><span class="memory-key">${esc(m.key)}</span><span class="memory-val">${esc(truncate(m.value, 110))}</span></div>
              <button class="chip-del" title="Forget" aria-label="Forget memory ${esc(m.key)}" data-del-mem="${esc(m.key)}">${icon("x")}</button>
            </div>`).join("") || `<p class="empty-inline">Nothing remembered yet — the bot writes here when it uses its memory tool.</p>`}
        </div>
      </div>
      <div class="insp-sec"><h3>Standing permissions (${detail.sticky_allows.length})</h3>
        <div class="interactive-chip-list">
          ${detail.sticky_allows.map(s => `
            <div class="allow-item">
              <code>${esc(s)}</code>
              <button class="chip-del" title="Revoke" aria-label="Revoke permission ${esc(s)}" data-revoke-sticky="${esc(s)}">${icon("x")}</button>
            </div>`).join("") || `<p class="empty-inline">None — every risky command asks.</p>`}
        </div>
      </div>
    </aside>`;

  // wire memory / permissions
  $$("[data-del-mem]").forEach(btn => btn.addEventListener("click", async () => {
    const k = btn.dataset.delMem;
    if (!(await confirmDialog({
      title: "Forget memory",
      body: `Delete the memory <b>${esc(k)}</b>? The bot will no longer recall it.`,
      confirmText: "Forget", danger: true,
    }))) return;
    await api(`/bots/${encodeURIComponent(bot.name)}/memory/${encodeURIComponent(k)}`, { method: "DELETE" });
    toast(`Forgot "${k}"`);
    renderChatStudio(bot.name);
  }));
  $$("[data-revoke-sticky]").forEach(btn => btn.addEventListener("click", async () => {
    const k = btn.dataset.revokeSticky;
    await api(`/bots/${encodeURIComponent(bot.name)}/sticky-allows/${encodeURIComponent(k)}`, { method: "DELETE" });
    toast(`Revoked: ${k}`);
    renderChatStudio(bot.name);
  }));

  const conversationSwitcher = $("#conversation-switcher");
  conversationSwitcher?.addEventListener("change", ev => {
    storageSet(`hutch-conversation:${bot.id}`, ev.target.value);
    renderChatStudio(bot.name);
  });
  $("#studio-new-conversation")?.addEventListener("click", async ev => {
    const button = ev.currentTarget;
    button.disabled = true;
    try {
      const conversation = await createStudioConversation(bot);
      storageSet(`hutch-conversation:${bot.id}`, conversation.id);
      await renderChatStudio(bot.name);
    } catch (err) {
      toast(`Could not create a conversation: ${err.message}`, true);
      button.disabled = false;
    }
  });
  $("#studio-archive-conversation")?.addEventListener("click", async ev => {
    const button = ev.currentTarget;
    const archived = !selectedConversation.archived;
    button.disabled = true;
    try {
      await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}/archive`, {
        method: "POST",
        headers: { "Idempotency-Key": newIdempotencyKey() },
        body: { archived },
      });
      if (archived) storageRemove(`hutch-conversation:${bot.id}`);
      toast(archived ? "Conversation archived; its history is retained." : "Conversation restored.");
      await renderChatStudio(bot.name);
    } catch (err) {
      toast(`Could not update this conversation: ${err.message}`, true);
      button.disabled = false;
    }
  });

  // inspector open/close
  const inspector = $("#inspector"), inspBtn = $("#inspector-open");
  const setInspector = open => {
    inspector.classList.toggle("open", open);
    inspBtn.setAttribute("aria-expanded", String(open));
    if (open) $("#inspector-close").focus();
  };
  inspBtn.addEventListener("click", () => setInspector(!inspector.classList.contains("open")));
  $("#inspector-close").addEventListener("click", () => { setInspector(false); inspBtn.focus(); });
  // Keep the optional panel closed by default so it cannot cover the composer or model menu.

  // wire composer
  const form = $("#chat-form"), txt = $("#chat-prompt"), sendBtn = $("#chat-send");
  const box = $("#composer-box");
  const switcher = window.hutchModelSwitcher?.mount($("#model-switch-slot"), detail);
  if (selectedConversation.archived) {
    txt.disabled = true;
    txt.placeholder = "This conversation is archived. Start a new one to continue.";
    sendBtn.disabled = true;
  }

  txt.value = loadDraft(bot.name);
  const autogrow = () => { txt.style.height = "auto"; txt.style.height = Math.min(txt.scrollHeight, 220) + "px"; };
  autogrow();
  let draftTimer = null;
  txt.addEventListener("input", () => {
    autogrow();
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => saveDraft(bot.name, txt.value), 300);
  });
  const enterSends = () => $("#enter-send-setting").checked;
  $("#enter-send-setting").checked = store$.get(`hutch:enter-send:${bot.name}`, !matchMedia("(pointer: coarse)").matches);
  $("#enter-send-setting").addEventListener("change", ev => {
    store$.set(`hutch:enter-send:${bot.name}`, ev.target.checked);
  });

  let inflight = false;
  const submit = async () => {
    const text = txt.value.trim();
    if (!text || inflight) return;
    inflight = true;
    box.classList.remove("has-error");
    sendBtn.disabled = true;
    sendBtn.classList.add("sending");
    sendBtn.setAttribute("aria-label", "Sending…");
    const snapshot = txt.value;
    lastPrompt = text;
    try {
      const body = { prompt: text, rehearse: false, model: switcher?.selected() || null };
      const key = await messageIdempotencyKey(currentConversationId, body);
      const r = await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}/messages`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(currentConversationId, key);
      const titleOption = conversationSwitcher?.selectedOptions?.[0];
      if (titleOption && titleOption.textContent.trim().endsWith("New conversation")) {
        titleOption.textContent = text.slice(0, 72);
      }
      toast(ACTIVE.has(r.status) && activeRun ? "Sent — queued behind the current run." : "Sent.");
      currentRunId = r.id;
      // Clear only the submitted revision; anything typed since stays put.
      if (txt.value === snapshot) { txt.value = ""; saveDraft(bot.name, ""); autogrow(); }
      subscribeRun(r.id);
      renderChatFeed();
      refreshRoster();
    } catch (err) {
      box.classList.add("has-error");
      toast(`Not sent: ${err.message}. Your draft is kept.`, true);
    } finally {
      inflight = false;
      sendBtn.disabled = false;
      sendBtn.classList.remove("sending");
      sendBtn.setAttribute("aria-label", "Send message");
    }
  };
  form.addEventListener("submit", ev => { ev.preventDefault(); submit(); });
  txt.addEventListener("keydown", ev => {
    if (ev.key !== "Enter" || ev.shiftKey) return;
    if (ev.isComposing || ev.keyCode === 229) return;   // never submit mid-IME-composition
    if (enterSends()) { ev.preventDefault(); submit(); }
  });
  $("#quick-prompts").addEventListener("click", ev => {
    const chip = ev.target.closest("[data-quick]");
    if (!chip) return;
    txt.value = chip.dataset.quick;
    saveDraft(bot.name, txt.value);
    autogrow(); txt.focus();
  });
  const composerToggle = $("#composer-toggle"), drawer = $("#composer-drawer");
  composerToggle.addEventListener("click", () => {
    const open = drawer.hasAttribute("hidden");
    drawer.toggleAttribute("hidden", !open);
    composerToggle.setAttribute("aria-expanded", String(open));
  });
  $("#studio-stop-run")?.addEventListener("click", async () => {
    if (!currentRunId) return;
    await api(`/runs/${currentRunId}/stop`, { method: "POST" });
    toast("Stop requested — already-finished steps are not undone.");
  });

  feedMode = "studio";
  if (activeRun) subscribeRun(activeRun.id);   // stream brings events; first paint below
  await renderChatFeed();
}

function statusChipTag(mode) {
  const map = { ask: ["ask", ""], auto: ["auto", "ok"], deny_all: ["deny all", "danger"] };
  const [word, cls] = map[mode] || [mode, ""];
  return `<span class="chip ${cls}">${esc(word)}</span>`;
}

function budgetMeterHtml(bot) {
  const cap = bot.limits?.daily_token_cap || 0;
  const used = bot.tokens_today || 0;
  const pct = cap ? Math.round((used / cap) * 100) : 0;
  const state = pct >= 100 ? "over" : pct >= 70 ? "warn" : "";
  return `
    <span class="budget-meter ${state}" title="Daily token budget: ${used} of ${cap}">
      <span class="meter-track"><span class="meter-fill" style="width:${Math.min(pct, 100)}%"></span></span>
      <span>${fmtTokens(used)} / ${fmtTokens(cap)}</span>
    </span>`;
}

/* -------------------------------------------------- live feed (SSE + render) */

let runStream = null, statusTimer = null, renderTimer = null, subRunId = null;
let feedMode = "studio";   // "studio" (bot transcript) or "run" (single-run detail)

function stopRunSubs() {
  subRunId = null;
  if (runStream) { runStream.close(); runStream = null; }
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
  if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
}

function subscribeRun(runId) {
  if (subRunId === runId && (runStream || statusTimer)) return;   // already live on this run
  stopRunSubs();
  subRunId = runId;
  try {
    runStream = new EventSource(`/api/runs/${runId}/stream`);
    // The server coalesces bursts; one message may carry up to a batch of events.
    runStream.onmessage = () => scheduleFeedRender();
    runStream.onerror = () => {
      // gap-free resume is Last-Event-ID based (server replays from SQLite);
      // a terminal run simply ends the stream — re-render to catch that.
      scheduleFeedRender();
    };
  } catch { /* no EventSource: polling below still works */ }
  statusTimer = setInterval(scheduleFeedRender, 4000);   // belt-and-braces refresh
}

function scheduleFeedRender() {
  if (renderTimer) return;
  renderTimer = setTimeout(() => {
    renderTimer = null;
    if (feedMode === "run" && currentRunId) renderRunDetail(currentRunId);
    else renderChatFeed();
  }, 250);
}

// Conversation history for this bot = its recent runs. Terminal runs are cached;
// the active one re-renders as events arrive.
const terminalRunCache = new Map();

async function renderChatFeed() {
  if (feedMode !== "studio") return;
  const stream = $("#chat-stream");
  const scroll = $("#chat-scroll");
  if (!stream || !scroll || !currentStudioBot) return;

  let messages;
  try {
    if (!currentConversationId) return;
    const summary = await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}?after=0&limit=1`);
    const lastSeq = summary.last_seq || 0;
    const after = Math.max(0, lastSeq - 100);
    const page = await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}?after=${after}&limit=100`);
    messages = page.messages || [];
  } catch { return; }
  const runIds = [...new Set(messages.filter(m => m.role === "user" && m.run_id).map(m => m.run_id))];
  if (!runIds.length) {
    stream.innerHTML = welcomeHtml();
    wireWelcome();
    return;
  }

  const wasNearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 90;

  const shown = runIds.slice(-6);
  const parts = [];
  for (const runId of shown) {
    let html;
    if (runId === currentRunId) html = await runBlockHtml(runId);
    else if (terminalRunCache.has(runId)) html = terminalRunCache.get(runId);
    else { html = await runBlockHtml(runId); terminalRunCache.set(runId, html); }
    parts.push(html);
  }
  stream.innerHTML = parts.join("");

  // The thinking bubble lives in a stable slot AFTER the feed: full re-renders
  // replace the transcript every event batch, and re-inserting the dots would
  // restart their bounce each time. Here the animation runs continuously.
  let slot = $("#typing-slot");
  if (!slot) {
    slot = document.createElement("div");
    slot.id = "typing-slot"; slot.className = "typing-slot"; slot.setAttribute("aria-hidden", "true");
    scroll.insertBefore(slot, stream.nextSibling);
  }
  const active = currentRunId ? await api(`/runs/${encodeURIComponent(currentRunId)}`).catch(() => null) : null;
  const thinking = !!active && isActiveStatus(active.status, active.terminal) &&
    !["waiting_approval", "waiting_human", "waiting_resources", "cancelling"].includes(active.status);
  if (thinking && !slot.innerHTML.trim()) slot.innerHTML = typingHtml();
  if (!thinking) slot.innerHTML = "";
  if (!active || !isActiveStatus(active.status, active.terminal)) stopRunSubs();
  if (active) announceRunLifecycle([active]);

  wireApprovals();
  wireFeedInteractions();
  updateTtls();
}

// Lifecycle transitions are announced once per change, not per token or poll.
function announceRunLifecycle(runs) {
  for (const r of runs) {
    const prev = seenRunStatus.get(r.id);
    if (prev === r.status) continue;
    if (r.status === "waiting_approval" && prev !== undefined) {
      announce(`${r.bot_name || "Your bot"} needs your approval before continuing.`);
    } else if (prev !== undefined && ACTIVE.has(prev) && !ACTIVE.has(r.status)) {
      announce(`Run ${r.status_label || statusInfo[r.status]?.label || "status unavailable"}.`);
    }
    seenRunStatus.set(r.id, r.status);
  }
}

const seenRunStatus = new Map();

function welcomeHtml() {
  const b = botsCache.find(x => x.name === currentStudioBot);
  if (!b) return "";
  return `
    <div class="welcome">
      <div class="welcome-hero">
        ${botAvatar(b.name, 56)}
        <h2>${esc(b.name)}</h2>
        <p class="hint">${esc(b.description || "No description yet.")}</p>
      </div>
      <div class="welcome-steps">
        <p><b>Nothing has run yet.</b> Give this bot a task and its transcript appears here — every tool call, every approval, the full accounting.</p>
        <ul class="welcome-list">
          <li>${icon("zap")} Model <span class="mono">${esc(b.model)}</span></li>
          <li>${icon("shield")} ${b.approval_mode === "auto" ? "Runs without asking (denylist still enforced)" : "Asks before non-read-only actions"}</li>
          <li>${icon("brain")} ${b.memory_count ? `${b.memory_count} memories` : "No memories yet"}</li>
        </ul>
      </div>
    </div>`;
}

function wireWelcome() { /* the composer is the call to action; nothing to wire yet */ }

/* One run = one conversation thread: the prompt bubble, the visible work,
   the answer. Tool activity is a quiet collapsed strip — approvals are never
   hidden inside it. */
async function runBlockHtml(runId) {
  const run = await api(`/runs/${runId}`);
  const events = run.events || [];
  const resolvedMap = new Map();
  for (const e of events) {
    if (e.type === "approval_resolved") resolvedMap.set((e.data || {}).approval_id, e.data || {});
  }
  const items = groupToolItems(pairToolEvents(events));
  const dur = fmtDur((run.finished_at ? new Date(run.finished_at) : Date.now()) - new Date(run.created_at));
  const running = ACTIVE.has(run.status);
  const anim = seenThreads.has(runId) ? "" : " enter";
  seenThreads.add(runId);

  const steps = [], cards = [];
  items.forEach(item => {
    const html = renderFeedItem(item, runId, resolvedMap);
    (item.kind === "event" && (item.e.type === "approval_request" || item.e.type === "human_needed") ? cards : steps).push(html);
  });

  const message = events.filter(e => e.type === "message").pop();
  const stepCount = events.filter(e => e.type === "tool_call").length;

  return `
    <article class="thread${anim}" data-run-id="${esc(runId)}">
      <div class="msg you">
        <div class="bubble">${esc(run.prompt)}</div>
        <span class="stamp">${timeAgo(run.created_at)}${run.origin === "schedule" ? " · scheduled" : ""}</span>
      </div>
      <div class="msg agent">
        <div class="mhead">
          ${botAvatar(run.bot_name || currentStudioBot, 26, running ? "running" : "")}
          <b>${esc(run.bot_name || currentStudioBot)}</b>
          ${statusChip(run.status, run.status_label)}
          <a class="mrun mono" href="#/run/${esc(runId)}" title="${esc(runId)} · ${esc(run.origin || "manual")} · ${dur}">#${esc(runId.slice(4, 12))}</a>
        </div>
        ${cards.join("")}
        ${stepCount || running ? `
        <details class="tool-stream" ${running || stepCount < 4 ? "open" : ""}>
          <summary>${icon("gear")}${running ? "Working" : `${stepCount} step${stepCount === 1 ? "" : "s"}`}${stepCount && !running ? ` · ${dur}` : ""} ${icon("caret", "tool-caret")}</summary>
          ${steps.join("")}
        </details>` : ""}
        ${message && message.data?.content ? `<div class="answer">${esc(message.data.content)}</div>` : ""}
        ${run.error ? `<div class="run-error">${icon("alert")}<span><b>Failed:</b> ${esc(run.error)}</span></div>` : ""}
      </div>
    </article>`;
}

const seenThreads = new Set();

/* Merge tool_call + tool_result pairs; runs of 4+ collapse under one group row. */
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

// Working indicator: deliberately aria-hidden — the status chip and the bounded
// announcer carry state; the dots are decorative feedback only.
function typingHtml() {
  return `<div class="typing" aria-hidden="true">
    <span class="typing-dots"><span></span><span></span><span></span></span>
    <span class="typing-label">Working…</span>
  </div>`;
}

function renderFeedItem(item, runId, resolvedMap) {
  if (item.kind === "tool") return toolLineHtml(item, item.call?.e ?? item.result.e, runId);
  if (item.kind === "group") return toolGroupHtml(item, runId);
  return renderChatEvent(item.e, resolvedMap);
}

function toolLineHtml(item, anchorEvent, runId) {
  const idx = anchorEvent.seq ?? anchorEvent.ts;
  const call = item.call, res = item.result;
  const tool = (res || call).d.tool;
  const running = !res;
  const ok = res ? res.d.ok !== false : true;
  const cls = running ? "running" : ok ? "success" : "error";
  const argsStr = JSON.stringify(call?.d.args ?? {});
  const summary = res ? summarizeOutput(res.d.output) || argsStr : argsStr;
  const t = (res || call).e.ts?.slice(11, 19) || "";
  const open = expandedStore(runId).has(String(idx));
  const verdict = running
    ? '<span class="spin-line" role="status" aria-label="running"></span>'
    : icon(ok ? "check" : "x");

  return `
    <div class="tool-line ${cls}" data-tool-line="${esc(String(idx))}">
      <button class="tool-line-head" type="button" aria-expanded="${open}" aria-controls="tlb-${esc(String(idx))}" data-tool-toggle="${esc(String(idx))}">
        <span class="tool-grid">
          <span class="tool-verdict">${verdict}</span>
          <span class="tool-name">${esc(tool)}</span>
          <span class="tool-args">${icon("caret", "tool-arrow")}${esc(truncate(summary, 90))}</span>
          <span class="tool-time">${t}</span>
          <span class="tool-caret">${icon("caret")}</span>
        </span>
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
    </div>`;
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
    </div>`;
}

function wireFeedInteractions() {
  const stream = $("#chat-stream");
  if (!stream || stream.dataset.wired === "1") return;
  stream.dataset.wired = "1";
  const runId = currentRunId;
  stream.addEventListener("click", ev => {
    const more = ev.target.closest("[data-show-more]");
    if (more) {
      const full = more.parentElement.querySelector("[data-out-full]");
      const clip = more.parentElement.querySelector("[data-out-clip]");
      const show = full.hidden;
      full.hidden = !show; clip.hidden = show;
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
      const blockRun = group.closest("[data-run-id]")?.dataset.runId || currentRunId;
      try { localStorage.setItem(`hutch-group:${blockRun}`, open ? "1" : "0"); } catch {}
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
      const blockRun = line.closest("[data-run-id]")?.dataset.runId || currentRunId;
      const ids = [...stream.querySelectorAll(`[data-run-id="${blockRun}"] [data-tool-toggle][aria-expanded='true']`)].map(b => b.dataset.toolToggle);
      try { localStorage.setItem(`hutch-expanded:${blockRun}`, JSON.stringify(ids)); } catch {}
    }
  });
}

/* Live fail-closed countdowns on approvals; at zero the gate flips to resolved. */
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

/* --------------------------------------------------------- approvals card */

// One approval, rendered identically in the feed and the queue: plain-language
// action first, exact detail behind a disclosure, honest expiry/scope notes.
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
          <span class="chip warn">${icon("shield")} Approval required</span>
          ${botName ? `<b class="approval-bot">${esc(botName)}</b>` : ""}
          ${tool ? `<span class="tag">${esc(tool)}</span>` : ""}
          <span class="tag ${risk === "high" ? "danger" : risk === "low" ? "" : "warn"}">${esc(risk)} risk</span>
          ${outward ? `<span class="tag danger" title="Leaves this machine; always-allow is not offered">leaves machine</span>` : ""}
        </div>
        <span class="ttl-countdown">${icon("hourglass")}<span data-ttl-text>${expired ? "expired — denied" : ""}</span></span>
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
        ${detail ? `<span class="review-label">Raw request</span><pre class="approval-detail">${esc(detail)}</pre>` : ""}
      </details>
      ${canAlways
        ? `<p class="hint approval-scope">Always-allow remembers <code class="mono">${esc(stickyKey)}</code> for this bot. Revoke it any time in the bot's standing permissions.</p>`
        : outward
          ? `<p class="hint approval-scope">This action leaves the machine, so always-allow is not offered — you decide each time.</p>`
          : ""}
      <div class="approval-buttons" data-approval="${esc(id)}">
        <button class="btn primary small" data-approve="1">Allow once</button>
        ${canAlways ? `<button class="btn ghost small" data-approve="always">Always allow for this bot</button>` : ""}
        <button class="btn ghost small" data-approve="0">Deny</button>
        ${runId ? `<a class="btn ghost small" href="#/run/${esc(runId)}">Open run</a>` : ""}
      </div>
    </div>`;
}

// Server-authoritative resolution: names who decided and when, so two devices
// racing to answer agree rather than diverge.
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
    scheduleFeedRender();
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

function renderChatEvent(e, resolvedMap) {
  const t = e.ts ? e.ts.slice(11, 19) : "";
  const d = e.data || {};
  switch (e.type) {
    case "approval_request": {
      const id = d.approval_id || d.id;
      const done = resolvedMap?.get(id);
      if (done) {   // the transcript of a finished run shows the real outcome, not a stale ask
        const outcome = done.result === "approved" ? "approved"
          : String(done.result).startsWith("expired") ? "expired" : "denied";
        return approvalResolvedHtml({ ...d, approval_id: id, decided_by: done.by || "" }, outcome);
      }
      const deadline = d.expires_at ? new Date(d.expires_at).getTime()
        : (e.ts ? new Date(e.ts).getTime() + 10 * 60 * 1000 : 0);
      return approvalCardHtml({ ...d, deadline, run_id: e.run_id || currentRunId },
        { botName: currentStudioBot || "" });
    }
    case "human_needed":
      return `<div class="run-cause"><b>${icon("alert")} Needs a person:</b> ${esc(d.reason || d.note || "A login, CAPTCHA, or 2FA step is waiting.")} ${
        d.handoff ? `<br><span class="hint">${esc(d.handoff)}</span>` : ""}</div>`;
    case "log":
      return `<div class="tool-line"><div class="tool-grid tool-log"><span class="tool-verdict">·</span><span class="tool-args">${esc(truncate(d.note || d.message || "", 140))}</span><span class="tool-time">${t}</span><span></span><span></span></div></div>`;
    default:
      return "";   // message / tool_call / tool_result / approval_resolved are consumed elsewhere
  }
}

function wireApprovals() {
  $$("[data-approve]").forEach(btn => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", () => {
      const wrap = btn.closest("[data-approval]");
      if (!wrap) return;
      resolveApproval(wrap.dataset.approval, btn.dataset.approve, btn.closest("[data-approval-card]"));
    });
  });
}

/* -------------------------------------------------------------- overview */

async function renderOverview() {
  const o = await api("/overview");
  const s = o.stats || {};
  const fmt = (n) => Number(n || 0).toLocaleString();
  setTopContext(`<div class="ctx-id"><h1>Overview</h1></div>
    <div class="ctx-actions"><a class="btn ghost small" href="#/bots">All bots ${icon("arrow")}</a></div>`);
  const row = (r) => `
    <a class="ov-row" href="#/run/${esc(r.id)}">
      <span class="ov-row-main"><b>${esc(r.bot_name)}</b>${statusChip(r.status)}</span>
      <span class="ov-row-prompt">${esc(truncate(r.prompt || "", 90))}</span>
      <span class="ov-row-meta mono">${r.steps} steps · ${fmt(r.tokens)} tok · ${timeAgo(r.created_at)}</span>
    </a>`;
  const waitBox = (w) => w && w.cause ? `<div class="ov-wait banner ${esc(w.kind || "wait")}"><b>Why:</b> ${esc(w.cause)}<br><b>What to do:</b> ${esc(w.fix)}</div>` : "";
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <div class="ov-stats">
        <div class="kpi"><span class="kpi-label">Bots</span><span class="kpi-val">${fmt(s.bots)}</span></div>
        <div class="kpi"><span class="kpi-label">Runs today</span><span class="kpi-val">${fmt(s.runs_today)}</span></div>
        <div class="kpi"><span class="kpi-label">Tokens today</span><span class="kpi-val">${fmt(s.tokens_today)}</span></div>
        <div class="kpi"><span class="kpi-label">Spend today</span><span class="kpi-val">$${Number(s.spend_today || 0).toFixed(2)}</span></div>
      </div>
      <div class="ov-grid">
        <section class="ov-col loud">
          <h2 class="ov-h">${icon("inbox")} Needs you <span class="count">${o.needs_count}</span></h2>
          ${!o.needs_count ? `<div class="empty-state">${icon("check", "icon-lg")}<p>Nothing needs you.</p></div>` : ""}
          ${(o.approvals || []).map(a => `
            <a class="ov-approval" href="#/approvals">
              <span class="ov-approval-head"><b>${esc(a.bot_name)}</b> <span class="tag">${esc(a.tool)}</span> <span class="tag ${a.risk === "high" ? "danger" : "warn"}">${esc(a.risk)} risk</span></span>
              <span class="ov-approval-action">${esc(a.action)}</span>
            </a>`).join("")}
          ${(o.humans || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
          ${(o.failures || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
        </section>
        <section class="ov-col">
          <h2 class="ov-h">${icon("play")} Running now <span class="count">${(o.running || []).length}</span></h2>
          ${(o.running || []).length ? (o.running || []).map(row).join("") : `<div class="empty-state"><p>Nothing is running.</p></div>`}
        </section>
        <section class="ov-col">
          <h2 class="ov-h">${icon("clock")} Stale <span class="count">${(o.stale || []).length}</span></h2>
          ${(o.stale || []).length ? (o.stale || []).map(x => `
            <a class="ov-row" href="#/bot/${esc(x.bot_name)}">
              <span class="ov-row-main"><b>${esc(x.bot_name)}</b><span class="status stale">stale</span></span>
              <span class="ov-row-meta">last success ${timeAgo(x.last_success)}</span>
            </a>`).join("") : `<div class="empty-state">${icon("check", "icon-lg")}<p>Every scheduled bot is up to date.</p></div>`}
        </section>
      </div>
    </div></div>`;
}

/* -------------------------------------------------------------- bots list */

async function renderBots() {
  const bots = botsCache.length ? botsCache : await api("/bots");
  botsCache = bots;
  renderRoster();
  setTopContext(`<div class="ctx-id"><h1>Bots</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-new-bot-top">${icon("plus")} New bot</button></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      ${bots.length ? `
      <div class="bot-grid">
        ${bots.map(b => `
          <article class="bot-card">
            <div class="bot-head">
              ${botAvatar(b.name, 32, botState(b) === "running" ? "running" : b.paused ? "paused" : "")}
              <span class="bot-name">${esc(b.name)}</span>
              ${b.paused ? `<span class="status pending">paused</span>` : `<span class="status succeeded">on</span>`}
            </div>
            <p class="bot-desc">${esc(b.description || "No description.")}</p>
            <div class="bot-chips">
              <span class="tag mono">${esc(truncate(b.model || "", 24))}</span>
              ${b.schedule ? `<span class="tag mono" title="${esc(b.schedule.timezone || "UTC")}">${esc(b.schedule.cron)}</span>` : `<span class="tag">on demand</span>`}
              <span class="tag">ask: ${esc(b.approval_mode)}</span>
            </div>
            <div class="bot-facts">
              <div>next run <b>${esc(b.next_run_local || "—")}</b></div>
              <div>last success <b title="${esc(b.last_success || "")}">${timeAgo(b.last_success)}</b></div>
              <div>tokens today <b>${fmtTokens(b.tokens_today)}</b></div>
              <div>memories <b>${b.memory_count}</b></div>
            </div>
            <div class="card-actions">
              <a class="btn primary small" href="#/chat/${esc(b.name)}">${icon("chat")} Open</a>
              <button class="btn ghost small" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                ${b.paused ? "Resume" : "Pause"}
              </button>
              <a class="btn ghost small" href="#/bot/${esc(b.name)}">${icon("sliders")} Settings</a>
            </div>
          </article>
        `).join("")}
      </div>
      ` : `
      <div class="empty-state">
        ${icon("bot", "icon-lg")}
        <p><b>No bots yet.</b></p>
        <p class="hint">A bot is a named agent with its own model, tools, workspace, schedule, and memory. Start from a template.</p>
        <button class="btn primary" id="btn-create-first-bot">Create your first bot</button>
      </div>`}
    </div></div>`;
  $("#btn-create-first-bot")?.addEventListener("click", promptNewBot);
  $("#btn-new-bot-top")?.addEventListener("click", promptNewBot);
  wireCommon();
}

/* -------------------------------------------------------------- runs list */

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
  setTopContext(`<div class="ctx-id"><h1>Runs</h1></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <div class="runs-filter-bar">
        <label class="visually-hidden" for="run-search">Filter runs</label>
        <input type="search" id="run-search" placeholder="Filter by bot or prompt…" value="${esc(runsState.q)}">
        <div class="runs-filter-pills" role="group" aria-label="Filter by status">
          ${["all", "succeeded", "failed", "waiting_approval"].map(f => `
            <button class="${runsState.status === f ? "active" : ""}" data-filter="${f}" aria-pressed="${runsState.status === f}">
              ${f === "all" ? "All" : f === "waiting_approval" ? "Waiting" : f[0].toUpperCase() + f.slice(1)}
            </button>`).join("")}
        </div>
        <span class="hint" id="runs-count"></span>
      </div>
      <div class="table-wrap" id="runs-table-wrap"></div>
    </div></div>`;

  const syncHash = () => {
    const p = new URLSearchParams();
    if (runsState.status !== "all") p.set("status", runsState.status);
    if (runsState.q) p.set("q", runsState.q);
    history.replaceState(null, "", `#/runs${p.toString() ? `?${p}` : ""}`);
  };

  const renderRows = () => {
    const q = runsState.q.trim().toLowerCase();
    const filtered = runsState.all.filter(r => {
      if (runsState.status !== "all" && r.status !== runsState.status) return false;
      if (q && !`${r.bot_name} ${r.prompt}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const wrap = $("#runs-table-wrap");
    if (!wrap) return;
    if (!filtered.length) {
      wrap.innerHTML = runsState.all.length ? `
        <div class="empty-state">
          ${icon("search", "icon-lg")}
          <p>No runs match this filter.</p>
          <button class="btn ghost small" id="runs-clear">Clear filters</button>
        </div>` : `
        <div class="empty-state">
          ${icon("zap", "icon-lg")}
          <p><b>No runs yet.</b></p>
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
        syncHash(); renderRows();
      });
    } else {
      const rows = filtered.slice(0, runsState.shown);
      const nowMs = Date.now();
      const durMs = (r) => {
        const a = r.created_at ? new Date(r.created_at).getTime() : nowMs;
        const b = r.finished_at ? new Date(r.finished_at).getTime() : nowMs;
        return Math.max(0, b - a);
      };
      const maxDur = Math.max(1, ...rows.map(durMs));
      wrap.innerHTML = `
        <table>
          <caption class="visually-hidden">Runs, newest first</caption>
          <thead>
            <tr>
              <th>Run</th><th>Bot</th><th>Status</th><th>Prompt</th>
              <th>Duration</th><th class="num">Steps</th><th class="num">Tokens</th><th>When</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(r => {
              const d = durMs(r);
              const cls = r.status === "failed" ? "bad" : ACTIVE.has(r.status) && r.status !== "pending" ? "warn" : "";
              return `
              <tr class="clickable" tabindex="0" role="link" aria-label="Open run ${esc(r.id)}" data-goto="#/run/${esc(r.id)}" title="${esc(r.created_at || "")}">
                <td class="mono">${esc(r.id.slice(0, 12))}…</td>
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
          <button class="btn ghost small runs-more" id="runs-more">Show ${Math.min(RUNS_PAGE_SIZE, filtered.length - runsState.shown)} more of ${filtered.length}</button>` : ""}`;
      $("#runs-more")?.addEventListener("click", () => { runsState.shown += RUNS_PAGE_SIZE; renderRows(); });
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
      syncHash(); renderRows();
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
      syncHash(); renderRows();
    });
  });
  renderRows();
}

/* -------------------------------------------------------------- approvals */

let approvalsTimer = null;

async function renderApprovals() {
  clearInterval(approvalsTimer);
  setTopContext(`<div class="ctx-id"><h1>Approvals</h1></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="page-subtitle">A bot wants to perform an irreversible action. Unanswered requests expire as <b>denied</b>.</p>
      <div id="approvals-pending"></div>
      <h2 class="section-sub">Recently decided</h2>
      <div id="approvals-resolved"></div>
    </div></div>`;
  await refreshApprovals();
  // Queue stays honest across devices: cards answered elsewhere (or expired)
  // update here without a manual reload.
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

/* -------------------------------------------------------- bot settings */

async function renderBotDetail(name) {
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(b.name, 30)}
      <h1>${esc(b.name)}</h1>
    </div>
    <div class="ctx-actions">
      <a class="btn ghost small" href="#/chat/${esc(b.name)}">${icon("chat")} Open Studio</a>
      <button class="btn danger small" id="btn-delete-bot">Delete bot</button>
    </div>`);

  const sched = b.schedule || {};
  const limits = b.limits || {};
  const rules = b.command_rules || [];
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="crumb"><a href="#/bots">Bots</a> / ${esc(b.name)}</p>
      <div class="detail-grid">
        <div>
          <form class="panel form-grid" id="form-identity">
            <div class="panel-title">Instructions</div>
            <label class="field">Description
              <input type="text" name="description" value="${esc(b.description || "")}" placeholder="What this bot does">
            </label>
            <label class="field">System instructions
              <textarea name="instructions" rows="7">${esc(b.instructions || "")}</textarea>
            </label>
            <div class="btn-row"><button class="btn primary small" type="submit">Save</button></div>
          </form>

          <form class="panel form-grid" id="form-model">
            <div class="panel-title">Model &amp; connection</div>
            <div class="form-grid row2">
              <label class="field">Model
                <input type="text" name="model" value="${esc(b.model || "")}">
                <span class="hint">hosted/&lt;model&gt; · ollama/&lt;tag&gt; · &lt;connection&gt;/&lt;model&gt;</span>
              </label>
              <label class="field">Runtime
                <input type="text" disabled value="${esc(b.runtime || "builtin")}">
              </label>
            </div>
            <p class="hint">Inference ${b.model && /ollama|llama|mock/.test(b.model) ? "runs on <b>this machine</b>." : "may <b>leave this machine</b> — the model string names where."} Tools always run here.</p>
            <div class="btn-row"><button class="btn primary small" type="submit">Save model</button></div>
          </form>

          <form class="panel form-grid" id="form-schedule">
            <div class="panel-title">Schedule</div>
            <div class="form-grid row2">
              <label class="field">Cron (blank = on demand)
                <input type="text" name="cron" value="${esc(sched.cron || "")}" placeholder="0 9 * * 1">
              </label>
              <label class="field">Timezone
                <input type="text" name="timezone" value="${esc(sched.timezone || "UTC")}">
              </label>
            </div>
            <div class="meta-row"><span>Next run</span><span class="mono">${esc(b.next_run_local || "—")}</span></div>
            <div class="meta-row"><span>Missed windows</span><span class="mono">${esc(sched.catch_up || "coalesce")} · changed with <code class="mono">hutch bot schedule</code></span></div>
            <div class="btn-row">
              <button class="btn primary small" type="submit">Save schedule</button>
              <button class="btn ghost small" type="button" id="btn-clear-schedule">Make it on-demand</button>
            </div>
          </form>

          <form class="panel form-grid" id="form-risk">
            <div class="panel-title">Risk policy</div>
            <div class="form-grid row2">
              <label class="field">Approval mode
                <select name="approval_mode">
                  ${["ask", "auto"].map(m => `<option value="${m}" ${b.approval_mode === m ? "selected" : ""}>${m}</option>`).join("")}
                </select>
              </label>
              <label class="field">Risk tier
                <select name="risk_tier">
                  ${["readonly", "supervised", "trusted"].map(t => `<option value="${t}" ${(b.risk_tier || "supervised") === t ? "selected" : ""}>${t}</option>`).join("")}
                </select>
              </label>
            </div>
            <label class="field">Working folder
              <input type="text" name="workdir" value="${esc(b.workdir || "")}" placeholder="absolute path or blank">
              <span class="hint">File tools use this folder. Shell isolation depends on the Linux sandbox setting; blank uses Hutch's per-bot folder.</span>
            </label>
            <div class="btn-row">
              <button class="btn primary small" type="submit">Save policy</button>
              <button class="btn ${b.paused ? "primary" : "ghost"} small" type="button" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                ${b.paused ? "Resume bot" : "Pause bot"}
              </button>
            </div>
          </form>

          <div class="panel">
            <div class="panel-title">Command rules</div>
            <div class="settings-list" id="rules-list">
              ${rules.map((r, i) => `
                <div class="meta-row"><span class="mono">${esc(r.match)}</span>${statusChipTag(r.verdict)}</div>`).join("")
                || `<p class="empty-inline">No rules — the risk tier decides everything.</p>`}
            </div>
            <form class="form-grid row2" id="form-rule" style="margin-top:12px;">
              <label class="field">Match (glob)
                <input type="text" name="match" placeholder="git push*" required>
              </label>
              <label class="field">Verdict
                <select name="verdict"><option>allow</option><option selected>ask</option><option>deny</option></select>
              </label>
              <div class="btn-row"><button class="btn primary small">Add rule</button></div>
            </form>
          </div>

          <div class="panel">
            <div class="panel-title">Estimate this task</div>
            <label class="field">Prompt sample
              <input type="text" id="estimate-prompt" placeholder="e.g. sort this week's downloads">
            </label>
            <div class="btn-row" style="margin-top:8px;"><button class="btn ghost small" id="btn-estimate">Estimate tokens and cost ${icon("chart")}</button></div>
            <div id="estimate-out" class="mono hint" style="margin-top:8px;"></div>
          </div>
        </div>

        <div>
          <div class="panel">
            <div class="panel-title">Execution and usage limits</div>
            <form class="form-grid" id="form-limits">
              <div class="form-grid row2">
                <label class="field">Maximum steps
                  <input type="number" name="max_steps" min="1" step="1" required value="${esc(limits.max_steps ?? 24)}">
                </label>
                <label class="field">Time limit (seconds)
                  <input type="number" name="timeout_seconds" min="1" step="1" required value="${esc(limits.timeout_seconds ?? 900)}">
                </label>
                <label class="field">Daily token estimate
                  <input type="number" name="daily_token_cap" min="0" step="1" required value="${esc(limits.daily_token_cap ?? 200000)}">
                </label>
                <label class="field">Tokens per model turn
                  <input type="number" name="max_turn_tokens" min="0" step="1" required value="${esc(limits.max_turn_tokens ?? 0)}">
                </label>
                <label class="field">Estimated cost per run (USD)
                  <input type="number" name="max_cost_usd" min="0" step="0.01" required value="${esc(limits.max_cost_usd ?? 0)}">
                </label>
                <label class="field">Estimated daily cost (USD)
                  <input type="number" name="daily_cost_cap_usd" min="0" step="0.01" required value="${esc(limits.daily_cost_cap_usd ?? 0)}">
                </label>
              </div>
              <p class="hint">Token and currency controls use estimates. Provider billing can differ; use provider-side controls for a guaranteed external spending limit. 0 means no estimate limit.</p>
              <div class="btn-row"><button class="btn primary small" type="submit">Save limits</button></div>
            </form>
            <div class="meta-row" style="margin-top:12px;"><span>Tokens estimated today</span><span class="mono">${fmtTokens(b.tokens_today)}</span></div>
          </div>

          <div class="panel">
            <div class="panel-title">Memory (${b.memory.length})</div>
            ${b.memory.map(m => `
              <div class="memory-item">
                <div><span class="memory-key">${esc(m.key)}</span><span class="memory-val">${esc(m.value)}</span></div>
                <button class="chip-del" aria-label="Forget memory ${esc(m.key)}" data-del-mem="${esc(m.key)}">${icon("x")}</button>
              </div>`).join("") || `<p class="empty-inline">Nothing remembered yet.</p>`}
          </div>

          <div class="panel">
            <div class="panel-title">Standing permissions (${b.sticky_allows.length})</div>
            ${b.sticky_allows.map(s => `
              <div class="allow-item"><code>${esc(s)}</code>
                <button class="chip-del" aria-label="Revoke ${esc(s)}" data-revoke-sticky="${esc(s)}">${icon("x")}</button>
              </div>`).join("") || `<p class="empty-inline">None — every risky command asks.</p>`}
          </div>

          <div class="panel">
            <div class="panel-title">Recent runs</div>
            ${(b.recent_runs || []).slice(0, 6).map(r => `
              <a class="meta-row" href="#/run/${esc(r.id)}" style="text-decoration:none;color:inherit;">
                <span>${statusChip(r.status)}</span><span class="mono">${timeAgo(r.created_at)}</span></a>`).join("")
              || `<p class="empty-inline">No runs yet.</p>`}
          </div>
        </div>
      </div>
    </div></div>`;

  // wiring
  const patch = async (body, msg) => {
    try {
      await api(`/bots/${encodeURIComponent(b.name)}`, { method: "PATCH", body });
      toast(msg); renderBotDetail(b.name); refreshRoster();
      return true;
    } catch (err) { toast(`Not saved: ${err.message}`, true); return false; }
  };
  $("#form-identity").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ description: fd.get("description"), instructions: fd.get("instructions") }, "Saved.");
  });
  $("#form-model").addEventListener("submit", ev => {
    ev.preventDefault();
    patch({ model: new FormData(ev.target).get("model").trim() }, "Model saved.");
  });
  $("#form-schedule").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ cron: fd.get("cron").trim(), timezone: fd.get("timezone").trim() }, "Schedule saved.");
  });
  $("#btn-clear-schedule").addEventListener("click", () => patch({ clear_cron: true }, "Now on demand."));
  $("#form-risk").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ approval_mode: fd.get("approval_mode"), risk_tier: fd.get("risk_tier"), workdir: fd.get("workdir").trim() }, "Policy saved.");
  });
  $("#form-limits").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const limits = Object.fromEntries([...fd.entries()].map(([key, value]) => [key,
      ["max_cost_usd", "daily_cost_cap_usd"].includes(key) ? Number(value) : Number.parseInt(value, 10)]));
    patch({ limits }, "Limits saved.");
  });
  $("#form-rule").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const rule = { match: fd.get("match").trim(), verdict: fd.get("verdict") };
    if (!rule.match) return;
    patch({ command_rules: [...rules, rule] }, "Rule added.");
  });
  $$("[data-del-mem]").forEach(btn => btn.addEventListener("click", async () => {
    const k = btn.dataset.delMem;
    if (!(await confirmDialog({ title: "Forget memory", body: `Delete <b>${esc(k)}</b>?`, confirmText: "Forget", danger: true }))) return;
    await api(`/bots/${encodeURIComponent(b.name)}/memory/${encodeURIComponent(k)}`, { method: "DELETE" });
    toast("Forgot it."); renderBotDetail(b.name);
  }));
  $$("[data-revoke-sticky]").forEach(btn => btn.addEventListener("click", async () => {
    await api(`/bots/${encodeURIComponent(b.name)}/sticky-allows/${encodeURIComponent(btn.dataset.revokeSticky)}`, { method: "DELETE" });
    toast("Permission revoked."); renderBotDetail(b.name);
  }));
  $("#btn-estimate").addEventListener("click", async () => {
    const out = $("#estimate-out");
    out.textContent = "estimating…";
    try {
      const e = await api(`/bots/${encodeURIComponent(b.name)}/estimate?prompt=${encodeURIComponent($("#estimate-prompt").value)}`);
      out.textContent = e.summary || `estimated at $${Number(e.effective_ceiling_usd ?? 0).toFixed(4)} per run; provider billing can differ`;
    } catch (err) { out.textContent = err.message; }
  });
  $("#btn-delete-bot").addEventListener("click", async () => {
    if (!(await confirmDialog({
      title: "Delete bot",
      body: `Delete <b>${esc(b.name)}</b>? Its workspace, memory, and transcripts stay on disk, but the bot and its schedule are removed.`,
      confirmText: "Delete bot", danger: true,
    }))) return;
    await api(`/bots/${encodeURIComponent(b.name)}`, { method: "DELETE" });
    toast(`Deleted ${b.name}`);
    location.hash = "#/bots";
  });
  wireCommon();
}

/* ------------------------------------------------------------- run detail */

async function renderRunDetail(runId) {
  feedMode = "run";
  const r = await api(`/runs/${runId}`);
  currentStudioBot = r.bot_name;
  currentRunId = runId;
  setTopContext(`
    <div class="ctx-id"><h1>Run <span class="mono">#${esc(runId.slice(0, 12))}</span></h1>
      <div class="ctx-meta">${statusChip(r.status, r.status_label)}</div></div>
    <div class="ctx-actions">
      ${ACTIVE.has(r.status) ? `<button class="btn danger small" id="stop-this-run">${icon("stop")} Stop</button>` : ""}
      <a class="btn ghost small" href="#/runs">${icon("arrowLeft")} All runs</a>
    </div>`);
  const steps = (r.events || []).filter(e => e.type === "step").map(e => e.data);
  const sum = (k) => steps.reduce((t, d) => t + (d[k] || 0), 0);
  const model = sum("model_ms"), tool = sum("tool_ms"), over = sum("overhead_ms");
  const total = Math.max(1, model + tool + over);
  const pct = (v) => (v / total * 100).toFixed(1);
  const dur = (r.finished_at ? new Date(r.finished_at) : Date.now()) - new Date(r.created_at);
  view.innerHTML = `
    <div class="page-scroll" id="chat-scroll"><div class="feed" id="chat-stream">
      <div class="run-stats">
        <div class="ov-stats">
          <div class="kpi"><span class="kpi-label">Steps</span><span class="kpi-val">${r.steps}</span></div>
          <div class="kpi"><span class="kpi-label">Elapsed</span><span class="kpi-val">${fmtDur(dur)}</span></div>
          <div class="kpi"><span class="kpi-label">Spend</span><span class="kpi-val">$${(r.cost_usd || 0).toFixed(4)}</span></div>
          <div class="kpi"><span class="kpi-label">Tokens</span><span class="kpi-val">${fmtTokens(r.tokens)}</span></div>
        </div>
        ${steps.length ? `
        <div class="panel run-timing">
          <div class="panel-title">Where the time went</div>
          <div class="timeline-stack" role="img" aria-label="model ${Math.round(model)}ms, tools ${Math.round(tool)}ms, hutch ${Math.round(over)}ms">
            <i class="s-model" style="width:${pct(model)}%"></i>
            <i class="s-tool" style="width:${pct(tool)}%"></i>
            <i class="s-over" style="width:${pct(over)}%"></i>
          </div>
          <div class="timeline-legend">
            <span><i class="dot s-model"></i>model ${Math.round(model)}ms</span>
            <span><i class="dot s-tool"></i>tools ${Math.round(tool)}ms</span>
            <span><i class="dot s-over"></i>hutch ${Math.round(over)}ms</span>
          </div>
          <div class="step-strip">
            ${steps.map(d => {
              const t2 = (d.model_ms || 0) + (d.tool_ms || 0) + (d.overhead_ms || 0);
              return `<span class="step-seg" title="step ${d.n}: ${fmtDur(t2)}" style="flex:${Math.max(1, t2)}"><i class="s-model" style="flex:${Math.max(0, d.model_ms || 0)}"></i><i class="s-tool" style="flex:${Math.max(0, d.tool_ms || 0)}"></i><i class="s-over" style="flex:${Math.max(0, d.overhead_ms || 0)}"></i></span>`;
            }).join("")}
          </div>
        </div>` : ""}
      </div>
    </div></div>`;
  // append the transcript block below the stats
  const block = await runBlockHtml(runId);
  $("#chat-stream").insertAdjacentHTML("beforeend", block);
  $("#stop-this-run")?.addEventListener("click", async () => {
    await api(`/runs/${runId}/stop`, { method: "POST" });
    toast("Stop requested — already-finished steps are not undone.");
  });
  if (ACTIVE.has(r.status)) subscribeRun(runId);
  wireApprovals();
  wireFeedInteractions();
  updateTtls();
}

/* ---------------------------------------------------------- connections */

async function renderConnections() {
  let data;
  try { data = await api("/connections"); }
  catch (err) { view.innerHTML = errorState(err); return; }
  setTopContext(`<div class="ctx-id"><h1>Connections</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-add-conn">${icon("plus")} Add connection</button></div>`);
  const conns = data.connections || [];
  const windows = { "5h": "per 5 hours", "day": "per day", "week": "per week", "month": "per month" };
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="page-subtitle">A named hosted endpoint with its own key, terms, and allowance. Reference its models as <code class="mono">&lt;connection&gt;/&lt;model&gt;</code>.</p>
      ${conns.length ? conns.map(c => `
        <div class="panel conn-card" data-conn="${esc(c.name)}">
          <div class="bot-head">
            <span class="bot-name">${esc(c.title || c.name)}</span>
            <span class="tag mono">${esc(c.protocol)}</span>
            <span class="tag ${c.billing === "per_token" ? "info" : ""}">${esc(c.billing === "per_token" ? "per token" : "flat rate")}</span>
            <span class="chip ${c.has_key ? "ok" : "danger"}" style="margin-left:auto;">${c.has_key ? "key set" : "no key"}</span>
            <span class="chip ${c.ack === "ok" || c.ack === "not_needed" ? "ok" : "warn"}">${esc(c.ack === "required" ? "terms need acknowledging" : c.ack === "stale" ? "terms changed" : c.ack === "ok" ? "terms accepted" : "no terms")}</span>
          </div>
          <div class="bot-facts">
            <div>endpoint <b class="mono">${esc(c.base_url)}</b></div>
            <div>key source <b>${esc(c.key_source)}</b></div>
            <div>allowance <b>${c.quota_tokens ? `${fmtTokens(c.quota_tokens)} ${windows[c.quota_window] || c.quota_window}` : "none declared"}</b></div>
            <div>used in window <b>${c.quota_tokens ? `${fmtTokens(c.used)} (${Math.round((c.used / c.quota_tokens) * 100)}%)` : "—"}</b></div>
          </div>
          ${c.quota_tokens ? `<div class="meter-track" style="width:100%;margin:8px 0;"><div class="meter-fill" style="width:${Math.min(100, c.used / c.quota_tokens * 100)}%"></div></div>` : ""}
          ${c.terms_notice ? `<p class="hint">${esc(c.terms_notice)}</p>` : ""}
          <div class="card-actions" style="margin-top:12px;">
            <button class="btn ghost small" data-conn-action="test">${icon("zap")} Test</button>
            <button class="btn ghost small" data-conn-action="key">Set key</button>
            ${c.ack === "required" || c.ack === "stale" ? `<button class="btn warn small" data-conn-action="ack">Accept terms</button>` : ""}
            <button class="btn ghost small" data-conn-action="allowance">Allowance</button>
            <button class="btn ghost small" data-conn-action="clear-key">Remove key</button>
            <button class="btn danger small" data-conn-action="remove">Remove</button>
          </div>
          <p class="conn-result hint mono" hidden></p>
        </div>`).join("") : `
        <div class="empty-state">
          ${icon("layers", "icon-lg")}
          <p><b>No connections configured.</b></p>
          <p class="hint">Hosted providers (OpenAI, Anthropic) read their env keys directly. A connection is for a custom endpoint or a flat-rate plan you own.</p>
        </div>`}
      ${data.errors?.length ? `<p class="hint" style="color:var(--warn);">${esc(data.errors.join(" "))}</p>` : ""}
    </div></div>`;

  $("#btn-add-conn")?.addEventListener("click", () => {
    const tpls = data.templates || [];
    openModal({
      title: "Add connection",
      bodyHtml: `
        <form id="conn-form" class="form-grid">
          <label class="field">Template
            <select name="template">${tpls.map(t => `<option value="${esc(t.key)}">${esc(t.title || t.key)} — ${esc(t.billing)}</option>`).join("")}</select>
          </label>
          <label class="field">Name (blank = template's)
            <input type="text" name="name" placeholder="my-plan">
          </label>
          <label class="field">Base URL override (optional)
            <input type="text" name="base_url" placeholder="https://…">
          </label>
        </form>`,
      confirmText: "Add",
      onConfirm: async () => {
        const fd = new FormData($("#conn-form"));
        try {
          await api("/connections", { method: "POST", body: {
            template: fd.get("template"), name: fd.get("name").trim() || null, base_url: fd.get("base_url").trim() || null } });
          toast("Connection added. Now give it a key.");
          renderConnections();
          return true;
        } catch (err) { toast(err.message, true); return false; }
      },
    });
  });

  $$("[data-conn]").forEach(card => {
    const name = card.dataset.conn;
    const out = $(".conn-result", card);
    const show = (msg, ok) => { out.hidden = false; out.textContent = msg; out.style.color = ok ? "var(--brand-hi)" : "var(--danger)"; };
    $$(".card-actions [data-conn-action]", card).forEach(btn => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.connAction;
        if (action === "key") {
          openModal({
            title: `API key for ${name}`,
            bodyHtml: `<label class="field">Paste key<input type="password" name="key" autocomplete="off" spellcheck="false"></label>
              <p class="hint">Stored 0600 in the state directory — never echoed back or kept in the browser.</p>`,
            confirmText: "Store key",
            onConfirm: async () => {
              const key = $('input[name="key"]').value;
              try { const r = await api(`/connections/${encodeURIComponent(name)}/set-key`, { method: "POST", body: { key } }); show(r.detail, true); return true; }
              catch (err) { toast(err.message, true); return false; }
            },
          });
          return;
        }
        if (action === "allowance") {
          openModal({
            title: `Allowance for ${name}`,
            bodyHtml: `<div class="form-grid row2">
              <label class="field">Window<select name="window"><option value="5h">5 hours</option><option value="day">day</option><option value="week">week</option><option value="month">month</option></select></label>
              <label class="field">Tokens (0 = none)<input type="number" name="tokens" min="0" step="100000"></label>
            </div><p class="hint">Hutch reserves estimated tokens before a call. Provider allowance counting can differ from Hutch's estimate.</p>`,
            confirmText: "Save allowance",
            onConfirm: async () => {
              try {
                const r = await api(`/connections/${encodeURIComponent(name)}/allowance`, { method: "POST", body: {
                  window: $('select[name="window"]').value, tokens: Number($('input[name="tokens"]').value) } });
                show(r.detail, true); setTimeout(renderConnections, 600); return true;
              } catch (err) { toast(err.message, true); return false; }
            },
          });
          return;
        }
        if (action === "ack") {
          if (!(await confirmDialog({ title: "Terms", body: "Confirm you have read this connection's terms notice.", confirmText: "I have read them" }))) return;
          try { const r = await api(`/connections/${encodeURIComponent(name)}/ack`, { method: "POST", body: { agree: true } }); toast(r.detail); renderConnections(); }
          catch (err) { toast(err.message, true); }
          return;
        }
        if (action === "remove") {
          if (!(await confirmDialog({ title: "Remove connection", body: `Remove <b>${esc(name)}</b> and its stored key?`, confirmText: "Remove", danger: true }))) return;
          try { await api(`/connections/${encodeURIComponent(name)}/remove`, { method: "POST", body: {} }); toast(`Removed ${name}`); renderConnections(); }
          catch (err) { toast(err.message, true); }
          return;
        }
        btn.disabled = true; btn.textContent = "…";
        try {
          const r = await api(`/connections/${encodeURIComponent(name)}/${action}`, { method: "POST", body: {} });
          show(r.detail || "ok", true);
        } catch (err) { show(err.message, false); }
        finally { btn.disabled = false; btn.textContent = action === "test" ? "Test" : action; }
      });
    });
  });
}

/* -------------------------------------------------------- new-bot modal */

async function promptNewBot() {
  const templates = await api("/bots/templates");
  const html = `
    <form id="modal-bot-form" class="form-grid">
      <label class="field">Name
        <input type="text" name="name" placeholder="my-agent" pattern="[a-z0-9][a-z0-9-]{1,40}" required
          spellcheck="false" autocapitalize="none">
        <span class="hint">lowercase slug: letters, digits, dashes</span>
      </label>
      <label class="field">Start from a template
        <select name="template">
          <option value="">— blank —</option>
          ${templates.map(t => `<option value="${esc(t.name)}">${esc(t.tagline || t.name)}</option>`).join("")}
        </select>
      </label>
      <p class="hint" id="tpl-note">Blank bots start with no tools — you wire what they can do.</p>
      <div class="form-grid row2">
        <label class="field">Model
          <input type="text" name="model" value="mock/demo" required>
          <span class="hint">mock/demo · openai/gpt-4o-mini · ollama/llama3.2</span>
        </label>
        <label class="field">Schedule (cron, optional)
          <input type="text" name="cron" placeholder="0 9 * * 1">
        </label>
      </div>
      <label class="field">What it does (description)
        <input type="text" name="description" placeholder="Sort the downloads folder, on demand">
      </label>
    </form>`;

  openModal({
    title: "Create a bot",
    bodyHtml: html,
    confirmText: "Create bot",
    onConfirm: async () => {
      const fd = new FormData($("#modal-bot-form"));
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
          },
        });
        toast(`Bot "${name}" created.`);
        location.hash = `#/chat/${encodeURIComponent(name)}`;
        return true;
      } catch (err) {
        toast(err.message, true);
        return false;
      }
    },
  });
  // live template note so choosing isn't a guess
  const sel = $('select[name="template"]'), note = $("#tpl-note");
  const describe = () => {
    const t = templates.find(x => x.name === sel.value);
    note.textContent = !t ? "Blank bots start with no tools — you wire what they can do."
      : `${t.tagline || ""} ${t.reads ? `Reads: ${t.reads}. ` : ""}${t.produces ? `Produces: ${t.produces}. ` : ""}${t.needs_folder ? "Needs a working folder." : ""}`;
  };
  sel.addEventListener("change", describe);
  describe();
}

/* ----------------------------------------------------------- shared wire */

function wireCommon() {
  $$('[data-action="toggle-pause"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      const bot = btn.dataset.bot;
      const paused = btn.dataset.paused !== "true";
      await api(`/bots/${encodeURIComponent(bot)}`, { method: "PATCH", body: { paused } });
      toast(paused ? "Paused" : "Resumed");
      route(); refreshRoster();
    });
  });
  $("#topbar-new-bot")?.addEventListener("click", promptNewBot);
}

/* ------------------------------------------------------------------ boot */

route();
void loadStatusInfo();
refreshRoster();
setInterval(() => { refreshBadge(); }, 6000);
setInterval(refreshRoster, 20000);   // roster activity, gentle
pollHealth();
setInterval(pollHealth, HEARTBEAT_MS);
