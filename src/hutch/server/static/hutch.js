/* hutch dashboard behaviour. Pages work without this file (plain forms, server-rendered);
   it adds live updates, countdowns and the resumable transcript stream. No framework, no build step. */
"use strict";

(function () {
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

  /* ---------------------------------------------------------- confirm forms */
  document.addEventListener("submit", (ev) => {
    const msg = ev.target.dataset && ev.target.dataset.confirm;
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });

  /* ------------------------------------------------------------- clocks */
  const pad = (n) => String(n).padStart(2, "0");
  function clock(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    return `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`;
  }
  function human(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    if (seconds < 90) return `${seconds}s`;
    if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h`;
  }
  function tick() {
    const now = Date.now();
    $$("[data-countdown-to]").forEach((el) => {
      const left = (new Date(el.dataset.countdownTo).getTime() - now) / 1000;
      const text = $(".cd-text", el);
      if (!text) return;
      if (left <= 0) { text.textContent = "expired - denied"; el.classList.add("expired"); }
      else { text.textContent = `denies in ${clock(left)}`; el.classList.remove("expired"); }
    });
    $$("[data-elapsed-since]").forEach((el) => {
      el.textContent = human((now - new Date(el.dataset.elapsedSince).getTime()) / 1000);
    });
    const meters = $("#meters[data-started]");
    if (meters) {
      const el = $("[data-elapsed]", meters);
      if (el) el.textContent = human((now - new Date(meters.dataset.started).getTime()) / 1000);
    }
  }
  tick();
  setInterval(tick, 1000);

  /* --------------------------------------------------- live partial refresh */
  let refreshTimer = null;
  function refreshLive() {
    if (!window.htmx) return;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      $$("[data-live]").forEach((el) => {
        const busy = el.matches(":focus-within") && el.querySelector("textarea, input[type=text]");
        if (busy) return;                       // never swap out a form someone is typing in
        window.htmx.ajax("GET", el.dataset.live, { target: el, swap: "innerHTML" }).then(() => {
          if (el.id === "approval-badge") el.classList.toggle("hidden", el.textContent.trim() === "0");
        });
      });
    }, 150);
  }
  window.hutchRefreshLive = refreshLive;

  const pill = $("#live-pill");
  function setPill(on) {
    if (!pill) return;
    pill.classList.toggle("off", !on);
    pill.textContent = on ? "live" : "reconnecting";
    pill.title = on ? "Live updates connected" : "Live updates lost - retrying. Pages still work; reload to refresh.";
  }
  if (window.EventSource && $$("[data-live]").length) {
    const es = new EventSource("/stream/live");
    es.addEventListener("hello", () => setPill(true));
    es.addEventListener("refresh", refreshLive);
    es.onerror = () => setPill(false);
    es.onopen = () => setPill(true);
  }

  /* --------------------------------------------- resumable transcript stream */
  const root = $("[data-run-stream]");
  if (root && window.EventSource) {
    const list = $("[data-events]", root);
    const state = $("#stream-state");
    const url = root.dataset.runStream;
    const gapUrl = root.dataset.gapUrl;
    let last = parseInt(root.dataset.lastSeq || "0", 10);
    let follow = true;
    const wasActive = root.dataset.active === "1";

    window.addEventListener("scroll", () => {
      follow = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160;
    }, { passive: true });

    const setState = (name, text) => {
      if (!state) return;
      state.dataset.state = name;
      const label = state.querySelector("span");
      if (label) label.textContent = text;
    };

    function append(html) {
      if (!html) return;
      list.insertAdjacentHTML("beforeend", html);
      if (window.htmx) window.htmx.process(list);
    }

    async function fillGap(from, to) {
      // Belt and braces: the server replays from the database, so gaps should not occur, but if a
      // batch ever arrives out of order we refetch the missing range rather than show a hole.
      let cursor = from;
      while (cursor < to) {
        const res = await fetch(`${gapUrl}?after=${cursor}&upto=${to}`, { credentials: "same-origin" });
        if (!res.ok) break;
        const html = await res.text();
        const seqs = [...html.matchAll(/data-seq="(\d+)"/g)].map((m) => parseInt(m[1], 10));
        if (!seqs.length) break;
        append(html);
        cursor = Math.max(...seqs);
      }
      return cursor;
    }

    const es = new EventSource(`${url}?after=${last}`);
    es.onopen = () => setState("live", "live - streaming this run");
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) setState("error", "stream closed - reload the page");
      else setState("reconnecting", "connection lost - reconnecting and resuming where it left off...");
    };
    es.addEventListener("batch", async (ev) => {
      const d = JSON.parse(ev.data);
      if (d.first > last + 1) await fillGap(last, d.first - 1);
      append(d.html);
      last = Math.max(last, d.last);
      const chip = $("#run-status");
      if (chip && d.status) { chip.textContent = d.status.replace(/_/g, " "); chip.className = `chip st-${d.status}`; }
      if (follow) window.scrollTo({ top: document.body.scrollHeight });
      refreshLive();
    });
    es.addEventListener("end", () => {
      es.close();
      setState("done", "run finished");
      if (wasActive) setTimeout(() => location.reload(), 350);
    });
  }
})();
