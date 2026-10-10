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
let currentWorkspaceTasks = [];
let currentCodeHandoffs = [];
let studioGeneration = 0;
let studioConversationMenuCleanup = null;
let activeReplySelectionHandler = null;
let activeWorkspaceResultSelectionHandler = null;
let activeBotCreationFromMessageHandler = null;
let activeChoiceSubmitHandler = null;
const requestedHumanResumes = new Set();
const runIntegrityStates = new Map();
let hutchSession = null;
let hutchCsrfToken = "";

/* ------------------------------------------------------------------ utils */

async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    if (hutchCsrfToken) headers["X-Hutch-CSRF"] = hutchCsrfToken;
    if (hutchSession?.principal === "paired") headers["X-Hutch-Request"] = "1";
  }
  let res;
  try {
    res = await fetch(`/api${path}`, {
      ...opts,
      credentials: "same-origin",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (error) {
    error.status = 0;
    throw error;
  }
  if (res.status === 401 && hutchSession?.principal === "paired") lockExpiredPhone();
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch {}
    const error = new Error(msg);
    error.status = res.status;
    throw error;
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

async function choiceAnswerIdempotencyKey(conversationId, questionId, body) {
  const storageKey = `hutch-pending-choice:${conversationId}:${questionId}`;
  const fingerprint = await payloadFingerprint(body);
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.fingerprint === fingerprint && previous?.key) return previous.key;
  } catch { /* replace a damaged browser-local retry marker */ }
  const key = newIdempotencyKey();
  storageSet(storageKey, JSON.stringify({ key, fingerprint }));
  return key;
}

function clearChoiceIdempotencyKey(conversationId, questionId, key) {
  const storageKey = `hutch-pending-choice:${conversationId}:${questionId}`;
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.key === key) localStorage.removeItem(storageKey);
  } catch { storageRemove(storageKey); }
}

function setRunIntegrityState(runId, state) {
  runIntegrityStates.set(runId, state);
  if (runIntegrityStates.size > 100) runIntegrityStates.delete(runIntegrityStates.keys().next().value);
  const section = $$('[data-run-integrity-run]', view).find(node => node.dataset.runIntegrityRun === runId);
  const result = section && $('[data-run-integrity-result]', section);
  if (!result) return;
  result.textContent = state.text;
  result.dataset.state = state.state;
  result.setAttribute('role', state.role);
}

function choiceDraftKey(conversationId, questionId) {
  return `hutch-choice-draft:${conversationId}:${questionId}`;
}

document.addEventListener("click", ev => {
  const openChoice = ev.target.closest("[data-open-choice-conversation]");
  if (!openChoice) return;
  void openConversation(openChoice.dataset.openChoiceConversation);
});

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

function conversationArtifactSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "Size unavailable";
  if (value < 1000) return `${value} bytes`;
  if (value < 1_000_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} kB`;
  return `${(value / 1_000_000).toFixed(value < 10_000_000 ? 1 : 0)} MB`;
}

function conversationArtifactHtml(item) {
  const filename = item.filename || (item.kind === "workspace_file" ? "Generated file" : "Saved tool output");
  const kind = item.kind === "workspace_file" ? "Created file" : `${item.source_tool || "Tool"} output`;
  const state = item.state === "available" ? "Verified and ready to download"
    : item.state === "missing" ? "Saved file is missing"
      : "Older file has no verification hash";
  const size = item.kind === "workspace_file" && Number.isInteger(item.size_bytes) && item.size_bytes >= 0
    ? conversationArtifactSize(item.size_bytes) : item.size_bytes ? conversationArtifactSize(item.size_bytes)
    : item.chars ? `${Number(item.chars).toLocaleString("en-US")} characters` : "";
  const sharedWith = Array.isArray(item.shared_with) ? item.shared_with : [];
  const sharedWithHtml = sharedWith.length ? `<div class="conversation-file-grants" aria-label="Active shares">
    ${sharedWith.map(target => `<div class="conversation-file-grant">
      <span>Shared with ${esc(target.target_conversation_title || "another chat")}</span>
      <button class="btn ghost small" type="button" data-artifact-unshare="${esc(target.id)}"
        data-share-target="${esc(target.target_conversation_id)}"
        data-share-name="${esc(target.target_conversation_title || "another chat")}" aria-label="Stop sharing ${esc(filename)} with ${esc(target.target_conversation_title || "another chat")}">Stop sharing</button>
    </div>`).join("")}
  </div>` : "";
  const safeUrl = item.state === "available" && typeof item.download_url === "string"
    && (/^\/api\/v1\/tasks\/runs\/[a-zA-Z0-9_-]{4,80}\/artifacts\/[0-9]{3,6}-[a-z0-9_-]{1,40}\.txt$/.test(item.download_url)
      || /^\/api\/v1\/conversations\/[a-zA-Z0-9_-]{4,80}\/artifact-shares\/ash_[a-f0-9]{24}\/content$/.test(item.download_url))
    ? item.download_url : "";
  return `<article class="conversation-file">
    <div class="conversation-file-main">
      ${icon(item.kind === "workspace_file" ? "fileText" : "layers")}
      <div class="conversation-file-copy">
        <strong title="${esc(filename)}">${esc(filename)}</strong>
        <span>${esc(kind)}${size ? ` · ${esc(size)}` : ""} · ${esc(timeAgo(item.created_at))}</span>
        <span class="conversation-file-state">${esc(state)}</span>
        ${item.share_id ? `<span>Shared from ${esc(item.shared_from || "another chat")}</span>` : ""}
      </div>
      <div class="conversation-file-actions">
        ${safeUrl ? `<a class="btn ghost small" href="${esc(safeUrl)}" aria-label="Download ${esc(filename)}">Download</a>` : ""}
        ${item.share_id ? `<button class="btn ghost small" type="button" data-artifact-unshare="${esc(item.share_id)}" aria-label="Stop sharing ${esc(filename)}">Stop sharing</button>`
          : safeUrl ? `<button class="btn ghost small" type="button" data-artifact-share data-run="${esc(item.run_id)}" data-version="${esc(item.version)}" data-kind="${esc(item.kind)}" aria-label="Share ${esc(filename)} with another chat">Share</button>` : ""}
      </div>
    </div>
    ${sharedWithHtml}
    <div class="conversation-file-share" hidden></div>
  </article>`;
}

async function showConversationArtifactShare(article, item, currentId) {
  const region = $(".conversation-file-share", article);
  if (!region) return;
  if (!region.hidden) { region.hidden = true; region.innerHTML = ""; return; }
  region.hidden = false;
  region.innerHTML = `<label class="field">Share with another chat
      <input class="artifact-share-search" type="search" placeholder="Find a chat" autocomplete="off">
      <select class="artifact-share-target" aria-label="Destination chat" disabled><option value="">Choose a chat…</option></select>
    </label>
    <p class="hint artifact-share-note">This adds a verified file reference to that chat’s Files list. It does not copy the file into its workspace or add the contents to its model context.</p>
    <div class="artifact-share-status hint" role="status" aria-live="polite">Loading available chats…</div>
    <div class="artifact-share-actions">
      <button type="button" class="btn ghost small artifact-share-more" hidden>Load more chats</button>
      <button type="button" class="btn ghost small artifact-share-cancel">Cancel</button>
      <button type="button" class="btn primary small artifact-share-submit" disabled>Share file</button>
    </div>`;
  const search = $(".artifact-share-search", region);
  const select = $(".artifact-share-target", region);
  const status = $(".artifact-share-status", region);
  const more = $(".artifact-share-more", region);
  const submit = $(".artifact-share-submit", region);
  let offset = 0;
  let hasMore = false;
  let loading = false;
  let botNames = new Map();

  const filterOptions = () => {
    const needle = search.value.trim().toLocaleLowerCase();
    let shown = 0;
    for (const option of [...select.options]) {
      if (!option.value) continue;
      option.hidden = Boolean(needle) && !option.textContent.toLocaleLowerCase().includes(needle);
      if (!option.hidden) shown++;
    }
    if (select.value && select.selectedOptions[0]?.hidden) select.value = "";
    submit.disabled = !select.value;
    if (needle && !shown) status.textContent = "No loaded chat matches. Load more chats or change the search.";
  };
  const loadChats = async () => {
    if (loading || !hasMore && offset > 0) return;
    loading = true;
    more.disabled = true;
    status.textContent = "Loading available chats…";
    try {
      if (!botNames.size) {
        const bots = await api("/bots");
        botNames = new Map((bots || []).map(bot => [bot.id, bot.name]));
      }
      const page = await api(`/v1/conversations?limit=100&offset=${offset}`);
      for (const conversation of page) {
        if (conversation.id === currentId) continue;
        const option = document.createElement("option");
        option.value = conversation.id;
        option.textContent = `${conversation.title || "New conversation"} · ${botNames.get(conversation.bot_id) || "Bot"}`;
        select.appendChild(option);
      }
      offset += page.length;
      hasMore = page.length === 100;
      select.disabled = ![...select.options].some(option => option.value && !option.hidden);
      more.hidden = !hasMore;
      status.textContent = select.options.length
        ? "Choose the chat that should see this file reference."
        : "No other active chats yet. Create another chat before sharing.";
      filterOptions();
      if (offset === page.length) select.focus({ preventScroll: true });
    } catch (error) {
      status.textContent = `Could not load chats: ${error.message}`;
      more.hidden = true;
    } finally {
      loading = false;
      more.disabled = false;
    }
  };
  search.addEventListener("input", filterOptions);
  select.addEventListener("change", () => { submit.disabled = !select.value; });
  more.addEventListener("click", () => { void loadChats(); });
  $(".artifact-share-cancel", region).addEventListener("click", () => {
    region.hidden = true;
    region.innerHTML = "";
    article.querySelector("[data-artifact-share]")?.focus({ preventScroll: true });
  });
  submit.addEventListener("click", async () => {
    const targetId = select.value;
    if (!targetId) return;
    const targetLabel = select.selectedOptions[0]?.textContent || "the selected chat";
    submit.disabled = true;
    status.textContent = "Sharing verified file reference…";
    try {
      await api(`/v1/conversations/${encodeURIComponent(targetId)}/artifact-shares`, {
        method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() },
        body: { source_run_id: item.run_id, source_version: Number(item.version), kind: item.kind },
      });
      status.textContent = `Shared with ${targetLabel}. The file appears in that chat’s Files list only.`;
      submit.textContent = "Shared";
      submit.disabled = true;
      more.disabled = true;
    } catch (error) {
      status.textContent = `Could not share this file: ${error.message}`;
      submit.disabled = false;
    }
  });
  await loadChats();
}

async function openConversationFiles(conversationId, returnFocus) {
  openModal({
    title: "Files in this chat",
    bodyHtml: `<p class="hint">Created files and saved tool output from this conversation. Downloads are checked against their recorded size and hash. You can share a verified file reference with another chat; it will not be copied into that chat’s workspace or model context.</p>
      <div id="conversation-files-status" class="hint" role="status" aria-live="polite">Loading files…</div>
      <div id="conversation-files-list" class="conversation-files-list"></div>
      <div id="conversation-files-more"></div>`,
    confirmText: "Done", showCancel: false, wide: true, tall: true, returnFocus,
  });

  const list = $("#conversation-files-list");
  const status = $("#conversation-files-status");
  const more = $("#conversation-files-more");
  if (!list || !status || !more) return;
  let cursor = "";
  let count = 0;

  const load = async (append = false) => {
    status.textContent = append ? "Loading more files…" : "Loading files…";
    more.innerHTML = "";
    try {
      const next = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
      const page = await api(`/v1/conversations/${encodeURIComponent(conversationId)}/artifacts?limit=50${next}`);
      if (!$("#conversation-files-list")) return;
      const items = page.artifacts || [];
      list.insertAdjacentHTML(append ? "beforeend" : "afterbegin", items.map(conversationArtifactHtml).join(""));
      count += items.length;
      cursor = page.next_cursor || "";
      status.textContent = count ? `${count} ${count === 1 ? "item" : "items"}`
        : "No files or saved tool output in this chat yet.";
      if (page.next_cursor) {
        more.innerHTML = `<button class="btn ghost small" id="conversation-files-load-more" type="button">Load more</button>`;
        $("#conversation-files-load-more")?.addEventListener("click", ev => {
          ev.currentTarget.disabled = true;
          load(true);
        });
      }
    } catch (err) {
      status.textContent = `Could not load files: ${err.message}`;
      more.innerHTML = `<button class="btn ghost small" id="conversation-files-retry" type="button">Try again</button>`;
      $("#conversation-files-retry")?.addEventListener("click", ev => {
        ev.currentTarget.disabled = true;
        load(append);
      });
    }
  };
  list.addEventListener("click", event => {
    const share = event.target.closest("[data-artifact-share]");
    if (share) {
      const article = share.closest(".conversation-file");
      void showConversationArtifactShare(article, {
        run_id: share.dataset.run, version: Number(share.dataset.version), kind: share.dataset.kind,
      }, conversationId);
      return;
    }
    const unshare = event.target.closest("[data-artifact-unshare]");
    if (unshare) {
      const shareId = unshare.dataset.artifactUnshare;
      const targetId = unshare.dataset.shareTarget || conversationId;
      const targetName = unshare.dataset.shareName || "this chat";
      const article = unshare.closest(".conversation-file");
      unshare.disabled = true;
      status.textContent = "Stopping the share…";
      void api(`/v1/conversations/${encodeURIComponent(targetId)}/artifact-shares/${encodeURIComponent(shareId)}`, {
        method: "DELETE", headers: { "Idempotency-Key": newIdempotencyKey() },
      }).then(async () => {
        cursor = ""; count = 0; list.innerHTML = "";
        await load();
        status.textContent = targetId === conversationId
          ? "This chat no longer has access to the shared file. Its source file remains in the original chat."
          : `Sharing with ${targetName} has stopped. The source file remains in this chat.`;
        if (!article.isConnected) $("#modal-confirm")?.focus({ preventScroll: true });
      }).catch(error => {
        status.textContent = `Could not stop sharing: ${error.message}`;
        unshare.disabled = false;
      });
    }
  });
  await load();
}

function openConversationExport(conversationId, returnFocus) {
  openModal({
    title: "Export conversation",
    returnFocus,
    bodyHtml: `<p>This JSON includes conversation metadata and ordered message text with run provenance.</p>
      <p>It excludes stored provider credentials, tool and action receipts, workspace content, artifact files, and memory records.</p>
      <p class="hint">Message text is included verbatim, so review it for sensitive content before sharing. Exports are limited to 10,000 messages and 2 MiB of source data.</p>`,
    confirmText: "Download JSON",
    onConfirm: async () => {
      try {
        const response = await fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}/export`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          let message = `Download failed (${response.status})`;
          try { message = (await response.json()).detail || message; } catch {}
          throw new Error(message);
        }
        const file = await response.blob();
        const url = URL.createObjectURL(file);
        const link = document.createElement("a");
        link.href = url;
        link.download = "hutch-conversation-export.json";
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast("Conversation export downloaded. Review its message text before sharing.");
        return true;
      } catch (error) {
        toast(`Could not export this conversation: ${error.message}`, true);
        return false;
      }
    },
  });
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
const googleCalendarResult = chatgptCallback.get("google_calendar_result");
const googleMailResult = chatgptCallback.get("google_mail_result");
const outlookCalendarResult = chatgptCallback.get("outlook_calendar_result");
const outlookMailResult = chatgptCallback.get("outlook_mail_result");
if (chatgptResult || googleCalendarResult || googleMailResult || outlookCalendarResult || outlookMailResult) {
  const detail = chatgptCallback.get("detail");
  const message = outlookMailResult
    ? outlookMailResult === "connected" ? "Outlook Mail account connected. Grant one Bot read access from Connections."
      : detail || "Outlook Mail sign-in did not complete. Start again from Connections."
    : googleMailResult
    ? googleMailResult === "connected" ? "Gmail account connected. Grant one Local-inference Bot search access from Connections."
      : detail || "Gmail sign-in did not complete. Start again from Connections."
    : outlookCalendarResult
    ? outlookCalendarResult === "connected" ? "Outlook Calendar account connected. Choose a calendar and grant one Bot read access from Connections."
      : detail || "Outlook Calendar sign-in did not complete. Start again from Connections."
    : googleCalendarResult
    ? googleCalendarResult === "connected" ? "Google Calendar account connected. Choose a calendar and grant one Bot read access from Connections."
      : detail || "Google Calendar sign-in did not complete. Start again from Connections."
    : chatgptResult === "connected" ? "ChatGPT plan route connected."
    : chatgptResult === "identity-only" ? "ChatGPT signed in, but plan use was not granted. Reauthorize to use it for models."
    : detail || "ChatGPT sign-in did not complete. Start again from Connections.";
  setTimeout(() => toast(message, chatgptResult === "error" || googleCalendarResult === "error" || googleMailResult === "error" || outlookCalendarResult === "error" || outlookMailResult === "error"), 0);
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
  moreHorizontal: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.2 3.9A2 2 0 0 0 7.5 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.2A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a15 15 0 0 1-3.1 3.8M6.2 6.2C3.5 8 2 12 2 12s3.5 7 10 7c1 0 1.9-.2 2.8-.5"/>',
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
  trash: '<path d="M3 6h18M8 6V4h8v2m3 0-.9 14H5.9L5 6m4 4v6m6-6v6"/>',
  pin: '<path d="M16 3 21 8l-4 1-4 4v4l-2 2-2-6-6-6 2-2 6 6 4-4z"/><path d="m2 22 7-7"/>',
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
   Each Bot gets one light 2D character: a distinctive, name-stable silhouette,
   one brand-family colour and a pair of inset ink eyes. This simple family
   belongs to the operator app; the marketing site keeps its detailed 3D artwork.
   Identity never encodes status. Status remains a separate labeled indicator. */
const ID_COLORS = ["#3DE8C5", "#35C3F0", "#5B9BFF", "#9B7CFF", "#C77DFF", "#FF6FA5", "#FFA83C", "#7BD85A"];
const ID_HEADS = [
  { key: "orb", d: "M32 8C45 8 55 18 55 32S45 56 32 56 9 46 9 32 19 8 32 8Z" },
  { key: "capsule", d: "M32 7c12 0 19 8 19 19v12c0 11-7 19-19 19s-19-8-19-19V26C13 15 20 7 32 7Z" },
  { key: "bean", d: "M13 28c0-12 11-19 23-17 11 1 19 10 18 21-1 12-9 21-21 22-12 1-21-9-20-26Z" },
  { key: "drop", d: "M32 8c8 10 21 21 21 32a21 18 0 0 1-42 0C11 29 24 18 32 8Z" },
  { key: "pebble", d: "M12 29c1-12 10-20 22-19 12 0 20 8 19 20 0 12-7 24-20 25-13 1-22-9-21-26Z" },
  { key: "shield", d: "M32 9c7 4 15 6 21 7v17c0 12-8 19-21 23-13-4-21-11-21-23V16c6-1 14-3 21-7Z" },
  { key: "triangle", d: "M27 12c2-4 8-4 10 0l19 32c2 4-1 8-5 8H13c-5 0-7-4-5-8l19-32Z" },
  { key: "hex", d: "M22 9h20l13 23-13 23H22L9 32 22 9Z" },
];
// Each silhouette gets a face tuned to its usable area. The paired eyes keep
// one simple language, while their spacing, oval proportions, and tilt follow
// the head instead of stamping the same expression onto every shape.
const ID_FACES = [
  [[25, 29, 4.8, 2.6, -42], [39, 28, 4.5, 2.4, -39]], // orb: relaxed diagonal
  [[25, 29, 4.4, 2.6, -35], [39, 29, 4.3, 2.5, -35]], // capsule: upright
  [[24, 30, 4.8, 2.7, -39], [39, 29, 4.3, 2.5, -36]], // bean: follows the lean
  [[25, 34, 4.6, 2.6, -42], [39, 32, 4.5, 2.5, -40]], // drop: lower in the bowl
  [[25, 29, 4.4, 2.5, -40], [39, 29, 4.8, 2.7, -45]], // pebble: gently uneven
  [[25, 27, 4.1, 2.6, -36], [39, 27, 4.1, 2.5, -36]], // shield: narrow brow
  [[26, 35, 4.0, 2.6, -42], [39, 33, 4.1, 2.5, -40]], // triangle: lower, centered
  [[25, 30, 4.4, 2.5, -35], [39, 30, 4.2, 2.4, -35]], // hex: upright facets
];

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

function sigilEyes(shapeIndex) {
  const [lead, companion] = ID_FACES[shapeIndex] || ID_FACES[0];
  const eye = (name, [cx, cy, rx, ry, angle]) =>
    `<ellipse data-sigil-eye="${name}" cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" transform="rotate(${angle} ${cx} ${cy})"/>`;
  return `<g fill="#10161f" aria-hidden="true">
    ${eye("lead", lead)}
    ${eye("companion", companion)}
  </g>`;
}

function sigilBody(pair) {
  const [ci, si] = pair;
  const base = ID_COLORS[ci];
  const h = ID_HEADS[si] || ID_HEADS[0];
  return `<path d="${h.d}" fill="${base}"/>${sigilEyes(si)}`;
}

function avatarFromPair(pair, size, state = "") {
  return `<span class="avatar" style="--av:${size}px" aria-hidden="true"><svg class="sig" viewBox="0 0 64 64">${sigilBody(pair)}</svg>${state ? `<span class="a-pip ${esc(state)}"></span>` : ""}</span>`;
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
// shared identity picker (creation modal + bot settings)
function identityPickerHtml() {
  return `
    <div class="idp">
      <div class="idp-prev" data-idp-prev></div>
      <p class="idp-lbl">Colour</p>
      <div class="idp-row" data-idp-colors>${ID_COLORS.map((c, i) =>
        `<button type="button" class="sw" data-ci="${i}" style="--swatch:${c}" aria-label="Colour ${i + 1}" aria-pressed="false"></button>`).join("")}</div>
      <p class="idp-lbl">Shape</p>
      <div class="idp-row" data-idp-shapes>${ID_HEADS.map((hh, i) =>
        `<button type="button" class="shp" data-si="${i}" aria-label="Shape ${esc(hh.key)}" aria-pressed="false">
          <svg viewBox="0 0 64 64" aria-hidden="true"><path d="${hh.d}" fill="currentColor"/>${sigilEyes(i)}</svg>
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

function openModal({ title, bodyHtml, onConfirm, onCancel, confirmText = "Confirm", confirmClass = "primary", wide = false, tall = false, returnFocus = null, showCancel = true }) {
  const root = $("#modal-root");
  const modalReturnFocus = returnFocus || document.activeElement;
  root.innerHTML = `
    <div class="modal-backdrop" data-modal-backdrop>
      <div class="modal-card${wide ? " modal-wide" : ""}${tall ? " modal-tall" : ""}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
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
    else if (modalReturnFocus?.dataset.backgroundProvider) {
      ($$('[data-background-provider]').find(button =>
        button.dataset.backgroundProvider === modalReturnFocus.dataset.backgroundProvider) || $('#nav-toggle'))?.focus();
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
let rosterMenuCleanup = null;

function closeRosterActionMenu(restoreFocus = false) {
  const menu = document.getElementById("roster-action-menu");
  const name = menu?.dataset.botName;
  rosterMenuCleanup?.();
  rosterMenuCleanup = null;
  menu?.remove();
  const trigger = name ? $$("#roster-list [data-bot-options]").find(button => button.dataset.botOptions === name) : null;
  trigger?.setAttribute("aria-expanded", "false");
  if (restoreFocus) trigger?.focus({ preventScroll: true });
}

function editBotRosterSection(bot, trigger) {
  const existing = bot.roster_section || "";
  closeRosterActionMenu(false);
  openModal({
    title: existing ? "Move to a section" : "New section",
    bodyHtml: `<p>Keep related Bots together in the sidebar. Reusing a section name groups them together.</p>
      <label class="field" for="roster-section-name">Section name
        <input id="roster-section-name" type="text" maxlength="40" autocomplete="off" value="${esc(existing)}" placeholder="For example, Client work">
      </label>
      <p class="hint">Leave the name empty to return this Bot to All bots. This changes organization only.</p>
      <p id="roster-section-error" class="form-error" role="status" aria-live="polite"></p>`,
    confirmText: "Save section",
    returnFocus: trigger,
    onConfirm: async () => {
      const input = $("#roster-section-name");
      const section = input.value.trim().replace(/\s+/g, " ");
      if (section.length > 40) {
        $("#roster-section-error").textContent = "Section names can be up to 40 characters.";
        input.focus();
        return false;
      }
      const confirm = $("#modal-confirm");
      confirm.disabled = true;
      try {
        const saved = await api(`/bots/${encodeURIComponent(bot.name)}`, {
          method: "PATCH", body: { roster_section: section },
        });
        botsCache = botsCache.map(item => item.id === saved.id ? { ...item, ...saved } : item);
        renderRoster();
        announce(section ? `${saved.display_name || saved.name} moved to ${section}.` : `${saved.display_name || saved.name} moved to All bots.`);
        return true;
      } catch (error) {
        confirm.disabled = false;
        $("#roster-section-error").textContent = `Could not save this section: ${error.message}`;
        return false;
      }
    },
  });
}

async function prepareBotTemplateDownload(bot, trigger) {
  closeRosterActionMenu(false);
  const configuration = {
    name: bot.name,
    display_name: bot.display_name || bot.name,
    template: bot.template || null,
    description: bot.description || "",
    instructions: bot.instructions || "",
    model: bot.model || "",
    inference_mode: bot.inference_mode || "hybrid",
    tools: Array.isArray(bot.tools) ? [...bot.tools] : [],
    memory_enabled: !!bot.memory_enabled,
    approval_mode: bot.approval_mode || "ask",
    risk_tier: bot.risk_tier || "supervised",
    command_rules: Array.isArray(bot.command_rules) ? bot.command_rules : [],
    workspace_mode: bot.workspace_mode === "folder" ? "managed" : (bot.workspace_mode || "managed"),
    local_browser_handoff: false,
    limits: bot.limits || {},
    // Schedules are intentionally omitted so importing a template never starts recurring work.
    cron: null,
    timezone: "UTC",
    catch_up: "coalesce",
    schedule_prompt: "",
  };
  try {
    const preview = await api("/v1/bot-configs/preview", { method: "POST", body: configuration });
    openModal({
      title: "Share as template",
      bodyHtml: `<p>Review this setup, then download a YAML file you can share yourself. <b>Nothing is uploaded.</b></p>
        <p class="hint">Provider URLs, local folders, schedules, memory values, and chat history are excluded. A folder-based Bot becomes a managed workspace in the template. Instructions and enabled tools are included, so check them for private details before sharing.</p>
        <pre class="setup-yaml-preview bot-template-preview" id="bot-template-preview" tabindex="0" aria-label="Reviewable Bot setup template">${esc(preview.yaml)}</pre>`,
      confirmText: "Download template",
      wide: true,
      returnFocus: trigger,
      onConfirm: async () => {
        const blob = new Blob([preview.yaml], { type: "application/yaml;charset=utf-8" });
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = `${(bot.display_name || bot.name).toLowerCase().replace(/[^a-z0-9-]+/g, "-")
          .replace(/^-+|-+$/g, "").slice(0, 48) || "bot"}-template.yaml`;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        return true;
      },
    });
  } catch (error) {
    toast(`Could not prepare this template: ${error.message}`, true);
    $$("#roster-list [data-bot-options]").find(button => button.dataset.botOptions === bot.name)?.focus({ preventScroll: true });
  }
}

function openRosterActionMenu(trigger) {
  const name = trigger.dataset.botOptions;
  const bot = botsCache.find(item => item.name === name);
  if (!bot) return;
  closeRosterActionMenu(false);
  const menu = document.createElement("div");
  menu.id = "roster-action-menu";
  menu.className = "roster-action-menu";
  menu.dataset.botName = name;
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", `Options for ${bot.display_name || bot.name}`);
  menu.innerHTML = `${bot.is_workspace_coordinator ? "" : `<button type="button" role="menuitem" tabindex="-1" data-menu-pin>${icon("pin")} ${bot.pinned ? "Remove from pinned" : "Pin to sidebar"}</button>
    <button type="button" role="menuitem" tabindex="-1" data-menu-section>${icon("folder")} ${bot.roster_section ? "Move to a section" : "New section"}</button>
    `}<button type="button" role="menuitem" tabindex="-1" data-menu-template>${icon("fileText")} Share as template</button>
    <button type="button" role="menuitem" tabindex="-1" data-menu-duplicate>${icon("bot")} Duplicate bot</button>
    ${bot.is_workspace_coordinator ? "" : `<button type="button" role="menuitem" tabindex="-1" data-menu-hide>${icon(bot.sidebar_hidden ? "eye" : "eyeOff")} ${bot.sidebar_hidden ? "Show in sidebar" : "Hide from sidebar"}</button>`}
    <a role="menuitem" tabindex="-1" data-menu-settings href="#/bot/${encodeURIComponent(bot.name)}">${icon("sliders")} Bot settings</a>`;
  document.body.append(menu);
  trigger.setAttribute("aria-expanded", "true");
  const triggerRect = trigger.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const left = Math.max(8, Math.min(triggerRect.right - menuRect.width, window.innerWidth - menuRect.width - 8));
  const below = triggerRect.bottom + 4;
  const top = below + menuRect.height <= window.innerHeight - 8
    ? below : Math.max(8, triggerRect.top - menuRect.height - 4);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  const items = () => $$('[role="menuitem"]', menu);
  const onPointerDown = event => {
    if (!menu.contains(event.target) && !trigger.contains(event.target)) closeRosterActionMenu(false);
  };
  const onKeyDown = event => {
    const options = items();
    const index = options.indexOf(document.activeElement);
    if (event.key === "Escape") {
      event.preventDefault();
      closeRosterActionMenu(true);
    } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && options.length) {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : options.length - 1)) % options.length;
      options[next].focus();
    }
  };
  const onScroll = () => closeRosterActionMenu(false);
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown);
  window.addEventListener("resize", onScroll);
  document.addEventListener("scroll", onScroll, true);
  rosterMenuCleanup = () => {
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("resize", onScroll);
    document.removeEventListener("scroll", onScroll, true);
  };
  menu.querySelector('[data-menu-settings]')?.addEventListener("click", () => closeRosterActionMenu(false));
  menu.querySelector("[data-menu-section]")?.addEventListener("click", () => editBotRosterSection(bot, trigger));
  menu.querySelector("[data-menu-template]")?.addEventListener("click", () => prepareBotTemplateDownload(bot, trigger));
  menu.querySelector("[data-menu-duplicate]")?.addEventListener("click", () => {
    closeRosterActionMenu(false);
    void promptNewBot("", "", bot);
  });
  menu.querySelector("[data-menu-hide]")?.addEventListener("click", async event => {
    const action = event.currentTarget;
    action.disabled = true;
    action.setAttribute("aria-busy", "true");
    try {
      const saved = await api(`/bots/${encodeURIComponent(name)}`, {
        method: "PATCH", body: { sidebar_hidden: !bot.sidebar_hidden, ...(bot.pinned ? { pinned: false } : {}) },
      });
      botsCache = botsCache.map(item => item.id === saved.id ? { ...item, ...saved } : item);
      closeRosterActionMenu(false);
      renderRoster();
      if (saved.sidebar_hidden) {
        $("#roster-hidden-details summary")?.focus({ preventScroll: true });
        announce(`${saved.display_name || saved.name} hidden from the roster. Runs and schedules continue.`);
        toast("Hidden from the roster. This does not pause the Bot or its schedules.");
      } else {
        $$("#roster-list [data-bot-options]").find(button => button.dataset.botOptions === name)?.focus({ preventScroll: true });
        announce(`${saved.display_name || saved.name} shown in the roster.`);
      }
    } catch (error) {
      action.disabled = false;
      action.removeAttribute("aria-busy");
      toast(`Could not update ${name}: ${error.message}`, true);
      action.focus();
    }
  });
  menu.querySelector("[data-menu-pin]")?.addEventListener("click", async event => {
    const action = event.currentTarget;
    action.disabled = true;
    action.setAttribute("aria-busy", "true");
    try {
      const saved = await api(`/bots/${encodeURIComponent(name)}`, {
        method: "PATCH", body: { pinned: !bot.pinned, ...(!bot.pinned && bot.sidebar_hidden ? { sidebar_hidden: false } : {}) },
      });
      botsCache = botsCache.map(item => item.id === saved.id ? { ...item, ...saved } : item);
      closeRosterActionMenu(false);
      renderRoster();
      $$("#roster-list [data-bot-options]").find(button => button.dataset.botOptions === name)?.focus({ preventScroll: true });
      announce(`${saved.display_name || saved.name} ${saved.pinned ? "pinned" : "unpinned"}.`);
    } catch (error) {
      action.disabled = false;
      action.removeAttribute("aria-busy");
      toast(`Could not update ${name}: ${error.message}`, true);
      action.focus();
    }
  });
  menu.querySelector('[role="menuitem"]')?.focus({ preventScroll: true });
}

function botDisplayName(ref) {
  if (ref && typeof ref === "object") return ref.display_name || ref.bot_display_name || ref.name || "Bot";
  return botsCache.find(bot => bot.name === ref || bot.id === ref)?.display_name || ref || "Bot";
}

const routes = [
  [/^#\/chat(?:\/([\w-]+))?$/, m => renderChatStudio(m ? m[1] : null), "chat"],
  [/^#\/conversation\/([\w-]+)$/, m => openConversation(m[1]), "chat"],
  [/^#\/overview$/, renderOverview, "overview"],
  [/^#\/schedules$/, renderSchedules, "schedules"],
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

function openConversationSearch(trigger) {
  const botOptions = botsCache.map(bot =>
    `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("");
  openModal({
    title: "Search chats",
    wide: true,
    tall: true,
    returnFocus: trigger,
    confirmText: "Done",
    confirmClass: "ghost",
    showCancel: false,
    bodyHtml: `<form class="message-search" id="message-search-form" role="search">
      <div class="message-search-controls">
        <label class="field message-search-query" for="message-search-query">Search messages
          <input id="message-search-query" type="search" maxlength="256" autocomplete="off" spellcheck="false"
            aria-describedby="message-search-scope" placeholder="Search words or a phrase" />
        </label>
        <label class="field message-search-bot-filter" for="message-search-bot">Bot
          <select id="message-search-bot"><option value="">All Bots</option>${botOptions}</select>
        </label>
      </div>
      <p class="hint message-search-scope" id="message-search-scope">Search covers active chats. Archived and imported history stays out of results.</p>
      <p class="message-search-status" id="message-search-status" role="status" aria-live="polite">Type at least two characters to search.</p>
      <div class="message-search-results" id="message-search-results" aria-label="Search results"></div>
    </form>`,
  });
  const form = $("#message-search-form");
  const input = $("#message-search-query");
  const botFilter = $("#message-search-bot");
  const status = $("#message-search-status");
  const results = $("#message-search-results");
  let requestGeneration = 0;
  let debounce = null;
  const renderHits = hits => {
    results.innerHTML = hits.map(hit => {
      const botName = botDisplayName(hit.bot_id);
      const title = hit.title || "Untitled conversation";
      const date = new Date(hit.created_at);
      const time = Number.isNaN(date.valueOf()) ? "Date unavailable"
        : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
      const role = hit.role === "user" ? "You" : botName;
      return `<button class="message-search-result" type="button"
        data-search-conversation="${esc(hit.conversation_id)}" data-search-run="${esc(hit.run_id || "")}">
        <span class="message-search-result-head"><span class="message-search-result-title">${esc(title)}</span>
          <span class="message-search-result-meta">${esc(botName)} · ${esc(role)} · ${esc(time)}</span></span>
        <span class="message-search-result-excerpt">${esc(hit.excerpt)}</span>
      </button>`;
    }).join("");
  };
  const search = async () => {
    clearTimeout(debounce);
    const query = input.value.trim();
    const generation = ++requestGeneration;
    if (query.length < 2) {
      results.innerHTML = "";
      status.textContent = "Type at least two characters to search.";
      return;
    }
    status.textContent = "Searching chats…";
    try {
      const hits = await api("/v1/search/messages", {
        method: "POST", body: { q: query, bot: botFilter.value || null, limit: 30 },
      });
      if (generation !== requestGeneration || !form.isConnected) return;
      renderHits(hits);
      status.textContent = hits.length ? `${hits.length} ${hits.length === 1 ? "message" : "messages"} found.`
        : "No messages found in active chats.";
    } catch (error) {
      if (generation !== requestGeneration || !form.isConnected) return;
      results.innerHTML = "";
      status.textContent = `Search unavailable: ${error.message}`;
    }
  };
  form.addEventListener("submit", event => { event.preventDefault(); void search(); });
  input.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => void search(), 220);
  });
  botFilter.addEventListener("change", () => { if (input.value.trim().length >= 2) void search(); });
  results.addEventListener("click", async event => {
    const result = event.target.closest("[data-search-conversation]");
    if (!result) return;
    const conversationId = result.dataset.searchConversation;
    const runId = result.dataset.searchRun;
    $("#modal-close")?.click();
    try {
      await openConversation(conversationId);
      if (runId) {
        const thread = $$("#chat-stream [data-run-id]").find(node => node.dataset.runId === runId);
        thread?.scrollIntoView({ block: "center", behavior: "instant" });
        if (thread) {
          thread.classList.add("message-search-target");
          setTimeout(() => thread.classList.remove("message-search-target"), 1600);
        }
      }
    } catch (error) {
      toast(`Could not open this conversation: ${error.message}`, true);
    }
  });
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
      if (["overview", "schedules", "runs", "bots"].includes(nav)) $("#monitor-nav").open = true;
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
  const menuBot = document.getElementById("roster-action-menu")?.dataset.botName || null;
  const focus = document.activeElement;
  const focusedMenuAction = focus?.matches?.("#roster-action-menu [data-menu-settings]") ? "settings"
    : focus?.matches?.("#roster-action-menu [data-menu-pin]") ? "pin"
      : focus?.matches?.("#roster-action-menu [data-menu-section]") ? "section"
        : focus?.matches?.("#roster-action-menu [data-menu-hide]") ? "hide" : null;
  const focusedBot = list.contains(focus) ? focus.dataset.switchBot : null;
  const focusedOptions = list.contains(focus) ? focus.dataset.botOptions : menuBot;
  closeRosterActionMenu(false);
  $("#fleet-nav").hidden = botsCache.length < 10;
  const q = ($("#bot-search")?.value || "").trim().toLowerCase();
  const coordinator = botsCache.find(b => b.is_workspace_coordinator);
  const matches = b => !q || `${b.display_name || b.name} ${b.name} ${b.description || ""}`.toLowerCase().includes(q);
  const byDisplayName = (a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name, undefined, { sensitivity: "base" })
    || a.name.localeCompare(b.name);
  const coordinatorMatch = coordinator && matches(coordinator) ? coordinator : null;
  const allMatching = botsCache.filter(matches);
  if (q) {
    const rows = allMatching.filter(b => b.id !== coordinator?.id).sort(byDisplayName);
    const rowHtml = b => rosterRowHtml(b, currentStudioBot);
    list.innerHTML = `${coordinatorMatch ? `<div class="roster-section roster-coordinator">${rosterRowHtml(coordinatorMatch, currentStudioBot)}</div>` : ""}
      ${rows.length ? `<section class="roster-section" aria-label="Bot search results"><h3 class="roster-section-title">Search results</h3>${rows.map(rowHtml).join("")}</section>`
        : `<div class="roster-empty">No bot matches.</div>`}`;
    wireRosterRows(list);
    wireRosterMenuButtons(list, menuBot, focusedMenuAction);
    return;
  }
  const hidden = botsCache.filter(b => b.id !== coordinator?.id && b.sidebar_hidden);
  const hiddenSpotlight = hidden.filter(b => botNeedsYou(b) || botState(b) !== "idle");
  const hiddenIdle = hidden.filter(b => !hiddenSpotlight.includes(b));
  const inRoster = botsCache.filter(b => b.id !== coordinator?.id && !b.sidebar_hidden);
  const visible = [...inRoster, ...hiddenSpotlight];
  const pinned = visible.filter(b => b.pinned).sort(byDisplayName);
  const remaining = visible.filter(b => !b.pinned).sort(byDisplayName);
  const currentChatBot = /^#\/chat(?:\/|$)/.test(location.hash || "#/chat") ? currentStudioBot : null;
  const needsYou = remaining.filter(b => botNeedsYou(b));
  const inProgress = remaining.filter(b => !botNeedsYou(b) && botState(b) !== "idle" && b.name !== currentChatBot);
  const current = remaining.filter(b => b.name === currentChatBot && !needsYou.includes(b) && !inProgress.includes(b));
  const spotlight = new Set([...needsYou, ...inProgress, ...current]);
  const idle = remaining.filter(b => !spotlight.has(b));
  const bots = [...(coordinatorMatch ? [coordinatorMatch] : []), ...pinned, ...remaining, ...hiddenIdle];
  if (!bots.length) {
    list.innerHTML = `<div class="roster-empty">${botsCache.length ? "No bot matches." : "No bots yet — create one."}</div>`;
    return;
  }
  const rowHtml = b => rosterRowHtml(b, currentStudioBot);
  const sections = [];
  if (coordinatorMatch) sections.push(`<div class="roster-section roster-coordinator">${rowHtml(coordinatorMatch)}</div>`);
  if (needsYou.length) sections.push(`<section class="roster-section" aria-label="Bots that need you">
    <h3 class="roster-section-title">Needs you</h3>${needsYou.map(rowHtml).join("")}</section>`);
  if (pinned.length) sections.push(`<section class="roster-section" aria-label="Pinned bots">
    <h3 class="roster-section-title">Pinned</h3>${pinned.map(rowHtml).join("")}</section>`);
  if (inProgress.length) sections.push(`<section class="roster-section" aria-label="Bots in progress">
    <h3 class="roster-section-title">In progress</h3>${inProgress.map(rowHtml).join("")}</section>`);
  if (current.length) sections.push(`<section class="roster-section" aria-label="Current chat bot">${current.map(rowHtml).join("")}</section>`);
  const bySection = new Map();
  for (const bot of idle.filter(item => item.roster_section)) {
    const label = bot.roster_section.trim();
    const key = label.toLocaleLowerCase();
    const group = bySection.get(key) || { label, bots: [] };
    group.bots.push(bot);
    bySection.set(key, group);
  }
  for (const [key, group] of [...bySection.entries()].sort((a, b) => a[1].label.localeCompare(b[1].label))) {
    const open = !!store$.get(`hutch:roster-section:${key}`, false);
    sections.push(`<details class="roster-section roster-idle-details roster-custom-details" data-roster-section="${esc(group.label)}" ${open ? "open" : ""}>
      <summary aria-label="${esc(group.label)}, ${group.bots.length} Bots">${esc(group.label)} <span class="roster-count">${group.bots.length}</span></summary>
      <div class="roster-section roster-idle-list">${group.bots.map(rowHtml).join("")}</div></details>`);
  }
  if (idle.length) {
    const ungrouped = idle.filter(item => !item.roster_section);
    const largeFleet = botsCache.length >= 10;
    if (!ungrouped.length) {
      // Every idle Bot is already reachable through a named section.
    } else if (largeFleet) {
      const allOpen = !!store$.get("hutch:roster-idle-open", false);
      sections.push(`<details class="roster-section roster-idle-details" id="roster-idle-details" ${allOpen ? "open" : ""}>
        <summary aria-controls="roster-idle-bots">All bots <span class="roster-count">${ungrouped.length}</span></summary>
        <div class="roster-section roster-idle-list" id="roster-idle-bots">${ungrouped.map(rowHtml).join("")}</div>
      </details>`);
    } else {
      sections.push(`<section class="roster-section" aria-label="All bots">
        ${pinned.length || needsYou.length || inProgress.length ? '<h3 class="roster-section-title">All bots</h3>' : ""}${ungrouped.map(rowHtml).join("")}</section>`);
    }
  }
  if (hiddenIdle.length) {
    const open = !!store$.get("hutch:roster-hidden-open", false);
    sections.push(`<details class="roster-section roster-idle-details roster-hidden-details" id="roster-hidden-details" ${open ? "open" : ""}>
      <summary aria-controls="roster-hidden-bots">Hidden bots <span class="roster-count">${hiddenIdle.length}</span></summary>
      <p class="roster-hidden-note">Hiding changes the roster only. Bot runs and schedules continue.</p>
      <div class="roster-section roster-idle-list" id="roster-hidden-bots">${hiddenIdle.map(rowHtml).join("")}</div>
    </details>`);
  }
  list.innerHTML = sections.join("");
  const idleDetails = $("#roster-idle-details");
  if (idleDetails) {
    if (q) idleDetails.open = true;
    idleDetails.addEventListener("toggle", () => store$.set("hutch:roster-idle-open", idleDetails.open));
  }
  $$(".roster-custom-details").forEach(details => details.addEventListener("toggle", () => {
    store$.set(`hutch:roster-section:${details.dataset.rosterSection.toLocaleLowerCase()}`, details.open);
  }));
  $("#roster-hidden-details")?.addEventListener("toggle", event => store$.set("hutch:roster-hidden-open", event.currentTarget.open));
  wireRosterRows(list);
  wireRosterMenuButtons(list, menuBot, focusedMenuAction);
  if (focus && !focus.isConnected && !document.getElementById("roster-action-menu")) {
    const replacement = focusedOptions
      ? $$("#roster-list [data-bot-options]").find(el => el.dataset.botOptions === focusedOptions)
      : focusedBot
      ? $$("[data-switch-bot]", list).find(el => el.dataset.switchBot === focusedBot)
      : null;
    (replacement || $("#bot-search"))?.focus({ preventScroll: true });
  }
}

