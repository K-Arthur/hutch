import fs from "fs"; import vm from "vm";
// -- minimal DOM/browser stubs sufficient for module init + pure renderers --
const noop = () => {};
const classList = { add: noop, remove: noop, contains: () => false, toggle: noop };
const documentStub = {
  readyState: "complete",
  documentElement: { classList },
  addEventListener: noop,
  createElement: () => ({ style: {}, setAttribute: noop, appendChild: noop, select: noop, remove: noop, click: noop }),
  querySelector: () => null,
  querySelectorAll: () => [],
  body: { appendChild: noop },
};
const storeMap = new Map();
const sandbox = {
  window: {},
  document: documentStub,
  navigator: {},
  localStorage: { getItem: k => storeMap.get(k) ?? null, setItem: (k, v) => storeMap.set(k, v), removeItem: k => storeMap.delete(k) },
  matchMedia: () => ({ matches: false, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }),
  MutationObserver: class { observe(){} disconnect(){} },
  ResizeObserver: class { observe(){} disconnect(){} unobserve(){} },
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  requestAnimationFrame: fn => setTimeout(fn, 0),
  console, setTimeout, clearTimeout, URL, Blob: class { constructor(){} },
  DOMParser: class { parseFromString() { throw new Error("not needed in smoke"); } },
  XMLSerializer: class {},
  CSS: { escape: s => String(s) },
  AbortController: globalThis.AbortController,
  fetch: () => Promise.reject(new Error("no fetch in smoke")),
};
sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.self = sandbox;
vm.createContext(sandbox);
const src = fs.readFileSync("src/hutch/server/static/widgets.js", "utf8");
vm.runInContext(src, sandbox, { filename: "widgets.js" });
const HW = sandbox.window.HutchWidgets;
if (!HW || typeof HW.blocksHtml !== "function" || typeof HW.renderBlocks !== "function" || typeof HW.renderBlock !== "function") {
  console.error("FAIL: window.HutchWidgets API incomplete"); process.exit(1);
}
console.log("API OK: renderBlocks, renderBlock, blocksHtml exposed");

let failures = 0;
const check = (name, cond, extra = "") => {
  if (!cond) { failures++; console.error(`FAIL: ${name} ${extra}`); }
  else console.log(`ok: ${name}`);
};

const fixtures = {};
for (const f of fs.readdirSync("tests/fixtures/blocks")) {
  fixtures[f.replace(/\.json$/, "")] = JSON.parse(fs.readFileSync(`tests/fixtures/blocks/${f}`, "utf8"));
}
const invalid = fixtures.invalid;
const kinds = Object.keys(fixtures).filter(k => k !== "invalid");

// every valid fixture renders a card with its block id and no fallback panel
for (const k of kinds) {
  const b = fixtures[k];
  const html = HW.blocksHtml([b], [], {});
  check(`${k}: card rendered`, html.includes(`data-block-id="${b.id}"`), html.slice(0, 120));
  check(`${k}: no fallback`, !html.includes("could not be rendered"));
  check(`${k}: payload embedded`, html.includes("data-widget-payload"));
}
// invalid envelope → labeled fallback, with reason, never silent
const badHtml = HW.blocksHtml([invalid], [], {});
check("invalid: fallback panel", badHtml.includes("could not be rendered"));
check("invalid: keeps id", badHtml.includes("blk_NOT-VALID"));
// block_errors entries render labeled chips
const errHtml = HW.blocksHtml([], [{ kind: "slideshow", error: "unknown block kind 'slideshow'" }], {});
check("block_errors: labeled chip", errHtml.includes("Output block rejected") && errHtml.includes("slideshow"));
// unknown kind → fallback naming it
const unkHtml = HW.blocksHtml([{ v: 1, id: "blk_aaaaaaaaaaaaaaaa", kind: "slideshow", revision: 1, availability: "ready", text_fallback: "x", provenance: { run_id: "r", tool: "t" }, payload: {} }], [], {});
check("unknown kind: fallback names it", unkHtml.includes("unsupported block kind") && unkHtml.includes("slideshow"));
// empty inputs → ''
check("empty → empty string", HW.blocksHtml([], [], {}) === "");

