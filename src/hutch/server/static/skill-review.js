/* Two review surfaces for one skill package: what it says, and what an update would change.

   Both belong to the moment before a decision, and both are advisory. Kept in their own module
   so skills.js stays within its size budget and so the exact wording of an advisory finding is
   written once.

   Contract: every function takes the detail object the API returns and returns an HTML string.
   Nothing here decides anything; the server already decided what the operator may do. */
(() => {
  const esc = value => String(value ?? "").replace(/[&<>"']/g,
    char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const severityTone = severity => ({ danger: "danger", warning: "warn" }[severity] || "muted");

  /** What the content review found. A clean result says plainly that it is not a guarantee. */
  function scanHtml(detail) {
    const scan = detail?.scan;
    if (!scan) return "";
    if (!scan.findings?.length) {
      return `<p class="hint tone-muted">Content review found nothing to flag in ${esc(scan.scanned_files)} text file(s). ` +
        `That is not a guarantee: read the instructions before trusting the package.</p>`;
    }
    const items = scan.findings.map(finding => `<li class="tone-${severityTone(finding.severity)}">` +
      `<strong>${esc(finding.severity)}</strong>: ${esc(finding.message)}` +
      (finding.where ? ` <span class="mono">${esc(finding.where)}</span>` : "") +
      (finding.excerpt ? `<br><span class="mono">${esc(finding.excerpt)}</span>` : "") + "</li>").join("");
    const counts = `${esc(scan.counts.danger)} serious, ${esc(scan.counts.warning)} worth reading, ` +
      `${esc(scan.counts.info)} informational`;
    return `<details class="skill-instructions"${scan.counts.danger ? " open" : ""}>` +
      `<summary>Content review (${counts})</summary><ul class="hint">${items}</ul>` +
      `<p class="hint">${esc(scan.note)}</p></details>`;
  }

  /** What applying the staged update would change, led by anything that alters its requirements. */
  function stagedChangesHtml(detail) {
    const changes = detail?.staged_changes;
    if (!changes) return "";
    if (!changes.comparable) {
      return `<p class="hint tone-muted">This update could not be compared with the installed ` +
        `version: ${esc(changes.reason)}.</p>`;
    }
    const tone = changes.material.length ? "tone-warn" : "tone-info";
    return `<p class="hint ${tone}" role="status">What applying changes: ${esc(changes.summary)}.</p>`;
  }

  /** Install from whatever the operator typed: a folder path, or a published package URL.

      Two different server routes, one control. A URL install lands untrusted exactly like a local
      one, and the inspector shows where it came from, so the operator still makes the same review
      decision with one more fact available. */
  async function installSource(value, callApi) {
    const source = String(value || "").trim();
    if (/^https?:\/\//i.test(source)) {
      return callApi("/v1/skills/fetch", { method: "POST", body: { url: source } });
    }
    return callApi("/v1/skills/install", { method: "POST", body: { source: "path", path: source } });
  }



  /** The registry panel: what configured indexes list, and an explicit install for each entry.

      Discovery never installs. Every row is a separate act, and the row says what it is before the
      button does anything: a listing someone published, with a digest that pins bytes and not
      authorship. */
  function registrySectionHtml() {
    return `<section class="panel" id="skills-registry" aria-labelledby="skills-registry-title" hidden>
      <div class="panel-title" id="skills-registry-title">From a published registry</div>
      <div id="skills-registry-body"><p class="hint">Reading configured registries...</p></div>
    </section>`;
  }

  async function mountRegistry(container, { callApi, notify, reload }) {
    if (!container) return;
    let data;
    try {
      data = await callApi("/v1/skills/available");
    } catch (error) {
      container.hidden = false;
      document.getElementById("skills-registry-body").innerHTML =
        `<p class="hint">Registries could not be read: ${esc(error.message)}</p>`;
      return;
    }
    const body = document.getElementById("skills-registry-body");
    if (!body) return;
    container.hidden = false;
    const failures = (data.registries || []).filter(item => !item.ok)
      .map(item => `<li>${esc(item.registry_id)}: ${esc(item.reason)}</li>`).join("");
    const rows = (data.entries || []).map(entry => `<div class="list-row">
        <div><strong>${esc(entry.name)}</strong> <span class="tag">${esc(entry.registry_id)}</span>
        ${entry.version ? `<span class="mono small">${esc(entry.version)}</span>` : ""}
        ${entry.sha256 ? `<span class="tag">digest pinned</span>` : `<span class="tag">no digest</span>`}
        <p class="hint">${esc(entry.description || "The registry did not describe this package.")}</p></div>
        <div class="card-actions">${entry.installed
          ? `<span class="hint">Already installed</span>`
          : `<button class="btn small" data-registry-install="${esc(entry.name)}">Install</button>`}</div>
      </div>`).join("");
    body.innerHTML = !rows
      ? `<p class="hint">No configured registry lists a package${(data.registries || []).length ? "" : ". Add one below."}</p>
         ${failures ? `<ul class="hint">${failures}</ul>` : ""}
         <form class="hutch-form hutch-inline" id="skills-registry-add">
           <div class="hutch-field"><label class="hutch-label" for="skills-registry-url">Registry index URL</label>
             <input class="hutch-input" id="skills-registry-url" name="url" placeholder="https://example.com/skills.json" autocomplete="off" spellcheck="false"></div>
           <div class="hutch-actions"><button class="btn small" type="submit">Add registry</button></div>
         </form>`
      : `<div class="plain-list">${rows}</div>${failures ? `<ul class="hint">${failures}</ul>` : ""}
         <p class="hint">${esc(data.note || "")}</p>`;
    body.querySelectorAll("[data-registry-install]").forEach(button => {
      button.onclick = async () => {
        button.disabled = true;
        try {
          await callApi("/v1/skills/registries/install", { method: "POST", body: { name: button.dataset.registryInstall } });
          notify(`Installed ${button.dataset.registryInstall}. Review it, then trust it.`);
          await reload();
        } catch (error) { notify(`Not installed: ${error.message}`, true); button.disabled = false; }
      };
    });
  }

  window.HutchSkillReview = Object.freeze({ scanHtml, stagedChangesHtml, installSource,
                                            registrySectionHtml, mountRegistry });
})();
