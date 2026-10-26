/* hutch — safe Markdown for assistant answers.

   Contract (tests/e2e/test_studio_markdown.py + tests/test_studio_markdown.mjs):
   · Escape-first: every character of the input is HTML-escaped before any markup is
     built, and only tags this file constructs are ever emitted. Raw HTML in the
     source is shown as text.
   · Links keep http:, https: and mailto: only; each opens in a new tab with
     rel="noopener noreferrer". Remote images are never fetched (local-first, no
     tracking pixels): an image becomes a plain link to its address.
   · A plain answer — no Markdown syntax — renders as one <p> per paragraph with soft
     line breaks, so its text content is unchanged.
   · Unterminated fences render as code to the end of the text (a reply that stops
     mid-block still reads correctly).

   Supported: paragraphs, headings, bold/italic/strike, inline code, fenced code with a
   copy control, block quotes, nested bulleted/numbered/task lists, tables, rules, links
   and bare URLs. Anything else is left as readable plain text. */
(function (root) {
  "use strict";

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = s => String(s).replace(/[&<>"']/g, c => ESC[c]);

  const SAFE_URL = /^(?:https?:\/\/|mailto:)[^\s<>"'`]*$/i;
  function safeHref(raw) {
    const url = String(raw).trim();
    return SAFE_URL.test(url) ? url : "";
  }

  /* ───────────────────────────── inline ───────────────────────────── */

  // Pull code spans out first so their contents are never interpreted, then
  // transform the escaped remainder. Placeholders use a private-use character so
  // they can never collide with escaped user text.
  const PH = "";

  const BARE_URL = new RegExp(`(^|[\\s(])(https?:\\/\\/[^\\s<>"'\`${PH}]+[^\\s<>"'\`${PH}.,;:!?)\\]])`, "g");

  function inline(text) {
    const stash = [];
    const hold = html => { stash.push(html); return `${PH}${stash.length - 1}${PH}`; };

    let s = String(text);

    // code spans: `x` or ``x with ` inside``
    s = s.replace(/(`+)(?!`)([\s\S]*?[^`])\1(?!`)/g, (_, _ticks, body) =>
      hold(`<code>${esc(body.replace(/^ (.+) $/s, "$1"))}</code>`));

    s = esc(s);

    // links: [label](url "title") — label is processed for emphasis, url validated
    s = s.replace(/!?\[([^\]\n]{1,300})\]\(([^()\s]{1,2000}(?:\([^()\s]*\)[^()\s]*)*)(?:\s+&quot;[^\n]*?&quot;)?\)/g,
      (match, label, url) => {
        const image = match.startsWith("!");
        const href = safeHref(url.replace(/&amp;/g, "&"));
        if (!href) return match;
        const shown = image ? `${label} (image)` : label;
        return hold(`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${emphasis(shown)}</a>`);
      });

    // bare URLs (the private-use placeholder is never part of one)
    s = s.replace(BARE_URL, (_, lead, url) => {
      const href = safeHref(url.replace(/&amp;/g, "&"));
      if (!href) return lead + url;
      return `${lead}${hold(`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${url}</a>`)}`;
    });

    s = emphasis(s);
    return s.replace(new RegExp(`${PH}(\\d+)${PH}`, "g"), (_, i) => stash[Number(i)]);
  }

  function emphasis(s) {
    return s
      .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^\w])__(?=\S)([\s\S]*?\S)__(?!\w)/g, "$1<strong>$2</strong>")
      .replace(/(^|[^*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?!\*)/g, "$1<em>$2</em>")
      .replace(/(^|[^\w_])_(?=[^\s_])([^_\n]*?[^\s_])_(?![\w_])/g, "$1<em>$2</em>")
      .replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<del>$1</del>");
  }

  /* ───────────────────────────── blocks ───────────────────────────── */

  const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([\w+#.-]*)[^\n]*$/;
  const HEADING = /^ {0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$/;
  const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/;
  const QUOTE = /^ {0,3}>\s?(.*)$/;
  const LIST = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const TABLE_SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

  function splitRow(line) {
    let row = line.trim();
    if (row.startsWith("|")) row = row.slice(1);
    if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
    const cells = [];
    let cell = "";
    for (let i = 0; i < row.length; i++) {
      if (row[i] === "\\" && row[i + 1] === "|") { cell += "|"; i++; }
      else if (row[i] === "|") { cells.push(cell.trim()); cell = ""; }
      else cell += row[i];
    }
    cells.push(cell.trim());
    return cells;
  }

  function codeBlock(lang, body) {
    const label = lang ? esc(lang.toLowerCase()) : "text";
    return `<div class="md-code" data-md-code><div class="md-code-head"><span class="md-code-lang" translate="no">${label}</span>` +
      `<button type="button" class="md-copy" data-md-copy aria-label="Copy ${label} code">Copy</button></div>` +
      `<pre tabindex="0"><code translate="no">${esc(body)}</code></pre></div>`;
  }

  function tableStarts(line, next) {
    if (!line.includes("|") || next === undefined || !TABLE_SEP.test(next) || !next.includes("-")) return false;
    const columns = splitRow(next).length;
    return columns === splitRow(line).length && (columns > 1 || next.includes("|"));
  }

  function isBlockStart(line, next) {
    return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || LIST.test(line) || tableStarts(line, next);
  }

  function renderList(lines, start) {
    // Collect the contiguous run of list lines (and their indented continuations).
    const items = [];
    let i = start;
    while (i < lines.length) {
      const m = LIST.exec(lines[i]);
      if (m) {
        const indent = m[1].replace(/\t/g, "    ").length;
        const ordered = /\d/.test(m[2]);
        // A different list type at the top level starts a new list (CommonMark).
        if (items.length && indent <= items[0].indent && ordered !== items[0].ordered) break;
        items.push({ indent, ordered, marker: m[2], text: m[3], extra: [], blocks: [] });
        i++;
        continue;
      }
      const fence = items.length && /^(\s{2,})(`{3,}|~{3,})\s*([\w+#.-]*)[^\n]*$/.exec(lines[i]);
      if (fence) {
        const closing = new RegExp(`^\\s*${fence[2][0]}{${fence[2].length},}\\s*$`);
        const body = [];
        i++;
        while (i < lines.length && !closing.test(lines[i])) {
          body.push(lines[i].slice(Math.min(fence[1].length, lines[i].length - lines[i].trimStart().length)));
          i++;
        }
        i++; // closing fence (or EOF)
        items[items.length - 1].blocks.push(codeBlock(fence[3] || "", body.join("\n")));
        continue;
      }
      if (lines[i].trim() === "") {
        // a single blank line may separate loose items; two end the list
        if (i + 1 < lines.length && LIST.test(lines[i + 1])) { i++; continue; }
        break;
      }
      if (/^\s{2,}\S/.test(lines[i]) && items.length) { items[items.length - 1].extra.push(lines[i].trim()); i++; continue; }
      break;
    }
    // Nesting level from a stack of indents: deeper nests, equal is a sibling, shallower pops back
    // (an item less indented than the first is a top-level sibling, not dropped).
    const stack = [];
    for (const item of items) {
      while (stack.length && item.indent < stack[stack.length - 1]) stack.pop();
      if (!stack.length || item.indent > stack[stack.length - 1]) stack.push(item.indent);
      item.level = stack.length - 1;
    }
    const build = (from, level) => {
      let html = "";
      let k = from;
      const ordered = items[from].ordered;
      const startNum = ordered ? parseInt(items[from].marker, 10) : null;
      html += ordered ? `<ol${startNum && startNum !== 1 ? ` start="${startNum}"` : ""}>` : "<ul>";
      while (k < items.length && items[k].level >= level) {
        if (items[k].level > level) { k++; continue; }
        const item = items[k];
        let body = inline([item.text, ...item.extra].join("\n")).replace(/\n/g, "<br>");
        let taskBox = "";
        const task = /^\[( |x|X)\]\s+/.exec(item.text);
        if (task) {
          const done = task[1].toLowerCase() === "x";
          body = inline([item.text.slice(task[0].length), ...item.extra].join("\n")).replace(/\n/g, "<br>");
          taskBox = `<span class="md-task${done ? " done" : ""}" role="img" aria-label="${done ? "Done" : "Not done"}"></span>`;
        }
        let n = k + 1;
        while (n < items.length && items[n].level > level) n++;
        const nested = n > k + 1 ? build(k + 1, items[k + 1].level) : "";
        html += `<li${task ? ' class="md-task-item"' : ""}>${taskBox}${body}${item.blocks.join("")}${nested}</li>`;
        k = n;
      }
      html += ordered ? "</ol>" : "</ul>";
      return html;
    };
    return { html: build(0, 0), next: i };
  }

  function render(source) {
    const text = String(source == null ? "" : source).replace(/\r\n?/g, "\n");
    if (!text.trim()) return "";
    const lines = text.split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim() === "") { i++; continue; }

      let m = FENCE.exec(line);
      if (m) {
        const fence = m[1], lang = m[2] || "";
        const body = [];
        i++;
        while (i < lines.length && !new RegExp(`^ {0,3}${fence[0]}{${fence.length},}\\s*$`).test(lines[i])) { body.push(lines[i]); i++; }
        i++; // closing fence (or EOF)
        out.push(codeBlock(lang, body.join("\n")));
        continue;
      }
      if ((m = HEADING.exec(line))) {
        const level = m[1].length;
        const tag = level <= 2 ? "h2" : level === 3 ? "h3" : "h4";   // the page <h1> is the assistant's name
        out.push(`<${tag} class="md-h md-h${Math.min(level, 4)}">${inline(m[2])}</${tag}>`);
        i++;
        continue;
      }
      if (RULE.test(line)) { out.push("<hr>"); i++; continue; }
      if (QUOTE.test(line)) {
        const inner = [];
        while (i < lines.length && QUOTE.test(lines[i])) { inner.push(QUOTE.exec(lines[i])[1]); i++; }
        out.push(`<blockquote>${render(inner.join("\n"))}</blockquote>`);
        continue;
      }
      if (tableStarts(line, lines[i + 1])) {
        const head = splitRow(line);
        const aligns = splitRow(lines[i + 1]).map(c => /^:-+:$/.test(c) ? "center" : /-+:$/.test(c) ? "right" : /^:-+/.test(c) ? "left" : "");
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].trim() !== "" && lines[i].includes("|")) { rows.push(splitRow(lines[i])); i++; }
        const cell = (tag, value, idx) => `<${tag}${aligns[idx] ? ` style="text-align:${aligns[idx]}"` : ""}>${inline(value)}</${tag}>`;
        out.push(`<div class="md-table" role="region" aria-label="Table" tabindex="0"><table><thead><tr>${head.map((c, idx) => cell("th", c, idx)).join("")}</tr></thead>` +
          `<tbody>${rows.map(r => `<tr>${head.map((_, idx) => cell("td", r[idx] ?? "", idx)).join("")}</tr>`).join("")}</tbody></table></div>`);
        continue;
      }
      if (LIST.test(line)) {
        const { html, next } = renderList(lines, i);
        out.push(html);
        i = next;
        continue;
      }
      // paragraph: gather until a blank line or a new block
      const para = [line];
      i++;
      while (i < lines.length && lines[i].trim() !== "" && !isBlockStart(lines[i], lines[i + 1])) { para.push(lines[i]); i++; }
      out.push(`<p>${inline(para.join("\n")).replace(/\n/g, "<br>")}</p>`);
    }
    return out.join("");
  }

  /* ─────────────────────── copy control (delegated) ─────────────────────── */

  const timers = new WeakMap();
  function onClick(event) {
    const button = event.target.closest && event.target.closest("[data-md-copy]");
    if (!button) return;
    const code = button.closest("[data-md-code]")?.querySelector("code");
    if (!code) return;
    const done = ok => {
      button.textContent = ok ? "Copied" : "Copy failed";
      button.dataset.state = ok ? "copied" : "failed";
      clearTimeout(timers.get(button));
      timers.set(button, setTimeout(() => { button.textContent = "Copy"; delete button.dataset.state; }, 1800));
    };
    const text = code.textContent || "";
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
    else done(false);
  }
  if (typeof document !== "undefined") document.addEventListener("click", onClick);

  const api = { render, inline, safeHref, escape: esc };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HutchMarkdown = api;
})(typeof window !== "undefined" ? window : globalThis);
