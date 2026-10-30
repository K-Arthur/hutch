# UI acceptance surface and frontend render-path audit (2026-10-29)

Read-only audit in the perf worktree. No source edit was made for this document. Sources are the
current tree plus the profiler baseline `benchmarks/results/hotpaths-2026-10-30.json` (quick mode,
20 bots / 2,000 events, host load average 6.45/9.86/13.58 on 8 threads). Absolute timings in that
baseline are noisy; use them as payload sizes and relative hints, not as targets.

Repository facts referenced below (file:line at the time of writing):
`src/hutch/server/pages.py`, `src/hutch/server/app.py`, `src/hutch/server/sse.py`,
`src/hutch/server/static/app.js`, `src/hutch/server/templates/_events.html`,
`tests/test_dashboard.py`, `tests/e2e/test_route_state_boundaries.py`, `docs/requirements.md`.

---

## (a) Route -> data -> render -> DOM, as it exists

| Surface | Route / trigger | Server source | Payload bound | Client consumer | DOM update |
|---|---|---|---|---|---|
| Studio shell + overview | `GET /` serves `static/index.html`; `#/overview` | `/api/overview` (`pages.py:205`, from `views.home_state`) + `/runs?limit=8` | needs/running/stale lists, 8 recent runs | `renderOverview` (`app.js:6937`) | `setTopContext(...)` + `view.innerHTML` replace |
| Roster / sidebar / `#/bots` | `GET /bots` -> `#/bots`; shell always mounts roster | `/api/bots` -> `store.roster_aggregates` (`store.py:9989`) | **all bots, no pagination** | `refreshRoster` (`app.js:2317`) -> `renderRoster` (`app.js:2339`) | `list.innerHTML = markup` for every row (`app.js:2334`); one string build over `botsCache` |
| Chat feed (studio home) | `#/chat`, `#/conversation/:id` | 6 requests per render: `/v1/conversations/:id?after=&limit=1`, then `?after=last_seq-100&limit=100`, `facts?limit=20`, `fact-shares?limit=20`, `workspace/tasks?limit=100`, `code-handoffs?limit=100` (`app.js:4744-4768`) | last **100 messages**; last **6 runs** (`runIds.slice(-6)`, `app.js:4806`) | `renderChatFeed` (`app.js:4732`) -> `runBlockHtml` per run (`app.js:5399`) | full `stream.innerHTML = nextHtml` rebuild of all 6 run blocks + fact panel (`app.js:4869-4871`); scroll anchor preserved (`app.js:4795-4805`, `4930`) |
| Run detail | `#/run/:id` | `GET /api/runs/:id` (`app.py:5211`) with `DEFAULT_EVENT_WINDOW = 200` (`app.py:101`); returns events + `approval_states` + `choice_states` + `event_count` + `events_truncated` | newest **200 events**, plus per-window approval/choice maps | `renderRunDetail` (`app.js:9316`) -> `runBlockHtml` | full `view.innerHTML` replace of the page (`app.js:9358`), stats computed by filtering `r.events` (`app.js:9348-9357`) |
| Run live stream | `EventSource /api/runs/:id/stream` (`app.js:4699`); alias `/api/v1/tasks/runs/:id/stream` (`app.py:5944`) | `run_event_stream` (`sse.py:63`) with `BATCH = 200` (`sse.py:29`), `COALESCE_SECONDS = 0.08` (`sse.py:30`), `Last-Event-ID` = per-run seq, replay from SQLite | one `batch` SSE message of <= 200 events; `render` = JSON `model_dump(exclude={"id"})` (`app.py:5951`) | `onmessage` -> `scheduleFeedRender()` (`app.js:4702`) = 250 ms debounce + single flight (`app.js:4712-4724`) | **not incremental**: each batch re-fetches `/api/runs/:id` (200 events) and rebuilds the whole page. Plus a 4 s belt-and-braces `statusTimer` refresh (`app.js:4709`) |
| Global change stream | `EventSource /api/v1/changes/stream?cursor=` (`app.js:13034`) | `resource_change_stream` (`sse.py:171`); gap -> `snapshot_required` -> `/api/v1/snapshot` | transactional invalidations, no event payloads | `refreshChangedResources` (`app.js:12998`), `reconcileResourceStream` (`app.js:13066`) | targeted refreshes (roster, badge, feed schedule) |
| Global event stream (durable) | `GET /api/v1/events/stream` (`app.py:2761-2762`) -> `global_event_stream` (`sse.py:117`) | SQLite global event id; gap -> `snapshot_required` | 200-event batches | phone/paired paths and any consumer of `/api/v1/events/stream` | phone uses `phoneRefresh` (`app.js:13344`) |
| Server-rendered fragments (retired surfaces) | `/runs/:id` -> 302 to `#/run/:id` (`pages.py:433`); `/runs/:id/events?before=` (`pages.py:438`) | `PAGE_WINDOW = 200` (`pages.py:33`), `render_events` (`pages.py:153`), `_events.html` macro (`_events.html:5`) | 200 events per fragment | htmx "Load earlier" (`_events.html:71-79`) | `hx-swap="outerHTML"` on `#tx-more`; **not used by the studio today** (route still tested) |