function rosterRowHtml(bot, currentStudioBot) {
  const state = botState(bot);
  const pip = botNeedsYou(bot) ? "waiting" : state === "running" ? "running" : state === "paused" ? "paused" : "";
  const word = botNeedsYou(bot) ? "Needs you" : botStatusLabel(bot);
  const subtitle = [bot.is_workspace_coordinator ? "Coordinator" : "", bot.sidebar_hidden ? "Hidden" : "", word]
    .filter(Boolean).join(" · ");
  return `
    <div class="roster-entry"><button class="roster-row" type="button" data-switch-bot="${esc(bot.name)}"
      ${bot.name === currentStudioBot && location.hash.startsWith("#/chat") ? 'aria-current="true"' : ""}
      title="${esc(bot.display_name || bot.name)} — ${esc(subtitle)}">
      ${botAvatar(bot.name, 30, pip)}
      <span class="roster-id">
        <span class="roster-name">${esc(bot.display_name || bot.name)}</span>
        <span class="roster-sub">${esc(subtitle)}</span>
      </span>
    </button><button class="icon-btn roster-options" type="button" data-bot-options="${esc(bot.name)}"
      aria-label="Options for ${esc(bot.display_name || bot.name)}" aria-haspopup="menu" aria-expanded="false"
      title="Bot options">${icon("moreHorizontal")}</button></div>`;
}

function wireRosterRows(list) {
  $$("[data-switch-bot]", list).forEach(row =>
    row.addEventListener("click", () => { location.hash = `#/chat/${encodeURIComponent(row.dataset.switchBot)}`; }));
}

function wireRosterMenuButtons(list, menuBot, focusedMenuAction) {
  $$("[data-bot-options]", list).forEach(button => button.addEventListener("click", () => openRosterActionMenu(button)));
  if (!menuBot) return;
  const trigger = $$("[data-bot-options]", list).find(button => button.dataset.botOptions === menuBot);
  if (!trigger) return;
  openRosterActionMenu(trigger);
  const menu = document.getElementById("roster-action-menu");
  const selector = focusedMenuAction === "settings" ? "[data-menu-settings]"
    : focusedMenuAction === "pin" ? "[data-menu-pin]"
      : focusedMenuAction === "section" ? "[data-menu-section]"
        : focusedMenuAction === "hide" ? "[data-menu-hide]" : '[role="menuitem"]';
  menu?.querySelector(selector)?.focus({ preventScroll: true });
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

async function openWorkspaceModelDefaultsDialog() {
  let defaults;
  try { defaults = await api("/v1/preferences/model-defaults"); }
  catch (err) { toast(`Workspace defaults are unavailable: ${err.message}`, true); return; }
  const initialMode = defaults.inference_mode || "hybrid";
  let routeChoices = [];
  try { routeChoices = await api(`/v1/model-routes?inference_mode=${encodeURIComponent(initialMode)}`); }
  catch { /* a route can still be entered and the server validates it on save */ }
  const optionHtml = routes => routes.filter(route => route.state === "ready" && !route.spec.startsWith("mock/"))
    .map(route => `<option value="${esc(route.spec)}" label="${esc(`${route.group}: ${route.note || route.label}`)}"></option>`).join("");
  const bodyHtml = `<div class="setup-conversation form-grid">
      <p class="setup-assistant">These defaults seed new Bot drafts. They do not change existing Bots, chats or runs. Hosted routes send prompts to their provider; Local routing keeps inference on this machine while tools may still use the network. Strict Offline requires verified host isolation.</p>
      <label class="field" for="workspace-default-model">Default model route<input id="workspace-default-model" list="workspace-default-routes" maxlength="200" autocomplete="off" placeholder="Choose or enter provider/model" value="${esc(defaults.model || "")}">
        <datalist id="workspace-default-routes">${optionHtml(routeChoices)}</datalist>
        <span class="hint">Leave empty to choose a route for each new Bot. Existing Bots keep their own saved model.</span></label>
      <label class="field" for="workspace-default-mode">Default routing<select id="workspace-default-mode">
        <option value="hybrid" ${initialMode === "hybrid" ? "selected" : ""}>Hybrid — local or hosted</option>
        <option value="local" ${initialMode === "local" ? "selected" : ""}>Local — this machine</option>
        <option value="offline" ${initialMode === "offline" ? "selected" : ""}>Strict Offline — host-gated</option>
      </select></label>
      <p class="hint" role="status" aria-live="polite">${defaults.configured ? "A saved default is shown. Review availability before using it for a new Bot." : "No workspace model default is set."}</p>
      <div id="workspace-default-error" role="alert" hidden></div>
    </div>`;
  openModal({
    title: "Model defaults for new Bots", bodyHtml, confirmText: "Save workspace defaults",
    returnFocus: $("#prefs-toggle"),
    onConfirm: async () => {
      const model = $("#workspace-default-model")?.value.trim() || "";
      const inference_mode = $("#workspace-default-mode")?.value || "hybrid";
      const error = $("#workspace-default-error");
      error.hidden = true;
      try {
        const saved = await api("/v1/preferences/model-defaults", {
          method: "PUT", body: { model, inference_mode },
        });
        toast(saved.configured ? "Workspace defaults saved for future Bots." : "Workspace model default cleared.");
        return true;
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
        return false;
      }
    },
  });
  $("#workspace-default-mode")?.addEventListener("change", async ev => {
    try {
      routeChoices = await api(`/v1/model-routes?inference_mode=${encodeURIComponent(ev.target.value)}`);
      const list = $("#workspace-default-routes");
      if (list) list.innerHTML = optionHtml(routeChoices);
    } catch { /* existing or manually entered routes remain editable */ }
  });
}

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
  $("#prefs-model-defaults")?.addEventListener("click", () => {
    pop.hidden = true;
    t.setAttribute("aria-expanded", "false");
    openWorkspaceModelDefaultsDialog();
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

function conversationOptionText(conversation) {
  return `${conversation.unread ? "Unread · " : ""}${conversation.is_legacy ? "Imported · " : ""}${conversation.title || "New conversation"}`;
}

function conversationOptionGroup(label, conversations) {
  if (!conversations.length) return "";
  return `<optgroup label="${esc(label)}">${conversations.map(conversation =>
    `<option value="${esc(conversation.id)}">${esc(conversationOptionText(conversation))}</option>`).join("")}</optgroup>`;
}

function conversationOptionsHtml(conversations, selectedId) {
  const active = conversations.filter(item => !item.archived);
  const pinned = active.filter(item => item.pinned);
  const unpinned = active.filter(item => !item.pinned);
  const sections = new Map();
  for (const conversation of unpinned.filter(item => item.section)) {
    const label = conversation.section.trim();
    const key = label.toLocaleLowerCase();
    if (!sections.has(key)) sections.set(key, { label, items: [] });
    sections.get(key).items.push(conversation);
  }
  const groupedIds = new Set([...sections.values()].flatMap(group => group.items.map(item => item.id)));
  const recent = unpinned.filter(item => !groupedIds.has(item.id));
  const archived = conversations.filter(item => item.archived);
  return [
    conversationOptionGroup("Pinned chats", pinned),
    ...[...sections.values()].sort((a, b) => a.label.localeCompare(b.label))
      .map(group => conversationOptionGroup(group.label, group.items)),
    conversationOptionGroup("Recent chats", recent),
    conversationOptionGroup("Archived chats", archived),
  ].join("").replace(`<option value="${esc(selectedId)}">`, `<option value="${esc(selectedId)}" selected>`);
}

function closeStudioConversationMenu(restoreFocus = false) {
  const details = $("#studio-conversation-actions");
  if (!details) return;
  const moreActions = $("#studio-conversation-more");
  if (moreActions) {
    moreActions.open = false;
    $("#studio-conversation-more > summary")?.setAttribute("aria-expanded", "false");
  }
  details.open = false;
  if (restoreFocus) $("#studio-conversation-options")?.focus({ preventScroll: true });
}

function syncConversationMenuLabels(conversation) {
  const pin = $("#studio-conversation-pin");
  if (pin) pin.innerHTML = `${icon("pin")} ${conversation.pinned ? "Unpin conversation" : "Pin conversation"}`;
  const unread = $("#studio-conversation-unread");
  if (unread) unread.innerHTML = `${icon("mail")} ${conversation.unread ? "Mark read" : "Mark unread"}`;
  const section = $("#studio-conversation-section");
  if (section) section.innerHTML = `${icon("folder")} ${conversation.section ? "Move to a section" : "New section"}`;
  const archive = $("#studio-archive-conversation");
  if (archive) archive.innerHTML = `${icon("inbox")} ${conversation.archived ? "Restore conversation" : "Archive conversation"}`;
}

function editStudioConversationSection(conversation) {
  closeStudioConversationMenu(false);
  openModal({
    title: conversation.section ? "Move chat to a section" : "New chat section",
    bodyHtml: `<p>Group related conversations for this Bot. Reusing a name places chats together.</p>
      <label class="field" for="conversation-section-name">Section name
        <input id="conversation-section-name" type="text" maxlength="40" autocomplete="off" value="${esc(conversation.section || "")}" placeholder="For example, Client work">
      </label>
      <p class="hint">Leave this empty to move the chat to Recent chats.</p>
      <p id="conversation-section-error" class="form-error" role="status" aria-live="polite"></p>`,
    confirmText: "Save section",
    returnFocus: $("#studio-conversation-options"),
    onConfirm: async () => {
      const input = $("#conversation-section-name");
      const section = input.value.trim().replace(/\s+/g, " ");
      if (section.length > 40) {
        $("#conversation-section-error").textContent = "Section names can be up to 40 characters.";
        input.focus();
        return false;
      }
      const confirm = $("#modal-confirm");
      confirm.disabled = true;
      try {
        const saved = await api(`/v1/conversations/${encodeURIComponent(conversation.id)}/preferences`, {
          method: "PATCH", headers: { "Idempotency-Key": newIdempotencyKey() },
          body: { section: section || null },
        });
        Object.assign(conversation, saved);
        const select = $("#conversation-switcher");
        if (select) select.innerHTML = conversationOptionsHtml(currentConversations, conversation.id);
        syncConversationMenuLabels(conversation);
        announce(section ? `Conversation moved to ${section}.` : "Conversation moved to Recent chats.");
        return true;
      } catch (error) {
        confirm.disabled = false;
        $("#conversation-section-error").textContent = `Could not save this section: ${error.message}`;
        return false;
      }
    },
  });
}

function renameStudioConversation(conversation) {
  closeStudioConversationMenu(false);
  openModal({
    title: "Rename conversation",
    bodyHtml: `<p>Give this chat a short name that helps you find it later.</p>
      <label class="field" for="conversation-title-input">Conversation name
        <input id="conversation-title-input" type="text" maxlength="120" autocomplete="off" value="${esc(conversation.title || "New conversation")}" required>
      </label>
      <p id="conversation-title-error" class="form-error" role="status" aria-live="polite"></p>`,
    confirmText: "Save name",
    returnFocus: $("#studio-conversation-options"),
    onConfirm: async () => {
      const input = $("#conversation-title-input");
      const title = input.value.trim().replace(/\s+/g, " ");
      if (!title || title.length > 120) {
        $("#conversation-title-error").textContent = "Enter a name of up to 120 characters.";
        input.focus();
        return false;
      }
      const confirm = $("#modal-confirm");
      confirm.disabled = true;
      try {
        const saved = await api(`/v1/conversations/${encodeURIComponent(conversation.id)}/title`, {
          method: "PATCH", headers: { "Idempotency-Key": newIdempotencyKey() }, body: { title },
        });
        Object.assign(conversation, saved);
        const listedConversation = currentConversations.find(item => item.id === conversation.id);
        if (listedConversation && listedConversation !== conversation) Object.assign(listedConversation, saved);
        const select = $("#conversation-switcher");
        if (select) select.innerHTML = conversationOptionsHtml(currentConversations, conversation.id);
        announce(`Conversation renamed to ${saved.title}.`);
        toast(`Conversation renamed to ${saved.title}.`);
        return true;
      } catch (error) {
        confirm.disabled = false;
        $("#conversation-title-error").textContent = `Could not rename this conversation: ${error.message}`;
        return false;
      }
    },
  });
}

async function prepareConversationTaskTemplate(conversation, returnFocus, saveToLibrary = false) {
  try {
    const page = await api(`/v1/conversations/${encodeURIComponent(conversation.id)}?after=0&limit=100`);
    const firstRequest = (page.messages || []).find(message => message.role === "user" && String(message.content || "").trim());
    if (!firstRequest) {
      toast("This conversation has no user request to save as a template yet.", true);
      return;
    }
    const prompt = String(firstRequest.content || "");
    openModal({
      title: saveToLibrary ? "Save reusable request" : "Download task template",
      bodyHtml: `<p>This uses the first request only. Later messages, assistant replies, tool activity, files, and account data are excluded.</p>
        <label class="field" for="task-template-name">Template name
          <input id="task-template-name" type="text" maxlength="80" autocomplete="off" value="${esc(conversation.title || "Task template")}" required>
        </label>
        <label class="field" for="task-template-prompt">Reusable request
          <textarea id="task-template-prompt" rows="8" maxlength="12000" required>${esc(prompt)}</textarea>
        </label>
        <p class="hint">Review and edit both fields. ${saveToLibrary
          ? "This stays in Hutch’s local database and is included in local state backups. It is not shared with a provider or another person."
          : "This downloads a local JSON file; nothing is uploaded. Loading it later only fills a draft."}</p>
        <p id="task-template-error" class="form-error" role="status" aria-live="polite"></p>`,
      confirmText: saveToLibrary ? "Save request" : "Download template",
      wide: true,
      returnFocus,
      onConfirm: async () => {
        const nameInput = $("#task-template-name");
        const promptInput = $("#task-template-prompt");
        const name = nameInput.value.trim().replace(/\s+/g, " ");
        const reusablePrompt = promptInput.value.trim();
        const error = $("#task-template-error");
        if (!name || name.length > 80) {
          error.textContent = "Enter a template name of up to 80 characters.";
          nameInput.focus();
          return false;
        }
        if (!reusablePrompt || reusablePrompt.length > 12000) {
          error.textContent = "Enter a request of up to 12,000 characters.";
          promptInput.focus();
          return false;
        }
        const taskTemplate = { kind: "hutch-task-template", version: 1, name, prompt: reusablePrompt };
        if (saveToLibrary) {
          const confirm = $("#modal-confirm");
          confirm.disabled = true;
          try {
            await api("/v1/task-templates", {
              method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() },
              body: { name, prompt: reusablePrompt },
            });
            toast(`“${name}” saved to your reusable requests.`);
            announce(`Saved reusable request ${name}. It has not been sent.`);
            return true;
          } catch (error) {
            confirm.disabled = false;
            $("#task-template-error").textContent = `Could not save this request: ${error.message}`;
            return false;
          }
        }
        const blob = new Blob([JSON.stringify(taskTemplate, null, 2) + "\n"], { type: "application/json;charset=utf-8" });
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = `${name.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "task"}-template.json`;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        return true;
      },
    });
  } catch (error) {
    toast(`Could not prepare this task template: ${error.message}`, true);
  }
}

async function openSavedTaskTemplateLibrary({ returnFocus, onUse }) {
  let templates;
  try {
    templates = await api("/v1/task-templates?limit=100");
  } catch (error) {
    toast(`Could not load saved requests: ${error.message}`, true);
    return;
  }
  const renderItems = query => {
    const normalized = query.trim().toLocaleLowerCase();
    const matches = templates.filter(item => !normalized || `${item.name}\n${item.prompt}`.toLocaleLowerCase().includes(normalized));
    const list = $("#saved-task-template-list");
    if (!list) return;
    list.innerHTML = matches.length ? matches.map(item => `
      <article class="saved-request-card" role="listitem" data-saved-request="${esc(item.id)}">
        <div class="saved-request-copy"><h4>${esc(item.name)}</h4><p>${esc(item.prompt.slice(0, 220))}${item.prompt.length > 220 ? "…" : ""}</p></div>
        <div class="saved-request-actions">
          <button class="btn primary small" type="button" data-saved-request-use="${esc(item.id)}">Use request</button>
          <button class="btn ghost small" type="button" data-saved-request-edit="${esc(item.id)}">Edit</button>
          <button class="btn ghost small" type="button" data-saved-request-delete="${esc(item.id)}">Delete</button>
        </div>
      </article>`).join("") : `<p class="hint saved-request-empty">${templates.length
        ? "No saved requests match that search."
        : "No saved requests yet. Open a chat’s More menu and save its first request, or import a task-template file."}</p>`;
  };
  openModal({
    title: "Saved requests",
    bodyHtml: `<p class="hint">Choose a request to place it in this chat’s draft. Nothing is sent until you review and send it.</p>
      <label class="field" for="saved-task-template-search">Find a saved request
        <input id="saved-task-template-search" type="search" autocomplete="off" placeholder="Search by name or request">
      </label>
      <div class="saved-request-list" id="saved-task-template-list" role="list" aria-label="Saved requests"></div>`,
    confirmText: "Done", showCancel: false, wide: true, returnFocus,
  });
  const search = $("#saved-task-template-search");
  search.addEventListener("input", () => renderItems(search.value));
  renderItems("");
  const scheduleLibraryRefresh = () => setTimeout(() => void openSavedTaskTemplateLibrary({ returnFocus, onUse }), 0);
  $("#saved-task-template-list").addEventListener("click", async event => {
    const use = event.target.closest("[data-saved-request-use]");
    const edit = event.target.closest("[data-saved-request-edit]");
    const remove = event.target.closest("[data-saved-request-delete]");
    const id = use?.dataset.savedRequestUse || edit?.dataset.savedRequestEdit || remove?.dataset.savedRequestDelete;
    const template = templates.find(item => item.id === id);
    if (!template) return;
    if (use) {
      try {
        onUse(template);
        $("#modal-confirm")?.click();
        requestAnimationFrame(() => $("#chat-prompt")?.focus({ preventScroll: true }));
      } catch (error) {
        toast(`Could not use this request: ${error.message}`, true);
      }
      return;
    }
    if (edit) {
      openModal({
        title: "Edit saved request",
        bodyHtml: `<p class="hint">This changes only the local reusable request. It does not change any Bot or past message.</p>
          <label class="field" for="saved-task-template-name">Request name
            <input id="saved-task-template-name" maxlength="80" value="${esc(template.name)}" required>
          </label>
          <label class="field" for="saved-task-template-prompt">Request text
            <textarea id="saved-task-template-prompt" rows="8" maxlength="12000" required>${esc(template.prompt)}</textarea>
          </label>
          <p id="saved-task-template-error" class="form-error" role="status" aria-live="polite"></p>`,
        confirmText: "Save changes", wide: true, returnFocus,
        onCancel: scheduleLibraryRefresh,
        onConfirm: async () => {
          const name = $("#saved-task-template-name").value.trim().replace(/\s+/g, " ");
          const prompt = $("#saved-task-template-prompt").value.trim();
          const error = $("#saved-task-template-error");
          if (!name || name.length > 80 || !prompt || prompt.length > 12000) {
            error.textContent = "Add a name up to 80 characters and request text up to 12,000 characters.";
            return false;
          }
          const confirm = $("#modal-confirm");
          confirm.disabled = true;
          try {
            await api(`/v1/task-templates/${encodeURIComponent(template.id)}`, {
              method: "PUT", headers: { "Idempotency-Key": newIdempotencyKey() },
              body: { name, prompt, expected_revision: template.revision },
            });
            toast(`Saved changes to “${name}”.`);
            scheduleLibraryRefresh();
            return true;
          } catch (error) {
            confirm.disabled = false;
            $("#saved-task-template-error").textContent = `Could not update this request: ${error.message}`;
            return false;
          }
        },
      });
      return;
    }
    if (remove) {
      openModal({
        title: "Delete saved request?",
        bodyHtml: `<p>“${esc(template.name)}” will be removed from this local library. Existing drafts and chat history are unchanged.</p>`,
        confirmText: "Delete request", confirmClass: "danger", returnFocus,
        onCancel: scheduleLibraryRefresh,
        onConfirm: async () => {
          const confirm = $("#modal-confirm");
          confirm.disabled = true;
          try {
            await api(`/v1/task-templates/${encodeURIComponent(template.id)}?expected_revision=${template.revision}`, {
              method: "DELETE", headers: { "Idempotency-Key": newIdempotencyKey() },
            });
            templates = templates.filter(item => item.id !== template.id);
            toast(`Deleted “${template.name}”.`);
            scheduleLibraryRefresh();
            return true;
          } catch (error) {
            confirm.disabled = false;
            toast(`Could not delete this request: ${error.message}`, true);
            return false;
          }
        },
      });
    }
  });
}

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
            botsCache.find(b => b.is_workspace_coordinator) ||
            botsCache[0];
  currentStudioBot = bot.name;
  const detail = await api(`/bots/${encodeURIComponent(bot.name)}`);
  if (generation !== studioGeneration) return;
  currentConversations = await api(`/v1/conversations?bot=${encodeURIComponent(bot.id)}&include_legacy=true&include_archived=true&limit=100`);
  if (generation !== studioGeneration) return;
  const rememberedConversation = storageGet(`hutch-conversation:${bot.id}`);
  let selectedConversation = currentConversations.find(c => c.id === rememberedConversation) || null;
  if (!selectedConversation) selectedConversation = currentConversations.find(c => !c.archived && !c.is_legacy) || null;
  if (!selectedConversation) {
    selectedConversation = await createStudioConversation(bot);
    currentConversations.unshift(selectedConversation);
  }
  if (generation !== studioGeneration) return;
  if (currentConversationId !== selectedConversation.id && selectedConversation.unread) {
    try {
      Object.assign(selectedConversation, await api(`/v1/conversations/${encodeURIComponent(selectedConversation.id)}/preferences`, {
        method: "PATCH", headers: { "Idempotency-Key": newIdempotencyKey() }, body: { unread: false },
      }));
    } catch (error) {
      toast(`This chat is still marked unread because its read state could not be updated: ${error.message}`, true);
    }
  }
  currentConversationId = selectedConversation.id;
  storageSet(`hutch-conversation:${bot.id}`, currentConversationId);
  const activeRun = selectedConversation.active_run_id ? {
    id: selectedConversation.active_run_id, status: selectedConversation.active_run_status,
    status_label: selectedConversation.active_run_status_label,
  } : null;
  currentRunId = activeRun?.id || selectedConversation.latest_run_id || null;

  const state = botState(detail);
  const botTitle = bot.display_name || bot.name;
  const botTitleParts = botTitle.split(" · ");
  const botHeading = botTitleParts.length > 1 ? botTitleParts.slice(0, -1).join(" · ") : botTitle;
  const botRole = botTitleParts.length > 1 ? botTitleParts[botTitleParts.length - 1] : "";
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(bot.name, 30, state === "running" ? "running" : state === "paused" ? "paused" : "")}
        <div class="ctx-heading">
          <h1>${esc(botHeading)}</h1>
          <span class="ctx-subtitle" title="${esc(botRole)}">AI bot${botRole ? ` · ${esc(botRole)}` : ""}</span>
        </div>
        <div class="ctx-meta${bot.is_workspace_coordinator ? " workspace-coordinator-meta" : ""}">
          ${bot.is_workspace_coordinator ? '<span class="tag" id="workspace-coordinator-pill" aria-label="Workspace coordinator"><span class="coordinator-label-wide">Workspace coordinator</span><span class="coordinator-label-compact" aria-hidden="true">Coordinator</span></span>' : ""}
          ${bot.paused ? '<span class="tag">paused</span>' : ""}
        ${activeRun ? statusChip(activeRun.status, activeRun.status_label) : ""}
      </div>
    </div>
    <div class="ctx-actions">
      <label class="visually-hidden" for="conversation-switcher">Conversation</label>
      <select class="conversation-select" id="conversation-switcher" aria-label="Conversation">
        ${conversationOptionsHtml(currentConversations, currentConversationId)}
      </select>
      <button class="icon-btn studio-search-button" id="studio-search-messages" type="button"
        aria-label="Search chats" title="Search chats">${icon("search")}</button>
      <details class="conversation-actions" id="studio-conversation-actions">
        <summary class="icon-btn" id="studio-conversation-options" aria-label="Conversation options" title="Conversation options">${icon("moreHorizontal")}</summary>
        <div class="conversation-actions-panel" aria-label="Conversation actions">
          <button class="conversation-action-item" id="studio-new-conversation" data-conversation-action="new" type="button">${icon("plus")} New conversation</button>
          <button class="conversation-action-item" id="studio-rename-conversation" data-conversation-action="rename" type="button">${icon("chat")} Rename conversation</button>
          <button class="conversation-action-item" id="studio-conversation-pin" data-conversation-action="pin" type="button">${icon("pin")} ${selectedConversation.pinned ? "Unpin conversation" : "Pin conversation"}</button>
          <button class="conversation-action-item" id="studio-conversation-unread" data-conversation-action="unread" type="button">${icon("mail")} ${selectedConversation.unread ? "Mark read" : "Mark unread"}</button>
          <button class="conversation-action-item" id="studio-conversation-section" data-conversation-action="section" type="button">${icon("folder")} ${selectedConversation.section ? "Move to a section" : "New section"}</button>
          <details class="conversation-action-more" id="studio-conversation-more">
            <summary class="conversation-action-item" aria-label="More conversation actions" aria-expanded="false" aria-controls="studio-conversation-more-panel">${icon("moreHorizontal")} More</summary>
            <div class="conversation-action-more-panel" id="studio-conversation-more-panel">
              <button class="conversation-action-item" id="studio-conversation-template-save" data-conversation-action="template-save" type="button">${icon("fileText")} Save reusable request</button>
              <button class="conversation-action-item" id="studio-conversation-template-download" data-conversation-action="template-download" type="button">${icon("fileText")} Download task template</button>
              <button class="conversation-action-item" id="studio-conversation-export" data-conversation-action="export" type="button">${icon("fileText")} Export conversation</button>
              ${!selectedConversation.is_legacy ? `<span class="conversation-action-divider" aria-hidden="true"></span>
                <button class="conversation-action-item" id="studio-archive-conversation" data-conversation-action="archive" type="button" ${activeRun ? "hidden" : ""}>${icon("inbox")} ${selectedConversation.archived ? "Restore conversation" : "Archive conversation"}</button>` : ""}
            </div>
          </details>
        </div>
      </details>
      <button class="btn ghost small" id="studio-review-run" type="button" ${activeRun?.status === "waiting_approval" ? "" : "hidden"}>${icon("shield")} Review</button>
      <button class="btn danger small" id="studio-stop-run" type="button" data-stop-target="${esc(activeRun?.id || "")}" ${activeRun ? "" : "hidden"}>${icon("stop")} Stop</button>
      <a class="btn ghost small" href="#/bot/${esc(bot.name)}">${icon("sliders")} Settings</a>
    </div>`);
  $("#studio-search-messages")?.addEventListener("click", event => openConversationSearch(event.currentTarget));

  view.innerHTML = `
    <section class="studio">
      <div class="chat-scroll" id="chat-scroll">
        <div class="feed" id="chat-stream"></div>
      </div>
      <footer class="composer">
        <form id="chat-form" autocomplete="off">
          <div class="composer-box" id="composer-box">
            <div class="reply-composer" id="reply-composer" hidden>
              <div class="reply-composer-preview" id="reply-composer-preview" role="status" aria-live="polite"></div>
              <button class="btn ghost small" id="reply-composer-clear" type="button" aria-label="Remove reply reference">Remove</button>
            </div>
            <div class="reply-composer workspace-result-composer" id="workspace-result-composer" hidden>
              <div class="reply-composer-preview" id="workspace-result-composer-preview" role="status" aria-live="polite"></div>
              <button class="btn ghost small" id="workspace-result-composer-clear" type="button" aria-label="Remove specialist result reference">Remove</button>
            </div>
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
                  <button class="cmenu-files" id="prompt-template-library-open" type="button">${icon("fileText")} Browse saved requests</button>
                  <button class="cmenu-files" id="prompt-template-import" type="button" aria-controls="task-template-file">Import task-template file</button>
                  <input class="visually-hidden" id="task-template-file" type="file" accept=".json,application/json">
                  <button class="cmenu-files" id="conversation-files-open" type="button">${icon("folder")} Browse files in this chat</button>
                  <button class="cmenu-files" id="conversation-export-open" type="button">Export conversation as JSON</button>
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
              <label class="visually-hidden" for="chat-prompt">Message ${esc(bot.display_name || bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message ${esc(bot.display_name || bot.name)}…" aria-describedby="chat-help"></textarea>
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
  conversationSwitcher?.addEventListener("change", async ev => {
    const selectedId = ev.target.value;
    storageSet(`hutch-conversation:${bot.id}`, selectedId);
    const target = currentConversations.find(item => item.id === selectedId);
    if (target?.unread) {
      try {
        Object.assign(target, await api(`/v1/conversations/${encodeURIComponent(selectedId)}/preferences`, {
          method: "PATCH", headers: { "Idempotency-Key": newIdempotencyKey() }, body: { unread: false },
        }));
      } catch (error) {
        toast(`This chat is still marked unread because its read state could not be updated: ${error.message}`, true);
      }
    }
    await renderChatStudio(bot.name);
  });
  studioConversationMenuCleanup?.();
  const conversationActions = $("#studio-conversation-actions");
  const conversationOptions = $("#studio-conversation-options");
  conversationActions?.addEventListener("toggle", () =>
    conversationOptions?.setAttribute("aria-expanded", String(conversationActions.open)));
  const moreConversationActions = $("#studio-conversation-more");
  const moreConversationActionsSummary = $("#studio-conversation-more > summary");
  moreConversationActions?.addEventListener("toggle", () =>
    moreConversationActionsSummary?.setAttribute("aria-expanded", String(moreConversationActions.open)));
  const closeOnOutsidePress = event => {
    if (conversationActions?.open && !conversationActions.contains(event.target)) closeStudioConversationMenu(false);
  };
  const closeOnEscape = event => {
    if (event.key === "Escape" && conversationActions?.open) {
      event.preventDefault();
      if (moreConversationActions?.open) {
        moreConversationActions.open = false;
        moreConversationActionsSummary?.focus({ preventScroll: true });
        return;
      }
      closeStudioConversationMenu(true);
    }
  };
  document.addEventListener("pointerdown", closeOnOutsidePress, true);
  document.addEventListener("keydown", closeOnEscape, true);
  studioConversationMenuCleanup = () => {
    document.removeEventListener("pointerdown", closeOnOutsidePress, true);
    document.removeEventListener("keydown", closeOnEscape, true);
  };
  conversationActions?.addEventListener("click", async event => {
    const action = event.target.closest("[data-conversation-action]");
    if (!action || action.disabled) return;
    const kind = action.dataset.conversationAction;
    if (kind === "new") {
      closeStudioConversationMenu(false);
      action.disabled = true;
      try {
        const conversation = await createStudioConversation(bot);
        storageSet(`hutch-conversation:${bot.id}`, conversation.id);
        await renderChatStudio(bot.name);
      } catch (error) {
        toast(`Could not create a conversation: ${error.message}`, true);
        action.disabled = false;
      }
      return;
    }
    if (kind === "section") {
      editStudioConversationSection(selectedConversation);
      return;
    }
    if (kind === "rename") {
      renameStudioConversation(selectedConversation);
      return;
    }
    if (kind === "template-save" || kind === "template-download") {
      closeStudioConversationMenu(false);
      void prepareConversationTaskTemplate(selectedConversation, conversationOptions, kind === "template-save");
      return;
    }
    if (kind === "export") {
      closeStudioConversationMenu(false);
      action.disabled = true;
      try {
        const payload = await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}/export`);
        const excluded = payload.scope?.excluded || [];
        openModal({
          title: "Export conversation",
          bodyHtml: `<p>${esc(payload.scope?.notice || "Review the file before sharing it.")}</p>
            <p><b>Included:</b> ${esc((payload.scope?.included || []).join(", ") || "Conversation details")}</p>
            <p><b>Excluded:</b> ${esc(excluded.join(", ") || "No excluded data listed")}</p>
            <p class="hint">This downloads a local JSON file. Hutch will not send or publish it.</p>`,
          confirmText: "Download JSON",
          returnFocus: conversationOptions,
          onConfirm: async () => {
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
            const objectUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = objectUrl;
            anchor.download = `${bot.name}-${(selectedConversation.title || "conversation").toLowerCase()
              .replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "conversation"}.json`;
            anchor.click();
            setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
            return true;
          },
        });
      } catch (error) {
        toast(`Could not prepare this export: ${error.message}`, true);
      } finally {
        action.disabled = false;
      }
      return;
    }
    if (kind === "archive") {
      const archived = !selectedConversation.archived;
      action.disabled = true;
      closeStudioConversationMenu(false);
      try {
        await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}/archive`, {
          method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() }, body: { archived },
        });
        if (archived) storageRemove(`hutch-conversation:${bot.id}`);
        toast(archived ? "Conversation archived; restore it from Archived chats." : "Conversation restored.");
        await renderChatStudio(bot.name);
      } catch (error) {
        toast(`Could not update this conversation: ${error.message}`, true);
        action.disabled = false;
      }
      return;
    }
    const changes = kind === "pin" ? { pinned: !selectedConversation.pinned }
      : kind === "unread" ? { unread: !selectedConversation.unread } : null;
    if (!changes) return;
    action.disabled = true;
    try {
      const saved = await api(`/v1/conversations/${encodeURIComponent(currentConversationId)}/preferences`, {
        method: "PATCH", headers: { "Idempotency-Key": newIdempotencyKey() }, body: changes,
      });
      Object.assign(selectedConversation, saved);
      action.disabled = false;
      const select = $("#conversation-switcher");
      if (select) select.innerHTML = conversationOptionsHtml(currentConversations, currentConversationId);
      syncConversationMenuLabels(selectedConversation);
      closeStudioConversationMenu(true);
      const message = kind === "pin" ? `Conversation ${saved.pinned ? "pinned" : "unpinned"}.`
        : saved.unread ? "Marked unread. It will be marked read when you open this chat again."
          : "Conversation marked read.";
      announce(message);
      toast(message);
    } catch (error) {
      toast(`Could not update this conversation: ${error.message}`, true);
      action.disabled = false;
      action.focus();
    }
  });

  // wire composer
  const form = $("#chat-form"), txt = $("#chat-prompt"), sendBtn = $("#chat-send");
  const box = $("#composer-box");
  const switcher = window.hutchModelSwitcher?.mount($("#model-switch-slot"), detail, selectedConversation.id);
  if (selectedConversation.archived) {
    txt.disabled = true;
    txt.placeholder = "This conversation is archived. Start a new one to continue.";
    sendBtn.disabled = true;
  }

  const composerConversationId = selectedConversation.id;
  const composerDraftId = `${bot.name}:${composerConversationId}`;
  const replyStorageKey = `hutch-reply:${composerDraftId}`;
  const workspaceResultStorageKey = `hutch-workspace-result:${composerDraftId}`;
  let selectedReply = null;
  let selectedWorkspaceTaskResult = null;
  let replySelectionGeneration = 0;
  const replyComposer = $("#reply-composer");
  const workspaceResultComposer = $("#workspace-result-composer");
  const setReply = (message, persist = true) => {
    if (message && selectedWorkspaceTaskResult) setWorkspaceTaskResult(null);
    selectedReply = message;
    if (message) {
      if (persist) storageSet(replyStorageKey, message.id);
      const excerpt = String(message.content || "").slice(0, 240);
      $("#reply-composer-preview").innerHTML = `<span class="reply-composer-by">Replying to ${esc(botDisplayName(bot))}</span><span class="reply-composer-text">${esc(excerpt)}${message.content?.length > 240 ? "…" : ""}</span>`;
      replyComposer.hidden = false;
    } else {
      if (persist) storageRemove(replyStorageKey);
      replyComposer.hidden = true;
      $("#reply-composer-preview").textContent = "";
    }
  };
  const setWorkspaceTaskResult = (task, persist = true) => {
    if (task && selectedReply) setReply(null);
    selectedWorkspaceTaskResult = task ? {
      id: task.id,
      result_message_id: task.result_message_id,
      target_display_name: task.target_display_name,
      result: task.result || "",
      result_truncated: Boolean(task.result_truncated),
    } : null;
    if (selectedWorkspaceTaskResult) {
      if (persist) storageSet(workspaceResultStorageKey, JSON.stringify({
        task_id: task.id, result_message_id: task.result_message_id,
      }));
      const excerpt = String(task.result || "").replace(/\s+/g, " ").slice(0, 150);
      const coordinatorName = botDisplayName(bot);
      $("#workspace-result-composer-preview").innerHTML =
        `<span class="reply-composer-by">Sharing ${esc(task.target_display_name)}’s response with ${esc(coordinatorName)}</span>` +
        `<span class="reply-composer-text">${esc(excerpt)}${task.result_truncated || task.result?.length > 150 ? "…" : ""}</span>` +
        `<span class="reply-composer-note">Only this response is sent as untrusted context. Files, memory and permissions stay private.</span>`;
      workspaceResultComposer.hidden = false;
    } else {
      if (persist) storageRemove(workspaceResultStorageKey);
      workspaceResultComposer.hidden = true;
      $("#workspace-result-composer-preview").textContent = "";
    }
  };
  activeWorkspaceResultSelectionHandler = async (taskId, resultMessageId) => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    const selectionRequest = ++replySelectionGeneration;
    try {
      const tasks = await api(`/v1/workspace/tasks?conversation_id=${encodeURIComponent(composerConversationId)}&limit=100`);
      if (generation !== studioGeneration || composerConversationId !== currentConversationId
          || selectionRequest !== replySelectionGeneration) return;
      const task = tasks.find(item => item.id === taskId);
      if (!task || task.status !== "succeeded" || !task.result
          || task.result_message_id !== resultMessageId) {
        throw new Error("That specialist result is no longer available. Refresh the conversation and choose the current response.");
      }
      setWorkspaceTaskResult(task);
      $("#chat-prompt").focus({preventScroll: true});
    } catch (err) {
      if (generation !== studioGeneration || composerConversationId !== currentConversationId
          || selectionRequest !== replySelectionGeneration) return;
      toast(`Could not reference this specialist response: ${err.message}`, true);
    }
  };
  activeReplySelectionHandler = async messageId => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    const selectionRequest = ++replySelectionGeneration;
    try {
      const message = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages/${encodeURIComponent(messageId)}`);
      if (generation !== studioGeneration || composerConversationId !== currentConversationId
          || selectionRequest !== replySelectionGeneration) return;
      if (message.role !== "assistant" || message.conversation_id !== composerConversationId) {
        throw new Error("That Bot message is no longer available in this conversation.");
      }
      setReply(message);
      txt.focus({ preventScroll: true });
    } catch (err) {
      if (generation !== studioGeneration || composerConversationId !== currentConversationId
          || selectionRequest !== replySelectionGeneration) return;
      toast(`Could not reference that message: ${err.message}`, true);
    }
  };
  activeBotCreationFromMessageHandler = async messageId => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    await promptNewBot("", messageId);
  };
  activeChoiceSubmitHandler = async form => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    if (form.dataset.submitting === "1") return;
    const questionId = form.dataset.choiceQuestion;
    const optionIds = [...form.querySelectorAll("input:checked")].map(input => input.value);
    const error = form.querySelector("[data-choice-error]");
    if (!optionIds.length) {
      error.textContent = "Choose an option before sending your answer.";
      return;
    }
    const button = form.querySelector("[type=submit]");
    const questionRunId = form.dataset.choiceRun;
    const body = { option_ids: optionIds, model: switcher?.selected() || null };
    form.dataset.submitting = "1";
    button.disabled = true;
    form.querySelectorAll("input").forEach(input => { input.disabled = true; });
    error.textContent = "";
    try {
      const key = await choiceAnswerIdempotencyKey(composerConversationId, questionId, body);
      const result = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/questions/${encodeURIComponent(questionId)}/answer`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearChoiceIdempotencyKey(composerConversationId, questionId, key);
      storageRemove(choiceDraftKey(composerConversationId, questionId));
      if (body.model) switcher?.consumeOverride(body.model);
      terminalRunCache.delete(questionRunId);
      toast(ACTIVE.has(result.status) && activeRun ? "Answer sent — queued behind the current run." : "Answer sent.");
      if (generation !== studioGeneration) return;
      currentRunId = result.id;
      subscribeRun(result.id);
      renderChatFeed();
      refreshRoster();
    } catch (err) {
      error.textContent = err.message || "Your answer could not be sent.";
      form.querySelectorAll("input").forEach(input => { input.disabled = false; });
      button.disabled = false;
      if (/already answered/i.test(err.message || "")) renderChatFeed();
    } finally {
      if (form.isConnected) form.dataset.submitting = "";
    }
  };
  $("#reply-composer-clear").addEventListener("click", () => {
    replySelectionGeneration++;
    setReply(null);
    txt.focus({ preventScroll: true });
  });
  $("#workspace-result-composer-clear").addEventListener("click", () => {
    replySelectionGeneration++;
    setWorkspaceTaskResult(null);
    txt.focus({ preventScroll: true });
  });
  const rememberedReply = storageGet(replyStorageKey);
  if (rememberedReply) {
    const restoreGeneration = replySelectionGeneration;
    void api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages/${encodeURIComponent(rememberedReply)}`)
      .then(message => {
        if (generation === studioGeneration && composerConversationId === currentConversationId && !selectedReply
            && restoreGeneration === replySelectionGeneration && storageGet(replyStorageKey) === rememberedReply) {
          setReply(message, false);
        }
      })
      .catch(() => {
        if (generation === studioGeneration && composerConversationId === currentConversationId
            && !selectedReply && storageGet(replyStorageKey) === rememberedReply) {
          storageRemove(replyStorageKey);
          toast("The saved reply reference is no longer available. Choose the Bot message again.", true);
        }
      });
  }
  const rememberedWorkspaceResult = storageGet(workspaceResultStorageKey);
  if (rememberedWorkspaceResult && !rememberedReply) {
    try {
      const saved = JSON.parse(rememberedWorkspaceResult);
      const restoreGeneration = replySelectionGeneration;
      void api(`/v1/workspace/tasks?conversation_id=${encodeURIComponent(composerConversationId)}&limit=100`)
        .then(tasks => {
          const task = tasks.find(item => item.id === saved.task_id);
          if (generation === studioGeneration && composerConversationId === currentConversationId
              && !selectedWorkspaceTaskResult && !selectedReply && restoreGeneration === replySelectionGeneration
              && storageGet(workspaceResultStorageKey) === rememberedWorkspaceResult
              && task?.status === "succeeded" && task.result_message_id === saved.result_message_id && task.result) {
            setWorkspaceTaskResult(task, false);
          }
        })
        .catch(() => {});
    } catch {
      storageRemove(workspaceResultStorageKey);
    }
  }
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
    const replySnapshot = selectedReply?.id || null;
    const workspaceResultSnapshot = selectedWorkspaceTaskResult
      ? {...selectedWorkspaceTaskResult} : null;
    lastPrompt = text;
    try {
      const body = { prompt: text, rehearse: !!rehearseOpt?.checked, model: switcher?.selected() || null };
      if (replySnapshot) body.reply_to_message_id = replySnapshot;
      if (workspaceResultSnapshot) {
        body.workspace_task_result_id = workspaceResultSnapshot.id;
        body.workspace_task_result_message_id = workspaceResultSnapshot.result_message_id;
      }
      const key = await messageIdempotencyKey(composerConversationId, body);
      const r = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(composerConversationId, key);
      if (body.model) switcher?.consumeOverride(body.model);
      if (replySnapshot && selectedReply?.id === replySnapshot) setReply(null);
      if (workspaceResultSnapshot && selectedWorkspaceTaskResult?.id === workspaceResultSnapshot.id) {
        setWorkspaceTaskResult(null);
      }
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
  $("#conversation-files-open").addEventListener("click", () => {
    setMenu(false);
    void openConversationFiles(composerConversationId, menuBtn);
  });
  $("#conversation-export-open").addEventListener("click", () => {
    setMenu(false);
    openConversationExport(composerConversationId, menuBtn);
  });

  // composer "+" menu: popover with rehearse, Enter behaviour, and live budget
  const menu = $("#composer-menu"), menuBtn = $("#composer-menu-btn");
  const setMenu = open => {
    menu.hidden = !open;
    menuBtn.setAttribute("aria-expanded", String(open));
    if (open) $("input, button", menu)?.focus();
  };
  const taskTemplateFile = $("#task-template-file");
  $("#prompt-template-library-open")?.addEventListener("click", () => {
    setMenu(false);
    void openSavedTaskTemplateLibrary({
      returnFocus: menuBtn,
      onUse: template => {
        if (txt.disabled) throw new Error("This conversation is archived. Start a new conversation to use a saved request.");
        txt.value = template.prompt;
        txt.dispatchEvent(new Event("input", { bubbles: true }));
        setMenu(false);
        announce(`Saved request “${template.name}” added to the draft. Nothing was sent.`);
      },
    });
  });
  $("#prompt-template-import")?.addEventListener("click", () => taskTemplateFile?.click());
  taskTemplateFile?.addEventListener("change", async event => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    try {
      if (file.size > 65536) throw new Error("Template files must be 64 KB or smaller.");
      const taskTemplate = JSON.parse(await file.text());
      if (!taskTemplate || Array.isArray(taskTemplate) || taskTemplate.kind !== "hutch-task-template"
          || taskTemplate.version !== 1 || typeof taskTemplate.name !== "string"
          || !taskTemplate.name.trim() || taskTemplate.name.length > 80
          || typeof taskTemplate.prompt !== "string" || !taskTemplate.prompt.trim()
          || taskTemplate.prompt.length > 12000) {
        throw new Error("Choose a Hutch task template with a name and a request under 12,000 characters.");
      }
      if (txt.disabled) throw new Error("This conversation is archived. Start a new conversation to use a template.");
      txt.value = taskTemplate.prompt;
      saveDraft(composerDraftId, txt.value);
      autogrow();
      setMenu(false);
      txt.focus();
      announce(`Task template “${taskTemplate.name.trim()}” loaded into the draft. Nothing was sent.`);
    } catch (error) {
      toast(`Could not load this task template: ${error.message}`, true);
    } finally {
      taskTemplateFile.value = "";
    }
  });
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

async function requestHumanResume(runId, rawEventSeq, button) {
  const eventSeq = Number(rawEventSeq);
  if (!runId || !Number.isSafeInteger(eventSeq) || eventSeq < 1 || button?.disabled) return;
  if (button) button.disabled = true;
  const key = `studio-human-resume:${runId}:${eventSeq}`;
  try {
    await api(`/v1/tasks/runs/${encodeURIComponent(runId)}/resume`, {
      method: "POST", headers: { "Idempotency-Key": key }, body: { human_event_seq: eventSeq },
    });
    requestedHumanResumes.add(`${runId}:${eventSeq}`);
    if (button?.isConnected) {
      button.disabled = true;
      button.textContent = "Resume requested";
      button.setAttribute("aria-label", "Resume requested; waiting for the run to continue");
      button.setAttribute("aria-live", "polite");
    }
    toast("Resume requested. Hutch will continue when the run confirms it.");
    scheduleFeedRender();
  } catch (error) {
    if (button?.isConnected) button.disabled = false;
    toast(`Resume was not confirmed: ${error.message}`, true);
    scheduleFeedRender();
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
const terminalRunReplyCache = new Set();

async function renderChatFeed() {
  if (feedMode !== "studio") return;
  const stream = $("#chat-stream");
  const scroll = $("#chat-scroll");
  if (!stream || !scroll || !currentStudioBot) return;

  const conversationId = currentConversationId, generation = studioGeneration;
  const stillCurrent = () => generation === studioGeneration && conversationId === currentConversationId && stream.isConnected;
  let messages, authority, factPage, factShares, workspaceTasks = [], codeHandoffs = [];
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
    factShares = await api(`/v1/bots/${encodeURIComponent(currentStudioBot)}/fact-shares?limit=20`)
      .catch(error => ({incoming:[], outgoing:[], error:error.message}));
    if (!stillCurrent()) return;
    workspaceTasks = await api(`/v1/workspace/tasks?conversation_id=${encodeURIComponent(conversationId)}&limit=100`)
      .catch(() => []);
    currentWorkspaceTasks = workspaceTasks;
    if (!stillCurrent()) return;
    codeHandoffs = await api(`/v1/code-handoffs?conversation_id=${encodeURIComponent(conversationId)}&limit=100`)
      .catch(() => []);
    currentCodeHandoffs = codeHandoffs;
    if (!stillCurrent()) return;
  } catch { return; }
  if ($("#modal-root .modal-card")) { feedRefreshPending = true; return; }
  const runIds = [...new Set(messages.filter(m => m.role === "user" && m.run_id).map(m => m.run_id))];
  if (authority.active_run_id && !runIds.includes(authority.active_run_id)) runIds.unshift(authority.active_run_id);
  if (!runIds.length) {
    const nextHtml = welcomeHtml() + factPanelHtml(factPage.facts || [], factPage.error, factShares);
    // Polling can return the same snapshot many times. Avoid replacing the
    // transcript DOM on a no-op refresh: doing so drops focus and invalidates
    // element references while someone is reading or interacting with a card.
    if (stream.innerHTML === nextHtml) return;
    const factUi = captureFactUi(stream);
    stream.innerHTML = nextHtml;
    wireWelcome();
    wireFactControls(factPage.facts || [], currentStudioBot, factShares);
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
      const hasVisibleBotReply = messages.some(m => m.role === "assistant" && m.run_id === runId);
      const hasWorkspaceTask = workspaceTasks.some(task => task.source_run_id === runId);
      const hasCodeHandoff = codeHandoffs.some(task => task.source_run_id === runId);
      if (runId === currentRunId || hasWorkspaceTask || hasCodeHandoff || !terminalRunCache.has(runId)
          || hasVisibleBotReply && !terminalRunReplyCache.has(runId)) {
        html = await runBlockHtml(runId, messages, workspaceTasks, codeHandoffs);
      } else html = terminalRunCache.get(runId);
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
  const nextHtml = parts.join("") + factPanelHtml(factPage.facts || [], factPage.error, factShares);
  if (stream.innerHTML === nextHtml) return;
  stream.innerHTML = nextHtml;
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

  // The working indicator lives in a stable slot AFTER the feed: full re-renders
  // replace the transcript every event batch, so keeping its slot stable avoids
  // needless DOM churn while the server reports an active run.
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
  wireFactControls(factPage.facts || [], currentStudioBot, factShares);
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
  ['factArchive','[data-fact-archive]'], ['factHistory','[data-fact-history]'],
  ['factShare','[data-fact-share-create]'], ['factShareRevoke','[data-fact-share-revoke]']];
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
      ${fact.status === 'approved' ? `<button type="button" class="btn ghost small" data-fact-share-create="${esc(fact.id)}">Share with a Bot</button>` : ''}
      <button type="button" class="btn ghost small" data-fact-history="${esc(fact.id)}">Fact history</button></div>
  </article>`;
}

