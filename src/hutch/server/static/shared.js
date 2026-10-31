/* Shared: household and project spaces with explicit access.

   A shared space is a data scope. Nothing here grants an assistant access by
   default; each grant is shown and can be revoked, and credentials/integrations
   are never part of a space. Plain language first: this page is for people who
   do not want to understand agent internals. */
(function () {
  "use strict";

  const P = () => window.hutchPersonal;
  const ROLES = ["adult", "collaborator", "child", "read_only", "guest"];
  const ROLE_LABELS = { owner: "Owner", adult: "Adult", collaborator: "Collaborator",
    child: "Child", read_only: "Read only", guest: "Guest" };

  function header() {
    if (typeof window.setTopContext !== "function") return;
    window.setTopContext('<div class="ctx-id"><div class="ctx-heading"><h1>Shared</h1>' +
      '<span class="ctx-subtitle">Household and project spaces, with their own access</span></div></div>');
  }

  function knownBots() {
    const cached = typeof botsCache !== "undefined" && Array.isArray(botsCache) ? botsCache : [];
    return cached.map(bot => ({ id: bot.id, label: bot.display_name || bot.name }));
  }

  async function roster() {
    const cached = knownBots();
    if (cached.length) return cached;
    try {
      const fetched = await P().call("/bots");
      return (Array.isArray(fetched) ? fetched : []).map(bot => ({
        id: bot.id, label: bot.display_name || bot.name,
      }));
    } catch (error) {
      return [];
    }
  }

  function memberRows(space) {
    const members = space.members || [];
    if (!members.length) return '<p class="hint">No people yet. Add the people this space is for.</p>';
    return '<ul class="pd-people">' + members.map(member =>
      '<li class="pd-person' + (member.status === "revoked" ? " revoked" : "") + '">' +
      "<span><strong>" + P().esc(member.display_name) + "</strong> " +
      '<span class="tag pd-chip">' + P().esc(ROLE_LABELS[member.role] || member.role) + "</span>" +
      (member.status === "revoked" ? ' <span class="tag pd-chip">Removed</span>' : "") + "</span>" +
      (member.status === "active"
        ? '<button type="button" class="btn ghost small" data-shared-action="revoke-member" data-space="' +
          P().esc(space.id) + '" data-member="' + P().esc(member.member_id) + '">Remove access</button>' : "") +
      "</li>"
    ).join("") + "</ul>";
  }

  function grantRows(space, knownBotsList) {
    const known = knownBotsList || knownBots();
    const byId = {};
    known.forEach(bot => { byId[bot.id] = bot.label; });
    const grants = space.bot_grants || [];
    const rows = grants.map(id => '<li class="pd-person"><span><strong>' + P().esc(byId[id] || "Assistant") +
      '</strong> <span class="tag pd-chip">Can use this space</span></span>' +
      '<button type="button" class="btn ghost small" data-shared-action="revoke-bot" data-space="' +
      P().esc(space.id) + '" data-bot="' + P().esc(id) + '">Revoke</button></li>').join("");
    const available = known.filter(bot => grants.indexOf(bot.id) === -1);
    const picker = available.length
      ? '<div class="pd-inline-form"><div class="hutch-field pd-grant-picker"><label class="hutch-label" for="pd-grant-' +
        P().esc(space.id) + '">Let an assistant help here</label><select class="hutch-select" id="pd-grant-' +
        P().esc(space.id) + '" data-grant-select="' + P().esc(space.id) + '">' +
        available.map(bot => '<option value="' + P().esc(bot.id) + '">' + P().esc(bot.label) + "</option>").join("") +
        '</select></div><button type="button" class="btn small" data-shared-action="grant-bot" data-space="' +
        P().esc(space.id) + '">Grant access</button></div>'
      : '<p class="hint">Every assistant already has access to this space.</p>';
    return '<ul class="pd-people">' + rows + "</ul>" + picker +
      '<p class="hint">Access is per assistant and can be revoked at any time. Connected accounts, credentials ' +
      "and personal data are never shared by granting a space.</p>";
  }

  function commitmentList(space, items) {
    if (!items.length) return '<p class="hint">Nothing shared here yet.</p>';
    return '<ul class="pd-list">' + items.map(item => {
      const row = Object.assign({}, item, { space_name: space.name });
      return P().commitmentRow(row, { showScope: false });
    }).join("") + "</ul>";
  }

  function spaceCard(space, items, knownBotsList) {
    return '<article class="pd-space panel" aria-labelledby="pd-space-' + P().esc(space.id) + '">' +
      '<header class="pd-space-head"><div><h2 id="pd-space-' + P().esc(space.id) + '">' + P().esc(space.name) +
      '</h2><p class="hint">' + P().esc(space.kind) + " · " + space.active_members + " member" +
      (space.active_members === 1 ? "" : "s") + " · " + space.open_commitments + " open</p></div>" +
      '<button type="button" class="btn ghost small" data-shared-action="archive-space" data-space="' +
      P().esc(space.id) + '" data-revision="' + P().esc(space.revision) + '">Archive space</button></header>' +
      (space.archived ? '<p class="hint">Archived. Assistants no longer have access.</p>' : "") +
      '<div class="pd-space-cols">' +
        '<section class="pd-space-col"><h3 class="pd-subhead">People</h3>' + memberRows(space) +
          '<button type="button" class="btn ghost small" data-shared-action="add-member" data-space="' +
          P().esc(space.id) + '">Add a person</button></section>' +
        '<section class="pd-space-col"><h3 class="pd-subhead">Assistants</h3>' + grantRows(space, knownBotsList) + "</section>" +
      "</div>" +
      '<section class="pd-space-col"><h3 class="pd-subhead">Shared commitments</h3>' +
        commitmentList(space, items) +
        P().captureForm([space], { defaultSpace: space.id, allowPersonal: false }) +
      "</section></article>";
  }

  async function loadSpaceCommitments(spaces) {
    const result = {};
    await Promise.all((spaces || []).map(async space => {
      try {
        const page = await P().call("/v1/commitments?space=" + encodeURIComponent(space.id) +
          "&include_proposed=true&limit=100");
        result[space.id] = (page.items || []).filter(item => item.status === "open" ||
          (item.status === "done" && item.completion_kind === "unverified"));
      } catch (error) {
        result[space.id] = [];
      }
    }));
    return result;
  }

  function createForm() {
    return '<section class="pd-section" aria-labelledby="pd-new-space-title">' +
      '<div class="pd-section-head"><h2 id="pd-new-space-title">Create a space</h2>' +
      '<p class="hint">For a household, a project or a group of people. Each space keeps its own people, ' +
      "assistants and commitments.</p></div>" +
      '<form class="hutch-form pd-create-space" data-create-space novalidate><div class="pd-capture-row">' +
        '<div class="hutch-field pd-capture-title"><label class="hutch-label" for="pd-space-name">Name</label>' +
          '<input class="hutch-input" id="pd-space-name" name="name" type="text" maxlength="80" required ' +
          'placeholder="For example, Our household"></div>' +
        '<div class="hutch-field pd-capture-space"><label class="hutch-label" for="pd-space-kind">Kind</label>' +
          '<select class="hutch-select" id="pd-space-kind" name="kind">' +
          '<option value="household">Household</option><option value="project">Project</option>' +
          '<option value="team">Team</option></select></div>' +
        '<div class="pd-capture-submit"><button class="btn primary" type="submit">Create space</button></div>' +
      '</div><p class="pd-form-error hint" role="status" aria-live="polite" hidden></p></form></section>';
  }

  async function reload() {
    await renderSharedPage(true);
  }

  async function renderSharedPage(refresh) {
    header();
    const view = document.getElementById("view");
    if (!refresh) {
      view.innerHTML = '<div class="page-scroll"><div class="container"><p class="hint" role="status">Loading spaces…</p></div></div>';
    }
    try {
      const payload = await P().call("/v1/spaces");
      const spaces = payload.items || [];
      const known = await roster();
      const perSpace = await loadSpaceCommitments(spaces);
      view.innerHTML = '<div class="page-scroll"><div class="container pd-page pd-shared">' +
        '<p class="hint" role="note">Shared spaces scope what an assistant can read and change. They do not ' +
        "share connected accounts or credentials.</p>" + createForm() +
        (spaces.length
          ? '<div class="pd-space-list">' + spaces.map(space => spaceCard(space, perSpace[space.id] || [], known)).join("") + "</div>"
          : P().emptyState("No shared spaces yet", "Create a household or project space above to share commitments and reminders.")) +
        "</div></div>";
      const page = view.querySelector(".pd-page");
      if (!page) return;
      P().wireCapture(page, reload);
      P().wireActions(page, reload);
      page.addEventListener("click", event => void onAction(event, spaces));
      page.addEventListener("submit", event => void onCreateSpace(event));
    } catch (error) {
      view.innerHTML = '<div class="page-scroll"><div class="container"><div class="pd-empty" role="alert">' +
        '<p><strong>Shared spaces could not be loaded.</strong></p><p class="hint">' +
        P().esc(error.message || String(error)) + "</p></div></div></div>";
    }
  }

  async function onAction(event, spaces) {
    const button = event.target.closest("[data-shared-action]");
    if (!button) return;
    event.preventDefault();
    const action = button.dataset.sharedAction;
    const spaceId = button.dataset.space;
    const space = (spaces || []).find(item => item.id === spaceId);
    if (!space) return;
    button.disabled = true;
    try {
      if (action === "grant-bot") {
        const select = button.parentElement.querySelector("[data-grant-select]");
        const botId = select && select.value;
        if (!botId) return;
        await P().call("/v1/spaces/" + encodeURIComponent(spaceId) + "/bots", { method: "POST", body: { bot_id: botId } });
        P().notify("Access granted.");
      } else if (action === "revoke-bot") {
        await P().call("/v1/spaces/" + encodeURIComponent(spaceId) + "/bots/" +
          encodeURIComponent(button.dataset.bot), { method: "DELETE" });
        P().notify("Access revoked.");
      } else if (action === "revoke-member") {
        await P().call("/v1/spaces/" + encodeURIComponent(spaceId) + "/members/" +
          encodeURIComponent(button.dataset.member), { method: "DELETE" });
        P().notify("Access removed.");
      } else if (action === "archive-space") {
        const confirmed = await window.confirmDialog({
          title: "Archive this space?",
          body: "Assistants lose access immediately. The shared history stays readable but is no longer active.",
          confirmText: "Archive space", danger: true,
        });
        if (!confirmed) return;
        await P().call("/v1/spaces/" + encodeURIComponent(spaceId) + "/archive",
          { method: "POST", body: { expected_revision: Number(button.dataset.revision) } });
        P().notify("Space archived.");
      } else if (action === "add-member") {
        openMemberDialog(space, reload);
        return;
      } else {
        return;
      }
      await reload();
    } catch (error) {
      P().notify(error.message || "That did not work.", true);
    } finally {
      button.disabled = false;
    }
  }

  function openMemberDialog(space, done) {
    const options = ROLES.map(role => '<option value="' + role + '">' + ROLE_LABELS[role] + "</option>").join("");
    window.openModal({
      title: "Add a person to " + space.name,
      bodyHtml: '<p>People in a space can be given different levels of involvement. This records who the space ' +
        'is for; it does not create a separate login.</p><div class="hutch-field"><label class="hutch-label" ' +
        'for="pd-member-name">Name<input class="hutch-input" id="pd-member-name" type="text" maxlength="80"></label>' +
        '</div><div class="hutch-field"><label class="hutch-label" for="pd-member-role">Role' +
        '<select class="hutch-select" id="pd-member-role">' + options + "</select></label>" +
        '<p class="hutch-help">Owner and adult roles are intended for people who share decisions; read only and ' +
        'guest are for limited access.</p><p class="pd-form-error hint" role="status" aria-live="polite" hidden></p></div>',
      confirmText: "Add person",
      onConfirm: async () => {
        const name = String(document.getElementById("pd-member-name")?.value || "").trim();
        const role = document.getElementById("pd-member-role")?.value || "collaborator";
        const error = document.querySelector(".modal-card .pd-form-error");
        if (!name) { if (error) { error.textContent = "Add a name."; error.hidden = false; } return false; }
        try {
          await P().call("/v1/spaces/" + encodeURIComponent(space.id) + "/members",
            { method: "POST", body: { display_name: name, role } });
          P().notify("Person added.");
          if (typeof done === "function") await done();
          return true;
        } catch (err) {
          if (error) { error.textContent = err.message || "That did not work."; error.hidden = false; }
          return false;
        }
      },
    });
  }

  async function onCreateSpace(event) {
    const form = event.target.closest("[data-create-space]");
    if (!form) return;
    event.preventDefault();
    const error = form.querySelector(".pd-form-error");
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    if (!name) { if (error) { error.textContent = "Give the space a name."; error.hidden = false; } return; }
    try {
      await P().call("/v1/spaces", { method: "POST", body: { name, kind: String(data.get("kind") || "household") } });
      P().notify("Space created.");
      form.reset();
      await reload();
    } catch (err) {
      if (error) { error.textContent = err.message || "That did not work."; error.hidden = false; }
    }
  }

  window.hutchShared = { renderSharedPage };
})();