### What is actually bounded today

- Run detail API/DOM window: **200 events** (`DEFAULT_EVENT_WINDOW`), `events_truncated` tells the
  client older events exist; API clamp `limit <= 1000` (`app.py:5936`).
- Chat feed: **100 messages**, **6 runs**, tool output clipped at 600 chars with an explicit "Show
  N more characters" control (`OUTPUT_CLIP = 600`, `app.js:6377-6391`).
- SSE: <= **200 events per message**, one message per >=80 ms coalesce window; keepalive 15 s.
- Server HTML fragment path: **200 events** per "load earlier" page.
- Roster: **not paginated or virtualised**; every bot renders one row per `renderRoster`.

### Where 10k events still costs time (ranked by likelihood, to be measured)

1. **Rebuild amplification in run detail.** At 10k events the visible window is 200, so DOM size is
   bounded, but every SSE batch causes a new `/api/runs/:id` request (200 events + approval/choice
   maps) and a full-page `innerHTML` parse+layout. At a sustained 200-event/80 ms stream the debounce
   allows up to ~4 rebuilds/s; each rebuild is O(window + stats), not O(total). The cost to measure is
   **rebuild duration and long tasks per burst**, not total events.
2. **Chat feed rebuild cost scales with content, not event count.** Six runs are re-rendered as HTML
   via `runBlockHtml`; any run with large tool outputs or long markdown makes every burst rebuild
   expensive. The existing snapshot compare (`app.js:4870`) skips the DOM write when markup is
   identical, but the markup has already been built.
3. **Six sequential API calls per chat-feed render** (`4744-4770`) — latency compounds; each is a
   server DB round trip. This is the most likely user-visible cost on a busy host.
4. **Roster at 50 bots.** Baseline: `/api/bots` 35 KiB / ~27 ms at 20 bots (quick-mode, noisy host);
   linear extrapolation to ~85-90 KiB at 50 bots, rendered as one `innerHTML` string. Probably fine
   but it is the one surface that grows without a window.
5. **Server encode cost per batch:** `model_dump(exclude={"id"})` over <=200 events (the stream
   render does **not** include approval/choice states; those are only in the `/api/runs/:id` refetch),
   then `json.dumps` in `sse_message` (`sse.py:37-40`). This is the only place where a Rust/JSON kernel could show up in
   a browser-visible metric, and only if profiling proves it dominates a batch.
6. **Unbounded-growth risks observed:** none in the studio run/chat windows by design; the risk is
   *rate* (rebuilds per second) and *content size*, not total DOM nodes. The retired server page path
   is bounded but not used.

---

## (b) Acceptance surface for "dashboard usable at >=10k events" and ">=50 bots"

Current documented gate: `docs/requirements.md:119` PF-9 = "Coalesced live updates, paginated
transcripts | usable at 10,000 events | done | the run page renders the last 200 events and paginates;
a 10,000-event run is tested (`tests/test_dashboard.py`)".

That test is **server-only** and has no browser in it:
`test_ten_thousand_event_run_page_is_paginated_and_fast` (`tests/test_dashboard.py:211`) creates 10k
events, asserts `/runs/:id` 302s in < 1.5 s (the page is retired), that
`/runs/:id/events?before=9801` returns exactly 200 rows with `data-seq 9601..9800` and a further
"load earlier" control, and that `/api/runs/:id` returns 200 events + `event_count == 10000` +
`events_truncated`. **There is no client-side 10k-event, no long-task, no DOM-growth, and no 50-bot
assertion anywhere.** That is the gap this audit recommends closing.

Proposed acceptance surface (each row is one measurement the Playwright recipe in (d) can produce):

