# Supervised computer use

Hutch can operate a **browser tab** and a **native desktop application** for a run, under the same approval, audit and stop
machinery as every other tool. This page says what that does and does not give you. Evidence for each claim is in
[research/computer-use-review-2026-10-11.md](research/computer-use-review-2026-10-11.md) and its linked baseline; status words used here:

| Word | Meaning |
| --- | --- |
| **verified** | exercised in a real process on the stated platform (real Chromium, real KWin session) |
| **protocol-verified** | request/response bodies checked against a wire-level fake; no live model was called |
| **experimental** | implemented and tested, but narrow or host-dependent |
| **unsupported / not implemented** | refused or absent; never silently emulated |

## Supported today

| Surface | Environment | Status |
| --- | --- | --- |
| Browser (Playwright Chromium) | per-bot persistent profile, headless or visible local desktop | **verified** (Linux, Chromium 153) |
| Native desktop application | **isolated** disposable KWin Wayland session Hutch starts for the run | **verified** on KDE Plasma/KWin 6.7 Wayland (KWrite) |
| Native desktop application | the person's **existing** desktop | **not implemented** (would be weaker isolation and needs the portal consent flow) |
| Portal (ScreenCast/RemoteDesktop) capture and input | consent-gated | probed only (`hutch computer doctor`); **not exercised** |
| GNOME/Mutter, X11-only, macOS, Windows | | **unsupported / untested** |
| Authenticated human step control | owned browser / disposable KWin desktop | **verified locally** through HTTP and viewport emulation; physical phones and live remote networks **unverified** |

## How a session is bounded

```
person ─ enables ─▶ Bot settings (tools, computer_apps, local_dev_origins, observation_to_hosted, remote_computer_access)
run ──▶ ApprovalGate (hard deny ▸ policy ▸ sticky ▸ ask)         outward actions are never sticky
        │
        ├─ browser tool ── driver slot (released while waiting) ── egress proxy (every hop) + route guard + LocalAccess
        └─ computer tool ── one session approval ── ManagedDesktop (own display/input/bus)
                              DesktopSession: ControlLease (generation fence) · FrameStore · typed commands
                                              EIS input worker (separate process, killable)
```

* **One authority.** Browser and desktop actions go through the existing `ApprovalGate`, run events and action receipts.
  A denied action is never retried through a more powerful path.
* **Control ownership is separate from task status.** `agent / human / paused / stopping / stopped / recovery_required`,
  with a generation counter. An action captures a ticket and re-checks it immediately before dispatching, so a takeover or
  stop that races an approved action wins. Changes are recorded as `computer_control` run events and shown in the panel.
* **Observation is separate from action.** Frames are bounded, private, hash-verified artifacts (below); an action is only
  accepted against the latest frame and inside it. Coordinates are never clamped onto a different target.

## The isolated desktop: what it does and does not isolate

`ManagedDesktop` starts its own `kwin_wayland --virtual` compositor, its own D-Bus session bus (minimal config, nothing
auto-activated) and private runtime/HOME directories. Automated input cannot reach your desktop: it never uses your Wayland
socket, your EIS socket or your input devices (it does not use `uinput`, which is system-global).

Native applications additionally require the existing bubblewrap/systemd/prlimit containment backend: only the workspace,
a disposable app home, read-only system files and the private Wayland socket are mounted. Apps have their own PID/network
namespaces, no host network and no D-Bus broker, with CPU, memory, task, descriptor and file-size limits. File dialogs start
in the workspace and cannot reach other user files. Unavailable containment fails closed even when shell containment is off.
The compositor, capture and input worker remain trusted host processes; this is **not a VM** or a boundary against a hostile
compositor. Allow only installed applications you intend to use. Do not put credentials in the granted workspace.

Keyboard input is sent as evdev keycodes and typed for a **US layout** (printable ASCII); other characters are refused
rather than guessed. The driver reports dispatched input and visual change; confirm the intended effect in application state or a saved artifact.

## Resource grants, revocation and budgets

The session review grants the **whole clean workspace**, including newly created ordinary documents. Before native
observation or input, Hutch checks known policy-denied credential paths, links/devices, 10,000 entries, 16 directory levels
and a 128 MiB file total. A denied resource prevents GUI observation/input; choose a clean workspace. This is a path policy,
not a content classifier. The trusted local owner must not add private material concurrently. The OS namespace does not
turn an approved application's scripts or displayed text into trusted instructions.

