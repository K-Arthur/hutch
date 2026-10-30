"""Playwright driver + in-page instrumentation for the dashboard live-update A/B.

No app source is touched. Instrumentation is injected with add_init_script before
navigation and wraps only browser primitives:

* window.fetch and Response.prototype.json -> request counts, timings, JSON cost;
* Element.prototype.innerHTML / insertAdjacentHTML -> synchronous DOM build cost
  (the app rebuilds the run detail with innerHTML, so this is rebuild cost);
* MutationObserver on the document -> mutation batch timestamps, plus rendering
  latency measured by counting a unique per-burst text token in #chat-stream (so
  the rendered-event check survives DOM markup changes in the candidate tree);
* window.EventSource -> stream opens and per-message type/change resources, so
  the run stream and the global changes stream are both visible;
* PerformanceObserver longtask/layout-shift (buffered);
* requestAnimationFrame timestamps for scroll frame gaps.

The app schema is not imported here on purpose: the driver works against any
tree that serves the studio, including the pre-change baseline.
"""

from __future__ import annotations

import secrets
import time

INIT_SCRIPT = r"""
(() => {
  if (window.__p) return;
  const now = () => performance.now();
  const streamEl = () => document.getElementById('chat-stream');
  const notes = () => document.querySelectorAll('#chat-stream .tool-note').length;
  const tokenCount = (token) => {
    const el = streamEl();
    if (!el || !token) return 0;
    const text = el.textContent || '';
    let count = 0, at = 0;
    while (true) {
      at = text.indexOf(token, at);
      if (at === -1) return count;
      count += 1;
      at += token.length;
    }
  };
  const push = (arr, item, limit) => { if (arr.length >= limit) arr.shift(); arr.push(item); };
  const p = window.__p = {
    startedAt: now(), fetches: [], jsonParses: [], innerHTMLSets: [], insertHTMLCalls: [],
    mutations: [], longtasks: [], shifts: [], bursts: [], frames: [], streams: [],
  };

  const origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    let url = '';
    try { url = typeof input === 'string' ? input : (input && input.url) || ''; } catch (e) { url = ''; }
    const rec = { url: url, start: now(), end: null, status: null, error: null };
    push(p.fetches, rec, 4000);
    return origFetch(input, init).then(
      (res) => { rec.end = now(); rec.status = res.status; return res; },
      (err) => { rec.end = now(); rec.error = String(err); throw err; });
  };

  const origJson = Response.prototype.json;
  Response.prototype.json = function () {
    const rec = { url: this.url, start: now(), end: null, ms: null, error: null };
    return origJson.call(this).then(
      (value) => { rec.end = now(); rec.ms = rec.end - rec.start; push(p.jsonParses, rec, 4000); return value; },
      (err) => { rec.end = now(); rec.ms = rec.end - rec.start; rec.error = String(err); push(p.jsonParses, rec, 4000); throw err; });
  };

  const htmlDesc = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  if (htmlDesc && htmlDesc.set && htmlDesc.get) {
    Object.defineProperty(Element.prototype, 'innerHTML', {
      configurable: true, enumerable: htmlDesc.enumerable, get: htmlDesc.get,
      set: function (value) {
        const t = now();
        htmlDesc.set.call(this, value);
        push(p.innerHTMLSets, { t: t, ms: now() - t, len: String(value == null ? '' : value).length,
          id: this.id || '', tag: this.tagName, cls: String(this.className || '').slice(0, 60) }, 4000);
      },
    });
  }
  const origIAH = Element.prototype.insertAdjacentHTML;
  Element.prototype.insertAdjacentHTML = function (position, text) {
    const t = now();
    const result = origIAH.call(this, position, text);
    push(p.insertHTMLCalls, { t: t, ms: now() - t, len: String(text == null ? '' : text).length,
      id: this.id || '', tag: this.tagName }, 4000);
    return result;
  };

  const OrigES = window.EventSource;
  const STREAM_EVENTS = ['message', 'batch', 'changes', 'refresh', 'hello', 'end',
                         'snapshot_required', 'auth_expired', 'events', 'phone-transcript'];
  if (OrigES) {
    window.EventSource = function (url, config) {
      const source = new OrigES(url, config);
      const rec = { url: String(url), start: now(), messages: [] };
      push(p.streams, rec, 40);
      const capture = (type) => (event) => {
        const summary = { t: now(), type: type, n: null, cursor: null, resources: null };
        try {
          if (typeof event.data === 'string' && event.data.length) {
            const data = JSON.parse(event.data);
            if (Array.isArray(data.changes)) {
              const resources = {};
              for (const change of data.changes) {
                const name = String(change.resource || 'unknown');
                resources[name] = (resources[name] || 0) + 1;
              }
              summary.resources = resources;
              summary.n = data.changes.length;
            }
            if (Array.isArray(data.events)) {
              summary.n = data.events.length;
              summary.first = data.first != null ? data.first : (data.events[0] || {}).seq;
              summary.last = data.last != null ? data.last : (data.events[data.events.length - 1] || {}).seq;
            }
            if (data.cursor != null) summary.cursor = data.cursor;
            if (data.status != null) summary.status = data.status;
          }
        } catch (e) { summary.parse_error = String(e); }
        push(rec.messages, summary, 300);
      };
      for (const type of STREAM_EVENTS) source.addEventListener(type, capture(type));
      return source;
    };
    window.EventSource.prototype = OrigES.prototype;
    window.EventSource.CONNECTING = OrigES.CONNECTING;
    window.EventSource.OPEN = OrigES.OPEN;
    window.EventSource.CLOSED = OrigES.CLOSED;
  }

  const checkBursts = () => {
    const t = now();
    for (let i = 0; i < p.bursts.length; i += 1) {
      const burst = p.bursts[i];
      if (burst.renderAt !== null) continue;
      if (tokenCount(burst.token) >= burst.expected) { burst.renderAt = t; }
    }
  };
  const observer = new MutationObserver((records) => {
    if (!records.length) return;
    push(p.mutations, { t: now(), n: records.length, notes: notes() }, 8000);
    checkBursts();
  });
  observer.observe(document, { childList: true, subtree: true });

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) push(p.longtasks, { start: entry.startTime, dur: entry.duration }, 4000);
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) { p.longtaskUnsupported = String(e); }
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) push(p.shifts, { t: entry.startTime, value: entry.value, recent: entry.hadRecentInput }, 4000);
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) { p.shiftUnsupported = String(e); }

  p.expectBurst = function (id, token, addCount, meta) {
    const burst = { id: id, token: token, at: now(), expected: addCount,
                    notesBefore: notes(), renderAt: null, notesAfter: null,
                    settledAt: null, meta: meta || null };
    p.bursts.push(burst);
    return { id: id, token: token, at: burst.at, expected: addCount };
  };
  p.awaitBurst = function (id, timeoutMs) {
    const burst = p.bursts.find((b) => b.id === id);
    const started = now();
    return new Promise((resolve) => {
      const finish = (timedOut) => {
        burst.settledAt = now();
        resolve({ id: id, token: burst.token, renderAt: burst.renderAt, settledAt: burst.settledAt,
                  rendered: tokenCount(burst.token), notesAfter: notes(), timedOut: timedOut });
      };
      const tick = () => {
        if (burst.renderAt !== null) {
          requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => finish(false), 0)));
          return;
        }
        if (now() - started > (timeoutMs || 10000)) { finish(true); return; }
        setTimeout(tick, 5);
      };
      tick();
    });
  };
  p.waitToken = function (token, expected, timeoutMs) {
    const started = now();
    return new Promise((resolve) => {
      const tick = () => {
        const count = tokenCount(token);
        if (count >= expected) { resolve({ ok: true, count: count, waited: now() - started }); return; }
        if (now() - started > (timeoutMs || 10000)) { resolve({ ok: false, count: count, waited: now() - started }); return; }
        setTimeout(tick, 10);
      };
      tick();
    });
  };
  p.waitQuiet = function (quietMs, timeoutMs) {
    const started = now();
    let lastFetches = p.fetches.length;
    let lastMutations = p.mutations.length;
    let lastBuilds = p.innerHTMLSets.length + p.insertHTMLCalls.length;
    let quietSince = now();
    return new Promise((resolve) => {
      const tick = () => {
        const activity = p.fetches.length !== lastFetches || p.mutations.length !== lastMutations
                      || (p.innerHTMLSets.length + p.insertHTMLCalls.length) !== lastBuilds;
        if (activity) {
          lastFetches = p.fetches.length;
          lastMutations = p.mutations.length;
          lastBuilds = p.innerHTMLSets.length + p.insertHTMLCalls.length;
          quietSince = now();
        }
        if (now() - quietSince >= quietMs) { resolve({ ok: true, waited: now() - started }); return; }
        if (now() - started > (timeoutMs || 5000)) { resolve({ ok: false, waited: now() - started }); return; }
        setTimeout(tick, 25);
      };
      tick();
    });
  };

  p.probe = function () {
    const t = now();
    const stream = streamEl();
    const height = stream ? stream.offsetHeight : 0;
    const scrollHeight = document.documentElement.scrollHeight;
    const forced = now() - t;
    return { forced_ms: forced, stream_height: height, scroll_height: scrollHeight,
             dom_nodes: document.getElementsByTagName('*').length,
             overflow: document.documentElement.scrollWidth - window.innerWidth,
             notes: notes(), has_stream: !!stream };
  };

  p.startFrames = function () {
    p.frames = [];
    p.frameOn = true;
    const loop = (ts) => {
      if (!p.frameOn) return;
      p.frames.push(ts);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    return true;
  };
  p.stopFrames = function () { p.frameOn = false; return p.frames; };

  p.snapshot = function () {
    const nav = (performance.getEntriesByType('navigation')[0] || null);
    return {
      notes: notes(),
      nav: nav ? { fetchStart: nav.fetchStart, responseEnd: nav.responseEnd,
                   domContentLoaded: nav.domContentLoadedEventEnd, load: nav.loadEventEnd,
                   duration: nav.duration } : null,
      fetches: p.fetches, jsonParses: p.jsonParses, innerHTMLSets: p.innerHTMLSets,
      insertHTMLCalls: p.insertHTMLCalls, mutations: p.mutations,
      longtasks: p.longtasks, shifts: p.shifts, bursts: p.bursts, frames: p.frames,
      streams: p.streams,
      longtaskUnsupported: p.longtaskUnsupported || null,
      shiftUnsupported: p.shiftUnsupported || null,
    };
  };
})();
"""

