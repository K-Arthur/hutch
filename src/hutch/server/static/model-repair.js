/* Moving an assistant onto a model that works, and offering the best one when it has none.

   An assistant on a route that cannot run (the retired demo route, no route, a malformed one) has no usable default, so
   "for the next message only" means nothing for it. And a model that belongs to another runtime (OpenCode's models, for an
   assistant on Hutch's own runtime) cannot be a one-message override at all. Both need the same honest step: say what is
   about to be saved, show the data-sharing notice when the model is hosted, and save the model (and the runtime it needs)
   only when the person confirms. Nothing here chooses silently; the offer button only opens that confirmation. */
(function () {
  "use strict";

  const FREE = /(^|[-_./])free($|[-_.])/i;
  const label = bot => bot.display_name || bot.name;
  const html = value => (typeof esc === "function" ? esc(value)
    : String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const runtimeOf = value => value || "builtin";

  /* True when choosing this model for this assistant is a repair (save it) and not a one-message override. */
  function needed(bot, model) {
    return !!model && model.state === "ready" && (!!bot.route_problem || runtimeOf(model.runtime) !== runtimeOf(bot.runtime));
  }

  function confirmBody(bot, model) {
    const notice = model.hosted ? window.hutchStarterRoute.noticeHtml({ hosted: true, free: model.free ?? FREE.test(model.spec) }) : "";
    const moves = runtimeOf(model.runtime) !== runtimeOf(bot.runtime);
    return notice + "<p>This saves <b>" + html(model.label) + "</b> as " + html(label(bot)) + "'s model"
      + (moves ? " and moves it to the " + (model.runtime === "opencode" ? "OpenCode" : "built-in") + " runtime" : "")
      + ". Future and scheduled runs use it. Nothing is sent until you ask it to work, and you can change it any time on its AI model tab.</p>";
  }

  /* Ask, then save. Resolves with the saved assistant, or null when the person backs out. */
  function apply(bot, model) {
    return new Promise(resolve => {
      openModal({ title: "Use " + model.label + " for " + label(bot) + "?", bodyHtml: confirmBody(bot, model), confirmText: "Use this model",
        confirmClass: "primary", onCancel: () => resolve(null),
        onConfirm: async () => {
          const body = { model: model.spec };
          if (runtimeOf(model.runtime) !== runtimeOf(bot.runtime)) body.runtime = runtimeOf(model.runtime);
          try {
            const saved = await api("/bots/" + encodeURIComponent(bot.name), { method: "PATCH", body });
            toast(model.label + " is now " + label(bot) + "'s model.");
            if (typeof renderChatStudio === "function") await renderChatStudio(bot.name);
            resolve(saved);
            return true;
          } catch (error) {
            toast("Not saved: " + error.message, true);
            return false;
          }
        } });
    });
  }

  /* Fill the "can't run yet" notice with one button: the best model this machine can start with (same decision as first run). */
  async function offer(slot) {
    const name = slot.dataset.repairBot;
    slot.removeAttribute("data-repair-bot");
    let bot, status = null, routes = [];
    try { bot = await api("/bots/" + encodeURIComponent(name)); } catch { return; }
    if (!bot.route_problem) return;
    try { status = await api("/v1/opencode/status"); } catch { /* OpenCode may not be installed */ }
    try { routes = await api("/v1/model-routes?inference_mode=hybrid&runtime=builtin"); } catch { /* setup stays possible by hand */ }
    const starter = window.hutchStarterRoute.choose(status, routes);
    if (!starter || !slot.isConnected) return;
    const model = { spec: starter.model, label: starter.label, hosted: starter.hosted, free: starter.free, state: "ready",
                    runtime: starter.runtime === "opencode" ? "opencode" : "" };
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn primary small";
    button.textContent = "Use " + starter.label;
    button.addEventListener("click", () => { void apply(bot, model); });
    slot.replaceChildren(button);
  }

  function scan() {
    document.querySelectorAll("[data-repair-bot]").forEach(slot => { void offer(slot); });
  }
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();

  window.hutchModelRepair = { needed, apply };
})();
