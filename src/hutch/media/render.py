"""Deterministic render engines — the VERIFIED path for diagrams and animations.

Everything here is a pure function of its input: identical input produces
byte-identical output (pinned by tests), no clock, no randomness, no network.
When a diagram cannot be drawn the source is NEVER lost (open-webui #14541):
:func:`render_flowchart` raises :class:`GraphInvalid` with ``.source`` attached so
callers can return source + error together. Cycles are valid input; layering
breaks them deterministically (first-encountered back edge, in the caller's own
node/edge order) and says so in the SVG.

Video assembly (``.webm``) is capability-detected: it happens ONLY when
``shutil.which('ffmpeg')`` is truthy, and is refused honestly otherwise — an
animation stays SVG (SMIL) rather than being silently degraded or faked.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional
from xml.sax.saxutils import escape, quoteattr

MAX_NODES = 64
MAX_EDGES = 128
MAX_ANIMATION_FRAMES = 199      # "< 200 nodes" for the animation engine
MAX_LABEL_CHARS = 200
_WRAP_CHARS = 26                # label wrap width, in characters
_MAX_LINES = 3

_CHAR_W = 7.2                   # approx glyph width at the node font size
_LINE_H = 15.0
_NODE_PAD_X = 12.0
_NODE_PAD_Y = 10.0
_COL_GAP = 88.0                 # horizontal gap between layers (LR)
_ROW_GAP = 64.0                 # vertical gap between layers (TB)
_CANVAS_PAD = 28.0


class RenderError(ValueError):
    """A render request could not be honoured; the source is returned, not swallowed."""


class GraphInvalid(RenderError):
    """A flowchart payload is not renderable. ``.source`` keeps the caller's dict
    and ``.problems`` lists every violation, so nothing is lost on the way out."""

    def __init__(self, problems: list[str], source: Any = None):
        self.problems = list(problems)
        self.source = source
        detail = "; ".join(self.problems[:6])
        super().__init__(f"invalid flowchart: {detail}")


class AnimationInvalid(RenderError):
    """An animation payload is not renderable (same source-preserving contract)."""

    def __init__(self, problems: list[str], source: Any = None):
        self.problems = list(problems)
        self.source = source
        super().__init__(f"invalid animation: {'; '.join(self.problems[:6])}")


class WebMUnavailable(RenderError):
    """ffmpeg is not installed; webm assembly is honestly unavailable."""


# ------------------------------------------------------------------ validation


def _require(condition: bool, problems: list[str], message: str) -> bool:
    if not condition:
        problems.append(message)
    return condition


def validate_flowchart(payload: Any) -> dict[str, Any]:
    """Validate a raw flowchart payload dict. Returns it normalized; raises
    :class:`GraphInvalid` (with ``.source``) on duplicate node ids, dangling edges,
    bounds violations, or a bad direction."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        raise GraphInvalid(["the flowchart payload must be an object"], payload)
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    direction = payload.get("direction", "LR")
    _require(isinstance(nodes, list), problems, "nodes must be a list")
    _require(isinstance(edges, list), problems, "edges must be a list")
    _require(direction in ("LR", "TB"), problems,
             f"direction must be 'LR' or 'TB', got {direction!r}")
    if problems:
        raise GraphInvalid(problems, payload)
    seen: dict[str, dict[str, Any]] = {}
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            problems.append(f"node #{i} is not an object")
            continue
        node_id = node.get("id")
        label = node.get("label")
        if not isinstance(node_id, str) or not re_fullmatch_id(node_id):
            problems.append(f"node #{i} id {node_id!r} must match [A-Za-z0-9_-]{{1,64}}")
            continue
        if node_id in seen:
            problems.append(f"duplicate node id {node_id!r}")
            continue
        if not isinstance(label, str) or not 1 <= len(label) <= MAX_LABEL_CHARS:
            problems.append(f"node {node_id!r} label must be 1–{MAX_LABEL_CHARS} characters")
            continue
        group = node.get("group")
        detail = node.get("detail")
        _require(group is None or (isinstance(group, str) and 1 <= len(group) <= 120),
                 problems, f"node {node_id!r} group must be 1–120 characters")
        _require(detail is None or (isinstance(detail, str) and 1 <= len(detail) <= 2000),
                 problems, f"node {node_id!r} detail must be at most 2000 characters")
        seen[node_id] = node
    clean_edges: list[dict[str, Any]] = []
    if len(nodes) > MAX_NODES:
        problems.append(f"at most {MAX_NODES} nodes are supported, got {len(nodes)}")
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            problems.append(f"edge #{i} is not an object")
            continue
        src = edge.get("from")
        dst = edge.get("to")
        label = edge.get("label")
        for role, endpoint in (("from", src), ("to", dst)):
            if not isinstance(endpoint, str) or not re_fullmatch_id(endpoint):
                problems.append(f"edge #{i} {role} endpoint {endpoint!r} is not a node id")
            elif endpoint not in seen:
                problems.append(
                    f"edge #{i} {role} endpoint {endpoint!r} does not match any declared "
                    "node id; dangling edges are invalid")
        _require(label is None or (isinstance(label, str) and 1 <= len(label) <= 120),
                 problems, f"edge #{i} label must be 1–120 characters")
        if isinstance(src, str) and isinstance(dst, str):
            clean_edges.append({"from": src, "to": dst, "label": label})
    if len(edges) > MAX_EDGES:
        problems.append(f"at most {MAX_EDGES} edges are supported, got {len(edges)}")
    note = payload.get("assumptions_note")
    _require(note is None or (isinstance(note, str) and 1 <= len(note) <= 1000),
             problems, "assumptions_note must be at most 1000 characters")
    if problems:
        raise GraphInvalid(problems, payload)
    return {"nodes": [dict(n) for n in nodes], "edges": clean_edges,
            "direction": direction, "assumptions_note": note}


