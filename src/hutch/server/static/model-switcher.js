/* Model switcher for the chat composer.
 *
 * A compact menu (the bot's own model first, then what is usable right now, a check on the one in use) and an
 * "All models" dialog for everything else, including what needs setup and why. Picking a model applies to the
 * messages you send from this chat; it never edits the bot, so scheduled runs keep using the bot's own model.
 * Data comes from GET /api/bots/<name>/models; the server validates the choice again when a message is sent.
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

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch { /* private mode */ } },
  };

  function mount(slot, bot) {
    if (!slot) return null;
    const key = `hutch.model.${bot.name}`;
    let data = { default: bot.model, models: [{ spec: bot.model, label: shortName(bot.model), group: "This bot",
                                                  state: "ready", default: true, note: "this bot's own model" }] };
    let selected = store.get(key) || "";

    const find = spec => data.models.find(m => m.spec === spec);
    const active = () => (selected && (find(selected) || /\//.test(selected))) ? selected : data.default;
    const usable = m => m && m.state === "ready";

    slot.innerHTML = `
      <div class="ms-wrap">
        <button type="button" class="ms-btn" aria-haspopup="menu" aria-expanded="false" aria-controls="ms-menu-${escHtml(bot.name)}">
          <span class="ms-dot" aria-hidden="true"></span><span class="ms-label"></span>${ico("chevron", 14)}
        </button>
        <div class="ms-menu" id="ms-menu-${escHtml(bot.name)}" role="menu" aria-label="Choose a model" hidden></div>
      </div>`;
    const btn = slot.querySelector(".ms-btn");
    const menu = slot.querySelector(".ms-menu");
    const label = slot.querySelector(".ms-label");

    function paintButton() {
      const spec = active();
      const m = find(spec);
      const custom = spec !== data.default;
      label.textContent = m ? m.label : shortName(spec);
      btn.classList.toggle("is-custom", custom);
      btn.title = custom ? `Using ${spec} for this chat. The bot's own model is ${data.default}.`
                         : `Model: ${spec} (this bot's own). Click to switch for this chat.`;
      btn.setAttribute("aria-label", `Model: ${m ? m.label : shortName(spec)}. Change model`);
    }

    function choose(spec) {
      selected = spec === data.default ? "" : spec;
      store.set(key, selected);
      paintButton();
      closeMenu(true);
    }

    function item(m) {
      const on = active() === m.spec;
      return `<button type="button" class="ms-item" role="menuitemradio" aria-checked="${on}" data-spec="${escHtml(m.spec)}">
        <span class="ms-item-main"><span class="ms-item-name">${escHtml(m.label)}</span>
          ${m.default ? '<span class="ms-tag">default</span>' : ""}
          <span class="ms-item-note">${escHtml(m.note || "")}</span></span>
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
      menu.innerHTML = shown.map(item).join("") +
        `<div class="ms-sep" role="separator"></div>
         <button type="button" class="ms-item ms-more" role="menuitem" data-more>
           <span class="ms-item-main"><span class="ms-item-name">All models</span>
             <span class="ms-item-note">${hidden > 0 ? `${hidden} more, with what each needs` : "fit, cost and setup for each"}</span></span></button>`;
    }

    const items = () => Array.from(menu.querySelectorAll(".ms-item"));
    function focusItem(i) { const l = items(); if (l.length) l[(i + l.length) % l.length].focus(); }
    function onOutside(ev) { if (!slot.contains(ev.target)) closeMenu(false); }

    async function refresh() {
      try {
        const fresh = await api(`/bots/${encodeURIComponent(bot.name)}/models`);
        data = fresh;
        paintButton();
        if (!menu.hidden) {                              // re-render without dropping the keyboard user's place
          const had = menu.contains(document.activeElement) ? document.activeElement : null;
          const spec = had && had.dataset.spec, more = had && had.hasAttribute("data-more");
          renderMenu();
          if (had) (items().find(i => (spec && i.dataset.spec === spec) || (more && i.hasAttribute("data-more"))) ||
                    items()[0])?.focus();
        }
      } catch { /* keep what we have: the button still works with the bot's own model */ }
    }

    function openMenu() {
      renderMenu();
      menu.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      document.addEventListener("mousedown", onOutside, true);
      const checked = items().findIndex(i => i.getAttribute("aria-checked") === "true");
      focusItem(Math.max(0, checked));
      refresh();
    }
    function closeMenu(returnFocus) {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
      document.removeEventListener("mousedown", onOutside, true);
      if (returnFocus) btn.focus();
    }

    btn.addEventListener("click", () => (menu.hidden ? openMenu() : closeMenu(true)));
    btn.addEventListener("keydown", ev => {
      if (menu.hidden && (ev.key === "ArrowUp" || ev.key === "ArrowDown")) { ev.preventDefault(); openMenu(); }
    });
    menu.addEventListener("click", ev => {
      const it = ev.target.closest(".ms-item");
      if (!it) return;
      if (it.hasAttribute("data-more")) { closeMenu(false); openAll(); return; }
      choose(it.dataset.spec);
    });
    menu.addEventListener("keydown", ev => {
      const l = items(), i = l.indexOf(document.activeElement);
      if (ev.key === "ArrowDown") { ev.preventDefault(); focusItem(i + 1); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); focusItem(i - 1); }
      else if (ev.key === "Home") { ev.preventDefault(); focusItem(0); }
      else if (ev.key === "End") { ev.preventDefault(); focusItem(l.length - 1); }
      else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeMenu(true); }
      else if (ev.key === "Tab") closeMenu(false);
    });

    // ------------------------------------------------------------- the full list
    async function openAll() {
      await refresh();                                   // never show a stale list
      const groups = [];
      for (const m of data.models) {
        let g = groups.find(x => x.name === m.group);
        if (!g) groups.push(g = { name: m.group, list: [] });
        g.list.push(m);
      }
      const rank = { "This bot": 0, "On this machine": 1, "Hosted": 2 };
      groups.sort((a, b) => (rank[a.name] ?? 3) - (rank[b.name] ?? 3));
      const cur = active();
      const row = m => {
        const ok = usable(m);
        const sub = ok ? (m.note || "") : (m.fix || m.note || "");     // the fix already says why it is off
        return `<label class="ms-row ${ok ? "" : "is-off"}" data-text="${escHtml((m.spec + " " + m.label + " " + m.group).toLowerCase())}">
          <input type="radio" name="ms-pick" value="${escHtml(m.spec)}" ${ok ? "" : "disabled"} ${m.spec === cur ? "checked" : ""}>
          <span class="ms-row-main"><span class="ms-row-name">${escHtml(m.label)}
              ${m.default ? '<span class="ms-tag">default</span>' : ""}
              ${m.hosted ? `<span class="ms-tag ms-hosted" title="This chat is sent to the provider">${ico("cloud", 11)} leaves this machine</span>` : ""}
              ${ok ? "" : `<span class="ms-tag ms-warn">${m.state === "wont_fit" ? "won't fit" : "needs setup"}</span>`}</span>
            <span class="ms-row-note">${escHtml(sub)}</span></span></label>`;
      };
      const body = `
        <div class="ms-all">
          <input type="text" role="searchbox" class="ms-search" placeholder="Filter models" aria-label="Filter models" autocomplete="off" spellcheck="false">
          <div class="ms-groups" role="radiogroup" aria-label="Models">
            ${groups.map(g => `<section class="ms-group"><h4>${escHtml(g.name)}</h4>${g.list.map(row).join("")}</section>`).join("")}
            <p class="ms-empty" hidden>No model matches that filter.</p>
          </div>
          <label class="ms-other">Another model <span class="muted">(provider/model, for example a model on one of your connections)</span>
            <input type="text" class="ms-custom mono" placeholder="opencode-go/glm-5.3" autocomplete="off" spellcheck="false"></label>
          <p class="ms-foot"><a href="/models">Hardware fit, task presets and prices</a> &middot;
            <a href="/connections">Connections</a></p>
        </div>`;
      openModal({
        title: "Choose a model for this chat", bodyHtml: body, confirmText: "Use this model",
        onConfirm: () => {
          const root = document.getElementById("modal-root");
          const custom = root.querySelector(".ms-custom").value.trim();
          const radio = root.querySelector('input[name="ms-pick"]:checked');
          const spec = custom || (radio && radio.value);
          if (!spec) return false;
          if (custom && !/^[^/\s]+\/\S+$/.test(custom)) {
            toast("Write it as provider/model, for example opencode-go/glm-5.3", true);
            return false;
          }
          selected = spec === data.default ? "" : spec;
          store.set(key, selected);
          paintButton();
          return true;
        },
      });
      const root = document.getElementById("modal-root");
      const search = root.querySelector(".ms-search");
      search.addEventListener("input", () => {
        const q = search.value.trim().toLowerCase();
        let any = false;
        root.querySelectorAll(".ms-row").forEach(r => {
          const hit = !q || r.dataset.text.includes(q);
          r.hidden = !hit;
          any = any || hit;
        });
        root.querySelectorAll(".ms-group").forEach(g => { g.hidden = !g.querySelector(".ms-row:not([hidden])"); });
        root.querySelector(".ms-empty").hidden = any;
      });
    }

    paintButton();
    refresh();
    return { selected: () => (active() === data.default ? "" : active()), refresh };
  }

  window.hutchModelSwitcher = { mount };
})();
