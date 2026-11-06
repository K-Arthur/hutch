/* Inbound webhooks management surface: sources, one-time secrets, rotation and deliveries.
 *
 * Appends to the Scheduled work (#/schedules) view without editing frozen app.js.
 */
(function () {
  "use strict";

  const state = {
    enhanced: new WeakSet(),
    sources: [],
    bots: [],
    activeModal: null,
    pending: null,
  };

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }

  function callApi(path, options) {
    if (typeof window.api === "function") return window.api(path, options || {});
    const opts = options || {};
    return fetch(`/api${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      method: opts.method || "GET",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(async res => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `${res.status}`);
      }
      return res.json();
    });
  }

  function notify(msg, isError) {
    if (typeof window.toast === "function") window.toast(msg, !!isError);
  }

  function sourceCardHtml(src) {
    const isPaused = !src.enabled;
    const badgeClass = isPaused ? "webhook-badge--paused" : "webhook-badge--active";
    const badgeText = isPaused ? "Paused" : "Active";
    const bot = state.bots.find(b => b.id === src.bot_id);
    const botName = bot?.display_name || bot?.name || src.bot_id;

    return `
      <div class="webhook-source-card" data-source-id="${esc(src.id)}">
        <div class="webhook-source-head">
          <h3>${esc(src.name)}</h3>
          <span class="webhook-badge ${badgeClass}">${badgeText}</span>
        </div>
        <div class="webhook-source-meta">
          <span>Assigned to: <b>${esc(botName)}</b></span>
          <span>Token prefix: <code>${esc(src.token_prefix)}</code></span>
          ${src.prev_token_prefix ? `<span>Retiring prefix: <code>${esc(src.prev_token_prefix)}</code></span>` : ""}
          <span>Limit: ${Number(src.cooldown_seconds)}s cooldown · ${Number(src.max_per_hour)}/hr</span>
        </div>
        <div class="webhook-source-meta">
          <span>Last delivery: ${src.last_delivery_at ? esc(src.last_delivery_at) : "Never"}</span>
          ${src.last_error ? `<span style="color:var(--danger)">Error: ${esc(src.last_error)}</span>` : ""}
        </div>
        <div class="webhook-source-actions">
          <button class="btn btn-sm ${isPaused ? "btn-primary" : "btn-outline"}" data-action="toggle-pause" data-id="${esc(src.id)}" data-paused="${isPaused ? "1" : "0"}">
            ${isPaused ? "Resume" : "Pause"}
          </button>
          <button class="btn btn-sm btn-outline" data-action="rotate-secret" data-id="${esc(src.id)}" data-rev="${src.revision}">
            Rotate secret
          </button>
          <button class="btn btn-sm btn-outline text-error" data-action="delete-source" data-id="${esc(src.id)}">
            Delete
          </button>
        </div>
        <details class="webhook-deliveries-details" data-id="${esc(src.id)}">
          <summary class="hint" style="cursor:pointer;margin-top:var(--s-1)">View recent deliveries</summary>
          <div class="webhook-deliveries-container" style="margin-top:var(--s-2)">
            <p class="hint">Loading deliveries…</p>
          </div>
        </details>
      </div>
    `;
  }

  function showSecretModal(container, rawToken, sourceName) {
    const existing = $(".webhook-secret-callout", container);
    if (existing) existing.remove();

    const callout = document.createElement("div");
    callout.className = "webhook-secret-callout";
    callout.innerHTML = `
      <strong>Save webhook secret for "${esc(sourceName)}"</strong>
      <p class="hint" style="margin:0">This secret is hashed with SHA-256 at rest. It will <b>never</b> be shown again.</p>
      <div style="display:flex;gap:var(--s-2);align-items:center;flex-wrap:wrap">
        <code id="webhook-token-display">${esc(rawToken)}</code>
        <button class="btn btn-sm btn-secondary" id="webhook-copy-token">Copy</button>
        <button class="btn btn-sm btn-ghost" id="webhook-dismiss-token">Dismiss</button>
      </div>
    `;

    const grid = $(".webhook-sources-grid", container);
    if (grid) grid.before(callout);

    $("#webhook-copy-token", callout)?.addEventListener("click", () => {
      navigator.clipboard?.writeText(rawToken).then(() => notify("Token copied to clipboard"));
    });
    $("#webhook-dismiss-token", callout)?.addEventListener("click", () => callout.remove());
  }

  function showCreateModal(container) {
    const existing = $(".webhook-create-dialog", container);
    if (existing) { existing.remove(); return; }

    const botOptions = state.bots.map(b => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("");
    const dialog = document.createElement("div");
    dialog.className = "webhook-create-dialog webhook-source-card";
    dialog.style.marginTop = "var(--s-3)";
    dialog.innerHTML = `
      <h3>Create Inbound Webhook</h3>
      <form id="webhook-create-form" style="display:grid;gap:var(--s-2)">
        <label>Name: <input type="text" class="input input-sm" id="wh-name" required placeholder="e.g. GitHub Production Deploy"></label>
        <label>Target Assistant: <select class="select select-sm" id="wh-bot">${botOptions}</select></label>
        <label>Prompt Template: <textarea class="textarea textarea-sm" id="wh-prompt" placeholder="Webhook payload from {name}:\n\n{payload}"></textarea></label>
        <div style="display:flex;gap:var(--s-3);flex-wrap:wrap">
          <label>Cooldown (sec): <input type="number" class="input input-sm" id="wh-cooldown" value="0" min="0" step="1"></label>
          <label>Max / Hour: <input type="number" class="input input-sm" id="wh-maxhour" value="60" min="0" step="1"></label>
        </div>
        <div style="display:flex;gap:var(--s-2);margin-top:var(--s-2)">
          <button type="submit" class="btn btn-sm btn-primary">Generate Webhook</button>
          <button type="button" class="btn btn-sm btn-ghost" id="wh-cancel">Cancel</button>
        </div>
      </form>
    `;

    const grid = $(".webhook-sources-grid", container);
    if (grid) grid.before(dialog);

    $("#wh-cancel", dialog)?.addEventListener("click", () => dialog.remove());
    $("#webhook-create-form", dialog)?.addEventListener("submit", async e => {
      e.preventDefault();
      const botId = $("#wh-bot", dialog).value;
      const name = $("#wh-name", dialog).value.trim();
      const promptTemplate = $("#wh-prompt", dialog).value;
      const cooldownSeconds = parseFloat($("#wh-cooldown", dialog).value) || 0;
      const maxPerHour = parseInt($("#wh-maxhour", dialog).value, 10) || 60;

      try {
        const res = await callApi("/v1/webhook-sources", {
          method: "POST",
          body: { bot_id: botId, name, prompt_template: promptTemplate, cooldown_seconds: cooldownSeconds, max_per_hour: maxPerHour },
        });
        dialog.remove();
        notify("Webhook source created");
        await reloadSources(container);
        showSecretModal(container, res.token, res.source.name);
      } catch (err) {
        notify(`Failed to create webhook: ${err.message}`, true);
      }
    });
  }

  async function loadDeliveries(container, sourceId, mount) {
    try {
      const items = await callApi(`/v1/webhook-sources/${sourceId}/deliveries?limit=20`);
      if (!items.length) {
        mount.innerHTML = `<p class="hint">No delivery events recorded yet.</p>`;
        return;
      }
      mount.innerHTML = `
        <ul class="webhook-deliveries-list">
          ${items.map(d => {
            const badgeClass = `webhook-badge--${d.status}`;
            return `
              <li class="webhook-delivery-item">
                <div>
                  <span class="webhook-badge ${badgeClass}">${esc(d.status)}</span>
                  <strong>HTTP ${d.status_code}</strong>
                  <span>${esc(d.received_at)}</span>
                  ${d.client_ip ? `<span>(${esc(d.client_ip)})</span>` : ""}
                  ${d.error_message ? `<div style="color:var(--danger)">${esc(d.error_message)}</div>` : ""}
                </div>
                <div>
                  <span>${d.payload_bytes} bytes</span>
                  ${d.idempotency_key ? `<span>Key: <code>${esc(d.idempotency_key)}</code></span>` : ""}
                  ${d.run_id ? `<a href="#/conversation/${esc(d.run_id)}">View run</a>` : ""}
                </div>
              </li>
            `;
          }).join("")}
        </ul>
      `;
    } catch (err) {
      mount.innerHTML = `<p class="hint" style="color:var(--danger)">Failed to load deliveries: ${esc(err.message)}</p>`;
    }
  }

  function bindEvents(section) {
    section.addEventListener("click", async e => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      const sourceId = btn.dataset.id;

      if (action === "toggle-pause") {
        const isPaused = btn.dataset.paused === "1";
        const endpoint = isPaused ? `/v1/webhook-sources/${sourceId}/resume` : `/v1/webhook-sources/${sourceId}/pause`;
        try {
          await callApi(endpoint, { method: "POST" });
          notify(isPaused ? "Webhook resumed" : "Webhook paused");
          await reloadSources(section);
        } catch (err) {
          notify(`Failed to toggle pause: ${err.message}`, true);
        }
      } else if (action === "rotate-secret") {
        const confirmed = confirm("Rotate secret? The existing secret will remain valid for 24 hours to prevent dropped in-flight deliveries.");
        if (!confirmed) return;
        const rev = parseInt(btn.dataset.rev, 10);
        try {
          const res = await callApi(`/v1/webhook-sources/${sourceId}/rotate-secret`, {
            method: "POST",
            body: { overlap_hours: 24, expected_revision: rev },
          });
          notify("Secret rotated");
          await reloadSources(section);
          showSecretModal(section, res.token, res.source.name);
        } catch (err) {
          notify(`Failed to rotate secret: ${err.message}`, true);
        }
      } else if (action === "delete-source") {
        const confirmed = confirm("Delete this webhook source? All delivery history will be permanently deleted.");
        if (!confirmed) return;
        try {
          await callApi(`/v1/webhook-sources/${sourceId}`, { method: "DELETE" });
          notify("Webhook source deleted");
          await reloadSources(section);
        } catch (err) {
          notify(`Failed to delete webhook source: ${err.message}`, true);
        }
      }
    });

    section.addEventListener("toggle", e => {
      const details = e.target.closest(".webhook-deliveries-details");
      if (details && details.open) {
        const sourceId = details.dataset.id;
        const mount = $(".webhook-deliveries-container", details);
        if (mount) void loadDeliveries(section, sourceId, mount);
      }
    }, true);

    $("#webhook-create-btn", section)?.addEventListener("click", () => showCreateModal(section));
  }

  async function reloadSources(section) {
    try {
      const [sources, bots] = await Promise.all([
        callApi("/v1/webhook-sources"),
        callApi("/v1/bots"),
      ]);
      state.sources = sources;
      state.bots = bots;

      const grid = $(".webhook-sources-grid", section);
      if (!grid) return;
      if (!sources.length) {
        grid.innerHTML = `<p class="hint">No webhook sources configured yet. Click "New Webhook Source" above to create one.</p>`;
      } else {
        grid.innerHTML = sources.map(sourceCardHtml).join("");
      }
    } catch (err) {
      const grid = $(".webhook-sources-grid", section);
      if (grid) grid.innerHTML = `<p class="hint" style="color:var(--danger)">Failed to load webhook sources: ${esc(err.message)}</p>`;
    }
  }

  function enhance() {
    if (location.hash !== "#/schedules") return;
    const container = $("#view .schedule-overview");
    if (!container) return;
    if (state.enhanced.has(container)) return;
    state.enhanced.add(container);

    const section = document.createElement("section");
    section.className = "webhook-management-section";
    section.innerHTML = `
      <div class="webhook-management-head">
        <h2>Inbound Webhooks</h2>
        <button class="btn btn-sm btn-primary" id="webhook-create-btn">New Webhook Source</button>
      </div>
      <div class="webhook-warning-banner" role="note">
        Inbound webhooks listen on loopback (127.0.0.1). To receive events from external services, use a secure tunnel (e.g. Cloudflare Tunnel, Tailscale Funnel) or reverse proxy with TLS. Never expose plain HTTP to untrusted networks.
      </div>
      <div class="webhook-sources-grid">
        <p class="hint">Loading webhook sources…</p>
      </div>
    `;

    container.append(section);
    bindEvents(section);
    void reloadSources(section);
  }

  function scheduleSoon() {
    clearTimeout(state.pending);
    state.pending = setTimeout(enhance, 120);
  }

  const view = document.getElementById("view");
  if (view) new MutationObserver(scheduleSoon).observe(view, { childList: true, subtree: true });
  window.addEventListener("hashchange", scheduleSoon);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scheduleSoon);
  else scheduleSoon();
})();
