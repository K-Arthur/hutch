"""Tool-call validation: the real catalog through validate_call, analyze_schema alone, jsonschema cost.

(a) times hutch.toolcalling.validate.validate_call for realistic valid args and a few invalid
args across every tool in hutch.tools._CATALOG, plus analyze_schema alone and per-tool medians.
(b) times Draft202012Validator(schema) construction versus a cached validator reused per call,
in memory only (no source edits): this quantifies the per-call validator construction cost the
production path currently pays.
"""

from __future__ import annotations

import time

SAMPLES_FULL = 200   # cheap in-process case: enough samples for a meaningful p95
SAMPLES_QUICK = 3
AGGREGATE_LOOPS = 10
TOOL_LOOPS = 20


def _valid_args() -> dict[str, dict]:
    """Realistic valid arguments for every built-in tool (one call each)."""
    return {
        "shell": {"command": "ls -la src/hutch/toolcalling"},
        "read_file": {"path": "reports/week-31.md"},
        "list_files": {"path": "reports"},
        "write_file": {"path": "out/summary.md", "content": "# Summary\n\nThree findings.\n"},
        "remember": {"key": "preferred-format", "value": "Use Markdown tables when comparing options."},
        "recall": {"query": "preferred format"},
        "web_fetch": {"url": "https://example.com/article/2026/10/hutch-performance"},
        "create_document": {
            "format": "xlsx", "filename": "Q4 report.xlsx", "title": "Q4 report",
            "content": {"sheets": [{"name": "Summary", "rows": [["Metric", "Value"], ["Revenue", 4200]]}]},
        },
        "revise_document": {"document_id": "doc_abc123", "expected_version": 3,
                            "content": {"text": "revised body text"}},
        "inspect_document": {"document_id": "doc_abc123", "version": 3},
        "create_media": {"kind": "image", "prompt": "a watercolor fox in a pine forest", "width": 1024,
                         "height": 1024},
        "render_diagram": {
            "title": "Ingest to render pipeline",
            "nodes": [{"id": "ingest", "label": "Ingest"}, {"id": "render", "label": "Render"}],
            "edges": [{"from": "ingest", "to": "render", "label": "bytes"}],
        },
        "run_python": {"code": "print(sum(i * i for i in range(10)))"},
        "reset_workspace": {},
        "delegate_task": {"task": "Summarize the three release notes in notes/ into one paragraph."},
        "live_search": {"question": "what changed for free-threaded CPython in 2026?"},
        "inspect_media": {"url": "https://example.com/clip.mp4", "claim": "the sign reads 42",
                          "times_ms": [1200, 3400]},
        "ingest_source": {"kind": "paper", "path": "papers/attention.pdf",
                          "title": "Attention Is All You Need", "author": "Vaswani et al."},
        "register_manifest": {
            "manifest": {"sources": [{"id": "s1", "title": "Fixture"}], "spans": [], "claims": [],
                         "audience": "engineers", "language": "en", "depth": "brief", "policy": "strict",
                         "caveats": [], "contradictions": [], "outputs": ["audio_overview"]},
        },
        "register_script": {
            "manifest_id": "man_abc123",
            "script": {"chapters": [{"title": "Intro", "utterances": [
                {"speaker": "guide", "kind": "speech", "text": "Welcome to the overview."}]}]},
        },
        "render_audio_overview": {"manifest_id": "man_abc123", "script_artifact_id": "art_abc123"},
        "render_infographic": {"manifest_id": "man_abc123"},
        "plan_workspace_action": {
            "intent": "Create the weekly handout",
            "steps": [{"kind": "read", "title": "Read notes",
                       "target": {"service": "files", "account": None, "resource_id": None,
                                  "parent_id": None, "display": "notes/", "audience": None},
                       "inputs": {}, "depends_on": []}],
        },
        "run_workspace_plan": {"plan_id": "plan_abc123", "approved_hash": "sha256:deadbeef"},
        "draft_workflow": {"plan": {"schema_version": 1, "name": "weekly-review", "steps": []}},
    }


