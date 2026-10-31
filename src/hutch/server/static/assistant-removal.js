/* Removing assistants: one list, one confirmation, and nothing erased without a preview and a typed phrase.

   Removal used to be a separate page per assistant (preview, then type the address, then confirm) and was reachable only
   from deep in an assistant's settings, so a workspace full of leftovers (the assistants and demo runs an earlier version
   seeded) could not realistically be cleaned. Here: pick assistants from a list (leftovers pre-selected), see exactly what
   would be erased for each, type one phrase, done. Underneath it is still the governed whole-assistant deletion: each
   assistant gets a preview and a confirm that carries the preview's one-time token, so the same evidence is kept. Folders
   you chose outside Hutch are never touched. Reachable from an assistant's menu in the sidebar, the can't-run notice,
   Review install and Settings. */
(function () {
  "use strict";

  // What the retired demo left: its runtime's routes, and the assistants an earlier version seeded or its design fixtures made.
  const SEEDS = new Set(["repo-sweeper", "research-briefing", "tidy-downloads", "design-system-review"]);
  const isRetiredRoute = model => /^(mock\/|demo$)/i.test(String(model || "").trim());       // mirrors hutch.demo_leftovers
  const isLeftover = bot => isRetiredRoute(bot.model) || SEEDS.has(bot.name);
  const text = value => (typeof esc === "function" ? esc(value)
    : String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const note = (message, error = false) => { if (typeof toast === "function") toast(message, error); };
  const phraseFor = count => "remove " + count + " assistant" + (count === 1 ? "" : "s");
  const labelOf = bot => bot.display_name || bot.name;

  function button(state) {
    const count = ((state && state.issues) || []).filter(issue => issue.kind === "assistant" && isRetiredRoute(issue.model)).length;
    return '<button type="button" class="btn danger small" data-remove-assistants>'
      + (count ? "Remove the " + count + " retired demo assistant" + (count === 1 ? "" : "s") + "…" : "Remove assistants…") + "</button>";
  }

  function chooseBody(bots, preselected) {
    return "<p>Choose the assistants to remove. Next you will see exactly what is erased for each one, and nothing is removed until you type a confirmation.</p>"
      + '<ul class="removal-list">' + bots.map(bot => '<li><label class="hutch-check"><input type="checkbox" name="remove" value="' + text(bot.name) + '"'
        + (preselected.has(bot.name) ? " checked" : "") + "><span><b>" + text(labelOf(bot)) + "</b> "
        + (bot.is_workspace_coordinator ? '<span class="tag">main assistant</span> ' : "")
        + (isLeftover(bot) ? '<span class="tag warn">earlier demo</span> ' : "")
        + '<span class="tag">' + text(bot.model || "no route") + "</span></span></label></li>").join("") + "</ul>";
  }

  function counted(counts) {
    const parts = Object.entries(counts || {}).filter(([key, value]) => value && !["bot", "total"].includes(key))
      .map(([key, value]) => value + " " + key.replace(/_/g, " "));
    return parts.length ? parts.join(", ") : "nothing else is stored for it";
  }

  function confirmBody(previews) {
    return "<p><b>This permanently erases</b> each assistant below and its conversations, runs, memory, schedules and managed files. It cannot be undone.</p>"
      + '<ul class="installation-issues">' + previews.map(preview => "<li><p><b>" + text(preview.display) + "</b> "
        + '<span class="tag">' + text(preview.bot_name) + "</span></p><p>Erases: " + text(counted(preview.counts)) + ".</p>"
        + ((preview.remaining || []).length ? '<p class="hint">Kept: ' + text(preview.remaining.join("; ")) + "</p>" : "") + "</li>").join("") + "</ul>"
      + '<div class="hutch-field"><label class="hutch-label" for="removal-phrase">Type <code>' + text(phraseFor(previews.length))
      + '</code> to confirm</label><input class="hutch-input" id="removal-phrase" autocomplete="off" autocapitalize="none" spellcheck="false"></div>';
  }

  async function finish(previews) {
    const failed = [];
    for (const preview of previews) {
      try {
        await api("/v1/bots/" + encodeURIComponent(preview.bot_name) + "/deletion-requests/" + encodeURIComponent(preview.request_id) + "/confirm",
          { method: "POST", headers: { "Idempotency-Key": (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + preview.request_id },
            body: { token: preview.token, confirmation: preview.bot_name } });
      } catch (error) { failed.push(preview.display + ": " + error.message); }
    }
    const done = previews.length - failed.length;
    note(failed.length ? "Removed " + done + "; could not remove " + failed.join("; ") : "Removed " + done + " assistant" + (done === 1 ? "" : "s") + ".", failed.length > 0);
    if (typeof renderChatStudio === "function") { history.replaceState(null, "", "#/chat"); await renderChatStudio(); }
    if (window.hutchInstallation && window.hutchInstallation.refresh) await window.hutchInstallation.refresh();
  }

  async function confirmStep(names, bots) {
    const previews = [];
    for (const name of names) {
      try {
        const preview = await api("/v1/bots/" + encodeURIComponent(name) + "/deletion-requests", { method: "POST", body: {} });
        previews.push({ ...preview, display: labelOf(bots.find(bot => bot.name === name) || { name }) });
      } catch (error) { note("Could not preview removing " + name + ": " + error.message, true); return; }
    }
    openModal({ title: "Remove " + previews.length + " assistant" + (previews.length === 1 ? "" : "s") + "?", bodyHtml: confirmBody(previews), wide: true,
      confirmText: "Remove permanently", confirmClass: "danger",
      onConfirm: async () => {
        const typed = (document.getElementById("removal-phrase")?.value || "").trim().toLowerCase();
        if (typed !== phraseFor(previews.length)) { note("Type the phrase exactly to confirm.", true); document.getElementById("removal-phrase")?.focus(); return false; }
        await finish(previews);
        return true;
      } });
  }

  /* Open the list. `names` pre-selects those assistants; with none given the earlier-demo leftovers are pre-selected. */
  async function open({ names = [] } = {}) {
    if (typeof api !== "function" || typeof openModal !== "function") return;
    let bots;
    try { bots = await api("/bots"); } catch (error) { note("Could not read your assistants: " + error.message, true); return; }
    if (!bots.length) { note("There are no assistants to remove."); return; }
    const preselected = new Set(names.length ? names : bots.filter(isLeftover).map(bot => bot.name));
    openModal({ title: "Remove assistants", bodyHtml: chooseBody(bots, preselected), wide: true, confirmText: "Continue", confirmClass: "primary",
      onConfirm: () => {
        const chosen = [...document.querySelectorAll('.removal-list input[name="remove"]:checked')].map(input => input.value);
        if (!chosen.length) { note("Choose at least one assistant.", true); return false; }
        window.setTimeout(() => { void confirmStep(chosen, bots); }, 0);       // let this dialog finish closing before the next opens
        return true;
      } });
  }

  document.addEventListener("click", event => {
    const trigger = event.target.closest("[data-remove-assistants]");
    if (!trigger) return;
    event.preventDefault();
    void open({ names: trigger.dataset.removeName ? [trigger.dataset.removeName] : [] });
  });

  window.hutchRemoval = { open, button, isLeftover };
})();
