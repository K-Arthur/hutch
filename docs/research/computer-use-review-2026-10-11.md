# Computer-use continuation: evidence and decisions

Reviewed 2026-10-11. This supplements, rather than replaces, the [earlier ledger](computer-use-baseline-2026-10-10.md).
The starting checkout is `2872f4f`, on `wcag22-audit-fixes`, with unrelated changed evidence and untracked work.
`master` is absent. The owner explicitly authorized a separate worktree after this was reported; work proceeds in the
attached, detached worktree `supervised-computer-use/hutch`. No shared checkout, branch, or unrelated service is changed.
Earlier computer-use work at `da7d590` is being reapplied to the newer integration, preserving the skills and safety work.

## Current evidence, not product prevalence

These are first-hand reports, not proof that every current version fails. Read on 2026-10-11; no issue commands were executed.

| Source | Reported environment and failure | Fix evidence | Hutch response / check |
| --- | --- | --- | --- |
| [Browser Use #4518](https://github.com/browser-use/browser-use/issues/4518) | 0.12.5, macOS: typing enables a button but a cached action batch clicks another element | Reporter closed it; no linked release establishes a fix | Resolve each action against the current DOM; enabled-after-type real-browser regression |
| [Browser Use #2862](https://github.com/browser-use/browser-use/issues/2862) | ≤0.7.0: missing field is replaced by a nearby field | Closed, no linked fix on the inspected page | Refuse missing and ambiguous targets; test the untouched neighbouring field |
| [Browser Use #1157](https://github.com/browser-use/browser-use/issues/1157) | 0.1.40, Linux Mint: repeated first step, blank browser, growing history | Closed; report does not establish a single cause | Existing repeat/deadline limits plus explicit dispatched/verified/unknown outcomes; do not infer success from driver return |
| [CUA #2105](https://github.com/trycua/cua/issues/2105) | Driver 0.7.0, GNOME/Wayland: capture works but no delivered input | Maintainer reports portal-enabled builds since 0.11.0 and requests a 0.30.4 retest; no independent retest here | Capture and input readiness are separate. KWin evidence does not establish GNOME support |
| [CUA #2962](https://github.com/trycua/cua/issues/2962) | 0.19.0, Hyprland/XWayland: another workspace's pixels returned for the requested window | Closed with #3200; not installed or reproduced here | Bound identity to the isolated display/session; never claim arbitrary existing-window identity |
| [CUA #2259](https://github.com/trycua/cua/issues/2259) | 0.8.3, KDE: reported runaway memory during a click | Maintainer cites #3336 / 0.23.0; reporter closed it after improvement | Bounded driver process and retention; separate process-tree measurements and soak |
| [PyAutoGUI #413](https://github.com/asweigart/pyautogui/issues/413) | Windows 10, Python 3.7.3, monitors at 200% and 100%: incorrect pointer coordinates | No cross-platform fix verified here | Use explicit image coordinates, reject out-of-bounds/stale frames; test preview letterboxing rather than assume Windows parity |
| [Claude quickstarts #254](https://github.com/anthropics/claude-quickstarts/issues/254) | Demo at 1280×900: request 413 after about ten minutes; lower resolution helped | Exact cause unconfirmed in report | One latest image per prompt, byte/resolution/storage budgets; wire-level context-growth tests |

The local regressions also cover profile isolation and cleanup, interrupted input/held-key cleanup, takeover fences,
malicious page metadata/self-approval, and typed sentinel absence from records. Those are Hutch checks, not claims about
the prevalence or security of another product. Their fresh results are recorded with each implementation milestone.

## Component decision

| Candidate | License / boundary inspected | Decision |
| --- | --- | --- |
| [Existing Playwright](https://playwright.dev/python/docs/library) | Installed 1.63.0; API is thread-affine, cancellation of an executing async call is unsupported | Retain owned synchronous sessions and supervise their driver processes; use [strict locators](https://playwright.dev/python/docs/locators) and actionability |
| [Browser Use](https://github.com/browser-use/browser-use) | MIT; adds its own agent loop and browser/cloud features | Do not add a second planner or its overlapping lifecycle; adopt regression hypotheses |
| [CUA](https://github.com/trycua/cua) | Driver/protocol MIT; current Spaces viewers/codecs include FSL, optional `cua-som` AGPL | No blanket MIT assumption or viewer dependency; bounded frames and reviewed step input fit the current task |
| [Agent S](https://github.com/simular-ai/Agent-S) | Apache-2.0; another planning/grounding stack and model configuration | Do not replace Hutch's authorization/model loop; benchmark claims do not establish local safety |
| [XDG portals](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html), [libei](https://libinput.pages.freedesktop.org/libei/) | Consent-negotiated session/input mechanisms; lifetime and device capabilities matter | Keep the narrow isolated KWin/libei slice. Personal-desktop portals remain consent-gated and unverified; no permission changes |
| [OSWorld](https://github.com/xlang-ai/OSWorld) | Real application outcome evaluation | Verify editor artifacts and browser receipts independently; do not call the smaller Hutch scenario set an official score |

No new dependency, model download, privileged daemon, network exposure, or paid inference is introduced by this decision.

## Revalidated host and initial checks

Linux 7.2.7 CachyOS, KDE Wayland; XWayland also exists but is not evidence of native Wayland input.
CPython 3.13.15, Playwright 1.63.0, OpenAI package 3.26.0, Anthropic package 1.13.0, FastAPI 0.142.3.
KWin, Spectacle, libei-related tools, D-Bus and KWrite are available. All input tests use disposable desktops/profiles.

Initial integrated baseline: **124 passed** in 47.82 seconds (browser profiles, approval CAS, runtime, skills, Responses).
Restored browser/frame/control unit and wire checks: **163 passed** in 54.37 seconds. Real-browser/native and visual
continuation results, packaging, phone emulation and live-model limitations are separate obligations; these counts do not
establish their completion.

Restored native/doctor/privacy/offline checks: **158 passed** in 52.49 seconds. The first real-process batch ran
**37 passing scenarios and one failure** in 237.52 seconds. The failure was the visible-browser handoff launch:
the host's 12 GiB `/tmp` tmpfs was full (`ENOSPC` in Chromium/dconf). It is not classified as a passing handoff.
Testing moves to a private, disk-backed `TMPDIR`; no unrelated temporary files or services are removed.
The passing scenarios include the real KWrite edit/save/dialog/reopen and menu flows, profile isolation,
browser target checks, and the session panel. Current 360/768/1440 panel captures live in
`docs/research/artifacts/computer-use-2026-10-11`; 360 and 1440 were opened and inspected.
The isolated visible-browser handoff recheck passed in **8.98 seconds** with the disk-backed temporary directory;
the original failed attempt remains recorded. This proves disposable KWin/EIS human input, not a physical phone.

## Privacy, control and native containment milestone

Replacing an approved field at the same URL is refused by its frame/backend-node fingerprint. Stop cannot be overwritten
by takeover/hand-back/pause between transition precheck and mutation. Hosted consent now covers page text and labels,
including text-only observations. Private local observation history blocks hosted fallback: model replies can quote it.
Official OpenAI image messages were checked through an HTTP mock transport; custom endpoints and unknown model names do
not infer vision. No hosted inference was performed.

Focused browser/privacy/image/profile checks: **43 passed** in 103.41 seconds. Earlier attempts caught two obsolete policy
expectations and an uninitialized test page; the corrected real DOM test requires the replacement field to remain untouched.
Settings round-trip/readiness: **3 passed** in 23.97 seconds after fixing a test label and respecting sorted backend origins.
Visual inspection caught the lengthy readiness wall; it now has a summary and expandable capability details.

Native apps now require the existing namespace/resource backend: workspace/private-home user files, no host network, no
D-Bus broker and bounded resources. The private compositor remains trusted. Before implementation, we read
[Bubblewrap's security notes](https://github.com/containers/bubblewrap/blob/main/README.md): arguments define the boundary,
and mounting a service bus can widen authority. The systemd web manual was unavailable through the browser; the existing
verified Hutch scope path and installed tooling were used. No dependency was added. A real app-process probe confirms an
outside sentinel is absent and a host loopback listener unreachable. Menus/edit/save/native-dialog/reopen still work.

Combined privacy/control/desktop/containment/native/panel checks: **65 passed** in 104.55 seconds. Native stop: **0.06 s**.
An earlier 54-pass/one-failure batch exposed a test assumption that its workspace was outside HOME; a workspace below the
disk-backed TMPDIR legitimately creates empty mount ancestors. The assertion accounts for that location and retains the
outside-file canary check. Native dialog/reopened/menu captures, settings at 360/1440, and the 768 panel were opened and
inspected. These are disposable Wayland and viewport-emulation results; physical phone/model validation remains open.

## Human step input, worker boundary and website milestone

The authenticated route now fences one viewer per surface and queues bounded commands to the owning driver thread.
Human pixels/text remain ephemeral, absent from transcripts and model requests. Browser conventional password/OTP/card
fields are masked in the private preview, with custom/native fields explicitly outside that guarantee. The controller has
a 15-second heartbeat lease, a 10-second input-frame lifetime, four pending commands, 5 Hz input, seven-second dispatch
deadline and eight-second acknowledgement wait. Identical retained sequences return their result without redispatch;
out-of-order or changed commands are rejected. Pause/revocation/restart discard queues and private pixels.

Review caught an integration gap: in-process tests initially proved HTTP input but normal run workers are separate
processes. We read [Python's socket contract](https://docs.python.org/3.13/library/socket.html) before adding a bounded,
owner-only Linux pathname socket, same-UID peer checks, four RPC handlers and no TCP listener. The worker alone touches
Playwright/native objects. The attempted Linux man-page web fetch was unavailable; no unsupported contract is claimed.
The corrected real-process test passed in **8.39 s**: a normal built-in process worker using a scripted local protocol
server opened a real headless login, received clicks/text/Tab/Enter from the actual Hutch web panel, reached the app's
conditional receipt endpoint, explicitly handed back and finished. No real model weights or physical phone were used.

Focused human/API/responsive tests passed **20 in 37.18 s**; API paired auth/Monitor versus Review/CSRF/revocation passed
**9 in 8.46 s**. The stricter login and panel fixtures passed **13 in 32.04 s**. Human/runtime/site checks passed **56 in
60.05 s**. These are overlapping checks, not an additive scenario count. Before correction: one tablet raw-click scenario
failed after supervision-page scrolling; it now uses explicit Tab/Enter and requires actual password entry. One website
test failed at all widths because its separate limitations disclosure was closed; it now opens both actual disclosures.
One lifecycle batch failed an immediate assertion before the second viewer's HTTP error arrived; it now waits for the
visible committed result. The first process-worker attempt used the test server's thread executor; the test now explicitly
requires the production process executor and a distinct worker PGID, with no in-process registry entry.

Review also fixed late queued input, handback during in-flight input, a complete takeover/handback during inference, late
HTTP grants after page backgrounding, stale-frame UI input and a misleading owner label/duplicate Resume control. The
independent watchdog runs without the driver pump. Public content cannot authorize these transitions.

Actual 360/768/1440 still-frame input, real KWrite human edit/save, landscape and 320-pixel reflow, two viewer exclusivity
and an injected `pagehide` pause are verified locally. This is **viewport emulation and lifecycle fault injection**, not
physical iOS/Android suspension. Fresh screenshots include `phone-control-*`, `site-computer-*`, limitations and settings
in `artifacts/computer-use-2026-10-11`. Website cards/limitations at all three widths and the 768 phone view were opened
and inspected; console/network/overflow evidence is in the adjacent website JSON. Marketing stays scoped to implemented
experimental capability and explicitly names physical-phone/live-network/model-grounding gaps. No site was published.

Combined human/API/pairing/CAS/native-input/doctor/panel/site verification: **96 passed in 102.98 s**. Subsequent visual
inspection found landscape focus partly covered by the sticky status. The status is now concise, capture time sits beside
the preview, and text/key focus is brought into view. A stricter follow-up exposed an in-flight run refresh replacing a newly
acquired controller: it now rechecks authority after its API wait and before DOM replacement. The earlier follow-up had
**14 passing checks and one failure**; corrected phone/panel checks passed **15 in 57.08 s**. Updated landscape, 320-pixel
reflow and the real process-worker signed-in preview were opened and inspected. Focus is visibly unobscured and Stop stays
reachable. These results do not replace the separate remaining file-transfer/resource/package obligations.

## Immutable profiles, iframe targets and bounded transfers

Focused official research: [Playwright frames](https://playwright.dev/python/docs/frames),
[in-memory file selection](https://playwright.dev/python/docs/input#upload-files),
[route ordering](https://playwright.dev/python/docs/api/class-route#route-fallback),
[download lifecycle](https://playwright.dev/python/docs/downloads),
[Python 3.13 HTTP parsing](https://docs.python.org/3.13/library/http.client.html), and
[formAction defaults](https://developer.mozilla.org/en-US/docs/Web/API/HTMLInputElement/formAction).
HTTPX streaming/proxy docs were also inspected for a candidate, then that candidate was removed after actual UI testing.
No dependency was added. Stable-ID profile paths preserve persistent cookies across rename and keep recycled names separate;
legacy name-profile data is untouched. Explicit iframe scope and the CDP backend-node binding refuse replacement frames.

Failures were retained: initial browser/isolation checks had **32 pass / 1 fail in 43.60 s** (the new test used a session cookie).
The first transfer batch had **3 pass / 2 fail in 9.15 s** (Chromium's file input UA shadow button was reviewed as a button).
The next **4 pass / 2 fail in 11.56 s** exposed `formAction`'s default document URL and a second sync driver in one thread.
Review now uses an override only when its HTML attribute exists, and the test respects driver thread ownership. Subsequent
mixed attempts failed once each in **11.98, 13.11 and 13.57 s**: iframe downloads made a real GET that bypassed both page and
context Playwright routes. A diagnostic trace confirmed the GET at the origin with no request callback. We did not repeat it.

The corrected path captures the actual plaintext GET at Hutch's DNS-pinned proxy, before forwarding response bytes, with
Content-Length/MIME/encoding/size/deadline/authority checks. HTTPS, redirects, chunks and blobs are explicitly unsupported
for this managed action; normal HTTPS navigation retains Chromium TLS. No unbounded Chrome download spool is enabled.
Uploads use descriptor-anchored workspace reads, reject secret paths/links, bind revisions/digests and select frozen bytes.
Form submission has a fresh outward review, checks exact selected file hashes, and includes a private cookie-state binding.
The legacy screenshot action now uses the bounded frame store rather than accumulating workspace PNGs.

The first corrected transfer batch passed **5 in 8.44 s**. The actual mixed fixture uses the production approval gate and
receipt recorder, a resource-contained shell command, a real iframe form, conditional upload receipt and one managed GET.
Its expected CSV, uploaded bytes, receipt SHA-256, immutable artifact and final workspace file match. `mixed-workflow.png`
was opened and inspected: the controlled app shows the accepted receipt and hash inside the intended iframe. The adjacent
JSON records UI/a11y state and provenance. This is a local deterministic workflow, not model grounding or an OSWorld score.

After adding the actual Next/upload form stage, cookie-account-change refusal, a whole-header bound and download-header
deadline, the combined profile/real-browser/isolation/transfer/proxy checks passed **46 in 54.27 s**. The refreshed receipt
screenshot was opened and inspected again. Source: `browser.py`, `browser_files.py`, `browser_proxy.py`, `config.py`;
regressions: `test_computer_transfers.py`, `test_computer_isolation.py`, `test_browser_profiles.py`, `test_browser_proxy.py`.
