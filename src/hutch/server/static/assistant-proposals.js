/* Assistants the main assistant has suggested, shown where assistants live: the sidebar.

   The main assistant can only suggest (see src/hutch/proposals.py). This lists what is waiting and offers two things: "Set up"
   opens the normal assistant setup with the name and job filled in, and the person reviews and creates it there like any other
   assistant; "Not now" dismisses it. Nothing is created from here, and a suggestion disappears by itself once an assistant with
   that name exists. This is the "ask before creating" step of Grok Bot's and OpenClaw's agent-created agents. */
(function () {
  "use strict";

  const POLL_MS = 20000;
  const text = value => (typeof esc === "function" ? esc(value)
    : String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  let items = [];
  let busy = false;
  let retries = 0;

  function slot() {
    let node = document.getElementById("proposals-slot");
    if (node) return node;
    const list = document.getElementById("roster-list");
    if (!list || !list.parentElement) return null;
    node = document.createElement("section");
    node.id = "proposals-slot";
    node.className = "proposals";
    node.setAttribute("aria-label", "Suggested assistants");
    list.parentElement.insertBefore(node, list);
    return node;
  }

  function render() {
    const node = slot();
    if (!node) return;
    if (!items.length) { node.hidden = true; node.replaceChildren(); return; }
    const main = (typeof botsCache !== "undefined" ? botsCache : []).find(bot => bot.is_workspace_coordinator);
    if (!main && retries < 10) { retries += 1; window.setTimeout(render, 400); }      // the roster may still be loading: say who suggested it once it is
    node.hidden = false;
    node.innerHTML = '<h3 class="proposals-title">Suggested' + (main ? " by " + text(main.display_name || main.name) : "") + "</h3><ul>"
      + items.map(item => '<li class="proposal"><b>' + text(item.name) + '</b><p class="hint">' + text(item.job) + "</p>"
        + (item.why ? '<p class="hint">' + text(item.why) + "</p>" : "")
        + '<div class="proposal-actions"><button type="button" class="btn small primary" data-proposal-open="' + text(item.id) + '">Set up</button>'
        + '<button type="button" class="btn small ghost" data-proposal-dismiss="' + text(item.id) + '">Not now</button></div></li>').join("") + "</ul>";
  }

  async function refresh() {
    if (busy || typeof api !== "function" || document.hidden) return;
    busy = true;
    try { items = (await api("/v1/assistant-proposals")).proposals || []; } catch { /* the sidebar simply shows none */ }
    finally { busy = false; }
    render();
  }

  document.addEventListener("click", async event => {
    const open = event.target.closest("[data-proposal-open]");
    if (open) {
      const item = items.find(entry => entry.id === open.dataset.proposalOpen);
      if (item && typeof promptNewBot === "function") { window.hutchProposalDraft = { name: item.name, job: item.job }; void promptNewBot("", "", null, item.job); }
      return;
    }
    const dismiss = event.target.closest("[data-proposal-dismiss]");
    if (!dismiss) return;
    dismiss.disabled = true;
    try { await api("/v1/assistant-proposals/" + encodeURIComponent(dismiss.dataset.proposalDismiss) + "/dismiss", { method: "POST", body: {} }); }
    catch (error) { if (typeof toast === "function") toast("Could not dismiss that suggestion: " + error.message, true); }
    await refresh();
  });

  window.addEventListener("hashchange", () => { void refresh(); });
  window.addEventListener("focus", () => { void refresh(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) void refresh(); });
  window.setInterval(() => { void refresh(); }, POLL_MS);
  new MutationObserver(() => { if (items.length && !document.getElementById("proposals-slot")) render(); }).observe(document.body, { childList: true, subtree: true });
  window.hutchProposals = { refresh };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { void refresh(); }); else void refresh();
})();
