# Supervised computer use: baseline, evidence ledger and gap matrix (2026-10-10)

Status: working record for the computer-use effort. Everything below is either **observed in this checkout / on this host**,
**fetched from a named source on 2026-10-10**, or explicitly marked *not reproduced* / *not fetched*.

## 1. Environment and repository state

| Item | Value |
| --- | --- |
| Base commit | `a2106ec` (`main`; remote `origin/main` is `8d71f8a`, local is 449 commits ahead) |
| Authorized branch | The brief names `master`. **No `master` exists locally or on the remote** (only `main`). No branch was created or renamed. |
| Working method | Detached-HEAD worktree `.worktrees/computer-use` at `a2106ec`; the shared checkout was never switched or written. |
| Concurrent work seen | `skills-lifecycle` worktree: uncommitted edits to `runtime/builtin.py` (`_system_prompt`), `tools/base.py` (`ToolContext.skills`), new `tools/skill.py`. Main checkout: uncommitted provider/connection/server/static edits. Main moved `f2b8b00 → a2106ec` during the session. |
| Python / Playwright | CPython 3.13.15, Playwright 1.63.0, Chrome for Testing 153.0.8010.12 (`chromium-1243`) |
| Host session | Linux 7.2.7 (CachyOS), KDE Plasma **Wayland** (`XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0`) with XWayland (`DISPLAY=:0`) |
| Host services present | `xdg-desktop-portal` + `-kde` + `-gtk` backends, PipeWire/WirePlumber, AT-SPI registry, `kwin_wayland`, `libei`/`libeis`, `libatspi`, `spectacle`, `wl-copy`, `gst-launch-1.0` |
| Host services absent | `grim`, `wtype`, `ydotool`, `xdotool`; no `gi` in the project venv (system Python has Atspi) |
| Resources | 8 CPUs, 22 GiB RAM with ~4.6 GiB available at probe time |

The host desktop is the user's personal session. **No test in this work drives it.** Native-desktop tests need an isolated
compositor (see section 6).

## 2. Source-lead revalidation (the brief's leads against this checkout)

| Lead | Finding in `a2106ec` |
| --- | --- |
| Class-level `_pw`/`_browser` shared across bots | **Already fixed.** State is instance-owned (`BrowserTool.__init__`), profile leases are OS file locks, and `tests/test_browser_profiles.py` covers distinct profiles and lease conflicts. |
| Global lock covers calls, not interactions; held while waiting | **Confirmed and fixed here.** `run()` held `_GLOBAL_BROWSER_LOCK` across `gate.decide()` and `wait_for_human()`, so one bot's pending approval or login wait froze every other bot's browser for up to the TTL. Reproduced by `test_a_pending_approval_does_not_block…` and `test_a_human_wait_does_not_block…` (both red on base). Earlier record: `docs/realignment/baseline.md` row 8. |
| Login detection only logs | **Partly rejected.** `wait_for_human` parks the run in `waiting_human` with a Resume. But `ToolContext.headless` defaults to true, and without the opt-in `local_browser_handoff` there is no human surface (the tool says so). **Gap:** there is no remote/phone viewable takeover path. |
| First page / `.first` | **Confirmed and fixed here.** `pages[0]` and `locator.first` silently chose a tab/element. Now: explicit tab ids with popup following, and zero/multiple matches are refused with a bounded candidate list. |
| Screenshot returns a filename | **Confirmed, not yet fixed.** No code path in `src/` carries image bytes to a model (only a `"vision"` field in `compat.json` that says "not exposed"). |
| Hard-deny precedence | **Holds** in `ApprovalGate.decide`: deny is evaluated before sticky/auto. `click`/`type` are `outward=True`, so `browser:*` sticky grants never apply to them. `read`, `wait`, `screenshot`, and `goto` to a public URL are not individually gated (observation consent is a gap, see matrix). |
| Cancellation/deadlines | **Partly.** Playwright calls carry 10–30 s timeouts; no cancel hook closes the browser, and the Playwright driver processes are not in `ctx.procs`. Stop latency during a hung call is bounded by the call timeout, *not measured* here. |

## 3. Evidence ledger

`Reported` is what the source says; `Confirmed` is what was reproduced against Hutch here.

