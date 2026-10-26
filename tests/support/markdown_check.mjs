// Node harness for src/hutch/server/static/markdown.js (run by tests/test_studio_markdown.py).
// The renderer is an IIFE that exposes globalThis.HutchMarkdown when loaded outside a browser.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

await import(pathToFileURL(path.resolve("src/hutch/server/static/markdown.js")).href);
const md = globalThis.HutchMarkdown;
assert.ok(md && typeof md.render === "function", "HutchMarkdown.render missing");

const textOf = html => html.replace(/<br>/g, "\n").replace(/<[^>]+>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const results = [];
const check = (name, fn) => { try { fn(); results.push([name, true]); } catch (error) { results.push([name, false, error.message]); } };

/* ── plain answers keep their text ─────────────────────────────────────── */
check("plain sentence is one paragraph with identical text", () => {
  const input = "A completed answer from the disabled adapter.";
  assert.equal(md.render(input), `<p>${input}</p>`);
});
check("curly quotes, ellipses and unicode survive", () => {
  const input = "Test scenario finished for “Research the latest news…” — 5 steps · 1750 tokens.";
  assert.equal(textOf(md.render(input)), input);
});
check("soft line breaks are kept", () => {
  assert.equal(md.render("one\ntwo"), "<p>one<br>two</p>");
});
check("blank input renders nothing", () => {
  assert.equal(md.render(""), "");
  assert.equal(md.render("   \n\n  "), "");
  assert.equal(md.render(null), "");
});

/* ── structure ─────────────────────────────────────────────────────────── */
check("headings sit under the page h1", () => {
  const html = md.render("# One\n## Two\n### Three\n#### Four");
  assert.match(html, /<h2 class="md-h md-h1">One<\/h2>/);
  assert.match(html, /<h2 class="md-h md-h2">Two<\/h2>/);
  assert.match(html, /<h3 class="md-h md-h3">Three<\/h3>/);
  assert.match(html, /<h4 class="md-h md-h4">Four<\/h4>/);
});
check("emphasis, strike and inline code", () => {
  const html = md.render("**bold** *ital* ~~gone~~ `x < y` snake_case_name 2 * 3 * 4");
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<em>ital<\/em>/);
  assert.match(html, /<del>gone<\/del>/);
  assert.match(html, /<code>x &lt; y<\/code>/);
  assert.ok(html.includes("snake_case_name"), "snake_case must not become emphasis");
  assert.ok(html.includes("2 * 3 * 4"), "spaced asterisks are literal");
});
check("code span contents are not interpreted", () => {
  const html = md.render("`**not bold** [x](https://a.b)`");
  assert.ok(!html.includes("<strong>") && !html.includes("<a "), html);
});
check("fenced code gets a language label and copy control", () => {
  const html = md.render("```js\nconst a = 1 < 2;\n```");
  assert.match(html, /data-md-code/);
  assert.match(html, /md-code-lang" translate="no">js</);
  assert.match(html, /data-md-copy/);
  assert.match(html, /const a = 1 &lt; 2;/);
});
check("unterminated fence still renders as code", () => {
  const html = md.render("```py\nprint('hi')");
  assert.match(html, /<pre/);
  assert.match(html, /print\(&#39;hi&#39;\)/);
});
check("lists: nested bullets, numbered start, tasks", () => {
  const html = md.render("- a\n  - b\n- c\n\n3. three\n4. four\n\n- [x] done\n- [ ] todo");
  assert.match(html, /<ul><li>a<ul><li>b<\/li><\/ul><\/li><li>c<\/li><\/ul>/);
  assert.match(html, /<ol start="3"><li>three<\/li><li>four<\/li><\/ol>/);
  assert.match(html, /md-task done/);
  assert.match(html, /aria-label="Not done"/);
});
check("tables render header, alignment and escaped cells", () => {
  const html = md.render("| Name | Qty |\n|:--|--:|\n| <b>x</b> | 2 |");
  assert.match(html, /<th style="text-align:left">Name<\/th>/);
  assert.match(html, /<th style="text-align:right">Qty<\/th>/);
  assert.match(html, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.match(html, /role="region"/);
});
check("block quotes recurse", () => {
  assert.match(md.render("> quoted **text**"), /<blockquote><p>quoted <strong>text<\/strong><\/p><\/blockquote>/);
});
check("horizontal rule", () => assert.match(md.render("a\n\n---\n\nb"), /<hr>/));

/* ── links and safety ──────────────────────────────────────────────────── */
check("http, https and mailto links open safely", () => {
  const html = md.render("[ok](https://example.com/a?b=1&c=2) and [mail](mailto:a@b.co)");
  assert.match(html, /<a href="https:\/\/example\.com\/a\?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">ok<\/a>/);
  assert.match(html, /<a href="mailto:a@b\.co"/);
});
check("bare URLs link, trailing punctuation does not", () => {
  const html = md.render("See https://example.com/path.");
  assert.match(html, /href="https:\/\/example\.com\/path"/);
  assert.match(html, /<\/a>\.<\/p>/);
});
for (const [name, input] of [
  ["javascript: link", "[x](javascript:alert(1))"],
  ["data: link", "[x](data:text/html;base64,PHNjcmlwdD4=)"],
  ["vbscript: link", "[x](vbscript:msgbox)"],
  ["relative link", "[x](/etc/passwd)"],
]) {
  check(`${name} is never an anchor`, () => assert.ok(!/<a /.test(md.render(input)), md.render(input)));
}
check("images are never fetched", () => {
  const html = md.render("![pixel](https://tracker.example/p.png)");
  assert.ok(!/<img/i.test(html), html);
  assert.match(html, /pixel \(image\)/);
});
const ALLOWED_TAGS = new Set(["p", "br", "h2", "h3", "h4", "strong", "em", "del", "code", "pre", "ul", "ol", "li", "blockquote", "hr",
  "a", "div", "span", "button", "table", "thead", "tbody", "tr", "th", "td"]);
const ALLOWED_ATTRS = new Set(["href", "target", "rel", "class", "role", "aria-label", "tabindex", "style", "start", "translate",
  "type", "data-md-code", "data-md-copy"]);
// Every emitted tag must be one the renderer builds, with allowlisted attributes and safe values.
function assertStructurallySafe(html) {
  const tag = /<\/?([a-zA-Z0-9]+)((?:\s+[a-zA-Z-]+(?:="[^"]*")?)*)\s*\/?>/g;
  const stripped = html.replace(tag, (whole, name, attrs) => {
    assert.ok(ALLOWED_TAGS.has(name.toLowerCase()), `tag <${name}> is not allowed in: ${html}`);
    for (const [, attr, value] of attrs.matchAll(/\s+([a-zA-Z-]+)(?:="([^"]*)")?/g)) {
      assert.ok(ALLOWED_ATTRS.has(attr), `attribute ${attr} is not allowed in: ${html}`);
      if (attr === "href") assert.match(value, /^(https?:\/\/|mailto:)[^"<>]*$/i, `unsafe href ${value}`);
      if (attr === "style") assert.match(value, /^text-align:(left|right|center)$/, `unsafe style ${value}`);
      if (attr === "target") assert.equal(value, "_blank");
    }
    return "";
  });
  // After removing every legitimate tag, no angle bracket may remain unescaped.
  assert.ok(!/[<>]/.test(stripped), `stray angle bracket survives in: ${html}`);
}
for (const [name, input] of [
  ["script tag", "<script>alert(1)</script>"],
  ["img onerror", '<img src=x onerror="alert(1)">'],
  ["svg onload", "<svg onload=alert(1)>"],
  ["attribute breakout in link", '[x](https://a.b/" onmouseover="alert(1))'],
  ["attribute breakout in label", '[" onmouseover="alert(1)](https://a.b)'],
  ["attribute breakout in bare url", 'https://a.b/"onmouseover="alert(1)'],
  ["html in heading", "# <iframe src=//evil></iframe>"],
  ["html in table", "| a |\n|---|\n| <img src=x onerror=alert(1)> |"],
  ["html in code fence lang", "```<script>alert(1)</script>\nx\n```"],
  ["html in list", "- <a href=javascript:alert(1)>x</a>"],
  ["html in quote", "> <style>*{display:none}</style>"],
  ["entity smuggling", "&lt;script&gt;alert(1)&lt;/script&gt; &#60;script&#62;"],
  ["unclosed tag", "<a href='x"],
  ["placeholder char injection", "\uE0000\uE000 `a`"],
  ["nested emphasis around html", "**<img src=x onerror=alert(1)>**"],
]) {
  check(`${name} is inert`, () => assertStructurallySafe(md.render(input)));
}
/* ── regressions found in code review: content must never vanish or be rewritten ───────────── */
check("a list whose first item is indented keeps every later item", () => {
  const html = md.render("  - a\n- b\n- c");
  assert.deepEqual([...html.matchAll(/<li>([^<]*)/g)].map(m => m[1]), ["a", "b", "c"], html);
});
check("mixed two- and four-space nesting keeps a shallower sibling after a deep run", () => {
  const html = md.render("- a\n    - b\n        - c\n  - d");
  assert.deepEqual([...html.matchAll(/<li>([^<]*)/g)].map(m => m[1]), ["a", "b", "c", "d"], html);
  assert.match(html, /<li>a<ul><li>b<ul><li>c<\/li><\/ul><\/li><li>d<\/li><\/ul><\/li>/);
});
check("an indented fence belongs to its list item and keeps its code block and copy control", () => {
  const html = md.render("1. step\n   ```\n   code\n   ```\n2. next");
  assert.match(html, /<li>step<div class="md-code" data-md-code>/);
  assert.match(html, /data-md-copy/);
  assert.match(html, /<code translate="no">code<\/code>/);
  assert.match(html, /<\/div><\/li><li>next<\/li>/);
});
check("a heading ends in # only when the hashes are a closing run", () => {
  const html = md.render("## Learning C#\n### F#\n## closed ##");
  assert.match(html, />Learning C#</);
  assert.match(html, />F#</);
  assert.match(html, />closed</);
  assert.ok(!html.includes("closed #"), html);
});
check("a URL followed by a code span keeps both intact", () => {
  const html = md.render("Visit https://a.com`x` ok");
  assert.match(html, /<a href="https:\/\/a\.com" [^>]*>https:\/\/a\.com<\/a><code>x<\/code>/);
});
check("a prose line with a pipe above a rule is a paragraph and a rule, not an empty table", () => {
  const html = md.render("text | here\n---");
  assert.equal(html, "<p>text | here</p><hr>");
});
check("a table needs a delimiter row as wide as its header", () => {
  assert.ok(!md.render("a | b | c\n--|--").includes("<table"));
  assert.ok(md.render("a | b\n--|--\n1 | 2").includes("<table"));
  assert.ok(md.render("| a |\n|---|\n| 1 |").includes("<table"));
});

check("large input renders quickly", () => {
  const big = Array.from({ length: 4000 }, (_, i) => `- item **${i}** with \`code\` and [link](https://example.com/${i})`).join("\n");
  const started = performance.now();
  const html = md.render(big);
  assert.ok(html.length > big.length);
  assert.ok(performance.now() - started < 1500, `took ${performance.now() - started}ms`);
});

let failed = 0;
for (const [name, ok, message] of results) {
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${ok ? "" : `\n     ${message}`}`);
  if (!ok) failed += 1;
}
console.log(`${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
