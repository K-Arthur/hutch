"""Analysis for the dashboard live-update browser A/B: medians, ratios, noise floor.

Everything is derived from raw per-rep evidence (fetch, mutation, long-task, rAF
frame and stream-message records). Windows are commit-relative: -5 ms to +400 ms
around the server commit mapped into the page performance timeline.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .stats import _summarize_metrics, median, percentile, stats

KEY_METRICS = (
    "refetches_per_burst",
    "commit_to_render_ms",
    "longtask_ms_per_burst",
    "longtask_count_per_burst",
    "dom_apply_ms",
    "data_to_dom_ms",
    "dom_nodes",
    "overflow_px",
    "forced_layout_ms",
    "frame_gap_median_ms",
    "frame_gap_p95_ms",
    "frame_gaps_over_50",
)

BURST_METRICS = (
    "refetches", "events_requests", "run_stream_opens", "changes_stream_opens",
    "run_batch_messages", "change_messages", "commit_to_render_ms", "data_to_dom_ms",
    "innerhtml_ms", "insert_html_ms", "json_parse_ms", "dom_apply_ms",
    "longtask_ms", "longtask_count", "fetch_wait_ms", "mutation_batches",
)


# ------------------------------------------------------------------- derive

def _path(url: str) -> str:
    try:
        return urlsplit(url or "").path
    except ValueError:
        return ""


def _frames_for(rep: dict) -> list:
    measurement = rep.get("measurement") or {}
    snapshot = measurement.get("snapshot") or {}
    return snapshot.get("frames") or []


def derive_bursts(rep: dict) -> list:
    """Per-burst metrics from the raw snapshot attached to one measured rep."""
    measurement = rep.get("measurement") or {}
    snapshot = measurement.get("snapshot") or {}
    run_id = measurement.get("run_id") or ""
    run_path = "/api/runs/" + run_id
    fetches = snapshot.get("fetches") or []
    streams = snapshot.get("streams") or []
    longtasks = snapshot.get("longtasks") or []
    json_parses = snapshot.get("jsonParses") or []
    html_sets = snapshot.get("innerHTMLSets") or []
    insert_calls = snapshot.get("insertHTMLCalls") or []
    mutations = snapshot.get("mutations") or []
    derived = []
    burst_list = measurement.get("bursts") or []
    for position, burst in enumerate(burst_list):
        commit = float(burst.get("browser_commit_ms") or 0.0)
        await_info = burst.get("await") or {}
        render_at = await_info.get("renderAt")
        settled_at = await_info.get("settledAt")
        settled = max([value for value in (render_at, settled_at, commit) if value is not None])
        quiet_end = float(burst.get("quiet_end_ms") or settled + 400.0)
        window_start = commit - 5.0
        window_end = max(quiet_end + 50.0, settled + 100.0)
        if position + 1 < len(burst_list) and burst_list[position + 1].get("browser_commit_ms"):
            window_end = min(window_end, float(burst_list[position + 1]["browser_commit_ms"]) - 2.0)
        in_window = [fetch for fetch in fetches
                     if fetch.get("start") is not None and window_start <= fetch["start"] <= window_end]
        refetches = [fetch for fetch in in_window if _path(fetch.get("url")) == run_path]
        events_requests = [fetch for fetch in in_window if _path(fetch.get("url")) == run_path + "/events"]
        stream_opens = [stream for stream in streams
                        if window_start <= stream.get("start", -1) <= window_end]
        messages = []
        for stream in streams:
            for message in stream.get("messages") or []:
                if window_start <= message.get("t", -1) <= window_end:
                    messages.append({"url": stream.get("url", ""), **message})
        change_messages = [message for message in messages if "/changes/stream" in message["url"]]
        batch_messages = [message for message in messages if run_path + "/stream" in message["url"]]
        resources: dict = {}
        for message in change_messages:
            for name, count in (message.get("resources") or {}).items():
                resources[name] = resources.get(name, 0) + count
        overlapping = [task for task in longtasks
                       if task["start"] < window_end and task["start"] + task["dur"] > window_start]
        longtask_ms = sum(max(0.0, min(task["start"] + task["dur"], window_end)
                              - max(task["start"], window_start)) for task in overlapping)
        json_ms = sum(float(entry["ms"]) for entry in json_parses
                      if entry.get("ms") is not None and window_start <= entry["start"] <= window_end
                      and _path(entry.get("url")) == run_path)
        innerhtml_ms = sum(float(entry["ms"]) for entry in html_sets
                           if window_start <= entry["t"] <= window_end)
        insert_ms = sum(float(entry["ms"]) for entry in insert_calls
                        if window_start <= entry["t"] <= window_end)
        mutation_window = [entry for entry in mutations if window_start <= entry["t"] <= window_end]
        fetch_ends = [fetch["end"] for fetch in refetches if fetch.get("end") is not None]
        anchor = max(fetch_ends) if fetch_ends else commit
        data_to_dom = (mutation_window[-1]["t"] - anchor) if mutation_window else None
        derived.append({
            "index": burst.get("index"),
            "commit_to_render_ms": (round(burst["render_ms"], 4)
                                    if burst.get("render_ms") is not None else None),
            "timed_out": bool(await_info.get("timedOut")),
            "refetches": len(refetches),
            "events_requests": len(events_requests),
            "run_stream_opens": len([stream for stream in stream_opens
                                     if run_path + "/stream" in stream.get("url", "")]),
            "changes_stream_opens": len([stream for stream in stream_opens
                                         if "/changes/stream" in stream.get("url", "")]),
            "run_batch_messages": len(batch_messages),
            "change_messages": len(change_messages),
            "change_msg_types": sorted({message.get("type") for message in change_messages}),
            "change_resources": resources,
            "fetch_wait_ms": round(sum(fetch["end"] - fetch["start"] for fetch in refetches
                                       if fetch.get("end") is not None), 4),
            "json_parse_ms": round(json_ms, 4),
            "innerhtml_ms": round(innerhtml_ms, 4),
            "insert_html_ms": round(insert_ms, 4),
            "dom_apply_ms": round(innerhtml_ms + insert_ms, 4),
            "mutation_batches": len(mutation_window),
            "data_to_dom_ms": round(data_to_dom, 4) if data_to_dom is not None else None,
            "longtask_ms": round(longtask_ms, 4),
            "longtask_count": len(overlapping),
            "notes_after": await_info.get("notesAfter"),
            "probe": burst.get("probe") or {},
            "scroll_phase": bool(burst.get("scroll_phase")),
        })
    return derived


def rep_metrics(rep: dict) -> dict:
    """One scalar per metric per rep (medians over that rep's bursts)."""
    measurement = rep.get("measurement") or {}
    bursts = derive_bursts(rep)
    if not bursts:
        return {}
    def per_burst(key):
        return median([burst.get(key) for burst in bursts])
    frames = _frames_for(rep)
    gaps = [frames[index] - frames[index - 1] for index in range(1, len(frames))
            if frames[index] >= frames[index - 1]]
    probes = [burst.get("probe") or {} for burst in bursts]
    initial = measurement.get("initial_probe") or {}
    final = measurement.get("final_probe") or {}
    forced = [probe.get("forced_ms") for probe in probes if probe.get("forced_ms") is not None]
    if initial.get("forced_ms") is not None:
        forced.append(initial["forced_ms"])
    snapshot = measurement.get("snapshot") or {}
    longtasks = snapshot.get("longtasks") or []
    return {
        "refetches_per_burst": per_burst("refetches"),
        "events_requests_per_burst": per_burst("events_requests"),
        "run_stream_opens_per_burst": per_burst("run_stream_opens"),
        "changes_stream_opens_per_burst": per_burst("changes_stream_opens"),
        "run_batch_messages_per_burst": per_burst("run_batch_messages"),
        "changes_messages_per_burst": per_burst("change_messages"),
        "commit_to_render_ms": per_burst("commit_to_render_ms"),
        "data_to_dom_ms": per_burst("data_to_dom_ms"),
        "fetch_wait_ms": per_burst("fetch_wait_ms"),
        "innerhtml_ms": per_burst("innerhtml_ms"),
        "insert_html_ms": per_burst("insert_html_ms"),
        "json_parse_ms": per_burst("json_parse_ms"),
        "dom_apply_ms": per_burst("dom_apply_ms"),
        "longtask_ms_per_burst": per_burst("longtask_ms"),
        "longtask_count_per_burst": per_burst("longtask_count"),
        "mutation_batches_per_burst": per_burst("mutation_batches"),
        "render_timeouts": sum(1 for burst in bursts if burst.get("timed_out")),
        "dom_nodes": final.get("dom_nodes"),
        "initial_dom_nodes": initial.get("dom_nodes"),
        "overflow_px": max(abs(final.get("overflow") or 0), abs(initial.get("overflow") or 0)),
        "forced_layout_ms": median(forced),
        "frame_gap_median_ms": median(gaps),
        "frame_gap_p95_ms": percentile(gaps, 95),
        "frame_gaps_over_50": sum(1 for gap in gaps if gap > 50.0),
        "frame_count": len(gaps),
        "page_load_ms": measurement.get("page_load_ms"),
        "total_longtask_ms": round(sum(task["dur"] for task in longtasks), 4),
        "total_longtask_count": len(longtasks),
        "page_errors": len(measurement.get("page_errors") or []),
        "bursts_measured": len(bursts),
    }


# ----------------------------------------------------------------- analysis

def _retained_positions(payload: dict) -> list:
    """One authoritative record per (side, viewport, rep): the last retained attempt."""
    groups: dict = {}
    for rep in payload.get("raw_reps") or []:
        key = (rep["side"], rep["viewport"], rep["rep"])
        groups.setdefault(key, []).append(rep)
    positions = []
    for key in sorted(groups):
        side, viewport, rep = key
        attempts = groups[key]
        retained = [attempt for attempt in attempts if not attempt.get("discarded")]
        chosen = retained[-1] if retained else attempts[-1]
        positions.append({"side": side, "viewport": viewport, "rep": rep,
                          "attempts": len(attempts), "retained": bool(retained),
                          "record": chosen})
    return positions


def analyze(payload: dict) -> dict:
    positions = _retained_positions(payload)
    effective = [position for position in positions if position["retained"]] or positions
    side_viewport: dict = {}
    for position in effective:
        rep = position["record"]
        metrics = rep_metrics(rep)
        bucket = side_viewport.setdefault(position["side"], {}).setdefault(
            position["viewport"], {"records": []})
        bucket["records"].append({"rep": position["rep"], "metrics": metrics,
                                  "bursts": derive_bursts(rep),
                                  "page_errors": (rep.get("measurement") or {}).get("page_errors") or [],
                                  "loadavg_before": rep.get("loadavg_before"),
                                  "loadavg_after": rep.get("loadavg_after")})

    per_side = {}
    for side, viewports in side_viewport.items():
        per_side[side] = {}
        for viewport, bucket in viewports.items():
            records = bucket["records"]
            per_side[side][viewport] = {
                "reps": len(records),
                "metrics": _summarize_metrics(records, KEY_METRICS + (
                    "events_requests_per_burst", "run_stream_opens_per_burst",
                    "changes_stream_opens_per_burst", "run_batch_messages_per_burst",
                    "changes_messages_per_burst", "fetch_wait_ms", "innerhtml_ms",
                    "insert_html_ms", "json_parse_ms", "mutation_batches_per_burst",
                    "render_timeouts", "initial_dom_nodes", "frame_count",
                    "page_load_ms", "total_longtask_ms", "total_longtask_count",
                    "page_errors", "bursts_measured")),
                "burst_metrics": {
                    key: stats([burst.get(key) for record in records
                                for burst in record["bursts"]]) for key in BURST_METRICS},
                "change_resource_totals": _resource_totals(records),
                "loadavg": {"before": [record.get("loadavg_before") for record in records],
                            "after": [record.get("loadavg_after") for record in records]},
            }

    noise_floor = None
    trees = {name: (payload.get("sides", {}).get(name) or {}).get("tree")
             for name in ("A", "B")}
    if trees.get("A") and trees.get("B") and trees["A"] == trees["B"]:
        noise_floor = _noise_floor(effective)

    paired = None
    if payload.get("mode") == "paired":
        paired = _paired_analysis(payload, effective, side_viewport)
        if noise_floor is None:
            noise_floor = _ratio_spread(paired)

    discarded = sum(1 for rep in payload.get("raw_reps") or [] if rep.get("discarded"))
    limitations = [
        "Headless Chromium, reduced-motion context, one cold context per rep; software rendering "
        "throughput depends on host CPU contention (recorded loadavg per rep).",
        "Burst-commit timestamps are mapped from the harness monotonic clock into the page "
        "performance timeline with a midpoint clock-offset sample; residual error is about 1-3 ms "
        "and is small relative to the ~500 ms debounce/changes-stream cadence it precedes.",
        "Pre-change refresh cadence is driven by /api/v1/changes/stream resource invalidations, not "
        "the dashboard's run SSE named events (see Lead finding); the analysis reports both stream "
        "opens and change resource types per burst so the mechanism stays visible.",
        "longtask entries begin at 50 ms; sub-50 ms rebuild work is visible via innerHTML build "
        "durations but not as long tasks.",
        "Paired ratios are B/A; A=A (same tree passed twice) measures the harness noise floor and "
        "should be treated as the smallest effect the harness can resolve.",
    ]
    return {
        "positions": [{"side": position["side"], "viewport": position["viewport"],
                       "rep": position["rep"], "attempts": position["attempts"],
                       "retained": position["retained"]} for position in positions],
        "retained_reps": len(effective),
        "discarded_reps": discarded,
        "discarded_only_positions": [{"side": position["side"], "viewport": position["viewport"],
                                      "rep": position["rep"]}
                                     for position in positions if not position["retained"]],
        "per_side": per_side,
        "paired": paired,
        "noise_floor": noise_floor,
        "limitations": limitations,
    }


def _resource_totals(records: list) -> dict:
    totals: dict = {}
    for record in records:
        for burst in record["bursts"]:
            for name, count in burst.get("change_resources", {}).items():
                totals[name] = totals.get(name, 0) + count
    return totals


def _ratios(values: list) -> dict:
    data = [value for value in values if value is not None]
    if not data:
        return {"n": 0, "median": None, "values": [], "b_less": 0, "b_greater": 0, "equal": 0}
    return {"n": len(data), "median": round(median(data), 4), "values": [round(value, 4) for value in data],
            "b_less": sum(1 for value in data if value < 1.0),
            "b_greater": sum(1 for value in data if value > 1.0),
            "equal": sum(1 for value in data if value == 1.0)}


def _paired_analysis(payload: dict, positions: list, side_viewport: dict) -> dict:
    sequence = payload.get("config", {}).get("sequence") or []
    viewports = sorted(side_viewport.get("A", {}).keys())
    paired = {}
    for viewport in viewports:
        by_order = {(position["side"], position["rep"]): position
                    for position in positions if position["viewport"] == viewport}
        pairs = []
        for start in range(0, len(sequence), 2):
            group = sequence[start:start + 2]
            sides = {item["side"] for item in group}
            if sides != {"A", "B"}:
                continue
            a_item = next(item for item in group if item["side"] == "A")
            b_item = next(item for item in group if item["side"] == "B")
            a_position = by_order.get(("A", a_item["rep"]))
            b_position = by_order.get(("B", b_item["rep"]))
            if not a_position or not b_position:
                continue
            a_metrics = rep_metrics(a_position["record"])
            b_metrics = rep_metrics(b_position["record"])
            ratios, deltas = {}, {}
            for key in KEY_METRICS:
                a_value, b_value = a_metrics.get(key), b_metrics.get(key)
                if a_value is None or b_value is None:
                    continue
                deltas[key] = round(b_value - a_value, 4)
                ratios[key] = round(b_value / a_value, 4) if a_value else None
            pairs.append({"a_rep": a_item["rep"], "b_rep": b_item["rep"],
                          "a": {key: a_metrics.get(key) for key in KEY_METRICS},
                          "b": {key: b_metrics.get(key) for key in KEY_METRICS},
                          "ratios": ratios, "deltas": deltas})
        if pairs:
            paired[viewport] = {
                "pairs": pairs,
                "ratios": {key: _ratios([pair["ratios"].get(key) for pair in pairs])
                           for key in KEY_METRICS},
                "deltas": {key: stats([pair["deltas"].get(key) for pair in pairs])
                           for key in KEY_METRICS},
            }
    return paired


def _ratio_spread(paired: dict) -> dict:
    floor = {}
    for viewport, data in (paired or {}).items():
        floor[viewport] = {key: {"median_ratio": value.get("median"),
                                 "iqr_width": (round(value["values"][-1] - value["values"][0], 4)
                                               if len(value.get("values") or []) > 1 else 0.0),
                                 "values": value.get("values")}
                           for key, value in data["ratios"].items()}
    return {"note": "paired A/B ratios when both sides are the same tree: this is harness noise, "
                    "not a candidate effect", "per_viewport": floor}


def _noise_floor(positions: list) -> dict:
    """A=A repeats: spread of each metric across reps of the same tree."""
    by_side: dict = {}
    for position in positions:
        metrics = rep_metrics(position["record"])
        code = position["viewport"]
        by_side.setdefault(position["side"], {}).setdefault(code, []).append(metrics)
    floor = {}
    for side, viewports in by_side.items():
        floor[side] = {}
        for viewport, records in viewports.items():
            base = records[0]
            floor[side][viewport] = {key: {"cv": stats([record.get(key) for record in records]).get("cv"),
                                           "median": stats([record.get(key) for record in records]).get("median"),
                                           "values": [record.get(key) for record in records]}
                                     for key in KEY_METRICS if key in base}
    return {"note": "same-tree repeats: per-metric coefficient of variation across reps",
            "per_side_viewport": floor}
