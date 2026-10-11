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
