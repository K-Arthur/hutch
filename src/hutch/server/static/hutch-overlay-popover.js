/* ============================================================================
   Hutch overlay primitives - popover, dropdown menu and tooltip

   Anchored, non-blocking panels. The controller owns placement (flip + shift,
   re-anchored on scroll/resize/visual viewport), outside-click and Escape
   dismissal for the topmost panel only, focus return, menu arrow/Home/End/
   typeahead navigation and enter/exit motion.

   Rendering strategy (browser support stated in hutch-overlays.css):
   - native popover top layer when available: the panel stays in its owner DOM
     (approved dropdown direction), escapes overflow clipping and stacks above
     inert content;
   - no Popover API: the panel is portalled to document.body so clipping cannot
     hide it. A panel opened inside an open native modal is never portalled,
     because the modal would make the portalled node inert.

   Callers that need markup-only panels use templates/macros/popover.html and
   the data-hutch-popover-open attribute handled below.
   ========================================================================== */
(function () {
  "use strict";

  var Core = window.__HutchOverlayCore;
  var doc = Core.doc;
  var q = Core.q;
  var qa = Core.qa;
  var supportsPopover = Core.supportsPopover;

  function viewport() {
    var vv = window.visualViewport;
    return {
      x: (vv && vv.offsetLeft) || 0,
      y: (vv && vv.offsetTop) || 0,
      width: (vv && vv.width) || window.innerWidth,
      height: (vv && vv.height) || window.innerHeight,
    };
  }

  function portal(node) {
    var marker = doc.createComment("hutch-popover-origin");
    node.parentNode.insertBefore(marker, node);
    doc.body.appendChild(node);
    node.dataset.portalled = "true";
    return function () {
      if (marker.parentNode) marker.parentNode.replaceChild(node, marker);
      delete node.dataset.portalled;
    };
  }

  function popover(options) {
    options = options || {};
    var trigger = options.trigger;
    var panel = options.panel;
    if (!trigger || !panel) return null;
    if (panel.__hutchPopover) return panel.__hutchPopover;
    var kind = options.kind || panel.getAttribute("role") || "dialog";
    var menu = options.menu === true || kind === "menu";
    var side = options.side || "bottom";
    var matchWidth = !!options.matchWidth;
    var opened = false;
    var typed = "";
    var typedAt = 0;
    var abort = new AbortController();
    var placeFrame = 0;
    var originRestore = null;
    var resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(function () {
      if (!placeFrame) placeFrame = requestAnimationFrame(function () { placeFrame = 0; place(); });
    }) : null;

    panel.id = panel.id || Core.nextId("hutch-popover-");
    panel.classList.add("hutch-popover", "hc-popup");
    panel.dataset.category = menu ? "dropdown" : (kind === "dialog" ? "dialog" : "popover");
    panel.dataset.popupKind = kind;
    panel.setAttribute("role", kind);
    if (menu) panel.dataset.menu = "true";
    panel.hidden = true;
    if (supportsPopover) panel.setAttribute("popover", "manual");
    else if (!panel.closest("dialog[open]")) originRestore = portal(panel);
    trigger.setAttribute("aria-haspopup", kind === "dialog" ? "dialog" : kind);
    trigger.setAttribute("aria-controls", panel.id);
    trigger.setAttribute("aria-expanded", "false");
    if (!panel.getAttribute("aria-label") && !panel.getAttribute("aria-labelledby")) {
      panel.setAttribute("aria-label", options.label || Core.labelFromTrigger(trigger) || "Options");
    }
    if (kind === "dialog" && !q(".hc-popup-header", panel)) {
      var header = doc.createElement("div");
      header.className = "hc-popup-header";
      var title = doc.createElement("span");
      title.textContent = panel.getAttribute("aria-label") || "Options";
      var dismiss = doc.createElement("button");
      dismiss.type = "button";
      dismiss.className = "hc-popup-close";
      dismiss.textContent = "Done";
      dismiss.setAttribute("aria-label", "Done, close " + title.textContent.toLowerCase());
      dismiss.addEventListener("click", function () { close(true); }, { signal: abort.signal });
      header.append(title, dismiss);
      panel.prepend(header);
    }
    if (menu) {
      qa('[role="menuitem"], [role^="menuitem"]', panel).forEach(function (row) { row.tabIndex = -1; });
    }

    function menuItems() {
      return qa('[role="menuitem"], [role^="menuitem"], [role="option"]', panel).filter(function (node) {
        return Core.visible(node) && !node.disabled && node.getAttribute("aria-disabled") !== "true";
      });
    }

    function place() {
      if (!opened) return;
      var vp = viewport();
      var gap = 8;
      var inset = 8;
      var anchor = trigger.getBoundingClientRect();
      panel.dataset.popupLayout = "anchored";
      panel.style.maxInlineSize = Math.max(0, vp.width - inset * 2) + "px";
      panel.style.maxBlockSize = Math.max(0, vp.height - inset * 2) + "px";
      if (matchWidth) panel.style.inlineSize = Math.max(0, Math.min(anchor.width, vp.width - inset * 2)) + "px";
      else panel.style.inlineSize = "";
      var natural = panel.getBoundingClientRect();
      var below = vp.y + vp.height - anchor.bottom - gap - inset;
      var above = anchor.top - vp.y - gap - inset;
      var right = vp.x + vp.width - anchor.right - gap - inset;
      var leftSpace = anchor.left - vp.x - gap - inset;
      var placement = side;
      if (placement === "bottom" && natural.height > below && above > below) placement = "top";
      else if (placement === "top" && natural.height > above && below > above) placement = "bottom";
      else if (placement === "right" && natural.width > right && leftSpace > right) placement = "left";
      else if (placement === "left" && natural.width > leftSpace && right > leftSpace) placement = "right";
      var sheet = kind === "dialog" && vp.width <= 560 && (natural.height > Math.max(above, below) || vp.height < 480);
      if (sheet) {
        panel.dataset.popupLayout = "sheet";
        panel.style.maxBlockSize = Math.max(96, vp.height - inset * 2) + "px";
        var sheetBox = panel.getBoundingClientRect();
        panel.style.left = (vp.x + inset) + "px";
        panel.style.top = (vp.y + vp.height - sheetBox.height - inset) + "px";
        panel.dataset.placement = "bottom";
        panel.style.setProperty("--hutch-popover-origin", "center bottom");
        return;
      }
      var room = placement === "top" ? above : placement === "bottom" ? below : placement === "left" ? leftSpace : right;
      if (placement === "top" || placement === "bottom") {
        panel.style.maxBlockSize = Math.max(96, Math.min(vp.height - inset * 2, room)) + "px";
      }
      var box = panel.getBoundingClientRect();
      var leftPos;
      if (placement === "right") leftPos = anchor.right + gap;
      else if (placement === "left") leftPos = anchor.left - gap - box.width;
      else if (options.align === "start") leftPos = anchor.left;
      else leftPos = anchor.right - box.width;
      leftPos = Math.max(vp.x + inset, Math.min(leftPos, vp.x + vp.width - box.width - inset));
      var topPos;
      if (placement === "top") topPos = anchor.top - gap - box.height;
      else if (placement === "bottom") topPos = anchor.bottom + gap;
      else topPos = anchor.top + (anchor.height - box.height) / 2;
      topPos = Math.max(vp.y + inset, Math.min(topPos, vp.y + vp.height - box.height - inset));
      panel.style.left = leftPos + "px";
      panel.style.top = topPos + "px";
      panel.dataset.placement = placement;
      panel.style.setProperty("--hutch-popover-origin",
        placement === "top" ? "center bottom" : placement === "bottom" ? "center top" : placement === "left" ? "right center" : "left center");
    }

    function close(restoreFocus) {
      if (!opened) return;
      opened = false;
      Core.unregisterPopover(api);
      resumeEvents();
      resizeObserver && resizeObserver.unobserve(panel);
      trigger.setAttribute("aria-expanded", "false");
      var rect = panel.getBoundingClientRect();
      /* The hidden contract is synchronous (escape closes now, not after the
         animation); the exit motion plays on an inert snapshot so it never
         delays or blocks the revealed surface. */
      if (supportsPopover && panel.matches(":popover-open")) {
        try { panel.hidePopover(); } catch (error) { /* already hidden */ }
      }
      panel.hidden = true;
      panel.dataset.state = "";
      exitShell(rect);
      if (restoreFocus && Core.visible(trigger)) trigger.focus({ preventScroll: true });
      if (options.onClose) options.onClose();
    }

    function exitShell(rect) {
      if (Core.reducedMotion() || !rect || !rect.width) return;
      var computed = getComputedStyle(panel);
      var shell = panel.cloneNode(true);
      shell.removeAttribute("id");
      shell.removeAttribute("popover");
      shell.removeAttribute("hidden");
      shell.removeAttribute("class");
      shell.setAttribute("aria-hidden", "true");
      shell.inert = true;
      shell.querySelectorAll("[id]").forEach(function (node) { node.removeAttribute("id"); });
      shell.querySelectorAll("[role], [aria-label], [aria-labelledby]").forEach(function (node) {
        node.removeAttribute("role");
        node.removeAttribute("aria-label");
        node.removeAttribute("aria-labelledby");
        node.removeAttribute("tabindex");
      });
      shell.style.cssText = "position:fixed;left:" + rect.left + "px;top:" + rect.top
        + "px;inline-size:" + rect.width + "px;max-block-size:" + rect.height
        + "px;margin:0;padding:" + computed.padding + ";overflow:hidden;pointer-events:none;"
        + "background:" + computed.backgroundColor + ";border:1px solid " + computed.borderTopColor
        + ";border-radius:" + computed.borderTopLeftRadius + ";box-shadow:" + computed.boxShadow
        + ";color:" + computed.color + ";font:" + computed.font + ";";
      document.body.append(shell);
      var duration = Core.motionMs(panel, "--hutch-motion-overlay-exit-duration", 120);
      var remove = function () { if (shell.parentNode) shell.parentNode.removeChild(shell); };
      if (typeof shell.animate === "function") {
        var animation = shell.animate(
          [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-3px) scale(0.99)" }],
          { duration: duration, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", fill: "forwards" }
        );
        if (animation && animation.finished) animation.finished.then(remove, remove);
      }
      window.setTimeout(remove, duration + 80);
    }

    function open(openOptions) {
      openOptions = openOptions || {};
      if (opened) return api;
      arrayFrom(Core.qa(".hutch-popover, .hc-popup")).forEach(function (other) {
        if (other !== panel && !other.contains(trigger) && other.__hutchPopover && other.__hutchPopover.opened) other.__hutchPopover.close(false);
      });
      if (options.onOpen) options.onOpen();
      opened = true;
      Core.registerPopover(api);
      /* A disclosure trigger opens its <details> ancestor first; the panel is
         only visible inside an open details element. */
      if (trigger.parentElement instanceof HTMLDetailsElement) trigger.parentElement.open = true;
      trigger.setAttribute("aria-expanded", "true");
      panel.hidden = false;
      if (supportsPopover && !panel.matches(":popover-open")) {
        try { panel.showPopover(); } catch (error) { /* UA refused: stay in flow */ }
      }
      panel.dataset.state = "opening";
      void panel.offsetWidth;
      panel.dataset.state = "open";
      resizeObserver && resizeObserver.observe(panel);
      place();
      if (openOptions.focus !== false) {
        var items = menu ? menuItems() : Core.focusable(panel).filter(function (node) { return !node.closest(".hc-popup-header"); });
        var selected = items.filter(function (node) {
          return node.matches('[aria-checked="true"], [aria-selected="true"]');
        })[0];
        (selected || items[0] || panel).focus({ preventScroll: true });
      }
      return api;
    }

    function navigate(event) {
      if (!menu) return;
      if (event.target.closest && event.target.closest("input, select, textarea")) return;
      var items = menuItems();
      if (!items.length) return;
      var index = items.indexOf(doc.activeElement);
      var next = -1;
      if (event.key === "ArrowDown") next = (index + 1) % items.length;
      else if (event.key === "ArrowUp") next = (index + items.length - 1) % items.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = items.length - 1;
      else if (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.altKey && !event.metaKey) {
        var now = performance.now();
        typed = now - typedAt > 700 ? event.key : typed + event.key;
        typedAt = now;
        var query = typed.toLocaleLowerCase();
        var ordered = items.slice(index + 1).concat(items.slice(0, index + 1));
        var match = ordered.filter(function (node) {
          return node.textContent.trim().toLocaleLowerCase().indexOf(query) === 0;
        })[0];
        if (match) next = items.indexOf(match);
      }
      if (next >= 0 && items[next]) {
        event.preventDefault();
        event.stopImmediatePropagation();
        items[next].focus();
      }
    }

    function onTriggerKey(event) {
      if (options.triggerKeys === false) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      event.preventDefault();
      open();
      if (event.key === "ArrowUp" && menu) {
        var items = menuItems();
        if (items.length) items[items.length - 1].focus();
      }
    }
    function onTriggerClick() {
      if (options.toggle !== true) return;
      if (opened) close(true); else open();
    }
    function resumeEvents() {
      panel.removeEventListener("keydown", navigate);
      trigger.removeEventListener("keydown", onTriggerKey);
      trigger.removeEventListener("click", onTriggerClick);
    }

    panel.addEventListener("keydown", navigate, { signal: abort.signal });
    trigger.addEventListener("keydown", onTriggerKey, { signal: abort.signal });
    trigger.addEventListener("click", onTriggerClick, { signal: abort.signal });

    var api = {
      panel: panel,
      trigger: trigger,
      open: open,
      close: close,
      place: place,
      get opened() { return opened; },
      destroy: function () {
        close(false);
        abort.abort();
        resumeEvents();
        panel.removeAttribute("popover");
        panel.classList.remove("hutch-popover", "hc-popup");
        if (originRestore) originRestore();
        delete panel.__hutchPopover;
      },
    };
    panel.__hutchPopover = api;
    return api;
  }

  function arrayFrom(list) { return Array.prototype.slice.call(list); }

  window.HutchOverlay.popover = popover;
  window.HutchOverlay.closeTopmost = Core.closeTopmostPopover;
  window.HutchOverlay.closeAll = Core.closeAllPopovers;
  window.HutchOverlay.lockScroll = Core.lockScroll;
  window.HutchOverlay.unlockScroll = Core.unlockScroll;

})();
