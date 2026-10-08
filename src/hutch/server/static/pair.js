"use strict";

(() => {
  const form = document.querySelector("#pair-form");
  const submit = document.querySelector("#pair-submit");
  const error = document.querySelector("#pair-error");
  const success = document.querySelector("#pair-success");
  if (!form || !submit || !error || !success) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const codeField = form.elements.code;
    const labelField = form.elements.label;
    const payload = { code: codeField.value.trim(), label: labelField.value.trim() || "Phone" };
    if (!payload.code) {
      error.textContent = "Enter the one-time code shown on your Hutch host.";
      error.hidden = false;
      codeField.focus();
      return;
    }

    submit.disabled = true;
    submit.textContent = "Pairing…";
    error.hidden = true;
    codeField.value = "";
    try {
      const response = await fetch("/api/v1/pairing/exchange", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || `Pairing failed (${response.status}).`);
      form.hidden = true;
      document.querySelector("#pair-instructions").hidden = true;
      success.hidden = false;
      success.querySelector("a").focus();
    } catch (cause) {
      error.textContent = cause.message || "Pairing failed. Check the code and try again.";
      error.hidden = false;
      codeField.focus();
    } finally {
      submit.disabled = false;
      submit.textContent = "Pair device";
    }
  });
})();
