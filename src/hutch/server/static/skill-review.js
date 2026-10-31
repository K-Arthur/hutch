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

  window.HutchSkillReview = Object.freeze({ scanHtml, stagedChangesHtml, installSource });
})();
