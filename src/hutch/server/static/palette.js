/* hutch — command palette (Cmd+K / Ctrl+K).

   One keyboard-first way to jump to an assistant, a recent conversation, a page or an
   action. A native modal <dialog> owns the focus trap and Escape; the input is an ARIA
   1.2 combobox over a listbox (DOM focus stays in the input, aria-activedescendant
   follows the arrows). Nothing here grants authority: every entry is a navigation the
   person could already make, and "Needs you" only opens the existing review drawer.

   app.js supplies what the palette needs through HutchPalette.init({...}); this file
   never reads app state directly. */
(function (root) {
  "use strict";

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Match when every whitespace-separated query word appears, in any order.
  function matches(entry, query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return true;
    const hay = `${entry.label} ${entry.hint || ""} ${entry.keywords || ""}`.toLowerCase();
    return words.every(word => hay.includes(word));
  }

  function init(ctx) {
    let dialog = null, input = null, list = null, status = null;
    let entries = [], visible = [], active = 0, trigger = null, loadToken = 0;

    function build() {
      dialog = document.createElement("dialog");
      dialog.className = "palette";
      dialog.setAttribute("aria-label", "Jump to");
      dialog.innerHTML = `
        <div class="palette-field">
          ${ctx.icon("search")}
          <input id="palette-input" type="text" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-autocomplete="list"
            aria-label="Search assistants, conversations and pages" placeholder="Search assistants, chats and pages…"
            autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="go">
          <kbd class="palette-esc" aria-hidden="true">Esc</kbd>
        </div>
        <ul id="palette-list" class="palette-list" role="listbox" aria-label="Results"></ul>
        <p class="palette-foot" aria-hidden="true"><span><kbd>${ctx.icon("up")}</kbd><kbd>${ctx.icon("down")}</kbd> to move</span><span><kbd>Enter</kbd> to open</span><span><kbd>Esc</kbd> to close</span></p>
        <p class="visually-hidden" id="palette-status" role="status" aria-live="polite"></p>`;
      document.body.appendChild(dialog);
      input = dialog.querySelector("#palette-input");
      list = dialog.querySelector("#palette-list");
      status = dialog.querySelector("#palette-status");

      input.addEventListener("input", () => { active = 0; render(); });   // a new query starts at its best match
      input.addEventListener("keydown", event => {
        if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
        else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
        else if (event.key === "Home" && !input.value) { event.preventDefault(); setActive(0); }
        else if (event.key === "End" && !input.value) { event.preventDefault(); setActive(visible.length - 1); }
        else if (event.key === "Enter") { event.preventDefault(); run(visible[active]); }
        else if (event.key === "Escape") { event.preventDefault(); close(); }
      });
      list.addEventListener("pointermove", event => {
        const row = event.target.closest("[data-palette-index]");
        if (row) setActive(Number(row.dataset.paletteIndex), false);
      });
      list.addEventListener("click", event => {
        const row = event.target.closest("[data-palette-index]");
        if (row) run(visible[Number(row.dataset.paletteIndex)]);
      });
      dialog.addEventListener("click", event => { if (event.target === dialog) close(); });   // backdrop
      // Escape from anywhere in the dialog (the input handles its own), or the native cancel path.
      dialog.addEventListener("close", restoreFocus);
    }

    function staticEntries() {
      const nav = (label, hash, icon, keywords = "") => ({ kind: "Go to", label, icon, keywords, run: () => { location.hash = hash; } });
      const go = [
        nav("Chats", "#/chat", "chat", "conversations home"),
        nav("Chat library", "#/chats", "inbox", "history archive search"),
        { kind: "Go to", label: "Needs you", icon: "shield", keywords: "approvals permissions requests review", run: () => ctx.openNeedsYou() },
        nav("Activity", "#/overview", "chart", "dashboard overview"),
        nav("Scheduled work", "#/schedules", "calendar", "routines cron"),
        nav("Work history", "#/runs", "clock", "runs past tasks"),
        nav("Runtime", "#/runtime", "terminal", "background sources"),
        nav("Skills", "#/skills", "sparkles", "abilities"),
        nav("Apps & AI", "#/connections", "layers", "connections models providers accounts"),
        nav("Settings", "#/settings", "sliders", "preferences workspace appearance"),
        { kind: "Go to", label: "Models", icon: "gear", keywords: "model routes", run: () => { location.href = "/models"; } },
        { kind: "Go to", label: "Usage", icon: "chart", keywords: "tokens cost spending", run: () => { location.href = "/usage"; } },
      ];
      const actions = [
        ...(ctx.hasModelPicker?.() ? [{ kind: "Action", label: "Choose a model", icon: "zap", keywords: "model switch change ai route provider", run: () => ctx.openModelPicker() }] : []),
        { kind: "Action", label: "New assistant", icon: "users", keywords: "create helper bot", run: () => { location.hash = "#/assistant/new"; } },
        { kind: "Action", label: "Search messages", icon: "search", keywords: "find text in chats", run: () => ctx.searchMessages() },
      ];
      return [...actions, ...go];
    }

    function render() {
      const query = input.value.trim();
      visible = entries.filter(entry => matches(entry, query)).slice(0, 40);
      active = Math.min(active, Math.max(0, visible.length - 1));
      if (!visible.length) {
        list.innerHTML = `<li class="palette-empty" role="presentation">No match for “${esc(query)}”. Try an assistant name or a page.</li>`;
        input.removeAttribute("aria-activedescendant");
        status.textContent = "No results";
        return;
      }
      let html = "", lastKind = "";
      visible.forEach((entry, index) => {
        if (entry.kind !== lastKind) {
          html += `${lastKind ? "</ul></li>" : ""}<li role="presentation" class="palette-group"><span class="palette-group-title" aria-hidden="true">${esc(entry.kind)}</span><ul role="group" aria-label="${esc(entry.kind)}">`;
          lastKind = entry.kind;
        }
        html += `<li id="palette-opt-${index}" class="palette-row" role="option" data-palette-index="${index}" aria-selected="${index === active}">
          <span class="palette-ico" aria-hidden="true">${entry.avatar || ctx.icon(entry.icon || "chat")}</span>
          <span class="palette-label">${esc(entry.label)}</span>
          ${entry.hint ? `<span class="palette-hint">${esc(entry.hint)}</span>` : ""}
        </li>`;
      });
      html += "</ul></li>";
      list.innerHTML = html;
      input.setAttribute("aria-activedescendant", `palette-opt-${active}`);
      status.textContent = `${visible.length} result${visible.length === 1 ? "" : "s"}`;
    }

    function setActive(next, scroll = true) {
      if (!visible.length) return;
      active = (next + visible.length) % visible.length;
      list.querySelectorAll("[aria-selected]").forEach(row => row.setAttribute("aria-selected", String(Number(row.dataset.paletteIndex) === active)));
      input.setAttribute("aria-activedescendant", `palette-opt-${active}`);
      if (scroll) document.getElementById(`palette-opt-${active}`)?.scrollIntoView({ block: "nearest" });
    }
    const move = delta => setActive(active + delta);

    function run(entry) {
      if (!entry) return;
      close();
      // Let the dialog finish closing (and restore focus) before the destination takes over.
      setTimeout(() => entry.run(), 0);
    }

    async function load() {
      const token = ++loadToken;
      entries = staticEntries();
      for (const bot of ctx.bots()) {
        entries.unshift({
          kind: "Assistants", label: ctx.botName(bot), hint: ctx.botRole(bot) || "", keywords: bot.name,
          avatar: ctx.avatar(bot.name), run: () => { location.hash = `#/chat/${encodeURIComponent(bot.name)}`; },
        });
      }
      render();
      try {
        const conversations = await ctx.recentConversations();
        if (token !== loadToken) return;
        const byBot = new Map(ctx.bots().map(bot => [bot.id, bot]));
        const recent = conversations.filter(item => !item.archived).slice(0, 12).map(item => ({
          kind: "Recent chats", label: item.title || "New conversation", icon: "chat",
          hint: byBot.get(item.bot_id) ? ctx.botName(byBot.get(item.bot_id)) : "",
          keywords: item.section || "", run: () => { location.hash = `#/conversation/${encodeURIComponent(item.id)}`; },
        }));
        // Assistants first, then chats, then actions and pages.
        const assistants = entries.filter(entry => entry.kind === "Assistants");
        const rest = entries.filter(entry => entry.kind !== "Assistants");
        entries = [...assistants, ...recent, ...rest];
        render();
      } catch { /* the palette still works with assistants and pages */ }
    }

    function open() {
      if (!dialog) build();
      if (dialog.open) return;
      // A modal already on screen (a confirmation, the review drawer) keeps priority.
      if (document.querySelector("#modal-root .modal-card") || document.getElementById("needs-you")?.open) return;
      trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      input.value = "";
      active = 0;
      dialog.showModal();
      void load();
      input.focus();
    }
    // Focus returns to where the person was, synchronously, so keyboard users never land on <body>.
    function restoreFocus() {
      const target = trigger;
      trigger = null;
      if (target?.isConnected) target.focus({ preventScroll: true });
    }
    function close() {
      if (!dialog?.open) return;
      dialog.close();
      restoreFocus();
    }

    document.addEventListener("keydown", event => {
      if (event.defaultPrevented || event.shiftKey || event.altKey) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog?.open) close(); else open();
      }
    });

    return { open, close };
  }

  root.HutchPalette = { init, matches };
})(typeof window !== "undefined" ? window : globalThis);
