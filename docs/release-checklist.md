# Release checklist (development preview)

Written 2026-10-30 at the end of the release-readiness run. Nothing here was published, tagged,
signed, deployed or pushed. Hutch stays a **development preview**: Linux source checkout only, no
packaged desktop installer, no hosted service, no PyPI package. Evidence and the full slice log are
in [`docs/realignment/release-readiness-progress.md`](realignment/release-readiness-progress.md); the
final gate run is recorded in [`docs/realignment/ledger.md`](realignment/ledger.md).

## 1. Verified in this run

| Item | How it was checked | Result |
|---|---|---|
| Version is consistent | `pyproject.toml`, `src/hutch/__init__.py`, `package.json`, `desktop/tauri.conf.json`, `desktop/Cargo.toml`, `hutch version` | `0.1.0` everywhere |
| Licence and notices | `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md`, `SECURITY.md` (private reporting path), `docs/README.md` all tracked; wheel and sdist metadata inspected | present |
| sdist and wheel build | `uv build` | `hutch-0.1.0.tar.gz` **8.3 MB, 1,862 files** (it was 267 MB until evidence screenshots under `docs/` were excluded; `tests/test_packaging_config.py` guards it), `hutch-0.1.0-py3-none-any.whl` 3.2 MB |
| Install into a fresh venv | wheel plus its declared dependencies installed into a throwaway venv (the registry was read; no dependency was added or changed) | installs |
| `hutch init`, `hutch doctor`, `hutch version` from the installed wheel | scratch state directory | `doctor`: "everything checks out" |
| `hutch serve` from the installed wheel | port 8798, scratch state, urllib and Chromium | `/`, `/models`, `/usage`, `/api/health`, new static modules 200; `/legacy` 404; `/overview` and `/runs` 302 to the canonical hashes; 7 routes at 1440 and 360: 0 console errors, 0 page errors, 0 failed requests, 0 px overflow |
| One title format `<View> — Hutch` | `tests/test_page_titles.py`, `tests/e2e/test_page_titles.py` | passing |
| Fresh state, every destination, three widths | `tests/e2e/test_fresh_state_routes.py` (15 routes at 1440, 900, 360) | 45 passed |
| Activity merge and redirects | `tests/e2e/test_activity_destination.py`, `tests/test_navbar_consistency.py` | passing |
| Controls have backends | `tests/test_ui_endpoints_exist.py` (about 290 SPA API calls and every template form) | no dangling control |
| One vocabulary | `scripts/audit_ui_vocabulary.py`, `tests/test_ui_vocabulary.py` | clean |
| Public docs link only to tracked files | `tests/test_docs_links.py` | passing |
| Emoji audit | `python scripts/audit_emoji.py` | clean |
| `check:agent` from a fresh clone | `npm run check:agent` in a `git clone` | all four gates pass |
| Full non-browser suite from a fresh clone | `pytest -q --ignore=tests/e2e` at `52b6f26d` | 4,247 passed, 63 skipped, 3 xfailed, 2 timing failures that pass alone twice; details in the ledger |

Browser environment for every browser result: Chromium 153.0.8010.12 (Playwright 1.63.0), Linux. No
Docker parity is claimed.

## 2. Known failing, not run, or limited

- **19 tests in `tests/e2e/test_browser.py` fail at the pre-change baseline `3bcbe454`** and still
  fail. They are not regressions from this run, and each needs a decision (fix the control or the
  test): memory export (phone), usage limits, chat choice question, conversation file browser empty
  state, coordinator specialist dispatch, Gmail local grant, Google Calendar event creation scope,
  KDE Connect device access (1440 and 390), restored state (phone), routine editor workflow link,
  scoped fact review (phone), tool permissions, virtual passkey over HTTPS, workflow amendment
  preview adoption, workflow amendment drain control, workflow question draft after a TCP
  disconnect, workflow studio pending questions, workflow studio policy steps. Several assert a 44 px
  touch target against a 40 px control.
- `tests/e2e/test_skills_browser.py::test_bot_skills_assignment_and_readiness[390-844-phone]` fails at the pre-change
  worktree too (a skill checkbox is 16 px against a 20 px assertion; the shared design-system checkbox is 16 px inside a
  44 px row), so a design-system decision, not a regression.
- Two `tests/e2e/test_route_state_boundaries.py` cases and one `test_wcag_measured_audit.py` case
  fail at baseline as well (a stub `ModelsView` without `hw`; a form field 44 px against a button 40 px).
- **Not run:** a live OpenCode install of the background service (the browser tests use labelled
  fixtures, because a real install writes a systemd unit); a screen-reader pass; axe-core; macOS and
  Windows anything; `cargo build` and native installers; physical-device phone validation. (A live
  free-route model journey **was** run on 2026-10-30: see section 3b and the progress slice log.)
- **Not made on purpose:** a populated-dashboard capture for the public site. `PRODUCT.md` requires
  marketing captures to come from the actual empty first-run product.
