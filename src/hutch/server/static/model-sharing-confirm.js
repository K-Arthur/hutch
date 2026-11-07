/* EC-28: one confirmation for a model route that leaves this machine.
   The server decides whether the route needs one and returns the exact words
   from the Phase 1 locality classifier. This module only shows them, records
   one acknowledgement and then runs the caller's change. A local route runs
   the change immediately. */
(function () {
  "use strict";

  const escHtml = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function requirement(bot, spec) {
    const query = new URLSearchParams({ model: spec });
    return api(`/bots/${encodeURIComponent(bot.name)}/model-sharing?${query.toString()}`);
  }

  async function record(bot, spec, scope) {
    return api(`/bots/${encodeURIComponent(bot.name)}/model-sharing`, {
      method: "POST", body: { model: spec, scope },
    });
  }

  async function confirm({ bot, spec, scope, returnFocus, then }) {
    let info;
    try {
      info = await requirement(bot, spec);
    } catch (err) {
      toast(`Could not check where this model runs: ${err.message}`, true);
      return;
    }
    if (!info?.required || !info.disclosure) { await then(); return; }
    const d = info.disclosure;
    const name = bot.display_name || bot.name;
    openModal({
      title: "Share this assistant's work?",
      bodyHtml: `<p><strong>${escHtml(d.title)}</strong></p>
        <p>${escHtml(d.body)}</p>
        <p class="muted small">Assistant: ${escHtml(name)} &middot; Route: <code>${escHtml(spec)}</code></p>`,
      confirmText: d.locality === "network" ? "Use this network route" : "Send to the hosted service",
      returnFocus,
      onConfirm: async () => {
        try {
          await api(`/bots/${encodeURIComponent(bot.name)}/model-sharing`, {
            method: "POST", body: { model: spec, scope },
          });
          await then();
          return true;
        } catch (err) {
          toast(`Could not record the data-sharing confirmation: ${err.message}`, true);
          return false;
        }
      },
    });
  }

  window.hutchModelSharing = { confirm, requirement, record };
})();
