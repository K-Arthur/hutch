/* Shared popup lifecycle. Data and authority stay with each caller; this module
   owns placement, keyboard movement and dismissal, never application actions.
   Keep panels in their owner's DOM (including native dialogs); top-layer popovers
   avoid clipping without a body portal or a second modal focus trap. */
(function () {
  "use strict";
  const live = new Set();
  let serial = 0;
  const visible = node => node?.isConnected && node.getClientRects().length && !node.closest("[hidden]");
  const focusables = root => [...root.querySelectorAll("button, a[href], input, select, textarea, summary, [tabindex]")]
    .filter(node => visible(node) && !node.disabled && node.getAttribute("aria-disabled") !== "true");

  function popup({ trigger, panel, kind = "dialog", side = "bottom", onClose = null }) {
    if (!trigger || !panel) return null;
    const abort = new AbortController();
    const options = { signal: abort.signal };
    const topLayer = typeof panel.showPopover === "function";
    let opened = false;
    panel.id ||= `hutch-popup-${++serial}`;
    panel.classList.add("hc-popup");
    panel.dataset.popupKind = kind;
    panel.setAttribute("role", kind);
    panel.hidden = true;
    if (topLayer) panel.setAttribute("popover", "manual");
    trigger.setAttribute("aria-haspopup", kind);
    trigger.setAttribute("aria-controls", panel.id);
    trigger.setAttribute("aria-expanded", "false");

    function place() {
      if (!opened) return;
      const viewport = window.visualViewport;
      const x = viewport?.offsetLeft || 0, y = viewport?.offsetTop || 0;
      const width = viewport?.width || innerWidth, height = viewport?.height || innerHeight;
      const gap = 8, inset = 8;
      const anchor = trigger.getBoundingClientRect();
      panel.style.maxWidth = `${Math.max(0, width - inset * 2)}px`;
      panel.style.maxHeight = `${Math.max(0, height - inset * 2)}px`;
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
      opened = true;
      if (trigger.parentElement instanceof HTMLDetailsElement) trigger.parentElement.open = true;
      panel.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      if (topLayer && !panel.matches(":popover-open")) panel.showPopover();
      live.add(api);
      place();
      if (focus) {
        const selected = panel.querySelector('[aria-checked="true"], [aria-selected="true"]');
        (selected || focusables(panel)[0] || panel).focus({ preventScroll: true });
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
      if (next >= 0 && items[next]) {
        event.preventDefault();
        event.stopImmediatePropagation();
        items[next].focus();
      }
    }
    panel.addEventListener("keydown", navigate, options);
    trigger.addEventListener("keydown", event => {
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
  document.addEventListener("keydown", event => {
    const item = [...live].at(-1);
    if (!item) return;
    if (event.key === "Escape") {
      // An inline details section consumes its own first Escape, before its
      // enclosing form popover. Native select pickers retain browser handling.
      const nested = event.target.closest("details[open]");
      if (nested && item.panel.contains(nested)) return;
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
  const selector = ".fleet-card-menu, .assistant-settings-menu, .conversation-actions";
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
