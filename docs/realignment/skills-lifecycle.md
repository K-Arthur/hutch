# Skills lifecycle — implementation and verification record (2026-10-10)

Workstream: agents / skills / customization / integration connections — the Agent Skills slice.
Base: `f2b8b00`, rebased onto the concurrent hardening commit `a2106ec`; all work done in the
detached worktree `.worktrees/skills-lifecycle` to avoid colliding with the active session that
owned the shared checkout. No push, no publication.

Commits (in order):

| Commit | Change |
|---|---|
| `60ca912` | Skills lifecycle core: discovery, validation, registry, trust (`src/hutch/skills.py`, samples, `tests/test_skills.py`) |
| `ec1812e` | Built-in runtime wiring, run snapshots, fail-closed activation (`engine.py`, `runtime/builtin.py`, `tools/skill.py`, `tools/base.py`, `tools/__init__.py`, `models.py`) |
| `40ce3b4` | API + readiness resolver + Bot binding + CLI (`readiness.py`, `server/skills_api.py`, `server/app.py`, `cli.py`) |
| `d8e12d1` | UI: library, review inspector, Bot panel, composer picker (`static/skills.js`, `static/skills.css`, `index.html`, `app.js`, browser tests + captures) |
| `af34be3` | Template identity collision + template-tool override fixes; docs (`templates.py`, `pages.py`, `README.md`, `CHANGELOG.md`, `docs/skills.md`) |
| `2d2d346` | Listing fast path (stat signature), stale-render fix, bounded soak |
| `bb6d009` | Refreshed evidence captures |

## What was already working vs. what this slice added

* **Already working (verified, not rebuilt):** Bot lifecycle, templates/presets, model routes and
  Connections, approvals and policy, memory, schedules, workspaces, provider/credential routing,
  transcript integrity, delegation machinery. The audit found no skills subsystem in the product:
  the only "skill" references were in the OpenCode coding-handoff docs.
* **Added:** the complete skills lifecycle — discover → import → validate → review/trust →
  install/version → assign → activate → inspect → update/rollback → disable/uninstall — with a
  backend resolver shared by the run path and the UI, a CLI, API resources, three bundled sample
  skills, and a Bot readiness resolver.

## Audit findings turned into fixes (agent-configuration slice)

1. **Template identity collision (real bug).** `TEMPLATES[key].model_copy(deep=True)` kept the
   template singleton's Bot ID; creating two Bots from one template in a process raised
   `BotConflict: bot already exists`. Fixed with `templates.instantiate()` used by API, dashboard
   and CLI; regression covers two template Bots with distinct IDs.
2. **Template tool override (real bug).** `BotCreate.tools` defaulted to `["shell","files","memory"]`,
   so a template create that omitted `tools` silently discarded the template's tool list (CLI and
   API). Now: omitted keeps the template's tools, explicit list replaces, explicit `[]` selects
   none. Regressions cover all three on both routes.
3. **Explicit-empty semantics verified.** Explicit `tools: []`, `skills: []` and empty CLI lists
   persist as empty; they are not coerced back to defaults.
4. **Readiness was absent.** `GET /api/v1/bots/{ref}/readiness` now separates runtime / model /
   tools / skills / connections, marks blocking `missing` vs visible `warning`, and never calls a
   provider.
5. **`_client_config()` / `_client()` (assignment hypothesis).** No such functions exist in this
   codebase; the analogous credential-routing logic lives in `providers/` + `connections.py` and
   was under active concurrent ownership. Left untouched; the host-scoped credential tests in
   `tests/test_credential_routing.py` remain the evidence for that area (unchanged, passing).

## Security model (enforced, not just documented)

* Installation is inert; only an operator trust decision on one exact content hash enables a skill.
* Run start re-reads and full-hashes every bound package; a change after review withholds it with a
  visible reason. A same-size edit with a restored mtime is caught at run start even though the
  listing's stat fast path cannot see it (regression test).
* Explicit activation is validated at submit (bound + trusted + enabled) and again at start;
  revocation in between fails the run (`skill_unavailable`) instead of running with different
  instructions. Assigned-only skills are excluded with a run-log warning.
* `allowed-tools` frontmatter is informational; tool exposure comes only from the Bot document.
  `use_skill` is enum-constrained to the run's resolved catalog, returns untrusted-labelled text,
  re-verifies the hash, and reads resources confined to the package directory (64 KiB, UTF-8).
* The registry is written atomically (0600) under a cross-process `flock`; installs reject
  symlinked packages/entries, path escapes, >2 MB files, >20 MB packages, >2,000 files.
* Skill bindings are part of the engine capability snapshot, so delegated children cannot gain
  newer bindings through delegation.

## Verification (exact commands, actual results)

