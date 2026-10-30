/* Hutch form enhancer.
   Progressive enhancement for the form system in hutch-forms.css: it adds the
   required marker, wires aria-describedby to a field's help and error slots,
   keeps aria-invalid in step with both native validation and explicit errors,
   and exposes a small API for callers that render fields at runtime.

   Pages still work without it - every control keeps its native label, its
   required attribute and its server-side validation. This file only makes the
   states visible to assistive tech. No framework, no build step. */
"use strict";

(function () {
  const FORM = "form.hutch-form";
  const CONTROL =
    'input:not([type="hidden"], [type="checkbox"], [type="radio"], [type="range"], [type="color"], [type="file"], [type="button"], [type="submit"], [type="reset"], [type="image"]), select, textarea:not(.hutch-composer__textarea)';
  /* The chat composer and any form that opts out keep their own chrome: they
     are not form fields in the settings sense and have their own system. */
  const EXEMPT = "data-hutch-exempt";
  const PICKER = 'input[type="checkbox"], input[type="radio"]';
  const HELP = ".hutch-help, .hutch-error, .hutch-ok";
  let serial = 0;

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, "\\$&");
  }

  /* The field a control belongs to: its own wrapper first, then the label that
     points at it, then a wrapping label. A bare control inside a form or a
     fieldset has no field of its own - group help is handled separately. */
  function fieldOf(control) {
    if (!control) return null;
    const own = control.closest(".hutch-field, .field");
    if (own) return own;
    if (control.id) {
      const pointing = document.querySelector('label[for="' + cssEscape(control.id) + '"]');
      if (pointing) return pointing;
    }
    const wrapping = control.closest("label");
    if (wrapping) return wrapping;
    const parent = control.parentElement;
    if (parent && !parent.closest(FORM + ", fieldset, .hutch-fieldset")) return parent;
    return null;
  }

  /* Slots a control is described by: its own field's, plus - for a checkbox or
     radio - the direct help of the group it belongs to. */
  function slotsOf(control) {
    const slots = [];
    const field = fieldOf(control);
    if (field) slots.push(...field.querySelectorAll(HELP));
    if (control.matches(PICKER)) {
      const group = control.closest("fieldset, .hutch-fieldset");
      if (group) {
        for (const child of group.children) {
          if (child.matches && child.matches(HELP)) slots.push(child);
        }
      }
    }
    return slots.filter((slot, index, all) => slot !== control && all.indexOf(slot) === index);
  }

  /* The marker is decorative: the control's own required attribute is what
     assistive tech announces, so the glyph is hidden from it. */
  function markRequired(control) {
    if (!control.required) return;
    /* A radio group is marked once on its legend, not once per option. */
    if (control.type === "radio") return;
    const label = control.closest("label") ||
      (control.id && document.querySelector('label[for="' + cssEscape(control.id) + '"]'));
    if (!label || label.querySelector(".hutch-req")) return;
    const marker = document.createElement("span");
    marker.className = "hutch-req";
    marker.setAttribute("aria-hidden", "true");
    marker.textContent = "*";
    label.appendChild(marker);
  }

  function wireDescribedBy(control) {
    const slots = slotsOf(control);
    if (!slots.length) return;
    const ids = [];
    for (const slot of slots) {
      if (!slot.id) slot.id = "hutch-" + ++serial + "-slot";
      ids.push(slot.id);
      if (slot.classList.contains("hutch-error")) slot.setAttribute("aria-live", "polite");
    }
    const existing = (control.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    const merged = existing.filter((id) => ids.indexOf(id) === -1).concat(ids);
    control.setAttribute("aria-describedby", merged.join(" "));
  }

  /* Native validity only counts once the form has been submitted: an untouched
     empty required field is not an error yet. */
  function syncInvalid(control) {
    const field = fieldOf(control);
    const slots = slotsOf(control);
    const error = slots.find((slot) => slot.classList.contains("hutch-error"));
    const form = control.form;
    const validated = Boolean(form && form.dataset.hutchValidated === "1");
    const explicit = control.getAttribute("aria-invalid") === "true";
    const message = Boolean(error && !error.hidden && error.textContent.trim());
    const native = validated && !control.validity.valid;
    const invalid = explicit || message || native;

    if (invalid) control.setAttribute("aria-invalid", "true");
    else control.removeAttribute("aria-invalid");

    if (field) {
      if (invalid) field.setAttribute("data-hutch-state", "invalid");
      else if (field.getAttribute("data-hutch-state") === "invalid") field.removeAttribute("data-hutch-state");
      if (error) error.hidden = !message;
    }
  }

  function initControl(control) {
    if (!control || control.dataset.hutchWired === "1") return;
    control.dataset.hutchWired = "1";
    if (control.tagName === "TEXTAREA") control.classList.add("hutch-textarea");
    else if (control.tagName === "SELECT") control.classList.add("hutch-select");
    else control.classList.add("hutch-input");
    markRequired(control);
    wireDescribedBy(control);
    syncInvalid(control);
    control.addEventListener("invalid", () => syncInvalid(control));
    control.addEventListener("input", () => syncInvalid(control));
    control.addEventListener("change", () => syncInvalid(control));
  }

  function initForm(form) {
    if (!form || !form.matches || !form.matches(FORM)) return;
    if (form.hasAttribute(EXEMPT)) return;
    form.querySelectorAll(CONTROL).forEach(initControl);
    form.querySelectorAll(PICKER).forEach((picker) => {
      if (picker.closest(".hutch-check, .hutch-radio, .hutch-option, .hutch-choice")) return;
      const label = picker.closest("label");
      if (label) label.classList.add(picker.type === "radio" ? "hutch-radio" : "hutch-check");
    });
    /* The first invalid control marks the whole form as validated, so every
       other empty required field shows its state instead of only the one the
       browser happened to report first. */
    if (!form.dataset.hutchSubmitWired) {
      form.dataset.hutchSubmitWired = "1";
      form.addEventListener(
        "invalid",
        (event) => {
          form.dataset.hutchValidated = "1";
          form.querySelectorAll(CONTROL).forEach(syncInvalid);
        },
        true
      );
    }
    form.querySelectorAll(HELP).forEach((slot) => {
      if (!slot.id) slot.id = "hutch-" + ++serial + "-slot";
      watchSlot(slot);
    });
    form.querySelectorAll(CONTROL).forEach(wireDescribedBy);
  }

  /* A field cluster with no form root (modal bodies, panel sections) gets the
     same wiring as a field inside a form: control classes, required marker and
     describedby. Nothing here posts; the caller owns the action. */
  function initField(field) {
    if (!field || !field.matches || !field.matches(".hutch-field")) return;
    field.querySelectorAll(CONTROL).forEach(initControl);
    field.querySelectorAll(HELP).forEach((slot) => {
      if (!slot.id) slot.id = "hutch-" + ++serial + "-slot";
      watchSlot(slot);
    });
    const control = field.querySelector(CONTROL);
    if (control) wireDescribedBy(control);
  }

  function init(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches && root.matches(FORM)) initForm(root);
    else if (root.matches && root.matches(".hutch-field")) initField(root);
    root.querySelectorAll(FORM).forEach(initForm);
    root.querySelectorAll(".hutch-field").forEach(initField);
  }

  /* An error or success slot whose text is written at runtime - by a caller
     that only assigns textContent and never touches hidden - shows and hides
     itself with its own text. Only text is observed, so a caller that hides a
     slot which still carries text keeps that choice. */
  const slotObserver =
    typeof MutationObserver === "function"
      ? new MutationObserver((records) => {
          for (const record of records) {
            const target = record.target;
            const slot = target.nodeType === 3 ? target.parentElement : target;
            if (!slot || !slot.matches || !slot.matches(".hutch-error, .hutch-ok")) continue;
            if (slot.textContent.trim()) slot.hidden = false;
            else slot.hidden = true;
            const field = slot.closest(".hutch-field, .field");
            const control = field && field.querySelector(CONTROL);
            if (control) syncInvalid(control);
          }
        })
      : null;

  function watchSlot(slot) {
    if (!slotObserver || !slot || slot.dataset.hutchSlotWatched === "1") return;
    if (!slot.matches(".hutch-error, .hutch-ok")) return;
    slot.dataset.hutchSlotWatched = "1";
    slotObserver.observe(slot, { childList: true, subtree: true, characterData: true });
  }

  /* Runtime callers (settings panels, modals, phone views) render fields after
     load; setFieldError writes the message into the field's own error slot. */
  function setFieldError(control, message) {
    if (!control) return null;
    const field = fieldOf(control);
    if (!field) return null;
    let error = field.querySelector(".hutch-error");
    if (!error) {
      error = document.createElement("p");
      error.className = "hutch-error";
      field.appendChild(error);
    }
    if (!error.id) error.id = "hutch-" + ++serial + "-slot";
    error.textContent = message || "";
    error.hidden = !message;
    if (message) {
      control.setAttribute("aria-invalid", "true");
      field.setAttribute("data-hutch-state", "invalid");
    } else {
      control.removeAttribute("aria-invalid");
      if (field.getAttribute("data-hutch-state") === "invalid") field.removeAttribute("data-hutch-state");
    }
    wireDescribedBy(control);
    return error;
  }

  function clearFieldError(control) {
    return setFieldError(control, "");
  }

  window.HutchForms = { init, initForm, setFieldError, clearFieldError, fieldOf };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => init(document), { once: true });
  } else {
    init(document);
  }

  /* Fields arrive after first paint: HTMX swaps on the server pages, rendered
     panels in the SPA. Watch additions so every form is wired exactly once. */
  if (typeof MutationObserver === "function" && document.body) {
    const dirty = new Set();
    const dirtyFields = new Set();
    const flush = () => {
      const forms = [...dirty];
      const fields = [...dirtyFields];
      dirty.clear();
      dirtyFields.clear();
      forms.forEach(initForm);
      fields.forEach(initField);
    };
    new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType !== 1) continue;
          const host = node.closest ? node.closest(FORM) : null;
          if (host) dirty.add(host);
          if (node.querySelectorAll) {
            node.querySelectorAll(FORM).forEach((form) => dirty.add(form));
            if (node.matches && node.matches(".hutch-field")) dirtyFields.add(node);
            node.querySelectorAll(".hutch-field").forEach((field) => dirtyFields.add(field));
          } else if (node.matches && node.matches(".hutch-field")) {
            dirtyFields.add(node);
          }
        }
      }
      if (dirty.size) queueMicrotask(flush);
    }).observe(document.body, { childList: true, subtree: true });
  }
  document.addEventListener("htmx:afterSwap", (event) => init(event.target));

  /* A link into a disclosure opens it. The Models page's "Add model" and
     "Hosted prices" actions target a section whose form sits in a closed
     <details>; without this the link lands on a summary that still has to be
     clicked. Native details behaviour is unchanged when JavaScript is off. */
  document.addEventListener("click", (event) => {
    const link = event.target && event.target.closest && event.target.closest('a[href^="#"]');
    if (!link) return;
    const id = link.getAttribute("href").slice(1);
    if (!id) return;
    const target = document.getElementById(id);
    if (!target) return;
    const details = target.tagName === "DETAILS" ? target
      : target.closest("details") || target.querySelector("details");
    if (details) details.open = true;
  });

  /* Opt-in submit state for ordinary form POSTs. A form marked data-busy
     disables its submit button and says what is happening until the browser
     navigates. Native validation has already run; a confirmation handler that
     called preventDefault (hutch.js) leaves the form untouched. */
  document.addEventListener("submit", (event) => {
    if (event.defaultPrevented) return;
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-busy")) return;
    const button = form.querySelector('button[type="submit"], button:not([type])');
    if (!button || button.disabled) return;
    button.disabled = true;
    button.textContent = form.dataset.busy || "Working...";
    form.setAttribute("aria-busy", "true");
  });
})();
