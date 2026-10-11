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
| Remote (phone) *control* of a surface | | **not implemented**; the phone can supervise, approve, stop and resume |

## How a session is bounded

```
person ─ enables ─▶ Bot settings (tools, computer_apps, local_dev_origins, observation_to_hosted, approval_mode)
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
rather than guessed. The result of typing is confirmed by observation, not assumed.

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

## Stop, takeover and recovery

| Path | What happens | Measured here |
| --- | --- | --- |
| Run stop → browser | cancel hook ends the Playwright driver's process tree from outside the owning thread | 1.1–1.3 s to unblock a call hung in navigation (3 runs) |
| Run stop → desktop | session fenced, input worker killed, compositor/bus/apps killed | 0.06 s to all processes ended |
| Human wait (login/CAPTCHA) | run parks in `waiting_human`; the driver slot is released; control is the person's; resume revalidates the live page and requires a fresh observation | verified with real input in a disposable Wayland session (`tests/e2e/test_computer_handoff_native.py`); local visible browser only |
| Takeover racing an approved action | the action's ticket is stale and is not dispatched | tested (200-iteration race, plus a real approved click) |
| Hand back | new generation; coordinates require a fresh observation | tested |

Honest limits: there is **no remote (phone) control surface**. A headless browser has no human view; the run says so
instead of waiting for a window that does not exist. Emergency stop is bound to the run's cancel path, not to a hardware
key. A stop leaves the run's outcome for the interrupted action `unknown`.

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

Isolated desktop prerequisites: `kwin_wayland`, `dbus-daemon`, `busctl`, `spectacle` (capture through KWin), `libei`, and a
Python with PyGObject for the input worker (`/usr/bin/python3` is found automatically; override with `HUTCH_GI_PYTHON`).
Bot settings: `computer_apps` (program **names** only, resolved on `PATH`), `local_dev_origins`, `observation_to_hosted`.
Add `computer` to the Bot's tools to enable the tool; nothing is on by default.

## Privacy and retention

Frames are private run artifacts (see above) and are removed with the run directory. Screens may show anything the allowed
applications display. Typed text is redacted from events, receipts and approvals (a typed sentinel secret was verified absent
from recorded events). Hutch does not read the clipboard, does not transfer files, and does not import your everyday browser
profile. Redaction is best-effort, not a guarantee; sensitive sessions should not use a hosted model route.

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

## Measured on the reference host

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

`benchmarks/computer_use_soak.py` reproduces these; the 100-cycle result is in
`research/artifacts/computer-use/soak-100-cycles.json`.

## Tests

`tests/test_computer_*.py`, `tests/test_netguard_local_origins.py` (deterministic); `tests/e2e/test_computer_browser_real.py`,
`test_computer_isolation.py`, `test_computer_panel.py` (real Chromium/server); `tests/e2e/test_computer_native.py` and
`test_computer_handoff_native.py` (real disposable KWin session; skipped when the prerequisites are absent). Fakes inject faults; they are not evidence that real
capture or input works.
