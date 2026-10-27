/* Shared popup lifecycle. Data and authority stay with each caller; this module
   owns placement, keyboard movement and dismissal, never application actions.
   Keep panels in their owner's DOM (including native dialogs); top-layer popovers
   avoid clipping without a body portal or a second modal focus trap. */
(function () {
  "use strict";
  const live = new Set();
  let layoutFrame = 0;
  const resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(() => {
    if (!layoutFrame) layoutFrame = requestAnimationFrame(() => { layoutFrame = 0; reposition(); });
  }) : null;
  let serial = 0;
  const visible = node => node?.isConnected && node.getClientRects().length && !node.closest("[hidden]");
  const focusables = root => [...root.querySelectorAll("button, a[href], input, select, textarea, summary, [tabindex]")]
    .filter(node => visible(node) && !node.disabled && node.getAttribute("aria-disabled") !== "true");

  function popup({ trigger, panel, kind = "dialog", side = "bottom", triggerKeys = true, matchWidth = false, onOpen = null, onClose = null }) {
    if (!trigger || !panel) return null;
    const abort = new AbortController();
    const options = { signal: abort.signal };
    const topLayer = typeof panel.showPopover === "function";
    let opened = false;
    let typed = "", typedAt = 0;
    panel.id ||= `hutch-popup-${++serial}`;
    panel.classList.add("hc-popup");
    panel.dataset.popupKind = kind;
    panel.setAttribute("role", kind);
    panel.hidden = true;
    if (topLayer) panel.setAttribute("popover", "manual");
    trigger.setAttribute("aria-haspopup", kind);
    trigger.setAttribute("aria-controls", panel.id);
    trigger.setAttribute("aria-expanded", "false");
    if (kind === "dialog") {
      const header = document.createElement("div");
      header.className = "hc-popup-header";
      const title = document.createElement("span");
      title.textContent = panel.getAttribute("aria-label") || trigger.getAttribute("aria-label") || "Options";
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "hc-popup-close";
      dismiss.textContent = "Done";
      dismiss.setAttribute("aria-label", `Done, close ${title.textContent.toLowerCase()}`);   // begins with the visible word (WCAG 2.5.3)
      dismiss.addEventListener("click", () => close(true), options);
      header.append(title, dismiss);
      panel.prepend(header);
    }

    function place() {
      if (!opened) return;
      const viewport = window.visualViewport;
      const x = viewport?.offsetLeft || 0, y = viewport?.offsetTop || 0;
      const width = viewport?.width || innerWidth, height = viewport?.height || innerHeight;
      const gap = 8, inset = 8;
      const anchor = trigger.getBoundingClientRect();
      if (matchWidth) panel.style.width = `${Math.min(anchor.width, width - inset * 2)}px`;
      panel.style.maxWidth = `${Math.max(0, width - inset * 2)}px`;
      panel.style.maxHeight = `${Math.max(0, height - inset * 2)}px`;
      // Measure the panel at its natural size. A sheet is capped to stay clear of its trigger, so measuring one that is
      // already a sheet would read it as shorter, pick anchored, grow, and flip back on the next resize notification.
      panel.dataset.popupLayout = "anchored";
      const bounds = panel.getBoundingClientRect();
      const below = y + height - anchor.bottom - gap - inset;
      const above = anchor.top - y - gap - inset;
      const upwards = side === "top" ? above >= Math.min(bounds.height, below) : below < Math.min(bounds.height, above);
      const room = Math.max(above, below);
      // Rich panels become a bounded sheet only when anchoring cannot provide a
      // usable viewport. Short action menus stay attached to their trigger.
      const sheet = kind === "dialog" && width <= 560 && (bounds.height > room || height < 480);
      panel.dataset.popupLayout = sheet ? "sheet" : "anchored";
      panel.style.maxHeight = `${Math.max(96, sheet ? height - inset * 2 : (upwards ? above : below))}px`;
      const final = panel.getBoundingClientRect();
      panel.style.left = `${sheet ? x + inset : Math.max(x + inset, Math.min(anchor.right - final.width, x + width - final.width - inset))}px`;
      panel.style.top = `${sheet ? y + height - final.height - inset : Math.max(y + inset, upwards ? anchor.top - final.height - gap : anchor.bottom + gap)}px`;
    }
    function close(restoreFocus = false) {
      if (!opened) return;
      opened = false;
      live.delete(api);
      resizeObserver?.unobserve(panel);
      if (topLayer && panel.matches(":popover-open")) panel.hidePopover();
      panel.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      onClose?.();
      if (restoreFocus && visible(trigger)) trigger.focus({ preventScroll: true });
    }
    function open({ focus = true } = {}) {
      for (const other of [...live]) {
        if (other !== api && !other.panel.contains(trigger)) other.close(false);
      }
      if (!opened) onOpen?.();
      opened = true;
      if (trigger.parentElement instanceof HTMLDetailsElement) trigger.parentElement.open = true;
      panel.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      if (topLayer && !panel.matches(":popover-open")) panel.showPopover();
      live.add(api);
      resizeObserver?.observe(panel);
      place();
      if (focus) {
        const selected = focusables(panel).find(node => node.matches('[aria-checked="true"], [aria-selected="true"]'));
        (selected || focusables(panel).find(node => !node.closest(".hc-popup-header")) || panel).focus({ preventScroll: true });
      }
    }
    function navigate(event) {
      if (kind !== "menu" || event.target.closest("input, select, textarea")) return;
      const items = focusables(panel).filter(node => node.matches('[role^="menuitem"]'));
      const index = items.indexOf(document.activeElement);
      let next = -1;
      if (event.key === "ArrowDown") next = (index + 1) % items.length;
      if (event.key === "ArrowUp") next = (index + items.length - 1) % items.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = items.length - 1;
      if (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.altKey && !event.metaKey) {
        const now = performance.now();
        typed = now - typedAt > 700 ? event.key : typed + event.key;
        typedAt = now;
        const query = typed.toLocaleLowerCase();
        const ordered = [...items.slice(index + 1), ...items.slice(0, index + 1)];
        const match = ordered.find(node => node.textContent.trim().toLocaleLowerCase().startsWith(query));
        if (match) next = items.indexOf(match);
      }
      if (next >= 0 && items[next]) {
        event.preventDefault();
        event.stopImmediatePropagation();
        items[next].focus();
      }
    }
    panel.addEventListener("keydown", navigate, options);
    trigger.addEventListener("keydown", event => {
      if (!triggerKeys) return;
      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      open();
      if (event.key === "ArrowUp" && kind === "menu") focusables(panel).at(-1)?.focus();
    }, options);
    const api = { panel, trigger, open, close, place, get opened() { return opened; },
      destroy() { close(); abort.abort(); panel.removeAttribute("popover"); } };
    return api;
  }

  // One set of document listeners, independent of how often a chat is rendered.
  document.addEventListener("pointerdown", event => {
    for (const item of [...live].reverse()) {
      if (!item.panel.contains(event.target) && !item.trigger.contains(event.target)) item.close(false);
    }
  }, true);
  document.addEventListener("focusin", event => {
    for (const item of [...live].reverse()) {
      if (!item.panel.contains(event.target) && !item.trigger.contains(event.target)) item.close(false);
    }
  });
  document.addEventListener("keydown", event => {
    const item = [...live].at(-1);
    if (!item) return;
    if (event.key === "Escape") {
      // Let the browser dismiss its own select picker, but do not let an outer
      // app/modal handler consume that same Escape and cancel the form layer.
      if (CSS.supports("selector(select:open)") && document.querySelector("select:open")) {
        event.stopImmediatePropagation();
        return;
      }
      // An inline details section consumes its own first Escape, before its
      // enclosing form popover. Native select pickers retain browser handling.
      const nested = event.target.closest("details[open]");
      if (nested && item.panel.contains(nested)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        nested.open = false;
        nested.querySelector(":scope > summary")?.focus({ preventScroll: true });
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      item.close(true);
    } else if (event.key === "Tab" && item.panel.getAttribute("role") === "menu") {
      item.close(true); // default Tab continues from the trigger, not a hidden row
    }
  }, true);
  function reposition(event) {
    for (const item of live) {
      if (event?.type === "scroll" && item.panel.contains(event.target)) continue;
      item.place();
    }
  }
  window.addEventListener("resize", reposition, { passive: true });
  document.addEventListener("scroll", reposition, { capture: true, passive: true });
  window.visualViewport?.addEventListener("resize", reposition, { passive: true });
  window.visualViewport?.addEventListener("scroll", reposition, { passive: true });

  // Pure action disclosures get menu semantics; mixed controls get a dialog
  // popover with normal Tab order. Ordinary inline <details> are not menus.
  const disclosures = new WeakMap();
  const suggestions = new WeakMap();
  const selector = ".fleet-card-menu, .assistant-settings-menu, .conversation-actions";

  function autocomplete(input) {
    if (suggestions.has(input)) return;
    const datalist = document.getElementById(input.getAttribute("list"));
    if (!(datalist instanceof HTMLDataListElement)) return;
    const panel = document.createElement("div");
    panel.className = "hc-suggestions";
    panel.setAttribute("aria-label", "Available model routes");
    // A sibling of the label, not interactive options inside a <label>. This
    // stays in the owning page/dialog; there is no body portal.
    (input.closest("label") || input).after(panel);
    input.removeAttribute("list");
    input.classList.add("hc-autocomplete-input");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    let rows = [], active = -1;
    const control = popup({ trigger: input, panel, kind: "listbox", triggerKeys: false, matchWidth: true,
      onClose: () => { input.removeAttribute("aria-activedescendant"); active = -1; } });
    suggestions.set(input, control);
    // Keep the persistent result announcement outside the listbox's owned
    // options. Recreating a live region on every keystroke is not reliable.
    panel.removeAttribute("role");
    panel.removeAttribute("aria-label");
    const list = document.createElement("div");
    list.id = `${panel.id}-list`;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "Available model routes");
    const status = document.createElement("p");
    status.className = "hc-popup-empty";
    status.setAttribute("role", "status");
    panel.append(list, status);
    input.setAttribute("aria-controls", list.id);

    function render() {
      const query = input.value.trim().toLocaleLowerCase();
      const matches = [...datalist.options].filter(option => !option.disabled &&
        `${option.value} ${option.label}`.toLocaleLowerCase().includes(query));
      list.replaceChildren();
      rows = matches.slice(0, 100).map((option, index) => {
        const row = document.createElement("div");
        row.className = "hc-suggestion";
        row.id = `${panel.id}-option-${index}`;
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", "false");
        const name = document.createElement("span");
        name.textContent = option.value;
        row.append(name);
        if (option.label && option.label !== option.value) {
          const note = document.createElement("small");
          note.textContent = option.label;
          row.append(note);
        }
        row.addEventListener("pointerdown", event => event.preventDefault());
        row.addEventListener("click", () => choose(index));
        list.append(row);
        return { node: row, value: option.value };
      });
      status.textContent = !matches.length
        ? "No available route matches. You can still enter an explicit route; Hutch checks it before saving."
        : matches.length > 100 ? `Showing 100 of ${matches.length} routes. Keep typing to narrow the list.`
        : `${matches.length} available ${matches.length === 1 ? "route" : "routes"}. Use arrow keys to explore, Enter to choose.`;
      active = -1;
      input.removeAttribute("aria-activedescendant");
    }
    function show() {
      if (input.disabled || input.readOnly) return;
      render();
      control.open({ focus: false });
    }
    function choose(index) {
      if (!rows[index]) return;
      input.value = rows[index].value;
      control.close();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      control.close(); // a caller's input listener may have reopened suggestions
    }
    input.addEventListener("click", show);
    input.addEventListener("input", event => { if (!event.isComposing) show(); });
    input.addEventListener("keydown", event => {
      if (event.isComposing) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!control.opened) show();
        if (!rows.length) return;
        active = (active + (event.key === "ArrowDown" ? 1 : active < 0 ? 0 : rows.length - 1) + rows.length) % rows.length;
        rows.forEach((row, index) => row.node.setAttribute("aria-selected", String(index === active)));
        input.setAttribute("aria-activedescendant", rows[active].node.id);
        rows[active].node.scrollIntoView({ block: "nearest" });
      } else if (event.key === "Enter" && control.opened && active >= 0) {
        event.preventDefault(); event.stopPropagation(); choose(active);
      } else if (event.key === "Tab") control.close();
    });
  }

  function enhance(root) {
    const nodes = [...root.querySelectorAll(selector)];
    if (root.matches?.(selector)) nodes.unshift(root);
    for (const details of nodes) {
      if (disclosures.has(details)) continue;
      const trigger = details.querySelector(":scope > summary");
      const panel = details.querySelector(":scope > div");
      if (!trigger || !panel) continue;
      const kind = details.matches(".conversation-actions") ? "dialog" : "menu";
      if (kind === "menu") {
        for (const row of panel.querySelectorAll("button, a[href]")) {
          row.setAttribute("role", "menuitem"); row.tabIndex = -1;
        }
      }
      const control = popup({ trigger, panel, kind,
        side: details.matches(".fleet-card-menu") ? "top" : "bottom",
        onClose: () => { details.open = false; } });
      disclosures.set(details, control);
      details.addEventListener("toggle", () => {
        if (details.open && !control.opened) control.open();
        else if (!details.open) control.close();
      });
      if (kind === "menu") panel.addEventListener("click", event => {
        if (event.target.closest("a[href]")) control.close(false);
      });
    }
    const inputs = [...root.querySelectorAll("input[list]")];
    if (root.matches?.("input[list]")) inputs.unshift(root);
    inputs.forEach(autocomplete);
  }
  const observer = new MutationObserver(records => {
    for (const item of [...live]) if (!item.trigger.isConnected || !item.panel.isConnected) item.destroy();
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) enhance(node);
    }
  });
  enhance(document);
  observer.observe(document.body, { childList: true, subtree: true });
  window.hutchControls = { popup, closeAll: () => { for (const item of [...live]) item.close(); } };
})();
