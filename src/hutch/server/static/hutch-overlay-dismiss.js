/* ============================================================================
   Hutch overlay primitives - document-level dismissal and data triggers

   Loaded after hutch-overlay-popover.js. One set of document listeners owns
   outside pointer/focus dismissal, topmost Escape (after the native select and
   nested-details guards), Tab-closes-menu and re-anchoring on window/container
   scroll, resize and visual-viewport changes. Also wires the server-rendered
   data-hutch-popover-open triggers.
   ========================================================================== */
(function () {
  "use strict";

  var Core = window.__HutchOverlayCore;
  var doc = Core.doc;
  var q = Core.q;
  var qa = Core.qa;

  function closeOutside(target) {
    var registry = Core.qa(".hutch-popover.hc-popup");
    var openPanels = registry.filter(function (panel) { return panel.__hutchPopover && panel.__hutchPopover.opened; });
    openPanels.reverse().forEach(function (panel) {
      var item = panel.__hutchPopover;
      if (item.panel.contains(target) || item.trigger.contains(target)) return;
      item.close(false);
    });
  }

  /* -- document-level dismissal -------------------------------------------- */
  doc.addEventListener("pointerdown", function (event) { closeOutside(event.target); }, true);
  doc.addEventListener("focusin", function (event) { closeOutside(event.target); });
  doc.addEventListener("keydown", function (event) {
    var top = Core.topPopover();
    if (!top || !top.opened) return;
    if (event.key === "Tab" && top.panel.getAttribute("role") === "menu") {
      /* Let the default Tab continue from the trigger, not a hidden row. */
      top.close(true);
      return;
    }
    if (event.key !== "Escape") return;
    if (window.CSS && CSS.supports && CSS.supports("selector(select:open)") && doc.querySelector("select:open")) {
      event.stopImmediatePropagation();
      return;
    }
    var nested = event.target.closest && event.target.closest("details[open]");
    if (nested && top.panel.contains(nested)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      nested.open = false;
      var summary = q(":scope > summary", nested);
      if (summary) summary.focus({ preventScroll: true });
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    top.close(true);
  }, true);
  function reposition() {
    Core.qa(".hutch-popover.hc-popup").forEach(function (panel) {
      if (panel.__hutchPopover && panel.__hutchPopover.opened) panel.__hutchPopover.place();
    });
  }
  window.addEventListener("resize", reposition, { passive: true });
  doc.addEventListener("scroll", function (event) {
    if (event.target && event.target.closest && event.target.closest(".hutch-popover, .hc-popup")) return;
    reposition();
  }, { capture: true, passive: true });
  window.visualViewport && window.visualViewport.addEventListener("resize", reposition, { passive: true });
  window.visualViewport && window.visualViewport.addEventListener("scroll", reposition, { passive: true });

  /* -- data triggers for server-rendered popovers -------------------------- */
  function wireDataTriggers(scope) {
    Core.qa("[data-hutch-popover-open]", scope || doc).forEach(function (trigger) {
      if (trigger.dataset.hutchPopoverBound === "1") return;
      trigger.dataset.hutchPopoverBound = "1";
      var panel = Core.byId(trigger.getAttribute("data-hutch-popover-open"));
      if (!panel) return;
      var menu = panel.getAttribute("role") === "menu";
      if (menu) qa('[role="menuitem"]', panel).forEach(function (row) { row.tabIndex = -1; });
      var control = window.HutchOverlay.popover({
        trigger: trigger,
        panel: panel,
        kind: menu ? "menu" : "dialog",
        menu: menu,
        side: trigger.getAttribute("data-popover-side") || "bottom",
        toggle: true,
        triggerKeys: true,
      });
      trigger.addEventListener("click", function () { trigger.setAttribute("aria-expanded", String(control.opened)); });
    });
  }

  window.HutchOverlay.wireDataTriggers = wireDataTriggers;

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { wireDataTriggers(doc); });
  else wireDataTriggers(doc);
})();