def _invalid_args() -> list[tuple[str, object]]:
    """A few representative invalid calls: missing required, wrong type, bad enum, wrong container."""
    return [
        ("shell", {"command": 123}),
        ("read_file", {}),
        ("write_file", {"path": "out/summary.md"}),
        ("create_document", {"format": "odt", "filename": "x.odt", "title": "x", "content": {}}),
        ("remember", {"key": "preferred-format"}),
        ("create_media", {"kind": "hologram", "prompt": "a fox"}),
        ("render_diagram", {"title": "Pipeline", "nodes": "ingest,render", "edges": []}),
        ("run_workspace_plan", {"plan_id": 7, "approved_hash": 9}),
    ]


def _time_batch(call, loops: int) -> float:
    started = time.perf_counter()
    for _ in range(loops):
        call()
    return time.perf_counter() - started


def _per_call_us(call, loops: int, calls_per_loop: int) -> float:
    return _time_batch(call, loops) / (loops * calls_per_loop) * 1_000_000


def _jsonschema_cases(schema: dict, args: dict, n: int, engine: str) -> list[dict]:
    from jsonschema import Draft202012Validator

    def make_us(fn) -> list[float]:
        return [fn() for _ in range(n)]

    def construct() -> float:
        return _per_call_us(lambda: Draft202012Validator(schema), 20, 1)

    def uncached_validate() -> float:
        def run() -> None:
            list(Draft202012Validator(schema).iter_errors(args))
        return _per_call_us(run, 20, 1)

    cached = Draft202012Validator(schema)

    def cached_validate() -> float:
        return _per_call_us(lambda: list(cached.iter_errors(args)), 20, 1)

    construct_samples = make_us(construct)
    uncached_samples = make_us(uncached_validate)
    cached_samples = make_us(cached_validate)
    ratios = [construct / uncached * 100 if uncached else 0.0
              for construct, uncached in zip(construct_samples, uncached_samples)]
    note = f"engine={engine}; construction is ~{sorted(ratios)[len(ratios) // 2]:.0f}% of a construct+validate call"
    return [
        {"name": "jsonschema.construct_validator_us", "unit": "us", "samples": construct_samples,
         "better": "lower", "note": note},
        {"name": "jsonschema.cached_validate_us", "unit": "us", "samples": cached_samples,
         "better": "lower", "note": "one Draft202012Validator reused"},
        {"name": "jsonschema.uncached_validate_us", "unit": "us", "samples": uncached_samples,
         "better": "lower", "note": "construct + iter_errors per call (production shape)"},
        {"name": "jsonschema.construct_share_of_uncached", "unit": "%",
         "samples": ratios, "better": "lower",
         "note": "paired per-sample ratio; = share of a construct+validate call spent building the validator"},
    ]


def _cached_validator(schemas: dict[str, dict]):
    """In-memory alternative: analyze each schema once, reuse one Draft validator per schema.

    No source edit: this wraps validate's own bounded checker (_errors) and the jsonschema
    Draft202012Validator to quantify the share of validate_call that a production cache would
    remove (analyze_schema + validator construction). It is a measurement sketch, not a fix.
    """
    from hutch.toolcalling.validate import _HAVE_JSONSCHEMA, _Draft202012Validator, _errors, analyze_schema

    cache: dict[str, tuple[object, object]] = {}
    for name, schema in schemas.items():
        report = analyze_schema(schema)
        if report.unsupported:
            raise RuntimeError(f"schema for {name} cannot be certified; cached comparison invalid")
        cache[name] = (report, _Draft202012Validator(schema) if _HAVE_JSONSCHEMA else None)

    def validate(name: str, args: object) -> list[str]:
        _report, validator = cache[name]
        problems: list[str] = []
        _errors(args, schemas[name], "", schemas[name], problems, depth=0, ref_seen=frozenset())
        if problems:
            return problems
        if validator is not None:
            return [error.message for error in validator.iter_errors(args)]
        return []

    return validate


