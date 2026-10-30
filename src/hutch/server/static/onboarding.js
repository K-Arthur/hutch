/* Onboarding request step (slice 01): progressive enhancement only.
 *
 * The page is a plain HTML form POST, and every action still works with
 * JavaScript disabled. This file adds three small conveniences:
 *   1. on submit, set aria-busy and unhide the polite "Saving..." line, then
 *      disable the submit buttons once the browser has begun the submission,
 *      so a double click cannot post twice;
 *   2. on pageshow (including a bfcache restore) undo that transient state so
 *      the Back button returns a usable page;
 *   3. on load, move focus to the server-rendered error summary when the
 *      response came back invalid (it carries tabindex="-1").
 *
 * A submit button must not be disabled synchronously inside the submit event:
 * disabling the submitter before the form submission is processed cancels the
 * POST in Chromium. The disable therefore runs on the next task, unless
 * another listener already prevented the submission (the browser-lane capture).
 *
 * Loaded with defer from templates/onboarding.html. No inline handlers, no
 * eval, no network access; strict-CSP compatible.
 */
"use strict";

(function () {
  const FORM = "[data-onboarding-form]";
  const SUBMIT = "[data-submit]";
  const SAVING = "[data-saving-status]";
  const ERROR_SUMMARY = "[data-error-summary]";
  const SAVING_TEXT = "Saving...";

  function markBusy(form) {
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll(SAVING).forEach((status) => {
      status.textContent = SAVING_TEXT;
      status.hidden = false;
    });
  }

  function disableSubmits(form) {
    form.querySelectorAll(SUBMIT).forEach((button) => { button.disabled = true; });
  }

  /* A live region that is already populated in the initial HTML is not
     announced reliably. Unhide it empty, then fill it once after load so the
     resumed step is announced exactly once; no-JS users read the noscript copy. */
  function announceResume() {
    document.querySelectorAll("[data-resume-message]").forEach((status) => {
      const text = status.getAttribute("data-resume-text");
      if (!text) return;
      status.textContent = "";
      status.hidden = false;
      window.setTimeout(() => { status.textContent = text; }, 60);
    });
  }

  function clearBusy(form) {
    form.removeAttribute("aria-busy");
    form.querySelectorAll(SUBMIT).forEach((button) => { button.disabled = false; });
    form.querySelectorAll(SAVING).forEach((status) => { status.hidden = true; });
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches(FORM)) return;
    markBusy(form);
    if (event.defaultPrevented) {
      disableSubmits(form);
      return;
    }
    window.setTimeout(() => disableSubmits(form), 0);
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll(FORM).forEach(clearBusy);
  });

  document.addEventListener("DOMContentLoaded", () => {
    const summary = document.querySelector(ERROR_SUMMARY);
    if (summary instanceof HTMLElement) summary.focus();
    announceResume();
  });
})();