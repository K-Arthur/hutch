/* ============================================================================
   Hutch overlay primitives - shared core

   Loaded before hutch-overlay-modal.js and hutch-overlay-popover.js. Owns the
   pieces both primitives share: DOM helpers, the scroll lock (with scrollbar
   compensation), motion timing that respects reduced motion, and the open
   popover registry that lets the modal layer dismiss floating panels first.

   The public contract is window.HutchOverlay; the private seam is
   window.__HutchOverlayCore. Nothing here renders UI on its own.
   ========================================================================== */
(function () {
  "use strict";

  var doc = document;
  var serial = 0;
  var popovers = [];
  var root = null;
  var scrollLockCount = 0;
  var originalBodyPadding = "";

  function byId(id) { return id ? doc.getElementById(id) : null; }
  function q(selector, el) { return (el || doc).querySelector(selector); }
  function qa(selector, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(selector)); }
  function visible(node) {
    if (!node || !node.isConnected || node.hidden) return false;
    var rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
  function focusable(scope) {
    return qa('a[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]', scope)
      .filter(function (node) {
        return visible(node) && !node.disabled
          && node.getAttribute("aria-disabled") !== "true"
          && !node.closest("[hidden]");
      });
  }
  function reducedMotion() {
    return (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      || doc.documentElement.classList.contains("reduce-effects");
  }
  function motionMs(el, prop, fallback) {
    if (reducedMotion()) return 1;
    var raw = getComputedStyle(el).getPropertyValue(prop).trim();
    var n = parseFloat(raw);
    if (!isFinite(n)) return fallback;
    return /ms$/.test(raw) ? n : n * 1000;
  }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function labelFromTrigger(trigger) {
    return (trigger && (trigger.getAttribute("aria-label") || trigger.getAttribute("title") || trigger.textContent || "")).trim();
  }
  function overlayRoot() {
    if (!root || !root.isConnected) root = byId("modal-root") || doc.body;
    return root;
  }
  function nextId(prefix) { serial += 1; return prefix + serial; }

  function lockScroll() {
    scrollLockCount += 1;
    if (scrollLockCount > 1) return;
    var scrollbar = window.innerWidth - doc.documentElement.clientWidth;
    if (!window.CSS || !CSS.supports || !CSS.supports("scrollbar-gutter", "stable")) {
      originalBodyPadding = doc.body.style.paddingRight;
      if (scrollbar > 0) doc.body.style.paddingRight = scrollbar + "px";
    }
    doc.documentElement.dataset.hutchScrollLocked = "";
  }
  function unlockScroll() {
    scrollLockCount = Math.max(0, scrollLockCount - 1);
    if (scrollLockCount > 0) return;
    delete doc.documentElement.dataset.hutchScrollLocked;
    if (originalBodyPadding !== "") {
      doc.body.style.paddingRight = originalBodyPadding;
      originalBodyPadding = "";
    }
  }

  function registerPopover(api) { if (popovers.indexOf(api) < 0) popovers.push(api); }
  function unregisterPopover(api) {
    var index = popovers.indexOf(api);
    if (index >= 0) popovers.splice(index, 1);
  }
  function topPopover() { return popovers.length ? popovers[popovers.length - 1] : null; }
  function closeTopmostPopover(restoreFocus) {
    var top = topPopover();
    if (!top) return false;
    top.close(!!restoreFocus);
    return true;
  }
  function closeAllPopovers() {
    popovers.slice().reverse().forEach(function (item) { item.close(false); });
  }

  window.__HutchOverlayCore = {
    doc: doc,
    byId: byId,
    q: q,
    qa: qa,
    visible: visible,
    focusable: focusable,
    reducedMotion: reducedMotion,
    motionMs: motionMs,
    esc: esc,
    labelFromTrigger: labelFromTrigger,
    overlayRoot: overlayRoot,
    nextId: nextId,
    lockScroll: lockScroll,
    unlockScroll: unlockScroll,
    registerPopover: registerPopover,
    unregisterPopover: unregisterPopover,
    topPopover: topPopover,
    closeTopmostPopover: closeTopmostPopover,
    closeAllPopovers: closeAllPopovers,
    supportsPopover: typeof HTMLElement !== "undefined" && typeof HTMLElement.prototype.showPopover === "function",
  };
  window.HutchOverlay = window.HutchOverlay || {};
})();