function factShareCardHtml(share, direction) {
  const incoming = direction === 'incoming';
  const owner = incoming ? share.source_display_name : share.target_display_name;
  const state = share.state === 'active' ? 'Active' : share.state.replaceAll('_', ' ');
  return `<article class="fact-card fact-share-card" data-fact-share-card="${esc(share.id)}">
    <div class="fact-heading"><strong>${esc(share.fact_key)}</strong><span class="tag">${esc(state)}</span></div>
    <p class="fact-value">${esc(share.fact_value)}</p>
    <p class="hint">${incoming ? `Shared by ${esc(owner)}` : `Shared with ${esc(owner)}`} · revision ${esc(share.fact_revision)} · reviewed snapshot</p>
    <p class="hint">${incoming ? 'This reference is untrusted data for this Bot’s chats. It does not grant tool access.' : 'The recipient can read this reference in all of its chats; revoke it here.'}</p>
    ${share.state !== 'revoked' ? `<div class="btn-row"><button type="button" class="btn ghost small" data-fact-share-revoke="${esc(share.id)}">${incoming ? 'Remove shared fact' : 'Revoke share'}</button></div>` : ''}
  </article>`;
}

function factShareRecordsHtml(sharePage = {}) {
  if (sharePage.error) return `<p class="hint" role="status">Could not refresh Bot-to-Bot shares: ${esc(sharePage.error)}. <button class="btn ghost small" type="button" data-retry-facts>Retry</button></p>`;
  const incoming = sharePage.incoming || [], outgoing = sharePage.outgoing || [];
  if (!incoming.length && !outgoing.length) return '';
  return `<details class="fact-share-list"><summary>Bot-to-Bot references · ${incoming.length} received · ${outgoing.length} shared</summary>
    <p class="hint">Only exact, reviewed snapshots appear here. Either Bot can revoke a grant; revisions do not silently update the snapshot.</p>
    ${incoming.map(item => factShareCardHtml(item, 'incoming')).join('')}
    ${outgoing.map(item => factShareCardHtml(item, 'outgoing')).join('')}
    ${(incoming.length === 20 || outgoing.length === 20) ? '<p class="hint">Showing the latest 20 grants for each direction.</p>' : ''}</details>`;
}

function factPanelHtml(facts, error = '', sharePage = {}) {
  if (error) return `<p class="hint" role="status">Could not refresh reference facts: ${esc(error)}. <button class="btn ghost small" type="button" data-retry-facts>Retry facts</button></p>${factShareRecordsHtml(sharePage)}`;
  if (!facts.length && !(sharePage.incoming || []).length && !(sharePage.outgoing || []).length && !sharePage.error) return '';
  const proposed = facts.filter(f => f.status === 'proposed'), reviewed = facts.filter(f => f.status === 'approved');
  return `<section class="fact-panel" aria-label="Reference facts">
    <h2>Reference facts</h2><p class="hint">Proposals need review before recall. Reviewed facts may be stale; they grant no tool permission. Memory can be disabled in bot settings.</p>
    ${proposed.map(factCardHtml).join('')}
    ${reviewed.length ? `<details><summary>${reviewed.length} reviewed ${reviewed.length === 1 ? 'fact' : 'facts'} in this window</summary>${reviewed.map(factCardHtml).join('')}</details>` : ''}
    ${factShareRecordsHtml(sharePage)}
    ${facts.length === 20 ? '<p class="hint">Showing 20 facts. Bot settings provide the full paginated inventory.</p>' : ''}</section>`;
}

function refreshFactsAfterChange(botName) {
  if (location.hash.startsWith('#/bot/')) void renderBotDetail(botName);
  else scheduleFeedRender();
}