| ID | Surface | Scenario | Metric that must be reported | Honest threshold |
|---|---|---|---|---|
| U1 | Run detail, 10k-event completed run | open `#/run/:id`, wait for first paint | time to first transcript paint; long-task count/total during first 3 s; DOM node count | no regression vs baseline; absolute floor 1 ms / 5% |
| U2 | Run detail, live 10k-event stream | replay/stream 200-event batches at ~4/s for 10 s | per-burst rebuild duration p95 (MutationObserver timestamps), total blocking time, frame gaps while scrolling | candidate <= baseline (paired ratio); no burst > 200 ms |
| U3 | Chat feed, 100-message/6-run window | open `#/chat` during an active run | time from first paint to interactive; 6 sequential API timings; rebuild duration per burst | same |
| U4 | Overview + roster, 50 bots | `#/overview` then `#/bots`; also 50 bots with 10k events total | `/api/bots` bytes+ms, roster `innerHTML` duration, long tasks | same |
| U5 | SSE encode cost (server) | measure `run_event_stream` batch size/time in-process (profiler harness) | ms per batch, bytes per batch, events per batch | candidate <= baseline |
| U6 | Scroll and layout stability | 20 scripted scroll steps during a live burst | rAF frame-gap p95, LayoutShift entries, scrollHeight delta | no frame > 100 ms added |

---

## (c) Candidate improvements, ranked by expected user impact and risk (no implementation here)

| Rank | Change | Expected effect | Risk | Evidence needed |
|---|---|---|---|---|
| 1 | Append/update only new events in run detail instead of full-page `innerHTML` rebuild; keep the existing scroll anchor logic | Removes O(window) parse+layout per burst; largest win at high burst rate; keeps 200-event DOM cap | Medium: focus/disclosure/scroll state is already carefully handled (`app.js:4847-4931`); must preserve approvals and "show more" | U2 before/after; DOM node count unchanged; focus/aria checks |
| 2 | Apply SSE batch events directly (server already sends them) instead of re-fetching `/api/runs/:id` per batch | Removes one HTTP round trip + full 200-event JSON parse per burst | Medium: server payload lacks approval/choice maps per event; would need the maps in the batch or a cached authority | U2 + U5; server encode cost may move into the batch path |
| 3 | Coalesce the 6 chat-feed calls into one composite endpoint or add caching/ETag; skip unchanged sub-fetches | Cuts feed render latency on a busy host; most likely visible win without touching DOM | Medium: API surface change (ADR-style decision), parked `app.py` dirty risk | U3; request waterfall from Playwright |
| 4 | CSS containment on event rows (`contain: content`/`content-visibility: auto` on `.tx`, `details`, `pre`) | Bounds layout/paint work for offscreen 200-event window | Low: CSS only, visual validation needed | U2/U6 frame gaps and LayoutShift |
| 5 | Roster incremental rendering or virtualization at >=50 bots | Avoids rebuilding 50 rows on every change; small absolute cost | Low-medium: roster focus/menu handling is intricate (`app.js:2339-2400`) | U4 at 50 bots |
| 6 | Trim `/api/runs/:id` payload (drop heaviest per-event fields; lazy-load tool args/output) | Fewer bytes and cheaper JSON per first paint | Medium: contract/API shape; tests assert event fields | U1/U5 bytes + parse time |
| 7 | Server-side: precompute per-window approval/choice maps or add an index-backed batch query | Reduces batch encode latency | Low: `store.py` internal (parked-dirty risk) | U5 server timing |

Do not start with a Rust/JSON kernel: rows 1-3 are user-visible and are pure render/algorithm work.
Only rows 5 (U5) would ever justify a kernel, and only if profiling shows encoding dominating.

---

## (d) Playwright measurement recipe for honest before/after on this noisy host

Preconditions: isolated state (`HUTCH_HOME` per side), a seeded corpus at the target scale (reuse the
profiler's `benchmarks/hotpath_workloads/events.py` shape or `hutch init` + direct `store.append_event`
in a scratch tree — not the parked checkout), two server processes: baseline from a temporary
`git worktree` at the previous commit, candidate from the perf worktree, on fixed loopback ports.
Never compare against a number recorded yesterday.

Per repetition (Playwright Python sync API, mirroring `tests/e2e/test_route_state_boundaries.py`):

1. `browser.new_context(viewport=..., reduced_motion="reduce")` and a fresh context per rep so JS heap,
   cache, SSE connections and DOM are cold; wait for `#chat-stream`/`#chat-scroll`.
2. Collect navigation timing: `performance.getEntriesByType("navigation")[0]` fields
   `responseStart`, `domContentLoadedEventEnd`, `loadEventEnd`.
3. Install observers with `page.add_init_script` before navigation:
   `new PerformanceObserver(...).observe({type:"longtask", buffered:true})`,
   `{type:"layout-shift", buffered:true}`, and a `MutationObserver` on `#chat-stream` that records
   timestamps; set `window.__p = {longtasks:[], shifts:[], mutations:[]}`.
