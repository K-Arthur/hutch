# Completion inventory: demo data, claims, and dashboard states

Read-only audit of the working tree on 2026-10-29 for a completion realignment slice. This is the
only file written. 153 pre-existing uncommitted entries stay untouched (section 6). Line numbers are
from the dirty working tree; lines inside files owned elsewhere may move after their edits land.

Method: `rg -n -i` over `src/`, `website/`, `tests/` excluding generated CSS/fonts, plus manual reads
of `pages.py`, `templates/`, `static/`, the named docs, README and website files.

## 1. Keyword inventory

Counts exclude generated CSS (where `::placeholder` is CSS syntax) and fonts.

| Term | src | website | tests | Class summary |
|---|---:|---:|---:|---|
| demo | 13 | 1 | 450 | guards/copy in src; test fixtures in tests |
| fixture | 68 | 3 | 1070 | evidence wording in src; test data in tests |
| mock | 24 | 0 | 597 | refusal guards and comments in src; test runtime in tests |
| TODO | 2 | 0 | 5 | prompt text and test strings, no code debt |
| FIXME | 0 | 0 | 0 | none |
| NotImplementedError | 1 | 0 | 0 | abstract base method |
| placeholder | 128 | 0 | 8 | HTML input attributes, markdown sentinels |
| sample | 107 | 7 | 84 | CSV probing, docgen, site response-style sample copy |
| dummy | 1 | 0 | 1 | comment; test-only dummy key |
| lorem | 0 | 0 | 0 | none |
| Total | 340 | 11 | 1746 | |

Classification: user-facing-data (bad) = 0 confirmed; test-only (fine) = all `tests/` hits (1746)
plus `tests/support/` fixtures; internal/legitimate = 340 src and 11 website hits, sampled below.

| file:line | Hit | Class |
|---|---|---|
| src/hutch/tools/base.py:46 | `raise NotImplementedError` | internal: abstract Tool contract, user-unreachable |
| src/hutch/shellparse.py:355 | dummy-word comment in redirect parsing | internal comment |
| src/hutch/server/static/app.js:3586,5248 | "Inspect this repository for TODOs" quick prompt | internal user-prompt copy, not code debt |
| src/hutch/data/compat.json:14,26,41,53 | "fixture-tested" provider verification wording | internal evidence wording |
| src/hutch/templates.py:5 | "not a pile of demo personas" | internal docstring, anti-demo |
| src/hutch/store.py:7090; views.py:439 | "(a fixture, an import, a demo)"; "a test fixture run" | internal comments |
| src/hutch/server/static/markdown.js:33,61; palette.js:36; static/index.html:94 | placeholder sentinels/input placeholders | internal UI attribute |
| src/hutch/workspace/csvprobe.py:12,29,64,82 | bounded CSV sample bytes | internal CSV sampling |
| tests/test_safety.py:109; test_studio_transcript.py:243-244 | shell sample; TODO text in synthetic output | test-only |

Mock-runtime hits are deliberate refusals, not selectable demo paths:

- `src/hutch/modelchoices.py:379-380` refuses `mock` (ModelNotUsable: test-only).
- `src/hutch/runtime/__init__.py:22-23` RuntimeUnavailable: "The mock runtime was removed."
- `src/hutch/engine.py:357`, `src/hutch/doctor.py:180`, `src/hutch/models.py:79` diagnose/legacy only.
- `src/hutch/server/static/model-switcher.js:37` lists "mock" only to classify brand marks; no route list.
- `tests/e2e/test_browser.py:10777` asserts the retired mock route is visibly unavailable.
- `src/hutch/server/pages_usage.py:33` still prints "legacy test fixture" as billing for legacy mock
  usage (low risk; user-visible only for pre-existing mock rows).

## 2. Hard-coded demo values in pages/templates/static

`rg` over `src/hutch/server/pages.py` (no demo/fixture/mock hits), all 28 templates, and static JS:
no hard-coded demo bots/runs, no fake counts, no lorem, no placeholder metrics.

