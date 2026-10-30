# Repository hygiene audit — 2026-10-26

This audit changed ignore rules, Python package selection and optional local commit checks.
It did not commit, push, rewrite history, remove local data, untrack evidence, install hooks,
change Git configuration or modify the concurrent CI/application work.

## Assessment

The existing ignore file already covered Python installs, Rust/Tauri build output, npm
dependencies, ordinary logs and browser test output. Missing rules left local environment
files, SQLite sidecars, parallel coverage files, plugin pointers, font caches and the server
PID eligible for accidental addition. The unanchored `build/` pattern also hid a prospective
`src/hutch/build/` source package. `.python-version` was hidden despite its reproducibility role.

The inspected tree has Python 3.11+, uv/Hatchling, FastAPI, pytest/Hypothesis/Playwright,
Tailwind/daisyUI via npm, and two Cargo projects for a Rust/Tauri desktop host. PyInstaller
freezes the Python backend. GitHub Actions runs Python/browser/benchmark checks and a manual
native-platform matrix. The npm package is private. No Docker configuration, npm publication,
mobile/WASM build, bundled model weights or Git LFS setup was found. Optional models, browser
profiles, credentials and downloads belong to Hutch's external state, not this source tree.

At the initial inventory there were 3,161 tracked files, about 384 MB of tracked documentation
and 1.54 GiB of Git packs. Historical blobs total about 2.52 GB uncompressed, including 2.01 GB
under docs. The largest current file is an 11.8 MB browser trace; the largest historical blob
is a 14.7 MB trace. Seventy-two groups of identical tracked files larger than 1 KiB contain
about 6.02 MB of repeated bytes, largely screenshots at distinct evidence paths. Removing
these would break evidence references for little benefit; no deduplication was performed.

Generated shipping CSS, desktop icons, JSON/Markdown evidence fixtures and benchmark baselines
are intentional inputs. In particular, `tests/test_workflow_document_research_acceptance.py`
loads `docs/realignment/artifacts/dynamic-workflows/document-research.plan.json`, and browser
tests load `docs/realignment/artifacts/workflow-studio/phone/visual-review.md`. Ignoring or
removing the artifact directory wholesale would break supported tests.

There was no staged work at audit start. Two test files were initially modified, and further
CI, documentation, application and test edits arrived concurrently. Those changes were left
alone. There are no tracked nested ignore files or `.gitattributes`; local Hypothesis and
ZCode workflow caches have their own ignore files. `.git/info/exclude` additionally excluded
worktrees and local Impeccable state. No active Git hook or configured hook path was found.
The existing `.gitleaksignore` contains 111 exact reviewed historical fingerprints.

## Classification and decisions

States describe the initial inventory unless a transition is shown. Risk describes changing
the treatment without reviewing its role.

| Path or pattern | Current state | Recommended action | Reason | Risk |
| --- | --- | --- | --- | --- |
| `src/hutch/`, `app/src/`, `website/` sources | Tracked | Keep | Application, styles and static site inputs | High |
| `uv.lock`, `package-lock.json`, both `desktop/**/Cargo.lock` | Tracked | Keep | Frozen Python/native CI and reproducible frontend installs | High |
| `src/hutch/server/static/ui.css`, `model-switcher.css`, `website/app.css`, `styles.min.css` | Tracked, generated | Keep | Wheels/site ship these without a runtime npm build | High |
| `desktop/icons/`, `desktop/web/`, `desktop/backend.spec` | Tracked | Keep | Native startup, packaging artwork and freeze recipe | High |
| `src/hutch/data/oauth-apps.json` | Tracked | Keep | Public application-ID manifest; schema rejects private credentials | High |
| `tests/fixtures/*.db.fixture`, `*.db.json` | Tracked | Keep | Intentional persisted-state compatibility fixtures | High |
| `benchmarks/baselines/*.json` | Tracked | Keep | Canonical comparison data, distinct from scratch results | Medium |
| `docs/**/artifacts/**/*.json`, `*.md`, images | Tracked | Keep | Evidence and some executable test inputs | Medium |
| 21 `docs/realignment/artifacts/**/*.log` files | Tracked, matched old ignore | Keep; now explicit exception | Reviewed evidence, distinct from runtime logs | Medium |
| 120 tracked `docs/**/artifacts/**/*.zip` files | Tracked; match new ignore | Keep existing; review storage policy | Trace evidence contains DOM/network data; no automatic untracking | Medium |
| `docs/realignment/artifacts/settings-disclosure-axes-2026-10-10/trace-failed.zip` | Untracked → ignored | Ignore | Raw failed browser capture; separate redacted scan had no candidates | Low |
| `.venv/`, `node_modules/`, `desktop/target/`, `desktop/process-guard/target/` | Ignored | Keep ignored | Installed dependencies and native intermediates | Low |
| `desktop/binaries/`, `desktop/gen/`, `/build/`, `/dist/` | Ignored | Keep ignored | Recreated package/schema output; source `build/` directories now visible | Low |
| `.hypothesis/`, `.coverage.*`, notebook checkpoints | Ignored or missing explicit rules | Ignore | Generated test state; root rules work in fresh clones | Low |
| `.state/`, SQLite databases and their WAL/SHM/journal files | Ignored or missing sidecar rules | Ignore | Runtime state may contain transcripts, credentials or personal data | High |
| `.env`, `.env.*`, `.aws/`, `.ssh/` | No real credential files found in candidate source | Ignore | Future credential protection; examples remain eligible | High |
| `.env.example`, `.env.sample`, `.env.template`, `.python-version` | No such tracked files currently | Keep eligible | Placeholder configuration and shareable interpreter selection | Low |
| `serve.pid`, `var/cache/fontconfig/` | Untracked → ignored | Ignore | Observed server and font-renderer scratch output | Low |
| `.v2c/plugin_root`, `.video_agent/plugin_root` | Untracked → ignored | Ignore | Machine-specific plugin pointers | Low |
| `.codex/hooks.json`, `.opencode/commands/impeccable.md` | Untracked | Review; remain visible | Potentially shareable tooling configuration, not blanket-ignored | Medium |
| `reports/`, `research_notes/`, tracked `.zcode/plans/` | Untracked notes / tracked plans | Review; preserve | Meaningful research or collaboration material, excluded from sdist | Medium |
| `.impeccable/config.json`, design/surface records | Tracked | Keep | Shared design decisions; local cache exclusions remain local | Medium |
| `.worktrees/` | Locally ignored → shared ignore | Ignore | Nested checkouts must not enter source packages | Low |