SCROLL_WHEEL_STEPS = 20
SCROLL_WHEEL_PX = 400
SCROLL_STEP_SECONDS = 0.016
INITIAL_QUIET_MS = 400
BURST_SETTLE_QUIET_MS = 250


def launch(playwright):
    """Launch the default headless Chromium and return (browser, metadata)."""
    browser = playwright.chromium.launch(headless=True)
    try:
        executable = playwright.chromium.executable_path
    except Exception:  # pragma: no cover - metadata only
        executable = ""
    return browser, {"engine": browser.browser_type.name, "version": browser.version,
                     "headless": True, "executable_path": executable}


def _new_token(prefix: str) -> str:
    return prefix + "-" + secrets.token_hex(5)


def measure_rep(browser, control, *, base_url: str, viewport: dict, rep_index: int,
                bursts: int, burst_size: int, seed_events: int,
                screenshot_path=None, timeout_ms: int = 30000,
                burst_timeout_ms: int = 12000) -> dict:
    """Open the live run detail in a cold context, push scripted bursts, return raw evidence.

    The control object must provide new_live_run(seed_events, token) and
    burst(run_id, count, label, token); both run inside the app process
    (see benchmarks.ui._serve).
    """
    seed_token = _new_token("uibseed" + str(rep_index))
    live = control.new_live_run(seed_events, seed_token)
    run_id = live["run_id"]
    context = browser.new_context(viewport=viewport, reduced_motion="reduce", device_scale_factor=1)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script(INIT_SCRIPT)
    measured = []
    try:
        started = time.monotonic()
        page.goto(base_url + "/#/run/" + run_id, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#chat-stream .run-stats", state="attached", timeout=timeout_ms)
        page.evaluate("(a) => window.__p.waitToken(a[0], a[1], a[2])",
                      [seed_token, seed_events, timeout_ms])
        page_load_ms = (time.monotonic() - started) * 1000.0
        page.wait_for_function(
            "(n) => document.querySelectorAll('#chat-stream .tool-note').length >= n",
            arg=seed_events, timeout=timeout_ms)
        page.evaluate("(a) => window.__p.waitQuiet(a[0], a[1])", [INITIAL_QUIET_MS, 5000])
        initial_probe = page.evaluate("window.__p.probe()")
        viewport_width = int(viewport.get("width", 0))
        viewport_height = int(viewport.get("height", 0))

        for index in range(bursts):
            token = _new_token("uibburst" + str(rep_index) + "-" + str(index))
            expected = page.evaluate("(a) => window.__p.expectBurst(a[0], a[1], a[2], a[3])",
                                     [index, token, burst_size, {"index": index, "rep": rep_index}])
            browser_before = float(page.evaluate("performance.now()"))
            python_before = time.monotonic()
            post = control.burst(run_id, burst_size,
                                 "rep" + str(rep_index) + "-burst" + str(index), token)
            python_after = time.monotonic()
            browser_after = float(page.evaluate("performance.now()"))
            offset_seconds = ((python_before + python_after) / 2.0
                              - (browser_before + browser_after) / 2000.0)
            browser_commit_ms = (float(post["commit_monotonic"]) - offset_seconds) * 1000.0
            scroll_phase = index == (bursts - 1)
            if scroll_phase:
                page.mouse.move(viewport_width / 2.0, viewport_height / 2.0)
                page.evaluate("window.__p.startFrames()")
                for _ in range(SCROLL_WHEEL_STEPS):
                    page.mouse.wheel(0, SCROLL_WHEEL_PX)
                    time.sleep(SCROLL_STEP_SECONDS)
            settled = page.evaluate("(a) => window.__p.awaitBurst(a[0], a[1])",
                                    [index, burst_timeout_ms])
            frames = page.evaluate("window.__p.stopFrames()") if scroll_phase else None
            time.sleep(0.12)  # trailing long-task/paint attribution
            quiet = page.evaluate("(a) => window.__p.waitQuiet(a[0], a[1])",
                                  [BURST_SETTLE_QUIET_MS, 5000])
            probe = page.evaluate("window.__p.probe()")
            measured.append({
                "index": index,
                "token": token,
                "expected_notes": expected["expected"],
                "notes_before": page.evaluate(
                    "document.querySelectorAll('#chat-stream .tool-note').length"),
                "commit_monotonic": float(post["commit_monotonic"]),
                "browser_commit_ms": browser_commit_ms,
                "server_queue_ms": float(post.get("queue_ms", 0.0)),
                "server_flush_ms": float(post.get("flush_ms", 0.0)),
                "render_ms": (float(settled["renderAt"]) - browser_commit_ms
                              if settled.get("renderAt") is not None else None),
                "await": settled,
                "quiet": quiet,
                "quiet_end_ms": browser_commit_ms + (quiet.get("waited") or 0.0),
                "probe": probe,
                "scroll_phase": scroll_phase,
                "scroll_frames": frames,
            })

        if screenshot_path:
            page.screenshot(path=screenshot_path, animations="disabled")
        snapshot = page.evaluate("window.__p.snapshot()")
        final_probe = page.evaluate("window.__p.probe()")
        return {
            "run_id": run_id,
            "seed_events": seed_events,
            "seed_token": seed_token,
            "page_load_ms": round(page_load_ms, 3),
            "page_errors": errors,
            "initial_probe": initial_probe,
            "final_probe": final_probe,
            "bursts": measured,
            "snapshot": snapshot,
            "screenshot": screenshot_path,
        }
    finally:
        context.close()