| # | Source / date | Version / platform | Reported | Confirmed against Hutch | Fix status | Design response | Regression test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | browser-use #4518 (opened and closed by reporter 2026-03-25) | 0.12.5, macOS | `multi_act()` caches the selector map; typing enables a disabled submit button; the batched click lands on the neighbouring button | Not applicable as a bug: Hutch has no cached batch executor; each action resolves against the live DOM | None referenced | Keep one resolution per action; no type+click batches | `test_a_button_enabled_only_after_typing_is_resolved_against_the_live_dom` (real Chromium) |
| 2 | browser-use #2862 (opened 2025-08-29, closed 2026-01-26) | ≤0.7.0 | Agent fills a neighbouring text box when the intended field is not found | Analogous defect existed (`.first`, substring label match) | Closed; no fix/PR shown on the page | Refuse 0 or >1 matches; exact-before-substring; list candidates | `test_ambiguous_selector_is_refused…`, `test_missing_target…`, `test_exact_label_match_wins…`, `test_duplicate_labels_are_refused…` |
| 3 | browser-use #1157 | n/a | repeated no-progress actions | **Not fetched** this session | n/a | Existing `LoopDetector` in `runtime/builtin.py` covers identical repeats; no-progress detection beyond that is open work | n/a |
| 4 | cua #2105 (opened 2026-07-03) | 0.7.0, GNOME/Wayland | Capture works but no input backend; clicks silently undelivered | Not reproduced (no cua install) | Open; a maintainer says portal input has shipped since 0.11.0 and asked for a retest on 0.30.4; no reply shown | Probe input independently of capture; never infer input from capture/`DISPLAY` | doctor probes (planned) |
| 5 | cua #2962 (opened 2026-08-07, closed 2026-08-16 via PR #3200) | 0.19.0, Hyprland + XWayland | Off-workspace window returns current-workspace pixels as that window | Not reproduced | Closed; page does not show what #3200 changed | Observation envelope must carry identity status, with explicit `surface_identity_unproven` | planned with native adapter |
| 6 | cua #2259 (opened 2026-07-16, closed 2026-09-29) | 0.8.3, KDE Wayland | One click allocated ~600–700 MB/s (RSS ~55 MB → ~5 GB in 5 s); `effect: unverifiable` | Not reproduced. Relevant: this host is KDE Wayland | Closed; reporter saw it resolved on a newer release (PR #3336 cited, 0.23.0) | Native driver runs as a supervised worker with an RSS/time watchdog | planned with native adapter |
| 7 | claude-quickstarts #254 (opened 2025-04-02) | demo loop, 1280×900 | `request_too_large` (413) after ~10 min; ran at 1024×768 | Cause **unconfirmed** on the page; plausible given unbounded image history | Open | Bound frame size and keep only the latest frames in model context | image-delivery tests (planned) |
| 8 | pyautogui #413 | n/a | mixed-monitor coordinate scaling | **Not fetched** this session | n/a | One coordinate contract with recorded transforms | planned |

### Official mechanisms (fetched 2026-10-10)

- **Playwright Python library page:** "Playwright's API is not thread-safe"; use one Playwright instance per thread. The page
  does not say whether an object may migrate threads, so Hutch treats that as unsupported. Design: the session owns its
  driver on the thread that created it.
- **Anthropic computer use:** current toolset is `computer_toolset_20260801` (GA, no beta header, 17 member tools). Screenshots
  return as an `image` content block inside `tool_result` (base64 `source`). Newer models accept up to **2576 px** on the long
  edge and 4784 visual tokens; the API does **not** downscale and rejects oversize images; more than 20 images tightens the
  per-side limit to 2000 px. Coordinates are in the pixel space of the images returned. Security guidance: dedicated
  VM/container, no credentials, domain allowlist, human confirmation for consequential actions, classifiers do not replace
  these. The last ~18 k characters of that page were not read.
- **XDG RemoteDesktop portal:** `CreateSession → SelectDevices → Start` (consent dialog) ; EIS (`ConnectToEIS`, since v2) is the
  recommended input path and the `Notify*` methods error once EIS is connected; `persist_mode` 0/1/2 and a **single-use**
  `restore_token`; if EIS disconnects the session should be closed. The fetched page did not describe revocation signalling.
- **XDG ScreenCast portal:** `types` bitmask (monitor 1, window 2, virtual 4); `restore_token` single-use; streams carry
  `position`/`size`/`source_type`/`mapping_id`; since v6 `pipewire-serial` supersedes node ids. No input restriction for window
  capture is documented, so **window-scoped capture must not be presented as input scoping**.

### Behaviours measured in this session (Playwright 1.63.0, Chrome for Testing 153.0.8010.12)