- The 19 `test_browser.py` failures above were not re-triaged in the platform follow-on run; the
  focused browser modules that run touches were re-run instead.
- Python-sourced API error strings that the app shows (for example "Bot settings") still say "bot".

## 3. Needs the owner

| Decision or action | State found |
|---|---|
| **Push `main`** | Local `main` is 148 commits ahead of `origin/main` (merge base `8db7f28e`); `origin/main` has one doc commit (`f222a21d`) that local does not. Nothing was pushed. |
| **CI** | The latest CI run on the published `origin/main` concluded `failure`. The current local tree has never run in CI; its nearest evidence is the fresh-clone suite above. Watch the first run after a push. |
| **PyPI name** | `hutch` returned 404 on PyPI on 2026-10-30, so it appears free but is not reserved. Publishing is the owner's call. |
| **GitHub release** | `v0.1.0` exists as a prerelease with no assets, consistent with "no installers". Replace or retire it deliberately; the README badge links to it. |
| **Signing** | None done. macOS notarization, Windows signing and Linux packaging are all open. |
| **Hosting** | The static site (`website/`) deploys from GitHub Pages; the refreshed captures and copy are in the tree but not deployed. |
| **macOS and Windows** | Executors are not implemented; the README says so. |
| **Product decision** | `archive/agent-connections-2026-10-11` (63 commits: skill ZIP import, versioned effective configuration, persisted assistant identity, others) is preserved at a tag, not merged. |
| **Housekeeping** | Seven worktrees whose branches are merged still carry uncommitted edits (see `unmerged-branch-triage-2026-10-30.md`); `~/.hutch-tmp/hp26` (14.8 GiB, three registered worktrees) was not examined and was deliberately not pruned. |

## 3b. Platform follow-on run (2026-10-30, after the release-readiness run)

The owner reviewed the running product and asked for one named main assistant, presets as a reviewed
catalog, and no demo or fixture content. That work is committed on `main` after this checklist's first
gate run; the slice log is the "Platform work after the gap analysis" table in the progress file. What is
now true and how it was checked:

