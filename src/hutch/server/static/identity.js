/* Reviewed identity: the person's profile and each assistant's boundaries, edited in place.

   Both documents live in the state directory as bounded JSON (see src/hutch/identity.py) and render into
   the system prompt as advisory context. This module only offers the review-and-save surface: it mounts a
   card into the assistant settings Behavior pane and the workspace Settings page, shows the exact text a
   model would receive, and saves only after a confirmation. Nothing here is written by a model tool. */

(function () {
  "use strict";

  const call = async (path, opts) => {
    if (typeof api === "function") return api(path, opts);
    const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts,
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
  const review = (title, bodyHtml, confirmText) => new Promise(resolve => {
    if (typeof openModal !== "function") { resolve(window.confirm(title)); return; }
    let settled = false;
    openModal({ title, bodyHtml, confirmText, confirmClass: "primary", wide: true,
      onConfirm: () => { settled = true; resolve(true); return true; },
      onCancel: () => { if (!settled) { settled = true; resolve(false); } } });
  });
  const preview = text => '<pre class="identity-preview" tabindex="0">' + escape(text) + "</pre>";
  const currentBotName = () => {
    const match = /^#\/bot\/([^/?]+)/.exec(location.hash || "");
    if (!match) return "";
    try { return decodeURIComponent(match[1]); } catch { return match[1]; }
  };

  function assistantCard(data) {
    const documentText = data.identity;
    const limits = data.limits;
    const problem = data.diagnostics.length ? "<strong>" + escape(data.diagnostics.join(" ")) + "</strong>" : "";
    return '<form class="panel hutch-form" id="identity-assistant-form">' +
      '<h3 class="panel-title settings-panel-title">Identity and boundaries</h3>' +
      '<p class="hint">Advisory text saved on this machine and put in this assistant\'s prompt. It never widens tools, ' +
      'approvals, budgets or data access; the rules of engagement and your saved settings still govern. ' + problem + '</p>' +
      '<div class="hutch-field"><label class="hutch-label" for="identity-signature">How it signs off</label>' +
      '<textarea class="hutch-textarea" id="identity-signature" rows="2" maxlength="' + limits.max_signature_chars + '" ' +
      'placeholder="Optional: how it should close a report or a handoff">' + escape(documentText.signature) + '</textarea></div>' +
      '<div class="hutch-field"><label class="hutch-label" for="identity-boundaries">Boundaries</label>' +
      '<textarea class="hutch-textarea" id="identity-boundaries" rows="4" placeholder="One per line, up to ' + limits.max_boundaries + '">' +
      escape(documentText.boundaries.join("\n")) + '</textarea>' +
      '<span class="hutch-help">One boundary per line, at most ' + limits.max_boundaries + ', each under ' +
      limits.max_boundary_chars + ' characters. Saved boundaries are guidance; command rules and approvals enforce access.</span></div>' +
      '<details class="identity-current"><summary>What the model currently receives</summary>' +
      preview(data.rendered || "(nothing saved yet)") + '</details>' +
      '<div class="hutch-actions"><button class="btn primary small" type="submit">Review and save identity</button> ' +
      '<span class="hint" id="identity-assistant-status" role="status" aria-live="polite"></span></div></form>';
  }

  function bindAssistant(slot, name, data) {
    slot.innerHTML = assistantCard(data);
    const form = slot.querySelector("#identity-assistant-form");
    const status = slot.querySelector("#identity-assistant-status");
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const signature = form.querySelector("#identity-signature").value.trim();
      const boundaries = form.querySelector("#identity-boundaries").value.split("\n")
        .map(line => line.trim()).filter(Boolean);
      if (boundaries.length > data.limits.max_boundaries) {
        return notify("At most " + data.limits.max_boundaries + " boundaries.", true);
      }
      const tooLong = boundaries.find(line => line.length > data.limits.max_boundary_chars);
      if (tooLong) return notify("A boundary is longer than " + data.limits.max_boundary_chars + " characters.", true);
      const changed = signature !== data.identity.signature
        || JSON.stringify(boundaries) !== JSON.stringify(data.identity.boundaries);
      if (!changed) { status.textContent = "Nothing changed."; return; }
      const body = { expected_revision: data.identity.revision, signature, boundaries };
      const summary = [signature ? "Signs off: " + signature : "No sign-off line.",
        boundaries.length ? "Boundaries:\n" + boundaries.map(line => "- " + line).join("\n") : "No boundaries."];
      const confirmed = await review("Save " + name + "'s identity?",
        '<p>This exact text is saved in Hutch\'s state directory and added to this assistant\'s prompt.</p>' +
        preview(summary.join("\n\n")) +
        '<p class="hint">Boundaries are advisory context. Tool access, approvals, budgets and data-sharing stay governed by your settings.</p>',
        "Save identity");
      if (!confirmed) return;
      status.textContent = "Saving…";
      try {
        const saved = await call("/v1/bots/" + encodeURIComponent(name) + "/identity", { method: "PUT", body });
        bindAssistant(slot, name, saved);
        notify("Identity saved. It applies from the next message.");
      } catch (error) {
        status.textContent = "";
        notify("Identity was not saved: " + error.message, true);
      }
    });
  }

  function personCard(data) {
    const profile = data.profile;
    const problem = data.diagnostics.length ? "<strong>" + escape(data.diagnostics.join(" ")) + "</strong>" : "";
    return '<form class="panel hutch-form" id="identity-person-form">' +
      '<h2 class="panel-title">About you</h2>' +
      '<p class="hint">Saved locally and shown to <strong>every assistant</strong>. It never grants access or changes ' +
      'approvals; each assistant still follows its own settings. ' + problem + '</p>' +
      '<div class="hutch-field"><label class="hutch-label" for="identity-preferred-name">Preferred name</label>' +
      '<input class="hutch-input" id="identity-preferred-name" maxlength="80" value="' + escape(profile.preferred_name) +
      '" placeholder="What should assistants call you?"></div>' +
      '<div class="hutch-field"><label class="hutch-label" for="identity-about">About you</label>' +
      '<textarea class="hutch-textarea" id="identity-about" rows="4" maxlength="2000" ' +
      'placeholder="Context an assistant should know when working for you">' + escape(profile.about) + '</textarea></div>' +
      '<div class="hutch-field"><label class="hutch-label" for="identity-treat">How to treat you</label>' +
      '<textarea class="hutch-textarea" id="identity-treat" rows="3" maxlength="1000" ' +
      'placeholder="Tone, pace, how much detail you want">' + escape(profile.treat_person) + '</textarea></div>' +
      '<details class="identity-current"><summary>What assistants currently receive</summary>' +
      preview(data.rendered || "(nothing saved yet)") + '</details>' +
      '<div class="hutch-actions"><button class="btn primary small" type="submit">Review and save profile</button> ' +
      '<span class="hint" id="identity-person-status" role="status" aria-live="polite"></span></div></form>';
  }

  function bindPerson(slot, data) {
    slot.innerHTML = personCard(data);
    const form = slot.querySelector("#identity-person-form");
    const status = slot.querySelector("#identity-person-status");
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const body = {
        expected_revision: data.profile.revision,
        preferred_name: form.querySelector("#identity-preferred-name").value.trim(),
        about: form.querySelector("#identity-about").value.trim(),
        treat_person: form.querySelector("#identity-treat").value.trim(),
      };
      if (body.preferred_name === data.profile.preferred_name && body.about === data.profile.about
          && body.treat_person === data.profile.treat_person) { status.textContent = "Nothing changed."; return; }
      const lines = [body.preferred_name && "Preferred name: " + body.preferred_name,
        body.about && "About you: " + body.about,
        body.treat_person && "How to treat you: " + body.treat_person].filter(Boolean);
      const confirmed = await review("Save your profile?",
        "<p>Every assistant sees this text in its prompt. It is saved only on this machine.</p>" +
        preview(lines.join("\n\n") || "(nothing)"), "Save profile");
      if (!confirmed) return;
      status.textContent = "Saving…";
      try {
        const saved = await call("/v1/identity/person", { method: "PUT", body });
        bindPerson(slot, saved);
        notify("Profile saved. Assistants see it from the next message.");
      } catch (error) {
        status.textContent = "";
        notify("Profile was not saved: " + error.message, true);
      }
    });
  }

  async function mount(slot) {
    const kind = slot.dataset.identitySlot;
    try {
      if (kind === "assistant") {
        const name = currentBotName();
        if (!name) return;
        bindAssistant(slot, name, await call("/v1/bots/" + encodeURIComponent(name) + "/identity"));
      } else if (kind === "person") {
        bindPerson(slot, await call("/v1/identity/person"));
      }
    } catch (error) {
      slot.innerHTML = '<p class="hint" role="alert">Identity could not be loaded: ' + escape(error.message) + "</p>";
    }
  }

  function scan() {
    document.querySelectorAll("[data-identity-slot]:not([data-identity-mounted])").forEach(slot => {
      slot.dataset.identityMounted = "1";
      void mount(slot);
    });
  }

  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan);
  else scan();
})();