1. **Route handlers are not invoked for redirect hops.** A page-level `route("**/*")` saw the first request only; the redirected
   request reached its destination unrouted. Only the egress proxy observes every hop.
2. **A redirect hop of a browser-initiated navigation keeps `Sec-Fetch-Site: none` and no Referer**, so it is indistinguishable
   from the tool's own `goto` by request headers. Sub-resources and link clicks carry a Referer and `same-site`/`cross-site`.
3. **A popup's first navigation request has no `request.frame`** (Playwright raises). A rule that needs the frame must treat
   that as "new top-level navigation", not as an error that fails the page.
4. `--unsafely-treat-insecure-origin-as-secure` had **no effect** in this build (headless persistent context); `localhost` is a
   secure context. The in-page form review needs `crypto.subtle`, so plain-HTTP non-localhost forms are refused (by design).
5. **KWin ties an EIS context to the requesting D-Bus peer.** The first input worker let its D-Bus connection be garbage
   collected after obtaining the socket; libei then logged `failed to send message: Broken pipe` and no device ever appeared,
   nondeterministically. Keeping the connection alive for the socket's lifetime (and calling `disconnect(cookie)` on exit) made
   it deterministic. This is the same failure mode as cua #2105 ("sessions ending when the creating D-Bus connection exits").
6. `connectToEIS` on KWin 6.7.5 returned the keyboard device only after the pointer device resumed; a worker that reports
   "ready" on the first resumed device has no keyboard yet. The worker therefore waits for every capability the caller needs.
7. **An application's first screen is not the one a script assumes.** KWrite started without a file shows a Welcome page; a
   scripted click/type landed on its recent-documents list. Every action therefore returns a fresh frame and is refused
   against an older one.
8. **A unique isolated-world name per reviewed click leaked a JS context each time** (about 0.5 MB per click, measured by a
   per-process RSS split in the soak). A stable name makes Chromium reuse the world.
9. Desktop capture through KWin (spectacle) costs about 600 ms per frame on the reference host; input dispatch is sub-
   millisecond, so a dispatched input is never evidence of an effect.

## 4. Capability / gap matrix (final state of this work)

State words: **verified** (exercised in a real process), **protocol-verified** (wire-level fake, no live model),
**implemented** (unit tests only), **gap**, **unsupported**, **blocked** (cannot be exercised on this host).

| Capability | Browser | Native desktop (KDE Wayland, isolated KWin) | Notes |
| --- | --- | --- | --- |
| Exclusive per-bot profile / session ownership | verified | verified (own bus, display, input) | OS file lease; instance-owned contexts |
| Driver not held while waiting on a person | **verified** | n/a | `_DriverSlot` |
| Target identity (no first-match guessing) | **verified** | frame-bound coordinates | exact label first; refuse 0/>1 |
| Tab identity / popups | **verified** | n/a | `t1…`, popup follows with notice |
| Approved local development origins | **verified** | n/a | http loopback only; proxy-enforced; dashboard refused |
| Observation record + frame ids + freshness | **verified** | **verified** | bounded, hash-verified, evicting |
| Image delivery to a model | protocol-verified (Anthropic, Ollama-vision) | protocol-verified | no live hosted call; **blocked**: no local multimodal runtime on host |
| Hosted-route image consent | **verified** (wire test) | same | `observation_to_hosted`, default off |
| Coordinate contract | verified (CSS-px frame, stale/scroll/OOB refused) | verified (screen px, stale/OOB refused) | no crop/zoom transform exists yet |
| Verified outcomes | partial: nav origin + field read-back | visual-change only; file verified in the scenario | `dispatched` is never reported as an effect |
| Control ownership with generation fence | **verified** | **verified** | `ControlLease`; `computer_control` run events |
| Emergency stop independent of the model | **verified** (1.1–1.3 s) | **verified** (0.06 s) | hung-call and whole-desktop kill |
| Stop while other bot waits / out-of-order finish | verified | n/a | two profiles, one parked in approval |
| Readiness probes (session, portal, ScreenCast/RemoteDesktop versions, PipeWire, libei, AT-SPI, clipboard, compositor) | n/a | **verified** read-only on host; unit-tested branches | consent-gated parts report `needs_consent` |
| Portal consent flow capture/input on a personal desktop | n/a | **gap / not exercised** | never driven in tests |
| Accessibility (AT-SPI) semantic targeting | DOM semantics instead | **gap** | bus present; bindings absent in the venv; worker pattern is ready for it |
| Human takeover, local visible browser | **verified** in a disposable Wayland session: genuine pause, person's input via real EIS, no frame captured during the pause, secret absent from every record, owner human→agent with a new generation | n/a | `tests/e2e/test_computer_handoff_native.py`; not a phone, not a personal desktop |
| Human takeover, remote/phone *control* | **gap** | **gap** | panel is supervision only and says so |
| Computer-session panel (360/768/1440) | verified with screenshots | same panel | static/computer.js |
| Terminal PTY, clipboard and file-transfer grants | **gap** | **gap** | tool launches only allowlisted apps and workspace files |
| Strict offline for the computer tool | **gap** | **gap** | not verified; do not rely on it |
| Page-text egress consent for hosted routes | **gap** | n/a | text rides the route approval |
| macOS / Windows / GNOME / X11-only | unsupported | unsupported | not assessed beyond reading platform docs |