## Implemented safeguards

`.gitignore` now separates Python, native and frontend output; anchors root packaging paths;
removes the interpreter-version exclusion; adds observed runtime/test/local credential rules;
and preserves sample environment files and reviewed logs. New documentation ZIP captures are
ignored, while all existing tracked archives remain tracked. There are no index-only removals:
no tracked candidate was proven disposable without affecting intentional evidence.

Hatch package selection is explicit. The sdist uses an allowlist of project source,
configuration, tests, docs, scripts, native/frontend inputs and locks. Shared build exclusions
protect nested local environment/state files, native build output and raw browser archives,
including when rebuilding an extracted source package without Git metadata. An isolated
baseline build demonstrated synthetic `.env`, agent, worktree, research and font-cache files
entering the old archive; final validation checks their absence. Documentation JSON/Markdown
fixtures, images and shipping CSS remain included. This does not change Git tracking.

`scripts/check_repo_hygiene.py` reads staged blobs and rejects ignored paths (including forced
additions) and changed blobs over 5 MiB. It does not read secret values or alter the index.
Unchanged historical evidence is grandfathered. `.githooks/pre-commit` optionally runs that
check and Gitleaks; installation is documented in `CONTRIBUTING.md`. No dependency was added
to Python/npm/Cargo and no existing hook was overwritten. Missing Gitleaks fails the opted-in
hook explicitly. Review an intentional exception in policy rather than bypassing the hook.

## Security findings and limits

- **Future tracking/packaging:** missing credential exclusions and demonstrated source-archive
  canary leakage were addressed. These were potential exposure paths, not confirmed live keys.
- **Staged exposure:** the real index was empty at the start and was not changed by this task.
- **Current source:** Gitleaks 8.30.1 scanned an isolated copy of tracked source at the initial
  audit snapshot, including ZIP
  entries. Its 82 generic candidates were triaged: 70 lines exactly match reviewed historical
  fingerprints; 12 archive `effect_key` values are SHA-256 digests. The implementation is in
  `src/hutch/action_receipts.py` and `src/hutch/store.py`. No new suppression was introduced.
- **Untracked source:** a separate redacted scan found no candidates. The now-ignored raw failed
  trace was scanned separately with archive traversal and also had no candidates. The observed
  root `.aws/` directory was empty; no real `.env` or private-key filename was found in the
  candidate source inventory. Installed dependencies, unrelated scratch state and private
  home credential stores were not indiscriminately scanned.
- **History:** the initial all-local-refs scan at `a483281b286fccaf8f5f4e47f8578fd04f7035cf`
  covered 1,125 commits. Concurrent work then advanced HEAD; the final all-local-refs rescan
  at `438202d9e6586cbc0cad277eec557783d4ba6066` covered **1,126 commits, 31.05 MB** of textual
  patch data with **no unsuppressed findings**, using the unchanged exact historical allowlist.
  Git patch scanning does not establish archive safety.
