/* First run: the setup check and the background-service offer.
   Findings come from GET /api/v1/setup/check (the `hutch doctor` checks, read-only).
   The service state comes from GET /api/v1/runtime. Installing is never automatic: the
   button opens a confirmation, and only its confirm sends the same request the Runtime
   page sends. Relies on app.js globals at call time: api, confirmDialog, toast. */
(() => {
  "use strict";

  const el = (tag, props = {}, ...kids) => {
    const node = Object.assign(document.createElement(tag), props);
    kids.forEach(kid => node.append(kid));
    return node;
  };

  function shell() {
    return `<aside class="first-run-readiness first-run-setup-check" id="first-run-setup-check" aria-labelledby="first-run-setup-title" aria-busy="true">
      <div class="first-run-readiness-head">
        <h2 id="first-run-setup-title" class="first-run-label">Setup check</h2>
        <span class="first-run-readiness-status" id="first-run-setup-status" data-state="checking"><span class="first-run-readiness-dot" aria-hidden="true"></span><span id="first-run-setup-status-text">Checking</span></span>
      </div>
      <div id="first-run-setup-body" role="status" aria-live="polite" aria-atomic="false"><p class="first-run-readiness-copy">Checking this install…</p></div>
    </aside>`;
  }

  function setStatus(state, text) {
    const chip = document.getElementById("first-run-setup-status");
    const label = document.getElementById("first-run-setup-status-text");
    if (chip) chip.dataset.state = state;
    if (label) label.textContent = text;
  }

  function checkSection(result) {
    const attention = (result.checks || []).filter(check => check.status === "warn" || check.status === "fail");
    if (!attention.length) {
      setStatus("ready", "Ready");
      return el("p", { className: "first-run-readiness-copy", textContent: "Nothing needs attention." });
    }
    setStatus("setup", "Needs attention");
    const list = el("ul", { className: "first-run-setup-findings" });
    for (const check of attention) {
      const item = el("li", {}, el("strong", { textContent: `${check.title}: ` }), check.detail || "");
      if (check.fix) item.append(el("span", { className: "hint", textContent: ` Fix: ${check.fix}` }));
      list.append(item);
    }
    return el("div", {}, el("p", { className: "first-run-readiness-copy",
      textContent: `${attention.length} thing${attention.length === 1 ? "" : "s"} ${attention.length === 1 ? "needs" : "need"} attention` }), list);
  }

  async function install(button, refresh) {
    const confirmed = await window.confirmDialog({
      title: "Install the background service?",
      body: "This installs a user service that runs Hutch on 127.0.0.1:8787 and starts it with your login session, so scheduled work keeps running. You can stop or remove it from Runtime.",
      confirmText: "Install",
    });
    if (!confirmed) return;
    button.disabled = true;
    try {
      await api("/v1/runtime/service/install", { method: "POST", body: { confirm: "install", port: 8787 } });
      toast("Background service installed.");
      await refresh();
    } catch (error) {
      toast(`Could not install the background service: ${error.message}`, true);
      button.disabled = false;
    }
  }

  function serviceSection(snapshot, refresh) {
    const service = snapshot?.service;
    if (!service) return null;
    const box = el("div", { className: "first-run-setup-service" }, el("h3", { className: "first-run-label", textContent: "Background service" }));
    if (service.supported === false) {
      box.append(el("p", { className: "first-run-readiness-copy",
        textContent: "The background service is not available on this system. Scheduled work runs while Hutch is open." }));
    } else if (service.installed && service.active) {
      box.append(el("p", { className: "first-run-readiness-copy", textContent: "Background service is running." }));
    } else if (service.installed) {
      box.append(el("p", { className: "first-run-readiness-copy", textContent: "Background service is installed but not running." }),
        el("a", { href: "#/runtime", textContent: "Open Runtime" }));
    } else {
      const button = el("button", { type: "button", className: "btn ghost", textContent: "Install background service" });
      button.addEventListener("click", () => install(button, refresh));
      box.append(
        el("p", { className: "first-run-readiness-copy",
          textContent: "Scheduled work runs only while Hutch is running. A background service keeps it running in your login session on this computer. Nothing is installed until you choose." }),
        button);
    }
    return box;
  }

  async function mount() {
    const body = document.getElementById("first-run-setup-body");
    const panel = document.getElementById("first-run-setup-check");
    if (!body || !panel) return;
    const refresh = async () => {
      panel.setAttribute("aria-busy", "true");
      const [checkResult, runtimeResult] = await Promise.allSettled([api("/v1/setup/check"), api("/v1/runtime")]);
      if (!document.body.contains(panel)) return;
      const nodes = [];
      if (checkResult.status === "fulfilled") {
        nodes.push(checkSection(checkResult.value));
      } else {
        setStatus("error", "Not checked");
        const retry = el("button", { type: "button", className: "btn ghost small", textContent: "Check again" });
        retry.addEventListener("click", () => void refresh());
        nodes.push(el("p", { className: "first-run-readiness-copy", textContent: "Hutch could not run the setup check." }), retry);
      }
      if (runtimeResult.status === "fulfilled") {
        const section = serviceSection(runtimeResult.value, refresh);
        if (section) nodes.push(section);
      }
      body.replaceChildren(...nodes);
      panel.setAttribute("aria-busy", "false");
    };
    await refresh();
  }

  window.hutchSetupCheck = { shell, mount };
})();
