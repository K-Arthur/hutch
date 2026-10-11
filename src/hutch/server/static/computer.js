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
  var CONTROLS = new Map();

  var OWNER = {
    agent: { label: "Hutch is in control", detail: "Hutch may act, subject to approvals." },
    human: { label: "Human control", detail: "Hutch will not act until control is explicitly handed back." },
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
        text: "Separate display and input from your own desktop. " + (env.boundary ? env.boundary + "." : "App containment was not recorded; this frame does not prove a sandbox boundary.") +
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
    var controllerPresent = (state.human_sessions || []).some(function(s) { return s.controller_present; });
    if (state.human_needed_seq && !controllerPresent) {
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
    var remote = previous && previous.querySelector(".computer-remote");
    if (remote) next.appendChild(remote); // preserve the controller's form/focus while ordinary run state is refreshed
    var previousOwner = previous && previous.querySelector(".computer-owner") && previous.querySelector(".computer-owner").dataset.owner;
    if (previous) previous.replaceWith(next); else root.insertBefore(next, root.firstChild);
    // restrained announcement: only a change of who is in control is a status update worth reading out
    if (previousOwner && previousOwner === owner) next.querySelector(".computer-owner").removeAttribute("role");
  }

  function mount(root, runId, options) {
    if (!root || !runId) return function () {};
    var stopped = false;
    var timer = 0;
    var controller = null;
    var quiet = 0;          // consecutive polls that found no computer surface on this run
    var remoteControl = null;

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
        if (state.remote_control && !remoteControl && options && options.api) remoteControl = mountControl(root, runId, options.api, state);
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
      if (remoteControl) remoteControl.close();
    }

    tick();
    return stop;
  }

  function mountControl(root, runId, api, state) {
    var viewer = crypto.randomUUID().replace(/-/g, ""), token = "", generation = 0, sequence = 0;
    var frame = null, busy = false, closed = false, objectUrl = "", heartbeat = 0, epoch = 0;
    var prefix = "/v1/tasks/runs/" + encodeURIComponent(runId) + "/computer";
    var pane = el("section", { class: "computer-remote", "aria-label": "Human step control" });
    var status = el("p", { class: "hint", role: "status", text: "Viewing mode." });
    var caption = el("p", { class: "hint", text: "Take control, then refresh the private preview before input." });
    var surface = el("select", { "aria-label": "Surface to control" });
    (state.human_sessions || []).forEach(function(s) { surface.appendChild(el("option", { value: s.surface, text: s.surface === "desktop" ? "Private desktop" : "Owned browser" })); });
    var take = el("button", { class: "btn primary", type: "button", text: "Take control" });
    var capture = el("button", { class: "btn", type: "button", text: "Refresh human frame", disabled: true });
    var pause = el("button", { class: "btn", type: "button", text: "Pause control", disabled: true });
    var resume = el("button", { class: "btn", type: "button", text: "Hand back to Hutch", disabled: true });
    var preview = el("button", { class: "computer-human-preview", type: "button", disabled: true,
      "aria-label": "Human preview. Click or touch to send a left click only in control mode." });
    var img = el("img", { alt: "Private human frame; never sent to the AI", class: "computer-human-img" });
    preview.appendChild(img);
    var text = el("textarea", { rows: 2, maxLength: 2000, placeholder: "Text for the focused control", "aria-label": "Text to type in the controlled app", autocomplete: "off" });
    var send = el("button", { class: "btn", type: "button", text: "Type in focused control", disabled: true });
    var keys = el("select", { "aria-label": "Key to send" });
    ["enter", "escape", "tab", "backspace", "ctrl+a", "ctrl+s", "ctrl+o"].forEach(function(key) { keys.appendChild(el("option", { value: key, text: key })); });
    var keySend = el("button", { class: "btn", type: "button", text: "Send key", disabled: true });
    pane.append(surface, el("div", { class: "computer-control-bar" }, [status, el("button", { class: "btn danger", type: "button", "data-stop-run": runId, text: "Stop run" })]), el("div", { class: "computer-actions" }, [take, capture, pause, resume]), preview, caption,
      el("label", { text: "Human text entry" }, [text]), el("div", { class: "computer-actions" }, [send, keys, keySend]),
      el("p", { class: "hint", text: "Scroll outside the preview to move this page. Each touch sends one click; drag, clipboard and held keys are unavailable. Enter can submit a form: check the focused control first. No text is saved in Hutch's run history." }));
    root.querySelector("[data-computer-panel]").appendChild(pane);

    function buttons() {
      var controlling = !!token && !closed;
      take.textContent = controlling ? "In control" : "Take control";
      take.disabled = controlling || busy; surface.disabled = controlling || busy;
      [capture, pause, resume].forEach(function(b) { b.disabled = !controlling || busy; });
      var fresh = frame && Date.now() - Date.parse(frame.captured_at) < 10000;
      [preview, send, keySend].forEach(function(b) { b.disabled = !controlling || busy || !fresh; });
      preview.classList.toggle("is-controlling", controlling);
    }
    function forget() {
      epoch++;
      token = ""; frame = null; text.value = ""; clearInterval(heartbeat);
      if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = ""; img.removeAttribute("src"); buttons();
    }
    async function command(action, detail) {
      if (busy || closed || (!token && action !== "takeover")) return;
      busy = true; buttons();
      var requestEpoch = epoch;
      try {
        var body = Object.assign({ action: action, surface: surface.value, viewer: viewer,
          control_token: token, generation: generation || undefined }, detail || {});
        if (["capture", "click", "type", "key"].indexOf(action) >= 0) { body.sequence = ++sequence; body.frame_id = frame && frame.frame_id || ""; }
        var answer = await api(prefix + "/control", { method: "POST", body: body });
        if (closed || document.hidden || requestEpoch !== epoch) {
          if (answer.control_token) api(prefix + "/control", { method: "POST", body: { action: "pause", surface: body.surface,
            viewer: viewer, control_token: answer.control_token, generation: answer.generation } }).catch(function() {});
          return;
        }
        if (action === "takeover") {
          token = answer.control_token; generation = answer.generation; sequence = 0;
          status.textContent = "You are in control.";
          root.querySelectorAll("[data-human-resume]").forEach(function(button) { button.remove(); });
          heartbeat = setInterval(async function() {
            if (!token || document.hidden || closed) return;
            try { await api(prefix + "/control", { method: "POST", body: { action: "heartbeat", surface: surface.value, viewer: viewer, control_token: token, generation: generation } }); }
            catch (error) { forget(); status.textContent = "Control connection was lost. The host will pause; take control again explicitly."; }
          }, 4000);
        } else if (action === "pause" || action === "resume") {
          forget(); status.textContent = action === "pause" ? "Control paused. Take control again to continue." : "Control handed back. Hutch must observe fresh state.";
        } else if (answer.frame && answer.frame.frame_id) {
          frame = answer.frame;
          var query = new URLSearchParams({ surface: surface.value, viewer: viewer, generation: String(generation), frame_id: frame.frame_id });
          var response = await fetch("/api" + prefix + "/human-frame?" + query, { credentials: "same-origin", headers: { "X-Hutch-Control": token } });
          if (!response.ok) throw new Error("Human frame unavailable. Refresh before further input.");
          var blob = await response.blob(), oldUrl = objectUrl;
          objectUrl = URL.createObjectURL(blob); img.src = objectUrl;
          if (oldUrl) URL.revokeObjectURL(oldUrl);
          status.textContent = "You are in control.";
          caption.textContent = "Last captured " + frame.captured_at + ". One step at a time; inspect its effect.";
          if (action === "type") text.value = "";
        }
      } catch (error) {
        frame = null;
        if ([401, 403, 409, 410].indexOf(error.status) >= 0) {
          if (token) api(prefix + "/control", { method: "POST", body: { action: "pause", surface: surface.value,
            viewer: viewer, control_token: token, generation: generation } }).catch(function() {});
          forget();
        }
        status.textContent = error.message + " No input is retried automatically. Refresh and inspect before continuing.";
      } finally { busy = false; buttons(); }
    }
    take.addEventListener("click", function() { command("takeover"); });
    capture.addEventListener("click", function() { command("capture"); });
    pause.addEventListener("click", function() { command("pause"); });
    resume.addEventListener("click", function() { command("resume"); });
    send.addEventListener("click", function() { if (text.value) command("type", { text: text.value }); });
    keySend.addEventListener("click", function() { command("key", { keys: keys.value }); });
    preview.addEventListener("click", function(event) {
      if (!token || !frame || !img.complete || !img.naturalWidth || event.detail === 0) return;
      var box = img.getBoundingClientRect(); // the image's actual aspect ratio, excluding preview padding/letterboxing
      var x = (event.clientX - box.left) * frame.width / box.width, y = (event.clientY - box.top) * frame.height / box.height;
      if (x < 0 || y < 0 || x >= frame.width || y >= frame.height) { status.textContent = "Touch the captured image, inside its edges."; return; }
      command("click", { x: x, y: y });
    });
    function hidden(event) {
      if (document.hidden || event.type === "pagehide") {
        // A best-effort pause request plus the independent 15-second host lease, even if this browser suspends immediately.
        if (token) api(prefix + "/control", { method: "POST", body: { action: "pause", surface: surface.value, viewer: viewer, control_token: token, generation: generation } }).catch(function() {});
        forget(); status.textContent = "Backgrounding paused control. Take control again explicitly.";
      }
    }
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("pagehide", hidden);
    var freshness = setInterval(buttons, 1000);
    pane.addEventListener("focusin", function(event) {
      if (event.target === text || event.target === keys) event.target.scrollIntoView({ block: "center" });
    });
    var controls = { isControlling: function() { return !!token || busy; }, close: function() {
      if (token) api(prefix + "/control", { method: "POST", body: { action: "pause", surface: surface.value, viewer: viewer, control_token: token, generation: generation } }).catch(function() {});
      closed = true; forget(); document.removeEventListener("visibilitychange", hidden);
      clearInterval(freshness); window.removeEventListener("pagehide", hidden);
      if (CONTROLS.get(runId) === controls) CONTROLS.delete(runId);
    } };
    CONTROLS.set(runId, controls);
    return controls;
  }

  window.HutchComputer = { mount: mount, render: render,
    hasControl: function(runId) { var controller = CONTROLS.get(runId); return !!controller && controller.isControlling(); } };
})();
