"""Focused hot-path workload modules for benchmarks.hotpaths.

One module per subsystem; one case is one function. Each module exposes:

    run(quick: bool, state: Path) -> list[dict]

A returned dict is one measurement:

    {"name": str, "unit": str, "samples": list[float], "better": "lower"|"higher"|None,
     "note": str, "detail": dict}

The runner (benchmarks/hotpaths.py) owns per-case state isolation by exporting
HUTCH_STATE_DIR before the module imports hutch; state is removed afterwards.
"""

from __future__ import annotations

#: (name, module path, one-line description) in report order.
MODULES: tuple[tuple[str, str, str], ...] = (
    ("validation", "benchmarks.hotpath_workloads.validation",
     "tool-call validation over the real catalog + jsonschema validator construction"),
    ("streaming", "benchmarks.hotpath_workloads.streaming",
     "OpenAI streaming tool-call assembly at 2 KB / 20 KB / 200 KB argument payloads"),
    ("events", "benchmarks.hotpath_workloads.events",
     "Event / SSE serialization: model_dump+json.dumps vs model_dump_json"),
    ("store", "benchmarks.hotpath_workloads.store_events",
     "SQLite event append throughput + list_events read latency at 1k / 10k events"),
    ("context", "benchmarks.hotpath_workloads.context",
     "prompt_tokens / count_tokens over 10 / 100 / 400-message transcripts"),
    ("workspace", "benchmarks.hotpath_workloads.workspace",
     "list_files tool (os.walk) discovery on 1k / 5k-file workspaces"),
    ("startup", "benchmarks.hotpath_workloads.startup",
     "cold CLI subprocess startup: hutch version / hutch status"),
    ("documents", "benchmarks.hotpath_workloads.documents",
     "xlsx document generation at 500 / 5000 rows (optional)"),
    ("dashboard", "benchmarks.hotpath_workloads.dashboard",
     "seeded dashboard-scale reads through the FastAPI app (50+ bots, 10k events)"),
)


def tool_catalog():
    """The real built-in tool registry (name -> Tool class); imports hutch lazily."""
    from hutch.tools import _CATALOG
    return _CATALOG


def tool_schemas(names: list[str] | None = None) -> dict[str, dict]:
    """Canonical parameters schemas from the real tool catalog."""
    catalog = tool_catalog()
    selected = names or sorted(catalog)
    out: dict[str, dict] = {}
    for name in selected:
        if name in catalog:
            out[name] = catalog[name]().parameters
    return out
