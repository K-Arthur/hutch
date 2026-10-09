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
let studioGeneration = 0;

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

// The local OAuth callback redirects to the Connections view with a short-lived
// status only. Remove it from browser history before rendering the page.
const chatgptCallback = new URLSearchParams(location.search);
const chatgptResult = chatgptCallback.get("chatgpt_result");
if (chatgptResult) {
  const detail = chatgptCallback.get("detail");
  const message = chatgptResult === "connected" ? "ChatGPT plan route connected."
    : chatgptResult === "identity-only" ? "ChatGPT signed in, but plan use was not granted. Reauthorize to use it for models."
    : detail || "ChatGPT sign-in did not complete. Start again from Connections.";
  setTimeout(() => toast(message, chatgptResult === "error"), 0);
  history.replaceState(null, "", `${location.pathname}${location.hash || "#/connections"}`);
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
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1"/>',
  bot: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
  caret: '<path d="m9 18 6-6-6-6"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
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
  brain: '<path d="M12 4a4 4 0 0 0-4 4 3.5 3.5 0 0 0-1 6.5A3.5 3.5 0 0 0 12 19a3.5 3.5 0 0 0 5-4.5 3.5 3.5 0 0 0-1-6.5 4 4 0 0 0-4-4Z"/><path d="M12 4v15"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6"/>',
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
   Unique agent sigils: a shape from a curated family wearing one of eight
   brand-adjacent colours, with two glints that read as a face. The pair is
   derived from the bot's name (stable with zero storage), and can be
   overridden at creation or in settings — no two bots look alike, while the
   family stays one visual language. Identity never encodes status: status
   rides the pip, and the pip is always paired with a word (title/aria). */
/* Identity palette — brighter, high-chroma, drawn from the mascot's mint
   lineage (website/assets/hutch-agent.svg). Identity only: status never
   rides here (the pip does that, always with a word). */
const ID_COLORS = ["#3DE8C5", "#35C3F0", "#5B9BFF", "#9B7CFF", "#C77DFF", "#FF6FA5", "#FFA83C", "#7BD85A"];
/* Transcribed from the 3D mascot blueprint (website/assets/hutch-agent.svg,
   rendered by the site-mascot workstream): gradient shell (light/base/deep
   with a rim light), a dome cap with a bright band, a wide dark glass visor
   with a top shine, glowing happy-arc eyes + smile, swept side fins, a
   luminous chest core, and a soft ground glow. Shape picker varies the shell
   silhouette; colour varies the shell. Detail is pruned at small sizes. */
// Eight silhouettes that stay distinct at 30px: tall pill, circle, squircle,
// wide bean, droplet, shield, triangle, hexagon. Per-shape face placement
// (visor width/y, fin level) so the plate always sits inside the body.
// Poly shapes round their corners via a {S}/{SW} stroke painted by bodySvg().
const ID_HEADS = [
  { key: "capsule",  top: 14,   h: 36,   vw: 20, vy: 7,    vh: 12,   hw: 13,   cap: true,  core: true,
    body: '<rect x="19" y="14" width="26" height="36" rx="13"/>' },
  { key: "round",    top: 15,   h: 32,   vw: 21, vy: 6,    vh: 12,   hw: 15.5, cap: true,  core: true,
    body: '<circle cx="32" cy="31" r="16"/>' },
  { key: "squircle", top: 15,   h: 31,   vw: 22, vy: 5.5,  vh: 12,   hw: 15.5, cap: true,  core: true,
    body: '<rect x="16.5" y="15" width="31" height="31" rx="11"/>' },
  { key: "bean",     top: 20,   h: 24,   vw: 24, vy: 5.5,  vh: 12,   hw: 18,   cap: false, core: false,
    body: '<rect x="13" y="20" width="38" height="24" rx="12"/>' },
  { key: "droplet",  top: 13,   h: 31.5, vw: 17, vy: 13,   vh: 11,   hw: 12,   cap: false, core: false,
    body: '<path d="M32 13c6.6 7.9 12 13.2 12 19.5a12 12 0 0 1-24 0c0-6.3 5.4-11.6 12-19.5Z"/>' },
  { key: "shield",   top: 13.5, h: 36,   vw: 19, vy: 7.5,  vh: 12,   hw: 14,   cap: false, core: true,
    body: '<path d="M32 13.5c4.8 2.8 10.2 4.5 14.6 5 1 .1 1.8.9 1.8 1.9v10.3c0 9.3-6.5 15.9-16.4 19.2C22.1 46.5 15.6 40 15.6 30.7V20.4c0-1 .8-1.8 1.8-1.9 4.4-.5 9.8-2.2 14.6-5Z"/>' },
  { key: "triangle", top: 14,   h: 30,   vw: 14, vy: 15,   vh: 10.5, hw: 9.5,  cap: false, core: false,
    body: '<path d="M30.62 16.66a3 3 0 0 1 2.76 0L46.12 41.34a3 3 0 0 1-1.62 2.66H19.5a3 3 0 0 1-1.62-2.66L30.62 16.66Z" stroke="{S}" stroke-width="{SW}" stroke-linejoin="round"/>' },
  { key: "hex",      top: 16.8, h: 29.4, vw: 20, vy: 6,    vh: 11.5, hw: 15,   cap: false, core: true,
    body: '<path d="M23.5 16.8h17L49 31.5l-8.5 14.7h-17L15 31.5Z" stroke="{S}" stroke-width="{SW}" stroke-linejoin="round"/>' },
];
const bodySvg = (h, paint, rw) => h.body.replace(/\{S\}/g, paint).replace(/\{SW\}/g, rw);

function hash32(s) {
  let h = 2166136261;
  for (const c of String(s)) { h ^= c.codePointAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function tint(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const m = c => Math.round(c + (255 - c) * amt);
  return `rgb(${m(n >> 16)},${m((n >> 8) & 255)},${m(n & 255)})`;
}
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const m = c => Math.round(c * amt);
  return `rgb(${m(n >> 16)},${m((n >> 8) & 255)},${m(n & 255)})`;
}

// chosen overrides live in localStorage (view state). A server-side avatar
// field on Bot is a recorded follow-up for the platform workstream.
const idStore = (() => {
  let all = {};
  try { all = JSON.parse(localStorage.getItem("hutch:sigils") || "{}"); } catch {}
  return {
    all,
    save() { try { localStorage.setItem("hutch:sigils", JSON.stringify(all)); } catch {} },
  };
})();
function sigilPair(name) {
  const over = idStore.all[name];
  if (Array.isArray(over) && ID_COLORS[over[0]] && ID_HEADS[over[1]]) return over;
  const h = hash32(name);
  return [h % ID_COLORS.length, ((h >>> 5) ^ (h >>> 13)) % ID_HEADS.length];
}
function sigilSet(name, pair) { idStore.all[name] = pair; idStore.save(); }

function sigilBody(pair, size = 30) {
  /* Transcribed from the 3D mascot (website/assets/hutch-agent.svg): gradient
     shell with rim light, dome cap + bright band, dark glass visor, glowing
     happy-arc eyes (+ smile), side fins, luminous chest core, ground glow.
     Detail prunes by size — visor+eyes at 30, rim+glow at 44, smile+core at
     56 — and the core only on shapes with chest room below the visor. */
  const [ci, si] = pair;
  const base = ID_COLORS[ci], light = tint(base, 0.45), pale = tint(base, 0.82), deep = shade(base, 0.55);
  const gid = `sg-${ci}`, vid = `vg-${ci}`, cid = `cg-${ci}`;
  const h = ID_HEADS[si] || ID_HEADS[0];
  const vy = h.top + h.vy, vh = h.vh, vw = h.vw;
  const big = size >= 44, face = size >= 56;
  const finY = (vy + vh * 0.75 + 1.5).toFixed(1);
  const fxr = (32 + h.hw + 1.8).toFixed(1), fxl = (32 - h.hw - 1.8).toFixed(1);
  const dome = h.cap ? `M25 ${h.top}c0-4.4 3-6.9 7-6.9s7 2.5 7 6.9Z` : "";
  const vx = (32 - vw / 2).toFixed(1);
  // Face sized to the visor: arcs keep 1.6–2.9u margins inside the plate, so
  // the eyes never smear into the rim at roster size.
  const gap = Math.max(1.4, vw * 0.1);
  const ew = ((vw - 5.8) / 2 - gap);
  const ey = (vy + (face ? vh * 0.42 : vh * 0.5 + 1.4)).toFixed(1);
  const arcEye = x1 => `M${x1.toFixed(1)} ${ey}q${(ew / 2).toFixed(1)} ${(-ew * 0.95).toFixed(1)} ${ew.toFixed(1)} 0`;
  const eyeL = arcEye(32 - gap - ew), eyeR = arcEye(32 + gap);
  const mouth = `M29.6 ${(vy + vh - 2.6).toFixed(1)}q2.4 2.4 4.8 0`;
  const coreCy = (vy + vh + 5.6).toFixed(1);
  return `<defs>
    <linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${light}"/><stop offset=".55" stop-color="${base}"/><stop offset="1" stop-color="${deep}"/></linearGradient>
    <linearGradient id="${vid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0c252b"/><stop offset="1" stop-color="#050d12"/></linearGradient>
    <radialGradient id="${cid}" cx=".5" cy=".45" r=".6"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset=".55" stop-color="${pale}" stop-opacity=".4"/><stop offset="1" stop-color="${pale}" stop-opacity="0"/></radialGradient>
  </defs>
  <ellipse cx="32" cy="${(h.top + h.h + 3).toFixed(1)}" rx="${Math.max(11, h.hw * 0.8).toFixed(1)}" ry="1.9" fill="${base}" opacity=".15"/>
  <g fill="url(#${gid})">
    <ellipse cx="${fxl}" cy="${finY}" rx="3.8" ry="6.2" transform="rotate(-15 ${fxl} ${finY})"/>
    <ellipse cx="${fxr}" cy="${finY}" rx="3.8" ry="6.2" transform="rotate(15 ${fxr} ${finY})"/>
    ${bodySvg(h, `url(#${gid})`, 5)}
    ${dome ? `<path d="${dome}"/>` : ""}
  </g>
  ${big ? `<g fill="none" stroke="${pale}" stroke-opacity=".5" stroke-width="1.1">${bodySvg(h, pale, 1.1)}${dome ? `<path d="${dome}"/>` : ""}</g>` : ""}
  ${h.cap ? `<rect x="23.8" y="${(h.top - 1.3).toFixed(1)}" width="16.4" height="2.3" rx="1.15" fill="#fff" opacity=".9"/>` : ""}
  <rect x="${vx}" y="${vy.toFixed(1)}" width="${vw}" height="${vh}" rx="${(vh * 0.42).toFixed(1)}" fill="url(#${vid})"${big ? ` stroke="${pale}" stroke-opacity=".55" stroke-width="1"` : ""}/>
  <rect x="${(32 - vw / 2 + 3).toFixed(1)}" y="${(vy + 1.7).toFixed(1)}" width="${(vw - 6).toFixed(1)}" height="1.5" rx=".75" fill="#fff" opacity=".14"/>
  ${h.core && face ? `<circle cx="32" cy="${coreCy}" r="4.6" fill="url(#${cid})"/><circle cx="32" cy="${(vy + vh + 4.9).toFixed(1)}" r="1.7" fill="#fff" opacity=".9"/>` : ""}
  <g class="gl" fill="none" stroke-linecap="round">
    ${big ? `<path d="${eyeL}" stroke="${pale}" stroke-opacity=".38" stroke-width="4.6"/><path d="${eyeR}" stroke="${pale}" stroke-opacity=".38" stroke-width="4.6"/>` : ""}
    <path d="${eyeL}" stroke="#fff" stroke-width="2.6"/>
    <path d="${eyeR}" stroke="#fff" stroke-width="2.6"/>
    ${face ? `<path d="${mouth}" stroke="#fff" stroke-width="1.8"/>` : ""}
  </g>`;
}

function avatarFromPair(pair, size, state = "") {
  return `<span class="avatar" style="--av:${size}px" ${size >= 36 ? 'data-gaze' : ""} aria-hidden="true"><svg class="sig" viewBox="0 0 64 64">${sigilBody(pair, size)}</svg>${state ? `<span class="a-pip ${esc(state)}"></span>` : ""}</span>`;
}

function botAvatar(name, size = 32, state = "") {
  return avatarFromPair(sigilPair(name), size, state);
}
const hexAvatar = botAvatar;   // shared renderers still call this name

function botStatusLabel(b) {
  if (b.active_run_id) return b.active_run_status_label || statusInfo[b.active_run_status]?.label || "Status unavailable";
  return b.paused ? "Paused" : "Idle";
}

function botNeedsYou(b) {
  return ["waiting_approval", "waiting_human"].includes(b.active_run_status) || attentionBots.includes(b.name);
}
// Glints follow the cursor on devices that can: a one-rAF pointer watcher that
// shifts each large avatar's eye group a few px toward the pointer. Local to
// the page — no position leaves the DOM, ever. Static for coarse pointers,
// reduced motion, and the Reduce effects control.
(function gazeTracking() {
  if (!window.matchMedia || !matchMedia("(pointer: fine)").matches) return;
  let raf = 0, mx = 0, my = 0;
  const apply = () => {
    raf = 0;
    const off = document.documentElement.classList.contains("reduce-effects");
    for (const el of document.querySelectorAll(".avatar[data-gaze]")) {
      if (off) { el.style.removeProperty("--gx"); el.style.removeProperty("--gy"); continue; }
      const r = el.getBoundingClientRect();
      if (!r.width) continue;
      const dx = mx - (r.left + r.width / 2), dy = my - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy);
      const k = Math.min(1, d / 160) * r.width * 0.075;
      el.style.setProperty("--gx", ((dx / (d || 1)) * k).toFixed(2));
      el.style.setProperty("--gy", ((dy / (d || 1)) * k).toFixed(2));
    }
  };
  document.addEventListener("pointermove", ev => {
    mx = ev.clientX; my = ev.clientY;
    if (!raf) raf = requestAnimationFrame(apply);
  }, { passive: true });
})();

/* Hero mascot look-at-cursor: the site workstream's 7x3 sprite set (the same
   character, transparent webp). Only on capable pointers with effects allowed;
   the center frame is the static fallback and the only frame loaded up front —
   the rest preload after the first pointer move over the hero. */
(function heroGaze() {
  if (!window.matchMedia || !matchMedia("(pointer: fine)").matches) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (navigator.connection && navigator.connection.saveData) return;
  if ((navigator.hardwareConcurrency || 4) < 4) return;
  const COLS = 7, ROWS = 3, CC = 3, CR = 1;          // center frame = f3-p1
  const srcFor = (c, r) => `/static/agent/f${c}-p${r}.webp`;
  const loaded = new Set(["3-1"]);
  let failed = false, prerested = false, raf = 0, cur = "3-1", tgt = { c: CC, r: CR };
  const img = () => document.querySelector("#hero-agent .hero-img");
  function show(c, r) {
    const el = img(); if (!el || failed) return;
    const k = `${c}-${r}`; if (k === cur) return;
    if (!loaded.has(k)) {
      const im = new Image();
      im.onload = () => { loaded.add(k); if (`${tgt.c}-${tgt.r}` === k) { el.src = srcFor(c, r); cur = k; } };
      im.onerror = () => { failed = true; };   // missing set: stay on the center frame
      im.src = srcFor(c, r);
      return;
    }
    el.src = srcFor(c, r); cur = k;
  }
  function preloadRest() {
    if (prerested) return; prerested = true;
    for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS; r++) {
      const k = `${c}-${r}`; if (loaded.has(k)) continue;
      const im = new Image();
      im.onload = () => loaded.add(k);
      im.onerror = () => { failed = true; };
      im.src = srcFor(c, r);
    }
  }
  document.addEventListener("pointermove", ev => {
    if (document.hidden || failed) return;
    const hero = document.getElementById("hero-agent");
    if (!hero) return;
    preloadRest();
    const rect = hero.getBoundingClientRect();
    const nx = (ev.clientX - (rect.left + rect.width / 2)) / (rect.width * 2.2);
    const ny = (ev.clientY - (rect.top + rect.height / 2)) / (rect.height * 2.6);
    const c = Math.round(CC + Math.max(-0.5, Math.min(0.5, nx)) * (COLS - 1));
    const r = Math.round(CR + Math.max(-0.5, Math.min(0.5, ny)) * (ROWS - 1));
    if (c !== tgt.c || r !== tgt.r) {
      tgt = { c, r };
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; show(tgt.c, tgt.r); });
    }
  }, { passive: true });
})();

// shared identity picker (creation modal + bot settings)
function identityPickerHtml() {
  return `
    <div class="idp">
      <div class="idp-prev" data-idp-prev></div>
      <p class="idp-lbl">Colour</p>
      <div class="idp-row" data-idp-colors>${ID_COLORS.map((c, i) =>
        `<button type="button" class="sw" data-ci="${i}" style="background:${c}" aria-label="Colour ${i + 1}" aria-pressed="false"></button>`).join("")}</div>
      <p class="idp-lbl">Shape</p>
      <div class="idp-row" data-idp-shapes>${ID_HEADS.map((hh, i) =>
        `<button type="button" class="shp" data-si="${i}" aria-label="Shape ${esc(hh.key)}" aria-pressed="false">
          <svg viewBox="0 0 64 64" aria-hidden="true"><g fill="currentColor">${bodySvg(hh, "currentColor", 4)}${hh.cap ? `<path d="M25 ${hh.top}c0-4.4 3-6.9 7-6.9s7 2.5 7 6.9Z"/>` : ""}</g></svg>
        </button>`).join("")}</div>
      <button type="button" class="btn ghost small idp-shuffle" data-idp-shuffle>${icon("refresh")} Surprise me</button>
    </div>`;
}
function mountIdentityPicker(scope, name) {
  let sel = sigilPair(name).slice();
  const prev = $("[data-idp-prev]", scope);
  const render = () => {
    prev.innerHTML = avatarFromPair(sel, 64);
    $$("[data-ci]", scope).forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.ci === sel[0])));
    $$("[data-si]", scope).forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.si === sel[1])));
  };
  scope.addEventListener("click", ev => {
    const c = ev.target.closest("[data-ci]"), s = ev.target.closest("[data-si]"), sh = ev.target.closest("[data-idp-shuffle]");
    if (c) sel = [+c.dataset.ci, sel[1]];
    else if (s) sel = [sel[0], +s.dataset.si];
    else if (sh) sel = [Math.floor(Math.random() * ID_COLORS.length), Math.floor(Math.random() * ID_HEADS.length)];
    else return;
    render();
  });
  render();
  return { get: () => sel.slice() };
}

function botState(b) {
  if (b.active_run_id) return b.active_run_status || "pending";
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

function openModal({ title, bodyHtml, onConfirm, onCancel, confirmText = "Confirm", confirmClass = "primary", wide = false, returnFocus = null, showCancel = true }) {
  const root = $("#modal-root");
  const modalReturnFocus = returnFocus || document.activeElement;
  root.innerHTML = `
    <div class="modal-backdrop" data-modal-backdrop>
      <div class="modal-card${wide ? " modal-wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-header">
          <h3 id="modal-title">${esc(title)}</h3>
          <button class="icon-btn" id="modal-close" aria-label="Close dialog">${icon("x")}</button>
        </div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-footer">
          <button class="btn ghost" id="modal-cancel" ${showCancel ? '' : 'hidden'}>Cancel</button>
          <button class="btn ${confirmClass}" id="modal-confirm">${esc(confirmText)}</button>
        </div>
      </div>
    </div>
  `;
  const card = $(".modal-card", root);
  const close = (cancelled = true) => {
    if (!card.isConnected) return;
    document.removeEventListener("keydown", keyHandler, true);
    root.innerHTML = "";
    if (cancelled && onCancel) onCancel();
    // Prefer a fresh equivalent control when a live SSE refresh replaced the
    // original node while the modal was open. A connected stale button can
    // still be detached immediately after close.
    if (modalReturnFocus?.dataset.receiptReview) {
      const target = $$('[data-receipt-review]').find(b => b.dataset.receiptReview === modalReturnFocus.dataset.receiptReview);
      (target || $('#chat-prompt') || $('#needs-you-open'))?.focus();
    }
    else if (FACT_BUTTONS.some(([field]) => modalReturnFocus?.dataset[field])) {
      const [field, selector] = FACT_BUTTONS.find(([field]) => modalReturnFocus.dataset[field]);
      ($$(selector).find(button => button.dataset[field] === modalReturnFocus.dataset[field]) || $('#chat-prompt'))?.focus();
    }
    else if (modalReturnFocus?.isConnected && modalReturnFocus.getClientRects().length) modalReturnFocus.focus();
    else ($('#chat-prompt') || $('#nav-toggle'))?.focus();
    if (feedRefreshPending) {
      feedRefreshPending = false;
      scheduleFeedRender();
    }
  };
  const keyHandler = ev => {
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); return; }
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
  [/^#\/conversation\/([\w-]+)$/, m => openConversation(m[1]), "chat"],
  [/^#\/overview$/, renderOverview, "overview"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs(?:\?(.*))?$/, m => renderRuns(m ? m[1] : ""), "runs"],
  [/^#\/approvals$/, renderApprovals, "chat"],
  [/^#\/connections$/, renderConnections, "connections"],
  [/^#\/bot\/([\w-]+)$/, m => renderBotDetail(decodeURIComponent(m[1])), "chat"],
  [/^#\/run\/([\w-]+)$/, m => renderRunDetail(m[1]), "runs"],
];

async function openConversation(id) {
  const conversation = await api(`/v1/conversations/${encodeURIComponent(id)}`);
  const bots = await api("/bots");
  const bot = bots.find(b => b.id === conversation.bot_id);
  if (!bot) throw new Error("This conversation's bot is no longer available. Its history is retained in run history.");
  storageSet(`hutch-conversation:${bot.id}`, id);
  history.replaceState(null, "", `#/chat/${encodeURIComponent(bot.name)}`);
  await renderChatStudio(bot.name);
}

async function route() {
  const hash = location.hash || "#/chat";
  document.body.classList.toggle("has-composer", hash.startsWith("#/chat"));
  stopRunSubs();
  studioGeneration++;
  if (needsYouDialog.open) closeNeedsYou();
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
      if (["overview", "runs", "bots"].includes(nav)) $("#monitor-nav").open = true;
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
  const focus = document.activeElement;
  const focusedBot = list.contains(focus) ? focus.dataset.switchBot : null;
  const focusedSettings = list.contains(focus) ? focus.getAttribute("href") : null;
  $("#fleet-nav").hidden = botsCache.length < 10;
  const q = ($("#bot-search")?.value || "").trim().toLowerCase();
  const bots = q ? botsCache.filter(b => b.name.toLowerCase().includes(q) || (b.description || "").toLowerCase().includes(q)) : botsCache;
  if (!bots.length) {
    list.innerHTML = `<div class="roster-empty">${botsCache.length ? "No bot matches." : "No bots yet — create one."}</div>`;
    return;
  }
  list.innerHTML = bots.map(b => {
    const state = botState(b);
    const pip = botNeedsYou(b) ? "waiting" : state === "running" ? "running" : state === "paused" ? "paused" : "";
    const word = botNeedsYou(b) ? "Needs you" : botStatusLabel(b);
    return `
      <div class="roster-entry"><button class="roster-row" type="button" data-switch-bot="${esc(b.name)}"
        ${b.name === currentStudioBot && location.hash.startsWith("#/chat") ? 'aria-current="true"' : ""}
        title="${esc(b.name)} — ${word}">
        ${botAvatar(b.name, 30, pip)}
        <span class="roster-id">
          <span class="roster-name">${esc(b.name)}</span>
          <span class="roster-sub">${esc(truncate(b.model || "", 20))} · ${word}</span>
        </span>
      </button><a class="roster-settings icon-btn" href="#/bot/${esc(b.name)}" aria-label="Settings for ${esc(b.name)}" title="Settings for ${esc(b.name)}">${icon("sliders")}</a></div>`;
  }).join("");
  $$("#roster-list [data-switch-bot]").forEach(row =>
    row.addEventListener("click", () => { location.hash = `#/chat/${encodeURIComponent(row.dataset.switchBot)}`; }));
  if (focus && !focus.isConnected) {
    const replacement = focusedBot
      ? $$("[data-switch-bot]", list).find(el => el.dataset.switchBot === focusedBot)
      : focusedSettings && $$("a", list).find(el => el.getAttribute("href") === focusedSettings);
    (replacement || $("#bot-search"))?.focus({ preventScroll: true });
  }
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
  const focusable = $$("#workspace a, #workspace button:not([hidden]), #workspace input:not([disabled]), #workspace summary")
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

/* Effects follow the OS by default; the explicit override lives in
   Preferences (sidebar footer) for the cases the OS setting does not cover. */
function applyEffects() {
  const stored = store$.get("hutch:reduce-effects", null);
  const reduce = stored === null ? matchMedia("(prefers-reduced-motion: reduce)").matches : !!stored;
  document.documentElement.classList.toggle("reduce-effects", reduce);
  const cb = $("#pref-reduce"); if (cb) cb.checked = reduce;
}
applyEffects();
matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", applyEffects);
{
  const t = $("#prefs-toggle"), pop = $("#prefs-pop");
  if (t && pop) {
    t.addEventListener("click", () => {
      const open = pop.hidden;
      pop.hidden = !open;
      t.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", ev => {
      if (!pop.hidden && !ev.target.closest(".pref-wrap")) { pop.hidden = true; t.setAttribute("aria-expanded", "false"); }
    });
    document.addEventListener("keydown", ev => {
      if (ev.key === "Escape" && !pop.hidden) { pop.hidden = true; t.setAttribute("aria-expanded", "false"); }
    });
  }
  const cb = $("#pref-reduce");
  cb?.addEventListener("change", () => {
    store$.set("hutch:reduce-effects", cb.checked);
    applyEffects();
    toast(cb.checked ? "Effects reduced" : "Effects restored");
  });
}

/* Sidebar docking: collapse to an icon rail on desktop; remembered between
   visits. Phones keep the full-width overlay sheet (the dock button hides). */
{
  const shell = $(".app-shell"), btn = $("#sidebar-toggle");
  const setDocked = docked => {
    shell.classList.toggle("collapsed", docked);
    btn?.setAttribute("aria-expanded", String(!docked));
    btn?.setAttribute("aria-label", docked ? "Expand sidebar" : "Collapse sidebar");
    btn?.setAttribute("title", docked ? "Expand sidebar" : "Collapse sidebar");
  };
  setDocked(store$.get("hutch:sidebar-collapsed", false));
  btn?.addEventListener("click", () => {
    const next = !shell.classList.contains("collapsed");
    store$.set("hutch:sidebar-collapsed", next);
    setDocked(next);
  });
  // Collapsed rail: the logo IS the expand control (the dock button hides);
  // expanded, the dock button sits separately beside the logo.
  $(".ws-brand .brand")?.addEventListener("click", () => {
    if (shell.classList.contains("collapsed") && innerWidth > 901) {
      store$.set("hutch:sidebar-collapsed", false);
      setDocked(false);
    }
  });
}

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
  pill.hidden = state === "live";   // healthy says nothing; degraded speaks up
}

async function pollHealth() {
  try {
    const h = await api("/health");
    lastHealthAt = Date.now();
    setDaemon(h.execution_held ? "held" : "live", `${h.execution_held ? 'Execution held for restore review' : 'daemon live'} — v${h.version} · schema ${h.schema}`);
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
let unresolvedReceiptCount = 0;
let lastNotificationPending = null;

function browserAlertsEnabled() {
  return store$.get("hutch:browser-alerts", false) && window.isSecureContext &&
    typeof Notification !== "undefined" && Notification.permission === "granted";
}

function updateBrowserAlertsUi() {
  const button = $("#browser-alerts-toggle"), status = $("#browser-alerts-status");
  if (!button || !status) return;
  if (!window.isSecureContext || typeof Notification === "undefined") {
    button.disabled = true;
    status.textContent = "This browser does not support alerts for this connection.";
    return;
  }
  const enabled = browserAlertsEnabled();
  button.textContent = enabled ? "Turn off alerts" : "Enable browser alerts";
  button.disabled = !enabled && Notification.permission === "denied";
  status.textContent = enabled
    ? "On while Hutch is open. Alerts show no chat, bot or action details."
    : Notification.permission === "denied"
      ? "Alerts are blocked by your browser. Change this site’s notification permission to enable them."
      : "Optional alerts while this page is in the background. Hutch must stay open; no chat or action text is included.";
}

$("#browser-alerts-toggle")?.addEventListener("click", async () => {
  if (browserAlertsEnabled()) {
    store$.set("hutch:browser-alerts", false);
    updateBrowserAlertsUi();
    return;
  }
  if (!window.isSecureContext || typeof Notification === "undefined" || Notification.permission === "denied") {
    updateBrowserAlertsUi();
    return;
  }
  try {
    const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (permission === "granted") store$.set("hutch:browser-alerts", true);
  } catch { /* browser permission APIs vary; the UI reports the resulting state */ }
  updateBrowserAlertsUi();
});

function notifyNewAttention(approvals, receipts) {
  const current = [approvals, receipts];
  if (lastNotificationPending === null) {
    lastNotificationPending = current;
    return;
  }
  const increased = current.some((value, index) => value > lastNotificationPending[index]);
  lastNotificationPending = current; // set before construction to deduplicate overlapping refreshes
  if (!increased) return;
  if (!document.hidden || !browserAlertsEnabled()) return;
  try {
    const notice = new Notification("Hutch needs you", {
      body: "An approval or action outcome is waiting for review.",
      tag: "hutch-needs-you",
    });
    notice.onclick = () => {
      window.focus();
      if (!needsYouDialog.open) void openNeedsYou();
      notice.close();
    };
  } catch { /* an OS/browser notification failure must not affect work or approvals */ }
}

async function refreshBadge() {
  try {
    const stats = await api("/stats");
    $('#execution-hold').hidden = !stats.execution_held;
    unresolvedReceiptCount = stats.unresolved_actions || 0;
    const n = (stats.pending_approvals || 0) + unresolvedReceiptCount;
    const previousPendingCount = lastPendingCount;
    const badge = $("#approval-badge");
    if (badge) {
      badge.textContent = n;
      badge.classList.toggle("hidden", n === 0);
    }
    $("#needs-you-open")?.classList.toggle("attention", n > 0);
    renderWorkflow(stats);
    $('[data-nav="approvals"]')?.classList.toggle("attention", n > 0);
    if (n) {
      try {
        const pend = await api("/approvals");
        attentionBots = [...new Set(pend.map(a => a.bot_name))];
      } catch { attentionBots = []; }
    } else attentionBots = [];
    lastPendingCount = n;
    renderRoster();
    renderAttention();
    if (previousPendingCount !== null && n > previousPendingCount) {
      announce(unresolvedReceiptCount ? `${n} items need your review.` : `${n} approval${n === 1 ? "" : "s"} waiting for you.`);
    }
    notifyNewAttention(stats.pending_approvals || 0, unresolvedReceiptCount);
    lastPendingCount = n;
  } catch {}
}

updateBrowserAlertsUi();

$('#restore-report-open').addEventListener('click', async () => {
  const trigger = $('#restore-report-open');
  trigger.disabled = true;
  try {
    const { report } = await api('/v1/state/restore?limit=1');
    if (!report) throw new Error('No restore report is available.');
    // The hold explanation remains in the header/dialog. Remove its prior
    // submission toast so it cannot cover the dialog's Close control on phones.
    $('#toast-root').replaceChildren();
    openModal({ title: 'Restored history', confirmText: 'Close', showCancel: false, returnFocus: trigger,
      bodyHtml: `<p>${report.execution_held ? 'Execution is paused for a local review on the executor.' : 'A local review was recorded; new work is allowed.'}</p>
        <p>Old attempts will not resume. Restoration paused saved schedules and revoked standing permissions and device sessions.</p>
        <p><strong>Source processes were not stopped by this restore.</strong> Stop the original services and check effects after the snapshot before activating this copy.</p>
        <dl class="kv-list">${Object.entries(report.counts).map(([key, count]) => `<div><dt>${esc(key.replaceAll('_', ' '))}</dt><dd>${esc(count)}</dd></div>`).join('')}</dl>
        <p>This database snapshot excludes credentials, browser profiles and user files. Preserve and review those separately.</p>
        <p class="hint">On the executor, inspect <code>hutch state report ${esc(report.id)}</code>. Record the review with <code>hutch state activate</code> when ready.</p>` });
  } catch (error) { toast(error.message, 'error'); }
  finally { trigger.disabled = false; }
});

// Workflow header status: real activity only — running runs, queued work,
// approvals needing a person, or a degraded executor. Idle+healthy = quiet.
function renderWorkflow(stats) {
  const el = $("#workflow");
  if (!el) return;
  const parts = [];
  const r = stats.active_runs || 0, q = stats.queued_tasks || 0, p = stats.pending_approvals || 0;
  if (r) parts.push(`<span class="w working"><span class="wdot"></span>${r} working</span>`);
  if (q) parts.push(`<span class="w queued"><span class="wdot"></span>${q} queued</span>`);
  if (p) parts.push(`<a class="w needs" href="#/approvals"><span class="wdot"></span>${p} need${p === 1 ? "s" : ""} you</a>`);
  el.innerHTML = parts.join("");
  el.hidden = parts.length === 0;
}

// The bar keeps pending approval discoverable from any surface (terminal,
// artifact, phone sheet) without modal storms: one line, one action.
function renderAttention() {  const bar = $("#attention-bar");
  if (!bar) return;
  const n = lastPendingCount || 0;
  const onApprovals = needsYouDialog.open;
  const shownRequests = $$("#chat-stream [data-approval-card]").filter(c => c.querySelector("[data-approve]:not([disabled])"));
  const shownReceipts = $$('#chat-stream [data-receipt-card]').filter(c => !c.dataset.receiptReviewed);
  const allInChat = location.hash.startsWith("#/chat") && n && n <= shownRequests.length + shownReceipts.length;
  if (!n || onApprovals || allInChat || attentionDismissedCount === n) { bar.hidden = true; return; }
  bar.hidden = false;
  bar.innerHTML = `${icon("alert")}
    <span><b>${unresolvedReceiptCount ? `${n} items need your review` : `${n} approval${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you`}</b></span>
    <button class="btn ghost small" id="attention-review" type="button">Review</button>
    <button class="icon-btn" id="attention-dismiss" aria-label="Dismiss reminder">${icon("x")}</button>`;
  $("#attention-review")?.addEventListener("click", openNeedsYou);
  $("#attention-dismiss")?.addEventListener("click", () => { attentionDismissedCount = n; bar.hidden = true; });
}

/* ------------------------------------------------------- CHAT STUDIO */

async function renderChatStudio(preferredBot = null) {
  const generation = ++studioGeneration;
  const fetchedBots = await api("/bots");
  if (generation !== studioGeneration) return;
  botsCache = fetchedBots;
  renderRoster();
  if (!botsCache.length) {
    view.innerHTML = `<div class="page-scroll"><div class="container"><div class="empty-state">
      ${icon("bot", "icon-lg")}
      <p><b>No bots yet.</b></p>
      <p class="hint">Choose a real model route when you create a bot. Configure a hosted connection or start a local model first; Hutch will not create sample bots or simulate a run.</p>
      <a class="btn ghost" href="#/connections">Configure a model connection</a>
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
  if (generation !== studioGeneration) return;
  currentConversations = await api(`/v1/conversations?bot=${encodeURIComponent(bot.id)}&include_legacy=true&limit=100`);
  if (generation !== studioGeneration) return;
  const rememberedConversation = storageGet(`hutch-conversation:${bot.id}`);
  let selectedConversation = currentConversations.find(c => c.id === rememberedConversation) || null;
  if (!selectedConversation) selectedConversation = currentConversations.find(c => !c.archived && !c.is_legacy) || null;
  if (!selectedConversation) {
    selectedConversation = await createStudioConversation(bot);
    currentConversations.unshift(selectedConversation);
  }
  if (generation !== studioGeneration) return;
  currentConversationId = selectedConversation.id;
  storageSet(`hutch-conversation:${bot.id}`, currentConversationId);
  const activeRun = selectedConversation.active_run_id ? {
    id: selectedConversation.active_run_id, status: selectedConversation.active_run_status,
    status_label: selectedConversation.active_run_status_label,
  } : null;
  currentRunId = activeRun?.id || selectedConversation.latest_run_id || null;

  const state = botState(detail);
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(bot.name, 30, state === "running" ? "running" : state === "paused" ? "paused" : "")}
      <h1>${esc(bot.name)}</h1>
      <div class="ctx-meta">
        ${bot.paused ? '<span class="tag">paused</span>' : ""}
        ${activeRun ? statusChip(activeRun.status, activeRun.status_label) : ""}
      </div>
    </div>
    <div class="ctx-actions">
      <label class="visually-hidden" for="conversation-switcher">Conversation</label>
      <select class="conversation-select" id="conversation-switcher" aria-label="Conversation">
        ${currentConversations.map(c => `<option value="${esc(c.id)}" ${c.id === currentConversationId ? "selected" : ""}>${c.is_legacy ? "Imported · " : ""}${c.archived ? "Archived · " : ""}${esc(c.title || "New conversation")}</option>`).join("")}
      </select>
      <button class="btn ghost small" id="studio-new-conversation" type="button">${icon("plus")} New</button>
      ${!selectedConversation.is_legacy ? `<button class="btn ghost small" id="studio-archive-conversation" type="button" ${activeRun ? "hidden" : ""}>${selectedConversation.archived ? "Restore" : "Archive"}</button>` : ""}
      <button class="btn ghost small" id="studio-review-run" type="button" ${activeRun?.status === "waiting_approval" ? "" : "hidden"}>${icon("shield")} Review</button>
      <button class="btn danger small" id="studio-stop-run" type="button" data-stop-target="${esc(activeRun?.id || "")}" ${activeRun ? "" : "hidden"}>${icon("stop")} Stop</button>
      <a class="btn ghost small" href="#/bot/${esc(bot.name)}">${icon("sliders")} Settings</a>
    </div>`);

  view.innerHTML = `
    <section class="studio">
      <div class="chat-scroll" id="chat-scroll">
        <div class="feed" id="chat-stream"></div>
      </div>
      <footer class="composer">
        <form id="chat-form" autocomplete="off">
          <div class="composer-box" id="composer-box">
            <div class="composer-row">
              <div class="cmenu-wrap">
                <button class="composer-util" type="button" id="composer-menu-btn" aria-label="Message options" aria-haspopup="dialog" aria-expanded="false" aria-controls="composer-menu">${icon("plus")}</button>
                <div class="cmenu" id="composer-menu" role="dialog" aria-label="Message options" hidden>
                  <p class="cmenu-h">Start from a suggestion</p>
                  <div class="quick-prompts" id="quick-prompts">
                    <button type="button" data-quick="Sort this week's downloads and move invoices into folders">${icon("folder")} Sort downloads</button>
                    <button type="button" data-quick="Research this week's AI news and write a short summary">${icon("fileText")} Research news</button>
                    <button type="button" data-quick="Inspect this repository for TODOs and report findings">${icon("search")} Repo sweep</button>
                  </div>
                  <div class="cmenu-sep"></div>
                  <label class="cmenu-row"><input type="checkbox" id="rehearse-opt">
                    <span>Rehearse this run<span class="cmenu-sub">simulates writes and commands; model calls and reads still happen</span></span></label>
                  <label class="cmenu-row"><input type="checkbox" id="enter-send-setting" checked>
                    <span>Enter sends<span class="cmenu-sub">off: Enter adds a newline, use the send button</span></span></label>
                  <div class="cmenu-sep"></div>
                  <div class="cmenu-facts">${budgetMeterHtml(detail)}
                    <span class="mono">${esc(detail.limits?.max_steps ?? "?")} steps max · ${esc((detail.tools || []).join(", ") || "no tools")}</span>
                  </div>
                </div>
              </div>
              <label class="visually-hidden" for="chat-prompt">Message ${esc(bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message ${esc(bot.name)}…" aria-describedby="chat-help"></textarea>
              <div class="composer-actions">
                <span class="model-switch-slot" id="model-switch-slot"></span>
                <button class="composer-send" id="chat-send" type="submit" aria-label="Send message">${icon("up")}</button>
              </div>
            </div>
            <div class="composer-strip" id="rehearse-flag" hidden>${icon("shield")} <b>Rehearsal</b> — writes and commands are simulated; model calls and reads still happen.</div>
          </div>
          <p class="visually-hidden" id="chat-help">Enter sends, Shift+Enter adds a newline. Your draft is kept for this bot if you navigate away.</p>
        </form>
      </footer>
    </section>`;

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

  // wire composer
  const form = $("#chat-form"), txt = $("#chat-prompt"), sendBtn = $("#chat-send");
  const box = $("#composer-box");
  const switcher = window.hutchModelSwitcher?.mount($("#model-switch-slot"), detail);
  if (selectedConversation.archived) {
    txt.disabled = true;
    txt.placeholder = "This conversation is archived. Start a new one to continue.";
    sendBtn.disabled = true;
  }

  const composerConversationId = selectedConversation.id;
  const composerDraftId = `${bot.name}:${composerConversationId}`;
  txt.value = loadDraft(composerDraftId);
  const autogrow = () => { txt.style.height = "auto"; txt.style.height = Math.min(txt.scrollHeight, 220) + "px"; };
  autogrow();
  txt.addEventListener("input", () => {
    autogrow();
    saveDraft(composerDraftId, txt.value);
  });
  const enterSends = () => $("#enter-send-setting").checked;
  $("#enter-send-setting").checked = store$.get(`hutch:enter-send:${bot.name}`, !matchMedia("(pointer: coarse)").matches);
  $("#enter-send-setting").addEventListener("change", ev => {
    store$.set(`hutch:enter-send:${bot.name}`, ev.target.checked);
  });

  let inflight = false;
  const rehearseOpt = $("#rehearse-opt"), rflag = $("#rehearse-flag");
  rehearseOpt?.addEventListener("change", () => { rflag.hidden = !rehearseOpt.checked; });
  const submit = async () => {
    const text = txt.value.trim();
    if (!text || inflight) return;
    inflight = true;
    box.classList.remove("has-error");
    sendBtn.disabled = true;
    sendBtn.classList.add("sending");
    sendBtn.innerHTML = '<span class="spinner"></span>';
    sendBtn.setAttribute("aria-label", "Sending…");
    const snapshot = txt.value;
    lastPrompt = text;
    try {
      const body = { prompt: text, rehearse: !!rehearseOpt?.checked, model: switcher?.selected() || null };
      const key = await messageIdempotencyKey(composerConversationId, body);
      const r = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(composerConversationId, key);
      const titleOption = conversationSwitcher?.selectedOptions?.[0];
      if (titleOption && titleOption.textContent.trim().endsWith("New conversation")) {
        titleOption.textContent = text.slice(0, 72);
      }
      toast(body.rehearse ? "Rehearsal started — model calls and reads still happen."
        : (ACTIVE.has(r.status) && activeRun ? "Sent — queued behind the current run." : "Sent."));
      if (generation !== studioGeneration) { if (loadDraft(composerDraftId) === snapshot) saveDraft(composerDraftId, ""); return; }
      currentRunId = r.id;
      // Clear only the submitted revision; anything typed since stays put.
      if (txt.value === snapshot) { txt.value = ""; saveDraft(composerDraftId, ""); autogrow(); }
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
      sendBtn.innerHTML = icon("up");
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
    saveDraft(composerDraftId, txt.value);
    autogrow(); txt.focus();
    setMenu(false);
  });

  // composer "+" menu: popover with rehearse, Enter behaviour, and live budget
  const menu = $("#composer-menu"), menuBtn = $("#composer-menu-btn");
  const setMenu = open => {
    menu.hidden = !open;
    menuBtn.setAttribute("aria-expanded", String(open));
    if (open) $("input, button", menu)?.focus();
  };
  menuBtn.addEventListener("click", () => setMenu(menu.hidden));
  menu.parentElement.addEventListener("focusout", ev => {
    if (ev.relatedTarget && !menu.parentElement.contains(ev.relatedTarget)) setMenu(false);
  });
  if (window.__cmenuDoc) document.removeEventListener("click", window.__cmenuDoc);
  window.__cmenuDoc = ev => { if (!menu.hidden && !ev.target.closest(".cmenu-wrap")) setMenu(false); };
  document.addEventListener("click", window.__cmenuDoc);
  box.addEventListener("keydown", ev => {
    if (ev.key === "Escape" && !menu.hidden) { ev.stopPropagation(); setMenu(false); menuBtn.focus(); }
  });
  $("#studio-stop-run").onclick = ev => requestStop(ev.currentTarget.dataset.stopTarget, ev.currentTarget);
  $("#studio-review-run").onclick = () => {
    const id = $("#studio-stop-run").dataset.stopTarget;
    const thread = $$("#chat-stream [data-run-id]").find(e => e.dataset.runId === id);
    const card = thread?.querySelector("[data-approval-card]");
    if (card) {
      card.scrollIntoView({ block: "center", behavior: "instant" });
      card.querySelector("summary, button")?.focus({ preventScroll: true });
    } else $("#needs-you-open")?.click();
  };

  feedMode = "studio";
  if (activeRun) subscribeRun(activeRun.id);   // stream brings events; first paint below
  await renderChatFeed();
}

async function requestStop(runId, button) {
  if (!runId || button?.disabled) return;
  if (button) button.disabled = true;
  try {
    const key = await messageIdempotencyKey(`stop:${runId}`, {});
    await api(`/v1/tasks/runs/${encodeURIComponent(runId)}/stop`, { method: "POST", headers: { "Idempotency-Key": key }, body: {} });
    toast("Stop requested — already-finished steps are not undone.");
    scheduleFeedRender();
  } catch (err) {
    if (button) button.disabled = false;
    toast(`Stop not confirmed: ${err.message}`, true);
  }
}

function syncStudioRunControls(run) {
  if (feedMode !== "studio" || !$("#conversation-switcher")) return;
  const active = run && isActiveStatus(run.status, run.terminal);
  const stop = $("#studio-stop-run");
  if (stop) {
    stop.dataset.stopTarget = active ? run.id : "";
    stop.hidden = !active;
    stop.disabled = run?.status === "cancelling";
    stop.innerHTML = `${icon("stop")} ${run?.status === "cancelling" ? "Stopping" : "Stop"}`;
  }
  const archive = $("#studio-archive-conversation");
  if (archive) archive.hidden = !!active;
  const review = $("#studio-review-run");
  if (review) review.hidden = run?.status !== "waiting_approval";
  const meta = $(".ctx-meta");
  if (meta) meta.innerHTML = active ? statusChip(run.status, run.status_label) : "";
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

let runStream = null, statusTimer = null, renderTimer = null, subRunId = null, feedRefreshPending = false;
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

// Messages belong to the selected conversation. Terminal runs are cached;
// the active one re-renders as events arrive.
const terminalRunCache = new Map();

async function renderChatFeed() {
  if (feedMode !== "studio") return;
  const stream = $("#chat-stream");
  const scroll = $("#chat-scroll");
  if (!stream || !scroll || !currentStudioBot) return;

  const conversationId = currentConversationId, generation = studioGeneration;
  const stillCurrent = () => generation === studioGeneration && conversationId === currentConversationId && stream.isConnected;
  let messages, authority, factPage;
  try {
    if (!currentConversationId) return;
    const summary = await api(`/v1/conversations/${encodeURIComponent(conversationId)}?after=0&limit=1`);
    if (!stillCurrent()) return;
    const lastSeq = summary.last_seq || 0;
    const after = Math.max(0, lastSeq - 100);
    const page = await api(`/v1/conversations/${encodeURIComponent(conversationId)}?after=${after}&limit=100`);
    if (!stillCurrent()) return;
    messages = page.messages || [];
    authority = page;
    factPage = await api(`/v1/bots/${encodeURIComponent(currentStudioBot)}/facts?conversation_id=${encodeURIComponent(conversationId)}&limit=20`)
      .catch(error => ({facts:[], error:error.message}));
    if (!stillCurrent()) return;
  } catch { return; }
  if ($("#modal-root .modal-card")) { feedRefreshPending = true; return; }
  const runIds = [...new Set(messages.filter(m => m.role === "user" && m.run_id).map(m => m.run_id))];
  if (authority.active_run_id && !runIds.includes(authority.active_run_id)) runIds.unshift(authority.active_run_id);
  if (!runIds.length) {
    const factUi = captureFactUi(stream);
    stream.innerHTML = welcomeHtml() + factPanelHtml(factPage.facts || [], factPage.error);
    wireWelcome();
    wireFactControls(factPage.facts || [], currentStudioBot);
    $('[data-retry-facts]', stream)?.addEventListener('click', () => scheduleFeedRender());
    restoreFactUi(stream, factUi);
    return;
  }

  const wasNearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 90;

  const shown = runIds.slice(-6);
  // An older live attempt (and its approval) must remain reachable even when
  // later queued messages have pushed it out of the bounded history window.
  if (authority.active_run_id && !shown.includes(authority.active_run_id)) {
    shown.splice(0, shown.length >= 6 ? 1 : 0, authority.active_run_id);
  }
  currentRunId = authority.active_run_id || authority.latest_run_id || null;
  const parts = [];
  for (const runId of shown) {
    let html;
    try {
      if (runId === currentRunId) html = await runBlockHtml(runId);
      else if (terminalRunCache.has(runId)) html = terminalRunCache.get(runId);
      else html = await runBlockHtml(runId);
    } catch {
      html = $$("[data-run-id]", stream).find(e => e.dataset.runId === runId)?.outerHTML || "";
      html += `<p class="feed-refresh-error hint" role="status">Could not refresh this attempt. Retained details may be outdated.
        <button class="btn ghost small" data-retry-feed type="button">Retry</button></p>`;
    }
    parts.push(html);
  }
  if (!stillCurrent()) return;
  if ($("#modal-root .modal-card")) { feedRefreshPending = true; return; }
  const reviewState = new Map($$("[data-approval-card] details", stream).map(d => [d.closest("[data-approval-card]").dataset.approvalCard, d.open]));
  const activityState = new Map($$("[data-run-id] .tool-stream", stream).map(d => [d.closest("[data-run-id]").dataset.runId, d.open]));
  const focused = document.activeElement;
  const focusedApproval = focused?.closest("[data-approval-card]")?.dataset.approvalCard;
  const focusedChoice = focused?.dataset.approve;
  const focusedReceipt = focused?.dataset.receiptReview;
  const focusedFact = focused?.dataset.factReview;
  const factUi = captureFactUi(stream);
  stream.innerHTML = parts.join("") + factPanelHtml(factPage.facts || [], factPage.error);
  $$("[data-approval-card] details", stream).forEach(d => {
    const id = d.closest("[data-approval-card]").dataset.approvalCard;
    if (reviewState.has(id)) d.open = reviewState.get(id);
  });
  $$("[data-run-id] .tool-stream", stream).forEach(d => {
    const id = d.closest("[data-run-id]").dataset.runId;
    if (activityState.has(id)) d.open = activityState.get(id);
  });
  if (focusedApproval && !focused.isConnected) {
    const card = $$("[data-approval-card]", stream).find(c => c.dataset.approvalCard === focusedApproval);
    const target = focusedChoice !== undefined
      ? card && [...card.querySelectorAll("button")].find(b => b.dataset.approve === focusedChoice)
      : card?.querySelector("summary");
    if (target) target.focus({ preventScroll: true });
  }
  if (focusedReceipt && !focused.isConnected) {
    $$('[data-receipt-review]', stream).find(b => b.dataset.receiptReview === focusedReceipt)?.focus({ preventScroll: true });
  }
  if (focusedFact && !focused.isConnected) {
    ($$('[data-fact-review]', stream).find(b => b.dataset.factReview === focusedFact) || $('#chat-prompt'))?.focus({ preventScroll: true });
  }
  restoreFactUi(stream, factUi);
  if (wasNearBottom) scroll.scrollTop = scroll.scrollHeight;

  // The thinking bubble lives in a stable slot AFTER the feed: full re-renders
  // replace the transcript every event batch, and re-inserting the dots would
  // restart their bounce each time. Here the animation runs continuously.
  let slot = $("#typing-slot");
  if (!slot) {
    slot = document.createElement("div");
    slot.id = "typing-slot"; slot.className = "typing-slot"; slot.setAttribute("aria-hidden", "true");
    scroll.appendChild(slot);
  }
  const active = currentRunId ? await api(`/runs/${encodeURIComponent(currentRunId)}`).catch(() =>
    authority.active_run_id ? { id: authority.active_run_id, status: authority.active_run_status,
      status_label: authority.active_run_status_label } : null) : null;
  if (!stillCurrent()) return;
  const thinking = active?.status === "running";
  if (thinking && !slot.innerHTML.trim()) slot.innerHTML = typingHtml();
  if (!thinking) slot.innerHTML = "";
  syncStudioRunControls(active);
  renderAttention();
  if (active && isActiveStatus(active.status, active.terminal)) subscribeRun(active.id);
  else if (active || !authority.active_run_id) stopRunSubs();
  if (active) announceRunLifecycle([active]);

  // The reader's place is sacred: follow the bottom only if they were there.
  let jump = $("#jump-latest");
  if (!wasNearBottom) {
    if (!jump) {
      jump = document.createElement("button");
      jump.id = "jump-latest"; jump.className = "jump-latest"; jump.type = "button";
      jump.innerHTML = `${icon("down")} Jump to latest`;
      scroll.appendChild(jump);
      jump.addEventListener("click", () => { scroll.scrollTop = scroll.scrollHeight; jump.hidden = true; });
    }
    jump.hidden = false;
  } else {
    scroll.scrollTop = scroll.scrollHeight;
    if (jump) jump.hidden = true;
  }

  wireApprovals();
  wireFeedInteractions();
  wireFactControls(factPage.facts || [], currentStudioBot);
  $('[data-retry-facts]', stream)?.addEventListener('click', () => scheduleFeedRender());
  $$("[data-retry-feed]", stream).forEach(button => button.onclick = () => scheduleFeedRender());
  updateTtls();
}

function factScopeLabel(fact) {
  return fact.scope_kind === 'bot' ? "Shared with this bot's chats" : fact.scope_kind === 'legacy'
    ? 'Legacy · scope needs review' : fact.scope_kind === 'run' ? 'This attempt' :
    fact.scope_id === currentConversationId && !location.hash.startsWith('#/bot/') ? 'This chat' : `Chat: ${fact.conversation_title || 'Untitled'}`;
}

const FACT_BUTTONS = [['factReview','[data-fact-review]'], ['factEdit','[data-fact-edit]'],
  ['factArchive','[data-fact-archive]'], ['factHistory','[data-fact-history]']];
function captureFactUi(stream) {
  const focused = document.activeElement;
  const match = stream.contains(focused) && FACT_BUTTONS.find(([field]) => focused.dataset[field]);
  return {focus:match ? [match[0], match[1], focused.dataset[match[0]]] : null,
    expanded:$('.fact-panel details', stream)?.open || false};
}
function restoreFactUi(stream, state) {
  const details = $('.fact-panel details', stream);
  if (details) details.open = state.expanded;
  if (state.focus) {
    const [field, selector, id] = state.focus;
    ($$(selector, stream).find(button => button.dataset[field] === id) || $('#chat-prompt'))?.focus({preventScroll:true});
  }
}

function factCardHtml(fact) {
  return `<article class="fact-card" data-fact-card="${esc(fact.id)}">
    <div class="fact-heading"><strong>${esc(fact.key)}</strong><span class="tag">${fact.status === 'approved' ? 'Reviewed' : fact.status === 'archived' ? 'Archived' : 'Proposed'}</span></div>
    <p class="fact-value">${esc(fact.value)}</p>
    <p class="hint">${esc(factScopeLabel(fact))} · revision ${esc(fact.revision)}${fact.truncated ? ' · truncated; revise before use' : ''}</p>
    <div class="btn-row">${fact.status === 'proposed' ? `<button type="button" class="btn primary small" data-fact-review="${esc(fact.id)}">Review fact</button>` : ''}
      ${fact.status !== 'archived' ? `<button type="button" class="btn ghost small" data-fact-edit="${esc(fact.id)}">Revise</button>
      <button type="button" class="btn ghost small" data-fact-archive="${esc(fact.id)}">Archive fact</button>` : ''}
      <button type="button" class="btn ghost small" data-fact-history="${esc(fact.id)}">Fact history</button></div>
  </article>`;
}

function factPanelHtml(facts, error = '') {
  if (error) return `<p class="hint" role="status">Could not refresh reference facts: ${esc(error)}. <button class="btn ghost small" type="button" data-retry-facts>Retry facts</button></p>`;
  if (!facts.length) return '';
  const proposed = facts.filter(f => f.status === 'proposed'), reviewed = facts.filter(f => f.status === 'approved');
  return `<section class="fact-panel" aria-label="Reference facts">
    <h2>Reference facts</h2><p class="hint">Proposals need review before recall. Reviewed facts may be stale; they grant no tool permission. Memory can be disabled in bot settings.</p>
    ${proposed.map(factCardHtml).join('')}
    ${reviewed.length ? `<details><summary>${reviewed.length} reviewed ${reviewed.length === 1 ? 'fact' : 'facts'} in this window</summary>${reviewed.map(factCardHtml).join('')}</details>` : ''}
    ${facts.length === 20 ? '<p class="hint">Showing 20 facts. Bot settings provide the full paginated inventory.</p>' : ''}</section>`;
}

function refreshFactsAfterChange(botName) {
  if (location.hash.startsWith('#/bot/')) void renderBotDetail(botName);
  else scheduleFeedRender();
}

function wireFactControls(facts, botName) {
  const byId = new Map(facts.map(f => [f.id, f]));
  $$('[data-fact-review]').forEach(button => button.onclick = () => {
    const fact = byId.get(button.dataset.factReview); if (!fact) return;
    const key = newIdempotencyKey();
    openModal({ title: 'Review reference fact', confirmText: 'Use as reference', returnFocus: button,
      bodyHtml: `<p>This records your review of revision ${esc(fact.revision)}. It is not proof of truth or permission to act.</p>
        <strong>${esc(fact.key)}</strong><p class="fact-value">${esc(fact.value)}</p>
        <p class="hint">${esc(factScopeLabel(fact))} · proposed ${esc(fact.updated_at)}</p>
        ${fact.scope_kind !== 'bot' ? `<label class="fact-share"><input id="fact-share" type="checkbox">Share this exact fact with all chats for this bot</label>` : ''}
        ${fact.scope_kind === 'legacy' ? '<p class="hint">Its original chat is unknown. Explicit sharing is required; otherwise archive it or propose a scoped revision.</p>' : ''}
        <p id="fact-review-error" role="status" class="hint"></p>`,
      onConfirm: async () => {
        const share = $('#fact-share')?.checked;
        if (fact.scope_kind === 'legacy' && !share) { $('#fact-review-error').textContent = 'Choose explicit sharing or cancel and archive this legacy fact.'; return false; }
        const confirm = $('#modal-confirm'); confirm.disabled = true;
        try {
          await api(`/v1/bots/${encodeURIComponent(botName)}/facts/${encodeURIComponent(fact.id)}/review`, {
            method: 'POST', headers: {'Idempotency-Key': key}, body: {content_hash: fact.content_hash, action: share ? 'share' : 'approve'}});
          refreshFactsAfterChange(botName); return true;
        } catch (error) { $('#fact-review-error').textContent = `${error.message} Review was not confirmed; keep this dialog to retry or close and refresh.`; return false; }
        finally { if (confirm.isConnected) confirm.disabled = false; }
      } });
  });
  $$('[data-fact-edit]').forEach(button => button.onclick = () => {
    const fact = byId.get(button.dataset.factEdit); if (!fact) return;
    const key = newIdempotencyKey();
    openModal({ title: 'Propose revised fact', confirmText: 'Save proposal', returnFocus: button,
      bodyHtml: `<p>Saving creates an unreviewed proposal. Existing versions and reviews stay in history.</p>
        <label class="field">Key<input id="fact-key" maxlength="120" value="${esc(fact.key)}"></label>
        <label class="field">Reference value<textarea id="fact-value" maxlength="2000">${esc(fact.value)}</textarea></label>
        <p class="hint">${['legacy','run'].includes(fact.scope_kind) ? "This creates a new proposal for all this bot's chats, requiring explicit review before recall. The original remains separately reviewable." : esc(factScopeLabel(fact))} Never save credentials here.</p>
        <p id="fact-edit-error" class="hint" role="status"></p>`,
      onConfirm: async () => {
        const body = {key: $('#fact-key').value, value: $('#fact-value').value,
          conversation_id: fact.scope_kind === 'conversation' ? fact.scope_id : null};
        try {
          await api(`/v1/bots/${encodeURIComponent(botName)}/facts`, {method:'POST', headers:{'Idempotency-Key':key}, body});
          refreshFactsAfterChange(botName); return true;
        } catch (error) { $('#fact-edit-error').textContent = error.message; return false; }
      } });
  });
  $$('[data-fact-archive]').forEach(button => button.onclick = () => {
    const fact = byId.get(button.dataset.factArchive); if (!fact) return;
    const key = newIdempotencyKey();
    openModal({ title:'Archive reference fact', confirmText:'Archive fact', returnFocus:button,
      bodyHtml:`<p>Archive <strong>${esc(fact.key)}</strong>, revision ${esc(fact.revision)} (${esc(factScopeLabel(fact))})?</p>
        <p>It will be excluded from new retrieval. Versions, reviews, previous prompts and backups remain; this is not permanent deletion.</p><p id="fact-archive-error" class="hint" role="status"></p>`,
      onConfirm: async () => {
        try {
          await api(`/v1/bots/${encodeURIComponent(botName)}/facts/${encodeURIComponent(fact.id)}/review`, {
            method:'POST', headers:{'Idempotency-Key':key}, body:{content_hash:fact.content_hash, action:'archive'}});
          refreshFactsAfterChange(botName); return true;
        } catch(error) { $('#fact-archive-error').textContent = error.message; return false; }
      } });
  });
  $$('[data-fact-history]').forEach(button => button.onclick = async () => {
    const fact = byId.get(button.dataset.factHistory); if (!fact) return;
    button.disabled = true;
    try {
      const page = await api(`/v1/bots/${encodeURIComponent(botName)}/facts/${encodeURIComponent(fact.id)}/history?limit=20`);
      openModal({title:'Reference fact history', confirmText:'Close', showCancel:false, returnFocus:button,
        bodyHtml: `<p>Versions and review records are retained. A review records a human decision; it does not prove a fact or authorize an action.</p>
          ${page.facts.map(version => `<article class="fact-card"><strong>Revision ${esc(version.revision)} · ${esc(version.status)}</strong>
            <p class="fact-value">${esc(version.key)}: ${esc(version.value)}</p><p class="hint">${esc(version.source)} · ${esc(version.updated_at)}${version.truncated ? ' · truncated' : ''}</p>
            ${page.reviews.filter(review => review.fact_id === version.id || review.result_id === version.id).map(review => `<p class="hint">${esc(review.action)} · ${esc(review.actor)} · ${esc(review.created_at)}${review.note ? ` · ${esc(review.note)}` : ''}</p>`).join('')}</article>`).join('')}
          ${page.next_offset !== null ? '<p class="hint">Showing the newest 20 revisions. The versioned API provides older pages.</p>' : ''}`});
    } catch(error) { toast(error.message, 'error'); }
    finally { if (button.isConnected) button.disabled = false; }
  });
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
        <div class="hero-agent" id="hero-agent" aria-hidden="true">
          <img class="hero-img" src="/static/agent/f3-p1.webp" alt="" width="160" height="227" decoding="async">
        </div>
        <h2>${esc(b.name)}</h2>
        <p class="hint">${esc(b.description || "No description yet.")}</p>
      </div>
      <div class="welcome-steps">
        <p><b>Start a conversation.</b> Send a task below, or choose an earlier conversation above. Actions that need a decision appear here.</p>

      </div>
      <div class="tpl-gal" id="tpl-gal" hidden>
        <h3 class="tpl-h">Start from a template</h3>
        <div class="tpl-grid" id="tpl-grid"></div>
      </div>
    </div>`;
}

async function wireWelcome() {
  /* Explore-agents gallery: real templates from the API, fetched lazily —
     never seeded. Picking one opens the create dialog with it preselected. */
  try {
    const templates = await api("/bots/templates");
    const grid = $("#tpl-grid"), gal = $("#tpl-gal");
    if (!grid || !templates.length) return;
    grid.innerHTML = templates.slice(0, 6).map((t, i) => {
      const ci = i % ID_COLORS.length;
      const si = hash32(t.name) % ID_HEADS.length;
      const hue = ID_COLORS[ci];
      const tile = `radial-gradient(circle at 50% 64%, rgba(255, 255, 255, 0.26), rgba(255, 255, 255, 0) 62%), linear-gradient(135deg, ${tint(hue, 0.34)}, ${hue} 55%, ${shade(hue, 0.5)})`;
      return `<button class="tpl-card" type="button" data-tpl="${esc(t.name)}">
        <span class="tpl-tile" style="background:${tile}">${avatarFromPair([ci, si], 64)}</span>
        <span class="tpl-name">${esc(t.name)}${icon("arrow", "tpl-go")}</span>
        <span class="tpl-tag">${esc(t.tagline || t.description || "")}</span>
      </button>`;
    }).join("");
    gal.hidden = false;
    grid.addEventListener("click", ev => {
      const card = ev.target.closest("[data-tpl]");
      if (card) promptNewBot(card.dataset.tpl);
    });
  } catch { /* gallery is an enhancement — welcome works without it */ }
}

/* One attempt in a conversation: the prompt bubble, the visible work,
   the answer. Tool activity is a quiet collapsed strip — approvals are never
   hidden inside it. */
async function runBlockHtml(runId) {
  const run = await api(`/runs/${runId}`);
  const events = run.events || [];
  const resolvedMap = new Map();
  for (const e of events) {
    if (e.type === "approval_resolved") resolvedMap.set((e.data || {}).approval_id, e.data || {});
  }
  for (const [id, state] of Object.entries(run.approval_states || {})) {
    if (state.result !== "pending") resolvedMap.set(id, state);
  }
  const items = groupToolItems(pairToolEvents(events));
  const dur = fmtDur((run.finished_at ? new Date(run.finished_at) : Date.now()) - new Date(run.created_at));
  const running = ACTIVE.has(run.status);
  const activityLabel = statusInfo[run.status]?.label || "Status unavailable";
  const anim = seenThreads.has(runId) ? "" : " enter";
  seenThreads.add(runId);

  const steps = [], cards = [];
  items.forEach(item => {
    const html = renderFeedItem(item, runId, resolvedMap);
    (item.kind === "event" && (item.e.type === "approval_request" || item.e.type === "human_needed") ? cards : steps).push(html);
  });

  const message = events.filter(e => e.type === "message" && e.data?.role !== "user").pop();
  const stepCount = events.filter(e => e.type === "tool_call").length;

  const html = `
    <article class="thread${anim}" data-run-id="${esc(runId)}">
      <div class="msg you">
        <div class="bubble">${esc(run.prompt)}</div>
        <span class="stamp">${timeAgo(run.created_at)}${run.origin === "schedule" ? " · scheduled" : ""}</span>
      </div>
      <div class="msg agent">
        <div class="mhead">
          ${botAvatar(run.bot_name || currentStudioBot, 26, run.status === "running" ? "running" : "")}
          <b>${esc(run.bot_name || currentStudioBot)}</b>
          ${statusChip(run.status, run.status_label)}
          ${running ? `<button class="btn ghost small" data-stop-run="${esc(runId)}" ${run.status === "cancelling" ? "disabled" : ""}>${run.status === "cancelling" ? "Stopping" : "Stop"}</button>` : ""}
          <a class="mrun mono" href="#/run/${esc(runId)}" title="${esc(runId)} · ${esc(run.origin || "manual")} · ${dur}">#${esc(runId.slice(4, 12))}</a>
        </div>
        ${cards.join("")}
        ${(run.unknown_actions || []).map(receiptCardHtml).join("")}
        ${(run.reviewed_actions || []).map(receiptCardHtml).join("")}
        ${run.unresolved_action_count > 5 ? `<p class="hint">${run.unresolved_action_count - 5} more action receipts need review. <button class="btn ghost small" data-receipt-queue type="button">Open Needs you</button></p>` : ""}
        ${run.status === "waiting_resources" && run.reason ? `<p class="run-wait">${esc(run.reason)}</p>` : ""}
        ${stepCount || running ? `
        <details class="tool-stream" ${running || stepCount < 4 ? "open" : ""}>
          <summary>${icon("gear")}${running ? esc(activityLabel) : `${stepCount} step${stepCount === 1 ? "" : "s"}`}${stepCount && !running ? ` · ${dur}` : ""} ${icon("caret", "tool-caret")}</summary>
          ${steps.join("")}
        </details>` : ""}
        ${message && message.data?.content ? `<div class="answer">${esc(message.data.content)}</div>` : ""}
        ${run.transcript_mirror?.error || run.transcript_mirror?.worker_error
          ? `<p class="run-notice" role="status">Transcript file needs attention: ${esc(run.transcript_mirror.error || run.transcript_mirror.worker_error)}. Database history remains available.</p>`
          : run.transcript_mirror?.pending ? '<p class="hint" role="status">Transcript file is catching up. History shown here is committed in the database.</p>' : ""}
        ${run.error ? run.status === 'outcome_unknown' && !run.unresolved_action_count && run.reviewed_actions?.length
          ? `<details class="run-notice"><summary>Original execution report</summary><p>${esc(run.error)}</p></details>`
          : `<div class="run-error ${run.status === "stopped" || run.status === "skipped" ? "run-notice" : run.status === "outcome_unknown" ? "run-review" : ""}">${icon("alert")}<span><b>${esc(run.status_label || activityLabel)}:</b> ${esc(run.error)}</span></div>` : ""}
      </div>
    </article>`;
  if (!running) terminalRunCache.set(runId, html.replace('class="thread enter"', 'class="thread"'));
  return html;
}

const seenThreads = new Set();

const receiptOutcomes = { confirmed_done: 'Effect confirmed', confirmed_failed: 'Failure confirmed', not_applied: 'No effect found' };
function receiptCardHtml(action) {
  const report = action.reconciliation;
  return `<section class="receipt-card" data-receipt-card="${esc(action.id)}" ${report ? 'data-receipt-reviewed="true"' : ''}>
    <b>${report ? esc(receiptOutcomes[report.outcome] || report.outcome) + ' · human report' : 'Action outcome needs review'}</b>
    <p>${esc(action.bot_name || '')} · ${esc(action.summary || action.tool)}</p>
    <p class="hint">${report ? 'Original execution status remains unchanged.' : 'This action may already have happened. Check the destination before repeating it.'}</p>
    <div class="btn-row"><button class="btn ghost small" type="button" data-receipt-review="${esc(action.id)}">${report ? 'View recorded outcome' : 'Review action outcome'}</button>
      <a class="btn ghost small" href="#/run/${esc(action.run_id)}">Open attempt</a></div>
  </section>`;
}

async function reviewReceipt(id, trigger) {
  const openedFromQueue = needsYouDialog.open;
  const returnFocus = openedFromQueue ? (wsBtn.offsetParent !== null ? wsBtn : $('#needs-you-open')) : trigger || document.activeElement;
  const route = location.hash;
  if (trigger) trigger.disabled = true;
  let action;
  try { action = await api(`/v1/actions/receipts/${encodeURIComponent(id)}`); }
  catch (err) { toast(`Could not load action: ${err.message}`, 'error'); return; }
  finally { if (trigger?.isConnected) trigger.disabled = false; }
  if (location.hash !== route) return;
  if (needsYouDialog.open) closeNeedsYou();
  const report = action.reconciliation;
  const json = JSON.stringify(action.intent, null, 2);
  const clipped = json.length > 12000;
  let submission = null;
  openModal({
    returnFocus,
    title: report ? 'Recorded action outcome' : 'Check this action’s outcome',
    bodyHtml: `<p>${esc(action.summary || action.tool)}</p>
      <p class="hint">${action.legacy ? 'Legacy receipt: original arguments were not recorded. Check external records; these details cannot establish what was sent.' : 'These are the saved arguments and authority from immediately before execution.'}</p>
      ${!action.intent_valid ? '<p role="alert">Saved intent failed integrity verification. Recording an outcome is unavailable.</p>' : ''}
      <details><summary>Saved action details${clipped ? ' (preview)' : ''}</summary><pre class="receipt-json">${esc(json.slice(0, 12000))}</pre>
        ${clipped ? '<button class="btn ghost small" id="receipt-download" type="button">Download complete intent JSON</button>' : ''}</details>
      ${report ? `<p><b>${esc(receiptOutcomes[report.outcome])} · human report</b></p><p class="receipt-evidence">${esc(report.evidence)}</p>
        <p class="hint">Recorded by ${esc(report.recorded_by)} at ${esc(report.recorded_at)}. This does not change the original receipt, status or transcript.</p>` : `
      <p class="hint">Check the file, account or service involved. This records your findings and runs no action. A new attempt still needs permission.</p>
      <label class="field">Observed outcome<select id="receipt-outcome"><option value="">Select a checked outcome</option>
        <option value="confirmed_done">I confirmed the effect happened</option><option value="confirmed_failed">I confirmed it failed</option>
        <option value="not_applied">I confirmed no effect happened</option></select></label>
      <label class="field">What did you check?<textarea id="receipt-evidence" rows="3" maxlength="4000" placeholder="Record the destination and evidence you checked"></textarea></label>
      <p id="receipt-error" role="alert" hidden></p>`}`,
    confirmText: report || !action.intent_valid ? 'Close' : 'Record checked outcome',
    onConfirm: async () => {
      if (report || !action.intent_valid) return true;
      const error = $('#receipt-error'), button = $('#modal-confirm');
      const body = { intent_hash: action.intent_hash, outcome: $('#receipt-outcome').value, evidence: $('#receipt-evidence').value.trim() };
      if (!body.outcome || !body.evidence) { error.textContent = 'Select an observed outcome and describe what you checked.'; error.hidden = false; return false; }
      // Retain a key for an uncertain response; changing the report uses a new
      // key and the server still resolves this action only once.
      const signature = JSON.stringify(body);
      if (submission?.signature !== signature) submission = { signature, key: newIdempotencyKey() };
      button.disabled = true;
      try {
        await api(`/v1/actions/receipts/${encodeURIComponent(id)}/reconcile`, {
          method: 'POST', body, headers: { 'Idempotency-Key': submission.key },
        });
        terminalRunCache.delete(action.run_id);
        refreshChangedResources(['actions']);
        toast('Your checked outcome was recorded. The original execution history is preserved.');
        return true;
      } catch (err) { error.textContent = `Could not record outcome: ${err.message}. Your report is retained.`; error.hidden = false; return false; }
      finally { if (button.isConnected) button.disabled = false; }
    },
  });
  $('#receipt-download')?.addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${id}-intent.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

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

function toolLineHtml(item, anchorEvent, runId, includeFileAttachments = true) {
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

  return `<div class="tool-line-wrap">
    <div class="tool-line ${cls}" data-tool-line="${esc(String(idx))}">
      <button class="tool-line-head" type="button" aria-expanded="${open}" aria-controls="tlb-${esc(String(idx))}" data-tool-toggle="${esc(String(idx))}">
        <span class="tool-grid" title="${t}">
          <span class="tool-verdict">${verdict}</span>
          <span class="tool-name">${esc(tool)}</span>
          <span class="tool-args">${esc(truncate(summary, 90))}</span>
        </span>
      </button>
      <div class="tool-line-body" id="tlb-${esc(String(idx))}" ${open ? "" : "hidden"}>
        <div class="tool-line-section">
          <span class="tool-line-label">Input</span>
          ${esc(JSON.stringify(call?.d.args ?? {}, null, 2))}
        </div>
        ${res ? artifactDownloadHtml(runId, res.d) : ""}
        ${res ? toolOutputHtml(res.d.output) : '<div class="tool-line-section"><span class="tool-line-label">Output</span>pending…</div>'}
      </div>
    </div>
    ${includeFileAttachments ? createdFilesHtml(runId, [{ result: res }]) : ""}
  </div>`;
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

function artifactDownloadHtml(runId, result) {
  const match = /^artifacts\/([0-9]{3,6}-[a-z0-9_-]{1,40}\.txt)$/.exec(String(result.artifact || ""));
  const digest = String(result.artifact_sha256 || "");
  if (!match || !/^[a-f0-9]{64}$/.test(digest)) return "";
  const bytes = Number(result.artifact_bytes);
  const size = Number.isSafeInteger(bytes) && bytes >= 0 ? ` · ${bytes.toLocaleString()} bytes` : "";
  const href = `/api/v1/tasks/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(match[1])}`;
  return `<div class="tool-line-section artifact-download">
    <span class="tool-line-label">Saved full output</span>
    <a class="btn ghost small" href="${href}" title="The server verifies this file against its recorded SHA-256 before download">Download${size}</a>
    <span class="hint mono">SHA-256 ${esc(digest.slice(0, 16))}…</span>
  </div>`;
}

function createdFilesHtml(runId, items) {
  const files = items.filter(it => it.result?.d?.workspace_file).map(it => it.result.d.workspace_file);
  if (!files.length) return "";
  return `<div class="workspace-file-attachments" role="group" aria-label="Files created in this run">
    ${files.map(file => {
      const match = /^artifacts\/([0-9]{3,6}-[a-z0-9_-]{1,40}\.txt)$/.exec(String(file.artifact || ""));
      const digest = String(file.sha256 || "");
      if (match && /^[a-f0-9]{64}$/.test(digest)) {
        const bytes = Number(file.bytes);
        const size = Number.isSafeInteger(bytes) && bytes >= 0 ? `${bytes.toLocaleString()} bytes` : "text file";
        const name = String(file.name || "file");
        const href = `/api/v1/tasks/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(match[1])}`;
        return `<div class="workspace-file-attachment">
          <span class="workspace-file-label">Created file</span>
          <a class="btn ghost small" href="${href}" title="The server verifies this file against its recorded SHA-256 before download">Download ${esc(name)}</a>
          <span class="workspace-file-meta">${esc(size)} · SHA-256 ${esc(digest.slice(0, 16))}…</span>
        </div>`;
      }
      if (file.error) {
        return `<div class="workspace-file-attachment" role="status">
          <span class="workspace-file-label">Created file</span>
          <span class="workspace-file-meta">Saved in the workspace; download unavailable: ${esc(file.error)}</span>
        </div>`;
      }
      return "";
    }).join("")}
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
        ${item.items.map(it => toolLineHtml(it, it.call?.e ?? it.result.e, runId, false)).join("")}
      </div>
    </div>
    ${createdFilesHtml(runId, item.items)}`;
}

function wireFeedInteractions() {
  const stream = $("#chat-stream");
  if (!stream || stream.dataset.wired === "1") return;
  stream.dataset.wired = "1";
  const runId = currentRunId;
  stream.addEventListener("click", ev => {
    const receipt = ev.target.closest('[data-receipt-review]');
    if (receipt) { void reviewReceipt(receipt.dataset.receiptReview, receipt); return; }
    if (ev.target.closest('[data-receipt-queue]')) { void openNeedsYou(); return; }
    const stop = ev.target.closest("[data-stop-run]");
    if (stop) { requestStop(stop.dataset.stopRun, stop); return; }
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

/* Client expiry disables controls; only a server receipt declares the outcome. */
function updateTtls() {
  $$("[data-deadline]").forEach(el => {
    const ms = Number(el.dataset.deadline) - Date.now();
    if (ms <= 0) {
      const card = el.closest("[data-approval-card]");
      if (card) {
        card.classList.add("expired");
        card.querySelectorAll("[data-approve]").forEach(b => { b.disabled = true; });
        const target = card.querySelector("[data-ttl-text]");
        if (target) target.textContent = "Expired — checking decision";
      }
      return;
    }
    el.classList.remove("expired");
    const target = el.querySelector("[data-ttl-text]");
    if (!target) return;
    const ttlEl = el.querySelector(".ttl-countdown");
    if (ttlEl) ttlEl.classList.toggle("urgent", ms < 120_000);   // amber only as it nears expiry
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
  const contextHref = a.conversation_id ? `#/conversation/${encodeURIComponent(a.conversation_id)}` : `#/run/${encodeURIComponent(runId)}`;

  const rows = [
    ["Tool", tool],
    a.account ? ["Account", a.account] : null,
    a.destination ? ["Destination", a.destination] : null,
    a.revision ? ["Revision", a.revision] : null,
    rule ? ["Why you are asked", rule] : null,
    ["Effect", outward
      ? "Sends data out of this machine — Stop cannot recall it once it has gone"
      : "Check the exact arguments below. Changes may need manual undo."],
  ].filter(Boolean).map(([k, v]) =>
    `<div class="review-row"><span class="review-key">${esc(k)}</span><span>${esc(v)}</span></div>`).join("");

  return `
    <div class="approval-card-chat risk-${esc(risk)} ${outward ? "outward" : ""} ${expired ? "expired" : ""}"
         data-approval-card="${esc(id)}" data-action-hash="${esc(a.action_hash || "")}" ${deadline ? `data-deadline="${deadline}"` : ""}>
      <div class="approval-badge-bar">
        <div class="approval-head-left">
          <span class="chip">${icon("shield")} Approval required</span>
          ${botName ? `<b class="approval-bot">${esc(botName)}</b>` : ""}
          ${tool ? `<span class="tag">${esc(tool)}</span>` : ""}
          <span class="tag ${risk === "high" ? "danger" : ""}">${esc(risk)} risk</span>
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
        ${detail ? `<span class="review-label">Raw request</span><pre class="approval-detail" tabindex="0" aria-label="Exact request arguments">${esc(detail)}</pre>` : ""}
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
        ${runId ? `<a class="btn ghost small" href="${esc(contextHref)}">${a.conversation_id ? "Open conversation" : "Open run"}</a>` : ""}
      </div>
    </div>`;
}

// Server-authoritative resolution: names who decided and when, so two devices
// racing to answer agree rather than diverge.
function approvalResolvedHtml(a, outcome, botName = "") {
  const labels = {
    approved: "Approved", denied: "Denied",
    expired: a.decided_by === "stopped" ? "Cancelled with this run"
      : a.decided_by === "owner_expired" ? "Expired — execution lost ownership"
      : a.decided_by === "timeout" ? "Expired — no decision in time" : "Expired — not approved",
    missing: "No longer exists",
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

function replaceApprovalCard(card, html) {
  if (!card?.isConnected) return;
  const restore = card.contains(document.activeElement);
  const template = document.createElement("template");
  template.innerHTML = html;
  const replacement = template.content.firstElementChild;
  card.replaceWith(replacement);
  if (restore) { replacement.tabIndex = -1; replacement.focus(); }
}

async function resolveApproval(id, choice, card) {
  const always = choice === "always";
  const approve = choice === "1" || always;
  const action = card?.querySelector(".approval-action-text")?.textContent || "";
  card?.querySelectorAll("button").forEach(b => { b.disabled = true; });   // no double-submit
  try {
    let actionHash = card?.dataset.actionHash;
    if (approve && !actionHash) {
      const persisted = await api(`/approvals/${encodeURIComponent(id)}`);
      if (persisted.status !== "pending") throw new Error(`Already ${persisted.status}`);
      actionHash = persisted.action_hash;
      // A historical transcript without a hash must be reviewed from the current resource.
      if (card) card.outerHTML = approvalCardHtml(persisted, { botName: persisted.bot_name });
      wireApprovals();
      toast("Request refreshed. Review its current details before deciding.");
      return;
    }
    const body = approve ? { always, action_hash: actionHash } : {};
    const key = await messageIdempotencyKey(`approval:${id}`, { choice, ...body });
    await api(`/v1/actions/approvals/${encodeURIComponent(id)}/${approve ? "approve" : "deny"}`, {
      method: "POST", headers: { "Idempotency-Key": key }, body,
    });
    toast(approve ? (always ? "Allowed — remembered for this bot" : "Allowed once") : "Denied");
    replaceApprovalCard(card, approvalResolvedHtml({ approval_id: id, action }, approve ? "approved" : "denied"));
    scheduleFeedRender();
  } catch (err) {
    let current = null;
    let unavailable = false;
    try { current = await api(`/approvals/${encodeURIComponent(id)}`); } catch (checkError) { unavailable = !checkError.message.startsWith("no such approval"); }
    if (current && current.status && current.status !== "pending") {
      replaceApprovalCard(card, approvalResolvedHtml({ ...current, approval_id: id }, current.status, current.bot_name || ""));
      toast(`Already ${current.status}${current.decided_by ? ` by ${current.decided_by}` : ""} — nothing changed.`);
    } else if (!current && !unavailable) {
      replaceApprovalCard(card, approvalResolvedHtml({ approval_id: id, action }, "missing"));
      toast("This request no longer exists — it may have been replaced.", true);
    } else {
      card?.querySelectorAll("button").forEach(b => { b.disabled = false; });
      toast(err.message || "Could not resolve approval", true);
    }
  }
  refreshBadge();
  if (needsYouDialog.open) await refreshApprovals();
}

function renderChatEvent(e, resolvedMap) {
  const t = e.ts ? e.ts.slice(11, 19) : "";
  const d = e.data || {};
  switch (e.type) {
    case "approval_request": {
      const id = d.approval_id || d.id;
      const done = resolvedMap?.get(id);
      if (done) {   // canonical decisions survive a crash before the worker's response event
        const outcome = done.result === "approved" ? "approved"
          : String(done.result).startsWith("expired") ? "expired" : "denied";
        return approvalResolvedHtml({ ...d, approval_id: id, decided_by: done.by || "", resolved_at: done.resolved_at || "" }, outcome);
      }
      const deadline = d.expires_at ? new Date(d.expires_at).getTime()
        : (e.ts ? new Date(e.ts).getTime() + 10 * 60 * 1000 : 0);
      return approvalCardHtml({ ...d, deadline, run_id: e.run_id || currentRunId },
        { botName: currentStudioBot || "" });
    }
    case "human_needed":
      return `<div class="run-cause"><b>${icon("alert")} Needs a person:</b> ${esc(d.reason || d.note || "A login, CAPTCHA, or 2FA step is waiting.")} ${
        d.handoff ? `<br><span class="hint">${esc(d.handoff)}</span>` : ""}</div>`;
    case "log": {
      const note = (d.note || d.message || "").trim();
      if (!note) return "";   // empty log notes must not leave an orphan row
      return `<div class="tool-line"><div class="tool-grid tool-log"><span class="tool-verdict"></span><span class="tool-args">${esc(truncate(note, 140))}</span></div></div>`;
    }
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
  setTopContext(`<div class="ctx-id"><h1>Activity</h1></div>`);
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
        <div class="kpi"><span class="kpi-label">Reported tokens today</span><span class="kpi-val">${fmt(s.tokens_today)}</span></div>
        <div class="kpi"><span class="kpi-label">Recorded cost today</span><span class="kpi-val">$${Number(s.spend_today || 0).toFixed(2)}</span></div>
      </div>
      <div class="ov-grid">
        <section class="ov-col loud">
          <h2 class="ov-h">${icon("inbox")} Needs you <span class="count">${o.needs_count}</span></h2>
          ${!o.needs_count ? `<div class="empty-state">${icon("check", "icon-lg")}<p>Nothing needs you.</p></div>` : ""}
          ${(o.approvals || []).map(a => `
            <a class="ov-approval" href="#/approvals">
              <span class="ov-approval-head"><b>${esc(a.bot_name)}</b> <span class="tag">${esc(a.tool)}</span> <span class="tag ${a.risk === "high" ? "danger" : ""}">${esc(a.risk)} risk</span></span>
              <span class="ov-approval-action">${esc(a.action)}</span>
            </a>`).join("")}
          ${(o.humans || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
          ${(o.failures || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
        </section>
        <section class="ov-col">
          <h2 class="ov-h">${icon("play")} In progress <span class="count">${(o.running || []).length}</span></h2>
          ${(o.running || []).length ? (o.running || []).map(row).join("") : `<div class="empty-state"><p>No work in progress.</p></div>`}
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
  const bots = await api("/bots");
  botsCache = bots;
  if (bots.length < 10) {
    history.replaceState(null, "", "#/chat");
    await renderChatStudio();
    return;
  }
  renderRoster();
  setTopContext(`<div class="ctx-id"><h1>Fleet</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-new-bot-top">${icon("plus")} New bot</button></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      ${bots.length ? `
      <div class="fleet-filters"><label class="field">Find a bot<input id="fleet-search" type="search" placeholder="Name, description or model"></label>
        <label class="field">Show<select id="fleet-state"><option value="all">All bots</option><option value="needs">Needs you</option><option value="active">In progress</option><option value="paused">Paused</option></select></label></div>
      <p class="hint" id="fleet-count" role="status"></p>
      <div class="bot-grid">
        ${bots.map(b => `
          <article class="bot-card" data-fleet-bot="${esc(b.name)}">
            <div class="bot-head">
              ${botAvatar(b.name, 32, botState(b) === "running" ? "running" : b.paused ? "paused" : "")}
              <span class="bot-name">${esc(b.name)}</span>
              ${b.active_run_id ? statusChip(b.active_run_status, b.active_run_status_label) : `<span class="tag">${esc(botStatusLabel(b))}</span>`}
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
  const filterFleet = () => {
    const q = $("#fleet-search").value.trim().toLowerCase(), state = $("#fleet-state").value;
    let visible = 0;
    $$("[data-fleet-bot]").forEach(card => {
      const b = bots.find(x => x.name === card.dataset.fleetBot);
      const match = `${b.name} ${b.description || ""} ${b.model || ""}`.toLowerCase().includes(q)
        && (state === "all" || state === "needs" && botNeedsYou(b)
          || state === "active" && b.active_run_id || state === "paused" && b.paused);
      card.hidden = !match;
      if (match) visible++;
    });
    $("#fleet-count").textContent = `${visible} of ${bots.length} bots`;
  };
  $("#fleet-search")?.addEventListener("input", filterFleet);
  $("#fleet-state")?.addEventListener("change", filterFleet);
  if ($("#fleet-search")) filterFleet();
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

let approvalsTimer = null, approvalSignature = "", needsYouReturnFocus = null, approvalOffset = 0;
const APPROVAL_PAGE_SIZE = 50;
const needsYouDialog = $("#needs-you");

async function openNeedsYou() {
  needsYouReturnFocus = wsEl.classList.contains("open") ? wsBtn : document.activeElement;
  closeWorkspace();
  if (!needsYouDialog.open) needsYouDialog.showModal();
  $("#needs-you-close").focus();
  renderAttention();
  await refreshApprovals();
  clearInterval(approvalsTimer);
  approvalsTimer = setInterval(refreshApprovals, 5000);
}

function closeNeedsYou() {
  clearInterval(approvalsTimer);
  approvalsTimer = null;
  needsYouDialog.close();
  if (needsYouReturnFocus?.isConnected) needsYouReturnFocus.focus();
  renderAttention();
}

$("#needs-you-open").addEventListener("click", openNeedsYou);
$("#needs-you-close").addEventListener("click", closeNeedsYou);
needsYouDialog.addEventListener("cancel", ev => { ev.preventDefault(); closeNeedsYou(); });
needsYouDialog.addEventListener("click", ev => {
  if (ev.target.closest("a[href]")) closeNeedsYou();
});

// Existing bookmarks open the queue over Studio, without trapping browser Back.
async function renderApprovals() {
  history.replaceState(null, "", "#/chat");
  await renderChatStudio();
  await openNeedsYou();
}

let receiptOffset = 0;
const RECEIPT_PAGE_SIZE = 20;

async function refreshApprovals() {
  if (!needsYouDialog.open) return;
  const error = $("#needs-you-error");
  const offset = approvalOffset;
  try {
    const receiptPageOffset = receiptOffset;
    const [pending, resolved, stats, receipts] = await Promise.all([
      api(`/v1/actions/approvals?limit=${APPROVAL_PAGE_SIZE}&offset=${offset}`),
      api("/v1/actions/approvals?status=resolved&limit=8"), api("/stats"),
      api(`/v1/actions/receipts?unresolved=true&limit=${RECEIPT_PAGE_SIZE}&offset=${receiptPageOffset}`),
    ]);
    if (!needsYouDialog.open || offset !== approvalOffset || receiptPageOffset !== receiptOffset) return;
    if (!pending.length && offset) { approvalOffset = 0; return refreshApprovals(); }
    if (!receipts.length && receiptPageOffset) { receiptOffset = 0; return refreshApprovals(); }
    error.hidden = true;
    const signature = JSON.stringify([pending, resolved, offset, stats.pending_approvals, receipts, receiptPageOffset, stats.unresolved_actions]);
    // Preserve keyboard focus and expanded review details during unchanged polls.
    if (signature === approvalSignature) return;
    approvalSignature = signature;
    const focus = document.activeElement;
    const focusedCard = focus?.closest("[data-approval-card]");
    const focusChoice = focus?.dataset.approve;
    const focusReceipt = focus?.dataset.receiptReview;
    const expanded = new Set($$("#needs-you [data-approval-card]").filter(c => c.querySelector("details[open]"))
      .map(c => c.dataset.approvalCard));
    $("#approvals-pending").innerHTML = pending.length
      ? pending.map(a => approvalCardHtml(a, { botName: a.bot_name })).join("")
      : `<div class="empty-state">${icon("check", "icon-lg")}<p>No pending approvals.</p><p class="hint">Requests appear in their conversation and here.</p></div>`;
    const total = stats.pending_approvals;
    $("#approvals-pagination").innerHTML = total ? `<span class="hint">${offset + 1}–${offset + pending.length} of ${total} requests</span>
      ${offset ? '<button class="btn ghost small" id="approvals-prev">Previous</button>' : ""}
      ${offset + pending.length < total ? '<button class="btn ghost small" id="approvals-next">Next</button>' : ""}` : "";
    $("#approvals-prev")?.addEventListener("click", () => { approvalOffset = Math.max(0, offset - APPROVAL_PAGE_SIZE); refreshApprovals(); });
    $("#approvals-next")?.addEventListener("click", () => { approvalOffset = offset + APPROVAL_PAGE_SIZE; refreshApprovals(); });
    $("#approvals-resolved").innerHTML = resolved.length
      ? resolved.map(a => approvalResolvedHtml(a, a.status, a.bot_name)).join("")
      : `<p class="hint">No recent decisions.</p>`;
    $('#receipts-pending').innerHTML = receipts.length ? receipts.map(receiptCardHtml).join('') : '<p class="hint">No uncertain action receipts.</p>';
    $('#receipts-pagination').innerHTML = receipts.length ? `<span class="hint">${receiptPageOffset + 1}–${receiptPageOffset + receipts.length} of ${stats.unresolved_actions} actions</span>
      ${receiptPageOffset ? '<button class="btn ghost small" id="receipts-prev">Previous actions</button>' : ''}
      ${receiptPageOffset + receipts.length < stats.unresolved_actions ? '<button class="btn ghost small" id="receipts-next">Next actions</button>' : ''}` : '';
    $('#receipts-prev')?.addEventListener('click', () => { receiptOffset = Math.max(0, receiptPageOffset - RECEIPT_PAGE_SIZE); void refreshApprovals(); });
    $('#receipts-next')?.addEventListener('click', () => { receiptOffset = receiptPageOffset + RECEIPT_PAGE_SIZE; void refreshApprovals(); });
    $$('#receipts-pending [data-receipt-review]').forEach(button => button.addEventListener('click', () => void reviewReceipt(button.dataset.receiptReview, button)));
    $$("#needs-you [data-approval-card]").forEach(c => {
      if (expanded.has(c.dataset.approvalCard) && c.querySelector("details")) c.querySelector("details").open = true;
    });
    if (focusedCard) {
      const replacement = $$("#needs-you [data-approval-card]").find(c => c.dataset.approvalCard === focusedCard.dataset.approvalCard);
      const button = replacement && [...replacement.querySelectorAll("button")].find(b => b.dataset.approve === focusChoice);
      (button || $("#needs-you-close")).focus();
    }
    if (focusReceipt) ($$('#receipts-pending [data-receipt-review]').find(b => b.dataset.receiptReview === focusReceipt) || $('#needs-you-close')).focus();
    wireApprovals();
    updateTtls();
  } catch (err) {
    if (!needsYouDialog.open) return;
    error.hidden = false;
    error.innerHTML = `<p>Could not refresh requests: ${esc(err.message)}. Displayed requests may be outdated.</p><button class="btn ghost small" id="needs-you-retry">Retry</button>`;
    $("#needs-you-retry").addEventListener("click", refreshApprovals);
  }
}

/* -------------------------------------------------------- bot settings */

async function renderBotDetail(name, factOffset = 0, showArchivedFacts = false) {
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  const factsPage = await api(`/v1/bots/${encodeURIComponent(name)}/facts?all_scopes=true&limit=20&offset=${factOffset}&include_archived=${showArchivedFacts}`);
  let offlineCapability = { status: "unavailable", reason: "Host isolation could not be verified." };
  let browserHandoffCapability = { status: "unavailable", reason: "The server could not verify this host's display and browser support." };
  try {
    const capabilities = await api("/v1/capabilities");
    offlineCapability = capabilities.find(capability => capability.id === "strict_offline") || offlineCapability;
    browserHandoffCapability = capabilities.find(capability => capability.id === "browser_handoff") || browserHandoffCapability;
  } catch { /* host-dependent options remain unavailable unless capabilities are verified */ }
  const offlineReady = ["supported", "experimental"].includes(offlineCapability.status);
  const offlineLabel = offlineCapability.status === "experimental"
    ? "Strict offline · experimental"
    : offlineReady ? "Strict offline · verified on this host" : "Strict offline · unavailable on this host";
  const offlineDisabled = !offlineReady ? "disabled" : "";
  const offlineReason = offlineReady
    ? "Hutch verified that the isolated worker cannot reach tested host TCP listeners and sees only its own processes; configured model traffic uses a private per-run Unix-socket broker. Browser and web tools are removed, and shell requires the strict sandbox. The separate model service itself may still use the network."
    : `Hutch could not verify worker network isolation (${offlineCapability.reason}). Local model routes alone do not make a run offline; the separate model service may still use the network.`;
  const handoffReason = ["supported", "experimental"].includes(browserHandoffCapability.status)
    ? "Local browser handoff is experimental on this host. A login wait keeps the same browser window open and pauses automation. Only one Hutch handoff can run at a time. This does not enable phone control."
    : `Local browser handoff is unavailable on this host: ${browserHandoffCapability.reason}. It will fail closed until its display and browser prerequisites are available. This does not enable phone control.`;
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(b.name, 30)}
      <h1>${esc(b.name)} settings</h1>
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
      <p class="crumb"><a href="#/chat/${esc(b.name)}">Studio</a> / Settings</p>
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

          <div class="panel" id="idp-panel">
            <div class="panel-title">Identity</div>
            ${identityPickerHtml()}
            <p class="hint" style="text-align:center;margin-top:8px;">Chosen immediately — the roster updates everywhere.</p>
          </div>

          <form class="panel form-grid" id="form-model">
            <div class="panel-title">Model &amp; connection</div>
            <div class="form-grid row2">
              <label class="field">Default model
                <input type="text" name="model" value="${esc(b.model || "")}">
                <span class="hint">Hybrid allows local and hosted routes; Local blocks hosted models but keeps tools online. Offline requires a host that verifies worker network isolation.</span>
              </label>
              <label class="field">Runtime
                <input type="text" disabled value="${esc(b.runtime || "builtin")}">
              </label>
            </div>
            <label class="field">Model routing
              <select name="inference_mode" aria-describedby="inference-mode-help">
                <option value="hybrid" ${(b.inference_mode || "hybrid") === "hybrid" ? "selected" : ""}>Hybrid · local and hosted routes</option>
                <option value="local" ${b.inference_mode === "local" ? "selected" : ""}>Local model routes only</option>
                <option value="offline" ${b.inference_mode === "offline" ? "selected" : ""} ${offlineDisabled}>${offlineLabel}</option>
              </select>
              <span class="hint" id="inference-mode-help">${esc(offlineReason)}</span>
            </label>
            <div class="btn-row"><button class="btn primary small" type="submit">Save model settings</button></div>
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
            <label class="field workspace-mode-field">Workspace
              <select name="workspace_mode" aria-describedby="workspace-mode-help">
                <option value="fresh" ${(b.workspace_mode || (b.workdir ? "folder" : "fresh")) === "fresh" ? "selected" : ""}>Fresh each run</option>
                <option value="managed" ${b.workspace_mode === "managed" ? "selected" : ""}>Hutch-managed</option>
                <option value="folder" ${b.workspace_mode === "folder" ? "selected" : ""}>Existing folder</option>
              </select>
              <span class="hint" id="workspace-mode-help">Fresh starts each run in a new folder. Managed reuses one private folder for this bot’s runs and chats. Folder uses the existing path below. Changing modes never moves or deletes files; deleting a bot keeps its managed folder.</span>
            </label>
            <label class="field workspace-folder-field" id="workspace-folder-field" ${b.workspace_mode === "folder" ? "" : "hidden"}>Existing folder
              <input type="text" name="workdir" value="${esc(b.workdir || "")}" placeholder="absolute path, for example ~/Projects/report" ${b.workspace_mode === "folder" ? "required" : ""}>
              <span class="hint">Choose a folder that already exists. System folders, your whole home, and Hutch’s private state are refused.</span>
            </label>
            <label class="field browser-handoff-field">Local browser handoff
              <select name="local_browser_handoff" aria-describedby="browser-handoff-help">
                <option value="false" ${b.local_browser_handoff ? "" : "selected"}>Off - browser stays headless</option>
                <option value="true" ${b.local_browser_handoff ? "selected" : ""}>On - visible Linux desktop window</option>
              </select>
              <span class="hint" id="browser-handoff-help">${esc(handoffReason)}</span>
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
            <div class="panel-title">Reference facts (${b.memory_count})</div>
            <p class="hint">${b.memory_enabled ? 'Runtime memory is enabled. Proposals require human review before recall.' : 'Runtime memory is disabled. Saved records remain manageable here.'} Review records are reference data, not tool permission. Never save credentials.</p>
            <button class="btn ghost small" id="memory-toggle" type="button">${b.memory_enabled ? 'Disable' : 'Enable'} memory</button>
            <button class="btn ghost small" id="memory-archives" type="button">${showArchivedFacts ? 'Hide' : 'Show'} archived facts</button>
            ${factsPage.facts.map(factCardHtml).join('') || `<p class="empty-inline">No active facts in this window.</p>`}
            <div class="btn-row"><button class="btn ghost small" id="facts-previous" type="button" ${factOffset ? '' : 'disabled'}>Previous facts</button>
              <span class="hint">${factsPage.facts.length ? `${factOffset + 1}–${factOffset + factsPage.facts.length}` : 'No facts in this window'}</span>
              <button class="btn ghost small" id="facts-next" type="button" ${factsPage.next_offset === null ? 'disabled' : ''}>Next facts</button></div>
          </div>

          <div class="panel">
            <div class="panel-title">Standing permissions (${b.sticky_allows.length})</div>
            ${b.sticky_allows.map(s => `
              <div class="allow-item"><code>${esc(s)}</code>
                <button class="chip-del" aria-label="Revoke ${esc(s)}" data-revoke-sticky="${esc(s)}">${icon("x")}</button>
              </div>`).join("") || `<p class="empty-inline">None — every risky command asks.</p>`}
          </div>

<p><a href="#/runs?q=${encodeURIComponent(b.name)}">View this bot’s run history</a></p>
        </div>
      </div>
    </div></div>`;

  // wiring
  mountIdentityPicker($("#idp-panel"), b.name, pair => { sigilSet(b.name, pair); refreshRoster(); });
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
    const fd = new FormData(ev.target);
    patch({ model: fd.get("model").trim(), inference_mode: fd.get("inference_mode") }, "Model settings saved.");
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
    patch({ approval_mode: fd.get("approval_mode"), risk_tier: fd.get("risk_tier"),
      workspace_mode: fd.get("workspace_mode"), workdir: fd.get("workdir").trim(),
      local_browser_handoff: fd.get("local_browser_handoff") === "true" }, "Policy and workspace saved.");
  });
  $('#form-risk [name="workspace_mode"]').addEventListener("change", ev => {
    const folder = ev.target.value === "folder";
    const field = $("#workspace-folder-field");
    field.hidden = !folder;
    const input = field.querySelector("input");
    input.required = folder;
    if (folder) input.focus();
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
  wireFactControls(factsPage.facts, b.name);
  $('#memory-toggle').onclick = () => patch({memory_enabled: !b.memory_enabled}, `Memory ${b.memory_enabled ? 'disabled' : 'enabled'}.`);
  $('#memory-archives').onclick = () => renderBotDetail(name, 0, !showArchivedFacts);
  $('#facts-previous').onclick = () => renderBotDetail(name, Math.max(0, factOffset - 20), showArchivedFacts);
  $('#facts-next').onclick = () => renderBotDetail(name, factsPage.next_offset, showArchivedFacts);
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
    location.hash = "#/chat";
    refreshRoster();
  });
  wireCommon();
}

/* ------------------------------------------------------------- run detail */

async function renderRunDetail(runId) {
  const generation = studioGeneration;
  const stillCurrent = () => generation === studioGeneration && location.hash === `#/run/${runId}`;
  feedMode = "run";
  const r = await api(`/runs/${runId}`);
  if (!stillCurrent()) return;
  currentStudioBot = r.bot_name;
  currentRunId = runId;
  setTopContext(`
    <div class="ctx-id"><h1>Run <span class="mono">#${esc(runId.slice(0, 12))}</span></h1>
      <div class="ctx-meta">${statusChip(r.status, r.status_label)}</div></div>
    <div class="ctx-actions">
      ${ACTIVE.has(r.status) ? `<button class="btn danger small" id="stop-this-run" ${r.status === "cancelling" ? "disabled" : ""}>${icon("stop")} ${r.status === "cancelling" ? "Stopping" : "Stop"}</button>` : ""}
      <a class="btn ghost small" href="#/runs">${icon("arrowLeft")} All runs</a>
    </div>`);
  const steps = (r.events || []).filter(e => e.type === "step").map(e => e.data);
  const sum = (k) => steps.reduce((t, d) => t + (d[k] || 0), 0);
  const model = sum("model_ms"), tool = sum("tool_ms"), over = sum("overhead_ms"), queue = sum("queue_ms");
  const total = Math.max(1, model + tool + over + queue);
  const pct = (v) => (v / total * 100).toFixed(1);
  const dur = (r.finished_at ? new Date(r.finished_at) : Date.now()) - new Date(r.created_at);
  view.innerHTML = `
    <div class="page-scroll" id="chat-scroll"><div class="feed" id="chat-stream">
      <div class="run-stats">
        <div class="ov-stats">
          <div class="kpi"><span class="kpi-label">Steps</span><span class="kpi-val">${r.steps}</span></div>
          <div class="kpi"><span class="kpi-label">Elapsed</span><span class="kpi-val">${fmtDur(dur)}</span></div>
          <div class="kpi"><span class="kpi-label">Recorded cost</span><span class="kpi-val">$${(r.cost_usd || 0).toFixed(4)}</span></div>
          <div class="kpi"><span class="kpi-label">Reported tokens</span><span class="kpi-val">${fmtTokens(r.tokens)}</span></div>
        </div>
        ${r.queue_ms > 0 && !steps.length ? `<p class="run-queue-time">Recorded inference admission waits: ${fmtDur(r.queue_ms)} (startup and steps)</p>` : ""}
        ${steps.length ? `
        <div class="panel run-timing">
          <div class="panel-title">Recorded step timing</div>
          ${r.queue_ms > 0 ? `<p class="run-queue-time">Recorded inference admission waits: ${fmtDur(r.queue_ms)} (startup and steps)</p>` : ""}
          <div class="timeline-stack" role="img" aria-label="model ${Math.round(model)}ms, tools ${Math.round(tool)}ms, hutch ${Math.round(over)}ms, step queue ${Math.round(queue)}ms">
            <i class="s-model" style="width:${pct(model)}%"></i>
            <i class="s-tool" style="width:${pct(tool)}%"></i>
            <i class="s-over" style="width:${pct(over)}%"></i>
            ${queue > 0 ? `<i class="s-queue" style="width:${pct(queue)}%"></i>` : ""}
          </div>
          <div class="timeline-legend">
            <span><i class="dot s-model"></i>model ${Math.round(model)}ms</span>
            <span><i class="dot s-tool"></i>tools ${Math.round(tool)}ms</span>
            <span><i class="dot s-over"></i>hutch ${Math.round(over)}ms</span>
            ${queue > 0 ? `<span><i class="dot s-queue"></i>queue ${Math.round(queue)}ms</span>` : ""}
          </div>
          <div class="step-strip">
            ${steps.map(d => {
              const t2 = (d.model_ms || 0) + (d.tool_ms || 0) + (d.overhead_ms || 0) + (d.queue_ms || 0);
              return `<span class="step-seg" title="step ${d.n}: ${fmtDur(t2)}" style="flex:${Math.max(1, t2)}"><i class="s-model" style="flex:${Math.max(0, d.model_ms || 0)}"></i><i class="s-tool" style="flex:${Math.max(0, d.tool_ms || 0)}"></i><i class="s-over" style="flex:${Math.max(0, d.overhead_ms || 0)}"></i>${d.queue_ms > 0 ? `<i class="s-queue" style="flex:${d.queue_ms}"></i>` : ""}</span>`;
            }).join("")}
          </div>
        </div>` : ""}
      </div>
    </div></div>`;
  // append the transcript block below the stats
  const stream = $("#chat-stream");
  const block = await runBlockHtml(runId);
  if (!stillCurrent() || !stream.isConnected) return;
  stream.insertAdjacentHTML("beforeend", block);
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
  let devices = [];
  let devicesError = "";
  try { devices = await api("/v1/devices"); }
  catch (err) { devicesError = err.message; }
  setTopContext(`<div class="ctx-id"><h1>Connections</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-add-conn">${icon("plus")} Add connection</button></div>`);
  const conns = data.connections || [];
  const windows = { "5h": "per 5 hours", "day": "per day", "week": "per week", "month": "per month" };
  const devicesOpen = $(".device-manager")?.open || false;
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="page-subtitle">A named hosted endpoint with its own key, terms, and allowance. Reference its models as <code class="mono">&lt;connection&gt;/&lt;model&gt;</code>.</p>
      <section class="panel conn-card" aria-labelledby="chatgpt-auth-title">
        <div class="bot-head"><span class="bot-name" id="chatgpt-auth-title">Sign in with ChatGPT</span>
          <span class="tag">experimental preview</span><span class="tag">local callback</span></div>
        <p class="hint">Uses OpenAI's official local sign-in flow and requests separate plan-use permission. It does not provide Hutch access to ChatGPT conversations. Availability depends on OpenAI eligibility and your account.</p>
        <p class="hint">This Responses preview has no provider-enforced output-token limit. Hutch's usage reservations and allowances are estimates, not a hard spending cap. <a href="https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations" target="_blank" rel="noopener noreferrer">Review preview limits</a>.</p>
        ${data.chatgpt_enabled ? '<button class="btn primary small" data-chatgpt-signin>Continue with ChatGPT</button>'
          : '<p class="hint">Preview sign-in is disabled. Set <code>HUTCH_ENABLE_CHATGPT_PLAN=1</code> only if Hutch is eligible for the local-app flow, then restart Hutch.</p><button class="btn primary small" disabled>Continue with ChatGPT</button>'}
        ${(data.chatgpt_accounts || []).map(account => `
          <div class="device-row" data-chatgpt-account="${esc(account.account_id)}">
            <div><strong>${esc(account.email || "ChatGPT account")}</strong>
              <span class="chip ${account.plan_usage ? "ok" : account.connected ? "warn" : "danger"}">${account.plan_usage ? "plan use authorized" : account.connected ? "identity only" : "disconnected"}</span>
              <p class="hint">${account.plan_usage ? `Model route: <code>chatgpt-${esc(account.account_id.replace(/^acct_/, ""))}/&lt;model&gt;</code>`
                : account.connected ? "Sign-in succeeded, but plan use was not granted. Authorize it before selecting models."
                : "Local credentials are cleared; the saved registration can be reauthorized."}</p></div>
            <div class="card-actions">
              ${data.chatgpt_enabled ? `<button class="btn ghost small" data-chatgpt-reauthorize="${esc(account.account_id)}">${account.plan_usage ? "Reconnect" : "Authorize plan use"}</button>` : ""}
              <button class="btn danger small" data-chatgpt-disconnect="${esc(account.account_id)}">Disconnect</button>
            </div>
          </div>`).join("")}
      </section>
      <details class="device-manager">
        <summary>Paired devices <span class="tag">${devices.length}</span></summary>
        <p class="hint">A paired browser can access this Hutch host while it is online. On the host, run <code>hutch pairing create</code>, then open <a href="/pair">/pair</a> on the device and enter the one-time code. For another device, Hutch must use <code>--allow-remote</code> with trusted TLS certificates; keep it on a private network.</p>
        ${devicesError ? `<p class="hint bad" role="alert">Could not load paired devices: ${esc(devicesError)}</p>` : devices.length ? `
          <div class="device-list" aria-label="Active paired devices">${devices.map(device => `
            <div class="device-row" data-device="${esc(device.id)}">
              <div><strong>${esc(device.label)}</strong> ${device.current ? '<span class="tag ok">this device</span>' : ''}
                <p class="hint">Last active ${esc(new Date(device.last_used_at).toLocaleString())} · expires ${esc(new Date(device.expires_at).toLocaleDateString())}</p></div>
              <button class="btn danger small" type="button" data-device-revoke="${esc(device.id)}">Revoke</button>
            </div>`).join("")}</div>` : `<p class="hint">No active paired devices.</p>`}
      </details>
      ${conns.length ? conns.map(c => `
        <div class="panel conn-card" data-conn="${esc(c.name)}">
          <div class="bot-head">
            <span class="bot-name">${esc(c.title || c.name)}</span>
            <span class="tag mono">${esc(c.protocol)}</span>
            <span class="tag ${c.billing === "per_token" ? "info" : ""}">${esc(c.billing === "per_token" ? "per token" : "flat rate")}</span>
            <span class="chip ${c.has_key ? "ok" : "danger"}" style="margin-left:auto;">${c.auth_type === "chatgpt-siws" ? (c.has_key ? "signed in" : "sign-in needed") : (c.has_key ? "key set" : "no key")}</span>
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
          ${c.auth_type === "chatgpt-siws" ? '<p class="hint">The provider does not accept a per-response output-token ceiling here. Hutch records estimates and provider-reported usage; it cannot guarantee a hard cap.</p>' : ""}
          ${c.get_key_url && c.template === "opencode-go" ? `<p class="hint"><a href="${esc(c.get_key_url)}" target="_blank" rel="noopener noreferrer">Continue to OpenCode</a>. Sign in to Go there, copy its issued API key, then paste it into Hutch. Hutch does not read OpenCode's private auth file.</p>` : ""}
          <div class="card-actions" style="margin-top:12px;">
            <button class="btn ghost small" data-conn-action="test">${icon("zap")} Test</button>
            ${c.auth_type === "chatgpt-siws" ? "" : '<button class="btn ghost small" data-conn-action="key">Set key</button>'}
            ${c.ack === "required" || c.ack === "stale" ? `<button class="btn warn small" data-conn-action="ack">Accept terms</button>` : ""}
            <button class="btn ghost small" data-conn-action="allowance">Allowance</button>
            ${c.auth_type === "chatgpt-siws" ? "" : '<button class="btn ghost small" data-conn-action="clear-key">Remove key</button>'}
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
  $(".device-manager").open = devicesOpen;

  const beginChatGPTSignIn = async (accountId = "", button = null) => {
    if (button) { button.disabled = true; button.textContent = "Opening ChatGPT…"; }
    try {
      const result = await api("/chatgpt/sign-in", { method: "POST", body: { account_id: accountId || null } });
      if (typeof result.authorization_url !== "string" ||
          !result.authorization_url.startsWith("https://auth.openai.com/api/accounts/authorize?")) {
        throw new Error("Hutch returned an unexpected ChatGPT sign-in destination.");
      }
      location.assign(result.authorization_url);
    } catch (err) {
      if (button) { button.disabled = false; button.textContent = accountId ? "Reconnect" : "Continue with ChatGPT"; }
      toast(err.message, true);
    }
  };
  $("[data-chatgpt-signin]")?.addEventListener("click", event => beginChatGPTSignIn("", event.currentTarget));
  $$('[data-chatgpt-reauthorize]').forEach(button => {
    button.addEventListener("click", () => beginChatGPTSignIn(button.dataset.chatgptReauthorize, button));
  });
  $$('[data-chatgpt-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (data.chatgpt_accounts || []).find(item => item.account_id === button.dataset.chatgptDisconnect);
      if (!account) return;
      const confirmed = await confirmDialog({
        title: "Disconnect ChatGPT",
        body: `Clear Hutch's local credentials for <b>${esc(account.email || "this account")}</b> and request remote revocation?`,
        confirmText: "Disconnect",
        danger: true,
      });
      if (!confirmed) return;
      button.disabled = true;
      try {
        const result = await api(`/chatgpt/accounts/${encodeURIComponent(account.account_id)}/disconnect`,
          { method: "POST", body: {} });
        toast(result.detail, !result.remote_revoked);
        await renderConnections();
      } catch (err) {
        button.disabled = false;
        toast(err.message, true);
      }
    });
  });

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

  $$('[data-device-revoke]').forEach(button => {
    button.addEventListener("click", async () => {
      const device = devices.find(item => item.id === button.dataset.deviceRevoke);
      if (!device) return;
      const confirmed = await confirmDialog({
        title: "Revoke device",
        body: `End Hutch access for <b>${esc(device.label)}</b>? This cannot be undone.`,
        confirmText: "Revoke device",
        danger: true,
      });
      if (!confirmed) return;
      button.disabled = true;
      try {
        await api(`/v1/devices/${encodeURIComponent(device.id)}/revoke`, { method: "POST", body: {} });
        if (device.current) {
          location.assign("/pair");
          return;
        }
        toast(`Revoked ${device.label}`);
        await renderConnections();
      } catch (err) {
        button.disabled = false;
        toast(err.message, true);
      }
    });
  });
}

/* -------------------------------------------------------- new-bot modal */

async function promptNewBot(preselect = "") {
  const templates = await api("/bots/templates");
  const html = `
    <form id="modal-bot-form" class="form-grid">
      <label class="field">Name
        <input type="text" name="name" placeholder="my-agent" pattern="[a-z0-9][a-z0-9-]{1,40}" required
          spellcheck="false" autocapitalize="none">
        <span class="hint">lowercase slug: letters, digits, dashes</span>
      </label>
      <div id="idp-root" class="panel" style="margin:0;">${identityPickerHtml()}</div>
      <label class="field">Start from a template
        <select name="template">
          <option value="">— blank —</option>
          ${templates.map(t => `<option value="${esc(t.name)}">${esc(t.tagline || t.name)}</option>`).join("")}
        </select>
      </label>
      <p class="hint" id="tpl-note">Blank bots start with no tools — you wire what they can do.</p>
      <div class="form-grid row2">
        <label class="field">Model
          <input type="text" name="model" placeholder="provider/model" required>
          <span class="hint">Use a configured route, such as openai/gpt-4o-mini or an installed ollama model. Model names are validated before a run.</span>
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
        sigilSet(name, picker.get());
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
  const picker = mountIdentityPicker($("#idp-root"), "draft");
  const sel = $('select[name="template"]'), note = $("#tpl-note");
  const describe = () => {
    const t = templates.find(x => x.name === sel.value);
    note.textContent = !t ? "Blank bots start with no tools — you wire what they can do."
      : `${t.tagline || ""} ${t.reads ? `Reads: ${t.reads}. ` : ""}${t.produces ? `Produces: ${t.produces}. ` : ""}${t.needs_folder ? "Needs a working folder." : ""}`;
  };
  sel.addEventListener("change", describe);
  if (preselect && templates.some(x => x.name === preselect)) sel.value = preselect;
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
}

/* ------------------------------------------------------------------ boot */

// Replay identifiers, then fetch authoritative state. Keep drafts/settings and
// their focus owned by the browser; resource updates never route the whole page.
let resourceStream = null, resourceStarting = false, resourceRetry = null, resourceRefreshTimer = null;
const changedResources = new Set();

function refreshChangedResources(resources) {
  resources.forEach(resource => changedResources.add(resource));
  if (resourceRefreshTimer) return;
  resourceRefreshTimer = setTimeout(() => {
    resourceRefreshTimer = null;
    const changed = new Set(changedResources);
    changedResources.clear();
    if (["bots", "runs", "usage", "usage_reservations"].some(r => changed.has(r))) void refreshRoster();
    if (["approvals", "runs", "actions", "state"].some(r => changed.has(r))) {
      void refreshBadge();
      if (needsYouDialog.open) void refreshApprovals();
    }
    if (changed.has("state")) void pollHealth();
    if (["messages", "conversations", "runs", "approvals", "actions", "transcript_mirrors", "memory"].some(r => changed.has(r))) {
      const visibleHash = location.hash || "#/chat";
      if (/^#\/chat(?:\/|$)/.test(visibleHash) || /^#\/run\/[\w-]+$/.test(visibleHash)) scheduleFeedRender();
    }
  }, 250);
}

async function startResourceStream() {
  if (resourceStarting || resourceStream || typeof EventSource === "undefined") return;
  resourceStarting = true;
  clearTimeout(resourceRetry);
  try {
    // A fresh page or a retention/history gap first reconciles state at a
    // consistent cursor. The targeted readers cover the visible resources;
    // snapshot items are not merged into potentially stale page state.
    const snapshot = await api("/v1/snapshot?limit=1");
    const source = new EventSource(`/api/v1/changes/stream?cursor=${encodeURIComponent(snapshot.change_cursor)}`);
    resourceStream = source;
    refreshChangedResources(["bots", "runs", "approvals", "conversations"]);
    source.addEventListener("changes", event => {
      if (source !== resourceStream) return;
      try {
        const page = JSON.parse(event.data);
        for (const change of page.changes) {
          if (change.context.run_id) terminalRunCache.delete(change.context.run_id);
          if (change.resource === "runs") terminalRunCache.delete(change.resource_id);
        }
        refreshChangedResources(page.changes.map(change => change.resource));
      } catch { reconcileResourceStream(source); }
    });
    source.addEventListener("snapshot_required", () => reconcileResourceStream(source));
    // EventSource preserves Last-Event-ID on ordinary reconnect. Only a
    // server-declared gap replaces its cursor; periodic readers remain fallback.
  } catch {
    resourceRetry = setTimeout(startResourceStream, 3000);
  } finally { resourceStarting = false; }
}

function reconcileResourceStream(source) {
  if (source !== resourceStream) return;
  source.close();
  resourceStream = null;
  terminalRunCache.clear();
  resourceRetry = setTimeout(startResourceStream, 1500);
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshChangedResources(["bots", "runs", "approvals", "conversations"]);
    void startResourceStream();
  }
});

$("#topbar-new-bot")?.addEventListener("click", promptNewBot);
route();
void loadStatusInfo();
refreshRoster();
void startResourceStream();
setInterval(() => { refreshBadge(); }, 6000);
setInterval(refreshRoster, 20000);   // roster activity, gentle
pollHealth();
setInterval(pollHealth, HEARTBEAT_MS);
