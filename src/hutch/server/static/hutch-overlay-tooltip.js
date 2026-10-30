/* ============================================================================
   Hutch overlay primitives - tooltip

   Descriptive, hover/focus-triggered, never interactive. Used directly through
   HutchOverlay.tooltip() and as progressive enhancement for native title
   attributes: the title stays the accessible fallback and is restored when the
   bubble hides, so the platform still works with JavaScript disabled.
   ========================================================================== */
(function () {
  "use strict";

  var Core = window.__HutchOverlayCore;
  var doc = Core.doc;

  function viewport() {
    var vv = window.visualViewport;
    return {
      x: (vv && vv.offsetLeft) || 0,
      y: (vv && vv.offsetTop) || 0,
      width: (vv && vv.width) || window.innerWidth,
      height: (vv && vv.height) || window.innerHeight,
    };
  }

  /* -- tooltip ------------------------------------------------------------- */
  function tooltip(options) {
    options = options || {};
    var target = options.target;
    if (!target) return null;
    if (target.__hutchTooltip) return target.__hutchTooltip;
    var bubble = doc.createElement("div");
    bubble.className = "hutch-tooltip";
    bubble.setAttribute("role", "tooltip");
    bubble.id = Core.nextId("hutch-tooltip-");
    bubble.textContent = typeof options.content === "function" ? options.content() : options.content;
    bubble.hidden = true;
    doc.body.appendChild(bubble);
    var describedBy = target.getAttribute("aria-describedby");
    var api = {
      show: function () {
        bubble.hidden = false;
        bubble.dataset.state = "open";
        var rect = target.getBoundingClientRect();
        var vp = viewport();
        var box = bubble.getBoundingClientRect();
        var left = Math.max(vp.x + 8, Math.min(rect.left + (rect.width - box.width) / 2, vp.x + vp.width - box.width - 8));
        var top = rect.top - box.height - 8;
        if (top < vp.y + 8) top = rect.bottom + 8;
        bubble.style.left = left + "px";
        bubble.style.top = top + "px";
        target.setAttribute("aria-describedby", [describedBy, bubble.id].filter(Boolean).join(" "));
      },
      hide: function () {
        bubble.hidden = true;
        bubble.dataset.state = "";
        if (describedBy) target.setAttribute("aria-describedby", describedBy);
        else target.removeAttribute("aria-describedby");
      },
      destroy: function () {
        api.hide();
        if (bubble.parentNode) bubble.parentNode.removeChild(bubble);
        delete target.__hutchTooltip;
      },
    };
    target.__hutchTooltip = api;
    return api;
  }

  var tooltipTimer = 0;
  var active = null;
  function tooltipTarget(event) {
    var target = event.target.closest && event.target.closest("[title]");
    if (!target || target.getAttribute("data-hutch-tooltip") === "native") return null;
    return target;
  }
  /* A modal makes the page behind it inert, so a tooltip for an element behind it (a pending hover
     timer, or one already showing when the dialog opened) must not appear or linger. It would also
     consume the first Escape, which belongs to the dialog. */
  function blockedByModal(target) {
    var modal = doc.querySelector("dialog[open]");
    return !!modal && !modal.contains(target);
  }
  function showTarget(target) {
    if (active && active.target === target) return;
    if (blockedByModal(target)) return;
    hideTarget();
    var text = target.getAttribute("title");
    if (!text) return;
    target.setAttribute("data-hutch-title", text);
    target.removeAttribute("title");
    active = { target: target, api: tooltip({ target: target, content: text }) };
    active.api.show();
  }
  function hideTarget() {
    clearTimeout(tooltipTimer);
    if (!active) return;
    var target = active.target;
    active.api.hide();
    active.api.destroy();
    if (target.getAttribute("data-hutch-title") != null) {
      target.setAttribute("title", target.getAttribute("data-hutch-title"));
      target.removeAttribute("data-hutch-title");
    }
    active = null;
  }
  doc.addEventListener("pointerover", function (event) {
    if (event.pointerType === "touch") return;
    var target = tooltipTarget(event);
    if (!target) return;
    clearTimeout(tooltipTimer);
    tooltipTimer = window.setTimeout(function () { showTarget(target); }, 420);
  });
  doc.addEventListener("pointerout", function (event) {
    if (!active) return;
    if (event.relatedTarget && active.target.contains(event.relatedTarget)) return;
    hideTarget();
  });
  doc.addEventListener("focusin", function (event) {
    var target = tooltipTarget(event);
    if (target) showTarget(target);
  });
  doc.addEventListener("focusout", function (event) {
    if (active && active.target === event.target) hideTarget();
  });
  doc.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && active) {
      event.preventDefault();
      event.stopImmediatePropagation();
      hideTarget();
    }
  }, true);

  tooltip.hideActive = hideTarget;
  window.HutchOverlay.tooltip = tooltip;
})();