- **Historical archives:** rescanned the existing extraction of all 571 historical ZIP objects:
  8,622 unique UTF-8 text payloads, 446,919,440 bytes. Verified extracted content hashes and
  equality of the historical ZIP object set. The 84 candidates exactly match the previously
  reviewed archive set: 76 effect-identity hashes, one tokenizer-profile hash and seven
  synthetic fixture-boundary prose occurrences. See the earlier
  [public source review](realignment/artifacts/desktop-production-2026-10-26/public-source-review.json).

No real credential exposure was confirmed and no rotation is prescribed without such evidence.
Scanners do not prove the absence of credentials or personal data; binary screenshot contents,
arbitrary private configuration and remote/unfetched refs remain outside that assurance.
If a real leak is identified, revoke/rotate first, assess exposure, and separately authorize
coordinated history cleanup. Ignore rules cannot remove committed history or recalled clones.

## Validation

Detailed sanitized local logs are under `.validation/repository-hygiene/` during the task;
large build trees and synthetic probe repositories are removed after verification.

- 38 hygiene regression cases passed; the combined hygiene, site-token and document-workflow
  batch passed **47 tests**. Tests use disposable repos, preserve local files and check the
  staged version rather than unstaged replacements, renames and unusual filenames.
- Real `git check-ignore --no-index` probes verified credentials, sidecars, caches, traces and
  output exclusions. Negative probes and actual additions in disposable repos verified samples,
  locks, fixture extensions, shipping CSS and `src/hutch/build/source.py` remain trackable.
- Hook probes passed clean content and rejected both a random unissued token-shaped string and
  forced `.env` staging. A repetitive low-entropy token-shaped probe was not detected initially;
  this illustrates scanner limits rather than proving arbitrary token detection.
- `uv lock --check --offline`, `npm ls --depth=0`, locked offline Cargo metadata, the CSS
  production build in a disposable checkout and `hutch --help` were exercised.
- Python source archive, wheel-from-source-archive, isolated wheel installation and resource
  checks passed explicit synthetic private-file and required-resource assertions. The comparable
  source archive shrank from **348,383,797 to 173,790,106 bytes (50.1%)**; the wheel is
  **2,799,305 bytes**. Root/nested placeholder examples remain included; root/nested private
  canaries, native targets, worktree, agent, research and font-cache canaries are absent.
- `git diff --check`, staged-state inspection and final status checks preserve concurrent work.
  No full application/browser suite or native installer build was required for this change;
  application behavior and UI source were not changed by this task. No network-fresh dependency
  reinstall, remote CI run, secret revocation or history rewrite is claimed.

## Follow-up priorities

1. Use the optional hook and consider running the same checks in CI with the project's existing
   public-only execution policy. Hooks remain bypassable; no remote branch protection or
   platform secret-protection setting was changed here. CI was changing concurrently.
2. Review future traces before retention. Prefer bounded sanitized JSON/Markdown plus selected
   screenshots in Git; use release/external storage for bulky raw captures if retention needs
   it. Moving the 120 existing archives requires updating references and an explicit decision.
3. The existing 1.54 GiB pack footprint remains: ordinary ignore/untracking does not reclaim
   history. A coordinated rewrite would affect every collaborator and public clone; do not
   perform it merely to save several megabytes of duplicated screenshots. Git LFS was not
   enabled: migration, hosting quotas and clone/build behavior need a separate decision.
4. Keep personal editor preferences in global ignores or `.git/info/exclude`; avoid blanket
   exclusions for agent configuration, research, assets, certificates, fixtures or lockfiles.

## Official conventions checked

- [Git ignore semantics](https://git-scm.com/docs/gitignore): tracked files are unaffected,
  deeper rules override parents, and a file cannot be re-included under an excluded parent.
  These explain common failed negations and why `--no-index` is needed for staged-file probes.
- [Hatch file selection](https://hatch.pypa.io/latest/config/build/): inclusion/exclusion and
  VCS handling are packaging concerns. The extracted-source canary test is the practical
  check; Git ignoring alone is insufficient assurance for a release archive.
- [uv project layout](https://docs.astral.sh/uv/concepts/projects/layout/),
  [Cargo locks](https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html) and
  [npm locks](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/): committed
  lockfiles preserve dependency resolution; installed environments and dependency trees do not.
- [Playwright traces](https://playwright.dev/python/docs/trace-viewer) capture DOM and network
  evidence, explaining their size and privacy risk. [Gitleaks](https://github.com/gitleaks/gitleaks)
  documents redaction and opt-in archive traversal; text-history scans alone miss archive data.
- [Tauri development](https://v2.tauri.app/develop/) and the actual desktop build configuration
  distinguish source/configuration/icons from target, schema and backend bundle output.