function wireFactControls(facts, botName, sharePage = {incoming:[], outgoing:[]}) {
  const byId = new Map(facts.map(f => [f.id, f]));
  $$('[data-fact-share-create]').forEach(button => button.onclick = async () => {
    const fact = byId.get(button.dataset.factShareCreate); if (!fact) return;
    button.disabled = true;
    let choices = [];
    try {
      const freshBots = await api('/bots');
      botsCache = freshBots;
      choices = freshBots.filter(bot => bot.id !== fact.bot_id && bot.name !== botName && bot.memory_enabled !== false);
    } catch (error) {
      button.disabled = false;
      toast(`Could not load Bots to share with: ${error.message}`, true);
      return;
    }
    button.disabled = false;
    if (!choices.length) { toast('Create another Bot with memory enabled before sharing this fact.', true); return; }
    const key = newIdempotencyKey();
    openModal({ title: 'Share this reference with a Bot', confirmText: 'Share reviewed fact', returnFocus: button,
      bodyHtml: `<p><strong>${esc(fact.key)}</strong></p><p class="fact-value">${esc(fact.value)}</p>
        <label class="field">Recipient Bot<select id="fact-share-target" required>
          ${choices.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}${bot.is_workspace_coordinator ? ' · Coordinator' : ''}</option>`).join('')}
        </select></label>
        <p class="fact-share-disclosure">This sends this exact reviewed snapshot to the selected Bot’s chats. That Bot can read it as untrusted reference data; it grants no tool permission. Either Bot can revoke it, and a newer revision requires a new review and share.</p>
        <p id="fact-share-create-error" role="status" class="hint"></p>`,
      onConfirm: async () => {
        const target = $('#fact-share-target').value;
        try {
          await api(`/v1/bots/${encodeURIComponent(botName)}/facts/${encodeURIComponent(fact.id)}/shares`, {
            method: 'POST', headers: {'Idempotency-Key': key}, body: {target_bot_id: target},
          });
          refreshFactsAfterChange(botName); return true;
        } catch (error) { $('#fact-share-create-error').textContent = `Share was not confirmed: ${error.message}`; return false; }
      } });
  });
  $$('[data-fact-share-revoke]').forEach(button => button.onclick = () => {
    const share = [...(sharePage.incoming || []), ...(sharePage.outgoing || [])]
      .find(item => item.id === button.dataset.factShareRevoke);
    if (!share) return;
    const key = newIdempotencyKey();
    openModal({ title: 'Remove shared reference?', confirmText: 'Revoke share', confirmClass: 'danger', returnFocus: button,
      bodyHtml: `<p>Stop <strong>${esc(share.fact_key)}</strong> from being recalled in ${esc(share.target_display_name)}’s chats?</p>
        <p>The retained snapshot and review history stay in Hutch’s audit record. New recalls stop after revocation.</p>
        <p id="fact-share-revoke-error" role="status" class="hint"></p>`,
      onConfirm: async () => {
        try {
          await api(`/v1/bots/${encodeURIComponent(botName)}/fact-shares/${encodeURIComponent(share.id)}`, {
            method: 'DELETE', headers: {'Idempotency-Key': key},
          });
          refreshFactsAfterChange(botName); return true;
        } catch (error) { $('#fact-share-revoke-error').textContent = `Revocation was not confirmed: ${error.message}`; return false; }
      } });
  });
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
      announce(`${botDisplayName(r.bot_display_name || r.bot_name || "Your bot")} needs your approval before continuing.`);
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
          ${avatarFromPair(sigilPair(b.name), 160)}
        </div>
        <h2>${esc(botDisplayName(b))}</h2>
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
async function runBlockHtml(runId, messages = null, workspaceTasks = [], codeHandoffs = []) {
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
  const waitingForChoice = Object.values(run.choice_states || {}).some(state => state.status === "pending");
  const activityLabel = statusInfo[run.status]?.label || "Status unavailable";
  const activeHumanEventSeq = run.status === "waiting_human"
    ? [...events].reverse().find(e => e.type === "human_needed")?.seq ?? null
    : null;
  const anim = seenThreads.has(runId) ? "" : " enter";
  seenThreads.add(runId);

  const steps = [], cards = [], choiceCards = [];
  items.forEach(item => {
    const html = renderFeedItem(item, runId, resolvedMap, activeHumanEventSeq,
      run.choice_states || {}, run.conversation_id || "");
    if (item.kind === "event" && item.e.type === "choice_requested") choiceCards.push(html);
    else (item.kind === "event" && (item.e.type === "approval_request" || item.e.type === "human_needed") ? cards : steps).push(html);
  });

  const choiceMessageIds = new Set(events.filter(e => e.type === "choice_requested").map(e => e.data?.message_id));
  const message = events.filter(e => e.type === "message" && e.data?.role !== "user"
    && !choiceMessageIds.has(e.data?.message_id)).pop();
  const userMessage = messages?.find(m => m.role === "user" && m.run_id === runId);
  const botMessage = messages?.filter(m => m.role === "assistant" && m.run_id === runId).at(-1);
  const botName = botDisplayName(run.bot_display_name || run.bot_name || currentStudioBot);
  const replyExcerpt = userMessage?.reply_to_excerpt || "Referenced Bot message";
  const replyPreview = userMessage?.reply_to_message_id ? `<aside class="reply-reference-quote">
    <span>Reply to ${esc(botName)}’s message</span><blockquote>${esc(replyExcerpt.slice(0, 240))}${replyExcerpt.length > 240 ? "…" : ""}</blockquote>
  </aside>` : "";
  const replyAction = botMessage ? `<div class="answer-actions"><button class="btn ghost small" type="button" data-reply-message="${esc(botMessage.id)}" aria-label="Reply to ${esc(botName)} message">Reply to this</button></div>` : "";
  const createBotAction = userMessage ? `<div class="request-actions"><button class="btn ghost small" type="button"
      data-create-bot-from-request="${esc(userMessage.id)}" aria-label="Create a bot from this request">Make a bot</button></div>` : "";
  const coordinator = botsCache.find(bot => bot.name === currentStudioBot);
  const prepareTaskAction = coordinator?.is_workspace_coordinator && run.status === "succeeded"
    && userMessage && botMessage && !waitingForChoice
    ? `<button class="btn ghost small" type="button" data-prepare-bot-task
        data-source-run="${esc(runId)}" data-source-user="${esc(userMessage.id)}"
        data-source-answer="${esc(botMessage.id)}" data-source-request="${esc(run.prompt)}">Prepare for a Bot</button>` : "";
  const relatedTasks = workspaceTasks.filter(task => task.source_run_id === runId).map(workspaceTaskCardHtml).join("");
  const sourceBot = botsCache.find(bot => bot.id === run.bot_id);
  const prepareCodeTaskAction = sourceBot?.workspace_mode === "folder" && sourceBot?.workdir
    && run.status === "succeeded" && userMessage && botMessage && !waitingForChoice
    ? `<button class="btn ghost small" type="button" data-prepare-code-task
        data-source-run="${esc(runId)}" data-source-user="${esc(userMessage.id)}"
        data-source-answer="${esc(botMessage.id)}" data-source-request="${esc(run.prompt)}">Prepare coding task</button>` : "";
  const relatedCodeTasks = codeHandoffs.filter(task => task.source_run_id === runId)
    .map(codeHandoffCardHtml).join("");
  const workspaceResultPreview = userMessage?.workspace_task_result_id
    ? `<details class="reply-reference-quote workspace-task-result-reference">
        <summary>Specialist response from ${esc(userMessage.workspace_task_result_display_name || "another Bot")}</summary>
        <blockquote>${esc(userMessage.workspace_task_result_content || "")}${userMessage.workspace_task_result_truncated ? "… [shared response truncated]" : ""}</blockquote>
        <span>Shared from task ${esc(userMessage.workspace_task_result_id)}. Treated as untrusted reference text.</span>
      </details>` : "";
  const stepCount = events.filter(e => e.type === "tool_call").length;

  const html = `
    <article class="thread${anim}" data-run-id="${esc(runId)}">
      <div class="msg you">
        <div class="bubble">${replyPreview}${workspaceResultPreview}${esc(run.prompt)}</div>
        <span class="stamp">${timeAgo(run.created_at)}${run.origin === "schedule" ? " · scheduled" : ""}</span>
        ${createBotAction}
      </div>
      <div class="msg agent">
        <div class="mhead">
          ${botAvatar(botName, 26, run.status === "running" ? "running" : "")}
          <b>${esc(botName)}</b>
          ${waitingForChoice
            ? statusChip("waiting_for_answer", "Waiting for your choice")
            : statusChip(run.status, run.status_label)}
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
        ${message && message.data?.content ? `<div class="answer">${esc(message.data.content)}</div>${replyAction}${prepareTaskAction}${prepareCodeTaskAction}` : ""}
        ${relatedTasks}
        ${relatedCodeTasks}
        ${choiceCards.join("")}
        ${run.transcript_mirror?.error || run.transcript_mirror?.worker_error
          ? `<p class="run-notice" role="status">Transcript file needs attention: ${esc(run.transcript_mirror.error || run.transcript_mirror.worker_error)}. Database history remains available.</p>`
          : run.transcript_mirror?.pending ? '<p class="hint" role="status">Transcript file is catching up. History shown here is committed in the database.</p>' : ""}
        ${run.error ? run.status === 'outcome_unknown' && !run.unresolved_action_count && run.reviewed_actions?.length
          ? `<details class="run-notice"><summary>Original execution report</summary><p>${esc(run.error)}</p></details>`
          : `<div class="run-error ${run.status === "stopped" || run.status === "skipped" ? "run-notice" : run.status === "outcome_unknown" ? "run-review" : ""}">${icon("alert")}<span><b>${esc(run.status_label || activityLabel)}:</b> ${esc(run.error)}</span></div>` : ""}
      </div>
    </article>`;
  if (!running) {
    if (messages) terminalRunReplyCache.add(runId);
    if (messages || !terminalRunCache.has(runId)) {
      terminalRunCache.set(runId, html.replace('class="thread enter"', 'class="thread"'));
    }
  }
  return html;
}

function workspaceTaskCardHtml(task) {
  const active = ACTIVE.has(task.status);
  const statusLabel = statusInfo[task.status]?.label || task.status || "Status unavailable";
  const coordinator = botsCache.find(bot => bot.name === currentStudioBot && bot.is_workspace_coordinator);
  const capability = [task.model, task.inference_mode, task.tools?.length ? task.tools.join(", ") : "no tools",
    `${task.risk_tier || "unknown"} action policy`, `${task.workspace_mode || "configured"} workspace`].filter(Boolean).join(" · ");
  const checkpointLabels = {
    task_submitted: "Reviewed task accepted", status_changed: "Run status changed",
    assistant_message: "Specialist response committed", approval_requested: "Approval requested",
    approval_resolved: "Approval resolved", human_needed: "Human input needed",
    human_resumed: "Human input resumed", choice_requested: "Choice requested",
    choice_answered: "Choice recorded", artifact_created: "Artifact saved",
  };
  const checkpoints = task.checkpoints || [];
  const checkpointSummary = task.checkpoint_count > checkpoints.length
    ? `Showing the ${checkpoints.length} most recent of ${task.checkpoint_count} committed checkpoints.`
    : `${task.checkpoint_count || checkpoints.length} committed checkpoints.`;
  const checkpointRecovery = task.continuation_available
    ? "A safe continuation starts a new run from this checkpoint; it does not resume or replay the old worker."
    : task.continuation_reason || "Continuation is offered only for a stopped or interrupted run with no recorded effects and unchanged permissions.";
  const checkpointHtml = checkpoints.length ? `<details class="workspace-task-checkpoints">
      <summary>Progress checkpoints (${Number(task.checkpoint_count || checkpoints.length).toLocaleString()})</summary>
      <p class="hint">${esc(checkpointSummary)} These record committed events, not a snapshot of execution state. ${esc(checkpointRecovery)}</p>
      <ol>${checkpoints.map(checkpoint => {
        const date = new Date(checkpoint.created_at);
        const when = Number.isNaN(date.valueOf()) ? "Time unavailable" : date.toLocaleString();
        const state = checkpoint.recovery_state === "reconcile" ? "Needs review" :
          checkpoint.recovery_state === "awaiting_owner" ? "Waiting for you" :
          checkpoint.recovery_state === "complete" ? "Complete" :
          checkpoint.recovery_state === "active" ? "In progress" :
          checkpoint.recovery_state === "queued" ? "Queued" :
          checkpoint.recovery_state === "interrupted" ? "Interrupted" :
          checkpoint.recovery_state === "stopped" ? "Stopped" :
          checkpoint.recovery_state === "waiting_for_resources" ? "Waiting for resources" :
          checkpoint.recovery_state === "recovering" ? "Recovering" :
          checkpoint.recovery_state === "stopping" ? "Stopping" :
          checkpoint.recovery_state === "skipped" ? "Skipped" : "Status unavailable";
        return `<li><span class="workspace-task-checkpoint-title">${esc(checkpointLabels[checkpoint.kind] || "Task event")}</span>
          <span class="workspace-task-checkpoint-state">${esc(state)}</span>
          <time datetime="${esc(checkpoint.created_at)}">${esc(when)}</time>
          <span class="workspace-task-checkpoint-seq">Event ${Number(checkpoint.event_seq) || 0}</span></li>`;
      }).join("")}</ol>
    </details>` : "";
  const sharedFacts = task.shared_facts || [];
  const sharedFactsHtml = sharedFacts.length ? `<details class="workspace-task-shared-facts">
      <summary>Reference facts shared for this task (${sharedFacts.length})</summary>
      <p class="hint">These exact reviewed values were included in this task's model context. They were not added to the specialist Bot's saved memory.</p>
      <ul>${sharedFacts.map(fact => `<li><strong>${esc(fact.key)}</strong><span>${esc(fact.value)}</span>
        <small>From ${esc(fact.source_display_name)} · ${fact.source_scope_kind === "conversation" ? "this coordinator chat" : "coordinator-wide reference"} · revision ${Number(fact.revision) || 0}</small></li>`).join("")}</ul>
    </details>` : "";
  const continuationLineage = task.continuation_of_task_id
    ? `<p class="hint">Continued from a prior no-effect attempt. Reviewed task facts and action receipts were not carried forward.</p>` : "";
  const continuationPreview = task.continuation_checkpoint_preview
    ? `<blockquote class="workspace-task-continuation-preview">${esc(task.continuation_checkpoint_preview)}</blockquote>`
    : `<p class="hint">No assistant response was committed yet. Hutch will start a fresh run from the reviewed brief.</p>`;
  const continueButton = task.continuation_available
    ? `<button class="btn ghost small" type="button" data-continue-workspace-task="${esc(task.id)}">Continue from checkpoint</button>` : "";
  return `<section class="workspace-task-card" data-workspace-task="${esc(task.id)}" aria-label="Task for ${esc(task.target_display_name)}">
    <div class="workspace-task-heading"><strong>Assigned to ${esc(task.target_display_name)}</strong>${statusChip(task.status, statusLabel)}</div>
    <p class="workspace-task-brief">${esc(task.task_brief)}</p>
    ${continuationLineage}
    ${task.assumptions ? `<p class="workspace-task-assumptions"><b>Reviewed constraints:</b> ${esc(task.assumptions)}</p>` : ""}
    <p class="hint">Specialist settings: ${esc(capability)}</p>
    ${sharedFactsHtml}
    ${task.result ? `<div class="workspace-task-result"><b>Latest specialist response</b><p>${esc(task.result)}${task.result_truncated ? "… [preview truncated]" : ""}</p></div>` : ""}
    ${task.reason && task.status !== "succeeded" ? `<p class="run-notice" role="status">${esc(task.reason)}</p>` : ""}
    ${checkpointHtml}
    <details><summary>Request and coordinator draft</summary>
      <p><b>Your original request</b><br>${esc(task.original_request)}${task.original_request_truncated ? "… [open the message above for the full request]" : ""}</p>
      <p><b>Coordinator’s suggested brief</b><br>${esc(task.proposed_brief)}${task.proposed_brief_truncated ? "… [open the message above for the full answer]" : ""}</p>
    </details>
    <div class="btn-row">
      <button class="btn ghost small" type="button" data-open-workspace-task="${esc(task.child_conversation_id)}">Open specialist chat</button>
      ${continueButton}
      ${coordinator && task.status === "succeeded" && task.result && task.result_message_id
        ? `<button class="btn ghost small" type="button" data-discuss-specialist-result="${esc(task.id)}"
            data-result-message-id="${esc(task.result_message_id)}">Discuss with ${esc(botDisplayName(coordinator))}</button>` : ""}
      ${active ? `<button class="btn ghost small" type="button" data-stop-run="${esc(task.child_run_id)}">Stop specialist</button>` : ""}
    </div>
  </section>`;
}

function codeHandoffCardHtml(task) {
  const statusLabels = {
    prepared: "Ready to launch locally", launching: "Preparing OpenCode",
    running: "OpenCode is running locally", changes_ready: "Changes ready for review",
    stopping: "Stopping · checking process cleanup", cleanup_incomplete: "Cleanup could not be verified",
    complete_no_changes: "Finished without file changes", stopped: "Stopped · worktree retained",
    interrupted: "Interrupted · worktree retained", failed: "Failed · worktree retained",
  };
  const statusLabel = task.status_label || statusLabels[task.status] || "Status unavailable";
  const prepared = task.status === "prepared";
  const active = ["launching", "running", "stopping", "cleanup_incomplete"].includes(task.status);
  const completed = ["changes_ready", "complete_no_changes", "stopped", "interrupted", "failed"].includes(task.status);
  const statusDetail = prepared
    ? `<p class="hint">Open a terminal on the Linux Hutch host, paste this command, then review OpenCode’s own permission prompts.</p>
       <div class="code-handoff-command"><code>${esc(task.launch_command)}</code>
         <button class="btn ghost small" type="button" data-copy-code-command="${esc(task.id)}">Copy command</button></div>`
    : task.status === "cleanup_incomplete"
      ? '<p class="run-notice" role="status">Hutch has not marked this task stopped. Check the Linux host and process group; then run <code>' + esc(task.reconcile_command) + '</code> to recheck identity. The worktree stays untouched.</p>'
    : active
      ? `<p class="hint">This handoff is owned by its local OpenCode process. If the terminal or host stopped, run <code>${esc(task.reconcile_command)}</code> on the Linux Hutch host to check its recorded process identity.</p>`
      : `<p class="code-handoff-summary">${esc(task.summary || "No completion details were recorded.")}</p>
         ${task.branch_name ? `<p class="hint">Review branch <code>${esc(task.branch_name)}</code>${task.changed_files ? ` · ${Number(task.changed_files).toLocaleString()} changed files` : ""}. Changes remain in the isolated worktree; they were not applied to the configured project.</p>` : ""}
         ${task.branch_name ? `<p class="hint">The CLI printed the local worktree path at exit.</p>` : ""}`;
  return `<section class="code-handoff-card" data-code-handoff="${esc(task.id)}" aria-label="OpenCode task for ${esc(task.project_name)}">
    <div class="code-handoff-heading"><strong>OpenCode coding task · ${esc(task.project_name)}</strong>${statusChip(task.status, statusLabel)}</div>
    <p class="workspace-task-brief">${esc(task.task_brief)}</p>
    ${task.error ? `<p class="run-notice" role="status">${esc(task.error)}</p>` : ""}
    ${statusDetail}
    <details><summary>Review source and execution boundary</summary>
      <p><b>Your original request</b><br>${esc(task.original_request)}</p>
      <p><b>Bot’s suggested brief</b><br>${esc(task.proposed_brief)}</p>
      <p class="hint">Pinned base: <code>${esc(String(task.base_commit || "").slice(0, 12))}</code> · OpenCode ${esc(task.opencode_version || "version checked at launch")}. The OpenCode CLI uses its own sign-in, model selection and usage pool; Hutch’s provider budgets do not cover this work. Hutch asks you to review the handoff before launch. Once launched, OpenCode shell commands run with your Linux user’s authority and each command must be reviewed there. Hutch does not inspect or approve that CLI’s commands.</p>
    </details>
  </section>`;
}

async function codeHandoffKey(conversationId, sourceAnswerId, body) {
  const storageKey = `hutch-pending-code-handoff:${conversationId}:${sourceAnswerId}`;
  const fingerprint = await payloadFingerprint(body);
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.fingerprint === fingerprint && previous?.key) return {storageKey, key: previous.key};
  } catch { /* replace a damaged retry marker */ }
  const key = newIdempotencyKey();
  storageSet(storageKey, JSON.stringify({fingerprint, key}));
  return {storageKey, key};
}

async function prepareCodeTask(button) {
  const {sourceRun, sourceUser, sourceAnswer} = button.dataset;
  const originalRequest = button.dataset.sourceRequest || "";
  const conversationId = currentConversationId;
  let answer;
  try {
    answer = await api(`/v1/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(sourceAnswer)}`);
  } catch (error) { toast(`Could not prepare this coding task: ${error.message}`, true); return; }
  const bot = botsCache.find(item => item.name === currentStudioBot);
  if (!bot || answer.role !== "assistant" || answer.run_id !== sourceRun || !originalRequest) {
    toast("The source request and Bot reply no longer match this completed attempt.", true); return;
  }
  const projectName = bot.workdir.split(/[\\/]/).filter(Boolean).pop() || "Configured project folder";
  openModal({
    returnFocus: button, title: "Prepare a coding task for OpenCode", confirmText: "Prepare reviewed task", wide: true, tall: true,
    bodyHtml: `<p>Turn this chat request into a separate coding task. Edit the suggested brief so OpenCode knows what to change and how you will judge the result.</p>
      <blockquote class="workspace-task-source"><b>Your original request</b><br>${esc(originalRequest)}</blockquote>
      <label class="field">Reviewed coding task<textarea id="code-task-brief" rows="7" maxlength="20000" aria-describedby="code-task-brief-help">${esc(answer.content)}</textarea>
        <span class="hint" id="code-task-brief-help">This is a draft from ${esc(botDisplayName(bot))}. Review or rewrite it; it does not grant extra access.</span></label>
      <p class="hint"><b>Project:</b> ${esc(projectName)} · the task starts from its saved Git commit in a new isolated worktree. Uncommitted and untracked files from the source folder are not copied.</p>
      <p class="hint"><b>How launch works:</b> Hutch prepares and saves the handoff. You launch it from a terminal on the Linux computer running Hutch; the browser cannot start a local terminal for you.</p>
      <p class="hint"><b>Account and permissions:</b> OpenCode uses its own sign-in, chosen model and usage limits, separate from Hutch’s budgets. Its interactive permission prompts are owned by OpenCode. Approved shell commands run with your Linux user’s filesystem, process and network access. Review each one; Hutch does not broker these approvals.</p>
      <p class="hint">Do not include passwords, access tokens, or other secrets in the coding task. The reviewed brief is sent to OpenCode’s selected model provider under that account’s terms.</p>
      <p class="hint">Hutch will not copy the resulting branch into your configured folder or publish it. Review the changes in the worktree before applying them yourself.</p>
      <p id="code-task-error" role="alert" hidden></p>`,
    onConfirm: async () => {
      const brief = $("#code-task-brief").value.trim();
      const error = $("#code-task-error"), confirm = $("#modal-confirm");
      if (!brief) { error.textContent = "Write a non-empty coding task before preparing the handoff."; error.hidden = false; return false; }
      const body = {conversation_id: conversationId, source_run_id: sourceRun,
        source_user_message_id: sourceUser, source_assistant_message_id: sourceAnswer, task_brief: brief};
      const retry = await codeHandoffKey(conversationId, sourceAnswer, body);
      confirm.disabled = true;
      try {
        const result = await api("/v1/code-handoffs", {method: "POST", body, headers: {"Idempotency-Key": retry.key}});
        storageRemove(retry.storageKey);
        toast("Reviewed coding task prepared. Open the command in the chat card on the Linux Hutch host.");
        scheduleFeedRender();
        return true;
      } catch (err) {
        error.textContent = `The handoff was not confirmed: ${err.message}. The reviewed text is kept here; retrying uses the same request key.`;
        error.hidden = false;
        return false;
      } finally { if (confirm.isConnected) confirm.disabled = false; }
    },
  });
}

async function copyCodeHandoffCommand(button) {
  const task = currentCodeHandoffs.find(item => item.id === button.dataset.copyCodeCommand);
  if (!task?.launch_command) { toast("This coding task is no longer available.", true); return; }
  try {
    await navigator.clipboard.writeText(task.launch_command);
    toast("Launch command copied. Paste it into a terminal on the Linux Hutch host.");
  } catch {
    toast(`Copy unavailable. Enter this in a terminal on the Linux Hutch host: ${task.launch_command}`, true);
  }
}

function continueWorkspaceTask(button) {
  const taskId = button.dataset.continueWorkspaceTask;
  const task = currentWorkspaceTasks.find(item => item.id === taskId);
  if (!task?.continuation_available) { toast(task?.continuation_reason || "This checkpoint cannot be continued.", true); return; }
  const keyStorage = `hutch-pending-workspace-continuation:${taskId}`;
  const checkpoint = task.continuation_checkpoint_preview
    ? `<blockquote class="workspace-task-continuation-preview">${esc(task.continuation_checkpoint_preview)}</blockquote>`
      : `<p class="hint">No assistant response was committed yet. Hutch will start a fresh run from the reviewed brief.</p>`;
  openModal({
    title: "Continue from a safe checkpoint",
    confirmText: "Start a new run",
    returnFocus: button,
    bodyHtml: `<p>This creates a fresh run for <b>${esc(task.target_display_name)}</b>. It does not resume the old process or repeat any recorded action.</p>
      <h4>Reviewed task</h4><p>${esc(task.task_brief)}</p>
      ${task.assumptions ? `<h4>Reviewed constraints</h4><p>${esc(task.assumptions)}</p>` : ""}
      <h4>Checkpoint</h4>${checkpoint}
      <p class="hint">The previous action list is empty and the specialist's saved model and permissions are unchanged. This new model call may use additional quota. Only the reviewed brief, constraints, and committed assistant response are passed forward; selected facts, old tool results, credentials, and action receipts are not.</p>
      <p id="workspace-continuation-error" role="alert" hidden></p>`,
    onConfirm: async () => {
      const confirm = $("#modal-confirm"), error = $("#workspace-continuation-error");
      let key = storageGet(keyStorage);
      if (!key) { key = newIdempotencyKey(); storageSet(keyStorage, key); }
      confirm.disabled = true;
      try {
        await api(`/v1/workspace/tasks/${encodeURIComponent(taskId)}/continue`, {
          method: "POST", headers: { "Idempotency-Key": key },
        });
        storageRemove(keyStorage);
        toast(`A new ${task.target_display_name} run has started from the committed checkpoint.`);
        scheduleFeedRender();
        return true;
      } catch (err) {
        error.textContent = `Continuation was not confirmed: ${err.message}. You can safely retry this same request.`;
        error.hidden = false;
        return false;
      } finally { if (confirm.isConnected) confirm.disabled = false; }
    },
  });
}

function workspaceTaskCapabilityHtml(bot) {
  if (!bot) return "";
  const rows = [
    ["Model", bot.model || "No model configured"],
    ["Inference", bot.inference_mode || "Hybrid"],
    ["Tools", (bot.tools || []).length ? bot.tools.join(", ") : "None configured"],
    ["Action policy", `${bot.risk_tier || "supervised"} · ${bot.approval_mode || "ask"}`],
    ["Workspace", bot.workdir ? "Selected folder" : (bot.workspace_mode || "fresh")],
  ];
  return `<dl class="workspace-task-capabilities">${rows.map(([label, value]) =>
    `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>`;
}

async function workspaceTaskKey(parentConversationId, sourceAnswerId, targetBotId, body) {
  const storageKey = `hutch-pending-workspace-task:${parentConversationId}:${sourceAnswerId}:${targetBotId}`;
  const fingerprint = await payloadFingerprint(body);
  try {
    const previous = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (previous?.fingerprint === fingerprint && previous?.key) return {storageKey, key: previous.key};
  } catch { /* replace a damaged retry marker */ }
  const key = newIdempotencyKey();
  storageSet(storageKey, JSON.stringify({fingerprint, key}));
  return {storageKey, key};
}

async function prepareWorkspaceTask(button) {
  const {sourceRun, sourceUser, sourceAnswer} = button.dataset;
  const originalRequest = button.dataset.sourceRequest || "";
  const parentConversationId = currentConversationId;
  const returnFocus = button;
  let sourceAnswerMessage, bots, specialistRoster;
  try {
    [sourceAnswerMessage, bots, specialistRoster] = await Promise.all([
      api(`/v1/conversations/${encodeURIComponent(parentConversationId)}/messages/${encodeURIComponent(sourceAnswer)}`),
      api("/bots"),
      api("/v1/workspace/specialists"),
    ]);
  } catch (error) { toast(`Could not prepare this task: ${error.message}`, "error"); return; }
  const coordinator = bots.find(bot => bot.name === currentStudioBot);
  const approvedIds = new Set(specialistRoster.specialist_bot_ids || []);
  const targets = bots.filter(bot => approvedIds.has(bot.id));
  if (!coordinator?.is_workspace_coordinator) { toast("Select this Bot as the workspace coordinator before assigning tasks.", "error"); return; }
  if (!targets.length) { toast("No specialists are approved yet. Add a Bot to the roster in workspace coordinator settings.", "error"); return; }
  if (!originalRequest || sourceAnswerMessage.role !== "assistant" || sourceAnswerMessage.run_id !== sourceRun) {
    toast("The coordinator messages no longer match this completed attempt.", "error"); return;
  }
  let shareableFacts = [], factLoadError = "";
  try {
    const factsPage = await api(`/v1/bots/${encodeURIComponent(coordinator.id)}/facts?conversation_id=${encodeURIComponent(parentConversationId)}&limit=100`);
    shareableFacts = (factsPage.facts || []).filter(fact => fact.status === "approved");
  } catch (error) { factLoadError = error.message; }
  let factChecks = [];
  let factCount = null;
  const selectedFactIds = () => factChecks.filter(input => input.checked)
    .map(input => input.dataset.workspaceTaskFact);
  const selectedFactSnapshots = () => selectedFactIds().map(id => {
    const fact = shareableFacts.find(item => item.id === id);
    return {
      content_hash: fact.content_hash,
      fact_id: fact.id,
      key: fact.key,
      revision: Number(fact.revision) || 0,
      source_bot_id: coordinator.id,
      source_conversation_id: fact.scope_kind === "conversation" ? fact.scope_id : "",
      source_display_name: coordinator.display_name,
      source_scope_id: fact.scope_id,
      source_scope_kind: fact.scope_kind,
      value: fact.value,
    };
  });
  const factChoices = shareableFacts.length ? `<details class="workspace-task-fact-selector">
      <summary>Reviewed reference facts to include (optional)</summary>
      <p class="hint">Nothing is selected automatically. Choose up to 8 approved facts from this coordinator or chat. They will be sent through the specialist's saved model route for this task only, and will not be added to its saved memory. The provider may retain them under its terms.</p>
      <p class="hint" id="workspace-task-facts-count" role="status">0 of 8 selected · 12 / 6,000 characters</p>
      <div class="workspace-task-fact-list">${shareableFacts.map(fact => `<label class="workspace-task-fact-choice">
        <input type="checkbox" data-workspace-task-fact="${esc(fact.id)}">
        <span><strong>${esc(fact.key)}</strong><span>${esc(fact.value)}</span>
          <small>${esc(factScopeLabel(fact))} · reviewed reference · revision ${Number(fact.revision) || 0}</small></span>
      </label>`).join("")}</div>
    </details>` : `<p class="hint">${factLoadError ? `Reviewed facts could not be loaded (${esc(factLoadError)}); the task can still be sent without them.` : "No reviewed coordinator facts are available to share with this task."}</p>`;

  openModal({
    returnFocus, title: "Refine a task for a specialist", confirmText: "Send reviewed task", wide: true, tall: true,
    bodyHtml: `<p>The coordinator’s reply is a starting draft. Check the original request, the task, expected result and limits. If something important is still unclear, ask the coordinator before sending.</p>
      <blockquote class="workspace-task-source"><b>Original request</b><br>${esc(originalRequest)}</blockquote>
      <label class="field">Assigned specialist Bot<select id="workspace-task-target">${targets.map(bot =>
        `<option value="${esc(bot.id)}">${esc(botDisplayName(bot))}</option>`).join("")}</select></label>
      <div id="workspace-task-capability" aria-live="polite"></div>
      <label class="field">Goal and task<textarea id="workspace-task-brief" rows="6" maxlength="20000" aria-describedby="workspace-task-brief-help">${esc(sourceAnswerMessage.content)}</textarea>
        <span class="hint" id="workspace-task-brief-help">Edit the coordinator’s draft so the specialist can act on what you meant. The original request stays linked for review.</span></label>
      <label class="field">Expected deliverable (optional)<textarea id="workspace-task-deliverable" rows="2" maxlength="4000" placeholder="For example: a one-page comparison with a recommendation."></textarea></label>
      <label class="field">Context, constraints, or unresolved assumptions (optional)<textarea id="workspace-task-assumptions" rows="3" maxlength="4000" placeholder="For example: use public sources only; do not contact anyone."></textarea>
        <span class="hint">If an unanswered detail could change the result, go back and ask the coordinator rather than guessing.</span></label>
      <p class="hint" id="workspace-task-boundary"><b>Execution boundary:</b> this task uses the selected specialist’s saved model, tools, account grants, workspace, limits and approval policy. The brief cannot add access. If the request needs broader access, review the Bot’s settings before dispatch.</p>
      ${factChoices}
      <p class="hint">The specialist receives the reviewed goal, requested deliverable, constraints and only facts you selected above in a new conversation. Other chat history and files are not copied. Its own enabled memory and workspace may still apply. Once a task starts, information already sent to a model cannot be recalled.</p>
      <p id="workspace-task-error" role="alert" hidden></p>`,
    onConfirm: async () => {
      const target = targets.find(bot => bot.id === $("#workspace-task-target").value);
      const goal = $("#workspace-task-brief").value.trim();
      const deliverable = $("#workspace-task-deliverable").value.trim();
      const taskBrief = [goal, deliverable ? `Expected deliverable:\n${deliverable}` : ""].filter(Boolean).join("\n\n");
      const assumptions = $("#workspace-task-assumptions").value.trim();
      const error = $("#workspace-task-error"), confirm = $("#modal-confirm");
      if (!target || !taskBrief) { error.textContent = "Choose a Bot and review a non-empty task brief."; error.hidden = false; return false; }
      if (taskBrief.length > 20000) {
        error.textContent = "Shorten the goal or expected deliverable; the reviewed task brief is limited to 20,000 characters.";
        error.hidden = false;
        return false;
      }
      const selectedFacts = selectedFactSnapshots();
      const serializedSize = Array.from(JSON.stringify(selectedFacts)
        .replace(/</g, "\\u003c").replace(/>/g, "\\u003e")).length;
      if (serializedSize > 6000) {
        error.textContent = "Choose fewer reference facts; the task limit is 6,000 serialized characters.";
        error.hidden = false;
        return false;
      }
      const body = {parent_conversation_id: parentConversationId, source_run_id: sourceRun,
        source_user_message_id: sourceUser, source_assistant_message_id: sourceAnswer,
        target_bot_id: target.id, task_brief: taskBrief, assumptions,
        memory_fact_ids: selectedFacts.map(fact => fact.fact_id)};
      const retry = await workspaceTaskKey(parentConversationId, sourceAnswer, target.id, body);
      confirm.disabled = true;
      try {
        const result = await api("/v1/workspace/tasks", {
          method: "POST", body, headers: {"Idempotency-Key": retry.key},
        });
        storageRemove(retry.storageKey);
        toast(`Task sent to ${result.target_display_name}. You can follow the specialist chat here or continue in the main chat.`);
        scheduleFeedRender();
        return true;
      } catch (err) {
        error.textContent = `Task not confirmed: ${err.message}. Your reviewed brief is retained so you can safely retry.`;
        error.hidden = false;
        return false;
      } finally { if (confirm.isConnected) confirm.disabled = false; }
    },
  });
  const select = $("#workspace-task-target"), summary = $("#workspace-task-capability");
  const refreshCapabilities = () => {
    const bot = targets.find(item => item.id === select.value);
    summary.innerHTML = bot ? `<h4>Saved specialist settings</h4>${workspaceTaskCapabilityHtml(bot)}` : "";
  };
  select.addEventListener("change", refreshCapabilities);
  refreshCapabilities();
  factChecks = $$('[data-workspace-task-fact]');
  factCount = $("#workspace-task-facts-count");
  const refreshFactCount = () => {
    if (!factCount) return;
    const selected = selectedFactIds();
    const serializedSize = Array.from(JSON.stringify(selectedFactSnapshots())
      .replace(/</g, "\\u003c").replace(/>/g, "\\u003e")).length;
    const overLimit = serializedSize > 6000;
    factCount.textContent = `${selected.length} of 8 selected · ${serializedSize.toLocaleString()} / 6,000 characters${overLimit ? " · over limit" : ""}`;
    factCount.setAttribute("aria-invalid", String(overLimit));
    factChecks.forEach(input => { input.disabled = !input.checked && selected.length >= 8; });
  };
  factChecks.forEach(input => input.addEventListener("change", refreshFactCount));
  refreshFactCount();
}

const seenThreads = new Set();

const receiptOutcomes = { confirmed_done: 'Effect confirmed', confirmed_failed: 'Failure confirmed', not_applied: 'No effect found' };
function receiptCardHtml(action) {
  const report = action.reconciliation;
  return `<section class="receipt-card" data-receipt-card="${esc(action.id)}" ${report ? 'data-receipt-reviewed="true"' : ''}>
    <b>${report ? esc(receiptOutcomes[report.outcome] || report.outcome) + ' · human report' : 'Action outcome needs review'}</b>
    <p>${esc(botDisplayName(action.bot_display_name || action.bot_name || ''))} · ${esc(action.summary || action.tool)}</p>
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
        terminalRunReplyCache.delete(action.run_id);
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

function renderFeedItem(item, runId, resolvedMap, activeHumanEventSeq, choiceStates = {}, conversationId = "") {
  if (item.kind === "tool") return toolLineHtml(item, item.call?.e ?? item.result.e, runId);
  if (item.kind === "group") return toolGroupHtml(item, runId);
  return renderChatEvent(item.e, resolvedMap, activeHumanEventSeq, choiceStates, conversationId);
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
      <button class="tool-line-head" type="button" aria-expanded="${open}" aria-controls="tlb-${esc(String(idx))}${res?.d.artifact ? ` tla-${esc(String(idx))}` : ""}" data-tool-toggle="${esc(String(idx))}">
        <span class="tool-grid" title="${t}">
          <span class="tool-verdict">${verdict}</span>
          <span class="tool-name">${esc(tool)}</span>
          <span class="tool-args"><span class="tool-args-text">${esc(truncate(summary, 90))}</span>${res?.d.artifact ? `<span class="tool-src-flag" title="Full output saved as an artifact">source</span>` : ""}</span>
        </span>
      </button>
      <div class="tool-line-body" id="tlb-${esc(String(idx))}" ${open ? "" : "hidden"}>
        <div class="tool-line-section">
          <span class="tool-line-label">Input</span>
          ${esc(JSON.stringify(call?.d.args ?? {}, null, 2))}
        </div>
        ${res ? toolOutputHtml(res.d.output) : '<div class="tool-line-section"><span class="tool-line-label">Output</span>pending…</div>'}
      </div>
      ${res?.d.artifact ? `<div class="tool-artifact-actions" id="tla-${esc(String(idx))}" ${open ? "" : "hidden"}>${artifactDownloadHtml(runId, res.d)}${sourceCardHtml(res.d, runId)}</div>` : ""}
    </div>
    ${includeFileAttachments ? createdFilesHtml(runId, [{ result: res }]) : ""}
  </div>`;
}

/* PF-2 kept the untruncated output on disk; this row is the only door to it. */
function sourceCardHtml(d, runId) {
  const file = String(d.artifact).replace(/^artifacts\//, "");
  return `
    <a class="tool-source" href="/api/runs/${esc(runId)}/artifacts/${esc(file)}" target="_blank" rel="noopener noreferrer">
      ${icon("folder")}
      <span class="tool-source-name" title="${esc(file)}">${esc(file)}</span>
      <span class="tool-source-meta">full output · ${(d.chars || 0).toLocaleString("en-US")} chars</span>
      <span class="tool-source-go">Open ${icon("arrow")}</span>
    </a>`;
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
    const discussResult = ev.target.closest("[data-discuss-specialist-result]");
    if (discussResult) {
      void activeWorkspaceResultSelectionHandler?.(discussResult.dataset.discussSpecialistResult,
        discussResult.dataset.resultMessageId);
      return;
    }
    const assignTask = ev.target.closest("[data-prepare-bot-task]");
    if (assignTask) { void prepareWorkspaceTask(assignTask); return; }
    const prepareCode = ev.target.closest("[data-prepare-code-task]");
    if (prepareCode) { void prepareCodeTask(prepareCode); return; }
    const copyCode = ev.target.closest("[data-copy-code-command]");
    if (copyCode) { void copyCodeHandoffCommand(copyCode); return; }
    const openWorkspaceTask = ev.target.closest("[data-open-workspace-task]");
    if (openWorkspaceTask) { void openConversation(openWorkspaceTask.dataset.openWorkspaceTask); return; }
    const continueTask = ev.target.closest("[data-continue-workspace-task]");
    if (continueTask) { continueWorkspaceTask(continueTask); return; }
    const reply = ev.target.closest("[data-reply-message]");
    if (reply) { void activeReplySelectionHandler?.(reply.dataset.replyMessage); return; }
    const createBotFromRequest = ev.target.closest("[data-create-bot-from-request]");
    if (createBotFromRequest) {
      void activeBotCreationFromMessageHandler?.(createBotFromRequest.dataset.createBotFromRequest);
      return;
    }
    const receipt = ev.target.closest('[data-receipt-review]');
    if (receipt) { void reviewReceipt(receipt.dataset.receiptReview, receipt); return; }
    if (ev.target.closest('[data-receipt-queue]')) { void openNeedsYou(); return; }
    const resume = ev.target.closest("[data-human-resume]");
    if (resume) { void requestHumanResume(resume.dataset.runId, resume.dataset.eventSeq, resume); return; }
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
      const artifacts = line.querySelector(".tool-artifact-actions");
      if (artifacts) artifacts.hidden = !open;
      const blockRun = line.closest("[data-run-id]")?.dataset.runId || currentRunId;
      const ids = [...stream.querySelectorAll(`[data-run-id="${blockRun}"] [data-tool-toggle][aria-expanded='true']`)].map(b => b.dataset.toolToggle);
      try { localStorage.setItem(`hutch-expanded:${blockRun}`, JSON.stringify(ids)); } catch {}
    }
  });
  stream.addEventListener("submit", ev => {
    const form = ev.target.closest("[data-choice-form]");
    if (!form) return;
    ev.preventDefault();
    void activeChoiceSubmitHandler?.(form);
  });
  stream.addEventListener("change", ev => {
    const input = ev.target.closest("[data-choice-option]");
    const form = input?.closest("[data-choice-form]");
    if (!form) return;
    const selected = [...form.querySelectorAll("input:checked")].map(item => item.value);
    storageSet(choiceDraftKey(currentConversationId, form.dataset.choiceQuestion), JSON.stringify(selected));
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
  const detailObject = a.detail && typeof a.detail === "object" ? a.detail : null;
  const formTarget = tool === "browser" && detailObject?.target_kind === "form_submit"
    && detailObject.target && typeof detailObject.target === "object" ? detailObject.target : null;
  const deadline = a.deadline
    || (a.expires_at ? new Date(a.expires_at).getTime()
      : (a.created_at ? new Date(a.created_at).getTime() + 10 * 60 * 1000 : 0));
  const expired = deadline && deadline <= Date.now();
  const detail = !formTarget && a.detail && Object.keys(a.detail || {}).length ? JSON.stringify(a.detail, null, 2) : "";
  const segments = a.segments || [];
  const stickyKey = a.sticky_key || "";
  const canAlways = !!(stickyKey && !outward);
  const runId = a.run_id || "";
  const contextHref = a.conversation_id ? `#/conversation/${encodeURIComponent(a.conversation_id)}` : `#/run/${encodeURIComponent(runId)}`;

  const rows = [
    ["Tool", tool],
    formTarget ? ["Destination", formTarget.destination || "unknown destination"] : null,
    formTarget ? ["Request method", String(formTarget.method || "get").toUpperCase()] : null,
    formTarget ? ["Submit control", formTarget.label || "Submit form"] : null,
    a.account ? ["Account", a.account] : null,
    a.destination ? ["Destination", a.destination] : null,
    a.revision ? ["Revision", a.revision] : null,
    rule && !formTarget ? ["Why you are asked", rule] : null,
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
        ${formTarget ? `<div class="review-rows form-review-rows">
          <div class="review-row"><span class="review-key">Form fields</span><span>
            ${(Array.isArray(formTarget.fields) ? formTarget.fields : []).length
              ? `<ul>${formTarget.fields.map(field => `<li>${esc(field.label || "Form field")}${field.sensitive ? " · sensitive value hidden" : field.selected ? " · file selected" : ""}</li>`).join("")}</ul>`
              : "No visible fields detected"}
          </span></div>
          <p class="hint">Hutch keeps field values out of this review and checks the destination and filled fields again before submission.</p>
        </div>` : ""}
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

function choiceCardHtml(e, state, conversationId) {
  const data = e.data || {};
  const questionId = String(data.question_id || "");
  const runId = String(e.run_id || "");
  const options = Array.isArray(data.options) ? data.options : [];
  if (!questionId || !state || !options.length) {
    return '<section class="choice-card" role="status"><b>Choice unavailable</b><p>The saved answer state could not be verified. Refresh the conversation before continuing.</p></section>';
  }
  if (state.status === "answered") {
    const selected = state.selected_labels || [];
    return `<section class="choice-card answered" aria-label="Choice answered">
      <div class="choice-card-head"><span class="choice-kicker">Your choice</span><span class="choice-state">Answered</span></div>
      <p class="choice-question">${esc(data.question || "")}</p>
      <p class="choice-selection">${selected.map(label => `<span>${esc(label)}</span>`).join("") || "Selection recorded"}</p>
    </section>`;
  }
  if (state.status !== "pending") {
    return '<section class="choice-card" role="status"><b>Choice closed</b><p>This question is no longer accepting an answer.</p></section>';
  }
  const selectedConversation = currentConversations.find(item => item.id === conversationId);
  const inConversation = location.hash.startsWith("#/chat") && currentConversationId === conversationId;
  const canAnswer = inConversation && !selectedConversation?.archived && !!activeChoiceSubmitHandler;
  if (!canAnswer) {
    return `<section class="choice-card" aria-label="Bot question">
      <div class="choice-card-head"><span class="choice-kicker">Bot question</span><span class="choice-state">Waiting for you</span></div>
      <p class="choice-question">${esc(data.question || "")}</p>
      ${selectedConversation?.archived && inConversation
        ? '<p class="hint">Restore this conversation to answer.</p>'
        : `<button class="btn ghost small" type="button" data-open-choice-conversation="${esc(conversationId)}">Open conversation to choose</button>`}
    </section>`;
  }
  const multi = data.selection_mode === "multiple";
  let draft = [];
  try { draft = JSON.parse(storageGet(choiceDraftKey(conversationId, questionId)) || "[]"); } catch {}
  const controls = options.map(option => `<label class="choice-option">
      <input data-choice-option type="${multi ? "checkbox" : "radio"}" name="choice-${esc(questionId)}" value="${esc(option.id)}" ${draft.includes(option.id) ? "checked" : ""} ${multi ? "" : "required"}>
      <span>${esc(option.label)}</span>
    </label>`).join("");
  return `<form class="choice-card" data-choice-form data-choice-question="${esc(questionId)}" data-choice-run="${esc(runId)}">
    <div class="choice-card-head"><span class="choice-kicker">Bot question</span><span class="choice-state">${multi ? "Choose any that fit" : "Choose one"}</span></div>
    <fieldset class="choice-options"><legend class="choice-question">${esc(data.question || "")}</legend>${controls}</fieldset>
    <p class="choice-error" data-choice-error role="status" aria-live="polite"></p>
    <button class="btn primary choice-submit" type="submit">Send answer</button>
  </form>`;
}

function renderChatEvent(e, resolvedMap, activeHumanEventSeq = null, choiceStates = {}, conversationId = "") {
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
    case "human_needed": {
      const eventSeq = Number(e.seq);
      const runId = e.run_id || currentRunId;
      const isCurrentWait = Number.isSafeInteger(eventSeq) && eventSeq === activeHumanEventSeq;
      const resumeWasRequested = isCurrentWait && requestedHumanResumes.has(`${runId}:${eventSeq}`);
      const action = isCurrentWait
        ? (resumeWasRequested
          ? '<p class="hint" role="status">Resume requested. Waiting for the run to continue.</p>'
          : `<button class="btn primary" type="button" data-human-resume data-run-id="${esc(runId)}" data-event-seq="${eventSeq}">I've cleared it — resume</button>`)
        : "";
      return `<div class="run-cause"><b>${icon("alert")} Needs a person:</b> ${esc(d.reason || d.note || "A login, CAPTCHA, or 2FA step is waiting.")} ${
        d.handoff ? `<br><span class="hint">${esc(d.handoff)}</span>` : ""}${action ? `<div class="human-resume-action">${action}</div>` : ""}</div>`;
    }
    case "choice_requested":
      return choiceCardHtml(e, choiceStates[d.question_id], conversationId);
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
      <span class="ov-row-main"><b>${esc(botDisplayName(r.bot_display_name || r.bot_name))}</b>${statusChip(r.status)}</span>
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
              <span class="ov-approval-head"><b>${esc(botDisplayName(a.bot_display_name || a.bot_name))}</b> <span class="tag">${esc(a.tool)}</span> <span class="tag ${a.risk === "high" ? "danger" : ""}">${esc(a.risk)} risk</span></span>
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
              <span class="ov-row-main"><b>${esc(botDisplayName(x.bot_display_name || x.bot_name))}</b><span class="status stale">stale</span></span>
              <span class="ov-row-meta">last success ${timeAgo(x.last_success)}</span>
            </a>`).join("") : `<div class="empty-state">${icon("check", "icon-lg")}<p>Every scheduled bot is up to date.</p></div>`}
        </section>
      </div>
    </div></div>`;
}

/* -------------------------------------------------------------- schedules */

const SCHEDULE_PAGE_SIZE = 100;
let scheduleOverview = { rows: [], bots: [], control: null, hasMore: false, generation: 0 };
let scheduleControlPending = false;

function scheduleNextTime(row) {
  if (!row.next_fire) return "Next time unavailable";
  const date = new Date(row.next_fire);
  if (Number.isNaN(date.valueOf())) return "Next time unavailable";
  try {
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      timeZone: row.timezone, timeZoneName: "short",
    }).format(date);
  } catch { return "Next time unavailable"; }
}

function schedulePauseStatus(row) {
  if (row.workspace_paused && row.paused) return "Paused in workspace and for this Bot";
  if (row.workspace_paused) return "Paused across workspace";
  if (row.paused) return "Paused for this Bot";
  return "Scheduled";
}

function paintSchedules() {
  const restoreFocusId = document.activeElement?.id?.startsWith("schedule-")
    ? document.activeElement.id : null;
  const { rows, bots, control, hasMore } = scheduleOverview;
  const paused = !!control?.paused;
  const empty = rows.length === 0;
  const emptyDetails = bots.length === 1
    ? `<a class="btn primary" href="#/bot/${encodeURIComponent(bots[0].name)}">Set up a schedule for ${esc(bots[0].display_name || bots[0].name)}</a>`
    : bots.length > 1
      ? `<details class="schedule-empty-bots" aria-label="Bots available for recurring tasks">
        <summary class="btn ghost small">Choose a Bot ${icon("down", "schedule-empty-chevron")}</summary>
          <p class="hint">Choose where to create the recurring task.</p>
          <div class="schedule-empty-bot-list">${bots.map(bot => `<a class="btn ghost small" href="#/bot/${encodeURIComponent(bot.name)}">${esc(bot.display_name || bot.name)} settings</a>`).join("")}</div>
        </details>`
    : `<a class="btn primary" href="#/chat">Create a Bot</a>`;
  setTopContext(`<div class="ctx-id"><h1>Schedules</h1></div>
    <div class="ctx-actions schedule-control-actions"><span class="schedule-control-state" role="status">Workspace schedules ${paused ? "paused" : "active"}</span>
      <button class="btn ${paused ? "primary" : "ghost"} small" id="schedule-control-toggle" type="button"
        ${scheduleControlPending ? 'aria-disabled="true" aria-busy="true"' : ""}>
        ${paused ? "Resume workspace schedules" : "Pause all schedules"}
      </button></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container schedule-overview">
      <p class="schedule-overview-note">See the next run in each task’s own time zone. While paused, no new scheduled run starts; queued or running work continues. On resume, missed windows follow each task’s catch-up policy. Bot-specific pauses remain in effect.</p>
      ${paused ? `<p class="schedule-paused-note" role="status">Future scheduled admissions are paused. Missed windows follow each task’s catch-up policy after resume.</p>` : ""}
      ${empty ? `<section class="empty-state schedule-empty" aria-labelledby="schedule-empty-title">
          ${icon("clock", "icon-lg")}<h2 id="schedule-empty-title">No recurring tasks yet</h2>
          <p class="hint">Bots only run on a schedule when you add a recurring task in their settings.</p>${emptyDetails}
        </section>` : `
        <div class="schedule-overview-heading"><h2>Upcoming scheduled work</h2>
          <span class="hint" role="status">${rows.length}${hasMore ? "+" : ""} task${rows.length === 1 ? "" : "s"}${hasMore ? " loaded" : ""}</span>
        </div>
        <div class="schedule-overview-list" role="list">
          ${rows.map(row => {
            const botLabel = row.bot_display_name || row.bot_name;
            const scheduleStatus = schedulePauseStatus(row);
            const catchUp = row.catch_up === "coalesce" ? "Missed windows combine into one run" : "Missed windows are skipped";
            return `<article class="schedule-overview-row" role="listitem">
              <div class="schedule-overview-task">
                <div class="schedule-overview-bot"><a href="#/chat/${encodeURIComponent(row.bot_name)}">${esc(botLabel)}</a>
                  <span class="tag">${esc(scheduleStatus)}</span></div>
                <h3>${esc(row.name)}</h3>
                <p class="schedule-overview-pattern"><span>Cron</span> <code>${esc(row.cron)}</code><span aria-hidden="true">·</span>
                  <span>${esc(catchUp)}</span></p>
                ${row.last_skip?.windows ? `<p class="schedule-skip" role="status">Last skipped ${Number(row.last_skip.windows).toLocaleString()} missed window${Number(row.last_skip.windows) === 1 ? "" : "s"}${row.last_skip.at ? ` · ${esc(timeAgo(row.last_skip.at))}` : ""}.</p>` : ""}
              </div>
              <div class="schedule-overview-next"><span>${row.effective_paused ? "Next scheduled time" : "Next run"}</span>
                ${row.next_fire ? `<time datetime="${esc(row.next_fire)}">${esc(scheduleNextTime(row))}</time>` : `<strong>Unavailable</strong>`}
                <small>${esc(row.timezone)}</small></div>
              <a class="btn ghost small schedule-overview-edit" href="#/bot/${encodeURIComponent(row.bot_name)}">Edit schedule</a>
            </article>`;
          }).join("")}
        </div>
        ${hasMore ? `<div class="schedule-overview-more"><button class="btn ghost" id="schedule-load-more" type="button">Load 100 more</button></div>` : ""}`}
    </div></div>`;

  const toggle = $("#schedule-control-toggle");
  toggle?.addEventListener("click", async () => {
    if (scheduleControlPending) return;
    scheduleControlPending = true;
    toggle.setAttribute("aria-disabled", "true");
    toggle.setAttribute("aria-busy", "true");
    try {
      const result = await api("/v1/schedules/control", { method: "PUT", body: { paused: !paused } });
      toast(result.paused ? "Future scheduled starts paused. Existing runs continue." : "Workspace schedule pause removed. Bot-specific pauses remain.");
      scheduleControlPending = false;
      await renderSchedules();
      $("#schedule-control-toggle")?.focus({ preventScroll: true });
    } catch (error) {
      scheduleControlPending = false;
      toast(`Schedule control was not changed: ${error.message}`, true);
      const currentToggle = $("#schedule-control-toggle");
      currentToggle?.removeAttribute("aria-disabled");
      currentToggle?.removeAttribute("aria-busy");
    }
  });

  const more = $("#schedule-load-more");
  more?.addEventListener("click", async () => {
    if (more.disabled) return;
    more.disabled = true;
    more.setAttribute("aria-busy", "true");
    try {
      const next = await api(`/v1/schedules?limit=${SCHEDULE_PAGE_SIZE}&offset=${scheduleOverview.rows.length}`);
      if (location.hash !== "#/schedules") return;
      scheduleOverview.rows.push(...next);
      scheduleOverview.hasMore = next.length === SCHEDULE_PAGE_SIZE;
      paintSchedules();
      $("#schedule-load-more")?.focus();
    } catch (error) {
      toast(`More schedules could not be loaded: ${error.message}`, true);
      if (more.isConnected) { more.disabled = false; more.removeAttribute("aria-busy"); }
    }
  });

  // Resource-feed refreshes can repaint this page while a schedule command is
  // resolving. Keep keyboard focus on the replacement control across either
  // repaint so background updates do not strand the user on the document.
  if (restoreFocusId) document.getElementById(restoreFocusId)?.focus({ preventScroll: true });
}

async function renderSchedules() {
  const generation = ++scheduleOverview.generation;
  const routeAtStart = location.hash;
  const alreadyVisible = routeAtStart === "#/schedules" && !!$(".schedule-overview", view);
  if (!alreadyVisible) {
    setTopContext(`<div class="ctx-id"><h1>Schedules</h1></div>`);
    view.innerHTML = `<div class="page-scroll"><div class="container"><div class="empty-state"><div class="spinner" role="status" aria-label="Loading schedules"></div><p>Loading schedules…</p></div></div></div>`;
  }
  const [control, rows, bots] = await Promise.all([
    api("/v1/schedules/control"),
    api(`/v1/schedules?limit=${SCHEDULE_PAGE_SIZE}&offset=0`),
    api("/bots"),
  ]);
  if (generation !== scheduleOverview.generation || location.hash !== routeAtStart) return;
  scheduleOverview = { rows, bots, control, hasMore: rows.length === SCHEDULE_PAGE_SIZE, generation };
  paintSchedules();
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
              <span class="bot-name">${esc(b.display_name || b.name)}</span>
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
              <details class="fleet-card-menu">
                <summary class="icon-btn" data-fleet-options="${esc(b.name)}" aria-label="More options for ${esc(b.display_name || b.name)}" title="More options">${icon("moreHorizontal")}</summary>
                <div class="fleet-card-menu-panel" aria-label="More options for ${esc(b.display_name || b.name)}">
                  <button class="fleet-card-menu-item" type="button" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                    ${icon(b.paused ? "play" : "pause")} ${b.paused ? "Resume bot" : "Pause bot"}
                  </button>
                  <a class="fleet-card-menu-item" href="#/bot/${esc(b.name)}">${icon("sliders")} Bot settings</a>
                </div>
              </details>
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
      if (q && !`${r.bot_display_name || ""} ${r.bot_name} ${r.prompt}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const wrap = $("#runs-table-wrap");
    if (!wrap) return;
    if (!filtered.length) {
      wrap.classList.remove("runs-has-results");
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
      wrap.classList.add("runs-has-results");
      wrap.innerHTML = `
        <div class="run-card-list" aria-label="Run history">
          ${rows.map(r => {
            const d = durMs(r);
            const displayName = r.bot_display_name || r.bot_name;
            return `<a class="run-card" href="#/run/${esc(r.id)}">
              <div class="run-card-head">
                <span class="run-card-bot">${botAvatar(r.bot_name, 28)}<b title="${esc(r.bot_name)}">${esc(displayName)}</b></span>
                ${statusChip(r.status, r.status_label)}
              </div>
              <p class="run-card-prompt">${esc(r.prompt || "No prompt saved.")}</p>
              <div class="run-card-meta"><span>${fmtDur(d)}</span><span>${r.steps} steps</span><span>${fmtTokens(r.tokens)} tokens</span></div>
              <div class="run-card-foot"><code>${esc(r.id.slice(0, 12))}…</code><time datetime="${esc(r.created_at || "")}">${timeAgo(r.created_at)}</time></div>
            </a>`;
          }).join("")}
        </div>
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
                <td><b title="${esc(r.bot_name)}">${esc(r.bot_display_name || r.bot_name)}</b></td>
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
      ? pending.map(a => approvalCardHtml(a, { botName: botDisplayName(a.bot_display_name || a.bot_name) })).join("")
      : `<div class="empty-state">${icon("check", "icon-lg")}<p>No pending approvals.</p><p class="hint">Requests appear in their conversation and here.</p></div>`;
    const total = stats.pending_approvals;
    $("#approvals-pagination").innerHTML = total ? `<span class="hint">${offset + 1}–${offset + pending.length} of ${total} requests</span>
      ${offset ? '<button class="btn ghost small" id="approvals-prev">Previous</button>' : ""}
      ${offset + pending.length < total ? '<button class="btn ghost small" id="approvals-next">Next</button>' : ""}` : "";
    $("#approvals-prev")?.addEventListener("click", () => { approvalOffset = Math.max(0, offset - APPROVAL_PAGE_SIZE); refreshApprovals(); });
    $("#approvals-next")?.addEventListener("click", () => { approvalOffset = offset + APPROVAL_PAGE_SIZE; refreshApprovals(); });
    $("#approvals-resolved").innerHTML = resolved.length
      ? resolved.map(a => approvalResolvedHtml(a, a.status, botDisplayName(a.bot_display_name || a.bot_name))).join("")
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

let botDetailRenderGeneration = 0;

const TOOL_SETTINGS = [
  ["read_file", "Read workspace files", "Open text files inside this run’s workspace."],
  ["list_files", "List workspace files", "See file names under this run’s workspace."],
  ["write_file", "Write workspace files", "Create or replace files; approval policy still applies."],
  ["shell", "Run shell commands", "Run commands inside the configured shell boundary."],
  ["web_fetch", "Fetch public pages", "Read public HTTP(S) pages through Hutch’s checked request path."],
  ["browser", "Use a browser", "Control this bot’s isolated browser profile."],
  ["remember", "Propose reference facts", "Suggest facts for human review before they can be recalled."],
  ["recall", "Recall reviewed facts", "Search reviewed facts available to this bot and chat."],
  ["delegate_task", "Delegate a bounded task", "Strict Offline only. Each request asks for approval and uses another run slot; the child receives only its task text."],
];

function scheduleEditorHtml(schedule, index, status = null) {
  const id = String(schedule.id || "");
  let nextFire = "Not calculated";
  if (status?.next_fire) {
    try { nextFire = new Intl.DateTimeFormat(undefined, {dateStyle:"medium", timeStyle:"short", timeZone:schedule.timezone || "UTC"})
      .format(new Date(status.next_fire)); } catch { nextFire = "Next run available"; }
  }
  const formId = index === 0 ? "form-schedule" : `form-schedule-${index}`;
  return `<details class="schedule-entry" data-schedule-entry ${index === 0 ? "open" : ""}>
    <summary class="schedule-summary">
      <strong>${esc(schedule.name || "Scheduled task")}</strong>
      <span class="schedule-summary-cron mono">${esc(schedule.cron)} · ${esc(schedule.timezone || "UTC")}</span>
      <span class="tag">${index === 0 ? "Primary" : `Task ${index + 1}`}</span>
    </summary>
    <form id="${formId}" class="form-grid schedule-editor" data-schedule-form data-schedule-id="${esc(id)}">
      <div class="form-grid row2">
        <label class="field">Task name
          <input type="text" name="name" maxlength="80" value="${esc(schedule.name || "Scheduled task")}" required>
        </label>
        <label class="field">Cron expression
          <input type="text" name="cron" value="${esc(schedule.cron || "")}" placeholder="0 9 * * 1" required>
        </label>
        <label class="field">Timezone
          <input type="text" name="timezone" value="${esc(schedule.timezone || "UTC")}" required>
        </label>
        <label class="field">Missed run policy
          <select name="catch_up">
            <option value="coalesce" ${schedule.catch_up === "coalesce" ? "selected" : ""}>Run once and report missed windows</option>
            <option value="skip" ${schedule.catch_up === "skip" ? "selected" : ""}>Skip if the last window was missed</option>
          </select>
        </label>
      </div>
      <label class="field">Task prompt
        <textarea name="schedule_prompt" rows="3" maxlength="4000" aria-describedby="schedule-prompt-help-${index}">${esc(schedule.prompt || "")}</textarea>
        <span class="hint" id="schedule-prompt-help-${index}">Leave blank to use this bot’s standing instructions. Each scheduled task runs as a separate attempt.</span>
      </label>
      <div class="meta-row"><span>Next run</span><span class="mono">${esc(nextFire)}</span></div>
      ${status?.last_skip ? `<p class="hint schedule-skip" role="status">Last skipped ${esc(status.last_skip.windows)} missed windows.</p>` : ""}
      <div class="btn-row schedule-actions">
        <button class="btn primary small" type="submit">Save task</button>
        <button class="btn ghost small" type="button" data-remove-schedule="${esc(id)}">Remove task</button>
      </div>
    </form>
  </details>`;
}

async function renderBotDetail(name, factOffset = 0, showArchivedFacts = false) {
  const generation = ++botDetailRenderGeneration;
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  const runtimeNames = { builtin: "Hutch built-in", opencode: "OpenCode", pi: "Pi", mock: "Retired mock" };
  const runtimeName = runtimeNames[b.runtime] || b.runtime || "Unknown";
  const runtimeUnavailable = b.runtime !== "builtin";
  const runtimeSwitchBlocked = b.active_run_id ? "Stop or wait for the active run before switching runtimes."
    : !b.model || b.model.startsWith("mock/") ? "Save a real Hutch model route above before switching."
      : "";
  const factsPage = await api(`/v1/bots/${encodeURIComponent(name)}/facts?all_scopes=true&limit=20&offset=${factOffset}&include_archived=${showArchivedFacts}`);
  const factSharesPage = await api(`/v1/bots/${encodeURIComponent(name)}/fact-shares?limit=20`)
    .catch(error => ({incoming:[], outgoing:[], error:error.message}));
  let specialistRoster = null;
  let specialistRosterError = "";
  if (b.is_workspace_coordinator) {
    try { specialistRoster = await api("/v1/workspace/specialists"); }
    catch (error) { specialistRosterError = error.message; }
  }
  const schedules = Array.isArray(b.schedules) ? b.schedules : (b.schedule ? [b.schedule] : []);
  let scheduleRows = [];
  try { scheduleRows = await api(`/v1/schedules?bot=${encodeURIComponent(b.id)}&limit=100&offset=0`); } catch {}
  const scheduleStatus = new Map(scheduleRows.map(item => [item.id, item]));
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
    : "Hutch could not verify worker network isolation on this host. Strict Offline stays unavailable; run hutch doctor for exact diagnostics. Local model routes alone do not make a run offline; the separate model service may still use the network.";
  const handoffReason = ["supported", "experimental"].includes(browserHandoffCapability.status)
    ? "Local browser handoff is experimental on this host. A login wait keeps the same browser window open and pauses automation. Only one Hutch handoff can run at a time. This does not enable phone control."
    : `Local browser handoff is unavailable on this host: ${browserHandoffCapability.reason}. It will fail closed until its display and browser prerequisites are available. This does not enable phone control.`;
  // A save can trigger another render before these independent resource reads
  // finish. Only the newest request for the still-active bot route may replace
  // the settings DOM; slower old responses otherwise discard newer task state.
  if (generation !== botDetailRenderGeneration || location.hash !== `#/bot/${encodeURIComponent(name)}`) return;
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(b.name, 30)}
          <h1>${esc(b.display_name || b.name)} settings</h1>
    </div>
    <div class="ctx-actions">
      <a class="btn ghost small" href="#/chat/${esc(b.name)}">${icon("chat")} Open Studio</a>
      <button class="btn danger small" id="btn-delete-bot">${icon("trash")}Delete bot</button>
    </div>`);

  const limits = b.limits || {};
  const rules = b.command_rules || [];
  const specialistRosterHtml = b.is_workspace_coordinator ? `
          <section class="panel" id="workspace-specialist-roster" aria-labelledby="workspace-specialist-roster-title">
            <details class="workspace-specialist-settings" id="workspace-specialist-settings" ${specialistRosterError ? "open" : ""}>
              <summary class="workspace-specialist-summary">
                <span class="workspace-specialist-heading" id="workspace-specialist-roster-title">Approved specialist Bots</span>
                <span class="workspace-specialist-count" id="workspace-specialist-roster-count">${specialistRosterError ? "Unavailable" : `${specialistRoster?.specialist_bot_ids.length || 0} approved`}</span>
                <span class="workspace-specialist-action"><span class="when-closed">Manage</span><span class="when-open">Close</span></span>
              </summary>
              <div class="workspace-specialist-content">
                <p class="hint">Only Bots you approve here can receive new tasks from the coordinator. This changes future assignments; it does not stop existing work or remove its history.</p>
            ${specialistRosterError
              ? `<p class="error" role="alert">The roster could not be loaded: ${esc(specialistRosterError)}. Reload this page before changing it.</p>`
              : specialistRoster?.bots.length
                ? `${specialistRoster.bots.length > 8 ? `<label class="field">Filter specialist Bots
                      <input type="search" id="workspace-specialist-filter" aria-controls="workspace-specialist-options" placeholder="Name or address">
                    </label><p id="workspace-specialist-filter-status" class="hint" role="status">${specialistRoster.bots.length} Bots available.</p>` : ""}
                  <fieldset class="workspace-specialist-list" id="workspace-specialist-options">
                    <legend class="sr-only">Bots the coordinator may assign new tasks to</legend>
                    ${specialistRoster.bots.map(bot => `<label class="workspace-task-fact-choice" data-workspace-specialist-choice>
                      <input type="checkbox" data-workspace-specialist="${esc(bot.id)}" ${specialistRoster.specialist_bot_ids.includes(bot.id) ? "checked" : ""}>
                      <span><strong>${esc(bot.display_name || bot.name)}</strong><span>@${esc(bot.name)}</span></span>
                    </label>`).join("")}
                  </fieldset>`
                : `<p class="hint">No other Bots are available yet. Create a Bot first, then add it here.</p>`}
            <div class="btn-row"><button class="btn primary small" type="button" id="btn-save-workspace-specialists" ${specialistRosterError ? "disabled" : ""}>Save specialist roster</button></div>
            <p class="hint" id="workspace-specialist-roster-status" aria-live="polite"></p>
              </div>
            </details>
          </section>` : "";
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="crumb"><a href="#/chat/${esc(b.name)}">Studio</a> / Settings</p>
      <div class="detail-grid">
        <div>
          <form class="panel form-grid" id="form-identity">
            <div class="panel-title">Identity and instructions</div>
            <label class="field">Display name
              <input type="text" name="display_name" maxlength="80" value="${esc(b.display_name || b.name)}" required>
              <span class="hint">Shown in chats and lists. The Bot address in existing links stays the same.</span>
            </label>
            <label class="field">Description
              <input type="text" name="description" value="${esc(b.description || "")}" placeholder="What this bot does">
            </label>
            <label class="field">System instructions
              <textarea name="instructions" rows="7">${esc(b.instructions || "")}</textarea>
            </label>
            <div class="btn-row"><button class="btn primary small" type="submit">Save</button></div>
          </form>

          <section class="panel" aria-labelledby="workspace-coordinator-title">
            <div class="panel-title" id="workspace-coordinator-title">Workspace coordinator</div>
            <p class="hint">Choose one Bot as the main conversation for your workspace. You can still chat with every Bot directly. This role does not add tools, account access, or permissions.</p>
            ${b.is_workspace_coordinator
              ? `<div class="coordinator-role-state" role="status"><span class="tag" id="workspace-coordinator-settings-state">Current coordinator</span>
                  <button class="btn ghost small" type="button" id="btn-clear-workspace-coordinator">Clear role</button></div>`
              : `<button class="btn ghost small" type="button" id="btn-set-workspace-coordinator">Set as workspace coordinator</button>`}
          </section>

          ${specialistRosterHtml}

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
              <label class="field">Execution runtime
                <input type="text" disabled value="${esc(runtimeUnavailable ? `${runtimeName} (unavailable)` : runtimeName)}">
              </label>
            </div>
            ${runtimeUnavailable ? `<div class="runtime-recovery" id="runtime-recovery" role="status">
              <p><strong>${esc(runtimeName)} execution is unavailable in Hutch.</strong> Hutch will not launch this external runtime.</p>
              <p class="hint">Switching uses this bot’s Hutch model route, tools, approvals and budget controls. Hutch never imports private sign-in files or credentials from another application.</p>
              <div class="btn-row">
                <button class="btn primary small" type="button" id="btn-runtime-to-builtin" ${runtimeSwitchBlocked ? "disabled" : ""}>Use Hutch’s built-in runtime</button>
                ${runtimeSwitchBlocked ? `<span class="hint">${esc(runtimeSwitchBlocked)}</span>` : ""}
              </div>
            </div>` : ""}
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

          ${(b.chatgpt_background || []).length ? `<section class="panel" aria-labelledby="background-plan-consent-title">
            <div class="panel-title" id="background-plan-consent-title">ChatGPT plan for unattended runs</div>
            <p class="hint">Scheduled tasks and coordinator-assigned specialist tasks can run while you are away. Hutch requires a separate, explicit permission for each ChatGPT account used by this Bot. It covers only this Bot’s current model, fallback and escalation routes. Changing those routes or disconnecting the account removes the permission.</p>
            <div class="settings-list">${b.chatgpt_background.map(route => `
              <div class="meta-row background-consent-row">
                <span><b>${esc(route.title)}</b><br><span class="hint">${route.state === "allowed" ? "Allowed for this route" : route.state === "sign_in_required" ? "Sign in again before enabling" : "Permission required"}</span></span>
                ${route.state === "sign_in_required"
                  ? `<a class="btn ghost small" href="#/connections">Open Connections</a>`
                  : `<button class="btn ${route.state === "allowed" ? "ghost" : "primary"} small" type="button" data-background-provider="${esc(route.provider)}" data-route-fingerprint="${esc(route.route_fingerprint)}" data-consent-state="${esc(route.state)}">${route.state === "allowed" ? "Revoke" : "Review and allow"}</button>`}
              </div>`).join("")}</div>
          </section>` : ""}

          <section class="panel" aria-labelledby="tool-settings-title">
            <div class="panel-title" id="tool-settings-title">Tools</div>
            <p class="hint" id="tool-settings-help">Choose what this bot may call. Every action still passes Hutch’s policy and approval checks. Strict Offline removes browser and public-page tools.</p>
            <form id="form-tools">
              <div class="tool-options" role="group" aria-labelledby="tool-settings-title" aria-describedby="tool-settings-help">
                ${TOOL_SETTINGS.map(([value, label, help]) => `
                  <label class="tool-option">
                    <input type="checkbox" name="tools" value="${esc(value)}" ${(b.tools || []).includes(value) ? "checked" : ""}>
                    <span class="tool-option-copy"><b>${esc(label)}</b><small>${esc(help)}</small></span>
                  </label>`).join("")}
              </div>
              <div class="btn-row tool-options-actions"><button class="btn primary small" type="submit">Save tools</button></div>
            </form>
          </section>

          <section class="panel schedule-manager" id="schedule-manager" aria-labelledby="schedule-manager-title">
            <div class="schedule-manager-head">
              <div>
                <div class="panel-title" id="schedule-manager-title">Recurring tasks</div>
                <p class="hint">Each task has its own timing and prompt. Runs share this bot’s tools, workspace, limits, and permissions.</p>
              </div>
              <button class="btn primary small" type="button" id="btn-add-schedule">Add task</button>
            </div>
            <div class="schedule-list" id="schedule-list">
              ${schedules.length ? schedules.map((scheduled, index) =>
                scheduleEditorHtml(scheduled, index, scheduleStatus.get(scheduled.id))).join("")
                : `<div class="empty-state schedule-empty"><p>No recurring tasks yet.</p><p class="hint">Add one when this bot should work on a regular schedule.</p></div>`}
            </div>
          </section>

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
            <div class="memory-actions"><button class="btn ghost small" id="memory-export" type="button">Download memory JSON</button></div>
            ${factsPage.facts.map(factCardHtml).join('') || `<p class="empty-inline">No active facts in this window.</p>`}
            ${factShareRecordsHtml(factSharesPage)}
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
    patch({ display_name: fd.get("display_name"), description: fd.get("description"), instructions: fd.get("instructions") }, "Saved.");
  });
  $("#btn-set-workspace-coordinator")?.addEventListener("click", () => {
    const current = botsCache.find(bot => bot.is_workspace_coordinator);
    const replacement = current && current.id !== b.id
      ? `<p>This replaces <b>${esc(current.display_name || current.name)}</b> as the workspace coordinator. It does not change either Bot’s permissions or settings.</p>`
      : `<p>This makes <b>${esc(b.display_name || b.name)}</b> the main workspace conversation. It does not change the Bot’s permissions or settings.</p>`;
    openModal({ title: "Set workspace coordinator?", bodyHtml: `${replacement}<p>If this Bot is currently an approved specialist, it will be removed from that roster. The former coordinator will not be added automatically. You can still open a direct conversation with each Bot from the roster.</p>`,
      confirmText: "Set coordinator", returnFocus: $("#btn-set-workspace-coordinator"),
      onConfirm: async () => {
        try {
          await api("/v1/workspace/coordinator", { method: "PUT", body: { bot_id: b.id } });
          toast(`${b.display_name || b.name} is now the workspace coordinator.`);
          await refreshRoster();
          await renderBotDetail(b.name);
          return true;
        } catch (err) { toast(`Coordinator not changed: ${err.message}`, true); return false; }
      },
    });
  });
  $("#btn-save-workspace-specialists")?.addEventListener("click", async () => {
    const button = $("#btn-save-workspace-specialists");
    const ids = $$('[data-workspace-specialist]:checked').map(input => input.dataset.workspaceSpecialist);
    button.disabled = true;
    try {
      const saved = await api("/v1/workspace/specialists", { method: "PUT", body: { bot_ids: ids } });
      const status = $("#workspace-specialist-roster-status");
      if (status) status.textContent = `Roster saved. ${saved.specialist_bot_ids.length} specialist ${saved.specialist_bot_ids.length === 1 ? "Bot" : "Bots"} approved for new assignments.`;
      const count = $("#workspace-specialist-roster-count");
      if (count) count.textContent = `${saved.specialist_bot_ids.length} approved`;
      await refreshRoster();
      button.disabled = false;
    } catch (err) {
      toast(`Roster not saved: ${err.message}`, true);
      button.disabled = false;
    }
  });
  $("#workspace-specialist-filter")?.addEventListener("input", event => {
    const query = event.currentTarget.value.trim().toLocaleLowerCase();
    const choices = $$('[data-workspace-specialist-choice]');
    let shown = 0;
    for (const choice of choices) {
      const matches = choice.textContent.toLocaleLowerCase().includes(query);
      choice.hidden = !matches;
      shown += Number(matches);
    }
    const status = $("#workspace-specialist-filter-status");
    if (status) status.textContent = `${shown} of ${choices.length} Bots shown.`;
  });
  $("#btn-clear-workspace-coordinator")?.addEventListener("click", () => {
    openModal({ title: "Clear workspace coordinator?", bodyHtml: `<p>${esc(b.display_name || b.name)} will remain a Bot and its direct conversations will stay available. The workspace will not have a selected main conversation.</p>`,
      confirmText: "Clear role", confirmClass: "danger", returnFocus: $("#btn-clear-workspace-coordinator"),
      onConfirm: async () => {
        try {
          await api("/v1/workspace/coordinator", { method: "PUT", body: { bot_id: null } });
          toast("Workspace coordinator cleared.");
          await refreshRoster();
          await renderBotDetail(b.name);
          return true;
        } catch (err) { toast(`Coordinator not changed: ${err.message}`, true); return false; }
      },
    });
  });
  $("#form-model").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ model: fd.get("model").trim(), inference_mode: fd.get("inference_mode") }, "Model settings saved.");
  });
  $$('[data-background-provider]').forEach(button => button.addEventListener("click", () => {
    const provider = button.dataset.backgroundProvider;
    if (button.dataset.consentState === "allowed") {
      openModal({
        title: "Revoke ChatGPT background use?",
        bodyHtml: `<p>Scheduled and coordinator-assigned specialist runs for <b>${esc(b.display_name || b.name)}</b> will stop using this ChatGPT account after any current request finishes. Messages you start remain governed by this Bot’s model and provider settings.</p>`,
        confirmText: "Revoke permission", confirmClass: "danger", returnFocus: button,
        onConfirm: async () => {
          try {
            await api(`/v1/bots/${encodeURIComponent(b.id)}/background-provider-consents/${encodeURIComponent(provider)}`, { method: "DELETE" });
            toast("Background permission revoked.");
            await renderBotDetail(b.name);
            return true;
          } catch (err) { toast(`Permission not revoked: ${err.message}`, true); return false; }
        },
      });
      return;
    }
    const route = (b.chatgpt_background || []).find(item => item.provider === provider);
    openModal({
      title: "Allow scheduled ChatGPT plan use?",
      bodyHtml: `<p>Allow <b>${esc(route?.title || "this ChatGPT account")}</b> to serve this Bot’s scheduled tasks and coordinator-assigned specialist tasks when you are not in the conversation?</p><p>Hutch will use the plan only for this Bot and its current model, fallback and escalation routes. The permission is stored on this Hutch machine, is tied to this account, and stops matching if its route changes. You can revoke it here at any time. OpenAI’s preview eligibility and usage limits still apply.</p>`,
      confirmText: "Allow background use", returnFocus: button,
      onConfirm: async () => {
        try {
          await api(`/v1/bots/${encodeURIComponent(b.id)}/background-provider-consents/${encodeURIComponent(provider)}`, {
            method: "PUT", body: { route_fingerprint: button.dataset.routeFingerprint },
          });
          toast("Background permission saved for this ChatGPT account and route.");
          await renderBotDetail(b.name);
          return true;
        } catch (err) { toast(`Permission not saved: ${err.message}`, true); return false; }
      },
    });
  }));
  $("#btn-runtime-to-builtin")?.addEventListener("click", () =>
    patch({ runtime: "builtin" }, "Switched to Hutch’s built-in runtime."));
  $("#form-tools").addEventListener("submit", ev => {
    ev.preventDefault();
    const tools = [...ev.target.querySelectorAll('input[name="tools"]:checked')].map(input => input.value);
    patch({ tools }, "Tool permissions saved.");
  });
  $("#btn-add-schedule").addEventListener("click", () => {
    const form = `<form id="modal-schedule-form" class="form-grid">
      <label class="field">Task name<input name="name" maxlength="80" value="Scheduled task" required></label>
      <div class="form-grid row2">
        <label class="field">Cron expression<input name="cron" placeholder="0 9 * * 1" required></label>
        <label class="field">Timezone<input name="timezone" value="UTC" required></label>
      </div>
      <label class="field">Missed run policy<select name="catch_up"><option value="coalesce">Run once and report missed windows</option><option value="skip">Skip if the last window was missed</option></select></label>
      <label class="field">Task prompt<textarea name="prompt" rows="3" maxlength="4000"></textarea>
        <span class="hint">Leave blank to use this bot’s standing instructions.</span>
      </label>
    </form>`;
    openModal({ title: "Add a recurring task", bodyHtml: form, confirmText: "Add task", returnFocus: $("#btn-add-schedule"),
      onConfirm: async () => {
        const fd = new FormData($("#modal-schedule-form"));
        const scheduleId = `schedule_${newIdempotencyKey().replace(/[^a-zA-Z0-9_-]/g, "")}`;
        try {
          await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(scheduleId)}`, {
            method: "PUT", body: { name: fd.get("name").trim(), cron: fd.get("cron").trim(),
              timezone: fd.get("timezone").trim(), catch_up: fd.get("catch_up"), prompt: fd.get("prompt").trim() },
          });
          toast("Recurring task added.");
          renderBotDetail(b.name); refreshRoster();
          return true;
        } catch (err) { toast(`Task not added: ${err.message}`, true); return false; }
      },
    });
  });
  $$('[data-schedule-form]').forEach(form => form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const fd = new FormData(form);
    const scheduleId = form.dataset.scheduleId;
    try {
      await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(scheduleId)}`, {
        method: "PUT", body: { name: fd.get("name").trim(), cron: fd.get("cron").trim(),
          timezone: fd.get("timezone").trim(), catch_up: fd.get("catch_up"), prompt: fd.get("schedule_prompt").trim() },
      });
      toast("Scheduled task saved.");
      renderBotDetail(b.name); refreshRoster();
    } catch (err) { toast(`Task not saved: ${err.message}`, true); }
  }));
  $$('[data-remove-schedule]').forEach(button => button.addEventListener("click", async () => {
    const schedule = schedules.find(item => item.id === button.dataset.removeSchedule);
    if (!schedule) return;
    if (!(await confirmDialog({ title: "Remove scheduled task", body: `Remove <b>${esc(schedule.name)}</b> from ${esc(b.name)}? Existing runs and their history remain.`,
                               confirmText: "Remove task", danger: true }))) return;
    try {
      await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(schedule.id)}`, { method: "DELETE" });
      toast("Scheduled task removed.");
      renderBotDetail(b.name); refreshRoster();
    } catch (err) { toast(`Task not removed: ${err.message}`, true); }
  }));
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
  wireFactControls(factsPage.facts, b.name, factSharesPage);
  $('#memory-toggle').onclick = () => patch({memory_enabled: !b.memory_enabled}, `Memory ${b.memory_enabled ? 'disabled' : 'enabled'}.`);
  $('#memory-archives').onclick = () => renderBotDetail(name, 0, !showArchivedFacts);
  $('#memory-export').onclick = event => {
    const button = event.currentTarget;
    openModal({
      title: 'Export Bot memory', confirmText: 'Download JSON', returnFocus: button,
      bodyHtml: `<p>Archived fact versions and review history are included with saved provenance and incoming or outgoing Bot shares.</p>
        <p>Excluded: conversation transcripts, credentials, action receipts, and workspace files.</p>
        <p class="hint">This downloads unencrypted plaintext and may include personal or sensitive fact values and review notes. Review the file before sharing it. Never save passwords or credentials in memory. Export is limited to 10,000 fact revisions, 5,000 shares per direction, and 2 MiB of source data.</p>
        <p id="memory-export-error" class="hint" role="status"></p>`,
      onConfirm: async () => {
        const confirm = $('#modal-confirm');
        const error = $('#memory-export-error');
        confirm.disabled = true;
        try {
          const response = await fetch(`/api/v1/bots/${encodeURIComponent(b.name)}/memory/export`, {
            headers: {Accept: 'application/json'}, credentials: 'same-origin',
          });
          if (!response.ok) {
            let message = `Export failed (${response.status}).`;
            try { message = (await response.json()).detail || message; } catch {}
            throw new Error(message);
          }
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `hutch-memory-${b.name}.json`;
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 60_000);
          return true;
        } catch (err) {
          error.textContent = `Memory export was not downloaded: ${err.message}`;
          return false;
        } finally {
          if (confirm.isConnected) confirm.disabled = false;
        }
      },
    });
  };
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
        <section class="run-integrity panel" aria-label="Transcript integrity" data-run-integrity-run="${esc(runId)}">
          <div class="run-integrity-copy"><strong>Transcript integrity</strong>
            <p class="hint" data-run-integrity-result role="status" aria-live="polite">Not checked for this run.</p>
          </div>
          <button class="btn ghost small" type="button" data-verify-run-history>Verify event history</button>
        </section>
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
  const verifyButton = $(`[data-verify-run-history]`, stream);
  const savedIntegrity = runIntegrityStates.get(runId);
  if (savedIntegrity) {
    setRunIntegrityState(runId, savedIntegrity);
    if (savedIntegrity.state === "checking" && verifyButton) verifyButton.disabled = true;
  }
  verifyButton?.addEventListener("click", async () => {
    if (verifyButton.disabled) return;
    verifyButton.disabled = true;
    setRunIntegrityState(runId, { text: "Checking the saved event history…", state: "checking", role: "status" });
    try {
      const verification = await api(`/v1/tasks/runs/${encodeURIComponent(runId)}/verify`);
      if (!verification.ok) {
        const location = verification.bad_seq ? `event ${verification.bad_seq}` : "the event sequence";
        setRunIntegrityState(runId, { text: `Integrity check failed at ${location}. Preserve and review this transcript.`,
          state: "failed", role: "alert" });
      } else if (verification.legacy) {
        const checkedLabel = `${verification.checked} chained event${verification.checked === 1 ? "" : "s"} verified`;
        const legacyLabel = `${verification.legacy} older event${verification.legacy === 1 ? "" : "s"} ${verification.legacy === 1 ? "has" : "have"} no hash.`;
        setRunIntegrityState(runId, { text: `${checkedLabel}; ${legacyLabel}`,
          state: "partial", role: "status" });
      } else if (verification.checked) {
        setRunIntegrityState(runId, { text: `${verification.checked} chained event${verification.checked === 1 ? "" : "s"} verified.`,
          state: "verified", role: "status" });
      } else {
        setRunIntegrityState(runId, { text: "No events were present to verify.", state: "empty", role: "status" });
      }
    } catch (error) {
      setRunIntegrityState(runId, { text: `Transcript verification could not finish: ${error.message}`,
        state: "failed", role: "alert" });
    } finally {
      if (verifyButton.isConnected) verifyButton.disabled = false;
      const currentSection = $$('[data-run-integrity-run]', view).find(node => node.dataset.runIntegrityRun === runId);
      const currentButton = currentSection && $("[data-verify-run-history]", currentSection);
      if (currentButton) currentButton.disabled = false;
    }
  });
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

