/* Typed output-block widgets for the hutch feed.
 *
 * Renders the validated block dicts a tool attaches to its tool_result event
 * (contract: docs/research/outputs-block-contract-2026-10-10.md). One renderer
 * per kind, plus a labeled fallback for anything unknown or invalid — a failed
 * rich render always degrades to text_fallback + the error, never silence.
 *
 * Conventions (matching model-switcher.js / skills.js):
 *   · vanilla ES in one IIFE, no build step, own local esc();
 *   · app.js globals (toast) are probed on window at call time, never imported;
 *   · renderers are PURE functions of block data — renderChatFeed replaces the
 *     transcript wholesale, so every piece of user-owned UI state (open/closed,
 *     filters, sort directions) lives in localStorage under "widgets:<block id>"
 *     and is re-read on the next render;
 *   · interactivity is wired by ONE document-level delegated listener set +
 *     per-chart hydration, so wholesale feed re-renders need no rewiring;
 *   · the only network this module ever performs is same-origin reads of the
 *     media store (/api/v1/media/...) — never a third-party request.
 *
 * Trust rules: every interpolated string passes esc(); animation SVGs are
 * parsed client-side and stripped of scripts/handlers as defense in depth;
 * selecting a flowchart node inspects, it never operates.
 */
(function () {
  "use strict";

  /* ── tiny shared helpers ─────────────────────────────────────────── */

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const WKEY = "widgets:";
  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(WKEY + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(WKEY + key, JSON.stringify(value)); } catch { /* private mode */ }
    },
  };

  const reduceMotion = () =>
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) ||
    document.documentElement.classList.contains("reduce-effects");

  const notify = (msg, isError = false) => {
    if (typeof window.toast === "function") return window.toast(msg, isError);
    if (isError) console.error(msg); else console.info(msg);
  };

  const fmtInt = n => Number(n).toLocaleString("en-US");
  function fmtNum(n) {
    if (typeof n !== "number" || !Number.isFinite(n)) return String(n ?? "");
    if (Number.isInteger(n)) return n.toLocaleString("en-US");
    const abs = Math.abs(n);
    const digits = abs >= 100 ? 1 : abs >= 1 ? 2 : 4;
    return n.toLocaleString("en-US", { maximumFractionDigits: digits });
  }
  function fmtBytes(n) {
    const b = Number(n);
    if (!Number.isSafeInteger(b) || b < 0) return "";
    if (b < 1024) return `${b} bytes`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  }
  function fmtDuration(startIso, endIso) {
    const a = Date.parse(startIso || ""), b = Date.parse(endIso || "");
    if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return "";
    const s = (b - a) / 1000;
    if (s < 1) return `${Math.round((b - a))} ms`;
    if (s < 60) return `${s.toFixed(1).replace(/\.0$/, "")} s`;
    return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
  }
  const shortDigest = d => /^[a-f0-9]{64}$/i.test(String(d || "")) ? `${String(d).slice(0, 16)}…` : "";

  /* Local 24 by 24 outline glyphs — same visual family as app.js's ICON_PATHS.
     SVG icons only (DESIGN.md audit gate), always next to a word. */
  const GLYPHS = {
    chart: '<path d="M3 3v18h18"/><path d="M7 15l4-6 3 4 4-7"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
    clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
    layers: '<path d="m12 2 8.5 4.7L12 11.4 3.5 6.7z"/><path d="m3.5 12.6 8.5 4.7 8.5-4.7"/><path d="m3.5 17.3 8.5 4.7 8.5-4.7"/>',
    flow: '<rect x="3" y="3" width="7" height="6" rx="1.5"/><rect x="14" y="15" width="7" height="6" rx="1.5"/><path d="M10 6h4a3 3 0 0 1 3 3v6"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m5 19 5.5-5.5L14 17l3-3 3 3"/>',
    code: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4"/>',
    pulse: '<path d="M3 12h4l2.5-6 4 12L16 12h5"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    text: '<path d="M4 6h16M4 11h16M4 16h10"/>',
    copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    download: '<path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14"/>',
    zoomIn: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M8.5 11h5M11 8.5v5"/>',
    zoomOut: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M8.5 11h5"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    alert: '<path d="M12 3.5 22 20.5H2z"/><path d="M12 10v5"/><path d="M12 18.2v.01"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    caretUp: '<path d="M17 11 12 6l-5 5"/>',
    caretDown: '<path d="M7 13l5 5 5-5"/>',
  };
  const glyph = (name, size = 14) =>
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${GLYPHS[name] || ""}</svg>`;

  /* Text + icon badges — never color alone (The Amber Rule, WCAG 1.4.1). */
  const tag = (label, tone, g) =>
    `<span class="tag${tone && tone !== "muted" ? ` ${tone}` : ""}">${glyph(g || "eye", 12)}<span>${esc(label)}</span></span>`;

  /* ── whitelisted URL builders (same-origin only, validated shapes) ── */

  const MEDIA_ID_RE = /^media_[0-9a-f]{16}$/;
  const DOC_ID_RE = /^doc_[0-9a-f]{16}$/;

  function mediaContentUrl(mediaId, version) {
    const v = Number(version);
    if (!MEDIA_ID_RE.test(String(mediaId || "")) || !Number.isSafeInteger(v) || v < 1) return "";
    return `/api/v1/media/${encodeURIComponent(mediaId)}/versions/${v}/content`;
  }
  function documentDownloadUrl(docId, version) {
    const v = Number(version);
    if (!DOC_ID_RE.test(String(docId || "")) || !Number.isSafeInteger(v) || v < 1) return "";
    return `/api/v1/documents/${encodeURIComponent(docId)}/versions/${v}/download`;
  }

  /* ── block envelope plumbing ─────────────────────────────────────── */

  const KIND_META = {
    chart: { label: "Chart", glyph: "chart" },
    table: { label: "Table", glyph: "table" },
    timeline: { label: "Timeline", glyph: "clock" },
    comparison: { label: "Comparison", glyph: "layers" },
    flowchart: { label: "Flowchart", glyph: "flow" },
    media: { label: "Media", glyph: "image" },
    code_receipt: { label: "Code receipt", glyph: "code" },
    status: { label: "Status", glyph: "pulse" },
    artifact_ref: { label: "Artifact", glyph: "file" },
    text: { label: "Note", glyph: "text" },
  };

  const AVAIL_META = {
    pending: { tone: "muted", glyph: "clock", label: "pending" },
    failed: { tone: "danger", glyph: "alert", label: "failed" },
    revoked: { tone: "danger", glyph: "x", label: "revoked" },
    stale: { tone: "warn", glyph: "alert", label: "stale" },
  };

  /* The block's own JSON rides along inertly so delegated handlers can
     re-render any card without a network round trip. `<`, `>`, `&` and the
     line/paragraph separators are escaped so `</script>` cannot break out. */
  const safeJson = value =>
    JSON.stringify(value ?? null)
      .replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026")
      .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");

  function readBlock(card) {
    const tagEl = card && card.querySelector('script[type="application/json"][data-widget-payload]');
    if (!tagEl) return null;
    try { return JSON.parse(tagEl.textContent || "{}"); } catch { return null; }
  }

  function provenanceMeta(block) {
    const p = block.provenance || {};
    const bits = [];
    if (p.tool) bits.push(esc(p.tool));
    if (p.run_id) bits.push(`<span class="mono" title="run ${esc(p.run_id)}">run ${esc(String(p.run_id).slice(0, 11))}…</span>`);
    return bits.length ? `<span class="widget-meta">${bits.join(" · ")}</span>` : "";
  }

  function blockFrame(block, bodyHtml, cardExtra = "") {
    const id = String(block.id || "");
    const kind = String(block.kind || "unknown");
    const meta = KIND_META[kind] || { label: "Output block", glyph: "file" };
    const avail = block.availability && block.availability !== "ready" ? AVAIL_META[block.availability] : null;
    return `<article class="widget-card widget-kind-${esc(kind)}${cardExtra}" data-widget-card data-block-id="${esc(id)}" data-block-kind="${esc(kind)}">
    <script type="application/json" data-widget-payload>${safeJson(block)}</script>
    <header class="widget-head">
      <span class="widget-kind">${glyph(meta.glyph)}<span>${esc(meta.label)}</span></span>
      ${provenanceMeta(block)}
      ${avail ? tag(avail.label, avail.tone, avail.glyph) : ""}
    </header>
    <div class="widget-body" data-widget-root>${bodyHtml}</div>
  </article>`;
  }

  /* The open-webui #14541 rule: a failed render surfaces the fallback text AND
     the diagnostic. Neither is ever erased. */
  function fallbackBody(block, reason) {
    const tf = block && typeof block.text_fallback === "string" ? block.text_fallback : "";
    return `<section class="widget-fallback" role="note" aria-label="Output block fallback">
    <p class="widget-fallback-head">${glyph("alert")} This output block could not be rendered (unsupported or invalid) — showing fallback.</p>
    ${reason ? `<p class="widget-fallback-error">Reason: ${esc(reason)}</p>` : ""}
    ${tf ? `<p class="widget-fallback-text">${esc(tf)}</p>` : ""}
    ${block && block.id ? `<p class="widget-meta mono">block ${esc(block.id)}${block.kind ? ` · kind ${esc(block.kind)}` : ""}${block.revision ? ` · revision ${esc(Number(block.revision))}` : ""}</p>` : ""}
  </section>`;
  }

  function errorChipHtml(entry) {
    const bits = [];
    if (entry.kind) bits.push(`kind ${esc(entry.kind)}`);
    if (entry.id) bits.push(`id ${esc(entry.id)}`);
    return `<section class="widget-fallback widget-fallback-chip" role="note" aria-label="Rejected output block">
    <p class="widget-fallback-head">${glyph("alert")} <strong>Output block rejected at validation</strong>${bits.length ? ` — ${bits.join(" · ")}` : ""}</p>
    <p class="widget-fallback-error">${esc(entry.error || "no diagnostic recorded")}</p>
  </section>`;
  }

  /* ── text ────────────────────────────────────────────────────────── */

  function renderTextHtml(block) {
    const content = String((block.payload || {}).content ?? "");
    if (!content) return fallbackBody(block, "text block has no content");
    return `<p class="widget-text">${esc(content)}</p>`;
  }

  /* ── status ──────────────────────────────────────────────────────── */

  const STATUS_STATES = {
    pending: { tone: "muted", glyph: "clock", label: "Pending" },
    running: { tone: "info", glyph: "pulse", label: "Running" },
    final: { tone: "ok", glyph: "check", label: "Final" },
    failed: { tone: "danger", glyph: "alert", label: "Failed" },
    cancelled: { tone: "muted", glyph: "x", label: "Cancelled" },
    stale: { tone: "warn", glyph: "alert", label: "Stale" },
    blocked: { tone: "warn", glyph: "alert", label: "Blocked" },
    unknown: { tone: "muted", glyph: "alert", label: "Unknown" },
  };

  function renderStatusHtml(block) {
    const p = block.payload || {};
    const st = STATUS_STATES[p.state] || STATUS_STATES.unknown;
    return `<div class="widget-status">
    ${tag(st.label, st.tone, st.glyph)}
    <span class="widget-status-stage">${esc(String(p.stage ?? "stage unknown"))}</span>
    ${p.detail ? `<p class="widget-text">${esc(String(p.detail))}</p>` : ""}
  </div>`;
  }

  /* ── artifact_ref ────────────────────────────────────────────────── */

  function renderArtifactRefHtml(block) {
    const p = block.payload || {};
    const href = p.ref_kind === "document" ? documentDownloadUrl(p.id, p.version) : mediaContentUrl(p.id, p.version);
    if (!href) return fallbackBody(block, `artifact reference does not match a known download URL shape (${esc(p.ref_kind || "?")} ${esc(p.id || "?")} v${esc(p.version ?? "?")})`);
    const digest = shortDigest(p.sha256);
    const meta = [p.mime ? esc(p.mime) : "", p.version ? `v${esc(Number(p.version))}` : "", fmtBytes(p.bytes), digest ? `SHA-256 ${esc(digest)}` : ""]
      .filter(Boolean).join(" · ");
    return `<div class="widget-ref-card">
    ${glyph("file", 20)}
    <div class="widget-ref-copy">
      <strong title="${esc(String(p.name || "artifact"))}">${esc(String(p.name || "artifact"))}</strong>
      <span class="widget-meta mono">${meta}</span>
    </div>
    <a class="btn ghost small" href="${esc(href)}" title="The server verifies this file against its recorded SHA-256 before download">Download</a>
  </div>`;
  }

  /* ── code_receipt ────────────────────────────────────────────────── */

  const CR_STATUS = {
    ok: { tone: "ok", glyph: "check", label: "ok" },
    error: { tone: "danger", glyph: "alert", label: "error" },
    timeout: { tone: "danger", glyph: "clock", label: "timeout" },
    cancelled: { tone: "muted", glyph: "x", label: "cancelled" },
    interrupt_unconfirmed: { tone: "warn", glyph: "alert", label: "interrupt — unconfirmed" },
  };
  const SOURCE_EXT = {
    python: ".py", py: ".py", bash: ".sh", sh: ".sh", shell: ".sh",
    javascript: ".js", js: ".js", typescript: ".ts", ts: ".ts",
    json: ".json", html: ".html", css: ".css", sql: ".sql",
  };

  function renderCodeReceiptHtml(block) {
    const p = block.payload || {};
    const source = String(p.source ?? "");
    if (!source) return fallbackBody(block, "code receipt carries no source");
    const ex = p.execution || {};
    const st = CR_STATUS[ex.status] || { tone: "muted", glyph: "alert", label: String(ex.status || "status unknown") };
    const dur = fmtDuration(ex.started_at, ex.finished_at);
    const receiptBits = [
      `execution #${esc(Number(ex.ordinal ?? "?"))}`,
      `environment generation ${esc(Number(ex.environment_generation ?? "?"))}`,
      dur ? `ran in ${esc(dur)}` : "",
      Number.isSafeInteger(ex.stdout_chars_total) ? `${fmtInt(ex.stdout_chars_total)} stdout chars` : "",
    ].filter(Boolean);
    const files = Array.isArray(p.produced_files) ? p.produced_files : [];
    return `<div class="widget-code" data-widget-code>
    <p class="widget-receipt-line">
      ${tag(st.label, st.tone, st.glyph)}
      <span class="widget-meta mono">${receiptBits.join(" · ")}</span>
    </p>
    <div class="widget-code-actions">
      <button class="btn ghost small" type="button" data-widget-action="cr-copy">${glyph("copy")} Copy</button>
      <button class="btn ghost small" type="button" data-widget-action="cr-download">${glyph("download")} Download</button>
      <span class="widget-meta mono">exactly what executed — hash-bound, not editable</span>
    </div>
    <pre class="widget-code-view"><code>${esc(source)}</code></pre>
    ${typeof p.result_repr === "string" && p.result_repr ? `<p class="widget-code-result"><span class="tool-line-label">Result</span> <code class="mono">${esc(p.result_repr)}</code></p>` : ""}
    ${p.stdout_tail ? `<details class="widget-code-tail"><summary>stdout (${fmtInt(String(p.stdout_tail).length)} chars, tail)</summary><pre>${esc(String(p.stdout_tail))}</pre></details>` : ""}
    ${p.stderr_tail ? `<details class="widget-code-tail"><summary>stderr (${fmtInt(String(p.stderr_tail).length)} chars, tail)</summary><pre>${esc(String(p.stderr_tail))}</pre></details>` : ""}
    ${files.length ? `<div class="widget-code-files"><span class="tool-line-label">Produced files</span><ul>${files.map(f =>
      `<li><span>${esc(String(f.name || "file"))}</span><span class="widget-meta mono">${fmtBytes(f.bytes)}${f.sha256 ? ` · ${esc(shortDigest(f.sha256))}` : ""}</span></li>`).join("")}</ul></div>` : ""}
  </div>`;
  }

  /* ── table ───────────────────────────────────────────────────────── */

  function cmpScalar(a, b, dtype) {
    if (dtype === "number") {
      const na = Number(a), nb = Number(b);
      const va = Number.isFinite(na) && String(a).trim() !== "" ? na : null;
      const vb = Number.isFinite(nb) && String(b).trim() !== "" ? nb : null;
      if (va === null && vb === null) return 0;
      if (va === null) return 1;               // non-numbers sort last, both directions
      if (vb === null) return -1;
      return va - vb;
    }
    const sa = String(a ?? ""), sb = String(b ?? "");
    return sa.localeCompare(sb, "en", { numeric: true });
  }

  function renderTableHtml(block) {
    const p = block.payload || {};
    const columns = Array.isArray(p.columns) ? p.columns : [];
    const rows = Array.isArray(p.rows) ? p.rows : [];
    if (!columns.length) return fallbackBody(block, "table block declares no columns");
    const id = block.id;
    const sort = store.get(`${id}:tsort`, null);            // [colIdx, 1|-1] — view state only
    const sortedRows = sort && Number.isInteger(sort[0]) && sort[0] >= 0 && sort[0] < columns.length
      ? rows.map((r, i) => [r, i]).sort((a, b) => {
          const d = cmpScalar(a[0][sort[0]], b[0][sort[0]], columns[sort[0]].dtype) * (sort[1] === -1 ? -1 : 1);
          return d !== 0 ? d : a[1] - b[1];                 // stable: evidence order preserved on ties
        }).map(pair => pair[0])
      : rows;
    const total = Number(p.row_total);
    const trunc = p.truncation || {};
    const shownNote = Number.isSafeInteger(total) && total > rows.length
      ? `Showing first ${fmtInt(rows.length)} of ${fmtInt(total)} rows${trunc.reason ? ` — ${esc(trunc.reason)}` : ""}`
      : `${fmtInt(rows.length)} ${rows.length === 1 ? "row" : "rows"}`;
    const head = columns.map((c, i) => {
      const active = sort && sort[0] === i;
      const dir = active ? (sort[1] === -1 ? -1 : 1) : 0;
      return `<th scope="col" aria-sort="${dir === 1 ? "ascending" : dir === -1 ? "descending" : "none"}">
      <button class="widget-sort" type="button" data-widget-sort="${i}" title="Sort by ${esc(c.name)} (client-side view only)">
        <span>${esc(c.name)}</span><span class="widget-dtype">${esc(c.dtype || "unknown")}</span>${glyph(dir === 1 ? "caretUp" : dir === -1 ? "caretDown" : "caretDown", 11)}
      </button></th>`;
    }).join("");
    const body = sortedRows.map(r => `<tr>${columns.map((c, i) => {
      const cell = Array.isArray(r) ? r[i] : undefined;
      const text = cell === undefined || cell === null ? "—" : typeof cell === "object" ? JSON.stringify(cell) : String(cell);
      return `<td${c.dtype === "number" ? ` class="num"` : ""}>${esc(text)}</td>`;
    }).join("")}</tr>`).join("");
    return `<div class="widget-table">
    <div class="table-wrap widget-scroll-table"><table>
      <caption class="visually-hidden">Data table preview; sorting is a client-side view and does not change stored evidence order</caption>
      <thead><tr>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${columns.length}" class="widget-empty">No rows in preview</td></tr>`}</tbody>
    </table></div>
    <p class="widget-note" role="note">${shownNote}</p>
    ${p.notes ? `<p class="widget-note">${esc(String(p.notes))}</p>` : ""}
  </div>`;
  }

  /* ── chart ───────────────────────────────────────────────────────── */

  const CHART_PALETTE = ["#34d399", "#60a5fa", "#c084fc", "#22d3ee", "#f472b6", "#a3e635", "#94a3b8", "#2dd4bf"];

  function axisLabel(axis, scaleNote) {
    if (!axis || typeof axis.label !== "string") return "";
    const unit = axis.unit ? ` (${axis.unit}${scaleNote ? `, ${scaleNote}` : ""})` : (scaleNote ? ` (${scaleNote})` : "");
    return `${axis.label}${unit}`;
  }

  function chartSummary(p) {
    const kinds = { line: "Line chart", bar: "Bar chart", scatter: "Scatter plot", area: "Area chart" };
    const names = (p.series || []).map(s => s.label);
    const seriesPart = names.length === 1 ? names[0] : `${names.length} series: ${names.join(", ")}`;
    const bits = [
      kinds[p.kind] || "Chart",
      seriesPart,
      `x: ${axisLabel(p.x) || "unnamed"} · ${p.x?.scale || "linear"}`,
      `y: ${axisLabel(p.y) || "unnamed"} · ${p.y?.scale || "linear"}`,
      p.source ? `source: ${p.source}` : "",
    ].filter(Boolean);
    return bits.join(" · ");
  }

  function renderChartHtml(block) {
    const p = block.payload || {};
    const series = Array.isArray(p.series) ? p.series : [];
    if (!series.length || !series.every(s => Array.isArray(s.points))) {
      return fallbackBody(block, "chart block carries no plottable series");
    }
    const logNote = (p.x?.scale === "log" || p.y?.scale === "log") ? "log" : "";
    // The exact-value table: the chart's own text_fallback made interactive.
    const xsSet = new Map();                                   // x -> row index, insertion then sorted
    for (const s of series) for (const pt of s.points) {
      if (Array.isArray(pt) && pt.length === 2) xsSet.set(pt[0], xsSet.size);
    }
    const xs = [...xsSet.keys()].sort((a, b) => a - b);
    const perSeries = series.map(s => {
      const m = new Map(s.points.map(pt => [pt[0], pt[1]]));
      return xs.map(x => m.has(x) ? m.get(x) : "");
    });
    const tableHead = `<tr><th scope="col">${esc(p.x?.label || "x")}${p.x?.unit ? ` (${esc(p.x.unit)})` : ""}</th>` +
      series.map(s => `<th scope="col">${esc(s.label)}</th>`).join("") + "</tr>";
    const tableBody = xs.map((x, i) =>
      `<tr><th scope="row">${esc(fmtNum(x))}</th>${perSeries.map(col => `<td>${col[i] === "" ? "—" : esc(fmtNum(col[i]))}</td>`).join("")}</tr>`).join("");
    return `<div class="widget-chart" data-widget-chart>
    <p class="widget-note widget-chart-summary">${esc(chartSummary(p))}${logNote ? " · logarithmic scale, labeled" : ""}</p>
    <div class="widget-chart-mount" data-widget-chart-mount></div>
    <div class="widget-chart-tools">
      <button class="btn ghost small" type="button" data-widget-action="chart-reset-zoom" title="Double-click the chart or use this button to reset zoom">${glyph("refresh")} Reset zoom</button>
      <span class="widget-meta">Drag across the plot to zoom · click legend entries to hide series</span>
    </div>
    ${p.notes ? `<p class="widget-note">${esc(String(p.notes))}</p>` : ""}
    ${p.dataset_ref ? `<p class="widget-meta mono">data: ${esc(String(p.dataset_ref))}</p>` : ""}
    <details class="widget-datatable" data-widget-datatable ${store.get(`${block.id}:datatable`, false) ? "open" : ""}>
      <summary>Data table — exact values</summary>
      <div class="table-wrap widget-scroll-table"><table>
        <caption class="visually-hidden">Exact plotted values</caption>
        <thead>${tableHead}</thead>
        <tbody>${tableBody}</tbody>
      </table></div>
    </details>
  </div>`;
  }

  /* ── timeline ────────────────────────────────────────────────────── */

  const TL_STATES = {
    reported: { tone: "info", glyph: "pulse", label: "reported" },
    confirmed: { tone: "ok", glyph: "check", label: "confirmed" },
    planned: { tone: "muted", glyph: "clock", label: "planned" },
    corrected: { tone: "warn", glyph: "refresh", label: "corrected" },
  };
  const TL_ORDER = ["confirmed", "reported", "planned", "corrected"];

  /* Late/corrected events merge by id: last occurrence wins, and any
     corrected_from anywhere in the merge group surfaces the corrected chip. */
  function mergeTimelineEvents(events) {
    const byId = new Map();
    for (const ev of events) {
      const id = String(ev.id || "");
      const prev = byId.get(id);
      const corrected = !!(ev.corrected_from || ev.state === "corrected" || (prev && prev._corrected));
      byId.set(id, { ...ev, _corrected: corrected });
    }
    return [...byId.values()];
  }

  function formatWhen(w) {
    if (!w || typeof w.iso8601 !== "string") return `<span class="widget-tl-when mono">time unknown</span>`;
    const precision = w.precision ? ` · ${esc(w.precision)} precision` : "";
    const tz = w.timezone ? ` · ${esc(w.timezone)}` : "";
    const ms = Date.parse(w.iso8601);
    const local = Number.isFinite(ms) && ["day", "hour", "minute", "second"].includes(w.precision)
      ? ` <span class="widget-tl-local">(local: ${esc(new Date(ms).toLocaleString())})</span>` : "";
    return `<time class="widget-tl-when mono" datetime="${esc(w.iso8601)}">${esc(w.iso8601)}${precision}${tz}</time>${local}`;
  }

  function timelineListHtml(block) {
    const p = block.payload || {};
    const id = block.id;
    const stateFilter = store.get(`${id}:tlstate`, "all");
    const group = store.get(`${id}:tlgroup`, false);
    const total = mergeTimelineEvents(Array.isArray(p.events) ? p.events : []).length;
    return `<div class="widget-timeline" data-widget-timeline>
    <div class="widget-tl-tools">
      <label class="widget-field">State
        <select data-widget-tl-state>
          <option value="all"${stateFilter === "all" ? " selected" : ""}>All states</option>
          ${TL_ORDER.map(s => `<option value="${s}"${stateFilter === s ? " selected" : ""}>${esc(TL_STATES[s].label)}</option>`).join("")}
        </select>
      </label>
      <label class="widget-field">Filter
        <input type="search" data-widget-tl-q placeholder="Filter events by text" value="${esc(String(store.get(`${id}:tlq`, "")))}">
      </label>
      <label class="widget-check"><input type="checkbox" data-widget-tl-group${group ? " checked" : ""}> Group by state</label>
    </div>
    <div data-widget-tl-results>${timelineResultsHtml(block, filteredTimelineEvents(block), total)}</div>
  </div>`;
  }

  /* Pure function of (block data + localStorage view state): merge late
     corrections by id, apply the state filter and text filter, order by time.
     No network, no model — filters are client-side only. */
  function filteredTimelineEvents(block) {
    const p = block.payload || {};
    const id = block.id;
    const stateFilter = store.get(`${id}:tlstate`, "all");
    const query = String(store.get(`${id}:tlq`, "")).toLowerCase();
    let merged = mergeTimelineEvents(Array.isArray(p.events) ? p.events : []);
    if (stateFilter !== "all") merged = merged.filter(ev => (ev.state === "corrected" || ev._corrected ? "corrected" : ev.state) === stateFilter);
    if (query) merged = merged.filter(ev =>
      String(ev.label || "").toLowerCase().includes(query) ||
      String(ev.source || "").toLowerCase().includes(query) ||
      String(ev.id || "").toLowerCase().includes(query));
    merged.sort((a, b) => {
      const ta = Date.parse(a.when?.iso8601 || ""), tb = Date.parse(b.when?.iso8601 || "");
      const va = Number.isFinite(ta) ? ta : Infinity, vb = Number.isFinite(tb) ? tb : Infinity;
      return va === vb ? 0 : va - vb;                          // stable: input order breaks ties
    });
    return merged;
  }

  /* The count + list live in their own container so the text filter can
     re-render them without replacing the input the person is typing in. */
  function timelineResultsHtml(block, merged, total) {
    const group = store.get(`${block.id}:tlgroup`, false);
    const listHtml = group
      ? TL_ORDER.map(stateKey => {
          const items = merged.filter(ev => stateKey === "corrected" ? (ev.state === "corrected" || ev._corrected) : ev.state === stateKey);
          if (!items.length) return "";
          const st = TL_STATES[stateKey];
          return `<li class="widget-tl-group"><h4 class="widget-tl-group-head">${glyph(st.glyph)} ${esc(st.label)} <span class="widget-meta">(${items.length})</span></h4>
            <ol class="widget-tl-list">${items.map(timelineItemHtml).join("")}</ol></li>`;
        }).join("")
      : merged.map(timelineItemHtml).join("");
    return `<p class="widget-note" role="status" data-widget-tl-count>${fmtInt(merged.length)} of ${fmtInt(total)} events shown — filters are local to this browser, nothing is sent anywhere</p>
    ${merged.length ? `<ol class="widget-tl-list${group ? " grouped" : ""}">${listHtml}</ol>` : `<p class="widget-empty">No events match the current filters.</p>`}`;
  }

  function timelineItemHtml(ev) {
    const stateKey = ev.state === "corrected" || ev._corrected ? "corrected" : (TL_STATES[ev.state] ? ev.state : "reported");
    const st = TL_STATES[stateKey];
    return `<li class="widget-tl-item" data-event-id="${esc(String(ev.id || ""))}">
      ${tag(st.label, st.tone, st.glyph)}
      <div class="widget-tl-copy">
        <strong>${esc(String(ev.label || "event"))}</strong>
        ${formatWhen(ev.when)}
        ${ev.source ? `<span class="widget-tl-src">source: ${esc(String(ev.source))}</span>` : ""}
        ${ev.corrected_from ? `<span class="widget-tl-src">corrected from event ${esc(String(ev.corrected_from))}</span>` : ""}
      </div>
    </li>`;
  }

  /* ── comparison ──────────────────────────────────────────────────── */

  const CMP_STATE_LABEL = { unknown: "Unknown", not_applicable: "Not applicable", unsupported: "Unsupported" };
  const CMP_STATE_RANK = { not_applicable: 1, unsupported: 2, unknown: 3 };

  function renderComparisonHtml(block) {
    const p = block.payload || {};
    const items = Array.isArray(p.items) ? p.items : [];
    const criteria = Array.isArray(p.criteria) ? p.criteria : [];
    if (!items.length || !criteria.length) return fallbackBody(block, "comparison block is missing items or criteria");
    const id = block.id;
    const cellMap = new Map();
    for (const c of (Array.isArray(p.cells) ? p.cells : [])) cellMap.set(`${c.item}\u0000${c.criterion}`, c);
    const sort = store.get(`${id}:csort`, null);              // [itemId, 1|-1] — view state only
    let cols = items.slice();                                 // a copy; stored evidence order is never touched
    if (sort && cols.some(it => it.id === sort[0])) {
      const dir = sort[1] === -1 ? -1 : 1;
      const firstCriterion = criteria[0].id;
      const rank = it => {
        const cell = cellMap.get(`${it.id}\u0000${firstCriterion}`);
        if (!cell || cell.state) return 2 + (CMP_STATE_RANK[cell?.state] || 9);   // unknown-state cells after values
        const n = Number(cell.value);
        return Number.isFinite(n) && String(cell.value).trim() !== "" ? 0 : 1;
      };
      const valueOf = it => {
        const cell = cellMap.get(`${it.id}\u0000${firstCriterion}`);
        const n = Number(cell?.value);
        return Number.isFinite(n) ? n : 0;
      };
      cols = cols.map((it, i) => [it, i]).sort((a, b) => {
        const ra = rank(a[0]), rb = rank(b[0]);
        let d = ra !== rb ? (ra < rb ? -1 : 1) : (ra === 0 ? valueOf(a[0]) - valueOf(b[0]) : 0);
        if (d === 0) d = a[1] - b[1];                         // stable: declared item order breaks ties
        return d * dir;
      }).map(pair => pair[0]);
    }
    const cellHtml = cell => {
      if (!cell) return `<td class="widget-cmp-cell"><span class="widget-missing">No cell provided</span></td>`;
      if (cell.state) {
        const label = CMP_STATE_LABEL[cell.state] || String(cell.state);
        return `<td class="widget-cmp-cell">${tag(label, "muted", "eye")}${cell.citations ? `<span class="widget-cite" title="${esc(String(cell.citations))}">source noted</span>` : ""}</td>`;
      }
      return `<td class="widget-cmp-cell">${esc(String(cell.value))}${cell.citations ? `<span class="widget-cite" title="${esc(String(cell.citations))}">source noted</span>` : ""}</td>`;
    };
    const headCols = cols.map(it => {
      const active = sort && sort[0] === it.id;
      const dir = active ? (sort[1] === -1 ? -1 : 1) : 0;
      return `<th scope="col" aria-sort="${dir === 1 ? "ascending" : dir === -1 ? "descending" : "none"}">
      <button class="widget-sort" type="button" data-widget-csort="${esc(it.id)}" title="Sort columns by first criterion (client-side view only)">
        <span>${esc(it.label)}</span>${glyph(dir === 1 ? "caretUp" : "caretDown", 11)}
      </button></th>`;
    }).join("");
    const bodyRows = criteria.map(cr => `<tr>
      <th scope="row" class="widget-cmp-crit">${esc(cr.label)}${cr.unit ? ` <span class="widget-dtype">${esc(cr.unit)}</span>` : ""}</th>
      ${cols.map(it => cellHtml(cellMap.get(`${it.id}\u0000${cr.id}`))).join("")}
    </tr>`).join("");
    return `<div class="widget-cmp">
    <div class="table-wrap widget-scroll-table"><table class="widget-cmp-table">
      <caption class="visually-hidden">Comparison matrix; column sorting is a client-side view and does not change stored evidence order</caption>
      <thead><tr><th scope="col" class="widget-cmp-crit-head">Criterion</th>${headCols}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table></div>
    ${p.ranking_note ? `<p class="widget-note widget-ranking" role="note">${glyph("check")} ${esc(String(p.ranking_note))}</p>` : ""}
  </div>`;
  }

  /* ── flowchart ───────────────────────────────────────────────────── */

  const FC = { NW: 172, NH: 46, GX: 64, GY: 30, PAD: 18 };

  /* Client-side layered layout mirroring the server renderer's contract:
     longest-path layering over the edge set; cycles are broken deterministically
     (first back-edge in declared node/edge order is ignored for layering). */
  function layoutFlowchart(p) {
    const nodes = Array.isArray(p.nodes) ? p.nodes : [];
    const edges = Array.isArray(p.edges) ? p.edges : [];
    const byId = new Map(nodes.map((n, i) => [n.id, { ...n, _i: i }]));
    const outEdges = new Map(nodes.map(n => [n.id, []]));
    for (const e of edges) {
      if (byId.has(e.from) && byId.has(e.to)) outEdges.get(e.from).push(e);
    }
    // DFS cycle-break: skip an edge whose target is on the current stack.
    const state = new Map(nodes.map(n => [n.id, 0]));
    const stack = new Set();
    const dagEdges = [];
    const visit = startId => {
      if (state.get(startId) !== 0) return;
      state.set(startId, 1); stack.add(startId);
      for (const e of outEdges.get(startId)) {
        if (stack.has(e.to)) continue;
        dagEdges.push(e);
        visit(e.to);
      }
      stack.delete(startId);
      state.set(startId, 2);
    };
    for (const n of nodes) visit(n.id);
    // Longest-path layering via Kahn topological order over the kept DAG.
    const layer = new Map(nodes.map(n => [n.id, 0]));
    const indeg = new Map(nodes.map(n => [n.id, 0]));
    for (const e of dagEdges) indeg.set(e.to, indeg.get(e.to) + 1);
    const queue = nodes.filter(n => indeg.get(n.id) === 0).map(n => n.id);
    const order = [];
    const localIndeg = new Map(indeg);
    while (queue.length) {
      const id = queue.shift();
      order.push(id);
      for (const e of outEdges.get(id)) {
        if (!dagEdges.includes(e)) continue;
        localIndeg.set(e.to, localIndeg.get(e.to) - 1);
        layer.set(e.to, Math.max(layer.get(e.to), layer.get(id) + 1));
        if (localIndeg.get(e.to) === 0) queue.push(e.to);
      }
    }
    const tb = p.direction === "TB";
    const layers = new Map();
    for (const n of nodes) {
      const L = layer.get(n.id);
      if (!layers.has(L)) layers.set(L, []);
      layers.get(L).push(n);                                  // declared order within a layer: deterministic
    }
    const layerKeys = [...layers.keys()].sort((a, b) => a - b);
    const pos = new Map();
    let maxRow = 0;
    layerKeys.forEach((L, col) => {
      const row = layers.get(L);
      maxRow = Math.max(maxRow, row.length);
      row.forEach((n, r) => pos.set(n.id, tb
        ? { x: r * (FC.NW + FC.GX), y: col * (FC.NH + FC.GY), L, r }
        : { x: col * (FC.NW + FC.GX), y: r * (FC.NH + FC.GY), L, r }));
    });
    const cols = layerKeys.length, rowsCount = maxRow;
    const width = (tb ? rowsCount : cols) * (FC.NW + FC.GX) - FC.GX + FC.PAD * 2;
    const height = (tb ? cols : rowsCount) * (FC.NH + FC.GY) - FC.GY + FC.PAD * 2;
    // group bounding boxes: one dashed container per declared group value
    const groups = new Map();
    for (const n of nodes) {
      if (!n.group) continue;
      const q = pos.get(n.id);
      if (!q) continue;
      if (!groups.has(n.group)) groups.set(n.group, { x1: q.x, y1: q.y, x2: q.x + FC.NW, y2: q.y + FC.NH });
      else {
        const g = groups.get(n.group);
        g.x1 = Math.min(g.x1, q.x); g.y1 = Math.min(g.y1, q.y);
        g.x2 = Math.max(g.x2, q.x + FC.NW); g.y2 = Math.max(g.y2, q.y + FC.NH);
      }
    }
    const edgeSeg = (e, markerId) => {
      const a = pos.get(e.from), b = pos.get(e.to);
      if (!a || !b) return "";
      let x1, y1, x2, y2;
      if (tb) { x1 = a.x + FC.NW / 2; y1 = a.y + FC.NH; x2 = b.x + FC.NW / 2; y2 = b.y; }
      else { x1 = a.x + FC.NW; y1 = a.y + FC.NH / 2; x2 = b.x; y2 = b.y + FC.NH / 2; }
      const dx = Math.max(28, Math.abs(x2 - x1) / 2), dy = Math.max(28, Math.abs(y2 - y1) / 2);
      const d = tb
        ? `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
        : `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
      const label = e.label
        ? `<text class="widget-flow-edge-label" x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 4}">${esc(String(e.label).length > 24 ? `${String(e.label).slice(0, 23)}…` : e.label)}</text>`
        : "";
      return `<path class="widget-flow-edge" d="${d}" marker-end="url(#${markerId})"></path>${label}`;
    };
    return { nodes, byId, pos, dagEdges, groups, edgeSeg, width: Math.max(width, 240), height: Math.max(height, 120), tb };
  }

  function renderFlowchartHtml(block) {
    const p = block.payload || {};
    const lay = layoutFlowchart(p);
    if (!lay.nodes.length) return fallbackBody(block, "flowchart block declares no nodes");
    const markerId = `wf-arrow-${String(block.id || "x").replace(/[^a-z0-9_-]/gi, "")}`;
    const groupRects = [...lay.groups.entries()].map(([name, g]) => {
      const x = g.x1 - 12, y = Math.max(2, g.y1 - 26), w = g.x2 - g.x1 + 24, h = g.y2 - g.y1 + 38;
      return `<g class="widget-flow-group"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12"/><text x="${x + 8}" y="${y + 14}">${esc(String(name))}</text></g>`;
    }).join("");
    const edgeEls = lay.dagEdges.map(e => lay.edgeSeg(e, markerId)).join("");
    const nodeEls = lay.nodes.map(n => {
      const q = lay.pos.get(n.id);
      if (!q) return "";
      const label = String(n.label || n.id);
      return `<g class="widget-flow-node" data-widget-fc-node="${esc(String(n.id))}" role="button" tabindex="0"
        aria-label="Step ${esc(label)}${n.group ? ` — group ${esc(String(n.group))}` : ""} — press Enter to inspect (read-only)">
        <rect class="widget-flow-node-box" x="${q.x}" y="${q.y}" width="${FC.NW}" height="${FC.NH}" rx="8"/>
        <text class="widget-flow-node-label" x="${q.x + FC.NW / 2}" y="${q.y + FC.NH / 2 + 4}">${esc(label.length > 26 ? `${label.slice(0, 25)}…` : label)}</text>
      </g>`;
    }).join("");
    return `<div class="widget-flow" data-widget-flow>
    <p class="widget-note">Read-only inspection: selecting a step opens its notes below; it never starts or changes anything. Drag to pan, scroll or use the buttons to zoom.</p>
    <div class="widget-flow-frame">
      <svg class="widget-flow-svg" data-widget-flow-svg viewBox="0 0 ${Math.round(lay.width)} ${Math.round(lay.height)}" width="100%" role="group" aria-label="Flowchart with ${lay.nodes.length} steps">
        <defs><marker id="${markerId}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" class="widget-flow-arrowhead"/></marker></defs>
        ${groupRects}
        <g class="widget-flow-edges">${edgeEls}</g>
        ${nodeEls}
      </svg>
    </div>
    <div class="widget-flow-tools">
      <button class="btn ghost small" type="button" data-widget-action="fc-zoom" data-delta="1" aria-label="Zoom in">${glyph("zoomIn")} Zoom in</button>
      <button class="btn ghost small" type="button" data-widget-action="fc-zoom" data-delta="-1" aria-label="Zoom out">${glyph("zoomOut")} Zoom out</button>
      <button class="btn ghost small" type="button" data-widget-action="fc-reset">${glyph("refresh")} Reset view</button>
    </div>
    <div class="widget-flow-detail" data-widget-fc-detail role="status">Select a step to inspect it — read-only.</div>
    ${p.assumptions_note ? `<p class="widget-note widget-ranking" role="note">${glyph("alert")} ${esc(String(p.assumptions_note))}</p>` : ""}
  </div>`;
  }

  /* ── media ───────────────────────────────────────────────────────── */

  function renderMediaHtml(block) {
    const p = block.payload || {};
    const alt = typeof p.alt_text === "string" ? p.alt_text.trim() : "";
    if (!alt) {
      // alt_text is REQUIRED: unlabeled media renders as a labeled failure.
      return fallbackBody(block, "media block is missing required alt_text — refusing to render unlabelled media");
    }
    const src = mediaContentUrl(p.media_id, p.version);
    if (!src) return fallbackBody(block, "media reference does not match the media store URL shape");
    const dims = Number(p.width) > 0 && Number(p.height) > 0 ? `width="${Number(p.width)}" height="${Number(p.height)}"` : "";
    const aspect = Number(p.width) > 0 && Number(p.height) > 0 ? ` style="aspect-ratio:${Number(p.width)}/${Number(p.height)}"` : "";
    const metaBits = [
      // "rendered by deterministic · deterministic" is noise: the backend name and
      // the generator label are shown once each, and only when they differ.
      p.backend && String(p.backend) !== String(p.generated_by || "") ? `rendered by ${esc(String(p.backend))}` : "",
      p.generated_by ? esc(String(p.generated_by)) : "",
      Number(p.duration_seconds) > 0 ? `${Number(p.duration_seconds).toFixed(1)} s` : "",
      shortDigest(p.sha256) ? `SHA-256 ${esc(shortDigest(p.sha256))}` : "",
    ].filter(Boolean).join(" · ");
    let inner = "";
    if (p.kind === "video") {
      const poster = p.poster ? mediaContentUrl(p.poster.media_id, p.poster.version) : "";
      const captions = p.captions ? mediaContentUrl(p.captions.media_id, p.captions.version) : "";
      inner = `<video controls muted playsinline preload="metadata"${dims}${poster ? ` poster="${esc(poster)}"` : ""} src="${esc(src)}"${captions ? `<track kind="captions" src="${esc(captions)}" default>` : ""}></video>`;
    } else if (p.kind === "audio") {
      inner = `<audio controls preload="metadata" src="${esc(src)}"></audio>`;
    } else if (p.kind === "animation") {
      // Sanitized server-side already; the client-side src-DOM pass below is
      // defense in depth: scripts and on* handlers are stripped before inline.
      inner = `<div class="widget-svg-mount" data-widget-svg-mount data-media-url="${esc(src)}"${aspect}><div class="widget-svg-placeholder" role="status">Loading animation…</div></div>`;
    } else {
      inner = `<img src="${esc(src)}" alt="${esc(alt)}" loading="lazy"${dims}>`;
    }
    return `<figure class="widget-media"${aspect}>
    ${inner}
    <figcaption class="widget-meta">${metaBits}</figcaption>
  </figure>`;
  }

  /* Defense-in-depth sanitizer for inline animation SVGs: DOMParser (a src-DOM
     pass — nothing executes), then strip scriptable content before inlining. */
  function sanitizeSvg(text) {
    const doc = new DOMParser().parseFromString(String(text), "image/svg+xml");
    if (doc.querySelector("parsererror")) throw new Error("animation SVG did not parse");
    const root = doc.documentElement;
    if (!root || root.nodeName.toLowerCase() !== "svg") throw new Error("not an SVG document");
    const removed = [];
    root.querySelectorAll("script, iframe, object, embed, foreignObject").forEach(el => { removed.push(el.nodeName); el.remove(); });
    const all = [root, ...root.querySelectorAll("*")];
    for (const el of all) {
      for (const attr of [...el.attributes]) {
        const name = attr.name.toLowerCase();
        const value = String(attr.value || "").trim().toLowerCase();
        if (name.startsWith("on")) { el.removeAttribute(attr.name); removed.push(attr.name); continue; }
        if ((name === "href" || name === "xlink:href") && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
          el.removeAttribute(attr.name); removed.push(attr.name);
        }
      }
    }
    if (removed.length) console.info("widgets: stripped from animation SVG:", removed.join(", "));
    return new XMLSerializer().serializeToString(root);
  }

  /* ── dispatch ────────────────────────────────────────────────────── */

  const RENDERERS = {
    text: renderTextHtml,
    table: renderTableHtml,
    chart: renderChartHtml,
    timeline: timelineListHtml,
    comparison: renderComparisonHtml,
    flowchart: renderFlowchartHtml,
    media: renderMediaHtml,
    code_receipt: renderCodeReceiptHtml,
    status: renderStatusHtml,
    artifact_ref: renderArtifactRefHtml,
  };

  function renderKindBody(block) {
    const kind = String(block.kind || "");
    const renderer = RENDERERS[kind];
    if (!renderer) return fallbackBody(block, `unsupported block kind '${esc(kind || "(none)")}'`);
    if (block.availability && block.availability !== "ready") {
      const meta = AVAIL_META[block.availability] || { label: block.availability };
      return fallbackBody(block, `content is not ready to render (availability: ${meta.label})`);
    }
    try {
      return renderer(block) || fallbackBody(block, "renderer produced nothing");
    } catch (err) {
      return fallbackBody(block, `renderer failed: ${err && err.message ? err.message : err}`);
    }
  }

  function blockHtml(block) {
    if (!block || typeof block !== "object") {
      return fallbackBody({}, "tool attached a block that is not an object");
    }
    if (!block.id || !block.kind) {
      return fallbackBody(block, "block is missing its id or kind");
    }
    return blockFrame(block, renderKindBody(block));
  }

  function blocksHtml(blocks, blockErrors, opts = {}) {
    const list = Array.isArray(blocks) ? blocks.filter(b => b && typeof b === "object") : [];
    const errors = Array.isArray(blockErrors) ? blockErrors.filter(e => e && typeof e === "object") : [];
    if (!list.length && !errors.length) return "";
    return `<div class="widget-blocks" role="group" aria-label="Presented output blocks">${list.map(blockHtml).join("")}${errors.map(errorChipHtml).join("")}</div>`;
  }

  /* ── hydration: charts (uPlot), flowchart pan/zoom, animation SVGs ── */

  const CHART_H = 240;
  function cssColor(varName, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return v || fallback;
  }

  function hydrateChart(mount, ctl) {
    if (mount.dataset.widgetLive === "1") return;
    mount.dataset.widgetLive = "1";
    let u = null;
    const card = mount.closest("[data-widget-card]");
    const block = readBlock(card);
    const p = (block && block.payload) || {};
    const series = Array.isArray(p.series) ? p.series : [];

    const build = () => {
      const U = window.uPlot;
      if (typeof U !== "function") {
        mount.innerHTML = `<p class="widget-note">${glyph("alert")} The chart engine did not load — exact values remain available in the data table below.</p>`;
        return;
      }
      if (!series.length) return;
      // uPlot needs one shared x array; series with divergent x values get
      // nulls where a point is absent (uPlot spans gaps).
      const xsSet = new Set();
      for (const s of series) for (const pt of s.points) if (Array.isArray(pt) && pt.length === 2) xsSet.add(pt[0]);
      const xs = [...xsSet].sort((a, b) => a - b);
      const data = [xs, ...series.map(s => {
        const m = new Map(s.points.filter(pt => Array.isArray(pt) && pt.length === 2).map(pt => [pt[0], pt[1]]));
        return xs.map(x => m.has(x) ? m.get(x) : null);
      })];
      // uPlot's time axis wants unix seconds; heuristic guard for ms epochs.
      const timeAxis = p.x?.scale === "time";
      if (timeAxis && xs.length && Math.abs(xs[0]) > 1e11) {
        data[0] = data[0].map(v => v / 1000);                 // y values untouched
      }
      const hidden = new Set(store.get(`${block.id}:hidseries`, []));
      const line = cssColor("--line", "rgba(255,255,255,0.07)");
      const axisText = cssColor("--text-2", "rgba(240,244,249,0.74)");
      const scales = { x: { time: timeAxis } };
      if (p.x?.scale === "log") scales.x.distr = 2;                // log10, labeled in the axis label
      if (p.y?.scale === "log") scales.y = { distr: 2 };
      const yLog = p.y?.scale === "log";
      const opts = {
        width: Math.max(240, Math.floor(mount.clientWidth || 320)),
        height: CHART_H,
        scales,
        axes: [
          { label: axisLabel(p.x, timeAxis ? "time" : p.x?.scale === "log" ? "log scale" : ""), stroke: axisText, grid: { stroke: line }, ticks: { stroke: line }, labelSize: 22, labelGap: 6 },
          { label: axisLabel(p.y, yLog ? "log scale" : ""), stroke: axisText, grid: { stroke: line }, ticks: { stroke: line }, labelSize: 12, labelGap: 6 },
        ],
        series: [{}, ...series.map((s, i) => {
          const color = CHART_PALETTE[i % CHART_PALETTE.length];
          const base = { label: String(s.label || `series ${i + 1}`), stroke: color, width: 1.8, show: !hidden.has(String(s.label)) };
          if (p.kind === "scatter") base.points = { show: true, size: 5, stroke: color };
          if (p.kind === "area") base.fill = `${color}26`;
          if (p.kind === "bar") base.paths = U.paths.bars ? U.paths.bars({ size: [0.6, 100] }) : undefined;
          return base;
        })],
        legend: { show: true, live: true, markers: { show: true } },
        cursor: { drag: { x: true, y: false, uni: 30 } },
        hooks: {
          setSelect: [plot => {
            if (plot.select.width > 4) {
              plot.setScale("x", {
                min: plot.posToVal(plot.select.left, "x"),
                max: plot.posToVal(plot.select.left + plot.select.width, "x"),
              });
            }
          }],
          setSeries: [(_plot, sidx, changed) => {
            if (!changed || typeof changed.show !== "boolean" || !series[sidx - 1]) return;
            const labels = new Set(store.get(`${block.id}:hidseries`, []));
            if (changed.show) labels.delete(String(series[sidx - 1].label));
            else labels.add(String(series[sidx - 1].label));
            store.set(`${block.id}:hidseries`, [...labels]);     // legend toggles are view state
          }],
          ready: [plot => {
            plot.over.addEventListener("dblclick", () => {
              const chart = chartFor(mount);
              if (chart) chart.setScale("x", { min: null, max: null });
            });
          }],
        },
      };
      try {
        u = new U(opts, data, mount);
      } catch (err) {
        mount.innerHTML = `<p class="widget-note">${glyph("alert")} Chart could not be drawn (${esc(String(err && err.message || err))}) — exact values remain in the data table below.</p>`;
        return;
      }
      chartByMount.set(mount, u);
      ctl.charts.push(u);
    };

    if ((mount.clientWidth || 0) >= 80) build();
    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth || 0;
      if (!u && w >= 80) build();
      else if (u && w >= 80 && Math.abs(w - u.width) > 8) u.setSize({ width: Math.floor(w), height: CHART_H });
    });
    ro.observe(mount);
    ctl.observers.push(ro);
  }

  const chartByMount = new WeakMap();
  function chartFor(mount) { return mount ? chartByMount.get(mount) || null : null; }
  const flowCtl = new WeakMap();

  function hydrateFlow(svg, ctl) {
    if (svg.dataset.widgetLive === "1") return;
    svg.dataset.widgetLive = "1";
    const card = svg.closest("[data-widget-card]");
    const block = readBlock(card);
    const p = (block && block.payload) || {};
    const lay = layoutFlowchart(p);           // recompute: pure, cheap at ≤64 nodes
    const fit = { x: 0, y: 0, w: lay.width, h: lay.height };
    const vp = { ...fit };
    const apply = () => svg.setAttribute("viewBox", `${vp.x} ${vp.y} ${vp.w} ${vp.h}`);
    apply();
    let drag = null;
    const onPointerDown = e => {
      if (e.button !== 0) return;
      drag = { px: e.clientX, py: e.clientY, vx: vp.x, vy: vp.y, moved: false };
      svg.setPointerCapture?.(e.pointerId);
    };
    const onPointerMove = e => {
      if (!drag) return;
      const rect = svg.getBoundingClientRect();
      const sx = vp.w / Math.max(rect.width, 1), sy = vp.h / Math.max(rect.height, 1);
      const dx = (e.clientX - drag.px) * sx, dy = (e.clientY - drag.py) * sy;
      if (Math.abs(e.clientX - drag.px) + Math.abs(e.clientY - drag.py) > 4) drag.moved = true;
      vp.x = drag.vx - dx;
      vp.y = drag.vy - dy;
      apply();
    };
    const onPointerUp = () => { setTimeout(() => { drag = null; }, 0); };
    const onWheel = e => {
      e.preventDefault();                                     // zoom on wheel; page scroll via the area outside the frame
      zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 1.12 : 1 / 1.12);
    };
    function zoomAt(cx, cy, factor) {
      const rect = svg.getBoundingClientRect();
      const mx = vp.x + ((cx - rect.left) / Math.max(rect.width, 1)) * vp.w;
      const my = vp.y + ((cy - rect.top) / Math.max(rect.height, 1)) * vp.h;
      const nw = Math.min(fit.w, Math.max(fit.w / 4, vp.w * factor));
      const nh = Math.min(fit.h, Math.max(fit.h / 4, vp.h * factor));
      vp.x = mx - (mx - vp.x) * (nw / vp.w);
      vp.y = my - (my - vp.y) * (nh / vp.h);
      vp.w = nw; vp.h = nh;
      apply();
    }
    ctl.on(svg, "pointerdown", onPointerDown);
    ctl.on(svg, "pointermove", onPointerMove);
    ctl.on(svg, "pointerup", onPointerUp);
    ctl.on(svg, "pointercancel", onPointerUp);
    ctl.on(svg, "wheel", onWheel, { passive: false });
    ctl.flowZoom = (delta) => {
      const rect = svg.getBoundingClientRect();
      zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, delta > 0 ? 1 / 1.25 : 1.25);
    };
    ctl.flowReset = () => { Object.assign(vp, fit); apply(); };
    ctl.flowDragMoved = () => !!drag?.moved;
    flowCtl.set(svg, ctl);                                  // every wired svg is reachable from the delegated handlers
  }

  function selectFlowNode(card, nodeId) {
    const detail = card.querySelector("[data-widget-fc-detail]");
    const block = readBlock(card);
    if (!detail || !block) return;
    const node = ((block.payload || {}).nodes || []).find(n => String(n.id) === String(nodeId));
    card.querySelectorAll(".widget-flow-node.selected").forEach(g => g.classList.remove("selected"));
    const g = card.querySelector(`[data-widget-fc-node="${CSS.escape(String(nodeId))}"]`);
    if (g) g.classList.add("selected");
    if (!node) { detail.innerHTML = `Step not found in this flowchart.`; return; }
    detail.innerHTML = `<strong>${esc(String(node.label || node.id))}</strong>` +
      (node.group ? ` <span class="widget-meta">group: ${esc(String(node.group))}</span>` : "") +
      (node.detail ? `<p class="widget-text">${esc(String(node.detail))}</p>` : `<p class="widget-meta">No further detail recorded for this step.</p>`) +
      `<span class="widget-meta mono">node id ${esc(String(node.id))}</span>`;
  }

  function hydrateMedia(mount, ctl) {
    if (mount.dataset.widgetLive === "1") return;
    mount.dataset.widgetLive = "1";
    const url = String(mount.dataset.mediaUrl || "");
    const match = /^\/api\/v1\/media\/(media_[0-9a-f]{16})\/versions\/\d+\/content$/.exec(url);
    if (!match) {
      mount.innerHTML = `<p class="widget-note">${glyph("alert")} Animation reference is not a whitelisted media URL.</p>`;
      return;
    }
    ctl.async(fetch(url, { credentials: "same-origin" }).then(r => {
      if (!r.ok) throw new Error(`media store responded ${r.status}`);
      return r.text();
    }).then(text => {
      const clean = sanitizeSvg(text);
      mount.innerHTML = clean;
      const svg = mount.querySelector("svg");
      if (svg) {
        svg.removeAttribute("width"); svg.removeAttribute("height");
        svg.setAttribute("width", "100%");
        svg.setAttribute("role", "img");
        const card = mount.closest("[data-widget-card]");
        const block = readBlock(card);
        const alt = (block?.payload || {}).alt_text;
        if (alt) svg.setAttribute("aria-label", String(alt));
      }
    }).catch(err => {
      const card = mount.closest("[data-widget-card]");
      const block = readBlock(card) || {};
      mount.innerHTML = fallbackBody(block, `animation could not be loaded or sanitized: ${err && err.message ? err.message : err}`);
    }));
  }

  /* Per-render wiring registry: renderBlocks' returned cleanup undoes all of it. */
  function makeCtl() {
    const ctl = {
      charts: [], observers: [], abort: new AbortController(), asyncTasks: [],
      flowZoom: null, flowReset: null, flowDragMoved: () => false,
      on(el, type, fn, opts) { el.addEventListener(type, fn, { ...(opts || {}), signal: ctl.abort.signal }); },
      async(promise) { ctl.asyncTasks.push(promise.catch(() => {})); },
      destroy() {
        ctl.abort.abort();
        ctl.charts.forEach(u => { try { u.destroy(); } catch { /* already gone */ } });
        ctl.observers.forEach(o => { try { o.disconnect(); } catch { /* fine */ } });
      },
    };
    return ctl;
  }

  function hydrateRoot(rootEl) {
    const ctl = makeCtl();
    rootEl.querySelectorAll("[data-widget-chart-mount]").forEach(m => hydrateChart(m, ctl));
    rootEl.querySelectorAll("[data-widget-flow-svg]").forEach(s => hydrateFlow(s, ctl));
    rootEl.querySelectorAll("[data-widget-svg-mount]").forEach(m => hydrateMedia(m, ctl));
    return ctl;
  }

  /* ── public API ──────────────────────────────────────────────────── */

  function renderBlocks(rootEl, blocks, opts = {}) {
    if (!rootEl) return () => {};
    rootEl.innerHTML = blocksHtml(blocks, opts.block_errors, opts);
    const ctl = hydrateRoot(rootEl);
    return () => ctl.destroy();
  }

  function renderBlock(el, block, opts = {}) {
    if (!el) return () => {};
    el.innerHTML = blockHtml(block);
    const ctl = hydrateRoot(el);
    return () => ctl.destroy();
  }

  /* Re-render one card in place after a filter/sort/toggle changed. */
  function rerenderCard(card) {
    const block = readBlock(card);
    const root = card && card.querySelector("[data-widget-root]");
    if (!block || !root) return;
    root.innerHTML = renderKindBody(block);
    hydrateRoot(root);
  }

  /* ── document-level delegation (installed once; survives any re-render) ── */

  function flowSvgOf(el) { return el.closest("[data-widget-flow]")?.querySelector("[data-widget-flow-svg]"); }

  function wireDocument() {
    document.addEventListener("click", ev => {
      const btn = ev.target.closest("[data-widget-action]");
      if (btn) {
        const card = btn.closest("[data-widget-card]");
        const action = btn.dataset.widgetAction;
        if (!card) return;
        const block = readBlock(card) || {};
        const p = block.payload || {};
        if (action === "chart-reset-zoom") {
          const chart = chartFor(card.querySelector("[data-widget-chart-mount]"));
          if (chart) chart.setScale("x", { min: null, max: null });
        } else if (action === "cr-copy") {
          copyTextToClipboard(String(p.source ?? ""), btn);
        } else if (action === "cr-download") {
          downloadSource(block, btn);
        } else if (action === "fc-zoom" || action === "fc-reset") {
          const svgEl = flowSvgOf(card);
          if (svgEl) {
            hydrateFlowLazy(card, svgEl);
            const ctl = flowCtl.get(svgEl);
            if (action === "fc-reset") ctl.flowReset();
            else ctl.flowZoom(Number(btn.dataset.delta) || 1);
          }
        }
        return;
      }
      const sortBtn = ev.target.closest("[data-widget-sort]");
      if (sortBtn) {
        const card = sortBtn.closest("[data-widget-card]");
        const block = readBlock(card);
        if (!block) return;
        const idx = Number(sortBtn.dataset.widgetSort);
        const prev = store.get(`${block.id}:tsort`, null);
        const next = prev && prev[0] === idx ? [idx, prev[1] === 1 ? -1 : 1] : [idx, 1];
        store.set(`${block.id}:tsort`, next);
        rerenderCard(card);
        return;
      }
      const cSortBtn = ev.target.closest("[data-widget-csort]");
      if (cSortBtn) {
        const card = cSortBtn.closest("[data-widget-card]");
        const block = readBlock(card);
        if (!block) return;
        const key = cSortBtn.dataset.widgetCsort;
        const prev = store.get(`${block.id}:csort`, null);
        const next = prev && prev[0] === key ? [key, prev[1] === 1 ? -1 : 1] : [key, 1];
        store.set(`${block.id}:csort`, next);
        rerenderCard(card);
        return;
      }
      const node = ev.target.closest("[data-widget-fc-node]");
      if (node) {
        const card = node.closest("[data-widget-card]");
        const svgEl = flowSvgOf(card);
        if (svgEl) {
          hydrateFlowLazy(card, svgEl);
          if (flowCtl.get(svgEl)?.flowDragMoved()) return;    // a pan gesture, not a selection
        }
        selectFlowNode(card, node.dataset.widgetFcNode);
      }
    });

    document.addEventListener("keydown", ev => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const node = ev.target.closest?.("[data-widget-fc-node]");
      if (!node) return;
      ev.preventDefault();
      selectFlowNode(node.closest("[data-widget-card]"), node.dataset.widgetFcNode);
    });

    document.addEventListener("change", ev => {
      const sel = ev.target.closest?.("[data-widget-tl-state]");
      if (sel) {
        const card = sel.closest("[data-widget-card]");
        const block = readBlock(card);
        if (block) { store.set(`${block.id}:tlstate`, String(sel.value || "all")); rerenderCard(card); }
        return;
      }
      const chk = ev.target.closest?.("[data-widget-tl-group]");
      if (chk) {
        const card = chk.closest("[data-widget-card]");
        const block = readBlock(card);
        if (block) { store.set(`${block.id}:tlgroup`, !!chk.checked); rerenderCard(card); }
      }
    });

    document.addEventListener("input", ev => {
      const input = ev.target.closest?.("[data-widget-tl-q]");
      if (!input) return;
      const card = input.closest("[data-widget-card]");
      const block = readBlock(card);
      if (!block) return;
      store.set(`${block.id}:tlq`, String(input.value || ""));
      // Re-render only the results (count + list) so the person keeps their
      // focus and typing rhythm; the input element itself is left untouched.
      const results = card.querySelector("[data-widget-tl-results]");
      if (!results) return;
      const total = mergeTimelineEvents(Array.isArray((block.payload || {}).events) ? block.payload.events : []).length;
      results.innerHTML = timelineResultsHtml(block, filteredTimelineEvents(block), total);
    });

    // <details> toggle events do not bubble — capture them at the document.
    document.addEventListener("toggle", ev => {
      const det = ev.target.closest?.("[data-widget-datatable]");
      if (!det) return;
      const card = det.closest("[data-widget-card]");
      const block = readBlock(card);
      if (block) store.set(`${block.id}:datatable`, !!det.open);
    }, true);
  }

  function copyTextToClipboard(text, btn) {
    const done = ok => {
      const original = btn.innerHTML;
      btn.innerHTML = ok ? `${glyph("check")} Copied` : `${glyph("alert")} Copy failed`;
      setTimeout(() => { btn.innerHTML = original; }, 1600);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      ta.remove();
      done(ok);
    }
  }

  function downloadSource(block, btn) {
    const p = block.payload || {};
    const source = String(p.source ?? "");
    const lang = String((p.language || "python")).toLowerCase();
    const ext = SOURCE_EXT[lang] || ".txt";                     // extension whitelist
    const ordinal = Number((p.execution || {}).ordinal || 1);
    try {
      const url = URL.createObjectURL(new Blob([source], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `execution-${Math.max(1, ordinal)}${ext}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("Source downloaded — it is the hash-bound copy of what executed.");
    } catch (err) {
      notify(`Could not download the source: ${err && err.message ? err.message : err}`, true);
    }
  }

  /* Flowcharts may be interacted with before the observer hydrated them (e.g.
     inside a collapsed tool group that was just opened); wire on first touch.
     hydrateFlow registers every wired svg in flowCtl itself, so this is a no-op
     for svg elements that already have pan/zoom state. */
  function hydrateFlowLazy(card, svgEl) {
    if (!svgEl || flowCtl.has(svgEl)) return;
    hydrateFlow(svgEl, makeCtl());
  }

  /* Feed path: renderChatFeed replaces the transcript wholesale, so charts,
     flowcharts and animation mounts are (re)hydrated from a MutationObserver —
     no app.js wiring beyond the one-line HTML delegation is needed. */
  let hydrateQueued = false;
  function queueHydrate() {
    if (hydrateQueued) return;
    hydrateQueued = true;
    (window.requestAnimationFrame || (fn => setTimeout(fn, 0)))(() => {
      hydrateQueued = false;
      hydrateAll(document);
    });
  }
  function hydrateAll(scope) {
    scope.querySelectorAll("[data-widget-chart-mount]:not([data-widget-live])").forEach(m => hydrateChart(m, makeCtl()));
    scope.querySelectorAll("[data-widget-flow-svg]:not([data-widget-live])").forEach(s => {
      hydrateFlowLazy(s.closest("[data-widget-card]"), s);
    });
    scope.querySelectorAll("[data-widget-svg-mount]:not([data-widget-live])").forEach(m => hydrateMedia(m, makeCtl()));
  }

  let moStarted = false;
  function startObserver() {
    if (moStarted || typeof MutationObserver !== "function") return;
    moStarted = true;
    const mo = new MutationObserver(records => {
      for (const r of records) {
        for (const node of r.addedNodes) {
          if (node.nodeType !== 1) continue;
          if (node.matches?.("[data-widget-card], .widget-blocks") || node.querySelector?.("[data-widget-card]")) {
            queueHydrate();
            return;
          }
        }
      }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { wireDocument(); startObserver(); }, { once: true });
  } else {
    wireDocument();
    startObserver();
  }

  window.HutchWidgets = { renderBlocks, renderBlock, blocksHtml };
})();