- Template hits are input `placeholder` attributes or macro parameters only:
  `templates/connections.html:70,91,99,122,141`, `models.html:118-124`, `bot.html:35,95,115,128`,
  `bot_new.html:10,16,17,19`, `_form.html:43,50,61,67`.
- Positive evidence (anti-demo copy already shipped): `templates/home.html:11` ("does not seed sample
  bots or simulated runs"), `templates/bots.html:26`, `templates/bot_new.html:7` ("does not create
  sample runs or simulate model output").
- `src/` does not import test code: `rg 'from tests|import tests'` and `tests.support|tests.fixtures`
  over `src/` return zero. Test-only runtime lives in `tests/support/runtime.py`, per
  `docs/realignment/no-mock-validation.md:12-16`.
- Residual fixture surface: `src/hutch/web/preview/fixtures.ts:1-20` and `bot-fixtures.ts:1-11` are
  synthetic, labelled, read-only fixtures for `src/hutch/server/static/redesign-preview.html`
  (`redesign-preview.html:71-72,91` says deliberately unlinked, no approval posted). It is served by
  the static mount (`app.py:7453`) so `/static/redesign-preview.html` works if guessed; no product
  link exists. Both files are untracked (owned elsewhere). Decide before ship: exclude from packaged
  static or document as developer-only.
- Dual UI surface (not demo data): `/` and `/legacy` both serve the SPA shell (`pages.py:178-183`,
  `pages.py:190-194`); server-rendered templates remain live at `/bots`, `/runs`, `/approvals`,
  `/legacy/connections` (`pages.py:245-707`).

## 3. Explicit "not implemented" / pending claims in current docs

Feasibility: small = copy/state only; large = multi-file product work; external = needs accounts,
signing, CI or upstream projects.

| file:line | Claim (current tense) | Feasibility |
|---|---|---|
| README.md:32,101,109 | macOS and Windows executors are not implemented | external |
| README.md:169 | Bot memory permanent deletion is not implemented | large |
| README.md:262 | No packaged desktop installers, no hosted sign-up, no PyPI | small copy; external to publish |
| docs/bot-config.md:24 | Drafting reusable procedures/skill metadata and permanent scoped deletion still pending | large |
| docs/bot-config.md:32 | Permanent deletion is not implemented; archive retains history | large |
| docs/operations.md:229 | Authenticated PTY and personal-desktop input not implemented | large |
| docs/operations.md:489 | Permanent scoped deletion is not implemented | large |
| docs/safety.md:34 | OpenCode plugin directories refused pending upstream verification | external prerequisite |
| docs/safety.md:416 | Authenticated PTY unavailable; physical-phone/live-network input unverified | large / external |
| docs/realignment/tests.md:36 | OpenCode permission round-trip not covered; execution unavailable | external |
| docs/realignment/tests.md:39 | T-PERMISSION-BROKER planned | external (installed OpenCode) |
| docs/realignment/tests.md:54 | Artifact/runtime-switch context remains open | large |
| docs/realignment/tests.md:56 | Natural-language request refinement/conversational detail resolution open | large |
| docs/realignment/tests.md:64 | Permanent scoped deletion remains unimplemented | large |
| docs/realignment/tests.md:76 | Coordinator brief partial; live model draft quality unverified | external (live model) |
| docs/realignment/tests.md:78 | T-CROSS-BOT-DELIVERY planned (same-Bot only today) | large |
| docs/realignment/tests.md:79 | Coordinator/specialist routing and actual-route reporting open | large |
| docs/realignment/tests.md:80 | Full process restore, external-runtime recovery, live model recovery unimplemented | large |
| docs/realignment/tests.md:82 | Full memory-policy journeys partial | large |
| docs/realignment/tests.md:84 | General reusable cross-Bot grants not implemented | large |
| docs/realignment/desktop-production-2026-10-26.md:9-13,15,17-18 | P1/P2/P4/P5/P7/P9/P10 in progress; other platforms, ports, drafts, Slack/webhooks, delegation, live workflows and the quality gate pending | external / large |
| docs/realignment/desktop-production-2026-10-26.md:11 | P3 specialist coordination Pending | large |
| docs/realignment/desktop-production-2026-10-26.md:78 | Google OAuth client ID absent; no accessible browsers/apps; acceptance pending authorization | external prerequisite |
| docs/realignment/desktop-production-2026-10-26.md:83 | Desktop GUI/bundle/install tests and non-Linux portability pending | external |
| docs/realignment/desktop-production-2026-10-26.md:89 | ADR 0021 navigation/context routing implementation pending | large |

Status drift in `docs/realignment/tests.md`: 106 test rows; the word "planned" appears on 3 lines (2
status-column rows: 39, 78), "partial" on 4, "unimplemented" on 2 (64, 80), "unverified" on 10.

## 4. Claim audit: README, website index, llms.txt, sitemap

| Location | Claim | Verdict |
|---|---|---|
| README.md:10,14,51,62-67 | development preview, no installers, source checkout only | Consistent with downloads.json (empty artifacts) and llms.txt:22 |
| README.md:175 | no user-facing mock model or simulated run; HUTCH_TESTING does not change product behavior | Verified by guards in section 1 |
| README.md:194 | bounded task delegation experimental | Consistent with tests.md:74-80 partial/planned |
| README.md:231 | computer use verified on KDE; personal desktop, GNOME, macOS/Windows not implemented | Consistent with website/index.html:830 |
| website/index.html:8 | links `downloads.json` as desktop release manifest | Manifest declares 4 platforms, every `artifacts` array empty (`downloads.json:9-38`); no download offered. Keep empty or remove the link if any download UI is added |
| website/index.html:791,799,812,843,953,997,1002 | installers not available yet / under development | Consistent with README:262, llms.txt:3,10,22 |
| website/index.html:813,820,828 | "fixture coverage" availability wording | Accurate; test-only data, no demo claim |
| website/index.html:822 | Full-Drive search and desktop file picker not implemented | Consistent with README:176 |
| website/index.html:830 | macOS/Windows executors, personal-desktop control, PTY, clipboard, Pi unavailable | Consistent with README:32,109 and safety.md:416 |
| website/llms.txt:3,10,11,22,26 | no installers, no install command, Linux only | Consistent; no stale mock/demo/coming-soon wording |
| website/llms.txt:9 | "single static page" | True (index.html is the only page; sitemap has one URL) |
| website/sitemap.xml:4-5 | one loc, lastmod 2026-10-28 | Fine; sitemap and llms.txt are clean |
| all website files | "coming soon" = 0, "mock" = 0, "demo" = 0 | No stale claims found |

Contradiction to reconcile: README.md:262 and llms.txt:22 say no installers exist, while
desktop-production-2026-10-26.md:9 records Ubuntu installed deb/AppImage webviews passing (built
locally, not published). P12 requires accurate download availability, so state "built, not published"
or publish the manifest. Dirty website files owned elsewhere: `website/index.html` (M), `app.css`
(M, generated), `src/input.css` (M), `THIRD_PARTY_NOTICES.txt` (M), 2 asset PNGs (M); `llms.txt`,
`sitemap.xml`, `downloads.json`, `robots.txt`, `site.js`, `styles.css` are clean.

## 5. Dashboard state coverage

Two surfaces: the SPA at `/` (`static/index.html` + `app.js`) and server-rendered `/bots`, `/bots/{name}`, `/runs`, `/runs/{id}`, `/usage`, `/approvals`, `/legacy/connections`.

| Page | Empty state | Loading/skeleton | Error banner | Permission-gated control | Asserted in tests |
|---|---|---|---|---|---|
| home/overview | home.html:10; _home_lists.html:18,49,74; app.js:7336-7338,7609-7623,7944-7948 | app.js:7614 (`role=status`), 7264 spinner | app.js:7609 `role=alert`; _wait.html:5 | paired-phone read-only limits (app.py:195-200) | test_browser.py:3313,6845,11612,11795,12172; wcag_measured_audit.py:368 |
| bots | bots.html:26; app.js:2345,2365 | first-run readiness app.js:3304; no roster skeleton | flash base.html:64 | model route required before run (app.js:8308-8309) | test_design_system.py:748; no e2e for "No bots yet" |
| bot detail | bot.html:59 "No runs yet"; app.js:7113,8545 schedules | app.js:7264 schedules | flash base.html:64 | browser handoff needs Linux display (bot.html:111) | none for empty runs state (gap) |
| run | n/a single run; live-stream spinner run.html:50 | run.html:50 | _events.html:42 error event; _wait.html:5 | approval/stop gates pages.py:480-504 | test_browser.py:2623; wcag_measured_audit.py:422 |
| runs | _runs_table.html:19 "No runs match."; app.js:13031 phone | app.js:7658 more/page busy | flash only | n/a | test_browser.py:2087; no error-state test (gap) |
| usage | usage.html:51 "No model calls" | none | flash only | n/a | test_browser.py:7104; no empty/error assertion (gap) |
| models | models.html:26 "No runtimes detected", :53-54 no models; app.js:10711 outage | none | models.html:12 notes, :103 price errors | route readiness gating app.js:3151,12278 | test_browser.py:4102,10777; no empty-state assertion |
| connections | connections.html:128; app.js:9967 | none | connections.html:46 flash; design_system 503 | ChatGPT sign-in disabled unless env gate (connections.html:24-25); terms ack :138 | test_browser.py:3521,4596; test_design_system.py:937 |
| approvals | _approval_list.html:4; app.js:7944-7948 | app.js:7944 | none server-rendered (gap) | phones allow-once/deny only (app.py:6092) | test_browser.py:7219,2284; no empty-state assertion |
| pair/login | n/a | n/a | pair.html:19, login.html:13 `role=alert` | owner-token sign-in host-only (pages.py:714) | test_browser.py:7446 |

No page lacks an empty state except non-list `run`/`pair`/`login`; no loading state on server-rendered bots, models, connections, usage, approvals (SSR; SPA views have loading copy); no error banner on server-rendered approvals, runs, usage. E2E tests asserting empty/error states: test_browser.py:3313,6263,11612,11795,12172;
test_wcag_measured_audit.py:368,422; test_studio_palette.py:80; test_channels.py:102 (503 inline
error); test_design_system.py:786,937,1416 (503); test_learning.py:73,133,201;
test_account_spending.py:88,100; test_conversation_navigation.py:64; test_task_pages.py:163;
test_browser.py:4124,10711. Server-rendered empty copy ("No bots yet", "No connections yet") is only
asserted in CLI/unit tests (`tests/test_cli.py:64,68,295,297`), never in e2e.

## 6. Pre-existing uncommitted files (owned elsewhere - do not edit)

`git status --porcelain` = 153 entries: 69 modified, 1 deleted, 83 untracked. All are another
session's brand/UI work; this audit's deliverable is the only new file it created.

- Modified templates (13): `_approval_card.html`, `_events.html`, `_home_lists.html`, `base.html`,
  `bot.html`, `bot_new.html`, `bots.html`, `connections.html`, `login.html`, `models.html`,
  `pair.html`, `run.html`, `runs.html`.
- Modified static (20) + deleted `composer.css`: `app.js`, `campaign-report.js`, `channels.js`,
  `composer.js`, `hutch.js`, `persona.js`, `skills.js`, `widgets.js`, `index.html`, and CSS
  (`controls`, `hutch`, `hutch-pages`, `model-switcher`, `skills`, `studio`, `style`, `ui`, `widgets`).
- Modified tests (9): 8 `tests/e2e/*` files plus `tests/test_workflow_usage_budget.py`.
- Modified website (6): `index.html`, `app.css` (generated), `src/input.css`, `THIRD_PARTY_NOTICES.txt`,
  `assets/github-social-preview-1280x640.png`, `assets/og-card-1200x630.png`.
- Modified brand/docs/config (13): `.pipeline/brand/2026-10/**`, `.gitignore`, `AGENTS.md`,
  `CONTRIBUTING.md`, `THIRD_PARTY_NOTICES.md`, `docs/brand-assets.md`, `docs/design-system.md`,
  `app/src/*.css`, `package.json`, `package-lock.json`, `pyproject.toml`, `desktop/icons/*`.
- Untracked highlights: `src/hutch/web/`, `src/hutch/server/static/redesign-preview.*`, new static
  CSS/JS/fonts/icons/manifests, `templates/_form.html`, `_message.html`, new e2e tests and scripts,
  `docs/agent-workflow.md`, `docs/concurrent-agents.md`, `docs/prompts/`, `docs/repository-hygiene.md`,
  `docs/validation-queue.md`, `docs/realignment/completion-plan.md` (another teammate's file),
  `reports/`, `research_notes/`, `tree.json`, `hig-app-icons.*`, `tsconfig.json`.

Dirty in this audit's read scope: templates, static JS, e2e tests, website/index.html (above). Target docs (`bot-config.md`, `operations.md`, `safety.md`, `realignment/tests.md`, desktop-production doc, `README.md`, `website/llms.txt`, `sitemap.xml`, `downloads.json`) are clean, so edits there will not collide.

## 7. Top actionable findings

1. No user-visible demo data ships: primary UI has no demo bots/runs, no fake counts, no lorem, and
   the strings that exist are refusals or anti-demo copy (templates/home.html:11, bots.html:26,
   bot_new.html:7). Treat "demo cleanup" as done except the items below.
2. Mock runtime is not selectable anywhere and is refused before execution
   (modelchoices.py:379-380, runtime/__init__.py:22-23, engine.py:357, doctor.py:180), with an e2e
   regression test (test_browser.py:10777). Only follow-up: reword legacy `pages_usage.py:33` billing
   label (small).
3. `/static/redesign-preview.html` is reachable by URL while unlinked and uses synthetic fixtures
   (`fixtures.ts:1-20`, `bot-fixtures.ts:1-11`); exclude it from packaged static or document it (small).
4. Two live UI surfaces: SPA at `/` and server-rendered templates. The old v0.1 shell comment says
   to delete `static/app.js|index.html|style.css` once unused (pages.py:182); decide whether legacy
   server-rendered routes are in scope (large if removed, small if documented).
5. Missing e2e empty-state assertions for server-rendered bots, usage, models, approvals and for the
   "No connections yet" copy (empty copy is only asserted in tests/test_cli.py today) (small).
6. Missing error-state assertions for server-rendered runs, usage, approvals; SPA error states are
   well covered (test_browser.py:11612,11795,12172; test_design_system.py 503 cases) (small).
7. README/llms vs desktop-production availability: state "built locally, not published" between
   README.md:262, llms.txt:22 and desktop-production-2026-10-26.md:9 (small).
8. `website/index.html:8` advertises a downloads manifest whose platform artifact lists are empty
   (`downloads.json:9-38`); keep it metadata-only or drop it before download UI appears (small; owned elsewhere).
9. Doc status drift: tests.md has 2 planned rows, 4 partial and 2 "unimplemented" rows while the desktop
   checkpoint marks P3 "Pending"; reconcile labels so the ledger is the single status source (small).
10. "Permanent scoped deletion" repeats in README.md:169, bot-config.md:24,32, operations.md:489 and
    tests.md:64; track it once (large implementation, small docs consolidation).
11. Test-only coupling is clean: `src/` imports no `tests/` module, so no production fixture leak.
12. Permission gating exists where expected (env-gated ChatGPT sign-in connections.html:24-25,
    browser handoff bot.html:111, runtime switch app.js:8308-8309, pair approval app.py:6092); no
    ungated privileged control was found in the audited surfaces.
