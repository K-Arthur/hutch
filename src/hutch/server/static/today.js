/* Today: what needs you, what is due, and what already ran.

   A deterministic projection from GET /api/v1/today. Nothing here is generated
   prose: every line names its source and links to the authoritative page, and the
   view repeats the server's list of what was not considered. */
(function () {
  "use strict";

  const P = () => window.hutchPersonal;

  function header() {
    if (typeof window.setTopContext !== "function") return;
    window.setTopContext('<div class="ctx-id"><div class="ctx-heading"><h1>Today</h1>' +
      '<span class="ctx-subtitle">Commitments, scheduled work and what needs you</span></div></div>');
  }

  function section(id, title, count, intro, body, tone) {
    return '<section class="pd-section' + (tone ? " " + tone : "") + '" aria-labelledby="pd-' + id + '">' +
      '<div class="pd-section-head"><h2 id="pd-' + id + '">' + title +
      (count ? ' <span class="count">' + count + "</span>" : "") + "</h2>" +
      (intro ? '<p class="hint">' + intro + "</p>" : "") + "</div>" + body + "</section>";
  }

  function list(items, options) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(item => P().commitmentRow(item, options || {})).join("") + "</ul>";
  }

  function annotate(items, spaces) {
    const names = {};
    (spaces || []).forEach(space => { names[space.id] = space.name; });
    return (items || []).map(item => Object.assign({}, item, {
      space_name: item.space_id ? (names[item.space_id] || "Shared space") : "",
    }));
  }

  function approvalRows(items) {
    if (!items.length) return "";
    return '<ul class="pd-list pd-approvals">' + items.map(item =>
      '<li class="pd-item"><div class="pd-item-head"><strong class="pd-title">' +
      P().esc(item.bot_label) + " · " + P().esc(item.action || item.tool) + "</strong>" +
      '<span class="tag pd-chip">' + P().esc(item.risk || "medium") + " risk</span></div>" +
      '<p class="pd-meta">' + P().esc(item.tool) +
      (item.expires_at ? " · expires " + P().esc(P().formatDue(item.expires_at)) : "") +
      '</p><div class="pd-actions"><a class="btn small primary" href="#/approvals">Review</a></div></li>'
    ).join("") + "</ul>";
  }

  function runRows(items) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(run =>
      '<li class="pd-item"><div class="pd-item-head"><a class="pd-title" href="' + P().esc(run.href) + '">' +
      P().esc(run.bot_label) + " · " + P().esc(run.subject || run.prompt || run.status_label) + "</a>" +
      '<span class="tag pd-chip">' + P().esc(run.status_label) + "</span></div>" +
      '<p class="pd-meta">' + P().esc(P().formatDue(run.finished_at || run.created_at)) +
      (run.exit_reason ? " · " + P().esc(run.exit_reason) : "") + "</p></li>"
    ).join("") + "</ul>";
  }

  function scheduleRows(items) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(row =>
      '<li class="pd-item"><div class="pd-item-head"><strong class="pd-title">' + P().esc(row.name) + "</strong>" +
      '<span class="tag pd-chip">' + P().esc(row.bot_label) + "</span></div>" +
      '<p class="pd-meta">Next ' + P().esc(P().formatDue(row.next_at, row.timezone)) +
      " · " + P().esc(row.timezone) + '</p></li>'
    ).join("") + "</ul>";
  }

  function blockedRows(items) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(row =>
      '<li class="pd-item"><div class="pd-item-head"><strong class="pd-title">' + P().esc(row.name) + "</strong>" +
      '<span class="tag pd-chip">Needs a look</span></div><p class="pd-meta">' +
      P().esc(row.bot_label) + " · " + P().esc(row.reason || "scheduled work is blocked") + "</p></li>"
    ).join("") + "</ul>";
  }

  function documentRows(items) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(doc =>
      '<li class="pd-item"><div class="pd-item-head">' +
      (doc.href ? '<a class="pd-title" href="' + P().esc(doc.href) + '">' : '<strong class="pd-title">') +
      P().esc(doc.filename) + (doc.href ? "</a>" : "</strong>") +
      '<span class="tag pd-chip">' + P().esc(doc.validation === "valid" ? "Validated" : doc.validation) + "</span></div>" +
      '<p class="pd-meta">' + P().esc(doc.bot_label) + " · " + P().esc(doc.mime || "document") +
      (doc.bytes ? " · " + Math.max(1, Math.round(doc.bytes / 1024)) + " KB" : "") + "</p></li>"
    ).join("") + "</ul>";
  }

    function alertRows(items) {
    if (!items || !items.length) return "";
    return '<ul class="pd-list">' + items.map(row => {
      const state = row.delivery === "not queued" ? "Not sent"
        : row.delivery === "sent" ? "Sent" : row.delivery === "uncertain" ? "Delivery unconfirmed"
        : row.delivery === "pending" ? "Queued" : row.delivery;
      return '<li class="pd-item"><div class="pd-item-head"><a class="pd-title" href="' + P().esc(row.href) + '">' +
        P().esc(row.kind_label) + " · " + P().esc(row.bot_label) + "</a>" +
        '<span class="tag pd-chip' + (row.delivery === "uncertain" ? " stale" : "") + '">' +
        P().esc(state) + '</span></div><p class="pd-meta">' +
        P().esc(P().formatDue(row.created_at)) + "</p></li>";
    }).join("") + "</ul>";
  }

  function spaceSummary(spaces) {
    if (!spaces || !spaces.length) {
      return '<p class="hint">No shared spaces yet. Create one for a household, a project or a group on ' +
        '<a href="#/shared">Shared</a>.</p>';
    }
    return '<div class="pd-space-grid">' + spaces.map(space =>
      '<a class="pd-space-card" href="#/shared"><strong>' + P().esc(space.name) + "</strong>" +
      '<span class="hint">' + space.active_members + " member" + (space.active_members === 1 ? "" : "s") +
      " · " + space.bot_grants.length + " assistant" + (space.bot_grants.length === 1 ? "" : "s") +
      " · " + space.open_commitments + " open</span></a>"
    ).join("") + "</div>";
  }

  const AGENDA_KEY = "hutch.pd.agenda";

  function agendaSelection() {
    try {
      const stored = JSON.parse(window.localStorage.getItem(AGENDA_KEY) || "{}");
      return stored && typeof stored === "object" ? stored : {};
    } catch (error) { return {}; }
  }

  function rememberAgenda(next) {
    try { window.localStorage.setItem(AGENDA_KEY, JSON.stringify(next)); } catch (error) { /* storage is optional */ }
  }

  function agendaSection() {
    return section("agenda", "Agenda", 0,
      "Calendar and mail you choose to include, each labelled with its source and the time it was read.",
      '<div class="pd-agenda" data-pd-agenda><p class="hint" role="status">Loading calendar and mail…</p></div>');
  }

  function agendaBadge(source) {
    if (source.status === "stale") return '<span class="tag pd-chip stale">Stale</span>';
    if (source.status === "unavailable") return '<span class="tag pd-chip unavailable">Unavailable</span>';
    return "";
  }

  function agendaItemRows(source, timezone) {
    if (!source.items || !source.items.length) {
      const empty = source.kind === "calendar" ? "No events in your local day."
        : "No messages in the last 24 hours.";
      return '<p class="hint">' + P().esc(empty) + "</p>";
    }
    return '<ul class="pd-list pd-agenda-list">' + source.items.map(item => {
      const stamp = item.kind === "event" ? item.starts_at : item.received_at;
      const meta = [stamp ? P().formatDue(stamp, timezone) : "", item.location || item.from]
        .filter(Boolean).map(value => P().esc(value)).join(" · ");
      return '<li class="pd-item" data-agenda-item="' + P().esc(item.kind) + '" data-source="' +
        P().esc(item.source) + '" data-fetched-at="' + P().esc(item.fetched_at) + '">' +
        '<div class="pd-item-head"><strong class="pd-title">' + P().esc(item.title) + "</strong>" +
        (item.stale ? '<span class="tag pd-chip stale">Stale</span>' : "") + "</div>" +
        (meta ? '<p class="pd-meta">' + meta + "</p>" : "") +
        (item.preview ? '<p class="pd-detail">' + P().esc(item.preview) + "</p>" : "") +
        '<p class="pd-meta pd-agenda-item-source">' + P().esc(item.source_label || "") +
        (item.fetched_at ? " · read " + P().esc(P().formatDue(item.fetched_at, timezone)) : "") + "</p></li>";
    }).join("") + "</ul>";
  }

  function agendaSourceBlock(source, timezone) {
    if (source.status === "not_configured") return "";
    const head = '<div class="pd-agenda-head"><strong>' + P().esc(source.source_label) + "</strong>" +
      agendaBadge(source) + "</div>";
    if (source.status === "unavailable") {
      return '<div class="pd-agenda-source" data-agenda-status="unavailable">' + head +
        '<p class="hint" role="status">' + P().esc(source.reason || "This source could not be read.") +
        ' <a href="#/connections">Review connections</a></p></div>';
    }
    const read = source.fetched_at ? P().formatDue(source.fetched_at, timezone) : "";
    const note = source.status === "stale"
      ? '<p class="hint" role="status">Showing the last successful read' +
        (read ? " (" + P().esc(read) + ")" : "") + ". The refresh failed: " +
        P().esc(source.reason) + '</p>'
      : '<p class="pd-meta">Read ' + P().esc(read) + "</p>";
    return '<div class="pd-agenda-source" data-agenda-status="' + P().esc(source.status) + '">' + head +
      note + agendaItemRows(source, timezone) + "</div>";
  }

  function agendaOption(value, text, selected, disabled) {
    return '<option value="' + P().esc(value) + '"' + (selected === value ? " selected" : "") +
      (disabled ? " disabled" : "") + ">" + P().esc(text) + "</option>";
  }

  function agendaPicker(sources, chosen) {
    const calendar = ['<option value="">No calendar</option>'].concat((sources.calendar || []).map(
      row => agendaOption(row.bot_id, row.bot_label + " · " + row.calendar_name, chosen.calendar)));
    const mail = ['<option value="">No mail</option>'].concat((sources.mail || []).map(
      row => agendaOption(row.bot_id, row.bot_label + (row.local_inference ? "" : " (Local inference only)"),
        chosen.mail, !row.local_inference)));
    return '<form class="pd-agenda-picker" data-pd-agenda-form>' +
      '<div class="hutch-field"><label class="hutch-label" for="pd-agenda-calendar">Calendar</label>' +
      '<select class="hutch-select" id="pd-agenda-calendar" name="calendar">' + calendar.join("") + "</select></div>" +
      '<div class="hutch-field"><label class="hutch-label" for="pd-agenda-mail">Mail</label>' +
      '<select class="hutch-select" id="pd-agenda-mail" name="mail">' + mail.join("") + "</select></div>" +
      '<div class="pd-capture-submit"><button class="btn" type="submit">Show agenda</button></div>' +
      '<p class="hutch-help">Only the connection you pick is read, once per refresh. Nothing is stored in your database.</p></form>';
  }

  async function loadAgenda(page, timezone) {
    const host = page.querySelector("[data-pd-agenda]");
    if (!host) return;
    let sources;
    try {
      sources = await P().call("/v1/personal/agenda/sources");
    } catch (error) {
      host.innerHTML = '<p class="hint" role="status">Calendar and mail connections could not be listed: ' +
        P().esc(error.message || String(error)) + "</p>";
      return;
    }
    if (!(sources.calendar || []).length && !(sources.mail || []).length) {
      host.innerHTML = '<div class="pd-empty"><p><strong>No calendar or mailbox is connected yet.</strong></p>' +
        '<p class="hint">Connect an account and grant one calendar or mailbox to an assistant in ' +
        '<a href="#/connections">Connections</a>. Today will not guess what your day holds.</p></div>';
      return;
    }
    const stored = agendaSelection();
    const usable = (rows, onlyLocal) => (rows || []).filter(row => !onlyLocal || row.local_inference)
      .map(row => row.bot_id);
    const selection = {
      calendar: usable(sources.calendar, false).includes(stored.calendar) ? stored.calendar : "",
      mail: usable(sources.mail, true).includes(stored.mail) ? stored.mail : "",
    };
    host.innerHTML = agendaPicker(sources, selection) +
      '<div data-pd-agenda-result><p class="hint" role="status">Loading your agenda…</p></div>';
    const form = host.querySelector("[data-pd-agenda-form]");
    const result = host.querySelector("[data-pd-agenda-result]");
    const load = async () => {
      if (!selection.calendar && !selection.mail) {
        result.innerHTML = '<p class="hint">Choose a calendar or mailbox above to include it in Today.</p>';
        return;
      }
      const params = new URLSearchParams();
      if (timezone) params.set("timezone", timezone);
      if (selection.calendar) params.set("calendar", selection.calendar);
      if (selection.mail) params.set("mail", selection.mail);
      result.innerHTML = '<p class="hint" role="status">Loading your agenda…</p>';
      try {
        const data = await P().call("/v1/personal/agenda?" + params.toString());
        result.innerHTML = agendaSourceBlock(data.sources.calendar, data.timezone) +
          agendaSourceBlock(data.sources.mail, data.timezone);
      } catch (error) {
        result.innerHTML = '<p class="hint" role="alert">The agenda could not be read: ' +
          P().esc(error.message || String(error)) + "</p>";
      }
    };
    form.addEventListener("change", () => {
      selection.calendar = form.querySelector("#pd-agenda-calendar").value;
      selection.mail = form.querySelector("#pd-agenda-mail").value;
      rememberAgenda(selection);
      void load();
    });
    form.addEventListener("submit", event => { event.preventDefault(); void load(); });
    await load();
  }

  function render(data) {
    const sections = data.sections;
    const commitments = sections.commitments;
    const spaces = sections.spaces || [];
    const at = item => annotate([item], spaces)[0];
    const annotated = group => annotate(group, spaces);
    const parts = [];

    if (data.counts.approvals > 0) {
      parts.push(section("needs", "Needs you", data.counts.approvals,
        "Actions waiting for your decision.", approvalRows(sections.approvals.items), "loud"));
    }

    parts.push(agendaSection());

    parts.push(section("capture", "Add a commitment", 0,
      "Capture it now; it stays yours until you mark it done.",
      P().captureForm(spaces, { defaultSpace: "" })));

    parts.push('<div class="pd-groups">' +
      section("overdue", "Overdue", commitments.overdue.length,
        "Past the date you set.", list(annotated(commitments.overdue)), "warn") +
      section("today", "Due today", commitments.due_today.length,
        "In your local day (" + P().esc(data.timezone) + ").", list(annotated(commitments.due_today))) +
      section("suggested", "Suggested by assistants", commitments.proposed.length,
        "Proposals, not commitments until you confirm them.", list(annotated(commitments.proposed))) +
      section("reported", "Reported done", commitments.reported_done.length,
        "An assistant says these are finished. Verify them before trusting that.", list(annotated(commitments.reported_done))) +
      section("upcoming", "Next 7 days", commitments.upcoming.length, "", list(annotated(commitments.upcoming))) +
      section("undated", "No date yet", commitments.undated.length, "", list(annotated(commitments.undated))) +
      section("completed", "Completed today", commitments.completed_today.length, "", list(annotated(commitments.completed_today))) +
      "</div>");

    const scheduleIntro = sections.schedules.paused
      ? "Scheduled work is paused for this workspace. New occurrences will not start until you resume it on Scheduled work."
      : "Today's scheduled occurrences for enabled schedules.";
    parts.push(section("schedules", "Scheduled work", sections.schedules.upcoming_today.length, scheduleIntro,
      scheduleRows(sections.schedules.upcoming_today) + blockedRows(sections.schedules.blocked) +
      (!sections.schedules.upcoming_today.length && !sections.schedules.blocked.length
        ? P().emptyState("Nothing scheduled today", "Recurring work appears here when a schedule fires in your local day.") : "")));

    const runs = sections.runs;
    if (runs.working.length || runs.needs_attention.length) {
      parts.push(section("runs", "Work in progress", runs.working.length + runs.needs_attention.length,
        "Actual run state, not an estimate.",
        (runs.working.length ? '<h3 class="pd-subhead">Working now</h3>' + runRows(runs.working) : "") +
        (runs.needs_attention.length ? '<h3 class="pd-subhead">Interrupted or needs review</h3>' +
          runRows(runs.needs_attention) : "")));
    }

    if (sections.deliverables.length) {
      parts.push(section("deliverables", "Deliverables today", sections.deliverables.length,
        "Generated files, with their validation state.", documentRows(sections.deliverables)));
    }

    if (sections.alerts && sections.alerts.length) {
      parts.push(section("alerts", "Alerts Hutch sent", sections.alerts.length,
        "What Hutch told your connected channel, with its delivery state. Delivery is not proof it was read.",
        alertRows(sections.alerts)));
    }

    parts.push(section("spaces", "Shared", spaces.length,
      "Household and project spaces, each with its own access grants.", spaceSummary(spaces)));

    parts.push('<p class="pd-note hint" role="note"><strong>What this view does not include:</strong> ' +
      P().esc(data.not_included.join(" ")) + "</p>");

    return '<div class="page-scroll"><div class="container pd-page">' +
      '<p class="pd-generated hint">As of ' + P().esc(P().formatDue(data.generated_at, data.timezone)) +
      " · local date " + P().esc(data.local_date) + " · " + P().esc(data.timezone) +
      ' <button type="button" class="btn ghost small" data-pd-refresh>Refresh</button></p>' +
      parts.join("") + "</div></div>";
  }

  async function renderTodayPage() {
    header();
    const view = document.getElementById("view");
    view.innerHTML = '<div class="page-scroll"><div class="container"><p role="status" class="hint">Loading your day…</p></div></div>';
    try {
      const zone = P().tz();
      const data = await P().call("/v1/today" + (zone ? "?timezone=" + encodeURIComponent(zone) : ""));
      view.innerHTML = render(data);
      const page = view.querySelector(".pd-page");
      if (!page) return;
      P().wireCapture(page, renderTodayPage);
      P().wireActions(page, renderTodayPage);
      void loadAgenda(page, data.timezone);
      page.addEventListener("click", event => {
        if (event.target.closest("[data-pd-refresh]")) { event.preventDefault(); void renderTodayPage(); }
      });
    } catch (error) {
      view.innerHTML = '<div class="page-scroll"><div class="container"><div class="pd-empty" role="alert">' +
        '<p><strong>Today could not be loaded.</strong></p><p class="hint">' + P().esc(error.message || String(error)) +
        '</p><p><button type="button" class="btn" data-pd-refresh>Try again</button></p></div></div></div>';
      view.querySelector("[data-pd-refresh]")?.addEventListener("click", () => void renderTodayPage());
    }
  }

  window.hutchToday = { renderTodayPage };
})();
