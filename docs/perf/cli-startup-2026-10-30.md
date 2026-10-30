# CLI cold start: lazily resolved tool catalog (2026-10-30)

Status: adopted and measured. This continues the 2026-10-29 performance programme, which
recorded CLI cold start as a deferred follow-up ("lazy command/tool imports") in
[plan-2026-10-29.md](plan-2026-10-29.md) item F and [results-2026-10-29.md](results-2026-10-29.md).

## Problem and measured attribution

Every shell invocation starts a fresh Python process. At HEAD 4c53c814, importing
`hutch.cli` eagerly imported the whole tool registry, so a quick command such as `hutch version`
paid for tool families it never uses.

Independent attribution (startup-profiler agent, pristine HEAD export, CPython -X importtime).
The representative trace is the run whose total import self time is the median of 5 traces;
the bracketed range is the per-run share variability across those traces:

| Subtree | Exclusive import self time (representative trace) | Share | Share across 5 traces |
|---|---:|---:|---:|
| `hutch.tools` | 500.6 ms | 56.2% | 44.6-56.2% (median 46.2%) |
| `hutch.models` | 204.4 ms | 23.0% | 22-33% |
| `hutch.cli_bot_deletion` | 6.7 ms | 0.75% | 0.70-1.10% |
| everything else (stdlib, typer/rich, pydantic, cli body) | 178.5 ms | 20.1% | remainder |

The ranking is robust: `hutch.tools` is the largest import bucket in every trace (212 of 528
import rows), and independent re-measurement during verification found 47.4-54.3% on a fresh
export. Individual shares move with the trace and absolute microseconds move with host load, so
quote the rank and the range rather than a single percentage.

Baseline wall time (head export, 11 fresh-process samples, loaded shared host): `version` median
857 ms / p95 1114 ms, `status` 951 / 1137 ms, `--help` 867 / 1137 ms.

Before the change, importing `hutch.tools` ran ~212 import-time module loads including
`hutch.synthesis` (and its model/tts/infographic dependencies), `hutch.media` (and
`hutch.outputblocks`), `hutch.grounding`, `hutch.actions`, `hutch.skills` and `hutch.persona`.
None are needed to print a version string or resolve an approval.

## Candidate decisions

| ID | Candidate | Measured or bounded cost | Alternative / plan | Decision |
|---|---|---|---|---|
| A | Lazy tool catalog (import tool classes on first use) | 500.6 ms exclusive self time in the representative trace (44.6-56.2% share); every quick command pays it | Static spec table + first-use `importlib` resolver behind a read-only `Mapping`; deterministic `sys.modules` regression tests instead of timing gates | ADOPT |
| B | Defer the bot-deletion command-layer import | 6.7 ms exclusive (0.75%); its inclusive share is nearly all `hutch.models`, imported by `cli.py` anyway | Move `from . import bot_deletion` into the three command helpers | ADOPT (small, removes a needless eager dependency) |
| C | Defer `hutch.models` / import commands lazily per Typer command | 247 ms inclusive (33%); models is imported by `cli.py` top level and used by most commands | Would require splitting the 2,758-line frozen `cli.py` and moving pydantic models to function scope; high regression risk for ~150-200 ms | DEFER (measured; needs its own frozen-file-safe split) |
| D | Lazy `hutch serve` application imports | serve startup to first HTTP response was 3.07 s in the real-world smoke; `server/app.py` is a 7,461-line frozen file owned by a parked session | Route-level lazy imports inside app.py; cannot be reviewed/merged in this window | DEFER (blocked by parked-file ownership, not by measurements) |
| E | Rust CLI or native import accelerator | A Rust binary would cut process start to single-digit ms (research: the local `uv --version` measured 8.6 ms median) | ADR-0024/P11 authorises kernel replacement after equivalent tests, not an entry-point rewrite; it is explicitly out of scope; no credible native accelerator exists for third-party imports; lazy imports recover most of the avoidable cost for a fraction of the risk | REJECT (documented in [research/cli-startup-2026-10-30.md](../research/cli-startup-2026-10-30.md)) |
| F | Keep `hutch --help` eager command registration | --help imports cli.py and therefore models/typer | Typer cannot render command help without the command table; splitting commands is candidate C | REJECT for this change (same frozen-file constraint) |

## Implementation

