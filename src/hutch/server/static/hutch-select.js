/* Hutch select component wrapper.
   No framework, no build step. Two jobs:

   1. Apply the .hutch-select class to every native select, including ones the
      SPA, HTMX swaps and dialogs inject after load, so a select can never miss
      the component skin. Templates already carry the class in static markup,
      so server pages stay correct with JavaScript disabled and this file is
      an accelerator, not a dependency. Opt a single control out with
      data-hutch-select="off".

   2. Keyboard affordances the native control does not give on every platform:
      Alt+ArrowDown, Alt+ArrowUp and F4 open the picker via showPicker() where
      the engine supports it. Arrow keys, type-ahead, Enter and Escape stay the
      native control's own behaviour - Escape closes the open picker, and
      controls.js already stops outer layers from stealing that key - so this
      wrapper never reimplements them. */
"use strict";

(function () {
  const COMPONENT = "hutch-select";
  const keyed = new WeakSet();

  function enhance(select) {
    if (!(select instanceof HTMLSelectElement)) return;
    if (select.dataset.hutchSelect === "off") return;
    select.classList.add(COMPONENT);
    if (keyed.has(select)) return;
    keyed.add(select);
    select.addEventListener("keydown", (event) => {
      const opens =
        event.key === "F4" ||
        (event.altKey && (event.key === "ArrowDown" || event.key === "ArrowUp"));
      if (!opens || select.disabled || typeof select.showPicker !== "function") return;
      event.preventDefault();
      try {
        select.showPicker();
      } catch {
        /* Not user-activated or not allowed: let the engine's own key handling stand. */
      }
    });
  }

  function sweep(root) {
    if (root instanceof HTMLSelectElement) enhance(root);
    if (root.querySelectorAll) root.querySelectorAll("select").forEach(enhance);
  }

  sweep(document);

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) sweep(node);
      }
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
