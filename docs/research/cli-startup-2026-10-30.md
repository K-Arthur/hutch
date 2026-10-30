# CLI cold start and lazy imports: external research record

- Programme row: D2 of the `hutch-cli-startup` long-horizon charter (`CHARTER.md`), dated 2026-10-30.
- Question: why Python CLIs start slowly, which import techniques help, what comparable tools do, which failures are reported, and whether selective Rust can clear the repository bar.
- Method: primary CPython and PEP documentation/source, maintainer pull requests and issue threads, competitor reports, plus one explicitly labelled local spot-check (section 9). All URLs were accessed 2026-10-30 unless a publication date is shown; evidence grades are defined in section 2.
- Repository frame: console script `hutch = hutch.cli:main` (`pyproject.toml`), Python >=3.11 (venv 3.13.15), dependencies Typer/Rich/Pydantic; `src/hutch/tools/__init__.py` is the tool registry; `src/hutch/cli.py` (2,760 lines) is the quick-command entry; `src/hutch/cli_bot_deletion.py` installs `hutch bot destroy`; `desktop/backend.spec` freezes the Python backend for the Tauri host; `benchmarks/hotpath_workloads/startup.py` already times `hutch version`/`status` as fresh processes with an isolated state directory; `docs/performance.md` records a 275 ms `hutch status` baseline (minimum of 11 cold-process runs).
- This is a research record, not the measurement record: D3/D4 own the baseline and import-cost attribution, and D7 owns the paired before/after.

## 1. Executive summary