def run(quick: bool, state) -> list[dict]:
    from benchmarks.hotpath_workloads import tool_schemas

    from hutch.toolcalling.validate import (analyze_schema, schema_engine, validate_call)
    from hutch.toolcalling.validate import _Draft202012Validator as Draft202012Validator

    engine = schema_engine()
    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    schemas = tool_schemas()
    valid = _valid_args()
    missing = sorted(set(schemas) - set(valid))
    if missing:
        raise RuntimeError(f"no realistic args fixture for tools: {missing}")
    extra = sorted(set(valid) - set(schemas))
    if extra:
        raise RuntimeError(f"fixture names tools that are not in the catalog: {extra}")

    problems = {name: validate_call(schemas[name], args) for name, args in valid.items()}
    broken = {name: detail for name, detail in problems.items() if detail}
    if broken:
        raise RuntimeError(f"valid-args fixtures rejected by the current catalog: {broken}")
    invalid = _invalid_args()
    unexpected_pass = [name for name, args in invalid if not validate_call(schemas[name], args)]
    if unexpected_pass:
        raise RuntimeError(f"invalid-args fixtures accepted (fix the fixture, not the code): {unexpected_pass}")

    cases: list[dict] = []

    def measure_valid() -> list[float]:
        from hutch.toolcalling.validate import validate_call as call

        samples = []
        for _ in range(n):
            started = time.perf_counter()
            for _loop in range(AGGREGATE_LOOPS):
                for name, args in valid.items():
                    call(schemas[name], args)
            elapsed = time.perf_counter() - started
            samples.append(elapsed / (AGGREGATE_LOOPS * len(valid)) * 1_000_000)
        return samples

    def measure_invalid() -> list[float]:
        from hutch.toolcalling.validate import validate_call as call

        samples = []
        for _ in range(n):
            started = time.perf_counter()
            for _loop in range(AGGREGATE_LOOPS):
                for name, args in invalid:
                    call(schemas[name], args)
            elapsed = time.perf_counter() - started
            samples.append(elapsed / (AGGREGATE_LOOPS * len(invalid)) * 1_000_000)
        return samples

    def measure_analysis() -> list[float]:
        samples = []
        for _ in range(n):
            started = time.perf_counter()
            for _loop in range(AGGREGATE_LOOPS):
                for schema in schemas.values():
                    analyze_schema(schema)
            elapsed = time.perf_counter() - started
            samples.append(elapsed / (AGGREGATE_LOOPS * len(schemas)) * 1_000_000)
        return samples

    per_tool: dict[str, float] = {}
    for name, args in valid.items():
        per_tool[name] = _per_call_us(lambda name=name, args=args: validate_call(schemas[name], args),
                                      TOOL_LOOPS, 1)
    valid_samples = measure_valid()
    cases.append({"name": "validation.validate_call_valid_us", "unit": "us", "samples": valid_samples,
                  "better": "lower", "note": f"engine={engine}; {len(valid)} tools, real schemas + args",
                  "detail": {"per_tool_us": dict(sorted(per_tool.items(), key=lambda row: -row[1]))}})
    invalid_samples = measure_invalid()
    cases.append({"name": "validation.validate_call_invalid_us", "unit": "us", "samples": invalid_samples,
                  "better": "lower", "note": f"{len(invalid)} invalid calls; first problem only"})
    analysis_samples = measure_analysis()
    cases.append({"name": "validation.analyze_schema_us", "unit": "us", "samples": analysis_samples,
                  "better": "lower", "note": "static schema walk alone (no validation)"})

    # Direct A/B: current validate_call vs the cacheable variant, same inputs, same process.
    cached_validate = _cached_validator(schemas)
    for name, args in valid.items():
        if cached_validate(name, args):
            raise RuntimeError(f"cached-validator A/B disagrees on valid args for {name}")
    for name, args in invalid:
        if not cached_validate(name, args):
            raise RuntimeError(f"cached-validator A/B accepted invalid args for {name}")

    cached_samples: list[float] = []
    for _ in range(n):
        started = time.perf_counter()
        for _loop in range(AGGREGATE_LOOPS):
            for name, args in valid.items():
                cached_validate(name, args)
        elapsed = time.perf_counter() - started
        cached_samples.append(elapsed / (AGGREGATE_LOOPS * len(valid)) * 1_000_000)
    cases.append({"name": "validation.cached_engine_valid_us", "unit": "us", "samples": cached_samples,
                  "better": "lower",
                  "note": "in-memory alternative: analyze_schema cached once + one reused Draft202012Validator"})
    speedups = [current / cached if cached else 0.0 for current, cached in zip(valid_samples, cached_samples)]
    cases.append({"name": "validation.cached_engine_speedup_ratio", "unit": "x", "samples": speedups,
                  "better": "higher",
                  "note": f"current validate_call / cached-engine cost; median {sorted(speedups)[len(speedups) // 2]:.2f}x"})

    cases.extend(_jsonschema_cases(schemas["shell"], valid["shell"], n, engine))
    return cases
