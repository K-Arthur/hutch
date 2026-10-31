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
- Two `tests/e2e/test_route_state_boundaries.py` cases and one `test_wcag_measured_audit.py` case
  fail at baseline as well (a stub `ModelsView` without `hw`; a form field 44 px against a button 40 px).
- **Not run:** a live-model first-request journey; a live OpenCode install of the background service
  (the browser tests use labelled fixtures, because a real install writes a systemd unit); a
  screen-reader pass; axe-core; macOS and Windows anything; `cargo build` and native installers;
  physical-device phone validation.
- **Not made on purpose:** a populated-dashboard capture for the public site. `PRODUCT.md` requires
  marketing captures to come from the actual empty first-run product.
- **Header chrome (C5) is still not unified.** Server pages keep an always-visible Stop all and a
  "live" chip and put the title in the body; the app shows work status and puts the title in its
  header. Tracked in the progress file.
- A running run whose owner process exited shows "Working" until the next supervisor beat, then
  "Failed" with an `interrupted` reason; there is no distinct "Interrupted" chip.
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
