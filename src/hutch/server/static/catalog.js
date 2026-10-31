/* Catalog: the agent store, built from the bundled reviewed manifests.

   A destination, not part of first run. Entries show who published them, their version and exact content
   hash, and what they ask to be allowed before anything is created. "Create a copy" opens the normal
   assistant setup with that entry preselected, so approval and creation stay in the existing reviewed flow.
   The export action runs the sharing checklist over a saved assistant and never uploads or creates anything. */

(function () {
  "use strict";

  const call = async (path, opts) => {
    if (typeof api === "function") return api(path, opts);
    const response = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...opts,
      body: opts && opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
    return response.json();
  };
  const escape = value => (typeof esc === "function" ? esc(value)
    : String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const notify = (message, error = false) => {
    if (typeof toast === "function") return toast(message, error);
    window.alert(message);
  };
  const setHeader = html => { if (typeof setTopContext === "function") setTopContext(html); };
  const el = (selector, root = document) => root.querySelector(selector);
  const iconOr = (name, fallback = "") => (typeof icon === "function" ? icon(name) : fallback);
  const page = () => el("#view");
  let cached = null;

  async function catalogData(refresh = false) {
    if (!cached || refresh) cached = await call("/v1/catalog");
    return cached;
  }

  function header() {
    setHeader('<div class="ctx-id"><div class="ctx-heading"><h1>Catalog</h1>'
      + '<span class="ctx-subtitle">Reviewed starters From Hutch, and the assistants you can share</span></div></div>');
  }

  function toolChips(permissions) {
    const tools = permissions.tools || [];
    if (!tools.length) return '<span class="tag">no tools</span>';
    return tools.map(tool => '<span class="tag' + ((permissions.elevated_tools || []).includes(tool) ? " warn" : "") + '">'
      + escape(tool) + "</span>").join(" ");
  }

  function entryCard(entry) {
    const shortHash = entry.content_hash.slice(0, 12);
    return '<article class="catalog-card panel" data-catalog-entry="' + escape(entry.id) + '">'
      + '<div class="catalog-card-head"><div><h2 class="card-title">' + escape(entry.name) + '</h2>'
      + '<p class="hint">' + escape(entry.publisher) + " · version " + escape(entry.version)
      + ' · <span class="mono" title="' + escape(entry.content_hash) + '">' + escape(shortHash) + '</span></p></div>'
      + '<span class="tag">' + escape(entry.category) + "</span></div>"
      + '<p>' + escape(entry.tagline) + "</p>"
      + '<p class="catalog-tools">' + toolChips(entry.permissions) + "</p>"
      + '<div class="catalog-card-actions"><a class="btn small" href="#/catalog/' + encodeURIComponent(entry.id) + '">Review</a>'
      + '<button type="button" class="btn ghost small" data-catalog-copy="' + escape(entry.id) + '">Create a copy</button></div></article>';
  }

  function listMarkup(data) {
    const entries = data.bundled.entries || [];
    const cards = entries.map(entryCard).join("");
    return '<div class="page-scroll"><div class="container catalog-page">'
      + '<p class="page-subtitle">Ready-made assistants are reviewed data, not built-ins: each one carries its publisher,'
      + ' version and content hash. Creating a copy opens the normal setup review and only that separate action saves it.</p>'
      + '<div class="catalog-search-row"><label class="hutch-label" for="catalog-search">Search</label>'
      + '<input class="hutch-input" id="catalog-search" type="search" placeholder="Search by name, publisher or what it does" autocomplete="off"></div>'
      + '<p class="hint" id="catalog-count" role="status" aria-live="polite">' + entries.length + " entries</p>"
      + '<div class="catalog-grid" id="catalog-grid">' + cards + "</div>"
      + '<p class="hint" id="catalog-empty" hidden>Nothing matches that search.</p>'
      + exportMarkup() + "</div></div>";
  }

  function exportMarkup() {
    return '<section class="panel catalog-export" aria-labelledby="catalog-share-title">'
      + '<h2 id="catalog-share-title">Share one of your assistants</h2>'
      + '<p class="hint">Exports a portable catalog template you can share yourself. <b>Nothing is uploaded.</b> The checklist'
      + ' checks for credentials and flags URLs, e-mail addresses and absolute paths; memory, history, attachments, facts and'
      + ' schedules are never included.</p>'
      + '<label class="hutch-label" for="catalog-export-bot">Assistant</label><select class="hutch-select" id="catalog-export-bot"></select>'
      + '<div class="hutch-actions"><button type="button" class="btn primary small" id="catalog-export-button">Review template</button>'
      + '<span class="hint" id="catalog-export-status" role="status" aria-live="polite"></span></div></section>';
  }

  function detailMarkup(entry) {
    const permissions = entry.permissions || {};
    const rules = (permissions.command_rules || []).map(rule => '<li>' + escape(rule.verdict) + " <code>" + escape(rule.match) + "</code></li>").join("");
    const elevated = (permissions.elevated_tools || []);
    return '<div class="page-scroll"><div class="container catalog-page">'
      + '<p><a href="#/catalog">' + iconOr("arrowLeft") + " All entries</a></p>"
      + '<div class="panel catalog-detail"><div class="catalog-card-head"><div>'
      + '<h1 class="card-title">' + escape(entry.name) + '</h1><p class="hint">'
      + escape(entry.publisher) + " · version " + escape(entry.version) + " · " + escape(entry.category) + "</p></div></div>"
      + '<p>' + escape(entry.tagline) + "</p>"
      + '<h2 class="card-title">What it asks for</h2>'
      + '<p class="hint">Creating a copy never grants more than the copy\'s own saved settings and Hutch\'s approvals allow.'
      + (elevated.length ? " Elevated tools are marked and still need their usual approvals." : "") + "</p>"
      + '<ul class="catalog-permissions"><li>Tools: ' + toolChips(permissions) + "</li>"
      + (elevated.length ? "<li>Elevated: " + elevated.map(escape).join(", ") + "</li>" : "")
      + (rules ? "<li>Command rules:<ul>" + rules + "</ul></li>" : "<li>No command rules.</li>")
      + "<li>Needs a folder: " + (permissions.needs_folder ? "yes" : "no") + "</li>"
      + (entry.permissions && entry.permissions.note ? "<li>" + escape(entry.permissions.note) + "</li>" : "") + "</ul>"
      + (entry.manifest ? '<details><summary>Instructions the model would receive</summary><pre class="catalog-instructions" tabindex="0">' + escape(entry.manifest.assistant.instructions) + "</pre></details>" : "")
      + '<p class="hint">Provenance: publisher <b>' + escape(entry.publisher) + "</b>, version " + escape(entry.version)
      + ', content hash <span class="mono">' + escape(entry.content_hash) + '</span>.</p>'
      + '<div class="hutch-actions"><button type="button" class="btn primary" data-catalog-copy="' + escape(entry.id) + '">Create a copy</button>'
      + '<a class="btn ghost" href="#/catalog">Back to the catalog</a></div></div></div></div>';
  }

  function wireSearch(data) {
    const input = el("#catalog-search"), grid = el("#catalog-grid"), empty = el("#catalog-empty"), count = el("#catalog-count");
    if (!input || !grid) return;
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      let shown = 0;
      grid.querySelectorAll("[data-catalog-entry]").forEach(card => {
        const text = card.textContent.toLowerCase();
        const hit = !query || text.includes(query);
        card.hidden = !hit;
        shown += hit ? 1 : 0;
      });
      if (empty) empty.hidden = shown !== 0;
      if (count) count.textContent = shown + (shown === 1 ? " entry" : " entries");
    });
  }

  async function wireExport(data) {
    const select = el("#catalog-export-bot"), button = el("#catalog-export-button"), status = el("#catalog-export-status");
    if (!select || !button) return;
    let bots = [];
    try { bots = await call("/bots"); } catch (error) { status.textContent = "Assistants could not be loaded: " + error.message; return; }
    select.innerHTML = bots.map(bot => '<option value="' + escape(bot.name) + '">' + escape(bot.display_name || bot.name) + "</option>").join("");
    if (!bots.length) { select.innerHTML = '<option value="">No assistants yet</option>'; button.disabled = true; }
    button.addEventListener("click", async () => {
      if (!select.value) return;
      button.disabled = true;
      status.textContent = "Checking the text for credentials and private details…";
      try {
        const review = await call("/v1/catalog/export-draft", { method: "POST", body: { bot: select.value } });
        status.textContent = "";
        if (review.blocked.length) {
          openReview("This assistant cannot be exported yet",
            '<p role="alert"><b>Remove these before sharing:</b></p><ul>' + review.blocked.map(item => "<li>" + escape(item) + "</li>").join("") + "</ul>"
            + '<p class="hint">Nothing was downloaded or sent.</p>', null);
          return;
        }
        openReview("Review before sharing", reviewMarkup(review), () => download(review.manifest, select.value));
      } catch (error) {
        status.textContent = "Could not prepare the template: " + error.message;
      } finally {
        button.disabled = false;
      }
    });
  }

  function reviewMarkup(review) {
    return '<p class="hint">Nothing is uploaded. Review the checklist, then download a JSON template you can share yourself.</p>'
      + '<ul class="catalog-checklist">' + review.checklist.map(item => "<li>" + escape(item) + "</li>").join("") + "</ul>"
      + (review.warnings.length ? '<div class="flash notice" role="status"><b>Review these:</b><ul>'
          + review.warnings.map(item => "<li>" + escape(item) + "</li>").join("") + "</ul></div>" : "")
      + '<details><summary>Never included</summary><ul>' + review.omitted.map(item => "<li>" + escape(item) + "</li>").join("") + "</ul></details>"
      + '<details><summary>Template JSON</summary><pre class="catalog-instructions" tabindex="0">' + escape(JSON.stringify(review.manifest, null, 2)) + "</pre></details>";
  }

  function openReview(title, bodyHtml, onConfirm) {
    if (typeof openModal !== "function") { notify(title); return; }
    openModal({ title, bodyHtml, wide: true, confirmText: onConfirm ? "Download template" : "Close",
      confirmClass: onConfirm ? "primary" : "ghost", showCancel: !!onConfirm,
      onConfirm: () => { if (onConfirm) onConfirm(); return true; } });
  }

  function download(manifest, botName) {
    const blob = new Blob([JSON.stringify(manifest, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = String(botName || manifest.id || "catalog") + "-template.json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify("Template prepared. Check the file before sharing it.");
  }

  function wireCreateCopy() {
    document.addEventListener("click", event => {
      const button = event.target.closest?.("[data-catalog-copy]");
      if (!button) return;
      event.preventDefault();
      const name = button.dataset.catalogCopy;
      if (typeof promptNewBot !== "function") return notify("Assistant setup is not available.", true);
      promptNewBot(name);
    });
  }

  async function render(capture) {
    header();
    const root = page();
    if (!root) return;
    root.innerHTML = '<div class="page-scroll"><div class="container"><p class="hint" role="status">Loading the catalog…</p></div></div>';
    try {
      const data = await catalogData();
      if (capture) {
        const entry = data.bundled.entries.find(item => item.id === capture);
        if (!entry) {
          root.innerHTML = '<div class="page-scroll"><div class="container"><div class="empty-state"><p>No catalog entry named ' + escape(capture) + '.</p><p><a href="#/catalog">All entries</a></p></div></div></div>';
          return;
        }
        root.innerHTML = detailMarkup(entry);
          return;
      }
      root.innerHTML = listMarkup(data);
      wireSearch(data);
      await wireExport(data);
    } catch (error) {
      root.innerHTML = '<div class="page-scroll"><div class="container"><div class="empty-state"><p><b>Could not load the catalog.</b></p><p class="hint">' + escape(error.message) + '</p><p><button class="btn ghost small" type="button" data-catalog-retry="1">Try again</button></p></div></div></div>';
      root.querySelector("[data-catalog-retry]")?.addEventListener("click", () => { cached = null; void render(null); });
    }
  }

  wireCreateCopy();   // one delegated listener for every rendered card

  window.hutchCatalog = { render, clearCache: () => { cached = null; } };
})();