- `src/hutch/tools/__init__.py`: the eager `from .<tool module> import <Tool>` block and the
  `_CATALOG` dict of classes became a `_SPECS` table of `(module, class)` names plus `_tool_class`,
  a memoizing `importlib.import_module` resolver. `_CATALOG` is now a read-only `Mapping` facade
  that resolves a class on lookup, so `_CATALOG[name]`, `.items()`, `.values()`, `ALL_TOOL_NAMES`,
  `GROUPS`, `expand_tools` and `build_tools` keep their observable behaviour. `build_tools` also
  imports `UseSkillTool`/`AskUserChoiceTool` at the point of use; they were never catalog entries.
- `src/hutch/cli_bot_deletion.py`: the command layer (`bot_deletion`) is imported inside the
  preview/confirm/recover helpers, i.e. only when `hutch bot destroy` actually runs.
- Catalog order, `ALL_TOOL_NAMES` membership/order, tool group expansion and tool construction
  order are unchanged; `_RESOLVED` memoizes per process.
- Guards: `tests/test_tool_catalog_lazy.py` checks every catalog name resolves to the declared
  module/class/tool name, mapping parity, group membership, `build_tools` construction, and (in a
  fresh interpreter) that importing `hutch.cli` does not import the heavy tool families while a
  single catalog lookup imports exactly the named tool module.

## Results (paired, interleaved, same driver/session)

Driver: `python -m benchmarks.cli_startup_ab --before <HEAD-export>/src --after src --samples 9 --check`.
Fresh process per sample, PYTHONPATH pins the tree, isolated `HUTCH_STATE_DIR`, samples alternate
before/after so host-load drift hits both sides. Host load median 6.8-7.5 during the run.

| Command | Before median | After median | Delta | Before p95 | After p95 |
|---|---:|---:|---:|---:|---:|
| `hutch version` | 609 ms | 331 ms | **-45.7%** | 854 ms | 415 ms |
| `hutch --help` | 864 ms | 575 ms | **-33.4%** | 1114 ms | 762 ms |
| `hutch status` | 1083 ms | 600 ms | **-44.6%** | 1534 ms | 866 ms |
| `hutch bot list` | 958 ms | 584 ms | **-39.1%** | 1203 ms | 772 ms |

All four commands return the same stdout bytes before and after (sha256 equal) and exit 0; the
driver's `--check` gate passes. Every case clears the repository's >=20% median bar.

Independent confirmation: the startup-profiler measured both trees with a different driver
(11 samples per case, rotated order, separate sequential runs, an independent provenance
snapshot of the after tree; host load 5.67 before / 5.66 after median):

| Command | Before median | After median | Delta | After p95 |
|---|---:|---:|---:|---:|
| `hutch version` | 856.7 ms | 413.0 ms | **-51.8%** | 558.4 ms |
| `hutch status` | 950.9 ms | 460.9 ms | **-51.5%** | 710.6 ms |
| `hutch --help` | 867.5 ms | 510.1 ms | **-41.2%** | 801.8 ms |
| `hutch bot list` | 821.8 ms | 419.3 ms | **-49.0%** | 660.4 ms |
| `hutch init` (fresh state dir) | 1139.2 ms | 658.6 ms | **-42.2%** | 917.2 ms |

Output was byte-identical for every command when run against the same state path; `serve`
startup did not regress (first-run TCP-ready median 3811 -> 3493 ms, -8.3%, p95 -17.4%; warm
-11.0%, n=5 per tree, server killed by process group and port checked closed). The two methods
(interleaved vs sequential) agree far beyond the pre-registered 20% bar; the interleaved table
above remains the authoritative claim because it controls load drift at sample level.

## Regression and real-world validation

- Focused pytest for the touched surface (259 passed / 1 skipped, 11 files): catalog/import-graph tests, tools, runtime builtin,
  engine, engine loop, integration catalog/contract, offline mode, sandbox, doctor/health, CLI,
  bot deletion, templates, skills, tool-calling suites.
- Real-world workflow on an isolated state dir (all exit 0): `init`, `bot create demo --model
  ollama/llama3.2 --tools files,memory`, `bot list`, `bot show demo`, `status`, `version`,
  `skills list`, `doctor`; then `serve --port 8899` reached `/api/health` (200), `/` (200,
  12,503 bytes) and `/api/bots` (200) and was terminated cleanly.
- Existing benchmark gate: `python -m benchmarks.run --check` (PF gate) passes; the recorded
  `startup.cli_version_ms` / `startup.cli_status_ms` cases are the same quick-path metric.
