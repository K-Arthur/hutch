/* Response-style (persona) surface for the workspace SPA.
 *
 * Three mount points, matching where a person chooses how an assistant should sound:
 *   mountBotForm(container, botName)             Settings: the assistant's saved style beside its standing directions
 *   mountChatOptions(container, conversationId)  Chat options: this conversation's style and the next reply's style
 *   mountComposerChip(container, conversationId) The composer chip that shows a pending next-reply style
 *
 * Saving is revision-aware: the server refuses a stale save (409) instead of merging, and this file keeps the
 * person's unsaved edits on screen when that happens. Nothing here decides model behavior; the server resolves
 * the stored layers into each run's write-once plan. Follows the same conventions as skills.js: vanilla ES,
 * no build step, app.js globals at call time.
 */
(function () {
  "use strict";

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const q = (sel, el = document) => el.querySelector(sel);
  const qa = (sel, el = document) => [...el.querySelectorAll(sel)];

  const GLYPH = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M4 8h10M18 8h2M4 16h2M10 16h10"/><circle cx="16" cy="8" r="2"/><circle cx="8" cy="16" r="2"/></svg>';

  const FIELDS = [
    { key: "depth", label: "Answer depth", hint: "How much detail routine answers carry.",
      options: [["brief", "Short"], ["standard", "Balanced"], ["thorough", "Thorough"]],
      short: { brief: "short", standard: "balanced", thorough: "thorough" } },
    { key: "tone", label: "Voice", hint: "How it sounds when it answers.",
      options: [["neutral", "Neutral"], ["warm", "Warm"], ["direct", "Direct"]],
      short: { neutral: "neutral", warm: "warm", direct: "direct" } },
    { key: "banter", label: "Joking", hint: "Playful replies stay limited to clearly playful messages.",
      options: [["off", "No joking"], ["on", "Match clear joking"]],
      short: { on: "playful allowed", off: "joking off" } },
  ];
  const INHERIT = "inherit";

  async function callApi(path, opts = {}) {
    // app.js defines api() as a top-level function in a classic script; reuse it when present.
    if (typeof api === "function") return api(path, opts);
    const res = await fetch(`/api${path}`, {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      credentials: "same-origin",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(data.detail || `Request failed (${res.status})`);
      error.status = res.status;
      throw error;
    }
    return data;
  }
  const notify = (message, isError = false) => {
    if (typeof toast === "function") return toast(message, isError);
    if (isError) console.error(message); else console.info(message);
  };
  const newKey = () => `persona-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

  const encodeValue = (key, value) =>
    key === "banter" ? (value === true ? "on" : value === false ? "off" : INHERIT) : (value ?? INHERIT);
  const decodeValue = (key, raw) =>
    raw === INHERIT ? null : key === "banter" ? raw === "on" : raw;
  const optionLabel = (key, value) => {
    const encoded = encodeValue(key, value);
    const option = FIELDS.find(f => f.key === key)?.options.find(([v]) => v === encoded);
    return option ? option[1] : String(value);
  };

  function fieldsHtml(prefix) {
    return FIELDS.map(field => `
      <label class="field persona-field">${esc(field.label)}
        <select data-persona-field="${field.key}" aria-describedby="${prefix}-hint-${field.key}">
          <option value="${INHERIT}">Inherited</option>
          ${field.options.map(([value, label]) =>
            `<option value="${esc(value)}">${esc(label)}</option>`).join("")}
        </select>
        <span class="hint" id="${prefix}-hint-${field.key}" data-persona-origin="${field.key}">${esc(field.hint)}</span>
      </label>`).join("");
  }

  const selectEls = scope => {
    const out = {};
    qa("[data-persona-field]", scope).forEach(el => { out[el.dataset.personaField] = el; });
    return out;
  };
  const originEls = scope => {
    const out = {};
    qa("[data-persona-origin]", scope).forEach(el => { out[el.dataset.personaOrigin] = el; });
    return out;
  };

  function writeSelects(scope, style) {
    const els = selectEls(scope);
    FIELDS.forEach(field => { if (els[field.key]) els[field.key].value = encodeValue(field.key, style?.[field.key]); });
  }

  function changesBetween(scope, baseline) {
    const els = selectEls(scope);
    const changes = {};
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el) return;
      const base = encodeValue(field.key, baseline?.[field.key]);
      if (el.value !== base) changes[field.key] = decodeValue(field.key, el.value);
    });
    return changes;
  }

  function writeOrigins(scope, state, explicitText) {
    const els = originEls(scope);
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el) return;
      const field_ = FIELDS.find(f => f.key === field.key);
      const explicit = state?.override?.[field.key] !== null && state?.override?.[field.key] !== undefined;
      if (explicit) { el.textContent = explicitText; return; }
      const effective = state?.effective?.[field.key];
      if (effective) {
        const source = state.labels?.[effective.source] || effective.source;
        el.textContent = `${source}: ${optionLabel(field.key, effective.value)}`;
      } else {
        el.textContent = field_.hint;
      }
    });
  }

  // ------------------------------------------------------------------ settings: the assistant's saved style

  async function mountBotForm(container, botName) {
    if (!container) return;
    const path = `/v1/bots/${encodeURIComponent(botName)}/persona`;
    container.innerHTML = `<div class="panel"><p class="hint">Loading response style…</p></div>`;
    let state;
    try {
      state = await callApi(path);
    } catch (err) {
      container.innerHTML = `<div class="panel"><p class="hint">Response style is unavailable right now: ${esc(err.message)}</p></div>`;
      return;
    }
    let saved = state.override || {};
    container.innerHTML = `
      <form class="panel form-grid persona-form" aria-labelledby="persona-form-title">
        <div class="panel-title settings-panel-title"><span class="settings-panel-icon">${GLYPH}</span>
          <span id="persona-form-title">Response style</span></div>
        <p class="hint">How it should sound and how much detail it gives. Anything left as inherited follows this
        assistant's preset and Hutch's defaults.</p>
        <div class="form-grid row2 persona-fields">${fieldsHtml("persona")}</div>
        <div class="btn-row">
          <button class="btn primary small" type="submit" data-persona-save disabled>Save style</button>
          <span class="hint" data-persona-status role="status" aria-live="polite"></span>
        </div>
      </form>`;
    const form = q(".persona-form", container);
    const status = q("[data-persona-status]", container);
    const saveBtn = q("[data-persona-save]", container);
    const setStatus = text => { status.textContent = text; };
    const refreshDirty = () => {
      const dirty = Object.keys(changesBetween(form, saved)).length > 0;
      saveBtn.disabled = !dirty;
      return dirty;
    };
    writeSelects(form, saved);
    writeOrigins(form, state, "Saved for this assistant.");
    refreshDirty();
    qa("[data-persona-field]", form).forEach(el => el.addEventListener("change", () =>
      setStatus(refreshDirty() ? "Unsaved changes" : "")));
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const changes = changesBetween(form, saved);
      if (!Object.keys(changes).length) return;
      saveBtn.disabled = true;
      qa("[data-persona-field]", form).forEach(el => { el.disabled = true; });
      setStatus("Saving…");
      try {
        state = await callApi(path, {
          method: "PATCH", headers: { "Idempotency-Key": newKey() },
          body: { ...changes, expected_revision: state.revision },
        });
        saved = state.override || {};
        writeSelects(form, saved);
        writeOrigins(form, state, "Saved for this assistant.");
        setStatus("Saved.");
      } catch (err) {
        if (err.status === 409) {
          try {
            state = await callApi(path);
            saved = state.override || {};
            writeOrigins(form, state, "Saved for this assistant.");
            setStatus("This assistant's style changed elsewhere. Your edits are kept — review them and save again.");
          } catch (reloadError) {
            setStatus(`This assistant's style changed elsewhere and the latest could not be loaded: ${reloadError.message}`);
          }
        } else {
          setStatus(`Not saved: ${err.message}`);
        }
      } finally {
        qa("[data-persona-field]", form).forEach(el => { el.disabled = false; });
        refreshDirty();
      }
    });
  }

  // ------------------------------------------------------------------ chat options: this chat + the next reply

  const conversationStates = new Map();     // conversation id -> GET /persona payload
  const conversationListeners = new Map();  // conversation id -> Set(listener)
  const pendingByConversation = new Map();  // conversation id -> sparse next-reply style

  const subscribe = (conversationId, listener) => {
    if (!conversationListeners.has(conversationId)) conversationListeners.set(conversationId, new Set());
    conversationListeners.get(conversationId).add(listener);
    return () => conversationListeners.get(conversationId)?.delete(listener);
  };
  const emit = conversationId => (conversationListeners.get(conversationId) || []).forEach(fn => fn());

  const pendingStorageKey = conversationId => `hutch-persona-turn:${conversationId}`;
  function pendingStyle(conversationId) {
    if (!pendingByConversation.has(conversationId)) {
      let stored = null;
      try { stored = JSON.parse(localStorage.getItem(pendingStorageKey(conversationId)) || "null"); } catch { stored = null; }
      pendingByConversation.set(conversationId, stored && typeof stored === "object" ? stored : null);
    }
    const style = pendingByConversation.get(conversationId);
    return style && Object.keys(style).length ? style : null;
  }
  function setPendingStyle(conversationId, style) {
    const clean = style && Object.keys(style).length ? style : null;
    pendingByConversation.set(conversationId, clean);
    try {
      if (clean) localStorage.setItem(pendingStorageKey(conversationId), JSON.stringify(clean));
      else localStorage.removeItem(pendingStorageKey(conversationId));
    } catch { /* storage is optional */ }
    emit(conversationId);
  }
  function summarize(style) {
    if (!style) return "";
    return FIELDS.filter(field => style[field.key] !== undefined && style[field.key] !== null)
      .map(field => field.short?.[encodeValue(field.key, style[field.key])] || optionLabel(field.key, style[field.key]))
      .join(" · ");
  }

  let activeOptions = null;   // {conversationId, listener}
  let activeChip = null;      // {conversationId, listener}

  async function mountChatOptions(container, conversationId) {
    if (!container) return;
    if (activeOptions) { conversationListeners.get(activeOptions.conversationId)?.delete(activeOptions.listener); activeOptions = null; }
    container.innerHTML = `
      <details class="conversation-action-more persona-options" id="persona-chat-options">
        <summary class="conversation-action-item" aria-label="Response style for this chat" aria-expanded="false">
          ${GLYPH} Response style</summary>
        <div class="conversation-action-more-panel persona-options-panel">
          <p class="cmenu-h">This conversation</p>
          <span data-persona-conversation-status class="hint" role="status" aria-live="polite"></span>
          <div class="persona-fields persona-fields-conversation" data-persona-scope="conversation">${fieldsHtml("persona-conv")}</div>
          <p class="cmenu-h">Next reply only</p>
          <div class="persona-fields persona-fields-turn" data-persona-scope="turn">${fieldsHtml("persona-turn")}</div>
          <p class="hint">Next-reply choices apply once and are not saved.</p>
        </div>
      </details>`;
    const details = q("#persona-chat-options", container);
    const summary = q("summary", details);
    details.addEventListener("toggle", () => summary.setAttribute("aria-expanded", String(details.open)));

    const conversationScope = q('[data-persona-scope="conversation"]', container);
    const turnScope = q('[data-persona-scope="turn"]', container);
    const conversationStatus = q("[data-persona-conversation-status]", container);
    let busy = false;

    const loadState = async () => {
      try {
        const state = await callApi(`/v1/conversations/${encodeURIComponent(conversationId)}/persona`);
        conversationStates.set(conversationId, state);
      } catch (err) {
        conversationStatus.textContent = `Response style is unavailable: ${err.message}`;
      }
      return conversationStates.get(conversationId);
    };
    const renderConversation = () => {
      const state = conversationStates.get(conversationId);
      if (!state) return;
      writeSelects(conversationScope, state.override || {});
      writeOrigins(conversationScope, state, "Saved for this conversation.");
    };
    const renderTurn = () => {
      writeSelects(turnScope, pendingStyle(conversationId));
      writeOrigins(turnScope, conversationStates.get(conversationId), "For the next reply only.");
    };

    qa("[data-persona-field]", conversationScope).forEach(el => el.addEventListener("change", async () => {
      if (busy) return;
      const state = conversationStates.get(conversationId);
      if (!state) return;
      const changes = changesBetween(conversationScope, state.override || {});
      if (!Object.keys(changes).length) return;
      busy = true;
      qa("[data-persona-field]", conversationScope).forEach(el => { el.disabled = true; });
      conversationStatus.textContent = "Saving…";
      try {
        const fresh = await callApi(`/v1/conversations/${encodeURIComponent(conversationId)}/persona`, {
          method: "PATCH", headers: { "Idempotency-Key": newKey() },
          body: { ...changes, expected_revision: state.revision },
        });
        conversationStates.set(conversationId, fresh);
        renderConversation();
        conversationStatus.textContent = "Saved for this conversation.";
      } catch (err) {
        if (err.status === 409) {
          await loadState();
          renderConversation();
          conversationStatus.textContent = "Style changed elsewhere; showing the latest.";
        } else {
          renderConversation();
          conversationStatus.textContent = `Not saved: ${err.message}`;
        }
      } finally {
        busy = false;
        qa("[data-persona-field]", conversationScope).forEach(el => { el.disabled = false; });
      }
    }));
    qa("[data-persona-field]", turnScope).forEach(el => el.addEventListener("change", () => {
      setPendingStyle(conversationId, readScope(turnScope));
      renderTurn();
    }));

    await loadState();
    renderConversation();
    renderTurn();
    const listener = () => renderTurn();
    subscribe(conversationId, listener);
    activeOptions = { conversationId, listener };
  }

  function readScope(scope) {
    const els = selectEls(scope);
    const style = {};
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el || el.value === INHERIT) return;
      style[field.key] = decodeValue(field.key, el.value);
    });
    return style;
  }

  function mountComposerChip(container, conversationId) {
    if (!container) return;
    if (activeChip) { conversationListeners.get(activeChip.conversationId)?.delete(activeChip.listener); activeChip = null; }
    container.innerHTML = `
      <div class="reply-composer persona-turn-chip" hidden>
        <div class="reply-composer-preview">
          <span class="reply-composer-by">Next reply style</span>
          <span class="reply-composer-text" data-persona-turn-text></span>
        </div>
        <button class="btn ghost small" type="button" data-persona-turn-clear aria-label="Clear the next-reply style">Remove</button>
      </div>`;
    const chip = q(".persona-turn-chip", container);
    const text = q("[data-persona-turn-text]", container);
    const render = () => {
      const summary = summarize(pendingStyle(conversationId));
      chip.hidden = !summary;
      text.textContent = summary;
    };
    q("[data-persona-turn-clear]", container).addEventListener("click", () => setPendingStyle(conversationId, null));
    const listener = () => render();
    subscribe(conversationId, listener);
    activeChip = { conversationId, listener };
    render();
  }

  window.hutchPersona = {
    mountBotForm,
    mountChatOptions,
    mountComposerChip,
    nextReply: conversationId => pendingStyle(conversationId),
    consumeNextReply: conversationId => setPendingStyle(conversationId, null),
  };
})();