| Item | How it was checked | Result |
|---|---|---|
| No demo content in the product | `tests/test_no_demo_content.py`: no canned starter prompts anywhere in `src/` (Python and templates included), `mock` may only shrink per file and now appears only in migration/refusal code, a fresh install starts with zero assistants, no template points at a fixture or evidence tree | clean; the browser no longer names the retired route at all (roster/chip/workspace default read the server's `route_problem`) |
| One header contract | `tests/test_server_shell_parity.py`, `tests/e2e/test_one_header_contract.py`, updated overlay/type tests | every chrome server page (Models, Usage, assistant, Connections, both deletion pages) puts its h1 in the shell header; work status and the global Stop all appear only while work runs; header grows at 200% text zoom |
| Interrupted runs say so | `tests/test_orphaned_run_display.py`, `tests/e2e/test_interrupted_run_status.py` | a failed run with `exit_reason=interrupted` reads "Interrupted" in Task details, Activity rows and cards; a plain failure still reads "Failed"; `/api/overview` carries the reason |
| One named main assistant | `tests/test_main_assistant.py`, `tests/e2e/test_identity_review.py` | the first assistant created is the main assistant when none is set (and an existing choice is kept); it carries an icon badge, not a text tag; a main assistant must be a local owned assistant |
| Reviewed identity | `tests/test_identity.py`, `tests/test_identity_api.py`, `tests/e2e/test_identity_review.py` | one workspace "About you" profile and one bounded identity per assistant (sign-off, up to 8 boundaries) as 0600 JSON with revision CAS; rendered into the system prompt as advisory context; damaged files are reported and never applied; review-before-save from assistant Behavior and workspace Settings |
| First request guidance | `tests/test_onboarding_page.py`, `tests/test_onboarding_chooser.py` | the first-run form and empty-chat welcome explain outcome, sources, constraints, hand-back and when to stop and ask — copy, not invented prompt buttons |
| Presets are catalog data | `tests/test_catalog.py` | the eight presets moved losslessly to `src/hutch/data/catalog/*.json` with publisher, version and content hash; `templates.py` builds the old CLI/API/dashboard shapes from the data |
| Catalog destination | `tests/e2e/test_catalog_destination.py` | a reachable searchable Catalog page with provenance, permissions, instructions and "Create a copy" that opens the normal setup review; 1440/900/360 with 0 overflow and 0 console errors |
| Sharing is checked | `tests/test_catalog_export.py`, `tests/e2e/test_catalog_destination.py` | export runs a checklist (credentials block; URLs, e-mail, absolute paths warn), lists what is never included and only downloads after review; catalog JSON import pre-fills the same reviewed setup draft |
| Sources are pinned | `tests/test_catalog_sources.py`, `tests/test_catalog_api.py` | local-folder and static-URL sources, explicit fetch only (netguard-bounded), entries inert until their exact manifest hash is trusted; changed content drops trust |
| A new person starts on a real route, with the cost said | `tests/test_starter_route_js.py` (the real `starter-route.js` under Node), `tests/e2e/test_starter_route.py` (7) | most private first: a ready model on this computer, then a provider the person connected, then a free OpenCode model (an unconnected profile is all free; once connected only models named free count; paid is never a free start). A hosted starter always shows a notice (leaves the computer; free hosted models can keep or learn from it; where to change it). Only **preselected**: nothing is saved until the assistant is created. A second assistant reuses the main assistant's route with no detection. With no OpenCode tool, first run says what to install (OpenCode for a free model, Ollama to stay private) |
| Every page checked, one overlap merged | [`docs/realignment/page-audit-2026-10-30.md`](realignment/page-audit-2026-10-30.md); `tests/e2e/test_skills_browser.py`, `test_page_titles.py`, `test_fresh_state_routes.py`, `tests/test_navbar_consistency.py` | 17 captures at 1440 and 360 px, 0 console errors. Skills is now a view of the Catalog (one trust model, one store; `#/skills` redirects; ten sidebar destinations became nine). An interrupted run says it was cut short and what to do; Skills says where it found skills |
| Review of the previous agent's work: fixes | `tests/test_recovery_settle.py` (4), `tests/test_catalog_sources.py` and `test_catalog_api.py` (+7), `tests/test_no_demo_content.py` | recovery settles an unverifiable cleanup as `outcome_unknown` only when nothing known to be alive is abandoned and the host can inspect processes (before: any second attempt closed the records, failing open); a URL catalog manifest must match the hash and id its index published, entry ids are validated before any file read, a source file edited into an invalid manifest is a 422 not a 500, local entries are found by the id inside the file; the `mock` allowlist and the overview test were restored |
| Deleting an assistant erases its identity file | `tests/test_bot_deletion.py` (the managed-files test now seeds `identity/assistant-<id>.json` and asserts it is erased while another assistant's and the workspace profile survive), `tests/e2e/test_bot_deletion_ui.py` (9) | sign-off and boundaries are listed in the deletion preview (managed files 6 to 7) and removed by the governed plan; found in review of the identity work |
| Live free OpenCode route | real OpenCode 2.2.0 private profile from a scratch state directory; `hutch run` CLI, the product HTTP server and a real Chromium chat journey | **verified 2026-10-30.** The private profile exposed 8-9 free models (`opencode/opencode/deepseek-v4.1-flash-free`, `glm-5.3-flash-free`, `big-pickle`, `flint-40b-free`, `beam-free`, `mimo-v2.6-flash-free`, `nemotron-3.5-*`, `nemotron-3-ultra-free`) with `authenticated: false`, and `/api/v1/opencode/status` reports `ready: true`. Two blocking CLI runs succeeded on two different free models (`deepseek-v4.1-flash-free`: 4,411 tokens, $0.00; `glm-5.3-flash-free`: 4,187 tokens, $0.00), each with `hutch runs verify` exit 0 and the exact requested reply; a product-server run and a real-browser SPA chat run (`deepseek-v4.1-flash-free`: `run_8b83db012b63` succeeded/completed, 4,415 tokens, $0.00, assistant bubble `HUTCH-BROWSER-OK`, 0 console errors, 0 overflow); the fresh-state first-run page detects it live ("OpenCode is ready with 8 model options. Its available models can be used without a separate account"). Evidence: `.dsh/long-horizon/hutch-platform/artifacts/live-opencode-{free-route,product-http,browser,first-run}.json` plus screenshots in the isolated artifact root |

Still open after this run:

- **Owner decisions:** fold Tasks into Activity (D2) and Runtime plus Settings > Installation into Scheduled work (D3);
  both change what the main assistant's Tasks board and the machine-health page are (see the page audit).
- Proposals and delegation (A2, A3, A6); the onboarding step that *requires* a verified completion before the first
  assistant exists (A7: the route and a real completion are verified, the gate is not built); per-task
  sandbox/branch isolation (D2 in the gap analysis); marketplace publishing, scanning, revocation and reporting
  (B5-B7, B10); distribution (E); the visual backlog (F2-F6).
- The `/onboarding` chooser still ends at "Saved on this machine. Hutch has not connected to this route yet" when
  nothing is detected; replacing that detour with one "install or connect one of these" page is the next
  simplification of model selection.
- Small redundancies recorded in the page audit: Activity's two stat tiles and usage accordion (pinned by frozen
  tests), and five "Not enabled in this build" cards on Apps & AI.

## 4. Reproduce

```bash
git clone https://github.com/K-Arthur/hutch.git && cd hutch     # or this checkout
uv sync --extra dev --extra browser
npm run check:agent
uv run --frozen --no-sync pytest -q --no-header --tb=line --ignore=tests/e2e   # about 21 minutes
uv run --frozen --no-sync python scripts/audit_emoji.py
uv build                                                                          # sdist and wheel
```

Browser journeys need the Playwright Chromium build; record `playwright` and Chromium versions with
any result. After any browser run, check `git status` for changes under `docs/**/artifacts` and
`docs/onboarding/evidence`.