## 5. Authority and session diagram (as built)

```
 person ─ enables ─▶ Bot settings (tools, computer_apps, local_dev_origins, observation_to_hosted, approval_mode)
 run ──▶ ApprovalGate (deny ▸ policy ▸ sticky ▸ ask)      hard deny first; outward actions never sticky
   │
   ├─ BrowserTool  per-bot profile lease · driver slot (released while waiting) · tab registry
   │      egress proxy (every hop) + route guard + LocalAccess permit · ControlLease · FrameStore
   │      emergency stop = end driver tree from the supervisor thread
   └─ ComputerTool one session approval · ManagedDesktop (kwin --virtual, own bus, workspace cwd)
          DesktopSession(ControlLease, FrameStore, typed commands) ─ EIS worker (separate, killable process)
          capture: KWin ScreenShot2 via spectacle         input: EIS (libei) keycodes / absolute pointer
 events: tool_result.frames (public refs) · log kind=computer_control · human_needed/resumed
 UI: GET /api/v1/tasks/runs/{id}/computer · GET .../frames/{frame_id} (verified) · panel in the run view
```

## 6. Migrations, rollback and residual risks

* **No schema migration.** New fields (`local_dev_origins`, `computer_apps`, `observation_to_hosted`) live in the bot's JSON
  document with empty/false defaults; older documents load unchanged. New events are `log`/`tool_result` data keys.
* **Rollback.** Reverting the commits removes the tool, panel and routes. Stored bots keep the unknown fields harmlessly
  (extra JSON keys). Nothing here widens authority that a rollback could re-open: every new capability is off until a Bot opts in.
* **Residual risks (not mitigated):** isolated desktop apps share the host network/filesystem; frames are not redacted;
  hosted-route page *text* is not separately consented; the keyboard layout is assumed US; capture is KDE-specific
  (spectacle/KWin), the portal path is the portable one and is not implemented; Playwright redirect/popup semantics were
  measured on one build; the soak is 100 cycles, not hours.

## 7. Implemented / verified / not run

Commits on the detached worktree (no branch exists to land on; see the report):

| Commit | Content |
| --- | --- |
| `455fb73` | driver slot, target identity, tabs, local dev origins, frame store, baseline document |
| `00d6128` | `observe`, image delivery (Anthropic/Ollama), runtime choke point, public frame refs |
| `8502e07` | emergency stop (driver tree), owner-thread guard, procguard helpers |
| `a3034da` | control lease, `click_at`, verified outcomes |
| `f3cdad6` | `hutch computer doctor` + readiness API |
| `605c1e3` | native slice: ManagedDesktop, EIS worker, DesktopSession, `computer` tool, Bot settings, hosted-image consent |
| `4a24cd4` | state API, verified frame route, run-view panel, evidence screenshots |
| `643dd62` | isolated-world leak fix + soak |
| `b231a6f` | dashboard-origin refusal, cross-thread cleanup, isolation and untrusted-content tests |
| `fa14f4a` | documentation |
| `fefad08` | computer tool withheld in strict offline mode; baseline record finalized |
| `2cac434` | mixed terminal-to-desktop workflow test |
| `be923ba` | launch waits for the window to appear and settle |
| `98b9311` | human takeover of a visible browser verified in a disposable Wayland session |

* **Verified in real processes:** everything in section 4 marked verified.
* **Protocol-level only:** image delivery to Anthropic and Ollama; provider limits were taken from the documentation.
* **Blocked on this host:** a real local multimodal model; a physical phone; a second compositor (GNOME); live hosted models.
* **Not implemented:** remote control surface, portal consent flow, existing-desktop mode, AT-SPI targeting, PTY/clipboard/file
  transfer grants, macOS/Windows.
