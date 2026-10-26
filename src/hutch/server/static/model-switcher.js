/* Model switcher for the chat composer.
 *
 * A compact menu (the bot's own model first, then what is usable right now, a check on the one in use) and an
 * "All models" dialog for everything else, including what needs setup and why. A selected route overrides the
 * next message in this conversation only; an accepted send consumes the override. Saving it as the Bot default
 * is a separate, explicit action. Data comes from GET /api/bots/<name>/models; the server validates on send and save.
 */
(function () {
  "use strict";

  const COMPACT_MAX = 5;
  const SVG = {
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    cloud: '<path d="M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9.5a4.2 4.2 0 0 1-.5 8.5z"/>',
  };
  const ico = (n, size = 16) =>
    `<svg class="ms-ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SVG[n] || ""}</svg>`;
  const escHtml = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const shortName = spec => String(spec).split("/").slice(1).join("/") || String(spec);
  const dollars = value => value === 0 ? "$0" : value < 0.0001 ? "less than $0.0001"
    : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(value);

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch { /* private mode */ } },
  };

  function mount(slot, bot, conversationId, onSelectionChange) {
    if (!slot) return null;
    const key = `hutch.model.${bot.id}.${conversationId || "none"}`;
    let data = { default: bot.model, models: [{ spec: bot.model, label: shortName(bot.model), group: "This bot",
                                                  state: "ready", default: true, note: "this bot's own model" }] };
    let selected = store.get(key) || "";
    let refreshRevision = 0;

    const find = spec => data.models.find(m => m.spec === spec);
    const active = () => (selected && (find(selected) || /\//.test(selected))) ? selected : data.default;
    const usable = m => m && m.state === "ready";
    const announceSelection = () => onSelectionChange?.(selected && selected !== data.default ? selected : "");

    slot.innerHTML = `
      <div class="ms-wrap">
        <button type="button" class="ms-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="ms-menu-${escHtml(bot.name)}">
          <span class="ms-route-icon" aria-hidden="true"></span><span class="ms-label"></span>${ico("chevron", 14)}
        </button>
        <div class="ms-menu" id="ms-menu-${escHtml(bot.name)}" role="menu" aria-label="Choose a model" hidden></div>
      </div>`;
    const btn = slot.querySelector(".ms-btn");
    const menu = slot.querySelector(".ms-menu");
    const label = slot.querySelector(".ms-label");
    const popup = window.hutchControls.popup({ trigger: btn, panel: menu, kind: "menu", side: "top",
      onOpen: () => { renderMenu(); void refresh({ discover: true }); } });

    function paintButton() {
      const spec = active();
      const m = find(spec);
      const custom = spec !== data.default;
      label.textContent = m ? m.label : shortName(spec);
      slot.querySelector(".ms-route-icon").innerHTML = ico(m?.hosted === false ? "chip" : "cloud");
      btn.classList.toggle("is-custom", custom);
      btn.title = custom ? `One-message override: ${spec}. The Bot default stays ${data.default}; this override clears after the next message is accepted.`
                         : `Model: ${spec} (this Bot's default). Choose another route for one message or save it as the Bot default.`;
      btn.setAttribute("aria-label", custom
        ? `Model: ${m ? m.label : shortName(spec)}. One-message override for this conversation; Bot default is ${shortName(data.default)}. Change model.`
        : `Model: ${m ? m.label : shortName(spec)}. Bot default. Change model.`);
    }

    function choose(spec) {
      selected = spec === data.default ? "" : spec;
      store.set(key, selected);
      paintButton();
      announceSelection();
      closeMenu(true);
      if (selected) toast(`${shortName(spec)} is selected for the next message in this conversation. Bot default stays ${shortName(data.default)}.`);
    }

    function consumeOverride(spec) {
      if (!spec || selected !== spec || spec === data.default) return false;
      selected = "";
      store.set(key, "");
      paintButton();
      announceSelection();
      return true;
    }

    function setLocalDefault(spec) {
      data.default = spec;
      data.models = data.models.map(m => ({ ...m, default: m.spec === spec }));
      if (!data.models.some(m => m.spec === spec)) {
        data.models.unshift({ spec, label: shortName(spec), group: "This bot", state: "ready",
                              default: true, note: "this bot's own model" });
      }
      bot.model = spec;
    }

    async function saveAsDefault(button) {
      const spec = active();
      button.disabled = true;
      try {
        const saved = await api(`/bots/${encodeURIComponent(bot.name)}`, {
          method: "PATCH", body: { model: spec },
        });
        setLocalDefault(saved.model);
        selected = "";
        store.set(key, "");
        paintButton();
        announceSelection();
        await refresh();
        closeMenu(true);
        toast(`Saved ${shortName(saved.model)} as ${bot.name}'s default. Future and scheduled runs will use it.`);
      } catch (err) {
        button.disabled = false;
        toast(`Could not save this Bot's model default: ${err.message}`, true);
      }
    }

    function item(m) {
      const on = active() === m.spec;
      return `<button type="button" class="ms-item" role="menuitemradio" tabindex="-1" aria-checked="${on}" data-spec="${escHtml(m.spec)}" ${usable(m) ? "" : 'disabled aria-disabled="true"'}>
        <span class="ms-item-main"><span class="ms-item-name">${escHtml(m.label)}</span>
          ${m.default ? '<span class="ms-tag">default</span>' : ""}
          <span class="ms-item-note">${escHtml(m.hosted ? `${m.group} · leaves this machine` : "On this machine")}</span>
          ${m.note ? `<span class="ms-item-note">${escHtml(m.note)}</span>` : ""}</span>
        <span class="ms-item-check">${on ? ico("check", 16) : ""}</span></button>`;
    }

    function renderMenu() {
      const ready = data.models.filter(usable);
      const shown = [];
      const def = data.models.find(m => m.default);      // the bot's own model is always listed, usable or not
      if (def) shown.push(def);
      for (const m of ready) if (!m.default && shown.length < COMPACT_MAX) shown.push(m);
      const cur = find(active());
      if (cur && usable(cur) && !shown.includes(cur)) shown.splice(1, 0, cur);   // the one in use is always visible
      const hidden = data.models.length - shown.length;
      menu.innerHTML = '<div class="hc-popup-label">Model for the next message</div>' + shown.map(item).join("") +
        `<div class="ms-sep" role="separator"></div>
         <button type="button" class="ms-item ms-more" role="menuitem" tabindex="-1" data-more>
           <span class="ms-item-main"><span class="ms-item-name">All models</span>
             <span class="ms-item-note">${hidden > 0 ? `${hidden} more, with what each needs` : "fit, cost and setup for each"}</span></span></button>
         ${active() !== data.default ? `<div class="ms-sep" role="separator"></div>
          <button type="button" class="ms-item ms-save-default" role="menuitem" tabindex="-1" data-save-default>
           <span class="ms-item-main"><span class="ms-item-name">Save as Bot default</span>
             <span class="ms-item-note">${escHtml(shortName(active()))}; future chats and scheduled runs use this route.</span></span></button>` : ""}`;
    }

    const items = () => Array.from(menu.querySelectorAll(".ms-item"));

    async function refresh({ discover = false, query = "" } = {}) {
      const revision = ++refreshRevision;
      try {
        const params = new URLSearchParams();
        if (discover) params.set("discover", "1");
        if (query) params.set("q", query);
        const encoded = params.toString();
        const suffix = encoded ? `?${encoded}` : "";
        const fresh = await api(`/bots/${encodeURIComponent(bot.name)}/models${suffix}`);
        if (revision !== refreshRevision || !slot.isConnected) return;
        data = fresh;
        paintButton();
        announceSelection();
        if (!menu.hidden) {                              // re-render without dropping the keyboard user's place
          const had = menu.contains(document.activeElement) ? document.activeElement : null;
          const spec = had && had.dataset.spec, more = had && had.hasAttribute("data-more"),
            saveDefault = had && had.hasAttribute("data-save-default");
          renderMenu();
          popup.place();
          if (had) (items().find(i => (spec && i.dataset.spec === spec) || (more && i.hasAttribute("data-more"))) ||
                    items().find(i => saveDefault && i.hasAttribute("data-save-default")) || items()[0])?.focus();
        }
        return true;
      } catch {
        if (revision !== refreshRevision || !slot.isConnected) return;
        if (!menu.hidden && !menu.querySelector(".ms-refresh-error")) {
          const status = document.createElement("p");
          status.className = "ms-refresh-error hc-popup-empty";
          status.setAttribute("role", "status");
          status.textContent = "Could not refresh models. Showing the last available choices.";
          menu.append(status);
          popup.place();
        }
        return false;
      }
    }

    function openMenu() {
      popup.open();
    }
    function closeMenu(returnFocus) {
      popup.close(returnFocus);
    }

    btn.addEventListener("click", () => (menu.hidden ? openMenu() : closeMenu(true)));
    menu.addEventListener("click", async ev => {
      const it = ev.target.closest(".ms-item");
      if (!it || it.disabled) return;
      if (it.hasAttribute("data-more")) { closeMenu(false); openAll(); return; }
      if (it.hasAttribute("data-save-default")) { await saveAsDefault(it); return; }
      choose(it.dataset.spec);
    });

    // ------------------------------------------------------------- the full list
    async function openAll() {
      const refreshed = await refresh({ discover: true }); // explicit catalog request, no inference
      if (!slot.isConnected) return;
      const cur = active();
      let draftSpec = cur;
      const row = m => {
        const ok = usable(m);
        let sub = ok ? (m.note || "") : (m.fix || m.note || "");     // the fix already says why it is off
        if (ok && m.worst_case_usd != null) sub += ` · estimated ${dollars(m.worst_case_usd)} per run`;
        return `<label class="ms-row ${ok ? "" : "is-off"}" data-text="${escHtml((m.spec + " " + m.label + " " + m.group).toLowerCase())}">
          <input type="radio" name="ms-pick" value="${escHtml(m.spec)}" ${ok ? "" : "disabled"} ${m.spec === draftSpec ? "checked" : ""}>
          <span class="ms-row-main"><span class="ms-row-name">${escHtml(m.label)}
              ${m.default ? '<span class="ms-tag">default</span>' : ""}
              ${m.hosted ? `<span class="ms-tag ms-hosted" title="This chat is sent to the provider">${ico("cloud", 11)} leaves this machine</span>` : ""}
              ${ok ? "" : `<span class="ms-tag ms-warn">${m.state === "wont_fit" ? "won't fit" : "needs setup"}</span>`}</span>
            <span class="ms-row-note">${escHtml(sub)}</span></span></label>`;
      };
      const body = `
        <div class="ms-all">
          <p class="ms-scope">For your next message only. ${escHtml(bot.display_name || bot.name)} keeps its saved model for future messages and scheduled work.</p>
          <input type="text" role="searchbox" class="ms-search" placeholder="Search available models" aria-label="Search available models" autocomplete="off" spellcheck="false" enterkeyhint="search">
          <p class="ms-search-status" role="status" aria-live="polite">${refreshed ? "" : "Could not refresh models. Showing the last available choices; check the connection and reopen to retry."}</p>
          <div class="ms-groups" role="radiogroup" aria-label="Models"></div>
          <div class="ms-selection" role="status" aria-live="polite"></div>
          <details class="ms-selection-details"><summary>Selected route and details</summary><div class="ms-selection-info"></div></details>
          <details class="ms-advanced"><summary>Enter a model ID</summary>
          <label class="ms-other">Another model <span class="muted">(provider/model, on one of your connections)</span>
            <input type="text" class="ms-custom mono" aria-describedby="ms-custom-egress-note" placeholder="opencode-go/glm-5.3" autocomplete="off" spellcheck="false">
            <span id="ms-custom-egress-note" class="muted">An openai-compatible route uses its configured endpoint and may send this chat off this machine. Confirm the provider endpoint for this Bot or Hutch installation before selecting it.</span></label></details>
          <p class="ms-foot"><a href="/models">Hardware fit, task presets and prices</a> &middot;
            <a href="/connections">Connections</a></p>
        </div>`;
      openModal({
        title: "Choose a model", bodyHtml: body, confirmText: "Use for next message", returnFocus: btn, wide: true,
        onConfirm: () => {
          const root = document.getElementById("modal-root");
          const custom = root.querySelector(".ms-custom").value.trim();
          const radio = root.querySelector('input[name="ms-pick"]:checked');
          const spec = custom || (radio && radio.value) || draftSpec;
          if (!spec) return false;
          if (!custom && find(spec) && !usable(find(spec))) {
            toast("This model is no longer available. Choose another model or check its connection.", true);
            return false;
          }
          if (custom && !/^[^/\s]+\/\S+$/.test(custom)) {
            toast("Write it as provider/model, for example opencode-go/glm-5.3", true);
            return false;
          }
          selected = spec === data.default ? "" : spec;
          store.set(key, selected);
          paintButton();
          announceSelection();
          if (selected) toast(`${shortName(spec)} is selected for the next message in this conversation. Bot default stays ${shortName(data.default)}.`);
          return true;
        },
      });
      const root = document.getElementById("modal-root");
      const search = root.querySelector(".ms-search");
      const groupList = root.querySelector(".ms-groups");
      const searchStatus = root.querySelector(".ms-search-status");
      const custom = root.querySelector(".ms-custom");
      const selection = root.querySelector(".ms-selection");
      const selectionInfo = root.querySelector(".ms-selection-info");
      const paintSelection = () => {
        const spec = custom.value.trim() || draftSpec;
        const model = find(spec);
        selection.textContent = `Next message: ${model?.label || shortName(spec)}`;
        const details = model?.detail || ["Custom route; availability and permissions are checked when you send."];
        selectionInfo.innerHTML = `<code>${escHtml(spec)}</code><ul>${details.map(line => `<li>${escHtml(line)}</li>`).join("")}</ul>`;
      };
      groupList.addEventListener("change", event => {
        if (event.target.matches('input[name="ms-pick"]')) {
          draftSpec = event.target.value;
          custom.value = "";
          paintSelection();
        }
      });
      custom.addEventListener("input", paintSelection);
      const renderGroups = (models, query = "") => {
        const groups = [];
        for (const model of models) {
          let group = groups.find(item => item.name === model.group);
          if (!group) groups.push(group = { name: model.group, list: [] });
          group.list.push(model);
        }
        const rank = { "This bot": 0, "On this machine": 1, "Hosted": 2 };
        groups.sort((a, b) => (rank[a.name] ?? 3) - (rank[b.name] ?? 3));
        groupList.innerHTML = groups.map(group =>
          `<section class="ms-group"><h4>${escHtml(group.name)}</h4>${group.list.map(row).join("")}</section>`).join("") +
          '<p class="ms-empty" hidden>No model matches. Try a different name or enter its ID below.</p>';
        const q = query.trim().toLowerCase();
        let any = false;
        root.querySelectorAll(".ms-row").forEach(item => {
          const hit = !q || item.dataset.text.includes(q);
          item.hidden = !hit;
          any = any || hit;
        });
        root.querySelectorAll(".ms-group").forEach(group => {
          group.hidden = !group.querySelector(".ms-row:not([hidden])");
        });
        root.querySelector(".ms-empty").hidden = any;
      };
      renderGroups(data.models);
      paintSelection();
      let searchTimer = 0;
      let searchRevision = 0;
      search.addEventListener("input", () => {
        const query = search.value.trim();
        renderGroups(data.models, query);
        if (searchTimer) clearTimeout(searchTimer);
        const revision = ++searchRevision;
        if (query.length < 2 || !data.models.some(model => model.catalog_search)) {
          searchStatus.textContent = "";
          return;
        }
        searchStatus.textContent = "Searching connected model catalogs…";
        searchTimer = setTimeout(async () => {
          if (!search.isConnected) return;
          try {
            const params = new URLSearchParams({ discover: "1", q: query });
            const fresh = await api(`/bots/${encodeURIComponent(bot.name)}/models?${params.toString()}`);
            if (!search.isConnected || revision !== searchRevision || search.value.trim() !== query) return;
            data = fresh;
            paintButton();
            renderGroups(data.models, query);
            paintSelection();
            searchStatus.textContent = "";
          } catch {
            if (revision === searchRevision) {
              searchStatus.textContent = "Could not search OpenRouter models right now. Check the connection and try again.";
            }
          }
        }, 300);
      });
    }

    paintButton();
    refresh();
    return { selected: () => (active() === data.default ? "" : active()), consumeOverride, refresh };
  }

  window.hutchModelSwitcher = { mount };
})();
