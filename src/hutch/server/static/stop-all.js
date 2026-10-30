/* Global emergency stop for the SPA header: `POST /api/stop-all`, offered only while
   work is running and always behind a confirmation. Server pages carry the same
   control in templates/base.html (docs/realignment/product-spine.md, item C2).
   Relies on app.js globals at click time: api, confirmDialog, toast. */
(() => {
  "use strict";

  function control() {
    return `<button type="button" class="btn danger small" data-stop-all aria-label="Stop all running work now">Stop all</button>`;
  }

  document.addEventListener("click", async event => {
    const button = event.target.closest?.("[data-stop-all]");
    if (!button) return;
    event.preventDefault();
    const confirmed = await window.confirmDialog({
      title: "Stop all running work?",
      body: "This kills child processes, not just the agent loop. Nothing else is changed.",
      confirmText: "Stop all",
      danger: true,
    });
    if (!confirmed) return;
    button.disabled = true;
    try {
      const result = await api("/stop-all", { method: "POST" });
      const count = Number(result?.stopping) || 0;
      toast(count ? `Stopping ${count} running ${count === 1 ? "job" : "jobs"}.` : "Nothing was running.");
    } catch (error) {
      toast(`Could not stop running work: ${error.message}`, true);
    } finally {
      button.disabled = false;
    }
  });

  window.hutchStopAll = { control };
})();