Browser and native checks reread the saved Bot's tools, apps, local origins, observation consent, remote access, risk,
approval/command rules, inference mode and paused state. A changed grant requires a new run. Revalidation also happens
after review. Independent two-second watchdogs stop idle sessions on revocation, unavailable authority state, oversized
retained state or sampled process-tree RSS above 1.5 GiB. Browser profiles and native session directories have a sampled
128 MiB / 10,000-entry bound; Chromium caches are requested at 4 MiB. Profiles are retained for review, never silently erased.
These are **soft sampled limits**, with possible overshoot; summed RSS includes shared mappings. Native app launchers also
have the existing hard scope/prlimit controls and at most four simultaneous launchers per private session. The trusted
compositor is not hard memory-isolated. Scheduler/run capacity and browser driver-slot bounds still apply; raising capacity
raises aggregate resource use. Disk-backed temporary storage avoids consuming an already-full tmpfs.

Native capture has a 15-second deadline and keeps only an accepted bounded PNG; failed/oversized capture files are removed.
Stop fences capture registration and kills owned capture processes too. Shared browser/native frame stores serialize their
quota and frame IDs across instances. Upload review allows one selected file across the whole form, before allocating its
hash buffer. Managed downloads retain at most eight files / 16 MB per browser run, within the shared artifact limit.
Clipboard, drag/held input and authenticated PTY transfer are unsupported. Strict Offline excludes browser/computer tools;
its governed file/shell loop uses the configured loopback model broker in a network-isolated worker. OpenCode/Pi Bot
executors still refuse before process creation until equivalent authority can be enforced.

## Observation and images

`browser observe` and `computer observe` return a bounded observation record (surface and tab ids, frame id, capture time,
viewport/screen size, transform `scale 1.0 / crop none`, freshness status, and, for the browser, a value-free list of visible
interactive elements) and one image frame.

* Frames live in `<run dir>/frames` (directory 0700, files 0400), at most 900 KB and 2000 px on the long edge each, at most
  64 frames / 8 MiB per run (oldest are evicted). Bytes are re-read and SHA-256 verified on every use. Nothing records the
  screen continuously; there is no video.
* Only the **newest** frame is sent to a model, converted to the route's real image format at the provider boundary.
  Older frames become text notes. Image bytes are never stored in the transcript or in message history.
* Image-capable routes: documented exact OpenAI image models at the official endpoint, Anthropic `claude-*` models,
  and Ollama models whose `/api/show` capabilities include `vision`
  (**protocol-verified**: no live hosted call and no local multimodal model was available on the test host). Every other
  route (including custom "OpenAI-compatible" endpoints and Sign in with ChatGPT) is **semantic-only** with an explicit note; "OpenAI-
  compatible" does not establish image support.
* **Egress consent.** Sending page text, labels or images to a *hosted* route is data egress even though execution is local, so it
  needs the Bot owner's explicit `observation_to_hosted` setting (default off). Loopback model routes are unaffected.
  Without consent the tool's observation text is also withheld. Once private observations have reached a local model,
  hosted fallback is blocked: model replies may quote them, so deleting image parts alone would not protect that history.
  Configure these choices under **Assistant settings → Customize how it works → Computer access**; saving does not launch a session.
* Hutch refuses to capture a browser page while a conventional password, payment or verification field is visible.
  Detection is by label/attribute and can miss custom widgets: the isolated desktop has no such detection, so do not point
  it at accounts or secrets.

## Actions and outcomes

Semantic browser actions (`click`/`type` by selector or exact label) are preferred; `click_at` exists for canvases and
unlabelled targets. Zero or several matching elements are **refused** with a bounded candidate list. Results carry one of:

| Outcome | Meaning |
| --- | --- |
| `effect_verified` | a postcondition was read back (navigation origin, field value) |
| `dispatched` | input was sent; no generic postcondition exists, so observe or check state |
| `mismatch` | the page changed the value that was entered |
| `navigated_elsewhere` | the page ended on a different origin than requested |
| `not_dispatched` | refused or fenced before any input |
| `unknown` | the channel failed or the run was stopped mid-action: reconcile before retrying |

