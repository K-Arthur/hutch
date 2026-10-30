/* Shared popup adapter.

   Data and authority stay with each caller; this module wires the shared
   overlay primitives (window.HutchOverlay) to the product's existing popup
   callers. The controller - placement, collision flip/shift, re-anchoring,
   Escape/outside-click dismissal, focus entry/return and teardown - now lives
   in static/hutch-overlay-popover.js. This file keeps three product-specific
   layers on top:

     1. hutchControls.popup({...}) - the stable API every caller already uses;
     2. disclosure enhancement for the three authored <details> menus;
     3. the datalist -> combobox progressive enhancement.

   Load order: overlay core/dialog/modal/popover before this file. */
(function () {
  "use strict";

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const primitives = () => window.HutchOverlay;

  function popup({ trigger, panel, kind = "dialog", side = "bottom", triggerKeys = true, matchWidth = false, onOpen = null, onClose = null }) {
    if (!trigger || !panel || !primitives()) return null;
    const control = primitives().popover({
      trigger,
      panel,
      kind,
      side,
      menu: kind === "menu",
      triggerKeys,
      matchWidth,
      toggle: false,
      align: "end",
      onOpen,
      onClose,
    });
    if (!control) return null;
    panel.dataset.popupKind = kind;
    return control;
  }

  // One set of document listeners lives in the primitive; nothing here adds
  // duplicate global handlers.

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
    // stays in the owning page/dialog; the primitive decides whether the
    // browser can lift it into the top layer.
    (input.closest("label") || input).after(panel);
    input.removeAttribute("list");
    input.classList.add("hc-autocomplete-input");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    let rows = [], active = -1;
    const control = popup({
      trigger: input, panel, kind: "listbox", triggerKeys: false, matchWidth: true,
      onClose: () => { input.removeAttribute("aria-activedescendant"); active = -1; },
    });
    if (!control) return;
    suggestions.set(input, control);
    // Keep the persistent result announcement outside the listbox's owned
    // options. Recreating a live region on every keystroke is not reliable.
    panel.removeAttribute("role");
    panel.removeAttribute("aria-label");
    const list = document.createElement("div");
    list.id = panel.id + "-list";
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
      if (!control) continue;
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
    for (const item of [...$$(".hc-popup")]) {
      if (item.__hutchPopover && (!item.__hutchPopover.trigger.isConnected || !item.isConnected)) item.__hutchPopover.destroy();
    }
    for (const record of records) for (const node of record.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) enhance(node);
    }
  });
  enhance(document);
  observer.observe(document.body, { childList: true, subtree: true });
  window.hutchControls = {
    popup,
    closeAll: () => primitives() && primitives().closeAll(),
  };
})();