Cold start here is import execution, not interpreter start: local medians were 24.3 ms for `python -c pass`, 412.9 ms for `hutch version`, and `-X importtime` attributes 279.2 ms (minimum of three) to importing `hutch.cli`. CPython documents `-X importtime` (cumulative versus self; cached trace with `=2` from 3.14) as the measurement of record. The lowest-risk fix is a static name table with first-use class resolution behind a Mapping facade, as pipx and Typer did for their lazy imports (45% startup cut in Typer's case). Implicit lazy imports were rejected (PEP 690); Python 3.15 ships explicit `lazy import` (PEP 810). Real failure modes are deferred errors, PyInstaller dynamic-import breakage and thread races. A Rust CLI would clear the 20% p95 bar but is out of scope by ADR-0001/0016/0024 and `docs/requirements.md`, and no general native import accelerator exists. Adopt the lazy registry plus deterministic import-graph guards; do not rewrite.

## 2. Sources

Evidence grades: **docs** = primary documentation or specification; **maintainer** = project maintainer change or statement, sometimes with single-host measurements; **single report** = one user issue or one project report. No peer-reviewed source specific to Python CLI cold start was found.

| # | Source | URL | Date | Finding | Grade | Applicability to Hutch |
|---|---|---|---|---|---|---|
| 1 | CPython docs, `-X` options and `PYTHONPROFILEIMPORTTIME` | https://docs.python.org/3/using/cmdline.html#cmdoption-X | 3.15 stable; option added 3.7; `=2` added 3.14 | `-X importtime` prints module name, cumulative time (including nested imports) and self time (excluding nested); `=2` also traces already-loaded modules as `cached`; output may be broken in multi-threaded applications | docs | Measurement of record for this programme |
| 2 | CPython docs, The import system | https://docs.python.org/3/reference/import.html | accessed 2026-10-30 | Modules are created once and cached in `sys.modules`; first import searches finders, loads bytecode, executes the module body, recursing into its imports | docs | Explains why a CLI pays its whole transitive closure once |
| 3 | CPython docs, Customizing module attribute access | https://docs.python.org/3/reference/datamodel.html#customizing-module-attribute-access | accessed 2026-10-30 | Module-level `__getattr__` is consulted only for attributes missing from normal lookup; `__dir__` overrides `dir()` | docs | Basis of the PEP 562 pattern for optional attributes |
| 4 | PEP 562, Module `__getattr__` and `__dir__` | https://peps.python.org/pep-0562/ | created 2017-09-09; Final; Python 3.7 | Lazy module attributes via `__getattr__`; performance impact minimal because it runs only for missing names; warns about pickling, recursion and tools that perform module attribute discovery | docs | Pattern and pitfalls for a public module API |
| 5 | CPython docs, `importlib.util.LazyLoader` | https://docs.python.org/3/library/importlib.html#importlib.util.LazyLoader | accessed 2026-10-30 | Defers the loader until an attribute is accessed; only works with compatible loaders; raises `ValueError` if a module replaces itself in `sys.modules`; the docs heavily discourage it outside startup-critical projects because load errors are postponed and occur out of context | docs | Why a registry resolver beats transparent module laziness |
| 6 | CPython docs, `site` | https://docs.python.org/3/library/site.html | accessed 2026-10-30 | `site` runs automatically during startup, adds site-packages, executes `import` lines in `.pth` files and imports `sitecustomize` | docs | Interpreter floor and editable-install/virtualenv effects |
| 7 | Python 3.11 What's New, Faster Startup | https://docs.python.org/3/whatsnew/3.11.html#faster-startup | 3.11 released 2022 | Core startup modules are frozen so their code objects are statically allocated, removing read/unmarshal steps; the release reports major startup improvements | docs | The floor was lowered, but user imports remain the dominant cost |
| 8 | Python 3.3 What's New, A Finer-Grained Import Lock | https://docs.python.org/3/whatsnew/3.3.html#a-finer-grained-import-lock | 3.3 released 2012 | Since 3.3 importing a module takes a per-module lock: imports of the same module from several threads serialize and never expose half-initialized modules | docs | First-use lazy resolution is safe at module granularity |
| 9 | PEP 484, Stub files (module `__getattr__`) | https://peps.python.org/pep-0484/#stub-files | accessed 2026-10-30 (Final) | A stub may declare `def __getattr__(name) -> Any: ...` so type checkers accept undeclared module attributes | docs | Typing escape hatch if a module-level `__getattr__` is added |
| 10 | PEP 690, Lazy Imports | https://peps.python.org/pep-0690/ | created 2022-04-29; **Rejected** | Proposed transparent global lazy imports; its reference implementation claimed 40-70% startup improvement and up to 40% memory reduction; rejected | docs | Why transparent laziness was not adopted by CPython |
| 11 | PEP 810, Explicit lazy imports | https://peps.python.org/pep-0810/ | created 2025-10-02; resolved 2025-11-03; Final; Python 3.15 | Opt-in `lazy import`/`lazy from`; `sys.set_lazy_imports("normal"/"all"/"none")` and a per-import filter; FAQ contrasts it with the rejected PEP 690; errors surface at first use with chained traceback showing definition and access sites | docs | Future option for Hutch; unusable while the floor is 3.11 |
| 12 | Python 3.15 What's New | https://docs.python.org/3/whatsnew/3.15.html | current stable 3.15.2 | Lazy imports are a release highlight (PEP 810); a dedicated profiling package (PEP 799) is added | docs | Upgrade context for the recommendation to monitor, not adopt now |
| 13 | pyperformance benchmarks (`python_startup`, `python_startup_nosite`) | https://pyperformance.readthedocs.io/benchmarks.html | accessed 2026-10-30 | Standard suite measures `python -c pass` and `python -S -c pass` to isolate interpreter and site startup | docs | Use as the floor reference, separate from application imports |
| 14 | pyinstrument API docs, command line interface | https://pyinstrument.readthedocs.io/en/latest/reference.html | accessed 2026-10-30; pyinstrument 5.1.3 | `pyinstrument -m module` runs a module like `python -m` under a sampling profiler | docs | CPU attribution across startup; not an import-tree accounting tool |
| 15 | tuna import-profile viewer | https://github.com/nschloe/tuna | accessed 2026-10-30 | Visualizes `python -X importtime ... 2> import.log` (and cProfile output) | maintainer | Optional human-readable import trees; used in the dbt report |
| 16 | hyperfine CLI benchmarker | https://github.com/sharkdp/hyperfine | accessed 2026-10-30 | Command-line wall-clock benchmarking with warmups and statistics | maintainer | Wall-time A/B interleaving for D7 |
| 17 | import-linter, forbidden contracts | https://import-linter.readthedocs.io/en/latest/contract_types/forbidden/ | accessed 2026-10-30 | Static contracts can forbid one module set from importing another, including indirect imports and external packages | docs | Architecture guard; cannot see imports performed from strings |
| 18 | pytest docs, plugin discovery and `PYTEST_DISABLE_PLUGIN_AUTOLOAD` | https://docs.pytest.org/en/stable/how-to/writing_plugins.html | accessed 2026-10-30 | At tool startup pytest loads plugins discovered through installed package entry points, and documents an environment variable to disable that autoload | docs | Precedent that plugin/tool discovery itself is startup cost |
| 19 | PyInstaller, When Things Go Wrong (hidden imports) | https://pyinstaller.org/en/stable/when-things-go-wrong.html | accessed 2026-10-30 | Imports that are only performed dynamically are not found by static analysis; PyInstaller documents listing hidden imports to fix frozen applications | docs | Critical for the frozen desktop backend |
| 20 | Scientific Python SPEC 1, Lazy Loading of Submodules and Functions | https://scientific-python.org/specs/spec-0001/ | endorsed spec; accessed 2026-10-30 | Recommends lazy submodule/function loading (via `lazy_loader` or module `__getattr__`) and notes adoption by scikit-image, NetworkX and MNE-Python, with SciPy implementing a subset; advises not every project needs it | docs (community consensus) | Mature typed lazy-loading pattern |
| 21 | lazy-loader package page | https://pypi.org/project/lazy-loader/ | accessed 2026-10-30 | Attaches `__getattr__`/`__dir__` from stubs; type checkers cannot infer lazily loaded imports, so projects must ship `.pyi` stubs; recommends Python >=3.11.9/3.12.3+ to avoid a known race condition | maintainer | Typing and thread-safety costs of lazy loading |
| 22 | lazy-loader changelog | https://github.com/scientific-python/lazy-loader/blob/main/CHANGELOG.md | accessed 2026-10-30 | Records PR #90 making `lazy_load.load` partially thread-safe and PR #102 recommending newer Python versions to avoid a race | maintainer | Lazy machinery needs explicit thread-safety work |
| 23 | Typer PR #1128, lazy-load `rich_utils` | https://github.com/fastapi/typer/pull/1128 | created 2025-01-19; merged 2025-08-30 | Lazy-loading `rich_utils`/`rich.traceback` cut a minimal Typer app from 94.19 ms to 51.99 ms (45%, best of 5, M4 Pro host); a test asserts Rich is not imported | maintainer (single-host measurement) | Direct precedent for Typer-based CLIs |
| 24 | Typer docs, Commands | https://typer.tiangolo.com/tutorial/commands/ | accessed 2026-10-30 | Commands are registered through decorators evaluated when the module is imported; no documented lazy-command mechanism | docs | Hutch builds every command eagerly in `cli.py` |
| 25 | Click source, `Group.get_command` and `list_commands` | https://github.com/pallets/click/blob/main/src/click/core.py | accessed 2026-10-30 | `get_command(ctx, cmd_name)` returns a command or `None`; `list_commands(ctx)` returns the names; these are the documented override points for custom command lookup | docs (source) | Enables lazy subcommands in Click/Typer applications |
| 26 | Pydantic docs, Performance tips | https://pydantic.dev/docs/validation/latest/concepts/performance/ | accessed 2026-10-30 | Guidance covers validation and serialization and says Pydantic is usually not the bottleneck; no import-cost guidance is documented on that page | docs | Pydantic import cost must be measured, not inferred from its docs |
| 27 | pipx PR #2113, cut startup by deferring imports and probes | https://github.com/pypa/pipx/pull/2113 | created and merged 2026-10-14 | Removed 100-150 ms (Linux) / 320-350 ms (Windows) of pre-work; `import filelock` alone about 15 ms; `pipx.commands` imports 21 command modules up front; `pipx --version` 110->60 ms, `pipx list` 130->63 ms | maintainer (measured, 2026-10-14) | The best recent blueprint for a Python CLI registry |
| 28 | pipx PR #2128, defer remaining startup imports | https://github.com/pypa/pipx/pull/2128 | created and merged 2026-10-14 | Follow-up `-X importtime` audit moved the remaining modules it named; `tests/test_imports.py` asserts importing `pipx.main` loads none of them; `pipx --version` 80->67 ms | maintainer (measured) | Shows the guard-test pattern Hutch needs |
| 29 | pipx PR #2132, make every import lazy on Python 3.15 | https://github.com/pypa/pipx/pull/2132 | created and merged 2026-10-14 | Uses `sys.set_lazy_imports("all")` (PEP 810) on 3.15 only; 37.6->34.1 ms `--version`; documents one visible change: a missing dependency's `ImportError` now appears on first use instead of at startup | maintainer (measured) | Future option and the exact error-behaviour trade-off |
| 30 | pipx `tests/test_imports.py` | https://github.com/pypa/pipx/blob/main/tests/test_imports.py | accessed 2026-10-30 | Runs subprocesses and asserts heavy modules are absent from `sys.modules` after importing the CLI; includes PEP 810-conditional cases | maintainer | Deterministic guard design to copy |
| 31 | Poetry issue #3502, slow startup | https://github.com/python-poetry/poetry/issues/3502 | created 2020-12-19; closed 2022-09-05 | User measured roughly 500 ms overhead versus native execution and noted Poetry 1.0 was under 350 ms; maintainers pointed at moving command imports into handlers and estimated about 300 ms, then about 250 ms; closed as "not a regression" | single report + maintainer | Older Click-era precedent; startup around a few hundred ms is not unusual for Python CLIs |
| 32 | dbt-core issue #9814, startup time of typing `dbt` | https://github.com/dbt-labs/dbt-core/issues/9814 | created 2024-03-25; closed stale 2024-10-07 | Bare `dbt` took 1.2-1.5 s on an M1; the reporter used `python -X importtime core/dbt/cli/main.py` and tuna; a dbt-common change plus import removal reached about 0.7 s then about 0.45 s; the cost made Click's shell completion unusable | single report + maintainer | Completion and help paths are the worst case for eager imports |
| 33 | AWS CLI issue #9011, slow startup | https://github.com/aws/aws-cli/issues/9011 | created 2024-10-25; open | `aws s3 ls` measured 0.346 s versus 0.091 s for s3cmd; the maintainer attributes startup to loading models and processing configuration; the reporter replaced the CLI with curl in CI and cut a job from 14-15 to 10-11 minutes | single report + maintainer | Large Python CLIs can carry several hundred ms as accepted cost |
| 34 | Azure CLI issue #31541, slow first instantiation | https://github.com/Azure/azure-cli/issues/31541 | created 2025-05-22; open | Reports that the CLI loads all command modules on first use, slowing CI first runs, and asks for just-in-time/queryable command-module loading | single report | Command-table discovery cost in another large Python CLI |
| 35 | PraisonAI PR #2001, lazy loading for CLI command modules | https://github.com/MervinPraison/PraisonAI/pull/2001 | created 2026-06-17; merged 2026-06-18 | Adds a `LazyCommandGroup` extending `TyperGroup`, moves about 85 command modules behind a lazy name map, and lists commands in `--help` without importing them | maintainer (no measurements) | A current Typer-specific lazy-command pattern |
| 36 | GitHub CLI manual, extensions | https://cli.github.com/manual/gh_extension | accessed 2026-10-30 | Extensions are repositories named `gh-*` containing an executable of the same name, discovered on PATH; arguments are forwarded; core commands cannot be overridden; update check runs at most every 24 hours | docs | In a Go host binary, extension discovery does not import an interpreter graph |
| 37 | uv installation docs | https://docs.astral.sh/uv/getting-started/installation/ | accessed 2026-10-30 | Rust implementation distributed as standalone binaries and as PyPI wheels (`pip install uv`) | docs | Rust CLI distribution reality: native binaries wrapped for Python packaging |
| 38 | Ruff installation docs | https://docs.astral.sh/ruff/installation/ | accessed 2026-10-30 | Rust linter installable via `pip install ruff`, `uv tool install`, pipx or standalone installers | docs | Same model: Rust binary, Python packaging |
| 39 | Meta engineering, Lazy is the new fast | https://engineering.fb.com/2024/01/18/developer-tools/lazy-imports-cinder-machine-learning-meta/ | 2024-01-18 | Lazy imports plus the Cinder runtime delivered up to 40% time-to-first-batch improvement and 20% Jupyter kernel startup reduction | maintainer (vendor self-report) | Industry-scale evidence that import time dominates Python startup |
| 40 | scikit-image issue #6772, PyInstaller and lazy loading | https://github.com/scikit-image/scikit-image/issues/6772 | created 2023-02-28; closed | Freezing a lazily loaded package fails with `ValueError: Cannot load imports from non-existent stub`; the reported workaround was bundling the package's stub files for PyInstaller | single report (reproducible) | Concrete frozen-app failure mode |
| 41 | OpenTelemetry PR #4735, cache `importlib.metadata.entry_points` | https://github.com/open-telemetry/opentelemetry-python/pull/4735 | created 2025-09-05; merged 2025-09-09 | Caching entry-point discovery gave about 10% import improvement in that repository, more with many installed packages | single report | Entry-point/plugin discovery can be a measurable startup cost |

## 3. Mechanism of Python CLI cold start

### 3.1 Interpreter and site

CPython initialises builtins and frozen modules, then imports `site`, which adds site-packages, executes `import` lines in `.pth` files and imports `sitecustomize` (source 6). Only after that does the console-script wrapper import the application. pyperformance isolates this floor with `python -c pass` versus `python -S -c pass` (source 13); Python 3.11 reduced it by freezing core modules (source 7). On the local spot-check the floor was 24.3 ms median, about 6% of `hutch version`.

A first import also pays filesystem lookup plus `.pyc` loading/compilation; a warm `__pycache__` is the normal case for installed packages and is the case a CLI benchmark should measure. Editable installs add their own path/import-hook setup to site processing, so a benchmark has to use the same installed console script users run, not a differently configured source checkout.

### 3.2 The import graph, and why eager imports dominate

Importing a module executes its top-level statements: definitions, decorators, class bodies, Pydantic model construction, Typer command registration, and every import it performs (source 2). The cost of a command is therefore the transitive closure of its static imports, not the subset it uses. PEP 690's motivation states the general case plainly: importing a program's main module typically triggers a cascade of most modules the program may ever need, while one invocation executes a single subcommand or none for `--help` (source 10).

For Hutch the closure starts at `src/hutch/cli.py`, which eagerly imports `models`, `config`, `store`, `lifecycle`, `templates`, `cli_bot_deletion` and `tools` (only the names `ALL_TOOL_NAMES`/`expand_tools` are used from the registry at module scope). `src/hutch/tools/__init__.py` in turn imports `.base`, whose own closure includes Pydantic models, config, safety, approvals and the store. So a lazy tool *class* table removes the per-tool families but not the registry/base closure; section 8 ranks a follow-up split.

### 3.3 Reading `-X importtime`

The documented format is module name, cumulative time (including nested imports) and self time (excluding nested imports) (source 1). Practical rules:

1. The total import cost of a target is the cumulative value on that target's own line; the last line of `python -X importtime -c 'import target'` is normally the target.
2. Self time is additive across all lines and is the right basis for ranking cost centres. Do not rank by cumulative: parents always look expensive because they include children.
3. Aggregate self time by top-level package (for Hutch: `hutch`, `pydantic`, `rich`, `typer`, `pydantic_core`, ...) to get a share table; then drill into the tree for the parent whose cumulative is the target.
4. A module imported earlier appears once; without `=2` (3.14+) later imports of cached modules are not shown, which is expected, not a missing cost. `-X importtime=2` prints `cached` for those lines.
5. The docs warn that multi-threaded applications can break the output; profile a single-threaded startup path and repeat.
6. Run on a warm bytecode cache and on a quiet machine, take the minimum of several runs (imports include disk and CPU scheduling noise), and record load average. The same rule applies to wall time.
7. To distinguish interpreter floor from application imports, compare `python -c pass`, `import hutch.cli`, and the full CLI wall time in the same session.

### 3.4 Measurement alternatives

| Tool | What it answers | Limits |
|---|---|---|
| `python -X importtime` / `PYTHONPROFILEIMPORTTIME` | which modules cost what, self vs cumulative | import phase only; no CPU attribution inside a module's statements; multi-thread caveat |
| `cProfile` / `profiling.tracing` (`python -m cProfile -o out.prof ...`) | CPU function attribution including imports executed by the profiled script | interpreter/site startup happens before the profiler; import nesting is less legible |
| pyinstrument | sampling CPU profile of a whole script/module run (`pyinstrument -m module`) | sampling, not exact; no separate import accounting |
| pyperformance `python_startup` / `python_startup_nosite` | interpreter and site floor as a standard benchmark | no application imports |
| hyperfine | wall-clock A/B of complete commands with statistics | host load dominates unless interleaved; measure the console script |
| tuna | readable import tree from `-X importtime` logs | visualization only |

For this programme: use `-X importtime` for attribution, interleaved fresh-process wall time for the claim (D7), pyperformance-style floor checks to detect environment drift, and pyinstrument only if CPU inside a module body matters.

## 4. Lazy import patterns and pitfalls

### 4.1 Patterns, in increasing order of coupling

1. **Function-local imports** (`def _cmd_...(): import heavy`). Simplest; each call site opts in; import machinery caches after the first call. pipx moved command modules this way (source 27).
2. **Module-level `__getattr__`/`__dir__`** (PEP 562, Python 3.7+; sources 3, 4). A package `__init__` keeps a name table and imports the matching submodule on attribute access. This preserves `from pkg import Name` for callers and interactive exploration. `lazy_loader` wraps this pattern for scientific Python (sources 20, 21).
3. **`importlib.util.LazyLoader`.** Standard library, but the docs discourage it outside startup-critical projects because errors are postponed and reported out of context; it also cannot be used with every loader and rejects modules that replace themselves in `sys.modules` (source 5).
4. **Static spec table plus resolver and Mapping facade** (what Hutch's worktree now does): a literal `name -> (module, class)` table, `_tool_class(name)` that calls `importlib.import_module` and memoizes, and a read-only `Mapping` object for `_CATALOG`. Callers keep `keys`/`items`/`values`/`in`/`len`/iteration semantics; type checkers see `Mapping[str, type[Tool]]` without stubs; the import graph stays visible in one table for guards and packaging.
5. **Command-group override.** For command registries (not tool factories), subclass the Click/Typer group and override `get_command`/`list_commands` (source 25); PraisonAI does this for about 85 Typer command modules (source 35). Hutch's commands live in the frozen `cli.py` module, so this pattern is a later option, not part of D6.

### 4.2 Pitfalls, and what the evidence says

- **Circular imports.** Eager cycles fail at import time, close to the cause; lazy resolution defers them to first use, which can be in a request or a bot run. Keep the resolver as the single place that knows module strings, keep dependency direction leaf-ward, and test a cold resolution of every catalog name.
- **Thread safety.** CPython has per-module import locks since 3.3 (source 8), so concurrent first imports of the same module serialize and cannot expose a half-initialized module. That does not make an arbitrary lazy registry thread-safe: `lazy_loader` needed a partial-thread-safety fix (PR #90) and recommends newer Python versions to avoid a race (sources 21, 22). A memo dict with an idempotent import is acceptable because the import machinery protects the module itself; avoid multi-step initialization that assumes one winner.
- **Error behaviour.** PEP 562 requires unknown names to raise `AttributeError`; PEP 810 changes when import errors occur (at first use) and chains the traceback to show both the import definition and the access site (source 11); `LazyLoader`'s docs warn about exactly this out-of-context error effect (source 5); pipx documents the same user-visible change when it made imports lazy on 3.15 (source 29). Do not swallow `ImportError`: let it name the missing module, and add a test for the missing-optional-dependency path.
- **Attribute discovery and pickling.** PEP 562 notes that tools performing module attribute discovery may not expect `__getattr__`, and asks authors to keep lazily exposed functions pickleable (source 4). `dir()`, `inspect.getmembers`, some documentation/REPL helpers and `unittest.mock` autospec can trigger imports or see incomplete namespaces.
- **Typing.** Type checkers cannot infer names from a dynamic `__getattr__`; the documented escape hatches are a stub `def __getattr__(name) -> Any: ...` (source 9) or explicit `.pyi` stubs attached by `lazy_loader` (source 21). A `Mapping` facade avoids the problem entirely because the type is static.
- **Packaging and frozen builds.** PyInstaller finds modules statically; imports performed through `importlib.import_module` strings are invisible, so dynamic imports require hidden imports (source 19). scikit-image's frozen build failed on lazy-loader stubs until the stubs were bundled (source 40). Hutch's `desktop/backend.spec` currently calls `collect_all("hutch")`, which collects every submodule, so today's frozen backend is covered; if that ever narrows to a hand-written list, `hutch.tools.*` must be added explicitly.
- **Editable installs.** [PEP 660](https://peps.python.org/pep-0660/) editable installs work through a `.pth` file or import hook configured during `site` processing; the lazy registry itself is indifferent, but a measurement comparing a source checkout against a wheel will see different path/hook overhead. Benchmark the installed console script.
- **Architecture lint.** import-linter and similar tools reason about static imports; imports performed from strings are invisible (source 17). The static `_SPECS` table plus an explicit import-graph test covers what the linter cannot.

### 4.3 Testing import-graph invariants

The strongest pattern found is a subprocess assertion on `sys.modules`, not a timing assertion: pipx's `tests/test_imports.py` runs `python -c "import pipx.main"` and asserts listed heavy modules are absent (sources 28, 30); Typer's lazy-Rich PR added a test asserting Rich is not imported (source 23); Hutch's `tests/test_tool_catalog_lazy.py` follows the same shape for `hutch.cli` and for resolving one catalog entry. This is deterministic, cheap, and fails in the right place when someone re-adds an eager import. Pair it with a catalog parity test (every name resolves to the declared class, module and parameters) and a failure-path test. Keep wall-time gates out of the required CI lane on shared hosts: the programme charter already records host-load drift (R1), and the repository's benchmark gate is the right place for trend numbers.

## 5. Ecosystem and competitor practice

| Tool | Startup/registry approach | Evidence | Lesson |
|---|---|---|---|
| uv / Ruff (Rust) | Native binaries shipped standalone and as PyPI wheels; no interpreter or Python import graph at CLI start | sources 37, 38; local `uv --version` median 8.6 ms (section 9) | Host-language CLIs start in single-digit ms; this is a rewrite, not an import optimisation |
| pipx (Python) | Deferred imports and probes; per-command module import; module `__getattr__` for `pipx.commands`; a subprocess import-graph test; PEP 810 opt-in on 3.15 | sources 27, 28, 29, 30 | A handful of imports dominated 100-150 ms Linux / 320-350 ms Windows; guard tests keep it fixed |
| Poetry (Python, Click/Cleo) | Command imports moved into handlers (per issue comments); startup work tracked in a single issue | source 31 | A Click-era CLI settled around a few hundred ms after lazy command imports; startup was closed as a non-regression |
| dbt (Python, Click) | Import-time analysis with `-X importtime` plus tuna; partial fixes upstream | source 32 | Help/completion invocations amplify startup cost; the import graph, not command logic, dominated 1.2-1.5 s |
| Typer itself | Lazy-loaded its own `rich_utils`/`rich.traceback`; test asserts Rich stays unimported | source 23 | TUI dependencies inside a CLI framework are a real startup tax; lazy imports inside the framework help every Typer app |
| Azure CLI (Python, knack) | Builds a command table; reported to load all command modules on first run, with a request for just-in-time loading | source 34 | Large command tables need lazy or queryable registration |
| AWS CLI v2 (Python) | Loads models and configuration at startup; several hundred ms accepted; users route high-frequency CI calls elsewhere | source 33 | Per-invocation cost matters most in loops/CI, which is Hutch's `version`/`status`/`--help` case too |
| GitHub CLI (Go) | Extensions are `gh-*` executables discovered on PATH and exec'd; no plugin imports into the host | source 36 | Executable plugin boundaries avoid the import-graph problem entirely; not a Python option for in-process tools |
| pytest (Python) | Discovers and imports entry-point plugins at startup; documents `PYTEST_DISABLE_PLUGIN_AUTOLOAD` | source 18; entry-point discovery cost measured in source 41 | Registry discovery itself can be the cost; make discovery lazy or opt-in where semantics allow |
| Meta ML / Cinder | Vendor runtime plus lazy imports; up to 40% TTFB and 20% Jupyter kernel startup improvement | source 39 | At scale, import time is treated as the primary target of startup work |

Two patterns recur: (a) keep the quick path's import graph tiny and explicit, and (b) make the registry know names without importing implementations until dispatch. Nobody in this sample reached single-digit ms in pure Python; the realistic Python target is the low hundreds of milliseconds, which is exactly the D7 bar's terrain.

## 6. Reported failure modes

| Report | What happened | Grade | Implication for a lazy tool registry |
|---|---|---|---|
| pipx 3.15 PEP 810 change | A missing dependency's `ImportError` moved from startup to first use; documented as the one visible change | maintainer | Deferred errors change user experience; keep messages explicit and test missing optional dependencies |
| importlib `LazyLoader` docs | Errors are postponed and "occurring out of context" | docs | Avoid transparent per-module laziness for user-facing CLIs |
| scikit-image #6772 | PyInstaller-frozen app failed on a lazy-loader stub ("Cannot load imports from non-existent stub") until stubs were added | single report, reproducible | Frozen builds need hidden imports/stubs for dynamic loading; verify the desktop backend |
| lazy-loader changelog | Needed a "partially thread-safe" fix (PR #90) and a newer-Python recommendation to avoid a race (PR #102) | maintainer | Concurrent first-use imports need deliberate design, not just a dict |
| PEP 562 notes | `__getattr__` can surprise attribute-discovery tools and break pickling of lazily exposed objects | docs | If module attributes are lazy, keep `__dir__`/stubs and pickle names correct |
| Azure CLI #31541 | First CLI instantiation in CI loads all command modules; reported as a CI slowdown | single report | Command tables are registries too; JIT registration is the fix pattern |
| dbt #9814 | 1.2-1.5 s bare startup made Click shell completion unusable | single report + maintainer | Completion/help must not pay the full import graph; Hutch embeds `ALL_TOOL_NAMES` in help strings, which is safe because they are static |
| AWS CLI #9011 | 0.346 s per invocation; user replaced the CLI in CI with curl (14-15 -> 10-11 min job) | single report + maintainer | Repeated short invocations make per-call savings valuable; CI users are a real constituency |
| Poetry #3502 | User reported roughly 500 ms overhead versus native execution (Poetry 1.0 had been under 350 ms); maintainers lowered it and closed as "not a regression" | single report + maintainer | Without a recorded baseline, slow startup is argued about instead of measured; D3/D7 fix that |
| pytest docs | Plugin autoload at startup is common enough that pytest documents an env var to disable it | docs | Tool/plugin discovery cost is a known failure mode; keep Hutch's catalog a static table, not entry-point scanning |

## 7. Selective-Rust evaluation against ADR-0024 / P11

### 7.1 The bar

`docs/realignment/desktop-production-2026-10-26.md` P11: a Rust native host is required, and any *additional* Rust performance replacement needs "equivalent tests and >=20% p95 or >=30% memory improvement including IPC". ADR-0024 applies that bar to measured kernel candidates, adopts no Rust replacement for validation/JSON/SSE/SQLite/streaming/orchestration, and states that a full or partial rewrite is out of scope per `docs/requirements.md` (which lists "A Rust rewrite" under out of scope). ADR-0001 rejected a Rust control-plane rewrite on measurement, and ADR-0016 deferred a Rust supervisor.

### 7.2 Would a Rust CLI or binary clear the bar?

Numerically, a whole-CLI Rust binary would clear >=20% p95 startup easily. The local spot-check measured `uv --version` at 8.6 ms median versus `hutch version` at 412.9 ms median, and a Rust implementation would not pay the ~24 ms interpreter floor or ~279 ms import graph (section 9). So the threshold is not the obstacle.

The decision frame is: P11 authorises a *replacement of a measured Python kernel* after equivalent tests; it does not authorise rewriting the Python CLI. The CLI is a console script (`hutch = hutch.cli:main`), the Tauri host is already Rust, and the desktop app freezes the Python backend rather than reimplementing it (`desktop/backend.spec`, `desktop/backend_entry.py`). A CLI rewrite would have to reproduce 2,760 lines of command behaviour, the Typer parsing/help/error text that D9 requires to stay byte-identical, every tool registration, the approval/local-first semantics, completion and packaged distribution, in a second language, permanently. That is a rewrite with rewrite-class risk, not a kernel substitution. ADR-0024's own revisit conditions are about a measured >20% p95 kernel candidate outside security/contract-critical paths; a whole-CLI rewrite does not satisfy them.

### 7.3 Would a native import accelerator clear it?

There is no credible general mechanism. Import cost is the execution of Python module top-level code (bytecode), object creation and file I/O; a PyO3/C extension cannot execute arbitrary third-party module bodies faster than CPython without reimplementing those modules. The available native-ish levers are narrower:

- Frozen stdlib modules (Python 3.11+) already remove startup work and cannot cover third-party imports.
- `.pyc` precompilation at install time (pip does it; uv can with `--compile-bytecode`) removes first-run compile cost but not execution.
- PyInstaller freezing (desktop only) changes the loader, not the bytecode execution cost, and is already how the desktop backend ships.
- PEP 810 (Python 3.15) is the sanctioned interpreter-level lazy mechanism; it is explicit, opt-in, and not available while Hutch's floor is 3.11.
- A native launcher that execs Python adds a process boundary; it does not remove interpreter or import time.

The memory half of P11 is also a poor fit: a CLI process is transient, and the desktop process memory is dominated by long-lived Pydantic/Rich/FastAPI state rather than the CLI entry point.

### 7.4 Verdict

**Not applicable for this programme.** A Rust CLI would pass the numeric bar but is a rewrite, explicitly out of scope (ADR-0001, ADR-0016, ADR-0024, `docs/requirements.md`), and cost/risk-dominated; a native import accelerator has no mechanism that would pass the bar for third-party imports. Do not recommend a rewrite. Revisit only under ADR-0024's existing conditions, and take the Python 3.15 PEP 810 route first if startup work continues after this programme.

| Rust/native candidate | P11 bar (>=20% p95 or >=30% memory, after equivalent tests) | Decision |
|---|---|---|
| Whole-CLI Rust rewrite | would clear the numeric bar mechanically (local `uv --version` 8.6 ms vs `hutch version` 412.9 ms medians) | **Not applicable / rejected**: a rewrite, out of scope by ADR-0001/0016/0024 and `docs/requirements.md`; P11 governs kernel replacement, not CLI rewrites; equivalent-tests and two-language maintenance cost |
| Optional Rust/native import accelerator (PyO3/C extension, frozen modules, native launcher) | no credible path to >=20% for third-party imports | **Not applicable**: import cost is Python bytecode execution and I/O; frozen modules cover the stdlib only; PyInstaller changes the loader for the desktop build only; a launcher adds a process boundary |
| Python-side lazy registry plus quick-path split (section 8) | to be measured by D7 (>=20% median startup on quick commands is the programme bar) | **Adopt**: low risk, behaviour-preserving, no new dependency or boundary |

## 8. Recommendations for Hutch, ranked

1. **Adopt and keep the static-spec-table plus first-use resolver pattern** (the D6 shape). `_SPECS` stays a literal name -> (module, class) table; `_tool_class` memoizes `importlib.import_module` results; `_CATALOG` remains a read-only `Mapping` so `_CATALOG[name]`, `keys/items/values`, `in`, `len` and iteration keep their semantics; `ALL_TOOL_NAMES`, `GROUPS`, `expand_tools` and `build_tools` signatures stay unchanged. Evidence: SPEC 1, pipx PRs #2113/#2128, Typer PR #1128 (sources 20, 27, 28, 23). Cost: low; risk: low. Current worktree implementation and `tests/test_tool_catalog_lazy.py` already follow this; the research recommends keeping it and extending the guards rather than changing the design.
2. **Keep deterministic import-graph guards, not timing gates.** In a subprocess assert that importing `hutch.cli` leaves `hutch.tools.documents`, `hutch.tools.synthesis`, `hutch.tools.media`, `hutch.tools.live`, `hutch.tools.workspace_actions`, `hutch.synthesis`, `hutch.media`, `hutch.grounding` and `hutch.bot_deletion` out of `sys.modules`; keep the every-name parity test (class name, module, tool name, JSON-schema dict); add a failure-path test where a spec entry points at a missing module and the resulting `ModuleNotFoundError` names that module. Evidence: pipx `test_imports.py`, Typer's Rich test, existing Hutch test (sources 28, 30, 23). Cost: low; risk: low. This is the regression guard the charter asks for.
3. **Slim the quick-command path one measured step further: move the pure name data out of the registry package.** `hutch.cli` imports only `ALL_TOOL_NAMES` and `expand_tools` at module scope, but that import executes `hutch.tools.__init__` and `.base`; a dependency-free module (for example `src/hutch/tool_names.py` holding `_SPECS` names, `GROUPS`, `ALL_TOOL_NAMES`, `expand_tools`) re-exported by `hutch.tools` would let the quick path skip the registry closure without changing any public name. Measure the *marginal* delta first: the measured `import hutch.tools` total (220 ms minimum locally) overstates the saving because `cli.py` already imports Pydantic/models/config/store, which overlap with `.base`. Cost: medium-low; risk: low (pure re-export); decision: adopt only with a D4 marginal measurement.
4. **Defer the remaining known eager import in the command layer.** `src/hutch/cli.py` imports `install_bot_destroy_command` at module scope; D6 targets deferring the bot-deletion command layer (including `hutch.bot_deletion`, which `src/hutch/cli_bot_deletion.py` needs) until `hutch bot destroy` runs. Keep the registration API identical (`install_bot_destroy_command(bot_app, ...)`) and verify `hutch bot --help` still lists the subcommand. Cost: low; risk: low (focused tests exist for the deletion path).
5. **Define first-use semantics explicitly.** One resolver, one memo dict, no `except ImportError: pass`; unknown names raise `KeyError` exactly as the current `Mapping` contract does; a missing module raises `ModuleNotFoundError` naming the module. Rely on CPython's per-module locks for concurrent first use and add a threaded smoke test that resolves the whole catalog concurrently (source 8; lazy-loader race evidence sources 21, 22). For `hutch serve`, only add a startup warm-up if a measurement shows a user-visible first-call stall; otherwise leave resolution on demand. Cost: low; risk: low.
6. **Protect typing and frozen packaging.** Keep `_CATALOG` annotated as `Mapping[str, type[Tool]]` so type checkers need no stubs; do not add a module-level `__getattr__` unless an external caller needs `from hutch.tools import SomeTool` (in-repo calls import only `Tool`, `ToolContext`, `ToolResult`, `build_tools`, `expand_tools`, `GROUPS`, `ALL_TOOL_NAMES`, `_CATALOG`, `_SPECS`, `_tool_class`; external consumers are unverified). If `__getattr__` is added, ship a stub or `TYPE_CHECKING` imports (sources 9, 21). Keep `collect_all("hutch")` in `desktop/backend.spec`; if the freeze is ever narrowed, generate hidden imports for every `hutch.tools.<module>` in `_SPECS` and test the frozen app (sources 19, 40). Cost: low; risk: moderate if packaging changes are untested.
7. **Institutionalise the measurement recipe.** Attribution: `-X importtime` (min of N, per-top-level self sums, target cumulative), `-X importtime=2` on 3.14+ when cached-import visibility matters. Claim: fresh-process wall time on the installed console script, interleaved before/after in one driver, median ratio as the claim, p95 and CV reported (the charter's R1 mitigation). Floor: pyperformance-style `python -c pass` each session to detect environment drift; existing `benchmarks/hotpath_workloads/startup.py` (`n=11`, isolated state dir) is the trend harness. Cost: low; risk: low.
8. **Defer PEP 810 adoption, but track it.** `lazy import` and `sys.set_lazy_imports` become available at Python 3.15; Hutch's floor is 3.11, so the current registry pattern is the right cross-version answer. Do not enable `sys.set_lazy_imports("all")` in a user-facing CLI: PEP 690's rejection and pipx's visible error-timing change show why transparent global laziness is risky, and pipx measured only a few extra milliseconds beyond its explicit deferrals (sources 10, 11, 29). Revisit when the minimum Python version is raised. Cost: none now; risk: none now.

## 9. Local spot-check (informational, not the D3/D4 baseline)

Host: 8 CPUs, load average 5.41/5.92/3.96, Linux; venv `/home/kevina/CodingProjects/hutch/.venv`, Python 3.13.15 (`Clang 22.1.3`), `PYTHONPATH=src` in the programme worktree. `import hutch.cli` samples were 279.2, 315.3 and 344.6 ms (minimum shown). Wall times: 15 fresh-process samples per command, one after another, no interleaving; this is a snapshot for reasoning about magnitudes, not a controlled benchmark.

| Import target | Min total ms (3 runs) | Largest self-time buckets (ms) |
|---|---|---|
| `typer` | 56.0 | typer 18.5; typing 3.1; encodings 2.5 |
| `click` | 29.7 | click 8.1; typing 3.2; inspect 2.9 |
| `rich.console` | 47.5 | rich 24.9; re 3.0; typing 2.7 |
| `pydantic` | 47.8 | pydantic_core 14.4; typing_inspection 4.3; pydantic 3.8 |
| `hutch.tools` | 220.2 | hutch 89.2; pydantic 37.4; pydantic_core 20.4; annotated_types 8.8 |
| `hutch.tools.documents` | 221.5 | hutch 93.1; pydantic 37.9; pydantic_core 19.9 |
| `hutch.cli` | 279.2 | hutch 96.0; pydantic 46.5; rich 24.3; typer 14.3; pydantic_core 14.2 |

| Fresh-process command | n | Min ms | Median ms | p95 ms |
|---|---|---|---|---|
| `python -c pass` | 15 | 22.8 | 24.3 | 27.1 |
| `hutch version` | 15 | 387.1 | 412.9 | 490.6 |
| `hutch --help` | 15 | 372.5 | 551.1 | 759.1 |
| `uv --version` (Rust binary) | 15 | 6.7 | 8.6 | 41.7 |

Reading: interpreter/site floor is ~24 ms (~6% of `hutch version`); the `hutch.cli` import graph is ~279 ms minimum; the remainder is CLI dispatch plus state/config work and host noise. `hutch.tools` at 220 ms is mostly the shared Pydantic/models closure, so the marginal saving of removing that package import from the quick path must be measured, not assumed. The `hutch --help` p95 is much worse than `version`; the likely cause is help rendering under a loaded host, but this snapshot does not decompose it (open question). This snapshot already included lazy tool-class resolution and is not a before/after pair.

Reproduce (read-only, from the worktree): `PYTHONPATH=src /home/kevina/CodingProjects/hutch/.venv/bin/python -X importtime -c 'import hutch.cli' 2>&1 | tail -n 3`; wall time with a loop of `time.perf_counter()` around `subprocess.run([hutch, 'version'], ...)` with a temporary `HUTCH_STATE_DIR`; `uv --version` for the Rust comparison. The official baseline, aggregation script and sample counts remain D3/D4 deliverables.

## 10. Open questions and unverified claims

- The local spot-check is one session on a loaded host (load average 5.4 on 8 CPUs) with a worktree that already contained the in-flight lazy-catalog change. It must not be quoted as the baseline; D3/D4 will produce the controlled numbers.
- The `hutch --help` median and p95 in section 9 are noisy and not explained by a decomposition; help rendering, Typer command construction and host load are all candidates. Unverified.
- Third-party numbers (Typer 45%, pipx medians, Meta 20-40%, Poetry/dbt/AWS/Azure reports) are self-reported or single-host; none was independently replicated here. They are used for direction and mechanism, not as Hutch targets.
- Whether first-use tool imports can stall a running `hutch serve` event loop is not measured. The theoretical risk is real (synchronous import inside async dispatch); the fix is to preload or offload only if measurement shows a stall.
- Whether any external caller does `from hutch.tools import SomeToolClass` is unknown. In-repo grep finds no such import, so a Mapping facade without module `__getattr__` preserves all in-repo call sites, but public API consumers are unverified.
- Whether the frozen desktop backend's startup improves with the lazy registry is unmeasured; PyInstaller's loader and import graph differ from a source install, and `collect_all("hutch")` still bundles every submodule.
- Whether raising Hutch's minimum Python to 3.15 (for PEP 810) is acceptable is a product/packaging decision and was not researched here.
- `-X importtime` totals include filesystem and page-cache effects; section 9 used minimum of three runs on a warm bytecode cache. Absolute values are host-specific; only ratios and module ordering are portable.
- No peer-reviewed study of Python CLI cold start was found; the strongest evidence in this record is primary documentation plus maintainer measurements.

## 11. Repository references

- ADR-0001, ADR-0016, ADR-0024: `docs/adr/`.
- P11 bar: `docs/realignment/desktop-production-2026-10-26.md`.
- Out-of-scope Rust rewrite: `docs/requirements.md` ("Out of scope (unchanged)").
- Recorded baseline: `docs/performance.md` (275 ms `hutch status`, minimum of 11 cold-process runs).
- Trend harness: `benchmarks/hotpath_workloads/startup.py`; gate `python -m benchmarks.run --check`; baseline JSON under `benchmarks/results/`.
- Registry/CLI: `src/hutch/tools/__init__.py`, `src/hutch/cli.py`, `src/hutch/cli_bot_deletion.py`; guard tests `tests/test_tool_catalog_lazy.py`.
- Frozen desktop backend: `desktop/backend.spec`, `desktop/backend_entry.py`.
- Evidence that overrides or extends this record: `docs/perf/results-2026-10-29.md`, `docs/research/performance-rust-2026-10-29.md`.