| Check | Command | Result |
|---|---|---|
| Skills core | `.venv/bin/python -m pytest tests/test_skills.py tests/test_skill_runtime.py tests/test_skills_api.py -q` | **74 passed** (after the review fixes) |
| Full offline suite (on the rebased tree) | `.venv/bin/python -m pytest -q --ignore=tests/e2e` | **1685 passed in 550.64s** |
| Concurrent agent's new suites with mine | `pytest tests/test_bot_stats_scaling.py tests/test_capacity_procs.py tests/test_bounded_file_read.py tests/test_dispatch_fairness.py` + skills suites | **70 passed** |
| Browser journeys | `.venv/bin/python -m pytest tests/e2e/test_skills_browser.py -q` | **6 passed** (Chromium 153, local fixture service) |
| Bounded soak | `.venv/bin/python -m pytest tests/e2e/test_skills_soak.py -q -s` | **1 passed, 60.4 s** — 225 runs submitted (75 activated), 112 approvals + 113 denials, 56 cancellations, 32 skill toggles, 45 library reads, 202 SPA navigations; 0 page errors, 0 console errors, 0 route errors, 0 leaked active runs, registry readable |
| Packaging | `uv build --wheel` + isolated `uv venv` install | Wheel ships `hutch/skills.py`, `readiness.py`, `server/skills_api.py`, `server/static/skills.js`, `skills.css` and all three sample `SKILL.md` files; installed wheel passes an install→trust→resolve smoke test |
| Independent adversarial review | separate read-only agent session at `fa73b0e`; re-ran suites and 14 probes | Confirmed enforcement boundary, path safety, API default-deny, concurrency integrity; found 8 issues, all fixed in `aeb244c` with 11 new regressions |

### Independent review findings and fixes (`aeb244c`)

A separate agent session reviewed the subsystem read-only and attacked it with 14 probes. It
confirmed: untrusted/disabled/tampered/hand-edited skills never reach a prompt, tool or
activation; run start is byte-level even when listing is not; revocation is fail-closed; resource
path traversal, symlink escapes and hostile install paths are refused; `allowed-tools`/metadata
never change tool exposure; all skills routes are default-deny for paired phones (403 reproduced
with a real paired session); two- and four-process registry races stay consistent. Its real
findings, all now fixed:

| # | Finding | Fix |
|---|---|---|
| D1 | YAML alias bomb (~1 KB SKILL.md → MemoryError) reachable through discovery on every library view | Frontmatter is scanned for aliases/anchors before construction; metadata values must be scalars; 5,000-node cap |
| D2 | Resource reads were not hash-verified (mid-run tamper served silently) | `read_resource` verifies the package hash before serving |
| D3 | Hostile `use_skill(resource=…)` args (NUL, over-long) raised and crashed the run | Refusals instead of exceptions; schema `maxLength` bounds added |
| D4 | `install_builtin` accepted absolute/parent names and could install outside the bundle | Path-shaped names rejected |
| D5 | One unreadable file made the readiness endpoint 500 and blocked runs unclearly | `inspect_package`/`resolve_binding` return "could not be read"; readiness catches all resolution errors and stays 200 |
| D6 | `uninstall` raised on a symlinked package dir (registry entry stuck) | Removes the link (never the target) or returns a clean error |
| D7 | Listing could show a stale hash for a same-size/mtime-forged edit; docs overstated detection | The review inspector and CLI always full-hash the bytes they show; docs state the exact boundary (listing signature vs enforcement hash) |
| D8 | Staged updates were not actually reviewable; `apply` did not re-hash the staged bytes | Staged instructions exposed in the inspector/CLI; `apply_update` re-verifies the staged hash and refuses changed content |
| D9 | Catalog descriptions were interpolated into the prompt block unescaped | Prompt text escapes skill-provided markup |

The reviewer also disclosed that running the browser suite regenerated two committed screenshots;
those files were restored to their committed bytes and the full browser suite is re-run from the
final revision.

One design-system browser test (`test_assistant_settings_keep_everyday_edits_up_front`) fails on
the base commit `a2106ec` **without this slice's commits** (reproduced in a clean worktree at
`a2106ec`); it is pre-existing and not introduced here.

The full browser suite on the final revision reports 25 failures and 8 teardown errors that are
**pre-existing at the base commit**: a clean worktree at `a2106ec` (no slice commits) run with the
same selection produced the identical failure set (verified by diffing both pytest `lastfailed`
caches — zero difference). The clearest mechanism found:
`test_composer_options_rehearsal_and_cancelled_notice` asserts `inner_text()` of `.run-queue-time`,
but commit `8059efd` moved that element inside a collapsed `<details id="run-technical-details">`,
where Chromium's `innerText` is empty; the element itself renders the correct `1.3s` text and the
run API carries `queue_ms=1250` (verified with a standalone DOM probe). The other failures cluster
in the same recently refactored surfaces (workspace modes, browser handoff, fact review, tool
permissions, coordinator, duplication) and are outside this slice's diff. This slice's own browser
files (`test_skills_browser.py` 6 tests, `test_skills_soak.py`) passed within the same full-suite
run; the offline suite (1685 tests) is fully green.

