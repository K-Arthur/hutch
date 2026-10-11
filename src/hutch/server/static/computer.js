/* Computer-session panel for the run view.
 *
 * Shows, for a run that operated a browser tab or an isolated desktop: who controls the surface, the environment, the last
 * captured frame (with its capture time; it is never called "live"), and recent control changes. Stop and Resume reuse the
 * feed's existing delegated handlers (data-stop-run / data-human-resume), so there is one implementation of each.
 *
 * Everything that came from a page or an application (URL, title, reasons) is untrusted and is written with textContent.
 */
(function () {
  "use strict";

  var POLL_MS = 3000;
  var STALE_AFTER_S = 15;

  var OWNER = {
    agent: { label: "Hutch is in control", detail: "Hutch may act, subject to approvals." },
    human: { label: "You are in control", detail: "Hutch will not act until control is handed back." },
    paused: { label: "Paused", detail: "Nobody is acting. Hutch will not continue until resumed." },
    stopping: { label: "Stopping", detail: "No further action will run while cleanup finishes." },
    stopped: { label: "Stopped", detail: "The session ended and its cleanup was verified." },
    recovery_required: { label: "Needs recovery", detail: "Cleanup could not be verified. Check the host before running again." }
  };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === "text") node.textContent = attrs[key];
      else if (key === "class") node.className = attrs[key];
      else if (key.indexOf("data-") === 0 || key.indexOf("aria-") === 0 || key === "role" || key === "type" || key === "id") {
        node.setAttribute(key, attrs[key]);
      } else node[key] = attrs[key];
    });
    (children || []).forEach(function (child) { if (child) node.appendChild(child); });
    return node;
  }

  function ago(iso, nowIso) {
    var then = Date.parse(iso);
    var now = nowIso ? Date.parse(nowIso) : Date.now();
    if (!isFinite(then) || !isFinite(now)) return null;
    return Math.max(0, Math.round((now - then) / 1000));
  }

  function human(seconds) {
    if (seconds < 90) return seconds + " s";
    if (seconds < 5400) return Math.round(seconds / 60) + " min";
    return Math.round(seconds / 3600) + " h";
  }

  function render(root, runId, state) {
    var section = root.querySelector("[data-computer-panel]");
    if (!state || !state.active) {
      if (section) section.remove();
      return;
    }
    var owner = (state.control && state.control.owner) || (state.run_status === "waiting_human" ? "human" : "agent");
    var meta = OWNER[owner] || OWNER.agent;
    var running = ["running", "waiting_approval", "waiting_human", "queued", "pending", "cancelling"].indexOf(state.run_status) >= 0;
    var desktop = state.surface === "desktop";

    // Re-render only when something a person would notice changed. Otherwise only the capture age is refreshed, so the
    // frame is not downloaded again (or flickered) on every poll, which also matters on a phone connection.
    var signature = [owner, state.run_status, state.surface, state.frame && state.frame.frame_id, state.human_needed_seq,
                     (state.history || []).length, state.control && state.control.reason].join("|");
    if (section && section.getAttribute("data-sig") === signature) {
      var existing = section.querySelector(".computer-caption span");
      var fresh = state.frame && state.frame.captured_at;
      if (existing && fresh) {
        var seconds = ago(fresh, state.now);
        var isStale = !running || (seconds !== null && seconds > STALE_AFTER_S);
        existing.textContent = !running ? "Final frame; the session has ended."
          : "Last captured " + (seconds === null ? "at an unknown time" : human(seconds) + " ago") +
            (isStale ? " \u2014 not a live view." : ". This is a still capture, not a live view.");
        var figureNode = section.querySelector(".computer-frame");
        if (figureNode) figureNode.classList.toggle("is-stale", isStale);
      }
      return;
    }

    var next = el("section", { class: "computer-panel panel", "data-computer-panel": runId, "data-sig": signature,
      "aria-labelledby": "computer-title-" + runId });
    var head = el("div", { class: "computer-head" }, [
      el("h2", { id: "computer-title-" + runId, class: "computer-title", text: desktop ? "Isolated desktop" : "Browser tab" }),
      el("p", { class: "computer-owner", "data-owner": owner, role: "status", text: meta.label })
    ]);
    next.appendChild(head);
    next.appendChild(el("p", { class: "hint computer-owner-detail", text: meta.detail }));
    if (state.control && state.control.reason) {
      next.appendChild(el("p", { class: "hint computer-reason", text: "Latest change: " + state.control.reason }));
    }

    if (desktop) {
      var env = state.environment || {};
      next.appendChild(el("p", { class: "hint computer-env",
        text: "Separate display and input from your own desktop. Applications run as you and can use your network and files; this is not a sandbox." +
              (env.applications && env.applications.length ? " Allowed applications: " + env.applications.join(", ") + "." : "") }));
    } else if (state.frame && state.frame.page && state.frame.page.url) {
      next.appendChild(el("p", { class: "hint computer-env", text: "Page: " + state.frame.page.url + (state.frame.page.id ? " (tab " + state.frame.page.id + ")" : "") }));
    }

    var frame = state.frame;
    if (frame) {
      var age = ago(frame.captured_at, state.now);
      var stale = !running || (age !== null && age > STALE_AFTER_S);
      var caption = !running ? "Final frame; the session has ended."
        : "Last captured " + (age === null ? "at an unknown time" : human(age) + " ago") + (stale ? " — not a live view." : ". This is a still capture, not a live view.");
      var figure = el("figure", { class: "computer-frame" + (stale ? " is-stale" : "") });
      var img = el("img", { class: "computer-img", alt: "Last captured frame of the " + (desktop ? "isolated desktop" : "browser tab") + ", " + frame.width + " by " + frame.height + " pixels. " + caption,
        src: frame.url + "?v=" + encodeURIComponent(frame.frame_id), width: frame.width, height: frame.height, decoding: "async" });
      img.addEventListener("error", function () {
        figure.classList.add("is-missing");
        var note = figure.querySelector(".computer-missing");
        if (!note) figure.insertBefore(el("p", { class: "computer-missing", role: "status",
          text: "This frame is no longer retained. Older frames are removed to keep storage bounded." }), figure.firstChild);
      });
      figure.appendChild(img);
      figure.appendChild(el("figcaption", { class: "computer-caption" }, [
        el("span", { text: caption }), el("span", { class: "computer-meta", text: " Frame " + frame.frame_id + ", " + frame.width + " by " + frame.height + " px" })
      ]));
      next.appendChild(figure);
    } else {
      next.appendChild(el("p", { class: "hint", text: "No frame has been captured yet." }));
    }

    var actions = el("div", { class: "computer-actions" });
    if (state.human_needed_seq) {
      actions.appendChild(el("button", { class: "btn primary small", type: "button", "data-human-resume": "", "data-run-id": runId,
        "data-event-seq": String(state.human_needed_seq), text: "I've finished my step — resume" }));
    }
    if (running && owner !== "stopping") {
      actions.appendChild(el("button", { class: "btn danger small", type: "button", "data-stop-run": runId, text: "Stop" }));
    }
    if (actions.childNodes.length) next.appendChild(actions);
    next.appendChild(el("p", { class: "hint computer-limits", text: state.remote_control_note || "" }));

    if (state.history && state.history.length) {
      var list = el("ol", { class: "computer-history", "aria-label": "Recent control changes" });
      state.history.slice().reverse().forEach(function (item) {
        var meta2 = OWNER[item.owner] || { label: String(item.owner) };
        list.appendChild(el("li", { text: meta2.label + (item.reason ? " — " + item.reason : "") }));
      });
      next.appendChild(el("details", { class: "computer-history-wrap" }, [el("summary", { text: "Control history" }), list]));
    }

    var previous = section;
    var previousOwner = previous && previous.querySelector(".computer-owner") && previous.querySelector(".computer-owner").dataset.owner;
    if (previous) previous.replaceWith(next); else root.insertBefore(next, root.firstChild);
    // restrained announcement: only a change of who is in control is a status update worth reading out
    if (previousOwner && previousOwner === owner) next.querySelector(".computer-owner").removeAttribute("role");
  }

  function mount(root, runId) {
    if (!root || !runId) return function () {};
    var stopped = false;
    var timer = 0;
    var controller = null;
    var quiet = 0;          // consecutive polls that found no computer surface on this run

    function visible() { return typeof document.hidden === "boolean" ? !document.hidden : true; }

    async function tick() {
      if (stopped) return;
      if (!root.isConnected) { stop(); return; }
      if (!visible()) { timer = setTimeout(tick, POLL_MS); return; }
      controller = typeof AbortController === "function" ? new AbortController() : null;
      var state = null;
      try {
        var response = await fetch("/api/v1/tasks/runs/" + encodeURIComponent(runId) + "/computer", {
          headers: { accept: "application/json" }, credentials: "same-origin", signal: controller && controller.signal });
        if (response.ok) state = await response.json();
      } catch (_error) { /* a failed poll leaves the last render in place; the next tick retries */ }
      if (stopped || !root.isConnected) return;
      var delay = POLL_MS;
      if (state) {
        render(root, runId, state);
        var live = ["running", "waiting_approval", "waiting_human", "queued", "pending", "cancelling"].indexOf(state.run_status) >= 0;
        if (!live) { stop(); return; }
        // A run that has not used a browser tab or desktop yet is checked on a slowly widening interval; a run that is
        // using one is refreshed every few seconds.
        quiet = state.active ? 0 : quiet + 1;
        delay = state.active ? POLL_MS : Math.min(30000, POLL_MS + quiet * 4000);
      }
      timer = setTimeout(tick, delay);
    }

    function stop() {
      stopped = true;
      clearTimeout(timer);
      if (controller) controller.abort();
    }

    tick();
    return stop;
  }

  window.HutchComputer = { mount: mount, render: render };
})();
