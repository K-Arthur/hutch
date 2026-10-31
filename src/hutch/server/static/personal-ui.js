/* Personal operations UI helpers: commitment rows, capture, completion review.

   Shared by the Today and Shared pages. Presentation and owner commands only;
   the server decides what is allowed. Vanilla ES, no build step; app.js globals
   (api, esc, icon, toast, openModal, setTopContext, botsCache) are read at call
   time so this file can load before or after the page handlers. */
(function () {
  "use strict";

  const esc = value => (typeof window.esc === "function" ? window.esc(value)
    : String(value == null ? "" : value).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const call = (path, opts) => window.api(path, opts || {});
  const notify = (message, error) => { if (typeof window.toast === "function") window.toast(message, error === true); };
  const iconOr = (name, fallback) => (typeof window.icon === "function" ? window.icon(name) : (fallback || ""));
  const key = () => (window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID()
    : "k" + Date.now() + Math.random().toString(36).slice(2));

  const COMMANDS = {
    confirm: { path: "confirm", label: "Confirm", done: "Confirmed. It is now a commitment." },
    complete: { path: "complete", label: "Mark done", done: "Completion recorded." },
    verify: { path: "verify", label: "Verify", done: "Verified as your own completed work." },
    reopen: { path: "reopen", label: "Reopen", done: "Reopened." },
    cancel: { path: "cancel", label: "Cancel", done: "Cancelled." },
  };

  function formatDue(iso, timezone) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    try {
      return new Intl.DateTimeFormat(undefined, {
        weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
        timeZone: timezone || undefined,
      }).format(date);
    } catch (error) {
      return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
    }
  }

  function dayDistance(iso) {
    if (!iso) return "";
    const due = new Date(iso).getTime();
    if (Number.isNaN(due)) return "";
    const days = Math.round((due - Date.now()) / 86400000);
    if (days < -1) return Math.abs(days) + " days overdue";
    if (days === -1) return "Yesterday";
    if (days === 0) return "Today";
    if (days === 1) return "Tomorrow";
    if (days <= 7) return "In " + days + " days";
    return "";
  }

  function scopeChip(item) {
    return item.space_name ? '<span class="tag pd-chip">' + esc(item.space_name) + "</span>"
      : '<span class="tag pd-chip pd-personal">Personal</span>';
  }

  function provenance(item) {
    if (item.confirmation === "proposed") {
      return '<span class="pd-prov proposed">Suggested by an assistant. Confirm it to add it as your commitment.</span>';
    }
    if (item.status === "done" && item.completion_kind === "unverified") {
      return '<span class="pd-prov reported">Reported by an assistant. Not verified yet.</span>';
    }
    if (item.status === "done" && item.completion_kind === "owner_confirmed") {
      return '<span class="pd-prov verified">Verified by you' +
        (item.completion_evidence ? ": " + esc(item.completion_evidence) : "") + "</span>";
    }
    if (item.completion_evidence) return '<span class="pd-prov">' + esc(item.completion_evidence) + "</span>";
    return "";
  }

  function actionButtons(item) {
    const buttons = [];
    const rev = item.revision;
    const cmd = (name, label, cls) => '<button type="button" class="btn small ' + (cls || "ghost") +
      '" data-commitment-action="' + name + '" data-commitment-id="' + esc(item.id) +
      '" data-revision="' + esc(rev) + '">' + esc(label) + "</button>";
    if (item.confirmation === "proposed" && item.status === "open") {
      buttons.push(cmd("confirm", "Confirm", "primary"));
      buttons.push(cmd("cancel", "Dismiss"));
    } else if (item.status === "open") {
      buttons.push(cmd("complete", "Mark done", "primary"));
      buttons.push(cmd("cancel", "Cancel"));
    } else if (item.status === "done" && item.completion_kind === "unverified") {
      buttons.push(cmd("verify", "Verify", "primary"));
      buttons.push(cmd("reopen", "Reopen"));
    } else if (item.status === "done") {
      buttons.push(cmd("reopen", "Reopen"));
    }
    return buttons.length ? '<div class="pd-actions">' + buttons.join("") + "</div>" : "";
  }

  function commitmentRow(item, options) {
    const opts = options || {};
    const due = item.due_at ? formatDue(item.due_at, item.due_timezone) : "";
    const relative = dayDistance(item.due_at);
    const classes = ["pd-item"];
    if (item.status === "done") classes.push("pd-done");
    if (item.status === "cancelled") classes.push("pd-cancelled");
    if (item.overdue) classes.push("pd-overdue");
    if (item.blocked) classes.push("pd-blocked");
    const meta = [];
    if (due) meta.push('<span class="pd-due' + (item.overdue ? " late" : "") + '">' +
      iconOr("clock") + esc(due) + (relative ? " · " + esc(relative) : "") + "</span>");
    if (item.priority === "high") meta.push('<span class="pd-priority">High priority</span>');
    if (item.blocked) meta.push('<span class="pd-priority">Blocked by an open commitment</span>');
    const body = [
      '<div class="pd-item-head"><strong class="pd-title">' + esc(item.title) + "</strong>" +
        '<span class="pd-chips">' + (opts.showScope === false ? "" : scopeChip(item)) +
        (item.confirmation === "proposed" ? '<span class="tag pd-chip proposed">Suggested</span>' : "") +
        (item.status === "done" && item.completion_kind === "unverified"
          ? '<span class="tag pd-chip reported">Reported done</span>' : "") +
        (item.status === "cancelled" ? '<span class="tag pd-chip">Cancelled</span>' : "") +
        "</span></div>",
      item.detail ? '<p class="pd-detail">' + esc(item.detail) + "</p>" : "",
      meta.length ? '<p class="pd-meta">' + meta.join("") + "</p>" : "",
      provenance(item),
      opts.actions === false ? "" : actionButtons(item),
    ];
    return '<li class="' + classes.join(" ") + '" data-commitment-row="' + esc(item.id) + '">' +
      body.join("") + "</li>";
  }

  function emptyState(title, copy) {
    return '<div class="pd-empty"><p><strong>' + esc(title) + '</strong></p><p class="hint">' + esc(copy) + "</p></div>";
  }

  function spaceOptions(spaces, selected, allowPersonal) {
    const rows = [];
    if (allowPersonal) rows.push('<option value=""' + (!selected ? " selected" : "") + ">Personal</option>");
    (spaces || []).forEach(space => {
      rows.push('<option value="' + esc(space.id) + '"' + (selected === space.id ? " selected" : "") +
        ">" + esc(space.name) + "</option>");
    });
    return rows.join("");
  }

  function captureForm(spaces, options) {
    const opts = options || {};
    return '<form class="hutch-form pd-capture" data-pd-capture novalidate>' +
      '<div class="pd-capture-row">' +
        '<div class="hutch-field pd-capture-title"><label class="hutch-label" for="pd-new-title">Commitment</label>' +
          '<input class="hutch-input" id="pd-new-title" name="title" type="text" maxlength="200" required ' +
            'placeholder="For example, Pay the water bill or Book the dentist" autocomplete="off"></div>' +
        '<div class="hutch-field pd-capture-due"><label class="hutch-label" for="pd-new-due">Due</label>' +
          '<input class="hutch-input" id="pd-new-due" name="due" type="datetime-local"></div>' +
        (opts.spaces === false ? "" :
          '<div class="hutch-field pd-capture-space"><label class="hutch-label" for="pd-new-space">For</label>' +
            '<select class="hutch-select" id="pd-new-space" name="space_id">' +
            spaceOptions(spaces, opts.defaultSpace || "", opts.allowPersonal !== false) + "</select></div>") +
        '<div class="pd-capture-submit"><button class="btn primary" type="submit">Add</button></div>' +
      "</div>" +
      '<p class="hutch-help">Saved as your own commitment. Assistants can suggest commitments; those appear as suggestions until you confirm them.</p>' +
      '<p class="pd-form-error hint" role="status" aria-live="polite" hidden></p></form>';
  }

  function toIso(localValue, timezone) {
    if (!localValue) return null;
    const date = new Date(localValue);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
  }

  const tz = () => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined; }
    catch (error) { return undefined; }
  };

  async function createCommitment(payload) {
    return call("/v1/commitments", {
      method: "POST", headers: { "Idempotency-Key": key() }, body: payload,
    });
  }

  function wireCapture(container, refresh) {
    container.addEventListener("submit", async event => {
      const form = event.target.closest("[data-pd-capture]");
      if (!form) return;
      event.preventDefault();
      const error = form.querySelector(".pd-form-error");
      const data = new FormData(form);
      const title = String(data.get("title") || "").trim();
      if (!title) {
        if (error) { error.textContent = "Give the commitment a short title."; error.hidden = false; }
        return;
      }
      if (error) error.hidden = true;
      const button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      try {
        const due = toIso(String(data.get("due") || ""));
        await createCommitment({
          title, due_at: due, due_timezone: tz(),
          space_id: String(data.get("space_id") || "") || null,
        });
        notify("Commitment added.");
        form.reset();
        if (typeof refresh === "function") await refresh();
      } catch (err) {
        if (error) { error.textContent = err.message || "That did not work."; error.hidden = false; }
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  async function runCommand(id, action, revision, extra) {
    const command = COMMANDS[action];
    if (!command) throw new Error("Unknown command");
    const body = Object.assign({ expected_revision: Number(revision) || undefined }, extra || {});
    return call("/v1/commitments/" + encodeURIComponent(id) + "/" + command.path, { method: "POST", body });
  }

  function completionDialog(item, onDone) {
    const body = '<p>Record what shows this is finished. The evidence is kept with the commitment.</p>' +
      '<div class="hutch-field"><label class="hutch-label" for="pd-evidence">What shows it is done?<textarea class="hutch-textarea" id="pd-evidence" rows="3" maxlength="2000" placeholder="Receipt number, confirmation email, or what you observed"></textarea></label>' +
      '<p class="pd-form-error hint" role="status" aria-live="polite" hidden></p></div>';
    window.openModal({
      title: "Mark done",
      bodyHtml: body,
      confirmText: "Record completion",
      onConfirm: async () => {
        const field = document.getElementById("pd-evidence");
        const evidence = String(field && field.value || "").trim();
        const error = document.querySelector(".modal-card .pd-form-error") || document.querySelector(".pd-form-error");
        if (!evidence) { if (error) { error.textContent = "Add what shows it is done."; error.hidden = false; } return false; }
        try {
          await runCommand(item.id, "complete", item.revision, { evidence });
          notify("Completion recorded.");
          if (typeof onDone === "function") await onDone();
          return true;
        } catch (err) {
          if (error) { error.textContent = err.message || "That did not work."; error.hidden = false; }
          return false;
        }
      },
    });
  }

  function wireActions(container, refresh) {
    container.addEventListener("click", async event => {
      const button = event.target.closest("[data-commitment-action]");
      if (!button) return;
      event.preventDefault();
      const id = button.dataset.commitmentId;
      const action = button.dataset.commitmentAction;
      const revision = button.dataset.revision;
      if (action === "complete") {
        completionDialog({ id: id, revision: revision }, refresh);
        return;
      }
      button.disabled = true;
      try {
        await runCommand(id, action, revision);
        notify((COMMANDS[action] || {}).done || "Updated.");
        if (typeof refresh === "function") await refresh();
      } catch (err) {
        notify(err.message || "That did not work.", true);
        button.disabled = false;
      }
    });
  }

  function describeServerError(error) {
    return (error && error.message) || "That did not work.";
  }

  window.hutchPersonal = {
    esc, call, notify, iconOr, key, formatDue, dayDistance, commitmentRow, emptyState,
    spaceOptions, captureForm, wireCapture, wireActions, runCommand, completionDialog, tz,
    describeServerError, createCommitment,
  };
})();
