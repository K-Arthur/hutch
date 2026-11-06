# Hutch agent map (generated)

Generated from the committed/staged tree (`git ls-files --cached`) by
`python scripts/generate_agent_map.py --write`. Deterministic: no timestamps,
no source line counts, no unstaged or ignored files. Ordinary source edits do
not change it; stage file additions or removals, then regenerate. Do not edit
this file by hand.

Tracked files in scope: 2614.

## Top-level layout

| Top-level entry | Tracked files |
| --- | ---: |
| `(root files)` | 23 |
| `.githooks/` | 2 |
| `.github/` | 10 |
| `.impeccable/` | 4 |
| `.zcode/` | 6 |
| `app/` | 2 |
| `benchmarks/` | 29 |
| `desktop/` | 23 |
| `docs/` | 1263 |
| `native/` | 9 |
| `scripts/` | 38 |
| `src/` | 639 |
| `tests/` | 500 |
| `website/` | 66 |

## Python package: src/hutch/

| Path | Tracked files |
| --- | ---: |
| `(root files)` | 120 |
| `actions/` | 3 |
| `channels/` | 5 |
| `computer/` | 19 |
| `data/` | 18 |
| `documents/` | 13 |
| `grounding/` | 8 |
| `gsuite/` | 4 |
| `integrations/` | 17 |
| `media/` | 12 |
| `personal/` | 8 |
| `platforms/` | 4 |
| `providers/` | 49 |
| `runtime/` | 19 |
| `server/` | 238 |
| `sources/` | 4 |
| `synthesis/` | 7 |
| `toolcalling/` | 11 |
| `tools/` | 38 |
| `vault/` | 13 |
| `web/` | 6 |
| `workflow/` | 17 |
| `workspace/` | 6 |

## Tests: tests/

| Path | Tracked files |
| --- | ---: |
| `(root files)` | 377 |
| `e2e/` | 86 |
| `fixtures/` | 17 |
| `native/` | 1 |
| `support/` | 19 |

## Desktop, dashboard sources and website

| Path | Tracked files |
| --- | ---: |
| `desktop/(root files)` | 8 |
| `desktop/icons/` | 7 |
| `desktop/process-guard/` | 5 |
| `desktop/src/` | 1 |
| `desktop/web/` | 2 |
| `app/src/(root files)` | 2 |
| `website/(root files)` | 23 |
| `website/.well-known/` | 1 |
| `website/assets/` | 34 |
| `website/icons/` | 7 |
| `website/src/` | 1 |

## Rust crates

| Crate | Manifest | Tracked files |
| --- | --- | ---: |
| `desktop/process-guard` | `desktop/process-guard/Cargo.toml` | 5 |

## Entry points

| Entry point | Load it for |
| --- | --- |
| `AGENTS.md` | always-loaded index and hard rules (<=150 lines) |
| `.ai/skills/README.md` | reusable task playbooks |
| `.ai/roles/README.md` | on-demand role files |
| `docs/agent-workflow.md` | context economy, guard commands, quiet validation |
| `docs/architecture.md` | architecture overview |
| `docs/repository-hygiene.md` | ignore, commit and packaging policy |
| `docs/realignment/tool-calling.md` | canonical tool contract and evidence |

## Largest frozen files

| File (frozen in .file-size-baseline.json) | Lines |
| --- | ---: |
| `src/hutch/server/static/app.js` | 14532 |
| `tests/e2e/test_browser.py` | 13265 |
| `src/hutch/store.py` | 12593 |
| `src/hutch/server/app.py` | 7461 |
| `tests/e2e/test_design_system.py` | 3334 |
| `src/hutch/server/static/style.css` | 2775 |
| `src/hutch/cli.py` | 2758 |
| `src/hutch/workflow/persistence.py` | 2066 |
| `tests/test_workflow_api.py` | 1961 |
| `src/hutch/runtime/builtin.py` | 1955 |

## Regenerate

Regenerate with python scripts/generate_agent_map.py --write after staging additions or removals; --check (also npm run audit:agent-map) detects drift.
