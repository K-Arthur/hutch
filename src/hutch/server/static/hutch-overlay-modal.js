/* ============================================================================
   Hutch overlay primitives - modal builder and server wiring

   Builds the native <dialog> markup that hutch-overlay-dialog.js enhances and
   wires the two server-rendered forms of the primitive:

     [data-hutch-modal-open="dialog-id"]   opens a rendered dialog
     form[data-hutch-confirm-form="id"]    destructive form: without JavaScript
                                           the form still submits; with it the
                                           dialog asks first and re-submits only
                                           on an explicit confirm.

   Public: HutchOverlay.modal(options), HutchOverlay.confirm(options).
   ========================================================================== */
(function () {
  "use strict";

  var Core = window.__HutchOverlayCore;
  var doc = Core.doc;
  var q = Core.q;
  var qa = Core.qa;
  var esc = Core.esc;

  function closeGlyph() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  }

  function populate(dialog, options) {
    dialog.innerHTML =
      '<header class="hutch-modal__header modal-header">' +
        '<h2 class="hutch-modal__title"' + (options.titleId ? ' id="' + esc(options.titleId) + '"' : "") + ">" + esc(options.title || "") + "</h2>" +
        (options.dismissible === false ? "" :
          '<button class="hutch-modal__close"' + (options.closeId ? ' id="' + esc(options.closeId) + '"' : "") +
          ' type="button" aria-label="' + esc(options.closeLabel || "Close dialog") + '">' + closeGlyph() + "</button>") +
      "</header>" +
      (options.description ? '<p class="hutch-modal__description">' + esc(options.description) + "</p>" : "") +
      '<div class="hutch-modal__body modal-body"></div>' +
      '<footer class="hutch-modal__actions modal-footer"></footer>';
    var body = q(".hutch-modal__body", dialog);
    if (options.body instanceof Node) body.appendChild(options.body);
    else body.innerHTML = options.body == null ? "" : String(options.body);
    var actions = q(".hutch-modal__actions", dialog);
    var cancel = null;
    if (options.cancel !== false) {
      cancel = doc.createElement("button");
      cancel.type = "button";
      cancel.className = "btn ghost";
      cancel.id = options.cancelId || "modal-cancel";
      cancel.setAttribute("data-hutch-modal-cancel", "");
      cancel.textContent = typeof options.cancel === "string" ? options.cancel : "Cancel";
      actions.appendChild(cancel);
    }
    var confirm = null;
    if (options.confirm !== false) {
      confirm = doc.createElement("button");
      confirm.type = "button";
      confirm.id = options.confirmId || "modal-confirm";
      confirm.className = "btn " + (options.danger ? "danger" : (options.confirmVariant || "primary"));
      confirm.textContent = options.confirmLabel || "Confirm";
      actions.appendChild(confirm);
    }
    (options.extraActions || []).forEach(function (item) { actions.appendChild(item); });
    Core.overlayRoot().prepend(dialog);
    var api = window.HutchOverlay.enhance(dialog, options);
    if (cancel) cancel.addEventListener("click", function () { api.close("cancel"); });
    var closeNode = q(".hutch-modal__close", dialog);
    if (closeNode) closeNode.addEventListener("click", function () { api.close("cancel"); });
    if (confirm && typeof options.onConfirm === "function") {
      confirm.addEventListener("click", function () {
        var result = options.onConfirm(api);
        if (result && typeof result.then === "function") {
          api.setBusy(true, options.busyLabel ? { label: options.busyLabel } : {});
          api.clearError();
          result.then(function (outcome) {
            if (outcome === false) { api.setBusy(false); return; }
            api.close("confirm");
          }).catch(function (error) {
            api.setBusy(false);
            api.showError((error && error.message) || "The action could not be completed. Try again.");
          });
        } else if (result === false) {
          /* Keep the dialog open; the caller signalled it is not done. */
        } else {
          api.close("confirm");
        }
      });
    }
    api.confirmNode = confirm;
    return api;
  }

  function buildModal(options) {
    options = options || {};
    var id = options.id || Core.nextId("hutch-modal-");
    var dialog = doc.createElement("dialog");
    dialog.id = id;
    dialog.className = "hutch-modal" + (options.className ? " " + options.className : "");
    dialog.setAttribute("data-size", options.size || "md");
    if (options.variant) dialog.setAttribute("data-variant", options.variant);
    if (options.dismissible === false) dialog.setAttribute("data-dismissible", "false");
    if (options.initialFocus) dialog.setAttribute("data-initial-focus", options.initialFocus);
    dialog.setAttribute("data-modal-backdrop", "");
    var enhanceOptions = {
      title: options.title,
      titleId: options.titleId,
      description: options.description,
      size: options.size,
      variant: options.variant,
      dismissible: options.dismissible,
      initialFocus: options.initialFocus,
      returnFocus: options.returnFocus,
      focusFallback: options.focusFallback,
      removeOnClose: options.removeOnClose !== false,
      onClose: options.onClose,
    };
    populate(dialog, Object.assign({}, options, enhanceOptions));
    return dialog.__hutchModal;
  }

  function modal(options) {
    var api = buildModal(options);
    return api.open(options);
  }

  function confirm(options) {
    options = options || {};
    var danger = options.danger === true;
    return new Promise(function (resolve) {
      var settled = false;
      var api = buildModal({
        title: options.title,
        size: "sm",
        id: options.id,
        dismissible: options.dismissible !== undefined ? options.dismissible : !danger,
        initialFocus: options.initialFocus,
        returnFocus: options.returnFocus,
        confirmLabel: options.confirmLabel || (danger ? "Delete" : "Confirm"),
        danger: danger,
        cancel: "Cancel",
        onConfirm: options.onConfirm || function () { return true; },
        onClose: function (reason) {
          if (!settled) {
            settled = true;
            resolve(reason === "confirm");
          }
          if (options.onClose) options.onClose(reason);
        },
      });
      if (options.descriptionHtml) {
        var node = doc.createElement("p");
        node.className = "hutch-modal__description";
        node.innerHTML = options.descriptionHtml;
        var body = q(".hutch-modal__body", api.dialog);
        body.parentNode.insertBefore(node, body);
        node.id = api.dialog.id + "-description";
        api.dialog.setAttribute("aria-describedby", node.id);
      }
      api.open();
    });
  }

  /* -- server-rendered destructive forms ----------------------------------- */

  function wireConfirmForm(form) {
    if (form.dataset.hutchConfirmBound === "1") return;
    var dialog = Core.byId(form.getAttribute("data-hutch-confirm-form"));
    if (!dialog) return;
    form.dataset.hutchConfirmBound = "1";
    var api = window.HutchOverlay.enhance(dialog, {
      dismissible: dialog.getAttribute("data-dismissible") !== "false",
      title: dialog.getAttribute("data-title") || null,
    });
    form.addEventListener("submit", function (event) {
      if (form.dataset.hutchConfirmed === "1") return;
      event.preventDefault();
      api.open({ returnFocus: doc.activeElement });
    });
    qa("[data-hutch-confirm-submit]", dialog).forEach(function (button) {
      button.addEventListener("click", function () {
        form.dataset.hutchConfirmed = "1";
        api.setBusy(true);
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      });
    });
  }

  function enhanceAll(scope) {
    qa("dialog.hutch-modal, dialog[data-hutch-modal]", scope || doc).forEach(function (dialog) {
      var api = window.HutchOverlay.enhance(dialog, {
        dismissible: dialog.getAttribute("data-dismissible") !== "false",
        initialFocus: dialog.getAttribute("data-initial-focus") || null,
        title: dialog.getAttribute("data-title") || null,
      });
      qa("[data-hutch-modal-cancel], .hutch-modal__close", dialog).forEach(function (button) {
        if (button.dataset.hutchModalCloseBound === "1" || button.type === "submit") return;
        button.dataset.hutchModalCloseBound = "1";
        button.addEventListener("click", function () { api.close("cancel"); });
      });
    });
    qa("[data-hutch-modal-open]", scope || doc).forEach(function (trigger) {
      if (trigger.dataset.hutchModalBound === "1") return;
      trigger.dataset.hutchModalBound = "1";
      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        var dialog = Core.byId(trigger.getAttribute("data-hutch-modal-open"));
        if (!dialog) return;
        var api = dialog.__hutchModal || window.HutchOverlay.enhance(dialog, {});
        if (api) api.open({ returnFocus: trigger });
      });
    });
    qa("form[data-hutch-confirm-form]", scope || doc).forEach(wireConfirmForm);
  }

  window.HutchOverlay.modal = modal;
  window.HutchOverlay.confirm = confirm;
  window.HutchOverlay.modalEnhanceAll = enhanceAll;

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { enhanceAll(doc); });
  else enhanceAll(doc);
  if (typeof MutationObserver === "function") {
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) { if (node.nodeType === 1) enhanceAll(node); });
      });
    }).observe(doc.body, { childList: true, subtree: true });
  }
})();
