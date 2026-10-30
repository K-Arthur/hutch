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
  const STEP_HEADING = "[data-focus-heading]";
  const SAVING_TEXT = "Saving...";
  const DRAFT_KEY = "hutch-first-run-request";
  const DRAFT_TARGET = "[data-draft-target]";
  const DRAFT_NOTE = "[data-draft-note]";
  const DRAFT_MAX = 20000;

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

  /* Slice-02 handoff: the empty chat keeps its first request in sessionStorage.
     The textarea is marked data-draft-target only when the server has no saved
     request, so this is a cache read for the empty state only. The normal form
     POST is still the only save; the server never trusts this value. */
  function restoreDraft() {
    const field = document.querySelector(DRAFT_TARGET);
    const note = document.querySelector(DRAFT_NOTE);
    if (!(field instanceof HTMLTextAreaElement) || field.value) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "null");
      const text = saved?.version === 1 && typeof saved.request === "string"
        ? saved.request.slice(0, DRAFT_MAX) : "";
      if (!text.trim()) return;
      field.value = text;
      if (note instanceof HTMLElement) note.hidden = false;
    } catch { /* the tab draft is optional */ }
  }

  /* On a step arrival the page focuses the new step heading so a screen reader
     announces the step change; an error summary always wins over the heading,
     and the request step (no data-focus-heading) keeps its slice-01 behaviour. */
  function focusArrival() {
    const summary = document.querySelector(ERROR_SUMMARY);
    const heading = document.querySelector(STEP_HEADING);
    const target = summary instanceof HTMLElement ? summary
      : heading instanceof HTMLElement ? heading : null;
    if (target) target.focus();
  }

  document.addEventListener("DOMContentLoaded", () => {
    restoreDraft();
    focusArrival();
    announceResume();
  });
})();