def re_fullmatch_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


# ------------------------------------------------------------------ layout


@dataclass
class _LaidOut:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    layers: dict[str, int] = field(default_factory=dict)
    broken_cycles: list[tuple[str, str]] = field(default_factory=list)


def break_cycles(node_ids: list[str], edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Deterministically remove back edges so the graph becomes a DAG.

    DFS from the caller's node order; the first edge that reaches a node already
    on the current stack is dropped. Deterministic because both orders are part
    of the (hashable, replayable) input.
    """
    adjacency: dict[str, list[str]] = {n: [] for n in node_ids}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
    removed: list[tuple[str, str]] = []
    state: dict[str, int] = {}   # absent/0 = unvisited, 1 = on stack, 2 = done
    for root in node_ids:
        if state.get(root):
            continue
        state[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, index = stack[-1]
            if index >= len(adjacency.get(node, [])):
                state[node] = 2
                stack.pop()
                continue
            stack[-1] = (node, index + 1)
            nxt = adjacency[node][index]
            if state.get(nxt) == 1:
                removed.append((node, nxt))   # back edge: break it
            elif not state.get(nxt):
                state[nxt] = 1
                stack.append((nxt, 0))
    return removed


def _layered_positions(node_ids: list[str], edges: list[tuple[str, str]],
                       broken: list[tuple[str, str]]) -> dict[str, int]:
    """Longest-path layering over the (cycle-broken) DAG: a node sits one layer
    below its deepest predecessor. Memoized over a Kahn topological order."""
    dag: dict[str, list[str]] = {n: [] for n in node_ids}
    indegree: dict[str, int] = {n: 0 for n in node_ids}
    broken_set = set(broken)
    for src, dst in edges:
        if (src, dst) in broken_set or src not in dag or dst not in indegree:
            continue
        dag[src].append(dst)
        indegree[dst] += 1
    queue = sorted(n for n, deg in indegree.items() if deg == 0)
    order: list[str] = []
    indeg = dict(indegree)
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in dag[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    for node in node_ids:      # any residue (impossible after cycle breaking) still lands somewhere
        if node not in order:
            order.append(node)
    layer = {n: 0 for n in node_ids}
    for node in order:
        for nxt in dag[node]:
            layer[nxt] = max(layer[nxt], layer[node] + 1)
    return layer


def _wrap_label(label: str) -> list[str]:
    """Wrap a long label into at most _MAX_LINES lines of _WRAP_CHARS, word-aware,
    ellipsized when the label does not fit. Oversized single words are hard-chunked."""
    words: list[str] = []
    for word in label.split():
        if len(word) > _WRAP_CHARS:
            words.extend(word[i:i + _WRAP_CHARS] for i in range(0, len(word), _WRAP_CHARS))
        else:
            words.append(word)
    lines: list[str] = []
    current = ""
    truncated = False
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= _WRAP_CHARS or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) >= _MAX_LINES:
            truncated = True
            break
    else:
        if current:
            lines.append(current)
    if truncated or " ".join(lines) != label.rstrip():
        lines[-1] = lines[-1][: max(_WRAP_CHARS - 1, 1)].rstrip() + "…"
    return lines or [label[:_WRAP_CHARS]]


def _layout(payload: dict[str, Any]) -> tuple[_LaidOut, float, float]:
    nodes = payload["nodes"]
    edges = [(e["from"], e["to"]) for e in payload["edges"]]
    direction = payload["direction"]
    node_ids = [n["id"] for n in nodes]
    broken = break_cycles(node_ids, edges)
    layer = _layered_positions(node_ids, edges, broken)
    laid = _LaidOut(layers=layer, broken_cycles=broken)
    # Geometry pass: slots within a layer follow the caller's node order.
    per_layer_count: dict[int, int] = {}
    for node in nodes:
        nid = node["id"]
        lines = _wrap_label(node["label"])
        width = max(_CHAR_W * max(len(line) for line in lines) + 2 * _NODE_PAD_X, 86.0)
        height = len(lines) * _LINE_H + 2 * _NODE_PAD_Y
        slot = per_layer_count.get(layer[nid], 0)
        per_layer_count[layer[nid]] = slot + 1
        if direction == "LR":
            x = _CANVAS_PAD + layer[nid] * (220.0 + _COL_GAP)
            y = _CANVAS_PAD + slot * 96.0
        else:
            x = _CANVAS_PAD + slot * 240.0
            y = _CANVAS_PAD + layer[nid] * (110.0 + _ROW_GAP)
        laid.nodes[nid] = {"x": x, "y": y, "w": width, "h": height, "lines": lines,
                           "label": node["label"], "group": node.get("group"),
                           "detail": node.get("detail")}
    total_w = max((n["x"] + n["w"] for n in laid.nodes.values()), default=0.0) + _CANVAS_PAD
    total_h = max((n["y"] + n["h"] for n in laid.nodes.values()), default=0.0) + _CANVAS_PAD + 30.0
    return laid, total_w, total_h


# ------------------------------------------------------------------ rendering


def _edge_anchor(laid: _LaidOut, node_id: str, direction: str, start: bool) -> tuple[float, float]:
    node = laid.nodes[node_id]
    cx, cy = node["x"] + node["w"] / 2, node["y"] + node["h"] / 2
    if direction == "LR":
        return (node["x"] + node["w"], cy) if start else (node["x"], cy)
    return (cx, node["y"] + node["h"]) if start else (cx, node["y"])


def render_flowchart(payload: dict[str, Any]) -> str:
    """Render a validated flowchart payload dict into a deterministic SVG string.

    Raises :class:`GraphInvalid` (with ``.source`` attached) for invalid graphs —
    duplicate node ids, dangling edges, bounds violations. Cycles are valid and
    are broken for layering only; every break is noted in the SVG output.
    """
    clean = validate_flowchart(payload)
    laid, width, height = _layout(clean)
    direction = clean["direction"]
    parts: list[str] = []
    parts.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    parts.append(
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width:.0f}\" "
        f"height=\"{height:.0f}\" viewBox=\"0 0 {width:.0f} {height:.0f}\" role=\"img\" "
        f"data-kind=\"flowchart\" data-direction={quoteattr(direction)}>")
    title_text = ", ".join(node["label"] for node in clean["nodes"])[:300]
    parts.append(f"<title>{escape(title_text)}</title>")
    parts.append("<defs><marker id=\"arrow\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" "
                 "markerWidth=\"7\" markerHeight=\"7\" orient=\"auto-start-reverse\">"
                 "<path d=\"M 0 0 L 10 5 L 0 10 z\" fill=\"#44506b\"/></marker></defs>")
    parts.append("<rect x=\"0\" y=\"0\" width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>")
    if laid.broken_cycles:
        note = "cycles present; broken for layering: " + ", ".join(
            f"{src}→{dst}" for src, dst in laid.broken_cycles)
        parts.append(f"<!-- {escape(note)} -->")
    # Group boxes first (behind everything), deterministic group order.
    groups: dict[str, list[str]] = {}
    for node_id in sorted(laid.nodes):
        group = laid.nodes[node_id].get("group")
        if group:
            groups.setdefault(group, []).append(node_id)
    for group in sorted(groups):
        members = groups[group]
        x0 = min(laid.nodes[m]["x"] for m in members) - 14
        y0 = min(laid.nodes[m]["y"] for m in members) - 14
        x1 = max(laid.nodes[m]["x"] + laid.nodes[m]["w"] for m in members) + 14
        y1 = max(laid.nodes[m]["y"] + laid.nodes[m]["h"] for m in members) + 14
        parts.append(
            f"<rect x=\"{x0:.0f}\" y=\"{y0:.0f}\" width=\"{x1 - x0:.0f}\" "
            f"height=\"{y1 - y0:.0f}\" rx=\"10\" fill=\"#f3f6fb\" stroke=\"#c9d4e8\" "
            f"stroke-dasharray=\"4 3\" data-group={quoteattr(group)}/>")
        parts.append(f"<text x=\"{x0 + 8:.0f}\" y=\"{y0 + 14:.0f}\" font-size=\"11\" "
                     f"fill=\"#5a6b8c\" font-family=\"sans-serif\">{escape(group)}</text>")
    # Edges (sorted for determinism), then nodes, then labels.
    def edge_sort_key(edge: dict[str, Any]) -> tuple[str, str, str]:
        return (edge["from"], edge["to"], edge.get("label") or "")
    for edge in sorted(clean["edges"], key=edge_sort_key):
        x1, y1 = _edge_anchor(laid, edge["from"], direction, start=True)
        x2, y2 = _edge_anchor(laid, edge["to"], direction, start=False)
        mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append(
            f"<path d=\"M {x1:.0f} {y1:.0f} L {x2:.0f} {y2:.0f}\" fill=\"none\" "
            "stroke=\"#44506b\" stroke-width=\"1.6\" marker-end=\"url(#arrow)\" "
            f"data-from={quoteattr(edge['from'])} data-to={quoteattr(edge['to'])}/>")
        if edge.get("label"):
            parts.append(
                f"<text x=\"{mid_x:.0f}\" y=\"{mid_y - 4:.0f}\" font-size=\"11\" "
                "text-anchor=\"middle\" fill=\"#33415e\" "
                f"font-family=\"sans-serif\">{escape(edge['label'])}</text>")
    for node_id in sorted(laid.nodes):
        node = laid.nodes[node_id]
        parts.append(
            f"<rect x=\"{node['x']:.0f}\" y=\"{node['y']:.0f}\" width=\"{node['w']:.0f}\" "
            f"height=\"{node['h']:.0f}\" rx=\"8\" fill=\"#eef2f9\" stroke=\"#7d8db0\" "
            f"stroke-width=\"1.4\" data-node={quoteattr(node_id)}/>")
        first_baseline = node["y"] + _NODE_PAD_Y + 13.0
        for i, line in enumerate(node["lines"]):
            parts.append(
                f"<text x=\"{node['x'] + _NODE_PAD_X:.0f}\" y=\"{first_baseline + i * _LINE_H:.0f}\" "
                "font-size=\"13\" fill=\"#1c2740\" font-family=\"sans-serif\">"
                f"{escape(line)}</text>")
        if node.get("detail"):
            detail_y = node["y"] + node["h"] + 13.0
            detail = node["detail"][:80] + ("…" if len(node["detail"]) > 80 else "")
            parts.append(
                f"<text x=\"{node['x']:.0f}\" y=\"{detail_y:.0f}\" font-size=\"10.5\" "
                "fill=\"#5a6b8c\" font-family=\"sans-serif\">"
                f"{escape(detail)}</text>")
    if clean.get("assumptions_note"):
        parts.append(
            f"<text x=\"{_CANVAS_PAD:.0f}\" y=\"{height - 10:.0f}\" font-size=\"11\" "
            "fill=\"#5a6b8c\" font-family=\"sans-serif\">assumption: "
            f"{escape(clean['assumptions_note'][:200])}</text>")
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ animation


def validate_animation(payload: Any) -> dict[str, Any]:
    """Validate an animation frames payload; raises :class:`AnimationInvalid`
    with ``.source`` attached."""
    problems: list[str] = []
    if not isinstance(payload, dict):
        raise AnimationInvalid(["the animation payload must be an object"], payload)
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise AnimationInvalid(["frames must be a non-empty list"], payload)
    if len(frames) > MAX_ANIMATION_FRAMES:
        problems.append(f"at most {MAX_ANIMATION_FRAMES} frames are supported, got {len(frames)}")
    total = 0.0
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            problems.append(f"frame #{i} is not an object")
            continue
        label = frame.get("label")
        if not isinstance(label, str) or not 1 <= len(label) <= 200:
            problems.append(f"frame #{i} label must be 1–200 characters")
        duration = frame.get("duration_seconds", 2.0)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) \
                or not math.isfinite(duration) or not 0.1 <= float(duration) <= 60.0:
            problems.append(f"frame #{i} duration_seconds must be 0.1–60")
        else:
            total += float(duration)
        detail = frame.get("detail")
        _require(detail is None or (isinstance(detail, str) and 1 <= len(detail) <= 2000),
                 problems, f"frame #{i} detail must be at most 2000 characters")
    title = payload.get("title")
    _require(title is None or (isinstance(title, str) and 1 <= len(title) <= 200),
             problems, "title must be 1–200 characters")
    if total > 600.0:
        problems.append("the animation totals more than 600 seconds")
    if problems:
        raise AnimationInvalid(problems, payload)
    return {"title": title, "frames": [dict(f) for f in frames]}


def render_animation(payload: dict[str, Any]) -> str:
    """Render a frames payload into a labeled SVG animation (SMIL), deterministically.

    Each frame is a full-bleed labeled card; frames cross-fade on a shared clock.
    Frame count is bounded (< 200); durations are validated. The SVG carries the
    frame schedule in ``data-`` attributes so the poster/frontends can be honest
    about what they show.
    """
    clean = validate_animation(payload)
    frames = clean["frames"]
    durations = [float(f.get("duration_seconds", 2.0)) for f in frames]
    total = sum(durations)
    width, height = 640.0, 400.0
    parts: list[str] = []
    parts.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    parts.append(f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width:.0f}\" "
                 f"height=\"{height:.0f}\" viewBox=\"0 0 {width:.0f} {height:.0f}\" "
                 f"role=\"img\" data-kind=\"animation\" data-frame-count=\"{len(frames)}\" "
                 f"data-duration-seconds=\"{total:g}\">")
    title_text = clean.get("title") or (frames[0].get("label") or "Animation")[:200]
    parts.append(f"<title>{escape(title_text)}</title>")
    parts.append("<rect width=\"100%\" height=\"100%\" fill=\"#101725\"/>")
    # Every frame shares ONE clock (dur = total, repeatCount = indefinite) and is
    # visible only inside its [begin, begin+duration) window, with a short fade.
    begin = 0.0
    for i, frame in enumerate(frames):
        label = str(frame.get("label", ""))
        detail = frame.get("detail")
        duration = durations[i]
        fade = min(0.4, duration / 2)
        window_end = min(begin + duration, total)
        fade_end = min(window_end + fade, total)
        if fade_end <= window_end:  # degenerate: no room for a fade-out
            fade_end = total
        group = [
            f"<g opacity=\"0\" data-frame=\"{i}\">",
            f"<animate attributeName=\"opacity\" dur=\"{total:g}s\" begin=\"0s\" "
            "repeatCount=\"indefinite\" values=\"0;1;1;0;0\" "
            f"keyTimes=\"0;{begin / total:.4f};{window_end / total:.4f};"
            f"{fade_end / total:.4f};1\"/>",
            f"<rect x=\"40\" y=\"52\" width=\"{width - 80:.0f}\" height=\"{height - 132:.0f}\" "
            "rx=\"14\" fill=\"#1b2740\" stroke=\"#3d5480\"/>",
            f"<text x=\"64\" y=\"120\" font-size=\"30\" fill=\"#f2f6ff\" "
            f"font-family=\"sans-serif\">{escape(label[:60])}</text>",
        ]
        if detail:
            group.append(f"<text x=\"64\" y=\"160\" font-size=\"16\" fill=\"#a8bade\" "
                         f"font-family=\"sans-serif\">{escape(str(detail)[:90])}</text>")
        group.append(f"<text x=\"64\" y=\"{height - 56:.0f}\" font-size=\"13\" "
                     f"fill=\"#7d94c4\" font-family=\"sans-serif\">frame {i + 1} of "
                     f"{len(frames)} · {duration:g}s</text>")
        group.append("</g>")
        parts.extend(group)
        begin += duration
    # Progress bar segments, deterministic widths.
    bar_y = height - 30.0
    x = 40.0
    for i, duration in enumerate(durations):
        seg = (width - 80.0) * duration / total
        parts.append(f"<rect x=\"{x:.1f}\" y=\"{bar_y:.0f}\" width=\"{seg:.1f}\" "
                     f"height=\"6\" rx=\"3\" fill=\"#3d5480\" data-segment=\"{i}\"/>")
        x += seg
    parts.append(f"<text x=\"{width - 40:.0f}\" y=\"{bar_y - 8:.0f}\" font-size=\"12\" "
                 "text-anchor=\"end\" fill=\"#7d94c4\" font-family=\"sans-serif\">"
                 f"{escape(str(title_text)[:80])} · {total:g}s total</text>")
    parts.append("</svg>")
    return "".join(parts)


def render_animation_poster(payload: dict[str, Any]) -> str:
    """A static poster: frame 1 of the animation, labeled honestly as a poster."""
    clean = validate_animation(payload)
    frames = clean["frames"]
    first = frames[0]
    width, height = 640.0, 400.0
    title_text = clean.get("title") or (first.get("label") or "Animation")[:200]
    parts: list[str] = []
    parts.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    parts.append(f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width:.0f}\" "
                 f"height=\"{height:.0f}\" viewBox=\"0 0 {width:.0f} {height:.0f}\" "
                 f"role=\"img\" data-kind=\"animation-poster\">")
    parts.append(f"<title>{escape('Poster: ' + title_text)}</title>")
    parts.append("<rect width=\"100%\" height=\"100%\" fill=\"#101725\"/>")
    parts.append(f"<rect x=\"40\" y=\"52\" width=\"{width - 80:.0f}\" height=\"{height - 132:.0f}\" "
                 "rx=\"14\" fill=\"#1b2740\" stroke=\"#3d5480\"/>")
    parts.append(f"<text x=\"64\" y=\"120\" font-size=\"30\" fill=\"#f2f6ff\" "
                 f"font-family=\"sans-serif\">{escape(str(first.get('label', ''))[:60])}</text>")
    if first.get("detail"):
        parts.append(f"<text x=\"64\" y=\"160\" font-size=\"16\" fill=\"#a8bade\" "
                     f"font-family=\"sans-serif\">{escape(str(first['detail'])[:90])}</text>")
    parts.append(f"<text x=\"64\" y=\"{height - 56:.0f}\" font-size=\"13\" fill=\"#7d94c4\" "
                 f"font-family=\"sans-serif\">poster: frame 1 of {len(frames)} — the "
                 "animation plays in the full SVG</text>")
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ webm assembly


def ffmpeg_available() -> bool:
    """Capability probe: webm assembly exists only when ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def assemble_webm(frame_pngs: list[bytes], *, fps: float = 1.0) -> bytes:
    """Assemble PNG frames into a .webm via ffmpeg — ONLY when ffmpeg is installed.

    This is capability-detected on purpose: without ffmpeg the honest answer is
    :class:`WebMUnavailable` (the caller stays with the SVG animation), never a
    silently degraded or fabricated video. Caller passes raster frames; SVG is
    not rasterized here because ffmpeg cannot read SVG without external helpers.
    """
    if not frame_pngs:
        raise WebMUnavailable("no frames were provided")
    if not all(frame.startswith(b"\x89PNG\r\n\x1a\n") for frame in frame_pngs):
        raise WebMUnavailable("webm assembly takes PNG frames; non-PNG input is refused")
    if not ffmpeg_available():
        raise WebMUnavailable(
            "ffmpeg was not found on PATH; the animation stays SVG (SMIL) and no "
            "video was fabricated")
    fps = max(0.1, min(float(fps), 60.0))
    with tempfile.TemporaryDirectory(prefix="hutch-webm-") as tmp:
        frames_dir = os.path.join(tmp, "frames")
        os.mkdir(frames_dir, mode=0o700)
        for i, frame in enumerate(frame_pngs):
            path = os.path.join(frames_dir, f"frame-{i:05d}.png")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(frame)
        out_path = os.path.join(tmp, "out.webm")
        argv = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-framerate", f"{fps:g}", "-i", os.path.join(frames_dir, "frame-%05d.png"),
                "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-pix_fmt", "yuv420p",
                "-loop", "0", out_path]
        proc = subprocess.run(argv, capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise WebMUnavailable(
                "ffmpeg failed to assemble the webm "
                f"(exit {proc.returncode}): {proc.stderr[:400]!r}")
        with open(out_path, "rb") as stream:
            data = stream.read()
    if not data.startswith(b"\x1a\x45\xdf\xa3"):
        raise WebMUnavailable("ffmpeg produced output that is not an EBML/webm stream")
    return data
