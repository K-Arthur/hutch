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

## 4. Capability / gap matrix

State words: **verified** (exercised in a real process), **implemented** (code exists, only fakes/unit tests), **gap**, **unsupported**.

| Capability | Browser | Native desktop (this host) | Notes |
| --- | --- | --- | --- |
| Isolated profile per bot, exclusive write ownership | verified (existing tests) | n/a | OS file leases; instance-owned contexts |
| Driver slot not held while waiting on a person | **verified** (this work) | n/a | `_DriverSlot`; limit `HUTCH_BROWSER_MAX_ACTIVE` (default 1) |
| Target identity (no first-match guessing) | **verified** | gap | exact label first; refuse 0/>1 |
| Tab identity / popups | **verified** | n/a | `t1…` ids, popup follows with notice, `tabs` action |
| Approved local development origins | **verified** | n/a | per-bot, `http` loopback only; proxy-enforced context |
| Observation envelope + frame ids + freshness | gap | gap | not started |
| Image delivery to model (per provider adapter) | gap | gap | no image path exists in `src/`; `compat.json` says not exposed |
| Coordinate contract / transforms | gap | gap | no coordinate actions exist in the tool yet |
| Verified action outcomes (dispatched vs effect-verified) | partial | gap | receipts exist (ADR-0003); no postcondition checks |
| Human takeover with a viewable surface | partial (local desktop opt-in only) | gap | no phone/remote surface |
| Control ownership with generation fence | gap | gap | run status only |
| Emergency stop independent of the model | partial | gap | bounded by call timeouts; driver not killable |
| Wayland capture / input / a11y readiness probes | n/a | gap | host has the pieces; nothing probes them |
| Observation (data egress) consent | gap | gap | `read`/`screenshot` are not gated; hosted-provider policy not applied to page text |
| Terminal/file/clipboard transfer grants | existing tools only | gap | |

## 5. Authority and session diagram (target design; only the first column exists today)

```
 person ──approves/grants──▶ Bot settings (tools, local_browser_handoff, local_dev_origins, approval_mode)
                                   │ (configuration version)
                                   ▼
 run ──▶ ApprovalGate (deny ▸ policy ▸ sticky ▸ ask)      ◀── hard deny always first; outward actions never sticky
   │          │ binds action_hash to args + target fingerprint
   ▼          ▼
 BrowserTool session (instance-owned context, profile lease, tab registry)   [implemented]
   │   driver slot (bounded) — released while waiting on a person              [implemented]
   │   egress proxy (every hop) + route guard (page-aware) + LocalAccess       [implemented]
   ▼
 ComputerSession (control owner + generation, observation envelope, frames)    [planned]
   ├─ browser driver (Playwright)   semantic first, coordinates only for canvases
   └─ desktop driver (portal/EIS, AT-SPI) in an isolated compositor            [planned]
```

## 6. Plan, budgets, risks, rollback

1. **Done here:** driver-slot scope, target identity, tab ownership, approved local development origins, egress-block reporting.
2. **Next:** observation envelope + bounded frame store + image delivery through the provider adapters (new module for the
   conversion logic so that the provider files only gain small hooks, because those files are being edited concurrently);
   control-ownership state with a generation fence; kill-able driver process for emergency stop; capability probes (doctor).
3. **Then:** isolated `kwin_wayland --virtual` environment for the native slice; computer-session panel in the run view.
4. **Budgets (to be measured, not asserted):** frame ≤ 600 KB and ≤ 1280 px long edge by default; at most the latest frame in
   model context; stop-to-quiescent target ≤ 2 s for a hung navigation; no unbounded retention of frames.
5. **Rollback:** every change is additive. `local_dev_origins` defaults to empty (behaviour unchanged); removing the field
   from a stored bot doc is safe. The driver-slot limit defaults to the previous behaviour (one active driver call per process).
   Rolling back never re-enables a known unsafe path because the previous unsafe path (global lock held across waits) only
   *reduced* concurrency; no authority is widened by this slice.
6. **Known residual risks:** an approved local origin is reachable from approved local pages by design (a local app can still
   call itself); `http://localhost` approval is per bot, not per run; Playwright redirect behaviour was measured on one build.

## 7. Implemented / verified / not run

- **Verified in a real browser:** duplicate-label refusal with candidates; scoped selector click with CDP review; type-then-click
  on a button enabled by typing; popup becomes the active tab and the original stays addressable; public page cannot load
  sub-resources from an approved local origin; public redirect into it is refused and reported as blocked; unapproved loopback
  port refused; approved local app and public names both reachable.
- **Verified by deterministic tests:** driver slot released during approval and human waits; local-origin validation and
  request-context matrix.
- **Not run / not implemented:** everything in the "gap" rows above, including all native-desktop work, image delivery, phone
  supervision, and the long-run resource soak.
