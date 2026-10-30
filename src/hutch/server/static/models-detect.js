/* Models page: acknowledge a detected-but-unsaved AI service (audit finding S2).
   Reads the same endpoint and uses the same wording as first run
   (readFirstRunReadiness in app.js). "Use" posts to the existing validated
   /models/set-default, which saves the route as the default for new assistants.
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

  function useForm(model) {
    const form = el("form", { method: "post", action: "/models/set-default", className: "card-actions" });
    for (const [name, value] of [["csrf", panel.dataset.csrf || ""], ["model", model.spec]]) {
      form.append(el("input", { type: "hidden", name, value }));
    }
    form.append(el("button", { type: "submit", className: "btn primary", textContent: `Use ${model.name || model.model_id || model.spec}` }));
    return form;
  }

  function render(status) {
    const models = Array.isArray(status?.models) ? status.models.filter(m => typeof m?.spec === "string" && m.spec) : [];
    if (!status?.ready || !models.length) {
      show(el("p", { className: "muted", textContent: "No ready AI service was found. Connect OpenCode or choose another provider." }));
      return;
    }
    const count = models.length;
    show(
      el("p", { textContent: `OpenCode is ready with ${count} model option${count === 1 ? "" : "s"}. ${status.authenticated
        ? "A provider account is connected."
        : "Its available models can be used without a separate account."}` }),
      el("p", { className: "hint", textContent: "Using it saves this route as the default for new assistants. Existing assistants keep their settings, and nothing runs." }),
      useForm(models[0]),
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
