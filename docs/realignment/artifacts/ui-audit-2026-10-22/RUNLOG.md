# Run log — measured UI audit, 2026-10-21/22

## Inputs and assumptions

The pipeline prompt arrived with every input blank. Assumptions (auto mode, "proceed, flag
decisions"):

- **Target:** Hutch SPA, server-rendered pages and marketing site in this repository.
- **Task (user terms):** a person running Hutch can chat, approve or deny actions, find past work
  and adjust assistants and settings, by mouse, keyboard, touch, zoom/text spacing and screen
  reader, at phone through wide desktop widths, without hidden, covered or unreachable controls.
  Inferred from the `wcag22-audit-fixes` branch and the 2026-10-20 audit's stated gaps (no axe run,
  no text-spacing/RTL/pseudo stress).
- **Users and platforms:** per PRODUCT.md (everyday users; desktop and phone first-class); web only.
- **Constraints:** PRODUCT.md (no framework or bundler, no external assets), DESIGN.md tokens and
  rules, WCAG 2.2 AA.

## Mid-task instructions from the user

1. *"switch to main and work from there but ensure anything from the current branch that is key is
   committed first including items prior to yours"* — committed `ui-audit.mjs` (1c1d873d) and five
   `.zcode/plans` session plans (c9b14d2d) on `wcag22-audit-fixes`; detached the idle
   `.worktrees/documents` checkout (same commit, no file changes) to free `main`; switched the
   primary checkout to `main` and merged the branch (ceb9d36b); rebased this worktree onto it.
   Left untracked as not key: `var/` (fontconfig cache), `.opencode/` (20 MB vendored skill),
   `.codex/hooks.json`, `.v2c/`, `.video_agent/` (machine-local plugin markers),
   `docs/realignment/artifacts/settings-disclosure-axes-2026-10-10/trace-failed.zip` (unreferenced
   debug trace; the passing `trace.zip` is tracked).
2. *"Also account for higher level design decisions …"*, *"also account for component alignment and
   arrangement"*, and *"text overload and not enough breathing room and processing time"* — added
   the design-level review (FINDINGS "Design-level review", PLAN DC-1…DC-9).

## Phase 0 — concurrency and isolation

- `git worktree list`: 25 worktrees; files modified in the last 4 hours: only the new
  `ui-audit.mjs`. Processes: another Claude session and OpenCode were working in a different
  repository (`varve`); none in Hutch. Ports in use: 4319 (unrelated `python -m http.server`),
  49374 (OpenCode).
- Claim: `.git/agent-claims/claude-wcag22m.md` (claimed paths: static JS/CSS, templates, these docs,
  WCAG tests; exclusive token files not touched).
- Worktree: `.worktrees/wcag22-measured`, branch `agent/claude-wcag22m/measured-audit`, own `.venv`
  (`uv sync --extra dev --extra browser`) and `npm ci`. Fixture servers on 8797/8798 (change set) and
  8796/8795 (frozen `git archive` of the base for "before"); the verifier was assigned 8799–8802.

## Tooling issues found and handled

- **ui-audit.mjs silently skipped axe** on every page: Hutch's CSP blocks the injected script and the
  error was swallowed (0 of 120 runs had axe results while the summary implied it ran). Patched
  (CSP bypass in the audit's own browser context; `axe-unavailable` finding; CSP in the self-test
  fixture). Self-test passes; with the bypass removed the self-test **fails**, so the check can fail.
- **My design-review instrument** first counted text inside collapsed, overflow-clipped panels
  (reported 1,653 words on Assistant settings); corrected to clip-aware visibility; the inflated
  numbers were discarded.
- **Fixture drift:** chat approvals expire after ~10 minutes; servers were restarted fresh before
  each comparison.
- **CLS under contention:** running two matrices at once inflated CLS; isolated re-measurements are
  the authority (table in the report).
- **Commit slip:** D-03 was committed once with a failing browser test hidden by a pipe; found
  immediately, fixed (the search-width rule matched the new radios) and folded into the same commit.
  Later runs check pytest's own exit status.

- **Regression caught by the final matrix:** the first header/reminder change (an 18rem identity
  basis and an in-flow reminder at 641–900 px) raised CLS on Scheduled work and run detail at
  1024 px (0.04 → 0.20), chat at 768 px (0.06 → 0.13) and the Needs you route (show-then-hide flash,
  up to 0.31). Isolated re-measurement confirmed the sources; commit 9c25bdbd replaced both
  mechanisms and added two tests that fail on the earlier version (one needed a 960 px viewport to
  discriminate in the test environment).

