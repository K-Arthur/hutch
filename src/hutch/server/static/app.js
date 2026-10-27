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
  "waiting_resources", "waiting_child", "recovering", "cancelling"]);
const TASK_ROLE_OPTIONS = [
  ["banter", "Banter"], ["classification", "Classification"], ["extraction", "Extraction"],
  ["summarization", "Summarization"], ["synthesis_research", "Synthesis / research"],
  ["code_analysis", "Code analysis"], ["verification", "Verification"],
];
const DEFAULT_STATUS_INFO = {
  pending: { label: "Queued", terminal: false },
  loading_model: { label: "Loading the model", terminal: false },
  running: { label: "Working", terminal: false },
  waiting_approval: { label: "Waiting for you", terminal: false },
  waiting_human: { label: "Needs you", terminal: false },
  waiting_resources: { label: "Waiting for a free slot or quota", terminal: false },
  waiting_child: { label: "Waiting for delegated work", terminal: false },
  recovering: { label: "Cleaning up", terminal: false },
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
let connectionsGeneration = 0;
let studioConversationMenuCleanup = null;
let activeReplySelectionHandler = null;
let activeAnswerCorrectionHandler = null;
let activeAnswerFeedbackHandler = null;
let activeWorkspaceResultSelectionHandler = null;
let activeBotCreationFromMessageHandler = null;
let activeChoiceSubmitHandler = null;
let activeWorkspaceQuestionSubmitHandler = null;
const requestedHumanResumes = new Set();
const pendingAnswerCorrections = new Set();
const pendingAnswerFeedbackUpdates = new Set();
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
      signal: opts.signal,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
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

/** One owned abort+generation token for a route or dialog subscription. */
function makeSubOwner() {
  return { gen: 0, abort: null, timers: new Set(), sources: new Set() };
}

function bumpSubOwner(owner) {
  owner.gen += 1;
  if (owner.abort) owner.abort.abort();
  owner.abort = typeof AbortController !== "undefined" ? new AbortController() : null;
  for (const t of owner.timers) clearTimeout(t);
  owner.timers.clear();
  for (const s of owner.sources) { try { s.close(); } catch {} }
  owner.sources.clear();
  return owner.gen;
}

function singleFlight(slot, fn) {
  if (slot.promise) return slot.promise;
  slot.promise = Promise.resolve()
    .then(fn)
    .finally(() => { slot.promise = null; });
  return slot.promise;
}

const routeOwner = makeSubOwner();
const shellOwner = makeSubOwner();
const approvalsOwner = makeSubOwner();
bumpSubOwner(shellOwner);

function newIdempotencyKey() {
  return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function storageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function storageSet(key, value) { try { localStorage.setItem(key, value); } catch {} }
function storageRemove(key) { try { localStorage.removeItem(key); } catch {} }

/* The first request belongs to this tab, not the whole workspace. Keeping it
   in sessionStorage survives navigation and reload without resurfacing on a
   later visit as if it were still the person's current intent. */
const firstRunDraftKey = "hutch-first-run-request";
let firstRunDraftMemory = "";
function loadFirstRunDraft() {
  try {
    const raw = sessionStorage.getItem(firstRunDraftKey);
    if (raw === null) return firstRunDraftMemory;
    const saved = JSON.parse(raw);
    if (saved?.version === 1 && typeof saved.request === "string" && saved.request.length <= 20000) {
      firstRunDraftMemory = saved.request;
      return saved.request;
    }
    sessionStorage.removeItem(firstRunDraftKey);
  } catch { /* the in-memory draft still survives this page */ }
  return firstRunDraftMemory;
}
function saveFirstRunDraft(value) {
  firstRunDraftMemory = typeof value === "string" ? value.slice(0, 20000) : "";
  try {
    if (firstRunDraftMemory) {
      sessionStorage.setItem(firstRunDraftKey, JSON.stringify({ version: 1, request: firstRunDraftMemory }));
    } else {
      sessionStorage.removeItem(firstRunDraftKey);
    }
  } catch { /* an in-memory draft remains available for this page */ }
}
function clearFirstRunDraft() {
  firstRunDraftMemory = "";
  try { sessionStorage.removeItem(firstRunDraftKey); } catch {}
}

/* Assistant setup can be long enough to leave and return to. Keep the unsaved
   form in this tab only, and discard it after creation or an explicit reset. */
const assistantSetupDraftKey = "hutch-assistant-setup-draft";
function saveAssistantSetupDraft(payload) {
  try {
    sessionStorage.setItem(assistantSetupDraftKey, JSON.stringify({ version: 1, ...payload }));
  } catch { /* the in-memory page still holds the draft */ }
}
function loadAssistantSetupDraft() {
  try {
    const raw = sessionStorage.getItem(assistantSetupDraftKey);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (saved?.version !== 1 || !saved.draft || typeof saved.draft !== "object") {
      sessionStorage.removeItem(assistantSetupDraftKey);
      return null;
    }
    return saved;
  } catch {
    try { sessionStorage.removeItem(assistantSetupDraftKey); } catch {}
    return null;
  }
}
function clearAssistantSetupDraft() {
  try { sessionStorage.removeItem(assistantSetupDraftKey); } catch {}
}

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
  $$(".assistant-settings-menu[open]").forEach(menu => {
    if (!menu.contains(ev.target)) menu.open = false;
  });
  const openChoice = ev.target.closest("[data-open-choice-conversation]");
  if (!openChoice) return;
  void openConversation(openChoice.dataset.openChoiceConversation);
});

document.addEventListener("keydown", ev => {
  if (ev.key !== "Escape") return;
  const menu = $(".assistant-settings-menu[open]");
  if (!menu) return;
  menu.open = false;
  menu.querySelector("summary")?.focus({ preventScroll: true });
});

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
  const sharedWithHtml = sharedWith.length ? `<div class="conversation-file-grants" role="group" aria-label="Active shares">
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
      <input class="artifact-share-search" type="search" placeholder="Find a chat" autocomplete="off" enterkeyhint="search">
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

let workflowPanelLoadToken = 0;

const WORKFLOW_STATUS_LABELS = {
  pending: "Queued", running: "Running", waiting: "Waiting", succeeded: "Finished",
  failed: "Failed", stopped: "Stopped", outcome_unknown: "Needs review",
};

function workflowDisplayTitle(value) {
  const title = String(value || "").trim();
  if (!/^[a-z0-9][a-z0-9._-]*$/.test(title) || !/[-_.]/.test(title)) return title || "Workflow";
  return title.split(/[-_.]+/).filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

function workflowNodeLabel(node) {
  if (node.question_status === "answered" && node.status !== "succeeded") return "Answer received";
  if (node.question_status === "expired") return "Question expired";
  if (node.question_status === "cancelled") return "Cancelled";
  if (node.status === "succeeded") {
    if (node.result && typeof node.result === "object" && node.result.verified === true) return "Verified";
    if (node.result && typeof node.result === "object" && node.result.verified === false) return "Completed · not verified";
    return "Completed";
  }
  return WORKFLOW_STATUS_LABELS[node.status] || String(node.status || "Unknown").replaceAll("_", " ");
}

async function refreshWorkflowPanel(botName, conversationId, generation, force = false) {
  const panel = $("#workflow-panel");
  if (!panel || !conversationId || !botName) return;
  const activeElement = document.activeElement;
  const hasDraftFocus = panel.contains(activeElement) && activeElement.matches(
    "input, textarea, select, [contenteditable='true']",
  );
  if (!force && hasDraftFocus) return;
  const token = ++workflowPanelLoadToken;
  try {
    const [runPage, definitionPage] = await Promise.all([
      api(`/v1/workflows/runs?bot=${encodeURIComponent(botName)}&limit=50`),
      api("/v1/workflows?limit=50"),
    ]);
    if (token !== workflowPanelLoadToken || generation !== studioGeneration || conversationId !== currentConversationId) return;
    const runs = (runPage.items || []).filter(run => run.conversation_id === conversationId);
    const selected = runs.find(run => ["pending", "running", "waiting"].includes(run.status)) || runs[0] || null;
    let detail = null;
    if (selected) detail = await api(`/v1/workflows/runs/${encodeURIComponent(selected.id)}`);
    if (token !== workflowPanelLoadToken || generation !== studioGeneration || conversationId !== currentConversationId) return;
    const definitions = definitionPage.items || [];
    if (!selected && !definitions.length) {
      panel.hidden = true;
      panel.innerHTML = "";
      return;
    }
    const oldDetails = new Map($$("details[data-workflow-disclosure]", panel).map(item => [item.dataset.workflowDisclosure, item.open]));
    const oldAnswerDrafts = new Map($$("[data-workflow-question-form]", panel).map(form => [
      form.dataset.questionId,
      $("textarea[name=answer]", form)?.value || "",
    ]));
    const focusedQuestion = panel.contains(document.activeElement)
      ? document.activeElement.closest("[data-workflow-question-form]")?.dataset.questionId || ""
      : "";
    const oldFocus = panel.contains(document.activeElement) ? {
      action: document.activeElement.dataset.workflowAction || "",
      id: document.activeElement.dataset.workflowId || document.activeElement.dataset.questionId || "",
      questionId: focusedQuestion,
      disclosure: document.activeElement.closest("details[data-workflow-disclosure]")?.dataset.workflowDisclosure || "",
      summary: document.activeElement.tagName === "SUMMARY",
    } : null;
    const status = selected ? (selected.pause_requested
      ? (detail?.resume_available ? "Paused" : "Pause requested")
      : WORKFLOW_STATUS_LABELS[selected.status] || selected.status)
      : "No run in this chat";
    const plan = detail?.plan || {};
    const structure = detail?.structure || [];
    const nodes = detail?.nodes || [];
    const currentQuestions = (detail?.questions || []).filter(question =>
      question.revision_id === selected?.revision_id && question.attempt_run_id === selected?.attempt_run_id);
    const pendingQuestions = currentQuestions.filter(question => question.status === "pending");
    const questionByIdentity = new Map(currentQuestions.map(question =>
      [JSON.stringify([question.site_id, question.instance_key]), question]));
    const questionNodeStatus = { pending: "waiting", answered: "waiting", expired: "failed", cancelled: "cancelled" };
    const projectedNodes = nodes.map(node => {
      const question = questionByIdentity.get(JSON.stringify([node.site_id, node.instance_key]));
      return question && !["succeeded", "failed", "skipped", "cancelled"].includes(node.status)
        ? { ...node, question_status: question.status } : node;
    });
    const nodeIdentities = new Set(projectedNodes.map(node => JSON.stringify([node.site_id, node.instance_key])));
    const questionNodes = currentQuestions.filter(question =>
      !nodeIdentities.has(JSON.stringify([question.site_id, question.instance_key]))
    ).map(question => ({
      site_id: question.site_id, instance_key: question.instance_key, kind: "ask",
      status: questionNodeStatus[question.status] || "unknown", question_status: question.status,
    }));
    const discoveredNodes = [...projectedNodes, ...questionNodes];
    const title = workflowDisplayTitle(plan.name || "Workflow run");
    const stopButton = selected && ["pending", "running", "waiting"].includes(selected.status)
      ? `<button class="btn danger small" type="button" data-workflow-action="stop" data-workflow-id="${esc(selected.id)}" data-revision-id="${esc(selected.revision_id)}">${icon("stop")} Stop workflow</button>` : "";
    const amendButton = selected && selected.status === "waiting" && detail?.attempt?.status === "waiting_workflow"
      && hutchSession?.principal === "owner"
      ? `<button class="btn ghost small" type="button" data-workflow-action="amend" data-workflow-id="${esc(selected.id)}">Amend parked run</button>` : "";
    const pauseButton = selected && detail?.pause_available && hutchSession?.principal === "owner"
      ? `<button class="btn ghost small" type="button" data-workflow-action="pause" data-workflow-id="${esc(selected.id)}">${detail.pause_after_work_available ? "Pause after current work" : "Pause workflow"}</button>` : "";
    const resumeButton = selected && detail?.resume_available && hutchSession?.principal === "owner"
      ? `<button class="btn ghost small" type="button" data-workflow-action="resume" data-workflow-id="${esc(selected.id)}">Resume workflow</button>` : "";
    const liveList = discoveredNodes.length ? `<ol class="workflow-step-list" aria-label="Discovered workflow instances">${discoveredNodes.map(node => {
      const label = structure.find(item => item.site_id === node.site_id)?.title || node.site_id;
      return `<li><span class="workflow-step-copy"><b title="${esc(label)}">${esc(label)}</b><span>${esc(node.instance_key)}</span></span><span class="workflow-step-status">${esc(workflowNodeLabel(node))}</span></li>`;
    }).join("")}</ol>` : `<p class="hint">No step instances have been created yet.</p>`;
    const plannedList = structure.length ? `<ol class="workflow-step-list workflow-planned-list" aria-label="Planned workflow structure">${structure.map(item =>
      `<li><span class="workflow-step-copy"><b title="${esc(item.title || item.site_id)}">${esc(item.title || item.site_id)}</b><span>${esc(item.kind || "step")}</span></span><span class="workflow-step-status">Planned</span></li>`
    ).join("")}</ol>` : `<p class="hint">This saved method has no compiled step outline.</p>`;
    const pendingQuestionLabel = `${pendingQuestions.length} pending question${pendingQuestions.length === 1 ? "" : "s"}`;
    const questionMarkup = pendingQuestions.map(question => `<form class="workflow-question" data-workflow-question-form data-question-id="${esc(question.id)}" aria-labelledby="workflow-question-title-${esc(question.id)} workflow-question-prompt-${esc(question.id)}">
      <p><b id="workflow-question-title-${esc(question.id)}">Question ${esc(question.id)}</b></p><p id="workflow-question-prompt-${esc(question.id)}">${esc(question.question)}</p>
      <label id="workflow-answer-label-${esc(question.id)}" for="workflow-answer-${esc(question.id)}">Your answer</label>
      <textarea id="workflow-answer-${esc(question.id)}" name="answer" rows="2" maxlength="4000" required aria-labelledby="workflow-question-title-${esc(question.id)} workflow-question-prompt-${esc(question.id)} workflow-answer-label-${esc(question.id)}" aria-describedby="workflow-answer-help-${esc(question.id)}"></textarea>
      <p class="hint" id="workflow-answer-help-${esc(question.id)}">This answer resolves only this question. It does not approve a separate action.</p>
      <button class="btn primary small" type="submit">Send answer</button><p class="workflow-question-error" role="status" aria-live="polite"></p>
    </form>`).join("");
    const savedList = definitions.length ? `<details data-workflow-disclosure="saved" ${oldDetails.has("saved") ? (oldDetails.get("saved") ? "open" : "") : ""}>
      <summary>Saved workflows <span class="hint">${definitions.length}</span></summary>
      <ul class="workflow-saved-list">${definitions.map(definition => `<li><span><b title="${esc(definition.name)}">${esc(definition.name)}</b><small>${definition.active ? "Active definition" : "Saved · run only when chosen"}</small></span>
        <button class="btn ghost small" type="button" data-workflow-action="start" data-workflow-id="${esc(definition.id)}">Run</button></li>`).join("")}</ul>
    </details>` : `<p class="hint">No saved workflows yet. Saving or importing a method does not activate it.</p>`;
    const disclosure = selected ? `<details class="workflow-inspector" data-workflow-disclosure="run" ${oldDetails.has("run") ? (oldDetails.get("run") ? "open" : "") : "open"}>
      <summary>Inspect workflow steps</summary>
      <div class="workflow-inspector-body">
        ${pendingQuestions.length ? `<section class="workflow-needs-you" aria-labelledby="workflow-questions-title"><h3 id="workflow-questions-title">Needs you <span class="workflow-pending-count">${esc(pendingQuestionLabel)}</span></h3>${questionMarkup}</section>` : ""}
        <section aria-labelledby="workflow-planned-title"><h3 id="workflow-planned-title">Planned structure</h3>${plannedList}</section>
        <section aria-labelledby="workflow-instances-title"><h3 id="workflow-instances-title">Discovered instances</h3>${liveList}</section>
        ${selected.reason ? `<p class="workflow-queue-reason"><b>Current reason:</b> ${esc(selected.reason)}</p>` : ""}
        <p class="hint">A completed step is not necessarily verified. Only an independent check is labelled Verified.</p>
      </div>
    </details>` : "";
    const markup = selected ? `<header class="workflow-panel-head"><div><p class="workflow-panel-kicker">Workflow activity</p>
      <h2 title="${esc(title)}">${esc(title)}</h2><p class="hint">${esc(status)}${selected?.definition_id ? " · saved workflow" : " · dynamic plan"}</p>
      ${selected.pause_requested && !detail?.resume_available ? `<p class="hint">Current work will settle before the next step is held.</p>` : ""}</div>
      <div class="workflow-panel-actions">${amendButton}${pauseButton}${resumeButton}${stopButton}<button class="btn ghost small" type="button" data-workflow-action="refresh">Refresh</button></div></header>
      <p class="workflow-panel-meta">${esc(discoveredNodes.length)} discovered ${discoveredNodes.length === 1 ? "instance" : "instances"} · workflow ${esc(selected.id)}</p>${disclosure}
      ${savedList}` : savedList;
    if (panel.innerHTML !== markup) {
      panel.innerHTML = markup;
      panel.hidden = false;
      panel.querySelectorAll("[data-workflow-question-form]").forEach(form => {
        const answer = $("textarea[name=answer]", form);
        if (answer && oldAnswerDrafts.has(form.dataset.questionId)) {
          answer.value = oldAnswerDrafts.get(form.dataset.questionId);
        }
      });
      panel.querySelectorAll("[data-workflow-action]").forEach(button => button.addEventListener("click", () => {
        if (button.dataset.workflowAction === "refresh") {
          void refreshWorkflowPanel(botName, conversationId, generation, true);
        } else if (button.dataset.workflowAction === "start") {
          void startSavedWorkflow(button.dataset.workflowId, button);
        } else if (button.dataset.workflowAction === "stop") {
          void stopWorkflowFromPanel(selected, button, botName, conversationId, generation);
        } else if (button.dataset.workflowAction === "pause" || button.dataset.workflowAction === "resume") {
          void setWorkflowPauseFromPanel(selected, button, button.dataset.workflowAction === "pause",
            botName, conversationId, generation);
        } else if (button.dataset.workflowAction === "amend") {
          void openWorkflowAmendment(selected, detail, button, botName, conversationId, generation);
        }
      }));
      panel.querySelectorAll("[data-workflow-question-form]").forEach(form => form.addEventListener("submit", event => {
        event.preventDefault();
        void answerWorkflowQuestion(form, botName, conversationId, generation);
      }));
      if (oldFocus) {
        const actionOrder = oldFocus.action === "pause" ? ["resume", "pause", "refresh"]
          : oldFocus.action === "resume" ? ["pause", "resume", "refresh"] : [oldFocus.action];
        const questionForms = [...panel.querySelectorAll("[data-workflow-question-form]")];
        const restoredQuestion = oldFocus.questionId
          ? questionForms.find(form => form.dataset.questionId === oldFocus.questionId)
          : null;
        const target = oldFocus.questionId
          ? (restoredQuestion?.querySelector("textarea[name=answer]")
            || questionForms[0]?.querySelector("textarea[name=answer]")
            || panel.querySelector('[data-workflow-action="refresh"]'))
          : oldFocus.summary && oldFocus.disclosure
          ? panel.querySelector(`details[data-workflow-disclosure="${CSS.escape(oldFocus.disclosure)}"] > summary`)
          : actionOrder.map(action => $$('[data-workflow-action]', panel).find(element =>
            element.dataset.workflowAction === action &&
            (action === "refresh" || element.dataset.workflowId === oldFocus.id))).find(Boolean);
        target?.focus({ preventScroll: true });
      }
    }
    panel.hidden = false;
  } catch (error) {
    if (token !== workflowPanelLoadToken || generation !== studioGeneration || conversationId !== currentConversationId) return;
    panel.hidden = false;
    const statusMessage = "Workflow activity could not be refreshed. Existing details are kept; use Refresh to retry.";
    if (panel.querySelector(".workflow-panel-head")) {
      let errorNotice = panel.querySelector("[data-workflow-refresh-error]");
      if (!errorNotice) {
        errorNotice = document.createElement("p");
        errorNotice.className = "workflow-panel-error";
        errorNotice.dataset.workflowRefreshError = "true";
        errorNotice.setAttribute("role", "status");
        errorNotice.setAttribute("aria-live", "polite");
        panel.querySelector(".workflow-panel-head").after(errorNotice);
      }
      errorNotice.textContent = statusMessage;
    } else {
      panel.innerHTML = `<p class="workflow-panel-error" role="status">${esc(statusMessage)} <button class="btn ghost small" type="button" data-workflow-action="refresh">Try again</button></p>`;
      panel.querySelector("[data-workflow-action=refresh]")?.addEventListener("click", () =>
        void refreshWorkflowPanel(botName, conversationId, generation, true));
    }
  }
}

function workflowAmendmentPreviewMarkup(preview, detail) {
  const allowedQuestionNodes = new Set((detail?.questions || [])
    .filter(question => question.status === "pending")
    .map(question => `${question.site_id}\u0000${question.instance_key}`));
  const carryNodes = preview.quiescence?.carry_active_nodes || [];
  const allowedCarryNodes = new Set(carryNodes.map(node => `${node.site_id}\u0000${node.instance_key}`));
  const drainedNodes = preview.quiescence?.drained_active_nodes || [];
  const allowedDrainedNodes = new Set(drainedNodes.map(node => `${node.site_id}\u0000${node.instance_key}`));
  const blockingActive = (preview.quiescence?.active_nodes || []).filter(node =>
    !allowedCarryNodes.has(`${node.site_id}\u0000${node.instance_key}`)
    && !allowedDrainedNodes.has(`${node.site_id}\u0000${node.instance_key}`)
    && (node.status !== "waiting" || !allowedQuestionNodes.has(`${node.site_id}\u0000${node.instance_key}`)));
  const drainableNodes = preview.quiescence?.drainable_active_nodes || [];
  const drainableMarkup = drainableNodes.map(node =>
    `<li><b>${esc(node.site_id)}</b> · ${esc(node.status)} · <code>${esc(node.run_id)}</code>${node.cancel_requested ? " · stop requested" : ""}<br><span class="hint">${esc(node.reason)}</span></li>`).join("");
  const drainedMarkup = drainedNodes.map(node =>
    `<li><b>${esc(node.site_id)}</b> · ${esc(node.status)} · <code>${esc(node.run_id)}</code> · ${esc(node.reason)}</li>`).join("");
  const pendingIds = preview.quiescence?.pending_question_ids || [];
  const changes = (preview.nodes || []).map(node => {
    const fields = (node.fields || []).map(change =>
      `<li><b>${esc(change.field)}</b><span>${esc(JSON.stringify(change.old ?? null))} to ${esc(JSON.stringify(change.new ?? null))}</span></li>`).join("");
    return `<li><b>${esc(node.site_id)}</b> · ${esc(node.change)}${node.dependencies_changed ? " · dependencies changed" : ""}${fields ? `<ul>${fields}</ul>` : ""}</li>`;
  }).join("");
  const changedFields = (preview.changed_fields || []).map(change =>
    `<li><b>${esc(change.field)}</b><span>${esc(JSON.stringify(change.old ?? null))} to ${esc(JSON.stringify(change.new ?? null))}</span></li>`).join("");
  const reused = (preview.reuse || []).map(item =>
    `<li><b>${esc(item.site_id)}</b> · ${esc(item.instance_key)} · ${esc(item.status)}</li>`).join("");
  const invalidated = (preview.invalidate || []).map(item =>
    `<li><b>${esc(item.site_id)}</b> · ${esc(item.instance_key)} · ${esc(item.reason)}</li>`).join("");
  const budgets = Object.entries(preview.budgets || {}).map(([name, budget]) =>
    `<li><b>${esc(name)}</b>: current ${esc(budget.current ?? "unset")}, proposed ${esc(budget.proposed ?? "unset")}, effective ${esc(budget.effective_if_adopted ?? "unset")}</li>`).join("");
  const roles = (preview.roles || []).map(role =>
    `<li><b>${esc(role.node || role.role || "Model role")}</b> · ${esc(role.state || (role.allowed ? "allowed" : "blocked"))}${role.profile ? ` · ${esc(role.profile)}` : ""}</li>`).join("");
  const carried = carryNodes.map(node =>
    `<li><b>${esc(node.site_id)}</b> · ${esc(node.role || "worker")} on ${esc(node.model || "recorded model")} · ${esc(node.status)} · <code>${esc(node.run_id)}</code><br><span class="hint">${esc(node.reason || "unchanged tool-free worker contract")}</span></li>`).join("");
  const blocked = preview.blocked_reasons || [];
  const canAdopt = workflowAmendmentCanAdopt(preview, detail);
  const readiness = preview.quiescence?.workflow_status !== "waiting"
    ? "This run is no longer parked. Refresh it before adopting an amendment."
    : !preview.quiescence?.attempt_parked
      ? "The orchestration attempt has not released its owner lease yet. Refresh after it parks."
      : blockingActive.length && drainableNodes.some(node => !node.cancel_requested)
        ? "The listed tool-free steps can be stopped explicitly after the workflow is paused. Their unfinished responses will be discarded; stopping work never undoes an external effect."
      : !preview.quiescence?.owned_work_quiet && !preview.quiescence?.owned_work_carryable
        ? "Owned child work or a process is still active and cannot be carried. Refresh after cleanup completes."
    : blockingActive.length
      ? `Owned work must settle first: ${blockingActive.map(node => `${node.site_id} (${node.status})`).join(", ")}.`
      : carryNodes.length
        ? "The unchanged tool-free step keeps its original contract; the new revision continues after that step settles."
        : "The run is parked and no other active step is recorded.";
  return `<section class="workflow-amendment-preview" aria-label="Amendment preview">
    <h4>Read-only preview</h4>
    <p class="${preview.eligible ? "" : "workflow-amendment-blocked"}" role="status">${preview.eligible ? "Candidate passes current authority and budget checks." : "Candidate is blocked."}</p>
    ${blocked.length ? `<ul>${blocked.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>` : ""}
    <p>${esc(readiness)}</p>
    <p>Candidate plan hash: <code>${esc(preview.candidate_plan_hash)}</code></p>
    <details open><summary>Changed fields · ${(preview.changed_fields || []).length}</summary><ul>${changedFields || "<li>No top-level field changes.</li>"}</ul></details>
    <details open><summary>Step changes · ${(preview.nodes || []).length}</summary><ul>${changes || "<li>No step structure changes.</li>"}</ul></details>
    <details><summary>Reusable completed results · ${(preview.reuse || []).length}</summary><ul>${reused || "<li>No results are reusable.</li>"}</ul></details>
    <details open><summary>Results to invalidate · ${(preview.invalidate || []).length}</summary><ul>${invalidated || "<li>No prior results need invalidation.</li>"}</ul></details>
    ${carryNodes.length ? `<details open><summary>Unchanged work to carry · ${carryNodes.length}</summary><p>The active step keeps its original model and execution contract. The new revision starts after it settles.</p><ul>${carried}</ul></details>` : ""}
    ${drainableNodes.length ? `<details open><summary>Affected tool-free steps · ${drainableNodes.length}</summary><p>Only children with no declared tools or owned descendants are listed. Stopping one discards its unfinished model response.</p><ul>${drainableMarkup}</ul>
      ${drainableNodes.some(node => !node.cancel_requested) && !detail?.workflow?.pause_requested
        ? '<p class="hint">Pause this workflow before stopping an affected step.</p>'
        : drainableNodes.some(node => !node.cancel_requested)
          ? '<button class="btn ghost small" type="button" id="workflow-amendment-drain">Stop affected steps</button>' : ""}</details>` : ""}
    ${drainedNodes.length ? `<details open><summary>Stopped affected steps · ${drainedNodes.length}</summary><p>These steps have reached a terminal state and their owned processes have drained. Their historical node records will be archived as cancelled.</p><ul>${drainedMarkup}</ul></details>` : ""}
    <details><summary>Effective budgets</summary><ul>${budgets}</ul></details>
    <details><summary>Model roles checked · ${(preview.roles || []).length}</summary><ul>${roles || "<li>No model role is required.</li>"}</ul></details>
    ${pendingIds.length ? `<div class="workflow-amendment-questions"><p>Pending questions that adoption would cancel:</p><ul>${pendingIds.map(id => `<li><code>${esc(id)}</code></li>`).join("")}</ul>
      <label><input type="checkbox" id="workflow-amendment-cancel-questions"> I understand these questions will be canceled and archived</label>
      <p class="hint">Adoption stays disabled until you select this choice.</p></div>` : ""}
    <p class="hint">Adoption archives the prior run state. The supervisor continues under a new revision; stale callbacks are rejected.</p>
    <button class="btn ghost small" type="button" id="workflow-amendment-preview-again">Revise candidate</button>
    ${canAdopt ? "" : "<p class=\"hint\">Adoption is unavailable until authority and run-state checks pass.</p>"}
  </section>`;
}

function workflowAmendmentCanAdopt(preview, detail) {
  const allowedQuestionNodes = new Set((detail?.questions || [])
    .filter(question => question.status === "pending")
    .map(question => `${question.site_id}\u0000${question.instance_key}`));
  const carryNodes = preview.quiescence?.carry_active_nodes || [];
  const allowedCarryNodes = new Set(carryNodes.map(node => `${node.site_id}\u0000${node.instance_key}`));
  const drainedNodes = preview.quiescence?.drained_active_nodes || [];
  const allowedDrainedNodes = new Set(drainedNodes.map(node => `${node.site_id}\u0000${node.instance_key}`));
  const blockingActive = (preview.quiescence?.active_nodes || []).some(node =>
    !allowedCarryNodes.has(`${node.site_id}\u0000${node.instance_key}`)
    && !allowedDrainedNodes.has(`${node.site_id}\u0000${node.instance_key}`)
    && (node.status !== "waiting" || !allowedQuestionNodes.has(`${node.site_id}\u0000${node.instance_key}`)));
  return preview.eligible && preview.quiescence?.workflow_status === "waiting"
    && preview.quiescence?.attempt_parked === true
    && (preview.quiescence?.owned_work_quiet === true || preview.quiescence?.owned_work_carryable === true)
    && !blockingActive;
}

async function openWorkflowAmendment(workflow, detail, trigger, botName, conversationId, generation) {
  if (hutchSession?.principal !== "owner" || workflow?.status !== "waiting"
      || detail?.attempt?.status !== "waiting_workflow" || !detail?.plan) return;
  const planText = JSON.stringify(detail.plan, null, 2);
  const inputsText = JSON.stringify(workflow.inputs || {}, null, 2);
  let reviewed = null;
  let busy = false;
  const payloadFromEditor = () => {
    const plan = JSON.parse($("#workflow-amendment-plan")?.value || "null");
    const inputs = JSON.parse($("#workflow-amendment-inputs")?.value || "null");
    if (!plan || typeof plan !== "object" || Array.isArray(plan)) throw new Error("Workflow plan must be a JSON object.");
    if (!inputs || typeof inputs !== "object" || Array.isArray(inputs)) throw new Error("Workflow inputs must be a JSON object.");
    return { expected_revision_id: workflow.revision_id, expected_generation: workflow.attempt_run_id, plan, inputs };
  };
  const updateAdoptionControl = () => {
    if (busy) return;
    const action = $("#modal-confirm");
    if (!action) return;
    if (!reviewed) { action.textContent = "Preview candidate"; action.disabled = false; return; }
    const pending = reviewed.preview.quiescence?.pending_question_ids || [];
    const cancelQuestions = $("#workflow-amendment-cancel-questions")?.checked === true;
    const canAdopt = workflowAmendmentCanAdopt(reviewed.preview, detail);
    action.textContent = canAdopt ? "Adopt amendment" : "Adoption unavailable";
    action.disabled = !canAdopt || (pending.length > 0 && !cancelQuestions);
  };
  const renderPreview = preview => {
    const result = $("#workflow-amendment-preview-result");
    result.innerHTML = workflowAmendmentPreviewMarkup(preview, detail);
    const modalAction = $("#modal-confirm");
    $("#workflow-amendment-cancel-questions")?.addEventListener("change", updateAdoptionControl);
    const previewButton = $("#workflow-amendment-preview-again", result);
    previewButton?.addEventListener("click", () => {
      reviewed = null;
      if (modalAction) modalAction.textContent = "Preview candidate";
      updateAdoptionControl();
      result.innerHTML = "";
      $("#workflow-amendment-status").textContent = "Edit the plan or inputs, then preview the candidate again.";
      $("#workflow-amendment-plan")?.focus({ preventScroll: false });
    });
    const drainButton = $("#workflow-amendment-drain", result);
    drainButton?.addEventListener("click", async () => {
      if (busy || !reviewed) return;
      busy = true;
      drainButton.disabled = true;
      const status = $("#workflow-amendment-status");
      if (status) status.textContent = "Requesting stops for the listed tool-free steps. Waiting for verified cleanup before adoption.";
      try {
        const drainBody = reviewed.body;
        const idemScope = "workflow-amendment-drain:" + workflow.id;
        const key = await messageIdempotencyKey(idemScope, drainBody);
        const response = await api("/v1/workflows/runs/" + encodeURIComponent(workflow.id) + "/amendments/drain", {
          method: "POST", headers: { "Idempotency-Key": key }, body: drainBody,
        });
        clearMessageIdempotencyKey(idemScope, key);
        let freshPreview = null;
        let drainVerified = false;
        for (let attempt = 0; attempt < 20; attempt += 1) {
          freshPreview = await api("/v1/workflows/runs/" + encodeURIComponent(workflow.id) + "/amendments/preview", {
            method: "POST", body: drainBody,
          });
          const drainedIds = new Set((freshPreview.quiescence?.drained_active_nodes || [])
            .map(node => node.run_id));
          const requestedIds = (response.requested || []).map(node => node.run_id);
          drainVerified = freshPreview.quiescence?.owned_work_quiet === true
            || requestedIds.length > 0 && requestedIds.every(runId => drainedIds.has(runId));
          if (drainVerified) break;
          await new Promise(resolve => setTimeout(resolve, 250));
        }
        reviewed.preview = freshPreview;
        renderPreview(freshPreview);
        if (status) status.textContent = drainVerified
          ? "Affected steps have stopped and their owned processes have drained. Review the updated preview before adopting."
          : response.message || "Stop requested. Refresh the preview after the owned processes have drained.";
        status?.focus({ preventScroll: false });
        updateAdoptionControl();
      } catch (error) {
        if (status) status.textContent = error.message || "Could not stop the affected steps.";
      } finally {
        busy = false;
        updateAdoptionControl();
      }
    });
  };
  openModal({
    title: `Amend ${detail.plan.name || workflow.definition_id || "workflow"}`,
    bodyHtml: `<p>Only parked runs can be amended here. Review the server-computed diff, authority and result reuse before adoption.</p>
      <p class="hint">This editor accepts declarative workflow JSON. Generated scripts are unsupported.</p>
      <label class="workflow-amendment-label" for="workflow-amendment-plan">Candidate workflow plan</label>
      <textarea id="workflow-amendment-plan" spellcheck="false" aria-describedby="workflow-amendment-plan-help">${esc(planText)}</textarea>
      <p id="workflow-amendment-plan-help" class="hint">The plan is validated and role authority is refreshed on preview and adoption.</p>
      <label class="workflow-amendment-label" for="workflow-amendment-inputs">Input snapshot</label>
      <textarea id="workflow-amendment-inputs" spellcheck="false">${esc(inputsText)}</textarea>
      <div id="workflow-amendment-preview-result"></div>
      <p class="workflow-amendment-error" id="workflow-amendment-status" role="status" aria-live="polite" tabindex="-1"></p>`,
    confirmText: "Preview candidate", confirmClass: "primary", wide: true, tall: true, returnFocus: trigger,
    onConfirm: async () => {
      if (busy) return false;
      const action = $("#modal-confirm");
      const status = $("#workflow-amendment-status");
      busy = true;
      action.disabled = true;
      if (!reviewed) {
        try {
          const body = payloadFromEditor();
          const preview = await api(`/v1/workflows/runs/${encodeURIComponent(workflow.id)}/amendments/preview`, {
            method: "POST", body,
          });
          reviewed = { body, preview };
          renderPreview(preview);
          const canAdopt = workflowAmendmentCanAdopt(preview, detail);
          action.textContent = canAdopt ? "Adopt amendment" : "Adoption unavailable";
          updateAdoptionControl();
          if (status) status.textContent = preview.eligible ? "Preview complete. Inspect every section before adoption." : "Preview complete with blocked checks.";
        } catch (error) {
          if (status) status.textContent = error.message || "Could not preview this candidate.";
        } finally {
          busy = false;
          updateAdoptionControl();
        }
        return false;
      }
      try {
        const freshBody = payloadFromEditor();
        if (JSON.stringify(freshBody) !== JSON.stringify(reviewed.body)) {
          reviewed = null;
          action.textContent = "Preview candidate";
          $("#workflow-amendment-preview-result").innerHTML = "";
          updateAdoptionControl();
          if (status) status.textContent = "Candidate changed. Run a fresh preview before adopting it.";
          return false;
        }
        if (!workflowAmendmentCanAdopt(reviewed.preview, detail)) {
          if (status) status.textContent = "Adoption is unavailable until authority passes and all owned work has settled.";
          return false;
        }
        const pending = reviewed.preview.quiescence?.pending_question_ids || [];
        const cancelQuestions = $("#workflow-amendment-cancel-questions")?.checked === true;
        if (pending.length && !cancelQuestions) {
          if (status) status.textContent = "Review and select the explicit question-cancellation choice before adoption.";
          return false;
        }
        const adoptionBody = { ...freshBody, cancel_pending_questions: cancelQuestions };
        const key = await messageIdempotencyKey(`workflow-amendment:${workflow.id}`, adoptionBody);
        const result = await api(`/v1/workflows/runs/${encodeURIComponent(workflow.id)}/amendments/adopt`, {
          method: "POST", headers: { "Idempotency-Key": key }, body: adoptionBody,
        });
        clearMessageIdempotencyKey(`workflow-amendment:${workflow.id}`, key);
        toast(`Amendment adopted. New revision ${result.revision_id} is running.`);
        await refreshWorkflowPanel(botName, conversationId, generation, true);
        return true;
      } catch (error) {
        if (error.status === 409 || error.status === 422 || error.status === 413) {
          reviewed = null;
          action.textContent = "Preview candidate";
          $("#workflow-amendment-preview-result").innerHTML = "";
        }
        if (status) status.textContent = error.message || "Amendment adoption was not confirmed.";
        return false;
      } finally {
        busy = false;
        if (action.isConnected) updateAdoptionControl();
      }
    },
  });
  $(".modal-card", $("#modal-root"))?.classList.add("workflow-amendment-modal");
  for (const selector of ["#workflow-amendment-plan", "#workflow-amendment-inputs"]) {
    $(selector)?.addEventListener("input", () => {
      if (!reviewed) return;
      reviewed = null;
      const action = $("#modal-confirm");
      if (action) action.textContent = "Preview candidate";
      updateAdoptionControl();
      $("#workflow-amendment-preview-result").innerHTML = "";
      $("#workflow-amendment-status").textContent = "Candidate changed. Run a fresh preview before adopting it.";
    });
  }
}

async function startSavedWorkflow(definitionId, trigger) {
  try {
    const saved = await api(`/v1/workflows/${encodeURIComponent(definitionId)}`);
    const plan = saved.plan || {};
    const inputs = plan.inputs || {};
    const entries = Object.entries(inputs);
    const fields = entries.map(([name, spec]) => {
      const value = spec.default === undefined || spec.default === null ? "" :
        typeof spec.default === "string" ? spec.default : JSON.stringify(spec.default);
      const placeholder = spec.required && !value ? `Enter a ${spec.type || "string"} value` : value;
      const hint = spec.description ? `<span class="hint">${esc(spec.description)}</span>` : "";
      return `<label class="field">${esc(name)}${spec.required ? " · required" : " · optional"}
        <textarea data-workflow-input="${esc(name)}" data-workflow-type="${esc(spec.type || "string")}" rows="2" maxlength="20000" placeholder="${esc(placeholder)}">${esc(value)}</textarea>${hint}</label>`;
    }).join("");
    openModal({
      title: `Run ${plan.name || definitionId}`,
      bodyHtml: `<p>Starting this saved workflow is an explicit action. Its plan and permissions are checked again before admission.</p>
        ${fields || '<p class="hint">This workflow does not require inputs.</p>'}
        <p class="workflow-question-error" id="workflow-start-error" role="alert"></p>`,
      confirmText: "Start workflow", confirmClass: "primary", wide: true, tall: entries.length > 4,
      returnFocus: trigger,
      onConfirm: async () => {
        const values = {};
        try {
          for (const field of $$("[data-workflow-input]")) {
            const raw = field.value;
            if (!raw.trim() && !inputs[field.dataset.workflowInput]?.required) continue;
            if (!raw.trim()) throw new Error(`${field.dataset.workflowInput} is required.`);
            switch (field.dataset.workflowType) {
              case "string": values[field.dataset.workflowInput] = raw; break;
              case "boolean":
              case "number":
              case "integer":
              case "array":
              case "object": values[field.dataset.workflowInput] = JSON.parse(raw); break;
              default: throw new Error(`Unsupported input type: ${field.dataset.workflowType}`);
            }
          }
          const payload = { bot: currentStudioBot, conversation_id: currentConversationId, inputs: values };
          const key = await messageIdempotencyKey(`workflow-start:${currentConversationId}:${definitionId}`, payload);
          const result = await api(`/v1/workflows/${encodeURIComponent(definitionId)}/runs`, {
            method: "POST", headers: { "Idempotency-Key": key }, body: payload,
          });
          clearMessageIdempotencyKey(`workflow-start:${currentConversationId}:${definitionId}`, key);
          currentRunId = result.attempt_run_id;
          subscribeRun(result.attempt_run_id);
          toast("Workflow started. Its progress and checks are available here.");
          void refreshWorkflowPanel(currentStudioBot, currentConversationId, studioGeneration, true);
          return true;
        } catch (error) {
          const status = $("#workflow-start-error");
          if (status) status.textContent = error.message;
          return false;
        }
      },
    });
  } catch (error) {
    toast(`Could not open this saved workflow: ${error.message}`, true);
  }
}

async function stopWorkflowFromPanel(workflow, button, botName, conversationId, generation) {
  if (!workflow?.id || button.disabled) return;
  button.disabled = true;
  const body = { expected_revision_id: workflow.revision_id };
  try {
    const key = await messageIdempotencyKey(`workflow-stop:${workflow.id}`, body);
    await api(`/v1/workflows/runs/${encodeURIComponent(workflow.id)}/stop`, {
      method: "POST", headers: { "Idempotency-Key": key }, body,
    });
    clearMessageIdempotencyKey(`workflow-stop:${workflow.id}`, key);
    toast("Stop requested. Hutch will keep the workflow visible until owned work is settled.");
    await refreshWorkflowPanel(botName, conversationId, generation, true);
  } catch (error) {
    button.disabled = false;
    toast(`Workflow stop was not confirmed: ${error.message}`, true);
  }
}

async function setWorkflowPauseFromPanel(workflow, button, paused, botName, conversationId, generation) {
  if (!workflow?.id || !workflow.attempt_run_id || button.disabled) return;
  const panel = $("#workflow-panel");
  button.disabled = true;
  const body = { expected_revision_id: workflow.revision_id, expected_generation: workflow.attempt_run_id };
  const action = paused ? "pause" : "resume";
  const operation = `workflow-${action}:${workflow.id}`;
  try {
    const key = await messageIdempotencyKey(operation, body);
    const result = await api(`/v1/workflows/runs/${encodeURIComponent(workflow.id)}/${action}`, {
      method: "POST", headers: { "Idempotency-Key": key }, body,
    });
    clearMessageIdempotencyKey(operation, key);
    announce(paused
      ? result.parked ? "Workflow paused. Its waiting questions and results remain available."
        : "Pause requested. Current work will settle before the next step is held."
      : "Workflow resumed. It will continue when its remaining work is ready.");
    await refreshWorkflowPanel(botName, conversationId, generation, true);
    if (generation === studioGeneration && conversationId === currentConversationId) {
      const nextAction = paused && result.parked ? "resume" : "refresh";
      panel?.querySelector(`[data-workflow-action="${nextAction}"]`)?.focus({ preventScroll: true });
    }
  } catch (error) {
    button.disabled = false;
    if (error.status === 409) {
      await refreshWorkflowPanel(botName, conversationId, generation, true);
      if (generation === studioGeneration && conversationId === currentConversationId) {
        toast(`Workflow ${action} was not applied because its state changed. The latest status is loaded; review it before trying again.`, true);
      }
      return;
    }
    toast(`Workflow ${action} was not confirmed: ${error.message}`, true);
  }
}

async function answerWorkflowQuestion(form, botName, conversationId, generation) {
  if (form.dataset.submitting === "1") return;
  const questionId = form.dataset.questionId;
  const answer = $("textarea[name=answer]", form)?.value.trim() || "";
  const errorNode = $(".workflow-question-error", form);
  if (!answer) { if (errorNode) errorNode.textContent = "Enter an answer first."; return; }
  form.dataset.submitting = "1";
  const button = $("[type=submit]", form);
  button.disabled = true;
  try {
    const body = { answer };
    const key = await messageIdempotencyKey(`workflow-question:${questionId}`, body);
    await api(`/v1/workflows/questions/${encodeURIComponent(questionId)}/answer`, {
      method: "POST", headers: { "Idempotency-Key": key }, body,
    });
    clearMessageIdempotencyKey(`workflow-question:${questionId}`, key);
    announce(`Answer sent for workflow question ${questionId}.`);
    $("#workflow-panel")?.scrollTo({ top: 0, behavior: "auto" });
    await refreshWorkflowPanel(botName, conversationId, generation, true);
    const refreshedPanel = $("#workflow-panel");
    const nextAnswer = refreshedPanel?.querySelector("[data-workflow-question-form] textarea[name=answer]");
    (nextAnswer || refreshedPanel?.querySelector('[data-workflow-action="refresh"]'))?.focus({ preventScroll: true });
  } catch (error) {
    if (errorNode) errorNode.textContent = error.message;
    button.disabled = false;
  } finally {
    if (form.isConnected) form.dataset.submitting = "";
  }
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
      if (!append) {
        const docsPage = await api(`/v1/documents?conversation_id=${encodeURIComponent(conversationId)}&limit=50`);
        if (!$("#conversation-files-list")) return;
        const docs = (docsPage.documents || []).map(documentListRowRef).filter(Boolean);
        list.insertAdjacentHTML("afterbegin", docs.map(documentCardHtml).join(""));
        count += docs.length;
      }
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
  if (isError) el.setAttribute("role", "alert");
  el.innerHTML = `<span class="toast-msg">${esc(msg)}</span>
    <button class="toast-close" aria-label="Dismiss notification">${icon("x")}</button>`;
  const dismiss = () => el.remove();
  el.querySelector(".toast-close").addEventListener("click", dismiss);
  root.appendChild(el);
  // Transient notices auto-dismiss; errors persist until dismissed. Longer notices
  // stay longer (5s plus ~1s per 15 words), and the countdown waits while the
  // notice is hovered or focused so people can finish reading it.
  if (isError) return;
  const readingTime = 5000 + Math.floor(String(msg).length / 90) * 1000;
  let timer = setTimeout(dismiss, readingTime);
  const hold = () => clearTimeout(timer);
  const resume = () => { if (!el.matches(":hover, :focus-within")) { clearTimeout(timer); timer = setTimeout(dismiss, readingTime / 2); } };
  // A notice that appears under a resting pointer still times out; moving onto it holds it.
  el.addEventListener("pointermove", ev => { if (ev.movementX || ev.movementY) hold(); });
  el.addEventListener("focusin", hold);
  el.addEventListener("pointerleave", resume);
  el.addEventListener("focusout", resume);
}

// The local OAuth callback redirects to the Connections view with a short-lived
// status only. Remove it from browser history before rendering the page.
const chatgptCallback = new URLSearchParams(location.search);
const chatgptResult = chatgptCallback.get("chatgpt_result");
const googleCalendarResult = chatgptCallback.get("google_calendar_result");
const googleWorkspaceResult = chatgptCallback.get("google_workspace_result");
const notionResult = chatgptCallback.get("notion_result");
const googleMailResult = chatgptCallback.get("google_mail_result");
const googleMailSendResult = chatgptCallback.get("google_mail_send_result");
const outlookCalendarResult = chatgptCallback.get("outlook_calendar_result");
const outlookCalendarWriteResult = chatgptCallback.get("outlook_calendar_write_result");
const outlookMailResult = chatgptCallback.get("outlook_mail_result");
const outlookMailSendResult = chatgptCallback.get("outlook_mail_send_result");
if (chatgptResult || notionResult || googleWorkspaceResult || googleCalendarResult || googleMailResult || googleMailSendResult || outlookCalendarResult || outlookCalendarWriteResult || outlookMailResult || outlookMailSendResult) {
  const detail = chatgptCallback.get("detail");
  const message = notionResult
    ? notionResult === "connected" ? "Notion connected. Choose an assistant and review its read access in Apps & AI."
      : detail || "Notion sign-in did not complete. Try again from Apps & AI."
    : googleWorkspaceResult
    ? googleWorkspaceResult === "connected" ? "Google Drive, Docs and Sheets connected. Workspace actions still need exact plan approval."
      : detail || "Google Workspace sign-in did not complete. Try again from Apps & AI."
    : googleMailSendResult
    ? googleMailSendResult === "connected" ? "Gmail send-only account connected. Grant one assistant permission to prepare messages; each send still needs your approval."
      : detail || "Gmail send-only sign-in did not complete. Start again from Connections."
    : outlookMailSendResult
    ? outlookMailSendResult === "connected" ? "Outlook Mail sending account connected. Grant one Bot sending access from Connections."
      : detail || "Outlook Mail sign-in did not complete. Start again from Connections."
    : outlookMailResult
    ? outlookMailResult === "connected" ? "Outlook Mail account connected. Grant one Bot read access from Connections."
      : detail || "Outlook Mail sign-in did not complete. Start again from Connections."
    : googleMailResult
    ? googleMailResult === "connected" ? "Gmail account connected. Grant one Local-inference Bot search access from Connections."
      : detail || "Gmail sign-in did not complete. Start again from Connections."
    : outlookCalendarWriteResult
    ? outlookCalendarWriteResult === "connected" ? "Outlook event-creation account connected. Choose one calendar and grant one assistant permission to create events after your approval."
      : detail || "Outlook event-creation sign-in did not complete. Start again from Connections."
    : outlookCalendarResult
    ? outlookCalendarResult === "connected" ? "Outlook Calendar account connected. Choose a calendar and grant one Bot read access from Connections."
      : detail || "Outlook Calendar sign-in did not complete. Start again from Connections."
    : googleCalendarResult
    ? googleCalendarResult === "connected" ? "Google Calendar account connected. Choose a calendar and grant one Bot read access from Connections."
      : detail || "Google Calendar sign-in did not complete. Start again from Connections."
    : chatgptResult === "connected" ? "ChatGPT plan route connected."
    : chatgptResult === "identity-only" ? "ChatGPT signed in, but plan use was not granted. Reauthorize to use it for models."
    : detail || "ChatGPT sign-in did not complete. Start again from Connections.";
  setTimeout(() => toast(message, notionResult === "error" || googleWorkspaceResult === "error" || chatgptResult === "error" || googleCalendarResult === "error" || googleMailResult === "error" || outlookCalendarResult === "error" || outlookCalendarWriteResult === "error" || outlookMailResult === "error" || outlookMailSendResult === "error"), 0);
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

function fmtUsd(value) {
  if (value === null || value === undefined) return "unknown";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "unknown";
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 9,
  }).format(amount);
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
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
  sparkles: '<path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Z"/><path d="m19 14 1.1 3L23 18l-2.9 1.1L19 22l-1.1-2.9L15 18l2.9-1.1L19 14Z"/>',
  cloud: '<path d="M20 16.2A4.5 4.5 0 0 0 18 7.5a6.5 6.5 0 0 0-12.4 2.2A4 4 0 0 0 6 17.5h12"/>',
  monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
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
  return `<svg class="icon ${esc(cls)}" data-icon="${esc(name)}" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICON_PATHS[name] || ""}</svg>`;
}

const BRAND_MARK_FILES = {
  openai: "openai-white-monoblossom.svg",
  anthropic: "anthropic-symbol-ivory.svg",
  openrouter: "openrouter-glyph-volt.svg",
  calendar: "google-calendar-2026q2.png",
  gmail: "google-gmail-2026q2.png",
  outlook: "microsoft-outlook.svg",
  notion: "notion.ico",
  drive: "google-drive.svg",
  docs: "google-docs.svg",
  sheets: "google-sheets.svg",
};
const TEMPLATE_MARKS = {
  "openai-api": "openai",
  "anthropic-api": "anthropic",
  "openrouter": "openrouter",
  "chatgpt-plan": "openai",
};

function providerLogo(mark, size = "") {
  const file = BRAND_MARK_FILES[mark];
  if (!file) return "";
  return `<span class="provider-logo provider-logo-${esc(mark)} ${size ? `provider-logo-${esc(size)}` : ""}" aria-hidden="true"><img src="/static/brands/${esc(file)}" alt=""></span>`;
}

function providerLogoForTemplate(template, size = "") {
  return providerLogo(TEMPLATE_MARKS[template] || "", size);
}

// Brand marks stay local and retain their original colours and proportions.
function serviceMark(kind) {
  const brand = kind === "chatgpt" ? "openai" : kind;
  if (BRAND_MARK_FILES[brand]) {
    return `<span class="service-mark service-mark-${esc(kind)}" data-service-category="${esc(kind)}" aria-hidden="true">${providerLogo(brand)}</span>`;
  }
  const serviceIcons = {
    calendar: "calendar",
    gmail: "mail",
    outlook: "inbox",
    hosted: "cloud",
    local: "monitor",
    drive: "folder",
    phone: "monitor",
  };
  const glyph = serviceIcons[kind] || "sparkles";
  return `<span class="service-mark service-mark-${esc(kind)}" data-service-category="${esc(kind)}" aria-hidden="true">${icon(glyph, "service-glyph")}</span>`;
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
   one brand-family colour and a pair of simple, shape-fitted eyes.
   This family belongs to the operator app; the marketing site keeps its
   detailed 3D artwork. Identity never encodes status. */
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
// Paired eyes follow each silhouette's usable face area. The compact organic
// ovals sit directly on the colour: no visor, slit marks, pupils, or highlights.
// Their slight inward tilt and near-matched size keep the family friendly while
// the shape-specific height and spacing keep the faces from becoming stamps.
const ID_FACES = [
  [[24.7, 30, 4.05, 4.55, -8], [39.2, 29.3, 4.05, 4.55, 8]], // orb
  [[25.2, 29.6, 3.9, 4.45, -8], [38.8, 29.2, 3.9, 4.45, 8]], // capsule
  [[24.9, 30.8, 3.95, 4.45, -10], [39, 30, 3.95, 4.45, 10]], // bean
  [[25.3, 36.7, 3.85, 4.35, -8], [38.8, 36.1, 3.85, 4.35, 8]], // drop
  [[24.5, 30.9, 4, 4.5, -9], [39.3, 30.1, 4, 4.5, 9]], // pebble
  [[24.8, 31.4, 3.8, 4.3, -7], [39.1, 30.8, 3.8, 4.3, 7]], // shield
  [[27, 37.4, 3.75, 4.25, -8], [38.3, 36.9, 3.75, 4.25, 8]], // triangle
  [[24.5, 31.8, 3.95, 4.45, -9], [39.3, 31, 3.95, 4.45, 9]], // hex
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
  const [left, right] = ID_FACES[shapeIndex] || ID_FACES[0];
  const eye = (name, [cx, cy, rx, ry, angle]) => {
    const transform = "rotate(" + angle + " " + cx + " " + cy + ")";
    const metadata = 'data-cx="' + cx + '" data-cy="' + cy + '" data-rx="' + rx + '" data-ry="' + ry + '" data-angle="' + angle + '"';
    const k = .55228475;
    const d = `M${cx} ${cy - ry}C${cx + rx * k} ${cy - ry} ${cx + rx} ${cy - ry * k} ${cx + rx} ${cy}C${cx + rx} ${cy + ry * k} ${cx + rx * k} ${cy + ry} ${cx} ${cy + ry}C${cx - rx * k} ${cy + ry} ${cx - rx} ${cy + ry * k} ${cx - rx} ${cy}C${cx - rx} ${cy - ry * k} ${cx - rx * k} ${cy - ry} ${cx} ${cy - ry}Z`;
    return '<path data-sigil-eye="' + name + '" data-contrast-ink="#0b1511" d="' + d + '" ' + metadata + ' transform="' + transform + '" fill="#0b1511" aria-hidden="true"/>';
  };
  return '<g aria-hidden="true">' + eye("left", left) + eye("right", right) + '</g>';
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

function botActionSummary(mode) {
  if (mode === "ask") return "Checks with you before actions";
  if (mode === "auto") return "Uses actions you approved";
  if (mode === "deny_all") return "Actions turned off";
  return "Action settings";
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
    else if (modalReturnFocus?.dataset.notionAccess) {
      ($$('[data-notion-access]').find(button => button.dataset.notionAccess === modalReturnFocus.dataset.notionAccess) || $('#notion-connect') || $('#nav-toggle'))?.focus();
    }
    else if (modalReturnFocus?.dataset.backgroundProvider) {
      ($$('[data-background-provider]').find(button =>
        button.dataset.backgroundProvider === modalReturnFocus.dataset.backgroundProvider) || $('#nav-toggle'))?.focus();
    }
    else if (modalReturnFocus?.dataset.workflowAction && modalReturnFocus?.dataset.workflowId) {
      ($$('[data-workflow-action]').find(button =>
        button.dataset.workflowAction === modalReturnFocus.dataset.workflowAction &&
        button.dataset.workflowId === modalReturnFocus.dataset.workflowId) || $('#chat-prompt'))?.focus();
    }
    else if (modalReturnFocus?.dataset.workflowSuggestionRun) {
      ($$('[data-workflow-suggestion-run]').find(button =>
        button.dataset.workflowSuggestionRun === modalReturnFocus.dataset.workflowSuggestionRun) || $('#chat-prompt'))?.focus();
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
let firstRunOpenCodeStatus = null;
let firstRunSelection = null;
let firstRunReadinessState = "checking";
let firstRunReadinessPromise = null;
let firstRunReadinessGeneration = 0;
let firstRunSubmitGeneration = 0;
let rosterMenuCleanup = null;

function closeRosterActionMenu(restoreFocus = false) {
  const menu = document.getElementById("roster-action-menu");
  const name = menu?.dataset.botName;
  const cleanup = rosterMenuCleanup;
  rosterMenuCleanup = null;
  cleanup?.();
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
        <p class="hint">Provider URLs, local folders, schedules, memory values, and chat history are excluded. A folder-based assistant becomes a managed workspace in the template. Instructions and enabled tools are included, so check them for private details before sharing.</p>
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
    <button type="button" role="menuitem" tabindex="-1" data-menu-duplicate>${icon("bot")} Duplicate assistant</button>
    ${bot.is_workspace_coordinator ? "" : `<button type="button" role="menuitem" tabindex="-1" data-menu-hide>${icon(bot.sidebar_hidden ? "eye" : "eyeOff")} ${bot.sidebar_hidden ? "Show in sidebar" : "Hide from sidebar"}</button>`}
    <a role="menuitem" tabindex="-1" data-menu-settings href="#/bot/${encodeURIComponent(bot.name)}">${icon("sliders")} Assistant settings</a>`;
  document.body.append(menu);
  const popup = window.hutchControls.popup({ trigger, panel: menu, kind: "menu",
    onClose: () => closeRosterActionMenu(false) });
  rosterMenuCleanup = () => popup.destroy();
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
  popup.open();
}

function botDisplayName(ref) {
  if (ref && typeof ref === "object") return ref.display_name || ref.bot_display_name || ref.name || "Bot";
  return botsCache.find(bot => bot.name === ref || bot.id === ref)?.display_name || ref || "Bot";
}

function botIdentityParts(ref) {
  const bot = ref && typeof ref === "object" ? ref
    : botsCache.find(item => item.name === ref || item.id === ref);
  const fullName = bot?.display_name || bot?.bot_display_name || bot?.name || ref || "Bot";
  const parts = String(fullName).split(" · ");
  return parts.length > 1
    ? { name: parts.slice(0, -1).join(" · "), role: parts.at(-1) || bot?.description || "" }
    : { name: String(fullName), role: bot?.description || "" };
}

function botHeading(ref) { return botIdentityParts(ref).name; }
function botRole(ref) { return botIdentityParts(ref).role; }

let assistantSetupPage = null;
let assistantSetupGeneration = 0;

window.addEventListener("pagehide", () => assistantSetupPage?.persist());

async function renderAssistantSetupPage() {
  if (!assistantSetupPage) {
    setTopContext(`<div class="ctx-id"><div class="ctx-heading"><h1>New assistant</h1><span class="ctx-subtitle">Set up an assistant without starting work</span></div></div>`);
    view.innerHTML = `<div class="page-scroll"><div class="container"><p role="status">Loading assistant setup…</p></div></div>`;
    await promptNewBot("", "", null, loadAssistantSetupDraft() ? "" : loadFirstRunDraft());
    return;
  }
  setTopContext(`<div class="ctx-id"><h1>New assistant</h1></div>`);
  view.replaceChildren(assistantSetupPage.element);
  await assistantSetupPage.render();
}

const routes = [
  [/^#\/assistant\/new$/, renderAssistantSetupPage, "bots"],
  [/^#\/chat(?:\/([\w-]+))?$/, m => renderChatStudio(m ? m[1] : null), "chat"],
  [/^#\/conversation\/([\w-]+)$/, m => openConversation(m[1]), "chat"],
  [/^#\/chats$/, renderChatLibrary, "chats"],
  [/^#\/settings$/, renderWorkspaceSettings, "settings"],
  [/^#\/overview$/, renderOverview, "overview"],
  [/^#\/schedules$/, renderSchedules, "schedules"],
  [/^#\/runtime$/, renderRuntime, "runtime"],
  [/^#\/bots$/, renderBots, "bots"],
  [/^#\/runs(?:\?(.*))?$/, m => renderRuns(m ? m[1] : ""), "runs"],
  [/^#\/skills$/, () => window.hutchSkills.renderSkillsPage(), "skills"],
  [/^#\/approvals$/, renderApprovals, "chat"],
  [/^#\/connections(?:\?.*)?$/, renderConnections, "connections"],
  [/^#\/bot\/([\w-]+)$/, m => renderBotDetail(decodeURIComponent(m[1])), "chat"],
  [/^#\/run\/([\w-]+)(?:\?(.*))?$/, m => renderRunDetail(m[1], new URLSearchParams(m ? m[2] || "" : "")), "runs"],
];

async function openConversation(id) {
  const conversation = await api(`/v1/conversations/${encodeURIComponent(id)}`);
  const bots = await api("/bots");
  const bot = bots.find(b => b.id === conversation.bot_id);
  if (!bot) throw new Error("This conversation's assistant is no longer available. Its history is retained in run history.");
  storageSet(`hutch-conversation:${bot.id}`, id);
  history.replaceState(null, "", `#/conversation/${encodeURIComponent(id)}`);
  await renderChatStudio(bot.name, id);
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
          <input id="message-search-query" type="search" maxlength="256" autocomplete="off" spellcheck="false" enterkeyhint="search"
            aria-describedby="message-search-scope" placeholder="Search words or a phrase" />
        </label>
        <label class="field message-search-bot-filter" for="message-search-bot">Bot
          <select id="message-search-bot"><option value="">All Bots</option>${botOptions}</select>
        </label>
      </div>
      <p class="hint message-search-scope" id="message-search-scope">Search covers active chats. Archived and imported history stays out of results.</p>
      <p class="message-search-status" id="message-search-status" role="status" aria-live="polite">Type at least two characters to search.</p>
      <div class="message-search-results" id="message-search-results" role="group" aria-label="Search results"></div>
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

function formatConversationDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : new Intl.DateTimeFormat(undefined,
    { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

async function renderChatLibrary() {
  const generation = ++studioGeneration;
  const bots = await api("/bots");
  if (generation !== studioGeneration) return;
  botsCache = bots;
  renderRoster();
  setTopContext(`<div class="ctx-id"><div class="ctx-heading"><h1>Chat library</h1><span class="ctx-subtitle">Find active, archived, and imported conversations</span></div></div>`);
  view.innerHTML = `<div class="page-scroll"><div class="container chat-library-page">
    <p class="page-subtitle">Browse conversation titles across your assistants. Message search remains in Chats.</p>
    <form class="panel chat-library-filters" id="chat-library-filters" role="search">
      <label class="field"><span>Find by chat title</span><input id="chat-library-query" type="search" maxlength="256" autocomplete="off" placeholder="For example, project notes"></label>
      <label class="field"><span>Assistant</span><select id="chat-library-bot"><option value="">All assistants</option>${bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("")}</select></label>
      <label class="field"><span>Show</span><select id="chat-library-scope"><option value="active">Active chats</option><option value="archived">Archived chats</option><option value="imported">Imported history</option><option value="all">Everything</option></select></label>
      <button class="btn primary" type="submit">Find chats</button>
    </form>
    <p class="hint" id="chat-library-status" role="status" aria-live="polite">Choose a filter to browse conversations.</p>
    <section class="chat-library-results" id="chat-library-results" aria-label="Conversation results"></section>
    <div class="btn-row chat-library-pagination" id="chat-library-pagination"></div>
  </div></div>`;
  const form = $("#chat-library-filters");
  const query = $("#chat-library-query");
  const bot = $("#chat-library-bot");
  const scope = $("#chat-library-scope");
  const status = $("#chat-library-status");
  const results = $("#chat-library-results");
  const pagination = $("#chat-library-pagination");
  let offset = 0;
  let requestGeneration = 0;
  const pageSize = 50;
  const load = async (nextOffset = 0) => {
    const request = ++requestGeneration;
    offset = nextOffset;
    status.textContent = "Loading chats…";
    results.setAttribute("aria-busy", "true");
    try {
      const page = await api("/v1/conversations/query", { method: "POST", body: {
        q: query.value.trim(), bot: bot.value || null, scope: scope.value, limit: pageSize, offset,
      }});
      if (!form.isConnected || request !== requestGeneration) return;
      const labels = new Map(bots.map(item => [item.id, item.display_name || item.name]));
      results.innerHTML = page.items.length ? page.items.map(item => `<a class="chat-library-row" href="#/conversation/${esc(item.id)}">
        <span class="chat-library-copy"><strong>${esc(item.title || "Untitled conversation")}</strong><small>${esc(labels.get(item.bot_id) || "Unavailable assistant")} · ${esc(formatConversationDate(item.updated_at))}</small></span>
        <span class="chat-library-meta">${item.is_legacy ? "Imported" : item.archived ? "Archived" : `${item.message_count} messages`} ${icon("arrow")}</span>
      </a>`).join("") : `<div class="empty-state"><p>Try another assistant, title, or history bucket.</p></div>`;
      const first = page.total ? offset + 1 : 0;
      status.textContent = page.total ? `Showing ${first}–${offset + page.items.length} of ${page.total} chats.` : "No chats found.";
      pagination.innerHTML = `${offset ? '<button class="btn ghost" type="button" data-library-page="previous">Previous</button>' : ""}${page.next_offset !== null ? '<button class="btn ghost" type="button" data-library-page="next">Load more</button>' : ""}`;
      pagination.querySelector('[data-library-page="previous"]')?.addEventListener("click", () => void load(Math.max(0, offset - pageSize)));
      pagination.querySelector('[data-library-page="next"]')?.addEventListener("click", () => void load(page.next_offset));
    } catch (error) {
      if (!form.isConnected || request !== requestGeneration) return;
      results.innerHTML = "";
      pagination.innerHTML = "";
      status.textContent = `Chat library unavailable: ${error.message}`;
    } finally {
      if (request === requestGeneration) results.removeAttribute("aria-busy");
    }
  };
  form.addEventListener("submit", event => { event.preventDefault(); void load(); });
  scope.addEventListener("change", () => void load());
  bot.addEventListener("change", () => void load());
  await load();
}

async function renderWorkspaceSettings() {
  const defaults = await api("/v1/preferences/model-defaults");
  const currentEffects = storageGet("hutch:reduce-effects");
  setTopContext(`<div class="ctx-id"><div class="ctx-heading"><h1>Settings</h1><span class="ctx-subtitle">Workspace defaults and appearance</span></div></div>`);
  view.innerHTML = `<div class="page-scroll"><div class="container workspace-settings-page">
    <p class="page-subtitle">These defaults apply when you create an assistant. Existing assistants and chats keep their saved settings.</p>
    <form class="panel form-grid workspace-settings-form" id="workspace-settings-form">
      <h3 class="panel-title">Model defaults for new assistants</h3>
      <label class="field" for="workspace-settings-model">Default model route
        <input id="workspace-settings-model" type="text" maxlength="200" autocomplete="off" placeholder="Choose or enter provider/model" value="${esc(defaults.model || "")}">
        <span class="hint">Leave empty to choose a route for each new assistant.</span></label>
      <label class="field" for="workspace-settings-mode">Default routing
        <select id="workspace-settings-mode"><option value="hybrid" ${defaults.inference_mode === "hybrid" ? "selected" : ""}>Hybrid — local or hosted</option><option value="local" ${defaults.inference_mode === "local" ? "selected" : ""}>Local — this machine</option><option value="offline" ${defaults.inference_mode === "offline" ? "selected" : ""}>Strict Offline — host-gated</option></select></label>
      <p class="hint">Hosted routes send prompts to their provider. Local routing keeps inference on this machine while tools may still use the network.</p>
      <h3 class="panel-title">Appearance</h3>
      <label class="field" for="workspace-settings-effects">Effects
        <select id="workspace-settings-effects"><option value="system" ${currentEffects === null ? "selected" : ""}>Follow system setting</option><option value="reduce" ${currentEffects === "true" ? "selected" : ""}>Reduce effects</option><option value="full" ${currentEffects === "false" ? "selected" : ""}>Show effects</option></select>
        <span class="hint">The dark workspace theme is fixed. This only controls nonessential motion.</span></label>
      <div class="btn-row"><button class="btn primary" type="submit">Save workspace settings</button><a class="btn ghost" href="#/connections">Apps &amp; AI</a></div>
      <p id="workspace-settings-status" class="hint" role="status" aria-live="polite"></p>
    </form>
  </div></div>`;
  $("#workspace-settings-form")?.addEventListener("submit", async event => {
    event.preventDefault();
    const status = $("#workspace-settings-status");
    status.textContent = "Saving settings…";
    try {
      await api("/v1/preferences/model-defaults", { method: "PUT", body: {
        model: $("#workspace-settings-model").value.trim(), inference_mode: $("#workspace-settings-mode").value,
      }});
      const effects = $("#workspace-settings-effects").value;
      if (effects === "system") storageRemove("hutch:reduce-effects");
      else storageSet("hutch:reduce-effects", effects === "reduce");
      applyEffects();
      status.textContent = "Workspace settings saved.";
    } catch (error) { status.textContent = `Could not save settings: ${error.message}`; }
  });
}

function isConversationView(hash = location.hash || "#/chat") {
  return /^#\/chat(?:\/|$)/.test(hash) || /^#\/conversation\/[\w-]+$/.test(hash);
}

const ROUTE_TITLES = { chat: "Chat", overview: "Activity", schedules: "Scheduled work",
  runtime: "Runtime", runs: "Work history", bots: "Assistants", connections: "Apps & AI",
  approvals: "Needs you", chats: "Conversation history", settings: "Settings" };

function routeTitle(hash) {
  if (hash.startsWith("#/conversation/")) return "Conversation";
  if (hash.startsWith("#/approvals")) return "Needs you";
  const bot = hash.match(/^#\/(?:chat|bot)\/([^/?]+)/);
  if (bot) return decodeURIComponent(bot[1]);
  const run = hash.match(/^#\/run\/([^/?]+)/);
  if (run) return `Run ${run[1].slice(4, 16)}`;
  const nav = routes.find(([re]) => re.test(hash))?.[2];
  return ROUTE_TITLES[nav] || "hutch";
}

async function route(announce = false) {
  const hash = location.hash || "#/chat";
  if (assistantSetupPage?.element.isConnected && hash !== "#/assistant/new") {
    assistantSetupPage.snapshot();
    assistantSetupPage.persist();
  }
  if (!hash.startsWith("#/")) {
    /* Plain fragment targets (the skip link's #view) are not views: leave the
       hash alone so the browser moves focus to the target element. */
    closeWorkspace();
    return;
  }
  updateRosterCurrentItem();
  document.body.classList.toggle("has-composer", isConversationView(hash));
  stopRunSubs();
  bumpSubOwner(routeOwner);
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
      if (["overview", "schedules", "runs", "bots", "runtime"].includes(nav)) $("#monitor-nav").open = true;
      try { await handler(m); }
      catch (err) { view.innerHTML = errorState(err); }
      if (announce) {
        document.title = `hutch — ${routeTitle(hash)}`;
        /* Replacing #view orphans keyboard focus to body; handlers that place
           focus deliberately keep it. Only rescue the orphaned case. */
        if (!document.activeElement || document.activeElement === document.body) {
          const heading = topContext?.querySelector("h1");
          if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
          else { view.tabIndex = -1; view.focus({ preventScroll: true }); }
        }
      }
      void refreshBadge();
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
    <p><a href="#/chat">Back to the studio</a> · <button class="btn ghost small" type="button" data-retry-route="1">Try again</button></p>
  </div></div></div>`;
}

function setTopContext(html) {
  if (!topContext || topContext.innerHTML === html) return;
  const active = document.activeElement;
  const focusedId = topContext.contains(active) ? active?.id : "";
  topContext.innerHTML = html;
  if (focusedId) document.getElementById(focusedId)?.focus({ preventScroll: true });
}

window.addEventListener("hashchange", () => route(true));
/* Delegated so the strict local CSP can forbid inline handlers: a rebuilt
   error state needs no re-wiring. */
document.addEventListener("click", event => {
  if (event.target.closest?.("[data-retry-route]")) {
    event.preventDefault();
    void route();
  }
});

/* -------------------------------------------------- roster + attention */

const rosterFlight = { promise: null };
async function refreshRoster() {
  return singleFlight(rosterFlight, async () => {
    try {
      botsCache = await api("/bots", { signal: shellOwner.abort?.signal });
      renderRoster();
      renderAttention();
    } catch (err) {
      if (err?.name === "AbortError") return;
      /* offline is handled by the daemon pill */
    }
  });
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
      : `<div class="roster-empty">No assistant matches.</div>`}`;
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
  const currentChatBot = isConversationView() ? currentStudioBot : null;
  const needsYou = remaining.filter(b => botNeedsYou(b));
  const inProgress = remaining.filter(b => !botNeedsYou(b) && botState(b) !== "idle" && b.name !== currentChatBot);
  const current = remaining.filter(b => b.name === currentChatBot && !needsYou.includes(b) && !inProgress.includes(b));
  const spotlight = new Set([...needsYou, ...inProgress, ...current]);
  const bots = [...(coordinatorMatch ? [coordinatorMatch] : []), ...pinned, ...remaining, ...hiddenIdle];
  if (!bots.length) {
    list.innerHTML = `<div class="roster-empty">${botsCache.length ? "No assistant matches." : "No assistants yet — create one."}</div>`;
    return;
  }
  const rowHtml = b => rosterRowHtml(b, currentStudioBot);
  const sections = [];
  if (coordinatorMatch) sections.push(`<div class="roster-section roster-coordinator">${rowHtml(coordinatorMatch)}</div>`);
  if (pinned.length) sections.push(`<section class="roster-section" aria-label="Pinned bots">
    <h3 class="roster-section-title">Pinned</h3>${pinned.map(rowHtml).join("")}</section>`);
  const bySection = new Map();
  for (const bot of remaining.filter(item => item.roster_section)) {
    const label = bot.roster_section.trim();
    const key = label.toLocaleLowerCase();
    const group = bySection.get(key) || { label, bots: [] };
    group.bots.push(bot);
    bySection.set(key, group);
  }
  for (const [key, group] of [...bySection.entries()].sort((a, b) => a[1].label.localeCompare(b[1].label))) {
    const open = !!store$.get(`hutch:roster-section:${key}`, false) || group.bots.some(b => spotlight.has(b));
    sections.push(`<details class="roster-section roster-idle-details roster-custom-details" data-roster-section="${esc(group.label)}" ${open ? "open" : ""}>
      <summary aria-label="${esc(group.label)}, ${group.bots.length} Bots">${esc(group.label)} <span class="roster-count">${group.bots.length}</span></summary>
      <div class="roster-section roster-idle-list">${group.bots.map(rowHtml).join("")}</div></details>`);
  }
  if (remaining.length) {
    const ungrouped = remaining.filter(item => !item.roster_section);
    const largeFleet = botsCache.length >= 10;
    if (!ungrouped.length) {
      // Every idle Bot is already reachable through a named section.
    } else if (largeFleet) {
      const active = ungrouped.filter(item => spotlight.has(item));
      const rest = ungrouped.filter(item => !spotlight.has(item));
      if (active.length) sections.push(`<section class="roster-section" aria-label="Active assistants">${active.map(rowHtml).join("")}</section>`);
      const allOpen = !!store$.get("hutch:roster-idle-open", false);
      if (rest.length) sections.push(`<details class="roster-section roster-idle-details" id="roster-idle-details" ${allOpen ? "open" : ""}>
        <summary aria-controls="roster-idle-bots">More assistants <span class="roster-count">${rest.length}</span></summary>
        <div class="roster-section roster-idle-list" id="roster-idle-bots">${rest.map(rowHtml).join("")}</div>
      </details>`);
    } else {
      sections.push(`<section class="roster-section" aria-label="All bots">
        ${ungrouped.map(rowHtml).join("")}</section>`);
    }
  }
  if (hiddenIdle.length) {
    const open = !!store$.get("hutch:roster-hidden-open", false);
    sections.push(`<details class="roster-section roster-idle-details roster-hidden-details" id="roster-hidden-details" ${open ? "open" : ""}>
      <summary aria-controls="roster-hidden-bots">Hidden bots <span class="roster-count">${hiddenIdle.length}</span></summary>
      <p class="roster-hidden-note">Hiding changes the roster only. Its runs and schedules continue.</p>
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
  updateRosterCurrentItem();
}

function updateRosterCurrentItem() {
  const inChat = isConversationView();
  $$("#roster-list [data-switch-bot]").forEach(button => {
    const current = inChat && button.dataset.switchBot === currentStudioBot;
    if (current) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
    button.closest(".roster-entry")?.classList.toggle("is-current", current);
  });
}

function rosterRowHtml(bot, currentStudioBot) {
  const state = botState(bot);
  const pip = botNeedsYou(bot) ? "waiting" : state === "running" ? "running" : state === "paused" ? "paused" : "";
  const status = botNeedsYou(bot) ? "Needs you" : botStatusLabel(bot);
  const role = botRole(bot);
  const visibleStatus = status === "Idle" && role ? "" : status;
  const coordinatorLabel = bot.is_workspace_coordinator && role.toLowerCase() !== "workspace coordinator" ? "Coordinator" : "";
  const subtitle = [visibleStatus, role, coordinatorLabel, bot.sidebar_hidden ? "Hidden" : ""]
    .filter(Boolean).join(" · ");
  const name = botHeading(bot);
  return `
    <div class="roster-entry${bot.name === currentStudioBot && isConversationView() ? " is-current" : ""}"><button class="roster-row" type="button" data-switch-bot="${esc(bot.name)}"
      ${bot.name === currentStudioBot && isConversationView() ? 'aria-current="true"' : ""}
      title="${esc(name)} — ${esc([subtitle, status !== visibleStatus ? status : ""].filter(Boolean).join(" · "))}">
      ${botAvatar(bot.name, 30, pip)}
      <span class="roster-id">
        <span class="roster-name">${esc(name)}</span>
        <span class="roster-sub">${esc(subtitle)}</span>
      </span>
    </button><button class="icon-btn roster-options" type="button" data-bot-options="${esc(bot.name)}"
      aria-label="Options for ${esc(name)}" aria-haspopup="menu" aria-expanded="false"
      title="Assistant options">${icon("moreHorizontal")}</button></div>`;
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
// Mobile overlay: labeled navigation sheet with focus ownership + restore.
const wsBtn = $("#nav-toggle"), wsEl = $("#workspace"), wsScrim = $("#ws-scrim"), wsClose = $("#ws-close");
// Same breakpoint as the CSS sheet. A closed sheet is only moved off-canvas, so it
// is made inert to keep its links out of the tab order and away from assistive tech.
const wsNarrow = matchMedia("(max-width: 900px)");
function syncWorkspaceInert() { wsEl.inert = wsNarrow.matches && !wsEl.classList.contains("open"); }
function openWorkspace() {
  wsEl.classList.add("open");
  syncWorkspaceInert();
  wsScrim.hidden = false;
  wsBtn.setAttribute("aria-expanded", "true");
  wsBtn.setAttribute("aria-label", "Close menu");
  wsClose.hidden = false;
  $("#workspace a")?.focus();
}
function closeWorkspace(restoreFocus = false) {
  if (!wsEl.classList.contains("open")) return;
  wsEl.classList.remove("open");
  syncWorkspaceInert();
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
wsNarrow.addEventListener("change", () => { if (!wsNarrow.matches) closeWorkspace(); syncWorkspaceInert(); });
syncWorkspaceInert();
// The reminder can wrap to several lines; publish its height so pages reserve
// enough room below their last item while it floats.
if ("ResizeObserver" in window) {
  const measured = new Map([[$("#attention-bar"), "--attention-h"]]);
  const sizes = new ResizeObserver(entries => {
    for (const { target } of entries) document.documentElement.style.setProperty(measured.get(target), `${target.offsetHeight}px`);
  });
  for (const el of measured.keys()) if (el) sizes.observe(el);
}
$("#bot-search")?.addEventListener("input", renderRoster);

/* Effects follow the OS by default; Settings offers an explicit override for
   the cases the system preference does not cover. */
function applyEffects() {
  const stored = store$.get("hutch:reduce-effects", null);
  const reduce = stored === null ? matchMedia("(prefers-reduced-motion: reduce)").matches : !!stored;
  document.documentElement.classList.toggle("reduce-effects", reduce);
}
applyEffects();

matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", applyEffects);

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

const healthFlight = { promise: null };
async function pollHealth() {
  return singleFlight(healthFlight, async () => {
    try {
      const h = await api("/health", { signal: shellOwner.abort?.signal });
      lastHealthAt = Date.now();
      setDaemon(h.execution_held ? "held" : "live", `${h.execution_held ? 'Execution held for restore review' : 'daemon live'} — v${h.version} · schema ${h.schema}`);
    } catch (err) {
      if (err?.name === "AbortError") return;
      const recent = lastHealthAt && Date.now() - lastHealthAt < 3 * HEARTBEAT_MS;
      const state = recent ? "reconnecting" : "offline";
      const changed = lastDaemonState !== state;
      setDaemon(state,
        recent ? "Server unreachable — retrying on the next heartbeat"
               : "Server offline — commands will not run until it returns");
      if (changed) announce("Connection to the hutch server was lost. Commands are paused until it returns.");
    }
  });
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
  const state = $("#browser-alerts-summary-state");
  if (!window.isSecureContext || typeof Notification === "undefined") {
    if (state) state.textContent = "Unavailable";
    button.disabled = true;
    status.textContent = "This browser does not support alerts for this connection.";
    return;
  }
  const enabled = browserAlertsEnabled();
  if (state) state.textContent = enabled ? "On" : Notification.permission === "denied" ? "Blocked" : "Off";
  button.textContent = enabled ? "Turn off alerts" : "Enable browser alerts";
  button.disabled = !enabled && Notification.permission === "denied";
  status.textContent = enabled
    ? "On while Hutch is open. Alerts show no chat, assistant or action details."
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

const badgeFlight = { promise: null };
async function refreshBadge() {
  return singleFlight(badgeFlight, async () => {
  try {
    const stats = await api("/stats", { signal: shellOwner.abort?.signal });
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
        const pend = await api("/approvals", { signal: shellOwner.abort?.signal });
        attentionBots = [...new Set(pend.map(a => a.bot_name))];
      } catch (err) {
        if (err?.name === "AbortError") return;
        attentionBots = [];
      }
    } else attentionBots = [];
    lastPendingCount = n;
    renderRoster();
    renderAttention();
    if (previousPendingCount !== null && n > previousPendingCount) {
      announce(unresolvedReceiptCount ? `${n} items need your review.` : `${n} approval${n === 1 ? "" : "s"} waiting for you.`);
    }
    notifyNewAttention(stats.pending_approvals || 0, unresolvedReceiptCount);
    lastPendingCount = n;
  } catch (err) {
    if (err?.name === "AbortError") return;
  }
  });
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
  const r = stats.working_runs || 0, w = stats.waiting_runs || 0;
  const q = stats.queued_tasks || 0, p = stats.pending_approvals || 0;
  if (r) parts.push(`<span class="w working"><span class="wdot"></span>${r} working</span>`);
  if (w) parts.push(`<span class="w waiting"><span class="wdot"></span>${w} waiting</span>`);
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
  // The Needs you route opens its dialog just after rendering chat; don't flash the reminder first.
  const onApprovals = needsYouDialog.open || needsYouRouteOpening;
  const shownRequests = $$("#chat-stream [data-approval-card]").filter(c => c.querySelector("[data-approve]:not([disabled])"));
  const shownReceipts = $$('#chat-stream [data-receipt-card]').filter(c => !c.dataset.receiptReviewed);
  const allInChat = isConversationView() && n && n <= shownRequests.length + shownReceipts.length;
  if (!n || onApprovals || allInChat || attentionDismissedCount === n) { bar.hidden = true; bar.dataset.message = ""; return; }
  bar.hidden = false;
  const message = unresolvedReceiptCount ? `${n} items need your review` : `${n} approval${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} you`;
  // Status polls call this every few seconds; rebuilding an unchanged reminder
  // would destroy a focused Review or Dismiss button and drop keyboard focus.
  if (bar.dataset.message === message) return;
  const focusedId = bar.contains(document.activeElement) ? document.activeElement.id : "";
  bar.dataset.message = message;
  bar.innerHTML = `${icon("alert")}
    <span><b>${message}</b></span>
    <button class="btn ghost small" id="attention-review" type="button">Review</button>
    <button class="icon-btn" id="attention-dismiss" aria-label="Dismiss reminder">${icon("x")}</button>`;
  $("#attention-review")?.addEventListener("click", openNeedsYou);
  $("#attention-dismiss")?.addEventListener("click", () => { attentionDismissedCount = n; bar.hidden = true; bar.dataset.message = ""; });
  if (focusedId) document.getElementById(focusedId)?.focus();
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
    bodyHtml: `<p>Group related conversations for this assistant. Reusing a name places chats together.</p>
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
        <input id="saved-task-template-search" type="search" autocomplete="off" placeholder="Search by name or request" enterkeyhint="search">
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
        bodyHtml: `<p class="hint">This changes only the local reusable request. It does not change any assistant or past message.</p>
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

function firstRunModelName(model) {
  const text = String(model || "");
  return text.split("/").filter(Boolean).at(-1) || text;
}

async function readFirstRunReadiness() {
  const [defaultsResult, openCodeResult, routesResult] = await Promise.allSettled([
    api("/v1/preferences/model-defaults"),
    api("/v1/opencode/status"),
    api("/v1/model-routes?inference_mode=hybrid&runtime=builtin"),
  ]);
  const defaults = defaultsResult.status === "fulfilled" ? defaultsResult.value : null;
  const openCode = openCodeResult.status === "fulfilled" ? openCodeResult.value : null;
  const routes = routesResult.status === "fulfilled" && Array.isArray(routesResult.value)
    ? routesResult.value : [];
  if (openCodeResult.status === "fulfilled") firstRunOpenCodeStatus = openCode;
  const failures = [
    defaultsResult.status === "rejected" ? "your saved AI choice" : "",
    openCodeResult.status === "rejected" ? "OpenCode" : "",
    routesResult.status === "rejected" ? "other AI routes" : "",
  ].filter(Boolean);
  const readyRoutes = routes.filter(route =>
    route?.state === "ready" && typeof route.spec === "string" && !route.spec.startsWith("mock/"));
  const savedModel = typeof defaults?.model === "string" ? defaults.model.trim() : "";
  const workspaceModel = savedModel.startsWith("mock/") ? "" : savedModel;
  const openCodeModels = Array.isArray(openCode?.models) ? openCode.models : [];

  if (workspaceModel) {
    const matchedRoute = readyRoutes.find(route => route.spec === workspaceModel);
    return {
      state: "saved",
      choice: {
        kind: "workspace", runtime: workspaceModel.startsWith("opencode/") ? "opencode" : "builtin",
        model: workspaceModel, label: matchedRoute?.label || firstRunModelName(workspaceModel),
      },
      copy: "Using your saved workspace choice for new assistants. Review it again before saving.",
      retry: false,
    };
  }
  if (openCode?.ready && openCodeModels.length) {
    const model = openCodeModels[0];
    const spec = typeof model?.spec === "string" ? model.spec : "";
    if (spec) {
      const count = openCodeModels.length;
      return {
        state: "ready",
        choice: { kind: "opencode", runtime: "opencode", model: spec, label: model.name || firstRunModelName(spec) },
        copy: `OpenCode is ready with ${count} model option${count === 1 ? "" : "s"}. ${openCode.authenticated
          ? "A provider account is connected."
          : "Its available models can be used without a separate account."}`,
        retry: false,
      };
    }
  }
  if (readyRoutes.length) {
    const route = readyRoutes[0];
    return {
      state: "ready",
      choice: { kind: "route", runtime: "builtin", model: route.spec, label: route.label || firstRunModelName(route.spec) },
      copy: `${route.group || "A configured provider"} has a ready model route for setup.`,
      retry: false,
    };
  }
  if (failures.length === 3) {
    return {
      state: "error",
      choice: null,
      copy: "Hutch could not check AI setup. Check the connection and try again, or open AI services to set one up.",
      retry: true,
    };
  }
  if (failures.length) {
    return {
      state: "setup",
      choice: null,
      copy: `No ready AI service was found, and Hutch could not check ${failures.join(", ")}. Try again before choosing a service.`,
      retry: true,
    };
  }
  return {
    state: "setup",
    choice: null,
    copy: "No ready AI service was found. Connect OpenCode or choose another provider; your request stays here.",
    retry: false,
  };
}

function paintFirstRunReadiness(snapshot) {
  const panel = $("#first-run-readiness");
  if (!panel || !panel.isConnected) return;
  const labels = { checking: "Checking", ready: "Ready", saved: "Saved", setup: "Choose AI", error: "Check failed" };
  const status = $("#first-run-readiness-status");
  if (status) status.dataset.state = snapshot.state || "checking";
  const statusText = $("#first-run-readiness-status-text");
  if (statusText) statusText.textContent = labels[snapshot.state] || labels.checking;
  const copy = $("#first-run-ai-state");
  if (copy) copy.textContent = snapshot.copy || labels.checking;
  const meta = $("#first-run-ai-meta");
  if (meta) meta.textContent = snapshot.choice?.model || "";
  const connect = $("#first-run-connect-opencode");
  if (connect) connect.textContent = snapshot.choice?.kind === "opencode" ? "OpenCode settings" : "Connect OpenCode";
  const retry = $("#first-run-ai-retry");
  if (retry) retry.hidden = !snapshot.retry;
  const submit = $("#first-run-submit");
  if (submit) {
    const ready = ["ready", "saved"].includes(snapshot.state);
    submit.formNoValidate = !ready;
    submit.innerHTML = `${ready ? "Set up my assistant" : "Choose an AI service"} ${icon("arrow")}`;
  }
  panel.setAttribute("aria-busy", snapshot.state === "checking" ? "true" : "false");
  firstRunSelection = snapshot.choice || null;
  firstRunReadinessState = snapshot.state || "checking";
}

async function refreshFirstRunReadiness() {
  const generation = ++firstRunReadinessGeneration;
  const panel = $("#first-run-readiness");
  if (!panel) return null;
  panel.setAttribute("aria-busy", "true");
  const pending = readFirstRunReadiness();
  firstRunReadinessPromise = pending;
  const snapshot = await pending;
  if (generation !== firstRunReadinessGeneration || !panel.isConnected) return snapshot;
  paintFirstRunReadiness(snapshot);
  return snapshot;
}

async function renderChatStudio(preferredBot = null, requestedConversationId = null) {
  // Direct assistant routes always resolve the durable home. Historical/task
  // routes keep their explicit identity through reloads and settings updates.
  const explicitConversation = location.hash.match(/^#\/conversation\/([\w-]+)$/);
  requestedConversationId ||= explicitConversation?.[1] || null;
  const directChat = !requestedConversationId;
  const generation = ++studioGeneration;
  const fetchedBots = await api("/bots");
  if (generation !== studioGeneration) return;
  botsCache = fetchedBots;
  renderRoster();
  if (!botsCache.length) {
    firstRunSelection = null;
    firstRunReadinessState = "checking";
    firstRunReadinessPromise = null;
    view.innerHTML = `<div class="page-scroll first-run-scroll"><div class="container first-run-container">
      <section class="welcome first-run-welcome" aria-labelledby="first-run-title">
        <div class="welcome-hero first-run-hero">
          <div class="welcome-stage" aria-hidden="true">
            <span class="welcome-app-mark welcome-app-calendar">${serviceMark("calendar")}</span>
            <span class="welcome-app-mark welcome-app-mail">${serviceMark("gmail")}</span>
            <span class="welcome-app-mark welcome-app-ai">${serviceMark("chatgpt")}</span>
            <div class="hero-agent first-run-mascot">${avatarFromPair([0, 0], 144)}</div>
          </div>
          <p class="first-run-eyebrow">Your personal assistant</p>
          <h1 id="first-run-title">What would you like help with?</h1>
          <p class="first-run-copy">Start with a request. Hutch carries it into setup for review.</p>
        </div>
        <div class="first-run-workbench">
          <form class="first-run-request" id="first-run-request-form">
            <div class="first-run-field-head">
              <label for="first-run-request">Your first request</label>
              <button class="first-run-clear" type="button" id="first-run-clear" hidden>Clear request</button>
            </div>
            <textarea id="first-run-request" rows="3" maxlength="20000" aria-describedby="first-run-request-hint" placeholder="For example, help me plan my week and keep track of the follow-ups." required></textarea>
            <div class="first-run-examples" role="group" aria-labelledby="first-run-examples-title">
              <p class="first-run-examples-title" id="first-run-examples-title">Or start with an idea</p>
              <div class="first-run-examples-grid">
                <button class="first-run-example" type="button" data-first-run-example="plan">${icon("clock")}<span>Plan my week</span></button>
                <button class="first-run-example" type="button" data-first-run-example="email">${icon("mail")}<span>Catch up on email</span></button>
                <button class="first-run-example" type="button" data-first-run-example="project">${icon("folder")}<span>Organize a project</span></button>
              </div>
            </div>
            <div class="first-run-request-foot">
              <span class="hint" id="first-run-request-hint">Nothing runs until you ask.</span>
              <button class="btn primary" type="submit" id="first-run-submit" formnovalidate>Set up my assistant ${icon("arrow")}</button>
            </div>
          </form>
          <aside class="first-run-readiness" id="first-run-readiness" aria-labelledby="first-run-readiness-title" aria-busy="true">
            <div class="first-run-readiness-head">
              <h2 id="first-run-readiness-title">AI service</h2>
              <span class="first-run-readiness-status" id="first-run-readiness-status" data-state="checking">
                <span class="first-run-readiness-dot" aria-hidden="true"></span><span id="first-run-readiness-status-text">Checking</span>
              </span>
            </div>
            <p class="first-run-readiness-copy" id="first-run-ai-state" role="status" aria-live="polite" aria-atomic="true">Looking for a saved model or a ready connection…</p>
            <p class="first-run-readiness-meta" id="first-run-ai-meta"></p>
            <div class="first-run-readiness-actions">
              <button class="btn ghost small" type="button" id="first-run-connect-opencode">Connect OpenCode</button>
              <a href="#/connections" id="first-run-manage-ai">Use another provider</a>
            </div>
            <button class="btn ghost small first-run-ai-retry" type="button" id="first-run-ai-retry" hidden>Check again</button>
          </aside>
        </div>
        <ul class="first-run-promises" aria-label="How Hutch works">
          <li>${icon("chat")}Start with a conversation</li>
          <li>${icon("shield")}Review important actions</li>
          <li>${icon("layers")}Choose the apps and AI you use</li>
        </ul>
        <p class="first-run-note">Your request stays in this tab while you set up an AI service. You can rename the assistant and change its settings before saving.</p>
      </section>
    </div></div>`;
    const request = $("#first-run-request");
    const clear = $("#first-run-clear");
    const syncDraftUi = () => { if (clear) clear.hidden = !request?.value; };
    if (request) {
      request.value = loadFirstRunDraft();
      syncDraftUi();
      request.addEventListener("input", () => {
        saveFirstRunDraft(request.value);
        syncDraftUi();
      });
    }
    clear?.addEventListener("click", () => {
      if (!request) return;
      request.value = "";
      clearFirstRunDraft();
      syncDraftUi();
      request.focus();
    });
    $("#first-run-request-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = $("#first-run-submit");
      const invocation = ++firstRunSubmitGeneration;
      const startingHash = location.hash;
      if (submit) {
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
      }
      try {
        if (firstRunReadinessState === "checking" && firstRunReadinessPromise) {
          try { await firstRunReadinessPromise; } catch { /* setup can still resolve its own choice */ }
        }
        if (invocation !== firstRunSubmitGeneration || location.hash !== startingHash
            || !submit?.isConnected) return;
        if (!firstRunSelection && ["setup", "error"].includes(firstRunReadinessState)) {
          saveFirstRunDraft(request?.value || "");
          location.hash = "#/connections";
          return;
        }
        const text = request?.value.trim() || "";
        if (!text) { request?.focus(); return; }
        saveFirstRunDraft(request.value);
        await promptNewBot("", "", null, text, firstRunSelection);
      } finally {
        if (submit?.isConnected) {
          submit.disabled = false;
          submit.removeAttribute("aria-busy");
        }
      }
    });
    $("#first-run-connect-opencode")?.addEventListener("click", () => {
      firstRunSubmitGeneration++;
      void openOpenCodeSetupDialog(() => { void refreshFirstRunReadiness(); });
    });
    $("#first-run-manage-ai")?.addEventListener("click", () => { firstRunSubmitGeneration++; });
    $("#first-run-ai-retry")?.addEventListener("click", () => { void refreshFirstRunReadiness(); });
    const starterRequests = {
      plan: "Help me plan my week and keep track of the follow-ups.",
      email: "Help me find the emails I need to answer and prepare drafts for me to review.",
      project: "Help me organize a project and keep track of the next steps.",
    };
    $$('[data-first-run-example]').forEach(button => button.addEventListener("click", () => {
      if (!request) return;
      request.value = starterRequests[button.dataset.firstRunExample] || "";
      saveFirstRunDraft(request.value);
      syncDraftUi();
      request.focus();
      request.setSelectionRange(request.value.length, request.value.length);
    }));
    void refreshFirstRunReadiness();
    return;
  }

  let requestedConversation = null;
  if (requestedConversationId) {
    try {
      requestedConversation = await api(`/v1/conversations/${encodeURIComponent(requestedConversationId)}`);
    } catch (error) {
      throw new Error(`That conversation is unavailable: ${error.message}`);
    }
  }
  let bot = requestedConversation ? botsCache.find(item => item.id === requestedConversation.bot_id)
          : botsCache.find(b => b.name === preferredBot) ||
            botsCache.find(b => b.is_workspace_coordinator) ||
            botsCache.find(b => b.name === "hutch") ||
            botsCache[0];
  if (requestedConversation && !bot) {
    throw new Error("This conversation's assistant is no longer available. Its history is retained in work history.");
  }
  currentStudioBot = bot.name;
  updateRosterCurrentItem();
  const detail = await api(`/bots/${encodeURIComponent(bot.name)}`);
  if (generation !== studioGeneration) return;
  currentConversations = await api(`/v1/conversations?bot=${encodeURIComponent(bot.id)}&include_legacy=true&include_archived=true&limit=100`);
  if (generation !== studioGeneration) return;
  const rememberedConversation = requestedConversationId;
  if (requestedConversation && !currentConversations.some(item => item.id === requestedConversation.id)) {
    currentConversations.unshift(requestedConversation);
  }
  let selectedConversation = currentConversations.find(c => c.id === rememberedConversation) || null;
  if (!selectedConversation) {
    const home = await api(`/v1/bots/${encodeURIComponent(bot.id)}/home-conversation`, { method: "PUT", body: {} });
    selectedConversation = home.conversation;
    if (!selectedConversation) throw new Error("This assistant's main chat could not be opened. Try again.");
    if (!currentConversations.some(item => item.id === selectedConversation.id)) currentConversations.unshift(selectedConversation);
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
  let workflowPolicy = { mode: "suggest", override: "inherit", revision: 0,
    auto_available: false, bot_mode: "suggest", limits: {} };
  let workflowPolicyError = "";
  try {
    workflowPolicy = await api(`/v1/workflows/conversations/${encodeURIComponent(selectedConversation.id)}/policy`);
  } catch (error) {
    workflowPolicyError = error.message || "Workflow settings could not be loaded.";
  }
  if (generation !== studioGeneration) return;
  const workflowModeOption = (value, label, disabled = false) =>
    `<option value="${value}" ${workflowPolicy.override === value ? "selected" : ""} ${disabled ? "disabled" : ""}>${esc(label)}</option>`;

  const state = botState(detail);
  const assistantName = botHeading(bot);
  const assistantRole = botRole(bot);
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(bot.name, 30, state === "running" ? "running" : state === "paused" ? "paused" : "")}
        <div class="ctx-heading">
          <h1 title="${esc(assistantName)}">${esc(assistantName)}</h1>
        <span class="ctx-subtitle" title="${esc(assistantRole)}">AI assistant${assistantRole ? ` · ${esc(assistantRole)}` : ""}</span>
        </div>
        <div class="ctx-meta${bot.is_workspace_coordinator ? " workspace-coordinator-meta" : ""}">
          ${bot.is_workspace_coordinator ? '<span class="tag" id="workspace-coordinator-pill" aria-label="Workspace coordinator"><span class="coordinator-label-wide">Workspace coordinator</span><span class="coordinator-label-compact" aria-hidden="true">Coordinator</span></span>' : ""}
          ${bot.paused ? '<span class="tag">paused</span>' : ""}
        ${activeRun ? statusChip(activeRun.status, activeRun.status_label) : ""}
      </div>
    </div>
    <div class="ctx-actions">
      ${!directChat ? '<label class="visually-hidden" for="conversation-switcher">Conversation history</label>' : ""}
      <select class="conversation-select" id="conversation-switcher" aria-label="Conversation history" ${directChat ? "hidden" : ""}>
        ${conversationOptionsHtml(currentConversations, currentConversationId)}
      </select>
      <button class="icon-btn studio-search-button" id="studio-search-messages" type="button"
        aria-label="Search chats" title="Search chats">${icon("search")}</button>
      <details class="conversation-actions" id="studio-conversation-actions">
        <summary class="icon-btn" id="studio-conversation-options" aria-label="Chat and assistant options" title="Chat and assistant options">${icon("moreHorizontal")}</summary>
        <div class="conversation-actions-panel" aria-label="Chat and assistant options">
          ${!directChat ? `<a class="conversation-action-item" href="#/chat/${esc(bot.name)}">${icon("chat")} Return to main chat</a>` : ""}
          <a class="conversation-action-item" href="#/chats">${icon("clock")} Conversation history</a>
          <button class="conversation-action-item" id="studio-rename-conversation" data-conversation-action="rename" type="button">${icon("chat")} Rename conversation</button>
          <button class="conversation-action-item" id="studio-conversation-pin" data-conversation-action="pin" type="button">${icon("pin")} ${selectedConversation.pinned ? "Unpin conversation" : "Pin conversation"}</button>
          <button class="conversation-action-item" id="studio-conversation-unread" data-conversation-action="unread" type="button">${icon("mail")} ${selectedConversation.unread ? "Mark read" : "Mark unread"}</button>
          <button class="conversation-action-item" id="studio-conversation-section" data-conversation-action="section" type="button">${icon("folder")} ${selectedConversation.section ? "Move to a section" : "New section"}</button>
          <div class="conversation-workflow-policy">
            <label for="chat-workflow-mode">Workflow mode for this chat</label>
            <select id="chat-workflow-mode" aria-describedby="chat-workflow-mode-help" ${workflowPolicyError ? "disabled" : ""}>
              ${workflowModeOption("inherit", `Assistant default · ${workflowPolicy.mode}`)}
              ${workflowModeOption("suggest", "Suggest in this chat")}
              ${workflowModeOption("off", "Off in this chat")}
              ${workflowModeOption("auto", workflowPolicy.auto_available || workflowPolicy.override === "auto" ? "Auto in this chat" : "Auto (set a reviewed assistant scope first)", !workflowPolicy.auto_available && workflowPolicy.override !== "auto")}
            </select>
            <p class="hint" id="chat-workflow-mode-help" role="status">${esc(workflowPolicyError || (workflowPolicy.auto_available
              ? "Auto stays inside this assistant’s saved workflow and budget limits."
              : "Suggest never starts a workflow. Auto needs an assistant-level reviewed scope."))}</p>
          </div>
          <details class="conversation-action-more" id="studio-conversation-more">
            <summary class="conversation-action-item" aria-label="More conversation actions" aria-expanded="false" aria-controls="studio-conversation-more-panel">${icon("moreHorizontal")} More</summary>
            <div class="conversation-action-more-panel" id="studio-conversation-more-panel">
              <button class="conversation-action-item" id="studio-conversation-template-save" data-conversation-action="template-save" type="button">${icon("fileText")} Save reusable request</button>
              <button class="conversation-action-item" id="studio-conversation-template-download" data-conversation-action="template-download" type="button">${icon("fileText")} Download task template</button>
              <button class="conversation-action-item" id="studio-conversation-export" data-conversation-action="export" type="button">${icon("fileText")} Export conversation</button>
              ${!directChat && !selectedConversation.is_legacy ? `<span class="conversation-action-divider" aria-hidden="true"></span>
                <button class="conversation-action-item" id="studio-archive-conversation" data-conversation-action="archive" type="button" ${activeRun ? "hidden" : ""}>${icon("inbox")} ${selectedConversation.archived ? "Restore conversation" : "Archive conversation"}</button>` : ""}
            </div>
          </details>
          <div id="persona-chat-options-slot"></div>
          <span class="conversation-action-divider" aria-hidden="true"></span>
          <a class="conversation-action-item" data-conversation-action="settings" href="#/bot/${esc(bot.name)}">${icon("sliders")} Assistant settings</a>
        </div>
      </details>
      <button class="btn ghost small" id="studio-review-run" type="button" aria-label="Review approval in this conversation" title="Jump to approval in this conversation" ${activeRun?.status === "waiting_approval" ? "" : "hidden"}>${icon("shield")} Review</button>
      <button class="btn danger small" id="studio-stop-run" type="button" data-stop-target="${esc(activeRun?.id || "")}" ${activeRun ? "" : "hidden"}>${icon("stop")} Stop</button>
    </div>`);
  $("#studio-search-messages")?.addEventListener("click", event => openConversationSearch(event.currentTarget));

  view.innerHTML = `
    <section class="studio">
      <section class="workflow-panel" id="workflow-panel" hidden aria-label="Workflow activity"></section>
      <div class="chat-scroll" id="chat-scroll">
        <div class="feed" id="chat-stream"></div>
      </div>
      <div class="jump-latest-slot" id="jump-latest-slot" hidden></div>
      <footer class="composer">
        <form id="chat-form" autocomplete="off">
          <div class="composer-box" id="composer-box">
            ${hutchUploadsRow(hutchUploadsGet(selectedConversation.id), "", selectedConversation.id)}
            <div class="reply-composer" id="reply-composer" hidden>
              <div class="reply-composer-preview" id="reply-composer-preview" role="status" aria-live="polite"></div>
              <button class="btn ghost small" id="reply-composer-clear" type="button" aria-label="Remove reply reference">Remove</button>
            </div>
            <div class="reply-composer workspace-result-composer" id="workspace-result-composer" hidden>
              <div class="reply-composer-preview" id="workspace-result-composer-preview" role="status" aria-live="polite"></div>
              <button class="btn ghost small" id="workspace-result-composer-clear" type="button" aria-label="Remove specialist result reference">Remove</button>
            </div>
            <div id="persona-turn-slot"></div>
            <div class="composer-body">
              <label class="visually-hidden" for="chat-prompt">Message ${esc(bot.display_name || bot.name)}</label>
              <textarea class="composer-textarea" id="chat-prompt" rows="1" placeholder="Message…" aria-describedby="chat-help" enterkeyhint="send"></textarea>
            </div>
            <div class="composer-toolbar">
              <div class="composer-tools">
                <div class="cmenu-wrap">
                  <button class="composer-util" type="button" id="composer-menu-btn" aria-label="Message options" aria-haspopup="dialog" aria-expanded="false" aria-controls="composer-menu">${icon("plus")}</button>
                  <div class="cmenu" id="composer-menu" role="dialog" aria-modal="false" aria-label="Message options" hidden>
                  <details class="cmenu-suggestions"><summary>Start from a suggestion</summary>
                  <div class="quick-prompts" id="quick-prompts">
                    <button type="button" data-quick="Sort this week's downloads and move invoices into folders">${icon("folder")} Sort downloads</button>
                    <button type="button" data-quick="Research this week's AI news and write a short summary">${icon("fileText")} Research news</button>
                    <button type="button" data-quick="Inspect this repository for TODOs and report findings">${icon("search")} Repo sweep</button>
                  </div></details>
                  <div class="cmenu-sep"></div>
                  <label class="cmenu-role-field" for="chat-task-role">Task role for the next message
                    <select id="chat-task-role" aria-describedby="chat-task-role-help">
                      <option value="">Default · Bot model</option>
                      ${TASK_ROLE_OPTIONS.map(([role, label]) => {
                        const route = detail.task_routes?.[role];
                        return `<option value="${role}">${label}${route ? ` · ${esc(route)}` : " · Bot model"}</option>`;
                      }).join("")}
                    </select>
                    <span class="cmenu-sub" id="chat-task-role-help">One message only. A configured task route is explicit; automatic classification is not enabled.</span>
                  </label>
                  <div class="cmenu-sep"></div>
                  <button class="cmenu-files" id="prompt-template-library-open" type="button">${icon("fileText")} Browse saved requests</button>
                  <button class="cmenu-files" id="prompt-template-import" type="button" aria-controls="task-template-file">${icon("fileText")} Import task-template file</button>
                  <input id="task-template-file" type="file" accept=".json,application/json" hidden>
                  <button class="cmenu-files" id="conversation-files-open" type="button">${icon("folder")} Browse files in this chat</button>
                  <button class="cmenu-files" id="workspace-upload-open" type="button">${icon("fileText")} Attach a data file</button>
                  <input id="workspace-upload-file" type="file" multiple hidden
                    accept=".csv,.jpeg,.jpg,.json,.md,.png,.tsv,.txt,.webp">
                  <button class="cmenu-files" id="conversation-export-open" type="button">${icon("fileText")} Export conversation as JSON</button>
                  <p class="hint cmenu-image-note" role="note">Images in this composer are sent with every message until you remove them (up to 4, 1.5 MB each). Other files stay in this chat’s workspace — mention them by name.</p>
                  <div class="cmenu-sep"></div>
                  <label class="cmenu-row"><input type="checkbox" id="rehearse-opt">
                    <span>Rehearse this run<span class="cmenu-sub">simulates writes and commands; model calls and reads still happen, and remote reads can have service-side effects</span></span></label>
                  <label class="cmenu-row"><input type="checkbox" id="enter-send-setting" role="switch" checked>
                    <span>Enter sends<span class="cmenu-sub">off: Enter adds a newline, use the send button</span></span></label>
                  <div class="cmenu-sep"></div>
                  <details class="cmenu-usage"><summary>Usage and limits</summary><div class="cmenu-facts">${budgetMeterHtml(detail)}
                    <span class="mono">${esc(detail.limits?.max_steps ?? "?")} steps max · ${esc((detail.tools || []).join(", ") || "no tools")}</span>
                  </div></details>
                  <button class="cmenu-files" id="preflight-open" type="button">${icon("chart")} Review cost and context before sending</button>
                  </div>
                </div>
                <span class="model-switch-slot" id="model-switch-slot"></span>
              </div>
              <div class="composer-actions">
                <span class="skill-switch-slot" id="skill-switch-slot"></span>
                <button class="composer-send" id="chat-send" type="submit" aria-label="Send message">${icon("up")}</button>
              </div>
            </div>
            <div class="composer-strip task-role-strip" id="task-role-flag" hidden></div>
            <div class="composer-strip" id="rehearse-flag" hidden>${icon("shield")} <b>Rehearsal</b> — writes and commands are simulated; model calls and reads still happen, and remote reads can have service-side effects.</div>
          </div>
          <p class="visually-hidden" id="chat-help">Enter sends, Shift+Enter adds a newline. Your draft is kept for this assistant if you navigate away.</p>
        </form>
      </footer>
    </section>`;

  void refreshWorkflowPanel(bot.name, selectedConversation.id, generation);

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
    await openConversation(selectedId);
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
      const archiveConversationId = selectedConversation.id;
      const archiveGeneration = studioGeneration;
      const archiveRoute = location.hash;
      action.disabled = true;
      closeStudioConversationMenu(false);
      try {
        await api(`/v1/conversations/${encodeURIComponent(archiveConversationId)}/archive`, {
          method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() }, body: { archived },
        });
        if (archiveGeneration !== studioGeneration || currentConversationId !== archiveConversationId
            || location.hash !== archiveRoute) return;
        if (archived) {
          storageRemove(`hutch-conversation:${bot.id}`);
          // Leaving a historical URL is deliberate here: re-rendering that
          // URL would immediately reopen the archived conversation.
          history.replaceState(null, "", `#/chat/${encodeURIComponent(bot.name)}`);
        }
        toast(archived ? "Conversation archived; restore it from Archived chats." : "Conversation restored.");
        await renderChatStudio(bot.name, archived ? null : archiveConversationId);
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

  const workflowModeSelect = $("#chat-workflow-mode");
  workflowModeSelect?.addEventListener("change", async event => {
    const select = event.currentTarget;
    const requested = select.value;
    const previous = workflowPolicy.override;
    if (requested === "auto" && !workflowPolicy.auto_available && previous !== "auto") {
      select.value = previous;
      return;
    }
    select.disabled = true;
    const help = $("#chat-workflow-mode-help");
    if (help) help.textContent = "Saving this conversation’s workflow mode…";
    const body = { mode: requested, expected_revision: workflowPolicy.revision };
    try {
      const key = await messageIdempotencyKey(`workflow-policy:${selectedConversation.id}`, body);
      const saved = await api(`/v1/workflows/conversations/${encodeURIComponent(selectedConversation.id)}/policy`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(`workflow-policy:${selectedConversation.id}`, key);
      if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
      workflowPolicy = saved;
      select.value = saved.override;
      if (help) help.textContent = saved.auto_available
        ? "Auto stays inside this assistant’s saved workflow and budget limits."
        : "Suggest never starts a workflow. Auto needs an assistant-level reviewed scope.";
      announce(`Workflow mode saved: ${saved.mode}.`);
    } catch (error) {
      select.value = previous;
      if (help) help.textContent = `Could not save this mode: ${error.message}`;
      toast(`Workflow mode was not saved: ${error.message}`, true);
    } finally {
      if (select.isConnected) select.disabled = !!workflowPolicyError;
    }
  });

  // wire composer
  const form = $("#chat-form"), txt = $("#chat-prompt"), sendBtn = $("#chat-send");
  const box = $("#composer-box");
  const switcher = window.hutchModelSwitcher?.mount($("#model-switch-slot"), detail, selectedConversation.id,
    () => paintTaskRole?.());
  const skillPicker = window.hutchSkills?.mountComposer($("#skill-switch-slot"), detail);
  window.hutchPersona?.mountChatOptions($("#persona-chat-options-slot"), selectedConversation.id);
  window.hutchPersona?.mountComposerChip($("#persona-turn-slot"), selectedConversation.id);
  const preflightOpen = $("#preflight-open");
  preflightOpen?.addEventListener("click", async () => {
    setMenu(false);
    preflightOpen.disabled = true;
    try {
      const preflightImageCount = hutchUploadsGet(composerConversationId)
        .filter(isImageUploadEntry).length;
      const html = await preflightHtml(detail, selectedConversation.id,
        { model: switcher?.selected() || "", taskRole: selectedTaskRole || "",
          prompt: txt.value.trim(), replyToMessageId: selectedReply?.id || "",
          workspaceTaskResult: selectedWorkspaceTaskResult || null,
          skills: skillPicker?.selected() || [], rehearse: !!rehearseOpt?.checked,
          imageCount: preflightImageCount });
      openModal({ title: "Before this call", bodyHtml: html, confirmText: "Close", showCancel: false,
                  returnFocus: menuBtn, onConfirm: async () => true });
    } finally {
      preflightOpen.disabled = false;
    }
  });
  if (selectedConversation.archived) {
    txt.disabled = true;
    txt.placeholder = "This conversation is archived. Start a new one to continue.";
    sendBtn.disabled = true;
  }

  const composerConversationId = selectedConversation.id;
  const composerDraftId = `${bot.name}:${composerConversationId}`;
  const taskRoleSelect = $("#chat-task-role");
  const taskRoleFlag = $("#task-role-flag");
  const taskRoleStorageKey = `hutch-task-role-next:${bot.id}:${composerConversationId}`;
  let selectedTaskRole = storageGet(taskRoleStorageKey) || "";
  if (!TASK_ROLE_OPTIONS.some(([role]) => role === selectedTaskRole)) selectedTaskRole = "";
  if (taskRoleSelect) taskRoleSelect.value = selectedTaskRole;
  const paintTaskRole = () => {
    if (!taskRoleFlag) return;
    if (!selectedTaskRole) { taskRoleFlag.hidden = true; taskRoleFlag.textContent = ""; return; }
    const label = TASK_ROLE_OPTIONS.find(([role]) => role === selectedTaskRole)?.[1] || selectedTaskRole;
    const assigned = detail.task_routes?.[selectedTaskRole] || "";
    const override = switcher?.selected() || "";
    const route = override || assigned || detail.model || "Bot default";
    taskRoleFlag.hidden = false;
    taskRoleFlag.textContent = `Next message · ${label} via ${route}${override ? " (one-message model choice takes precedence)" : assigned ? " (configured role route)" : " (Bot default)"}`;
  };
  taskRoleSelect?.addEventListener("change", () => {
    selectedTaskRole = taskRoleSelect.value;
    if (selectedTaskRole) storageSet(taskRoleStorageKey, selectedTaskRole);
    else storageRemove(taskRoleStorageKey);
    paintTaskRole();
  });
  paintTaskRole();
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
  activeAnswerCorrectionHandler = async (messageId, correction, button) => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    if (!bot || bot.runtime !== "builtin") {
      toast("Answer rewrites are available for the built-in runtime only.", true);
      return;
    }
    const pendingKey = `${composerConversationId}:${messageId}:${correction}`;
    if (pendingAnswerCorrections.has(pendingKey)) return;
    const prompts = {
      shorter: "Make this answer shorter.",
      go_deeper: "Go deeper on this answer.",
      less_banter: "Rewrite this answer with less banter.",
    };
    const prompt = prompts[correction];
    if (!prompt || !messageId) return;
    pendingAnswerCorrections.add(pendingKey);
    const actionGroup = button?.closest("[data-answer-actions]");
    actionGroup?.querySelectorAll("[data-answer-correction]").forEach(action => {
      action.setAttribute("aria-disabled", "true");
      action.setAttribute("aria-busy", "true");
    });
    const originalButtonLabel = button?.textContent;
    if (button) button.textContent = "Starting…";
    try {
      const body = { prompt, correction, reply_to_message_id: messageId, model: switcher?.selected() || null };
      const key = await messageIdempotencyKey(`correction:${composerConversationId}`, body);
      const result = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(`correction:${composerConversationId}`, key);
      if (body.model) switcher?.consumeOverride(body.model);
      if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
      currentRunId = result.id;
      subscribeRun(result.id);
      toast(ACTIVE.has(result.status) && activeRun ? "Rewrite queued behind the current run." : "Rewrite started.");
      refreshRoster();
    } catch (err) {
      if (generation === studioGeneration && composerConversationId === currentConversationId) {
        toast(`Could not rewrite this answer: ${err.message}. Your draft is unchanged.`, true);
      }
    } finally {
      pendingAnswerCorrections.delete(pendingKey);
      if (button?.isConnected) {
        if (originalButtonLabel) button.textContent = originalButtonLabel;
        actionGroup?.querySelectorAll("[data-answer-correction]").forEach(action => {
          action.removeAttribute("aria-disabled");
          action.removeAttribute("aria-busy");
        });
      }
      if (generation === studioGeneration && composerConversationId === currentConversationId) renderChatFeed();
    }
  };
  activeAnswerFeedbackHandler = async (messageId, rating, reason, control) => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    const pendingKey = `${composerConversationId}:${messageId}`;
    if (!messageId || pendingAnswerFeedbackUpdates.has(pendingKey)) return;
    const expectedRevision = Number(control?.dataset.feedbackRevision || 0);
    const body = { rating, reason: reason || null, expected_revision: expectedRevision };
    const scope = `persona-feedback:${composerConversationId}:${messageId}`;
    pendingAnswerFeedbackUpdates.add(pendingKey);
    const feedbackGroup = control?.closest(".answer-feedback");
    feedbackGroup?.setAttribute("aria-busy", "true");
    feedbackGroup?.querySelectorAll("button, select").forEach(action => {
      action.setAttribute("aria-disabled", "true");
      action.setAttribute("aria-busy", "true");
    });
    const feedbackStatus = feedbackGroup?.querySelector("[role=status]");
    if (feedbackStatus) feedbackStatus.textContent = "Saving locally…";
    try {
      const key = await messageIdempotencyKey(scope, body);
      const saved = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages/${encodeURIComponent(messageId)}/persona-feedback`, {
        method: "PUT", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(scope, key);
      if (generation === studioGeneration && composerConversationId === currentConversationId) {
        $$('[data-feedback-message]', $("#chat-stream")).filter(action => action.dataset.feedbackMessage === messageId)
          .forEach(action => { action.dataset.feedbackRevision = String(saved.revision); });
      }
    } catch (err) {
      if (generation === studioGeneration && composerConversationId === currentConversationId) {
        if (err.status === 409) {
          toast("This answer’s feedback changed elsewhere. The latest version has been loaded; review it before trying again.", true);
        } else toast(`Could not save answer feedback: ${err.message}`, true);
      }
    } finally {
      pendingAnswerFeedbackUpdates.delete(pendingKey);
      if (generation === studioGeneration && composerConversationId === currentConversationId) {
        // The pending state is applied directly to the live controls. If no
        // poll rendered while the request was in flight, the cached server
        // snapshot still matches the post-save markup and the no-op shortcut
        // would leave those controls stuck in their busy state.
        const stream = $("#chat-stream");
        if (stream) chatRenderSnapshots.delete(stream);
        scheduleFeedRender();
      }
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
  // Answer a specialist's question from the coordinator task card. The answer is
  // created in the specialist's own conversation, so the coordinator's model
  // switcher override must never be sent: the specialist keeps its saved route.
  activeWorkspaceQuestionSubmitHandler = async form => {
    if (generation !== studioGeneration || composerConversationId !== currentConversationId) return;
    if (form.dataset.submitting === "1") return;
    const questionConversationId = form.dataset.conversationId;
    const questionId = form.dataset.questionId;
    const optionIds = [...form.querySelectorAll("input:checked")].map(input => input.value);
    const error = form.querySelector("[data-choice-error]");
    if (!optionIds.length) {
      error.textContent = "Choose an option before sending your answer.";
      return;
    }
    const body = { option_ids: optionIds, model: null };
    form.dataset.submitting = "1";
    form.querySelectorAll("input, button").forEach(el => { el.disabled = true; });
    error.textContent = "";
    try {
      const key = await choiceAnswerIdempotencyKey(questionConversationId, questionId, body);
      await api(`/v1/conversations/${encodeURIComponent(questionConversationId)}/questions/${encodeURIComponent(questionId)}/answer`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearChoiceIdempotencyKey(questionConversationId, questionId, key);
      storageRemove(choiceDraftKey(composerConversationId, questionId));
      toast("Answer sent to the specialist.");
      if (generation !== studioGeneration) return;
      scheduleFeedRender();
    } catch (err) {
      error.textContent = err.message || "Your answer could not be sent.";
      form.querySelectorAll("input, button").forEach(el => { el.disabled = false; });
      if (/already answered/i.test(err.message || "")) scheduleFeedRender();
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
  const { resize: autogrow } = window.hutchComposer.mountAutogrow(txt, { onInput: () => saveDraft(composerDraftId, txt.value) });
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
    // Attachment-tray contract: images staged in the composer travel with every
    // message until removed, so an image-only send is a complete request.
    const stagedUploads = hutchUploadsGet(composerConversationId);
    const imageAttachmentIds = stagedUploads.filter(isImageUploadEntry).map(upload => upload.id);
    if ((!text && !imageAttachmentIds.length) || inflight) return;
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
      const body = { rehearse: !!rehearseOpt?.checked, model: switcher?.selected() || null,
                     task_role: selectedTaskRole || null, skills: skillPicker?.selected() || [] };
      // The prompt key is omitted for an image-only message (the API accepts
      // prompt-less sends only when images are attached).
      if (text) body.prompt = text;
      if (imageAttachmentIds.length) body.image_attachment_ids = imageAttachmentIds;
      if (replySnapshot) body.reply_to_message_id = replySnapshot;
      if (workspaceResultSnapshot) {
        body.workspace_task_result_id = workspaceResultSnapshot.id;
        body.workspace_task_result_message_id = workspaceResultSnapshot.result_message_id;
      }
      const personaTurn = window.hutchPersona?.nextReply(composerConversationId);
      if (personaTurn) body.persona = personaTurn;
      const key = await messageIdempotencyKey(composerConversationId, body);
      const r = await api(`/v1/conversations/${encodeURIComponent(composerConversationId)}/messages`, {
        method: "POST", headers: { "Idempotency-Key": key }, body,
      });
      clearMessageIdempotencyKey(composerConversationId, key);
      if (body.model) switcher?.consumeOverride(body.model);
      if (body.task_role) {
        selectedTaskRole = "";
        storageRemove(taskRoleStorageKey);
        if (taskRoleSelect) taskRoleSelect.value = "";
        paintTaskRole();
      }
      if (body.skills.length) skillPicker?.consume();
      if (personaTurn) window.hutchPersona?.consumeNextReply(composerConversationId);
      if (replySnapshot && selectedReply?.id === replySnapshot) setReply(null);
      if (workspaceResultSnapshot && selectedWorkspaceTaskResult?.id === workspaceResultSnapshot.id) {
        setWorkspaceTaskResult(null);
      }
      const titleOption = conversationSwitcher?.selectedOptions?.[0];
      if (titleOption && titleOption.textContent.trim().endsWith("New conversation")) {
        titleOption.textContent = text ? text.slice(0, 72)
          : `${imageAttachmentIds.length} image${imageAttachmentIds.length === 1 ? "" : "s"} attached`;
      }
      if (body.rehearse) toast("Rehearsal started — model calls and reads still happen.");
      else if (ACTIVE.has(r.status) && activeRun) toast("Sent — queued behind the current run.");
      if (generation !== studioGeneration) { if (loadDraft(composerDraftId) === snapshot) saveDraft(composerDraftId, ""); return; }
      currentRunId = r.id;
      // Clear only the submitted revision; anything typed since stays put.
      if (txt.value === snapshot) { txt.value = ""; saveDraft(composerDraftId, ""); autogrow(); }
      subscribeRun(r.id);
      renderChatFeed();
      refreshRoster();
    } catch (err) {
      box.classList.add("has-error");
      toast(`Not sent: ${err.message}. ${imageAttachmentIds.length && !text
        ? "Your attachments are kept." : "Your draft is kept."}`, true);
    } finally {
      inflight = false;
      sendBtn.disabled = false;
      sendBtn.classList.remove("sending");
      sendBtn.innerHTML = icon("up");
      sendBtn.setAttribute("aria-label", "Send message");
    }
  };
  form.addEventListener("submit", ev => { ev.preventDefault(); submit(); });
  // Paste and drop stage real uploads through the same path as the file picker;
  // a pasted screenshot blob gets the extension the upload intake requires.
  txt.addEventListener("paste", ev => {
    const files = Array.from(ev.clipboardData?.items || [])
      .filter(item => item.kind === "file")
      .map(item => item.getAsFile())
      .filter(file => file && /^image\//i.test(file.type || ""));
    if (!files.length) return;
    ev.preventDefault();
    void stageWorkspaceFiles(files);
  });
  // Composer-level drop target: files land in the tray, not the browser window.
  let dropDepth = 0;
  const dropsFiles = ev => Array.from(ev.dataTransfer?.types || []).includes("Files");
  box.addEventListener("dragenter", ev => {
    if (!dropsFiles(ev)) return;
    ev.preventDefault();
    dropDepth += 1;
    box.classList.add("is-dragover");
  });
  box.addEventListener("dragover", ev => {
    if (!dropsFiles(ev)) return;
    ev.preventDefault();
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = "copy";
  });
  box.addEventListener("dragleave", () => {
    dropDepth = Math.max(0, dropDepth - 1);
    if (!dropDepth) box.classList.remove("is-dragover");
  });
  box.addEventListener("drop", ev => {
    const files = Array.from(ev.dataTransfer?.files || []);
    if (!files.length) return;
    ev.preventDefault();
    dropDepth = 0;
    box.classList.remove("is-dragover");
    void stageWorkspaceFiles(files);
  });
  // Enter/IME behaviour is owned by the shared composer module so every surface
  // matches (never submit mid-composition; Shift+Enter always newlines).
  window.hutchComposer.mountEnterSubmit(txt, { enterSends, submit });
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
  const composerPopup = window.hutchControls.popup({ trigger: menuBtn, panel: menu, kind: "dialog", side: "top" });
  const setMenu = open => {
    if (open) composerPopup.open(); else composerPopup.close(false);
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
  $("#studio-stop-run").onclick = ev => requestStop(ev.currentTarget.dataset.stopTarget, ev.currentTarget);
  $("#studio-review-run").onclick = () => {
    const id = $("#studio-stop-run").dataset.stopTarget;
    const thread = $$("#chat-stream [data-run-id]").find(e => e.dataset.runId === id);
    const card = thread?.querySelector("[data-approval-card]");
    if (card) {
      card.scrollIntoView({ block: "center", behavior: "instant" });
      card.querySelector("summary, button")?.focus({ preventScroll: true });
    } else void openNeedsYou();
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
  const spent = Number(bot.cost_measured_today_usd || 0) + Number(bot.cost_reserved_today_usd || 0);
  const cost = spent > 0 ? ` · ${fmtUsd(spent)} today` : "";
  return `
    <span class="budget-meter ${state}" title="Daily token budget: ${used} of ${cap}; recorded cost today (measured + held): ${fmtUsd(spent)}">
      <span class="meter-track"><span class="meter-fill" style="width:${Math.min(pct, 100)}%"></span></span>
      <span class="cost">${fmtTokens(used)} / ${fmtTokens(cap)}${cost}</span>
    </span>`;
}

/* The preflight sheet is the "review before spending" step of SR-2: the route, the price basis
   admission would hold, the context this request needs, and the applicable scope budget. It is built
   from the same server-side estimator the runtime uses, so the numbers a person sees are the numbers a
   reservation would hold; provider billing can still differ and the copy says so. */
/* Bands are loaded separately from the limits form so a failure to read them cannot blank the page. */
async function loadBotBudget(bot) {
  try {
    const data = await api(`/v1/budgets?scope_kind=bot&scope_id=${encodeURIComponent(bot.id)}`);
    const policy = data.policy || {};
    const set = (id, value) => { const el = $(id); if (el) el.value = value === null || value === undefined ? "" : String(value); };
    set("#band-warn", policy.warn_usd);
    set("#band-pause", policy.pause_usd);
    set("#band-ceiling", policy.ceiling_usd);
    const unknown = $("#band-unknown");
    if (unknown) unknown.value = policy.unknown_price || "refuse";
    const extra = $("#assistant-usage-today-extra");
    if (extra) {
      const spent = Number(data.spent_usd || 0), held = Number(data.held_usd || 0);
      extra.textContent = spent || held ? ` · ${fmtUsd(spent)} spent + ${fmtUsd(held)} held today` : "";
    }
  } catch { /* the fields simply stay empty; saving them later is still possible */ }
}

async function preflightHtml(bot, conversationId = "", selection = {}) {
  try {
    const body = { conversation_id: conversationId, prompt: selection.prompt || "" };
    if (selection.model) body.model = selection.model;
    if (selection.taskRole) body.task_role = selection.taskRole;
    if (selection.skills?.length) body.skills = selection.skills;
    if (selection.rehearse) body.rehearse = true;
    if (selection.replyToMessageId) body.reply_to_message_id = selection.replyToMessageId;
    if (selection.workspaceTaskResult) {
      body.workspace_task_result_id = selection.workspaceTaskResult.id;
      body.workspace_task_result_message_id = selection.workspaceTaskResult.result_message_id;
    }
    const e = await api(`/bots/${encodeURIComponent(bot.name)}/estimate`, { method: "POST", body });
    const money = fmtUsd;
    const basis = {
      openrouter: "live OpenRouter endpoint quote", price_file: "your price file",
      openrouter_unavailable: "fresh OpenRouter quote unavailable",
      openrouter_no_eligible_endpoint: "no eligible OpenRouter endpoint",
      local: "local model — no per-token cost", flat: "flat-rate plan", unknown: "unknown — no price basis",
    }[e.price_source] || e.price_source || "unknown";
    const bands = [["warn", e.warn_usd], ["pause", e.pause_usd], ["hard stop", e.ceiling_usd]]
      .filter(([, v]) => v !== null && v !== undefined);
    const scope = e.budget_scope ? `${e.budget_scope} budget` : "no scope budget set";
    const hasDraft = !!selection.prompt?.trim();
    const draftLabel = hasDraft ? "this draft" : "a generic task placeholder because the draft is empty";
    const taskRoleLabel = TASK_ROLE_OPTIONS.find(([role]) => role === selection.taskRole)?.[1] || "";
    return `
      <dl class="preflight-grid">
        <div><dt>Route</dt><dd class="mono">${esc(e.spec)}</dd></div>
        ${taskRoleLabel ? `<div><dt>Task role</dt><dd>${esc(taskRoleLabel)}${selection.model ? " · one-message model choice takes precedence" : " · configured route when mapped"}</dd></div>` : ""}
        <div><dt>Price basis</dt><dd>${esc(basis)}${e.price_verified_on ? ` · fetched ${esc(String(e.price_verified_on).slice(0, 19))}` : ""}${e.price_expires_at ? ` · expires ${esc(String(e.price_expires_at).slice(0, 19))}` : ""}${e.price_stale ? " · stale" : ""}${e.price_endpoint_identities?.length ? ` · maximum of ${e.price_endpoint_identities.length} eligible endpoints` : ""}${e.price_snapshot_sha256 ? ` · quote ${esc(e.price_snapshot_sha256.slice(0, 12))}` : ""}</dd></div>
        <div><dt>Next call reserve</dt><dd>${money(e.next_call_usd)}${e.next_call_usd === null ? " — no USD price basis; the unknown-price policy and caps govern admission" : ""}</dd></div>
        <div><dt>Run estimate</dt><dd>${money(e.worst_case_usd)} up to ${e.steps} steps${e.run_cap_usd ? ` · run limit ${money(e.run_cap_usd)}` : ""}</dd></div>
        <div><dt>Context</dt><dd>${fmtTokens((e.message_tokens || 0) + (e.tool_tokens || 0))} estimated tokens for instructions, tools, selected skills, recent conversation and ${esc(draftLabel)}${selection.imageCount ? ` · plus ${selection.imageCount} staged image${selection.imageCount === 1 ? "" : "s"} not included in this estimate` : ""} · window ${e.window_tokens ? fmtTokens(e.window_tokens) : "not reported yet"}</dd></div>
        <div><dt>Scope spend</dt><dd>${esc(scope)}: ${money(e.budget_measured_usd)} spent + ${money(e.budget_held_usd)} held${bands.length ? ` · ${bands.map(([label, v]) => `${label} ${money(v)}`).join(", ")}` : ""}</dd></div>
      </dl>
      <p class="hint">USD and token estimates for ${esc(draftLabel)} and the bounded context preview; context may change before sending, and provider tokenization/billing can differ. OpenRouter may select a different live endpoint. A pause threshold asks you before the call; a hard stop refuses new paid calls.${e.window_note ? ` ${esc(e.window_note)}.` : ""}</p>`;
  } catch (err) {
    return `<p class="hint">Could not build the preview: ${esc(err.message)}</p>`;
  }
}

/* -------------------------------------------------- live feed (SSE + render) */

let runStream = null, statusTimer = null, renderTimer = null, subRunId = null, feedRefreshPending = false;
let feedMode = "studio";   // "studio" (bot transcript) or "run" (single-run detail)
const feedRenderFlight = { promise: null };

function stopRunSubs() {
  subRunId = null;
  if (runStream) { runStream.close(); runStream = null; }
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
  if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
  bumpSubOwner(routeOwner);
}

function subscribeRun(runId) {
  if (subRunId === runId && (runStream || statusTimer)) return;   // already live on this run
  stopRunSubs();
  subRunId = runId;
  try {
    runStream = new EventSource(`/api/runs/${runId}/stream`);
    routeOwner.sources.add(runStream);
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
    void singleFlight(feedRenderFlight, async () => {
      if (feedMode === "run" && currentRunId) {
        // Preserve the private controller's form, focus and token while the session panel polls ownership separately.
        if (!window.HutchComputer?.hasControl(currentRunId)) await renderRunDetail(currentRunId);
      }
      else await renderChatFeed();
    });
  }, 250);
}

// Messages belong to the selected conversation. Terminal runs are cached;
// the active one re-renders as events arrive.
const terminalRunCache = new Map();
const terminalRunReplyCache = new Set();
const chatRenderSnapshots = new WeakMap();

async function renderChatFeed() {
  if (feedMode !== "studio") return;
  const stream = $("#chat-stream");
  const scroll = $("#chat-scroll");
  if (!stream || !scroll || !currentStudioBot) return;

  const conversationId = currentConversationId, generation = studioGeneration;
  void refreshWorkflowPanel(currentStudioBot, conversationId, generation);
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
    for (const task of workspaceTasks) {
      const question = task.pending_question;
      if (!question || seenTaskQuestions.has(question.id)) continue;
      seenTaskQuestions.add(question.id);
      announce(`${botDisplayName(task.target_display_name || "A specialist")} is waiting for your answer.`);
    }
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
    // Compare the server-rendered snapshot, not innerHTML: wireWelcome() adds
    // the async template gallery after this markup is installed.
    if (chatRenderSnapshots.get(stream) === nextHtml) return;
    const factUi = captureFactUi(stream);
    stream.innerHTML = nextHtml;
    chatRenderSnapshots.set(stream, nextHtml);
    wireWelcome();
    wireFactControls(factPage.facts || [], currentStudioBot, factShares);
    $('[data-retry-facts]', stream)?.addEventListener('click', () => scheduleFeedRender());
    restoreFactUi(stream, factUi);
    return;
  }

  const wasNearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 90;
  const scrollTopBefore = scroll.scrollTop;
  const scrollViewport = scroll.getBoundingClientRect();
  const scrollAnchor = $$('.thread[data-run-id]', stream).find(thread => {
    const rect = thread.getBoundingClientRect();
    return rect.bottom > scrollViewport.top && rect.top < scrollViewport.bottom;
  });
  const scrollAnchorRunId = scrollAnchor?.dataset.runId || null;
  const scrollAnchorOffset = scrollAnchor
    ? scrollAnchor.getBoundingClientRect().top - scrollViewport.top : null;

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
      const hasPendingAnswerCorrection = messages.some(m => m.role === "assistant" && m.run_id === runId
        && [...pendingAnswerCorrections].some(key => key.startsWith(`${conversationId}:${m.id}:`)));
      const hasPersonaFeedback = messages.some(m => m.role === "assistant" && m.run_id === runId && m.persona_feedback);
      const hasPendingAnswerFeedback = messages.some(m => m.role === "assistant" && m.run_id === runId
        && pendingAnswerFeedbackUpdates.has(`${conversationId}:${m.id}`));
      const hasWorkspaceTask = workspaceTasks.some(task => task.source_run_id === runId);
      const hasCodeHandoff = codeHandoffs.some(task => task.source_run_id === runId);
      if (runId === currentRunId || hasPendingAnswerCorrection || hasPersonaFeedback || hasPendingAnswerFeedback
          || hasWorkspaceTask || hasCodeHandoff || !terminalRunCache.has(runId)
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
  // A card can contain nested disclosures (for example, review summary and
  // technical arguments). Store all open bits per card; keying each disclosure
  // only by approval ID lets a nested closed state overwrite the outer open one.
  const reviewState = new Map($$("[data-approval-card]", stream).map(card => [
    card.dataset.approvalCard,
    [...card.querySelectorAll("details")].map(details => details.open),
  ]));
  const activityState = new Map($$("[data-run-id] .tool-stream", stream).map(d => [d.closest("[data-run-id]").dataset.runId, d.open]));
  const focused = document.activeElement;
  const focusedApproval = focused?.closest("[data-approval-card]")?.dataset.approvalCard;
  const focusedChoice = focused?.dataset.approve;
  const focusedReceipt = focused?.dataset.receiptReview;
  const focusedFact = focused?.dataset.factReview;
  const focusedAnswerCorrection = focused?.dataset.answerCorrection;
  const focusedAnswerMessage = focused?.dataset.answerMessage;
  const focusedFeedbackRating = focused?.dataset.answerFeedbackRating;
  const focusedFeedbackMessage = focused?.dataset.feedbackMessage;
  const focusedFeedbackReason = focused?.hasAttribute("data-answer-feedback-reason");
  const focusedWorkflowSuggestion = focused?.dataset.workflowSuggestionRun;
  const focusedWorkspaceQuestion = focused?.closest("[data-workspace-question-form]")?.dataset.questionId;
  const focusedWorkspaceOption = focused?.matches("[data-workspace-question-form] [data-choice-option]")
    ? focused.value : null;
  const focusedWorkspaceSubmit = Boolean(focusedWorkspaceQuestion
    && focused?.matches("[data-workspace-question-form] [type=submit]"));
  const factUi = captureFactUi(stream);
  const nextHtml = parts.join("") + factPanelHtml(factPage.facts || [], factPage.error, factShares);
  if (chatRenderSnapshots.get(stream) === nextHtml) return;
  stream.innerHTML = nextHtml;
  chatRenderSnapshots.set(stream, nextHtml);
  $$("[data-approval-card]", stream).forEach(card => {
    const states = reviewState.get(card.dataset.approvalCard);
    if (!states) return;
    [...card.querySelectorAll("details")].forEach((details, index) => {
      if (index < states.length) details.open = states[index];
    });
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
  if (focusedAnswerCorrection && !focused.isConnected) {
    $$('[data-answer-correction]', stream).find(button => button.dataset.answerCorrection === focusedAnswerCorrection
      && button.dataset.answerMessage === focusedAnswerMessage)?.focus({ preventScroll: true });
  }
  if (focusedFeedbackRating !== undefined && !focused.isConnected) {
    $$('[data-answer-feedback-rating]', stream).find(button => button.dataset.answerFeedbackRating === focusedFeedbackRating
      && button.dataset.feedbackMessage === focusedFeedbackMessage)?.focus({ preventScroll: true });
  }
  if (focusedFeedbackReason && !focused.isConnected) {
    $$('[data-answer-feedback-reason]', stream).find(select => select.dataset.feedbackMessage === focusedFeedbackMessage)
      ?.focus({ preventScroll: true });
  }
  if (focusedWorkflowSuggestion && !focused.isConnected) {
    ($$('[data-workflow-suggestion-run]', stream)
      .find(button => button.dataset.workflowSuggestionRun === focusedWorkflowSuggestion) || $('#chat-prompt'))
      ?.focus({ preventScroll: true });
  }
  if (focusedWorkspaceQuestion && !focused.isConnected) {
    const form = $$('[data-workspace-question-form]', stream)
      .find(item => item.dataset.questionId === focusedWorkspaceQuestion);
    const target = focusedWorkspaceOption !== null
      ? [...(form?.querySelectorAll("[data-choice-option]") || [])]
        .find(input => input.value === focusedWorkspaceOption)
      : focusedWorkspaceSubmit ? form?.querySelector('[type="submit"]') : null;
    (target || $("#chat-prompt"))?.focus({ preventScroll: true });
  }
  restoreFactUi(stream, factUi);
  if (wasNearBottom) scroll.scrollTop = scroll.scrollHeight;
  else if (scrollAnchorRunId && scrollAnchorOffset !== null) {
    const nextAnchor = $$('.thread[data-run-id]', stream).find(thread => thread.dataset.runId === scrollAnchorRunId);
    if (nextAnchor) {
      const nextOffset = nextAnchor.getBoundingClientRect().top - scroll.getBoundingClientRect().top;
      scroll.scrollTop += nextOffset - scrollAnchorOffset;
    } else scroll.scrollTop = scrollTopBefore;
  } else scroll.scrollTop = scrollTopBefore;

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
  const jumpSlot = $("#jump-latest-slot");
  if (!wasNearBottom) {
    if (!jump) {
      jump = document.createElement("button");
      jump.id = "jump-latest"; jump.className = "jump-latest"; jump.type = "button";
      jump.innerHTML = `${icon("down")} Jump to latest`;
      jump.addEventListener("click", () => { scroll.scrollTop = scroll.scrollHeight; jumpSlot.hidden = true; });
    }
    jumpSlot.appendChild(jump);
    jumpSlot.hidden = false;
  } else {
    scroll.scrollTop = scroll.scrollHeight;
    jumpSlot.hidden = true;
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
    <div class="fact-heading"><strong>${esc(fact.learning ? 'Formatting preference' : fact.key)}</strong><span class="tag">${fact.status === 'approved' ? fact.learning ? 'Saved automatically' : 'Reviewed' : fact.status === 'archived' ? 'Archived' : 'Proposed'}</span></div>
    <p class="fact-value">${esc(fact.value)}</p>
    <p class="hint">${esc(factScopeLabel(fact))} · revision ${esc(fact.revision)}${fact.truncated ? ' · truncated; revise before use' : ''}</p>
    ${fact.learning ? `<p class="hint">From your explicit formatting preference in this chat. <a href="#/conversation/${esc(fact.scope_id)}">Open source chat</a> · message <code>${esc(fact.learning.source_message_id)}</code></p>` : ''}
    <div class="btn-row">${fact.status === 'proposed' ? `<button type="button" class="btn primary small" data-fact-review="${esc(fact.id)}">Review fact</button>` : ''}
      ${fact.status !== 'archived' ? `<button type="button" class="btn ghost small" data-fact-edit="${esc(fact.id)}">Revise</button>
      <button type="button" class="btn ghost small" data-fact-archive="${esc(fact.id)}">${fact.learning ? 'Undo saved preference' : 'Archive fact'}</button>` : ''}
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
  const proposed = facts.filter(f => f.status === 'proposed');
  const automatic = facts.filter(f => f.status === 'approved' && f.learning);
  const reviewed = facts.filter(f => f.status === 'approved' && !f.learning);
  return `<section class="fact-panel" aria-label="Reference facts">
    <h2>Reference facts</h2><p class="hint">Model proposals need review. Explicit formatting preferences may be saved automatically when hybrid learning is enabled. Records grant no tool permission; you can undo or disable memory.</p>
    ${automatic.length ? `<section class="learning-preferences" aria-label="Formatting preferences"><h3>Formatting preferences</h3><p class="hint">Saved automatically from your messages in this chat.</p><ul>${automatic.map(fact => `<li data-fact-card="${esc(fact.id)}"><strong>${esc(fact.value)}</strong><button class="btn ghost small" type="button" data-fact-archive="${esc(fact.id)}">Undo</button><button class="btn ghost small" type="button" data-fact-history="${esc(fact.id)}" aria-label="Details for ${esc(fact.value)}">Details</button></li>`).join('')}</ul></section>` : ''}
    ${proposed.map(factCardHtml).join('')}
    ${reviewed.length ? `<details><summary>${reviewed.length} saved or reviewed ${reviewed.length === 1 ? 'fact' : 'facts'} in this window</summary>${reviewed.map(factCardHtml).join('')}</details>` : ''}
    ${factShareRecordsHtml(sharePage)}
    ${facts.length === 20 ? '<p class="hint">Showing 20 facts. Bot settings provide the full paginated inventory.</p>' : ''}</section>`;
}

function refreshFactsAfterChange(botName) {
  if (location.hash === `#/bot/${encodeURIComponent(botName)}`) void renderBotDetail(botName);
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
    if (fact.learning) {
      button.disabled = true;
      void api(`/v1/bots/${encodeURIComponent(botName)}/facts/${encodeURIComponent(fact.id)}/review`, {
        method:'POST', headers:{'Idempotency-Key':key}, body:{content_hash:fact.content_hash, action:'archive'}})
        .then(() => { toast('Preference removed from new retrieval. Earlier conversation text remains.'); refreshFactsAfterChange(botName); })
        .catch(error => { button.disabled = false; toast(`Could not undo this preference: ${error.message}`, true); });
      return;
    }
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
        bodyHtml: `<p>Versions and decisions are retained. Automatic formatting decisions and human reviews show their actor; neither proves a fact or authorizes an action.</p>
          ${page.facts.map(version => `<article class="fact-card"><strong>Revision ${esc(version.revision)} · ${esc(version.status)}</strong>
            <p class="fact-value">${esc(version.learning ? 'Formatting preference' : version.key)}: ${esc(version.value)}</p><p class="hint">${version.learning ? `Saved automatically from message <code>${esc(version.learning.source_message_id)}</code>` : esc(version.source)} · ${esc(version.updated_at)}${version.truncated ? ' · truncated' : ''}</p>
            ${page.reviews.filter(review => review.fact_id === version.id || review.result_id === version.id).map(review => `<p class="hint">${esc(review.actor === 'automatic-explicit-format/v1' ? 'Automatic formatting decision' : `${review.action} · ${review.actor}`)} · ${esc(review.created_at)}${review.note ? ` · ${esc(review.note)}` : ''}</p>`).join('')}</article>`).join('')}
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
// A pending specialist question is announced once, when its task card first shows it.
const seenTaskQuestions = new Set();

function welcomeHtml() {
  const b = botsCache.find(x => x.name === currentStudioBot);
  if (!b) return "";
  const description = String(b.description || "").trim();
  return `
    <div class="welcome">
      <div class="welcome-hero">
        <div class="hero-agent" id="hero-agent" aria-hidden="true">
          ${avatarFromPair(sigilPair(b.name), 160)}
        </div>
        <h2>${esc(botDisplayName(b))}</h2>
        ${description ? `<p class="hint">${esc(description)}</p>` : ""}
      </div>
      <p class="welcome-intro">Send me a message below. I’ll ask before anything that needs your okay.</p>
      <details class="tpl-gal" id="tpl-gal" hidden>
        <summary class="tpl-gal-summary">
          <span class="tpl-gal-copy">
            <span class="tpl-gal-title">Create a helper from an example</span>
            <span class="tpl-gal-subtitle">Optional setup; message below to start a task.</span>
          </span>
          ${icon("caret", "tpl-gal-caret")}
        </summary>
        <p class="tpl-gal-note">Choosing an example opens setup; it won’t start a task.</p>
        <div class="tpl-grid" id="tpl-grid"></div>
      </details>
    </div>`;
}

const TEMPLATE_TITLES = {
  "personal-assistant": "Personal assistant",
  "day-planner": "Day planner",
  "inbox-followups": "Inbox and follow-ups",
  "research-decisions": "Research and decisions",
  "project-coordinator": "Project coordinator",
  "meeting-followthrough": "Meeting follow-through",
  "document-workbench": "Document workbench",
  "data-brief": "Data brief",
};
const TEMPLATE_GALLERY_ORDER = [
  "personal-assistant", "day-planner", "inbox-followups", "research-decisions",
  "project-coordinator", "meeting-followthrough", "document-workbench", "data-brief",
];

async function wireWelcome() {
  /* Explore-agents gallery: real templates from the API, fetched lazily —
     never seeded. Picking one opens the create dialog with it preselected. */
  try {
    const templates = await api("/bots/templates");
    const grid = $("#tpl-grid"), gal = $("#tpl-gal");
    if (!grid || !templates.length) return;
    const rankedTemplates = [...templates].sort((a, b) =>
      TEMPLATE_GALLERY_ORDER.indexOf(a.name) - TEMPLATE_GALLERY_ORDER.indexOf(b.name));
    grid.innerHTML = rankedTemplates.slice(0, 6).map((t, i) => {
      const ci = i % ID_COLORS.length;
      const si = hash32(t.name) % ID_HEADS.length;
      const title = TEMPLATE_TITLES[t.name] || t.name.replace(/[-_]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
      return `<button class="tpl-card" type="button" data-tpl="${esc(t.name)}" aria-label="Create ${esc(title)} helper from an example: ${esc(t.tagline || t.description || "")}">
        <span class="tpl-tile">${avatarFromPair([ci, si], 36)}</span>
        <span class="tpl-copy"><span class="tpl-name">${esc(title)}</span><span class="tpl-tag">${esc(t.tagline || t.description || "")}</span></span>
        ${icon("arrow", "tpl-go")}
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
function runMirrorNoticeHtml(mirror) {
  return mirror?.error || mirror?.worker_error
    ? `<p class="run-notice" role="status">Transcript file needs attention: ${esc(mirror.error || mirror.worker_error)}. Database history remains available.</p>`
    : mirror?.pending ? '<p class="hint" role="status">Transcript file is catching up. History shown here is committed in the database.</p>' : "";
}

async function runBlockHtml(runId, messages = null, workspaceTasks = [], codeHandoffs = [], snapshot = null) {
  const run = snapshot || await api(`/runs/${runId}`);
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
  const sourceBot = botsCache.find(bot => bot.id === run.bot_id);
  const correctionKey = botMessage ? `${run.conversation_id}:${botMessage.id}` : "";
  const pendingCorrectionKey = [...pendingAnswerCorrections].find(key => key.startsWith(`${correctionKey}:`)) || "";
  const correctionBusy = !!pendingCorrectionKey;
  const correctionBusyKind = pendingCorrectionKey.split(":").at(-1);
  const answerFeedback = botMessage?.persona_feedback || null;
  const feedbackRevision = Number(answerFeedback?.revision || 0);
  const feedbackRating = answerFeedback?.rating || "";
  const feedbackReason = answerFeedback?.reason || "";
  const feedbackPending = !!botMessage && pendingAnswerFeedbackUpdates.has(`${run.conversation_id}:${botMessage.id}`);
  const correctionActions = run.status === "succeeded" && botMessage?.content && botMessage.content.length <= 12_000
    && !waitingForChoice && sourceBot?.runtime === "builtin" && sourceBot?.adaptive_persona_enabled !== false
    ? `<button class="btn ghost small" type="button" data-answer-correction="shorter" data-answer-message="${esc(botMessage.id)}"
          aria-label="Make this answer shorter; tools and external actions will not be repeated" ${correctionBusy ? 'aria-disabled="true" aria-busy="true"' : ""}>${correctionBusyKind === "shorter" ? "Starting…" : "Shorter"}</button>
       <button class="btn ghost small" type="button" data-answer-correction="go_deeper" data-answer-message="${esc(botMessage.id)}"
          aria-label="Go deeper on this answer; tools and external actions will not be repeated" ${correctionBusy ? 'aria-disabled="true" aria-busy="true"' : ""}>${correctionBusyKind === "go_deeper" ? "Starting…" : "Go deeper"}</button>
       <button class="btn ghost small" type="button" data-answer-correction="less_banter" data-answer-message="${esc(botMessage.id)}"
          aria-label="Rewrite this answer with less banter; tools and external actions will not be repeated" ${correctionBusy ? 'aria-disabled="true" aria-busy="true"' : ""}>${correctionBusyKind === "less_banter" ? "Starting…" : "Less banter"}</button>` : "";
  const replyAction = botMessage ? `<div class="answer-actions" data-answer-actions role="group"
      aria-label="Adjust this answer. Rewrites do not run tools or external actions again.">
      ${correctionActions}<button class="btn ghost small" type="button" data-reply-message="${esc(botMessage.id)}" aria-label="Reply to ${esc(botName)} message">Reply to this</button></div>` : "";
  const feedbackReasons = [["accuracy", "Accuracy"], ["relevance", "Relevance"], ["completeness", "Completeness"],
    ["depth", "Depth"], ["tone_or_humor", "Tone or humor"], ["safety", "Safety or boundaries"], ["other", "Other"]];
  const feedbackActions = run.status === "succeeded" && botMessage?.content && botMessage.content.length <= 12_000
    && !waitingForChoice && sourceBot?.runtime === "builtin" && sourceBot?.adaptive_persona_enabled !== false
    ? `<div class="answer-feedback" data-answer-feedback role="group" aria-label="Local answer feedback">
        <span class="answer-feedback-prompt">Was this answer useful?</span>
        <button class="btn ghost small" type="button" data-answer-feedback-rating="helpful"
          data-feedback-message="${esc(botMessage.id)}" data-feedback-revision="${feedbackRevision}"
          aria-pressed="${feedbackRating === "helpful"}" ${feedbackPending ? 'aria-disabled="true" aria-busy="true"' : ""}>Helpful</button>
        <button class="btn ghost small" type="button" data-answer-feedback-rating="needs_work"
          data-feedback-message="${esc(botMessage.id)}" data-feedback-revision="${feedbackRevision}"
          data-feedback-reason="${feedbackReason}" aria-pressed="${feedbackRating === "needs_work"}"
          ${feedbackPending ? 'aria-disabled="true" aria-busy="true"' : ""}>Needs work</button>
        ${feedbackRating === "needs_work" ? `<label class="answer-feedback-reason"><span>Optional reason</span>
          <select data-answer-feedback-reason data-feedback-message="${esc(botMessage.id)}"
            data-feedback-revision="${feedbackRevision}" aria-label="Optional reason for feedback"
            ${feedbackPending ? 'aria-disabled="true" aria-busy="true"' : ""}><option value="">No specific reason</option>${feedbackReasons.map(([value, label]) =>
              `<option value="${value}" ${feedbackReason === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>` : ""}
        ${feedbackRating ? `<button class="btn ghost small" type="button" data-answer-feedback-rating=""
          data-feedback-message="${esc(botMessage.id)}" data-feedback-revision="${feedbackRevision}"
          aria-label="Clear answer feedback" ${feedbackPending ? 'aria-disabled="true" aria-busy="true"' : ""}>Clear</button>` : ""}
        <span class="answer-feedback-note" role="status" aria-live="polite">${feedbackPending ? "Saving locally…" : feedbackRating ? "Feedback saved locally; never changes saved response style." : "Local only; never changes saved response style."}</span>
      </div>` : "";
  const createBotAction = userMessage ? `<div class="request-actions"><button class="btn ghost small" type="button"
      data-create-bot-from-request="${esc(userMessage.id)}" aria-label="Create a bot from this request">Make a bot</button></div>` : "";
  const coordinator = botsCache.find(bot => bot.name === currentStudioBot);
  const prepareTaskAction = coordinator?.is_workspace_coordinator && run.status === "succeeded"
    && userMessage && botMessage && !waitingForChoice
    ? `<button class="btn ghost small" type="button" data-prepare-bot-task
        data-source-run="${esc(runId)}" data-source-user="${esc(userMessage.id)}"
        data-source-answer="${esc(botMessage.id)}" data-source-request="${esc(run.prompt)}">Prepare for a Bot</button>` : "";
  const relatedTasks = workspaceTasks.filter(task => task.source_run_id === runId).map(workspaceTaskCardHtml).join("");
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
  // Sent images render in the transcript from the run's recorded attachments
  // (run_view flows the model_dump), so what was attached stays reviewable.
  const sentImages = Array.isArray(run.image_attachments) ? run.image_attachments : [];
  const bubbleImages = sentImages.length
    ? `<div class="bubble-images" role="group" aria-label="Images attached to this message">${sentImages.map(attachment => {
        const src = `/api/v1/conversations/${encodeURIComponent(run.conversation_id)}/uploads/${encodeURIComponent(attachment.id)}/content`;
        return `<a class="bubble-image" href="${src}" target="_blank" rel="noopener"
            title="Open ${esc(attachment.filename)} full size">
          <img src="${src}" alt="${esc(attachment.filename)}" loading="lazy" decoding="async">
        </a>`;
      }).join("")}</div>`
    : "";
  const stepCount = events.filter(e => e.type === "tool_call").length;

  const html = `
    <article class="thread${anim}" data-run-id="${esc(runId)}">
      <div class="msg you">
        <div class="bubble">${replyPreview}${workspaceResultPreview}${bubbleImages}${esc(run.prompt)}</div>
        <span class="stamp">${timeAgo(run.created_at)}${run.origin === "schedule" ? " · scheduled" : ""}</span>
        ${createBotAction}
      </div>
      <div class="msg agent">
        <div class="mhead">
          ${botAvatar(sourceBot?.name || run.bot_name || currentStudioBot || botName, 26, run.status === "running" ? "running" : "")}
          <b>${esc(botName)}</b>
          ${waitingForChoice
            ? statusChip("waiting_for_answer", "Waiting for your choice")
            : statusChip(run.status, run.status_label)}
          ${running ? `<button class="btn ghost small" data-stop-run="${esc(runId)}" ${run.status === "cancelling" ? "disabled" : ""}>${run.status === "cancelling" ? "Stopping" : "Stop"}</button>` : ""}
          <a class="mrun" href="#/run/${esc(runId)}" aria-label="View work details" title="View work details">${icon("fileText")}</a>
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
        ${message && message.data?.content ? `<div class="answer">${esc(message.data.content)}</div>${replyAction}${feedbackActions}${prepareTaskAction}${prepareCodeTaskAction}` : ""}
        ${groundingEntryHtml(events, runId)}
        ${relatedTasks}
        ${relatedCodeTasks}
        ${choiceCards.join("")}
        <div data-run-mirror-notice="${esc(runId)}">${runMirrorNoticeHtml(run.transcript_mirror)}</div>
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

// A specialist's pending question is a needed input, not a produced result. The
// card answers it in place through the specialist conversation's single-resolution
// question endpoint; the task keeps the exchange in its own audit surface.
function workspaceTaskQuestionHtml(task) {
  const question = task.pending_question;
  const options = Array.isArray(question.options) ? question.options : [];
  const multi = question.selection_mode === "multiple";
  let selected = [];
  try {
    const stored = JSON.parse(storageGet(choiceDraftKey(currentConversationId, question.id)) || "[]");
    if (Array.isArray(stored)) selected = stored.filter(value => options.some(option => option.id === value));
  } catch { /* ignore a damaged local draft and render the durable question */ }
  const controls = options.map(option => `<label class="choice-option">
      <input data-choice-option type="${multi ? "checkbox" : "radio"}" name="question-${esc(question.id)}" value="${esc(option.id)}" ${selected.includes(option.id) ? "checked" : ""} ${multi ? "" : "required"}>
      <span>${esc(option.label)}</span>
    </label>`).join("");
  return `<section class="workspace-task-question" data-workspace-task-question="${esc(task.id)}"
      aria-label="Question from ${esc(task.target_display_name)}">
    <form class="choice-card" data-workspace-question-form data-conversation-id="${esc(task.child_conversation_id)}"
          data-question-id="${esc(question.id)}">
      <div class="choice-card-head"><span class="choice-kicker">Question from ${esc(task.target_display_name)}</span>
        <span class="choice-state">${multi ? "Choose any that fit" : "Choose one"}</span></div>
      <fieldset class="choice-options"><legend class="choice-question">${esc(question.question)}</legend>${controls}</fieldset>
      <p class="hint">Your answer goes to ${esc(task.target_display_name)}’s own chat. It is a preference, not approval for an action.</p>
      <p class="choice-error" data-choice-error role="status" aria-live="polite"></p>
      <button class="btn primary choice-submit" type="submit">Send answer</button>
    </form>
  </section>`;
}

function workspaceTaskCardHtml(task) {
  const active = ACTIVE.has(task.status);
  const needsAnswer = task.status === "needs_input" && Boolean(task.pending_question);
  const statusLabel = needsAnswer ? "Needs your answer"
    : (statusInfo[task.status]?.label || task.status || "Status unavailable");
  const questionHtml = needsAnswer ? workspaceTaskQuestionHtml(task) : "";
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
    ${questionHtml}
    ${task.result && !needsAnswer ? `<div class="workspace-task-result"><b>Latest specialist response</b><p>${esc(task.result)}${task.result_truncated ? "… [preview truncated]" : ""}</p></div>` : ""}
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
      ${active ? `<button class="btn ghost small" type="button" data-stop-run="${esc(task.current_run_id || task.child_run_id)}">Stop specialist</button>` : ""}
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
    ? `<p class="hint">First connect a provider once with <code>hutch code login</code>. Then run this command in a terminal on the Linux Hutch host and review OpenCode’s permission prompts.</p>
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
      <p class="hint">Pinned base: <code>${esc(String(task.base_commit || "").slice(0, 12))}</code> · OpenCode ${esc(task.opencode_version || "version checked at launch")}. The provider connection and model usage belong to OpenCode, not Hutch’s budgets. Hutch stores this connection in a private profile separate from your regular OpenCode setup. Hutch asks you to review the handoff before launch. Once launched, OpenCode shell commands run with your Linux user’s authority and each command must be reviewed there. Hutch does not inspect or approve that CLI’s commands.</p>
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
      <p class="hint"><b>Before launch:</b> Run <code>hutch code login</code> once on the Linux Hutch host to connect a provider. Hutch stores it in a private OpenCode profile; it does not copy your regular OpenCode sign-in. The task card will show the launch command.</p>
      <blockquote class="workspace-task-source"><b>Your original request</b><br>${esc(originalRequest)}</blockquote>
      <label class="field">Reviewed coding task<textarea id="code-task-brief" rows="7" maxlength="20000" aria-describedby="code-task-brief-help">${esc(answer.content)}</textarea>
        <span class="hint" id="code-task-brief-help">This is a draft from ${esc(botDisplayName(bot))}. Review or rewrite it; it does not grant extra access.</span></label>
      <p class="hint"><b>Project:</b> ${esc(projectName)} · the task starts from its saved Git commit in a new isolated worktree. Uncommitted and untracked files from the source folder are not copied.</p>
      <p class="hint"><b>How launch works:</b> Hutch prepares and saves the handoff. You launch it from a terminal on the Linux computer running Hutch; the browser cannot start a local terminal for you.</p>
      <p class="hint"><b>OpenCode permissions:</b> Choose a model and review usage in OpenCode; costs are separate from Hutch’s budgets. Review each OpenCode prompt. Approved commands run with your Linux account’s filesystem, process and network access. Hutch does not broker or sandbox them.</p>
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
    if (it.kind === "tool" && it.result?.d?.workflow_recommendation) {
      flush();
      out.push(it); // keep a workflow card visible even when surrounding tools collapse
    } else if (it.kind === "tool") run.push(it);
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
  const workflowRecommendation = res?.d?.workflow_recommendation;
  const recommendationCard = workflowRecommendation && workflowRecommendation.route !== "direct"
    ? workflowRecommendationHtml(workflowRecommendation) : "";

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
      ${hutchWidgetsFeedItemHtml(res ? res.d : null, { runId })}
    </div>
    ${recommendationCard}
    ${includeFileAttachments ? createdFilesHtml(runId, [{ result: res }]) : ""}
  </div>`;
}

function workflowRecommendationHtml(recommendation) {
  const route = String(recommendation.route || "workflow").replaceAll("_", " ");
  const status = recommendation.status === "started" ? "Started within Auto scope"
    : recommendation.status === "suggested" ? "Suggestion · nothing started" : "Not started";
  const method = recommendation.suggested_plan_name
    ? `<p><b>${esc(recommendation.suggested_plan_name)}</b></p>` : "";
  const runButton = recommendation.status === "suggested" && recommendation.route === "saved_workflow"
      && recommendation.definition_id
    ? `<button class="btn primary small" type="button" data-workflow-suggestion-run="${esc(recommendation.definition_id)}">Review &amp; run</button>` : "";
  const refreshButton = recommendation.status === "started"
    ? '<button class="btn ghost small" type="button" data-workflow-suggestion-refresh>Refresh workflow activity</button>' : "";
  const reason = recommendation.why || "A workflow may fit this request.";
  const simpler = recommendation.simpler
    ? `<p class="workflow-recommendation-simpler">Simpler option: ${esc(recommendation.simpler)}</p>` : "";
  return `<section class="workflow-recommendation" aria-label="Workflow recommendation">
    <div><p class="workflow-panel-kicker">Workflow suggestion · ${esc(route)}</p><p class="workflow-recommendation-status">${esc(status)}</p></div>
    ${method}<p>${esc(reason)}</p>${simpler}
    ${recommendation.attempt_run_id ? `<p class="hint">Attempt ${esc(recommendation.attempt_run_id)}</p>` : ""}
    <div class="workflow-recommendation-actions">${runButton}${refreshButton}</div>
  </section>`;
}

/* PF-2 kept the untruncated output on disk; this row is the only door to it. */
function hutchWidgetsFeedItemHtml(data, helpers) {
  const widgets = window.HutchWidgets;
  if (!widgets || typeof widgets.blocksHtml !== "function") return "";
  try {
    return widgets.blocksHtml(data ? data.blocks : null, data ? data.block_errors : null,
      { runId: helpers ? helpers.runId : "" }) || "";
  } catch (err) {
    console.error("widget block render failed", err);
    return "";
  }
}

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
  const documents = items.map(it => it.result?.d?.document).filter(Boolean)
    .map(validDocumentRef).filter(Boolean);
  if (!files.length && !documents.length) return "";
  return `<div class="workspace-file-attachments" role="group" aria-label="Files created in this run">
    ${documents.map(documentAttachmentHtml).join("")}
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
    const feedback = ev.target.closest("[data-answer-feedback-rating]");
    if (feedback && feedback.getAttribute("aria-disabled") !== "true") {
      const rating = feedback.dataset.answerFeedbackRating || null;
      void activeAnswerFeedbackHandler?.(feedback.dataset.feedbackMessage, rating,
        rating === "needs_work" ? feedback.dataset.feedbackReason : null, feedback);
      return;
    }
    const correction = ev.target.closest("[data-answer-correction]");
    if (correction && correction.getAttribute("aria-disabled") !== "true") {
      void activeAnswerCorrectionHandler?.(correction.dataset.answerMessage, correction.dataset.answerCorrection, correction);
      return;
    }
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
    const suggestedRun = ev.target.closest("[data-workflow-suggestion-run]");
    if (suggestedRun) {
      void startSavedWorkflow(suggestedRun.dataset.workflowSuggestionRun, suggestedRun);
      return;
    }
    if (ev.target.closest("[data-workflow-suggestion-refresh]")) {
      void refreshWorkflowPanel(currentStudioBot, currentConversationId, studioGeneration, true);
      return;
    }
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
    const questionForm = form ? null : ev.target.closest("[data-workspace-question-form]");
    if (!form && !questionForm) return;
    ev.preventDefault();
    if (questionForm) {
      void activeWorkspaceQuestionSubmitHandler?.(questionForm);
      return;
    }
    void activeChoiceSubmitHandler?.(form);
  });
  stream.addEventListener("change", ev => {
    const feedbackReason = ev.target.closest("[data-answer-feedback-reason]");
    if (feedbackReason && feedbackReason.getAttribute("aria-disabled") !== "true") {
      void activeAnswerFeedbackHandler?.(feedbackReason.dataset.feedbackMessage, "needs_work",
        feedbackReason.value || null, feedbackReason);
      return;
    }
    const input = ev.target.closest("[data-choice-option]");
    const form = input?.closest("[data-choice-form]");
    const workspaceForm = form ? null : input?.closest("[data-workspace-question-form]");
    if (!form && !workspaceForm) return;
    const selected = [...(form || workspaceForm).querySelectorAll("input:checked")].map(item => item.value);
    const questionId = form ? form.dataset.choiceQuestion : workspaceForm.dataset.questionId;
    storageSet(choiceDraftKey(currentConversationId, questionId), JSON.stringify(selected));
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
    target.textContent = formatApprovalTtl(ms);
  });
}
setInterval(updateTtls, 1000);

/* --------------------------------------------------------- approvals card */

function approvalReasonText(rule, tool) {
  const value = String(rule || "").trim().toLowerCase();
  if (value === "ask:paid-context-compaction") {
    return "A paid model call would summarize earlier conversation text. Review its estimated cost and covered context.";
  }
  if (value.startsWith("rule:")) return "A rule you set asks you to review this action.";
  if (["ask:file-write", "ask-file-write"].includes(value)) {
    return "Changing a file needs your okay.";
  }
  if (["ask:rm", "shell:rm"].includes(value)) return "This command could remove files.";
  if (value.startsWith("ask:git-push") || value === "shell:git-push") {
    return "This command could send repository changes outside this computer.";
  }
  if (value.startsWith("ask:git-") || value === "shell:git") {
    return "This command changes the Git repository.";
  }
  if (value === "delegation:always-review") return "Starting a separate assistant task always needs your okay.";
  if (value.includes("hosted-model")) return "This sends the task to a hosted AI service.";
  if (value.startsWith("ask:program:")) return "This command can change files or system settings.";
  const service = { files: "file change", shell: "command", browser: "browser action", memory: "saved note" }[tool];
  return service ? `This ${service} needs your review.` : "A safety check asks you to review this action.";
}

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
  const toolLabel = tool === "context_compaction" ? "AI context summary" : tool;
  const formTarget = tool === "browser" && detailObject?.target_kind === "form_submit"
    && detailObject.target && typeof detailObject.target === "object" ? detailObject.target : null;
  const deadline = a.deadline
    || (a.expires_at ? new Date(a.expires_at).getTime()
      : (a.created_at ? new Date(a.created_at).getTime() + 10 * 60 * 1000 : 0));
  const expired = deadline && deadline <= Date.now();
  const ttlText = expired ? "expired — denied" : (deadline ? formatApprovalTtl(deadline - Date.now()) : "");
  const detail = !formTarget && a.detail && Object.keys(a.detail || {}).length ? JSON.stringify(a.detail, null, 2) : "";
  const segments = a.segments || [];
  const stickyKey = a.sticky_key || "";
  const canAlways = !!(stickyKey && !outward);
  const runId = a.run_id || "";
  const contextHref = a.conversation_id ? `#/conversation/${encodeURIComponent(a.conversation_id)}` : `#/run/${encodeURIComponent(runId)}`;

  const summaryRows = tool === "context_compaction" ? [
    ["Model", detailObject?.model],
    ["Estimated USD", detailObject?.estimated_cost_usd === null || detailObject?.estimated_cost_usd === undefined
      ? "unknown" : fmtUsd(detailObject.estimated_cost_usd)],
    ["Input / output allowance", `${Number(detailObject?.input_tokens_estimate || 0).toLocaleString()} input tokens · ${Number(detailObject?.max_output_tokens || 0).toLocaleString()} output tokens max`],
    ["Price quote", `${detailObject?.quote_source || "unknown"}${detailObject?.quote_fetched_at ? ` · fetched ${String(detailObject.quote_fetched_at).slice(0, 19)}` : ""}${detailObject?.quote_expires_at ? ` · expires ${String(detailObject.quote_expires_at).slice(0, 19)}` : ""}${detailObject?.quote_stale ? " · stale" : ""}`],
    ["Eligible endpoints", Array.isArray(detailObject?.eligible_endpoints) && detailObject.eligible_endpoints.length
      ? `${detailObject.eligible_endpoints.length} considered; reservation uses the highest estimate` : "not reported"],
    ["Content", detailObject?.content_scope || "earlier conversation context"],
    ["Original history", detailObject?.original_history_preserved ? "remains unchanged" : "status unavailable"],
  ].filter(([, value]) => value !== null && value !== undefined) : [];
  const rows = [
    ["Tool", toolLabel],
    ["Approval ID", id],
    ...summaryRows,
    formTarget ? ["Destination", formTarget.destination || "unknown destination"] : null,
    formTarget ? ["Request method", String(formTarget.method || "get").toUpperCase()] : null,
    formTarget ? ["Submit control", formTarget.label || "Submit form"] : null,
    a.account ? ["Account", a.account] : null,
    a.destination ? ["Destination", a.destination] : null,
    a.revision ? ["Revision", a.revision] : null,
    rule && !formTarget ? ["Why you are asked", approvalReasonText(rule, tool)] : null,
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
          ${toolLabel ? `<span class="tag">${esc(toolLabel)}</span>` : ""}
          <span class="tag ${risk === "high" ? "danger" : ""}">${esc(risk)} risk</span>
          ${outward ? `<span class="tag danger" title="Leaves this machine; always-allow is not offered">leaves machine</span>` : ""}
        </div>
        <span class="ttl-countdown">${icon("hourglass")}<span data-ttl-text>${esc(ttlText)}</span></span>
      </div>
      <div class="approval-action-text" id="approval-action-${esc(id)}">${esc(action)}</div>
      <span class="visually-hidden" id="approval-id-${esc(id)}">Approval ID <code class="mono">${esc(id)}</code></span>
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
        ${detail ? `<details class="approval-raw"><summary>Technical details</summary>
          <span class="review-label">Exact request data</span><pre class="approval-detail" tabindex="0" aria-label="Exact request arguments">${esc(detail)}</pre>
        </details>` : ""}
      </details>
      ${canAlways
        ? `<p class="hint approval-scope">Always-allow remembers <code class="mono">${esc(stickyKey)}</code> for this bot. Revoke it any time in the bot's standing permissions.</p>`
        : outward
          ? `<p class="hint approval-scope">This action leaves the machine, so always-allow is not offered — you decide each time.</p>`
          : ""}
      <div class="approval-buttons" data-approval="${esc(id)}">
        <button class="btn primary small" data-approve="1" aria-describedby="approval-action-${esc(id)} approval-id-${esc(id)}">Allow once</button>
        ${canAlways ? `<button class="btn ghost small" data-approve="always" aria-describedby="approval-action-${esc(id)} approval-id-${esc(id)}">Always allow for this bot</button>` : ""}
        <button class="btn ghost small" data-approve="0" aria-describedby="approval-action-${esc(id)} approval-id-${esc(id)}">Deny</button>
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
  const inConversation = isConversationView() && currentConversationId === conversationId;
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

async function renderOverview(preservePosition = false) {
  preservePosition = preservePosition === true;
  const renderedHash = location.hash || "#/chat";
  const oldPage = preservePosition ? view.querySelector(".page-scroll") : null;
  const oldActive = preservePosition && view.contains(document.activeElement) ? document.activeElement : null;
  const focusId = oldActive?.id || "";
  const focusHref = !focusId ? oldActive?.closest("a")?.getAttribute("href") || "" : "";
  const scrollTop = oldPage?.scrollTop || 0;
  const usageOpen = preservePosition && !!view.querySelector("#ov-usage-details")?.open;
  const [o, recentRuns] = await Promise.all([
    api("/overview"),
    api("/runs?limit=8").catch(() => []),
    // Overview rows carry only the Bot slug; on a direct visit the roster may not
    // have loaded yet, and names would fall back to storage IDs.
    botsCache.length ? null : refreshRoster(),
  ]);
  if ((location.hash || "#/chat") !== renderedHash) return;
  const s = o.stats || {};
  const fmt = (n) => Number(n || 0).toLocaleString();
  setTopContext(`<div class="ctx-id"><h1>Activity</h1></div>`);
  const row = (r) => `
    <a class="ov-row" href="#/run/${esc(r.id)}">
      <span class="ov-row-main"><b>${esc(botDisplayName(r.bot_display_name || r.bot_name))}</b>${statusChip(r.status)}</span>
      <span class="ov-row-prompt">${esc(truncate(r.prompt || "", 90))}</span>
      <span class="ov-row-meta">${timeAgo(r.created_at)}</span>
    </a>`;
  const waitBox = (w) => w && w.cause ? `<div class="ov-wait banner ${esc(w.kind || "wait")}"><b>Why:</b> ${esc(w.cause)}<br><b>What to do:</b> ${esc(w.fix)}</div>` : "";
  const approvalToolName = (tool) => {
    const labels = {
      gmail_send: "Gmail", gmail_read: "Gmail", google_calendar_events: "Google Calendar",
      google_calendar_create_event: "Google Calendar", outlook_send: "Outlook", outlook_read: "Outlook",
      browser: "Browser", shell: "Computer commands", web_fetch: "Web access",
      read_file: "Workspace files", write_file: "Workspace files", list_files: "Workspace files",
      context_compaction: "AI context summary",
    };
    return labels[tool] || BOT_SETUP_TOOLS.find(([name]) => name === tool)?.[1]
      || String(tool || "Action").replace(/[_-]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
  };
  const needsCount = Number(o.needs_count || 0);
  const running = o.running || [];
  const stale = o.stale || [];
  const sections = [];
  if (needsCount) sections.push(`
    <section class="ov-col loud">
      <h2 class="ov-h">${icon("inbox")} Needs you <span class="count">${needsCount}</span></h2>
      ${(o.approvals || []).map(a => `
        <a class="ov-approval" href="#/approvals">
          <span class="ov-approval-head"><b>${esc(botDisplayName(a.bot_display_name || a.bot_name))}</b> <span class="tag">${esc(approvalToolName(a.tool))}</span> <span class="tag ${a.risk === "high" ? "danger" : ""}">${esc(a.risk)} risk</span></span>
          <span class="ov-approval-action">${esc(a.action)}</span>
        </a>`).join("")}
      ${(o.humans || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
      ${(o.failures || []).map(r => `<div class="ov-item">${row(r)}${waitBox(r.wait)}</div>`).join("")}
    </section>`);
  if (running.length) sections.push(`
    <section class="ov-col">
      <h2 class="ov-h">${icon("play")} Working now <span class="count">${running.length}</span></h2>
      ${running.map(row).join("")}
    </section>`);
  if (stale.length) sections.push(`
    <section class="ov-col">
      <h2 class="ov-h">${icon("clock")} Schedule check <span class="count">${stale.length}</span></h2>
      ${stale.map(x => `
        <a class="ov-row" href="#/bot/${esc(x.bot_name)}">
          <span class="ov-row-main"><b>${esc(botDisplayName(x.bot_display_name || x.bot_name))}</b><span class="status stale">Needs a look</span></span>
          <span class="ov-row-meta">Last completed ${timeAgo(x.last_success)}</span>
        </a>`).join("")}
    </section>`);
  const activity = sections.length ? `<div class="ov-grid ov-grid-active">${sections.join("")}</div>` : `
    <section class="ov-all-clear" aria-labelledby="ov-all-clear-title">
      <span class="ov-all-clear-icon">${icon("check", "icon-lg")}</span>
      <div class="ov-all-clear-copy">
        <h2 id="ov-all-clear-title">No open tasks need your attention</h2>
        <p>Your assistants are quiet right now. Start a chat when you need help, or revisit something you’ve already sent.</p>
      </div>
      <div class="ov-all-clear-actions">
        <a class="btn primary" href="#/chat">Start a chat</a>
        <a class="btn ghost" href="#/runs">View past work</a>
      </div>
    </section>`;
  const recent = recentRuns.filter(run => run.terminal).slice(0, 3);
  view.innerHTML = `
    <div class="page-scroll"><div class="container activity-page">
      ${activity}
      <div class="ov-stats ov-summary-stats">
        <div class="kpi"><span class="kpi-label">Assistants</span><span class="kpi-val">${fmt(s.bots)}</span></div>
        <div class="kpi"><span class="kpi-label">Tasks today</span><span class="kpi-val">${fmt(s.runs_today)}</span></div>
      </div>
      <details class="ov-usage-details" id="ov-usage-details">
        <summary id="ov-usage-summary"><span>Usage details</span><span>Model tokens and cost</span></summary>
        <div class="ov-stats ov-usage-stats">
          <div class="kpi"><span class="kpi-label">Reported model tokens today</span><span class="kpi-val">${fmt(s.tokens_today)}</span></div>
          <div class="kpi"><span class="kpi-label">Recorded provider cost today</span><span class="kpi-val">${fmtUsd(s.spend_today || 0)}</span></div>
        </div>
      </details>
      ${recent.length ? `<section class="ov-recent" aria-labelledby="ov-recent-title">
        <h2 class="ov-h" id="ov-recent-title">${icon("clock")} Recent work</h2>
        ${recent.map(row).join("")}
      </section>` : ""}
    </div></div>`;
  if (preservePosition) {
    const nextPage = view.querySelector(".page-scroll");
    if (nextPage) nextPage.scrollTop = scrollTop;
    const nextDetails = view.querySelector("#ov-usage-details");
    if (nextDetails) nextDetails.open = usageOpen;
    let nextFocus = focusId ? document.getElementById(focusId) : null;
    if (!nextFocus && focusHref) {
      nextFocus = Array.from(view.querySelectorAll("a")).find(anchor => anchor.getAttribute("href") === focusHref) || null;
    }
    nextFocus?.focus({ preventScroll: true });
  }
}

/* -------------------------------------------------------------- schedules */

const SCHEDULE_PAGE_SIZE = 100;
let scheduleOverview = { rows: [], bots: [], control: null, hasMore: false, generation: 0 };
let scheduleControlPending = false;
const schedulePaintSnapshots = new WeakMap();

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
  if (row.blocked?.reason) return "Needs repair";
  if (row.enabled === false) return "Draft";
  if (row.workspace_paused && row.paused) return "Paused";
  if (row.workspace_paused) return "Paused for now";
  if (row.paused) return "Paused for this assistant";
  return "On";
}

function scheduleTriggerLabel(row) {
  if (row.trigger === "interval" && row.interval_seconds) {
    const minutes = row.interval_seconds / 60;
    if (Number.isInteger(minutes)) return `Every ${minutes} minutes`;
    return `Every ${row.interval_seconds} seconds`;
  }
  if (row.trigger === "once") return "One time";
  return row.cron || "Schedule unavailable";
}

function paintSchedules() {
  const restoreFocusId = document.activeElement?.id?.startsWith("schedule-")
    ? document.activeElement.id : null;
  const { rows, bots, control, hasMore } = scheduleOverview;
  const expanded = new Set($$('.schedule-overview-row').filter(row => row.querySelector('details')?.open)
    .map(row => row.dataset.scheduleId));
  const previousScroll = $('.page-scroll', view)?.scrollTop || 0;
  const paused = !!control?.paused;
  const empty = rows.length === 0;
  const emptyDetails = bots.length === 1
    ? `<a class="btn primary" href="#/bot/${encodeURIComponent(bots[0].name)}">Set up a schedule for ${esc(bots[0].display_name || bots[0].name)}</a>`
    : bots.length > 1
          ? `<details class="schedule-empty-bots" aria-label="Assistants available for scheduled work">
        <summary class="btn primary small">Choose an assistant ${icon("down", "schedule-empty-chevron")}</summary>
          <p class="hint">Choose where to create the recurring task.</p>
          <div class="schedule-empty-bot-list">${bots.map(bot => {
            const displayName = bot.display_name || bot.name;
            const setupLabel = `Set up ${displayName}`;
            return `<a class="btn ghost small" href="#/bot/${encodeURIComponent(bot.name)}" aria-label="${esc(setupLabel)}" title="${esc(displayName)}"><span>${esc(setupLabel)}</span></a>`;
          }).join("")}</div>
        </details>`
    : `<a class="btn primary" href="#/chat">Create an assistant</a>`;
  const headerHtml = `<div class="ctx-id"><h1>Scheduled work</h1></div>
    <div class="ctx-actions schedule-control-actions">
      <button class="switch" id="schedule-control-toggle" type="button" role="switch" aria-checked="${!paused}"
        ${scheduleControlPending ? 'aria-disabled="true" aria-busy="true"' : ""}>
        <span>Automatic starts</span><span class="switch-track" aria-hidden="true"></span><span class="switch-state" aria-hidden="true">${paused ? "Off" : "On"}</span>
      </button></div>`;
  const bodyHtml = `
    <div class="page-scroll"><div class="container schedule-overview">
      <p class="schedule-overview-note">See what’s coming up. Pausing prevents new scheduled starts; anything already in progress can finish.</p>
      ${paused ? `<p class="schedule-paused-note" role="status">Scheduled starts are paused. When you resume, each task follows its saved choice for missed times.</p>` : ""}
      ${empty ? `<section class="empty-state schedule-empty" aria-labelledby="schedule-empty-title">
          ${icon("clock", "icon-lg")}<h2 id="schedule-empty-title">No recurring tasks yet</h2>
          <p class="hint">Choose an assistant and pick a task you’d like them to repeat.</p>${emptyDetails}
        </section>` : `
        <div class="schedule-overview-heading"><h2>Upcoming scheduled work</h2>
          <span class="hint" role="status">${rows.length}${hasMore ? "+" : ""} task${rows.length === 1 ? "" : "s"}${hasMore ? " loaded" : ""}</span>
        </div>
        <div class="schedule-overview-list" role="list">
          ${rows.map(row => {
            const botLabel = row.bot_display_name || row.bot_name;
            const scheduleStatus = schedulePauseStatus(row);
            const missedTimeChoice = row.catch_up === "coalesce" ? "Run once for missed times" : "Skip missed times";
            const overlapChoice = row.overlap === "skip" ? "Skip while busy"
              : row.overlap === "buffer_one" ? "Keep one waiting" : "Queue while busy";
            return `<article class="schedule-overview-row" role="listitem" data-schedule-id="${esc(row.id)}">
              <div class="schedule-overview-task">
                <div class="schedule-overview-bot"><a href="#/chat/${encodeURIComponent(row.bot_name)}">${esc(botLabel)}</a>
                  <span class="tag">${esc(scheduleStatus)}</span></div>
                <h3>${esc(row.name)}</h3>
                <details class="schedule-overview-details"><summary>Timing details</summary>
                  <dl class="schedule-overview-timing">
                    <div><dt>Schedule</dt><dd><code>${esc(scheduleTriggerLabel(row))}</code></dd></div>
                    <div><dt>Time zone</dt><dd>${esc(row.timezone)}</dd></div>
                    <div><dt>If a time is missed</dt><dd>${esc(missedTimeChoice)}</dd></div>
                    <div><dt>If already busy</dt><dd>${esc(overlapChoice)}</dd></div>
                  </dl>
                </details>
                ${row.blocked?.reason ? `<p class="schedule-skip" role="status">Blocked: ${esc(row.blocked.reason.replaceAll("_", " "))}${row.blocked.detail ? ` (${esc(row.blocked.detail)})` : ""}. Repair the timezone or trigger before it can run.</p>` : ""}
                ${row.last_skip?.windows ? `<p class="schedule-skip" role="status">Last skipped ${Number(row.last_skip.windows).toLocaleString()} missed window${Number(row.last_skip.windows) === 1 ? "" : "s"}${row.last_skip.reason ? ` · ${esc(String(row.last_skip.reason).replaceAll("_", " "))}` : ""}${row.last_skip.at ? ` · ${esc(timeAgo(row.last_skip.at))}` : ""}.</p>` : ""}
              </div>
              <div class="schedule-overview-next"><span>${row.effective_paused ? "Next scheduled time" : "Next run"}</span>
                ${row.next_fire ? `<time datetime="${esc(row.next_fire)}">${esc(scheduleNextTime(row))}</time>` : `<strong>Unavailable</strong>`}
              </div>
              <div class="schedule-overview-actions">
                <button class="btn ghost small" type="button" data-schedule-run-now="${esc(row.bot_name)}/${esc(row.id)}">Run now</button>
                <button class="btn ghost small" type="button" data-schedule-skip-next="${esc(row.bot_name)}/${esc(row.id)}">Skip next</button>
                <a class="btn ghost small schedule-overview-edit" href="#/bot/${encodeURIComponent(row.bot_name)}">Edit schedule</a>
              </div>
            </article>`;
          }).join("")}
        </div>
        ${hasMore ? `<div class="schedule-overview-more"><button class="btn ghost" id="schedule-load-more" type="button">Load 100 more</button></div>` : ""}`}
    </div></div>`;

  // Reconciliation reads may finish after a command has already painted the
  // same state. Preserve the live rows, expanded details and focused controls.
  const previousPaint = schedulePaintSnapshots.get(view);
  if ($('.schedule-overview', view) && previousPaint?.headerHtml === headerHtml
      && previousPaint.bodyHtml === bodyHtml) return;
  const focused = document.activeElement;
  const focusedAttribute = ['data-schedule-run-now', 'data-schedule-skip-next']
    .find(attribute => focused?.hasAttribute(attribute));
  const focusedValue = focusedAttribute ? focused.getAttribute(focusedAttribute) : null;
  setTopContext(headerHtml);
  view.innerHTML = bodyHtml;
  schedulePaintSnapshots.set(view, {headerHtml, bodyHtml});
  $$('.schedule-overview-row').forEach(row => {
    if (expanded.has(row.dataset.scheduleId)) row.querySelector('details').open = true;
  });
  $('.page-scroll', view).scrollTop = previousScroll;

  const toggle = $("#schedule-control-toggle");
  toggle?.addEventListener("click", async () => {
    if (scheduleControlPending) return;
    scheduleControlPending = true;
    toggle.setAttribute("aria-disabled", "true");
    toggle.setAttribute("aria-busy", "true");
    try {
      const result = await api("/v1/schedules/control", { method: "PUT", body: { paused: !paused } });
      toast(result.paused ? "New scheduled starts are paused. Work already in progress can finish." : "Scheduled work has resumed. Assistant-specific pauses remain.");
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

  view.querySelectorAll("[data-schedule-run-now]").forEach(button => {
    button.addEventListener("click", async () => {
      const [botName, scheduleId] = button.getAttribute("data-schedule-run-now").split("/");
      button.setAttribute("aria-busy", "true");
      try {
        const result = await api(`/v1/bots/${encodeURIComponent(botName)}/schedules/${encodeURIComponent(scheduleId)}/run-now`, {
          method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() }, body: {},
        });
        toast(result?.workflow_run_id
          ? "Started the linked saved workflow once. The routine schedule is unchanged."
          : "Started a one-off run. The recurring schedule is unchanged.");
        if (result?.run_id) location.hash = `#/run/${encodeURIComponent(result.run_id)}`;
      } catch (error) {
        toast(`Could not run now: ${error.message}`, true);
      } finally {
        button.removeAttribute("aria-busy");
      }
    });
  });

  view.querySelectorAll("[data-schedule-skip-next]").forEach(button => {
    button.addEventListener("click", async () => {
      const [botName, scheduleId] = button.getAttribute("data-schedule-skip-next").split("/");
      button.setAttribute("aria-busy", "true");
      try {
        await api(`/v1/bots/${encodeURIComponent(botName)}/schedules/${encodeURIComponent(scheduleId)}/skip-next`, { method: "POST", body: {} });
        toast("The next scheduled occurrence will be skipped.");
        await renderSchedules();
      } catch (error) {
        toast(`Could not skip next: ${error.message}`, true);
      } finally {
        button.removeAttribute("aria-busy");
      }
    });
  });

  // Resource-feed refreshes can repaint this page while a schedule command is
  // resolving. Keep keyboard focus on the replacement control across either
  // repaint so background updates do not strand the user on the document.
  if (restoreFocusId) document.getElementById(restoreFocusId)?.focus({ preventScroll: true });
  else if (focusedAttribute) $$(`[${focusedAttribute}]`, view)
    .find(button => button.getAttribute(focusedAttribute) === focusedValue)?.focus({preventScroll: true});
}

async function renderSchedules() {
  if (location.hash !== '#/schedules') return;
  const generation = ++scheduleOverview.generation;
  const routeAtStart = location.hash;
  const alreadyVisible = routeAtStart === "#/schedules" && !!$(".schedule-overview", view);
  if (!alreadyVisible) {
    setTopContext(`<div class="ctx-id"><h1>Scheduled work</h1></div>`);
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
  const requestedHash = location.hash;
  const generation = studioGeneration;
  if (requestedHash !== '#/bots') return;
  const bots = await api("/bots");
  if (location.hash !== requestedHash || studioGeneration !== generation) return;
  botsCache = bots;
  if (bots.length < 10) {
    history.replaceState(null, "", "#/chat");
    await renderChatStudio();
    return;
  }
  renderRoster();
  setTopContext(`<div class="ctx-id"><h1>Manage assistants</h1></div>
    <div class="ctx-actions"><button class="btn primary small" id="btn-new-bot-top" aria-label="New assistant" title="New assistant">${icon("plus")}<span class="fleet-create-full-label">New assistant</span><span class="fleet-create-compact-label" aria-hidden="true">New</span></button></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      ${bots.length ? `
      <div class="fleet-filters"><label class="field">Find an assistant<input id="fleet-search" type="search" placeholder="Search by name or task" enterkeyhint="search"></label>
        <label class="field">Show<select id="fleet-state"><option value="all">All assistants</option><option value="needs">Need your attention</option><option value="active">Working now</option><option value="paused">Paused</option></select></label></div>
      <p class="hint" id="fleet-count" role="status"></p>
      <div class="bot-grid">
        ${bots.map(b => `
          <article class="bot-card" data-fleet-bot="${esc(b.name)}">
            <div class="bot-head">
              ${botAvatar(b.name, 32, botState(b) === "running" ? "running" : b.paused ? "paused" : "")}
              <span class="bot-name" title="${esc(botHeading(b))}">${esc(botHeading(b))}</span>
              ${b.active_run_id ? statusChip(b.active_run_status, b.active_run_status_label) : `<span class="tag">${esc(botStatusLabel(b))}</span>`}
            </div>
            <p class="bot-desc">${esc(b.description || "Ready when you are.")}</p>
            <details class="bot-card-details">
              <summary><span class="bot-card-details-label">Details</span><span class="bot-card-details-hint">Settings and activity</span>${icon("down", "bot-card-details-chevron")}</summary>
              <div class="bot-facts">
                <div>AI service <b>${esc(b.model || "Not selected")}</b></div>
                <div>Schedule <b>${b.schedule ? esc(b.schedule.cron) : "No schedule"}</b></div>
                <div>Action access <b>${esc(botActionSummary(b.approval_mode))}</b></div>
                <div>Next run <b>${esc(b.next_run_local || "Not scheduled")}</b></div>
                <div>Last completed <b title="${esc(b.last_success || "")}">${b.last_success ? timeAgo(b.last_success) : "Not yet"}</b></div>
                <div>Estimated tokens today <b>${fmtTokens(b.tokens_today)}</b></div>
                <div>Saved notes <b>${b.memory_count}</b></div>
              </div>
            </details>
            <div class="card-actions">
              <a class="btn ghost small" href="#/chat/${esc(b.name)}" aria-label="Open chat with ${esc(b.display_name || b.name)}">${icon("chat")} Open</a>
              <details class="fleet-card-menu">
                <summary class="icon-btn" data-fleet-options="${esc(b.name)}" aria-label="More options for ${esc(b.display_name || b.name)}" title="More options">${icon("moreHorizontal")}</summary>
                <div class="fleet-card-menu-panel" aria-label="More options for ${esc(b.display_name || b.name)}">
                  <button class="fleet-card-menu-item" type="button" data-action="toggle-pause" data-bot="${esc(b.name)}" data-paused="${b.paused}">
                    ${icon(b.paused ? "play" : "pause")} ${b.paused ? "Resume assistant" : "Pause assistant"}
                  </button>
                  <a class="fleet-card-menu-item" href="#/bot/${esc(b.name)}">${icon("sliders")} Assistant settings</a>
                </div>
              </details>
            </div>
          </article>
        `).join("")}
      </div>
      ` : `
      <div class="empty-state">
        ${icon("bot", "icon-lg")}
        <p><b>No assistants yet.</b></p>
        <p class="hint">Start with a request. Hutch will suggest a name and carry your words into setup.</p>
        <button class="btn primary" id="btn-create-first-bot">Create your first assistant</button>
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
    $("#fleet-count").textContent = `${visible} of ${bots.length} assistants`;
  };
  $("#fleet-search")?.addEventListener("input", filterFleet);
  $("#fleet-state")?.addEventListener("change", filterFleet);
  if ($("#fleet-search")) filterFleet();
  $("#btn-create-first-bot")?.addEventListener("click", () => void promptNewBot());
  $("#btn-new-bot-top")?.addEventListener("click", () => void promptNewBot());
  wireCommon();
}

/* -------------------------------------------------------------- runs list */

const RUNS_PAGE_SIZE = 25;
const RUNS_API_PAGE_SIZE = 50;
const RUNS_API_FETCH_SIZE = RUNS_API_PAGE_SIZE + 1;
let runsState = { all: [], status: "all", q: "", shown: RUNS_PAGE_SIZE, offset: 0,
  hasMore: false, loading: false, error: "", loaded: false };
let runsRequestGeneration = 0;

/* ------------------------------------------------------------------ grounded evidence panel
   Route: a compact entry under a grounded answer links here (run detail), where the full
   panel lives. Everything shown is stored evidence: what was asked, what each source is
   (with independence), which checks ran or failed, inspected media frames with exact
   timecodes, and every answer revision. Findings stay scoped; no universal truth badge. */

const GROUNDING_TOOLS = ["live_search", "inspect_media"];

function groundingSummary(events) {
  let checks = 0, media = 0;
  for (const e of events || []) {
    if (e.type !== "tool_result" || !GROUNDING_TOOLS.includes(e.data?.tool)) continue;
    checks += 1;
    if (e.data.tool === "inspect_media") media += 1;
  }
  return { checks, media };
}

const EVIDENCE_LABELS = {
  supported_in_context: ["Supported in this context", "ok"],
  contradicted_or_out_of_context: ["Contradicted / out of context", "bad"],
  materially_altered: ["Materially altered (with evidence)", "bad"],
  mixed_or_disputed: ["Mixed or disputed", "warn"],
  insufficient_evidence: ["Insufficient evidence", "plain"],
  unknown: ["Check did not run", "plain"],
};

const EVIDENCE_STATES = { ok: "ok", partial: "warn", zero_results: "plain", unavailable: "warn",
  blocked: "warn", disabled: "plain", rate_limited: "warn", timeout: "bad", error: "bad" };

function exactTime(ts) {
  if (!ts) return "time unknown in the source";
  if (!ts.instant) return ts.raw ? `${ts.raw} (unparsed)` : "time unknown";
  const label = ts.role === "occurrence" ? "event" : ts.role === "publication" ? "published"
    : ts.role === "index" ? "source seen" : ts.role === "retrieval" ? "fetched" : (ts.role || "time");
  const stamp = ts.instant.replace("T", " ").replace("+00:00", " UTC");
  return `${label} ${stamp}${ts.precision && ts.precision !== "second" ? ` (± ${ts.precision})` : ""}${ts.uncertain ? " · uncertain" : ""}`;
}

function groundingEntryHtml(events, runId) {
  const summary = groundingSummary(events);
  if (!summary.checks) return "";
  return `<a class="grounding-entry" href="#/run/${esc(runId)}?focus=evidence" data-grounding-entry>
    ${icon("search")}<span>Evidence</span>
    <span class="grounding-entry-meta">${summary.checks} live check${summary.checks === 1 ? "" : "s"}${summary.media ? ` · ${summary.media} media` : ""}</span></a>`;
}

function evidencePanelHtml(bundle) {
  const inv = bundle.investigation || {};
  const coverage = inv.coverage_json || {};
  const attempts = bundle.attempts || [];
  const sources = bundle.sources || [];
  const media = bundle.media || [];
  const observations = bundle.observations || [];
  const answers = bundle.answers || [];
  const latest = answers[answers.length - 1];
  const assessments = (latest && latest.body_json && latest.body_json.assessments) || {};
  const claims = bundle.claims || [];
  const citationOf = {};
  for (const [sid, handle] of Object.entries(coverage.citations || {})) citationOf[sid] = handle;
  const sample = coverage.sample || {};
  const claimBlocks = claims.map(claim => {
    const a = assessments[claim.id];
    const [labelText, tone] = EVIDENCE_LABELS[a?.label] || ["Not assessed", "plain"];
    const links = (bundle.evidence || []).filter(ev => ev.claim_id === claim.id);
    return `<div class="evidence-claim">
      <p class="evidence-claim-text">${esc(claim.text)}</p>
      <div class="evidence-claim-meta">
        <span class="ev-chip ${tone}">${esc(labelText)}</span>
        <span class="hint">${esc(claim.kind)}</span>
        ${links.length
          ? `<span class="hint">${links.map(l => `${esc(citationOf[l.source_id] || "S?")} ${esc(l.relation)}`).join(" · ")}</span>`
          : `<span class="hint">no evidence bound</span>`}
      </div>
      ${(a?.reasons || []).slice(0, 3).map(r => `<p class="evidence-reason">${esc(r)}</p>`).join("")}
    </div>`;
  }).join("");
  const outcomeRow = o => `<li class="evidence-outcome">
      <span class="ev-chip ${EVIDENCE_STATES[o.state] || "plain"}">${esc(o.state)}</span>
      <span class="evidence-outcome-name">${esc(o.adapter)}</span>
      <span class="hint">${Number.isFinite(o.retained) && Number.isFinite(o.returned) ? `${o.retained}/${o.returned} kept` : "no results kept"}${o.dropped_out_of_range ? ` · ${o.dropped_out_of_range} outside the frame` : ""}${o.dropped_undated ? ` · ${o.dropped_undated} undated` : ""}${(o.disabled_engines_json || []).length ? ` · engines disabled: ${esc((o.disabled_engines_json || []).join(", "))}` : ""}${o.freshness ? ` · ${esc(o.freshness)}` : ""}${Number.isFinite(o.latency_ms) && (o.latency_ms || 0) > 0 ? ` · ${Math.round(o.latency_ms)}ms` : ""}</span>
      ${o.detail ? `<span class="evidence-outcome-detail">${esc(o.detail)}</span>` : ""}
    </li>`;
  const sourceRows = sources.map(s => {
    const pub = s.published_json || null;
    const independence = s.independence === "independent" ? "independent origin"
      : s.independence === "same_origin" ? "same origin: copy, repost, or syndication"
      : "origin not established";
    return `<li class="evidence-source">
      <div class="evidence-source-head">
        <span class="ev-handle">${esc(citationOf[s.id] || "S?")}</span>
        <a class="evidence-source-title" href="${esc(s.canonical_url || s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.canonical_url || s.url)}</a>
      </div>
      <div class="evidence-source-meta">
        <span class="hint">${esc(s.adapter)}/${esc(s.lane)} · ${esc(s.origin || "origin unknown")}</span>
        <span class="hint" title="${esc((pub && pub.raw) || "no source time")}">${esc(exactTime(pub))}</span>
        <span class="hint">fetched ${esc((s.retrieved_at || "").replace("T", " ").slice(0, 19))} · ${esc(s.freshness)}${s.revision > 1 ? ` · revision ${s.revision}` : ""}</span>
        <span class="ev-chip ${s.independence === "independent" ? "ok" : "plain"}">${esc(independence)}</span>
        ${s.access_state && s.access_state !== "ok" ? `<span class="ev-chip warn">${esc(s.access_state)}</span>` : ""}
      </div>
      ${s.excerpt ? `<p class="evidence-source-excerpt">${esc(s.excerpt.slice(0, 280))}</p>` : ""}
      ${s.note ? `<p class="hint">${esc(s.note)}</p>` : ""}
    </li>`;
  }).join("");
  const mediaBlocks = media.map(m => {
    const frames = (m.frames || []).filter(f => f.available);
    const c2pa = m.c2pa_json || {};
    const transmitted = observations.filter(o => o.media_id === m.id && o.kind === "model_input").pop();
    const notes = observations.filter(o => o.media_id === m.id
      && ["limitation", "scope_statement", "sampling_plan", "claim_under_check"].includes(o.kind));
    const c2paTone = c2pa.state === "absent" ? "plain" : c2pa.state === "present_unverified" ? "warn" : "ok";
    return `<div class="evidence-media-item">
      <div class="evidence-source-head"><span class="ev-handle">${icon("layers")}</span>
        <span class="evidence-source-title">${esc(m.kind)} · ${esc(m.mime)} · ${esc((m.sha256 || "").slice(0, 12))}…</span></div>
      <div class="evidence-source-meta">
        <span class="hint">${esc((m.origin || "").slice(0, 120))}</span>
        <span class="ev-chip ${c2paTone}">C2PA: ${esc(c2pa.state || "absent")}</span>
        ${transmitted ? `<span class="hint">${esc(transmitted.text)}</span>` : ""}
      </div>
      ${frames.length
        ? `<div class="evidence-frames">${frames.map(f => `<figure class="evidence-frame">
            <img src="${esc(f.url)}" alt="${esc(`Frame inspected at ${(f.at_ms / 1000).toFixed(2)} seconds of the ${m.kind}`)}" loading="lazy" />
            <figcaption>${esc((f.at_ms / 1000).toFixed(2))}s</figcaption></figure>`).join("")}</div>`
        : `<p class="hint">No inspected frames are available for this item.</p>`}
      ${notes.map(o => `<p class="evidence-reason">${esc(o.text)}</p>`).join("")}
    </div>`;
  }).join("");
  const revisionRows = answers.slice().reverse().map((a, i) => `<li class="evidence-revision">
      <span class="hint">${esc((a.created_at || "").replace("T", " ").slice(0, 19))}</span>
      <span class="hint">effective ${esc((a.effective_as_of || "").replace("T", " ").slice(0, 19))}</span>
      <span class="ev-chip ${i === 0 ? "ok" : "plain"}">${i === 0 ? "current" : "earlier"}</span>
      <details class="evidence-revision-body"><summary>What Hutch recorded</summary><pre>${esc(((a.body_json || {}).text || "").slice(0, 1600))}</pre></details>
    </li>`).join("");
  const missing = coverage.missing || [];
  const asyncState = inv.as_of_instant
    ? `as of ${exactTime({ instant: inv.as_of_instant, role: "verification", precision: "second" })}`
    : `as of the request instant ${(inv.reference_instant || "").replace("T", " ").replace("+00:00", " UTC")}`;
  return `<section class="evidence-panel panel" aria-labelledby="evidence-title" data-evidence-panel>
    <div class="evidence-head">
      <h2 id="evidence-title">${icon("search")} Evidence</h2>
      <p class="hint">Effective ${esc(asyncState)} · zone ${esc(inv.user_timezone || "UTC")}${inv.horizon_hours ? ` · horizon ${inv.horizon_hours}h` : ""}${coverage.deadline_hit ? " · the deadline stopped remaining sources" : ""}${coverage.truncated ? " · source budget reached" : ""}</p>
      <button class="btn ghost small evidence-refresh" type="button" data-evidence-refresh>Refresh evidence</button>
    </div>
    <div class="evidence-split">
      <div class="evidence-split-cell"><h3>What was asked</h3><p>${esc(inv.question || "")}</p></div>
      <div class="evidence-split-cell"><h3>What the evidence shows</h3>
        ${claimBlocks || `<p class="hint">No claims were bound in this check.</p>`}
        <p class="evidence-disclaimer">Findings describe the evidence gathered in this window. They are not a universal verdict, and “insufficient evidence” is a valid result.</p>
      </div>
    </div>
    <div class="evidence-sample"><span class="hint">Observed sample: ${sample.raw_items || 0} retrieved · ${sample.unique_items || 0} unique · ${sample.distinct_origins || 0} origin cluster(s). Copies and reposts count once, and popularity is never corroboration.</span></div>
    ${attempts.length ? `<details class="evidence-block"><summary>Acquisition outcomes (${attempts.length})</summary><ul class="evidence-list">${attempts.map(outcomeRow).join("")}</ul></details>` : ""}
    ${missing.length ? `<details class="evidence-block"><summary>Coverage gaps (${missing.length})</summary><ul class="evidence-list">${missing.map(outcomeRow).join("")}</ul></details>` : ""}
    ${sources.length ? `<details class="evidence-block" open><summary>Sources (${sources.length})</summary><ul class="evidence-list">${sourceRows}</ul></details>` : ""}
    ${media.length ? `<details class="evidence-block"><summary>Media checks (${media.length})</summary>${mediaBlocks}</details>` : ""}
    ${answers.length ? `<details class="evidence-block"><summary>Answer revisions (${answers.length})</summary><ul class="evidence-list">${revisionRows}</ul></details>` : ""}
  </section>`;
}

async function renderEvidencePanel(runId, events, params) {
  const host = document.querySelector(`[data-evidence-host="${runId}"]`);
  if (!host || !groundingSummary(events).checks) return;
  const mount = (bundle) => {
    host.innerHTML = evidencePanelHtml(bundle);
    const button = host.querySelector("[data-evidence-refresh]");
    button?.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Refreshing…";
      try {
        await api(`/v1/investigations/${encodeURIComponent(bundle.investigation.id)}/refresh`,
                  { method: "POST", body: {} });
        const updated = await api(`/v1/tasks/runs/${encodeURIComponent(runId)}/investigation`);
        if (updated && updated.investigation) mount(updated);
      } catch (err) {
        button.disabled = false;
        button.textContent = "Refresh evidence";
        toast(`Could not refresh evidence: ${err.message}`, true);
      }
    });
  };
  try {
    const bundle = await api(`/v1/tasks/runs/${encodeURIComponent(runId)}/investigation`);
    if (!bundle || !bundle.investigation) return;
    mount(bundle);
    if (params && params.get("focus") === "evidence") {
      host.scrollIntoView({ block: "start", behavior: "auto" });
      const first = host.querySelector("details.evidence-block");
      if (first) first.open = true;
    }
  } catch (err) {
    host.innerHTML = `<p class="hint" role="status">Evidence could not be loaded: ${esc(String((err && err.message) || err))}</p>`;
  }
}

async function renderRuns(query = "") {
  const params = new URLSearchParams(query);
  runsState = {
    all: [],
    status: params.get("status") || "all",
    q: params.get("q") || "",
    shown: RUNS_PAGE_SIZE,
    offset: 0, hasMore: false, loading: false, error: "", loaded: false,
  };
  setTopContext(`<div class="ctx-id"><h1>Past work</h1></div>`);
  view.innerHTML = `
    <div class="page-scroll"><div class="container">
      <p class="runs-intro">See what your assistants have done. Open any task to review the full conversation and decisions.</p>
      <div class="runs-filter-bar">
        <label class="visually-hidden" for="run-search">Find a task or assistant</label>
        <input type="search" id="run-search" placeholder="Find a task or assistant…" value="${esc(runsState.q)}" enterkeyhint="search">
        <div class="runs-filter-pills" role="radiogroup" aria-label="Filter past work">
          ${["all", "succeeded", "failed", "waiting_approval"].map(f => `
            <label><input type="radio" name="runs-filter" value="${f}" ${runsState.status === f ? "checked" : ""}>
              ${f === "all" ? "All" : f === "succeeded" ? "Completed" : f === "failed" ? "Didn't finish" : "Waiting on you"}</label>`).join("")}
        </div>
        <span class="hint" id="runs-count" aria-live="polite" aria-atomic="true"></span>
      </div>
      <div class="runs-results" id="runs-table-wrap"></div>
    </div></div>`;

  const syncHash = () => {
    if (!location.hash.startsWith("#/runs")) return;
    const p = new URLSearchParams();
    if (runsState.status !== "all") p.set("status", runsState.status);
    if (runsState.q) p.set("q", runsState.q);
    history.replaceState(null, "", `#/runs${p.toString() ? `?${p}` : ""}`);
  };

  const renderRows = () => {
    const filtered = runsState.all;
    const wrap = $("#runs-table-wrap");
    if (!wrap) return;
    const restoreMoreFocus = document.activeElement?.id === "runs-more";
    const restoreRetryFocus = document.activeElement?.id === "runs-retry";
    if (runsState.error && !runsState.all.length) {
      wrap.classList.remove("runs-has-results");
      wrap.innerHTML = `<div class="empty-state" role="alert"><p>Past work could not be loaded.</p>
        <p class="hint">${esc(runsState.error)}</p><button class="btn ghost small" id="runs-retry" type="button">Try again</button></div>`;
      $("#runs-retry")?.addEventListener("click", () => { void loadPage({ reset: !runsState.all.length }); });
    } else if (!filtered.length && runsState.loading) {
      wrap.classList.remove("runs-has-results");
      wrap.innerHTML = `<div class="empty-state" role="status"><p>Loading past work…</p></div>`;
    } else if (!filtered.length) {
      wrap.classList.remove("runs-has-results");
      wrap.innerHTML = (runsState.q || runsState.status !== "all") ? `
        <div class="empty-state">
          ${icon("search", "icon-lg")}
          <p>No past work matches this filter.</p>
          <button class="btn ghost small" id="runs-clear">Clear filters</button>
        </div>` : `
        <div class="empty-state">
          ${icon("zap", "icon-lg")}
          <p><b>No past work yet.</b></p>
          <p class="hint">Tasks you start in a chat will show up here.</p>
          <a class="btn primary small" href="#/chat">Start a chat</a>
        </div>`;
      $("#runs-clear")?.addEventListener("click", () => {
        runsState = { ...runsState, status: "all", q: "", shown: RUNS_PAGE_SIZE };
        $("#run-search").value = "";
        const all = $('.runs-filter-pills input[value="all"]');
        if (all) all.checked = true;
        syncHash(); void loadPage({ reset: true });
      });
    } else {
      const rows = filtered.slice(0, runsState.shown);
      const moreLoaded = rows.length < filtered.length;
      const moreAvailable = moreLoaded || runsState.hasMore;
      wrap.classList.add("runs-has-results");
      wrap.innerHTML = `
        <div class="run-card-list" aria-label="Past work">
          ${rows.map(r => {
            const displayName = r.bot_display_name || r.bot_name;
            return `<a class="run-card" href="#/run/${esc(r.id)}">
              <div class="run-card-head">
                <span class="run-card-bot">${botAvatar(r.bot_name, 28)}<b title="${esc(r.bot_name)}">${esc(displayName)}</b></span>
                ${statusChip(r.status, r.status_label)}
              </div>
              <p class="run-card-prompt">${esc(r.prompt || "No task description saved.")}</p>
              <div class="run-card-foot"><time datetime="${esc(r.created_at || "")}">${timeAgo(r.created_at)}</time><span class="run-card-open">See what happened ${icon("arrow")}</span></div>
            </a>`;
          }).join("")}
        </div>
        ${runsState.error ? `<p class="hint" role="alert">Older tasks could not be loaded. ${esc(runsState.error)}
          <button class="btn ghost small" id="runs-retry" type="button">Try again</button></p>` : ""}
        ${moreAvailable ? `
          <button class="btn ghost small runs-more" id="runs-more" type="button" aria-busy="${runsState.loading}">
            ${runsState.loading ? "Loading older tasks…" : moreLoaded
              ? `Show ${Math.min(RUNS_PAGE_SIZE, filtered.length - runsState.shown)} more tasks`
              : "Load older tasks"}
          </button>` : ""}`;
      $("#runs-more")?.addEventListener("click", () => {
        if (moreLoaded) { runsState.shown += RUNS_PAGE_SIZE; renderRows(); }
        else void loadPage();
      });
      $("#runs-retry")?.addEventListener("click", () => { void loadPage(); });
    }
    const count = $("#runs-count");
    if (count) {
      if (runsState.loading && !runsState.loaded) count.textContent = "Loading past work…";
      else if (runsState.loading) count.textContent = `${runsState.all.length} matching tasks loaded; loading more…`;
      else if (runsState.hasMore) count.textContent = `Showing ${Math.min(runsState.shown, filtered.length)} of more than ${filtered.length} matching tasks`;
      else count.textContent = `${filtered.length} result${filtered.length === 1 ? "" : "s"}`;
    }
    if (restoreMoreFocus) $("#runs-more")?.focus();
    if (restoreRetryFocus) $("#runs-retry")?.focus();
  };

  const loadPage = async ({ reset = false } = {}) => {
    if (runsState.loading && !reset) return;
    if (reset) {
      runsState = { ...runsState, all: [], shown: RUNS_PAGE_SIZE, offset: 0,
        hasMore: false, error: "", loaded: false };
    }
    const generation = ++runsRequestGeneration;
    const request = new URLSearchParams({ limit: String(RUNS_API_FETCH_SIZE), offset: String(runsState.offset) });
    if (runsState.status !== "all") request.set("status", runsState.status);
    if (runsState.q.trim()) request.set("q", runsState.q.trim());
    runsState.loading = true;
    runsState.error = "";
    renderRows();
    try {
      const page = await api(`/runs?${request}`);
      if (generation !== runsRequestGeneration || !location.hash.startsWith("#/runs")) return;
      const nextPage = page.slice(0, RUNS_API_PAGE_SIZE);
      runsState.all = reset ? nextPage : [...runsState.all, ...nextPage];
      runsState.offset += nextPage.length;
      runsState.hasMore = page.length > RUNS_API_PAGE_SIZE;
      runsState.loaded = true;
    } catch (error) {
      if (generation !== runsRequestGeneration || error?.name === "AbortError") return;
      runsState.error = error.message || "Check your connection and try again.";
    } finally {
      if (generation === runsRequestGeneration) {
        runsState.loading = false;
        renderRows();
      }
    }
  };

  let searchTimer = null;
  $("#run-search").addEventListener("input", ev => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      runsState.q = ev.target.value;
      syncHash(); void loadPage({ reset: true });
    }, 180);
  });
  $$('.runs-filter-pills input[name="runs-filter"]').forEach(input => {
    input.addEventListener("change", () => {
      runsState.status = input.value;
      runsState.shown = RUNS_PAGE_SIZE;
      syncHash(); void loadPage({ reset: true });
    });
  });
  renderRows();
  void loadPage({ reset: true });
}

/* -------------------------------------------------------------- approvals */

let approvalsTimer = null, approvalSignature = "", needsYouReturnFocus = null, approvalOffset = 0;
const APPROVAL_PAGE_SIZE = 50;
const APPROVAL_FETCH_SIZE = 200;
const APPROVAL_FETCH_MAX = 1000;
const APPROVAL_DUE_SOON_MS = 10 * 60 * 1000;
let approvalFilter = "all";
let pendingApprovalsCache = [];
let approvalsStatsCache = null;
let approvalsStickyObserver = null;
let needsYouClosing = false;
const needsYouDialog = $("#needs-you");
const approvalsFlight = { promise: null };

function approvalDeadline(a) {
  if (a?.deadline) {
    const direct = Number(a.deadline);
    if (Number.isFinite(direct)) return direct;
    const parsed = Date.parse(a.deadline);
    if (Number.isFinite(parsed)) return parsed;
  }
  if (a?.expires_at) {
    const t = Date.parse(a.expires_at);
    if (Number.isFinite(t)) return t;
  }
  if (a?.created_at) {
    const t = Date.parse(a.created_at);
    if (Number.isFinite(t)) return t + Number(a.ttl_seconds || 600) * 1000;
  }
  return Number.MAX_SAFE_INTEGER;
}

function approvalRiskRank(a) {
  return { high: 0, medium: 1, low: 2 }[a?.risk] ?? 1;
}

function compareApprovalPriority(a, b) {
  return approvalDeadline(a) - approvalDeadline(b)
    || approvalRiskRank(a) - approvalRiskRank(b)
    || Number(!!b.outward) - Number(!!a.outward)
    || String(a.created_at || "").localeCompare(String(b.created_at || ""))
    || String(a.approval_id || a.id || "").localeCompare(String(b.approval_id || b.id || ""));
}

function sortPendingApprovals(list) {
  return [...list].sort(compareApprovalPriority);
}

function approvalMatchesFilter(a) {
  if (approvalFilter === "due") return approvalDeadline(a) - Date.now() <= APPROVAL_DUE_SOON_MS;
  if (approvalFilter === "high") return a.risk === "high";
  if (approvalFilter === "outward") return !!a.outward;
  return true;
}

function formatApprovalTtl(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${m}m left`;
  if (m) return `${m}m ${s}s left`;
  return `${s}s left`;
}

function scheduleApprovalsPoll() {
  clearTimeout(approvalsTimer);
  approvalsTimer = null;
  if (!needsYouDialog.open || document.hidden) return;
  approvalsTimer = setTimeout(() => {
    approvalsTimer = null;
    void refreshApprovals().finally(() => scheduleApprovalsPoll());
  }, 5000);
}

async function openNeedsYou() {
  needsYouReturnFocus = wsEl.classList.contains("open") ? wsBtn : document.activeElement;
  closeWorkspace();
  approvalSignature = "";
  approvalOffset = 0;
  approvalFilter = "all";
  needsYouDialog.scrollTop = 0;
  if ($("#approvals-overview")?.dataset.loaded !== "true") {
    needsYouDialog.dataset.approvalsLoading = "true";
  }
  if (!needsYouDialog.open) needsYouDialog.showModal();
  observeNeedsYouSticky();
  $("#needs-you-close").focus();
  renderAttention();
  bumpSubOwner(approvalsOwner);
  await refreshApprovals();
  scheduleApprovalsPoll();
}

function finalizeNeedsYouClose() {
  clearTimeout(approvalsTimer);
  approvalsTimer = null;
  bumpSubOwner(approvalsOwner);
  const visible = (el) => {
    if (!el?.isConnected) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0
      && rect.top < innerHeight && rect.left < innerWidth;
  };
  const target = visible(needsYouReturnFocus) ? needsYouReturnFocus
    : (visible($("#nav-toggle")) ? $("#nav-toggle") : null);
  target?.focus();
  needsYouReturnFocus = null;
  renderAttention();
}

function closeNeedsYou() {
  if (!needsYouDialog.open) return;
  needsYouClosing = true;
  needsYouDialog.close();
  finalizeNeedsYouClose();
}

function observeNeedsYouSticky() {
  const sticky = $("#needs-you-sticky");
  if (!sticky) return;
  const update = () => {
    const height = Math.ceil(sticky.getBoundingClientRect().height);
    needsYouDialog.style.setProperty("--needs-you-sticky", `${height}px`);
  };
  if (!approvalsStickyObserver && typeof ResizeObserver === "function") {
    approvalsStickyObserver = new ResizeObserver(update);
    approvalsStickyObserver.observe(sticky);
  }
  update();
}

$("#needs-you-open").addEventListener("click", openNeedsYou);
$("#needs-you-close").addEventListener("click", closeNeedsYou);
needsYouDialog.addEventListener("cancel", ev => { ev.preventDefault(); closeNeedsYou(); });
needsYouDialog.addEventListener("close", () => {
  if (needsYouClosing) { needsYouClosing = false; return; }
  finalizeNeedsYouClose();
});
needsYouDialog.addEventListener("click", ev => {
  if (ev.target.closest("a[href]")) { closeNeedsYou(); return; }
  if (ev.target !== needsYouDialog) return;
  const rect = needsYouDialog.getBoundingClientRect();
  const outside = ev.clientX < rect.left || ev.clientX > rect.right
    || ev.clientY < rect.top || ev.clientY > rect.bottom;
  if (outside) closeNeedsYou();
});

// Existing bookmarks open the queue over Studio, without trapping browser Back.
let needsYouRouteOpening = false;
async function renderApprovals() {
  history.replaceState(null, "", "#/chat");
  needsYouRouteOpening = true;
  try {
    await renderChatStudio();
    await openNeedsYou();
  } finally {
    needsYouRouteOpening = false;
  }
}

let receiptOffset = 0;
const RECEIPT_PAGE_SIZE = 20;

async function fetchAllPendingApprovals(signal) {
  const all = [];
  const seen = new Set();
  let offset = 0;
  while (all.length < APPROVAL_FETCH_MAX) {
    const page = await api(`/v1/actions/approvals?status=pending&limit=${APPROVAL_FETCH_SIZE}&offset=${offset}`, { signal });
    if (!Array.isArray(page) || !page.length) break;
    for (const item of page) {
      if (all.length >= APPROVAL_FETCH_MAX) break;
      const id = item.approval_id || item.id;
      if (!id || seen.has(id)) continue;
      seen.add(id);
      all.push(item);
    }
    offset += page.length;
    if (all.length >= APPROVAL_FETCH_MAX || page.length < APPROVAL_FETCH_SIZE) break;
  }
  return all.slice(0, APPROVAL_FETCH_MAX);
}

function approvalOverviewHtml(pending, stats) {
  const total = Math.max(pending.length, Number(stats?.pending_approvals) || 0);
  const receipts = Number(stats?.unresolved_actions) || 0;
  const due = pending.filter(a => approvalDeadline(a) - Date.now() <= APPROVAL_DUE_SOON_MS).length;
  const high = pending.filter(a => a.risk === "high").length;
  const outward = pending.filter(a => a.outward).length;
  const summary = [`<b>${total}</b> approval${total === 1 ? "" : "s"}`];
  if (receipts) summary.push(`<b>${receipts}</b> action outcome${receipts === 1 ? "" : "s"}`);
  if (pending.length < total) summary.push(`showing ${pending.length}`);
  const filters = [
    ["all", "All", pending.length],
    ["due", "Due soon", due],
    ["high", "High risk", high],
    ["outward", "Leaves machine", outward],
  ];
  const filterRow = pending.length
    ? `<div class="approvals-filters" role="group" aria-label="Filter requests">
      ${filters.map(([key, label, count]) => `<button type="button" class="approval-filter" data-approval-filter="${key}" aria-pressed="${String(approvalFilter === key)}" aria-label="${label}: ${count} request${count === 1 ? "" : "s"}">${label}<span class="count">${count}</span></button>`).join("")}
    </div>` : "";
  return `<p class="approvals-summary">${summary.join(" · ")}</p>
    ${filterRow}
    ${pending.length < total ? `<p class="hint approvals-cap">Showing the first ${pending.length} of ${total} requests. Resolve these, or use the CLI queue for the rest.</p>` : ""}`;
}

function approvalEmptyHtml(pending, stats) {
  if (!pending.length) {
    const receipts = Number(stats?.unresolved_actions) || 0;
    if (receipts) {
      return `<div class="empty-state"><p>No pending approvals.</p><p class="hint">${receipts === 1 ? "One action outcome still needs review." : `${receipts} action outcomes still need review.`}</p></div>`;
    }
    return `<div class="empty-state">${icon("check", "icon-lg")}<p>No pending approvals.</p><p class="hint">Requests appear in their conversation and here.</p></div>`;
  }
  return `<div class="empty-state"><p>No requests match this filter.</p><button class="btn ghost small" type="button" data-clear-approval-filter>Show all requests</button></div>`;
}

function renderApprovalQueue({ scrollTop = false, focusFilterAfter = "" } = {}) {
  const pending = pendingApprovalsCache;
  const stats = approvalsStatsCache || {};
  const filtered = pending.filter(approvalMatchesFilter);
  const maxOffset = Math.max(0, Math.ceil(filtered.length / APPROVAL_PAGE_SIZE) - 1) * APPROVAL_PAGE_SIZE;
  if (approvalOffset > maxOffset) approvalOffset = maxOffset;
  const page = filtered.slice(approvalOffset, approvalOffset + APPROVAL_PAGE_SIZE);

  const focus = document.activeElement;
  const focusedCard = focus?.closest?.("[data-approval-card]");
  const focusChoice = focus?.dataset?.approve;
  const focusSummary = focus?.tagName === "SUMMARY" ? focus.textContent.trim() : "";
  const focusFilter = focus?.dataset?.approvalFilter;
  const focusPager = ["approvals-next", "approvals-prev"].includes(focus?.id) ? focus.id : "";
  const expanded = new Set($$("#needs-you [data-approval-card]").filter(c => c.querySelector("details[open]"))
    .map(c => c.dataset.approvalCard));

  const overview = $("#approvals-overview");
  if (overview) {
    overview.innerHTML = approvalOverviewHtml(pending, stats);
    overview.dataset.loaded = "true";
  }
  delete needsYouDialog.dataset.approvalsLoading;
  $("#approvals-pending").innerHTML = page.length
    ? page.map(a => approvalCardHtml(a, { botName: botDisplayName(a.bot_display_name || a.bot_name) })).join("")
    : approvalEmptyHtml(pending, stats);

  const start = page.length ? approvalOffset + 1 : 0;
  const end = approvalOffset + page.length;
  $("#approvals-pagination").innerHTML = filtered.length
    ? `<span class="hint">${start}–${end} of ${filtered.length} requests</span>
      ${approvalOffset ? '<button class="btn ghost small" id="approvals-prev" type="button">Previous</button>' : ""}
      ${end < filtered.length ? '<button class="btn ghost small" id="approvals-next" type="button">Next</button>' : ""}`
    : "";

  $$("#needs-you [data-approval-card]").forEach(c => {
    if (expanded.has(c.dataset.approvalCard) && c.querySelector("details")) c.querySelector("details").open = true;
  });
  if (focusedCard) {
    const replacement = $$("#needs-you [data-approval-card]").find(c => c.dataset.approvalCard === focusedCard.dataset.approvalCard);
    const button = replacement && [...replacement.querySelectorAll("button")].find(b => b.dataset.approve === focusChoice);
    const summary = replacement && focusSummary
      ? [...replacement.querySelectorAll("summary")].find(s => s.textContent.trim() === focusSummary) : null;
    (button || summary || $("#needs-you-close")).focus();
  } else if (focusFilter) {
    ($$("#approvals-overview [data-approval-filter]").find(b => b.dataset.approvalFilter === focusFilter) || $("#needs-you-close")).focus();
  } else if (focusPager) {
    ($(`#${focusPager}`) || $("#approvals-pending [data-approval-card] summary") || $("#needs-you-close")).focus();
  }
  if (focusFilterAfter) {
    ($$("#approvals-overview [data-approval-filter]").find(b => b.dataset.approvalFilter === focusFilterAfter) || $("#needs-you-close")).focus();
  }

  $("#approvals-prev")?.addEventListener("click", () => {
    approvalOffset = Math.max(0, approvalOffset - APPROVAL_PAGE_SIZE);
    renderApprovalQueue({ scrollTop: true });
  });
  $("#approvals-next")?.addEventListener("click", () => {
    approvalOffset += APPROVAL_PAGE_SIZE;
    renderApprovalQueue({ scrollTop: true });
  });
  wireApprovals();
  updateTtls();
  if (scrollTop) $("#approvals-pending")?.scrollIntoView({ block: "start" });
}

$("#approvals-overview")?.addEventListener("click", ev => {
  const filterButton = ev.target.closest("[data-approval-filter]");
  if (!filterButton) return;
  approvalFilter = filterButton.dataset.approvalFilter || "all";
  approvalOffset = 0;
  renderApprovalQueue({ scrollTop: true });
});
$("#approvals-pending")?.addEventListener("click", ev => {
  if (!ev.target.closest("[data-clear-approval-filter]")) return;
  approvalFilter = "all";
  approvalOffset = 0;
  renderApprovalQueue({ scrollTop: true, focusFilterAfter: "all" });
});

function orderReceiptsSection(pendingCount, receiptCount) {
  const section = $("#receipt-queue");
  const pending = $("#approvals-pending");
  const pagination = $("#approvals-pagination");
  if (!section || !pending || !pagination) return;
  if (!pendingCount && receiptCount) {
    if (pending.previousElementSibling !== section) pending.before(section);
  } else if (pagination.nextElementSibling !== section) {
    pagination.after(section);
  }
}

function renderApprovalReceipts(receipts, stats) {
  const total = Number(stats?.unresolved_actions) || 0;
  const section = $("#receipt-queue");
  if (section) section.hidden = !receipts.length;
  const count = $("#receipt-queue-count");
  if (count) {
    count.textContent = total ? String(total) : "";
    count.hidden = !total;
  }
  const focus = document.activeElement;
  const focusReceipt = focus?.dataset?.receiptReview;
  $("#receipts-pending").innerHTML = receipts.length ? receipts.map(receiptCardHtml).join("") : "";
  $("#receipts-pagination").innerHTML = receipts.length
    ? `<span class="hint">${receiptOffset + 1}–${receiptOffset + receipts.length} of ${total} actions</span>
      ${receiptOffset ? '<button class="btn ghost small" id="receipts-prev" type="button">Previous actions</button>' : ""}
      ${receiptOffset + receipts.length < total ? '<button class="btn ghost small" id="receipts-next" type="button">Next actions</button>' : ""}`
    : "";
  $("#receipts-prev")?.addEventListener("click", () => {
    receiptOffset = Math.max(0, receiptOffset - RECEIPT_PAGE_SIZE);
    void refreshApprovals();
  });
  $("#receipts-next")?.addEventListener("click", () => {
    receiptOffset += RECEIPT_PAGE_SIZE;
    void refreshApprovals();
  });
  $$("#receipts-pending [data-receipt-review]").forEach(button => {
    button.addEventListener("click", () => void reviewReceipt(button.dataset.receiptReview, button));
  });
  orderReceiptsSection(pendingApprovalsCache.length, total);
  if (focusReceipt) {
    ($$("#receipts-pending [data-receipt-review]").find(b => b.dataset.receiptReview === focusReceipt) || $("#needs-you-close")).focus();
  }
}

async function refreshApprovals() {
  if (!needsYouDialog.open) return;
  let retry = false;
  await singleFlight(approvalsFlight, async () => {
  if (!needsYouDialog.open) return;
  const error = $("#needs-you-error");
  const gen = approvalsOwner.gen;
  const signal = approvalsOwner.abort?.signal;
  try {
    const receiptPageOffset = receiptOffset;
    const [pending, resolved, stats, receipts] = await Promise.all([
      fetchAllPendingApprovals(signal),
      api("/v1/actions/approvals?status=resolved&limit=8", { signal }),
      api("/stats", { signal }),
      api(`/v1/actions/receipts?unresolved=true&limit=${RECEIPT_PAGE_SIZE}&offset=${receiptPageOffset}`, { signal }),
    ]);
    if (!needsYouDialog.open || gen !== approvalsOwner.gen || receiptPageOffset !== receiptOffset) return;
    if (!receipts.length && receiptPageOffset) { receiptOffset = 0; retry = true; return; }
    error.hidden = true;
    const dueIds = pending
      .filter(a => approvalDeadline(a) - Date.now() <= APPROVAL_DUE_SOON_MS)
      .map(a => a.approval_id || a.id || "").sort();
    const signature = JSON.stringify([pending, resolved, stats.pending_approvals, receipts, receiptPageOffset,
      stats.unresolved_actions, dueIds]);
    // Preserve keyboard focus and expanded review details during unchanged polls.
    if (signature === approvalSignature) return;
    approvalSignature = signature;
    pendingApprovalsCache = sortPendingApprovals(pending);
    approvalsStatsCache = stats;
    const filtered = pendingApprovalsCache.filter(approvalMatchesFilter);
    const maxOffset = Math.max(0, Math.ceil(filtered.length / APPROVAL_PAGE_SIZE) - 1) * APPROVAL_PAGE_SIZE;
    if (approvalOffset > maxOffset) approvalOffset = maxOffset;
    renderApprovalQueue();
    $("#approvals-resolved").innerHTML = resolved.length
      ? resolved.map(a => approvalResolvedHtml(a, a.status, botDisplayName(a.bot_display_name || a.bot_name))).join("")
      : `<p class="hint">No recent decisions.</p>`;
    renderApprovalReceipts(receipts, stats);
  } catch (err) {
    if (err?.name === "AbortError" || !needsYouDialog.open || gen !== approvalsOwner.gen) return;
    delete needsYouDialog.dataset.approvalsLoading;
    const loaded = $("#approvals-overview")?.dataset.loaded === "true";
    if (!loaded) {
      $("#approvals-overview").innerHTML = '<p class="approvals-summary">Requests could not be loaded.</p>';
    }
    error.hidden = false;
    error.innerHTML = `<p>Could not refresh requests: ${esc(err.message)}. ${loaded ? "Displayed requests may be outdated." : "No requests are displayed."}</p><button class="btn ghost small" id="needs-you-retry">Retry</button>`;
    $("#needs-you-retry").addEventListener("click", () => void refreshApprovals());
  }
  });
  if (retry && needsYouDialog.open) return refreshApprovals();
}

/* -------------------------------------------------------- bot settings */

let botDetailRenderGeneration = 0;

const TOOL_SETTINGS = [
  ["read_file", "Read workspace files", "Open text files inside this run’s workspace."],
  ["list_files", "List workspace files", "See file names under this run’s workspace."],
  ["write_file", "Write workspace files", "Create or replace files; approval policy still applies."],
  ["shell", "Run shell commands", "Run commands inside the configured shell boundary."],
  ["web_fetch", "Fetch public pages", "Read public HTTP(S) pages through Hutch’s checked request path."],
  ["live_search", "Search live sources", "Fan out across public feeds, news, and discussion with explicit time bounds; sources, outcomes, and limits are stored as evidence."],
  ["inspect_media", "Inspect images and video", "Store and hash media, sample claim-relevant frames, and state what was not inspected. No authenticity verdict."],
  ["browser", "Use a browser", "Control this bot’s isolated browser profile."],
  ["computer", "Use isolated desktop apps", "Experimental Linux Wayland support. Choose allowed apps under Computer access."],
  ["remember", "Propose reference facts", "Suggest facts for human review before they can be recalled."],
  ["recall", "Recall reviewed facts", "Search reviewed facts available to this bot and chat."],
  ["delegate_task", "Delegate a bounded task", "Strict Offline only. Each request asks for approval and uses another run slot; the child receives only its task text."],
];

function scheduleBodyFromForm(fd) {
  const trigger = String(fd.get("trigger") || "cron");
  const workflowDefinitionId = String(fd.get("workflow_definition_id") || "").trim();
  let workflowInputs = {};
  if (workflowDefinitionId) {
    workflowInputs = JSON.parse(String(fd.get("workflow_inputs_json") || "{}"));
    if (!workflowInputs || Array.isArray(workflowInputs) || typeof workflowInputs !== "object") {
      throw new Error("Workflow inputs must be a JSON object.");
    }
  }
  const body = {
    name: String(fd.get("name") || "").trim(),
    trigger,
    cron: String(fd.get("cron") || "").trim(),
    timezone: String(fd.get("timezone") || "UTC").trim(),
    catch_up: String(fd.get("catch_up") || "coalesce"),
    overlap: String(fd.get("overlap") || "queue"),
    enabled: fd.get("enabled") === "on" || fd.get("enabled") === "true",
    prompt: String(fd.get("schedule_prompt") || fd.get("prompt") || "").trim(),
    workflow_definition_id: workflowDefinitionId || null,
    workflow_revision_id: workflowDefinitionId ? (String(fd.get("workflow_revision_id") || "").trim() || null) : null,
    workflow_inputs: workflowInputs,
  };
  if (trigger === "interval") {
    const minutes = Number(fd.get("interval_minutes"));
    body.interval_seconds = Math.round(minutes * 60);
    body.cron = "";
    const anchor = String(fd.get("anchor_at") || "").trim();
    if (anchor) body.anchor_at = anchor;
  } else if (trigger === "once") {
    body.cron = "";
    body.anchor_at = String(fd.get("anchor_at") || "").trim();
  }
  return body;
}

function scheduleEditorHtml(schedule, index, status = null, workflowDefinitions = [], workflowError = "") {
  const id = String(schedule.id || "");
  const trigger = schedule.trigger || "cron";
  const enabled = schedule.enabled !== false;
  let nextFire = "Not calculated";
  if (status?.next_fire) {
    try { nextFire = new Intl.DateTimeFormat(undefined, {dateStyle:"medium", timeStyle:"short", timeZone:schedule.timezone || "UTC"})
      .format(new Date(status.next_fire)); } catch { nextFire = "Next run available"; }
  }
  const intervalMinutes = schedule.interval_seconds ? String(schedule.interval_seconds / 60) : "65";
  const summaryTrigger = trigger === "interval"
    ? `every ${intervalMinutes}m`
    : trigger === "once" ? "one time" : (schedule.cron || "cron");
  const formId = index === 0 ? "form-schedule" : `form-schedule-${index}`;
  const preview = Array.isArray(status?.preview) ? status.preview.slice(0, 5) : [];
  const currentDefinition = workflowDefinitions.find(item => item.id === schedule.workflow_definition_id);
  const workflowOptions = workflowDefinitions.filter(item => item.active || item.id === schedule.workflow_definition_id)
    .map(item => `<option value="${esc(item.id)}" data-revision-id="${esc(item.latest_revision_id || "")}" ${item.id === schedule.workflow_definition_id ? "selected" : ""}>${esc(item.name)}${item.active ? "" : " · inactive"}</option>`).join("");
  const missingLinkedOption = schedule.workflow_definition_id && !currentDefinition
    ? `<option value="${esc(schedule.workflow_definition_id)}" selected>Linked workflow ${esc(schedule.workflow_definition_id)} · details unavailable</option>` : "";
  const currentRevisionId = schedule.workflow_revision_id || "";
  const workflowInputsText = JSON.stringify(schedule.workflow_inputs || {}, null, 2);
  const linkedWorkflowName = currentDefinition?.name || schedule.workflow_definition_id || "none";
  return `<details class="schedule-entry" data-schedule-entry ${index === 0 ? "open" : ""}>
    <summary class="schedule-summary">
      <strong>${esc(schedule.name || "Scheduled task")}</strong>
      <span class="schedule-summary-cron mono">${esc(summaryTrigger)} · ${esc(schedule.timezone || "UTC")}</span>
      <span class="tag">${enabled ? (index === 0 ? "Primary" : `Task ${index + 1}`) : "Draft"}</span>
    </summary>
    <form id="${formId}" class="form-grid schedule-editor" data-schedule-form data-schedule-id="${esc(id)}">
      <label class="check"><input type="checkbox" name="enabled" ${enabled ? "checked" : ""}> Enabled for future scheduled runs</label>
      <div class="form-grid row2">
        <label class="field">Task name
          <input type="text" name="name" maxlength="80" value="${esc(schedule.name || "Scheduled task")}" required>
        </label>
        <label class="field" data-cron-field ${trigger === "cron" ? "" : "hidden"}>Cron expression
          <input type="text" name="cron" value="${esc(schedule.cron || "")}" placeholder="0 9 * * 1" ${trigger === "cron" ? "required" : ""}>
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
        <textarea name="schedule_prompt" rows="2" maxlength="4000" aria-describedby="schedule-prompt-help-${index}">${esc(schedule.prompt || "")}</textarea>
        <span class="hint" id="schedule-prompt-help-${index}">Leave blank to use this bot’s standing instructions. This prompt is ignored when a saved workflow is linked.</span>
      </label>
      <label class="field">Run a saved workflow
        <select name="workflow_definition_id" data-schedule-workflow-definition>
          <option value="" ${schedule.workflow_definition_id ? "" : "selected"}>Run the routine prompt</option>
          ${workflowOptions}${missingLinkedOption}
        </select>
        <span class="hint">Connecting here is a separate owner action. Only activated saved methods are offered; the routine stores an exact revision and checked inputs.</span>
      </label>
      <p class="hint" data-workflow-revision-summary ${schedule.workflow_definition_id ? "" : "hidden"}>${schedule.workflow_definition_id
        ? `Pinned revision ${esc(currentRevisionId)} of ${esc(linkedWorkflowName)}.` : ""}</p>
      <input type="hidden" name="workflow_revision_id" value="${esc(currentRevisionId)}">
      <label class="field" data-workflow-inputs-field ${schedule.workflow_definition_id ? "" : "hidden"}>
        <span data-workflow-inputs-title>Inputs for ${esc(linkedWorkflowName)}</span>
        <textarea name="workflow_inputs_json" rows="3" maxlength="32768" spellcheck="false">${esc(workflowInputsText)}</textarea>
        <span class="hint">JSON object only. Inputs are validated against the pinned plan before saving and again when it runs.</span>
      </label>
      ${workflowError ? `<p class="hint" role="status">Saved workflow choices are unavailable: ${esc(workflowError)}</p>` : ""}
      <div class="meta-row"><span>Next run</span><span class="mono">${esc(nextFire)}</span></div>
      ${status?.blocked ? `<p class="hint schedule-skip" role="status">Blocked: ${esc(String(status.blocked.reason || "configuration").replaceAll("_", " "))}.</p>` : ""}
      ${status?.last_skip ? `<p class="hint schedule-skip" role="status">Last skipped ${esc(status.last_skip.windows)} missed windows${status.last_skip.reason ? ` · ${esc(String(status.last_skip.reason).replaceAll("_", " "))}` : ""}.</p>` : ""}
      <button class="btn ghost small schedule-advanced-toggle" type="button" data-schedule-advanced-toggle aria-expanded="false">Advanced timing and recovery</button>
      <div class="schedule-advanced" hidden>
        <div class="form-grid row2">
          <label class="field">Trigger
            <select name="trigger" data-schedule-trigger>
              <option value="cron" ${trigger === "cron" ? "selected" : ""}>Calendar cron</option>
              <option value="interval" ${trigger === "interval" ? "selected" : ""}>Fixed interval</option>
              <option value="once" ${trigger === "once" ? "selected" : ""}>One time</option>
            </select>
          </label>
          <label class="field" data-interval-field ${trigger === "interval" ? "" : "hidden"}>Interval (minutes)
            <input type="number" name="interval_minutes" min="1" step="1" value="${esc(intervalMinutes)}" ${trigger === "interval" ? "required" : ""}>
          </label>
          <label class="field" data-anchor-field ${trigger === "cron" ? "hidden" : ""}>Anchor (ISO UTC)
            <input type="text" name="anchor_at" value="${esc(schedule.anchor_at || "")}" placeholder="2026-10-07T00:00:00+00:00" ${trigger === "once" ? "required" : ""}>
          </label>
          <label class="field">If already busy
            <select name="overlap">
              <option value="queue" ${(schedule.overlap || "queue") === "queue" ? "selected" : ""}>Queue</option>
              <option value="skip" ${schedule.overlap === "skip" ? "selected" : ""}>Skip this occurrence</option>
              <option value="buffer_one" ${schedule.overlap === "buffer_one" ? "selected" : ""}>Keep one waiting</option>
            </select>
          </label>
        </div>
        ${preview.length ? `<div class="schedule-preview" aria-label="Upcoming occurrences"><p class="hint">Upcoming occurrences</p><ol>${preview.map(p => `<li><time datetime="${esc(p.at)}">${esc(p.at)}</time> · ${esc(p.timezone)} (${esc(p.utc_offset)})</li>`).join("")}</ol></div>` : ""}
        <div class="schedule-occurrence-panel" data-occurrence-panel="${esc(id)}" hidden>
          <h4>Recent occurrences</h4>
          <div class="schedule-occurrence-list hint">Loading…</div>
        </div>
        <div class="btn-row">
          <button class="btn ghost small" type="button" data-schedule-run-now-bot="${esc(id)}">Run now</button>
          <button class="btn ghost small" type="button" data-schedule-skip-next-bot="${esc(id)}">Skip next</button>
          <button class="btn ghost small" type="button" data-show-occurrences="${esc(id)}">History</button>
        </div>
      </div>
      <div class="btn-row schedule-actions">
        <button class="btn primary small" type="submit">Save task</button>
        <button class="btn ghost small" type="button" data-remove-schedule="${esc(id)}">Remove task</button>
      </div>
    </form>
  </details>`;
}

async function renderBotDetail(name, factOffset = 0, showArchivedFacts = false) {
  const generation = ++botDetailRenderGeneration;
  const route = `#/bot/${encodeURIComponent(name)}`;
  const keepCustomizationOpen = location.hash === route && $("#assistant-more-settings")?.open === true;
  const b = await api(`/bots/${encodeURIComponent(name)}`);
  let taskPresets = [];
  let taskPresetsError = "";
  try { taskPresets = await api("/v1/task-presets"); }
  catch (error) { taskPresetsError = error.message; }
  const runtimeNames = { builtin: "Hutch built-in", opencode: "OpenCode", pi: "Pi", mock: "Retired mock" };
  const runtimeName = runtimeNames[b.runtime] || b.runtime || "Unknown";
  const runtimeUnavailable = !["builtin", "opencode"].includes(b.runtime);
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
  let workflowDefinitions = [];
  let workflowDefinitionsError = "";
  try {
    const workflowPage = await api("/v1/workflows?limit=100");
    workflowDefinitions = workflowPage.items || [];
  } catch (error) { workflowDefinitionsError = error.message; }
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
  if (generation !== botDetailRenderGeneration || location.hash !== route) return;
  setTopContext(`
    <div class="ctx-id">
      ${botAvatar(b.name, 30)}
      <div class="ctx-heading"><h1 title="${esc(botHeading(b))}">${esc(botHeading(b))}</h1><span class="ctx-subtitle" title="${esc(botRole(b))}">Assistant settings${botRole(b) ? ` · ${esc(botRole(b))}` : ""}</span></div>
    </div>
    <div class="ctx-actions">
      <details class="assistant-settings-menu">
        <summary class="icon-btn" aria-label="Assistant options" title="Assistant options">${icon("moreHorizontal")}</summary>
        <div class="assistant-settings-menu-panel" aria-label="Assistant options">
          <a class="assistant-settings-menu-item" href="#/chat/${esc(b.name)}">${icon("chat")} Open chat</a>
          <button class="assistant-settings-menu-item is-danger" id="btn-delete-bot" type="button">${icon("trash")} Delete assistant</button>
        </div>
      </details>
    </div>`);

  const limits = b.limits || {};
  const limitMaxSteps = Number(limits.max_steps ?? 24);
  const limitTimeoutSeconds = Number(limits.timeout_seconds ?? 900);
  const formatLimitDuration = seconds => seconds < 60
    ? `${Number(seconds.toFixed(1))} sec`
    : `${Number((seconds / 60).toFixed(1))} min`;
  const limitDurationLabel = formatLimitDuration(limitTimeoutSeconds);
  const rules = b.command_rules || [];
  const specialistRosterHtml = b.is_workspace_coordinator ? `
          <section class="panel" id="workspace-specialist-roster" aria-labelledby="workspace-specialist-roster-title">
            <details class="workspace-specialist-settings summary-row-sm summary-row-3col" id="workspace-specialist-settings" ${specialistRosterError ? "open" : ""}>
              <summary class="workspace-specialist-summary">
                <span class="summary-row-copy workspace-specialist-copy" id="workspace-specialist-roster-title"><strong>Approved specialist Bots</strong></span>
                <span class="workspace-specialist-count" id="workspace-specialist-roster-count">${specialistRosterError ? "Unavailable" : `${specialistRoster?.specialist_bot_ids.length || 0} approved`}</span>
                <span class="summary-row-action workspace-specialist-action"><span class="when-closed">Manage</span><span class="when-open">Close</span>${icon("down")}</span>
              </summary>
              <div class="workspace-specialist-content">
                <p class="hint">Only Bots you approve here can receive new tasks from the coordinator. This changes future assignments; it does not stop existing work or remove its history.</p>
            ${specialistRosterError
              ? `<p class="error" role="alert">The roster could not be loaded: ${esc(specialistRosterError)}. Reload this page before changing it.</p>`
              : specialistRoster?.bots.length
                ? `${specialistRoster.bots.length > 8 ? `<label class="field">Filter specialist Bots
                      <input type="search" id="workspace-specialist-filter" aria-controls="workspace-specialist-options" placeholder="Name or address" enterkeyhint="search">
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
    <div class="page-scroll"><div class="container assistant-settings-page">
      <p class="crumb"><a href="#/chat/${esc(b.name)}">Chats</a> / Assistant settings</p>
      <form class="panel form-grid assistant-settings-basics" id="form-identity">
        <div class="assistant-settings-intro">
          ${botAvatar(b.name, 48)}
          <div><h2 class="panel-title">About this assistant</h2><p class="hint">Give it a name and a little direction. You can change the details whenever you like.</p></div>
        </div>
        <label class="field"><span id="assistant-name-label">Assistant name</span>
          <input type="text" name="display_name" maxlength="80" value="${esc(b.display_name || b.name)}" required aria-labelledby="assistant-name-label" aria-describedby="assistant-name-hint">
          <span class="hint" id="assistant-name-hint">Shown in your chats and assistant list.</span>
        </label>
        <label class="field">What it helps with
          <input type="text" name="description" value="${esc(b.description || "")}" placeholder="For example, helps me stay on top of email">
        </label>
        <div class="btn-row"><button class="btn primary small" type="submit">Save details</button></div>
      </form>
      <details class="assistant-more-settings summary-row" id="assistant-more-settings">
        <summary>
          <span class="assistant-settings-summary-icon">${icon("sliders")}</span>
          <span class="summary-row-copy"><strong>Customize how it works</strong><small>Choose its AI, apps, schedule, safety, and saved notes</small></span>
          <span class="summary-row-action"><span class="when-closed">More settings</span><span class="when-open">Hide settings</span>${icon("down")}</span>
        </summary>
      <div class="detail-grid">
        <div>
          <form class="panel form-grid" id="form-instructions">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("chat")}</span>How it should help</div>
            <p class="hint">These are the standing directions it follows in every conversation. Requests you already gave it stay here, ready for you to refine when you want.</p>
            <label class="field" for="assistant-instructions">Standing directions
              <textarea id="assistant-instructions" name="instructions" rows="7" placeholder="Add guidance for how this assistant should work">${esc(b.instructions || "")}</textarea>
            </label>
            <div class="btn-row"><button class="btn primary small" type="submit">Save directions</button></div>
          </form>

          <div id="persona-form-slot"></div>

          ${b.is_workspace_coordinator || botsCache.length > 1 ? `<section class="panel" aria-labelledby="workspace-coordinator-title">
            <div class="panel-title" id="workspace-coordinator-title">Main assistant</div>
            <p class="hint">Choose which assistant opens as your main conversation. You can still chat with all of them directly. This role does not add app access or permissions.</p>
            ${b.is_workspace_coordinator
              ? `<div class="coordinator-role-state" role="status"><span class="tag" id="workspace-coordinator-settings-state">Main assistant</span>
                  <button class="btn ghost small" type="button" id="btn-clear-workspace-coordinator">Clear selection</button></div>`
              : `<button class="btn ghost small" type="button" id="btn-set-workspace-coordinator">Make this the main assistant</button>`}
          </section>` : ""}

          ${specialistRosterHtml}

          <div class="panel" id="idp-panel">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("bot")}</span>Look and feel</div>
            ${identityPickerHtml()}
            <p class="hint idp-note">Chosen immediately — the roster updates everywhere.</p>
          </div>

          <form class="panel form-grid" id="form-model">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("zap")}</span>AI service and model</div>
            <div class="form-grid row2">
              <label class="field"><span id="default-model-label">Default model</span>
                <input type="text" name="model" value="${esc(b.model || "")}" aria-labelledby="default-model-label" aria-describedby="default-model-hint">
                <span class="hint" id="default-model-hint">Hybrid allows local and hosted routes; Local blocks hosted models but keeps tools online. Offline requires a host that verifies worker network isolation.</span>
              </label>
              <label class="field" for="form-runtime">Execution runtime
                <select id="form-runtime" name="runtime" ${runtimeUnavailable ? "disabled" : ""}>
                  <option value="opencode" ${b.runtime === "opencode" ? "selected" : ""}>OpenCode assistant</option>
                  <option value="builtin" ${b.runtime === "builtin" ? "selected" : ""}>Hutch built-in</option>
                </select>
                <span class="hint">${runtimeUnavailable ? `${esc(runtimeName)} is unavailable in Hutch.` : b.runtime === "opencode" ? "OpenCode runs with Hutch approval and usage controls." : "Direct provider chat through Hutch's own agent loop."}</span>
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
            <label class="field"><span id="inference-mode-label">Model routing</span>
              <select name="inference_mode" aria-labelledby="inference-mode-label" aria-describedby="inference-mode-help">
                <option value="hybrid" ${(b.inference_mode || "hybrid") === "hybrid" ? "selected" : ""}>Hybrid · local and hosted routes</option>
                <option value="local" ${b.inference_mode === "local" ? "selected" : ""}>Local model routes only</option>
                <option value="offline" ${b.inference_mode === "offline" ? "selected" : ""} ${offlineDisabled}>${offlineLabel}</option>
              </select>
              <span class="hint" id="inference-mode-help">${esc(offlineReason)}</span>
            </label>
            <label class="field"><span id="task-focus-label">Task focus for local models</span>
              <select name="preset" aria-labelledby="task-focus-label" aria-describedby="task-focus-help" ${taskPresetsError ? "disabled" : ""}>
                <option value="" ${b.preset ? "" : "selected"}>Standard context policy</option>
                ${taskPresets.map(preset => `<option value="${esc(preset.id)}" ${b.preset === preset.id ? "selected" : ""}>${esc(preset.title)}</option>`).join("")}
              </select>
              <span class="hint" id="task-focus-help">${taskPresetsError
                ? `Task focus could not be loaded: ${esc(taskPresetsError)}. Reload before changing this setting.`
                : "This changes the built-in local runtime’s context sizing and residency only. The selected model still determines its capabilities; this never selects a model, provider, or paid route."}</span>
            </label>
            <label class="field">Tool calling
              <select name="tool_protocol" id="tool-protocol-select" aria-describedby="tool-protocol-help">
                ${[["auto", "Automatic — this route’s own tool protocol"],
                   ["native", "Provider-native tools"],
                   ["constrained", "Constrained JSON — backend schema"],
                   ["prompt", "Prompt contract — best effort"],
                   ["disabled", "No tools"]].map(([value, label]) =>
                     `<option value="${value}" ${(b.tool_protocol || "auto") === value ? "selected" : ""}>${label}</option>`).join("")}
              </select>
              <span class="hint" id="tool-protocol-help">Automatic keeps this route’s native tool protocol. Constrained and prompt modes are explicit choices; every mode validates each call before it can run.</span>
            </label>
            <details id="tool-compat" class="tool-compat">
              <summary>Check compatibility for this model route</summary>
              <div id="tool-compat-result" class="settings-list"><p class="hint">Open to check this route’s tool-calling evidence. No model request is made.</p></div>
            </details>
            <div class="form-grid row2">
              <label class="field">Fallback models (when the primary is unavailable)
                <input type="text" name="fallbacks" value="${esc((b.fallbacks || []).join(", "))}" placeholder="provider/model, provider/model">
              </label>
              <label class="field">Escalation models (after repeated quality failures)
                <input type="text" name="escalation" value="${esc((((b.escalation && b.escalation.to) || [])).join(", "))}" placeholder="provider/model">
              </label>
            </div>
            <section class="task-routing-settings" aria-labelledby="task-routing-title">
              <div class="panel-title" id="task-routing-title">Manual task-role routes</div>
              <p class="hint">Choose a role for one chat message to use its exact route. Blank roles use the Bot model. Fallbacks still handle availability; escalation still handles repeated quality failures. Automatic classification is not enabled.</p>
              <div class="form-grid row2">
                ${TASK_ROLE_OPTIONS.map(([role, label]) => `<label class="field">${label}
                  <input type="text" data-task-route="${role}" value="${esc(b.task_routes?.[role] || "")}" placeholder="provider/model" autocomplete="off" spellcheck="false">
                </label>`).join("")}
              </div>
              <p class="hint">Use an exact route such as <code>ollama/qwen3:8b</code> or <code>openrouter/author/model-id</code>, never a display label. Hutch validates availability, context fit, spending admission and route permissions when you select it.</p>
            </section>
            <label class="field">Context pressure on smaller windows
              <select name="compaction">
                <option value="ask" ${(b.compaction || "ask") === "ask" ? "selected" : ""}>Review before hosted summaries (recommended)</option>
                <option value="auto" ${b.compaction === "auto" ? "selected" : ""}>Allow bounded summaries without a review</option>
                <option value="off" ${b.compaction === "off" ? "selected" : ""}>Never summarize — stop and ask instead</option>
              </select>
              <span class="hint">Paid summaries ask first by default. Auto is an explicit opt-in; every summary remains bounded, budget-checked and recorded, and the original conversation is never rewritten. Local summaries have no metered provider charge.</span>
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
            <div class="panel-title settings-panel-title" id="tool-settings-title"><span class="settings-panel-icon">${icon("check")}</span>What it can do</div>
            <p class="hint" id="tool-settings-help">Choose which actions this assistant may use. Important actions still come to you for review. Offline mode removes web browsing.</p>
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

          <div id="bot-skills-section"></div>

          <form class="panel form-grid" id="form-computer" aria-labelledby="computer-settings-title">
            <div class="panel-title settings-panel-title" id="computer-settings-title"><span class="settings-panel-icon">${icon("sliders")}</span>Computer access</div>
            <p class="hint">Browser profiles belong to this assistant. Native apps use a separate Linux display and input session. Enable the relevant tool above; saving these choices does not start a session.</p>
            <label class="field">Local web apps
              <textarea name="local_dev_origins" rows="2" aria-describedby="local-origin-help" placeholder="http://localhost:3000">${esc((b.local_dev_origins || []).join("\n"))}</textarea>
              <span class="hint" id="local-origin-help">One exact HTTP loopback origin per line, with a port. Up to eight. Hutch’s own dashboard and other private addresses are refused.</span>
            </label>
            <label class="field">Allowed desktop applications
              <input name="computer_apps" value="${esc((b.computer_apps || []).join(", "))}" placeholder="kwrite" aria-describedby="desktop-app-help">
              <span class="hint" id="desktop-app-help">Up to eight installed program names, separated by commas. Apps have workspace-only user files, a private home and no network. This experimental Linux tool needs a private KWin session and the containment backend.</span>
            </label>
            <label class="tool-option"><input type="checkbox" name="observation_to_hosted" ${b.observation_to_hosted ? "checked" : ""}>
              <span class="tool-option-copy"><b>Allow observations to hosted AI</b><small>Page text, labels and screenshots may leave this machine through this assistant’s chosen AI service. Sensitive-field detection is best effort. Leave off for private sessions; local model routes can still receive observations.</small></span>
            </label>
            <label class="field">Computer access from paired devices
              <select name="remote_computer_access" aria-describedby="remote-computer-help">
                ${[["off", "Off"], ["view", "View captured frames"], ["control", "View and take step control"]].map(([value, label]) => `<option value="${value}" ${(b.remote_computer_access || "off") === value ? "selected" : ""}>${label}</option>`).join("")}
              </select>
              <span class="hint" id="remote-computer-help">Uses the existing private, authenticated phone connection. View needs Monitor permission; input needs Review permission and an explicit takeover. No new listener is opened. Lost or hidden viewers pause control. New runs use this choice.</span>
            </label>
            <div class="btn-row"><button class="btn primary small" type="submit">Save computer access</button><button class="btn ghost small" type="button" id="computer-doctor">Check host readiness</button></div>
            <p class="hint" id="computer-readiness" role="status"></p><details id="computer-readiness-details" hidden><summary>Capability details and setup steps</summary><ul class="computer-capabilities"></ul></details>
          </form>

          <section class="panel schedule-manager" id="schedule-manager" aria-labelledby="schedule-manager-title">            <div class="schedule-manager-head">
              <div>
                <div class="panel-title settings-panel-title" id="schedule-manager-title"><span class="settings-panel-icon">${icon("calendar")}</span>Work on a schedule</div>
                <p class="hint">Set a time for this assistant to check in or take care of a repeat task.</p>
              </div>
              <button class="btn primary small" type="button" id="btn-add-schedule">Add task</button>
            </div>
            <div class="schedule-list" id="schedule-list">
              ${schedules.length ? schedules.map((scheduled, index) =>
                scheduleEditorHtml(scheduled, index, scheduleStatus.get(scheduled.id),
                  workflowDefinitions, workflowDefinitionsError)).join("")
                : `<div class="empty-state schedule-empty"><p>No recurring tasks yet.</p><p class="hint">Add one when this bot should work on a regular schedule.</p></div>`}
            </div>
          </section>

          <form class="panel form-grid" id="form-risk">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("shield")}</span>Approvals and workspace</div>
            <div class="form-grid row2">
              <label class="field">When should it check with you?
                <select name="approval_mode">
                  <option value="ask" ${b.approval_mode === "ask" ? "selected" : ""}>Ask before each important action</option>
                  <option value="auto" ${b.approval_mode === "auto" ? "selected" : ""}>Use actions I have already approved</option>
                </select>
              </label>
              <label class="field">Action safety level
                <select name="risk_tier">
                  ${[["readonly", "Look only"], ["supervised", "Ask before changes"], ["trusted", "Use approved actions"]].map(([value, label]) => `<option value="${value}" ${(b.risk_tier || "supervised") === value ? "selected" : ""}>${label}</option>`).join("")}
                </select>
              </label>
            </div>
            <label class="field workspace-mode-field"><span id="workspace-mode-label">Workspace</span>
              <select name="workspace_mode" aria-labelledby="workspace-mode-label" aria-describedby="workspace-mode-help">
                <option value="fresh" ${(b.workspace_mode || (b.workdir ? "folder" : "fresh")) === "fresh" ? "selected" : ""}>Fresh each run</option>
                <option value="managed" ${b.workspace_mode === "managed" ? "selected" : ""}>Hutch-managed</option>
                <option value="folder" ${b.workspace_mode === "folder" ? "selected" : ""}>Existing folder</option>
              </select>
              <span class="hint" id="workspace-mode-help">Fresh starts each run in a new folder. Managed reuses one private folder for this bot’s runs and chats. Folder uses the existing path below. Changing modes never moves or deletes files; deleting a bot keeps its managed folder.</span>
            </label>
            <label class="field workspace-folder-field" id="workspace-folder-field" ${b.workspace_mode === "folder" ? "" : "hidden"}><span id="workdir-folder-label">Existing folder</span>
              <input type="text" name="workdir" value="${esc(b.workdir || "")}" placeholder="absolute path, for example ~/Projects/report" ${b.workspace_mode === "folder" ? "required" : ""} aria-labelledby="workdir-folder-label" aria-describedby="workdir-folder-hint">
              <span class="hint" id="workdir-folder-hint">Choose a folder that already exists. System folders, your whole home, and Hutch’s private state are refused.</span>
            </label>
            <label class="field browser-handoff-field"><span id="browser-handoff-label">Local browser handoff</span>
              <select name="local_browser_handoff" aria-labelledby="browser-handoff-label" aria-describedby="browser-handoff-help">
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
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("sliders")}</span>Extra command rules</div>
            <div class="settings-list" id="rules-list">
              ${rules.map((r, i) => `
                <div class="meta-row"><span class="mono">${esc(r.match)}</span>${statusChipTag(r.verdict)}</div>`).join("")
                || `<p class="empty-inline">No rules — the risk tier decides everything.</p>`}
            </div>
            <form class="form-grid row2 form-rule" id="form-rule">
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
          <div class="panel assistant-usage-panel">
            <details class="assistant-usage-details summary-row" id="assistant-usage-limits">
              <summary>
                <span class="settings-panel-icon">${icon("chart")}</span>
                <span class="summary-row-copy assistant-usage-copy"><strong>Usage and time limits</strong>
                  <small>${limitMaxSteps} work steps · ${esc(limitDurationLabel)} per task</small>
                </span>
                <span class="summary-row-action assistant-usage-action"><span class="when-closed">Change</span><span class="when-open">Hide</span>${icon("down")}</span>
              </summary>
              <form class="form-grid assistant-usage-form" id="form-limits">
                <div class="form-grid row2">
                  <label class="field">Maximum work steps
                    <input type="number" name="max_steps" min="1" step="1" required value="${esc(limits.max_steps ?? 24)}">
                  </label>
                  <label class="field">Time per task (minutes)
                    <input type="number" name="timeout_minutes" min="0.1" step="0.1" required value="${esc(Number((limitTimeoutSeconds / 60).toFixed(1)))}">
                  </label>
                  <label class="field">Approximate daily AI use (tokens)
                    <input type="number" name="daily_token_cap" min="0" step="1" required value="${esc(limits.daily_token_cap ?? 200000)}">
                  </label>
                  <label class="field">Maximum reply length (tokens)
                    <input type="number" name="max_turn_tokens" min="0" step="1" required value="${esc(limits.max_turn_tokens ?? 0)}">
                  </label>
                  <label class="field">Estimated cost per task (USD)
                    <input type="number" name="max_cost_usd" min="0" step="any" required value="${esc(limits.max_cost_usd ?? 0)}">
                  </label>
                  <label class="field">Estimated daily cost (USD)
                    <input type="number" name="daily_cost_cap_usd" min="0" step="any" required value="${esc(limits.daily_cost_cap_usd ?? 0)}">
                  </label>
                  <label class="field">Warn me at (USD)
                    <input type="number" name="band_warn_usd" id="band-warn" min="0" step="any" placeholder="not set">
                  </label>
                  <label class="field">Pause for approval at (USD)
                    <input type="number" name="band_pause_usd" id="band-pause" min="0" step="any" placeholder="not set">
                  </label>
                  <label class="field">Hard stop at (USD)
                    <input type="number" name="band_ceiling_usd" id="band-ceiling" min="0" step="any" placeholder="not set">
                  </label>
                  <label class="field">When a price is unknown
                    <select name="unknown_price" id="band-unknown">
                      <option value="refuse">Block the call</option>
                      <option value="mark">Run it and record the charge as unknown</option>
                    </select>
                  </label>
                </div>
                <p class="hint">Usage and cost figures are estimates, not guaranteed charges. Your AI provider controls final billing; set spending limits there for a hard cap. On the six fields above, 0 means no estimate limit. The three bands below are independent: leave a field empty for no limit, or set 0 on the hard stop for no paid spend. Warn only tells you; pause asks you before the crossing call; the hard stop refuses new paid calls.</p>
                <div class="btn-row"><button class="btn primary small" type="submit">Save limits</button></div>
              </form>
            </details>
            <div class="assistant-usage-today"><span>Estimated AI use today</span><strong>${fmtTokens(b.tokens_today)} tokens</strong>
              <span class="hint" id="assistant-usage-today-extra"></span></div>
          </div>

          <div class="panel">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("fileText")}</span>Saved notes (${b.memory_count})</div>
            <label class="field" for="memory-toggle"><span id="memory-learning-label">Memory and learning</span><select id="memory-toggle" aria-labelledby="memory-learning-label" aria-describedby="memory-learning-help memory-learning-privacy">
              <option value="off" ${!b.memory_enabled ? 'selected' : ''}>Off</option>
              <option value="review" ${b.memory_enabled && b.memory_learning !== 'hybrid' ? 'selected' : ''}>Review first</option>
              <option value="hybrid" ${b.memory_enabled && b.memory_learning === 'hybrid' ? 'selected' : ''}>Hybrid</option>
            </select></label>
            <p class="hint" id="memory-learning-help">${!b.memory_enabled ? 'Runtime memory is off. Saved records remain manageable here.' : b.memory_learning === 'hybrid' ? 'Clear statements such as “I prefer concise answers” are saved for that chat, with provenance and undo. Other facts still need review.' : 'New reference facts need your review. Previously saved preferences remain until you undo them or turn memory off.'}</p>
            <p class="hint" id="memory-learning-privacy">Saved preferences can be included in future requests to this assistant’s model. Undo stops new retrieval; source conversations and backups remain. Learning never activates executable skills or expands access.</p>
            <button class="btn ghost small" id="memory-archives" type="button">${showArchivedFacts ? 'Hide' : 'Show'} archived facts</button>
            <div class="memory-actions"><button class="btn ghost small" id="memory-export" type="button">Download memory JSON</button></div>
            ${factsPage.facts.map(factCardHtml).join('') || `<p class="empty-inline">No active facts in this window.</p>`}
            ${factShareRecordsHtml(factSharesPage)}
            <div class="btn-row"><button class="btn ghost small" id="facts-previous" type="button" ${factOffset ? '' : 'disabled'}>Previous facts</button>
              <span class="hint">${factsPage.facts.length ? `${factOffset + 1}–${factOffset + factsPage.facts.length}` : 'No facts in this window'}</span>
              <button class="btn ghost small" id="facts-next" type="button" ${factsPage.next_offset === null ? 'disabled' : ''}>Next facts</button></div>
          </div>

          <div class="panel">
            <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${icon("check")}</span>Always-allowed actions (${b.sticky_allows.length})</div>
            ${b.sticky_allows.map(s => `
              <div class="allow-item"><code>${esc(s)}</code>
                <button class="chip-del" aria-label="Revoke ${esc(s)}" data-revoke-sticky="${esc(s)}">${icon("x")}</button>
              </div>`).join("") || `<p class="empty-inline">None — every risky command asks.</p>`}
          </div>

<p><a href="#/runs?q=${encodeURIComponent(b.name)}">See this assistant’s work history</a></p>
        </div>
      </div>
      </details>
    </div></div>`;

  if (keepCustomizationOpen) $("#assistant-more-settings").open = true;

  // wiring
  mountIdentityPicker($("#idp-panel"), b.name, pair => { sigilSet(b.name, pair); refreshRoster(); });
  window.hutchSkills?.mountBotPanel($("#bot-skills-section"), b);
  window.hutchPersona?.mountBotForm($("#persona-form-slot"), b.name);
  loadBotBudget(b);
  const patch = async (body, msg) => {
    const requestedHash = location.hash;
    const requestedGeneration = studioGeneration;
    let saved;
    try {
      saved = await api(`/bots/${encodeURIComponent(b.name)}`, { method: "PATCH", body });
    } catch (err) { toast(`Not saved: ${err.message}`, true); return false; }
    b.memory_enabled = saved.memory_enabled;
    b.memory_learning = saved.memory_learning;
    b.memory_revision = saved.memory_revision;
    toast(msg);
    try {
      if (location.hash === requestedHash && studioGeneration === requestedGeneration
          && botDetailRenderGeneration === generation) await renderBotDetail(b.name);
    } catch (err) { toast(`Saved, but settings could not refresh. Reload to see the latest settings: ${err.message}`, true); }
    void refreshRoster();
    return true;
  };
  $("#form-identity").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ display_name: fd.get("display_name"), description: fd.get("description") }, "Saved.");
  });
  $("#form-instructions").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ instructions: fd.get("instructions") }, "Directions saved.");
  });
  $("#btn-set-workspace-coordinator")?.addEventListener("click", () => {
    const current = botsCache.find(bot => bot.is_workspace_coordinator);
    const replacement = current && current.id !== b.id
      ? `<p>This replaces <b>${esc(current.display_name || current.name)}</b> as the workspace coordinator. It does not change either Bot’s permissions or settings.</p>`
      : `<p>This makes <b>${esc(b.display_name || b.name)}</b> the main workspace conversation. It does not change the Bot’s permissions or settings.</p>`;
    openModal({ title: "Make this your main assistant?", bodyHtml: `${replacement}<p>If this assistant is currently approved to receive assigned work, it will be removed from that list. The previous main assistant will not be added automatically. You can still open a conversation with every assistant from the roster.</p>`,
      confirmText: "Make main assistant", returnFocus: $("#btn-set-workspace-coordinator"),
      onConfirm: async () => {
        try {
          await api("/v1/workspace/coordinator", { method: "PUT", body: { bot_id: b.id } });
          toast(`${b.display_name || b.name} is now your main assistant.`);
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
    openModal({ title: "Remove the main assistant?", bodyHtml: `<p>${esc(b.display_name || b.name)} will remain an assistant and its conversations will stay available. You can choose another main assistant later.</p>`,
      confirmText: "Clear role", confirmClass: "danger", returnFocus: $("#btn-clear-workspace-coordinator"),
      onConfirm: async () => {
        try {
          await api("/v1/workspace/coordinator", { method: "PUT", body: { bot_id: null } });
          toast("Main assistant cleared.");
          await refreshRoster();
          await renderBotDetail(b.name);
          return true;
        } catch (err) { toast(`Coordinator not changed: ${err.message}`, true); return false; }
      },
    });
  });
  const toolCompat = { data: null };
  const toolCompatDetails = $("#tool-compat");
  const toolCompatResult = $("#tool-compat-result");
  const toolProtocolSelect = $("#tool-protocol-select");
  const toolProtocolHelp = $("#tool-protocol-help");
  const modeLabels = { auto: "Automatic", native: "Provider-native tools", constrained: "Constrained JSON",
    prompt: "Prompt contract", disabled: "No tools" };
  const evidenceWords = { documented: "documented", advertised: "advertised (not verified)", probed: "probed on this route",
    observed: "observed in a governed run", stale: "stale evidence", unsupported: "not supported", unknown: "unknown" };
  const renderToolCompat = () => {
    const data = toolCompat.data;
    if (!data) return;
    const eligibility = data.eligibility || {};
    const profile = data.profile || {};
    for (const option of toolProtocolSelect.options) {
      const base = modeLabels[option.value] || option.value;
      const entry = eligibility[option.value];
      option.disabled = option.value !== "auto" && !!entry && !entry.available;
      option.textContent = base + (entry && !entry.available ? " — unavailable here" : "");
    }
    const saved = data.requested || "auto";
    const native = profile.native_tools || {};
    const constrained = profile.constrained_schema || {};
    toolProtocolHelp.textContent = `Saved: ${modeLabels[saved] || saved}. Native tool evidence: ` +
      `${evidenceWords[native.state] || native.state || "unknown"}. Constrained schema: ` +
      `${evidenceWords[constrained.state] || constrained.state || "unknown"}.`;
    const rows = [];
    rows.push(`<div class="meta-row"><span><b>Route</b><br><span class="hint">${esc(data.model || "")} · ${esc(profile.provider || "unknown provider")}${profile.endpoint_class ? " · " + esc(profile.endpoint_class) : ""}${profile.revision ? " · build " + esc(profile.revision) : ""}</span></span></div>`);
    for (const mode of ["native", "constrained", "prompt", "disabled"]) {
      const entry = eligibility[mode] || {};
      rows.push(`<div class="meta-row"><span><b>${modeLabels[mode]}</b><br><span class="hint">${entry.available ? "Available — " : "Unavailable — "}${esc(entry.reason || "")}</span></span><span class="hint">${entry.available ? "available" : "blocked"}</span></div>`);
    }
    rows.push(`<div class="meta-row"><span><b>Argument validator</b><br><span class="hint">${esc(data.validator || "unknown")}; every run records its compiled catalog hash and diagnostics in the transcript</span></span></div>`);
    const observations = data.observations || [];
    rows.push(`<div class="meta-row"><span><b>Last governed observation</b><br><span class="hint">${observations.length ? esc(observations.map(item => `${item.observed_at || "unknown time"} · ${item.source_tool || "call"}`).join("; ")) : "No governed run has recorded a call on this exact route yet — and one valid call would not be a model guarantee."}</span></span></div>`);
    rows.push(`<p class="hint" style="margin:0;">${esc(data.evidence_note || "")}</p>`);
    toolCompatResult.innerHTML = rows.join("");
  };
  if (toolCompatDetails) {
    toolCompatDetails.addEventListener("toggle", async () => {
      if (!toolCompatDetails.open || toolCompat.data) return;
      toolCompatResult.innerHTML = `<p class="hint">Checking this route…</p>`;
      try {
        const data = await api(`/v1/tool-compatibility?ref=${encodeURIComponent(name)}`);
        if (generation !== botDetailRenderGeneration) return;
        toolCompat.data = data;
        renderToolCompat();
      } catch (error) {
        if (generation !== botDetailRenderGeneration) return;
        toolCompatResult.innerHTML = `<p class="hint">Could not check this route: ${esc(error.message)}</p>`;
      }
    });
    $('#form-model input[name="model"]').addEventListener("input", () => {
      if (!toolCompat.data) return;
      toolCompat.data = null;
      for (const option of toolProtocolSelect.options) option.disabled = false;
      toolCompatResult.innerHTML = `<p class="hint">Route changed — save the model, then check compatibility again.</p>`;
    });
  }
  $("#form-model").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const choice = fd.get("tool_protocol") || "auto";
    const eligibility = toolCompat.data?.eligibility || {};
    const blocked = choice !== "auto" && eligibility[choice] && !eligibility[choice].available
      && choice !== (toolCompat.data.requested || "auto");
    if (blocked) {
      toast(`${modeLabels[choice]} cannot generate tool calls on this route: ${eligibility[choice].reason}`, true);
      toolProtocolSelect.focus();
      return;
    }
    const parseSpecs = value => String(value || "").split(",").map(part => part.trim()).filter(Boolean);
    const fallbacks = parseSpecs(fd.get("fallbacks"));
    const escalationTo = parseSpecs(fd.get("escalation"));
    const taskRoutes = Object.fromEntries($$("[data-task-route]", ev.target)
      .map(input => [input.dataset.taskRoute, input.value.trim()]).filter(([, spec]) => spec));
    patch({ model: fd.get("model").trim(), runtime: fd.get("runtime") || b.runtime,
      inference_mode: fd.get("inference_mode"),
      preset: fd.get("preset") || null, tool_protocol: choice, fallbacks,
      escalation: { ...(b.escalation || {}), to: escalationTo },
      task_routes: taskRoutes,
      compaction: fd.get("compaction") || "ask" }, "Model settings saved.");
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
  $("#form-computer").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    patch({ local_dev_origins: String(fd.get("local_dev_origins") || "").split(/\n/).map(s => s.trim()).filter(Boolean),
      computer_apps: String(fd.get("computer_apps") || "").split(",").map(s => s.trim()).filter(Boolean),
      observation_to_hosted: fd.get("observation_to_hosted") === "on",
      remote_computer_access: fd.get("remote_computer_access") }, "Computer access saved.");
  });
  $("#computer-doctor").addEventListener("click", async ev => {
    const button = ev.currentTarget, status = $("#computer-readiness");
    button.disabled = true; status.textContent = "Checking this host…";
    try {
      const report = await api("/v1/computer/readiness");
      const capabilities = report.capabilities || [];
      status.textContent = `Browser: ${report.summary?.browser || "unknown"}. Personal desktop: ${report.summary?.native_desktop || "unknown"}. Expand the details for private desktop prerequisites and setup.`;
      const details = $("#computer-readiness-details"), list = details.querySelector("ul");
      list.replaceChildren(...capabilities.map(c => {
        const li = document.createElement("li"), title = document.createElement("b"), description = document.createElement("p");
        title.textContent = `${c.title || c.id}: ${c.state}`;
        description.textContent = `${c.detail || ""}${c.fix ? " " + c.fix : ""}`;
        li.append(title, description); return li;
      }));
      details.hidden = capabilities.length === 0;
    } catch (err) { status.textContent = `Readiness unavailable: ${err.message}`; }
    finally { button.disabled = false; }
  });
  $("#btn-add-schedule").addEventListener("click", () => {
    const form = `<form id="modal-schedule-form" class="form-grid">
      <label class="check"><input type="checkbox" name="enabled" checked> Enable immediately</label>
      <label class="field">Task name<input name="name" maxlength="80" value="Scheduled task" required></label>
      <label class="field">Trigger<select name="trigger"><option value="cron">Calendar cron</option><option value="interval">Fixed interval</option></select></label>
      <div class="form-grid row2">
        <label class="field">Cron expression<input name="cron" placeholder="0 9 * * 1" required></label>
        <label class="field">Interval (minutes)<input type="number" name="interval_minutes" min="1" value="65"></label>
        <label class="field">Timezone<input name="timezone" value="UTC" required></label>
        <label class="field">If already busy<select name="overlap"><option value="queue">Queue</option><option value="skip">Skip</option><option value="buffer_one">Keep one waiting</option></select></label>
      </div>
      <label class="field">Missed run policy<select name="catch_up"><option value="coalesce">Run once and report missed windows</option><option value="skip">Skip if the last window was missed</option></select></label>
      <label class="field">Task prompt<textarea name="prompt" rows="3" maxlength="4000"></textarea>
        <span class="hint">Leave blank to use this bot’s standing instructions. Uncheck Enable to save a draft.</span>
      </label>
    </form>`;
    openModal({ title: "Add a recurring task", bodyHtml: form, confirmText: "Add task", returnFocus: $("#btn-add-schedule"),
      onConfirm: async () => {
        const fd = new FormData($("#modal-schedule-form"));
        const scheduleId = `schedule_${newIdempotencyKey().replace(/[^a-zA-Z0-9_-]/g, "")}`;
        try {
          await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(scheduleId)}`, {
            method: "PUT", body: scheduleBodyFromForm(fd),
          });
          toast(fd.get("enabled") ? "Recurring task added." : "Draft routine saved (not enabled).");
          renderBotDetail(b.name); refreshRoster();
          return true;
        } catch (err) { toast(`Task not added: ${err.message}`, true); return false; }
      },
    });
  });
  $$("[data-schedule-advanced-toggle]").forEach(button => button.addEventListener("click", () => {
    const panel = button.parentElement?.querySelector(".schedule-advanced");
    if (!panel) return;
    const open = panel.hidden;
    panel.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }));
  $$("[data-schedule-trigger]").forEach(select => select.addEventListener("change", () => {
    const form = select.closest("form");
    if (!form) return;
    const trigger = select.value;
    form.querySelectorAll("[data-cron-field]").forEach(el => { el.hidden = trigger !== "cron"; el.querySelector("input")?.toggleAttribute("required", trigger === "cron"); });
    form.querySelectorAll("[data-interval-field]").forEach(el => { el.hidden = trigger !== "interval"; el.querySelector("input")?.toggleAttribute("required", trigger === "interval"); });
    form.querySelectorAll("[data-anchor-field]").forEach(el => { el.hidden = trigger === "cron"; el.querySelector("input")?.toggleAttribute("required", trigger === "once"); });
  }));
  $$('[data-schedule-workflow-definition]').forEach(select => select.addEventListener("change", () => {
    const form = select.closest("form");
    if (!form) return;
    const selected = select.selectedOptions[0];
    const linked = Boolean(select.value);
    const revision = form.querySelector('[name="workflow_revision_id"]');
    const inputsField = form.querySelector("[data-workflow-inputs-field]");
    const inputsTitle = form.querySelector("[data-workflow-inputs-title]");
    const revisionSummary = form.querySelector("[data-workflow-revision-summary]");
    const selectedName = selected?.textContent?.replace(/ · inactive$/, "") || "saved workflow";
    if (revision) revision.value = linked ? (selected?.dataset.revisionId || "") : "";
    if (inputsField) inputsField.hidden = !linked;
    if (inputsTitle) inputsTitle.textContent = `Inputs for ${selectedName}`;
    if (revisionSummary) {
      revisionSummary.hidden = !linked;
      revisionSummary.textContent = linked
        ? `Pinned revision ${revision?.value || "not available"} of ${selectedName}.`
        : "";
    }
  }));
  $$('[data-schedule-form]').forEach(form => form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const fd = new FormData(form);
    const scheduleId = form.dataset.scheduleId;
    try {
      await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(scheduleId)}`, {
        method: "PUT", headers: { "Idempotency-Key": newIdempotencyKey() }, body: scheduleBodyFromForm(fd),
      });
      toast(fd.get("workflow_definition_id")
        ? (fd.get("enabled") === "on" ? "Saved workflow linked. Future runs are enabled." : "Saved workflow linked to this draft. Future runs stay off until enabled.")
        : (fd.get("enabled") === "on" ? "Scheduled task saved." : "Draft saved. Future occurrences stay off until enabled."));
      renderBotDetail(b.name); refreshRoster();
    } catch (err) { toast(`Task not saved: ${err.message}`, true); }
  }));
  $$("[data-schedule-run-now-bot]").forEach(button => button.addEventListener("click", async () => {
    try {
      const result = await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(button.dataset.scheduleRunNowBot)}/run-now`, {
        method: "POST", headers: { "Idempotency-Key": newIdempotencyKey() }, body: {},
      });
      toast(result?.workflow_run_id
        ? "Started the linked saved workflow once. The routine schedule is unchanged."
        : "Started a one-off run. The recurring schedule is unchanged.");
      if (result?.run_id) location.hash = `#/run/${encodeURIComponent(result.run_id)}`;
    } catch (err) { toast(`Could not run now: ${err.message}`, true); }
  }));
  $$("[data-schedule-skip-next-bot]").forEach(button => button.addEventListener("click", async () => {
    try {
      await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(button.dataset.scheduleSkipNextBot)}/skip-next`, { method: "POST", body: {} });
      toast("Next occurrence will be skipped.");
      renderBotDetail(b.name);
    } catch (err) { toast(`Could not skip next: ${err.message}`, true); }
  }));
  $$("[data-show-occurrences]").forEach(button => button.addEventListener("click", async () => {
    const scheduleId = button.dataset.showOccurrences;
    const panel = view.querySelector(`[data-occurrence-panel="${CSS.escape(scheduleId)}"]`);
    if (!panel) return;
    panel.hidden = false;
    const list = panel.querySelector(".schedule-occurrence-list");
    list.textContent = "Loading…";
    try {
      const rows = await api(`/v1/bots/${encodeURIComponent(b.id)}/schedules/${encodeURIComponent(scheduleId)}/occurrences?limit=20`);
      list.innerHTML = rows.length
        ? `<ol>${rows.map(row => `<li><time datetime="${esc(row.occurrence)}">${esc(row.occurrence)}</time> · ${esc(row.run_status || "unknown")}${row.missed_windows ? ` · missed ${esc(row.missed_windows)}` : ""} · <a href="#/run/${encodeURIComponent(row.run_id)}">open run</a></li>`).join("")}</ol>`
        : "No claimed occurrences yet.";
    } catch (err) { list.textContent = `History unavailable: ${err.message}`; }
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
  $("#form-limits").addEventListener("submit", async ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const limits = Object.fromEntries([...fd.entries()].filter(([key]) => !["timeout_minutes", "band_warn_usd", "band_pause_usd", "band_ceiling_usd", "unknown_price"].includes(key)).map(([key, value]) => [key,
      ["max_cost_usd", "daily_cost_cap_usd"].includes(key) ? Number(value) : Number.parseInt(value, 10)]));
    limits.timeout_seconds = Math.round(Number(fd.get("timeout_minutes")) * 60);
    await patch({ limits }, "Limits saved.");
    try {
      const band = name => { const raw = fd.get(name); return raw === "" || raw === null ? null : Number(raw); };
      const policy = await api("/v1/budgets", { method: "PUT", body: {
        scope_kind: "bot", scope_id: b.id, reset: "local_day",
        warn_usd: band("band_warn_usd"), pause_usd: band("band_pause_usd"), ceiling_usd: band("band_ceiling_usd"),
        unknown_price: fd.get("unknown_price") || "refuse",
      }});
      toast(policy.ceiling_usd === null ? "Spending bands saved (warn-only and pause are advisory safeguards, not a hard cap)." : "Spending bands saved.");
    } catch (err) { toast(`Bands not saved: ${err.message}`, true); }
  });
  $("#form-rule").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const rule = { match: fd.get("match").trim(), verdict: fd.get("verdict") };
    if (!rule.match) return;
    patch({ command_rules: [...rules, rule] }, "Rule added.");
  });
  wireFactControls(factsPage.facts, b.name, factSharesPage);
  $('#memory-toggle').onchange = async event => {
    const control = event.currentTarget;
    const mode = control.value;
    control.disabled = true;
    const saved = await patch({memory_enabled: mode !== 'off', memory_learning: mode === 'off' ? b.memory_learning : mode,
      expected_memory_revision: b.memory_revision},
      mode === 'off' ? 'Memory disabled.' : mode === 'hybrid' ? 'Hybrid learning enabled.' : 'New facts require review.');
    if (!saved) control.value = b.memory_enabled ? b.memory_learning : 'off';
    control.disabled = false;
  };
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
      out.textContent = e.summary || `estimated at ${fmtUsd(e.effective_ceiling_usd ?? 0)} per run; provider billing can differ`;
    } catch (err) { out.textContent = err.message; }
  });
  $("#btn-delete-bot").addEventListener("click", async () => {
    $(".assistant-settings-menu").open = false;
    if (!(await confirmDialog({
      title: "Delete assistant",
      body: `Delete <b>${esc(b.name)}</b>? Its workspace, memory, and transcripts stay on disk, but the bot and its schedule are removed.`,
      confirmText: "Delete assistant", danger: true,
    }))) return;
    await api(`/bots/${encodeURIComponent(b.name)}`, { method: "DELETE" });
    toast(`Deleted ${b.name}`);
    location.hash = "#/chat";
    refreshRoster();
  });
  wireCommon();
}

/* ------------------------------------------------------------- run detail */

const runDetailSnapshots = new WeakMap();
let runDetailRequest = 0;

async function renderRunDetail(runId, params = new URLSearchParams()) {
  const generation = studioGeneration;
  const request = ++runDetailRequest;
  const stillCurrent = () => generation === studioGeneration
    && request === runDetailRequest
    && (location.hash === `#/run/${runId}` || location.hash.startsWith(`#/run/${runId}?`));
  feedMode = "run";
  const r = await api(`/runs/${runId}`, { signal: routeOwner.abort?.signal });
  if (!stillCurrent()) return;
  // Control may have started while this refresh awaited the API. Recheck before replacing any controller DOM.
  if (window.HutchComputer?.hasControl(runId)) return;
  const snapshot = JSON.stringify([generation, params.toString(), { ...r, transcript_mirror: undefined }]);
  if (!ACTIVE.has(r.status) && runDetailSnapshots.get(view.firstElementChild) === snapshot) {
    const mirrorNotice = $("[data-run-mirror-notice]", view);
    const notice = runMirrorNoticeHtml(r.transcript_mirror);
    if (mirrorNotice && mirrorNotice.innerHTML !== notice) mirrorNotice.innerHTML = notice;
    updateTtls();
    return; // Global changes must preserve unchanged widgets, selection and focus.
  }
  currentStudioBot = r.bot_name;
  currentRunId = runId;
  // Render the header and transcript from the same authoritative response.
  const block = await runBlockHtml(runId, null, [], [], r);
  if (!stillCurrent() || window.HutchComputer?.hasControl(runId)) return;
  setTopContext(`
    <div class="ctx-id"><h1>Task details</h1>
      <div class="ctx-meta">${statusChip(r.status, r.status_label)}</div></div>
    <div class="ctx-actions">
      ${ACTIVE.has(r.status) ? `<button class="btn danger small" id="stop-this-run" ${r.status === "cancelling" ? "disabled" : ""}>${icon("stop")} ${r.status === "cancelling" ? "Stopping" : "Stop"}</button>` : ""}
      <a class="btn ghost small" href="#/runs">${icon("arrowLeft")} All runs</a>
    </div>`);
  const steps = (r.events || []).filter(e => e.type === "step").map(e => e.data);
  // Refreshes can replace this view while a run is settling. Preserve an
  // operator's disclosure state so the visible transcript does not collapse.
  const previousTechnicalDetails = document.querySelector("#run-technical-details");
  const technicalDetailsOpen = previousTechnicalDetails?.dataset.runId === runId && previousTechnicalDetails.open;
  const sum = (k) => steps.reduce((t, d) => t + (d[k] || 0), 0);
  const model = sum("model_ms"), tool = sum("tool_ms"), over = sum("overhead_ms"), queue = sum("queue_ms");
  const total = Math.max(1, model + tool + over + queue);
  const pct = (v) => (v / total * 100).toFixed(1);
  const dur = (r.finished_at ? new Date(r.finished_at) : Date.now()) - new Date(r.created_at);
  view.innerHTML = `
    <div class="page-scroll run-detail-page" id="chat-scroll"><div class="feed" id="chat-stream">
      <div class="run-stats">
        <details class="run-technical-details" id="run-technical-details" data-run-id="${esc(runId)}"${technicalDetailsOpen ? " open" : ""}>
          <summary><span>More details</span><span>Usage, timing, and transcript checks</span></summary>
          <div class="run-technical-content">
        <div class="ov-stats">
          <div class="kpi"><span class="kpi-label">Steps</span><span class="kpi-val">${r.steps}</span></div>
          <div class="kpi"><span class="kpi-label">Elapsed</span><span class="kpi-val">${fmtDur(dur)}</span></div>
          <div class="kpi"><span class="kpi-label">Recorded cost</span><span class="kpi-val">${fmtUsd(r.cost_usd || 0)}</span></div>
          <div class="kpi"><span class="kpi-label">Reported tokens</span><span class="kpi-val">${fmtTokens(r.tokens)}</span></div>
        </div>
        ${(() => {
          const used = r.context_used || 0, limit = r.context_limit || 0;
          const share = limit ? Math.round(used / limit * 100) : 0;
          const state = limit && share >= 100 ? "over" : limit && share >= 85 ? "warn" : "";
          const label = limit ? `Context: ${fmtTokens(used)} of ${fmtTokens(limit)} tokens (${share}%)`
                              : `Context: ${fmtTokens(used)} tokens used — this runtime did not report a window`;
          return `<p class="context-line ${state}">${label}</p>`;
        })()}
        ${(() => {
          const counted = steps.filter(d => d.cost_source);
          if (!counted.length) return "";
          const provider = counted.filter(d => d.cost_source === "provider").length;
          const estimated = counted.filter(d => d.cost_source === "estimated").length;
          const unknown = counted.filter(d => d.cost_source === "unknown").length;
          return `<p class="run-cost-provenance hint">Charges this task: ${provider} provider-reported · ${estimated} estimated${unknown ? ` · ${unknown} with an unknown price` : ""}.</p>`;
        })()}
        ${(r.compactions || []).length ? `<div class="panel compaction-list"><div class="panel-title">Context summaries</div>
          ${r.compactions.map(c => `<div class="meta-row"><span>#${c.seq} · ${esc(c.status)} · ${fmtTokens(c.before_tokens)} to ${fmtTokens(c.after_tokens)} tokens · ${c.attempts} attempt(s)</span><span class="hint">${esc(String(c.created_at || "").slice(0, 19))}</span></div>`).join("")}
          <p class="hint">The original messages are unchanged; summaries are bounded, recorded, and use routes already approved for this task.</p></div>` : ""}
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
            <p class="run-reference hint">Run reference <code>${esc(runId)}</code></p>
          </div>
        </details>
      </div>
      <div class="evidence-host" data-evidence-host="${esc(runId)}"></div>
    </div></div>`;
  // append the transcript block below the stats
  const stream = $("#chat-stream");
  if (!stillCurrent() || !stream.isConnected) return;
  stream.insertAdjacentHTML("beforeend", block);
  window.HutchComputer?.mount(stream, runId, { api });   // owned computer-session panel and human step control
  void renderEvidencePanel(runId, r.events || [], params);
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
  runDetailSnapshots.set(view.firstElementChild, snapshot);
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

async function openKDEConnectSetup(button, bots) {
  button.disabled = true;
  let connection;
  try { connection = await api("/v1/connections/kdeconnect"); }
  catch (error) { toast(error.message, true); return; }
  finally { button.disabled = false; }
  const eligible = bots.filter(bot => bot.inference_mode !== "offline" && ["builtin", "opencode"].includes(bot.runtime));
  let devices = null;
  openModal({ title: "KDE Connect device access", returnFocus: button,
    confirmText: connection.available ? "Find paired devices" : "Close", showCancel: !!connection.available,
    bodyHtml: `<p>Read a device’s connection and last reported battery. Choose one device and assistant. Status may go to that assistant’s model provider and run history.</p>
      <p class="hint">This grants status reads only. Removing access here leaves KDE Connect pairing intact.</p>
      ${!connection.available ? '<p role="status">This connection needs Linux with busctl installed. Pair the device in the KDE Connect app first.</p>' : '<p>Pair your phone in KDE Connect first, then choose Find paired devices.</p>'}
      <div id="kdeconnect-device-fields"></div><p class="hint" id="kdeconnect-status" role="status"></p>
      <div aria-label="Current device status access">${(connection.grants || []).map(grant => `<div class="device-row"><div><strong>${esc(grant.label)}</strong><p class="hint">${esc(bots.find(bot => bot.id === grant.bot_id)?.display_name || bots.find(bot => bot.id === grant.bot_id)?.name || "Assistant")} · status and battery only</p></div><button class="btn ghost small" type="button" data-kdeconnect-revoke="${esc(grant.device_id)}" data-kdeconnect-bot="${esc(grant.bot_id)}">Remove access</button></div>`).join("") || '<p class="hint">No assistant has device status access.</p>'}</div>`,
    onConfirm: async () => {
      if (!connection.available) return true;
      const confirm = $("#modal-confirm"), status = $("#kdeconnect-status"), fields = $("#kdeconnect-device-fields");
      if (confirm.disabled) return false;
      confirm.disabled = true;
      try {
        if (!devices) {
          status.textContent = "Looking for devices already paired in KDE Connect…";
          const result = await api("/v1/connections/kdeconnect/discover", { method: "POST", body: {} });
          if (!fields.isConnected) return false;
          if (!result.devices?.length) { status.textContent = "No paired devices found. Pair your phone in KDE Connect, then try again."; return false; }
          devices = result.devices;
          fields.innerHTML = `<label class="field">Paired device<select id="kdeconnect-device"><option value="">Choose a device…</option>${devices.map(device => `<option value="${esc(device.device_id)}">${esc(device.name)} · ${device.reachable ? "connected" : "offline"}${device.battery ? ` · ${Number(device.battery.percent)}% reported battery` : ""}</option>`).join("")}</select></label>
            <label class="field">Assistant<select id="kdeconnect-bot"><option value="">Choose an assistant…</option>${eligible.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("")}</select></label>`;
          confirm.textContent = "Allow status reads";
          status.textContent = eligible.length ? "Select a device and assistant to allow status reads." : "Create a built-in or OpenCode assistant outside Strict Offline mode first.";
          fields.addEventListener("change", () => {
            status.textContent = $("#kdeconnect-device")?.value && $("#kdeconnect-bot")?.value
              ? "Ready to allow status reads for this device and assistant." : "Choose both a device and an assistant.";
          });
          $("#kdeconnect-device")?.focus();
          return false;
        }
        const deviceId = $("#kdeconnect-device")?.value, botId = $("#kdeconnect-bot")?.value;
        if (!deviceId || !botId) { status.textContent = "Choose both a device and an assistant."; return false; }
        await api("/v1/connections/kdeconnect/grants", { method: "POST", body: { device_id: deviceId, bot: botId } });
        toast("Device status access saved. Ask the selected assistant about its connection or battery.");
        // A late result must not close a different dialog opened in the meantime.
        return confirm.isConnected;
      } catch (error) { if (status.isConnected) status.textContent = error.message; return false; }
      finally { if (confirm.isConnected) confirm.disabled = false; }
    },
  });
  $$("#modal-root [data-kdeconnect-revoke]").forEach(control => control.addEventListener("click", async () => {
    control.disabled = true;
    try {
      await api(`/v1/connections/kdeconnect/devices/${encodeURIComponent(control.dataset.kdeconnectRevoke)}/grants/${encodeURIComponent(control.dataset.kdeconnectBot)}`, { method: "DELETE" });
      control.textContent = "Access removed";
    } catch (error) { toast(error.message, true); if (control.isConnected) control.disabled = false; }
  }));
}

async function renderConnections() {
  const requestedHash = location.hash;
  if (!/^#\/connections(?:\?|$)/.test(requestedHash)) return;
  const generation = ++connectionsGeneration;
  const stillCurrent = () => generation === connectionsGeneration && location.hash === requestedHash;
  let data;
  try { data = await api("/connections"); }
  catch (err) { if (stillCurrent()) view.innerHTML = errorState(err); return; }
  if (!stillCurrent()) return;
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
  let phoneSetup = { ready: false, pair_url: "", detail: "Could not load phone connection setup. Reload to try again." };
  try { phoneSetup = await api("/v1/pairing/setup"); } catch { /* keep visible failure and existing device controls */ }
  if (!stillCurrent()) return;
  setTopContext(`<div class="ctx-id"><h1>Apps &amp; AI</h1></div>`);
  const conns = data.connections || [];
  const googleOAuthClient = data.google_oauth_client || {
    client_id: "", source: "unset", editable: true, configured: false, valid: false,
    detail: "Google sign-in is not enabled in this Hutch build.",
  };
  const googleCalendar = data.google_calendar || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const [workspaceResult, notionConnectionResult, deviceConnectionResult] = await Promise.allSettled([
    api("/v1/connections/google-workspace"), api("/v1/connections/notion"), api("/v1/connections/kdeconnect"),
  ]);
  const googleWorkspace = workspaceResult.status === "fulfilled" ? workspaceResult.value
    : { configured: false, secret_store_available: false, accounts: [] };
  const workspaceError = workspaceResult.status === "rejected" ? workspaceResult.reason.message : "";
  const notion = notionConnectionResult.status === "fulfilled" ? notionConnectionResult.value
    : { secret_store_available: false, accounts: [], grants: [] };
  const notionError = notionConnectionResult.status === "rejected" ? notionConnectionResult.reason.message : "";
  const deviceConnection = deviceConnectionResult.status === "fulfilled" ? deviceConnectionResult.value : { available: false, grants: [] };
  if (!stillCurrent()) return;
  const googleMail = data.google_mail || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const googleMailBots = bots.filter(bot => bot.inference_mode === "local");
  const googleMailSend = data.google_mail_send || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const googleMailSendBots = bots.filter(bot => bot.inference_mode !== "offline");
  const outlookCalendar = data.outlook_calendar || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const outlookCalendarWrite = data.outlook_calendar_write || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const outlookMail = data.outlook_mail || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const outlookMailSend = data.outlook_mail_send || { configured: false, secret_store_available: false, accounts: [], grants: [] };
  const windows = { "5h": "per 5 hours", "day": "per day", "week": "per week", "month": "per month" };
  const devicesOpen = $(".device-manager")?.open || false;
  const outlookCalendarAccessOpen = $("#outlook-calendar-access")?.open || false;
  const outlookCalendarWriteAccessOpen = $("#outlook-calendar-write-access")?.open || false;
  const outlookMailAccessOpen = $("#outlook-mail-access")?.open || false;
  const outlookMailSendAccessOpen = $("#outlook-mail-send-access")?.open || false;
  const googleMailAccessOpen = $("#google-mail-access")?.open || false;
  const googleMailSendAccessOpen = $("#google-mail-send-access")?.open || false;
  const googleOAuthSetupOpen = $("#google-oauth-setup")?.open ?? false;
  const connectionManagerOpen = $("#connection-management")?.open || false;
  const googleCalendarAccountsHtml = (googleCalendar.accounts || []).map(account => {
    const grants = (googleCalendar.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">${grant.allow_event_creation ? "Can read and create events on" : "Can read"} ${esc(grant.calendar_name)} · ${esc(account.label)}${grant.allow_event_creation ? " · every creation needs approval" : ""}</p></div>
        <button class="btn ghost small" type="button" data-google-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")
      : '<p class="hint">No Bot has access to this account.</p>';
    return `<article class="google-calendar-account" data-google-calendar-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">${account.can_create_events ? "Calendar read and event-creation scope" : "Read-only calendar-list and event scopes"} · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
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
        ${account.can_create_events ? `<label class="background-consent-row calendar-create-consent">
          <input type="checkbox" data-google-calendar-create-access disabled>
          <span>Allow event creation after each approval<small>Only calendars you own qualify. Guests, invitations, edits and deletion stay unavailable.</small></span>
        </label>` : '<p class="hint">This account is read-only. To grant event creation, reconnect with the explicit event-creation option below.</p>'}
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
  const googleMailSendAccountsHtml = (googleMailSend.accounts || []).map(account => {
    const grants = (googleMailSend.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">May prepare approved messages · ${esc(account.from_address)}</p></div>
        <button class="btn ghost small" type="button" data-google-mail-send-ungrant="${esc(grant.bot_id)}">Revoke send access</button></div>`).join("")
      : '<p class="hint">No assistant has send access to this account.</p>';
    return `<article class="google-calendar-account" data-google-mail-send-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">send only</span>
        <p class="hint">From ${esc(account.from_address)} · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-google-mail-send-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Assistants with Gmail send access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-google-mail-send-grant-form="${esc(account.id)}">
        <label class="field">Choose an assistant
          <select data-google-mail-send-bot ${googleMailSendBots.length ? "" : "disabled"} aria-label="Assistant for Gmail send access">
            ${googleMailSendBots.length ? googleMailSendBots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create an assistant first</option>'}
          </select>
        </label>
        <button class="btn primary small" type="button" data-google-mail-send-grant="${esc(account.id)}" ${googleMailSendBots.length ? "" : "disabled"}>Allow approved sending</button>
        <p class="hint" role="status" aria-live="polite" data-google-mail-send-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanGoogleMailSendGrants = (googleMailSend.grants || []).filter(grant =>
    !(googleMailSend.accounts || []).some(account => account.id === grant.account_id));
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
  const outlookCalendarWriteAccountsHtml = (outlookCalendarWrite.accounts || []).map(account => {
    const grants = (outlookCalendarWrite.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can create approved events on ${esc(grant.calendar_name)} · ${esc(account.label)}</p></div>
        <button class="btn ghost small" type="button" data-outlook-calendar-write-ungrant="${esc(grant.bot_id)}">Revoke event access</button></div>`).join("")
      : '<p class="hint">No assistant has event-creation access to this account.</p>';
    return `<article class="google-calendar-account" data-outlook-calendar-write-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Separate Calendars.ReadWrite sign-in · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-outlook-calendar-write-disconnect="${esc(account.id)}">Disconnect</button>
      </div>
      <div class="google-calendar-grants" aria-label="Assistants with Outlook event-creation access">${grantRows}</div>
      <div class="google-calendar-grant-form" data-outlook-calendar-write-grant-form="${esc(account.id)}">
        <label class="field">Choose an assistant
          <select data-outlook-calendar-write-bot ${bots.length ? "" : "disabled"} aria-label="Assistant for Outlook event access">
            ${bots.length ? bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create an assistant first</option>'}
          </select>
        </label>
        <button class="btn ghost small" type="button" data-outlook-calendar-write-load-calendars="${esc(account.id)}" ${bots.length ? "" : "disabled"}>Load calendars</button>
        <label class="field" hidden data-outlook-calendar-write-calendar-field>Calendar
          <select data-outlook-calendar-write-calendar aria-label="Outlook calendar for event creation" disabled><option value="">Choose a calendar…</option></select>
        </label>
        <button class="btn primary small" type="button" data-outlook-calendar-write-grant="${esc(account.id)}" disabled>Allow approved event creation</button>
        <p class="hint" role="status" aria-live="polite" data-outlook-calendar-write-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanOutlookCalendarWriteGrants = (outlookCalendarWrite.grants || []).filter(grant =>
    !(outlookCalendarWrite.accounts || []).some(account => account.id === grant.account_id));
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
  const outlookMailSendAccountsHtml = (outlookMailSend.accounts || []).map(account => {
    const grants = (outlookMailSend.grants || []).filter(grant => grant.account_id === account.id);
    const grantRows = grants.length ? grants.map(grant => `
      <div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can prepare one plain-text email · ${esc(account.label)} · every send needs your exact approval</p></div>
        <button class="btn ghost small" type="button" data-outlook-mail-send-ungrant="${esc(grant.bot_id)}">Revoke send access</button></div>`).join("")
      : '<p class="hint">No Bot can prepare email from this account.</p>';
    return `<article class="google-calendar-account outlook-mail-send-account" data-outlook-mail-send-account="${esc(account.id)}">
      <div class="device-row"><div><strong>${esc(account.label)}</strong> <span class="chip ok">connected</span>
        <p class="hint">Delegated Mail.Send only · connected ${esc(new Date(account.created_at).toLocaleDateString())}</p></div>
        <button class="btn danger small" type="button" data-outlook-mail-send-disconnect="${esc(account.id)}">Disconnect sending account</button>
      </div>
      <div class="outlook-mail-send-grants" aria-label="Bots with Outlook Mail sending access">${grantRows}</div>
      <div class="google-calendar-grant-form outlook-mail-send-grant-form" data-outlook-mail-send-grant-form="${esc(account.id)}">
        <label class="field">Give one Bot permission to prepare email
          <select data-outlook-mail-send-bot ${bots.length ? "" : "disabled"} aria-label="Bot for Outlook Mail sending access">
            ${bots.length ? bots.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("") : '<option value="">Create a Bot first</option>'}
          </select>
        </label>
        <button class="btn primary small" type="button" data-outlook-mail-send-grant="${esc(account.id)}" ${bots.length ? "" : "disabled"}>Grant send access</button>
        <p class="hint" role="status" aria-live="polite" data-outlook-mail-send-status></p>
      </div>
    </article>`;
  }).join("");
  const orphanOutlookMailSendGrants = (outlookMailSend.grants || []).filter(grant =>
    !(outlookMailSend.accounts || []).some(account => account.id === grant.account_id));
  const notionGrantRows = account => [...new Set(notion.grants.filter(grant => grant.account_id === account).map(grant => grant.bot_id))].map(bot => {
    const names = notion.grants.filter(grant => grant.account_id === account && grant.bot_id === bot).map(grant => grant.name).join(", ");
    return `<div class="device-row"><p class="hint">${esc(botLabels.get(bot) || bot)} · ${esc(names)}</p><button class="btn ghost small" type="button" data-notion-revoke="${esc(account)}" data-notion-bot="${esc(bot)}">Revoke assistant access</button></div>`;
  }).join("");
  const chatgptAccounts = data.chatgpt_accounts || [];
  const tile = (kind, title, description, state, stateKind, action = "manage", actionLabel = "Manage") => `
    <article class="service-tile" data-connection-entry="${esc(action)}" data-connection-title="${esc(title)}" data-connection-state="${esc(stateKind)}">
      <div class="service-tile-top">${serviceMark(kind)}<h3>${esc(title)}</h3><span class="service-state ${stateKind}">${esc(state)}</span></div>
      <p>${esc(description)}</p>
      <button class="service-tile-action" type="button" data-connection-open="${esc(action)}">
        ${esc(actionLabel)}${icon("arrow")}
      </button>
    </article>`;
  const fileServices = [
    { id: "drive", title: "Google Drive", description: "Upload files to a chosen folder, with a reviewed destination and verified result.",
      lead: "Put finished work where it belongs.", tasks: ["Upload a prepared file to a selected folder", "Verify the uploaded file before reporting success"],
      boundary: "Access stays limited to files created by Hutch or opened or shared with this app. Full-Drive search and a file picker are not available yet." },
    { id: "docs", title: "Google Docs", description: "Turn research and drafts into documents. Review the content before it reaches Google.",
      lead: "From a working draft to a useful document.", tasks: ["Create a document from an approved draft", "Update content with revision checks and read it back"],
      boundary: "Hutch can work with documents created by Hutch or opened or shared with this app. This connection does not give access to every document in your account." },
    { id: "sheets", title: "Google Sheets", description: "Create trackers and append structured rows, with validation and readback.",
      lead: "Keep the numbers and the next steps together.", tasks: ["Create a spreadsheet with named sheets", "Append validated rows and check the stored result"],
      boundary: "Hutch can work with spreadsheets created by Hutch or opened or shared with this app. This connection does not give access to every spreadsheet in your account." },
  ];
  const enabledFileServices = account => account.services ?? ["drive", "docs", "sheets"];
  const fileServiceName = id => fileServices.find(item => item.id === id)?.title || id;
  const googleFilePanel = service => {
    const connected = googleWorkspace.accounts.filter(account => enabledFileServices(account).includes(service.id));
    const available = googleWorkspace.accounts.filter(account => !enabledFileServices(account).includes(service.id)
      && account.scopes.includes("https://www.googleapis.com/auth/drive.file"));
    const accountCard = (account, enabled) => `<article class="google-file-account">
      <div class="google-file-account-head"><div><h3>${esc(account.label)}</h3>${account.email && account.email !== account.label ? `<p class="hint google-file-account-email">${esc(account.email)}</p>` : ""}<p class="hint">${enabled ? "Enabled for this service" : "Already connected to Hutch"}</p></div>
        <button class="btn ${enabled ? "ghost" : "primary"}" type="button" data-google-file-service="${service.id}" data-google-file-account="${esc(account.account_id)}" data-google-file-enabled="${!enabled}" data-google-file-revision="${Number(account.revision || 0)}">${enabled ? `Disable ${esc(service.title)}` : "Use this account"}</button></div>
      <p class="hint">Also enabled: ${esc(enabledFileServices(account).filter(id => id !== service.id).map(fileServiceName).join(", ") || "No other file services")}</p>
      <details class="google-file-account-details"><summary>Account details</summary>${account.email ? "" : '<p class="hint">This older connection has no verified account email. Reconnect to identify the selected Google account.</p>'}<p class="hint">Account reference: <code>${esc(account.account_id)}</code></p>
        <p class="hint">${account.scopes.some(scope => /auth\/(documents|spreadsheets)$/.test(scope)) ? "This older connection has broader Google permissions. Disconnect and reconnect to use per-file consent." : "Google permission: per-file access (drive.file)."}</p>
        <button class="btn danger" type="button" data-workspace-disconnect="${esc(account.account_id)}">Disconnect shared Google account</button></details>
    </article>`;
    return `<section class="panel conn-card google-file-card" id="connection-google-${service.id}" aria-labelledby="google-${service.id}-title">
      <div class="bot-head"><span class="bot-name" id="google-${service.id}-title">${service.title}</span><span class="tag">Preview</span></div>
      <section class="google-file-accounts" aria-label="${service.title} accounts"><div class="google-file-section-head"><h2>${connected.length ? "Connected accounts" : "Connect an account"}</h2>
        ${googleWorkspace.configured && googleWorkspace.secret_store_available ? `<button class="btn ${connected.length || available.length ? "ghost" : "primary"}" type="button" data-google-file-connect="${service.id}">${connected.length || available.length ? "Connect another Google account" : `Connect ${service.title}`}</button>` : ""}</div>
        ${workspaceError ? `<p class="hint bad" role="alert">Could not load this connection: ${esc(workspaceError)}</p>` : ""}
        ${!googleWorkspace.configured ? '<p class="hint" role="status">Google sign-in is not enabled in this build. Hutch’s publisher must configure its app registration.</p>' : !googleWorkspace.secret_store_available ? '<p class="hint" role="alert">Unlock the operating system’s secure credential store before connecting.</p>' : ""}
        ${connected.map(account => accountCard(account, true)).join("") || `<p class="hint">No ${service.title} accounts connected.</p>`}
        ${available.length ? `<div class="google-file-reuse"><h3>Use an existing Google connection</h3><p class="hint">Enable ${service.title} with its existing per-file permission. No new Google sign-in or assistant permissions.</p>${available.map(account => accountCard(account, false)).join("")}</div>` : ""}
      </section>
      <div class="google-file-overview"><div><h2>${service.lead}</h2><ul>${service.tasks.map(task => `<li>${task}</li>`).join("")}</ul></div>
        <aside class="google-file-boundary"><h3>Your control</h3><p>${service.boundary}</p><p>Connecting an account does not give every assistant access. Assistants need workspace action tools; each execution still needs your approval of its exact account, destination and changes.</p></aside></div>
      <details class="google-file-permissions"><summary>Permissions and shared sign-in</summary><p>New connections request only <code>drive.file</code>. Drive, Docs and Sheets can reuse that permission, but you enable each service separately in Hutch. Disabling this service keeps the others connected. Disconnecting the shared account removes local access for every file service using it and requests Google revocation. Google may also revoke other Hutch Google sign-ins; reconnect affected services if needed.</p><p>Sharing files with people needs separate authority. Existing cloud files remain when you disconnect.</p></details>
    </section>`;
  };
  const appTiles = [
    tile("calendar", "Google Calendar", "See upcoming events. An assistant can create an event only after you approve it.",
      googleCalendar.accounts.length ? "Connected" : googleCalendar.configured ? "Ready to connect" : "Not enabled in this build",
      googleCalendar.accounts.length ? "connected" : "setup", "google-calendar",
      googleCalendar.accounts.length ? "Manage access" : googleCalendar.configured ? "Connect Google" : "Connection details"),
    ...fileServices.map(service => {
      const connected = googleWorkspace.accounts.some(account => enabledFileServices(account).includes(service.id));
      return tile(service.id, service.title, service.description,
        workspaceError ? "Could not load" : connected ? "Connected" : googleWorkspace.configured ? "Ready to connect" : "Not enabled in this build",
        connected ? "connected" : "setup", `google-${service.id}`, connected ? "Manage access" : "Connection details");
    }),
    tile("notion", "Notion", "Search and read your workspace pages with the assistants you choose.",
      notionError ? "Could not load" : notion.accounts.length ? "Connected" : notion.secret_store_available ? "Ready to connect" : "Secure storage required",
      notion.accounts.length ? "connected" : "setup", "notion", notion.accounts.length ? "Manage access" : "Connect Notion"),
    tile("gmail", "Gmail", "Find emails without sending, editing, or deleting messages.",
      googleMail.accounts.length ? "Connected" : googleMail.configured ? "Limited preview" : "Not enabled in this build",
      googleMail.accounts.length ? "connected" : googleMail.configured ? "preview" : "setup", "gmail",
      googleMail.accounts.length ? "Manage access" : googleMail.configured ? "Connect Google" : "Connection details"),
    tile("outlook", "Microsoft Outlook", "Use mail or calendar, then choose which assistant can reach each account.",
      outlookCalendar.accounts.length || outlookMail.accounts.length || outlookMailSend.accounts.length ? "Connected"
        : outlookCalendar.configured && outlookCalendar.secret_store_available ? "Ready to connect" : "Not available here",
      outlookCalendar.accounts.length || outlookMail.accounts.length || outlookMailSend.accounts.length ? "connected" : "setup", "outlook-calendar",
      outlookCalendar.accounts.length || outlookMail.accounts.length || outlookMailSend.accounts.length ? "Manage access"
        : outlookCalendar.configured && outlookCalendar.secret_store_available ? "Connect Microsoft" : "Connection details"),
  ].join("");
  const phoneTile = tile("phone", "Hutch on your phone", "Follow work, review approvals and stop runs from your phone. This connects your phone to Hutch; it does not read phone apps or messages.",
    devices.length ? `${devices.length} paired` : phoneSetup.ready ? "Ready to pair" : "Private connection required",
    devices.length ? "connected" : "setup", "phone", devices.length ? "Manage devices" : phoneSetup.ready ? "Pair a phone" : "Connection details")
    + tile("local", "KDE Connect", "Let an assistant check a paired device’s connection and reported battery. Set up pairing in KDE Connect first.",
      deviceConnectionResult.status === "rejected" ? "Could not load" : deviceConnection.grants.length ? "Status access enabled" : deviceConnection.available ? "Pair in KDE Connect first" : "Linux only",
      deviceConnection.grants.length ? "connected" : "setup", "kdeconnect", "Choose device access");
  const modelTiles = [
    tile("chatgpt", "ChatGPT", "Sign in with ChatGPT where available. Your existing chats stay separate.",
      chatgptAccounts.some(account => account.connected && account.plan_usage) ? "Connected"
        : data.chatgpt_enabled ? "Sign-in preview" : "Not available here",
      chatgptAccounts.some(account => account.connected && account.plan_usage) ? "connected"
        : data.chatgpt_enabled ? "preview" : "unavailable", "chatgpt",
      data.chatgpt_enabled ? "See sign-in options" : "Check availability"),
    tile("hosted", "AI model providers", "Connect OpenAI API, Anthropic, OpenRouter, or another model service.",
      conns.length ? `${conns.length} service${conns.length === 1 ? "" : "s"}` : "Not set up yet",
      conns.length ? "connected" : "setup", "models", conns.length ? "Add or manage providers" : "Connect a provider"),
  ].join("");
  view.innerHTML = `
    <div class="page-scroll"><div class="container connections-workspace">
      <div data-connection-directory>
      <header class="connections-intro">
        <h2>Connect your work</h2>
        <p>Bring your apps, devices and AI together. You choose what each assistant can use.</p>
      </header>
      <div class="connection-toolbar">
        <label class="connection-search" for="connection-search">${icon("search")}<span class="visually-hidden">Find an app or device</span><input id="connection-search" type="search" placeholder="Find an app or device…" autocomplete="off"></label>
        <div class="connection-filters" role="group" aria-label="Filter connections">
          <button type="button" data-connection-filter="all" aria-pressed="true">All</button>
          <button type="button" data-connection-filter="connected" aria-pressed="false">Connected</button>
          <button type="button" data-connection-filter="setup" aria-pressed="false">Not connected</button>
        </div>
        <span class="hint" id="connection-results" role="status"></span>
      </div>
      <section class="connection-empty" id="connection-empty" hidden><h3>No matching connections</h3><p>Try a different name or view all connections.</p><button type="button" class="btn ghost" id="connection-clear-filters">Clear filters</button></section>
      <section class="service-group" aria-labelledby="app-connections-heading">
        <div class="service-group-heading"><h2 id="app-connections-heading">Your apps</h2><p>Documents, calendar and email, with you in control.</p></div>
        <div class="service-grid">${appTiles}</div>
      </section>
      <section class="service-group" aria-labelledby="phone-connection-heading">
        <div class="service-group-heading"><h2 id="phone-connection-heading">Your devices</h2><p>Stay in control while away from this computer.</p></div>
        <div class="service-grid">${phoneTile}</div>
      </section>
      <section class="service-group" aria-labelledby="model-connections-heading">
        <div class="service-group-heading"><h2 id="model-connections-heading">How Hutch replies</h2><p>Choose a service you know, or use one on this computer.</p></div>
        <div class="service-grid">${modelTiles}</div>
        <p class="local-model-note">Each assistant can have its own reply service. You can change it anytime.</p>
      </section>
      </div>
      <header class="connection-detail" data-connection-detail hidden>
        <a class="connection-back" href="#/connections">${icon("arrowLeft")} All connections</a>
        <div class="connection-detail-heading" id="connection-detail-heading"></div>
        <p id="connection-detail-description"></p>
        <button class="btn primary" type="button" data-connection-open="phone-pair" hidden>Pair another phone</button>
        <ol class="connection-steps" aria-label="Connection setup"><li>Connect your account</li><li>Choose assistant access</li><li>Use in chat</li></ol>
      </header>
      <details class="connection-management summary-row-sm" id="connection-management" ${connectionManagerOpen ? "open" : ""}>
        <summary><span class="summary-row-copy"><strong>More account settings</strong><small>Access, permissions and setup details</small></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
        <div class="connection-management-content">
      <section class="panel conn-card" id="connection-chatgpt" aria-labelledby="chatgpt-auth-title">
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
      <section class="panel conn-card google-calendar-card" id="connection-google-calendar" aria-labelledby="google-calendar-title">
        <div class="bot-head"><span class="bot-name" id="google-calendar-title">Google Calendar</span>
          <span class="tag">experimental</span><span class="tag">local desktop sign in</span></div>
        <p class="hint">Connect with Google's official installed-app flow. By default, Hutch reads event titles, times and locations from one calendar you grant to one Bot. You can separately request event-creation access; Hutch shows each guest-free event in chat and waits for your exact approval before creating it.</p>
        <p class="hint"><strong>Google permission:</strong> event creation requires a broader account-level scope that can change or delete events on calendars you own. Google desktop OAuth cannot add that scope later, so it needs a separate sign-in. Hutch exposes only guest-free event creation on the one calendar you choose; it offers no event edits, deletes or invitations. Public OAuth verification and live account tests remain incomplete.</p>
        <details class="google-oauth-setup summary-row-sm" id="google-oauth-setup" ${googleOAuthSetupOpen ? "open" : ""}>
          <summary><span class="summary-row-copy"><strong>Developer settings for Google</strong></span><span class="chip ${googleOAuthClient.configured ? "ok" : "warn"}">${googleOAuthClient.configured ? "client ready" : "setup needed"}</span></summary>
          <div class="google-oauth-setup-body">
            <p class="hint">Released builds should include Hutch’s app registration. These advanced settings let developers override it with their own <strong>Desktop app</strong> registration. Never paste a client secret or access token.</p>
            <label class="field" for="google-oauth-client-id">Google Desktop OAuth client ID
              <input id="google-oauth-client-id" type="text" maxlength="512" autocomplete="off" spellcheck="false"
                value="${esc(googleOAuthClient.client_id || "")}" placeholder="your-client-id.apps.googleusercontent.com"
                aria-describedby="google-oauth-client-help" ${googleOAuthClient.editable ? "" : "readonly"}>
            </label>
            <div class="google-oauth-setup-actions">
              <button class="btn primary small" id="google-oauth-client-save" type="button" ${googleOAuthClient.editable ? "" : "disabled"}>Save client ID</button>
              <button class="btn ghost small" id="google-oauth-client-clear" type="button" ${googleOAuthClient.editable && googleOAuthClient.source === "hutch" ? "" : "disabled"}>Clear</button>
              <span class="hint">${googleOAuthClient.source === "environment" ? "Managed by the Hutch operator; change the environment setting and restart to update it." : googleOAuthClient.source === "hutch" ? "Custom registration saved on this Hutch only." : googleOAuthClient.source === "distribution" ? "Provided by this Hutch build." : "This build has no Google app registration."}</span>
            </div>
            <p class="hint" id="google-oauth-client-help">This one client ID is shared by Calendar, Workspace and the separate Gmail preview. Gmail test-user and restricted-scope requirements are described below.</p>
            <p class="hint" role="status" aria-live="polite" tabindex="-1" id="google-oauth-client-status">${esc(googleOAuthClient.detail || "")}</p>
          </div>
        </details>
        ${!googleCalendar.configured ? '<p class="hint" role="status">Google sign-in is not enabled in this build. Hutch’s publisher must configure its Google registration before this connection can work.</p>' : ''}
        ${googleCalendar.configured && !googleCalendar.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting an account. On Linux, install <code>secret-tool</code> if needed. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
        <div class="google-calendar-connect">
          <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="google-calendar-label">Account label
            <input id="google-calendar-label" type="text" maxlength="80" autocomplete="off" placeholder="Personal or Work" aria-describedby="google-calendar-label-help">
          </label></details>
          <label class="background-consent-row calendar-create-consent">
            <input id="google-calendar-event-creation" type="checkbox">
            <span>Also request event-creation access<small>Google's account-wide scope can also change or delete events on calendars you own. Hutch requires approval and offers creation on one selected calendar.</small></span>
          </label>
          <button class="btn primary small" id="google-calendar-connect" type="button" ${!googleCalendar.configured || !googleCalendar.secret_store_available ? "disabled" : ""}>Connect Google Calendar</button>
          <p class="hint" id="google-calendar-label-help">This label stays on this Hutch. A write-enabled sign-in is a separate account record; previous read-only accounts remain unchanged. Sign-in starts here and finishes in your system browser at <code>127.0.0.1</code>.</p>
        </div>
        ${googleCalendarAccountsHtml || '<p class="hint">No Google Calendar accounts connected.</p>'}
        ${orphanCalendarGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanCalendarGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">${esc(grant.calendar_name)}</p></div><button class="btn ghost small" data-google-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
      </section>
      <section class="panel conn-card" id="connection-notion" aria-labelledby="notion-title">
        <div class="bot-head"><span class="bot-name" id="notion-title">Notion</span><span class="tag">experimental · read access</span></div>
        <p>${notion.accounts.length ? "Choose who can use each workspace. Access is revocable at any time." : "Sign in with your Notion account, then choose an assistant. No token or developer setup needed."}</p>
        <p class="hint">Hutch offers search and page reads only. Notion’s consent may allow broader access. Pages may reach your selected assistants’ model providers and stay in run history; edits and connected-source search are unavailable.</p>
        ${notionError ? `<p class="hint bad" role="alert">Could not load Notion: ${esc(notionError)}</p>` : !notion.secret_store_available ? '<p class="hint" role="status">Unlock the operating system’s secure credential store before connecting Notion.</p>' : !notion.accounts.length ? '<button class="btn primary" id="notion-connect" type="button">Connect Notion</button>' : ""}
        ${notion.accounts.map(account => `<article class="google-calendar-account"><div class="device-row"><div><strong>${esc(account.workspace_name || account.label)}</strong><details class="connection-reference"><summary>Connection details</summary><code>${esc(account.id)}</code></details></div><div class="card-actions"><button class="btn primary small" type="button" data-notion-access="${esc(account.id)}">Choose assistant access</button><button class="btn ghost small" type="button" data-notion-disconnect="${esc(account.id)}">Disconnect Notion</button></div></div>
          ${notionGrantRows(account.id)}
        </article>`).join("") || '<p class="hint">No Notion accounts connected.</p>'}
        ${notion.secret_store_available && notion.accounts.length ? '<button class="btn ghost" id="notion-connect" type="button">Connect another workspace</button>' : ""}
      </section>
      ${fileServices.map(googleFilePanel).join("")}
      <section class="panel conn-card outlook-calendar-card" id="connection-gmail" aria-labelledby="google-mail-title">
        <div class="bot-head"><span class="bot-name" id="google-mail-title">Gmail</span>
          <span class="tag">experimental</span><span class="tag">Local inference only</span></div>
        <p class="hint">Search a connected mailbox for up to 10 matches. Hutch returns only sender, subject, received date and a short preview, which becomes untrusted local run history. This search connection cannot send, edit, forward, delete or fetch attachments. Only built-in assistants with loopback Local model routes and no hosted fallbacks can receive search access; Hutch cannot verify what the operator's local model service does.</p>
        <p class="hint"><strong>Search permission:</strong> <code>gmail.readonly</code> is a restricted, account-wide scope. Each assistant grant is enforced by Hutch, but Google consent is broader and remains managed in your Google Account. Public distribution requires Google's restricted-scope verification; server-side access can also require a security assessment. This private-preview search integration is not approved for public release.</p>
        <p class="hint"><a href="https://developers.google.com/workspace/gmail/api/auth/scopes" target="_blank" rel="noopener noreferrer">Review Google's Gmail scope requirements</a> · <a href="https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification" target="_blank" rel="noopener noreferrer">Review restricted-scope verification</a>.</p>
        <details class="outlook-calendar-details summary-row-sm" id="google-mail-access" ${googleMailAccessOpen ? "open" : ""}>
          <summary><span class="summary-row-copy"><strong>Manage Gmail access</strong></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          ${!googleMail.configured ? '<p class="hint" role="status">Google sign-in is not enabled in this build. Hutch’s publisher must configure its registration. <button class="inline-link" type="button" data-google-oauth-setup-link>Developer settings</button> Gmail asks for restricted <code>gmail.readonly</code> consent, separately from Calendar.</p>' : ''}
          ${googleMail.configured && !googleMail.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting. On Linux, install <code>secret-tool</code> if needed. Refresh tokens stay outside SQLite and browser storage.</p>' : ''}
          ${googleMail.configured && googleMail.secret_store_available ? `<div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="google-mail-label">Account label
              <input id="google-mail-label" type="text" maxlength="80" autocomplete="off" placeholder="Personal or Work" aria-describedby="google-mail-label-help">
            </label></details>
            <button class="btn primary small" id="google-mail-connect" type="button">Connect Gmail</button>
            <p class="hint" id="google-mail-label-help">Sign in from this Hutch host at <code>127.0.0.1</code>. A project in Testing is limited to 100 listed users, and test-user refresh tokens expire after seven days. Google's restricted-scope review rules still apply.</p>
          </div>` : ''}
          ${googleMailAccountsHtml || '<p class="hint">No Gmail accounts connected.</p>'}
          ${orphanGoogleMailGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A Bot grant refers to a disconnected Gmail account. Revoke it before reconnecting.</p>${orphanGoogleMailGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Gmail search access</p></div><button class="btn ghost small" data-google-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ''}
          </div>
        </details>
        <details class="outlook-calendar-details outlook-mail-send-details summary-row-sm" id="google-mail-send-access" ${googleMailSendAccessOpen ? "open" : ""}>
          <summary><span class="summary-row-copy"><strong>Set up send-only access</strong><small>A separate Google connection for <code>gmail.send</code> only</small></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          <p class="hint">This is a separate Google connection with <code>gmail.send</code> only. It cannot read or search your mailbox. An assistant can prepare one plain-text message; you approve the exact sender, recipients, subject and message each time, even in automatic mode. No attachments, CC, BCC, replies or forwards.</p>
          <p class="hint"><strong>Google permission:</strong> <code>gmail.send</code> is sensitive and requires additional OAuth app verification for public distribution. It is separate from restricted <code>gmail.readonly</code>. Hutch is a private preview; no live Google account or consent flow has been verified.</p>
          ${!googleMailSend.configured ? '<p class="hint" role="status">Google sign-in is not enabled in this build. Hutch’s publisher must configure its registration before connecting a send-only account.</p>' : ''}
          ${googleMailSend.configured && !googleMailSend.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting. On Linux, install <code>secret-tool</code> if needed. Refresh tokens stay outside SQLite and browser storage.</p>' : ''}
          ${googleMailSend.configured && googleMailSend.secret_store_available ? `<div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="google-mail-send-label">Account label
              <input id="google-mail-send-label" type="text" maxlength="80" autocomplete="off" placeholder="Work sender" aria-describedby="google-mail-send-help">
            </label></details>
            <label class="field" for="google-mail-send-from">Send-from address
              <input id="google-mail-send-from" type="email" maxlength="254" autocomplete="email" placeholder="you@example.com" aria-describedby="google-mail-send-help">
            </label>
            <button class="btn primary small" id="google-mail-send-connect" type="button">Connect send-only Gmail</button>
            <p class="hint" id="google-mail-send-help">Google checks that the address is allowed for this account. The address is stored only in this Hutch account record. Sign-in stays on this computer at <code>127.0.0.1</code>.</p>
          </div>` : ''}
          ${googleMailSendAccountsHtml || '<p class="hint">No send-only Gmail accounts connected.</p>'}
          ${orphanGoogleMailSendGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved send grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanGoogleMailSendGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Gmail send access</p></div><button class="btn ghost small" data-google-mail-send-ungrant="${esc(grant.bot_id)}">Revoke send access</button></div>`).join("")}</div>` : ''}
          </div>
        </details>
      </section>
      <section class="panel conn-card outlook-calendar-card" id="connection-outlook-calendar" aria-labelledby="outlook-calendar-title">
        <div class="bot-head"><span class="bot-name" id="outlook-calendar-title">Outlook Calendar</span>
          <span class="tag">experimental</span><span class="tag">read, with optional event creation</span></div>
        <p class="hint">Connect a Microsoft account to let an assistant check one selected calendar. The default sign-in uses delegated <code>Calendars.ReadBasic</code>; event bodies, attachments and extensions are not available. Event creation is a separate optional sign-in and requires your approval each time.</p>
        <p class="hint"><strong>Permission boundary:</strong> Microsoft consent applies to the signed-in account. Hutch enforces each Bot's selected-calendar grant locally, and calendar text stays untrusted. Disconnect clears Hutch's refresh credential and Bot grants; Microsoft consent must be revoked separately in your account or organisation settings.</p>
        <details class="outlook-calendar-details summary-row-sm" id="outlook-calendar-access">
          <summary><span class="summary-row-copy"><strong>Manage Outlook Calendar access</strong></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          ${!outlookCalendar.configured ? '<p class="hint" role="status">Microsoft sign-in is not enabled in this build. Hutch’s publisher must supply its app registration.</p>' : ''}
          ${outlookCalendar.configured && !outlookCalendar.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting an account. On Linux, install <code>secret-tool</code> if needed. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
          <div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="outlook-calendar-label">Account label
              <input id="outlook-calendar-label" type="text" maxlength="80" autocomplete="off" placeholder="Work or Personal" aria-describedby="outlook-calendar-label-help">
            </label></details>
            <button class="microsoft-signin-button" id="outlook-calendar-connect" type="button" aria-label="Sign in with Microsoft" ${!outlookCalendar.configured || !outlookCalendar.secret_store_available ? "disabled" : ""}><img src="/static/brands/ms-symbollockup_signin_dark.svg" width="215" height="41" alt=""></button>
            <p class="hint" id="outlook-calendar-label-help">Choose your signed-in Microsoft account in the browser and approve calendar access. Then choose one calendar and which assistant can use it.</p>
          </div>
          ${outlookCalendarAccountsHtml || '<p class="hint">No Outlook Calendar accounts connected.</p>'}
          ${orphanOutlookGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">${esc(grant.calendar_name)}</p></div><button class="btn ghost small" data-outlook-calendar-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
          </div>
        </details>
        <details class="outlook-calendar-details outlook-mail-send-details summary-row-sm" id="outlook-calendar-write-access" ${outlookCalendarWriteAccessOpen ? "open" : ""}>
          <summary><span class="summary-row-copy"><strong>Add event creation (optional)</strong><small>A separate Microsoft sign-in for one selected calendar</small></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          <p class="hint">This needs a separate Microsoft sign-in for <code>Calendars.ReadWrite</code>. Microsoft grants that permission to create, read, change and delete events across the signed-in user's calendars. Hutch keeps this token separate and only gives an assistant the ability to create guest-free events on the one calendar you select. Hutch does not expose event editing or deletion.</p>
          <div class="outlook-mail-send-safety"><strong>Every event needs your exact approval.</strong><p class="hint">The approval shows the title, time, description, location, account and calendar. Hutch creates once, checks the event details with Microsoft, and never retries an uncertain result. Disconnect removes Hutch's credential; revoke Microsoft's broader account permission in your Microsoft account or organisation settings.</p></div>
          ${!outlookCalendarWrite.configured ? '<p class="hint" role="status">Microsoft sign-in is not enabled in this build. Hutch’s publisher must supply its app registration.</p>' : ''}
          ${outlookCalendarWrite.configured && !outlookCalendarWrite.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting an account. On Linux, install <code>secret-tool</code> if needed. Refresh tokens stay outside SQLite and browser storage.</p>' : ''}
          <div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="outlook-calendar-write-label">Event-creation account label
              <input id="outlook-calendar-write-label" type="text" maxlength="80" autocomplete="off" placeholder="Work calendar" aria-describedby="outlook-calendar-write-help">
            </label></details>
            <button class="microsoft-signin-button" id="outlook-calendar-write-connect" type="button" aria-label="Sign in with Microsoft for event creation" ${!outlookCalendarWrite.configured || !outlookCalendarWrite.secret_store_available ? "disabled" : ""}><img src="/static/brands/ms-symbollockup_signin_dark.svg" width="215" height="41" alt=""></button>
            <p class="hint" id="outlook-calendar-write-help">Sign in separately for event creation. Hutch shows each exact event for approval before creating it.</p>
          </div>
          ${outlookCalendarWriteAccountsHtml || '<p class="hint">No Outlook event-creation accounts connected.</p>'}
          ${orphanOutlookCalendarWriteGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved event-creation grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookCalendarWriteGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Can create approved events on ${esc(grant.calendar_name)}</p></div><button class="btn ghost small" data-outlook-calendar-write-ungrant="${esc(grant.bot_id)}">Revoke event access</button></div>`).join("")}</div>` : ""}
          </div>
        </details>
      </section>
      <section class="panel conn-card outlook-calendar-card outlook-mail-card" id="connection-outlook-mail" aria-labelledby="outlook-mail-title">
        <div class="bot-head"><span class="bot-name" id="outlook-mail-title">Outlook Mail</span>
          <span class="tag">experimental</span><span class="tag">separate read and send access</span></div>
        <p class="hint">Search across a connected mailbox, including Deleted Items and Clutter. Hutch returns sender, subject, received time and a short, untrusted preview for up to 10 matches. Grant one mailbox to a Bot from here.</p>
        <p class="hint"><strong>Permission boundary:</strong> Microsoft's delegated <code>Mail.Read</code> consent applies to the signed-in account; Hutch enables search only for a Bot you grant. Reading and sending use separate account sign-ins and separate Bot grants. Mail previews are sent to that Bot's selected model and kept in its run history. Local disconnect clears Hutch's credential and grants; provider consent must be revoked separately.</p>
        ${!outlookMail.configured ? '<p class="hint" role="status">Microsoft sign-in is not enabled in this build. Hutch’s publisher must supply its app registration.</p>' : ''}
        ${outlookMail.configured && !outlookMail.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting an account. On Linux, install <code>secret-tool</code> if needed. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
        <details class="outlook-calendar-details summary-row-sm" id="outlook-mail-access">
          <summary><span class="summary-row-copy"><strong>Manage Outlook Mail access</strong></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          <div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="outlook-mail-label">Account label
              <input id="outlook-mail-label" type="text" maxlength="80" autocomplete="off" placeholder="Work or Personal" aria-describedby="outlook-mail-label-help">
            </label></details>
            <button class="microsoft-signin-button" id="outlook-mail-connect" type="button" aria-label="Sign in with Microsoft" ${!outlookMail.configured || !outlookMail.secret_store_available ? "disabled" : ""}><img src="/static/brands/ms-symbollockup_signin_dark.svg" width="215" height="41" alt=""></button>
            <p class="hint" id="outlook-mail-label-help">Choose your Microsoft account in the browser and approve email access. Mail and calendar access are separate choices.</p>
          </div>
          ${outlookMailAccountsHtml || '<p class="hint">No Outlook Mail accounts connected.</p>'}
          ${orphanOutlookMailGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved Bot grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookMailGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Outlook Mail access</p></div><button class="btn ghost small" data-outlook-mail-ungrant="${esc(grant.bot_id)}">Revoke Bot access</button></div>`).join("")}</div>` : ""}
          </div>
        </details>
        <details class="outlook-calendar-details outlook-mail-send-details summary-row-sm" id="outlook-mail-send-access" ${outlookMailSendAccessOpen ? "open" : ""}>
          <summary><span class="summary-row-copy"><strong>Set up optional email sending</strong><small>A separate Microsoft sign-in for <code>Mail.Send</code></small></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
          <div class="outlook-calendar-details-body">
          <p class="hint">This uses a separate Microsoft sign-in for <code>Mail.Send</code>. Reading access does not include sending, and sending access does not include reading. Grant it only to a Bot that should prepare outgoing mail.</p>
          <div class="outlook-mail-send-safety"><strong>Every send requires your exact approval.</strong><p class="hint">Hutch can prepare one new plain-text email to at most five recipients. No replies, forwards, attachments, CC or BCC. Hutch sends once and does not retry an uncertain result; Microsoft acceptance does not confirm delivery.</p></div>
          <div class="google-calendar-connect outlook-calendar-connect">
            <details class="connection-nickname"><summary>Nickname (optional)</summary><label class="field" for="outlook-mail-send-label">Sending account label
              <input id="outlook-mail-send-label" type="text" maxlength="80" autocomplete="off" placeholder="Work sender" aria-describedby="outlook-mail-send-label-help">
            </label></details>
            <button class="microsoft-signin-button" id="outlook-mail-send-connect" type="button" aria-label="Sign in with Microsoft" ${!outlookMailSend.configured || !outlookMailSend.secret_store_available ? "disabled" : ""}>
              <img src="/static/brands/ms-symbollockup_signin_dark.svg" width="215" height="41" alt="">
            </button>
            <p class="hint" id="outlook-mail-send-label-help">A new sign-in is required for delegated <code>Mail.Send</code>; Hutch never upgrades a read-only account. Register <code>http://localhost/api/v1/connections/outlook-mail-send/callback</code> as a desktop redirect.</p>
          </div>
          ${!outlookMailSend.configured ? '<p class="hint" role="status">Microsoft sign-in is not enabled in this build. Hutch’s publisher must supply its app registration.</p>' : ''}
          ${outlookMailSend.configured && !outlookMailSend.secret_store_available ? '<p class="hint" role="alert">Your operating system’s secure credential store is unavailable. Unlock it before connecting. On Linux, install <code>secret-tool</code> if needed. Hutch never stores refresh tokens in SQLite or browser storage.</p>' : ''}
          ${outlookMailSendAccountsHtml || '<p class="hint">No Outlook Mail sending accounts connected.</p>'}
          ${orphanOutlookMailSendGrants.length ? `<div class="google-calendar-orphan-grants"><p class="hint">A saved send grant refers to a disconnected account. Revoke it before reconnecting.</p>${orphanOutlookMailSendGrants.map(grant => `<div class="device-row"><div><strong>${esc(grantedBotLabel(grant))}</strong><p class="hint">Outlook Mail send access</p></div><button class="btn ghost small" data-outlook-mail-send-ungrant="${esc(grant.bot_id)}">Revoke send access</button></div>`).join("")}</div>` : ""}
          </div>
        </details>
      </section>
      <details class="device-manager summary-row-sm" id="connection-phone-devices">
        <summary><span class="summary-row-copy"><strong>Paired devices</strong><small>${devices.length} paired</small></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
        <p class="hint">A paired browser can access this Hutch host while it is online. Use <strong>Pair a phone</strong> in Your devices above to create a one-time code, then open the displayed private HTTPS address on the phone. For another device, Hutch must use <code>--allow-remote</code> with trusted TLS certificates; keep it on a private network.</p>
        ${devicesError ? `<p class="hint bad" role="alert">Could not load paired devices: ${esc(devicesError)}</p>` : devices.length ? `
          <div class="device-list" aria-label="Active paired devices">${devices.map(device => `
            <div class="device-row" data-device="${esc(device.id)}">
              <div><strong>${esc(device.label)}</strong> ${device.current ? '<span class="tag ok">this device</span>' : ''}
                <p class="hint">Last active ${esc(new Date(device.last_used_at).toLocaleString())} · expires ${esc(new Date(device.expires_at).toLocaleDateString())}</p></div>
              <button class="btn danger small" type="button" data-device-revoke="${esc(device.id)}">Revoke</button>
            </div>`).join("")}</div>` : `<p class="hint">No active paired devices.</p>`}
      </details>
      <div class="custom-service-heading">
        <div><h3>Connected model services</h3><p class="hint">Manage model accounts, allowances and advanced endpoints.</p></div>
        <button class="btn ghost small" id="btn-add-conn" type="button">${icon("plus")} Connect a provider</button>
      </div>
      ${conns.length ? conns.map(c => `
        <div class="panel conn-card" data-conn="${esc(c.name)}">
          <div class="bot-head conn-provider-heading">
            ${providerLogoForTemplate(c.template) || `<span class="service-mark service-mark-hosted" aria-hidden="true">${icon("cloud")}</span>`}
            <span class="bot-name">${esc(c.title || c.name)}</span>
            <span class="tag mono">${esc(c.protocol)}</span>
            <span class="tag ${c.billing === "per_token" ? "info" : ""}">${esc(c.billing === "per_token" ? "per token" : "flat rate")}</span>
            <span class="chip ${c.has_key ? "ok" : "danger"} chip-end">${c.auth_type === "chatgpt-siws" ? (c.has_key ? "signed in" : "sign-in needed") : (c.has_key ? "key set" : "no key")}</span>
            <span class="chip ${c.ack === "ok" || c.ack === "not_needed" ? "ok" : "warn"}">${esc(c.ack === "required" ? "terms need acknowledging" : c.ack === "stale" ? "terms changed" : c.ack === "ok" ? "terms accepted" : "no terms")}</span>
          </div>
          <div class="bot-facts">
            <div>endpoint <b class="mono">${esc(c.base_url)}</b></div>
            <div>key source <b>${esc(c.key_source)}</b></div>
            <div>allowance <b>${c.quota_tokens ? `${fmtTokens(c.quota_tokens)} ${windows[c.quota_window] || c.quota_window}` : "none declared"}</b></div>
            <div>used in window <b>${c.quota_tokens ? `${fmtTokens(c.used)} (${Math.round((c.used / c.quota_tokens) * 100)}%)` : "—"}</b></div>
          </div>
          ${c.quota_tokens ? `<div class="meter-track meter-full"><div class="meter-fill" style="width:${Math.min(100, c.used / c.quota_tokens * 100)}%"></div></div>` : ""}
          ${c.terms_notice ? `<p class="hint">${esc(c.terms_notice)}</p>` : ""}
          ${c.auth_type === "chatgpt-siws" ? '<p class="hint">The provider does not accept a per-response output-token ceiling here. Hutch records estimates and provider-reported usage; it cannot guarantee a hard cap.</p>' : ""}
          ${c.get_key_url && c.template === "opencode-go" ? `<p class="hint"><a href="${esc(c.get_key_url)}" target="_blank" rel="noopener noreferrer">Get an OpenCode Go API key</a>. Sign in to Go, copy its provider-issued key, and paste it here. To import one existing account instead, choose Use existing OpenCode login when adding a provider. Browser sessions stay separate.</p>` : ""}
          <div class="card-actions">
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
      ${data.errors?.length ? `<p class="hint conn-errors">${esc(data.errors.join(" "))}</p>` : ""}
      <section class="panel conn-card model-capability-card" aria-labelledby="model-capabilities-title">
        <div class="bot-head"><span class="bot-name" id="model-capabilities-title">Model tool-call observations</span>
          <span class="tag">observed evidence</span></div>
        <p class="hint">Hutch records a tool-call observation only after a normal, owned Bot run receives a declared tool call with valid arguments and its usage reservation is settled or retained for reconciliation. Each record applies to that exact connection, account, model and route revision. It is evidence from one past response, not a guarantee about the next run.</p>
        <div id="model-capability-results"><p class="hint" role="status">Loading model tool-call observations…</p></div>
      </section>
        </div>
      </details>
    </div></div>`;
  $("#connection-management").open = connectionManagerOpen;
  $(".device-manager").open = devicesOpen;
  $("#outlook-calendar-access").open = outlookCalendarAccessOpen;
  $("#outlook-mail-access").open = outlookMailAccessOpen;
  $("#outlook-mail-send-access").open = outlookMailSendAccessOpen;
  $("#google-mail-access").open = googleMailAccessOpen;
  window.hutchConnections?.mount($(".connections-workspace"));
  $$("[data-connection-open]").forEach(button => button.addEventListener("click", () => {
    const targetKey = button.dataset.connectionOpen;
    if (targetKey === "kdeconnect") {
      void openKDEConnectSetup(button, bots);
      return;
    }
    if (targetKey === "phone" && devices.length) {
      location.hash = "#/connections?app=phone";
      return;
    }
    if (targetKey === "phone" || targetKey === "phone-pair") {
      openModal({ title: "Use Hutch on your phone", returnFocus: button,
        confirmText: phoneSetup.ready ? "Create pairing code" : "Close", showCancel: phoneSetup.ready,
        bodyHtml: `<p>${esc(phoneSetup.detail)}</p><p>Pairing grants monitoring and review. Starting new work is a separate choice, and each assistant must also allow remote starts.</p>${phoneSetup.ready ? '<label class="phone-pair-start"><input id="phone-pair-start" type="checkbox"><span>Also allow requests to start work</span></label>' : '<p>This development build needs a private HTTPS host connection before a phone can reach it. It stays local until that is configured.</p>'}<p>Paired browsers cannot administer integrations or pair another device. Use Manage devices in Hutch on your phone’s connection page to revoke a paired browser.</p><div id="phone-pair-result" role="status" aria-live="polite"></div>`,
        onConfirm: async () => {
          if (!phoneSetup.ready) return true;
          const confirm = $("#modal-confirm");
          if (confirm.disabled) return false;
          confirm.disabled = true;
          try {
            const result = await api("/v1/pairing/codes", { method: "POST", body: { allow_start: !!$("#phone-pair-start")?.checked } });
            // The code is intentionally shown once in the live dialog only; never
            // put it in a URL, localStorage, logs, or the clipboard automatically.
            const panel = $("#phone-pair-result");
            if (panel) panel.innerHTML = `<p>Open <a href="${esc(result.pair_url)}" target="_blank" rel="noopener noreferrer">${esc(result.pair_url)}</a> on your phone and enter:</p><p><strong>${esc(result.code)}</strong></p><p>This code expires in ${Number(result.expires_in_seconds)} seconds and works once. Then enroll your phone’s passkey.</p>`;
            confirm.textContent = "Code created";
          } catch (error) {
            const panel = $("#phone-pair-result");
            if (panel) panel.textContent = error.message;
            if (confirm.isConnected) confirm.disabled = false;
          }
          return false;
        } });
      return;
    }
    if (["google-calendar", "gmail"].includes(targetKey)) {
      const service = targetKey === "gmail" ? googleMail : googleCalendar;
      if (!service.accounts.length && service.configured && service.secret_store_available) {
        if (targetKey === "google-calendar") $("#google-calendar-event-creation").checked = false;
        $(targetKey === "gmail" ? "#google-mail-connect" : "#google-calendar-connect")?.click();
        return;
      }
      if (!service.accounts.length && !service.configured) {
        location.hash = `#/connections?app=${encodeURIComponent(targetKey)}`;
        return;
      }
    }
    if (targetKey === "outlook-calendar" && !outlookCalendar.accounts.length && !outlookMail.accounts.length && !outlookMailSend.accounts.length
        && outlookCalendar.configured && outlookCalendar.secret_store_available) {
      openModal({ title: "Connect Microsoft", returnFocus: button, confirmText: "Continue with Microsoft",
        bodyHtml: '<fieldset class="form-grid"><legend>What should Hutch connect?</legend><label><input type="radio" name="microsoft-purpose" value="outlook-calendar-connect" checked> Read a calendar</label><label><input type="radio" name="microsoft-purpose" value="outlook-mail-connect"> Search email</label></fieldset><p>Choose your account in your browser, then approve access. You choose which assistants can use it after connecting. Sending and event creation remain separate choices.</p>',
        onConfirm: () => {
          const id = $('#modal-root input[name="microsoft-purpose"]:checked')?.value;
          if (!id || !["outlook-calendar-connect", "outlook-mail-connect"].includes(id)) return false;
          document.getElementById(id)?.click();
          return true;
        } });
      return;
    }
    if (targetKey === "models") {
      location.hash = "#/connections?app=models";
      return;
    }
    location.hash = `#/connections?app=${encodeURIComponent(targetKey)}`;
  }));

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
    if (!location.hash.startsWith("#/connections?app=google-calendar")) {
      location.hash = "#/connections?app=google-calendar&developer=1";
      return;
    }
    const setup = $("#google-oauth-setup");
    if (!setup) return;
    setup.open = true;
    setup.scrollIntoView({ behavior: "auto", block: "center" });
    $("#google-oauth-client-id")?.focus({ preventScroll: true });
  });

  $("#notion-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) { toast("Allow Hutch to open a browser tab, then try again.", true); return; }
    authWindow.opener = null;
    button.disabled = true;
    try {
      const result = await api("/v1/connections/notion/sign-in", { method: "POST", body: {} });
      const url = new URL(result.authorization_url);
      if (url.origin !== "https://mcp.notion.com" || url.pathname !== "/authorize" || url.username || url.password || url.hash || !url.search) throw new Error("Unexpected Notion sign-in destination.");
      authWindow.location.replace(url.href);
      toast("Finish Notion sign-in in your browser, then reload Apps & AI to choose assistant access.");
    } catch (error) { authWindow.close(); toast(error.message, true); }
    finally { button.disabled = false; }
  });
  $$("[data-notion-access]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const account = button.dataset.notionAccess;
      const discovery = await api(`/v1/connections/notion/accounts/${encodeURIComponent(account)}/discover`, { method: "POST", body: {} });
      const eligible = bots.filter(bot => bot.inference_mode !== "offline" && ["builtin", "opencode"].includes(bot.runtime || "builtin"));
      const names = Object.keys(discovery.tools || {}).filter(name => ["notion-search", "notion-fetch"].includes(name));
      if (!names.length) throw new Error("Notion returned no compatible read tools. No assistant access was added.");
      if (!eligible.length) throw new Error("Create an assistant with online integration access first. Strict Offline assistants cannot use Notion.");
      openModal({ title: "Notion assistant access", returnFocus: button, confirmText: "Grant read access",
        bodyHtml: `${discovery.grants_invalidated ? '<p role="status">Notion’s tool definitions changed. Previous assistant grants were removed; review them again.</p>' : ""}<p>This grant lets the selected assistant search or read pages accessible through this Notion account. Pages may go to that assistant’s configured model providers and remain in run history. It cannot edit Notion through this connector.</p><label class="field">Assistant<select id="notion-grant-bot">${eligible.map(bot => `<option value="${esc(bot.id)}">${esc(bot.display_name || bot.name)}</option>`).join("")}</select></label><fieldset><legend>Read tools</legend>${names.map(name => `<label class="phone-pair-start"><input type="checkbox" data-notion-tool="${esc(name)}" checked><span>${name === "notion-search" ? "Search workspace pages" : "Read a page"}</span></label>`).join("")}</fieldset><details class="notion-tool-definitions"><summary>Tool definitions</summary><pre>${esc(JSON.stringify(discovery.tools, null, 2))}</pre></details><p id="notion-grant-status" class="hint" role="status"></p>`,
        onConfirm: async () => {
          const tools = $$("#modal-root [data-notion-tool]:checked").map(input => input.dataset.notionTool);
          const confirm = $("#modal-confirm");
          if (confirm.disabled) return false;
          confirm.disabled = true;
          try {
            await api(`/v1/connections/notion/accounts/${encodeURIComponent(account)}/grants`, { method: "POST", body: { bot: $("#notion-grant-bot").value, tools, revision: discovery.revision } });
            toast("Notion read access granted for new work.");
            await renderConnections();
            return true;
          } catch (error) {
            const status = $("#notion-grant-status");
            if (status) status.textContent = error.message;
            if (confirm.isConnected) confirm.disabled = false;
            return false;
          }
        } });
    } catch (error) { toast(error.message, true); }
    finally { if (button.isConnected) button.disabled = false; }
  }));
  $$("[data-notion-revoke]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/v1/connections/notion/accounts/${encodeURIComponent(button.dataset.notionRevoke)}/grants/${encodeURIComponent(button.dataset.notionBot)}`, { method: "DELETE" });
      await renderConnections();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }));
  $$("[data-notion-disconnect]").forEach(button => button.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Disconnect Notion", body: "Remove local credentials and all assistant grants for this Notion account, then request provider revocation. Your Notion pages stay unchanged.", confirmText: "Disconnect", danger: true }))) return;
    button.disabled = true;
    try {
      const result = await api(`/v1/connections/notion/accounts/${encodeURIComponent(button.dataset.notionDisconnect)}/disconnect`, { method: "POST", body: {} });
      toast(result.detail);
      await renderConnections();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }));

  $$("[data-google-file-connect]").forEach(button => button.addEventListener("click", async event => {
    const button = event.currentTarget;
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) { toast("Allow Hutch to open a browser tab, then try again.", true); return; }
    authWindow.opener = null;
    button.disabled = true;
    try {
      const result = await api("/v1/connections/google-workspace/sign-in", { method: "POST", body: { service: button.dataset.googleFileConnect, label: fileServiceName(button.dataset.googleFileConnect) } });
      const url = new URL(result.authorization_url);
      if (url.origin !== "https://accounts.google.com" || url.pathname !== "/o/oauth2/v2/auth" || url.username || url.password || url.hash || !url.search) throw new Error("Unexpected Google sign-in destination.");
      authWindow.location.replace(url.href);
      toast("Approve per-file access in your browser, then reload this connection.");
    } catch (error) { authWindow.close(); toast(error.message, true); }
    finally { button.disabled = false; }
  }));
  $$("[data-google-file-service]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/v1/connections/google-workspace/accounts/${encodeURIComponent(button.dataset.googleFileAccount)}/services/${encodeURIComponent(button.dataset.googleFileService)}`, { method: "PUT", body: { contract_version: 1, enabled: button.dataset.googleFileEnabled === "true", expected_revision: Number(button.dataset.googleFileRevision) } });
      toast(`${fileServiceName(button.dataset.googleFileService)} ${button.dataset.googleFileEnabled === "true" ? "enabled" : "disabled"}.`);
      await renderConnections();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }));
  $$("[data-workspace-disconnect]").forEach(button => button.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Disconnect shared Google account", body: "Remove this account from Drive, Docs and Sheets in Hutch and request Google revocation. Pending plans cannot use it afterward. Existing cloud files remain. Google may also revoke other Hutch Google sign-ins. To keep other services connected, cancel and disable only this service instead.", confirmText: "Disconnect", danger: true }))) return;
    button.disabled = true;
    try {
      const result = await api(`/v1/connections/google-workspace/accounts/${encodeURIComponent(button.dataset.workspaceDisconnect)}/disconnect`, { method: "POST", body: {} });
      toast(result.detail || "Workspace disconnected.");
      await renderConnections();
    } catch (error) { button.disabled = false; toast(error.message, true); }
  }));

  $("#google-calendar-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#google-calendar-label")?.value.trim() || "Google Calendar";
    const allowEventCreation = !!$("#google-calendar-event-creation")?.checked;
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
      const result = await api("/v1/connections/google-calendar/sign-in", {
        method: "POST", body: { label, allow_event_creation: allowEventCreation } });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Google sign-in destination."); }
      if (authUrl.origin !== "https://accounts.google.com" || authUrl.pathname !== "/o/oauth2/v2/auth" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Google sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      button.textContent = "Connect Google Calendar";
      toast(allowEventCreation
        ? "Finish Google sign-in for event creation in the new browser tab. This creates a separate account record; reload Connections after returning."
        : "Finish Google read-only sign-in in the new browser tab, then reload Connections here.");
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
        const account = (googleCalendar.accounts || []).find(row => row.id === button.dataset.googleCalendarLoadCalendars);
        calendarSelect.innerHTML = `<option value="">Choose a calendar…</option>${rows.map(calendar => {
          const canCreate = !!account?.can_create_events && calendar.access_role === "owner";
          const capability = account?.can_create_events ? (canCreate ? " · event creation available" : " · read only here") : "";
          return `<option value="${esc(calendar.id)}" data-calendar-name="${esc(calendar.name)}" data-calendar-owner="${canCreate ? "true" : "false"}">${esc(calendar.name)}${calendar.primary ? " · primary" : ""}${capability}</option>`;
        }).join("")}`;
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
      const button = $("[data-google-calendar-grant]", form);
      const createAccess = $("[data-google-calendar-create-access]", form);
      const canCreate = select.selectedOptions?.[0]?.dataset?.calendarOwner === "true";
      if (createAccess) {
        createAccess.disabled = !canCreate;
        if (!canCreate && createAccess.checked) {
          createAccess.checked = false;
          $("[data-google-calendar-status]", form).textContent = "Google's event-creation scope covers calendars you own. This selection will stay read-only.";
        }
      }
      button.disabled = !select.value;
      button.textContent = $("[data-google-calendar-create-access]", form)?.checked
        ? "Grant read and create access" : "Grant read access";
    });
  });
  $$('[data-google-calendar-create-access]').forEach(input => {
    input.addEventListener("change", () => {
      const form = input.closest("[data-google-calendar-grant-form]");
      const button = $("[data-google-calendar-grant]", form);
      button.textContent = input.checked ? "Grant read and create access" : "Grant read access";
    });
  });
  $$('[data-google-calendar-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-google-calendar-grant-form]");
      const bot = $("[data-google-calendar-bot]", form).value;
      const calendarSelect = $("[data-google-calendar-calendar]", form);
      const calendar = calendarSelect.value;
      const calendarName = calendarSelect.selectedOptions?.[0]?.dataset?.calendarName || calendar;
      const allowEventCreation = !!$("[data-google-calendar-create-access]", form)?.checked;
      const status = $("[data-google-calendar-status]", form);
      const existing = (googleCalendar.grants || []).find(grant => grant.bot_id === bot);
      const grantChange = allowEventCreation
        ? `This enables that Bot to create guest-free events on one calendar. Each event still needs exact approval; event edits, deletion and invitations remain unavailable. Google's account-level scope can also change or delete events on every calendar you own.`
        : "The Bot will have read-only access to the selected calendar.";
      if (existing && !(await confirmDialog({ title: "Replace calendar access", body: `<b>${esc(grantedBotLabel(existing))}</b> already has access to <b>${esc(existing.calendar_name)}</b>. Replace it with access to <b>${esc(calendarName)}</b>? ${esc(grantChange)}`, confirmText: allowEventCreation ? "Review and replace" : "Replace grant" }))) return;
      const selectedBotName = bots.find(candidate => candidate.id === bot)?.display_name || bots.find(candidate => candidate.id === bot)?.name || "this Bot";
      if (!existing && allowEventCreation && !(await confirmDialog({ title: "Grant event creation", body: `<b>${esc(selectedBotName)}</b> can create events on <b>${esc(calendarName)}</b> after your approval of each exact event. Google’s account-level scope also permits changing and deleting events on calendars you own; Hutch itself offers creation only.`, confirmText: "Grant after review" }))) return;
      button.disabled = true;
      status.textContent = "Verifying the selected calendar with Google…";
      try {
        const result = await api("/v1/connections/google-calendar/grants", { method: "POST", body: {
          bot, account_id: button.dataset.googleCalendarGrant, calendar_id: calendar,
          allow_event_creation: allowEventCreation } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-google-calendar-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (googleCalendar.grants || []).find(row => row.bot_id === button.dataset.googleCalendarUngrant);
      if (!(await confirmDialog({ title: "Revoke Bot calendar access", body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from ${grant?.allow_event_creation ? "reading and creating events on" : "reading"} the granted Google Calendar?`, confirmText: "Revoke access" }))) return;
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
    const label = $("#google-mail-label")?.value.trim() || "Gmail";
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

  $("#google-mail-send-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#google-mail-send-label")?.value.trim() || "Gmail sending";
    const fromAddress = $("#google-mail-send-from")?.value.trim();
    if (!fromAddress || !$("#google-mail-send-from")?.reportValidity()) {
      toast("Enter the email address this account should send from.", true);
      $("#google-mail-send-from")?.focus();
      return;
    }
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Google sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const result = await api("/v1/connections/google-mail-send/sign-in", {
        method: "POST", body: { label, from_address: fromAddress },
      });
      let authUrl;
      try { authUrl = new URL(result.authorization_url); }
      catch { throw new Error("Hutch returned an invalid Google sign-in destination."); }
      if (authUrl.origin !== "https://accounts.google.com" || authUrl.pathname !== "/o/oauth2/v2/auth" ||
          authUrl.username || authUrl.password || authUrl.hash || !authUrl.search) {
        throw new Error("Hutch returned an unexpected Google sign-in destination.");
      }
      authWindow.location.replace(authUrl.href);
      toast("Review the separate Gmail send permission in Google, then return to Connections.");
    } catch (err) { authWindow.close(); toast(err.message, true); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); }
  });
  $$('[data-google-mail-send-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-google-mail-send-grant-form]");
      const bot = $("[data-google-mail-send-bot]", form).value;
      const status = $("[data-google-mail-send-status]", form);
      const existing = (googleMailSend.grants || []).find(grant => grant.bot_id === bot);
      if (existing && existing.account_id !== button.dataset.googleMailSendGrant && !(await confirmDialog({
        title: "Replace Gmail send access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has send access to another account. Replace that grant?`,
        confirmText: "Replace grant",
      }))) return;
      button.disabled = true;
      status.textContent = "Saving this assistant's send-only grant…";
      try {
        const result = await api("/v1/connections/google-mail-send/grants", { method: "POST", body: {
          bot, account_id: button.dataset.googleMailSendGrant,
        } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-google-mail-send-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const botRef = button.dataset.googleMailSendUngrant;
      const grant = (googleMailSend.grants || []).find(row => row.bot_id === botRef);
      if (!(await confirmDialog({ title: "Revoke Gmail sending access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from preparing approved emails from this account?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/google-mail-send/grants/${encodeURIComponent(botRef)}`, { method: "DELETE" });
        toast("Assistant Gmail sending access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-google-mail-send-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const accountId = button.dataset.googleMailSendDisconnect;
      const account = (googleMailSend.accounts || []).find(row => row.id === accountId);
      const grants = (googleMailSend.grants || []).filter(row => row.account_id === accountId);
      const botNames = grants.map(grantedBotLabel);
      const linkedBots = botNames.length ? `<p>This also revokes Gmail send access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect send-only Gmail",
        body: `Clear Hutch's send-only refresh credential for <b>${esc(account?.label || "this account")}</b> and request Google revocation?${linkedBots} This does not affect a separate Gmail search connection.`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/google-mail-send/accounts/${encodeURIComponent(accountId)}/disconnect`, {
          method: "POST", body: {},
        });
        toast(result.detail, result.provider_revocation !== "confirmed");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });

  $("#outlook-calendar-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-calendar-label")?.value.trim() || "Outlook Calendar";
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
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
      button.removeAttribute("aria-busy");
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

  $("#outlook-calendar-write-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-calendar-write-label")?.value.trim() || "Outlook event creation";
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const result = await api("/v1/connections/outlook-calendar-write/sign-in", { method: "POST", body: { label } });
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
      button.removeAttribute("aria-busy");
    }
  });
  $$('[data-outlook-calendar-write-load-calendars]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-calendar-write-grant-form]");
      const status = $("[data-outlook-calendar-write-status]", form);
      const calendarField = $("[data-outlook-calendar-write-calendar-field]", form);
      const calendarSelect = $("[data-outlook-calendar-write-calendar]", form);
      const grantButton = $("[data-outlook-calendar-write-grant]", form);
      button.disabled = true;
      button.textContent = "Loading…";
      status.textContent = "Loading calendars from Microsoft…";
      try {
        const result = await api(`/v1/connections/outlook-calendar-write/calendars?account_id=${encodeURIComponent(button.dataset.outlookCalendarWriteLoadCalendars)}`);
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
  $$('[data-outlook-calendar-write-grant-form] [data-outlook-calendar-write-calendar]').forEach(select => {
    select.addEventListener("change", () => {
      const form = select.closest("[data-outlook-calendar-write-grant-form]");
      $("[data-outlook-calendar-write-grant]", form).disabled = !select.value;
    });
  });
  $$('[data-outlook-calendar-write-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-calendar-write-grant-form]");
      const bot = $("[data-outlook-calendar-write-bot]", form).value;
      const calendar = $("[data-outlook-calendar-write-calendar]", form).value;
      const status = $("[data-outlook-calendar-write-status]", form);
      const existing = (outlookCalendarWrite.grants || []).find(grant => grant.bot_id === bot);
      if (existing && !(await confirmDialog({
        title: "Replace event-creation access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has permission to create events on <b>${esc(existing.calendar_name)}</b>. Replace it with the selected calendar?`,
        confirmText: "Replace access",
      }))) return;
      button.disabled = true;
      status.textContent = "Verifying the selected calendar with Microsoft…";
      try {
        const result = await api("/v1/connections/outlook-calendar-write/grants", { method: "POST", body: {
          bot, account_id: button.dataset.outlookCalendarWriteGrant, calendar_id: calendar } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-outlook-calendar-write-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const grant = (outlookCalendarWrite.grants || []).find(row => row.bot_id === button.dataset.outlookCalendarWriteUngrant);
      if (!(await confirmDialog({ title: "Revoke assistant event access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from creating Outlook Calendar events?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/outlook-calendar-write/grants/${encodeURIComponent(button.dataset.outlookCalendarWriteUngrant)}`, { method: "DELETE" });
        toast("Outlook Calendar event access revoked for this assistant.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-outlook-calendar-write-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const account = (outlookCalendarWrite.accounts || []).find(row => row.id === button.dataset.outlookCalendarWriteDisconnect);
      const botNames = (outlookCalendarWrite.grants || []).filter(row => row.account_id === account?.id).map(grantedBotLabel);
      const grants = botNames.length ? `<p>This also removes Hutch event access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Outlook event creation",
        body: `Clear Hutch's separate event-creation credential for <b>${esc(account?.label || "this account")}</b>? Microsoft consent remains account-wide until revoked in your Microsoft account or organisation settings.${grants}`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/outlook-calendar-write/accounts/${encodeURIComponent(button.dataset.outlookCalendarWriteDisconnect)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail);
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });

  $("#outlook-mail-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-mail-label")?.value.trim() || "Outlook Mail";
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) {
      toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true);
      return;
    }
    authWindow.opener = null;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
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
      button.removeAttribute("aria-busy");
    }
  });
  $("#outlook-mail-send-connect")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const label = $("#outlook-mail-send-label")?.value.trim() || "Outlook sending";
    const authWindow = window.open("about:blank", "_blank");
    if (!authWindow) { toast("Allow Hutch to open a browser tab, then try Microsoft sign-in again.", true); return; }
    authWindow.opener = null;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const result = await api("/v1/connections/outlook-mail-send/sign-in", { method: "POST", body: { label } });
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
    } catch (err) { authWindow.close(); toast(err.message, true); }
    finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  });
  $$('[data-outlook-mail-send-grant]').forEach(button => {
    button.addEventListener("click", async () => {
      const form = button.closest("[data-outlook-mail-send-grant-form]");
      const bot = $("[data-outlook-mail-send-bot]", form).value;
      const status = $("[data-outlook-mail-send-status]", form);
      const accountId = button.dataset.outlookMailSendGrant;
      const existing = (outlookMailSend.grants || []).find(grant => grant.bot_id === bot);
      if (existing && existing.account_id !== accountId && !(await confirmDialog({
        title: "Replace Outlook Mail send access",
        body: `<b>${esc(grantedBotLabel(existing))}</b> already has send access to another account. Replace that grant with this account?`,
        confirmText: "Replace grant",
      }))) return;
      button.disabled = true;
      status.textContent = "Saving this Bot's send grant…";
      try {
        const result = await api("/v1/connections/outlook-mail-send/grants", { method: "POST", body: { bot, account_id: accountId } });
        toast(result.detail);
        await renderConnections();
      } catch (err) { status.textContent = err.message; button.disabled = false; }
    });
  });
  $$('[data-outlook-mail-send-ungrant]').forEach(button => {
    button.addEventListener("click", async () => {
      const botRef = button.dataset.outlookMailSendUngrant;
      const grant = (outlookMailSend.grants || []).find(row => row.bot_id === botRef);
      if (!(await confirmDialog({ title: "Revoke Outlook Mail sending access",
        body: `Stop <b>${esc(grantedBotLabel(grant))}</b> from preparing outgoing email from this account?`,
        confirmText: "Revoke access" }))) return;
      button.disabled = true;
      try {
        await api(`/v1/connections/outlook-mail-send/grants/${encodeURIComponent(botRef)}`, { method: "DELETE" });
        toast("Bot Outlook Mail send access revoked.");
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
  });
  $$('[data-outlook-mail-send-disconnect]').forEach(button => {
    button.addEventListener("click", async () => {
      const accountId = button.dataset.outlookMailSendDisconnect;
      const account = (outlookMailSend.accounts || []).find(row => row.id === accountId);
      const grants = (outlookMailSend.grants || []).filter(row => row.account_id === accountId);
      const botNames = grants.map(grantedBotLabel);
      const linkedBots = botNames.length ? `<p>This also removes Hutch send access for ${botNames.map(esc).join(", ")}.</p>` : "";
      if (!(await confirmDialog({ title: "Disconnect Outlook Mail sending",
        body: `Clear Hutch's local refresh credential for <b>${esc(account?.label || "this account")}</b>? Microsoft consent is not revoked by Hutch; revoke it separately in your Microsoft account or organisation settings.${linkedBots}`,
        confirmText: "Disconnect", danger: true }))) return;
      button.disabled = true;
      try {
        const result = await api(`/v1/connections/outlook-mail-send/accounts/${encodeURIComponent(accountId)}/disconnect`, { method: "POST", body: {} });
        toast(result.detail);
        await renderConnections();
      } catch (err) { button.disabled = false; toast(err.message, true); }
    });
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
    const keyProviders = tpls.filter(template => (template.auth_type || "api_key") === "api_key");
    const quickProviders = keyProviders.filter(template => template.quick_setup && BRAND_MARK_FILES[template.provider_mark]);
    const advancedProviders = keyProviders.filter(template => !template.quick_setup);
    const quickChoice = template => `
      <button class="provider-choice" type="button" data-quick-provider="${esc(template.key)}" aria-pressed="false">
        ${providerLogo(template.provider_mark)}
        <span class="provider-choice-copy"><strong>${esc(template.title || template.key)}</strong>
          <small>${template.billing === "per_token" ? "API usage billing" : esc(template.billing || "Provider account")}</small></span>
      </button>`;
    openModal({
      title: "Connect an AI provider",
      wide: true,
      bodyHtml: `
        <form id="conn-form" class="provider-connect-form">
          <fieldset class="provider-choice-fieldset">
            <legend>Choose a provider</legend>
            <div class="provider-choice-grid" role="group" aria-label="Popular model providers">
              ${quickProviders.map(quickChoice).join("")}
            </div>
          </fieldset>
          <p class="provider-selection-detail hint" id="provider-selection-detail" role="status" aria-live="polite">Choose one provider. OpenAI API keys use API billing; ChatGPT sign-in is a separate option above.</p>
          <div class="provider-key-row">
            <label class="field" for="provider-api-key">API key
              <input id="provider-api-key" name="api_key" type="password" autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="Paste the key from your provider" aria-describedby="provider-key-help">
            </label>
            <button class="btn ghost small provider-key-reveal" id="provider-key-reveal" type="button" aria-pressed="false" aria-controls="provider-api-key">Show</button>
          </div>
          <div class="provider-key-help-row">
            <p class="hint" id="provider-key-help">Saved in a private file on this Hutch and sent only to the selected provider. It is never shown again or placed in browser storage.</p>
            <a id="provider-key-link" href="#" target="_blank" rel="noopener noreferrer" hidden>Get an API key</a>
          </div>
          <p class="provider-discovery-note">Hutch checks the provider's live model list without sending a chat. Names and prices can change; a listed model's actual chat and tool support is confirmed only by a normal run.</p>
          <details class="provider-advanced summary-row-sm" id="provider-advanced">
            <summary><span class="summary-row-copy"><strong>More providers and endpoint settings</strong></span><span class="summary-row-action"><span class="when-closed">Show</span><span class="when-open">Hide</span>${icon("down")}</span></summary>
            <div class="provider-advanced-body">
              <label class="field" for="provider-advanced-template">Provider or service
                <select id="provider-advanced-template" name="advanced_template">
                  <option value="">Choose an additional service…</option>
                  ${advancedProviders.map(t => `<option value="${esc(t.key)}">${esc(t.title || t.key)} · ${esc(t.billing.replaceAll("_", " "))}</option>`).join("")}
                </select>
              </label>
              <label class="field">Connection name (optional)<input type="text" name="name" maxlength="41" placeholder="Choose one automatically"></label>
              <label class="field">Custom endpoint (optional)<input type="url" name="base_url" placeholder="Leave blank for the provider's endpoint" autocomplete="url"></label>
              <p class="hint">Use endpoint overrides only when your service documents OpenAI Chat Completions or Anthropic Messages compatibility. Hutch will not silently switch providers if this one fails.</p>
            </div>
          </details>
        </form>`,
      confirmText: "Connect and find models",
      onConfirm: async () => {
        const form = $("#conn-form");
        const fd = new FormData(form);
        const selectedQuick = $$("[data-quick-provider]", form).find(button => button.getAttribute("aria-pressed") === "true")?.dataset.quickProvider || "";
        const selectedAdvanced = $("#provider-advanced-template", form).value;
        const template = selectedAdvanced || selectedQuick;
        const apiKey = String(fd.get("api_key") || "").trim();
        if (!template) { toast("Choose a provider to continue.", true); return false; }
        if (!apiKey) { toast("Paste the provider API key to connect.", true); return false; }
        try {
          const result = await api("/connections", { method: "POST", body: {
            template,
            name: selectedAdvanced ? String(fd.get("name") || "").trim() || null : null,
            base_url: selectedAdvanced ? String(fd.get("base_url") || "").trim() || null : null,
            api_key: apiKey || null,
            discover_models: true,
          } });
          const discovery = result.discovery;
          if (discovery?.verified && discovery.ok) {
            toast(`Connected. Found ${discovery.model_count} model IDs; choose one from the model menu.`);
          } else if (discovery) {
            toast(`Connection saved, but the model list could not be verified: ${discovery.detail}`, true);
          } else {
            toast("Connection saved. Add an API key or check the provider configuration to discover models.");
          }
          void renderConnections();
          return true;
        } catch (err) { toast(err.message, true); return false; }
      },
    });
    const updateProviderSummary = template => {
      const detail = $("#provider-selection-detail");
      const link = $("#provider-key-link");
      const keyLabel = $("label[for='provider-api-key']");
      if (!template) {
        detail.textContent = "Choose one provider. OpenAI API keys use API billing; ChatGPT sign-in is a separate option above.";
        link.hidden = true;
        link.removeAttribute("href");
        return;
      }
      const billing = template.billing === "per_token" ? "Usage is billed by the provider; Hutch allowances are estimates." :
        template.billing === "subscription" ? "This route uses the provider's subscription terms; Hutch still records usage." :
          "Review the provider's billing terms before connecting.";
      detail.textContent = `${template.setup_description || "Connect this provider with its own API key."} ${billing}`;
      const providerTitle = template.title || "Provider";
      const providerName = providerTitle.replace(/\s+API$/i, "");
      keyLabel.childNodes[0].textContent = `${providerName} API key `;
      if (template.get_key_url && /^https:\/\//i.test(template.get_key_url)) {
        link.href = template.get_key_url;
        link.textContent = `Get an API key from ${providerName}`;
        link.hidden = false;
      } else {
        link.hidden = true;
        link.removeAttribute("href");
      }
    };
    const quickButtons = $$('[data-quick-provider]');
    quickButtons.forEach(button => button.addEventListener("click", () => {
      quickButtons.forEach(item => {
        const selected = item === button;
        item.setAttribute("aria-pressed", String(selected));
      });
      $("#provider-advanced-template").value = "";
      const selected = quickProviders.find(template => template.key === button.dataset.quickProvider);
      updateProviderSummary(selected);
    }));
    // Provider choice is the first decision; keep initial keyboard focus there.
    (quickButtons[0] || $("#provider-advanced-template"))?.focus();
    $("#provider-advanced-template")?.addEventListener("change", event => {
      quickButtons.forEach(button => button.setAttribute("aria-pressed", "false"));
      updateProviderSummary(advancedProviders.find(template => template.key === event.target.value));
    });
    $("#provider-key-reveal")?.addEventListener("click", event => {
      const input = $("#provider-api-key");
      const reveal = event.currentTarget.getAttribute("aria-pressed") !== "true";
      input.type = reveal ? "text" : "password";
      event.currentTarget.setAttribute("aria-pressed", String(reveal));
      event.currentTarget.textContent = reveal ? "Hide" : "Show";
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
  if (!stillCurrent()) return;
  const modelCapabilityResults = $("#model-capability-results");
  if (modelCapabilityResults?.isConnected) {
    modelCapabilityResults.innerHTML = modelCapabilityResultsMarkup(modelCapabilityResult.page, modelCapabilityResult.error);
  }
}

/* -------------------------------------------------------- guided bot setup */

const SETUP_TOOL_EXPANSIONS = { files: ["read_file", "list_files", "write_file"], memory: ["remember", "recall"],
  grounding: ["live_search", "inspect_media"] };
const OPENCODE_TOOL_NAMES = new Set(["read_file", "list_files", "write_file", "shell", "web_fetch", "live_search", "remember", "recall"]);
const BOT_SETUP_TOOLS = [
  ["read_file", "Read workspace files", "Open text files in this bot’s workspace."],
  ["list_files", "List workspace files", "See file names in this bot’s workspace."],
  ["write_file", "Write workspace files", "Create or replace workspace files; policy still applies."],
  ["shell", "Run shell commands", "Run commands within Hutch’s configured shell boundary."],
  ["web_fetch", "Fetch public pages", "Read public pages through Hutch’s checked network path."],
  ["live_search", "Search live sources", "Fan out across public feeds, news, and discussion with explicit time bounds; every result keeps its source and limits."],
  ["inspect_media", "Inspect images and video", "Store and hash media, sample claim-relevant frames, and state what was not inspected. No authenticity verdict."],
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
  if (!suggestBotRoleName(purpose)) return "";
  const givenNames = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Rowan", "Quinn",
    "Alex", "Jamie", "Cameron", "Sage", "Reese", "Drew", "Robin", "Sam"];
  const familyNames = ["Bennett", "Chen", "Clarke", "Ellis", "James", "Kim", "Lee", "Morgan",
    "Patel", "Reed", "Rivera", "Shah", "Singh", "Taylor", "Walker", "Wright"];
  const identities = givenNames.flatMap(given => familyNames.map(family => `${given} ${family}`));
  const occupied = new Set((existingBots || []).map(bot =>
    String(bot.display_name || bot.name || "").trim().split(" · ", 1)[0].toLowerCase()));
  let seed = 0;
  for (const char of `${purpose || ""}`.toLowerCase()) seed = (Math.imul(seed, 31) + char.charCodeAt(0)) | 0;
  const start = (seed >>> 0) % identities.length;
  let identity = "";
  for (let offset = 0; offset < identities.length; offset++) {
    const candidate = identities[(start + offset) % identities.length];
    if (!occupied.has(candidate.toLowerCase())) { identity = candidate; break; }
  }
  if (!identity) identity = `${identities[start]} ${(existingBots || []).length + 1}`;
  return identity;
}

function suggestedBotAddress(roleName) {
  const addressSource = roleName || "";
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

/* OpenCode owns its provider login. This dialog lists the methods the
   installed server actually reports; Hutch never asks a person to paste a
   credential into a page it does not also own the destination of. */
async function openOpenCodeSetupDialog(onReady) {
  let status;
  try { status = await api("/v1/opencode/status"); }
  catch (error) {
    openModal({
      title: "OpenCode is not ready",
      bodyHtml: `<p>${esc(error.message)}</p>
        <p class="hint">Install or update the OpenCode V2 CLI, then reopen this setup. Hutch uses its own private profile. You can choose an existing API login during setup.</p>`,
      confirmText: "Close", onConfirm: () => true,
    });
    return;
  }
  let ready = Boolean(status.ready);
  let activeAttempt = null;
  const integrations = (status.integrations || []).filter(item =>
    item.methods?.length && item.id !== "opencode");
  let filter = "";
  const methodButtons = row => (row.methods || []).map(method => {
    if (method.type === "key") return `<button class="btn ghost small" type="button" data-oc-key="${esc(row.id)}">Use API key</button>`;
    if (method.type === "oauth") return `<button class="btn ghost small" type="button" data-oc-oauth="${esc(row.id)}" data-oc-method="${esc(method.id)}">${esc(method.label || "Sign in")}</button>`;
    if (method.type === "command") return `<span class="hint">Needs the provider's CLI sign-in</span>`;
    if (method.type === "env") return `<span class="hint">Needs an environment variable: ${esc((method.names || []).join(", "))}</span>`;
    return "";
  }).join(" ");
  const rowsHtml = () => {
    const q = filter.trim().toLowerCase();
    const matches = integrations.filter(item => !q || `${item.name} ${item.id}`.toLowerCase().includes(q));
    const ordered = [...matches].sort((a, b) => Number(b.connected) - Number(a.connected) || a.name.localeCompare(b.name)).slice(0, 24);
    if (!ordered.length) return `<p class="hint">No matching provider. Try another name.</p>`;
    return ordered.map(row => `<article class="oc-provider-card" data-oc-row="${esc(row.id)}">
      <div class="oc-provider-head">
        <div class="provider-choice-copy"><strong>${esc(row.name)}</strong>
          <small>${row.connected ? "Connected to this private profile" : "Not connected"}</small></div>
        <div class="oc-provider-actions" role="group" aria-label="Connect ${esc(row.name)}">${methodButtons(row)}</div>
      </div>
      <div class="oc-connect-slot" data-oc-slot="${esc(row.id)}"></div>
    </article>`).join("");
  };
  openModal({
    title: "Connect OpenCode",
    wide: true,
    showCancel: false,
    confirmText: "Done",
    bodyHtml: `<div id="opencode-setup">
      <p>Choose the account you want OpenCode to use. Hutch requires OpenCode V2 and creates a private profile for this installation.</p>
      <button class="btn ghost small" type="button" id="oc-find-local">Use an existing OpenCode login</button>
      <div id="oc-local-logins" class="oc-provider-list" aria-live="polite"></div>
      <label class="field" for="oc-provider-filter">Find a provider<input id="oc-provider-filter" type="search" autocomplete="off" placeholder="Search OpenAI, Anthropic, OpenRouter…"></label>
      <div id="oc-provider-list" class="oc-provider-list" aria-live="polite">${rowsHtml()}</div>
      <p class="hint" id="oc-setup-status" role="status" aria-live="polite"></p>
      <p class="hint">An API key or sign-in is saved by OpenCode inside Hutch's private profile. Hutch never displays it again. If a provider is not listed, install or update the OpenCode CLI and reconnect.</p>
    </div>`,
    onConfirm: async () => {
      if (ready) onReady?.(status);
      return true;
    },
  });
  const statusNode = $("#oc-setup-status");
  const note = text => { if (statusNode) statusNode.textContent = text; };
  const refreshAfterConnect = async () => {
    note("Checking the private OpenCode profile…");
    const refreshed = await api("/v1/opencode/status");
    status = refreshed;
    ready = Boolean(refreshed.ready);
    integrations.splice(0, integrations.length, ...(refreshed.integrations || []).filter(item =>
      item.methods?.length && item.id !== "opencode"));
    const providerList = $("#oc-provider-list");
    if (providerList) { providerList.innerHTML = rowsHtml(); bindRows(); }
    if (ready) {
      note(refreshed.authenticated ? "Connected. OpenCode has a usable model." : "OpenCode has a usable model available.");
      toast("OpenCode is ready.");
      onReady?.(refreshed);
      return true;
    }
    note("The account was saved, but OpenCode does not list a usable model yet. Reopen setup after checking the provider account.");
    return false;
  };
  $("#oc-find-local")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    note("Checking local OpenCode logins…");
    try {
      const result = await api("/v1/opencode/local-logins");
      const target = $("#oc-local-logins");
      if (!target) return;
      const logins = result.logins || [];
      target.innerHTML = logins.length ? `<p class="hint">Only the API login you select is copied. Your personal profile stays unchanged. Browser sign-ins need a fresh sign-in below.</p>` + logins.map(login =>
        `<article class="oc-provider-card"><div class="oc-provider-head">
          <div class="provider-choice-copy"><strong>${esc(login.provider_id)}</strong><small>${esc(login.detail)}</small></div>
          ${login.reusable ? `<button class="btn ghost small" type="button" data-oc-local="${esc(login.provider_id)}">Use this login</button>` : ""}
        </div></article>`).join("") : `<p class="hint">No local login was found. Connect a provider below.</p>`;
      note("");
      $$("[data-oc-local]", target).forEach(use => use.addEventListener("click", async () => {
        const buttons = $$("[data-oc-local]", target);
        buttons.forEach(item => { item.disabled = true; });
        note("Connecting the selected local account…");
        try {
          await api("/v1/opencode/connect/local", {method: "POST", body: {provider_id: use.dataset.ocLocal}});
          await refreshAfterConnect();
        } catch (error) { note(error.message); }
        finally { buttons.forEach(item => { item.disabled = false; }); }
      }));
    } catch (error) { note(error.message); }
    finally { button.disabled = false; }
  });
  const bindRows = () => {
    $$("[data-oc-key]").forEach(button => button.addEventListener("click", () => {
      const integrationId = button.dataset.ocKey;
      const slot = $(`[data-oc-slot="${CSS.escape(integrationId)}"]`);
      if (!slot) return;
      slot.innerHTML = `<label class="field" for="oc-key-${esc(integrationId)}">API key
        <input id="oc-key-${esc(integrationId)}" type="password" autocomplete="off" spellcheck="false"></label>
        <button class="btn primary small" type="button" data-oc-save="${esc(integrationId)}">Save key</button>
        <button class="btn ghost small" type="button" data-oc-cancel>Cancel</button>`;
      $("[data-oc-save]", slot)?.addEventListener("click", async () => {
        const input = $("input", slot);
        const key = input?.value.trim() || "";
        if (!key) { note("Paste the provider API key first."); input?.focus(); return; }
        const save = $("[data-oc-save]", slot);
        if (save) save.disabled = true;
        note("Saving this account in the private OpenCode profile…");
        try {
          await api("/v1/opencode/connect/key", { method: "POST", body: {
            integration_id: integrationId, key, label: "Hutch",
          } });
          input.value = "";
          await refreshAfterConnect();
        } catch (error) {
          note(error.message);
          if (save) save.disabled = false;
        }
      });
      $("[data-oc-cancel]", slot)?.addEventListener("click", bindRows);
      $("input", slot)?.focus();
    }));
    $$("[data-oc-oauth]").forEach(button => button.addEventListener("click", async () => {
      const integrationId = button.dataset.ocOauth;
      const methodId = button.dataset.ocMethod;
      const slot = $(`[data-oc-slot="${CSS.escape(integrationId)}"]`);
      if (!slot) return;
      button.disabled = true;
      note("Starting the provider sign-in…");
      try {
        const result = await api("/v1/opencode/oauth/start", { method: "POST", body: {
          integration_id: integrationId, method_id: methodId,
        } });
        activeAttempt = { integrationId, attempt: result.attempt || {} };
        const attempt = activeAttempt.attempt;
        const url = typeof attempt.url === "string" ? attempt.url : "";
        slot.innerHTML = `<p class="hint">${esc(attempt.instructions || "Complete the sign-in in your browser.")}</p>
          ${url ? `<p><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open provider sign-in</a></p>` : ""}
          ${attempt.mode === "code" ? `<label class="field" for="oc-code-${esc(integrationId)}">Authorization code<input id="oc-code-${esc(integrationId)}" autocomplete="one-time-code"></label>
            <button class="btn primary small" type="button" data-oc-complete>Finish sign-in</button>` : ""}
          <button class="btn ghost small" type="button" data-oc-cancel>Cancel</button>`;
        $("[data-oc-complete]", slot)?.addEventListener("click", async () => {
          const code = $("input", slot)?.value.trim() || "";
          try {
            await api("/v1/opencode/oauth/complete", { method: "POST", body: {
              integration_id: integrationId, attempt_id: attempt.attemptID, code,
            } });
            await refreshAfterConnect();
          } catch (error) { note(error.message); }
        });
        $("[data-oc-cancel]", slot)?.addEventListener("click", async () => {
          try { await api(`/v1/opencode/oauth/${encodeURIComponent(integrationId)}/${encodeURIComponent(attempt.attemptID)}`, { method: "DELETE" }); } catch { /* best effort */ }
          activeAttempt = null; bindRows();
        });
        if (attempt.mode !== "code" && attempt.attemptID) {
          note("Waiting for the provider sign-in to finish…");
          const poll = setInterval(async () => {
            if (!activeAttempt || activeAttempt.attempt.attemptID !== attempt.attemptID) { clearInterval(poll); return; }
            try {
              const current = await api(`/v1/opencode/oauth/${encodeURIComponent(integrationId)}/${encodeURIComponent(attempt.attemptID)}`);
              const state = current.attempt?.status || "";
              if (state === "complete") { clearInterval(poll); await refreshAfterConnect(); }
              else if (state === "failed" || state === "expired") {
                clearInterval(poll); note(current.attempt?.message || `Sign-in ${state}.`); button.disabled = false;
              }
            } catch (error) { clearInterval(poll); note(error.message); button.disabled = false; }
          }, 1200);
        }
      } catch (error) {
        note(error.message);
        button.disabled = false;
      }
    }));
  };
  $("#oc-provider-filter")?.addEventListener("input", event => {
    filter = event.currentTarget.value;
    $("#oc-provider-list").innerHTML = rowsHtml();
    bindRows();
  });
  bindRows();
}

async function promptNewBot(preselect = "", sourceMessageId = "", duplicateBot = null, prefillPurpose = "", firstRunChoice = null) {
  const startsNewDraft = !!(preselect || sourceMessageId || duplicateBot || prefillPurpose || firstRunChoice);
  if (assistantSetupPage?.isSubmitting()) {
    toast("Assistant creation is still pending. Wait for its result before starting another setup.");
    return;
  }
  if (assistantSetupPage && !startsNewDraft) {
    if (location.hash === "#/assistant/new") await renderAssistantSetupPage();
    else location.hash = "#/assistant/new";
    return;
  }
  if (startsNewDraft && (assistantSetupPage || loadAssistantSetupDraft())) {
    const confirmed = await confirmDialog({
      title: "Replace your unsaved setup?",
      body: "You already have an assistant setup in this tab. Replacing it discards that draft; Cancel keeps it available.",
      confirmText: "Replace draft",
      danger: true,
    });
    if (!confirmed) return;
  }
  const generation = ++assistantSetupGeneration;
  const returnRoute = location.hash === "#/assistant/new" ? "#/chat" : location.hash || "#/chat";
  const requestedFrom = location.hash;
  let templates;
  try { templates = await api("/bots/templates"); }
  catch (err) {
    if (generation !== assistantSetupGeneration || location.hash !== requestedFrom) return;
    if (requestedFrom === "#/assistant/new") view.innerHTML = errorState(err);
    else toast(`Bot setup is unavailable: ${err.message}`, true);
    return;
  }
  let taskPresets = [];
  try { taskPresets = await api("/v1/task-presets"); }
  catch { /* choosing a task focus is optional; the server still validates a submitted profile */ }
  let workspaceDefaults = { model: "", inference_mode: "hybrid", configured: false };
  try { workspaceDefaults = await api("/v1/preferences/model-defaults"); }
  catch (err) { toast(`Workspace model defaults could not be loaded; choose a route manually. ${err.message}`, true); }
  let conversationSource = null;
  if (!duplicateBot && currentConversationId && currentStudioBot && isConversationView()) {
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
  let openCodeStatus = firstRunOpenCodeStatus;
  if (!botsCache.length && openCodeStatus === null) {
    try { openCodeStatus = await api("/v1/opencode/status"); firstRunOpenCodeStatus = openCodeStatus; }
    catch { openCodeStatus = null; }
  }
  const openCodeDefault = openCodeStatus?.ready ? openCodeStatus.models?.[0]?.spec || "" : "";
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
  const firstRunModel = firstRunChoice?.model && !firstRunChoice.model.startsWith("mock/") ? firstRunChoice.model : "";
  let modelSuggestion = duplicateBot?.model || conversationSource?.model_suggestion || workspaceDefaults.model || firstRunModel || "";
  let modelSuggestionSource = duplicateBot ? "duplicate" : conversationSource?.model_suggestion ? "chat" : workspaceDefaults.model ? "workspace" : firstRunModel ? "first_run" : "";
  const draft = {
    step: 0, forceAdvanced: !!chosenTemplate || !!duplicateBot,
    runtime: duplicateBot?.runtime || firstRunChoice?.runtime || (!modelSuggestion && openCodeDefault ? "opencode" : "builtin"),
    purpose: duplicateBot?.instructions || conversationSource?.original_request || prefillPurpose || "",
    useConversationSource: !duplicateBot && !!conversationSource,
    selectedContextMessageIds: new Set(),
    template: chosenTemplate?.name || "", preset: duplicateBot?.preset || chosenTemplate?.preset || "", name: "",
    display_name: duplicateBot ? `${botHeading(duplicateBot)} copy`.slice(0, 80) : "",
    description: duplicateBot?.description || "",
    model: modelSuggestion || (!duplicateBot ? openCodeDefault : ""),
    purposeRefinement: null, purposeRefinementStatus: "",
    purposeClarificationHistory: [], purposeClarificationQuestion: null,
    purposeClarificationChoice: "", purposeClarificationAnswer: "", purposeDraftPending: null,
    inference_mode: duplicateBot?.inference_mode || conversationSource?.inference_mode_suggestion ||
      (openCodeDefault && !modelSuggestion ? "hybrid" : workspaceDefaults.inference_mode || "hybrid"),
    workspace_mode: duplicateBot?.workspace_mode === "fresh" ? "fresh" : "managed",
    // A duplicate is a safe configuration starting point, not a copy of authority.
    tools: duplicateBot ? new Set() : chosenTemplate ? templateTools(chosenTemplate) : new Set(),
    memory_enabled: false,
    memory_learning: duplicateBot?.memory_learning || 'hybrid',
    local_browser_handoff: false,
    cron: "", timezone: "UTC", catch_up: "coalesce", schedule_prompt: "",
    limits: { max_steps: 24, timeout_seconds: 900, daily_token_cap: 200000,
      max_turn_tokens: 0, max_cost_usd: 0, daily_cost_cap_usd: 0, ...(duplicateBot?.limits || {}) },
  };
  let presetEdited = false;
  draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
  let displayNameEdited = !!duplicateBot;
  let descriptionEdited = !!duplicateBot?.description;
  let addressEdited = false;
  let draftClosed = false;
  let persistTimer = 0;
  let creating = false;
  const restoredSetup = !preselect && !sourceMessageId && !duplicateBot && !prefillPurpose && !firstRunChoice
    ? loadAssistantSetupDraft() : null;
  if (restoredSetup) {
    const saved = restoredSetup.draft;
    draft.step = Math.min(3, Math.max(0, Math.floor(Number(saved.step) || 0)));
    draft.forceAdvanced = !!saved.forceAdvanced;
    draft.runtime = typeof saved.runtime === "string" ? saved.runtime : draft.runtime;
    draft.purpose = typeof saved.purpose === "string" ? saved.purpose.slice(0, 20_000) : draft.purpose;
    draft.useConversationSource = !!saved.useConversationSource;
    draft.template = typeof saved.template === "string" ? saved.template.slice(0, 120) : "";
    draft.preset = typeof saved.preset === "string" ? saved.preset.slice(0, 120) : "";
    draft.name = typeof saved.name === "string" ? saved.name.slice(0, 41) : "";
    draft.display_name = typeof saved.display_name === "string" ? saved.display_name.slice(0, 80) : "";
    draft.description = typeof saved.description === "string" ? saved.description.slice(0, 500) : "";
    draft.model = typeof saved.model === "string" ? saved.model.slice(0, 200) : draft.model;
    draft.inference_mode = ["hybrid", "local", "offline"].includes(saved.inference_mode) ? saved.inference_mode : draft.inference_mode;
    draft.workspace_mode = saved.workspace_mode === "fresh" ? "fresh" : "managed";
    draft.memory_learning = saved.memory_learning === "hybrid" ? "hybrid" : "review";
    draft.local_browser_handoff = !!saved.local_browser_handoff;
    draft.cron = typeof saved.cron === "string" ? saved.cron.slice(0, 200) : "";
    draft.timezone = typeof saved.timezone === "string" ? saved.timezone.slice(0, 80) : "UTC";
    draft.catch_up = saved.catch_up === "skip" ? "skip" : "coalesce";
    draft.schedule_prompt = typeof saved.schedule_prompt === "string" ? saved.schedule_prompt.slice(0, 20_000) : "";
    draft.tools = new Set(Array.isArray(saved.tools) ? saved.tools.filter(item => typeof item === "string").slice(0, 64) : []);
    draft.selectedContextMessageIds = new Set(Array.isArray(saved.selectedContextMessageIds)
      ? saved.selectedContextMessageIds.filter(item => typeof item === "string").slice(0, 32) : []);
    if (saved.limits && typeof saved.limits === "object") {
      for (const key of Object.keys(draft.limits)) {
        const value = Number(saved.limits[key]);
        if (Number.isFinite(value) && value >= 0) draft.limits[key] = value;
      }
    }
    if (restoredSetup.conversationSource && typeof restoredSetup.conversationSource.original_request === "string"
        && Array.isArray(restoredSetup.conversationSource.context_candidates)
        && restoredSetup.conversationSource.context_candidates.every(message => message && typeof message.id === "string" && typeof message.content === "string")) {
      conversationSource = restoredSetup.conversationSource;
    }
    draft.useConversationSource = draft.useConversationSource && !!conversationSource;
    draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
    draft.purposeRefinementStatus = "Restored your unsaved setup from this tab. Nothing has been saved or created.";
    displayNameEdited = !!draft.display_name;
    descriptionEdited = !!draft.description;
    addressEdited = !!draft.name;
    presetEdited = !!draft.preset;
  }
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
    const role = suggestBotRoleName(draft.purpose);
    if (!displayNameEdited) draft.display_name = suggestBotDisplayName(draft.purpose);
    if (!descriptionEdited) draft.description = role;
    if (!addressEdited) draft.name = uniqueAddress(role);
  };
  const refreshNamePreview = () => {
    const displayName = $("#setup-display_name");
    if (displayName && !displayNameEdited) displayName.value = draft.display_name;
    const description = $("#setup-description");
    if (description && !descriptionEdited) description.value = draft.description;
    const address = $("#setup-name");
    if (address && !addressEdited) address.value = draft.name;
  };
  const selectedCreationContext = () => (conversationSource?.context_candidates || [])
    .filter(message => draft.selectedContextMessageIds.has(message.id));
  const purposeSetupStorageKey = conversationSource && !duplicateBot
    ? `hutch-bot-setup-clarification:${conversationSource.conversation_id}:${conversationSource.message_id}` : "";
  const currentPurposeDraftFingerprint = () => JSON.stringify({
    source_message_id: draft.useConversationSource ? conversationSource?.message_id || "" : "",
    purpose: draft.purpose, context: selectedCreationContext().map(message => message.id),
    clarification_history: draft.purposeClarificationHistory,
  });
  const currentPurposeDraftRequest = () => ({
    source_message_id: conversationSource?.message_id || "", purpose: draft.purpose,
    context_message_ids: selectedCreationContext().map(message => message.id),
    clarification_history: draft.purposeClarificationHistory,
  });
  const validClarificationTurn = turn => turn && typeof turn.question === "string"
    && turn.question.trim() && turn.question.length <= 1_000 && typeof turn.answer === "string"
    && turn.answer.trim() && turn.answer.length <= 4_000;
  const validClarificationQuestion = question => question && typeof question.question === "string"
    && question.question.trim() && question.question.length <= 1_000 && Array.isArray(question.options)
    && question.options.length >= 2 && question.options.length <= 5
    && question.options.every(option => typeof option === "string" && option.trim() && option.length <= 240);
  const persistPurposeSetupDraft = () => {
    if (draftClosed || !purposeSetupStorageKey || !conversationSource || !draft.useConversationSource) return;
    const pending = draft.purposeDraftPending;
    storageSet(purposeSetupStorageKey, JSON.stringify({
      version: 1, updated_at: Date.now(), conversation_id: conversationSource.conversation_id,
      source_message_id: conversationSource.message_id, purpose: draft.purpose,
      selected_context_message_ids: [...draft.selectedContextMessageIds],
      display_name: draft.display_name, name: draft.name,
      description: draft.description, display_name_edited: displayNameEdited,
      description_edited: descriptionEdited, address_edited: addressEdited,
      clarification_history: draft.purposeClarificationHistory,
      clarification_question: draft.purposeClarificationQuestion,
      clarification_choice: draft.purposeClarificationChoice,
      clarification_answer: draft.purposeClarificationAnswer,
      refinement: draft.purposeRefinement,
      status: draft.purposeRefinementStatus,
      pending: pending ? {
        request_body: pending.requestBody, idempotency_key: pending.idempotencyKey,
        run_id: pending.runId || "", source_fingerprint: pending.sourceFingerprint,
      } : null,
    }));
  };
  const clearPurposeSetupProgress = ({ clearStorage = true } = {}) => {
    draft.purposeClarificationHistory = [];
    draft.purposeClarificationQuestion = null;
    draft.purposeClarificationChoice = "";
    draft.purposeClarificationAnswer = "";
    draft.purposeRefinement = null;
    draft.purposeDraftPending = null;
    draft.purposeRefinementStatus = "";
    if (clearStorage && purposeSetupStorageKey) storageRemove(purposeSetupStorageKey);
  };
  const restorePurposeSetupDraft = () => {
    if (!purposeSetupStorageKey || !conversationSource) return;
    let saved;
    try { saved = JSON.parse(storageGet(purposeSetupStorageKey) || "null"); }
    catch { storageRemove(purposeSetupStorageKey); return; }
    if (!saved || saved.version !== 1 || saved.conversation_id !== conversationSource.conversation_id
        || saved.source_message_id !== conversationSource.message_id || typeof saved.purpose !== "string"
        || !Number.isFinite(saved.updated_at) || saved.updated_at > Date.now() + 60_000
        || Date.now() - saved.updated_at > 7 * 24 * 60 * 60 * 1000
        || saved.purpose.length > 20_000 || !saved.purpose.trim()
        || !Array.isArray(saved.clarification_history) || saved.clarification_history.length > 5
        || !saved.clarification_history.every(validClarificationTurn)) {
      storageRemove(purposeSetupStorageKey); return;
    }
    const validContextIds = new Set((conversationSource.context_candidates || []).map(message => message.id));
    const contextIds = Array.isArray(saved.selected_context_message_ids)
      ? saved.selected_context_message_ids : [];
    if (contextIds.length > (conversationSource.context_candidates || []).length
        || contextIds.some(id => typeof id !== "string" || !validContextIds.has(id))) {
      storageRemove(purposeSetupStorageKey); return;
    }
    draft.useConversationSource = true;
    draft.purpose = saved.purpose;
    draft.selectedContextMessageIds = new Set(contextIds);
    draft.purposeClarificationHistory = saved.clarification_history;
    if (validClarificationQuestion(saved.clarification_question)) {
      draft.purposeClarificationQuestion = saved.clarification_question;
    }
    if (typeof saved.clarification_choice === "string") draft.purposeClarificationChoice = saved.clarification_choice;
    if (typeof saved.clarification_answer === "string" && saved.clarification_answer.length <= 4_000) {
      draft.purposeClarificationAnswer = saved.clarification_answer;
    }
    if (saved.display_name_edited && typeof saved.display_name === "string" && saved.display_name.length <= 80) {
      draft.display_name = saved.display_name; displayNameEdited = true;
    }
    if (saved.description_edited && typeof saved.description === "string" && saved.description.length <= 240) {
      draft.description = saved.description; descriptionEdited = true;
    }
    if (saved.address_edited && typeof saved.name === "string" && /^[a-z0-9][a-z0-9-]{1,40}$/.test(saved.name)) {
      draft.name = saved.name; addressEdited = true;
    }
    if (saved.refinement && typeof saved.refinement.content === "string"
        && saved.refinement.content.length <= 20_000
        && Array.isArray(saved.refinement.assumptions || [])
        && (saved.refinement.assumptions || []).length <= 5
        && (saved.refinement.assumptions || []).every(item => typeof item === "string" && item.length <= 500)) {
      draft.purposeRefinement = {
        content: saved.refinement.content,
        assumptions: saved.refinement.assumptions || [],
        sourceFingerprint: typeof saved.refinement.sourceFingerprint === "string"
          ? saved.refinement.sourceFingerprint : "",
      };
    }
    if (typeof saved.status === "string" && saved.status.length <= 500) draft.purposeRefinementStatus = saved.status;
    const pending = saved.pending;
    const pendingBody = pending?.request_body;
    const pendingContext = Array.isArray(pendingBody?.context_message_ids) ? pendingBody.context_message_ids : [];
    const pendingHistory = Array.isArray(pendingBody?.clarification_history) ? pendingBody.clarification_history : [];
    const pendingBodyValid = pendingBody && pendingBody.source_message_id === conversationSource.message_id
      && typeof pendingBody.purpose === "string" && pendingBody.purpose.trim() && pendingBody.purpose.length <= 20_000
      && pendingContext.length <= (conversationSource.context_candidates || []).length
      && pendingContext.every(id => typeof id === "string" && validContextIds.has(id))
      && new Set(pendingContext).size === pendingContext.length
      && !pendingContext.includes(conversationSource.message_id)
      && pendingHistory.length <= 5 && pendingHistory.every(validClarificationTurn);
    if (pending && typeof pending.idempotency_key === "string" && pending.idempotency_key.length <= 128
        && typeof pending.source_fingerprint === "string" && pending.source_fingerprint.length <= 4_000
        && (!pending.run_id || (typeof pending.run_id === "string" && pending.run_id.length <= 128))
        && pendingBodyValid) {
      draft.purposeDraftPending = {
        requestBody: pending.request_body, idempotencyKey: pending.idempotency_key,
        runId: pending.run_id || "", sourceFingerprint: pending.source_fingerprint,
      };
    }
    const sourceChars = conversationSource.original_request.length + draft.purpose.length
      + selectedCreationContext().reduce((total, message) => total + message.content.length, 0)
      + draft.purposeClarificationHistory.reduce((total, turn) => total + turn.question.length + turn.answer.length, 0);
    if (sourceChars > 20_000) clearPurposeSetupProgress();
  };
  restorePurposeSetupDraft();
  refreshSuggestedIdentity();
  const markPurposeDraftFreshness = () => {
    const savedOutput = draft.purposeRefinement || draft.purposeClarificationQuestion;
    if (!savedOutput) {
      if (draft.purposeDraftPending) {
        const fresh = draft.purposeDraftPending.sourceFingerprint === currentPurposeDraftFingerprint();
        draft.purposeRefinementStatus = fresh
          ? "Coordinator review is still running; resume it here or Stop it in the coordinator chat."
          : "A review for an earlier request is still running. It cannot be applied to this edited draft.";
        const pendingStatus = $("#setup-purpose-draft-status");
        if (pendingStatus) pendingStatus.textContent = draft.purposeRefinementStatus;
      }
      persistPurposeSetupDraft(); return;
    }
    const fingerprint = savedOutput.sourceFingerprint;
    const fresh = fingerprint === currentPurposeDraftFingerprint();
    draft.purposeRefinementStatus = fresh
      ? draft.purposeClarificationQuestion
        ? "Answer this one detail to continue; nothing has been saved or created."
        : "Draft ready. Review it before applying; no Bot configuration has changed."
      : "The request or selected context changed. Start a fresh check before using this response.";
    const status = $("#setup-purpose-draft-status");
    if (status) status.textContent = draft.purposeRefinementStatus;
    const apply = $("#setup-purpose-draft-use");
    if (apply) apply.disabled = !fresh;
    const continueButton = $("#setup-clarification-continue");
    if (continueButton) continueButton.disabled = !fresh;
    persistPurposeSetupDraft();
  };
  const purposeRefinementHtml = () => {
    const question = draft.purposeClarificationQuestion;
    if (question) {
      const fresh = question.sourceFingerprint === currentPurposeDraftFingerprint();
      return `<section class="setup-purpose-draft" id="setup-clarification-question" tabindex="-1" aria-labelledby="setup-clarification-title">
        <h4 id="setup-clarification-title">One detail to confirm</h4>
        <p>${esc(question.question)}</p>
        <fieldset class="setup-template-options setup-clarification-options"><legend>Choose one, or write another answer</legend>
          ${question.options.map((option, index) => `<label class="setup-choice"><input type="radio" name="setup-clarification-choice" value="${index}" ${draft.purposeClarificationChoice === String(index) ? "checked" : ""}>
            <span><b>${esc(option)}</b></span></label>`).join("")}
        </fieldset>
        <label class="field" for="setup-clarification-answer">Your answer (optional if you choose above)
          <textarea id="setup-clarification-answer" rows="3" maxlength="4000" placeholder="Add a different answer or useful detail">${esc(draft.purposeClarificationAnswer)}</textarea>
        </label>
        <p class="hint">Do not enter passwords, codes or account credentials. Your answer and draft stay on this device for up to 7 days.</p>
        <div class="setup-clarification-actions"><button type="button" class="btn" id="setup-clarification-continue" ${fresh ? "" : "disabled"}>Continue with this answer</button>
          <button type="button" class="btn ghost small" id="setup-clarification-reset">Start over</button></div>
      </section>`;
    }
    if (!draft.purposeRefinement) return "";
    const suggestion = draft.purposeRefinement;
    const fresh = suggestion.sourceFingerprint === currentPurposeDraftFingerprint();
    const assumptions = suggestion.assumptions?.length
      ? `<div id="setup-purpose-draft-assumptions"><b>Assumptions to review</b><ul>${suggestion.assumptions.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : "";
    return `<section class="setup-purpose-draft" id="setup-purpose-draft-review" tabindex="-1" aria-labelledby="setup-purpose-draft-title">
      <h4 id="setup-purpose-draft-title">Proposed Bot instructions</h4>
      <p class="hint">Review and edit this draft. Your original request stays linked. No settings or permissions change until you confirm.</p>
      <label class="field" for="setup-purpose-draft-text">Standing instructions<textarea id="setup-purpose-draft-text" rows="7" maxlength="20000">${esc(suggestion.content)}</textarea></label>
      ${assumptions}
      <div class="setup-clarification-actions"><button type="button" class="btn small" id="setup-purpose-draft-use" ${fresh ? "" : "disabled"}>Use this draft</button>
        <button type="button" class="btn ghost small" id="setup-clarification-reset">Start over</button></div>
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
    runtime: draft.runtime || "builtin",
    preset: draft.preset,
    description: draft.description.trim() || draft.purpose.trim().split("\n")[0].slice(0, 240),
    instructions: instructionsForDraft(), model: draft.model.trim(), inference_mode: draft.inference_mode,
    workspace_mode: draft.workspace_mode, tools: [...draft.tools], approval_mode: "ask", risk_tier: "supervised",
    limits: draft.limits, memory_enabled: draft.memory_enabled, memory_learning: draft.memory_learning,
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
    draft.preset = config.preset || "";
    presetEdited = true;
    draft.model = config.model || "";
    draft.runtime = config.runtime || "builtin";
    draft.inference_mode = config.inference_mode || "hybrid";
    draft.workspace_mode = config.workspace_mode || "managed";
    draft.tools = new Set(config.tools || []);
    draft.memory_enabled = !!config.memory_enabled;
    draft.memory_learning = config.memory_learning || 'review';
    draft.limits = { ...draft.limits, ...(config.limits || {}) };
    draft.local_browser_handoff = !!config.local_browser_handoff;
    draft.cron = config.cron || "";
    draft.timezone = config.timezone || "UTC";
    draft.catch_up = config.catch_up || "coalesce";
    draft.schedule_prompt = config.schedule_prompt || "";
    clearPurposeSetupProgress();
    draft.purposeRefinementStatus = "";
    displayNameEdited = true;
    descriptionEdited = true;
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
  const stepTitles = ["Set up your assistant", "Choose what powers it", "Choose its apps", "Review and create"];
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
    for (const key of ["inference_mode", "workspace_mode", "catch_up", "preset", "runtime", "memory_learning"]) {
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
  const persistSetupDraft = () => {
    clearTimeout(persistTimer);
    if (draftClosed || assistantSetupPage?.element !== element) return;
    snapshotFields();
    saveAssistantSetupDraft({
      conversationSource,
      draft: {
        ...draft,
        tools: [...draft.tools],
        selectedContextMessageIds: [...draft.selectedContextMessageIds],
        purposeRefinement: null,
        purposeDraftPending: null,
        purposeClarificationQuestion: null,
        purposeClarificationHistory: [],
      },
    });
  };
  let purposeDraftRequestInFlight = false;
  const parsePurposeDraftResponse = answer => {
    const normalized = answer.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    let parsed;
    try { parsed = JSON.parse(normalized); }
    catch { throw new Error("The coordinator response was not valid JSON. Nothing was applied; edit the request or try again."); }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("The coordinator response did not match the review format. Nothing was applied.");
    }
    const sensitive = /password|passcode|credential|verification code|one[- ]time code|two[- ]factor|\b2fa\b|sign[- ]?in|authorization|permission|account access|access token|secret/i;
    if (parsed.kind === "question") {
      if (!validClarificationQuestion(parsed) || sensitive.test(parsed.question)
          || parsed.options.some(option => sensitive.test(option))) {
        throw new Error("The coordinator returned an unsafe or malformed follow-up. Nothing was applied; edit the request and try again.");
      }
      const options = parsed.options.map(option => option.trim());
      if (new Set(options.map(option => option.toLocaleLowerCase())).size !== options.length) {
        throw new Error("The coordinator returned duplicate choices. Nothing was applied; try again.");
      }
      return {kind: "question", question: parsed.question.trim(), options};
    }
    if (parsed.kind === "draft") {
      const assumptions = parsed.assumptions === undefined ? [] : parsed.assumptions;
      if (typeof parsed.instructions !== "string" || !parsed.instructions.trim()
          || parsed.instructions.length > 20_000 || !Array.isArray(assumptions)
          || assumptions.length > 5 || assumptions.some(item => typeof item !== "string" || item.length > 500)) {
        throw new Error("The coordinator returned an incomplete instruction draft. Nothing was applied; try again.");
      }
      return {kind: "draft", instructions: parsed.instructions, assumptions};
    }
    throw new Error("The coordinator response did not match the review format. Nothing was applied.");
  };
  const runPurposeClarification = async ({ answerCurrentQuestion = false } = {}) => {
    if (purposeDraftRequestInFlight) return;
    snapshotFields();
    setError("");
    if (!conversationSource?.source_bot_is_coordinator || !draft.useConversationSource || !draft.purpose.trim()) {
      setError("Use the selected coordinator request and review a non-empty purpose before drafting.");
      return;
    }
    if (answerCurrentQuestion) {
      const question = draft.purposeClarificationQuestion;
      if (!question || question.sourceFingerprint !== currentPurposeDraftFingerprint()) {
        setError("The request changed after this question. Start a fresh check before answering it.");
        return;
      }
      const answerText = $("#setup-clarification-answer")?.value?.trim() || "";
      const choiceIndex = draft.purposeClarificationChoice;
      const chosen = /^\d+$/.test(choiceIndex) ? question.options[Number(choiceIndex)] || "" : "";
      const answer = answerText && chosen ? `${chosen} — ${answerText}` : answerText || chosen;
      if (!answer) {
        setError("Choose an option or write a short answer before continuing.");
        $("#setup-clarification-answer")?.focus();
        return;
      }
      if (answer.length > 4_000) {
        setError("Keep this answer under 4,000 characters.");
        $("#setup-clarification-answer")?.focus();
        return;
      }
      if (draft.purposeClarificationHistory.length >= 5) {
        setError("This setup has reached its five-question limit. Start a fresh check or edit the instructions directly.");
        return;
      }
      const selectedChars = selectedCreationContext().reduce((total, message) => total + message.content.length, 0);
      const historyChars = draft.purposeClarificationHistory.reduce(
        (total, turn) => total + turn.question.length + turn.answer.length, 0);
      if (conversationSource.original_request.length + draft.purpose.length + selectedChars
          + historyChars + question.question.length + answer.length > 20_000) {
        setError("This request plus its clarifications exceeds the 20,000-character review limit. Shorten the purpose or start over.");
        return;
      }
      draft.purposeClarificationHistory.push({question: question.question, answer});
      draft.purposeClarificationQuestion = null;
      draft.purposeClarificationChoice = "";
      draft.purposeClarificationAnswer = "";
    }
    if (Array.from(instructionsForDraft()).length > 20_000) {
      setError("Shorten the purpose or select fewer messages before drafting; the combined text exceeds 20,000 characters.");
      return;
    }
    const requestBody = draft.purposeDraftPending?.requestBody || currentPurposeDraftRequest();
    const sourceFingerprint = draft.purposeDraftPending?.sourceFingerprint || currentPurposeDraftFingerprint();
    if (!draft.purposeDraftPending) {
      const keyStorage = `hutch-bot-purpose-draft:${conversationSource.conversation_id}:${conversationSource.message_id}`;
      const fingerprint = await payloadFingerprint(requestBody);
      let key;
      try {
        const prior = JSON.parse(storageGet(keyStorage) || "null");
        key = prior?.fingerprint === fingerprint ? prior.key : null;
      } catch { /* replace a damaged retry marker */ }
      if (!key) {
        key = newIdempotencyKey();
        storageSet(keyStorage, JSON.stringify({fingerprint, key}));
      }
      draft.purposeDraftPending = {requestBody, idempotencyKey: key, runId: "", sourceFingerprint};
    }
    purposeDraftRequestInFlight = true;
    draft.purposeRefinementStatus = draft.purposeDraftPending.runId
      ? "Resuming the coordinator’s tool-free review…"
      : "Starting the coordinator’s tool-free review…";
    persistPurposeSetupDraft();
    const status = $("#setup-purpose-draft-status");
    if (status) status.textContent = draft.purposeRefinementStatus;
    const button = $("#setup-refine-purpose");
    if (button) button.disabled = true;
    let state = null;
    try {
      if (!draft.purposeDraftPending.runId) {
        const run = await api(`/v1/conversations/${encodeURIComponent(conversationSource.conversation_id)}/bot-purpose-drafts`, {
          method: "POST", headers: {"Idempotency-Key": draft.purposeDraftPending.idempotencyKey},
          body: draft.purposeDraftPending.requestBody,
        });
        if (typeof run.id !== "string" || !run.id || run.id.length > 128) {
          throw new Error("The coordinator did not return a valid review run. You can safely resume it.");
        }
        draft.purposeDraftPending.runId = run.id;
        persistPurposeSetupDraft();
      }
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline) {
        state = await api(`/v1/tasks/runs/${encodeURIComponent(draft.purposeDraftPending.runId)}?events=200`);
        if (state.terminal) break;
        draft.purposeRefinementStatus = `Coordinator review is ${state.status_label || state.status}; you can Stop it in the coordinator chat.`;
        const progress = $("#setup-purpose-draft-status");
        if (progress) progress.textContent = draft.purposeRefinementStatus;
        await new Promise(resolve => setTimeout(resolve, 900));
      }
      if (!state?.terminal) throw new Error("The review is still running. Its status and Stop control are in the coordinator chat; resume here when it finishes.");
      if (state.status !== "succeeded") throw new Error(state.error || state.reason || `Review ended as ${state.status_label || state.status}.`);
      const answer = [...(state.events || [])].reverse().find(item => item.type === "message" && item.data?.role === "assistant")?.data?.content || "";
      if (!answer.trim()) throw new Error("The coordinator did not return a review response.");
      const parsed = parsePurposeDraftResponse(answer);
      draft.purposeDraftPending = null;
      if (parsed.kind === "question") {
        if (draft.purposeClarificationHistory.length >= 5) {
          throw new Error("The coordinator requested another question after the five-question limit. Edit the instructions directly or start over.");
        }
        draft.purposeRefinement = null;
        draft.purposeClarificationQuestion = {...parsed, sourceFingerprint};
        draft.purposeRefinementStatus = "Answer this one detail to continue; nothing has been saved or created.";
      } else {
        draft.purposeClarificationQuestion = null;
        draft.purposeRefinement = {content: parsed.instructions, assumptions: parsed.assumptions, sourceFingerprint};
        draft.purposeRefinementStatus = "Draft ready. Review it before applying; no Bot configuration has changed.";
      }
      markPurposeDraftFreshness();
      persistPurposeSetupDraft();
      await renderStep();
      if (draft.purposeClarificationQuestion) $("#setup-clarification-question")?.focus();
      else $("#setup-purpose-draft-review")?.focus();
    } catch (error) {
      if (state?.terminal) draft.purposeDraftPending = null;
      draft.purposeRefinementStatus = `Nothing was applied: ${error.message}`;
      persistPurposeSetupDraft();
      const progress = $("#setup-purpose-draft-status");
      if (progress) progress.textContent = draft.purposeRefinementStatus;
      if (button?.isConnected) button.disabled = false;
    } finally {
      purposeDraftRequestInFlight = false;
    }
  };
  const displayTool = tool => BOT_SETUP_TOOLS.find(([name]) => name === tool)?.[1] || tool;
  const reviewHtml = () => {
    const template = selectedTemplate();
    const taskFocus = taskPresets.find(item => item.id === draft.preset);
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
        <div><dt>Short note</dt><dd>${esc(draft.description.trim() || "None")}</dd></div>
        <div><dt>Bot address</dt><dd>${esc(draft.name)}</dd></div>
        <div><dt>Purpose</dt><dd>${esc(draft.purpose)}</dd></div>
        ${sourceReview}
        ${contextReview}
        <div><dt>Starting point</dt><dd>${duplicateBot ? `Setup based on ${esc(duplicateBot.display_name || duplicateBot.name)}` : esc(template?.tagline || "Blank bot")}</dd></div>
        <div><dt>Runtime</dt><dd>${draft.runtime === "opencode" ? "OpenCode assistant" : "Hutch built-in"}</dd></div>
        <div><dt>Model route</dt><dd>${esc(draft.model)}</dd></div>
        <div><dt>Task focus</dt><dd>${esc(taskFocus?.title || "Standard context policy")}</dd></div>
        <div><dt>Inference</dt><dd>${esc(draft.inference_mode)}</dd></div>
        <div><dt>Workspace</dt><dd>${esc(draft.workspace_mode)}</dd></div>
        <div><dt>Approval</dt><dd>Ask before actions that require approval</dd></div>
        <div><dt>Tools</dt><dd>${draft.tools.size ? [...draft.tools].map(displayTool).map(esc).join(", ") : "No tools enabled"}</dd></div>
        <div><dt>Browser handoff</dt><dd>${draft.local_browser_handoff ? "On · human can take over in the visible Linux browser" : "Off"}</dd></div>
        <div><dt>Execution limits</dt><dd>${draft.limits.max_steps} steps · ${draft.limits.timeout_seconds} seconds · ${draft.limits.daily_token_cap.toLocaleString()} estimated tokens per day</dd></div>
        <div><dt>Model limits</dt><dd>${draft.limits.max_turn_tokens ? `${draft.limits.max_turn_tokens.toLocaleString()} tokens per turn` : "Provider default tokens per turn"} · ${draft.limits.max_cost_usd ? `${fmtUsd(draft.limits.max_cost_usd)} estimated per run` : "No per-run estimate limit"} · ${draft.limits.daily_cost_cap_usd ? `${fmtUsd(draft.limits.daily_cost_cap_usd)} estimated per day` : "No daily estimate limit"}</dd></div>
        <div><dt>Recurring task</dt><dd>${draft.cron.trim() ? `${esc(draft.cron.trim())} · ${esc(draft.timezone)} · missed windows: ${draft.catch_up === "skip" ? "skip" : "run once"}${draft.schedule_prompt.trim() ? ` · ${esc(draft.schedule_prompt.trim())}` : ""}` : "None"}</dd></div>
        <div><dt>Memory and learning</dt><dd>${draft.memory_enabled ? draft.memory_learning === 'hybrid' ? "Explicit formatting preferences saved automatically in each chat; other facts require review" : "New reference facts require review" : "Disabled"}</dd></div>
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
        ${draft.forceAdvanced ? `<p class="setup-assistant">Only this request and earlier user messages you select are included in this Bot draft. Assistant replies and other chats stay private; selected text cannot change tools, accounts or permissions.</p>` : ""}`
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
        <label class="field" for="setup-purpose"><span id="setup-purpose-label">Bot instructions</span><textarea id="setup-purpose" rows="4" maxlength="20000" required aria-labelledby="setup-purpose-label" aria-describedby="setup-purpose-hint">${esc(draft.purpose)}</textarea>
          <span class="hint" id="setup-purpose-hint">By default, Hutch uses your selected request. Editing it is optional; no tools or account access are inferred.</span></label>
      </details>` : `<label class="field" for="setup-purpose"><span id="setup-purpose-label">${prefillPurpose.trim() ? "Your starting request" : conversationSource ? "What should this assistant keep doing?" : "What would you like this assistant to handle?"}</span><textarea id="setup-purpose" rows="${draft.forceAdvanced ? 5 : 3}" maxlength="20000" placeholder="For example: review release notes and prepare a short summary of changes that affect our project." required aria-labelledby="setup-purpose-label" aria-describedby="setup-purpose-hint">${esc(draft.purpose)}</textarea>
        <span class="hint" id="setup-purpose-hint">${prefillPurpose.trim() ? "We carried this over from your first message. You can edit it, but you do not need to repeat it." : "This becomes the assistant’s starting instructions. Hutch does not add tools or account access."}</span></label>`}
        ${conversationSource?.source_bot_is_coordinator && conversationSource.source_bot_runtime === "builtin" && conversationSource.source_bot_model ? `<details class="setup-schedule setup-refine-details" id="setup-refine-details" ${draft.purposeClarificationQuestion || draft.purposeRefinement || draft.purposeDraftPending || draft.purposeRefinementStatus ? "open" : ""}>
          <summary>Check for missing details (optional)</summary>
          <div class="setup-refine-action">
            <button type="button" class="btn small" id="setup-refine-purpose" ${draft.purposeClarificationQuestion || draft.purposeRefinement ? "hidden" : ""}>${draft.purposeDraftPending ? "Resume clarification" : "Check for missing details"}</button>
            <p class="hint">${esc(conversationSource.source_bot_display_name)} uses this request and any earlier user messages you chose. It asks one question at a time only when an important work detail is missing, then offers an editable instruction draft. Up to five follow-ups. You can also skip this and create the Bot from your request as-is.</p>
            <p class="hint">This uses ${esc(conversationSource.source_bot_model)} without tools or permission changes. The unsent answer and draft are kept in this browser so you can resume after reopening setup. Normal usage limits apply.</p>
            <p class="hint" role="status" aria-live="polite" id="setup-purpose-draft-status">${esc(draft.purposeRefinementStatus)}</p>
            ${purposeRefinementHtml()}
          </div>
        </details>` : ""}
      <label class="field" for="setup-display_name"><span id="setup-display-name-label">Assistant name</span><input id="setup-display_name" maxlength="80" autocomplete="off" placeholder="Avery Chen" value="${esc(draft.display_name)}" required aria-labelledby="setup-display-name-label" aria-describedby="setup-display-name-hint">
        <span class="hint" id="setup-display-name-hint">Suggested from your request. Rename it anytime.</span></label>
      <details class="setup-schedule setup-identity">
        <summary>Advanced details</summary>
        <div class="form-grid">
          <label class="field" for="setup-name"><span id="setup-name-label">Internal address</span><input id="setup-name" maxlength="41" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="release-notes-reviewer" value="${esc(draft.name)}" required aria-labelledby="setup-name-label" aria-describedby="setup-name-hint">
            <span class="hint" id="setup-name-hint">A stable local identifier based on the task. Most people can leave it as suggested.</span></label>
          <label class="field" for="setup-description">Short note<input id="setup-description" maxlength="240" placeholder="What people can ask this assistant to do" value="${esc(draft.description)}"></label>
        </div>
      </details>
      ${!draft.forceAdvanced ? `<section class="setup-quick-summary" aria-label="Starting settings">
        <p>${draft.model ? "Uses the selected AI service" : "Choose an AI option to finish setup"} · no apps connected or recurring work · checks with you before important actions.</p>
        <p class="hint">Saves your assistant only; nothing starts until you ask it to work.</p>
      </section>
      <button type="button" class="btn ghost small setup-customize" id="setup-customize">Fine-tune the details</button>` : ""}
    </div>`;
    if (step === 1) {
      let routeOptions = [];
      try { routeOptions = await api(`/v1/model-routes?inference_mode=${encodeURIComponent(draft.inference_mode)}&runtime=${encodeURIComponent(draft.runtime)}`); }
      catch { /* the route can still be entered directly; creation validates it */ }
      if (draft.step !== 1) return;
      const readyRoutes = routeOptions.filter(route => route.state === "ready" && !route.spec.startsWith("mock/"));
      const options = readyRoutes.map(route => `<option value="${esc(route.spec)}" label="${esc(`${route.group}: ${route.note || route.label}`)}"></option>`).join("");
      const opencode = draft.runtime === "opencode";
      content = `<div class="setup-conversation form-grid">
        <p class="setup-assistant">${draft.model ? "Review the configured route below." : opencode ? "OpenCode needs a connected provider account and one of its models." : "Choose a configured model route. Safe defaults fill the other setup choices."} It becomes the Bot’s saved default; creating the Bot does not start a run.</p>
        <label class="field" for="setup-runtime"><span id="setup-runtime-label">Assistant runtime</span><select id="setup-runtime" aria-labelledby="setup-runtime-label" aria-describedby="setup-runtime-hint">
          <option value="opencode" ${opencode ? "selected" : ""}>OpenCode assistant — governed tools, provider sign-in or API key</option>
          <option value="builtin" ${opencode ? "" : "selected"}>Hutch built-in — direct provider chat</option>
        </select><span class="hint" id="setup-runtime-hint">OpenCode is the full assistant runtime. The built-in runtime is a lighter chat path with Hutch's own agent loop.</span></label>
        ${opencode ? `<div class="setup-open-code" role="group" aria-label="OpenCode connection">
          <button class="btn ghost small" type="button" id="setup-connect-opencode">Connect OpenCode provider</button>
          <p class="hint">Hutch uses a private OpenCode profile. It never reads your personal OpenCode session. Tools and approvals remain governed by Hutch.</p>
        </div>` : ""}
        <label class="field" for="setup-model"><span id="setup-model-label">Model route</span><input id="setup-model" list="setup-model-routes" maxlength="240" autocomplete="off" placeholder="${opencode ? "opencode/provider/model" : "Choose or enter provider/model"}" value="${esc(draft.model)}" required aria-labelledby="setup-model-label" aria-describedby="setup-model-hint">
          <datalist id="setup-model-routes">${options}</datalist>
          <span class="hint"><span id="setup-model-hint">${opencode ? (readyRoutes.length ? `${readyRoutes.length} OpenCode model route${readyRoutes.length === 1 ? "" : "s"} found in the private profile.` : "No OpenCode models are available yet. Connect a provider account, then reopen this step.") : `${modelSuggestionSource === "chat" ? `Suggested from ${esc(conversationSource.source_bot_name)}’s current route and routing mode: ${esc(conversationSource.model_suggestion)}.` : modelSuggestionSource === "duplicate" ? `Copied from ${esc(duplicateBot?.display_name || duplicateBot?.name)}; confirm it is configured in Connections.` : modelSuggestionSource === "workspace" ? `Workspace default for new Bots: ${esc(workspaceDefaults.model)}.` : modelSuggestionSource === "first_run" ? `Chosen from the AI service checked on the welcome screen: ${esc(modelSuggestion)}.` : modelSuggestionSource === "import" ? `Imported route: ${esc(modelSuggestion)}. Confirm it is configured in Connections.` : "No workspace or chat model route is configured yet."} ${readyRoutes.length ? `${readyRoutes.length} ready route${readyRoutes.length === 1 ? "" : "s"} shown as suggestions.` : "No ready routes were found. Configure a provider or local model in Connections."} Hosted routes send prompts to that provider; local routes use this machine.`}</span> ${opencode ? "" : `<a href="/#/connections" target="_blank" rel="noopener">Open Connections in another tab</a>.`}</span></label>
        <label class="field" for="setup-inference_mode"><span id="setup-inference-mode-label">Inference mode</span><select id="setup-inference_mode" aria-labelledby="setup-inference-mode-label" aria-describedby="setup-inference-mode-hint">
          <option value="hybrid" ${draft.inference_mode === "hybrid" ? "selected" : ""}>Hybrid — local or hosted</option>
          <option value="local" ${draft.inference_mode === "local" ? "selected" : ""}>Local — this machine</option>
          <option value="offline" ${draft.inference_mode === "offline" ? "selected" : ""}>Strict offline</option>
        </select><span class="hint" id="setup-inference-mode-hint">Strict offline requires a verified local route.</span></label>
        <label class="field" for="setup-workspace_mode"><span id="setup-workspace-mode-label">Workspace</span><select id="setup-workspace_mode" aria-labelledby="setup-workspace-mode-label" aria-describedby="setup-workspace-mode-hint">
          <option value="fresh" ${draft.workspace_mode === "fresh" ? "selected" : ""}>Fresh — new folder each run</option>
          <option value="managed" ${draft.workspace_mode === "managed" ? "selected" : ""}>Managed — reuse one folder</option>
        </select><span class="hint" id="setup-workspace-mode-hint">Fresh starts clean each run. Managed keeps one private folder for this assistant’s runs and chats.</span></label>
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
      <details class="setup-schedule setup-task-focus">
        <summary>Task focus (optional)</summary>
        <label class="field" for="setup-preset"><span id="setup-preset-label">Focus</span>
          <select id="setup-preset" aria-labelledby="setup-preset-label" aria-describedby="setup-preset-hint">
            <option value="" ${draft.preset ? "" : "selected"}>Standard context policy</option>
            ${taskPresets.map(preset => `<option value="${esc(preset.id)}" ${draft.preset === preset.id ? "selected" : ""}>${esc(preset.title)}</option>`).join("")}
          </select>
          <span class="hint" id="setup-preset-hint">A focus profile tunes local context sizing and residency. The selected model and tools determine actual capabilities; this never chooses a model or provider, and the route above stays explicit.</span>
        </label>
      </details>
      <details class="setup-schedule" id="setup-tools-details" ${draft.tools.size ? "open" : ""}>
        <summary>Enable tools (none enabled by default)</summary>
        ${draft.runtime === "opencode" ? `<p class="hint">File, shell, public web and memory selections below use Hutch’s governed bridge on Linux. Every tool still follows Hutch’s policy. Native computer control and unmanaged delegation remain unavailable.</p>` : ""}
        <fieldset class="setup-tool-options" id="setup-tools"><legend>Tools and permissions</legend>
          ${BOT_SETUP_TOOLS.filter(([tool]) => draft.runtime !== "opencode" || OPENCODE_TOOL_NAMES.has(tool)).map(([tool, label, help]) => `<label class="tool-option"><input type="checkbox" name="setup-tool" value="${esc(tool)}" ${draft.tools.has(tool) ? "checked" : ""}>
            <span class="tool-option-copy"><b>${esc(label)}</b><small>${esc(help)}</small></span></label>`).join("")}
        </fieldset>
        <label class="field" for="setup-memory_learning"><span id="setup-learning-label">Learning when memory is enabled</span>
          <select id="setup-memory_learning" aria-labelledby="setup-learning-label" aria-describedby="setup-learning-help">
            <option value="hybrid" ${draft.memory_learning === 'hybrid' ? 'selected' : ''}>Hybrid</option>
            <option value="review" ${draft.memory_learning !== 'hybrid' ? 'selected' : ''}>Review first</option>
          </select>
          <span class="hint" id="setup-learning-help">Hybrid saves explicit formatting preferences in their chat, with provenance and undo. Other facts still need review. Review first saves no preference automatically. Memory stays off until a memory tool is enabled above.</span>
        </label>
      </details>
      <details class="setup-schedule">
        <summary>Add a recurring task (optional)</summary>
        <div class="form-grid">
          <label class="field" for="setup-cron">Cron schedule<input id="setup-cron" maxlength="100" placeholder="0 9 * * 1" value="${esc(draft.cron)}"></label>
          <label class="field" for="setup-timezone"><span id="setup-timezone-label">Time zone</span><input id="setup-timezone" maxlength="120" placeholder="America/Vancouver" value="${esc(draft.timezone)}" aria-labelledby="setup-timezone-label" aria-describedby="setup-timezone-hint"><span class="hint" id="setup-timezone-hint">Use an IANA time zone such as UTC or America/Vancouver.</span></label>
          <label class="field" for="setup-catch_up">Missed schedule windows<select id="setup-catch_up">
            <option value="coalesce" ${draft.catch_up === "coalesce" ? "selected" : ""}>Run once when Hutch is available</option>
            <option value="skip" ${draft.catch_up === "skip" ? "selected" : ""}>Skip windows older than 30 minutes</option>
          </select></label>
          <label class="field" for="setup-schedule_prompt"><span id="setup-schedule-prompt-label">Scheduled task prompt</span><textarea id="setup-schedule_prompt" maxlength="4000" rows="3" placeholder="Leave blank to use the standing instructions" aria-labelledby="setup-schedule-prompt-label" aria-describedby="setup-schedule-prompt-hint">${esc(draft.schedule_prompt)}</textarea>
            <span class="hint" id="setup-schedule-prompt-hint">A scheduled task prompt needs a cron schedule.</span></label>
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
            <label class="field" for="setup-limit-max_cost_usd">Estimated cost per run (USD)<input type="number" id="setup-limit-max_cost_usd" min="0" step="any" value="${draft.limits.max_cost_usd}" required></label>
            <label class="field" for="setup-limit-daily_cost_cap_usd">Estimated daily cost (USD)<input type="number" id="setup-limit-daily_cost_cap_usd" min="0" step="any" value="${draft.limits.daily_cost_cap_usd}" required></label>
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
    const root = assistantSetupPage?.element;
    if (draftClosed || root !== element || !root?.isConnected) return;
    const body = $(".setup-page-body", root), title = $("#setup-page-title", root), confirm = $("#setup-page-confirm", root);
    if (!body || !title || !confirm) return;
    const sourceQuick = step === 0 && !draft.forceAdvanced && (conversationSource
      ? draft.useConversationSource : !!prefillPurpose.trim());
    title.textContent = sourceQuick ? "Create from this request" : stepTitles[step];
    const progress = step === 0 && !draft.forceAdvanced
      ? sourceQuick ? "Your request is already selected · no need to enter it again"
        : "Quick setup · safe defaults; customize anything before creating"
      : `Step ${step + 1} of ${stepTitles.length}`;
    body.innerHTML = `<div class="bot-setup"><div class="setup-progress" role="status">${progress}</div>${back}${content}<p class="setup-error" id="bot-setup-error" role="alert" hidden></p></div>`;
    element.scrollTop = 0;
    body.disabled = creating;
    $("#setup-discard-actions", root).disabled = creating;
    confirm.textContent = creating ? "Creating assistant…" : step === 3 || (step === 0 && !draft.forceAdvanced && !!draft.model.trim())
      ? "Create bot" : step === 0 && !draft.forceAdvanced ? "Choose a model" : "Continue";
    confirm.disabled = creating;
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
      if (!draft.useConversationSource) {
        draft.selectedContextMessageIds.clear();
        clearPurposeSetupProgress();
      }
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
    $$('input[name="setup-clarification-choice"]').forEach(input => input.addEventListener("change", event => {
      draft.purposeClarificationChoice = event.currentTarget.value;
      draft.purposeClarificationAnswer = $("#setup-clarification-answer")?.value || "";
      persistPurposeSetupDraft();
    }));
    $("#setup-clarification-answer")?.addEventListener("input", event => {
      draft.purposeClarificationAnswer = event.currentTarget.value;
      persistPurposeSetupDraft();
    });
    $("#setup-clarification-continue")?.addEventListener("click", () => {
      void runPurposeClarification({answerCurrentQuestion: true});
    });
    $("#setup-clarification-reset")?.addEventListener("click", () => {
      clearPurposeSetupProgress();
      void renderStep().then(() => $("#setup-refine-purpose")?.focus());
    });
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
      persistPurposeSetupDraft();
      void renderStep().then(() => $("#setup-purpose")?.focus());
    });
    $("#setup-refine-purpose")?.addEventListener("click", () => { void runPurposeClarification(); });
    refreshContextCount();
    $("#setup-display_name")?.addEventListener("input", event => {
      displayNameEdited = true;
      draft.display_name = event.currentTarget.value;
      refreshNamePreview();
      persistPurposeSetupDraft();
    });
    $("#setup-description")?.addEventListener("input", event => {
      descriptionEdited = true;
      draft.description = event.currentTarget.value;
      persistPurposeSetupDraft();
    });
    $("#setup-name")?.addEventListener("input", event => {
      addressEdited = true;
      draft.name = event.currentTarget.value;
      persistPurposeSetupDraft();
    });
    $$('input[name="setup-template"]').forEach(input => input.addEventListener("change", () => {
      draft.template = input.value;
      draft.tools = templateTools(selectedTemplate());
      draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
      if (!presetEdited) {
        draft.preset = selectedTemplate()?.preset || "";
        const preset = $("#setup-preset");
        if (preset) preset.value = draft.preset;
      }
      const toolsDetails = $("#setup-tools-details");
      if (toolsDetails && draft.tools.size) toolsDetails.open = true;
    }));
    $("#setup-preset")?.addEventListener("change", event => {
      draft.preset = event.currentTarget.value;
      presetEdited = true;
    });
    $$('input[name="setup-tool"]').forEach(input => input.addEventListener("change", () => {
      if (input.checked) draft.tools.add(input.value); else draft.tools.delete(input.value);
      draft.memory_enabled = draft.tools.has("remember") || draft.tools.has("recall");
    }));
    $("#setup-inference_mode")?.addEventListener("change", async () => {
      snapshotFields(); draft.inference_mode = $("#setup-inference_mode").value; await renderStep();
    });
    $("#setup-runtime")?.addEventListener("change", async () => {
      snapshotFields();
      draft.runtime = $("#setup-runtime").value;
      draft.model = "";
      if (draft.runtime === "opencode") {
        draft.inference_mode = "hybrid";
        draft.tools = new Set([...draft.tools].filter(tool => OPENCODE_TOOL_NAMES.has(tool)));
        draft.memory_enabled = false;
      }
      await renderStep();
    });
    $("#setup-connect-opencode")?.addEventListener("click", () => {
      snapshotFields();
      void openOpenCodeSetupDialog(status => {
        draft.runtime = "opencode";
        draft.inference_mode = "hybrid";
        draft.model = status.models?.[0]?.spec || draft.model;
        void renderStep();
      });
    });
    (step === 0 && draft.purposeClarificationQuestion ? $("#setup-clarification-question")
      : step === 0 && draft.purposeRefinement ? $("#setup-purpose-draft-review")
      : step === 0 ? (conversationSource && draft.useConversationSource && !draft.forceAdvanced
      ? $("#setup-display_name") : $("#setup-purpose")) : step === 1 ? $("#setup-model")
      : step === 3 ? title : $("input, textarea, select", body))?.focus();
    persistSetupDraft();
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
  const submitSetup = async () => {
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
      const button = $("#setup-page-confirm"); if (button) button.disabled = true;
      const actionText = button?.textContent;
      creating = true;
      if (button) button.textContent = "Creating assistant…";
      $(".setup-page-body", element).disabled = true;
      $("#setup-discard-actions", element).disabled = true;
      try {
        const key = await creationKey(body);
        const bot = await api("/v1/bots", { method: "POST", headers: { "Idempotency-Key": key }, body });
        storageRemove("hutch-pending-bot-create");
        clearFirstRunDraft();
        draftClosed = true;
        clearTimeout(persistTimer);
        if (assistantSetupPage?.element === element) clearAssistantSetupDraft();
        firstRunSelection = null;
        if (purposeSetupStorageKey) storageRemove(purposeSetupStorageKey);
        if (assistantSetupPage?.element === element) assistantSetupPage = null;
        toast(`Bot “${bot.display_name || draft.display_name}” created. It has not started a run.`);
        if (location.hash === "#/assistant/new" && generation === assistantSetupGeneration) {
          location.hash = `#/chat/${encodeURIComponent(bot.name)}`;
        }
        return true;
      } catch (err) {
        if (assistantSetupPage?.element === element && element.isConnected) setError(err.message);
        else toast(`Assistant was not created: ${err.message}`, true);
        if (button) button.disabled = false;
        return false;
      } finally {
        creating = false;
        if (!draftClosed) {
          $(".setup-page-body", element).disabled = false;
          $("#setup-discard-actions", element).disabled = false;
          if (button) button.textContent = actionText;
        }
      }
  };
  const element = document.createElement("div");
  if (location.hash !== requestedFrom || generation !== assistantSetupGeneration) return;
  element.className = "page-scroll";
  element.innerHTML = `<div class="container setup-page">
    <div class="setup-step-head"><h2 class="page-title" id="setup-page-title" tabindex="-1">New assistant</h2></div>
    ${restoredSetup ? `<p class="setup-restored" role="status">Restored your unsaved setup from this tab. Nothing has been saved or created.</p>` : ""}
    <fieldset class="setup-page-body" aria-labelledby="setup-page-title"></fieldset>
    <div class="setup-page-actions">
      <button class="btn ghost" id="setup-discard-actions" type="button">Discard draft</button>
      <a class="btn ghost" href="${esc(returnRoute)}" id="setup-save-leave">Save draft and leave</a>
      <button class="btn primary" id="setup-page-confirm" type="button">Continue</button>
    </div>
  </div>`;
  let submitting = false;
  assistantSetupPage?.close();
  assistantSetupPage = {
    element, render: renderStep, snapshot: snapshotFields, persist: persistSetupDraft,
    isSubmitting: () => submitting,
    close: () => {
      draftClosed = true;
      clearTimeout(persistTimer);
      if (purposeSetupStorageKey) storageRemove(purposeSetupStorageKey);
    },
  };
  $("#setup-page-confirm", element).addEventListener("click", async () => {
    if (submitting) return;
    submitting = true;
    try { await submitSetup(); }
    finally { submitting = false; }
  });
  const discardDraft = () => {
    if (submitting) return;
    draftClosed = true;
    clearTimeout(persistTimer);
    clearAssistantSetupDraft();
    if (purposeSetupStorageKey) storageRemove(purposeSetupStorageKey);
    assistantSetupPage = null;
    location.hash = returnRoute.startsWith("#") ? returnRoute : "#/chat";
  };
  $("#setup-discard-actions", element)?.addEventListener("click", discardDraft);
  const schedulePersist = () => {
    clearTimeout(persistTimer);
    persistTimer = setTimeout(persistSetupDraft, 250);
  };
  element.addEventListener("input", schedulePersist);
  element.addEventListener("change", schedulePersist);
  element.addEventListener("click", event => {
    if (event.target.closest("#setup-save-leave")) persistSetupDraft();
  });
  persistSetupDraft();
  if (location.hash !== "#/assistant/new") location.hash = "#/assistant/new";
  else await renderAssistantSetupPage();
}

/* ----------------------------------------------------------- shared wire */

function wireCommon() {
  $$('[data-action="toggle-pause"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      const bot = btn.dataset.bot;
      const paused = btn.dataset.paused !== "true";
      const actionRoute = location.hash;
      btn.disabled = true;
      try {
        await api(`/bots/${encodeURIComponent(bot)}`, { method: "PATCH", body: { paused } });
        toast(paused ? "Paused" : "Resumed");
        if (location.hash === actionRoute && btn.isConnected) await route();
        await refreshRoster();
      } catch (error) {
        btn.disabled = false;
        toast(`Could not update this assistant: ${error.message}`, true);
      }
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
    if ((location.hash || "#/chat") === "#/overview"
        && ["bots", "runs", "approvals", "actions", "state", "usage"].some(r => changed.has(r))) {
      void renderOverview(true);
    }
    if (["workspace", "bots"].some(resource => changed.has(resource)) && (location.hash || "#/chat") === "#/schedules") {
      void renderSchedules();
    }
    if (["messages", "conversations", "runs", "approvals", "actions", "transcript_mirrors", "memory", "workspace_tasks", "code_handoffs"].some(r => changed.has(r))) {
      const visibleHash = location.hash || "#/chat";
      if (isConversationView(visibleHash) || /^#\/run\/[\w-]+$/.test(visibleHash)) scheduleFeedRender();
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
    // The route already loaded its visible resource from the same authoritative
    // endpoints. Reconcile the shared shell directly here so startup does not
    // repaint a form/detail page just after it becomes interactive.
    void refreshRoster();
    void refreshBadge();
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
let phoneModel = { bots: [], runs: [], approvals: [], workflows: [], workflowQuestions: [],
  selectedRun: null, selectedWorkflow: null, tab: "status", notice: "", offline: false };
let phonePoll = null;
let phoneChangeStream = null;
let phoneRunStream = null;
let phoneRunStreamId = null;
let phoneExpiryTimer = null;
let phoneRefreshInFlight = false;
let phoneRefreshQueued = false;
let phoneRefreshQueuedQuiet = true;
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

function phoneCommandIsAllowed(command) {
  const required = command?.path === "/v1/tasks/runs" ? "start" : "review";
  return (hutchSession?.capabilities || []).includes(required);
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
  if (!phoneRoot || document.hidden) return;
  if (phoneRefreshInFlight) {
    phoneRefreshQueued = true;
    phoneRefreshQueuedQuiet = phoneRefreshQueuedQuiet && quiet;
    return;
  }
  phoneRefreshInFlight = true;
  try {
    const freshSession = await api("/v1/session");
    if (freshSession.principal !== "paired") { lockExpiredPhone(); return; }
    hutchSession = freshSession;
    hutchCsrfToken = freshSession.csrf_token || "";
    phoneSetSessionExpiry(freshSession.idle_expires_at, freshSession.absolute_expires_at);
    const capabilities = new Set(hutchSession?.capabilities || []);
    if (!capabilities.has("review")) {
      phoneModel.approvals = [];
      phoneModel.workflowQuestions = [];
      if (phoneModel.tab === "review") phoneModel.tab = "status";
    }
    const requests = [api("/bots"), api("/v1/tasks/runs?limit=40"),
      api("/v1/phone/workflows/runs?limit=40")];
    if (capabilities.has("review")) {
      requests.push(api("/v1/actions/approvals?status=pending&limit=100"));
      requests.push(api("/v1/phone/workflows/questions?limit=100"));
    }
    const [bots, runs, workflows, approvalsPage, questionsPage] = await Promise.all(requests);
    phoneModel.bots = bots;
    phoneModel.runs = runs;
    phoneModel.workflows = workflows.items || [];
    phoneModel.approvals = approvalsPage || [];
    phoneModel.workflowQuestions = questionsPage?.items || [];
    const selectedRunId = phoneModel.selectedRun?.id;
    if (selectedRunId) {
      try {
        const selectedRun = await api(`/v1/tasks/runs/${encodeURIComponent(selectedRunId)}`);
        if (phoneModel.selectedRun?.id === selectedRunId) phoneModel.selectedRun = selectedRun;
      }
      catch (error) {
        if (error.status !== 404) throw error;
        if (phoneModel.selectedRun?.id === selectedRunId) phoneModel.selectedRun = null;
      }
    }
    const selectedWorkflowId = phoneModel.selectedWorkflow?.id;
    if (selectedWorkflowId) {
      try {
        const selectedWorkflow = await api(`/v1/phone/workflows/runs/${encodeURIComponent(selectedWorkflowId)}`);
        if (phoneModel.selectedWorkflow?.id === selectedWorkflowId) phoneModel.selectedWorkflow = selectedWorkflow;
      }
      catch (error) {
        if (error.status !== 404) throw error;
        if (phoneModel.selectedWorkflow?.id === selectedWorkflowId) phoneModel.selectedWorkflow = null;
      }
    }
    phoneModel.offline = false;
    if (!quiet) phoneModel.notice = "";
    phoneRender();
    phoneAttachRunStream();
  } catch (error) {
    if (!phoneRoot) return;
    if (error.status === 403) {
      phoneModel.approvals = [];
      phoneModel.workflowQuestions = [];
      if (!(hutchSession?.capabilities || []).includes("review")) phoneModel.tab = "status";
    }
    phoneModel.offline = true;
    if (!quiet) phoneModel.notice = `Could not refresh Hutch: ${error.message}. Displayed status may be out of date.`;
    phoneRender();
  } finally {
    phoneRefreshInFlight = false;
    if (phoneRefreshQueued) {
      const queuedQuiet = phoneRefreshQueuedQuiet;
      phoneRefreshQueued = false;
      phoneRefreshQueuedQuiet = true;
      if (phoneRoot && !document.hidden) queueMicrotask(() => void phoneRefresh({ quiet: queuedQuiet }));
    }
  }
}

function phoneRender() {
  if (!phoneRoot) return;
  const pending = phonePendingCommand;
  const bots = phoneModel.bots || [];
  const runs = phoneModel.runs || [];
  const approvals = phoneModel.approvals || [];
  const workflows = phoneModel.workflows || [];
  const workflowQuestions = phoneModel.workflowQuestions || [];
  const canReview = (hutchSession?.capabilities || []).includes("review");
  const canStart = (hutchSession?.capabilities || []).includes("start");
  const active = new Set(["pending", "loading_model", "running", "waiting_approval", "waiting_human",
    "waiting_resources", "waiting_child", "recovering", "cancelling"]);
  const activeWorkflow = new Set(["pending", "running", "waiting"]);
  const selected = phoneModel.selectedRun;
  const selectedWorkflow = phoneModel.selectedWorkflow;
  const phoneTimestamp = (value) => {
    if (!value) return "time unavailable";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "time unavailable" : date.toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
    });
  };
  let body = "";

  if (phoneModel.tab === "review") {
    const questionCards = workflowQuestions.map(q => `<article class="phone-card phone-question-card">
      <div class="phone-card-head"><span class="phone-status needs">Needs your answer</span><span>${esc(q.bot_display_name || "Assistant")}</span></div>
      <h2 id="phone-question-title-${esc(q.id)}">${esc(workflowDisplayTitle(q.workflow_title || "Workflow"))}</h2><p class="phone-sub" id="phone-question-id-${esc(q.id)}">Step ${esc(q.site_id)} · Question ID <code>${esc(q.id)}</code></p>
      <p class="phone-question-prompt" id="phone-question-prompt-${esc(q.id)}">${esc(q.question)}</p>
      <form class="phone-workflow-answer-form" data-question-id="${esc(q.id)}" aria-labelledby="phone-question-title-${esc(q.id)} phone-question-id-${esc(q.id)} phone-question-prompt-${esc(q.id)}">
        ${q.options?.length ? `<label id="phone-question-answer-label-${esc(q.id)}" for="phone-question-answer-${esc(q.id)}">Answer<select id="phone-question-answer-${esc(q.id)}" name="answer" required aria-labelledby="phone-question-title-${esc(q.id)} phone-question-id-${esc(q.id)} phone-question-prompt-${esc(q.id)} phone-question-answer-label-${esc(q.id)}" aria-describedby="phone-question-help-${esc(q.id)}"><option value="">Choose an answer</option>${q.options.map(option => `<option value="${esc(option)}">${esc(option)}</option>`).join("")}</select></label>` : `<label id="phone-question-answer-label-${esc(q.id)}" for="phone-question-answer-${esc(q.id)}">Your answer<textarea id="phone-question-answer-${esc(q.id)}" name="answer" rows="3" maxlength="4000" required aria-labelledby="phone-question-title-${esc(q.id)} phone-question-id-${esc(q.id)} phone-question-prompt-${esc(q.id)} phone-question-answer-label-${esc(q.id)}" aria-describedby="phone-question-help-${esc(q.id)}"></textarea></label>`}
        <button class="btn primary" type="submit" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Send answer</button>
      </form><p class="phone-sub" id="phone-question-help-${esc(q.id)}">Answering this resolves only this question. It does not approve a separate action.</p><p class="phone-sub">Expires ${esc(phoneTimestamp(q.expires_at))}</p>
    </article>`).join("");
    const approvalCards = approvals.map(a => {
      const id = a.approval_id || a.id;
      const detail = JSON.stringify(a.detail || {}, null, 2);
      return `<article class="phone-card approval-card"><div class="phone-card-head"><span class="phone-status needs">Needs review</span><span>${esc(a.bot_display_name || a.bot_name || "Bot")}</span></div>
        <h2 id="phone-approval-action-${esc(id)}">${esc(a.action || "Requested action")}</h2><p class="phone-sub" id="phone-approval-id-${esc(id)}">Approval ID <code>${esc(id)}</code></p><p class="phone-sub">${esc(a.tool || "Action")} · ${esc(a.risk || "risk unavailable")}${a.outward ? " · sends data outside this machine" : ""}</p>
        <details><summary>Review exact request</summary><pre>${esc(detail)}</pre>${a.rule ? `<p>${esc(a.rule)}</p>` : ""}</details>
        <div class="phone-actions"><button class="btn primary" type="button" data-phone-approve="${esc(id)}" data-action-hash="${esc(a.action_hash || "")}" aria-describedby="phone-approval-action-${esc(id)} phone-approval-id-${esc(id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Allow once</button><button class="btn danger" type="button" data-phone-deny="${esc(id)}" aria-describedby="phone-approval-action-${esc(id)} phone-approval-id-${esc(id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Deny</button></div>
      </article>`;
    }).join("");
    body = questionCards || approvalCards
      ? `<section class="phone-list" aria-label="Needs you">${questionCards}${approvalCards}</section>`
      : `<section class="phone-empty"><h2>Nothing needs review</h2><p>Pending workflow questions and action requests will appear here.</p></section>`;
  } else if (phoneModel.tab === "workflows" && selectedWorkflow) {
    const nodes = selectedWorkflow.nodes || [];
    const plannedSteps = selectedWorkflow.planned_steps || [];
    body = `<section class="phone-workflow-detail"><button class="btn ghost" type="button" data-phone-workflow-back>All workflows</button>
      <article class="phone-card phone-workflow-heading"><div class="phone-card-head"><span class="phone-status ${selectedWorkflow.needs_you ? "needs" : ""}">${esc(selectedWorkflow.pause_requested ? (selectedWorkflow.pause_ready ? "Paused" : "Pause requested") : selectedWorkflow.status)}${selectedWorkflow.stop_requested ? " · stop requested" : ""}</span><span>${esc(selectedWorkflow.bot_display_name || "Assistant")}</span></div>
      <h1>${esc(workflowDisplayTitle(selectedWorkflow.title || "Workflow"))}</h1><p class="phone-sub">${plannedSteps.length} planned · ${nodes.length} recorded instance${nodes.length === 1 ? "" : "s"} · updated ${esc(phoneTimestamp(selectedWorkflow.updated_at))}</p>
      ${canReview && activeWorkflow.has(selectedWorkflow.status) && !selectedWorkflow.stop_requested ? `<button class="btn danger" type="button" data-phone-workflow-stop="${esc(selectedWorkflow.id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Stop workflow</button>` : ""}</article>
      <h2 class="phone-section-title">Planned steps</h2>
      ${plannedSteps.length ? `<ol class="phone-workflow-steps phone-planned-steps">${plannedSteps.map(step => `<li data-depth="${Math.min(5, Math.max(0, Number(step.depth) || 0))}"><span class="phone-step-status">planned</span><span class="phone-step-title">${esc(step.site_id)}</span><span class="phone-sub">${esc(step.kind)}${step.bounded ? " · bounded group" : ""}</span></li>`).join("")}</ol>` : `<p class="phone-empty">No plan steps are available.</p>`}
      <h2 class="phone-section-title">Recorded instances</h2>
      ${nodes.length ? `<ol class="phone-workflow-steps">${nodes.map(node => `<li><span class="phone-step-status">${esc(node.status)}</span><span class="phone-step-title">${esc(node.site_id)}${node.instance_number > 1 ? ` · instance ${Number(node.instance_number)}` : ""}</span><span class="phone-sub">${esc(node.kind)}</span></li>`).join("")}</ol>` : `<p class="phone-empty">No discovered instances have been recorded yet.</p>`}
      ${selectedWorkflow.needs_you ? `<p class="phone-sub">${selectedWorkflow.needs_you} pending question${selectedWorkflow.needs_you === 1 ? "" : "s"}. Open Review to answer by question ID.</p>` : ""}
      <p class="phone-sub">Step names and status only. Results, inputs, artifacts and usage details stay on the local owner view.</p></section>`;
  } else if (phoneModel.tab === "workflows") {
    body = workflows.length ? `<section class="phone-list" aria-label="Workflows">${workflows.map(workflow => `<button class="phone-card phone-workflow-card" type="button" data-phone-workflow="${esc(workflow.id)}"><span class="phone-card-head"><span class="phone-status ${workflow.needs_you ? "needs" : ""}">${esc(workflow.pause_requested ? (workflow.pause_ready ? "Paused" : "Pause requested") : workflow.status)}${workflow.stop_requested ? " · stop requested" : ""}</span><span>${esc(workflow.bot_display_name || "Assistant")}</span></span><strong>${esc(workflowDisplayTitle(workflow.title || "Workflow"))}</strong><span class="phone-sub">${Number(workflow.planned_step_count) || 0} planned · ${Number(workflow.step_count) || 0} instances · ${workflow.needs_you ? `${Number(workflow.needs_you)} need you · ` : ""}${esc(phoneTimestamp(workflow.updated_at))}</span></button>`).join("")}</section>` : `<section class="phone-empty"><h2>No workflow runs yet</h2><p>Workflows launched on the local Hutch host will appear here.</p></section>`;
  } else if (phoneModel.tab === "runs" && selected) {
    const events = selected.events || [];
    body = `<section class="phone-run-detail"><button class="btn ghost" type="button" data-phone-back><svg class="ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg> All runs</button>
      <article class="phone-card"><div class="phone-card-head"><span class="phone-status">${esc(selected.status_label || selected.status)}</span><span>${esc(selected.bot_display_name || selected.bot_name || "Bot")}</span></div>
      <h1>${esc(selected.prompt || (selected.image_attachment_count ? `${selected.image_attachment_count} image${selected.image_attachment_count === 1 ? "" : "s"} attached` : "Run"))}</h1><p class="phone-sub">Started ${esc(phoneTimestamp(selected.created_at))}${selected.image_attachment_count ? ` · ${selected.image_attachment_count} image${selected.image_attachment_count === 1 ? "" : "s"} attached` : ""}</p>
      ${canReview && active.has(selected.status) ? `<button class="btn danger" type="button" data-phone-stop="${esc(selected.id)}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Stop run</button>` : ""}
      ${canReview && selected.status === "waiting_human" ? (() => { const wait = [...events].reverse().find(e => e.type === "human_needed"); return wait ? `<button class="btn primary" type="button" data-phone-resume="${esc(selected.id)}" data-human-seq="${Number(wait.seq) || 0}" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Resume after completing the requested step</button>` : ""; })() : ""}
      </article><h2 class="phone-section-title">Progress</h2>
      ${events.length ? `<ol class="phone-transcript">${events.map(e => {
        const d = e.data || {};
        const statusLabel = typeof d.status === "string"
          ? (statusInfo[d.status]?.label || d.status.replaceAll("_", " ")) : null;
        const content = e.type === "status" && statusLabel
          ? statusLabel : (d.content ?? d.text ?? d.command ?? d.message ?? JSON.stringify(d, null, 2));
        const prose = e.type === "message" && (typeof d.content === "string" || typeof d.text === "string");
        return `<li><span>${esc(String(e.type || "event").replaceAll("_", " "))} · ${esc(phoneTimestamp(e.ts))}</span><pre${prose ? ' class="phone-prose"' : ""}>${esc(String(content).slice(0, 6000))}${String(content).length > 6000 ? "\\n… clipped for phone display" : ""}</pre></li>`;
      }).join("")}</ol>` : `<p class="phone-empty">No transcript events have arrived yet.</p>`}
      ${selected.events_truncated ? `<p class="phone-sub">Showing the latest transcript window. Open Hutch on its host to inspect older history.</p>` : ""}</section>`;
  } else if (phoneModel.tab === "runs") {
    body = runs.length ? `<section class="phone-list" aria-label="Runs">${runs.map(run => `<button class="phone-card phone-run-card" type="button" data-phone-run="${esc(run.id)}"><span class="phone-card-head"><span class="phone-status ${run.needs_person ? "needs" : ""}">${esc(run.status_label || run.status)}</span><span>${esc(run.bot_display_name || run.bot_name || "Bot")}</span></span><strong>${esc(run.prompt || (run.image_attachment_count ? `${run.image_attachment_count} image${run.image_attachment_count === 1 ? "" : "s"} attached` : "Run"))}</strong><span class="phone-sub">${esc(phoneTimestamp(run.created_at))}</span></button>`).join("")}</section>` : `<section class="phone-empty"><h2>No runs yet</h2><p>Runs started locally or from a paired device will appear here.</p></section>`;
  } else {
    const running = runs.filter(run => active.has(run.status));
    const candidates = canStart ? bots.filter(bot => bot.remote_start_enabled) : [];
    const startUnavailable = canStart
      ? `No Bot is enabled for phone starts. A local owner can enable one with <code>hutch bot update NAME --remote-start</code>.`
      : `This paired session is ${canReview ? "monitor and review" : "monitor"} only. Starting work is unavailable.`;
    body = `<section class="phone-summary"><div><strong>${running.length}</strong><span>in progress</span></div><div><strong>${approvals.length + workflowQuestions.length}</strong><span>need review</span></div><div><strong>${workflows.length}</strong><span>workflows</span></div></section>
      <section><h2 class="phone-section-title">Bots</h2>${bots.length ? `<div class="phone-list">${bots.map(bot => `<article class="phone-card"><div class="phone-card-head"><strong>${esc(bot.display_name || bot.name)}</strong><span class="phone-status ${bot.paused ? "needs" : ""}">${bot.paused ? "Paused" : esc(bot.active_run_status_label || "Ready")}</span></div><p class="phone-sub">${esc(bot.description || "")}</p>${bot.paused ? `<span class="phone-sub">Scheduled tasks are paused</span>` : ""}${canStart && bot.remote_start_enabled ? `<span class="phone-sub">Phone starts enabled by the local owner</span>` : canReview ? `<span class="phone-sub">Monitor and review only</span>` : `<span class="phone-sub">Monitor only</span>`}</article>`).join("")}</div>` : `<p class="phone-empty">No Bots are configured.</p>`}</section>
      <section><h2 class="phone-section-title">Start work</h2>${candidates.length ? `<form class="phone-card phone-start-form" id="phone-start-form"><label>Bot<select name="bot" required>${candidates.map(bot => `<option value="${esc(bot.name)}">${esc(bot.display_name || bot.name)}${bot.paused ? " · scheduled tasks paused" : ""}</option>`).join("")}</select></label><label>What should this Bot do?<textarea name="prompt" rows="4" maxlength="20000" required placeholder="Describe the task"></textarea></label><p class="phone-sub">Uses the Bot’s locally configured model, tools, workspace and approval policy. Starting work here creates an on-demand run; pausing a Bot only pauses its scheduled tasks.</p><button class="btn primary" type="submit" ${pending || phoneUnresolvedCommand ? "disabled" : ""}>Start work</button></form>` : `<p class="phone-empty">${startUnavailable}</p>`}</section>
      <section><h2 class="phone-section-title">Recent runs</h2>${runs.slice(0, 8).map(run => `<button class="phone-card phone-run-card" type="button" data-phone-run="${esc(run.id)}"><span class="phone-card-head"><span class="phone-status ${run.needs_person ? "needs" : ""}">${esc(run.status_label || run.status)}</span><span>${esc(run.bot_display_name || run.bot_name || "Bot")}</span></span><strong>${esc(run.prompt || (run.image_attachment_count ? `${run.image_attachment_count} image${run.image_attachment_count === 1 ? "" : "s"} attached` : "Run"))}</strong></button>`).join("") || `<p class="phone-empty">No runs to show yet.</p>`}</section>`;
  }

  phoneRoot.innerHTML = `<header class="phone-header"><a href="/" class="phone-brand" aria-label="Hutch home">hutch <span>supervision</span></a><div class="phone-header-actions"><span class="phone-connection ${phoneModel.offline ? "offline" : ""}" role="status">${phoneModel.offline ? "Reconnect needed" : "Connected"}</span><button class="btn ghost small" type="button" data-phone-refresh>Refresh</button><button class="btn ghost small" type="button" data-phone-logout>Lock</button></div></header>
    <nav class="phone-tabs ${canReview ? "has-review" : "monitor-only"}" aria-label="Phone supervision"><button type="button" data-phone-tab="status" aria-current="${phoneModel.tab === "status" ? "page" : "false"}">Status</button><button type="button" data-phone-tab="workflows" aria-current="${phoneModel.tab === "workflows" ? "page" : "false"}">Workflows${workflowQuestions.length ? ` <span>${workflowQuestions.length}</span>` : ""}</button>${canReview ? `<button type="button" data-phone-tab="review" aria-current="${phoneModel.tab === "review" ? "page" : "false"}">Review${approvals.length + workflowQuestions.length ? ` <span>${approvals.length + workflowQuestions.length}</span>` : ""}</button>` : ""}<button type="button" data-phone-tab="runs" aria-current="${phoneModel.tab === "runs" ? "page" : "false"}">Runs</button></nav>
    <main class="phone-content">${phonePendingCommandMarkup()}${phoneUnresolvedCommand ? `<aside class="phone-retry" role="alert"><strong>A prior phone command is unresolved.</strong><p>${esc(phoneUnresolvedCommand.label)} used another paired credential. Check current runs and approvals on the host before issuing another command from this device.</p><button class="btn ghost" type="button" data-phone-clear-foreign>I've checked the current state</button></aside>` : ""}${phoneModel.notice ? `<p class="phone-notice" role="status">${esc(phoneModel.notice)}</p>` : ""}${body}</main>`;
}

function phonePendingCommandMarkup() {
  const pending = phonePendingCommand;
  if (!pending) return "";
  if (!phoneCommandIsAllowed(pending)) {
    return `<aside class="phone-retry" role="alert"><strong>${esc(pending.label)} may not have been confirmed.</strong><p>This session no longer has permission to retry it. Reconcile the current state on the Hutch host first.</p><button class="btn ghost" type="button" data-phone-clear-pending>Clear saved command</button></aside>`;
  }
  return `<aside class="phone-retry" role="alert"><strong>${esc(pending.label)} may not have been confirmed.</strong><p>Check the current run or approval state. Hutch will only resend if you choose Retry, using the same idempotency key.</p><div class="phone-actions"><button class="btn primary" type="button" data-phone-retry>Retry same request</button><button class="btn ghost" type="button" data-phone-clear-pending>Clear retry</button></div></aside>`;
}

function phoneAttachRunStream() {
  const run = phoneModel.selectedRun;
  if (!phoneRoot || !run || !["pending", "loading_model", "running", "waiting_approval", "waiting_human", "waiting_resources", "waiting_child", "recovering", "cancelling"].includes(run.status)) {
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
  if (!phoneCommandIsAllowed(request)) {
    phoneModel.notice = `${label} is not available to this paired session.`;
    phoneRender();
    return;
  }
  phonePendingCommand = request;
  phoneSavePendingCommand();
  await phoneAttemptPending();
}

async function phoneAttemptPending() {
  const command = phonePendingCommand;
  if (!command || !phoneRoot) return;
  if (!phoneCommandIsAllowed(command)) {
    phoneModel.notice = `${command.label} may have been sent, but this session no longer has permission to retry it. Reconcile the current state on the Hutch host first.`;
    phoneRender();
    return;
  }
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
  } else if (button.dataset.phoneTab) {
    const requestedTab = button.dataset.phoneTab;
    if (requestedTab === "review" && !(hutchSession?.capabilities || []).includes("review")) return;
    phoneModel.tab = requestedTab; phoneModel.selectedRun = null; phoneModel.selectedWorkflow = null;
    phoneRender(); phoneAttachRunStream();
  }
  else if (button.dataset.phoneRun) {
    const id = button.dataset.phoneRun;
    void api(`/v1/tasks/runs/${encodeURIComponent(id)}`).then(run => {
      phoneModel.selectedRun = run; phoneModel.tab = "runs"; phoneRender(); phoneAttachRunStream();
    }).catch(error => { if (phoneRoot) { phoneModel.notice = `Could not load run: ${error.message}`; phoneRender(); } });
  } else if (button.hasAttribute("data-phone-back")) { phoneModel.selectedRun = null; phoneRender(); }
  else if (button.dataset.phoneWorkflow) {
    const id = button.dataset.phoneWorkflow;
    void api(`/v1/phone/workflows/runs/${encodeURIComponent(id)}`).then(workflow => {
      phoneModel.selectedWorkflow = workflow; phoneModel.selectedRun = null; phoneModel.tab = "workflows";
      phoneRender(); phoneAttachRunStream();
    }).catch(error => { if (phoneRoot) { phoneModel.notice = `Could not load workflow: ${error.message}`; phoneRender(); } });
  } else if (button.hasAttribute("data-phone-workflow-back")) { phoneModel.selectedWorkflow = null; phoneRender(); }
  else if (button.dataset.phoneWorkflowStop) {
    const workflow = phoneModel.selectedWorkflow;
    if (workflow?.id === button.dataset.phoneWorkflowStop && workflow.revision_id && (hutchSession?.capabilities || []).includes("review")) {
      void phoneQueueCommand("Stop workflow", `/v1/phone/workflows/runs/${encodeURIComponent(workflow.id)}/stop`,
        { expected_revision_id: workflow.revision_id });
    }
  }
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
  const answerForm = event.target.closest(".phone-workflow-answer-form");
  if (answerForm && phoneRoot?.contains(answerForm)) {
    event.preventDefault();
    if (phonePendingCommand || phoneUnresolvedCommand || !(hutchSession?.capabilities || []).includes("review")) return;
    const answer = String(new FormData(answerForm).get("answer") || "").trim();
    const questionId = answerForm.dataset.questionId;
    if (!answer || !questionId) { phoneModel.notice = "Choose or enter an answer before sending it."; phoneRender(); return; }
    void phoneQueueCommand("Answer workflow question", `/v1/phone/workflows/questions/${encodeURIComponent(questionId)}/answer`, { answer });
    return;
  }
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

let shellBadgeTimer = null, shellRosterTimer = null, shellHealthTimer = null;

function armShellTimers() {
  clearInterval(shellBadgeTimer);
  clearInterval(shellRosterTimer);
  clearInterval(shellHealthTimer);
  shellBadgeTimer = setInterval(() => { if (!document.hidden) void refreshBadge(); }, 6000);
  shellRosterTimer = setInterval(() => { if (!document.hidden) void refreshRoster(); }, 20000);
  shellHealthTimer = setInterval(() => { if (!document.hidden) void pollHealth(); }, HEARTBEAT_MS);
}

function startOwnerApp() {
  $("#topbar-new-bot")?.addEventListener("click", () => void promptNewBot());
  route();
  void loadStatusInfo();
  void refreshRoster();
  void startResourceStream();
  void pollHealth();
  armShellTimers();
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
    if (needsYouDialog.open) scheduleApprovalsPoll();
  } else {
    clearTimeout(approvalsTimer);
    approvalsTimer = null;
  }
});

/* ------------------------------------------- documents (generated, committed) */

const DOCUMENT_FORMAT_LABELS = {
  pdf: "PDF", docx: "DOCX", xlsx: "XLSX", pptx: "PPTX",
  md: "MD", txt: "TXT", csv: "CSV", json: "JSON", yaml: "YAML", zip: "ZIP",
};

/* Only committed documents with a well-formed id and version get a card; the
   download URL is built here from validated parts, never taken from event data. */
function validDocumentRef(ref) {
  if (!ref || typeof ref !== "object") return null;
  const id = typeof ref.id === "string" ? ref.id : "";
  const version = Number(ref.version);
  if (!/^doc_[0-9a-f]{16}$/.test(id) || !Number.isInteger(version) || version < 1 || version > 999) return null;
  const bytes = Number(ref.bytes);
  return {
    id, version,
    name: String(ref.name || "document"),
    title: String(ref.title || ref.name || "Document"),
    format: String(ref.format || ""),
    formatLabel: DOCUMENT_FORMAT_LABELS[ref.format] || String(ref.format || "?").toUpperCase(),
    bytes: Number.isSafeInteger(bytes) && bytes >= 0 ? bytes : null,
    validationState: String(ref.validation_state || "passed"),
    findings: Array.isArray(ref.validation_findings) ? ref.validation_findings : [],
    previewMode: String(ref.preview_mode || "download_only"),
    created_at: typeof ref.created_at === "string" ? ref.created_at : "",
  };
}

function documentListRowRef(row) {
  if (!row || typeof row !== "object") return null;
  const v = typeof row.version === "object" && row.version ? row.version : null;
  return validDocumentRef({
    id: row.id, version: v ? v.version : row.current_version,
    name: (v && v.filename) || row.title, title: row.title,
    format: row.format, bytes: v ? v.size_bytes : null,
    validation_state: v ? v.validation_state : "passed",
    preview_mode: v ? v.preview_mode : "download_only",
    created_at: row.created_at || (v && v.created_at) || "",
  });
}

function documentDownloadUrl(ref) {
  return `/api/v1/documents/${ref.id}/versions/${ref.version}/download`;
}

function documentStateHtml(ref) {
  if (ref.validationState === "passed") return `${icon("check")} Verified`;
  if (ref.validationState === "passed_with_warnings") {
    return `${icon("eye")} Validated · ${ref.findings.length || "notes"}`;
  }
  return `${icon("alert")} Validation failed`;
}

function documentCardHtml(ref) {
  const failed = ref.validationState === "failed";
  const download = failed ? "" :
    `<a class="btn ghost small" href="${documentDownloadUrl(ref)}" aria-label="Download ${esc(ref.name)}">Download</a>`;
  return `<article class="document-card conversation-file" data-document-card="${esc(ref.id)}">
    <div class="conversation-file-main">
      ${icon("fileText")}
      <div class="conversation-file-copy">
        <strong title="${esc(ref.name)}">${esc(ref.name)}</strong>
        <span><span class="document-format">${esc(ref.formatLabel)}</span> · v${ref.version}${ref.bytes ? ` · ${conversationArtifactSize(ref.bytes)}` : ""} · ${timeAgo(ref.created_at || "")}</span>
        <span class="conversation-file-state">${documentStateHtml(ref)}</span>
      </div>
      <div class="conversation-file-actions">
        <button class="btn ghost small" type="button" data-doc-preview="${esc(ref.id)}"
          data-doc-version="${ref.version}" data-doc-name="${esc(ref.name)}"
          aria-label="Preview ${esc(ref.name)}">Preview</button>
        <button class="btn ghost small" type="button" data-doc-versions="${esc(ref.id)}"
          data-doc-name="${esc(ref.name)}" aria-label="Version history for ${esc(ref.name)}">Versions</button>
        ${download}
      </div>
    </div>
  </article>`;
}

function documentAttachmentHtml(ref) {
  const failed = ref.validationState === "failed";
  const download = failed ? "" :
    ` <a class="btn ghost small" href="${documentDownloadUrl(ref)}" title="The server verifies this file against its recorded SHA-256 before download">Download ${esc(ref.name)}</a>`;
  return `<div class="workspace-file-attachment document-attachment">
    <span class="workspace-file-label"><span class="document-format">${esc(ref.formatLabel)}</span> Document</span>
    <button class="btn ghost small" type="button" data-doc-preview="${esc(ref.id)}"
      data-doc-version="${ref.version}" data-doc-name="${esc(ref.name)}"
      aria-label="Preview ${esc(ref.name)}">Preview</button>
    <button class="btn ghost small" type="button" data-doc-versions="${esc(ref.id)}"
      data-doc-name="${esc(ref.name)}" aria-label="Version history for ${esc(ref.name)}">Versions</button>
    ${download}
    <span class="workspace-file-meta">v${ref.version}${ref.bytes ? ` · ${conversationArtifactSize(ref.bytes)}` : ""} · ${documentStateHtml(ref)}</span>
  </div>`;
}

function documentPreviewBodyHtml(data) {
  const note = (extra) => `<p class="hint">${esc(extra)}</p>`;
  if (data.mode === "pages") {
    const total = Number(data.rendered_pages || 0);
    if (!total) {
      return note("No rendered page images are available for this version. The exact file is unchanged and ready to download.");
    }
    const base = String(data.pages_url || "");
    return note("Rendered page images — an approximate render of the exact stored file.") +
      `<div class="document-pages">${Array.from({ length: Math.min(total, 60) }, (_, i) =>
        `<img loading="lazy" src="${esc(base)}${i + 1}.png" alt="Page ${i + 1} of ${total} — approximate render">`).join("")}</div>`;
  }
  if (data.mode === "structure" && typeof data.text === "string") {
    const clipped = data.text_truncated ? note("Preview truncated; the download contains the full text.") : "";
    return clipped + `<pre class="document-preview-text">${esc(data.text)}</pre>`;
  }
  if (data.mode === "structure" && data.kind === "outline") {
    const items = (data.items || []).map(item =>
      `<li class="document-outline-${esc(item.level || "p")}">${esc(item.text || "")}</li>`).join("");
    return note("Extracted structure — not the rendered layout.") + `<ul class="document-outline">${items}</ul>`;
  }
  if (data.mode === "structure" && data.kind === "grid") {
    const sheets = (data.sheets || []).map(sheet => {
      const head = (sheet.sample || [])[0] || [];
      const rows = (sheet.sample || []).slice(1);
      return `<h4>${esc(sheet.name || "Sheet")}</h4>
        <table class="document-grid"><thead><tr>${head.map(cell => `<th>${esc(String(cell ?? ""))}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${esc(String(cell ?? ""))}</td>`).join("")}</tr>`).join("")}</tbody></table>
        <p class="hint">${Number(sheet.rows || 0).toLocaleString("en-US")} rows total (sample shows the first ${Math.max((sheet.sample || []).length - 1, 0)}); values as stored, without formatting.</p>`;
    }).join("");
    return note("Extracted sheet values — not the rendered workbook.") + sheets;
  }
  if (data.mode === "structure" && data.kind === "slides") {
    const slides = (data.items || []).map((slide, i) =>
      `<li class="document-slide"><strong>Slide ${i + 1}: ${esc(slide.title || "(untitled)")}</strong>
        <span>${Number(slide.bullet_count || 0)} bullet(s)${slide.has_table ? " · table" : ""}${slide.has_notes ? " · notes" : ""}</span></li>`).join("");
    return note("Slide outline — not the rendered deck.") + `<ul class="document-outline">${slides}</ul>`;
  }
  return note("This version has no in-app preview. The exact file is ready to download; layout previews for office documents become available when LibreOffice is installed on the Hutch host.");
}

async function openDocumentPreview(docId, version, docName, returnFocus) {
  openModal({
    title: `Preview — ${docName || "document"}`,
    bodyHtml: `<div id="doc-preview-status" class="hint" role="status" aria-live="polite">Loading preview…</div>
      <div id="doc-preview-body"></div>`,
    confirmText: "Close", showCancel: false, wide: true, tall: true, returnFocus,
  });
  try {
    const data = await api(`/v1/documents/${encodeURIComponent(docId)}/versions/${version}/preview`);
    const body = $("#doc-preview-body");
    const status = $("#doc-preview-status");
    if (!body) return;
    body.innerHTML = documentPreviewBodyHtml(data);
    if (status) status.textContent = `${data.mode === "pages" ? "Rendered pages" : "Extracted preview"}${data.mode === "pages" && data.rendered_pages ? ` · ${data.rendered_pages} page(s)` : ""}`;
  } catch (err) {
    const status = $("#doc-preview-status");
    if (status) status.textContent = `Could not load the preview: ${err.message}. The download is unaffected.`;
  }
}

async function openDocumentVersions(docId, docName, returnFocus) {
  openModal({
    title: `Versions — ${docName || "document"}`,
    bodyHtml: `<div id="doc-versions-status" class="hint" role="status" aria-live="polite">Loading versions…</div>
      <div id="doc-versions-list" class="conversation-files-list"></div>`,
    confirmText: "Close", showCancel: false, returnFocus,
  });
  try {
    const page = await api(`/v1/documents/${encodeURIComponent(docId)}/versions`);
    const list = $("#doc-versions-list");
    const status = $("#doc-versions-status");
    if (!list) return;
    const versions = (page.versions || []).filter(v =>
      /^\/api\/v1\/documents\/doc_[0-9a-f]{16}\/versions\/\d+\/download$/.test(String(v.download_url || "")));
    list.innerHTML = versions.map(v => `<div class="workspace-file-attachment">
      <span class="workspace-file-label">v${v.version}</span>
      <span>${esc(v.filename)}</span>
      <span class="workspace-file-meta">${conversationArtifactSize(v.size_bytes)} · ${timeAgo(v.created_at)} · ${esc(v.validation_state === "passed" ? "Verified" : v.validation_state === "passed_with_warnings" ? "Validated with notes" : "Validation failed")}</span>
      ${v.validation_state !== "failed" ? `<a class="btn ghost small" href="${esc(v.download_url)}" aria-label="Download version ${v.version} of ${esc(docName || "document")}">Download</a>` : ""}
    </div>`).join("") || "";
    if (status) status.textContent = versions.length ? `${versions.length} version(s); older versions stay downloadable` : "No versions recorded.";
  } catch (err) {
    const status = $("#doc-versions-status");
    if (status) status.textContent = `Could not load versions: ${err.message}`;
  }
}

document.addEventListener("click", event => {
  const preview = event.target.closest("[data-doc-preview]");
  if (preview) {
    openDocumentPreview(preview.dataset.docPreview, Number(preview.dataset.docVersion),
      preview.dataset.docName, preview);
    return;
  }
  const versions = event.target.closest("[data-doc-versions]");
  if (versions) {
    openDocumentVersions(versions.dataset.docVersions, versions.dataset.docName, versions);
  }
});

/* ------------------------------------- runtime & background work (route) */

/* One place that answers: where does execution live, is it really running,
   what is watched, and what is waiting. Controls here are local-owner only;
   paired phones never receive these routes (authorize_remote_route returns 403). */

let runtimeCache = null;

function runtimeHumanizeSeconds(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} second${s === 1 ? "" : "s"}`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"}`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"}`;
  return `${Math.round(h / 24)} day${h < 48 ? "" : "s"}`;
}

function runtimeNextLabel(iso) {
  if (!iso) return "not scheduled";
  const when = Date.parse(iso);
  if (Number.isNaN(when)) return "unknown";
  const delta = (when - Date.now()) / 1000;
  return delta <= 0 ? "due now" : `in ${runtimeHumanizeSeconds(delta)}`;
}

function runtimeServiceWord(service) {
  if (!service || service.supported === false) return { word: "Unavailable", cls: "warn" };
  if (!service.installed) return { word: "Not installed", cls: "" };
  if (service.state === "active") {
    return service.ready ? { word: "Ready", cls: "ok" } : { word: "Active, not ready", cls: "warn" };
  }
  return { word: `systemd: ${service.state}`, cls: service.state === "failed" ? "danger" : "warn" };
}

function runtimeSourceState(source) {
  if (!source.enabled) return { word: "Paused", cls: "" };
  if (source.last_error) return { word: "Needs attention", cls: "warn", detail: source.last_error };
  if (source.pending_events > 0) return { word: `${source.pending_events} waiting to start`, cls: "info" };
  if (!source.last_success_at) return { word: "Never checked", cls: "" };
  return { word: `Checked ${timeAgo(source.last_success_at)} — no changes`, cls: "ok" };
}

function runtimeSourceTarget(source) {
  const config = source.config || {};
  if (source.kind === "feed") return config.url || "feed";
  const path = config.path || "folder";
  return source.kind === "git" ? `${path} (${config.ref || "HEAD"})` : path;
}

function runtimeEventsHtml(sourceId) {
  return `<div class="runtime-events" data-source-events-body="${esc(sourceId)}"><p class="hint">Loading recorded changes…</p></div>`;
}

async function loadRuntimeEvents(sourceId, container) {
  try {
    const page = await api(`/v1/sources/${encodeURIComponent(sourceId)}/events?limit=20`);
    const items = page.items || [];
    if (!items.length) {
      container.innerHTML = `<p class="hint">Nothing recorded yet. Checks run in the background; an unchanged source records nothing.</p>`;
      return;
    }
    container.innerHTML = `<ul class="runtime-event-list">${items.map(item => `
      <li><span class="runtime-event-when mono">${esc((item.received_at || "").slice(0, 16).replace("T", " "))}Z</span>
        <span class="tag ${item.status === "admitted" ? "ok" : item.status === "ignored" ? "" : item.status === "superseded" ? "" : "info"}">${esc(item.status)}</span>
        <span>${esc(item.kind)}</span> <span class="runtime-event-summary">${esc(item.summary)}</span>
        ${item.status === "admitted" && item.run_id ? `<a class="btn ghost small" href="#/run/${esc(item.run_id)}">Open run</a>` : ""}
      </li>`).join("")}</ul>
      <p class="hint">Newest first. Superseded means a newer revision of the same item arrived; ignored means it was deliberately excluded or retired.</p>`;
  } catch (err) {
    container.innerHTML = `<p class="hint">Could not load recorded changes: ${esc(err.message)}</p>`;
  }
}

function paintRuntime() {
  const { data, sources, bots, schedules } = runtimeCache;
  const service = data.service || {};
  const queue = data.queue || {};
  const stats = data.sources || {};
  const engine = data.engine || {};
  const schedulerRole = data.scheduler?.role === "supervisor"
    ? "This process holds the scheduler lease." : "Another Hutch process holds the scheduler lease.";
  const serviceWord = runtimeServiceWord(service);
  const automationPaused = !!schedules?.paused;

  const attention = [];
  if (!service.supported) {
    attention.push({ text: "Background service management is unavailable on this platform; Hutch runs only while this process is open.",
                     action: "" });
  } else if (!service.installed) {
    attention.push({ text: "Hutch is running without its background service — work stops when this process stops.",
                     action: "install" });
  } else if (service.active && service.ready === false) {
    attention.push({ text: `The background service is active but not confirmed ready: ${service.detail || "not confirmed"}`,
                     action: "restart" });
  }
  if (stats.failing > 0) {
    attention.push({ text: `${stats.failing} watched source${stats.failing === 1 ? "" : "s"} cannot be read right now.`,
                     action: "sources" });
  }
  if (queue.pending_approvals > 0 || queue.unresolved_actions > 0) {
    attention.push({ text: `${queue.pending_approvals} approval${queue.pending_approvals === 1 ? "" : "s"} and ${queue.unresolved_actions} action outcome${queue.unresolved_actions === 1 ? "" : "s"} need review.`,
                     action: "needs-you" });
  }

  setTopContext(`<div class="ctx-id"><h1>Runtime &amp; background work</h1></div>
    <div class="ctx-actions ctx-actions-compact"><button class="btn ghost small" type="button" data-runtime-action="refresh" aria-label="Refresh" title="Refresh runtime status">${icon("refresh")}Refresh</button></div>`);

  view.innerHTML = `
    <div class="page-scroll"><div class="container runtime-page">
      <div id="runtime-notice" class="runtime-notice" role="status" aria-live="polite" hidden></div>

      ${attention.length ? `<section class="runtime-attention" aria-label="Items that need attention">
        <h2>Needs attention</h2>
        ${attention.map(item => `<div class="runtime-attention-row">
          <span>${esc(item.text)}</span>
          ${item.action ? `<button class="btn ghost small" type="button" data-runtime-action="${esc(item.action)}">${{
            install: "Set up background work", restart: "Restart and re-check", sources: "Review sources",
            "needs-you": "Review in Needs you" }[item.action] || "Open"}</button>` : ""}
        </div>`).join("")}
      </section>` : ""}

      <section class="runtime-card" aria-labelledby="runtime-machine-title">
        <h2 id="runtime-machine-title">This machine</h2>
        <dl class="runtime-facts">
          <div><dt>Execution</dt><dd>On this computer — this process owns accepted work, schedules and watchers.</dd></div>
          <div><dt>Version</dt><dd>v${esc(engine.version || "?")} · database schema ${esc(String(engine.schema ?? "?"))}</dd></div>
          <div><dt>Instance</dt><dd class="mono">${esc(engine.instance_id || "unknown")} · PID ${esc(String(engine.pid ?? "?"))}</dd></div>
          <div><dt>Scheduler</dt><dd>${esc(schedulerRole)}</dd></div>
          <div><dt>Reachable from</dt><dd>${data.exposure?.mode === "remote"
            ? "This computer and paired devices. Paired phones can monitor and review; they cannot administer this machine."
            : "This computer only (loopback). Remote phone supervision is a separate, explicit setup."}</dd></div>
        </dl>
      </section>

      <section class="runtime-card" aria-labelledby="runtime-service-title">
        <h2 id="runtime-service-title">Background service</h2>
        <p class="hint runtime-lead">Closing this window never stops accepted work. Hutch keeps running while this process runs${service.installed ? "" : " — install the user service to keep it running without a terminal."}</p>
        <dl class="runtime-facts">
          <div><dt>Managed service</dt><dd><span class="tag ${serviceWord.cls}">${esc(serviceWord.word)}</span>
            ${service.state && service.supported ? `<span class="hint">systemd: ${esc(service.state)}</span>` : ""}
            ${service.ready === true ? `<span class="hint">answered the readiness check for this state directory</span>` : ""}
            ${service.ready === false && service.detail ? `<span class="hint">${esc(service.detail)}</span>` : ""}</dd></div>
          <div><dt>Starts at login and survives logout</dt><dd>
            ${service.linger === "enabled" ? `<span class="tag ok">On</span> <span class="hint">systemd lingering is enabled for this user</span>`
              : service.linger === "disabled" ? `<span class="tag">Off</span> <span class="hint">logging out stops user services; turn this on only if you want scheduled work to continue after logout (a system-level opt-in)</span>`
              : service.linger === "unavailable" ? `<span class="hint">cannot be determined here</span>`
              : `<span class="hint">unknown</span>`}</dd></div>
          <div><dt>Uninstalling</dt><dd>Stops and removes the unit only. Your database, assistants, credentials and workspaces stay.</dd></div>
        </dl>
        <div class="runtime-controls" role="group" aria-label="Background service controls">
          ${!service.installed
            ? `<button class="btn primary small" type="button" data-runtime-action="install">Set up background work</button>`
            : `${service.active
                ? `<button class="btn ghost small" type="button" data-runtime-action="restart">Restart service</button>
                   <button class="btn ghost small" type="button" data-runtime-action="stop">Stop service</button>`
                : `<button class="btn primary small" type="button" data-runtime-action="restart">Start service</button>`}
               <button class="btn ghost small" type="button" data-runtime-action="uninstall">Remove background service</button>
               ${service.linger === "enabled"
                 ? `<button class="btn ghost small" type="button" data-runtime-action="startup-off">Stop starting at login</button>`
                 : service.linger === "disabled"
                   ? `<button class="btn ghost small" type="button" data-runtime-action="startup-on">Start at login and keep running after logout</button>`
                   : ""}`}
          <span class="runtime-controls-state hint" data-runtime-pending hidden>Working…</span>
        </div>
        ${!service.supported ? `<p class="hint">This platform has no supported service manager yet; Hutch runs while this process runs.</p>` : ""}
      </section>

      <section class="runtime-card" aria-labelledby="runtime-sources-title">
        <div class="runtime-card-head">
          <h2 id="runtime-sources-title">Watched sources</h2>
          <button class="btn ghost small" type="button" data-runtime-action="add-source">Add a source</button>
        </div>
        <p class="hint runtime-lead">Checks are deterministic and run in the background: an unchanged source costs no model call. Material changes admit one bounded assistant run per cooldown window.</p>
        ${sources.length ? `<div class="runtime-source-list" role="list">
          ${sources.map(source => {
            const state = runtimeSourceState(source);
            const bot = bots.find(b => b.id === source.bot_id);
            return `<article class="runtime-source" role="listitem" data-source-id="${esc(source.id)}">
              <div class="runtime-source-main">
                <div class="runtime-source-head">
                  <strong>${esc(source.name)}</strong>
                  <span class="tag">${esc(source.kind)}</span>
                  <span class="tag ${state.cls}">${esc(state.word)}</span>
                  ${source.enabled ? "" : `<span class="hint">checks paused</span>`}
                </div>
                <p class="hint runtime-source-target mono">${esc(runtimeSourceTarget(source))}</p>
                <p class="hint">${bot ? `Assistant: ${esc(bot.display_name || bot.name)} · ` : ""}${source.enabled
                  ? `last checked ${source.last_check_at ? timeAgo(source.last_check_at) : "never"} · next check ${esc(runtimeNextLabel(source.next_check_at))}`
                  : "checks are paused"}</p>
                ${state.detail ? `<p class="hint runtime-source-error">${esc(state.detail)}</p>` : ""}
                ${source.ignored_events ? `<p class="hint">${source.ignored_events} change(s) were deliberately ignored (excluded paths or retired on an edit).</p>` : ""}
              </div>
              <div class="runtime-source-actions">
                <button class="btn ghost small" type="button" data-runtime-action="source-check" data-source-id="${esc(source.id)}">Check now</button>
                <button class="btn ghost small" type="button" data-runtime-action="${source.enabled ? "source-pause" : "source-resume"}" data-source-id="${esc(source.id)}">${source.enabled ? "Pause" : "Resume"}</button>
                <button class="btn ghost small" type="button" data-runtime-action="source-remove" data-source-id="${esc(source.id)}">Remove</button>
              </div>
              <details class="runtime-source-events" data-source-events="${esc(source.id)}">
                <summary>Recent changes${source.admitted_events ? ` · ${source.admitted_events} admitted` : ""}</summary>
                ${runtimeEventsHtml(source.id)}
              </details>
            </article>`;
          }).join("")}
        </div>` : `<section class="empty-state runtime-empty">
          <p><b>Nothing is watched yet.</b></p>
          <p class="hint">Watch a folder, a git repository, or an RSS/Atom feed. Hutch records changes durably; only material changes start a bounded assistant run.</p>
          <button class="btn primary small" type="button" data-runtime-action="add-source">Add a source</button>
        </section>`}
        ${stats.pending_events ? `<p class="hint" role="status">${stats.pending_events} recorded change(s) are waiting to start within their cooldown limits.</p>` : ""}
      </section>

      <section class="runtime-card" aria-labelledby="runtime-jobs-title">
        <h2 id="runtime-jobs-title">Multi-step jobs</h2>
        <p class="hint runtime-lead">A watched folder in document mode runs a checkpointed pipeline: register inputs, extract text, OCR only scanned pages, update the local index, then write a grounded summary. An interruption resumes at the last verified step; a possible external effect stops the job for review instead of being replayed.</p>
        ${runtimeCache.jobs.length ? `<div class="runtime-job-list" role="list">
          ${runtimeCache.jobs.map(job => {
            const label = { document_pipeline: "Document summary" }[job.kind] || job.kind;
            const done = (job.steps || []).filter(step => step.status === "succeeded").length;
            const total = (job.steps || []).length || 6;
            const statusWord = { queued: "Queued", running: "Working", blocked: "Needs review",
              succeeded: "Done", failed: "Failed", cancelled: "Cancelled" }[job.status] || job.status;
            const statusClass = { succeeded: "ok", blocked: "warn", failed: "danger", running: "info",
              cancelled: "" }[job.status] || "";
            return `<article class="runtime-job" role="listitem" data-job-id="${esc(job.id)}">
              <div class="runtime-source-head">
                <strong>${esc(label)}</strong>
                <span class="tag ${statusClass}">${esc(statusWord)}</span>
                <span class="hint mono">${done}/${total} steps</span>
                <span class="hint">${timeAgo(job.updated_at || job.created_at)}</span>
                ${["queued", "running", "blocked"].includes(job.status)
                  ? `<button class="btn ghost small" type="button" data-runtime-action="job-cancel" data-job-id="${esc(job.id)}">Cancel job</button>` : ""}
              </div>
              ${job.error ? `<p class="hint runtime-source-error">${esc(job.error)}</p>` : ""}
              <details class="runtime-source-events">
                <summary>Steps and result</summary>
                <div>
                  <ul class="runtime-event-list">
                    ${(job.steps || []).map(step => `<li>
                      <span class="tag ${step.status === "succeeded" ? "ok" : step.status === "running" ? "info" : step.status === "failed" ? "danger" : ""}">${esc(step.status)}</span>
                      <span>${esc(step.step_key)}</span>
                      <span class="hint">attempt ${step.attempt}${step.error ? ` — ${esc(step.error)}` : ""}</span>
                      ${step.run_id ? `<a class="btn ghost small" href="#/run/${esc(step.run_id)}">Open run</a>` : ""}
                    </li>`).join("")}
                  </ul>
                  ${job.message ? `<p class="runtime-job-message">${esc(job.message.slice(0, 600))}${job.message.length > 600 ? "…" : ""}</p>` : ""}
                  ${job.artifact ? `<p class="hint mono">artifact ${esc(job.artifact_sha256.slice(0, 12))} · ${esc(job.artifact)}</p>` : ""}
                </div>
              </details>
            </article>`;
          }).join("")}
        </div>` : `<p class="hint">No multi-step jobs yet. A watched folder that uses document mode creates them automatically when something changes.</p>`}
      </section>

      <section class="runtime-card" aria-labelledby="runtime-queue-title">
        <h2 id="runtime-queue-title">Queue &amp; automation</h2>
        <dl class="runtime-facts">
          <div><dt>Working now</dt><dd>${queue.active_runs || 0} run(s), ${queue.queued_tasks || 0} queued</dd></div>
          <div><dt>Waiting for you</dt><dd>${queue.pending_approvals || 0} approval(s) · ${queue.unresolved_actions || 0} action outcome(s) to check
            ${(queue.pending_approvals || queue.unresolved_actions) ? ` · <a href="#/approvals">Review in Needs you</a>` : ""}</dd></div>
          <div><dt>Recurring work</dt><dd>${automationPaused
            ? `<span class="tag warn">Paused</span> Scheduled starts and watched-source admissions are paused; work already running can finish.`
            : `<span class="tag ok">On</span> Schedules and watched sources can start new work.`}</dd></div>
          ${queue.execution_held ? `<div><dt>Execution</dt><dd><span class="tag danger">Held</span> Restore review is required before new work starts.</dd></div>` : ""}
        </dl>
        <div class="runtime-controls">
          <button class="switch" type="button" role="switch" aria-checked="${!automationPaused}"
                  data-runtime-action="${automationPaused ? "automation-resume" : "automation-pause"}">
            <span>Automatic starts</span><span class="switch-track" aria-hidden="true"></span><span class="switch-state" aria-hidden="true">${automationPaused ? "Off" : "On"}</span>
          </button>
        </div>
      </section>
    </div></div>`;
  bindRuntimeActions();
}

function setRuntimePending(action, pending) {
  runtimeCache = runtimeCache ? { ...runtimeCache, pending: pending ? action : "" } : runtimeCache;
  const state = $("[data-runtime-pending]");
  if (state) state.hidden = !pending;
  $$("[data-runtime-action]").forEach(button => {
    button.disabled = pending;
  });
}

function runtimeNotice(message, isError = false) {
  const notice = $("#runtime-notice");
  if (!notice) return;
  notice.hidden = !message;
  notice.className = `runtime-notice${isError ? " error" : ""}`;
  notice.textContent = message || "";
}

async function runtimeAction(action, button) {
  if (runtimeCache?.pending) return;
  const sourceId = button?.dataset.sourceId || "";
  const focusId = button?.dataset.runtimeAction + (sourceId ? `:${sourceId}` : "");
  try {
    if (action === "refresh") {
      await renderRuntime();
      return;
    }
    if (action === "install") {
      const ok = await confirmDialog({
        title: "Set up background work",
        body: `Install and start Hutch's <b>user service</b> on this machine? It runs the loopback dashboard without a terminal, starts after you log in, and never enables remote access. It uses this installation's Python environment and state directory.`,
        confirmText: "Install service",
      });
      if (!ok) return;
      setRuntimePending(action, true);
      const snapshot = await api("/v1/runtime/service/install", { method: "POST", body: { confirm: "install", port: 8787 } });
      await renderRuntime();
      runtimeNotice(snapshot.ready ? "Background work is set up and ready."
                                   : "The unit is installed but readiness was not confirmed. Check the service block.");
      return;
    }
    if (action === "restart") {
      setRuntimePending(action, true);
      const snapshot = await api("/v1/runtime/service/restart", { method: "POST", body: { confirm: "restart" } });
      await renderRuntime();
      runtimeNotice(snapshot.ready ? "Service restarted; the readiness check passed." : "Restarted, but readiness is not confirmed.");
      return;
    }
    if (action === "stop") {
      const ok = await confirmDialog({
        title: "Stop the Hutch service",
        body: `Stop the background service? Work already accepted is signalled and records its outcome; nothing already sent to a provider is undone. Schedules and watchers <b>stop</b> until you start the service again — Hutch will not restart itself after a deliberate stop.`,
        confirmText: "Stop service", danger: true,
      });
      if (!ok) return;
      await api("/v1/runtime/service/stop", { method: "POST", body: { confirm: "stop" } });
      runtimeNotice("Stopping… this page will stop responding when the service stops. Restart later with `hutch service restart` or by starting `hutch serve`.");
      return;
    }
    if (action === "uninstall") {
      const ok = await confirmDialog({
        title: "Remove the background service",
        body: `Stop and remove the managed unit? Scheduled and watched work will only run while a Hutch process is open. Your database, assistants, credentials and workspaces are <b>not</b> removed.`,
        confirmText: "Remove service", danger: true,
      });
      if (!ok) return;
      setRuntimePending(action, true);
      await api("/v1/runtime/service/uninstall", { method: "POST", body: { confirm: "uninstall" } });
      await renderRuntime();
      runtimeNotice("The background service was removed. Data was preserved.");
      return;
    }
    if (action === "startup-on" || action === "startup-off") {
      const enabling = action === "startup-on";
      const ok = await confirmDialog({
        title: enabling ? "Start Hutch at login" : "Stop starting Hutch at login",
        body: enabling
          ? `Enable systemd <b>lingering</b> for this user? Hutch then starts at boot and keeps running after you log out. This changes login behavior for your user account and is an explicit opt-in.`
          : `Disable systemd lingering? Hutch stops running after you log out; work continues while you are logged in.`,
        confirmText: enabling ? "Enable lingering" : "Disable lingering",
      });
      if (!ok) return;
      setRuntimePending(action, true);
      const snapshot = await api("/v1/runtime/service/startup", { method: "POST", body: { confirm: "startup", enabled: enabling } });
      await renderRuntime();
      runtimeNotice(`Start-at-login is now ${snapshot.linger}.`);
      return;
    }
    if (action === "automation-pause" || action === "automation-resume") {
      const paused = action === "automation-pause";
      setRuntimePending(action, true);
      await api("/v1/schedules/control", { method: "PUT", body: { paused } });
      await renderRuntime();
      runtimeNotice(paused ? "Automatic starts paused. Schedules and watched sources will not start new work; running work can finish."
                           : "Automatic starts resumed.");
      return;
    }
    if (action === "source-check") {
      setRuntimePending(action, true);
      await api(`/v1/sources/${encodeURIComponent(sourceId)}/check`, { method: "POST", body: {} });
      await renderRuntime();
      runtimeNotice("A check is scheduled; the next refresh shows its result.");
      return;
    }
    if (action === "source-pause" || action === "source-resume") {
      setRuntimePending(action, true);
      await api(`/v1/sources/${encodeURIComponent(sourceId)}`, { method: "PUT", body: { enabled: action === "source-resume" } });
      await renderRuntime();
      runtimeNotice(action === "source-pause"
        ? "Checks paused. Recorded-but-unadmitted changes were retired so a pause cannot start work."
        : "Checks resumed. The next check re-establishes the cursor from the source's current state.");
      return;
    }
    if (action === "source-remove") {
      const source = runtimeCache?.sources.find(item => item.id === sourceId);
      const ok = await confirmDialog({
        title: "Remove this watched source",
        body: `Stop checking <b>${esc(source?.name || sourceId)}</b>? Recorded change history stays for review; no further checks or runs are admitted.`,
        confirmText: "Remove source", danger: true,
      });
      if (!ok) return;
      setRuntimePending(action, true);
      await api(`/v1/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
      await renderRuntime();
      runtimeNotice("Source removed.");
      return;
    }
    if (action === "add-source") {
      openAddSourceDialog();
      return;
    }
    if (action === "job-cancel") {
      const jobId = button?.dataset.jobId || "";
      const ok = await confirmDialog({
        title: "Cancel this job",
        body: "Stop this multi-step job? No further steps start, and a step that is currently running is asked to stop. Work already delivered is not undone.",
        confirmText: "Cancel job", danger: true,
      });
      if (!ok) return;
      setRuntimePending(action, true);
      await api(`/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: {} });
      await renderRuntime();
      runtimeNotice("Job cancelled.");
      return;
    }
    if (action === "needs-you") {
      void openNeedsYou();
      return;
    }
  } catch (err) {
    setRuntimePending("", false);
    runtimeNotice(err.message || "That action failed.", true);
  } finally {
    setRuntimePending("", false);
    // The automatic-starts switch changes its action as it flips, so find it by role.
    const again = action.startsWith("automation-") ? $('[role="switch"][data-runtime-action]')
      : focusId ? $(`[data-runtime-action="${focusId.split(":")[0]}"][data-source-id="${focusId.split(":")[1] || ""}"]`) : null;
    (again || $("[data-runtime-action]"))?.focus?.({ preventScroll: true });
  }
}

function openAddSourceDialog() {
  const bots = runtimeCache?.bots || [];
  if (!bots.length) {
    runtimeNotice("Create an assistant first — a watched source needs an assistant to do the work.", true);
    return;
  }
  openModal({
    title: "Add a watched source",
    confirmText: "Start watching",
    bodyHtml: `<div class="runtime-add-source">
      <label class="field">Assistant
        <select id="runtime-source-bot" required>${bots.map(bot => `<option value="${esc(bot.name)}">${esc(bot.display_name || bot.name)}</option>`).join("")}</select>
      </label>
      <label class="field">What to watch
        <select id="runtime-source-kind">
          <option value="folder">A folder on this machine</option>
          <option value="git">A git repository</option>
          <option value="feed">An RSS or Atom feed</option>
        </select>
      </label>
      <label class="field" data-source-field="path">Folder or repository path
        <input id="runtime-source-path" type="text" placeholder="/home/you/Documents/scans" autocomplete="off">
      </label>
      <label class="field" data-source-field="url" hidden>Feed URL
        <input id="runtime-source-url" type="url" placeholder="https://example.com/feed.xml" autocomplete="off">
      </label>
      <label class="field">Name <input id="runtime-source-name" type="text" maxlength="80" placeholder="Scanned documents"></label>
      <label class="field">What should the assistant do when something changes?
        <textarea id="runtime-source-prompt" rows="3" maxlength="4000"
          placeholder="Summarize what changed and file it in the project folder."></textarea>
      </label>
      <details class="runtime-advanced"><summary>Check timing and limits</summary>
        <label class="field">Check every <input id="runtime-source-every" type="number" min="10" max="86400" value="60" inputmode="numeric"> seconds</label>
        <label class="field">Wait at least <input id="runtime-source-cooldown" type="number" min="10" max="86400" value="300" inputmode="numeric"> seconds between started runs</label>
        <label class="field">At most <input id="runtime-source-max" type="number" min="1" max="60" value="6" inputmode="numeric"> runs per hour</label>
      </details>
      <p id="runtime-source-error" class="form-error" role="status"></p>
      <p class="hint">Change reports are copied from outside Hutch and treated as untrusted data: the assistant verifies them and never follows instructions inside them. Folder sources never watch Hutch's own state directory.</p>
    </div>`,
    onConfirm: async () => {
      const kind = $("#runtime-source-kind").value;
      const error = $("#runtime-source-error");
      const payload = {
        bot: $("#runtime-source-bot").value,
        kind,
        name: $("#runtime-source-name").value.trim() || `${kind} source`,
        path: $("#runtime-source-path").value.trim(),
        url: $("#runtime-source-url").value.trim(),
        prompt: $("#runtime-source-prompt").value.trim(),
        every_seconds: Number($("#runtime-source-every").value) || 60,
        cooldown_seconds: Number($("#runtime-source-cooldown").value) || 300,
        max_per_hour: Number($("#runtime-source-max").value) || 6,
      };
      if (kind !== "feed" && !(payload.path.startsWith("/") || /^[A-Za-z]:\\/.test(payload.path))) {
        error.textContent = "Enter an absolute path (starting with /).";
        $("#runtime-source-path").focus();
        return false;
      }
      if (kind === "feed" && !payload.url) {
        error.textContent = "Enter the feed URL.";
        $("#runtime-source-url").focus();
        return false;
      }
      try {
        await api("/v1/sources", { method: "POST", body: payload });
      } catch (err) {
        error.textContent = err.message || "That source could not be registered.";
        return false;
      }
      await renderRuntime();
      runtimeNotice("Source registered. The first check establishes a baseline; later checks report changes.");
      return true;
    },
  });
  const kindSelect = $("#runtime-source-kind");
  kindSelect?.addEventListener("change", () => {
    const isFeed = kindSelect.value === "feed";
    $('[data-source-field="path"]').hidden = isFeed;
    $('[data-source-field="url"]').hidden = !isFeed;
  });
}

function bindRuntimeActions() {
  const root = $(".runtime-page");
  if (!root) return;
  root.addEventListener("click", event => {
    const button = event.target.closest("[data-runtime-action]");
    if (button) {
      event.preventDefault();
      void runtimeAction(button.dataset.runtimeAction, button);
    }
  });
  root.querySelectorAll(".runtime-source-events").forEach(details => {
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      const body = details.querySelector("[data-source-events-body]");
      if (body && !body.dataset.loaded) {
        body.dataset.loaded = "1";
        void loadRuntimeEvents(details.dataset.sourceEvents, body);
      }
    });
  });
}

async function renderRuntime() {
  const [data, sourcePage, jobsPage, bots, schedules] = await Promise.all([
    api("/v1/runtime"),
    api("/v1/sources"),
    api("/v1/jobs?limit=10"),
    api("/bots"),
    api("/v1/schedules/control"),
  ]);
  runtimeCache = { data, sources: sourcePage.items || [], jobs: jobsPage.items || [], bots, schedules, pending: "" };
  paintRuntime();
}

function hutchUploadsKey(conversationId) {
  return `hutch-uploads:${conversationId || ""}`;
}

function hutchUploadsGet(conversationId) {
  try {
    const value = JSON.parse(localStorage.getItem(hutchUploadsKey(conversationId)) || "[]");
    return Array.isArray(value) ? value.filter(item => item && typeof item.id === "string") : [];
  } catch { return []; }
}

function hutchUploadsPut(conversationId, uploads) {
  try { localStorage.setItem(hutchUploadsKey(conversationId), JSON.stringify(uploads)); }
  catch { /* chips are view state; an unavailable browser store drops them honestly */ }
}

function hutchUploadsHumanSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/* Image attachments for chat: the composer's tray is the set of files that
   travel with the NEXT message — sendable images go with every message until
   removed, other files stay workspace-only (mention them by name). */
const CHAT_MAX_IMAGES = 4;
const CHAT_MAX_IMAGE_BYTES = 1_500_000;          // mirrors providers/attachments.py
const SENDABLE_IMAGE_TYPE = /^image\/(png|jpeg|webp)$/i;
const SENDABLE_IMAGE_NAME = /\.(png|jpe?g|webp)$/i;

function isImageUploadEntry(upload) {
  if (!upload || typeof upload !== "object") return false;
  const mime = String(upload.mime || "").toLowerCase();
  if (mime) return SENDABLE_IMAGE_TYPE.test(mime);
  // Chips stored before the mime field existed still recognise their extension.
  return SENDABLE_IMAGE_NAME.test(String(upload.filename || ""));
}

function isSendableImageFile(file) {
  const type = String(file?.type || "");
  if (type) return SENDABLE_IMAGE_TYPE.test(type);
  return SENDABLE_IMAGE_NAME.test(String(file?.name || ""));
}

/* Uploads still in flight, so a slow file shows a chip and a status instead of
   a silent wait (the failure class users report as "upload freezes with no
   feedback"). Keys are per conversation; entries are dropped on settle. */
const uploadInFlight = new Map();

function addInFlight(conversationId, entry) {
  const list = uploadInFlight.get(conversationId) || [];
  uploadInFlight.set(conversationId, [...list, entry]);
}

function clearInFlight(conversationId, key) {
  const list = (uploadInFlight.get(conversationId) || []).filter(item => item.key !== key);
  if (list.length) uploadInFlight.set(conversationId, list);
  else uploadInFlight.delete(conversationId);
}

function hutchUploadsRow(uploads, status = "", conversationId = "") {
  const inflight = conversationId ? (uploadInFlight.get(conversationId) || []) : [];
  if (!uploads.length && !inflight.length && !status) return "";
  const inflightChips = inflight.map(item => `<span class="upload-chip is-uploading" role="listitem">
    <span class="upload-chip-name">${esc(item.filename)}</span>
    <span class="upload-chip-size">Uploading…</span>
  </span>`).join("");
  const chips = inflightChips + uploads.map(upload => {
    const image = isImageUploadEntry(upload);
    const thumb = image && conversationId
      ? `<img class="upload-chip-thumb" alt="" width="24" height="24" loading="lazy" decoding="async"
           src="/api/v1/conversations/${encodeURIComponent(conversationId)}/uploads/${encodeURIComponent(upload.id)}/content">`
      : "";
    return `<span class="upload-chip${image ? " is-image" : ""}" role="listitem">
    ${thumb}<span class="upload-chip-name" title="${esc(upload.filename)}">${esc(upload.filename)}</span>
    <span class="upload-chip-size">${esc(hutchUploadsHumanSize(upload.bytes))}</span>
    <button type="button" class="upload-chip-remove" data-upload-remove="${esc(upload.id)}"
      aria-label="Remove ${esc(upload.filename)} from the composer">${icon("x")}</button>
  </span>`;
  }).join("");
  return `<div class="composer-attachments">
    <div class="composer-attachments-chips" role="list" aria-label="Files in this composer">${chips}</div>
    <p class="composer-attachments-hint">Images here are sent with every message until you remove them; other files stay in this chat’s workspace — mention them by name.
      <span class="composer-attachments-status" role="status" aria-live="polite">${esc(status)}</span></p>
  </div>`;
}

function hutchUploadsSync(conversationId = currentConversationId, status = "") {
  const box = document.getElementById("composer-box");
  if (!box || !conversationId || conversationId !== currentConversationId) return;
  box.querySelector(".composer-attachments")?.remove();
  box.insertAdjacentHTML("afterbegin", hutchUploadsRow(hutchUploadsGet(conversationId), status, conversationId));
  box.querySelectorAll(".upload-chip-thumb").forEach(img => {
    // A missing thumbnail shows the filename alone; send re-verifies the bytes anyway.
    img.addEventListener("error", () => img.remove(), { once: true });
  });
}

async function hutchUploadsSend(conversationId, file) {
  if (file.size > 25000000) return { error: `${file.name} is over the 25 MB upload limit` };
  const body = new FormData();
  body.append("file", file, file.name);
  const headers = {};
  if (hutchCsrfToken) headers["X-Hutch-CSRF"] = hutchCsrfToken;
  if (hutchSession?.principal === "paired") headers["X-Hutch-Request"] = "1";
  try {
    const response = await fetch(`/api/v1/conversations/${encodeURIComponent(conversationId)}/uploads`, {
      method: "POST", credentials: "same-origin", headers, body,
    });
    if (!response.ok) {
      let detail = "";
      try { detail = (await response.json())?.detail || ""; } catch { /* non-JSON error body */ }
      return { error: `Upload of ${file.name} refused: ${detail || response.status}` };
    }
    return { upload: await response.json() };
  } catch {
    return { error: `Upload of ${file.name} failed: no response from the server` };
  }
}

/* One staging path for the file picker, paste, and drag-drop: honest client-side
   limits before any upload, a visible in-flight chip while it transfers, and the
   server's own sniffing/verification as the final word. */
async function stageWorkspaceFiles(files) {
  const conversationId = currentConversationId;
  if (!conversationId) {
    announce("No conversation is open, so nothing was attached.");
    return;
  }
  for (const file of files) {
    const type = String(file.type || "");
    const looksLikeImage = /^image\//i.test(type);
    const image = isSendableImageFile(file);
    if (looksLikeImage && !image) {
      const msg = `${file.name || "That image"} is ${type}; PNG, JPEG and WebP are the accepted image types, so it was not attached.`;
      toast(msg, true);
      announce(msg);
      continue;
    }
    if (image && file.size > CHAT_MAX_IMAGE_BYTES) {
      const msg = `${file.name || "That image"} is ${hutchUploadsHumanSize(file.size)}; images are limited to ${(CHAT_MAX_IMAGE_BYTES / 1_000_000).toFixed(1)} MB and it was not attached.`;
      toast(msg, true);
      announce(msg);
      continue;
    }
    const stagedImages = hutchUploadsGet(conversationId).filter(isImageUploadEntry).length
      + (uploadInFlight.get(conversationId) || []).filter(item => item.image).length;
    if (image && stagedImages >= CHAT_MAX_IMAGES) {
      const msg = `A message can carry at most ${CHAT_MAX_IMAGES} images; remove one before adding ${file.name ? `"${file.name}"` : "another"}.`;
      toast(msg, true);
      announce(msg);
      continue;
    }
    // The upload intake sniffs magic bytes against the filename's extension, and
    // pasted screenshots are often nameless — give them the matching suffix.
    let uploadFile = file;
    if (!String(file.name || "").match(SENDABLE_IMAGE_NAME)) {
      const ext = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" }[type.toLowerCase()];
      if (ext) uploadFile = new File([file], `pasted-image.${ext}`, { type: type || `image/${ext}` });
    }
    const label = uploadFile.name || file.name || "file";
    const flightKey = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    addInFlight(conversationId, { key: flightKey, filename: label, bytes: file.size, image });
    hutchUploadsSync(conversationId, `Uploading ${label}…`);
    announce(`Uploading ${label}…`);
    const result = await hutchUploadsSend(conversationId, uploadFile);
    clearInFlight(conversationId, flightKey);
    if (result.error) {
      hutchUploadsSync(conversationId, result.error);
      toast(result.error, true);
      announce(result.error);
      continue;
    }
    const uploads = hutchUploadsGet(conversationId);
    uploads.push({ id: result.upload.id, filename: result.upload.filename,
                   mime: result.upload.mime, bytes: result.upload.bytes });
    hutchUploadsPut(conversationId, uploads);
    const done = `${image ? "Attached" : "Uploaded"} ${result.upload.filename}`;
    hutchUploadsSync(conversationId, done);
    announce(image ? `${result.upload.filename} is in the composer; it is sent with your next message`
                   : `${result.upload.filename} is in this chat's workspace`);
  }
}

document.addEventListener("click", event => {
  if (event.target.closest("#workspace-upload-open")) {
    document.getElementById("workspace-upload-file")?.click();
    return;
  }
  const remove = event.target.closest("[data-upload-remove]");
  if (remove && currentConversationId) {
    const conversationId = currentConversationId;
    hutchUploadsPut(conversationId,
      hutchUploadsGet(conversationId).filter(upload => upload.id !== remove.dataset.uploadRemove));
    hutchUploadsSync(conversationId);
  }
});

document.addEventListener("change", async event => {
  const input = event.target.closest("#workspace-upload-file");
  if (!input || !input.files?.length) return;
  const files = Array.from(input.files);
  input.value = "";
  await stageWorkspaceFiles(files);
});

void bootstrapHutchApp();