- Browser: the live-update journey passes (1 passed, 17 s) and a 6-check visual gate at
  1440x900, 900x900 and 360x800 over the dashboard home and a run detail captured screenshots
  with zero page errors, zero console errors and zero horizontal overflow (screenshots inspected
  manually; no UI source changed in this increment).

## Prior programme re-verification (2026-10-30, HEAD 4c53c814)

- Optional native XLSX kernel: `python scripts/build_native_docgen.py --check` built the
  PyO3 0.29.3 + rust_xlsxwriter 0.90.2 crate under `native/docgen_xlsx` and passed its smoke
  test (5,365-byte workbook, extension version 0.1.0, exit 0) on this host; no manifest or
  mandatory Rust dependency was added. Build artifacts were removed afterwards.
- Focused pytest for the touched and adjacent surface (final clean run): 259 passed / 1 skipped across the
  tool-calling, tools, CLI, bot-deletion, templates and skills sets, plus 162 passed / 23 skipped
  / 3 xfailed across engine, engine-loop, integration-catalog/contract, offline, sandbox,
  doctor/health, skills and stats sets.
- Committed audits: `python scripts/audit_emoji.py` clean (1,734 files, 10 waivers);
  `python scripts/check_commit_attribution.py --range 4c53c814..HEAD` clean. The fuller
  `npm run check:agent` script set exists only in the parked session's uncommitted
  package.json, so it is not runnable from a clean HEAD worktree; that is an environment
  limitation, not a check claimed as passing.
- Benchmark gate: `python -m benchmarks.run --check`. The first run failed only on
  `events_per_sec` (1,998 ev/s vs committed baseline 3,607 ev/s) while the host was at load
  7.5-8.6 with other agents; an interleaved A/B of the untouched in-process writer on a pristine
  HEAD export vs this change measured 916 vs 824 ev/s median (-10%, inside the alternating
  noise) while both trees were equally starved, so the failure was not caused by this change.
  A clean rerun at load 2.9 then passed every metric (`no regression beyond 20%`, exit 0):
  `events_per_sec` 5,382 ev/s p50 (baseline 3,607, 1,000 floor), `cli_version_ms` 467 ms p50
  (baseline 1,138), `cli_status_ms` 448 ms p50 (baseline 1,417; the 300 ms proposed target is a goal,
  not a gate, and was not met on this loaded host), `step_overhead_ms` 0.5 ms, idle RSS/CPU within
  target. Both runs are recorded; the pass is the honest gate result and the first run documents
  why the gate is host-load sensitive.

## Honest limits

- Absolute milliseconds are host-specific and noisy: the shared 4C/8T host ran at load average
  6.8-7.5 during sampling (other sessions). Only the paired ratio between the two trees in one
  driver is a claim; cross-run absolute numbers are not comparable.
- The measurement is control-path CPU. It does not make a model reply arrive sooner; it removes
  pure overhead from every quick CLI invocation (and from the dashboard process import path).
- The first run after a fresh install also compiles bytecode. The paired driver warms both trees
  once before sampling, so the reported numbers are steady-state cold-process numbers, not the
  one-off compile of a new install.
- Remaining floor: `hutch version` still imports `hutch.models` (pydantic), Typer/Rich and the CLI
  command table. The measured ~330 ms median under this load is close to the sum of those
  imports; candidates C/F need a frozen-file-safe command split and are deliberately deferred.
- The `--help` result has a wider spread than the other cases on this host (help renders every
  command); do not read the p95 difference as a precise rendering cost.
- No Rust/native work was adopted here; the Rust evaluation is in the research document and is
  consistent with ADR-0024 (no bar-clearing kernel for this problem, no rewrite).

## Reproduce

~~~
# pristine comparison tree (no checkout switching)
mkdir -p /tmp/hutch-before && git archive <before-ref> | tar -x -C /tmp/hutch-before
PYTHONPATH=$PWD/src .venv/bin/python -m benchmarks.cli_startup_ab \
    --before /tmp/hutch-before/src --after src --samples 9 --check

# import attribution
PYTHONPATH=<tree>/src .venv/bin/python -X importtime -c \
    "import sys; sys.argv=['hutch','version']; from hutch.cli import main; main()" 2>&1 \
    | grep '^import time:'

# focused guards and real-world workflow
PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q --no-header --tb=line \
    tests/test_tool_catalog_lazy.py tests/test_tools.py tests/test_runtime_builtin.py \
    tests/test_engine.py tests/test_cli.py tests/test_bot_deletion.py
~~~