The desktop tool additionally reports whether the screen visibly changed. A driver return is never reported as an effect;
the native scenario verifies the saved file on disk.

## Profiles, iframe scope and governed files

Profiles live at `browser-profiles/<immutable bot id>/browser-profile`, with one writer. Renaming an assistant preserves
persistent cookies; deleting it and reusing its name gives a different profile. Session-cookie retention follows the site's
cookie policy. Old `bots/<name>/browser-profile` directories stay untouched and are never silently imported: stop old runs,
back up the old directory separately, and sign in again using human control. Do not copy a profile to a different bot ID.

Pass `frame="#editor"` with a unique iframe selector for `read`, `type`, `click`, `wait`, `upload` or `download`. A removed
frame, replacement element, changed form or changed URL-scoped cookie state invalidates review. Cookie bindings are keyed
and ephemeral; cookies never reach an approval, log or planner. Browser observation refuses conventional sensitive fields
in child frames too. This cannot establish an identity held solely in a site's custom storage or interpret arbitrary scripts.

`browser upload` requires one visible file input and a regular UTF-8 workspace file (`.txt`, `.md`, `.csv`, `.json`). Review
shows the file name, path, size, SHA-256, bounded preview and page/form destination; selection may transmit bytes immediately.
Hutch rechecks the source revision, target and account binding after review, then selects frozen bytes. Symlinks, hard links,
known credential paths, binary content and files over 4 MB are refused. A later form submit separately reviews the exact
selected file digest and destination; its upload grant expires after 120 seconds or a control-generation change. File
selection verifies bytes in the input; the task still needs the app's service receipt.

`browser download` clicks a reviewed same-origin direct **HTTP** link into a new workspace text file. The pinned proxy
captures that actual GET once, requires HTTP 200, one Content-Length, identity encoding and a supported MIME type, bounds
headers to 32 KiB and body to 4 MB, and checks its eight-second deadline and authority during reads. A partial, oversized,
redirected, chunked, compressed, HTTPS or blob download is refused without retry or partial workspace output. HTTPS browsing
still works; its encrypted response cannot use this plaintext transfer boundary. Ordinary Chrome downloads are disabled.
Successful bytes become a private immutable SHA-256 artifact and a new workspace file; existing files are never overwritten.
The transfer budget is eight files / 16 MB per run, in addition to the shared 16 MB artifact cap.

The historic `screenshot` action now uses the same bounded frame store as `observe`, removing unbounded timestamp files in
the workspace. Human controls cannot invoke host uploads, clipboard or file transfer. A native dialog only sees its session's
explicitly granted workspace and disposable home; other user files and host network are absent.

## Stop, takeover and recovery

| Path | What happens | Measured here |
| --- | --- | --- |
| Run stop → browser | cancel hook ends the Playwright driver's process tree from outside the owning thread | 1.1–1.3 s to unblock a call hung in navigation (3 runs) |
| Run stop → desktop | session fenced, input worker killed, compositor/bus/apps killed | 0.06 s to all processes ended |
| Human wait (login/CAPTCHA) | run parks in `waiting_human`; driver slot is released; explicit handback revalidates the page | real visible-browser Wayland input and HTTP step input to a headless login fixture; no third-party challenge or physical-phone claim |
| Takeover racing an approved action | the action's ticket is stale and is not dispatched | tested (200-iteration race, plus a real approved click) |
| Hand back | new generation; coordinates require a fresh observation | tested |

Without local handoff or explicit step-control permission, a headless login fails clearly. Emergency stop is bound to the
run's independent cancellation path; there is no hardware hotkey. An interrupted action can have outcome `unknown`.

## Human step control