- **Second correction:** the fixed dock still made the reminder jump on its own when the header
  grew after load (+0.027 CLS at 641–720 px) and could sit above the open tablet navigation sheet;
  a824292a places it in the main view's grid cell instead. The stress pass also caught the new
  switch's label refusing to wrap at 320 px under pseudo-localization (6e1ff7dd).
- **Accepted trade-off:** at 901–960 px, run detail (title, status chip and controls need 438 px of
  a 340 px row because the workflow counts take ~230 px) and Scheduled work (2 px short) wrap the
  header once on load (CLS ≈ 0.17–0.25 at exactly 901 px) instead of overlapping, which was the
  original defect. Removing it needs a product decision to shorten the workflow counts at that width.
- **Disk:** `/tmp` (a 12 GB shared RAM disk) filled during the run, mostly with other tools'
  files (`hutch-apt` 2.3 GB, `.pnpm-store` 1.6 GB, `opencode` 728 MB, ~2.3 GB of build caches from
  18–21 Oct). It crashed one matrix pass and the fast test suite (`database or disk is full`). Only
  this session's own screenshots were deleted; the remaining test runs used a temporary directory on
  the main disk (`~/.cache/hutch-claude-tmp`, removed afterwards).

- **Full browser suite, first final run (336 tests): 7 failed.** Classified: 2 were this
  branch's own tests broken by an edit that removed a shared constant (a353b404); 2 were caused by
  the D-06 hover hold keeping a notice alive under a resting cursor (168985b2); 1 was the 18rem tile
  threshold making compact phone cards too tall (7c29b027); 2 are pre-existing on `main` and fail
  identically against the frozen base export (`test_workspace_model_default_…` — `#prefs-toggle`
  was removed by 431a9f32; `test_runs_archive_loads_older_pages_and_searches_them` — expects
  "200 loaded results", text that no longer exists on `main`).
- **Commit slips:** twice a commit went in while a test in the same command had failed (pipe hid
  the exit code); both were caught on the next check and corrected (the D-03 search-width fix folded
  into its commit; the F-10/F-07 test wait fixed and amended). Later runs gate commits on pytest's
  own exit status.

## Gates

- Plan gate: no global token change, feature removal, dependency, or API change, so the plan
  proceeded (auto mode). Flagged product decisions are listed in FINDINGS and were not changed.
- One new shared component (switch) was added; the user asked explicitly for switches where they fit.

## Skipped or not available

- Lighthouse was not run (not installed; adding it was out of scope). CLS was measured with
  PerformanceObserver; LCP/INP were not measured.
- No screen reader, real iOS/Android device, Windows High Contrast or real Safari: these remain
  **needs human check**. Forced colours were emulated in Chromium; Firefox and WebKit were assigned to
  the independent verifier.
- Light theme: N/A (dark-only by design; computed colours identical under `prefers-color-scheme`).

## Independent verification

A separate agent received only the cards, measurable acceptance criteria and the branch (none of the
implementer's reasoning). Its first start stopped on an account rate limit; it was resumed after the
reset against a frozen `git archive` of commit 7b7291fa, with its own fixtures (ports 8799–8802) and
the base export for comparison, in Chromium and Firefox (WebKit cannot launch on this host: missing
libicu74/libxml2/libflite1).

**Verdict: 14 PASS, 2 PARTIAL, 0 FAIL.** PASS: TC-1, TC-2 (+ switches), TC-3, TC-5, TC-6, TC-7, TC-8,
D-03, D-05, D-06, D-07, D-08, F-18, F-19, both CLS regression checks, parity (control inventories
identical before/after on 11 screens at 1280 and 390 px except the intended swaps; no new axe
violations; no console errors), and 38/38 tests against the frozen export. PARTIAL:

- TC-4: "ChatGPT" still broke at 641–664 px beside "Not available here" (pre-existing). Fixed in
  543a9d5e (threshold 16rem → 18rem); test now forces the longest badge on every tile.
- D-09: at 390 px touch the import field is 42.8 px and the button 40 px (stacked, so not side by
  side) — a side effect of the touch floor; accepted.

Defects it reported: the touch floor shrank the 18 px composer to 16 px (fixed in 543a9d5e); tables
are tab stops even where they do not scroll at 1280 px (accepted trade-off, documented); the chat
header wrap at 901–1280 px raises chat CLS from ~0.0001 to ~0.03 (under 0.1); the docked reminder
overlays the top of the conversation text (as before; no control covered while tabbing).