### Bounded-corpus measurements (200 installed skills, 100 Bots, 20 bound, 3 activated)

| Measure | Before fast path | After |
|---|---|---|
| Library listing (registry) | p50 672 ms | **p50 213 ms** |
| `GET /api/v1/skills` | p50 450 ms | **p50 243 ms** (199,661 bytes response) |
| Skill detail | p50 23 ms | **p50 7 ms** |
| Bot readiness | p50 157 ms | **p50 74 ms** |
| Run resolution, 20 bound | p50 49 ms | **p50 12 ms** |
| Catalog prompt, 20 skills | — | 4,550 chars ≈ 1,137 est. tokens |
| One activated skill body | — | 751 chars ≈ 187 est. tokens |

Script: `/tmp/opencode/skills-bench.py` (development-only, not committed). No runtime processes or
skill bodies are loaded to render the library; only `use_skill` and explicit activation read bodies.

## Inspected visual evidence

`docs/realignment/artifacts/skills/`: `library-review-desktop`, `inspector-desktop`,
`library-trusted-desktop` (1440), `library-discovered-tablet` (768), `bot-assignment-desktop`
(1440), `bot-assignment-phone` (390), `bot-readiness-disabled-tablet` (900). Inspected as pixels:
status is always glyph + word, phone layout has no horizontal overflow, the review modal shows
provenance/hash/instructions/diagnostics and states that skill metadata is not authority. The
browser tests also assert no page errors and (in the soak) no route error states.

## Research-to-test mapping (current sources, fetched 2026-10-10)

| Source | Design response | Test |
|---|---|---|
| [Agent Skills specification](https://agentskills.io/specification) | SKILL.md parsing, name/description constraints, optional fields, `allowed-tools` informational | `test_skills.py` parsing cases |
| [Client implementation guide](https://agentskills.io/client-implementation/adding-skills-support) | Discovery scopes + precedence, lenient validation with diagnostics, catalog disclosure, dedicated activation tool, resource listing, dedupe | discovery/precedence/collision tests, `test_skill_runtime.py`, `use_skill` dedupe |
| The guide's trust note (project repos may be untrusted) | Nothing auto-trusted; explicit review per hash | `test_install_from_path_requires_review_before_use` |
| Assignment failure classes (silent settings loss, false "Connected", revocation not applied) | Readiness separates missing/warning; revocation fails closed | `test_readiness_*`, `test_revocation_between_submit_and_execution_fails_the_run_closed` |

## Verification boundaries (not claimed)

* **No live provider, model, or external account was used.** No live OAuth flow was exercised;
  "auth refresh" during the soak means local session/navigation resilience, not provider token
  rotation. Live provider auth-refresh races remain unverified here.
* No physical device, screen-reader, or Firefox-specific pass for the new surfaces (Chromium only).
* External runtimes (Pi, OpenCode) do not load Hutch skills; explicitly activating one there fails
  before start. That is a product boundary, not a verified integration.
* The template-identity bug was found and fixed on this branch; whether upstream releases shipped
  it elsewhere was not investigated.
* A connection-requiring skill is withheld in Strict Offline mode even when a grant exists
  (regression covered); live OAuth/token behavior itself remains unverified.
* The full browser suite result for the final revision is recorded when the background run
  completes; individual browser files were run and passed during development.

## Integration state

The shared checkout `/home/kevina/CodingProjects/hutch` was owned by another active session
(provider/model-switcher and UI work; commits `a2106ec`, `4f3f0c1`, `777324a`, with further
uncommitted edits). This work was developed in `.worktrees/skills-lifecycle`, rebased first onto
`a2106ec` and then onto `777324a`; the second rebase produced exactly one conflict (both sessions
appending to `CHANGELOG.md` under Unreleased), resolved by keeping both entry sets. `main` has
**not** been advanced underneath that session's dirty working tree. Integration is a fast-forward
of `main` to this worktree's HEAD once the shared checkout is quiet:

```bash
cd /home/kevina/CodingProjects/hutch
git merge --ff-only skills-lifecycle/HEAD   # after the active session commits or clears its tree
```

Local tags anchor the history across rebases: `skills-lifecycle-prerebase` (originals at
`f2b8b00`) and `skills-lifecycle-prerebase2` (pre-second-rebase at `b823349`). After the rebase
onto `777324a`, the focused suites (**74 passed**) and the skills browser files (**7 passed**,
including the soak) were re-run green; a fresh full browser-suite pass is run from this revision
and its result is recorded below when it completes.