// per-kind specifics
const chart = HW.blocksHtml([fixtures.chart], [], {});
check("chart: data table toggle", chart.includes("Data table") && chart.includes("data-widget-datatable"));
check("chart: axis labels + units", chart.includes("elapsed") && chart.includes("(s)"));
check("chart: summary is honest", chart.includes("linear") && chart.includes("requests/s"));
const tbl = HW.blocksHtml([fixtures.table], [], {});
check("table: first-N disclosure", tbl.includes("Showing first 2 of 8 rows"));
check("table: dtype labels", tbl.includes("text") && tbl.includes("number"));
const tl = HW.blocksHtml([fixtures.timeline], [], {});
check("timeline: state chips as text", tl.includes("confirmed") && tl.includes("planned"));
check("timeline: precision + timezone", tl.includes("second precision") && tl.includes("UTC"));
check("timeline: local filter note", tl.includes("nothing is sent anywhere"));
const cmp = HW.blocksHtml([fixtures.comparison], [], {});
check("comparison: unsupported badge text", cmp.includes("Unsupported"));
check("comparison: unit shown", cmp.includes("USD"));
check("comparison: ranking note", cmp.includes("local shell wins"));
check("comparison: th scope", cmp.includes('scope="col"') && cmp.includes('scope="row"'));
const fc = HW.blocksHtml([fixtures.flowchart], [], {});
check("flowchart: focusable nodes", fc.includes('role="button"') && fc.includes("tabindex"));
check("flowchart: arrow marker", fc.includes("marker-end") && fc.includes("wf-arrow-"));
check("flowchart: group container", fc.includes("ingest"));
check("flowchart: reset view", fc.includes("Reset view"));
check("flowchart: cycle edge kept (rejection loop)", fc.includes("on rejection"));
const md = HW.blocksHtml([fixtures.media], [], {});
check("media: alt text present", md.includes("Bar chart of requests per second"));
check("media: whitelisted content URL", md.includes("/api/v1/media/media_0f1e2d3c4b5a6978/versions/1/content"));
check("media: video hardening absent for image (no autoplay)", !md.includes("autoplay"));
const cr = HW.blocksHtml([fixtures.code_receipt], [], {});
check("code_receipt: source rendered", cr.includes("the answer is"));
check("code_receipt: receipt line", cr.includes("execution #1") && cr.includes("environment generation 3"));
check("code_receipt: status badge", cr.includes("ok"));
check("code_receipt: copy + download", cr.includes("cr-copy") && cr.includes("cr-download"));
check("code_receipt: immutable note", cr.includes("hash-bound"));
const st = HW.blocksHtml([fixtures.status], [], {});
check("status: text label", st.includes("Running") && st.includes("render"));
const ar = HW.blocksHtml([fixtures.artifact_ref], [], {});
check("artifact_ref: document download URL", ar.includes("/api/v1/documents/doc_0f1e2d3c4b5a6978/versions/2/download"));
check("artifact_ref: name + digest", ar.includes("quarterly-report.pdf") && ar.includes("SHA-256"));
const tx = HW.blocksHtml([fixtures.text], [], {});
check("text: content", tx.includes("42 answers"));

// availability: failed → fallback with availability label, text_fallback preserved
const failedBlock = { ...fixtures.chart, availability: "failed" };
const fHtml = HW.blocksHtml([failedBlock], [], {});
check("failed availability: labeled", fHtml.includes("availability: failed") && fHtml.includes("Line chart: requests"));

// timeline late-merge: duplicate id with corrected_from merges without duplicates
const merged = HW.blocksHtml([{ ...fixtures.timeline, payload: { events: [
  { id: "e1", label: "Original", when: { iso8601: "2026-10-10T09:00:00+00:00", precision: "second", timezone: "UTC" }, state: "reported" },
  { id: "e1", label: "Fixed", when: { iso8601: "2026-10-10T09:05:00+00:00", precision: "second", timezone: "UTC" }, state: "corrected", corrected_from: "e0" },
] } }], [], {});
check("timeline merge: one entry per id", (merged.match(/data-event-id="e1"/g) || []).length === 1);
check("timeline merge: corrected chip + from", merged.includes("corrected") && merged.includes("corrected from event e0"));

console.log(failures ? `\n${failures} FAILURES` : "\nALL SMOKE CHECKS PASSED");
process.exit(failures ? 1 : 0);