4. First-paint marks from the page itself: a MutationObserver records the first mutation with a
   transcript child and a 300 ms quiet window -> `feed-first-paint`, `feed-idle`. Report
   `feed-idle - navigationStart`.
5. Burst cost (U2): drive a live run with the existing deterministic mock provider/e2e fixture, or
   append events server-side at a controlled rate. For each burst, record
   `mutations[i+1].t - mutations[i].t` and the gap between the SSE message and the settled DOM;
   report median/p95 across >=20 bursts.
6. Layout/reflow proxies: `document.documentElement.scrollHeight`, `scrollHeight/clientHeight` of
   `#chat-scroll`, and a forced synchronous layout read (`el.offsetHeight`) timed with
   `performance.now()` immediately after a mutation; plus `layout-shift` value sum. DOM node count
   `document.getElementsByTagName("*").length` before/after burst proves bounded vs unbounded growth.
7. Scroll responsiveness (U6): 20 `mouse.wheel` steps of 400 px with 16 ms spacing; record rAF deltas
   via a script that logs `performance.now()` per frame; report median and p95 frame gap, count > 50 ms.
8. Server-side visibility: also record `performance.getEntriesByType("resource")` for
   `/api/runs/`, `/api/bots`, `/v1/conversations` (count, transferSize, duration) so a frontend win
   cannot hide a server regression.
9. Paired A/B discipline on this host: alternate baseline and candidate reps in one browser process
   (B/A/B/A..., 5 reps per side per viewport minimum); record `/proc/loadavg` before and after each
   rep and the git head of each side; compute per-rep ratio (candidate/baseline) and report the
   median ratio plus the full list, never a cross-day comparison. Discard a rep whose start/end load
   average exceeds a pre-registered ceiling (for example 12 on this 8-thread host), and re-run it.
10. Acceptance: a change is accepted only if the median paired ratio and at least 4 of 5 reps agree in
    direction, the effect exceeds the absolute floor (1 ms or 5% of the metric, whichever is larger),
    and no other row (U1-U6) regresses. Memory/DOM claims require node-count or heap evidence, not
    wall time.

Reference viewports and existing conventions: `VIEWPORTS = ((1440, 900), (900, 900), (360, 800))`
(`tests/e2e/test_route_state_boundaries.py:31`), plus the paired-phone 390x844 context used at
`tests/e2e/test_route_state_boundaries.py:316`. Capture screenshots with `animations="disabled"`
(as in `tests/e2e/test_composer.py:222`) for the visual gate.

---

## (e) Flows and visual/state checks required for any SSE/serialization-affecting change

| Flow | Why it is affected | States that must be checked |
|---|---|---|
| Studio chat during an active run | live SSE batch -> debounce -> full feed rebuild | loading (empty feed while run starts), progress (typing indicator, status chip), error (feed refresh error + Retry, stream lost/offline pill), steady streaming, long transcript (100-message cap) |
| Run detail live update | batch -> refetch -> whole-page rebuild; scroll anchoring | first paint, live bursts while scrolled up (Jump to latest appears), scrolled at bottom (follows), terminal transition, 10k-event truncated window, "Show more" tool output expansion, approval card inline |
| Overview / roster | change stream -> targeted refresh; 50-bot roster | loading, empty (no assistants), error (offline pill), 50 bots with search/filter, pinned/needs-you sections, badge updates |
| Approvals inline in transcript | stream events + full rebuild can collapse cards | pending, approved, denied, resolved-by-other, focused button retained after rebuild |
| Paired phone run detail (390x844) | separate polling + phone SSE (`phone-transcript`) | loading, empty, error, progress, truncated transcript notice |
| Reconnect / gap | `Last-Event-ID` resume, `snapshot_required`, `auth_expired` | server restart mid-run (resume without duplicates/lost events), expired session, network drop, duplicate prevention |

Visual validation for each affected flow: the three repo viewports (1440x900, 900x900, 360x800) plus
390x844 for the phone path; verified items = no horizontal overflow, no new layout shift after the
late-arriving transcript, focus not stolen while reading, no duplicate event rows after reconnect,
loading/empty/error/progress states present and announced (role=status / aria-live), screenshots
inspected before/after.

---

## Open items

- No browser run was performed (task is read-only, no browser needed); every claim above is a code
  reading plus the profiler baseline, not a UI measurement.
- The 10k/50-bot acceptance criteria in (b) are proposals; they are not yet recorded in
  `docs/requirements.md` or the programme's DoD.
- Server-side batch encode cost and `approval_states_for_events` query cost are unmeasured at 10k
  events; the profiler's `dashboard.*` cases are HTTP-level at 20 bots / 2k events only.