In **Assistant settings → Customize how it works → Computer access**, choose `Off`, `View captured frames` or
`View and take step control` (`remote_computer_access`, default `off`). Save, then start a new built-in run: changing an
active run cannot create a missing channel. The local owner controls settings. Paired devices additionally need Monitor
for viewing and Review for input, an unrevoked passkey session and its CSRF token. Use the existing explicitly configured
[private HTTPS deployment](operations.md#phone-supervision-over-private-https); this feature creates no TCP listener or relay.

1. Open the run panel and select its owned browser or private desktop. **Take control** fences automation immediately.
2. **Refresh human frame**, inspect the timestamp, and touch inside the image for one left click. Image bounds, aspect
   ratio, surface identity and geometry are checked. Scroll outside the image to move the supervision page.
3. Use the separate text and key controls for the focused app. Enter can submit a form; check focus first. Text is limited
   to 2,000 characters. Drag, held keys, clipboard, arbitrary chords and PTY are unavailable.
4. **Hand back to Hutch** explicitly resumes. It discards old plans, including a takeover/handback that completed during
   inference. New coordinate actions require fresh observation. **Pause control** fences both sides; **Stop run** ends it.

Only one viewer controls each surface. Tokens stay in the page's memory, are bound to its authenticated identity and
generation, and disappear on reload/restart. Hidden pages/pagehide request a pause; an independent host watchdog pauses
within the 15-second lease plus a one-second polling interval if heartbeats or permission disappear. No input queue replays
after reconnect. Frames expire for input after 10 seconds; commands run at most five times per second, queue four at most,
and must start within seven seconds. HTTP acknowledgement waits eight seconds. A lost response is uncertain: inspect
before retrying; an identical retained sequence never dispatches twice. Handback refuses pending input.

Human frames and text use the worker's owning thread and private in-memory channel, reached through an owner-only Linux Unix socket. They are never model observations,
run events or retained screenshots. Conventional browser passwords/OTP/payment fields are masked in the human preview;
custom widgets and native windows are **not reliably redacted**. Avoid credential material in native sessions. The transport
accepts at most 16 KiB per command. Slow or failed capture disables input until a fresh frame is available. Physical user
intervention in another display is not detected; use the explicitly owned session, rather than a shared personal desktop.

## Approved local development origins

By default the browser cannot reach loopback or internal names (SSRF protection). To work on your own web app, list exact
origins in the Bot's `local_dev_origins` (for example `http://localhost:3000`):

* `http` only, `localhost` or a loopback literal, explicit port, at most 8; LAN, link-local and metadata addresses can never
  be listed. Hutch's own dashboard port is refused.
* Public pages cannot load sub-resources from, redirect into, or script-navigate to an approved origin: the egress proxy (the
  only layer that sees redirect hops) requires an approved referrer/same-site context or a one-shot navigation permit the tool
  opens only around its own `goto`.
* Residual risk: an approved local app can still call itself and anything it is configured to call.

## Setup

```
hutch computer doctor            # read-only; one line per capability, with the step that fixes it
hutch computer doctor --deep     # also launches a headless browser in a throwaway profile
GET /api/v1/computer/readiness   # same data for the UI
```

Isolated desktop prerequisites: `kwin_wayland`, `dbus-daemon`, `busctl`, `spectacle` (capture through KWin), `libei`,
`bwrap`, `systemd-run`, `prlimit`, user namespace support and a
Python with PyGObject for the input worker (`/usr/bin/python3` is found automatically; override with `HUTCH_GI_PYTHON`).
Bot settings: `computer_apps` (program **names** only, resolved on `PATH`), `local_dev_origins`, `observation_to_hosted`,
`remote_computer_access`.
Add `computer` to the Bot's tools to enable the tool; nothing is on by default.

## Privacy and retention

Frames are private run artifacts (see above) and are removed with the run directory. Screens may show anything the allowed
applications display. Typed text is redacted from events, receipts and approvals (a typed sentinel secret was verified absent
from recorded events). Hutch does not read the clipboard or import your everyday browser profile. Browser file transfers require the separate
reviewed actions below; screen viewing or human step input grants no host file picker. Redaction is best-effort, not a guarantee; sensitive sessions should not use a hosted model route.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| "the isolated desktop could not start" | `hutch computer doctor`: missing `kwin_wayland`, `dbus-daemon`, `busctl` or `spectacle` |
| "input could not be established" | no PyGObject interpreter (set `HUTCH_GI_PYTHON`); KWin EIS not ready |
| click lands on the wrong widget | the app showed a different screen than assumed (for example KWrite's Welcome page): act on the frame you got back |
| typed text differs | non-US keyboard layout in the session; typing is US-keycode based |
| "frame … is not the latest observation" | an action since then returned a new frame; use that frame_id |
| "N elements match" | use an id/`data-testid` selector from the candidate list |
| frame shows "no longer retained" | the bounded store evicted it; observe again |
| browser tab blocked "internal name" | the origin is not in `local_dev_origins`, or is Hutch's own dashboard |
| another viewer controls the surface | ask that viewer to pause; after disconnect wait for lease expiry, then explicitly take control |
| stale frame / changed generation / lost acknowledgement | refresh and inspect; never blindly retry a submit |
| session stops after settings change | revocation won; review settings and start a new authorized run |
| workspace contains a policy-denied resource | move ordinary work to a clean workspace; do not weaken the credential deny |
| retained state / RSS budget exceeded | stop, inspect the private profile/session and reduce capacity; no automatic profile deletion |
| no Take control button | enable step control locally, start a new built-in run, check device Review permission and active channel |

## Upgrade and rollback

The added Bot setting has a backward-compatible default `off`; old saved configurations grant no remote input. Authority,
human pixels and input queues are not durable. On process restart, old tokens cannot resume a session. Stop active runs and
verify cleanup before rollback. Keep revoked device sessions and generation fences revoked; restoring a database requires
the existing restore review. Do not downgrade into the former shared browser or uncontained native-app paths.

## Prior measurements on the reference host

Host: Linux 7.2, KDE Plasma 6 Wayland, 8 cores, Playwright 1.63.0 / Chrome for Testing 153. Disposable KWin 6.7.5 session.
No model in the loop (so these are driver costs, not task times).

| Quantity | Result |
| --- | --- |
| Desktop capture (spectacle→KWin) | median 602 ms, p90 679 ms |
| EIS connect | 0.3–0.44 s; input dispatch under 1 ms (confirmation needs a new frame) |
| Desktop action + settle + capture | median 617 ms, p90 771 ms (100 cycles) |
| Browser observe | median 39 ms, p90 46 ms; act + verify median 214 ms, p90 257 ms (100 cycles) |
| Desktop memory over 100 cycles | flat (361→359 MB process tree) |
| Browser memory over 100 cycles | Hutch process flat (~59 MB); browser+driver 627→667 MB, mostly in the first 15 cycles |
| Frame store | capped at 64 frames (0.65 MB browser, 2.2 MB desktop) |
| Leftover processes after the soak | none |

These are the earlier slice's baseline, **not measurements of the final resource-watchdog code**. The earlier 100-cycle result is in
`research/artifacts/computer-use/soak-100-cycles.json`.

## Contributor and installed-package checks

Use the existing development environment and installed Chromium; native tests need the prerequisites above. Use a private,
disk-backed `TMPDIR` on this host. Direct offline-broker fixtures need a short pytest base path (Linux Unix socket pathname
limits); the normal run broker already creates a short private directory.

```sh
PYTHONPATH=src python -m pytest -q --ignore=tests/e2e --basetemp=/short/private/test-path
PYTHONPATH=src python -m pytest -q tests/e2e/test_computer_*.py tests/e2e/test_browser*.py
PYTHONPATH=src python benchmarks/computer_use_soak.py --cycles 100 --json /private/soak.json
uv build --offline --wheel --out-dir /private/dist
# Install that wheel with browser/anthropic extras into a separate environment; no editable source import.
/private/install/bin/python -I scripts/verify_computer_wheel.py --source-root "$PWD" --evidence /private/wheel.json
```

The wheel check serves packaged assets/readiness, invokes the installed CLI, checks native worker/driver source hashes,
and observes a real throwaway Chromium page. It does not claim real model inference, native delivery on another platform,
or a deployed phone connection. The soak measures deterministic driver tasks, errors/navigation and control-lease handoff;
HTTP/phone latency is a separate scenario. Capture includes encoding/driver transport, whose CPU costs are not separately
instrumented. Fresh results and unexecuted checks belong in the dated evidence ledger, rather than being inferred from a
successful installation.

## Tests

`tests/test_computer_*.py`, `tests/test_netguard_local_origins.py` (deterministic); `tests/e2e/test_computer_browser_real.py`,
`test_computer_isolation.py`, `test_computer_transfers.py`, `test_computer_panel.py` (real Chromium/server); `tests/e2e/test_computer_native.py` and
`test_computer_handoff_native.py` (real disposable KWin session; skipped when the prerequisites are absent). Fakes inject faults; they are not evidence that real
capture or input works.
