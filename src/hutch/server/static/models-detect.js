/* Models page: acknowledge a detected-but-unsaved AI service (audit finding S2).
   Reads the same endpoint and uses the same wording as first run
   (readFirstRunReadiness in app.js). The detected route opens Settings with the
   route prefilled: Settings is the one place the new-assistant default is written.
   The check runs only when nothing is saved, because it can start a private
   OpenCode server; it never runs a model or contacts a provider account. */
(() => {
  "use strict";

  const panel = document.getElementById("detected-service");
  const body = document.getElementById("detected-body");
  if (!panel || !body) return;

  const el = (tag, props = {}, ...kids) => {
    const node = Object.assign(document.createElement(tag), props);
    kids.forEach(kid => node.append(kid));
    return node;
  };

  function show(...nodes) {
    body.replaceChildren(...nodes);
    panel.hidden = false;
  }

  // One writer: Settings. This hands the detected route to the Settings page and saves nothing by itself.
  document.addEventListener("click", event => {
    const trigger = event.target.closest("[data-settings-model]");
    if (!trigger) return;
    try { sessionStorage.setItem("hutch:settings-prefill-model", trigger.dataset.settingsModel || ""); } catch { /* private mode */ }
  });

  function useForm(choice) {
    const link = el("a", { className: "btn primary", href: "/#/settings", textContent: `Review ${choice.label} in Settings` });
    link.dataset.settingsModel = choice.model;
    return link;
  }

  function render(status) {
    const choice = window.hutchStarterRoute.choose(status, []);   // the same decision first run makes
    if (!choice) {
      show(el("p", { className: "muted", textContent: "No ready AI service was found. Connect OpenCode or choose another provider." }));
      return;
    }
    const notice = el("div");
    notice.innerHTML = window.hutchStarterRoute.noticeHtml(choice);   // the shared notice: static markup, values escaped there
    show(
      el("p", { textContent: window.hutchStarterRoute.availability(choice) }),   // the same sentence first run shows
      el("p", { className: "hint", textContent: "Review it in Settings, where the new-assistant default is saved. Existing assistants keep their settings, and nothing runs." }),
      notice,
      useForm(choice),
    );
  }

  async function check() {
    show(el("p", { className: "muted", textContent: "Checking for AI services…" }));
    try {
      const response = await fetch("/api/v1/opencode/status", { credentials: "same-origin" });
      if (!response.ok) throw new Error(String(response.status));
      render(await response.json());
    } catch {
      const retry = el("button", { type: "button", className: "btn small ghost", textContent: "Check again" });
      retry.addEventListener("click", check);
      show(el("p", { className: "muted", textContent: "Hutch could not check for AI services." }), retry);
    }
  }

  void check();
})();