function modelCapabilityResultsMarkup(page, error) {
  if (error) return `<p class="hint bad" role="alert">Observation history could not be loaded: ${esc(error)}. Model capability remains unknown until Hutch can read the evidence.</p>`;
  if (!page?.items?.length) return '<p class="hint" role="status">No tool-call observations recorded yet. Capability is unknown, not passed or failed; model availability checks do not test tool calling.</p>';
  return `<ol class="model-capability-list" aria-label="Latest model tool-call observations">${page.items.map(item => `
    <li class="model-capability-row">
      <div class="model-capability-main"><strong>${esc(item.provider)} · ${esc(item.model)}</strong>
        <span class="tag ok">Observed</span>
        <p class="hint">Returned <code>${esc(item.source_tool)}</code> · route revision <code>${esc(item.route_revision.slice(0, 12))}</code></p></div>
      <time class="hint" datetime="${esc(item.observed_at)}">${esc(new Date(item.observed_at).toLocaleString())}</time>
    </li>`).join("")}</ol>
    <p class="hint">Showing the latest ${page.items.length} recorded observation${page.items.length === 1 ? "" : "s"}. An absent record means unknown; it does not mean the model failed a test.</p>`;
}

async function renderConnections() {
  let data;
  try { data = await api("/connections"); }
  catch (err) { view.innerHTML = errorState(err); return; }
  const modelCapabilityRequest = api("/v1/model-capabilities?direction=desc&limit=5")
    .then(page => ({ page, error: "" }))
    .catch(err => ({ page: null, error: err.message }));
  let bots = [];
  try { bots = await api("/bots"); }
  catch { /* Provider and device controls remain usable if the Bot list is unavailable. */ }
  const botLabels = new Map(bots.map(bot => [bot.id, bot.display_name || bot.name]));
  const grantedBotLabel = grant => grant
    ? (botLabels.get(grant.bot_id) || grant.bot_display_name || grant.bot_name || "this Bot")
    : "this Bot";
  let devices = [];
  let devicesError = "";
  try { devices = await api("/v1/devices"); }
  catch (err) { devicesError = err.message; }
  setTopContext(`<div class="ctx-id"><h1>Connections</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-add-conn">${icon("plus")} Add connection</button></div>`);
  const conns = data.connections || [];
  const googleOAuthClient = data.google_oauth_client || {
    client_id: "", source: "unset", editable: true, configured: false, valid: false,
    detail: "Enter a Google Desktop OAuth client ID ending in .apps.googleusercontent.com.",
  };
  const googleCalendar = data.google_calendar || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const googleMail = data.google_mail || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const googleMailBots = bots.filter(bot => bot.inference_mode === "local");
  const outlookCalendar = data.outlook_calendar || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const outlookMail = data.outlook_mail || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const windows = { "5h": "per 5 hours", "day": "per day", "week": "per week", "month": "per month" };
  const devicesOpen = $(".device-manager")?.open || false;
  const outlookCalendarAccessOpen = $("#outlook-calendar-access")?.open || false;
  const outlookMailAccessOpen = $("#outlook-mail-access")?.open || false;
  const googleMailAccessOpen = $("#google-mail-access")?.open || false;
  const googleOAuthSetupOpen = $("#google-oauth-setup")?.open ?? !googleOAuthClient.configured;
  const googleCalendarAccountsHtml = (googleCalendar.accounts || []).map(account => {
    const grants = (googleCalendar.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can read ${esc(grant.calendar_name)} · ${esc(account.label)}</p></div>
        <button class="btn ghost small" type="button" data-google-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")
      : '<p class="hint">No Bot has access to this account.</p>';
    return `<article class="google-calendar-account" data-google-calendar-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Read-only calendar-list and event scopes · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-google-calendar-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Bots with calendar access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-google-calendar-grant-form="${esc(account.id)}">
        <label class="field">Grant one calendar to a Bot
          <select data-google-calendar-bot ${bots.length ? "" : "disabled"} aria-label="Bot for Google Calendar access">
            ${bots.length ? bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create a Bot first</option>'}
          </select>
        </label>
        <button class="btn ghost small" type="button" data-google-calendar-load-calendars="${esc(account.id)}" ${bots.length ? "" : "disabled"}>Load calendars</button>
        <label class="field" hidden data-google-calendar-calendar-field>Calendar
          <select data-google-calendar-calendar aria-label="Calendar to grant" disabled><option value="">Choose a calendar…</option></select>
        </label>
        <button class="btn primary small" type="button" data-google-calendar-grant="${esc(account.id)}" disabled>Grant read access</button>
        <p class="hint" role="status" aria-live="polite" data-google-calendar-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanCalendarGrants = (googleCalendar.grants || []).filter(grant =>
    !(googleCalendar.accounts || []).some(account => account.id === grant.account_id));
  const googleMailAccountsHtml = (googleMail.accounts || []).map(account => {
    const grants = (googleMail.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can search sender, subject, date and short previews · ${esc(account.label)}</p></div>
        <button class="btn ghost small" type="button" data-google-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")
      : '<p class="hint">No Bot has access to this account.</p>';
    return `<article class="google-calendar-account" data-google-mail-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Restricted <code>gmail.readonly</code> access · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-google-mail-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Bots with Gmail access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-google-mail-grant-form="${esc(account.id)}">
        <label class="field">Grant this mailbox to one Local-inference Bot
          <select data-google-mail-bot ${googleMailBots.length ? "" : "disabled"} aria-label="Local-inference Bot for Gmail access">
            ${googleMailBots.length ? googleMailBots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create or switch a Bot to Local inference</option>'}
          </select>
        </label>
        <button class="btn primary small" type="button" data-google-mail-grant="${esc(account.id)}" ${googleMailBots.length ? "" : "disabled"}>Grant search access</button>
        <p class="hint">Before saving, Hutch verifies that the built-in Bot's primary, fallback and escalation models all use loopback endpoints. Hosted fallback and remote custom endpoints are refused.</p>
        <p class="hint" role="status" aria-live="polite" data-google-mail-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanGoogleMailGrants = (googleMail.grants || []).filter(grant =>
    !(googleMail.accounts || []).some(account => account.id === grant.account_id));
  const outlookCalendarAccountsHtml = (outlookCalendar.accounts || []).map(account => {
    const grants = (outlookCalendar.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can read ${esc(grant.calendar_name)} · ${esc(account.label)}</p></div>
        <button class="btn ghost small" type="button" data-outlook-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")
      : '<p class="hint">No Bot has access to this account.</p>';
    return `<article class="google-calendar-account" data-outlook-calendar-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Delegated Calendars.ReadBasic · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-outlook-calendar-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Bots with Outlook Calendar access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-outlook-calendar-grant-form="${esc(account.id)}">
        <label class="field">Grant one calendar to a Bot
          <select data-outlook-calendar-bot ${bots.length ? "" : "disabled"} aria-label="Bot for Outlook Calendar access">
            ${bots.length ? bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create a Bot first</option>'}
          </select>
        </label>
        <button class="btn ghost small" type="button" data-outlook-calendar-load-calendars="${esc(account.id)}" ${bots.length ? "" : "disabled"}>Load calendars</button>
        <label class="field" hidden data-outlook-calendar-calendar-field>Calendar
          <select data-outlook-calendar-calendar aria-label="Outlook calendar to grant" disabled><option value="">Choose a calendar…</option></select>
        </label>
        <button class="btn primary small" type="button" data-outlook-calendar-grant="${esc(account.id)}" disabled>Grant read access</button>
        <p class="hint" role="status" aria-live="polite" data-outlook-calendar-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanOutlookGrants = (outlookCalendar.grants || []).filter(grant =>
    !(outlookCalendar.accounts || []).some(account => account.id === grant.account_id));
  const outlookMailAccountsHtml = (outlookMail.accounts || []).map(account => {
    const grants = (outlookMail.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can search message previews · ${esc(account.label)}</p></div>
        <button class="btn ghost small" type="button" data-outlook-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")
      : '<p class="hint">No Bot has access to this account.</p>';
    return `<article class="google-calendar-account" data-outlook-mail-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Delegated Mail.Read · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-outlook-mail-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Bots with Outlook Mail access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-outlook-mail-grant-form="${esc(account.id)}">
        <label class="field">Grant this mailbox to one Bot
          <select data-outlook-mail-bot ${bots.length ? "" : "disabled"} aria-label="Bot for Outlook Mail access">
            ${bots.length ? bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create a Bot first</option>'}
          </select>
        </label>
        <button class="btn primary small" type="button" data-outlook-mail-grant="${esc(account.id)}" ${bots.length ? "" : "disabled"}>Grant read access</button>
        <p class="hint" role="status" aria-live="polite" data-outlook-mail-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanOutlookMailGrants = (outlookMail.grants || []).filter(grant =>
    !(outlookMail.accounts || []).some(account => account.id === grant.account_id));
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
      <section class="panel conn-card google-calendar-card" aria-labelledby="google-calendar-title">
        <div class="bot-head"><span class="bot-name" id="google-calendar-title">Google Calendar</span>
          <span class="tag">read only</span><span class="tag">local desktop sign in</span></div>
        <p class="hint">Connect with Google's official installed-app flow. Hutch can list calendars and read events only. Grant one calendar to one Bot; matching event titles, times and locations go to that Bot's selected model and remain in its run history. Descriptions and attendee details are not included.</p>
        <p class="hint"><strong>Google permission:</strong> Google's OAuth grant is read-only at the account level; Hutch exposes only the calendar you select to each Bot. Calendar content is untrusted and cannot approve actions.</p>
        <details class="google-oauth-setup" id="google-oauth-setup" ${googleOAuthSetupOpen ? "open" : ""}>
          <summary>Google account setup <span class="chip ${googleOAuthClient.configured ? "ok" : "warn"}">${googleOAuthClient.configured ? "client ready" : "setup needed"}</span></summary>
          <div class="google-oauth-setup-body">
            <p class="hint">Use a Google Cloud OAuth client of type <strong>Desktop app</strong>. Enable the Calendar API or Gmail API for each service you plan to use, then enter its public client ID. Never paste a client secret or access token.</p>
            <label class="field" for="google-oauth-client-id">Google Desktop OAuth client ID
              <input id="google-oauth-client-id" type="text" maxlength="512" autocomplete="off" spellcheck="false"
                value="${esc(googleOAuthClient.client_id || "")}" placeholder="your-client-id.apps.googleusercontent.com"
                aria-describedby="google-oauth-client-help" ${googleOAuthClient.editable ? "" : "readonly"}>
            </label>
            <div class="google-oauth-setup-actions">
              <button class="btn primary small" id="google-oauth-client-save" type="button" ${googleOAuthClient.editable ? "" : "disabled"}>Save client ID</button>
              <button class="btn ghost small" id="google-oauth-client-clear" type="button" ${googleOAuthClient.editable && googleOAuthClient.source === "hutch" ? "" : "disabled"}>Clear</button>
              <span class="hint">${googleOAuthClient.source === "environment" ? "Managed by the Hutch operator; change the environment setting and restart to update it." : googleOAuthClient.source === "hutch" ? "Saved on this Hutch only." : "Not saved yet."}</span>
            </div>
            <p class="hint" id="google-oauth-client-help">This one client ID is shared by Calendar and the separate Gmail preview. Gmail test-user and restricted-scope requirements are described below.</p>
            <p class="hint" role="status" aria-live="polite" tabindex="-1" id="google-oauth-client-status">${esc(googleOAuthClient.detail || "")}</p>
          </div>
        </details>
        ${!googleCalendar.configured ? '<p class="hint" role="status">Add a valid Google Desktop OAuth client ID above and enable the Calendar API in Google Cloud to connect a calendar.</p>' : ''}
        ${googleCalendar.configured && !googleCalendar.secret_store_available ? '<p class="hint" role="alert">Unavailable because Linux Secret Service is missing. Install and unlock <code>secret-tool</code> before connecting an account. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
        <div class="google-calendar-connect">
          <label class="field" for="google-calendar-label">Account label
            <input id="google-calendar-label" type="text" maxlength="80" autocomplete="off" placeholder="Personal or Work" aria-describedby="google-calendar-label-help">
          </label>
          <button class="btn primary small" id="google-calendar-connect" type="button" ${!googleCalendar.configured || !googleCalendar.secret_store_available ? "disabled" : ""}>Connect Google Calendar</button>
          <p class="hint" id="google-calendar-label-help">This label stays on this Hutch. Sign-in must start on the Hutch host at <code>127.0.0.1</code>; pair the phone after connecting here.</p>
        </div>
        ${googleCalendarAccountsHtml || '<p class="hint">No Google Calendar accounts connected.</p>'}
        ${orphanCalendarGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanCalendarGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">${esc(grant.calendar_name)}</p></div><button class="btn ghost small" data-google-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
      </section>
      <section class="panel conn-card outlook-calendar-card" aria-labelledby="google-mail-title">
        <div class="bot-head"><span class="bot-name" id="google-mail-title">Gmail</span>
          <span class="tag">experimental</span><span class="tag">Local inference only</span></div>
        <p class="hint">Search a connected mailbox for up to 10 matches. Hutch returns only sender, subject, received date and a short preview, which becomes untrusted local run history. It cannot send, edit, forward, delete or fetch attachments. Only built-in Bots with loopback Local model routes and no hosted fallbacks can receive Gmail access; Hutch cannot verify what the operator's local model service does.</p>
        <p class="hint"><strong>Google permission:</strong> <code>gmail.readonly</code> is a restricted, account-wide scope. Each Bot grant is enforced by Hutch, but Google consent is broader and remains managed in your Google Account. Public distribution requires Google's restricted-scope verification; server-side access can also require a security assessment. This private-preview integration is not approved for public release.</p>
        <p class="hint"><a href="https://developers.google.com/workspace/gmail/api/auth/scopes" target="_blank" rel="noopener noreferrer">Review Google's Gmail scope requirements</a> · <a href="https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification" target="_blank" rel="noopener noreferrer">Review restricted-scope verification</a>.</p>
        <details class="outlook-calendar-details" id="google-mail-access" ${googleMailAccessOpen ? "open" : ""}>
          <summary>Manage Gmail access</summary>
          ${!googleMail.configured ? '<p class="hint" role="status">Add a valid Google Desktop OAuth client ID in the shared setup above. <button class="inline-link" type="button" data-google-oauth-setup-link>Open Google setup</button> Gmail asks for restricted <code>gmail.readonly</code> consent, separately from Calendar.</p>' : ''}
          ${googleMail.configured && !googleMail.secret_store_available ? '<p class="hint" role="alert">Unavailable because Linux Secret Service is missing. Install and unlock <code>secret-tool</code> before connecting. Refresh tokens stay outside SQLite and browser storage.</p>' : ''}
          ${googleMail.configured && googleMail.secret_store_available ? `<div class="google-calendar-connect outlook-calendar-connect">
            <label class="field" for="google-mail-label">Account label
              <input id="google-mail-label" type="text" maxlength="80" autocomplete="off" placeholder="Personal or Work" aria-describedby="google-mail-label-help">
            </label>
            <button class="btn primary small" id="google-mail-connect" type="button">Connect Gmail</button>
            <p class="hint" id="google-mail-label-help">Sign in from this Hutch host at <code>127.0.0.1</code>. A project in Testing is limited to 100 listed users, and test-user refresh tokens expire after seven days. Google's restricted-scope review rules still apply.</p>
          </div>` : ''}
          ${googleMailAccountsHtml || '<p class="hint">No Gmail accounts connected.</p>'}
          ${orphanGoogleMailGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A Bot grant refers to a disconnected Gmail account. Revoke it before reconnecting.</p>${orphanGoogleMailGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Gmail search access</p></div><button class="btn ghost small" data-google-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ''}
        </details>
      </section>
      <section class="panel conn-card outlook-calendar-card" aria-labelledby="outlook-calendar-title">
        <div class="bot-head"><span class="bot-name" id="outlook-calendar-title">Outlook Calendar</span>
          <span class="tag">experimental</span><span class="tag">read only</span></div>
        <p class="hint">Connect a Microsoft account through its official local sign-in flow. Hutch uses delegated <code>Calendars.ReadBasic</code>; it cannot read event bodies, attachments or extensions. Grant one selected calendar to one Bot. Matching titles, times and locations go to that Bot's selected model and remain in its run history.</p>
        <p class="hint"><strong>Permission boundary:</strong> Microsoft consent applies to the signed-in account. Hutch enforces each Bot's selected-calendar grant locally, and calendar text stays untrusted. Disconnect clears Hutch's refresh credential and Bot grants; Microsoft consent must be revoked separately in your account or organisation settings.</p>
        <details class="outlook-calendar-details" id="outlook-calendar-access">
          <summary>Manage Outlook Calendar access</summary>
          ${!outlookCalendar.configured ? '<p class="hint" role="status">Unavailable until the Hutch operator configures <code>HUTCH_OUTLOOK_OAUTH_CLIENT_ID</code> for a Microsoft public-client application registration.</p>' : ''}
          ${outlookCalendar.configured && !outlookCalendar.secret_store_available ? '<p class="hint" role="alert">Unavailable because Linux Secret Service is missing. Install and unlock <code>secret-tool</code> before connecting an account. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
          <div class="google-calendar-connect outlook-calendar-connect">
            <label class="field" for="outlook-calendar-label">Account label
              <input id="outlook-calendar-label" type="text" maxlength="80" autocomplete="off" placeholder="Work or Personal" aria-describedby="outlook-calendar-label-help">
            </label>
            <button class="btn primary small" id="outlook-calendar-connect" type="button" ${!outlookCalendar.configured || !outlookCalendar.secret_store_available ? "disabled" : ""}>Connect Outlook Calendar</button>
            <p class="hint" id="outlook-calendar-label-help">Choose supported account types in the Microsoft registration for the accounts you want (organization, personal, or both); the <code>common</code> authority cannot expand that choice. Add <code>http://localhost/api/v1/connections/outlook-calendar/callback</code> under Mobile and desktop application redirects. Sign in from this Hutch host.</p>
          </div>
          ${outlookCalendarAccountsHtml || '<p class="hint">No Outlook Calendar accounts connected.</p>'}
          ${orphanOutlookGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">${esc(grant.calendar_name)}</p></div><button class="btn ghost small" data-outlook-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
        </details>
      </section>
      <section class="panel conn-card outlook-calendar-card outlook-mail-card" aria-labelledby="outlook-mail-title">
        <div class="bot-head"><span class="bot-name" id="outlook-mail-title">Outlook Mail</span>
          <span class="tag">experimental</span><span class="tag">read only</span></div>
        <p class="hint">Search across a connected mailbox, including Deleted Items and Clutter. Hutch returns sender, subject, received time and a short, untrusted preview for up to 10 matches. Grant one mailbox to a Bot from here.</p>
        <p class="hint"><strong>Permission boundary:</strong> Microsoft's delegated <code>Mail.Read</code> consent applies to the signed-in account; Hutch enables the search tool only for the Bot you grant. Matching previews are sent to that Bot's selected model and kept in its run history. Hutch cannot send, edit, delete or forward email, and cannot read attachments. Local disconnect clears Hutch's credential and grants; provider consent must be revoked separately.</p>
        ${!outlookMail.configured ? '<p class="hint" role="status">Unavailable until the Hutch operator configures <code>HUTCH_OUTLOOK_OAUTH_CLIENT_ID</code> for a Microsoft public-client application registration.</p>' : ''}
        ${outlookMail.configured && !outlookMail.secret_store_available ? '<p class="hint" role="alert">Unavailable because Linux Secret Service is missing. Install and unlock <code>secret-tool</code> before connecting an account. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
        <details class="outlook-calendar-details" id="outlook-mail-access">
          <summary>Manage Outlook Mail access</summary>
          <div class="google-calendar-connect outlook-calendar-connect">
            <label class="field" for="outlook-mail-label">Account label
              <input id="outlook-mail-label" type="text" maxlength="80" autocomplete="off" placeholder="Work or Personal" aria-describedby="outlook-mail-label-help">
            </label>
            <button class="btn primary small" id="outlook-mail-connect" type="button" ${!outlookMail.configured || !outlookMail.secret_store_available ? "disabled" : ""}>Connect Outlook Mail</button>
            <p class="hint" id="outlook-mail-label-help">Use a Microsoft registration that supports the accounts you want. Add <code>http://localhost/api/v1/connections/outlook-mail/callback</code> under Mobile and desktop application redirects. Mail consent is separate from calendar consent.</p>
          </div>
          ${outlookMailAccountsHtml || '<p class="hint">No Outlook Mail accounts connected.</p>'}
          ${orphanOutlookMailGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookMailGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Outlook Mail access</p></div><button class="btn ghost small" data-outlook-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
        </details>
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
          ${c.get_key_url && c.template === "opencode-go" ? `<p class="hint"><a href="${esc(c.get_key_url)}" target="_blank" rel="noopener noreferrer">Get an OpenCode Go API key</a>. Sign in to Go, subscribe if needed, copy its provider-issued key, and paste it here. This is key-based access; Hutch does not read OpenCode's private auth file or browser session.</p>` : ""}
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
      <section class="panel conn-card model-capability-card" aria-labelledby="model-capabilities-title">
        <div class="bot-head"><span class="bot-name" id="model-capabilities-title">Model tool-call observations</span>
          <span class="tag">observed evidence</span></div>
        <p class="hint">Hutch records a tool-call observation only after a normal, owned Bot run receives a declared tool call with valid arguments and its usage reservation is settled or retained for reconciliation. Each record applies to that exact connection, account, model and route revision. It is evidence from one past response, not a guarantee about the next run.</p>
        <div id="model-capability-results"><p class="hint" role="status">Loading model tool-call observations…</p></div>
      </section>
  </div></div>`;
  $(".device-manager").open = devicesOpen;
  $("#outlook-calendar-access").open = outlookCalendarAccessOpen;
  $("#outlook-mail-access").open = outlookMailAccessOpen;
  $("#google-mail-access").open = googleMailAccessOpen;

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

  const saveGoogleOAuthClient = async () => {
    const input = $("#google-oauth-client-id");
    const status = $("#google-oauth-client-status");
    const button = $("#google-oauth-client-save");
    const clientId = input?.value.trim() || "";
    if (!clientId) {
      status.textContent = "Enter a Google Desktop OAuth client ID.";
      input?.focus();
      return;
    }
    const hasConnectedAccounts = (googleCalendar.accounts || []).length + (googleMail.accounts || []).length > 0;
    if (hasConnectedAccounts && clientId !== googleOAuthClient.client_id && !(await confirmDialog({
      title: "Change Google OAuth client",
      body: "Existing Google accounts stay on this Hutch, but Google may require you to disconnect and sign in again with the new client ID.",
      confirmText: "Save new ID",
    }))) return;
    button.disabled = true;
    status.textContent = "Saving the Google client ID on this Hutch…";
    try {
      await api("/v1/connections/google-oauth-client", { method: "PUT", body: { client_id: clientId } });
      toast("Google OAuth client ID saved on this Hutch.");
      await renderConnections();
      $("#google-oauth-client-status")?.focus({ preventScroll: true });
    } catch (err) {
      status.textContent = err.message;
      button.disabled = false;
    }
  };
  $("#google-oauth-client-save")?.addEventListener("click", saveGoogleOAuthClient);
  $("#google-oauth-client-id")?.addEventListener("keydown", event => {
    if (event.key === "Enter" && !$("#google-oauth-client-save")?.disabled) {
      event.preventDefault();
      saveGoogleOAuthClient();
    }
  });
  $("#google-oauth-client-clear")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const status = $("#google-oauth-client-status");
    const hasConnectedAccounts = (googleCalendar.accounts || []).length + (googleMail.accounts || []).length > 0;
    const body = hasConnectedAccounts
      ? "This clears Hutch's saved client ID. Connected account records remain, but sign-in and token refresh may stop until you save the same or a compatible client ID again. Disconnect accounts first if you want them removed."
      : "This removes the Google client ID saved on this Hutch.";
    if (!(await confirmDialog({ title: "Clear Google OAuth client", body, confirmText: "Clear client ID", danger: true }))) return;
    button.disabled = true;
    status.textContent = "Clearing the saved Google client ID…";
    try {
      await api("/v1/connections/google-oauth-client", { method: "DELETE" });
      toast("Google OAuth client ID cleared.");
      await renderConnections();
      $("#google-oauth-client-status")?.focus({ preventScroll: true });
    } catch (err) {
      status.textContent = err.message;
      button.disabled = false;
    }
  });
  $("[data-google-oauth-setup-link]")?.addEventListener("click", () => {
    const setup = $("#google-oauth-setup");
    if (!setup) return;
    setup.open = true;
    setup.scrollIntoView({ behavior: "auto", block: "center" });
    $("#google-oauth-client-id")?.focus({ preventScroll: true });
  });

  $("#google-calendar-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#google-calendar-label")?.value.trim();
    if (!label) { toast("Enter a label for this Google Calendar account.", true); $("#google-calendar-label")?.focus(); return; }
    // Google installed-app OAuth must run in a browser context, not inside a
    // form submit or embedded credential field. Open synchronously during the
    // click gesture, sever its opener, then navigate only after Hutch returns
    // the fixed Google authorization endpoint.
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Google sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.textContent = "Opening Google…";
    try {
      const result = await api("/v1/connections/google-calendar/sign-in", { method: "POST", body: { label } });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Google sign-in destination."); }
      if (authUrl.origin !== "https://accounts.google.com" || authUrl.pathname !== "/o/oauth2/v2/auth" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Google sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      button.textContent = "Connect Google Calendar";
      toast("Finish Google sign-in in the new browser tab, then reload Connections here.");
    } catch (err) {
      authWindow.close();
      button.disabled = false;
      button.textContent = "Connect Google Calendar";
      toast(err.message, true);
    }
    button.disabled = false;
  });
  $$('[data-google-calendar-load-calendars]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-google-calendar-grant-form]");
      const status = $("[data-google-calendar-status]", form);
      const calendarField = $("[data-google-calendar-calendar-field]", form);
      const calendarSelect = $("[data-google-calendar-calendar]", form);
      const grantButton = $("[data-google-calendar-grant]", form);
      button.disabled = true;
      button.textContent = "Loading…";
      status.textContent = "Loading calendars from Google…";
      try {
        const result = await api(`/v1/connections/google-calendar/calendars?account_id=${encodeURIComponent(button.dataset.googleCalendarLoadCalendars)}`);
        const rows = result.calendars || [];
        calendarSelect.innerHTML = `<option value="">Choose a calendar…</option>${rows.map(calendar => `<option value="${esc(calendar.id)}">${esc(calendar.name)}${calendar.primary ? " · primary" : ""}</option>`).join("")}`;
        calendarField.hidden = false;
        calendarSelect.disabled = false;
        grantButton.disabled = true;
        status.textContent = rows.length ? `${rows.length} calendar${rows.length === 1 ? "" : "s"} loaded. Select one to continue.` : "Google returned no calendars for this account.";
        calendarSelect.focus();
      } catch (err) { status.textContent = err.message; }
      finally { button.disabled = false; button.textContent = "Load calendars"; }
    });
  });
  $$('[data-google-calendar-grant-form] [data-google-calendar-calendar]').forEach(select => {
    select.addEventListener("change", () => {
      const form = select.closest("[data-google-calendar-grant-form]");
      $("[data-google-calendar-grant]", form).disabled = !select.value;
    });
  });
  $$('[data-google-calendar-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-google-calendar-grant-form]");
      const bot = $("[data-google-calendar-bot]", form).value;
      const calendar = $("[data-google-calendar-calendar]", form).value;
      const status = $("[data-google-calendar-status]", form);
      const existing = (googleCalendar.grants || []).find(grant => grant.bot_id === bot);
      if (existing && !(await confirmDialog({ title: "Replace calendar access", body: `<b>${esc(grantedBotLabel(existing))}</b> already has access to <b>${esc(existing.calendar_name)}</b>. Replace that grant with the selected calendar?`, confirmText: "Replace grant" }))) return;
      button.disabled = true;
      status.textContent = "Verifying the selected calendar with Google…";
      try {
        const result = await api("/v1/connections/google-calendar/grants", { method: "POST", body: {
          bot, account_id: button.dataset.googleCalendarGrant, calendar_id: calendar } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-google-calendar-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (googleCalendar.grants || []).find(row => row.bot_id === button.dataset.googleCalendarUngrant);
      if (!(await confirmDialog({ title: "Revoke Bot calendar access", body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from reading the granted Google Calendar?`, confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/google-calendar/grants/${encodeURIComponent(button.dataset.googleCalendarUngrant)}`, { method: "DELETE" });
        toast("Bot calendar access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-google-calendar-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (googleCalendar.accounts || []).find(row => row.id === button.dataset.googleCalendarDisconnect);
      const botNames = (googleCalendar.grants || []).filter(row => row.account_id === account?.id).map(grantedBotLabel);
      const detail = botNames.length ? `<p>This also revokes access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Google Calendar", body: `Clear the local refresh credential and request Google revocation?${detail}`, confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/google-calendar/accounts/${encodeURIComponent(button.dataset.googleCalendarDisconnect)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail, result.provider_revocation !== "confirmed");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });

  $("#google-mail-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#google-mail-label")?.value.trim();
    if (!label) { toast("Enter a label for this Gmail account.", true); $("#google-mail-label")?.focus(); return; }
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Google sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.textContent = "Opening Google…";
    try {
      const result = await api("/v1/connections/google-mail/sign-in", { method: "POST", body: { label } });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Google sign-in destination."); }
      if (authUrl.origin !== "https://accounts.google.com" || authUrl.pathname !== "/o/oauth2/v2/auth" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Google sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      toast("Finish Google sign-in in the new browser tab, then reload Connections here.");
    } catch (err) {
      authWindow.close();
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Connect Gmail";
    }
  });
  $$('[data-google-mail-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-google-mail-grant-form]");
      const bot = $("[data-google-mail-bot]", form).value;
      const status = $("[data-google-mail-status]", form);
      const existing = (googleMail.grants || []).find(grant => grant.bot_id === bot);
      if (existing && existing.account_id !== button.dataset.googleMailGrant && !(await confirmDialog({
        title: "Replace Gmail access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has a grant to another mailbox. Replace it with this Gmail account?`,
        confirmText: "Replace grant",
      }))) return;
      button.disabled = true;
      status.textContent = "Saving this Bot's local-only Gmail grant…";
      try {
        const result = await api("/v1/connections/google-mail/grants", { method: "POST", body: {
          bot, account_id: button.dataset.googleMailGrant } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-google-mail-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (googleMail.grants || []).find(row => row.bot_id === button.dataset.googleMailUngrant);
      if (!(await confirmDialog({ title: "Revoke Bot Gmail access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from searching the granted Gmail mailbox?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/google-mail/grants/${encodeURIComponent(button.dataset.googleMailUngrant)}`, { method: "DELETE" });
        toast("Bot Gmail access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-google-mail-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (googleMail.accounts || []).find(row => row.id === button.dataset.googleMailDisconnect);
      const botNames = (googleMail.grants || []).filter(row => row.account_id === account?.id).map(grantedBotLabel);
      const grants = botNames.length ? `<p>This also removes Hutch Gmail access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Gmail",
        body: `Clear Hutch's local refresh credential for <b>${esc(account?.label || "this account")}</b> and request Google's token revocation?${grants} Google consent is account-wide; check your Google Account if remote revocation is not confirmed.`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/google-mail/accounts/${encodeURIComponent(button.dataset.googleMailDisconnect)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail, result.provider_revocation === "not_confirmed");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });

  $("#outlook-calendar-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-calendar-label")?.value.trim();
    if (!label) { toast("Enter a label for this Outlook Calendar account.", true); $("#outlook-calendar-label")?.focus(); return; }
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.textContent = "Opening Microsoft…";
    try {
      const result = await api("/v1/connections/outlook-calendar/sign-in", { method: "POST", body: { label } });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Microsoft sign-in destination."); }
      if (authUrl.origin !== "https://login.microsoftonline.com" ||
          authUrl.pathname !== "/common/oauth2/v2.0/authorize" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Microsoft sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      toast("Finish Microsoft sign-in in the new browser tab, then reload Connections here.");
    } catch (err) {
      authWindow.close();
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Connect Outlook Calendar";
    }
  });
  $$('[data-outlook-calendar-load-calendars]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-calendar-grant-form]");
      const status = $("[data-outlook-calendar-status]", form);
      const calendarField = $("[data-outlook-calendar-calendar-field]", form);
      const calendarSelect = $("[data-outlook-calendar-calendar]", form);
      const grantButton = $("[data-outlook-calendar-grant]", form);
      button.disabled = true;
      button.textContent = "Loading…";
      status.textContent = "Loading calendars from Microsoft…";
      try {
        const result = await api(`/v1/connections/outlook-calendar/calendars?account_id=${encodeURIComponent(button.dataset.outlookCalendarLoadCalendars)}`);
        const rows = result.calendars || [];
        calendarSelect.innerHTML = `<option value="">Choose a calendar…</option>${rows.map(calendar => `<option value="${esc(calendar.id)}">${esc(calendar.name)}${calendar.primary ? " · default" : ""}</option>`).join("")}`;
        calendarField.hidden = false;
        calendarSelect.disabled = false;
        grantButton.disabled = true;
        status.textContent = rows.length ? `${rows.length} calendar${rows.length === 1 ? "" : "s"} loaded. Select one to continue.` : "Microsoft returned no calendars for this account.";
        calendarSelect.focus();
      } catch (err) { status.textContent = err.message; }
      finally { button.disabled = false; button.textContent = "Load calendars"; }
    });
  });
  $$('[data-outlook-calendar-grant-form] [data-outlook-calendar-calendar]').forEach(select => {
    select.addEventListener("change", () => {
      const form = select.closest("[data-outlook-calendar-grant-form]");
      $("[data-outlook-calendar-grant]", form).disabled = !select.value;
    });
  });
  $$('[data-outlook-calendar-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-calendar-grant-form]");
      const bot = $("[data-outlook-calendar-bot]", form).value;
      const calendar = $("[data-outlook-calendar-calendar]", form).value;
      const status = $("[data-outlook-calendar-status]", form);
      const existing = (outlookCalendar.grants || []).find(grant => grant.bot_id === bot);
      if (existing && !(await confirmDialog({
        title: "Replace calendar access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has access to <b>${esc(existing.calendar_name)}</b>. Replace that grant with the selected Outlook calendar?`,
        confirmText: "Replace grant",
      }))) return;
      button.disabled = true;
      status.textContent = "Verifying the selected calendar with Microsoft…";
      try {
        const result = await api("/v1/connections/outlook-calendar/grants", { method: "POST", body: {
          bot, account_id: button.dataset.outlookCalendarGrant, calendar_id: calendar } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-outlook-calendar-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (outlookCalendar.grants || []).find(row => row.bot_id === button.dataset.outlookCalendarUngrant);
      if (!(await confirmDialog({ title: "Revoke Bot calendar access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from reading the granted Outlook Calendar?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/outlook-calendar/grants/${encodeURIComponent(button.dataset.outlookCalendarUngrant)}`, { method: "DELETE" });
        toast("Bot Outlook Calendar access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-outlook-calendar-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (outlookCalendar.accounts || []).find(row => row.id === button.dataset.outlookCalendarDisconnect);
      const botNames = (outlookCalendar.grants || []).filter(row => row.account_id === account?.id).map(grantedBotLabel);
      const grants = botNames.length ? `<p>This also removes Hutch calendar access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Outlook Calendar",
        body: `Clear Hutch's local refresh credential for <b>${esc(account?.label || "this account")}</b>? Microsoft consent is not revoked by Hutch; you must revoke it separately in your Microsoft account or organisation settings.${grants}`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/outlook-calendar/accounts/${encodeURIComponent(button.dataset.outlookCalendarDisconnect)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail);
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });

  $("#outlook-mail-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-mail-label")?.value.trim();
    if (!label) { toast("Enter a label for this Outlook Mail account.", true); $("#outlook-mail-label")?.focus(); return; }
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.textContent = "Opening Microsoft…";
    try {
      const result = await api("/v1/connections/outlook-mail/sign-in", { method: "POST", body: { label } });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Microsoft sign-in destination."); }
      if (authUrl.origin !== "https://login.microsoftonline.com" ||
          authUrl.pathname !== "/common/oauth2/v2.0/authorize" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Microsoft sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      toast("Finish Microsoft sign-in in the new browser tab, then reload Connections here.");
    } catch (err) {
      authWindow.close();
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Connect Outlook Mail";
    }
  });
  $$('[data-outlook-mail-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-mail-grant-form]");
      const bot = $("[data-outlook-mail-bot]", form).value;
      const status = $("[data-outlook-mail-status]", form);
      const existing = (outlookMail.grants || []).find(grant => grant.bot_id === bot);
      if (existing && existing.account_id !== button.dataset.outlookMailGrant && !(await confirmDialog({
        title: "Replace Outlook Mail access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has access to another mailbox. Replace that grant with this Outlook account?`,
        confirmText: "Replace grant",
      }))) return;
      button.disabled = true;
      status.textContent = "Saving this Bot's Outlook Mail grant…";
      try {
        const result = await api("/v1/connections/outlook-mail/grants", { method: "POST", body: {
          bot, account_id: button.dataset.outlookMailGrant } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-outlook-mail-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (outlookMail.grants || []).find(row => row.bot_id === button.dataset.outlookMailUngrant);
      if (!(await confirmDialog({ title: "Revoke Bot Outlook Mail access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from searching the granted Outlook mailbox?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/outlook-mail/grants/${encodeURIComponent(button.dataset.outlookMailUngrant)}`, { method: "DELETE" });
        toast("Bot Outlook Mail access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-outlook-mail-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (outlookMail.accounts || []).find(row => row.id === button.dataset.outlookMailDisconnect);
      const botNames = (outlookMail.grants || []).filter(row => row.account_id === account?.id).map(grantedBotLabel);
      const grants = botNames.length ? `<p>This also removes Hutch mail access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Outlook Mail",
        body: `Clear Hutch's local refresh credential for <b>${esc(account?.label || "this account")}</b>? Microsoft consent is not revoked by Hutch; revoke it separately in your Microsoft account or organisation settings.${grants}`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/outlook-mail/accounts/${encodeURIComponent(button.dataset.outlookMailDisconnect)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail);
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
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
  const modelCapabilityResult = await modelCapabilityRequest;
  const modelCapabilityResults = $("#model-capability-results");
  if (modelCapabilityResults?.isConnected) {
    modelCapabilityResults.innerHTML = modelCapabilityResultsMarkup(modelCapabilityResult.page, modelCapabilityResult.error);
  }
}

/* -------------------------------------------------------- guided bot setup */

const SETUP_TOOL_EXPANSIONS = { files: ["read_file", "list_files", "write_file"], memory: ["remember", "recall"] };
const BOT_SETUP_TOOLS = [
  ["read_file", "Read workspace files", "Open text files in this bot’s workspace."],
  ["list_files", "List workspace files", "See file names in this bot’s workspace."],
  ["write_file", "Write workspace files", "Create or replace workspace files; policy still applies."],
  ["shell", "Run shell commands", "Run commands within Hutch’s configured shell boundary."],
  ["web_fetch", "Fetch public pages", "Read public pages through Hutch’s checked network path."],
  ["browser", "Use an isolated browser", "Control this bot’s private browser profile."],
  ["remember", "Propose reference facts", "Suggest facts for review before they can be recalled."],
  ["recall", "Recall reviewed facts", "Search facts approved for this bot and conversation."],
  ["delegate_task", "Delegate a bounded task", "Request a separately approved child task."],
];

function suggestBotRoleName(purpose) {
  const text = (purpose || "").replace(/\s+/g, " ").trim()
    .replace(/^(?:(?:please|can you|could you|i want|i need|i'd like|i would like|set up|create)\s+)*(?:a\s+)?(?:new\s+)?(?:bot|agent|assistant)\s+(?:to|that|which)\s+/i, "");
  if (!text) return "";
  const patterns = [
    { re: /\b(?:prepare|prepares|write|writes|draft|drafts|compile|compiles|generate|generates|produce|produces|create|creates)\b(?=[^.!?]{0,80}\b(?:reports?|updates?|briefings?|summaries)\b)/i, role: "Reporter" },
    { re: /\b(?:monitor|watch|track|follow|flag|keep an eye on|keep up with)\b/i, role: "Monitor" },
    { re: /\b(?:review|audit|check|evaluate|inspect)\b/i, role: "Reviewer" },
    { re: /\b(?:research|investigate|find|compare|analy[sz]e)\b/i, role: "Analyst" },
    { re: /\b(?:organize|organise|sort|file|archive|categorize|categorise)\b/i, role: "Organizer" },
    { re: /\b(?:remind(?:\s+me)?|notify(?:\s+me)?|alert(?:\s+me)?|reminder)\b/i, role: "Reminder" },
    { re: /\b(?:plan|schedule|prepare)\b/i, role: "Planner" },
    { re: /\b(?:coordinate|manage)\b/i, role: "Coordinator" },
    { re: /\b(?:draft|write|compose)\b/i, role: "Writer" },
    { re: /\b(?:summari[sz]e|recap|brief)\b/i, role: "Briefing Assistant" },
    { re: /\b(?:answer|support|respond)\b/i, role: "Support Specialist" },
    { re: /\b(?:automate|handle)\b/i, role: "Operations Assistant" },
  ];
  let selected = null;
  for (const item of patterns) {
    const match = item.re.exec(text);
    if (match && (!selected || match.index < selected.match.index)) selected = { ...item, match };
  }
  if (!selected) return "Workspace Assistant";
  if (selected.role === "Coordinator" && /\b(?:bots?|agents?|specialists?)\b/i.test(text)) {
    return "Workspace Coordinator";
  }
  let subjectSource = text.slice(selected.match.index + selected.match[0].length);
  if (selected.role === "Reminder") subjectSource = subjectSource.replace(/^\s*(?:when|whenever|if|that)\s+/i, "");
  let subject = subjectSource
    .split(/[.;,:!?]|\b(?:and then|and|then|so that|when|whenever|if|unless|before|after|while|to notify|notify me|from|into|for)\b/i, 1)[0]
    .replace(/\bfollow[ -]+up\b/gi, "follow-up")
    .replace(/\btasks\b/gi, "task")
    .replace(/\breceipts\b/gi, "receipt")
    .replace(/^(?:\s|the\s+|my\s+|our\s+|a\s+|an\s+|me\s+|us\s+)+/i, "");
  let reminderAction = "";
  if (selected.role === "Reminder") {
    subject = subject.replace(/^\s*(?:to|about|for)\s+/i, "");
    const actions = { pay: "Payment", renew: "Renewal", submit: "Submission", file: "Filing",
      schedule: "Scheduling", book: "Booking", complete: "Completion", update: "Update",
      replace: "Replacement", return: "Return" };
    const action = /^(pay|renew|submit|file|schedule|book|complete|update|replace|return)\b/i.exec(subject);
    if (action) {
      reminderAction = actions[action[1].toLowerCase()];
      subject = subject.slice(action[0].length).replace(/^\s+(?:the|my|our|a|an)\s+/i, " ");
    }
  }
  const stop = new Set(["a", "about", "an", "and", "are", "as", "at", "be", "by", "changes", "each", "from", "in", "into", "is", "it", "of", "on", "or", "the", "this", "to", "with", "me", "my", "our", "us", "you", "your", "bot", "agent", "please", "daily", "weekly", "monthly", "quarterly", "affecting", "anything", "requests", "things", "whatever", "what", "work", "next", "today", "tomorrow", "tonight", "month", "week", "year", "due", "overdue", "late", "missing", "report", "reports", "update", "updates", "briefing", "briefings", "summary", "summaries"]);
  const acronyms = new Set(["ai", "api", "ci", "cd", "crm", "hr", "qa", "sre", "ui", "ux"]);
  const words = (subject.match(/[a-z0-9]+(?:-[a-z0-9]+)*/gi) || []).filter(word => !stop.has(word.toLowerCase())).slice(0, 3);
  const title = words.map(word => acronyms.has(word.toLowerCase()) ? word.toUpperCase()
    : word.split("-").map((part, index) => index === 0
      ? part[0].toUpperCase() + part.slice(1).toLowerCase() : part.toLowerCase()).join("-"));
  return (title.length ? [...title, ...(reminderAction ? [reminderAction] : []), ...selected.role.split(" ")]
    : ["Workspace", ...selected.role.split(" ")]).join(" ");
}

function suggestBotDisplayName(purpose, existingBots = botsCache) {
  const role = suggestBotRoleName(purpose);
  if (!role) return "";
  const givenNames = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Rowan", "Quinn",
    "Alex", "Jamie", "Cameron", "Sage", "Reese", "Drew", "Robin", "Sam"];
  const familyNames = ["Bennett", "Chen", "Clarke", "Ellis", "James", "Kim", "Lee", "Morgan",
    "Patel", "Reed", "Rivera", "Shah", "Singh", "Taylor", "Walker", "Wright"];
  const identities = givenNames.flatMap(given => familyNames.map(family => `${given} ${family}`));
  const occupied = new Set((existingBots || []).map(bot =>
    (bot.display_name || bot.name || "").trim().split(" · ", 1)[0].toLowerCase()));
  let seed = 0;
  for (const char of `${purpose || ""}`.toLowerCase()) seed = (Math.imul(seed, 31) + char.charCodeAt(0)) | 0;
  const start = (seed >>> 0) % identities.length;
  let identity = "";
  for (let offset = 0; offset < identities.length; offset++) {
    const candidate = identities[(start + offset) % identities.length];
    if (!occupied.has(candidate.toLowerCase())) { identity = candidate; break; }
  }
  if (!identity) identity = `${identities[start]} ${(existingBots || []).length + 1}`;
  return `${identity} · ${role}`;
}

function suggestedBotAddress(displayName) {
  const pieces = (displayName || "").split(" · ");
  const addressSource = pieces[pieces.length - 1];
  const normalized = addressSource.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 41).replace(/-+$/g, "");
  return normalized.length >= 2 ? normalized : "workspace-assistant";
}

function templateTools(template) {
  const result = new Set();
  for (const tool of template?.tools || []) {
    for (const expanded of (SETUP_TOOL_EXPANSIONS[tool] || [tool])) result.add(expanded);
  }
  return result;
}

async function promptNewBot(preselect = "", sourceMessageId = "", duplicateBot = null) {
  let templates;
  try { templates = await api("/bots/templates"); }
  catch (err) { toast(`Bot setup is unavailable: ${err.message}`, true); return; }
  let workspaceDefaults = { model: "", inference_mode: "hybrid", configured: false };
  try { workspaceDefaults = await api("/v1/preferences/model-defaults"); }
  catch (err) { toast(`Workspace model defaults could not be loaded; choose a route manually. ${err.message}`, true); }
  let conversationSource = null;
  if (!duplicateBot && currentConversationId && currentStudioBot && /^#\/chat(?:\/|$)/.test(location.hash || "#/chat")) {
    try {
      const conversationId = currentConversationId;
      const summary = await api(`/v1/conversations/${encodeURIComponent(conversationId)}?after=0&limit=1`);
      const after = Math.max(0, Number(summary.last_seq || 0) - 100);
      if (summary.last_seq) {
        const page = await api(`/v1/conversations/${encodeURIComponent(conversationId)}?after=${after}&limit=100`);
        const userMessages = (page.messages || []).filter(message => message.role === "user" && message.content?.trim());
        const latestRequest = userMessages.at(-1);
        const selectedRequest = sourceMessageId
          ? userMessages.find(message => message.id === sourceMessageId)
          : latestRequest;
        if (sourceMessageId && !selectedRequest) {
          toast("That request is no longer available in this chat window. Refresh the conversation and try again.", true);
          return;
        }
        if (selectedRequest && currentConversationId === conversationId) {
          const conversation = currentConversations.find(item => item.id === conversationId);
          const sourceBot = botsCache.find(item => item.name === currentStudioBot);
          conversationSource = {
            conversation_id: conversationId, message_id: selectedRequest.id,
            sequence: selectedRequest.seq, created_at: selectedRequest.created_at,
            original_request: selectedRequest.content, source_bot_name: currentStudioBot,
            source_bot_display_name: sourceBot ? botDisplayName(sourceBot) : currentStudioBot,
            source_bot_is_coordinator: !!sourceBot?.is_workspace_coordinator,
            source_bot_runtime: sourceBot?.runtime || "",
            source_bot_model: sourceBot?.model && !sourceBot.model.startsWith("mock/") ? sourceBot.model : "",
            is_latest_request: selectedRequest.id === latestRequest?.id,
            context_candidates: userMessages.filter(message => message.id !== selectedRequest.id
              && Number(message.seq) < Number(selectedRequest.seq)).slice(-8),
            model_suggestion: sourceBot?.model && !sourceBot.model.startsWith("mock/") ? sourceBot.model : "",
            inference_mode_suggestion: sourceBot?.model && !sourceBot.model.startsWith("mock/") ? sourceBot.inference_mode : "",
            conversation_title: conversation?.title || "Untitled conversation",
          };
        }
      }
    } catch { /* a source is optional; setup remains available without chat history */ }
  }
  let browserHandoffCapability = { status: "unavailable", reason: "The host has not confirmed local browser support." };
  try {
    const capabilities = await api("/v1/capabilities");
    browserHandoffCapability = capabilities.find(capability => capability.id === "browser_handoff") || browserHandoffCapability;
  } catch { /* host-dependent options remain unavailable unless verified */ }
  const browserHandoffReady = ["supported", "experimental"].includes(browserHandoffCapability.status);
  const browserHandoffHelp = browserHandoffReady
    ? "Experimental on this Linux desktop. A person enters passwords, passcodes and verification codes in the visible browser. Hutch never types them or accepts them in chat. This does not enable phone browser control."
    : `Unavailable on this host: ${browserHandoffCapability.reason} This does not enable phone browser control.`;
  const chosenTemplate = templates.find(item => item.name === preselect) || null;
  let modelSuggestion = duplicateBot?.model || conversationSource?.model_suggestion || workspaceDefaults.model || "";
  let modelSuggestionSource = duplicateBot ? "duplicate" : conversationSource?.model_suggestion ? "chat" : workspaceDefaults.model ? "workspace" : "";
  const draft = {
    step: 0, forceAdvanced: !!chosenTemplate || !!duplicateBot,
    purpose: duplicateBot?.instructions || conversationSource?.original_request || "",
    useConversationSource: !duplicateBot && !!conversationSource,
    selectedContextMessageIds: new Set(),
    template: chosenTemplate?.name || "", name: "",
    display_name: duplicateBot ? `${duplicateBot.display_name || duplicateBot.name} copy`.slice(0, 80) : "",
    description: duplicateBot?.description || "", model: modelSuggestion,
    purposeRefinement: null, purposeRefinementStatus: "",
    inference_mode: duplicateBot?.inference_mode || conversationSource?.inference_mode_suggestion || workspaceDefaults.inference_mode || "hybrid",
    workspace_mode: duplicateBot?.workspace_mode === "fresh" ? "fresh" : "managed",
    // A duplicate is a safe configuration starting point, not a copy of authority.
    tools: duplicateBot ? new Set() : templateTools(chosenTemplate), memory_enabled: false,
    local_browser_handoff: false,
    cron: "", timezone: "UTC", catch_up: "coalesce", schedule_prompt: "",
    limits: { max_steps: 24, timeout_seconds: 900, daily_token_cap: 200000,
      max_turn_tokens: 0, max_cost_usd: 0, daily_cost_cap_usd: 0, ...(duplicateBot?.limits || {}) },
  };
  draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
  let displayNameEdited = !!duplicateBot;
  let addressEdited = false;
  const occupiedAddresses = new Set(botsCache.map(bot => bot.name));
  const uniqueAddress = value => {
    const base = suggestedBotAddress(value);
    if (!occupiedAddresses.has(base)) return base;
    for (let suffix = 2; suffix < 10000; suffix++) {
      const ending = `-${suffix}`;
      const candidate = `${base.slice(0, 41 - ending.length).replace(/-+$/g, "")}${ending}`;
      if (!occupiedAddresses.has(candidate)) return candidate;
    }
    return base;
  };
  const refreshSuggestedIdentity = () => {
    if (!displayNameEdited) draft.display_name = suggestBotDisplayName(draft.purpose);
    if (!addressEdited) draft.name = uniqueAddress(draft.display_name);
  };
  refreshSuggestedIdentity();
  const refreshNamePreview = () => {
    const displayName = $("#setup-display_name");
    if (displayName && !displayNameEdited) displayName.value = draft.display_name;
    const address = $("#setup-name");
    if (address && !addressEdited) address.value = draft.name;
  };
  const selectedCreationContext = () => (conversationSource?.context_candidates || [])
    .filter(message => draft.selectedContextMessageIds.has(message.id));
  const currentPurposeDraftFingerprint = () => JSON.stringify({
    source_message_id: draft.useConversationSource ? conversationSource?.message_id || "" : "",
    purpose: draft.purpose, context: selectedCreationContext().map(message => message.id),
  });
  const markPurposeDraftFreshness = () => {
    const suggestion = draft.purposeRefinement;
    if (!suggestion) return;
    draft.purposeRefinementStatus = suggestion.sourceFingerprint === currentPurposeDraftFingerprint()
      ? "Draft ready. Review it before applying; no Bot configuration has changed."
      : "The purpose or selected context changed after this suggestion. Draft again before applying it.";
    const status = $("#setup-purpose-draft-status");
    if (status) status.textContent = draft.purposeRefinementStatus;
  };
  const purposeRefinementHtml = () => {
    if (!draft.purposeRefinement) return "";
    const suggestion = draft.purposeRefinement;
    return `<section class="setup-purpose-draft" aria-labelledby="setup-purpose-draft-title">
      <h4 id="setup-purpose-draft-title">Coordinator’s instruction draft</h4>
      ${suggestion ? `<p class="hint">Review and edit the suggestion. Your original request remains linked; nothing changes until you apply it.</p>
        <label class="field" for="setup-purpose-draft-text">Proposed standing instructions<textarea id="setup-purpose-draft-text" rows="7" maxlength="20000">${esc(suggestion.content)}</textarea></label>
        <p class="hint">Open questions are listed instead of guessed. To add an answer, update the purpose above and draft again; later chat messages are not sent.</p>
        <button type="button" class="btn small" id="setup-purpose-draft-use">Use this draft</button>` : ""}
    </section>`;
  };
  const instructionsForDraft = () => {
    const purpose = draft.purpose.trim();
    const selected = selectedCreationContext();
    if (!selected.length) return purpose;
    const context = selected.map(message => `User message ${message.seq}:\n${message.content}`).join("\n\n");
    return `${purpose}\n\nOwner-selected background context from this chat (not a permission or access grant):\n${context}`;
  };
  const setupConfiguration = () => ({
    name: draft.name.trim(), display_name: draft.display_name.trim(), template: draft.template || null,
    description: draft.description.trim() || draft.purpose.trim().split("\n")[0].slice(0, 240),
    instructions: instructionsForDraft(), model: draft.model.trim(), inference_mode: draft.inference_mode,
    workspace_mode: draft.workspace_mode, tools: [...draft.tools], approval_mode: "ask", risk_tier: "supervised",
    limits: draft.limits, memory_enabled: draft.memory_enabled,
    local_browser_handoff: draft.local_browser_handoff,
    cron: draft.cron.trim() || null, timezone: draft.timezone, catch_up: draft.catch_up,
    schedule_prompt: draft.schedule_prompt.trim(),
  });
  const applyImportedConfiguration = config => {
    draft.forceAdvanced = true;
    draft.purpose = config.instructions || "";
    draft.useConversationSource = false;
    draft.selectedContextMessageIds = new Set();
    draft.name = config.name;
    draft.display_name = config.display_name;
    draft.description = config.description || "";
    draft.template = config.template || "";
    draft.model = config.model || "";
    draft.inference_mode = config.inference_mode || "hybrid";
    draft.workspace_mode = config.workspace_mode || "managed";
    draft.tools = new Set(config.tools || []);
    draft.memory_enabled = !!config.memory_enabled;
    draft.limits = { ...draft.limits, ...(config.limits || {}) };
    draft.local_browser_handoff = !!config.local_browser_handoff;
    draft.cron = config.cron || "";
    draft.timezone = config.timezone || "UTC";
    draft.catch_up = config.catch_up || "coalesce";
    draft.schedule_prompt = config.schedule_prompt || "";
    draft.purposeRefinement = null;
    draft.purposeRefinementStatus = "";
    displayNameEdited = true;
    addressEdited = true;
    modelSuggestion = draft.model;
    modelSuggestionSource = "import";
    const addressInUse = occupiedAddresses.has(draft.name);
    draft.yamlImportExpanded = true;
    draft.yamlImportStatus = addressInUse
      ? "YAML validated. This Bot address is already in use; change it in Review or change the address before creating. Nothing has been saved."
      : "YAML validated and copied into this unsaved draft. Review each step; no Bot or run has been created.";
  };
  const refreshContextCount = () => {
    const node = $("#setup-context-count");
    if (!node) return;
    const count = selectedCreationContext().length;
    const characters = Array.from(instructionsForDraft()).length;
    node.textContent = `${count ? `${count} message${count === 1 ? "" : "s"} selected` : "No earlier messages selected"} · ${characters.toLocaleString()} / 20,000 saved-instruction characters`;
    node.setAttribute("aria-invalid", String(characters > 20000));
  };
  const stepTitles = ["Describe the work", "Set model and workspace", "Choose tools and schedule", "Review bot"];
  const selectedTemplate = () => templates.find(item => item.name === draft.template) || null;
  const setError = message => {
    const node = $("#bot-setup-error");
    if (node) { node.textContent = message; node.hidden = !message; }
  };
  const snapshotFields = () => {
    const purpose = $("#setup-purpose"); if (purpose) draft.purpose = purpose.value;
    const contextInputs = $$('[data-setup-context-message]');
    if (contextInputs.length) {
      draft.selectedContextMessageIds = new Set(contextInputs.filter(input => input.checked)
        .map(input => input.dataset.setupContextMessage));
    }
    for (const key of ["name", "display_name", "description", "model", "cron", "timezone", "schedule_prompt"]) {
      const field = $(`#setup-${key}`); if (field) draft[key] = field.value;
    }
    for (const key of ["inference_mode", "workspace_mode", "catch_up"]) {
      const field = $(`#setup-${key}`); if (field) draft[key] = field.value;
    }
    const handoff = $("#setup-local-browser-handoff");
    if (handoff) draft.local_browser_handoff = handoff.checked;
    for (const key of Object.keys(draft.limits)) {
      const field = $(`#setup-limit-${key}`);
      if (field) draft.limits[key] = ["max_cost_usd", "daily_cost_cap_usd"].includes(key)
        ? Number(field.value) : Number.parseInt(field.value, 10);
    }
    const tools = $("#setup-tools");
    if (tools) draft.tools = new Set($$("input[name=setup-tool]:checked", tools).map(input => input.value));
  };
  const displayTool = tool => BOT_SETUP_TOOLS.find(([name]) => name === tool)?.[1] || tool;
  const reviewHtml = () => {
    const template = selectedTemplate();
    const selectedContext = selectedCreationContext();
    const sourceReview = draft.useConversationSource && conversationSource
      ? `<div><dt>Request source</dt><dd>${esc(conversationSource.source_bot_name)} · ${esc(conversationSource.conversation_title)} · message ${conversationSource.sequence}
          <details class="setup-source-details"><summary>View original message</summary><blockquote class="setup-source-quote">${esc(conversationSource.original_request)}</blockquote></details></dd></div>`
      : `<div><dt>Request source</dt><dd>Written for this Bot draft</dd></div>`;
    const contextReview = selectedContext.length ? `<div><dt>Earlier chat context</dt><dd>
        <p class="hint">Selected text becomes part of the saved Bot instructions and may be sent to its model on future runs.</p>
        ${selectedContext.map(message => `<details class="setup-source-details"><summary>User message ${message.seq} · ${esc(conversationSource.conversation_title)}</summary><blockquote class="setup-source-quote">${esc(message.content)}</blockquote></details>`).join("")}
      </dd></div>`
      : conversationSource ? `<div><dt>Earlier chat context</dt><dd>None selected</dd></div>` : "";
    return `<div class="setup-review">
      <p class="setup-assistant">Here’s the setup you chose. Creating it saves the bot only; it will not start a run.</p>
      <dl class="setup-review-list">
        <div><dt>Display name</dt><dd>${esc(draft.display_name)}</dd></div>
        <div><dt>Bot address</dt><dd>${esc(draft.name)}</dd></div>
        <div><dt>Purpose</dt><dd>${esc(draft.purpose)}</dd></div>
        ${sourceReview}
        ${contextReview}
        <div><dt>Starting point</dt><dd>${duplicateBot ? `Setup based on ${esc(duplicateBot.display_name || duplicateBot.name)}` : esc(template?.tagline || "Blank bot")}</dd></div>
        <div><dt>Model route</dt><dd>${esc(draft.model)}</dd></div>
        <div><dt>Inference</dt><dd>${esc(draft.inference_mode)}</dd></div>
        <div><dt>Workspace</dt><dd>${esc(draft.workspace_mode)}</dd></div>
        <div><dt>Approval</dt><dd>Ask before actions that require approval</dd></div>
        <div><dt>Tools</dt><dd>${draft.tools.size ? [...draft.tools].map(displayTool).map(esc).join(", ") : "No tools enabled"}</dd></div>
        <div><dt>Browser handoff</dt><dd>${draft.local_browser_handoff ? "On · human can take over in the visible Linux browser" : "Off"}</dd></div>
        <div><dt>Execution limits</dt><dd>${draft.limits.max_steps} steps · ${draft.limits.timeout_seconds} seconds · ${draft.limits.daily_token_cap.toLocaleString()} estimated tokens per day</dd></div>
        <div><dt>Model limits</dt><dd>${draft.limits.max_turn_tokens ? `${draft.limits.max_turn_tokens.toLocaleString()} tokens per turn` : "Provider default tokens per turn"} · ${draft.limits.max_cost_usd ? `$${draft.limits.max_cost_usd.toFixed(2)} estimated per run` : "No per-run estimate limit"} · ${draft.limits.daily_cost_cap_usd ? `$${draft.limits.daily_cost_cap_usd.toFixed(2)} estimated per day` : "No daily estimate limit"}</dd></div>
        <div><dt>Recurring task</dt><dd>${draft.cron.trim() ? `${esc(draft.cron.trim())} · ${esc(draft.timezone)} · missed windows: ${draft.catch_up === "skip" ? "skip" : "run once"}${draft.schedule_prompt.trim() ? ` · ${esc(draft.schedule_prompt.trim())}` : ""}` : "None"}</dd></div>
        <div><dt>Memory</dt><dd>${draft.memory_enabled ? "Enabled for allowed memory tools" : "Disabled"}</dd></div>
      </dl>
      <details class="setup-schedule setup-yaml" id="setup-yaml-details">
        <summary>View or download YAML</summary>
        <p class="hint">The file contains these saved instructions and Bot settings. It never includes provider credentials, chat-source links, custom endpoint URLs, or local folder paths. If your instructions contain private context, that text will be in the file. Previewing does not create or change a Bot.</p>
        <div class="setup-yaml-actions">
          <button type="button" class="btn small" id="setup-yaml-build">Build YAML preview</button>
          <button type="button" class="btn ghost small" id="setup-yaml-download" disabled>Download YAML</button>
        </div>
        <p class="hint" id="setup-yaml-status" role="status" aria-live="polite"></p>
        <pre class="setup-yaml-preview" id="setup-yaml-preview" tabindex="0" aria-label="YAML Bot configuration preview" hidden></pre>
      </details>
      <p class="hint">Token and currency limits use estimates, not guaranteed provider billing caps. The purpose, selected context and selected configuration are saved; they do not add tools or access. Passwords and one-time codes must be entered directly by you in the visible browser, never in chat.</p>
    </div>`;
  };
  const renderStep = async () => {
    const step = draft.step;
    const back = step ? `<button type="button" class="btn ghost small setup-back" id="setup-back">${icon("arrow-left")} Back</button>` : "";
    let content = "";
    if (step === 0) content = `<div class="setup-conversation${draft.forceAdvanced ? "" : " setup-quick"}">
      ${duplicateBot ? `<p class="hint setup-duplicate-note">Starting from <b>${esc(duplicateBot.display_name || duplicateBot.name)}</b>. Instructions, model route, inference mode, workspace type and limits are copied. Tools, connected accounts, schedules, memory values, custom provider URLs, local folders, browser handoff and chat history are not copied. Review the new setup before saving.</p>` : ""}
      ${conversationSource ? `<label class="setup-context-source"><input id="setup-use-source" type="checkbox" ${draft.useConversationSource ? "checked" : ""}>
        <span><b>Use this request as the Bot’s instructions</b><small>From ${esc(conversationSource.source_bot_name)} · ${esc(conversationSource.conversation_title)} · message ${conversationSource.sequence}.</small><small class="setup-request-preview">${esc(truncate(conversationSource.original_request.replace(/\s+/g, " ").trim(), 220))}</small></span></label>
        ${!draft.forceAdvanced ? `<p class="hint setup-source-note">The request you already gave becomes the starting instructions. No need to enter it again.</p>` : `<p class="setup-assistant">Only this request and earlier user messages you select are included in this Bot draft. Assistant replies and other chats stay private; selected text cannot change tools, accounts or permissions.</p>`}`
        : ""}
      ${draft.forceAdvanced ? `<details class="setup-schedule setup-yaml-import" id="setup-yaml-import-details" ${draft.yamlImportExpanded ? "open" : ""}>
        <summary>Load a saved YAML setup</summary>
        <p class="hint">A validated file fills this unsaved draft. Review the name, model, tools, schedule, limits and permissions across all steps; only the separate <b>Create bot</b> action saves it.</p>
        <button type="button" class="btn small" id="setup-yaml-import-button">Choose YAML file</button>
        <input id="setup-yaml-file" type="file" accept=".yaml,.yml,application/yaml,text/yaml" hidden>
        <p class="hint" id="setup-yaml-import-status" role="status" aria-live="polite">${esc(draft.yamlImportStatus || "")}</p>
      </details>` : ""}
      ${(draft.forceAdvanced && conversationSource?.context_candidates || []).length ? `<details class="setup-schedule" id="setup-context-picker" ${draft.selectedContextMessageIds.size ? "open" : ""}>
        <summary>Add earlier user messages (optional)</summary>
        <p class="hint">Choose only messages that should become background in this Bot’s saved instructions. No assistant replies or other chats are included. Avoid passwords, codes and unrelated private details.</p>
        <p class="hint" id="setup-context-count" role="status" aria-live="polite"></p>
        <div class="setup-context-choices">${conversationSource.context_candidates.map(message => {
          const preview = message.content.length > 220 ? `${message.content.slice(0, 220)}…` : message.content;
          return `<article class="setup-context-choice">
            <label class="setup-choice"><input type="checkbox" data-setup-context-message="${esc(message.id)}" ${draft.selectedContextMessageIds.has(message.id) ? "checked" : ""}>
              <span><b>User message ${message.seq}</b><small>${esc(preview)}</small></span></label>
            <details class="setup-source-details"><summary>Read full message</summary><blockquote class="setup-source-quote">${esc(message.content)}</blockquote></details>
          </article>`;
        }).join("")}</div>
      </details>` : ""}
      ${conversationSource && draft.useConversationSource && !draft.forceAdvanced ? `<details class="setup-schedule setup-purpose-editor" id="setup-purpose-editor">
        <summary>Edit these instructions (optional)</summary>
        <label class="field" for="setup-purpose">Bot instructions<textarea id="setup-purpose" rows="4" maxlength="20000" required>${esc(draft.purpose)}</textarea>
          <span class="hint">By default, Hutch uses your selected request. Editing it is optional; no tools or account access are inferred.</span></label>
      </details>` : `<label class="field" for="setup-purpose">${conversationSource ? "What should this bot keep doing?" : "What would you like this bot to handle?"}<textarea id="setup-purpose" rows="${draft.forceAdvanced ? 5 : 3}" maxlength="20000" placeholder="For example: review release notes and prepare a short summary of changes that affect our project." required>${esc(draft.purpose)}</textarea>
        <span class="hint">This becomes the Bot’s standing instructions. Hutch does not add tools or account access.</span></label>`}
        ${draft.forceAdvanced && conversationSource?.source_bot_is_coordinator && conversationSource.source_bot_runtime === "builtin" && conversationSource.source_bot_model ? `<details class="setup-schedule setup-refine-details" id="setup-refine-details" ${draft.purposeRefinement || draft.purposeRefinementStatus ? "open" : ""}>
          <summary>Improve these instructions (optional)</summary>
          <div class="setup-refine-action">
            <button type="button" class="btn small" id="setup-refine-purpose">Draft clearer instructions with ${esc(conversationSource.source_bot_display_name)}</button>
            <p class="hint">This sends one request, purpose and only earlier messages you selected to ${esc(conversationSource.source_bot_display_name)}’s saved route (${esc(conversationSource.source_bot_model)}). No tools are available; normal usage limits apply. Review the draft before using it.</p>
            <p class="hint">Stop a running draft from the coordinator chat. No Bot settings change until you apply it.</p>
            <p class="hint" role="status" aria-live="polite" id="setup-purpose-draft-status">${esc(draft.purposeRefinementStatus)}</p>
            ${purposeRefinementHtml()}
          </div>
        </details>` : ""}
      <label class="field" for="setup-display_name">Bot name<input id="setup-display_name" maxlength="80" autocomplete="off" placeholder="Avery Morgan · Project Status Reporter" value="${esc(draft.display_name)}" required>
        <span class="hint">Suggested from the work you described. You can change it now or later.</span></label>
      <details class="setup-schedule setup-identity">
        <summary>More name options</summary>
        <div class="form-grid">
          <label class="field" for="setup-name">Bot address<input id="setup-name" maxlength="41" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="release-notes-reviewer" value="${esc(draft.name)}" required>
            <span class="hint">Stable local address; it follows the display name until you edit it.</span></label>
          <label class="field" for="setup-description">Short description<input id="setup-description" maxlength="240" placeholder="What people can ask this Bot to do" value="${esc(draft.description)}"></label>
        </div>
      </details>
      ${!draft.forceAdvanced ? `<section class="setup-quick-summary" aria-label="Starting settings">
        <p>${draft.model ? `Uses ${esc(draft.model)} · ${esc(draft.inference_mode)} route` : "Choose a model route to continue"} · managed workspace · no tools or schedule · actions ask first.</p>
        <p class="hint">Creates the Bot only; no run starts.</p>
      </section>
      <button type="button" class="btn ghost small setup-customize" id="setup-customize">Customize advanced settings</button>` : ""}
    </div>`;
    if (step === 1) {
      let routeOptions = [];
      try { routeOptions = await api(`/v1/model-routes?inference_mode=${encodeURIComponent(draft.inference_mode)}`); }
      catch { /* the route can still be entered directly; creation validates it */ }
      if (draft.step !== 1) return;
      const readyRoutes = routeOptions.filter(route => route.state === "ready" && !route.spec.startsWith("mock/"));
      const options = readyRoutes.map(route => `<option value="${esc(route.spec)}" label="${esc(`${route.group}: ${route.note || route.label}`)}"></option>`).join("");
      content = `<div class="setup-conversation form-grid">
        <p class="setup-assistant">${draft.model ? "Hutch found a configured route from this chat or your workspace. Review it below." : "Choose a configured model route. Safe defaults fill the other setup choices."} It becomes the Bot’s saved default; creating the Bot does not start a run.</p>
        <label class="field" for="setup-model">Model route<input id="setup-model" list="setup-model-routes" maxlength="240" autocomplete="off" placeholder="Choose or enter provider/model" value="${esc(draft.model)}" required>
          <datalist id="setup-model-routes">${options}</datalist>
          <span class="hint">${modelSuggestionSource === "chat" ? `Suggested from ${esc(conversationSource.source_bot_name)}’s current route and routing mode: ${esc(conversationSource.model_suggestion)}.` : modelSuggestionSource === "duplicate" ? `Copied from ${esc(duplicateBot?.display_name || duplicateBot?.name)}; confirm it is configured in Connections.` : modelSuggestionSource === "workspace" ? `Workspace default for new Bots: ${esc(workspaceDefaults.model)}.` : modelSuggestionSource === "import" ? `Imported route: ${esc(modelSuggestion)}. Confirm it is configured in Connections.` : "No workspace or chat model route is configured yet."} ${readyRoutes.length ? `${readyRoutes.length} ready route${readyRoutes.length === 1 ? "" : "s"} shown as suggestions.` : "No ready routes were found. Configure a provider or local model in Connections."} Hosted routes send prompts to that provider; local routes use this machine. <a href="/#/connections" target="_blank" rel="noopener">Open Connections in another tab</a>.</span></label>
        <label class="field" for="setup-inference_mode">Inference mode<select id="setup-inference_mode">
          <option value="hybrid" ${draft.inference_mode === "hybrid" ? "selected" : ""}>Hybrid — local or hosted</option>
          <option value="local" ${draft.inference_mode === "local" ? "selected" : ""}>Local — this machine</option>
          <option value="offline" ${draft.inference_mode === "offline" ? "selected" : ""}>Strict offline</option>
        </select><span class="hint">Strict offline requires a verified local route.</span></label>
        <label class="field" for="setup-workspace_mode">Workspace<select id="setup-workspace_mode">
          <option value="fresh" ${draft.workspace_mode === "fresh" ? "selected" : ""}>Fresh — a clean workspace for each run</option>
          <option value="managed" ${draft.workspace_mode === "managed" ? "selected" : ""}>Managed — keep this bot’s workspace between runs</option>
        </select></label>
      </div>`;
    }
    if (step === 2) content = `<div class="setup-conversation form-grid">
      <p class="setup-assistant">Bots start with no tools unless a starter is selected. Choose only abilities this Bot needs; actions that require approval stay ask-first.</p>
      <details class="setup-schedule" ${draft.template ? "open" : ""}>
        <summary>Choose a starting point</summary>
        <fieldset class="setup-template-options"><legend class="sr-only">Starting point</legend>
          <label class="setup-choice"><input type="radio" name="setup-template" value="" ${draft.template ? "" : "checked"}>
            <span><b>Blank bot</b><small>No tools enabled by default.</small></span></label>
          ${templates.map(template => `<label class="setup-choice"><input type="radio" name="setup-template" value="${esc(template.name)}" ${draft.template === template.name ? "checked" : ""}>
            <span><b>${esc(template.tagline || template.name)}</b><small>${esc(template.description || template.safety || "Starter configuration")}</small></span></label>`).join("")}
        </fieldset>
      </details>
      <details class="setup-schedule" id="setup-tools-details" ${draft.tools.size ? "open" : ""}>
        <summary>Enable tools (none enabled by default)</summary>
        <fieldset class="setup-tool-options" id="setup-tools"><legend>Tools and permissions</legend>
          ${BOT_SETUP_TOOLS.map(([tool, label, help]) => `<label class="tool-option"><input type="checkbox" name="setup-tool" value="${esc(tool)}" ${draft.tools.has(tool) ? "checked" : ""}>
            <span class="tool-option-copy"><b>${esc(label)}</b><small>${esc(help)}</small></span></label>`).join("")}
        </fieldset>
      </details>
      <details class="setup-schedule">
        <summary>Add a recurring task (optional)</summary>
        <div class="form-grid">
          <label class="field" for="setup-cron">Cron schedule<input id="setup-cron" maxlength="100" placeholder="0 9 * * 1" value="${esc(draft.cron)}"></label>
          <label class="field" for="setup-timezone">Time zone<input id="setup-timezone" maxlength="120" placeholder="America/Vancouver" value="${esc(draft.timezone)}"><span class="hint">Use an IANA time zone such as UTC or America/Vancouver.</span></label>
          <label class="field" for="setup-catch_up">Missed schedule windows<select id="setup-catch_up">
            <option value="coalesce" ${draft.catch_up === "coalesce" ? "selected" : ""}>Run once when Hutch is available</option>
            <option value="skip" ${draft.catch_up === "skip" ? "selected" : ""}>Skip windows older than 30 minutes</option>
          </select></label>
          <label class="field" for="setup-schedule_prompt">Scheduled task prompt<textarea id="setup-schedule_prompt" maxlength="4000" rows="3" placeholder="Leave blank to use the standing instructions">${esc(draft.schedule_prompt)}</textarea>
            <span class="hint">A scheduled task prompt needs a cron schedule.</span></label>
        </div>
      </details>
      <details class="setup-schedule">
        <summary>Adjust execution and usage limits</summary>
        <div class="form-grid">
          <div class="form-grid row2">
            <label class="field" for="setup-limit-max_steps">Maximum steps<input type="number" id="setup-limit-max_steps" min="1" step="1" value="${draft.limits.max_steps}" required></label>
            <label class="field" for="setup-limit-timeout_seconds">Time limit (seconds)<input type="number" id="setup-limit-timeout_seconds" min="1" step="1" value="${draft.limits.timeout_seconds}" required></label>
            <label class="field" for="setup-limit-daily_token_cap">Daily estimated tokens<input type="number" id="setup-limit-daily_token_cap" min="0" step="1" value="${draft.limits.daily_token_cap}" required></label>
            <label class="field" for="setup-limit-max_turn_tokens">Tokens per turn<input type="number" id="setup-limit-max_turn_tokens" min="0" step="1" value="${draft.limits.max_turn_tokens}" required></label>
            <label class="field" for="setup-limit-max_cost_usd">Estimated cost per run (USD)<input type="number" id="setup-limit-max_cost_usd" min="0" step="0.01" value="${draft.limits.max_cost_usd}" required></label>
            <label class="field" for="setup-limit-daily_cost_cap_usd">Estimated daily cost (USD)<input type="number" id="setup-limit-daily_cost_cap_usd" min="0" step="0.01" value="${draft.limits.daily_cost_cap_usd}" required></label>
          </div>
          <p class="hint">Token and currency limits use estimates. Provider billing can differ; use provider-side controls for a guaranteed spending limit. 0 means no estimate limit.</p>
        </div>
      </details>
      <details class="setup-schedule">
        <summary>Human browser handoff (optional)</summary>
        <div class="form-grid">
          <label class="tool-option" for="setup-local-browser-handoff">
            <input type="checkbox" id="setup-local-browser-handoff" ${draft.local_browser_handoff ? "checked" : ""} ${browserHandoffReady ? "" : "disabled"}>
            <span class="tool-option-copy"><b>Let me take over this bot’s browser</b><small>Pause for login, CAPTCHA, 2FA and sensitive form fields. Hutch will not solve challenges or type passwords.</small></span>
          </label>
          <p class="hint">${esc(browserHandoffHelp)}</p>
        </div>
      </details>
    </div>`;
    if (step === 3) content = reviewHtml();
    const root = $("#modal-root");
    const body = $(".modal-body", root), title = $("#modal-title"), confirm = $("#modal-confirm");
    if (!body || !title || !confirm) return;
    const sourceQuick = step === 0 && !draft.forceAdvanced && !!conversationSource && draft.useConversationSource;
    title.textContent = sourceQuick ? "Create from this request" : stepTitles[step];
    const progress = step === 0 && !draft.forceAdvanced
      ? sourceQuick ? "Your request is already selected · review the name and starting settings"
        : "Quick setup · safe defaults; customize anything before creating"
      : `Step ${step + 1} of ${stepTitles.length}`;
    body.innerHTML = `<div class="bot-setup" aria-live="polite"><div class="setup-progress">${progress}</div>${back}${content}<p class="setup-error" id="bot-setup-error" role="alert" hidden></p></div>`;
    body.scrollTop = 0;
    confirm.textContent = step === 3 || (step === 0 && !draft.forceAdvanced && !!draft.model.trim())
      ? "Create bot" : step === 0 && !draft.forceAdvanced ? "Choose a model" : "Continue";
    confirm.disabled = false;
    let configurationYaml = "";
    $("#setup-yaml-build")?.addEventListener("click", async event => {
      snapshotFields();
      const button = event.currentTarget;
      const download = $("#setup-yaml-download"), status = $("#setup-yaml-status"), preview = $("#setup-yaml-preview");
      button.disabled = true;
      if (download) download.disabled = true;
      if (preview) { preview.hidden = true; preview.textContent = ""; }
      if (status) status.textContent = "Validating and building a preview…";
      try {
        const result = await api("/v1/bot-configs/preview", { method: "POST", body: setupConfiguration() });
        configurationYaml = result.yaml;
        if (preview) { preview.textContent = configurationYaml; preview.hidden = false; }
        if (download) download.disabled = false;
        if (status) status.textContent = "YAML preview ready. No Bot was created or changed.";
      } catch (error) {
        configurationYaml = "";
        if (status) status.textContent = `Could not build the preview: ${error.message}`;
      } finally {
        button.disabled = false;
      }
    });
    $("#setup-yaml-download")?.addEventListener("click", () => {
      if (!configurationYaml) return;
      const blob = new Blob([configurationYaml], { type: "application/yaml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const slug = (draft.name || "bot-config").toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "") || "bot-config";
      link.href = url;
      link.download = `hutch-${slug}.yaml`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    });
    $("#setup-yaml-import-button")?.addEventListener("click", () => $("#setup-yaml-file")?.click());
    $("#setup-yaml-file")?.addEventListener("change", async event => {
      const input = event.currentTarget;
      const file = input.files?.[0];
      const status = $("#setup-yaml-import-status");
      if (!file) return;
      if (file.size > 65_536) {
        if (status) status.textContent = "Choose a YAML file no larger than 64 KiB.";
        input.value = "";
        return;
      }
      const choose = $("#setup-yaml-import-button");
      if (choose) choose.disabled = true;
      if (status) status.textContent = "Checking the YAML file; nothing will be saved yet…";
      try {
        const result = await api("/v1/bot-configs/import", { method: "POST", body: { yaml: await file.text() } });
        if (result.configuration.local_browser_handoff && !browserHandoffReady) {
          throw new Error(`This file enables browser handoff, which is unavailable here: ${browserHandoffCapability.reason}`);
        }
        snapshotFields();
        applyImportedConfiguration(result.configuration);
        await renderStep();
        $("#setup-purpose")?.focus();
      } catch (error) {
        if (status) status.textContent = `Could not load this YAML file: ${error.message}`;
      } finally {
        input.value = "";
        const activeChoose = $("#setup-yaml-import-button");
        if (activeChoose) activeChoose.disabled = false;
      }
    });
    $("#setup-back")?.addEventListener("click", () => { snapshotFields(); draft.step = Math.max(0, draft.step - 1); void renderStep(); });
    $("#setup-customize")?.addEventListener("click", () => {
      snapshotFields(); draft.forceAdvanced = true; draft.step = 1;
      void renderStep().then(() => $("#setup-model")?.focus());
    });
    $("#setup-use-source")?.addEventListener("change", event => {
      draft.useConversationSource = event.currentTarget.checked;
      draft.purpose = draft.useConversationSource ? conversationSource.original_request : "";
      const purposeEditor = $("#setup-purpose-editor");
      if (purposeEditor) purposeEditor.open = !draft.useConversationSource;
      refreshSuggestedIdentity();
      refreshNamePreview();
      const purpose = $("#setup-purpose");
      if (purpose) { purpose.value = draft.purpose; if (!draft.useConversationSource) purpose.focus(); }
      const refine = $("#setup-refine-purpose");
      if (refine) refine.disabled = !draft.useConversationSource;
      refreshContextCount();
      markPurposeDraftFreshness();
    });
    $("#setup-purpose")?.addEventListener("input", event => {
      draft.purpose = event.currentTarget.value;
      refreshSuggestedIdentity();
      refreshNamePreview();
      refreshContextCount();
      markPurposeDraftFreshness();
    });
    $$('[data-setup-context-message]').forEach(input => input.addEventListener("change", () => {
      draft.selectedContextMessageIds = new Set($$('[data-setup-context-message]:checked')
        .map(item => item.dataset.setupContextMessage));
      refreshContextCount();
      markPurposeDraftFreshness();
    }));
    $("#setup-purpose-draft-use")?.addEventListener("click", () => {
      const suggestion = $("#setup-purpose-draft-text")?.value || "";
      if (!suggestion.trim() || suggestion.length > 20_000) {
        setError("Review a non-empty instruction draft within the 20,000-character limit.");
        return;
      }
      const sourceState = draft.purposeRefinement?.sourceFingerprint;
      if (!draft.useConversationSource || sourceState !== currentPurposeDraftFingerprint()) {
        setError("The purpose or selected context changed after this draft was requested. Draft again before using it.");
        return;
      }
      draft.purpose = suggestion;
      draft.purposeRefinement = null;
      draft.purposeRefinementStatus = "Draft applied to the purpose field. Review it and the remaining Bot settings before creating.";
      refreshSuggestedIdentity();
      void renderStep().then(() => $("#setup-purpose")?.focus());
    });
    $("#setup-refine-purpose")?.addEventListener("click", async event => {
      snapshotFields();
      setError("");
      if (!conversationSource?.source_bot_is_coordinator || !draft.useConversationSource || !draft.purpose.trim()) {
        setError("Use the selected coordinator request and review a non-empty purpose before drafting.");
        return;
      }
      if (Array.from(instructionsForDraft()).length > 20_000) {
        setError("Shorten the purpose or select fewer messages before drafting; the combined text exceeds 20,000 characters.");
        return;
      }
      const body = {source_message_id: conversationSource.message_id, purpose: draft.purpose,
        context_message_ids: selectedCreationContext().map(message => message.id)};
      const sourceFingerprint = currentPurposeDraftFingerprint();
      const keyStorage = `hutch-bot-purpose-draft:${conversationSource.conversation_id}:${conversationSource.message_id}`;
      const fingerprint = await payloadFingerprint(body);
      let key;
      try {
        const prior = JSON.parse(storageGet(keyStorage) || "null");
        key = prior?.fingerprint === fingerprint ? prior.key : null;
      } catch { /* replace a damaged retry marker */ }
      if (!key) {
        key = newIdempotencyKey();
        storageSet(keyStorage, JSON.stringify({fingerprint, key}));
      }
      const button = event.currentTarget;
      button.disabled = true;
      draft.purposeRefinement = null;
      draft.purposeRefinementStatus = "Starting one tool-free model response with the workspace coordinator…";
      const status = $("#setup-purpose-draft-status");
      if (status) status.textContent = draft.purposeRefinementStatus;
      try {
        const run = await api(`/v1/conversations/${encodeURIComponent(conversationSource.conversation_id)}/bot-purpose-drafts`, {
          method: "POST", headers: {"Idempotency-Key": key}, body,
        });
        const deadline = Date.now() + 120_000;
        let state;
        while (Date.now() < deadline) {
          state = await api(`/v1/tasks/runs/${encodeURIComponent(run.id)}?events=200`);
          if (state.terminal) break;
          draft.purposeRefinementStatus = `Coordinator draft is ${state.status_label || state.status}; you can keep this sheet open or stop the run in chat.`;
          const progress = $("#setup-purpose-draft-status");
          if (progress) progress.textContent = draft.purposeRefinementStatus;
          await new Promise(resolve => setTimeout(resolve, 900));
        }
        if (!state?.terminal) throw new Error("The request is still running. Its status and Stop control are in the coordinator chat.");
        if (state.status !== "succeeded") throw new Error(state.error || state.reason || `Draft ended as ${state.status_label || state.status}.`);
        const answer = [...(state.events || [])].reverse().find(item => item.type === "message" && item.data?.role === "assistant")?.data?.content || "";
        if (!answer.trim()) throw new Error("The coordinator did not return an instruction draft.");
        if (answer.length > 20_000) throw new Error("The coordinator draft exceeds the 20,000-character limit; edit it in chat before using it.");
        draft.purposeRefinement = {content: answer, sourceFingerprint};
        draft.purposeRefinementStatus = "Draft ready. Review it before applying; no Bot configuration has changed.";
        await renderStep();
        $("#setup-purpose-draft-text")?.focus();
      } catch (error) {
        draft.purposeRefinementStatus = `Draft not applied: ${error.message}`;
        const progress = $("#setup-purpose-draft-status");
        if (progress) progress.textContent = draft.purposeRefinementStatus;
        button.disabled = false;
      }
    });
    refreshContextCount();
    $("#setup-display_name")?.addEventListener("input", event => {
      displayNameEdited = true;
      draft.display_name = event.currentTarget.value;
      refreshNamePreview();
      if (!addressEdited) {
        draft.name = uniqueAddress(draft.display_name);
        const address = $("#setup-name");
        if (address) address.value = draft.name;
      }
    });
    $("#setup-name")?.addEventListener("input", event => {
      addressEdited = true;
      draft.name = event.currentTarget.value;
    });
    $$('input[name="setup-template"]').forEach(input => input.addEventListener("change", () => {
      draft.template = input.value;
      draft.tools = templateTools(selectedTemplate());
      draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
      const toolsDetails = $("#setup-tools-details");
      if (toolsDetails && draft.tools.size) toolsDetails.open = true;
    }));
    $$('input[name="setup-tool"]').forEach(input => input.addEventListener("change", () => {
      if (input.checked) draft.tools.add(input.value); else draft.tools.delete(input.value);
      draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
    }));
    $("#setup-inference_mode")?.addEventListener("change", async () => {
      snapshotFields(); draft.inference_mode = $("#setup-inference_mode").value; await renderStep();
    });
    (step === 0 ? (conversationSource && draft.useConversationSource && !draft.forceAdvanced
      ? $("#setup-display_name") : $("#setup-purpose")) : step === 1 ? $("#setup-model") : $("input, textarea, select", body))?.focus();
  };
  const creationKey = async body => {
    const fingerprint = await payloadFingerprint(body), keyName = "hutch-pending-bot-create";
    try {
      const previous = JSON.parse(localStorage.getItem(keyName) || "null");
      if (previous?.fingerprint === fingerprint && previous?.key) return previous.key;
    } catch { /* replace a damaged retry marker */ }
    const key = newIdempotencyKey();
    storageSet(keyName, JSON.stringify({ key, fingerprint }));
    return key;
  };
  openModal({
    title: stepTitles[0], bodyHtml: `<div class="bot-setup"></div>`,
    confirmText: draft.model ? "Create bot" : "Choose a model", wide: true, tall: true,
    returnFocus: document.activeElement,
    onConfirm: async () => {
      snapshotFields();
      setError("");
      if (draft.step === 0 && !draft.purpose.trim()) { setError("Describe what this bot should handle."); $("#setup-purpose")?.focus(); return false; }
      if (draft.step === 0 && Array.from(instructionsForDraft()).length > 20_000) {
        setError("Shorten the purpose or select fewer messages; saved Bot instructions are limited to 20,000 characters.");
        $("#setup-purpose")?.focus(); return false;
      }
      if (draft.step === 0) {
        if (!draft.display_name.trim()) { setError("Add a display name for this Bot."); $("#setup-display_name")?.focus(); return false; }
        if (!/^[a-z0-9][a-z0-9-]{1,40}$/.test(draft.name.trim())) { setError("Use 2–41 lowercase letters, numbers, and dashes for the Bot address."); $("#setup-name")?.focus(); return false; }
      }
      if (draft.step === 1 && !draft.model.trim()) { setError("Choose or enter a configured model route."); $("#setup-model")?.focus(); return false; }
      if (draft.step === 2 && draft.schedule_prompt.trim() && !draft.cron.trim()) { setError("Add a cron schedule before setting its task prompt."); $("#setup-cron")?.focus(); return false; }
      if (draft.step === 2) {
        const invalidLimit = $$(".bot-setup input[type=number]").find(field => !field.checkValidity());
        if (invalidLimit) { setError("Check the execution and usage limit values."); invalidLimit.focus(); return false; }
      }
      if (draft.step === 0 && !draft.forceAdvanced && !draft.model.trim()) {
        draft.forceAdvanced = true; draft.step = 1; await renderStep(); return false;
      }
      if (draft.step === 0 && draft.forceAdvanced) { draft.step = 1; await renderStep(); return false; }
      if (draft.step > 0 && draft.step < 3) { draft.step += 1; await renderStep(); return false; }
      const body = {
        ...setupConfiguration(),
        source_conversation_id: draft.useConversationSource || selectedCreationContext().length ? conversationSource?.conversation_id || null : null,
        source_message_id: draft.useConversationSource ? conversationSource?.message_id || null : null,
        source_context_message_ids: selectedCreationContext().map(message => message.id),
      };
      const button = $("#modal-confirm"); if (button) button.disabled = true;
      try {
        const key = await creationKey(body);
        const bot = await api("/v1/bots", { method: "POST", headers: { "Idempotency-Key": key }, body });
        storageRemove("hutch-pending-bot-create");
        toast(`Bot “${bot.display_name || draft.display_name}” created. It has not started a run.`);
        location.hash = `#/chat/${encodeURIComponent(bot.name)}`;
        return true;
      } catch (err) { setError(err.message); if (button) button.disabled = false; return false; }
    },
  });
  await renderStep();
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
    if (["workspace", "bots"].some(resource => changed.has(resource)) && (location.hash || "#/chat") === "#/schedules") {
      void renderSchedules();
    }
    if (["messages", "conversations", "runs", "approvals", "actions", "transcript_mirrors", "memory", "workspace_tasks", "code_handoffs"].some(r => changed.has(r))) {
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
          if (change.context.run_id) {
            terminalRunCache.delete(change.context.run_id);
            terminalRunReplyCache.delete(change.context.run_id);
          }
          if (change.resource === "runs") {
            terminalRunCache.delete(change.resource_id);
            terminalRunReplyCache.delete(change.resource_id);
          }
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
  terminalRunReplyCache.clear();
  resourceRetry = setTimeout(startResourceStream, 1500);
}

/* ------------------------------------------------------- paired-phone mode */

let phoneRoot = null;
let phoneModel = { bots: [], runs: [], approvals: [], selectedRun: null, tab: "status", notice: "", offline: false };
let phonePoll = null;
let phoneChangeStream = null;
let phoneRunStream = null;
let phoneRunStreamId = null;
let phoneExpiryTimer = null;
let phoneRefreshInFlight = false;
let phoneLastActivityTouch = 0;
let phonePendingCommand = null;
let phoneUnresolvedCommand = null;

function phoneStorageKey() { return "hutch-phone-pending-command"; }

function phoneLoadPendingCommand() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(phoneStorageKey()) || "null");
    if (stored && stored.method === "POST" && stored.key && stored.path?.startsWith("/v1/")) {
      if (stored.credential_id === hutchSession?.credential_id) phonePendingCommand = stored;
      else phoneUnresolvedCommand = stored;
    }
  } catch { phonePendingCommand = null; }
}

function phoneSavePendingCommand() {
  try {
    if (phonePendingCommand) sessionStorage.setItem(phoneStorageKey(), JSON.stringify(phonePendingCommand));
    else if (phoneUnresolvedCommand) sessionStorage.setItem(phoneStorageKey(), JSON.stringify(phoneUnresolvedCommand));
    else sessionStorage.removeItem(phoneStorageKey());
  } catch { /* an in-memory retry remains available for this page */ }
}

function lockExpiredPhone() {
  if (phoneChangeStream) phoneChangeStream.close();
  if (phoneRunStream) phoneRunStream.close();
  clearInterval(phonePoll);
  clearTimeout(phoneExpiryTimer);
  phoneChangeStream = phoneRunStream = null;
  phoneRunStreamId = null;
  phoneExpiryTimer = null;
  phoneRoot = null;
  hutchSession = null;
  hutchCsrfToken = "";
  document.body.classList.remove("paired-phone");
  document.body.replaceChildren();
  const message = document.createElement("main");
  message.className = "phone-locked";
  message.innerHTML = `<h1>Hutch is locked</h1><p>Your paired session expired or was revoked. Private dashboard content has been cleared from this page.</p><a class="btn primary" href="/login">Sign in with your passkey</a>`;
  document.body.append(message);
}

function phoneSetSessionExpiry(idleExpiresAt, absoluteExpiresAt) {
  clearTimeout(phoneExpiryTimer);
  const deadlines = [Date.parse(idleExpiresAt || ""), Date.parse(absoluteExpiresAt || "")].filter(Number.isFinite);
  if (!deadlines.length) return;
  const delay = Math.min(...deadlines) - Date.now();
  if (delay <= 0) { lockExpiredPhone(); return; }
  phoneExpiryTimer = setTimeout(lockExpiredPhone, delay);
}

async function phoneRefresh({ quiet = false } = {}) {
  if (!phoneRoot || phoneRefreshInFlight || document.hidden) return;
  phoneRefreshInFlight = true;
  try {
    const [bots, runs, approvals] = await Promise.all([
      api("/bots"), api("/v1/tasks/runs?limit=40"),
      api("/v1/actions/approvals?status=pending&limit=100"),
    ]);
    phoneModel.bots = bots;
    phoneModel.runs = runs;
    phoneModel.approvals = approvals;
    if (phoneModel.selectedRun) {
      try { phoneModel.selectedRun = await api(`/v1/tasks/runs/${encodeURIComponent(phoneModel.selectedRun.id)}`); }
      catch (error) { if (error.status !== 404) throw error; phoneModel.selectedRun = null; }
    }
    phoneModel.offline = false;
    if (!quiet) phoneModel.notice = "";
    phoneRender();
    phoneAttachRunStream();
  } catch (error) {
    if (!phoneRoot) return;
    phoneModel.offline = true;
    if (!quiet) phoneModel.notice = `Could not refresh Hutch: ${error.message}. Displayed status may be out of date.`;
    phoneRender();
  } finally { phoneRefreshInFlight = false; }
}

function phoneRender() {
  if (!phoneRoot) return;
  const pending = phonePendingCommand;
  const bots = phoneModel.bots || [];
  const runs = phoneModel.runs || [];
  const approvals = phoneModel.approvals || [];
  const active = new Set(["pending", "loading_model", "running", "waiting_approval", "waiting_human",
    "waiting_resources", "recovering", "cancelling"]);
  const selected = phoneModel.selectedRun;
  const phoneTimestamp = (value) => {
    if (!value) return "time unavailable";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "time unavailable" : date.toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
    });
  };
  let body = "";

  if (phoneModel.tab === "review") {
    body = approvals.length ? `<section class="phone-list" aria-label="Pending approvals">${approvals.map(a => {
      const id = a.approval_id || a.id;
      const detail = JSON.stringify(a.detail || {}, null, 2);
      return `<article class="phone-card approval-card"><div class="phone-card-head"><span class="phone-status needs">Needs review</span><span>${esc(a.bot_display_name || a.bot_name || "Bot")}</span></div>
        <h2>${esc(a.action || "Requested action")}</h2><p class="phone-sub">${esc(a.tool || "Action")} · ${esc(a.risk || "risk unavailable")}${a.outward ? " · sends data outside this machine" : ""}</p>
        <details><summary>Review exact request</summary><pre>${esc(detail)}</pre>${a.rule ? `<p>${esc(a.rule)}</p>` : ""}</details>
        <div class="phone-actions"><button class="btn primary" type="button" data-phone-approve="${esc(id)}" data-action-hash="${esc(a.action_hash || "")}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Allow once</button><button class="btn danger" type="button" data-phone-deny="${esc(id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Deny</button></div>
      </article>`;
    }).join("")}</section>` : `<section class="phone-empty"><h2>Nothing needs review</h2><p>Pending action requests will appear here.</p></section>`;
  } else if (phoneModel.tab === "runs" && selected) {
    const events = selected.events || [];
    body = `<section class="phone-run-detail"><button class="btn ghost" type="button" data-phone-back><svg class="ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg> All runs</button>
      <article class="phone-card"><div class="phone-card-head"><span class="phone-status">${esc(selected.status_label || selected.status)}</span><span>${esc(selected.bot_display_name || selected.bot_name || "Bot")}</span></div>
      <h1>${esc(selected.prompt || "Run")}</h1><p class="phone-sub">Started ${esc(phoneTimestamp(selected.created_at))}</p>
      ${active.has(selected.status) ? `<button class="btn danger" type="button" data-phone-stop="${esc(selected.id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Stop run</button>` : ""}
      ${selected.status === "waiting_human" ? (() => { const wait = [...events].reverse().find(e => e.type === "human_needed"); return wait ? `<button class="btn primary" type="button" data-phone-resume="${esc(selected.id)}" data-human-seq="${Number(wait.seq) || 0}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Resume after completing the requested step</button>` : ""; })() : ""}
      </article><h2 class="phone-section-title">Progress</h2>
      ${events.length ? `<ol class="phone-transcript">${events.map(e => {
        const d = e.data || {};
        const content = d.content ?? d.text ?? d.command ?? d.message ?? JSON.stringify(d, null, 2);
        return `<li><span>${esc(String(e.type || "event").replaceAll("_", " "))} · ${esc(phoneTimestamp(e.ts))}</span><pre>${esc(String(content).slice(0, 6000))}${String(content).length > 6000 ? "\\n… clipped for phone display" : ""}</pre></li>`;
      }).join("")}</ol>` : `<p class="phone-empty">No transcript events have arrived yet.</p>`}
      ${selected.events_truncated ? `<p class="phone-sub">Showing the latest transcript window. Open Hutch on its host to inspect older history.</p>` : ""}</section>`;
  } else if (phoneModel.tab === "runs") {
    body = runs.length ? `<section class="phone-list" aria-label="Runs">${runs.map(run => `<button class="phone-card phone-run-card" type="button" data-phone-run="${esc(run.id)}"><span class="phone-card-head"><span class="phone-status ${run.needs_person ? "needs" : ""}">${esc(run.status_label || run.status)}</span><span>${esc(run.bot_display_name || run.bot_name || "Bot")}</span></span><strong>${esc(run.prompt || "Run")}</strong><span class="phone-sub">${esc(phoneTimestamp(run.created_at))}</span></button>`).join("")}</section>` : `<section class="phone-empty"><h2>No runs yet</h2><p>Runs started locally or from a paired device will appear here.</p></section>`;
  } else {
    const running = runs.filter(run => active.has(run.status));
    const candidates = bots.filter(bot => bot.remote_start_enabled);
    body = `<section class="phone-summary"><div><strong>${running.length}</strong><span>in progress</span></div><div><strong>${approvals.length}</strong><span>need review</span></div><div><strong>${bots.length}</strong><span>Bots</span></div></section>
      <section><h2 class="phone-section-title">Bots</h2>${bots.length ? `<div class="phone-list">${bots.map(bot => `<article class="phone-card"><div class="phone-card-head"><strong>${esc(bot.display_name || bot.name)}</strong><span class="phone-status ${bot.paused ? "needs" : ""}">${bot.paused ? "Paused" : esc(bot.active_run_status_label || "Ready")}</span></div><p class="phone-sub">${esc(bot.description || "")}</p>${bot.paused ? `<span class="phone-sub">Scheduled tasks are paused</span>` : ""}${bot.remote_start_enabled ? `<span class="phone-sub">Phone starts enabled by the local owner</span>` : `<span class="phone-sub">Monitor and review only</span>`}</article>`).join("")}</div>` : `<p class="phone-empty">No Bots are configured.</p>`}</section>
      <section><h2 class="phone-section-title">Start work</h2>${candidates.length ? `<form class="phone-card phone-start-form" id="phone-start-form"><label>Bot<select name="bot" required>${candidates.map(bot => `<option value="${esc(bot.name)}">${esc(bot.display_name || bot.name)}${bot.paused ? " · scheduled tasks paused" : ""}</option>`).join("")}</select></label><label>What should this Bot do?<textarea name="prompt" rows="4" maxlength="20000" required placeholder="Describe the task"></textarea></label><p class="phone-sub">Uses the Bot’s locally configured model, tools, workspace and approval policy. Starting work here creates an on-demand run; pausing a Bot only pauses its scheduled tasks.</p><button class="btn primary" type="submit" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Start work</button></form>` : `<p class="phone-empty">No Bot is enabled for phone starts. A local owner can enable one with <code>hutch bot update NAME --remote-start</code>.</p>`}</section>
      <section><h2 class="phone-section-title">Recent runs</h2>${runs.slice(0, 8).map(run => `<button class="phone-card phone-run-card" type="button" data-phone-run="${esc(run.id)}"><span class="phone-card-head"><span class="phone-status ${run.needs_person ? "needs" : ""}">${esc(run.status_label || run.status)}</span><span>${esc(run.bot_display_name || run.bot_name || "Bot")}</span></span><strong>${esc(run.prompt || "Run")}</strong></button>`).join("") || `<p class="phone-empty">No runs to show yet.</p>`}</section>`;
  }

  phoneRoot.innerHTML = `<header class="phone-header"><a href="/" class="phone-brand" aria-label="Hutch home">hutch <span>supervision</span></a><div class="phone-header-actions"><span class="phone-connection ${phoneModel.offline ? "offline" : ""}" role="status">${phoneModel.offline ? "Reconnect needed" : "Connected"}</span><button class="btn ghost small" type="button" data-phone-refresh>Refresh</button><button class="btn ghost small" type="button" data-phone-logout>Lock</button></div></header>
    <nav class="phone-tabs" aria-label="Phone supervision"><button type="button" data-phone-tab="status" aria-current="${phoneModel.tab === "status" ? "page" : "false"}">Status</button><button type="button" data-phone-tab="review" aria-current="${phoneModel.tab === "review" ? "page" : "false"}">Review${approvals.length ? ` <span>${approvals.length}</span>` : ""}</button><button type="button" data-phone-tab="runs" aria-current="${phoneModel.tab === "runs" ? "page" : "false"}">Runs</button></nav>
    <main class="phone-content">${pending ? `<aside class="phone-retry" role="alert"><strong>${esc(pending.label)} may not have been confirmed.</strong><p>Check the current run or approval state. Hutch will only resend if you choose Retry, using the same idempotency key.</p><div class="phone-actions"><button class="btn primary" type="button" data-phone-retry>Retry same request</button><button class="btn ghost" type="button" data-phone-clear-pending>Clear retry</button></div></aside>` : ""}${phoneUnresolvedCommand ? `<aside class="phone-retry" role="alert"><strong>A prior phone command is unresolved.</strong><p>${esc(phoneUnresolvedCommand.label)} used another paired credential. Check current runs and approvals on the host before issuing another command from this device.</p><button class="btn ghost" type="button" data-phone-clear-foreign>I've checked the current state</button></aside>` : ""}${phoneModel.notice ? `<p class="phone-notice" role="status">${esc(phoneModel.notice)}</p>` : ""}${body}</main>`;
}

function phoneAttachRunStream() {
  const run = phoneModel.selectedRun;
  if (!phoneRoot || !run || !["pending", "loading_model", "running", "waiting_approval", "waiting_human", "waiting_resources", "recovering", "cancelling"].includes(run.status)) {
    if (phoneRunStream) phoneRunStream.close();
    phoneRunStream = null;
    phoneRunStreamId = null;
    return;
  }
  if (phoneRunStreamId === run.id) return;
  if (phoneRunStream) phoneRunStream.close();
  const source = new EventSource(`/api/v1/tasks/runs/${encodeURIComponent(run.id)}/stream`);
  phoneRunStream = source;
  phoneRunStreamId = run.id;
  source.addEventListener("batch", () => { if (phoneRunStream === source) void phoneRefresh({ quiet: true }); });
  source.addEventListener("auth_expired", () => { source.close(); lockExpiredPhone(); });
}

async function phoneQueueCommand(label, path, body = null) {
  if (phonePendingCommand || phoneUnresolvedCommand) return;
  const request = { method: "POST", path, body, label, key: newIdempotencyKey(),
    credential_id: hutchSession?.credential_id };
  phonePendingCommand = request;
  phoneSavePendingCommand();
  await phoneAttemptPending();
}

async function phoneAttemptPending() {
  const command = phonePendingCommand;
  if (!command || !phoneRoot) return;
  try {
    const result = await api(command.path, { method: command.method, headers: { "Idempotency-Key": command.key }, body: command.body });
    phonePendingCommand = null;
    phoneSavePendingCommand();
    phoneModel.notice = `${command.label} confirmed.`;
    if (result?.id && command.path === "/v1/tasks/runs") {
      try { phoneModel.selectedRun = await api(`/v1/tasks/runs/${encodeURIComponent(result.id)}`); phoneModel.tab = "runs"; }
      catch { /* list reconciliation below remains authoritative */ }
    }
    await phoneRefresh({ quiet: true });
  } catch (error) {
    if (!phoneRoot) return;
    if (error.status === 0 || error.status >= 500) {
      phoneModel.notice = "The response was not confirmed. Check the visible run or approval state before choosing Retry.";
    } else {
      phonePendingCommand = null;
      phoneSavePendingCommand();
      phoneModel.notice = `${command.label} was not accepted: ${error.message}. Refresh and review the current state.`;
    }
    phoneRender();
  }
}

function phoneHandleClick(event) {
  const button = event.target.closest("button");
  if (!button || !phoneRoot?.contains(button)) return;
  if (button.hasAttribute("data-phone-refresh")) void phoneRefresh();
  else if (button.hasAttribute("data-phone-logout")) {
    void api("/v1/session/logout", { method: "POST", body: {} }).catch(() => {}).finally(lockExpiredPhone);
  } else if (button.dataset.phoneTab) { phoneModel.tab = button.dataset.phoneTab; phoneModel.selectedRun = null; phoneRender(); }
  else if (button.dataset.phoneRun) {
    const id = button.dataset.phoneRun;
    void api(`/v1/tasks/runs/${encodeURIComponent(id)}`).then(run => {
      phoneModel.selectedRun = run; phoneModel.tab = "runs"; phoneRender(); phoneAttachRunStream();
    }).catch(error => { if (phoneRoot) { phoneModel.notice = `Could not load run: ${error.message}`; phoneRender(); } });
  } else if (button.hasAttribute("data-phone-back")) { phoneModel.selectedRun = null; phoneRender(); }
  else if (button.dataset.phoneApprove) {
    if (!button.dataset.actionHash) { phoneModel.notice = "This approval has no current action fingerprint. Refresh before deciding."; phoneRender(); return; }
    void phoneQueueCommand("Allow once", `/v1/actions/approvals/${encodeURIComponent(button.dataset.phoneApprove)}/approve`,
      { always: false, action_hash: button.dataset.actionHash });
  } else if (button.dataset.phoneDeny) {
    void phoneQueueCommand("Deny action", `/v1/actions/approvals/${encodeURIComponent(button.dataset.phoneDeny)}/deny`, {});
  } else if (button.dataset.phoneStop) {
    void phoneQueueCommand("Stop run", `/v1/tasks/runs/${encodeURIComponent(button.dataset.phoneStop)}/stop`, {});
  } else if (button.dataset.phoneResume) {
    const seq = Number(button.dataset.humanSeq);
    if (seq > 0) void phoneQueueCommand("Resume run", `/v1/tasks/runs/${encodeURIComponent(button.dataset.phoneResume)}/resume`, { human_event_seq: seq });
  } else if (button.hasAttribute("data-phone-retry")) void phoneAttemptPending();
  else if (button.hasAttribute("data-phone-clear-pending")) {
    phonePendingCommand = null; phoneSavePendingCommand(); phoneModel.notice = "Saved retry cleared. Refresh to reconcile current state."; void phoneRefresh({ quiet: true });
  } else if (button.hasAttribute("data-phone-clear-foreign")) {
    phoneUnresolvedCommand = null; phoneSavePendingCommand(); phoneModel.notice = "Prior command was cleared after checking current state."; phoneRender();
  }
}

function phoneHandleSubmit(event) {
  const form = event.target.closest("#phone-start-form");
  if (!form || !phoneRoot?.contains(form)) return;
  event.preventDefault();
  if (phonePendingCommand || phoneUnresolvedCommand) return;
  const data = new FormData(form);
  const bot = phoneModel.bots.find(item => item.name === data.get("bot"));
  const prompt = String(data.get("prompt") || "").trim();
  if (!bot?.remote_start_enabled || !prompt) {
    phoneModel.notice = "Choose an enabled Bot and enter a task. The local owner controls each Bot’s remote-start setting.";
    phoneRender();
    return;
  }
  void phoneQueueCommand("Start work", "/v1/tasks/runs", { bot: bot.name, prompt });
}

function phoneNoteActivity() {
  if (hutchSession?.principal !== "paired" || !phoneRoot || document.hidden) return;
  const now = Date.now();
  if (now - phoneLastActivityTouch < 60_000) return;
  phoneLastActivityTouch = now;
  void api("/v1/session/activity", { method: "POST", body: {} }).then(result => {
    if (phoneRoot) phoneSetSessionExpiry(result.idle_expires_at, result.absolute_expires_at);
  }).catch(() => {});
}

function startPhoneApp() {
  document.body.classList.add("paired-phone");
  phoneRoot = document.createElement("div");
  phoneRoot.id = "phone-root";
  document.body.append(phoneRoot);
  phoneLoadPendingCommand();
  phoneSetSessionExpiry(hutchSession.idle_expires_at, hutchSession.absolute_expires_at);
  phoneRoot.addEventListener("click", phoneHandleClick);
  phoneRoot.addEventListener("submit", phoneHandleSubmit);
  document.addEventListener("pointerdown", phoneNoteActivity, { passive: true });
  document.addEventListener("keydown", phoneNoteActivity);
  document.addEventListener("click", phoneNoteActivity, { passive: true });
  phoneRender();
  void phoneRefresh();
  phonePoll = setInterval(() => { if (!document.hidden) void phoneRefresh({ quiet: true }); }, 12_000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void phoneRefresh({ quiet: true }); });
  window.addEventListener("online", () => { phoneModel.offline = false; void phoneRefresh(); });
  window.addEventListener("offline", () => { phoneModel.offline = true; phoneRender(); });
  void api("/v1/snapshot?limit=1").then(snapshot => {
    if (!phoneRoot) return;
    const source = new EventSource(`/api/v1/changes/stream?cursor=${encodeURIComponent(snapshot.change_cursor)}`);
    phoneChangeStream = source;
    source.addEventListener("changes", () => { if (phoneChangeStream === source) void phoneRefresh({ quiet: true }); });
    source.addEventListener("snapshot_required", () => { source.close(); if (phoneChangeStream === source) phoneChangeStream = null; void phoneRefresh(); });
    source.addEventListener("auth_expired", () => { source.close(); lockExpiredPhone(); });
    source.onerror = () => { if (phoneRoot) { phoneModel.offline = true; phoneRender(); } };
  }).catch(() => {});
}

function startOwnerApp() {
  $("#topbar-new-bot")?.addEventListener("click", promptNewBot);
  route();
  void loadStatusInfo();
  refreshRoster();
  void startResourceStream();
  setInterval(() => { refreshBadge(); }, 6000);
  setInterval(refreshRoster, 20000);
  pollHealth();
  setInterval(pollHealth, HEARTBEAT_MS);
}

async function bootstrapHutchApp() {
  try {
    const response = await fetch("/api/v1/session", { credentials: "same-origin", cache: "no-store" });
    if (response.status === 401) { window.location.replace("/login"); return; }
    if (!response.ok) throw new Error(`session check failed (${response.status})`);
    hutchSession = await response.json();
    hutchCsrfToken = hutchSession.csrf_token || "";
    if (hutchSession.principal === "paired") startPhoneApp();
    else startOwnerApp();
  } catch (error) {
    document.body.replaceChildren();
    const panel = document.createElement("main");
    panel.className = "phone-locked";
    panel.textContent = `Could not verify the Hutch session: ${error.message}. Reload when the Hutch host is available.`;
    document.body.append(panel);
  }
}

document.addEventListener("visibilitychange", () => {
  if (hutchSession?.principal === "paired") return;
  if (!document.hidden) {
    refreshChangedResources(["bots", "runs", "approvals", "conversations"]);
    void startResourceStream();
  }
});

void bootstrapHutchApp();
