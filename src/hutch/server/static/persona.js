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
    { key: "preset", label: "Style preset", hint: "A starting voice; depth remains independent.",
      options: [["direct", "Direct"], ["warm", "Warm"], ["dry_wit", "Dry Wit"]],
      short: { direct: "Direct", warm: "Warm", dry_wit: "Dry Wit" } },
    { key: "depth", label: "Answer depth", hint: "Automatic depth follows task complexity without dropping necessary work.",
      options: [["auto", "Auto"], ["brief", "Brief"], ["standard", "Standard"], ["detailed", "Detailed"]],
      short: { auto: "Auto depth", brief: "Brief", standard: "Standard", detailed: "Detailed", thorough: "Detailed" } },
    { key: "humor", label: "Humor", hint: "Jokes stay limited to clear, low-stakes playful turns.",
      options: [["off", "Off"], ["subtle", "Subtle"], ["playful", "Playful"]],
      short: { off: "Humor off", subtle: "Subtle humor", playful: "Playful" } },
    { key: "warmth", type: "range", label: "Warmth", hint: "0 is reserved; 100 is more personable.", min: 0, max: 100, step: 10 },
    { key: "directness", type: "range", label: "Directness", hint: "0 is more explanatory; 100 is more concise.", min: 0, max: 100, step: 10 },
    { key: "formality", type: "range", label: "Formality", hint: "0 is casual; 100 is more formal.", min: 0, max: 100, step: 10 },
    { key: "profanity", label: "Profanity", hint: "Mirroring applies only after the operator uses it first and when suitable.",
      options: [["avoid", "Avoid"], ["mirror", "Mirror operator"]] },
    { key: "format_style", label: "Answer format", hint: "A preference only; requested output formats always take priority.",
      options: [["automatic", "Automatic"], ["conversational", "Conversational"], ["structured", "Structured"], ["bullets", "Bullets"]] },
    { key: "avoid_habits", type: "habits", label: "Habits to avoid", hint: "Choose from bounded wording preferences." },
  ];
  const CHAT_FIELDS = ["preset", "depth", "humor"];
  const CUSTOM_FIELDS = ["warmth", "directness", "formality", "profanity", "format_style"];
  const HABITS = [
    ["filler", "Filler openings and closings"],
    ["overpraise", "Unearned praise or flattering agreement"],
    ["emojis", "Emojis"],
    ["repeated_summary", "Repeating the conclusion"],
    ["unasked_offer", "Unasked offers at the end"],
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

  const valueForStyle = (style, key) => {
    if (key === "preset" && (style?.preset === null || style?.preset === undefined) &&
        (style?.tone === "warm" || style?.tone === "direct")) return style.tone;
    if (key === "humor" && (style?.humor === null || style?.humor === undefined) && style?.banter !== null && style?.banter !== undefined)
      return style.banter ? "subtle" : "off";
    return style?.[key];
  };
  const encodeValue = (key, value) => {
    if (value === null || value === undefined) return INHERIT;
    if (key === "depth" && value === "thorough") return "detailed";
    const field = FIELDS.find(item => item.key === key);
    return field?.type === "range" ? String(value) : value;
  };
  const decodeValue = (key, raw) => {
    if (raw === INHERIT) return null;
    return FIELDS.find(item => item.key === key)?.type === "range" ? Number(raw) : raw;
  };
  const optionLabel = (key, value) => {
    const encoded = encodeValue(key, value);
    const option = (FIELDS.find(f => f.key === key)?.options || []).find(([v]) => v === encoded);
    return option ? option[1] : String(value);
  };
  const displayValue = (key, value) => key === "avoid_habits"
    ? ((value || []).length ? value.map(item => HABITS.find(([habit]) => habit === item)?.[1] || item).join(", ") : "No habits")
    : key === "preset" && (value === null || value === undefined) ? "Neutral voice"
    : optionLabel(key, value);

  function fieldsHtml(prefix, keys = CHAT_FIELDS) {
    return FIELDS.filter(field => keys.includes(field.key) && field.type !== "habits").map(field => `
      <label class="field persona-field">${esc(field.label)}
        ${field.type === "range"
          ? `<span class="persona-range-row"><select aria-label="${esc(field.label)} inheritance" data-persona-field="${field.key}"><option value="${INHERIT}">Inherited</option><option value="custom">Custom</option></select><input id="${prefix}-${field.key}" type="range" min="${field.min}" max="${field.max}" step="${field.step}" data-persona-range="${field.key}" aria-label="${esc(field.label)} value"><output data-persona-value="${field.key}" for="${prefix}-${field.key}" aria-hidden="true"></output></span>`
          : `<select id="${prefix}-${field.key}" data-persona-field="${field.key}">
              <option value="${INHERIT}">Inherited</option>
              ${field.options.map(([value, label]) =>
                `<option value="${esc(value)}">${esc(label)}</option>`).join("")}
            </select>`}
        <span class="hint" id="${prefix}-hint-${field.key}" data-persona-origin="${field.key}">${esc(field.hint)}</span>
      </label>`).join("");
  }

  function habitsHtml(prefix) {
    return `<fieldset class="persona-habits" data-persona-habits>
      <legend>${esc(FIELDS.find(field => field.key === "avoid_habits").label)}</legend>
      <label class="persona-habit-inherit"><input type="checkbox" data-persona-habits-inherit> Use inherited preferences</label>
      <div class="persona-habit-options">${HABITS.map(([value, label]) => `
        <label><input type="checkbox" value="${esc(value)}" data-persona-habit> ${esc(label)}</label>`).join("")}</div>
      <span class="hint" data-persona-origin="avoid_habits">${esc(FIELDS.find(field => field.key === "avoid_habits").hint)}</span>
    </fieldset>`;
  }

  const selectEls = scope => {
    const out = {};
    qa("select[data-persona-field], input[data-persona-field]", scope).forEach(el => { out[el.dataset.personaField] = el; });
    return out;
  };
  const rangeEls = scope => {
    const out = {};
    qa("[data-persona-range]", scope).forEach(el => { out[el.dataset.personaRange] = el; });
    return out;
  };
  const originEls = scope => {
    const out = {};
    qa("[data-persona-origin]", scope).forEach(el => { out[el.dataset.personaOrigin] = el; });
    return out;
  };

  function writeSelects(scope, style) {
    const els = selectEls(scope);
    const ranges = rangeEls(scope);
    FIELDS.forEach(field => {
      if (!els[field.key]) return;
      const value = valueForStyle(style, field.key);
      els[field.key].value = field.type === "range" ? (value === null || value === undefined ? INHERIT : "custom") : encodeValue(field.key, value);
      if (ranges[field.key]) {
        ranges[field.key].value = value === null || value === undefined ? String((field.min + field.max) / 2) : String(value);
        ranges[field.key].disabled = value === null || value === undefined;
      }
      const output = q(`[data-persona-value="${field.key}"]`, scope);
      if (output) output.value = value === null || value === undefined ? "Inherited" : `${value}/100`;
    });
    writeHabits(scope, style);
  }

  function writeHabits(scope, style) {
    const group = q("[data-persona-habits]", scope);
    if (!group) return;
    const inherited = style?.avoid_habits === null || style?.avoid_habits === undefined;
    q("[data-persona-habits-inherit]", group).checked = inherited;
    qa("[data-persona-habit]", group).forEach(el => {
      el.checked = !inherited && (style.avoid_habits || []).includes(el.value);
      el.disabled = inherited;
    });
  }

  function syncHabitInputs(scope) {
    const group = q("[data-persona-habits]", scope);
    if (!group) return;
    const inherited = q("[data-persona-habits-inherit]", group).checked;
    qa("[data-persona-habit]", group).forEach(el => { el.disabled = inherited; });
  }

  function readHabits(scope) {
    const group = q("[data-persona-habits]", scope);
    if (!group) return undefined;
    if (q("[data-persona-habits-inherit]", group).checked) return null;
    return qa("[data-persona-habit]:checked", group).map(el => el.value);
  }

  function setDisabled(scope, disabled) {
    qa("[data-persona-field], [data-persona-range], [data-persona-habits] input", scope).forEach(el => { el.disabled = disabled; });
    if (!disabled) {
      const ranges = rangeEls(scope);
      Object.entries(selectEls(scope)).forEach(([key, select]) => {
        if (ranges[key]) ranges[key].disabled = select.value === INHERIT;
      });
      writeHabits(scope, { avoid_habits: readHabits(scope) });
    }
  }

  function captureControls(scope) {
    const controls = {};
    Object.entries(selectEls(scope)).forEach(([key, el]) => { controls[key] = el.value; });
    Object.entries(rangeEls(scope)).forEach(([key, el]) => { controls[`${key}__range`] = el.value; });
    const habits = readHabits(scope);
    if (habits !== undefined) controls.avoid_habits = habits;
    return controls;
  }

  function restoreControls(scope, controls) {
    const els = selectEls(scope);
    const ranges = rangeEls(scope);
    Object.entries(controls || {}).forEach(([key, value]) => {
      if (key === "avoid_habits") return;
      if (key.endsWith("__range")) { const range = ranges[key.slice(0, -7)]; if (range) range.value = value; return; }
      if (els[key]) els[key].value = value;
    });
    Object.entries(els).forEach(([key, select]) => { if (ranges[key]) ranges[key].disabled = select.value === INHERIT; });
    if (Object.hasOwn(controls || {}, "avoid_habits")) writeHabits(scope, { avoid_habits: controls.avoid_habits });
  }

  function restoreDraftChanges(scope, draft, changedFields) {
    const controls = {};
    changedFields.forEach(key => {
      if (Object.hasOwn(draft || {}, key)) controls[key] = draft[key];
      const rangeKey = `${key}__range`;
      if (Object.hasOwn(draft || {}, rangeKey)) controls[rangeKey] = draft[rangeKey];
    });
    restoreControls(scope, controls);
  }

  function resetFields(scope, keys) {
    const selects = selectEls(scope);
    const ranges = rangeEls(scope);
    keys.forEach(key => {
      if (selects[key]) selects[key].value = INHERIT;
      if (ranges[key]) {
        ranges[key].disabled = true;
        ranges[key].value = "50";
        const output = q(`[data-persona-value="${key}"]`, scope);
        if (output) output.value = "Inherited";
      }
    });
    if (keys.includes("avoid_habits")) writeHabits(scope, { avoid_habits: null });
  }

  function focusFallbackSelector(target) {
    if (target?.matches("[data-persona-save]")) return "[data-persona-save]";
    if (target?.matches("[data-persona-conversation-save]")) return "[data-persona-conversation-save]";
    if (target?.matches("[data-persona-field]")) return `[data-persona-field="${target.dataset.personaField}"]`;
    if (target?.matches("[data-persona-range]")) return `[data-persona-range="${target.dataset.personaRange}"]`;
    if (target?.matches("[data-persona-habits-inherit]")) return "[data-persona-habits-inherit]";
    if (target?.matches("[data-persona-habit]")) return `[data-persona-habit][value="${target.value}"]`;
    return null;
  }

  function changesBetween(scope, baseline) {
    const els = selectEls(scope);
    const ranges = rangeEls(scope);
    const changes = {};
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el) return;
      if (field.type === "range") {
        const base = valueForStyle(baseline, field.key) ?? null;
        const next = el.value === INHERIT ? null : Number(ranges[field.key]?.value);
        if (next !== base) changes[field.key] = next;
        return;
      }
      const base = encodeValue(field.key, valueForStyle(baseline, field.key));
      if (el.value !== base) changes[field.key] = decodeValue(field.key, el.value);
    });
    const habits = readHabits(scope);
    if (habits !== undefined && JSON.stringify(habits) !== JSON.stringify(baseline?.avoid_habits ?? null))
      changes.avoid_habits = habits;
    return changes;
  }

  function writeOrigins(scope, state, explicitText) {
    const els = originEls(scope);
    const selects = selectEls(scope);
    const ranges = rangeEls(scope);
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el) return;
      const storedValue = valueForStyle(state?.override, field.key);
      const savedValue = field.type === "range"
        ? (storedValue === null || storedValue === undefined ? null : Number(storedValue))
        : encodeValue(field.key, storedValue);
      const current = field.type === "range"
        ? (selects[field.key]?.value === INHERIT ? null : Number(ranges[field.key]?.value))
        : field.key === "avoid_habits" ? readHabits(scope) : selects[field.key]?.value;
      const matches = field.key === "avoid_habits"
        ? JSON.stringify(current) === JSON.stringify(savedValue === INHERIT ? null : state?.override?.avoid_habits ?? null)
        : current === savedValue;
      if (current !== undefined && !matches) {
        el.textContent = "Unsaved change — not saved yet.";
        return;
      }
      const legacyNeutral = field.key === "preset" && state?.override?.preset == null && state?.override?.tone === "neutral";
      const explicit = (storedValue !== null && storedValue !== undefined) || legacyNeutral;
      if (explicit) { el.textContent = explicitText; return; }
      const effective = state?.effective?.[field.key];
      if (effective) {
        const source = state.labels?.[effective.source] || effective.source;
        el.textContent = `${source}: ${displayValue(field.key, effective.value)}`;
      } else {
        el.textContent = FIELDS.find(f => f.key === field.key).hint;
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
        <p class="hint">Choose a voice, answer depth, and humor independently. Style changes wording only; tools,
        permissions, evidence, and requested formats stay unchanged.</p>
        <div class="form-grid row2 persona-fields">${fieldsHtml("persona", CHAT_FIELDS)}</div>
        <section class="persona-customize" aria-labelledby="persona-customize-title">
          <h3 id="persona-customize-title">Optional customization</h3>
          <p class="hint">These bounded preferences refine wording. Inherited values follow the assistant, conversation, and Hutch defaults.</p>
          <div class="form-grid row2 persona-fields">${fieldsHtml("persona-custom", CUSTOM_FIELDS)}</div>
          ${habitsHtml("persona-custom")}
        </section>
        <div class="btn-row">
          <button class="btn ghost small" type="button" data-persona-reset>Reset all to inherited</button>
          <button class="btn primary small" type="submit" data-persona-save disabled>Save style</button>
          <span class="hint" data-persona-status role="status" aria-live="polite"></span>
        </div>
      </form>`;
    const form = q(".persona-form", container);
    const status = q("[data-persona-status]", container);
    const saveBtn = q("[data-persona-save]", container);
    const resetBtn = q("[data-persona-reset]", container);
    const setStatus = text => { status.textContent = text; };
    let resetAll = false;
    const refreshDirty = () => {
      const dirty = resetAll || Object.keys(changesBetween(form, saved)).length > 0;
      saveBtn.disabled = !dirty;
      return dirty;
    };
    writeSelects(form, saved);
    writeOrigins(form, state, "Saved for this assistant.");
    refreshDirty();
    const update = event => {
      const key = event.currentTarget.dataset.personaRange;
      if (key) q(`[data-persona-value="${key}"]`, form).value = `${event.currentTarget.value}/100`;
      const field = event.currentTarget.dataset.personaField;
      if (field && rangeEls(form)[field]) {
        const inherited = event.currentTarget.value === INHERIT;
        rangeEls(form)[field].disabled = inherited;
        q(`[data-persona-value="${field}"]`, form).value = inherited
          ? "Inherited" : `${rangeEls(form)[field].value}/100`;
      }
      if (event.currentTarget.matches("[data-persona-habits-inherit]")) {
        if (event.currentTarget.checked) qa("[data-persona-habit]", form).forEach(el => { el.checked = false; });
        syncHabitInputs(form);
      }
      setStatus(refreshDirty() ? "Unsaved changes" : "");
      writeOrigins(form, state, "Saved for this assistant.");
    };
    qa("[data-persona-field], [data-persona-range], [data-persona-habits] input", form)
      .forEach(el => el.addEventListener(el.matches("[data-persona-range]") ? "input" : "change", update));
    resetBtn.addEventListener("click", () => {
      resetFields(form, [...CHAT_FIELDS, ...CUSTOM_FIELDS, "avoid_habits"]);
      resetAll = true;
      setStatus("All response-style choices will be cleared to inherited.");
      refreshDirty();
      writeOrigins(form, state, "Saved for this assistant.");
    });
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const changes = changesBetween(form, saved);
      if (resetAll) { changes.tone = null; changes.banter = null; }
      if (!Object.keys(changes).length) return;
      const draft = captureControls(form);
      const changedFields = Object.keys(changes).filter(key => FIELDS.some(field => field.key === key));
      const wasReset = resetAll;
      const focusTarget = document.activeElement;
      const restoreFocus = form.contains(focusTarget);
      const focusFallback = focusFallbackSelector(focusTarget);
      saveBtn.disabled = true;
      setDisabled(form, true);
      setStatus("Saving…");
      try {
        state = await callApi(path, {
          method: "PATCH", headers: { "Idempotency-Key": newKey() },
          body: { ...changes, expected_revision: state.revision },
        });
        saved = state.override || {};
        resetAll = false;
        writeSelects(form, saved);
        writeOrigins(form, state, "Saved for this assistant.");
        setStatus("Saved.");
      } catch (err) {
        if (err.status === 409) {
          try {
            state = await callApi(path);
            saved = state.override || {};
            writeSelects(form, saved);
            if (wasReset) resetFields(form, [...CHAT_FIELDS, ...CUSTOM_FIELDS, "avoid_habits"]);
            else restoreDraftChanges(form, draft, changedFields);
            writeOrigins(form, state, "Saved for this assistant.");
            setStatus("This assistant's style changed elsewhere. Your edits are kept — review them and save again.");
          } catch (reloadError) {
            setStatus(`This assistant's style changed elsewhere and the latest could not be loaded: ${reloadError.message}`);
          }
        } else {
          setStatus(`Not saved: ${err.message}`);
        }
      } finally {
        setDisabled(form, false);
        refreshDirty();
        const currentForm = q("#persona-form-slot .persona-form") || q(".persona-form", container);
        let target = focusTarget?.isConnected ? focusTarget : focusFallback && currentForm && q(focusFallback, currentForm);
        if (target?.disabled && target.matches("[data-persona-save]")) target = q("[data-persona-reset]", currentForm);
        if (restoreFocus && target?.isConnected && !target.disabled && document.activeElement === document.body)
          target.focus({ preventScroll: true });
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
      if (stored && typeof stored === "object") {
        const migrated = { ...stored };
        if (!migrated.preset && (migrated.tone === "warm" || migrated.tone === "direct")) migrated.preset = migrated.tone;
        if (migrated.humor === null || migrated.humor === undefined) {
          if (migrated.banter === true) migrated.humor = "subtle";
          else if (migrated.banter === false) migrated.humor = "off";
        }
        delete migrated.tone;
        delete migrated.banter;
        pendingByConversation.set(conversationId, Object.keys(migrated).length ? migrated : null);
      } else {
        pendingByConversation.set(conversationId, null);
      }
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
    const parts = FIELDS.filter(field => valueForStyle(style, field.key) !== undefined && valueForStyle(style, field.key) !== null)
      .filter(field => field.key !== "avoid_habits")
      .map(field => field.short?.[encodeValue(field.key, valueForStyle(style, field.key))] || optionLabel(field.key, valueForStyle(style, field.key)));
    if (style.tone === "neutral") parts.push("Neutral voice");
    return parts
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
          <div class="persona-fields persona-fields-conversation" data-persona-scope="conversation">${fieldsHtml("persona-conv", CHAT_FIELDS)}</div>
          <div class="btn-row persona-chat-save-row">
            <button class="btn primary small" type="button" data-persona-conversation-save disabled>Save conversation style</button>
            <button class="btn ghost small" type="button" data-persona-conversation-reset>Use inherited</button>
          </div>
          <p class="cmenu-h">Next reply only</p>
          <div class="persona-fields persona-fields-turn" data-persona-scope="turn">${fieldsHtml("persona-turn", CHAT_FIELDS)}</div>
          <p class="hint">Next-reply choices apply once, stay on this device, and make no inference request while you change them.</p>
        </div>
      </details>`;
    const details = q("#persona-chat-options", container);
    const summary = q("summary", details);
    details.addEventListener("toggle", () => summary.setAttribute("aria-expanded", String(details.open)));

    const conversationScope = q('[data-persona-scope="conversation"]', container);
    const turnScope = q('[data-persona-scope="turn"]', container);
    const conversationStatus = q("[data-persona-conversation-status]", container);
    const conversationSave = q("[data-persona-conversation-save]", container);
    const conversationReset = q("[data-persona-conversation-reset]", container);
    let busy = false;
    let resetConversation = false;

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
      refreshConversationDirty();
    };
    const renderTurn = () => {
      const state = conversationStates.get(conversationId);
      const pending = pendingStyle(conversationId) || {};
      writeSelects(turnScope, pending);
      writeOrigins(turnScope, { override: pending, effective: state?.effective, labels: state?.labels },
                   "For the next reply only.");
    };
    const refreshConversationDirty = () => {
      const state = conversationStates.get(conversationId);
      const dirty = resetConversation || (state && Object.keys(changesBetween(conversationScope, state.override || {})).length > 0);
      conversationSave.disabled = busy || !dirty;
      const overrides = state?.override || {};
      conversationReset.disabled = busy || !Object.values(overrides).some(value => value !== null && value !== undefined);
      return Boolean(dirty);
    };
    const updateConversationDraft = event => {
      if (busy) return;
      const key = event.currentTarget.dataset.personaRange;
      if (key) q(`[data-persona-value="${key}"]`, conversationScope).value = `${event.currentTarget.value}/100`;
      const state = conversationStates.get(conversationId);
      if (state) writeOrigins(conversationScope, state, "Saved for this conversation.");
      conversationStatus.textContent = refreshConversationDirty() ? "Unsaved conversation style" : "";
    };
    qa("[data-persona-field], [data-persona-range]", conversationScope)
      .forEach(el => el.addEventListener(el.matches("[data-persona-range]") ? "input" : "change", updateConversationDraft));
    conversationReset.addEventListener("click", () => {
      resetFields(conversationScope, CHAT_FIELDS);
      resetConversation = true;
      conversationStatus.textContent = "Conversation choices will be cleared to inherited.";
      refreshConversationDirty();
      writeOrigins(conversationScope, conversationStates.get(conversationId), "Saved for this conversation.");
    });
    conversationSave.addEventListener("click", async () => {
      if (busy) return;
      const state = conversationStates.get(conversationId);
      if (!state) return;
      const changes = changesBetween(conversationScope, state.override || {});
      if (resetConversation) { changes.tone = null; changes.banter = null; }
      if (!Object.keys(changes).length) return;
      const draft = captureControls(conversationScope);
      const wasReset = resetConversation;
      const changedFields = Object.keys(changes).filter(key => CHAT_FIELDS.includes(key));
      const focusTarget = document.activeElement;
      const restoreFocus = details.contains(focusTarget);
      const focusFallback = focusFallbackSelector(focusTarget);
      busy = true;
      setDisabled(conversationScope, true);
      refreshConversationDirty();
      conversationStatus.textContent = "Saving…";
      try {
        const fresh = await callApi(`/v1/conversations/${encodeURIComponent(conversationId)}/persona`, {
          method: "PATCH", headers: { "Idempotency-Key": newKey() },
          body: { ...changes, expected_revision: state.revision },
        });
        conversationStates.set(conversationId, fresh);
        resetConversation = false;
        renderConversation();
        conversationStatus.textContent = "Saved for this conversation.";
      } catch (err) {
        if (err.status === 409) {
          await loadState();
          const latest = conversationStates.get(conversationId);
          writeSelects(conversationScope, latest?.override || {});
          if (wasReset) resetFields(conversationScope, CHAT_FIELDS);
          else restoreDraftChanges(conversationScope, draft, changedFields);
          resetConversation = wasReset;
          if (latest) writeOrigins(conversationScope, latest, "Saved for this conversation.");
          refreshConversationDirty();
          conversationStatus.textContent = "Style changed elsewhere. Your edits are kept; review them and save again.";
        } else {
          conversationStatus.textContent = `Not saved: ${err.message}`;
        }
      } finally {
        busy = false;
        setDisabled(conversationScope, false);
        refreshConversationDirty();
        const currentSlot = q("#persona-chat-options-slot") || container;
        const currentScope = q('[data-persona-scope="conversation"]', currentSlot);
        let target = focusTarget?.isConnected ? focusTarget
          : focusFallback && (focusFallback === "[data-persona-conversation-save]"
            ? q(focusFallback, currentSlot) : currentScope && q(focusFallback, currentScope));
        if (target?.disabled && target.matches("[data-persona-conversation-save]")) {
          const reset = q("[data-persona-conversation-reset]", currentSlot);
          const currentDetails = q("#persona-chat-options", currentSlot);
          target = reset && !reset.disabled ? reset : currentDetails && q("summary", currentDetails);
        }
        if (restoreFocus && target?.isConnected && !target.disabled && document.activeElement === document.body)
          target.focus({ preventScroll: true });
      }
    });
    qa("[data-persona-field], [data-persona-range]", turnScope).forEach(el => el.addEventListener("change", event => {
      const key = event.currentTarget.dataset.personaRange;
      if (key) q(`[data-persona-value="${key}"]`, turnScope).value = `${event.currentTarget.value}/100`;
      setPendingStyle(conversationId, readScope(turnScope, pendingStyle(conversationId) || {}));
      renderTurn();
    }));

    await loadState();
    renderConversation();
    renderTurn();
    const listener = () => renderTurn();
    subscribe(conversationId, listener);
    activeOptions = { conversationId, listener };
  }

  function readScope(scope, previous = {}) {
    const els = selectEls(scope);
    const ranges = rangeEls(scope);
    const style = { ...(previous || {}) };
    FIELDS.forEach(field => {
      const el = els[field.key];
      if (!el) return;
      if (field.type === "range") {
        if (el.value === INHERIT) delete style[field.key];
        else style[field.key] = Number(ranges[field.key]?.value);
      } else if (el.value === INHERIT) {
        delete style[field.key];
      } else {
        style[field.key] = decodeValue(field.key, el.value);
      }
    });
    const habits = readHabits(scope);
    if (habits !== undefined) {
      if (habits === null) delete style.avoid_habits;
      else style.avoid_habits = habits;
    }
    return style;
  }

  function mountComposerChip(container, conversationId) {
    if (!container) return;
    if (activeChip) { conversationListeners.get(activeChip.conversationId)?.delete(activeChip.listener); activeChip = null; }
    container.innerHTML = `
      <div class="reply-composer persona-turn-chip" hidden>
        <div class="reply-composer-preview" role="status" aria-live="polite">
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
