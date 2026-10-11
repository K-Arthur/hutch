/* Agent Skills surface for the workspace SPA.
 *
 * Three mount points, matching the three places a person meets skills:
 *   renderSkillsPage()            the #/skills library: install, review, inspect, update, remove
 *   mountBotPanel(container, bot) the Bot editor's assignment + readiness panel
 *   mountComposer(slot, bot)      the chat composer's one-run activation picker
 *
 * Everything here is presentation and explicit owner actions. Trust, installation and activation
 * are decided by the server; this file never decides what may run. It follows the same
 * conventions as model-switcher.js: vanilla ES, no build step, app.js globals at call time.
 */
(function () {
  "use strict";

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const q = (sel, el = document) => el.querySelector(sel);
  const qa = (sel, el = document) => [...el.querySelectorAll(sel)];

  const STATUS = {
    enabled: { label: "Enabled", tone: "ok", glyph: "check" },
    disabled: { label: "Disabled", tone: "muted", glyph: "minus" },
    review_required: { label: "Needs review", tone: "warn", glyph: "eye" },
    update_pending: { label: "Update ready", tone: "info", glyph: "up" },
    modified: { label: "Changed on disk", tone: "danger", glyph: "alert" },
    missing: { label: "Missing", tone: "danger", glyph: "alert" },
  };

  const GLYPHS = {
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    minus: '<path d="M6 12h12"/>',
    eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.5"/>',
    up: '<path d="M12 19V5m-6 6 6-6 6 6"/>',
    alert: '<path d="M12 4 3 19h18z"/><path d="M12 10v4m0 3h.01"/>',
    skill: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
  };
  const glyph = (name, size = 16) =>
    `<svg class="skill-ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GLYPHS[name] || ""}</svg>`;

  const statusChip = status => {
    const info = STATUS[status] || { label: status, tone: "muted", glyph: "minus" };
    return `<span class="skill-status tone-${info.tone}">${glyph(info.glyph, 13)}<span>${esc(info.label)}</span></span>`;
  };

  const toneFor = status => ({ ok: "ok", warning: "warn", missing: "danger", unsupported: "muted" }[status] || "muted");

  async function callApi(path, opts = {}) {
    // app.js defines api() as a top-level function in a classic script; reuse it when present.
    if (typeof api === "function") return api(path, opts);
    const res = await fetch(`/api${path}`, {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
  }
  const notify = (message, isError = false) => {
    if (typeof toast === "function") return toast(message, isError);
    if (isError) console.error(message); else console.info(message);
  };

  function withBusy(button, work) {
    if (!button) return work();
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    return work().finally(() => {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    });
  }

  // ------------------------------------------------------------------ library

  let skillsRenderGeneration = 0;

  async function renderSkillsPage() {
    const generation = ++skillsRenderGeneration;
    const container = q("#view");
    container.innerHTML = `<div class="page-scroll"><div class="container">
      <div class="page-title-row"><h1 class="page-title">Skills</h1>
        <button class="btn ghost small" id="skills-refresh" type="button">Refresh</button></div>
      <p class="page-subtitle">Reusable instruction packages (SKILL.md). Installing copies a package here;
        nothing is disclosed to a model until you review it and trust it, and assigning it to an assistant is a separate step.</p>
      <div id="skills-error" class="panel skill-error" role="alert" hidden></div>
      <section class="panel" aria-labelledby="skills-import-title">
        <div class="panel-title" id="skills-import-title">Add a skill</div>
        <div class="skill-import-grid">
          <form id="skills-import-path" class="skill-import-form">
            <label class="field">From a local folder
              <input type="text" name="path" placeholder="~/my-skills/meeting-notes" autocomplete="off" spellcheck="false">
            </label>
            <button class="btn small" type="submit">Install from folder</button>
          </form>
          <div class="skill-import-bundled">
            <p class="hint">Or install one of Hutch's reviewed samples:</p>
            <div class="btn-row" id="skills-bundled"></div>
          </div>
        </div>
        <p class="hint">Import reads a folder on this machine only; Hutch never fetches skills from the network.
          Installation is inert until you review the files and trust the exact content hash.</p>
      </section>
      <div id="skills-body"><div class="empty-state"><div class="spinner" role="status" aria-label="Loading"></div><p>Loading skills…</p></div></div>
    </div></div>`;

    q("#skills-refresh").addEventListener("click", () => void refresh());
    q("#skills-import-path").addEventListener("submit", async event => {
      event.preventDefault();
      const input = q('input[name="path"]', event.target);
      const path = input.value.trim();
      if (!path) { notify("Enter a folder path to import.", true); return; }
      await withBusy(q("button", event.target), async () => {
        try {
          const detail = await callApi("/v1/skills/install", { method: "POST", body: { source: "path", path } });
          notify(`Installed ${detail.name}. Review it, then trust it to enable it.`);
          await refresh();
          await openInspector(detail.name);
        } catch (error) { notify(`Not installed: ${error.message}`, true); }
      });
    });

    async function refresh() {
      const body = q("#skills-body");
      if (!body || generation !== skillsRenderGeneration) return;   // the user left this route
      body.innerHTML = `<div class="empty-state"><div class="spinner" role="status" aria-label="Loading"></div><p>Loading skills…</p></div>`;
      const errorSlot = q("#skills-error");
      if (errorSlot) errorSlot.hidden = true;
      let report;
      try {
        report = await callApi("/v1/skills");
      } catch (error) {
        if (!body.isConnected || generation !== skillsRenderGeneration) return;
        if (errorSlot) {
          errorSlot.hidden = false;
          errorSlot.textContent = `Skills could not be loaded: ${error.message}`;
        }
        body.innerHTML = `<div class="empty-state"><p>Nothing can be installed or changed until the skills state is readable.</p></div>`;
        return;
      }
      if (!body.isConnected || generation !== skillsRenderGeneration) return;
      paint(report);
    }

    function paint(report) {
      const body = q("#skills-body");
      const bundledSlot = q("#skills-bundled");
      if (!body || !bundledSlot || !body.isConnected || generation !== skillsRenderGeneration) return;
      const bundled = report.available.filter(item => item.source.scope === "builtin" && !item.installed);
      bundledSlot.innerHTML = bundled.length
        ? bundled.map(item => `<button class="btn ghost small" type="button" data-install-builtin="${esc(item.name)}"
            title="${esc(item.description)}">${glyph("plus", 13)} ${esc(item.name)}</button>`).join("")
        : `<span class="hint">All bundled samples are installed.</span>`;

      const installed = report.skills;
      const candidates = report.available.filter(item => !item.installed);
      const sections = [];
      sections.push(`<section aria-labelledby="skills-installed-title">
        <h2 class="skill-section-title" id="skills-installed-title">Installed (${installed.length})</h2>
        ${installed.length ? `<div class="skill-grid">${installed.map(card).join("")}</div>`
          : `<div class="empty-state skill-empty"><p>No skills installed yet.</p>
             <p class="hint">Install a bundled sample above, or import a folder that contains SKILL.md.</p></div>`}
      </section>`);
      if (candidates.length) {
        sections.push(`<section aria-labelledby="skills-available-title">
          <h2 class="skill-section-title" id="skills-available-title">Available to install (${candidates.length})</h2>
          <div class="skill-list">${candidates.map(candidateRow).join("")}</div>
        </section>`);
      }
      if (report.collisions.length) {
        sections.push(`<section aria-labelledby="skills-shadowed-title">
          <h2 class="skill-section-title" id="skills-shadowed-title">Shadowed duplicates</h2>
          <div class="panel skill-diagnostics"><p class="hint">Project skills override user skills, which override bundled
            samples. Shadowed copies are shown here instead of being silently dropped.</p>
            ${report.collisions.map(c => `<div class="skill-diagnostic">${esc(c.name)}: using ${esc(c.winner)},
              shadowed ${esc(c.shadowed.join(", "))}</div>`).join("")}</div>
        </section>`);
      }
      if (report.scan_diagnostics.length) {
        sections.push(`<details class="skill-scan"><summary>Discovery notes (${report.scan_diagnostics.length})</summary>
          <div class="panel skill-diagnostics">${report.scan_diagnostics.slice(0, 50).map(d =>
            `<div class="skill-diagnostic tone-${d.level === "error" ? "danger" : d.level === "warning" ? "warn" : "muted"}">${esc(d.message)}</div>`).join("")}
          </div></details>`);
      }
      body.innerHTML = sections.join("");
      wire(body);
    }

    function card(item) {
      const bound = item.status === "enabled" ? "" : "";
      const actions = [];
      if (item.status === "review_required") actions.push(`<button class="btn primary small" type="button" data-action="trust">Review &amp; trust</button>`);
      if (item.status === "enabled") actions.push(`<button class="btn ghost small" type="button" data-action="disable">Disable</button>`);
      if (item.status === "disabled") actions.push(`<button class="btn ghost small" type="button" data-action="enable">Enable</button>`);
      if (item.status === "update_pending") {
        actions.push(`<button class="btn primary small" type="button" data-action="update/apply">Apply update</button>`);
        actions.push(`<button class="btn ghost small" type="button" data-action="update/discard">Discard update</button>`);
      } else if (item.source && (item.source.kind === "path" || item.source.kind === "builtin")) {
        actions.push(`<button class="btn ghost small" type="button" data-action="update">Check for update</button>`);
      }
      if (item.versions && item.versions.length) actions.push(`<button class="btn ghost small" type="button" data-action="rollback">Roll back</button>`);
      if (item.status === "modified") actions.push(`<button class="btn ghost small" type="button" data-action="recheck">Recheck</button>`);
      actions.push(`<button class="btn ghost small" type="button" data-action="inspect">Inspect</button>`);
      return `<article class="panel skill-card" data-skill="${esc(item.name)}">
        <div class="skill-card-head">
          <div><div class="skill-name">${esc(item.name)}</div>
            <div class="skill-desc">${esc(item.description || "No description")}</div></div>
          ${statusChip(item.status)}
        </div>
        <div class="skill-meta">
          ${item.version ? `<span>v${esc(item.version)}</span>` : ""}
          ${item.license ? `<span>${esc(item.license)}</span>` : ""}
          <span title="${esc(item.hash)}">${esc((item.hash || "").slice(0, 12))}</span>
          <span>${esc(item.source.kind)}${item.source.scope && item.source.scope !== "imported" ? `:${esc(item.source.scope)}` : ""}</span>
          ${item.requires_tools.length ? `<span>needs ${esc(item.requires_tools.join(", "))}</span>` : ""}
        </div>
        ${item.staged_update ? `<p class="hint">A staged update (${esc(item.staged_update.hash.slice(0, 12))}) is waiting:
          apply it after reviewing, or discard it. The reviewed version stays active until then.</p>` : ""}
        ${item.status === "modified" ? `<p class="hint tone-danger">The files changed after review. It is withheld from runs;
          inspect the new content and trust it again if the change is yours.</p>` : ""}
        <div class="btn-row skill-actions">${actions.join("")}</div>
      </article>`;
    }

    function candidateRow(item) {
      if (!item.valid) {
        const reason = (item.diagnostics.find(d => d.level === "error") || {}).message || "invalid package";
        return `<div class="panel skill-candidate invalid">
          <div><b>${esc(item.name)}</b> <span class="skill-status tone-danger">${glyph("alert", 13)}<span>Invalid</span></span>
            <div class="hint">${esc(reason)} — ${esc(item.source.path)}</div></div></div>`;
      }
      return `<div class="panel skill-candidate">
        <div class="skill-candidate-copy"><b>${esc(item.name)}</b>
          <span class="skill-status tone-muted">${esc(item.source.scope)}</span>
          <div class="hint">${esc(item.description || "")}</div>
          ${item.shadowed_by ? `<div class="hint">A copy from ${esc(item.shadowed_by)} was shadowed.</div>` : ""}
        </div>
        <button class="btn small" type="button" data-install-builtin="${esc(item.name)}"
          data-source-kind="${esc(item.source.kind)}" data-source-path="${esc(item.source.path)}">Install</button>
      </div>`;
    }

    function wire(body) {
      qa("[data-install-builtin]", body).forEach(button => button.addEventListener("click", () =>
        withBusy(button, async () => {
          try {
            const kind = button.dataset.sourceKind || "builtin";
            const detail = kind === "builtin"
              ? await callApi("/v1/skills/install", { method: "POST", body: { source: "builtin", name: button.dataset.installBuiltin } })
              : await callApi("/v1/skills/install", { method: "POST", body: { source: "path", path: button.dataset.sourcePath } });
            notify(`Installed ${detail.name}. Review it, then trust it to enable it.`);
            await refresh();
            await openInspector(detail.name);
          } catch (error) { notify(`Not installed: ${error.message}`, true); }
        })));
      qa(".skill-card", body).forEach(cardEl => {
        const name = cardEl.dataset.skill;
        qa("[data-action]", cardEl).forEach(button => button.addEventListener("click", () => {
          const action = button.dataset.action;
          if (action === "inspect") { void openInspector(name); return; }
          if (action === "trust") { void openInspector(name, { trust: true }); return; }
          void withBusy(button, async () => {
            try {
              const detail = await callApi(`/v1/skills/${encodeURIComponent(name)}/${action}`, { method: "POST" });
              const messages = {
                disable: `Disabled ${name}. New runs will not load it.`,
                enable: `Enabled ${name}.`,
                "update/apply": `Update applied to ${name}.`,
                "update/discard": `Staged update discarded; the reviewed version stays active.`,
                rollback: `Rolled ${name} back to the previous version.`,
                recheck: detail.status === "review_required" || detail.status === "modified"
                  ? `${name} still needs review after recheck.` : `${name} rechecked.`,
              };
              if (action === "update") {
                notify(`Update staged for ${name}. Review the new content, then apply or discard it.`);
                await openInspector(name);
              } else {
                notify(messages[action] || `${name} updated.`);
              }
              await refresh();
            } catch (error) { notify(`Not changed: ${error.message}`, true); }
          });
        }));
      });
    }

    async function openInspector(name, options = {}) {
      let detail;
      try {
        detail = await callApi(`/v1/skills/${encodeURIComponent(name)}`);
      } catch (error) { notify(`Could not open ${name}: ${error.message}`, true); return; }
      const diagnostics = detail.diagnostics.length
        ? detail.diagnostics.map(d => `<div class="skill-diagnostic tone-${d.level === "error" ? "danger" : d.level === "warning" ? "warn" : "muted"}">${esc(d.level)}: ${esc(d.message)}</div>`).join("")
        : `<div class="hint">No validation findings.</div>`;
      const resources = detail.resources.length
        ? detail.resources.map(r => `<div class="skill-resource">${esc(r.path)} <span class="hint">${r.size} bytes</span></div>`).join("")
        : `<div class="hint">No supporting files.</div>`;
      const bound = detail.bound_bots.length
        ? detail.bound_bots.map(b => `<span class="skill-status tone-muted">${esc(b.display_name || b.name)}</span>`).join(" ")
        : `<span class="hint">Not assigned to any assistant.</span>`;
      const staged = detail.staged_update
        ? `<p class="hint tone-info">Staged update ${esc(detail.staged_update.hash.slice(0, 12))} from ${esc(detail.staged_update.staged_at)}.
             The reviewed version stays active until you apply this from the card.</p>
           ${detail.staged_body ? `<details class="skill-instructions" open><summary>Staged update instructions (what applying would activate)</summary>
             <pre tabindex="0" aria-label="Staged skill instructions">${esc(detail.staged_body)}</pre></details>` : ""}` : "";
      const html = `
        <div class="skill-inspector">
          <div class="skill-inspector-head">${statusChip(detail.status)}
            <span class="skill-meta"><span title="${esc(detail.hash)}">hash ${esc((detail.hash || "").slice(0, 12))}</span>
            <span>source ${esc(detail.source.kind)}: ${esc(detail.source.detail || "")}</span></span></div>
          <p>${esc(detail.description || "")}</p>
          ${staged}
          <dl class="skill-facts">
            <dt>Installed</dt><dd>${esc(detail.installed_at)}</dd>
            <dt>Last reviewed</dt><dd>${esc(detail.reviewed_at || "never")}</dd>
            <dt>License</dt><dd>${esc(detail.license || "(none stated)")}</dd>
            <dt>Compatibility</dt><dd>${esc(detail.compatibility || "(none stated)")}</dd>
            <dt>Needs tools</dt><dd>${detail.requires_tools.length ? esc(detail.requires_tools.join(", ")) : "(none)"}</dd>
            <dt>Allowed-tools note</dt><dd>${detail.allowed_tools ? `${esc(detail.allowed_tools)} <span class="hint">(informational only — Hutch never grants authority from skill metadata)</span>` : "(none)"}</dd>
            <dt>Assigned to</dt><dd>${bound}</dd>
          </dl>
          <p class="hint">Skill instructions and metadata never grant tools, accounts or approval bypasses;
            every action still follows this assistant's own settings and approvals.</p>
          <details class="skill-instructions" open><summary>Instructions the model would receive</summary>
            <pre tabindex="0" aria-label="Skill instructions">${esc(detail.body || "")}</pre></details>
          <details><summary>Supporting files (${detail.resources.length})</summary>${resources}</details>
          <details><summary>Validation findings (${detail.diagnostics.length})</summary>${diagnostics}</details>
        </div>`;
      if (typeof openModal === "function") {
        if (options.trust) {
          openModal({
            title: `Review and trust ${name}`, wide: true, tall: true, bodyHtml: html,
            confirmText: "Trust & enable", confirmClass: "primary",
            onConfirm: async () => {
              try {
                await callApi(`/v1/skills/${encodeURIComponent(name)}/trust`, { method: "POST" });
                notify(`Trusted ${name}. It can now be assigned to assistants.`);
                await refresh();
                return true;
              } catch (error) { notify(`Not trusted: ${error.message}`, true); return false; }
            },
          });
        } else {
          openModal({ title: `Skill: ${name}`, wide: true, tall: true, showCancel: false, confirmText: "Done",
                      confirmClass: "ghost", bodyHtml: html });
        }
      } else {
        notify(`${name}: ${detail.description}`);
      }
    }

    await refresh();
  }

  // ------------------------------------------------------------- bot panel

  async function mountBotPanel(container, bot) {
    if (!container) return;
    container.innerHTML = `<section class="panel" aria-labelledby="bot-skills-title">
      <div class="panel-title settings-panel-title" id="bot-skills-title">${glyph("skill", 16)} Skills</div>
      <div class="bot-skills-body"><div class="empty-state"><div class="spinner" role="status" aria-label="Loading"></div></div></div>
    </section>`;
    const body = q(".bot-skills-body", container);

    async function load() {
      let report, readiness;
      try {
        [report, readiness] = await Promise.all([
          callApi("/v1/skills"),
          callApi(`/v1/bots/${encodeURIComponent(bot.name)}/readiness`),
        ]);
      } catch (error) {
        if (container.isConnected) body.innerHTML = `<p class="hint">Skills could not be loaded: ${esc(error.message)}</p>`;
        return;
      }
      if (!container.isConnected) return;   // the user navigated away while this loaded
      const assigned = new Set(bot.skills || []);
      const installed = report.skills;
      const options = installed.length ? installed.map(item => {
        const checked = assigned.has(item.name);
        const selectable = item.status === "enabled" || checked;
        const reason = !selectable ? (item.status === "review_required" ? "review it on the Skills page first"
          : item.status === "modified" ? "changed on disk; review it again"
          : item.status === "disabled" ? "disabled" : item.status.replace(/_/g, " ")) : "";
        return `<label class="tool-option skill-option ${selectable ? "" : "is-blocked"}">
          <input type="checkbox" name="skills" value="${esc(item.name)}" ${checked ? "checked" : ""} ${selectable ? "" : "disabled"}>
          <span class="tool-option-copy"><b>${esc(item.name)}</b>
            <small>${esc(item.description || "")}${reason ? ` — ${esc(reason)}` : ""}</small></span>
          ${statusChip(item.status)}
        </label>`;
      }).join("") : `<div class="empty-state"><p>No skills are installed yet.</p>
        <p class="hint">Install and review one from the <a href="#/skills">Skills page</a>.</p></div>`;
      const skillArea = readiness.areas.find(area => area.id === "skills");
      body.innerHTML = `
        <p class="hint">Skills are reviewed instruction packages this assistant may load. They never grant tools or
          permissions; each action still follows this assistant's approval settings. A skill also needs the tools or
          connected account it declares.</p>
        <form id="bot-skills-form">
          <div class="tool-options" role="group" aria-label="Assigned skills">${options}</div>
          <div class="btn-row"><button class="btn primary small" type="submit" ${installed.length ? "" : "disabled"}>Save skills</button></div>
        </form>
        <div class="readiness" aria-label="Readiness">
          <div class="readiness-head">${readiness.ready
            ? `<span class="skill-status tone-ok">${glyph("check", 13)}<span>Ready to run</span></span>`
            : `<span class="skill-status tone-danger">${glyph("alert", 13)}<span>Blocked: ${esc(readiness.blocked_areas.join(", "))}</span></span>`}</div>
          <div class="readiness-areas">${readiness.areas.map(area => `
            <details class="readiness-area tone-${toneFor(area.status)}" ${area.status !== "ok" ? "open" : ""}>
              <summary>${esc(area.label)}: <span class="tone-text">${esc(area.status)}</span></summary>
              ${area.note ? `<p class="hint">${esc(area.note)}</p>` : ""}
              ${area.items.map(item => `<div class="readiness-item">${esc(item.name)}: ${esc(item.detail || item.status)}</div>`).join("")}
            </details>`).join("")}</div>
        </div>`;
      q("#bot-skills-form", container).addEventListener("submit", async event => {
        event.preventDefault();
        const button = q("button[type=submit]", event.target);
        const skills = qa('input[name="skills"]:checked', event.target).map(input => input.value);
        await withBusy(button, async () => {
          try {
            await callApi(`/bots/${encodeURIComponent(bot.name)}`, { method: "PATCH", body: { skills } });
            bot.skills = skills;
            notify(skills.length ? `Saved ${skills.length} skill assignment(s).` : "Skill assignments cleared.");
            await load();
          } catch (error) { notify(`Not saved: ${error.message}`, true); }
        });
      });
      if (skillArea && !readiness.ready) {
        // keep the skills area visible without expanding the panel's other areas twice
      }
    }
    await load();
  }

  // ---------------------------------------------------------------- composer

  function mountComposer(slot, bot) {
    if (!slot) return null;
    let usable = [];
    let selected = new Set();
    let open = false;

    slot.innerHTML = `<div class="skill-picker" hidden>
      <button type="button" class="composer-util skill-picker-btn" aria-haspopup="menu" aria-expanded="false">
        ${glyph("skill", 14)}<span class="skill-picker-label">Skills</span>
      </button>
      <div class="skill-picker-menu" role="menu" aria-label="Activate a skill for this message" hidden></div>
    </div>`;
    const wrap = q(".skill-picker", slot);
    const button = q(".skill-picker-btn", slot);
    const menu = q(".skill-picker-menu", slot);
    const label = q(".skill-picker-label", slot);

    function paint() {
      if (!usable.length) { wrap.hidden = true; return; }
      wrap.hidden = false;
      label.textContent = selected.size ? `Skills (${selected.size})` : "Skills";
      button.classList.toggle("is-active", selected.size > 0);
      menu.innerHTML = usable.map(item => `
        <label class="skill-picker-item" role="menuitemcheckbox" aria-checked="${selected.has(item.name)}">
          <input type="checkbox" value="${esc(item.name)}" ${selected.has(item.name) ? "checked" : ""}>
          <span><b>${esc(item.name)}</b><small>${esc(item.description || "")}</small></span>
        </label>`).join("") + `<p class="hint skill-picker-hint">Selected skills load into the next message only.</p>`;
      qa("input", menu).forEach(input => input.addEventListener("change", () => {
        if (input.checked) selected.add(input.value); else selected.delete(input.value);
        paint();
      }));
    }

    button.addEventListener("click", event => {
      event.stopPropagation();
      open = !open;
      menu.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
      if (open) q("input", menu)?.focus();
    });
    menu.addEventListener("keydown", event => { if (event.key === "Escape") { open = false; menu.hidden = true; button.setAttribute("aria-expanded", "false"); button.focus(); } });
    document.addEventListener("click", event => {
      if (open && !wrap.contains(event.target)) { open = false; menu.hidden = true; button.setAttribute("aria-expanded", "false"); }
    });

    (async () => {
      try {
        const readiness = await callApi(`/v1/bots/${encodeURIComponent(bot.name)}/readiness`);
        if (!slot.isConnected) return;   // the composer was replaced while this loaded
        const skillArea = readiness.areas.find(area => area.id === "skills");
        const bound = new Set(bot.skills || []);
        usable = (skillArea ? skillArea.items : [])
          .filter(item => bound.has(item.name) && item.status === "ok")
          .map(item => ({ name: item.name, description: "" }));
        // descriptions come from the library (bounded, installed only)
        const report = await callApi("/v1/skills").catch(() => null);
        if (report) {
          const byName = new Map(report.skills.map(item => [item.name, item.description]));
          usable.forEach(item => { item.description = byName.get(item.name) || ""; });
        }
        paint();
      } catch { wrap.hidden = true; }
    })();

    return {
      selected: () => [...selected],
      consume: () => { selected = new Set(); paint(); },
    };
  }

  window.hutchSkills = { renderSkillsPage, mountBotPanel, mountComposer };
})();
