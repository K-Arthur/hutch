/* ============================================================================
   Hutch overlay primitives - dialog behaviour

   Attaches the modal contract to a native <dialog>: accessible name and optional
   description, initial focus, exact focus return, dismissible/non-dismissible
   policy, scroll lock, busy/error state and the enter/exit state machine.
   The markup builder in hutch-overlay-modal.js and the server-rendered Jinja
   macro both call HutchOverlay.enhance(dialog, options).
   ========================================================================== */
(function () {
  "use strict";

  var Core = window.__HutchOverlayCore;
  var doc = Core.doc;
  var q = Core.q;
  var qa = Core.qa;

  function describe(dialog, options) {
    var title = options.title || dialog.getAttribute("data-title") || "";
    var heading = q(".hutch-modal__title, [data-hutch-modal-title]", dialog);
    if (!heading && title) {
      heading = doc.createElement("h2");
      heading.className = "hutch-modal__title";
      heading.textContent = title;
      var header = q(".hutch-modal__header", dialog);
      if (header) header.insertBefore(heading, header.firstChild);
      else dialog.insertBefore(heading, dialog.firstChild);
    }
    if (heading) {
      if (!heading.id) heading.id = options.titleId || dialog.id + "-title";
      dialog.setAttribute("aria-labelledby", heading.id);
    }
    var descriptionNode = q(".hutch-modal__description", dialog);
    if (!descriptionNode && options.description) {
      descriptionNode = doc.createElement("p");
      descriptionNode.className = "hutch-modal__description";
      descriptionNode.id = dialog.id + "-description";
      descriptionNode.textContent = options.description;
      var body = q(".hutch-modal__body, .modal-body", dialog);
      if (body && body.parentNode) body.parentNode.insertBefore(descriptionNode, body);
      else dialog.appendChild(descriptionNode);
    }
    if (descriptionNode) {
      if (!descriptionNode.id) descriptionNode.id = dialog.id + "-description";
      dialog.setAttribute("aria-describedby", descriptionNode.id);
    }
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("role", "dialog");
    dialog.dataset.hutchModal = "";
    dialog.classList.add("hutch-modal");
    if (options.size) dialog.setAttribute("data-size", options.size);
    if (options.variant) dialog.setAttribute("data-variant", options.variant);
  }

  function chooseInitialFocus(dialog, options) {
    var dismissible = options.dismissible !== false && dialog.getAttribute("data-dismissible") !== "false";
    var selector = options.initialFocus || dialog.getAttribute("data-initial-focus");
    if (typeof selector === "string" && selector) {
      var explicit = q(selector, dialog);
      if (explicit && Core.visible(explicit) && !explicit.disabled) return explicit;
    }
    var autofocus = q("[data-hutch-autofocus], [autofocus]", dialog);
    if (autofocus && Core.visible(autofocus) && !autofocus.disabled) return autofocus;
    if (!dismissible) {
      /* A destructive or irreversible decision must never receive focus by default. */
      var safe = q("[data-hutch-modal-cancel], .hutch-modal__cancel", dialog);
      if (safe && Core.visible(safe) && !safe.disabled) return safe;
      return dialog;
    }
    var body = q(".hutch-modal__body, .modal-body", dialog);
    /* Form dialogs start at their first field; review dialogs start at their
       first control, then the confirm action, then the dialog itself. */
    var field = body ? Core.focusable(body).filter(function (node) {
      return node.matches("input:not([type=hidden]), select, textarea");
    })[0] : null;
    if (field) return field;
    var control = q("#modal-confirm", dialog) || (body ? Core.focusable(body)[0] : null);
    return control || dialog;
  }

  function enhance(dialog, options) {
    options = options || {};
    if (!dialog) return null;
    if (dialog.__hutchModal) return dialog.__hutchModal;
    if (!dialog.id) dialog.id = Core.nextId("hutch-modal-");
    describe(dialog, options);

    var state = {
      returnFocus: options.returnFocus || doc.activeElement,
      fallbackFocus: options.focusFallback || null,
      dismissible: options.dismissible !== false && dialog.getAttribute("data-dismissible") !== "false",
      closing: false,
      timer: 0,
      instant: options.instant === true,
      focusResolver: options.focusResolver || null,
      finish: options.onClose || null,
    };
    var api = {
      dialog: dialog,
      id: dialog.id,
      get isOpen() { return dialog.open; },
      get dismissible() { return state.dismissible; },
    };

    function restoreFocus() {
      if (typeof state.focusResolver === "function") {
        try { if (state.focusResolver()) return; } catch (error) { /* fall through */ }
      }
      var target = state.returnFocus;
      if (target && target.isConnected && Core.visible(target) && typeof target.focus === "function") {
        target.focus({ preventScroll: true });
        return;
      }
      if (typeof state.fallbackFocus === "function") {
        try { state.fallbackFocus(); } catch (error) { /* a fallback must not block close */ }
        return;
      }
      var fallback = Core.byId("chat-prompt") || Core.byId("nav-toggle") || Core.byId("view");
      if (fallback && Core.visible(fallback)) fallback.focus({ preventScroll: true });
    }

    function finishClose(reason) {
      if (state.closing) return;
      state.closing = true;
      var settle = function () {
        state.closing = false;
        if (dialog.open) dialog.close(reason || "dismiss");
        dialog.dataset.state = "";
        Core.unlockScroll();
        if (options.removeOnClose && dialog.parentNode) dialog.parentNode.removeChild(dialog);
        var callback = state.finish;
        state.finish = null;
        if (callback) callback(reason || "dismiss");
        restoreFocus();
      };
      if (state.instant) { settle(); return; }
      dialog.dataset.state = "closing";
      state.timer = window.setTimeout(settle, Core.motionMs(dialog, "--hutch-motion-overlay-exit-duration", 120));
    }

    api.close = function (reason) {
      if (!dialog.open || state.closing) return;
      finishClose(reason || "dismiss");
    };
    api.setBusy = function (busy, busyOptions) {
      busyOptions = busyOptions || {};
      dialog.dataset.busy = busy ? "true" : "false";
      dialog.setAttribute("aria-busy", busy ? "true" : "false");
      qa(".hutch-modal__actions button, .modal-footer button, .hutch-modal__close", dialog).forEach(function (button) {
        if (busy) {
          if (!button.dataset.hutchWidth && button.getBoundingClientRect().width) {
            button.dataset.hutchWidth = String(Math.round(button.getBoundingClientRect().width));
            button.style.minInlineSize = button.dataset.hutchWidth + "px";
          }
          button.disabled = true;
          button.setAttribute("aria-busy", "true");
        } else {
          button.disabled = false;
          button.removeAttribute("aria-busy");
          if (button.dataset.hutchWidth) {
            button.style.minInlineSize = "";
            delete button.dataset.hutchWidth;
          }
        }
      });
      var confirm = q("#modal-confirm", dialog);
      if (confirm) {
        if (busy && busyOptions.label) {
          if (!confirm.dataset.hutchIdleLabel) confirm.dataset.hutchIdleLabel = confirm.textContent;
          confirm.textContent = busyOptions.label;
        } else if (!busy && confirm.dataset.hutchIdleLabel) {
          confirm.textContent = confirm.dataset.hutchIdleLabel;
          delete confirm.dataset.hutchIdleLabel;
        }
      }
    };
    api.showError = function (message) {
      var node = q(".hutch-modal__error", dialog);
      if (!node) {
        node = doc.createElement("p");
        node.className = "hutch-modal__error";
        node.setAttribute("role", "alert");
        node.setAttribute("aria-live", "assertive");
        var footer = q(".hutch-modal__actions, .modal-footer", dialog);
        if (footer && footer.parentNode) footer.parentNode.insertBefore(node, footer);
        else dialog.appendChild(node);
      }
      node.textContent = message;
      node.hidden = false;
      api.setBusy(false);
    };
    api.clearError = function () {
      var node = q(".hutch-modal__error", dialog);
      if (node) { node.hidden = true; node.textContent = ""; }
    };
    api.destroy = function () {
      if (dialog.open) dialog.close("destroy");
      if (dialog.parentNode) dialog.parentNode.removeChild(dialog);
    };

    function onCancel(event) {
      event.preventDefault();
      if (state.dismissible) api.close("escape");
    }
    function onKeydown(event) {
      if (!dialog.open) return;
      if (event.key === "Escape" && event.target && event.target.matches && event.target.matches("input[type=search]")) {
        /* Chromium clears a search field on Escape and swallows the key, so the native cancel never
           fires. Close explicitly so Escape always dismisses the topmost dialog. */
        event.preventDefault();
        if (state.dismissible) api.close("escape");
        return;
      }
      if (event.key === "Tab") {
        /* Explicit cycle: Chromium parks focus on body after the last control of
           a native dialog, which reads as a trap escape even though the page is
           inert. Keep focus inside the dialog instead. */
        var items = Core.focusable(dialog).filter(function (node) {
          return node.matches("button, a[href], input:not([type=hidden]), select, textarea, summary, [tabindex]");
        });
        if (!items.length) { event.preventDefault(); dialog.focus(); return; }
        var first = items[0];
        var last = items[items.length - 1];
        var inside = dialog.contains(doc.activeElement);
        if (event.shiftKey && (!inside || doc.activeElement === first)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (!inside || doc.activeElement === last)) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (event.key !== "Escape") return;
      /* A native select picker consumes its own Escape first. */
      if (window.CSS && CSS.supports && CSS.supports("selector(select:open)") && dialog.querySelector("select:open")) return;
      var nested = event.target.closest && event.target.closest("details[open]");
      if (nested && dialog.contains(nested)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        nested.open = false;
        var summary = q(":scope > summary", nested);
        if (summary) summary.focus({ preventScroll: true });
        return;
      }
      if (!state.dismissible) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }
    function onBackdrop(event) {
      if (state.dismissible && event.target === dialog) api.close("backdrop");
    }
    function onDialogClose() {
      dialog.removeEventListener("keydown", onKeydown, true);
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("pointerdown", onBackdrop);
      dialog.removeEventListener("close", onDialogClose);
    }

    dialog.addEventListener("keydown", onKeydown, true);
    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("pointerdown", onBackdrop);
    dialog.addEventListener("close", onDialogClose);
    dialog.__hutchModal = api;

    function resolveReturnFocus(candidate) {
      /* An action launched from a popover should return to that popover's
         trigger, not to the row that is about to become hidden. */
      if (candidate && candidate.closest) {
        var panel = candidate.closest(".hc-popup, .hutch-popover");
        if (panel && panel.__hutchPopover && panel.__hutchPopover.trigger) {
          return panel.__hutchPopover.trigger;
        }
      }
      return candidate;
    }

    api.open = function (openOptions) {
      openOptions = openOptions || {};
      if (dialog.open) return api;
      state.returnFocus = resolveReturnFocus(openOptions.returnFocus || options.returnFocus || doc.activeElement);
      Core.closeAllPopovers();
      if (window.HutchOverlay.tooltip && window.HutchOverlay.tooltip.hideActive) window.HutchOverlay.tooltip.hideActive();
      Core.lockScroll();
      if (typeof dialog.showModal === "function") dialog.showModal();
      else {
        dialog.setAttribute("open", "");
        dialog.setAttribute("role", "dialog");
      }
      dialog.dataset.state = "opening";
      void dialog.offsetWidth;
      dialog.dataset.state = "open";
      var target = chooseInitialFocus(dialog, options);
      if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
      return api;
    };
    return api;
  }

  window.HutchOverlay.enhance = enhance;
})();
