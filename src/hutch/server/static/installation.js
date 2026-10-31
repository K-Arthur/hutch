/* Installation review: state an earlier version left behind, and a one-time welcome for a new browser.

   The server computes the issues read-only (src/hutch/installation.py). This module never deletes or changes
   an assistant, run or file: it shows the current state, links to the existing governed actions (assistant
   settings, whole-assistant deletion, Activity), and records only that the person reviewed the current set.
   The header carries one small control so a non-empty/legacy installation is recognised on any device; the
   same control becomes a one-time "Welcome back" on a browser that has not seen this Hutch before. */

(function () {
  "use strict";

  const apiCall = async (path, opts) => {
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
  const WELCOME_KEY = "hutch:installation:welcomed";

  function closeButton(id) {
    document.getElementById(id)?.remove();
  }

  function headerControl(id, label, title, onClick) {
    const status = document.getElementById("app-top-status");
    if (!status) return null;
    closeButton(id);
    const button = document.createElement("button");
    button.type = "button";
    button.id = id;
    button.className = "btn ghost small app-top-installation";
    const glyph = typeof icon === "function" ? icon("shield") : "";
    button.innerHTML = glyph + '<span class="app-top-installation-label">' + escape(label) + "</span>";
    button.title = title;
    button.setAttribute("aria-label", title);
    button.addEventListener("click", onClick);
    const live = document.getElementById("live-pill");
    status.insertBefore(button, live || null);
    return button;
  }

  function issueHtml(issue) {
    if (issue.kind === "assistant") {
      return '<li><p><b>' + escape(issue.display_name) + '</b> <span class="tag">' + escape(issue.model || "no route")
        + '</span></p><p>' + escape(issue.reason) + ". " + escape(issue.fix) + '</p><p class="hutch-actions">'
        + '<a class="btn ghost small" href="' + escape(issue.href) + '">Choose a model route</a> '
        + '<a class="btn ghost small" href="' + escape(issue.remove_href) + '">Remove assistant</a></p></li>';
    }
    const link = issue.href ? '<a href="' + escape(issue.href) + '">' + escape(issue.fix) + '</a>' : escape(issue.fix);
    return '<li><p><b>' + escape(issue.reason) + '</b></p><p>' + link + '</p></li>';
  }

  function reviewBody(state) {
    const assistants = state.assistant_count;
    return '<p>This Hutch has <b>' + assistants + ' assistant' + (assistants === 1 ? "" : "s")
      + '</b>. Some state comes from an earlier version and has not been reviewed on this installation yet.</p>'
      + '<p class="hint">Nothing is deleted, rewritten, sent or closed by reviewing. Each action below opens the'
      + ' normal governed page; the roster keeps showing any assistant that still cannot run.</p>'
      + '<ul class="installation-issues">' + state.open_issues.map(issueHtml).join("") + '</ul>'
      + '<p class="hint">Continuing records that you saw this state. A new problem after this appears once more.</p>';
  }

  function mountSettingsCard(state) {
    const slot = document.querySelector('[data-installation-slot="settings"]');
    if (!slot) return;
    const reviewed = state.reviewed_at ? new Date(state.reviewed_at).toLocaleDateString() : "not yet";
    slot.innerHTML = '<section class="panel" aria-labelledby="installation-card-title">'
      + '<h2 class="panel-title" id="installation-card-title">Installation</h2>'
      + '<p class="hint">' + escape(state.assistant_count) + ' assistant' + (state.assistant_count === 1 ? "" : "s")
      + ' · reviewed ' + escape(reviewed) + (state.open_issues.length
        ? ' · <b>' + state.open_issues.length + ' item' + (state.open_issues.length === 1 ? "" : "s") + ' need review</b>'
        : ' · nothing needs review') + '</p>'
      + '<div class="hutch-actions"><button type="button" class="btn ghost small" id="installation-settings-review">Review installation</button>'
      + '<button type="button" class="btn ghost small" id="installation-settings-check">Check setup</button></div>'
      + '<div id="installation-settings-findings" class="hint" role="status" aria-live="polite"></div></section>';
    slot.querySelector("#installation-settings-review")?.addEventListener("click", () => openReview(state));
    slot.querySelector("#installation-settings-check")?.addEventListener("click", async event => {
      const target = slot.querySelector("#installation-settings-findings");
      const button = event.currentTarget;
      button.disabled = true;
      target.textContent = "Checking…";
      try {
        const report = await apiCall("/v1/setup/check");
        const findings = (report.checks || report.findings || []).filter(c => c.status && c.status !== "ok");
        target.innerHTML = findings.length
          ? findings.map(c => '<p><b>' + escape(c.title || c.id) + ':</b> ' + escape(c.detail || "")
              + (c.fix ? ' <a href="#/runtime">Fix</a>' : "") + '</p>').join("")
          : "Everything checks out.";
      } catch (error) {
        target.textContent = "Setup check failed: " + error.message;
      } finally {
        button.disabled = false;
      }
    });
  }

  function openReview(state) {
    if (typeof openModal !== "function") { notify("Review this installation from Settings."); return; }
    openModal({ title: "Review this installation", bodyHtml: reviewBody(state), wide: true, confirmText: "This looks right — continue",
      confirmClass: "primary",
      onConfirm: async () => {
        try {
          await apiCall("/v1/installation/review", { method: "POST" });
          closeButton("installation-review");
          notify("Installation reviewed.");
          void refresh();
          return true;
        } catch (error) {
          notify("Could not record the review: " + error.message, true);
          return false;
        }
      } });
  }

  function openWelcome(state) {
    if (typeof openModal !== "function") return;
    openModal({ title: "Welcome back to this Hutch", confirmText: "Continue to this Hutch", confirmClass: "primary",
      bodyHtml: '<p>This browser has not seen this Hutch before. Your installation already has <b>'
        + state.assistant_count + ' assistant' + (state.assistant_count === 1 ? "" : "s") + '</b>.'
        + (state.reviewed_at ? ' Installation reviewed ' + escape(new Date(state.reviewed_at).toLocaleDateString()) + "." : "")
        + '</p><p class="hint">Recognising this browser stores one small marker locally. It does not create, change or share any assistant, run or account.</p>'
        + '<p><a href="/pair">Set up the Hutch app on a phone</a> · <a href="#/activity">Open Activity</a></p>',
      onConfirm: () => {
        try { localStorage.setItem(WELCOME_KEY, state.reviewed_at || "ready"); } catch { /* private mode */ }
        closeButton("installation-welcome");
        notify("This browser is recognised for this Hutch.");
        return true;
      } });
  }

  async function refresh() {
    let state;
    try {
      state = await apiCall("/v1/installation");
    } catch (error) {
      return;
    }
    if (state.state === "needs_review") {
      headerControl("installation-review", "Review install", "Review this Hutch installation",
                    () => openReview(state));
    } else {
      closeButton("installation-review");
      if (state.state === "ready") {
        let welcomed = "";
        try { welcomed = localStorage.getItem(WELCOME_KEY) || ""; } catch { /* private mode */ }
        const marker = state.reviewed_at || "ready";
        if (welcomed !== marker) {
          headerControl("installation-welcome", "Welcome back", "Welcome back to this Hutch installation",
                        () => openWelcome(state));
        } else {
          closeButton("installation-welcome");
        }
      } else {
        closeButton("installation-welcome");
      }
    }
    mountSettingsCard(state);
  }

  window.hutchInstallation = { refresh, openReview: () => refresh().then(() => {}) };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { void refresh(); });
  else void refresh();

  // Re-check when the SPA renders Settings (the card lives there) and after a review.
  new MutationObserver(() => {
    if (document.querySelector('[data-installation-slot="settings"]:not([data-installation-mounted])')) {
      document.querySelectorAll('[data-installation-slot="settings"]').forEach(node => {
        node.dataset.installationMounted = "1";
      });
      void refresh();
    }
  }).observe(document.body, { childList: true, subtree: true });
})();
